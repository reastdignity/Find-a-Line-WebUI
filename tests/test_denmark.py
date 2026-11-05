"""Denmark (sources/catalogue/denmark.py): Danmarks Højdemodel from Datafordeler's WCS 1.0.0 with the
server's API key; without the key the source is unavailable, with it the layers ask the fake WCS of
tests/test_keys.py as the catalogue declares them."""

import os
import sqlite3
import sys

import numpy as np
import pytest
import rasterio as rio
from rasterio.io import MemoryFile
from rasterio.transform import from_origin

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import sources as src  # noqa: E402
from sources import probe  # noqa: E402
from sources.catalogue import denmark  # noqa: E402
from http_server import Answer  # noqa: E402
from tile_values import TILE_EPS, same_tile  # noqa: E402
from test_keys import EXTENT, TOKEN, height, no_keys, wcs10  # noqa: E402,F401  (no_keys: autouse here too)


def test_declared():
    """WCS 1.0.0 with the API key as the query parameter `apikey`, terrain and surface, the 1 m grid
    by default; the credit (CC BY 4.0: owner, licence, datasets, processed) in its constants."""
    source = src.SOURCES["denmark"]
    assert source.countries == ("dk",) and source.crs == "EPSG:25832" and source.default_resolution == 1.0
    for layer, coverage in ((source.nmt, "dhm_terraen"), (source.nmpt, "dhm_overflade")):
        assert layer.coverage == coverage and layer.reader.version == "1.0.0"
        assert layer.reader.key_params == (("apikey", "datafordeler_api_key"),) and layer.keys == ("datafordeler_api_key",)
        assert layer.reader.zero_is_nodata and layer.fmt == "GTiff" and layer.origin == (0.0, 0.0)
        assert layer.url == "https://wcs.datafordeler.dk/DHMNedboer/dhm_wcs/1.0.0/WCS"  # never a key here
        assert layer.credit.attribution == denmark.DHM_ATTRIBUTION
    assert denmark.DHM_ATTRIBUTION == "Danmarks Højdemodel (Terræn / Overflade), Klimadatastyrelsen, CC BY 4.0, processed"
    credit = source.nmt.credit
    assert credit.licence == "CC BY 4.0" and credit.url == "https://creativecommons.org/licenses/by/4.0/"
    assert "dataforsyningen.dk/data/930" in credit.notice and "dataforsyningen.dk/data/928" in credit.notice
    assert source.ortho is None  # Datafordeler's orthophoto needs the key in the map's own requests
    for text in (source.name, source.description, source.note, source.nmt.description, source.nmpt.description):
        text.encode("cp1250")  # printed to a Windows console


def test_chosen_only_with_a_key(monkeypatch, tmp_path):
    """--source auto takes Denmark only with an API key (else the Europe-wide model, saying why), --source
    denmark refuses without one, and the probe skips it."""
    monkeypatch.setattr(src.choose, "country_code", lambda lat, lon, cache_dir: "dk")
    source, reason = src.choose_source("auto", 54.965, 12.545, str(tmp_path))
    assert source.id == "europe" and "DATAFORDELER_API_KEY" in reason and "the centre is in DK" in reason
    with pytest.raises(ValueError, match="DATAFORDELER_API_KEY"):
        src.choose_source("denmark", 54.965, 12.545, str(tmp_path))
    assert "DATAFORDELER_API_KEY" in probe.skip_reason(src.SOURCES["denmark"], True, None)
    monkeypatch.setenv("DATAFORDELER_API_KEY", TOKEN)
    source, reason = src.choose_source("auto", 54.965, 12.545, str(tmp_path))
    assert source.id == "denmark" and reason == "the centre is in DK"
    assert probe.skip_reason(src.SOURCES["denmark"], True, None) is None


def test_offline_boxes():
    """Offline, Copenhagen, Mons Klint and Bornholm are Danish; Flensburg and Malmo are not."""
    boxes = src.OFFLINE_BOXES
    def code(lat, lon):  # noqa: E306
        return next((c.split("-")[0] for c, (s, n, w, e) in boxes if s <= lat <= n and w <= lon <= e), None)
    assert code(55.676, 12.568) == code(54.965, 12.545) == code(55.200, 14.708) == "dk"
    assert code(54.784, 9.437) != "dk" and code(55.605, 13.003) != "dk"


def test_tiles_from_the_wcs(http_server, monkeypatch, tmp_path):
    """The catalogue's layer, pointed at a fake WCS 1.0.0 that wants the API key: a 1 m tile of 2 km
    on whole metres, the key in each request, none in the cache's index."""
    http_server.route("/dhm", wcs10(TOKEN))
    monkeypatch.setenv("DATAFORDELER_API_KEY", TOKEN)
    monkeypatch.setattr(denmark, "DHM_WCS", http_server.url("/dhm"))
    layer = denmark._dhm("dhm_terraen", "dhm-terraen", "DHM/Terraen 0.4 m (terrain)")
    cache_dir = str(tmp_path / "cache")
    tile = (1.0, 250, 3000)  # 500000-502000 / 6000000-6002000, inside the fake coverage
    assert layer._download_and_record(tile, cache_dir) > 0
    path = layer.tile_path(cache_dir, tile)
    assert path.replace("\\", "/").endswith("denmark/dhm-terraen/live/epsg25832-1m-2000px-tif/250_3000.tif")
    with rio.open(path) as f:
        assert f.transform == from_origin(500000, 6002000, 1, 1) and f.crs.to_epsg() == 25832
        band = f.read(1)
    ys, xs = np.mgrid[0:2000:500, 0:2000:500]
    assert same_tile(band[::500, ::500], height(500000 + xs + 0.5, 6002000 - ys - 0.5))
    query = dict(http_server.requests("/dhm")[-1].query)
    assert query["apikey"] == TOKEN and query["COVERAGE"] == "dhm_terraen" and query["WIDTH"] == "2000"
    with sqlite3.connect(os.path.join(cache_dir, "denmark", "index.sqlite")) as db:
        (url,), = db.execute("SELECT url FROM files").fetchall()
    assert TOKEN not in url and "apikey=..." in url
    assert layer.coverage_extent() == EXTENT


def test_zero_is_no_data(http_server, monkeypatch, tmp_path):
    """The live service (2026-11-01) answers the sea, Germany and everything outside its data with 0.0
    and no nodata value, never a 404: those pixels become no data, so the water filling and the
    fallback take them; the land keeps its heights."""
    land_until = 501000.0  # east of it: the sea

    def handle(request):
        query = dict((k.upper(), v) for k, v in request.query)
        assert dict(request.query).get("apikey") == TOKEN and query["REQUEST"] == "GetCoverage"
        left, bottom, right, top = map(float, query["BBOX"].split(","))
        width, rows = int(query["WIDTH"]), int(query["HEIGHT"])
        res = (right - left) / width
        ys, xs = np.mgrid[0:rows, 0:width]
        x, y = left + (xs + 0.5) * res, top - (ys + 0.5) * res
        band = np.where(x < land_until, height(x, y), np.float32(0.0)).astype(np.float32)
        with MemoryFile() as memfile:
            with memfile.open(driver="GTiff", width=width, height=rows, count=1, dtype="float32", crs="EPSG:25832",
                              transform=from_origin(left, top, res, res)) as dst:
                dst.write(band, 1)
            return Answer(200, memfile.read(), {"Content-Type": "image/tiff"})

    http_server.route("/dhm", handle)
    monkeypatch.setenv("DATAFORDELER_API_KEY", TOKEN)
    monkeypatch.setattr(denmark, "DHM_WCS", http_server.url("/dhm"))
    layer = denmark._dhm("dhm_terraen", "dhm-terraen", "DHM/Terraen 0.4 m (terrain)")
    cache_dir = str(tmp_path / "cache")
    tile = (1.0, 250, 3000)  # 500000-502000: land in its western half, sea in the eastern
    assert layer._download_and_record(tile, cache_dir) > 0
    with rio.open(layer.tile_path(cache_dir, tile)) as f:
        band = f.read(1)
    assert np.isfinite(band[:, :1000]).all() and np.isnan(band[:, 1000:]).all()
    assert abs(band[0, 0] - height(np.float32(500000.5), np.float32(6001999.5))) <= TILE_EPS
