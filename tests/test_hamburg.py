"""Hamburg: LGV's DGM1 and bDOM1, members of two remote ZIP archives (sources/catalogue/germany.py), the ZIP members'
transform fix (sources/readers/zipmember.py TransformFix: Hamburg's rounding, Bremerhaven's zone prefix) against
archives made here with zipfile (served by tests/http_server.py), and the catalogue's source."""

import zipfile

import numpy as np
import pytest
import rasterio as rio
from rasterio.transform import Affine

import sources as src
from sources.catalogue import germany
from sources.layers.zipmembers import ZipMemberTiles
from sources.readers.zipmember import TransformFix, ZipMember
from test_saarland import _archive, _serve, _tile

NOISY = Affine(1.0, 0.0, 552999.9999999999, 0.0, -1.0, 5935000.000000001)  # Hamburg's DGM1 553_5934 as it says


def _member(transform: Affine, values: np.ndarray, nodata) -> bytes:
    """A GeoTIFF member of values (float32) on transform, LZW like LGV's, with its declared nodata."""
    with rio.io.MemoryFile() as memfile:
        with memfile.open(driver="GTiff", width=values.shape[1], height=values.shape[0], count=1, dtype="float32",
                          crs="EPSG:25832", transform=transform, nodata=nodata, compress="lzw") as dst:
            dst.write(values.astype(np.float32), 1)
        return memfile.read()


def _fetch(http_server, tmp_path, reader: ZipMember, name: str, body: bytes):
    _serve(http_server, "/m.zip", body)
    path = str(tmp_path / "t.tif")
    reader.fetch(_tile(http_server, "/m.zip", body, name), path)
    with rio.open(path) as written:
        return written.transform, written.crs, written.read(1, masked=True).astype(np.float32).filled(np.nan)


def test_the_fix_rounds_float_noise():
    assert TransformFix(snap=1.0).apply(NOISY, "t") == Affine(1.0, 0.0, 553000.0, 0.0, -1.0, 5935000.0)
    assert TransformFix().apply(NOISY, "t") == NOISY  # neither offset nor snap: as the file says
    exact = Affine(0.5, 0.0, 553000.0, 0.0, -0.5, 5935000.0)
    assert TransformFix(snap=1.0).apply(exact, "t") == exact


@pytest.mark.parametrize("x, y", [(553000.3, 5935000.0), (553000.0, 5934999.99), (552999.5, 5935000.0)])
def test_the_fix_never_moves_a_member_off_the_grid(x, y):
    """More than a thousandth of a pixel from the grid is an error, never rounded away."""
    with pytest.raises(RuntimeError, match="off the 1.0 m grid"):
        TransformFix(snap=1.0).apply(Affine(1.0, 0.0, x, 0.0, -1.0, y), "t")


def test_the_fix_refuses_a_rotated_member():
    with pytest.raises(RuntimeError, match="rotated"):
        TransformFix(snap=1.0).apply(Affine(1.0, 0.1, 553000.0, 0.0, -1.0, 5935000.0), "t")


def test_an_offset_for_eastings_with_the_zone(http_server, tmp_path):
    """Bremerhaven's XYZ files (not built yet) write their eastings with the zone (32466000.5): GDAL's XYZ driver
    reads a member from memory with that origin, the fix takes 32 000 000 off and rounds to whole metres."""
    rows = [f"{32466000.5 + i} {5939000 - 0.5 - j} {1.234 + i + j:.3f}" for j in range(4) for i in range(4)]
    xyz = ("\r\n".join(["x y z"] + rows) + "\r\n").encode()
    name = "Gitternetz_DGM1_2015_BHV/dgm1_32466__5938_1_hb.xyz"
    body = _archive([(name, xyz, zipfile.ZIP_DEFLATED, False)])
    reader = ZipMember("DGM1 (test)", crs="EPSG:25832", fix=TransformFix(offset=(-32_000_000.0, 0.0), snap=1.0))
    transform, crs, z = _fetch(http_server, tmp_path, reader, name, body)
    assert transform == Affine(1.0, 0.0, 466000.0, 0.0, -1.0, 5939000.0) and crs.to_epsg() == 25832
    assert z.shape == (4, 4) and abs(float(z[0, 0]) - 1.234) < 0.006 and abs(float(z[3, 3]) - 7.234) < 0.006
    # Without the fix the tile lies 32 000 km east, as the file says
    transform, _, _ = _fetch(http_server, tmp_path, ZipMember("DGM1 (test)", crs="EPSG:25832"), name, body)
    assert transform.c == 32466000.0


def test_without_the_fix_the_transform_is_the_members(http_server, tmp_path):
    """The option off (Saarland's layers): the member's transform as it is, float noise and all."""
    name = "s32_553/dgm1_32_553_5934_1_hh_2022.tif"
    body = _archive([(name, _member(NOISY, np.full((10, 10), 5.0), -3.4028234663852886e38),
                      zipfile.ZIP_DEFLATED, False)])
    transform, _, _ = _fetch(http_server, tmp_path, ZipMember("DGM1 (test)", crs="EPSG:25832"), name, body)
    assert transform == NOISY
    for layer in (src.SOURCES["saarland"].nmt, src.SOURCES["saarland"].nmpt):
        assert layer.reader.fix is None


@pytest.mark.parametrize("kind, declared", [("nmt", -3.4028234663852886e38), ("nmpt", None)])
def test_the_catalogues_layers(http_server, tmp_path, kind, declared):
    """The catalogue's own readers: the DGM1's noisy origin rounded to whole metres; no data both where the member
    declares it (-3.4e38, the DGM1) and where it writes -9999 without declaring it (the bDOM1 declares none)."""
    layer = getattr(src.SOURCES["hamburg"], kind)
    values = np.full((10, 10), 7.5, dtype=np.float32)
    values[0, :] = -9999.0
    if declared is not None:
        values[1, :3] = declared
    values[5, 5] = 2.0  # the Elbe's constant: data
    name = f"s32_553/d{'g' if kind == 'nmt' else 'o'}m1_32_553_5934_1_hh_2022.tif"
    assert layer.listing.name.search(name)
    body = _archive([(name, _member(NOISY, values, declared), zipfile.ZIP_DEFLATED, False)])
    transform, crs, z = _fetch(http_server, tmp_path, layer.reader, name, body)
    assert transform == Affine(1.0, 0.0, 553000.0, 0.0, -1.0, 5935000.0) and crs.to_epsg() == 25832
    expected = np.zeros((10, 10), dtype=bool)
    expected[0, :] = True
    if declared is not None:
        expected[1, :3] = True
    assert np.array_equal(np.isnan(z), expected) and z[5, 5] == 2.0


def test_a_tile_only_in_the_surface_archive(http_server, tmp_path, monkeypatch):
    """Five tiles at the city's edge are members of the bDOM1's archive only (555_5939, 569_5949, 571_5922,
    571_5953, 578_5916: their central directories, 2026-11-15; the DGM1 has 466_5976 and 467_5976 alone). The
    catalogue's own layers on two archives served here: the terrain lists no tile there (the search's gap filling
    takes it: FABDEM, as Hamburg names no neighbour on that side), the surface one, downloaded."""
    from grid import make_grid
    hh = src.SOURCES["hamburg"]
    flat = np.full((1000, 1000), 10.0)
    both = Affine(1.0, 0.0, 553000.0, 0.0, -1.0, 5935000.0)
    only = Affine(1.0, 0.0, 571000.0, 0.0, -1.0, 5923000.0)
    archives = {
        "dgm": _archive([("s32_553/dgm1_32_553_5934_1_hh_2022.tif", _member(both, flat, None), zipfile.ZIP_DEFLATED,
                          False)]),
        "dom": _archive([("s32_553/dom1_32_553_5934_1_hh_2022.tif", _member(both, flat, None), zipfile.ZIP_DEFLATED,
                          False),
                         ("s32_571/dom1_32_571_5922_1_hh_2022.tif", _member(only, flat + 5, None),
                          zipfile.ZIP_DEFLATED, False)])}
    for kind, layer in (("dgm", hh.nmt), ("dom", hh.nmpt)):
        _serve(http_server, f"/{kind}.zip", archives[kind])
        url = http_server.url(f"/{kind}.zip")  # only the archive's address replaced
        monkeypatch.setattr(layer.listing, "urls", [url])
        monkeypatch.setattr(layer.listing, "url", url)
    cache_dir = str(tmp_path / "cache")
    grid = make_grid((571100, 5922100, 571900, 5922900), 1.0, "EPSG:25832")
    for layer in (hh.nmt, hh.nmpt):
        layer._use(cache_dir)
    assert hh.nmt.tiles(grid) == []
    (tile,) = hh.nmpt.tiles(grid)
    assert (tile.east, tile.north) == (571, 5922)
    hh.nmpt.download(grid, cache_dir, None, "surface")
    with rio.open(hh.nmpt.tile_path(cache_dir, tile)) as cached:
        assert cached.transform.c == 571000.0 and float(cached.read(1).max()) == 15.0
    assert hh.fallbacks == ["europe"] and "lower_saxony" not in hh.neighbours


def test_source():
    hh = src.SOURCES["hamburg"]
    assert hh.regions == ("de-hh",) and hh.countries == ("de",) and hh.crs == "EPSG:25832"
    assert hh.grid_origin == (0.0, 0.0) and hh.fallbacks == ["europe"] and hh.ortho is None
    assert isinstance(hh.nmt, ZipMemberTiles) and isinstance(hh.nmpt, ZipMemberTiles)
    assert hh.nmt.folder == "hamburg/dgm1-2022" and hh.nmpt.folder == "hamburg/bdom1-2022"
    assert hh.nmt.metalinks == (germany.HH_DGM1,) and hh.nmpt.metalinks == (germany.HH_BDOM1,)
    assert hh.nmt.reader.fix == hh.nmpt.reader.fix == TransformFix(snap=1.0)
    assert hh.nmt.floor is None and hh.nmt.ttl_days is None
    # The archives' own member names (their central directories, read 2026-11-15)
    for name, east, north in (("dgm1_hh_2022-04-30/dgm1_hh_2022/s32_553/dgm1_32_553_5934_1_hh_2022.tif", "553", "5934"),
                              ("dgm1_hh_2022-04-30/dgm1_hh_2022/S32_466/dgm1_32_466_5974_1_hh_2022.tif", "466", "5974")):
        match = hh.nmt.listing.name.search(name)
        assert match and match.group("east", "north", "year") == (east, north, "2022")
        assert not hh.nmpt.listing.name.search(name)
    assert hh.nmpt.listing.name.search("s32_466/dom1_32_466_5973_1_hh_2022.tif")
    assert not hh.nmt.listing.name.search("dgm1_hh_2022-04-30/dgm1_hh_2022/dgm1_hh_2023-02-09.csv")
    assert src.HOST_SLOTS_OF["www.daten-hamburg.de"] == 2
    assert [c.data for c in hh.credits] == ["DGM1 / bDOM1 (LGV, Hamburg)"]
    # Lower Saxony is full (six neighbours): only Schleswig-Holstein, both ways
    assert hh.neighbours == ("schleswig_holstein",) and "hamburg" in src.SOURCES["schleswig_holstein"].neighbours
    assert "hamburg" not in src.SOURCES["lower_saxony"].neighbours and len(src.SOURCES["lower_saxony"].neighbours) == 6
    assert hh.map_areas() == ("de-hh",) and "de-hh" in src.AREA_NAMES
    from sources import probe
    assert probe.strategy(hh.nmt) == "zip"
    ids = [s.id for s in germany.SOURCES]
    assert ids.index("hamburg") < ids.index("lower_saxony") < ids.index("schleswig_holstein")


@pytest.mark.parametrize("lat, lon, inside", [
    (53.5585, 9.8070, True),    # Blankenese
    (53.5500, 9.9930, True),    # the Binnenalster
    (53.4600, 9.9800, True),    # Harburg
    (53.4880, 10.2150, True),   # Bergedorf
    (53.6300, 9.9880, True),    # the airport
    (53.9150, 8.5000, True),    # Neuwerk
    (53.4000, 10.0500, False),  # Seevetal-Maschen (Lower Saxony)
    (53.4650, 9.7950, False),   # Neu Wulmstorf (Lower Saxony)
    (53.4700, 9.7300, False),   # east of Buxtehude (Lower Saxony)
    (53.7000, 10.0000, False),  # Norderstedt (Schleswig-Holstein)
    (53.6600, 9.8000, False),   # Pinneberg (Schleswig-Holstein)
    (53.4700, 9.6900, False),   # Stade's marshes (Lower Saxony)
    (53.7700, 9.9000, False),   # Quickborn (Schleswig-Holstein)
    (53.2500, 10.4100, False),  # Lüneburg
])
def test_offline_boxes(lat, lon, inside):
    """Offline, the first box holding a point wins: Hamburg's before Lower Saxony's and Schleswig-Holstein's, so its
    boxes keep off their towns at the city's edges (Hamburg has no tiles there and does not name Lower Saxony)."""
    found = next((code for code, (s, n, w, e) in src.OFFLINE_BOXES if s <= lat <= n and w <= lon <= e), None)
    assert (found == "de-hh") == inside, found
