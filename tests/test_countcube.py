"""The counter cube of a country (countcube.py): keys, bins, the tile counter against a brute-force
count, spots merged over tiles, the levels, filters and the cube's cells, corners and requests."""
import json
import os
import subprocess
import sys
from collections import Counter, defaultdict

import numpy as np
import pytest
import shapely
from pyproj import Transformer
from shapely.geometry import shape

import countcube as cc
import helpers as sh
from grid import Grid

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CRS = "EPSG:8353"  # S-JTSK [JTSK03] / Krovak East North: negative coordinates
ORIGIN = (-560000.0, -1240000.0)


def _grid(left=-559000.0, top=-1230000.0, res=2.0, size=4000):
    return Grid(left=left, top=top, res=res, width=size, height=size, crs=CRS)


def _lines(rng, grid, n, max_px=600, nan_share=0.1, lengths=(20, 5200)):
    """A synthetic LineTable of n lines with random anchors, values and NaNs."""
    a1 = rng.integers(0, grid.height, size=(n, 2))
    a2 = np.clip(a1 + rng.integers(-max_px, max_px + 1, size=(n, 2)), 0, grid.height - 1)
    c = {"a1": a1.astype(np.int64), "a2": a2.astype(np.int64)}
    for name in sh.LINE_VALUES:
        c[name] = rng.uniform(-5, 120, n)
    c["length"] = rng.uniform(*lengths, n)
    c["angle1"], c["angle2"] = rng.uniform(0, 95, n), rng.uniform(0, 95, n)  # never below the first edge
    # values on the edges, so the bins' edges are hit
    edges = np.array([e for v in cc.EDGES.values() for e in v], dtype=float)
    for name in ("prom1", "prom2", "clearance", "height_max", "angle1", "angle2", "length"):
        on = rng.random(n) < 0.2
        choices = np.array(cc.LENGTH_EDGES, dtype=float) if name == "length" else edges
        c[name][on] = rng.choice(choices, on.sum())
    for name in ("prom1", "prom2", "clearance_nmpt", "height_max", "angle1"):
        c[name][rng.random(n) < nan_share] = np.nan
    c["water_px"] = rng.integers(0, 3, n) * (rng.random(n) < 0.3)
    return sh.LineTable(c)


def _bin(value, edges):
    """One value's bin, plainly."""
    if value != value:
        return cc.UNKNOWN
    b = 0
    for k, e in enumerate(edges):
        if value >= e:
            b = k
    return b


def _length_bin(length):
    for k in range(cc.LENGTH_BINS):
        if length < cc.LENGTH_EDGES[k + 1]:
            return max(k, 0) if length >= cc.LENGTH_EDGES[0] else 0
    return cc.LENGTH_BINS - 1


def _record(row):
    """One line's record, field by field."""
    rec = 1 << (0 + (row["water_px"] > 0))
    rec |= 1 << (2 + (row["clearance_nmpt"] <= 0))
    rec |= _bin(row["height_max"], cc.EDGES["height"]) << 4
    rec |= _bin(row["clearance"], cc.EDGES["clearance"]) << 7
    wall = np.nan if np.isnan(row["angle1"]) or np.isnan(row["angle2"]) else max(row["angle1"], row["angle2"])
    rec |= _bin(wall, cc.EDGES["wall"]) << 10
    prom = np.nan if np.isnan(row["prom1"]) or np.isnan(row["prom2"]) else min(row["prom1"], row["prom2"])
    rec |= _bin(prom, cc.EDGES["prominence"]) << 13
    rec |= 1 << (16 + _length_bin(row["length"]))
    return rec


def _merge(a, b):
    """Two records of one spot merged, field by field."""
    out = (a | b) & cc.OR_MASK
    for name, shift in cc.SHIFT.items():
        x, y = (a >> shift) & 7, (b >> shift) & 7
        if name == "wall":
            x, y = (8 if x == 7 else x), (8 if y == 7 else y)
            m = min(x, y)
            m = 7 if m == 8 else m
        else:
            x, y = (-1 if x == 7 else x), (-1 if y == 7 else y)
            m = max(x, y)
            m = 7 if m == -1 else m
        out |= m << shift
    return out


def _brute(grid, table, origin, core, lengths, last):
    """Lines per key and spot records per id, line by line."""
    lines, spots, dropped = Counter(), {}, 0
    for k in range(len(table)):
        row = {name: table.columns[name][k] for name in table.columns}
        x1, y1 = (float(v) for v in grid.pixel_to_xy(row["a1"][0], row["a1"][1]))
        x2, y2 = (float(v) for v in grid.pixel_to_xy(row["a2"][0], row["a2"][1]))
        fx, fy = min((x1, y1), (x2, y2))
        ok = lengths[0] <= row["length"] and (row["length"] <= lengths[1] if last else row["length"] < lengths[1])
        if core is not None:
            ok = ok and core[0] <= fx < core[2] and core[1] <= fy < core[3]
        if not ok:
            dropped += 1
            continue
        rec = _record(row)
        i, j = int((fx - origin[0]) // 1000), int((fy - origin[1]) // 1000)
        lines[(i << 39) | (j << 25) | rec] += 1
        c1 = (int((x1 - origin[0]) // 50), int((y1 - origin[1]) // 50))
        c2 = (int((x2 - origin[0]) // 50), int((y2 - origin[1]) // 50))
        p, q = min(c1, c2), max(c1, c2)
        sid = (p[0] << 35) | (p[1] << 16) | ((q[0] - p[0]) << 8) | (q[1] - p[1] + 128)
        spots[sid] = _merge(spots[sid], rec) if sid in spots else rec
    return lines, spots, dropped


def test_keys_pack_and_unpack():
    rng = np.random.default_rng(1)
    i, j = rng.integers(0, 1 << 14, 1000), rng.integers(0, 1 << 14, 1000)
    rec = rng.integers(0, 1 << 25, 1000)
    keys = cc.pack_keys(i, j, rec)
    assert keys.max() < 1 << 53
    f = cc.unpack_keys(keys)
    assert (f["i"] == i).all() and (f["j"] == j).all() and (f["record"] == rec).all()
    assert (f["water"] == rec & 3).all() and (f["trees"] == (rec >> 2) & 3).all()
    assert (f["height"] == (rec >> 4) & 7).all() and (f["clearance"] == (rec >> 7) & 7).all()
    assert (f["wall"] == (rec >> 10) & 7).all() and (f["prominence"] == (rec >> 13) & 7).all()
    assert (f["length"] == (rec >> 16) & 511).all()
    with pytest.raises(ValueError):
        cc.pack_keys(np.array([-1]), np.array([0]), np.array([0]))
    with pytest.raises(ValueError):
        cc.pack_keys(np.array([0]), np.array([1 << 14]), np.array([0]))


def test_bins_at_the_edges():
    edges = cc.EDGES["prominence"]  # 0, 5, 10, 20, 50
    values = np.array([-3, 0, 4.999, 5, 5.001, 10, 19.9, 20, 50, 1e9, np.nan])
    assert cc._bin(values, edges).tolist() == [0, 0, 0, 1, 1, 2, 2, 3, 4, 4, cc.UNKNOWN]
    lengths = np.array([30, 59.99, 60, 299, 300, 1000, 2999, 3000, 4999.9, 5000])
    assert cc.length_bin(lengths).tolist() == [0, 0, 1, 3, 4, 6, 7, 8, 8, 8]
    for name, e in cc.EDGES.items():
        assert len(e) <= cc.UNKNOWN and list(e) == sorted(e), name


def test_origin_of():
    assert cc.origin_of((-559000.0, -1239000.0, 0, 0)) == (-560000.0, -1240000.0)
    assert cc.origin_of((16000.0, 8000.0, 0, 0)) == (16000.0, 8000.0)


@pytest.mark.parametrize("core,last", [(None, False), ((-557000.0, -1235000.0, -553000.0, -1231000.0), True)])
def test_tile_counter_against_brute_force(core, last, monkeypatch):
    rng = np.random.default_rng(7)
    grid = _grid()
    monkeypatch.setattr(cc, "PENDING_MAX", 3000)  # reduced again on the way
    counter = cc.TileCounter(grid, ORIGIN, core, (100, 3000), last)
    tables = [_lines(rng, grid, n) for n in (5000, 0, 1, 4000, 2500)]
    for t in tables:
        counter(t)
    result = counter.result()
    lines, spots, dropped = Counter(), {}, 0
    for t in tables:
        if not len(t):
            continue
        a, b, d = _brute(grid, t, ORIGIN, core, (100, 3000), last)
        lines.update(a)
        dropped += d
        for sid, rec in b.items():
            spots[sid] = cc.merge_spots(np.array([sid, sid]), np.array([spots[sid], rec]))[1][0] \
                if sid in spots else rec
    assert dict(zip(result.line_keys.tolist(), result.line_counts.tolist())) == dict(lines)
    assert (np.diff(result.line_keys) > 0).all() and (np.diff(result.spot_ids) > 0).all()
    assert dict(zip(result.spot_ids.tolist(), result.spot_records.tolist())) == spots
    assert result.lines == sum(lines.values()) and result.dropped == dropped
    assert result.lines + result.dropped == sum(len(t) for t in tables)
    assert 0 < result.lines < sum(len(t) for t in tables)


def test_merge_matches_the_plain_merge_and_is_commutative():
    rng = np.random.default_rng(3)
    ids = rng.integers(0, 50, 3000)
    recs = cc.line_records({**{name: rng.uniform(-5, 120, 3000) for name in sh.LINE_VALUES},
                            "water_px": rng.integers(0, 2, 3000)})
    recs[rng.random(3000) < 0.1] |= 7 << 13  # UNKNOWN prominence
    u, m = cc.merge_spots(ids, recs)
    plain = {}
    for sid, rec in zip(ids.tolist(), recs.tolist()):
        plain[sid] = _merge(plain[sid], rec) if sid in plain else rec
    assert dict(zip(u.tolist(), m.tolist())) == plain
    for _ in range(5):
        order = rng.permutation(len(ids))
        u2, m2 = cc.merge_spots(ids[order], recs[order])
        assert (u2 == u).all() and (m2 == m).all()
    half = len(ids) // 2  # partial merges merged again
    a, b = cc.merge_spots(ids[:half], recs[:half]), cc.merge_spots(ids[half:], recs[half:])
    u3, m3 = cc.merge_spots(np.concatenate([b[0], a[0]]), np.concatenate([b[1], a[1]]))
    assert (u3 == u).all() and (m3 == m).all()
    # UNKNOWN only when every line's is
    unknown = 7 << 13
    assert (cc.merge_spots(np.array([1, 1]), np.array([unknown, 2 << 13]))[1][0] >> 13) & 7 == 2
    assert (cc.merge_spots(np.array([1, 1]), np.array([unknown, unknown]))[1][0] >> 13) & 7 == 7
    assert (cc.merge_spots(np.array([1, 1]), np.array([7 << 10, 3 << 10]))[1][0] >> 10) & 7 == 3


def _counts(grid, table, core=None, lengths=(30, 5000), last=True):
    counter = cc.TileCounter(grid, ORIGIN, core, lengths, last)
    counter(table)
    return counter.result()


def test_save_and_load_tile(tmp_path):
    rng = np.random.default_rng(5)
    grid = _grid()
    counts = _counts(grid, _lines(rng, grid, 1000))
    path = str(tmp_path / "t.npz")
    cc.save_tile(path, counts, {"band": "S", "tile": "E0_N0", "lines": counts.lines})
    back, meta = cc.load_tile(path)
    assert meta == {"band": "S", "tile": "E0_N0", "lines": counts.lines}
    for name in ("line_keys", "line_counts", "spot_ids", "spot_records"):
        assert (getattr(back, name) == getattr(counts, name)).all() and getattr(back, name).dtype == np.int64
    assert (back.lines, back.dropped) == (counts.lines, counts.dropped)
    assert os.listdir(tmp_path) == ["t.npz"]
    np.savez_compressed(path, version=np.int64(cc.VERSION + 1), meta=np.array("{}"))
    with pytest.raises(ValueError, match="version"):
        cc.load_tile(path)


def _build(tmp_path, tables, name="cube"):
    """A cube of tiles (grid, table, core[, lengths, last]) with its area.geojson: a part of the
    grid's extent."""
    paths = []
    for k, (grid, table, core, *band) in enumerate(tables):
        path = str(tmp_path / f"tile{k}.npz")
        cc.save_tile(path, _counts(grid, table, core, *band), {})
        paths.append(path)
    out = tmp_path / name
    to = Transformer.from_crs(CRS, "EPSG:4326", always_xy=True)
    lon0, lat0, lon1, lat1 = to.transform_bounds(-559000.0, -1238000.0, -551000.0, -1230000.0)
    info = {"id": "test", "name": "Test", "crs": CRS, "origin": list(ORIGIN), "bounds_wgs84": [lon0, lat0, lon1, lat1],
            "bands": [{"name": "S", "lengths": [30, 300], "layer": True, "params": {"max_length": 300, "resolution": 1.0}},
                      {"name": "M2", "lengths": [1000, 2000], "layer": False, "params": {"max_length": 2000}}]}
    cube = cc.build(paths, str(out), info)
    outline = shapely.Polygon([(-559000, -1238000), (-555000, -1238000), (-551000, -1234000), (-551000, -1230000),
                               (-559000, -1230000)])
    back = shapely.transform(outline, lambda xy: np.column_stack(to.transform(xy[:, 0], xy[:, 1])))
    (out / "area.geojson").write_text(json.dumps({"type": "Feature", "properties": {},
                                                 "geometry": json.loads(shapely.to_geojson(back))}))
    return out, cube


def test_build_counts_shared_spots_once_and_sums_levels(tmp_path):
    rng = np.random.default_rng(11)
    grid = _grid()
    table = _lines(rng, grid, 6000, lengths=(30, 300))
    # two tiles and two bands: (30, 150) and [150, 300] in each
    left, right = (-559000.0, -1238000.0, -555000.0, -1230000.0), (-555000.0, -1238000.0, -551000.0, -1230000.0)
    tiles = [(grid, table, core, lengths, last) for core in (left, right)
             for lengths, last in (((30, 150), False), ((150, 300), True))]
    out, cube = _build(tmp_path, tiles)
    whole = _counts(grid, table, (left[0], left[1], right[2], right[3]), (30, 300), True)
    lines = np.load(out / "lines_1.npy")
    assert lines.dtype == np.int64 and lines.shape[1] == 2 and (np.diff(lines[:, 0]) > 0).all()
    assert (lines[:, 0] == whole.line_keys).all() and (lines[:, 1] == whole.line_counts).all()
    # spots of lines whose anchors lie in both tiles: once, as in the counts of one grid
    i, j = cc.spot_cells(whole.spot_ids)
    keys, counts = cc.count_keys(cc.pack_keys(i, j, whole.spot_records))
    spots = np.load(out / "spots_1.npy")
    assert (spots[:, 0] == keys).all() and (spots[:, 1] == counts).all()
    assert cube["totals"]["lines"] == whole.lines and cube["totals"]["spots"] == len(whole.spot_ids)
    parts = [_counts(*tile) for tile in tiles]
    assert len(np.intersect1d(parts[0].spot_ids, parts[1].spot_ids))  # a spot with lines in both bands
    assert cube["totals"]["spots"] < sum(len(p.spot_ids) for p in parts)
    for mode in ("lines", "spots"):
        base = np.load(out / f"{mode}_1.npy")
        for level in (2, 4, 8):
            rows = np.load(out / f"{mode}_{level}.npy")
            assert (np.diff(rows[:, 0]) > 0).all()
            expected = Counter()
            for key, n in base.tolist():
                i, j, rec = key >> 39, (key >> 25) & 0x3FFF, key & ((1 << 25) - 1)
                expected[((i // level) << 39) | ((j // level) << 25) | rec] += n
            assert dict(zip(rows[:, 0].tolist(), rows[:, 1].tolist())) == dict(expected)
            assert rows[:, 1].sum() == base[:, 1].sum()
            assert cube["totals"]["keys"][f"{mode}_{level}"] == len(rows)
    saved = json.loads((out / "cube.json").read_text())
    assert saved == cube and saved["version"] == cc.VERSION and saved["id"] == "test"
    assert saved["edges"]["length"] == list(cc.LENGTH_EDGES) and saved["levels"] == [1, 2, 4, 8]
    assert saved["built"].endswith("Z") and saved["cell_m"] == 1000


def _random_filters(rng):
    lo, hi = sorted(rng.choice(len(cc.LENGTH_EDGES), 2, replace=False))
    return cc.Filters(length=(cc.LENGTH_EDGES[lo], cc.LENGTH_EDGES[hi]),
                      prominence=float(rng.choice(cc.EDGES["prominence"])),
                      wall=None if rng.random() < 0.3 else float(rng.choice(cc.EDGES["wall"])),
                      clearance=float(rng.choice(cc.EDGES["clearance"])) if rng.random() < 0.5 else 0,
                      height=float(rng.choice(cc.EDGES["height"])) if rng.random() < 0.5 else 0,
                      trees=str(rng.choice(cc.TREES)), water=str(rng.choice(cc.WATERS)))


def _passes(row, length, f):
    """One line's values against filters, as the viewer's filters do (unknown prominence fails)."""
    lo, hi = f.length
    if not lo <= length <= hi or (length == hi and hi != cc.LENGTH_EDGES[-1]):
        return False
    prom = np.minimum(row["prom1"], row["prom2"])  # NaN when either is
    if f.prominence and not prom >= f.prominence:
        return False
    if f.wall is not None and not np.maximum(row["angle1"], row["angle2"]) < f.wall:
        return False
    if f.clearance and not row["clearance"] >= f.clearance:
        return False
    if f.height and not row["height_max"] >= f.height:
        return False
    over = row["clearance_nmpt"] <= 0
    if (f.trees == "no" and over) or (f.trees == "only" and not over):
        return False
    wet = row["water_px"] > 0
    return not ((f.water == "land" and wet) or (f.water == "water" and not wet))


def test_select_against_the_values():
    rng = np.random.default_rng(13)
    grid = _grid()
    table = _lines(rng, grid, 3000, lengths=(30, 5000))
    keys = cc.pack_keys(np.zeros(len(table), dtype=np.int64), np.zeros(len(table), dtype=np.int64),
                        cc.line_records(table.columns))
    for _ in range(200):
        f = _random_filters(rng)
        mask = cc.select(keys, f)
        expected = [_passes({n: table.columns[n][k] for n in table.columns}, table.columns["length"][k], f)
                    for k in range(len(table))]
        assert mask.tolist() == expected, f
    assert cc.select(keys, cc.Filters()).all()


def test_filters_parse():
    f = cc.Filters.parse({"length": "60-1000", "prominence": "10", "wall": "45", "clearance": "2", "height": "",
                          "trees": "no", "water": "land", "mode": "spots", "bbox": "1,2,3,4"})
    assert f == cc.Filters(length=(60, 1000), prominence=10, wall=45, clearance=2, trees="no", water="land")
    assert cc.Filters.parse({}) == cc.Filters()
    for query, text in [({"length": "61-1000"}, "length"), ({"length": "1000-60"}, "length"),
                        ({"length": "60"}, "length"), ({"prominence": "7"}, "prominence"),
                        ({"wall": "31"}, "wall"), ({"clearance": "x"}, "number"), ({"height": "nan"}, "number"),
                        ({"trees": "maybe"}, "trees"), ({"water": "sea"}, "water")]:
        with pytest.raises(ValueError, match=text):
            cc.Filters.parse(query)


def test_cube_cells_against_brute_force(tmp_path):
    rng = np.random.default_rng(17)
    grid = _grid()
    table = _lines(rng, grid, 8000, lengths=(30, 300))
    out, _ = _build(tmp_path, [(grid, table, None)])
    cube = cc.Cube(str(out))
    for mode in ("lines", "spots"):
        for level in cc.LEVELS:
            rows = np.load(out / f"{mode}_{level}.npy")
            for _ in range(25):
                f = _random_filters(rng)
                x = sorted(rng.uniform(-561000, -549000, 2))
                y = sorted(rng.uniform(-1240000, -1228000, 2))
                box = None if rng.random() < 0.2 else (x[0], y[0], x[1], y[1])
                expected = defaultdict(int)
                passing = cc.select(rows[:, 0], f).tolist()  # select itself: test_select_against_the_values
                for (key, n), ok in zip(rows.tolist(), passing):
                    i, j = key >> 39, (key >> 25) & 0x3FFF
                    size = level * 1000
                    inside = box is None or (ORIGIN[0] + (i + 1) * size > box[0] and ORIGIN[0] + i * size <= box[2]
                                             and ORIGIN[1] + (j + 1) * size > box[1]
                                             and ORIGIN[1] + j * size <= box[3])
                    if inside and ok:
                        expected[(i, j)] += n
                i, j, n = cube.cells(mode, level, box, f)
                assert dict(zip(zip(i.tolist(), j.tolist()), n.tolist())) == {k: v for k, v in expected.items() if v}
    with pytest.raises(ValueError):
        cube.cells("groups", 1, None, cc.Filters())
    with pytest.raises(ValueError):
        cube.cells("lines", 3, None, cc.Filters())
    i, j, n = cube.cells("lines", 1, (0.0, 0.0, 1000.0, 1000.0), cc.Filters())
    assert len(i) == 0


def test_select_skip():
    """select(skip=<dimension>) leaves that dimension's condition out: the mask of the same filters with
    that dimension off; another name is refused."""
    rng = np.random.default_rng(31)
    grid = _grid()
    table = _lines(rng, grid, 3000, lengths=(30, 5000))
    keys = cc.pack_keys(np.zeros(len(table), dtype=np.int64), np.zeros(len(table), dtype=np.int64),
                        cc.line_records(table.columns))
    off = {"length": {"length": (30, 5000)}, "prominence": {"prominence": 0}, "wall": {"wall": None},
           "clearance": {"clearance": 0}, "height": {"height": 0}}
    for _ in range(100):
        f = _random_filters(rng)
        assert (cc.select(keys, f, skip=None) == cc.select(keys, f)).all()
        for name, args in off.items():
            relaxed = cc.Filters(**{**f.__dict__, **args})
            assert (cc.select(keys, f, skip=name) == cc.select(keys, relaxed)).all(), (f, name)
            assert (cc.select(keys, f, skip=name) | ~cc.select(keys, f)).all()  # never stricter
    with pytest.raises(ValueError, match="skip"):
        cc.select(keys, cc.Filters(), skip="trees")


def test_cube_histogram_against_brute_force(tmp_path):
    """Cube.histogram: per row the bins read from the key and the counts summed with the row's own
    dimension dropped from the filters; the total is the cells' sum; the lines' length bins partition
    the total, the spots' sum to at least it."""
    rng = np.random.default_rng(37)
    grid = _grid()
    table = _lines(rng, grid, 8000, lengths=(30, 5000))
    out, _ = _build(tmp_path, [(grid, table, None)])
    cube = cc.Cube(str(out))
    off = {"length": {"length": (30, 5000)}, "prominence": {"prominence": 0}, "wall": {"wall": None},
           "clearance": {"clearance": 0}, "height": {"height": 0}}
    for mode in ("lines", "spots"):
        for level in cc.LEVELS:
            rows = np.load(out / f"{mode}_{level}.npy")
            for _ in range(15):
                f = _random_filters(rng)
                x = sorted(rng.uniform(-561000, -549000, 2))
                y = sorted(rng.uniform(-1240000, -1228000, 2))
                box = None if rng.random() < 0.2 else (x[0], y[0], x[1], y[1])
                size = level * 1000
                expected = {"total": 0, "length": [0] * cc.LENGTH_BINS,
                            **{name: [0] * 6 for name in ("prominence", "wall", "clearance", "height")}}
                relaxed = {name: cc.Filters(**{**f.__dict__, **args}) for name, args in off.items()}
                for key, n in rows.tolist():
                    i, j = key >> 39, (key >> 25) & 0x3FFF
                    inside = box is None or (ORIGIN[0] + (i + 1) * size > box[0] and ORIGIN[0] + i * size <= box[2]
                                             and ORIGIN[1] + (j + 1) * size > box[1]
                                             and ORIGIN[1] + j * size <= box[3])
                    if not inside:
                        continue
                    one = np.array([key])
                    if cc.select(one, f)[0]:
                        expected["total"] += n
                    if cc.select(one, relaxed["length"])[0]:
                        for k in range(cc.LENGTH_BINS):
                            if key & (1 << (16 + k)):
                                expected["length"][k] += n
                    for name, shift in (("prominence", 13), ("wall", 10), ("clearance", 7), ("height", 4)):
                        if cc.select(one, relaxed[name])[0]:
                            b = (key >> shift) & 7
                            expected[name][5 if b == cc.UNKNOWN else b] += n
                got = cube.histogram(mode, level, box, f)
                assert got == expected, (mode, level, f, box)
                assert isinstance(got["total"], int)
                assert all(isinstance(v, int) for name in off for v in got[name])
                assert got["total"] == int(cube.cells(mode, level, box, f)[2].sum())
                # the length bins are counted with the length filter off: a line's one bit partitions that
                # total (the view's total when the filter is off), a spot's ORed bits sum to at least it
                relaxed_total = cube.histogram(mode, level, box, relaxed["length"])["total"]
                assert relaxed_total >= got["total"]
                if mode == "lines":
                    assert sum(got["length"]) == relaxed_total
                    if f.length == (30, 5000):
                        assert sum(got["length"]) == got["total"]
                else:
                    assert sum(got["length"]) >= relaxed_total
    with pytest.raises(ValueError):
        cube.histogram("groups", 1, None, cc.Filters())
    empty = cube.histogram("lines", 1, (0.0, 0.0, 1000.0, 1000.0), cc.Filters())
    assert empty == {"total": 0, "length": [0] * 9, "prominence": [0] * 6, "wall": [0] * 6, "clearance": [0] * 6,
                     "height": [0] * 6}


def test_cube_histogram_of_a_view(tmp_path):
    """Cube.histogram with a WGS84 view: the histogram of the keys whose cell's corners (rounded as
    /cells rounds them) have a box intersecting the view, edges included: the cells the page counts in
    view, fewer than the view's box in the cube's CRS holds; reaching gives that mask."""
    rng = np.random.default_rng(41)
    grid = _grid()
    table = _lines(rng, grid, 6000, lengths=(30, 5000))
    out, _ = _build(tmp_path, [(grid, table, None)])
    cube = cc.Cube(str(out))
    west, south, east, north = cube.info["bounds_wgs84"]
    fewer = 0
    for mode in ("lines", "spots"):
        for level in cc.LEVELS:
            rows = np.load(out / f"{mode}_{level}.npy")
            keys, counts = rows[:, 0], rows[:, 1]
            for _ in range(8):
                f = _random_filters(rng)
                lon = sorted(rng.uniform(west, east, 2))
                lat = sorted(rng.uniform(south, north, 2))
                view = (lon[0], lat[0], lon[1], lat[1])
                box = cube.box(*view)
                corners = np.round(cube.corners(level, keys >> 39, (keys >> 25) & 0x3FFF), 6)
                la, lo = corners[:, :, 0], corners[:, :, 1]
                near = ((la.max(1) >= view[1]) & (la.min(1) <= view[3]) & (lo.max(1) >= view[0])
                        & (lo.min(1) <= view[2]))
                assert (cube.reaching(level, keys, view, 6) == near).all()
                got = cube.histogram(mode, level, box, f, view=view, decimals=6)
                # the brute force: the histogram of the near keys alone, through a cube of those rows
                part = cc.Cube.__new__(cc.Cube)
                part.__dict__.update(cube.__dict__)
                part._arrays = {f"{mode}_{level}": rows[near]}
                assert got == part.histogram(mode, level, None, f), (mode, level, view, f)
                if got["total"] < cube.histogram(mode, level, box, f)["total"]:
                    fewer += 1
                assert got["total"] == int(counts[near][cc.select(keys[near], f)].sum())
    assert fewer > 0  # the CRS box holds more than the view somewhere
    assert cube.reaching(1, np.zeros(0, dtype=np.int64), (0, 0, 1, 1)).shape == (0,)


def test_outline_simplified(tmp_path):
    """The outline for a map: valid, fewer coordinates than the original, within the country's bounds (plus
    the tolerance), the original's km², kept per tolerance."""
    rng = np.random.default_rng(41)
    grid = _grid()
    out, _ = _build(tmp_path, [(grid, _lines(rng, grid, 10, lengths=(30, 300)), None)])
    # a wiggly outline: the plain one's edges every 20 m with noise of 1 m, about 1600 points
    cube = cc.Cube(str(out))
    to_crs = Transformer.from_crs("EPSG:4326", CRS, always_xy=True)
    to_wgs84 = Transformer.from_crs(CRS, "EPSG:4326", always_xy=True)
    local = shapely.transform(cube.outline(), lambda xy: np.column_stack(to_crs.transform(xy[:, 0], xy[:, 1])))
    dense = shapely.segmentize(local, 20.0)
    xy = shapely.get_coordinates(dense) + rng.uniform(-1, 1, (shapely.get_num_coordinates(dense), 2))
    xy[-1] = xy[0]  # the ring closed
    dense = shapely.Polygon(xy)
    back = shapely.transform(dense, lambda xy: np.column_stack(to_wgs84.transform(xy[:, 0], xy[:, 1])))
    (out / "area.geojson").write_text(json.dumps({"type": "Feature", "properties": {},
                                                 "geometry": json.loads(shapely.to_geojson(back))}))
    cube = cc.Cube(str(out))
    original = cube.outline()
    assert shapely.get_num_coordinates(original) > 1000
    found = cube.outline_simplified()
    assert found["tolerance"] == cc.OUTLINE_TOLERANCE
    assert cube.outline_simplified() is found  # kept
    assert cube.outline_simplified(0.001) is not found and cube.outline_simplified(0.001)["tolerance"] == 0.001
    geometry = shape(found["geometry"])
    assert geometry.is_valid and geometry.geom_type in ("Polygon", "MultiPolygon")
    assert 4 <= shapely.get_num_coordinates(geometry) < shapely.get_num_coordinates(original) / 10
    json.dumps(found)
    rings = [geometry.exterior] if geometry.geom_type == "Polygon" else [p.exterior for p in geometry.geoms]
    for ring in rings:
        for x, y in ring.coords:
            assert round(x, 4) == x and round(y, 4) == y
    lon0, lat0, lon1, lat1 = cube.info["bounds_wgs84"]
    t = cc.OUTLINE_TOLERANCE + 1e-4
    assert geometry.bounds[0] >= lon0 - t and geometry.bounds[1] >= lat0 - t
    assert geometry.bounds[2] <= lon1 + t and geometry.bounds[3] <= lat1 + t
    assert found["area_km2"] > 0
    assert found["area_km2"] == pytest.approx(dense.area / 1e6, rel=0.01) == pytest.approx(56, rel=0.05)
    assert found["area_km2"] == round(found["area_km2"], 1)


def _lattice(cube, level):
    """The columns and rows of a level's cells over the outline's box."""
    size = level * cc.CELL_M
    left, bottom, right, top = cc._project(cube.outline(), cube._to_crs).bounds
    return (range(int((left - cube.origin[0]) // size), int((right - cube.origin[0]) // size) + 1),
            range(int((bottom - cube.origin[1]) // size), int((top - cube.origin[1]) // size) + 1))


def test_cut_cells(tmp_path):
    """Cube.cut against each cell cut alone, on an outline of a wiggly edge, a hole and an island: the same cells at
    every level, each with its km²; the km² of a level's whole and cut cells add up to the outline's; the shape to
    draw is the part inside within its simplification (a hole stays a hole), in [lat, lon]; kept; none without an
    outline."""
    rng = np.random.default_rng(42)
    grid = _grid()
    out, _ = _build(tmp_path, [(grid, _lines(rng, grid, 10, lengths=(30, 300)), None)])
    to_wgs84 = Transformer.from_crs(CRS, "EPSG:4326", always_xy=True)
    land = shapely.segmentize(shapely.Polygon([(-559000, -1238000), (-543000, -1238000), (-543000, -1226000),
                                               (-559000, -1226000)]), 50.0)
    xy = shapely.get_coordinates(land) + rng.uniform(-20, 20, (shapely.get_num_coordinates(land), 2))
    xy[-1] = xy[0]
    hole = shapely.Polygon([(-552300, -1233300), (-550700, -1233300), (-550700, -1231700), (-552300, -1231700)])
    island = shapely.Polygon([(-540500, -1236500), (-539300, -1236500), (-539300, -1235300), (-540500, -1235300)])
    local = shapely.MultiPolygon([shapely.Polygon(xy, [hole.exterior.coords]), island])
    assert local.is_valid
    back = shapely.transform(local, lambda xy: np.column_stack(to_wgs84.transform(xy[:, 0], xy[:, 1])))
    (out / "area.geojson").write_text(json.dumps({"type": "Feature", "properties": {},
                                                 "geometry": json.loads(shapely.to_geojson(back))}))
    cube = cc.Cube(str(out))
    assert cube.cut(1) is cube.cut(1)  # kept
    outline = cc._project(cube.outline(), cube._to_crs)
    to_crs = cube._to_crs
    for level in cube.levels:
        size = level * cc.CELL_M
        columns, rows = _lattice(cube, level)
        expected, whole = {}, 0
        for i in columns:
            for j in rows:
                x, y = cube.origin[0] + i * size, cube.origin[1] + j * size
                part = shapely.box(x, y, x + size, y + size).intersection(outline)
                if part.area >= size * size * cc.CUT_FULL:
                    whole += 1
                elif part.area > 0:
                    expected[i, j] = part
        found = cube.cut(level)
        assert set(found) == set(expected) and len(found) > 5
        for key, part in expected.items():
            assert found[key]["km2"] == pytest.approx(part.area / 1e6, abs=1.1e-6)
            polygons = [shapely.Polygon(rings[0], rings[1:])
                        for rings in ([[(lon, lat) for lat, lon in ring] for ring in polygon]
                                      for polygon in found[key]["shape"])]
            drawn = shapely.transform(shapely.MultiPolygon(polygons), lambda xy: np.column_stack(to_crs.transform(xy[:, 0], xy[:, 1])))
            assert drawn.area == pytest.approx(part.area, abs=part.length * size / cc.CUT_SIMPLIFY + 1)
        total = whole * size * size / 1e6 + sum(v["km2"] for v in found.values())
        assert total == pytest.approx(outline.area / 1e6, abs=1e-3)
    assert any(len(polygon) == 2 for v in cube.cut(8).values() for polygon in v["shape"]) \
        or any(len(v["shape"]) > 1 for v in cube.cut(8).values())  # the hole or the island within one cell
    json.dumps(list(cube.cut(1).values()))
    # an outline on the cells' edges cuts none at the coarse levels (an empty level), a corner at the finest
    square = shapely.Polygon([(-552000, -1232000), (-544000, -1232000), (-544000, -1224000), (-552000, -1224000.5)])
    back = shapely.transform(square, lambda xy: np.column_stack(to_wgs84.transform(xy[:, 0], xy[:, 1])))
    (out / "area.geojson").write_text(json.dumps({"type": "Feature", "properties": {},
                                                 "geometry": json.loads(shapely.to_geojson(back))}))
    assert isinstance(cc.Cube(str(out)).cut(8), dict)
    (out / "area.geojson").unlink()
    assert cc.Cube(str(out)).cut(1) == {}


def test_box_auto_level_and_corners(tmp_path):
    rng = np.random.default_rng(19)
    grid = _grid()
    out, _ = _build(tmp_path, [(grid, _lines(rng, grid, 100, lengths=(30, 300)), None)])
    cube = cc.Cube(str(out))
    to = Transformer.from_crs(CRS, "EPSG:4326", always_xy=True)
    i, j = np.array([0, 3, 7]), np.array([2, 0, 5])
    for level in cc.LEVELS:
        corners = cube.corners(level, i, j)
        assert corners.shape == (3, 4, 2)
        for k in range(3):
            x, y = ORIGIN[0] + i[k] * level * 1000.0, ORIGIN[1] + j[k] * level * 1000.0
            size = level * 1000.0
            for c, (cx, cy) in enumerate([(x, y), (x + size, y), (x + size, y + size), (x, y + size)]):
                lon, lat = to.transform(cx, cy)
                assert corners[k, c].tolist() == pytest.approx([lat, lon], abs=1e-9)
    lon0, lat0 = to.transform(-556000.0, -1236000.0)
    lon1, lat1 = to.transform(-552000.0, -1232000.0)
    box = cube.box(min(lon0, lon1), min(lat0, lat1), max(lon0, lon1), max(lat0, lat1))
    assert box[0] <= -556000 + 300 and box[2] >= -552000 - 300 and box[0] < box[2] and box[1] < box[3]
    assert cube.auto_level(box) == 1 and cube.auto_level(box, most=4) >= 2 and cube.auto_level(box, most=0) == 8
    assert cube.cell_count(1, (0.0, 0.0, 999.0, 999.0)) == 1
    far = cube.box(100, 10, 101, 11)  # far from the country: empty
    assert far[0] > far[2] and len(cube.cells("lines", 1, far, cc.Filters())[0]) == 0
    whole = cube.box(-540, -100, 540, 100)
    assert all(np.isfinite(whole))
    with pytest.raises(ValueError):
        cube.box(10, 50, 9, 51)


def test_cell_request(tmp_path):
    rng = np.random.default_rng(23)
    grid = _grid()
    out, _ = _build(tmp_path, [(grid, _lines(rng, grid, 100, lengths=(30, 300)), None)])
    cube = cc.Cube(str(out))
    to_crs = Transformer.from_crs("EPSG:4326", CRS, always_xy=True)
    outline = shapely.transform(cube.outline(), lambda xy: np.column_stack(to_crs.transform(xy[:, 0], xy[:, 1])))
    for level, i, j in [(1, 2, 3), (2, 4, 4), (1, 1, 2), (8, 0, 1)]:
        request = cc.cell_request(cube, "S", level, i, j)
        assert request["params"] == {"max_length": 300, "resolution": 1.0}
        geometry = request["geometry"]
        assert geometry["type"] in ("Polygon", "MultiPolygon")
        json.dumps(geometry)
        got = shapely.transform(shape(geometry), lambda xy: np.column_stack(to_crs.transform(xy[:, 0], xy[:, 1])))
        size = level * 1000.0
        x, y = ORIGIN[0] + i * size, ORIGIN[1] + j * size
        expected = shapely.box(x, y, x + size, y + size).buffer(300).intersection(outline)
        assert got.symmetric_difference(expected).area < 1e-3 * expected.area
        if (level, i, j) in ((1, 1, 2), (8, 0, 1)):  # at the outline's edge: cut by it
            assert got.area < 0.9 * shapely.box(x, y, x + size, y + size).buffer(300).area
    with pytest.raises(ValueError, match="band"):
        cc.cell_request(cube, "M2", 1, 2, 3)  # not in the layer
    with pytest.raises(ValueError, match="band"):
        cc.cell_request(cube, "X", 1, 2, 3)
    with pytest.raises(ValueError, match="outside"):
        cc.cell_request(cube, "S", 1, 100, 100)
    with pytest.raises(ValueError, match="outside"):
        cc.cell_request(cube, "S", 1, 7, 2)  # south-east of the outline's diagonal
    with pytest.raises(ValueError, match="level"):
        cc.cell_request(cube, "S", 3, 2, 3)


def test_cube_of_another_version(tmp_path):
    rng = np.random.default_rng(29)
    grid = _grid()
    out, _ = _build(tmp_path, [(grid, _lines(rng, grid, 10, lengths=(30, 300)), None)])
    meta = json.loads((out / "cube.json").read_text())
    (out / "cube.json").write_text(json.dumps({**meta, "version": cc.VERSION + 1}))
    with pytest.raises(ValueError, match="version"):
        cc.Cube(str(out))


def test_import_loads_no_search_code():
    code = (f"import json, sys; sys.path.insert(0, {REPO!r}); import countcube\n"
            "print(json.dumps(sorted(m for m in sys.modules if m.split('.')[0] in "
            "('numba', 'linesearch', 'search', 'country'))))")
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout.strip().splitlines()[-1]) == []
