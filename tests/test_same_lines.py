"""The square rule (--same-line-square, samelines.py): of all valid lines between the same two anchor
squares one is kept while the pair search runs.

The reducer against a plain reference on small tables (the order of a pair's lines, the counts, any order
of the parts, a tile's core, the join of tiles, its check), then searches of the Żabi Koń clip: with the
option off the files of before, with it on one grid's lines from tiles and from any number of threads,
the kept lines of the full table's pairs, the limits counted on kept lines, and what a run stores."""

import csv
import gc
import glob
import hashlib
import io
import json
import os
import sys

import numpy as np
import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
DATA = os.path.join(REPO, "tests", "data")

import grid as gd  # noqa: E402
import helpers as sh  # noqa: E402
import samelines  # noqa: E402

COLUMN = samelines.COLUMN
# A square area of the clip (as test_offline.test_area_in_tiles) and the two settings searched: the
# formula, and the sag model with the no-fall zone and A-frames (the rigging classes of the order)
SQUARE = {"type": "Polygon", "coordinates": [[[19.7522, 50.1546], [19.7590, 50.1546], [19.7590, 50.1580],
                                              [19.7522, 50.1580], [19.7522, 50.1546]]]}
SETTINGS = {"formula": {}, "sag": {"model": "sag", "end_zone": 5, "anchor_lift": 2}}
# lines.csv of those two searches with the option off, as branch line-volume at 3353f68 wrote it (before
# the option existed): a change that moves results changes these with the regression set's checksums
OFF_SHA256 = {"formula": "63acf23e3188d5e5497a73f57d62f7e8f8cbd10f580dab09972a78b0c85ae51c",
              "sag": "da5bb3092dcd86a964e433f84251f2792731091081db7361297ec83d6b9b0ea9"}


def _grid(left=1000.0, top=5000.0, res=1.0, size=30) -> gd.Grid:
    return gd.Grid(left, top, res, size, size, "EPSG:2180")


def _table(n: int, seed: int, ends: bool = True, size: int = 30) -> sh.LineTable:
    """n different lines between random pixels of a grid of size pixels, with few different values of
    the mean height, the length and the A-frame heights, so the later steps of the order decide too."""
    rng = np.random.default_rng(seed)
    pixels = rng.choice(size ** 4, 2 * n, replace=False)
    pixels = pixels[pixels // size ** 2 < pixels % size ** 2][:n]  # a pair of pixels once, not in both directions
    swap = rng.random(len(pixels)) < 0.5
    pixels = np.where(swap, pixels % size ** 2 * size ** 2 + pixels // size ** 2, pixels)
    a1 = np.column_stack([pixels // size ** 3, pixels // size ** 2 % size])
    a2 = np.column_stack([pixels // size % size, pixels % size])
    n = len(pixels)
    columns = {"a1": a1.astype(np.int64), "a2": a2.astype(np.int64)}
    for name in sh.LINE_VALUES:
        columns[name] = rng.random(n)
    columns["height_mean"] = rng.integers(0, 3, n).astype(np.float64)
    columns["length"] = rng.integers(40, 43, n).astype(np.float64)
    if ends:
        columns["lift_no_zone"] = rng.choice([0.0, 0.0, 0.4, 1.5], n)
        columns["lift_needed"] = np.where(rng.random(n) < 0.5, 0.0, columns["lift_no_zone"])
    return sh.LineTable(columns)


def _ends(grid: gd.Grid, a1, a2):
    """The anchors of lines as (xa, ya, xb, yb), the first anchor (the smaller x, then y) first."""
    x1, y1 = grid.pixel_to_xy(a1[:, 0], a1[:, 1])
    x2, y2 = grid.pixel_to_xy(a2[:, 0], a2[:, 1])
    return [(a, b, c, d) if (a, b) <= (c, d) else (c, d, a, b)
            for a, b, c, d in zip(x1.tolist(), y1.tolist(), x2.tolist(), y2.tolist())]


def _reference(ends, values, side: float, core=None) -> dict:
    """The rule written plainly: {pair of squares: (the anchors of its first line, its lines)} of lines
    given by their anchors (_ends) and values (dicts): per pair the least of (rigging class, -mean height,
    -length, the anchors)."""
    best = {}
    for (xa, ya, xb, yb), v in zip(ends, values):
        if core is not None and not (core[0] <= xa < core[2] and core[1] <= ya < core[3]):
            continue
        squares = sorted([(xa // side, ya // side), (xb // side, yb // side)])
        key = (squares[0], squares[1])
        rigging = 0 if "lift_no_zone" not in v or v["lift_no_zone"] == 0 else 1 if v["lift_needed"] == 0 else 2
        rank = (rigging, -v["height_mean"], -v["length"], xa, ya, xb, yb)
        if key not in best:
            best[key] = [rank, 0]
        best[key] = [min(best[key][0], rank), best[key][1] + 1]
    return {key: (rank[3:], count) for key, (rank, count) in best.items()}


def _kept(grid: gd.Grid, table: sh.LineTable) -> dict:
    """{the anchors of a kept line: the lines it stands for} of a reducer's table."""
    ends = _ends(grid, table.columns["a1"], table.columns["a2"])
    assert len(set(ends)) == len(ends)
    return dict(zip(ends, table.columns[COLUMN].tolist()))


def _rows(table: sh.LineTable) -> list:
    return [{name: table.columns[name][k] for name in table.columns if name not in ("a1", "a2")}
            for k in range(len(table))]


# The ranges (samelines.RANGED): of the values as a run without the rule stores them, the mean height and the A-frame
# heights at 2 decimals by Python's round() (the store's rounding, written plainly here), the others as they are
RANGE_DECIMALS = {"height_mean": 2, "lift_needed": 2, "lift_no_zone": 2}


def _range_names(table: sh.LineTable) -> list:
    return [name for name in table.columns if name.endswith(("_lo", "_hi"))]


def _range_reference(ends, table: sh.LineTable, side: float, core=None) -> dict:
    """The ranges written plainly: {pair of squares: {value: (least, most)}} of a table's lines given by their
    anchors (_ends), over the stored values (RANGE_DECIMALS by round()), NaN skipped (NaN when every one is)."""
    values = [v for v in samelines.RANGED if v in table.columns]
    columns = {v: table.columns[v].tolist() for v in values}
    out = {}
    for k, (xa, ya, xb, yb) in enumerate(ends):
        if core is not None and not (core[0] <= xa < core[2] and core[1] <= ya < core[3]):
            continue
        squares = sorted([(xa // side, ya // side), (xb // side, yb // side)])
        ranges = out.setdefault((squares[0], squares[1]), {v: [] for v in values})
        for v in values:
            value = columns[v][k]
            if value == value:  # NaN skipped
                ranges[v].append(round(value, RANGE_DECIMALS[v]) if v in RANGE_DECIMALS else value)
    return {key: {v: (min(seen), max(seen)) if seen else (float("nan"), float("nan")) for v, seen in r.items()}
            for key, r in out.items()}


def _assert_outward(lo, hi, least: float, most: float, where):
    """lo the largest float32 not above least, hi the smallest not below most (an infinity as it is); NaN for
    NaN; a zero +0.0."""
    for got, want, down in ((lo, least, True), (hi, most, False)):
        assert isinstance(got, np.float32), where
        if want != want:
            assert got != got, where
            continue
        g = float(got)
        with np.errstate(over="ignore"):  # the step beyond float32's largest value: an infinity
            up, down_step = float(np.nextafter(got, np.float32(np.inf))), float(np.nextafter(got, np.float32(-np.inf)))
        if abs(want) == float("inf"):
            assert g == want, where
        elif down:
            assert g <= want < up, (where, got, want)
        else:
            assert down_step < want <= g, (where, got, want)
        assert g != 0 or not np.signbit(got), where


def _xy_ends(table: sh.LineTable) -> list:
    """_ends of a table with coordinates (a1_xy, a2_xy: after mapping.coordify)."""
    c = table.columns
    return [(a, b, x, y) if (a, b) <= (x, y) else (x, y, a, b)
            for (a, b), (x, y) in zip(c["a1_xy"].tolist(), c["a2_xy"].tolist())]


def _assert_ranges(grid, kept: sh.LineTable, expected: dict, side: float, ends: bool):
    """Each kept line's range columns: the outward float32 of its pair's least and most (expected:
    _range_reference); the A-frame heights' only with them; float32 each, in the order of samelines.RANGED,
    right after COLUMN. grid: of the pixels a1, a2 (None: the table's coordinates)."""
    values = [v for v in samelines.RANGED if ends or v not in sh.END_VALUES]
    assert _range_names(kept) == [name for v in values for name in samelines.range_columns(v)]
    assert all(kept.columns[name].dtype == np.float32 for name in _range_names(kept))
    assert list(kept.columns).index(COLUMN) == list(kept.columns).index(_range_names(kept)[0]) - 1
    anchors = _xy_ends(kept) if grid is None else _ends(grid, kept.columns["a1"], kept.columns["a2"])
    assert len(anchors) == len(expected)
    for k, (xa, ya, xb, yb) in enumerate(anchors):
        squares = sorted([(xa // side, ya // side), (xb // side, yb // side)])
        for v in values:
            lo, hi = (kept.columns[name][k] for name in samelines.range_columns(v))
            _assert_outward(lo, hi, *expected[(squares[0], squares[1])][v], (k, v))


def _bits(table: sh.LineTable) -> dict:
    """The range columns' bits (NaN and the sign of zero as they are)."""
    return {name: table.columns[name].view(np.uint32).tobytes() for name in _range_names(table)}


def test_side_of_the_squares():
    """The option's metres on data of 1 m or finer, that many pixels on coarser data."""
    assert samelines.side(5, 1) == 5 and samelines.side(5, 2) == 10 and samelines.side(3, 2.5) == 7.5
    assert samelines.side(5, 0.5) == 5
    import runs
    assert runs.STANDS_FOR == COLUMN  # runs is imported without samelines (the web process)


@pytest.mark.parametrize("ends", [True, False])
def test_reducer_as_plain_reference(ends, monkeypatch):
    """The reducer keeps, per pair of squares without order, the first line of the order (least rigging,
    highest mean height, longest, the anchors' coordinates) with the number of the pair's lines: the
    plain reference's answer, whatever the parts and their order, in the order of the keys; with a core
    only the lines whose first anchor lies in it."""
    grid, side = _grid(), 5.0
    table = _table(6000, 1, ends)
    values = _rows(table)
    ends_of = _ends(grid, table.columns["a1"], table.columns["a2"])
    expected = _reference(ends_of, values, side)
    ranges = _range_reference(ends_of, table, side)
    assert len(expected) < len(table) / 2  # many lines share a pair
    tables = []
    for parts, merge_rows, seed in ((1, 1 << 20, 0), (7, 1 << 20, 1), (40, 300, 2), (40, 1, 3)):
        monkeypatch.setattr(samelines, "MERGE_ROWS", merge_rows)
        order = np.random.default_rng(seed).permutation(len(table))
        reducer = samelines.BestPerSquarePair(side, grid)
        for index in np.array_split(order, parts):
            reducer(table.take(index))
        counts = reducer.counts()
        kept = reducer.table()
        assert counts["found"] == len(table) and counts["kept"] == len(kept) == len(expected)
        assert _kept(grid, kept) == {anchors: count for anchors, count in expected.values()}
        assert int(kept.columns[COLUMN].sum()) == len(table) and kept.columns[COLUMN].dtype == np.int64
        assert not any(name.startswith("_") for name in kept.columns)
        _assert_ranges(grid, kept, ranges, side, ends)  # the least and the most of the pair's lines
        tables.append(kept)
    for other in tables[1:]:  # the same rows in the same order, every column
        assert list(other.columns) == list(tables[0].columns)
        assert all(np.array_equal(other.columns[name], tables[0].columns[name]) for name in other.columns)
        assert _bits(other) == _bits(tables[0])
    # a tile's core: its own lines only (the first anchor's test of search.line_coordinates)
    core = (1004.0, 4977.0, 1019.0, 4993.0)
    reducer = samelines.BestPerSquarePair(side, grid, core)
    for index in np.array_split(np.arange(len(table)), 5):
        reducer(table.take(index))
    in_core = _reference(_ends(grid, table.columns["a1"], table.columns["a2"]), values, side, core)
    assert 0 < len(in_core) < len(expected)
    assert reducer.counts()["found"] == sum(count for _, count in in_core.values())
    kept = reducer.table()
    assert _kept(grid, kept) == {anchors: count for anchors, count in in_core.values()}
    _assert_ranges(grid, kept, _range_reference(ends_of, table, side, core), side, ends)
    # no line at all: an empty table with the column and the ranges (float32, in their places)
    empty = samelines.BestPerSquarePair(side, grid)
    empty(sh.LineTable.empty())
    assert len(empty.table()) == 0 and COLUMN in samelines.BestPerSquarePair(side, grid).table().columns
    none = samelines.BestPerSquarePair(side, grid).table()
    assert list(none.columns) == [*sh.LineTable.empty().columns, COLUMN, *(
        name for v in samelines.RANGED[:4] for name in samelines.range_columns(v))]
    assert all(none.columns[name].dtype == np.float32 for name in _range_names(none))


def test_outward_float32():
    """samelines.outward: lo the largest float32 not above a value, hi the smallest not below it, exact where float32
    holds the value, a zero +0.0 (also from -0.0 and from a value just below zero), NaN as NaN, beyond float32's range
    its largest finite value and an infinity; the hard floats of the saved text and random doubles."""
    from test_units import HARD_FLOATS
    rng = np.random.default_rng(11)
    values = np.concatenate([np.array(HARD_FLOATS, dtype=np.float64), rng.normal(0, 300, 20000),
                             rng.random(2000) * 1e-40, -rng.random(2000) * 1e-46, np.float32(rng.random(500)),
                             [0.0, -0.0, 1e39, -1e39, 3.4028235e38, np.inf, -np.inf, np.nan, 2.675, 0.1, -1e-300]])
    lo, hi = samelines.outward(values)
    assert lo.dtype == hi.dtype == np.float32
    for k, v in enumerate(values.tolist()):
        _assert_outward(lo[k], hi[k], v, v, (k, v))
    with np.errstate(over="ignore"):
        exact = np.isfinite(values) & (values.astype(np.float32).astype(np.float64) == values)
    assert exact.sum() > 500 and np.array_equal(lo[exact], hi[exact])
    assert float(lo[values == 1e39][0]) == float(np.finfo(np.float32).max) and hi[values == 1e39][0] == np.inf


def test_ranges_of_rounded_values_nan_and_zeros(monkeypatch):
    """The ranges are of the values as a run without the rule stores them (the mean height and the A-frame heights
    rounded to 2 decimals, the others as they are), NaN skipped, NaN for a pair whose every mean height is NaN,
    -0.0 and +0.0 in one pair the same bits for every order; the kept line's own values stay unrounded (the order
    reads them so); any split, order and MERGE_ROWS give the same bits."""
    grid, side = _grid(), 5.0
    table = _table(6000, 7)
    rng = np.random.default_rng(8)
    c = table.columns
    n = len(table)
    c["height_mean"] = rng.random(n) * 50 + rng.random(n) * 1e-3
    c["height_mean"][rng.random(n) < 0.2] = np.nan
    c["lift_no_zone"] = np.where(rng.random(n) < 0.5, 0.0, rng.random(n) * 3)
    c["lift_needed"] = np.where(rng.random(n) < 0.5, 0.0, c["lift_no_zone"] * rng.random(n))
    c["clearance"] = np.where(rng.random(n) < 0.3, np.where(rng.random(n) < 0.5, 0.0, -0.0), c["clearance"])
    c["height_max"][::7] = -0.0
    x1, y1 = grid.pixel_to_xy(c["a1"][:, 0], c["a1"][:, 1])
    x2, y2 = grid.pixel_to_xy(c["a2"][:, 0], c["a2"][:, 1])
    ka, kb = samelines.square_keys(x1, y1, x2, y2, side)
    _, inverse, counts = np.unique(np.column_stack([ka, kb]), axis=0, return_inverse=True, return_counts=True)
    all_nan = np.flatnonzero(inverse.ravel() == int(np.argmax(counts)))
    c["height_mean"][all_nan] = np.nan  # the largest pair: no mean height at all
    ends_of = _ends(grid, c["a1"], c["a2"])
    ranges = _range_reference(ends_of, table, side)
    assert sum(r["height_mean"][0] != r["height_mean"][0] for r in ranges.values()) >= 1
    assert sum(r["clearance"][0] == 0.0 for r in ranges.values()) > 100  # -0.0 and +0.0 in many pairs
    bits = None
    for parts, merge_rows, seed in ((1, 1 << 20, 0), (9, 1 << 20, 1), (60, 200, 2), (30, 1, 3)):
        monkeypatch.setattr(samelines, "MERGE_ROWS", merge_rows)
        order = np.random.default_rng(seed).permutation(n)
        reducer = samelines.BestPerSquarePair(side, grid)
        for index in np.array_split(order, parts):
            reducer(table.take(index))
        kept = reducer.table()
        _assert_ranges(grid, kept, ranges, side, True)
        assert bits is None or _bits(kept) == bits
        bits = _bits(kept)
        # the kept line's own values unrounded: those of the found line itself
        own = dict(zip(ends_of, c["height_mean"].tolist()))
        got = kept.columns["height_mean"].tolist()
        for k, anchors in enumerate(_ends(grid, kept.columns["a1"], kept.columns["a2"])):
            assert got[k] == own[anchors] or (got[k] != got[k] and own[anchors] != own[anchors])
        assert any(v != round(v, 2) for v in got if v == v)


def test_squares_on_a_coarse_grid_and_any_lattice_side():
    """The lattice has a corner at (0, 0) of the CRS whatever the grid's own corner; other sides and a
    2 m grid follow the same reference."""
    for grid, side in ((_grid(1001.0, 5003.0, 1.0), 3.0), (_grid(1000.0, 5000.0, 2.0), 10.0),
                       (_grid(-37.0, 12.0, 1.0), 5.0)):
        table = _table(3000, 5, size=20)
        expected = _reference(_ends(grid, table.columns["a1"], table.columns["a2"]), _rows(table), side)
        reducer = samelines.BestPerSquarePair(side, grid)
        reducer(table)
        assert _kept(grid, reducer.table()) == {anchors: count for anchors, count in expected.values()}


def test_join_of_tiles_as_one_grid():
    """Tiles reduce their own lines; a pair of squares may hold lines of two tiles, so the join is
    reduced again (reduce_table, on the coordinates): one grid's lines, counts and order."""
    grid, side = _grid(), 5.0
    table = _table(6000, 2)
    whole = samelines.BestPerSquarePair(side, grid)
    whole(table.take(np.arange(len(table))))
    whole = whole.table()
    whole.reorder(np.argsort(-whole.columns["length"], kind="stable"))  # as search._pair_search returns it
    tiles, held = [], 0
    for core in ((1000.0, 4970.0, 1013.0, 5000.0), (1013.0, 4970.0, 1030.0, 4983.0),
                 (1013.0, 4983.0, 1030.0, 5000.0)):  # cores that cut squares
        reducer = samelines.BestPerSquarePair(side, grid, core)
        for index in np.array_split(np.random.default_rng(3).permutation(len(table)), 9):
            reducer(table.take(index))
        tile = reducer.table()
        for name, pixels in (("a1_xy", tile.columns["a1"]), ("a2_xy", tile.columns["a2"])):
            tile.columns[name] = np.column_stack(grid.pixel_to_xy(pixels[:, 0], pixels[:, 1]))
        held += len(tile)
        tiles.append(tile.reorder(np.argsort(-tile.columns["length"], kind="stable")))
    joined = samelines.reduce_table(sh.LineTable.join(tiles), side)
    assert len(whole) < held  # some pairs had lines of two tiles
    assert len(joined) == len(whole) and int(joined.columns[COLUMN].sum()) == len(table)
    for name in whole.columns:
        assert np.array_equal(joined.columns[name], whole.columns[name]), name
    assert len(_range_names(whole)) == 12 and _bits(joined) == _bits(whole)  # the ranges of one grid, bit for bit
    _assert_ranges(grid, whole, _range_reference(_ends(grid, table.columns["a1"], table.columns["a2"]), table, side),
                   side, True)
    assert samelines.reduce_table(sh.LineTable.empty(), side) is not None
    # a table without range columns (tests/test_search_findings.py's): reduced as before, none added
    plain = samelines.BestPerSquarePair(side, grid)
    plain(table.take(np.arange(len(table))))
    plain = plain.table()
    for name in _range_names(plain):
        plain.columns.pop(name)
    plain.columns.update(a1_xy=np.column_stack(grid.pixel_to_xy(plain.columns["a1"][:, 0], plain.columns["a1"][:, 1])),
                         a2_xy=np.column_stack(grid.pixel_to_xy(plain.columns["a2"][:, 0], plain.columns["a2"][:, 1])))
    again = samelines.reduce_table(sh.LineTable.join([plain.take(np.arange(0, len(plain), 2)),
                                                      plain.take(np.arange(1, len(plain), 2))]), side)
    assert not _range_names(again) and len(again) == len(plain)


def test_reducer_asks_its_check_about_kept_lines(monkeypatch):
    """The check gets the kept lines after a merge, never the found ones: it stops a search whose kept
    lines pass the limit, lets one pass whose found lines do, and bounds the rows held between merges."""
    grid, side = _grid(), 5.0
    table = _table(6000, 4)
    pairs = len(_reference(_ends(grid, table.columns["a1"], table.columns["a2"]), _rows(table), side))
    monkeypatch.setattr(samelines, "CHECK_ROWS", 1)

    class Stop(Exception):
        pass

    def run(limit):
        asked = []

        def check(count):
            asked.append(count)
            if count > limit:
                raise Stop(count)
        reducer = samelines.BestPerSquarePair(side, grid, check=check)
        for index in np.array_split(np.arange(len(table)), 60):
            reducer(table.take(index))
        return reducer, asked

    reducer, asked = run(pairs)  # the found lines are four times the limit
    assert len(reducer.table()) == pairs and max(asked) <= len(table) and reducer.found == len(table)
    assert reducer.peak_rows <= pairs + pairs // 8 + 200  # merged whenever the rows held would be refused
    with pytest.raises(Stop) as stopped:
        run(pairs // 2)
    assert pairs // 2 < stopped.value.args[0] <= pairs  # kept lines, and stopped before the last part
    reducer, asked = samelines.BestPerSquarePair(side, grid), []
    reducer(table)
    assert reducer.peak_rows == pairs  # without a check: merged by MERGE_ROWS alone


def test_option_and_its_bounds():
    """--same-line-square: 0 (off, the default) or 2 to 20; in the form's topic of the lines."""
    import params as pm
    point = {"lat": 50.0, "lon": 19.0}
    assert pm.SearchParams(**point).same_line_square == 0
    for value in (2, 5, 7.5, 20):
        assert pm.SearchParams(**point, same_line_square=value).same_line_square == value
    for value in (-1, 0.5, 1, 1.99, 20.5, 100):
        with pytest.raises(ValueError) as error:
            pm.SearchParams(**point, same_line_square=value)
        problem = error.value.errors()[0]["ctx"]["error"]
        assert problem.code == "same_line_square_range" and problem.params == {"min": 2, "max": 20}
        assert "2 to 20" in problem.web_text() and "same" not in problem.web_text()
    assert pm.TOPIC_OF["same_line_square"] == "lines"
    params = pm.parse_cli(["--lat", "50", "--lon", "19", "--same-line-square", "5"])[0][0]
    assert params.same_line_square == 5


# --- searches of the clip ---

def _search(tmp_path, name: str, limits=None, memory=None, early_stop=None, **values):
    """A search of the clip in this process: (the run's folder, its lines' table, the plan)."""
    import search
    from params import SearchParams
    area = tmp_path / "square.geojson"
    if not area.exists():
        area.write_text(json.dumps({"type": "Feature", "properties": {}, "geometry": SQUARE}))
    where = {} if "radius" in values else {"area": str(area)}
    params = SearchParams(**{"elevation_file": os.path.join(DATA, "zabi_kon_nmt.tif"), "max_length": 150,
                             "water": "off", "fill_gaps": "off", "ortho": "never", **where, **values})
    paths = search.Paths(str(tmp_path / name), str(tmp_path / name / "work"))
    os.makedirs(paths.work, exist_ok=True)
    plan = search.plan_search(params, paths, lambda kind, text: None, limits=limits)
    if memory is not None:
        plan.memory = memory(plan)
    if early_stop is not None:
        plan.early_stop = early_stop
    lines, run = search.search_lines(plan)
    table = sh.LineTable(dict(lines.results.columns))
    result = search.save_run(plan, lines, run)
    del lines
    gc.collect()  # the memory-mapped grids closed before the next search writes its own (Windows)
    return result.run["path"], table, plan


def _read(run: str, name: str) -> bytes:
    with open(os.path.join(run, name), "rb") as f:
        return f.read()


def _export(run: str, fmt: str = "csv") -> bytes:
    """The run's CSV or GeoJSON export (its lines.csv and lines.geojson before store wave 4)."""
    import clip_runs
    return clip_runs.export_text(run, fmt)


def _store(run: str):
    """(the store's lines as a LineTable, its head): data.js's rows and head before store wave 4."""
    import linestore
    return linestore.read(run, profiles=False)


def _store_table(run: str):
    """lines.arrow without its schema's metadata (the head names the run)."""
    import pyarrow as pa
    with pa.OSFile(os.path.join(run, "lines.arrow"), "rb") as f:
        return pa.ipc.open_file(f).read_all().replace_schema_metadata(None)


def _table_reference(table: sh.LineTable, side: float) -> dict:
    """_reference of a search's full table (coordinates in the grid's CRS)."""
    c = table.columns
    ends = [(a, b, x, y) if (a, b) <= (x, y) else (x, y, a, b)
            for (a, b), (x, y) in zip(c["a1_xy"].tolist(), c["a2_xy"].tolist())]
    names = [name for name in ("height_mean", "length", "lift_needed", "lift_no_zone") if name in c]
    values = [dict(zip(names, row)) for row in zip(*(c[name].tolist() for name in names))]
    return _reference(ends, values, side)


@pytest.mark.parametrize("setting", list(SETTINGS))
def test_search_with_the_option_off_as_before(tmp_path, setting):
    """Option off: the CSV export byte for byte the lines.csv of before the option existed, and no file of the run
    knows of it (no column, no value of a row, no key of run.json or of the store's head; the exports too)."""
    import search
    run, table, plan = _search(tmp_path, "off", **SETTINGS[setting])
    assert hashlib.sha256(_export(run)).hexdigest() == OFF_SHA256[setting]
    assert COLUMN not in table.columns and plan.square == 0
    meta = json.loads(_read(run, "run.json"))
    assert "found" not in meta["summary"] and not [k for k in meta["params"] if k.startswith("same_line")]
    for name, text in (("csv", _export(run)), ("geojson", _export(run, "geojson")), *(
            (name, _read(run, name)) for name in ("lines.arrow", "profiles.arrow", "run.json"))):
        assert b"stands_for" not in text and b"same_line" not in text, name
    stored, head = _store(run)
    assert COLUMN not in stored.columns and "found" not in head and "square" not in head
    assert not _range_names(table) and not _range_names(stored)  # no range anywhere
    assert not [name for name in _store_table(run).schema.names if name.endswith(("_lo", "_hi"))]
    assert set(sh.END_VALUES) <= set(stored.columns) if SETTINGS[setting] else \
        not set(sh.END_VALUES) & set(stored.columns)
    assert "same_line_square" not in search._run_params(plan)


@pytest.mark.parametrize("setting", list(SETTINGS))
def test_search_keeps_one_line_per_pair_of_squares(tmp_path, setting):
    """Option on: the kept lines are the first lines of the pairs of squares of the full table (the
    search without the option) and stand for all its lines; tiles and one thread give the same files."""
    values = SETTINGS[setting]
    _, full, _ = _search(tmp_path, "off", **values)
    run, kept, plan = _search(tmp_path, "on", same_line_square=5, **values)
    assert plan.square == 5 and plan.resolution == 1
    expected = _table_reference(full, plan.square)
    assert 0 < len(expected) < len(full) / 3
    assert len(kept) == len(expected) and int(kept.columns[COLUMN].sum()) == len(full)
    c = kept.columns
    got = {(a, b, x, y) if (a, b) <= (x, y) else (x, y, a, b): count
           for (a, b), (x, y), count in zip(c["a1_xy"].tolist(), c["a2_xy"].tolist(), c[COLUMN].tolist())}
    assert got == {anchors: count for anchors, count in expected.values()}
    # the ranges: of the full table's lines of each pair, as the store keeps them (the mean height and the A-frame
    # heights rounded), in the store as the search's table holds them
    _assert_ranges(None, kept, _range_reference(_xy_ends(full), full, plan.square), plan.square, bool(values))
    stored, _ = _store(run)
    assert _bits(stored) == _bits(kept)
    if values:  # the rigging classes took part: a pair with lines of several keeps one of the least
        assert len(set(np.sign(full.columns["lift_no_zone"]).tolist())) == 2
    tiled, _, tiled_plan = _search(tmp_path, "tiled", same_line_square=5, tile_size=150, **values)
    assert tiled_plan.tiles and len(glob.glob(os.path.join(tiled, "tiles", "*.pkl.gz"))) > 1
    one_thread, _, _ = _search(tmp_path, "one-thread", same_line_square=5, threads=1, **values)
    for other in (tiled, one_thread):
        assert _export(other) == _export(run)
        assert _store_table(other).equals(_store_table(run))  # lines.js's rows before store wave 4
        assert json.loads(_read(other, "run.json"))["summary"] == json.loads(_read(run, "run.json"))["summary"]


def test_run_stores_the_count_and_the_side(tmp_path):
    """A run made with the option: every line with the found lines it stands for (the CSV export's last
    column, a property of the GeoJSON export, a column of the store that its head names last in "ends"),
    run.json with the option, the side its squares had and the lines found."""
    values = SETTINGS["sag"]
    _, full, _ = _search(tmp_path, "off", **values)
    run, kept, plan = _search(tmp_path, "on", same_line_square=5, **values)
    rows = list(csv.DictReader(io.StringIO(_export(run).decode("utf-8-sig"), newline="")))
    assert list(rows[0])[-1] == "stands_for" and len(rows) == len(kept)
    assert sum(int(r["stands_for"]) for r in rows) == len(full) and min(int(r["stands_for"]) for r in rows) >= 1
    features = json.loads(_export(run, "geojson"))["features"]
    assert [f["properties"]["stands_for"] for f in features] == [int(r["stands_for"]) for r in rows]
    meta = json.loads(_read(run, "run.json"))
    assert meta["summary"]["lines"] == len(kept) and meta["summary"]["found"] == len(full)
    assert meta["params"]["same_line_square"] == 5 and meta["params"]["same_line_side"] == 5
    assert "one line per pair of 5 m anchor squares" in meta["description"]
    stored, head = _store(run)
    assert head["ends"] == [*sh.END_VALUES, "stands_for"] and head["found"] == len(full) and head["square"] == 5
    assert sorted(stored.columns[COLUMN].tolist()) == sorted(kept.columns[COLUMN].tolist())
    # the formula (no A-frame heights): the count alone
    run, kept, _ = _search(tmp_path, "formula", same_line_square=5)
    stored, head = _store(run)
    assert head["ends"] == ["stands_for"] and not set(sh.END_VALUES) & set(stored.columns)
    assert int(stored.columns[COLUMN].sum()) == head["found"] > len(kept)
    # a coarser grid: the squares are as many pixels wide
    run, _, plan = _search(tmp_path, "coarse", same_line_square=5, resolution=2)
    assert plan.square == 10 and json.loads(_read(run, "run.json"))["params"]["same_line_side"] == 10


def test_hash_of_a_tiled_search_only_when_set(tmp_path, monkeypatch):
    """The search hash (resuming a tiled search) holds the option only when it is set."""
    import search
    seen = []
    real = search.hashlib.sha1
    monkeypatch.setattr(search.hashlib, "sha1", lambda data: (seen.append(data), real(data))[1])
    from params import SearchParams
    paths = search.Paths(str(tmp_path), str(tmp_path / "work"))
    for square in (0, 5):
        params = SearchParams(elevation_file=os.path.join(DATA, "zabi_kon_nmt.tif"), northing=254608,
                              easting=553966, radius=150, same_line_square=square)
        search._search_hash(search.plan_search(params, paths, lambda kind, text: None))
    assert b"same_line_square" not in seen[0] and b'"same_line_square": 5' in seen[1]


def test_limits_count_kept_lines(tmp_path, monkeypatch):
    """With the option on, the line limit and the memory check count kept lines: a search whose found
    lines pass a limit but whose kept lines do not is accepted, one whose kept lines pass it is refused
    with the codes and texts of before, early (the reducer's check) or at its end."""
    import messages
    import search
    from settings import Limits
    monkeypatch.setattr(search, "REFUSE_FACTOR", float("inf"))  # the checks of the search's own pairs (the
    # estimate before them, of a small sample of this small search: tests/test_sample_estimate.py)
    point = {"northing": 254608, "easting": 553966, "radius": 150}
    _, full, _ = _search(tmp_path, "off", **point)
    _, kept, plan = _search(tmp_path, "on", same_line_square=5, **point)
    found, pairs = len(full), len(kept)
    assert pairs < found / 2
    # the found lines over the limit, the kept lines at it: accepted with the option, refused without
    run, table, _ = _search(tmp_path, "at-limit", limits=Limits(lines_max=pairs), same_line_square=5, **point)
    assert len(table) == pairs
    with pytest.raises(search.SearchError) as error:
        _search(tmp_path, "without", limits=Limits(lines_max=pairs), **point)
    assert error.value.code == "too_many_lines_early"
    assert error.value.params["advice"][0] == {"key": "same_line_square", "value": 5}  # off: offered first
    gc.collect()
    monkeypatch.setattr(samelines, "CHECK_ROWS", 1)
    for early, code, text in ((False, "too_many_lines", f"{pairs} lines, at most {pairs - 1}"),
                              (True, "too_many_lines_early", f"more than {pairs - 1} lines (the search stopped at")):
        with pytest.raises(search.SearchError) as error:
            _search(tmp_path, f"over-{early}", limits=Limits(lines_max=pairs - 1, lines_early_stop=early),
                    same_line_square=5, **point)
        assert error.value.code == code and text in str(error.value), error.value
        assert error.value.params["max"] == pairs - 1 and pairs - 1 < error.value.params["n"] <= pairs
        assert error.value.params["advice"] == messages.line_advice(plan.params)
        # the square rule is on: the advice does not name it again
        assert "same_line_square" not in [a["key"] for a in error.value.params["advice"]]
        assert "--same-line-square" not in str(error.value), error.value
        gc.collect()
    # the memory: the grids and the kept lines fit, one line fewer does not
    pixels = plan.grid.width * plan.grid.height
    monkeypatch.setattr(search, "profile_points", lambda lines: 0)  # a circle's profiles: not counted here
    _, table, _ = _search(tmp_path, "fits", memory=lambda plan: int(search.memory_needed(pixels, pairs)),
                          same_line_square=5, **point)
    assert len(table) == pairs
    for early, code in ((False, "too_many_lines_memory"), (True, "too_many_lines_memory_early")):
        with pytest.raises(search.SearchError) as error:
            _search(tmp_path, f"memory-{early}", memory=lambda plan: int(search.memory_needed(pixels, pairs - 1)),
                    early_stop=early, same_line_square=5, **point)
        assert error.value.code == code and error.value.params["max"] == pairs - 1, error.value
        gc.collect()


# --- the web app: the Advanced form's field ---

def test_form_field_round_trip(tmp_path, monkeypatch):
    """The field of the Advanced form: in the schema with the page's words (topic "lines"), also on the
    public site; a request keeps its value through the queue ("search again", the form's edit) into
    run.json; a value outside 0 or 2 to 20 is refused for everyone, with the catalogue's text."""
    pytest.importorskip("httpx2")
    import time
    from fastapi.testclient import TestClient
    import messages
    import web
    from jobs import Jobs, Scheduler
    from settings import Limits
    public = Limits.load(public=True)
    for limits in (None, public):
        field = {f["name"]: f for f in web.schema(limits)}["same_line_square"]
        assert (field["type"], field["default"], field["topic"], field["unit"]) == ("number", 0, "lines", "m")
        assert field["label"] == messages.text("field.same_line_square.label") and "0: off" in field["help"]
        assert not field["optional"] and (field["min"], field["max"]) == (None, None)
    point = {"lat": 50.1, "lon": 19.7}
    for limits in (None, public):
        for value in (0, 2, 5, 20, "5"):
            web.checked_request({"params": {**point, "same_line_square": value}}, limits)
        for value in (1, 1.9, 21, -5, 1e9, "x"):
            with pytest.raises(ValueError) as error:
                web.checked_request({"params": {**point, "same_line_square": value}}, limits)
            if value != "x":
                assert "One line per pair of anchor squares is 0 (off) or 2 to 20 m." in str(web.error_detail(error.value))
    # the page's request, kept by the queue and given back for "search again" and the form's edit
    token, local = "test-token", "http://127.0.0.1:8765"
    app = web.create_app(str(tmp_path), token=token, start_scheduler=False)
    headers = {"x-findaline-token": token}
    with TestClient(app, base_url=local) as client:
        assert "same_line_square" in {f["name"] for f in client.get("/api/schema").json()["fields"]}
        request = {"params": {**point, "radius": 300, "same_line_square": 5}}
        job = client.post("/api/jobs", json=request, headers=headers).json()["id"]
        assert client.get(f"/api/jobs/{job}").json()["request"]["params"]["same_line_square"] == 5
        answer = client.post("/api/jobs", json={"params": {**point, "same_line_square": 1}}, headers=headers)
        assert answer.status_code == 400 and "0 (off) or 2 to 20 m" in answer.text
        jobs = Jobs(str(tmp_path))
        jobs.set(job, "failed", error="interrupted")
        again = client.post(f"/api/jobs/{job}/again", headers=headers).json()["id"]
        assert json.loads(jobs.get(again)["request"])["params"]["same_line_square"] == 5
        for waiting in (job, again):
            jobs.set(waiting, "cancelled")
    # a job through the worker: the run knows the option, the side and the lines found
    for key, value in {"HTTP_PROXY": "http://127.0.0.1:9", "HTTPS_PROXY": "http://127.0.0.1:9", "NO_PROXY": ""}.items():
        monkeypatch.setenv(key, value)
    params = {"elevation_file": os.path.join(DATA, "zabi_kon_nmt.tif"), "northing": 254608, "easting": 553966,
              "radius": 150, "water": "off", "fill_gaps": "off", "name": "Clip", "ortho": "never",
              "same_line_square": 5}
    job = jobs.add({"params": params, "geometry": None}, "clip")
    scheduler = Scheduler(jobs)
    scheduler.start()
    try:
        deadline = time.time() + 300
        while jobs.get(job)["status"] not in ("done", "failed") and time.time() < deadline:
            time.sleep(0.5)
    finally:
        scheduler.stop()
    result = jobs.get(job)
    assert result["status"] == "done", result["error"]
    meta = json.loads(_read(str(tmp_path / "runs" / result["run_id"]), "run.json"))
    assert meta["params"]["same_line_square"] == 5 and meta["params"]["same_line_side"] == 5
    assert meta["summary"]["found"] > 2 * meta["summary"]["lines"] > 0
    assert any("Square rule:" in str(e["data"]) for e in jobs.events(0, job) if e["kind"] == "info")


# --- the page: the lines found, and what a line stands for ---

PAGE_SCRIPT = """
run({
  loaded(next) { wait(() => model() && rows().length, () => {
    result.summary = text(".r-summary-count");
    result.foundLine = text(".r-found-line");
    result.found = [model().data.found, model().data.square, ($(".r-found") || {title: null}).title];
    result.sum = Array.from({length: model().total}, (_, k) => model().lineAt(k)).reduce((n, l) => n + (l.stands_for || 0), 0);
    result.n = model().count;
    // the tight mark: on every row under 1 m and on no other; the first row is the line made tight (TIGHT_LINE)
    result.marks = rows().every((r, k) => !!r.querySelector(".r-tight") === (model().rows[k].line.clr < 1));
    result.first = [!!rows()[0].querySelector(".r-tight"), rows()[0].querySelector(".r-clr").textContent];
    result.key = text(".r-tight-key");
    rows()[0].click();
    wait(() => $(".r-kv") && $(".r-card .fal-profile-title"), () => {
      result.facts = $$(".r-kv dt").map((dt) => [dt.textContent, dt.nextElementSibling.textContent]);
      result.stands = model().selected.line.stands_for;
      result.tightLine = text(".r-tight-line");
      result.card = text(".r-card");  // the profile's title: the line's clearance as the rows write it
      next();
    });
  }); },
  why(next) {
    const link = $(".r-why-link");
    if (!link) { result.why = null; return next(); }
    link.click();
    wait(() => $(".r-why"), () => {
      result.why = {text: text(".r-why-text"), rows: $$(".r-why-row").map((r) => r.textContent),
                    bar: !!$(".r-why-bar")};
      const counts = model().needCounts();
      if (!counts) { result.counts = null; return next(); }  // without the zone and A-frames: the first sentence only
      const k = counts.indexOf(Math.max(...counts));
      result.counts = [counts, k];
      $$(".r-why-row input")[k].click();
      // the page drawn again after the model changed: its count of hidden lines and "Clear all"
      wait(() => model().shown.lines < result.n && text(".r-summary-count").includes("hidden") && button("Clear all"), () => {
        result.hidden = [result.n - model().shown.lines, text(".r-summary-count"), $$(".r-why-row input").map((i) => i.checked)];
        button("Clear all").click();
        wait(() => model().shown.lines === result.n && !text(".r-summary-count").includes("hidden"), () => {
          result.cleared = $$(".r-why-row input").map((i) => i.checked);
          next();
        });
      });
    });
  },
  noTight(next) {
    model().setFilters({...model().filters, clrMin: 1});
    later(() => { result.keyAfter = [!!$(".r-tight-key"), $$(".r-rows .r-tight").length]; next(); });
  },
});
"""

# The first line of the run made tight (0.99 m) and the highest on average, so its spot is the list's first row (the
# store's columns: test_web.store_with)
TIGHT_LINE = {"clr": 0.99, "hmean": 10000}


def _spaced(n: int) -> str:
    """A count as the page writes it: a no-break space as the thousands separator."""
    return f"{n:,}".replace(",", " ")


@pytest.mark.skipif(not os.path.exists(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
                    reason="needs Microsoft Edge")
def test_page_says_found_and_what_a_line_stands_for(tmp_path, monkeypatch):
    """The result page of a run made with the option (here with the no-fall zone and A-frames): the head's counts
    with a no-break space as the thousands separator, a second line "1 234 found. Why so many?" (with what that
    means as its title) whose box says what the found lines are and how many of the run's lines need each class of
    rigging (adding up to its lines; a cleared "Show" hides that class like a filter, "Clear all" shows it again);
    a line's details how many found lines it stands for. The tight mark on every row under 1 m and on no other,
    its key above the list only while a row is tight, its words with the A-frames, and without them on a run
    without A-frames, the profile card's clearance rounded down as the rows'. A run without the option shows no
    second line and no box; one made with it without the no-fall zone and A-frames only the box's first sentence."""
    import test_web as tw
    monkeypatch.delenv("ESRI_API_KEY", raising=False)
    monkeypatch.setattr("settings.SECRETS_DIR", str(tmp_path / "no-secrets"))
    results = {}
    for name, extra in (("on", ("--same-line-square", "5", "--end-zone", "5", "--anchor-lift", "2")), ("off", ())):
        run_id = tw._clip_run(tmp_path, monkeypatch, "--name", name, *extra)
        folder = tmp_path / "runs" / run_id
        page = tw._map_page(folder, "square_test", tw.MAP_HELPERS + PAGE_SCRIPT, before_data=tw.INTROS_SEEN,
                            first=TIGHT_LINE)
        r = tw._result_in(tw._edge_page(tmp_path, f"runs/{run_id}/{page}", size="1280,800", profile=f"edge-{name}"))
        assert "timeout" not in r and r["at"] == "end" and "error" not in r, r
        results[name] = (r, json.loads(_read(str(folder), "run.json"))["summary"])
    # the run without the option, its head given a count of found lines: a run made with the square rule without
    # the no-fall zone and A-frames (no new search)
    page = tw._map_page(folder, "plain_test", tw.MAP_HELPERS + PAGE_SCRIPT, before_data=tw.INTROS_SEEN,
                        head={"found": 12345, "square": 5}, first=TIGHT_LINE)
    plain = tw._result_in(tw._edge_page(tmp_path, f"runs/{run_id}/{page}", size="1280,800", profile="edge-plain"))
    assert "timeout" not in plain and plain["at"] == "end" and "error" not in plain, plain
    assert plain["foundLine"] == f"{_spaced(12345)} found. Why so many?" and plain["counts"] is None, plain
    assert plain["why"] == {"text": f"Each line stands for the found lines a few metres from it: {_spaced(12345)} in all.",
                            "rows": [], "bar": False}, plain
    r, summary = results["on"]
    found, n = summary["found"], summary["lines"]
    assert found > 2 * n and r["sum"] == found and r["found"][:2] == [found, 5] and r["n"] == n, r
    assert f"{_spaced(n)} lines" in r["summary"] and "found" not in r["summary"] and found >= 1000, r
    assert r["foundLine"] == f"{_spaced(found)} found. Why so many?" and "5 m anchor squares" in r["found"][2], r
    assert r["why"]["text"] == (f"Each line stands for the found lines a few metres from it: {_spaced(found)} in all. "
                                f"Of all {_spaced(n)} lines of the result:"), r
    counts, k = r["counts"]
    assert sum(counts) == n and r["hidden"][0] == counts[k] > 0, r
    assert f"{_spaced(counts[k])} hidden by filters" in r["hidden"][1] and r["hidden"][2] == [j != k for j in range(3)], r
    assert r["cleared"] == [True] * 3 and len(r["why"]["rows"]) == 3, r
    assert r["why"]["rows"][2].startswith(f"{_spaced(counts[2])} need") and r["why"]["rows"][2].endswith("A-framesShow"), r
    stands = dict(r["facts"])["Stands for"]
    assert stands == (f"{_spaced(r['stands'])} found lines between the same two anchor squares" if r["stands"] > 1 else
                      "this line only: no other was found between its two anchor squares"), r
    assert r["marks"] and r["first"] == [True, "0.9 m"] and r["keyAfter"] == [False, 0], r
    assert r["key"] == "Tight: under 1 m clear at the tightest point, with the 2 m A-frames up.", r
    assert r["tightLine"] == "Tight: 0.9 m clear at its tightest point, with the 2 m A-frames up.", r
    assert "min. clearance 0.9 m" in r["card"] and "min. clearance 1.0 m" not in r["card"], r
    r, summary = results["off"]
    assert "found" not in summary and "found" not in r["summary"] and r["found"] == [None, None, None], r
    assert r["summary"].endswith(f"{_spaced(summary['lines'])} lines") and r["sum"] == 0 and r["stands"] is None, r
    assert "Stands for" not in dict(r["facts"]) and r["foundLine"] == "" and r["why"] is None, r
    assert r["marks"] and r["first"] == [True, "0.9 m"] and r["keyAfter"] == [False, 0], r
    assert r["key"] == "Tight: under 1 m clear at the tightest point." and r["tightLine"] == (
        "Tight: 0.9 m clear at its tightest point."), r
