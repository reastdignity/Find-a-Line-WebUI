"""
Run by hand: what a "reach mask" of the 3D view would cost the worker's quick lane (docs/3d-view-contract.md,
"/api/patch"; the 3D view of 3D view round 2): for ONE fixed anchor of the patch's grid, for every sample of
the grid, is a line from the anchor to the sample valid, and with what clearance? The quick lane is one process
shared by all users and never imports numba (tests/test_patch.py::test_patch_loads_no_numba); the question is
whether a batched numpy evaluation is fast enough or the numba kernel (linesearch.evaluate_lines) is needed there.

"Valid" is the search's decision for a pair, without the anchor rules (slope, prominence, drop, wall angle, the
rings' screening): the length within the run's min_length..max_length, the heights of the two anchors differing by
at most min(max_anchor_diff % of the length, max_anchor_diff_m) (linesearch._pairs), and helpers.is_valid of
helpers.evaluate_line for the run's model (the formula, or the sag table of search._sag_table) and nmpt mode
over the run's terrain and obstacle surface (search.profile_of_line's plan.obstacles). The two anchors are
ordered as the search orders a pair (the one with the lower [row, col] first: the pixels sampled depend on the
direction, np.rint rounding halves to even).

Engines (`reach`):
  numpy  our own batched evaluation: lines of similar length in rectangular batches, the arithmetic of
         helpers.evaluate_line / max_safe_elevation / sag.EnvelopeTable (identical results, see `check`)
  numba  linesearch.evaluate_lines, the search's kernel, on the pairs (fixed anchor, sample)

    uv run tools/perf_reach.py measure --out <scratch> --data <data folder> --case poland-1m --case poland-2m
    uv run tools/perf_reach.py numba-cost --out <scratch>
    uv run tools/perf_reach.py report --out <scratch>

`measure` writes <out>/results-<case>.json (a case's step 1, the engines per lattice step, the equality with
helpers.evaluate_line, the representatives of a fixed point, the answer sizes) and prints the tables. Each case
works in <out>/<case>/ with a data folder whose cache is a link to the real one (nothing is written to the real
runs/); the process runs offline (a dead HTTP proxy) unless --online. Remove a case's folder with its links
first (a junction: os.rmdir("<out>/<case>/data/cache"), never rmtree through it).
"""

import argparse
import dataclasses
import gc
import json
import math
import os
import statistics
import subprocess
import sys
import threading
import time
import zlib
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

NUMPY_ELEMENTS = 1 << 20      # the samples (lines x pixels) of one batch of the numpy engine
NUMBA_PART = 1 << 18          # the targets handed to evaluate_lines at once
LATTICE_STEPS = (1, 2, 4)
THREAD_COUNTS = (1, 2, 4)
SECTOR_DEG = 15.0             # the direction sectors of the representatives
MASK_STEP_M = 0.5             # the answer's clearance steps
MASK_STEPS_MAX = 127          # 7 bits
TREES_BIT = 0x80
CHECK_SAMPLE = 2500           # the random targets of `check` ...
CHECK_BORDERLINE = 1000       # ... and up to this many with a clearance within BORDER_M of 0
BORDER_M = 1.0
OTHER_POINTS = 3              # steep points beside the line's two anchors
CASES = {
    "clip": {"kind": "clip"},
    # the real runs of the data folder, each its longest line (lines.csv): 1 m, 2 m (the Gozo coast: sea and cliffs;
    # the 2 m Polish run of 2026-10-23 is older than the grid alignment and is not reproduced by today's code), 1 m with sag
    "poland-1m": {"run": "2026-10-25_085353_Kobylanka-Borynia"},
    "malta-2m": {"run": "2026-10-25_205659_coast-100-m-within-osm-Gozo"},
    "poland-1m-sag": {"run": "2026-10-25_165522_Dolinki-pod-Krakowem-Jezmanowice-i-spolk"},
}
CLIP_TIF = os.path.join(HERE, "tests", "data", "zabi_kon_nmt.tif")
CLIP_SIDE_M = 500


# --- Measuring ---------------------------------------------------------------------------------------------

class PeakRss:
    """The process's resident set sampled every `interval` seconds while the block runs: the peak, and the
    growth over the start (memory-mapped grids count as they are paged in)."""

    def __init__(self, interval: float = 0.01):
        import psutil
        self.process, self.interval = psutil.Process(), interval
        self.start = self.peak = 0
        self._stop = threading.Event()

    def _run(self):
        while not self._stop.wait(self.interval):
            self.peak = max(self.peak, self.process.memory_info().rss)

    def __enter__(self):
        self.start = self.peak = self.process.memory_info().rss
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        self._thread.join()
        self.peak = max(self.peak, self.process.memory_info().rss)

    @property
    def growth(self) -> int:
        return self.peak - self.start


def timed(fn, reps: int):
    """(the last result, the seconds of each of reps calls)."""
    seconds, result = [], None
    for _ in range(reps):
        result = None
        gc.collect()
        t0 = time.perf_counter()
        result = fn()
        seconds.append(time.perf_counter() - t0)
    return result, seconds


def spread(seconds: Sequence[float]) -> Dict:
    return {"median": statistics.median(seconds), "min": min(seconds), "max": max(seconds), "runs": list(seconds)}


# --- The patch: step 1 -------------------------------------------------------------------------------------

@dataclasses.dataclass
class Patch:
    """The grids of the 3D view's patch of a run around a line (search.patch_of_line's square), with the run's
    obstacle surface: what the quick lane has after its step 1."""
    meta: Dict
    plan: object
    data: object
    res: float
    size: int
    left: float
    top: float
    z: np.ndarray
    s: Optional[np.ndarray]
    anchors: List[Tuple[int, int]]
    nmpt_mode: Optional[str]
    sag_table: object
    step1_seconds: float
    work: str
    obstacles: str

    @property
    def params(self) -> Dict:
        return self.meta["params"]

    def pixel(self, lat: float, lon: float) -> Tuple[int, int]:
        """The pixel of the patch holding a point (as patch_of_line places the line's anchors)."""
        import area as ar
        x, y = ar._to(self.meta["center"]["crs"])(lon, lat)
        return int(round((self.top - y) / self.res - 0.5)), int(round((x - self.left) / self.res - 0.5))

    def close(self):
        import cache
        self.z = self.s = self.data = self.plan = None
        gc.collect()  # close the memory-mapped grids before the work folder is deleted (Windows)
        cache.remove_work(self.work)


def build_patch(meta: Dict, data_dir: str, work: str, anchor1: Tuple[float, float], anchor2: Tuple[float, float],
                obstacles: str = "run", side_m: Optional[float] = None) -> Patch:
    """Step 1 of search.patch_of_line for the line (lat, lon) x 2 of a run (meta: its run.json), the same
    square (PATCH_BLOCK·n + 1 samples centred on the line's middle, on the run's pixel edges) and the same
    prepare_data call (the uncertain shore's kinds too), but with the obstacle surface of the run's rule as
    search.profile_of_line has it. obstacles: "run" the rule the run recorded (None: the surface model as it
    is), "rule" the current obstacles.RULE where the source and the nmpt mode allow it, "none" the surface
    model as it is. The seconds of plan_search and prepare_data are in step1_seconds."""
    import dataclasses as dc

    from pyproj import Transformer

    import area as ar
    import obstacles as ob
    import search
    from params import SearchParams
    import sources as src
    p = meta["params"]
    values = search._run_values(meta)
    crs, res = meta["center"]["crs"], float(p["resolution"])
    to_xy = ar._to(crs)
    (x1, y1), (x2, y2) = to_xy(anchor1[1], anchor1[0]), to_xy(anchor2[1], anchor2[0])
    length = math.hypot(x2 - x1, y2 - y1)
    if side_m is None:
        side_m = max(search.PATCH_SIDE_MIN, length + search.PATCH_SIDE_MARGIN)
    size = search.PATCH_BLOCK * max(1, math.ceil(side_m / res / search.PATCH_BLOCK)) + 1
    paths = search.Paths(data_dir, work)
    os.makedirs(work, exist_ok=True)
    t0 = time.perf_counter()
    source, _ = src.choose_source(values["source"], anchor1[0], anchor1[1], paths.cache,
                                  values.get("elevation_file"), values.get("surface_file"))
    ox, oy = source.grid_origin
    half = size // 2
    left = ox + (math.floor(((x1 + x2) / 2 - ox) / res) - half) * res
    bottom = oy + (math.floor(((y1 + y2) / 2 - oy) / res) - half) * res
    right, top = left + size * res, bottom + size * res
    to_lonlat = Transformer.from_crs(crs, "EPSG:4326", always_xy=True).transform
    inset = res / 4
    corners = [(left + inset, bottom + inset), (right - inset, bottom + inset), (right - inset, top - inset),
               (left + inset, top - inset)]
    ring = [list(to_lonlat(x, y)) for x, y in corners]
    values["geometry"] = {"type": "Polygon", "coordinates": [ring + [ring[0]]]}
    plan = search.plan_search(SearchParams(**values), paths, lambda kind, text: None, with_margin=False)
    grid = plan.grid
    if (grid.width, grid.height) != (size, size) or abs(grid.left - left) > res / 100 or abs(grid.top - top) > res / 100:
        raise RuntimeError(f"the patch's grid ({grid.width} x {grid.height} at {grid.left}, {grid.top}) is not "
                           f"the square asked for ({size} x {size} at {left}, {top})")
    if obstacles == "run":
        plan.obstacles = p.get("obstacles")
    elif obstacles == "rule":
        plan.obstacles = dict(ob.RULE) if plan.nmpt and plan.source.obstacles and ob.RULE else None
    elif obstacles == "none":
        plan.obstacles = None
    else:
        raise ValueError("obstacles: run, rule or none")
    data = search.prepare_data(plan, statistics=False, shore="kinds")
    step1 = time.perf_counter() - t0
    anchors = []
    for x, y in ((x1, y1), (x2, y2)):
        anchors.append((int(round((grid.top - y) / res - 0.5)), int(round((x - grid.left) / res - 0.5))))
    sag_table = None
    if p["model"] == "sag":
        sag_table = search._sag_table(dc.astuple(plan.rigging), p["min_length"], p["max_length"])
    z = np.asarray(data.elevation)
    s = np.asarray(data.surface) if data.surface is not None else None
    return Patch(meta, plan, data, res, size, grid.left, grid.top, z, s, anchors, plan.nmpt, sag_table, step1,
                 work, obstacles)


# --- The targets -------------------------------------------------------------------------------------------

@dataclasses.dataclass
class Targets:
    """The samples of the patch's lattice (every `step`-th row and column) a line from the fixed anchor may
    reach: within the run's lengths and height differences."""
    step: int
    shape: Tuple[int, int]   # the lattice
    flat: np.ndarray         # index into the lattice, row-major
    rows: np.ndarray         # pixel row and column of each target in the patch (int64)
    cols: np.ndarray

    def __len__(self) -> int:
        return len(self.flat)


def candidate_targets(z: np.ndarray, res: float, fixed: Tuple[int, int], step: int, min_length: float,
                      max_length: float, max_dh_ratio: float, max_dh: float) -> Targets:
    """The lattice samples whose line to the fixed anchor passes linesearch._pairs' length test
    (min_length <= length <= max_length, length = hypot(dr, dc) · res) and height test (the anchors' float32
    heights differ by at most min(max_dh_ratio · length, max_dh); a sample without data never does)."""
    height, width = z.shape
    r = np.arange(0, height, step)[:, None]
    c = np.arange(0, width, step)[None, :]
    length = np.hypot(r - fixed[0], c - fixed[1]) * res
    ok = (length <= max_length) & (length >= min_length)
    ok &= np.abs(z[::step, ::step] - z[fixed[0], fixed[1]]) <= np.minimum(max_dh_ratio * length, max_dh)
    flat = np.flatnonzero(ok)
    n_cols = c.shape[1]
    return Targets(step, (r.shape[0], n_cols), flat, (flat // n_cols) * step, (flat % n_cols) * step)


def limits_of(params: Dict) -> Dict:
    """The run's limits of a pair (search._pair_search: p.max_anchor_diff / 100, p.max_anchor_diff_m)."""
    return {"min_length": float(params["min_length"]), "max_length": float(params["max_length"]),
            "max_dh_ratio": params["max_anchor_diff"] / 100, "max_dh": float(params["max_anchor_diff_m"])}


def forward(fixed: Tuple[int, int], rows: np.ndarray, cols: np.ndarray) -> np.ndarray:
    """Whether the fixed anchor is the first of the pair with each target: the lower [row, col], as the search's
    anchors are ordered (row-major) and a pair is checked from its lower index."""
    return (fixed[0] < rows) | ((fixed[0] == rows) & (fixed[1] < cols))


# --- The engines -------------------------------------------------------------------------------------------

@dataclasses.dataclass
class Evaluation:
    """Per target: valid (helpers.is_valid of the run's nmpt mode), the clearance over the terrain (NaN: not
    known; the numba engine gives it for the valid ones only) and over the surface (NaN: none), and whether a
    valid line passes over trees or buildings (the surface clearance <= 0: the "mark" mode's over_obstacles)."""
    valid: np.ndarray
    clearance: np.ndarray
    clearance_nmpt: np.ndarray
    trees: np.ndarray


def decide(clearance: np.ndarray, nmpt: np.ndarray, nmpt_mode: Optional[str]) -> Evaluation:
    """helpers.is_valid on arrays (a NaN clearance never passes; an unmeasured surface clearance is kept)."""
    with np.errstate(invalid="ignore"):
        valid = clearance > 0
        if nmpt_mode == "reject":
            valid &= ~(nmpt <= 0)
        trees = valid & (nmpt <= 0)
    return Evaluation(valid, clearance, nmpt, trees)


def _sag_rows(sag_table, length: np.ndarray, dh: np.ndarray) -> np.ndarray:
    """sag.EnvelopeTable.__call__'s blend of the table for each line (rows of the table at the fractions)."""
    unique, inverse = np.unique(length, return_inverse=True)  # math.log, as EnvelopeTable.__call__ (np.log may differ by an ulp)
    logs = np.array([math.log(v) for v in unique.tolist()])[inverse.ravel()]
    si = np.interp(logs, np.log(sag_table.spans), np.arange(len(sag_table.spans)))
    ri = np.interp(dh / length, sag_table.RATIOS, np.arange(len(sag_table.RATIOS)))
    i0 = np.minimum(si.astype(np.int64), len(sag_table.spans) - 2)
    j0 = np.minimum(ri.astype(np.int64), len(sag_table.RATIOS) - 2)
    a, b = (si - i0)[:, None], (ri - j0)[:, None]
    sag = sag_table.sag
    return ((1 - a) * (1 - b) * sag[i0, j0] + a * (1 - b) * sag[i0 + 1, j0]
            + (1 - a) * b * sag[i0, j0 + 1] + a * b * sag[i0 + 1, j0 + 1])


def _interp_rows(t: np.ndarray, xp: np.ndarray, rows: np.ndarray) -> np.ndarray:
    """np.interp(t[k], xp, rows[k]) for every line k, with numpy's arithmetic (t strictly inside xp)."""
    j = np.searchsorted(xp, t, side="right") - 1
    j = np.clip(j, 0, len(xp) - 2)
    f0 = np.take_along_axis(rows, j, axis=1)
    f1 = np.take_along_axis(rows, j + 1, axis=1)
    slope = (f1 - f0) / (xp[j + 1] - xp[j])
    return slope * (t - xp[j]) + f0


def evaluate_numpy(z: np.ndarray, s: Optional[np.ndarray], res: float, fixed: Tuple[int, int], rows: np.ndarray,
                   cols: np.ndarray, nmpt_mode: Optional[str], sag_table=None,
                   elements: int = NUMPY_ELEMENTS) -> Evaluation:
    """helpers.evaluate_line for the pairs (fixed anchor, each target), batched: the pairs sorted by their
    steps and cut into batches of `elements` samples at most (lines x pixels, shorter lines padded and
    masked), each batch one set of array operations. The same arithmetic as evaluate_line (the DDA pixels
    r1 + rint(dr · t), max_safe_elevation, the sag table's blend and np.interp), so the same values."""
    from helpers import LEASH_FALL, SLOPE
    n = len(rows)
    clearance, nmpt = np.full(n, np.nan), np.full(n, np.nan)
    fwd = forward(fixed, rows, cols)
    r1, c1 = np.where(fwd, fixed[0], rows), np.where(fwd, fixed[1], cols)
    r2, c2 = np.where(fwd, rows, fixed[0]), np.where(fwd, cols, fixed[1])
    dr, dc = r2 - r1, c2 - c1
    steps = np.maximum(np.abs(dr), np.abs(dc))
    order = np.flatnonzero(steps >= 2)
    order = order[np.argsort(steps[order], kind="stable")]
    sorted_steps = steps[order]
    fall_zone = float(sag_table.rig.fall_zone) if sag_table is not None else 0.0
    pos = 0
    while pos < len(order):
        lo, hi = pos + 1, len(order)  # the longest batch within `elements`
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if (mid - pos) * max(1, int(sorted_steps[mid - 1]) - 1) <= elements:
                lo = mid
            else:
                hi = mid - 1
        batch = order[pos:lo]
        pos = lo
        k_steps = steps[batch]
        i = np.arange(1, int(k_steps.max()))[None, :]
        inside = i < k_steps[:, None]
        t = i / k_steps[:, None]
        br1, bc1 = r1[batch][:, None], c1[batch][:, None]
        rr = np.where(inside, br1 + np.rint(dr[batch][:, None] * t).astype(np.intp), br1)
        cc = np.where(inside, bc1 + np.rint(dc[batch][:, None] * t).astype(np.intp), bc1)
        length = np.hypot(dr[batch], dc[batch]).astype(np.float64) * res
        e1 = z[r1[batch], c1[batch]].astype(np.float64)
        e2 = z[r2[batch], c2[batch]].astype(np.float64)
        if sag_table is None:
            limit = np.minimum(e1, e2)[:, None] - SLOPE * np.minimum(t, 1 - t) * length[:, None] - LEASH_FALL
        else:
            sagged = _interp_rows(t, sag_table.fractions, _sag_rows(sag_table, length, e1 - e2))
            limit = (e1[:, None] + (e2 - e1)[:, None] * t) - sagged - fall_zone
        margin = limit - z[rr, cc]
        clearance[batch] = np.where(inside, margin, np.inf).min(axis=1)  # NaN stays: no data fails the line
        if s is not None:
            over = limit - s[rr, cc]
            seen = inside & ~np.isnan(over)
            nmpt[batch] = np.where(seen.any(axis=1), np.where(seen, over, np.inf).min(axis=1), np.nan)
    return decide(clearance, nmpt, nmpt_mode)


def evaluate_numba(z: np.ndarray, s: Optional[np.ndarray], res: float, fixed: Tuple[int, int], rows: np.ndarray,
                   cols: np.ndarray, nmpt_mode: Optional[str], sag_table=None, threads: Optional[int] = None,
                   part: int = NUMBA_PART) -> Evaluation:
    """linesearch.evaluate_lines for the pairs (fixed anchor, each target), `part` targets at a time (the
    anchors array is the fixed anchor and the targets, the pairs ordered as the search orders them; the
    wall angles are not wanted: down is zeros). The lines it keeps are matched to their target by pixel."""
    import numba

    import linesearch as ls
    if threads:
        numba.set_num_threads(threads)
    n = len(rows)
    height, width = z.shape
    valid, clearance, nmpt = np.zeros(n, dtype=bool), np.full(n, np.nan), np.full(n, np.nan)
    lookup = np.full(height * width, -1, dtype=np.int64)
    lookup[rows * width + cols] = np.arange(n)
    for lo in range(0, n, part):
        hi = min(n, lo + part)
        anchors = np.empty((hi - lo + 1, 2), dtype=np.int64)
        anchors[0] = fixed
        anchors[1:, 0], anchors[1:, 1] = rows[lo:hi], cols[lo:hi]
        k = np.arange(1, hi - lo + 1)
        first = forward(fixed, rows[lo:hi], cols[lo:hi])
        found = np.column_stack([np.where(first, 0, k), np.where(first, k, 0)])
        lines = ls.evaluate_lines(found, anchors, z, res, s, sag_table, nmpt_mode, down=np.zeros((len(anchors), 2)))
        a1, a2 = lines.columns["a1"], lines.columns["a2"]
        at_fixed = (a1[:, 0] == fixed[0]) & (a1[:, 1] == fixed[1])
        other = np.where(at_fixed[:, None], a2, a1)
        index = lookup[other[:, 0] * width + other[:, 1]]
        valid[index] = True
        clearance[index], nmpt[index] = lines.columns["clearance"], lines.columns["clearance_nmpt"]
    with np.errstate(invalid="ignore"):
        trees = valid & (nmpt <= 0)
    return Evaluation(valid, clearance, nmpt, trees)


def evaluate_reference(z: np.ndarray, s: Optional[np.ndarray], res: float, fixed: Tuple[int, int],
                       rows: np.ndarray, cols: np.ndarray, nmpt_mode: Optional[str], sag_table=None,
                       reverse: bool = False) -> Evaluation:
    """helpers.evaluate_line and helpers.is_valid line by line. reverse: each pair in the other direction
    (the target first), which samples other pixels where np.rint meets a half."""
    import helpers as sh
    n = len(rows)
    clearance, nmpt = np.full(n, np.nan), np.full(n, np.nan)
    valid = np.zeros(n, dtype=bool)
    fwd = forward(fixed, rows, cols)
    for k in range(n):
        target = (int(rows[k]), int(cols[k]))
        a, b = (fixed, target) if bool(fwd[k]) != reverse else (target, fixed)
        result = sh.evaluate_line(np.array(a), np.array(b), z, res, s, sag_table)
        if result is None:
            continue
        clearance[k] = result[3]
        nmpt[k] = np.nan if result[4] is None else result[4]
        valid[k] = sh.is_valid(result, nmpt_mode)
    with np.errstate(invalid="ignore"):
        trees = valid & (nmpt <= 0)
    return Evaluation(valid, clearance, nmpt, trees)


def evaluate(engine: str, patch: Patch, fixed: Tuple[int, int], targets: Targets, threads: Optional[int] = None
             ) -> Evaluation:
    """One of the engines ("numpy", "numba") on the targets of a patch."""
    args = (patch.z, patch.s, patch.res, fixed, targets.rows, targets.cols, patch.nmpt_mode, patch.sag_table)
    if engine == "numpy":
        return evaluate_numpy(*args)
    if engine == "numba":
        return evaluate_numba(*args, threads=threads)
    raise ValueError("engine: numpy or numba")


def reach(patch: Patch, fixed: Tuple[int, int], step: int = 1, engine: str = "numba",
          threads: Optional[int] = None) -> Tuple[Targets, Evaluation]:
    """The reach of a fixed anchor over the lattice of every `step`-th sample: (the candidate targets, their
    evaluation by the engine)."""
    targets = candidate_targets(patch.z, patch.res, fixed, step, **limits_of(patch.params))
    return targets, evaluate(engine, patch, fixed, targets, threads)


# --- The answer ---------------------------------------------------------------------------------------------

def encode_mask(targets: Targets, ev: Evaluation) -> np.ndarray:
    """The answer's lattice, one uint8 per sample row-major: 0 not valid (or not a candidate), else the
    clearance over the terrain in MASK_STEP_M steps rounded up (1..MASK_STEPS_MAX, so a valid line is never 0)
    in the low 7 bits and the over-trees flag in the high bit."""
    out = np.zeros(targets.shape[0] * targets.shape[1], dtype=np.uint8)
    steps = np.clip(np.ceil(ev.clearance[ev.valid] / MASK_STEP_M), 1, MASK_STEPS_MAX).astype(np.uint8)
    out[targets.flat[ev.valid]] = steps | np.where(ev.trees[ev.valid], TREES_BIT, 0).astype(np.uint8)
    return out.reshape(targets.shape)


def decode_mask(mask: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(valid, the clearance's upper bound in metres, over trees) of an encode_mask lattice."""
    steps = mask & 0x7F
    return steps > 0, steps * MASK_STEP_M, (mask & TREES_BIT) != 0


def mask_bytes(mask: np.ndarray) -> int:
    """The size of the answer: the lattice deflated at zlib level 6 (as the patch's heights)."""
    return len(zlib.compress(np.ascontiguousarray(mask).tobytes(), 6))


# --- The representatives of a fixed point ------------------------------------------------------------------

def sector_representatives(dx: np.ndarray, dy: np.ndarray, value: np.ndarray, sector_deg: float = SECTOR_DEG
                           ) -> np.ndarray:
    """The index of the target with the greatest value in each non-empty sector of direction (dx east, dy north
    from the fixed point; the first of equal ones)."""
    if not len(value):
        return np.zeros(0, dtype=np.int64)
    sector = (np.degrees(np.arctan2(dy, dx)) % 360.0 // sector_deg).astype(np.int64)
    order = np.lexsort((-value, sector))
    first = np.ones(len(order), dtype=bool)
    first[1:] = sector[order][1:] != sector[order][:-1]
    return order[first]


def spot_representatives(x: np.ndarray, y: np.ndarray, clearance: np.ndarray, length: np.ndarray,
                         over: np.ndarray, distance: float, by: str = "clearance") -> np.ndarray:
    """The representatives of the lines from one point grouped as the result's spots (mapping.group_lines,
    viewer/src/grouping.ts): best first (clearance then length, or length then clearance), each line still free
    takes every free line whose target lies within `distance` (dx² + dy² <= distance²); lines over trees are
    grouped apart from the clear ones. Every line shares the fixed point, so only the targets decide."""
    from scipy.spatial import cKDTree
    first, second = (length, clearance) if by == "longest" else (clearance, length)
    d2 = float(distance) ** 2
    reps = []
    for flag in (False, True):
        rows = np.flatnonzero(over == flag)
        if not len(rows):
            continue
        rows = rows[np.lexsort((-second[rows], -first[rows]))]
        px, py = x[rows], y[rows]
        tree = cKDTree(np.column_stack([px, py]))
        free = np.ones(len(rows), dtype=bool)
        for i in range(len(rows)):
            if not free[i]:
                continue
            reps.append(rows[i])
            near = np.asarray(tree.query_ball_point([px[i], py[i]], distance * (1 + 1e-9)), dtype=np.int64)
            dx, dy = px[near] - px[i], py[near] - py[i]
            free[near[dx * dx + dy * dy <= d2]] = False
    return np.asarray(reps, dtype=np.int64)


def representative_counts(patch: Patch, fixed: Tuple[int, int], targets: Targets, ev: Evaluation) -> Dict:
    """How many representatives of the valid lines from a fixed point each rule gives: the best clearance and the
    longest line in each SECTOR_DEG sector of direction, and the spots (the result's greedy grouping at the run's
    group distance and order); in all the valid lines and in those clear of trees only."""
    p, res = patch.params, patch.res
    distance = p.get("group_distance") or max(20.0, 2 * res)
    by = p.get("group_by", "clearance")
    by = by if by in ("clearance", "longest") else "clearance"  # the order by height needs the webbing heights
    out = {"valid": int(ev.valid.sum()), "trees": int(ev.trees.sum()), "group_distance": distance, "group_by": by}
    for name, keep in (("all", ev.valid), ("clear", ev.valid & ~ev.trees)):
        dr, dc = targets.rows[keep] - fixed[0], targets.cols[keep] - fixed[1]
        dx, dy = dc * res, -dr * res
        length = np.hypot(dx, dy)
        clearance = ev.clearance[keep]
        out[name] = {
            "best_clearance": int(len(sector_representatives(dx, dy, clearance))),
            "longest": int(len(sector_representatives(dx, dy, length))),
            "spots": int(len(spot_representatives(dx, dy, clearance, length, ev.trees[keep], distance, by)))
            if keep.any() else 0}
    return out


def steep_points(patch: Patch, count: int = OTHER_POINTS, seed: int = 7, margin: int = 30) -> List[Tuple[int, int]]:
    """Pixels on steep terrain of the patch (the run's slope threshold, helpers.find_significant_slopes' slope),
    at least `margin` pixels inside its edges and away from the line's anchors, drawn at random (a fixed seed)."""
    z = np.asarray(patch.z, dtype=np.float32)
    gy, gx = np.gradient(z, patch.res)
    slope = np.degrees(np.arctan(np.hypot(gx, gy)))
    ok = np.zeros(z.shape, dtype=bool)
    inner = (slice(margin, -margin), slice(margin, -margin))
    ok[inner] = slope[inner] >= float(patch.params["slope_threshold"])
    rows, cols = np.nonzero(ok)
    near = np.zeros(len(rows), dtype=bool)
    for r, c in patch.anchors:
        near |= np.hypot(rows - r, cols - c) * patch.res < 100.0
    rows, cols = rows[~near], cols[~near]
    if not len(rows):
        raise RuntimeError("no steep terrain in the patch")
    pick = np.random.default_rng(seed).choice(len(rows), size=min(count, len(rows)), replace=False)
    return [(int(rows[i]), int(cols[i])) for i in pick]


# --- The check ---------------------------------------------------------------------------------------------

def compare(a: Evaluation, b: Evaluation, on: Optional[np.ndarray] = None) -> Dict:
    """How two evaluations of the same targets differ: the targets whose validity differs, and the largest
    absolute differences of the clearances (over the terrain and the surface) where both are known; on: the
    targets compared (default: all)."""
    on = np.ones(len(a.valid), dtype=bool) if on is None else on
    out = {"targets": int(on.sum()), "valid_differs": int((a.valid != b.valid)[on].sum()),
           "trees_differs": int((a.trees != b.trees)[on].sum())}
    for name in ("clearance", "clearance_nmpt"):
        x, y = getattr(a, name), getattr(b, name)
        both = on & ~np.isnan(x) & ~np.isnan(y)
        out[f"max_{name}_diff"] = float(np.abs(x[both] - y[both]).max()) if both.any() else 0.0
        out[f"{name}_nan_differs"] = int((np.isnan(x) != np.isnan(y))[on & (a.valid | b.valid)].sum())
    return out


def check(patch: Patch, fixed: Tuple[int, int], targets: Targets, full: Evaluation, seed: int = 11) -> Dict:
    """Both engines against helpers.evaluate_line / is_valid line by line on a random sample of the targets
    (CHECK_SAMPLE of them, with up to CHECK_BORDERLINE whose clearance is within BORDER_M of 0: the decisions that
    could differ; all of them when fewer), and one engine against the other on every target. The reference run
    the other way round (the target first) says how much the direction of a pair matters."""
    n = len(targets)
    rng = np.random.default_rng(seed)
    if n <= CHECK_SAMPLE:
        pick = np.arange(n)
    else:
        near = np.flatnonzero(np.abs(full.clearance) <= BORDER_M)
        pick = np.union1d(rng.choice(n, size=CHECK_SAMPLE, replace=False),
                          rng.choice(near, size=min(CHECK_BORDERLINE, len(near)), replace=False))
    rows, cols = targets.rows[pick], targets.cols[pick]
    args = (patch.z, patch.s, patch.res, fixed, rows, cols, patch.nmpt_mode, patch.sag_table)
    ref, by_numpy, by_numba = evaluate_reference(*args), evaluate_numpy(*args), evaluate_numba(*args)
    out = {"sample": int(len(pick)), "valid_in_sample": int(ref.valid.sum()),
           "numpy": compare(by_numpy, ref), "numba": compare(by_numba, ref, ref.valid),
           "numba_valid_flags": compare(by_numba, ref)["valid_differs"]}
    back = evaluate_reference(*args, reverse=True)
    out["other_direction"] = {"valid_differs": int((back.valid != ref.valid).sum()),
                              "max_clearance_diff": compare(back, ref, ~np.isnan(back.clearance) & ~np.isnan(ref.clearance))
                              ["max_clearance_diff"]}
    return out


def check_search(z: np.ndarray, s: Optional[np.ndarray], res: float, fixed: Tuple[int, int], limits: Dict,
                 nmpt_mode: Optional[str], sag_table=None) -> Dict:
    """The end-to-end meaning of "valid": linesearch.find_valid_lines on a grid whose anchors are all its pixels
    (row-major, as the search's) finds exactly the lines at the fixed anchor that evaluate_numpy calls valid
    (the rings' screening is only a necessary condition, so no anchor rules differ)."""
    import linesearch as ls
    height, width = z.shape
    rr, cc = np.meshgrid(np.arange(height), np.arange(width), indexing="ij")
    anchors = np.column_stack([rr.ravel(), cc.ravel()]).astype(np.int64)
    found = ls.find_valid_lines(z, s, anchors, res, limits["min_length"], limits["max_length"], nmpt_mode, 2,
                                sag_table, limits["max_dh_ratio"], limits["max_dh"])
    a1, a2 = found.columns["a1"], found.columns["a2"]
    at = ((a1[:, 0] == fixed[0]) & (a1[:, 1] == fixed[1])) | ((a2[:, 0] == fixed[0]) & (a2[:, 1] == fixed[1]))
    other = np.where(((a1[:, 0] == fixed[0]) & (a1[:, 1] == fixed[1]))[:, None], a2, a1)[at]
    searched = set(map(tuple, other.tolist()))
    targets = candidate_targets(z, res, fixed, 1, **limits)
    ev = evaluate_numpy(z, s, res, fixed, targets.rows, targets.cols, nmpt_mode, sag_table)
    ours = set(zip(targets.rows[ev.valid].tolist(), targets.cols[ev.valid].tolist()))
    return {"search_lines": len(searched), "valid": len(ours), "only_search": len(searched - ours),
            "only_ours": len(ours - searched)}


def line_reproduced(patch: Patch, row: Dict) -> Dict:
    """Whether today's code gives a run's line (its lines.csv row) the clearances the run saved: a run made
    by older code (another grid alignment, a changed model) does not reproduce, and a reach computed on its
    patch says nothing about its lines."""
    import helpers as sh
    a, b = sorted(patch.anchors)
    result = sh.evaluate_line(np.array(a), np.array(b), patch.z, patch.res, patch.s, patch.sag_table)
    return {"csv_clearance": float(row["clearance_m"]), "clearance": round(result[3], 2),
            "csv_clearance_nmpt": row.get("clearance_nmpt_m"),
            "clearance_nmpt": None if result[4] is None else round(result[4], 2),
            "valid": bool(sh.is_valid(result, patch.nmpt_mode))}


# --- Cases -------------------------------------------------------------------------------------------------

def link(target: str, link_path: str):
    """A directory link (a junction on Windows: no special rights needed)."""
    if os.name == "nt":
        import _winapi
        _winapi.CreateJunction(os.path.abspath(target), link_path)
    else:
        os.symlink(os.path.abspath(target), link_path)


def case_data_folder(out: str, name: str, real_data: Optional[str]) -> str:
    """<out>/<name>/data with `cache` linked to the real data folder's (or an empty one): the worker's paths
    with nothing of the real runs/ or work/ in them."""
    data = os.path.join(out, name, "data")
    os.makedirs(data, exist_ok=True)
    cache_link = os.path.join(data, "cache")
    if not os.path.lexists(cache_link):
        if real_data:
            link(os.path.join(real_data, "cache"), cache_link)
        else:
            os.makedirs(cache_link)
    return data


def longest_row(run_dir: str) -> Dict:
    """The row of the longest line of a run's lines.csv."""
    import csv
    with open(os.path.join(run_dir, "lines.csv"), encoding="utf-8-sig", newline="") as f:
        return max(csv.DictReader(f), key=lambda r: float(r["length_m"]))


def longest_line(run_dir: str) -> Tuple[Tuple[float, float], Tuple[float, float], float]:
    """The anchors (lat, lon) x 2 and the length of the longest line of a run's lines.csv."""
    best = longest_row(run_dir)
    return ((float(best["anchor1_lat"]), float(best["anchor1_lon"])),
            (float(best["anchor2_lat"]), float(best["anchor2_lon"])), float(best["length_m"]))


def busiest_anchor(run_dir: str, inside=None) -> Tuple[float, float, int]:
    """The anchor (lat, lon) that most lines of a run's lines.csv start or end at, and how many; with
    inside(lat, lon), the busiest one for which it is true (an anchor within a patch)."""
    import collections
    import csv
    count = collections.Counter()
    with open(os.path.join(run_dir, "lines.csv"), encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            count[(row["anchor1_lat"], row["anchor1_lon"])] += 1
            count[(row["anchor2_lat"], row["anchor2_lon"])] += 1
    for (lat, lon), n in count.most_common():
        if inside is None or inside(float(lat), float(lon)):
            return float(lat), float(lon), n
    raise ValueError("no anchor of the run's lines inside")


def make_clip_run(data: str) -> Dict:
    """A run of the Żabi Koń clip (offline, tests/test_patch.py's fixture) in `data`: its run.json."""
    result = subprocess.run(
        [sys.executable, "findaline.py", "--elevation-file", CLIP_TIF, "--northing", "254608", "--easting", "553966",
         "--radius", "150", "--water", "off", "--fill-gaps", "off", "--no-plot", "--yes", "--ortho", "never",
         "--nmpt", "off", "--model", "sag", "--data-dir", data],
        cwd=HERE, capture_output=True, text=True, encoding="utf-8", timeout=900, env=offline_env())
    if result.returncode != 0:
        raise RuntimeError(result.stdout + result.stderr)
    runs = os.path.join(data, "runs")
    run = next(d for d in os.listdir(runs) if os.path.isfile(os.path.join(runs, d, "run.json")))
    with open(os.path.join(runs, run, "run.json"), encoding="utf-8") as f:
        return json.load(f)


def offline_env() -> Dict:
    return {**os.environ, "HTTP_PROXY": "http://127.0.0.1:9", "HTTPS_PROXY": "http://127.0.0.1:9", "NO_PROXY": ""}


def load_case(name: str, out: str, real_data: Optional[str]):
    """(run.json, data folder, the line's anchors, side_m or None, the line's length, the run's folder)."""
    spec = CASES[name]
    data = case_data_folder(out, name, real_data if spec.get("run") else None)
    if spec.get("kind") == "clip":
        meta = make_clip_run(data)
        a1, a2, length = longest_line(os.path.join(data, "runs", meta["id"]))
        return meta, data, a1, a2, CLIP_SIDE_M, length, os.path.join(data, "runs", meta["id"])
    if not real_data:
        raise SystemExit("--data (the real data folder) is needed for " + name)
    run_dir = os.path.join(real_data, "runs", spec["run"])
    with open(os.path.join(run_dir, "run.json"), encoding="utf-8") as f:
        meta = json.load(f)
    a1, a2, length = longest_line(run_dir)
    return meta, data, a1, a2, None, length, run_dir


def measure_case(name: str, out: str, real_data: Optional[str], reps: int = 3, obstacles: str = "rule",
                 skip_numpy_at_1: bool = False) -> Dict:
    """Everything the report needs of one case (see the module's docstring)."""
    import numba
    meta, data, a1, a2, side_m, line_m, run_dir = load_case(name, out, real_data)
    result = {"case": name, "run": meta["id"], "model": meta["params"]["model"], "nmpt": meta["params"]["nmpt"],
              "resolution": meta["params"]["resolution"], "line_m": line_m, "obstacles": obstacles,
              "recorded_obstacles": meta["params"].get("obstacles") is not None,
              "limits": limits_of(meta["params"]), "cpu_count": os.cpu_count(), "numba_threads": numba.config.NUMBA_NUM_THREADS}
    work_root = os.path.join(out, name, "work")
    patch = None
    step1, rss1 = [], None
    for k in range(reps):
        if patch is not None:
            patch.close()
        gc.collect()
        with PeakRss() as rss:
            patch = build_patch(meta, data, os.path.join(work_root, f"step1-{k}"), a1, a2, obstacles, side_m)
        step1.append(patch.step1_seconds)
        rss1 = rss1 or {"start": rss.start, "peak": rss.peak, "growth": rss.growth}
    result["step1"] = {**spread(step1), "rss": rss1, "size": patch.size, "dtype": str(patch.z.dtype),
                       "has_surface": patch.s is not None, "applied_rule": patch.plan.obstacles is not None}
    fixed = patch.anchors[0]
    result["anchors"] = [list(a) for a in patch.anchors]
    result["line_reproduced"] = line_reproduced(patch, longest_row(run_dir))
    lat, lon, n_lines = busiest_anchor(run_dir, lambda la, lo: all(
        0 <= v < patch.size for v in patch.pixel(la, lo)))
    busy = patch.pixel(lat, lon)
    result["busiest"] = {"pixel": list(busy), "lines_in_run": n_lines}
    result["finite_share"] = float(np.isfinite(patch.z).mean())
    if patch.sag_table is not None:  # the quick lane builds it once per process (search._sag_table)
        t0 = time.perf_counter()
        from sag import EnvelopeTable
        EnvelopeTable(patch.sag_table.rig, patch.params["min_length"], patch.params["max_length"])
        result["sag_table_build_seconds"] = time.perf_counter() - t0
    evaluate("numba", patch, fixed, candidate_targets(patch.z, patch.res, fixed, 4, **limits_of(patch.params)))  # compile
    runs, masks, last = [], {}, {}
    for step in LATTICE_STEPS:
        targets = candidate_targets(patch.z, patch.res, fixed, step, **limits_of(patch.params))
        row = {"step": step, "samples": int(targets.shape[0] * targets.shape[1]), "targets": len(targets)}
        if skip_numpy_at_1 and step == 1:
            numpy_ev = None
        else:
            with PeakRss() as rss:
                numpy_ev, seconds = timed(lambda: evaluate("numpy", patch, fixed, targets), reps)
            row["numpy"] = {**spread(seconds), "rss_peak": rss.peak, "rss_growth": rss.growth}
        row["numba"] = {}
        for threads in THREAD_COUNTS:
            with PeakRss() as rss:
                numba_ev, seconds = timed(lambda: evaluate("numba", patch, fixed, targets, threads), reps)
            row["numba"][str(threads)] = {**spread(seconds), "rss_peak": rss.peak, "rss_growth": rss.growth}
        numba.set_num_threads(numba.config.NUMBA_NUM_THREADS)
        reference = numpy_ev if numpy_ev is not None else evaluate("numpy", patch, fixed, targets)
        row["valid"] = int(reference.valid.sum())
        row["trees"] = int(reference.trees.sum())
        row["engines_differ"] = compare(reference, numba_ev, reference.valid | numba_ev.valid)
        mask = encode_mask(targets, reference)
        row["answer_bytes"] = mask_bytes(mask)
        row["answer_raw_bytes"] = int(mask.size)
        valid_back, upper, trees_back = decode_mask(mask)
        row["mask_roundtrip_ok"] = bool(
            (valid_back.ravel()[targets.flat] == reference.valid).all() and
            (upper.ravel()[targets.flat][reference.valid] >= reference.clearance[reference.valid]).all())
        busy_targets, busy_ev = reach(patch, busy, step, "numba")
        busy_mask = encode_mask(busy_targets, busy_ev)
        row["busiest"] = {"targets": len(busy_targets), "valid": int(busy_ev.valid.sum()), "trees": int(busy_ev.trees.sum()),
                          "answer_bytes": mask_bytes(busy_mask)}
        runs.append(row)
        last[step] = (targets, reference)
    result["lattice"] = runs
    result["check"] = check(patch, fixed, *last[2][:1], last[2][1])
    reps_out = {}
    points = [("anchor 1", patch.anchors[0]), ("anchor 2", patch.anchors[1]), ("busiest anchor", busy)] + [
        (f"steep {k + 1}", pt) for k, pt in enumerate(steep_points(patch))]
    for step in (1, 2):
        rows = []
        for label, point in points:
            if not np.isfinite(patch.z[point]):
                rows.append({"point": label, "pixel": list(point), "valid": 0, "note": "no data"})
                continue
            targets, ev = reach(patch, point, step, "numba")
            rows.append({"point": label, "pixel": list(point), "targets": len(targets),
                         **representative_counts(patch, point, targets, ev)})
        reps_out[str(step)] = rows
    result["representatives"] = reps_out
    import psutil
    result["peak_wset"] = psutil.Process().memory_info().peak_wset if os.name == "nt" else None
    patch.close()
    return result


# --- numba's one-time costs --------------------------------------------------------------------------------

def numba_child(spec: Dict) -> Dict:
    """In a fresh process (the cache of compiled kernels NUMBA_CACHE_DIR names, set by the parent): the
    import of numba and linesearch, and the first call of evaluate_lines in each argument-type variant a quick
    lane would meet (read-only memory-mapped float32 grids, with a surface and without, formula and sag)."""
    import psutil
    process = psutil.Process()
    t0 = time.perf_counter()
    import helpers  # noqa: F401
    import numpy  # noqa: F401
    t_base = time.perf_counter() - t0
    rss_base = process.memory_info().rss
    t0 = time.perf_counter()
    import numba  # noqa: F401
    t_numba = time.perf_counter() - t0
    t0 = time.perf_counter()
    import linesearch as ls
    t_ls = time.perf_counter() - t0
    rss_imported = process.memory_info().rss
    import sag
    rng = np.random.default_rng(3)
    base = os.path.join(spec["work"], "grids")
    os.makedirs(base, exist_ok=True)
    grid = np.cumsum(np.cumsum(rng.normal(0, 0.2, (400, 400)), axis=0), axis=1).astype(np.float32) + 500
    np.save(os.path.join(base, "z.npy"), grid)
    np.save(os.path.join(base, "s.npy"), grid + 2)
    z = np.load(os.path.join(base, "z.npy"), mmap_mode="r")
    s = np.load(os.path.join(base, "s.npy"), mmap_mode="r")
    anchors = np.column_stack([rng.integers(0, 400, 3000), rng.integers(0, 400, 3000)]).astype(np.int64)
    found = np.column_stack([np.arange(0, 2998), np.arange(1, 2999)]).astype(np.int64)
    t0 = time.perf_counter()
    table = sag.EnvelopeTable(sag.Rigging(), 30, 300)
    t_table = time.perf_counter() - t0
    calls = {}
    for label, surface, sag_table in (("formula_with_surface", s, None), ("formula_no_surface", None, None),
                                      ("sag_with_surface", s, table)):
        t0 = time.perf_counter()
        ls.evaluate_lines(found, anchors, z, 1.0, surface, sag_table, "mark", down=np.zeros((len(anchors), 2)))
        calls[label] = time.perf_counter() - t0
    t0 = time.perf_counter()
    ls.evaluate_lines(found, anchors, z, 1.0, s, None, "mark", down=np.zeros((len(anchors), 2)))
    again = time.perf_counter() - t0
    return {"kind": spec["kind"], "import_helpers_numpy_s": t_base, "import_numba_s": t_numba,
            "import_linesearch_s": t_ls, "first_calls_s": calls, "repeat_call_s": again, "sag_table_s": t_table,
            "rss_base": rss_base, "rss_after_import": rss_imported, "rss_end": process.memory_info().rss,
            "peak_wset": process.memory_info().peak_wset if os.name == "nt" else None}


def numba_cost(out: str, reps: int = 3) -> Dict:
    """numba's one-time costs: `reps` times a child process with an empty cache of compiled kernels (cold), then
    another with the cache the first one filled (warm). The results are the medians of the children's numbers."""
    import shutil
    runs = {"cold": [], "warm": []}
    for _ in range(reps):
        cache_dir = os.path.join(out, "numba-cache")
        if os.path.isdir(cache_dir):
            shutil.rmtree(cache_dir)
        os.makedirs(cache_dir)
        for kind in ("cold", "warm"):
            env = {**os.environ, "NUMBA_CACHE_DIR": cache_dir, "PYTHONIOENCODING": "utf-8"}
            spec = {"kind": kind, "work": os.path.join(out, "numba-child")}
            done = subprocess.run([sys.executable, os.path.abspath(__file__), "_child", json.dumps(spec)], env=env,
                                  capture_output=True, text=True, encoding="utf-8", cwd=HERE, check=True)
            runs[kind].append(json.loads(done.stdout.strip().splitlines()[-1]))

    def median_of(items):
        first = items[0]
        if isinstance(first, dict):
            return {k: median_of([i[k] for i in items]) for k in first}
        if isinstance(first, (int, float)):
            return statistics.median(items)
        return first
    return {kind: {**median_of(runs[kind]), "runs": len(runs[kind])} for kind in runs}


# --- Tables ------------------------------------------------------------------------------------------------

def tables(results: List[Dict], cost: Optional[Dict] = None) -> str:
    lines = ["Step 1 (plan_search + prepare_data of the patch, seconds, median [min-max] of the repeats; peak RSS of the process)", "",
             "| case | resolution | patch | model | obstacle rule | step 1 s | RSS peak MB |", "| --- | --- | --- | --- | --- | --- | --- |"]
    for r in results:
        s1 = r["step1"]
        lines.append(f"| {r['case']} | {r['resolution']} m | {s1['size']}² | {r['model']} | {r['obstacles']}"
                     f"{'' if s1['applied_rule'] else ' (none applied)'} | {s1['median']:.2f} [{s1['min']:.2f}-{s1['max']:.2f}] | "
                     f"{s1['rss']['peak'] / 2**20:.0f} |")
    lines += ["", "Evaluation of the reach of anchor 1 (seconds, median [min-max]; numba with 1/2/4 threads)", "",
              "| case | lattice | targets | valid | numpy s | numba 1 s | numba 2 s | numba 4 s | numpy RSS growth MB | numba RSS growth MB | answer bytes |",
              "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for r in results:
        for row in r["lattice"]:
            def cell(d):
                return f"{d['median']:.2f} [{d['min']:.2f}-{d['max']:.2f}]" if d else "-"
            nb = row["numba"]
            lines.append(f"| {r['case']} | {row['step']} | {row['targets']} | {row['valid']} | {cell(row.get('numpy'))} | "
                         f"{cell(nb['1'])} | {cell(nb['2'])} | {cell(nb['4'])} | "
                         f"{(row.get('numpy') or {}).get('rss_growth', 0) / 2**20:.0f} | {nb['4']['rss_growth'] / 2**20:.0f} | "
                         f"{row['answer_bytes']} (busiest anchor: {row['busiest']['valid']} valid, {row['busiest']['answer_bytes']}) |")
    if cost:
        lines += ["", "numba's one-time costs in a fresh process (seconds)", "",
                  "| cache | import numba | import linesearch | first call: formula+surface | formula, no surface | sag+surface | repeat call | RSS after import MB |",
                  "| --- | --- | --- | --- | --- | --- | --- | --- |"]
        for kind in ("cold", "warm"):
            c = cost[kind]
            f = c["first_calls_s"]
            lines.append(f"| {kind} | {c['import_numba_s']:.2f} | {c['import_linesearch_s']:.2f} | "
                         f"{f['formula_with_surface']:.2f} | {f['formula_no_surface']:.2f} | {f['sag_with_surface']:.2f} | "
                         f"{c['repeat_call_s']:.3f} | {(c['rss_after_import'] - c['rss_base']) / 2**20:.0f} |")
    lines += ["", "The run's longest line (the patch is centred on it) evaluated by today's code against the run's lines.csv", "",
              "| case | run | clearance csv / now | over the surface csv / now | valid now |", "| --- | --- | --- | --- | --- |"]
    for r in results:
        c = r.get("line_reproduced")
        if c:
            lines.append(f"| {r['case']} | {r['run']} | {c['csv_clearance']} / {c['clearance']} | "
                         f"{c['csv_clearance_nmpt']} / {c['clearance_nmpt']} | {c['valid']} |")
    lines += ["", "Equality with helpers.evaluate_line / is_valid (sample of the targets at lattice 2)", "",
              "| case | sample | valid in it | numpy: validity differs | numpy: max clearance diff | numba: validity differs | numba: max clearance diff | other direction: validity differs |",
              "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for r in results:
        c = r["check"]
        lines.append(f"| {r['case']} | {c['sample']} | {c['valid_in_sample']} | {c['numpy']['valid_differs']} | "
                     f"{c['numpy']['max_clearance_diff']:.3g} | {c['numba_valid_flags']} | {c['numba']['max_clearance_diff']:.3g} | "
                     f"{c['other_direction']['valid_differs']} |")
    lines += ["", "Representatives of the valid lines from a fixed point (all valid / clear of trees)", "",
              "| case | lattice | point | valid | best clearance per 15° | longest per 15° | spots |", "| --- | --- | --- | --- | --- | --- | --- |"]
    for r in results:
        for step, rows in r["representatives"].items():
            for row in rows:
                if "all" not in row:
                    lines.append(f"| {r['case']} | {step} | {row['point']} | 0 | - | - | - |")
                    continue
                a, c = row["all"], row["clear"]
                lines.append(f"| {r['case']} | {step} | {row['point']} | {row['valid']} | {a['best_clearance']} / {c['best_clearance']} | "
                             f"{a['longest']} / {c['longest']} | {a['spots']} / {c['spots']} |")
    return "\n".join(lines)


def load_results(out: str) -> List[Dict]:
    results = []
    for name in CASES:
        path = os.path.join(out, f"results-{name}.json")
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as f:
                results.append(json.load(f))
    return results


def main(argv: Optional[Sequence[str]] = None):
    if argv is None and sys.argv[1:2] == ["_child"]:
        print(json.dumps(numba_child(json.loads(sys.argv[2]))))
        return
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("command", choices=("measure", "numba-cost", "report"))
    parser.add_argument("--out", required=True, help="scratch folder for the cases' folders and results")
    parser.add_argument("--data", help="the real data folder (runs/ read, cache/ linked)")
    parser.add_argument("--case", action="append", choices=sorted(CASES), default=[])
    parser.add_argument("--reps", type=int, default=3)
    parser.add_argument("--obstacles", choices=("run", "rule", "none"), default="rule",
                        help="the obstacle surface: the run's recorded rule, the current rule (default: runs of "
                             "before the rule recorded none) or the surface model as it is")
    parser.add_argument("--skip-numpy-at-1", action="store_true", help="no timing of the numpy engine at lattice 1")
    parser.add_argument("--online", action="store_true", help="allow network access (default: a dead proxy)")
    args = parser.parse_args(argv)
    os.makedirs(args.out, exist_ok=True)
    if not args.online:
        os.environ.update(HTTP_PROXY="http://127.0.0.1:9", HTTPS_PROXY="http://127.0.0.1:9", NO_PROXY="")
    if args.command == "numba-cost":
        cost = numba_cost(args.out, args.reps)
        with open(os.path.join(args.out, "numba-cost.json"), "w", encoding="utf-8") as f:
            json.dump(cost, f, indent=1)
        print(json.dumps(cost, indent=1))
    elif args.command == "report":
        cost = None
        path = os.path.join(args.out, "numba-cost.json")
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as f:
                cost = json.load(f)
        print(tables(load_results(args.out), cost))
    else:
        for name in args.case or ["clip"]:
            print(f"--- {name}", flush=True)
            result = measure_case(name, args.out, args.data, args.reps, args.obstacles, args.skip_numpy_at_1)
            with open(os.path.join(args.out, f"results-{name}.json"), "w", encoding="utf-8") as f:
                json.dump(result, f, indent=1)
            print(tables([result]), flush=True)


if __name__ == "__main__":
    from progress import utf8_output
    utf8_output()  # redirected output in UTF-8, not the Windows code page
    main()
