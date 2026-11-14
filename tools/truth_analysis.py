"""
Run by hand (and by tools/truth_study.py analyse|report): the known lines of each place of the truth
check (2026-11-08) matched to the lines its search found, every miss diagnosed on the search's own
grid, and the recall of the search per country, source, length and resolution.

    uv run tools/truth_analysis.py analyse <out> [--profiles] [--cluster ID ...] [--cache <cache folder>]
    uv run tools/truth_analysis.py report <out> [--no-pictures]

The input is what tools/truth_study.py run writes per cluster of known lines (<out>/<cluster>/:
capture/grid.json, capture/grids.npz, capture/anchors.npy, capture/lines.npz, capture.json and
known.json; the contract of the task, "The capture of a cluster"). Nothing here runs a search, but
--profiles: search.profile_of_line of each known pair from the cache, as a cross-check, with the
saved run's run.json as its meta (capture.json's "run": the run's folder relative to <out>,
data/runs/<run>; a search without lines saved no run: a meta made from grid.json instead) in the
data folder the run was saved in (<out>/data, shared by every cluster), its cache/ linked to --cache
for the analysis when it has none (an existing link is used as it is and left: a `run` may be using
it; a real cache/, a run with --no-cache-link, is that data folder's own).

The known lines are SlackMap's (tools/slackmap_data.KnownLine): known positives only. A line missing
from SlackMap is not a line missing from the cliff, so the found spots without a known line are a
precision proxy only, never a count of false lines.

Matching (candidates, match): in the grid's CRS, a found line is a candidate of a known line when it
has both anchors within the known line's tolerance of the known anchors, either way round
(tools/coverage_contrast.matched with a radius per line), and its length within the tolerance of the
known line's stated length or of its anchors' distance (two ends moved inwards by up to tol each would
otherwise match a line of L - 2 tol; the anchors' distance as well, since on a line of a good geometry
it may differ from the stated length by up to max(10 m, 20 %), more than the tolerance, and a found
line on the known anchors themselves would fail). The match ("match") is the nearest candidate, the
smallest sum of the two anchor distances (the lowest index among ties); "best_match" the candidate of
the highest clearance (the nearest among ties): the best line the search offers there. The tolerance
(tolerance): tol = max(TOL_M, TOL_SHARE * L) metres, L the line's length_m (the stated length, else
the anchors' distance); for coarse anchors (the flag coarse_anchor, at most COARSE_DECIMALS decimals)
raised to the coordinate quantum QUANTUM_M * 10 ** -decimals (111 m at 3 decimals): a line matched
only thanks to it has a doubtful geometry and counts in matched_doubtful, and its match says whether
the nearest candidate lies within the base tolerance max(TOL_M, TOL_SHARE * L) as well ("within_base").

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
- structure_anchor: an end has no anchor and no steep pixel inside the area within tol, and the
  surface stands STRUCTURE_M or more above the terrain at the end's pixel or within STRUCTURE_PX
  pixels of it (the obstacle surface the search used: obstacles.obstacle_surface keeps the surface
  model only where it stands above the terrain's envelope): the line is rigged on a building, a tower
  or a tree, which the search never takes as an anchor ("which" names the end, each end's
  "structure_m" the largest height of the surface above the terrain there).
- no_steep_pixel: an end has no anchor and no steep pixel inside the area within tol, and no
  structure (the record's "which" names the end: "a", "b" or "both").
- anchor_filtered: every end without an anchor within tol has a steep pixel inside the area within tol
  (the anchor was left out by the elevation band, the prominence or the drop: "hint" says which of
  those limits the search had).
- the rest have anchors within tol at both ends; their pairs (at most MAX_END_ANCHORS per end, the
  nearest to the known point) whose length lies within tol of the known line's stated length or of its
  anchors' distance (candidates' length test: only such a pair can be a match; the length of a pair is
  the distance of its pixel centres, as linesearch._pairs measures it and the found lines' table
  holds it) go through the search's tests in its order, and the reason is the first stage no pair
  passes:
  - length_range: no pair with min_length <= length <= max_length (the search's length range, grid.json's
    params). The study's searches take their range from the known lines' stated and geodesic lengths
    (truth_study.py: 0.8 x the shortest, 1.1 x the longest), so a known line gets this reason when its
    anchors as written lie far off the length the range was made from (the tolerance moves each end up
    to tol), or when the range a --place gave leaves it out; also when no pair has the known line's
    length at all (the note "known_length": the anchors at the two ends lie too near or too far apart),
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
  anchors, which the capture does not hold, may explain it: the note says so), or no pixel lies
  between a pair's anchors (the note "no_pixel_between").

A clearance miss (ZONE_LIFT_REASONS: clearance_near_anchor, clearance_mid) also gets "zone_lift": the
funnel's evaluated pairs at each end zone of ZONES and A-frame lift of LIFTS by the search's rule
(helpers.evaluate_line's bucket minima with the ladder ZONES, a zone at most helpers.ZONE_CAP of a
line's length as the search caps it, delta the fall allowance: the search's end_clearance is 0):
"valid"[zone][lift] whether some pair passes there (helpers.valid_at on the terrain's buckets and,
under nmpt "reject", on the surface's; the pairs over max_wall_angle left out; the height limits
min_height, min_mean_height and min_high_share, which none of the study's searches sets, not
applied), and "lift" per zone the smallest lift some pair needs (end_zone_study.needed_lift's rule,
the larger of the terrain's and the surface's need; valid at any lift above it; None above the last
of LIFTS). A column of the report, not a change of the verdict, which stays the run's rule (zone 0
and lift 0 by default).

Each record (diagnose) holds the ends (per end: its pixel, slope, the nearest pixel of each of
THRESHOLDS within tol, the anchors within tol and the nearest one's distance, steep pixels at a seam,
the pixel's filled/joined/water flags, canopy, structure_m and structure), "on_terrain" (no structure
at either end; an end without surface data or outside the grid counts as terrain), the funnel's
counts and its best pair
(end_zone_study.line_detail: length, strict clearance, first strict failure, the lift each ladder zone
needs; with the rule's clearance, the surface's, the wall angles, the height difference and its
limit), "near": end_zone_study.diagnose_line on studylib.grid_namespace within NEAR_PX pixels of the
known ends (the best pair of any pixels there and its staircase: diagnose_line looks at every pair of
pixels, which is too slow at the tolerance itself), and "exact": helpers.evaluate_line between the
two end pixels. A match ("match", the nearest candidate, and "best_match", the one of the highest
clearance) records the found line's clearances, over obstacles, representative, group, the anchor
distances, the wall angles (on the capture's elevation at the found pixels) and the canopy (surface
- terrain: the obstacle surface the search used) at both anchors; "match" also the number of
candidates, whether any of them is a group's representative ("rep_any") and "within_base".

analyse writes <out>/<cluster>/analysis.json and <out>/analysis.json (every cluster's records); a
cluster whose search failed (capture.json's status "failed", or no grid.json) is listed, not counted,
with its search's error code and message (capture.json's "error" and "message" as "search_error" and
"search_message"; report reads them from capture.json for an analysis.json written before), each in
study.md's "Failed searches".
report writes <out>/study.json, study.md and pictures/ (a hillshade per place: the found lines grey,
the known lines coloured by outcome; a profile chip per miss): per country, source, SlackMap length
bin and resolution, every count as the total and per type (highline, midline): recall (matched /
verifiable), recall_clean (the lines of a good geometry only), recall_terrain (matched / verifiable of
the lines on terrain at both ends), the reasons, the clearance quantiles and the over-trees share of
the best matches, the wall angles of the nearest, how many nearest matches are a group's
representative (shown as a spot), the tolerances of the matched doubtful lines, and the clearance
misses some pair of which is valid at each zone and lift ("zone_lift"). Its head names the searches'
model ("model": the first place's model, for the sag model its rigging and fall zone, from grid.json,
and whether every place's search used the same). study.md is written from study.json alone (read
back): every number it quotes is there, the places' counts per type and the misses' lines too.

Under the sag model (grid.json's model "sag") every evaluation takes the run's sag.EnvelopeTable
(sag_table_of: search._sag_table of the run's rigging and length range, the table the search used),
the fall allowance is the rigging's fall zone (grid.json's "fall"), and the zones' delta with it.
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
import time
import warnings
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "tools"))

import numpy as np  # noqa: E402

import helpers as sh  # noqa: E402
import studylib  # noqa: E402
from slackmap_data import COARSE_DECIMALS, KnownLine  # noqa: E402

REASONS = ("unverifiable", "outside_area", "no_data", "seam_pixel", "water_pixel", "structure_anchor",
           "no_steep_pixel", "anchor_filtered", "length_range", "height_difference", "clearance_near_anchor",
           "clearance_mid", "surface_obstacle", "wall_angle", "unexplained")
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
STRUCTURE_M = 3.0     # metres: a structure at an end (structure_anchor): the surface this much above the terrain
STRUCTURE_PX = 1      # pixels around an end's pixel looked at for a structure
ZONES = (0.0, 5.0, 10.0, 20.0)  # metres: the end zones of a clearance miss's "zone_lift" (a ladder from 0)
LIFTS = (0.0, 1.0, 2.0, 3.0)    # metres: its A-frame lifts; a smallest lift above the last is None
ZONE_LIFT_REASONS = ("clearance_near_anchor", "clearance_mid")
DOUBTFUL_TOL_EDGES = (TOL_M, 100.0, 1000.0)  # metres: the report's bins of the matched doubtful lines' tolerances
REPORT_TYPES = ("highline", "midline")    # always in the tables, other types when present
PICTURE_PX = 1600     # pixels of a place's hillshade at most (a larger view is drawn every k-th pixel)
VIEW_PAD = (20, 0.05)  # a place's picture: the search area and the known lines, padded by max(20 px, 5 % of it)
MAP_LINES = 20000     # found lines a place's picture draws at most (a sample beyond)
COLOURS = {"matched": "#2f855a", "missed": "#c53030", "unverifiable": "#dd6b20"}
FOUND_COLOUR = "#334155"
AREA_COLOUR = "#2563eb"


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
    def lengths(self) -> np.ndarray:
        """The lines' lengths in metres: the table's, the anchors' distance in the grid's CRS where it has none."""
        return np.where(np.isfinite(self.length), self.length, np.hypot(*(self.xy2 - self.xy1).T))

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
    run: Optional[str] = None         # the saved run's folder (absolute: capture.json's "run" under <out>), or None
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


def capture_state(cluster_folder: str) -> Dict:
    """capture.json of a cluster ({} when missing)."""
    path = os.path.join(cluster_folder, "capture.json")
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def capture_status(cluster_folder: str) -> Optional[str]:
    return capture_state(cluster_folder).get("status")


def search_failure(cluster_folder: str) -> Dict:
    """The error code and message of a cluster's failed search (capture.json's "error" and "message",
    as tools/truth_study.py run writes them) as {"search_error", "search_message"}; {} when its search
    did not fail (or capture.json cannot be read)."""
    try:
        state = capture_state(cluster_folder)
    except (OSError, ValueError):
        return {}
    if state.get("status") != "failed":
        return {}
    return {"search_error": state.get("error"), "search_message": state.get("message")}


def run_folder(cluster_folder: str, state: Optional[Dict] = None) -> Optional[str]:
    """The absolute folder of a cluster's saved run: capture.json's "run", a path relative to <out> (the
    cluster folder's parent), or None (no run saved: a search without lines, a failed one)."""
    run = (capture_state(cluster_folder) if state is None else state).get("run")
    if not run:
        return None
    return os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(cluster_folder)), run))


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
    state = capture_state(cluster_folder)
    return Capture(folder=cluster_folder, cluster=os.path.basename(cluster_folder), grid=grid, elevation=elevation,
                   surface=grids.get("surface"), filled=as_mask("filled"), joined=as_mask("joined"),
                   water=as_mask("water"), mask=mask, anchors=np.ascontiguousarray(anchors), found=found,
                   known=load_known(cluster_folder), status=state.get("status"),
                   run=run_folder(cluster_folder, state))


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


def known_lengths(line: KnownLine) -> Tuple[float, ...]:
    """The lengths a candidate's length is compared with: the stated length (when given) and the
    anchors' distance (the module docstring)."""
    return tuple(float(v) for v in (line.stated_m, line.geodesic_m) if v is not None)


def _distances(a: np.ndarray, b: np.ndarray, tol: float, found: FoundLines,
               lengths: Sequence[float] = ()) -> np.ndarray:
    """The anchor-distance sum of each found line with both anchors within tol of (a, b), either way
    round (the smaller sum of the orientations that fit), and, lengths given, its length within tol of
    one of them; inf for the others."""
    if not len(found):
        return np.zeros(0)
    d11, d22 = np.hypot(*(found.xy1 - a).T), np.hypot(*(found.xy2 - b).T)
    d12, d21 = np.hypot(*(found.xy1 - b).T), np.hypot(*(found.xy2 - a).T)
    straight = np.where((d11 <= tol) & (d22 <= tol), d11 + d22, np.inf)
    crossed = np.where((d12 <= tol) & (d21 <= tol), d12 + d21, np.inf)
    sums = np.minimum(straight, crossed)
    if len(lengths):
        fits = np.zeros(len(found), dtype=bool)
        for length in lengths:
            fits |= np.abs(found.lengths - length) <= tol
        sums = np.where(fits, sums, np.inf)
    return sums


def candidates(known: List[KnownLine], found: FoundLines, grid: Dict) -> List[np.ndarray]:
    """The found lines matching each known line (both anchors and the length within its tolerance:
    the module docstring), the nearest first (the anchor-distance sum, the lowest index among ties);
    coverage_contrast.matched with each line's tolerance skips the lines without one."""
    import coverage_contrast
    if not known:
        return []
    ka, kb = _xy(grid, [k.a for k in known]), _xy(grid, [k.b for k in known])
    tol = np.array([tolerance(k) for k in known])
    ok = coverage_contrast.matched(ka, kb, found.xy1, found.xy2, tol)
    out = []
    for k, line in enumerate(known):
        sums = _distances(ka[k], kb[k], tol[k], found, known_lengths(line)) if ok[k] else np.zeros(0)
        idx = np.flatnonzero(np.isfinite(sums))
        out.append(idx[np.argsort(sums[idx], kind="stable")])
    return out


def match(known: List[KnownLine], found: FoundLines, grid: Dict) -> List[Optional[int]]:
    """The index of each known line's found line, its nearest candidate (None: no candidate)."""
    return [int(c[0]) if len(c) else None for c in candidates(known, found, grid)]


def best_candidate(cands: Sequence[int], found: FoundLines) -> Optional[int]:
    """The candidate of the highest clearance (NaN the lowest; the nearest among ties: cands come
    nearest first), None without candidates."""
    cands = np.asarray(cands, dtype=np.int64)
    if not len(cands):
        return None
    clearance = found.clearance[cands]
    return int(cands[int(np.argmax(np.where(np.isnan(clearance), -np.inf, clearance)))])


def near_known(known: List[KnownLine], found: FoundLines, grid: Dict) -> np.ndarray:
    """Which found lines are a candidate of a known line of a good geometry (candidates' test): the
    found spots holding none are the precision proxy."""
    near = np.zeros(len(found), dtype=bool)
    for line in known:
        if doubtful(line):
            continue
        a, b = _xy(grid, [line.a])[0], _xy(grid, [line.b])[0]
        near |= np.isfinite(_distances(a, b, tolerance(line), found, known_lengths(line)))
    return near


def length_bin(length: float) -> str:
    """SlackMap's length bin of a length (LENGTH_EDGES): "0-30" ... "500+"."""
    edges = LENGTH_EDGES
    for lo, hi in zip(edges, edges[1:]):
        if length < hi:
            return f"{lo}-{hi}"
    return f"{edges[-1]}+"


def tol_bin(tol: float) -> str:
    """The bin of a tolerance on DOUBTFUL_TOL_EDGES (metres): "10-100", "100-1000", "1000+"."""
    edges = DOUBTFUL_TOL_EDGES
    for lo, hi in zip(edges, edges[1:]):
        if tol < hi:
            return f"{lo:g}-{hi:g}"
    return f"{edges[-1]:g}+"


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


def _structure(c: Capture, pixel) -> Optional[float]:
    """The largest height of the surface above the terrain at a pixel or within STRUCTURE_PX pixels of
    it (metres; None without a surface, outside the grid or without data there)."""
    r, col = pixel
    h, w = c.elevation.shape
    if c.surface is None or not (0 <= r < h and 0 <= col < w):
        return None
    k = STRUCTURE_PX
    window = (slice(max(0, r - k), r + k + 1), slice(max(0, col - k), col + k + 1))
    above = np.asarray(c.surface[window], dtype=np.float64) - np.asarray(c.elevation[window], dtype=np.float64)
    above = above[np.isfinite(above)]
    return float(above.max()) if len(above) else None


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
    structure = _structure(c, pixel)
    entry.update(filled=_flag(c.filled, pixel), joined=_flag(c.joined, pixel), water=_flag(c.water, pixel),
                 at_seam=bool(in_grid and _seams(c, np.array([pixel], dtype=np.int64))[0]),
                 canopy=_canopy(c, pixel) if in_grid else None, structure_m=structure,
                 structure=bool(structure is not None and structure >= STRUCTURE_M))
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


def _evaluate(c: Capture, lo, hi, zones: Sequence[float] = ()):
    """helpers.evaluate_line of the pair with the run's surface, model, end zone and lift (with zones
    also the bucket minima of that ladder: two more values, the first eight unchanged); None for a pair
    without a pixel between its anchors or with an anchor without data (no line: the sag table takes
    no NaN height difference, and the formula's clearance would be NaN)."""
    if not (math.isfinite(float(c.elevation[int(lo[0]), int(lo[1])]))
            and math.isfinite(float(c.elevation[int(hi[0]), int(hi[1])]))):
        return None
    p = c.params
    with warnings.catch_warnings():  # np.nanmin's "All-NaN slice" where an anchor has no data: NaN fails anyway
        warnings.simplefilter("ignore", RuntimeWarning)
        return sh.evaluate_line(lo, hi, c.elevation, c.res, c.surface if c.nmpt else None, c.sag_table,
                                float(p.get("high_above", sh.HIGH_ABOVE)),
                                end_zone=float(p.get("end_zone", 0) or 0), lift=float(p.get("anchor_lift", 0) or 0),
                                zones=zones)


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


def _needed(buckets: np.ndarray, j: int, delta: float) -> np.ndarray:
    """end_zone_study.needed_lift of each row of bucket minima at ladder zone j: max(0, -min(core),
    -min(zone) - delta), inf where a bucket is NaN (a pixel without data fails at any lift)."""
    n = len(buckets)
    core = buckets[:, j:].min(axis=1) if buckets.shape[1] > j else np.full(n, np.inf)
    zone = buckets[:, :j].min(axis=1) if j else np.full(n, np.inf)
    need = np.maximum(np.maximum(0.0, -core), -zone - delta) + 0.0  # + 0.0: never -0.0
    need[np.isnan(buckets).any(axis=1)] = np.inf
    return need


def _zone_lift(c: Capture, lo: np.ndarray, hi: np.ndarray, results: Sequence[tuple]) -> Optional[Dict]:
    """A clearance miss's evaluated pairs (lo, hi and their evaluate_line results with the ladder ZONES)
    at each zone of ZONES and lift of LIFTS (the module docstring): "valid", "lift" and the pairs."""
    if not len(results):
        return None
    delta = c.fall  # helpers.end_delta with the search's end_clearance of 0
    grids = [np.array([r[8] for r in results], dtype=np.float64).reshape(-1, len(ZONES))]
    if c.nmpt == "reject":  # helpers.is_valid: a line without surface data passes (+inf buckets)
        grids.append(np.array([np.full(len(ZONES), np.inf) if r[9] is None else r[9] for r in results],
                              dtype=np.float64).reshape(-1, len(ZONES)))
    keep = np.ones(len(results), dtype=bool)
    if c.params.get("max_wall_angle") is not None:
        lo, hi = np.asarray(lo, dtype=np.int64).reshape(-1, 2), np.asarray(hi, dtype=np.int64).reshape(-1, 2)
        down = sh.downslope(c.elevation, np.vstack([lo, hi]), c.res)
        a1, a2 = sh.wall_angles(lo, hi, down[:len(lo)], down[len(lo):])
        keep &= np.where(a2 > a1, a2, a1) <= float(c.params["max_wall_angle"])
    valid, lift = [], []
    for j in range(len(ZONES)):
        ok = [keep & np.logical_and.reduce([sh.valid_at(g, j, h, delta) for g in grids]) for h in LIFTS]
        valid.append([bool(v.any()) for v in ok])
        need = np.maximum.reduce([_needed(g, j, delta) for g in grids])
        smallest = float(need[keep].min()) if keep.any() else math.inf
        lift.append(smallest if smallest <= LIFTS[-1] else None)
    return {"zones": list(ZONES), "lifts": list(LIFTS), "valid": valid, "lift": lift, "pairs": int(keep.sum())}


def _funnel(c: Capture, ends: Sequence[Tuple[np.ndarray, np.ndarray]], lengths: Sequence[float], tol: float
            ) -> Tuple[Dict, Optional[Dict], str, Optional[str], Optional[Dict]]:
    """The anchor pairs of the two ends with a length within tol of one of lengths (the known line's:
    known_lengths) through the search's tests (the module docstring): the counts, the best pair of the
    last stage reached, the reason, a note and a clearance miss's zone_lift (None for the other
    reasons)."""
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
    fits = np.zeros(len(length), dtype=bool)
    for known_length in lengths:
        fits |= np.abs(length - known_length) <= tol
    counts = {"pairs": int(len(i)), "known_length": int(fits.sum())}
    in_range = fits & (length >= float(p.get("min_length", 0))) & (length <= float(p.get("max_length", np.inf)))
    counts["length"] = int(in_range.sum())

    def detail(k, stage):
        return _pair_detail(c, lo[k], hi[k], stage, (da[i[k]], db[j[k]]))

    if not in_range.any():
        k = int(np.argmin(np.where(fits, dsum, np.inf) if fits.any() else dsum)) if len(dsum) else None
        return (counts, None if k is None else detail(k, "length"), "length_range",
                None if fits.any() else "known_length", None)
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
        return counts, detail(int(np.argmin(excess)), "height"), "height_difference", None, None
    rows = np.flatnonzero(height)
    rows = rows[np.argsort(dsum[rows], kind="stable")]
    counts["capped"] = bool(len(rows) > MAX_PAIRS)
    rows = rows[:MAX_PAIRS]
    counts["evaluated"] = int(len(rows))
    results = [_evaluate(c, lo[k], hi[k], ZONES) for k in rows]
    valid = np.array([r is not None for r in results])
    rows, results = rows[valid], [r for r in results if r is not None]
    clearance = np.array([r[3] for r in results], dtype=np.float64)
    terrain = clearance > 0
    counts["terrain"] = int(terrain.sum())
    if not terrain.any():
        k = int(rows[np.argmax(np.where(np.isnan(clearance), -np.inf, clearance))]) if len(rows) else None
        if k is None:
            return counts, None, "unexplained", "no_pixel_between", None
        best = detail(k, "terrain")
        failure = best["rule_failure"]
        reason = "clearance_near_anchor" if failure and failure["near"] else "clearance_mid"
        return counts, best, reason, None, _zone_lift(c, lo[rows], hi[rows], results)
    nmpt = np.array([np.nan if r[4] is None else r[4] for r in results], dtype=np.float64)
    surface = terrain.copy()
    if c.nmpt == "reject":  # helpers.is_valid: a surface without data at every pixel (None, NaN here) passes
        surface &= np.isnan(nmpt) | (nmpt > 0)
    counts["surface"] = int(surface.sum())
    if not surface.any():
        k = int(rows[np.argmax(np.where(terrain & ~np.isnan(nmpt), nmpt, -np.inf))])
        return counts, detail(k, "surface"), "surface_obstacle", None, None
    down = sh.downslope(z, np.vstack([lo[rows], hi[rows]]), c.res)
    a1, a2 = sh.wall_angles(lo[rows], hi[rows], down[:len(rows)], down[len(rows):])
    wall_max = np.where(a2 > a1, a2, a1)
    wall = surface.copy()
    if p.get("max_wall_angle") is not None:
        wall &= wall_max <= float(p["max_wall_angle"])
    counts["wall"] = int(wall.sum())
    if not wall.any():
        k = int(rows[np.argmin(np.where(surface, wall_max, np.inf))])
        return counts, detail(k, "wall"), "wall_angle", None, None
    limits = wall & np.array([_limits_pass(c, r) for r in results])
    counts["limits"] = int(limits.sum())
    last = limits if limits.any() else wall
    k = int(rows[np.argmax(np.where(last, clearance, -np.inf))])
    note = "a_pair_passes" if limits.any() else "height_limits"
    if limits.any() and p.get("min_prominence") is not None:
        note += "; min_prominence set: the strong anchors are not in the capture"
    return counts, detail(k, "limits" if limits.any() else "wall"), "unexplained", note, None


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
    if c.sag_table is not None and any(np.isnan(c.elevation[tuple(studylib.disc(c.elevation, e, NEAR_PX).T)]).any()
                                       for e in ends):
        return {"error": "a pixel without data near an end (the sag table takes no NaN height difference)"}
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


def diagnose(capture: Capture, line: KnownLine, found_index: Optional[int],
             cands: Optional[Sequence[int]] = None) -> Dict:
    """One known line's record (the module docstring): the match, or the miss with its reason. cands:
    the line's candidates in candidates' order (computed here when not given)."""
    c = capture
    tol = tolerance(line)
    record = {"id": line.id, "type": line.type, "country": line.country, "cluster": c.cluster, "source": c.source,
              "resolution": c.res, "length_m": line.length_m, "stated_m": line.stated_m, "geodesic_m": line.geodesic_m,
              "decimals": line.decimals, "flags": list(line.flags), "doubtful": doubtful(line),
              "bin": length_bin(line.length_m), "tol": tol,
              "outcome": "matched" if found_index is not None else "missed",
              "verifiable": True, "reason": None, "which": None, "note": None, "match": None, "best_match": None,
              "ends": [], "funnel": None, "best": None, "zone_lift": None, "near": None, "exact": None,
              "canopy": [None, None], "structure": [None, None], "on_terrain": True}
    ea, pa, da = _end(c, line.a, tol)
    eb, pb, db = _end(c, line.b, tol)
    ends = [ea, eb]
    record.update(ends=ends, exact=_exact(c, ends), structure=[ea["structure_m"], eb["structure_m"]],
                  on_terrain=not (ea["structure"] or eb["structure"]))
    if found_index is not None:
        found_index = int(found_index)
        cands = [int(k) for k in (candidates([line], c.found, c.grid)[0] if cands is None else cands)]
        if found_index not in cands:  # a match the caller chose: taken as the nearest candidate
            cands.insert(0, found_index)
        best = best_candidate(cands, c.found)
        base = max(TOL_M, TOL_SHARE * line.length_m)
        m = _match_detail(c, line, found_index)
        fits = min(abs(float(c.found.lengths[found_index]) - v) for v in known_lengths(line)) <= base
        m.update(candidates=len(cands), rep_any=bool(c.found.rep[cands].any()),
                 within_base=bool(max(m["d"]) <= base and fits))
        record.update(match=m, best_match={**_match_detail(c, line, best), "nearest": best == found_index},
                      canopy=m["canopy"])
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
        elif any(not e["steep"] and e["structure"] for e in lacking):
            record.update(reason="structure_anchor",
                          which=_which([b and not e["steep"] and e["structure"] for e, b in zip(ends, bare)]))
        elif any(not e["steep"] for e in lacking):
            record.update(reason="no_steep_pixel", which=_which([b and not e["steep"] for e, b in zip(ends, bare)]))
        else:
            record.update(reason="anchor_filtered", which=_which(bare), note=_filter_hint(c, lacking))
        return record
    counts, best, reason, note, zone_lift = _funnel(c, [(pa, da), (pb, db)], known_lengths(line), tol)
    record.update(funnel=counts, best=best, reason=reason, note=note, zone_lift=zone_lift)
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


def profile_meta(c: Capture) -> Dict:
    """The meta search.profile_of_line takes: the saved run's run.json, or (no run saved: a search
    without lines) one made from grid.json (its params, CRS and source)."""
    path = os.path.join(c.run, "run.json") if c.run else None
    if path and os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {"params": c.params, "center": {"crs": c.grid["crs"]}, "source": {"id": c.source},
            "data": (c.grid.get("layer_meta") or {}).get("data", [])}


def profile_check(c: Capture, line: KnownLine, record: Dict, data: str) -> Dict:
    """search.profile_of_line of the known pair (profile_meta; the data folder `data` with its cache)
    against the grid's verdict of the same pair."""
    import search
    meta = profile_meta(c)
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


def _is_link(path: str) -> bool:
    """A directory link: a symlink, or a junction on Windows."""
    return os.path.islink(path) or (hasattr(os.path, "isjunction") and os.path.isjunction(path))


class ProfileFolders:
    """The data folders --profiles computes in, each made ready once per analyse (a context manager):
    the folder the cluster's run was saved in (<out>/data/runs/<run> -> <out>/data), else <out>/data.
    A data folder with a real cache/ is used as it is (a run with --no-cache-link), one whose cache/ is
    a link already too (a `run` may be using it: never removed here); otherwise its cache/ is linked to
    cache_dir (studylib.linked_data_folder) and the link removed on leaving, also after an error."""

    def __init__(self, cache_dir: Optional[str]):
        self.cache_dir = cache_dir
        self.ready: Dict[str, str] = {}
        self.stack = contextlib.ExitStack()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.ready.clear()
        return self.stack.__exit__(*exc)

    def data_of(self, c: Capture) -> str:
        data = os.path.dirname(os.path.dirname(c.run)) if c.run else os.path.join(os.path.dirname(c.folder), "data")
        data = os.path.normpath(os.path.abspath(data))
        if data not in self.ready:
            cache_folder = os.path.join(data, "cache")
            if os.path.isdir(cache_folder) or _is_link(cache_folder):
                self.ready[data] = data
            else:
                self.ready[data] = self.stack.enter_context(
                    studylib.linked_data_folder(os.path.dirname(data), self.cache_dir))
        return self.ready[data]


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


def analyse_cluster(folder: str, profiles: bool = False, cache_dir: Optional[str] = None,
                    folders: Optional[ProfileFolders] = None) -> Dict:
    """One cluster: its records and summary (with the seconds it took), written to <folder>/analysis.json.
    folders: the data folders of --profiles made ready for the whole analyse (else for this cluster)."""
    if profiles and folders is None:
        with ProfileFolders(cache_dir) as folders:
            return analyse_cluster(folder, profiles, cache_dir, folders)
    started = time.perf_counter()
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
                  **search_failure(folder), "records": []}
        _write_json(os.path.join(folder, "analysis.json"), result)
        return result
    cands = candidates(c.known, c.found, c.grid)
    index = [int(k[0]) if len(k) else None for k in cands]
    records = [diagnose(c, line, k, ks) for line, k, ks in zip(c.known, index, cands)]
    if profiles:
        checks = [(line, r) for line, r in zip(c.known, records)
                  if r["verifiable"] and r["reason"] not in ("outside_area", "no_data")]
        if checks:
            data = folders.data_of(c)
            for line, r in checks:
                r["profile"] = profile_check(c, line, r, data)
    near = near_known(c.known, c.found, c.grid)
    groups = np.unique(c.found.group)
    with_known = np.unique(c.found.group[near]) if near.any() else np.zeros(0, dtype=np.int64)
    result = {"cluster": name, "status": c.status or "done", "analysed": True, "source": c.source,
              "resolution": c.res, "crs": c.grid["crs"], "model": c.grid.get("model", c.params.get("model")),
              "rigging": c.grid.get("rigging") or c.params.get("rigging"), "fall": c.fall,
              "nmpt": c.nmpt, "slope_threshold": c.threshold, "anchors": int(len(c.anchors)),
              "found_lines": int(len(c.found)), "found_spots": int(len(groups)),
              "spots_without_known": int(len(groups) - len(with_known)), "known": len(c.known),
              "matched": int(sum(k is not None for k in index)),
              "seconds": round(time.perf_counter() - started, 2), "records": records}
    _write_json(os.path.join(folder, "analysis.json"), result)
    return result


def analyse(out: str, profiles: bool = False, clusters: Optional[Sequence[str]] = None,
            cache_dir: Optional[str] = None) -> Dict:
    """Every cluster's capture (or the named ones) -> <out>/<cluster>/analysis.json, then <out>/analysis.json
    of every cluster analysed so far (the summaries and all records). cache_dir: the cache --profiles
    links into the data folder the runs were saved in when it has none (ProfileFolders; default: the
    data folder's, cache.data_dir())."""
    if profiles and cache_dir is None:
        import cache
        cache_dir = os.path.join(cache.data_dir(), "cache")
    with ProfileFolders(cache_dir) as folders:
        for folder in cluster_folders(out, clusters):
            r = analyse_cluster(folder, profiles, cache_dir, folders)
            if r["analysed"]:
                print(f"{r['cluster']}: {r['matched']} of {r['known']} known lines matched, {r['found_lines']} "
                      f"lines found, {r['seconds']:.1f} s", flush=True)
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


def _share(n: int, d: int) -> Optional[float]:
    return round(n / d, 4) if d else None


def zone_lift_counts(records: Sequence[Dict]) -> Dict:
    """The misses of ZONE_LIFT_REASONS (each, and "both") some pair of which is valid at each zone and
    lift: {"zones", "lifts", "rows": {name: {"misses", "found": [[count per lift] per zone]}}}."""
    rows = {}
    for name, reasons in [*((r, (r,)) for r in ZONE_LIFT_REASONS), ("both", ZONE_LIFT_REASONS)]:
        rs = [r for r in records if r["outcome"] == "missed" and r["reason"] in reasons]
        found = [[0] * len(LIFTS) for _ in ZONES]
        for r in rs:
            valid = (r.get("zone_lift") or {}).get("valid")
            for j in range(len(ZONES) if valid else 0):
                for k in range(len(LIFTS)):
                    found[j][k] += bool(valid[j][k])
        rows[name] = {"misses": len(rs), "found": found}
    return {"zones": list(ZONES), "lifts": list(LIFTS), "rows": rows}


def stats(records: Sequence[Dict]) -> Dict:
    """Counts, recalls, reasons, the matched lines' quantiles and representatives, the doubtful
    matches' tolerances and the clearance misses' zones and lifts of some records (the module
    docstring)."""
    matched = [r for r in records if r["outcome"] == "matched"]
    verifiable = sum(bool(r["verifiable"]) for r in records)
    clean = [r for r in records if not r["doubtful"]]
    clean_matched = sum(r["outcome"] == "matched" for r in clean)
    terrain = [r for r in records if r.get("on_terrain", True)]
    terrain_verifiable = sum(bool(r["verifiable"]) for r in terrain)
    terrain_matched = sum(r["outcome"] == "matched" for r in terrain)
    reasons = collections.Counter(r["reason"] for r in records if r["outcome"] == "missed")
    best = [r.get("best_match") or r["match"] for r in matched]  # an analysis.json of before: the nearest only
    over = [b["over"] for b in best]
    doubtful_matched = [r for r in matched if r["doubtful"]]
    bins = {tol_bin(lo): 0 for lo in DOUBTFUL_TOL_EDGES}
    for r in doubtful_matched:
        bins[tol_bin(r["tol"])] += 1
    tols = sorted(round(r["tol"], 1) for r in doubtful_matched)
    return {"known": len(records), "verifiable": verifiable, "matched": len(matched),
            "recall": _share(len(matched), verifiable), "misses": len(records) - len(matched),
            "known_clean": len(clean), "matched_clean": clean_matched, "recall_clean": _share(clean_matched, len(clean)),
            "known_terrain": len(terrain), "verifiable_terrain": terrain_verifiable, "matched_terrain": terrain_matched,
            "recall_terrain": _share(terrain_matched, terrain_verifiable),
            "matched_doubtful": len(doubtful_matched),
            "doubtful_tolerance": {"bins": bins, "quantiles": _quantiles(tols), "largest": tols[-1] if tols else None,
                                   "within_base": sum(bool(r["match"].get("within_base")) for r in doubtful_matched),
                                   "tolerances": tols},
            "matched_rep": sum(bool(r["match"]["rep"]) for r in matched),
            "matched_rep_any": sum(bool(r["match"].get("rep_any", r["match"]["rep"])) for r in matched),
            "reasons": {k: reasons.get(k, 0) for k in REASONS},
            "clearance": _quantiles([b["clearance"] for b in best]),
            "over_trees": _share(sum(over), len(over)),
            "wall_angle": _quantiles([r["match"]["wall"] for r in matched]),
            "zone_lift": zone_lift_counts(records)}


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


def _zone_cell(s: Dict, name: str, j: int, k: int, types: Sequence[str]) -> str:
    """A cell of the zone x lift table: the misses found at zone j and lift k, total (per type)."""
    found = {t: s[t]["zone_lift"]["rows"][name]["found"][j][k] for t in ["all", *types]}
    return f"{found['all']} (" + " / ".join(str(found[t]) for t in types) + ")"


def _code_span(text, width: int = 400) -> str:
    """A text as a markdown code span on one line (its whitespace collapsed, at most width characters,
    backticks made quotes): an error's message may hold an HTML page or a "|"."""
    text = " ".join(str(text).split()).replace("`", "'")
    return f"`{text if len(text) <= width else text[:width - 3] + '...'}`"


def _failure_cause(s: Dict) -> str:
    """A place not analysed, in short: "search failed: <code>" (its search's error code, "no code" without
    one), else "not analysed"."""
    if s.get("status") == "failed":
        return f"search failed: {s.get('search_error') or 'no code'}"
    return "not analysed"


def _failure_line(s: Dict) -> str:
    """study.md's line of a place not analysed: its known lines, its search's error and message, or why the
    analysis could not read its capture."""
    n = s["known"]
    text = (_code_span(s["search_message"]) if s.get("status") == "failed" and s.get("search_message")
            else "no message" if s.get("status") == "failed" else _code_span(s.get("error") or s.get("status")))
    return f"- {s['cluster']} ({n} known line{'' if n == 1 else 's'}): {_failure_cause(s)}; {text}"


def _miss_entry(n: int, r: Dict) -> Dict:
    """What study.json keeps of a miss (record r, the n-th known line of its place: the number of its
    picture) for its line in study.md (_miss_line)."""
    entry = {"n": n, **{k: r.get(k) for k in ("id", "type", "length_m", "tol", "reason", "which", "note",
                                               "profile")}}
    b = r.get("best")
    entry["best"] = {k: b.get(k) for k in ("length", "dh", "dh_limit", "clearance_rule", "clearance_nmpt",
                                           "rule_failure", "angles", "staircase")} if b else None
    entry["ends"] = [{k: e.get(k) for k in ("slope", "steep_m", "anchor_within", "structure_m", "structure")}
                     for e in r.get("ends") or []]
    entry["exact_clearance"] = (r.get("exact") or {}).get("clearance")
    zl = r.get("zone_lift")
    entry["zone_lift"] = {"zones": zl["zones"], "lift": zl["lift"]} if zl else None
    return entry


def _miss_line(r: Dict, rules_: Dict) -> str:
    """One miss of a place's list, from its entry in study.json (_miss_entry)."""
    text = (f"- #{r['n']} `{r['id']}` ({r['type']}, {r['length_m']:.0f} m, tol {r['tol']:.0f} m): **{r['reason']}**"
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
        zl = r.get("zone_lift")
        if zl:
            text += "; smallest lift of any pair: " + ", ".join(
                f"zone {z:g} m: " + (f"{_num(v)} m" if v is not None else f"over {rules_['lifts'][-1]:g} m")
                for z, v in zip(zl["zones"], zl["lift"]))
        else:
            text += "; lift needed " + ", ".join(f"zone {s['zone']:g} m: {_num(s['lift'])} m" for s in b["staircase"])
    elif r.get("ends"):
        parts = []
        for side, e in zip("ab", r["ends"]):
            part = (f"{side}: slope {_num(e.get('slope'))} deg, steep pixel {_num(e.get('steep_m'))} m, "
                    f"anchor {_num(e.get('anchor_within'))} m")
            if e.get("structure"):
                part += f", surface {_num(e['structure_m'])} m above the terrain"
            parts.append(part)
        text += "; " + "; ".join(parts)
    if r.get("exact_clearance") is not None:
        text += f"; the known pair itself: clearance {_num(r['exact_clearance'], 2)} m"
    if r.get("profile"):
        p = r["profile"]
        text += (f"; profile: {p['error']}" if "error" in p else
                 f"; profile {'valid' if p['production'] else 'not valid'} ({'agrees' if p['agree'] else 'DISAGREES'})")
    return text


def model_of(places: Sequence[Dict]) -> Optional[Dict]:
    """The model of the analysed places' searches: the first place's model, its fall allowance and (the
    sag model) its rigging, and whether every place's search used the same ("variants": each with its
    places); None without places."""
    if not places:
        return None

    def key(s):
        rigging = s.get("rigging") if s.get("model") == "sag" else None
        return s.get("model"), json.dumps(rigging, sort_keys=True), s.get("fall")

    variants = collections.Counter(key(s) for s in places)
    first = places[0]
    return {"model": first.get("model"), "fall": first.get("fall"),
            "rigging": first.get("rigging") if first.get("model") == "sag" else None, "same": len(variants) == 1,
            "variants": [{"model": m, "rigging": json.loads(r), "fall": f, "places": n}
                         for (m, r, f), n in variants.items()]}


def _model_text(m: Dict) -> str:
    """The model of a variant of model_of, in words."""
    if m["model"] != "sag":
        return f"the {m['model']} model (a fall allowance of {_num(m['fall'], 1)} m)"
    rig = m.get("rigging") or {}
    if not rig:
        return "the sag model (its rigging not recorded)"
    return (f"the sag model (the sag estimator): pretension {_num(rig.get('pretension'))} kN, stretch "
            f"{_num(rig.get('stretch'))} % at 10 kN, webbing {_num(rig.get('webbing_weight'), 0)} g/m, athlete "
            f"{_num(rig.get('athlete_mass'), 0)} kg, a fall zone of {_num(rig.get('fall_zone'))} m below the sagged "
            "webbing (the fall allowance)")


def rules() -> Dict:
    """The rules and constants study.md quotes (study.json's "rules")."""
    return {"tolerance": {"floor_m": TOL_M, "share": TOL_SHARE, "quantum_m": QUANTUM_M},
            "coarse_decimals": COARSE_DECIMALS, "structure_m": STRUCTURE_M, "structure_px": STRUCTURE_PX,
            "zones": list(ZONES), "lifts": list(LIFTS), "zone_cap": sh.ZONE_CAP,
            "zone_lift_reasons": list(ZONE_LIFT_REASONS), "doubtful_tol_edges": list(DOUBTFUL_TOL_EDGES)}


def report(out: str, pictures: bool = True) -> str:
    """<out>/study.json, study.md and pictures/ from <out>/analysis.json (analyse first); returns study.md's
    text, written from study.json as read back (markdown)."""
    out = os.path.abspath(out)
    path = os.path.join(out, "analysis.json")
    if not os.path.exists(path):
        raise FileNotFoundError(f"{path} is missing: run analyse first")
    with open(path, encoding="utf-8") as f:
        analysis = json.load(f)
    records, clusters = analysis["records"], analysis["clusters"]
    types = types_of(records)
    analysed = [s for s in clusters if s.get("analysed")]
    # a failed search's error and message: capture.json's when an analysis.json of before lacks them
    failed = [s if s.get("status") != "failed" or "search_error" in s
              else {**s, **search_failure(os.path.join(out, s["cluster"]))}
              for s in clusters if not s.get("analysed")]
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
    by_place = collections.defaultdict(list)
    for r in records:
        by_place[r["cluster"]].append(r)
    places = []
    for s in analysed:
        rs = by_place.get(s["cluster"], [])
        places.append({**s, "known_by_type": {t: sum(r["type"] == t for r in rs) for t in types},
                       "matched_by_type": {t: sum(r["type"] == t and r["outcome"] == "matched" for r in rs)
                                           for t in types}})
    misses = {s["cluster"]: [_miss_entry(n, r) for n, r in enumerate(by_place.get(s["cluster"], []), 1)
                             if r["outcome"] == "missed"] for s in analysed}
    made = draw(out, analysis) if pictures else []
    study = {"generated": datetime.date.today().isoformat(), "reasons": list(REASONS), "types": types,
             "model": model_of(analysed), "rules": rules(), "overall": overall, "by": by, "places": places, "failed": failed, "misses": misses,
             "profiles": profile_counts, "pictures": [os.path.relpath(p, out).replace(os.sep, "/") for p in made]}
    _write_json(os.path.join(out, "study.json"), study)
    with open(os.path.join(out, "study.json"), encoding="utf-8") as f:
        text = "\n".join(markdown(json.load(f)))
    with open(os.path.join(out, "study.md"), "w", encoding="utf-8") as f:
        f.write(text)
    return text


def markdown(study: Dict) -> List[str]:
    """study.md's lines from study.json alone: every number they quote is there (or a share of two of its
    numbers)."""
    types, overall, rules_ = study["types"], study["overall"], study["rules"]
    tol = rules_["tolerance"]
    columns = [*types, "all"]
    legend = "total (" + " / ".join(types) + ")"
    a = overall["all"]

    def headline(value) -> str:
        """Each type's value first, the total's after: "highline ..., midline ...; all ..."."""
        return ", ".join(f"{t} {value(overall[t])}" for t in types) + f"; all {value(a)}"

    def recall(key, matched, verifiable):
        return lambda s: f"{_pct(s[key])} ({s[matched]} of {s[verifiable]})"

    quantum3 = tol["quantum_m"] * 10.0 ** -rules_["coarse_decimals"]
    md = ["# Truth check: the search against known lines", ""]
    m = study.get("model")
    if m:
        md += [f"Searches with {_model_text(m)}."
               + ("" if m["same"] else " The places' searches differ: " + "; ".join(
                   f"{_model_text(v)} in {v['places']} place{'' if v['places'] == 1 else 's'}"
                   for v in m["variants"]) + "."), ""]
    md += [
          "- **Recall** (matched of verifiable known lines): " + headline(recall("recall", "matched", "verifiable")) + ".",
          "- **Both ends on terrain** (no structure at either end): "
          + headline(recall("recall_terrain", "matched_terrain", "verifiable_terrain")) + ".",
          "- **Misses at a structure** (structure_anchor: an end on a building, a tower or a tree): "
          + headline(lambda s: str(s["reasons"]["structure_anchor"])) + ".",
          "- **Shown as a spot** (the nearest match is its group's representative): "
          + headline(lambda s: f"{s['matched_rep']} of {s['matched']}") + ".", "",
          "Midlines hang below the fall allowance by construction, so their recall is expected to be near 0 under "
          "today's rule.", "",
          f"{a['known']} known lines in {len(study['places'])} places"
          + (f" ({len(study['failed'])} more places whose search failed: their "
             f"{sum(s['known'] for s in study['failed'])} known lines are left out)" if study["failed"] else "")
          + f". Counts as {legend}. A found line is a candidate of a known line when both its anchors lie within "
          f"the known line's tolerance, either way round, and its length within the tolerance of the known line's "
          f"stated length or of its anchors' distance; the tolerance is max({tol['floor_m']:g} m, "
          f"{100 * tol['share']:g} % of its length). The match is the nearest candidate (the smallest sum of the two "
          "anchor distances), the best match the candidate of the highest clearance. Recall = matched / verifiable "
          "(a line with coarse anchors or a stated length far from its anchors' distance is verifiable only when "
          "matched); the clean recall leaves those lines out; the terrain recall takes the lines with no structure "
          f"at either end (the surface {rules_['structure_m']:g} m or more above the terrain at an end's pixel or "
          f"within {rules_['structure_px']} pixel of it; an end without a surface model counts as terrain). "
          "SlackMap holds the lines people rigged and reported: a found spot without a known line is a precision "
          "proxy only, never a false line.", "", "## Overall", "",
          "| | " + " | ".join(columns) + " |", "| --- | " + " | ".join(["---:"] * len(columns)) + " |"]
    rows = (("known", "known", str), ("verifiable", "verifiable", str), ("matched", "matched", str),
            ("recall", "recall", _pct), ("clean geometry: known", "known_clean", str),
            ("clean geometry: matched", "matched_clean", str), ("clean recall", "recall_clean", _pct),
            ("both ends on terrain: known", "known_terrain", str),
            ("both ends on terrain: verifiable", "verifiable_terrain", str),
            ("both ends on terrain: matched", "matched_terrain", str), ("terrain recall", "recall_terrain", _pct),
            ("matched with a doubtful geometry", "matched_doubtful", str),
            ("matched: shown as a spot (the nearest match a representative)", "matched_rep", str),
            ("matched: a representative among the candidates", "matched_rep_any", str),
            ("matched: over trees (best match)", "over_trees", _pct))
    for label, key, fmt in rows:
        md.append(f"| {label} | " + " | ".join(fmt(overall[t][key]) for t in columns) + " |")
    for label, key in (("matched: clearance p10 / p50 / p90 (m, best match)", "clearance"),
                       ("matched: wall angle p10 / p50 / p90 (deg, nearest match)", "wall_angle")):
        md.append(f"| {label} | " + " | ".join(" / ".join(f"{v:g}" for v in overall[t][key]) if overall[t][key]
                                                 else "-" for t in columns) + " |")
    md += ["", "The clearance quantiles and the over-trees share are those of each matched line's best match (its "
           "candidate of the highest clearance: the best line the search offers there); the wall angles those of its "
           "nearest match (the walls at the known anchors). Shown as a spot: the nearest match is its group's "
           "representative, the line the map shows for that spot."]
    dt = {t: overall[t]["doubtful_tolerance"] for t in columns}
    md += ["", "### Matches with a doubtful geometry", "",
           f"A line with coarse anchors (at most {rules_['coarse_decimals']} decimals) gets a tolerance of at least "
           f"the coordinate quantum, {tol['quantum_m']:g} m x 10^-decimals ({quantum3:g} m at "
           f"{rules_['coarse_decimals']} decimals), so its match is doubtful: it counts as matched with a doubtful "
           "geometry, and the clean recall leaves it out. The tolerances of the matched doubtful lines, and how many "
           "of them have their nearest match within the base tolerance as well:", "",
           "| tolerance | " + " | ".join(columns) + " |", "| --- | " + " | ".join(["---:"] * len(columns)) + " |"]
    for label in dt["all"]["bins"]:
        md.append(f"| {label} m | " + " | ".join(str(dt[t]["bins"][label]) for t in columns) + " |")
    md.append("| p10 / p50 / p90 (m) | " + " | ".join(" / ".join(f"{v:g}" for v in dt[t]["quantiles"])
                                                       if dt[t]["quantiles"] else "-" for t in columns) + " |")
    md.append("| largest (m) | " + " | ".join(_num(dt[t]["largest"]) for t in columns) + " |")
    md.append("| within the base tolerance as well | " + " | ".join(str(dt[t]["within_base"]) for t in columns) + " |")
    md += ["", "### Reasons of the misses", "", "| reason | " + " | ".join(columns) + " | share |",
           "| --- | " + " | ".join(["---:"] * (len(columns) + 1)) + " |"]
    for reason in study["reasons"]:
        n = a["reasons"][reason]
        md.append(f"| {reason} | " + " | ".join(str(overall[t]["reasons"][reason]) for t in columns)
                  + f" | {_pct(n / a['misses']) if a['misses'] else '-'} |")
    zones, lifts = rules_["zones"], rules_["lifts"]
    md += ["", "## Clearance misses with a no-fall zone or A-frames", "",
           f"The clearance misses ({', '.join(rules_['zone_lift_reasons'])}) checked again at each end zone (rows) "
           "and A-frame lift (columns) by the search's rule: the pairs of anchors within the tolerance, of the known "
           "line's length within it too, that passed the search's length range and the height difference, a zone at "
           f"most {100 * rules_['zone_cap']:g} % of a line's length, "
           "under nmpt reject the surface too, the pairs over the wall-angle limit left out. A cell counts the misses "
           f"some pair of which would be valid there, {legend}. A column, not the verdict: the verdict stays the "
           "run's rule, today's default no zone and no lift."]
    for name in [*rules_["zone_lift_reasons"], "both"]:
        title = "Both reasons" if name == "both" else name
        md += ["", f"{title}: " + headline(lambda s: str(s["zone_lift"]["rows"][name]["misses"])) + " misses.", "",
               "| zone \\ lift | " + " | ".join(f"{h:g} m" for h in lifts) + " |",
               "| --- | " + " | ".join(["---:"] * len(lifts)) + " |"]
        for j, z in enumerate(zones):
            md.append(f"| {z:g} m | " + " | ".join(_zone_cell(overall, name, j, k, types) for k in range(len(lifts)))
                      + " |")
    for dimension in DIMENSIONS:
        table = study["by"][dimension]
        md += ["", f"## By {dimension}", "",
               f"| {dimension} | known | verifiable | matched | recall | clean recall | terrain recall | "
               "clearance p50 | over trees | wall angle p50 |", "| --- | " + " | ".join(["---:"] * 9) + " |"]
        for key, s in table.items():
            b = s["all"]
            md.append(f"| {key} | {_cell(s, 'known', types)} | {_cell(s, 'verifiable', types)} | "
                      f"{_cell(s, 'matched', types)} | {_cell(s, 'recall', types, pct=True)} | "
                      f"{_cell(s, 'recall_clean', types, pct=True)} | {_cell(s, 'recall_terrain', types, pct=True)} | "
                      f"{b['clearance'][1] if b['clearance'] else '-'} | {_pct(b['over_trees'])} | "
                      f"{b['wall_angle'][1] if b['wall_angle'] else '-'} |")
        used = [reason for reason in study["reasons"] if any(s["all"]["reasons"][reason] for s in table.values())]
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
    md += ["", "## Places", "", "Spots without a known line: found spots none of whose lines is a candidate of a "
           "known line of a good geometry (a precision proxy only).", "",
           "| place | source | res | found lines | found spots | spots without a known line | known | matched |",
           "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for s in study["places"]:
        known = f"{s['known']} (" + " / ".join(str(s["known_by_type"][t]) for t in types) + ")"
        hits = f"{s['matched']} (" + " / ".join(str(s["matched_by_type"][t]) for t in types) + ")"
        md.append(f"| {s['cluster']} | {s['source']} | {s['resolution']:g} | {s['found_lines']} | {s['found_spots']} | "
                  f"{s['spots_without_known']} | {known} | {hits} |")
    for s in study["failed"]:
        md.append(f"| {s['cluster']} | {_failure_cause(s)} | | | | | {s['known']} | |")
    if study["failed"]:
        causes = collections.Counter(_failure_cause(s) for s in study["failed"])
        places_out, known_out = len(study["failed"]), sum(s["known"] for s in study["failed"])
        md += ["", "## Failed searches", "",
               f"{places_out} place{'' if places_out == 1 else 's'} not analysed, {known_out} known "
               f"line{'' if known_out == 1 else 's'} left out; by "
               "cause: " + ", ".join(f"{cause} {count}" for cause, count in
                                     sorted(causes.items(), key=lambda kv: (-kv[1], kv[0])))
               + ". A failed search's error is the coded error's code (no code: an error without one), its message "
               "the error's text or the last line the search wrote to stderr (capture.json; the whole output in "
               "the place's output.log).", ""]
        md += [_failure_line(s) for s in study["failed"]]
    names = {os.path.basename(p) for p in study["pictures"]}
    md += ["", "## Misses by place", ""]
    for s in study["places"]:
        entries = study["misses"].get(s["cluster"], [])
        if not entries and f"{s['cluster']}-map.png" not in names:
            continue
        md += [f"### {s['cluster']} ({s['source']}, {s['resolution']:g} m, {s['matched']} of {s['known']} matched)", ""]
        if f"{s['cluster']}-map.png" in names:
            md += [f"![{s['cluster']}](pictures/{s['cluster']}-map.png)", ""]
        for r in entries:
            md.append(_miss_line(r, rules_))
            chip = f"{s['cluster']}-miss-{r['n']}.png"
            if chip in names:
                md.append(f"  ![#{r['n']}](pictures/{chip})")
        md.append("")
    return md


def _chip_pair(r: Dict, z: np.ndarray) -> Optional[Tuple[list, list]]:
    """The pixels a miss's profile chip draws: the funnel's best pair, else the best pair near the known
    ends, else the known end pixels when both lie in the grid, each only with data at both pixels (the
    sag table takes no NaN); None otherwise."""
    h, w = z.shape

    def usable(p, q):
        return all(0 <= v[0] < h and 0 <= v[1] < w and math.isfinite(float(z[v[0], v[1]])) for v in (p, q))

    near = r.get("near") or {}
    for pair in (r.get("best"), near.get("best")):
        if pair and usable(pair["a1"], pair["a2"]):
            return pair["a1"], pair["a2"]
    pixels = [e["pixel"] for e in r.get("ends") or []]
    if len(pixels) == 2 and usable(*pixels):
        lo, hi = sorted(map(tuple, pixels))
        if max(abs(hi[0] - lo[0]), abs(hi[1] - lo[1])) >= 2:
            return list(lo), list(hi)
    return None


def view_box(mask: np.ndarray, grid: Dict, lines: Sequence[KnownLine]) -> Tuple[int, int, int, int]:
    """The pixels a place's picture shows, (row0, row1, col0, col1) half-open: the search area (the
    mask's box: the grid reaches the search's margin beyond it, often more than half of it) and every
    known line's ends, padded by VIEW_PAD, within the grid; the whole grid without an area."""
    h, w = mask.shape
    rows, cols = np.nonzero(np.any(mask, axis=1))[0], np.nonzero(np.any(mask, axis=0))[0]
    if not len(rows):
        return 0, h, 0, w
    r0, r1, c0, c1 = float(rows[0]), float(rows[-1]), float(cols[0]), float(cols[-1])
    for line in lines:
        for point in (line.a, line.b):
            r, c = _pixel_float(grid, *point)
            r0, r1, c0, c1 = min(r0, r), max(r1, r), min(c0, c), max(c1, c)
    pad = max(VIEW_PAD[0], VIEW_PAD[1] * max(r1 - r0, c1 - c0))
    return (max(0, int(math.floor(r0 - pad))), min(h, int(math.ceil(r1 + pad)) + 1),
            max(0, int(math.floor(c0 - pad))), min(w, int(math.ceil(c1 + pad)) + 1))


def draw(out: str, analysis: Dict) -> List[str]:
    """pictures/: a hillshade per place over view_box (the search area outlined, found lines dark grey,
    known lines coloured by outcome, numbered as in study.md) and a profile chip per miss
    (studylib.profile_chip, the reason in its title)."""
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
        r0, r1, c0, c1 = view_box(c.mask, c.grid, c.known)
        k = max(1, int(math.ceil(max(r1 - r0, c1 - c0) / PICTURE_PX)))
        window = c.elevation[r0:r1:k, c0:c1:k]
        shade = coverage_contrast.shade(window, c.res * k)
        fig, ax = plt.subplots(figsize=(9.5, 8))
        ax.imshow(shade, cmap="gray", interpolation="nearest",
                  extent=(c0 - 0.5, c0 + shade.shape[1] * k - 0.5, r0 + shade.shape[0] * k - 0.5, r0 - 0.5))
        area = c.mask[r0:r1:k, c0:c1:k]
        if area.any() and not area.all():
            ax.contour(c0 + np.arange(area.shape[1]) * k, r0 + np.arange(area.shape[0]) * k, area.astype(float),
                       levels=[0.5], colors=AREA_COLOUR, linewidths=0.8, linestyles="--")
        f = c.found
        if len(f):
            rows = np.arange(len(f)) if len(f) <= MAP_LINES else np.sort(rng.choice(len(f), MAP_LINES, replace=False))
            g = c.grid  # (col, row) of the anchors: the image's x and y
            ends = [np.column_stack([(xy[rows, 0] - g["left"]) / g["res"] - 0.5,
                                     (g["top"] - xy[rows, 1]) / g["res"] - 0.5]) for xy in (f.xy1, f.xy2)]
            ax.add_collection(LineCollection(np.stack(ends, axis=1), colors=FOUND_COLOUR, linewidths=0.5, alpha=0.5))
        known = {x.id: x for x in c.known}
        for n, r in enumerate(rs, 1):
            outcome = "unverifiable" if r["reason"] == "unverifiable" else r["outcome"]
            line = c.known[n - 1] if n <= len(c.known) and c.known[n - 1].id == r["id"] else known[r["id"]]
            (ra, ca), (rb, cb) = _pixel_float(c.grid, *line.a), _pixel_float(c.grid, *line.b)
            ax.plot([ca, cb], [ra, rb], color=COLOURS[outcome], lw=1.6)
            ax.annotate(str(n), ((ca + cb) / 2, (ra + rb) / 2), color=COLOURS[outcome], fontsize=8, fontweight="bold")
        ax.set_xlim(c0 - 0.5, c1 - 0.5)
        ax.set_ylim(r1 - 0.5, r0 - 0.5)
        ax.set_xticks([])
        ax.set_yticks([])
        ax.legend(handles=[Line2D([], [], color=FOUND_COLOUR, lw=1, label=f"found ({len(f)})"),
                           Line2D([], [], color=AREA_COLOUR, lw=1, ls="--", label="search area")] +
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
            pair = _chip_pair(r, c.elevation)
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
