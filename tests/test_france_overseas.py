"""France's overseas territories (sources/catalogue/france.py OVERSEAS: RGE ALTI 1 m of Guadeloupe with
Saint-Barthélemy and Saint-Martin, Martinique, French Guiana and Saint-Pierre-et-Miquelon from IGN's WMS-R): their
layers, the half-metre pixel edges of the Antilles' layers on recorded answers (tests/data/recorded/wmsr/overseas/,
served by tests/http_server.py), and which source --source auto takes there."""

import json
import os
import sys
from urllib.parse import urlsplit

import numpy as np
import pytest
import rasterio as rio

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
import osm  # noqa: E402
import sources as src  # noqa: E402
from sources import net  # noqa: E402
from sources.catalogue import france  # noqa: E402
from sources.layers.wmsr import WmsrTiles  # noqa: E402
from tile_values import same_tile  # noqa: E402

RECORDED = os.path.join(REPO, "tests", "data", "recorded", "wmsr", "overseas")
GLP = "RGEALTI-MNT_PYR-ZIP_GLP_WGS84UTM20_WMS"
# The recorded boxes (EPSG:32620, 32 m on the layer's pixel edges): the Soufrière and Sint Maarten
SOUFRIERE = (642912.5, 1774240.5)
SINT_MAARTEN = (493632.5, 1993504.5)
OVERSEAS = {"france_guadeloupe": ("RGEALTI-MNT_PYR-ZIP_GLP_WGS84UTM20_WMS", "EPSG:32620", (0.5, 0.5)),
            "france_martinique": ("RGEALTI-MNT_PYR-ZIP_MTQ_WGS84UTM20_WMS", "EPSG:32620", (0.5, 0.5)),
            "france_guiana": ("RGEALTI-MNT_PYR-ZIP_GUF_UTM22RGFG95_WMS", "EPSG:2972", (0.0, 0.0)),
            "france_spm": ("RGEALTI-MNT_PYR-ZIP_SPM_RGSPM06U21_WMS", "EPSG:4467", (0.5, 0.5))}


@pytest.fixture
def service(http_server, monkeypatch):
    with open(os.path.join(RECORDED, "requests.json"), encoding="utf-8") as f:
        for answer in json.load(f)["answers"]:
            with open(os.path.join(RECORDED, answer["body"]), "rb") as body:
                parts = urlsplit(answer["url"])
                http_server.add(f"{parts.path}?{parts.query}", body.read(), answer["content_type"],
                                answer["status"])
    monkeypatch.setattr(net, "_sleep", lambda attempt: None)
    return http_server


def _answer(n):
    with rio.open(os.path.join(RECORDED, f"{n:03d}.tif")) as raster:
        return raster.read(1, masked=True).astype(np.float32).filled(np.nan), raster.transform


def _layer(server) -> WmsrTiles:
    # Guadeloupe's layer as declared, on 32 m tiles so a recorded box is one tile
    return WmsrTiles("RGE ALTI test", server.url("/wms-r/wms"), GLP, "EPSG:32620", "france/test-glp/live",
                     native_res=1.0, fetch_res=(1.0,), tile_m=32, origin=(0.5, 0.5))


def test_the_overseas_layers():
    for sid, (layer, crs, origin) in OVERSEAS.items():
        s = src.SOURCES[sid]
        assert isinstance(s.nmt, WmsrTiles) and s.nmt.reader.layer == layer and s.nmpt is None, sid
        assert s.crs == s.nmt.crs == crs and s.nmt.origin == origin, sid
        assert s.grid_origin == origin, sid  # the working grid's edges on the stored pixels' edges
        assert s.default_resolution == 1.0 and s.fallbacks == ["europe"] and s.neighbours == (), sid
        assert s.nmt.folder.startswith("france/rgealti-1m-") and s.nmt.folder.endswith("/live"), sid
        assert s.ortho is src.SOURCES["france"].ortho and s.credits == src.SOURCES["france_rgealti"].credits, sid
        assert s.countries == ("fr",) and not s.regions, sid
        for area in s.map_areas():
            assert area in src.AREA_NAMES, (sid, area)
    assert src.SOURCES["france_guadeloupe"].map_areas() == ("fr-gp", "bl", "mf")


# Per layer the recorded 32 m box on its declared pixel edges: (source, the answer at 1 m, at 0.5 m, its corner)
ALIGNMENT = [("france_guadeloupe", 1, 2, SOUFRIERE), ("france_martinique", 4, 5, (704544.5, 1626528.5)),
             ("france_guiana", 6, 7, (359168.0, 539520.0)), ("france_spm", 8, 9, (562592.5, 5181024.5))]


def test_the_alignment_recordings_are_the_layers_requests():
    """Each recording is the GetMap its layer writes for that box (the BBOX on the declared origin)."""
    with open(os.path.join(RECORDED, "requests.json"), encoding="utf-8") as f:
        urls = {a["body"]: a["url"] for a in json.load(f)["answers"]}
    from sources.readers.wmsr import MapRequest
    from urllib.parse import parse_qsl
    for sid, one, half, (x, y) in ALIGNMENT:
        layer = src.SOURCES[sid].nmt
        assert ((x - layer.origin[0]) % 32, (y - layer.origin[1]) % 32) == (0, 0), sid
        for n, px in ((one, 32), (half, 64)):
            asked = dict(parse_qsl(urlsplit(urls[f"{n:03d}.tif"]).query, keep_blank_values=True))
            assert asked == dict(layer.reader.getmap_params(MapRequest(x, y, x + 32, y + 32, px, px))), (sid, n)


@pytest.mark.parametrize("sid, one, half, corner", ALIGNMENT)
def test_the_declared_pixel_edges(sid, one, half, corner):
    """The 1 m answer on the layer's declared edges (half metres in the Antilles and Saint-Pierre-et-Miquelon,
    whole metres in French Guiana) is the stored pixels: at 0.5 m on the same box the server repeats each of them in
    a 2 x 2 block (nearest), which starts on those edges. Declared half a metre off, the blocks would straddle the
    0.5 m pixel pairs and differ from the 1 m answer."""
    a, transform = _answer(one)
    b, _ = _answer(half)
    assert (transform.c, transform.f) == (corner[0], corner[1] + 32)
    assert np.isfinite(a).all() and np.isfinite(b).all()
    assert np.ptp(a) > 1  # relief: equal blocks are not flat ground
    for dy in (0, 1):
        for dx in (0, 1):
            assert np.array_equal(b[dy::2, dx::2], a), (sid, dy, dx)


def test_a_tile_on_the_half_metre_edges(service, tmp_path):
    layer = _layer(service)
    i, j = round((SOUFRIERE[0] - 0.5) / 32), round((SOUFRIERE[1] - 0.5) / 32)
    assert layer.index.request((1.0, i, j))[:4] == (SOUFRIERE[0], SOUFRIERE[1], SOUFRIERE[0] + 32,
                                                    SOUFRIERE[1] + 32)
    path = layer.tile_path(str(tmp_path), (1.0, i, j))
    assert path.replace(os.sep, "/").endswith(f"france/test-glp/live/epsg32620-1m-32px-tif-o0.5_0.5/{i}_{j}.tif")
    assert layer.download_tile((1.0, i, j), path).received > 0
    with rio.open(path) as raster:
        assert raster.transform.c == SOUFRIERE[0] and raster.transform.f == SOUFRIERE[1] + 32
        assert raster.crs.to_epsg() == 32620
        cached = raster.read(1, masked=True).astype(np.float32).filled(np.nan)
    assert same_tile(cached, _answer(1)[0])


def test_sint_maarten_is_missing(service, tmp_path):
    """The Dutch side of the island: every pixel nodata (-99999, HTTP 200), so no tile and the fallback fills it."""
    layer = _layer(service)
    i, j = round((SINT_MAARTEN[0] - 0.5) / 32), round((SINT_MAARTEN[1] - 0.5) / 32)
    path = layer.tile_path(str(tmp_path), (1.0, i, j))
    assert layer.download_tile((1.0, i, j), path).received == 0
    assert not os.path.exists(path)


# La Réunion: the recorded 32 m box at Cilaos (EPSG:2975, on whole metres) and one at sea off Cap Méchant
CILAOS = (339552, 7662688)
REU_SEA = (370432, 7633056)
# (the catalogue's layer, the box's corner, its pixels a side, the recording)
REU_RECORDED = [(france.REU_MNT, CILAOS, 64, 10), (france.REU_MNT, CILAOS, 128, 11), (france.REU_MNT, CILAOS, 32, 12),
                (france.REU_MNS, CILAOS, 64, 13), (france.REU_MNT, REU_SEA, 64, 14),
                (france.REU_RGEALTI, (CILAOS[0] + 0.5, CILAOS[1] + 0.5), 32, 15),
                (france.REU_RGEALTI, (CILAOS[0] + 0.5, CILAOS[1] + 0.5), 64, 16)]


def test_the_reunion_layers():
    """The island's LiDAR HD MNT and MNS as the mainland's (0.5 m, fetched at 1 m for a grid of 1 m or more) on
    pixel edges at multiples of 0.5 m (origin 0, not the mainland's .75 / .25), and its RGE ALTI on half metres."""
    for layer, kind in ((france.REU_MNT, "MNT"), (france.REU_MNS, "MNS")):
        assert isinstance(layer, WmsrTiles)
        assert layer.reader.layer == f"IGNF_LIDAR-HD_{kind}_ELEVATION.ELEVATIONGRIDCOVERAGE.RGR92UTM40S"
        assert layer.crs == layer.reader.crs == "EPSG:2975" and layer.origin == (0.0, 0.0)
        assert layer.native_res == 0.5 and layer.fetch_res == (0.5, 1.0) and layer.tile_m == 1000
        assert layer.folder == f"france/lidarhd-{kind.lower()}-reu/live"
        assert layer.index.resolution(1.0) == 1.0 and layer.index.resolution(0.5) == 0.5
    rge = france.REU_RGEALTI
    assert rge.reader.layer == "RGEALTI-MNT_PYR-ZIP_REU_RGR92UTM40S_WMS" and rge.crs == "EPSG:2975"
    assert rge.origin == (0.5, 0.5) and rge.fetch_res == (1.0,) and rge.folder == "france/rgealti-1m-reu/live"
    # The mainland's layers keep their names, CRS, edges and folders
    assert france.FR_MNT.reader.layer == "IGNF_LIDAR-HD_MNT_ELEVATION.ELEVATIONGRIDCOVERAGE.LAMB93"
    assert france.FR_MNT.origin == (-0.25, 0.25) and france.FR_MNT.folder == "france/lidarhd-mnt/live"
    assert france.FR_MNS.crs == "EPSG:2154" and france.FR_MNS.folder == "france/lidarhd-mns/live"


def test_the_reunion_recordings_are_the_layers_requests():
    with open(os.path.join(RECORDED, "requests.json"), encoding="utf-8") as f:
        urls = {a["body"]: a["url"] for a in json.load(f)["answers"]}
    from sources.readers.wmsr import MapRequest
    from urllib.parse import parse_qsl
    for layer, (x, y), px, n in REU_RECORDED:
        asked = dict(parse_qsl(urlsplit(urls[f"{n:03d}.tif"]).query, keep_blank_values=True))
        assert asked == dict(layer.reader.getmap_params(MapRequest(x, y, x + 32, y + 32, px, px))), n


def test_the_reunion_lidar_pixel_edges():
    """At 0.25 m on the box the server repeats each 0.5 m pixel in a 2 x 2 block starting on the box's whole metres:
    the stored pixels' edges lie on multiples of 0.5 m. The 1 m answer is the mean of the 2 x 2 pixels of 0.5 m
    (within 1e-4 m: IGN's float rounding)."""
    half, transform = _answer(10)
    quarter, _ = _answer(11)
    one, _ = _answer(12)
    assert (transform.c, transform.f) == (CILAOS[0], CILAOS[1] + 32)
    assert np.isfinite(half).all() and np.ptp(half) > 10  # the rampart's relief
    for dy in (0, 1):
        for dx in (0, 1):
            assert np.array_equal(quarter[dy::2, dx::2], half), (dy, dx)
    assert not np.array_equal(quarter[1:-1:2, 1:-1:2], quarter[2::2, 2::2])  # blocks a quarter off would be equal
    mean = (half[0::2, 0::2].astype(np.float64) + half[1::2, 0::2] + half[0::2, 1::2] + half[1::2, 1::2]) / 4
    assert np.abs(mean - one).max() < 1e-4
    # RGE ALTI: centres on whole metres (edges on half metres), 2 x 2 blocks at 0.5 m
    rge_one, rge_transform = _answer(15)
    rge_half, _ = _answer(16)
    assert (rge_transform.c, rge_transform.f) == (CILAOS[0] + 0.5, CILAOS[1] + 32.5)
    for dy in (0, 1):
        for dx in (0, 1):
            assert np.array_equal(rge_half[dy::2, dx::2], rge_one), (dy, dx)


@pytest.mark.parametrize("layer, corner, px, n", [r for r in REU_RECORDED if r[3] in (10, 12, 13, 15)])
def test_a_reunion_tile_from_the_catalogues_reader(service, tmp_path, monkeypatch, layer, corner, px, n):
    """The catalogue's own reader (only the service's address replaced) keeps the answer as it came: its CRS forced
    to EPSG:2975 (the answers name EPSG:32740), its nodata (-9999, RGE ALTI's -99999) none here."""
    from sources.readers.wmsr import MapRequest
    monkeypatch.setattr(layer.reader, "service_url", service.url("/wms-r/wms"))
    path = str(tmp_path / f"{n}.tif")
    x, y = corner
    assert layer.reader.fetch(MapRequest(x, y, x + 32, y + 32, px, px), path).received > 0
    with rio.open(path) as raster:
        assert raster.crs.to_epsg() == 2975
        assert (raster.transform.c, raster.transform.f, raster.transform.a) == (x, y + 32, 32 / px)
        cached = raster.read(1, masked=True).astype(np.float32).filled(np.nan)
    assert np.isfinite(cached).all() and same_tile(cached, _answer(n)[0])


def test_the_reunion_sea_is_missing(service, tmp_path, monkeypatch):
    """The sea off Cap Méchant: every pixel -9999 (HTTP 200), so no tile: the water filling takes it."""
    from sources.readers.wmsr import MapRequest
    layer = france.REU_MNT
    monkeypatch.setattr(layer.reader, "service_url", service.url("/wms-r/wms"))
    path = str(tmp_path / "sea.tif")
    x, y = REU_SEA
    assert layer.reader.fetch(MapRequest(x, y, x + 32, y + 32, 64, 64), path).received == 0
    assert not os.path.exists(path)


@pytest.mark.parametrize("grid_res, fetched", [(0.5, 0.5), (1.0, 1.0), (2.0, 1.0), (5.0, 1.0), (10.0, 1.0)])
def test_the_reunion_fetch_resolution(grid_res, fetched):
    """LiDAR HD is fetched at 0.5 m only for a grid finer than 1 m; at 1, 2, 5 and 10 m the 1 m answers (the
    service's 2 x 2 means) are cached and averaged further by the mosaic. The RGE ALTI only at 1 m."""
    from grid import make_grid
    grid = make_grid((339100, 7662100, 339900, 7662900), grid_res, "EPSG:2975")
    for layer in (france.REU_MNT, france.REU_MNS):
        assert layer.index.resolution(grid_res) == fetched
        assert {t[0] for t in layer.tiles(grid)} == {fetched}
    assert {t[0] for t in france.REU_RGEALTI.tiles(grid)} == {1.0}


def _geotiff(values: np.ndarray, left: float, top: float, res: float, nodata: float) -> bytes:
    """A GeoTIFF answer as IGN's WMS-R gives one: float32, its nodata, the CRS IGN names (EPSG:32740)."""
    from rasterio.transform import from_origin
    with rio.io.MemoryFile() as memfile:
        with memfile.open(driver="GTiff", width=values.shape[1], height=values.shape[0], count=1, dtype="float32",
                          crs="EPSG:32740", transform=from_origin(left, top, res, res), nodata=nodata) as dst:
            dst.write(values.astype(np.float32), 1)
        return memfile.read()


def _serve_tile(server, layer, tile, values, nodata):
    """The GetMap the catalogue's layer writes for tile, answered by values (the query matched exactly)."""
    from urllib.parse import urlencode
    request = layer.index.request(tile)
    query = urlencode(layer.reader.getmap_params(request))
    server.add(f"/wms-r/wms?{query}", _geotiff(values, request.left, request.top, (request.right - request.left)
                                                / request.width, nodata), "image/geotiff")


def test_the_reunion_chain_in_action(http_server, tmp_path, monkeypatch):
    """The catalogue's own layers on served answers: LiDAR HD answers every pixel -9999 (no tile), so the whole grid
    is a gap; the RGE ALTI filler (france_reunion_rgealti, the first of france_reunion's fallbacks) fills its west
    half, its east half answered -99999 (no data, never a height); what is left goes to the next fallback (europe:
    here a local stand-in, as FABDEM is not served)."""
    from grid import make_grid
    from test_italy import _File, _local
    reunion = src.SOURCES["france_reunion"]
    assert reunion.fallbacks == ["france_reunion_rgealti", "europe"]
    filler = src.SOURCES[reunion.fallbacks[0]]
    for layer in (france.REU_MNT, france.REU_MNS, france.REU_RGEALTI):
        monkeypatch.setattr(layer.reader, "service_url", http_server.url("/wms-r/wms"))
    monkeypatch.setattr(net, "_sleep", lambda attempt: None)
    grid = make_grid((339100, 7662100, 339900, 7662900), 10.0, reunion.crs, reunion.grid_origin)
    lidar_tile, rge_tile = (1.0, 339, 7662), (1.0, 339, 7662)
    assert france.REU_MNT.tiles(grid) == [lidar_tile] and france.REU_RGEALTI.tiles(grid) == [rge_tile]
    for layer in (france.REU_MNT, france.REU_MNS):
        _serve_tile(http_server, layer, lidar_tile, np.full((1000, 1000), -9999.0), -9999.0)
    rge = np.full((1000, 1000), 800.0)
    rge[:, 500:] = -99999.0
    _serve_tile(http_server, france.REU_RGEALTI, rge_tile, rge, -99999.0)
    cache_dir = str(tmp_path / "cache")
    nmt = src.mosaic.prepare_layer(france.REU_MNT, grid, cache_dir, str(tmp_path / "nmt.npy"), "terrain")
    assert np.isnan(np.load(nmt)).all()  # all -9999: missing, no tile
    shape = (grid.height, grid.width)
    europe = src.Source(id="europe_test", name="europe test", description="e", fallback=None,
                        credits=(src.FABDEM_CREDIT,),
                        nmt=_File("fabdem", _local(str(tmp_path / "fabdem.tif"), grid, np.full(shape, 500.0, np.float32))))
    europe.nmt.credit = src.FABDEM_CREDIT
    src.mosaic.used_data.clear()
    try:
        _, counts = src.filling.fill_gaps_chain(nmt, None, grid, [filler, europe], cache_dir, str(tmp_path / "gap.npy"))
    finally:
        src.mosaic.used_data.clear()
    z = np.load(nmt)
    assert counts[0][0] is filler and counts[0][1] > 0 and counts[1][1] > 0
    assert not np.isnan(z).any()
    # The RGE ALTI's west half (339000.5-339500.5 E): its height, never -99999; the east half from the next fallback
    west = grid.left + (np.arange(grid.width) + 0.5) * grid.res < 339490
    east = grid.left + (np.arange(grid.width) + 0.5) * grid.res > 339510
    assert np.allclose(z[:, west], 800.0) and (z > 0).all()
    assert counts[0][1] + counts[1][1] == z.size and int(east.sum()) * grid.height <= counts[1][1]


def test_the_reunion_sources():
    """france_reunion: the island's LiDAR HD on a grid with edges on whole metres, gaps from its RGE ALTI, then
    FABDEM / Copernicus; the filler a source of its own, on its half-metre edges, with no coverage of its own."""
    s, filler = src.SOURCES["france_reunion"], src.SOURCES["france_reunion_rgealti"]
    assert s.nmt is france.REU_MNT and s.nmpt is france.REU_MNS and filler.nmt is france.REU_RGEALTI
    assert s.crs == filler.crs == "EPSG:2975" and s.grid_origin == (0.0, 0.0) and filler.grid_origin == (0.5, 0.5)
    assert s.default_resolution == 1.0 and s.fallbacks == ["france_reunion_rgealti", "europe"]
    assert filler.fallbacks == ["europe"] and s.neighbours == () == filler.neighbours
    assert s.countries == filler.countries == ("fr",) and s.bbox == filler.bbox == (-21.42, -20.84, 55.20, 55.86)
    assert s.offline == (("fr", s.bbox),) and not filler.offline
    assert s.credits == src.SOURCES["france"].credits and filler.credits == src.SOURCES["france_rgealti"].credits
    assert s.ortho is filler.ortho is src.SOURCES["france"].ortho
    assert s.map_areas() == ("fr-re",) and "fr-re" in src.AREA_NAMES and filler.coverage is None
    assert s.covers(*s.sample) and filler.covers(*filler.sample)
    # No other "fr" source's box reaches the island, nor the island's box any other's
    others = [box for o in src.SOURCES.values() if o.id not in (s.id, filler.id) and "fr" in o.countries
              for box in [o.bbox] + [b for _, b in o.offline] if box]
    south, north, west, east = s.bbox
    assert not [b for b in others if b[0] <= north and b[1] >= south and b[2] <= east and b[3] >= west]


# (lat, lon, the country Nominatim names at zoom 3 (asked 2026-11-15), the source --source auto takes)
PLACES = [(16.044, -61.664, "fr", "france_guadeloupe"), (17.90, -62.83, "fr", "france_guadeloupe"),
          (18.08, -63.05, "fr", "france_guadeloupe"), (18.03, -63.06, "nl", "europe"),
          (14.705, -61.100, "fr", "france_martinique"), (4.93, -52.33, "fr", "france_guiana"),
          (46.78, -56.18, "fr", "france_spm"), (47.05, -56.38, "fr", "france_spm"),
          (-21.11, 55.53, "fr", "france_reunion"), (-21.373, 55.715, "fr", "france_reunion"),  # Cap Méchant
          (-12.78, 45.23, "fr", "europe"),  # Mayotte: not declared
          (43.7655, 6.3580, "fr", "france")]


@pytest.mark.parametrize("lat, lon, code, expected", PLACES)
def test_the_source_of_a_place(monkeypatch, tmp_path, lat, lon, code, expected):
    monkeypatch.setattr(osm, "reverse", lambda *args, **kwargs: {"address": {"country_code": code}})
    assert src.choose.choose_source("auto", lat, lon, str(tmp_path))[0].id == expected


# Mayotte's "europe" offline is europe for want of any box, not of a lookup: every "fr" place but Mayotte
@pytest.mark.parametrize("lat, lon, code, expected", [p for p in PLACES if p[2] == "fr" and p[3] != "europe"])
def test_the_source_of_a_place_offline(monkeypatch, tmp_path, lat, lon, code, expected):
    def offline(*args, **kwargs):
        raise ValueError("offline")
    monkeypatch.setattr(osm, "reverse", offline)
    assert src.choose.choose_source("auto", lat, lon, str(tmp_path))[0].id == expected
