"""
Run by hand: which rule tells the trees and buildings of the surface model from the terrain's
own rock (obstacles.py; docs/roadmap.md, priority 1).

run captures the line search of each place, analyses it and writes the report:

    uv run tools/obstacle_study.py run --out <scratch>/study R41 R40 \
        --place "cwm-silyn=--lat 53.03 --lon -4.215 --radius 400 --min-length 50 --max-length 400"

A place is a regression test (its options from tests/regression.json) or NAME=OPTIONS of
findaline.py. Each search runs in a child process with a data folder of its own,
<out>/<name>/data, whose cache/ links to the real cache (--cache), as tests/regression.py does,
and with linesearch.find_valid_lines wrapped as tools/perf_line_funnel.py wraps it: every call's
grids, anchors and parameters (<out>/<name>/capture/call-<k>/), with the georeference of its grid
and the lines it found. A captured place is not searched again unless --again. analyse
<out>/<name> and report <out> redo those steps alone.

analyse takes every line over trees/buildings (clearance over the surface model <= 0) and the
pixels where the surface stands above the line's limit, and asks which of them each rule keeps
as obstacles: A<r> (the envelope of r pixels, obstacles.is_obstacle, r = 1..10), A1+W<deg>/<px>
(with the band around steep terrain), B<k> (a tolerance of k * res * tan(slope) + MIN_HEIGHT),
C<deg> (none on terrain at least that steep), D<k> (none within k steps of an anchor), F (A1
where CHMv2 sees a tree within a pixel or the terrain is gentler than GENTLE) and F-trees (A1
where CHMv2 sees a tree). A line stays marked while one of its pixels does. The production
kernel checks the counts: linesearch.evaluate_lines over the raw surface gives the captured
clearances, over obstacles.obstacle_surface the marks of A1.

What a pixel is comes from two layers read by HTTP range requests (here only, never in the app):
Meta/WRI's CHMv2 canopy heights (about 1 m, trees; CC BY 4.0) and ESA WorldCover 2021 (10 m,
CC BY 4.0). Tree: CHMv2 >= TREE m within a pixel; built-up: WorldCover 50; rock: CHMv2 < SHRUB m
within a pixel and WorldCover neither tree cover nor built-up. A line whose pixels are all rock
should lose its mark ("rock only"), a line with a tree or a building should keep it ("real").
Also measured: the shift of CHMv2 against the surface's height above the terrain on gentle
ground, and pictures of sample lines (<out>/<name>/chips/).
"""

import argparse
import glob
import json
import math
import os
import re
import shlex
import shutil
import subprocess
import sys
from types import SimpleNamespace
from typing import Callable, Dict, List, Optional, Tuple

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "tools"))
sys.path.insert(0, os.path.join(HERE, "tests"))

import numpy as np  # noqa: E402
from scipy import ndimage  # noqa: E402

import cache  # noqa: E402
import helpers as sh  # noqa: E402
import obstacles  # noqa: E402
import sag as sg  # noqa: E402

CHM_URL = "https://dataforgood-fb-data.s3.amazonaws.com/forests/v2/global/dinov3_global_chm_v2_ml3"
WORLDCOVER_URL = "https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map"
TREE, SHRUB = 3.0, 1.0      # CHMv2 metres: a tree; below SHRUB nothing grows there
TREE_COVER, BUILT_UP = 10, 50  # WorldCover classes
GENTLE = 30.0               # degrees: F keeps A1's obstacles on gentler terrain without CHMv2 (buildings)
RADII = range(1, 11)
WALLS = ((70, 2), (75, 2), (80, 2), (70, 3), (75, 3), (80, 3), (70, 5), (75, 5), (80, 5))
SLOPE_FACTORS = (0.5, 1.0)
MASK_SLOPES = (55, 65, 75)
ANCHOR_ZONES = (1, 2, 3)
SHIFT = 8                   # pixels each way of the search for the shift of CHMv2
ALIGN_GAIN = 0.03           # CHMv2 is moved by its shift when that raises r by this much
CONTEXT_RADII = (1, 2, 3)   # A<r>+V<k>: A<r>, and a pixel it excuses stays an obstacle when a crown
CONTEXT_REACH = (1, 2)      # within k pixels (surface TREE above its terrain gentler than CANOPY_SLOPE,
CANOPY_SLOPE = 50.0         # above its own envelope) reaches its surface less MIN_HEIGHT
WINDOW = 40                 # pixels around the pixel a picture shows
GROUPS = {"removed_rock": "A1 removes the mark, all pixels rock",
          "lost": "A1 removes the mark, a tree (CHMv2) or building among the pixels",
          "kept_real": "A1 keeps the mark, a tree (CHMv2) or building among its pixels",
          "residual_rock": "A1 keeps the mark, its pixels all rock"}
DISTANCES = ((1, 1), (2, 2), (3, 3), (4, 5), (6, 10), (11, 20), (21, 10 ** 9))
SLOPES = ((0, 30), (30, 50), (50, 70), (70, 80), (80, 91))
REPORT_RULES = ("raw", "A1", "A2", "A3", "A1+W75/2", "A1+W75/3", "A1+V2", "A2+V2", "A3+V2", "C65", "D2", "F")


def rule_names() -> List[str]:
    return (["raw"] + [f"A{r}" for r in RADII] + [f"A1+W{d}/{p}" for d, p in WALLS]
            + [f"A{r}+V{k}" for r in CONTEXT_RADII for k in CONTEXT_REACH]
            + [f"B{k:g}" for k in SLOPE_FACTORS] + [f"C{d}" for d in MASK_SLOPES]
            + [f"D{k}" for k in ANCHOR_ZONES] + ["F", "F-trees"])


# ---------------------------------------------------------------------------------------------
# capture (a child process per place)

class Capture:
    """perf_line_funnel's capture of every find_valid_lines call, plus the georeference of the
    call's grid (from search._lines) and the lines it returned (lines.npz)."""

    def __init__(self, out: str):
        import perf_line_funnel as plf
        self.inner = plf.Capture(out, None)
        self.grid = None  # (grid, core) of the running search._lines

    def __call__(self, *args, **kwargs):
        k = self.inner.n
        result = self.inner(*args, **kwargs)
        folder = os.path.join(self.inner.out, f"call-{k}")
        grid, core = self.grid
        with open(os.path.join(folder, "grid.json"), "w") as f:
            json.dump({"crs": grid.crs, "left": grid.left, "top": grid.top, "res": grid.res, "height": grid.height,
                       "width": grid.width, "core": list(core) if core is not None else None}, f, indent=1)
        c = result.columns
        np.savez(os.path.join(folder, "lines.npz"), a1=c["a1"], a2=c["a2"], clearance=c["clearance"],
                 clearance_nmpt=c["clearance_nmpt"])
        return result


def capture(out: str, search_args: List[str]) -> int:
    import runpy

    import linesearch as ls
    import search

    os.makedirs(out, exist_ok=True)
    os.environ.setdefault("FINDALINE_PROGRESS", "text")
    obstacles.RULE = None  # the surface model as it is: the rules are what this tool compares
    wrapper = Capture(out)
    original = search._lines

    def lines(plan, data, core=None, before=0):
        wrapper.grid = plan.grid, core
        return original(plan, data, core, before)

    search._lines = lines  # find_lines and search_lines look it up at each call
    ls.find_valid_lines = wrapper
    sys.argv = [os.path.join(HERE, "findaline.py"), *search_args, "--no-plot", "--yes", "--ortho", "never"]
    code = 0
    try:
        runpy.run_path(sys.argv[0], run_name="__main__")
    except SystemExit as e:
        if e.code not in (None, 0):
            print(f"findaline.py ended with {e.code!r}", file=sys.stderr)
            code = 1
    finally:
        ls.find_valid_lines = wrapper.inner.original
        search._lines = original
    print(f"find_valid_lines called {wrapper.inner.n} times; captured into {out}")
    return code


# ---------------------------------------------------------------------------------------------
# the outside layers (CHMv2, WorldCover) on a grid

def chm_index(out: str) -> Tuple[np.ndarray, np.ndarray]:
    """The CHMv2 tiles (names, lon/lat boxes) from the provider's tiles.geojson, read once into
    <out>/chmv2-tiles.npz."""
    path = os.path.join(out, "chmv2-tiles.npz")
    if not os.path.exists(path):
        import requests
        answer = requests.get(f"{CHM_URL}/tiles.geojson", headers=cache.http_headers(), timeout=300)
        answer.raise_for_status()
        names, boxes = [], []
        for feature in answer.json()["features"]:
            ring = np.asarray(feature["geometry"]["coordinates"][0], dtype=np.float64)
            names.append(feature["properties"]["tile"])
            boxes.append([ring[:, 0].min(), ring[:, 1].min(), ring[:, 0].max(), ring[:, 1].max()])
        np.savez(path, names=np.array(names), boxes=np.array(boxes))
    with np.load(path) as data:
        return data["names"], data["boxes"]


def _wgs84_box(grid: Dict) -> Tuple[float, float, float, float]:
    from rasterio.warp import transform_bounds
    bottom = grid["top"] - grid["height"] * grid["res"]
    right = grid["left"] + grid["width"] * grid["res"]
    return transform_bounds(grid["crs"], "EPSG:4326", grid["left"], bottom, right, grid["top"], densify_pts=21)


def chm_urls(grid: Dict, index) -> List[str]:
    names, boxes = index
    west, south, east, north = _wgs84_box(grid)
    hit = (boxes[:, 0] < east) & (boxes[:, 2] > west) & (boxes[:, 1] < north) & (boxes[:, 3] > south)
    return [f"{CHM_URL}/chm/{name}.tif" for name in names[hit]]


def worldcover_urls(grid: Dict) -> List[str]:
    west, south, east, north = _wgs84_box(grid)
    urls = []
    for lat in range(int(math.floor(south / 3) * 3), int(math.ceil(north)), 3):
        for lon in range(int(math.floor(west / 3) * 3), int(math.ceil(east)), 3):
            name = f"{'N' if lat >= 0 else 'S'}{abs(lat):02d}{'E' if lon >= 0 else 'W'}{abs(lon):03d}"
            urls.append(f"{WORLDCOVER_URL}/ESA_WorldCover_10m_2021_v200_{name}_Map.tif")
    return urls


def on_grid(urls: List[str], grid: Dict, resampling) -> Optional[np.ndarray]:
    """Remote rasters warped onto the grid's pixels (float32, NaN where none has data); None
    when none of them exists. Inside sources.net's GDAL settings, a read during which GDAL
    signalled an error is made again (net.gdal_errors: values it could not fetch come back as
    zeros), as sources/readers/windows.py does."""
    import rasterio as rio
    import rasterio.cache
    from affine import Affine
    from rasterio.warp import reproject

    from sources import net

    shape = (grid["height"], grid["width"])
    transform = Affine(grid["res"], 0, grid["left"], 0, -grid["res"], grid["top"])
    out, found = np.full(shape, np.nan, dtype=np.float32), False
    with net._gdal_http():
        for url in urls:
            for attempt in range(net.RETRIES):
                part = np.full(shape, np.nan, dtype=np.float32)
                try:
                    with net.gdal_errors() as errors:
                        with rio.open(net._remote(url)) as src:
                            reproject(rio.band(src, 1), part, src_transform=src.transform, src_crs=src.crs,
                                      src_nodata=src.nodata, dst_transform=transform, dst_crs=grid["crs"],
                                      dst_nodata=np.nan, resampling=resampling)
                except rio.errors.RasterioIOError as e:
                    if re.search(r"\b404\b|No such file|does not exist", str(e)):
                        part = None
                        break
                    raise
                if not errors:
                    break
                rasterio.cache.invalidate(url)
                if attempt == net.RETRIES - 1:
                    raise RuntimeError(f"could not read {url} completely: {'; '.join(errors)}")
                net._sleep(attempt)
            if part is not None:
                out, found = np.fmax(out, part), True
    return out if found else None


def outside_layers(index) -> Callable:
    """The layers of a call's grid: (CHMv2 in metres by its maximum per pixel, WorldCover's
    class), kept in the call's folder (chmv2.npy, worldcover.npy: a missing layer is an empty
    file) so pictures and a second analysis read them from there."""
    from rasterio.warp import Resampling

    def layers(call: str, grid: Dict):
        found = []
        for name, urls, resampling in (("chmv2", lambda: chm_urls(grid, index) if index is not None else [],
                                        Resampling.max),
                                       ("worldcover", lambda: worldcover_urls(grid), Resampling.nearest)):
            path = os.path.join(call, f"{name}.npy")
            if not os.path.exists(path):
                values = on_grid(urls(), grid, resampling)
                np.save(path, values if values is not None else np.zeros(0, dtype=np.float32))
            values = np.load(path)
            found.append(values if values.size else None)
        return tuple(found)
    return layers


def _moved(a: np.ndarray, dy: int, dx: int) -> np.ndarray:
    """a moved dy rows down and dx columns right, NaN where nothing moved in."""
    h, w = a.shape
    out = np.full(a.shape, np.nan, dtype=np.float32)
    out[max(dy, 0):h + min(dy, 0), max(dx, 0):w + min(dx, 0)] = a[max(-dy, 0):h + min(-dy, 0), max(-dx, 0):w + min(-dx, 0)]
    return out


def chm_shift(z: np.ndarray, s: np.ndarray, chm: np.ndarray, res: float, slope: np.ndarray) -> Optional[Dict]:
    """The move of CHMv2 (metres east and north) that matches the surface's height above the
    terrain best on ground gentler than 15 degrees (Pearson's r); None without enough trees."""
    step = max(1, int(math.sqrt(z.size / 2e6)))  # about 2 million pixels compared
    height = np.clip(s - z, 0, 40)[::step, ::step]
    chm = chm[::step, ::step]
    with np.errstate(invalid="ignore"):
        gentle = (slope[::step, ::step] < 15) & np.isfinite(height)
    if gentle.sum() < 1000 or np.nanstd(np.where(gentle, height, np.nan)) < 1:
        return None
    reach = max(1, round(SHIFT / step))
    best, at_zero = None, None
    for dy in range(-reach, reach + 1):
        for dx in range(-reach, reach + 1):
            moved = _moved(chm, dy, dx)
            both = gentle & np.isfinite(moved)
            if both.sum() < 1000:
                continue
            r = float(np.corrcoef(height[both], moved[both])[0, 1])
            if dx == dy == 0:
                at_zero = r
            if best is None or r > best[0]:
                best = (r, dx, dy)
    if best is None:
        return None
    return {"east_m": best[1] * step * res, "north_m": -best[2] * step * res, "r_best": round(best[0], 3),
            "r_zero": None if at_zero is None else round(at_zero, 3), "pixels": int(gentle.sum())}


# ---------------------------------------------------------------------------------------------
# analyse

class SavedTable(SimpleNamespace):
    """A sag.EnvelopeTable from the arrays a capture saved (helpers.max_safe_elevation calls it)."""
    __call__ = sg.EnvelopeTable.__call__


def saved_table(inputs: Dict, params: Dict):
    if not params["sag"]:
        return None
    if "sag_sag" not in inputs:
        return sg.EnvelopeTable(sg.Rigging(**params["rigging"]), params["sag_min_span"], params["sag_max_span"])
    return SavedTable(spans=inputs["sag_spans"], sag=inputs["sag_sag"], fractions=inputs["sag_fractions"],
                      RATIOS=sg.EnvelopeTable.RATIOS, rig=sg.Rigging(**params["rigging"]))


def line_pixels(a1, a2) -> Tuple[np.ndarray, np.ndarray, np.ndarray, int]:
    """The pixels between two anchors as helpers.evaluate_line takes them: t, rows, cols, steps."""
    (r1, c1), (r2, c2) = a1, a2
    dr, dc = int(r2) - int(r1), int(c2) - int(c1)
    steps = max(abs(dr), abs(dc))
    t = np.arange(1, steps) / steps
    return t, r1 + np.rint(dr * t).astype(np.intp), c1 + np.rint(dc * t).astype(np.intp), steps


def obstacle_pixels(z: np.ndarray, s: np.ndarray, res: float, table, a1: np.ndarray, a2: np.ndarray) -> Dict:
    """The pixels where the surface stands at or above each line's limit (the computation of
    helpers.evaluate_line): line (index into a1), step from anchor 1, the line's steps, row,
    col and the margin (limit minus surface, <= 0), in the order of the lines."""
    parts = {k: [] for k in ("line", "step", "steps", "row", "col", "margin")}
    for k in range(len(a1)):
        t, rows, cols, steps = line_pixels(a1[k], a2[k])
        length = float(np.hypot(*(a2[k] - a1[k]))) * res
        limit = sh.max_safe_elevation(t, length, float(z[a1[k][0], a1[k][1]]), float(z[a2[k][0], a2[k][1]]), table)
        margin = limit - s[rows, cols]
        with np.errstate(invalid="ignore"):
            bad = np.flatnonzero(margin <= 0)  # NaN: not measured
        parts["line"].append(np.full(len(bad), k))
        parts["step"].append(bad + 1)
        parts["steps"].append(np.full(len(bad), steps))
        parts["row"].append(rows[bad])
        parts["col"].append(cols[bad])
        parts["margin"].append(margin[bad])
    empty = {"line": np.int64, "step": np.int64, "steps": np.int64, "row": np.intp, "col": np.intp,
             "margin": np.float64}
    return {k: np.concatenate(v) if v else np.zeros(0, dtype=empty[k]) for k, v in parts.items()}


def in_core(a1: np.ndarray, a2: np.ndarray, grid: Dict) -> np.ndarray:
    """The lines whose first anchor (smaller x, then y) lies in the call's core, as
    search.line_coordinates keeps them (all without a core)."""
    if grid["core"] is None:
        return np.ones(len(a1), dtype=bool)
    left, bottom, right, top = grid["core"]
    xy = lambda a: (grid["left"] + (a[:, 1] + 0.5) * grid["res"], grid["top"] - (a[:, 0] + 0.5) * grid["res"])  # noqa: E731
    (x1, y1), (x2, y2) = xy(a1), xy(a2)
    first = (x1 < x2) | ((x1 == x2) & (y1 <= y2))
    x, y = np.where(first, x1, x2), np.where(first, y1, y2)
    return (left <= x) & (x < right) & (bottom <= y) & (y < top)


def rule_flags(z: np.ndarray, s: np.ndarray, res: float, pix: Dict, chm3: Optional[np.ndarray],
               slope_grid: np.ndarray) -> Dict:
    """Per rule, which of the pixels (obstacle_pixels) it keeps as obstacles."""
    rows, cols = pix["row"], pix["col"]
    sv, zv = s[rows, cols], z[rows, cols]
    slope = slope_grid[rows, cols]
    flags = {"raw": np.ones(len(rows), dtype=bool)}
    with np.errstate(invalid="ignore"):
        for r in RADII:
            flags[f"A{r}"] = sv > obstacles.envelope(z, r)[rows, cols] + np.float32(obstacles.MIN_HEIGHT)
        for wall in WALLS:
            flags[f"A1+W{wall[0]}/{wall[1]}"] = obstacles.is_obstacle(z, s, res, wall=wall)[rows, cols]
        height = s - z
        for r in CONTEXT_RADII:
            crowns = np.where((height >= TREE) & (slope_grid < CANOPY_SLOPE)
                              & obstacles.is_obstacle(z, s, res, radius=r), s, np.float32(-np.inf))
            for k in CONTEXT_REACH:
                near = ndimage.maximum_filter(crowns, size=2 * k + 1, mode="constant", cval=-np.inf)[rows, cols]
                flags[f"A{r}+V{k}"] = flags[f"A{r}"] | ((sv - zv > obstacles.MIN_HEIGHT)
                                                          & (near >= sv - obstacles.MIN_HEIGHT))
        for k in SLOPE_FACTORS:
            flags[f"B{k:g}"] = sv - zv > k * res * np.tan(np.radians(slope)) + obstacles.MIN_HEIGHT
        for degrees in MASK_SLOPES:
            flags[f"C{degrees}"] = (sv - zv > obstacles.MIN_HEIGHT) & (slope < degrees)
    for k in ANCHOR_ZONES:
        flags[f"D{k}"] = np.minimum(pix["step"], pix["steps"] - pix["step"]) > k
    if chm3 is not None:
        tree = chm3[rows, cols] >= SHRUB
        with np.errstate(invalid="ignore"):
            flags["F"] = flags["A1"] & (tree | (slope < GENTLE))
        flags["F-trees"] = flags["A1"] & tree
    return flags


def _bins(values: np.ndarray, bins) -> List[int]:
    return [int(((values >= lo) & (values <= hi) if hi < 10 ** 9 else values >= lo).sum()) for lo, hi in bins]


def _slope_bins(values: np.ndarray) -> List[int]:
    with np.errstate(invalid="ignore"):
        return [int(((values >= lo) & (values < hi)).sum()) for lo, hi in SLOPES]


def analyse_call(call: str, layers: Optional[Callable] = None, chips: Optional[Dict] = None,
                 chip_rule: str = "A1") -> Optional[Dict]:
    """The counts of one find_valid_lines call (see the module's docstring). layers(call, grid)
    gives CHMv2 and WorldCover on the grid (outside_layers); chips, when given, collects the
    candidates for pictures per group of chip_rule: {group: [(call, line, info)]}."""
    import linesearch as ls
    import perf_line_funnel as plf

    inputs, params, _ = plf.load_call(call)
    if "surface" not in inputs or not os.path.exists(os.path.join(call, "lines.npz")):
        return None
    with open(os.path.join(call, "grid.json")) as f:
        grid = json.load(f)
    with np.load(os.path.join(call, "lines.npz")) as data:
        lines = {k: data[k] for k in data.files}
    z = np.asarray(inputs["elevation"], dtype=np.float32)
    s = np.asarray(inputs["surface"], dtype=np.float32)
    res, table = float(params["res"]), saved_table(inputs, params)
    a1, a2 = lines["a1"].astype(np.int64), lines["a2"].astype(np.int64)
    n = len(a1)
    with np.errstate(invalid="ignore"):
        marked = lines["clearance_nmpt"] <= 0  # NaN: not measured, never marked
    slope_grid = obstacles.slope_degrees(z, res)

    # The production kernel: the raw surface gives the captured clearances, the obstacle surface A1's marks
    checks = {"lines": n}
    if n:
        anchors = np.vstack([a1, a2])
        found = np.column_stack([np.arange(n), np.arange(n) + n])
        down = sh.downslope(z, anchors, res)
        raw = ls.evaluate_lines(found, anchors, z, res, s, table, "mark", params["high_above"], None, down)
        checks["raw_equal"] = bool(len(raw) == n and np.array_equal(raw.columns["clearance_nmpt"],
                                                                     lines["clearance_nmpt"], equal_nan=True))
        rule = ls.evaluate_lines(found, anchors, z, res, obstacles.obstacle_surface(z, s, res), table, "mark",
                                 params["high_above"], None, down)
        with np.errstate(invalid="ignore"):
            kernel_a1 = rule.columns["clearance_nmpt"] <= 0

    idx = np.flatnonzero(marked)
    pix = obstacle_pixels(z, s, res, table, a1[idx], a2[idx])
    with_pixels = np.zeros(len(idx), dtype=bool)
    with_pixels[pix["line"]] = True
    if not with_pixels.all():  # every line over trees/buildings has a pixel above its limit
        raise RuntimeError(f"{call}: {int((~with_pixels).sum())} lines over trees/buildings without a pixel above "
                           "their limit: obstacle_pixels no longer computes what helpers.evaluate_line does")
    starts = np.searchsorted(pix["line"], np.arange(len(idx)))

    chm, wc = layers(call, grid) if layers is not None else (None, None)
    chm3, shift = None, None
    if chm is not None:
        shift = chm_shift(z, s, chm, res, slope_grid)
        if shift and shift["r_zero"] is not None and shift["r_best"] >= shift["r_zero"] + ALIGN_GAIN:
            chm = _moved(chm, round(-shift["north_m"] / res), round(shift["east_m"] / res))  # aligned
            shift["applied"] = True
        chm3 = ndimage.maximum_filter(np.where(np.isnan(chm), -1, chm), size=3, mode="constant", cval=-1)
    flags = rule_flags(z, s, res, pix, chm3, slope_grid)
    per_line = {name: np.logical_or.reduceat(f, starts) if len(f) else np.zeros(0, dtype=bool)
                for name, f in flags.items()}
    if n:
        a1_marks = np.zeros(n, dtype=bool)
        a1_marks[idx] = per_line["A1"]
        checks["a1_equal"] = bool(np.array_equal(a1_marks, kernel_a1))

    # What the pixels are: a tree when CHMv2 and WorldCover agree and the lidar's surface stands
    # TREE above its terrain there too (CHMv2 takes rock towers and their shadows for trees at times
    # and spreads the crowns of a forest onto the rock beside it), "tree_chm" by CHMv2 alone
    rows, cols = pix["row"], pix["col"]
    none = np.zeros(len(rows), dtype=bool)
    tree_chm = chm3[rows, cols] >= TREE if chm3 is not None else none
    with np.errstate(invalid="ignore"):
        tall = s[rows, cols] - z[rows, cols] >= TREE
    tree = tree_chm & (wc[rows, cols] == TREE_COVER) & tall if wc is not None else none
    built = wc[rows, cols] == BUILT_UP if wc is not None else none
    rock = none
    if chm3 is not None and wc is not None:
        c, w = chm3[rows, cols], wc[rows, cols]
        rock = (c >= 0) & (c < SHRUB) & (w > 0) & (w != TREE_COVER) & (w != BUILT_UP)
    real_pixel, real_chm_pixel = tree | built, tree_chm | built
    count = lambda f: np.add.reduceat(f.astype(np.int64), starts) if len(f) else np.zeros(0, dtype=np.int64)  # noqa: E731
    real, real_chm = count(real_pixel) > 0, count(real_chm_pixel) > 0
    rock_only = count(~rock) == 0

    # The worst pixel of each line (raw) and the radius A needs
    order = np.lexsort((pix["margin"], pix["line"]))
    worst = order[starts] if len(order) else order
    nearest = np.minimum(pix["step"], pix["steps"] - pix["step"])[worst]
    slope = slope_grid[rows[worst], cols[worst]]
    height = s[rows[worst], cols[worst]] - z[rows[worst], cols[worst]]
    r_needed = 1 + sum(per_line[f"A{r}"].astype(np.int64) for r in RADII)

    inside = in_core(a1, a2, grid)[idx]
    line_of = pix["line"]

    def objects(chosen: np.ndarray) -> int:
        """Separate objects (8 neighbours) among the chosen pixels: lines of one spot share theirs."""
        if not chosen.any():
            return 0
        mask = np.zeros(z.shape, dtype=bool)
        mask[rows[chosen], cols[chosen]] = True
        return int(ndimage.label(mask, structure=np.ones((3, 3), dtype=bool))[1])

    classes = {"real": real & inside, "rock_only": rock_only & inside,
               "other": ~real & ~rock_only & inside}  # rock_only and real never meet
    result = {"checks": checks, "res": res, "lines": int(in_core(a1, a2, grid).sum()), "marked": int(inside.sum()),
              "classes": {**{k: int(v.sum()) for k, v in classes.items()}, "real_chm": int((real_chm & inside).sum()),
                          "real_objects": objects(real_pixel & inside[line_of]),
                          "rock_objects": objects(rock & (rock_only & inside)[line_of])},
              "rules": {},
              "r_needed": {k: np.bincount(r_needed[v], minlength=12)[1:].tolist() for k, v in classes.items()},
              "distance": {k: _bins(nearest[v], DISTANCES) for k, v in classes.items()},
              "slope": {k: _slope_bins(slope[v]) for k, v in classes.items()},
              "height_median": {k: float(np.nanmedian(height[v])) if v.any() else None for k, v in classes.items()},
              "proxies": {"chmv2": chm is not None, "worldcover": wc is not None}}
    for name, keep in per_line.items():
        f = flags[name]
        lost = ~keep & real & inside
        residual = keep & (count(f & ~rock) == 0) & inside
        result["rules"][name] = {"marked": int((keep & inside).sum()), "lost": int(lost.sum()),
                                 "lost_objects": objects(real_pixel & lost[line_of]),
                                 "lost_chm": int((~keep & real_chm & inside).sum()),
                                 "removed_rock": int((~keep & rock_only & inside).sum()),
                                 "residual_rock": int(residual.sum()),
                                 "residual_objects": objects(f & rock & residual[line_of]),
                                 "kept_real": int((keep & (count(f & real_pixel) > 0) & inside).sum())}
    if shift is not None:
        result["chm_shift"] = shift

    if chips is not None and len(idx):
        a1_kept, f1 = per_line[chip_rule], flags[chip_rule]
        groups = {"removed_rock": ~a1_kept & rock_only, "lost": ~a1_kept & real_chm,
                  "kept_real": a1_kept & (count(f1 & real_chm_pixel) > 0),
                  "residual_rock": a1_kept & (count(f1 & ~rock) == 0)}
        within = {"removed_rock": None, "lost": real_chm_pixel, "kept_real": f1 & real_chm_pixel,
                  "residual_rock": f1}  # the pixels a picture centres on: its worst one among these
        ends = np.append(starts[1:], len(pix["line"]))
        for group, members in groups.items():
            for k in np.flatnonzero(members & inside):
                segment = np.arange(starts[k], ends[k])
                if within[group] is not None:
                    segment = segment[within[group][segment]]
                focus = segment[np.argmin(pix["margin"][segment])]
                r, c = rows[focus], cols[focus]
                info = {"step": int(pix["step"][focus]), "height": float(s[r, c] - z[r, c]),
                        "slope": float(slope_grid[r, c]),
                        "chm": None if chm3 is None else float(chm3[r, c]),
                        "worldcover": None if wc is None or np.isnan(wc[r, c]) else int(wc[r, c])}
                chips.setdefault(group, []).append((call, int(idx[k]), info))
    return result


def merge(results: List[Dict]) -> Dict:
    """The sum of the calls' counts."""
    def add(a, b):
        if isinstance(a, dict):
            return {k: add(a.get(k), b.get(k)) for k in set(a) | set(b)}
        if isinstance(a, list):
            return [x + y for x, y in zip(a, b)]
        if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool):
            return a + b
        return a if a is not None else b
    total = None
    for r in results:
        r = {k: v for k, v in r.items() if k not in ("chm_shift", "height_median", "checks", "res", "proxies")}
        total = r if total is None else add(total, r)
    return total or {}


def place_name(folder: str) -> str:
    return os.path.basename(os.path.abspath(folder))


def source_of(folder: str) -> Optional[str]:
    log = os.path.join(folder, "output.log")
    if os.path.exists(log):
        with open(log, encoding="utf-8", errors="replace") as f:
            match = re.search(r"^Data: (.+) \([^()]*\) - ", f.read(), re.M)
            if match:
                return match.group(1)
    return None


def analyse(folder: str, samples: int = 6, outside: bool = True, chip_rule: str = "A1") -> Dict:
    """Analyse a captured place: <folder>/study.json, study.md and chips/ (the groups of chip_rule)."""
    calls = sorted(glob.glob(os.path.join(folder, "capture", "call-*")), key=lambda p: int(p.rsplit("-", 1)[1]))
    layers = None
    if outside:
        try:
            index = chm_index(os.path.dirname(os.path.abspath(folder)))
        except Exception as e:  # WorldCover alone still tells built-up and bare rock
            print(f"CHMv2's index not read ({cache.clean_error(e)}): without CHMv2", file=sys.stderr)
            index = None
        layers = outside_layers(index)
    results, candidates = [], {}
    for call in calls:
        part = analyse_call(call, layers, candidates, chip_rule)
        if part is not None:
            results.append(part)
    study = {"place": place_name(folder), "source": source_of(folder), "calls": len(calls),
             "res": results[0]["res"] if results else None, **merge(results),
             "checks": [r["checks"] for r in results],
             "chm_shift": [r.get("chm_shift") for r in results],
             "proxies": results[0]["proxies"] if results else None}
    picked = pictures(folder, candidates, samples, chip_rule) if results else {}
    study["chips"], study["chip_rule"] = picked, chip_rule
    with open(os.path.join(folder, "study.json"), "w", encoding="utf-8") as f:
        json.dump(study, f, indent=1, ensure_ascii=False)
    with open(os.path.join(folder, "study.md"), "w", encoding="utf-8") as f:
        f.write(place_markdown(study))
    return study


# ---------------------------------------------------------------------------------------------
# pictures

def pictures(folder: str, candidates: Dict, samples: int, rule: str = "A1") -> Dict:
    """Up to `samples` pictures per group, chosen at random (seed 0): chips-<rule>/<group>-<n>.png,
    drawn call by call (each call's grids loaded once)."""
    out = os.path.join(folder, chips_dir(rule))
    shutil.rmtree(out, ignore_errors=True)
    rng = np.random.default_rng(0)
    chosen = []
    for group in GROUPS:
        members = candidates.get(group, [])
        if members:
            for n, choice in enumerate(sorted(rng.choice(len(members), min(samples, len(members)), replace=False))):
                chosen.append((members[choice][0], group, n, *members[choice][1:]))
    picked, loaded = {}, None
    for call, group, n, line, info in sorted(chosen, key=lambda c: (c[0], list(GROUPS).index(c[1]), c[2])):
        if loaded is None or loaded.call != call:
            loaded = _load_for_picture(call)
        entry = draw(os.path.join(out, f"{group}-{n}.png"), place_name(folder), group, loaded, line, info, rule)
        picked.setdefault(group, []).append(entry)
    return {group: sorted(picked[group], key=lambda e: e["png"]) for group in GROUPS if group in picked}


def chips_dir(rule: str) -> str:
    return "chips-" + re.sub(r"[^A-Za-z0-9.-]", "_", rule)


def _load_for_picture(call: str) -> SimpleNamespace:
    import perf_line_funnel as plf
    inputs, params, _ = plf.load_call(call)
    with open(os.path.join(call, "grid.json")) as f:
        grid = json.load(f)
    with np.load(os.path.join(call, "lines.npz")) as data:
        lines = {k: data[k] for k in data.files}
    z = np.asarray(inputs["elevation"], dtype=np.float32)
    s = np.asarray(inputs["surface"], dtype=np.float32)
    res = float(params["res"])
    path = os.path.join(call, "chmv2.npy")  # kept by outside_layers
    chm = np.load(path) if os.path.exists(path) else None
    return SimpleNamespace(call=call, z=z, s=s, s1=obstacles.obstacle_surface(z, s, res),
                           chm=chm if chm is not None and chm.size else None, res=res, grid=grid,
                           table=saved_table(inputs, params), a1=lines["a1"], a2=lines["a2"])


def _to_wgs84(grid: Dict, rows, cols):
    from pyproj import Transformer
    x = grid["left"] + (np.asarray(cols) + 0.5) * grid["res"]
    y = grid["top"] - (np.asarray(rows) + 0.5) * grid["res"]
    lon, lat = Transformer.from_crs(grid["crs"], "EPSG:4326", always_xy=True).transform(x, y)
    return lat, lon


def draw(path: str, place: str, group: str, d: SimpleNamespace, line: int, info: Dict, rule: str = "A1") -> Dict:
    """A picture of one line around a pixel: the terrain shaded, the surface's height above it,
    CHMv2, and the profile there (terrain, surface, A1's obstacle surface, the limit)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import LightSource

    a1, a2 = d.a1[line].astype(np.int64), d.a2[line].astype(np.int64)
    dr, dc = int(a2[0] - a1[0]), int(a2[1] - a1[1])
    steps = max(abs(dr), abs(dc))
    t = np.arange(steps + 1) / steps
    rows = a1[0] + np.rint(dr * t).astype(np.intp)
    cols = a1[1] + np.rint(dc * t).astype(np.intp)
    length = float(np.hypot(dr, dc)) * d.res
    limit = sh.max_safe_elevation(t, length, float(d.z[a1[0], a1[1]]), float(d.z[a2[0], a2[1]]), d.table)
    focus = info["step"]
    fr, fc = rows[focus], cols[focus]
    h, w = d.z.shape
    r0, r1, c0, c1 = max(0, fr - WINDOW), min(h, fr + WINDOW + 1), max(0, fc - WINDOW), min(w, fc + WINDOW + 1)
    terrain = d.z[r0:r1, c0:c1]
    fig, axes = plt.subplots(1, 4, figsize=(15, 3.8))
    shade = LightSource(315, 45).hillshade(np.nan_to_num(terrain, nan=float(np.nanmin(terrain))), dx=d.res, dy=d.res)
    panels = [(shade, "terrain, shaded", "gray", 0, 1), (d.s[r0:r1, c0:c1] - terrain, "surface - terrain (m)",
                                                           "viridis", 0, 20),
              (None if d.chm is None else d.chm[r0:r1, c0:c1], "CHMv2 (m)", "viridis", 0, 20)]
    for ax, (image, title, cmap, low, high) in zip(axes[:3], panels):
        ax.set_xticks([])
        ax.set_yticks([])
        ax.set_title(title, fontsize=9)
        if image is None:
            ax.text(0.5, 0.5, "no CHMv2", ha="center", va="center", transform=ax.transAxes)
            continue
        ax.imshow(image, cmap=cmap, vmin=low, vmax=high, interpolation="nearest")
        ax.plot(cols - c0, rows - r0, color="red", lw=1)
        ax.plot([fc - c0], [fr - r0], "o", mfc="none", mec="cyan", ms=9, mew=2)
        ax.set_xlim(-0.5, c1 - c0 - 0.5)
        ax.set_ylim(r1 - r0 - 0.5, -0.5)
    k0, k1 = max(0, focus - WINDOW), min(steps, focus + WINDOW)
    span = slice(k0, k1 + 1)
    distance = t[span] * length
    ax = axes[3]
    ax.plot(distance, d.z[rows, cols][span], color="saddlebrown", label="terrain")
    ax.plot(distance, d.s[rows, cols][span], color="green", label="surface")
    ax.plot(distance, d.s1[rows, cols][span], color="orange", ls="--", label="obstacles (A1)")
    ax.plot(distance, limit[span], color="black", lw=1, label="limit")
    ax.axvline(t[focus] * length, color="cyan")
    ax.set_xlabel("m from anchor 1", fontsize=8)
    ax.legend(fontsize=7)
    lat, lon = _to_wgs84(d.grid, [a1[0], a2[0], fr], [a1[1], a2[1], fc])
    chm = "-" if info["chm"] is None else f"{info['chm']:.0f} m"
    fig.suptitle(f"{place}, {group}: {GROUPS[group].replace('A1', rule)}. Pixel {focus} of {steps} steps, surface {info['height']:.1f} m "
                 f"above the terrain, slope up to {info['slope']:.0f} deg, CHMv2 {chm}, WorldCover "
                 f"{'-' if info['worldcover'] is None else int(info['worldcover'])}", fontsize=9)
    fig.tight_layout()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fig.savefig(path, dpi=70)
    plt.close(fig)
    return {"png": os.path.basename(path), "anchor1": [round(float(lat[0]), 6), round(float(lon[0]), 6)],
            "anchor2": [round(float(lat[1]), 6), round(float(lon[1]), 6)],
            "pixel": [round(float(lat[2]), 6), round(float(lon[2]), 6)], **info}


# ---------------------------------------------------------------------------------------------
# report

def _pct(part, whole) -> str:
    return f"{part} ({100 * part / whole:.0f} %)" if whole else str(part)


def place_markdown(study: Dict) -> str:
    rules = study.get("rules", {})
    marked = study.get("marked", 0)
    lines = [f"# {study['place']}", "",
             f"{study.get('source') or 'source not found'}, {study.get('res')} m: {study.get('lines', 0)} lines, "
             f"{marked} over trees/buildings; by CHMv2 and WorldCover {study.get('classes', {})}; checks "
             f"{study.get('checks')}; CHMv2 shift {study.get('chm_shift')}.", "",
             "| rule | marked | lost (tree/building): lines, objects | lost (CHMv2 tree/building) | removed, rock only | "
             "kept, rock only: lines, objects | kept, tree/building |", "| --- | --- | --- | --- | --- | --- | --- |"]
    for name in rule_names():
        r = rules.get(name)
        if r:
            lines.append(f"| {name} | {_pct(r['marked'], marked)} | {r['lost']}, {r['lost_objects']} | {r['lost_chm']} | "
                         f"{r['removed_rock']} | {r['residual_rock']}, {r['residual_objects']} | {r['kept_real']} |")
    lines += ["", "r needed by A (1..10, 11: more):", ""]
    for k, v in study.get("r_needed", {}).items():
        lines.append(f"- {k}: {v}")
    lines += ["", f"Steps of the worst pixel from the nearer anchor {[f'{a}-{b}' for a, b in DISTANCES]}:", ""]
    for k, v in study.get("distance", {}).items():
        lines.append(f"- {k}: {v}")
    lines += ["", f"Slope there {[f'{a}-{b}' for a, b in SLOPES]}:", ""]
    for k, v in study.get("slope", {}).items():
        lines.append(f"- {k}: {v}")
    for group, entries in study.get("chips", {}).items():
        lines += ["", f"## {GROUPS[group].replace('A1', study.get('chip_rule') or 'A1')}", ""]
        for e in entries:
            lat, lon = e["pixel"]
            lines.append(f"- [{e['png']}]({chips_dir(study.get('chip_rule') or 'A1')}/{e['png']}): pixel {lat}, {lon} "
                         f"([satellite](https://www.google.com/maps/@{lat},{lon},19z/data=!3m1!1e3)), anchors "
                         f"{e['anchor1']} - {e['anchor2']}")
    return "\n".join(lines) + "\n"


def report(out: str) -> str:
    """<out>/study.md: the places side by side and the sums over them."""
    studies = []
    for path in sorted(glob.glob(os.path.join(out, "*", "study.json"))):
        with open(path, encoding="utf-8") as f:
            studies.append(json.load(f))
    head = ["place", "source", "res", "lines", "ideal"] + list(REPORT_RULES)
    rows = ["| " + " | ".join(head) + " |", "|" + " --- |" * len(head)]
    total = {}
    for st in studies:
        rules = st.get("rules", {})
        if not rules:
            rows.append("| " + " | ".join([st["place"], st.get("source") or "", f"{st.get('res')}",
                                           str(st.get("lines")), "-"] + ["-"] * len(REPORT_RULES)) + " |")
            continue
        ideal = st.get("classes", {}).get("real", 0)
        cells = [st["place"], st.get("source") or "", f"{st.get('res')}", str(st.get("lines")), str(ideal)]
        cells += [str(rules[r]["marked"]) if r in rules else "-" for r in REPORT_RULES]
        rows.append("| " + " | ".join(cells) + " |")
        for name, r in rules.items():
            t = total.setdefault(name, {k: 0 for k in r})
            for k, v in r.items():
                t[k] += v
    marked = sum(st.get("marked", 0) for st in studies)
    real = sum(st.get("classes", {}).get("real", 0) for st in studies)
    real_chm = sum(st.get("classes", {}).get("real_chm", 0) for st in studies)
    rock = sum(st.get("classes", {}).get("rock_only", 0) for st in studies)
    sums = ["| rule | marked | lost (tree/building): lines, objects | lost (CHMv2 tree/building) | removed, rock only | "
            "kept, rock only: lines, objects | kept, tree/building |", "| --- | --- | --- | --- | --- | --- | --- |"]
    for name in rule_names():
        t = total.get(name)
        if t:
            sums.append(f"| {name} | {_pct(t['marked'], marked)} | {_pct(t['lost'], real)}, {t['lost_objects']} | "
                        f"{_pct(t['lost_chm'], real_chm)} | {_pct(t['removed_rock'], rock)} | "
                        f"{t['residual_rock']}, {t['residual_objects']} | {t['kept_real']} |")
    shifts = [f"- {st['place']}: {st.get('chm_shift')}" for st in studies]
    checks = [st["place"] for st in studies if any(not c.get("raw_equal", True) or not c.get("a1_equal", True)
                                                   or c.get("marked_without_pixels") for c in st.get("checks", []))]
    text = "\n".join([
        "# Obstacles on rock: the rules side by side", "",
        "Lines over trees/buildings per place under each rule (tools/obstacle_study.py); ideal: the lines with a "
        "tree (CHMv2 >= 3 m within a pixel where WorldCover has tree cover and the lidar's surface stands 3 m "
        "above its terrain) or a building (WorldCover) among the pixels above their limit; objects: separate "
        "groups of such pixels (the lines of one spot share theirs).", "",
        *rows, "",
        f"## Over all places ({marked} lines over trees/buildings: {real} with a tree (CHMv2 and WorldCover) or "
        f"building, {real_chm} with a tree by CHMv2 alone or a building, {rock} rock only)",
        "", *sums, "",
        "## CHMv2 against the surface's height above the terrain (gentle ground)", "", *shifts, "",
        "## Checks", "", "Places where a check failed: " + (", ".join(checks) if checks else "none"), ""])
    with open(os.path.join(out, "study.md"), "w", encoding="utf-8") as f:
        f.write(text)
    return text


# ---------------------------------------------------------------------------------------------

def _unlink(path: str):
    """Remove a directory link (a junction on Windows, a symlink elsewhere) without its target."""
    if os.path.islink(path):
        os.unlink(path)
    elif os.path.isjunction(path):
        os.rmdir(path)  # removes the junction, not what it points to


def run(args) -> int:
    import regression

    out = os.path.abspath(args.out)
    os.makedirs(out, exist_ok=True)
    tests = regression.load()
    places = [(test_id, regression.full_args(tests, test_id)) for test_id in args.ids]
    for spec in args.place:
        name, _, options = spec.partition("=")
        places.append((name, shlex.split(options)))
    cache_dir = os.path.abspath(args.cache or os.path.join(cache.data_dir(), "cache"))
    env = {**os.environ, "FINDALINE_PROGRESS": "text", "PYTHONIOENCODING": "utf-8"}
    for name, options in places:
        folder = os.path.join(out, name)
        if args.again or not glob.glob(os.path.join(folder, "capture", "call-*", "lines.npz")):
            _unlink(os.path.join(folder, "data", "cache"))  # the link only, never the real cache behind it
            shutil.rmtree(folder, ignore_errors=True)
            data = os.path.join(folder, "data")
            os.makedirs(data)
            regression.link(cache_dir, os.path.join(data, "cache"))
            print(f"{name}: searching", flush=True)
            with open(os.path.join(folder, "output.log"), "w", encoding="utf-8") as log:
                subprocess.run([sys.executable, os.path.abspath(__file__), "capture", "--out",
                                os.path.join(folder, "capture"), "--", *options, "--data-dir", data],
                               cwd=HERE, env=env, stdout=log, stderr=subprocess.STDOUT)
        print(f"{name}: analysing", flush=True)
        subprocess.run([sys.executable, os.path.abspath(__file__), "analyse", folder, "--samples", str(args.samples),
                        "--chips-rule", args.chips_rule] + ([] if args.outside else ["--offline"]), cwd=HERE, env=env)
    print(report(out))
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("run", help="search, analyse and report places")
    p.add_argument("ids", nargs="*", help="regression tests (tests/regression.json)")
    p.add_argument("--place", action="append", default=[], help="NAME=OPTIONS of findaline.py")
    p.add_argument("--out", required=True)
    p.add_argument("--cache", help="the cache to link (default: the data folder's)")
    p.add_argument("--again", action="store_true", help="search places captured already again")
    p.add_argument("--samples", type=int, default=6, help="pictures per group and place")
    p.add_argument("--offline", dest="outside", action="store_false", help="without CHMv2 and WorldCover")
    p.add_argument("--chips-rule", default="A1", help="the rule whose groups the pictures show")
    p = sub.add_parser("capture", help="(child) one search with find_valid_lines captured")
    p.add_argument("--out", required=True)
    p.add_argument("search_args", nargs=argparse.REMAINDER)
    p = sub.add_parser("analyse", help="analyse a captured place")
    p.add_argument("folder")
    p.add_argument("--samples", type=int, default=6)
    p.add_argument("--offline", dest="outside", action="store_false")
    p.add_argument("--chips-rule", default="A1")
    p = sub.add_parser("report", help="the report of the analysed places")
    p.add_argument("out")
    args = parser.parse_args(argv)
    if args.command == "run":
        return run(args)
    if args.command == "capture":
        search_args = args.search_args[1:] if args.search_args[:1] == ["--"] else args.search_args
        return capture(args.out, search_args)
    if args.command == "analyse":
        analyse(args.folder, args.samples, args.outside, args.chips_rule)
        return 0
    print(report(args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
