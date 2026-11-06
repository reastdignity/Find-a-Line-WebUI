"""
Run by hand: how many lines a "no-fall zone" at the ends of a line and A-frames lifting its
anchors would add, and what they cost (the end-zone study, 2026-11-06).

The rule measured (tools/end_zone_kernels.py): a pixel of a line passes when its strict margin
s = limit - terrain (helpers.max_safe_elevation; the surface model likewise) satisfies

    s > -lift - delta * [the pixel lies in the end zone]

lift: an A-frame of that height at both ends; delta = fall - end_clearance (fall:
helpers.fall_allowance, the 6 m of the formula or the sag model's fall zone; end_clearance
>= 0 and at most fall); the zone: the steps closer to the nearer anchor than min(end_zone,
cap * length) (end_zone_kernels.zone_steps). The limit itself is never changed: at zone 0 and
lift 0 every operation is production's.

capture runs a search in a child process with a data folder of its own whose cache/ links to
the real cache (a junction on Windows, removed as a link afterwards, never followed), with
linesearch.find_valid_lines wrapped as tools/perf_line_funnel.py wraps it (each call's inputs
and parameters in <out>/<place>/capture/call-<k>/, with grid.json: the grid's georeference)
and its options in <out>/<place>/capture.json. One capture per place and slope threshold
(--slope-threshold is an option of the search):

    uv run tools/end_zone_study.py capture zabi-kon-45 --out <scratch>/study -- \
        --lat 50.1559508 --lon 19.7562722 --slope-threshold 45

variants runs the variant kernels on a capture: once at the superset (the largest zone and
lift) and once at zone 0 and lift 0 (the baseline, through the same harness, so the ratio of
their seconds is fair), each timed per stage (free directions, anchor pairs, checking lines:
wall and CPU seconds) after a warm-up of numba, with the funnel of each. In its one evaluation
pass every line keeps the smallest strict margin per bucket of the ladder of --zones (the steps
first in the zone of each ladder value, and the rest), so the valid lines at every (zone, lift)
of the grid come from the superset's lines without another search (valid iff the buckets
beyond the zone are above -lift and those within it above -lift - delta). It stops unless the
(0, 0) entry, and the baseline run, equal production's find_valid_lines on the capture (the
same lines in the same order) and the baseline's funnel equals production's. The spots of each
entry by mapping.group_lines (group distance and rule from the capture's options, defaults
otherwise; over the lines of find_valid_lines, so not always the run's spot count). Writes
<place>/variants.json and variants.npz (the superset's lines and where each is valid).

    uv run tools/end_zone_study.py variants <scratch>/study/zabi-kon-45 [--zones 0,5,10,20] \
        [--lifts 0,1,2] [--cap 0.25] [--end-clearance 0] [--threads N]

diagnose looks at known real lines (a JSON list of {"name", "a": [lat, lon], "b": [lat, lon]})
on a capture's grid: the nearest pixels of slope 45/40/35/30 degrees or more within --radius
metres of each end, the best pair of pixels within that radius of the two ends by today's rule
(the largest clearance), whether today's rule accepts it, else its first failing step from
each end (distance and deficit), and the staircase: the lift each ladder zone needs at least
(the best pair for each). Brute force with helpers.max_safe_elevation. Writes
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

import end_zone_kernels as K  # noqa: E402
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


class StudyError(RuntimeError):
    """The variant kernels at zone 0, lift 0 do not give production's lines."""


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
    print(f"{place}: exit {result.returncode}, {len(calls)} call(s) captured in {folder}")
    return 0 if result.returncode == 0 and calls else 1


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
# the variant kernels' harness

def no_rings(z, anchors, *rest):
    """A stand-in for perf_line_funnel.rebuild's rings: the harness computes its own."""
    return np.zeros((len(anchors), ls.SECTORS), dtype=np.uint8)


def setup(folder: str) -> SimpleNamespace:
    """A captured call's inputs and the kernels' arguments (perf_line_funnel.rebuild: the set-up
    of linesearch.find_valid_lines), with what the evaluation needs besides."""
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


def subset(a: SimpleNamespace, n: int) -> SimpleNamespace:
    """The call with its first n anchors only (the warm-up: the same argument types)."""
    b = SimpleNamespace(**vars(a))
    b.anchors = np.ascontiguousarray(a.anchors[:n])
    b.elev, b.down, b.strong = a.elev[:n], a.down[:n], a.strong[:n]
    b.first = None if a.first is None else np.asarray(a.first)[:n]
    return b


def limits_of(a: SimpleNamespace) -> Optional[sh.LineLimits]:
    """A fresh helpers.LineLimits of the call (its left_out counted anew)."""
    q = a.params["limits"]
    return None if q is None else sh.LineLimits(**{k: v for k, v in q.items() if k != "left_out"})


def pair_chunk_v(args: tuple, todo: np.ndarray, tail: tuple, rule: tuple, buffer: Optional[int] = None):
    """linesearch.pair_chunk with end_zone_kernels.pairs_v (rule: lift, delta, end_zone, cap)."""
    n = len(todo)
    index = np.int32 if len(args[1]) <= np.iinfo(np.int32).max else np.int64
    keep = buffer or max(1, min(ls.PAIR_BUFFER, ls.PAIR_BUFFER_BYTES // (2 * np.dtype(index).itemsize * max(1, n))))
    buf = np.empty((n, keep, 2), dtype=index)
    counts = np.zeros((n, 3), dtype=np.int64)
    K.pairs_v(*args, todo, *tail, *rule, None, np.zeros((0, 2), dtype=np.int64), buf, counts)
    found = counts[:, 2]
    offsets = (np.cumsum(found) - found).astype(np.int64)
    out = np.empty((int(found.sum()), 2), dtype=np.int64)
    if len(out):
        K._copy_buffered(buf, found, offsets, out)
    more = np.flatnonzero(found > keep)
    if len(more):
        K.pairs_v(*args, np.ascontiguousarray(todo[more]), *tail, *rule, np.ascontiguousarray(offsets[more]), out,
                  np.zeros((0, 0, 2), dtype=index), np.zeros((len(more), 3), dtype=np.int64))
    return counts, out


def directions_v(a: SimpleNamespace, offsets: np.ndarray):
    """linesearch.free_directions with end_zone_kernels.free_rings_v."""
    kmax, masks = ls.largest_need(a.min_length, a.max_length, a.res), ls.sector_masks()
    need_min = ls.smallest_need(a.min_length, a.res)
    useful, rows = [], []
    for start in range(0, len(a.anchors), ls.RING_CHUNK):
        rings = K.free_rings_v(a.z, a.anchors[start:start + ls.RING_CHUNK], a.res, a.gain, a.cap, offsets, kmax,
                               masks)
        keep = np.flatnonzero(rings.max(axis=1) >= need_min)
        useful.append(keep + start)
        rows.append(rings[keep])
    useful = np.concatenate(useful).astype(np.int64) if useful else np.zeros(0, dtype=np.int64)
    rows = np.concatenate(rows) if rows else np.zeros((0, ls.SECTORS), dtype=np.uint8)
    slot = np.full(len(a.anchors), -1, dtype=np.int32)
    slot[useful] = np.arange(len(useful), dtype=np.int32)
    return useful, rows, slot


def check_rule(a: SimpleNamespace, lift: float, end_zone: float, end_clearance: float, cap: float) -> float:
    """delta of the rule; refuses what the study's monotony needs (lift, end_zone >= 0, delta >= 0)."""
    delta = a.fall - end_clearance
    if lift < 0 or end_zone < 0 or not 0 <= cap <= 0.5 or end_clearance < 0 or delta < 0:
        raise ValueError(f"lift {lift}, end zone {end_zone}, cap {cap} and end clearance {end_clearance} "
                         f"(at most the fall, {a.fall:g} m) must not be negative")
    return delta


class Stages:
    """Wall and CPU seconds (time.process_time: every thread) of the stages of a run."""

    def __init__(self):
        self.seconds = {}

    @contextlib.contextmanager
    def __call__(self, stage: str):
        wall, cpu = time.perf_counter(), time.process_time()
        yield
        w, c = self.seconds.get(stage, (0.0, 0.0))
        self.seconds[stage] = (w + time.perf_counter() - wall, c + time.process_time() - cpu)


def run_rule(a: SimpleNamespace, lift: float = 0.0, end_zone: float = 0.0, cap: float = CAP,
             end_clearance: float = 0.0, zones: Sequence[float] = ZONES) -> SimpleNamespace:
    """The line search of a call with the variant kernels at one rule: the funnel, the seconds
    per stage, and the lines valid under the rule (with limits and nmpt_mode as the call's) with
    their bucket minima of the ladder zones (in the order of the pairs found)."""
    delta = check_rule(a, lift, end_zone, end_clearance, cap)
    zones = np.asarray(sorted(set(float(x) for x in zones)), dtype=np.float64)
    clock = Stages()
    with clock("free directions"):
        kmax = ls.largest_need(a.min_length, a.max_length, a.res)
        offsets = K.ring_offsets(a.offset, kmax, a.res, lift, delta, end_zone)
        useful, rows, slot = directions_v(a, offsets)
    with clock("anchor pairs"):
        todo_all, head, tail = ls.pair_arguments(a.z, a.anchors, a.elev, useful, rows, slot, a.first, a.res,
                                                 a.min_length, a.max_length, a.max_dh_ratio, a.max_dh, a.down,
                                                 a.cos_limit, a.strong, a.use_sag, a.log_spans, a.ratios,
                                                 a.table, a.fall_zone)
        rule = (float(lift), float(delta), float(end_zone), float(cap))
        pairs, candidates, checked, found = [], 0, 0, 0
        for todo in np.array_split(todo_all, min(ls.CHUNKS, max(1, len(todo_all)))):
            counts, out = pair_chunk_v(head, todo, tail, rule)
            pairs.append(out)
            found += len(out)
            candidates += int(counts[:, 0].sum())
            checked += int(counts[:, 1].sum())
    with clock("checking lines"):
        limits = limits_of(a)
        kept = [evaluate_part(a, part, rule, zones, limits)
                for part in ls.evaluation_parts(pairs, max(ls.EVAL_PART, -(-found // ls.CHUNKS)))]
        lines = {k: np.concatenate([p[k] for p in kept]) for k in kept[0]} if kept else empty_lines(len(zones))
    funnel = {"anchors": len(a.anchors), "open": len(useful), "todo": len(todo_all), "candidates": candidates,
              "checked": checked, "found": found, "valid": len(lines["pairs"])}
    return SimpleNamespace(funnel=funnel, seconds=clock.seconds, lines=lines, zones=zones, lift=lift,
                           end_zone=end_zone, delta=delta, cap=cap)


def empty_lines(nz: int) -> Dict[str, np.ndarray]:
    return {"pairs": np.zeros((0, 2), dtype=np.int64), "length": np.zeros(0), "clearance": np.zeros(0),
            "clearance_nmpt": np.zeros(0), "height_max": np.zeros(0), "terrain": np.zeros((0, nz + 1)),
            "surface": np.zeros((0, nz + 1))}


def evaluate_part(a: SimpleNamespace, found: np.ndarray, rule: tuple, zones: np.ndarray,
                  limits: Optional[sh.LineLimits]) -> Dict[str, np.ndarray]:
    """linesearch.evaluate_lines of a part with end_zone_kernels.evaluate_v: the lines valid under
    the rule that reach the limits, with their bucket minima."""
    found = np.asarray(found, dtype=np.int64).reshape(-1, 2)
    nz = len(zones)
    out, terrain, surface = np.zeros((len(found), 11)), np.zeros((len(found), nz + 1)), np.zeros((len(found), nz + 1))
    if len(found):
        t = a.sag_table
        if t is None:
            log_spans = span_index = ratios = ratio_index = fractions = np.zeros(2)
            sag, fall_zone = np.zeros((2, 2, 2)), 0.0
        else:
            log_spans = np.log(t.spans)
            span_index = np.arange(len(t.spans)).astype(np.float64)
            ratios = t.RATIOS.astype(np.float64)
            ratio_index = np.arange(len(ratios)).astype(np.float64)
            sag, fractions = np.ascontiguousarray(t.sag), t.fractions.astype(np.float64)
            fall_zone = float(t.rig.fall_zone)
        z = np.asarray(a.z)
        s = np.asarray(a.surface) if a.surface is not None else np.zeros((1, 1), dtype=z.dtype)
        K.evaluate_v(z, s, a.surface is not None, a.anchors, np.ascontiguousarray(found), float(a.res),
                     t is not None, log_spans, span_index, ratios, ratio_index, sag, fractions, fall_zone,
                     float(a.high_above), *rule, zones, out, terrain, surface)
    keep = (out[:, 5] != 0) & (out[:, 9] != 0)
    if a.nmpt_mode == "reject":
        keep &= out[:, 10] == 0
    if limits is not None:
        angles = sh.wall_angles(a.anchors[found[:, 0]], a.anchors[found[:, 1]], a.down[found[:, 0]],
                                a.down[found[:, 1]])
        keep = limits.passes(out[:, 6], out[:, 7], out[:, 8], angles[0], angles[1], keep)
    return {"pairs": found[keep], "length": out[keep, 2], "clearance": out[keep, 3], "clearance_nmpt": out[keep, 4],
            "height_max": out[keep, 6], "terrain": terrain[keep], "surface": surface[keep]}


def valid_at(lines: Dict[str, np.ndarray], zones: np.ndarray, j: int, lift: float, delta: float,
             nmpt_mode: Optional[str]) -> np.ndarray:
    """Which of a run's lines are valid at ladder zone zones[j] and lift (both at most the run's):
    the buckets 0..j above -lift - delta, the rest above -lift; with "reject" the surface's
    buckets not at or below them. The same float comparisons as evaluate_v's rule."""
    strict, lenient = -lift - 0.0, -lift - delta
    t, s = lines["terrain"], lines["surface"]
    inf = np.full(len(t), np.inf)
    zone = t[:, :j + 1].min(axis=1) if len(t) else inf
    core = t[:, j + 1:].min(axis=1) if t.shape[1] > j + 1 and len(t) else inf
    ok = (zone > lenient) & (core > strict)
    if nmpt_mode == "reject":
        szone = s[:, :j + 1].min(axis=1) if len(s) else inf
        score = s[:, j + 1:].min(axis=1) if s.shape[1] > j + 1 and len(s) else inf
        ok &= ~((szone <= lenient) | (score <= strict))
    return ok


def ordered(lines: Dict[str, np.ndarray], mask: Optional[np.ndarray] = None) -> np.ndarray:
    """The rows (of mask) in find_valid_lines' order: longest first, ties in the order found."""
    rows = np.arange(len(lines["length"])) if mask is None else np.flatnonzero(mask)
    return rows[np.argsort(-lines["length"][rows], kind="stable")]


def production(a: SimpleNamespace, threads: Optional[int]):
    """linesearch.find_valid_lines on the call, with its funnel and the seconds of its bars."""
    stats, clock = {}, plf.BarClock()
    plf.progress.subscribe(clock)
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            result = ls.find_valid_lines(a.z, a.surface, a.anchors, a.res, a.min_length, a.max_length,
                                         a.nmpt_mode, threads, a.sag_table, a.max_dh_ratio, a.max_dh, a.first,
                                         a.high_above, limits_of(a), a.anchor_values,
                                         a.strong_given, stats)
    finally:
        plf.progress.unsubscribe(clock)
    return result, stats, clock.seconds


def same_lines(table, pairs: np.ndarray, anchors: np.ndarray) -> bool:
    """Production's lines (a LineTable) and pairs of anchor indices: the same lines in the same order."""
    return (len(table) == len(pairs) and np.array_equal(table.columns["a1"], anchors[pairs[:, 0]])
            and np.array_equal(table.columns["a2"], anchors[pairs[:, 1]]))


def spots(a: SimpleNamespace, lines: Dict[str, np.ndarray], rows: np.ndarray, distance: float, by: str) -> int:
    """The groups mapping.group_lines makes of the lines at rows (anchor pixels to the grid's metres)."""
    import mapping as mp

    if not len(rows):
        return 0
    pairs = lines["pairs"][rows]
    left, top = (a.grid["left"], a.grid["top"]) if a.grid else (0.0, 0.0)
    xy = lambda p: np.column_stack([left + (a.anchors[p, 1] + 0.5) * a.res,  # noqa: E731
                                    top - (a.anchors[p, 0] + 0.5) * a.res])
    over = lines["clearance_nmpt"][rows] <= 0 if a.nmpt_mode == "mark" else np.zeros(len(rows), dtype=bool)
    table = sh.LineTable({"length": lines["length"][rows], "clearance": lines["clearance"][rows],
                          "height_max": lines["height_max"][rows], "over_obstacles": over,
                          "a1_xy": xy(pairs[:, 0]), "a2_xy": xy(pairs[:, 1])})
    with contextlib.redirect_stdout(io.StringIO()):
        return len(mp.group_lines(table, distance, by))


def variants_call(a: SimpleNamespace, zones: Sequence[float], lifts: Sequence[float], cap: float,
                  end_clearance: float, threads: Optional[int], with_spots: bool, distance: float,
                  by: str) -> Dict:
    """variants of one captured call (see the module docstring)."""
    zones = sorted(set([0.0] + [float(x) for x in zones]))
    lifts = sorted(set([0.0] + [float(h) for h in lifts]))
    threads = threads or numba.get_num_threads()
    numba.set_num_threads(threads)
    delta = check_rule(a, lifts[-1], zones[-1], end_clearance, cap)
    warm = subset(a, min(WARM_ANCHORS, len(a.anchors)))  # numba compiles here, not in the timed runs
    run_rule(warm, 0.0, 0.0, cap, end_clearance, zones)
    run_rule(warm, lifts[-1], zones[-1], cap, end_clearance, zones)
    with contextlib.redirect_stdout(io.StringIO()):
        ls.find_valid_lines(warm.z, warm.surface, warm.anchors, warm.res, warm.min_length, warm.max_length,
                            warm.nmpt_mode, threads, warm.sag_table, warm.max_dh_ratio, warm.max_dh, warm.first)
    base = run_rule(a, 0.0, 0.0, cap, end_clearance, zones)
    top = run_rule(a, lifts[-1], zones[-1], cap, end_clearance, zones)
    prod, prod_funnel, prod_seconds = production(a, threads)
    # the referee: production's lines at (0, 0), by the baseline run and by the superset's buckets
    if not same_lines(prod, base.lines["pairs"][ordered(base.lines)], a.anchors):
        raise StudyError(f"{a.folder}: the variant kernels at zone 0, lift 0 differ from find_valid_lines")
    funnel_keys = {"open": "open", "todo": "todo", "candidates": "candidates", "checked": "checked",
                   "found": "found", "valid": "valid"}
    if any(base.funnel[k] != prod_funnel.get(p) for k, p in funnel_keys.items()):
        raise StudyError(f"{a.folder}: the baseline's funnel {base.funnel} is not production's {prod_funnel}")
    nz = len(zones)
    valid = np.zeros((len(top.lines["pairs"]), nz, len(lifts)), dtype=bool)
    for j in range(nz):
        for k, lift in enumerate(lifts):
            valid[:, j, k] = valid_at(top.lines, top.zones, j, lift, delta, a.nmpt_mode)
    if not same_lines(prod, top.lines["pairs"][ordered(top.lines, valid[:, 0, 0])], a.anchors):
        raise StudyError(f"{a.folder}: the superset's lines at zone 0, lift 0 differ from find_valid_lines")
    if not valid[:, -1, -1].all():
        raise StudyError(f"{a.folder}: a line of the superset run fails the superset's own buckets")
    table = {}
    for j, x in enumerate(zones):
        for k, lift in enumerate(lifts):
            mask = valid[:, j, k]
            entry = {"zone": x, "lift": lift, "lines": int(mask.sum()), "new": int((mask & ~valid[:, 0, 0]).sum())}
            if with_spots:
                entry["spots"] = spots(a, top.lines, ordered(top.lines, mask), distance, by)
            table[f"{x:g},{lift:g}"] = entry
    return {"call": os.path.basename(os.path.normpath(a.folder)), "anchors": len(a.anchors), "res": a.res,
            "min_length": a.min_length, "max_length": a.max_length, "model": "sag" if a.use_sag else "formula",
            "nmpt_mode": a.nmpt_mode, "fall": a.fall, "delta": delta, "zones": zones, "lifts": lifts, "cap": cap,
            "end_clearance": end_clearance, "threads": numba.get_num_threads(), "table": table,
            "funnel": {"baseline": base.funnel, "superset": top.funnel, "production": prod_funnel},
            "seconds": {"baseline": base.seconds, "superset": top.seconds, "production": prod_seconds},
            "checks": {"baseline_equals_production": True, "superset_00_equals_production": True},
            "_lines": top.lines, "_valid": valid}


def summed_calls(results: List[Dict]) -> Dict:
    """The calls of a place added up (counts and seconds; the parameters of the first)."""
    first = {k: v for k, v in results[0].items() if not k.startswith("_")}
    if len(results) == 1:
        return first
    total = json.loads(json.dumps(first))
    for r in results[1:]:
        total["anchors"] += r["anchors"]
        for key, e in r["table"].items():
            for name in ("lines", "new", "spots"):
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
             with_spots: bool = True) -> Dict:
    calls = call_folders(folder)
    out = folder
    distance_opt = search_option(folder, "--group-distance")
    by = search_option(folder, "--group-by", "clearance")
    results, arrays = [], {}
    for call in calls:
        a = setup(call)
        distance = float(distance_opt) if distance_opt else max(20.0, 2 * a.res)
        r = variants_call(a, zones, lifts, cap, end_clearance, threads, with_spots, distance, by)
        name = r["call"]
        arrays[f"{name}_a1"] = a.anchors[r["_lines"]["pairs"][:, 0]].astype(np.int32)
        arrays[f"{name}_a2"] = a.anchors[r["_lines"]["pairs"][:, 1]].astype(np.int32)
        arrays[f"{name}_valid"] = r["_valid"]
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
# brute force (the tests' referee, and diagnose)

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


def in_zone(steps: int, length: float, end_zone: float, cap: float) -> np.ndarray:
    """Which of the steps 1 .. steps - 1 lie in the zone (end_zone_kernels.zone_steps)."""
    kz = K.zone_steps(steps, length, end_zone, cap)
    k = np.arange(1, steps)
    return (k < kz) | (steps - k < kz)


def rule_passes(m, steps: int, length: float, lift: float, delta: float, end_zone: float, cap: float,
                nmpt_mode: Optional[str] = None) -> bool:
    """The rule of the study pixel by pixel (no EPS): terrain margins m = (terrain, surface)."""
    terrain, surface = m
    zone = in_zone(steps, length, end_zone, cap)
    bound = np.where(zone, -lift - delta, -lift - 0.0)
    if not np.all(terrain > bound):  # NaN fails
        return False
    if nmpt_mode == "reject" and surface is not None:
        seen = ~np.isnan(surface)
        if np.any(surface[seen] <= bound[seen]):
            return False
    return True


def brute_force(z, surface, anchors, res, min_length, max_length, max_dh_ratio, max_dh, sag_table, nmpt_mode,
                rules: Sequence[tuple], cap: float = CAP, end_clearance: float = 0.0, first=None) -> List[set]:
    """Every anchor pair under each rule (lift, end_zone) as find_valid_lines' filters and the
    rule pixel by pixel decide (no limits, no strong mask): a set of (lower index, higher) each."""
    delta = sh.fall_allowance(sag_table) - end_clearance
    anchors = np.asarray(anchors, dtype=np.int64)
    elev = z[anchors[:, 0], anchors[:, 1]]
    found = [set() for _ in rules]
    for i in range(len(anchors)):
        for j in range(i + 1, len(anchors)):
            if first is not None:  # the line belongs to its first anchor (smaller x, then y)
                f = i if (anchors[i, 1], anchors[i, 0]) < (anchors[j, 1], anchors[j, 0]) else j
                if not first[f]:
                    continue
            dr, dc = anchors[j] - anchors[i]
            length = math.hypot(dr, dc) * res
            if length > max_length or length < min_length:
                continue
            if not abs(float(elev[j]) - float(elev[i])) <= min(max_dh_ratio * length, max_dh):
                continue
            m = margins(z, anchors[i], anchors[j], res, sag_table, surface)
            if m is None:
                continue
            for n, (lift, end_zone) in enumerate(rules):
                if rule_passes(m[:2], m[2], m[3], lift, delta, end_zone, cap, nmpt_mode):
                    found[n].add((i, j))
    return found


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


def buckets_of(m, steps: int, length: float, zones: Sequence[float], cap: float):
    """The smallest terrain margin per ladder bucket (as evaluate_v; NaN: the line fails anywhere)."""
    terrain = m[0]
    k = np.arange(1, steps)
    e = np.minimum(k, steps - k)
    out = np.full(len(zones) + 1, np.inf)
    bucket = np.full(len(k), len(zones))
    for j in reversed(range(len(zones))):
        bucket[e < K.zone_steps(steps, length, zones[j], cap)] = j
    for j in range(len(zones) + 1):
        if (bucket == j).any():
            out[j] = np.min(terrain[bucket == j])
    return out


def needed_lift(buckets: np.ndarray, j: int, delta: float) -> float:
    """The lift that ladder zone j needs at least (valid for any larger lift; the rule is strict)."""
    if np.isnan(buckets).any():
        return math.inf
    zone, core = buckets[:j + 1].min(), buckets[j + 1:].min() if len(buckets) > j + 1 else math.inf
    return max(0.0, -core, -zone - delta)


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
            b = buckets_of(m, m[2], m[3], zones, cap)
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
    terrain, steps, length = m[0], m[2], m[3]
    result["best"] = {"a1": [int(v) for v in lo], "a2": [int(v) for v in hi], "length": length,
                      "clearance": clearance, "accepted": bool(clearance > 0),
                      "dh": float(a.z[tuple(hi)] - a.z[tuple(lo)])}
    if not clearance > 0:
        fails = np.flatnonzero(~(terrain > 0))
        first, last = int(fails[0]) + 1, int(fails[-1]) + 1
        result["best"]["first_fail"] = {
            "from_a1": {"step": first, "m": first * length / steps, "deficit": float(terrain[first - 1])},
            "from_a2": {"step": steps - last, "m": (steps - last) * length / steps, "deficit": float(terrain[last - 1])}}
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
            cells.append(cell)
        md.append(f"| {x:g} m | " + " | ".join(cells) + " |")
    md += ["", "Funnel:", "", "| run | anchors | open | open share | todo | candidates | checked | found | valid |",
           "| --- | " + " | ".join(["---:"] * 8) + " |"]
    for run in ("baseline", "superset"):
        f = v["funnel"][run]
        md.append(f"| {run} | {f['anchors']} | {f['open']} | {100 * f['open'] / f['anchors'] if f['anchors'] else 0:.1f}% "
                  f"| {f['todo']} | {f['candidates']} | {f['checked']} | {f['found']} | {f['valid']} |")
    md += ["", f"Seconds (superset: zone {zones[-1]:g} m, lift {lifts[-1]:g} m; indicative when measured in a "
               "shared slot):", "", *seconds_rows(v), "",
           "Checks: the baseline run and the superset's zone 0 / lift 0 equal find_valid_lines (lines and order), "
           "the baseline's funnel equals production's: " + ("passed" if all(v["checks"].values()) else "FAILED"), ""]
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


def pictures(folder: str, v: Dict, d: Optional[Dict], out: str) -> List[str]:
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
    picks = [(len(zones) - 1, 0), (0, len(lifts) - 1), (len(zones) - 1, len(lifts) - 1)]
    fig, axes = plt.subplots(1, 3, figsize=(18, 6.4))
    rng = np.random.default_rng(0)

    def segments(mask):
        rows = np.flatnonzero(mask)
        if len(rows) > MAP_LINES:
            rows = np.sort(rng.choice(rows, MAP_LINES, replace=False))
        return np.stack([a1[rows][:, ::-1], a2[rows][:, ::-1]], axis=1), len(np.flatnonzero(mask))

    base = valid[:, 0, 0]
    rows, cols = np.nonzero(np.isfinite(z))  # the grid's data only (a circle's corners are NaN)
    box = (cols.min() - 0.5, cols.max() + 0.5, rows.max() + 0.5, rows.min() - 0.5) if len(rows) else None
    for ax, (j, k) in zip(axes, picks):
        ax.imshow(shade, cmap="gray", interpolation="nearest")
        new = valid[:, j, k] & ~base
        segs, n_new = segments(new)  # the new lines below, the baseline's above them
        ax.add_collection(LineCollection(segs, colors="#e53e3e", linewidths=0.3, alpha=0.35))
        segs, n_base = segments(base)
        ax.add_collection(LineCollection(segs, colors="#1e40af", linewidths=0.6, alpha=0.9))
        if box:
            ax.set_xlim(box[0], box[1])
            ax.set_ylim(box[2], box[3])
        ax.set_title(f"zone {zones[j]:g} m, lift {lifts[k]:g} m: {n_base} lines (blue) + {n_new} new (red)",
                     fontsize=9)
        ax.set_xticks([])
        ax.set_yticks([])
    fig.suptitle(f"{v['place']}: baseline and new lines (at most {MAP_LINES} drawn per colour)")
    fig.tight_layout()
    path = os.path.join(out, f"{v['place']}-map.png")
    fig.savefig(path, dpi=110)
    plt.close(fig)
    made.append(path)
    if d:
        a = setup(call)
        for n, ln in enumerate(d["lines"]):
            b = ln.get("best")
            if not b:
                continue
            m = margins(a.z, b["a1"], b["a2"], a.res, a.sag_table)
            terrain, steps, length = m[0], m[2], m[3]
            t = np.arange(steps + 1) / steps
            r1, c1 = b["a1"]
            dr, dc = b["a2"][0] - r1, b["a2"][1] - c1
            ground = a.z[r1 + np.rint(dr * t).astype(int), c1 + np.rint(dc * t).astype(int)]
            limit = sh.max_safe_elevation(t, length, float(ground[0]), float(ground[-1]), a.sag_table)
            fig, ax = plt.subplots(figsize=(8, 3.2))
            ax.plot(t * length, ground, color="#555", label="terrain")
            ax.plot(t * length, limit, color="#2b6cb0", label="limit (today)")
            ax.plot(t * length, limit + d["delta"], color="#2b6cb0", ls=":", label="limit + delta (in a zone)")
            ax.set_title(f"{ln['name']}: {length:.0f} m, clearance {b['clearance']:.2f} m; lift needed "
                         + ", ".join(f"{s['zone']:g} m: {fmt(s['lift'], 1)}" for s in ln["staircase"]), fontsize=8)
            ax.set_xlabel("m from a1")
            ax.legend(fontsize=7)
            fig.tight_layout()
            path = os.path.join(out, f"{v['place']}-line-{n + 1}.png")
            fig.savefig(path, dpi=110)
            plt.close(fig)
            made.append(path)
    return made


def report(out: str, folders: List[str], with_pictures: bool = True) -> str:
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
        md += place_markdown(v, d)
        made = []
        if with_pictures:
            made = pictures(folder, v, d, os.path.join(out, "pictures"))
            md += [f"![{os.path.basename(p)}](pictures/{os.path.basename(p)})" for p in made] + [""]
        places.append({"variants": v, "diagnose": d, "pictures": [os.path.relpath(p, out) for p in made]})
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
        else:
            p.add_argument("--lines", required=True, help="JSON: [{name, a: [lat, lon], b: [lat, lon]}, ...]")
            p.add_argument("--radius", type=float, default=RADIUS, help="metres around each end")
            p.add_argument("--thresholds", type=numbers, default=list(THRESHOLDS), help="slope thresholds, degrees")
    p = sub.add_parser("report", help="study.json, study.md and pictures of the places")
    p.add_argument("out")
    p.add_argument("folders", nargs="+")
    p.add_argument("--no-pictures", action="store_true")
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
                        not args.no_spots)
        for key, e in data["table"].items():
            print(f"zone,lift {key}: {e['lines']} lines (+{e['new']})" + (f", {e['spots']} spots" if "spots" in e
                                                                           else ""))
        return 0
    if args.command == "diagnose":
        data = diagnose(args.folder, args.lines, args.radius, args.zones, args.cap, args.end_clearance,
                        args.thresholds)
        for ln in data["lines"]:
            b = ln.get("best")
            print(f"{ln['name']}: " + (f"clearance {b['clearance']:.2f} m, "
                                       f"{'accepted' if b['accepted'] else 'rejected'}" if b else ln.get("error", "")))
        return 0
    report(args.out, args.folders, not args.no_pictures)
    print(os.path.join(args.out, "study.md"))
    return 0


if __name__ == "__main__":
    from progress import utf8_output
    utf8_output()  # redirected output in UTF-8, not the Windows code page
    sys.exit(main())
