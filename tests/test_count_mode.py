"""The count mode of the search (the country layer, docs/country-precompute/contract.md, section 1):
find_valid_lines with a sink, covered_pixels, the sag table of T(L), plan_search(tiled=False),
fixed_tiles and count_tile. Offline, on the Żabi Koń clip of tests/data."""

import dataclasses
import json
import math
import os
import sys

import numpy as np
import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
DATA = os.path.join(REPO, "tests", "data")
CLIP = os.path.join(DATA, "zabi_kon_nmt.tif")
OFFLINE_ENV = {"HTTP_PROXY": "http://127.0.0.1:9", "HTTPS_PROXY": "http://127.0.0.1:9", "NO_PROXY": "",
               "FINDALINE_PROGRESS": "text"}
SQUARE = {"type": "Polygon", "coordinates": [[[19.7522, 50.1546], [19.7590, 50.1546], [19.7590, 50.1580],
                                              [19.7522, 50.1580], [19.7522, 50.1546]]]}


@pytest.fixture
def offline(monkeypatch):
    for key, value in OFFLINE_ENV.items():
        monkeypatch.setenv(key, value)


def _plan(tmp_path, tiled=True, **values):
    import search
    from params import SearchParams
    params = SearchParams(water="off", fill_gaps="off", **values)
    return search.plan_search(params, search.Paths(str(tmp_path), str(tmp_path / "work")), lambda kind, text: None,
                              tiled=tiled)


def _clip_circle(tmp_path, **values):
    """The plan and data of a circle on the clip (step 1 offline)."""
    import search
    plan = _plan(tmp_path, elevation_file=CLIP, northing=254608, easting=553966, radius=290, **values)
    return plan, search.prepare_data(plan)


def _sorted(columns):
    """The columns in the order of their anchors' pixels."""
    a1, a2 = columns["a1"], columns["a2"]
    order = np.lexsort((a2[:, 1], a2[:, 0], a1[:, 1], a1[:, 0]))
    return {name: column[order] for name, column in columns.items()}


def _sink_parts(plan, data, table, threads=None):
    """search._pair_search with a sink: the parts handed to it and the stats."""
    import search
    plan.params = plan.params.model_copy(update={"threads": threads})
    found = search._anchors(plan, data)
    plan.funnel = {}  # the counts of the pair search only
    parts = []
    assert search._pair_search(plan, data, found, None, table, sink=parts.append) is None
    return parts, dict(plan.funnel)


def _joined(parts):
    import helpers as sh
    return sh.LineTable.concat(parts).columns if parts else sh.LineTable.empty().columns


def _assert_same(a, b):
    assert list(a) == list(b)
    for name, column in a.items():
        assert b[name].dtype == column.dtype and b[name].shape == column.shape, name
        assert np.array_equal(b[name], column, equal_nan=column.dtype.kind == "f"), name


@pytest.mark.parametrize("model", ["formula", "sag", "tension"])
def test_sink_parts_equal_the_table(tmp_path, offline, monkeypatch, model):
    """The sink's parts, joined and sorted by their anchors, are the table of find_valid_lines
    without a sink (every column), and the funnel's counts are the same, with any slice of anchors
    and any number of pending pairs."""
    import helpers as sh
    import linesearch as ls
    import sag as sg
    import search
    values = {"min_length": 30, "max_length": 200}
    if model != "formula":
        values["model"] = "sag"
    plan, data = _clip_circle(tmp_path, **values)
    table = None
    if model == "sag":
        table = sg.EnvelopeTable(plan.rigging, 30, 200)
    elif model == "tension":
        table = sg.TensionTable(plan.rigging, 30, 200, [(50, 2.0), (150, 6.0)])
    found = search._anchors(plan, data)
    plan.funnel = {}
    whole = search._pair_search(plan, data, found, None, table)
    stats = dict(plan.funnel)
    assert len(whole) > 100 and set(whole.columns) == {"a1", "a2", *sh.LINE_VALUES}
    expected = _sorted(whole.columns)
    for chunk, part in ((ls.SINK_CHUNK, ls.EVAL_PART), (37, 100), (1, 1), (5000, 10 ** 9)):
        monkeypatch.setattr(ls, "SINK_CHUNK", chunk)
        monkeypatch.setattr(ls, "EVAL_PART", part)
        parts, sink_stats = _sink_parts(plan, data, table)
        assert all(len(p) for p in parts)
        assert all(set(p.columns) == {"a1", "a2", *sh.LINE_VALUES} for p in parts)
        _assert_same(expected, _sorted(_joined(parts)))
        assert sink_stats == stats, (chunk, part)
    with pytest.raises(ValueError):
        ls.find_valid_lines(data.elevation, None, found.anchors, plan.resolution, 30, 200, sink=lambda t: None,
                            check=lambda n: None)


def test_sink_parts_independent_of_threads(tmp_path, offline, monkeypatch):
    """The parts handed to the sink do not depend on the number of threads (the lines as a
    multiset; their parts' sizes too)."""
    import linesearch as ls
    import numba
    plan, data = _clip_circle(tmp_path, min_length=30, max_length=200)
    monkeypatch.setattr(ls, "SINK_CHUNK", 64)
    monkeypatch.setattr(ls, "EVAL_PART", 500)
    most = numba.config.NUMBA_NUM_THREADS
    results = []
    try:
        for threads in sorted({1, min(3, most), most}):
            parts, stats = _sink_parts(plan, data, None, threads)
            results.append(([len(p) for p in parts], _sorted(_joined(parts)), stats))
    finally:
        numba.set_num_threads(most)
    sizes, columns, stats = results[0]
    assert len(sizes) > 1
    for other_sizes, other_columns, other_stats in results[1:]:
        assert other_sizes == sizes and other_stats == stats
        _assert_same(columns, other_columns)


@pytest.mark.parametrize("res", [0.5, 1.0, 2.0, 5.0])
def test_covered_pixels(monkeypatch, res):
    """covered_pixels > 0 exactly where covered_metres > 0, in parts of any size; zeros without a mask."""
    import linesearch as ls
    rng = np.random.default_rng(7)
    mask = rng.random((200, 200)) < 0.05
    a1 = rng.integers(0, 200, (400, 2))
    a2 = rng.integers(0, 200, (400, 2))
    pixels = ls.covered_pixels(a1, a2, mask)
    assert pixels.dtype == np.int64 and pixels.shape == (400,)
    assert ((pixels > 0) == (ls.covered_metres(a1, a2, res, mask) > 0)).all()
    assert 0 < (pixels > 0).sum() < len(a1)
    for k in range(20):  # the pixels of helpers.line_profile: anchors excluded
        (r1, c1), (r2, c2) = a1[k], a2[k]
        steps = max(abs(r2 - r1), abs(c2 - c1))
        n = sum(bool(mask[r1 + int(np.rint((r2 - r1) * i / steps)), c1 + int(np.rint((c2 - c1) * i / steps))])
                for i in range(1, steps))
        assert pixels[k] == n
    monkeypatch.setattr(ls, "COVERED_PART", 7)
    assert ls.covered_pixels(a1, a2, mask).tolist() == pixels.tolist()
    none = ls.covered_pixels(a1, a2, None)
    assert none.dtype == np.int64 and none.tolist() == [0] * len(a1)
    assert ls.covered_pixels(a1[:0], a2[:0], mask).shape == (0,)


def test_tension_table():
    """parse_tension, tension_at, and a TensionTable of one point equal to the EnvelopeTable of
    that pretension, bit for bit; more tension at the long spans, less sag there."""
    import sag as sg
    points = sg.parse_tension("1500:6,300:2.5,5000:15")
    assert points == [(300, 2.5), (1500, 6), (5000, 15)]
    assert sg.tension_at(points, 100) == 2.5 and sg.tension_at(points, 9000) == 15
    assert sg.tension_at(points, 900) == pytest.approx(4.25)
    assert sg.tension_at([(100, 4)], 20) == 4
    rig = sg.Rigging(pretension=2.5, stretch=2.1, webbing_weight=41.0)
    one = sg.TensionTable(rig, 20, 300, [(100, 4.0)])
    original = sg.EnvelopeTable(dataclasses.replace(rig, pretension=4.0), 20, 300)
    assert np.array_equal(one.sag, original.sag) and np.array_equal(one.spans, original.spans)
    assert np.array_equal(one.fractions, original.fractions) and one.rig is rig
    assert np.array_equal(one(150, 10, np.linspace(0, 1, 9)), original(150, 10, np.linspace(0, 1, 9)))
    longer = sg.TensionTable(sg.Rigging(pretension=4), 20, 300, [(20, 4), (300, 10)])
    plain = sg.EnvelopeTable(sg.Rigging(pretension=4), 20, 300)
    assert np.array_equal(longer.sag[0], plain.sag[0])          # 4 kN at the shortest span
    assert (longer.sag[-1, :, 1:-1] < plain.sag[-1, :, 1:-1]).all()


def test_plan_without_tiles(tmp_path, offline):
    """plan_search(tiled=False): an area gets one grid (with its outline), whatever its size."""
    path = tmp_path / "square.geojson"
    path.write_text(json.dumps({"type": "Feature", "properties": {}, "geometry": SQUARE}))
    values = {"elevation_file": CLIP, "area": str(path), "max_length": 150, "tile_size": 150}
    tiled = _plan(tmp_path / "a", **values)
    one = _plan(tmp_path / "b", tiled=False, **values)
    assert tiled.tiles and tiled.tile_core == 150
    assert one.tiles is None and one.tile_core is None and one.grid.area_shape is not None
    assert one.grid == tiled.grid


def _krovak_clip(tmp_path) -> str:
    """The clip reprojected to EPSG:8353 (S-JTSK [JTSK03] / Krovak East North: negative
    coordinates), 1 m."""
    import rasterio as rio
    from rasterio.warp import Resampling, calculate_default_transform, reproject
    out = str(tmp_path / "clip_8353.tif")
    with rio.open(CLIP) as src:
        transform, width, height = calculate_default_transform(src.crs, "EPSG:8353", src.width, src.height,
                                                               *src.bounds, resolution=1.0)
        profile = src.profile.copy()
        profile.update(crs="EPSG:8353", transform=transform, width=width, height=height, nodata=np.nan,
                       dtype="float32")
        with rio.open(out, "w", **profile) as dst:
            reproject(rio.band(src, 1), rio.band(dst, 1), src_nodata=src.nodata, dst_nodata=np.nan,
                      resampling=Resampling.bilinear)
    return out


def _krovak_plan(tmp_path, **values):
    path = tmp_path / "square.geojson"
    path.write_text(json.dumps({"type": "Feature", "properties": {}, "geometry": SQUARE}))
    return _plan(tmp_path / "data", tiled=False, elevation_file=_krovak_clip(tmp_path), area=str(path),
                 max_length=150, **values)


def test_fixed_tiles(tmp_path, offline):
    """fixed_tiles: cores of core_m at its multiples (negative Krovak coordinates too), named by
    their corners, rows from the north, west to east, covering the area; each grid the core with
    _overlap around it clipped to the plan's grid, on the source's pixel edges."""
    import search
    from shapely.geometry import box
    from shapely.ops import unary_union
    plan = _krovak_plan(tmp_path)
    assert plan.crs == "EPSG:8353" and plan.tiles is None
    shape = plan.grid.area_shape
    assert shape.bounds[2] < 0 and shape.bounds[3] < 0
    tiles = search.fixed_tiles(plan, 150)
    assert len(tiles) >= 4
    overlap = search._overlap(plan.params, plan.resolution)
    g_left, g_bottom, g_right, g_top = plan.grid.bounds
    for tile in tiles:
        left, bottom, right, top = tile.core
        assert right - left == top - bottom == 150
        assert left % 150 == 0 and bottom % 150 == 0
        assert tile.name == f"E{int(left)}_N{int(bottom)}" and tile.name.startswith("E-") and "_N-" in tile.name
        assert shape.intersection(box(*tile.core)).area > 0
        assert tile.grid.res == plan.resolution and tile.grid.crs == plan.crs
        assert tile.grid.area_shape is shape
        t_left, t_bottom, t_right, t_top = tile.grid.bounds
        assert t_left == pytest.approx(max(g_left, left - overlap), abs=1)
        assert t_top == pytest.approx(min(g_top, top + overlap), abs=1)
        assert t_right == pytest.approx(min(g_right, right + overlap), abs=1)
        assert t_bottom == pytest.approx(max(g_bottom, bottom - overlap), abs=1)
        assert (tile.grid.left - plan.grid.left) % plan.resolution == 0
        assert (tile.grid.top - plan.grid.top) % plan.resolution == 0
    keys = [(-t.core[1], t.core[0]) for t in tiles]
    assert keys == sorted(keys) and len(set(t.name for t in tiles)) == len(tiles)
    assert unary_union([box(*t.core) for t in tiles]).contains(shape)
    # only the cores the area touches with some area: a coarser lattice gives fewer, the same cover
    big = search.fixed_tiles(plan, 1000)
    assert 1 <= len(big) <= 4 and unary_union([box(*t.core) for t in big]).contains(shape)


def _lines_by_xy(grid, columns, core=None):
    """The lines of a count as rows of the first anchor's and the second anchor's (x, y) and the
    LINE_VALUES (NaN as None), only those whose first anchor lies in core when given."""
    import helpers as sh
    x1, y1 = grid.pixel_to_xy(columns["a1"][:, 0], columns["a1"][:, 1])
    x2, y2 = grid.pixel_to_xy(columns["a2"][:, 0], columns["a2"][:, 1])
    rows = []
    for k in range(len(x1)):
        p, q = (float(x1[k]), float(y1[k])), (float(x2[k]), float(y2[k]))
        first = min(p, q)
        if core is not None and not (core[0] <= first[0] < core[2] and core[1] <= first[1] < core[3]):
            continue
        values = tuple(None if math.isnan(v) else v for v in (float(columns[n][k]) for n in sh.LINE_VALUES))
        rows.append((p, q, values, int(columns["water_px"][k])))
    return sorted(rows, key=lambda r: (r[0], r[1]))


@pytest.mark.parametrize("model", ["formula", "tension"])
def test_count_tile_over_fixed_tiles(tmp_path, offline, model):
    """count_tile over fixed tiles gives exactly the lines of one grid (the anchors' coordinates and
    every value), on the clip in EPSG:8353 (water and gap filling off, as test_area_in_tiles); one
    grid's count gives the lines of _lines."""
    import sag as sg
    import search
    values = {"model": "sag"} if model == "tension" else {}
    plan = _krovak_plan(tmp_path, **values)
    table = sg.TensionTable(plan.rigging, plan.params.min_length, plan.params.max_length,
                            [(30, 2.5), (150, 6.0)]) if model == "tension" else None
    data = search.prepare_data(plan)
    parts = []
    funnel = search.count_tile(plan, data, None, parts.append, table)
    assert funnel is plan.funnel and funnel["grids"] == 1 and funnel["valid"] == sum(len(p) for p in parts)
    assert all(p.columns["water_px"].dtype == np.int64 and not p.columns["water_px"].any() for p in parts)
    one = _lines_by_xy(plan.grid, _joined(parts))
    assert len(one) > 100
    if model == "formula":
        lines, _ = search._lines(dataclasses.replace(plan, funnel={}), data)
        assert len(lines) == len(one)
    del data
    tiled = []
    tiles = search.fixed_tiles(plan, 150)
    assert len(tiles) >= 4
    for tile in tiles:
        work = tmp_path / "work" / tile.name
        tile_plan = dataclasses.replace(plan, grid=tile.grid, paths=search.Paths(plan.paths.data, str(work)),
                                        tiles=None, funnel={})
        tile_parts = []
        search.count_tile(tile_plan, search.prepare_data(tile_plan), tile.core, tile_parts.append, table)
        if tile_parts:
            tiled += _lines_by_xy(tile.grid, _joined(tile_parts), tile.core)
    assert sorted(tiled, key=lambda r: (r[0], r[1])) == one


def _timed_values(monkeypatch):
    """The calls of terrain.prominence and terrain.drop, and the bars seen, as a list of their names
    (the bars of search's own progress, by their label: progress.bars() leaves the bars it found, with theirs)."""
    import search
    import terrain
    seen = []
    for name in ("prominence", "drop"):
        kernel = getattr(terrain, name)
        monkeypatch.setattr(terrain, name, lambda *args, k=kernel, n=name, **kw: (seen.append(n), k(*args, **kw))[1])
    listener = lambda state: seen.append(("bar", state["stage"], state["done"])) if state.get("bar") else None
    search.progress.subscribe(listener)
    return seen, lambda: search.progress.unsubscribe(listener)


@pytest.mark.parametrize("chunk, part, calls", [(None, None, None), (16, 50, 1000), (16, 50, 2), (16, 50, 0)])
def test_count_tile_computes_the_anchor_values_of_the_lines(tmp_path, offline, monkeypatch, chunk, part, calls):
    """count_tile computes prominence and drop of the anchors of each part's lines when the part comes
    (terrain.py on the crop around them), each anchor once, after linesearch.SUBSET_CALLS computations
    every useful anchor not known yet in the rows a later line can reach, and hands the sink what a
    search computing them first does, bit for bit; the bar of the pairs goes on after each computation.
    One part; many parts, subsets only; the switch after two; the switch at the first line."""
    import linesearch as ls
    import search
    import terrain
    if chunk is not None:
        monkeypatch.setattr(ls, "SINK_CHUNK", chunk)
        monkeypatch.setattr(ls, "EVAL_PART", part)
        monkeypatch.setattr(ls, "SUBSET_CALLS", calls)
    plan = _krovak_plan(tmp_path)
    data = search.prepare_data(plan)
    first = []
    search._pair_search(plan, data, search._anchors(plan, data), None, None, sink=first.append)
    asked, useful = {"prominence": [], "drop": []}, []
    for name in asked:
        kernel = getattr(terrain, name)
        monkeypatch.setattr(terrain, name, lambda z, a, *args, k=kernel, n=name, **kw:
                            (asked[n].append((np.array(a), kw.get("crop"))), k(z, a, *args, **kw))[1])
    free = ls.free_directions
    monkeypatch.setattr(ls, "free_directions", lambda *a, **k: (lambda r: (useful.append(r[0]), r)[1])(free(*a, **k)))
    bars = []
    listener = lambda state: bars.append((state["stage"], state["done"])) if state.get("bar") else None
    search.progress.subscribe(listener)
    try:
        plan.funnel = {}
        later = []
        search.count_tile(plan, data, None, later.append)
    finally:
        search.progress.unsubscribe(listener)
    assert sum(len(p) for p in later) > 100 and len(later) > (1 if chunk else 0)
    a, b = _sorted(_joined(first)), _sorted(_joined(later))
    del b["water_px"]
    _assert_same(a, b)
    # the anchors computed: each once, on a crop, the lines' own while subsets, all useful after the switch
    anchors = search._anchors(plan, data, quiet=True, deferred=True).anchors
    w = data.elevation.shape[1]
    flat = anchors[:, 0] * w + anchors[:, 1]
    sets = [np.searchsorted(flat, a[:, 0] * w + a[:, 1]) for a, crop in asked["prominence"]]
    assert all(crop is True for _, crop in asked["prominence"] + asked["drop"])
    assert [len(s) for s in sets] == [len(a) for a, _ in asked["drop"]]
    done = np.concatenate(sets)
    assert len(np.unique(done)) == len(done)  # each anchor once
    in_lines = set(np.searchsorted(flat, b["a1"][:, 0] * w + b["a1"][:, 1]).tolist()) | \
        set(np.searchsorted(flat, b["a2"][:, 0] * w + b["a2"][:, 1]).tolist())
    limit = ls.SUBSET_CALLS
    assert 1 <= len(sets) <= limit + 1
    if len(sets) > limit:  # switched: the useful anchors not known before, from the rows a later line can reach
        computed, whole = set(done.tolist()), set(useful[0].tolist())
        assert in_lines <= computed <= whole
        missing = np.array(sorted(whole - computed), dtype=np.int64)
        extra = np.setdiff1d(sets[-1], np.array(sorted(in_lines), dtype=np.int64))
        assert len(extra)
        if len(missing):
            assert anchors[missing, 0].max() < anchors[extra, 0].min()
    else:
        assert set(done.tolist()) == in_lines
    assert any(len(s) < len(anchors) for s in sets)
    starts = [k for k, bar in enumerate(bars) if bar == ("anchor prominence and drop", False)  # its start, not its update
              and (k == 0 or bars[k - 1][0] != "anchor prominence and drop")]
    assert len(starts) == len(sets) and bars[:starts[0]] and ("anchor pairs", False) in bars[:starts[0]]
    for k in starts:  # the bar of the pairs put back right after each computation
        done_at = bars.index(("anchor prominence and drop", True), k)
        assert bars[done_at + 1] == ("anchor pairs", False)
    assert bars[-1] == ("anchor pairs", True)


@pytest.mark.parametrize("model", ["formula", "tension"])
def test_count_tile_carries_the_lift_values(tmp_path, offline, monkeypatch, model):
    """With the no-fall zone and A-frames (5 m, 2 m) every part handed to the sink carries the A-frame
    heights of its lines ("lift_needed", "lift_no_zone"), those the search's table has for the same
    lines (every column equal, bit for bit); the ladder adds values only (without it the same lines and
    values); at 0 / 0 the parts have the columns of before, no END_VALUES."""
    import helpers as sh
    import linesearch as ls
    import sag as sg
    import search
    for ends in ({"end_zone": 5.0, "anchor_lift": 2.0}, {}):
        values = {"model": "sag", **ends} if model == "tension" else dict(ends)
        folder = tmp_path / ("ends" if ends else "plain")
        folder.mkdir()
        plan = _krovak_plan(folder, **values)
        table = sg.TensionTable(plan.rigging, plan.params.min_length, plan.params.max_length,
                                [(30, 2.5), (150, 6.0)]) if model == "tension" else None
        data = search.prepare_data(plan)
        whole = search._pair_search(plan, data, search._anchors(plan, data), None, table)
        plan.funnel = {}
        parts = []
        search.count_tile(plan, data, None, parts.append, table)
        assert len(parts) and sum(len(p) for p in parts) == len(whole) > 100
        columns = {"a1", "a2", *sh.LINE_VALUES, "water_px"} | (set(sh.END_VALUES) if ends else set())
        assert all(set(p.columns) == columns for p in parts)
        counted = _sorted(_joined(parts))
        del counted["water_px"]
        _assert_same(_sorted(whole.columns), counted)
        if not ends:
            continue
        assert (counted["lift_needed"] > 0).any() and (counted["lift_no_zone"] > counted["lift_needed"]).any()
        find = ls.find_valid_lines  # the same count without the ladder: the same lines and values
        monkeypatch.setattr(ls, "find_valid_lines", lambda *a, **k: find(*a, **{**k, "zones": ()}))
        plan.funnel = {}
        plain = []
        search.count_tile(plan, data, None, plain.append, table)
        monkeypatch.setattr(ls, "find_valid_lines", find)
        plain = _sorted(_joined(plain))
        for name in ("a1", "a2", *sh.LINE_VALUES, "water_px"):
            assert np.array_equal(plain[name], _sorted(_joined(parts))[name], equal_nan=True), name
        del data


@pytest.mark.parametrize("calls", [None, 0])
def test_count_tile_releases_its_grids(tmp_path, offline, monkeypatch, calls):
    """After a count (lines, lazy anchor values, the switch to every useful anchor or not) nothing keeps the
    grids of step 1: deleting the data frees the memory-mapped terrain by reference counting alone, with the
    cyclic collector off, and step 1 writes the same work path again (Windows refuses to write a file while a
    view of it lives: the next grid of a work path, a test's fixture or a tile of a worker). A count on another
    plan first compiles what numba has not cached (the first compilation in a process may keep the frames of
    its call alive, whatever the count holds)."""
    import gc
    import weakref
    import linesearch as ls
    import search
    if calls is not None:
        monkeypatch.setattr(ls, "SUBSET_CALLS", calls)
    (tmp_path / "warm").mkdir()
    warm = _krovak_plan(tmp_path / "warm")
    search.count_tile(warm, search.prepare_data(warm), None, [].append)
    plan = _krovak_plan(tmp_path)
    data = search.prepare_data(plan)
    terrain = weakref.ref(data.elevation)
    parts = []
    enabled = gc.isenabled()
    gc.collect()
    gc.disable()
    try:
        search.count_tile(plan, data, None, parts.append)
        assert sum(len(p) for p in parts) > 100
        del data, parts
        assert terrain() is None
        again = search.prepare_data(plan)  # the same work path written again
        assert again.elevation.shape == (plan.grid.height, plan.grid.width)
        del again
    finally:
        if enabled:
            gc.enable()


def test_lazy_anchor_values():
    """LazyAnchorValues: the anchors of the pairs not known yet computed, each once, in increasing
    order; the values of every anchor returned (NaN where not computed); after `calls` computations
    the next takes the rest too, in the rows from floor() on; nothing computed when every anchor of the
    pairs is known."""
    import linesearch as ls
    truth = np.column_stack([np.arange(20.0), -np.arange(20.0)])
    truth[3] = np.nan  # a value NaN (an anchor without data) is a value, never asked again
    asked, after = [], []
    lazy = ls.LazyAnchorValues(lambda idx: (asked.append(idx.tolist()), truth[idx])[1], 20, calls=2)
    lazy.after = lambda: after.append(len(asked))
    lazy.rest = np.array([0, 3, 5, 7, 9, 11, 13])
    lazy.rows, lazy.floor = np.arange(20) // 2, lambda: 3  # anchor 0 (row 0) never in a later line
    got = lazy(np.array([[5, 3], [3, 1]]))
    assert asked == [[1, 3, 5]] and after == [1]
    assert np.array_equal(got[[1, 3, 5]], truth[[1, 3, 5]], equal_nan=True) and np.isnan(got[[0, 2, 4]]).all()
    lazy(np.array([[1, 5], [5, 3]]))
    assert asked == [[1, 3, 5]]  # all known: nothing computed
    lazy(np.array([[2, 1]]))
    assert asked == [[1, 3, 5], [2]]
    got = lazy(np.array([[19, 2]]))  # the third: the rest not known yet in rows from 3 on with it
    assert asked[-1] == [7, 9, 11, 13, 19] and lazy.computed == 3 and after == [1, 2, 3]
    assert np.array_equal(got[lazy.known], truth[lazy.known], equal_nan=True)
    assert np.isnan(got[~lazy.known]).all() and lazy.known.sum() == 9
    lazy(np.array([[0, 19]]))  # an anchor left out by the floor is still computed when a line has it
    assert asked[-1] == [0] and lazy.known[0]


def test_count_tile_without_a_line_computes_no_anchor_values(tmp_path, offline, monkeypatch):
    """Pairs evaluated, no line passing: neither prominence nor drop is computed, the sink's parts
    are empty."""
    import search
    plan = _krovak_plan(tmp_path, min_height=5000.0)
    data = search.prepare_data(plan)
    seen, stop = _timed_values(monkeypatch)
    try:
        parts = []
        funnel = search.count_tile(plan, data, None, parts.append)
    finally:
        stop()
    assert funnel["found"] > 0 and funnel["valid"] == 0 and funnel["left_out"] > 0
    assert sum(len(p) for p in parts) == 0
    assert "prominence" not in seen and "drop" not in seen


@pytest.mark.parametrize("limit", [{"min_prominence": 1.0}, {"min_prominence_both": 1.0}, {"min_drop": 1.0}])
def test_count_tile_computes_anchor_values_first_under_a_limit(tmp_path, offline, monkeypatch, limit):
    """A limit on the anchors needs their values before the pair search."""
    import search
    plan = _krovak_plan(tmp_path, **limit)
    data = search.prepare_data(plan)
    seen, stop = _timed_values(monkeypatch)
    try:
        search.count_tile(plan, data, None, [].append)
    finally:
        stop()
    stages = [s[1] for s in seen if isinstance(s, tuple)]
    assert seen.count("prominence") == 1
    assert stages.index("anchor prominence and drop") < stages.index("free directions")


def test_tile_inside_the_country_skips_its_coverage(tmp_path, offline):
    """Plan.border False (a tile inside the outline), step 1 in strips: the mask full without a burn, no
    line about the coverage; the rest of step 1 goes on. With a border the line is there."""
    import search
    plan = _krovak_plan(tmp_path)
    said = []
    plan.emit = lambda kind, text: said.append(text)
    search.prepare_data(plan, strips=True)
    assert any(text.startswith("Elevation data:") for text in said)
    said.clear()
    inside = dataclasses.replace(plan, border=False, paths=search.Paths(plan.paths.data, str(tmp_path / "inside")))
    data = search.prepare_data(inside, strips=True)
    assert data.mask.all() and data.mask.shape == data.elevation.shape
    assert not any(text.startswith("Elevation data:") for text in said)


def test_count_tile_without_anchors(tmp_path, offline):
    """A grid without steep terrain hands the sink nothing and raises nothing."""
    import search
    plan = _krovak_plan(tmp_path, slope_threshold=89.9)
    parts = []
    funnel = search.count_tile(plan, search.prepare_data(plan), None, parts.append)
    assert parts == [] and funnel.get("valid", 0) == 0


def _box_file(path, west, east, south=50.152, north=50.161) -> str:
    ring = [[west, south], [east, south], [east, north], [west, north], [west, south]]
    path.write_text(json.dumps({"type": "Feature", "properties": {},
                                "geometry": {"type": "Polygon", "coordinates": [ring]}}))
    return str(path)


def _grown(plan):
    """The plan's grid grown by its longest line (as country._grown gives a country's band)."""
    import grid as gd
    g, res = plan.grid, plan.resolution
    reach = math.ceil(plan.params.max_length / res) * res
    left, bottom, right, top = g.bounds
    wide = gd.make_grid((left - reach, bottom - reach, right + reach, top + reach), res, g.crs,
                        plan.source.grid_origin)
    wide.area_shape = g.area_shape
    return dataclasses.replace(plan, grid=wide)


SPLIT_LON = 19.7561  # tests/test_border_study.py's BORDER_LON: lines from the tower to the rocks west of it cross it
SIDES = {"west": (19.750, SPLIT_LON, {1}), "east": (SPLIT_LON, 19.762, {2})}  # its anchor first by longitude, or not


def _split(tmp_path, side="west", **values):
    """The clip (EPSG:2180, its data within the box of the whole) split at SPLIT_LON: the plan of a box around
    the whole clip (one grid) and that of one side (its grid grown by the longest line, as a country's band),
    offline, water and gap filling off."""
    clip = CLIP
    whole = _plan(tmp_path / "whole", tiled=False, elevation_file=clip, max_length=150,
                  area=_box_file(tmp_path / "whole.geojson", 19.750, 19.762), **values)
    west, east, _ = SIDES[side]
    plan = _plan(tmp_path / side, tiled=False, elevation_file=clip, max_length=150,
                 area=_box_file(tmp_path / f"{side}.geojson", west, east), **values)
    return whole, _grown(plan)


def _first_by_lonlat(grid, a1, a2):
    from pyproj import Transformer
    to = Transformer.from_crs(grid.crs, "EPSG:4326", always_xy=True)
    lon1, lat1 = (np.asarray(v) for v in to.transform(*grid.pixel_to_xy(a1[:, 0], a1[:, 1])))
    lon2, lat2 = (np.asarray(v) for v in to.transform(*grid.pixel_to_xy(a2[:, 0], a2[:, 1])))
    return (lon1 < lon2) | ((lon1 == lon2) & (lat1 <= lat2))


@pytest.mark.parametrize("model", ["formula", "tension"])
@pytest.mark.parametrize("side", ["west", "east"])
def test_count_tile_across_a_border(tmp_path, offline, model, side):
    """A grid split by an outline, with the partner anchors beyond it (Plan.partners): the lines with a
    border are those of one grid over both sides with one anchor in the outline (every value, the
    partners' prominence and drop too), those without the lines of one grid with both anchors in it and
    the lines of the clipped grid without partners; "partner" 7 (an elevation file has no neighbour:
    its own data beyond the outline), "border" 1 exactly when the anchor in the outline is the first by
    (lon, lat) (always west of the meridian, never east of it), both 0 inside."""
    import area as ar
    import sag as sg
    import search
    values = {"model": "sag"} if model == "tension" else {}
    whole, cut = _split(tmp_path, side, **values)
    table = sg.TensionTable(cut.rigging, 30, 150, [(30, 2.5), (150, 6.0)]) if model == "tension" else None
    parts = []
    search.count_tile(whole, search.prepare_data(whole), None, parts.append, table)
    one = _joined(parts)
    inside = ar.Polygon(cut.area.geometry).mask(whole.grid)
    in1 = inside[one["a1"][:, 0], one["a1"][:, 1]]
    in2 = inside[one["a2"][:, 0], one["a2"][:, 1]]
    both = {k: v[in1 & in2] for k, v in one.items()}
    across = {k: v[in1 != in2] for k, v in one.items()}
    assert len(both["a1"]) > 0 and len(across["a1"]) > 5
    plain = dataclasses.replace(cut, funnel={}, paths=search.Paths(cut.paths.data, str(tmp_path / "plain")))
    clipped = []
    search.count_tile(plain, search.prepare_data(plain), None, clipped.append, table)
    plan = dataclasses.replace(cut, partners=150.0, funnel={})
    data = search.prepare_data(plan)
    assert data.partner is not None and data.partner.dtype == np.uint8
    assert set(np.unique(data.partner).tolist()) == {0, 7} and not data.partner[data.mask].any()
    counted = []
    funnel = search.count_tile(plan, data, None, counted.append, table)
    got = _joined(counted)
    border, partner = got["border"], got["partner"]
    assert border.dtype == np.int8 and partner.dtype == np.uint8
    assert ((border != 0) == (partner != 0)).all() and set(partner.tolist()) == {0, 7}
    inner = {k: v[border == 0] for k, v in got.items()}
    outer = {k: v[border != 0] for k, v in got.items()}
    assert _lines_by_xy(plan.grid, inner) == _lines_by_xy(whole.grid, both)
    assert _lines_by_xy(plan.grid, inner) == _lines_by_xy(plain.grid, _joined(clipped))
    assert _lines_by_xy(plan.grid, outer) == _lines_by_xy(whole.grid, across)
    assert np.isfinite(outer["prom1"]).all() and np.isfinite(outer["drop2"]).all()
    own1 = data.mask[outer["a1"][:, 0], outer["a1"][:, 1]]
    assert (own1 != data.mask[outer["a2"][:, 0], outer["a2"][:, 1]]).all()
    first = _first_by_lonlat(plan.grid, outer["a1"], outer["a2"])
    assert np.array_equal(outer["border"], np.where(first == own1, 1, 2))
    assert set(outer["border"].tolist()) == SIDES[side][2]
    assert funnel["valid"] == len(got["a1"]) and funnel["anchors"] > plain.funnel["anchors"]


def test_count_tile_with_partners_inside_a_country(tmp_path, offline):
    """Partners asked where none lies beyond the outline (the clip wholly inside it): the same parts and
    funnel as without, their columns of a border all 0; and find_valid_lines with an array of zeros as
    without."""
    import linesearch as ls
    import search
    whole, _ = _split(tmp_path)
    data = search.prepare_data(whole)
    parts, partnered = [], []
    funnel = dict(search.count_tile(dataclasses.replace(whole, funnel={}), data, None, parts.append))
    asked = dataclasses.replace(whole, partners=150.0, funnel={},
                                paths=search.Paths(whole.paths.data, str(tmp_path / "asked")))
    asked_data = search.prepare_data(asked)
    assert asked_data.partner is not None and not asked_data.partner.any()
    assert dict(search.count_tile(asked, asked_data, None, partnered.append)) == funnel
    joined = _sorted(_joined(partnered))
    assert not joined.pop("border").any() and not joined.pop("partner").any()
    _assert_same(_sorted(_joined(parts)), joined)
    found = search._anchors(whole, data)
    args = (data.elevation, None, found.anchors, whole.resolution, 30, 150)
    values = np.column_stack([found.prominence, found.drop])
    zeros = ls.find_valid_lines(*args, partner=np.zeros(len(found.anchors), dtype=np.uint8), anchor_values=values)
    plain = ls.find_valid_lines(*args, anchor_values=values)
    assert len(plain) > 100
    _assert_same(plain.columns, zeros.columns)


@pytest.mark.parametrize("engine", ["numba", "numpy"])
def test_border_lines_over_fixed_tiles(tmp_path, offline, engine):
    """Each side of the split clip counted in fixed tiles as the country layer counts a border tile (the
    partners within the longest line, the footprint grown: country.tile_plan): each line once, by the tile
    whose core holds its anchor in the outline (a line inside: its first anchor in pixel order), and the
    tiles' TileCounters sum to the counter of one grid with partners (lines and spots per key), the lines
    across the border owned (border 1, west) or the partner's (border 2, east)."""
    import country
    import countcube as cc
    import search
    land = country.Country(id="land", name="Land", source="files", area="unused")
    for side in SIDES:
        (tmp_path / side).mkdir()
        _, cut = _split(tmp_path / side, side)
        plan = dataclasses.replace(cut, partners=150.0, funnel={})
        data = search.prepare_data(plan)
        parts = []
        search.count_tile(plan, data, None, parts.append)
        one = _joined(parts)
        origin = cc.origin_of(cut.area.geometry.bounds, 150.0)
        reference = cc.TileCounter(plan.grid, origin, None, (30, 150), True, engine=engine)
        for part in parts:
            reference(part)
        reference = reference.result()
        expected = sorted(_lines_by_xy(plan.grid, one))
        del data
        tiles = search.fixed_tiles(cut, 200)
        assert len(tiles) >= 4
        lines, keys, spots = [], [], []
        for tile in tiles:
            tile_plan = country.tile_plan(land, cut, tile.core,
                                          search.Paths(cut.paths.data, str(tmp_path / side / "tiles" / tile.name)))
            assert tile_plan.border and tile_plan.partners == 150.0  # the clip's tiles all reach the meridian
            grid = tile_plan.grid
            tile_data = search.prepare_data(tile_plan, strips=True)
            counter = cc.TileCounter(grid, origin, tile.core, (30, 150), True, engine=engine)
            tile_parts = []
            search.count_tile(tile_plan, tile_data, tile.core, lambda p: (tile_parts.append(p), counter(p)), None)
            if tile_parts:
                got = _joined(tile_parts)
                mine = got["border"] == 0
                lines += _lines_by_xy(grid, {k: v[mine] for k, v in got.items()}, tile.core)  # inside: first in core
                lines += _lines_by_xy(grid, {k: v[~mine] for k, v in got.items()})  # across: all of them the tile's
            counts = counter.result()
            keys.append((counts.line_keys, counts.line_counts))
            spots.append((counts.spot_ids, counts.spot_records))
            del tile_data
        assert sorted(lines) == expected, side
        k, n = cc.sum_keys(np.concatenate([k for k, _ in keys]), np.concatenate([n for _, n in keys]))
        assert np.array_equal(k, reference.line_keys) and np.array_equal(n, reference.line_counts), side
        ids, records = cc.merge_spots(np.concatenate([i for i, _ in spots]), np.concatenate([r for _, r in spots]))
        assert np.array_equal(ids, reference.spot_ids) and np.array_equal(records, reference.spot_records), side
        found = cc.unpack_keys(reference.line_keys)
        assert {int(b) for b in found["border"]} == {0} | SIDES[side][2], side
        assert set(found["partner"][found["border"] > 0].tolist()) == {7}, side


def test_partner_grid_and_its_last_pass(tmp_path):
    """sources.filling's partner grid: the zone beyond the outline within reach (near()'s square, in strips
    as whole), the source's own data in it marked before the filling, a neighbour's index where it filled,
    and the last pass: 0 outside the zone; own data the neighbour whose fill lies nearest when its rough
    boxes hold them, else the first neighbour whose boxes hold them (a neighbour without boxes holds every
    pixel), else 7."""
    from types import SimpleNamespace
    import sources.filling as filling
    from grid import Grid
    grid = Grid(left=19.0, top=50.0, res=0.01, width=12, height=10, crs="EPSG:4326")
    mask = np.zeros((10, 12), dtype=bool)
    mask[:, :4] = True  # the outline: the four western columns
    whole = filling.partner_zone(mask, 0.025, 0.01)
    assert whole[:, 4:7].all() and not whole[:, 7:].any() and not whole[mask].any()
    rows = filling.partner_zone(mask, 0.025, 0.01, filling.new_mask(str(tmp_path / "zone.npy"), mask.shape), 3)
    assert np.array_equal(np.asarray(rows), whole)
    z = np.full((10, 12), np.nan, dtype=np.float32)
    z[:, :6] = 100.0  # the source's data reach two columns beyond the outline
    np.save(tmp_path / "nmt.npy", z)
    partner = filling.partner_grid(str(tmp_path / "nmt.npy"), whole, str(tmp_path / "partner.npy"), 4)
    assert (partner[:, 4:6] == filling.PARTNER_OWN).all() and not partner[:, :4].any() and not partner[:, 6:].any()
    north = SimpleNamespace(rough_boxes=lambda: [(49.95, 50.0, 18.0, 20.0)])  # the top five rows
    everywhere = SimpleNamespace(rough_boxes=lambda: [(49.0, 51.0, 18.0, 20.0)])
    nowhere = SimpleNamespace(rough_boxes=lambda: [(10.0, 11.0, 0.0, 1.0)])

    def resolved(start, neighbours):
        out = np.array(start)
        filling.resolve_partners(out, whole, neighbours, grid, 3)
        return out

    p = resolved(partner, [north, everywhere])  # nothing filled: the first whose boxes hold them
    assert (p[:5, 4:6] == 1).all() and (p[5:, 4:6] == 2).all() and not p[:, 6:].any() and not p[:, :4].any()
    assert (resolved(partner, [nowhere])[:, 4:6] == filling.PARTNER_UNKNOWN).all()
    assert (resolved(partner, [nowhere, SimpleNamespace(rough_boxes=lambda: [])])[:, 4:6] == 2).all()
    assert (resolved(partner, [])[:, 4:6] == filling.PARTNER_UNKNOWN).all()
    np.save(tmp_path / "filled.npy", np.isnan(z) & (np.arange(12) >= 6))  # a neighbour filled the rest
    second = np.array(partner)
    filling._mark_rows(second, str(tmp_path / "filled.npy"), 2, 4)
    assert (second[:, 6:] == 2).all()
    p = resolved(second, [north, everywhere])  # the nearest fill (everywhere's) first: its boxes hold them all
    assert (p[:, 4:6] == 2).all() and (p[:, 6] == 2).all() and not p[:, 7:].any()  # beyond the reach: 0
    first = np.array(partner)
    filling._mark_rows(first, str(tmp_path / "filled.npy"), 1, 4)
    p = resolved(first, [north, everywhere])  # north's fill nearest, but its boxes hold the top rows only
    assert (p[:5, 4:6] == 1).all() and (p[5:, 4:6] == 2).all()
