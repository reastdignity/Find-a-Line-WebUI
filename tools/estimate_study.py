"""
Run by hand: the size of a search estimated from a sample before its pairs (search.sample_estimate, the web
worker's estimate: docs/line-volume/spec-search.md section 2) against the exact count, per case, fraction and
seed, in both designs: the anchors (the lines found; part P4's study of the line-volume task) and the squares
of the square rule (the lines kept; part M2's). Offline from the cache: nothing written but --out; nothing of
the search changed (it calls the search's own functions, one call per design, fraction, seed and tile, where
the studies counted every estimate of a tile from one pair search).

    python tools/estimate_study.py [--fractions 0.005,0.01,0.02,0.05] [--seeds 5] [--seed-rule study|search]
        [--designs anchors,squares] [--square 5] [--exact] [--limit 1500000] [--name NAME] [--out F.json]
        -- <findaline.py options of the search, with its --data-dir>

Seeds: "study" (the default) draws as the studies did, numpy default_rng([1000 + s, tile]) for the anchors
and default_rng([2000 + s, tile]) for the squares, s = 0 .. --seeds - 1, so their rows can be reproduced;
"search" takes the search's own seed (the first 8 hex digits of search._search_hash of the plan in that
design: one seed, the estimate a job of the web worker gets). The squares design is the plan with
--same-line-square (the search's own value, else --square), the anchors design the plan without it. Step 1
runs once; a tiled area takes each tile's window (search._tile_data) and its anchors as the search does, and
sums its tiles. --exact adds one pair search from every useful anchor of each core: the lines found (the
anchors design at a fraction of 1 gives the same number), the lines kept after the join (the distinct pairs
of squares of all tiles), the tiles' kept lines before the join (what a tiled search's limit counts) and the
keys seen from their first square (the squares design at a fraction of 1).

Writes --out (JSON, written whole and then renamed: the settings without the place, the tiles with the units
of each, a row per design, fraction and seed: the estimate, its standard error and interval of two standard
errors, k of n units, seconds, with --exact the ratio to the exact count (found lines for the anchors, kept
lines after the join for the squares) and with --limit the band's verdict (refused over 1.25 times it,
"close" from 0.8 times, else "on"), the exact counts) and prints a table. No coordinates are written or
printed (the search's header is not printed).

In Python (cwd or sys.path: the repository; `sys.path.insert(0, "tools")`):

    import estimate_study as es
    result = es.study(params, data_dir, fractions=(0.02,), seeds=5, seed_rule="study", exact=True)
    result["rows"], result["exact"], result["tiles"]
"""

import argparse
import contextlib
import dataclasses
import gc
import io
import json
import math
import os
import shutil
import sys
import time
from typing import Dict, List, Optional, Sequence

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

FRACTIONS = (0.005, 0.01, 0.02, 0.05)  # the studies' (parts P4 and M2)
SEEDS = 5
SQUARE = 5  # the squares design's --same-line-square when the search has none (the studies' and the advice's)
STUDY_SEEDS = {"anchors": 1000, "squares": 2000}  # the studies' streams: default_rng([base + s, tile])
DESIGNS = ("anchors", "squares")
# Settings never written: where the search is (and its files)
PLACE = ("lat", "lon", "northing", "easting", "point", "area", "geometry", "within", "name", "elevation_file",
         "surface_file", "opentopo_key")


def _quiet(kind: str, text: str):
    """on_event of the tool's plans: nothing is printed (the header names the centre)."""


def designed(plan, design: str, square: float = SQUARE):
    """The plan of a design: the anchors without the square rule, the squares with it (the search's own
    value when it has one, else `square`)."""
    p = plan.params
    value = 0 if design == "anchors" else (p.same_line_square or square)
    return dataclasses.replace(plan, params=p.model_copy(update={"same_line_square": value}))


def seeds_of(rule: str, plan, design: str, seeds: int) -> List[int]:
    """The seeds of a design: the studies' (base + s) or the search's own (one) of the design's plan."""
    import search
    if rule == "search":
        return [int(search._search_hash(plan)[:8], 16)]
    if rule != "study":
        raise ValueError(f"unknown seed rule {rule!r} (study or search)")
    return [STUDY_SEEDS[design] + s for s in range(seeds)]


def verdict(estimate: float, limit: Optional[int]) -> Optional[str]:
    """The band of search._estimate_check on one limit: "refused", "close" or "on" (None without a limit)."""
    import search
    if not limit:
        return None
    return "refused" if estimate > search.REFUSE_FACTOR * limit else \
        "close" if estimate >= search.ACCEPT_FACTOR * limit else "on"


class _Exact:
    """The exact pass of a tile (a sink of search._pair_search from every useful anchor of its core): the
    lines found, the keys of the square rule in the tile and over the area, and those seen from their first
    square."""

    def __init__(self, side: float):
        import search
        self.side, self.found, self.kept_tiles, self.from_ka = side, 0, 0, 0
        self.area = search._KeySet()
        self.grid = self.tile = self.first = None

    def start(self, grid):
        import search
        self.grid, self.tile, self.first = grid, search._KeySet(), search._KeySet()

    def __call__(self, part):
        import samelines
        c = part.columns
        if not len(part):
            return
        self.found += len(part)
        x1, y1 = self.grid.pixel_to_xy(c["a1"][:, 0], c["a1"][:, 1])
        x2, y2 = self.grid.pixel_to_xy(c["a2"][:, 0], c["a2"][:, 1])
        one = (x1 < x2) | ((x1 == x2) & (y1 <= y2))
        xa, ya = np.where(one, x1, x2), np.where(one, y1, y2)
        ka, kb = samelines.square_keys(xa, ya, np.where(one, x2, x1), np.where(one, y2, y1), self.side)
        own = (np.floor(xa / self.side).astype(np.int64) << 32) + np.floor(ya / self.side).astype(np.int64)
        mine = ka == own
        self.tile.add(ka, kb)
        self.area.add(ka, kb)
        self.first.add(ka[mine], kb[mine])

    def finish(self):
        self.kept_tiles += len(self.tile.pairs()[0])
        self.from_ka += len(self.first.pairs()[0])
        self.tile = self.first = None

    def result(self) -> Dict[str, int]:
        return {"found": self.found, "kept": len(self.area.pairs()[0]), "kept_tiles": self.kept_tiles,
                "from_ka": self.from_ka}


def study(params, data_dir: str, fractions: Sequence[float] = FRACTIONS, seeds: int = SEEDS,
          seed_rule: str = "study", designs: Sequence[str] = DESIGNS, square: float = SQUARE,
          exact: bool = False, limit: Optional[int] = None) -> Dict:
    """The study of one search (params.SearchParams, data_dir its data folder): see the module's docstring.
    Returns {"settings", "tiles", "per_tile", "rows", "exact", "seconds"}."""
    import cache
    import samelines
    import search
    started = time.monotonic()
    paths = search.Paths(data_dir, cache.new_work(data_dir))
    plan = search.plan_search(params, paths, _quiet)
    p = plan.params
    table = search._sag_table(dataclasses.astuple(plan.rigging), p.min_length, p.max_length) \
        if p.model == "sag" else None
    plans = {d: designed(plan, d, square) for d in designs}
    streams = {d: seeds_of(seed_rule, plans[d], d, seeds) for d in designs}
    sums = {(d, f, s): [0.0, 0.0, 0, 0, 0.0] for d in designs for f in fractions for s in streams[d]}
    side = samelines.side(plans["squares"].params.same_line_square if "squares" in plans else square,
                          plan.resolution)
    counter = _Exact(side) if exact else None
    per_tile, seconds = [], {"exact": 0.0}

    def run(data, core, k: int, grid, work: Optional[str]):
        def of(d):
            if not plan.tiles:
                return plans[d]
            return dataclasses.replace(plans[d], grid=grid, paths=search.Paths(plan.paths.data, work), tiles=None)
        found = search._anchors(dataclasses.replace(of(designs[0]), funnel={}), data, quiet=True)
        tile = {"tile": k, "anchors": 0 if found is None else len(found.anchors)}
        per_tile.append(tile)
        if found is None:
            return
        for d in designs:
            for f in fractions:
                for s in streams[d]:
                    t = time.monotonic()
                    estimate, variance, kk, n = search.sample_estimate(of(d), data, found, core, table, k,
                                                                       fraction=f, seed=s)
                    row = sums[(d, f, s)]
                    row[0] += estimate
                    row[1] += variance
                    row[2] += kk
                    row[3] += n
                    row[4] += time.monotonic() - t
                    tile[d] = n
        if counter is not None:
            t = time.monotonic()
            counter.start(grid)
            with contextlib.redirect_stdout(io.StringIO()):
                search._pair_search(dataclasses.replace(of(designs[0]), funnel={}), data, found, core, table,
                                    sink=counter)  # a sink: never the square rule's reducer
            counter.finish()
            seconds["exact"] += time.monotonic() - t

    try:
        t = time.monotonic()
        if not plan.tiles:
            data = search.prepare_data(plan, statistics=False, shore="none")
            seconds["step1"] = time.monotonic() - t
            run(data, None, 0, plan.grid, None)
            del data
        else:
            area = search.prepare_data(plan, strips=True, statistics=False, shore="none")
            seconds["step1"] = time.monotonic() - t
            for k, (core, tile) in enumerate(plan.tiles):
                work = os.path.join(plan.paths.work, f"tile{k}")
                os.makedirs(work, exist_ok=True)
                data = search._tile_data(area, plan.grid, tile, work, None)
                run(data, core, k, tile, work)
                del data
                gc.collect()  # close the memory-mapped grids before deleting them (Windows)
                shutil.rmtree(work, ignore_errors=True)
            del area
            gc.collect()
            search._remove_grids(plan.paths.work)
    finally:
        gc.collect()
        cache.remove_work(paths.work)
    truth = counter.result() if counter is not None else None
    rows = []
    for (d, f, s), (estimate, variance, kk, n, took) in sums.items():
        se = math.sqrt(variance)
        row = {"design": d, "fraction": f, "seed": s, "estimate": int(round(estimate)), "se": int(round(se)),
               "lo": max(0, int(round(estimate - 2 * se))), "hi": int(round(estimate + 2 * se)), "k": kk, "n": n,
               "seconds": round(took, 2)}
        if truth is not None:
            true = truth["found" if d == "anchors" else "kept"]
            row["ratio"] = round(estimate / true, 4) if true else None
        if limit:
            row["verdict"] = verdict(estimate, limit)
        rows.append(row)
    seconds["wall"] = time.monotonic() - started
    settings = {k: v for k, v in p.model_dump().items() if k not in PLACE}
    return {"settings": settings, "side": side, "tiles": len(plan.tiles or []), "per_tile": per_tile, "rows": rows,
            "exact": truth, "limit": limit, "seed_rule": seed_rule,
            "seconds": {k: round(v, 1) for k, v in seconds.items()}}


def table_text(result: Dict, name: str = "") -> str:
    """The rows as a Markdown table, one line per design, fraction and seed."""
    lines = [f"# {name or 'estimate'}: {result['tiles'] or 'one grid'} tiles, exact {result['exact']}", "",
             "| design | fraction | seed | estimate | 2 SE interval | k of n | ratio | verdict | s |",
             "|---|---|---|---:|---|---|---|---|---:|"]
    for r in result["rows"]:
        lines.append(f"| {r['design']} | {r['fraction']:g} | {r['seed']} | {r['estimate']:,} | {r['lo']:,} - "
                     f"{r['hi']:,} | {r['k']:,} of {r['n']:,} | {r.get('ratio', '')} | {r.get('verdict') or ''} | "
                     f"{r['seconds']} |")
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None):
    argv = sys.argv[1:] if argv is None else argv
    own, search_argv = (argv[:argv.index("--")], argv[argv.index("--") + 1:]) if "--" in argv else (argv, [])
    parser = argparse.ArgumentParser(description="The estimate of a search's lines from a sample against the "
                                                 "exact count (tools/estimate_study.py).")
    parser.add_argument("--fractions", default=",".join(f"{f:g}" for f in FRACTIONS))
    parser.add_argument("--seeds", type=int, default=SEEDS)
    parser.add_argument("--seed-rule", choices=("study", "search"), default="study")
    parser.add_argument("--designs", default=",".join(DESIGNS))
    parser.add_argument("--square", type=float, default=SQUARE)
    parser.add_argument("--exact", action="store_true")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--name", default="")
    parser.add_argument("--out")
    args = parser.parse_args(own)
    if not search_argv:
        parser.error("give the search's options after --")
    import cache
    import params as pm
    searches, options = pm.parse_cli(search_argv + ["--no-plot", "--yes"])
    designs = tuple(d for d in args.designs.split(",") if d)
    if set(designs) - set(DESIGNS):
        parser.error(f"--designs: {', '.join(DESIGNS)}")
    result = study(searches[0], cache.data_dir(options.data_dir),
                   fractions=tuple(float(f) for f in args.fractions.split(",")), seeds=args.seeds,
                   seed_rule=args.seed_rule, designs=designs, square=args.square, exact=args.exact,
                   limit=args.limit)
    result["name"] = args.name
    print(table_text(result, args.name), flush=True)
    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out + ".partial", "w", encoding="utf-8") as f:
            json.dump(result, f, indent=1)
        os.replace(args.out + ".partial", args.out)
    return result


if __name__ == "__main__":
    from progress import utf8_output
    utf8_output()
    main()
