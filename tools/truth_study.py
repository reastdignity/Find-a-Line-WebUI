"""
Run by hand: the truth check (2026-11-08): the search measured against the highlines people have
rigged, SlackMap's known lines (tools/slackmap_data.py), by one real search around each cluster of
them, the known lines matched to the lines found and every miss diagnosed on the captured grid
(tools/truth_analysis.py). This tool clusters the known lines, ranks the places and runs the searches:

    uv run tools/truth_study.py fetch [--update] --data-dir <data>
    uv run tools/truth_study.py cluster --out <out> --data-dir <data> [--types h,m] [--country PL SK]
        [--auto | --country-from-lines | --offline-sources] [--extra "<findaline.py options>"]
    uv run tools/truth_study.py places --out <out>
    uv run tools/truth_study.py run --out <out> --data-dir <data> [--ids ID ...] [--country PL] [--source geoportal]
        [--max-clusters N] [--national-only] [--again] [--timeout S] [--parallel N]
    uv run tools/truth_study.py run --out <out> --place NAME=OPTIONS [--known lines.json] [--no-cache-link]
    uv run tools/truth_study.py analyse <out> [--profiles] [--cache <cache> | --data-dir <data>] [--cluster ID ...]
    uv run tools/truth_study.py report <out> [--no-pictures]

fetch is slackmap_data.fetch (the lines and spots files into the data folder's cache).

cluster takes the known lines of the chosen types (covered: highlines and midlines by default, the
user's decision of 2026-11-08: a midline is a sub-class of a highline; letters of slackmap_data.TYPES
or their names) in the countries the catalogue has a source for (Source.countries), and clusters them
per country: each line in the CRS of its country's source (linking_crs: the first source of the
country without regions that covers it, else the one fixed CRS its regional sources share, else the
UTM zone of the line), every pair of anchors within --link metres (scipy's cKDTree.query_pairs) joins
their lines (connected components: union-find), and a group whose circle would pass --radius-max is
bisected along the longer side of its anchors' box (by the lines' midpoints) until each part fits. A
cluster's centre is its anchors' box centre, its radius the farthest anchor plus --margin, at least
--radius-min (never cut below the farthest anchor: a single line longer than the cap keeps its
radius, over_cap). Lines whose anchors lie farther apart than any cluster may reach (twice
--radius-max less the margin: a misplaced anchor) are left out and counted. Each cluster's search:

    --lat --lon --radius, --min-length max(15, 0.8 shortest), --max-length max(100, 1.1 longest),
    --source <id>, <--extra>, --no-plot --yes --ortho never

the lengths of each line its stated and its geodesic length (only the stated one where they
disagree: length_mismatch, the anchors misplaced), the source from sources.choose_source("auto") at
the centre, once per cluster (Nominatim, cached; --country-from-lines: the lines' own country, Nominatim
only for the regions of a country with regional sources; --offline-sources: from
sources.choose.OFFLINE_BOXES alone, no lookup, rough at borders: the first box holding the centre
wins; --auto: none, the search chooses), and the radius measured again in that source's
working CRS (what the search's circle is drawn in). --extra: findaline.py options added to every
cluster's search after --source (--extra "--model sag": the sag estimator; an option without a space
as --extra=--yes; an option the cluster sets already is given twice, and findaline.py takes the
last). A cluster's id is its country and centre ("pl-50.156n19.756e"): the same on the same data.
<out>/clusters.json holds every cluster with its known lines (dataclasses.asdict of
slackmap_data.KnownLine), its options and its "extra" (also in "params"); the summary is printed.

places ranks the clusters by known lines, per country and source, with a ready --lat --lon --radius
and the nearest place of tests/regression.json (its --lat/--lon, or --northing/--easting in EPSG:2180;
tests of an --area left out), "covered by R<n>" within --near metres (2 km): <out>/places.md, printed.

run searches each cluster (or --place NAME=OPTIONS of findaline.py, with the known lines of --known: a
JSON list of KnownLine dicts, or a GeoJSON FeatureCollection of SlackMap-like line features) in a
child process (search-child), one after another (--parallel N: N at once, below), all with one data
folder, <out>/data: its cache/ a link to the real cache for the whole run (studylib.linked_data_folder:
made once at the start, removed at the end, also after an error or Ctrl+C; --no-cache-link: a fresh
cache of its own in it), its runs/ every cluster's saved run (one copy of the viewer, runs/_viewer, for
them all). It writes,
resumable (a cluster captured with the same options and known lines is not searched again unless
--again; a failed one is; a cluster searched again has its earlier run removed):

    <out>/<cluster>/known.json        the cluster's known lines (KnownLine dicts)
    <out>/<cluster>/output.log        the search's output
    <out>/<cluster>/capture.json      {"status": "done" | "no_lines" | "failed", "seconds", "options", "id",
                                       "returncode", "error" (a SearchError's code), "message", "lines",
                                       "anchors", "source", "finished", "run" (the saved run's folder
                                       relative to <out>, "data/runs/<run>"; null when none was saved:
                                       a search without lines, a failed one)}
    <out>/<cluster>/capture/grid.json {"crs", "left", "top" (the grid's upper left corner), "res",
                                       "shape": [rows, cols], "params": search._run_params, "nmpt",
                                       "obstacles", "model", "rigging", "slope_threshold", "fall"
                                       (helpers.fall_allowance of the run), "layer_meta"
                                       (obstacle_study.layer_meta), "source", "area_wgs84": [S, W, N, E],
                                       and "centre", "radius", "resolution", "end_zone", "lift"}
    <out>/<cluster>/capture/grids.npz elevation (float32: the filled terrain the search used), surface
                                      (float32: the obstacle surface it used; absent without a surface
                                      model), filled, joined, water, covered (uint8; each absent when the
                                      search had none), mask (uint8: the search area)
    <out>/<cluster>/capture/anchors.npy step 2's anchors, int64 (n, 2) pixels (row, col), as search._anchors
                                      returned them (a search stopped in step 2: the steep pixels off the
                                      seams it found, result.json's "anchors": "steep")
    <out>/<cluster>/capture/lines.npz the lines found: a1, a2 (float64 (n, 2) [lat, lon]), length, clearance,
                                      clearance_nmpt (NaN without a surface model), over (bool: over
                                      trees/buildings), rep (bool: a group's representative), group (int64),
                                      and a1_xy, a2_xy (float64 (n, 2), the grid's CRS), elev_a1, elev_a2,
                                      height_max, height_mean, high_pct, angle1, angle2, prom1, prom2,
                                      drop1, drop2, water_m, filled_m (float64), lift_needed, lift_no_zone
                                      (with an end zone or A-frames); every array of length 0 without lines
    <out>/<cluster>/capture/result.json what the child saw: its exit code, the SearchError's code and text,
                                      the saved run's folder (absolute)
    <out>/data/runs/<run>/            the saved run (its map, run.json for analyse --profiles)

A search without lines (findaline.py's exit 1 with a SearchError of NO_LINES: no lines, no steep
terrain, ...) is a result, status "no_lines" (every known line a miss), not a failure. Circles only:
the tiles of an area are not captured.

run --parallel N (default 1) keeps N children running, started in the order of the clusters (the most
known lines first; one waits while a search of the same id runs), looked at by one thread every
POLL_SECONDS; all share the one data folder (the runs' viewer and runs.js go through cache.runs_lock,
the cache's downloads through its tile locks; a fresh cache of --no-cache-link is marked before they
start). One at a time a progress line names the cluster's place in the order, "[k/n] <id>: ...", as
before; with several, the searches finished so far, "[d/n done] <id>: ..." (those captured already
too). Each child makes its searches' work folders inside one folder of the data folder's work/ that run
names for it (search-child --work-id work/truth-<time>-<hex>/: cache.new_work wrapped in the child, its
folder inside named as production names it), and run removes that folder, and only that one, once the
child's process tree has ended: findaline.py on Windows cannot delete its own work folder after a
search that stops without lines, and another child's folders are never touched (nothing goes by age or
by "new in work/"). --timeout is each child's own; a child stopped by it has its process tree killed
(jobs.kill_tree: also the processes it started) and the status "failed". A child's failure never stops
the others. Ctrl+C (or an error of run itself) kills every running child's tree and removes its work
folder: the clusters finished keep their captures, those still running have no capture.json (searched
on the next pass), the cache is unlinked and the interruption goes on (the exit code as before).

analyse and report are tools/truth_analysis.py's (truth_analysis.analyse, truth_analysis.report);
analyse --profiles computes in <out>/data, its cache/ linked to --cache (default: the data folder's
cache) while the analysis runs when it has none.

SlackMap's data have no published licence: nothing of them goes into the repository (the tests use
synthetic lines); the study's outputs belong outside it (a scratchpad, local/).
"""

import argparse
import collections
import contextlib
import dataclasses
import json
import math
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
import traceback
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "tools"))
sys.path.insert(0, os.path.join(HERE, "tests"))

import numpy as np  # noqa: E402

import cache  # noqa: E402
import slackmap_data as sd  # noqa: E402
from studylib import _unlink, linked_data_folder  # noqa: E402

DEFAULT_TYPES = ("h", "m")  # highlines and midlines (a midline: a highline's sub-class, the user's decision)
LINK_M = 300.0              # anchors this near join their lines into one cluster
MARGIN_M = 50.0             # the radius: the farthest anchor plus this
RADIUS_MIN = 200.0          # metres: no search circle smaller
RADIUS_MAX = 1500.0         # metres: a cluster whose circle would be larger is bisected
MIN_LENGTH_FLOOR, MIN_LENGTH_SHARE = 15.0, 0.8   # --min-length max(15, 0.8 * shortest)
MAX_LENGTH_FLOOR, MAX_LENGTH_SHARE = 100.0, 1.1  # --max-length max(100, 1.1 * longest)
FIXED_OPTIONS = ("--no-plot", "--yes", "--ortho", "never")
NEAR_M = 2000.0             # places: a regression test this near a cluster's centre covers it
NO_LINES = ("no_lines", "no_steep_terrain", "no_prominent_anchors", "no_anchors_in_elevation_range")
STATUSES = ("done", "no_lines", "failed")
NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}")  # a place's or cluster's name: it names a folder
SOURCE_MODES = ("nominatim", "lines", "offline", "defer")
LINE_EXTRAS = ("elev_a1", "elev_a2", "height_max", "height_mean", "high_pct", "angle1", "angle2", "prom1", "prom2",
               "drop1", "drop2", "water_m", "filled_m")
DEFAULT_RADIUS = 1000.0     # findaline.py's --radius when a regression test gives none (params.SearchParams)
POLL_SECONDS = 0.2          # run: how often the running children are looked at


# ---------------------------------------------------------------------------------------------
# the known lines of the study

def type_names(types: Iterable[str]) -> Tuple[str, ...]:
    """The type names of letters (slackmap_data.TYPES: h, m, ...) or names (highline, other, unknown)."""
    names = []
    for value in types:
        t = str(value).strip().lower()
        if not t:
            continue
        if t in sd.TYPES:
            names.append(sd.TYPES[t])
        elif t in sd.TYPES.values() or t in ("other", "unknown"):
            names.append(t)
        else:
            raise ValueError(f"not a line type: {value!r} (letters {', '.join(sd.TYPES)}, or their names)")
    if not names:
        raise ValueError("no line type given")
    return tuple(dict.fromkeys(names))


def catalogue_countries() -> set:
    """The countries (upper case) some source of the catalogue names (Source.countries)."""
    import sources
    return {code.upper() for source in sources.SOURCES.values() for code in source.countries}


def covered(lines: Iterable[sd.KnownLine], types: Iterable[str] = DEFAULT_TYPES) -> List[sd.KnownLine]:
    """The known lines of the types (letters or names) whose country a source of the catalogue names."""
    names, countries = type_names(types), catalogue_countries()
    return [line for line in lines if line.type in names and line.country in countries]


def linking_crs(country: Optional[str], lat: float, lon: float) -> str:
    """The metric CRS a line of a country is clustered in: the working CRS of the first source of the
    country without regions that covers the point (Source.covers; the order of sources.SOURCES), else
    the one fixed CRS of the country's regional sources when they share one (Great Britain's
    EPSG:27700), else the UTM zone of the point (Germany's Länder in EPSG:25832 and 25833)."""
    import sources
    from grid import utm_crs
    code = (country or "").lower()
    found = [s for s in sources.SOURCES.values() if code and code in s.countries and s.covers(lat, lon)]
    plain = [s for s in found if not s.regions]
    if plain:
        return plain[0].working_crs(lat, lon)
    fixed = {s.crs for s in found}
    if len(fixed) == 1 and None not in fixed:
        return fixed.pop()
    return utm_crs(lat, lon)


def line_span(line: sd.KnownLine) -> Tuple[float, float]:
    """The lengths a line may have in the search: its stated and its geodesic length (only the stated
    one when they disagree, length_mismatch: its anchors are misplaced, not its length)."""
    values = [] if "length_mismatch" in line.flags else [line.geodesic_m]
    if line.stated_m is not None:
        values.append(line.stated_m)
    return min(values), max(values)


# ---------------------------------------------------------------------------------------------
# clusters

@dataclass
class Cluster:
    """A cluster of known lines: one search (its options)."""
    id: str
    country: str
    crs: str                         # the CRS it was clustered in (linking_crs)
    centre: Tuple[float, float]      # (lat, lon) of its anchors' box centre
    radius: float                    # metres of the search circle (in search_crs once a source is chosen)
    farthest: float                  # metres from the centre to its farthest anchor (likewise)
    lines: List[sd.KnownLine]
    split: int = 0                   # bisections that made it (0: a whole linked group)
    radius_max: float = RADIUS_MAX
    source: Optional[str] = None     # --source of its search (None: the search chooses)
    reason: Optional[str] = None     # why that source (sources.choose_source)
    national: Optional[bool] = None  # the source colours the coverage map (not a gap filler, not FABDEM)
    search_crs: Optional[str] = None  # the source's working CRS at the centre
    extra: str = ""                  # findaline.py options added to its search (cluster --extra)

    @property
    def over_cap(self) -> bool:
        return self.radius > self.radius_max

    @property
    def shortest(self) -> float:
        return min(line_span(line)[0] for line in self.lines)

    @property
    def longest(self) -> float:
        return max(line_span(line)[1] for line in self.lines)

    @property
    def min_length(self) -> float:
        return max(MIN_LENGTH_FLOOR, math.floor(round(MIN_LENGTH_SHARE * self.shortest, 6)))

    @property
    def max_length(self) -> float:
        return max(MAX_LENGTH_FLOOR, math.ceil(round(MAX_LENGTH_SHARE * self.longest, 6)))

    @property
    def types(self) -> Dict[str, int]:
        return dict(sorted(collections.Counter(line.type for line in self.lines).items()))

    @property
    def options(self) -> str:
        """findaline.py's options of its search."""
        lat, lon = self.centre
        parts = [f"--lat {lat:.6f}", f"--lon {lon:.6f}", f"--radius {self.radius:g}",
                 f"--min-length {self.min_length:g}", f"--max-length {self.max_length:g}"]
        if self.source:
            parts.append(f"--source {self.source}")
        if self.extra:
            parts.append(self.extra)
        return " ".join(parts + list(FIXED_OPTIONS))

    def as_dict(self) -> Dict:
        return {"id": self.id, "country": self.country, "crs": self.crs, "search_crs": self.search_crs,
                "centre": [round(self.centre[0], 7), round(self.centre[1], 7)], "radius": self.radius,
                "farthest": round(self.farthest, 2), "split": self.split, "over_cap": self.over_cap,
                "source": self.source, "reason": self.reason, "national": self.national, "types": self.types,
                "count": len(self.lines), "lines": [line.id for line in self.lines],
                "shortest": round(self.shortest, 2), "longest": round(self.longest, 2),
                "min_length": self.min_length, "max_length": self.max_length, "extra": self.extra,
                "options": self.options, "known": [dataclasses.asdict(line) for line in self.lines]}


def _transformer(source: str, target: str):
    from studylib import _transformer as cached
    return cached(source, target)


def _anchors_xy(lines: Sequence[sd.KnownLine], crs: str) -> np.ndarray:
    """The anchors of the lines in crs: (2n, 2) [x, y], line k's at rows 2k and 2k + 1."""
    lat = np.array([v for line in lines for v in (line.a[0], line.b[0])], dtype=np.float64)
    lon = np.array([v for line in lines for v in (line.a[1], line.b[1])], dtype=np.float64)
    x, y = _transformer("EPSG:4326", crs).transform(lon, lat)
    return np.column_stack([np.asarray(x, dtype=np.float64), np.asarray(y, dtype=np.float64)])


def _box(points: np.ndarray) -> Tuple[np.ndarray, float, np.ndarray]:
    """The centre of the points' box, the distance of the farthest point from it, the box's sides."""
    lo, hi = points.min(axis=0), points.max(axis=0)
    centre = (lo + hi) / 2
    return centre, float(np.hypot(*(points - centre).T).max()), hi - lo


def _radius(farthest: float, margin_m: float, radius_min: float) -> float:
    return float(max(radius_min, math.ceil(round(farthest + margin_m, 6))))


def _bisect(idx: np.ndarray, xy: np.ndarray, margin_m: float, radius_max: float, depth: int = 0) -> List[tuple]:
    """(lines, box centre, farthest, depth) of a linked group, halved along the longer side of its
    anchors' box (by the lines' midpoints; at their median when the middle leaves a side empty)
    while its circle passes radius_max."""
    points = xy[np.concatenate([2 * idx, 2 * idx + 1])]
    centre, farthest, sides = _box(points)
    if farthest + margin_m <= radius_max or len(idx) < 2:
        return [(idx, centre, farthest, depth)]
    axis = int(np.argmax(sides))
    mids = (xy[2 * idx, axis] + xy[2 * idx + 1, axis]) / 2
    left = mids < centre[axis]
    if left.all() or not left.any():
        left = np.zeros(len(idx), dtype=bool)
        left[np.argsort(mids, kind="stable")[:len(idx) // 2]] = True
    return (_bisect(idx[left], xy, margin_m, radius_max, depth + 1)
            + _bisect(idx[~left], xy, margin_m, radius_max, depth + 1))


def cluster_id(country: str, lat: float, lon: float) -> str:
    """A cluster's name: its country and centre to 3 decimals ("pl-50.156n19.756e")."""
    return (f"{(country or 'xx').lower()}-{abs(lat):.3f}{'n' if lat >= 0 else 's'}"
            f"{abs(lon):.3f}{'e' if lon >= 0 else 'w'}")


def reach_limit(margin_m: float = MARGIN_M, radius_max: float = RADIUS_MAX) -> float:
    """The anchors of a line farther apart than this fit no cluster's circle."""
    return 2 * (radius_max - margin_m)


def cluster(lines: Iterable[sd.KnownLine], link_m: float = LINK_M, margin_m: float = MARGIN_M,
            radius_min: float = RADIUS_MIN, radius_max: float = RADIUS_MAX,
            types: Iterable[str] = DEFAULT_TYPES) -> List[Cluster]:
    """The clusters of the known lines of the types (letters or names; every line carries its type):
    per country (lines without one under "XX"), each line in its linking_crs, anchors within link_m
    joining their lines (cKDTree.query_pairs, connected components), a group bisected while its
    circle (farthest anchor + margin_m) passes radius_max; radius at least radius_min. Lines whose
    anchors lie farther apart than reach_limit are left out (a misplaced anchor). No source chosen
    (with_sources). Sorted by country, then the most lines first, then id; the lines of a cluster by
    their id."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    from scipy.spatial import cKDTree

    names = type_names(types)
    limit = reach_limit(margin_m, radius_max)
    groups: Dict[Tuple[str, str], List[sd.KnownLine]] = collections.defaultdict(list)
    for line in lines:
        if line.type not in names or line.geodesic_m > limit:
            continue
        lat, lon = (line.a[0] + line.b[0]) / 2, (line.a[1] + line.b[1]) / 2
        groups[(line.country or "XX", linking_crs(line.country, lat, lon))].append(line)
    found: List[Cluster] = []
    for (country, crs), members in sorted(groups.items()):
        members = sorted(members, key=lambda line: line.id)
        xy = _anchors_xy(members, crs)
        pairs = cKDTree(xy).query_pairs(link_m, output_type="ndarray")
        n = len(members)
        graph = coo_matrix((np.ones(len(pairs)), (pairs[:, 0] // 2, pairs[:, 1] // 2)), shape=(n, n))
        count, labels = connected_components(graph, directed=False)
        back = _transformer(crs, "EPSG:4326")
        for label in range(count):
            for idx, centre, farthest, depth in _bisect(np.flatnonzero(labels == label), xy, margin_m, radius_max):
                lon, lat = back.transform(float(centre[0]), float(centre[1]))
                found.append(Cluster(id=cluster_id(country, lat, lon), country=country, crs=crs, centre=(lat, lon),
                                     radius=_radius(farthest, margin_m, radius_min), farthest=farthest,
                                     lines=[members[k] for k in idx], split=depth, radius_max=radius_max))
    seen: Dict[str, int] = {}
    for c in sorted(found, key=lambda c: (c.id, c.centre, c.lines[0].id)):  # the same names on the same data
        seen[c.id] = seen.get(c.id, 0) + 1
        if seen[c.id] > 1:
            c.id = f"{c.id}-{seen[c.id]}"
    return sorted(found, key=lambda c: (c.country, -len(c.lines), c.id))


@contextlib.contextmanager
def offline_lookups():
    """sources.choose_source without Nominatim: osm.reverse refuses, so country_code and region_codes
    take sources.choose.OFFLINE_BOXES (the first box holding the point)."""
    import osm
    import requests
    original = osm.reverse

    def refuse(*args, **kwargs):
        raise requests.ConnectionError("truth_study --offline-sources: no Nominatim lookup")

    osm.reverse = refuse
    try:
        yield
    finally:
        osm.reverse = original


@contextlib.contextmanager
def countries_from_lines(current: Dict):
    """sources.choose_source with the country of current["code"] (the cluster's lines' own country)
    instead of Nominatim's at zoom 3: sources.choose.country_code answers it; the regions of a country
    with regional sources are still looked up (region_codes)."""
    from sources import choose
    original = choose.country_code
    choose.country_code = lambda lat, lon, cache_dir: current.get("code")
    try:
        yield
    finally:
        choose.country_code = original


def measured_again(c: Cluster, crs: str, margin_m: float, radius_min: float):
    """The cluster's farthest anchor and radius around its centre in crs (the search's circle)."""
    xy = _anchors_xy(c.lines, crs)
    x, y = _transformer("EPSG:4326", crs).transform(c.centre[1], c.centre[0])
    c.farthest = float(np.hypot(xy[:, 0] - x, xy[:, 1] - y).max())
    c.radius = _radius(c.farthest, margin_m, radius_min)
    c.search_crs = crs


def with_sources(clusters: List[Cluster], cache_dir: str, mode: str = "nominatim", margin_m: float = MARGIN_M,
                 radius_min: float = RADIUS_MIN, say: Optional[Callable[[str], None]] = None) -> List[Cluster]:
    """Each cluster's source: sources.choose_source("auto") at its centre, once (mode "nominatim": its
    lookups, cached in the data folder; "lines": the country of the cluster's lines instead of the
    lookup of the country, the regions still looked up where a country has regional sources;
    "offline": OFFLINE_BOXES alone, no lookup; "defer": none, the search chooses), and its radius
    measured again in that source's working CRS. Returns the clusters."""
    if mode not in SOURCE_MODES:
        raise ValueError(f"mode {mode!r}: one of {', '.join(SOURCE_MODES)}")
    if mode == "defer":
        for c in clusters:
            c.source = c.reason = c.national = None
            c.search_crs = c.crs
        return clusters
    import sources
    current: Dict = {}
    with contextlib.ExitStack() as stack:
        if mode == "offline":
            stack.enter_context(offline_lookups())
        if mode == "lines":
            stack.enter_context(countries_from_lines(current))
        for k, c in enumerate(clusters):
            current["code"] = None if c.country == "XX" else c.country.lower()
            source, reason = sources.choose_source("auto", c.centre[0], c.centre[1], cache_dir)
            c.source, c.reason, c.national = source.id, reason, source.coverage is not None
            measured_again(c, source.working_crs(*c.centre), margin_m, radius_min)
            if say and (k + 1) % 25 == 0:
                say(f"sources: {k + 1} of {len(clusters)} clusters")
    return clusters


def write_clusters(out: str, clusters: List[Cluster], params: Dict, left_out: int = 0) -> str:
    """<out>/clusters.json: the clusters with their known lines and options."""
    os.makedirs(out, exist_ok=True)
    path = os.path.join(out, "clusters.json")
    data = {"made": datetime.now(timezone.utc).isoformat(timespec="seconds"), "params": params,
            "lines": sum(len(c.lines) for c in clusters), "left_out": left_out,
            "clusters": [c.as_dict() for c in clusters]}
    with cache.replacing(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
    return path


def load_clusters(out: str) -> List[Dict]:
    """The clusters of <out>/clusters.json (dicts as Cluster.as_dict writes them)."""
    path = os.path.join(out, "clusters.json")
    if not os.path.exists(path):
        raise FileNotFoundError(f"{path} is missing: run `cluster --out {out}` first")
    with open(path, encoding="utf-8") as f:
        return json.load(f)["clusters"]


def _quantiles(values: Sequence[float], qs=(0, 10, 50, 90, 100)) -> str:
    if not len(values):
        return "-"
    return ", ".join(f"p{q} {np.percentile(values, q):.0f}" for q in qs)


def summary(clusters: List[Cluster], left_out: int = 0, radius_min: float = RADIUS_MIN) -> str:
    """Clusters per country and source, their radii, the caps hit, lines per cluster."""
    lines = sum(len(c.lines) for c in clusters)
    types = collections.Counter(line.type for c in clusters for line in c.lines)
    out = [f"{len(clusters)} clusters of {lines} known lines ("
           + ", ".join(f"{n} {t}" for t, n in sorted(types.items())) + ")"
           + (f"; {left_out} lines left out (anchors farther apart than a cluster may reach)" if left_out else "")]
    radii = [c.radius for c in clusters]
    counts = [len(c.lines) for c in clusters]
    out.append(f"Radius (m): {_quantiles(radii)}; at the minimum {sum(c.radius <= radius_min for c in clusters)}")
    edges = (0, 200, 300, 500, 750, 1000, 1500, 10 ** 9)
    bins = np.histogram(radii, bins=edges)[0] if radii else [0] * (len(edges) - 1)
    out.append("Radius bins: " + ", ".join(f"{a}-{b if b < 10 ** 9 else ''}: {n}"
                                           for a, b, n in zip(edges[:-1], edges[1:], bins)))
    out.append(f"Over the cap: {sum(c.over_cap for c in clusters)}; made by bisection: "
               f"{sum(c.split > 0 for c in clusters)} (deepest {max((c.split for c in clusters), default=0)})")
    out.append(f"Lines per cluster: {_quantiles(counts)}; mean {np.mean(counts) if counts else 0:.2f}; "
               f"single lines {sum(n == 1 for n in counts)}")
    out.append("")
    out.append("country source               clusters lines (h/m) radius p50  national")
    per = collections.defaultdict(list)
    for c in clusters:
        per[(c.country, c.source or "auto")].append(c)
    for (country, source), group in sorted(per.items(), key=lambda kv: (-sum(len(c.lines) for c in kv[1]), kv[0])):
        n = sum(len(c.lines) for c in group)
        h = sum(line.type == "highline" for c in group for line in c.lines)
        m = sum(line.type == "midline" for c in group for line in c.lines)
        national = group[0].national
        out.append(f"{country:<7} {source:<24} {len(group):>5} {n:>5} ({h}/{m}) "
                   f"{np.median([c.radius for c in group]):>8.0f}  {'-' if national is None else national}")
    return "\n".join(out)


# ---------------------------------------------------------------------------------------------
# places

def _option(args: List[str], name: str) -> Optional[str]:
    value = None
    for k, arg in enumerate(args):
        if arg == name and k + 1 < len(args):
            value = args[k + 1]
        elif arg.startswith(name + "="):
            value = arg.split("=", 1)[1]
    return value


def regression_places(path: Optional[str] = None) -> List[Dict]:
    """The places of tests/regression.json (or path): {"id", "lat", "lon", "radius"} of each test with
    --lat/--lon or --northing/--easting (EPSG:2180), its "extends" followed; tests of an --area (and
    without a place, the osm kind) left out."""
    import regression
    if path is None:
        path = regression.TESTS
    with open(path, encoding="utf-8") as f:
        tests = json.load(f)
    found = []
    for test_id, test in tests.items():
        if "args" not in test and "extends" not in test:
            continue
        args = regression.full_args(tests, test_id)
        if _option(args, "--area") is not None:
            continue
        lat, lon = _option(args, "--lat"), _option(args, "--lon")
        northing, easting = _option(args, "--northing"), _option(args, "--easting")
        if lat is not None and lon is not None:
            lat, lon = float(lat), float(lon)
        elif northing is not None and easting is not None:
            lon, lat = _transformer("EPSG:2180", "EPSG:4326").transform(float(easting), float(northing))
        else:
            continue
        radius = _option(args, "--radius")
        found.append({"id": test_id, "lat": float(lat), "lon": float(lon),
                      "radius": float(radius) if radius is not None else DEFAULT_RADIUS})
    return found


def places(clusters: List[Dict], tests: List[Dict], near_m: float = NEAR_M) -> List[Dict]:
    """The clusters (dicts of clusters.json) ranked by known lines (then id), each with its ready
    --lat --lon --radius, the nearest regression test and its distance in metres, and the test that
    covers it (within near_m of its centre) or None."""
    from pyproj import Geod
    geod = Geod(ellps="WGS84")
    rows = []
    t_lat = np.array([t["lat"] for t in tests], dtype=np.float64)
    t_lon = np.array([t["lon"] for t in tests], dtype=np.float64)
    for c in clusters:
        lat, lon = c["centre"]
        row = {"id": c["id"], "country": c["country"], "source": c.get("source") or "auto",
               "count": len(c["lines"]), "types": c.get("types") or {}, "radius": c["radius"],
               "where": f"--lat {lat:.6f} --lon {lon:.6f} --radius {c['radius']:g}",
               "lengths": [c.get("min_length"), c.get("max_length")], "nearest": None, "distance": None,
               "covered_by": None}
        if len(tests):
            distance = geod.inv(np.full(len(tests), lon), np.full(len(tests), lat), t_lon, t_lat)[2]
            k = int(np.argmin(distance))
            row["nearest"], row["distance"] = tests[k]["id"], float(distance[k])
            if distance[k] <= near_m:
                row["covered_by"] = tests[k]["id"]
        rows.append(row)
    return sorted(rows, key=lambda r: (-r["count"], r["id"]))


def _types_text(types: Dict[str, int]) -> str:
    return f"{types.get('highline', 0)}/{types.get('midline', 0)}"


def _nearest_text(row: Dict) -> str:
    if row["nearest"] is None:
        return "-"
    text = f"{row['nearest']} ({row['distance'] / 1000:.1f} km)"
    return f"**covered by {row['covered_by']}**, {text}" if row["covered_by"] else text


def places_markdown(rows: List[Dict], top: int = 20, per_group: int = 10, near_m: float = NEAR_M) -> str:
    """places.md: the top clusters, then per country and source."""
    total = sum(r["count"] for r in rows)
    covered_rows = [r for r in rows if r["covered_by"]]
    head = "| # | cluster | country | source | lines (h/m) | where | lengths | nearest regression test |"
    out = ["# Places with known highlines", "",
           f"{len(rows)} clusters of {total} known lines (highline/midline), ranked by known lines; the nearest "
           f"place of tests/regression.json, \"covered by\" within {near_m / 1000:g} km of the cluster's centre "
           f"({len(covered_rows)} clusters, {sum(r['count'] for r in covered_rows)} lines). The study's own "
           "search of a cluster: its options in clusters.json.", "",
           f"## The top {min(top, len(rows))}", "", head, "|" + " --- |" * 8]
    for k, r in enumerate(rows[:top], 1):
        out.append(f"| {k} | {r['id']} | {r['country']} | {r['source']} | {r['count']} ({_types_text(r['types'])}) "
                   f"| `{r['where']}` | {r['lengths'][0]:g}-{r['lengths'][1]:g} m | {_nearest_text(r)} |")
    out += ["", "## By country and source", ""]
    groups = collections.defaultdict(list)
    for r in rows:
        groups[(r["country"], r["source"])].append(r)
    for (country, source), group in sorted(groups.items(), key=lambda kv: (-sum(r["count"] for r in kv[1]), kv[0])):
        n = sum(r["count"] for r in group)
        h = sum(r["types"].get("highline", 0) for r in group)
        m = sum(r["types"].get("midline", 0) for r in group)
        covered_by = sorted({r["covered_by"] for r in group if r["covered_by"]})
        out += [f"### {country}, {source}: {len(group)} clusters, {n} lines (highlines {h}, midlines {m})"
                + (f"; covered by {', '.join(covered_by)}" if covered_by else ""), "",
                "| cluster | lines (h/m) | where | lengths | nearest regression test |", "|" + " --- |" * 5]
        for r in group[:per_group]:
            out.append(f"| {r['id']} | {r['count']} ({_types_text(r['types'])}) | `{r['where']}` | "
                       f"{r['lengths'][0]:g}-{r['lengths'][1]:g} m | {_nearest_text(r)} |")
        if len(group) > per_group:
            out.append(f"| {len(group) - per_group} more | {sum(r['count'] for r in group[per_group:])} | | | |")
        out.append("")
    return "\n".join(out)


def write_places(out: str, regression_json: Optional[str] = None, top: int = 20, per_group: int = 10,
                 near_m: float = NEAR_M) -> str:
    """<out>/places.md from <out>/clusters.json; returns its text."""
    rows = places(load_clusters(out), regression_places(regression_json), near_m)
    text = places_markdown(rows, top, per_group, near_m)
    with open(os.path.join(out, "places.md"), "w", encoding="utf-8") as f:
        f.write(text)
    return text


# ---------------------------------------------------------------------------------------------
# run: a search per cluster

def split_options(text: str) -> List[str]:
    """findaline.py's options of a text: split as a shell would, quotes kept together, backslashes
    literal (Windows paths)."""
    lexer = shlex.shlex(text, posix=True)
    lexer.whitespace_split = True
    lexer.escape = ""
    return list(lexer)


def known_lines(path: str) -> List[sd.KnownLine]:
    """The known lines of a file: a JSON list of KnownLine dicts (a known.json), or a GeoJSON
    FeatureCollection of SlackMap-like line features (slackmap_data.normalise)."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict) and data.get("type") == "FeatureCollection":
        return [sd.normalise(feature) for feature in data["features"]]
    if isinstance(data, list):
        return [sd.KnownLine.from_dict(item) for item in data]
    raise ValueError(f"{path}: neither a list of known lines nor a FeatureCollection")


def _check_name(name: str) -> str:
    if not NAME.fullmatch(name):
        raise ValueError(f"{name!r}: a name of letters, digits, '.', '_' and '-' (it names a folder)")
    return name


def _read_json(path: str) -> Optional[Dict]:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def captured(folder: str, options: str, ids: Sequence[str]) -> Optional[str]:
    """The status of a cluster's capture when it is done (or a search without lines) with these
    options and known lines; None otherwise (not run, failed, other options or lines)."""
    state = _read_json(os.path.join(folder, "capture.json"))
    known = _read_json(os.path.join(folder, "known.json"))
    if not state or known is None or state.get("status") not in ("done", "no_lines"):
        return None
    if state.get("options") != options or sorted(str(k.get("id")) for k in known) != sorted(map(str, ids)):
        return None
    return state["status"]


def status_of(returncode: Optional[int], child: Optional[Dict]) -> str:
    """done: the search ended well with its capture; no_lines: it found none (a SearchError of NO_LINES)
    with its capture written; failed otherwise (another error, a timeout, a capture missing)."""
    child = child or {}
    if returncode == 0 and child.get("complete"):
        return "done"
    if child.get("complete") and child.get("error") in NO_LINES:
        return "no_lines"
    return "failed"


def _relative_run(out: str, run: Optional[str]) -> Optional[str]:
    """A saved run's folder relative to <out> with forward slashes ("data/runs/<run>"), None for none."""
    return os.path.relpath(run, os.path.abspath(out)).replace(os.sep, "/") if run else None


def _remove_run(out: str, folder: str):
    """The run an earlier search of a cluster saved (its capture.json's "run"), when it lies in
    <out>/data/runs/: a cluster searched again keeps only its new run."""
    run = (_read_json(os.path.join(folder, "capture.json")) or {}).get("run")
    if not run:
        return
    runs = os.path.join(os.path.abspath(out), "data", "runs")
    path = os.path.normpath(os.path.join(os.path.abspath(out), run))
    if os.path.dirname(path) == runs and os.path.isdir(path) and not os.path.islink(path):
        shutil.rmtree(path)


def _work_id(data: str) -> str:
    """A name for one child's folder in <data>/work, not taken there: "truth-<time>-<6 hex digits>"."""
    while True:
        work_id = f"truth-{datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}"
        if not os.path.lexists(os.path.join(data, "work", work_id)):
            return work_id


def _remove_work(data: str, work_id: str):
    """One child's folder in the data folder's work/, <data>/work/<work_id>, once the child's process tree
    has ended. The child makes its searches' work folders inside it (search-child --work-id: cache.new_work
    wrapped), so this removes what its search left and nothing of another child running beside it:
    findaline.py on Windows cannot delete its own work folder after a search that stops without lines
    (cache.remove_work's "Could not delete the work folder": the memory-mapped grids are still referenced
    by the exception in flight), and every cluster's search shares the one data folder."""
    path = os.path.join(data, "work", work_id)
    if os.path.isdir(path) and not os.path.islink(path):
        shutil.rmtree(path, ignore_errors=True)


def child_command(capture: str, options: str, data: str, work_id: str) -> List[str]:
    """The command of one cluster's search: this script's search-child (the tests put a stand-in here)."""
    return [sys.executable, os.path.abspath(__file__), "search-child", "--out", capture, "--work-id", work_id, "--",
            *split_options(options), "--data-dir", data]


@dataclass
class Child:
    """A cluster's search running in its child process."""
    k: int                       # its place in the order of the items (from 1)
    name: str
    options: str
    folder: str                  # <out>/<name>
    data: str                    # the data folder
    work_id: str                 # its folder in <data>/work (_remove_work)
    process: subprocess.Popen
    log: object                  # output.log: the child's stdout and stderr
    started: float


def start_child(out: str, k: int, name: str, options: str, known: List[Dict], data: str) -> Child:
    """One search started in a fresh <out>/<name>/ (an earlier search's folder and run removed): its
    known.json written, the child's output into output.log, its work folders in <data>/work/<work id>."""
    folder = os.path.join(os.path.abspath(out), _check_name(name))
    if os.path.exists(folder):
        _remove_run(out, folder)
        _unlink(os.path.join(folder, "data", "cache"))  # a data folder of its own (before 2026-11-08): the link only
        shutil.rmtree(folder)
    os.makedirs(folder)
    with open(os.path.join(folder, "known.json"), "w", encoding="utf-8") as f:
        json.dump(known, f, indent=1, ensure_ascii=False)
    env = {**os.environ, "FINDALINE_PROGRESS": "text", "PYTHONIOENCODING": "utf-8"}
    started = time.time()
    work_id = _work_id(data)
    log = open(os.path.join(folder, "output.log"), "w", encoding="utf-8")
    try:
        process = subprocess.Popen(child_command(os.path.join(folder, "capture"), options, data, work_id),
                                   cwd=HERE, env=env, stdout=log, stderr=subprocess.STDOUT)
    except BaseException:
        log.close()
        raise
    return Child(k, name, options, folder, data, work_id, process, log, started)


def _kill(child: Child):
    """A running child's process tree ended (jobs.kill_tree: also the processes it started)."""
    import jobs
    if child.process.poll() is None:  # never the number of a process ended and gone (it may be another's now)
        jobs.kill_tree(child.process.pid)
    child.process.wait()


def _drop(child: Child):
    """A child stopped unfinished (Ctrl+C, an error of the run itself): its tree ended, its work folder
    removed, no capture.json (the cluster is searched on the next pass)."""
    try:
        _kill(child)
    finally:
        child.log.close()
        _remove_work(child.data, child.work_id)


def _anchor_count(path: str) -> Optional[int]:
    """The anchors of a capture's anchors.npy; None without one (or a part of one: a child killed while
    writing it)."""
    try:
        return int(np.load(path).shape[0]) if os.path.exists(path) else None
    except (OSError, ValueError, EOFError):
        return None


def finish_child(out: str, child: Child, timeout: Optional[float] = None) -> Dict:
    """The capture.json of a child whose process has ended (timeout: stopped after that many seconds, its
    tree killed), written into its folder once its work folder is removed; returns it."""
    returncode = None if timeout is not None else child.process.returncode
    try:
        if timeout is not None:
            child.log.write(f"\ntruth_study: stopped after {timeout:g} s\n")
    finally:
        child.log.close()
        _remove_work(child.data, child.work_id)
    capture = os.path.join(child.folder, "capture")
    result = _read_json(os.path.join(capture, "result.json")) or {}
    grid = _read_json(os.path.join(capture, "grid.json")) or {}
    state = {"status": status_of(returncode, result), "seconds": round(time.time() - child.started, 1),
             "options": child.options, "id": child.name, "returncode": returncode,
             "error": result.get("error") or ("timeout" if returncode is None else None),
             "message": result.get("message"), "lines": result.get("lines"),
             "anchors": _anchor_count(os.path.join(capture, "anchors.npy")),
             "source": grid.get("source"), "finished": datetime.now(timezone.utc).isoformat(timespec="seconds"),
             "run": _relative_run(out, result.get("run"))}
    with open(os.path.join(child.folder, "capture.json"), "w", encoding="utf-8") as f:
        json.dump(state, f, indent=1, ensure_ascii=False)
    return state


def run_one(out: str, name: str, options: str, known: List[Dict], data: str,
            timeout: Optional[float] = None) -> Dict:
    """One search with its capture into <out>/<name>/ (a fresh folder; an earlier search's run removed),
    data: the data folder of the search (run's <out>/data, its cache ready); returns its capture.json."""
    return _run_items(out, [{"id": name, "options": options, "known": known}], data, True, timeout,
                      lambda text: None)[name]


def run(out: str, items: List[Dict], cache_dir: Optional[str], again: bool = False, timeout: Optional[float] = None,
        say: Callable[[str], None] = print, parallel: int = 1) -> Dict[str, Dict]:
    """The searches of items ({"id", "options", "known": KnownLine dicts}) one after another, or
    `parallel` at once (started in the items' order), each skipped when captured already with the same
    options and known lines (unless again), all in the data folder <out>/data, its cache/ linked to
    cache_dir while they run (None: a cache of its own, marked before several children start; nothing
    linked when every item is captured already). Returns {id: its capture.json}."""
    if parallel < 1:
        raise ValueError(f"--parallel {parallel}: one search at once or more")
    out = os.path.abspath(out)
    os.makedirs(out, exist_ok=True)
    pending = [item for item in items
               if again or not captured(os.path.join(out, _check_name(item["id"])), item["options"],
                                        [line["id"] for line in item["known"]])]
    with contextlib.ExitStack() as stack:
        data = stack.enter_context(linked_data_folder(out, cache_dir)) if pending else None
        if data and not cache_dir and parallel > 1:
            cache.check_layout(os.path.join(data, "cache"))  # children started together never race to mark it
        return _run_items(out, items, data, again, timeout, say, parallel)


def _outcome(state: Dict) -> str:
    """A finished search's status, lines, seconds and error, as its progress line says them."""
    return (f"{state['status']}, {state['lines'] if state['lines'] is not None else '-'} lines, "
            f"{state['seconds']:.0f} s" + (f" ({state['error']}: {state['message']})"
                                           if state["status"] == "failed" and state.get("message")
                                           else f" ({state['error']})" if state["error"] else ""))


def _run_items(out: str, items: List[Dict], data: Optional[str], again: bool, timeout: Optional[float],
               say: Callable[[str], None], parallel: int = 1) -> Dict[str, Dict]:
    """The items' searches, at most `parallel` children at once, started in the items' order (an item
    waits while a search of the same id runs), looked at every POLL_SECONDS by this one thread. Each line
    said names its cluster: "[k/n] <id>: ..." with its place k in the order when one runs at a time,
    "[d/n done] <id>: ..." with the searches finished so far (those captured already too) when several do.
    A child's failure is its status only; --timeout is each child's own. A child still running when this
    stops (Ctrl+C, an error of the run itself) has its tree killed and leaves no capture.json, the
    finished ones keep theirs, and the exception goes on."""
    found: Dict[str, Dict] = {}
    running: List[Child] = []
    queue = collections.deque(enumerate(items, 1))
    total, finished = len(items), 0

    def tell(k: int, name: str, text: str):
        say(f"[{k}/{total}] {name}: {text}" if parallel == 1 else f"[{finished}/{total} done] {name}: {text}")

    try:
        while queue or running:
            while queue and len(running) < parallel and queue[0][1]["id"] not in {c.name for c in running}:
                k, item = queue.popleft()
                name, options, known = item["id"], item["options"], item["known"]
                folder = os.path.join(out, _check_name(name))
                done = None if again else captured(folder, options, [line["id"] for line in known])
                if done:
                    finished += 1
                    tell(k, name, f"captured already ({done})")
                    found[name] = _read_json(os.path.join(folder, "capture.json"))
                    continue
                running.append(start_child(out, k, name, options, known, data))
                tell(k, name, f"searching ({len(known)} known lines) {options}")
            if running:
                with contextlib.suppress(subprocess.TimeoutExpired):
                    running[0].process.wait(POLL_SECONDS)
            for child in list(running):
                ended = child.process.poll() is not None
                late = not ended and timeout is not None and time.time() - child.started > timeout
                if not ended and not late:
                    continue
                if late:
                    _kill(child)
                state = finish_child(out, child, timeout if late else None)
                running.remove(child)
                finished += 1
                tell(child.k, child.name, _outcome(state))
                found[child.name] = state
    except BaseException:
        for child in running:
            with contextlib.suppress(Exception):  # the others are ended all the same; the first exception goes on
                _drop(child)
        raise
    return {item["id"]: found[item["id"]] for item in items}


def chosen(clusters: List[Dict], ids: Sequence[str] = (), countries: Sequence[str] = (),
           source_ids: Sequence[str] = (), national_only: bool = False,
           max_clusters: Optional[int] = None) -> List[Dict]:
    """The clusters run searches: those of the ids, countries and sources given (each filter only when
    given), the most known lines first (then id), at most max_clusters."""
    wanted = set(ids)
    unknown = wanted - {c["id"] for c in clusters}
    if unknown:
        raise ValueError(f"no such cluster: {', '.join(sorted(unknown))}")
    countries = {c.upper() for c in countries}
    picked = [c for c in clusters if (not wanted or c["id"] in wanted) and (not countries or c["country"] in countries)
              and (not source_ids or (c.get("source") or "auto") in source_ids)
              and (not national_only or c.get("national"))]
    picked.sort(key=lambda c: (-len(c["lines"]), c["id"]))
    return picked[:max_clusters] if max_clusters is not None else picked


# ---------------------------------------------------------------------------------------------
# the child: one search with its capture

def write_grid(out: str, plan, data):
    """grid.json and grids.npz of a search's grid (search._lines' plan and step 1's data)."""
    import area as ar
    import helpers as sh
    import obstacle_study as ob
    import search

    p, g = plan.params, plan.grid
    sag_table = (search._sag_table(dataclasses.astuple(plan.rigging), p.min_length, p.max_length)
                 if p.model == "sag" else None)  # built once per process: _lines takes the same table
    try:
        meta = ob.layer_meta(plan)
    except Exception as e:  # a local file as the source: no layer files to record
        meta = {"layer_meta_error": str(e)}
    west, south, east, north = plan.area.shape_wgs84().bounds
    grid = {"crs": str(g.crs), "left": float(g.left), "top": float(g.top), "res": float(g.res),
            "shape": [int(g.height), int(g.width)], "params": search._run_params(plan), "nmpt": plan.nmpt,
            "obstacles": plan.obstacles, "model": p.model, "rigging": dataclasses.asdict(plan.rigging),
            "slope_threshold": float(p.slope_threshold), "fall": float(sh.fall_allowance(sag_table)),
            "layer_meta": meta, "source": plan.source.id, "area_wgs84": [south, west, north, east],
            "centre": list(plan.area.center), "radius": p.radius if isinstance(plan.area, ar.Circle) else None,
            "resolution": float(plan.resolution), "end_zone": plan.end_zone, "lift": plan.lift}
    with open(os.path.join(out, "grid.json"), "w", encoding="utf-8") as f:
        json.dump(grid, f, indent=1, ensure_ascii=False)
    mask = data.mask if data.mask is not None else plan.area.mask(g)
    arrays = {"elevation": np.asarray(data.elevation, dtype=np.float32), "mask": np.asarray(mask, dtype=np.uint8)}
    if data.surface is not None:
        arrays["surface"] = np.asarray(data.surface, dtype=np.float32)
    for name in ("filled", "joined", "water", "covered"):
        value = getattr(data, name)
        if value is not None:
            arrays[name] = np.asarray(value).astype(np.uint8)
    np.savez_compressed(os.path.join(out, "grids.npz"), **arrays)


def save_anchors(out: str, anchors):
    np.save(os.path.join(out, "anchors.npy"), np.ascontiguousarray(np.asarray(anchors, dtype=np.int64).reshape(-1, 2)))


def save_lines(out: str, results=None, groups=None):
    """lines.npz of the lines found (search._lines' table and groups; None: none found)."""
    import helpers as sh
    if results is None or not len(results):
        pairs = {k: np.zeros((0, 2), dtype=np.float64) for k in ("a1", "a2", "a1_xy", "a2_xy")}
        values = {k: np.zeros(0, dtype=np.float64) for k in ("length", "clearance", "clearance_nmpt") + LINE_EXTRAS}
        np.savez(os.path.join(out, "lines.npz"), **pairs, **values, over=np.zeros(0, dtype=bool),
                 rep=np.zeros(0, dtype=bool), group=np.zeros(0, dtype=np.int64))
        return
    c, n = results.columns, len(results)
    rep = np.zeros(n, dtype=bool)
    rep[np.asarray(groups.rep, dtype=np.int64)] = True
    group = np.full(n, -1, dtype=np.int64)
    group[np.asarray(groups.members, dtype=np.int64)] = np.repeat(np.arange(len(groups), dtype=np.int64),
                                                                  groups.sizes())
    arrays = {"a1": np.asarray(c["anchor1"], dtype=np.float64).reshape(-1, 2),
              "a2": np.asarray(c["anchor2"], dtype=np.float64).reshape(-1, 2),
              "a1_xy": np.asarray(c["a1_xy"], dtype=np.float64).reshape(-1, 2),
              "a2_xy": np.asarray(c["a2_xy"], dtype=np.float64).reshape(-1, 2),
              "over": np.asarray(c["over_obstacles"], dtype=bool), "rep": rep, "group": group}
    for key in ("length", "clearance", "clearance_nmpt") + LINE_EXTRAS + tuple(sh.END_VALUES):
        if key in c:
            arrays[key] = np.asarray(c[key], dtype=np.float64)
    np.savez(os.path.join(out, "lines.npz"), **arrays)


def search_child(out: str, search_args: List[str], work_id: Optional[str] = None) -> int:
    """findaline.py with search._lines and search._anchors wrapped (the capture: write_grid, the
    anchors, save_lines), its outcome in result.json. Production's obstacle rule, one grid only.
    work_id: each search's work folder made inside <data>/work/<work_id>/ (cache.new_work wrapped; the
    name production gives it, "<time>-<pid>"), the folder run removes once this process has ended."""
    import runpy

    import helpers as sh
    import search

    os.makedirs(out, exist_ok=True)
    os.environ.setdefault("FINDALINE_PROGRESS", "text")
    state = SimpleNamespace(grid=False, anchors=None, lines=None, error=None, message=None, steep=None, run=None)
    original_lines, original_anchors, original_slopes = search._lines, search._anchors, sh.find_significant_slopes
    original_save, original_new_work = search.save_run, cache.new_work

    def new_work(data: str) -> str:
        path = os.path.join(data, "work", work_id, f"{datetime.now():%Y%m%d-%H%M%S}-{os.getpid()}")
        os.makedirs(path, exist_ok=True)
        return path

    def save_run(plan, lines, run=None):
        result = original_save(plan, lines, run)
        state.run = os.path.abspath(result.run.get("path") or os.path.join(plan.paths.runs, result.meta["id"]))
        return result

    def slopes(*args, **kwargs):
        state.steep = original_slopes(*args, **kwargs)
        return state.steep

    def anchors(plan, data, quiet=False, deferred=False):
        found = original_anchors(plan, data, quiet, deferred)
        if found is not None:
            save_anchors(out, found.anchors)
            state.anchors = "step 2"
        return found

    def lines(plan, data, core=None, before=0):
        if core is not None:
            raise RuntimeError("truth_study captures one grid (a circle), not the tiles of an area")
        write_grid(out, plan, data)
        state.grid = True
        try:
            results, groups = original_lines(plan, data, core, before)
        except search.SearchError as e:
            state.error, state.message = e.code, str(e)
            if state.anchors is None:  # stopped in step 2: the steep pixels off the seams, as _anchors had them
                steep = np.zeros((0, 2), dtype=np.int64) if state.steep is None else state.steep
                for seams in (data.filled, data.joined):
                    if seams is not None and len(steep):
                        steep = steep[~search.at_seams(seams, steep)]
                save_anchors(out, steep)
                state.anchors = "steep"
            save_lines(out)
            state.lines = 0
            raise
        save_lines(out, results, groups)
        state.lines = len(results)
        return results, groups

    search._lines, search._anchors, sh.find_significant_slopes, search.save_run = lines, anchors, slopes, save_run
    if work_id:
        cache.new_work = new_work
    sys.argv = [os.path.join(HERE, "findaline.py"), *search_args, *FIXED_OPTIONS]
    code = 0
    try:
        runpy.run_path(sys.argv[0], run_name="__main__")
    except SystemExit as e:
        if e.code not in (None, 0):
            print(f"findaline.py ended with {e.code!r}", file=sys.stderr)
            code = 1
    except Exception as e:  # any other error: a failure, its traceback in the log
        traceback.print_exc()
        state.message = state.message or f"{type(e).__name__}: {cache.clean_error(e)}"
        code = 1
    finally:
        search._lines, search._anchors, sh.find_significant_slopes = original_lines, original_anchors, original_slopes
        search.save_run, cache.new_work = original_save, original_new_work
    complete = state.grid and all(os.path.exists(os.path.join(out, name))
                                  for name in ("grid.json", "grids.npz", "anchors.npy", "lines.npz"))
    with open(os.path.join(out, "result.json"), "w", encoding="utf-8") as f:
        json.dump({"code": code, "error": state.error, "message": state.message, "lines": state.lines,
                   "anchors": state.anchors, "complete": bool(complete), "run": state.run}, f, indent=1,
                  ensure_ascii=False)
    print(f"truth_study: exit {code}, {state.lines if state.lines is not None else 'no'} lines captured into {out}")
    return code


# ---------------------------------------------------------------------------------------------
# the command line

def _analysis():
    """tools/truth_analysis.py, or None with a message when it is missing."""
    try:
        import truth_analysis
    except ImportError as e:
        if e.name != "truth_analysis":
            raise
        print("tools/truth_analysis.py is missing: analyse and report need it", file=sys.stderr)
        return None
    return truth_analysis


def _cache_dir(data_dir: Optional[str]) -> str:
    return os.path.join(cache.data_dir(data_dir), "cache")


def _cluster_command(args) -> int:
    cache_dir = _cache_dir(args.data_dir)
    cache.check_layout(cache_dir)
    types = [t for value in args.types for t in value.split(",")]
    lines = covered(sd.load_lines(cache_dir), types)
    if args.country:
        countries = {c.upper() for value in args.country for c in value.split(",")}
        lines = [line for line in lines if line.country in countries]
    limit = reach_limit(args.margin, args.radius_max)
    left_out = sum(line.geodesic_m > limit for line in lines)
    extra = args.extra.strip()
    split_options(extra)  # a ValueError for an unclosed quote, before any lookup
    found = cluster(lines, args.link, args.margin, args.radius_min, args.radius_max, types)
    for c in found:
        c.extra = extra
    mode = ("defer" if args.auto else "offline" if args.offline_sources else "lines" if args.country_from_lines
            else "nominatim")
    print(f"{len(found)} clusters of {len(lines) - left_out} lines; choosing their sources ({mode})", flush=True)
    with_sources(found, cache_dir, mode, args.margin, args.radius_min, say=lambda t: print(t, flush=True))
    params = {"types": list(type_names(types)), "countries": sorted({c.upper() for v in args.country or []
                                                                      for c in v.split(",")}),
              "link_m": args.link, "margin_m": args.margin, "radius_min": args.radius_min,
              "radius_max": args.radius_max, "sources": mode, "extra": extra,
              "lines_file": cache.relative(cache_dir, sd.lines_path(cache_dir))}
    path = write_clusters(args.out, found, params, left_out)
    print(summary(found, left_out, args.radius_min))
    print(f"\n{path}")
    return 0


def _run_command(args) -> int:
    filters = bool(args.ids or args.country or args.source or args.max_clusters is not None or args.national_only)
    items = []
    if args.place:
        files = args.known or []
        if len(files) > 1 and len(files) != len(args.place):
            raise ValueError("--known: one file for every --place, or one for all")
        for k, spec in enumerate(args.place):
            name, sep, options = spec.partition("=")
            if not sep:
                raise ValueError(f"--place {spec!r}: NAME=OPTIONS")
            known = known_lines(files[k if len(files) > 1 else 0]) if files else []
            items.append({"id": _check_name(name.strip()), "options": options.strip(),
                          "known": [dataclasses.asdict(line) for line in known]})
    if not args.place or filters:
        countries = [c for value in args.country or [] for c in value.split(",")]
        items += [{"id": c["id"], "options": c["options"], "known": c["known"]}
                  for c in chosen(load_clusters(args.out), args.ids or [], countries, args.source or [],
                                  args.national_only, args.max_clusters)]
    cache_dir = None if args.no_cache_link else os.path.abspath(args.cache or _cache_dir(args.data_dir))
    if cache_dir:
        cache.check_layout(cache_dir)
    found = run(args.out, items, cache_dir, args.again, args.timeout, say=lambda text: print(text, flush=True),
                parallel=args.parallel)
    counts = collections.Counter(state["status"] for state in found.values())
    print(f"\n{len(found)} searches: " + ", ".join(f"{counts.get(s, 0)} {s}" for s in STATUSES))
    return 1 if counts.get("failed") else 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    data_help = "data folder whose cache/ holds SlackMap's files (default: FINDALINE_DATA or the repository)"
    p = sub.add_parser("fetch", help="SlackMap's lines and spots files into the cache (slackmap_data.fetch)")
    p.add_argument("--update", action="store_true", help="ask the server now (a 304 keeps the files)")
    p.add_argument("--data-dir", help=data_help)
    p = sub.add_parser("cluster", help="cluster the known lines into searches: <out>/clusters.json")
    p.add_argument("--out", required=True)
    p.add_argument("--data-dir", help=data_help + "; also Nominatim's cache")
    p.add_argument("--types", nargs="+", default=[",".join(DEFAULT_TYPES)],
                   help="line types, letters or names (default %(default)s: highlines and midlines)")
    p.add_argument("--country", nargs="+", help="only these countries (ISO codes)")
    p.add_argument("--link", type=float, default=LINK_M, help="metres: anchors this near join (default %(default)s)")
    p.add_argument("--margin", type=float, default=MARGIN_M,
                   help="metres beyond the farthest anchor (default %(default)s)")
    p.add_argument("--radius-min", type=float, default=RADIUS_MIN, help="default %(default)s")
    p.add_argument("--radius-max", type=float, default=RADIUS_MAX, help="a larger cluster is bisected "
                                                                         "(default %(default)s)")
    how = p.add_mutually_exclusive_group()
    how.add_argument("--auto", action="store_true", help="no --source in the options: each search chooses")
    how.add_argument("--offline-sources", action="store_true",
                     help="choose the sources from sources.choose.OFFLINE_BOXES alone (no Nominatim)")
    how.add_argument("--country-from-lines", action="store_true",
                     help="the lines' own country instead of Nominatim's (regions still looked up)")
    p.add_argument("--extra", default="", help='findaline.py options added to every search, e.g. --extra '
                                               '"--model sag" (one without a space: --extra=--yes)')
    p = sub.add_parser("places", help="the clusters ranked, with the nearest regression test: <out>/places.md")
    p.add_argument("--out", required=True)
    p.add_argument("--regression", help="the regression tests (default tests/regression.json)")
    p.add_argument("--top", type=int, default=20, help="clusters of the overall ranking (default %(default)s)")
    p.add_argument("--per-group", type=int, default=10, help="clusters per country and source (default %(default)s)")
    p.add_argument("--near", type=float, default=NEAR_M, help="metres: a test this near covers a cluster "
                                                              "(default %(default)s)")
    p = sub.add_parser("run", help="search the clusters (resumable): <out>/<cluster>/capture")
    p.add_argument("--out", required=True)
    p.add_argument("--ids", nargs="+", help="only these clusters")
    p.add_argument("--country", nargs="+", help="only the clusters of these countries")
    p.add_argument("--source", nargs="+", help="only the clusters of these sources")
    p.add_argument("--national-only", action="store_true",
                   help="only clusters whose source colours the coverage map (not FABDEM or a gap filler)")
    p.add_argument("--max-clusters", type=int, help="at most this many clusters (the most known lines first)")
    p.add_argument("--place", action="append", default=[], help="NAME=OPTIONS of findaline.py, an ad-hoc place")
    p.add_argument("--known", action="append", help="the known lines of --place: a JSON list of KnownLine dicts "
                                                    "or a GeoJSON FeatureCollection (one for all places, or one each)")
    p.add_argument("--again", action="store_true", help="search clusters captured already again")
    p.add_argument("--timeout", type=float, help="seconds a search may take (then: failed), each search's own")
    p.add_argument("--parallel", type=int, default=1, metavar="N",
                   help="searches at once, each in its child process (default %(default)s)")
    p.add_argument("--data-dir", help=data_help)
    link = p.add_mutually_exclusive_group()
    link.add_argument("--cache", help="the cache to link (default: the data folder's)")
    link.add_argument("--no-cache-link", action="store_true", help="a fresh cache in <out>/data (all clusters)")
    p = sub.add_parser("search-child", help="(child) one search with its capture")
    p.add_argument("--out", required=True)
    p.add_argument("--work-id", help="its searches' work folders inside <data>/work/<this> (run removes it)")
    p.add_argument("search_args", nargs=argparse.REMAINDER)
    p = sub.add_parser("analyse", help="match and diagnose the captures (tools/truth_analysis.py)")
    p.add_argument("out")
    p.add_argument("--profiles", action="store_true", help="also search.profile_of_line of every known pair")
    p.add_argument("--cluster", nargs="+", help="only these clusters")
    where = p.add_mutually_exclusive_group()
    where.add_argument("--cache", help="the cache --profiles links into <out>/data (default: the data folder's)")
    where.add_argument("--data-dir", help=data_help)
    p = sub.add_parser("report", help="study.json, study.md and pictures (tools/truth_analysis.py)")
    p.add_argument("out")
    p.add_argument("--no-pictures", dest="pictures", action="store_false")
    args = parser.parse_args(argv)
    try:
        if args.command == "fetch":
            cache_dir = _cache_dir(args.data_dir)
            cache.check_layout(cache_dir)
            sd.fetch(cache_dir, args.update, say=print)
            return 0
        if args.command == "cluster":
            return _cluster_command(args)
        if args.command == "places":
            print(write_places(args.out, args.regression, args.top, args.per_group, args.near))
            return 0
        if args.command == "run":
            return _run_command(args)
        if args.command == "search-child":
            search_args = args.search_args[1:] if args.search_args[:1] == ["--"] else args.search_args
            return search_child(args.out, search_args, args.work_id and _check_name(args.work_id))
        analysis = _analysis()
        if analysis is None:
            return 2
        if args.command == "analyse":
            cache_dir = os.path.abspath(args.cache or _cache_dir(args.data_dir))
            analysis.analyse(args.out, profiles=args.profiles, clusters=args.cluster, cache_dir=cache_dir)
            return 0
        print(analysis.report(args.out, pictures=args.pictures))
        return 0
    except (FileNotFoundError, ValueError, RuntimeError) as e:
        print(f"error: {cache.clean_error(e)}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    from progress import utf8_output
    utf8_output()  # redirected output in UTF-8, not the Windows code page
    sys.exit(main())
