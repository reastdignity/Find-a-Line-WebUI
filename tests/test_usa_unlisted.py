"""The USA's 1 m DEM files that USGS's bucket holds and the TNM index does not list (sources/layers/tnmbucket.py): the
list (the bucket's listing, the index's, the zone of names without one, the file), the copy shipped with the code,
and the merge of the list into the index's answers (tnm.UnlistedIndex)."""

import contextlib
import json
import os
import re
import sys
from urllib.parse import urlencode, urlsplit

import numpy as np
import pytest
import rasterio as rio
import requests
from rasterio.transform import from_origin
from rasterio.warp import transform_bounds

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cache  # noqa: E402
import sources as src  # noqa: E402
from http_server import Answer, key_of  # noqa: E402
from sources import net  # noqa: E402
from sources.indexes.cached import CachedIndex, IndexUnavailable  # noqa: E402
from sources.indexes.s3listing import S3_NS, PageBudget, S3Object  # noqa: E402
from sources.layers import tnmbucket as tb  # noqa: E402
from sources.layers.tnm import tile_extent, tile_item  # noqa: E402
from test_sources import RES, FakeTnm, _tile_1m  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
RECORDED = os.path.join(HERE, "data", "recorded", "bucket1m", "usgs-1m")
API_PATH = "/api/v1/products"


@pytest.fixture(autouse=True)
def fresh_list(monkeypatch):
    """Every test reads the lists anew; the shipped copy stays off (conftest) unless a test turns it on."""
    tb.forget_unlisted()
    monkeypatch.setattr(src.net, "_sleep", lambda attempt: None)
    yield
    tb.forget_unlisted()


def _key(project, name):
    return f"{tb.PROJECTS}{project}/TIFF/{name}"


# A small bucket and TNM index on the local server

def _s3_answer(keys, request, max_keys_default=1000):
    """ListObjectsV2 over keys [(key, size, date)]: a prefix, an optional delimiter, pages of max-keys with
    continuation tokens (the index of the next key)."""
    query = dict(request.query)
    prefix, delimiter = query.get("prefix", ""), query.get("delimiter")
    size = int(query.get("max-keys", max_keys_default))
    entries = []
    for key, length, date in sorted(keys):
        if not key.startswith(prefix):
            continue
        rest = key[len(prefix):]
        if delimiter and delimiter in rest:
            folder = prefix + rest[:rest.index(delimiter) + 1]
            if ("p", folder) not in entries:
                entries.append(("p", folder))
        else:
            entries.append(("k", (key, length, date)))
    start = int(query.get("continuation-token", "0"))
    page, more = entries[start:start + size], start + size < len(entries)
    body = [f"<ListBucketResult xmlns='{S3_NS[1:-1]}'><IsTruncated>{'true' if more else 'false'}</IsTruncated>"]
    if more:
        body.append(f"<NextContinuationToken>{start + size}</NextContinuationToken>")
    for kind, entry in page:
        if kind == "p":
            body.append(f"<CommonPrefixes><Prefix>{entry}</Prefix></CommonPrefixes>")
        else:
            body.append(f"<Contents><Key>{entry[0]}</Key><LastModified>{entry[2]}</LastModified>"
                        f"<ETag>\"e\"</ETag><Size>{entry[1]}</Size></Contents>")
    body.append("</ListBucketResult>")
    return Answer(200, "".join(body).encode(), {"Content-Type": "application/xml"})


def _product(url, zone, x, y):
    west, south, east, north = transform_bounds(f"EPSG:{26900 + zone}", "EPSG:4326", x * 10000, (y - 1) * 10000,
                                                (x + 1) * 10000, y * 10000)
    return {"downloadURL": url, "publicationDate": "2024-01-01",
            "boundingBox": {"minX": west, "minY": south, "maxX": east, "maxY": north}}


def _tnm_answer(products, request, page_size=500):
    """The TNM index: every product in every box (the boxes are not tested here), pages by offset."""
    query = dict(request.query)
    offset, size = int(query["offset"]), int(query["max"])
    body = json.dumps({"total": len(products), "items": products[offset:offset + min(size, page_size)]})
    return Answer(200, body.encode(), {"Content-Type": "application/json"})


def _header_file(path, zone, x, y, crs=None, shift=0.0):
    """A small GeoTIFF like a 1 m tile: its name's 10 km square with 6 m around, in NAD83 / UTM of zone."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    px = 20
    res = 10012.0 / px
    with rio.open(path, "w", driver="GTiff", width=px, height=px, count=1, dtype="float32",
                  crs=crs or f"EPSG:{26900 + zone}", nodata=-999999.0,
                  transform=from_origin(x * 10000 - 6 + shift, y * 10000 + 6, res, res)) as dst:
        dst.write(np.full((px, px), 1000.0, np.float32), 1)


def _serve(http_server, tmp_path, products_of=None):
    """A bucket of four projects and an index listing some of their files, on the server; the files that need a
    header read served as GeoTIFFs. Returns the bucket's keys."""
    base = http_server.base
    listed_names = [("CO_Listed_2019", "USGS_1M_13_x46y443_CO_Listed_2019.tif"),
                    ("CO_Two_2018", "USGS_1M_12_x75y443_CO_Two_2018.tif"),
                    ("CO_Two_2018", "USGS_1M_13_x23y443_CO_Two_2018.tif"),
                    ("UT_Named_2020", "USGS_1M_12_x43y448_UT_Named_2020.tif")]
    unlisted = [("UT_Named_2020", "USGS_1M_12_x43y449_UT_Named_2020.tif"),        # the zone in the name
                ("CO_Listed_2019", "USGS_one_meter_x47y443_CO_Listed_2019.tif"),  # the project's one zone
                ("CO_Two_2018", "USGS_one_meter_x24y443_CO_Two_2018.tif"),        # two zones: the header
                ("AL_25Co_B1_2017", "USGS_1m_x38y372_AL_25Co_B1_2017.tif"),       # none listed: the header
                ("AL_25Co_B1_2017", "USGS_1m_x99y999_AL_25Co_B1_2017.tif")]       # no file: left out
    keys = [(_key(p, n), 1000 + i, f"2026-02-1{i}T10:00:00.000Z") for i, (p, n) in enumerate(listed_names + unlisted)]
    keys.append((_key("UT_Named_2020", "USGS_1M_12_x43y448_UT_Named_2020.xml"), 5, "2026-02-10T10:00:00.000Z"))
    products = [_product(f"{base}/{_key(p, n)}", int(n.split("_")[2]), int(re.search(r"x(\d+)", n).group(1)),
                         int(re.search(r"y(\d+)", n).group(1))) for p, n in listed_names]
    files = tmp_path / "served"
    _header_file(str(files / "a.tif"), 13, 24, 443)
    _header_file(str(files / "b.tif"), 16, 38, 372)
    for name, key in (("a.tif", _key("CO_Two_2018", "USGS_one_meter_x24y443_CO_Two_2018.tif")),
                      ("b.tif", _key("AL_25Co_B1_2017", "USGS_1m_x38y372_AL_25Co_B1_2017.tif"))):
        with open(files / name, "rb") as f:
            http_server.add("/" + key, f.read(), "image/tiff")
    http_server.route(API_PATH, lambda request: _tnm_answer(products_of() if products_of else products, request))
    http_server.route("/", lambda request: _s3_answer(keys, request) if request.path == "/" else None)
    return keys


# 1. The list

def test_make_unlisted(http_server, tmp_path, monkeypatch):
    """The bucket's .tif files the index does not name, each as a TNM item with its zone (in the name; the
    project's one zone; the header), one without a file left out by name; written atomically with a row in the
    cache's index; counts, bytes and requests returned; every request with our User-Agent under a host slot."""
    _serve(http_server, tmp_path)
    monkeypatch.setattr(tb, "MAX_UNLISTED_SHARE", 1.0)  # 5 of this bucket's 9 files are unlisted
    slots = []
    original = net.host_slot

    @contextlib.contextmanager
    def slot(cache_dir, url):
        slots.append(urlsplit(url).path)
        with original(cache_dir, url):
            yield
    monkeypatch.setattr(net, "host_slot", slot)
    cache_dir = str(tmp_path / "cache")
    done = tb.make_unlisted(cache_dir, bucket=http_server.base, api=http_server.url(API_PATH),
                            regions=[(-125.0, 24.0, -66.0, 50.0)], log=lambda text: None)
    path = tb.unlisted_path(cache_dir)
    assert done["path"] == path and os.path.exists(path) and not [n for n in os.listdir(os.path.dirname(path))
                                                                   if n.endswith(".part")]
    assert (done["files"], done["zone_in_name"], done["zone_from_project"], done["zone_from_header"]) == (4, 1, 1, 2)
    assert done["left_out"] == ["USGS_1m_x99y999_AL_25Co_B1_2017.tif"]
    assert done["bytes"] == 1004 + 1005 + 1006 + 1007 and done["bucket_files"] == 9 and done["listed"] == 4
    assert done["requests"] == {"bucket": 5, "index": 1, "headers": 3}  # the folders, 4 projects
    items = tb.read_list(path)
    by_name = {i["name"]: i for i in items}
    assert {n: i["crs"] for n, i in by_name.items()} == {
        "USGS_1M_12_x43y449_UT_Named_2020": "EPSG:26912", "USGS_one_meter_x47y443_CO_Listed_2019": "EPSG:26913",
        "USGS_one_meter_x24y443_CO_Two_2018": "EPSG:26913", "USGS_1m_x38y372_AL_25Co_B1_2017": "EPSG:26916"}
    item = by_name["USGS_1M_12_x43y449_UT_Named_2020"]
    assert item == {"name": "USGS_1M_12_x43y449_UT_Named_2020",
                    "url": f"{http_server.base}/{_key('UT_Named_2020', 'USGS_1M_12_x43y449_UT_Named_2020.tif')}",
                    "crs": "EPSG:26912", "extent": [430000, 4480000, 440000, 4490000], "year": 2020,
                    "published": "2026-02-14T10:00:00.000Z"}
    assert [i["url"] for i in items] == sorted(i["url"] for i in items)
    assert cache.info(cache_dir, path)["status"] == "ok" and tb.unlisted_age_days(cache_dir) < 0.01
    assert {r.user_agent for r in http_server.log} == {cache.http_headers()["User-Agent"]}
    assert not [r for r in http_server.stray() if "x99y999" not in r.path]
    # every list page and index page under a slot of its host (the header reads too)
    assert slots.count("/") == 5 and slots.count(API_PATH) == 1 and len(slots) == 9


def test_make_unlisted_keeps_the_list_when_a_step_fails(http_server, tmp_path):
    """A failing index (HTTP 500, asked again, then given up), an index that lists nothing or one that answered too
    little: IndexUnavailable, and the list there was stays as it was."""
    state = {"products": None}
    _serve(http_server, tmp_path, products_of=lambda: state["products"])
    cache_dir = str(tmp_path / "cache")
    path = tb.unlisted_path(cache_dir)
    os.makedirs(os.path.dirname(path))
    with open(path, "w", encoding="utf-8") as f:
        f.write('{"items": []}')
    run = lambda: tb.make_unlisted(cache_dir, bucket=http_server.base, api=http_server.url(API_PATH),  # noqa: E731
                                   regions=[(-125.0, 24.0, -66.0, 50.0)], log=lambda text: None)
    http_server.add(API_PATH, b"busy", "text/plain", status=500)  # a fixed answer wins over the route
    with pytest.raises(IndexUnavailable, match="TNM API"):
        run()
    del http_server.answers[key_of("GET", API_PATH)]
    state["products"] = []
    with pytest.raises(IndexUnavailable, match="listed no 1 m file"):
        run()
    state["products"] = [_product("https://x/Projects/P/TIFF/USGS_1M_12_x1y1_P.tif", 12, 1, 1)]
    with pytest.raises(IndexUnavailable, match="answered too little"):
        run()
    with open(path, encoding="utf-8") as f:
        assert f.read() == '{"items": []}'


def test_bucket_listing_is_bounded(http_server):
    """A repeated continuation token ends the bucket's listing with an error, not a loop; so does a listing that
    needs more pages than its budget."""
    page = (f"<ListBucketResult xmlns='{S3_NS[1:-1]}'><IsTruncated>true</IsTruncated>"
            f"<NextContinuationToken>same</NextContinuationToken>"
            f"<CommonPrefixes><Prefix>{tb.PROJECTS}A/</Prefix></CommonPrefixes></ListBucketResult>").encode()
    http_server.route("/", lambda request: Answer(200, page, {"Content-Type": "application/xml"}))
    with pytest.raises(IndexUnavailable, match="token"):
        tb.bucket_files(None, http_server.base)
    assert len(http_server.requests("/")) == 2
    keys = [(_key(f"P{i}", f"USGS_1M_12_x{i}y1_P{i}.tif"), 1, "2026-01-01T00:00:00.000Z") for i in range(5)]
    http_server.routes.clear()
    http_server.route("/", lambda request: _s3_answer(keys, request))
    assert len(tb.bucket_files(None, http_server.base, PageBudget("test", 6))) == 5  # the folders, then 5 projects
    with pytest.raises(IndexUnavailable, match="more than 5 pages"):
        tb.bucket_files(None, http_server.base, PageBudget("test", 5))


def test_tnm_listing_in_small_boxes(monkeypatch):
    """The index asked over the regions: a box that holds more than SPLIT_ABOVE is asked as its quarters (no deep
    offsets), a page shorter than its total promises asked again once and joined (the API counts some products
    twice), the pages after it at the offset of what came; distinct URLs kept; more pages than the budget: an
    error."""
    monkeypatch.setattr(tb, "SPLIT_ABOVE", 6)
    monkeypatch.setattr(tb, "TNM_PAGE", 4)
    asked = []
    products = [f"https://x/Projects/P/TIFF/USGS_1M_12_x{i}y1_P.tif" for i in range(9)]

    def fake(url, params=None, headers=None, **kwargs):
        box, offset = tuple(float(v) for v in params["bbox"].split(",")), int(params["offset"])
        asked.append((box, offset))
        assert headers["User-Agent"] == cache.http_headers()["User-Agent"] and params["max"] == 4
        if box == (0.0, 0.0, 8.0, 8.0):                       # the region: 9 products, more than 6
            total, items = 9, products[:4]
        elif box == (0.0, 0.0, 4.0, 4.0):                     # its south-west quarter: 6 said, 5 distinct
            total = 6
            first = sum(1 for b, o in asked if b == box and o == 0)
            items = {0: products[:2] if first == 1 else products[:3], 3: products[3:5], 5: []}.get(offset, [])
        else:
            total, items = 0, []
        response = requests.Response()
        response.status_code, response._content = 200, json.dumps(
            {"total": total, "items": [{"downloadURL": u} for u in items]}).encode()
        return response
    monkeypatch.setattr(requests, "get", fake)
    found = tb.tnm_listed(None, "https://tnm.example/api", "Test DEM", [(0.0, 0.0, 8.0, 8.0)])
    assert sorted(found) == sorted(products[:5])
    quarter = [o for b, o in asked if b == (0.0, 0.0, 4.0, 4.0)]
    # 2 of 4: asked again (3 came); from 3: 2 of 3, again; from 5: nothing of the 1 said, again; the end
    assert quarter == [0, 0, 3, 3, 5, 5]
    assert [b for b, _ in asked].count((0.0, 0.0, 8.0, 8.0)) == 1 and len({b for b, _ in asked}) == 5
    with pytest.raises(IndexUnavailable, match="more than 3 pages"):
        tb.tnm_listed(None, "https://tnm.example/api", "Test DEM", [(0.0, 0.0, 8.0, 8.0)], PageBudget("TNM", 3))


# 3. The zone

def test_zone_of_the_three_name_forms():
    """USGS_1M_<zone>_x..y..: the zone in the name. USGS_one_meter_x..y..: the project's one zone when the tile then
    lies in the project's box, else the header. USGS_1m_x..y..: the header when no file of its project is listed. A
    header that gives no zone: left out by name."""
    urls = [f"https://b/{tb.PROJECTS}OR_A_2019/TIFF/USGS_1M_10_x50y500_OR_A_2019.tif",
            f"https://b/{tb.PROJECTS}UT_B_2013/TIFF/USGS_1M_12_x43y448_UT_B_2013.tif"]
    listed = {urls[0]: _product(urls[0], 10, 50, 500), urls[1]: _product(urls[1], 12, 43, 448)}
    objects = [S3Object(_key("OR_A_2019", "USGS_1M_10_x51y500_OR_A_2019.tif"), 1, "2026-02-01T00:00:00Z", ""),
               S3Object(_key("UT_B_2013", "USGS_one_meter_x43y449_UT_B_2013.tif"), 2, "2026-02-01T00:00:00Z", ""),
               S3Object(_key("UT_B_2013", "USGS_one_meter_x93y449_UT_B_2013.tif"), 3, "2026-02-01T00:00:00Z", ""),
               S3Object(_key("AL_C_2017", "USGS_1m_x38y372_AL_C_2017.tif"), 4, "2026-02-01T00:00:00Z", ""),
               S3Object(_key("AL_C_2017", "USGS_1m_x38y373_AL_C_2017.tif"), 5, "2026-02-01T00:00:00Z", ""),
               S3Object(_key("OR_A_2019", "USGS_1M_10_x50y500_OR_A_2019.tif"), 6, "2026-02-01T00:00:00Z", "")]
    asked = []

    def header(url, extent):
        asked.append(url.rsplit("/", 1)[-1])
        return {"USGS_1m_x38y372_AL_C_2017.tif": 16}.get(url.rsplit("/", 1)[-1])
    items, left_out, counts = tb.unlisted_from(objects, listed, header, "https://b")
    assert {i["name"]: i["crs"] for i in items} == {"USGS_1M_10_x51y500_OR_A_2019": "EPSG:26910",
                                                    "USGS_one_meter_x43y449_UT_B_2013": "EPSG:26912",
                                                    "USGS_1m_x38y372_AL_C_2017": "EPSG:26916"}
    # x93 in zone 12 lies 500 km east of the project's box: its header was asked (and gave nothing)
    assert asked == ["USGS_one_meter_x93y449_UT_B_2013.tif", "USGS_1m_x38y372_AL_C_2017.tif",
                     "USGS_1m_x38y373_AL_C_2017.tif"]
    assert left_out == ["USGS_1m_x38y373_AL_C_2017.tif", "USGS_one_meter_x93y449_UT_B_2013.tif"]
    assert counts == {"zone_in_name": 1, "zone_from_project": 1, "zone_from_header": 1, "bytes": 1 + 2 + 4}


def test_header_zone(http_server, tmp_path):
    """The zone from a remote file's header: the NAD83 / UTM zone of its CRS when its bounds are the name's square;
    None for a file that is not there, one in no UTM zone or one off its square; an answer that keeps failing
    raises."""
    for name, args in (("good.tif", (12, 43, 449)), ("geo.tif", (12, 43, 449, "EPSG:4326")),
                       ("off.tif", (12, 43, 449, None, 1500.0))):
        _header_file(str(tmp_path / name), *args)
        with open(tmp_path / name, "rb") as f:
            http_server.add(f"/h/{name}", f.read(), "image/tiff")
    extent = [430000, 4480000, 440000, 4490000]
    assert tb.header_zone(http_server.url("/h/good.tif"), extent, str(tmp_path / "cache")) == 12
    assert tb.header_zone(http_server.url("/h/missing.tif"), extent, None) is None
    assert tb.header_zone(http_server.url("/h/geo.tif"), extent, None) is None
    assert tb.header_zone(http_server.url("/h/off.tif"), extent, None) is None
    http_server.add("/h/busy.tif", b"busy", "text/plain", status=403)  # (GDAL asks a 503 again itself, slowly)
    with pytest.raises(IndexUnavailable, match="busy.tif"):
        tb.header_zone(http_server.url("/h/busy.tif"), extent, None)
    assert {r.user_agent for r in http_server.log} == {cache.http_headers()["User-Agent"]}


# 4. The merge

def _unlisted(cache_dir, items):
    """A cached list of these items."""
    tb.write_list(tb.unlisted_path(cache_dir), {"made_at": cache.now_iso(), "files": len(items), "bytes": 0,
                                                "zone_in_name": 0, "zone_from_project": 0, "zone_from_header": 0,
                                                "bucket_files": 0, "listed": 0, "left_out": []},
                  items, "b", "a", "d")
    cache.record(cache_dir, tb.unlisted_path(cache_dir), url="b")
    tb.forget_unlisted()


def test_merge_when_an_answer_is_read(tmp_path, monkeypatch):
    """A tile's files: its cached answer plus the unlisted files reaching it whose URL the answer lacks (the same
    URL in both: once); the cached answer is not rewritten; a block over an unlisted file gets it (another key: read
    again, the older one deleted); has_data_near sees it; the list is read once for many tiles; Alaska's IfSAR
    layer merges nothing."""
    import grid as gd
    import osm
    tnm, files = FakeTnm(), tmp_path / "files"
    monkeypatch.setattr(requests, "get", tnm.get)
    _tile_1m(tnm, files, "CO_Full_2013", 1013)
    make = lambda: src.Usgs1mBlocks("Test 1 m", "Test DEM", "test1m", "usa/test1m", native_res=RES,  # noqa: E731
                                    block_m=1000, bytes_per_tile=1e4)
    layer, cache_dir = make(), str(tmp_path / "cache")
    grid = gd.make_grid((474100, 4424100, 475900, 4425900), RES, "EPSG:26913")
    layer.download(grid, cache_dir, None, "test")
    before = sorted(os.listdir(tmp_path / "cache" / "usa" / "test1m" / "epsg26913" / "47_442"))
    answers = sorted((tmp_path / "cache" / "usa" / "sheet-index" / "test1m").glob("*.json"))
    written = [a.read_bytes() for a in answers]

    # The list gains a newer file over the tile, and one already listed (same URL)
    newer = _tile_1m(FakeTnm(), files, "CO_New_2025", 1025, name="USGS_one_meter_x47y443_CO_New_2025.tif")
    listed = tnm.products[0]["downloadURL"]
    _unlisted(cache_dir, [tile_item(newer, 13, "2026-02-12T17:17:41.000Z"),
                          tile_item(listed, 13, "2026-02-12T17:17:41.000Z")])
    reads = tb.READS
    lat, lon = osm.tiles(*transform_bounds("EPSG:26913", "EPSG:4326", *grid.bounds))[0]
    items = make().index.answers(cache_dir, lat, lon)
    assert [i["name"] for i in items] == ["USGS_1M_13_x47y443_CO_Full_2013", "USGS_one_meter_x47y443_CO_New_2025"]
    assert items[1]["year"] == 2025 and items[1]["published"] == "2026-02-12T17:17:41.000Z"
    fresh = make()
    fresh._use(cache_dir, None)
    blocks = fresh.tiles(grid)
    assert len(blocks) == 4 and all([n for n, _, _ in b.files] == ["USGS_one_meter_x47y443_CO_New_2025",
                                                                   "USGS_1M_13_x47y443_CO_Full_2013"] for b in blocks)
    assert fresh.estimate(grid, cache_dir, None)[:2] == (4, 4)  # new keys: read again
    fresh.download(grid, cache_dir, None, "test")
    after = sorted(os.listdir(tmp_path / "cache" / "usa" / "test1m" / "epsg26913" / "47_442"))
    assert len(after) == 4 and not set(after) & set(before) and all(n.startswith("2025_") for n in after)
    mosaic = src.build_mosaic(fresh.files(grid, cache_dir), grid, str(tmp_path / "m.npy"), "test")
    assert (mosaic == 1025).all()
    assert [a.read_bytes() for a in answers] == written  # the cached answers as the index gave them
    assert tb.READS == reads + 1  # once for every tile and layer of this process and data folder

    # A place with only an unlisted file: has_data_near
    far = _tile_1m(FakeTnm(), files, "CO_Far_2021", 1021, x=40, y=443, name="USGS_1m_x40y443_CO_Far_2021.tif")
    west, south, east, north = transform_bounds("EPSG:26913", "EPSG:4326", 400000, 4420000, 410000, 4430000)
    assert make().has_data_near((south + north) / 2, (west + east) / 2, cache_dir) is False
    _unlisted(cache_dir, [tile_item(far, 13, "2026-04-01T00:00:00.000Z")])
    assert make().has_data_near((south + north) / 2, (west + east) / 2, cache_dir) is True

    # The IfSAR layer's index is a plain CachedIndex
    assert type(src.SOURCES["alaska_ifsar"].nmt.index) is CachedIndex
    assert type(src.SOURCES["usa"].nmt.index).__name__ == "UnlistedIndex"


def test_update_reads_blocks_of_a_new_unlisted_file(tmp_path, monkeypatch):
    """update_index_tile over a cached block: the list gained a file over it, so its set of files changed: read
    again, the older file deleted."""
    import grid as gd
    import osm
    tnm, files = FakeTnm(), tmp_path / "files"
    monkeypatch.setattr(requests, "get", tnm.get)
    _tile_1m(tnm, files, "CO_Full_2013", 1013)
    make = lambda: src.Usgs1mBlocks("Test 1 m", "Test DEM", "test1m", "usa/test1m", native_res=RES,  # noqa: E731
                                    block_m=1000, bytes_per_tile=1e4)
    cache_dir = str(tmp_path / "cache")
    grid = gd.make_grid((474100, 4424100, 475900, 4425900), RES, "EPSG:26913")
    make().download(grid, cache_dir, None, "test")
    newer = _tile_1m(FakeTnm(), files, "CO_New_2025", 1025, name="USGS_one_meter_x47y443_CO_New_2025.tif")
    _unlisted(cache_dir, [tile_item(newer, 13, "2026-02-12T17:17:41.000Z")])
    west, south, east, north = transform_bounds("EPSG:26913", "EPSG:4326", *grid.bounds)
    results = [make().update_index_tile(cache_dir, lat, lon) for lat, lon in osm.tiles(west, south, east, north)]
    assert sum(r[0] for r in results) == 4 and sum(r[2] for r in results) == 4
    folder = tmp_path / "cache" / "usa" / "test1m" / "epsg26913" / "47_442"
    assert len(os.listdir(folder)) == 4 and all(n.startswith("2025_") for n in os.listdir(folder))


def test_list_read_again_when_renewed(tmp_path, monkeypatch):
    """A process reads the list once; it looks again (a stat) only after RECHECK_S and reads it again only when it
    changed (a renewal by another process)."""
    cache_dir = str(tmp_path / "cache")
    one = tile_item("https://b/Projects/P/TIFF/USGS_1M_12_x43y449_P.tif", 12, "2026-01-01")
    two = tile_item("https://b/Projects/Q/TIFF/USGS_1M_12_x43y449_Q.tif", 12, "2026-01-02")
    _unlisted(cache_dir, [one])
    clock = [1000.0]
    monkeypatch.setattr(tb, "_now", lambda: clock[0])
    lat, lon = 40.5, -111.75
    reads = tb.READS
    assert [i["name"] for i in tb.unlisted_in_tile(cache_dir, "usa", lat, lon)] == ["USGS_1M_12_x43y449_P"]
    tb.write_list(tb.unlisted_path(cache_dir), {"made_at": "x", "files": 2, "bytes": 0, "zone_in_name": 0,
                                                "zone_from_project": 0, "zone_from_header": 0, "bucket_files": 0,
                                                "listed": 0, "left_out": []}, [one, two], "b", "a", "d")
    assert len(tb.unlisted_in_tile(cache_dir, "usa", lat, lon)) == 1 and tb.READS == reads + 1
    clock[0] += tb.RECHECK_S + 1
    assert len(tb.unlisted_in_tile(cache_dir, "usa", lat, lon)) == 2 and tb.READS == reads + 2
    clock[0] += tb.RECHECK_S + 1
    assert len(tb.unlisted_in_tile(cache_dir, "usa", lat, lon)) == 2 and tb.READS == reads + 2  # unchanged
    assert tb.unlisted_in_tile(cache_dir, "usa", lat, lon + 3) == []


# 5. The shipped copy

def test_shipped_copy():
    """The copy shipped with the code parses; every item has the fields of a TNM item, a zone, a 10 km extent and a
    URL of USGS's bucket, once each; the left-out names are a list."""
    with open(tb.SHIPPED, encoding="utf-8") as f:
        document = json.load(f)
    items = tb.read_list(tb.SHIPPED)
    assert items and len(items) == len(document["items"]) == document["counts"]["files"]
    assert isinstance(document["left_out"], list) and document["made_at"][:4] == "2026"
    assert len({i["url"] for i in items}) == len(items)
    for item in items:
        assert set(item) == set(tb.ITEM_KEYS)
        zone = int(item["crs"].split(":")[1]) - 26900
        assert item["crs"].startswith("EPSG:269") and 1 <= zone <= 23
        assert item["url"].startswith(f"{tb.BUCKET}/{tb.PROJECTS}") and item["url"].endswith(item["name"] + ".tif")
        left, bottom, right, top = item["extent"]
        assert right - left == 10000 and top - bottom == 10000 and item["extent"] == tile_extent(item["name"])
        named = tb.TILE_ZONE.match(item["name"])
        assert not named or int(named.group(1)) == zone
        assert 1990 < item["year"] <= 2030 and re.match(r"\d{4}-\d\d-\d\dT", item["published"])


def test_shipped_copy_used_without_a_cached_list(tmp_path, monkeypatch):
    """Without a cached list the shipped copy is read (unless turned off); a cached list wins over it."""
    shipped = str(tmp_path / "shipped.json")
    item = tile_item("https://b/Projects/P/TIFF/USGS_1M_12_x43y449_P.tif", 12, "2026-01-01")
    tb.write_list(shipped, {"made_at": "x", "files": 1, "bytes": 0, "zone_in_name": 1, "zone_from_project": 0,
                            "zone_from_header": 0, "bucket_files": 0, "listed": 0, "left_out": []}, [item], "b", "a", "d")
    monkeypatch.setattr(tb, "SHIPPED", shipped)
    cache_dir = str(tmp_path / "cache")
    assert tb.unlisted_in_tile(cache_dir, "usa", 40.5, -111.75) == []  # off in the tests (conftest)
    monkeypatch.setenv(tb.SHIPPED_ENV, "")
    tb.forget_unlisted()
    assert tb.unlisted_in_tile(cache_dir, "usa", 40.5, -111.75) == [item]
    assert tb.unlisted_age_days(cache_dir) == float("inf")
    _unlisted(cache_dir, [])
    assert tb.unlisted_in_tile(cache_dir, "usa", 40.5, -111.75) == []


# 8. The recorded answers (tools/record_answers.py, recipe bucket1m-usgs)

def test_recorded_bucket_and_index(http_server, tmp_path):
    """The recorded listing of one project of USGS's bucket and one box of the TNM index give the list the code
    that recorded them wrote, with the same requests and nothing else asked."""
    with open(os.path.join(RECORDED, "answers.json"), encoding="utf-8") as f:
        recorded = json.load(f)
    http_server.add_cassette(RECORDED)
    case = recorded["case"]
    cache_dir = str(tmp_path / "cache")
    tb.make_unlisted(cache_dir, bucket=http_server.base, api=http_server.url(API_PATH),
                     regions=[tuple(box) for box in case["regions"]], projects=case["projects"],
                     log=lambda text: None)
    with open(os.path.join(RECORDED, "expected.json"), encoding="utf-8") as f:
        expected = json.load(f)
    written = tb.read_list(tb.unlisted_path(cache_dir))
    host = "https://prd-tnm.s3.amazonaws.com"
    assert [{**i, "url": i["url"].replace(http_server.base, host)} for i in written] == expected["items"]
    assert len(written) > 0
    assert not http_server.stray()
    asked = [key_of(r.method, r.path + "?" + urlencode(r.query)) for r in http_server.log]
    wanted = [key_of(a["method"], urlsplit(a["url"])._replace(scheme="", netloc="").geturl())
              for a in recorded["answers"]]
    assert asked == wanted
    assert {r.user_agent for r in http_server.log} == {cache.http_headers()["User-Agent"]}
