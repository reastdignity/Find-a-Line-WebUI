"""British Columbia: LidarBC's files found through its ArcGIS FeatureServer index (sources/indexes/arcgis.py), each
entry confirmed by a listing of GeoBC's S3 bucket, read in blocks and composed newest first (sources/layers/
lidarbc.py); the compound CRSs of its 2023+ files (readers.windows._same_crs); the source and its offline boxes.

The FeatureServer follows the ArcGIS REST API's Query (Feature Service/Layer) (https://developers.arcgis.com/rest/
services-reference/enterprise/query-feature-service-layer/): features with attributes and geometry, paged by
resultOffset while exceededTransferLimit, errors as {"error": {...}} also with HTTP 200. Real answers recorded on
2026-11-03: tests/data/recorded/arcgis/lidarbc-dem/ (tests/test_parts.py)."""

import json
import os
import sys
from xml.sax.saxutils import escape

import numpy as np
import pytest
import rasterio as rio
from rasterio.crs import CRS
from rasterio.transform import from_origin
from rasterio.warp import transform_bounds

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import osm  # noqa: E402
import sources as src  # noqa: E402
from grid import Grid  # noqa: E402
from http_server import Answer  # noqa: E402
from sources.indexes import arcgis  # noqa: E402
from sources.indexes.arcgis import query_features  # noqa: E402
from sources.indexes.cached import IndexUnavailable  # noqa: E402
from sources.layers.lidarbc import LidarBcBlocks, bc_utm_crs, file_crs  # noqa: E402
from sources.readers.windows import _same_crs  # noqa: E402

FS = "/rest/services/LiDAR_BC_S3_Public/FeatureServer"
NS = "http://s3.amazonaws.com/doc/2006-03-01/"
BC = src.SOURCES["british_columbia"]


@pytest.fixture(autouse=True)
def no_waiting(monkeypatch):
    monkeypatch.setattr(src.net, "_sleep", lambda attempt: None)


# The compound CRSs of the 2023+ files

def test_same_crs_compound():
    """A compound CRS whose horizontal part is the other CRS is the same (NAD83(CSRS) / UTM 10N and 11N + CGVD2013
    height); another horizontal CRS stays another, also as the file's own WKT."""
    assert _same_crs("EPSG:6654", "EPSG:2955") and _same_crs("EPSG:2955", "EPSG:6654")
    assert _same_crs("EPSG:6653", "EPSG:3157")
    assert not _same_crs("EPSG:6654", "EPSG:3157") and not _same_crs("EPSG:6653", "EPSG:2955")
    assert not _same_crs("EPSG:6654", "EPSG:3005")
    assert not _same_crs("EPSG:6653", "EPSG:6654")


def test_same_crs_of_a_written_compound_file(tmp_path):
    path = str(tmp_path / "c.tif")
    with rio.open(path, "w", driver="GTiff", width=4, height=4, count=1, dtype="float32", crs=CRS.from_epsg(6654),
                  transform=from_origin(316000, 5460000, 1, 1)) as dst:
        dst.write(np.zeros((1, 4, 4), np.float32))
    with rio.open(path) as written:
        assert _same_crs(written.crs, "EPSG:2955")
        assert not _same_crs(written.crs, "EPSG:3157")


# The FeatureServer's query

def _ring(west, south, east, north):
    return {"rings": [[[west, south], [east, south], [east, north], [west, north], [west, south]]]}


def _featureserver(server, layers, page=None, status=200, body=None):
    """A FeatureServer on the local server: layers {n: [features]} answered in pages of page (else as asked), or
    every query answered with body and status."""
    def query(request):
        layer = int(request.path.split("/")[-2])
        q = dict(request.query)
        if body is not None:
            return Answer(status, body, {"Content-Type": "application/json"})
        assert q["f"] == "json" and q["inSR"] == "4326" and q["orderByFields"] == "OBJECTID"
        offset, count = int(q["resultOffset"]), page or int(q["resultRecordCount"])
        features = layers.get(layer, [])
        answer = {"features": features[offset:offset + count]}
        if offset + count < len(features):
            answer["exceededTransferLimit"] = True
        return Answer(200, json.dumps(answer).encode(), {"Content-Type": "application/json"})
    server.route(FS, query)


def test_query_features_pages(http_server):
    features = [{"attributes": {"OBJECTID": k}} for k in range(5)]
    _featureserver(http_server, {6: features}, page=2)
    found = query_features(http_server.url(f"{FS}/6"), (-120.0, 49.0, -119.75, 49.25), ("year",), geometry=False)
    assert found == features
    asked = [dict(r.query) for r in http_server.requests(FS)]
    assert [q["resultOffset"] for q in asked] == ["0", "2", "4"]
    assert asked[0]["geometry"] == "-120.0,49.0,-119.75,49.25" and asked[0]["returnGeometry"] == "false"
    assert "outSR" not in asked[0] and not http_server.stray()


@pytest.mark.parametrize("status, body", [
    (200, b'{"error": {"code": 400, "message": "Invalid query parameters"}}'),  # an error with HTTP 200
    (400, b'{"error": {"code": 400, "message": "Invalid URL"}}'),
    (200, b"<html>Service unavailable</html>"),
    (200, b"[]"),
    (200, b'{"count": 3}'),
    (404, b"not found"),
])
def test_query_features_error_answers(http_server, status, body):
    _featureserver(http_server, {}, status=status, body=body)
    with pytest.raises(IndexUnavailable):
        query_features(http_server.url(f"{FS}/6"), (-120.0, 49.0, -119.75, 49.25), ("year",))
    assert len(http_server.requests(FS)) == 1  # no retry of an answer


def test_query_features_retries_server_errors_and_caps_bytes(http_server, monkeypatch):
    answers = [Answer(503, b"busy"), Answer(200, b'{"features": []}', {"Content-Type": "application/json"})]
    http_server.route(FS, lambda request: answers.pop(0))
    assert query_features(http_server.url(f"{FS}/5"), (0, 0, 1, 1), ("year",)) == []
    assert len(http_server.requests(FS)) == 2
    http_server.routes.clear()
    _featureserver(http_server, {5: [{"attributes": {"OBJECTID": k, "s3Url": "x" * 100}} for k in range(50)]})
    monkeypatch.setattr(arcgis, "QUERY_BYTES_MAX", 1000)
    with pytest.raises(IndexUnavailable, match="more than 1000 bytes"):
        query_features(http_server.url(f"{FS}/5"), (0, 0, 1, 1), ("year",))


def test_query_features_an_endless_listing(http_server, monkeypatch):
    """A service that says more features match but sends none, or never stops: an error, never a shorter list."""
    http_server.route(FS, lambda request: Answer(200, b'{"features": [], "exceededTransferLimit": true}',
                                                 {"Content-Type": "application/json"}))
    with pytest.raises(IndexUnavailable, match="empty page"):
        query_features(http_server.url(f"{FS}/5"), (0, 0, 1, 1), ("year",))
    http_server.routes.clear()
    _featureserver(http_server, {5: [{"attributes": {"OBJECTID": k}} for k in range(10)]}, page=1)
    monkeypatch.setattr(arcgis, "QUERY_PAGES_MAX", 3)
    with pytest.raises(IndexUnavailable, match="more than 3 pages"):
        query_features(http_server.url(f"{FS}/5"), (0, 0, 1, 1), ("year",))


# The listing: the FeatureServer's entries confirmed by the bucket

def _bucket(server, keys, files=None):
    """GeoBC's bucket on the local server at /gdwuts: ListObjectsV2 of keys {key: (etag, LastModified)}, and the
    files {key: bytes}."""
    names = sorted(keys)

    def listing(request):
        if request.path != "/gdwuts/":
            return None
        q = dict(request.query)
        assert q["list-type"] == "2"
        found = [k for k in names if k.startswith(q.get("prefix", ""))]
        body = (f"<?xml version='1.0' encoding='UTF-8'?><ListBucketResult xmlns='{NS}'><Name>gdwuts</Name>"
                f"<Prefix>{escape(q.get('prefix', ''))}</Prefix><KeyCount>{len(found)}</KeyCount>"
                "<IsTruncated>false</IsTruncated>"
                + "".join(f"<Contents><Key>{escape(k)}</Key><LastModified>{keys[k][1]}</LastModified>"
                          f"<ETag>&quot;{keys[k][0]}&quot;</ETag><Size>10</Size></Contents>" for k in found)
                + "</ListBucketResult>")
        return Answer(200, body.encode(), {"Content-Type": "application/xml"})
    server.route("/gdwuts/", listing)
    for key, content in (files or {}).items():
        server.add(f"/gdwuts/{key}", content, "image/tiff")


def _feature(oid, key, maptile, year, projection, box, bucket="gdwuts"):
    return {"attributes": {"OBJECTID": oid, "maptile": maptile, "year": year, "projection": projection,
                           "s3Url": f"https://nrs.objectstore.gov.bc.ca/{bucket}/{key}"},
            "geometry": _ring(*box)}


def _layer(server, kind="dem"):
    layers = (6, 5) if kind == "dem" else (3, 1)
    return LidarBcBlocks(f"LidarBC {kind}", server.url(FS), layers, server.url("/gdwuts"), f"lidarbc-{kind}",
                         f"canada/lidarbc-{kind}")


SHEET_2019 = "082/082e/2019/dem/bc_082e023_xli1m_utm11_2019.tif"
TILE_2024 = "082/082e/2024/dem/bc_082e023_3_2_2_xli1m_utm11_20240721_20240726.tif"
TILE_2017 = "082/082e/2017/dem/bc_082e023_3_2_2_xl1m_17603.tif"
LAZ_2016 = "082/082e/2016/dem/bc_082e023_3_2_2_xyes_8_utm11_20170601.tif"  # listed as .laz only
GONE_2011 = "082/082e/2011/dem/bc_082e023_3_2_4_xli1m_utm11_20240721_20240726.tif"  # a path that does not exist
ALBERS_2016 = "092/092h/2016/dem/bc_092h073441_xl2m_bcalb_20160531_dem.tif"
TILE_BOX = (-119.50, 49.25, -119.475, 49.2625)  # 082e023_3_2_2 (1:2 500: 0.025° x 0.0125°)


def test_listing_items(http_server):
    """The entries of both index layers whose files the bucket lists, with their ETag and LastModified, the CRS
    their name, the index or their place gives, the footprint's box in it with the margin, and the survey folder's
    year; entries the bucket does not list (a LAZ named .tif, a folder that does not exist, another bucket's) drop
    out. One listing per sheet and survey folder."""
    sheet_box = (-119.6, 49.2, -119.4, 49.3)
    _featureserver(http_server, {
        6: [_feature(1, SHEET_2019, "082e023", 2019, "utm11", sheet_box)],
        5: [_feature(2, TILE_2024, "082e023_3_2_2", 2024, "utm11", TILE_BOX),
            _feature(3, TILE_2017, "082e023_3_2_2", 2017, " ", TILE_BOX),
            _feature(4, LAZ_2016, "082e023_3_2_2", 2016, "utm11", TILE_BOX),
            _feature(5, GONE_2011, "082e023_3_2_4", 2011, "utm11", TILE_BOX),
            _feature(6, TILE_2024, "082e023_3_2_2", 2024, "utm11", TILE_BOX, bucket="other"),
            _feature(7, ALBERS_2016, "092h073441", 2016, "bcalb", TILE_BOX)]})
    _bucket(http_server, {SHEET_2019: ("aaaa1111bbbb", "2024-07-09T15:03:56.303Z"),
                          TILE_2024: ("cccc2222dddd", "2026-05-08T01:51:31.269Z"),
                          TILE_2017: ("eeee3333", "2025-01-02T00:00:00.000Z"),
                          LAZ_2016.replace(".tif", ".laz"): ("ffff", "2025-01-02T00:00:00.000Z"),
                          ALBERS_2016: ("abcdef12-3", "2024-01-01T00:00:00.000Z")})
    items = _layer(http_server).index.listing.fetch(49.25, -119.75)["sheets"]
    tile = list(transform_bounds("EPSG:4326", "EPSG:2955", *TILE_BOX, densify_pts=21))
    tile = [int(np.floor(tile[0] - 100)), int(np.floor(tile[1] - 100)), int(np.ceil(tile[2] + 100)),
            int(np.ceil(tile[3] + 100))]
    base = http_server.url("/gdwuts")
    assert [(i["name"], i["url"], i["crs"], i["year"], i["published"]) for i in items] == [
        ("bc_082e023_xli1m_utm11_2019@aaaa1111", f"{base}/{SHEET_2019}", "EPSG:2955", 2019,
         "2024-07-09T15:03:56.303Z"),
        ("bc_082e023_3_2_2_xli1m_utm11_20240721_20240726@cccc2222", f"{base}/{TILE_2024}", "EPSG:2955", 2024,
         "2026-05-08T01:51:31.269Z"),
        ("bc_082e023_3_2_2_xl1m_17603@eeee3333", f"{base}/{TILE_2017}", "EPSG:2955", 2017,
         "2025-01-02T00:00:00.000Z"),
        ("bc_092h073441_xl2m_bcalb_20160531_dem@abcdef12", f"{base}/{ALBERS_2016}", "EPSG:3005", 2016,
         "2024-01-01T00:00:00.000Z")]
    assert items[1]["extent"] == tile == items[2]["extent"]
    asked = sorted(dict(r.query)["prefix"] for r in http_server.requests("/gdwuts/"))
    assert asked == ["082/082e/2011/dem/bc_082e023", "082/082e/2016/dem/bc_082e023", "082/082e/2017/dem/bc_082e023",
                     "082/082e/2019/dem/bc_082e023", "082/082e/2024/dem/bc_082e023",
                     "092/092h/2016/dem/bc_092h073"]
    assert not http_server.stray()


@pytest.mark.parametrize("name, projection, box, crs", [
    ("bc_092g065_xl1m_utm10_2019.tif", "utm10", (-123.2, 49.6, -123.0, 49.7), "EPSG:3157"),
    ("bc_103j001_xl1m_utm08_20170805_dem.tif", "utm08", (-134.0, 59.0, -133.8, 59.1), "EPSG:3155"),
    ("bc_093b036_xli1m_utm10_20240508_20240520.tif", "utm9", (-122.9, 52.3, -122.7, 52.4), "EPSG:3157"),  # the name
    ("bc_103g001_xli1m_2023.tif", "utm9", (-130.0, 54.0, -129.8, 54.1), "EPSG:3156"),  # the index
    ("bc_082e023_1_4_4_xl1m_17603.tif", " ", (-119.5, 49.25, -119.475, 49.2625), "EPSG:2955"),  # the place
    ("bc_092h073441_xl2m_bcalb_20160531_dem.tif", "bcalb", (-121.4, 49.8, -121.38, 49.81), "EPSG:3005"),
])
def test_file_crs(name, projection, box, crs):
    assert file_crs(name, projection, *box) == crs


def test_bc_utm_crs():
    assert bc_utm_crs(49.682, -123.143) == "EPSG:3157"   # Squamish, zone 10
    assert bc_utm_crs(49.2582, -119.5016) == "EPSG:2955"  # McIntyre Bluff, zone 11
    assert bc_utm_crs(54.0, -130.5) == "EPSG:3156"       # Prince Rupert, zone 9
    assert bc_utm_crs(59.5, -136.0) == "EPSG:3155"       # zone 8
    assert bc_utm_crs(49.5, -115.0) == "EPSG:2955"
    assert bc_utm_crs(48.0, 20.0) == "EPSG:32634"         # elsewhere the WGS84 zone


def test_index_unavailable_caches_nothing(http_server, tmp_path, capsys):
    """An error of the FeatureServer, or of the bucket's listing, caches no answer: the cached blocks are used."""
    cache_dir = str(tmp_path / "cache")
    _featureserver(http_server, {}, body=b'{"error": {"code": 500, "message": "Unable to perform query"}}')
    layer = _layer(http_server)
    with pytest.raises(IndexUnavailable):
        layer.index.answers(cache_dir, 49.25, -119.75)
    assert not os.path.exists(layer.index_path(cache_dir, 49.25, -119.75))
    http_server.routes.clear()
    _featureserver(http_server, {5: [_feature(2, TILE_2024, "082e023_3_2_2", 2024, "utm11", TILE_BOX)]})
    http_server.route("/gdwuts/", lambda request: Answer(503, b"<Error><Code>SlowDown</Code></Error>"))
    grid = Grid(left=316500.0, top=5459500.0, res=1.0, height=200, width=200, crs="EPSG:2955")
    layer = _layer(http_server)
    layer._use(cache_dir, None)
    assert layer.tiles(grid) is None
    assert "index not available" in capsys.readouterr().out
    assert not os.path.exists(layer.index_path(cache_dir, 49.25, -119.75))


# A block composed newest first

def _tif(left, top, width, height, values, crs, nodata=-32767.0, strips=False, res=1.0):
    path = os.path.join(_tif.folder, f"{len(os.listdir(_tif.folder))}.tif")
    layout = {"blockysize": 1} if strips else {"tiled": True, "blockxsize": 256, "blockysize": 256}
    with rio.open(path, "w", driver="GTiff", width=width, height=height, count=1, dtype="float32", crs=crs,
                  transform=from_origin(left, top, res, res), nodata=nodata, compress="lzw", **layout) as dst:
        dst.write(values.astype(np.float32), 1)
    with open(path, "rb") as f:
        return f.read()


def test_block_composed_newest_first(http_server, tmp_path):
    """A 1 km block at McIntyre Bluff from a 2024 strip file in EPSG:6654 (its west part) and a 2017 tiled file
    in EPSG:2955 (all of it): each pixel from the newest file with data there; a listed file that answers 404
    adds nothing; the block's key changes with a file's ETag."""
    _tif.folder = str(tmp_path / "files")
    os.makedirs(_tif.folder)
    west = np.full((1200, 1200), -32767.0)
    west[:, :700] = 500.0  # 316 900-317 600 m E (the block starts at 317 000)
    new = _tif(316900, 5459100, 1200, 1200, west, CRS.from_epsg(6654), strips=True)
    old = _tif(316800, 5459200, 1400, 1400, np.full((1400, 1400), 400.0), "EPSG:2955")
    box = transform_bounds("EPSG:2955", "EPSG:4326", 316900, 5457900, 318100, 5459100, densify_pts=21)
    gone = "082/082e/2025/dem/bc_082e023_3_2_2_xli1m_utm11_20250629_20250629.tif"
    features = {5: [_feature(1, TILE_2017, "082e023_3_2_2", 2017, " ", box),
                    _feature(2, TILE_2024, "082e023_3_2_2", 2024, "utm11", box),
                    _feature(3, gone, "082e023_3_2_2", 2025, "utm11", box)]}
    _featureserver(http_server, features)
    keys = {TILE_2024: ("n1", "2026-05-08T01:51:31.269Z"), TILE_2017: ("o1", "2025-01-02T00:00:00.000Z"),
            gone: ("g1", "2026-06-01T00:00:00.000Z")}
    _bucket(http_server, keys, {TILE_2024: new, TILE_2017: old})
    cache_dir = str(tmp_path / "cache")
    grid = Grid(left=317100.0, top=5458900.0, res=1.0, height=800, width=800, crs="EPSG:2955")
    layer = _layer(http_server)
    layer._use(cache_dir, None)
    block, = layer.tiles(grid)
    assert (block.crs, block.i, block.j, block.year) == ("EPSG:2955", 317, 5458, 2025)
    assert [f[0] for f in block.files] == ["bc_082e023_3_2_2_xli1m_utm11_20250629_20250629@g1",
                                           "bc_082e023_3_2_2_xli1m_utm11_20240721_20240726@n1",
                                           "bc_082e023_3_2_2_xl1m_17603@o1"]
    path = layer.tile_path(cache_dir, block)
    layer.download_tile(block, path)
    with rio.open(path) as cached:
        values = cached.read(1, masked=True).filled(np.nan)
        assert cached.bounds == (317000, 5458000, 318000, 5459000) and cached.res == (1.0, 1.0)
        assert cached.tags()["sources"] == ("bc_082e023_3_2_2_xli1m_utm11_20240721_20240726@n1,"
                                            "bc_082e023_3_2_2_xl1m_17603@o1")
        assert cached.tags()["years"] == "2024,2017"
    assert (values[:, :600] == 500).all() and (values[:, 600:] == 400).all()
    http_server.routes.clear()  # the file of 2017 uploaded again
    _featureserver(http_server, features)
    _bucket(http_server, {**keys, TILE_2017: ("o2", "2026-07-03T00:00:00.000Z")})
    again, = layer.index.versions._blocks(_layer(http_server).index.listing.fetch(49.25, -119.75)["sheets"],
                                          {"EPSG:2955": grid.bounds})
    assert again.key != block.key


# The source

def test_declaration():
    assert BC.regions == ("ca-bc",) and BC.countries == ("ca",) and BC.crs is None
    assert BC.local_crs is bc_utm_crs and BC.grid_origin == (0.0, 0.0)
    assert BC.fallbacks == ["canada", "canada_2m", "mrdem30"]  # never FABDEM
    assert set(BC.neighbours) == {"usa", "alaska", "alaska_ifsar"}
    for sid in BC.neighbours:
        assert "british_columbia" in src.SOURCES[sid].neighbours
    # canada is its first gap filler, no neighbour: a search on HRDEM in British Columbia (R41) takes nothing of it
    assert "canada" not in BC.neighbours and "british_columbia" not in src.SOURCES["canada"].neighbours
    for layer, kind, layers in ((BC.nmt, "dem", (6, 5)), (BC.nmpt, "dsm", (3, 1))):
        assert isinstance(layer, LidarBcBlocks) and layer.layers == layers
        assert layer.folder == f"canada/lidarbc-{kind}" and layer.block_m == 1000 and layer.native_res == 1.0
        assert layer.bucket == "https://nrs.objectstore.gov.bc.ca/gdwuts" and layer.index.ttl_days == 30
    assert src.net.HOST_SLOTS_OF["nrs.objectstore.gov.bc.ca"] == 4
    assert BC.credits[0].attribution == "Contains information licensed under the Open Government Licence – British " \
                                        "Columbia."
    assert BC.ortho is None
    order = [s.id for s in src.catalogue.canada.SOURCES]  # its offline boxes before canada's
    assert order.index("british_columbia") < order.index("canada")


@pytest.fixture
def offline(monkeypatch):
    def lookup(*args, **kwargs):
        raise ValueError("offline")
    monkeypatch.setattr(osm, "reverse", lookup)


@pytest.mark.parametrize("lat, lon, sid", [
    (49.70, -123.15, "british_columbia"),   # Squamish
    (49.49, -119.59, "british_columbia"),   # Penticton
    (49.50, -115.06, "british_columbia"),   # Fernie
    (53.92, -122.75, "british_columbia"),   # Prince George
    (51.30, -116.97, "british_columbia"),   # Golden
    (52.88, -119.26, "british_columbia"),   # Valemount
    (51.18, -115.57, "canada"),             # Banff
    (52.87, -118.08, "canada"),             # Jasper
    (51.43, -116.18, "canada"),             # Lake Louise
])
def test_offline_boxes(tmp_path, offline, lat, lon, sid):
    """Offline, the region boxes give British Columbia inside Canada's box; Alberta's places stay canada."""
    source, _ = src.choose_source("auto", lat, lon, str(tmp_path))
    assert source.id == sid


def test_offline_boxes_outside(tmp_path, offline):
    """Bellingham (the USA), Juneau (Alaska's box) and Haida Gwaii (west of 129.9° W: Alaska's box, as for canada)
    are no British Columbia offline; nor are Victoria and Vancouver, south of 49.4° N in the USA's box, which comes
    first (as for canada: the place lookup online gives them their region)."""
    for lat, lon in ((48.75, -122.48), (58.30, -134.42), (53.25, -132.07), (48.43, -123.37), (49.28, -123.12)):
        assert src.choose.country_code(lat, lon, str(tmp_path)) == "us", (lat, lon)
    assert src.choose.region_codes(49.70, -123.15, str(tmp_path), "ca") == ("ca-bc",)
