"""Slovenia (ARSO's lidar DMR 1 m: "x;y;z" text tiles of 1 km in blocks, the block of a tile from a static table,
a tile outside the table missing without a request) and the orthophoto's WMS 1.1.1 (GURS's DOF takes EPSG:4326
in lon-lat order only: OrthoService.wms_version)."""

import io
import os
import sys

import numpy as np
import pytest
import rasterio as rio
from PIL import Image
from rasterio.transform import from_origin
from rasterio.warp import transform

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cache  # noqa: E402
import orthophoto  # noqa: E402
import sources as src  # noqa: E402
from grid import Grid  # noqa: E402
from sources.catalogue import slovenia  # noqa: E402

SI = src.SOURCES["slovenia"]


def test_block_table():
    """The official index LIDAR_mreza_D96 as read on 2026-11-02: 21 263 tiles in 19 blocks."""
    tiles = slovenia._si_tiles()
    assert len(tiles) == 21263
    assert sorted(set(tiles.values())) == ["b_11", "b_12", "b_13", "b_14", "b_15", "b_16", "b_21", "b_22", "b_23",
                                           "b_24", "b_25", "b_26", "b_31", "b_32", "b_33", "b_34", "b_35", "b_36",
                                           "b_37"]
    # Osp (b_21), Triglav's north face (b_37), the border tiles that run past it (full of data)
    assert slovenia.si_block(411, 48) == "b_21" and slovenia.si_block(410, 138) == "b_37"
    assert slovenia.si_block(401, 48) == "b_21" and slovenia.si_block(386, 140) is not None
    assert slovenia.si_block(411, 20) is None  # the sea south of Piran


@pytest.mark.parametrize("lat, lon, tile, block", [
    (45.5690, 13.8630, (411, 48), "b_21"),   # Osp, Mišja peč
    (46.3880, 13.8370, (410, 139), "b_37"),  # the north face of Triglav
])
def test_tile_names(lat, lon, tile, block):
    """1 km tiles named by their south-west point (whole km in D96/TM), their pixel edges 0.5 m below it."""
    xs, ys = transform("EPSG:4326", "EPSG:3794", [lon], [lat])
    x, y = round(xs[0]) // 1000 * 1000 + 500, round(ys[0]) // 1000 * 1000 + 500  # in the middle of the tile
    grid = Grid(left=x - 20.5, top=y + 20.5, res=1.0, height=40, width=40, crs="EPSG:3794")
    assert SI.nmt.tiles(grid) == [tile]
    assert SI.nmt.index.edges(tile) == (tile[0] * 1000 - 0.5, tile[1] * 1000 - 0.5, tile[0] * 1000 + 999.5,
                                        tile[1] * 1000 + 999.5)
    assert SI.nmt.tile_url(tile) == f"https://gis.arso.gov.si/lidar/dmr1/{block}/D96TM/TM1_{tile[0]}_{tile[1]}.asc"
    assert SI.nmt.tile_of(f"slovenia/lss-dmr1/2011-2015/{tile[0] // 10}_{tile[1] // 10}/{tile[0]}_{tile[1]}.tif") \
        == tile


def test_tile_outside_the_table(tmp_path, monkeypatch):
    """A tile ARSO does not have: no URL, missing without a request, and recorded so (never asked again)."""
    def no_request(*args, **kwargs):
        raise AssertionError("requested")
    monkeypatch.setattr(src.net, "_get", no_request)
    tile = (411, 20)
    assert SI.nmt.index.request(tile) is None and SI.nmt.tile_url(tile) is None
    cache_dir = str(tmp_path)
    assert SI.nmt._download_and_record(tile, cache_dir) == 0
    path = SI.nmt.tile_path(cache_dir, tile)
    assert not os.path.exists(path)
    assert not cache.due(cache_dir, path, SI.nmt.processing, None, SI.nmt.ttl_days)


def test_xyz_tile(http_server, tmp_path):
    """ARSO's text as it is: "x;y;z" with LF, column by column, y rising, whole metres; cached as a GeoTIFF in
    D96/TM with its pixel edges on .5."""
    lines = [f"{x}.00;{y}.00;{100 + (x - 411000) + (y - 48000) / 100:.2f}"
             for x in range(411000, 411004) for y in range(48000, 48003)]
    http_server.add("/lidar/dmr1/b_21/D96TM/TM1_411_48.asc", ("\n".join(lines) + "\n").encode(),
                    "application/octet-stream")
    request = SI.nmt.index.request((411, 48))
    request = request._replace(url=http_server.url("/lidar/dmr1/b_21/D96TM/TM1_411_48.asc"))
    path = str(tmp_path / "t.tif")
    assert SI.nmt.reader.fetch(request, path).received > 0
    with rio.open(path) as cached:
        assert cached.crs.to_epsg() == 3794
        assert cached.transform == from_origin(410999.5, 48002.5, 1.0, 1.0)
        values = cached.read(1)
    assert values.shape == (3, 4)
    assert values[0, 0] == np.float32(100.02) and values[2, 0] == np.float32(100.0)
    assert values[2, 3] == np.float32(103.0) and values[0, 3] == np.float32(103.02)


def test_declaration():
    assert SI.grid_origin == (0.5, 0.5) and SI.crs == "EPSG:3794" and SI.nmpt is None
    assert SI.neighbours == ("austria",) and "slovenia" in src.SOURCES["austria"].neighbours
    assert src.net.HOST_SLOTS_OF["gis.arso.gov.si"] == 2
    assert SI.ortho.wms_version == "1.1.1"
    # Slovenia's offline boxes before Austria's (which reaches over Triglav)
    assert list(src.SOURCES).index("slovenia") < list(src.SOURCES).index("austria")


def _jpeg() -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (8, 8), (10, 20, 30)).save(out, "JPEG")
    return out.getvalue()


@pytest.mark.parametrize("version, expected", [
    ("1.1.1", {"VERSION": "1.1.1", "SRS": "EPSG:4326"}),
    ("1.3.0", {"VERSION": "1.3.0", "CRS": "EPSG:4326"}),
])
def test_wms_axis_order(monkeypatch, version, expected):
    """WMS 1.3.0 asks EPSG:4326 as lat-lon, 1.1.1 as lon-lat (SRS)."""
    asked = []
    monkeypatch.setattr(orthophoto, "_get", lambda url, params, z, x, y: asked.append(params) or _jpeg())
    service = src.OrthoService("Fake", "https://wms.example/ows", "DOF5", "fake/ortho/live", "test",
                               wms_version=version)
    orthophoto.tile_content(service, 18, 142236, 93450)
    params = asked[0]
    for key, value in expected.items():
        assert params[key] == value
    assert ("CRS" in params) != ("SRS" in params)
    west, south, east, north = orthophoto.bounds_wgs84(18, 142236, 93450)
    bbox = [float(v) for v in params["BBOX"].split(",")]
    assert bbox == ([west, south, east, north] if version == "1.1.1" else [south, west, north, east])
    with pytest.raises(ValueError):
        orthophoto._get_map("https://wms.example/ows", "DOF5", 18, 142236, 93450, version="1.1.0")


def test_map_data_names_the_wms_version(tmp_path):
    """data.js carries wms_version for a WMS taking lon-lat only (layers.ts asks it as 1.1.1), and leaves it out
    for 1.3.0, as in the maps of before."""
    import json

    from shapely.geometry import Point

    import helpers
    import mapping

    class Area:
        center = (45.569, 13.863)

        @staticmethod
        def shape_wgs84():
            return Point(13.863, 45.569).buffer(0.01)

    run = {"id": "r", "name": "r", "created": "2026-11-02T10:00:00+00:00"}
    found = []
    for version in ("1.1.1", "1.3.0"):
        service = src.OrthoService("Ortho", "https://wms.example/ows", "DOF5", "fake/ortho/live", "test",
                                   wms_version=version)
        folder = tmp_path / version
        folder.mkdir()
        mapping.save_map(helpers.LineTable.empty(), Area, str(folder), str(tmp_path / "runs"), run, "EPSG:3794",
                         ortho_service=service)
        text = (folder / "data.js").read_text(encoding="utf-8")
        found.append(json.loads(text.partition(" = ")[2].rstrip().rstrip(";"))["ortho"])
    assert found[0]["wms_version"] == "1.1.1" and "wms_version" not in found[1]
