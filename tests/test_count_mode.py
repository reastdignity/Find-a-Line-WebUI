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
        monkeypatch.setattr(terrain, name, lambda *args, k=kernel, n=name: (seen.append(n), k(*args))[1])
    listener = lambda state: seen.append(("bar", state["stage"], state["done"])) if state.get("bar") else None
    search.progress.subscribe(listener)
    return seen, lambda: search.progress.unsubscribe(listener)


def test_count_tile_leaves_the_anchor_values_to_the_first_line(tmp_path, offline, monkeypatch):
    """count_tile computes prominence and drop when the first line needs them, once, and hands the
    sink what a search computing them first does; the bar of the pairs goes on afterwards."""
    import search
    plan = _krovak_plan(tmp_path)
    data = search.prepare_data(plan)
    first = []
    search._pair_search(plan, data, search._anchors(plan, data), None, None, sink=first.append)
    seen, stop = _timed_values(monkeypatch)
    try:
        plan.funnel = {}
        later = []
        search.count_tile(plan, data, None, later.append)
    finally:
        stop()
    assert sum(len(p) for p in later) > 100
    assert seen.count("prominence") == 1 and seen.count("drop") == 1
    a, b = _sorted(_joined(first)), _sorted(_joined(later))
    del b["water_px"]
    _assert_same(a, b)
    bars = [s for s in seen if isinstance(s, tuple)]
    start = bars.index(("bar", "anchor prominence and drop", False))
    assert bars[0:start] and any(s[1] == "anchor pairs" for s in bars[:start])  # the pairs had started
    after = bars[bars.index(("bar", "anchor prominence and drop", True)):]
    assert ("bar", "anchor pairs", False) in after and after[-1] == ("bar", "anchor pairs", True)


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
