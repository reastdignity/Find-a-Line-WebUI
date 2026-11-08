"""Fast checks of single parts: search areas, the parameter schema, progress listeners, the cache index."""

import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import area as ar  # noqa: E402
import cache  # noqa: E402
import grid as gd  # noqa: E402
import params as pm  # noqa: E402
import sources as src  # noqa: E402
import update  # noqa: E402
from progress import progress  # noqa: E402


def test_polygon_mask_matches_circle():
    circle = ar.Circle(50.1559508, 19.7562722, 500)
    grid = gd.make_grid(circle.bounds("EPSG:2180"), 2, "EPSG:2180", (0.5, 0.5))
    polygon = ar.Polygon(circle.shape_wgs84())
    a, b = circle.mask(grid), polygon.mask(grid)
    assert a.sum() == pytest.approx(np.pi * 250 ** 2, rel=0.01)
    assert (a != b).sum() < 0.01 * a.sum()  # only pixels on the boundary differ


def test_circle_grid_snaps_to_origin():
    circle = ar.Circle(50.1559508, 19.7562722, 1000)
    grid = gd.make_grid(circle.bounds("EPSG:2180"), 2, "EPSG:2180", (0.5, 0.5))
    assert (grid.left - 0.5) % 2 == 0 and (grid.top - 0.5) % 2 == 0
    assert grid.width == grid.height == 1001


@pytest.mark.parametrize("values, message", [
    ({"lat": 50}, "both --lat and --lon are required"),
    ({"lat": 50, "lon": 19, "northing": 1, "easting": 2}, "either --lat/--lon or --northing/--easting"),
    ({"lat": 50, "lon": 19, "min_length": 50, "max_length": 40}, "--min-length must be positive"),
    ({"lat": 50, "lon": 19, "radius": 0}, "--radius must be positive"),
    ({"lat": 50, "lon": 19, "source": "mars"}, "unknown --source mars"),
])
def test_params_validation(values, message):
    with pytest.raises(ValueError, match=message):
        pm.SearchParams(**values)


def test_params_defaults_and_cli():
    [params], options = pm.parse_cli(["--lat", "50", "--lon", "19", "--nmpt", "off", "-y"])
    assert params.radius == 1000 and params.nmpt_mode is None and options.yes
    assert pm.SearchParams(lat=50, lon=19).nmpt_mode == "mark"


def test_points():
    searches, _ = pm.parse_cli(["--point", "50.1,19.7,Żabi Koń, Kobylany", "--point", "35.85,14.38",
                                "--radius", "500"])
    assert [(p.lat, p.lon, p.name, p.radius) for p in searches] == [
        (50.1, 19.7, "Żabi Koń, Kobylany", 500), (35.85, 14.38, None, 500)]
    with pytest.raises(SystemExit):
        pm.parse_cli(["--point", "50.1,19.7", "--lat", "50"])
    with pytest.raises(SystemExit):
        pm.parse_cli(["--point", "50.1"])


def test_progress_listener():
    events = []
    progress.subscribe(events.append)
    try:
        progress.compute.start("test stage", 3, unit="step")
        progress.compute.update(2, note="x")
        progress.compute.finish()
    finally:
        progress.unsubscribe(events.append)
    assert [e["count"] for e in events] == [0, 2, 3]
    assert events[-1]["done"] and events[0]["stage"] == "test stage"


def test_bars_put_back_the_bars_they_found(monkeypatch):
    """progress.bars() leaves the bars that were there, with their labels: bars without a label stayed for
    the rest of the process, and a test that followed the bars by their label saw none
    (tests/test_count_mode.py after a test that had run the country layer in its process)."""
    monkeypatch.setenv("FINDALINE_PROGRESS", "text")
    outer = progress.download, progress.compute
    with progress.bars():
        inner = progress.download, progress.compute
        assert [b.label for b in inner] == ["Download", "Compute"] and all(a is not b for a, b in zip(inner, outer))
        with progress.bars():
            assert all(a is not b for a, b in zip((progress.download, progress.compute), inner))
        assert (progress.download, progress.compute) == inner
    assert (progress.download, progress.compute) == outer
    assert [outer[0].label, outer[1].label] == ["Download", "Compute"]


def _age(cache_dir, path, days):
    """Pretend a file was checked (and fetched) `days` ago."""
    import sqlite3
    from datetime import datetime, timedelta, timezone
    when = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")
    top, inner = cache.relative(cache_dir, path).split("/", 1)
    with sqlite3.connect(os.path.join(cache_dir, top, "index.sqlite")) as db:
        db.execute("UPDATE files SET checked_at = ?, fetched_at = ? WHERE path = ?", (when, when, inner))
    db.close()


def test_cache_same_content_keeps_fetch_time(tmp_path):
    path = tmp_path / "spain" / "mdt05" / "live" / "t" / "0_0.tif"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"a")
    cache.record(str(tmp_path), str(path))
    _age(str(tmp_path), str(path), 1000)
    old = cache.info(str(tmp_path), str(path))
    cache.record(str(tmp_path), str(path))           # downloaded again, same content
    same = cache.info(str(tmp_path), str(path))
    assert same["fetched_at"] == old["fetched_at"] and same["checked_at"] > old["checked_at"]
    path.write_bytes(b"b")
    cache.record(str(tmp_path), str(path))           # new content
    assert cache.info(str(tmp_path), str(path))["fetched_at"] > old["fetched_at"]


@pytest.mark.parametrize("status, age, ttl, update, expected", [
    ("ok", 800, 730, None, False),       # never without an update
    ("ok", 800, None, "all", False),     # versioned releases never change
    ("ok", 10, 730, "all", True),
    ("ok", 10, 730, "stale", False),
    ("ok", 800, 730, "stale", True),
    ("missing", 100, 730, "stale", True),  # missing: after MISSING_TTL_DAYS
    ("missing", 100, None, "stale", False),
])
def test_cache_stale(status, age, ttl, update, expected):
    from datetime import datetime, timedelta, timezone
    row = {"status": status, "checked_at": (datetime.now(timezone.utc) - timedelta(days=age)).isoformat()}
    assert cache.stale(row, ttl, update) is expected


def test_cache_due_many_answers_as_due(tmp_path):
    """cache.due_many (one connection per top-level folder) and due (one connection) answer as due()
    did (state, then stale of the row of info: two connections) for each file: not recorded, adopted
    (a file without a row, which all record), another processing, missing, stale for an update, in
    two top-level folders; and in the order of the paths."""
    import shutil

    def due_before(cache_dir, path, processing, update, ttl):
        return cache.state(cache_dir, path, processing) is None or             cache.stale(cache.info(cache_dir, path), ttl, update)
    first = tmp_path / "first"
    kinds = {}
    for top in ("spain", "poland"):
        for name, days in (("new", None), ("adopted", None), ("ok", 10), ("old", 800), ("missing", 100),
                           ("lost", 10)):
            path = first / top / "live" / f"{name}.tif"
            path.parent.mkdir(parents=True, exist_ok=True)
            if name != "new":
                path.write_bytes(b"a")
            if days is not None:
                cache.record(str(first), str(path), "missing" if name == "missing" else "ok",
                             processing=2 if name == "lost" else 1)
                _age(str(first), str(path), days)
                if name in ("missing", "lost"):
                    path.unlink()
            kinds[str(path)] = name
    second, third = tmp_path / "second", tmp_path / "third"
    shutil.copytree(first, second)
    shutil.copytree(first, third)
    paths = list(kinds)[::-1]  # not grouped by folder
    moved = lambda folder: [p.replace(str(first), str(folder)) for p in paths]  # noqa: E731
    for update, ttl in ((None, 730), ("stale", 730), ("all", 730), ("stale", None), ("all", None)):
        for processing in (1, 2):
            expected = [due_before(str(first), p, processing, update, ttl) for p in paths]
            assert cache.due_many(str(second), moved(second), processing, update, ttl) == expected, (update, ttl)
            assert [cache.due(str(third), p, processing, update, ttl) for p in moved(third)] == expected
    assert cache.due_many(str(second), []) == []
    for folder in (second, third):
        assert cache.info(str(folder), str(folder / "spain" / "live" / "adopted.tif"))["status"] == "ok"
    assert [kinds[p] for p, due in zip(paths, cache.due_many(str(first), paths)) if due] ==         ["lost", "new"] * 2


def test_cache_states_answers_as_state(tmp_path):
    """cache.states (one connection per top-level folder) answers as state() of each file, in the order
    of the paths: not recorded, adopted (a file without a row, which it records), missing, another
    processing, in two top-level folders."""
    import shutil
    first = tmp_path / "first"
    paths = []
    for top in ("spain", "poland"):
        for name in ("new", "adopted", "ok", "missing", "lost"):
            path = first / top / "live" / f"{name}.tif"
            path.parent.mkdir(parents=True, exist_ok=True)
            if name != "new":
                path.write_bytes(b"a")
            if name in ("ok", "missing", "lost"):
                cache.record(str(first), str(path), "missing" if name == "missing" else "ok",
                             processing=2 if name == "lost" else 1)
                if name != "ok":
                    path.unlink()
            paths.append(str(path))
    second = tmp_path / "second"
    shutil.copytree(first, second)
    paths = paths[::-1]  # not grouped by folder
    moved = [p.replace(str(first), str(second)) for p in paths]
    for processing in (1, 2):
        assert cache.states(str(second), moved, processing) == [cache.state(str(first), p, processing) for p in paths]
    assert cache.states(str(second), []) == []
    assert cache.info(str(second), str(second / "spain" / "live" / "adopted.tif"))["status"] == "ok"
    assert cache.states(str(second), moved)[::-1] == [None, "ok", "ok", "missing", None] * 2


def test_prepared_outline_keeps_the_tiles():
    """A tiling's test of every tile against the outline, prepared (tilings._outline), keeps exactly the
    tiles of the plain test, of a jagged outline with a hole and an island, also in another CRS, and
    leaves grid.area_shape, which threads share, as it was."""
    import math
    import shapely
    from shapely.geometry import MultiPolygon, Polygon, box

    from area import project
    from grid import Grid
    from sources.indexes.tilings import FileBlockTiling, MetricTiling, TenthDegreeTiling, _outline
    rng = np.random.default_rng(3)
    angles = np.linspace(0, 2 * np.pi, 400, endpoint=False)
    radius = 40_000 + 15_000 * rng.random(400)
    x, y = 500_000.0, 5_000_000.0
    hole = Polygon([(x + 9000 * math.cos(a), y + 9000 * math.sin(a)) for a in angles[::10]])
    land = Polygon(np.column_stack([x + radius * np.cos(angles), y + radius * np.sin(angles)])).difference(hole)
    outline = MultiPolygon([land, box(x - 2000, y - 2000, x + 2000, y + 2000)])
    crs = "EPSG:32634"
    grid = Grid(crs=crs, left=x - 60_000, top=y + 60_000, width=1200, height=1200, res=100.0)
    grid.area_shape = outline
    assert _outline(Grid(crs=crs, left=0, top=0, width=1, height=1, res=1.0), crs) is None
    tenth = lambda t, i: (t[0] / 10, t[1] / 10, (t[0] + 1) / 10, (t[1] + 1) / 10)  # noqa: E731
    for index, edges in ((MetricTiling(crs, "f", 4000), lambda t, i: i.edges(t)),
                         (MetricTiling("EPSG:3035", "f", 5000, origin=(1000.0, 0.0)), lambda t, i: i.edges(t)),
                         (FileBlockTiling(crs, "f", 1.0, 3000, lambda i, j: []), lambda t, i: i._edges(*t)),
                         (TenthDegreeTiling("EPSG:4326", "f", 3600, lambda name: name), tenth)):
        kept = index.tiles(grid)
        shape = project(outline, crs, index.crs)
        every = index.tiles(Grid(crs=grid.crs, left=grid.left, top=grid.top, width=grid.width, height=grid.height,
                                 res=grid.res))
        assert kept and len(every) > len(kept) and not shapely.is_prepared(shape)
        assert kept == [t for t in every if shape.intersects(box(*edges(t, index)))]
    assert not shapely.is_prepared(outline)


def test_update_checks(tmp_path):
    """Live tiles are checked after their interval, releases never; --bbox limits the checks."""
    spain = src.SOURCES["spain"].nmt
    malta = src.SOURCES["malta"].nmt
    live = spain.tile_path(str(tmp_path), (5.0, 100, 2000))
    release = malta.tile_path(str(tmp_path), (1.0, 230, 1790))
    for path in (live, release):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        open(path, "wb").write(b"x")
        cache.record(str(tmp_path), path)
        _age(str(tmp_path), path, 1000)
    assert spain.tile_of(cache.relative(str(tmp_path), live)) == (5.0, 100, 2000)
    assert spain.tile_of(cache.relative(str(tmp_path), release)) is None
    found = update.checks(str(tmp_path))
    assert [c.path for c in found] == [cache.relative(str(tmp_path), live)]
    west, south, east, north = found[0].extent
    assert update.checks(str(tmp_path), bbox=(west - 1, south - 1, west - 0.5, south - 0.5)) == []
    assert len(update.checks(str(tmp_path), bbox=(west, south, west, south))) == 1


def test_covered_metres_match_profiles(monkeypatch):
    """The metres over water of every line (numba) equal those of its profile, in parts of any size."""
    import helpers as sh
    import linesearch as ls
    rng = np.random.default_rng(5)
    elevation = rng.random((200, 200)) * 10
    mask = rng.random((200, 200)) < 0.3
    a1 = rng.integers(0, 200, (300, 2))
    a2 = rng.integers(0, 200, (300, 2))
    keep = np.abs(a2 - a1).max(axis=1) >= 2
    a1, a2 = a1[keep], a2[keep]
    fast = ls.covered_metres(a1, a2, 2.0, mask).tolist()
    slow = [sh.line_profile(tuple(p), tuple(q), elevation, 2.0, water=mask)["water_m"] for p, q in zip(a1, a2)]
    assert fast == slow
    monkeypatch.setattr(ls, "COVERED_PART", 7)
    parts = ls.covered_metres(a1, a2, 2.0, mask)
    assert parts.dtype == np.float64 and parts.tolist() == slow
    assert ls.covered_metres(a1, a2, 2.0, None).tolist() == [0.0] * len(a1)


def _old_covered_metres(a1, a2, res, mask):
    """linesearch.covered_metres before wave 3 of round 3 (Python's round() line by line): the reference."""
    import linesearch as ls
    out = np.zeros(len(a1))
    if mask is None or len(a1) == 0:
        return out
    p, q = np.ascontiguousarray(a1, dtype=np.int64), np.ascontiguousarray(a2, dtype=np.int64)
    counts = np.zeros(len(p), dtype=np.int64)
    ls._covered_pixels(p, q, np.ascontiguousarray(mask, dtype=np.bool_), counts)
    d = q - p
    steps = np.maximum(np.abs(d[:, 0]), np.abs(d[:, 1]))
    lengths = np.hypot(d[:, 0], d[:, 1]) * res
    out[:] = [round(float(n) * length / s, 1) if n else 0.0
              for n, length, s in zip(counts.tolist(), lengths.tolist(), steps.tolist())]
    return out


def test_covered_metres_as_before(monkeypatch):
    """covered_metres rounds whole parts with runs.round_floats: the values of the old round() per
    line, halfway cases too (lines along a row or a column at 0.25 or 1.25 m give n * res with a 5
    in the second decimal, exact in binary), lines of one step and of none, parts of any size."""
    import linesearch as ls
    rng = np.random.default_rng(29)
    size = 120
    a1 = rng.integers(0, size, (4000, 2))
    a2 = rng.integers(0, size, (4000, 2))
    straight = rng.random(len(a1)) < 0.4  # along a row or a column
    axis = rng.integers(0, 2, len(a1))
    a2[straight, axis[straight]] = a1[straight, axis[straight]]
    diagonal = rng.random(len(a1)) < 0.1
    span = rng.integers(-40, 40, len(a1))
    a2[diagonal] = np.clip(a1[diagonal] + span[diagonal, None], 0, size - 1)
    a2[:5] = a1[:5]  # no step
    a2[5:10] = a1[5:10] + [0, 1]  # one step
    a2 = np.clip(a2, 0, size - 1)
    for share in (0.0, 0.05, 0.3, 0.9, 1.0):
        mask = rng.random((size, size)) < share
        for res in (0.25, 0.5, 1.0, 1.25, 2.0, 0.1, 0.15, 5.0, 30.0, 1 / 3):
            expected = _old_covered_metres(a1, a2, res, mask)
            got = ls.covered_metres(a1, a2, res, mask)
            assert got.dtype == np.float64
            assert list(map(repr, got.tolist())) == list(map(repr, expected.tolist())), (share, res)
    monkeypatch.setattr(ls, "COVERED_PART", 37)
    assert ls.covered_metres(a1, a2, 1.25, mask).tolist() == _old_covered_metres(a1, a2, 1.25, mask).tolist()


def _profile_case(seed=13, size=300):
    """Terrain with walls (lines over a gap), a few pixels without data, a surface model missing in
    places, water and filled masks, and lines of 2 to about 300 pixels between non-NaN anchors."""
    rng = np.random.default_rng(seed)
    terrain = (rng.random((size, size)) * 30 + 100).astype(np.float32)
    terrain[:, :10] += 80
    terrain[:, -10:] += 70
    terrain[rng.random((size, size)) < 0.003] = np.nan
    terrain[5, :] = 512.125  # halves at 2 decimals: round() and the rounding of the batch must agree
    surface = (terrain + rng.random((size, size)) * 15).astype(np.float32)
    surface[rng.random((size, size)) < 0.3] = np.nan
    surface[:, 150:160] = np.nan  # lines without surface data between their anchors
    water = rng.random((size, size)) < 0.1
    filled = np.zeros((size, size), dtype=bool)
    filled[100:140, 50:250] = True
    a1 = rng.integers(0, size, (900, 2))
    a2 = rng.integers(0, size, (900, 2))
    a2[:100] = a1[:100] + rng.integers(-6, 7, (100, 2))  # short ones
    a1[100:150, 0], a2[100:150, 0] = 5, 5  # along the row of halves
    a1[150:200, 1], a2[150:200, 1] = 155, 155  # along the columns without surface data
    a2 = np.clip(a2, 0, size - 1)
    keep = (np.abs(a2 - a1).max(axis=1) >= 2) & ~np.isnan(terrain[a1[:, 0], a1[:, 1]]) \
        & ~np.isnan(terrain[a2[:, 0], a2[:, 1]])
    return terrain, surface, water, filled, a1[keep], a2[keep]


@pytest.mark.parametrize("model", ["formula", "sag"])
def test_line_profiles_match_line_profile(model):
    """The batch of lineprofiles gives every line exactly (==, and the same JSON text) the profile of
    helpers.line_profile, with and without surface, water and filled masks, also thinned to fewer
    points; its metres over water and filled gaps are those of linesearch.covered_metres; its
    profiles survive the pickle of a tile file and become the same text of data.js."""
    import json
    import pickle

    import helpers as sh
    import lineprofiles as lp
    import linesearch as ls
    import sag
    terrain, surface, water, filled, a1, a2 = _profile_case()
    table = sag.EnvelopeTable(sag.Rigging(), 2, 400) if model == "sag" else None
    encoder = json.JSONEncoder(separators=(",", ":"))
    cases = [(0.25, surface, water, filled, 200), (0.25, None, None, None, 200), (1.0, surface, None, filled, 7),
             (2.0, None, water, None, 1), (5.0, surface, water, None, 2)]
    seen = set()
    for res, s, w, g, points in cases:
        batch = lp.line_profiles(a1, a2, terrain, res, s, points, table, w, g, parts=7)
        assert len(batch) == len(a1)
        assert batch.w is None if w is None else batch.w.dtype == np.uint8
        for k in range(len(a1)):
            slow = sh.line_profile(tuple(a1[k].tolist()), tuple(a2[k].tolist()), terrain, res, s, points, table, w, g)
            fast = batch[k].as_dict()
            assert fast == slow, (res, points, k)
            assert list(fast) == list(slow)
            assert encoder.encode(fast) == encoder.encode(slow), (res, points, k)
            seen |= {"no nmpt"} if s is not None and fast["min_nmpt"] is None else set()
            seen |= {"no terrain"} if None in fast["z"] else set()
            seen |= {"water"} if fast["w"] is not None else set()
        if w is not None:
            assert batch.small[:, 6].tolist() == ls.covered_metres(a1, a2, res, w).tolist()
        if g is not None:
            assert batch.small[:, 7].tolist() == ls.covered_metres(a1, a2, res, g).tolist()
    assert seen == {"no nmpt", "no terrain", "water"}
    # A table with these profiles, through a tile file, gives the dicts of before
    columns = {"a1": a1, "a2": a2, "clearance_nmpt": np.zeros(len(a1))}
    tables = sh.LineTable(columns, {k: batch[k] for k in range(0, len(a1), 3)})
    again = pickle.loads(pickle.dumps(tables, pickle.HIGHEST_PROTOCOL))
    assert {k: sh.profile_dict(p) for k, p in again.profiles.items()} == \
           {k: sh.profile_dict(p) for k, p in tables.profiles.items()}
    assert again.row(3)["profile"] == batch[3].as_dict()
    with pytest.raises(ValueError):
        lp.line_profiles(np.array([[0, 0]]), np.array([[0, 1]]), terrain, 1.0)  # no pixel between the anchors


def test_line_profiles_independent_of_threads():
    """The batch gives the same arrays with any number of threads."""
    import numba

    import lineprofiles as lp
    import sag
    terrain, surface, water, filled, a1, a2 = _profile_case(seed=17)
    table = sag.EnvelopeTable(sag.Rigging(), 2, 400)
    most = numba.config.NUMBA_NUM_THREADS
    results = []
    try:
        for threads in sorted({1, min(3, most), min(7, most), most}):
            numba.set_num_threads(threads)
            for sag_table in (None, table):
                results.append(lp.line_profiles(a1, a2, terrain, 0.5, surface, 50, sag_table, water, filled, parts=3))
    finally:
        numba.set_num_threads(most)
    for k, other in enumerate(results[2:], 2):
        first = results[k % 2]
        for name in ("offsets", "d", "z", "s", "w", "g", "small", "flags"):
            assert np.array_equal(getattr(other, name), getattr(first, name), equal_nan=name in "dzs small"), name


@pytest.mark.parametrize("model", ["formula", "sag"])
def test_evaluate_lines_matches_evaluate_line(model):
    """The numba check gives exactly (==) the decisions and values of helpers.evaluate_line."""
    import helpers as sh
    import linesearch as ls
    import sag
    rng = np.random.default_rng(7)
    terrain = (rng.random((120, 120)) * 30 + 100).astype(np.float32)
    terrain[rng.random((120, 120)) < 0.002] = np.nan          # a few pixels without data
    surface = (terrain + rng.random((120, 120)) * 15).astype(np.float32)
    surface[rng.random((120, 120)) < 0.3] = np.nan            # no surface model in places
    terrain[:, :8] += 60                                     # cliffs on both sides, so lines pass
    terrain[:, -8:] += 60
    anchors = np.column_stack([rng.integers(0, 120, 400),  # on the cliffs, and some anywhere
                               np.where(rng.random(400) < 0.5, rng.integers(0, 8, 400), rng.integers(112, 120, 400))])
    anchors[:50] = rng.integers(0, 120, (50, 2))
    found = rng.integers(0, 400, (3000, 2))
    table = sag.EnvelopeTable(sag.Rigging(), 20, 200) if model == "sag" else None
    for mode, high_above in (("mark", sh.HIGH_ABOVE), ("reject", 35.0)):
        values = rng.random((len(anchors), 2)) * 50  # prominence, drop of the anchors
        fast = ls.evaluate_lines(found, anchors, terrain, 1.0, surface, table, mode, high_above,
                                 anchor_values=values).lines()
        down = sh.downslope(terrain, anchors, 1.0)
        angles = np.column_stack(sh.wall_angles(anchors[found[:, 0]], anchors[found[:, 1]],
                                                down[found[:, 0]], down[found[:, 1]])).tolist()
        slow = []
        for (i, j), (angle1, angle2) in zip(found, angles):
            result = sh.evaluate_line(anchors[i], anchors[j], terrain, 1.0, surface, table, high_above)
            if sh.is_valid(result, mode):  # as find_valid_lines always made them
                elev_a1, elev_a2, length, clearance, clearance_nmpt, *heights = result
                slow.append(sh.Line(tuple(map(int, anchors[i])), tuple(map(int, anchors[j])),
                                    length, elev_a1, elev_a2, clearance, clearance_nmpt, *heights, angle1, angle2,
                                    values[i, 0], values[j, 0], values[i, 1], values[j, 1]))
        assert slow and fast == slow
        assert 0 < sum(0 < line.high_pct < 100 for line in fast)  # the threshold is crossed


def _old_coordify(a1, a2, grid):
    """mapping.coordify's coordinates before wave 3 of round 3 (every anchor of every line
    transformed): the reference. Returns anchor1, anchor2, a1_xy, a2_xy."""
    from pyproj import Transformer
    rows = np.column_stack([a1[:, 0], a2[:, 0]]).ravel()
    cols = np.column_stack([a1[:, 1], a2[:, 1]]).ravel()
    easting, northing = grid.pixel_to_xy(rows, cols)
    lon, lat = Transformer.from_crs(grid.crs, "EPSG:4326", always_xy=True).transform(easting, northing)
    out = []
    for a, b, first in ((lat, lon, 0), (lat, lon, 1), (easting, northing, 0), (easting, northing, 1)):
        out.append(np.column_stack([np.asarray(a, dtype=np.float64)[first::2], np.asarray(b, dtype=np.float64)[first::2]]))
    return out


def test_coordify_as_before(monkeypatch):
    """coordify transforms the different anchor pixels of a part once: the same float64 values as
    every anchor transformed (the old code), in several CRSs (UTM, Swiss LV95, Polish 1992, the
    Czech Krovak, British National Grid), anchors shared by many lines, parts of any size."""
    import helpers as sh
    import mapping
    from grid import Grid
    rng = np.random.default_rng(37)
    cases = [("EPSG:32633", 447000.0, 5551000.0, 1.0), ("EPSG:2056", 2636000.0, 1158000.0, 1.0),
             ("EPSG:2180", 565000.0, 160000.0, 5.0), ("EPSG:5514", -650000.0, -1020000.0, 2.0),
             ("EPSG:27700", 330000.0, 400000.0, 0.5)]
    for crs, left, top, res in cases:
        grid = Grid(left=left, top=top, res=res, height=900, width=1300, crs=crs)
        anchors = np.column_stack([rng.integers(0, 900, 700), rng.integers(0, 1300, 700)])
        pairs = rng.integers(0, len(anchors), (5000, 2))
        a1, a2 = anchors[pairs[:, 0]], anchors[pairs[:, 1]]
        a1[:3] = [[0, 0], [899, 1299], [0, 1299]]  # the grid's corners
        expected = _old_coordify(a1, a2, grid)
        for part in (1 << 17, 1, 777):
            monkeypatch.setattr(mapping, "COORDINATE_PART", part)
            clearance = rng.normal(0, 3, len(a1))
            table = sh.LineTable({"a1": a1.copy(), "a2": a2.copy(), "clearance_nmpt": clearance})
            mapping.coordify(table, grid, "mark")
            for name, values in zip(("anchor1", "anchor2", "a1_xy", "a2_xy"), expected):
                got = table.columns[name]
                assert got.dtype == np.float64 and got.tobytes() == values.tobytes(), (crs, part, name)
            assert table.columns["over_obstacles"].tolist() == (clearance <= 0).tolist()


def test_interp_forward_matches_interp():
    """_evaluate's _interp_forward (the index walked forward along a line) gives exactly _interp's
    value for non-decreasing x: the sag table's fractions and the t = i / steps of lines of 2 to
    2 000 steps, other increasing tables, x on the table's points, below and above it, and NaN."""
    import linesearch as ls
    rng = np.random.default_rng(31)
    tables = [np.linspace(0, 1, 42), np.cumsum(rng.random(17) + 0.01), np.array([0.0, 1.0]),
              np.array([-1.0, 0.0, 0.0, 2.0])]
    for xp in tables:
        fp = rng.normal(0, 3, len(xp))
        runs = [np.arange(1, steps) / steps for steps in (2, 3, 7, 41, 42, 43, 130, 1000, 2000)]
        runs.append(np.sort(np.concatenate([xp, rng.uniform(xp[0] - 1, xp[-1] + 1, 300)])))
        runs.append(np.concatenate([np.sort(rng.uniform(xp[0], xp[-1], 50)), [np.nan, np.inf]]))
        for x in runs:
            at = 0
            for v in x.tolist():
                got, at = ls._interp_forward(v, xp, fp, at)
                expected = ls._interp(v, xp, fp)
                assert repr(got) == repr(expected), (v, xp)


@pytest.mark.parametrize("model", ["formula", "sag"])
def test_kernels_independent_of_threads(model):
    """The parallel kernels give the same results (==, in the same order) with any number of
    threads (--threads, NUMBA_NUM_THREADS): no float sum across prange iterations, every
    result written at its iteration's place. Odd counts move the borders between threads."""
    import numba

    import helpers as sh
    import linesearch as ls
    import sag
    import terrain
    rng = np.random.default_rng(11)
    z = (rng.random((160, 160)) * 3 + 100).astype(np.float32)
    z[:, :20] += 60                                          # a canyon between two walls
    z[:, 140:] += 55 + rng.random((160, 20)).astype(np.float32) * 10
    z[rng.random((160, 160)) < 0.003] = np.nan
    surface = (z + rng.random((160, 160)) * 20).astype(np.float32)
    anchors = np.vstack([np.column_stack([np.arange(0, 160, 2), np.full(80, 19)]),
                         np.column_stack([np.arange(1, 160, 2), np.full(80, 140)]),
                         rng.integers(0, 160, (60, 2))])
    first = rng.random(len(anchors)) < 0.7
    table = sag.EnvelopeTable(sag.Rigging(), 20, 200) if model == "sag" else None
    mask = rng.random((160, 160)) < 0.2
    most = numba.config.NUMBA_NUM_THREADS
    results = []
    try:
        for threads in sorted({1, min(3, most), min(7, most), most}):
            numba.set_num_threads(threads)
            values = np.column_stack([terrain.prominence(z, anchors, 1.0, 40), terrain.drop(z, anchors, 1.0, 30)])
            found = ls.find_valid_lines(z, surface, anchors, 1.0, 20, 150, nmpt_mode="mark", threads=threads,
                                        sag_table=table, max_dh_ratio=0.3, first=first,
                                        limits=sh.LineLimits(max_wall_angle=120), anchor_values=values)
            covered = ls.covered_metres(found.columns["a1"], found.columns["a2"], 1.0, mask).tolist()
            results.append((threads, values, found.columns, covered))
    finally:
        numba.set_num_threads(most)
    _, values, columns, covered = results[0]
    assert len(columns["a1"]) > 100
    for threads, other_values, other_columns, other_covered in results[1:]:
        assert np.array_equal(other_values, values, equal_nan=True), threads
        assert other_columns.keys() == columns.keys(), threads
        for name in columns:
            assert np.array_equal(other_columns[name], columns[name], equal_nan=columns[name].dtype.kind == "f"), \
                (threads, name)
        assert other_covered == covered, threads


def _canyon(seed=11):
    """The canyon of test_kernels_independent_of_threads: elevation, surface, anchors, a first mask."""
    rng = np.random.default_rng(seed)
    z = (rng.random((160, 160)) * 3 + 100).astype(np.float32)
    z[:, :20] += 60
    z[:, 140:] += 55 + rng.random((160, 20)).astype(np.float32) * 10
    z[rng.random((160, 160)) < 0.003] = np.nan
    surface = (z + rng.random((160, 160)) * 20).astype(np.float32)
    anchors = np.vstack([np.column_stack([np.arange(0, 160, 2), np.full(80, 19)]),
                         np.column_stack([np.arange(1, 160, 2), np.full(80, 140)]),
                         rng.integers(0, 160, (60, 2))])
    return z, surface, anchors, rng.random(len(anchors)) < 0.7


def _old_valid_lines(z, surface, anchors, min_length, max_length, table, first, limits, values):
    """The end of find_valid_lines as it was before wave 4 (all pairs concatenated, evaluated in
    np.array_split parts, the tables concatenated, then take of the sort): the reference."""
    import math

    import helpers as sh
    import linesearch as ls
    elev = z[anchors[:, 0], anchors[:, 1]]
    if table is None:
        log_spans, ratios, sag, fall_zone = np.zeros(2), np.zeros(2), np.zeros((2, 2, 2)), 0.0
        gain, cap, offset = -sh.SLOPE, np.inf, sh.LEASH_FALL
    else:
        log_spans, ratios = np.log(table.spans), table.RATIOS.astype(np.float64)
        sag, fall_zone = np.ascontiguousarray(table.sag), table.rig.fall_zone
        gain, cap, offset = 0.3 * math.sqrt(2), np.inf, fall_zone + min(0.0, float(sag.min()))
    useful, rings, slot = ls.free_directions(z, anchors, 1.0, gain, cap, offset, min_length, max_length)
    down = sh.downslope(z, anchors, 1.0)
    angle = limits.max_wall_angle if limits.max_wall_angle is not None else 180.0
    cos_limit = -2.0 if angle >= 180 else math.cos(math.radians(angle))
    todo_all, args, tail = ls.pair_arguments(z, anchors, elev, useful, rings, slot, first, 1.0, min_length,
                                             max_length, 0.3, np.inf, down, cos_limit, None, table is not None,
                                             log_spans, ratios, sag, fall_zone)
    pairs = [ls.pair_chunk(args, todo, tail)[1] for todo in np.array_split(todo_all, min(200, max(1, len(todo_all))))]
    found = np.concatenate(pairs) if pairs else np.zeros((0, 2), dtype=np.int64)
    parts = [ls.evaluate_lines(part, anchors, z, 1.0, surface, table, "mark", sh.HIGH_ABOVE, limits, down, values)
             for part in np.array_split(found, max(1, min(200, len(found) // 10000)))]
    lines = sh.LineTable.concat(parts)
    return lines.take(np.argsort(-lines.columns["length"], kind="stable")), len(found)


@pytest.mark.parametrize("model", ["formula", "sag"])
@pytest.mark.parametrize("case", ["all", "first", "limits", "empty"])
def test_valid_lines_in_parts_as_before(model, case, monkeypatch):
    """find_valid_lines evaluates the chunks' pairs in parts, joins the tables column by column and
    sorts them in place: the table of before (every column, its dtype, left_out and the funnel's
    counts), whatever the size of the parts and the number of chunks."""
    import helpers as sh
    import linesearch as ls
    import sag
    import terrain
    z, surface, anchors, first = _canyon()
    first = first if case == "first" else None
    min_length, max_length = (300.0, 400.0) if case == "empty" else (20.0, 150.0)
    table = sag.EnvelopeTable(sag.Rigging(), min_length, max_length) if model == "sag" else None
    values = np.column_stack([terrain.prominence(z, anchors, 1.0, 40), terrain.drop(z, anchors, 1.0, 30)])

    def limits():
        return sh.LineLimits(min_height=60.5, max_wall_angle=120) if case == "limits" else sh.LineLimits()

    old_limits = limits()
    old, found = _old_valid_lines(z, surface, anchors, min_length, max_length, table, first, old_limits, values)
    assert (len(old) == 0) == (case == "empty") and (old_limits.left_out > 0) == (case == "limits")
    for chunks, part in ((200, 10_000), (200, 1), (7, 13), (1, 100), (3, 10_000)):
        monkeypatch.setattr(ls, "CHUNKS", chunks)
        monkeypatch.setattr(ls, "EVAL_PART", part)
        new_limits, stats = limits(), {}
        new = ls.find_valid_lines(z, surface, anchors, 1.0, min_length, max_length, nmpt_mode="mark",
                                  sag_table=table, max_dh_ratio=0.3, first=first, limits=new_limits,
                                  anchor_values=values, stats=stats)
        assert list(new.columns) == list(old.columns) and new.profiles == {}
        for name, column in old.columns.items():
            assert new.columns[name].dtype == column.dtype and new.columns[name].shape == column.shape, name
            assert np.array_equal(new.columns[name], column, equal_nan=column.dtype.kind == "f"), (chunks, part, name)
        assert new_limits.left_out == old_limits.left_out
        assert stats["found"] == found and stats["valid"] == len(old) and stats["left_out"] == old_limits.left_out


def _old_group_lines(lines, distance, by="clearance"):
    """mapping.group_lines of 792efad (its cell index a dict of Python lists), the reference of
    test_grouping_as_before."""
    import mapping
    first, second = mapping._rank(lines, by)
    over_all = lines.columns["over_obstacles"]
    d2 = distance ** 2
    reps, members = [], []
    for over in (False, True):
        rows = np.flatnonzero(over_all == over)
        if not len(rows):
            continue
        rows = rows[np.lexsort((-second[rows], -first[rows]))]
        a1 = lines.columns["a1_xy"][rows]
        a2 = lines.columns["a2_xy"][rows]
        free = np.ones(len(rows), dtype=bool)
        cells = {}
        for k, cell in enumerate(map(tuple, np.floor(a1 / distance).astype(np.int64).tolist())):
            cells.setdefault(cell, []).append(k)

        def near(point):
            cx, cy = (int(v) for v in np.floor(point / distance))
            return [k for dx in (-1, 0, 1) for dy in (-1, 0, 1) for k in cells.get((cx + dx, cy + dy), ())]

        for i in range(len(rows)):
            if not free[i]:
                continue
            candidates = np.unique(np.array(near(a1[i]) + near(a2[i]), dtype=np.int64))
            candidates = candidates[free[candidates]]
            c1, c2 = a1[candidates], a2[candidates]
            same = (((c1 - a1[i]) ** 2).sum(1) <= d2) & (((c2 - a2[i]) ** 2).sum(1) <= d2)
            flipped = (((c1 - a2[i]) ** 2).sum(1) <= d2) & (((c2 - a1[i]) ** 2).sum(1) <= d2)
            found = candidates[same | flipped]
            free[found] = False
            reps.append(int(rows[i]))
            members.append(rows[found])
    rep = np.array(reps, dtype=np.int64)
    order = np.lexsort((-second[rep], -first[rep], over_all[rep])) if len(rep) else np.zeros(0, dtype=np.int64)
    members = [members[g] for g in order.tolist()]
    start = np.concatenate([[0], np.cumsum([len(m) for m in members], dtype=np.int64)]).astype(np.int64)
    return rep[order], np.concatenate(members).astype(np.int64) if members else np.zeros(0, dtype=np.int64), start


def _grouping_table(n, seed, offset, spread, distance):
    """n lines for test_grouping_as_before: anchors on a lattice of steps of `distance` / 2 and in
    between (lines exactly `distance` apart), some flipped and some copied, ranks with ties."""
    import helpers as sh
    rng = np.random.default_rng(seed)
    a1 = rng.integers(-spread, spread, (n, 2)) * (distance / 2)
    a1[n // 3:] += rng.random((n - n // 3, 2)) * distance
    a2 = a1 + rng.integers(5, 40, (n, 2)) * distance / 2
    near = rng.random(n) < 0.3  # a line next to one before it, exactly `distance` away or less
    source = rng.integers(0, max(n // 2, 1), n)
    step = rng.choice(np.array([[distance, 0], [0, -distance], [distance * 0.6, distance * 0.8],
                                [0.3 * distance, 0.1], [0, 0]]), n)
    a1[near], a2[near] = a1[source[near]] + step[near], a2[source[near]] - step[near]
    flip = rng.random(n) < 0.2
    a1[flip], a2[flip] = a2[flip].copy(), a1[flip].copy()
    a1, a2 = a1 + offset, a2 + offset
    columns = {"a1_xy": a1, "a2_xy": a2, "over_obstacles": rng.random(n) < 0.3,
               "clearance": rng.integers(0, 4, n).astype(np.float64),
               "length": rng.integers(20, 23, n).astype(np.float64),
               "height_max": np.round(rng.random(n) * 3, 1)}
    return sh.LineTable(columns)


@pytest.mark.parametrize("by", ["clearance", "longest", "height", "other"])
@pytest.mark.parametrize("distance", [1.0, 2.5, 5.0, 20.0])
@pytest.mark.parametrize("offset", [(0.0, 0.0), (-3.2e5, -1.7e4), (6.1e5, 5.4e6), (-7.0e5, 5.0e6)])
def test_grouping_as_before(by, distance, offset, monkeypatch):
    """mapping.group_lines with its cell index as numpy arrays and its loop in numba (in parts of
    GROUP_PART lines): the groups of before (rep, members, start), equal ranks, lines exactly
    `distance` apart, flipped lines, lines over obstacles, negative and large coordinates; an empty
    table and a single line."""
    import helpers as sh
    import mapping
    tables = [_grouping_table(n, seed, np.array(offset), spread, distance)
              for n, seed, spread in ((600, 1, 20), (2000, 2, 200), (300, 3, 3), (1, 4, 5), (40, 5, 1))]
    tables.append(sh.LineTable({k: np.zeros((0, 2)) if k.endswith("_xy") else np.zeros(0, dtype=bool)
                                if k == "over_obstacles" else np.zeros(0)
                                for k in ("a1_xy", "a2_xy", "over_obstacles", "clearance", "length", "height_max")}))
    for k, lines in enumerate(tables):
        old = _old_group_lines(lines, distance, by)
        for part in (mapping.GROUP_PART, 7):
            monkeypatch.setattr(mapping, "GROUP_PART", part)
            new = mapping.group_lines(lines, distance, by)
            for name, a, b in zip(("rep", "members", "start"), old, (new.rep, new.members, new.start)):
                assert b.dtype == a.dtype and np.array_equal(a, b), (k, part, name)
        if k == 0:
            assert 0 < len(new.rep) < len(lines) and new.sizes().max() > 2  # groups formed


def test_early_stop_of_the_evaluation(monkeypatch):
    """find_valid_lines' check is called after every evaluated part with the valid lines so far; when
    it raises, the evaluation stops there, the "checking lines" bar is closed and the counts so far
    are in stats (the pair search ran to its end)."""
    import linesearch as ls
    from progress import progress
    z, surface, anchors, _ = _canyon()
    full = ls.find_valid_lines(z, surface, anchors, 1.0, 20, 150, nmpt_mode="mark")
    monkeypatch.setattr(ls, "EVAL_PART", 100)  # parts of 100 pairs (the 200 chunks are smaller)
    seen, states = [], []
    progress.subscribe(states.append)

    def check(valid):
        seen.append(valid)
        if valid > 1000:
            raise ValueError("more than 1000 lines")
    stats = {}
    try:
        with pytest.raises(ValueError, match="more than 1000"):
            ls.find_valid_lines(z, surface, anchors, 1.0, 20, 150, nmpt_mode="mark", stats=stats, check=check)
    finally:
        progress.unsubscribe(states.append)
    assert len(full) > 2000 and seen == sorted(seen) and seen[-1] > 1000 >= seen[-2]
    assert stats["valid"] == seen[-1] < len(full) and stats["found"] >= len(full)
    last = [s for s in states if s["stage"] == "checking lines"][-1]
    assert last["done"] and last["extra"]["note"] == f"{seen[-1]} valid, stopped"
    assert ls.find_valid_lines(z, surface, anchors, 1.0, 20, 150, nmpt_mode="mark", check=lambda n: None
                               ).columns["length"].tolist() == full.columns["length"].tolist()


def test_evaluation_parts():
    """The pairs of the chunks in parts of the size asked, in their order, each chunk released."""
    import linesearch as ls
    chunks = [np.arange(2 * n).reshape(n, 2) + 1000 * k for k, n in enumerate((0, 3, 25, 1, 0, 4, 9))]
    whole = np.concatenate(chunks)
    for size in (1, 2, 5, 10, 100):
        given = list(chunks)
        parts = list(ls.evaluation_parts(given, size))
        assert given == [None] * len(chunks)
        assert all(len(p) == size for p in parts[:-1]) and 0 < len(parts[-1]) <= size
        assert np.array_equal(np.concatenate(parts), whole)
    assert list(ls.evaluation_parts([np.zeros((0, 2), dtype=np.int64)], 10)) == []


def _reference_case(model, first, strong, wall, max_dh=np.inf, max_length=150.0):
    """The canyon of test_kernels_independent_of_threads (anchors not in row-major order, NaNs) as
    a captured call of tools/perf_line_funnel.py, rebuilt into the kernels' arguments."""
    import dataclasses

    import sag
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
    import perf_line_funnel as plf
    rng = np.random.default_rng(11)
    z = (rng.random((160, 160)) * 3 + 100).astype(np.float32)
    z[:, :20] += 60
    z[:, 140:] += 55 + rng.random((160, 20)).astype(np.float32) * 10
    z[rng.random((160, 160)) < 0.003] = np.nan
    anchors = np.vstack([np.column_stack([np.arange(0, 160, 2), np.full(80, 19)]),
                         np.column_stack([np.arange(1, 160, 2), np.full(80, 140)]),
                         rng.integers(0, 160, (60, 2))])
    inputs = {"elevation": z, "anchors": anchors}
    if first:
        inputs["first"] = rng.random(len(anchors)) < 0.7
    if strong:
        inputs["strong"] = rng.random(len(anchors)) < 0.5
    params = {"res": 1.0, "min_length": 20.0, "max_length": max_length, "max_dh_ratio": 0.3, "max_dh": max_dh,
              "limits": {"max_wall_angle": 60.0} if wall else None, "sag": model == "sag",
              "rigging": dataclasses.asdict(sag.Rigging()), "sag_min_span": 20.0, "sag_max_span": max_length}
    return plf, plf.rebuild(inputs, params)


@pytest.mark.parametrize("model", ["formula", "sag"])
@pytest.mark.parametrize("max_length", [150.0, 60.0])
def test_free_rings_match_reference(model, max_length):
    """linesearch's free directions give the rings of the frozen reference of
    tools/line_funnel_kernels.py (the self-check of tools/perf_line_funnel.py analyse), capped
    at the largest need of a pair (60 m: 30 rings), which changes no decision."""
    plf, a = _reference_case(model, False, False, False, max_length=max_length)
    assert np.array_equal(plf.production_rings(a), plf.capped_rings(a))
    assert 0 < len(a.useful) < len(a.anchors)
    assert (a.rings > plf.capped_rings(a)).any() == (max_length < 127)


@pytest.mark.parametrize("model", ["formula", "sag"])
@pytest.mark.parametrize("first, strong, wall, max_dh, max_length", [
    (False, False, False, np.inf, 150.0), (True, False, True, np.inf, 150.0), (False, True, True, 12.0, 150.0),
    (True, True, False, 12.0, 150.0), (False, False, False, np.inf, 125.0), (True, False, True, 12.0, 125.0)])
def test_pairs_match_reference(model, first, strong, wall, max_dh, max_length):
    """linesearch's pair search gives the per-anchor counts and the pairs, in their order, of the
    frozen reference (ref_pairs), with and without a tile's first mask, --min-prominence's strong
    anchors, a wall-angle limit and a height difference limit; rings capped below 64 at 125 m."""
    plf, a = _reference_case(model, first, strong, wall, max_dh, max_length)
    chunks = plf.self_check(a)  # raises SelfCheckError when they differ
    candidates, checked, found = sum(counts.sum(axis=0) for _, counts, *_ in chunks)
    assert candidates >= checked > found > 10


@pytest.mark.parametrize("model", ["formula", "sag"])
def test_line_ok_matches_reference(model):
    """linesearch._line_ok (bit-reversal order for lines of LINE_ORDER_SPLIT to LINE_ORDER_MAX
    steps) decides as the frozen ref_line_ok on lines of every length class."""
    import linesearch as ls
    import sag
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
    import line_funnel_kernels as K
    rng = np.random.default_rng(5)
    z = (rng.random((1300, 1300)) * 2 + 100).astype(np.float32)
    z[rng.random(z.shape) < 1e-5] = np.nan
    if model == "sag":
        table = sag.EnvelopeTable(sag.Rigging(), 2, 1300)
        args = (True, np.log(table.spans), table.RATIOS.astype(np.float64), np.ascontiguousarray(table.sag),
                float(table.rig.fall_zone))
    else:
        args = (False, np.zeros(2), np.zeros(2), np.zeros((2, 2, 2)), 0.0)
    decided = {True: 0, False: 0}
    for _ in range(3000):
        r1, c1 = rng.integers(0, 1300, 2)
        steps = int(rng.choice([2, 5, 60, 129, 130, 400, 1024, 1025, 1200]))
        r2, c2 = r1 + int(rng.integers(-steps, steps + 1)), c1 + steps * int(rng.choice([-1, 1]))
        if not (0 <= r2 < 1300 and 0 <= c2 < 1300):
            continue
        z[r1, c1] = z[r2, c2] = 140.0 + rng.random() * 20  # anchors high above the terrain
        if rng.random() < 0.5:  # one pixel too high somewhere
            k = int(rng.integers(1, steps))
            z[r1 + int(np.rint((r2 - r1) * k / steps)), c1 + int(np.rint((c2 - c1) * k / steps))] = 200
        ok = ls._line_ok(z, r1, c1, r2, c2, 1.0, *args, 0.0, 0.0, 0.0, 0.25)  # end zone 0, lift 0
        assert ok == K.ref_line_ok(z, r1, c1, r2, c2, 1.0, *args)
        decided[bool(ok)] += 1
    assert min(decided.values()) > 100


@pytest.mark.parametrize("model", ["formula", "sag"])
@pytest.mark.parametrize("buffer", [1, 3])
def test_pair_buffer_overflow_matches_reference(model, buffer):
    """linesearch.pair_chunk with a buffer of a few pairs per anchor: the anchors that found more
    get the writing pass, and the counts and the pairs, in their order, are still those of the
    frozen reference (ref_pairs), also with a tile's first mask and in one chunk of every anchor."""
    import linesearch as ls
    for first in (False, True):
        plf, a = _reference_case(model, first, False, True)
        head, tail, todo_all = plf.production_args(a, plf.production_directions(a))
        overflowed = 0
        for todo in plf.chunks_of(todo_all) + [todo_all]:
            ref_counts, ref_out = plf.two_passes(plf.K.ref_pairs, a, todo)
            counts, out = ls.pair_chunk(head, todo, tail, buffer=buffer)
            assert np.array_equal(counts[:, 1:], ref_counts[:, 1:]) and np.array_equal(out, ref_out)
            assert np.array_equal(counts, ls.pair_chunk(head, todo, tail)[0])
            overflowed += int((counts[:, 2] > buffer).sum())
        assert overflowed > 5 and len(ref_out) > 10


def _random_case(model, seed, first, strong, wall, max_length=150.0, size=400):
    """Random terrain with raised blocks whose edges hold anchors (lines in every direction,
    cells in every sector around an anchor, also across the -pi / pi seam of atan2) and
    anchors anywhere, as a captured call rebuilt into the kernels' arguments."""
    import dataclasses

    import sag
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
    import perf_line_funnel as plf
    rng = np.random.default_rng(seed)
    z = (rng.random((size, size)) * 3 + 100).astype(np.float32)
    anchors = []
    for _ in range(12):
        h, w = rng.integers(10, 80, 2)
        r0, c0 = rng.integers(0, size - h), rng.integers(0, size - w)
        z[r0:r0 + h, c0:c0 + w] += 40 + rng.random() * 40
        edge = np.vstack([np.column_stack([np.full(w, r0), np.arange(c0, c0 + w)]),
                          np.column_stack([np.full(w, r0 + h - 1), np.arange(c0, c0 + w)]),
                          np.column_stack([np.arange(r0, r0 + h), np.full(h, c0)]),
                          np.column_stack([np.arange(r0, r0 + h), np.full(h, c0 + w - 1)])])
        anchors.append(edge[rng.random(len(edge)) < 0.3])
    anchors.append(rng.integers(0, size, (150, 2)))
    anchors = np.unique(np.vstack(anchors), axis=0)  # row-major, as helpers.find_significant_slopes
    z[rng.random((size, size)) < 0.002] = np.nan
    inputs = {"elevation": z, "anchors": anchors}
    if first:
        inputs["first"] = rng.random(len(anchors)) < 0.7
    if strong:
        inputs["strong"] = rng.random(len(anchors)) < 0.5
    params = {"res": 1.0, "min_length": 20.0, "max_length": max_length, "max_dh_ratio": 0.3, "max_dh": np.inf,
              "limits": {"max_wall_angle": 60.0} if wall else None, "sag": model == "sag",
              "rigging": dataclasses.asdict(sag.Rigging()), "sag_min_span": 20.0, "sag_max_span": max_length}
    return plf, plf.rebuild(inputs, params)


@pytest.mark.parametrize("model", ["formula", "sag"])
@pytest.mark.parametrize("seed, first, strong, wall, max_length", [
    (1, False, False, False, 150.0), (2, True, False, True, 150.0), (3, False, True, False, 60.0),
    (4, True, True, True, 60.0), (5, False, False, True, 100.0)])
def test_f8c_skips_only_rings_failures(model, seed, first, strong, wall, max_length):
    """F8c (linesearch._pairs: the cells outside the anchor's open sectors or without a partner
    open towards it, the partners whose need exceeds the anchor's rings in their cell's sectors
    and the partners with no sector open towards their cell's sectors) skips only pairs the
    rings test rejects: on random grids the written pairs and the
    checked and found counts per anchor are the frozen reference's (self_check raises when
    not), the candidates are the reference's less those N1 and F8c skip, no checked pair would
    have been skipped, and every part of the rule skips something."""
    import linesearch as ls
    plf, a = _random_case(model, seed, first, strong, wall, max_length)
    K = plf.K
    chunks = plf.self_check(a)
    c = np.vstack([c for _, _, c, _, _ in chunks]).sum(axis=0)
    assert c[K.C_UNSAFE + 3] == 0 and c[K.C_CHECKED] > c[K.C_FOUND] > 20
    assert c[K.C_SKIP + 3] > c[K.C_F8C_OWN] > 0 and c[K.C_F8C_PARTNERS] > 0 and c[K.C_F8C_PARTNER_MASK] > 0
    if max_length == 150.0:  # with rings capped at 30 (60 m), N1 skips what F8c would
        assert c[K.C_F8C_CANDIDATES] > c[K.C_F8C_MASK_CANDIDATES] > 0 and c[K.C_F8C_PARTNER_OWN] > 0
    # the open sectors of the cells (pair_arguments) are the tool's
    useful, rows, slot = plf.production_directions(a)
    open_cells = ls._cell_open(rows, ls.smallest_need(a.min_length, a.res), a.order, a.starts, slot)
    assert np.array_equal(open_cells, K.cell_summary(a.order, a.starts, a.elev, a.rings, a.need_min)[0])


def test_cell_sectors_hold_every_pixel():
    """linesearch._cell_sectors (the sectors of a cell seen from an anchor outside it, one of
    margin at each end) gives the sectors of the tool's _arc and holds _sector of every pixel of
    the cell, also for cells across the -pi / pi seam of atan2 and next to the anchor."""
    import linesearch as ls
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
    import line_funnel_kernels as K
    rng = np.random.default_rng(3)
    width = 2 * np.pi / ls.SECTORS
    spans = 0
    for n in range(3000):
        cell = int(rng.integers(1, 40))
        if n % 3 == 0:  # the box of a cell next to the anchor's own, in any direction
            gy, gx = rng.integers(-1, 2, 2)
            r0, c0 = gy * cell - int(rng.integers(0, cell)), gx * cell - int(rng.integers(0, cell))
        else:
            r0, c0 = rng.integers(-300, 300, 2)
        r1, c1 = r0 + cell - 1, c0 + cell - 1
        if r0 <= 0 <= r1 and c0 <= 0 <= c1:
            continue  # the anchor's own cell: _pairs never skips it
        s_lo, s_hi = ls._cell_sectors(r0, r1, c0, c1)
        alo, ahi = K._arc(r0, r1, c0, c1)
        assert (s_lo, s_hi) == (int(np.floor(alo / width)) - 1, int(np.floor(ahi / width)) + 1)
        assert 0 < s_hi - s_lo + 1 <= ls.SECTORS // 2 + 4
        allowed = {s % ls.SECTORS for s in range(s_lo, s_hi + 1)}
        for dr in range(r0, r1 + 1):
            for dc in range(c0, c1 + 1):
                assert ls._sector(dr, dc) in allowed, (r0, r1, c0, c1, dr, dc)
        spans += (s_lo % ls.SECTORS) > (s_hi % ls.SECTORS)  # across the seam
    assert spans > 50


def test_wall_angles():
    """The downslope direction of a slope and the angle of lines leaving it."""
    import helpers as sh
    rows, cols = np.mgrid[0:20, 0:20]
    terrain = 100.0 - 2.0 * cols  # falls towards the east (growing col)
    terrain[5, 5] = np.nan        # no data next to an anchor: its elevation is used instead
    down = sh.downslope(terrain, [(10, 10), (4, 4), (0, 0)], 1.0)
    assert np.allclose(down[0], [0, 1])
    # next to no data and at the corner of the grid: still a direction, roughly east
    assert np.allclose(np.hypot(down[1:, 0], down[1:, 1]), 1) and (down[1:, 1] > 0.9).all()
    a1, a2 = np.array([[10, 10], [10, 10], [10, 10]]), np.array([[10, 18], [2, 10], [18, 18]])
    angle1, angle2 = sh.wall_angles(a1, a2, down[[0, 0, 0]], down[[0, 0, 0]])
    assert np.allclose(angle1, [0, 90, 45]) and np.allclose(angle2, [180, 90, 135])  # east, north, south-east
    assert np.array_equal(sh.downslope(np.full((3, 3), 5.0), [(1, 1)], 1.0), [[0, 0]])  # flat: 90° to all
    assert np.allclose(sh.wall_angles(np.array([[1, 1]]), np.array([[1, 2]]), np.zeros((1, 2)), np.zeros((1, 2))), 90)


def _flooded_prominence(z, pixel, span):
    """Prominence by labelling the terrain at or above every level (slow, for the test)."""
    from scipy import ndimage
    e = z[pixel]
    for level in sorted(set(z[~np.isnan(z)].tolist()), reverse=True):
        if level <= e:
            labels, _ = ndimage.label(z >= level, structure=np.ones((3, 3)))
            rows, cols = np.nonzero(labels == labels[pixel])
            if rows.max() - rows.min() + 1 >= span or cols.max() - cols.min() + 1 >= span:
                return e - level
    return np.nan


def test_prominence_matches_flooding():
    import terrain
    rng = np.random.default_rng(3)
    z = np.round(rng.random((40, 50)) * 20, 1).astype(np.float32)
    z[rng.random(z.shape) < 0.05] = np.nan
    anchors = np.argwhere(~np.isnan(z))[rng.integers(0, 1800, 60)]
    anchors = np.vstack([anchors, anchors[:3]])  # several anchors on one pixel
    fast = terrain.prominence(z, anchors, 2.0, 24)  # 12 pixels
    slow = np.array([_flooded_prominence(z, tuple(a), 12) for a in anchors])
    assert np.allclose(fast, slow, equal_nan=True) and np.nanmax(fast) > 3


def _old_prominence(elevation, anchors, res, span):
    """terrain.prominence before 2026-10-31: the union-find over every pixel of the grid."""
    import math

    import terrain
    from numba import njit

    @njit
    def run(z, order, anchor_pixel, span):
        h, w = z.shape
        n = h * w
        parent = np.full(n, -1, dtype=np.int32)
        size = np.ones(n, dtype=np.int32)
        r0, r1 = np.empty(n, dtype=np.int32), np.empty(n, dtype=np.int32)
        c0, c1 = np.empty(n, dtype=np.int32), np.empty(n, dtype=np.int32)
        big = np.zeros(n, dtype=np.bool_)
        head, tail = np.full(n, -1, dtype=np.int32), np.full(n, -1, dtype=np.int32)
        first = np.full(n, -1, dtype=np.int32)
        nxt = np.full(anchor_pixel.size, -1, dtype=np.int32)
        result = np.full(anchor_pixel.size, np.nan)
        for a in range(anchor_pixel.size):
            p = anchor_pixel[a]
            nxt[a] = first[p]
            first[p] = a
        for k in range(order.size):
            p = order[k]
            level = np.float64(z.flat[p])
            r, c = p // w, p % w
            parent[p] = p
            r0[p], r1[p], c0[p], c1[p] = r, r, c, c
            big[p] = span <= 1
            if first[p] >= 0:
                head[p] = first[p]
                last = first[p]
                while nxt[last] >= 0:
                    last = nxt[last]
                tail[p] = last
            root = p
            for dr in (-1, 0, 1):
                for dc in (-1, 0, 1):
                    rr, cc = r + dr, c + dc
                    if (dr == 0 and dc == 0) or rr < 0 or cc < 0 or rr >= h or cc >= w:
                        continue
                    q = rr * w + cc
                    if parent[q] < 0:
                        continue
                    other = terrain._find(parent, q)
                    if other == root:
                        continue
                    if size[other] > size[root]:
                        root, other = other, root
                    parent[other] = root
                    size[root] += size[other]
                    r0[root], r1[root] = min(r0[root], r0[other]), max(r1[root], r1[other])
                    c0[root], c1[root] = min(c0[root], c0[other]), max(c1[root], c1[other])
                    big[root] = big[root] or big[other]
                    if head[other] >= 0:
                        if head[root] >= 0:
                            nxt[tail[root]] = head[other]
                        else:
                            head[root] = head[other]
                        tail[root] = tail[other]
                        head[other] = -1
            if not big[root] and (r1[root] - r0[root] + 1 >= span or c1[root] - c0[root] + 1 >= span):
                big[root] = True
            if big[root] and head[root] >= 0:
                a = head[root]
                while a >= 0:
                    result[a] = np.float64(z.flat[anchor_pixel[a]]) - level
                    a = nxt[a]
                head[root] = -1
        return result

    z = np.ascontiguousarray(elevation, dtype=np.float32)
    flat = z.ravel()
    valid = np.flatnonzero(~np.isnan(flat))
    order = valid[np.argsort(-flat[valid], kind="stable")]
    pixels = anchors[:, 0] * z.shape[1] + anchors[:, 1]
    return run(z, order.astype(np.int64), pixels, max(1, math.ceil(span / res)))


def _old_drop(elevation, anchors, res, radius):
    """terrain.drop before 2026-10-31: two minimum filters of scipy over the whole grid."""
    import math

    from scipy import ndimage
    size = 2 * max(1, math.ceil(radius / res)) + 1
    z = np.where(np.isnan(elevation), np.inf, np.asarray(elevation, dtype=np.float32))
    lowest = ndimage.minimum_filter1d(z, size, axis=1, mode="constant", cval=np.inf)
    lowest = ndimage.minimum_filter1d(lowest, size, axis=0, mode="constant", cval=np.inf)
    e = np.asarray(elevation[anchors[:, 0], anchors[:, 1]], dtype=np.float64)
    return e - lowest[anchors[:, 0], anchors[:, 1]].astype(np.float64)


@pytest.mark.parametrize("seed", [0, 1, 2])
def test_prominence_and_drop_match_the_whole_grid(seed):
    """Prominence over the windows of the anchors and the separable minimum of the drop give
    exactly the values of the union-find and the filters over the whole grid: random terrain
    with ties, plateaus, holes, anchors at the edges, on holes and on one pixel together."""
    import terrain
    rng = np.random.default_rng(seed)
    shape = [(70, 150), (131, 67), (40, 300)][seed]
    z = np.round(rng.random(shape) * 40 + np.linspace(0, 30, shape[1]), 0).astype(np.float32)
    z[10:25, 20:45] = 33                                      # a plateau
    z[rng.random(shape) < 0.04] = np.nan
    z[:, -3:] = np.nan                                        # a band without data
    h, w = shape
    picked = np.argwhere(rng.random(shape) < [0.003, 0.02, 0.1][seed])
    edges = np.array([[0, 0], [h - 1, w - 1], [0, w - 4], [h - 1, 5], [h // 2, 0], [3, w - 1]])
    anchors = np.vstack([picked, edges, picked[:4]])          # several anchors on one pixel
    for res, span in [(1.0, 0.5), (1.0, 1), (1.0, 2), (1.0, 5), (2.0, 24), (1.0, 37), (0.5, 40), (1.0, 1000)]:
        new = terrain.prominence(z, anchors, res, span)
        assert np.array_equal(new, _old_prominence(z, anchors, res, span), equal_nan=True), (res, span)
        ordered = anchors[np.lexsort((anchors[:, 1], anchors[:, 0]))]  # row-major: no lexsort inside
        assert np.array_equal(terrain.prominence(z, ordered, res, span), _old_prominence(z, ordered, res, span),
                              equal_nan=True), (res, span)
    for res, radius in [(1.0, 0.5), (1.0, 1), (1.0, 3), (2.0, 21), (1.0, 64), (1.0, 500)]:
        new = terrain.drop(z, anchors, res, radius)
        assert np.array_equal(new, _old_drop(z, anchors, res, radius), equal_nan=True), (res, radius)
    assert np.isnan(terrain.prominence(z, anchors, 1.0, 5)[len(picked) + 5])  # an anchor without data
    # The windows: the pixels with data within reach (Chebyshev) of an anchor, in either index type
    by_row = np.lexsort((anchors[:, 1], anchors[:, 0]))
    rows, cols = anchors[by_row, 0], anchors[by_row, 1]
    starts = np.searchsorted(rows, np.arange(h + 1))
    for reach in (0, 1, 7, 400):
        near = np.zeros(shape, bool)
        for r, c in anchors:
            near[max(0, r - reach):r + reach + 1, max(0, c - reach):c + reach + 1] = True
        expected = np.flatnonzero(near & ~np.isnan(z))
        for kind in (np.int32, np.int64):
            got = terrain._window(z, rows, cols, starts, reach, np.zeros(0, dtype=kind))
            assert got.dtype == kind and np.array_equal(got, expected), (reach, kind)


def test_prominence_and_drop_of_a_tower():
    """A 30 m cone on a plain next to a wall: an anchor on the cone has its height above the
    plain, the edge of the wall none; the drop is the height above the lowest ground near."""
    import terrain
    yy, xx = np.mgrid[0:400, 0:400]
    z = 100.0 + np.maximum(0, 30 - np.hypot(yy - 200, xx - 200) * 1.5)
    z[:, 330:] = 200
    anchors = np.array([[200, 205], [200, 335], [200, 330]])
    assert np.allclose(terrain.prominence(z, anchors, 1.0, 300), [22.5, 0, 0])
    assert np.isnan(terrain.prominence(z, anchors, 1.0, 1000)).all()  # nothing spans more than the grid
    import runs
    assert runs.rounded(float("nan"), 1) is None and runs.rounded(2.345, 1) == 2.3
    assert np.allclose(terrain.drop(z, anchors, 1.0, 50), [22.5, 100, 100])
    assert np.allclose(terrain.drop(z, anchors[1:2], 1.0, 4), [0])  # the wall's foot is 5 px away


def test_webbing_heights():
    """Heights of the webbing above the terrain: margin + leash fall (formula) or fall zone (sag)."""
    import helpers as sh
    import sag
    terrain = np.full((3, 21), 100.0)
    terrain[1, 0] = terrain[1, 20] = 140.0  # two anchors 20 m apart, 40 m above the flat ground
    _, _, length, clearance, _, height_max, height_mean, high_pct = sh.evaluate_line(
        (1, 0), (1, 20), terrain, 1.0, high_above=39.0)
    # the formula's webbing: 140 - 0.15 * (distance to the nearer anchor), lowest in the middle
    assert abs(height_max - (40 - 0.15)) < 1e-9 and abs(clearance - (40 - 0.15 * 10 - sh.LEASH_FALL)) < 1e-9
    assert abs(height_mean - (40 - 0.15 * sum(min(k, 20 - k) for k in range(1, 20)) / 19)) < 1e-9
    assert high_pct == 100.0 * 12 / 19  # 39 m or more: within 6 m of an anchor, 2 x 6 of 19 pixels
    profile = sh.line_profile((1, 0), (1, 20), terrain, 1.0)
    assert profile["max_height"] == [1.0, 39.85]
    # sag: the chord (140) minus the sag under the athlete, so the highest point is next to an anchor
    table = sag.EnvelopeTable(sag.Rigging(fall_zone=3), 10, 40)
    t = np.arange(1, 20) / 20
    webbing = sh.max_safe_elevation(t, 20.0, 140.0, 140.0, table) + 3
    result = sh.evaluate_line((1, 0), (1, 20), terrain, 1.0, sag_table=table)
    assert result[5] == float(np.max(webbing - 100.0)) and result[6] == float(np.cumsum(webbing - 100.0)[-1]) / 19


def _near_by_dilation(mask, metres, res):
    """sources.filling.near before 2026-11-03: n iterations of a 3 x 3 dilation (the reference)."""
    import math
    from scipy import ndimage
    if metres <= 0:
        return mask
    return ndimage.binary_dilation(mask, structure=np.ones((3, 3)), iterations=max(1, math.ceil(metres / res)))


def test_near_matches_the_dilation():
    """near() grows a mask in one pass: exactly the n iterations of a 3 x 3 dilation it replaced, also at
    the grid's edges (nothing outside the grid is in the mask), for empty and full masks."""
    rng = np.random.default_rng(7)
    shapes = [(1, 1), (1, 9), (9, 1), (37, 53), (64, 64)]
    for shape in shapes:
        masks = [np.zeros(shape, bool), np.ones(shape, bool)]
        for density in (0.002, 0.02, 0.2, 0.6):
            masks.append(rng.random(shape) < density)
        edges = np.zeros(shape, bool)  # touching the grid's edges and corners only
        edges[0, ::5] = edges[-1, 2::7] = edges[::4, 0] = edges[1::6, -1] = True
        masks.append(edges)
        corner = np.zeros(shape, bool)
        corner[-1, -1] = True
        masks.append(corner)
        for mask in masks:
            for n in range(1, 51):
                for metres, res in ((n, 1.0), (2.0 * n - 0.5, 2.0), (0.3 * n, 0.3)):
                    expected = _near_by_dilation(mask, metres, res)
                    got = src.near(mask, metres, res)
                    assert got.dtype == bool and got.shape == mask.shape
                    assert np.array_equal(got, expected), (shape, n, metres, res)
            assert src.near(mask, 0, 1.0) is mask and src.near(mask, 0.4, 1.0).sum() >= mask.sum()


def _slopes_before(elevation, res, slope_threshold, area_mask, slope=None, block_rows=512):
    """helpers.find_significant_slopes before 2026-11-03 (one thread, blocks of 512 rows), the reference."""
    height, width = elevation.shape
    anchors = []
    for r0 in range(0, height, block_rows):
        r1 = min(height, r0 + block_rows)
        if slope is None:
            h0, h1 = max(0, r0 - 1), min(height, r1 + 1)
            z = np.asarray(elevation[h0:h1], dtype=np.float32)
            gy, gx = np.gradient(z, res)
            block = np.degrees(np.arctan(np.hypot(gx, gy)))[r0 - h0:r0 - h0 + (r1 - r0)]
        else:
            block = np.asarray(slope[r0:r1])
        rows, cols = np.nonzero(block >= slope_threshold)
        rows += r0
        inside = area_mask[rows, cols]
        anchors.append(np.column_stack([rows[inside], cols[inside]]).astype(np.int32))
    return np.concatenate(anchors) if anchors else np.empty((0, 2), dtype=np.int32)


def test_significant_slopes_as_before():
    """find_significant_slopes in blocks on threads: exactly the anchors of the old single-threaded
    pass, in row-major order (what terrain.prominence's lexsort gives), for any block size and thread
    count, with NaN, a slope raster and grids of two rows or columns (np.gradient needs two)."""
    import helpers as sh
    rng = np.random.default_rng(5)
    for shape in [(2, 2), (2, 40), (40, 2), (2, 3), (511, 7), (513, 9), (700, 300), (1500, 120)]:
        z = np.cumsum(rng.normal(0, 2.0, shape), axis=0).astype(np.float32)
        z += rng.normal(0, 1.5, shape).astype(np.float32)
        z[rng.random(shape) < 0.02] = np.nan
        mask = rng.random(shape) < 0.9
        slope = (rng.random(shape) * 90).astype(np.float32)
        for res, threshold in ((1.0, 45), (0.5, 60), (2.0, 30)):
            expected = _slopes_before(z, res, threshold, mask)
            expected_slope = _slopes_before(z, res, threshold, mask, slope)
            for block_rows, threads in ((256, None), (512, 1), (1, 3), (7, 8), (100, 2), (2000, 4)):
                got = sh.find_significant_slopes(z, res, threshold, mask, block_rows=block_rows, threads=threads)
                assert got.dtype == np.int32 and np.array_equal(got, expected), (shape, res, block_rows, threads)
                got = sh.find_significant_slopes(z, res, threshold, mask, slope, block_rows=block_rows,
                                                 threads=threads)
                assert np.array_equal(got, expected_slope), (shape, res, block_rows, threads)
            if len(expected):
                assert np.array_equal(np.lexsort((expected[:, 1], expected[:, 0])), np.arange(len(expected)))


def test_seams_as_before():
    """search.at_seams: the seams of a mask tested at the anchors give exactly the old expression over
    the whole grid (scipy's 3 x 3 dilation and not its erosion, border 0), read at the anchors: every
    pixel an anchor, grids of 1 x 1 up to 50 x 50, gaps at the edges and corners, empty and full masks."""
    from scipy import ndimage
    import search

    def before(gaps, anchors):
        unreliable = ndimage.binary_dilation(gaps, structure=np.ones((3, 3))) & \
            ~ndimage.binary_erosion(gaps, structure=np.ones((3, 3)))
        return unreliable[anchors[:, 0], anchors[:, 1]]

    rng = np.random.default_rng(11)
    shapes = [(1, 1), (1, 2), (2, 1), (2, 2), (1, 7), (7, 1), (3, 3), (4, 9), (13, 5), (50, 50)]
    shapes += [tuple(rng.integers(1, 51, 2)) for _ in range(20)]
    for shape in shapes:
        masks = [np.zeros(shape, bool), np.ones(shape, bool)]
        for density in (0.05, 0.3, 0.5, 0.8, 0.97):
            masks += [rng.random(shape) < density for _ in range(3)]
        edges = np.zeros(shape, bool)
        edges[0, ::3] = edges[-1, 1::4] = edges[::2, 0] = edges[2::5, -1] = True
        masks += [edges, ~edges]
        for corner in ((0, 0), (0, -1), (-1, 0), (-1, -1)):
            mask = np.zeros(shape, bool)
            mask[corner] = True
            masks += [mask, ~mask]
        rows, cols = np.indices(shape)
        anchors = np.column_stack([rows.ravel(), cols.ravel()]).astype(np.int32)
        for mask in masks:
            assert np.array_equal(search.at_seams(mask, anchors), before(mask, anchors)), shape
            some = anchors[rng.random(len(anchors)) < 0.3]  # a subset, and none
            assert np.array_equal(search.at_seams(mask, some), before(mask, some)), shape
    assert search.at_seams(np.ones((4, 4), bool), np.empty((0, 2), np.int32)).shape == (0,)


def test_coast_within_osm_keeps_islets_and_the_sea_side(monkeypatch):
    """coast within osm:<name>: the coastline within the reach of the area, not clipped to its land."""
    import osm
    from shapely.geometry import Point, box
    m = 1 / 111320  # about a metre in degrees here (near the equator)
    island = box(0, 0, 1000 * m, 1000 * m)
    rings = {"island": island.exterior, "islet": Point(1300 * m, 500 * m).buffer(50 * m).exterior,
             "far": Point(2600 * m, 500 * m).buffer(50 * m).exterior, "away": Point(5000 * m, 500 * m).buffer(50 * m).exterior}
    monkeypatch.setattr(osm, "search", lambda name, cache_dir, whole=False: {"geojson": island.__geo_interface__})
    monkeypatch.setattr(osm, "theme", lambda theme, *bounds_and_cache: [
        {"id": k, "geometry": g} for k, g in rings.items()])
    area = ar.from_spec("coast", 100, "osm:Island", "unused", reach=1000)
    assert area.geometry.contains(Point(1300 * m, 550 * m))     # the islet 300 m off the coast
    assert area.geometry.contains(Point(1050 * m, 500 * m))     # the sea side of the coastline
    assert not area.geometry.contains(Point(2600 * m, 550 * m))  # 1.6 km away: left out...
    assert len(area.notes) == 1 and "1 piece(s)" in area.notes[0]  # ...with a note; 4 km away: nothing
    clipped = ar.from_spec("coast", 100, f"0,0,{1000 * m},{1000 * m}", "unused", reach=1000)
    assert not clipped.geometry.contains(Point(1050 * m, 500 * m))  # a box clips the band


def test_world_water_read_once_for_the_tiles(tmp_path, monkeypatch):
    """coast.sea_mask of the tiles of a search (extent: its whole grid) reads the world file's polygons
    once, and each tile's mask is the one the polygons read for that tile alone gave."""
    import geopandas as gpd
    import coast
    from shapely.geometry import Point, box
    rng = np.random.default_rng(3)
    polygons = [Point(14.20 + 0.10 * rng.random(), 36.00 + 0.06 * rng.random()).buffer(0.001 + 0.006 * rng.random())
                for _ in range(80)] + [box(14.17, 35.99, 14.34, 36.004), box(14.25, 36.07, 14.40, 36.2)]
    shapefile = str(tmp_path / "water_polygons.shp")
    gpd.GeoDataFrame(geometry=polygons, crs="EPSG:4326").to_file(shapefile)
    monkeypatch.setattr(coast, "world_polygons", lambda cache_dir, update=None: shapefile)
    reads = []
    read_file = gpd.read_file
    monkeypatch.setattr(gpd, "read_file", lambda *a, **k: reads.append(k["bbox"]) or read_file(*a, **k))
    crs = "EPSG:32633"
    from rasterio.warp import transform_bounds
    whole = gd.make_grid(transform_bounds("EPSG:4326", crs, 14.2, 36.0, 14.3, 36.06), 5, crs)
    left, bottom, right, top = whole.bounds
    tiles = [gd.make_grid((x, y, min(x + 3000, right), min(y + 2500, top)), 5, crs)
             for x in np.arange(left, right, 2500) for y in np.arange(bottom, top, 2000)]
    coast._WORLD_READ.clear()
    for tile in tiles:
        sea, _, _ = coast.sea_mask(tile, "unused", "world", np.ones((tile.height, tile.width), bool), extent=whole)
        assert sea.dtype == bool and sea.shape == (tile.height, tile.width)
        alone = read_file(shapefile, bbox=coast._grid_bbox_wgs84(tile)).to_crs(crs)
        assert np.array_equal(sea, coast._rasterize(alone.geometry, tile))
    assert len(reads) == 1 and reads[0] == coast._grid_bbox_wgs84(whole)
    assert sum(coast._rasterize(gpd.GeoSeries(polygons, crs="EPSG:4326").to_crs(crs), t).sum() for t in tiles) > 0
    coast._WORLD_READ.clear()


def _fill_before(target, other, gaps, res):
    """sources.filling._fill of 1056134 (the reference), without its progress bar."""
    from scipy import ndimage
    from sources.filling import GAP_MATCH_SLOPE, GAP_RING, GAP_MAX_LOCAL_SHIFT
    values = np.asarray(target)
    gy, gx = np.gradient(np.where(np.isfinite(values), values, other), res)
    flat = np.degrees(np.arctan(np.hypot(gx, gy))) < GAP_MATCH_SLOPE
    both = ~gaps & np.isfinite(values) & np.isfinite(other) & flat
    overall = float(np.median(values[both] - other[both])) if both.any() else 0.0
    labels, count = ndimage.label(gaps, structure=np.ones((3, 3)))
    ring = ndimage.grey_dilation(labels, size=(GAP_RING * 2 + 1,) * 2) * (both & (labels == 0))
    offsets = np.full(count + 1, overall)
    if ring.any():
        near = ring > 0
        local = ndimage.median(values[near] - other[near], ring[near], index=np.arange(1, count + 1))
        local = np.asarray(local, dtype=float)
        usable = np.isfinite(local) & (np.abs(local - overall) <= GAP_MAX_LOCAL_SHIFT)
        offsets[1:] = np.where(usable, local, overall)
    count = int((gaps & np.isfinite(other)).sum())
    target[gaps] = other[gaps] + offsets[labels[gaps]]
    return count


@pytest.mark.parametrize("seed", [0, 1, 2, 4])
def test_gap_fill_as_before(seed, tmp_path):
    """_fill with its temporaries computed in place fills every gap with the same float32 bits as before."""
    terrain, gaps, other = _gap_fill_case(seed)
    shape = terrain.shape
    grids = []
    for name in ("new", "old"):
        grid = np.lib.format.open_memmap(str(tmp_path / f"{name}.npy"), mode="w+", dtype=np.float32, shape=shape)
        grid[:] = np.where(gaps, np.nan, terrain)
        grids.append(grid)
    assert src.filling._fill(grids[0], other, gaps, 1.0) == _fill_before(grids[1], other, gaps, 1.0)
    assert np.array_equal(np.asarray(grids[0]).view(np.uint32), np.asarray(grids[1]).view(np.uint32))


def _place_before(src_file, grid, mosaic, categorical=False, shift=(0.0, 0.0)):
    """sources.mosaic._place of 1056134 (the reference, a float32 mosaic for categorical rasters too)."""
    import math
    import rasterio as rio
    from affine import Affine
    from rasterio.transform import from_origin
    from rasterio.warp import Resampling, reproject, transform_bounds
    from rasterio.windows import from_bounds
    from sources.layer import _clean
    from sources.mosaic import WARP_THREADS
    clean = (lambda band: band.astype(np.float32)) if categorical else _clean
    grid_crs = rio.crs.CRS.from_user_input(grid.crs)
    src_crs = src_file.crs or grid_crs
    moved = Affine.translation(*shift)
    src_bounds = rio.coords.BoundingBox(src_file.bounds.left + shift[0], src_file.bounds.bottom + shift[1],
                                        src_file.bounds.right + shift[0], src_file.bounds.top + shift[1])
    same_grid = src_crs == grid_crs and shift == (0.0, 0.0) and math.isclose(abs(src_file.res[0]), grid.res) \
        and math.isclose(abs(src_file.res[1]), grid.res)
    if same_grid:
        row_off = int(round((grid.top - src_file.bounds.top) / grid.res))
        col_off = int(round((src_file.bounds.left - grid.left) / grid.res))
        if abs(row_off * grid.res - (grid.top - src_file.bounds.top)) < grid.res / 100:
            r0, c0 = max(row_off, 0), max(col_off, 0)
            r1, c1 = min(row_off + src_file.height, grid.height), min(col_off + src_file.width, grid.width)
            if r0 < r1 and c0 < c1:
                window = rio.windows.Window(c0 - col_off, r0 - row_off, c1 - c0, r1 - r0)
                values = clean(src_file.read(1, window=window, masked=True).astype(np.float32).filled(np.nan))
                target = mosaic[r0:r1, c0:c1]
                mosaic[r0:r1, c0:c1] = np.where(np.isnan(target), values, target)
            return
    left, bottom, right, top = transform_bounds(src_crs, grid.crs, *src_bounds)
    c0 = max(0, int(math.floor((left - grid.left) / grid.res)))
    c1 = min(grid.width, int(math.ceil((right - grid.left) / grid.res)))
    r0 = max(0, int(math.floor((grid.top - top) / grid.res)))
    r1 = min(grid.height, int(math.ceil((grid.top - bottom) / grid.res)))
    if r0 >= r1 or c0 >= c1:
        return
    src_res = abs(src_file.res[0]) * (111320 if src_crs.is_geographic else 1)
    if categorical:
        resampling = Resampling.nearest
    else:
        resampling = Resampling.average if src_res < grid.res * 0.75 else Resampling.bilinear
    window_transform = from_origin(grid.left + c0 * grid.res, grid.top - r0 * grid.res, grid.res, grid.res)
    values = np.full((r1 - r0, c1 - c0), np.nan, dtype=np.float32)
    area = transform_bounds(grid.crs, src_crs, *grid.bounds)
    area = (area[0] - shift[0], area[1] - shift[1], area[2] - shift[0], area[3] - shift[1])
    margin = 3 * max(abs(src_file.res[0]), abs(src_file.res[1]))
    window = from_bounds(area[0] - margin, area[1] - margin, area[2] + margin, area[3] + margin,
                         src_file.transform).round_offsets().round_lengths()
    window = window.intersection(rio.windows.Window(0, 0, src_file.width, src_file.height))
    band = src_file.read(1, window=window, masked=True).astype(np.float32).filled(np.nan)
    reproject(clean(band), values, src_transform=moved @ src_file.window_transform(window), src_crs=src_crs,
              dst_transform=window_transform, dst_crs=grid.crs,
              src_nodata=np.nan, dst_nodata=np.nan, resampling=resampling, num_threads=WARP_THREADS)
    target = mosaic[r0:r1, c0:c1]
    mosaic[r0:r1, c0:c1] = np.where(np.isnan(target), values, target)


def test_mosaics_as_before(tmp_path):
    """build_mosaic reads each window without its copies and places it in place: the same float32 bits
    as before for heights (on the grid, reprojected, finer, shifted, with nodata, integers, NaN, values
    below VALID_MIN); a categorical mosaic is uint8 with mosaic.NODATA where the float32 one had NaN."""
    import rasterio as rio
    from rasterio.transform import from_origin
    rng = np.random.default_rng(5)
    grid = gd.make_grid((500000, 300000, 500600, 300400), 2, "EPSG:2180")

    def tif(name, band, crs, left, top, res, nodata=None):
        path = str(tmp_path / f"{name}.tif")
        with rio.open(path, "w", driver="GTiff", width=band.shape[1], height=band.shape[0], count=1,
                      dtype=band.dtype, crs=crs, nodata=nodata, transform=from_origin(left, top, res, res)) as dst:
            dst.write(band, 1)
        return path

    heights = (200 + rng.normal(0, 30, (150, 160))).astype(np.float32)
    heights[10:20, 30:60] = -9999
    heights[40:44, :] = -700  # below VALID_MIN: no data
    on_grid = tif("on_grid", heights, "EPSG:2180", 500100, 300300, 2, nodata=-9999)
    ints = (rng.integers(150, 260, (90, 100))).astype(np.int16)
    ints[:5] = -32768
    from rasterio.warp import transform_bounds
    u_left, _, _, u_top = transform_bounds("EPSG:2180", "EPSG:32634", *grid.bounds)
    utm = tif("utm", ints, "EPSG:32634", round(u_left) - 52.5, round(u_top) - 30, 5, nodata=-32768)
    fine = (180 + rng.normal(0, 10, (400, 500))).astype(np.float32)
    fine[100:150, 100:120] = np.nan
    finer = tif("finer", fine, "EPSG:2180", 499950, 300420, 0.5, nodata=np.nan)
    plain = tif("plain", (rng.random((120, 120)) * 300).astype(np.float64), "EPSG:2180", 500350, 300250, 2)
    files = [on_grid, utm, finer, plain]
    for shift in ((0.0, 0.0), (3.0, -1.5)):
        new = src.build_mosaic(files, grid, str(tmp_path / "new.npy"), "test", shift=shift)
        old = np.full((grid.height, grid.width), np.nan, np.float32)
        for path in files:
            with rio.open(path) as f:
                _place_before(f, grid, old, shift=shift)
        assert new.dtype == np.float32 and np.isfinite(old).any() and np.isnan(old).any()
        assert np.array_equal(np.asarray(new).view(np.uint32), old.view(np.uint32))
        del new
    # The water body mask's categories in EPSG:4326, two overlapping tiles, part of the grid outside both
    west, south, east, north = transform_bounds("EPSG:2180", "EPSG:4326", *grid.bounds)
    step = 1 / 3600
    a = rng.integers(0, 4, (int((north - south) / step) + 8, int((east - west) / step / 2) + 4)).astype(np.uint8)
    b = rng.integers(0, 4, a.shape).astype(np.uint8)
    first = tif("wbm_a", a, "EPSG:4326", west - 2 * step, north + 2 * step, step)
    second = tif("wbm_b", b, "EPSG:4326", west + (east - west) * 0.3, north - (north - south) * 0.4, step)
    new = src.build_mosaic([first, second], grid, str(tmp_path / "wbm.npy"), "water mask", categorical=True)
    old = np.full((grid.height, grid.width), np.nan, np.float32)
    for path in (first, second):
        with rio.open(path) as f:
            _place_before(f, grid, old, categorical=True)
    assert new.dtype == np.uint8 and np.isnan(old).any() and {0, 1, 2, 3} <= set(np.unique(old[~np.isnan(old)]))
    assert np.array_equal(new, np.where(np.isnan(old), src.mosaic.NODATA, old).astype(np.uint8))
    del new


def _float_tiles(tmp_path):
    """Rasters of one band on a 2 m grid of EPSG:2180, float32 with NaN as nodata (GTiff as it comes, deflate in
    blocks, LERC as the cache writes it) and others (a nodata number, an internal mask, float64, no nodata), with
    NaN of other payloads, values below VALID_MIN and infinities."""
    import rasterio as rio
    from rasterio.transform import from_origin
    from sources.layer import _write_tile
    rng = np.random.default_rng(12)
    band = (300 + rng.normal(0, 40, (300, 260))).astype(np.float32)
    band[20:40, 10:90] = np.nan
    band.view(np.uint32)[50, :30] = 0xFFC00001  # NaN of other signs and payloads
    band.view(np.uint32)[51, :30] = 0x7F800001
    band[60:62] = -700  # below VALID_MIN: no data
    band[63, :5], band[63, 5:10] = -np.inf, np.inf
    transform = from_origin(500000, 300600, 2, 2)

    def tif(name, data, nodata, mask=None, **profile):
        path = str(tmp_path / f"{name}.tif")
        with rio.open(path, "w", driver="GTiff", width=data.shape[1], height=data.shape[0], count=1,
                      dtype=data.dtype, crs="EPSG:2180", nodata=nodata, transform=transform, **profile) as dst:
            dst.write(data, 1)
            if mask is not None:
                dst.write_mask(mask)
        return path

    lerc = str(tmp_path / "lerc.tif")
    _write_tile(lerc, band, "EPSG:2180", transform)
    mask = np.full(band.shape, 255, np.uint8)
    mask[100:120, 40:200] = 0  # masked, its values finite
    fast = {"nan": tif("nan", band, np.nan),
            "deflate": tif("deflate", band, np.nan, compress="deflate", predictor=3, tiled=True, blockxsize=64,
                           blockysize=64),
            "lerc": lerc}
    with np.errstate(invalid="ignore"):  # the signalling NaN cast to float64
        wide = band.astype(np.float64)
    other = {"number": tif("number", np.where(np.isnan(band), np.float32(-9999), band).astype(np.float32), -9999),
             "masked": tif("masked", band, np.nan, mask=mask),
             "float64": tif("float64", wide, np.nan),
             "none": tif("none", band, None)}
    return band, fast, other


def test_read_band_without_the_mask(tmp_path):
    """_read_band reads a float32 band whose nodata is NaN without GDAL's mask (a second decode of every block
    to find its NaN pixels): the bits of the masked read (every NaN np.nan, whatever its payload) and, with
    clean, of _clean after it; any other band (a nodata number, an internal mask, float64, no nodata) by the
    masked read as before."""
    import rasterio as rio
    from rasterio.windows import Window
    from sources.layer import _clean
    from sources.mosaic import _nan_nodata, _read_band
    _, fast, other = _float_tiles(tmp_path)
    windows = (Window(0, 0, 260, 300), Window(13, 7, 101, 95), Window(0, 250, 260, 50), Window(5, 48, 40, 20))
    for name, path in {**fast, **other}.items():
        with rio.open(path) as f:
            assert _nan_nodata(f) == (name in fast), name
            for window in windows:
                for clean in (False, True):
                    ref = f.read(1, window=window, masked=True).astype(np.float32).filled(np.nan)
                    if clean:
                        ref = _clean(ref)
                    got = _read_band(f, window, clean)
                    assert got.dtype == np.float32 and np.array_equal(_bits(got), _bits(ref)), (name, window, clean)
                    if window == windows[0]:
                        assert np.isnan(got).any() and np.isfinite(got).any()


def test_mosaic_of_float_tiles_as_before(tmp_path):
    """build_mosaic of float32 tiles with NaN as nodata, on the grid (disjoint ones read straight into the mosaic)
    and overlapping (a raster placed before wins), with others and a reprojected one first or later, whole and in
    strips: the bits of the reference (_place_before)."""
    import rasterio as rio
    from rasterio.transform import from_origin
    _, fast, other = _float_tiles(tmp_path)
    grid = gd.make_grid((499900, 300100, 500500, 300700), 2, "EPSG:2180")
    with rio.open(fast["deflate"]) as f:  # the same tile 50 px further east and south: overlapping
        profile, data = f.profile, f.read(1)
    profile["transform"] = from_origin(500100, 300500, 2, 2)
    moved = str(tmp_path / "moved.tif")
    with rio.open(moved, "w", **profile) as dst:
        dst.write(np.ascontiguousarray(data[::-1]), 1)
    with rio.open(fast["nan"]) as f:  # half a pixel off the grid: reprojected (bilinear)
        profile, data = f.profile, f.read(1)
    profile["transform"] = from_origin(499951, 300651, 2, 2)
    off = str(tmp_path / "off.tif")
    with rio.open(off, "w", **profile) as dst:
        dst.write(data, 1)
    halves = []  # the tile cut in two on the grid: disjoint, each read straight into the mosaic
    for name, rows, top in (("top", slice(0, 150), 300600), ("bottom", slice(150, 300), 300300)):
        profile.update(height=150, transform=from_origin(500000, top, 2, 2))
        halves.append(str(tmp_path / f"{name}.tif"))
        with rio.open(halves[-1], "w", **profile) as dst:
            dst.write(np.ascontiguousarray(data[rows]), 1)
    for files in ([fast["lerc"], moved, other["masked"]], [moved, fast["nan"], off, other["number"]],
                  [other["float64"], fast["deflate"]], halves + [moved], [off, fast["lerc"]], [other["none"], off]):
        old = np.full((grid.height, grid.width), np.nan, np.float32)
        for path in files:
            with rio.open(path) as f:
                _place_before(f, grid, old)
        assert np.isfinite(old).any() and np.isnan(old).any()
        for rows in (None, 7):
            new = src.build_mosaic(files, grid, str(tmp_path / "new.npy"), "test", rows=rows)
            assert np.array_equal(_bits(new), _bits(old)), (files, rows)
            del new


def test_mosaic_reads_sidecars(tmp_path):
    """build_mosaic opens its files without a listing of their folder (GDAL_DISABLE_READDIR_ON_OPEN): GDAL
    still finds a file's sidecar by its name, here an .aux.xml giving its nodata."""
    import rasterio as rio
    from rasterio.transform import from_origin
    grid = gd.make_grid((500000, 300000, 500200, 300200), 2, "EPSG:2180")
    band = np.full((100, 100), 250.0, np.float32)
    band[:30] = 123.0
    path = str(tmp_path / "tile.tif")
    with rio.open(path, "w", driver="GTiff", width=100, height=100, count=1, dtype="float32", crs="EPSG:2180",
                  transform=from_origin(500000, 300200, 2, 2)) as dst:
        dst.write(band, 1)
    with open(path + ".aux.xml", "w", encoding="utf-8") as f:
        f.write('<PAMDataset><PAMRasterBand band="1"><NoDataValue>123</NoDataValue></PAMRasterBand></PAMDataset>')
    for name in ("a.tif", "b.tif", "c.npy"):  # a folder of other files too
        (tmp_path / name).write_bytes(b"")
    with rio.open(path) as f:
        assert f.nodata == 123.0
    mosaic = np.array(src.build_mosaic([path], grid, str(tmp_path / "m.npy"), "test"))
    assert np.isnan(mosaic[:30]).all() and (mosaic[30:] == 250.0).all()


# Step 1 in strips of rows (the area of a tiled search, search.search_lines: prepare_data(strips=True)):
# each function with `rows` gives the whole-grid function's values, for any strip height

def _memmap(tmp_path, name, array):
    out = np.lib.format.open_memmap(str(tmp_path / name), mode="w+", dtype=array.dtype, shape=array.shape)
    out[:] = array
    out.flush()
    return out


def _bits(a):
    return np.asarray(a).view(np.uint32)


def test_near_rows_as_near():
    """near_rows gives near() of the whole grid for any strip height (a halo of n rows), also at the
    grid's edges, for empty and full masks and n of 0 (a copy)."""
    rng = np.random.default_rng(11)
    for shape in ((1, 7), (37, 53), (64, 20)):
        masks = [np.zeros(shape, bool), np.ones(shape, bool), rng.random(shape) < 0.05, rng.random(shape) < 0.4]
        for mask in masks:
            for metres, res in ((0, 1.0), (1, 1.0), (2.5, 1.0), (45, 2.0), (9.0, 0.3), (100, 1.0)):
                expected = src.near(mask, metres, res)
                for rows in (1, 3, 16, shape[0], shape[0] + 5):
                    out = np.zeros(shape, bool)
                    got = src.filling.near_rows(lambda r0, r1: mask[r0:r1], metres, res, out, rows)
                    assert got is out and np.array_equal(got, expected), (shape, metres, res, rows)


def test_median_of_rows_is_np_median(monkeypatch):
    """The overall offset of _fill in strips (filling._median_of: a selection on the float32 bit
    patterns, read chunk by chunk) is np.median of the values held whole: odd and even counts,
    ties, negative values, -0.0, the extremes, and the histogram refined over several rounds."""
    rng = np.random.default_rng(5)
    cases = [rng.normal(0, 3, n).astype(np.float32) for n in (1, 2, 3, 4, 1000, 100001)]
    cases.append(np.round(rng.normal(0, 3, 5000), 1).astype(np.float32))  # many ties
    cases.append(np.full(70001, 2.5, np.float32))
    cases.append(np.array([-0.0, 0.0, 0.0, -0.0], np.float32))
    cases.append(np.array([3.0, -1e-40, 1e38, -1e38, 7.0, -7.5], np.float32))
    cases.append(rng.choice(np.array([-2.0, -1.0, 0.0, 1.0, 2.0], np.float32), 300000))
    for small in (False, True):
        if small:  # bins of a few keys and a few values collected: the range narrows round by round
            monkeypatch.setattr(src.filling, "SELECT_BINS", 4)
            monkeypatch.setattr(src.filling, "SELECT_COLLECT", 50)
        for values in cases:
            for chunk in (1, 7, 1000, len(values)):
                parts = [values[i:i + chunk] for i in range(0, len(values), chunk)]
                keys = src.filling._KeyRange()
                for part in parts:
                    keys.add(part)
                assert keys.n == len(values)
                got = src.filling._median_of(lambda: iter(parts), keys)
                assert got == float(np.median(values)), (len(values), chunk, small)
    keys = src.filling._keys(np.array([-np.inf, -1e38, -2.0, -0.0, 0.0, 1e-45, 2.0, np.inf], np.float32))
    assert np.all(np.diff(keys) > 0)  # the keys follow the values
    assert all(src.filling._key_value(int(k)) == v or (np.isnan(v))
               for k, v in zip(keys, [-np.inf, -1e38, -2.0, -0.0, 0.0, 1e-45, 2.0, np.inf]))


def _select_before(chunks, k, lo, hi):
    """filling._select of main d466347 (one value a call): the reference of the pairs."""
    f = src.filling
    while lo < hi:
        width = -(-(hi - lo + 1) // f.SELECT_BINS)
        counts = np.zeros(f.SELECT_BINS, np.int64)
        for values in chunks():
            keys = f._keys(values)
            keys = keys[(keys >= lo) & (keys <= hi)]
            counts += np.bincount((keys - lo) // width, minlength=f.SELECT_BINS)
        cum = np.cumsum(counts)
        b = int(np.searchsorted(cum, k, side="right"))
        k -= int(cum[b - 1]) if b else 0
        lo, hi = lo + b * width, min(hi, lo + (b + 1) * width - 1)
        if counts[b] <= f.SELECT_COLLECT:
            found = []
            for values in chunks():
                keys = f._keys(values)
                found.append(np.asarray(values, dtype=np.float32)[(keys >= lo) & (keys <= hi)])
            return np.sort(np.concatenate(found))[k]
    return f._key_value(lo)


def test_select_pair_as_two_selections(monkeypatch):
    """_select(pair=True), the two middle values of an even count in the same passes, gives the float32
    bits of two selections of before (_select_before), and _median_of the bits of before: ties across
    and within bins, -0.0 and 0.0 as the two middle values, two clusters far apart (the (k+1)-th in a
    later bin, also of single keys), at the default bins and at bins of a few keys over several rounds."""
    rng = np.random.default_rng(9)
    cases = [rng.normal(0, 3, n).astype(np.float32) for n in (2, 4, 1000, 100000)]
    cases.append(np.round(rng.normal(0, 3, 5000), 1).astype(np.float32))
    cases.append(np.array([-0.0, 0.0, 0.0, -0.0], np.float32))
    cases.append(np.array([0.0, -0.0], np.float32))
    cases.append(np.array([3.0, -1e-40, 1e38, -1e38, 7.0, -7.5], np.float32))
    cases.append(np.concatenate([np.full(3000, -1e38, np.float32), np.full(3000, 1e38, np.float32)]))
    cases.append(np.concatenate([np.full(300, 1.5, np.float32), np.full(300, np.nextafter(np.float32(1.5), 2))]))
    cases.append(rng.choice(np.array([-2.0, -1.0, 0.0, 1.0, 2.0], np.float32), 300000))
    bits = lambda v: np.float32(v).view(np.uint32)  # noqa: E731
    for small in (False, True):
        if small:
            monkeypatch.setattr(src.filling, "SELECT_BINS", 4)
            monkeypatch.setattr(src.filling, "SELECT_COLLECT", 50)
        for values in cases:
            for chunk in (1, 7, len(values)):
                parts = [values[i:i + chunk] for i in range(0, len(values), chunk)]
                keys = src.filling._KeyRange()
                for part in parts:
                    keys.add(part)
                chunks = lambda: iter(parts)  # noqa: E731
                for k in sorted({0, (len(values) - 2) // 2, len(values) - 2}):
                    pair = src.filling._select(chunks, k, keys.lo, keys.hi, pair=True)
                    before = (_select_before(chunks, k, keys.lo, keys.hi), _select_before(chunks, k + 1, keys.lo, keys.hi))
                    assert [bits(v) for v in pair] == [bits(v) for v in before], (len(values), chunk, small, k)
                k0 = (len(values) - 1) // 2
                v0, v1 = _select_before(chunks, k0, keys.lo, keys.hi), _select_before(chunks, len(values) // 2, keys.lo, keys.hi)
                median = float(np.median(np.array([v0, v1], np.float32))) if len(values) % 2 == 0 else float(v0)
                assert bits(src.filling._median_of(chunks, keys)) == bits(median), (len(values), chunk, small)


def test_keys32_as_keys_before():
    """The keys of the selection in int32 (filling._keys32, and _keys from it) are those of before,
    -(bits & 0x7FFFFFFF) - 1 for a negative float32 and its bits otherwise, on every sign and exponent:
    random bit patterns, the extremes of int32, the zeros, the infinities and the NaNs."""
    rng = np.random.default_rng(11)
    patterns = np.concatenate([rng.integers(-2 ** 31, 2 ** 31, 1_000_000, dtype=np.int64).astype(np.int32),
                               np.array([-2 ** 31, -2 ** 31 + 1, -1, 0, 1, 2 ** 31 - 1], np.int32)])
    values = np.concatenate([patterns.view(np.float32),
                             np.array([-0.0, 0.0, np.inf, -np.inf, np.nan, 1e-45, -1e-45], np.float32)])
    bits = values.view(np.int32).astype(np.int64)
    before = np.where(bits < 0, -(bits & 0x7FFFFFFF) - 1, bits)
    assert src.filling._keys32(values).dtype == np.int32
    assert np.array_equal(src.filling._keys32(values).astype(np.int64), before)
    assert np.array_equal(src.filling._keys(values), before) and src.filling._keys(values).dtype == np.int64


def _gap_fill_case(seed):
    """A terrain with gaps and a filling source (test_gap_fill_as_before's)."""
    from scipy import ndimage
    rng = np.random.default_rng(seed)
    shape = (157, 211)
    y, x = np.mgrid[:shape[0], :shape[1]]
    terrain = (300 + 40 * np.sin(x / 17) * np.cos(y / 23) + 25 * (x > 120) + rng.normal(0, 0.3, shape))
    terrain = terrain.astype(np.float32)
    terrain[60:66, :] += np.linspace(0, 90, shape[1], dtype=np.float32)  # a cliff band: steep pixels
    gaps = ndimage.binary_dilation(rng.random(shape) < 0.002, iterations=4) | (rng.random(shape) < 0.01)
    gaps[:5, :9] = True  # a gap at the corner
    other = (terrain + 1.7 + rng.normal(0, 0.4, shape)).astype(np.float32)
    other[rng.random(shape) < 0.03] = np.nan  # the filling source has gaps too
    other[100:110, 150:170] += 20  # a misaligned patch: a local offset far from the overall one
    if seed == 2:
        other[:] = np.nan  # nothing to fill with
    if seed == 4:  # a tile at a border: the land beyond it a gap, its edge irregular, small gaps beside it
        gaps |= x > 150 + 12 * np.sin(y / 9)
    return terrain, gaps, other


@pytest.mark.parametrize("seed", [0, 1, 2, 3, 4])
def test_fill_rows_as_before(seed, tmp_path):
    """_fill in strips of rows fills every gap with the float32 bits of _fill on the whole grid
    (test_gap_fill_as_before's reference): any strip height, also the filling source known on a
    window of the grid only (a neighbour's, NaN outside), the same count; its temporary mask gone."""
    terrain, gaps, other = _gap_fill_case(seed)
    shape = terrain.shape
    whole = _memmap(tmp_path, "whole.npy", np.where(gaps, np.nan, terrain).astype(np.float32))
    expected = _fill_before(whole, other, gaps, 1.0)
    gaps_mm = _memmap(tmp_path, "gaps.npy", gaps)
    other_mm = _memmap(tmp_path, "other.npy", other)
    for rows in (1, 5, 40, shape[0], 500):
        grid = _memmap(tmp_path, f"rows{rows}.npy", np.where(gaps, np.nan, terrain).astype(np.float32))
        count = src.filling._fill(grid, other_mm, gaps_mm, 1.0, "test", rows=rows, work=str(tmp_path))
        assert count == expected and np.array_equal(_bits(grid), _bits(whole)), rows
        assert not os.path.exists(tmp_path / "both.npy")
    window = (slice(20, 120), slice(30, 190))
    other_w = np.full(shape, np.nan, np.float32)
    other_w[window] = other[window]
    whole_w = _memmap(tmp_path, "whole_w.npy", np.where(gaps, np.nan, terrain).astype(np.float32))
    expected = _fill_before(whole_w, other_w, gaps, 1.0)
    sub = _memmap(tmp_path, "sub.npy", np.ascontiguousarray(other[window]))
    for rows in (7, 64):
        grid = _memmap(tmp_path, f"window{rows}.npy", np.where(gaps, np.nan, terrain).astype(np.float32))
        count = src.filling._fill(grid, sub, gaps_mm, 1.0, "test", rows=rows, window=window, work=str(tmp_path))
        assert count == expected and np.array_equal(_bits(grid), _bits(whole_w)), rows


def test_fill_water_rows_as_before(tmp_path):
    """fill_water in strips of rows: the same terrain and surface bits, the same water mask, for any
    strip height (lakes crossing strips, a lake measured, the sea given by the data, a provider's
    constant), and the bare mask of the pixels filled."""
    from grid import Grid
    rng = np.random.default_rng(3)
    H, W = 90, 160  # 2 m pixels: the lakes' shore buffer (SHORE_BUFFER) reaches 23 px
    z = (rng.random((H, W)) * 30 + 2).astype(np.float32)
    z[:, :12] = np.nan  # the sea without data
    z[:, 12:15] = rng.choice([0.2, 0.9, 1.1, 1.3, 4.0], (H, 3)).astype(np.float32)  # the shore
    z[5:12, 30:40] = np.nan  # lakes without data (the second crosses the strips)
    z[40:70, 20:25] = np.nan
    z[80:88, 50:60] = np.nan
    z[60:62, 120:122] = np.nan  # a gap on land, away from any lake: stays without data
    z[2:4, 20:22] = np.nan  # no data at the edge of a lake's shore buffer
    wbm = np.zeros((H, W), np.uint8)
    wbm[:, :13] = src.OCEAN
    for r, c in ((slice(4, 13), slice(29, 41)), (slice(39, 71), slice(19, 26)), (slice(79, 89), slice(49, 61)),
                 (slice(20, 24), slice(50, 55))):  # the last a lake the data measured
        wbm[r, c] = src.LAKE
    sea_zone = np.zeros((H, W), bool)
    sea_zone[:, :18] = True
    surface = (z + 2).astype(np.float32)
    surface[:, :12] = np.nan
    surface[50:55, 22:24] = np.nan
    surface[30:33, 100:102] = np.nan  # the surface alone without data: stays so
    grid = Grid(500000.0, 300000.0, 2.0, H, W, "EPSG:2180")
    wbm_mm, zone_mm = _memmap(tmp_path, "wbm.npy", wbm), _memmap(tmp_path, "zone.npy", sea_zone)
    for sea_value in (None, 1.3):
        np.save(str(tmp_path / "nmt_w.npy"), z)
        np.save(str(tmp_path / "nmpt_w.npy"), surface)
        water_w = np.load(src.fill_water(str(tmp_path / "nmt_w.npy"), str(tmp_path / "nmpt_w.npy"), grid, wbm,
                                         sea_zone, str(tmp_path / "water_w.npy"), sea_value=sea_value))
        filled_w = np.load(str(tmp_path / "nmt_w.npy"))
        assert water_w[:, :12].all() and water_w[40:70, 20:25].all() and water_w[20:24, 50:55].all()
        assert np.isnan(filled_w).sum() == 4 and np.isnan(np.load(str(tmp_path / "nmpt_w.npy"))).sum() == 4 + 6
        for rows in (1, 5, 13, H, 200):
            nmt, nmpt = _memmap(tmp_path, "nmt_s.npy", z), _memmap(tmp_path, "nmpt_s.npy", surface)
            del nmt, nmpt
            water_s = np.load(src.fill_water(str(tmp_path / "nmt_s.npy"), str(tmp_path / "nmpt_s.npy"), grid, wbm_mm,
                                             zone_mm, str(tmp_path / "water_s.npy"), sea_value=sea_value, rows=rows,
                                             bare_path=str(tmp_path / "bare.npy")))
            assert np.array_equal(water_s, water_w), (sea_value, rows)
            for name in ("nmt", "nmpt"):
                assert np.array_equal(_bits(np.load(str(tmp_path / f"{name}_s.npy"))),
                                      _bits(np.load(str(tmp_path / f"{name}_w.npy")))), (name, sea_value, rows)
            bare = np.load(str(tmp_path / "bare.npy"))
            assert np.array_equal(bare, water_s & np.isnan(z)) and bare.any()
            assert not os.path.exists(tmp_path / "lake.npy")


def test_fill_water_rows_dry_strips(tmp_path, monkeypatch):
    """fill_water in strips leaves out the dry strips (no sea zone in them, no lake within SHORE_BUFFER of
    them) and gives the whole grid's values: the sea in the top rows only, a lake measured and one without
    data in the middle, gaps on land in every row (they stay without data), and a grid with no water at all,
    whose water and bare masks stay all False and whose elevation is never read for the water with data."""
    from grid import Grid
    rng = np.random.default_rng(5)
    H, W = 120, 70  # 2 m pixels: the lakes' shore buffer reaches 23 px
    z = (rng.random((H, W)) * 30 + 2).astype(np.float32)
    z[::9, 40:43] = np.nan  # gaps on land in every few rows
    z[:6, :] = np.nan  # the sea without data in the top rows
    z[6, :20] = 0.4  # the sea given by the data
    z[60:66, 10:20] = np.nan  # a lake without data
    wbm = np.zeros((H, W), np.uint8)
    wbm[:7, :] = src.OCEAN
    wbm[58:68, 8:22] = src.LAKE
    wbm[80:84, 50:60] = src.LAKE  # measured
    sea_zone = np.zeros((H, W), bool)
    sea_zone[:12, :] = True
    surface = (z + 2).astype(np.float32)
    grid = Grid(500000.0, 300000.0, 2.0, H, W, "EPSG:2180")
    calls = []
    original = src.filling.water_with_data
    monkeypatch.setattr(src.filling, "water_with_data", lambda z, *a, **k: calls.append(len(z)) or original(z, *a, **k))
    for name, (w, zone) in {"wet": (wbm, sea_zone), "dry": (np.zeros_like(wbm), np.zeros_like(sea_zone))}.items():
        np.save(str(tmp_path / "nmt_w.npy"), z)
        np.save(str(tmp_path / "nmpt_w.npy"), surface)
        water_w = np.load(src.fill_water(str(tmp_path / "nmt_w.npy"), str(tmp_path / "nmpt_w.npy"), grid, w, zone,
                                         str(tmp_path / "water_w.npy")))
        assert water_w.any() == (name == "wet")
        w_mm, zone_mm = _memmap(tmp_path, f"wbm_{name}.npy", w), _memmap(tmp_path, f"zone_{name}.npy", zone)
        for rows in (1, 7, 16, 50, H):
            nmt, nmpt = _memmap(tmp_path, "nmt_s.npy", z), _memmap(tmp_path, "nmpt_s.npy", surface)
            del nmt, nmpt
            calls.clear()
            water_s = np.load(src.fill_water(str(tmp_path / "nmt_s.npy"), str(tmp_path / "nmpt_s.npy"), grid, w_mm,
                                             zone_mm, str(tmp_path / "water_s.npy"), rows=rows,
                                             bare_path=str(tmp_path / "bare.npy")))
            assert np.array_equal(water_s, water_w), (name, rows)
            for f in ("nmt", "nmpt"):
                assert np.array_equal(_bits(np.load(str(tmp_path / f"{f}_s.npy"))),
                                      _bits(np.load(str(tmp_path / f"{f}_w.npy")))), (name, f, rows)
            assert np.array_equal(np.load(str(tmp_path / "bare.npy")), water_s & np.isnan(z)), (name, rows)
            if name == "dry":
                assert not calls and not water_s.any()  # every strip dry: the water with data never computed
            elif rows <= 16:  # the strips more than SHORE_BUFFER from the lakes and below the sea zone are left out
                assert 0 < sum(calls) < H, (rows, calls)
        del w_mm, zone_mm


def test_border_gaps_rows_as_whole(tmp_path):
    """border_gaps in strips of rows marks the gaps of the whole grid (the footprint and its edge
    strip by strip), for a circle's footprint and an area's outline, and neighbour_window finds
    the same window from them in strips."""
    from types import SimpleNamespace
    from grid import Grid
    from shapely.geometry import Polygon
    rng = np.random.default_rng(9)
    H, W = 120, 100
    z = (rng.random((H, W)) * 10 + 100).astype(np.float32)
    z[:, :20] = np.nan  # a gap reaching the west edge, large
    z[50:53, -2:] = np.nan  # a sliver at the east edge: too small
    z[20:40, 40:60] = np.nan  # a hole inside the data: no border
    z[-30:, 30:70] = np.nan  # reaching the south edge
    z[:6, :] = np.nan  # the north edge: outside a circle's footprint mostly
    s = z.copy()
    s[60:80, 85:] = np.nan  # the surface alone without data at the east edge
    exclude = np.zeros((H, W), bool)
    exclude[-14:, 30:50] = True  # a sea zone over part of the southern gap
    np.save(str(tmp_path / "nmt.npy"), z)
    np.save(str(tmp_path / "nmpt.npy"), s)
    circle = Grid(500000.0, 300000.0, 2.0, H, W, "EPSG:2180")
    outline = Grid(500000.0, 300000.0, 2.0, H, W, "EPSG:2180")
    outline.area_shape = Polygon([(500010, 299790), (500190, 299800), (500180, 299990), (500030, 299960)])
    neighbour = SimpleNamespace(rough_boxes=lambda: [(0.0, 90.0, 0.0, 180.0)])  # boxes: the world's east
    anywhere = SimpleNamespace(rough_boxes=lambda: [])
    exclude_mm = _memmap(tmp_path, "exclude.npy", exclude)
    for grid in (circle, outline):
        for surface in (None, str(tmp_path / "nmpt.npy")):
            for excluded in (None, exclude):
                whole = src.filling.border_gaps(str(tmp_path / "nmt.npy"), surface, grid, excluded)
                assert whole.any() and not whole[20:40, 40:60].any() and not whole[50:53, -2:].any()
                for rows in (1, 7, 50, H):
                    out = _memmap(tmp_path, "border.npy", np.zeros((H, W), bool))
                    got = src.filling.border_gaps(str(tmp_path / "nmt.npy"), surface, grid,
                                                  None if excluded is None else exclude_mm, rows=rows, out=out)
                    assert got is out and np.array_equal(np.asarray(got), whole), (rows, surface, excluded)
                    assert not os.path.exists(tmp_path / "edge.npy")
                    for source in (neighbour, anywhere):
                        expected = src.filling.neighbour_window(source, grid, whole)
                        assert src.filling.neighbour_window(source, grid, got, rows=rows) == expected
                    del got, out
    # no gaps at all: an empty mask either way
    np.save(str(tmp_path / "full.npy"), np.ones((H, W), np.float32))
    out = _memmap(tmp_path, "border2.npy", np.zeros((H, W), bool))
    assert not src.filling.border_gaps(str(tmp_path / "full.npy"), None, circle, None, rows=10, out=out).any()
    assert src.filling.neighbour_window(neighbour, circle, out, rows=10) is None


def test_rasterize_into_as_whole(tmp_path):
    """sources.filling.rasterize_into burns into a memory-mapped mask the pixels of coast._rasterize
    (polygons, holes, none, empty), of area.Polygon.mask and, all touched, of the footprint
    border_gaps took from geometry_mask; _sea_from_coastline_rows keeps the faces of
    _sea_from_coastline (the Copernicus mask's share of each face counted strip by strip)."""
    import coast
    from grid import Grid
    from rasterio.features import geometry_mask
    from shapely.geometry import LineString, Point, Polygon
    rng = np.random.default_rng(2)
    H, W = 131, 97
    grid = Grid(500000.0, 300000.0, 2.0, H, W, "EPSG:2180")
    left, top = grid.left, grid.top
    polygons = []
    for _ in range(9):
        cx, cy = left + rng.random() * W * 2, top - rng.random() * H * 2
        hull = Polygon([(cx + rng.normal(0, 50), cy + rng.normal(0, 50)) for _ in range(6)]).convex_hull
        polygons.append(Point(cx, cy).buffer(rng.random() * 80, 4).union(hull))
    ring = Point(left + 100, top - 150).buffer(60).difference(Point(left + 100, top - 150).buffer(20))
    circle = Point(left + W, top - H).buffer(min(W, H))
    cases = [polygons, polygons[:1], [ring], [circle], [Polygon()], []]
    for geometries in cases:
        expected = coast._rasterize(geometries, grid)
        out = src.filling.new_mask(str(tmp_path / "mask.npy"), (H, W))
        got = src.filling.rasterize_into(geometries, grid, out)
        assert got is out and np.array_equal(np.asarray(got), expected), len(geometries)
        touched = geometry_mask(geometries, (H, W), grid.transform, invert=True, all_touched=True) \
            if any(not g.is_empty for g in geometries) else np.zeros((H, W), bool)
        out = src.filling.new_mask(str(tmp_path / "touched.npy"), (H, W))
        assert np.array_equal(np.asarray(src.filling.rasterize_into(geometries, grid, out, all_touched=True)), touched)
        del out, got
    lines = [LineString([(left - 10, top - 100 - 40 * k), (left + W * 2 + 10, top - 60 - 50 * k)]) for k in range(3)]
    lines.append(LineString([(left + 80, top + 10), (left + 90, top - 120), (left + 60, top - H * 2 - 10)]))
    copernicus = rng.random((H, W)) < 0.3
    copernicus[:50] = rng.random((50, W)) < 0.8  # the north is sea, with noise
    expected = coast._sea_from_coastline(lines, grid, copernicus)
    assert expected.any() and not expected.all()
    for rows in (1, 9, H):
        out = src.filling.new_mask(str(tmp_path / "sea.npy"), (H, W))
        out[:] = True
        got = coast._sea_from_coastline_rows(lines, grid, lambda r0, r1: copernicus[r0:r1], out, rows)
        assert got is out and np.array_equal(np.asarray(got), expected), rows
        del out, got


def test_mosaic_resampling_methods(tmp_path):
    """build_mosaic(resampling=): the method of the reprojected rasters of heights instead of the
    mosaic's own choice (bilinear for data of the grid's resolution or coarser, the average of finer
    data); a raster on the grid is copied whatever it says; not for a categorical mosaic."""
    import rasterio as rio
    from rasterio.transform import from_origin
    rng = np.random.default_rng(11)
    grid = gd.make_grid((500000, 300000, 500400, 300300), 2, "EPSG:2180")

    def mosaic(name, band, left, top, res, method, **kwargs):
        path = str(tmp_path / f"{name}.tif")
        with rio.open(path, "w", driver="GTiff", width=band.shape[1], height=band.shape[0], count=1,
                      dtype=band.dtype, crs="EPSG:2180", transform=from_origin(left, top, res, res)) as dst:
            dst.write(band, 1)
        return np.array(src.build_mosaic([path], grid, str(tmp_path / "m.npy"), "test", resampling=method, **kwargs))

    coarse = (200 + rng.normal(0, 30, (70, 90))).astype(np.float32)
    fine = (200 + rng.normal(0, 30, (700, 900))).astype(np.float32)
    on_grid = (200 + rng.normal(0, 30, (150, 200))).astype(np.float32)
    got = {m: mosaic("coarse", coarse, 499987, 300321, 5, m) for m in (None, "bilinear", "nearest", "cubic", "average")}
    assert np.array_equal(got[None], got["bilinear"], equal_nan=True) and np.isfinite(got[None]).all()
    assert np.isin(got["nearest"], coarse).all() and np.isin(got["bilinear"], coarse).mean() < 0.01
    assert not np.array_equal(got["cubic"], got["bilinear"])
    got = {m: mosaic("fine", fine, 499979.75, 300320.25, 0.5, m) for m in (None, "bilinear", "nearest", "average")}
    assert np.array_equal(got[None], got["average"], equal_nan=True) and np.isfinite(got[None]).all()
    assert np.isin(got["nearest"], fine).all() and not np.array_equal(got["bilinear"], got["average"])
    # GDAL widens the bilinear kernel to the grid's pixel for finer data: smoother than the blocks' means,
    # which are smoother than single pixels of the fine data
    assert got["bilinear"].std() < got["average"].std() < 0.5 * got["nearest"].std()
    for method in (None, "nearest", "cubic"):
        assert np.array_equal(mosaic("on_grid", on_grid, 500000, 300300, 2, method), on_grid)
    # same_resolution: a method for the rasters at about the grid's resolution only (a neighbour's data,
    # half a pixel off the grid here); finer rasters stay averaged, coarser ones bilinear, a method for all wins
    same = (200 + rng.normal(0, 30, (170, 220))).astype(np.float32)
    off = {m: mosaic("same", same, 499979, 300321, 2, None, same_resolution=m) for m in (None, "nearest")}
    assert np.array_equal(off[None], mosaic("same", same, 499979, 300321, 2, "bilinear"))
    assert np.isin(off["nearest"], same).all() and np.isin(off[None], same).mean() < 0.01
    assert np.array_equal(mosaic("same", same, 499979, 300321, 2, "cubic", same_resolution="nearest"),
                          mosaic("same", same, 499979, 300321, 2, "cubic"))
    assert np.array_equal(mosaic("coarse", coarse, 499987, 300321, 5, None, same_resolution="nearest"),
                          mosaic("coarse", coarse, 499987, 300321, 5, "bilinear"))
    # ... also a little coarser (2.5 m data on the 2 m grid, measured: nearest makes walls of their steps)
    wider = (200 + rng.normal(0, 30, (140, 180))).astype(np.float32)
    assert src.mosaic.FINER < 1.0 < src.mosaic.SAME < 1.25
    assert np.array_equal(mosaic("wider", wider, 499979, 300321, 2.5, None, same_resolution="nearest"),
                          mosaic("wider", wider, 499979, 300321, 2.5, "bilinear"))
    assert np.array_equal(mosaic("fine", fine, 499979.75, 300320.25, 0.5, None, same_resolution="nearest"),
                          got["average"])
    assert np.array_equal(mosaic("on_grid", on_grid, 500000, 300300, 2, None, same_resolution="nearest"), on_grid)
    with pytest.raises(ValueError, match="resampling"):
        mosaic("same", same, 499979, 300321, 2, None, same_resolution="lanczos")
    with pytest.raises(ValueError, match="resampling"):
        mosaic("coarse", coarse, 499987, 300321, 5, "lanczos")
    with pytest.raises(ValueError, match="resampling"):
        mosaic("coarse", coarse.astype(np.uint8), 499987, 300321, 5, "nearest", categorical=True)


def test_mosaic_rows_as_whole(tmp_path):
    """build_mosaic in strips of rows: a raster on the grid (copied) and rasters of the grid's CRS
    resampled (bilinear from a coarser one, averaged from a finer one: an exact transformation)
    give the bits of the whole mosaic; a raster of another CRS (bilinear, and a categorical one
    by the nearest pixel) the same pixels within GDAL's approximate transformer, whose
    interpolation depends on the destination (a tile's extent today), so cross-CRS mosaics of an
    area may differ a little from one grid's."""
    import rasterio as rio
    from rasterio.transform import from_origin
    from rasterio.warp import transform_bounds
    rng = np.random.default_rng(6)
    grid = gd.make_grid((500000, 300000, 500600, 300400), 2, "EPSG:2180")

    def tif(name, band, crs, left, top, res, nodata=None):
        path = str(tmp_path / f"{name}.tif")
        with rio.open(path, "w", driver="GTiff", width=band.shape[1], height=band.shape[0], count=1,
                      dtype=band.dtype, crs=crs, nodata=nodata, transform=from_origin(left, top, res, res)) as dst:
            dst.write(band, 1)
        return path

    heights = (200 + rng.normal(0, 30, (150, 160))).astype(np.float32)
    heights[10:20, 30:60] = -9999
    on_grid = tif("on_grid", heights, "EPSG:2180", 500100, 300300, 2, nodata=-9999)
    coarse = (rng.normal(0, 30, (90, 130))).astype(np.float32)
    coarser = tif("coarser", coarse, "EPSG:2180", 499951, 300441, 5, nodata=np.nan)
    fine = (180 + rng.normal(0, 10, (400, 500))).astype(np.float32)
    fine[100:150, 100:120] = np.nan
    finer = tif("finer", fine, "EPSG:2180", 499950, 300420, 0.5, nodata=np.nan)
    u_left, _, _, u_top = transform_bounds("EPSG:2180", "EPSG:32634", *grid.bounds)
    y, x = np.mgrid[:90, :100]
    smooth = (200 + 30 * np.sin(x / 9) * np.cos(y / 11)).astype(np.float32)  # a slope of at most 3.4 m a pixel
    utm = tif("utm", smooth, "EPSG:32634", round(u_left) - 52.5, round(u_top) - 30, 5, nodata=np.nan)
    west, south, east, north = transform_bounds("EPSG:2180", "EPSG:4326", *grid.bounds)
    step = 1 / 3600
    categories = rng.integers(0, 4, (int((north - south) / step) + 8, int((east - west) / step) + 8)).astype(np.uint8)
    wbm = tif("wbm", categories, "EPSG:4326", west - 2 * step, north + 2 * step, step)
    cases = (("same crs", [on_grid, coarser, finer], False, 0.0), ("other crs", [utm], False, 3.4 * 0.125),
             ("wbm", [wbm], True, None))
    for name, files, categorical, within in cases:
        whole = np.array(src.build_mosaic(files, grid, str(tmp_path / "whole.npy"), "test", categorical=categorical))
        assert (whole != src.mosaic.NODATA).any() if categorical else np.isfinite(whole).any()
        for rows in (1, 7, 60, grid.height, 1000):
            got = np.array(src.build_mosaic(files, grid, str(tmp_path / "rows.npy"), "test", categorical=categorical,
                                            rows=rows))
            if categorical:
                assert np.mean(got != whole) < 0.01, (name, rows)
            elif within:
                assert np.array_equal(np.isnan(got), np.isnan(whole)) and np.nanmax(np.abs(got - whole)) <= within, \
                    (name, rows)
            else:
                assert np.array_equal(_bits(got), _bits(whole)), (name, rows)


def _fake_lines(n):
    import helpers as sh
    return sh.LineTable.from_rows([
        {"a1": (k, 0), "a2": (k, 1), "anchor1": (50 + k / 1e4, 19.1234567), "anchor2": (50.0001, 19 + k / 1e4),
         "a1_xy": (k * 0.5, 1.0), "a2_xy": (2.0, k / 3), "length": 100 + k / 7, "clearance": k / 3,
         "clearance_nmpt": None if k % 2 else k / 9, "over_obstacles": bool(k % 3), "elev_a1": 400 + k / 11,
         "elev_a2": 410.0, "water_m": 0.0, "filled_m": k / 13, "height_max": 30 + k / 17, "height_mean": 20 + k / 19,
         "high_pct": k / 0.23, "angle1": k * 7.3, "angle2": 90 - k / 3, "prom1": np.nan if k % 4 else k / 1.7,
         "prom2": 4.0, "drop1": k * 2.1, "drop2": 30.0,
         "profile": {"d": [0, k], "z": [1.5, None]} if k in (0, 4) else None}
        for k in range(n)])


def test_chunked_writes_match_one_dump(tmp_path, monkeypatch):
    """Results, the map data and tile files written in chunks: the same text, the same lines."""
    import json
    from shapely.geometry import Point
    import helpers as sh
    import mapping as mp
    import runs as rn
    import search

    class Area:
        center = (50.0, 19.1)

        @staticmethod
        def shape_wgs84():
            return Point(19.1, 50.0).buffer(0.01)

    lines = _fake_lines(10)
    groups = mp.Groups(np.array([4, 0]), np.array([4, 5, 6, 7, 8, 9, 3, 0, 1, 2]), np.array([0, 6, 10]))
    meta = {"name": "Żabi Koń", "summary": {"lines": 10}}
    run = {"id": "r", "name": "Żabi Koń", "created": "2026-10-31T10:00:00+00:00"}
    for chunk, folder in ((3, tmp_path / "small"), (10_000, tmp_path / "one")):
        monkeypatch.setattr(rn, "LINES_CHUNK", chunk)
        monkeypatch.setattr(mp, "LINES_CHUNK", chunk)
        folder.mkdir()
        counts = []
        rn.save_results(str(folder), lines, groups, meta, lambda n, file: counts.append(n))
        assert sum(counts) == len(lines)
        counts = []
        mp.save_map(lines, Area, str(folder), str(tmp_path / "runs"), run, "EPSG:2180",
                    on_lines=lambda n, file: counts.append(n))
        assert sum(counts) == len(lines)
    for name in ("lines.csv", "lines.geojson", "run.json", "data.js", "lines.js"):
        assert (tmp_path / "small" / name).read_bytes() == (tmp_path / "one" / name).read_bytes()
    text = (tmp_path / "small" / "lines.geojson").read_text(encoding="utf-8")
    assert text == json.dumps(json.loads(text), ensure_ascii=False)
    # Group by group, each representative first; NaN and a missing clearance as empty cells
    rows = (tmp_path / "small" / "lines.csv").read_text(encoding="utf-8-sig").splitlines()[1:]
    assert [r.split(",")[:3] for r in rows][:3] == [["1", "True", "6"], ["1", "False", "6"], ["1", "False", "6"]]
    assert [int(float(r.split(",")[3]) * 7 - 700 + 0.5) for r in rows] == [4, 5, 6, 7, 8, 9, 0, 3, 1, 2]
    for name in ("data.js", "lines.js"):
        text = (tmp_path / "small" / name).read_text(encoding="utf-8")
        value = json.loads(text[text.index("= {") + 2:-2])
        assert text.endswith("};\n") and len(value["lines"]) == 10
    data = (tmp_path / "small" / "data.js").read_text(encoding="utf-8")
    run_value = json.loads(data[data.index("= {") + 2:-2])
    assert [row[-1] for row in run_value["lines"]][:5] == [{"d": [0, 0], "z": [1.5, None]}, None, None, None,
                                                           {"d": [0, 4], "z": [1.5, None]}]

    path = str(tmp_path / "0.table.pkl.gz")
    search._save_tile(path, lines)
    loaded = search._load_tile(path)
    assert loaded.profiles == lines.profiles and loaded.columns.keys() == lines.columns.keys()
    assert all(np.array_equal(loaded.columns[k], lines.columns[k], equal_nan=True) for k in lines.columns)
    search._save_tile(path, sh.LineTable.empty())
    assert len(search._load_tile(path)) == 0


def test_line_table():
    """Rows taken and joined keep their profiles; a row as the dict of before."""
    import helpers as sh
    lines = _fake_lines(6)
    taken = lines.take(np.array([4, 1, 0]))
    assert taken.columns["length"].tolist() == [lines.columns["length"][k] for k in (4, 1, 0)]
    assert taken.profiles == {0: lines.profiles[4], 2: lines.profiles[0]}
    both = sh.LineTable.concat([taken, lines.take(lines.columns["over_obstacles"])])
    assert len(both) == 3 + 4 and both.profiles == {0: lines.profiles[4], 2: lines.profiles[0], 5: lines.profiles[4]}
    row = lines.row(1)
    assert row["clearance_nmpt"] is None and row["anchor1"] == (50.0001, 19.1234567) and row["a1"] == (1, 0)
    assert lines.row(0)["clearance_nmpt"] == 0.0 and row["over_obstacles"] is True and row["profile"] is None
    assert len(sh.LineTable.concat([sh.LineTable.empty(), sh.LineTable.empty()])) == 0
    for index in (np.array([4, 1, 0]), lines.columns["over_obstacles"]):  # reorder: take in place
        expected, again = lines.take(index), _fake_lines(6)
        assert again.reorder(index) is again and again.profiles == expected.profiles
        assert all(np.array_equal(again.columns[k], v, equal_nan=v.dtype.kind == "f") for k, v in expected.columns.items())


def _cgroup(folder, **files):
    folder.mkdir(exist_ok=True)
    for name, text in files.items():
        (folder / name.replace("_", ".", 1)).write_text(text + "\n")
    return str(folder)


def test_cgroup_limits(tmp_path, monkeypatch):
    import search
    gib = 1 << 30
    # Docker: mem_limit 4g with 1 GiB used, a third of it droppable page cache; cpus 1.5
    root = _cgroup(tmp_path / "limited", memory_max=str(4 * gib), memory_current=str(gib),
                   memory_stat=f"anon {gib // 2}\ninactive_file {gib // 3}\nactive_file 1",
                   cpu_max="150000 100000")
    limits = search.cgroup_limits(root)
    assert limits.memory == 4 * gib - (gib - gib // 3)
    cpus = len(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else 2
    assert limits.cpus == min(2, cpus)
    # No limits set, or no cgroup v2 files at all (Windows, macOS, cgroup v1)
    unlimited = _cgroup(tmp_path / "max", memory_max="max", memory_current=str(gib), cpu_max="max 100000")
    assert search.cgroup_limits(unlimited) == search.CgroupLimits()
    assert search.cgroup_limits(str(tmp_path / "missing")) == search.CgroupLimits()

    # The tiles follow the container's memory, the threads its quota, unless set explicitly
    params = pm.SearchParams(lat=50, lon=19, max_length=2000)  # an overlap of 2 302 m at 1 m
    monkeypatch.setattr(search.psutil, "virtual_memory", lambda: type("M", (), {"available": 64 * gib})())
    small = _cgroup(tmp_path / "small", memory_max=str(4 * gib), memory_current="0", cpu_max="100000 100000")
    monkeypatch.setattr(search, "CGROUP_ROOT", small)
    assert search.tile_core_size(params, 1.0) == 1500  # sqrt(4 GiB / 2 / 50 B) = 6 554 px less the overlaps
    monkeypatch.delenv("NUMBA_NUM_THREADS", raising=False)
    assert search.line_threads(params) == 1
    assert search.line_threads(params.model_copy(update={"threads": 3})) == 3
    # NUMBA_NUM_THREADS of compose.yaml (the quota's cores): all of them, never more than the quota
    import numba
    monkeypatch.setenv("NUMBA_NUM_THREADS", "4")
    assert search.line_threads(params) == 1
    seven = _cgroup(tmp_path / "seven", memory_max="max", memory_current="0", cpu_max="700000 100000")
    monkeypatch.setattr(search, "CGROUP_ROOT", seven)
    monkeypatch.setattr(numba.config, "NUMBA_NUM_THREADS", 7)
    monkeypatch.setattr(search.os, "sched_getaffinity", lambda pid: set(range(8)), raising=False)
    assert search.line_threads(params) == 7
    monkeypatch.setattr(search, "CGROUP_ROOT", unlimited)
    assert search.line_threads(params) is None
    monkeypatch.delenv("NUMBA_NUM_THREADS")
    assert search.line_threads(params) is None
    assert search.tile_core_size(params, 1.0) == 5000  # TILE_PX_MAX: 10 000 px; the 64 GiB would allow 26 000


def test_tile_at_most_tile_px_max():
    """A tile has at most TILE_PX_MAX pixels with its overlap whatever the memory (a PC with much
    memory would take one tile of hundreds of Mpx to save little work); a site's max_px below it
    and --tile-size are as before."""
    import search
    params = pm.SearchParams(lat=50, lon=19, max_length=100)
    assert search._overlap(params, 1.0) == 402 and search.TILE_PX_MAX == 100e6
    assert search.tile_core_size(params, 1.0, memory=10 ** 12) == 9000  # 10 000 px less twice 402 m, in steps of 500
    assert search.tile_core_size(params, 1.0, memory=10 ** 12, max_px=150e6) == 9000
    small = int(300 * 300 * search.PIXEL_BYTES / search.TILE_MEMORY_SHARE)  # a tile of 300 px with its overlaps
    assert search.tile_core_size(params, 1.0, memory=small) == 500
    long = params.model_copy(update={"max_length": 2000})  # an overlap of 2 302 m
    assert search.tile_core_size(long, 1.0, memory=10 ** 12) == 5000
    assert search.tile_core_size(long, 1.0, memory=10 ** 12, max_px=36e6) == 1000  # 6 000 px less twice 2 302
    assert search.tile_core_size(long.model_copy(update={"tile_size": 12000}), 1.0, memory=10 ** 12) == 12000


def test_errors_without_query_strings(monkeypatch):
    """A failed request reports its URL without the query (an API key must not reach messages)."""
    monkeypatch.setattr(src.net, "_sleep", lambda attempt: None)
    url = "http://127.0.0.1:9/API/globaldem?demtype=NASADEM&API_Key=secret123"
    with pytest.raises(RuntimeError) as error:
        src.net._get(url, timeout=2)
    assert "secret123" not in str(error.value) and "/API/globaldem" in str(error.value)
    with pytest.raises(RuntimeError) as error:
        src.net._get("http://127.0.0.1:9/API/globaldem", params={"API_Key": "secret123"}, timeout=2)
    assert "secret123" not in str(error.value)
    assert cache.clean_error("404 for url: https://x.org/a?key=k&b=1 (why?)") == "404 for url: https://x.org/a?... (why?)"


def test_run_folder_names():
    """A run's folder takes its name in ASCII (anyascii): letters without a Unicode decomposition were
    dropped before ("Għar Ħasan" -> "Gar-asan", "Ærø" -> "r") and other scripts gave "run"."""
    import runs as rn
    for name, folder in (("Żabi Koń", "Zabi-Kon"), ("Łódź", "Lodz"), ("Għar Ħasan", "Ghar-Hasan"), ("Ta' Ċenċ", "Ta-Cenc"),
                         ("Tromsø", "Tromso"), ("Ærø", "Aero"), ("Straße", "Strasse"), ("Đakovo", "Dakovo"),
                         ("Þingvellir", "Thingvellir"), ("Γαύδος", "Gaydos"), ("Санкт-Петербург", "Sankt-Peterburg"),
                         ("coast ±100 m within osm:Gozo", "coast-100-m-within-osm-Gozo"), ("", "run"), ("—", "run")):
        assert rn._slug(name) == folder, (name, rn._slug(name))
    assert len(rn._slug("Ħ" * 60)) == 40


def test_run_ids_and_public_meta(tmp_path):
    """Run ids are unique within one second and not guessable; lines.geojson lists no cache files."""
    import json
    import re
    from datetime import datetime
    import helpers as sh
    import mapping as mp
    import runs as rn
    created = datetime(2026, 10, 27, 12, 0, 0)
    first, second = (rn.new_run(str(tmp_path), "Żabi Koń", created) for _ in range(2))
    assert first["id"] != second["id"]
    assert re.fullmatch(r"2026-10-27_120000_Zabi-Kon_[0-9a-f]{16}", first["id"]), first["id"]
    meta = {"name": "x", "summary": {"lines": 0},
            "data": [{"layer": "NMT", "folder": "poland/nmt", "files": 2, "paths": ["poland/nmt/a.tif", "b.tif"]}]}
    rn.save_results(first["path"], sh.LineTable.empty(), mp.Groups.each_alone(0), meta)
    saved = json.loads(open(os.path.join(first["path"], "lines.geojson"), encoding="utf-8").read())["findaline"]
    assert saved["data"] == [{"layer": "NMT", "folder": "poland/nmt", "files": 2}]
    assert json.load(open(os.path.join(first["path"], "run.json"), encoding="utf-8")) == meta  # run.json keeps them


def test_every_source_has_licence_and_attribution():
    """Every source, each of its layers and the layers used for filling name their licence and notice."""
    layers = [src.WATER_MASK]
    for source in src.SOURCES.values():
        assert source.licence and source.attribution, source.id
        layers += [layer for layer in (source.nmt, source.nmpt) if layer is not None]
    for layer in layers:
        credit = layer.credit
        assert credit and credit.data and credit.attribution and credit.licence, layer.description
        assert credit.url.startswith("https://"), layer.description
    assert src.SOURCES["europe"].nmt.credit is src.FABDEM_CREDIT  # the gap filling layer has its own
    assert "CC BY-NC-SA 4.0" in src.SOURCES["europe"].licence


def test_used_layers_carry_their_credit(tmp_path):
    """What a run records about a layer (run.json "data") includes its credit."""
    from types import SimpleNamespace
    grid = SimpleNamespace(crs="EPSG:2180", bounds=(553000, 254000, 554000, 255000))
    assert src.WATER_MASK.used(grid, str(tmp_path))["credit"] == src.WATER_MASK_CREDIT.as_dict()
    assert src.SOURCES["geoportal"].nmt.credit is src.GUGIK_CREDIT


def test_run_credits(tmp_path):
    """A run lists each dataset's credit once, OSM too when the area came from it, and writes
    them to ATTRIBUTION.txt; runs.js leaves them out."""
    import json
    from datetime import datetime
    import helpers as sh
    import mapping as mp
    import runs as rn
    import search
    from types import SimpleNamespace
    europe = src.SOURCES["europe"]
    data = [{"layer": "FABDEM", "credit": europe.nmt.credit.as_dict()},
            {"layer": "FABDEM", "credit": europe.nmt.credit.as_dict()},  # e.g. the gap filling of a second tile
            {"layer": "Terrain file", "file": "x.tif"}]
    area = ar.Circle(50.0, 19.0, 100)
    assert search._credits(SimpleNamespace(area=area), data) == [src.FABDEM_CREDIT.as_dict()]
    area.spec = {"area": "cliffs", "within": "osm:Gozo"}
    credits = search._credits(SimpleNamespace(area=area), data)
    assert credits == [src.FABDEM_CREDIT.as_dict(), src.OSM_CREDIT.as_dict()]
    run = rn.new_run(str(tmp_path), "Gozo", datetime(2026, 10, 27, 12, 0, 0))
    meta = {"id": run["id"], "name": "Gozo", "created": "2026-10-27T12:00:00", "description": "",
            "summary": {"lines": 0}, "source": {"id": "europe"}, "data": data, "attribution": credits}
    rn.save_results(run["path"], sh.LineTable.empty(), mp.Groups.each_alone(0), meta)
    with open(os.path.join(run["path"], "ATTRIBUTION.txt"), encoding="utf-8") as f:
        text = f.read()
    for credit in credits:
        assert credit["attribution"] in text and credit["licence"] in text and credit["url"] in text
    assert src.COPERNICUS_DISCLAIMER in text  # FABDEM's notice
    assert "attribution" not in rn._listed(meta)  # runs.js
    with open(os.path.join(run["path"], "run.json"), encoding="utf-8") as f:
        assert json.load(f)["attribution"] == credits


def test_replacing(tmp_path):
    """A file written under a unique temporary name replaces the old one only when complete."""
    path = tmp_path / "runs.js"
    path.write_text("old", encoding="utf-8")
    with cache.replacing(str(path), "w", encoding="utf-8") as a, cache.replacing(str(path), "w", encoding="utf-8") as b:
        assert a.name != b.name and path.read_text(encoding="utf-8") == "old"  # two writers, two files
        a.write("first")
        b.write("second")
    assert path.read_text(encoding="utf-8") == "first"  # the writer that finished last (b closes first)
    with pytest.raises(ValueError):
        with cache.replacing(str(path)) as f:
            f.write(b"half")
            raise ValueError("failed")
    assert path.read_text(encoding="utf-8") == "first" and os.listdir(tmp_path) == ["runs.js"]


def test_shared_run_files_one_process_at_a_time(tmp_path):
    """The viewer and the index of the runs folder are written by one process at a time
    (cache.runs_lock): a run saved while another process holds the lock waits for it, then writes
    them. Two compute slots installing the viewer at once failed on Windows (PermissionError of
    os.replace while the other process had the file open), seen in test_two_jobs_computing_at_once."""
    import subprocess
    import time
    runs_dir = tmp_path / "runs"
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    code = ("import sys; sys.path.insert(0, sys.argv[1]); import mapping, runs\n"
            "open(sys.argv[3], 'w').close()\n"
            "runs.write_index(sys.argv[2])\n")
    started = tmp_path / "started"
    with cache.runs_lock(str(runs_dir)):
        child = subprocess.Popen([sys.executable, "-c", code, repo, str(runs_dir), str(started)])
        deadline = time.monotonic() + 120
        while not started.exists():
            assert time.monotonic() < deadline and child.poll() is None, "the child never started"
            time.sleep(0.05)
        # Its imports done, a second to reach the lock (later on a busy machine: then the checks below
        # pass without having seen it wait, never wrongly fail)
        time.sleep(1.0)
        assert child.poll() is None
        assert not (runs_dir / "runs.js").exists() and not (runs_dir / "_viewer" / "viewer.js").exists()
    assert child.wait(timeout=120) == 0
    assert (runs_dir / "runs.js").read_text(encoding="utf-8") == "window.FINDALINE_RUNS = [];\n"
    assert (runs_dir / "index.html").exists() and (runs_dir / "_viewer" / "viewer.js").exists()


def test_labels_topics_and_presets():
    """Every field the web may set has a label, a unit and a hint in the message catalogue
    (locales/en.json), and every choice of a choice field a label; every such field belongs to one
    topic of the form (params.TOPICS), every topic and preset has a title; each preset sets only
    fields of PRESET_FIELDS and validates as SearchParams; a preset outside a user's bounds is
    unavailable."""
    import messages
    import web
    from settings import Limits
    texts = messages.catalogue()
    web_fields = [f["name"] for f in web.schema()]
    assert set(web_fields) == {n for n, i in pm.SearchParams.model_fields.items()
                               if not {"cli_only", "web_only"} & set(i.json_schema_extra or {})}
    for name in web_fields:
        assert texts[f"field.{name}.label"] and not texts[f"field.{name}.label"].endswith("."), name
        assert f"field.{name}.unit" in texts and texts[f"field.{name}.help"].endswith("."), name
    for field in web.schema():
        for choice in field["choices"] or []:
            assert field["name"] == "source" or f"choice.{field['name']}.{choice}" in texts, (field["name"], choice)
    named = {k.split(".")[1] for k in texts if k.startswith("field.")}
    assert named == set(web_fields), named ^ set(web_fields)  # no texts of fields that are gone
    topics = [n for names in pm.TOPICS.values() for n in names]
    assert sorted(topics) == sorted(web_fields), set(topics) ^ set(web_fields)
    assert all(f"topic.{t}" in texts for t in pm.TOPICS) and all(f"preset.{p}" in texts for p in pm.PRESETS)
    for preset, values in pm.PRESETS.items():
        assert (values is None or set(values) <= set(pm.PRESET_FIELDS)), preset
        full = pm.preset_values(preset)
        if full is not None:
            assert set(full) == set(pm.PRESET_FIELDS)
            pm.SearchParams(lat=50.1, lon=19.7, **full)  # valid on its own
    assert pm.preset_values("typical") == {"min_length": 30, "max_length": 150, "max_anchor_diff_m": 10}
    assert pm.preset_values("long")["max_anchor_diff_m"] == pm.SearchParams.model_fields["max_anchor_diff_m"].default
    offered = {p["id"]: p for p in web.presets(Limits.load(public=True))}
    assert list(offered) == ["typical", "long", "short", "custom"] and all(p["available"] for p in offered.values())
    assert offered["custom"]["values"] is None
    tight = {p["id"]: p for p in web.presets(Limits(max_length_max=200))}
    assert tight["typical"]["available"] and not tight["long"]["available"]
    assert tight["long"]["reason"] == "Longest line: at most 200 m on this site."
    fields = {f["name"]: f for f in web.schema()}
    assert offered["short"]["label"] == "Short & low" and fields["nmpt"]["choice_labels"]["off"] == "Do not check"
    assert fields["max_anchor_diff_m"]["label"] == "Anchor height difference"
    assert fields["max_anchor_diff_m"]["unit"] == "m" and fields["max_anchor_diff_m"]["topic"] == "lines"
    assert fields["source"]["choice_labels"]["auto"] == "Automatic"


def test_viewer_keys_in_catalogue():
    """Every key the page asks for by its literal (t("...") or t('...') in viewer/src) is in the message
    catalogue, in its plain or a plural form."""
    import re

    import messages
    texts = messages.catalogue()
    root = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "viewer", "src")
    used = set()
    for folder, _, files in os.walk(root):
        for file in files:
            if file.endswith((".ts", ".tsx")):
                with open(os.path.join(folder, file), encoding="utf-8") as f:
                    used |= set(re.findall(r"""\bt\(\s*["']([^"'`]+)["']""", f.read()))
    assert "ui.credits.toggle" in used
    missing = [k for k in used if not {k, f"{k}_one", f"{k}_other"} & set(texts)]
    assert not missing, missing


def _error_codes() -> dict:
    """The codes of the coded errors and notes of the server's modules (messages.UserError, Note,
    ServiceError, search.SearchError, jobs.QuotaExceeded, osm.OverpassDayMax): {code: "file:line"}, read
    from the source."""
    import ast
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    kinds = {"rate_": ["estimate", "profile", "patch", "reach", "place", "report", "time_zone", "job"],  # web.RATE_NAMES
             "quota_use_": ["km2", "mpx", "nominatim", "download_mb"]}           # jobs.USAGE
    position = {"UserError": 1, "SearchError": 1, "Note": 1, "ServiceError": 1, "QuotaExceeded": 2,
                "OverpassDayMax": 1}

    def literals(node) -> list:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return [node.value]
        if isinstance(node, ast.IfExp):
            return literals(node.body) + literals(node.orelse)
        if isinstance(node, ast.JoinedStr) and isinstance(node.values[0], ast.Constant):
            return [node.values[0].value + kind for kind in kinds[node.values[0].value]]
        return []

    found = {}
    names = [name for name in sorted(os.listdir(root)) if name.endswith(".py")]
    for folder, _, files in sorted(os.walk(os.path.join(root, "sources"))):  # the package sources/
        names += [os.path.relpath(os.path.join(folder, f), root) for f in sorted(files) if f.endswith(".py")]
    for name in names:
        with open(os.path.join(root, name), encoding="utf-8") as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            called = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
            web = called == "web" and isinstance(func, ast.Attribute)
            of = called == "of" and isinstance(func, ast.Attribute)  # SearchError.of(error, text, code)
            if web or of:
                called = func.value.attr if isinstance(func.value, ast.Attribute) else getattr(func.value, "id", "")
            if called == "E":  # web.py's short name of messages.UserError
                called = "UserError"
            if called not in position:
                continue
            code = next((k.value for k in node.keywords if k.arg == "code"), None)
            index = 0 if web else 2 if of else position[called]
            if code is None and len(node.args) > index:
                code = node.args[index]
            for value in literals(code) if code is not None else []:
                found[value] = f"{name}:{node.lineno}"
    import messages
    for value in set(messages._PYDANTIC.values()) | {"invalid_request"}:
        found[value] = "messages.py"
    return found


def test_error_codes_in_catalogue():
    """Every code of a coded error or note has its text in the message catalogue ("error.<code>", or
    its plural forms), and no text of the web names a command-line option or a field's snake_case name."""
    import messages
    import params as pm
    texts = messages.catalogue()
    codes = _error_codes()
    assert {"lat_lon_range", "at_most", "too_many_lines", "quota_use_km2", "coast_pieces_left_out", "rate_job",
            "no_worker", "opentopo_key", "not_a_number", "download_failed", "no_source",
            "overpass_day_max"} <= set(codes), sorted(codes)
    missing = [f"{c} ({w})" for c, w in codes.items()
               if not {f"error.{c}", f"error.{c}_one", f"error.{c}_other"} & set(texts)]
    assert not missing, missing
    names = [n for n in list(pm.SearchParams.model_fields) + list(pm.CliOptions.model_fields) if "_" in n]
    for key, value in texts.items():
        if key.startswith("error."):
            assert "--" not in value and not [n for n in names if n in value], (key, value)


def test_coded_errors():
    """A coded error keeps the command line's text as str() and gives the web its own, with the field's
    label; pydantic's errors are unwrapped: a validator's coded error, or a code of their type."""
    import messages
    import params as pm
    from pydantic import ValidationError
    with pytest.raises(ValidationError) as error:
        pm.SearchParams(lat=50, lon=19, radius=0)
    coded = messages.user_error(error.value)
    assert str(coded) == "--radius must be positive" and coded.code == "positive"
    assert coded.detail() == {"message": "Search radius must be more than 0.", "code": "positive",
                              "params": {"field": "radius"}}
    with pytest.raises(ValidationError) as error:
        pm.SearchParams(lat=50, lon=19, threads="many")
    assert messages.user_error(error.value).detail() == {
        "message": "Threads: enter a whole number.", "code": "not_whole_number", "params": {"field": "threads"}}
    assert messages.user_error(ValueError("plain")) is None
    note = messages.Note("1 piece(s) ... --max-length", "coast_pieces_left_out", count=3, near=200, far=400,
                         lat=1.5, lon=2.5)
    assert str(note).endswith("--max-length") and note.web_text().startswith("3 parts of the coast are 200–400 m")
    assert messages.quantity("slope_threshold", 45.0) == "45°" and messages.quantity("ortho_detail", 5) == "5"


def test_elevation_band_validation():
    """--min-elevation/--max-elevation: either bound alone, or both in order (equal is a band of one
    height); a lower bound above the upper one is refused with its code."""
    import messages
    import params as pm
    import runs
    from pydantic import ValidationError
    assert pm.SearchParams(lat=50, lon=19).min_elevation is None
    assert pm.SearchParams(lat=50, lon=19, min_elevation=800).min_elevation == 800
    assert pm.SearchParams(lat=50, lon=19, max_elevation=-20).max_elevation == -20
    assert pm.SearchParams(lat=50, lon=19, min_elevation=800, max_elevation=800).max_elevation == 800
    with pytest.raises(ValidationError) as error:
        pm.SearchParams(lat=50, lon=19, min_elevation=1500, max_elevation=800)
    coded = messages.user_error(error.value)
    assert coded.code == "elevation_range" and "--min-elevation" in str(coded)
    assert "--" not in coded.web_text()
    base = {"radius": 100, "resolution": 1, "slope_threshold": 45, "min_length": 30, "max_length": 100,
            "nmpt": None}
    assert "anchors" not in runs.params_summary({"params": base})
    assert runs.params_summary({"params": {**base, "min_elevation": 800, "max_elevation": 1500}}).endswith(
        "anchors ≥800 m a.s.l., anchors ≤1500 m a.s.l.")


HARD_FLOATS = [0.125, 0.375, 2.675, 1.005, 0.5, 1.5, 2.5, -0.5, -2.675, 0.0, -0.0, -0.004, -1e-9, 1e-300, 5e-324,
               1e300, -1e300, 2.0 ** 52 + 1, 4.5e15 + 0.5, 1e16, 123456.78905, 50.12345675, 19.00000005,
               float("nan"), float("inf"), float("-inf"), 0.1 + 0.2, 1 / 3, 1e22, 0.045, 0.055, 9.995]


def test_round_floats_like_round():
    """round_floats: Python's round() of every value, halfway cases, signs and specials too."""
    import runs
    rng = np.random.default_rng(1)
    values = np.concatenate([HARD_FLOATS, [k / 1000 for k in range(-3000, 3000)], [k / 8 for k in range(-100, 100)],
                             rng.normal(0, 1, 20000), rng.normal(0, 1, 20000) * 10.0 ** rng.integers(-12, 18, 20000),
                             rng.integers(-10 ** 7, 10 ** 7, 20000) / 10 ** rng.integers(1, 9, 20000) + 0.5e-7])
    for digits in (0, 1, 2, 3, 7, 12):
        got = runs.round_floats(values, digits).tolist()
        expected = [round(v, digits) for v in values.tolist()]
        assert list(map(repr, got)) == list(map(repr, expected)), digits


def _old_row_order(groups) -> tuple:
    """runs.row_order before wave 5 (the order of every line at once): the reference."""
    sizes = groups.sizes()
    is_rep = groups.members == np.repeat(groups.rep, sizes)
    group = np.repeat(np.arange(len(groups), dtype=np.int64), sizes)
    order = np.lexsort((~is_rep, group))
    return groups.members[order], group[order] + 1, is_rep[order], sizes[group[order]]


def _old_csv_and_features(lines, groups):
    """lines.csv and the features of lines.geojson as the code before 2026-10-31 wrote them:
    csv.DictWriter and json.dumps of dicts of round()ed Python values."""
    import csv
    import io
    import json
    import runs as rn
    rows = []
    ends = "lift_needed" in lines.columns  # a run with an end zone or A-frames (wave 2b): two columns more
    for k, number, is_rep, size in zip(*(column.tolist() for column in _old_row_order(groups))):
        r = lines.row(k)
        (lat1, lon1), (lat2, lon2), (x1, y1), (x2, y2) = r["anchor1"], r["anchor2"], r["a1_xy"], r["a2_xy"]
        nmpt = np.nan if r["clearance_nmpt"] is None else r["clearance_nmpt"]
        rows.append({
            "group": number, "representative": is_rep, "group_size": size, "length_m": round(r["length"], 1),
            "clearance_m": round(r["clearance"], 2), "clearance_nmpt_m": rn.rounded(nmpt, 2),
            **({"lift_needed_m": round(r["lift_needed"], 2), "lift_no_zone_m": round(r["lift_no_zone"], 2)}
               if ends else {}),
            "over_trees_buildings": r["over_obstacles"], "water_m": r["water_m"], "filled_m": r["filled_m"],
            "height_max_m": round(r["height_max"], 2), "height_mean_m": round(r["height_mean"], 2),
            "high_pct": round(r["high_pct"], 1),
            "anchor1_lat": round(lat1, 7), "anchor1_lon": round(lon1, 7), "anchor1_elev_m": round(r["elev_a1"], 2),
            "anchor1_northing": round(y1, 2), "anchor1_easting": round(x1, 2),
            "anchor1_wall_angle": round(r["angle1"], 1),
            "anchor1_prominence_m": rn.rounded(r["prom1"], 1), "anchor1_drop_m": rn.rounded(r["drop1"], 1),
            "anchor2_lat": round(lat2, 7), "anchor2_lon": round(lon2, 7), "anchor2_elev_m": round(r["elev_a2"], 2),
            "anchor2_northing": round(y2, 2), "anchor2_easting": round(x2, 2),
            "anchor2_wall_angle": round(r["angle2"], 1),
            "anchor2_prominence_m": rn.rounded(r["prom2"], 1), "anchor2_drop_m": rn.rounded(r["drop2"], 1)})
    table = io.StringIO(newline="")
    fields = list(rows[0]) if ends else rn.FIELDS
    writer = csv.DictWriter(table, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)
    features = [{"type": "Feature", "geometry": {"type": "LineString", "coordinates": [
        [r["anchor1_lon"], r["anchor1_lat"]], [r["anchor2_lon"], r["anchor2_lat"]]]}, "properties": r} for r in rows]
    return table.getvalue(), json.dumps(features, ensure_ascii=False)[1:-1]


def _old_map_rows(lines, profiles: bool):
    import runs as rn
    rows = []
    for k in range(len(lines)):
        r = lines.row(k)
        (lat1, lon1), (lat2, lon2) = r["anchor1"], r["anchor2"]
        nmpt = np.nan if r["clearance_nmpt"] is None else r["clearance_nmpt"]
        row = [round(lat1, 7), round(lon1, 7), round(lat2, 7), round(lon2, 7), *r["a1_xy"], *r["a2_xy"], r["length"],
               r["clearance"], rn.rounded(nmpt, 2), round(r["elev_a1"], 2), round(r["elev_a2"], 2),
               r["over_obstacles"], round(r["water_m"], 1), round(r["filled_m"], 1), r["height_max"],
               round(r["height_mean"], 2), round(r["high_pct"], 1), round(r["angle1"], 1), round(r["angle2"], 1),
               rn.rounded(r["prom1"], 1), rn.rounded(r["prom2"], 1), rn.rounded(r["drop1"], 1),
               rn.rounded(r["drop2"], 1)]
        if "lift_needed" in r:  # wave 2b: the head's "ends", before the profile
            row += [round(r["lift_needed"], 2), round(r["lift_no_zone"], 2)]
        if profiles:
            row.append(lines.profiles.get(k))
        rows.append(row)
    return rows


@pytest.mark.parametrize("ends", [False, True], ids=["plain", "end-zone"])
def test_saved_text_as_before(tmp_path, monkeypatch, ends):
    """lines.csv, lines.geojson, data.js and lines.js built column by column: the same text as
    csv.DictWriter and json.dumps of the rows of Python values wrote, for values hard to round
    (halves, negative zero, NaN, infinities, very large and small), a missing clearance and
    non-ASCII names; with an end zone and A-frames (ends) also the two A-frame heights (after
    clearance_nmpt_m, before the profile) and the heads' "ends"."""
    import json
    from shapely.geometry import Point
    import mapping as mp
    import runs as rn

    class Area:
        center = (50.0, 19.1)

        @staticmethod
        def shape_wgs84():
            return Point(19.1, 50.0).buffer(0.01)

    n = len(HARD_FLOATS)
    lines = _fake_lines(n)
    hard = np.array(HARD_FLOATS)
    for shift, name in enumerate(["length", "clearance", "clearance_nmpt", "water_m", "filled_m", "height_max",
                                  "height_mean", "high_pct", "elev_a1", "elev_a2", "angle1", "angle2", "prom1",
                                  "prom2", "drop1", "drop2"]):
        lines.columns[name] = np.roll(hard, shift)
    for shift, name in enumerate(["anchor1", "anchor2", "a1_xy", "a2_xy"]):
        lines.columns[name] = np.column_stack([np.roll(hard, 3 * shift + 1), np.roll(hard, -3 * shift - 2)])
    if ends:
        lines.columns["lift_needed"], lines.columns["lift_no_zone"] = np.roll(hard, 5), np.roll(hard, -7)
    lines.profiles[2] = {"d": [0.0, -0.0, 1e300], "z": [float("nan"), None], "name": "Żabi"}
    groups = mp.Groups(np.array([4, 0]), np.array([4, *range(5, n), 3, 0, 1, 2]), np.array([0, n - 4, n]))
    meta = {"name": "Żabi Koń „ß”", "summary": {"lines": n}}
    run = {"id": "r", "name": "Żabi Koń „ß”", "created": "2026-10-31T10:00:00+00:00"}
    if ends:
        run["params"] = {"end_zone": 5, "anchor_lift": 2}
    monkeypatch.setattr(rn, "LINES_CHUNK", 5)
    monkeypatch.setattr(mp, "LINES_CHUNK", 5)
    rn.save_results(str(tmp_path), lines, groups, meta)
    mp.save_map(lines, Area, str(tmp_path), str(tmp_path / "runs"), run, "EPSG:2180")

    table, features = _old_csv_and_features(lines, groups)
    assert (tmp_path / "lines.csv").read_bytes() == table.encode("utf-8-sig")
    geojson = (tmp_path / "lines.geojson").read_text(encoding="utf-8")
    assert geojson == ('{"type": "FeatureCollection", "features": [' + features + '], "findaline": '
                       + json.dumps(rn.public_meta(meta), ensure_ascii=False) + "}")
    for name, profiles in (("data.js", True), ("lines.js", False)):
        text = (tmp_path / name).read_text(encoding="utf-8")
        expected = json.dumps(_old_map_rows(lines, profiles), separators=(",", ":"))
        assert text[text.index('"lines":[') + len('"lines":'):] == expected + "};\n"
        head = json.loads(text[text.index(" = {") + 3:text.index(',"lines":[')] + "}")
        assert head.get("ends") == (["lift_needed", "lift_no_zone"] if ends else None), name
    assert '"name":"\\u017babi Ko\\u0144' in (tmp_path / "data.js").read_text(encoding="utf-8")
    header = (tmp_path / "lines.csv").read_text(encoding="utf-8-sig").splitlines()[0].split(",")
    assert ("lift_needed_m" in header) == ends and header[6:8] == (["lift_needed_m", "lift_no_zone_m"] if ends else
                                                                   ["over_trees_buildings", "water_m"])
    import helpers as sh
    assert rn.END_COLUMNS == sh.END_VALUES  # runs repeats them (the web process imports runs, not helpers)


def test_year_of_the_run():
    """sources.YEAR in a credit is filled with a run's year; texts without it stay as they are;
    LGLN's credit, orthophoto and note name it (AGNB no. 7.2: the year of the download)."""
    assert src.dated(f"© X {src.YEAR}, changed", 2031) == "© X 2031, changed"
    assert src.dated("© X {other} {", 2031) == "© X {other} {"
    for credit in (src.FABDEM_CREDIT, src.OSM_CREDIT, src.GUGIK_CREDIT):
        assert src.dated_credit(credit.as_dict(), 2031) == credit.as_dict()
        assert list(src.dated_credit(credit.as_dict(), 2031)) == list(credit.as_dict())  # order kept
    lower_saxony = src.SOURCES["lower_saxony"]
    assert lower_saxony.credits[0].attribution == f"© GeoBasis-DE/LGLN {src.YEAR}, Daten geändert"
    assert src.YEAR in lower_saxony.ortho.attribution and src.YEAR in lower_saxony.note
    assert src.dated_credit(lower_saxony.credits[0].as_dict(), 2027)["attribution"] == \
        "© GeoBasis-DE/LGLN 2027, Daten geändert"


def test_row_order_in_parts_as_before(monkeypatch):
    """runs.row_order of a part of the rows: the rows of the order of every line at once (the old
    lexsort), for parts of any size, representatives anywhere in their groups or not among them,
    empty groups and groups of one; a representative twice in its group is refused."""
    import mapping as mp
    import runs as rn
    rng = np.random.default_rng(5)
    cases = [mp.Groups.each_alone(0), mp.Groups.each_alone(1), mp.Groups.each_alone(7),
             mp.Groups(np.array([4, 0]), np.array([4, 5, 6, 7, 8, 9, 3, 0, 1, 2]), np.array([0, 6, 10])),
             mp.Groups(np.array([9, 2, 5]), np.array([0, 1, 2, 3, 4]), np.array([0, 0, 3, 5]))]  # 9: not a member
    for _ in range(40):
        n = int(rng.integers(1, 400))
        members = rng.permutation(n).astype(np.int64)
        cuts = np.sort(rng.integers(0, n + 1, int(rng.integers(0, 30))))
        start = np.concatenate([[0], cuts, [n]]).astype(np.int64)
        rep = np.array([members[rng.integers(a, b)] if b > a and rng.random() < 0.9 else n + g
                        for g, (a, b) in enumerate(zip(start[:-1], start[1:]))], dtype=np.int64)
        cases.append(mp.Groups(rep, members, start))
    for groups in cases:
        old = _old_row_order(groups)
        n = len(groups.members)
        for chunk in (1, 2, 3, 7, 64, 10_000):
            monkeypatch.setattr(rn, "LINES_CHUNK", chunk)
            at = rn.rep_positions(groups)
            parts = [rn.row_order(groups, lo, min(n, lo + chunk), at) for lo in range(0, n, chunk)] or \
                [rn.row_order(groups, 0, 0, at)]
            for k, column in enumerate(old):
                new = np.concatenate([part[k] for part in parts])
                assert new.dtype.kind == column.dtype.kind and np.array_equal(new, column), (groups, chunk, k)
    twice = mp.Groups(np.array([1]), np.array([1, 0, 1]), np.array([0, 3]))
    for chunk in (1, 10):
        monkeypatch.setattr(rn, "LINES_CHUNK", chunk)
        with pytest.raises(ValueError):
            rn.rep_positions(twice)


def test_join_of_tiles_as_concat(tmp_path):
    """LineTable.join (the lines of a tiled search, column by column, each tile's columns released):
    the same columns, dtypes, values and profiles as concat, also with empty tables and tile files
    saved by _save_tile; the joined tables are left empty."""
    import helpers as sh
    import search
    lines = _fake_lines(9)
    cases = [[], [sh.LineTable.empty()], [sh.LineTable.empty(), sh.LineTable.empty()], [lines.take(np.arange(9))],
             [lines.take([4, 1, 0]), sh.LineTable.empty(), lines.take(np.arange(9) % 2 == 1), lines.take([8, 4])],
             [sh.LineTable.empty(), lines.take([0]), lines.take([4, 0, 4])]]
    paths = []
    for k, table in enumerate(cases[4]):
        paths.append(str(tmp_path / search.TILE_FILE.format(k)))
        search._save_tile(paths[-1], table)
    cases.append([search._load_tile(path) for path in paths])
    for tables in cases:
        old = sh.LineTable.concat(tables)
        new = sh.LineTable.join(tables)
        assert list(new.columns) == list(old.columns) and new.profiles == old.profiles
        assert set(new.profiles) == set(old.profiles)
        for name, column in old.columns.items():
            assert new.columns[name].dtype == column.dtype and new.columns[name].shape == column.shape, name
            assert np.array_equal(new.columns[name], column, equal_nan=column.dtype.kind == "f"), name
        assert all(t.columns == {} and t.profiles == {} for t in tables)


def test_tiles_without_pixels(tmp_path):
    """search._lines ends without the pixel columns; a tile file of before (with them) and a tile
    without anchors (LineTable.empty) lose them on loading, so tiles of both kinds join."""
    import helpers as sh
    import search
    old, new = _fake_lines(5), _fake_lines(4).without_pixels()
    assert "a1" not in new.columns and "a2" not in new.columns and len(new) == 4
    assert new.row(0)["anchor1"] == old.row(0)["anchor1"]
    paths = [str(tmp_path / search.TILE_FILE.format(k)) for k in range(3)]
    for path, table in zip(paths, (old, sh.LineTable.empty(), new)):
        search._save_tile(path, table)
    joined = sh.LineTable.join([search._load_tile(path).without_pixels() for path in paths])
    expected = sh.LineTable.concat([_fake_lines(5).without_pixels(), _fake_lines(4).without_pixels()])
    assert list(joined.columns) == list(expected.columns) and joined.profiles == expected.profiles
    assert all(np.array_equal(joined.columns[k], expected.columns[k], equal_nan=True) for k in expected.columns)


def test_search_imports_numba_only_to_compute(tmp_path):
    """search.py imports the kernels (linesearch, lineprofiles, terrain, grouping: numba) inside the
    functions of steps 2-4: the download phase (plan, estimate, download_data) and the quick lane
    never load numba; a search computes as before."""
    import subprocess
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    code = f"""
import json, os, sys
sys.path.insert(0, {repo!r})
import search, warmup
from params import SearchParams
kernels = lambda: sorted(m for m in sys.modules if m.split('.')[0] in
                         ('numba', 'llvmlite', 'linesearch', 'lineprofiles', 'terrain', 'grouping'))
folder = {str(tmp_path)!r}
nmt, nmpt, (e, n) = warmup.write_grids(folder)
paths = search.Paths(folder, os.path.join(folder, 'work'))
plan = search.plan_search(SearchParams(elevation_file=nmt, surface_file=nmpt, easting=e, northing=n, radius=45,
                                       min_length=15, max_length=60, water='off', fill_gaps='off'), paths)
search.estimate_search(plan)
search.download_data(plan)
before = kernels()
lines = search.find_lines(plan, search.prepare_data(plan))
print(json.dumps([before, 'numba' in sys.modules, len(lines.results)]))
"""
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=600,
                            env={**os.environ, "HTTP_PROXY": "http://127.0.0.1:9", "HTTPS_PROXY": "http://127.0.0.1:9"})
    assert result.returncode == 0, result.stdout + result.stderr
    import json
    before, loaded, lines = json.loads(result.stdout.strip().splitlines()[-1])
    assert before == [] and loaded and lines > 0


def test_download_data_fetches_the_coastline_alongside_the_tiles(tmp_path, monkeypatch):
    """download_data asks the coastline's theme tiles (--coastline overpass without the world file) in a
    thread while the layers' tiles download; a requests error of the coastline is left to the search
    (the Copernicus mask), a RuntimeError fails the download as before."""
    import threading

    import requests

    import search
    import warmup
    from params import SearchParams
    nmt, _, (e, n) = warmup.write_grids(str(tmp_path))
    plan = search.plan_search(SearchParams(elevation_file=nmt, easting=e, northing=n, radius=45, min_length=15,
                                           max_length=60, water="fill", coastline="overpass", fill_gaps="off"),
                              search.Paths(str(tmp_path), str(tmp_path / "work")), lambda kind, text: None)
    asked, order = threading.Event(), []

    def theme(name, west, south, east, north, cache_dir, update):
        order.append(name)
        asked.set()
        return []

    def tiles(plan):
        assert asked.wait(30)  # the coastline is asked while the tiles download
        order.append("tiles")

    monkeypatch.setattr(search.coast, "world_file", lambda cache_dir: None)
    monkeypatch.setattr(search.osm, "theme", theme)
    monkeypatch.setattr(search, "_download_layers", tiles)
    search.download_data(plan)
    assert order == ["coastline", "tiles"]

    def fails(error):
        def theme(*args):
            raise error
        return theme
    monkeypatch.setattr(search, "_download_layers", lambda plan: None)
    monkeypatch.setattr(search.osm, "theme", fails(requests.ConnectionError("Overpass is down")))
    search.download_data(plan)
    monkeypatch.setattr(search.osm, "theme", fails(RuntimeError("broken")))
    with pytest.raises(search.SearchError, match="Download failed: broken"):
        search.download_data(plan)
    monkeypatch.setattr(search.coast, "world_file", lambda cache_dir: "world.shp")  # not asked with the world file
    search.download_data(plan)


def test_download_data_looks_the_place_name_up_alongside_the_tiles(tmp_path, monkeypatch):
    """download_data asks Nominatim for the run's name (a circle's place) in a thread while the
    layers' tiles download, so that step 5 finds the answers cached; its failure never fails the
    download."""
    import threading

    import search
    import warmup
    from params import SearchParams
    nmt, _, (e, n) = warmup.write_grids(str(tmp_path))
    plan = search.plan_search(SearchParams(elevation_file=nmt, easting=e, northing=n, radius=45, min_length=15,
                                           max_length=60, water="off", fill_gaps="off"),
                              search.Paths(str(tmp_path), str(tmp_path / "work")), lambda kind, text: None)
    asked, threads = threading.Event(), []

    def place_name(lat, lon, cache_dir):
        threads.append(threading.current_thread())
        asked.set()
        return "Somewhere"

    def tiles(plan):
        assert asked.wait(30)  # the name is asked while the tiles download

    monkeypatch.setattr(search.rn, "place_name", place_name)
    monkeypatch.setattr(search, "_download_layers", tiles)
    search.download_data(plan)
    assert threads and threads[0] is not threading.main_thread()

    def fails(lat, lon, cache_dir):
        raise RuntimeError("no name")

    monkeypatch.setattr(search.rn, "place_name", fails)
    monkeypatch.setattr(search, "_download_layers", lambda plan: None)
    search.download_data(plan)  # the download is fine without a name


def test_estimate_layers_in_parallel():
    """sources.layer.estimate_layers asks every layer's estimate at the same time (their indexes),
    each layer once, the answers in the order of the layers."""
    import threading

    from sources.layer import Layer, estimate_layers
    both = threading.Barrier(2, timeout=30)  # broken (an error) when the layers are asked one after another
    calls = []

    class Fake(Layer):
        def __init__(self, n):
            self.n = n

        def estimate(self, grid, cache_dir, update):
            calls.append(self.n)
            both.wait()
            return self.n, 0, float(self.n)

    one, two = Fake(1), Fake(2)
    assert estimate_layers([two, one, two], None, "cache") == [(2, 0, 2.0), (1, 0, 1.0), (2, 0, 2.0)]
    assert sorted(calls) == [1, 2]


def _batch_profiles(n: int, rng) -> "sh.Profiles":
    """A helpers.Profiles of n lines as lineprofiles.line_profiles gives one: 2-30 points each,
    some without data, over water or a filled gap, a missing min_nmpt."""
    import helpers as sh
    counts = rng.integers(2, 30, n)
    offsets = np.concatenate([[0], np.cumsum(counts)]).astype(np.int64)
    total = int(offsets[-1])
    d = np.round(rng.random(total) * 500, 1)
    z = np.round(rng.normal(400, 50, total), 2)
    s = np.round(z + rng.random(total) * 3, 2)
    z[rng.random(total) < 0.02] = np.nan
    w = (rng.random(total) < 0.3).astype(np.uint8)
    g = (rng.random(total) < 0.1).astype(np.uint8)
    small = np.column_stack([np.round(rng.random(n) * 500, 1), np.round(rng.random(n) * 50, 2),
                             np.round(rng.random(n) * 500, 1), np.round(rng.random(n) * 50, 2),
                             np.round(rng.random(n) * 500, 1), np.round(rng.random(n) * 90, 2),
                             np.round(rng.random(n) * 100, 1), np.round(rng.random(n) * 100, 1)])
    small[rng.random(n) < 0.3, 2:4] = np.nan
    flags = np.zeros(n, dtype=np.int64)
    for k, (lo, hi) in enumerate(zip(offsets[:-1].tolist(), offsets[1:].tolist())):
        flags[k] = (1 if w[lo:hi].any() else 0) | (2 if g[lo:hi].any() else 0) | (4 if np.isnan(z[lo:hi]).any() else 0)
    return sh.Profiles(offsets, d, z, s, w, g, small, flags)


def test_saved_by_children_as_in_process(tmp_path, monkeypatch):
    """saving.py: the line files of a run written by child processes (one per file, or the
    results' apart from the map's) are byte for byte those save_results and save_map write in
    one process, for 50 000 lines with the profiles of a batch, of a batch with an end zone and
    a lift ("zone", "lift"), the A-frame heights of a run with those options, profiles that
    are dicts, lines without one and values hard to round; the children's progress reaches the Compute bars
    "saving results" and "saving the map" with the lines as their totals; the hand-over folder is
    removed; a failing child raises RuntimeError naming its file."""
    import os
    from shapely.geometry import Point
    import mapping as mp
    import runs as rn
    import saving
    from progress import progress

    class Area:
        center = (50.0, 19.1)

        @staticmethod
        def shape_wgs84():
            return Point(19.1, 50.0).buffer(0.01)

    rng = np.random.default_rng(7)
    n = 50_000
    lines = _fake_lines(n)
    hard = np.array(HARD_FLOATS)
    for shift, name in enumerate(["length", "clearance", "clearance_nmpt", "height_max", "high_pct", "prom1", "drop2"]):
        lines.columns[name][:len(hard)] = np.roll(hard, shift)
    lines.columns["anchor1"][:len(hard)] = np.column_stack([np.roll(hard, 1), np.roll(hard, -2)])
    # a run with --end-zone and --anchor-lift: the A-frame heights of every line, hard ones among them
    lines.columns["lift_needed"] = np.round(rng.random(n) * 2, 3)
    lines.columns["lift_no_zone"] = lines.columns["lift_needed"] + rng.random(n) * 5
    lines.columns["lift_no_zone"][:len(hard)] = np.roll(hard, 3)
    batch = _batch_profiles(n, rng)
    zoned = _batch_profiles(n, rng)  # a search with --end-zone and --anchor-lift: the zone of each line, the lift
    zoned.zone, zoned.lift = np.round(np.minimum(5.0, rng.random(n) * 30), 1), 2.0
    lines.profiles = {k: (zoned if k % 3 == 0 else batch)[k] for k in range(n) if k % 7}
    assert "zone" in lines.profiles[3].as_dict() and "zone" not in lines.profiles[1].as_dict()
    lines.profiles[7] = {"d": [0.0, -0.0, 1e300], "z": [float("nan"), None], "name": "Żabi"}
    members = rng.permutation(n).astype(np.int64)
    start = np.concatenate([[0], np.sort(rng.integers(0, n + 1, 3000)), [n]]).astype(np.int64)
    rep = np.array([members[rng.integers(a, b)] if b > a else n + g for g, (a, b) in enumerate(zip(start[:-1], start[1:]))],
                   dtype=np.int64)
    groups = mp.Groups(rep, members, start)
    meta = {"id": "r", "name": "Żabi Koń „ß”", "created": "2026-10-31T10:00:00+00:00", "summary": {"lines": n},
            "attribution": [], "source": {"id": "files"}, "params": {"x": 1.5, "end_zone": 5, "anchor_lift": 2},
            "data": [{"file": "C:/a/b.tif"}]}
    one = tmp_path / "one"
    one.mkdir()
    rn.save_results(str(one), lines, groups, meta)
    mp.save_map(lines, Area, str(one), str(tmp_path / "runs"), meta, "EPSG:2180")
    files = ("lines.csv", "lines.geojson", "data.js", "lines.js", "run.json", "ATTRIBUTION.txt", "map.html")
    assert sorted(os.listdir(one)) == sorted(files)

    work = tmp_path / "work"
    for count in (4, 2):
        folder = tmp_path / f"children{count}"
        folder.mkdir()
        heads = mp.map_heads(Area, str(folder / "map.html"), meta, "EPSG:2180")
        states = []
        progress.subscribe(states.append)
        try:
            saving.save(str(work), str(folder), lines, groups, meta, heads, saving.plan(count),
                        lambda: rn.save_results(str(folder), lines, groups, meta, files=("ATTRIBUTION.txt", "run.json")))
        finally:
            progress.unsubscribe(states.append)
        mp.save_map(lines, Area, str(folder), str(tmp_path / "runs"), meta, "EPSG:2180", files=("map.html",))
        for name in files:
            assert (folder / name).read_bytes() == (one / name).read_bytes(), (count, name)
        assert b"lift_no_zone_m" in (folder / "lines.csv").read_bytes()
        assert b'"ends":["lift_needed","lift_no_zone"]' in (folder / "lines.js").read_bytes()
        assert sorted(os.listdir(folder)) == sorted(files) and not (work / saving.FOLDER).exists()
        # by the stage: after a test's progress.bars() the Compute bar's label is "" (its finally)
        bars = [(s["stage"], s["count"], s["total"], s["done"]) for s in states if s["stage"].startswith("saving")]
        assert [b for b in bars if b[3]] == [("saving results", n, n, True), ("saving the map", n, n, True)]
        for stage in ("saving results", "saving the map"):
            counts = [c for name, c, total, done in bars if name == stage and not done]
            assert counts and counts == sorted(counts) and 0 <= counts[0] and counts[-1] <= n, stage
    assert saving.plan(1) == [] and saving.plan(2) == [saving.RESULT_FILES, saving.MAP_FILES]
    assert saving.plan(3, map_files=False) == [("lines.csv",), ("lines.geojson",)] and len(saving.plan(4)) == 4
    assert [saving.processes(t) for t in (1, 2, 3, 4, 24)] == [1, 2, 2, 4, 4]
    with pytest.raises(RuntimeError, match="saving lines"):  # the run folder missing: every child fails
        saving.save(str(work), str(tmp_path / "missing"), lines, groups, meta, heads, [("lines.csv",), ("lines.js",)],
                    lambda: None)
    assert not (work / saving.FOLDER).exists()
