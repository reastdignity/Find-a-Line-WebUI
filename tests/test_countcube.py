"""The counter cube of a country (countcube.py, cube v2): the two words of a key, the bins, the global
lattice (cells and clusters of known lon/lat, the origin's floor, the levels), the spot ids, the tile
counter against a brute-force count, merge_spots on word B and the split of a spot by its border, spots
merged over tiles, filters and histograms of every dimension against the values, the cube's cells,
corners, cut cells and requests, the border filter, the rows by side and the parts beyond the outline,
and a cube or tile of version 1 refused."""
import json
import math
import os
import subprocess
import sys
from collections import Counter, defaultdict

import numpy as np
import pytest
import shapely
from pyproj import Geod, Transformer
from shapely.geometry import shape

import countcube as cc
import helpers as sh
from grid import Grid

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CRS = "EPSG:8353"  # S-JTSK [JTSK03] / Krovak East North: negative coordinates
TO_WGS84 = Transformer.from_crs(CRS, "EPSG:4326", always_xy=True)
TO_CRS = Transformer.from_crs("EPSG:4326", CRS, always_xy=True)
GRID_BOUNDS = (-559000.0, -1238000.0, -551000.0, -1230000.0)  # the grid of _grid, in the CRS
ORIGIN = cc.origin_of(TO_WGS84.transform_bounds(*GRID_BOUNDS), 5000)
GEOD = Geod(ellps="WGS84")


def _grid(left=-559000.0, top=-1230000.0, res=2.0, size=4000):
    return Grid(left=left, top=top, res=res, width=size, height=size, crs=CRS)


def _on_edges(rng, values, edges, share=0.2):
    on = rng.random(len(values)) < share
    values[on] = rng.choice(np.asarray(edges, dtype=float), on.sum())


def _lines(rng, grid, n, max_px=600, nan_share=0.1, lengths=(20, 5200), lifts=True, borders=False):
    """A synthetic LineTable of n lines with random anchors, values (some on the bins' edges) and NaNs;
    the A-frame columns when `lifts`, border and partner when `borders`."""
    a1 = rng.integers(0, grid.height, size=(n, 2))
    a2 = np.clip(a1 + rng.integers(-max_px, max_px + 1, size=(n, 2)), 0, grid.height - 1)
    c = {"a1": a1.astype(np.int64), "a2": a2.astype(np.int64)}
    for name in sh.LINE_VALUES:
        c[name] = rng.uniform(-5, 120, n)
    c["length"] = rng.uniform(*lengths, n)
    c["angle1"], c["angle2"] = rng.uniform(0, 95, n), rng.uniform(0, 95, n)  # never below the first edge
    c["elev_a1"], c["elev_a2"] = rng.uniform(-20, 3200, n), rng.uniform(-20, 3200, n)  # beyond the top edges
    near = rng.random(n) < 0.4  # anchors of about one height, so the height difference's bins fill
    c["elev_a2"][near] = c["elev_a1"][near] + rng.uniform(-60, 60, near.sum())
    c["drop1"], c["drop2"] = rng.uniform(0, 300, n), rng.uniform(0, 300, n)
    c["high_pct"] = rng.uniform(0, 100, n)
    c["height_mean"] = rng.uniform(0, 250, n)
    edges = np.array([e for v in cc.EDGES.values() for e in v], dtype=float)
    for name in ("prom1", "prom2", "clearance", "clearance_nmpt", "height_max", "height_mean", "high_pct",
                 "angle1", "angle2", "drop1", "drop2", "elev_a1", "elev_a2"):
        _on_edges(rng, c[name], edges)
    _on_edges(rng, c["length"], cc.LENGTH_EDGES)
    for name in ("prom1", "prom2", "clearance_nmpt", "height_max", "angle1", "elev_a1", "drop2", "height_mean",
                 "high_pct"):
        c[name][rng.random(n) < nan_share] = np.nan
    c["water_px"] = rng.integers(0, 120, n) * (rng.random(n) < 0.3)
    if lifts:
        for name in ("lift_needed", "lift_no_zone"):
            c[name] = np.where(rng.random(n) < 0.5, 0.0, rng.uniform(0, 3, n))
            _on_edges(rng, c[name], cc.EDGES[name])
            c[name][rng.random(n) < nan_share] = np.nan
    if borders:
        c["border"] = rng.choice(np.array([0, 0, 0, 1, 2], dtype=np.uint8), n)
        c["partner"] = np.where(c["border"] > 0, rng.integers(1, 8, n), 0).astype(np.uint8)
    return sh.LineTable(c)


def _bin(value, edges, at_most=False):
    """One value's bin, plainly."""
    if value != value:
        return cc.UNKNOWN
    if at_most:
        return sum(1 for e in edges if value > e)
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


def _values(row, res):
    """The values of every dimension of one line, plainly (NaN where either anchor's is)."""
    def low(a, b):
        return np.nan if np.isnan(a) or np.isnan(b) else min(a, b)

    def high(a, b):
        return np.nan if np.isnan(a) or np.isnan(b) else max(a, b)

    return {"height": row["height_max"], "clearance": row["clearance"], "wall": high(row["angle1"], row["angle2"]),
            "prominence": low(row["prom1"], row["prom2"]), "water_m": row["water_px"] * res,
            "elevation_low": low(row["elev_a1"], row["elev_a2"]), "elevation_high": high(row["elev_a1"], row["elev_a2"]),
            "height_mean": row["height_mean"], "prominence_high": high(row["prom1"], row["prom2"]),
            "drop": low(row["drop1"], row["drop2"]), "high_pct": row["high_pct"],
            "height_diff": abs(row["elev_a1"] - row["elev_a2"]), "clearance_trees": row["clearance_nmpt"],
            "lift_needed": row.get("lift_needed", np.nan), "lift_no_zone": row.get("lift_no_zone", np.nan)}


def _record(row, res=2.0):
    """One line's record (word A's, word B), field by field."""
    rec = 1 << (0 + (row["water_px"] > 0))
    rec |= 1 << (2 + (row["clearance_nmpt"] <= 0))
    values = _values(row, res)
    for name, shift in (("height", 4), ("clearance", 7), ("wall", 10), ("prominence", 13)):
        rec |= _bin(values[name], cc.EDGES[name]) << shift
    rec |= 1 << (16 + _length_bin(row["length"]))
    rec |= int(row.get("border", 0)) << 25
    rec |= int(row.get("partner", 0)) << 27
    word = 0
    for k, name in enumerate(cc.B_FIELDS):
        word |= _bin(values[name], cc.EDGES[name], cc.KINDS[name] == "at_most") << (3 * k)
    return rec, word


def _merge(a, b):
    """Two records ((word A, word B)) of one spot merged, field by field."""
    def field(x, y, worst):
        x, y = (worst if x == 7 else x), (worst if y == 7 else y)
        m = max(x, y) if worst < 0 else min(x, y)
        return 7 if m == worst else m

    assert (a[0] >> 25) & 31 == (b[0] >> 25) & 31  # one border and partner a spot
    out = ((a[0] | b[0]) & cc.OR_MASK) | (a[0] & (31 << 25))
    for name, shift in cc.SHIFT.items():
        out |= field((a[0] >> shift) & 7, (b[0] >> shift) & 7, 8 if name == "wall" else -1) << shift
    word = 0
    for k, name in enumerate(cc.B_FIELDS):
        word |= field((a[1] >> 3 * k) & 7, (b[1] >> 3 * k) & 7, -1 if cc.KINDS[name] == "floor" else 8) << (3 * k)
    return out, word


def _lon_lat(grid, pixels):
    x, y = grid.pixel_to_xy(pixels[:, 0], pixels[:, 1])
    lon, lat = TO_WGS84.transform(x, y)
    return np.asarray(lon), np.asarray(lat)


def _brute(grid, table, origin, core, lengths, last):
    """Lines per key and spot records per (id, border, partner), line by line, the cell by the
    contract's formula: floor(lon × 120) - I0 of the first anchor by (lon, lat); a line across a border
    (its border not 0) skips the core's test (search.count_tile hands it to the tile that owns it)."""
    lines, spots, dropped = Counter(), {}, 0
    lon1, lat1 = _lon_lat(grid, table.columns["a1"])
    lon2, lat2 = _lon_lat(grid, table.columns["a2"])
    for k in range(len(table)):
        row = {name: table.columns[name][k] for name in table.columns}
        x1, y1 = (float(v) for v in grid.pixel_to_xy(row["a1"][0], row["a1"][1]))
        x2, y2 = (float(v) for v in grid.pixel_to_xy(row["a2"][0], row["a2"][1]))
        fx, fy = min((x1, y1), (x2, y2))
        ok = lengths[0] <= row["length"] and (row["length"] <= lengths[1] if last else row["length"] < lengths[1])
        if core is not None and not int(row.get("border", 0)):
            ok = ok and core[0] <= fx < core[2] and core[1] <= fy < core[3]
        if not ok:
            dropped += 1
            continue
        rec = _record(row, grid.res)
        flon, flat = min((lon1[k], lat1[k]), (lon2[k], lat2[k]))
        i, j = math.floor(flon * 120) - origin[0], math.floor(flat * 120) - origin[1]
        lines[((i << 46) | (j << 30) | rec[0], rec[1])] += 1
        c1 = (math.floor(lon1[k] * 2400) - 20 * origin[0], math.floor(lat1[k] * 2400) - 20 * origin[1])
        c2 = (math.floor(lon2[k] * 2400) - 20 * origin[0], math.floor(lat2[k] * 2400) - 20 * origin[1])
        p, q = min(c1, c2), max(c1, c2)
        sid = ((p[0] << 42) | (p[1] << 22) | ((q[0] - p[0]) << 11) | (q[1] - p[1] + 1024), (rec[0] >> 25) & 31)
        spots[sid] = _merge(spots[sid], rec) if sid in spots else rec
    return lines, spots, dropped


def test_keys_pack_and_unpack():
    rng = np.random.default_rng(1)
    i, j = rng.integers(0, 1 << 16, 1000), rng.integers(0, 1 << 16, 1000)
    rec = np.column_stack([rng.integers(0, 1 << 30, 1000), rng.integers(0, 1 << 33, 1000)])
    keys = cc.pack_keys(i, j, rec)
    assert keys.shape == (1000, 2) and keys.dtype == np.int64 and keys[:, 0].max() < 1 << 62
    f = cc.unpack_keys(keys)
    assert (f["i"] == i).all() and (f["j"] == j).all() and (f["record"] == rec[:, 0]).all()
    a = rec[:, 0]
    assert (f["water"] == a & 3).all() and (f["trees"] == (a >> 2) & 3).all()
    assert (f["height"] == (a >> 4) & 7).all() and (f["clearance"] == (a >> 7) & 7).all()
    assert (f["wall"] == (a >> 10) & 7).all() and (f["prominence"] == (a >> 13) & 7).all()
    assert (f["length"] == (a >> 16) & 511).all()
    assert (f["border"] == (a >> 25) & 3).all() and (f["partner"] == (a >> 27) & 7).all()
    for k, name in enumerate(cc.B_FIELDS):
        assert (f[name] == (rec[:, 1] >> 3 * k) & 7).all(), name
    assert cc.B_BITS == 33 and set(cc.B_FIELDS) | set(cc.SHIFT) == set(cc.KINDS) == set(cc.EDGES)
    with pytest.raises(ValueError):
        cc.pack_keys(np.array([-1]), np.array([0]), np.array([[0, 0]]))
    with pytest.raises(ValueError):
        cc.pack_keys(np.array([0]), np.array([1 << 16]), np.array([[0, 0]]))


def test_bins_at_the_edges():
    edges = cc.EDGES["prominence"]  # 0, 5, 10, 20, 50
    values = np.array([-3, 0, 4.999, 5, 5.001, 10, 19.9, 20, 50, 1e9, np.nan])
    assert cc._bin(values, edges).tolist() == [0, 0, 0, 1, 1, 2, 2, 3, 4, 4, cc.UNKNOWN]
    lifts = np.array([0.0, -0.0, 1e-9, 0.5, 0.50001, 1, 1.4, 1.5, 2, 2.0001, 7, np.nan])
    assert cc.bin_of("lift_needed", lifts).tolist() == [0, 0, 1, 1, 2, 2, 3, 3, 4, 5, 5, cc.UNKNOWN]
    assert cc.bins_of("lift_needed") == 6 and cc.bins_of("height_diff") == 5
    lengths = np.array([30, 59.99, 60, 299, 300, 1000, 2999, 3000, 4999.9, 5000])
    assert cc.length_bin(lengths).tolist() == [0, 0, 1, 3, 4, 6, 7, 8, 8, 8]
    for name, e in cc.EDGES.items():
        assert cc.bins_of(name) < cc.UNKNOWN and list(e) == sorted(e), name
    # the bins by comparisons are searchsorted's (lower edges: side right less one, at least 0; upper: side left)
    rng = np.random.default_rng(8)
    values = np.concatenate([rng.uniform(-100, 3000, 20000), [np.nan, -np.inf, np.inf]])
    for name, e in cc.EDGES.items():
        values[:200] = rng.choice(np.asarray(e, dtype=float), 200)
        edges = np.asarray(e, dtype=float)
        lower = np.maximum(np.searchsorted(edges, values, side="right") - 1, 0)
        upper = np.searchsorted(edges, values, side="left")
        for got, plain in ((cc._bin(values, e), lower), (cc._bin_at_most(values, e), upper)):
            plain[np.isnan(values)] = cc.UNKNOWN
            assert (got == plain).all() and got.dtype == np.int64, name


def test_line_records_field_by_field():
    """line_records against _record line by line; absent A-frame columns are UNKNOWN, absent border and
    partner 0."""
    rng = np.random.default_rng(2)
    grid = _grid()
    for lifts, borders in ((True, True), (False, False)):
        table = _lines(rng, grid, 2000, lifts=lifts, borders=borders)
        records = cc.line_records(table.columns, grid.res)
        assert records.shape == (2000, 2) and records.dtype == np.int64
        for k in range(len(table)):
            row = {name: table.columns[name][k] for name in table.columns}
            assert tuple(records[k].tolist()) == _record(row, grid.res), k
        f = cc.unpack_keys(cc.pack_keys(np.zeros(2000), np.zeros(2000), records))
        if not lifts:
            assert (f["lift_needed"] == cc.UNKNOWN).all() and (f["lift_no_zone"] == cc.UNKNOWN).all()
            assert (f["border"] == 0).all() and (f["partner"] == 0).all()
        else:
            assert set(f["border"].tolist()) == {0, 1, 2} and set(f["lift_needed"].tolist()) >= {0, 1, 4, 5, 7}


def test_origin_of():
    """The south-west corner less the reach, floored to a multiple of 8 cells: an anchor the reach
    beyond the box lies in the cube; the origin on the lattice of every country."""
    for bounds, reach in (((16.83, 47.73, 22.57, 49.61), 5000), ((-122.9, 49.0, -114.0, 60.0), 5000),
                          ((172.6, -47.3, 178.6, -34.4), 3000), ((10.0, 79.0, 30.0, 81.0), 5000),
                          ((19.0, 49.0, 19.5, 49.5), 0)):
        i0, j0 = cc.origin_of(bounds, reach)
        assert isinstance(i0, int) and isinstance(j0, int) and i0 % 8 == 0 and j0 % 8 == 0
        west, south = bounds[0], bounds[1]
        pole = max(abs(bounds[1]), abs(bounds[3]))
        assert i0 / 120 <= west and j0 / 120 <= south
        assert west * 120 - i0 < 8 + 1.05 * reach / (111000 * math.cos(math.radians(pole + 0.1))) * 120 + 1
        assert south * 120 - j0 < 8 + 1.05 * reach / 110000 * 120 + 1
        # the reach beyond the box's corners on the ellipsoid lies east and north of the origin
        if reach:
            for lat in (bounds[1], bounds[3]):
                lon, _, _ = GEOD.fwd(west, lat, 270, reach)
                assert lon > i0 / 120
            _, lat, _ = GEOD.fwd(west, south, 180, reach)
            assert lat > j0 / 120
    assert cc.origin_of((16.83, 47.73, 22.57, 49.61), 0) == (2016, 5720)  # 16.8°, 47.667°
    assert cc.origin_of((16.83, 47.73, 22.57, 49.61), 5000) == (2008, 5720)


@pytest.mark.parametrize("engine", ["numba", "numpy"])
def test_lattice_of_known_points(engine):
    """The cells and clusters of points of known lon/lat on a grid of WGS84 itself: the cell of a line is
    its first anchor's by (lon, lat), whatever the pixel order; a spot's clusters are 1/2400°."""
    origin = (2160, 5880)  # 18°, 49°
    res = 1 / 9600  # four pixels a cluster
    grid = Grid(left=18.0, top=49.5, res=res, width=4800, height=4800, crs="EPSG:4326")

    def pixel(lon, lat):
        return [round((49.5 - lat) / res - 0.5), round((lon - 18.0) / res - 0.5)]

    # (anchor 1, anchor 2) in degrees: the pixel's centre lies 1/19200° inside the cluster
    q = 1 / 19200
    pairs = [((18.2 + q, 49.3 + q), (18.21 + q, 49.29 + q)),   # the first by lon is anchor 1
             ((18.25 + q, 49.21 + q), (18.24 + q, 49.4 + q)),  # anchor 2, north of it
             ((18.3 + q, 49.2 + q), (18.3 + q, 49.1 + q))]     # one lon: the smaller lat
    a1 = np.array([pixel(*p[0]) for p in pairs], dtype=np.int64)
    a2 = np.array([pixel(*p[1]) for p in pairs], dtype=np.int64)
    n = len(pairs)
    columns = {"a1": a1, "a2": a2, **{name: np.full(n, 10.0) for name in sh.LINE_VALUES}, "water_px": np.zeros(n)}
    columns["length"] = np.full(n, 100.0)
    counter = cc.TileCounter(grid, origin, None, (30, 300), False, engine=engine)
    counter(sh.LineTable(columns))
    counts = counter.result()
    f = cc.unpack_keys(counts.line_keys)
    first = [min(p) for p in pairs]
    expected = sorted((math.floor(lon * 120) - 2160, math.floor(lat * 120) - 5880) for lon, lat in first)
    assert sorted(zip(f["i"].tolist(), f["j"].tolist())) == expected
    assert expected == [(24, 36), (28, 48), (36, 12)]
    ids = counts.spot_ids
    for (p1, p2) in pairs:
        c1 = (math.floor(p1[0] * 2400) - 20 * 2160, math.floor(p1[1] * 2400) - 20 * 5880)
        c2 = (math.floor(p2[0] * 2400) - 20 * 2160, math.floor(p2[1] * 2400) - 20 * 5880)
        p, r = min(c1, c2), max(c1, c2)
        assert ((p[0] << 42) | (p[1] << 22) | ((r[0] - p[0]) << 11) | (r[1] - p[1] + 1024)) in ids.tolist()
    i, j = cc.spot_cells(ids)
    assert sorted(zip(i.tolist(), j.tolist())) == expected  # here the first anchor's cluster is p
    with pytest.raises(ValueError, match="outside the cube"):
        cc.TileCounter(grid, (2200, 5880), None, (30, 300), False, engine=engine)(sh.LineTable(columns))


def test_spot_ids_span():
    """dx of 11 bits (0..2047) and dy + 1024 (-1024..1023): a line spanning more is refused plainly."""
    cx = np.array([0, 5, 100, 100], dtype=np.int64)
    cy = np.array([2000, 3000, 2000, 3500], dtype=np.int64)
    ids = cc.cluster_spot_ids(cx, cy, cx + np.array([2047, 0, 0, 3]), cy + np.array([-1024, 1023, -5, 0]))
    assert ((ids >> 11) & 2047).tolist() == [2047, 0, 0, 3]
    assert ((ids & 2047) - 1024).tolist() == [-1024, 1023, 5, 0]  # p is the smaller (cx, cy): dy 5 for the third
    assert ((ids >> 42) & cc.SPOT_C_MASK).tolist() == [0, 5, 100, 100]
    assert ((ids >> 22) & cc.SPOT_C_MASK).tolist() == [2000, 3000, 1995, 3500]
    for dx, dy in ((2048, 0), (0, 1024), (5, -1025)):
        with pytest.raises(ValueError, match="spans"):
            cc.cluster_spot_ids(np.array([10]), np.array([2000]), np.array([10 + dx]), np.array([2000 + dy]))
    lon = np.array([18.0, 18.0 + 2047 / 2400])
    assert len(cc.spot_ids(lon[:1], np.array([49.0]), lon[1:], np.array([49.0]), (2152, 5872))) == 1


@pytest.mark.parametrize("engine", ["numba", "numpy"])
@pytest.mark.parametrize("core,last", [(None, False), ((-557000.0, -1235000.0, -553000.0, -1231000.0), True)])
def test_tile_counter_against_brute_force(core, last, engine, monkeypatch):
    rng = np.random.default_rng(7)
    grid = _grid()
    monkeypatch.setattr(cc, "PENDING_MAX", 3000)  # reduced again on the way
    import countkernels as ck
    for name in ("GROW_LINES", "GROW_SPOTS", "GROW_PIXELS"):  # the hash tables grown on the way
        monkeypatch.setattr(ck, name, 16)
    counter = cc.TileCounter(grid, ORIGIN, core, (100, 3000), last, engine=engine)
    tables = [_lines(rng, grid, n, borders=True) for n in (5000, 0, 1, 4000)] + [_lines(rng, grid, 2500, lifts=False)]
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
            spots[sid] = _merge(spots[sid], rec) if sid in spots else rec
    assert dict(zip(map(tuple, result.line_keys.tolist()), result.line_counts.tolist())) == dict(lines)
    order = np.lexsort((result.line_keys[:, 1], result.line_keys[:, 0]))
    assert (order == np.arange(len(order))).all() and len(np.unique(result.line_keys, axis=0)) == len(order)
    bp = (result.spot_records[:, 0] >> 25) & 31
    assert (np.lexsort((bp, result.spot_ids)) == np.arange(len(bp))).all()
    got = {(sid, b): tuple(rec) for sid, b, rec in zip(result.spot_ids.tolist(), bp.tolist(),
                                                     result.spot_records.tolist())}
    assert len(got) == len(result.spot_ids) and got == spots
    assert result.lines == sum(lines.values()) and result.dropped == dropped
    assert result.lines + result.dropped == sum(len(t) for t in tables)
    assert 0 < result.lines < sum(len(t) for t in tables)
    assert counter.transform_seconds > 0
    assert len({b for _, b in spots}) > 5  # spots split by border and partner


def test_anchors_transformed_once_per_tile():
    """TileCounter.anchors over parts with a1 in runs (as the count hands them) and without: each line's
    lon, lat and clusters as pyproj gives them pixel by pixel; a pixel seen in an earlier part is not
    transformed again, and the pixels kept are sorted and distinct."""
    rng = np.random.default_rng(6)
    grid = _grid()
    counter = cc.TileCounter(grid, ORIGIN, None, (30, 5000), True)
    calls = []
    transform = counter._transformer.transform
    counter._transformer = type("Counting", (), {"transform": lambda self, x, y: (calls.append(len(x)),
                                                                                   transform(x, y))[1]})()
    pool = rng.integers(0, grid.height, size=(3000, 2))
    seen = set()
    for runs in (True, False, True, True):
        n = 4000
        a1 = pool[np.sort(rng.integers(0, 3000, n // 8)).repeat(8)] if runs else pool[rng.integers(0, 3000, n)]
        a2 = pool[rng.integers(0, 3000, n)]
        (lon1, lat1, cx1, cy1), (lon2, lat2, cx2, cy2) = counter.anchors(a1, a2)
        for a, lon, lat, cx, cy in ((a1, lon1, lat1, cx1, cy1), (a2, lon2, lat2, cx2, cy2)):
            x, y = grid.pixel_to_xy(a[:, 0], a[:, 1])
            elon, elat = TO_WGS84.transform(x, y)
            assert (lon == elon).all() and (lat == elat).all()
            ecx, ecy = cc.clusters_of(elon, elat, ORIGIN)
            assert (cx == ecx).all() and (cy == ecy).all()
        codes = {int(r) * grid.width + int(c) for r, c in np.concatenate([a1, a2])}
        assert calls[-1] == len(codes - seen) if codes - seen else True
        seen |= codes
    assert sum(calls) == len(seen) and (np.diff(counter._codes) > 0).all() and len(counter._codes) == len(seen)


def test_engines_count_alike(monkeypatch):
    """The engines numba (hash tables, grown from tiny ones) and numpy give the same counts, byte for byte,
    over parts with and without the optional columns, a1 in runs and not, and a core; the numba engine
    transforms each pixel of the tile once."""
    import countkernels as ck
    for name in ("GROW_LINES", "GROW_SPOTS", "GROW_PIXELS"):
        monkeypatch.setattr(ck, name, 8)
    rng = np.random.default_rng(9)
    grid = _grid()
    core = (-558000.0, -1237000.0, -552000.0, -1231000.0)
    parts = []
    for k in range(6):
        table = _lines(rng, grid, 3000, max_px=300, lifts=k % 2 == 0, borders=k % 3 == 0)
        if k % 2:  # a1 in runs, as the count hands them
            order = np.lexsort((table.columns["a1"][:, 1], table.columns["a1"][:, 0]))
            table = sh.LineTable({name: np.asarray(v)[order] for name, v in table.columns.items()})
        parts.append(table)
    counters = {e: cc.TileCounter(grid, ORIGIN, core, (30, 3000), True, engine=e) for e in ("numba", "numpy")}
    seen = []
    transform = counters["numba"]._transform
    counters["numba"]._transform = lambda codes: (seen.append(codes.copy()), transform(codes))[1]
    for part in parts:
        for counter in counters.values():
            counter(part)
    a, b = counters["numba"].result(), counters["numpy"].result()
    for name in ("line_keys", "line_counts", "spot_ids", "spot_records"):
        x, y = getattr(a, name), getattr(b, name)
        assert x.dtype == y.dtype == np.int64 and x.shape == y.shape and np.array_equal(x, y), name
    assert (a.lines, a.dropped) == (b.lines, b.dropped) and 0 < a.lines < 18000
    codes = np.concatenate(seen)
    assert len(np.unique(codes)) == len(codes) and len(seen) > 1  # each pixel once, over several parts
    assert len(counters["numba"]._tables.line_a) > 8 and len(counters["numba"]._tables.spot_id) > 8  # grown
    with pytest.raises(ValueError, match="engine"):
        cc.TileCounter(grid, ORIGIN, core, (30, 3000), True, engine="pandas")


def test_merge_on_word_b_and_the_split_by_border():
    rng = np.random.default_rng(3)
    grid = _grid()
    n = 3000
    ids = rng.integers(0, 50, n)
    table = _lines(rng, grid, n, borders=True)
    recs = cc.line_records(table.columns, grid.res)
    u, m = cc.merge_spots(ids, recs)
    plain = {}
    for sid, rec in zip(ids.tolist(), map(tuple, recs.tolist())):
        key = (sid, (rec[0] >> 25) & 31)
        plain[key] = _merge(plain[key], rec) if key in plain else rec
    got = {(sid, (rec[0] >> 25) & 31): tuple(rec) for sid, rec in zip(u.tolist(), m.tolist())}
    assert got == plain and len(u) == len(plain) > 50  # some ids split into several spots
    for _ in range(5):
        order = rng.permutation(n)
        u2, m2 = cc.merge_spots(ids[order], recs[order])
        assert (u2 == u).all() and (m2 == m).all()
    half = n // 2  # partial merges merged again
    a, b = cc.merge_spots(ids[:half], recs[:half]), cc.merge_spots(ids[half:], recs[half:])
    u3, m3 = cc.merge_spots(np.concatenate([b[0], a[0]]), np.concatenate([b[1], a[1]]))
    assert (u3 == u).all() and (m3 == m).all()
    # a floor takes the largest bin, a ceiling the smallest, UNKNOWN only when every line's is
    one = np.array([1, 1])
    for name in cc.B_FIELDS:
        s = cc.B_SHIFT[name]
        merged = cc.merge_spots(one, np.array([[0, 2 << s], [0, 4 << s]]))[1][0, 1] >> s & 7
        assert merged == (4 if cc.KINDS[name] == "floor" else 2), name
        assert cc.merge_spots(one, np.array([[0, 7 << s], [0, 3 << s]]))[1][0, 1] >> s & 7 == 3
        assert cc.merge_spots(one, np.array([[0, 7 << s], [0, 7 << s]]))[1][0, 1] >> s & 7 == 7
    # one id with lines of two border values: two spots, each with its own lines' merge
    bp = np.array([[1 << 16 | 1 << 25 | 3 << 27, 0], [1 << 17 | 1 << 25 | 3 << 27, 0], [1 << 18 | 2 << 25, 0]])
    u4, m4 = cc.merge_spots(np.array([9, 9, 9]), bp)  # sorted by id, then by border | partner << 2
    assert u4.tolist() == [9, 9] and ((m4[:, 0] >> 25) & 3).tolist() == [2, 1]
    assert m4[0, 0] == (1 << 18 | 2 << 25) and m4[1, 0] == (3 << 16 | 1 << 25 | 3 << 27)


def test_sum_and_count_keys_of_wide_words():
    """The pairs sorted and reduced whatever their widths: one int64 sort when they fit, lexsort else."""
    rng = np.random.default_rng(4)
    for b_max in (1, 1 << 33, 1 << 62):
        a = rng.integers(0, 1 << 62, 40)[rng.integers(0, 40, 5000)]
        b = rng.integers(0, b_max, 30)[rng.integers(0, 30, 5000)]
        keys = np.column_stack([a, b])
        counts = rng.integers(1, 9, 5000)
        k, n = cc.sum_keys(keys, counts)
        expected = Counter()
        for row, c in zip(map(tuple, keys.tolist()), counts.tolist()):
            expected[row] += c
        assert dict(zip(map(tuple, k.tolist()), n.tolist())) == dict(expected)
        assert sorted(map(tuple, k.tolist())) == list(map(tuple, k.tolist()))
        k2, n2 = cc.count_keys(keys)
        assert dict(zip(map(tuple, k2.tolist()), n2.tolist())) == dict(Counter(map(tuple, keys.tolist())))
        assert (k2 == k).all()
    assert cc.count_keys(np.zeros((0, 2), dtype=np.int64))[0].shape == (0, 2)
    one = rng.integers(0, 50, 1000)  # keys of one word (cells, ids): as before
    k, n = cc.sum_keys(one, np.ones(1000, dtype=np.int64))
    assert (k == np.unique(one)).all() and (n == np.unique(one, return_counts=True)[1]).all()
    assert (cc.count_keys(one)[1] == n).all()


def _counts(grid, table, core=None, lengths=(30, 5000), last=True):
    counter = cc.TileCounter(grid, ORIGIN, core, lengths, last)
    counter(table)
    return counter.result()


def test_save_and_load_tile(tmp_path):
    rng = np.random.default_rng(5)
    grid = _grid()
    counts = _counts(grid, _lines(rng, grid, 1000, borders=True))
    path = str(tmp_path / "t.npz")
    cc.save_tile(path, counts, {"band": "S", "tile": "E0_N0", "lines": counts.lines})
    back, meta = cc.load_tile(path)
    assert meta == {"band": "S", "tile": "E0_N0", "lines": counts.lines}
    for name in ("line_keys", "line_counts", "spot_ids", "spot_records"):
        assert (getattr(back, name) == getattr(counts, name)).all() and getattr(back, name).dtype == np.int64
    assert back.line_keys.shape[1] == 2 and back.spot_records.shape[1] == 2
    assert (back.lines, back.dropped) == (counts.lines, counts.dropped)
    assert os.listdir(tmp_path) == ["t.npz"]
    for version in (1, cc.VERSION + 1):  # a tile of cube v1 (or another) is counted again
        np.savez_compressed(path, version=np.int64(version), meta=np.array("{}"))
        with pytest.raises(ValueError, match="version"):
            cc.load_tile(path)
    empty = cc.TileCounter(grid, ORIGIN, None, (30, 300), False).result()
    assert empty.line_keys.shape == (0, 2) and empty.spot_records.shape == (0, 2) and empty.lines == 0


def _outline_wgs84():
    to = Transformer.from_crs(CRS, "EPSG:4326", always_xy=True)
    outline = shapely.Polygon([(-559000, -1238000), (-555000, -1238000), (-551000, -1234000), (-551000, -1230000),
                               (-559000, -1230000)])
    return shapely.transform(shapely.segmentize(outline, 50.0),
                             lambda xy: np.column_stack(to.transform(xy[:, 0], xy[:, 1])))


def _build(tmp_path, tables, name="cube"):
    """A cube of tiles (grid, table, core[, lengths, last]) with its area.geojson: a part of the
    grid's extent."""
    paths = []
    for k, (grid, table, core, *band) in enumerate(tables):
        path = str(tmp_path / f"tile{k}.npz")
        cc.save_tile(path, _counts(grid, table, core, *band), {})
        paths.append(path)
    out = tmp_path / name
    lon0, lat0, lon1, lat1 = TO_WGS84.transform_bounds(*GRID_BOUNDS)
    info = {"id": "test", "name": "Test", "crs": CRS, "origin": [float(v) for v in ORIGIN],
            "bounds_wgs84": [lon0, lat0, lon1, lat1],
            "bands": [{"name": "S", "lengths": [30, 300], "layer": True, "params": {"max_length": 300, "resolution": 1.0}},
                      {"name": "M2", "lengths": [1000, 2000], "layer": False, "params": {"max_length": 2000}}]}
    cube = cc.build(paths, str(out), info)
    (out / "area.geojson").write_text(json.dumps({"type": "Feature", "properties": {},
                                                 "geometry": json.loads(shapely.to_geojson(_outline_wgs84()))}))
    return out, cube


def _rows(out, mode, level):
    rows = np.load(out / f"{mode}_{level}.npy")
    assert rows.dtype == np.int64 and rows.shape[1] == 3
    return rows


def _owned(grid, table, core):
    """The lines a tile's count hands its counter: those inside the country, and those across the border whose
    first anchor in pixel order lies in the core (a stand-in for the anchor in the country)."""
    import helpers as sh
    c = table.columns
    x1, y1 = grid.pixel_to_xy(c["a1"][:, 0], c["a1"][:, 1])
    x2, y2 = grid.pixel_to_xy(c["a2"][:, 0], c["a2"][:, 1])
    first = (x1 < x2) | ((x1 == x2) & (y1 <= y2))
    fx, fy = np.where(first, x1, x2), np.where(first, y1, y2)
    keep = (c["border"] == 0) | ((fx >= core[0]) & (fx < core[2]) & (fy >= core[1]) & (fy < core[3]))
    return sh.LineTable({name: column[keep] for name, column in c.items()})


def test_build_counts_shared_spots_once_and_sums_levels(tmp_path):
    rng = np.random.default_rng(11)
    grid = _grid()
    table = _lines(rng, grid, 6000, lengths=(30, 300), borders=True)
    c = table.columns  # lines of the same anchors in both bands: spots with lines in two bands
    for name in ("a1", "a2", "border", "partner"):
        c[name][3000:4000] = c[name][:1000]
    c["length"][:1000] = rng.uniform(30, 149, 1000)
    c["length"][3000:4000] = rng.uniform(150, 300, 1000)
    # two tiles and two bands: (30, 150) and [150, 300] in each
    left, right = (-559000.0, -1238000.0, -555000.0, -1230000.0), (-555000.0, -1238000.0, -551000.0, -1230000.0)
    # a line across a border reaches only the tile that owns it (search.count_tile): here the one holding its
    # first anchor in pixel order, as a line inside
    tiles = [(grid, _owned(grid, table, core), core, lengths, last) for core in (left, right)
             for lengths, last in (((30, 150), False), ((150, 300), True))]
    out, cube = _build(tmp_path, tiles)
    whole = _counts(grid, table, (left[0], left[1], right[2], right[3]), (30, 300), True)
    lines = _rows(out, "lines", 1)
    assert (np.lexsort((lines[:, 1], lines[:, 0])) == np.arange(len(lines))).all()
    assert (lines[:, :2] == whole.line_keys).all() and (lines[:, 2] == whole.line_counts).all()
    # spots of lines whose anchors lie in both tiles: once, as in the counts of one grid
    i, j = cc.spot_cells(whole.spot_ids)
    keys, counts = cc.count_keys(cc.pack_keys(i, j, whole.spot_records))
    spots = _rows(out, "spots", 1)
    assert (spots[:, :2] == keys).all() and (spots[:, 2] == counts).all()
    assert cube["totals"]["lines"] == whole.lines and cube["totals"]["spots"] == len(whole.spot_ids)
    parts = [_counts(*tile) for tile in tiles]
    assert len(np.intersect1d(parts[0].spot_ids, parts[1].spot_ids))  # a spot with lines in both bands
    assert cube["totals"]["spots"] < sum(len(p.spot_ids) for p in parts)
    for mode in ("lines", "spots"):
        base = _rows(out, mode, 1)
        for level in (2, 4, 8):
            rows = _rows(out, mode, level)
            assert (np.lexsort((rows[:, 1], rows[:, 0])) == np.arange(len(rows))).all()
            expected = Counter()
            for a, b, n in base.tolist():
                i, j, rec = a >> 46, (a >> 30) & 0xFFFF, a & ((1 << 30) - 1)
                expected[((i // level) << 46) | ((j // level) << 30) | rec, b] += n
            assert dict(zip(map(tuple, rows[:, :2].tolist()), rows[:, 2].tolist())) == dict(expected)
            assert rows[:, 2].sum() == base[:, 2].sum()
            assert cube["totals"]["keys"][f"{mode}_{level}"] == len(rows)
    saved = json.loads((out / "cube.json").read_text())
    assert saved == cube and saved["version"] == cc.VERSION == 2 and saved["id"] == "test"
    assert saved["edges"]["length"] == list(cc.LENGTH_EDGES) and saved["levels"] == [1, 2, 4, 8]
    assert set(saved["edges"]) == {"length"} | set(cc.KINDS) and saved["kinds"] == cc.KINDS
    assert saved["built"].endswith("Z") and saved["cell_deg"] == 1 / 120 and "cell_m" not in saved
    assert saved["origin"] == list(ORIGIN) and all(isinstance(v, int) for v in saved["origin"])
    assert saved["neighbours"] == [] and saved["clusters_per_cell"] == 20
    border = saved["totals"]["border"]
    f = cc.unpack_keys(lines[:, :2])
    assert border["lines"] == {"owned": int(lines[f["border"] == 1, 2].sum()),
                               "partner": int(lines[f["border"] == 2, 2].sum())}
    assert border["lines"]["owned"] > 0 and set(border["spots"]) == {"owned", "partner"}


def test_build_of_interior_tiles_has_zero_border_totals(tmp_path):
    rng = np.random.default_rng(12)
    grid = _grid()
    out, cube = _build(tmp_path, [(grid, _lines(rng, grid, 500, lengths=(30, 300)), None)])
    assert cube["totals"]["border"] == {"lines": {"owned": 0, "partner": 0}, "spots": {"owned": 0, "partner": 0}}
    empty = cc.build([], str(tmp_path / "empty"), {"origin": [1, 2]})
    assert empty["totals"]["lines"] == 0 and _rows(tmp_path / "empty", "lines", 1).shape == (0, 3)


def _random_filters(rng):
    lo, hi = sorted(rng.choice(len(cc.LENGTH_EDGES), 2, replace=False))
    args = {"length": (cc.LENGTH_EDGES[lo], cc.LENGTH_EDGES[hi]), "trees": str(rng.choice(cc.TREES)),
            "water": str(rng.choice(cc.WATERS))}
    for name, kind in cc.KINDS.items():
        if rng.random() < 0.5:
            args[name] = float(rng.choice(cc.EDGES[name]))
        elif kind != "floor":
            args[name] = None
    return cc.Filters(**args)


def _passes(row, f, res=2.0, skip=None):
    """One line's values against filters (unknown values fail every filter that is on)."""
    lo, hi = f.length
    length = row["length"]
    if skip != "length" and (not lo <= length <= hi or (length == hi and hi != cc.LENGTH_EDGES[-1])):
        return False
    values = _values(row, res)
    for name, kind in cc.KINDS.items():
        if name == skip or not f.active(name):
            continue
        limit, v = getattr(f, name), values[name]
        if kind == "floor" and not v >= limit:
            return False
        if kind == "below" and not v < limit:
            return False
        if kind == "at_most" and not v <= limit:
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
    keys = cc.pack_keys(np.zeros(len(table)), np.zeros(len(table)), cc.line_records(table.columns, grid.res))
    rows = [{n: table.columns[n][k] for n in table.columns} for k in range(len(table))]
    for _ in range(200):
        f = _random_filters(rng)
        assert cc.select(keys, f).tolist() == [_passes(row, f) for row in rows], f
    assert cc.select(keys, cc.Filters()).all()
    # every new dimension alone at each of its edges, against the values
    for name in cc.B_FIELDS:
        for edge in cc.EDGES[name]:
            f = cc.Filters(**{name: edge})
            mask = cc.select(keys, f)
            assert mask.tolist() == [_passes(row, f) for row in rows], (name, edge)
            if f.active(name):
                assert 0 < mask.sum() < len(rows), (name, edge)
    # the A-frame at 0: the lines that stand without A-frames, today's lines
    standing = cc.select(keys, cc.Filters(lift_needed=0, lift_no_zone=0))
    assert standing.tolist() == [row["lift_needed"] == 0 and row["lift_no_zone"] == 0 for row in rows]


def test_filters_parse():
    f = cc.Filters.parse({"length": "60-1000", "prominence": "10", "wall": "45", "clearance": "2", "height": "",
                          "trees": "no", "water": "land", "mode": "spots", "bbox": "1,2,3,4", "water_m": "20",
                          "elevation_low": "500", "elevation_high": "2000", "height_mean": "20",
                          "prominence_high": "50", "drop": "100", "high_pct": "75", "height_diff": "5",
                          "clearance_trees": "5", "lift_needed": "0", "lift_no_zone": "1.5"})
    assert f == cc.Filters(length=(60, 1000), prominence=10, wall=45, clearance=2, trees="no", water="land",
                           water_m=20, elevation_low=500, elevation_high=2000, height_mean=20, prominence_high=50,
                           drop=100, high_pct=75, height_diff=5, clearance_trees=5, lift_needed=0, lift_no_zone=1.5)
    assert cc.Filters.parse({}) == cc.Filters()
    assert not any(cc.Filters().active(name) for name in cc.KINDS)
    assert not cc.Filters(elevation_high=0, height_diff=0).active("height_diff")  # the first edge: off
    assert cc.Filters(lift_needed=0).active("lift_needed") and cc.Filters(wall=0).active("wall")
    for query, text in [({"length": "61-1000"}, "length"), ({"length": "1000-60"}, "length"),
                        ({"length": "60"}, "length"), ({"prominence": "7"}, "prominence"),
                        ({"wall": "31"}, "wall"), ({"clearance": "x"}, "number"), ({"height": "nan"}, "number"),
                        ({"trees": "maybe"}, "trees"), ({"water": "sea"}, "water"), ({"drop": "30"}, "drop"),
                        ({"lift_needed": "0.7"}, "lift_needed"), ({"height_diff": "inf"}, "number"),
                        ({"elevation_high": "300"}, "elevation_high")]:
        with pytest.raises(ValueError, match=text):
            cc.Filters.parse(query)


def _inside(cube, level, a, box):
    """Whether the key's cell (word A) touches a box (west, south, east, north in degrees), edges included
    within RANGE_EPSILON of a cell."""
    if box is None:
        return True
    i, j = a >> 46, (a >> 30) & 0xFFFF
    side = level / 120
    e = cc.RANGE_EPSILON * side
    west, south = (cube.origin[0] + i * level) / 120, (cube.origin[1] + j * level) / 120
    return west + side + e > box[0] and west - e <= box[2] and south + side + e > box[1] and south - e <= box[3]


def _random_box(rng, cube):
    west, south, east, north = cube.info["bounds_wgs84"]
    lon = sorted(rng.uniform(west - 0.02, east + 0.02, 2))
    lat = sorted(rng.uniform(south - 0.02, north + 0.02, 2))
    return None if rng.random() < 0.2 else (lon[0], lat[0], lon[1], lat[1])


def test_cube_cells_against_brute_force(tmp_path):
    rng = np.random.default_rng(17)
    grid = _grid()
    table = _lines(rng, grid, 8000, lengths=(30, 300))
    out, _ = _build(tmp_path, [(grid, table, None)])
    cube = cc.Cube(str(out))
    for mode in ("lines", "spots"):
        for level in cc.LEVELS:
            rows = _rows(out, mode, level)
            assert (cube.array(mode, level) == rows).all()
            for _ in range(25):
                f = _random_filters(rng)
                box = _random_box(rng, cube)
                expected = defaultdict(int)
                passing = cc.select(rows[:, :2], f).tolist()  # select itself: test_select_against_the_values
                for (a, b, n), ok in zip(rows.tolist(), passing):
                    if ok and _inside(cube, level, a, box):
                        expected[(a >> 46, (a >> 30) & 0xFFFF)] += n
                i, j, n = cube.cells(mode, level, box, f)
                assert dict(zip(zip(i.tolist(), j.tolist()), n.tolist())) == {k: v for k, v in expected.items() if v}
    with pytest.raises(ValueError):
        cube.cells("groups", 1, None, cc.Filters())
    with pytest.raises(ValueError):
        cube.cells("lines", 3, None, cc.Filters())
    i, j, n = cube.cells("lines", 1, (0.0, 0.0, 1.0, 1.0), cc.Filters())
    assert len(i) == 0


def test_select_skip():
    """select(skip=<dimension>) leaves that dimension's condition out: the mask of the same filters with
    that dimension off; another name is refused."""
    rng = np.random.default_rng(31)
    grid = _grid()
    table = _lines(rng, grid, 3000, lengths=(30, 5000))
    keys = cc.pack_keys(np.zeros(len(table)), np.zeros(len(table)), cc.line_records(table.columns, grid.res))
    off = {"length": {"length": (30, 5000)},
           **{name: {name: cc.EDGES[name][0] if kind == "floor" else None} for name, kind in cc.KINDS.items()}}
    assert set(off) == set(cc.DIMENSIONS)
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
    dimension dropped from the filters, every dimension of word A and word B; the total is the cells'
    sum; the lines' length bins partition the total, the spots' sum to at least it."""
    rng = np.random.default_rng(37)
    grid = _grid()
    table = _lines(rng, grid, 8000, lengths=(30, 5000), borders=True)
    out, _ = _build(tmp_path, [(grid, table, None)])
    cube = cc.Cube(str(out))
    off = {"length": {"length": (30, 5000)},
           **{name: {name: cc.EDGES[name][0] if kind == "floor" else None} for name, kind in cc.KINDS.items()}}
    for mode in ("lines", "spots"):
        for level in cc.LEVELS:
            rows = _rows(out, mode, level)
            for _ in range(10):
                f = _random_filters(rng)
                box = _random_box(rng, cube)
                expected = {"total": 0, "length": [0] * cc.LENGTH_BINS,
                            **{name: [0] * (cc.bins_of(name) + 1) for name in cc.KINDS}}
                relaxed = {name: cc.Filters(**{**f.__dict__, **args}) for name, args in off.items()}
                masks = {name: cc.select(rows[:, :2], r) for name, r in relaxed.items()}
                total = cc.select(rows[:, :2], f)
                fields = cc.unpack_keys(rows[:, :2])
                for k, (a, b, n) in enumerate(rows.tolist()):
                    if not _inside(cube, level, a, box):
                        continue
                    if total[k]:
                        expected["total"] += n
                    if masks["length"][k]:
                        for bit in range(cc.LENGTH_BINS):
                            if a & (1 << (16 + bit)):
                                expected["length"][bit] += n
                    for name in cc.KINDS:
                        if masks[name][k]:
                            v = int(fields[name][k])
                            expected[name][cc.bins_of(name) if v == cc.UNKNOWN else v] += n
                got = cube.histogram(mode, level, box, f)
                assert got == expected, (mode, level, f, box)
                assert isinstance(got["total"], int) and all(isinstance(v, int) for name in off for v in got[name])
                assert got["total"] == int(cube.cells(mode, level, box, f)[2].sum())
                relaxed_total = cube.histogram(mode, level, box, relaxed["length"])["total"]
                assert relaxed_total >= got["total"]
                if mode == "lines":
                    assert sum(got["length"]) == relaxed_total
                    for name in cc.KINDS:  # a line has one bin of each dimension
                        assert sum(got[name]) == cube.histogram(mode, level, box, relaxed[name])["total"]
                else:
                    assert sum(got["length"]) >= relaxed_total
    with pytest.raises(ValueError):
        cube.histogram("groups", 1, None, cc.Filters())
    empty = cube.histogram("lines", 1, (0.0, 0.0, 1.0, 1.0), cc.Filters())
    assert empty == {"total": 0, "length": [0] * 9, **{name: [0] * (cc.bins_of(name) + 1) for name in cc.KINDS}}
    assert len(empty["lift_needed"]) == 7 and len(empty["drop"]) == 6


def test_cube_histogram_of_a_view(tmp_path):
    """Cube.histogram with a WGS84 view: the histogram of the keys whose cell's corners (rounded as
    /cells rounds them) have a box intersecting the view, edges included; reaching gives that mask."""
    rng = np.random.default_rng(41)
    grid = _grid()
    table = _lines(rng, grid, 6000, lengths=(30, 5000))
    out, _ = _build(tmp_path, [(grid, table, None)])
    cube = cc.Cube(str(out))
    west, south, east, north = cube.info["bounds_wgs84"]
    for mode in ("lines", "spots"):
        for level in cc.LEVELS:
            rows = _rows(out, mode, level)
            keys, counts = rows[:, :2], rows[:, 2]
            for _ in range(8):
                f = _random_filters(rng)
                lon = sorted(rng.uniform(west, east, 2))
                lat = sorted(rng.uniform(south, north, 2))
                view = (lon[0], lat[0], lon[1], lat[1])
                box = cube.box(*view)
                assert box == view  # a box of the lattice is the view itself
                corners = np.round(cube.corners(level, keys[:, 0] >> 46, (keys[:, 0] >> 30) & 0xFFFF), 6)
                la, lo = corners[:, :, 0], corners[:, :, 1]
                near = ((la.max(1) >= view[1]) & (la.min(1) <= view[3]) & (lo.max(1) >= view[0])
                        & (lo.min(1) <= view[2]))
                assert (cube.reaching(level, keys, view, 6) == near).all()
                got = cube.histogram(mode, level, box, f, view=view, decimals=6)
                part = cc.Cube.__new__(cc.Cube)
                part.__dict__.update(cube.__dict__)
                part._arrays = {f"{mode}_{level}": (keys[near], counts[near])}
                assert got == part.histogram(mode, level, None, f), (mode, level, view, f)
                assert got["total"] == int(counts[near][cc.select(keys[near], f)].sum())
    assert cube.reaching(1, np.zeros((0, 2), dtype=np.int64), (0, 0, 1, 1)).shape == (0,)


def _with_border(rng, f):
    """Filters `f` with a random border (all or own) and random replaced partners."""
    replaced = tuple(sorted(int(p) for p in rng.choice(np.arange(1, 7), rng.integers(0, 3), replace=False)))
    return cc.Filters(**{**f.__dict__, "border": str(rng.choice(cc.BORDERS)), "replaced": replaced})


def test_border_filter_against_the_fields():
    """Filters.border and Filters.replaced against each line's border and partner columns: own keeps border 0 and 1,
    all every line but the partner lines (border 2) of a replaced partner; with the other filters, their mask and the
    border's; never skipped (select(skip=)); parsed from a query (replaced never), refused off its values."""
    rng = np.random.default_rng(43)
    grid = _grid()
    table = _lines(rng, grid, 4000, lengths=(30, 5000), borders=True)
    keys = cc.pack_keys(np.zeros(len(table)), np.zeros(len(table)), cc.line_records(table.columns, grid.res))
    border = np.asarray(table.columns["border"], dtype=np.int64)
    partner = np.asarray(table.columns["partner"], dtype=np.int64)
    assert {0, 1, 2} <= set(border.tolist()) and set(range(1, 8)) <= set(partner[border == 2].tolist())
    assert cc.select(keys, cc.Filters()).all() and cc.border_kept(keys, cc.Filters()) is None
    assert cc.select(keys, cc.Filters(border="own")).tolist() == (border != 2).tolist()
    for replaced in [(1,), (2, 5), (1, 2, 3, 4, 5, 6)]:
        expected = ~((border == 2) & np.isin(partner, replaced))
        assert cc.select(keys, cc.Filters(replaced=replaced)).tolist() == expected.tolist(), replaced
        assert cc.select(keys, cc.Filters(border="own", replaced=replaced)).tolist() == (border != 2).tolist()
    assert cc.select(keys, cc.Filters(replaced=(1, 2, 3, 4, 5, 6)))[(border == 2) & (partner == 7)].all()  # unknown kept
    for _ in range(100):
        f = _with_border(rng, _random_filters(rng))
        plain = cc.Filters(**{**f.__dict__, "border": "all", "replaced": ()})
        kept = (border != 2) if f.border == "own" else ~((border == 2) & np.isin(partner, f.replaced))
        assert (cc.select(keys, f) == (cc.select(keys, plain) & kept)).all(), f
        for name in cc.DIMENSIONS:
            assert not (cc.select(keys, f, skip=name) & ~kept).any(), (f, name)
    assert cc.Filters.parse({"border": "own", "replaced": "2"}) == cc.Filters(border="own")
    assert cc.Filters.parse({"border": ""}) == cc.Filters()
    for args, text in [({"border": "beyond"}, "border"), ({"replaced": (7,)}, "replaced"), ({"replaced": (0,)}, "replaced")]:
        with pytest.raises(ValueError, match=text):
            cc.Filters(**args)


def test_cube_cells_by_side_and_the_histogram_summary(tmp_path):
    """Cube.cells(sides=True): a row per cell and side (0 for the lines of border 0 and 1, the partner index for those
    of border 2) against the rows of the cube, in the order of the cells and then the sides, summing to cells()'s; the
    histogram's summary: both modes' totals (cells()'s) and the lines' split by their border field."""
    rng = np.random.default_rng(47)
    grid = _grid()
    table = _lines(rng, grid, 8000, lengths=(30, 300), borders=True)
    out, _ = _build(tmp_path, [(grid, table, None)])
    cube = cc.Cube(str(out))
    for mode in ("lines", "spots"):
        for level in cc.LEVELS:
            rows = _rows(out, mode, level)
            for _ in range(10):
                f = _with_border(rng, _random_filters(rng))
                box = _random_box(rng, cube)
                expected = defaultdict(int)
                for (a, b, n), ok in zip(rows.tolist(), cc.select(rows[:, :2], f).tolist()):
                    if ok and _inside(cube, level, a, box):
                        side = (a >> 27) & 7 if (a >> 25) & 3 == 2 else 0
                        expected[(a >> 46, (a >> 30) & 0xFFFF, side)] += n
                i, j, side, n = cube.cells(mode, level, box, f, sides=True)
                found = list(zip(i.tolist(), j.tolist(), side.tolist()))
                assert dict(zip(found, n.tolist())) == {k: v for k, v in expected.items() if v}, (mode, level, f)
                assert found == sorted(found)
                ci, cj, cn = cube.cells(mode, level, box, f)
                whole = defaultdict(int)
                for (a, b, _), v in zip(found, n.tolist()):
                    whole[a, b] += v
                assert dict(whole) == dict(zip(zip(ci.tolist(), cj.tolist()), cn.tolist()))
                got = cube.histogram(mode, level, box, f, summary=True)
                plain = cube.histogram(mode, level, box, f)
                assert {k: v for k, v in got.items() if k not in ("totals", "border")} == plain
                assert got["totals"] == {m: int(cube.cells(m, level, box, f)[2].sum()) for m in ("lines", "spots")}
                lines = _rows(out, "lines", level)
                split = [0, 0, 0]
                for (a, b, v), ok in zip(lines.tolist(), cc.select(lines[:, :2], f).tolist()):
                    if ok and _inside(cube, level, a, box):
                        split[(a >> 25) & 3] += v
                assert got["border"] == dict(zip(("interior", "owned", "partner"), split)), (mode, level, f)
    empty = cube.histogram("spots", 1, (0.0, 0.0, 1.0, 1.0), cc.Filters(), summary=True)
    assert empty["totals"] == {"lines": 0, "spots": 0} and empty["border"] == {"interior": 0, "owned": 0, "partner": 0}
    assert all(len(v) == 0 for v in cube.cells("lines", 1, (0.0, 0.0, 1.0, 1.0), cc.Filters(), sides=True))


def _oracle_filters():
    """The filters of the oracle's grid: none; each of the sixteen dimensions alone at every value that turns it on
    (the length at ranges of both ends and the middle); the flags; combinations (_random_filters)."""
    out = [cc.Filters()]
    out += [cc.Filters(length=r) for r in ((30, 60), (60, 1000), (150, 300), (300, 5000), (30, 3000), (3000, 5000))]
    for name in cc.KINDS:
        out += [f for f in (cc.Filters(**{name: edge}) for edge in cc.EDGES[name]) if f.active(name)]
    out += [cc.Filters(trees="no"), cc.Filters(trees="only"), cc.Filters(water="land"), cc.Filters(water="water")]
    rng = np.random.default_rng(53)
    return out + [_random_filters(rng) for _ in range(24)]


ORACLE_BORDERS = ({"border": "all"}, {"border": "own"}, {"border": "all", "replaced": (1, 2)},
                  {"border": "own", "replaced": (3,)}, {"border": "all", "replaced": (1, 2, 3, 4, 5, 6)})


def test_lean_answers_equal_the_oracle(tmp_path, monkeypatch):
    """Cube.cells and Cube.histogram (the lean code: the rows of a view by binary searches per column, chunks, one
    pass) give the answers of today's code (tests/cube_oracle.py: b45b950 frozen) over a grid of queries: no filter,
    each of the sixteen dimensions alone at every value that turns it on, the flags, combinations; border all and own
    with and without replaced partners; both modes, every level; the whole cube, boxes that cut it, a box of one or
    two cells, a box on the lattice's lines, a box away from the cube (empty), each as a view for reaching too and a
    view without a box; with and without sides and the summary: equal arrays (and dtypes), equal dicts and equal JSON.
    Chunks of 97 rows (ranges and cells across chunks), the default chunk for a part; select and reaching too."""
    import cube_oracle as oracle
    rng = np.random.default_rng(59)
    grid = _grid()
    out, _ = _build(tmp_path, [(grid, _lines(rng, grid, 3000, lengths=(30, 5000), borders=True), None)])
    cube = cc.Cube(str(out))
    west, south, east, north = cube.info["bounds_wgs84"]
    lon, lat = (west + east) / 2, (south + north) / 2
    on_lattice = ((ORIGIN[0] + 9) / 120, (ORIGIN[1] + 13) / 120, (ORIGIN[0] + 17) / 120, (ORIGIN[1] + 21) / 120)
    views = [(west + 0.01, south + 0.005, lon, lat), (lon, lat, lon + 0.004, lat + 0.003), on_lattice, (0.0, 0.0, 1.0, 1.0)]
    cases = [(None, None), (None, (lon - 0.02, lat - 0.01, lon + 0.01, lat + 0.02))]
    cases += [(cube.box(*v), None) for v in views] + [(cube.box(*v), v) for v in views]
    filters = _oracle_filters()
    compared = filled = 0
    for chunk in (97, cc.CHUNK_ROWS):
        monkeypatch.setattr(cc, "CHUNK_ROWS", chunk)
        for mode in ("lines", "spots"):
            for li, level in enumerate(cc.LEVELS):
                for k, f in enumerate(filters if chunk == 97 else filters[::5]):
                    f = cc.Filters(**{**f.__dict__, **ORACLE_BORDERS[(k + li) % len(ORACLE_BORDERS)]})
                    box, view = cases[(k + 3 * li) % len(cases)]
                    sides = k % 2 == 0
                    want = oracle.cells(cube, mode, level, box, f, sides)
                    got = cube.cells(mode, level, box, f, sides)
                    assert len(got) == len(want) and all(np.array_equal(g, w) and g.dtype == w.dtype
                                                         for g, w in zip(got, want)), (mode, level, box, f, sides)
                    summary = k % 3 != 1
                    want = oracle.histogram(cube, mode, level, box, f, view, 6, summary)
                    got = cube.histogram(mode, level, box, f, view, 6, summary)
                    assert got == want and json.dumps(got) == json.dumps(want), (mode, level, box, view, f, summary)
                    compared += 2
                    filled += got["total"] > 0
    assert compared == 2 * 8 * (len(filters) + len(filters[::5]))
    assert filled > compared / 6  # the grid compares counts, not only zeros
    keys = cube.array("lines", 1)[:, :2]
    for k, f in enumerate(filters):
        f = cc.Filters(**{**f.__dict__, **ORACLE_BORDERS[k % len(ORACLE_BORDERS)]})
        for skip in (None,) + cc.DIMENSIONS:
            assert (cc.select(keys, f, skip) == oracle.select(keys, f, skip)).all(), (f, skip)
        kept = cc.border_kept(keys, f)
        assert (kept is None) == (oracle.border_kept(keys, f) is None)
        assert kept is None or (kept == oracle.border_kept(keys, f)).all()
    for level in cc.LEVELS:
        keys = cube.array("spots", level)[:, :2]
        for view in views + [cases[1][1]]:
            assert (cube.reaching(level, keys, view, 6) == oracle.reaching(cube, level, keys, view, 6)).all()
            assert (cube.reaching(level, keys, view) == oracle.reaching(cube, level, keys, view)).all()


def test_outline_simplified(tmp_path):
    """The outline for a map: valid, fewer coordinates than the original, within the country's bounds (plus
    the tolerance), the original's km² on the ellipsoid, kept per tolerance."""
    rng = np.random.default_rng(41)
    grid = _grid()
    out, _ = _build(tmp_path, [(grid, _lines(rng, grid, 10, lengths=(30, 300)), None)])
    local = shapely.Polygon([(-559000, -1238000), (-555000, -1238000), (-551000, -1234000), (-551000, -1230000),
                             (-559000, -1230000)])
    dense = shapely.segmentize(local, 20.0)
    xy = shapely.get_coordinates(dense) + rng.uniform(-1, 1, (shapely.get_num_coordinates(dense), 2))
    xy[-1] = xy[0]  # the ring closed
    dense = shapely.Polygon(xy)
    back = shapely.transform(dense, lambda xy: np.column_stack(TO_WGS84.transform(xy[:, 0], xy[:, 1])))
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
    for x, y in geometry.exterior.coords:
        assert round(x, 4) == x and round(y, 4) == y
    lon0, lat0, lon1, lat1 = cube.info["bounds_wgs84"]
    t = cc.OUTLINE_TOLERANCE + 1e-4
    assert geometry.bounds[0] >= lon0 - t and geometry.bounds[1] >= lat0 - t
    assert geometry.bounds[2] <= lon1 + t and geometry.bounds[3] <= lat1 + t
    geodesic = abs(GEOD.geometry_area_perimeter(original)[0]) / 1e6
    assert found["area_km2"] == pytest.approx(geodesic, abs=0.1) == pytest.approx(56, rel=0.05)
    assert found["area_km2"] == round(found["area_km2"], 1)


def test_cell_km2_on_the_ellipsoid():
    """A whole cell's km² from its latitude: the geodesic area of its rectangle (pyproj's Geod)."""
    for level, j0, j in ((1, 5880, 0), (8, 5880, 3), (1, 0, 0), (4, -9000, 7), (2, 9000, 100)):
        south, north = (j0 + j * level) / 120, (j0 + (j + 1) * level) / 120
        side = level / 120
        lons = [10, 10 + side, 10 + side, 10]
        lats = [south, south, north, north]
        # a parallel is no geodesic: densify the rectangle's edges for Geod
        ring = shapely.segmentize(shapely.Polygon(list(zip(lons, lats))), side / 64)
        geodesic = abs(GEOD.geometry_area_perimeter(ring)[0]) / 1e6
        assert cc.lattice_km2(level, j0, np.array([j]))[0] == pytest.approx(geodesic, rel=1e-6)
    assert cc.lattice_km2(1, 5880, np.array([0]))[0] == pytest.approx(0.565, abs=0.001)  # 30″ at 49°


def _lattice(cube, level, outline):
    """The columns and rows of a level's cells over the outline's box."""
    left, bottom, right, top = outline.bounds
    return (range(math.floor((left * 120 - cube.origin[0]) / level), math.floor((right * 120 - cube.origin[0]) / level) + 1),
            range(math.floor((bottom * 120 - cube.origin[1]) / level), math.floor((top * 120 - cube.origin[1]) / level) + 1))


def test_cut_cells(tmp_path):
    """Cube.cut against each lattice rectangle cut alone, on an outline of a wiggly edge, a hole and an island:
    the same cells at every level, each with its km² on the ellipsoid (pyproj's Geod); the km² of a level's
    whole cells (cell_km2) and cut cells add up to the outline's; the shape to draw is the part inside within
    its simplification (a hole stays a hole), in [lat, lon]; kept; none without an outline."""
    rng = np.random.default_rng(42)
    grid = _grid()
    out, _ = _build(tmp_path, [(grid, _lines(rng, grid, 10, lengths=(30, 300)), None)])
    land = shapely.segmentize(shapely.Polygon([(-559000, -1240000), (-535000, -1240000), (-535000, -1218000),
                                               (-559000, -1218000)]), 50.0)
    xy = shapely.get_coordinates(land) + rng.uniform(-20, 20, (shapely.get_num_coordinates(land), 2))
    xy[-1] = xy[0]
    land = shapely.transform(shapely.Polygon(xy), lambda xy: np.column_stack(TO_WGS84.transform(xy[:, 0], xy[:, 1])))
    # a hole in the middle of the level-8 cell at the land's centre, an island east of it
    centre = land.centroid
    i8 = math.floor((centre.x * 120 - ORIGIN[0]) / 8)
    j8 = math.floor((centre.y * 120 - ORIGIN[1]) / 8)
    west, south = (ORIGIN[0] + 8 * i8) / 120, (ORIGIN[1] + 8 * j8) / 120
    assert shapely.box(west, south, west + 8 / 120, south + 8 / 120).within(land)
    hole = shapely.box(west + 3 / 120, south + 3 / 120, west + 5 / 120, south + 5 / 120)
    east = land.bounds[2]
    island = shapely.box(east + 0.01, centre.y, east + 0.025, centre.y + 0.01)
    back = shapely.MultiPolygon([shapely.Polygon(land.exterior.coords, [hole.exterior.coords]), island])
    assert back.is_valid
    (out / "area.geojson").write_text(json.dumps({"type": "Feature", "properties": {},
                                                 "geometry": json.loads(shapely.to_geojson(back))}))
    cube = cc.Cube(str(out))
    assert cube.cut(1) is cube.cut(1)  # kept
    outline = cube.outline()
    area = abs(GEOD.geometry_area_perimeter(shapely.segmentize(outline, 1 / 1200))[0]) / 1e6
    for level in cube.levels:
        side = level / 120
        columns, rows = _lattice(cube, level, outline)
        expected, whole = {}, 0.0
        for i in columns:
            for j in rows:
                west, south = (cube.origin[0] + i * level) / 120, (cube.origin[1] + j * level) / 120
                rectangle = shapely.box(west, south, west + side, south + side)
                part = rectangle.intersection(outline)
                if part.area >= rectangle.area * cc.CUT_FULL:
                    whole += cube.cell_km2(level, np.array([j]))[0]
                elif part.area > 0:
                    expected[i, j] = part
        found = cube.cut(level)
        assert set(found) == set(expected) and len(found) > 5
        for key, part in expected.items():
            geodesic = abs(GEOD.geometry_area_perimeter(shapely.segmentize(part, side / 64))[0]) / 1e6
            assert found[key]["km2"] == pytest.approx(geodesic, rel=1e-5, abs=2e-6)
            polygons = [shapely.Polygon(rings[0], rings[1:])
                        for rings in ([[(lon, lat) for lat, lon in ring] for ring in polygon]
                                      for polygon in found[key]["shape"])]
            drawn = shapely.MultiPolygon(polygons)
            assert drawn.area == pytest.approx(part.area, abs=part.length * side / cc.CUT_SIMPLIFY + 1e-9)
        total = whole + sum(v["km2"] for v in found.values())
        assert total == pytest.approx(area, rel=1e-5)
    assert [len(polygon) for polygon in cube.cut(8)[i8, j8]["shape"]] == [2]  # the hole in its cell
    assert cube.cut(8)[i8, j8]["km2"] == pytest.approx(cube.cell_km2(8, np.array([j8]))[0] * 15 / 16, rel=1e-3)
    json.dumps(list(cube.cut(1).values()))
    # an outline on the cells' edges cuts none of its cells but at a corner
    i0, j0 = cube.origin
    square = shapely.box((i0 + 16) / 120, (j0 + 16) / 120, (i0 + 32) / 120, (j0 + 32) / 120)
    (out / "area.geojson").write_text(json.dumps({"type": "Feature", "properties": {},
                                                 "geometry": json.loads(shapely.to_geojson(square))}))
    on_edges = cc.Cube(str(out))
    assert all(on_edges.cut(level) == {} for level in cc.LEVELS)
    (out / "area.geojson").unlink()
    assert cc.Cube(str(out)).cut(1) == {}


def test_cut_outside_against_each_cell(tmp_path):
    """Cube.cut_outside: the part of a cell beyond the outline within the layer's reach (its layer bands' longest line:
    300 m here) against each cell cut alone (the rectangle less the outline, clipped to the outline grown by the reach
    in the cube's CRS): the km² on the ellipsoid (pyproj's Geod) within the 20 m the grown outline is simplified by,
    a whole part not listed, a cell beyond the reach not listed, the shape within its simplification; kept; the parts
    inside (cut) and beyond add up to the cell's where the reach holds it whole."""
    rng = np.random.default_rng(53)
    grid = _grid()
    out, _ = _build(tmp_path, [(grid, _lines(rng, grid, 10, lengths=(30, 300)), None)])
    cube = cc.Cube(str(out))
    assert cube.reach_m() == 300
    outline = cube.outline()
    plane = shapely.transform(outline, lambda xy: np.column_stack(TO_CRS.transform(xy[:, 0], xy[:, 1])))
    zone = shapely.transform(shapely.segmentize(plane.buffer(300), 50.0),
                             lambda xy: np.column_stack(TO_WGS84.transform(xy[:, 0], xy[:, 1])))
    checked = 0
    for level in (1, 2):
        side = level / 120
        columns, rows = _lattice(cube, level, zone)
        cells = [(i, j) for i in columns for j in rows]
        found = cube.cut_outside(level, cells)
        assert cube.cut_outside(level, cells) == found  # kept
        inside = cube.cut(level)
        for i, j in cells:
            west, south = (cube.origin[0] + i * level) / 120, (cube.origin[1] + j * level) / 120
            rectangle = shapely.box(west, south, west + side, south + side)
            part = rectangle.difference(outline).intersection(zone)
            whole = abs(GEOD.geometry_area_perimeter(shapely.segmentize(rectangle, side / 64))[0]) / 1e6
            geodesic = abs(GEOD.geometry_area_perimeter(shapely.segmentize(part, side / 64))[0]) / 1e6 if part.area else 0.0
            if rectangle.within(outline):
                continue  # no partner lines there: not asked of a real cube
            km2 = found[i, j]["km2"] if (i, j) in found else (whole if part.area > rectangle.area / 2 else 0.0)
            strip = 0.02 * 4 * side * 111.32  # the grown outline's simplification along the cell's edges, km²
            assert km2 == pytest.approx(geodesic, abs=strip + 2e-6), (level, i, j)
            if (i, j) in found:
                checked += 1
                polygons = [shapely.Polygon(rings[0], rings[1:])
                            for rings in ([[(lon, lat) for lat, lon in ring] for ring in polygon]
                                          for polygon in found[i, j]["shape"])]
                drawn = shapely.MultiPolygon(polygons)
                assert drawn.area == pytest.approx(part.area, abs=part.length * side / cc.CUT_SIMPLIFY
                                                   + rectangle.length * 0.02 / 111.32 * 4)
                if (i, j) in inside and rectangle.within(zone):
                    assert inside[i, j]["km2"] + found[i, j]["km2"] == pytest.approx(whole, rel=1e-5)
    assert checked > 20
    json.dumps([v for v in cube.cut_outside(1, cells).values()])
    (out / "area.geojson").unlink()
    assert cc.Cube(str(out)).cut_outside(1, cells) == {}  # no outline: every part is the whole cell


def test_box_auto_level_and_corners(tmp_path):
    rng = np.random.default_rng(19)
    grid = _grid()
    out, _ = _build(tmp_path, [(grid, _lines(rng, grid, 100, lengths=(30, 300)), None)])
    cube = cc.Cube(str(out))
    i, j = np.array([0, 3, 7]), np.array([2, 0, 5])
    for level in cc.LEVELS:
        corners = cube.corners(level, i, j)
        assert corners.shape == (3, 4, 2)
        for k in range(3):
            west, south = (ORIGIN[0] + i[k] * level) / 120, (ORIGIN[1] + j[k] * level) / 120
            side = level / 120
            for c, (lon, lat) in enumerate([(west, south), (west + side, south), (west + side, south + side),
                                            (west, south + side)]):
                assert corners[k, c].tolist() == pytest.approx([lat, lon], abs=1e-12)
    lon0, lat0, lon1, lat1 = cube.info["bounds_wgs84"]
    box = cube.box(lon0 + 0.01, lat0 + 0.01, lon0 + 0.04, lat0 + 0.03)
    assert box == (lon0 + 0.01, lat0 + 0.01, lon0 + 0.04, lat0 + 0.03)
    assert cube.cell_count(1, box) == len(range(*_span(box[0], box[2], ORIGIN[0]))) * len(range(*_span(box[1], box[3], ORIGIN[1])))
    assert cube.auto_level(box) == 1 and cube.auto_level(box, most=4) >= 2 and cube.auto_level(box, most=0) == 8
    far = cube.box(100, 10, 101, 11)  # far from the country: empty
    assert far[0] > far[2] and len(cube.cells("lines", 1, far, cc.Filters())[0]) == 0 and cube.cell_count(1, far) == 0
    whole = cube.box(-540, -100, 540, 100)
    assert whole == (lon0 - 1, lat0 - 1, lon1 + 1, lat1 + 1)
    with pytest.raises(ValueError):
        cube.box(10, 50, 9, 51)


def _span(lo, hi, origin):
    return math.floor(lo * 120) - origin, math.floor(hi * 120) - origin + 1


def test_cell_request(tmp_path):
    rng = np.random.default_rng(23)
    grid = _grid()
    out, _ = _build(tmp_path, [(grid, _lines(rng, grid, 100, lengths=(30, 300)), None)])
    cube = cc.Cube(str(out))
    outline = cube.outline()
    to_crs = Transformer.from_crs("EPSG:4326", CRS, always_xy=True)
    local = shapely.transform(outline, lambda xy: np.column_stack(to_crs.transform(xy[:, 0], xy[:, 1])))
    columns, rows = _lattice(cube, 1, outline)
    inside = [(i, j) for i in columns for j in rows
              if shapely.box(*(cube.corners(1, [i], [j])[0][[0, 2]][:, ::-1].ravel())).within(outline)]
    edge = [(i, j) for i in columns for j in rows
            if (i, j) in cube.cut(1)]
    centre = outline.centroid
    i8, j8 = math.floor((centre.x * 120 - cube.origin[0]) / 8), math.floor((centre.y * 120 - cube.origin[1]) / 8)
    for level, i, j in [(1, *inside[len(inside) // 2]), (1, *edge[0]), (2, inside[0][0] // 2, inside[0][1] // 2),
                        (8, i8, j8)]:
        request = cc.cell_request(cube, "S", level, i, j)
        assert request["params"] == {"max_length": 300, "resolution": 1.0}
        geometry = request["geometry"]
        assert geometry["type"] in ("Polygon", "MultiPolygon")
        json.dumps(geometry)
        got = shapely.transform(shape(geometry), lambda xy: np.column_stack(to_crs.transform(xy[:, 0], xy[:, 1])))
        (south, west), _, (north, east), _ = cube.corners(level, np.array([i]), np.array([j]))[0]
        rectangle = shapely.transform(shapely.segmentize(shapely.box(west, south, east, north), 1e-4),
                                      lambda xy: np.column_stack(to_crs.transform(xy[:, 0], xy[:, 1])))
        expected = rectangle.buffer(300)  # not cut by the outline: the lines across the border are counted too
        assert got.symmetric_difference(expected).area < 3e-3 * expected.area, (level, i, j)
        if level == 1 and (i, j) in edge:
            assert not got.within(local.buffer(1))  # it reaches beyond the outline
    # a cell wholly beyond the outline within the band's reach (a partner row's cell, which the page offers to
    # search) is searched as any other; one farther than the reach is outside the country
    near_cells, far_cells = [], []
    for i in range(columns.start - 2, columns.stop + 2):
        for j in range(rows.start - 2, rows.stop + 2):
            (south, west), _, (north, east), _ = cube.corners(1, np.array([i]), np.array([j]))[0]
            if shapely.box(west, south, east, north).intersects(outline):
                continue
            box = shapely.transform(shapely.segmentize(shapely.box(west, south, east, north), 1e-4),
                                    lambda xy: np.column_stack(to_crs.transform(xy[:, 0], xy[:, 1])))
            gap = box.distance(local)
            (near_cells if gap < 250 else far_cells if gap > 350 else []).append((i, j, box))
    assert near_cells and far_cells
    i, j, box = near_cells[0]
    got = shapely.transform(shape(cc.cell_request(cube, "S", 1, i, j)["geometry"]),
                            lambda xy: np.column_stack(to_crs.transform(xy[:, 0], xy[:, 1])))
    assert got.symmetric_difference(box.buffer(300)).area < 3e-3 * box.buffer(300).area and got.intersects(local)
    with pytest.raises(ValueError, match="outside"):
        cc.cell_request(cube, "S", 1, far_cells[0][0], far_cells[0][1])
    with pytest.raises(ValueError, match="band"):
        cc.cell_request(cube, "M2", 1, *inside[0])  # not in the layer
    with pytest.raises(ValueError, match="band"):
        cc.cell_request(cube, "X", 1, *inside[0])
    with pytest.raises(ValueError, match="outside"):
        cc.cell_request(cube, "S", 1, 1000, 1000)
    with pytest.raises(ValueError, match="outside"):
        cc.cell_request(cube, "S", 1, -1, 0)
    with pytest.raises(ValueError, match="level"):
        cc.cell_request(cube, "S", 3, *inside[0])


def test_cube_of_another_version(tmp_path):
    rng = np.random.default_rng(29)
    grid = _grid()
    out, _ = _build(tmp_path, [(grid, _lines(rng, grid, 10, lengths=(30, 300)), None)])
    meta = json.loads((out / "cube.json").read_text())
    for version in (1, cc.VERSION + 1):  # a cube of v1 (CRS cells of 1 km) is built again, never read
        (out / "cube.json").write_text(json.dumps({**meta, "version": version}))
        with pytest.raises(ValueError, match="version"):
            cc.Cube(str(out))


def test_import_loads_no_search_code():
    code = (f"import json, sys; sys.path.insert(0, {REPO!r}); import countcube\n"
            "print(json.dumps(sorted(m for m in sys.modules if m.split('.')[0] in "
            "('numba', 'linesearch', 'search', 'country'))))")
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout.strip().splitlines()[-1]) == []
