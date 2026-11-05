"""Queensland (sources/catalogue/australia.py): the State's DEM time series ImageServer asked in the MGA zone of the
working grid (ImageServerTiles with zones: ZonedTiling, ZonedReader), against real answers recorded in
tests/data/recorded/imageserver/queensland/ (README there), served by the local server; the sources queensland and
queensland_demh."""

import json
import os
import sys
from urllib.parse import parse_qsl, urlsplit

import numpy as np
import pytest
import rasterio as rio
from rasterio.transform import from_origin

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import sources as src  # noqa: E402
from tile_values import TILE_EPS, same_tile  # noqa: E402
from grid import make_grid  # noqa: E402
from sources import net, probe  # noqa: E402
from sources.catalogue import australia  # noqa: E402
from sources.catalogue.australia import (QLD_DEMH, QLD_DEMH_RULE, QLD_LIDAR, QLD_LIDAR_RULE, QLD_ZONES,  # noqa: E402
                                         mga_crs)
from sources.layers.imageserver import ImageServerTiles, ZonedTiling  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
CASSETTE = os.path.join(HERE, "data", "recorded", "imageserver", "queensland")
SERVICE = "/arcgis/rest/services/Elevation/DEM_TimeSeries_AllUsers/ImageServer"
# The recorded boxes (left, bottom) of 16 x 16 px: see record.py
TIBROGARGAN = (494770, 7021640)
ISA = (343040, 7707480)
SEA = (562000, 7002000)
DEMH = (494400, 7021400)


def _body(name: str) -> bytes:
    with open(os.path.join(CASSETTE, name), "rb") as f:
        return f.read()


def _values(body: bytes) -> np.ndarray:
    with rio.MemoryFile(body) as memfile, memfile.open() as raster:
        return raster.read(1)


def _recorded():
    with open(os.path.join(CASSETTE, "exports.json"), encoding="utf-8") as f:
        return json.load(f)["answers"]


@pytest.fixture
def server(http_server, monkeypatch):
    monkeypatch.setattr(net, "_sleep", lambda attempt: None)
    for entry in _recorded():
        http_server.add(urlsplit(entry["url"])._replace(scheme="", netloc="").geturl(), _body(entry["body"]),
                        entry["content_type"], entry["status"])
    return http_server


def _layer(server, box, res=1.0, rule=QLD_LIDAR_RULE) -> ImageServerTiles:
    """A layer like the catalogue's on the local server whose tiles of 16 px have the box's corner as an edge."""
    size = 16 * res
    return ImageServerTiles("test", server.url(SERVICE), QLD_ZONES[0], "test/qld", res, tile_px=16,
                            origin=(box[0] % size, box[1] % size), mosaic_rule=rule, zones=QLD_ZONES)


def _tile_at(layer, crs, box, res=1.0):
    """The tile of a zoned layer whose box starts at box, and a grid inside it."""
    grid = make_grid((box[0] + 2 * res, box[1] + 2 * res, box[0] + 14 * res, box[1] + 14 * res), res, crs)
    tiles = layer.tiles(grid)
    size = 16 * res
    ox, oy = layer.origin
    tile = (crs, (res, round((box[0] - ox) / size), round((box[1] - oy) / size)))
    assert tiles == [tile]
    return tile


def test_mga_zones():
    """The working grid is GDA94 / MGA of the centre: zone 54 west of 144° E, 55 to 150° E, 56 east of it (the
    State's extremes clamped to those)."""
    assert mga_crs(-20.7256, 139.4927) == "EPSG:28354"  # Mount Isa
    assert mga_crs(-25.07, 148.2) == "EPSG:28355"  # Carnarvon Gorge
    assert mga_crs(-26.927, 152.947) == "EPSG:28356"  # Tibrogargan
    assert mga_crs(-10.6, 137.9) == "EPSG:28354" and mga_crs(-27.0, 156.5) == "EPSG:28356"
    source = src.SOURCES["queensland"]
    assert source.crs is None and source.working_crs(-26.927, 152.947) == "EPSG:28356"
    assert source.working_crs(-20.7256, 139.4927) == "EPSG:28354"
    assert src.SOURCES["queensland_demh"].working_crs(-25.07, 148.2) == "EPSG:28355"


def test_zoned_tiles_and_paths(tmp_path):
    """A grid in one of the zones gets its tiles in that zone, any other grid those of the default (MGA 56);
    each zone has its own folder, and tile_of finds the zone again."""
    assert isinstance(QLD_LIDAR.index, ZonedTiling) and QLD_LIDAR.zones == ("EPSG:28355", "EPSG:28354")
    assert list(QLD_LIDAR.readers) == list(QLD_ZONES)
    assert {crs: r.sr for crs, r in QLD_LIDAR.readers.items()} == {"EPSG:28356": "28356", "EPSG:28355": "28355",
                                                                    "EPSG:28354": "28354"}
    for crs, x, y in (("EPSG:28356", 494770, 7021640), ("EPSG:28354", 343040, 7707480),
                      ("EPSG:32756", 494770, 7021640)):
        grid = make_grid((x - 600, y - 600, x + 600, y + 600), 1.0, crs)
        tiles = QLD_LIDAR.tiles(grid)
        zone = crs if crs in QLD_ZONES else "EPSG:28356"
        assert tiles and {t[0] for t in tiles} == {zone} and {t[1][0] for t in tiles} == {1.0}
        assert len(tiles) == len(QLD_LIDAR.index.tilings[zone].tiles(grid)) >= 4  # 1 km tiles
        for tile in tiles:
            rel = os.path.relpath(QLD_LIDAR.tile_path(str(tmp_path), tile), tmp_path).replace(os.sep, "/")
            assert rel == f"queensland/dem-lidar/live/{zone.lower().replace(':', '')}-1m-1000px-tif/" \
                          f"{tile[1][1]}_{tile[1][2]}.tif"
            assert QLD_LIDAR.tile_of(rel) == tile
            assert QLD_LIDAR.tile_url(tile) == australia.QLD_DEM_URL
    assert QLD_LIDAR.tile_of("queensland/dem-lidar/live/epsg28357-1m-1000px-tif/1_2.tif") is None
    assert QLD_LIDAR.tile_of("queensland/dem-h/live/epsg28356-30m-500px-tif/1_2.tif") is None
    assert QLD_DEMH.tile_of("queensland/dem-h/live/epsg28355-30m-500px-tif/26_512.tif") == \
        ("EPSG:28355", (30.0, 26, 512))
    # The tiles of DEM-H are 15 km of 30 m whatever the working resolution
    grid = make_grid((494000, 7021000, 494900, 7021900), 1.0, "EPSG:28356")
    assert QLD_DEMH.tiles(grid) == [("EPSG:28356", (30.0, 32, 468))]
    west, south, east, north = QLD_DEMH.bounds_wgs84(("EPSG:28356", (30.0, 32, 468)))
    assert west < 152.947 < east and south < -26.927 < north
    # An unzoned layer keeps its tiles as before
    plain = ImageServerTiles("t", "https://example/ImageServer", "EPSG:5514", "czechia/dmr5g/live", 2.0)
    assert plain.zones == () and plain.reader is plain.readers["EPSG:5514"]


def test_requests_as_the_catalogue_writes_them():
    """The mosaic rules: the lidar DTMs (product_type 8 at 1 m or finer: no photogrammetric ODEM, no bathymetry)
    by the service's ZOrder, DEM-H apart; nearest neighbour, noData -9999, in the zone's WKID."""
    reader = QLD_LIDAR.readers["EPSG:28354"]
    params = dict(reader.export_params(343040, 7707480, 344040, 7708480, 1.0))
    assert params["mosaicRule"] == ('{"ascending":true,"mosaicMethod":"esriMosaicAttribute","sortField":"ZOrder",'
                                    '"sortValue":"0","where":"product_type = 8 AND res_value <= 1"}')
    assert (params["bboxSR"], params["imageSR"], params["size"]) == ("28354", "28354", "1000,1000")
    assert (params["interpolation"], params["noData"], params["f"]) == ("RSP_NearestNeighbor", "-9999", "image")
    assert json.loads(dict(QLD_DEMH.readers["EPSG:28356"].export_params(0, 0, 15000, 15000, 30.0))["mosaicRule"]
                      )["where"] == "product_type = 1"
    assert QLD_DEMH_RULE["where"] == "product_type = 1"


def test_the_service_keeps_its_pixels():
    """What the reader relies on, as the service answered (2026-11-02): in MGA 56 at 1 m nearest neighbour a box
    equals its two halves; every answer is on the pixels asked for, in the CRS asked for."""
    answers = {e["case"]: e for e in _recorded()}
    full = _values(_body(answers["full"]["body"]))
    halves = [_values(_body(answers[k]["body"])) for k in ("left", "right")]
    assert np.array_equal(full, np.hstack(halves)) and (full > 340).all() and (full < 365).all()
    for case, crs, (x, y), res in (("full", 28356, TIBROGARGAN, 1), ("isa", 28354, ISA, 1),
                                   ("demh", 28356, DEMH, 30)):
        with rio.MemoryFile(_body(answers[case]["body"])) as memfile, memfile.open() as raster:
            assert raster.crs.to_epsg() == crs and raster.transform == from_origin(x, y + 16 * res, res, res)
        query = dict(parse_qsl(urlsplit(answers[case]["url"]).query))
        assert query["bboxSR"] == query["imageSR"] == str(crs)
    assert (_values(_body(answers["sea"]["body"])) == -9999).all()


@pytest.mark.parametrize("crs, box, name", [("EPSG:28356", TIBROGARGAN, "001-full.tif"),
                                            ("EPSG:28354", ISA, "004-isa.tif")])
def test_tile_in_the_zone_of_the_grid(server, tmp_path, crs, box, name):
    """A grid in MGA 56 or 54 gets its tile from the service in that zone, exactly the values answered, saved in
    that CRS on its own pixels."""
    layer = _layer(server, box)
    tile = _tile_at(layer, crs, box)
    path = layer.tile_path(str(tmp_path), tile)
    fetched = layer.download_tile(tile, path)
    assert fetched.received == len(_body(name))
    with rio.open(path) as raster:
        assert raster.crs.to_string() == crs
        assert raster.transform == from_origin(box[0], box[1] + 16, 1.0, 1.0)
        assert same_tile(raster.read(1), _values(_body(name)))
    asked = server.requests(f"{SERVICE}/exportImage")
    assert len(asked) == 1 and dict(asked[0].query)["bboxSR"] == crs.split(":")[1]
    assert not server.stray()


def test_demh_tile(server, tmp_path):
    layer = _layer(server, DEMH, 30.0, QLD_DEMH_RULE)
    tile = _tile_at(layer, "EPSG:28356", DEMH, 30.0)
    path = layer.tile_path(str(tmp_path), tile)
    layer.download_tile(tile, path)
    with rio.open(path) as raster:
        assert raster.res == (30.0, 30.0) and same_tile(raster.read(1), _values(_body("006-demh.tif")))


def test_sea_is_missing(server, tmp_path):
    """Every pixel at noData (no project there): no file, nothing received."""
    layer = _layer(server, SEA)
    tile = _tile_at(layer, "EPSG:28356", SEA)
    path = layer.tile_path(str(tmp_path), tile)
    fetched = layer.download_tile(tile, path)
    assert fetched.received == 0 and not os.path.exists(path)


def test_error_of_the_mosaic_rule(server, tmp_path):
    """A wrong mosaic rule is answered with an error JSON under HTTP 200 (code 400): an error, asked once, no
    file."""
    rule = {"mosaicMethod": "esriMosaicAttribute", "sortField": "ZOrder", "where": "no_field = 1"}
    layer = _layer(server, TIBROGARGAN, rule=rule)
    tile = _tile_at(layer, "EPSG:28356", TIBROGARGAN)
    with pytest.raises(RuntimeError, match="the service answered an error.*no_field"):
        layer.download_tile(tile, layer.tile_path(str(tmp_path), tile))
    assert len(server.requests(f"{SERVICE}/exportImage")) == 1 and not list(tmp_path.iterdir())


def test_probe_in_the_default_zone(server, tmp_path):
    """sources check: the description, then 16 x 16 px at the sample in the layer's default zone (MGA 56), as its
    reader writes the request: here the recorded box."""
    server.add(f"{SERVICE}?f=json", b'{"currentVersion": 11.5}', "application/json")
    layer = _layer(server, TIBROGARGAN)
    # (494778.5, 7021648.5) in MGA 56: the probe's box starts 8 px west and south of it, on the layer's pixels
    assert probe._image_service(str(tmp_path), layer, -26.927005, 152.9474059) == (probe.OK, probe.OK)
    query = dict(server.requests(f"{SERVICE}/exportImage")[0].query)
    assert query["bbox"] == "494770,7021640,494786,7021656" and query["bboxSR"] == "28356"


def test_sources(tmp_path, monkeypatch):
    """queensland: lidar, its gaps from DEM-H of the same service only (never FABDEM: BY-NC-SA and BY-SA), no
    surface model; chosen in Queensland (offline: by its boxes), Tasmania keeps its own."""
    qld, demh = src.SOURCES["queensland"], src.SOURCES["queensland_demh"]
    assert qld.fallbacks == ["queensland_demh"] and demh.fallbacks == [] and qld.neighbours == ()
    assert qld.nmpt is None and demh.nmpt is None and qld.regions == ("au-qld",) and demh.countries == ()
    assert qld.default_resolution == 1.0 and demh.default_resolution == 30.0
    assert qld.nmt.credit is qld.credits[0] and demh.nmt.credit is demh.credits[0]
    assert "CC BY-SA" in qld.ortho.attribution and qld.ortho.base_max_zoom == 20
    assert qld.ortho.base_url.endswith("/Basemaps/LatestStateProgram_AllUsers/ImageServer/tile/{z}/{y}/{x}")
    for text in (qld.description, qld.note, demh.description, demh.note, qld.name, demh.name):
        text.encode("cp1250")  # printed to a Windows console

    def offline(*args, **kwargs):
        raise ValueError("offline")
    monkeypatch.setattr(src.choose.osm, "reverse", offline)
    for lat, lon, sid in ((-26.927, 152.947, "queensland"), (-27.983, 152.620, "queensland"),
                          (-20.7256, 139.4927, "queensland"), (-10.58, 142.22, "queensland"),
                          (-42.893, 147.237, "tasmania"), (-33.87, 151.21, "europe"), (-28.64, 153.61, "europe")):
        assert src.choose_source("auto", lat, lon, str(tmp_path))[0].id == sid, (lat, lon)
