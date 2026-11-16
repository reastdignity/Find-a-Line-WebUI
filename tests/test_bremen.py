"""Bremen and Bremerhaven: Landesamt GeoInformation Bremen's DGM1 and DOM1 as XYZ members of remote ZIP archives
(sources/catalogue/germany.py), read by sources/readers/zipmember.py: GDAL's XYZ driver, and xyz_rows for a member
in columns with points missing, against archives made here with zipfile (served by tests/http_server.py); the
catalogue's two sources, their members' names as the archives' central directories list them (recorded,
tests/data/recorded/bremen/), and which source a place takes, online and offline."""

import gzip
import json
import os
import zipfile

import numpy as np
import pytest
import rasterio as rio
from rasterio.transform import Affine

import osm
import sources as src
from sources.catalogue import germany
from sources.layers.zipmembers import ZipMemberTiles
from sources.readers.zipmember import TransformFix, ZipMember, xyz_rows
from test_saarland import _archive, _serve, _tile

RECORDED = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "recorded", "bremen", "directories.json.gz")

ZONE = TransformFix(offset=(-32_000_000.0, 0.0), snap=0.5)


def _xyz(points, header: bool = True, newline: str = "\r\n") -> bytes:
    """An XYZ member: "x y z" lines of the points in their order, after a header line or not."""
    return (newline.join((["x y z"] if header else []) + [f"{x} {y} {z}" for x, y, z in points]) + newline).encode()


def _fetch(http_server, tmp_path, reader: ZipMember, name: str, body: bytes):
    _serve(http_server, "/m.zip", body)
    path = str(tmp_path / "t.tif")
    reader.fetch(_tile(http_server, "/m.zip", body, name), path)
    with rio.open(path) as written:
        return written.transform, written.read(1, masked=True).astype(np.float32).filled(np.nan)


# Bremerhaven's DOM1: whole metres with the zone, in columns from the south (dom1_32474_5936_1_hb.xyz's layout)
COLUMNS = [(32474000 + i, 5936000 + j, round(2 + 0.1 * i + 0.01 * j, 3)) for i in range(4) for j in range(3)]
EXPECTED = np.array([[2.02, 2.12, 2.22, 2.32], [2.01, 2.11, 2.21, 2.31], [2.0, 2.1, 2.2, 2.3]], dtype=np.float32)


def test_xyz_rows_keeps_the_lines():
    """The lines in rows, north to south and west to east, each as it was written; the header kept; a GeoTIFF or
    other text is not XYZ (None)."""
    member = _xyz([(1.5, 10.5, "0.100"), (1.5, 11.5, "0.200"), (2.5, 10.5, "0.300"), (2.5, 11.5, "0.400")])
    assert xyz_rows(member) == b"x y z\n1.5 11.5 0.200\n2.5 11.5 0.400\n1.5 10.5 0.100\n2.5 10.5 0.300\n"
    assert xyz_rows(_xyz([(1, 2, 3), (1, 1, 4)], header=False, newline="\n")) == b"1 2 3\n1 1 4\n"
    assert xyz_rows(b"II*\x00\x08\x00\x00\x00\xff\xfe") is None
    assert xyz_rows(b"x y z\r\n1 2\r\n") is None
    assert xyz_rows(b"x y z\r\n") is None


@pytest.mark.parametrize("gone, nan", [
    ([(32474003, 5936001), (32474003, 5936002)], [(0, 3), (1, 3)]),   # the last column only its lowest point
    ([(32474001, 5936001)], [(1, 1)]),                                  # a point inside a column
    ([(32474000, 5936002), (32474001, 5936002)], [(0, 0), (0, 1)])])    # the first columns' top
def test_a_member_in_columns_with_points_missing(http_server, tmp_path, gone, nan):
    """GDAL refuses points in columns with some missing ("does not support datasets organized by columns with
    missing values", or "Ungridded dataset"): the catalogue's own reader (Bremerhaven's DOM1) reads the member again
    in rows, the missing points no data, the others where the whole member puts them."""
    reader = src.SOURCES["bremerhaven"].nmpt.reader
    name = "Gitternetz_DOM1_2015_BHV/dom1_32474_5936_1_hb.xyz"
    whole = _archive([(name, _xyz(COLUMNS), zipfile.ZIP_DEFLATED, False)])
    transform, z = _fetch(http_server, tmp_path, reader, name, whole)
    assert transform == Affine(1.0, 0.0, 473999.5, 0.0, -1.0, 5936002.5) and np.allclose(z, EXPECTED)
    part = _archive([(name, _xyz([p for p in COLUMNS if p[:2] not in gone]), zipfile.ZIP_DEFLATED, False)])
    transform_part, z_part = _fetch(http_server, tmp_path, reader, name, part)
    expected = EXPECTED.copy()
    for row, col in nan:
        expected[row, col] = np.nan
    assert transform_part == transform and np.allclose(z_part, expected, equal_nan=True)


def test_members_in_columns_are_read_one_at_a_time(monkeypatch):
    """GDAL keeps one cache per process for an XYZ file in columns: two read at once in two threads evict each
    other's on every block (46 s for a pair of Bremerhaven's DGM1 members instead of 0.3 s each), so a member in
    columns is read under zipmember.COLUMNS_LOCK; one in rows (Bremen's) and a GeoTIFF are not."""
    from sources.readers import zipmember
    entered = []

    class Recorder:
        def __enter__(self):
            entered.append(1)

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(zipmember, "COLUMNS_LOCK", Recorder())
    columns = _xyz(COLUMNS)
    rows = _xyz([(465000 + i, 5896999 - j, 3.25) for j in range(3) for i in range(4)])
    assert zipmember.xyz_in_columns(columns) and not zipmember.xyz_in_columns(rows)
    assert not zipmember.xyz_in_columns(b"II*\x00\x08\x00\x00\x00") and not zipmember.xyz_in_columns(b"x y z\r\n")
    reader = ZipMember("DOM1 (test)", crs="EPSG:25832", fix=ZONE)
    band, _, _ = reader.raster(columns, "t")
    assert entered == [1] and np.allclose(band, EXPECTED)
    ZipMember("DGM1 (test)", crs="EPSG:25832").raster(rows, "t")
    assert entered == [1]


def test_not_a_raster_is_still_an_error(http_server, tmp_path):
    """Text that is no XYZ grid at all fails as before (no tile), also after the second reading."""
    name = "dom1_32474_5936_1_hb.xyz"
    body = _archive([(name, _xyz([(0, 0, 1), (0.3, 7, 2), (5, 1.1, 3), (9, 9, 4)]), zipfile.ZIP_DEFLATED, False)])
    with pytest.raises(RuntimeError, match="not a raster"):
        _fetch(http_server, tmp_path, ZipMember("DOM1 (test)", crs="EPSG:25832"), name, body)
    assert not (tmp_path / "t.tif").exists()


# --- the catalogue's sources ---

def _recorded():
    with gzip.open(RECORDED, "rt", encoding="utf-8") as f:
        return json.load(f)["archives"]


@pytest.mark.parametrize("sid, kind, tiles, east, north", [
    ("bremen", "nmt", 395, (465, 499), (5873, 5897)), ("bremen", "nmpt", 395, (465, 499), (5873, 5897)),
    ("bremerhaven", "nmt", 188, (466, 477), (5924, 5940)), ("bremerhaven", "nmpt", 114, (466, 477), (5924, 5940))])
def test_member_names(sid, kind, tiles, east, north):
    """The archives' own member names (their central directories, read by Range 2026-11-15: Bremerhaven's DGM1 with
    a double underscore, its DOM1 with one): every tile matches the layer's expression, the folders and Bremen's
    Thumbs.db do not, nor the other model's names; the tiles' km as the names say."""
    layer = getattr(src.SOURCES[sid], kind)
    (url,) = layer.metalinks
    names = [m[0] for m in _recorded()[url]["members"]]
    matched = [layer.listing.name.search(n) for n in names]
    found = [(int(m.group("east")), int(m.group("north"))) for m in matched if m]
    assert len(found) == len(set(found)) == tiles
    assert (min(e for e, _ in found), max(e for e, _ in found)) == east
    assert (min(n for _, n in found), max(n for _, n in found)) == north
    assert all(n.endswith("/") or n.endswith("Thumbs.db") for n, m in zip(names, matched) if not m)
    other = src.SOURCES[sid].nmpt if kind == "nmt" else src.SOURCES[sid].nmt
    assert not any(other.listing.name.search(n) for n in names)
    if sid == "bremerhaven":
        assert all(("__" in n) == (kind == "nmt") for n, m in zip(names, matched) if m)


def test_the_surface_covers_part_of_the_terrains_tiles_in_the_record():
    """Bremerhaven's DOM1 covers the city only: 114 tiles of the DGM1's 188, 41 of them with fewer points than a
    full km (inflated under 90 % of the median; the twelve read on 2026-11-16 were rectangles of part of it, which GDAL
    reads as they are, and xyz_rows reads one that is not)."""
    archives = _recorded()
    bhv = {url: a for url, a in archives.items() if "_BHV_" in url}
    dom = next(a for url, a in bhv.items() if "DOM1" in url)
    sizes = sorted(m[5] for m in dom["members"] if m[0].endswith(".xyz"))
    assert len(sizes) == 114 and sum(s < 0.9 * sizes[len(sizes) // 2] for s in sizes) == 41


@pytest.mark.parametrize("sid, kind, name, points, header, newline, transform, expected", [
    # Bremen: whole metres without the zone, rows from the north, centimetres (dgm1_32483_5876_1_hb.xyz)
    ("bremen", "nmt", "Gitternetz_DGM1_2017/dgm1_32483_5876_1_hb.xyz",
     [(483000 + i, 5876999 - j, f"{3 + 0.1 * i + 0.01 * j:.2f}") for j in range(3) for i in range(4)], True, "\r\n",
     Affine(1.0, 0.0, 482999.5, 0.0, -1.0, 5876999.5),
     [[3.0, 3.1, 3.2, 3.3], [3.01, 3.11, 3.21, 3.31], [3.02, 3.12, 3.22, 3.32]]),
    ("bremen", "nmpt", "Gitternetz_DOM1_2017/dom1_32483_5876_1_hb.xyz",
     [(483000 + i, 5876999 - j, f"{3 + 0.1 * i + 0.01 * j:.2f}") for j in range(3) for i in range(4)], False, "\n",
     Affine(1.0, 0.0, 482999.5, 0.0, -1.0, 5876999.5),
     [[3.0, 3.1, 3.2, 3.3], [3.01, 3.11, 3.21, 3.31], [3.02, 3.12, 3.22, 3.32]]),
    # Bremerhaven's DGM1: x.5 with the zone, columns from the north, millimetres (dgm1_32474__5936_1_hb.xyz)
    ("bremerhaven", "nmt", "Gitternetz_DGM1_2015_BHV/dgm1_32474__5936_1_hb.xyz",
     [(32474000.5 + i, 5936999.5 - j, f"{1 + 0.1 * i + 0.001 * j:.3f}") for i in range(4) for j in range(3)], True,
     "\r\n", Affine(1.0, 0.0, 474000.0, 0.0, -1.0, 5937000.0),
     [[1.0, 1.1, 1.2, 1.3], [1.001, 1.101, 1.201, 1.301], [1.002, 1.102, 1.202, 1.302]]),
    # Bremerhaven's DOM1: whole metres with the zone, columns from the south, part of a km (dom1_32475_5936_1_hb.xyz:
    # its north-west corner)
    ("bremerhaven", "nmpt", "Gitternetz_DOM1_2015_BHV/dom1_32475_5936_1_hb.xyz",
     [(32475000 + i, 5936997 + j, f"{2 + 0.1 * i + 0.001 * j:.3f}") for i in range(4) for j in range(3)], True,
     "\r\n", Affine(1.0, 0.0, 474999.5, 0.0, -1.0, 5936999.5),
     [[2.002, 2.102, 2.202, 2.302], [2.001, 2.101, 2.201, 2.301], [2.0, 2.1, 2.2, 2.3]]),
])
def test_the_catalogues_layers(http_server, tmp_path, sid, kind, name, points, header, newline, transform, expected):
    """The catalogue's own readers on members of each layout (the header or none, CRLF or LF): the zone taken off
    Bremerhaven's eastings, each value in its pixel, the transform on the grid the measurement found (Bremen's and
    Bremerhaven's DOM1's centres on whole metres, Bremerhaven's DGM1's edges)."""
    layer = getattr(src.SOURCES[sid], kind)
    assert layer.listing.name.search(name)
    body = _archive([(name, _xyz(points, header, newline), zipfile.ZIP_DEFLATED, False)])
    got, z = _fetch(http_server, tmp_path, layer.reader, name, body)
    assert got == transform and np.allclose(z, np.array(expected, dtype=np.float32), atol=0.006)
    with rio.open(tmp_path / "t.tif") as written:
        assert written.crs.to_epsg() == 25832


def test_bremerhavens_grid_and_its_surface():
    """Bremerhaven's terrain sets the grid (edges on whole metres); its surface lies half a pixel off, so the mosaic
    interpolates it (not moved: a TransformFix rounding it to whole metres would refuse it, 0.5 px off)."""
    bhv, hb = src.SOURCES["bremerhaven"], src.SOURCES["bremen"]
    assert bhv.grid_origin == (0.0, 0.0) and hb.grid_origin == (0.5, 0.5)
    assert bhv.nmt.reader.fix == TransformFix(offset=(-32_000_000.0, 0.0), snap=1.0)
    assert bhv.nmpt.reader.fix == TransformFix(offset=(-32_000_000.0, 0.0), snap=0.5)
    assert hb.nmt.reader.fix is None and hb.nmpt.reader.fix is None
    with pytest.raises(RuntimeError, match="0.5 px off"):
        bhv.nmt.reader.fix.apply(Affine(1.0, 0.0, 32473999.5, 0.0, -1.0, 5936999.5), "t")
    assert bhv.nmt.shift == bhv.nmpt.shift == (0.0, 0.0)


def test_changed_archives_read_again_as_saarlands():
    """Bremen's and Bremerhaven's readers (XYZ members, a TransformFix or none) renew their archive's directory after
    a 404, a moved or a changed member (a 416 too) as Saarland's and Hamburg's: every ZipMemberTiles does."""
    for sid in ("bremen", "bremerhaven", "saarland", "hamburg"):
        for layer in (src.SOURCES[sid].nmt, src.SOURCES[sid].nmpt):
            assert isinstance(layer, ZipMemberTiles) and layer.reader.renew == layer._renew


def test_a_tile_without_the_surface(http_server, tmp_path, monkeypatch):
    """Bremerhaven's DOM1 has 114 of the DGM1's 188 tiles: the catalogue's own layers on two archives served here,
    the terrain lists a tile the surface does not (the search checks lines there against the bare terrain) and a
    partial surface tile (a rectangle of its km) downloads as it is."""
    from grid import make_grid
    bhv = src.SOURCES["bremerhaven"]
    dgm = [(32466000.5 + i, 5924999.5 - j, "1.000") for i in range(3) for j in range(3)]
    dgm2 = [(32475000.5 + i, 5936999.5 - j, "1.500") for i in range(3) for j in range(3)]
    dom = [(32475000 + i, 5936997 + j, "9.000") for i in range(2) for j in range(3)]
    archives = {
        "dgm": _archive([("Gitternetz_DGM1_2015_BHV/dgm1_32466__5924_1_hb.xyz", _xyz(dgm), zipfile.ZIP_DEFLATED, False),
                         ("Gitternetz_DGM1_2015_BHV/dgm1_32475__5936_1_hb.xyz", _xyz(dgm2), zipfile.ZIP_DEFLATED,
                          False)]),
        "dom": _archive([("Gitternetz_DOM1_2015_BHV/dom1_32475_5936_1_hb.xyz", _xyz(dom), zipfile.ZIP_DEFLATED, False)])}
    for kind, layer in (("dgm", bhv.nmt), ("dom", bhv.nmpt)):
        _serve(http_server, f"/{kind}.zip", archives[kind])
        url = http_server.url(f"/{kind}.zip")  # only the archive's address replaced
        monkeypatch.setattr(layer.listing, "urls", [url])
        monkeypatch.setattr(layer.listing, "url", url)
    cache_dir = str(tmp_path / "cache")
    for layer in (bhv.nmt, bhv.nmpt):
        layer._use(cache_dir)
    south = make_grid((466100, 5924100, 466900, 5924900), 1.0, "EPSG:25832")
    assert [(t.east, t.north) for t in bhv.nmt.tiles(south)] == [(466, 5924)] and bhv.nmpt.tiles(south) == []
    east = make_grid((475100, 5936100, 475900, 5936900), 1.0, "EPSG:25832")
    (tile,) = bhv.nmpt.tiles(east)
    bhv.nmpt.download(east, cache_dir, None, "surface")
    with rio.open(bhv.nmpt.tile_path(cache_dir, tile)) as cached:
        assert cached.transform == Affine(1.0, 0.0, 474999.5, 0.0, -1.0, 5936999.5) and cached.shape == (3, 2)
        assert float(cached.read(1).max()) == 9.0
    assert os.path.relpath(bhv.nmpt.tile_path(cache_dir, tile), cache_dir).startswith(
        os.path.join("bremerhaven", "dom1-2015"))


def _hamburg_member(values: np.ndarray) -> bytes:
    """A GeoTIFF member of LGV Hamburg's DGM1 553_5934 as it says its origin (552999.9999999999), LZW, nodata -3.4e38."""
    noisy = Affine(1.0, 0.0, 552999.9999999999, 0.0, -1.0, 5935000.000000001)
    with rio.io.MemoryFile() as memfile:
        with memfile.open(driver="GTiff", width=values.shape[1], height=values.shape[0], count=1, dtype="float32",
                          crs="EPSG:25832", transform=noisy, nodata=-3.4028234663852886e38, compress="lzw") as dst:
            dst.write(values.astype(np.float32), 1)
        return memfile.read()


# (source, layer, member's name, its bytes, the grid over it); the values random so a misplaced tile cannot pass
RNG = np.random.default_rng(5)
CHECKED = [
    ("bremerhaven", "nmt", "Gitternetz_DGM1_2015_BHV/dgm1_32474__5936_1_hb.xyz",
     _xyz([(32474000.5 + i, 5936999.5 - j, f"{RNG.uniform(0, 9):.3f}") for i in range(30) for j in range(20)]),
     (474002, 5936982, 474018, 5936998)),
    ("bremerhaven", "nmpt", "Gitternetz_DOM1_2015_BHV/dom1_32474_5936_1_hb.xyz",
     _xyz([(32474000 + i, 5936980 + j, f"{RNG.uniform(0, 30):.3f}") for i in range(31) for j in range(20)]),
     (474002, 5936982, 474018, 5936998)),
    ("hamburg", "nmt", "s32_553/dgm1_32_553_5934_1_hh_2022.tif", _hamburg_member(RNG.uniform(0, 9, (20, 30))),
     (553002, 5934982, 553018, 5934998))]


def _saarland_member() -> bytes:
    """A GeoTIFF member as LVGL's: uncompressed float32, -9999 for no data, a patch at 0 m (its floor's case)."""
    from rasterio.transform import from_origin
    values = np.random.default_rng(7).uniform(180, 220, (40, 40)).astype(np.float32)
    values[:3, :] = -9999.0
    values[20:23, 20:23] = 0.0
    with rio.io.MemoryFile() as memfile:
        with memfile.open(driver="GTiff", width=40, height=40, count=1, dtype="float32", crs="EPSG:25832",
                          transform=from_origin(327000.0, 5486000.0, 1.0, 1.0), nodata=-9999.0) as dst:
            dst.write(values, 1)
        return memfile.read()


@pytest.mark.parametrize("sid, member", [("hamburg", _hamburg_member(np.random.default_rng(3).uniform(0, 9, (20, 30)))),
                                         ("saarland", _saarland_member())], ids=["hamburg", "saarland"])
def test_geotiff_members_written_as_before(tmp_path, sid, member):
    """The reader's tile of a GeoTIFF member (Hamburg's, Saarland's) is byte for byte the tile of the path before
    xyz_rows, COLUMNS_LOCK and ZipMember.raster: GDAL's plain read, layer._clean, the layer's fix, drop_below and
    _write_tile (the catalogue's own readers: Hamburg's rounding, Saarland's floor and ring)."""
    import hashlib
    from sources.layer import _clean, _write_tile
    from sources.readers.zipmember import drop_below
    reader = src.SOURCES[sid].nmt.reader
    reader._write(member, str(tmp_path / "reader.tif"), "t")
    with rio.io.MemoryFile(member) as memfile, memfile.open() as plain:
        band = _clean(plain.read(1, masked=True).astype(np.float32).filled(np.nan), copy=False)
        crs, transform = reader.crs or plain.crs, plain.transform
    if reader.fix is not None:
        transform = reader.fix.apply(transform, "t")
    drop_below(band, reader.floor, reader.ring)
    _write_tile(str(tmp_path / "plain.tif"), band, crs, transform)
    digest = [hashlib.sha256((tmp_path / f"{name}.tif").read_bytes()).hexdigest() for name in ("reader", "plain")]
    assert digest[0] == digest[1]
    assert (reader.fix is not None) == (sid == "hamburg") and (reader.floor is not None) == (sid == "saarland")


@pytest.mark.parametrize("sid, kind, name, member, box", CHECKED, ids=["bremerhaven-dgm1", "bremerhaven-dom1",
                                                                      "hamburg-dgm1"])
@pytest.mark.parametrize("wrong", [None, (5.0, 0.0), (1_000_000.0, 0.0)], ids=["right", "5-m-east", "a-zone-east"])
def test_check_source_finds_a_wrong_fix(http_server, tmp_path, monkeypatch, sid, kind, name, member, box, wrong):
    """tools/check_source.py's file check reads each member by its own rules (the member's georeferencing, a zone in
    front of an easting taken off), not through the layer's fix: Bremerhaven's and Hamburg's cached tiles equal their
    members (PASS, within LERC's bound), and a tile the catalogue's fix put 5 m or a whole zone (1000 km) away is
    found (WARN)."""
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
    import check_source as cs
    from grid import make_grid
    monkeypatch.setattr(src.layer, "DOWNLOAD_THREADS", 1)
    layer = getattr(src.SOURCES[sid], kind)
    _serve(http_server, "/m.zip", _archive([(name, member, zipfile.ZIP_DEFLATED, False)]))
    url = http_server.url("/m.zip")
    monkeypatch.setattr(layer.listing, "urls", [url])
    monkeypatch.setattr(layer.listing, "url", url)
    monkeypatch.setattr(layer.index, "_listed", {})  # the process's answers of an earlier case (another server)
    if wrong is not None:
        fix = layer.reader.fix
        monkeypatch.setattr(layer.reader, "fix", fix._replace(offset=(fix.offset[0] + wrong[0], fix.offset[1] + wrong[1])))
    cache_dir = str(tmp_path / "cache")
    grid = make_grid(box, 1.0, "EPSG:25832")
    layer.download(grid, cache_dir, None, kind)
    check = cs.check_files(layer, grid, cache_dir, 2)
    if wrong is None:
        assert check["status"] == cs.PASS and check["tiles"][0]["max_abs_m"] <= 0.006, check["text"]
    else:
        assert check["status"] == cs.WARN, check["text"]


def test_sources():
    hb, bhv, ni = src.SOURCES["bremen"], src.SOURCES["bremerhaven"], src.SOURCES["lower_saxony"]
    for s, city, year, top in ((hb, "HB", "2017", "bremen"), (bhv, "BHV", "2015", "bremerhaven")):
        assert s.countries == ("de",) and s.regions == ("de-hb",) and s.crs == "EPSG:25832"
        assert isinstance(s.nmt, ZipMemberTiles) and isinstance(s.nmpt, ZipMemberTiles)
        assert s.nmt.metalinks == (germany.HB_DATA.format(kind="DGM", year=year, city=city),)
        assert s.nmpt.metalinks == (germany.HB_DATA.format(kind="DOM", year=year, city=city),)
        assert (s.nmt.folder, s.nmpt.folder) == (f"{top}/dgm1-{year}", f"{top}/dom1-{year}")
        assert s.nmt.listing.top == s.nmpt.listing.top == top  # its own directories and index answers
        assert s.nmt.floor is None and s.nmt.ttl_days is None and s.fallbacks == ["europe"]
        assert [c.data for c in s.credits] == ["DGM1 / DOM1 (Landesamt GeoInformation Bremen)"]
        assert s.ortho.url == "https://geodienste.bremen.de/wms_dop_lb" and s.ortho.ttl_days is None
        # Lower Saxony is full (six neighbours, countcube.PARTNERS): no neighbours either way
        assert s.neighbours == () and s.id not in ni.neighbours
        south, north, west, east = s.bbox
        assert all(south <= s_ < n_ <= north and west <= w_ < e_ <= east for _, (s_, n_, w_, e_) in s.offline)
        assert s.covers(*s.sample)
    assert len(ni.neighbours) == 6
    assert (hb.ortho.layer, bhv.ortho.layer) == ("dop10_2025_HB", "dop10_2025_BHV")
    assert hb.bbox[1] < bhv.bbox[0]  # the two boxes apart: Lower Saxony between them
    assert src.HOST_SLOTS_OF["gdi2.geo.bremen.de"] == 2
    # Two areas of the coverage map, each its city's (de-hb-bhv our code: ISO 3166-2 names neither city)
    assert hb.map_areas() == ("de-hb",) and bhv.map_areas() == ("de-hb-bhv",)
    assert (hb.coverage.survey, bhv.coverage.survey) == ("2017", "2015")
    assert (src.AREA_NAMES["de-hb"], src.AREA_NAMES["de-hb-bhv"]) == ("Freie Hansestadt Bremen", "Bremerhaven")
    from sources import probe
    assert probe.strategy(hb.nmt) == probe.strategy(bhv.nmpt) == "zip"
    ids = list(src.SOURCES)
    assert ids.index("bremen") < ids.index("lower_saxony") and ids.index("bremerhaven") < ids.index("lower_saxony")


def test_the_download_window_has_a_row_per_city():
    """tools/area_rows.py makes a row of each city's area, each downloading through its own source, and
    tools/area_download.py's plan_of clips a row's outline to its source's coverage boxes (area.clip_to_boxes):
    Bremerhaven's row keeps Bremerhaven (bremen's boxes would leave all of it out), Bremen's keeps Bremen."""
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
    import area
    import area_rows as ar
    from shapely.geometry import box
    rows = {row.name: row for row in ar.catalogue()}
    hb, bhv = rows["germany-bremen"], rows["germany-bremerhaven"]
    assert (hb.source, hb.area, hb.country, hb.label) == ("bremen", "osm:Freie Hansestadt Bremen", "Germany", "Bremen")
    assert (bhv.source, bhv.area, bhv.country, bhv.label) == ("bremerhaven", "osm:Bremerhaven", "Germany",
                                                              "Bremerhaven")
    assert hb.continent == bhv.continent == "Europe" and hb.km2 > 200 and 50 < bhv.km2 < 200
    in_bhv, in_hb = box(8.55, 53.50, 8.62, 53.58), box(8.72, 53.04, 8.95, 53.10)  # inside each city (lon, lat)
    for city, own, other in ((in_bhv, "bremerhaven", "bremen"), (in_hb, "bremen", "bremerhaven")):
        kept, dropped = area.clip_to_boxes(city, src.SOURCES[own].coverage_boxes())
        assert dropped == 0.0 and kept.equals(city)
        kept, dropped = area.clip_to_boxes(city, src.SOURCES[other].coverage_boxes())
        assert kept.is_empty and dropped > 10


# (lat, lon, Nominatim's region, the source online, the source offline)
PLACES = [
    (53.0760, 8.8075, "DE-HB", "bremen", "bremen"),              # the Marktplatz
    (53.1705, 8.6215, "DE-HB", "bremen", "bremen"),              # Vegesack
    (53.2030, 8.5200, "DE-HB", "bremen", "bremen"),              # Farge, the north-west end
    (53.0300, 8.8400, "DE-HB", "bremen", "bremen"),              # Kattenturm, the south
    (53.5400, 8.5800, "DE-HB", "bremerhaven", "bremerhaven"),    # Bremerhaven's centre
    (53.5850, 8.5350, "DE-HB", "bremerhaven", "bremerhaven"),    # the container terminal (the city of Bremen's port)
    (53.4900, 8.5300, "DE-HB", "bremerhaven", "bremerhaven"),    # the Luneplate
    (53.0506, 8.6317, "DE-NI", "lower_saxony", "lower_saxony"),  # Delmenhorst
    (53.1420, 8.9050, "DE-NI", "lower_saxony", "lower_saxony"),  # Lilienthal
    (53.0250, 8.8050, "DE-NI", "lower_saxony", "lower_saxony"),  # Stuhr-Brinkum
    (53.1667, 8.6100, "DE-NI", "lower_saxony", "lower_saxony"),  # Lemwerder, across the Weser from Vegesack
    (53.2300, 8.7900, "DE-NI", "lower_saxony", "lower_saxony"),  # Osterholz-Scharmbeck, between the cities
    (53.3500, 8.5500, "DE-NI", "lower_saxony", "lower_saxony"),  # the Wesermarsch, between the cities
    (53.5300, 8.5300, "DE-NI", "lower_saxony", "lower_saxony"),  # Blexen, across the Weser from Bremerhaven
    (53.6050, 8.5970, "DE-NI", "lower_saxony", "lower_saxony"),  # Langen (Geestland)
    (53.5350, 8.6600, "DE-NI", "lower_saxony", "lower_saxony"),  # Schiffdorf
]


@pytest.mark.parametrize("lat, lon, region, online, offline", PLACES)
def test_the_source_of_a_place(monkeypatch, tmp_path, lat, lon, region, online, offline):
    """Nominatim names both cities DE-HB: each city's source is chosen by its bbox, Lower Saxony's land (DE-NI) inside
    a city's box keeps Lower Saxony's source. Offline, the staircases of boxes inside the cities decide."""
    answer = {"address": {"country_code": "de", "ISO3166-2-lvl4": region}}
    monkeypatch.setattr(osm, "reverse", lambda *args, **kwargs: answer)
    assert src.choose.choose_source("auto", lat, lon, str(tmp_path))[0].id == online

    def no_lookup(*args, **kwargs):
        raise ValueError("offline")
    monkeypatch.setattr(osm, "reverse", no_lookup)
    assert src.choose.choose_source("auto", lat, lon, str(tmp_path))[0].id == offline


def test_offline_boxes_before_lower_saxonys():
    """The cities' staircases (14 boxes and 7) come before Lower Saxony's box, which holds both cities (the first box
    holding a point wins)."""
    boxes = src.OFFLINE_BOXES
    first_ni = next(i for i, (code, _) in enumerate(boxes) if code == "de-ni")
    mine = [i for i, (code, _) in enumerate(boxes) if code == "de-hb"]
    assert len(mine) == 21 and max(mine) < first_ni
    assert [len(src.SOURCES[sid].offline) for sid in ("bremen", "bremerhaven")] == [14, 7]
