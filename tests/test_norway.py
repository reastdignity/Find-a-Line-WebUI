"""Norway (sources/catalogue/norway.py): Kartverket's NHM DTM 1 / DOM 1 from Geonorge's WCS 1.0.0 (no key), the
sea 0.0 as no data, and the service's refusals (HTTP 200 with an XML exception report) as errors, never data."""

import os
import sys

import numpy as np
import pytest
import rasterio as rio
from rasterio.io import MemoryFile
from rasterio.transform import from_origin

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cache  # noqa: E402
import sources as src  # noqa: E402
from sources.catalogue import norway  # noqa: E402
from http_server import Answer  # noqa: E402

# A ServiceExceptionReport as the live service sent it for 4097 x 100 px (2026-11-02), with HTTP 200
REFUSAL = (b'<?xml version="1.0" encoding="UTF-8"?>\n<ServiceExceptionReport version="1.2.0" '
           b'xmlns="http://www.opengis.net/ogc"><ServiceException>Request image size exceeds allowed limit.'
           b'</ServiceException></ServiceExceptionReport>')


def test_declared():
    """WCS 1.0.0 without a key, terrain and surface on the 1 m grid of EPSG:25833, zero as no data, the
    credit in Kartverket's wording, Finland as the neighbour both ways."""
    source = src.SOURCES["norway"]
    assert source.countries == ("no",) and source.crs == "EPSG:25833" and source.default_resolution == 1.0
    for layer, coverage, url in ((source.nmt, "nhm_dtm_topo_25833", norway.NHM_DTM_WCS),
                                 (source.nmpt, "nhm_dom_topo_25833", norway.NHM_DOM_WCS)):
        assert layer.coverage == coverage and layer.url == url and layer.reader.version == "1.0.0"
        assert layer.reader.zero_is_nodata and layer.fmt == "GeoTIFF" and layer.origin == (0.0, 0.0)
        assert layer.keys == () and layer.tile_px == 2000 and layer.ttl_days
        assert layer.credit.attribution == "©Kartverket, CC BY 4.0, processed"
        assert layer.credit.licence == "CC BY 4.0" and "https://www.kartverket.no/" in layer.credit.notice
    assert source.ortho is None  # Norge i bilder needs a token
    assert source.neighbours == ("finland",) and "norway" in src.SOURCES["finland"].neighbours
    assert src.net.HOST_SLOTS_OF["wcs.geonorge.no"] == 4
    for text in (source.name, source.description, source.note, source.nmt.description, source.nmpt.description):
        text.encode("cp1250")  # printed to a Windows console


def test_offline_boxes():
    """Offline, Oslo, Preikestolen, Trondheim, Bodo, Lofoten, Tromso and the North Cape are Norwegian;
    Gothenburg, Ostersund, Kiruna and Stockholm are not; Alta and Kirkenes lie in Finland's box, which comes
    first (the neighbours fill each other's border gaps)."""
    boxes = src.OFFLINE_BOXES

    def code(lat, lon):
        return next((c.split("-")[0] for c, (s, n, w, e) in boxes if s <= lat <= n and w <= lon <= e), None)

    for lat, lon in ((59.913, 10.739), (58.9864, 6.1904), (63.430, 10.395), (67.280, 14.405), (68.234, 14.568),
                     (69.649, 18.955), (71.169, 25.783)):
        assert code(lat, lon) == "no", (lat, lon)
    for lat, lon in ((57.709, 11.974), (63.179, 14.636), (67.856, 20.225), (59.329, 18.069)):
        assert code(lat, lon) != "no", (lat, lon)  # Gothenburg lies in Denmark's box
    assert code(69.969, 23.272) == code(69.727, 30.045) == "fi"


def _wcs(handle_band):
    """A fake WCS 1.0.0 answering GetCoverage with a float32 GeoTIFF without a nodata value."""
    def handle(request):
        query = dict((k.upper(), v) for k, v in request.query)
        assert query["VERSION"] == "1.0.0" and query["CRS"] == "EPSG:25833" and query["FORMAT"] == "GeoTIFF"
        left, bottom, right, top = map(float, query["BBOX"].split(","))
        width, rows = int(query["WIDTH"]), int(query["HEIGHT"])
        res = (right - left) / width
        ys, xs = np.mgrid[0:rows, 0:width]
        band = handle_band(left + (xs + 0.5) * res, top - (ys + 0.5) * res)
        if band is None:
            return Answer(200, REFUSAL, {"Content-Type": "application/vnd.ogc.se_xml"})
        with MemoryFile() as memfile:
            with memfile.open(driver="GTiff", width=width, height=rows, count=1, dtype="float32", crs="EPSG:25833",
                              transform=from_origin(left, top, res, res)) as dst:
                dst.write(band.astype(np.float32), 1)
            return Answer(200, memfile.read(), {"Content-Type": "image/tiff"})
    return handle


def test_zero_is_no_data(http_server, tmp_path):
    """The service answers the fjord, the sea and everything outside its data with 0.0: those pixels become no
    data (the water filling and the fallback take them); the land keeps its heights."""
    http_server.route("/dtm", _wcs(lambda x, y: np.where(x < -5000, 600.25 + 0 * y, 0.0)))
    layer = norway._nhm(http_server.url("/dtm"), "nhm_dtm_topo_25833", "nhm-dtm1", "NHM DTM 1 1 m (terrain)")
    cache_dir = str(tmp_path / "cache")
    tile = (1.0, -3, 3285)  # -6000..-4000 / 6570000..6572000: land in its western half
    assert layer._download_and_record(tile, cache_dir) > 0
    path = layer.tile_path(cache_dir, tile)
    assert path.replace("\\", "/").endswith("norway/nhm-dtm1/live/epsg25833-1m-2000px-tif/-3_3285.tif")
    with rio.open(path) as f:
        assert f.transform == from_origin(-6000, 6572000, 1, 1) and f.crs.to_epsg() == 25833
        band = f.read(1)
    assert (band[:, :1000] == np.float32(600.25)).all() and np.isnan(band[:, 1000:]).all()
    query = dict(http_server.requests("/dtm")[-1].query)
    assert query["BBOX"] == "-6000.000,6570000.000,-4000.000,6572000.000" and query["WIDTH"] == "2000"


def test_refusal_is_an_error(http_server, tmp_path):
    """A refused request comes as HTTP 200 with an XML exception report: an error, no tile and no "missing"."""
    http_server.route("/dtm", _wcs(lambda x, y: None))
    layer = norway._nhm(http_server.url("/dtm"), "nhm_dtm_topo_25833", "nhm-dtm1", "NHM DTM 1 1 m (terrain)")
    cache_dir = str(tmp_path / "cache")
    tile = (1.0, -3, 3285)
    with pytest.raises(Exception):
        layer._download_and_record(tile, cache_dir)
    path = layer.tile_path(cache_dir, tile)
    assert not os.path.exists(path)
    assert cache.state(cache_dir, path) is None  # asked again next time
