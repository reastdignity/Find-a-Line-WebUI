"""tools/prune_study.py: the audit of pruning rules on made-up tables with known answers. Offline; the
tables are written by production's own code (runs.save_results, mapping.write_map_scripts) and every
line, place and known line in them is invented."""

import json
import os
import re
import subprocess
import sys

import numba
import numpy as np
import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools"))
import helpers  # noqa: E402
import mapping  # noqa: E402
import prune_study as ps  # noqa: E402
import runs  # noqa: E402


def line(k, x1, y1, x2, y2, drop=False, **values):
    """A made-up line as a row of helpers.LineTable: water_m carries its number k (tables come back in
    lines.csv's order), filled_m 1.0 marks it for the test rule "marked"."""
    row = {"anchor1": (50.0 + y1 * 1e-5, 19.0 + x1 * 1e-5), "anchor2": (50.0 + y2 * 1e-5, 19.0 + x2 * 1e-5),
           "a1_xy": (float(x1), float(y1)), "a2_xy": (float(x2), float(y2)),
           "length": round(float(np.hypot(x2 - x1, y2 - y1)), 1), "clearance": 5.0, "clearance_nmpt": None,
           "over_obstacles": False, "water_m": float(k), "filled_m": 1.0 if drop else 0.0, "height_max": 20.0,
           "height_mean": 10.0, "high_pct": 30.0, "elev_a1": 500.0, "elev_a2": 500.0, "angle1": 10.0,
           "angle2": 10.0, "prom1": 0.0, "prom2": 0.0, "drop1": 20.0, "drop2": 20.0, "lift_needed": 0.0,
           "lift_no_zone": 0.0}
    assert not set(values) - set(row), set(values) - set(row)
    row.update(values)
    return row


def save(folder, rows, lines_js=False, distance=20.0):
    """A run's folder as a search saves it: lines.csv and run.json (lines.js on request)."""
    os.makedirs(folder)
    lines = helpers.LineTable.from_rows(rows)
    groups = mapping.group_lines(lines, distance, "clearance")
    meta = {"id": "made-up", "name": "Made-up place", "summary": {"lines": len(rows), "spots": len(groups)},
            "params": {"resolution": 1.0, "group_distance": distance, "group_by": "clearance", "model": "sag",
                       "end_zone": 5.0, "anchor_lift": 2.0}}
    runs.save_results(str(folder), lines, groups, meta, files=("lines.csv", "run.json"))
    if lines_js:
        head = '(window.FINDALINE_LINES = window.FINDALINE_LINES || {})["made-up"] = {"crs":"EPSG:2180","lines":['
        mapping.write_map_scripts(lines, str(folder), ("", head), files=("lines.js",))
    return str(folder), groups


def rows_of(table):
    """The table's row of each made-up line by its number."""
    return {int(k): i for i, k in enumerate(table["water_m"])}


@ps.rule("marked", title="Drop the marked lines (test)", idea="T-00")
def marked(table):
    return table["filled_m"] == 0


# The table of the never-prune tests: place A (three lines heading east), place B (two heading north),
# place C (one line)
PLACES = [
    line(0, 0, 0, 100, 0, clearance=10.0, length=100.0, height_max=30.0, height_mean=20.0, high_pct=50.0,
         elev_a1=500.0, elev_a2=500.0, angle1=10.0, angle2=20.0, prom1=5.0, prom2=1.0, drop1=40.0, drop2=30.0),
    line(1, 2, 1, 101, 1, drop=True, clearance=4.0, length=120.0, height_max=50.0, height_mean=15.0, high_pct=40.0,
         elev_a1=480.0, elev_a2=482.0, angle1=5.0, angle2=6.0, drop1=10.0, drop2=10.0, lift_no_zone=1.5),
    line(2, 1, 3, 99, 5, drop=True, clearance=6.0, length=90.0, height_max=10.0, height_mean=5.0, high_pct=10.0,
         elev_a1=495.0, elev_a2=495.0, angle1=30.0, angle2=30.0),
    line(3, 1000, 0, 1000, 100, drop=True, clearance=3.0, length=100.0, clearance_nmpt=1.0, height_max=20.0,
         elev_a1=320.0, elev_a2=330.0, angle1=10.0, angle2=10.0),
    line(4, 1001, 1, 1001, 99, clearance=2.0, length=98.0, clearance_nmpt=2.0, height_max=25.0, elev_a1=300.0,
         elev_a2=305.0, angle1=20.0, angle2=20.0, lift_no_zone=2.0),
    line(5, 3000, 0, 3100, 0, drop=True, clearance=1.0, length=100.0),
]


def test_table_as_the_search_saves_it(tmp_path):
    folder, groups = save(tmp_path / "run", PLACES)
    before = sorted(os.listdir(folder))
    cache = str(tmp_path / "cache")
    table = ps.load_table(folder, cache=cache)
    assert len(table) == 6 and table.name == "Made-up place" and table.source == "lines.csv"
    assert table.params["end_zone"] == 5.0 and table.distance == 20.0
    k = rows_of(table)
    assert table["length"][k[1]] == 120.0 and table["clearance"][k[0]] == 10.0
    assert (table["x1"][k[4]], table["y1"][k[4]], table["x2"][k[4]], table["y2"][k[4]]) == (1001.0, 1.0, 1001.0, 99.0)
    assert table["elev_a2"][k[3]] == 330.0 and table["angle2"][k[0]] == 20.0 and table["drop1"][k[0]] == 40.0
    assert np.isnan(table["clearance_nmpt"][k[0]]) and table["clearance_nmpt"][k[4]] == 2.0
    assert table["lift_no_zone"][k[1]] == 1.5 and table["over_obstacles"].dtype == bool
    assert table["representative"].sum() == 3 and table["group"].dtype == np.int64
    with pytest.raises(ValueError):  # a rule cannot write into the table
        table["length"][0] = 1.0
    # the cache lies outside the run's folder and gives the same table
    assert sorted(os.listdir(folder)) == before and len(os.listdir(cache)) == 1
    again = ps.load_table(folder, cache=cache)
    assert all(np.array_equal(table[c], again[c], equal_nan=True) for c in table.columns)
    plain = ps.load_table(os.path.join(folder, "lines.csv"), cache=False)
    assert sorted(plain.columns) == sorted(table.columns) and sorted(os.listdir(folder)) == before
    # the places are production's: the saved ones, and the same from the grouping run here
    places = ps.places_of(table)
    assert places.source == "saved" and len(places) == len(groups) == 3
    assert [int(table["water_m"][r]) for r in places.rep] == [0, 3, 5]  # the best place first
    assert places.sizes().tolist() == [3, 2, 1]
    grouped = ps.places_of(table, saved=False)
    assert grouped.source == "grouped" and np.array_equal(grouped.place, places.place)
    assert np.array_equal(grouped.rep, places.rep)
    assert ps.grouping_check(table) == {"saved": 3, "grouped_again": 3, "lines": 6, "lines_in_the_same_place": 6}


def test_places_of_kept_lines_are_productions(tmp_path):
    rng = np.random.default_rng(5)
    rows = []
    for k in range(400):  # clusters of near-identical lines
        cx, cy = rng.integers(0, 6, 2) * 60.0
        x1, y1 = cx + rng.integers(0, 30), cy + rng.integers(0, 30)
        rows.append(line(k, x1, y1, x1 + 80 + rng.integers(0, 30), y1 + rng.integers(0, 30),
                         clearance=float(rng.integers(1, 40)) / 4, over_obstacles=bool(k % 7 == 0)))
    folder, groups = save(tmp_path / "run", rows)
    table = ps.load_table(folder, cache=False)
    assert len(ps.places_of(table)) == len(groups)
    keep = rng.random(len(table)) < 0.5
    places = ps.places_of(table, keep)
    # production's grouping called by hand on the kept rows of the table
    kept = np.flatnonzero(keep)
    columns = {"a1_xy": np.column_stack([table["x1"], table["y1"]])[kept],
               "a2_xy": np.column_stack([table["x2"], table["y2"]])[kept],
               "over_obstacles": table["over_obstacles"][kept], "clearance": table["clearance"][kept],
               "length": table["length"][kept], "height_max": table["height_max"][kept]}
    expected = mapping.group_lines(helpers.LineTable(columns), 20.0, "clearance")
    assert len(places) == len(expected) and np.array_equal(places.rep, kept[expected.rep])
    assert (places.place[~keep] == -1).all()
    for g in range(len(expected)):
        assert set(np.flatnonzero(places.place == g)) == set(kept[expected.of(g)])
    assert len(ps.places_of(table, np.zeros(len(table), dtype=bool))) == 0
    assert len(ps.places_of(table, distance=5.0)) > len(groups)  # another distance: grouped here


def test_lines_js_gives_the_searchs_values_and_order(tmp_path):
    # Line 1 lies within 20 m of lines 0 and 2, which are 30 m apart. The search ranks 2 first (clearance
    # 10.004 against 10.001) and gives it line 1; lines.csv rounds both to 10.0, where the longer line 0
    # comes first and takes line 1
    rows = [line(0, 0, 0, 100, 0, clearance=10.001, length=100.0), line(1, 0, 15, 100, 15, clearance=5.0),
            line(2, 0, 30, 99, 30, clearance=10.004, length=99.0)]
    folder, groups = save(tmp_path / "csv", rows)
    table = ps.load_table(folder, cache=False)
    k = rows_of(table)
    saved = ps.places_of(table)
    assert saved.place[k[1]] == saved.place[k[2]] != saved.place[k[0]]
    rounded = ps.places_of(table, saved=False)
    assert rounded.place[k[1]] == rounded.place[k[0]]
    assert ps.grouping_check(table) == {"saved": 2, "grouped_again": 2, "lines": 3, "lines_in_the_same_place": 0}
    # with lines.js beside the table the grouping is the search's
    folder, groups = save(tmp_path / "js", rows, lines_js=True)
    table = ps.load_table(folder, cache=str(tmp_path / "cache"))
    assert table.source == "lines.js" and table.exact["clearance"][rows_of(table)[2]] == 10.004
    assert [int(table["water_m"][r]) for r in table.order] == [0, 1, 2]
    again = ps.places_of(table, saved=False)
    assert np.array_equal(again.place, ps.places_of(table).place)
    assert ps.grouping_check(table)["lines_in_the_same_place"] == 3
    cached = ps.load_table(folder, cache=str(tmp_path / "cache"))
    assert cached.source == "lines.js" and np.array_equal(cached.order, table.order)
    # a lines.js of other lines is not taken
    with open(os.path.join(folder, "lines.js"), encoding="utf-8") as f:
        text = f.read()
    with open(os.path.join(folder, "lines.js"), "w", encoding="utf-8") as f:
        f.write(text.replace(",15.0,", ",16.0,"))
    assert ps.load_table(folder, cache=False).source == "lines.csv"


def test_rules_register_by_name():
    assert {"higher_wins", "best_per_cell_pair"} <= set(ps.RULES)
    assert ps.RULES["higher_wins"].label == "'Higher wins on a face' (K-17)"
    assert ps.RULES["best_per_cell_pair"].label == "'One best line per pair of anchor cells' (K-01)"
    assert ps.RULES["best_per_cell_pair"].parameters({"cell": 3}) == {"cell": 3, "x0": 0.0, "y0": 0.0}
    with pytest.raises(ValueError, match="no parameter size"):
        ps.RULES["best_per_cell_pair"].parameters({"size": 3})
    with pytest.raises(ValueError, match="exists already"):
        @ps.rule("higher_wins")
        def other(table):
            return np.ones(len(table), dtype=bool)
    table = ps.Table({"x1": np.zeros(3), "filled_m": np.zeros(3)})
    with pytest.raises(ValueError, match="one boolean per line"):
        ps.apply_rule(ps.Rule("bad", "bad", None, lambda t: np.ones(2, dtype=bool)), table, {})
    with pytest.raises(ValueError, match="one boolean per line"):
        ps.apply_rule(ps.Rule("bad", "bad", None, lambda t: np.ones(3)), table, {})
    with pytest.raises(ValueError, match="no rule named nothing"):
        ps.audit(table, "nothing")
    assert ps.parse_params(["cell=5", "x0=-345601.0", "name=top", "on=true"]) == {
        "cell": 5, "x0": -345601.0, "name": "top", "on": True}


def test_higher_wins(tmp_path):
    rows = [  # one bucket of 8 m cells: the ends near (0, 0) and (100, 0); line 4 the other way round
        line(0, 1, 0, 100, 0, elev_a1=100.0, elev_a2=100.0), line(1, 2, 1, 100, 1, elev_a1=96.0, elev_a2=94.0),
        line(2, 5, 0, 100, 0, elev_a1=90.0, elev_a2=90.0), line(3, 6, 1, 100, 1, elev_a1=80.0, elev_a2=80.0),
        line(4, 100, 0, 3, 0, elev_a1=70.0, elev_a2=70.0),
        # another bucket: its heights span 9 m only
        line(5, 300, 0, 400, 0, elev_a1=50.0, elev_a2=50.0), line(6, 301, 0, 401, 0, elev_a1=41.0, elev_a2=41.0)]
    folder, _ = save(tmp_path / "run", rows)
    table = ps.load_table(folder, cache=False)
    kept = lambda **params: sorted(table["water_m"][ps.higher_wins(table, **params)].astype(int).tolist())  # noqa: E731
    assert kept() == [0, 1, 5, 6]  # within 10 m of the highest: 100 and 95; 90 is 10 m lower: dropped
    assert kept(step=20) == [0, 1, 2, 5, 6]
    assert kept(step=9) == [0, 1, 5]
    # a lattice from x0 = 4 splits the first bucket: {100, 95, 70} and {90, 80}
    assert kept(x0=4.0) == [0, 1, 2, 5, 6]
    assert kept(cell=500.0) == [0, 1]  # one bucket for all seven lines
    assert len(np.unique(ps.stack_buckets(table))) == 2


def test_best_per_cell_pair(tmp_path):
    rows = [line(0, 1, 1, 51, 1, clearance=5.0, length=50.0),
            line(1, 2, 2, 52, 3, clearance=7.0, length=50.1, height_max=8.0),
            line(2, 53, 4, 3, 3, clearance=7.0, length=50.1, height_max=9.0),  # the same cells, the other way round
            line(3, 6, 1, 51, 1, clearance=1.0, length=45.0),                  # another first cell
            line(4, 20, 20, 70, 20, clearance=3.0, length=50.0), line(5, 21, 20, 71, 20, clearance=3.0, length=50.0)]
    folder, _ = save(tmp_path / "run", rows)
    table = ps.load_table(folder, cache=False)
    kept = lambda **params: sorted(table["water_m"][ps.best_per_cell_pair(table, **params)].astype(int).tolist())  # noqa: E731
    assert kept() == [2, 3, 4]  # clearance, then length, then height; exact ties by the coordinates
    assert kept(cell=10.0) == [2, 4]
    assert kept(cell=5.0, x0=1.5) == [0, 2, 3, 4]  # the lattice moved: line 0 starts in a cell of its own
    # as many lines as unordered pairs of cells
    pairs = {frozenset([(x1 // 5, y1 // 5), (x2 // 5, y2 // 5)]) for x1, y1, x2, y2 in
             zip(table["x1"], table["y1"], table["x2"], table["y2"])}
    assert len(pairs) == len(kept()) == 3


def test_keepers(tmp_path):
    rows = [line(0, 0, 0, 100, 0, clearance=10.0, height_max=30.0, length=100.0, high_pct=50.0),
            line(1, 0, 50, 100, 50, clearance=5.0, height_max=25.0, length=100.0, high_pct=20.0),
            line(2, 4, 50, 104, 50, clearance=7.0, height_max=19.0, length=100.0, high_pct=20.0),
            # dropped: 5 m from line 0, which is lower and shorter
            line(10, 3, 0, 103, 4, drop=True, clearance=8.0, height_max=35.0, length=100.1, high_pct=50.0),
            # dropped: 6 m from line 0 the other way round, equal in every value
            line(11, 100, 2, 0, -6, drop=True, clearance=10.0, height_max=30.0, length=100.0, high_pct=50.0),
            # dropped: one end on line 0's, the other 20 m away; and one far from everything
            line(12, 0, 0, 100, 20, drop=True), line(13, 500, 500, 600, 500, drop=True),
            # dropped: 1 m from line 1 (less clearance), 3 m from line 2 (more clearance, lower)
            line(14, 1, 50, 101, 50, drop=True, clearance=6.0, height_max=20.0, length=100.0, high_pct=10.0)]
    folder, _ = save(tmp_path / "run", rows)
    table = ps.load_table(folder, cache=False)
    k = rows_of(table)
    result = ps.audit(table, "marked")
    s = result.summary["keepers"]
    assert (s["dropped"], s["with_keeper"], s["violations"]) == (5, 3, 2)
    assert [result.nearest[k[i]] for i in (10, 11, 14)] == [k[0], k[0], k[1]]
    assert [result.distance[k[i]] for i in (10, 11, 14)] == [5.0, 6.0, 1.0]
    assert result.nearest[k[12]] == result.nearest[k[13]] == result.nearest[k[0]] == -1
    values = {name: (v["nearest_not_worse"], v["some_keeper_not_worse"]) for name, v in s["values"].items()}
    assert values == {"clearance": (2, 3), "height": (2, 2), "length": (2, 2), "share high": (3, 3)}
    assert s["values"]["clearance"]["loss_where_worse"] == {"p50": 1.0, "p90": 1.0, "max": 1.0}
    assert s["values"]["height"]["loss_where_worse"]["max"] == 5.0
    assert (s["nearest_not_worse_in_all"], s["some_keeper_not_worse_in_all"]) == (1, 1)
    assert s["distance_m"] == {"p50": 5.0, "p90": 5.8, "max": 6.0}
    # a smaller radius: only the line 1 m away keeps its keeper
    assert ps.audit(table, "marked", radius=4.0).summary["keepers"]["violations"] == 4
    # the files: the violations listed by their row of lines.csv
    out = str(tmp_path / "out")
    files = result.write(out)
    assert [os.path.basename(f) for f in files] == ["audit.json", "audit.md", "violations.csv"]
    with open(files[2], encoding="utf-8") as f:
        listed = [r.split(",") for r in f.read().split()]
    assert listed[0][:3] == ["line", "csv_row", "place"]
    assert sorted(int(r[0]) for r in listed[1:]) == sorted([k[12], k[13]])
    assert all(int(r[1]) == int(r[0]) + 2 for r in listed[1:])
    with open(files[0], encoding="utf-8") as f:
        assert json.load(f) == result.summary
    text = result.markdown()
    assert "'Drop the marked lines (test)' (T-00) on Made-up place (8 lines)" in text
    assert "| **Violations: dropped lines without a kept line within 8 m** | 2 | 40.0 % |" in text


def brute_keepers(table, keep, radius, columns):
    """The keepers line by line in Python: the reference of the kernel."""
    x1, y1, x2, y2 = (table[c] for c in ("x1", "y1", "x2", "y2"))
    values = np.column_stack([table[c] for c in columns])
    out = {}
    r2 = radius * radius
    for i in np.flatnonzero(~keep).tolist():
        best, arg, bits, whole = np.inf, -1, 0, False
        for j in np.flatnonzero(keep).tolist():
            ds = []
            for (ax, ay, bx, by) in ((x1[i], y1[i], x2[i], y2[i]), (x2[i], y2[i], x1[i], y1[i])):
                da = (x1[j] - ax) ** 2 + (y1[j] - ay) ** 2
                db = (x2[j] - bx) ** 2 + (y2[j] - by) ** 2
                if da <= r2 and db <= r2:
                    ds.append(max(da, db))
            if not ds:
                continue
            if min(ds) < best:
                best, arg = min(ds), j
            ok = values[j] >= values[i]
            bits |= sum(1 << c for c in range(len(columns)) if ok[c])
            whole |= bool(ok.all())
        out[i] = (arg, np.sqrt(best) if arg >= 0 else np.inf, bits, whole)
    return out


def random_table(n=1500, seed=3):
    rng = np.random.default_rng(seed)
    x1, y1 = rng.integers(0, 120, n) / 2.0, rng.integers(0, 120, n) / 2.0  # half metres: equal distances occur
    turn = rng.random(n) < 0.5
    x2, y2 = x1 + 100 + rng.integers(0, 40, n) / 2.0, y1 + rng.integers(0, 40, n) / 2.0
    columns = {"x1": np.where(turn, x2, x1), "y1": np.where(turn, y2, y1), "x2": np.where(turn, x1, x2),
               "y2": np.where(turn, y1, y2), "clearance": rng.integers(1, 30, n) / 2.0,
               "length": np.round(np.hypot(x2 - x1, y2 - y1), 1), "height_max": rng.integers(5, 60, n).astype(float),
               "high_pct": rng.integers(0, 100, n).astype(float), "elev_a1": rng.integers(400, 440, n).astype(float),
               "elev_a2": rng.integers(400, 440, n).astype(float), "over_obstacles": np.zeros(n, dtype=bool)}
    return ps.Table(columns, name="random")


def test_keepers_match_the_line_by_line_reference():
    table = random_table()
    keep = np.random.default_rng(8).random(len(table)) < 0.15
    summary, nearest, distance = ps.keepers(table, keep, 6.0)
    reference = brute_keepers(table, keep, 6.0, [c for _, c in ps.VALUES])
    dropped = np.flatnonzero(~keep)
    assert [int(nearest[i]) for i in dropped] == [reference[i][0] for i in dropped.tolist()]
    assert np.array_equal(distance[dropped], [reference[i][1] for i in dropped.tolist()])
    has = [i for i in dropped.tolist() if reference[i][0] >= 0]
    assert 100 < len(has) < len(dropped) and summary["with_keeper"] == len(has)
    for c, (name, _) in enumerate(ps.VALUES):
        assert summary["values"][name]["some_keeper_not_worse"] == sum((reference[i][2] >> c) & 1 for i in has)
    assert summary["some_keeper_not_worse_in_all"] == sum(reference[i][3] for i in has)
    # every line kept, every line dropped
    assert ps.keepers(table, np.ones(len(table), dtype=bool), 6.0)[0]["dropped"] == 0
    assert ps.keepers(table, np.zeros(len(table), dtype=bool), 6.0)[0]["violations"] == len(table)


def test_same_results_with_any_number_of_threads():
    table = random_table(4000, seed=11)
    threads = numba.get_num_threads()
    texts = []
    try:
        for count in (1, max(2, numba.config.NUMBA_NUM_THREADS), 1):
            numba.set_num_threads(min(count, numba.config.NUMBA_NUM_THREADS))
            result = ps.audit(table, "best_per_cell_pair", {"cell": 5.0}, radius=8.0)
            texts.append((json.dumps(result.summary), result.nearest.tobytes(), result.distance.tobytes(),
                          result.keep.tobytes(), result.markdown()))
    finally:
        numba.set_num_threads(threads)
    assert texts[0] == texts[1] == texts[2]
    assert json.loads(texts[0][0])["keepers"]["violations"] == 0  # a 5 m cell's keeper lies within 8 m


def test_never_prune_list(tmp_path):
    folder, _ = save(tmp_path / "run", PLACES)
    table = ps.load_table(folder, cache=False)
    result = ps.audit(table, "marked")  # drops lines 1, 2 (place A), 3 (place B's shown line), 5 (place C)
    s = result.summary
    assert s["lines"] == {"before": 6, "kept": 2, "dropped": 4}
    assert (s["places"]["before"], s["places"]["emptied"], s["places"]["representatives_dropped"],
            s["places"]["after_grouped_again"]) == (3, 1, 2, 2)
    assert s["places"]["source"] == "saved by the search" and s["places"]["distance_m"] == 20.0
    best = {key: (v["places_with_a_value"], v["lost"], v["lost_in_places_with_lines_left"])
            for key, v in s["never_prune"]["best_per_sort_key"].items()}
    assert best == {
        "len": (3, 3, 2),       # A's longest (line 1) and B's (line 3) are dropped, C is emptied
        "clr": (3, 2, 1),       # A keeps its best (line 0)
        "clrN": (1, 0, 0),      # only B has clearances over trees; its best (line 4) stays
        "hmax": (3, 2, 1),      # A's highest is line 1
        "hmean": (3, 1, 0), "highPct": (3, 1, 0),
        "dh": (3, 1, 0),        # the smallest difference: A's line 0, B's line 4
        "elev": (3, 2, 1),      # B's higher line 3
        "angle": (3, 3, 2),     # the smallest: A's line 1, B's line 3
        "prom": (3, 1, 0), "promBoth": (3, 1, 0), "drop": (3, 1, 0)}
    assert s["never_prune"]["best_per_sort_key"]["len"]["loss"] == {"p50": 11.0, "p90": 18.2, "max": 20.0}
    # stacks: A (500, 495 and 481 m) keeps its top, B (325 over 302.5 m) loses it
    assert s["never_prune"]["stack_tops"] == {"available": True, "cell_m": 8.0, "step_m": 10.0, "stacks": 2,
                                              "lines_in_stacks": 5, "top_level_lost": 1, "highest_line_lost": 1}
    # sectors: A has lines at 90 degrees and one at 88.8 (dropped), B at 0, C at 90 (emptied)
    assert s["never_prune"]["sectors"] == {"sector_deg": 30.0, "pairs": 4, "lost": 2,
                                           "lost_in_places_with_lines_left": 1}
    assert s["never_prune"]["valid_without_zone_and_frames"] == {"column": True, "lines": 4, "dropped": 3}
    # the top level of a stack against its highest line: dropping only A's line 0 leaves line 2 at 495 m
    keep = table["water_m"] != 0
    tops = ps.never_prune(table, keep, ps.places_of(table))["stack_tops"]
    assert (tops["top_level_lost"], tops["highest_line_lost"]) == (0, 1)
    text = result.markdown()
    assert "| Never prune: places that lose their best line by length | 3 | of 3; 2 in places with lines left |" in text
    assert "| Made-up place | 'Drop the marked lines (test)' (T-00) | 6 | 2 (33.3 %) | 3 | 1 | 2 | 2 |" in text
    # a table without the zone's columns: every line counts as valid without it
    plain = ps.Table({c: v for c, v in table.columns.items() if not c.startswith("lift")}, table.meta)
    without = ps.audit(plain, "marked").summary["never_prune"]["valid_without_zone_and_frames"]
    assert without == {"column": False, "lines": 6, "dropped": 4}


def test_sort_keys_are_the_result_pages():
    with open(os.path.join(REPO, "viewer", "src", "list.ts"), encoding="utf-8") as f:
        block = f.read().split("export const SORT_KEYS")[1].split("];")[0]
    theirs = [(key, label, desc == "true") for key, label, desc in
              re.findall(r'\{key: "(\w+)", label: "([^"]+)".*?desc: (true|false)\}', block, flags=re.S)]
    assert len(theirs) == 13 and theirs[-1][0] == "n"
    assert [(key, label, largest) for key, label, _, largest in ps.SORT_KEYS] == theirs[:-1]


def known_folder(folder):
    """A made-up pass folder of the truth check: one capture with four found lines and three known
    lines (two matched). Returns the texts that must never appear in an output."""
    from pyproj import Transformer
    to_wgs = Transformer.from_crs("EPSG:2180", "EPSG:4326", always_xy=True).transform
    latlon = lambda x, y: list(to_wgs(x, y))[::-1]  # noqa: E731
    found = [(500001, 250000, 500101, 250000, 100.0), (500005, 250003, 500103, 250004, 98.0),
             (500000, 250030, 500100, 250030, 100.0), (500102, 249998, 500002, 249999, 100.0)]
    cluster = os.path.join(folder, "xx-49.999n19.000e")
    os.makedirs(os.path.join(cluster, "capture"))
    n = len(found)
    np.savez(os.path.join(cluster, "capture", "lines.npz"),
             a1=np.array([latlon(f[0], f[1]) for f in found]), a2=np.array([latlon(f[2], f[3]) for f in found]),
             a1_xy=np.array([f[:2] for f in found], dtype=np.float64),
             a2_xy=np.array([f[2:4] for f in found], dtype=np.float64), length=np.array([f[4] for f in found]),
             clearance=np.array([4.0, 3.0, 2.0, 1.0]), clearance_nmpt=np.full(n, np.nan), over=np.zeros(n, dtype=bool),
             rep=np.array([True, False, True, False]), group=np.array([0, 0, 1, 0]),
             elev_a1=np.full(n, 300.0), elev_a2=np.full(n, 300.0), height_max=np.full(n, 20.0),
             high_pct=np.full(n, 10.0), water_m=np.arange(n, dtype=np.float64),
             filled_m=np.array([1.0, 0.0, 1.0, 0.0]))  # the test rule drops found lines 0 and 2
    with open(os.path.join(cluster, "capture", "grid.json"), "w", encoding="utf-8") as f:
        json.dump({"crs": "EPSG:2180", "res": 1.0, "left": 499000.0, "top": 251000.0, "params": {}}, f)
    known = [{"id": "secret-line-1", "a": latlon(500000, 250000), "b": latlon(500100, 250000), "stated_m": 100.0,
              "geodesic_m": 100.0, "type": "highline"},
             {"id": "secret-line-2", "a": latlon(500000, 250031), "b": latlon(500100, 250031), "stated_m": None,
              "geodesic_m": 100.0, "type": "midline"},
             {"id": "secret-line-3", "a": latlon(500000, 250500), "b": latlon(500100, 250500), "stated_m": 100.0,
              "geodesic_m": 100.0, "type": "highline"}]
    with open(os.path.join(cluster, "known.json"), "w", encoding="utf-8") as f:
        json.dump(known, f)
    records = [{"id": "secret-line-1", "type": "highline", "tol": 10.0, "match": {"index": 0, "candidates": 3}},
               {"id": "secret-line-2", "type": "midline", "tol": 10.0, "match": {"index": 2, "candidates": 1}},
               {"id": "secret-line-3", "type": "highline", "tol": 10.0, "match": None}]
    with open(os.path.join(cluster, "analysis.json"), "w", encoding="utf-8") as f:
        json.dump({"status": "done", "records": records}, f)
    for name, status in (("xx-50.100n19.100e", "no_lines"), ("xx-50.200n19.200e", "failed")):
        os.makedirs(os.path.join(folder, name))
        with open(os.path.join(folder, name, "analysis.json"), "w", encoding="utf-8") as f:
            json.dump({"status": status, "records": []}, f)
    with open(os.path.join(folder, "analysis.json"), "w", encoding="utf-8") as f:  # the pass's own files are skipped
        json.dump({"clusters": 3}, f)
    return ["secret-line", "xx-49", "49.99", "50000", "2500"]


def test_known_lines_counts_only(tmp_path):
    folder, _ = save(tmp_path / "run", PLACES)
    table = ps.load_table(folder, cache=False)
    secrets = known_folder(str(tmp_path / "pass"))
    result = ps.audit(table, "marked", known=str(tmp_path / "pass"))
    known = result.summary["known"]
    # known line 1: its match (found line 0) is dropped, found lines 1 and 3 stay within its tolerance and line
    # 3 within 8 m of the match; known line 2: its only candidate is dropped; known line 3 was never matched
    assert known == {
        "radius_m": 8.0, "captures": 1, "captures_unreadable": 0, "found_lines": 4, "found_lines_kept": 2,
        "matching_as_the_truth_check": 2,
        "all": {"matched_before": 2, "within_tolerance_after": 1, "matched_line_kept": 0,
                "kept_line_within_radius_of_matched": 1},
        "types": {"highline": {"matched_before": 1, "within_tolerance_after": 1, "matched_line_kept": 0,
                               "kept_line_within_radius_of_matched": 1},
                  "midline": {"matched_before": 1, "within_tolerance_after": 0, "matched_line_kept": 0,
                              "kept_line_within_radius_of_matched": 0}}}
    out = str(tmp_path / "out")
    files = result.write(out)
    text = "".join(open(f, encoding="utf-8").read() for f in files)
    assert "| Known lines (all) that still have one | 1 | 50.0 % |" in text
    assert not [s for s in secrets if s in text]
    # the candidates are the truth check's: the nearest first
    capture = ps.capture_table(os.path.join(str(tmp_path / "pass"), "xx-49.999n19.000e"))
    assert capture.name == "capture" and capture.path is None and len(capture) == 4
    xy1, xy2 = (np.column_stack([capture["x" + k], capture["y" + k]]) for k in "12")
    rows = ps._candidates(np.array([500000.0, 250000.0]), np.array([500100.0, 250000.0]), 10.0, [100.0], xy1, xy2,
                          capture["length"])
    assert rows.tolist() == [0, 3, 1]
    assert ps._candidates(np.array([500000.0, 250000.0]), np.array([500100.0, 250000.0]), 10.0, [120.0], xy1, xy2,
                          capture["length"]).tolist() == []
    # a rule that needs a column the captures lack says so, without a word of the capture
    known = ps.audit(table, "higher_wins", known=str(tmp_path / "pass")).summary["known"]
    assert known["all"]["matched_before"] == 2
    @ps.rule("needs_lift")
    def needs_lift(table):
        return table["lift_no_zone"] == 0
    known = ps.audit(table, "needs_lift", known=str(tmp_path / "pass")).summary["known"]
    assert known == {"error": "the rule cannot run on the captures' tables: they have no column 'lift_no_zone'"}
    assert "| Known lines | not measured |" in ps.audit(table, "needs_lift", known=str(tmp_path / "pass")).markdown()


def test_pictures(tmp_path):
    pytest.importorskip("matplotlib")
    folder, _ = save(tmp_path / "run", PLACES)
    result = ps.audit(ps.load_table(folder, cache=False), "marked")
    files = result.write(str(tmp_path / "out"), pictures=True, picture_places=2)
    pictures = [f for f in files if f.endswith(".png")]
    assert [os.path.relpath(f, str(tmp_path / "out")).replace(os.sep, "/") for f in pictures] == [
        "pictures/place-1.png", "pictures/place-2.png"]
    for f in pictures:
        with open(f, "rb") as png:
            assert png.read(8) == b"\x89PNG\r\n\x1a\n" and os.path.getsize(f) > 10_000


def test_command_line_with_a_rules_file(tmp_path):
    folder, _ = save(tmp_path / "run", PLACES)
    before = sorted(os.listdir(folder))
    rules = tmp_path / "my_rules.py"
    rules.write_text('from prune_study import cells, rule\n\n\n'
                     '@rule("longer_than", title="Only lines longer than a limit", idea="X-00")\n'
                     'def longer_than(table, limit=100.0):\n'
                     '    assert len(cells(table, 5.0)) == 4\n'
                     '    return table["length"] >= float(limit)\n', encoding="utf-8")
    command = [sys.executable, os.path.join(REPO, "tools", "prune_study.py"), folder, "--rules-file", str(rules),
               "--cache", str(tmp_path / "cache")]
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    run = lambda *more: subprocess.run(command + list(more), capture_output=True, text=True, encoding="utf-8",  # noqa: E731
                                       cwd=str(tmp_path), env=env, timeout=600)
    done = run("--rule", "longer_than", "--param", "limit=99", "--out", str(tmp_path / "out"), "--threads", "2")
    assert done.returncode == 0, done.stderr
    assert "### 'Only lines longer than a limit' (X-00), limit 99 on Made-up place (6 lines)" in done.stdout
    assert "seconds: table" in done.stdout
    with open(tmp_path / "out" / "audit.json", encoding="utf-8") as f:
        first = f.read()
    summary = json.loads(first)
    assert summary["rule"] == {"name": "longer_than", "title": "Only lines longer than a limit", "idea": "X-00",
                               "params": {"limit": 99}}
    assert summary["lines"] == {"before": 6, "kept": 4, "dropped": 2}  # lines 2 (90 m) and 4 (98 m) go
    assert summary["table"]["settings"]["end_zone"] == 5.0 and summary["table"]["saved_summary"]["spots"] == 3
    # a second run, one thread, the cached columns: the same files
    done = run("--rule", "longer_than", "--param", "limit=99", "--out", str(tmp_path / "again"), "--threads", "1")
    assert done.returncode == 0, done.stderr
    for name in ("audit.json", "audit.md", "violations.csv"):
        with open(tmp_path / "out" / name, "rb") as a, open(tmp_path / "again" / name, "rb") as b:
            assert a.read() == b.read()
    assert sorted(os.listdir(folder)) == before  # nothing written beside the run
    # a rule or a parameter that does not exist: said, exit code 2
    done = run("--rule", "shorter_than", "--out", str(tmp_path / "none"))
    assert done.returncode == 2 and "no rule named shorter_than" in done.stderr and "longer_than" in done.stderr
    done = run("--rule", "longer_than", "--param", "length=5", "--out", str(tmp_path / "none"))
    assert done.returncode == 2 and "no parameter length" in done.stderr
    assert not os.path.exists(tmp_path / "none")
