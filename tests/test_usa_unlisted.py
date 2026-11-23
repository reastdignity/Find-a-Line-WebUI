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


def _serve(http_server, tmp_path, products_of=None, delay=0.0):
    """A bucket of four projects and an index listing some of their files, on the server; the files that need a
    header read served as GeoTIFFs; every answer after delay seconds (requests in flight at once can be seen).
    Returns the bucket's keys."""
    import time

    def later(answer):
        if answer is not None and delay:
            time.sleep(delay)
        return answer
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
    served = {}
    for name, key in (("a.tif", _key("CO_Two_2018", "USGS_one_meter_x24y443_CO_Two_2018.tif")),
                      ("b.tif", _key("AL_25Co_B1_2017", "USGS_1m_x38y372_AL_25Co_B1_2017.tif"))):
        with open(files / name, "rb") as f:
            served["/" + key] = f.read()
    http_server.route("/StagedProducts/", lambda request: later(
        Answer(200, served[request.path], {"Content-Type": "image/tiff"}) if request.path in served else None))
    http_server.route(API_PATH, lambda request: later(
        _tnm_answer(products_of() if products_of else products, request)))
    http_server.route("/", lambda request: later(_s3_answer(keys, request)) if request.path == "/" else None)
    return keys


def _most_at_once(asked, which) -> int:
    """The most requests of a server's log (which(request) true) it was answering at the same moment."""
    spans = [(r.started, r.ended or float("inf")) for r in asked if which(r)]
    events = sorted([(s, 1) for s, _ in spans] + [(e, -1) for _, e in spans])
    most = now = 0
    for _, step in events:
        now += step
        most = max(most, now)
    return most


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
    assert done["answer_bytes"]["bucket"] > 0 and done["answer_bytes"]["index"] > 0
    assert set(done["seconds_by_part"]) == {"bucket", "index", "headers"} and done["at_once"] == tb.REQUESTS_AT_ONCE
    items, wrong = tb.read_list(path)
    assert wrong == 0
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
    little: IndexUnavailable, and the list there was stays as it was; the last refused before any header is read."""
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
    assert not [r for r in http_server.log if r.path.endswith(".tif")]  # no header read before the guard
    with open(path, encoding="utf-8") as f:
        assert f.read() == '{"items": []}'


def test_header_reads_have_a_budget(http_server, tmp_path, monkeypatch):
    """One header read more than HEADER_READS is IndexUnavailable, and nothing is written."""
    _serve(http_server, tmp_path)
    monkeypatch.setattr(tb, "MAX_UNLISTED_SHARE", 1.0)
    monkeypatch.setattr(tb, "HEADER_READS", 2)  # 3 are needed
    cache_dir = str(tmp_path / "cache")
    with pytest.raises(IndexUnavailable, match="headers of the unlisted 1 m files: more than 2"):
        tb.make_unlisted(cache_dir, bucket=http_server.base, api=http_server.url(API_PATH),
                         regions=[(-125.0, 24.0, -66.0, 50.0)], log=lambda text: None, at_once=1)
    assert not os.path.exists(tb.unlisted_path(cache_dir))


def test_index_listing_clearly_fewer_files_than_before(http_server, tmp_path, monkeypatch):
    """The index listing fewer files than the list before recorded (its counts.listed) by more than MAX_LISTED_DROP
    is IndexUnavailable before any header is read, the list kept; allow_drop writes it."""
    _serve(http_server, tmp_path)
    monkeypatch.setattr(tb, "MAX_UNLISTED_SHARE", 1.0)
    cache_dir = str(tmp_path / "cache")
    path = tb.unlisted_path(cache_dir)
    tb.write_list(path, {"made_at": "x", "listed": 100, "left_out": []}, [], "b", "a", "d")
    with open(path, encoding="utf-8") as f:
        before = f.read()
    run = lambda **kw: tb.make_unlisted(cache_dir, bucket=http_server.base, api=http_server.url(API_PATH),  # noqa
                                        regions=[(-125.0, 24.0, -66.0, 50.0)], log=lambda text: None, **kw)
    with pytest.raises(IndexUnavailable, match="listed 4 1 m files, the list before 100"):
        run()
    assert not [r for r in http_server.log if r.path.endswith(".tif")]
    with open(path, encoding="utf-8") as f:
        assert f.read() == before
    assert tb.previous_listed(cache_dir) == 100
    assert run(allow_drop=True)["listed"] == 4 and tb.previous_listed(cache_dir) == 4
    tb.write_list(path, {"made_at": "x", "listed": 4, "left_out": []}, [], "b", "a", "d")  # 4 of 4: no drop
    assert run()["files"] == 4


def test_the_count_guard_heals_after_a_real_shrink(http_server, tmp_path, monkeypatch):
    """A refused listing records its count and time (refused.json); refused again within the day (the record keeps
    its time); accepted at least a day after it when the count agrees (the index did shrink), the record removed with
    the list written; a record that cannot be read is ignored (written anew)."""
    from datetime import datetime, timedelta, timezone
    _serve(http_server, tmp_path)
    monkeypatch.setattr(tb, "MAX_UNLISTED_SHARE", 1.0)
    cache_dir = str(tmp_path / "cache")
    tb.write_list(tb.unlisted_path(cache_dir), {"made_at": "x", "listed": 100, "left_out": []}, [], "b", "a", "d")
    record = tb.refused_path(cache_dir)
    t0 = datetime(2026, 11, 23, 8, 0, tzinfo=timezone.utc)
    clock = [t0]
    monkeypatch.setattr(tb, "_utc_now", lambda: clock[0])
    run = lambda: tb.make_unlisted(cache_dir, bucket=http_server.base, api=http_server.url(API_PATH),  # noqa: E731
                                   regions=[(-125.0, 24.0, -66.0, 50.0)], log=lambda text: None)
    with pytest.raises(IndexUnavailable, match="listed 4 1 m files, the list before 100"):
        run()
    with open(record, encoding="utf-8") as f:
        assert json.load(f) == {"listed": 4, "at": "2026-11-23T08:00:00+00:00"}
    clock[0] = t0 + timedelta(hours=20)
    with pytest.raises(IndexUnavailable, match="the list before 100"):
        run()
    with open(record, encoding="utf-8") as f:
        assert json.load(f)["at"] == "2026-11-23T08:00:00+00:00"  # within the day: the first time kept
    clock[0] = t0 + timedelta(hours=25)
    assert run()["listed"] == 4 and not os.path.exists(record) and tb.previous_listed(cache_dir) == 4
    # an unreadable record is ignored: refused, the record written anew
    tb.write_list(tb.unlisted_path(cache_dir), {"made_at": "x", "listed": 100, "left_out": []}, [], "b", "a", "d")
    with open(record, "w", encoding="utf-8") as f:
        f.write("{not json")
    with pytest.raises(IndexUnavailable, match="the list before 100"):
        run()
    with open(record, encoding="utf-8") as f:
        assert json.load(f)["listed"] == 4
    # a record of another count (a day old) does not confirm this one: refused, the record renewed
    with open(record, "w", encoding="utf-8") as f:
        json.dump({"listed": 50, "at": "2026-11-20T08:00:00+00:00"}, f)
    with pytest.raises(IndexUnavailable):
        run()
    with open(record, encoding="utf-8") as f:
        assert json.load(f) == {"listed": 4, "at": (t0 + timedelta(hours=25)).isoformat()}


def test_previous_listed_falls_back_to_the_shipped_copy(tmp_path, monkeypatch):
    """The count the guard compares with: the cached list's, else (none, or one that cannot be used) the shipped
    copy's, unless the shipped copy is off."""
    cache_dir = str(tmp_path / "cache")
    assert tb.previous_listed(cache_dir) is None  # the shipped copy off (conftest), no cached list
    _shipped(tmp_path, monkeypatch, [ONE])        # its counts.listed: 1
    assert tb.previous_listed(cache_dir) == 1
    os.makedirs(os.path.dirname(tb.unlisted_path(cache_dir)))
    with open(tb.unlisted_path(cache_dir), "w", encoding="utf-8") as f:
        f.write('{"counts": {"listed": 0}}')
    assert tb.previous_listed(cache_dir) == 1
    tb.write_list(tb.unlisted_path(cache_dir), {"made_at": "x", "listed": 7, "left_out": []}, [], "b", "a", "d")
    assert tb.previous_listed(cache_dir) == 7


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


def _tnm_pages(boxes, asked, dropped=None, short=None):
    """requests.get of the TNM index as its answers of 2026-11-23 show it: a box's `total` counts some products
    twice (positions: the products in the API's order, a file listed as two products appearing twice), a page
    returns its positions as they are (a page of 4 items may hold 3 distinct URLs). dropped: (box, offset) -> how
    many times that page comes back empty first (a dropped page); short: (box, offset) pages that come back one
    item short (2 of 151 boxes did so on 2026-11-23)."""
    dropped, short = dict(dropped or {}), set(short or ())

    def fake(url, params=None, headers=None, **kwargs):
        box, offset = tuple(float(v) for v in params["bbox"].split(",")), int(params["offset"])
        asked.append((box, offset))
        assert headers["User-Agent"] == cache.http_headers()["User-Agent"]
        positions = boxes.get(box, [])
        items = positions[offset:offset + int(params["max"])]
        if (box, offset) in short:
            items = items[:-1]
        if dropped.get((box, offset)):
            dropped[(box, offset)] -= 1
            items = []
        response = requests.Response()
        response.status_code, response._content = 200, json.dumps(
            {"total": len(positions), "items": [{"downloadURL": u} for u in items]}).encode()
        return response
    return fake


P9 = [f"https://x/Projects/P/TIFF/USGS_1M_12_x{i}y1_P.tif" for i in range(9)]
REGION = (0.0, 0.0, 8.0, 8.0)
QUARTERS = [(0.0, 0.0, 4.0, 4.0), (4.0, 0.0, 8.0, 4.0), (0.0, 4.0, 4.0, 8.0), (4.0, 4.0, 8.0, 8.0)]


def test_tnm_listing_in_small_boxes(monkeypatch):
    """The index asked over the regions: a box that holds more than SPLIT_ABOVE is asked as its quarters (no deep
    offsets); the API's double counting (a URL twice in a page, a page short by one) is no error: the next page
    starts after the items that came, repeats included, a short page is asked again once, the distinct URLs are
    kept; more pages than the budget: an error."""
    monkeypatch.setattr(tb, "SPLIT_ABOVE", 6)
    monkeypatch.setattr(tb, "TNM_PAGE", 4)
    asked = []
    p = P9
    boxes = {REGION: p[:9],                                        # the region: 9 products, more than 6
             QUARTERS[0]: [p[0], p[1], p[0], p[2], p[3], p[4]],    # a quarter: 6 said, 5 distinct
             QUARTERS[1]: [p[5], p[6], p[7], p[8]]}                # the quarters say 10 >= 9: whole
    monkeypatch.setattr(requests, "get", _tnm_pages(boxes, asked, short={(QUARTERS[1], 0)}))
    found = tb.tnm_listed(None, "https://tnm.example/api", "Test DEM", [REGION])
    assert sorted(found) == sorted(p)
    # the first quarter: 4 items (3 distinct) at offset 0, the last 2 at offset 4; the second: 3 of 4, asked again
    # (3 again), the last one at offset 3
    assert [o for b, o in asked if b == QUARTERS[0]] == [0, 4]
    assert [o for b, o in asked if b == QUARTERS[1]] == [0, 0, 3]
    assert [b for b, _ in asked].count(REGION) == 1 and len({b for b, _ in asked}) == 5
    with pytest.raises(IndexUnavailable, match="more than 3 pages"):
        tb.tnm_listed(None, "https://tnm.example/api", "Test DEM", [REGION], PageBudget("TNM", 3))


def test_tnm_listing_a_dropped_page(monkeypatch):
    """A page that comes back empty before the box's `total` is reached is no double counting but a dropped page:
    asked again once (it comes: the box is whole), then IndexUnavailable, never a box ended early."""
    monkeypatch.setattr(tb, "TNM_PAGE", 4)
    p = [f"https://x/Projects/P/TIFF/USGS_1M_12_x{i}y1_P.tif" for i in range(12)]
    box = (0.0, 0.0, 1.0, 1.0)
    asked = []
    monkeypatch.setattr(requests, "get", _tnm_pages({box: p}, asked, {(box, 4): 1}))
    assert sorted(tb.tnm_listed(None, "https://tnm.example/api", "Test DEM", [box])) == sorted(p)
    assert [o for _, o in asked] == [0, 4, 4, 8]
    monkeypatch.setattr(requests, "get", _tnm_pages({box: p}, [], {(box, 4): 2}))
    with pytest.raises(IndexUnavailable, match="empty page at offset 4 of 12"):
        tb.tnm_listed(None, "https://tnm.example/api", "Test DEM", [box])


def _answering(statuses, pages):
    """requests.get answering these statuses first (one each), then as pages."""
    calls = []

    def get(url, params=None, **kwargs):
        calls.append(params["offset"])
        if len(calls) <= len(statuses):
            response = requests.Response()
            response.status_code, response._content, response.url = statuses[len(calls) - 1], b"busy", url
            return response
        return pages(url, params=params, **kwargs)
    return get, calls


def test_tnm_page_asked_again_while_it_fails(monkeypatch):
    """A page of the index answering 500 is asked again: 5 failures then the answer (a renewal met three 500s in a
    row on 2026-11-23), 6 failures are IndexUnavailable."""
    box = (0.0, 0.0, 1.0, 1.0)
    pages = _tnm_pages({box: ["https://x/Projects/P/TIFF/USGS_1M_12_x1y1_P.tif"]}, [])
    get, calls = _answering([500] * 5, pages)
    monkeypatch.setattr(requests, "get", get)
    assert len(tb.tnm_listed(None, "https://tnm.example/api", "Test DEM", [box])) == 1 and len(calls) == 6
    get, calls = _answering([500] * 6, pages)
    monkeypatch.setattr(requests, "get", get)
    with pytest.raises(IndexUnavailable, match="500"):
        tb.tnm_listed(None, "https://tnm.example/api", "Test DEM", [box])


def test_tnm_page_answers_by_status(monkeypatch):
    """A 429 or a 503 backs off longer (net._sleep(attempt + 3), as net._get does); another 4xx is IndexUnavailable
    at once, never asked again; a 500 after the usual pause."""
    box = (0.0, 0.0, 1.0, 1.0)
    pages = _tnm_pages({box: ["https://x/Projects/P/TIFF/USGS_1M_12_x1y1_P.tif"]}, [])
    pauses = []
    monkeypatch.setattr(src.net, "_sleep", pauses.append)
    get, calls = _answering([429, 503, 500], pages)
    monkeypatch.setattr(requests, "get", get)
    assert len(tb.tnm_listed(None, "https://tnm.example/api", "Test DEM", [box])) == 1
    assert pauses == [3, 4, 2] and len(calls) == 4
    for status in (400, 403, 404):
        get, calls = _answering([status], pages)
        monkeypatch.setattr(requests, "get", get)
        with pytest.raises(IndexUnavailable, match=f"HTTP {status}"):
            tb.tnm_listed(None, "https://tnm.example/api", "Test DEM", [box])
        assert len(calls) == 1


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
    items, left_out, counts, upload_projects = tb.unlisted_from(objects, listed, header, "https://b")
    assert upload_projects == []
    assert {i["name"]: i["crs"] for i in items} == {"USGS_1M_10_x51y500_OR_A_2019": "EPSG:26910",
                                                    "USGS_one_meter_x43y449_UT_B_2013": "EPSG:26912",
                                                    "USGS_1m_x38y372_AL_C_2017": "EPSG:26916"}
    # x93 in zone 12 lies 500 km east of the project's box: its header was asked (and gave nothing)
    assert asked == ["USGS_one_meter_x93y449_UT_B_2013.tif", "USGS_1m_x38y372_AL_C_2017.tif",
                     "USGS_1m_x38y373_AL_C_2017.tif"]
    assert left_out == ["USGS_1m_x38y373_AL_C_2017.tif", "USGS_one_meter_x93y449_UT_B_2013.tif"]
    assert counts == {"zone_in_name": 1, "zone_from_project": 1, "zone_from_header": 1, "bytes": 1 + 2 + 4}


def test_year_of_a_project_whose_folder_names_none():
    """A file of a project whose folders name no year takes the year its project's listed files carry (the most
    frequent; ND_Lidar_Phase10's listed 2024, its unlisted uploaded in 2026), published its upload time; only a
    project without a listed file keeps the upload year, counted and named."""
    def listed_url(project, name):
        return f"https://b/{tb.PROJECTS}{project}/TIFF/{name}"
    listed = {}
    for name, published in (("USGS_1M_14_x40y520_ND_Lidar_Phase10.tif", "2024-03-01"),
                            ("USGS_1M_14_x41y520_ND_Lidar_Phase10.tif", "2024-05-01"),
                            ("USGS_1M_14_x42y520_ND_Lidar_Phase10.tif", "2023-01-01")):
        url = listed_url("ND_Lidar_Phase10", name)
        listed[url] = {**_product(url, 14, 40, 520), "publicationDate": published}
    objects = [S3Object(_key("ND_Lidar_Phase10", "USGS_1M_14_x43y520_ND_Lidar_Phase10.tif"), 1,
                        "2026-02-14T10:00:00.000Z", ""),
               S3Object(_key("XX_No_Year_Listed", "USGS_1M_14_x43y521_XX_No_Year_Listed.tif"), 2,
                        "2026-04-21T10:00:00.000Z", ""),
               S3Object(_key("ND_Phase11_C24", "USGS_1M_14_x43y520_ND_Phase11_C24.tif"), 3,
                        "2026-02-14T10:00:00.000Z", "")]
    items, left_out, counts, upload_projects = tb.unlisted_from(objects, listed, lambda url, extent: None, "https://b")
    assert {i["name"]: (i["year"], i["published"]) for i in items} == {
        "USGS_1M_14_x43y520_ND_Lidar_Phase10": (2024, "2026-02-14T10:00:00.000Z"),
        "USGS_1M_14_x43y521_XX_No_Year_Listed": (2026, "2026-04-21T10:00:00.000Z"),
        "USGS_1M_14_x43y520_ND_Phase11_C24": (2024, "2026-02-14T10:00:00.000Z")}
    assert counts["year_from_siblings"] == 1 and counts["year_from_upload"] == 1
    assert upload_projects == ["XX_No_Year_Listed"]


EXTENT = [430000, 4480000, 440000, 4490000]  # x43 y449


def _served_header(http_server, tmp_path, name, *args, **kwargs):
    _header_file(str(tmp_path / name), *args, **kwargs)
    with open(tmp_path / name, "rb") as f:
        http_server.add(f"/h/{name}", f.read(), "image/tiff")
    return http_server.url(f"/h/{name}")


def test_header_zone(http_server, tmp_path, monkeypatch):
    """The zone from a remote file's header: the NAD83 / UTM zone of its CRS when its bounds are the name's square,
    read with our User-Agent under a host slot."""
    url = _served_header(http_server, tmp_path, "good.tif", 12, 43, 449)
    turns = []
    original = src.net.rate_turn
    monkeypatch.setattr(src.net, "rate_turn", lambda u, *a, **k: (turns.append(u), original(u, *a, **k))[1])
    assert tb.header_zone(url, EXTENT, str(tmp_path / "cache")) == 12
    assert {r.user_agent for r in http_server.log} == {cache.http_headers()["User-Agent"]}
    assert turns == [url]  # its rate turn, as every request


def test_refused_status_pattern():
    """Only the HTTP status as GDAL reports it is a refusal: not curl's "after 403 ms" nor a name's x40y404."""
    assert tb.REFUSED_STATUS.search("HTTP response code: 404").group(1) == "404"
    assert tb.REFUSED_STATUS.search("x.tif: HTTP response code: 403; more").group(1) == "403"
    for text in ("CURL error: Failed to connect to 127.0.0.1 port 1 after 403 ms: Could not connect",
                 "Operation timed out with 404 out of 16384 bytes received", "USGS_1m_x40y404_P.tif: busy",
                 "HTTP response code: 4031", "HTTP response code: 500"):
        assert tb.REFUSED_STATUS.search(text) is None, text


@pytest.mark.parametrize("keep", [8, 100])
def test_header_cut_short_is_asked_again(http_server, tmp_path, keep):
    """A header read whose answer is cut short (after 8 or 100 bytes: GDAL says TIFFReadDirectory) is no definite
    answer: GDAL's ranges forgotten, the file's first bytes show a TIFF, the read made again: the zone."""
    url = _served_header(http_server, tmp_path, "cut.tif", 12, 43, 449)
    http_server.fault("/h/cut.tif", "truncate", lambda n, r: n == 1, keep=keep)
    assert tb.header_zone(url, EXTENT, None) == 12


def test_header_that_stays_cut_stops_the_list(http_server, tmp_path):
    """A header whose every read is cut short (the small range request of the first bytes comes whole: a TIFF) is
    asked again net.RETRIES times, then IndexUnavailable: never taken for "not a TIFF"."""
    url = _served_header(http_server, tmp_path, "cut.tif", 12, 43, 449)
    http_server.fault("/h/cut.tif", "truncate", lambda n, r: r != "bytes=0-7", keep=8)
    with pytest.raises(IndexUnavailable, match="cut.tif"):
        tb.header_zone(url, EXTENT, None)
    assert len([r for r in http_server.requests("/h/cut.tif") if r.headers.get("range") == "bytes=0-7"]) == \
        src.net.RETRIES


def _no_crs_file(path):
    with rio.open(path, "w", driver="GTiff", width=20, height=20, count=1, dtype="float32",
                  transform=from_origin(429994, 4490006, 500.6, 500.6)) as dst:
        dst.write(np.full((20, 20), 1000.0, np.float32), 1)


@pytest.mark.parametrize("kind", ["404", "403", "not a TIFF", "no CRS", "not NAD83 UTM", "off its square"])
def test_header_definite_answers_leave_the_file_out(http_server, tmp_path, kind):
    """A definite answer of a header is None (the file left out and named), never an error that stops the list: not
    there, refused, not a TIFF, without a CRS, in no NAD83 / UTM zone, bounds off the name's square."""
    if kind == "404":
        url = http_server.url("/h/missing.tif")
    elif kind == "403":
        http_server.add("/h/refused.tif", b"<Error><Code>AccessDenied</Code></Error>", "application/xml", status=403)
        url = http_server.url("/h/refused.tif")
    elif kind == "not a TIFF":
        http_server.add("/h/page.tif", b"<html>a page, not a TIFF</html>" * 20, "text/html")
        url = http_server.url("/h/page.tif")
    elif kind == "no CRS":
        _no_crs_file(str(tmp_path / "nocrs.tif"))
        with open(tmp_path / "nocrs.tif", "rb") as f:
            http_server.add("/h/nocrs.tif", f.read(), "image/tiff")
        url = http_server.url("/h/nocrs.tif")
    elif kind == "not NAD83 UTM":
        url = _served_header(http_server, tmp_path, "geo.tif", 12, 43, 449, crs="EPSG:4326")
    else:
        url = _served_header(http_server, tmp_path, "off.tif", 12, 43, 449, shift=1500.0)
    assert tb.header_zone(url, EXTENT, None) is None


@pytest.mark.parametrize("kind", ["5xx", "connection closed"])
def test_header_failures_that_may_pass_stop_the_list(http_server, tmp_path, monkeypatch, kind):
    """A header failure that may pass (a 5xx, a connection closed without an answer) is asked again, then
    IndexUnavailable; a name holding "404" (a northing of 4,040 km) is no "not there"."""
    monkeypatch.setattr(src.net, "RETRIES", 1)  # GDAL's own retries too: one, after 2 s
    name = "USGS_1m_x40y404_P.tif"
    if kind == "5xx":
        http_server.add(f"/h/{name}", b"busy", "text/plain", status=500)
    else:
        _served_header(http_server, tmp_path, name, 12, 40, 404)
        http_server.fault(f"/h/{name}", "close", lambda n, r: True, plain=True)
    with pytest.raises(IndexUnavailable, match="x40y404"):
        tb.header_zone(http_server.url(f"/h/{name}"), [400000, 4030000, 410000, 4040000], None)


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
    asked = list(tnm.asked)

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
    assert tnm.asked == asked  # a search with cached answers asks the index nothing, the list or not
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


def _shipped(tmp_path, monkeypatch, items):
    """A stand-in shipped copy of these items, switched on."""
    shipped = str(tmp_path / "shipped.json")
    tb.write_list(shipped, {"made_at": "x", "listed": 1, "left_out": []}, items, "b", "a", "d")
    monkeypatch.setattr(tb, "SHIPPED", shipped)
    monkeypatch.setenv(tb.SHIPPED_ENV, "")
    tb.forget_unlisted()


ONE = tile_item("https://b/Projects/P/TIFF/USGS_1M_12_x43y449_P.tif", 12, "2026-01-01")
TWO = tile_item("https://b/Projects/Q/TIFF/USGS_1M_12_x43y449_Q.tif", 12, "2026-01-02")


@pytest.mark.parametrize("content", ["not JSON", "cut short", "[]", "items not a list", "extent null"])
def test_a_cached_list_that_cannot_be_used(tmp_path, monkeypatch, capsys, content):
    """Whatever the cached list holds, reading the 1 m layer never fails because of it: one printed line, the shipped
    copy instead, remembered as a good read (no read per tile); a wrong item in a list otherwise right is dropped
    and counted in that line."""
    _shipped(tmp_path, monkeypatch, [TWO])
    cache_dir = str(tmp_path / "cache")
    path = tb.unlisted_path(cache_dir)
    _unlisted(cache_dir, [ONE])
    with open(path, encoding="utf-8") as f:
        good = f.read()
    text = {"not JSON": "this is no list", "cut short": good[:len(good) // 2], "[]": "[]",
            "items not a list": '{"items": 5}',
            "extent null": good.replace('"extent": [430000', '"extent": null, "x": [430000')}[content]
    if content == "extent null":  # a second, good item beside the broken one
        text = text.replace('"items": [\n', '"items": [\n' + json.dumps(TWO) + ",\n")
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    tb.forget_unlisted()
    reads = tb.READS
    found = [tb.unlisted_in_tile(cache_dir, "usa", 40.5, -111.75) for _ in range(5)]
    assert all(f == [TWO] for f in found)  # the shipped copy's (or the good item's) file
    out = capsys.readouterr().out
    if content == "extent null":
        assert out.count("1 of its items are no 1 m file") == 1 and tb.READS == reads + 1
    else:
        assert out.count("cannot be used") == 1 and "the shipped copy is read instead" in out
        assert tb.READS <= reads + 2  # the cached list tried once, the shipped copy once
    # the layer's answers work on (no exception out of UnlistedIndex.answers)
    layer = src.Usgs1mBlocks("Test 1 m", "Test DEM", "test1m", "usa/test1m", native_res=RES, block_m=1000,
                             bytes_per_tile=1e4)
    monkeypatch.setattr(requests, "get", FakeTnm().get)
    assert [i["name"] for i in layer.index.answers(cache_dir, 40.5, -111.75)] == [TWO["name"]]


def test_list_write_failure_keeps_the_list(tmp_path, monkeypatch):
    """A failure to put the written list in its place is IndexUnavailable, the temporary file removed and the list
    there was kept (an open-and-write in place would have changed it)."""
    cache_dir = str(tmp_path / "cache")
    path = tb.unlisted_path(cache_dir)
    _unlisted(cache_dir, [ONE])
    with open(path, encoding="utf-8") as f:
        before = f.read()

    def refused(a, b):
        raise PermissionError(13, "The process cannot access the file", b)
    monkeypatch.setattr(os, "replace", refused)
    with pytest.raises(IndexUnavailable, match="could not be written"):
        tb.write_list(path, {"made_at": "y", "left_out": []}, [ONE, TWO], "b", "a", "d")
    monkeypatch.undo()
    with open(path, encoding="utf-8") as f:
        assert f.read() == before
    assert [n for n in os.listdir(os.path.dirname(path))] == ["unlisted.json"]


@pytest.mark.skipif(sys.platform != "win32", reason="only Windows refuses to replace a file another handle holds")
def test_list_write_while_another_process_holds_it(tmp_path):
    """On Windows a list held open (a reader) cannot be replaced: IndexUnavailable, no .part, the old list kept."""
    cache_dir = str(tmp_path / "cache")
    path = tb.unlisted_path(cache_dir)
    _unlisted(cache_dir, [ONE])
    with open(path, encoding="utf-8") as held:
        before = held.read()
        with pytest.raises(IndexUnavailable, match="could not be written"):
            tb.write_list(path, {"made_at": "y", "left_out": []}, [ONE, TWO], "b", "a", "d")
    with open(path, encoding="utf-8") as f:
        assert f.read() == before
    assert os.listdir(os.path.dirname(path)) == ["unlisted.json"]


# 7. Several requests at a time

def test_several_requests_at_a_time_give_the_same_list(http_server, tmp_path, monkeypatch):
    """The three parts 4 requests at a time give the list one at a time gives: the same items, the same counts; and
    4 at a time the server sees more than one request of each part in flight (one at a time, never)."""
    _serve(http_server, tmp_path, delay=0.05)
    monkeypatch.setattr(tb, "MAX_UNLISTED_SHARE", 1.0)
    cache_dir = str(tmp_path / "cache")
    runs, peaks = {}, {}
    parts = {"bucket": lambda r: r.path == "/" and "TIFF" in dict(r.query).get("prefix", ""),
             "index": lambda r: r.path == API_PATH, "headers": lambda r: r.path.endswith(".tif")}
    import rasterio.cache
    for at_once in (1, 4):
        out = str(tmp_path / f"list-{at_once}.json")
        for key in ("CO_Two_2018/TIFF/USGS_one_meter_x24y443_CO_Two_2018.tif",
                    "AL_25Co_B1_2017/TIFF/USGS_1m_x38y372_AL_25Co_B1_2017.tif"):  # GDAL's ranges of the run before
            rasterio.cache.invalidate(f"{http_server.base}/{tb.PROJECTS}{key}")
        first = len(http_server.log)
        done = tb.make_unlisted(cache_dir, out=out, bucket=http_server.base, api=http_server.url(API_PATH),
                                regions=[(-125.0, 24.0, -95.0, 50.0), (-95.0, 24.0, -66.0, 50.0)],
                                log=lambda text: None, at_once=at_once)
        asked = http_server.log[first:]
        peaks[at_once] = {name: _most_at_once(asked, which) for name, which in parts.items()}
        with open(out, encoding="utf-8") as f:
            document = json.load(f)
        runs[at_once] = (document["items"], document["counts"], document["left_out"],
                         {k: v for k, v in done["requests"].items()})
    assert runs[1] == runs[4] and len(runs[4][0]) == 4
    assert peaks[1] == {"bucket": 1, "index": 1, "headers": 1}
    assert all(peak > 1 for peak in peaks[4].values()), peaks[4]


def test_a_failing_request_stops_the_others(http_server, tmp_path, monkeypatch):
    """A project of the bucket whose listing keeps failing stops the listing of the others (not all are asked) and
    leaves the list there was; so does a header read failing inside make_unlisted."""
    import time
    keys = [(_key(f"P{i:02d}_2020", f"USGS_1M_12_x{i}y1_P{i:02d}_2020.tif"), 1, "2026-01-01T00:00:00.000Z")
            for i in range(40)]

    def bucket(request):
        prefix = dict(request.query).get("prefix", "")
        if "P05_2020" in prefix:
            return Answer(500, b"<Error><Code>InternalError</Code><Message>x</Message></Error>")
        time.sleep(0.05)
        return _s3_answer(keys, request)
    http_server.route("/", lambda request: bucket(request) if request.path == "/" else None)
    cache_dir = str(tmp_path / "cache")
    _unlisted(cache_dir, [ONE])
    with open(tb.unlisted_path(cache_dir), encoding="utf-8") as f:
        before = f.read()
    with pytest.raises(IndexUnavailable, match="HTTP 500"):
        tb.make_unlisted(cache_dir, bucket=http_server.base, api=http_server.url(API_PATH), log=lambda text: None,
                         at_once=4)
    listed = {dict(r.query)["prefix"] for r in http_server.log if "TIFF" in dict(r.query).get("prefix", "")}
    assert len(listed) < 40
    with open(tb.unlisted_path(cache_dir), encoding="utf-8") as f:
        assert f.read() == before


def test_ctrl_c_stops_a_part(monkeypatch):
    """A KeyboardInterrupt in the calling thread while a part runs 4 at a time (its wait) sets the stop, drops the
    tasks not started and is raised once the tasks in flight have ended: fewer tasks ran than were queued."""
    import threading
    import time
    ran, lock = [], threading.Lock()

    def task(n):
        time.sleep(0.1)  # one request
        with lock:
            ran.append(n)
        return n
    real, calls = tb.wait, []

    def interrupted(*args, **kwargs):  # Ctrl+C while the caller waits, after its first look
        calls.append(1)
        result = real(*args, **kwargs)
        if len(calls) == 1:
            raise KeyboardInterrupt
        return result
    monkeypatch.setattr(tb, "wait", interrupted)
    monkeypatch.setattr(tb, "WAIT_POLL_S", 0.15)
    stop = threading.Event()
    with pytest.raises(KeyboardInterrupt):
        tb._all(task, list(range(40)), 4, stop)
    assert stop.is_set() and len(ran) < 40
    done = len(ran)
    time.sleep(0.3)
    assert len(ran) == done  # nothing runs on after the caller left


def test_sibling_year_tie():
    """Of two years its listed files carry as often, a project's year is the newer."""
    import collections
    assert tb._sibling_year(collections.Counter({2023: 2, 2024: 2, 2019: 1})) == 2024
    assert tb._sibling_year(collections.Counter({2023: 3, 2024: 2})) == 2023


def test_a_header_failing_inside_make_unlisted(http_server, tmp_path, monkeypatch):
    """A header read that keeps failing (a 5xx) inside make_unlisted is IndexUnavailable, the list kept."""
    _serve(http_server, tmp_path)
    monkeypatch.setattr(tb, "MAX_UNLISTED_SHARE", 1.0)
    monkeypatch.setattr(src.net, "RETRIES", 1)
    http_server.add("/" + _key("AL_25Co_B1_2017", "USGS_1m_x38y372_AL_25Co_B1_2017.tif"), b"busy", "text/plain",
                    status=503)
    cache_dir = str(tmp_path / "cache")
    _unlisted(cache_dir, [ONE])
    with open(tb.unlisted_path(cache_dir), encoding="utf-8") as f:
        before = f.read()
    with pytest.raises(IndexUnavailable, match="x38y372"):
        tb.make_unlisted(cache_dir, bucket=http_server.base, api=http_server.url(API_PATH),
                         regions=[(-125.0, 24.0, -66.0, 50.0)], log=lambda text: None)
    with open(tb.unlisted_path(cache_dir), encoding="utf-8") as f:
        assert f.read() == before


# 8. Behaviours of their own

def test_out_writes_no_row(http_server, tmp_path, monkeypatch):
    """With out= the list goes there (the shipped copy's way): no cached list, no row in the index."""
    _serve(http_server, tmp_path)
    monkeypatch.setattr(tb, "MAX_UNLISTED_SHARE", 1.0)
    cache_dir, out = str(tmp_path / "cache"), str(tmp_path / "elsewhere" / "list.json")
    done = tb.make_unlisted(cache_dir, out=out, bucket=http_server.base, api=http_server.url(API_PATH),
                            regions=[(-125.0, 24.0, -66.0, 50.0)], log=lambda text: None)
    assert done["path"] == out and len(tb.read_list(out)[0]) == 4
    assert not os.path.exists(tb.unlisted_path(cache_dir)) and cache.info(cache_dir, tb.unlisted_path(cache_dir)) is None


def test_the_list_under_threads(tmp_path, monkeypatch):
    """Many threads asking tiles while the list is replaced again and again: never an error, each answer one of the
    lists."""
    import threading
    cache_dir = str(tmp_path / "cache")
    _unlisted(cache_dir, [ONE])
    monkeypatch.setattr(tb, "RECHECK_S", 0)  # every ask looks at the file
    errors, seen = [], set()

    def ask():
        try:
            for _ in range(200):
                seen.add(len(tb.unlisted_in_tile(cache_dir, "usa", 40.5, -111.75)))
        except Exception as e:  # noqa: BLE001
            errors.append(e)
    threads = [threading.Thread(target=ask) for _ in range(8)]
    for t in threads:
        t.start()
    written = 0
    while written < 30:  # on Windows a reader holding the file makes a write fail now and then (F4): written again
        try:
            tb.write_list(tb.unlisted_path(cache_dir), {"made_at": str(written), "left_out": []},
                          [ONE, TWO][:1 + written % 2], "b", "a", "d")
            written += 1
        except IndexUnavailable:
            pass
    for t in threads:
        t.join()
    assert not errors and seen <= {1, 2}


def test_a_file_reaching_two_index_tiles(tmp_path):
    """A file whose square crosses the edges of 0.25° index tiles is in each of their answers, and a block over it
    has one key whichever tile's files make it."""
    from sources.indexes.versions import ComposedBlocks
    cache_dir = str(tmp_path / "cache")
    _unlisted(cache_dir, [ONE])  # x43 y449 of zone 12: 40.47-40.56 N, 111.83-111.71 W
    corners = [(40.25, -112.0), (40.25, -111.75), (40.5, -112.0), (40.5, -111.75)]
    answers = [tb.unlisted_in_tile(cache_dir, "usa", lat, lon) for lat, lon in corners]
    assert all(a == [ONE] for a in answers)
    assert tb.unlisted_in_tile(cache_dir, "usa", 40.75, -111.75) == []
    versions = ComposedBlocks("usa/test1m", 1000, 1.0)
    bounds = {"EPSG:26912": (434000, 4484000, 436000, 4486000)}
    keys = {tuple(b.key for b in versions._blocks(a, bounds)) for a in answers}
    assert len(keys) == 1 and len(next(iter(keys))) == 4


def test_the_tool_against_a_stand_in(http_server, tmp_path, monkeypatch, capsys):
    """tools/usa_unlisted.py makes the list from a bucket and an index given, prints what it did and the files left
    out."""
    sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
    import usa_unlisted
    _serve(http_server, tmp_path)
    monkeypatch.setattr(tb, "MAX_UNLISTED_SHARE", 1.0)
    out = str(tmp_path / "shipped.json")
    assert usa_unlisted.main(["--cache", str(tmp_path / "cache"), "--out", out, "--bucket", http_server.base,
                              "--api", http_server.url(API_PATH)]) == 0
    printed = capsys.readouterr().out
    assert '"files": 4' in printed and "left out (1): USGS_1m_x99y999_AL_25Co_B1_2017.tif" in printed
    assert "dated by their upload (0 files): -" in printed
    assert len(tb.read_list(out)[0]) == 4
    # --cached --allow-drop: a cache's own list (with its row) made in spite of a drop of the index's count
    cache_dir = str(tmp_path / "cache")
    tb.write_list(tb.unlisted_path(cache_dir), {"made_at": "x", "listed": 100, "left_out": []}, [], "b", "a", "d")
    args = ["--cache", cache_dir, "--cached", "--bucket", http_server.base, "--api", http_server.url(API_PATH)]
    with pytest.raises(IndexUnavailable, match="the list before 100"):
        usa_unlisted.main(args)
    assert usa_unlisted.main(args + ["--allow-drop"]) == 0
    assert tb.previous_listed(cache_dir) == 4 and cache.info(cache_dir, tb.unlisted_path(cache_dir)) is not None
    assert not os.path.exists(tb.refused_path(cache_dir))


# 5. The shipped copy

def test_shipped_copy():
    """The copy shipped with the code parses; every item has the fields of a TNM item, a zone, a 10 km extent and a
    URL of USGS's bucket, once each; the left-out names are a list."""
    from sources.layers.tnm import folder_year
    with open(tb.SHIPPED, encoding="utf-8") as f:
        document = json.load(f)
    items, wrong = tb.read_list(tb.SHIPPED)
    assert items and not wrong and len(items) == len(document["items"]) == document["counts"]["files"]
    # A year that is the upload's only where the project has no listed file (named in the list's head): not the 49
    # files of ND_Lidar_Phase10 and Maine_and_Massachusetts_..._BAA dated 2026 by their upload (fix round 1, F2)
    upload_projects = set(document["upload_year_projects"])
    dated = [i for i in items if folder_year(i["url"]) is None and tb.project_of(i["url"]) in upload_projects]
    assert len(dated) == document["counts"]["year_from_upload"]
    assert all(i["year"] == int(i["published"][:4]) for i in dated)
    assert document["counts"]["year_from_siblings"] == sum(
        1 for i in items if folder_year(i["url"]) is None and tb.project_of(i["url"]) not in upload_projects)
    assert isinstance(document["left_out"], list) and re.match(r"20\d\d-\d\d-\d\dT", document["made_at"])
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
        assert 1990 < item["year"] <= int(item["published"][:4]) and re.match(r"\d{4}-\d\d-\d\dT", item["published"])


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


def test_web_process_never_imports_the_list(tmp_path):
    """The web process builds the catalogue (the 1 m layer's UnlistedIndex) and serves its pages without
    importing tnmbucket: nothing of the list is read there."""
    import subprocess
    repo = os.path.dirname(HERE)
    code = (f"import sys; sys.path.insert(0, {repo!r}); import web\n"
            "from fastapi.testclient import TestClient\n"
            f"c = TestClient(web.create_app({str(tmp_path)!r}, token='t', start_scheduler=False), "
            "base_url='http://127.0.0.1:8765')\n"
            "c.get('/?token=t'); import sources\n"
            "print(type(sources.SOURCES['usa'].nmt.index).__name__, 'sources.layers.tnmbucket' in sys.modules)")
    env = {**os.environ, "HTTP_PROXY": "http://127.0.0.1:9", "HTTPS_PROXY": "http://127.0.0.1:9", "NO_PROXY": ""}
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120, env=env)
    assert result.returncode == 0, result.stderr
    index, imported = result.stdout.strip().splitlines()[-1].split()
    assert (index, imported) == ("UnlistedIndex", "False")


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
                     log=lambda text: None, at_once=1)  # one at a time: the recorded order
    with open(os.path.join(RECORDED, "expected.json"), encoding="utf-8") as f:
        expected = json.load(f)
    written, _ = tb.read_list(tb.unlisted_path(cache_dir))
    host = "https://prd-tnm.s3.amazonaws.com"
    assert [{**i, "url": i["url"].replace(http_server.base, host)} for i in written] == expected["items"]
    assert len(written) > 0
    assert not http_server.stray()
    asked = [key_of(r.method, r.path + "?" + urlencode(r.query)) for r in http_server.log]
    wanted = [key_of(a["method"], urlsplit(a["url"])._replace(scheme="", netloc="").geturl())
              for a in recorded["answers"]]
    assert asked == wanted
    assert {r.user_agent for r in http_server.log} == {cache.http_headers()["User-Agent"]}
