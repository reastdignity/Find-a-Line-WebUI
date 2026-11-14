"""
Helpers shared by the study tools that run a search on a place and look at its grid afterwards.

Moved from tools/end_zone_study.py (2026-11-08, the truth check), unchanged in behaviour and
imported there again under the same names: _unlink, to_pixel, pixels_wgs84, disc, slope_degrees,
margins, profile_chip. New: linked_data_folder (the data folder whose cache/ links to the real
cache, as end_zone_study.capture and obstacle_study.run make it) and grid_namespace (the object
end_zone_study.diagnose_line and line_detail read, from a capture's grid.json and arrays instead of
a captured call of find_valid_lines). Used by tools/end_zone_study.py and the truth check's
tools/truth_study.py and tools/truth_analysis.py.

A capture's grid is the dict of its grid.json: "crs", "left", "top" (the grid's upper left corner
in the CRS's metres), "res" and whatever else the tool writing it records (the truth check's
"slope_threshold", "nmpt", "fall", ...). Pixels are (row, col) of that grid.
"""

import contextlib
import functools
import math
import os
import sys
from types import SimpleNamespace
from typing import Dict, Iterator, List, Optional

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "tools"))
sys.path.insert(0, os.path.join(HERE, "tests"))

import numpy as np  # noqa: E402

import helpers as sh  # noqa: E402


# ---------------------------------------------------------------------------------------------
# the data folder of a place

def _unlink(path: str):
    """Remove a directory link (a junction on Windows, a symlink elsewhere), never its target."""
    if os.path.islink(path):
        os.unlink(path)
    elif hasattr(os.path, "isjunction") and os.path.isjunction(path):
        os.rmdir(path)  # the junction only


@contextlib.contextmanager
def linked_data_folder(folder: str, cache_dir: Optional[str]) -> Iterator[str]:
    """<folder>/data as a search's data folder (made when missing), its cache/ a link to cache_dir
    (tests/regression.link: a junction on Windows, a symlink elsewhere); yields the data folder's
    absolute path. On leaving, also after an error, only the link is removed, never the cache behind
    it; the data folder stays. A link left by a run that was killed is replaced; a real folder at
    data/cache stops it (FileExistsError: a cache of its own, never deleted here). cache_dir None: a
    plain data folder, nothing linked (the search makes a fresh cache in it)."""
    data = os.path.join(os.path.abspath(folder), "data")
    link = os.path.join(data, "cache")
    os.makedirs(data, exist_ok=True)
    _unlink(link)  # a stale link only, never the cache behind it
    if cache_dir:
        import regression
        regression.link(os.path.abspath(cache_dir), link)
    try:
        yield data
    finally:
        if cache_dir:
            _unlink(link)


# ---------------------------------------------------------------------------------------------
# pixels of a capture's grid

@functools.lru_cache(maxsize=16)
def _transformer(source: str, target: str):
    """pyproj's Transformer from source to target (x, y order), made once per pair."""
    from pyproj import Transformer
    return Transformer.from_crs(source, target, always_xy=True)


def to_pixel(grid: Dict, lat: float, lon: float):
    """The pixel (row, col) of a WGS84 point on a capture's grid: the pixel whose centre is nearest."""
    x, y = _transformer("EPSG:4326", grid["crs"]).transform(lon, lat)
    col, row = (x - grid["left"]) / grid["res"] - 0.5, (grid["top"] - y) / grid["res"] - 0.5
    return int(round(row)), int(round(col))


def pixels_wgs84(grid: Dict, pixels) -> List[List[float]]:
    """[lat, lon] of pixel centres of a capture's grid, rounded to 7 decimals."""
    t = _transformer(grid["crs"], "EPSG:4326")
    out = []
    for r, c in pixels:
        lon, lat = t.transform(grid["left"] + (int(c) + 0.5) * grid["res"], grid["top"] - (int(r) + 0.5) * grid["res"])
        out.append([round(lat, 7), round(lon, 7)])
    return out


def disc(z: np.ndarray, centre, radius_px: float) -> np.ndarray:
    """The pixels within radius_px of centre, inside the grid z."""
    r0, c0 = centre
    k = int(math.floor(radius_px))
    rr, cc = np.mgrid[r0 - k:r0 + k + 1, c0 - k:c0 + k + 1]
    rr, cc = rr.ravel(), cc.ravel()
    inside = ((rr - r0) ** 2 + (cc - c0) ** 2 <= radius_px ** 2) & (rr >= 0) & (cc >= 0) & \
             (rr < z.shape[0]) & (cc < z.shape[1])
    return np.column_stack([rr[inside], cc[inside]])


def slope_degrees(z: np.ndarray, res: float) -> np.ndarray:
    """The slope of helpers.find_significant_slopes (float32, np.gradient)."""
    gy, gx = np.gradient(np.asarray(z, dtype=np.float32), res)
    return np.degrees(np.arctan(np.hypot(gx, gy)))


# ---------------------------------------------------------------------------------------------
# the margins of a line

def margins(z: np.ndarray, p, q, res: float, sag_table, surface: Optional[np.ndarray] = None):
    """The strict margins of the line p -> q (pixels, p the lower index): helpers.evaluate_line's
    pixels and helpers.max_safe_elevation (terrain, and the surface or None), steps, length.
    None for a line without a pixel between its anchors."""
    r1, c1, r2, c2 = int(p[0]), int(p[1]), int(q[0]), int(q[1])
    dr, dc = r2 - r1, c2 - c1
    steps = max(abs(dr), abs(dc))
    if steps < 2:
        return None
    t = np.arange(1, steps) / steps
    rows = r1 + np.rint(dr * t).astype(np.intp)
    cols = c1 + np.rint(dc * t).astype(np.intp)
    length = float(np.hypot(dr, dc)) * res
    limit = sh.max_safe_elevation(t, length, float(z[r1, c1]), float(z[r2, c2]), sag_table)
    s = None if surface is None else limit - surface[rows, cols]
    return limit - z[rows, cols], s, steps, length


def grid_namespace(grid: Dict, z: np.ndarray, surface: Optional[np.ndarray], sag_table, anchors: np.ndarray,
                   fall: float) -> SimpleNamespace:
    """The object end_zone_study.diagnose_line, line_detail and buckets_of and profile_chip read,
    from a capture's grid instead of a captured call (end_zone_study.setup):
    - z: the terrain (np.asarray of z, its dtype kept: the filled terrain the search used),
    - res: grid["res"] as a float,
    - sag_table: the run's sag.EnvelopeTable, None under the formula model,
    - fall: helpers.fall_allowance of the run (diagnose_line's delta is fall - end_clearance),
    - grid: the grid dict itself (to_pixel, pixels_wgs84),
    - anchors: step 2's anchors as int64 (n, 2) pixels (row, col), C-contiguous,
    - surface: the obstacle surface (np.asarray) or None without a surface model,
    - slope_threshold: grid.get("slope_threshold"), the search's degrees (None when not recorded),
    - nmpt_mode: grid.get("nmpt"), the search's surface mode (None without a surface model)."""
    return SimpleNamespace(z=np.asarray(z), res=float(grid["res"]), sag_table=sag_table, fall=float(fall), grid=grid,
                           anchors=np.ascontiguousarray(anchors, dtype=np.int64).reshape(-1, 2),
                           surface=None if surface is None else np.asarray(surface),
                           slope_threshold=grid.get("slope_threshold"), nmpt_mode=grid.get("nmpt"))


def profile_chip(a: SimpleNamespace, lo, hi, delta: float, title: str, path: str, zone: float = 0.0,
                 cap: float = sh.ZONE_CAP):
    """The terrain along a line with today's limit and the limit moved up by delta, the zone of
    `zone` metres shaded (at most cap of the line's length), as a PNG at path; a reads z, res and
    sag_table (end_zone_study.setup's namespace or grid_namespace's)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    m = margins(a.z, lo, hi, a.res, a.sag_table)
    steps, length = m[2], m[3]
    t = np.arange(steps + 1) / steps
    r1, c1 = int(lo[0]), int(lo[1])
    dr, dc = int(hi[0]) - r1, int(hi[1]) - c1
    ground = a.z[r1 + np.rint(dr * t).astype(int), c1 + np.rint(dc * t).astype(int)]
    limit = sh.max_safe_elevation(t, length, float(ground[0]), float(ground[-1]), a.sag_table)
    fig, ax = plt.subplots(figsize=(8, 3.2))
    if zone > 0:
        kz = sh.zone_steps(steps, length, zone, cap)
        for x0, x1 in ((0, kz * length / steps), (length - kz * length / steps, length)):
            ax.axvspan(x0, x1, color="#fde68a", alpha=0.5, lw=0)
    ax.plot(t * length, ground, color="#555", label="terrain")
    ax.plot(t * length, limit, color="#2b6cb0", label="limit (today)")
    ax.plot(t * length, limit + delta, color="#2b6cb0", ls=":", label="limit + delta (in a zone)")
    ax.set_title(title, fontsize=8)
    ax.set_xlabel("m from a1")
    ax.legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)
