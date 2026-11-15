"""Italy's sources of batch 5: Sardinia's coastal lidar (a WFS of its tiles' footprints as GeoJSON,
sources/indexes/listings.py WfsFeatures and sources/layers/sheets.py WfsFeatureTiles, ZIPs of ASCII grids with
centres on whole metres) and TINITALY (INGV's WCS: its open sea all 0 without nodata), against tests/http_server.py;
the catalogue's two sources (offline)."""

import io
import json
import os
import zipfile

import numpy as np
import pytest
import rasterio as rio
import requests
from rasterio.transform import from_origin

import cache
import sources as src
from grid import make_grid
from http_server import Answer
from sources import net
from sources.catalogue import italy
from sources.indexes.cached import IndexUnavailable
from sources.indexes.listings import WfsFeatures

LAT, LON = 40.25, 9.5  # the 0.25° tile of the made-up answers
X0, Y0 = 552314.5, 4460004.5  # a tile's south-west pixel edge (its first centre on whole metres, as Sardinia's)
COLS, ROWS = 6, 4


@pytest.fixture
def no_sleep(monkeypatch):
    monkeypatch.setattr(net, "_sleep", lambda attempt: None)


def _feature(name: str, x0: float, y0: float, url, cols: int = COLS, rows: int = ROWS) -> dict:
    ring = [[x0, y0], [x0 + cols, y0], [x0 + cols, y0 + rows], [x0, y0 + rows], [x0, y0]]
    return {"type": "Feature", "id": f"QU.{name}", "geometry": {"type": "MultiPolygon", "coordinates": [[ring]]},
            "properties": {"nomemappa": name, "dtm": url, "dsm": None}}


def _collection(features, matched=None) -> bytes:
    return json.dumps({"type": "FeatureCollection", "features": features, "totalFeatures": len(features),
                       "numberMatched": len(features) if matched is None else matched,
                       "numberReturned": len(features)}).encode()


def _asc(values: np.ndarray, x0: float = X0, y0: float = Y0) -> bytes:
    """An ASCII grid as Sardinia's: no CRS, XLLCENTER / YLLCENTER on whole metres, millimetres, CRLF."""
    rows, cols = values.shape
    head = (f"NCOLS {cols}\r\nNROWS {rows}\r\nCELLSIZE 1.000\r\nXLLCENTER {x0 + 0.5:.3f}\r\n"
            f"YLLCENTER {y0 + 0.5:.3f}\r\nNODATA_VALUE -9999.000\r\n")
    body = "".join(" " + " ".join(f"{v:.3f}" for v in row) + "\r\n" for row in values)
    return (head + body).encode()


def _zip(name: str, values: np.ndarray, **kwargs) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(f"{name}_WGS.ASC", _asc(values, **kwargs))
    return out.getvalue()


def _layer(server, link: str = "dtm") -> src.WfsFeatureTiles:
    return src.WfsFeatureTiles("DTM test", server.url("/geoserver/ows"), italy.SAR_TYPE, link, "nomemappa",
                               "sar-test", "test_it/sar-test/2008", "EPSG:32632", 1.0, 2008)


def _serve_index(server, body: bytes, status: int = 200, kind: str = "application/json;charset=UTF-8"):
    asked = []

    def answer(request):
        asked.append(dict(request.query))
        return Answer(status, body, {"Content-Type": kind})
    server.route("/geoserver/ows", answer)
    return asked


def test_listing_asks_geojson_in_the_files_crs(http_server, tmp_path):
    """One GetFeature per 0.25° tile: GeoJSON, the footprints in EPSG:32632 (their extents the files' own), the box
    in EPSG:4326 (lat, lon); a feature without a URL or a geometry is left out."""
    url = http_server.url("/dl/500120_03.ZIP")
    features = [_feature("500120_03", X0, Y0, url), _feature("500120_04", X0 + COLS, Y0, None),
                {**_feature("500120_05", X0, Y0, url), "geometry": None}]
    asked = _serve_index(http_server, _collection(features))
    listing = WfsFeatures(http_server.url("/geoserver/ows"), italy.SAR_TYPE, "dtm", "nomemappa", "EPSG:32632", 1.0,
                          2008)
    listing.use(None, str(tmp_path))
    answer = listing.fetch(LAT, LON)
    assert answer == {"sheets": [{"year": 2008, "godlo": "500120_03", "url": url, "crs": "EPSG:32632", "res": 1.0,
                                  "extent": [X0, Y0, X0 + COLS, Y0 + ROWS]}]}
    (query,) = asked
    assert query["TYPENAMES"] == italy.SAR_TYPE and query["OUTPUTFORMAT"] == "application/json"
    assert query["SRSNAME"] == "urn:ogc:def:crs:EPSG::32632"
    assert query["BBOX"] == "40.25,9.5,40.5,9.75,urn:ogc:def:crs:EPSG::4326"
    assert {r.user_agent for r in http_server.log} == {cache.http_headers()["User-Agent"]}


@pytest.mark.parametrize("body, status, kind", [
    (b'<?xml version="1.0"?><ows:ExceptionReport><ows:Exception><ows:ExceptionText>Unknown type'
     b'</ows:ExceptionText></ows:Exception></ows:ExceptionReport>', 200, "application/xml"),
    (b"<html>maintenance</html>", 200, "text/html"),
    (_collection([_feature("500120_03", X0, Y0, "https://example.org/a.ZIP")], matched=5000), 200,
     "application/json"),
])
def test_listing_errors_cache_nothing(http_server, tmp_path, body, status, kind):
    """An exception report (with HTTP 200), an answer that is no FeatureCollection and a cut listing (more matched
    than returned) are IndexUnavailable; nothing is cached, the cached files are used."""
    _serve_index(http_server, body, status, kind)
    layer = _layer(http_server)
    cache_dir = str(tmp_path / "cache")
    with pytest.raises(IndexUnavailable):
        layer.index.listing.fetch(LAT, LON)
    layer._use(cache_dir)
    grid = make_grid((X0, Y0, X0 + COLS, Y0 + ROWS), 1.0, "EPSG:32632", italy.SAR_ORIGIN)
    assert layer.tiles(grid) is None
    assert not os.path.exists(layer.index_path(cache_dir, LAT, LON))


def test_http_error_is_a_request_error(http_server, tmp_path):
    _serve_index(http_server, b"busy", 503, "text/plain")
    with pytest.raises(requests.RequestException):
        _layer(http_server).index.listing.fetch(LAT, LON)


def test_tiles_on_their_own_pixels(http_server, tmp_path):
    """A listed ZIP of one ASCII grid without a CRS: cached in EPSG:32632 with its pixel edges on .5 m, the heights
    to the millimetre, its nodata none; on a grid of origin (0.5, 0.5) the mosaic is the file itself. A listed tile
    the server lacks (404) is no data."""
    rng = np.random.default_rng(3)
    values = np.round(rng.uniform(100, 300, (ROWS, COLS)), 3)
    values[0, 0] = -9999.0
    http_server.add("/dl/500120_03.ZIP", _zip("500120_03", values), "application/zip")
    features = [_feature("500120_03", X0, Y0, http_server.url("/dl/500120_03.ZIP")),
                _feature("500120_04", X0 + COLS, Y0, http_server.url("/dl/500120_04.ZIP"))]
    _serve_index(http_server, _collection(features))
    layer = _layer(http_server)
    cache_dir = str(tmp_path / "cache")
    grid = make_grid((X0, Y0, X0 + 2 * COLS, Y0 + ROWS), 1.0, "EPSG:32632", italy.SAR_ORIGIN)
    layer._use(cache_dir)
    assert sorted(t.godlo for t in layer.tiles(grid)) == ["500120_03", "500120_04"]
    out = src.prepare_layer(layer, grid, cache_dir, str(tmp_path / "nmt.npy"), "terrain")
    path = os.path.join(cache_dir, "test_it", "sar-test", "2008", "2008_500120_03.tif")
    with rio.open(path) as cached:
        assert cached.crs.to_epsg() == 32632 and cached.transform == from_origin(X0, Y0 + ROWS, 1.0, 1.0)
        assert np.isnan(cached.read(1)[0, 0])
    assert not os.path.exists(os.path.join(cache_dir, "test_it", "sar-test", "2008", "2008_500120_04.tif"))
    mosaic = np.load(out)
    expected = np.where(values == -9999.0, np.nan, values).astype(np.float32)
    assert np.allclose(mosaic[:, :COLS], expected, atol=0.0051, equal_nan=True)  # LERC within 5 mm
    assert np.isnan(mosaic[:, COLS:]).all()
    assert layer.used(grid, cache_dir)["survey_years"] == [2008, 2008]


def test_probe_reads_the_first_kb(http_server, tmp_path):
    """The probe of Sardinia's layers reads the first KB of a tile's ZIP, never a byte range 0-0."""
    from sources import probe
    rng = np.random.default_rng(4)
    http_server.add("/dl/500120_03.ZIP", _zip("500120_03", rng.uniform(0, 9, (300, 300))), "application/zip")
    http_server.add("/dl/missing.ZIP", b"<html>Not Found</html>", "text/html", status=404)
    layer = _layer(http_server)
    sheet = src.Sheet(2008, "500120_03", "500120_03", http_server.url("/dl/500120_03.ZIP"), "EPSG:32632", 1.0)
    assert probe.strategy(layer) == "zipfile"
    assert probe._zip_head(str(tmp_path), layer, sheet) == ""
    assert all("range" not in r.headers for r in http_server.requests("/dl/"))
    missing = src.Sheet(2008, "missing", "missing", http_server.url("/dl/missing.ZIP"), "EPSG:32632", 1.0)
    with pytest.raises(RuntimeError, match="HTTP 404"):
        probe._zip_head(str(tmp_path), layer, missing)


def _tiff(values: np.ndarray, left: float, top: float, nodata) -> bytes:
    with rio.io.MemoryFile() as memfile:
        with memfile.open(driver="GTiff", width=values.shape[1], height=values.shape[0], count=1, dtype="float32",
                          crs="EPSG:32632", transform=from_origin(left, top, 10.0, 10.0), nodata=nodata,
                          compress="deflate") as dst:
            dst.write(values.astype(np.float32), 1)
        return memfile.read()


def test_tinitaly_tiles(http_server, tmp_path, no_sleep):
    """TINITALY's WCS as the layer asks it (WCS 2.0.1, axes E N, DEFLATE, 10 km tiles at 10 m): the sea of a tile
    with granules is -9999, a tile without any is all 0 without a nodata tag, both no data; heights stay."""
    px = 1000
    land = np.full((px, px), 250.0, np.float32)
    land[:, :100] = -9999.0
    asked = []

    def answer(request):
        query = dict(request.query)
        asked.append(query)
        east = [v for k, v in request.query if k == "SUBSET" and v.startswith("E(")][0]
        left = float(east[2:].split(",")[0])
        if left == 870000.0:
            body = _tiff(land, left, 4720000.0, -9999.0)
        else:  # no granule: GeoServer's background, 0 without nodata
            body = _tiff(np.zeros((px, px)), left, 4720000.0, None)
        return Answer(200, body, {"Content-Type": "image/tiff"})
    http_server.route("/wcs", answer)
    dem = italy.TINITALY_DEM  # the catalogue's layer, asked on the local server
    assert dem.reader.zero_is_nodata and dem.params == (("GEOTIFF:COMPRESSION", "DEFLATE"),)
    assert (dem.url, dem.coverage, dem.crs, dem.axes, dem.fmt) == (
        "https://tinitaly.pi.ingv.it/TINItaly_1_1/wcs", "TINItaly_1_1__tinitaly_dem", "EPSG:32632", ("E", "N"),
        "image/tiff")
    assert (dem.native_res, dem.fetch_res, dem.tile_px, dem.origin, dem.edge_px) == (10.0, 10.0, 1000, (0.0, 0.0), 0)
    layer = src.WcsTiles(dem.description, http_server.url("/wcs"), dem.coverage, dem.crs, "test_it/tinitaly",
                         native_res=dem.native_res, tile_px=dem.tile_px, fmt=dem.fmt, axes=dem.axes,
                         fetch_res=dem.fetch_res, zero_is_nodata=dem.reader.zero_is_nodata,
                         bytes_per_px=dem.bytes_per_px, params=dem.params)
    grid = make_grid((879000.0, 4711000.0, 881000.0, 4713000.0), 10.0, "EPSG:32632")
    cache_dir = str(tmp_path / "cache")
    out = np.load(src.prepare_layer(layer, grid, cache_dir, str(tmp_path / "t.npy"), "terrain"))
    assert np.isclose(np.nanmax(out), 250.0) and np.isnan(out[:, out.shape[1] // 2 + 1:]).all()
    assert all(q["GEOTIFF:COMPRESSION"] == "DEFLATE" and q["COVERAGEID"] == "TINItaly_1_1__tinitaly_dem"
               for q in asked)
    assert not any("SCALESIZE" in q for q in asked)


def _local(path: str, grid, band: np.ndarray) -> str:
    with rio.open(path, "w", driver="GTiff", width=band.shape[1], height=band.shape[0], count=1, dtype="float32",
                  crs=grid.crs, nodata=-9999.0, transform=from_origin(grid.left, grid.top, grid.res, grid.res)) as dst:
        dst.write(np.where(np.isnan(band), -9999.0, band).astype(np.float32), 1)
    return path


class _File(src.FileLayer):
    """A local file that records its credit, as the cached layers do."""

    def used(self, grid, cache_dir):
        return {**super().used(grid, cache_dir), "credit": self.credit.as_dict()}


@pytest.mark.parametrize("tinitaly_has_data", [True, False])
def test_chain_credits_the_layers_that_filled(tmp_path, tinitaly_has_data):
    """A regional source's chain [tinitaly, europe]: where TINITALY fills the gaps (its terrain also the surface's:
    it has no surface model) the run credits INGV only, not FABDEM nor Copernicus; where it has no data there, FABDEM
    and Copernicus fill and are credited, INGV is not (filling.fill_gaps drops a layer that filled no pixel)."""
    import search
    grid = make_grid((880000, 4700000, 881000, 4701000), 10, "EPSG:32632")
    shape = (grid.height, grid.width)
    terrain, surface = np.full(shape, 500.0, np.float32), np.full(shape, 505.0, np.float32)
    terrain[40:60, 40:60] = np.nan
    surface[40:60, 40:60] = np.nan
    nmt, nmpt = str(tmp_path / "nmt.npy"), str(tmp_path / "nmpt.npy")
    np.save(nmt, terrain)
    np.save(nmpt, surface)

    def layer(name, value, credit):
        made = _File(name, _local(str(tmp_path / f"{name}.tif"), grid, np.full(shape, value, np.float32)))
        made.credit = credit
        return made
    tin_credit = src.SOURCES["tinitaly"].credits[0]
    copernicus = src.SOURCES["europe"].credits[1]
    tin = src.Source(id="tinitaly_test", name="TINITALY test", description="t", credits=(tin_credit,),
                     nmt=layer("tinitaly", 501.0 if tinitaly_has_data else np.nan, tin_credit))
    europe = src.Source(id="europe_test", name="europe test", description="e", fallback=None,
                        credits=(src.FABDEM_CREDIT, copernicus), nmt=layer("fabdem", 499.0, src.FABDEM_CREDIT),
                        nmpt=layer("copernicus", 510.0, copernicus))
    src.mosaic.used_data.clear()
    try:
        _, counts = src.filling.fill_gaps_chain(nmt, nmpt, grid, [tin, europe], str(tmp_path / "cache"),
                                                str(tmp_path / "gap.npy"))

        class _Plan:
            area = None
        credits = {c["data"] for c in search._credits(_Plan(), search._dated_data(search._merged_data(), 2026))}
    finally:
        src.mosaic.used_data.clear()
    assert [n > 0 for _, n in counts] == ([True, False] if tinitaly_has_data else [False, True])
    assert not np.isnan(np.load(nmt)).any() and not np.isnan(np.load(nmpt)).any()
    if tinitaly_has_data:
        assert tin_credit.data in credits and not credits & {src.FABDEM_CREDIT.data, copernicus.data}
    else:
        assert {src.FABDEM_CREDIT.data, copernicus.data} <= credits and tin_credit.data not in credits


def test_probe_layer_dispatches_zipfile(http_server, tmp_path):
    """probe_layer on a WfsFeatureTiles: the kind "zipfile", its index asked (OK) and the first tile's ZIP read by
    its first KB (OK), no Range header sent."""
    from pyproj import Transformer
    from sources import probe
    rng = np.random.default_rng(5)
    http_server.add("/dl/500120_03.ZIP", _zip("500120_03", rng.uniform(0, 9, (ROWS, COLS))), "application/zip")
    _serve_index(http_server, _collection([_feature("500120_03", X0, Y0, http_server.url("/dl/500120_03.ZIP"))]))
    layer = _layer(http_server)
    lon, lat = Transformer.from_crs("EPSG:32632", "EPSG:4326", always_xy=True).transform(X0 + 3, Y0 + 2)
    source = src.Source(id="sar_test", name="sar test", description="s", nmt=layer, crs="EPSG:32632",
                        grid_origin=italy.SAR_ORIGIN, sample=(lat, lon))
    row = probe.probe_layer(source, layer, "terrain", str(tmp_path), str(tmp_path / "probe"), deep=False)
    assert (row.index, row.read) == (probe.OK, probe.OK), row.notes
    assert http_server.requests("/dl/500120_03.ZIP")
    assert all("range" not in r.headers for r in http_server.requests("/dl/"))


def test_sources():
    tin, sar = src.SOURCES["tinitaly"], src.SOURCES["sardinia"]
    assert tin.countries == ("it", "sm", "va") and tin.regions == () and tin.crs == "EPSG:32632"
    assert tin.nmpt is None and tin.default_resolution == 10.0 and tin.map_areas() == ("it",)
    assert tin.credits[0].licence == "CC BY 4.0" and tin.nmt.folder == "italy/tinitaly/1.1"
    assert sar.regions == ("it-88",) and sar.grid_origin == (0.5, 0.5) and sar.fallbacks == ["tinitaly", "europe"]
    assert isinstance(sar.nmt, src.WfsFeatureTiles) and sar.nmt.link == "dtm" and sar.nmpt.link == "dsm"
    assert sar.nmt.folder == "italy/sar-dtm/2008" and sar.nmpt.folder == "italy/sar-dsm/2008"
    assert sar.nmt.ttl_days is None and sar.ortho is None and tin.ortho is None
    assert src.HOST_SLOTS_OF["tinitaly.pi.ingv.it"] == 2 and src.HOST_SLOTS_OF["webgis.regione.sardegna.it"] == 2
    ids = [s.id for s in italy.SOURCES]  # the regions' sources before TINITALY (the catalogue's order: test_catalogue)
    assert ids.index("tinitaly") == len(ids) - 1


@pytest.mark.parametrize("lat, lon, found", [
    (40.2850, 9.6300, "it-88"),   # Cala Gonone
    (41.3100, 9.3600, "it-88"),   # Razzoli, La Maddalena
    (41.3350, 9.2700, "fr"),      # Lavezzi, Corsica
    (41.2050, 13.5650, "it"),     # Gaeta
    (37.7500, 15.0000, "it"),     # Etna
    (36.7900, 11.9900, "it"),     # Pantelleria
    (35.5100, 12.6000, "it"),     # Lampedusa
    (42.1200, 15.5000, "it"),     # the Tremiti islands
    (45.0800, 7.6800, "it"),      # Turin
    (46.5000, 11.3500, "at"),     # Bolzano: Austria's box comes first (as before)
    (45.4500, 6.9800, None),      # Val d'Isère (France, no box)
    (43.7750, 7.5050, None),      # Menton
    (43.7380, 7.4240, None),      # Monaco
    (37.2700, 9.8700, None),      # Bizerte, Tunisia
    (37.5300, 8.9300, None),      # La Galite, Tunisia
    (42.6400, 18.1100, None),     # Dubrovnik
    (45.2300, 13.6000, None),     # Poreč, Istria
    # The Alps and Friuli: the neighbours' boxes come first (as before), Italy's hold the rest
    (45.7915, 6.9733, "it-23"),   # Courmayeur: Valle d'Aosta's band (45.75-45.80 N from 6.80 E)
    (45.0800, 6.7000, "it"),      # Bardonecchia
    (44.9400, 6.7500, "it"),      # Claviere
    (43.8700, 7.5400, "it"),      # Airole, the Roya below Breil
    (46.5405, 12.1357, "at"),     # Cortina d'Ampezzo
    (46.6000, 12.3000, "at"),     # Tre Cime, the Belluno side (Auronzo)
    (46.5670, 12.6900, "at"),     # Sappada
    (46.5050, 13.5780, "at"),     # Tarvisio
    (46.4670, 10.3700, "ch"),     # Bormio
    (46.5380, 10.1350, "ch"),     # Livigno
    (46.3800, 8.4200, "ch"),      # Val Formazza
    (45.6500, 13.7700, "si"),     # Trieste
    (45.6200, 13.8800, "si"),     # Val Rosandra
    # Just across the borders: never Italy's
    (45.2000, 6.6700, None),      # Modane
    (45.2850, 6.8750, None),      # Lanslebourg
    (44.9000, 6.6400, None),      # Briançon
    (44.3870, 6.6520, None),      # Barcelonnette
    (44.0880, 7.5940, None),      # Tende
    (45.9230, 6.8700, "ch"),      # Chamonix (Switzerland's box, as before)
    (45.8350, 9.0300, "ch"),      # Chiasso
    (45.9560, 13.6480, "si"),     # Nova Gorica
    (46.4850, 13.7850, "at"),     # Kranjska Gora (Austria's box, as before)
])
def test_offline_boxes(lat, lon, found):
    """Offline, the first box holding a point wins: Italy's keep off its neighbours without boxes of their own."""
    code = next((code for code, (s, n, w, e) in src.OFFLINE_BOXES if s <= lat <= n and w <= lon <= e), None)
    assert code == found


@pytest.mark.parametrize("lat, lon", [
    (45.7915, 6.9733), (46.5405, 12.1357), (46.6000, 12.3000), (46.5670, 12.6900), (46.4670, 10.3700),
    (46.5380, 10.1350), (46.4300, 8.4300), (46.5050, 13.5780), (45.6500, 13.7700), (45.6200, 13.8800),
    (45.0800, 6.7000), (43.8700, 7.5400), (41.9300, 16.0000), (44.1200, 7.7200), (43.7900, 7.5400)])
def test_coverage_boxes_hold_italy(lat, lon):
    """TINITALY's coverage (its offline boxes: an area download of Italy clips the outline to them) holds Italy's
    Alps, Friuli, Trieste, the Gargano and the Ligurian border."""
    assert any(s <= lat <= n and w <= lon <= e for s, n, w, e in src.SOURCES["tinitaly"].coverage_boxes())
