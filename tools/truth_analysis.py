"""
Run by hand (and by tools/truth_study.py analyse|report): the known lines of each place of the truth
check (2026-11-08) matched to the lines its search found, every miss diagnosed on the search's own
grid, and the recall of the search per country, source, length and resolution.

    uv run tools/truth_analysis.py analyse <out> [--profiles] [--cluster ID ...] [--cache <cache folder>]
    uv run tools/truth_analysis.py report <out> [--no-pictures]

The input is what tools/truth_study.py run writes per cluster of known lines (<out>/<cluster>/:
capture/grid.json, capture/grids.npz, capture/anchors.npy, capture/lines.npz, capture.json and
known.json; the contract of the task, "The capture of a cluster"). Nothing here runs a search, but
--profiles (search.profile_of_line of each known pair from the cache, as a cross-check).

The known lines are SlackMap's (tools/slackmap_data.KnownLine): known positives only. A line missing
from SlackMap is not a line missing from the cliff, so the found spots without a known line are a
precision proxy only, never a count of false lines.

Matching (match): in the grid's CRS, a known line is matched when a found line has both anchors
within its tolerance of the known anchors, either way round (tools/coverage_contrast.matched with a
radius per line), the best of them the one with the smallest sum of the two anchor distances (the
lowest index among ties). The tolerance (tolerance): tol = max(TOL_M, TOL_SHARE * L) metres, L the
line's length_m (the stated length, else the anchors' distance); for coarse anchors (the flag
coarse_anchor, at most 3 decimals) raised to the coordinate quantum QUANTUM_M * 10 ** -decimals.

A miss gets one reason, the first of REASONS whose test holds; "an end" is a known anchor, its pixel
the grid's pixel whose centre is nearest (studylib.to_pixel), "within tol" a distance from the exact
known point (not its pixel) of at most tol, "steep" a slope (studylib.slope_degrees, the slope of
helpers.find_significant_slopes) at or above the search's threshold (grid.json's slope_threshold),
"anchor" a pixel of anchors.npy (step 2's anchors as search._anchors returned them):

- unverifiable: the line has the flag coarse_anchor or length_mismatch (a doubtful geometry) and no
  match. A doubtful line that is matched counts as matched; recall is also given without them.
- outside_area: an end's pixel lies outside the grid or outside the search area (grids.npz's mask).
- no_data: an end's pixel has no elevation (NaN in the filled terrain the search used).
- seam_pixel: an end has no anchor within tol, and a steep pixel within tol lies at a seam of the
  filled gaps or of a neighbour's data (search.at_seams on the masks filled and joined): the search
  drops anchors there.
- water_pixel: an end has no anchor within tol and its pixel is water (the mask water).
- no_steep_pixel: an end has no anchor and no steep pixel inside the area within tol (the record's
  "which" names the end: "a", "b" or "both").
- anchor_filtered: every end without an anchor within tol has a steep pixel inside the area within tol
  (the anchor was left out by the elevation band, the prominence or the drop: "hint" says which of
  those limits the search had).
- the rest have anchors within tol at both ends; their pairs (at most MAX_END_ANCHORS per end, the
  nearest to the known point) go through the search's tests in its order, and the reason is the first
  stage no pair passes:
  - length (not a reason: no pair within the search's min_length..max_length gives "unexplained" with
    the note "length_range"),
  - height_difference: no pair with |z2 - z1| <= min(max_anchor_diff / 100 * length, max_anchor_diff_m)
    (linesearch._pairs' test, grid.json's params),
  - clearance (helpers.evaluate_line's decision with the run's end zone and lift, on the MAX_PAIRS
    pairs of the smallest distance sum that passed the height test): no pair with clearance > 0. Of
    the pair with the largest clearance, the first failing step from either end (helpers.end_zone_rule's
    decision values): within max(NEAR_M, NEAR_SHARE * its length) of an end gives
    clearance_near_anchor, else clearance_mid,
  - surface_obstacle: the search rejects lines over obstacles (nmpt "reject") and no pair that passed
    the terrain passes the surface (helpers.is_valid). Under "mark" the surface rejects nothing (such
    lines are found and marked: the report's over-trees share), so this stage is skipped,
  - wall_angle: max_wall_angle is set and no pair left has max(angle1, angle2) <= it
    (helpers.downslope and wall_angles at the pair's pixels),
  - the other line limits (min_height, min_mean_height, min_high_share): no pair passes them gives
    "unexplained" with the note "height_limits",
- unexplained: a pair passes every test (the note "a_pair_passes"; with min_prominence set the strong
  anchors, which the capture does not hold, may explain it: the note says so), or the length note.

Each record (diagnose) holds the ends (per end: its pixel, slope, the nearest pixel of each of
THRESHOLDS within tol, the anchors within tol and the nearest one's distance, steep pixels at a seam,
the pixel's filled/joined/water flags and canopy), the funnel's counts and its best pair
(end_zone_study.line_detail: length, strict clearance, first strict failure, the lift each ladder zone
needs; with the rule's clearance, the surface's, the wall angles, the height difference and its
limit), "near": end_zone_study.diagnose_line on studylib.grid_namespace within NEAR_PX pixels of the
known ends (the best pair of any pixels there and its staircase: diagnose_line looks at every pair of
pixels, which is too slow at the tolerance itself), and "exact": helpers.evaluate_line between the
two end pixels. A match records the found line's clearances, over obstacles, representative, group,
the anchor distances, the wall angles (on the capture's elevation at the found pixels) and the canopy
(surface - terrain: the obstacle surface the search used) at both anchors.

analyse writes <out>/<cluster>/analysis.json and <out>/analysis.json (every cluster's records); a
cluster whose search failed (capture.json's status "failed", or no grid.json) is listed, not counted.
report writes <out>/study.json, study.md and pictures/ (a hillshade per place: the found lines grey,
the known lines coloured by outcome; a profile chip per miss): per country, source, SlackMap length
bin and resolution, every count as the total and per type (highline, midline).
"""

import argparse
import collections
import contextlib
import datetime
import glob
import io
import json
import math
import os
import shutil
import sys
import warnings
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "tools"))

import numpy as np  # noqa: E402

import helpers as sh  # noqa: E402
import studylib  # noqa: E402
from slackmap_data import KnownLine  # noqa: E402

REASONS = ("unverifiable", "outside_area", "no_data", "seam_pixel", "water_pixel", "no_steep_pixel",
           "anchor_filtered", "height_difference", "clearance_near_anchor", "clearance_mid", "surface_obstacle",
           "wall_angle", "unexplained")
TOL_M = 10.0          # metres: the tolerance's floor
TOL_SHARE = 0.10      # of the line's length
QUANTUM_M = 1.11e5    # metres of one degree of latitude: a coarse anchor's quantum is QUANTUM_M * 10 ** -decimals
DOUBTFUL = ("coarse_anchor", "length_mismatch")  # the geometry flags that make a line unverifiable unless matched
NEAR_M = 10.0         # clearance_near_anchor: the first failure within max(NEAR_M, NEAR_SHARE * length) of an end
NEAR_SHARE = 0.10
NEAR_PX = 2           # pixels around the known ends of diagnose_line's pairs ("near")
THRESHOLDS = (45.0, 40.0, 35.0, 30.0)  # degrees: the nearest pixel of each within tol (end_zone_study's)
ENDS_MAX_M = 150.0    # metres: the ends' neighbourhood at most (a coarse line's tolerance reaches a kilometre)
MAX_END_ANCHORS = 400  # anchors per end in the funnel, the nearest to the known point
MAX_PAIRS = 3000      # pairs evaluated pixel by pixel, those of the smallest distance sum
LENGTH_EDGES = (0, 30, 50, 100, 200, 500)  # SlackMap's length bins, metres
REPORT_TYPES = ("highline", "midline")    # always in the tables, other types when present
PICTURE_PX = 1600     # pixels of a place's hillshade at most (a larger grid is drawn every k-th pixel)
MAP_LINES = 20000     # found lines a place's picture draws at most (a sample beyond)
COLOURS = {"matched": "#2f855a", "missed": "#c53030", "unverifiable": "#dd6b20"}
FOUND_COLOUR = "#9ca3af"


# ---------------------------------------------------------------------------------------------
# the capture

@dataclass
class FoundLines:
    """The lines a cluster's search found (capture/lines.npz): anchors [lat, lon], their values, and
    the anchors in the grid's CRS (xy1, xy2: metres)."""
    a1: np.ndarray
    a2: np.ndarray
    length: np.ndarray
    clearance: np.ndarray
    clearance_nmpt: np.ndarray
    over: np.ndarray
    rep: np.ndarray
    group: np.ndarray
    xy1: np.ndarray
    xy2: np.ndarray

    def __len__(self) -> int:
        return len(self.a1)

    @property
    def spots(self) -> int:
        return int(len(np.unique(self.group)))


@dataclass
class Capture:
    """One cluster's capture (load_capture)."""
    folder: str                       # <out>/<cluster>
    cluster: str
    grid: Dict                        # grid.json
    elevation: np.ndarray             # the filled terrain the search used
    surface: Optional[np.ndarray]     # the obstacle surface it used (None without a surface model)
    filled: Optional[np.ndarray]      # bool masks (None when absent)
    joined: Optional[np.ndarray]
    water: Optional[np.ndarray]
    mask: np.ndarray                  # bool: the search area
    anchors: np.ndarray               # int64 (n, 2): step 2's anchors
    found: FoundLines
    known: List[KnownLine]
    status: Optional[str] = None      # capture.json's status
    _cache: Dict = field(default_factory=dict, repr=False)

    @property
    def res(self) -> float:
        return float(self.grid["res"])

    @property
    def params(self) -> Dict:
        return self.grid.get("params") or {}

    @property
    def source(self) -> Optional[str]:
        return self.grid.get("source") or (self.grid.get("layer_meta") or {}).get("source")

    @property
    def nmpt(self) -> Optional[str]:
        mode = self.grid.get("nmpt", self.params.get("nmpt"))
        return None if mode in (None, "off") else mode

    @property
    def threshold(self) -> float:
        return float(self.grid.get("slope_threshold", self.params.get("slope_threshold", 45.0)))

    @property
    def slope(self) -> np.ndarray:
        if "slope" not in self._cache:
            self._cache["slope"] = studylib.slope_degrees(self.elevation, self.res)
        return self._cache["slope"]

    @property
    def tree(self):
        """A cKDTree of the anchors' pixels (None without anchors)."""
        if "tree" not in self._cache:
            from scipy.spatial import cKDTree
            self._cache["tree"] = cKDTree(self.anchors.astype(np.float64)) if len(self.anchors) else None
        return self._cache["tree"]

    @property
    def sag_table(self):
        if "sag" not in self._cache:
            self._cache["sag"] = sag_table_of(self.grid)
        return self._cache["sag"]

    @property
    def fall(self) -> float:
        return float(self.grid["fall"]) if self.grid.get("fall") is not None else sh.fall_allowance(self.sag_table)

    @property
    def namespace(self):
        """studylib.grid_namespace of the capture (what end_zone_study.diagnose_line and profile_chip read)."""
        if "ns" not in self._cache:
            self._cache["ns"] = studylib.grid_namespace(self.grid, self.elevation, self.surface, self.sag_table,
                                                        self.anchors, self.fall)
        return self._cache["ns"]


def sag_table_of(grid: Dict):
    """The run's sag.EnvelopeTable as search._lines makes it (search._sag_table of the rigging and the
    lengths of the search), None under the formula model."""
    p = grid.get("params") or {}
    if (grid.get("model") or p.get("model")) != "sag":
        return None
    import dataclasses

    import sag
    import search
    rigging = grid.get("rigging") or p.get("rigging") or {}
    rig = sag.Rigging(**rigging) if isinstance(rigging, dict) else sag.Rigging(*rigging)
    with contextlib.redirect_stdout(io.StringIO()):  # the bar of the table
        return search._sag_table(dataclasses.astuple(rig), p["min_length"], p["max_length"])


def _xy(grid: Dict, latlon) -> np.ndarray:
    """(n, 2) [lat, lon] -> (n, 2) [x, y] metres in the grid's CRS."""
    latlon = np.asarray(latlon, dtype=np.float64).reshape(-1, 2)
    if not len(latlon):
        return np.zeros((0, 2))
    x, y = studylib._transformer("EPSG:4326", grid["crs"]).transform(latlon[:, 1], latlon[:, 0])
    return np.column_stack([np.asarray(x, dtype=np.float64), np.asarray(y, dtype=np.float64)])


def _pixel_float(grid: Dict, lat: float, lon: float) -> Tuple[float, float]:
    """The (row, col) of a WGS84 point on the grid as floats (pixel centres at whole numbers)."""
    x, y = studylib._transformer("EPSG:4326", grid["crs"]).transform(lon, lat)
    return (grid["top"] - y) / grid["res"] - 0.5, (x - grid["left"]) / grid["res"] - 0.5


def _folders(folder: str) -> Tuple[str, str]:
    """(cluster folder, capture folder) of either."""
    folder = os.path.abspath(folder)
    if os.path.exists(os.path.join(folder, "grid.json")) and os.path.basename(folder) == "capture":
        return os.path.dirname(folder), folder
    return folder, os.path.join(folder, "capture")


def load_known(cluster_folder: str) -> List[KnownLine]:
    path = os.path.join(cluster_folder, "known.json")
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [KnownLine.from_dict(d) for d in json.load(f)]


def capture_status(cluster_folder: str) -> Optional[str]:
    path = os.path.join(cluster_folder, "capture.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f).get("status")


def load_capture(folder: str) -> Capture:
    """A cluster's capture (the cluster folder or its capture/ folder): grid.json and grids.npz are
    needed (FileNotFoundError otherwise); without anchors.npy no anchors, without lines.npz no lines
    (a search that stopped at "not enough steep terrain" or found none)."""
    cluster_folder, cap = _folders(folder)
    with open(os.path.join(cap, "grid.json"), encoding="utf-8") as f:
        grid = json.load(f)
    with np.load(os.path.join(cap, "grids.npz")) as g:
        grids = {k: g[k] for k in g.files}
    elevation = grids["elevation"]
    as_mask = lambda k: grids[k].astype(bool) if k in grids else None  # noqa: E731
    mask = as_mask("mask")
    if mask is None:
        mask = np.ones(elevation.shape, dtype=bool)
    path = os.path.join(cap, "anchors.npy")
    anchors = np.load(path).astype(np.int64).reshape(-1, 2) if os.path.exists(path) else np.zeros((0, 2), np.int64)
    found = load_found(os.path.join(cap, "lines.npz"), grid)
    return Capture(folder=cluster_folder, cluster=os.path.basename(cluster_folder), grid=grid, elevation=elevation,
                   surface=grids.get("surface"), filled=as_mask("filled"), joined=as_mask("joined"),
                   water=as_mask("water"), mask=mask, anchors=np.ascontiguousarray(anchors), found=found,
                   known=load_known(cluster_folder), status=capture_status(cluster_folder))


def load_found(path: str, grid: Dict) -> FoundLines:
    """lines.npz as FoundLines (empty when missing); absent columns: clearance_nmpt NaN, over False,
    every line a representative of its own group."""
    data = {}
    if os.path.exists(path):
        with np.load(path) as f:
            data = {k: f[k] for k in f.files}
    a1 = np.asarray(data.get("a1", np.zeros((0, 2))), dtype=np.float64).reshape(-1, 2)
    a2 = np.asarray(data.get("a2", np.zeros((0, 2))), dtype=np.float64).reshape(-1, 2)
    n = len(a1)
    def column(k, default, dtype):
        return np.asarray(data[k], dtype=dtype) if k in data else np.full(n, default, dtype)

    return FoundLines(a1=a1, a2=a2, length=column("length", np.nan, np.float64),
                      clearance=column("clearance", np.nan, np.float64),
                      clearance_nmpt=column("clearance_nmpt", np.nan, np.float64),
                      over=column("over", False, bool), rep=column("rep", True, bool),
                      group=np.asarray(data["group"], dtype=np.int64) if "group" in data else np.arange(n),
                      xy1=_xy(grid, a1), xy2=_xy(grid, a2))


# ---------------------------------------------------------------------------------------------
# matching

def tolerance(line: KnownLine) -> float:
    """max(TOL_M, TOL_SHARE * L) metres, raised to the coordinate quantum for coarse anchors."""
    tol = max(TOL_M, TOL_SHARE * line.length_m)
    if "coarse_anchor" in line.flags:
        tol = max(tol, QUANTUM_M * 10.0 ** -line.decimals)
    return float(tol)


def doubtful(line: KnownLine) -> bool:
    """A geometry that cannot verify a miss (DOUBTFUL flags)."""
    return any(flag in line.flags for flag in DOUBTFUL)


def _distances(a: np.ndarray, b: np.ndarray, tol: float, found: FoundLines) -> np.ndarray:
    """The anchor-distance sum of each found line with both anchors within tol of (a, b), either way
    round (the smaller sum of the orientations that fit), inf for the others."""
    if not len(found):
        return np.zeros(0)
    d11, d22 = np.hypot(*(found.xy1 - a).T), np.hypot(*(found.xy2 - b).T)
    d12, d21 = np.hypot(*(found.xy1 - b).T), np.hypot(*(found.xy2 - a).T)
    straight = np.where((d11 <= tol) & (d22 <= tol), d11 + d22, np.inf)
    crossed = np.where((d12 <= tol) & (d21 <= tol), d12 + d21, np.inf)
    return np.minimum(straight, crossed)


def match(known: List[KnownLine], found: FoundLines, grid: Dict) -> List[Optional[int]]:
    """The index of each known line's found line (None: no match): coverage_contrast.matched with each
    line's tolerance decides, the smallest anchor-distance sum chooses (the lowest index of a tie)."""
    import coverage_contrast
    if not known:
        return []
    ka, kb = _xy(grid, [k.a for k in known]), _xy(grid, [k.b for k in known])
    tol = np.array([tolerance(k) for k in known])
    ok = coverage_contrast.matched(ka, kb, found.xy1, found.xy2, tol)
    out = []
    for k in range(len(known)):
        sums = _distances(ka[k], kb[k], tol[k], found) if ok[k] else np.zeros(0)
        out.append(int(np.argmin(sums)) if len(sums) and np.isfinite(sums).any() else None)
    return out


def near_known(known: List[KnownLine], found: FoundLines, grid: Dict) -> np.ndarray:
    """Which found lines have a known line of a good geometry within its tolerance (either way round):
    the found spots holding none are the precision proxy."""
    near = np.zeros(len(found), dtype=bool)
    for line in known:
        if doubtful(line):
            continue
        a, b = _xy(grid, [line.a])[0], _xy(grid, [line.b])[0]
        near |= np.isfinite(_distances(a, b, tolerance(line), found))
    return near


def length_bin(length: float) -> str:
    """SlackMap's length bin of a length (LENGTH_EDGES): "0-30" ... "500+"."""
    edges = LENGTH_EDGES
    for lo, hi in zip(edges, edges[1:]):
        if length < hi:
            return f"{lo}-{hi}"
    return f"{edges[-1]}+"


# ---------------------------------------------------------------------------------------------
# diagnosis

def _value(array: Optional[np.ndarray], pixel) -> Optional[float]:
    """array[pixel] as a float, None outside the grid, without the array or for NaN."""
    if array is None:
        return None
    r, c = pixel
    if not (0 <= r < array.shape[0] and 0 <= c < array.shape[1]):
        return None
    v = float(array[r, c])
    return v if math.isfinite(v) else None


def _flag(mask: Optional[np.ndarray], pixel) -> bool:
    r, c = pixel
    return bool(mask is not None and 0 <= r < mask.shape[0] and 0 <= c < mask.shape[1] and mask[r, c])


def _seams(c: Capture, pixels: np.ndarray) -> np.ndarray:
    """Which pixels lie at a seam of the filled gaps or of a neighbour's data (search.at_seams)."""
    out = np.zeros(len(pixels), dtype=bool)
    if not len(pixels):
        return out
    import search
    for seams in (c.filled, c.joined):
        if seams is not None:
            out |= search.at_seams(seams, pixels)
    return out


def _canopy(c: Capture, pixel) -> Optional[float]:
    """surface - terrain at a pixel (metres; None without a surface or data)."""
    s, z = _value(c.surface, pixel), _value(c.elevation, pixel)
    return None if s is None or z is None else s - z


def _end(c: Capture, point: Tuple[float, float], tol: float) -> Tuple[Dict, np.ndarray, np.ndarray]:
    """One known end: its record entry (see the module docstring), and the anchors within tol (at most
    MAX_END_ANCHORS, the nearest first) with their distances in metres."""
    lat, lon = point
    row, col = _pixel_float(c.grid, lat, lon)
    pixel = studylib.to_pixel(c.grid, lat, lon)
    h, w = c.elevation.shape
    in_grid = 0 <= pixel[0] < h and 0 <= pixel[1] < w
    radius = min(tol, ENDS_MAX_M)
    entry = {"pixel": [int(pixel[0]), int(pixel[1])], "inside": bool(in_grid and c.mask[pixel]),
             "z": _value(c.elevation, pixel), "slope": _value(c.slope, pixel) if in_grid else None,
             "radius": radius}
    k = radius / c.res
    r0, r1 = max(0, int(math.floor(row - k))), min(h, int(math.ceil(row + k)) + 1)
    c0, c1 = max(0, int(math.floor(col - k))), min(w, int(math.ceil(col + k)) + 1)
    if r0 < r1 and c0 < c1:
        rr, cc = np.mgrid[r0:r1, c0:c1]
        d = np.hypot(rr - row, cc - col) * c.res
        near = d <= radius
        rr, cc, d = rr[near], cc[near], d[near]
    else:
        rr = cc = np.zeros(0, dtype=np.intp)
        d = np.zeros(0)
    slope = c.slope[rr, cc] if len(rr) else np.zeros(0, dtype=np.float32)
    usable = c.mask[rr, cc] if len(rr) else np.zeros(0, dtype=bool)  # NaN slopes compare False below
    for thr in THRESHOLDS:
        hit = usable & (slope >= thr)
        entry[f"{thr:g}"] = float(d[hit].min()) if hit.any() else None
    steep = usable & (slope >= c.threshold)  # the search's anchors before its other filters
    entry["steep"] = bool(steep.any())
    entry["steep_m"] = float(d[steep].min()) if steep.any() else None
    entry["steep_at_seam"] = int(_seams(c, np.column_stack([rr[steep], cc[steep]]).astype(np.int64)).sum())
    if c.tree is not None:
        idx = np.asarray(c.tree.query_ball_point([row, col], radius / c.res + 1e-9), dtype=np.int64)
    else:
        idx = np.zeros(0, dtype=np.int64)
    pa = c.anchors[idx] if len(idx) else np.zeros((0, 2), dtype=np.int64)
    da = np.hypot(pa[:, 0] - row, pa[:, 1] - col) * c.res
    keep = da <= radius
    pa, da = pa[keep], da[keep]
    order = np.lexsort((pa[:, 1], pa[:, 0], da))[:MAX_END_ANCHORS] if len(pa) else np.zeros(0, dtype=np.intp)
    pa, da = pa[order], da[order]
    entry["anchors"] = int(keep.sum())
    entry["anchor_within"] = float(da[0]) if len(da) else None
    entry.update(filled=_flag(c.filled, pixel), joined=_flag(c.joined, pixel), water=_flag(c.water, pixel),
                 at_seam=bool(in_grid and _seams(c, np.array([pixel], dtype=np.int64))[0]),
                 canopy=_canopy(c, pixel) if in_grid else None)
    return entry, pa, da


def _first_failure(c: Capture, lo, hi) -> Optional[Dict]:
    """The first failing step from each end of the line lo -> hi by the run's rule (the decision values
    of helpers.end_zone_rule; NaN fails), and whether it lies near an end; None when every step passes."""
    m = studylib.margins(c.elevation, lo, hi, c.res, c.sag_table)
    if m is None:
        return None
    terrain, _, steps, length = m
    p = c.params
    end_zone, lift = float(p.get("end_zone", 0) or 0), float(p.get("anchor_lift", 0) or 0)
    offsets = sh.zone_offsets(steps, length, end_zone, lift, c.fall)
    fails = np.flatnonzero(~(sh.decision_values(terrain, offsets) > 0))
    if not len(fails):
        return None
    first, last = int(fails[0]) + 1, int(fails[-1]) + 1
    from_a1, from_a2 = first * length / steps, (steps - last) * length / steps
    return {"from_a1": from_a1, "from_a2": from_a2, "near_m": max(NEAR_M, NEAR_SHARE * length),
            "near": bool(min(from_a1, from_a2) <= max(NEAR_M, NEAR_SHARE * length))}


def _evaluate(c: Capture, lo, hi):
    """helpers.evaluate_line of the pair with the run's surface, model, end zone and lift."""
    p = c.params
    with warnings.catch_warnings():  # np.nanmin's "All-NaN slice" where an anchor has no data: NaN fails anyway
        warnings.simplefilter("ignore", RuntimeWarning)
        return sh.evaluate_line(lo, hi, c.elevation, c.res, c.surface if c.nmpt else None, c.sag_table,
                                float(p.get("high_above", sh.HIGH_ABOVE)),
                                end_zone=float(p.get("end_zone", 0) or 0), lift=float(p.get("anchor_lift", 0) or 0))


def _limits_pass(c: Capture, result) -> bool:
    """The search's height limits (helpers.LineLimits but the wall angle) on an evaluated line."""
    p = c.params
    checks = (("min_height", result[5]), ("min_mean_height", result[6]), ("min_high_share", result[7]))
    return all(p.get(k) is None or v >= p[k] for k, v in checks)


def _pair_detail(c: Capture, lo, hi, stage: str, d_known: Sequence[float]) -> Dict:
    """The funnel's best pair: end_zone_study.line_detail plus the rule's and the surface's clearance,
    the wall angles, the height difference against its limit, the first failure by the rule and the
    distances of the pair's pixels to the known ends (a, b)."""
    import end_zone_study as ezs
    lo, hi = [int(v) for v in lo], [int(v) for v in hi]
    detail = ezs.line_detail(c.namespace, lo, hi, ezs.ZONES, ezs.CAP, c.fall)
    result = _evaluate(c, lo, hi)
    down = sh.downslope(c.elevation, np.array([lo, hi]), c.res)
    a1, a2 = sh.wall_angles(np.array([lo]), np.array([hi]), down[:1], down[1:])
    p = c.params
    limit = min(float(p.get("max_anchor_diff", np.inf)) / 100 * detail["length"],
                float(p.get("max_anchor_diff_m") if p.get("max_anchor_diff_m") is not None else np.inf))
    detail.update(stage=stage, clearance_rule=None if result is None else result[3],
                  clearance_nmpt=None if result is None else result[4], angles=[float(a1[0]), float(a2[0])],
                  dh_limit=limit, d_known=[float(v) for v in d_known], rule_failure=_first_failure(c, lo, hi),
                  wgs84=studylib.pixels_wgs84(c.grid, [lo, hi]))
    return detail


def _funnel(c: Capture, ends: Sequence[Tuple[np.ndarray, np.ndarray]]
            ) -> Tuple[Dict, Optional[Dict], str, Optional[str]]:
    """The anchor pairs of the two ends through the search's tests (the module docstring): the counts,
    the best pair of the last stage reached, the reason and a note."""
    (pa, da), (pb, db) = ends
    p = c.params
    i, j = np.meshgrid(np.arange(len(pa)), np.arange(len(pb)), indexing="ij")
    i, j = i.ravel(), j.ravel()
    differ = np.any(pa[i] != pb[j], axis=1)
    i, j = i[differ], j[differ]
    p1, p2 = pa[i], pb[j]
    first = (p1[:, 0] < p2[:, 0]) | ((p1[:, 0] == p2[:, 0]) & (p1[:, 1] < p2[:, 1]))  # row-major: the search's order
    lo, hi = np.where(first[:, None], p1, p2), np.where(first[:, None], p2, p1)
    dsum = da[i] + db[j]
    length = np.hypot(*(hi - lo).T.astype(np.float64)) * c.res
    counts = {"pairs": int(len(i))}
    in_range = (length >= float(p.get("min_length", 0))) & (length <= float(p.get("max_length", np.inf)))
    counts["length"] = int(in_range.sum())

    def detail(k, stage):
        return _pair_detail(c, lo[k], hi[k], stage, (da[i[k]], db[j[k]]))

    if not in_range.any():
        k = int(np.argmin(dsum)) if len(dsum) else None
        return counts, None if k is None else detail(k, "length"), "unexplained", "length_range"
    z = c.elevation
    dh = np.abs(z[hi[:, 0], hi[:, 1]] - z[lo[:, 0], lo[:, 1]])
    max_dh = p.get("max_anchor_diff_m")
    limit = np.minimum(float(p.get("max_anchor_diff", np.inf)) / 100 * length,
                       float(max_dh) if max_dh is not None else np.inf)
    height = in_range & (dh <= limit)
    counts["height"] = int(height.sum())
    if not height.any():
        excess = np.where(in_range, dh - limit, np.inf)
        excess = np.where(np.isnan(excess), np.inf, excess)
        return counts, detail(int(np.argmin(excess)), "height"), "height_difference", None
    rows = np.flatnonzero(height)
    rows = rows[np.argsort(dsum[rows], kind="stable")]
    counts["capped"] = bool(len(rows) > MAX_PAIRS)
    rows = rows[:MAX_PAIRS]
    counts["evaluated"] = int(len(rows))
    results = [_evaluate(c, lo[k], hi[k]) for k in rows]
    valid = np.array([r is not None for r in results])
    rows, results = rows[valid], [r for r in results if r is not None]
    clearance = np.array([r[3] for r in results], dtype=np.float64)
    terrain = clearance > 0
    counts["terrain"] = int(terrain.sum())
    if not terrain.any():
        k = int(rows[np.argmax(np.where(np.isnan(clearance), -np.inf, clearance))]) if len(rows) else None
        if k is None:
            return counts, None, "unexplained", "no_pixel_between"
        best = detail(k, "terrain")
        failure = best["rule_failure"]
        return counts, best, "clearance_near_anchor" if failure and failure["near"] else "clearance_mid", None
    nmpt = np.array([np.nan if r[4] is None else r[4] for r in results], dtype=np.float64)
    surface = terrain.copy()
    if c.nmpt == "reject":  # helpers.is_valid: a surface without data at every pixel (None, NaN here) passes
        surface &= np.isnan(nmpt) | (nmpt > 0)
    counts["surface"] = int(surface.sum())
    if not surface.any():
        k = int(rows[np.argmax(np.where(terrain & ~np.isnan(nmpt), nmpt, -np.inf))])
        return counts, detail(k, "surface"), "surface_obstacle", None
    down = sh.downslope(z, np.vstack([lo[rows], hi[rows]]), c.res)
    a1, a2 = sh.wall_angles(lo[rows], hi[rows], down[:len(rows)], down[len(rows):])
    wall_max = np.where(a2 > a1, a2, a1)
    wall = surface.copy()
    if p.get("max_wall_angle") is not None:
        wall &= wall_max <= float(p["max_wall_angle"])
    counts["wall"] = int(wall.sum())
    if not wall.any():
        k = int(rows[np.argmin(np.where(surface, wall_max, np.inf))])
        return counts, detail(k, "wall"), "wall_angle", None
    limits = wall & np.array([_limits_pass(c, r) for r in results])
    counts["limits"] = int(limits.sum())
    last = limits if limits.any() else wall
    k = int(rows[np.argmax(np.where(last, clearance, -np.inf))])
    note = "a_pair_passes" if limits.any() else "height_limits"
    if limits.any() and p.get("min_prominence") is not None:
        note += "; min_prominence set: the strong anchors are not in the capture"
    return counts, detail(k, "limits" if limits.any() else "wall"), "unexplained", note


def _filter_hint(c: Capture, entries: Sequence[Dict]) -> str:
    """What may have left out a steep end's anchors: the elevation band, the prominence or the drop."""
    p, hints = c.params, []
    for e in entries:
        z = e.get("z")
        if z is not None and ((p.get("min_elevation") is not None and z < p["min_elevation"]) or
                              (p.get("max_elevation") is not None and z > p["max_elevation"])):
            hints.append("elevation band")
    hints += [name for name in ("min_prominence_both", "min_drop") if p.get(name) is not None]
    return ", ".join(dict.fromkeys(hints)) or "none of the band, prominence or drop limits set"


def _which(flags: Sequence[bool]) -> Optional[str]:
    return {(True, False): "a", (False, True): "b", (True, True): "both"}.get(tuple(bool(f) for f in flags))


def _exact(c: Capture, ends: Sequence[Dict]) -> Optional[Dict]:
    """helpers.evaluate_line between the two end pixels (None when one lies outside the grid)."""
    h, w = c.elevation.shape
    pixels = [tuple(e["pixel"]) for e in ends]
    if not all(0 <= r < h and 0 <= col < w for r, col in pixels):
        return None
    lo, hi = sorted(pixels)
    result = _evaluate(c, lo, hi)
    if result is None:
        return None
    return {"a1": list(lo), "a2": list(hi), "length": result[2], "clearance": result[3],
            "clearance_nmpt": result[4], "dh": result[1] - result[0], "valid": sh.is_valid(result, c.nmpt)}


def _near(c: Capture, line: KnownLine) -> Optional[Dict]:
    """end_zone_study.diagnose_line within NEAR_PX pixels of the known ends: the best pair of any pixels
    there (today's strict rule) and the lift each ladder zone needs."""
    import end_zone_study as ezs
    ends = [studylib.to_pixel(c.grid, *line.a), studylib.to_pixel(c.grid, *line.b)]
    anchors = set()
    if c.tree is not None:  # the anchors near the ends: the only ones diagnose_line asks about
        for e in ends:
            anchors |= set(map(tuple, c.anchors[c.tree.query_ball_point(e, NEAR_PX + 1)].tolist()))
    result = ezs.diagnose_line(c.namespace, c.slope, anchors, {"name": line.id, "a": list(line.a), "b": list(line.b)},
                               NEAR_PX * c.res, ezs.ZONES, ezs.CAP, 0.0, (c.threshold,))
    return {k: result[k] for k in ("pixels", "best", "staircase", "error") if k in result}


def _match_detail(c: Capture, line: KnownLine, k: int) -> Dict:
    """What a match records of its found line (the module docstring), in the known line's order (a, b)."""
    f = c.found
    a, b = _xy(c.grid, [line.a])[0], _xy(c.grid, [line.b])[0]
    d11, d22 = np.hypot(*(f.xy1[k] - a)), np.hypot(*(f.xy2[k] - b))
    d12, d21 = np.hypot(*(f.xy1[k] - b)), np.hypot(*(f.xy2[k] - a))
    swapped = bool(d12 + d21 < d11 + d22)
    p1, p2 = studylib.to_pixel(c.grid, *f.a1[k]), studylib.to_pixel(c.grid, *f.a2[k])
    down = sh.downslope(c.elevation, np.array([p1, p2]), c.res)
    g1, g2 = sh.wall_angles(np.array([p1]), np.array([p2]), down[:1], down[1:])
    angles, canopy = [float(g1[0]), float(g2[0])], [_canopy(c, p1), _canopy(c, p2)]
    if swapped:  # the known a is the found a2
        angles, canopy = angles[::-1], canopy[::-1]
    nmpt = float(f.clearance_nmpt[k])
    return {"index": int(k), "length": float(f.length[k]), "clearance": float(f.clearance[k]),
            "clearance_nmpt": nmpt if math.isfinite(nmpt) else None, "over": bool(f.over[k]),
            "rep": bool(f.rep[k]), "group": int(f.group[k]), "swapped": swapped,
            "d": [float(d21), float(d12)] if swapped else [float(d11), float(d22)],
            "angles": angles, "wall": max(angles), "canopy": canopy,
            "pixels": [list(p2), list(p1)] if swapped else [list(p1), list(p2)]}


def diagnose(capture: Capture, line: KnownLine, found_index: Optional[int]) -> Dict:
    """One known line's record (the module docstring): the match, or the miss with its reason."""
    c = capture
    tol = tolerance(line)
    record = {"id": line.id, "type": line.type, "country": line.country, "cluster": c.cluster, "source": c.source,
              "resolution": c.res, "length_m": line.length_m, "stated_m": line.stated_m, "geodesic_m": line.geodesic_m,
              "decimals": line.decimals, "flags": list(line.flags), "doubtful": doubtful(line),
              "bin": length_bin(line.length_m), "tol": tol,
              "outcome": "matched" if found_index is not None else "missed",
              "verifiable": True, "reason": None, "which": None, "note": None, "match": None, "ends": [],
              "funnel": None, "best": None, "near": None, "exact": None, "canopy": [None, None]}
    ea, pa, da = _end(c, line.a, tol)
    eb, pb, db = _end(c, line.b, tol)
    ends = [ea, eb]
    record["ends"] = ends
    record["exact"] = _exact(c, ends)
    if found_index is not None:
        record["match"] = _match_detail(c, line, found_index)
        record["canopy"] = record["match"]["canopy"]
        return record
    record["canopy"] = [ea["canopy"], eb["canopy"]]
    if doubtful(line):
        record.update(reason="unverifiable", verifiable=False)
        return record
    outside = [not e["inside"] for e in ends]
    if any(outside):
        record.update(reason="outside_area", which=_which(outside))
        return record
    nodata = [e["z"] is None for e in ends]
    if any(nodata):
        record.update(reason="no_data", which=_which(nodata))
        return record
    record["near"] = _near(c, line)
    bare = [e["anchors"] == 0 for e in ends]
    if any(bare):
        lacking = [e for e, b in zip(ends, bare) if b]
        if any(e["steep_at_seam"] for e in lacking):
            record.update(reason="seam_pixel", which=_which([b and e["steep_at_seam"] > 0 for e, b in zip(ends, bare)]))
        elif any(e["water"] for e in lacking):
            record.update(reason="water_pixel", which=_which([b and e["water"] for e, b in zip(ends, bare)]))
        elif any(not e["steep"] for e in lacking):
            record.update(reason="no_steep_pixel", which=_which([b and not e["steep"] for e, b in zip(ends, bare)]))
        else:
            record.update(reason="anchor_filtered", which=_which(bare), note=_filter_hint(c, lacking))
        return record
    counts, best, reason, note = _funnel(c, [(pa, da), (pb, db)])
    record.update(funnel=counts, best=best, reason=reason, note=note)
    return record


# ---------------------------------------------------------------------------------------------
# --profiles: production's verdict of the known pair

def profile_verdict(profile: Dict, nmpt: Optional[str]) -> bool:
    """helpers.is_valid on a profile of search.profile_of_line (its rounded clearances): the terrain's
    smallest clearance above 0, and under "reject" the surface's too (when it has one)."""
    if not profile["min"][1] > 0:
        return False
    return not (nmpt == "reject" and profile.get("min_nmpt") is not None and not profile["min_nmpt"][1] > 0)


def grid_verdict(exact: Optional[Dict], nmpt: Optional[str]) -> Optional[bool]:
    """The same verdict from the captured grid's exact pair (its clearances rounded as a profile's)."""
    if exact is None or exact["clearance"] is None or not math.isfinite(exact["clearance"]):
        return None if exact is None else False
    if not round(exact["clearance"], 2) > 0:
        return False
    s = exact.get("clearance_nmpt")
    return not (nmpt == "reject" and s is not None and not round(s, 2) > 0)


def profile_check(c: Capture, line: KnownLine, record: Dict, data: str) -> Dict:
    """search.profile_of_line of the known pair (a meta from grid.json, the cluster's data folder `data`
    with its cache) against the grid's verdict of the same pair."""
    import search
    meta = {"params": c.params, "center": {"crs": c.grid["crs"]}, "source": {"id": c.source},
            "data": (c.grid.get("layer_meta") or {}).get("data", [])}
    work = os.path.join(c.folder, "profile-work")
    os.makedirs(work, exist_ok=True)
    try:
        with contextlib.redirect_stdout(io.StringIO()):  # the messages of building the grids
            profile = search.profile_of_line(meta, search.Paths(data, work), tuple(line.a), tuple(line.b))
    except Exception as e:  # SearchError (too far, too close, another CRS), a source without data, ...
        return {"error": f"{type(e).__name__}: {e}"}
    finally:
        shutil.rmtree(work, ignore_errors=True)
    production, grid = profile_verdict(profile, c.nmpt), grid_verdict(record.get("exact"), c.nmpt)
    return {"production": production, "grid": grid, "agree": grid is not None and production == grid,
            "clearance": profile["min"][1], "clearance_nmpt": (profile.get("min_nmpt") or [None, None])[1]}


@contextlib.contextmanager
def _profile_data(c: Capture, cache_dir: Optional[str]):
    """The cluster's data folder for profile_of_line: its own cache when it has a real one, else one
    linked to cache_dir (studylib.linked_data_folder, the link removed afterwards)."""
    own = os.path.join(c.folder, "data", "cache")
    if os.path.isdir(own) and not os.path.islink(own) and not \
            (hasattr(os.path, "isjunction") and os.path.isjunction(own)):
        yield os.path.join(c.folder, "data")
        return
    with studylib.linked_data_folder(c.folder, cache_dir) as data:
        yield data


# ---------------------------------------------------------------------------------------------
# analyse

def _plain(value):
    """JSON's values: numpy scalars as Python's, NaN and infinities as None."""
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    if isinstance(value, np.ndarray):
        return _plain(value.tolist())
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        return float(value) if math.isfinite(value) else None
    return value


def _write_json(path: str, data) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(_plain(data), f, ensure_ascii=False, indent=1)


def cluster_folders(out: str, clusters: Optional[Sequence[str]] = None) -> List[str]:
    """The clusters' folders under out (those with a known.json or a capture/), sorted, or the named ones."""
    out = os.path.abspath(out)
    if clusters:
        return [os.path.join(out, name) for name in clusters]
    return sorted(f for f in glob.glob(os.path.join(out, "*")) if os.path.isdir(f) and (
        os.path.exists(os.path.join(f, "known.json")) or os.path.isdir(os.path.join(f, "capture"))))


def analyse_cluster(folder: str, profiles: bool = False, cache_dir: Optional[str] = None) -> Dict:
    """One cluster: its records and summary, written to <folder>/analysis.json."""
    name = os.path.basename(os.path.normpath(folder))
    status = capture_status(folder)
    try:
        if status == "failed":
            raise RuntimeError("the search failed (capture.json)")
        c = load_capture(folder)
    except (FileNotFoundError, OSError, KeyError, RuntimeError, ValueError) as e:
        known = load_known(folder)
        result = {"cluster": name, "status": status or "failed", "analysed": False, "error": str(e),
                  "known": len(known), "known_by_type": dict(collections.Counter(k.type for k in known)),
                  "records": []}
        _write_json(os.path.join(folder, "analysis.json"), result)
        return result
    index = match(c.known, c.found, c.grid)
    records = [diagnose(c, line, k) for line, k in zip(c.known, index)]
    if profiles:
        candidates = [(line, r) for line, r in zip(c.known, records)
                      if r["verifiable"] and r["reason"] not in ("outside_area", "no_data")]
        if candidates:
            with _profile_data(c, cache_dir) as data:
                for line, r in candidates:
                    r["profile"] = profile_check(c, line, r, data)
    near = near_known(c.known, c.found, c.grid)
    groups = np.unique(c.found.group)
    with_known = np.unique(c.found.group[near]) if near.any() else np.zeros(0, dtype=np.int64)
    result = {"cluster": name, "status": c.status or "done", "analysed": True, "source": c.source,
              "resolution": c.res, "crs": c.grid["crs"], "model": c.grid.get("model", c.params.get("model")),
              "nmpt": c.nmpt, "slope_threshold": c.threshold, "anchors": int(len(c.anchors)),
              "found_lines": int(len(c.found)), "found_spots": int(len(groups)),
              "spots_without_known": int(len(groups) - len(with_known)), "known": len(c.known),
              "matched": int(sum(k is not None for k in index)), "records": records}
    _write_json(os.path.join(folder, "analysis.json"), result)
    return result


def analyse(out: str, profiles: bool = False, clusters: Optional[Sequence[str]] = None,
            cache_dir: Optional[str] = None) -> Dict:
    """Every cluster's capture (or the named ones) -> <out>/<cluster>/analysis.json, then <out>/analysis.json
    of every cluster analysed so far (the summaries and all records). cache_dir: the cache --profiles
    links into a cluster's data folder (default: the data folder's, cache.data_dir())."""
    if profiles and cache_dir is None:
        import cache
        cache_dir = os.path.join(cache.data_dir(), "cache")
    for folder in cluster_folders(out, clusters):
        r = analyse_cluster(folder, profiles, cache_dir)
        if r["analysed"]:
            print(f"{r['cluster']}: {r['matched']} of {r['known']} known lines matched, {r['found_lines']} lines found",
                  flush=True)
        else:
            print(f"{r['cluster']}: not analysed ({r['error']})", flush=True)
    summaries, records = [], []
    for folder in cluster_folders(out):
        path = os.path.join(folder, "analysis.json")
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        records += data.pop("records")
        summaries.append(data)
    result = {"clusters": summaries, "records": records}
    _write_json(os.path.join(os.path.abspath(out), "analysis.json"), result)
    return result


# ---------------------------------------------------------------------------------------------
# report

def _quantiles(values: Sequence[float]) -> Optional[List[float]]:
    values = [v for v in values if v is not None and math.isfinite(v)]
    return [round(float(q), 2) for q in np.percentile(values, [10, 50, 90])] if values else None


def stats(records: Sequence[Dict]) -> Dict:
    """Counts, recall, reasons and the matched lines' quantiles of some records."""
    matched = [r for r in records if r["outcome"] == "matched"]
    verifiable = sum(bool(r["verifiable"]) for r in records)
    clean = [r for r in records if not r["doubtful"]]
    clean_matched = sum(r["outcome"] == "matched" for r in clean)
    reasons = collections.Counter(r["reason"] for r in records if r["outcome"] == "missed")
    over = [r["match"]["over"] for r in matched]
    return {"known": len(records), "verifiable": verifiable, "matched": len(matched),
            "recall": round(len(matched) / verifiable, 4) if verifiable else None,
            "known_clean": len(clean), "matched_clean": clean_matched,
            "recall_clean": round(clean_matched / len(clean), 4) if clean else None,
            "matched_doubtful": sum(r["doubtful"] for r in matched),
            "reasons": {k: reasons.get(k, 0) for k in REASONS},
            "clearance": _quantiles([r["match"]["clearance"] for r in matched]),
            "over_trees": round(sum(over) / len(over), 4) if over else None,
            "wall_angle": _quantiles([r["match"]["wall"] for r in matched])}


def types_of(records: Sequence[Dict]) -> List[str]:
    return list(REPORT_TYPES) + sorted({r["type"] for r in records} - set(REPORT_TYPES))


def by_type(records: Sequence[Dict], types: Sequence[str]) -> Dict:
    """stats of all the records and of each type's."""
    return {"all": stats(records), **{t: stats([r for r in records if r["type"] == t]) for t in types}}


def _key(dimension: str, record: Dict) -> str:
    if dimension == "country":
        return record["country"] or "?"
    if dimension == "source":
        return record["source"] or "?"
    if dimension == "length":
        return record["bin"]
    return f"{record['resolution']:g} m"


def _order(dimension: str, groups: Dict[str, list]) -> List[str]:
    if dimension == "length":
        bins = [length_bin(lo) for lo in LENGTH_EDGES]
        return [b for b in bins if b in groups]
    if dimension == "resolution":
        return sorted(groups, key=lambda k: float(k.split()[0]))
    return sorted(groups, key=lambda k: (-len(groups[k]), k))


DIMENSIONS = ("country", "source", "length", "resolution")


def _pct(v: Optional[float]) -> str:
    return "-" if v is None else f"{100 * v:.0f}%"


def _num(v, digits=1) -> str:
    if v is None or (isinstance(v, float) and not math.isfinite(v)):
        return "-"
    return f"{v:.{digits}f}" if isinstance(v, float) else str(v)


def _cell(s: Dict, key: str, types: Sequence[str], pct: bool = False) -> str:
    """A table cell: the total, then each type's in parentheses ("12 (10 / 2)")."""
    fmt = _pct if pct else str
    return f"{fmt(s['all'][key])} (" + " / ".join(fmt(s[t][key]) for t in types) + ")"


def _reason_cell(s: Dict, reason: str, types: Sequence[str]) -> str:
    return f"{s['all']['reasons'][reason]} (" + " / ".join(str(s[t]['reasons'][reason]) for t in types) + ")"


def _miss_line(n: int, r: Dict) -> str:
    """One miss of a place's list."""
    text = (f"- #{n} `{r['id']}` ({r['type']}, {r['length_m']:.0f} m, tol {r['tol']:.0f} m): **{r['reason']}**"
            + (f" ({r['which']})" if r.get("which") else "") + (f"; {r['note']}" if r.get("note") else ""))
    b = r.get("best")
    if b:
        text += f"; best pair {b['length']:.1f} m, height difference {abs(b['dh']):.1f} m (limit {_num(b['dh_limit'])})"
        text += f", clearance {_num(b['clearance_rule'], 2)} m"
        if b.get("clearance_nmpt") is not None:
            text += f", over the surface {_num(b['clearance_nmpt'], 2)} m"
        if b.get("rule_failure"):
            f = b["rule_failure"]
            text += f", first failure {f['from_a1']:.1f} / {f['from_a2']:.1f} m from the ends"
        text += f", wall angles {_num(b['angles'][0], 0)} / {_num(b['angles'][1], 0)} deg"
        text += "; lift needed " + ", ".join(f"zone {s['zone']:g} m: {_num(s['lift'])} m" for s in b["staircase"])
    elif r.get("ends"):
        parts = []
        for side, e in zip("ab", r["ends"]):
            parts.append(f"{side}: slope {_num(e.get('slope'))} deg, steep pixel {_num(e.get('steep_m'))} m, "
                         f"anchor {_num(e.get('anchor_within'))} m")
        text += "; " + "; ".join(parts)
    if r.get("exact") and r["exact"].get("clearance") is not None:
        text += f"; the known pair itself: clearance {_num(r['exact']['clearance'], 2)} m"
    if r.get("profile"):
        p = r["profile"]
        text += (f"; profile: {p['error']}" if "error" in p else
                 f"; profile {'valid' if p['production'] else 'not valid'} ({'agrees' if p['agree'] else 'DISAGREES'})")
    return text


def report(out: str, pictures: bool = True) -> str:
    """<out>/study.json, study.md and pictures/ from <out>/analysis.json (analyse first); returns study.md's text."""
    out = os.path.abspath(out)
    path = os.path.join(out, "analysis.json")
    if not os.path.exists(path):
        raise FileNotFoundError(f"{path} is missing: run analyse first")
    with open(path, encoding="utf-8") as f:
        analysis = json.load(f)
    records, clusters = analysis["records"], analysis["clusters"]
    types = types_of(records)
    analysed = [s for s in clusters if s.get("analysed")]
    failed = [s for s in clusters if not s.get("analysed")]
    by = {}
    for dimension in DIMENSIONS:
        groups = collections.defaultdict(list)
        for r in records:
            groups[_key(dimension, r)].append(r)
        by[dimension] = {k: by_type(groups[k], types) for k in _order(dimension, groups)}
    overall = by_type(records, types)
    checked = [r["profile"] for r in records if r.get("profile")]
    profile_counts = {"checked": len(checked), "agree": sum(bool(p.get("agree")) for p in checked),
                      "disagree": sum("error" not in p and not p.get("agree") for p in checked),
                      "errors": sum("error" in p for p in checked)} if checked else None
    made = []
    if pictures:
        made = draw(out, analysis)
    study = {"generated": datetime.date.today().isoformat(), "reasons": list(REASONS), "types": types,
             "tolerance": {"floor_m": TOL_M, "share": TOL_SHARE, "quantum_m": QUANTUM_M},
             "overall": overall, "by": by, "places": analysed, "failed": failed, "profiles": profile_counts,
             "pictures": [os.path.relpath(p, out).replace(os.sep, "/") for p in made]}
    _write_json(os.path.join(out, "study.json"), study)
    text = "\n".join(markdown(study, records, made, out))
    with open(os.path.join(out, "study.md"), "w", encoding="utf-8") as f:
        f.write(text)
    return text


def markdown(study: Dict, records: Sequence[Dict], made: Sequence[str], out: str) -> List[str]:
    types, overall = study["types"], study["overall"]
    legend = "total (" + " / ".join(types) + ")"
    md = ["# Truth check: the search against known lines", "",
          f"{len(records)} known lines in {len(study['places'])} places"
          + (f" ({len(study['failed'])} more places whose search failed: their "
             f"{sum(s['known'] for s in study['failed'])} known lines are left out)" if study["failed"] else "")
          + f". Counts as {legend}. A known line is matched when a found line has both anchors within its "
          f"tolerance, either way round: max({TOL_M:g} m, {100 * TOL_SHARE:g} % of its length), for coarse anchors "
          f"at least {QUANTUM_M:g} m x 10^-decimals. Recall = matched / verifiable (a line with coarse anchors or a "
          "stated length far from its anchors' distance is verifiable only when matched); the clean recall leaves "
          "those lines out. SlackMap holds the lines people rigged and reported: a found spot without a known line "
          "is a precision proxy only, never a false line.", "", "## Overall", "",
          "| | " + " | ".join(["all", *types]) + " |", "| --- | " + " | ".join(["---:"] * (len(types) + 1)) + " |"]
    rows = (("known", "known", str), ("verifiable", "verifiable", str), ("matched", "matched", str),
            ("recall", "recall", _pct), ("clean geometry: known", "known_clean", str),
            ("clean geometry: matched", "matched_clean", str), ("clean recall", "recall_clean", _pct),
            ("matched with a doubtful geometry", "matched_doubtful", str),
            ("matched: over trees", "over_trees", _pct))
    for label, key, fmt in rows:
        md.append(f"| {label} | " + " | ".join(fmt(overall[t][key]) for t in ["all", *types]) + " |")
    for label, key in (("matched: clearance p10 / p50 / p90 (m)", "clearance"),
                       ("matched: wall angle p10 / p50 / p90 (deg)", "wall_angle")):
        md.append(f"| {label} | " + " | ".join(" / ".join(f"{v:g}" for v in overall[t][key]) if overall[t][key]
                                                 else "-" for t in ["all", *types]) + " |")
    misses = overall["all"]["known"] - overall["all"]["matched"]
    md += ["", "### Reasons of the misses", "", "| reason | " + " | ".join(["all", *types]) + " | share |",
           "| --- | " + " | ".join(["---:"] * (len(types) + 2)) + " |"]
    for reason in REASONS:
        n = overall["all"]["reasons"][reason]
        md.append(f"| {reason} | " + " | ".join(str(overall[t]["reasons"][reason]) for t in ["all", *types])
                  + f" | {_pct(n / misses) if misses else '-'} |")
    for dimension in DIMENSIONS:
        table = study["by"][dimension]
        md += ["", f"## By {dimension}", "",
               f"| {dimension} | known | verifiable | matched | recall | clean recall | clearance p50 | over trees | "
               "wall angle p50 |", "| --- | " + " | ".join(["---:"] * 8) + " |"]
        for key, s in table.items():
            a = s["all"]
            md.append(f"| {key} | {_cell(s, 'known', types)} | {_cell(s, 'verifiable', types)} | "
                      f"{_cell(s, 'matched', types)} | {_cell(s, 'recall', types, pct=True)} | "
                      f"{_cell(s, 'recall_clean', types, pct=True)} | "
                      f"{a['clearance'][1] if a['clearance'] else '-'} | {_pct(a['over_trees'])} | "
                      f"{a['wall_angle'][1] if a['wall_angle'] else '-'} |")
        used = [reason for reason in REASONS if any(s["all"]["reasons"][reason] for s in table.values())]
        if used:
            md += ["", f"Reasons of the misses by {dimension}, {legend}:", "",
                   f"| {dimension} | " + " | ".join(used) + " |", "| --- | " + " | ".join(["---:"] * len(used)) + " |"]
            for key, s in table.items():
                md.append(f"| {key} | " + " | ".join(_reason_cell(s, reason, types) for reason in used) + " |")
    if study["profiles"]:
        p = study["profiles"]
        md += ["", "## Cross-check with production's profiles", "",
               f"search.profile_of_line of each verifiable known pair, its verdict (helpers.is_valid on the rounded "
               f"clearances) against the captured grid's: {p['checked']} checked, {p['agree']} agree, "
               f"{p['disagree']} disagree, {p['errors']} could not be computed."]
    md += ["", "## Places", "", "Spots without a known line: found spots none of whose lines has a known line of a "
           "good geometry within its tolerance (a precision proxy only).", "",
           "| place | source | res | found lines | found spots | spots without a known line | known | matched |",
           "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    by_place = collections.defaultdict(list)
    for r in records:
        by_place[r["cluster"]].append(r)
    for s in study["places"]:
        rs = by_place.get(s["cluster"], [])
        known = f"{len(rs)} (" + " / ".join(str(sum(r['type'] == t for r in rs)) for t in types) + ")"
        hits = f"{s['matched']} (" + " / ".join(str(sum(r['type'] == t and r['outcome'] == 'matched' for r in rs))
                                                for t in types) + ")"
        md.append(f"| {s['cluster']} | {s['source']} | {s['resolution']:g} | {s['found_lines']} | {s['found_spots']} | "
                  f"{s['spots_without_known']} | {known} | {hits} |")
    for s in study["failed"]:
        md.append(f"| {s['cluster']} | not analysed: {s.get('error', s.get('status'))} | | | | | {s['known']} | |")
    names = {os.path.basename(p) for p in made}
    md += ["", "## Misses by place", ""]
    for s in study["places"]:
        rs = by_place.get(s["cluster"], [])
        if not any(r["outcome"] == "missed" for r in rs) and f"{s['cluster']}-map.png" not in names:
            continue
        md += [f"### {s['cluster']} ({s['source']}, {s['resolution']:g} m, {s['matched']} of {s['known']} matched)", ""]
        if f"{s['cluster']}-map.png" in names:
            md += [f"![{s['cluster']}](pictures/{s['cluster']}-map.png)", ""]
        for n, r in enumerate(rs, 1):
            if r["outcome"] != "missed":
                continue
            md.append(_miss_line(n, r))
            chip = f"{s['cluster']}-miss-{n}.png"
            if chip in names:
                md.append(f"  ![#{n}](pictures/{chip})")
        md.append("")
    return md


def _chip_pair(r: Dict, shape) -> Optional[Tuple[list, list]]:
    """The pixels a miss's profile chip draws: the funnel's best pair, else the best pair near the known
    ends, else the known end pixels when both lie in the grid; None otherwise."""
    if r.get("best"):
        return r["best"]["a1"], r["best"]["a2"]
    near = r.get("near") or {}
    if near.get("best"):
        return near["best"]["a1"], near["best"]["a2"]
    h, w = shape
    pixels = [e["pixel"] for e in r.get("ends") or []]
    if len(pixels) == 2 and all(0 <= p[0] < h and 0 <= p[1] < w for p in pixels):
        lo, hi = sorted(map(tuple, pixels))
        if max(abs(hi[0] - lo[0]), abs(hi[1] - lo[1])) >= 2:
            return list(lo), list(hi)
    return None


def draw(out: str, analysis: Dict) -> List[str]:
    """pictures/: a hillshade per place (found lines grey, known lines coloured by outcome, numbered as
    in study.md) and a profile chip per miss (studylib.profile_chip, the reason in its title)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.collections import LineCollection
    from matplotlib.lines import Line2D

    import coverage_contrast
    folder = os.path.join(out, "pictures")
    os.makedirs(folder, exist_ok=True)
    by_place = collections.defaultdict(list)
    for r in analysis["records"]:
        by_place[r["cluster"]].append(r)
    made, rng = [], np.random.default_rng(0)
    for s in analysis["clusters"]:
        if not s.get("analysed"):
            continue
        try:
            c = load_capture(os.path.join(out, s["cluster"]))
        except (FileNotFoundError, OSError) as e:
            print(f"{s['cluster']}: no pictures ({e})", flush=True)
            continue
        rs = by_place.get(s["cluster"], [])
        h, w = c.elevation.shape
        k = max(1, int(math.ceil(max(h, w) / PICTURE_PX)))
        shade = coverage_contrast.shade(c.elevation[::k, ::k], c.res * k)
        fig, ax = plt.subplots(figsize=(9.5, 8))
        ax.imshow(shade, cmap="gray", interpolation="nearest",
                  extent=(-0.5, shade.shape[1] * k - 0.5, shade.shape[0] * k - 0.5, -0.5))
        f = c.found
        if len(f):
            rows = np.arange(len(f)) if len(f) <= MAP_LINES else np.sort(rng.choice(len(f), MAP_LINES, replace=False))
            g = c.grid  # (col, row) of the anchors: the image's x and y
            ends = [np.column_stack([(xy[rows, 0] - g["left"]) / g["res"] - 0.5,
                                     (g["top"] - xy[rows, 1]) / g["res"] - 0.5]) for xy in (f.xy1, f.xy2)]
            ax.add_collection(LineCollection(np.stack(ends, axis=1), colors=FOUND_COLOUR, linewidths=0.4, alpha=0.6))
        known = {x.id: x for x in c.known}
        for n, r in enumerate(rs, 1):
            outcome = "unverifiable" if r["reason"] == "unverifiable" else r["outcome"]
            line = c.known[n - 1] if n <= len(c.known) and c.known[n - 1].id == r["id"] else known[r["id"]]
            (ra, ca), (rb, cb) = _pixel_float(c.grid, *line.a), _pixel_float(c.grid, *line.b)
            ax.plot([ca, cb], [ra, rb], color=COLOURS[outcome], lw=1.6)
            ax.annotate(str(n), ((ca + cb) / 2, (ra + rb) / 2), color=COLOURS[outcome], fontsize=8, fontweight="bold")
        finite = np.argwhere(np.isfinite(c.elevation[::k, ::k])) * k
        if len(finite):
            box = [finite[:, 1].min() - 0.5, finite[:, 1].max() + k - 0.5, finite[:, 0].max() + k - 0.5,
                   finite[:, 0].min() - 0.5]
            ax.set_xlim(box[0], box[1])
            ax.set_ylim(box[2], box[3])
        ax.set_xticks([])
        ax.set_yticks([])
        ax.legend(handles=[Line2D([], [], color=FOUND_COLOUR, lw=1, label=f"found ({len(f)})")] +
                  [Line2D([], [], color=colour, lw=2, label=name) for name, colour in COLOURS.items()],
                  fontsize=7, loc="upper left", bbox_to_anchor=(1.01, 1.0))
        ax.set_title(f"{s['cluster']}: {s['source']}, {s['resolution']:g} m; {s['matched']} of {s['known']} known "
                     f"lines matched", fontsize=9)
        fig.tight_layout()
        path = os.path.join(folder, f"{s['cluster']}-map.png")
        fig.savefig(path, dpi=110)
        plt.close(fig)
        made.append(path)
        for n, r in enumerate(rs, 1):
            if r["outcome"] != "missed":
                continue
            pair = _chip_pair(r, c.elevation.shape)
            if pair is None:
                continue
            path = os.path.join(folder, f"{s['cluster']}-miss-{n}.png")
            b = r.get("best") or {}
            title = (f"{s['cluster']} #{n} {r['id']} ({r['type']}, {r['length_m']:.0f} m): {r['reason']}"
                     + (f" ({r['which']})" if r.get("which") else "")
                     + (f"; best pair clearance {_num(b.get('clearance_rule'), 2)} m" if b else "")
                     + ("" if r.get("best") else "; drawn: " + ("the best pixels near the known ends"
                                                               if (r.get("near") or {}).get("best") else
                                                               "the known end pixels")))
            studylib.profile_chip(c.namespace, pair[0], pair[1], c.fall, title, path)
            made.append(path)
    return made


# ---------------------------------------------------------------------------------------------

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("analyse", help="match and diagnose every cluster's known lines")
    p.add_argument("out", help="the study folder of tools/truth_study.py run")
    p.add_argument("--profiles", action="store_true", help="also production's profile of each known pair (slow)")
    p.add_argument("--cluster", nargs="+", help="these clusters only")
    p.add_argument("--cache", help="the cache --profiles links in (default: the data folder's)")
    p = sub.add_parser("report", help="study.json, study.md and pictures/ from analysis.json")
    p.add_argument("out")
    p.add_argument("--no-pictures", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "analyse":
        data = analyse(args.out, args.profiles, args.cluster, args.cache)
        records = data["records"]
        matched = sum(r["outcome"] == "matched" for r in records)
        print(f"{matched} of {len(records)} known lines matched in {len(data['clusters'])} clusters: "
              f"{os.path.join(os.path.abspath(args.out), 'analysis.json')}")
        return 0
    report(args.out, not args.no_pictures)
    print(os.path.join(os.path.abspath(args.out), "study.md"))
    return 0


if __name__ == "__main__":
    from progress import utf8_output
    utf8_output()  # redirected output in UTF-8, not the Windows code page
    sys.exit(main())
