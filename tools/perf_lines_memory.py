"""
Run by hand: the memory of the lines of a search per line (docs/performance.md; search.LINE_BYTES).

Two modes, both measuring the traced heap (tracemalloc) above what was there before, divided by
the number of lines (and for step 3 also by the pairs found), with the code of --repo (this
checkout, or another one, e.g. an older version):

--call <folder>: a captured call of tools/perf_line_funnel.py (call-<k>/inputs.npz and params.json)
run through steps 3, 4 and 5 as search._lines and save_run do:
    step 3 peak     linesearch.find_valid_lines (pair search, evaluation, joining, sorting)
    lines found     its output, as step 3 hands it to step 4
    coordinates     the peak of step 4's coordinates, the tile core's lines (a call with `first`:
                    the core is the box of its first anchors) and the metres over water (a
                    mask of the lowest tenth of the grid)
    groups          the peak of mapping.group_lines
    profiles        the peak of the representatives' profiles (lineprofiles.line_profiles)
    held            the lines with their coordinates and groups, as a finished tile keeps them
    step 5 peak     save_results and save_map of all of them
A first call on a few thousand anchors loads the numba code before the measurement.

--tiles <run>/tiles: the lines of a tiled run (its tiles/<k>.table.pkl.gz) through steps 4 and 5
(--legacy: the code of --repo keeps a dict per line):
    tiles held      the tiles' tables loaded, as search_lines holds them before the join (not --legacy)
    join peak       the join of their lines (LineTable.join; concat in a version without it)
    joined          the joined table alone
then, from the joined columns again:
    lines found    the output of the line search (find_valid_lines)
    step 4 peak     coordify and group_lines over them (the peak of a tile's step 4, the grids apart)
    held            the lines with their coordinates, as a finished tile keeps them
    step 5 peak     save_results and save_map of all of them

The grids of a tile are not included (search.PIXEL_BYTES), nor the profiles of a circle's every
line (search.PROFILE_POINT_BYTES: measure them with perf_profile.py --tracemalloc).

    uv run tools/perf_lines_memory.py --call <capture>/call-0 --out <scratch> [--repo <checkout>] [--json <file>]
    uv run tools/perf_lines_memory.py --tiles <run>/tiles --out <scratch> [--repo <checkout> --legacy]
"""

import argparse
import glob
import gzip
import json
import os
import pickle
import sys
import time
import tracemalloc

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class _Table:
    """A tile's helpers.LineTable read without this checkout's helpers (another --repo)."""


class _Unpickler(pickle.Unpickler):
    def find_class(self, module, name):
        return _Table if name == "LineTable" else super().find_class(module, name)


class _Area:
    center = (36.05, 14.25)

    @staticmethod
    def shape_wgs84():
        from shapely.geometry import Point
        return Point(14.25, 36.05).buffer(0.05)


class _Marks:
    """The traced bytes above the start, per line, by name."""

    def __init__(self):
        tracemalloc.start()
        self.base = tracemalloc.get_traced_memory()[0]
        self.bytes = {}

    def mark(self, name, peak=False):
        current, top = tracemalloc.get_traced_memory()
        self.bytes[name] = (top if peak else current) - self.base
        tracemalloc.reset_peak()


def _save(np, sh, mp, rn, found, groups, out, n):
    os.makedirs(out, exist_ok=True)
    run = {"id": "r", "name": "memory", "created": "2026-10-31T10:00:00+00:00"}
    rn.save_results(out, found, groups, {"name": "memory", "summary": {"lines": n}})
    mp.save_map(found, _Area, out, os.path.join(out, "runs"), run, "EPSG:32633")


def load_call(folder):
    """The inputs and parameters of a captured call (as tools/perf_line_funnel.py load_call)."""
    import numpy as np
    with np.load(os.path.join(folder, "inputs.npz")) as data:
        inputs = {name: data[name] for name in data.files}
    with open(os.path.join(folder, "params.json")) as f:
        params = json.load(f)
    return inputs, params


def call_arguments(inputs, params):
    """find_valid_lines' arguments of the call (perf_line_funnel's sag_table_of without its import)."""
    from types import SimpleNamespace

    import helpers as sh
    import sag as sg
    table = None
    if params["sag"]:
        if "sag_sag" in inputs:
            table = SimpleNamespace(spans=inputs["sag_spans"], sag=inputs["sag_sag"],
                                    fractions=inputs["sag_fractions"], RATIOS=sg.EnvelopeTable.RATIOS,
                                    rig=sg.Rigging(**params["rigging"]))
        else:
            table = sg.EnvelopeTable(sg.Rigging(**params["rigging"]), params["sag_min_span"], params["sag_max_span"])
    limits = params["limits"]
    return dict(elevation=inputs["elevation"], surface=inputs.get("surface"), anchors=inputs["anchors"],
                res=params["res"], min_length=params["min_length"], max_length=params["max_length"],
                nmpt_mode=params["nmpt_mode"], threads=params["threads"], sag_table=table,
                max_dh_ratio=params["max_dh_ratio"], max_dh=params["max_dh"], first=inputs.get("first"),
                high_above=params["high_above"],
                limits=sh.LineLimits(**{k: v for k, v in limits.items() if k != "left_out"}) if limits else None,
                anchor_values=inputs.get("anchor_values"), strong=inputs.get("strong"))


def measure_call(folder, out):
    import numpy as np
    import grid as gd
    import helpers as sh
    import lineprofiles as lp
    import linesearch as ls
    import mapping as mp
    import runs as rn
    import search
    inputs, params = load_call(folder)
    args = call_arguments(inputs, params)
    z, res = args["elevation"], args["res"]
    grid = gd.Grid(left=430000.0, top=3990000.0, res=res, height=z.shape[0], width=z.shape[1], crs="EPSG:32633")
    low = np.nanpercentile(z, 10)
    water = np.asarray(z < low)  # a mask with lines over it
    core = None
    if args["first"] is not None:
        x, y = grid.pixel_to_xy(args["anchors"][args["first"], 0], args["anchors"][args["first"], 1])
        core = (x.min() - res / 2, y.min() - res / 2, x.max() + res / 2, y.max() + res / 2)
    in_place = hasattr(search, "line_coordinates")

    def step4(lines):
        if in_place:
            return search.line_coordinates(lines, grid, args["nmpt_mode"], res, water, None, core)
        results = mp.coordify(lines, grid, args["nmpt_mode"])  # the code of before wave 4
        if core is not None:
            left, bottom, right, top = core
            x, y = mp.first_anchor(results).T
            results = results.take((left <= x) & (x < right) & (bottom <= y) & (y < top))
        a1, a2 = results.columns["a1"], results.columns["a2"]
        results.columns["water_m"] = np.array(ls.covered_metres(a1, a2, res, water), dtype=np.float64)
        results.columns["filled_m"] = np.array(ls.covered_metres(a1, a2, res, None), dtype=np.float64)
        return results

    def profiles(results, groups):
        wanted = np.unique(groups.rep)
        a1, a2 = results.columns["a1"], results.columns["a2"]
        batch = lp.line_profiles(a1[wanted], a2[wanted], z, res, args["surface"], sag_table=args["sag_table"],
                                 water=water)
        results.profiles.update(zip(wanted.tolist(), map(batch.__getitem__, range(len(wanted)))))

    # Warm-up: the numba code of every step on a few thousand anchors
    small = dict(args, anchors=args["anchors"][:3000])
    for name in ("first", "anchor_values", "strong"):
        if small[name] is not None:
            small[name] = small[name][:3000]
    small["limits"] = call_arguments(inputs, params)["limits"]
    warm = step4(ls.find_valid_lines(**small))
    if len(warm):
        profiles(warm, mp.group_lines(warm, 20, "clearance"))
    del warm

    stats, seconds = {}, {}
    marks = _Marks()
    t = time.time()
    lines = ls.find_valid_lines(**args, stats=stats)
    seconds["step 3"] = time.time() - t
    marks.mark("step 3 peak", peak=True)
    marks.mark("lines found")
    valid = len(lines)
    t = time.time()
    results = step4(lines)
    del lines
    marks.mark("coordinates", peak=True)
    groups = mp.group_lines(results, 20, "clearance")
    marks.mark("groups", peak=True)
    profiles(results, groups)
    marks.mark("profiles", peak=True)
    seconds["step 4"] = time.time() - t
    marks.mark("held")
    t = time.time()
    _save(np, sh, mp, rn, results, groups, out, len(results))
    seconds["step 5"] = time.time() - t
    marks.mark("step 5 peak", peak=True)
    tracemalloc.stop()
    kept = len(results)
    report = {"call": folder, "repo": os.path.dirname(os.path.abspath(search.__file__)), "found": stats["found"],
              "valid": valid, "core lines": kept, "groups": len(groups), "seconds": seconds,
              "bytes": marks.bytes,
              "per line": {k: v / max(valid if k in ("step 3 peak", "lines found", "coordinates") else kept, 1)
                           for k, v in marks.bytes.items()},
              "step 3 peak per found pair": marks.bytes["step 3 peak"] / max(stats["found"], 1)}
    print(f"{stats['found']} pairs found, {valid} valid lines, {kept} in the core, {len(groups)} groups; "
          + ", ".join(f"{k} {v:.1f} s" for k, v in seconds.items()))
    for name, value in report["per line"].items():
        print(f"  {name:12} {value:8.0f} bytes per line ({marks.bytes[name] / 2 ** 20:8.1f} MiB)")
    print(f"  step 3 peak  {report['step 3 peak per found pair']:8.0f} bytes per found pair")
    return report


def measure_tiles(args):
    import numpy as np
    import grid as gd
    import helpers as sh
    import mapping as mp
    import runs as rn

    # The join of the tiles' lines as search.search_lines does it (LineTable.join, or concat before)
    join = {}
    if not args.legacy:
        joining = _Marks()
        tables = []
        for path in sorted(glob.glob(os.path.join(args.tiles, "*.table.pkl.gz"))):
            with gzip.open(path, "rb") as f:
                table = _Unpickler(f).load()
            tables.append(sh.LineTable(table.columns, table.profiles))
            del table
        joining.mark("tiles held")
        joined = (sh.LineTable.join if hasattr(sh.LineTable, "join") else sh.LineTable.concat)(tables)
        joining.mark("join peak", peak=True)
        del tables
        joining.mark("joined")
        tracemalloc.stop()
        join = {name: value / max(len(joined), 1) for name, value in joining.bytes.items()}
        print(f"{len(joined)} lines joined: " + ", ".join(f"{k} {v:.0f}" for k, v in join.items()) + " bytes per line")
        del joined
    tables = []
    for path in sorted(glob.glob(os.path.join(args.tiles, "*.table.pkl.gz"))):
        with gzip.open(path, "rb") as f:
            table = _Unpickler(f).load()
        if len(table.columns["a1"]):
            tables.append(table)
    a1 = np.concatenate([t.columns["a1"] for t in tables])
    a2 = np.concatenate([t.columns["a2"] for t in tables])
    values = {k: np.concatenate([t.columns[k] for t in tables]) for k in sh.Line._fields[2:]}
    some_profile = next(p for t in tables for p in t.profiles.values())
    del tables
    n = len(a1)
    grid = gd.Grid(left=430000.0, top=3990000.0, res=1.0, height=int(a1[:, 0].max()) + 1,
                   width=int(a1[:, 1].max()) + 1, crs="EPSG:32633")

    os.makedirs(args.out, exist_ok=True)
    marks = _Marks()
    # The output of the line search
    if args.legacy:
        names = sh.Line._fields[2:]
        lines = [sh.Line(tuple(p), tuple(q), *v[:4], None if v[4] != v[4] else v[4], *v[5:])
                 for p, q, *v in zip(a1.tolist(), a2.tolist(), *(values[k].tolist() for k in names))]
    else:
        lines = sh.LineTable({"a1": a1.copy(), "a2": a2.copy(), **{k: v.copy() for k, v in values.items()}})
    del a1, a2, values
    marks.mark("lines found")
    t = time.time()
    # Step 4: coordinates, metres over water and gaps, groups, the representatives' profiles
    if args.legacy:
        found = mp.coordify(lines, grid, "mark")
        for r in found:
            r["water_m"], r["filled_m"], r["profile"] = 0.0, 0.0, None
        groups = mp.group_lines(found, 20, "clearance")
        for g in groups:
            g["rep"]["profile"] = some_profile
    else:
        found = mp.coordify(lines, grid, "mark")
        found.columns["water_m"] = np.zeros(n)
        found.columns["filled_m"] = np.zeros(n)
        groups = mp.group_lines(found, 20, "clearance")
        found.profiles = {k: some_profile for k in groups.rep.tolist()}
    marks.mark("step 4 peak", peak=True)
    del lines
    marks.mark("held")
    step4 = time.time() - t
    t = time.time()
    meta = {"name": "memory", "summary": {"lines": n}}
    run = {"id": "r", "name": "memory", "created": "2026-10-31T10:00:00+00:00"}
    if args.legacy:
        rn.save_results(args.out, groups, meta)
    else:
        rn.save_results(args.out, found, groups, meta)
    mp.save_map(found, _Area, args.out, os.path.join(args.out, "runs"), run, "EPSG:32633")
    marks.mark("step 5 peak", peak=True)
    print(f"{n} lines, {len(groups)} groups ({'dicts' if args.legacy else 'columns'}"
          f"): step 4 {step4:.1f} s, "
          f"step 5 {time.time() - t:.1f} s")
    for name, value in marks.bytes.items():
        print(f"  {name:12} {value / n:8.0f} bytes per line")
    return {"tiles": args.tiles, "lines": n, "bytes": marks.bytes, "join per line": join}


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--call", help="a captured call of tools/perf_line_funnel.py (its call-<k> folder)")
    source.add_argument("--tiles", help="the tiles folder of a tiled run of this version")
    parser.add_argument("--out", required=True, help="a scratch folder for the saved files")
    parser.add_argument("--repo", default=HERE, help="the checkout whose code is measured")
    parser.add_argument("--legacy", action="store_true", help="--tiles: the code of --repo keeps a dict per line")
    parser.add_argument("--json", help="also write the results to this file")
    args = parser.parse_args()
    sys.path.insert(0, args.repo)
    report = measure_call(args.call, args.out) if args.call else measure_tiles(args)
    if args.json:
        with open(args.json, "w") as f:
            json.dump(report, f, indent=1)


if __name__ == "__main__":
    main()
