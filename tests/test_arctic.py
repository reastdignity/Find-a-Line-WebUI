"""The Arctic sources (sources/catalogue/arctic.py) on ArcticDEM v4.1: the subtile of a block computed from its
position, the sources chosen in Greenland, Svalbard and Jan Mayen (NO-21, NO-22) and Nunavut (CA-NU) only (Nominatim's
reverse answers recorded on 2026-11-03: tests/data/recorded/nominatim/reverse-arctic.json), their offline boxes,
the open gap filler copernicus, and the probe of a layer with a geoid (local server)."""

import json
import math
import os
import sys

import numpy as np
import pytest
import rasterio as rio
from rasterio.transform import from_origin
from rasterio.warp import transform as warp

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
import osm  # noqa: E402
import sources as src  # noqa: E402
from sources import vertical  # noqa: E402
from sources.catalogue import arctic  # noqa: E402
from sources.layers.fileblocks import FileBlocks  # noqa: E402

RECORDED = os.path.join(REPO, "tests", "data", "recorded", "nominatim", "reverse-arctic.json")
TASERMIUT = (60.3786, -44.5502)    # GL (R58)
UUMMANNAQ = (70.7073, -52.1184)    # GL
LONGYEARBYEN = (78.1913, 15.1801)  # NO, NO-21 (R59)
JAN_MAYEN = (71.08, -8.16)         # NO, NO-22 (Beerenberg)
SAM_FORD = (70.7175, -71.4268)     # CA, CA-NU (R60)
IQALUIT = (63.75, -68.52)          # CA, CA-NU
THOR = (66.54, -65.326)            # CA, CA-NU (Mt Thor's west face: voids)
YELLOWKNIFE = (62.45, -114.37)     # CA, CA-NT
PREIKESTOLEN = (58.9864, 6.1904)   # NO, NO-11
# Subtiles read or listed in the research of 2026-11-02 (PGC's STAC items, reads of the computed names)
SUBTILES = {THOR: "16_32_2_1", (71.0, -8.3): "24_53_1_1", (74.43, 19.0): "33_56_2_1", (59.78, -43.9): "07_41_2_2",
            TASERMIUT: "08_41_1_1", LONGYEARBYEN: "34_52_2_1", SAM_FORD: "22_31_1_2"}


@pytest.fixture
def recorded(monkeypatch):
    with open(RECORDED, encoding="utf-8") as f:
        answers = {(r["query"]["lat"], r["query"]["lon"], r["query"]["zoom"]): r["answer"] for r in json.load(f)}
    monkeypatch.setattr(osm, "reverse", lambda lat, lon, cache_dir, **params:
                        answers[(round(lat, 5), round(lon, 5), params["zoom"])])


def _block(lat, lon):
    (x,), (y,) = warp("EPSG:4326", arctic.ARCTIC_CRS, [lon], [lat])
    return math.floor(x / arctic.ARCTIC_BLOCK_M), math.floor(y / arctic.ARCTIC_BLOCK_M)


@pytest.mark.parametrize("point", sorted(SUBTILES))
def test_subtile_of_a_block(point):
    request = arctic.ARCTIC_DEM_2M.index.request(_block(*point))
    (name, url, year), = request.files
    tile = SUBTILES[point][:5]
    assert name == f"{SUBTILES[point]}_2m_v4.1_dem.tif" and year == 0
    assert url == f"https://pgc-opendata-dems.s3.us-west-2.amazonaws.com/arcticdem/mosaics/v4.1/2m/{tile}/{name}"
    assert request.crs == "EPSG:3413" and request.shape == (1000, 1000)
    assert request.transform.a == 2.0 and request.transform.c % 2000 == 0 and request.transform.f % 2000 == 0


def test_blocks_lie_inside_one_subtile():
    """Every block of 2 km lies in the core of one 50 km subtile: its corners name the same file; blocks beyond
    the 82 x 82 tiles have none (missing without a request)."""
    files = arctic.arcticdem_files(1.0)  # the subtile of a point (a block of 1 m)
    rng = np.random.default_rng(1)
    for i, j in rng.integers(-2050, 2050, size=(200, 2)):
        x, y = i * 2000, j * 2000
        names = {files(math.floor(px), math.floor(py))[0][0] for px, py in
                 ((x, y), (x + 1999, y), (x, y + 1999), (x + 1999, y + 1999))}
        assert names == {arctic.ARCTIC_DEM_2M.index.request((i, j)).files[0][0]}
    index = arctic.ARCTIC_DEM_2M.index
    assert index.request((2050, 0)).files == [] and index.request((-2051, 0)).files == []
    assert index.request((2049, 2049)).files[0][0] == "81_81_2_2_2m_v4.1_dem.tif"
    assert index.request((-2050, -2050)).files[0][0] == "00_00_1_1_2m_v4.1_dem.tif"


def test_the_layer():
    layer = arctic.ARCTIC_DEM_2M
    assert layer.geoid is vertical.EGM2008 and layer.folder.endswith("-egm08") and layer.ttl_days is None
    assert layer.reader.geoid is vertical.EGM2008
    for sid in ("greenland", "svalbard", "nunavut"):
        source = src.SOURCES[sid]
        assert source.nmt is layer and source.nmpt is None and source.crs is None  # UTM of the centre
        assert source.default_resolution == 2.0
        for text in (source.note, source.description, source.name, layer.description):
            text.encode("cp1250")  # printed to a Windows console
        assert "EGM2008" in source.note and "30 m" in source.note
    assert src.SOURCES["greenland"].fallbacks == ["copernicus"] and src.SOURCES["svalbard"].fallbacks == ["copernicus"]
    assert src.SOURCES["nunavut"].fallbacks == ["mrdem30"]
    assert src.SOURCES["nunavut"].neighbours == ("canada",) and "nunavut" in src.SOURCES["canada"].neighbours
    assert src.SOURCES["svalbard"].ortho.base_max_zoom == 17 and src.SOURCES["greenland"].ortho is None


def test_copernicus_source():
    """GLO-30 as an open source of its own: the folder of europe's surface model (nothing downloaded twice), no
    fallback (FABDEM's terms are not open), anywhere by hand."""
    source = src.SOURCES["copernicus"]
    assert source.nmt is src.SOURCES["europe"].nmpt and source.nmpt is None
    assert source.fallbacks == [] and source.countries == () and source.offline == ()
    assert source.credits[0].data == "Copernicus DEM GLO-30"
    assert src.choose_source("copernicus", 10.0, 10.0, "unused") == (source, "--source copernicus")


def test_chosen_in_their_regions(tmp_path, recorded):
    cache_dir = str(tmp_path)
    expected = {TASERMIUT: ("greenland", "GL"), UUMMANNAQ: ("greenland", "GL"),
                LONGYEARBYEN: ("svalbard", "NO-21"), JAN_MAYEN: ("svalbard", "NO-22"),
                SAM_FORD: ("nunavut", "CA-NU"), IQALUIT: ("nunavut", "CA-NU"), THOR: ("nunavut", "CA-NU"),
                YELLOWKNIFE: ("canada", "CA"), PREIKESTOLEN: ("norway", "NO")}
    for point, (sid, where) in expected.items():
        assert src.choose_source("auto", *point, cache_dir) == (src.SOURCES[sid], f"the centre is in {where}"), point


def test_offline_boxes(monkeypatch, tmp_path):
    """Offline, the boxes give Greenland, the Norwegian regions and Nunavut (before Canada's box, which holds
    north-western Greenland and all of Nunavut); Iceland stays out of Greenland's."""
    def offline(*args, **kwargs):
        raise ValueError("offline")
    monkeypatch.setattr(osm, "reverse", offline)
    cache_dir = str(tmp_path)
    for point, sid in ((TASERMIUT, "greenland"), (UUMMANNAQ, "greenland"), ((77.47, -69.23), "greenland"),
                       ((81.6, -61.5), "greenland"), (LONGYEARBYEN, "svalbard"), (JAN_MAYEN, "svalbard"),
                       (SAM_FORD, "nunavut"), (IQALUIT, "nunavut"), (THOR, "nunavut"), ((79.0, -76.0), "nunavut"),
                       (YELLOWKNIFE, "canada")):
        assert src.choose_source("auto", *point, cache_dir)[0].id == sid, point
    for point in ((64.15, -21.94), (65.68, -18.09), (63.4, -19.0)):  # Iceland: no box of Greenland's
        assert src.choose.country_code(*point, cache_dir) != "gl", point


def test_probe_notes_the_geoid(http_server, tmp_path, capsys, monkeypatch):
    """A FileBlocks layer with a geoid: the window as for any, and its grid (not cached: a HEAD of its address
    with its size, nothing downloaded; cached: said so); a grid of another size at its address fails."""
    from sources import probe
    left, top = -150000.0, -2400000.0
    band = np.full((200, 200), 500.0, np.float32)
    os.makedirs(tmp_path / "files")
    with rio.open(tmp_path / "files" / "a.tif", "w", driver="GTiff", width=200, height=200, count=1, dtype="float32",
                  crs="EPSG:3413", nodata=-9999.0, transform=from_origin(left, top, 2.0, 2.0)) as dst:
        dst.write(band, 1)
    http_server.add_folder("/files", str(tmp_path / "files"))
    http_server.add("/grids/g.tif", b"x" * 1234, "image/tiff")
    geoid = vertical.Geoid("Test geoid", "tg", http_server.url("/grids/g.tif"), "0" * 64, 1234, "geoid/test", "")
    layer = FileBlocks("H", "test/h-tg", "EPSG:3413", 2.0, 40, http_server.url("/files/a.tif"), geoid=geoid)
    (lon,), (lat,) = warp("EPSG:3413", "EPSG:4326", [left + 200], [top - 200])
    sources = {"there": src.Source(id="there", name="there", description="there", nmt=layer, crs="EPSG:3413",
                                   sample=(lat, lon), default_resolution=2.0)}
    cache_dir = str(tmp_path / "cache")
    assert probe.run(cache_dir, ["there"], sources=sources) == 0
    out = capsys.readouterr().out
    assert "window 100% with data" in out and "Test geoid grid not cached" in out
    assert [r.method for r in http_server.requests("/grids/")] == ["HEAD"]
    os.makedirs(os.path.join(cache_dir, "geoid", "test"))
    with open(os.path.join(cache_dir, "geoid", "test", "g.tif"), "wb") as f:
        f.write(b"x" * 1234)
    assert probe.run(cache_dir, ["there"], sources=sources) == 0
    assert "Test geoid grid cached" in capsys.readouterr().out
    geoid.size = 999
    os.remove(os.path.join(cache_dir, "geoid", "test", "g.tif"))
    assert probe.run(cache_dir, ["there"], sources=sources) == 1
    assert "1234 bytes (999 expected)" in capsys.readouterr().out
