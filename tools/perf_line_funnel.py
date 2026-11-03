"""
Run by hand: how the line search eliminates potential lines, stage by stage (docs/performance.md).

capture runs findaline.py in this process (as perf_profile.py) with linesearch.find_valid_lines
wrapped: for each selected call (a tiled area makes one per tile) it saves the inputs and
parameters into <out>/call-<k>/ and records the wall and CPU seconds of the bars "free
directions", "anchor pairs" and "checking lines". The search itself runs unchanged.

    uv run tools/perf_line_funnel.py capture --out <scratch>/zk [--calls 0,1] -- --lat .. --lon .. ...

analyse rebuilds the kernels' arguments from a capture, checks that the production kernels
still give exactly the results of the frozen references (tools/line_funnel_kernels.py), and
counts where the work goes: the rings of the free directions, the visits of the pair search
and the tests that reject them, the visits candidate rules would skip, the work held by the
anchors that find lines, and the pixel tests of _line_ok under other pixel orders. Writes
<out>/funnel.json and <out>/funnel.md.

    uv run tools/perf_line_funnel.py analyse <scratch>/zk/call-0 --out <scratch>/zk [--sample-every M]

The options after "--" are findaline.py's; --no-plot, --yes and --ortho never are added. Give
--data-dir there to keep the runs out of the repository's runs/.
"""

import argparse
import dataclasses
import inspect
import json
import math
import os
import runpy
import sys
import time
from types import SimpleNamespace
from typing import Dict, List, Optional

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "tools"))

import numba  # noqa: E402
import numpy as np  # noqa: E402

import helpers as sh  # noqa: E402
import line_funnel_kernels as K  # noqa: E402
import linesearch as ls  # noqa: E402
import sag as sg  # noqa: E402
from progress import progress  # noqa: E402

STAGES = ("free directions", "anchor pairs", "checking lines")
PAIR_COUNTERS = {
    "visits": K.C_VISITS, "dedup": K.C_DEDUP, "strong": K.C_STRONG, "max_length": K.C_MAX_LENGTH,
    "min_length": K.C_MIN_LENGTH, "height_diff": K.C_HEIGHT, "wall_angle": K.C_WALL,
    "candidates": K.C_CANDIDATES, "rings_a": K.C_RINGS_A, "rings_b": K.C_RINGS_B, "checked": K.C_CHECKED,
    "line_ok_fail": K.C_LINE_FAIL, "found": K.C_FOUND, "line_ok_tests": K.C_TESTS,
    "F2a_with_prefix": K.C_PREFIX, "F8c_own_rings": K.C_F8C_OWN, "F8c_partners": K.C_F8C_PARTNERS,
    "sampled_anchors": K.C_SAMPLED, "sampled_line_ok_tests": K.C_SAMPLED_TESTS,
    "sim_mismatch": K.C_SIM_MISMATCH, "N1_candidates": K.C_N1_CANDIDATES,
    "F8c_candidates": K.C_F8C_CANDIDATES, "F8c_partner_own": K.C_F8C_PARTNER_OWN,
    "F8c_partner_mask": K.C_F8C_PARTNER_MASK, "F8c_mask_candidates": K.C_F8C_MASK_CANDIDATES,
}
RULES = ("F2a", "F2b", "N1", "F8c", "cell_elev", "N3")
# The tests of the pair search in today's order: (name, counter of its rejections)
REJECTIONS = (("dedup", "dedup"), ("strong", "strong"), ("max length", "max_length"),
              ("min length", "min_length"), ("height difference", "height_diff"),
              ("wall angle", "wall_angle"), ("rings of a", "rings_a"), ("rings of b", "rings_b"),
              ("_line_ok", "line_ok_fail"))
CLASSES = ("<=129 px", "<=500 px", ">500 px")
THREAD_SPLITS = (7, 24)


class SelfCheckError(RuntimeError):
    """The production kernels no longer give the results of the references."""


# ---------------------------------------------------------------------------------------------
# capture

class BarClock:
    """Wall and CPU seconds (time.process_time: all threads) of the bars of STAGES."""

    def __init__(self):
        self.running = {}
        self.seconds = {}

    def __call__(self, state):
        stage = state["stage"]
        if stage not in STAGES:
            return
        if state["done"]:
            start = self.running.pop(stage, None)
            if start is not None:
                wall, cpu = self.seconds.get(stage, (0.0, 0.0))
                self.seconds[stage] = (wall + time.monotonic() - start[0], cpu + time.process_time() - start[1])
        elif state["count"] == 0 and stage not in self.running:
            self.running[stage] = (time.monotonic(), time.process_time())


def save_call(folder: str, bound: Dict, step: str = ""):
    """The inputs (copies: the grids of a search are memory-mapped and deleted with its work
    folder) and the parameters of one find_valid_lines call, by argument name."""
    os.makedirs(folder, exist_ok=True)
    arrays = {"elevation": np.array(bound["elevation"]),
              "anchors": np.asarray(bound["anchors"], dtype=np.int64)}
    for name in ("surface", "first", "strong", "anchor_values"):
        if bound.get(name) is not None:
            arrays[name] = np.array(bound[name])
    table = bound.get("sag_table")
    if table is not None:
        arrays["sag_spans"], arrays["sag_sag"] = np.array(table.spans), np.array(table.sag)
        arrays["sag_fractions"] = np.array(table.fractions)
    np.savez(os.path.join(folder, "inputs.npz"), **arrays)
    limits = bound.get("limits")
    params = {"res": float(bound["res"]), "min_length": float(bound["min_length"]),
              "max_length": float(bound["max_length"]), "max_dh_ratio": float(bound["max_dh_ratio"]),
              "max_dh": float(bound["max_dh"]), "nmpt_mode": bound.get("nmpt_mode"),
              "high_above": float(bound["high_above"]), "threads": bound.get("threads"),
              "limits": dataclasses.asdict(limits) if limits is not None else None,
              "sag": table is not None,
              # search.py builds the table as sag.EnvelopeTable(rigging, min_length, max_length)
              "rigging": dataclasses.asdict(table.rig) if table is not None else None,
              "sag_min_span": float(bound["min_length"]) if table is not None else None,
              "sag_max_span": float(bound["max_length"]) if table is not None else None,
              "step": step}
    with open(os.path.join(folder, "params.json"), "w") as f:
        json.dump(params, f, indent=1)


class Capture:
    """The wrapper of linesearch.find_valid_lines (all arguments passed through)."""

    def __init__(self, out: str, calls: Optional[List[int]]):
        self.out, self.calls, self.n = out, calls, 0
        self.original = ls.find_valid_lines
        self.signature = inspect.signature(self.original)

    def __call__(self, *args, **kwargs):
        k, self.n = self.n, self.n + 1
        if self.calls is not None and k not in self.calls:
            return self.original(*args, **kwargs)
        bound = self.signature.bind(*args, **kwargs)
        bound.apply_defaults()
        folder = os.path.join(self.out, f"call-{k}")
        save_call(folder, dict(bound.arguments), progress_step())
        clock = BarClock()
        progress.subscribe(clock)
        wall, cpu = time.monotonic(), time.process_time()
        try:
            result = self.original(*args, **kwargs)
        finally:
            progress.unsubscribe(clock)
        timing = {"call": [time.monotonic() - wall, time.process_time() - cpu], "lines": len(result),
                  "stages": {stage: list(v) for stage, v in clock.seconds.items()}}
        with open(os.path.join(folder, "timings.json"), "w") as f:
            json.dump(timing, f, indent=1)
        return result

    def install(self):
        ls.find_valid_lines = self  # search.py looks it up as ls.find_valid_lines at each call

    def uninstall(self):
        ls.find_valid_lines = self.original


def progress_step() -> str:
    import progress as pg
    return pg._step["text"]


def capture(out: str, calls: Optional[List[int]], search_args: List[str]) -> int:
    os.makedirs(out, exist_ok=True)
    os.environ.setdefault("FINDALINE_PROGRESS", "text")
    wrapper = Capture(out, calls)
    wrapper.install()
    sys.argv = [os.path.join(HERE, "findaline.py"), *search_args, "--no-plot", "--yes", "--ortho", "never"]
    code = 0
    try:
        runpy.run_path(sys.argv[0], run_name="__main__")
    except SystemExit as e:
        if e.code not in (None, 0):
            print(f"findaline.py ended with {e.code!r}", file=sys.stderr)
            code = 1
    finally:
        wrapper.uninstall()
    print(f"find_valid_lines called {wrapper.n} times; captured into {out}")
    return code


# ---------------------------------------------------------------------------------------------
# analyse

def load_call(folder: str):
    with np.load(os.path.join(folder, "inputs.npz")) as data:
        inputs = {name: data[name] for name in data.files}
    with open(os.path.join(folder, "params.json")) as f:
        params = json.load(f)
    timings = None
    if os.path.exists(os.path.join(folder, "timings.json")):
        with open(os.path.join(folder, "timings.json")) as f:
            timings = json.load(f)
    return inputs, params, timings


def sag_table_of(inputs: Dict, params: Dict):
    """The sag.EnvelopeTable of the call (its saved arrays; rebuilt from the rigging without them)."""
    if not params["sag"]:
        return None
    if "sag_sag" not in inputs:
        return sg.EnvelopeTable(sg.Rigging(**params["rigging"]), params["sag_min_span"], params["sag_max_span"])
    return SimpleNamespace(spans=inputs["sag_spans"], sag=inputs["sag_sag"], fractions=inputs["sag_fractions"],
                           RATIOS=sg.EnvelopeTable.RATIOS, rig=sg.Rigging(**params["rigging"]))


def rebuild(inputs: Dict, params: Dict, free_rings=K.ref_free_rings) -> SimpleNamespace:
    """The arguments of the kernels exactly as linesearch.find_valid_lines builds them: a
    mirror of linesearch.py:408-452 (at 975a1b7; keep it in step when that part changes).
    The rings come from free_rings (the reference by default)."""
    a = SimpleNamespace()
    a.z = z = np.asarray(inputs["elevation"])
    a.anchors = anchors = np.ascontiguousarray(inputs["anchors"], dtype=np.int64)
    a.elev = np.asarray(z[anchors[:, 0], anchors[:, 1]])
    a.res = res = params["res"]
    a.min_length, a.max_length = float(params["min_length"]), float(params["max_length"])
    max_dh_ratio, max_dh = params["max_dh_ratio"], params["max_dh"]
    sag_table = sag_table_of(inputs, params)
    if sag_table is None:
        a.use_sag, a.log_spans, a.ratios, a.table, a.fall_zone = (False, np.zeros(2), np.zeros(2),
                                                                  np.zeros((2, 2, 2)), 0.0)
        a.gain, a.cap, a.offset = -sh.SLOPE, np.inf, sh.LEASH_FALL
    else:
        a.use_sag = True
        a.log_spans, a.ratios = np.log(sag_table.spans), sag_table.RATIOS.astype(np.float64)
        a.table, a.fall_zone = np.ascontiguousarray(sag_table.sag), sag_table.rig.fall_zone
        a.gain, a.cap = max_dh_ratio * math.sqrt(2), max_dh
        a.offset = a.fall_zone + min(0.0, float(a.table.min()))

    a.rings = free_rings(z, anchors, res, a.gain, a.cap, a.offset)
    a.need_min = min(ls.RINGS, int(a.min_length / (res * math.sqrt(2))) // 2)
    a.useful = useful = np.flatnonzero(a.rings.max(axis=1) >= a.need_min)
    first = inputs.get("first")
    a.todo_all = useful if first is None else useful[np.asarray(first)[useful]]

    a.cell = cell = max(1, int(a.max_length / res) // 4)
    a.cells_x = cells_x = z.shape[1] // cell + 1
    a.cells_y = cells_y = z.shape[0] // cell + 1
    keys = (anchors[useful, 0] // cell) * cells_x + anchors[useful, 1] // cell
    a.order = useful[np.argsort(keys, kind="stable")]
    a.starts = np.searchsorted(np.sort(keys), np.arange(cells_y * cells_x)).astype(np.int64)

    a.down = sh.downslope(z, anchors, res)
    limits = params["limits"]
    wall = limits.get("max_wall_angle") if limits else None
    max_angle = wall if wall is not None else 180.0
    a.cos_limit = -2.0 if max_angle >= 180 else math.cos(math.radians(max_angle))
    strong = inputs.get("strong")
    a.strong = np.ones(len(anchors), dtype=np.bool_) if strong is None else np.asarray(strong, dtype=np.bool_)
    a.first_only = first is not None
    a.first = first
    a.args = (z, anchors, a.elev, a.rings)
    a.tail = (a.order, a.starts, cell, cells_x, res, a.min_length, a.max_length, float(max_dh_ratio),
              float(max_dh), a.down, a.cos_limit, a.strong, a.use_sag, a.log_spans, a.ratios, a.table,
              float(a.fall_zone), a.first_only)
    a.max_dh_ratio, a.max_dh = float(max_dh_ratio), float(max_dh)
    return a


def chunks_of(todo_all: np.ndarray) -> List[np.ndarray]:
    """The chunks of find_valid_lines."""
    return np.array_split(todo_all, min(ls.CHUNKS, max(1, len(todo_all))))


def two_passes(kernel, a, todo):
    """A pair kernel's counting pass, then its writing pass over every anchor of the chunk, as
    find_valid_lines ran them at 975a1b7 (the references')."""
    counts = np.zeros((len(todo), 3), dtype=np.int64)
    kernel(*a.args, todo, *a.tail, None, np.zeros((0, 2), dtype=np.int64), counts)
    offsets = np.concatenate([[0], np.cumsum(counts[:, 2])[:-1]]).astype(np.int64)
    out = np.empty((int(counts[:, 2].sum()), 2), dtype=np.int64)
    kernel(*a.args, todo, *a.tail, offsets, out, np.zeros_like(counts))
    return counts, out


def production_rings(a):
    """Production's rings of every anchor of the call (linesearch._free_rings on all at once)."""
    return ls._free_rings(a.z, a.anchors, a.res, a.gain, a.cap, a.offset,
                          ls.largest_need(a.min_length, a.max_length, a.res), ls.sector_masks())


def production_directions(a):
    """Production's step 1 (linesearch.free_directions): the useful anchors, their rings, the
    row of every anchor."""
    return ls.free_directions(a.z, a.anchors, a.res, a.gain, a.cap, a.offset, a.min_length, a.max_length)


def capped_rings(a):
    """The references' rings capped at production's largest ring (linesearch.largest_need, the
    largest need of a pair: every decision compares a ring with a need up to it, so the cap
    changes none)."""
    return np.minimum(a.rings, ls.largest_need(a.min_length, a.max_length, a.res))


def production_args(a, directions):
    """Production's arguments of the pair search (linesearch.pair_arguments) from those of
    production_directions: (_pairs' arguments before and after todo, the anchors pairs are
    searched from)."""
    useful, rows, slot = directions
    todo_all, head, tail = ls.pair_arguments(a.z, a.anchors, a.elev, useful, rows, slot, a.first, a.res,
                                             a.min_length, a.max_length, a.max_dh_ratio, a.max_dh, a.down,
                                             a.cos_limit, a.strong, a.use_sag, a.log_spans, a.ratios, a.table,
                                             a.fall_zone)
    return head, tail, todo_all


def funnel_inputs(a) -> SimpleNamespace:
    """What funnel_pairs needs besides the kernels' arguments."""
    f = SimpleNamespace()
    f.rmax = a.rings.max(axis=1).astype(np.int64) if len(a.anchors) else np.zeros(0, dtype=np.int64)
    f.big_k = min(ls.RINGS, (int(a.max_length / a.res) + 1) // 2)
    f.cell_mask, f.cell_emin, f.cell_emax = K.cell_summary(a.order, a.starts, a.elev, a.rings, a.need_min)
    f.anchor_mask = K.anchor_masks(a.rings, a.need_min)
    f.d0 = min(a.max_dh_ratio * a.max_length, a.max_dh)
    f.far2 = int(math.floor((a.max_length / a.res + 2) ** 2))
    return f


def self_check(a, folder: str = "", sample_every: int = 1) -> List:
    """Production's kernels against the frozen references (SelfCheckError when they differ):
    the rings, then per chunk the counts of the counting pass and the pairs written, both
    against the references and funnel_pairs (run here, simulating the pixel orders for every
    sample_every-th anchor). The pairs and the checked and found counts must be equal; the
    candidates are the references' less those N1 and F8c skip (production skips them before
    counting: they fail the rings' test, which comes after the count). Returns per chunk (todo,
    the references' counts, funnel_pairs' counters, simulated tests, histograms)."""
    capped = capped_rings(a)
    if not np.array_equal(production_rings(a), capped):
        raise SelfCheckError(f"{folder}: linesearch._free_rings differs from ref_free_rings")
    directions = production_directions(a)
    useful, rows, slot = directions
    if not (np.array_equal(useful, a.useful) and np.array_equal(rows, capped[a.useful])
            and np.array_equal(slot[useful], np.arange(len(useful))) and (np.delete(slot, useful) == -1).all()):
        raise SelfCheckError(f"{folder}: linesearch.free_directions differs from ref_free_rings")
    head, tail, todo_all = production_args(a, directions)
    if not np.array_equal(todo_all, a.todo_all):
        raise SelfCheckError(f"{folder}: linesearch.pair_arguments starts from other anchors")
    f = funnel_inputs(a)
    chunks, q0 = [], 0
    for todo in chunks_of(a.todo_all):
        ref_counts, ref_out = two_passes(K.ref_pairs, a, todo)
        c = np.zeros((len(todo), K.N_COUNTERS), dtype=np.int64)
        s = np.zeros((len(todo), K.N_ORDERS), dtype=np.int64)
        h = np.zeros((len(todo), K.N_HIST), dtype=np.int64)
        sample = (np.arange(q0, q0 + len(todo)) % sample_every) == 0
        K.funnel_pairs(*a.args, todo, *a.tail, f.rmax, f.big_k, f.cell_mask, f.cell_emin, f.cell_emax,
                       f.anchor_mask, f.d0, f.far2, ls.LINE_ORDER_SPLIT, ls.LINE_ORDER_MAX, sample, c, s, h)
        if not np.array_equal(c[:, [K.C_CANDIDATES, K.C_CHECKED, K.C_FOUND]], ref_counts):
            raise SelfCheckError(f"{folder}: funnel_pairs counts differ from ref_pairs")
        counts, out = ls.pair_chunk(head, todo, tail)
        if not (np.array_equal(counts[:, 1:], ref_counts[:, 1:]) and np.array_equal(out, ref_out)):
            raise SelfCheckError(f"{folder}: linesearch._pairs differs from ref_pairs")
        if not np.array_equal(counts[:, 0], ref_counts[:, 0] - c[:, K.C_N1_CANDIDATES] - c[:, K.C_F8C_CANDIDATES]):
            raise SelfCheckError(f"{folder}: linesearch._pairs' candidates are not ref_pairs' less those N1 "
                                 "and F8c skip")
        chunks.append((todo, ref_counts, c, s, h))
        q0 += len(todo)
    return chunks


def ring_work(a) -> Dict:
    """The work of the free directions per anchor and per ring (funnel_rings), and that its
    rings are the reference's."""
    n = len(a.anchors)
    big_k = min(ls.RINGS, (int(a.max_length / a.res) + 1) // 2)
    totals = np.zeros(len(K.RING_COUNTERS), dtype=np.int64)
    alive_anchors = np.zeros(K.RINGS, dtype=np.int64)
    alive_sectors = np.zeros(K.RINGS, dtype=np.int64)
    reads = np.zeros(K.RINGS, dtype=np.int64)
    scan = np.zeros(K.RINGS, dtype=np.int64)
    for part in np.array_split(np.arange(n), min(ls.CHUNKS, max(1, n))):
        sub = np.ascontiguousarray(a.anchors[part])
        counters = np.zeros((len(sub), len(K.RING_COUNTERS)), dtype=np.int64)
        per = [np.zeros((len(sub), K.RINGS), dtype=np.int32) for _ in range(3)]
        rings = K.funnel_rings(a.z, sub, a.res, a.gain, a.cap, a.offset, big_k, counters, *per)
        if not np.array_equal(rings, a.rings[part]):
            raise SelfCheckError("funnel_rings differs from ref_free_rings")
        totals += counters.sum(axis=0)
        alive_anchors += np.array([(counters[:, 0] >= k).sum() for k in range(1, K.RINGS + 1)], dtype=np.int64)
        alive_sectors += per[0].sum(axis=0, dtype=np.int64)
        reads += per[1].sum(axis=0, dtype=np.int64)
        scan += per[2].sum(axis=0, dtype=np.int64)
    result = {name: int(v) for name, v in zip(K.RING_COUNTERS, totals)}
    result["alive_sector_scan_reads"] = int(scan.sum())
    result["need_max"] = big_k
    result["per_ring"] = {"alive_anchors": alive_anchors.tolist(), "alive_sectors": alive_sectors.tolist(),
                          "pixel_reads": reads.tolist(), "alive_sector_scan_reads": scan.tolist()}
    result["rings_max_histogram"] = np.bincount(a.rings.max(axis=1), minlength=K.RINGS + 1).tolist() \
        if n else [0] * (K.RINGS + 1)
    return result


def box_visits(a, size: int) -> int:
    """Visits of the pair search if its cells were size pixels: the useful anchors in the
    box of cells around each todo anchor (prefix sums over the cells)."""
    size = max(1, int(size))
    cells_x, cells_y = a.z.shape[1] // size + 1, a.z.shape[0] // size + 1
    reach = int(a.max_length / a.res) // size + 1
    keys = (a.anchors[a.useful, 0] // size) * cells_x + a.anchors[a.useful, 1] // size
    grid = np.bincount(keys, minlength=cells_y * cells_x).reshape(cells_y, cells_x).astype(np.int64)
    prefix = np.zeros((cells_y + 1, cells_x + 1), dtype=np.int64)
    prefix[1:, 1:] = grid.cumsum(axis=0).cumsum(axis=1)
    cy, cx = a.anchors[a.todo_all, 0] // size, a.anchors[a.todo_all, 1] // size
    y0, y1 = np.maximum(0, cy - reach), np.minimum(cells_y, cy + reach + 1)
    x0, x1 = np.maximum(0, cx - reach), np.minimum(cells_x, cx + reach + 1)
    return int((prefix[y1, x1] - prefix[y0, x1] - prefix[y1, x0] + prefix[y0, x0]).sum())


def log2_histogram(values: np.ndarray) -> Dict[str, int]:
    """Counts of 0, 1, 2-3, 4-7, ..."""
    values = np.asarray(values, dtype=np.int64)
    out = {"0": int((values == 0).sum())}
    positive = values[values > 0]
    if len(positive):
        bins = np.floor(np.log2(positive)).astype(np.int64)
        for b, n in enumerate(np.bincount(bins)):
            if n:
                out[f"{2 ** b}-{2 ** (b + 1) - 1}" if b else "1"] = int(n)
    return out


def analyse_call(folder: str, sample_every: int = 1) -> Dict:
    """Everything of one captured call (see the module docstring)."""
    inputs, params, timings = load_call(folder)
    a = rebuild(inputs, params)
    chunks = self_check(a, folder, sample_every)
    rings = ring_work(a)

    counters = np.zeros(K.N_COUNTERS, dtype=np.int64)
    sim = np.zeros(K.N_ORDERS, dtype=np.int64)
    hist = np.zeros(K.N_HIST, dtype=np.int64)
    visits_q, tests_q, found_q = [], [], []
    splits = {t: [0.0, 0.0, 0.0, 0.0] for t in THREAD_SPLITS}  # sum of max, sum of mean: visits, tests
    for todo, ref_counts, c, s, h in chunks:
        counters += c.sum(axis=0)
        sim += s.sum(axis=0)
        hist += h.sum(axis=0)
        visits_q.append(c[:, K.C_VISITS])
        tests_q.append(c[:, K.C_TESTS])
        found_q.append(c[:, K.C_FOUND])
        for t in THREAD_SPLITS:  # numba's static split of the prange into equal blocks
            for n, work in enumerate((c[:, K.C_VISITS], c[:, K.C_TESTS])):
                blocks = [int(b.sum()) for b in np.array_split(work, t)]
                splits[t][2 * n] += max(blocks)
                splits[t][2 * n + 1] += sum(blocks) / t
    visits_q, tests_q, found_q = (np.concatenate(v) if v else np.zeros(0, dtype=np.int64)
                                  for v in (visits_q, tests_q, found_q))

    pairs = {name: int(counters[k]) for name, k in PAIR_COUNTERS.items()}
    if pairs["visits"] != sum(pairs[name] for _, name in REJECTIONS) + pairs["found"]:
        raise SelfCheckError(f"{folder}: visits are not the rejections plus the found pairs")
    with_lines = found_q > 0
    result = {
        "params": params, "timings": timings, "sample_every": sample_every,
        "anchors": len(a.anchors), "open": len(a.useful), "todo": len(a.todo_all),
        "cell": a.cell, "need_min": a.need_min, "need_max": rings["need_max"],
        "rings": rings,
        "pairs": pairs,
        "skip_alone": {r: int(counters[K.C_SKIP + n]) for n, r in enumerate(RULES)},
        "skip_cumulative": {r: int(counters[K.C_CUM + n]) for n, r in enumerate(RULES)},
        "skip_unsafe": {r: int(counters[K.C_UNSAFE + n]) for n, r in enumerate(RULES)},
        "box_visits": {"L/4": box_visits(a, int(a.max_length / a.res) // 4),
                       "L/8": box_visits(a, int(a.max_length / a.res) // 8),
                       "L/16": box_visits(a, int(a.max_length / a.res) // 16), "64 px": box_visits(a, 64)},
        "work": {
            "anchors_with_lines": int(with_lines.sum()),
            "visits_of_anchors_with_lines": int(visits_q[with_lines].sum()),
            "line_ok_tests_of_anchors_with_lines": int(tests_q[with_lines].sum()),
            "found_per_anchor": log2_histogram(found_q),
            "static_split": {str(t): {"visits_max": v[0], "visits_mean": v[1], "tests_max": v[2],
                                      "tests_mean": v[3]} for t, v in splits.items()},
        },
        "orders": {name: int(sim[n]) for n, name in enumerate(K.ORDERS)},
        "first_failure": {
            "checked": {cls: int(hist[K.H_CHECKED + n]) for n, cls in enumerate(CLASSES)},
            "passed": {cls: int(hist[K.H_PASS + n]) for n, cls in enumerate(CLASSES)},
            "distance_log2": {cls: hist[K.H_LOG + n * K.LOG_BINS:K.H_LOG + (n + 1) * K.LOG_BINS].tolist()
                              for n, cls in enumerate(CLASSES)},
            "screened": {cls: {"inside": int(hist[K.H_ZONE + 2 * n]), "outside": int(hist[K.H_ZONE + 2 * n + 1])}
                         for n, cls in enumerate(CLASSES)},
            "end": {"higher": int(hist[K.H_END]), "lower": int(hist[K.H_END + 1]),
                    "neither": int(hist[K.H_END + 2])},
        },
    }
    if pairs["sim_mismatch"] or pairs["sampled_line_ok_tests"] != result["orders"]["ends_inward"]:
        raise SelfCheckError(f"{folder}: the simulated pixel tests differ from _line_ok's")
    return result


def summed(results: List[Dict]) -> Dict:
    """The counters of all calls added up (nested dicts and lists of numbers)."""
    def add(x, y):
        if isinstance(x, dict):
            return {k: add(x[k], y[k]) if k in y else x[k] for k in x} | {k: v for k, v in y.items() if k not in x}
        if isinstance(x, list):
            return [add(u, v) for u, v in zip(x, y)]
        if isinstance(x, (int, float)) and not isinstance(x, bool):
            return x + y
        return x
    skip = ("params", "timings", "sample_every", "cell", "need_min", "need_max")
    total = None
    for r in results:
        part = {k: v for k, v in r.items() if k not in skip}
        part["rings"] = {k: v for k, v in part["rings"].items() if k != "need_max"}
        part["work"] = {k: v for k, v in part["work"].items() if k != "found_per_anchor"}
        total = part if total is None else add(total, part)
    return total or {}


def pct(n, d) -> str:
    return f"{100 * n / d:.1f}%" if d else "-"


def report(name: str, r: Dict) -> List[str]:
    """The Markdown of one call (or of the sum)."""
    p = r["pairs"]
    lines = [f"## {name}", ""]
    if r.get("params"):
        q = r["params"]
        lines += [f"res {q['res']} m, length {q['min_length']}-{q['max_length']} m, "
                  f"{'sag' if q['sag'] else 'formula'}, cell {r['cell']} px, need_min {r['need_min']}, "
                  f"largest need {r['need_max']}; {q['step']}", ""]
    if r.get("timings"):
        lines += ["| Bar | wall s | CPU s |", "| --- | ---: | ---: |"]
        for stage, (w, c) in r["timings"]["stages"].items():
            lines.append(f"| {stage} | {w:.2f} | {c:.2f} |")
        lines.append("")
    lines += ["### Funnel", "", "| Stage | in | out | kept |", "| --- | ---: | ---: | ---: |",
              f"| free directions (anchors → open) | {r['anchors']} | {r['open']} | {pct(r['open'], r['anchors'])} |",
              f"| todo (pairs start from) | {r['open']} | {r['todo']} | {pct(r['todo'], r['open'])} |"]
    left = p["visits"]
    for label, key in REJECTIONS:
        out = left - p[key]
        lines.append(f"| {label} | {left} | {out} | {pct(out, left)} |")
        left = out
    produced = p['candidates'] - p['N1_candidates'] - p['F8c_candidates']
    lines += ["", f"Visits {p['visits']}, candidates {p['candidates']} (production counts {produced}: N1 skips "
              f"{p['N1_candidates']} and F8c {p['F8c_candidates']} of them before the count), checked {p['checked']}, "
              f"found {p['found']}, `_line_ok` pixel tests {p['line_ok_tests']}.", "",
              "### Visits candidate rules would skip", "",
              "| Rule | alone | cumulative | checked pairs skipped (must be 0) |", "| --- | ---: | ---: | ---: |"]
    for rule in RULES:
        lines.append(f"| {rule} | {pct(r['skip_alone'][rule], p['visits'])} | "
                     f"{pct(r['skip_cumulative'][rule], p['visits'])} | {r['skip_unsafe'][rule]} |")
    lines += ["", f"F2a with the within-cell prefix: {pct(p['F2a_with_prefix'], p['visits'])}; F8c by the anchor's "
              f"own rings {pct(p['F8c_own_rings'], p['visits'])}, by the partners' masks "
              f"{pct(p['F8c_partners'], p['visits'])}, its per-partner parts after the cell rules: the anchor's "
              f"rings {pct(p['F8c_partner_own'], p['visits'])}, the partner's mask "
              f"{pct(p['F8c_partner_mask'], p['visits'])} (the mask alone skips {p['F8c_mask_candidates']} of the "
              f"{p['F8c_candidates']} candidates F8c skips).", "",
              "Visits by cell size: " + ", ".join(f"{k} {v}" for k, v in r["box_visits"].items()), ""]
    w = r["work"]
    lines += ["### Work held by the anchors that find lines (F1)", "",
              f"{w['anchors_with_lines']} of {r['todo']} todo anchors find a line; they hold "
              f"{pct(w['visits_of_anchors_with_lines'], p['visits'])} of the visits and "
              f"{pct(w['line_ok_tests_of_anchors_with_lines'], p['line_ok_tests'])} of the pixel tests "
              "(what a writing pass restricted to them repeats).", ""]
    if "found_per_anchor" in w:
        lines += ["Found per anchor: " + ", ".join(f"{k}: {v}" for k, v in w["found_per_anchor"].items()), ""]
    lines += ["| Threads | visits: mean/max of blocks | tests: mean/max |", "| ---: | ---: | ---: |"]
    for t, v in w["static_split"].items():
        lines.append(f"| {t} | {pct(v['visits_mean'], v['visits_max'])} | {pct(v['tests_mean'], v['tests_max'])} |")
    g = r["rings"]
    lines += ["", "### Free directions", "",
              f"Rings {g['rings']}, beyond the largest need {g['rings_beyond_need']}; pixel reads "
              f"{g['pixel_reads']}, of them within the alive sectors {g['alive_sector_scan_reads']} "
              f"({pct(g['alive_sector_scan_reads'], g['pixel_reads'])}); atan2 {g['atan2']}, of them with all "
              f"marked sectors dead {g['atan2_dead']} ({pct(g['atan2_dead'], g['atan2'])}).", "",
              "| Ring | alive anchors | mean alive sectors | reads | alive-sector reads |",
              "| ---: | ---: | ---: | ---: | ---: |"]
    per = g["per_ring"]
    for k in range(K.RINGS):
        if k < 8 or k % 8 == 7:
            n = per["alive_anchors"][k]
            lines.append(f"| {k + 1} | {n} | {per['alive_sectors'][k] / n if n else 0:.1f} | "
                         f"{per['pixel_reads'][k]} | {per['alive_sector_scan_reads'][k]} |")
    hist = g["rings_max_histogram"]
    lines += ["", "Largest ring per anchor: " + ", ".join(f"{k}: {n}" for k, n in enumerate(hist) if n), ""]
    o, f = r["orders"], r["first_failure"]
    lines += ["### `_line_ok` pixel orders (sampled anchors)", "", "| Order | pixel tests | vs today |",
              "| --- | ---: | ---: |"]
    for name, n in o.items():
        lines.append(f"| {name} | {n} | {pct(n, o['ends_inward'])} |")
    lines += ["", "First failing pixel (today's order), distance from the nearer end:", "",
              "| Length | checked | passed | inside screened zone | outside | " +
              " | ".join(f"d {2 ** b}-{2 ** (b + 1) - 1}" for b in range(10)) + " | d >= 1024 |",
              "| --- | " + " | ".join(["---:"] * 15) + " |"]
    for cls in CLASSES:
        d = f["distance_log2"][cls]
        lines.append(f"| {cls} | {f['checked'][cls]} | {f['passed'][cls]} | {f['screened'][cls]['inside']} | "
                     f"{f['screened'][cls]['outside']} | " + " | ".join(str(n) for n in d[:10]) +
                     f" | {sum(d[10:])} |")
    e = f["end"]
    lines += ["", f"At the higher anchor's end {e['higher']}, the lower {e['lower']}, neither {e['neither']}.", ""]
    return lines


def analyse(folders: List[str], out: str, sample_every: int, threads: Optional[int]) -> Dict:
    if threads:
        numba.set_num_threads(threads)
    os.makedirs(out, exist_ok=True)
    names = [os.path.basename(os.path.normpath(f)) for f in folders]
    if len(set(names)) < len(names):  # calls of several captures: their paths
        names = [os.path.normpath(f) for f in folders]
    results = {name: analyse_call(f, sample_every) for name, f in zip(names, folders)}
    data = {"calls": results, "sum": summed(list(results.values()))}
    with open(os.path.join(out, "funnel.json"), "w") as f:
        json.dump(data, f, indent=1)
    md = ["# Line search funnel", ""]
    if len(results) > 1:
        md += report("All calls", data["sum"])
    for name, r in results.items():
        md += report(name, r)
    with open(os.path.join(out, "funnel.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(md))
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    cap = sub.add_parser("capture", help="run a search and save the inputs of its line searches")
    cap.add_argument("--out", required=True, help="folder for call-<k>/")
    cap.add_argument("--calls", default="0", help="the calls to save: indices (0,1) or 'all' (default 0)")
    cap.add_argument("args", nargs=argparse.REMAINDER, help="-- and the options of findaline.py")
    ana = sub.add_parser("analyse", help="count the funnel of captured calls")
    ana.add_argument("calls", nargs="+", help="call-<k> folders of a capture")
    ana.add_argument("--out", required=True, help="folder for funnel.json and funnel.md")
    ana.add_argument("--sample-every", type=int, default=1,
                     help="simulate the pixel orders for every M-th todo anchor only (default 1: all)")
    ana.add_argument("--threads", type=int, help="numba threads (default: numba's)")
    args = parser.parse_args()
    if args.command == "capture":
        search_args = args.args[1:] if args.args[:1] == ["--"] else args.args
        calls = None if args.calls == "all" else [int(c) for c in args.calls.split(",")]
        sys.exit(capture(args.out, calls, search_args))
    data = analyse(args.calls, args.out, max(1, args.sample_every), args.threads)
    total = data["sum"]["pairs"]
    print(f"visits {total['visits']}, candidates {total['candidates']}, checked {total['checked']}, "
          f"found {total['found']}; {os.path.join(args.out, 'funnel.md')}")


if __name__ == "__main__":
    main()
