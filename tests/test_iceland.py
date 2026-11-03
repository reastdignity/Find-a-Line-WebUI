"""Iceland: IslandsDEM v1.0 10 m (one national COG, float32 ZSTD with predictor 2, nodata -3.4e38, read in blocks of
5 km on its own pixels) and the orthophoto WMS asked in Web Mercator (gis.natt.is's mapcache serves EPSG:3857
only and answers PNG: OrthoService.wms_crs)."""

import io
import json
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
import grid as gd  # noqa: E402
import orthophoto  # noqa: E402
import sources as src  # noqa: E402
from sources.catalogue import iceland  # noqa: E402
from sources.layers.fileblocks import FileBlocks  # noqa: E402

IS = src.SOURCES["islandsdem10"]
NODATA = -3.4028234663852886e+38  # IslandsDEM's


def test_declaration():
    """By hand only (no countries, no offline boxes), on the file's own pixels in EPSG:8088, no fallback until the
    merge gives it the open Copernicus source; the constants the source `iceland` is built from."""
    assert IS.countries == () and IS.offline == () and IS.fallback is None and IS.fallbacks == []
    assert IS.crs == "EPSG:8088" and IS.grid_origin == (0.0, 0.0) and IS.default_resolution == 10.0
    assert IS.nmpt is None and IS.ortho is iceland.IS_ORTHO
    assert IS.nmt.folder == "iceland/islandsdem-v1.0-10m" and IS.nmt.ttl_days is None
    lat, lon = iceland.IS_SAMPLE
    assert IS.sample == iceland.IS_SAMPLE
    assert [code for code, _ in iceland.IS_BOXES] == ["is"]
    assert any(s <= lat <= n and w <= lon <= e for _, (s, n, w, e) in iceland.IS_BOXES)
    assert "IslandsDEM" in iceland.IS_NOTE_ARCTICDEM and "Copernicus" in iceland.IS_NOTE_ARCTICDEM
    assert src.net.HOST_SLOTS_OF["ftp.natt.is"] == 4 and src.net.HOST_SLOTS_OF["gis.natt.is"] == 4


def test_printed_texts_in_cp1250():
    """Names, descriptions and notes are printed to a Windows console (cp1250): no "æ" or "ð" in them. The
    credits' attributions keep the provider's Icelandic name (written to files and the map only)."""
    texts = [IS.name, IS.description, IS.note, IS.nmt.description, iceland.IS_ORTHO.name, iceland.IS_NOTE_ARCTICDEM,
             IS.credits[0].data]
    for text in texts:
        text.encode("cp1250")
    assert IS.credits[0].attribution.startswith("IslandsDEM v1.0 by Náttúrufræðistofnun is licensed under CC BY 4.0.")
    assert "Copernicus WorldDEM-30" in IS.credits[0].attribution
    assert iceland.IS_OPEN_DATA in IS.credits[0].notice
    assert (iceland.IS_ORTHO.attribution, iceland.IS_ORTHO.attribution_url) == (
        "Grunnkort - Loftmynd by Náttúrufræðistofnun is licensed under CC BY 4.0", src.CC_BY[1])


@pytest.mark.parametrize("lat, lon, tile", [
    (65.8239, -16.3934, (563, 78)),   # Hafragil
    (66.006, -16.508, (562, 82)),     # Ásbyrgi
])
def test_blocks(lat, lon, tile):
    """Blocks of 5 km (500 px of 10 m) from multiples of 5 km in EPSG:8088, every one read from the national file;
    one outside the file's extent makes no request."""
    (x,), (y,) = transform("EPSG:4326", "EPSG:8088", [lon], [lat])
    assert (int(x // 5000), int(y // 5000)) == tile
    request = IS.nmt.index.request(tile)
    assert request.files == [("IslandsDEMv1.0_10x10m_isn2016_zmasl.tif", iceland.IS_DEM_URL, 2021)]
    assert request.shape == (500, 500) and request.crs == "EPSG:8088"
    assert (request.transform.a, request.transform.c, request.transform.f) == (10.0, tile[0] * 5000.0,
                                                                              (tile[1] + 1) * 5000.0)
    assert IS.nmt.index.request((487, 50)).files == []    # west of the file (2 440 000)
    assert IS.nmt.index.request((560, 96)).files == []    # north of it (480 000)
    assert IS.nmt.tile_of(f"iceland/islandsdem-v1.0-10m/{tile[0] // 50}_{tile[1] // 50}/{tile[0]}_{tile[1]}.tif") \
        == tile


def test_zstd_file_read_in_blocks(http_server, tmp_path, monkeypatch):
    """A file like IslandsDEM (float32, ZSTD with predictor 2, 512 px tiles, nodata -3.4e38, edges on whole 10 m)
    read by range requests: the wheels' GDAL decodes ZSTD, values come exactly, nodata (the sea) as NaN."""
    monkeypatch.setattr(src.layer, "DOWNLOAD_THREADS", 1)  # one block at a time (the test server)
    left, top = 2810000.0, 420000.0
    band = (np.add.outer(np.arange(600) * 0.25, np.arange(600) * 0.5) + 20.0).astype(np.float32)
    band[:50, :70] = np.nan                                 # "the sea"
    os.makedirs(tmp_path / "files")
    with rio.open(tmp_path / "files" / "is.tif", "w", driver="GTiff", width=600, height=600, count=1,
                  dtype="float32", crs="EPSG:8088", nodata=NODATA, transform=from_origin(left, top, 10.0, 10.0),
                  tiled=True, blockxsize=512, blockysize=512, compress="zstd", predictor=2) as dst:
        dst.write(np.where(np.isnan(band), NODATA, band).astype(np.float32), 1)
    with rio.open(tmp_path / "files" / "is.tif") as check:
        assert check.compression.value.lower() == "zstd"
    http_server.add_folder("/files", str(tmp_path / "files"))
    layer = FileBlocks("IslandsDEM test", "test/is10", "EPSG:8088", 10.0, 5000, http_server.url("/files/is.tif"),
                       extent=(left, top - 6000, left + 6000, top), year=2021)
    grid = gd.make_grid((left + 100, top - 4900, left + 5500, top - 100), 10.0, "EPSG:8088")
    cache_dir = str(tmp_path / "cache")
    assert layer.tiles(grid) == [(562, 83), (563, 83)]
    layer.download(grid, cache_dir, None, "test")
    with rio.open(layer.tile_path(cache_dir, (562, 83))) as block:
        values = block.read(1)
        assert block.shape == (500, 500) and block.transform.c == left and block.transform.f == top
        assert np.isnan(values[:50, :70]).all() and not np.isnan(values[50:, :]).any()
        assert (values[50:, 70:] == band[50:500, 70:500]).all()
        assert block.tags()["sources"] == "is.tif" and block.tags()["years"] == "2021"
    with rio.open(layer.tile_path(cache_dir, (563, 83))) as block:   # partly over the file
        values = block.read(1)
        assert (values[:, :100] == band[:500, 500:600]).all() and np.isnan(values[:, 100:]).all()
    assert all(cache.state(cache_dir, layer.tile_path(cache_dir, t)) == "ok" for t in layer.tiles(grid))


def _png(rgba) -> bytes:
    out = io.BytesIO()
    Image.fromarray(np.asarray(rgba, np.uint8)).save(out, "PNG")
    return out.getvalue()


@pytest.mark.parametrize("version, key", [("1.1.1", "SRS"), ("1.3.0", "CRS")])
def test_wms_in_web_mercator(monkeypatch, version, key):
    """A WMS asked in EPSG:3857 gets the tile's own Mercator box (x before y in both versions); a PNG answer
    (gis.natt.is answers PNG also to a JPEG request) is cached as JPEG, its transparent parts white."""
    asked = []
    tile = np.zeros((256, 256, 4), np.uint8)
    tile[:, :128] = (30, 120, 60, 255)                      # imagery on the left, transparent sea on the right
    monkeypatch.setattr(orthophoto, "_get", lambda url, params, z, x, y: asked.append(params) or _png(tile))
    service = src.OrthoService("Fake", "https://wms.example/wms", "grunnkort-loftmynd", "fake/ortho/live", "test",
                               wms_version=version, wms_crs="EPSG:3857")
    z, x, y = 17, 59525, 33226                              # at Ásbyrgi
    content = orthophoto.tile_content(service, z, x, y)
    params = asked[0]
    assert params[key] == "EPSG:3857" and ("CRS" in params) != ("SRS" in params) and params["VERSION"] == version
    left, bottom, right, top = (float(v) for v in params["BBOX"].split(","))
    size = 2 * 20037508.342789244 / 2 ** z
    assert right - left == pytest.approx(size) and top - bottom == pytest.approx(size)
    (west, east), (south, north) = transform("EPSG:3857", "EPSG:4326", [left, right], [bottom, top])
    assert np.allclose((west, south, east, north), orthophoto.bounds_wgs84(z, x, y), atol=1e-9)
    assert content.startswith(orthophoto.JPEG_MAGIC)
    image = np.asarray(Image.open(io.BytesIO(content)).convert("RGB")).astype(int)
    assert abs(image[:, :120] - (30, 120, 60)).max() < 10 and (image[:, 136:] > 245).all()
    with pytest.raises(ValueError):
        orthophoto._get_map("https://wms.example/wms", "x", z, x, y, crs="EPSG:3035")


def test_wms_in_degrees_unchanged(monkeypatch):
    """The default (EPSG:4326) asks as before, and a JPEG answer is cached as the service sent it."""
    out = io.BytesIO()
    Image.new("RGB", (8, 8), (10, 20, 30)).save(out, "JPEG")
    asked = []
    monkeypatch.setattr(orthophoto, "_get", lambda url, params, z, x, y: asked.append(params) or out.getvalue())
    service = src.OrthoService("Fake", "https://wms.example/wms", "x", "fake/ortho/live", "test")
    assert service.wms_crs == "EPSG:4326"
    assert orthophoto.tile_content(service, 17, 59525, 33226) == out.getvalue()
    assert asked[0]["CRS"] == "EPSG:4326" and asked[0]["BBOX"] == orthophoto._wms_bbox(17, 59525, 33226)


def test_map_data_names_the_wms_crs(tmp_path):
    """data.js carries wms_crs for a WMS asked in Web Mercator (layers.ts asks Leaflet's WMS in EPSG:3857) and
    leaves it out for EPSG:4326, so the maps of other sources stay as they were."""
    from shapely.geometry import Point

    import helpers
    import mapping

    class Area:
        center = (66.006, -16.508)

        @staticmethod
        def shape_wgs84():
            return Point(-16.508, 66.006).buffer(0.01)

    run = {"id": "r", "name": "r", "created": "2026-11-03T10:00:00+00:00"}
    found = []
    for service in (iceland.IS_ORTHO, src.OrthoService("Ortho", "https://wms.example/ows", "x", "fake/ortho/live",
                                                       "test")):
        folder = tmp_path / service.folder.replace("/", "_")
        folder.mkdir()
        mapping.save_map(helpers.LineTable.empty(), Area, str(folder), str(tmp_path / "runs"), run, "EPSG:8088",
                         ortho_service=service)
        text = (folder / "data.js").read_text(encoding="utf-8")
        found.append(json.loads(text.partition(" = ")[2].rstrip().rstrip(";"))["ortho"])
    assert found[0]["wms_crs"] == "EPSG:3857" and found[0]["wms_version"] == "1.1.1"
    assert "wms_crs" not in found[1] and "wms_version" not in found[1]
