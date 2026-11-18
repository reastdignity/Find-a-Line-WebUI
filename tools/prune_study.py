"""
Run by hand: what a pruning rule keeps of a saved table of lines, and an audit of what it drops
('The keeper guarantee: an audit for every rule', K-49; the line-volume study, 2026-11-13).
Offline: no network, nothing written beside a run, nothing of the search changed. It measures
rules; it adopts none.

The command line (fixed for the study):

    python tools/prune_study.py <table folder> --rule <name> [--param k=v ...] [--rules-file F]
        [--radius M] [--known DIR] [--pictures] --out <folder>
        [--cache DIR | --no-cache] [--threads N] [--picture-places N] [--terrain F.npz]

<table folder>: a run's folder as a search saves it (read only): its store (lines.arrow) and run.json,
or, for a run saved before the store (2026-11-15), its lines.csv and run.json (lines.js beside them when
there). The columns are parsed once and kept as .npz under --cache (default: prune_study_cache in the
system's temporary folder), never beside the run. Writes <out>/audit.json (every count), <out>/audit.md (a
table for a report and one row for a table of cases), <out>/violations.csv (the dropped lines
without a keeper) and, with --pictures, <out>/pictures/place-<k>.png (plan views of the largest
places before and after). The same table, rule and parameters give the same files on every run and
with every number of threads (seconds are printed, never written).

In Python (cwd or sys.path: the repository; `sys.path.insert(0, "tools")`):

    import prune_study as ps
    table = ps.load_table(folder)                    # a Table: table["clearance"], len(table), table.meta
    places = ps.places_of(table)                     # Places: .place per line, .rep per place, len()
    result = ps.audit(table, "higher_wins", {"cell": 8}, radius=8.0, known=None)   # an Audit
    result.summary, result.keep, result.markdown(), result.write(out, pictures=True)

A rule is a function from the table (and its parameters) to a boolean mask of the kept lines, one
value per line of the table, registered under a name:

    from prune_study import rule

    @rule("longer_than", title="Only lines longer than a limit", idea="X-00")
    def longer_than(table, limit=100.0):
        return table["length"] >= float(limit)

--rules-file F.py loads such a file (several: repeat the option), so rules are added without
editing this one; `title` and `idea` (the idea's id) name the rule in the outputs. A rule must not
change the table and must give the same mask on every run. Helpers for rules: ids_of (a number per
combination of values), cells (the lattice cells of both anchors), PerGroup (the largest or
smallest value per group), best_per_key (the best line per key by a fixed order), places_of.

The table's columns (numpy arrays in the order of lines.csv, float64 unless said; a column the file
lacks is absent: `"lift_no_zone" in table`): group, group_size (int64), representative (bool), the
place the search saved; length, clearance, clearance_nmpt (NaN: not measured), lift_needed,
lift_no_zone (only runs with a no-fall zone or A-frames), over_obstacles (bool), water_m, filled_m,
height_max, height_mean, high_pct; per anchor (1, 2): lat, lon, elev_a, y (northing), x (easting),
angle, prom, drop (lat1 ... drop2). The names are helpers.LineTable's, the anchors' coordinates
apart. Values are what lines.csv holds: rounded as a user reads them (a run's store is read through
linestore.export's CSV, the run's lines.csv byte for byte, written into a temporary folder outside the run).

The terrain under the anchors, for rules that judge an anchor by the ground around it:
table.terrain is None when the table has none, else a Terrain: z (the elevation as the search used
it: float32, rows from north to south, NaN without data), water (bool like z, or None), res (metres
per pixel), left and top (the x of the grid's west edge and the y of its north edge, in the
coordinates of x1 y1 x2 y2: the pixel (row, col) holds the points with top - (row + 1) * res < y <=
top - row * res and left + col * res <= x < left + (col + 1) * res), shape, and pixels(table, k):
the (row, col) of every anchor k (1 or 2) of the table as two int64 arrays (ValueError when an
anchor lies outside the grid; inside(table, k) tells which do, pixels(table, k, clip=True) gives
the nearest pixel for those outside). A rule that uses it:

    @rule("anchors_above", title="Both anchors above a height (example)")
    def anchors_above(table, height=1000.0):
        t = table.terrain
        if t is None:                                # a table without terrain: keep every line
            return np.ones(len(table), dtype=bool)
        (r1, c1), (r2, c2) = t.pixels(table, 1), t.pixels(table, 2)
        return (t.z[r1, c1] >= height) & (t.z[r2, c2] >= height)

A run's table has no terrain unless --terrain F.npz attaches one (in Python: table.terrain =
ps.load_terrain(F), or a Terrain made by hand): an .npz with the keys z (2-D), res, left, top and,
optionally, water (2-D like z); Terrain(z, res, left, top, water).save(F) writes it. Under --known
every capture's table has the capture's own grids (the terrain and the water the truth check saved
beside the found lines), read only when the rule asks for table.terrain; a capture without grids
has None. So one rule works on a run's table and on the captures alike. The audit's outputs say
nothing of a terrain unless one was used: audit.json's "table" gets "terrain" (shape, res) when
the run's table has one, its "known" gets "terrain" (the captures with and without grids) when the
rule read table.terrain there.

Places come from production's grouping, never from a copy of it: before the rule they are the
table's saved places (the `group` column, when the run was grouped at the app's default distance,
max(20 m, 2 pixels), by clearance); the kept lines are grouped again by mapping.group_lines. From a
run's store (Table.source "store") or lines.js beside the table (Table.source "lines.js": a run
saved before the store) its unrounded values and the search's order of the lines are used, as
the search itself would group: exact. Without them (a table of lines.csv and run.json alone) the
lines are grouped in the order the file's rows imply (Table.file_rank): every line together gives
the saved places again, but the kept lines of a rule may group differently than in the search
where lines of different places tie in the rounded clearance (four audits of two tables of the
study, 0.9 and 3.1 million lines: the same number of places as with lines.js three times, 3 501
against 3 499 once). The audit states which was read, and always gives the check "every line
grouped again: N places, saved: M".

The audit of one rule on one table (Audit.summary, audit.json):
- lines kept and dropped; places before, emptied (no line kept), places whose shown line (the
  representative) is dropped, places of the kept lines grouped again;
- keepers: for every dropped line the nearest kept line with both ends within --radius metres
  (default 8), either way round, the larger of the two end distances being the distance; in which
  of the values a user reads the keeper is not worse (VALUES: clearance, height above the terrain,
  length, share of the line high; "not worse": at least the dropped line's saved value); whether
  some kept line within the radius is not worse (per value, and in all at once). A dropped line
  without a kept line within the radius is a violation, listed in violations.csv;
- the never-prune list, each item counted by itself: each place's best line per sort key of the
  result page (SORT_KEYS, as viewer/src/list.ts: lost when no kept line of the place has the best
  value); the top level of each stack of levels (stacks as the line-volume study's report E4b:
  lines whose ends fall into the same STACK_CELL m cells, mean anchor heights spanning STACK_STEP m
  or more; lost when no kept line stands within STACK_STEP m of the highest); one line per place
  and 30 degree sector of direction; every line valid without the no-fall zone and without A-frames
  (lift_no_zone 0; a table without the column: every line);
- with --known <pass folder> (the truth check's private captures, docs/truth-check.md: read only):
  the rule runs on the found lines of every capture, and of the known lines that had a found line
  within their tolerance before the rule (the truth check's match: both ends within the tolerance,
  the length too) the audit counts those that still have one, those whose matched line is kept and
  those with a kept line within the radius of it. Counts per type only: no coordinate, name or id
  of a known line or of a capture is printed or written.

The rules shipped here repeat two that the study's phase 1 measured: higher_wins ('Higher wins on
a face', K-17, as report E4b's stacks.py) and best_per_cell_pair ('One best line per pair of
anchor cells', K-01, the lattice classes of report E4a's m2_classes.py).

tests/test_prune_study.py: made-up tables with known answers for every item.
"""

import argparse
import contextlib
import csv
import hashlib
import importlib.util
import inspect
import io
import json
import math
import os
import sys
import tempfile
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "tools"))
if __name__ == "__main__":  # a rules file's `import prune_study` must give this module, not a second copy
    sys.modules.setdefault("prune_study", sys.modules["__main__"])
    for stream in (sys.stdout, sys.stderr):  # UTF-8 when redirected (progress.utf8_output, inline)
        stream.reconfigure(encoding="utf-8", errors="replace")

import numba  # noqa: E402
import numpy as np  # noqa: E402
from numba import njit, prange  # noqa: E402

RADIUS = 8.0          # metres: a keeper's ends lie this near the dropped line's (report E4b's "near twin")
STACK_CELL = 8.0      # metres: the plan cells of a stack of levels (report E4b's stacks.py)
STACK_STEP = 10.0     # metres: a stack spans this much height; its top level is this thick
SECTOR = 30.0         # degrees: the sectors of direction of the never-prune list
APP_DISTANCE = 20.0   # metres: the app's default grouping distance (search.plan_search: or 2 pixels if more)
VIOLATIONS_MAX = 100_000  # rows of violations.csv at most (audit.json holds the whole count)
PICTURE_PLACES = 4    # --pictures: the largest places drawn
PICTURE_LINES = 20_000  # lines drawn per picture and kind at most (an even sample beyond)
CACHE_VERSION = 1     # of the cached columns: raised when load_table reads a file differently
GROUPING_VERSION = 2  # of grouping_check's cached result: raised when places_of groups a table differently
CACHE_FOLDER = "prune_study_cache"

# lines.csv's columns (runs.FIELDS, runs.END_FIELDS) and the table's names for them
CSV_COLUMNS = {"group": "group", "representative": "representative", "group_size": "group_size",
               "length_m": "length", "clearance_m": "clearance", "clearance_nmpt_m": "clearance_nmpt",
               "lift_needed_m": "lift_needed", "lift_no_zone_m": "lift_no_zone",
               "over_trees_buildings": "over_obstacles", "water_m": "water_m", "filled_m": "filled_m",
               "height_max_m": "height_max", "height_mean_m": "height_mean", "high_pct": "high_pct"}
for _k in ("1", "2"):
    CSV_COLUMNS.update({f"anchor{_k}_lat": "lat" + _k, f"anchor{_k}_lon": "lon" + _k,
                        f"anchor{_k}_elev_m": "elev_a" + _k, f"anchor{_k}_northing": "y" + _k,
                        f"anchor{_k}_easting": "x" + _k, f"anchor{_k}_wall_angle": "angle" + _k,
                        f"anchor{_k}_prominence_m": "prom" + _k, f"anchor{_k}_drop_m": "drop" + _k})
INT_COLUMNS = ("group", "group_size")
BOOL_COLUMNS = ("representative", "over_obstacles")
# A row of lines.js (mapping.map_rows): the positions of the values the grouping reads, unrounded
JS_COLUMNS = {4: "x1", 5: "y1", 6: "x2", 7: "y2", 8: "length", 9: "clearance", 16: "height_max"}
# A capture's lines.npz (tools/truth_study.py save_lines): its names that differ from the table's
CAPTURE_COLUMNS = {"over": "over_obstacles", "rep": "representative"}

# The values a user reads of a line, for "the keeper is not worse": (name in the outputs, column); larger is
# not worse in each
VALUES = (("clearance", "clearance"), ("height", "height_max"), ("length", "length"), ("share high", "high_pct"))


def _pair(table, name, pick):
    a, b = table.get(name + "1"), table.get(name + "2")
    return None if a is None or b is None else pick(a, b)  # np.maximum/minimum: NaN (not known) stays NaN


# The sort keys of the result page's list of lines (viewer/src/list.ts SORT_KEYS without "n", the group's size,
# which is no value of a line; tests/test_prune_study.py compares the keys): (key, label, value, largest first)
SORT_KEYS = (
    ("len", "length", lambda t: t.get("length"), True),
    ("clr", "clearance over terrain", lambda t: t.get("clearance"), True),
    ("clrN", "clearance over trees/buildings", lambda t: t.get("clearance_nmpt"), True),
    ("hmax", "height above the terrain", lambda t: t.get("height_max"), True),
    ("hmean", "mean height", lambda t: t.get("height_mean"), True),
    ("highPct", "share of the line high", lambda t: t.get("high_pct"), True),
    ("dh", "anchor height difference", lambda t: _pair(t, "elev_a", lambda a, b: np.abs(a - b)), False),
    ("elev", "lower anchor elevation", lambda t: _pair(t, "elev_a", np.minimum), True),
    ("angle", "angle to the wall", lambda t: _pair(t, "angle", np.maximum), False),
    ("prom", "prominence of an anchor", lambda t: _pair(t, "prom", np.maximum), True),
    ("promBoth", "prominence of both anchors", lambda t: _pair(t, "prom", np.minimum), True),
    ("drop", "drop below both anchors", lambda t: _pair(t, "drop", np.minimum), True),
)


# ---------------------------------------------------------------------------------------------
# rules

@dataclass
class Rule:
    name: str
    title: str
    idea: Optional[str]
    function: Callable

    @property
    def label(self) -> str:
        """The rule as a report names it: its title with the idea's id."""
        return f"'{self.title}'" + (f" ({self.idea})" if self.idea else "")

    def parameters(self, given: Optional[Dict] = None) -> Dict:
        """The rule's parameters with their defaults, `given` over them (ValueError for one it has not)."""
        own = {k: p.default for k, p in list(inspect.signature(self.function).parameters.items())[1:]
               if p.kind in (p.POSITIONAL_OR_KEYWORD, p.KEYWORD_ONLY)}
        unknown = sorted(set(given or {}) - set(own))
        if unknown and not any(p.kind == p.VAR_KEYWORD for p in inspect.signature(self.function).parameters.values()):
            raise ValueError(f"rule {self.name} has no parameter {', '.join(unknown)} (it has: "
                             f"{', '.join(own) or 'none'})")
        missing = sorted(k for k, v in own.items() if v is inspect.Parameter.empty and k not in (given or {}))
        if missing:
            raise ValueError(f"rule {self.name} needs --param {missing[0]}=...")
        return {**own, **(given or {})}


RULES: Dict[str, Rule] = {}


def rule(name: str, title: Optional[str] = None, idea: Optional[str] = None):
    """Register a pruning rule under `name`: a function (table, **parameters) -> boolean mask of the kept
    lines. title: the rule in plain words (the idea's title), idea: the idea's id; both name it in the outputs."""
    def register(function):
        known = RULES.get(name)
        if known is not None and (known.function.__module__, known.function.__qualname__) != (
                function.__module__, function.__qualname__):
            raise ValueError(f"a rule named {name} exists already ({known.function.__module__})")
        RULES[name] = Rule(name, title or name, idea, function)
        return function
    return register


def load_rules_file(path: str):
    """Run a Python file whose functions decorated with `rule` register themselves (--rules-file)."""
    path = os.path.abspath(path)
    name = "prune_rules_" + hashlib.sha1(path.encode("utf-8")).hexdigest()[:12]
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        del sys.modules[name]
        raise
    return module


def apply_rule(a_rule: Rule, table: "Table", params: Dict) -> np.ndarray:
    """The rule's mask of kept lines, checked: one boolean per line of the table."""
    keep = np.asarray(a_rule.function(table, **params))
    if keep.dtype != np.bool_ or keep.shape != (len(table),):
        raise ValueError(f"rule {a_rule.name} must return one boolean per line: got {keep.dtype} {keep.shape} "
                         f"for {len(table)} lines")
    return keep


# ---------------------------------------------------------------------------------------------
# the terrain under a table's anchors

class Terrain:
    """The grid a table's anchors sit on (the module docstring): z (float32, rows from north to south,
    NaN without data), water (bool like z, or None), res (metres per pixel), left and top (the x of
    the west edge and the y of the north edge, in the table's coordinates). The arrays are read-only.
    """

    def __init__(self, z: np.ndarray, res: float, left: float, top: float, water: Optional[np.ndarray] = None):
        self.z = np.ascontiguousarray(z, dtype=np.float32)
        if self.z.ndim != 2:
            raise ValueError(f"a terrain's z has two dimensions, not {self.z.ndim}")
        self.water = None if water is None else np.ascontiguousarray(water).astype(bool, copy=False)
        if self.water is not None and self.water.shape != self.z.shape:
            raise ValueError(f"a terrain's water has the shape of z {self.z.shape}, not {self.water.shape}")
        self.res, self.left, self.top = float(res), float(left), float(top)
        if not self.res > 0:
            raise ValueError("a terrain's res is more than 0")
        for array in (self.z, self.water):
            if array is not None:
                array.setflags(write=False)

    @property
    def shape(self):
        return self.z.shape

    def _pixels(self, table: "Table", anchor: int):
        if anchor not in (1, 2):
            raise ValueError("anchor 1 or 2")
        row = np.floor((self.top - table[f"y{anchor}"]) / self.res).astype(np.int64)
        col = np.floor((table[f"x{anchor}"] - self.left) / self.res).astype(np.int64)
        return row, col, (row >= 0) & (row < self.z.shape[0]) & (col >= 0) & (col < self.z.shape[1])

    def inside(self, table: "Table", anchor: int) -> np.ndarray:
        """Which lines of the table have their anchor 1 or 2 on the grid."""
        return self._pixels(table, anchor)[2]

    def pixels(self, table: "Table", anchor: int, clip: bool = False):
        """The pixel (row, col) of every anchor 1 or 2 of the table: two int64 arrays for z[row, col].
        An anchor outside the grid is a ValueError; with clip=True it gets the nearest pixel of the
        grid's edge instead (inside tells which)."""
        row, col, inside = self._pixels(table, anchor)
        if not clip and not inside.all():
            raise ValueError(f"{int((~inside).sum())} of {len(row)} anchors lie outside the terrain's grid")
        return np.clip(row, 0, self.z.shape[0] - 1), np.clip(col, 0, self.z.shape[1] - 1)

    def save(self, path: str):
        """The terrain as the .npz that --terrain and load_terrain read."""
        arrays = {"z": self.z, "res": self.res, "left": self.left, "top": self.top}
        if self.water is not None:
            arrays["water"] = self.water
        np.savez_compressed(path, **arrays)


def load_terrain(path: str) -> Terrain:
    """A Terrain from an .npz with the keys z, res, left, top and, optionally, water (--terrain)."""
    with np.load(path) as f:
        missing = [k for k in ("z", "res", "left", "top") if k not in f.files]
        if missing:
            raise ValueError(f"{path}: no key {', '.join(missing)} (a terrain has z, res, left, top; water)")
        return Terrain(f["z"], float(f["res"]), float(f["left"]), float(f["top"]),
                       f["water"] if "water" in f.files else None)


def capture_terrain(cluster_folder: str) -> Optional[Terrain]:
    """The terrain of one of the truth check's captures: the elevation and the water of its grids.npz on
    the grid of its grid.json; None when the capture has no such grids."""
    capture = os.path.join(cluster_folder, "capture")
    try:
        with open(os.path.join(capture, "grid.json"), encoding="utf-8") as f:
            grid = json.load(f)
        with np.load(os.path.join(capture, "grids.npz")) as f:  # only these two of its grids are read
            return Terrain(f["elevation"], grid["res"], grid["left"], grid["top"],
                           (f["water"] > 0) if "water" in f.files else None)
    except (OSError, ValueError, KeyError, TypeError):
        return None


# ---------------------------------------------------------------------------------------------
# the table

class Table:
    """A table of lines as numpy columns (the module docstring names them), one row per line.

    table[name] gives a column (KeyError when the table has none: `name in table`, table.get(name)).
    meta: the run's run.json ({} without one); name: the run's name; source: what the grouping
    reads ("store", "lines.js", "lines.csv" or "capture"). A rule reads the table and never writes into it.
    terrain: the grid under the anchors (a Terrain; None: the table has none), read when first asked
    for (terrain_read tells that a rule asked).
    """

    def __init__(self, columns: Dict[str, np.ndarray], meta: Optional[Dict] = None, name: str = "",
                 path: Optional[str] = None, source: str = "table", order: Optional[np.ndarray] = None,
                 exact: Optional[Dict[str, np.ndarray]] = None):
        self.columns = columns
        self.meta = meta or {}
        self.name = name
        self.path = path
        self.source = source
        self.order = order        # the rows in the search's order (the store, lines.js), None: the table's own order
        self.exact = exact or {}  # unrounded values of the grouping, by the table's rows
        self._saved = None
        self._grouped = {}
        self._rank = {}
        self._terrain = None
        self._terrain_loader = None  # a function that reads the terrain when a rule first asks for it
        self.terrain_read = False
        self._check = None
        self._tag = None
        self._cache = None
        for column in columns.values():
            column.setflags(write=False)

    def __len__(self) -> int:
        return len(self.columns["x1"])

    def __getitem__(self, name: str) -> np.ndarray:
        return self.columns[name]

    def __contains__(self, name: str) -> bool:
        return name in self.columns

    def get(self, name: str, default=None):
        return self.columns.get(name, default)

    @property
    def terrain(self) -> Optional[Terrain]:
        self.terrain_read = True
        if self._terrain_loader is not None:
            self._terrain, self._terrain_loader = self._terrain_loader(), None
        return self._terrain

    @terrain.setter
    def terrain(self, value: Optional[Terrain]):
        if value is not None and not isinstance(value, Terrain):
            raise ValueError("a table's terrain is a Terrain or None")
        self._terrain, self._terrain_loader = value, None

    @property
    def params(self) -> Dict:
        return self.meta.get("params") or {}

    @property
    def distance(self) -> float:
        """The app's default grouping distance for this table's grid (search.plan_search)."""
        resolution = self.params.get("resolution") or self.meta.get("res")
        if not resolution:  # an automatic resolution is not recorded: the run's own distance, when it has one
            return float(self.params.get("group_distance") or APP_DISTANCE)
        return max(APP_DISTANCE, 2.0 * float(resolution))

    def file_rank(self, by: str) -> Optional[np.ndarray]:
        """For a table of lines.csv alone: each row's position in the search's order of the lines (best
        first by `by`), as far as the file tells it; None for any other table, or when the run was
        grouped by another rule.

        lines.csv is written place by place, the best place first, each place's lines best first
        (runs.row_order). So three things are known of the search's order: a line of a larger rounded
        value (the clearance of "clearance") comes first; the lines of one place stand in their order;
        the places' representatives stand in theirs. The rows sorted by the rounded value alone, equal
        ones as the file has them, keep all three (sorting by the rounded length too would not). Every
        line grouped in that order gives the saved places again; a part of the lines may still group
        differently than in the search where lines of different places tie in the rounded value.
        """
        first = {"clearance": "clearance", "longest": "length", "height": "height_max"}.get(by)
        if (self.source != "lines.csv" or self.order is not None or "group" not in self or first not in self
                or self.params.get("group_by", "clearance") != by):
            return None
        if by not in self._rank:
            order = np.argsort(-self[first], kind="stable")
            rank = np.empty(len(order), dtype=np.int64)
            rank[order] = np.arange(len(order), dtype=np.int64)
            self._rank[by] = rank
        return self._rank[by]

    def saved_places(self, distance: float, by: str) -> bool:
        """Whether the table's `group` column holds production's places at this distance and rule."""
        p = self.params
        return ("group" in self and "representative" in self and p.get("group_distance") is not None
                and float(p["group_distance"]) == float(distance) and p.get("group_by", "clearance") == by)


def _cache_dir(cache) -> Optional[str]:
    if cache is False:
        return None
    return os.path.abspath(cache) if cache else os.path.join(tempfile.gettempdir(), CACHE_FOLDER)


def _read_csv(path: str) -> Dict[str, np.ndarray]:
    import pandas as pd
    with open(path, encoding="utf-8-sig") as f:
        header = f.readline().strip().split(",")
    use = [h for h in header if h in CSV_COLUMNS]
    for needed in ("anchor1_easting", "anchor1_northing", "anchor2_easting", "anchor2_northing", "length_m",
                   "clearance_m"):
        if needed not in use:
            raise ValueError(f"{path}: no column {needed}")
    kind = lambda h: np.int64 if CSV_COLUMNS[h] in INT_COLUMNS else bool if CSV_COLUMNS[h] in BOOL_COLUMNS \
        else np.float64  # noqa: E731
    frame = pd.read_csv(path, encoding="utf-8-sig", usecols=use, dtype={h: kind(h) for h in use}, engine="c")
    return {CSV_COLUMNS[h]: np.ascontiguousarray(frame[h].to_numpy()) for h in use}


def _match_order(search: Dict[str, np.ndarray], columns: Dict[str, np.ndarray]):
    """The search's order of the lines and the grouping's unrounded values (`search`: JS_COLUMNS' names, each in
    the search's order, from lines.js or the store) matched to the table's rows by the anchors' coordinates
    rounded as lines.csv rounds them: (order, exact) with order[k] the table's row of the search's k-th line and
    exact[name] by the table's rows; (None, {}) when they are not exactly the table's lines."""
    import runs
    n = len(columns["x1"])
    if len(search["x1"]) != n:
        return None, {}
    names = ("x1", "y1", "x2", "y2")
    theirs = [runs.round_floats(search[name], 2) for name in names]  # as lines.csv rounds them
    mine = [columns[name] for name in names]
    a, b = np.lexsort(theirs[::-1]), np.lexsort(mine[::-1])
    if any(not np.array_equal(t[a], m[b]) for t, m in zip(theirs, mine)):
        return None, {}
    order = np.empty(n, dtype=np.int64)
    order[a] = b  # the search's line a[i] is the table's row b[i]
    exact = {}
    for name in JS_COLUMNS.values():
        values = np.empty(n, dtype=np.float64)
        values[b] = np.asarray(search[name], dtype=np.float64)[a]
        exact[name] = values
    return order, exact


def _read_lines_js(path: str, columns: Dict[str, np.ndarray]):
    """The unrounded values of the grouping and the search's order of the lines from a run's lines.js:
    (order, exact) of _match_order; (None, {}) when the file does not hold exactly the table's lines."""
    import pandas as pd

    with open(path, "rb") as f:
        text = f.read()
    start, end = text.find(b'"lines":['), text.rfind(b"]}")
    if start < 0 or end < start:
        return None, {}
    text = text[start + len(b'"lines":[') + 1:end - 1]  # without the first "[" and the last "]"
    body = text.replace(b"],[", b"\n")
    del text
    n = len(columns["x1"])
    if not body:
        return None, {}
    try:
        frame = pd.read_csv(io.BytesIO(body), header=None, usecols=list(JS_COLUMNS), dtype=np.float64,
                            na_values=["null"], engine="c")
    except (ValueError, IndexError):
        return None, {}
    del body
    if len(frame) != n:
        return None, {}
    return _match_order({name: frame[position].to_numpy() for position, name in JS_COLUMNS.items()}, columns)


# A run's store (linestore.read): the LineTable's columns of the grouping's values (JS_COLUMNS' names), unrounded
STORE_COLUMNS = {"x1": ("a1_xy", 0), "y1": ("a1_xy", 1), "x2": ("a2_xy", 0), "y2": ("a2_xy", 1),
                 "length": ("length", None), "clearance": ("clearance", None), "height_max": ("height_max", None)}


def _read_store(folder: str) -> Tuple[Dict[str, np.ndarray], Optional[np.ndarray], Dict[str, np.ndarray]]:
    """The table's columns of a run's store (linestore.export's CSV, written into a temporary folder outside the
    run, parsed as lines.csv is) and the search's order and the grouping's unrounded values (linestore.read: the
    values lines.js held, in its order): (arrays, order, exact)."""
    import linestore
    with tempfile.TemporaryDirectory(prefix="prune-study-") as tmp:
        path = os.path.join(tmp, "lines.csv")
        linestore.export(folder, "csv", path)
        arrays = _read_csv(path)
    lines, _ = linestore.read(folder, profiles=False)
    search = {name: (lines.columns[column] if index is None else lines.columns[column][:, index])
              for name, (column, index) in STORE_COLUMNS.items()}
    del lines
    order, exact = _match_order(search, arrays)
    if order is None:  # never: the export is made of the same lines
        raise ValueError(f"{folder}: the store's lines do not match its CSV export")
    return arrays, order, exact


def load_table(folder: str, cache=None) -> Table:
    """The table of lines of a run's folder: its store (lines.arrow) and run.json (Table.source "store"), or
    for a run saved before the store, its lines.csv, run.json and lines.js when it is there (source
    "lines.js", else "lines.csv").

    cache: the folder of the parsed columns (None: prune_study_cache in the system's temporary
    folder; False: no cache). A cached table is taken when lines.arrow (or lines.csv and lines.js)
    have the size and time they had; nothing is ever written into the run's folder.
    """
    folder = os.path.abspath(folder)
    if os.path.isfile(folder):
        folder = os.path.dirname(folder)
    path, js = os.path.join(folder, "lines.csv"), os.path.join(folder, "lines.js")
    store = os.path.join(folder, "lines.arrow")
    from_store = os.path.isfile(store)
    if from_store:
        path, js = store, None
    elif not os.path.exists(path):
        raise FileNotFoundError(f"{folder}: no lines.arrow and no lines.csv")
    meta = {}
    if os.path.exists(os.path.join(folder, "run.json")):
        with open(os.path.join(folder, "run.json"), encoding="utf-8") as f:
            meta = json.load(f)
    stamp = [f"v{CACHE_VERSION}", path]
    for file in (path, js):
        if file and os.path.exists(file):
            s = os.stat(file)
            stamp.append(f"{s.st_size}|{s.st_mtime_ns}")
    tag = hashlib.sha1("|".join(stamp).encode("utf-8")).hexdigest()[:16]
    cache_dir = _cache_dir(cache)
    cached = os.path.join(cache_dir, f"{os.path.basename(folder)[:40]}_{tag}.npz") if cache_dir else None
    if cached and os.path.exists(cached):
        with np.load(cached) as z:
            arrays = {k: z[k] for k in z.files}
    else:
        if from_store:
            arrays, order, exact = _read_store(folder)
        else:
            arrays = _read_csv(path)
            order, exact = _read_lines_js(js, arrays) if os.path.exists(js) else (None, {})
        if order is not None:
            arrays["order__"] = order
            arrays.update({"exact__" + k: v for k, v in exact.items()})
        if cached:
            os.makedirs(cache_dir, exist_ok=True)
            partial = cached + f".{os.getpid()}.tmp.npz"
            np.savez(partial, **arrays)
            os.replace(partial, cached)
    order = arrays.pop("order__", None)
    exact = {k[len("exact__"):]: arrays.pop(k) for k in [k for k in arrays if k.startswith("exact__")]}
    source = "store" if from_store else "lines.js" if order is not None else "lines.csv"
    table = Table(arrays, meta, name=str(meta.get("name") or os.path.basename(folder)), path=folder,
                  source=source, order=order, exact=exact)
    table._tag, table._cache = tag, cache_dir
    return table


def capture_table(cluster_folder: str) -> Table:
    """The found lines of one of the truth check's captures (<cluster>/capture/lines.npz with grid.json)
    as a table: the search's own unrounded values in its order. Its name and path are left empty: a
    cluster's folder is named by its coordinates. Its terrain (capture_terrain) is read when a rule
    first asks for it."""
    capture = os.path.join(cluster_folder, "capture")
    with open(os.path.join(capture, "grid.json"), encoding="utf-8") as f:
        grid = json.load(f)
    with np.load(os.path.join(capture, "lines.npz")) as z:
        data = {k: z[k] for k in z.files}
    columns = {}
    for k in ("1", "2"):
        latlon = np.asarray(data.pop("a" + k), dtype=np.float64).reshape(-1, 2)
        xy = np.asarray(data.pop(f"a{k}_xy"), dtype=np.float64).reshape(-1, 2)
        columns.update({"lat" + k: latlon[:, 0].copy(), "lon" + k: latlon[:, 1].copy(),
                        "x" + k: xy[:, 0].copy(), "y" + k: xy[:, 1].copy()})
    for name, values in data.items():
        columns[CAPTURE_COLUMNS.get(name, name)] = np.ascontiguousarray(values)
    meta = {"params": grid.get("params") or {}, "crs": grid.get("crs"), "res": grid.get("res")}
    table = Table(columns, meta, name="capture", source="capture")
    table._terrain_loader = lambda: capture_terrain(cluster_folder)
    return table


# ---------------------------------------------------------------------------------------------
# places: production's grouping

@dataclass
class Places:
    """The places ("spots") of a table's lines: place[i] the place of line i (0 the best place; -1 for
    a line left out), rep[p] the row of place p's representative (the line the app shows for it);
    source "saved" (the table's group column) or "grouped" (mapping.group_lines run here)."""
    place: np.ndarray
    rep: np.ndarray
    source: str
    distance: float

    def __len__(self) -> int:
        return len(self.rep)

    def sizes(self) -> np.ndarray:
        return np.bincount(self.place[self.place >= 0], minlength=len(self.rep))


def places_of(table: Table, keep: Optional[np.ndarray] = None, distance: Optional[float] = None,
              by: str = "clearance", saved: bool = True) -> Places:
    """The places of the table's lines (keep: only of those lines; the others get -1), by production's
    grouping at `distance` (None: the app's default, Table.distance) and rule `by`.

    Without `keep` and with saved=True the table's own places are returned when the run saved them at
    that distance and rule (production's result as it stands in lines.csv). Otherwise the lines are
    grouped here by mapping.group_lines: in the search's order with lines.js's unrounded values when the
    table has them (Table.source "store" or "lines.js", or a capture), else in the order that lines.csv's rows
    imply (Table.file_rank: exact for every line together, an estimate for a part of them).
    """
    distance = table.distance if distance is None else float(distance)
    n = len(table)
    if keep is None and saved and table.saved_places(distance, by):
        if table._saved is None:
            numbers, place = np.unique(table["group"], return_inverse=True)
            rows = np.flatnonzero(table["representative"])
            if len(rows) == len(numbers) and len(np.unique(place[rows])) == len(numbers):
                rep = np.empty(len(numbers), dtype=np.int64)
                rep[place[rows]] = rows
                table._saved = (place.astype(np.int64), rep)
        if table._saved is not None:
            return Places(table._saved[0], table._saved[1], "saved", distance)
    import helpers
    import mapping
    whole, key = keep is None, (distance, by)
    if whole and key in table._grouped:
        return table._grouped[key]
    keep = np.ones(n, dtype=bool) if whole else np.asarray(keep, dtype=bool)
    rows = np.flatnonzero(keep) if table.order is None else table.order[keep[table.order]]
    place = np.full(n, -1, dtype=np.int64)
    if not len(rows):
        return Places(place, np.zeros(0, dtype=np.int64), "grouped", distance)
    value = lambda name: table.exact.get(name, table.get(name))[rows]  # noqa: E731
    columns = {"a1_xy": np.column_stack([value("x1"), value("y1")]),
               "a2_xy": np.column_stack([value("x2"), value("y2")]),
               "over_obstacles": (table["over_obstacles"][rows] if "over_obstacles" in table
                                  else np.zeros(len(rows), dtype=bool)),
               "clearance": value("clearance"), "length": value("length")}
    if "height_max" in table:
        columns["height_max"] = value("height_max")
    rank = table.file_rank(by)
    if rank is not None:  # lines.csv alone: its rows' order of the search, as the one value production sorts by
        columns.update(clearance=-rank[rows].astype(np.float64), length=np.zeros(len(rows)))
        by = "clearance"
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):  # its bar
        groups = mapping.group_lines(helpers.LineTable(columns), distance, by)
    place[rows[groups.members]] = np.repeat(np.arange(len(groups), dtype=np.int64), groups.sizes())
    places = Places(place, rows[groups.rep], "grouped", distance)
    if whole:
        table._grouped[key] = places
    return places


def same_places(a: np.ndarray, b: np.ndarray) -> int:
    """How many lines stand in a place of exactly the same lines under both numberings a and b."""
    if not len(a):
        return 0
    pair = ids_of(a, b)
    size = lambda ids: np.bincount(ids)[ids]  # noqa: E731
    return int(((size(pair) == size(ids_of(a))) & (size(pair) == size(ids_of(b)))).sum())


def grouping_check(table: Table) -> Optional[Dict]:
    """What the grouping run here gives for every line of a table with saved places: the number of
    places against the saved number, and the lines whose place holds the same lines in both. The size
    of what "grouped again" may differ from the search by (None: the table has no saved places at the
    app's distance). Kept beside the cached columns."""
    if table._check is not None:
        return table._check
    saved = places_of(table)
    if saved.source != "saved":
        return None
    file = (os.path.join(table._cache, f"check_{table._tag}_{saved.distance:g}_{GROUPING_VERSION}.json")
            if table._cache else None)
    if file and os.path.exists(file):
        with open(file, encoding="utf-8") as f:
            table._check = json.load(f)
        return table._check
    again = places_of(table, saved=False)
    table._check = {"saved": len(saved), "grouped_again": len(again), "lines": len(table),
                    "lines_in_the_same_place": same_places(saved.place, again.place)}
    if file:
        os.makedirs(table._cache, exist_ok=True)
        with open(file, "w", encoding="utf-8") as f:
            json.dump(table._check, f)
    return table._check


# ---------------------------------------------------------------------------------------------
# helpers of rules and of the audit

def ids_of(*columns: np.ndarray) -> np.ndarray:
    """A number per line, 0..k-1, the same for lines equal in every column (numbered in the sorted
    order of the columns' values, the first column the most significant)."""
    n = len(columns[0])
    if not n:
        return np.zeros(0, dtype=np.int64)
    order = np.lexsort(columns[::-1])
    new = np.zeros(n, dtype=bool)
    for column in columns:
        s = np.asarray(column)[order]
        new[1:] |= s[1:] != s[:-1]
    ids = np.empty(n, dtype=np.int64)
    ids[order] = np.cumsum(new)
    return ids


class PerGroup:
    """Values per group of lines (ids: 0..k-1 per line, as ids_of or Places.place gives them)."""

    def __init__(self, ids: np.ndarray, count: Optional[int] = None):
        self.ids = np.asarray(ids, dtype=np.int64)
        self.count = int(count if count is not None else (self.ids.max() + 1 if len(self.ids) else 0))
        self.order = np.argsort(self.ids, kind="stable")
        s = self.ids[self.order]
        self.starts = np.flatnonzero(np.concatenate([[True], s[1:] != s[:-1]])) if len(s) else np.zeros(0, np.int64)
        self.present = s[self.starts]

    def reduce(self, values: np.ndarray, ufunc=np.maximum, empty=np.nan) -> np.ndarray:
        """ufunc over each group's values (np.maximum, np.minimum; np.fmax, np.fmin skip NaN): one
        value per group, `empty` for a group without lines."""
        out = np.full(self.count, empty, dtype=np.float64)
        if len(self.starts):
            out[self.present] = ufunc.reduceat(np.asarray(values, dtype=np.float64)[self.order], self.starts)
        return out


def cells(table: Table, size: float, x0: float = 0.0, y0: float = 0.0):
    """The lattice cells (side `size` metres, a corner at (x0, y0)) of both anchors: cx1, cy1, cx2, cy2."""
    cell = lambda v, o: np.floor((v - o) / size).astype(np.int64)  # noqa: E731
    return cell(table["x1"], x0), cell(table["y1"], y0), cell(table["x2"], x0), cell(table["y2"], y0)


def best_per_key(key: np.ndarray, *ranks: np.ndarray) -> np.ndarray:
    """A mask with one line per value of `key`: its first in the order of `ranks` (ascending, the first
    rank the most significant: pass -clearance for "the most clearance first"; NaN last), lines equal
    in every rank by their row."""
    n = len(key)
    keep = np.zeros(n, dtype=bool)
    if n:
        order = np.lexsort(tuple(ranks[::-1]) + (key,)) if ranks else np.argsort(key, kind="stable")
        s = np.asarray(key)[order]
        keep[order[np.concatenate([[True], s[1:] != s[:-1]])]] = True
    return keep


def stack_buckets(table: Table, cell: float = STACK_CELL, x0: float = 0.0, y0: float = 0.0) -> np.ndarray:
    """The plan bucket of each line as report E4b's stacks.py made them: the lines whose two ends fall
    into the same cells, the ends ordered by easting, then by northing downwards (its "by column, then
    row"), so a line and its reverse share a bucket."""
    x1, y1, x2, y2 = (table[k] for k in ("x1", "y1", "x2", "y2"))
    swap = (x1 > x2) | ((x1 == x2) & (y1 < y2))
    cx1, cy1, cx2, cy2 = cells(table, cell, x0, y0)
    return ids_of(np.where(swap, cx2, cx1), np.where(swap, cy2, cy1), np.where(swap, cx1, cx2),
                  np.where(swap, cy1, cy2))


def mean_anchor_height(table: Table) -> np.ndarray:
    return (table["elev_a1"] + table["elev_a2"]) / 2


# ---------------------------------------------------------------------------------------------
# the two rules of phase 1

@rule("higher_wins", title="Higher wins on a face", idea="K-17")
def higher_wins(table, cell=STACK_CELL, step=STACK_STEP, x0=0.0, y0=0.0):
    """Report E4b's "the higher wins" (its scripts/stacks.py): in every plan bucket (stack_buckets, cells
    of `cell` metres with a corner at (x0, y0)) whose lines' mean anchor heights span `step` metres or
    more, only the lines within `step` of the highest are kept. Neighbouring buckets are not compared.
    E4b's lattice started at its grid's corner: pass that corner (left, top) as x0, y0 to repeat its
    numbers."""
    bucket = PerGroup(stack_buckets(table, float(cell), float(x0), float(y0)))
    height = mean_anchor_height(table)
    top, low = bucket.reduce(height, np.maximum), bucket.reduce(height, np.minimum)
    stacked = (top - low) >= float(step)
    return ~(stacked[bucket.ids] & (height <= top[bucket.ids] - float(step)))


@rule("best_per_cell_pair", title="One best line per pair of anchor cells", idea="K-01")
def best_per_cell_pair(table, cell=5.0, x0=0.0, y0=0.0):
    """One line per unordered pair of anchor cells (a lattice of `cell` metres with a corner at
    (x0, y0)): the best by clearance, then length, then height above the terrain, then the anchors'
    coordinates. The kept lines are report E4a's lattice classes (its m2_classes.py, variant "plain",
    offset 0 at x0 = y0 = 0)."""
    cx1, cy1, cx2, cy2 = cells(table, float(cell), float(x0), float(y0))
    first = (cx1 < cx2) | ((cx1 == cx2) & (cy1 <= cy2))
    key = ids_of(np.where(first, cx1, cx2), np.where(first, cy1, cy2), np.where(first, cx2, cx1),
                 np.where(first, cy2, cy1))
    ranks = [-table["clearance"], -table["length"]]
    if "height_max" in table:
        ranks.append(-table["height_max"])
    return best_per_key(key, *ranks, table["x1"], table["y1"], table["x2"], table["y2"])


# ---------------------------------------------------------------------------------------------
# keepers

@njit(parallel=True, cache=True)
def _keepers(x1, y1, x2, y2, values, dropped, kept, order, keys, low, high, width, radius):
    """For each dropped line: the nearest kept line with both ends within `radius` (either way round;
    the distance: the larger of its two end distances, ties to the lower row), and of the kept lines
    within the radius: `some`, a bit per column of `values` set when one of them has at least the
    dropped line's value there, and `whole`, True when one of them has it in every column.

    kept: the rows of the kept lines; order, keys, low, high, width: mapping._cell_index of their first
    anchors at cell size `radius` (the candidates: the 3 x 3 cells around each end of the dropped
    line). Every dropped line writes at its own index: the results do not depend on the threads.
    """
    n, m = len(dropped), values.shape[1]
    nearest = np.full(n, -1, dtype=np.int64)
    distance = np.full(n, np.inf)
    some = np.zeros(n, dtype=np.int64)
    whole = np.zeros(n, dtype=np.bool_)
    r2 = radius * radius
    for t in prange(n):
        i = dropped[t]
        best, arg, bits, full = np.inf, -1, 0, False
        for which in range(2):  # a kept line's first anchor near this line's anchor 1, then near its anchor 2
            px = x1[i] if which == 0 else x2[i]
            py = y1[i] if which == 0 else y2[i]
            qx = x2[i] if which == 0 else x1[i]
            qy = y2[i] if which == 0 else y1[i]
            cx = np.int64(math.floor(px / radius))
            cy = np.int64(math.floor(py / radius))
            v0, v1 = max(cy - 1, low[1]), min(cy + 1, high[1])
            if v0 > v1:
                continue
            for u in range(max(cx - 1, low[0]), min(cx + 1, high[0]) + 1):
                row = (u - low[0]) * width - low[1]
                lo = np.searchsorted(keys, row + v0, side="left")
                hi = np.searchsorted(keys, row + v1, side="right")
                for s in range(lo, hi):
                    j = kept[order[s]]
                    dx, dy = x1[j] - px, y1[j] - py
                    da = dx * dx + dy * dy
                    if da > r2:
                        continue
                    dx, dy = x2[j] - qx, y2[j] - qy
                    db = dx * dx + dy * dy
                    if db > r2:
                        continue
                    d = max(da, db)
                    if d < best or (d == best and j < arg):
                        best, arg = d, j
                    every = True
                    for c in range(m):
                        if values[j, c] >= values[i, c]:
                            bits |= 1 << c
                        else:
                            every = False
                    if every:
                        full = True
        nearest[t] = arg
        if arg >= 0:
            distance[t] = math.sqrt(best)
        some[t] = bits
        whole[t] = full
    return nearest, distance, some, whole


def _quantiles(values: np.ndarray) -> Dict:
    values = np.asarray(values, dtype=np.float64)
    if not len(values):
        return {"p50": None, "p90": None, "max": None}
    p50, p90 = np.percentile(values, [50, 90])
    return {"p50": round(float(p50), 3), "p90": round(float(p90), 3), "max": round(float(values.max()), 3)}


def keepers(table: Table, keep: np.ndarray, radius: float = RADIUS):
    """The keeper of every dropped line (the module docstring): (summary, nearest, distance) with
    nearest[i] the row of line i's nearest kept line within `radius` (-1: none, or line i is kept) and
    distance[i] its distance in metres (inf likewise)."""
    import mapping
    n = len(table)
    names = [(name, column) for name, column in VALUES if column in table]
    values = np.ascontiguousarray(np.column_stack([table[column] for _, column in names])
                                  if names else np.zeros((n, 0)), dtype=np.float64)
    known = np.isfinite(values)
    values = np.where(known, values, -np.inf)  # a value not known: nothing to lose, nothing to offer
    dropped, kept = np.flatnonzero(~keep), np.flatnonzero(keep)
    nearest = np.full(n, -1, dtype=np.int64)
    distance = np.full(n, np.inf)
    some = np.zeros(len(dropped), dtype=np.int64)
    whole = np.zeros(len(dropped), dtype=bool)
    if len(dropped) and len(kept):
        x1, y1, x2, y2 = (np.ascontiguousarray(table[k], dtype=np.float64) for k in ("x1", "y1", "x2", "y2"))
        order, keys, low, high, width = mapping._cell_index(np.column_stack([x1, y1]), kept, float(radius))
        near, dist, some, whole = _keepers(x1, y1, x2, y2, values, dropped, kept, order, keys, low, high,
                                           int(width), float(radius))
        nearest[dropped], distance[dropped] = near, dist
    has = nearest[dropped] >= 0
    with_keeper, keeper = dropped[has], nearest[dropped][has]
    summary = {"radius_m": float(radius), "dropped": int(len(dropped)), "with_keeper": int(has.sum()),
               "violations": int((~has).sum()), "distance_m": _quantiles(distance[dropped][has]), "values": {}}
    not_worse_all = np.ones(len(with_keeper), dtype=bool)
    for c, (name, column) in enumerate(names):
        not_worse = values[keeper, c] >= values[with_keeper, c]
        not_worse_all &= not_worse
        both = ~not_worse & known[keeper, c] & known[with_keeper, c]
        summary["values"][name] = {
            "column": column, "nearest_not_worse": int(not_worse.sum()),
            "some_keeper_not_worse": int(((some[has] >> c) & 1).sum()),
            "loss_where_worse": _quantiles(values[with_keeper, c][both] - values[keeper, c][both])}
    summary["values_missing"] = [name for name, column in VALUES if column not in table]
    summary["nearest_not_worse_in_all"] = int(not_worse_all.sum())
    summary["some_keeper_not_worse_in_all"] = int(whole[has].sum())
    return summary, nearest, distance


# ---------------------------------------------------------------------------------------------
# the never-prune list

def never_prune(table: Table, keep: np.ndarray, places: Places, cell: float = STACK_CELL,
                step: float = STACK_STEP) -> Dict:
    """The never-prune items, each counted by itself (the module docstring)."""
    n, count = len(table), len(places)
    by_place = PerGroup(places.place, count)
    emptied = np.bincount(places.place[keep], minlength=count) == 0
    out = {"best_per_sort_key": {}}
    for key, label, value, largest in SORT_KEYS:
        v = value(table)
        if v is None:
            out["best_per_sort_key"][key] = {"label": label, "available": False}
            continue
        v = np.asarray(v, dtype=np.float64)
        v = np.where(np.isfinite(v), v, np.nan)
        pick = np.fmax if largest else np.fmin
        best, left = by_place.reduce(v, pick), by_place.reduce(np.where(keep, v, np.nan), pick)
        has = np.isfinite(best)
        with np.errstate(invalid="ignore"):
            lost = has & ~((left >= best) if largest else (left <= best))
        partly = lost & ~emptied
        out["best_per_sort_key"][key] = {
            "label": label, "available": True, "largest_first": largest, "places_with_a_value": int(has.sum()),
            "lost": int(lost.sum()), "lost_in_places_with_lines_left": int(partly.sum()),
            "loss": _quantiles(np.abs(best - left)[partly & np.isfinite(left)])}
    if "elev_a1" in table and "elev_a2" in table:
        bucket = PerGroup(stack_buckets(table, cell))
        height = mean_anchor_height(table)
        top, low = bucket.reduce(height, np.maximum), bucket.reduce(height, np.minimum)
        left = bucket.reduce(np.where(keep, height, -np.inf), np.maximum)
        stack = (top - low) >= step
        out["stack_tops"] = {"available": True, "cell_m": cell, "step_m": step, "stacks": int(stack.sum()),
                             "lines_in_stacks": int(stack[bucket.ids].sum()),
                             "top_level_lost": int((stack & ~(left > top - step)).sum()),
                             "highest_line_lost": int((stack & ~(left >= top)).sum())}
    else:
        out["stack_tops"] = {"available": False}
    bearing = np.degrees(np.arctan2(table["x2"] - table["x1"], table["y2"] - table["y1"])) % 180.0
    sectors = int(round(180.0 / SECTOR))
    code = places.place * sectors + np.minimum((bearing // SECTOR).astype(np.int64), sectors - 1)
    before, after = np.unique(code), np.unique(code[keep])
    lost = np.setdiff1d(before, after, assume_unique=True)
    out["sectors"] = {"sector_deg": SECTOR, "pairs": int(len(before)), "lost": int(len(lost)),
                      "lost_in_places_with_lines_left": int((~emptied[lost // sectors]).sum())}
    valid = (table["lift_no_zone"] == 0) if "lift_no_zone" in table else np.ones(n, dtype=bool)
    out["valid_without_zone_and_frames"] = {"column": "lift_no_zone" in table, "lines": int(valid.sum()),
                                            "dropped": int((valid & ~keep).sum())}
    return out


# ---------------------------------------------------------------------------------------------
# the known lines (private: counts only)

def _candidates(a, b, tol: float, lengths: Sequence[float], xy1: np.ndarray, xy2: np.ndarray,
                length: np.ndarray) -> np.ndarray:
    """The found lines that match a known line (a, b: its ends in the grid's CRS) as the truth check
    matches them (tools/truth_analysis.py _distances and candidates): both anchors within tol of the
    ends, either way round, and the length within tol of one of the known lengths; the nearest first
    (the sum of the two anchor distances, the lowest row among ties)."""
    d11, d22 = np.hypot(*(xy1 - a).T), np.hypot(*(xy2 - b).T)
    d12, d21 = np.hypot(*(xy1 - b).T), np.hypot(*(xy2 - a).T)
    sums = np.minimum(np.where((d11 <= tol) & (d22 <= tol), d11 + d22, np.inf),
                      np.where((d12 <= tol) & (d21 <= tol), d12 + d21, np.inf))
    if len(lengths):
        fits = np.zeros(len(xy1), dtype=bool)
        for known in lengths:
            fits |= np.abs(length - known) <= tol
        sums = np.where(fits, sums, np.inf)
    rows = np.flatnonzero(np.isfinite(sums))
    return rows[np.argsort(sums[rows], kind="stable")]


def known_lines(folder: str, a_rule: Rule, params: Dict, radius: float = RADIUS) -> Dict:
    """The known lines of a truth-check pass folder under a rule (the module docstring): counts per type
    of line, nothing that tells a line or a place. A rule that cannot run on the captures' tables (a
    column they lack) gives {"error": ...}. "terrain" (the captures with and without grids) is there
    only when the rule read table.terrain."""
    from pyproj import Transformer
    blank = lambda: {"matched_before": 0, "within_tolerance_after": 0, "matched_line_kept": 0,  # noqa: E731
                     "kept_line_within_radius_of_matched": 0}
    out = {"radius_m": float(radius), "captures": 0, "captures_unreadable": 0, "found_lines": 0,
           "found_lines_kept": 0, "matching_as_the_truth_check": 0, "all": blank(), "types": {}}
    transformers = {}
    for name in sorted(os.listdir(folder)):
        cluster = os.path.join(folder, name)
        try:
            with open(os.path.join(cluster, "analysis.json"), encoding="utf-8") as f:
                analysis = json.load(f)
        except (OSError, ValueError):
            continue
        records = [r for r in analysis.get("records") or [] if r.get("match")]
        if analysis.get("status") != "done" or not records:
            continue
        try:
            table = capture_table(cluster)
            with open(os.path.join(cluster, "known.json"), encoding="utf-8") as f:
                known = {k["id"]: k for k in json.load(f)}
            crs = table.meta["crs"]
            if crs not in transformers:
                transformers[crs] = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
            to_grid = transformers[crs].transform
            xy1 = np.column_stack(to_grid(table["lon1"], table["lat1"]))  # as the truth check: from lat, lon
            xy2 = np.column_stack(to_grid(table["lon2"], table["lat2"]))
        except (OSError, ValueError, KeyError):
            out["captures_unreadable"] += 1
            continue
        try:
            keep = apply_rule(a_rule, table, params)
        except KeyError as e:
            return {"error": f"the rule cannot run on the captures' tables: they have no column {e.args[0]!r}"}
        except Exception as e:  # noqa: BLE001  (the text of an error may hold values of a capture: its type only)
            return {"error": f"the rule failed on a capture's table: {type(e).__name__}"}
        out["captures"] += 1
        if table.terrain_read:  # the rule asked for the terrain: said in the output, with the captures without
            terrain = out.setdefault("terrain", {"captures_with_terrain": 0, "captures_without_terrain": 0})
            terrain["captures_without_terrain" if table._terrain is None else "captures_with_terrain"] += 1
        out["found_lines"] += len(table)
        out["found_lines_kept"] += int(keep.sum())
        length = np.where(np.isfinite(table["length"]), table["length"], np.hypot(*(xy2 - xy1).T))
        x1, y1, x2, y2 = (table[k] for k in ("x1", "y1", "x2", "y2"))
        for record in records:
            line, index = known.get(record.get("id")), int(record["match"]["index"])
            if line is None or not 0 <= index < len(table):
                continue
            a, b = (np.array(to_grid(line[end][1], line[end][0]), dtype=np.float64) for end in ("a", "b"))
            lengths = [float(v) for v in (line.get("stated_m"), line.get("geodesic_m")) if v is not None]
            rows = _candidates(a, b, float(record["tol"]), lengths, xy1, xy2, length)
            if len(rows) and rows[0] == index and len(rows) == record["match"].get("candidates", len(rows)):
                out["matching_as_the_truth_check"] += 1
            elif index not in rows:  # the truth check's own match stays a candidate
                rows = np.concatenate([[index], rows])
            straight = np.maximum(np.hypot(x1 - x1[index], y1 - y1[index]), np.hypot(x2 - x2[index], y2 - y2[index]))
            crossed = np.maximum(np.hypot(x1 - x2[index], y1 - y2[index]), np.hypot(x2 - x1[index], y2 - y1[index]))
            for counts in (out["all"], out["types"].setdefault(str(record.get("type") or "other"), blank())):
                counts["matched_before"] += 1
                counts["within_tolerance_after"] += int(keep[rows].any())
                counts["matched_line_kept"] += int(keep[index])
                counts["kept_line_within_radius_of_matched"] += int((keep & (np.minimum(straight, crossed)
                                                                              <= radius)).any())
    out["types"] = {k: out["types"][k] for k in sorted(out["types"])}
    return out


# ---------------------------------------------------------------------------------------------
# the audit

def _number(n) -> str:
    return "–" if n is None else f"{n:,}".replace(",", " ") if isinstance(n, int) else f"{n:g}"


def _share(n: int, d: int) -> str:
    return f"{100.0 * n / d:.1f} %" if d else "–"


@dataclass
class Audit:
    """The audit of one rule on one table: summary (what audit.json holds), keep (the rule's mask),
    places (before the rule), nearest and distance (keepers: per line)."""
    table: Table
    rule: Rule
    params: Dict
    keep: np.ndarray
    places: Places
    nearest: np.ndarray
    distance: np.ndarray
    summary: Dict = field(default_factory=dict)

    @property
    def title(self) -> str:
        params = ", ".join(f"{k} {v:.12g}" if isinstance(v, float) else f"{k} {v}" for k, v in self.params.items())
        return self.rule.label + (f", {params}" if params else "")

    def markdown(self) -> str:
        """audit.md: the audit as a table for a report, then one row for a table of cases."""
        s = self.summary
        lines, places, k, never = s["lines"], s["places"], s["keepers"], s["never_prune"]
        n, d, radius = lines["before"], lines["dropped"], f"{k['radius_m']:g} m"
        rows = [("Lines kept", lines["kept"], _share(lines["kept"], n)),
                ("Lines dropped", d, _share(d, n)),
                (f"Places before ({places['source']}, {places['distance_m']:g} m)", places["before"], ""),
                ("Places emptied (no line kept)", places["emptied"], _share(places["emptied"], places["before"])),
                ("Places whose shown line is dropped", places["representatives_dropped"],
                 _share(places["representatives_dropped"], places["before"])),
                (f"Places after (kept lines grouped again from {places['grouping_reads']})",
                 places["after_grouped_again"], "")]
        check = places.get("check")
        if check:
            rows.append(("Check: every line grouped again / saved places",
                         f"{_number(check['grouped_again'])} / {_number(check['saved'])}",
                         f"{_share(check['lines_in_the_same_place'], check['lines'])} of lines in the same place"))
        rows += [(f"Dropped lines with a kept line within {radius}", k["with_keeper"], _share(k["with_keeper"], d)),
                 (f"**Violations: dropped lines without a kept line within {radius}**", k["violations"],
                  _share(k["violations"], d))]
        for name, v in k["values"].items():
            loss = v["loss_where_worse"]
            rows.append((f"Nearest kept line not worse in {name}", v["nearest_not_worse"],
                         _share(v["nearest_not_worse"], k["with_keeper"])
                         + (f"; where worse: median {loss['p50']:g}, largest {loss['max']:g}"
                            if loss["max"] is not None else "")))
        rows += [("Nearest kept line not worse in all of them", k["nearest_not_worse_in_all"],
                  _share(k["nearest_not_worse_in_all"], k["with_keeper"])),
                 (f"Some kept line within {radius} not worse in all of them", k["some_keeper_not_worse_in_all"],
                  _share(k["some_keeper_not_worse_in_all"], k["with_keeper"]))]
        for key, v in never["best_per_sort_key"].items():
            if not v["available"]:
                rows.append((f"Never prune: place's best line by {v['label']}", "not in the table", ""))
                continue
            rows.append((f"Never prune: places that lose their best line by {v['label']}", v["lost"],
                         f"of {_number(v['places_with_a_value'])}; {_number(v['lost_in_places_with_lines_left'])} "
                         "in places with lines left"))
        t = never["stack_tops"]
        if t["available"]:
            rows.append((f"Never prune: stacks that lose their top level ({t['step_m']:g} m)", t["top_level_lost"],
                         f"of {_number(t['stacks'])} stacks; the highest line itself: "
                         f"{_number(t['highest_line_lost'])}"))
        t = never["sectors"]
        rows.append((f"Never prune: place and {t['sector_deg']:g}° sector pairs left without a line", t["lost"],
                     f"of {_number(t['pairs'])}; {_number(t['lost_in_places_with_lines_left'])} in places with "
                     "lines left"))
        t = never["valid_without_zone_and_frames"]
        rows.append(("Never prune: lines valid without zone and A-frames that are dropped", t["dropped"],
                     f"of {_number(t['lines'])}" + ("" if t["column"] else " (no such column: every line)")))
        known = s.get("known")
        if known and "error" in known:
            rows.append(("Known lines", "not measured", known["error"]))
        elif known:
            if "terrain" in known:
                rows.append(("Known lines: captures with terrain for the rule / without",
                             f"{_number(known['terrain']['captures_with_terrain'])} / "
                             f"{_number(known['terrain']['captures_without_terrain'])}", ""))
            for name, v in [("all", known["all"])] + list(known["types"].items()):
                m = v["matched_before"]
                rows += [(f"Known lines ({name}) with a found line within tolerance before", m, ""),
                         (f"Known lines ({name}) that still have one", v["within_tolerance_after"],
                          _share(v["within_tolerance_after"], m)),
                         (f"Known lines ({name}) whose matched line is kept", v["matched_line_kept"],
                          _share(v["matched_line_kept"], m)),
                         (f"Known lines ({name}) with a kept line within {known['radius_m']:g} m of the matched one",
                          v["kept_line_within_radius_of_matched"],
                          _share(v["kept_line_within_radius_of_matched"], m))]
        text = [f"### {self.title} on {s['table']['name']} ({_number(n)} lines)", "",
                "| Item | Count | Share or note |", "|---|---:|---|"]
        text += [f"| {a} | {_number(b) if not isinstance(b, str) else b} | {c} |" for a, b, c in rows]
        clr = never["best_per_sort_key"]["clr"]
        text += ["", "One row for a table of cases:", "",
                 "| Table | Rule | Lines | Kept | Places | Emptied | Shown line dropped | Places after | "
                 f"No kept line within {radius} | Best clearance lost | Stack tops lost | Sectors lost | "
                 "Valid without zone and A-frames dropped |", "|---|---|" + "---:|" * 11,
                 f"| {s['table']['name']} | {self.title} | {_number(n)} | {_number(lines['kept'])} "
                 f"({_share(lines['kept'], n)}) | {_number(places['before'])} | {_number(places['emptied'])} | "
                 f"{_number(places['representatives_dropped'])} | {_number(places['after_grouped_again'])} | "
                 f"{_number(k['violations'])} | {_number(clr.get('lost'))} | "
                 f"{_number(never['stack_tops'].get('top_level_lost'))} | {_number(never['sectors']['lost'])} | "
                 f"{_number(never['valid_without_zone_and_frames']['dropped'])} |", ""]
        return "\n".join(text)

    def write(self, out: str, pictures: bool = False, picture_places: int = PICTURE_PLACES) -> List[str]:
        """audit.json, audit.md and violations.csv in `out` (made when missing), with pictures=True also
        pictures/place-<k>.png; returns the files written."""
        os.makedirs(out, exist_ok=True)
        files = [os.path.join(out, name) for name in ("audit.json", "audit.md", "violations.csv")]
        with open(files[0], "w", encoding="utf-8") as f:
            json.dump(self.summary, f, ensure_ascii=False, indent=1)
            f.write("\n")
        with open(files[1], "w", encoding="utf-8") as f:
            f.write(self.markdown())
        t = self.table
        rows = np.flatnonzero(~self.keep & (self.nearest < 0))[:VIOLATIONS_MAX]
        names = [c for c in ("length", "clearance", "height_max", "high_pct", "x1", "y1", "x2", "y2") if c in t]
        with open(files[2], "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["line", "csv_row", "place"] + names)  # csv_row: the line's row in lines.csv (2: the first; the export's of a store)
            for i in rows.tolist():
                writer.writerow([i, i + 2, int(self.places.place[i]) + 1] + [repr(float(t[c][i])) for c in names])
        if pictures:
            files += draw_places(self, os.path.join(out, "pictures"), picture_places)
        return files


def audit(table: Table, a_rule, params: Optional[Dict] = None, radius: float = RADIUS,
          known: Optional[str] = None, timings: Optional[Dict] = None) -> Audit:
    """Audit one rule (its registered name, or a Rule) with `params` on a table (the module docstring).
    known: a truth-check pass folder, for the private counts of the known lines. timings: a dict
    that gets the seconds of each part."""
    if not isinstance(a_rule, Rule):
        if a_rule not in RULES:
            raise ValueError(f"no rule named {a_rule} (registered: {', '.join(sorted(RULES)) or 'none'})")
        a_rule = RULES[a_rule]
    timings = {} if timings is None else timings
    clock = time.perf_counter()

    def lap(name):
        nonlocal clock
        now = time.perf_counter()
        timings[name], clock = round(now - clock, 2), now

    params = a_rule.parameters(params)
    n = len(table)
    keep = apply_rule(a_rule, table, params)
    lap("rule")
    before = places_of(table)
    after = places_of(table, keep)
    check = grouping_check(table)
    lap("places")
    emptied = np.bincount(before.place[keep], minlength=len(before)) == 0
    keeper_summary, nearest, distance = keepers(table, keep, radius)
    lap("keepers")
    never = never_prune(table, keep, before)
    lap("never-prune")
    summary = {
        "tool": "prune_study", "table": {
            "name": table.name, "folder": os.path.basename(table.path) if table.path else None, "lines": n,
            "saved_summary": table.meta.get("summary"),
            "settings": {k: table.params.get(k) for k in ("model", "end_zone", "anchor_lift", "min_length",
                                                          "max_length", "slope_threshold", "resolution")}},
        "rule": {"name": a_rule.name, "title": a_rule.title, "idea": a_rule.idea, "params": params},
        "lines": {"before": n, "kept": int(keep.sum()), "dropped": int(n - keep.sum())},
        "places": {"before": len(before), "source": "saved by the search" if before.source == "saved"
                   else f"grouped here from {table.source}", "distance_m": before.distance,
                   "emptied": int(emptied.sum()), "representatives_dropped": int((~keep[before.rep]).sum()),
                   "after_grouped_again": len(after), "grouping_reads": table.source, "check": check},
        "keepers": keeper_summary, "never_prune": never, "known": None}
    if table._terrain is not None:  # a terrain attached to the table (--terrain): said, nothing otherwise
        summary["table"]["terrain"] = {"shape": list(table._terrain.shape), "res": table._terrain.res,
                                       "water": table._terrain.water is not None}
    if known:
        summary["known"] = known_lines(known, a_rule, params, radius)
        lap("known lines")
    return Audit(table, a_rule, params, keep, before, nearest, distance, summary)


# ---------------------------------------------------------------------------------------------
# pictures

KEPT_COLOUR, DROPPED_COLOUR = "#2a78d6", "#eb6834"  # checked as a pair for colour-blind readers
INK, MUTED, SURFACE = "#0b0b0b", "#52514e", "#fcfcfb"


def _sample(rows: np.ndarray, limit: int = PICTURE_LINES) -> np.ndarray:
    return rows if len(rows) <= limit else rows[np.linspace(0, len(rows) - 1, limit).round().astype(np.int64)]


def _points(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """The different points (x, y), one row each."""
    return np.unique(np.column_stack([x, y]), axis=0) if len(x) else np.zeros((0, 2))


def draw_places(result: Audit, out: str, count: int = PICTURE_PLACES) -> List[str]:
    """Plan views of the `count` largest places (by their lines before the rule), one picture each: the
    upper row before the rule, the lower row after it; left the whole place (the lines), then both
    ends enlarged (the anchors as points: after the rule those that keep a line and those that lose
    all of theirs). Metres from the place's middle, north up. The pictures show the run's own places:
    they belong beside the audit, never in the repository."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.collections import LineCollection
    from matplotlib.lines import Line2D
    t, keep, places = result.table, result.keep, result.places
    os.makedirs(out, exist_ok=True)
    sizes = places.sizes()
    files = []
    for rank, p in enumerate(np.argsort(-sizes, kind="stable")[:count].tolist(), 1):
        rows, shown = np.flatnonzero(places.place == p), int(places.rep[p])
        x1, y1, x2, y2 = (t[c][rows] for c in ("x1", "y1", "x2", "y2"))
        # every line turned as the shown line lies: end A near its first anchor
        sx1, sy1, sx2, sy2 = (t[c][shown] for c in ("x1", "y1", "x2", "y2"))
        turn = (np.hypot(x1 - sx1, y1 - sy1) + np.hypot(x2 - sx2, y2 - sy2)
                > np.hypot(x1 - sx2, y1 - sy2) + np.hypot(x2 - sx1, y2 - sy1))
        mx, my = (min(x1.min(), x2.min()) + max(x1.max(), x2.max())) / 2, (min(y1.min(), y2.min())
                                                                             + max(y1.max(), y2.max())) / 2
        ax_, ay_ = np.where(turn, x2, x1) - mx, np.where(turn, y2, y1) - my
        bx_, by_ = np.where(turn, x1, x2) - mx, np.where(turn, y1, y2) - my
        kept = keep[rows]
        at = int(np.flatnonzero(rows == shown)[0])
        fig, axes = plt.subplots(2, 3, figsize=(17, 10.5), dpi=100, facecolor=SURFACE)
        for row, after in ((0, False), (1, True)):
            ax = axes[row, 0]
            parts = ([(~kept, DROPPED_COLOUR, "dropped lines"), (kept, KEPT_COLOUR, "kept lines")] if after
                     else [(np.ones(len(rows), dtype=bool), MUTED, "all lines")])
            handles = []
            for mask, colour, label in parts:
                drawn = _sample(np.flatnonzero(mask))
                segments = np.stack([np.column_stack([ax_[drawn], ay_[drawn]]),
                                     np.column_stack([bx_[drawn], by_[drawn]])], axis=1)
                ax.add_collection(LineCollection(segments, colors=colour, linewidths=0.6,
                                                 alpha=float(np.clip(600.0 / max(len(drawn), 1), 0.05, 0.8))))
                handles.append(Line2D([], [], color=colour, lw=2, label=f"{label} ({_number(int(mask.sum()))}"
                               + (f", {_number(len(drawn))} drawn)" if len(drawn) < mask.sum() else ")")))
            state = "" if not after else " (kept)" if keep[shown] else " (dropped)"
            ax.plot([ax_[at], bx_[at]], [ay_[at], by_[at]], color=INK, lw=1.4, ls=(0, (5, 3)))
            handles.append(Line2D([], [], color=INK, lw=1.4, ls=(0, (5, 3)),
                                  label="the line shown for the place today" + state))
            xs, ys = np.concatenate([ax_, bx_]), np.concatenate([ay_, by_])
            pad = 0.05 * max(xs.max() - xs.min(), ys.max() - ys.min(), 1.0)
            ax.set_xlim(xs.min() - pad, xs.max() + pad)
            ax.set_ylim(ys.min() - pad, ys.max() + pad)
            ax.set_title(f"After: {_number(int(kept.sum()))} lines kept, {_number(int((~kept).sum()))} dropped"
                         if after else f"Before: {_number(len(rows))} lines", color=INK, fontsize=12, loc="left")
            falling = (bx_[at] - ax_[at]) * (by_[at] - ay_[at]) < 0  # the lines run from the upper left corner
            ax.legend(handles=handles, loc="upper right" if falling else "upper left", frameon=True,
                      facecolor=SURFACE, edgecolor="#c9c8c3", labelcolor=INK, fontsize=9)
            ax.set_ylabel("metres north of the place's middle", color=MUTED)
            for column, (ex, ey, name) in enumerate(((ax_, ay_, "A"), (bx_, by_, "B")), 1):
                ax = axes[row, column]
                every, left = _points(ex, ey), _points(ex[kept], ey[kept])
                if after:
                    lost = _points(ex[~kept], ey[~kept])
                    if len(left) and len(lost):  # the anchors that lose every line: not among the kept ones
                        codes = lambda v: (np.round(v[:, 0] * 100).astype(np.int64) * 10 ** 9  # noqa: E731
                                           + np.round(v[:, 1] * 100).astype(np.int64))
                        lost = lost[~np.isin(codes(lost), codes(left))]
                    ax.scatter(lost[:, 0], lost[:, 1], s=9, color=DROPPED_COLOUR, linewidths=0,
                               label=f"anchors that lose all their lines ({_number(len(lost))})")
                    ax.scatter(left[:, 0], left[:, 1], s=14, color=KEPT_COLOUR, linewidths=0,
                               label=f"anchors with a kept line ({_number(len(left))})")
                else:
                    ax.scatter(every[:, 0], every[:, 1], s=9, color=MUTED, linewidths=0,
                               label=f"anchors ({_number(len(every))})")
                ax.scatter([ex[at]], [ey[at]], s=90, facecolors="none", edgecolors=INK, linewidths=1.4,
                           label="the shown line's anchor")
                span = max(every[:, 0].max() - every[:, 0].min(), every[:, 1].max() - every[:, 1].min(), 10.0)
                cx, cy = (every[:, 0].max() + every[:, 0].min()) / 2, (every[:, 1].max() + every[:, 1].min()) / 2
                ax.set_xlim(cx - 0.56 * span, cx + 0.56 * span)
                ax.set_ylim(cy - 0.56 * span, cy + 0.9 * span)  # room for the legend above the anchors
                ax.set_title(f"End {name}, enlarged", color=INK, fontsize=12, loc="left")
                ax.legend(loc="upper left", frameon=True, facecolor=SURFACE, edgecolor="#c9c8c3", labelcolor=INK,
                          fontsize=9)
            for ax in axes[row]:
                ax.set_facecolor(SURFACE)
                ax.set_aspect("equal")
                ax.grid(color="#e4e3df", lw=0.6)
                ax.tick_params(colors=MUTED)
                ax.set_axisbelow(True)
                for spine in ax.spines.values():
                    spine.set_color("#c9c8c3")
                if after:
                    ax.set_xlabel("metres east of the place's middle", color=MUTED)
        fig.suptitle(f"{t.name}: place {p + 1} of {_number(len(places))} (number {rank} by size). {result.title}",
                     color=INK, fontsize=12, x=0.01, ha="left")
        fig.tight_layout(rect=(0, 0, 1, 0.96))
        files.append(os.path.join(out, f"place-{rank}.png"))
        fig.savefig(files[-1], facecolor=SURFACE)
        plt.close(fig)
    return files


# ---------------------------------------------------------------------------------------------
# the command line

def _value(text: str):
    for kind in (int, float):
        try:
            return kind(text)
        except ValueError:
            pass
    return {"true": True, "false": False, "none": None}.get(text.lower(), text)


def parse_params(items: Sequence[str]) -> Dict:
    """--param k=v ... as a dict: whole numbers, numbers, true/false/none, anything else as text."""
    out = {}
    for item in items:
        key, sep, text = item.partition("=")
        if not sep or not key:
            raise ValueError(f"--param {item}: expected name=value")
        out[key.strip()] = _value(text.strip())
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="What a pruning rule keeps of a saved table of lines, and an "
                                                 "audit of what it drops.")
    parser.add_argument("table", help="a run's folder: its store (lines.arrow) or lines.csv, and run.json (read only)")
    parser.add_argument("--rule", required=True, help="the rule's registered name")
    parser.add_argument("--param", action="append", default=[], metavar="K=V", help="a parameter of the rule")
    parser.add_argument("--rules-file", action="append", default=[], metavar="F",
                        help="a Python file that registers more rules with prune_study.rule")
    parser.add_argument("--radius", type=float, default=RADIUS,
                        help=f"metres: a keeper's ends lie this near the dropped line's (default {RADIUS:g})")
    parser.add_argument("--known", metavar="DIR", help="a truth-check pass folder: private counts of the known "
                                                       "lines that keep a found line nearby")
    parser.add_argument("--pictures", action="store_true", help="plan views of the largest places")
    parser.add_argument("--picture-places", type=int, default=PICTURE_PLACES, metavar="N")
    parser.add_argument("--out", required=True, help="the folder of audit.json, audit.md, violations.csv")
    parser.add_argument("--cache", metavar="DIR", help="the folder of the parsed columns (default: "
                                                       f"{CACHE_FOLDER} in the temporary folder)")
    parser.add_argument("--no-cache", action="store_true", help="parse the lines every time, keep nothing")
    parser.add_argument("--threads", type=int, help="numba's threads (the results do not depend on them)")
    parser.add_argument("--terrain", metavar="F.npz", help="the grid under the table's anchors for rules that read "
                                                           "table.terrain: an .npz with z, res, left, top (water)")
    args = parser.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    if args.threads:
        numba.set_num_threads(args.threads)
    try:
        for path in args.rules_file:
            load_rules_file(path)
        if args.rule not in RULES:
            raise ValueError(f"no rule named {args.rule} (registered: {', '.join(sorted(RULES))})")
        params = RULES[args.rule].parameters(parse_params(args.param))
        terrain = load_terrain(args.terrain) if args.terrain else None
    except (ValueError, OSError) as e:
        print(f"prune_study: {e}", file=sys.stderr)
        return 2
    start = time.perf_counter()
    table = load_table(args.table, cache=False if args.no_cache else args.cache)
    if terrain is not None:
        table.terrain = terrain
    timings = {"table": round(time.perf_counter() - start, 2)}
    result = audit(table, args.rule, params, radius=args.radius, known=args.known, timings=timings)
    start = time.perf_counter()
    files = result.write(args.out, pictures=args.pictures, picture_places=args.picture_places)
    timings["files"] = round(time.perf_counter() - start, 2)
    print(result.markdown())
    print("seconds: " + ", ".join(f"{k} {v:g}" for k, v in timings.items()) + f"; total {sum(timings.values()):.1f}")
    print("written: " + ", ".join(os.path.relpath(f, args.out) for f in files) + f" in {os.path.abspath(args.out)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
