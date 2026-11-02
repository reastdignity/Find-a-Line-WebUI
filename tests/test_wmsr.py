"""The WMS-R reader (raw heights by WMS GetMap as GeoTIFF: IGN's Géoplateforme) on recorded answers of
data.geopf.fr (tests/data/recorded/wmsr/, its README), served by tests/http_server.py, and France's
layers built on it.

The requests follow OGC WMS 1.3.0 (06-042), 7.3 GetMap: VERSION, REQUEST, LAYERS, STYLES, CRS, BBOX
(the CRS's own axis order: easting, northing for EPSG:2154), WIDTH, HEIGHT, FORMAT; SERVICE=WMS as every
KVP request of the standard (6.9.2); an error is a ServiceExceptionReport (7.3.3.11, 6.11), which IGN sends
with HTTP 400. IGN's vendor parameter FORMAT_OPTIONS=compression:deflate (the Géoplateforme's WMS-R
documentation) compresses the GeoTIFF without changing a value.
"""

import json
import os
import sys
from urllib.parse import urlsplit

import numpy as np
import pytest
import rasterio as rio
from rasterio.transform import from_origin

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
import sources as src  # noqa: E402
from sources import net  # noqa: E402
from sources.readers.wmsr import MapRequest, WmsrReader  # noqa: E402
from sources.layers.wmsr import WmsrTiles  # noqa: E402
from grid import make_grid  # noqa: E402
from http_server import Answer  # noqa: E402

RECORDED = os.path.join(REPO, "tests", "data", "recorded", "wmsr")
MNT = "IGNF_LIDAR-HD_MNT_ELEVATION.ELEVATIONGRIDCOVERAGE.LAMB93"
MNS = "IGNF_LIDAR-HD_MNS_ELEVATION.ELEVATIONGRIDCOVERAGE.LAMB93"
RGE = "RGEALTI-MNT_PYR-ZIP_FXX_LAMB93_WMS"
L93 = "EPSG:2154"
# The recorded box at the Verdon (Escalès): 32 m on the LiDAR HD's pixel edges
BOX = (970339.75, 6302000.25, 970371.75, 6302032.25)


@pytest.fixture
def service(http_server, monkeypatch):
    for case in ("verdon", "rgealti", "sea", "errors"):
        with open(os.path.join(RECORDED, case, "requests.json"), encoding="utf-8") as f:
            for answer in json.load(f)["answers"]:
                with open(os.path.join(RECORDED, case, answer["body"]), "rb") as body:
                    parts = urlsplit(answer["url"])
                    http_server.add(f"{parts.path}?{parts.query}", body.read(), answer["content_type"],
                                    answer["status"])
    monkeypatch.setattr(net, "_sleep", lambda attempt: None)
    return http_server


def _reader(server, layer=MNT, **kwargs) -> WmsrReader:
    return WmsrReader("test", server.url("/wms-r/wms"), layer, L93, **kwargs)


def _read(path):
    with rio.open(path) as raster:
        return (raster.read(1, masked=True).astype(np.float32).filled(np.nan), raster.crs, raster.transform,
                raster.nodata)


def _answer(case: str, n: int) -> np.ndarray:
    """A recorded answer's own pixels, nodata as NaN."""
    with rio.open(os.path.join(RECORDED, case, f"{n:03d}.tif")) as raster:
        return raster.read(1, masked=True).astype(np.float32).filled(np.nan)


def _box(left, bottom, right, top, res) -> MapRequest:
    return MapRequest(left, bottom, right, top, round((right - left) / res), round((top - bottom) / res))


def test_recorded_answers_are_the_requests_of_the_reader():
    """The cassettes hold what the reader asks: every recorded query is one of its GetMaps (the server
    matches them exactly, so the other tests would find no answer otherwise)."""
    reader = WmsrReader("test", "https://data.geopf.fr/wms-r/wms", MNT, L93)
    params = dict(reader.getmap_params(_box(*BOX, 0.5)))
    assert params == {"SERVICE": "WMS", "VERSION": "1.3.0", "REQUEST": "GetMap", "LAYERS": MNT, "STYLES": "",
                      "CRS": "EPSG:2154", "BBOX": "970339.75,6302000.25,970371.75,6302032.25", "WIDTH": "64",
                      "HEIGHT": "64", "FORMAT": "image/geotiff", "FORMAT_OPTIONS": "compression:deflate"}
    with open(os.path.join(RECORDED, "verdon", "requests.json"), encoding="utf-8") as f:
        first = json.load(f)["answers"][0]
    assert first["url"].startswith("https://data.geopf.fr/wms-r/wms?")
    assert first["status"] == 200 and first["content_type"] == "image/geotiff"


def test_numbers_written_exactly():
    """No float noise in a BBOX: edges on .25/.75 (and whole metres) as they are, however computed."""
    reader = WmsrReader("test", "https://x/wms", MNT, L93)
    noisy = MapRequest(0.1 + 0.2 + 970339.45, 6302000.25, 970371.75000000001, 6302032.25, 64, 64)
    assert dict(reader.getmap_params(noisy))["BBOX"] == "970339.75,6302000.25,970371.75,6302032.25"
    whole = MapRequest(970340.0, 6302000.0, 970372.0, -0.0 + 6302032.0, 32, 32)
    assert dict(reader.getmap_params(whole))["BBOX"] == "970340,6302000,970372,6302032"
    negative = MapRequest(-0.25, -1000.75, 999.75, -0.75, 2000, 2000)
    assert dict(reader.getmap_params(negative))["BBOX"] == "-0.25,-1000.75,999.75,-0.75"


def test_tile_kept_exactly_with_its_crs(service, tmp_path):
    """The answer's pixels as they come, on the box's own grid, in EPSG:2154 (the answer names a broken
    PROJCS["EPSG:2154"] on an unknown datum: the reader's CRS is forced)."""
    path = str(tmp_path / "box.tif")
    fetched = _reader(service).fetch(_box(*BOX, 0.5), path)
    assert fetched.received > 0
    values, crs, transform, nodata = _read(path)
    assert crs == rio.crs.CRS.from_epsg(2154)
    assert transform == from_origin(BOX[0], BOX[3], 0.5, 0.5)
    np.testing.assert_array_equal(values, _answer("verdon", 1))
    assert np.isfinite(values).all() and 1130 < np.nanmin(values) < np.nanmax(values) < 1145


def test_a_box_and_its_halves(service, tmp_path):
    """Two halves of a box give its pixels exactly (the service keeps its stored pixels, the reader too)."""
    reader = _reader(service)
    reader.fetch(_box(*BOX, 0.5), str(tmp_path / "box.tif"))
    middle = (BOX[0] + BOX[2]) / 2
    reader.fetch(_box(BOX[0], BOX[1], middle, BOX[3], 0.5), str(tmp_path / "left.tif"))
    reader.fetch(_box(middle, BOX[1], BOX[2], BOX[3], 0.5), str(tmp_path / "right.tif"))
    box, left, right = (_read(str(tmp_path / f"{n}.tif"))[0] for n in ("box", "left", "right"))
    np.testing.assert_array_equal(np.hstack([left, right]), box)
    assert _read(str(tmp_path / "right.tif"))[2] == from_origin(middle, BOX[3], 0.5, 0.5)


def test_one_pixel_shift(service, tmp_path):
    """A box one pixel further east gives the same values, shifted by one column."""
    reader = _reader(service)
    reader.fetch(_box(*BOX, 0.5), str(tmp_path / "box.tif"))
    reader.fetch(_box(BOX[0] + 0.5, BOX[1], BOX[2] + 0.5, BOX[3], 0.5), str(tmp_path / "east.tif"))
    box, east = _read(str(tmp_path / "box.tif"))[0], _read(str(tmp_path / "east.tif"))[0]
    np.testing.assert_array_equal(east[:, :-1], box[:, 1:])


def test_one_metre_is_the_mean_of_four(service, tmp_path):
    """At 1 m on the pixel edges (.75/.25) the server answers the mean of the 2 x 2 pixels of 0.5 m."""
    reader = _reader(service)
    reader.fetch(_box(*BOX, 0.5), str(tmp_path / "half.tif"))
    reader.fetch(_box(*BOX, 1.0), str(tmp_path / "one.tif"))
    half, (one, _, transform, _) = _read(str(tmp_path / "half.tif"))[0], _read(str(tmp_path / "one.tif"))
    assert transform == from_origin(BOX[0], BOX[3], 1.0, 1.0)
    mean = half.reshape(32, 2, 32, 2).astype(np.float64).mean(axis=(1, 3))
    assert np.abs(one - mean).max() < 2e-4


def test_deflate_keeps_the_values(service, tmp_path):
    """FORMAT_OPTIONS=compression:deflate (the default) changes no value: the same as uncompressed."""
    _reader(service).fetch(_box(*BOX, 0.5), str(tmp_path / "deflate.tif"))
    _reader(service, params=()).fetch(_box(*BOX, 0.5), str(tmp_path / "plain.tif"))
    np.testing.assert_array_equal(_read(str(tmp_path / "deflate.tif"))[0], _read(str(tmp_path / "plain.tif"))[0])
    assert _answer("verdon", 7).shape == (64, 64)


def test_surface_model(service, tmp_path):
    _reader(service, MNS).fetch(_box(*BOX, 0.5), str(tmp_path / "mns.tif"))
    surface = _read(str(tmp_path / "mns.tif"))[0]
    np.testing.assert_array_equal(surface, _answer("verdon", 6))
    assert np.nanmax(surface - _answer("verdon", 1)) > 1  # trees or bushes on the plateau


def test_rge_alti_nodata_and_whole_metres(service, tmp_path):
    """RGE ALTI 1 m: pixel edges on whole metres, centimetre values, nodata -99999 (NaN in the tile)."""
    box = (970340.0, 6302000.0, 970372.0, 6302032.0)
    _reader(service, RGE).fetch(_box(*box, 1.0), str(tmp_path / "rge.tif"))
    values, _, transform, _ = _read(str(tmp_path / "rge.tif"))
    assert transform == from_origin(970340, 6302032, 1, 1)
    assert np.isfinite(values).all()
    assert np.allclose(values * 100, np.round(values * 100), atol=2e-3)


def test_all_nodata_is_missing(service, tmp_path):
    """The sea off Étretat: HTTP 200 with every pixel -9999 is no data there, not an error: no file."""
    path = str(tmp_path / "sea.tif")
    fetched = _reader(service).fetch(_box(494390.75, 6961600.25, 494422.75, 6961632.25, 0.5), path)
    assert fetched.received == 0 and not os.path.exists(path)


def test_exception_report_is_an_error(service, tmp_path):
    """A ServiceExceptionReport (HTTP 400, text/xml: an unknown layer) never becomes data."""
    path = str(tmp_path / "bad.tif")
    with pytest.raises(RuntimeError, match="LayerNotDefined|unknown"):
        _reader(service, "NO_SUCH_LAYER").fetch(_box(*BOX, 0.5), path)
    assert not os.path.exists(path)


def test_too_large_refused_before_asking(service, tmp_path):
    """More than MaxWidth/MaxHeight (5010 px, the capabilities; the recorded 5011 px answer is a 400) is
    refused by the reader without a request."""
    reader = _reader(service)
    asked = len(service.requests("/wms-r"))
    with pytest.raises(ValueError, match="5010"):
        reader.fetch(MapRequest(BOX[0], BOX[1], BOX[0] + 5011 * 0.5, BOX[3], 5011, 64), str(tmp_path / "big.tif"))
    assert len(service.requests("/wms-r")) == asked


def _serve(server, body: bytes, content_type: str, status: int = 200):
    server.route("/lying", lambda request: Answer(status, body, {"Content-Type": content_type}))
    return WmsrReader("test", server.url("/lying/wms"), MNT, L93)


def test_an_answer_that_is_no_geotiff(http_server, tmp_path, monkeypatch):
    """An exception report labelled image/geotiff (a content type that lies), or as text/xml with HTTP 200:
    an error, no file."""
    monkeypatch.setattr(net, "_sleep", lambda attempt: None)
    report = open(os.path.join(RECORDED, "errors", "002.xml"), "rb").read()
    for kind in ("image/geotiff", "text/xml"):
        server_reader = _serve(http_server, report, kind)
        path = str(tmp_path / "x.tif")
        with pytest.raises(RuntimeError):
            server_reader.fetch(_box(*BOX, 0.5), path)
        assert not os.path.exists(path)
        http_server.routes.clear()


def test_an_answer_on_other_pixels_is_an_error(http_server, tmp_path):
    """An answer whose size or grid differs from the request (here the 1 m answer to a 0.5 m request) is
    never resampled into the tile: an error."""
    one_metre = open(os.path.join(RECORDED, "verdon", "005.tif"), "rb").read()
    reader = _serve(http_server, one_metre, "image/geotiff")
    path = str(tmp_path / "x.tif")
    with pytest.raises(RuntimeError, match="grid|size"):
        reader.fetch(_box(*BOX, 0.5), path)
    assert not os.path.exists(path)


def test_a_layer_the_server_forgets_now_and_then(http_server, tmp_path, monkeypatch):
    """IGN's servers answer now and then LayerNotDefined (HTTP 400) or 502 for a layer they have (seen
    twice in eleven requests while recording, none in 180 afterwards): an error, asked again (net._get's
    retries), the tile's pixels from the next answer."""
    monkeypatch.setattr(net, "_sleep", lambda attempt: None)
    report = open(os.path.join(RECORDED, "errors", "003.xml"), "rb").read()
    tiff = open(os.path.join(RECORDED, "verdon", "001.tif"), "rb").read()
    answers = [Answer(400, report, {"Content-Type": "text/xml; charset=UTF-8"}),
               Answer(502, b"<html>502 Bad Gateway</html>", {"Content-Type": "text/html"}),
               Answer(200, tiff, {"Content-Type": "image/geotiff"})]
    http_server.route("/flaky", lambda request: answers.pop(0))
    path = str(tmp_path / "x.tif")
    WmsrReader("test", http_server.url("/flaky/wms"), MNT, L93).fetch(_box(*BOX, 0.5), path)
    np.testing.assert_array_equal(_read(path)[0], _answer("verdon", 1))
    assert len(http_server.requests("/flaky")) == 3


def test_a_longer_burst_and_a_layer_that_is_gone(http_server, tmp_path, monkeypatch):
    """LayerNotDefined for longer than net._get's retries (two of its rounds here): asked again in more rounds,
    longer apart; a layer that stays unknown fails after them (net.RETRIES x (1 + TRANSIENT_ROUNDS) requests)."""
    from sources.readers import wmsr
    slept = []
    monkeypatch.setattr(net, "_sleep", slept.append)
    report = open(os.path.join(RECORDED, "errors", "003.xml"), "rb").read()
    tiff = open(os.path.join(RECORDED, "verdon", "001.tif"), "rb").read()
    answers = [Answer(400, report, {"Content-Type": "text/xml; charset=UTF-8"})] * (2 * net.RETRIES) +         [Answer(200, tiff, {"Content-Type": "image/geotiff"})]
    http_server.route("/burst", lambda request: answers.pop(0))
    path = str(tmp_path / "x.tif")
    WmsrReader("test", http_server.url("/burst/wms"), MNT, L93).fetch(_box(*BOX, 0.5), path)
    np.testing.assert_array_equal(_read(path)[0], _answer("verdon", 1))
    assert [a for a in slept if a >= 3] == [3, 4]  # the rounds' pauses, between net._get's own
    http_server.route("/gone", lambda request: Answer(400, report, {"Content-Type": "text/xml; charset=UTF-8"}))
    with pytest.raises(RuntimeError, match="LayerNotDefined"):
        WmsrReader("test", http_server.url("/gone/wms"), MNT, L93).fetch(_box(*BOX, 0.5), str(tmp_path / "y.tif"))
    assert len(http_server.requests("/gone")) == net.RETRIES * (1 + wmsr.TRANSIENT_ROUNDS)


def test_probe_asks_a_small_getmap(http_server, tmp_path, monkeypatch):
    """The source probe asks a GetMap of 16 x 16 px at the top left of the first tile, as the reader writes
    it (the probe's strategy "getmap"); an exception report fails it."""
    from sources import probe
    from sources.source import ReadmeRow, Source
    monkeypatch.setattr(net, "_sleep", lambda attempt: None)
    tiff = open(os.path.join(RECORDED, "verdon", "001.tif"), "rb").read()
    forgotten = open(os.path.join(RECORDED, "errors", "003.xml"), "rb").read()
    answers = [Answer(400, forgotten, {"Content-Type": "text/xml"})]  # a transient answer first: asked again
    http_server.route("/probe", lambda request: answers.pop(0) if answers else
                      Answer(200, tiff, {"Content-Type": "image/geotiff"}))
    layer = WmsrTiles("LiDAR HD test", http_server.url("/probe/wms"), MNT, L93, "france/test/live", native_res=0.5,
                      fetch_res=(0.5, 1.0), tile_m=1000, origin=(-0.25, 0.25))
    source = Source(id="fr_test", name="test", description="test", nmt=layer, crs=L93, grid_origin=(0.75, 0.25),
                    listing=ReadmeRow("x", "y"), sample=(43.7655, 6.358))
    row = probe.probe_layer(source, layer, "terrain", str(tmp_path / "data"), str(tmp_path / "probe"), False)
    assert (row.index, row.read) == (probe.NONE, probe.OK), row.notes
    asked = dict(http_server.requests("/probe")[1].query)
    assert (asked["WIDTH"], asked["HEIGHT"], asked["BBOX"]) == ("16", "16", "969999.75,6301984.25,970015.75,6302000.25")
    http_server.routes.clear()
    report = open(os.path.join(RECORDED, "errors", "002.xml"), "rb").read()
    http_server.route("/probe", lambda request: Answer(200, report, {"Content-Type": "image/geotiff"}))
    row = probe.probe_layer(source, layer, "terrain", str(tmp_path / "data"), str(tmp_path / "probe"), False)
    assert row.read == probe.FAILED and "LayerNotDefined" in " ".join(row.notes)


def test_not_found_is_missing(http_server, tmp_path):
    reader = WmsrReader("test", http_server.url("/nothing/wms"), MNT, L93)
    path = str(tmp_path / "x.tif")
    assert reader.fetch(_box(*BOX, 0.5), path).received == 0 and not os.path.exists(path)


# The layer: tiles of a fixed grid at the fetch resolution chosen for the grid


def _layer(**kwargs) -> WmsrTiles:
    return WmsrTiles("LiDAR HD test", "https://data.geopf.fr/wms-r/wms", MNT, L93, "france/test/live",
                     native_res=0.5, fetch_res=(0.5, 1.0), tile_m=1000, origin=(-0.25, 0.25), **kwargs)


def test_tiles_are_ign_tiles():
    """Tile (res, i, j) is IGN's tile LHD_FXX_<i>_<j + 1> (X the km of its west edge, Y of its north edge):
    BBOX X*1000-0.25, (Y-1)*1000+0.25, X*1000+999.75, Y*1000+0.25 (wave 0), 2000 px at 0.5 m, 1000 at 1 m."""
    layer = _layer()
    for res, px in ((0.5, 2000), (1.0, 1000)):
        request = layer.index.request((res, 969, 6301))
        assert request == MapRequest(968999.75, 6301000.25, 969999.75, 6302000.25, px, px)
        assert dict(layer.reader.getmap_params(request))["BBOX"] == "968999.75,6301000.25,969999.75,6302000.25"


@pytest.mark.parametrize("res, fetched", [(1.0, 1.0), (2.0, 1.0), (5.0, 1.0), (0.5, 0.5), (0.75, 0.5)])
def test_fetch_resolution_of_a_grid(res, fetched):
    """The coarsest fetch resolution not coarser than the grid (the finest below all of them)."""
    grid = make_grid((970100, 6301500, 970400, 6302400), res, L93, (0.75, 0.25))
    tiles = _layer().tiles(grid)
    assert tiles and {t[0] for t in tiles} == {fetched}
    assert {(t[1], t[2]) for t in tiles} == {(970, 6301), (970, 6302)}


def test_paths_and_tile_of(tmp_path):
    layer = _layer()
    for tile, path in (((1.0, 969, 6301), "france/test/live/epsg2154-1m-1000px-tif-o-0.25_0.25/969_6301.tif"),
                       ((0.5, 969, 6301), "france/test/live/epsg2154-0.5m-2000px-tif-o-0.25_0.25/969_6301.tif")):
        found = os.path.relpath(layer.tile_path(str(tmp_path), tile), tmp_path).replace(os.sep, "/")
        assert found == path
        assert layer.tile_of(path) == tile
    assert layer.tile_of("france/test/live/epsg2154-1m-2000px-tif-o-0.25_0.25/969_6301.tif") is None
    assert layer.ttl_days is not None  # "live": editions are re-issued


def test_layer_downloads_a_tile(service, tmp_path):
    """The whole path of a layer: its index's request fetched by its reader (a 32 m tile here)."""
    layer = WmsrTiles("LiDAR HD test", service.url("/wms-r/wms"), MNT, L93, "france/test/live", native_res=0.5,
                      fetch_res=(0.5, 1.0), tile_m=32, origin=(BOX[0] % 32, BOX[1] % 32))
    i, j = round((BOX[0] - BOX[0] % 32) / 32), round((BOX[1] - BOX[1] % 32) / 32)
    path = layer.tile_path(str(tmp_path), (0.5, i, j))
    assert layer.download_tile((0.5, i, j), path).received > 0
    np.testing.assert_array_equal(_read(path)[0], _answer("verdon", 1))
    assert layer.tile_url((0.5, i, j)) == service.url("/wms-r/wms")


def test_france_layers():
    france, rge = src.SOURCES["france"], src.SOURCES["france_rgealti"]
    assert isinstance(france.nmt, WmsrTiles) and isinstance(france.nmpt, WmsrTiles) and isinstance(rge.nmt, WmsrTiles)
    assert france.nmt.reader.layer == MNT and france.nmpt.reader.layer == MNS and rge.nmt.reader.layer == RGE
    assert france.default_resolution == 1.0 and france.grid_origin == (0.75, 0.25)
    assert rge.grid_origin == (0.0, 0.0) and rge.nmpt is None
    assert france.fallbacks == ["france_rgealti", "europe"]
    from sources import probe
    assert probe.strategy(france.nmt) == "getmap"
