"""Scotland (the Scottish Remote Sensing Portal's open S3 bucket: an S3 ListObjectsV2 listing, OS National Grid
tile names, blocks composed newest collection first), North Rhine-Westphalia (Geobasis NRW's WCS) and Trento
(PAT's LiDAR 2014 ASCII grids on a computed 500 m tiling).

The listing follows Amazon S3's API reference, ListObjectsV2 (https://docs.aws.amazon.com/AmazonS3/latest/API/
API_ListObjectsV2.html): GET /?list-type=2&prefix=..&max-keys=.., a ListBucketResult in the namespace
http://s3.amazonaws.com/doc/2006-03-01/ with Contents (Key, LastModified, ETag, Size), IsTruncated and
NextContinuationToken, the next page asked with continuation-token; errors as <Error><Code>..<Message>. Real
answers recorded on 2026-11-02: tests/data/recorded/s3/ (README there)."""

import json
import os
import re
import sys
from urllib.parse import urlsplit
from xml.sax.saxutils import escape

import numpy as np
import pytest
import rasterio as rio
import requests
from rasterio.transform import from_origin
from rasterio.warp import transform

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cache  # noqa: E402
import osm  # noqa: E402
import sources as src  # noqa: E402
from grid import Grid  # noqa: E402
from http_server import Answer  # noqa: E402
from sources.indexes.cached import IndexUnavailable  # noqa: E402
from sources.indexes.osgrid import os_prefixes, os_square, os_tile_extent  # noqa: E402
from sources.indexes.s3listing import S3Object, S3Objects, list_objects  # noqa: E402
from sources.layers.s3blocks import S3Blocks  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
RECORDED = os.path.join(HERE, "data", "recorded", "s3", "srsp")
ORKNEY = "lidar/orkney-islands-council-23/dtm/27700/gridded/"
NS = "http://s3.amazonaws.com/doc/2006-03-01/"


def _recorded(name: str) -> bytes:
    with open(os.path.join(RECORDED, name), "rb") as f:
        return f.read()


@pytest.fixture(autouse=True)
def no_waiting(monkeypatch):
    monkeypatch.setattr(src.net, "_sleep", lambda attempt: None)


# The listing: recorded answers

def _serve_recorded(server):
    """The recorded pages of HY17 (max-keys 2: two pages) and the empty HY99 at the bucket's root."""
    token = re.search(rb"<NextContinuationToken>([^<]+)<", _recorded("page-1.xml")).group(1).decode()
    base = f"/?list-type=2&max-keys=2&prefix={ORKNEY}"
    server.add(base + "HY17", _recorded("page-1.xml"), "application/xml")
    server.add(f"{base}HY17&continuation-token={requests.utils.quote(token, safe='')}", _recorded("page-2.xml"),
               "application/xml")
    server.add(base + "HY99", _recorded("empty.xml"), "application/xml")
    return token


def test_list_objects_pages(http_server):
    """Two pages joined in their order, each key with its size, date and ETag (without its quotes); the
    second page asked with the first's continuation token, every request with our User-Agent."""
    token = _serve_recorded(http_server)
    found = list_objects(http_server.base, ORKNEY + "HY17", max_keys=2)
    assert [o.key.rsplit("/", 1)[-1] for o in found] == ["HY1700_50CM_DTM_ORKNEY2023.tif",
                                                          "HY1701_50CM_DTM_ORKNEY2023.tif",
                                                          "HY1702_50CM_DTM_ORKNEY2023.tif"]
    assert found[0] == S3Object(ORKNEY + "HY1700_50CM_DTM_ORKNEY2023.tif", 16012495, "2026-03-03T16:26:36.000Z",
                                "3101cb7fadd670caf3feddfd6c1d88db-2")
    asked = http_server.requests("/")
    assert len(asked) == 2 and not http_server.stray()
    assert dict(asked[0].query) == {"list-type": "2", "prefix": ORKNEY + "HY17", "max-keys": "2"}
    assert dict(asked[1].query)["continuation-token"] == token
    assert {r.user_agent for r in asked} == {cache.http_headers()["User-Agent"]}


def test_list_objects_empty(http_server):
    _serve_recorded(http_server)
    assert list_objects(http_server.base, ORKNEY + "HY99", max_keys=2) == []


@pytest.mark.parametrize("name, status, code", [("error-token.xml", 400, "InvalidArgument"),
                                                ("error-bucket.xml", 404, "NoSuchBucket")])
def test_list_objects_error_answers(http_server, name, status, code):
    """S3's error answers are IndexUnavailable naming their code and message, never an empty listing;
    so is the same <Error> with HTTP 200."""
    http_server.add(f"/?list-type=2&max-keys=1000&prefix=x", _recorded(name), "application/xml", status=status)
    with pytest.raises(IndexUnavailable, match=code):
        list_objects(http_server.base, "x")
    http_server.add(f"/?list-type=2&max-keys=1000&prefix=y", _recorded(name), "application/xml")
    with pytest.raises(IndexUnavailable, match=code):
        list_objects(http_server.base, "y")


@pytest.mark.parametrize("body", [b"<html>busy</html>", b"", b"<ListBucketResult xmlns='other'/>",
                                  f"<ListBucketResult xmlns='{NS}'><IsTruncated>true</IsTruncated>"
                                  f"</ListBucketResult>".encode()])
def test_list_objects_not_a_listing(http_server, body):
    """An answer that is no ListBucketResult of S3's namespace, or a truncated page without a token,
    is IndexUnavailable."""
    http_server.add("/?list-type=2&max-keys=1000&prefix=x", body, "application/xml")
    with pytest.raises(IndexUnavailable):
        list_objects(http_server.base, "x")


def test_list_objects_retries_server_errors(http_server):
    """S3's 500 and 503 (SlowDown) are asked again (net.RETRIES); a 4xx is not."""
    calls = []

    def flaky(request):
        calls.append(request)
        if len(calls) < 3:
            return Answer(503, b"<Error><Code>SlowDown</Code><Message>Please reduce</Message></Error>")
        return Answer(200, _recorded("empty.xml"), {"Content-Type": "application/xml"})
    http_server.route("/", flaky)
    assert list_objects(http_server.base, "z") == [] and len(calls) == 3


def test_list_objects_stops_at_a_repeated_token(http_server):
    """A service that hands out the same continuation token again never makes the listing loop."""
    page = (f"<ListBucketResult xmlns='{NS}'><IsTruncated>true</IsTruncated>"
            f"<NextContinuationToken>same</NextContinuationToken></ListBucketResult>").encode()
    http_server.route("/", lambda request: Answer(200, page, {"Content-Type": "application/xml"}))
    with pytest.raises(IndexUnavailable, match="token"):
        list_objects(http_server.base, "z")


def test_s3_objects_cached_per_tile(http_server, tmp_path):
    """The listing as a CachedIndex's: the items of the prefixes of a tile, cached in its answer (asked once);
    an error answer caches nothing."""
    _serve_recorded(http_server)
    from sources.indexes.cached import CachedIndex
    from sources.indexes.versions import ComposedBlocks

    def item(obj, lat, lon):
        return {"name": obj.key.rsplit("/", 1)[-1][:-4], "url": f"{http_server.base}/{obj.key}"}
    listing = S3Objects(http_server.base, lambda lat, lon: [ORKNEY + "HY17", ORKNEY + "HY99"], item, max_keys=2)
    index = CachedIndex("test", listing, ComposedBlocks("t/x", 1000, 0.5), "x", "t")
    cache_dir = str(tmp_path)
    assert [i["name"] for i in index.answers(cache_dir, 58.75, -3.5)] == [
        "HY1700_50CM_DTM_ORKNEY2023", "HY1701_50CM_DTM_ORKNEY2023", "HY1702_50CM_DTM_ORKNEY2023"]
    assert len(http_server.log) == 3
    index.answers(cache_dir, 58.75, -3.5)
    assert len(http_server.log) == 3
    broken = S3Objects(http_server.base, lambda lat, lon: ["x"], item)
    http_server.add("/?list-type=2&max-keys=1000&prefix=x", _recorded("error-token.xml"), "application/xml", 400)
    index = CachedIndex("test", broken, ComposedBlocks("t/x", 1000, 0.5), "y", "t")
    with pytest.raises(IndexUnavailable):
        index.answers(cache_dir, 58.75, -3.5)
    assert not os.path.exists(index.index_path(cache_dir, 58.75, -3.5))


# The OS National Grid

@pytest.mark.parametrize("name, extent", [
    ("HY1700", (317000, 1000000, 318000, 1001000)),  # Orkney 2023: the file's own bounds
    ("NL9145", (91000, 745000, 92000, 746000)),      # coastal 2025-26 on Tiree: the file's own bounds
    ("NR9542", (195000, 642000, 196000, 643000)),    # Arran
    ("NX1530", (215000, 530000, 216000, 531000)),
    ("SV0000", (0, 0, 1000, 1000)),
    ("HY21", (320000, 1010000, 330000, 1020000)),    # 10 km
    ("NO10NE", (315000, 705000, 320000, 710000)),    # a 5 km quadrant
])
def test_os_tile_extent(name, extent):
    assert os_tile_extent(name) == extent
    assert os_tile_extent(name.lower()) == extent
    assert os_square(extent[0], extent[1]) == name[:2]


def test_os_tile_extent_not_a_tile():
    for name in ("XX1234", "NI1234", "N1234", "NR954", "AB", ""):
        assert os_tile_extent(name) is None, name


def test_os_prefixes():
    """The prefixes of the 1 km names over a box: a 100 km square and the tens of kilometres east."""
    assert os_prefixes(195500, 642500, 196500, 642600) == ["NR9"]
    assert os_prefixes(199500, 642500, 200500, 642600) == ["NR9", "NS0"]
    assert os_prefixes(195500, 699500, 196500, 700500) == ["NR9", "NM9"]
    assert os_prefixes(185000, 642000, 205000, 643000) == ["NR8", "NR9", "NS0"]


# Scotland's layers

SCT = src.SOURCES["scotland"] if "scotland" in src.SOURCES else None
NLP, COASTAL = "lidar/national-lidar-programme/{}/27700/gridded/", "lidar/coastal/coastal-2025-2026/{}/27700/gridded/"


def _contents(key: str, etag: str = "abc", modified: str = "2026-09-25T11:04:31.000Z", size: int = 1000) -> str:
    return (f"<Contents><Key>{escape(key)}</Key><LastModified>{modified}</LastModified><ETag>&quot;{etag}&quot;"
            f"</ETag><Size>{size}</Size><StorageClass>STANDARD</StorageClass></Contents>")


def _bucket(server, keys, max_keys: int = 1000):
    """A bucket on the local server answering ListObjectsV2 for keys {key: etag} (pages of max_keys, the
    continuation token the position of the next key) and serving each file whose content is bytes."""
    names = sorted(keys)

    def listing(request):
        if request.path != "/":
            return None
        q = dict(request.query)
        assert q["list-type"] == "2"
        found = [k for k in names if k.startswith(q.get("prefix", ""))]
        start = int(q.get("continuation-token", 0))
        page, rest = found[start:start + int(q.get("max-keys", 1000))], found[start + int(q.get("max-keys", 1000)):]
        body = (f"<?xml version='1.0' encoding='UTF-8'?><ListBucketResult xmlns='{NS}'><Name>b</Name>"
                f"<Prefix>{escape(q.get('prefix', ''))}</Prefix><KeyCount>{len(page)}</KeyCount>"
                f"<IsTruncated>{'true' if rest else 'false'}</IsTruncated>"
                + (f"<NextContinuationToken>{start + len(page)}</NextContinuationToken>" if rest else "")
                + "".join(_contents(k, keys[k] if isinstance(keys[k], str) else "e") for k in page)
                + "</ListBucketResult>")
        return Answer(200, body.encode(), {"Content-Type": "application/xml"})
    server.route("/", listing)


def _scotland_layer(server, kind="dtm", max_keys=1000):
    layer = SCT.nmt if kind == "dtm" else SCT.nmpt
    return S3Blocks(layer.description, server.base, layer.collections, layer.prefix, layer.folder, layer.crs,
                    layer.native_res, layer.block_m, layer.bytes_per_tile(), layer.names, layer.extent,
                    max_keys=max_keys)


def test_scotland_declaration():
    assert SCT is not None
    for kind, layer in (("dtm", SCT.nmt), ("dsm", SCT.nmpt)):
        assert isinstance(layer, S3Blocks) and isinstance(layer, src.IndexedTiles)
        assert layer.crs == "EPSG:27700" and layer.native_res == 0.5 and layer.block_m == 1000
        # Newest collection first: coastal 2025-26, the national programme, Orkney 2023
        assert [(c, y) for c, y in layer.collections] == [
            (COASTAL.format(kind), 2026), (NLP.format(kind), 2025),
            (f"lidar/orkney-islands-council-23/{kind}/27700/gridded/", 2023)]
        assert layer.bucket == "https://srsp-open-data.s3.eu-west-2.amazonaws.com"


def test_scotland_items(http_server, tmp_path):
    """The listed files of a 0.25° tile (Arran): those of every collection under the tile's prefixes whose
    1 km square meets the tile, with their collection's year, their date, and the ETag in their name (a file
    uploaded again changes its block's key); other files and names are left out. Paged answers give the
    same items."""
    keys = {NLP.format("dtm") + "NR9542_50cm_DTM_ScotlandNationalLiDAR.tif": "aaaa1111bbbb",
            NLP.format("dtm") + "NR9543_50cm_DTM_ScotlandNationalLiDAR.tif": "cccc2222",
            NLP.format("dtm") + "NR9599_50cm_DTM_ScotlandNationalLiDAR.tif": "dddd",  # north of the tile
            NLP.format("dtm") + "NR9542_50cm_DTM_ScotlandNationalLiDAR.tif.aux.xml": "x",
            NLP.format("dsm") + "NR9542_50cm_DSM_ScotlandNationalLiDAR.tif": "eeee",
            COASTAL.format("dtm") + "NR9542_50CM_DTM_COASTAL20252026.tif": "ffff3333-2"}
    _bucket(http_server, keys)
    cache_dir = str(tmp_path)
    for max_keys in (1000, 1):
        layer = _scotland_layer(http_server, max_keys=max_keys)
        items = sorted(layer.index.listing.fetch(55.5, -5.25)["sheets"], key=lambda i: i["url"])
        assert items == [
            {"name": "NR9542_50CM_DTM_COASTAL20252026@ffff3333", "url": f"{http_server.base}/{COASTAL.format('dtm')}"
             "NR9542_50CM_DTM_COASTAL20252026.tif", "crs": "EPSG:27700", "extent": [195000, 642000, 196000, 643000],
             "year": 2026, "published": "2026-09-25T11:04:31.000Z"},
            {"name": "NR9542_50cm_DTM_ScotlandNationalLiDAR@aaaa1111", "url": f"{http_server.base}/"
             f"{NLP.format('dtm')}NR9542_50cm_DTM_ScotlandNationalLiDAR.tif", "crs": "EPSG:27700",
             "extent": [195000, 642000, 196000, 643000], "year": 2025, "published": "2026-09-25T11:04:31.000Z"},
            {"name": "NR9543_50cm_DTM_ScotlandNationalLiDAR@cccc2222", "url": f"{http_server.base}/"
             f"{NLP.format('dtm')}NR9543_50cm_DTM_ScotlandNationalLiDAR.tif", "crs": "EPSG:27700",
             "extent": [195000, 643000, 196000, 644000], "year": 2025, "published": "2026-09-25T11:04:31.000Z"}]
    asked = {dict(r.query)["prefix"] for r in http_server.requests("/")}
    # The tile 55.5-55.75 N, 5.25-5 W: 194.8-211.8 km E, 627-655.5 km N, the columns NR9, NS0 and NS1
    assert {p.rsplit("/", 1)[-1] for p in asked} == {"NR9", "NS0", "NS1"}
    assert all(p.startswith((NLP.format("dtm"), COASTAL.format("dtm"), "lidar/orkney-islands-council-23/dtm/"))
               for p in asked)
    assert not http_server.stray()


def _tif(path, left, top, width, height, values, nodata=-32767.0, tiled=True):
    with rio.open(path, "w", driver="GTiff", width=width, height=height, count=1, dtype="float32",
                  crs="EPSG:27700", transform=from_origin(left, top, 0.5, 0.5), nodata=nodata,
                  **({"tiled": True, "blockxsize": 256, "blockysize": 256} if tiled else {})) as dst:
        dst.write(values.astype(np.float32), 1)
    with open(path, "rb") as f:
        return f.read()


def test_scotland_block_composed_newest_first(http_server, tmp_path):
    """A 1 km block (2000 px of 0.5 m) over Arran from a coastal file (newest) that covers its west half and
    a national file clipped at the coast (as NLP's coast tiles are: 31 x 331 px of NL9145): each pixel from the
    newest file with data there; the block's key changes when a file's ETag does."""
    west = np.full((2000, 2000), -9999.0, dtype=np.float32)
    west[:, :1000] = 100.0
    coastal = _tif(str(tmp_path / "c.tif"), 195000, 643000, 2000, 2000, west, nodata=-9999.0)
    clipped = _tif(str(tmp_path / "n.tif"), 195500, 642900, 1200, 400, np.full((400, 1200), 50.0), tiled=False)
    c_key = COASTAL.format("dtm") + "NR9542_50CM_DTM_COASTAL20252026.tif"
    n_key = NLP.format("dtm") + "NR9542_50cm_DTM_ScotlandNationalLiDAR.tif"
    keys = {c_key: "c1", n_key: "n1"}
    _bucket(http_server, keys)
    http_server.add("/" + c_key, coastal, "image/tiff")
    http_server.add("/" + n_key, clipped, "image/tiff")
    layer = _scotland_layer(http_server)
    cache_dir = str(tmp_path / "cache")
    grid = Grid(left=195100.0, top=642900.0, res=1.0, height=800, width=800, crs="EPSG:27700")
    layer._use(cache_dir, None)
    block, = layer.tiles(grid)
    assert (block.i, block.j, block.year) == (195, 642, 2026)
    assert [f[0] for f in block.files] == ["NR9542_50CM_DTM_COASTAL20252026@c1",
                                           "NR9542_50cm_DTM_ScotlandNationalLiDAR@n1"]
    path = layer.tile_path(cache_dir, block)
    layer.download_tile(block, path)
    with rio.open(path) as cached:
        values = cached.read(1, masked=True).filled(np.nan)
        assert cached.res == (0.5, 0.5) and cached.bounds == (195000, 642000, 196000, 643000)
        assert cached.tags()["sources"] == "NR9542_50CM_DTM_COASTAL20252026@c1,NR9542_50cm_DTM_ScotlandNationalLiDAR@n1"
    assert (values[:, :1000] == 100).all()
    assert (values[200:600, 1000:] == 50).all() and np.isnan(values[:200, 1000:]).all()
    assert np.isnan(values[600:, 1000:]).all()
    # A file uploaded again (a new ETag): another key, so the block is read again
    http_server.routes.clear()
    _bucket(http_server, {c_key: "c2", n_key: "n1"})
    other = _scotland_layer(http_server)
    again, = other.index.versions._blocks(
        [dict(i) for i in other.index.listing.fetch(55.5, -5.25)["sheets"]], {"EPSG:27700": grid.bounds})
    assert again.key != block.key


def test_scotland_offline_boxes():
    """Scotland's boxes come before England's (which reaches 55.82° N): Arran, Galloway and Orkney give
    gb-sct; Northern Ireland and Cumbria do not."""
    assert {code for code, _ in SCT.offline} == {"gb-sct"}

    def inside(lat, lon):
        return any(s <= lat <= n and w <= lon <= e for _, (s, n, w, e) in SCT.offline)
    for lat, lon in ((55.636, -5.206), (54.682, -4.394), (58.887, -3.43), (55.8, -6.2), (57.0, -6.3)):
        assert inside(lat, lon), (lat, lon)
    for lat, lon in ((54.6, -5.9), (55.2, -6.2), (54.7, -3.5), (54.9, -2.9), (55.0, -1.6)):
        assert not inside(lat, lon), (lat, lon)
    order = list(src.SOURCES)
    assert order.index("scotland") < order.index("england")


# North Rhine-Westphalia

def test_nrw_wcs_requests():
    """2 km tiles of 1 m on whole metres from the WCS 2.0.1 of each model (axes x and y); the DOM's
    answers compressed by the server and its 0 outside the Land taken as no data."""
    nrw = src.SOURCES["north_rhine_westphalia"]
    for layer, name in ((nrw.nmt, "dgm"), (nrw.nmpt, "dom")):
        assert isinstance(layer, src.WcsTiles)
        assert layer.url == f"https://www.wcs.nrw.de/geobasis/wcs_nw_{name}" and layer.coverage == f"nw_{name}"
        assert layer.crs == "EPSG:25832" and layer.axes == ("x", "y") and layer.tile_px == 2000
        assert layer.native_res == 1.0 and layer.fetch_res == 1.0 and layer.folder.endswith("/live")
        params = dict(layer.reader.coverage_params(466000, 5684000, 468000, 5686000, 1.0))
        assert params["COVERAGEID"] == f"nw_{name}" and params["FORMAT"] == "image/tiff"
    assert not nrw.nmt.zero_is_nodata and nrw.nmpt.zero_is_nodata
    assert ("GEOTIFF:COMPRESSION", "DEFLATE") in nrw.nmpt.params
    grid = Grid(left=466100.0, top=5685900.0, res=1.0, height=800, width=800, crs="EPSG:25832")
    assert nrw.nmt.tiles(grid) == [(1.0, 233, 2842)]  # 466-468 km E, 5684-5686 km N


# Trento

@pytest.mark.parametrize("lat, lon, tile, name", [
    (45.9245, 10.8855, (1292, 10174), "5h646050870"),  # the Colodri wall above Arco
    (45.990, 10.905, (1295, 10189), "5h647550945"),    # Monte Brento
])
def test_trento_tile_names(lat, lon, tile, name):
    """500 m tiles named 5h<E / 100 m, 4 digits><N / 100 m, 5 digits> by their south-west corner (EPSG:25832);
    the DTM's and the DSM's (first returns) folders; cached as grid_tile_name, read back."""
    tn = src.SOURCES["trento"]
    xs, ys = transform("EPSG:4326", "EPSG:25832", [lon], [lat])
    grid = Grid(left=xs[0] - 20, top=ys[0] + 20, res=1.0, height=40, width=40, crs="EPSG:25832")
    assert tn.nmt.tiles(grid) == [tile] and tn.nmpt.tiles(grid) == [tile]
    assert tn.nmt.tile_url(tile) == f"https://siatservices.provincia.tn.it/stemdata/2014_lidar_dtm_asc/{name}_DTM.asc"
    assert (tn.nmpt.tile_url(tile)
            == f"https://siatservices.provincia.tn.it/stemdata/2014_lidar_dsmfirst_asc/{name}_DSMFirst.asc")
    for layer in (tn.nmt, tn.nmpt):
        path = f"{layer.folder}/{tile[0] // 10}_{tile[1] // 10}/{tile[0]}_{tile[1]}.tif"
        assert layer.tile_of(path) == tile


@pytest.mark.parametrize("header", [
    "ncols 4\nnrows 3\nxllcenter 646000.25\nyllcenter 5087000.25\ncellsize 0.50\nnodata_value -9999.00\n",
    "NCOLS         4\r\nNROWS         3\r\nXLLCENTER     646000.250\r\nYLLCENTER     5087000.250\r\n"
    "CELLSIZE      0.5\r\nNODATA_VALUE  -9999\r\n",
])
def test_trento_ascii_tile(http_server, tmp_path, header):
    """A plain ASCII grid without a CRS (either header as the province writes them): cached as a GeoTIFF in
    EPSG:25832 with its pixel edges on whole metres (xllcenter = corner + 0.25), -9999 as no data."""
    rows = " 252.03 251.70 -9999.00 248.47\n 1 2 3 4\n 5 6 7 8\n"
    http_server.add("/2014_lidar_dtm_asc/5h646050870_DTM.asc", (header + rows).encode(), "application/octet-stream")
    layer = src.SOURCES["trento"].nmt
    request = layer.index.request((1292, 10174))
    request = request._replace(url=http_server.url("/2014_lidar_dtm_asc/5h646050870_DTM.asc"))
    path = str(tmp_path / "t.tif")
    fetched = layer.reader.fetch(request, path)
    assert fetched.received > 0
    with rio.open(path) as cached:
        assert cached.crs.to_epsg() == 25832
        assert cached.transform == from_origin(646000.0, 5087001.5, 0.5, 0.5)
        values = cached.read(1, masked=True).astype(np.float32).filled(np.nan)
    assert np.isnan(values[0, 2]) and values[0, 0] == np.float32(252.03) and values[2, 3] == 8


# --source auto in the regions (Nominatim's answers recorded on 2026-11-01 and 2026-11-02)

@pytest.fixture
def recorded(monkeypatch):
    answers = {}
    for name in ("reverse.json", "reverse-sct-nw.json"):
        with open(os.path.join(HERE, "data", "recorded", "nominatim", name), encoding="utf-8") as f:
            answers.update({(r["query"]["lat"], r["query"]["lon"], r["query"]["zoom"]): r["answer"]
                            for r in json.load(f)})
    monkeypatch.setattr(osm, "reverse", lambda lat, lon, cache_dir, **params:
                        answers[(round(lat, 5), round(lon, 5), params["zoom"])])


@pytest.mark.parametrize("lat, lon, sid, region", [
    (55.636, -5.206, "scotland", "GB-SCT"),      # Arran
    (58.887, -3.43, "scotland", "GB-SCT"),       # Hoy, Orkney
    (51.32, 8.54, "north_rhine_westphalia", "DE-NW"),  # the Bruchhauser Steine
    (46.07, 11.12, "trento", "IT-TN"),           # Trento (IT-TN is a lvl6 code, as IT-BZ)
    (54.4542, -3.2116, "england", "GB-ENG"),     # Scafell Pike stays England's
])
def test_regions(tmp_path, recorded, lat, lon, sid, region):
    assert src.choose_source("auto", lat, lon, str(tmp_path)) == (src.SOURCES[sid], f"the centre is in {region}")
