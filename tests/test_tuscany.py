"""Tuscany's lidar sheets (Regione Toscana's cartoteca): the WFS listing and which surveys of a sheet are read
(sources/indexes/cartoteca.py), the GetFeatureInfo that names a file's hashed URL and the ZIP whose licence names its
owner (sources/readers/cartoteca.py), the credits per owner (sources/layers/cartoteca.py, Layer.used_entries) through
the record of the data a run used, against tests/http_server.py; the catalogue's source (offline)."""

import glob
import io
import json
import os
import zipfile

import numpy as np
import pytest
import rasterio as rio
import requests

import cache
import sources as src
from grid import make_grid
from http_server import Answer
from sources import choose, net
from sources.catalogue import italy
from sources.indexes import cartoteca as idx
from sources.indexes.cached import IndexUnavailable
from sources.layers.cartoteca import CartotecaTiles, owner_of
from sources.readers import cartoteca as rd

LAT, LON = 44.0, 10.0  # the 0.25° tile of the made-up answers (Carrara)
WMS = "/wmsraster/com.rt.wms.RTmap/wms"
DL = "/geoscopio/download/altimetria/lidar/"
# Sheets of 1600 x 1200 m (EPSG:3003) as the cartoteca's 22d35, 22d36, 22d43, 22d44
S35, S36, S43, S44 = (1588000, 4880400), (1589600, 4880400), (1588000, 4879200), (1589600, 4879200)
HASH = "0123456789abcdef0123456789abcdef"
RT_PDF = b"%PDF-1.4\n<< /URI (http://creativecommons.org/licenses/by/4.0/) >>\n%%EOF"
MATTM_PDF = b"%PDF-1.4\n<< /URI (https://creativecommons.org/licenses/by-sa/3.0/it/) >>\n%%EOF"


@pytest.fixture
def no_sleep(monkeypatch):
    monkeypatch.setattr(net, "_sleep", lambda attempt: None)


def _name(sheet: str, kind: str, lot: str, year: int, res: int = 1) -> str:
    return f"{sheet}_{res}x{res}_{kind}_{lot}_{year}_3003"


def _feature(sheet, lot, year, corner, ring=None, res=1, zero=False):
    """A MapServer GML 3.1.1 feature of rt_cartoteca.lidar2k: the footprint ring (default the whole sheet, 0.4 m off
    as the real ones), the sheet's box (0 for zero: the surveys of 2016 and 2017)."""
    x, y = corner
    ring = ring or [(x - 0.4, y + 0.4), (x + 1599.6, y + 0.4), (x + 1599.6, y + 1200.4), (x - 0.4, y + 1200.4)]
    ring = list(ring) + [ring[0]]
    pos = " ".join(f"{a:.6f} {b:.6f}" for a, b in ring)
    box = (0, 0, 0, 0) if zero else (x, y, x + 1600, y + 1200)
    return f"""
    <gml:featureMember>
      <ms:rt_cartoteca.lidar2k gml:id="rt_cartoteca.lidar2k.{abs(hash((sheet, lot, res))) % 10000}">
        <ms:GEOMETRY><gml:Polygon srsName="urn:ogc:def:crs:EPSG::3003"><gml:exterior><gml:LinearRing>
          <gml:posList srsDimension="2">{pos}</gml:posList></gml:LinearRing></gml:exterior></gml:Polygon></ms:GEOMETRY>
        <ms:foglio>{sheet.upper() if zero else sheet}</ms:foglio>
        <ms:dtmname>{_name(sheet, "dtm", lot, year, res)}</ms:dtmname>
        <ms:dsmname>{_name(sheet, "dsm", lot, year, res)}</ms:dsmname>
        <ms:eg_bsw>{box[0]}</ms:eg_bsw><ms:ng_bsw>{box[1]}</ms:ng_bsw>
        <ms:eg_bne>{box[2]}</ms:eg_bne><ms:ng_bne>{box[3]}</ms:ng_bne>
      </ms:rt_cartoteca.lidar2k>
    </gml:featureMember>"""


def _gml(features) -> bytes:
    return ("<?xml version='1.0' encoding=\"UTF-8\" ?>\n<wfs:FeatureCollection "
            'xmlns:ms="http://mapserver.gis.umn.edu/mapserver" xmlns:gml="http://www.opengis.net/gml" '
            'xmlns:wfs="http://www.opengis.net/wfs" xmlns:ogc="http://www.opengis.net/ogc">'
            + "".join(features) + "\n</wfs:FeatureCollection>").encode()


def _part(corner, x0, x1):
    """A footprint over the columns x0..x1 (metres from the sheet's left edge) of a sheet."""
    x, y = corner
    return [(x + x0, y), (x + x1, y), (x + x1, y + 1200), (x + x0, y + 1200)]


# The made-up tile: 22d35 the RT survey of 2012 on its right 30 %, MATTM's of 2010 on all of it (both read); 22d36
# RT 2012 on all of it, MATTM 2010 too (not read); 22d43 lot 006 of 2008 at 1 m on its left half, at 2 m on all of it
# (both, 1 m first); 22d44 the survey of 2016 without its sheet's box on its left 40 %, MATTM 2010 on all of it
FEATURES = [_feature("22d35", "005", 2012, S35, _part(S35, 1120, 1600)), _feature("22d35", "007", 2010, S35),
            _feature("22d36", "005", 2012, S36), _feature("22d36", "007", 2010, S36),
            _feature("22d43", "006", 2008, S43, _part(S43, 0, 800)), _feature("22d43", "006", 2008, S43, res=2),
            _feature("22d44", "017", 2016, S44, _part(S44, 0, 640), zero=True), _feature("22d44", "007", 2010, S44)]


def _serve_index(server, body: bytes, status: int = 200, kind: str = "text/xml; subtype=gml/3.1.1; charset=UTF-8"):
    asked = []

    def answer(request):
        query = dict(request.query)
        if query.get("SERVICE") != "WFS":
            return None
        asked.append(query)
        return Answer(status, body, {"Content-Type": kind})
    server.route(WMS, answer)
    return asked


def _gfi_html(server, entries, owner="RT") -> bytes:
    """A GetFeatureInfo's HTML as the cartoteca's: the owner, the links to the DSM and the DTM of one survey."""
    links = "".join(f"[<a href={server.url(DL)}{kind}/{name}_{HASH}.zip>{kind.upper()}</a>]\n"
                    for kind, name in entries)
    return (f"<html><body><table><tr><td><font size=\"-1\" face=\"Arial\">Proprieta':<b>{owner}</b> </font></td></tr>"
            f"<tr><td>Scarica il dataset {links}[Su questo foglio nuvola di punti non disponibile]</td></tr>"
            "</table></body></html>").encode()


def _asc(values: np.ndarray, left: float, bottom: float, res: float = 1.0) -> bytes:
    """An ASCII grid as the cartoteca's: no CRS, xllcenter on .5 (edges on whole metres), millimetres, CRLF."""
    rows, cols = values.shape
    head = (f"ncols {cols}\r\nnrows {rows}\r\nxllcenter {left + res / 2:.3f}\r\nyllcenter {bottom + res / 2:.3f}\r\n"
            f"cellsize {res:g}\r\nNODATA_value -9999.000\r\n")
    body = "".join(" " + " ".join("-9999.000" if np.isnan(v) else f"{v:.3f}" for v in row) + "\r\n" for row in values)
    return (head + body).encode()


def _zip(name: str, values, left, bottom, pdf=RT_PDF, res=1.0) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(f"{name}.asc", _asc(values, left, bottom, res))
        if pdf is not None:
            archive.writestr("licenza_dati_Lidar.pdf", pdf)
    return out.getvalue()


def _layer(server, kind="dtm", folder=None) -> CartotecaTiles:
    layer = CartotecaTiles(f"{kind} test", server.url(WMS) + "?map=wmscartoteca", italy.TOS_TYPE, kind,
                           "tos-test", folder or f"test_it/tos-{kind}", "test_it/sheet-index/tos-test-urls",
                           italy.TOS_CREDITS, italy.TOS_LABELS)
    layer.reader.base = server.url(DL)
    return layer


def _on_server(monkeypatch, server, layer):
    """The catalogue's own layer asking the local server (its index, GetFeatureInfo and download folder)."""
    monkeypatch.setattr(layer.index.listing, "url", server.url(WMS) + "?map=wmscartoteca")
    monkeypatch.setattr(layer.reader, "wms_url", server.url(WMS) + "?map=wmscartoteca")
    monkeypatch.setattr(layer.reader, "base", server.url(DL))
    monkeypatch.setattr(layer.index, "_listed", {})  # no tiles listed by another test's server
    return layer


# The listing

def test_listing_keeps_the_surveys_that_add_data(http_server, tmp_path):
    """One GetFeature per 0.25° tile (WFS 1.1.0, the box in EPSG:4326 lat-lon, the footprints in EPSG:3003, only the
    attributes used); per sheet the surveys whose footprints add data to the newer ones, newest first, 1 m before 2 m
    of one year; a survey without its sheet's box takes another survey's."""
    asked = _serve_index(http_server, _gml(FEATURES))
    listing = idx.CartotecaSheets(http_server.url(WMS) + "?map=wmscartoteca", italy.TOS_TYPE)
    listing.use(None, str(tmp_path))
    sheets = listing.fetch(LAT, LON)["sheets"]
    assert [(s["godlo"], s["lot"], s["year"], s["res"]) for s in sheets] == [
        ("22d44", "017", 2016, 1.0), ("22d36", "005", 2012, 1.0), ("22d35", "005", 2012, 1.0),
        ("22d44", "007", 2010, 1.0), ("22d35", "007", 2010, 1.0), ("22d43", "006", 2008, 1.0),
        ("22d43", "006", 2008, 2.0)]
    by = {(s["godlo"], s["lot"], s["res"]): s for s in sheets}
    # The extents: the footprint's box grown by the 20 m buffer, within the file (sheet + buffer)
    assert by[("22d35", "005", 1.0)]["extent"] == [S35[0] + 1100, S35[1] - 20, S35[0] + 1620, S35[1] + 1220]
    assert by[("22d35", "007", 1.0)]["extent"] == [S35[0] - 20, S35[1] - 20, S35[0] + 1620, S35[1] + 1220]
    assert by[("22d44", "017", 1.0)]["extent"] == [S44[0] - 20, S44[1] - 20, S44[0] + 660, S44[1] + 1220]
    assert by[("22d44", "017", 1.0)]["dtm"] == _name("22d44", "dtm", "017", 2016)
    # A point of each survey in its own part of the sheet first (where no other survey lies)
    x, y = by[("22d35", "007", 1.0)]["points"][0]
    assert S35[0] + 2 <= x <= S35[0] + 1118 and S35[1] + 2 <= y <= S35[1] + 1198
    x, y = by[("22d43", "006", 2.0)]["points"][0]
    assert x >= S43[0] + 802
    assert all(s["crs"] == "EPSG:3003" for s in sheets)
    (query,) = asked
    assert (query["SERVICE"], query["VERSION"], query["REQUEST"], query["TYPENAME"], query["map"]) == (
        "WFS", "1.1.0", "GetFeature", "rt_cartoteca.lidar2k", "wmscartoteca")
    assert query["SRSNAME"] == "EPSG:3003" and query["MAXFEATURES"] == str(idx.FEATURES_MAX)
    assert query["BBOX"] == "44.0,10.0,44.25,10.25,urn:ogc:def:crs:EPSG::4326"
    assert query["PROPERTYNAME"] == idx.PROPERTIES
    assert {r.user_agent for r in http_server.log} == {cache.http_headers()["User-Agent"]}


def test_listing_drops_a_sliver_and_a_covered_sheet():
    """select_versions: an older survey adding less than MIN_ADDED of its sheet is not read, nor one under newer
    surveys that cover SHEET_COVERED of it; an entry without a footprint (or an empty one) covers the sheet."""
    from shapely.geometry import Polygon, box
    x, y = S35
    rect = (x, y, x + 1600, y + 1200)

    def entry(lot, year, shape):
        return {"year": year, "lot": lot, "res": 1.0, "godlo": "22d35", "dtm": _name("22d35", "dtm", lot, year),
                "dsm": "", "rectangle": rect, "footprint": shape}
    whole = box(*rect)
    sliver = box(x, y, x + 10, y + 1200)  # 0.6 % of the sheet
    kept = idx.select_versions([entry("005", 2012, box(x + 10, y, x + 1600, y + 1200)), entry("007", 2010, whole),
                                entry("006", 2008, sliver)])
    assert [e["lot"] for e in kept] == ["005"]
    kept = idx.select_versions([entry("005", 2012, None), entry("007", 2010, whole)])
    assert [e["lot"] for e in kept] == ["005"]
    kept = idx.select_versions([entry("005", 2012, Polygon()), entry("007", 2010, whole)])
    assert [e["lot"] for e in kept] == ["005"]


@pytest.mark.parametrize("body, status, kind", [
    (b"<?xml version='1.0' encoding=\"UTF-8\" standalone=\"no\" ?>\n<ServiceExceptionReport version=\"1.2.0\">"
     b"<ServiceException code=\"InvalidParameterValue\">msWFSGetFeature(): unknown type</ServiceException>"
     b"</ServiceExceptionReport>", 200, "text/xml"),
    (b"<html>manutenzione</html>", 200, "text/html"),
    (_gml(FEATURES), 200, "text/xml"),  # with FEATURES_MAX set to its count: a cut listing
], ids=["exception", "html", "cut"])
def test_listing_errors_cache_nothing(http_server, tmp_path, monkeypatch, body, status, kind):
    """An exception report (with HTTP 200), an answer that is no FeatureCollection and one of the most features
    asked are IndexUnavailable; nothing is cached, the cached files are used."""
    monkeypatch.setattr(idx, "FEATURES_MAX", len(FEATURES))
    _serve_index(http_server, body, status, kind)
    layer = _layer(http_server)
    with pytest.raises(IndexUnavailable):
        layer.index.listing.fetch(LAT, LON)
    cache_dir = str(tmp_path / "cache")
    layer._use(cache_dir)
    grid = make_grid((S35[0], S35[1], S35[0] + 100, S35[1] + 100), 1.0, "EPSG:3003")
    assert layer.tiles(grid) is None
    assert not os.path.exists(layer.index_path(cache_dir, LAT, LON))


def test_listing_http_error_and_size_cap(http_server, tmp_path, monkeypatch):
    """An HTTP error is a RequestException; an answer of more than ANSWER_BYTES is IndexUnavailable, read no
    further."""
    _serve_index(http_server, b"busy", 503, "text/plain")
    listing = idx.CartotecaSheets(http_server.url(WMS) + "?map=wmscartoteca", italy.TOS_TYPE)
    with pytest.raises(requests.RequestException):
        listing.fetch(LAT, LON)
    http_server.routes.clear()
    _serve_index(http_server, _gml(FEATURES))
    monkeypatch.setattr(idx, "ANSWER_BYTES", 1000)
    with pytest.raises(IndexUnavailable, match="more than 1000 bytes"):
        listing.fetch(LAT, LON)


def test_an_empty_tile(http_server, tmp_path):
    """A tile without sheets (outside the lidar) lists nothing, cached."""
    _serve_index(http_server, _gml([]))
    listing = idx.CartotecaSheets(http_server.url(WMS) + "?map=wmscartoteca", italy.TOS_TYPE)
    assert listing.fetch(LAT, LON) == {"sheets": []}


# The files

def _serve_files(server, entries, owner="RT", pdf=None, gfi_counter=None):
    """GetFeatureInfo answers naming the survey whose own part holds the point (by x: the made-up 22d35's RT 2012
    survey right of x0 + 1120), and the ZIPs of the surveys' files (values = the year, a NaN column)."""
    zips = {}
    for sheet, lot, year, corner, cols in entries:
        x, y = corner
        values = np.full((1240, 1640), float(year), np.float32)
        values[:, :20 + cols[0]] = np.nan  # no data outside the survey's footprint (the file's 20 m buffer first)
        values[:, 20 + cols[1]:] = np.nan
        for kind in ("dtm", "dsm"):
            name = _name(sheet, kind, lot, year)
            zips[name] = _zip(name, values + (0.5 if kind == "dsm" else 0.0), x - 20, y - 20, pdf or (
                MATTM_PDF if lot == "007" else RT_PDF))
            server.add(f"{DL}{kind}/{name}_{HASH}.zip", zips[name], "application/zip")

    def gfi(request):
        query = dict(request.query)
        if query.get("REQUEST") != "GetFeatureInfo":
            return None
        if gfi_counter is not None:
            gfi_counter.append(query)
        left, bottom, right, top = map(float, query["BBOX"].split(","))
        px, py = (left + right) / 2, (bottom + top) / 2
        for sheet, lot, year, corner, cols in entries:
            x, y = corner
            if x + cols[0] <= px <= x + cols[1] and y <= py <= y + 1200:
                return Answer(200, _gfi_html(server, [("dsm", _name(sheet, "dsm", lot, year)),
                                                      ("dtm", _name(sheet, "dtm", lot, year))], owner),
                              {"Content-Type": "text/html; charset=UTF-8"})
        return Answer(200, b"<html><body>nessun dato</body></html>", {"Content-Type": "text/html; charset=UTF-8"})
    server.route(WMS, gfi)
    return zips


FILES = [("22d35", "005", 2012, S35, (1120, 1600)), ("22d35", "007", 2010, S35, (0, 1120))]


def test_files_by_their_getfeatureinfo(http_server, tmp_path, no_sleep):
    """A grid over 22d35: both surveys downloaded, each URL from a GetFeatureInfo at its own part (one per survey:
    the DSM's URL comes with the DTM's), written on whole-metre edges in EPSG:3003 with their owners; the mosaic
    takes the newer survey where it has data and the older one elsewhere; no Range header is sent."""
    gfis = []
    _serve_index(http_server, _gml(FEATURES[:2]))
    _serve_files(http_server, FILES, gfi_counter=gfis)
    cache_dir = str(tmp_path / "cache")
    grid = make_grid((S35[0] + 1000, S35[1] + 100, S35[0] + 1300, S35[1] + 300), 1.0, "EPSG:3003")
    dtm, dsm = _layer(http_server), _layer(http_server, "dsm")
    out = np.load(src.prepare_layer(dtm, grid, cache_dir, str(tmp_path / "t.npy"), "terrain"))
    assert len(gfis) == 2
    np.load(src.prepare_layer(dsm, grid, cache_dir, str(tmp_path / "s.npy"), "surface"))
    assert len(gfis) == 2  # the DSM's URLs were resolved with the DTM's
    files = dtm.files(grid, cache_dir)
    assert [os.path.relpath(p, cache_dir).replace(os.sep, "/") for p in files] == [
        "test_it/tos-dtm/005-2012/22d35_1m.tif", "test_it/tos-dtm/007-2010/22d35_1m.tif"]
    assert [owner_of(p) for p in files] == ["RT", "MATTM"]
    with rio.open(files[0]) as tile:
        assert tile.crs.to_epsg() == 3003 and tile.transform.c == S35[0] - 20 and tile.transform.f == S35[1] + 1220
        assert tile.tags()[rd.OWNER_TAG] == "RT"
    # Newest first, the older survey where the newer has no data (left of x0 + 1120: the grid's first 120 columns)
    assert (out[:, :120] == 2010.0).all() and (out[:, 120:] == 2012.0).all()
    urls = json.load(open(dtm.index.versions.urls_path(cache_dir, dtm.tiles(grid)[0]), encoding="utf-8"))
    assert urls["dtm"].endswith(f"/dtm/{_name('22d35', 'dtm', '005', 2012)}_{HASH}.zip") and urls["owner"] == "RT"
    assert not any("range" in r.headers for r in http_server.log)
    assert not http_server.stray()


def test_a_moved_file_is_asked_again(http_server, tmp_path, no_sleep):
    """A cached URL that answers 404 asks the GetFeatureInfo again and downloads the new address; a survey no
    GetFeatureInfo names is an error (SheetUnresolved) the layer leaves out of the search, nothing recorded."""
    gfis = []
    _serve_index(http_server, _gml(FEATURES[:2]))
    _serve_files(http_server, FILES, gfi_counter=gfis)
    layer = _layer(http_server)
    cache_dir = str(tmp_path / "cache")
    grid = make_grid((S35[0] + 1200, S35[1] + 100, S35[0] + 1300, S35[1] + 200), 1.0, "EPSG:3003")
    layer._use(cache_dir)
    (sheet,) = [t for t in layer.tiles(grid) if t.lot == "005"]
    urls_path = layer.index.versions.urls_path(cache_dir, sheet)
    os.makedirs(os.path.dirname(urls_path))
    with open(urls_path, "w", encoding="utf-8") as f:
        json.dump({"dtm": http_server.url(DL) + "dtm/old_" + HASH + ".zip", "owner": "RT"}, f)
    request = layer.index.request(sheet)
    path = layer.tile_path(cache_dir, sheet)
    fetched = layer.download_tile(sheet, path)
    assert fetched.received > 0 and os.path.exists(path) and len(gfis) == 1
    assert json.load(open(urls_path, encoding="utf-8"))["dtm"].endswith(f"_{HASH}.zip")
    # Not named by any GetFeatureInfo: an error, not cached as no data
    lost = idx.LidarSheet(2001, "099", 1.0, "22d35", _name("22d35", "dtm", "099", 2001), "", sheet.extent,
                          ((S35[0] + 1500.0, S35[1] + 600.0),))
    other = layer.index.versions.request(lost)
    assert other.urls != request.urls
    lost_path = layer.tile_path(cache_dir, lost)
    with pytest.raises(rd.SheetUnresolved):
        layer.download_tile(lost, lost_path)
    assert layer._download_and_record(lost, cache_dir) == 0
    assert not os.path.exists(lost_path) and cache.states(cache_dir, [lost_path]) != ["missing"]
    # A cached URL that answers 404 and a GetFeatureInfo that then names nothing: also an error
    os.makedirs(os.path.dirname(other.urls), exist_ok=True)
    with open(other.urls, "w", encoding="utf-8") as f:
        json.dump({"dtm": http_server.url(DL) + "dtm/old_" + HASH + ".zip"}, f)
    with pytest.raises(rd.SheetUnresolved):
        layer.download_tile(lost, lost_path)


def test_cache_update_reads_a_new_survey_of_a_cached_sheet(http_server, tmp_path, no_sleep):
    """update_index_tile (cache update): a survey listed anew for a sheet with a cached file is downloaded, the
    cached one kept (no pruning); a sheet without a cached file is not downloaded."""
    _serve_index(http_server, _gml([FEATURES[0]]))  # 22d35: only Regione Toscana's survey of 2012 listed at first
    _serve_files(http_server, FILES)
    layer = _layer(http_server)
    cache_dir = str(tmp_path / "cache")
    grid = make_grid((S35[0] + 1200, S35[1] + 100, S35[0] + 1300, S35[1] + 200), 1.0, "EPSG:3003")
    src.prepare_layer(layer, grid, cache_dir, str(tmp_path / "t.npy"), "terrain")
    assert [os.path.basename(os.path.dirname(p)) for p in layer.files(grid, cache_dir)] == ["005-2012"]
    http_server.routes.clear()
    _serve_index(http_server, _gml(FEATURES[:4]))  # now MATTM's survey of 22d35 and both surveys of 22d36 too
    _serve_files(http_server, FILES)
    assert layer.update_index_tile(cache_dir, LAT, LON)[0] == 1
    cached = sorted(os.path.relpath(p, cache_dir).replace(os.sep, "/")
                    for p in glob.glob(os.path.join(cache_dir, "test_it", "tos-dtm", "*", "*.tif")))
    assert cached == ["test_it/tos-dtm/005-2012/22d35_1m.tif", "test_it/tos-dtm/007-2010/22d35_1m.tif"]


def test_links_elsewhere_and_a_wrong_survey_are_not_taken(http_server, tmp_path):
    """A GetFeatureInfo naming another survey at the first point, or linking outside the download folder, is passed
    over: the next point names the survey."""
    layer = _layer(http_server)
    name = _name("22d35", "dtm", "007", 2010)
    answers = iter([
        _gfi_html(http_server, [("dtm", _name("22d35", "dtm", "005", 2012))]),
        f"<a href=https://example.org{DL}dtm/{name}_{HASH}.zip>DTM</a>".encode(),
        _gfi_html(http_server, [("dtm", name)], owner="MATTM")])
    http_server.route(WMS, lambda request: Answer(200, next(answers), {"Content-Type": "text/html"}))
    sheet = idx.LidarSheet(2010, "007", 1.0, "22d35", name, "", (0, 0, 1, 1), ((1.0, 1.0), (2.0, 2.0), (3.0, 3.0)))
    request = idx.CartotecaRequest(sheet, name, str(tmp_path / "urls.json"))
    urls = layer.reader.resolve(request)
    assert urls["dtm"] == f"{http_server.url(DL)}dtm/{name}_{HASH}.zip" and urls["owner"] == "MATTM"
    assert len(http_server.requests(WMS)) == 3


def test_the_owner_comes_from_the_files_licence(http_server, tmp_path):
    """The ZIP's licence decides the owner (a co-owned MATTM sheet the GetFeatureInfo calls RT is MATTM's); without
    a licence in the ZIP the GetFeatureInfo's owner, without either MATTM (the stricter licence); a ZIP cut short
    or too large is an error."""
    reader = _layer(http_server).reader
    sheet = idx.LidarSheet(2008, "006", 1.0, "16e05", "16e05_1x1_dtm_006_2008_3003", "", (0, 0, 1, 1))
    request = idx.CartotecaRequest(sheet, sheet.dtm, "")
    values = np.arange(12, dtype=np.float32).reshape(3, 4)
    band, transform, owner = reader.read(_zip("a", values, 1604000, 4827600, MATTM_PDF), request, "t", "RT")
    assert owner == "MATTM" and (transform.c, transform.f) == (1604000, 4827603)
    assert np.allclose(band, values)
    assert reader.read(_zip("a", values, 0, 0, None), request, "t", "RT")[2] == "RT"
    assert reader.read(_zip("a", values, 0, 0, b"%PDF"), request, "t", None)[2] == "MATTM"
    whole = _zip("a", values, 0, 0)
    with pytest.raises(RuntimeError, match="not a ZIP"):
        reader.read(whole[:len(whole) // 2], request, "t", "RT")
    reader.max_bytes = 100
    with pytest.raises(RuntimeError, match="more than 100"):
        reader.read(whole, request, "t", "RT")


def test_a_cut_download_writes_nothing(http_server, tmp_path, no_sleep):
    """A ZIP cut short (its end missing) raises and leaves no tile; the next search asks again."""
    _serve_index(http_server, _gml(FEATURES[:2]))
    zips = _serve_files(http_server, FILES)
    name = _name("22d35", "dtm", "005", 2012)
    http_server.add(f"{DL}dtm/{name}_{HASH}.zip", zips[name][:len(zips[name]) // 2], "application/zip")
    layer = _layer(http_server)
    cache_dir = str(tmp_path / "cache")
    grid = make_grid((S35[0] + 1200, S35[1] + 100, S35[0] + 1300, S35[1] + 200), 1.0, "EPSG:3003")
    layer._use(cache_dir)
    sheet = next(t for t in layer.tiles(grid) if t.lot == "005")
    with pytest.raises(RuntimeError):
        layer.download_tile(sheet, layer.tile_path(cache_dir, sheet))
    assert not os.path.exists(layer.tile_path(cache_dir, sheet))


# The credits

def _tile(path: str, corner, owner: str, value: float):
    x, y = corner
    os.makedirs(os.path.dirname(path), exist_ok=True)
    src.layer._write_tile(path, np.full((1240, 1640), value, np.float32), "EPSG:3003",
                          rio.transform.from_origin(x - 20, y + 1220, 1.0, 1.0), tags={rd.OWNER_TAG: owner})


@pytest.mark.parametrize("owners, credited", [
    (("RT",), ["CC BY 4.0"]), (("MATTM",), ["CC BY-SA 3.0 IT"]), (("RT", "MATTM"), ["CC BY 4.0", "CC BY-SA 3.0 IT"])])
def test_a_run_is_credited_by_the_owners_of_its_sheets(http_server, tmp_path, monkeypatch, owners, credited):
    """The catalogue's layer: a run that used only Regione Toscana's sheets credits it under CC BY 4.0 (no MATTM,
    no share-alike), one with only the Ministry's sheets the Ministry under CC BY-SA 3.0 IT, one with both both;
    through the record of the data used (prepare_layer, search._merged_data over two tiles, search._credits)."""
    import search
    layer = _on_server(monkeypatch, http_server, src.SOURCES["tuscany"].nmt)
    cache_dir = str(tmp_path / "cache")
    corners = {"RT": S35, "MATTM": S36}
    features = {"RT": _feature("22d35", "005", 2012, S35), "MATTM": _feature("22d36", "007", 2010, S36)}
    _serve_index(http_server, _gml([features[o] for o in owners]))
    for owner in owners:
        lot, year, sheet = ("005", 2012, "22d35") if owner == "RT" else ("007", 2010, "22d36")
        _tile(os.path.join(cache_dir, "italy", "tos-dtm", f"{lot}-{year}", f"{sheet}_1m.tif"), corners[owner], owner,
              100.0)
    halves = [make_grid((S35[0] + 1500, S35[1] + 500, S35[0] + 1600, S35[1] + 600), 1.0, "EPSG:3003"),
              make_grid((S36[0], S36[1] + 500, S36[0] + 100, S36[1] + 600), 1.0, "EPSG:3003")]
    layer._use(cache_dir)
    src.mosaic.used_data.clear()
    try:
        for k, grid in enumerate(halves):  # two tiles of one run, each prepared on its own
            src.prepare_layer(layer, grid, cache_dir, str(tmp_path / f"t{k}.npy"), "terrain", download=False)

        class _Plan:
            area = None
        merged = search._merged_data()
        credits = search._credits(_Plan(), search._dated_data(merged, 2026))
    finally:
        src.mosaic.used_data.clear()
    assert [c["licence"] for c in credits] == credited
    by_licence = {c["licence"]: c for c in credits}
    if "RT" in owners:
        assert by_licence["CC BY 4.0"]["attribution"] == "Fonte dei dati: Regione Toscana – “Rilievi LIDAR”"
    if "MATTM" in owners:
        mattm = by_licence["CC BY-SA 3.0 IT"]
        assert mattm["attribution"] == ("Fonte dei dati: Ministero dell’Ambiente e della tutela del Territorio e del "
                                        "Mare – “Rilievi Lidar”")
        assert mattm["url"] == "https://creativecommons.org/licenses/by-sa/3.0/it/" and "Share-alike" in mattm["notice"]
    used = [e for e in merged if e.get("credit")]
    assert sorted(e["layer"] for e in used) == sorted(f"{layer.description}, {italy.TOS_LABELS[o]}" for o in owners)
    assert all(e["files"] == 1 for e in used) and all(e["files"] == 0 for e in merged if not e.get("credit"))


def test_a_filler_that_filled_nothing_drops_every_owners_entry(tmp_path, monkeypatch):
    """filling.fill_gaps leaves out all the entries of a layer that filled no pixel, one per owner as one."""
    entries = [{"layer": "a, RT", "credit": {"data": "rt"}}, {"layer": "a, MATTM", "credit": {"data": "m"}}]

    class _Layer(src.FileLayer):
        def used_entries(self, grid, cache_dir, wrote=None):
            return [dict(e) for e in entries]
    grid = make_grid((S35[0], S35[1], S35[0] + 50, S35[1] + 50), 1.0, "EPSG:3003")
    path = str(tmp_path / "f.tif")
    _tile(path, S35, "RT", np.nan)  # all no data: fills nothing
    filler = src.Source(id="f_test", name="f", description="f", nmt=_Layer("f", path), fallback=None)
    terrain = np.full((grid.height, grid.width), 5.0, np.float32)
    terrain[10:20, 10:20] = np.nan
    np.save(str(tmp_path / "nmt.npy"), terrain)
    src.mosaic.used_data[:] = [{"layer": "before"}]
    try:
        _, filled, _ = src.fill_gaps(str(tmp_path / "nmt.npy"), None, grid, filler, str(tmp_path / "cache"),
                                     str(tmp_path / "gap.npy"))
        assert filled == 0 and src.mosaic.used_data == [{"layer": "before"}]
    finally:
        src.mosaic.used_data.clear()


def test_a_sole_strip_and_a_newer_strip_are_kept():
    """select_versions keeps the newest (or a sole) survey however small: a sole strip of 0.94 % of the sheet, and
    a newer strip over an older survey of the whole sheet (then the older one too)."""
    from shapely.geometry import box
    x, y = S35
    rect = (x, y, x + 1600, y + 1200)

    def entry(lot, year, shape):
        return {"year": year, "lot": lot, "res": 1.0, "godlo": "22d35", "dtm": _name("22d35", "dtm", lot, year),
                "dsm": "", "rectangle": rect, "footprint": shape}
    strip = box(x, y, x + 15, y + 1200)  # 18 000 m²: 0.94 %
    (kept,) = idx.select_versions([entry("017", 2016, strip)])
    assert kept["lot"] == "017" and kept["extent"] == [x - 20, y - 20, x + 35, y + 1220]
    px, py = kept["points"][0]
    assert x <= px <= x + 15 and y <= py <= y + 1200
    kept = idx.select_versions([entry("017", 2016, strip), entry("007", 2010, box(*rect))])
    assert [e["lot"] for e in kept] == ["017", "007"]
    # A strip too narrow for a point inside its edge still gets one (on it)
    (kept,) = idx.select_versions([entry("017", 2016, box(x, y, x + 3, y + 1200))])
    assert x <= kept["points"][0][0] <= x + 3


def _sheet_tile(cache_dir, folder, lot, year, sheet, corner, owner, cols=None):
    """A cached tile of a survey of a sheet (the file and its 20 m buffer), its values 100 within the columns cols
    of the sheet (metres from its left edge; None: everywhere), no data elsewhere."""
    x, y = corner
    values = np.full((1240, 1640), 100.0 if owner == "RT" else 200.0, np.float32)
    if cols is not None:
        values[:, :20 + cols[0]] = np.nan
        values[:, 20 + cols[1]:] = np.nan
    path = os.path.join(cache_dir, *folder.split("/"), f"{lot}-{year}", f"{sheet}_1m.tif")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    src.layer._write_tile(path, values, "EPSG:3003", rio.transform.from_origin(x - 20, y + 1220, 1.0, 1.0),
                          tags={rd.OWNER_TAG: owner})
    return path


@pytest.mark.parametrize("box_m, owners", [
    ((1200, 100, 1300, 200), ["RT"]),           # wholly in the RT part of 22d35 (MATTM's survey under it)
    ((100, 100, 200, 200), ["MATTM"]),          # in MATTM's part only
    ((1050, 100, 1250, 200), ["RT", "MATTM"]),  # across both
    ((1610, 100, 1650, 200), ["RT"]),           # in 22d36 (RT, whole), touching 22d35's MATTM buffer only
], ids=["rt-part", "mattm-part", "both", "buffer"])
def test_credits_follow_the_pixels_given(http_server, tmp_path, monkeypatch, box_m, owners):
    """An owner is credited only when its files gave the mosaic a pixel: a Ministry's survey under a newer one, or
    whose 20 m buffer alone meets the grid, brings no CC BY-SA (the catalogue's layer, prepare_layer)."""
    layer = _on_server(monkeypatch, http_server, src.SOURCES["tuscany"].nmt)
    cache_dir = str(tmp_path / "cache")
    _serve_index(http_server, _gml([_feature("22d35", "005", 2012, S35, _part(S35, 1120, 1600)),
                                    _feature("22d35", "007", 2010, S35), _feature("22d36", "005", 2012, S36)]))
    _sheet_tile(cache_dir, layer.folder, "005", 2012, "22d35", S35, "RT", (1120, 1600))
    _sheet_tile(cache_dir, layer.folder, "007", 2010, "22d35", S35, "MATTM")
    _sheet_tile(cache_dir, layer.folder, "005", 2012, "22d36", S36, "RT")
    x, y = S35
    grid = make_grid((x + box_m[0], y + box_m[1], x + box_m[2], y + box_m[3]), 1.0, "EPSG:3003")
    layer._use(cache_dir)
    src.mosaic.used_data.clear()
    try:
        out = np.load(src.prepare_layer(layer, grid, cache_dir, str(tmp_path / "t.npy"), "terrain", download=False))
        entries = list(src.mosaic.used_data)
    finally:
        src.mosaic.used_data.clear()
    assert np.isfinite(out).all()
    credited = [e["credit"]["licence"] for e in entries if e.get("credit")]
    assert credited == [{"RT": "CC BY 4.0", "MATTM": "CC BY-SA 3.0 IT"}[o] for o in owners]
    assert any(t.lot == "007" for t in layer.tiles(grid))  # the Ministry's file met the grid in every case


def test_the_mosaic_tells_which_files_wrote(tmp_path):
    """build_mosaic(wrote=): whether each file wrote a pixel, the values the same as without it (a file on the grid
    copied, one under another, one reprojected, one in strips)."""
    from sources.mosaic import build_mosaic
    cache_dir = str(tmp_path)
    a = _sheet_tile(cache_dir, "m", "005", 2012, "22d35", S35, "RT", (1120, 1600))
    b = _sheet_tile(cache_dir, "m", "007", 2010, "22d35", S35, "MATTM")
    c = _sheet_tile(cache_dir, "m", "006", 2008, "22d35", S35, "MATTM")  # under both
    x, y = S35
    for res, rows in ((1.0, None), (2.0, None), (2.0, 20)):
        grid = make_grid((x + 1000, y + 100, x + 1300, y + 300), res, "EPSG:3003")
        plain = np.array(build_mosaic([a, b, c], grid, str(tmp_path / "p.npy"), "p", rows=rows))
        wrote = []
        counted = np.array(build_mosaic([a, b, c], grid, str(tmp_path / "c.npy"), "c", rows=rows, wrote=wrote))
        assert np.array_equal(plain, counted, equal_nan=True)
        assert wrote == [True, True, False], (res, rows)


def test_fabdem_is_never_in_tuscanys_chain():
    """The Ministry's sheets are CC BY-SA, FABDEM CC BY-NC-SA: Tuscany's gaps come from TINITALY, then Copernicus."""
    s = src.SOURCES["tuscany"]
    assert s.fallbacks == ["tinitaly", "copernicus"] and not s.neighbours
    credits = [layer.credit for sid in s.fallbacks for layer in (src.SOURCES[sid].nmt, src.SOURCES[sid].nmpt)
               if layer is not None]
    assert src.FABDEM_CREDIT not in credits and credits


def test_dtm_and_dsm_resolve_once_together(http_server, tmp_path, no_sleep):
    """The DTM's and the DSM's downloads of one survey at the same time: one GetFeatureInfo (the survey's lock),
    the URLs' file written once and read by the other, both tiles written."""
    import threading
    import time
    gfis = []
    _serve_index(http_server, _gml(FEATURES[:1]))
    _serve_files(http_server, FILES[:1], gfi_counter=gfis)
    slow = http_server.routes[-1][1]

    def slower(request):
        time.sleep(0.5) if dict(request.query).get("REQUEST") == "GetFeatureInfo" else None
        return slow(request)
    http_server.routes[-1] = (WMS, slower)
    cache_dir = str(tmp_path / "cache")
    grid = make_grid((S35[0] + 1200, S35[1] + 100, S35[0] + 1300, S35[1] + 200), 1.0, "EPSG:3003")
    dtm, dsm = _layer(http_server), _layer(http_server, "dsm")
    jobs = []
    for layer in (dtm, dsm):
        layer._use(cache_dir)
        (sheet,) = layer.tiles(grid)
        jobs.append(threading.Thread(target=layer.download_tile, args=(sheet, layer.tile_path(cache_dir, sheet))))
    for job in jobs:
        job.start()
    for job in jobs:
        job.join()
    assert len(gfis) == 1
    assert all(os.path.exists(layer.tile_path(cache_dir, layer.tiles(grid)[0])) for layer in (dtm, dsm))


def test_caps_of_the_answers(http_server, tmp_path, monkeypatch, no_sleep):
    """A GetFeatureInfo longer than GFI_BYTES, a ZIP longer than max_bytes and a member longer than member_bytes are
    errors, read no further than their cap; nothing written."""
    _serve_index(http_server, _gml(FEATURES[:1]))
    _serve_files(http_server, FILES[:1])
    layer = _layer(http_server)
    cache_dir = str(tmp_path / "cache")
    grid = make_grid((S35[0] + 1200, S35[1] + 100, S35[0] + 1300, S35[1] + 200), 1.0, "EPSG:3003")
    layer._use(cache_dir)
    (sheet,) = layer.tiles(grid)
    path = layer.tile_path(cache_dir, sheet)
    monkeypatch.setattr(rd, "GFI_BYTES", 100)
    with pytest.raises(RuntimeError, match="more than 100 bytes"):
        layer.download_tile(sheet, path)
    monkeypatch.setattr(rd, "GFI_BYTES", 2_000_000)
    layer.reader.max_bytes = 1000
    with pytest.raises(RuntimeError, match="more than 1000 bytes"):
        layer.download_tile(sheet, path)
    layer.reader.max_bytes = 60_000_000
    layer.reader.member_bytes = 1000
    with pytest.raises(RuntimeError, match="more than 1000"):
        layer.download_tile(sheet, path)
    assert not os.path.exists(path)


def test_fill_gaps_rows_drops_every_owners_entry(tmp_path):
    """filling._fill_gaps_rows (fill_gaps in strips) leaves out all the entries of a filler that filled no pixel."""
    entries = [{"layer": "a, RT", "credit": {"data": "rt"}}, {"layer": "a, MATTM", "credit": {"data": "m"}}]

    class _Layer(src.FileLayer):
        def used_entries(self, grid, cache_dir, wrote=None):
            return [dict(e) for e in entries]
    grid = make_grid((S35[0], S35[1], S35[0] + 50, S35[1] + 50), 1.0, "EPSG:3003")
    path = str(tmp_path / "f.tif")
    _tile(path, S35, "RT", np.nan)
    filler = src.Source(id="f_test", name="f", description="f", nmt=_Layer("f", path), fallback=None)
    terrain = np.full((grid.height, grid.width), 5.0, np.float32)
    terrain[10:20, 10:20] = np.nan
    np.save(str(tmp_path / "nmt.npy"), terrain)
    src.mosaic.used_data[:] = [{"layer": "before"}]
    try:
        _, filled, _ = src.fill_gaps(str(tmp_path / "nmt.npy"), None, grid, filler, str(tmp_path / "cache"),
                                     str(tmp_path / "gap.npy"), rows=16)
        assert filled == 0 and src.mosaic.used_data == [{"layer": "before"}]
    finally:
        src.mosaic.used_data.clear()


def test_query_under_an_outline(http_server, tmp_path):
    """CartotecaVersions.query with an outline (area_shape): a grid inside it gets its surveys, one across its edge
    those under it only, one wholly outside none."""
    import dataclasses
    from shapely.geometry import box
    _serve_index(http_server, _gml(FEATURES[:4]))
    layer = _layer(http_server)
    cache_dir = str(tmp_path / "cache")
    layer._use(cache_dir)
    x, y = S35
    outline = box(x + 1300, y, x + 1700, y + 1200)  # the right part of 22d35, the left edge of 22d36
    grid = make_grid((x + 1000, y + 100, x + 2000, y + 300), 1.0, "EPSG:3003")

    def listed(g):
        return sorted((t.godlo, t.lot) for t in layer.index.versions.query(layer.index, g, cache_dir, None))
    inside = dataclasses.replace(make_grid((x + 1400, y + 100, x + 1500, y + 300), 1.0, "EPSG:3003"),
                                 area_shape=outline)
    assert listed(inside) == [("22d35", "005"), ("22d35", "007")]
    assert listed(dataclasses.replace(grid, area_shape=outline)) == [("22d35", "005"), ("22d35", "007"),
                                                                    ("22d36", "005")]
    assert listed(dataclasses.replace(grid, area_shape=box(x + 1000, y, x + 1090, y + 1200))) == [("22d35", "007")]
    outside = dataclasses.replace(make_grid((x + 3500, y + 100, x + 3600, y + 300), 1.0, "EPSG:3003"),
                                  area_shape=outline)
    assert listed(outside) == []


def test_cached_files_without_the_index(http_server, tmp_path, no_sleep):
    """Without the index (503), the cached surveys over the grid are used, best first, and credited by their tags;
    a tile without the tag is the Ministry's (the stricter licence)."""
    _serve_index(http_server, b"busy", 503, "text/plain")
    layer = _layer(http_server)
    cache_dir = str(tmp_path / "cache")
    a = _sheet_tile(cache_dir, layer.folder, "005", 2012, "22d35", S35, "RT", (1120, 1600))
    b = _sheet_tile(cache_dir, layer.folder, "007", 2010, "22d35", S35, "MATTM")
    _sheet_tile(cache_dir, layer.folder, "005", 2012, "22d38", (S35[0] + 4800, S35[1]), "RT")  # far away
    grid = make_grid((S35[0] + 1050, S35[1] + 100, S35[0] + 1250, S35[1] + 200), 1.0, "EPSG:3003")
    layer._use(cache_dir)
    assert [os.path.normpath(p) for p in layer.files(grid, cache_dir)] == [os.path.normpath(a), os.path.normpath(b)]
    entries = layer.used_entries(grid, cache_dir)
    assert [e["credit"]["licence"] for e in entries] == ["CC BY 4.0", "CC BY-SA 3.0 IT"]
    with rio.open(b, "r+") as tile:
        tile.update_tags(**{rd.OWNER_TAG: ""})
    assert owner_of(b) == "MATTM"
    untagged = str(tmp_path / "plain.tif")
    src.layer._write_tile(untagged, np.ones((2, 2), np.float32), "EPSG:3003",
                          rio.transform.from_origin(0, 2, 1, 1))
    assert owner_of(untagged) == "MATTM"


def test_probe_cartoteca_head(http_server, tmp_path, no_sleep):
    """The probe's read of a cartoteca layer: the first tile's URL by a GetFeatureInfo, then the first KB of its ZIP
    (no Range header); a survey no GetFeatureInfo names fails."""
    from sources import probe
    _serve_index(http_server, _gml(FEATURES[:1]))
    _serve_files(http_server, FILES[:1])
    layer = _layer(http_server)
    cache_dir = str(tmp_path / "cache")
    grid = make_grid((S35[0] + 1200, S35[1] + 100, S35[0] + 1300, S35[1] + 200), 1.0, "EPSG:3003")
    layer._use(cache_dir)
    (sheet,) = layer.tiles(grid)
    assert probe._cartoteca_head(cache_dir, layer, sheet) == f"{_name('22d35', 'dtm', '005', 2012)} (RT)"
    assert not any("range" in r.headers for r in http_server.log)
    lost = idx.LidarSheet(2001, "099", 1.0, "22d35", _name("22d35", "dtm", "099", 2001), "", sheet.extent,
                          ((S35[0] + 1500.0, S35[1] + 600.0),))
    with pytest.raises(RuntimeError, match="no GetFeatureInfo names"):
        probe._cartoteca_head(cache_dir, layer, lost)


# The catalogue

def test_catalogue_source():
    s = src.SOURCES["tuscany"]
    assert (s.countries, s.regions, s.crs, s.grid_origin) == (("it",), ("it-52",), "EPSG:3003", (0.0, 0.0))
    assert (s.fallback, s.more_fallbacks, s.neighbours, s.ortho) == ("tinitaly", ("copernicus",), (), None)
    assert s.credits == (italy.TOS_RT_CREDIT, italy.TOS_MATTM_CREDIT) and s.nmt.credit is italy.TOS_MATTM_CREDIT
    ids = list(src.SOURCES)
    assert ids.index("sardinia") < ids.index("tuscany") < ids.index("tinitaly")
    for layer, kind in ((s.nmt, "dtm"), (s.nmpt, "dsm")):
        assert (layer.index_url, layer.typename, layer.kind, layer.prefix, layer.folder, layer.urls_folder) == (
            "https://www502.regione.toscana.it/wmsraster/com.rt.wms.RTmap/wms?map=wmscartoteca",
            "rt_cartoteca.lidar2k", kind, "tos-lidar", f"italy/tos-{kind}", "italy/sheet-index/tos-urls")
        assert layer.index.top == "italy" and layer.reader.base == rd.DOWNLOADS
        assert layer.credits == {"RT": italy.TOS_RT_CREDIT, "MATTM": italy.TOS_MATTM_CREDIT}
    assert net.HOST_SLOTS_OF["www502.regione.toscana.it"] == 2
    assert src.AREA_NAMES["it-52"] == "Toscana"


@pytest.mark.parametrize("lat, lon, expected", [
    (44.085, 10.150, ("it", "it-52")),   # Carrara
    (44.030, 10.320, ("it", "it-52")),   # Pania della Croce
    (42.78, 10.25, ("it", "it-52")),     # Elba
    (42.36, 10.90, ("it", "it-52")),     # Giglio
    (43.05, 9.83, ("it", "it-52")),      # Capraia
    (43.77, 11.25, ("it", "it-52")),     # Florence
    (42.50, 9.45, ("fr", None)),         # Corsica's east coast
    (44.06, 9.85, ("it", None)),         # Liguria: the Muzzerone above Portovenere
    (43.11, 12.39, ("it", None)),        # Perugia (Umbria)
])
def test_offline_boxes(lat, lon, expected):
    """Offline the boxes give Tuscany its islands and keep Corsica, the Muzzerone and Perugia out."""
    country, region = expected
    boxes = [(code, b) for code, b in choose.OFFLINE_BOXES if b[0] <= lat <= b[1] and b[2] <= lon <= b[3]]
    assert boxes, (lat, lon)
    code = boxes[0][0]
    assert code.split("-")[0] == country and (code if "-" in code else None) == region, code
