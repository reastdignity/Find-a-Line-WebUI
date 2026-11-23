"""tools/prune_study.py --ranges: the report of the square rule's ranges (step 2e) of two runs of one search, on a
made-up table (the four checks pass; a kept line missing, a wrong count and ranges drawn inward are each caught) and
on two searches of the Żabi Koń clip with the no-fall zone and A-frames (no miss)."""

import json
import os
import sys

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools"))

import prune_study as ps  # noqa: E402
import runs as rn  # noqa: E402
import samelines  # noqa: E402
from test_same_lines import SETTINGS, _grid, _search, _table  # noqa: E402


def _made_up(seed: int = 3):
    """(full, kept, side): every found line of a made-up search as a store gives its columns (the mean height and
    the A-frame heights at 2 decimals, some mean heights missing) and the reducer's kept lines of them."""
    grid, side = _grid(), 5.0
    table = _table(5000, seed)
    rng = np.random.default_rng(seed)
    c = table.columns
    n = len(table)
    c["height_mean"] = rn.round_floats(rng.random(n) * 50, 2)
    c["height_mean"][rng.random(n) < 0.1] = np.nan
    c["clearance"] = rng.random(n) * 20
    c["length"] = 30 + rng.random(n) * 100  # (the order's own steps decide too: _table's few lengths no longer)
    xy = lambda pixels: np.column_stack(grid.pixel_to_xy(pixels[:, 0], pixels[:, 1]))  # noqa: E731
    full = {"a1_xy": xy(c["a1"]), "a2_xy": xy(c["a2"]), **{v: c[v].copy() for v in ps.RANGE_VALUES}}
    reducer = samelines.BestPerSquarePair(side, grid)
    for index in np.array_split(rng.permutation(n), 7):
        reducer(table.take(index))
    kept = reducer.table()
    out = {"a1_xy": xy(kept.columns["a1"]), "a2_xy": xy(kept.columns["a2"])}
    out.update({name: v for name, v in kept.columns.items() if name not in ("a1", "a2")})
    return full, out, side


def test_ranges_check_of_a_made_up_table():
    """The four checks on a made-up search: the pairs are the kept lines with their counts, every lo / hi is the
    outward cast of its pair's least / most, no miss under 300 random filters (single bounds and two to four at
    once, the two A-frame switches never together), shares named too many between 0 and 100 %; a kept line left
    out, a count changed and ranges drawn in to the kept line's own value are each caught, the last as misses."""
    full, kept, side = _made_up()
    r = ps.ranges_check(full, kept, side, filters=300, seed=1)
    assert r["found"] == 5000 > r["kept"] == r["check1"]["pairs"] and r["check1"]["ok"]
    assert r["check2"]["ok"] and set(r["check2"]["wrong"]) == {f"{v}_{e}" for v in ps.RANGE_VALUES for e in ("lo", "hi")}
    assert r["check3"] == {"filters": 300, "seed": 1, "misses": 0, "ok": True}
    singles = [f for f in r["filters"] if len(f["filter"]) == 1]
    assert len(singles) == 20 * len(ps.RANGE_BOUNDS) and all(f["found_passing"] for f in singles[::5])
    assert not any({"liftMax", "liftMaxNoZone"} <= set(f["filter"]) for f in r["filters"])
    assert all(0 <= f["share_too_many_pct"] <= 100 for f in r["filters"] if f["share_too_many_pct"] is not None)
    assert any(f["named_too_many"] for f in r["filters"])  # a range names lines none of whose copies pass
    pooled = r["check4"]["all_filters"]["pooled_pct"]  # named too many over shown, summed over the filters
    assert pooled == round(100 * sum(f["named_too_many"] for f in r["filters"])
                           / sum(f["kept_shown"] for f in r["filters"]), 3) and 0 < pooled < 100
    assert ps.ranges_check(full, kept, side, filters=300, seed=1)["filters"] == r["filters"]  # the seed fixes them
    # broken kept lines
    dropped = {k: v[1:] for k, v in kept.items()}
    bad = ps.ranges_check(full, dropped, side, filters=10)
    assert not bad["check1"]["ok"] and bad["check1"]["found_without_kept"] > 0
    counted = {**kept, "stands_for": kept["stands_for"] + (np.arange(len(kept["stands_for"])) == 4)}
    assert ps.ranges_check(full, counted, side, filters=10)["check1"]["stands_for_differs"] == 1
    inward = dict(kept)
    for v in ("length", "height_mean"):
        own = kept[v].astype(np.float32)
        inward[v + "_lo"], inward[v + "_hi"] = own, own
    bad = ps.ranges_check(full, inward, side, filters=300, seed=1)
    assert not bad["check2"]["ok"] and bad["check2"]["wrong"]["length_hi"] > 0 and bad["check3"]["misses"] > 0
    assert "| 3. misses under 300 random filters (seed 1) | 0 |" in ps.ranges_markdown(r)


def test_ranges_report_of_the_clip(tmp_path):
    """Two searches of the clip with the no-fall zone and A-frames, without and with --same-line-square 5: the report
    from their stores passes the four checks with no miss, run.json's found is the found lines, the searches are the
    same but for the rule; ranges.json and ranges.md written, the command's exit status 0."""
    values = SETTINGS["sag"]
    full, table, _ = _search(tmp_path, "off", **values)
    kept, _, _ = _search(tmp_path, "on", same_line_square=5, **values)
    out = tmp_path / "report"
    r = ps.ranges_report(full, kept, str(out), filters=200, seed=2)
    assert r["found"] == len(table) and r["check1"]["ok"] and r["check2"]["ok"] and r["check3"]["misses"] == 0
    assert r["summary_found_ok"] and r["same_search"] and r["side"] == 5.0
    assert json.loads((out / "ranges.json").read_text(encoding="utf-8"))["check3"]["misses"] == 0
    assert "| 1. pairs = kept lines" in (out / "ranges.md").read_text(encoding="utf-8")
    assert ps.main([full, "--ranges", kept, "--out", str(tmp_path / "command"), "--filters", "50"]) == 0
