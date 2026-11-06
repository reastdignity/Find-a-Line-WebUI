"""
Run by hand: how many lines a "no-fall zone" at the ends of a line and A-frames lifting its
anchors would add, and what they cost (the end-zone study, 2026-11-06).

The rule measured (production's line search since wave 1: helpers.end_zone_rule,
linesearch.find_valid_lines(end_zone=, lift=, end_clearance=, zone_cap=, zones=)): a pixel of a
line passes when its strict margin
s = limit - terrain (helpers.max_safe_elevation; the surface model likewise) satisfies

    s > -lift - delta * [the pixel lies in the end zone]

lift: an A-frame of that height at both ends; delta = fall - end_clearance (fall:
helpers.fall_allowance, the 6 m of the formula or the sag model's fall zone; end_clearance
>= 0 and at most fall); the zone: the steps closer to the nearer anchor than min(end_zone,
cap * length) (helpers.zone_steps). The limit itself is never changed: at zone 0 and lift 0
every operation is today's.

capture runs a search in a child process with a data folder of its own whose cache/ links to
the real cache (a junction on Windows, removed as a link afterwards, never followed), with
linesearch.find_valid_lines wrapped as tools/perf_line_funnel.py wraps it (each call's inputs
and parameters in <out>/<place>/capture/call-<k>/, with grid.json: the grid's georeference)
and its options in <out>/<place>/capture.json. One capture per place and slope threshold
(--slope-threshold is an option of the search):

    uv run tools/end_zone_study.py capture zabi-kon-45 --out <scratch>/study -- \
        --lat 50.1559508 --lon 19.7562722 --slope-threshold 45

variants runs find_valid_lines on a capture: once at the superset (the largest zone and lift,
with the ladder of --zones) and once at zone 0 and lift 0 (the baseline: today's search), each
timed per stage (free directions, anchor pairs, checking lines: wall and CPU seconds of its bars)
after a warm-up of numba, with the funnel of each. Every line of the superset carries the
smallest strict margin per bucket of the ladder (the columns zone_margins, zone_margins_nmpt),
so the valid lines at every (zone, lift) of the grid come from the superset's lines without
another search (helpers.valid_at). It stops unless the (0, 0) entry equals the baseline (the same
lines in the same order, and their clearances). The spots of each entry by mapping.group_lines
(group distance and rule from the capture's options, defaults otherwise; by the clearances and
marks over obstacles a search at that entry gives; over the lines of find_valid_lines, so not
always the run's spot count). Writes <place>/variants.json and variants.npz (the superset's
lines, today's clearance of each and where each is valid).

    uv run tools/end_zone_study.py variants <scratch>/study/zabi-kon-45 [--zones 0,5,10,20] \
        [--lifts 0,1,2] [--cap 0.25] [--end-clearance 0] [--threads N]

diagnose looks at known real lines (a JSON list of {"name", "a": [lat, lon], "b": [lat, lon]})
on a capture's grid: the nearest pixels of slope 45/40/35/30 degrees or more within --radius
metres of each end, the best pair of pixels within that radius of the two ends by today's rule
(the largest clearance), whether today's rule accepts it, else its first failing step from
each end (distance and deficit), and the staircase: the lift each ladder zone needs at least
(the best pair for each; the buckets by helpers.evaluate_line with the ladder). Writes
<place>/diagnose.json.

    uv run tools/end_zone_study.py diagnose <scratch>/study/zabi-kon-45 --lines lines.json

report gathers the places into <out>/study.json and <out>/study.md and draws (unless
--no-pictures) per place a map of the baseline's lines and the new ones of a few variants over
a hillshade, and a profile chip of each diagnosed line:

    uv run tools/end_zone_study.py report <out> <scratch>/study/zabi-kon-45 <scratch>/study/zabi-kon-35
"""

import argparse
import contextlib
import glob
import io
import json
import math
import os
import shutil
import subprocess
import sys
import time
from types import SimpleNamespace
from typing import Dict, List, Optional, Sequence

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "tools"))
sys.path.insert(0, os.path.join(HERE, "tests"))

import numba  # noqa: E402
import numpy as np  # noqa: E402

import helpers as sh  # noqa: E402
import linesearch as ls  # noqa: E402
import perf_line_funnel as plf  # noqa: E402

ZONES = (0.0, 5.0, 10.0, 20.0)  # metres: the ladder of end zones
LIFTS = (0.0, 1.0, 2.0)         # metres: the A-frames' heights
CAP = 0.25                      # the zone is at most this share of a line's length
STAGES = ("free directions", "anchor pairs", "checking lines")
THRESHOLDS = (45.0, 40.0, 35.0, 30.0)  # degrees: diagnose's slope thresholds
RADIUS = 5.0                    # metres around each end diagnose searches
WARM_ANCHORS = 300              # anchors of the numba warm-up before the timed runs
MAP_LINES = 20000               # lines a panel of the map draws at most (a sample beyond)
LONG = 250.0                    # metres: the long lines counted apart (the quarry's lines across the lake)
EXAMPLES = 6                    # long new lines the report details per place (distinct spots)


class StudyError(RuntimeError):
    """The superset's lines at zone 0, lift 0 are not today's."""


# ---------------------------------------------------------------------------------------------
# capture

def _unlink(path: str):
    """Remove a directory link (a junction on Windows, a symlink elsewhere), never its target."""
    if os.path.islink(path):
        os.unlink(path)
    elif hasattr(os.path, "isjunction") and os.path.isjunction(path):
        os.rmdir(path)  # the junction only


def capture(place: str, out: str, search_args: List[str], cache_dir: Optional[str]) -> int:
    """The search of a place in a child process (capture_child) with <out>/<place>/data as its
    data folder, data/cache a link to cache_dir (none: a fresh cache), removed afterwards."""
    import regression

    folder = os.path.join(os.path.abspath(out), place)
    data = os.path.join(folder, "data")
    link = os.path.join(data, "cache")
    if os.path.exists(folder):
        _unlink(link)  # the link only, never the cache behind it
        shutil.rmtree(folder)
    os.makedirs(data)
    if cache_dir:
        regression.link(os.path.abspath(cache_dir), link)
    env = {**os.environ, "FINDALINE_PROGRESS": "text", "PYTHONIOENCODING": "utf-8"}
    started = time.time()
    try:
        with open(os.path.join(folder, "output.log"), "w", encoding="utf-8") as log:
            result = subprocess.run([sys.executable, os.path.abspath(__file__), "capture-child", "--out",
                                     os.path.join(folder, "capture"), "--", *search_args, "--data-dir", data],
                                    cwd=HERE, env=env, stdout=log, stderr=subprocess.STDOUT)
    finally:
        if cache_dir:
            _unlink(link)
    with open(os.path.join(folder, "capture.json"), "w") as f:
        json.dump({"place": place, "args": search_args, "seconds": time.time() - started,
                   "returncode": result.returncode, "cache_linked": bool(cache_dir)}, f, indent=1)
    calls = sorted(glob.glob(os.path.join(folder, "capture", "call-*")))
    print(f"{place}: findaline.py exit {result.returncode} (1 also when it found no line), {len(calls)} call(s) "
          f"captured in {folder}")
    return 0 if calls else 1


def capture_child(out: str, search_args: List[str]) -> int:
    """perf_line_funnel's capture plus grid.json (obstacle_study's Capture: the grid's georeference
    and the lines found) with the obstacle rule of production (obstacle_study clears it)."""
    import runpy

    import obstacle_study as ob
    import search

    os.makedirs(out, exist_ok=True)
    os.environ.setdefault("FINDALINE_PROGRESS", "text")
    wrapper = ob.Capture(out)
    original = search._lines

    def lines(plan, data, core=None, before=0):
        try:
            meta = ob.layer_meta(plan)
        except Exception as e:  # a local file as the source: no layer files to record
            meta = {"layer_meta_error": str(e)}
        wrapper.grid, wrapper.meta = (plan.grid, core), meta
        return original(plan, data, core, before)

    search._lines = lines
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


def call_folders(folder: str) -> List[str]:
    """The call folders of a place folder, a capture folder or a call folder itself."""
    if os.path.exists(os.path.join(folder, "inputs.npz")):
        return [folder]
    for pattern in (os.path.join(folder, "capture", "call-*"), os.path.join(folder, "call-*")):
        found = sorted(glob.glob(pattern), key=lambda p: int(p.rsplit("-", 1)[1]))
        if found:
            return found
    raise FileNotFoundError(f"no captured call under {folder}")


def search_option(folder: str, name: str, default=None):
    """The value of a findaline option in the place's capture.json (default when not given)."""
    path = os.path.join(folder, "capture.json")
    if not os.path.exists(path):
        return default
    with open(path) as f:
        args = json.load(f)["args"]
    for k, arg in enumerate(args):
        if arg == name and k + 1 < len(args):
            return args[k + 1]
        if arg.startswith(name + "="):
            return arg.split("=", 1)[1]
    return default


# ---------------------------------------------------------------------------------------------
# the harness: production's line search on a captured call

def setup(folder: str) -> SimpleNamespace:
    """A captured call's inputs (perf_line_funnel.rebuild: the set-up of linesearch.find_valid_lines,
    without its rings), with what the evaluation needs besides."""
    inputs, params, timings = plf.load_call(folder)
    a = plf.rebuild(inputs, params, free_rings=no_rings)
    a.folder, a.params, a.timings = folder, params, timings
    a.surface = inputs.get("surface")
    a.sag_table = plf.sag_table_of(inputs, params)
    a.anchor_values = inputs.get("anchor_values")
    a.strong_given = inputs.get("strong")
    a.nmpt_mode, a.high_above = params["nmpt_mode"], params["high_above"]
    a.fall = sh.fall_allowance(a.sag_table)
    grid_path = os.path.join(folder, "grid.json")
    a.grid = json.load(open(grid_path)) if os.path.exists(grid_path) else None
    return a


def no_rings(z, anchors, *rest):
    """A stand-in for perf_line_funnel.rebuild's rings: production computes its own."""
    return np.zeros((len(anchors), ls.SECTORS), dtype=np.uint8)


def subset(a: SimpleNamespace, n: int) -> SimpleNamespace:
    """The call with its first n anchors only (the warm-up: the same argument types)."""
    b = SimpleNamespace(**vars(a))
    b.anchors = np.ascontiguousarray(a.anchors[:n])
    b.first = None if a.first is None else np.asarray(a.first)[:n]
    b.strong_given = None if a.strong_given is None else np.asarray(a.strong_given)[:n]
    b.anchor_values = None if a.anchor_values is None else np.asarray(a.anchor_values)[:n]
    return b


def limits_of(a: SimpleNamespace) -> Optional[sh.LineLimits]:
    """A fresh helpers.LineLimits of the call (its left_out counted anew)."""
    q = a.params["limits"]
    return None if q is None else sh.LineLimits(**{k: v for k, v in q.items() if k != "left_out"})


def check_rule(a: SimpleNamespace, lift: float, end_zone: float, end_clearance: float, cap: float) -> float:
    """delta of the rule (helpers.end_zone_rule: lift, end zone and delta not negative, the cap
    within 0 .. 0.5; ValueError otherwise)."""
    return sh.end_zone_rule(a.sag_table, end_zone, lift, end_clearance, cap)[0]


def run_rule(a: SimpleNamespace, lift: float = 0.0, end_zone: float = 0.0, cap: float = CAP,
             end_clearance: float = 0.0, zones: Sequence[float] = (), threads: Optional[int] = None
             ) -> SimpleNamespace:
    """linesearch.find_valid_lines on the call at one rule (with the call's limits, nmpt mode and
    the ladder of zones when given): the lines (a LineTable, longest first), the funnel and the
    seconds of its bars."""
    delta = check_rule(a, lift, end_zone, end_clearance, cap)
    zones = np.asarray(sorted(set(float(x) for x in zones)), dtype=np.float64)
    stats, clock = {}, plf.BarClock()
    plf.progress.subscribe(clock)
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            table = ls.find_valid_lines(a.z, a.surface, a.anchors, a.res, a.min_length, a.max_length, a.nmpt_mode,
                                        threads, a.sag_table, a.max_dh_ratio, a.max_dh, a.first, a.high_above,
                                        limits_of(a), a.anchor_values, a.strong_given, stats, end_zone=end_zone,
                                        lift=lift, end_clearance=end_clearance, zone_cap=cap, zones=zones)
    finally:
        plf.progress.unsubscribe(clock)
    funnel = {"anchors": len(a.anchors), **{k: stats.get(k, 0) for k in ("open", "todo", "candidates", "checked",
                                                                        "found", "valid")}}
    return SimpleNamespace(table=table, funnel=funnel, seconds=clock.seconds, zones=zones, lift=lift,
                           end_zone=end_zone, delta=delta, cap=cap)


def valid_grid(run: SimpleNamespace, lifts: Sequence[float], nmpt_mode: Optional[str]) -> np.ndarray:
    """Which of a run's lines are valid at every ladder zone and lift (both at most the run's):
    helpers.valid_at on the terrain's buckets, and the surface's with "reject"."""
    t = run.table.columns
    valid = np.zeros((len(run.table), len(run.zones), len(lifts)), dtype=bool)
    for j in range(len(run.zones)):
        for k, lift in enumerate(lifts):
            ok = sh.valid_at(t["zone_margins"], j, lift, run.delta)
            if nmpt_mode == "reject" and "zone_margins_nmpt" in t:
                ok &= sh.valid_at(t["zone_margins_nmpt"], j, lift, run.delta)
            valid[:, j, k] = ok
    return valid


def decision_at(margins: np.ndarray, j: int, lift: float, delta: float) -> np.ndarray:
    """The clearance (the rule's decision value) of lines at ladder zone j and lift from their
    buckets: what a search at that zone and lift gives them (helpers.decision_values)."""
    inf = np.full(len(margins), np.inf)
    zone = margins[:, :j].min(axis=1) if j and len(margins) else inf
    core = margins[:, j:].min(axis=1) if len(margins) else inf
    c = lift + delta
    return np.minimum(zone if c == 0.0 else zone + c, core if lift == 0.0 else core + lift)


def same_lines(table, other) -> bool:
    """Two LineTables: the same lines in the same order."""
    return (len(table) == len(other) and np.array_equal(table.columns["a1"], other.columns["a1"])
            and np.array_equal(table.columns["a2"], other.columns["a2"]))


def spots(a: SimpleNamespace, table, rows: np.ndarray, clearance: np.ndarray, over: np.ndarray, distance: float,
          by: str) -> int:
    """The groups mapping.group_lines makes of the lines at rows (anchor pixels to the grid's metres),
    by the given clearances and marks over obstacles (those of a search at the entry's zone and lift)."""
    import mapping as mp

    if not len(rows):
        return 0
    t = table.columns
    left, top = (a.grid["left"], a.grid["top"]) if a.grid else (0.0, 0.0)
    xy = lambda p: np.column_stack([left + (p[:, 1] + 0.5) * a.res, top - (p[:, 0] + 0.5) * a.res])  # noqa: E731
    lines = sh.LineTable({"length": t["length"][rows], "clearance": clearance,
                          "height_max": t["height_max"][rows], "over_obstacles": over,
                          "a1_xy": xy(t["a1"][rows]), "a2_xy": xy(t["a2"][rows])})
    with contextlib.redirect_stdout(io.StringIO()):
        return len(mp.group_lines(lines, distance, by))


def variants_call(a: SimpleNamespace, zones: Sequence[float], lifts: Sequence[float], cap: float,
                  end_clearance: float, threads: Optional[int], with_spots: bool, distance: float,
                  by: str, long: float = LONG) -> Dict:
    """variants of one captured call (see the module docstring)."""
    zones = sorted(set([0.0] + [float(x) for x in zones]))
    lifts = sorted(set([0.0] + [float(h) for h in lifts]))
    threads = threads or numba.get_num_threads()
    numba.set_num_threads(threads)
    delta = check_rule(a, lifts[-1], zones[-1], end_clearance, cap)
    warm = subset(a, min(WARM_ANCHORS, len(a.anchors)))  # numba compiles here, not in the timed runs
    run_rule(warm, 0.0, 0.0, cap, end_clearance, threads=threads)
    run_rule(warm, lifts[-1], zones[-1], cap, end_clearance, zones, threads)
    base = run_rule(a, 0.0, 0.0, cap, end_clearance, threads=threads)  # today's search: the baseline
    top = run_rule(a, lifts[-1], zones[-1], cap, end_clearance, zones, threads)
    nz = len(zones)
    valid = valid_grid(top, lifts, a.nmpt_mode)
    # the referee: the superset's lines at zone 0, lift 0 by its buckets are today's (lines and order)
    if not same_lines(top.table.take(valid[:, 0, 0]), base.table):
        raise StudyError(f"{a.folder}: the superset's lines at zone 0, lift 0 differ from find_valid_lines at 0 / 0")
    if not np.array_equal(decision_at(top.table.columns["zone_margins"][valid[:, 0, 0]], 0, 0.0, delta),
                          base.table.columns["clearance"]):
        raise StudyError(f"{a.folder}: the superset's buckets do not give today's clearances")
    if not valid[:, -1, -1].all():
        raise StudyError(f"{a.folder}: a line of the superset run fails the superset's own buckets")
    table = {}
    for j, x in enumerate(zones):
        for k, lift in enumerate(lifts):
            mask = valid[:, j, k]
            entry = {"zone": x, "lift": lift, "lines": int(mask.sum()), "new": int((mask & ~valid[:, 0, 0]).sum())}
            if long:
                longer = top.table.columns["length"] >= long
                entry["long"] = int((mask & longer).sum())
                entry["long_new"] = int((mask & longer & ~valid[:, 0, 0]).sum())
            if with_spots:
                rows = np.flatnonzero(mask)
                clearance = decision_at(top.table.columns["zone_margins"][rows], j, lift, delta)
                over = np.zeros(len(rows), dtype=bool)
                if a.nmpt_mode == "mark" and "zone_margins_nmpt" in top.table.columns:
                    over = decision_at(top.table.columns["zone_margins_nmpt"][rows], j, lift, delta) <= 0
                entry["spots"] = spots(a, top.table, rows, clearance, over, distance, by)
            table[f"{x:g},{lift:g}"] = entry
    return {"call": os.path.basename(os.path.normpath(a.folder)), "anchors": len(a.anchors), "res": a.res,
            "min_length": a.min_length, "max_length": a.max_length, "model": "sag" if a.use_sag else "formula",
            "nmpt_mode": a.nmpt_mode, "fall": a.fall, "delta": delta, "zones": zones, "lifts": lifts, "cap": cap,
            "end_clearance": end_clearance, "threads": numba.get_num_threads(), "long": long, "table": table,
            "funnel": {"baseline": base.funnel, "superset": top.funnel, "production": base.funnel},
            "seconds": {"baseline": base.seconds, "superset": top.seconds, "production": base.seconds},
            "checks": {"superset_00_equals_production": True, "superset_00_clearances": True},
            "_table": top.table, "_valid": valid}


def summed_calls(results: List[Dict]) -> Dict:
    """The calls of a place added up (counts and seconds; the parameters of the first)."""
    first = {k: v for k, v in results[0].items() if not k.startswith("_")}
    if len(results) == 1:
        return first
    total = json.loads(json.dumps(first))
    for r in results[1:]:
        total["anchors"] += r["anchors"]
        for key, e in r["table"].items():
            for name in ("lines", "new", "spots", "long", "long_new"):
                if name in e:
                    total["table"][key][name] += e[name]
        for run in total["funnel"]:
            for name, n in r["funnel"][run].items():
                total["funnel"][run][name] = total["funnel"][run].get(name, 0) + n
        for run in total["seconds"]:
            for stage, (w, c) in r["seconds"][run].items():
                old = total["seconds"][run].get(stage, [0.0, 0.0])
                total["seconds"][run][stage] = [old[0] + w, old[1] + c]
    total["calls"] = [r["call"] for r in results]
    if any("spots" in e for e in total["table"].values()):
        total["spots_note"] = "spots summed over the calls (a tiled search's spots across tiles counted twice)"
    return total


def variants(folder: str, zones, lifts, cap: float, end_clearance: float, threads: Optional[int],
             with_spots: bool = True, long: float = LONG) -> Dict:
    calls = call_folders(folder)
    out = folder
    distance_opt = search_option(folder, "--group-distance")
    by = search_option(folder, "--group-by", "clearance")
    results, arrays = [], {}
    for call in calls:
        a = setup(call)
        distance = float(distance_opt) if distance_opt else max(20.0, 2 * a.res)
        r = variants_call(a, zones, lifts, cap, end_clearance, threads, with_spots, distance, by, long)
        name = r["call"]
        t = r.pop("_table").columns  # released with the call
        arrays[f"{name}_a1"] = t["a1"].astype(np.int32)
        arrays[f"{name}_a2"] = t["a2"].astype(np.int32)
        arrays[f"{name}_valid"] = r.pop("_valid")
        arrays[f"{name}_length"] = t["length"]
        arrays[f"{name}_clearance"] = t["zone_margins"].min(axis=1)  # today's (strict) clearance
        results.append(r)
    data = summed_calls(results)
    data["place"] = os.path.basename(os.path.normpath(folder))
    data["slope_threshold"] = float(search_option(folder, "--slope-threshold", 45))
    capture_json = os.path.join(folder, "capture.json")
    data["search_args"] = json.load(open(capture_json))["args"] if os.path.exists(capture_json) else None
    data["per_call"] = [{k: v for k, v in r.items() if not k.startswith("_")} for r in results] if len(results) > 1 else None
    with open(os.path.join(out, "variants.json"), "w") as f:
        json.dump(data, f, indent=1)
    np.savez_compressed(os.path.join(out, "variants.npz"), **arrays)
    return data


# ---------------------------------------------------------------------------------------------
# the margins of a line (diagnose and the profile chips)

def margins(z: np.ndarray, p, q, res: float, sag_table, surface: Optional[np.ndarray] = None):
    """The strict margins of the line p -> q (pixels, p the lower index): helpers.evaluate_line's
    pixels and helpers.max_safe_elevation (terrain, and the surface or None), steps, length."""
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


# ---------------------------------------------------------------------------------------------
# diagnose

def slope_degrees(z: np.ndarray, res: float) -> np.ndarray:
    """The slope of helpers.find_significant_slopes (float32, np.gradient)."""
    gy, gx = np.gradient(np.asarray(z, dtype=np.float32), res)
    return np.degrees(np.arctan(np.hypot(gx, gy)))


def to_pixel(grid: Dict, lat: float, lon: float):
    """The pixel (row, col) of a WGS84 point on a capture's grid, and its offset in metres."""
    from pyproj import Transformer
    x, y = Transformer.from_crs("EPSG:4326", grid["crs"], always_xy=True).transform(lon, lat)
    col, row = (x - grid["left"]) / grid["res"] - 0.5, (grid["top"] - y) / grid["res"] - 0.5
    return int(round(row)), int(round(col))


def disc(z: np.ndarray, centre, radius_px: float) -> np.ndarray:
    """The pixels within radius_px of centre, inside the grid."""
    r0, c0 = centre
    k = int(math.floor(radius_px))
    rr, cc = np.mgrid[r0 - k:r0 + k + 1, c0 - k:c0 + k + 1]
    rr, cc = rr.ravel(), cc.ravel()
    inside = ((rr - r0) ** 2 + (cc - c0) ** 2 <= radius_px ** 2) & (rr >= 0) & (cc >= 0) & \
             (rr < z.shape[0]) & (cc < z.shape[1])
    return np.column_stack([rr[inside], cc[inside]])


def buckets_of(a: SimpleNamespace, lo, hi, zones: Sequence[float], cap: float) -> np.ndarray:
    """The smallest strict terrain margin per ladder bucket of the line lo -> hi (helpers.evaluate_line
    with the ladder: one column per zone, the core last; NaN: the line fails anywhere)."""
    result = sh.evaluate_line(lo, hi, a.z, a.res, sag_table=a.sag_table, zone_cap=cap, zones=zones)
    return np.full(len(zones), np.nan) if result is None else result[8]


def needed_lift(buckets: np.ndarray, j: int, delta: float) -> float:
    """The lift that ladder zone j needs at least (valid for any larger lift; the rule is strict)."""
    if np.isnan(buckets).any():
        return math.inf
    zone, core = buckets[:j].min() if j else math.inf, buckets[j:].min()
    return max(0.0, -core, -zone - delta)


def line_detail(a: SimpleNamespace, lo, hi, zones: Sequence[float], cap: float, delta: float) -> Dict:
    """One line between two pixels (lo the lower index: row-major) by today's rule and the ladder:
    length, clearance, accepted, the height difference, the first failing step from each end
    (distance and deficit) and the staircase (the lift each ladder zone needs at least)."""
    lo, hi = [int(v) for v in lo], [int(v) for v in hi]
    m = margins(a.z, lo, hi, a.res, a.sag_table)
    terrain, steps, length = m[0], m[2], m[3]
    clearance = float(np.min(terrain))
    detail = {"a1": lo, "a2": hi, "length": length, "clearance": clearance, "accepted": bool(clearance > 0),
              "dh": float(a.z[tuple(hi)] - a.z[tuple(lo)])}
    if not clearance > 0:
        fails = np.flatnonzero(~(terrain > 0))
        first, last = int(fails[0]) + 1, int(fails[-1]) + 1
        detail["first_fail"] = {
            "from_a1": {"step": first, "m": first * length / steps, "deficit": float(terrain[first - 1])},
            "from_a2": {"step": steps - last, "m": (steps - last) * length / steps,
                        "deficit": float(terrain[last - 1])}}
    b = buckets_of(a, lo, hi, zones, cap)
    detail["staircase"] = [{"zone": float(x), "lift": needed_lift(b, j, delta)} for j, x in enumerate(zones)]
    return detail


def diagnose_line(a: SimpleNamespace, slope: np.ndarray, anchors: set, line: Dict, radius: float,
                  zones: Sequence[float], cap: float, end_clearance: float, thresholds: Sequence[float]) -> Dict:
    """One known line on a call's grid (see the module docstring)."""
    delta = a.fall - end_clearance
    ends = [to_pixel(a.grid, *line["a"]), to_pixel(a.grid, *line["b"])]
    radius_px = radius / a.res
    result = {"name": line.get("name"), "a": line["a"], "b": line["b"], "pixels": [list(e) for e in ends]}
    near = []
    for e in ends:
        pixels = disc(a.z, e, radius_px)
        d = np.hypot(pixels[:, 0] - e[0], pixels[:, 1] - e[1]) * a.res
        entry = {"slope": float(slope[e]) if 0 <= e[0] < a.z.shape[0] and 0 <= e[1] < a.z.shape[1] else None}
        for thr in thresholds:
            steep = slope[pixels[:, 0], pixels[:, 1]] >= thr
            entry[f"{thr:g}"] = float(d[steep].min()) if steep.any() else None
        entry["anchor_within"] = float(min((dd for p, dd in zip(map(tuple, pixels), d) if p in anchors),
                                           default=math.nan))
        near.append((pixels, entry))
    result["ends"] = [entry for _, entry in near]
    best, stairs = None, [None] * len(zones)
    for p in near[0][0]:
        for q in near[1][0]:
            lo, hi = (p, q) if tuple(p) <= tuple(q) else (q, p)  # row-major: the anchors' order
            m = margins(a.z, lo, hi, a.res, a.sag_table)
            if m is None:
                continue
            clearance = float(np.min(m[0]))
            b = buckets_of(a, lo, hi, zones, cap)
            if best is None or clearance > best[0] or (math.isnan(best[0]) and not math.isnan(clearance)):
                best = (clearance, lo, hi, m)
            for j in range(len(zones)):
                need = needed_lift(b, j, delta)
                if stairs[j] is None or need < stairs[j][0]:
                    stairs[j] = (need, [int(v) for v in lo], [int(v) for v in hi])
    if best is None:
        result["error"] = "no pair of pixels with a step between them"
        return result
    clearance, lo, hi, m = best
    result["best"] = {k: v for k, v in line_detail(a, lo, hi, zones, cap, delta).items() if k != "staircase"}
    result["staircase"] = [{"zone": float(x), "lift": s[0] if s else None, "a1": s[1] if s else None,
                            "a2": s[2] if s else None} for x, s in zip(zones, stairs)]
    return result


def diagnose(folder: str, lines_file: str, radius: float, zones, cap: float, end_clearance: float,
             thresholds: Sequence[float]) -> Dict:
    call = call_folders(folder)[0]
    a = setup(call)
    if a.grid is None:
        raise ValueError(f"{call} has no grid.json: capture the place with this tool")
    zones = sorted(set([0.0] + [float(x) for x in zones]))
    with open(lines_file, encoding="utf-8") as f:
        lines = json.load(f)
    lines = [ln if isinstance(ln, dict) else {"name": f"line {k + 1}", "a": ln[0], "b": ln[1]}
             for k, ln in enumerate(lines)]
    slope = slope_degrees(a.z, a.res)
    anchors = set(map(tuple, a.anchors.tolist()))
    data = {"place": os.path.basename(os.path.normpath(folder)), "call": call, "radius": radius, "zones": zones,
            "cap": cap, "end_clearance": end_clearance, "delta": a.fall - end_clearance,
            "lines": [diagnose_line(a, slope, anchors, ln, radius, zones, cap, end_clearance, thresholds)
                      for ln in lines]}
    with open(os.path.join(folder, "diagnose.json"), "w") as f:
        json.dump(data, f, indent=1, default=lambda v: None)
    return data


# ---------------------------------------------------------------------------------------------
# report

def fmt(v, digits=2) -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "-"
    if isinstance(v, float) and math.isinf(v):
        return "inf"
    return f"{v:.{digits}f}" if isinstance(v, float) else str(v)


def seconds_rows(v: Dict) -> List[str]:
    rows = ["| Stage | baseline wall | baseline CPU | superset wall | superset CPU | wall ratio | CPU ratio | "
            "production wall | production CPU |", "| --- | " + " | ".join(["---:"] * 8) + " |"]
    totals = {run: [0.0, 0.0] for run in ("baseline", "superset", "production")}
    for stage in STAGES:
        cells = []
        for run in ("baseline", "superset"):
            w, c = v["seconds"][run].get(stage, (0.0, 0.0))
            totals[run][0] += w
            totals[run][1] += c
            cells += [fmt(w), fmt(c)]
        bw, bc = v["seconds"]["baseline"].get(stage, (0.0, 0.0))
        sw, sc = v["seconds"]["superset"].get(stage, (0.0, 0.0))
        pw, pc = v["seconds"]["production"].get(stage, (0.0, 0.0))
        totals["production"][0] += pw
        totals["production"][1] += pc
        rows.append(f"| {stage} | " + " | ".join(cells) + f" | {fmt(sw / bw if bw else None)} | "
                    f"{fmt(sc / bc if bc else None)} | {fmt(pw)} | {fmt(pc)} |")
    (bw, bc), (sw, sc), (pw, pc) = totals["baseline"], totals["superset"], totals["production"]
    rows.append(f"| total | {fmt(bw)} | {fmt(bc)} | {fmt(sw)} | {fmt(sc)} | {fmt(sw / bw if bw else None)} | "
                f"{fmt(sc / bc if bc else None)} | {fmt(pw)} | {fmt(pc)} |")
    return rows


def place_markdown(v: Dict, d: Optional[Dict]) -> List[str]:
    zones, lifts = v["zones"], v["lifts"]
    md = [f"## {v['place']} (slope threshold {v['slope_threshold']:g} deg)", "",
          f"{v['model']}, res {v['res']:g} m, lines {v['min_length']:g}-{v['max_length']:g} m, nmpt {v['nmpt_mode']}, "
          f"anchors {v['anchors']}; fall {v['fall']:g} m, end clearance {v['end_clearance']:g} m (delta "
          f"{v['delta']:g} m), cap {v['cap']:g} of the length; {v['threads']} threads.", "",
          "Valid lines (new against zone 0, lift 0)" + (", spots" if "spots" in next(iter(v["table"].values()))
                                                        else "") + ":", "",
          "| zone \\ lift | " + " | ".join(f"{h:g} m" for h in lifts) + " |",
          "| ---: | " + " | ".join(["---:"] * len(lifts)) + " |"]
    for x in zones:
        cells = []
        for h in lifts:
            e = v["table"][f"{x:g},{h:g}"]
            cell = f"{e['lines']} (+{e['new']})"
            if "spots" in e:
                cell += f", {e['spots']} spots"
            if "long" in e:
                cell += f"; {e['long']} of {v['long']:g} m+ (+{e['long_new']})"
            cells.append(cell)
        md.append(f"| {x:g} m | " + " | ".join(cells) + " |")
    if v.get("long"):
        first = first_appearance(v)
        md += ["", f"Lines of {v['long']:g} m or more first appear at (zone, lift): "
               + (", ".join(f"({x:g} m, {h:g} m)" for x, h in first) if first else "none up to the ladder's end")
               + " (the smallest entries with one: no smaller zone at that lift and no smaller lift at that zone)."]
    md += ["", "Funnel:", "", "| run | anchors | open | open share | todo | candidates | checked | found | valid |",
           "| --- | " + " | ".join(["---:"] * 8) + " |"]
    for run in ("baseline", "superset"):
        f = v["funnel"][run]
        md.append(f"| {run} | {f['anchors']} | {f['open']} | {100 * f['open'] / f['anchors'] if f['anchors'] else 0:.1f}% "
                  f"| {f['todo']} | {f['candidates']} | {f['checked']} | {f['found']} | {f['valid']} |")
    md += ["", f"Seconds (superset: zone {zones[-1]:g} m, lift {lifts[-1]:g} m; indicative when measured in a "
               "shared slot):", "", *seconds_rows(v), "",
           "Checks: the superset's zone 0 / lift 0 equals the baseline, find_valid_lines at 0 / 0 (lines, order and "
           "clearances): " + ("passed" if all(v["checks"].values()) else "FAILED"), ""]
    if d:
        md += ["### Diagnosed lines", ""]
        for ln in d["lines"]:
            md.append(f"**{ln['name']}**: pixels {ln['pixels']}")
            for side, e in zip(("a", "b"), ln["ends"]):
                md.append(f"- end {side}: slope {fmt(e['slope'], 1)} deg; nearest pixel of "
                          + ", ".join(f"{k} deg {fmt(e[k], 1)} m" for k in e if k not in ("slope", "anchor_within"))
                          + f"; nearest anchor of the capture {fmt(e['anchor_within'], 1)} m")
            b = ln.get("best")
            if b:
                md.append(f"- best pair within {d['radius']:g} m: {b['length']:.1f} m, clearance "
                          f"{b['clearance']:.2f} m, today {'accepted' if b['accepted'] else 'rejected'}")
                if "first_fail" in b:
                    ff = b["first_fail"]
                    md.append(f"- first failing step: from a1 at {ff['from_a1']['m']:.1f} m "
                              f"(deficit {ff['from_a1']['deficit']:.2f} m), from a2 at {ff['from_a2']['m']:.1f} m "
                              f"(deficit {ff['from_a2']['deficit']:.2f} m)")
                md.append("- lift needed: " + ", ".join(f"zone {s['zone']:g} m: {fmt(s['lift'])} m"
                                                        for s in ln["staircase"]))
            md.append("")
    return md


def first_appearance(v: Dict) -> List[tuple]:
    """The (zone, lift) entries with long lines that no entry of a smaller zone and lift dominates."""
    have = [(e["zone"], e["lift"]) for e in v["table"].values() if e.get("long")]
    return sorted((x, h) for x, h in have if not any((y, g) != (x, h) and y <= x and g <= h for y, g in have))


def examples(folder: str, v: Dict, count: int = EXAMPLES) -> List[Dict]:
    """A few long lines new against zone 0, lift 0 (length >= v["long"]): those valid at the
    smallest ladder entry first (zone, then lift), then by today's clearance, each at least the
    group distance (20 m) from the anchors of those taken before (distinct spots), with
    line_detail."""
    if not v.get("long"):
        return []
    call = call_folders(folder)[0]
    name = os.path.basename(os.path.normpath(call))
    arrays = np.load(os.path.join(folder, "variants.npz"))
    a1, a2, valid = arrays[f"{name}_a1"], arrays[f"{name}_a2"], arrays[f"{name}_valid"]
    length, clearance = arrays[f"{name}_length"], arrays[f"{name}_clearance"]
    rows = np.flatnonzero((length >= v["long"]) & valid[:, -1, -1] & ~valid[:, 0, 0])
    if not len(rows):
        return []
    flat = valid[rows].reshape(len(rows), -1)  # zone-major, then lift
    first = np.argmax(flat, axis=1)
    rows = rows[np.lexsort((-clearance[rows], first))]
    a = setup(call)
    spacing = max(20.0, 2 * a.res) / a.res
    taken, out = [], []
    for r in rows.tolist():
        p, q = a1[r].astype(float), a2[r].astype(float)
        if any(min(max(np.hypot(*(p - u)), np.hypot(*(q - w))), max(np.hypot(*(p - w)), np.hypot(*(q - u))))
               <= spacing for u, w in taken):
            continue
        taken.append((p, q))
        j, k = divmod(int(np.argmax(valid[r].reshape(-1))), valid.shape[2])
        detail = line_detail(a, a1[r], a2[r], v["zones"], v["cap"], v["delta"])
        detail["first_valid"] = [v["zones"][j], v["lifts"][k]]
        detail["wgs84"] = pixels_wgs84(a.grid, [a1[r], a2[r]]) if a.grid else None
        out.append(detail)
        if len(out) >= count:
            break
    return out


def pixels_wgs84(grid: Dict, pixels) -> List[List[float]]:
    """[lat, lon] of pixel centres of a capture's grid."""
    from pyproj import Transformer
    t = Transformer.from_crs(grid["crs"], "EPSG:4326", always_xy=True)
    out = []
    for r, c in pixels:
        lon, lat = t.transform(grid["left"] + (int(c) + 0.5) * grid["res"], grid["top"] - (int(r) + 0.5) * grid["res"])
        out.append([round(lat, 7), round(lon, 7)])
    return out


def examples_markdown(v: Dict, chosen: List[Dict]) -> List[str]:
    if not v.get("long"):
        return []
    md = [f"### Lines of {v['long']:g} m or more new against zone 0, lift 0 (a few, distinct spots)", ""]
    if not chosen:
        return md + ["None up to the ladder's end.", ""]
    md += ["| # | ends (lat, lon) | length | today's clearance | first valid (zone, lift) | first strict failure "
           "from a1 / a2 (m, deficit) | lift needed at zone " + " / ".join(f"{x:g}" for x in v["zones"]) + " m |",
           "| ---: | --- | ---: | ---: | --- | --- | --- |"]
    for n, e in enumerate(chosen, 1):
        ff = e.get("first_fail")
        fail = (f"{ff['from_a1']['m']:.1f} m, {ff['from_a1']['deficit']:.2f} / {ff['from_a2']['m']:.1f} m, "
                f"{ff['from_a2']['deficit']:.2f}") if ff else "-"
        ends = " - ".join(f"{p[0]:.6f}, {p[1]:.6f}" for p in e["wgs84"]) if e.get("wgs84") else f"{e['a1']} - {e['a2']}"
        md.append(f"| {n} | {ends} | {e['length']:.1f} m | {e['clearance']:.2f} m | ({e['first_valid'][0]:g} m, "
                  f"{e['first_valid'][1]:g} m) | {fail} | " + " / ".join(fmt(s["lift"]) for s in e["staircase"]) + " |")
    return md + [""]


def profile_chip(a: SimpleNamespace, lo, hi, delta: float, title: str, path: str, zone: float = 0.0,
                 cap: float = CAP):
    """The terrain along a line with today's limit and the limit moved up by delta, the zone of
    `zone` metres shaded."""
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


def pictures(folder: str, v: Dict, d: Optional[Dict], out: str, chosen: Sequence[Dict] = ()) -> List[str]:
    """The map of the baseline and a few variants over a hillshade, and the profile chips."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.collections import LineCollection
    from matplotlib.colors import LightSource

    made = []
    os.makedirs(out, exist_ok=True)
    call = call_folders(folder)[0]
    inputs, params, _ = plf.load_call(call)
    z = inputs["elevation"].astype(np.float64)
    arrays = np.load(os.path.join(folder, "variants.npz"))
    name = os.path.basename(os.path.normpath(call))
    a1, a2, valid = arrays[f"{name}_a1"], arrays[f"{name}_a2"], arrays[f"{name}_valid"]
    zones, lifts = v["zones"], v["lifts"]
    shade = LightSource(315, 45).hillshade(np.nan_to_num(z, nan=np.nanmin(z)), vert_exag=1, dx=v["res"], dy=v["res"])
    picks = [(min(1, len(zones) - 1), 0), (len(zones) // 2, len(lifts) // 2), (len(zones) - 1, len(lifts) - 1)]
    fig, axes = plt.subplots(1, 3, figsize=(18, 6.4))
    rng = np.random.default_rng(0)

    def segments(mask):
        rows = np.flatnonzero(mask)
        if len(rows) > MAP_LINES:
            rows = np.sort(rng.choice(rows, MAP_LINES, replace=False))
        return np.stack([a1[rows][:, ::-1], a2[rows][:, ::-1]], axis=1), len(np.flatnonzero(mask))

    base = valid[:, 0, 0]
    long = v.get("long") or 0.0
    longer = arrays[f"{name}_length"] >= long if long and f"{name}_length" in arrays.files else \
        np.ones(len(base), dtype=bool)
    rows, cols = np.nonzero(np.isfinite(z))  # the grid's data only (a circle's corners are NaN)
    box = (cols.min() - 0.5, cols.max() + 0.5, rows.max() + 0.5, rows.min() - 0.5) if len(rows) else None
    if box and len(a1):  # around the superset's lines, with a margin
        ends = np.vstack([a1, a2])
        pad = 0.25 * max(np.ptp(ends[:, 0]), np.ptp(ends[:, 1]), 200)
        box = (max(box[0], ends[:, 1].min() - pad), min(box[1], ends[:, 1].max() + pad),
               min(box[2], ends[:, 0].max() + pad), max(box[3], ends[:, 0].min() - pad))
    for ax, (j, k) in zip(axes, picks):
        ax.imshow(shade, cmap="gray", interpolation="nearest")
        new = valid[:, j, k] & ~base & longer
        segs, n_new = segments(new)  # the new lines below, the baseline's above them
        ax.add_collection(LineCollection(segs, colors="#e53e3e", linewidths=0.3, alpha=0.35))
        segs, n_base = segments(base)
        ax.add_collection(LineCollection(segs, colors="#1e40af", linewidths=0.6, alpha=0.9))
        if box:
            ax.set_xlim(box[0], box[1])
            ax.set_ylim(box[2], box[3])
        ax.set_title(f"zone {zones[j]:g} m, lift {lifts[k]:g} m: {n_base} lines (blue) + {n_new} new"
                     + (f" of {long:g} m+" if long else "") + " (red)", fontsize=9)
        ax.set_xticks([])
        ax.set_yticks([])
    fig.suptitle(f"{v['place']}: baseline and new lines (at most {MAP_LINES} drawn per colour)")
    for n, e in enumerate(chosen, 1):  # the detailed long lines, numbered
        for ax in axes:
            ax.plot([e["a1"][1], e["a2"][1]], [e["a1"][0], e["a2"][0]], color="#facc15", lw=1.2)
            ax.annotate(str(n), (e["a1"][1], e["a1"][0]), color="#facc15", fontsize=8, fontweight="bold")
    fig.tight_layout()
    path = os.path.join(out, f"{v['place']}-map.png")
    fig.savefig(path, dpi=110)
    plt.close(fig)
    made.append(path)
    a = setup(call) if d or chosen else None
    if d:
        for n, ln in enumerate(d["lines"]):
            b = ln.get("best")
            if not b:
                continue
            path = os.path.join(out, f"{v['place']}-line-{n + 1}.png")
            profile_chip(a, b["a1"], b["a2"], d["delta"], f"{ln['name']}: {b['length']:.0f} m, clearance "
                         f"{b['clearance']:.2f} m; lift needed " + ", ".join(f"{s['zone']:g} m: {fmt(s['lift'], 1)}"
                                                                         for s in ln["staircase"]), path)
            made.append(path)
    for n, e in enumerate(chosen, 1):
        path = os.path.join(out, f"{v['place']}-long-{n}.png")
        profile_chip(a, e["a1"], e["a2"], v["delta"], f"#{n}: {e['length']:.0f} m, clearance {e['clearance']:.2f} m, "
                     f"first valid at zone {e['first_valid'][0]:g} m / lift {e['first_valid'][1]:g} m (shaded); "
                     "lift needed " + ", ".join(f"{s['zone']:g} m: {fmt(s['lift'], 1)}" for s in e["staircase"]),
                     path, zone=e["first_valid"][0], cap=v["cap"])
        made.append(path)
    return made


def report(out: str, folders: List[str], with_pictures: bool = True, count: int = EXAMPLES) -> str:
    os.makedirs(out, exist_ok=True)
    places, md = [], ["# End-zone study", "",
                      "The rule: a pixel passes when limit - terrain > -lift - delta * [in the zone]; delta = fall - "
                      "end clearance; the zone: steps nearer to an anchor than min(zone, cap * length). Seconds "
                      "measured in a shared slot of tools/test_lock.py are indicative only.", ""]
    for folder in folders:
        with open(os.path.join(folder, "variants.json")) as f:
            v = json.load(f)
        dpath = os.path.join(folder, "diagnose.json")
        d = json.load(open(dpath)) if os.path.exists(dpath) else None
        chosen = examples(folder, v, count)
        md += place_markdown(v, d) + examples_markdown(v, chosen)
        made = []
        if with_pictures:
            made = pictures(folder, v, d, os.path.join(out, "pictures"), chosen)
            md += [f"![{os.path.basename(p)}](pictures/{os.path.basename(p)})" for p in made] + [""]
        places.append({"variants": v, "diagnose": d, "examples": chosen,
                       "pictures": [os.path.relpath(p, out) for p in made]})
    with open(os.path.join(out, "study.json"), "w") as f:
        json.dump({"places": places}, f, indent=1)
    text = "\n".join(md)
    with open(os.path.join(out, "study.md"), "w", encoding="utf-8") as f:
        f.write(text)
    return text


# ---------------------------------------------------------------------------------------------

def numbers(text: str) -> List[float]:
    return [float(v) for v in text.split(",") if v.strip()]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("capture", help="a place's search with its line search captured")
    p.add_argument("place")
    p.add_argument("--out", required=True, help="the study folder (<out>/<place>/)")
    p.add_argument("--cache", help="the cache to link (default: the data folder's)")
    p.add_argument("--no-cache-link", action="store_true", help="a fresh cache instead of a link")
    p = sub.add_parser("capture-child", help="(internal) the child process of capture")
    p.add_argument("--out", required=True)
    for name, text in (("variants", "the variants of a capture"), ("diagnose", "known lines on a capture")):
        p = sub.add_parser(name, help=text)
        p.add_argument("folder", help="a place folder of capture (or a call folder)")
        p.add_argument("--zones", type=numbers, default=list(ZONES), help="the ladder of zones, metres")
        p.add_argument("--cap", type=float, default=CAP, help="the zone's largest share of a line's length")
        p.add_argument("--end-clearance", type=float, default=0.0, help="metres kept free below the webbing in a zone")
        if name == "variants":
            p.add_argument("--lifts", type=numbers, default=list(LIFTS), help="the lifts, metres")
            p.add_argument("--threads", type=int, help="numba threads (default: numba's)")
            p.add_argument("--no-spots", action="store_true", help="without mapping.group_lines")
            p.add_argument("--long", type=float, default=LONG, help="long lines counted apart from this length, m "
                                                                   "(0: none)")
        else:
            p.add_argument("--lines", required=True, help="JSON: [{name, a: [lat, lon], b: [lat, lon]}, ...]")
            p.add_argument("--radius", type=float, default=RADIUS, help="metres around each end")
            p.add_argument("--thresholds", type=numbers, default=list(THRESHOLDS), help="slope thresholds, degrees")
    p = sub.add_parser("report", help="study.json, study.md and pictures of the places")
    p.add_argument("out")
    p.add_argument("folders", nargs="+")
    p.add_argument("--no-pictures", action="store_true")
    p.add_argument("--examples", type=int, default=EXAMPLES, help="long new lines detailed per place")
    argv = list(sys.argv[1:] if argv is None else argv)
    search_args = argv[argv.index("--") + 1:] if "--" in argv else []  # findaline.py's options after "--"
    argv = argv[:argv.index("--")] if "--" in argv else argv
    args = parser.parse_args(argv)
    if args.command in ("capture", "capture-child"):
        if args.command == "capture-child":
            return capture_child(args.out, search_args)
        import cache
        cache_dir = None if args.no_cache_link else (args.cache or os.path.join(cache.data_dir(), "cache"))
        return capture(args.place, args.out, search_args, cache_dir)
    if args.command == "variants":
        data = variants(args.folder, args.zones, args.lifts, args.cap, args.end_clearance, args.threads,
                        not args.no_spots, args.long)
        for key, e in data["table"].items():
            print(f"zone,lift {key}: {e['lines']} lines (+{e['new']})" + (f", {e['spots']} spots" if "spots" in e
                                                                           else "")
                  + (f", {e['long']} of {args.long:g} m+ (+{e['long_new']})" if "long" in e else ""))
        return 0
    if args.command == "diagnose":
        data = diagnose(args.folder, args.lines, args.radius, args.zones, args.cap, args.end_clearance,
                        args.thresholds)
        for ln in data["lines"]:
            b = ln.get("best")
            print(f"{ln['name']}: " + (f"clearance {b['clearance']:.2f} m, "
                                       f"{'accepted' if b['accepted'] else 'rejected'}" if b else ln.get("error", "")))
        return 0
    report(args.out, args.folders, not args.no_pictures, args.examples)
    print(os.path.join(args.out, "study.md"))
    return 0


if __name__ == "__main__":
    from progress import utf8_output
    utf8_output()  # redirected output in UTF-8, not the Windows code page
    sys.exit(main())
