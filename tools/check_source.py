"""
The data checks of a new source (or download path) as one command (run by hand; docs/regression-tests.md,
"Data checks for a new source or download path").

    uv run tools/check_source.py SOURCE --lat LAT --lon LON [--radius 1500] [--resolution 10]
        [--layers nmt,nmpt] [--reference auto|fabdem|copernicus|FILE] [--shift-range 200]
        [--shift-step M] [--samples 3] [--data-dir DIR] [--elevation-file F --surface-file F] [--json OUT]

For each layer of the source (terrain: nmt, surface: nmpt), on a grid built as a search builds
it (search.plan_search without margin, water and gap filling), downloading through the
layer's own path into the cache of --data-dir:

1. shift: the layer mosaicked over the grid enlarged by --shift-range, compared with a
   reference on the grid (auto: the terrain with FABDEM, the surface with Copernicus GLO-30;
   or a raster file) at whole-pixel shifts; the best shift is the correction to add to the
   layer's `shift` (data placed 56 m east needs -56). WARN if it is more than 30 m away.
2. valid: the share of pixels with data inside the circle (at most 500 m) at 1 m and at 5 m;
   WARN if 5 m is more than 1 percentage point below 1 m (a server that loses data when it
   downsamples).
3. files: --samples cached tiles against their source files read through GDAL (/vsicurl/,
   /vsizip/): the largest difference, the share of equal values, the same pixels without
   data (blocks: against the newest file with data there). n/a for WCS tiles and local files.
4. alignment: the cached tiles' pixel edges against Source.grid_origin, their pixel size and CRS.
5. precision: the share of whole-metre and whole-centimetre heights; WARN above 90% whole metres.
6. missing: tiles the service had no data for (normal over the sea; on land a lost tile).

Each check is PASS, WARN, FAIL or n/a; the exit code is 1 when one FAILs. --json writes the
numbers. The tool writes only into the cache of --data-dir (use a scratch folder for a new
source) and a work folder there, deleted at the end.
"""

import argparse
import gc
import json
import math
import os
import sys
from typing import Dict, List, Optional, Tuple

import numpy as np
import rasterio as rio
import rasterio.cache
from rasterio.enums import Resampling
from rasterio.vrt import WarpedVRT

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

import area as ar  # noqa: E402
import cache  # noqa: E402
import search  # noqa: E402
import sources as src  # noqa: E402
from params import SearchParams  # noqa: E402
from progress import progress  # noqa: E402

PASS, WARN, FAIL, NA = "PASS", "WARN", "FAIL", "n/a"
SHIFT_WARN_M = 30          # a best shift further than this from (0, 0) is a warning
VALID_RADIUS_MAX = 500     # the circle of the valid shares at 1 and 5 m
VALID_DROP_PP = 1.0        # 5 m may lose this many percentage points against 1 m
WHOLE_METRES_WARN = 0.9    # share of whole-metre heights above which the precision is a warning
EQUAL_M = 0.01             # a cached tile and its source file differ by at most this
ALIGN_TILES = 20           # cached tiles looked at for the alignment and the precision
LAYER_NAMES = {"nmt": "terrain", "nmpt": "surface"}


# --- metrics (pure functions, unit-tested) ---

def shift_table(raw: np.ndarray, reference: np.ndarray, margin_px: int, step_px: int = 1,
                mask: Optional[np.ndarray] = None) -> Dict[Tuple[int, int], Tuple[float, float, int]]:
    """Medians of |d| and d (d = layer - reference) over the inner window for every correction
    (i, j) in pixels (east, north) within margin_px, in steps of step_px: the layer corrected by
    (i, j) has at [r, c] the raw value at [r + j, c - i]. raw and reference are on the same
    grid; the inner window leaves margin_px on every side; mask (of the inner window) limits
    the pixels compared. Corrections without common pixels are left out."""
    h, w = reference.shape
    inner = reference[margin_px:h - margin_px, margin_px:w - margin_px]
    keep = np.isfinite(inner) if mask is None else np.isfinite(inner) & mask
    table = {}
    for j in range(-margin_px, margin_px + 1, step_px):
        for i in range(-margin_px, margin_px + 1, step_px):
            moved = raw[margin_px + j:h - margin_px + j, margin_px - i:w - margin_px - i]
            both = keep & np.isfinite(moved)
            if both.any():
                d = moved[both].astype(np.float64) - inner[both]
                table[(i, j)] = (float(np.median(np.abs(d))), float(np.median(d)), int(both.sum()))
    return table


def best_shift(table: Dict[Tuple[int, int], Tuple[float, float, int]]) -> Tuple[int, int]:
    """The correction with the smallest median |d| (the nearest to (0, 0) among equals)."""
    return min(table, key=lambda k: (round(table[k][0], 6), k[0] ** 2 + k[1] ** 2, k))


def valid_share(values: np.ndarray, mask: np.ndarray) -> float:
    """The share of the masked pixels that have data."""
    return float(np.isfinite(values[mask]).mean()) if mask.any() else 0.0


def precision(values: np.ndarray) -> Tuple[float, float]:
    """(whole metres, whole centimetres): the shares of the heights with data that are such."""
    v = values[np.isfinite(values)].astype(np.float64)
    if not v.size:
        return 0.0, 0.0
    return (float((np.abs(v - np.round(v)) < 1e-4).mean()),
            float((np.abs(v * 100 - np.round(v * 100)) < 1e-2).mean()))


def compare(tile: np.ndarray, source: np.ndarray, source_only: bool = False) -> Dict:
    """A cached tile against its source on the same pixels: the largest |difference|, the
    share of equal values (where both have data) and of pixels where both agree on having
    data; source_only: only where the source has data (a block composed from several files)."""
    both = np.isfinite(tile) & np.isfinite(source)
    d = np.abs(tile[both].astype(np.float64) - source[both]) if both.any() else np.zeros(0)
    where = np.isfinite(source) if source_only else np.ones(tile.shape, bool)
    same = (np.isfinite(tile) == np.isfinite(source))[where]
    return {"pixels": int(both.sum()), "max_abs_m": float(d.max()) if d.size else None,
            "equal": float((d == 0).mean()) if d.size else None,
            "same_nodata": float(same.mean()) if same.size else None}


def origin_offset(transform, res: float, origin: Tuple[float, float]) -> float:
    """How far (metres, at most res / 2) the pixel edges of a raster are from origin modulo res."""
    worst = 0.0
    for value, o in ((transform.c, origin[0]), (transform.f, origin[1])):
        off = (value - o) % res
        worst = max(worst, min(off, res - off))
    return worst


# --- helpers ---

class Check(dict):
    def __init__(self, name: str, status: str, text: str, **values):
        super().__init__(name=name, status=status, text=text, **values)


def _quiet(kind: str, text: str):
    if kind == "warning":
        print(f"Warning: {text}")


def _plan(args, data: str, work: str, radius: float, resolution: float):
    params = SearchParams(lat=args.lat, lon=args.lon, radius=radius, resolution=resolution, source=args.source,
                          elevation_file=args.elevation_file, surface_file=args.surface_file, water="off",
                          fill_gaps="off", ortho="never", no_html=True)
    return search.plan_search(params, search.Paths(data, work), _quiet, with_margin=False)


def _mosaic(layer: src.Layer, grid, cache_dir: str, work: str, name: str) -> np.ndarray:
    path = src.prepare_layer(layer, grid, cache_dir, os.path.join(work, f"{name}.npy"), name)
    values = np.load(path)  # into memory: the work folder is deleted at the end (Windows)
    gc.collect()
    return values


def _reference(args, kind: str) -> src.Layer:
    choice = args.reference
    if choice == "auto":
        choice = "fabdem" if kind == "nmt" else "copernicus"
    if choice == "fabdem":
        return src.SOURCES["europe"].nmt
    if choice == "copernicus":
        return src.SOURCES["europe"].nmpt
    return src.FileLayer("Reference file", choice)


def _cached_tiles(layer: src.Layer, grid, cache_dir: str) -> List:
    tiles = layer.tiles(grid) or []
    return [t for t in tiles if cache.state(cache_dir, layer.tile_path(cache_dir, t), layer.processing) == "ok"]


def _spread(items: List, n: int) -> List:
    """n items spread over the list (all when there are fewer)."""
    if len(items) <= n:
        return list(items)
    return [items[k * len(items) // n] for k in range(n)]


def _gdal_path(url: str) -> str:
    path = f"/vsicurl/{url}" if url.startswith(("http://", "https://")) else url
    return f"/vsizip/{path}" if url.lower().endswith(".zip") else path


def _read_source(url: str, profile: Dict) -> np.ndarray:
    """A source file's values on the pixels of a cached tile (nearest: the same pixels when the
    tile is on the file's own grid), NaN without data. A read GDAL could not complete although it
    returned (src.net.gdal_errors: what it could not fetch comes back as nodata or zeros) raises
    RuntimeError with GDAL's error, never a false difference. GDAL's settings as
    src.net._gdal_http's (retries of requests without an answer, the blocks read in this thread)
    but for the extensions: the sources here include zips and ASCII grids."""
    env = rio.Env(GDAL_HTTP_USERAGENT=cache.http_headers()["User-Agent"], GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
                  GDAL_HTTP_TIMEOUT="120", GDAL_HTTP_MAX_RETRY="3", GDAL_HTTP_RETRY_DELAY="2",
                  GDAL_HTTP_RETRY_CODES=src.net.GDAL_RETRY_CODES, GDAL_NUM_THREADS="1")
    src.net.rate_turn(url)  # the file's read counts as one request where its host has a rate (net.HOST_RATES_OF)
    try:
        with env, src.net.gdal_errors() as errors, rio.open(_gdal_path(url)) as source:
            kwargs = {} if source.crs else {"src_crs": profile["crs"]}  # ASCII grids name no CRS
            with WarpedVRT(source, crs=profile["crs"], transform=profile["transform"], width=profile["width"],
                           height=profile["height"], resampling=Resampling.nearest, **kwargs) as vrt:
                values = vrt.read(1, masked=True).astype(np.float32).filled(np.nan)
        if errors:
            raise RuntimeError("not read completely: " + "; ".join(dict.fromkeys(errors)))
    except (RuntimeError, rio.errors.RasterioError):
        if url.startswith(("http://", "https://")):
            rio.cache.invalidate(url)  # not the short answer again from GDAL's cache
        raise
    values[values < -500] = np.nan  # as the layers clean their tiles (sources.layer.VALID_MIN)
    return values


def _sources_of(layer: src.Layer, tile) -> Optional[List[str]]:
    """The files a cached tile comes from, newest first; None: no file to compare with."""
    if isinstance(layer, (src.WcsTiles, src.FileLayer, src.OpenTopographyTiles)):
        return None  # a service's answer, a local file, or the API's limited calls
    if isinstance(layer, src.TnmBlocks):
        return [url for _, url, _ in tile.files]
    if isinstance(layer, src.GridTiles):
        base = layer.tile_url(tile)
        return [f"{base}/{src.grid_tile_name(*tile)}"] if base else None
    url = layer.tile_url(tile)
    return [url] if url else None


# --- the checks ---

def check_shift(layer, reference, args, data, work, cache_dir) -> Check:
    plan = _plan(args, data, work, args.radius + args.shift_range, args.resolution)
    grid, res = plan.grid, plan.resolution
    margin = math.ceil(args.shift_range / res - 1e-9)
    step = max(1, round((args.shift_step or res) / res))
    raw = _mosaic(layer, grid, cache_dir, work, "layer")
    ref = _mosaic(reference, grid, cache_dir, work, "reference")
    mask = ar.Circle(args.lat, args.lon, args.radius).mask(grid)
    mask = mask[margin:grid.height - margin, margin:grid.width - margin]
    table = shift_table(raw, ref, margin, step, mask)
    if (0, 0) not in table:
        return Check("shift", FAIL, f"no pixels with data in both the layer and {reference.description}")
    i, j = best_shift(table)
    best, zero = table[(i, j)], table[(0, 0)]
    shift = (i * res, j * res)
    total = (layer.shift[0] + shift[0], layer.shift[1] + shift[1])
    status = WARN if math.hypot(*shift) > SHIFT_WARN_M else PASS
    text = (f"best ({shift[0]:g}, {shift[1]:g}) m against {reference.description}: median |d| {best[0]:.2f} m, "
            f"median d {best[1]:+.2f} m; at (0, 0): {zero[0]:.2f} m, {zero[1]:+.2f} m")
    if shift != (0, 0):
        text += f"; correction: shift=({total[0]:g}, {total[1]:g})"
    return Check("shift", status, text, best_m=list(shift), shift=list(total), reference=reference.description,
                 median_abs_m=best[0], median_m=best[1], zero_median_abs_m=zero[0], zero_median_m=zero[1],
                 pixels=best[2], grid_m=res, range_m=margin * res)


def check_valid(layer, args, data, work, cache_dir) -> Check:
    radius = min(args.radius, VALID_RADIUS_MAX)
    shares, notes = {}, []
    for res in (1.0, 5.0):
        try:
            plan = _plan(args, data, work, radius, res)
        except search.SearchError as e:  # a WCS that serves no finer grid than its own
            notes.append(f"{res:g} m: {e}")
            continue
        values = _mosaic(layer, plan.grid, cache_dir, work, f"valid-{res:g}")
        shares[res] = valid_share(values, plan.area.mask(plan.grid))
    if not shares:
        return Check("valid", NA, "; ".join(notes))
    text = ", ".join(f"{100 * share:.2f}% at {res:g} m" for res, share in shares.items()) + f" (radius {radius:g} m)"
    status = PASS
    if not any(shares.values()):
        status = FAIL
    elif 1.0 in shares and 5.0 in shares and 100 * (shares[1.0] - shares[5.0]) > VALID_DROP_PP:
        status = WARN
        text += ": less data at 5 m"
    if notes:
        text += "; " + "; ".join(notes)
    return Check("valid", status, text, **{f"valid_{res:g}m": share for res, share in shares.items()})


def check_files(layer, grid, cache_dir, samples: int) -> Check:
    if isinstance(layer, src.FileLayer):  # not in the cache (it may lie on another drive): nothing to compare
        return Check("files", NA, "a local file")
    tiles = _cached_tiles(layer, grid, cache_dir)
    if not tiles or _sources_of(layer, tiles[0]) is None:
        why = "no cached tiles" if not tiles else f"{type(layer).__name__}: no source file to compare with"
        return Check("files", NA, why)
    results, problems = [], []
    for tile in _spread(tiles, samples):
        path = layer.tile_path(cache_dir, tile)
        with rio.open(path) as cached:
            values = cached.read(1, masked=True).astype(np.float32).filled(np.nan)
            profile = {"crs": cached.crs, "transform": cached.transform, "width": cached.width,
                       "height": cached.height}
        name = cache.relative(cache_dir, path)
        blocks = isinstance(layer, src.TnmBlocks)
        result = None
        for url in _sources_of(layer, tile):
            try:
                source = _read_source(url, profile)
            except (rio.errors.RasterioIOError, RuntimeError) as e:
                problems.append(f"{name}: {cache.clean_error(e)}")
                break
            if blocks and not np.isfinite(source).any():
                continue  # the newest file with data there
            result = {"tile": name, "file": cache.clean_url(url), **compare(values, source, source_only=blocks)}
            break
        if result:
            results.append(result)
    if not results:
        return Check("files", WARN, "could not read the source files: " + "; ".join(problems), problems=problems)
    worst = max((r["max_abs_m"] or 0.0) for r in results)
    same = min((r["same_nodata"] if r["same_nodata"] is not None else 1.0) for r in results)
    equal = min((r["equal"] if r["equal"] is not None else 1.0) for r in results)
    status = PASS if worst <= EQUAL_M and same >= 0.999 and not problems else WARN
    text = (f"{len(results)} tiles against their files: max |d| {worst:.4f} m, equal {100 * equal:.2f}%, "
            f"same pixels without data {100 * same:.2f}%")
    if problems:
        text += "; " + "; ".join(problems)
    return Check("files", status, text, tiles=results, problems=problems)


def _layer_rasters(layer, grid, cache_dir) -> List[str]:
    if isinstance(layer, src.FileLayer):
        return layer.files(grid, cache_dir)
    return [layer.tile_path(cache_dir, t) for t in _spread(_cached_tiles(layer, grid, cache_dir), ALIGN_TILES)]


def check_alignment(layer, source, plan, cache_dir) -> Check:
    paths = _layer_rasters(layer, plan.grid, cache_dir)
    if not paths:
        return Check("alignment", NA, "no cached tiles")
    working = rio.crs.CRS.from_user_input(plan.crs)
    worst, sizes, crss, other = 0.0, set(), set(), False
    for path in paths:
        with rio.open(path) as raster:
            res = abs(raster.res[0])
            sizes.add(round(res, 6))
            crss.add(raster.crs.to_string() if raster.crs else "none")
            if raster.crs is not None and raster.crs == working:
                worst = max(worst, origin_offset(raster.transform, res, source.grid_origin))
            else:
                other = True
    size_text = ", ".join(f"{s:g}" for s in sorted(sizes))
    text = (f"{len(paths)} rasters in {', '.join(sorted(crss))} (working grid {plan.crs}), pixels {size_text} "
            f"(native_res {layer.native_res:g}), edges {worst:.3f} m from grid_origin "
            f"({source.grid_origin[0]:g}, {source.grid_origin[1]:g})")
    if other:
        text += "; some in another CRS: reprojected onto the grid"
    status = WARN if worst > min(sizes) / 100 else PASS
    return Check("alignment", status, text, crs=sorted(crss), pixel_sizes=sorted(sizes), edge_offset_m=worst,
                 grid_origin=list(source.grid_origin), native_res=layer.native_res)


def check_precision(layer, grid, cache_dir) -> Check:
    paths = _layer_rasters(layer, grid, cache_dir)
    if not paths:
        return Check("precision", NA, "no cached tiles")
    values = []
    for path in paths[:5]:
        with rio.open(path) as raster:
            band = raster.read(1, masked=True).astype(np.float32).filled(np.nan)
        values.append(band[np.isfinite(band)][:2_000_000])
    metres, cm = precision(np.concatenate(values))
    status = WARN if metres > WHOLE_METRES_WARN else PASS
    text = f"whole metres {100 * metres:.1f}%, whole centimetres {100 * cm:.1f}%"
    if status == WARN:
        text += ": heights in whole metres make slopes and clearances coarser"
    return Check("precision", status, text, whole_metres=metres, whole_cm=cm)


def check_missing(layer, grid, cache_dir) -> Check:
    if isinstance(layer, src.FileLayer):
        return Check("missing", NA, "a local file")
    tiles = layer.tiles(grid)
    if tiles is None:
        return Check("missing", NA, "the index could not be reached")
    empty = [cache.relative(cache_dir, layer.tile_path(cache_dir, t)) for t in tiles
             if cache.state(cache_dir, layer.tile_path(cache_dir, t), layer.processing) == "missing"]
    text = f"{len(empty)} of {len(tiles)} tiles without data"
    if empty:
        text += " (normal over the sea; on land a lost tile): " + ", ".join(empty[:5])
    return Check("missing", WARN if empty else PASS, text, tiles=len(tiles), missing=empty)


def check_layer(kind: str, args, data: str, work: str) -> Dict:
    cache_dir = os.path.join(data, "cache")
    plan = _plan(args, data, work, args.radius + args.shift_range, args.resolution)
    source = plan.source
    layer = getattr(source, kind)
    checks = []

    def run(name, fn, *a):
        try:
            checks.append(fn(*a))
        except (RuntimeError, ValueError, OSError, search.SearchError) as e:
            checks.append(Check(name, FAIL, cache.clean_error(e)))

    run("shift", check_shift, layer, _reference(args, kind), args, data, work, cache_dir)
    run("valid", check_valid, layer, args, data, work, cache_dir)
    run("files", check_files, layer, plan.grid, cache_dir, args.samples)
    run("alignment", check_alignment, layer, source, plan, cache_dir)
    run("precision", check_precision, layer, plan.grid, cache_dir)
    run("missing", check_missing, layer, plan.grid, cache_dir)
    return {"layer": kind, "description": layer.description, "checks": checks}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().split("\n\n")[0])
    parser.add_argument("source", help="the source's id (sources/catalogue/), or files with --elevation-file")
    parser.add_argument("--lat", type=float, required=True)
    parser.add_argument("--lon", type=float, required=True)
    parser.add_argument("--radius", type=float, default=1500, help="metres (default 1500)")
    parser.add_argument("--resolution", type=float, default=10, help="grid of the shift search, m (default 10)")
    parser.add_argument("--layers", default="nmt,nmpt", help="nmt, nmpt or both (default: the source's)")
    parser.add_argument("--reference", default="auto",
                        help="auto (terrain: fabdem, surface: copernicus), fabdem, copernicus or a raster file")
    parser.add_argument("--shift-range", type=float, default=200, help="largest shift tried, m (default 200)")
    parser.add_argument("--shift-step", type=float, help="step of the shifts, m (default: the resolution)")
    parser.add_argument("--samples", type=int, default=3, help="cached tiles compared with their files")
    parser.add_argument("--data-dir", help="data folder whose cache is used (a scratch folder for a new source)")
    parser.add_argument("--elevation-file", help="with SOURCE files: the terrain raster")
    parser.add_argument("--surface-file", help="with SOURCE files: the surface raster")
    parser.add_argument("--json", help="write the results to this file")
    args = parser.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):  # names of the data on a Windows console
        stream.reconfigure(errors="replace")

    data = cache.data_dir(args.data_dir)
    work = cache.new_work(data)
    results = []
    try:
        with progress.bars():
            plan = _plan(args, data, work, args.radius + args.shift_range, args.resolution)
            source = plan.source
            kinds = [k for k in args.layers.split(",") if getattr(source, k.strip(), None) is not None]
            for kind in kinds:
                results.append(check_layer(kind.strip(), args, data, work))
    finally:
        gc.collect()
        cache.remove_work(work)

    print(f"\n{source.id}: {source.name} at {args.lat:g}, {args.lon:g}; radius {args.radius:g} m, "
          f"{plan.resolution:g} m grid in {plan.crs}")
    counts = {PASS: 0, WARN: 0, FAIL: 0, NA: 0}
    for result in results:
        print(f"{LAYER_NAMES.get(result['layer'], result['layer']).capitalize()}: {result['description']}")
        for check in result["checks"]:
            counts[check["status"]] += 1
            print(f"  {check['status']:<4}  {check['name']:<9}  {check['text']}")
    print(", ".join(f"{n} {status}" for status, n in counts.items()))
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump({"source": source.id, "lat": args.lat, "lon": args.lon, "radius": args.radius,
                       "resolution": plan.resolution, "crs": plan.crs, "layers": results}, f, indent=1)
    return 1 if counts[FAIL] else 0


if __name__ == "__main__":
    sys.exit(main())
