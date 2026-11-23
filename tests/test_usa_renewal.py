"""The renewal of an area's index (sources/renewal.py, wave A of the USA, part A-2): the list of the bucket's unlisted 1 m
files made when older than 28 days and every index answer under the area asked again; failures that never stop the
caller; no listing tried twice within a day or by two processes at once, no answer asked twice; the progress; what a
renewal changes in the cached blocks (a block whose year changed, a block whose order of files changed, a file that
left the list); `cache update` and `cache status`; a search that never renews; the web process that never imports it.

The TNM index is a stand-in in this process (Tnm: requests.get, every product in every tile); USGS's bucket is a
stand-in on the local server (tests/http_server.py)."""

import json
import os
import sys
import threading
import time
from types import SimpleNamespace

import numpy as np
import pytest
import rasterio as rio
import requests
from filelock import FileLock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cache  # noqa: E402
import grid as gd  # noqa: E402
import sources as src  # noqa: E402
from sources import renewal  # noqa: E402
from sources.indexes.cached import index_tiles  # noqa: E402
from sources.indexes.versions import Block, ComposedBlocks  # noqa: E402
from sources.layers import tnmbucket as tb  # noqa: E402
from sources.layers.tnm import TNM_API, tile_item  # noqa: E402
from test_sources import RES, FakeTnm, _tile_1m  # noqa: E402
from http_server import Answer  # noqa: E402
from test_usa_unlisted import _s3_answer  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
REAL_GET = requests.get
EXTENT = (470000, 4420000, 480000, 4430000)  # x47 y443, zone 13


class Response:
    """An answer of the TNM API."""

    def __init__(self, page):
        self.status_code, self.content = 200, json.dumps(page).encode()
        self.text, self.headers = self.content.decode(), {"content-type": "application/json"}

    def json(self):
        return json.loads(self.content)

    def raise_for_status(self):
        pass


class Tnm(FakeTnm):
    """The TNM Access API (every product in every box, pages of `max`), each request noted with its box; any other
    URL (the stand-in bucket on the local server) goes to requests.get itself."""

    def __init__(self, delay=0.0):
        super().__init__()
        self.delay, self.lock = delay, threading.Lock()

    def get(self, url, params=None, **kwargs):
        if not str(url).startswith(TNM_API):
            return REAL_GET(url, params=params, **kwargs)
        if self.delay:
            time.sleep(self.delay)
        if self.offline:
            raise requests.ConnectionError("offline")
        offset, size = int(params["offset"]), int(params.get("max", 500))
        with self.lock:
            self.asked.append((params["datasets"], offset, params.get("bbox")))
        return Response({"total": len(self.products), "items": self.products[offset:offset + size]})

    def tile_requests(self):
        """The requests of answers of 0.25° tiles (not the list's boxes over the USA), by box."""
        boxes = [b for _, _, b in self.asked if b and abs(float(b.split(",")[2]) - float(b.split(",")[0]) - 0.25) < 1e-9]
        return {b: boxes.count(b) for b in boxes}


def _bucket(http_server, tnm, extra=(), delay=0.0):
    """USGS's bucket on the local server: a key for every product of the index (so none of them is unlisted) and the
    extra keys [(key, size, date)]; HTTP 500 while the returned dict's "fail" is set."""
    control = {"fail": False}
    def keys():
        out = []
        for product in tnm.products:
            path = product["downloadURL"]
            project, name = path.split("/Projects/")[1].split("/")[0], path.rsplit("/", 1)[-1]
            out.append((f"{tb.PROJECTS}{project}/TIFF/{name}", 1000, "2026-02-10T10:00:00.000Z"))
        return out + list(extra)

    def answer(request):
        if request.path != "/":
            return None
        if delay:
            time.sleep(delay)
        if control["fail"]:
            return Answer(500, b"busy", {"Content-Type": "text/plain"})
        return _s3_answer(keys(), request)
    http_server.route("/", answer)
    return control


FAR = (f"{tb.PROJECTS}CO_Far_2021/TIFF/USGS_1M_13_x40y443_CO_Far_2021.tif", 5000, "2026-02-12T10:00:00.000Z")


@pytest.fixture
def renewing(monkeypatch):
    """The list may be made (conftest keeps it off), read anew in every test; no backoff; a small bucket may look
    mostly unlisted."""
    monkeypatch.setenv(tb.RENEW_ENV, "")
    monkeypatch.setattr(src.net, "_sleep", lambda attempt: None)
    monkeypatch.setattr(tb, "MAX_UNLISTED_SHARE", 1.0)
    tb.forget_unlisted()
    yield
    tb.forget_unlisted()


def _layer(bucket=None):
    layer = src.Usgs1mBlocks("Test 1 m", "Test DEM", "test1m", "usa/test1m", native_res=RES, block_m=1000,
                             bytes_per_tile=1e4)
    layer.index.bucket = bucket
    return layer


def _grid(west=474100, south=4424100, size=1800):
    return gd.make_grid((west, south, west + size, south + size), RES, "EPSG:26913")


def _age(cache_dir, path, days):
    """The row of a cached file checked `days` ago."""
    top, inner = cache._split(cache_dir, path)
    db = cache._connect(cache_dir, top)
    with db:
        db.execute("UPDATE files SET checked_at = ? WHERE path = ?", (cache.now_iso(days * 86400), inner))
    db.close()


def _settle(cache_dir):
    """The rows of the cached answers checked 10 s ago: an answer checked at or after a renewal's start (in whole
    seconds) counts as asked by another renewal meanwhile, and these tests renew right after a download."""
    db = cache._connect(cache_dir, "usa")
    with db:
        db.execute("UPDATE files SET checked_at = ? WHERE path LIKE 'sheet-index/test1m/%'", (cache.now_iso(10),))
    db.close()


def _bucket_requests(http_server):
    return sum(1 for r in http_server.log if r.path == "/")


def _start(tmp_path, monkeypatch, http_server, delay=0.0, bucket_delay=0.0):
    tnm, files = Tnm(delay), tmp_path / "files"
    monkeypatch.setattr(requests, "get", tnm.get)
    _tile_1m(tnm, files, "CO_Full_2013", 1013)
    tnm.bucket = _bucket(http_server, tnm, [FAR], bucket_delay)
    return tnm, files, str(tmp_path / "cache")


# 1. The function

def test_renewal_makes_a_stale_list_and_asks_every_answer(http_server, tmp_path, monkeypatch, renewing):
    """The list made when missing or older than 28 days (kept at 27), every answer under the grid asked again on
    every renewal and written; what it did returned (answers, changes, the list, requests, bytes, seconds by part);
    a layer that does not renew is left alone."""
    tnm, files, cache_dir = _start(tmp_path, monkeypatch, http_server)
    layer, grid = _layer(http_server.base), _grid()
    layer.download(grid, cache_dir, None, "test")
    _settle(cache_dir)
    tiles = index_tiles(grid)
    answers = {t: layer.index.index_path(cache_dir, *t) for t in tiles}
    tnm.asked.clear()

    done = renewal.renew([layer, src.SOURCES["usgs10m"].nmt], grid, cache_dir, lambda text: None)
    assert done.list == "made" and tb.unlisted_age_days(cache_dir) < 0.01
    assert [i["name"] for i in tb.read_list(tb.unlisted_path(cache_dir))[0]] == ["USGS_1M_13_x40y443_CO_Far_2021"]
    assert (done.asked, done.changed, done.failed, done.left, done.skipped) == (len(tiles), 0, 0, 0, 0)
    assert done.requests["list bucket"] == 3 and done.requests["list index"] == len(tb.REGIONS)
    assert done.requests["answers"] == len(tiles) and done.bytes["answers"] > 0 and done.bytes["list bucket"] > 0
    assert {"list bucket", "list index", "list headers", "answers", "total"} <= set(done.seconds)
    assert tnm.tile_requests() == {f"{lon},{lat},{lon + 0.25},{lat + 0.25}": 1 for lat, lon in tiles}
    assert "index answers asked again" in done.text()

    # a new project: the next renewal (a minute later) keeps the list and asks every answer again
    _tile_1m(tnm, files, "CO_New_2025", 1025, published="2026-01-01")
    bucket = _bucket_requests(http_server)
    _settle(cache_dir)
    again = renewal.renew([layer], grid, cache_dir, lambda text: None)
    assert again.list == "kept" and _bucket_requests(http_server) == bucket
    assert (again.asked, again.changed) == (len(tiles), len(tiles))
    assert all("CO_New_2025" in open(p, encoding="utf-8").read() for p in answers.values())

    _age(cache_dir, tb.unlisted_path(cache_dir), 27)
    assert renewal.renew([layer], grid, cache_dir, lambda text: None).list == "kept"
    _age(cache_dir, tb.unlisted_path(cache_dir), 29)
    assert renewal.renew([layer], grid, cache_dir, lambda text: None).list == "made"
    assert _bucket_requests(http_server) == bucket + 4  # the folders, three projects now

    # a layer that does not renew: nothing asked
    tnm.asked.clear()
    bucket = _bucket_requests(http_server)
    none = renewal.renew([src.SOURCES["usgs10m"].nmt], grid, cache_dir, lambda text: None)
    assert (none.asked, none.list, tnm.asked, _bucket_requests(http_server)) == (0, "", [], bucket)


# 2. Failures

def test_a_failed_answer_keeps_the_cached_one(http_server, tmp_path, monkeypatch, renewing, capsys):
    """The index down: each failed answer keeps its cached one with one printed line, and after FAILED_IN_A_ROW in a
    row the rest keep theirs without being asked; the layer then lists from the cached answers."""
    tnm, files, cache_dir = _start(tmp_path, monkeypatch, http_server)
    monkeypatch.setenv(tb.RENEW_ENV, "off")
    layer, grid = _layer(http_server.base), _grid(440000, 4400000, 30000)  # several index tiles
    tiles = index_tiles(grid)
    assert len(tiles) >= 4
    for t in tiles:
        layer.index.answers(cache_dir, *t)
    _settle(cache_dir)
    written = {t: open(layer.index.index_path(cache_dir, *t), "rb").read() for t in tiles}
    tnm.offline = True
    monkeypatch.setattr(renewal, "FAILED_IN_A_ROW", 2)
    said = []
    done = renewal.renew([layer], grid, cache_dir, said.append)
    assert (done.asked, done.failed, done.left) == (0, 2, len(tiles) - 2)
    out = capsys.readouterr().out
    assert out.count("could not be asked again") == 2 and "the cached one is kept" in out
    assert any(f"the other {len(tiles) - 2}" in line for line in said)
    assert {t: open(layer.index.index_path(cache_dir, *t), "rb").read() for t in tiles} == written
    fresh = _layer()
    assert fresh.to_download(_grid(), cache_dir, None)[0] and fresh.tiles(_grid()) is not None


def test_a_failed_listing_keeps_the_list_there_is(http_server, tmp_path, monkeypatch, renewing, capsys):
    """The bucket answering 500: the list there is stays (byte for byte), one line says so, the failure is recorded
    and the answers are still asked."""
    tnm, files, cache_dir = _start(tmp_path, monkeypatch, http_server)
    layer, grid = _layer(http_server.base), _grid()
    renewal.renew([layer], grid, cache_dir, lambda text: None)
    path = tb.unlisted_path(cache_dir)
    kept = open(path, "rb").read()
    _age(cache_dir, path, 29)
    _settle(cache_dir)
    tnm.bucket["fail"] = True
    said = []
    done = renewal.renew([layer], grid, cache_dir, said.append)
    assert done.list == "failed" and open(path, "rb").read() == kept
    assert tb.read_failed(cache_dir) is not None and "could not be made" in " ".join(said)
    assert done.asked == len(index_tiles(grid))


# 3. No hammering

def test_a_failed_listing_waits_a_day(http_server, tmp_path, monkeypatch, renewing):
    """After a failed listing no renewal of any process lists again within FAILED_RETRY_DAYS (failed.json); after it
    one does, and success removes the record."""
    from datetime import datetime, timedelta, timezone
    tnm, files, cache_dir = _start(tmp_path, monkeypatch, http_server)
    layer, grid = _layer(http_server.base), _grid()
    tnm.bucket["fail"] = True
    assert renewal.renew([layer], grid, cache_dir, lambda text: None).list == "failed"
    tnm.bucket["fail"] = False
    asked = _bucket_requests(http_server)
    said = []
    assert renewal.renew([layer], grid, cache_dir, said.append).list == "kept"
    assert _bucket_requests(http_server) == asked and "a day has passed" in " ".join(said)
    with open(tb.failed_path(cache_dir), encoding="utf-8") as f:
        record = json.load(f)
    record["at"] = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat(timespec="seconds")
    with open(tb.failed_path(cache_dir), "w", encoding="utf-8") as f:
        json.dump(record, f)
    assert renewal.renew([layer], grid, cache_dir, lambda text: None).list == "made"
    assert not os.path.exists(tb.failed_path(cache_dir))


def test_two_renewals_at_once_list_once_and_ask_each_answer_once(http_server, tmp_path, monkeypatch, renewing):
    """Two renewals of one data folder at the same moment (two rows started together): the bucket is listed once,
    the second renewal takes the list the first made; every answer of an index tile is asked once."""
    tnm, files, cache_dir = _start(tmp_path, monkeypatch, http_server, delay=0.2, bucket_delay=0.2)
    grid = _grid(440000, 4400000, 30000)
    results = []

    def one():
        results.append(renewal.renew([_layer(http_server.base)], grid, cache_dir, lambda text: None))
    threads = [threading.Thread(target=one) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(r.list for r in results) == ["kept", "made"]
    assert _bucket_requests(http_server) == 3  # one listing: the projects' folders, two projects
    tiles = index_tiles(grid)
    assert sum(r.asked for r in results) == len(tiles) and sum(r.skipped for r in results) == len(tiles)
    assert set(tnm.tile_requests().values()) == {1} and len(tnm.tile_requests()) == len(tiles)


def test_the_wait_for_another_listing_ends(http_server, tmp_path, monkeypatch, renewing):
    """While another process holds the list's lock past LIST_LOCK_WAIT_S, the renewal goes on with the list there is:
    one line, no listing."""
    tnm, files, cache_dir = _start(tmp_path, monkeypatch, http_server)
    monkeypatch.setattr(renewal, "LIST_LOCK_WAIT_S", 0.3)
    lock = FileLock(os.path.join(cache_dir, cache.LOCKS, "renewal", "usa-bucket1m.lock"))
    os.makedirs(os.path.dirname(lock.lock_file), exist_ok=True)
    said = []
    with lock:
        done = threading.Thread(target=lambda: said.append(
            renewal.renew([_layer(http_server.base)], _grid(), cache_dir, said.append)))
        done.start()
        done.join()
    assert said[-1].list == "kept" and any("Another process is making the list" in s for s in said[:-1])
    assert _bucket_requests(http_server) == 0


# 4. Progress

def test_progress_through_the_callers_say(http_server, tmp_path, monkeypatch, renewing):
    """The listing's three parts, its requests while a part runs and the answers as counts, all through say."""
    tnm, files, cache_dir = _start(tmp_path, monkeypatch, http_server, delay=0.05, bucket_delay=0.1)
    monkeypatch.setattr(renewal, "PROGRESS_SECONDS", 0.02)
    said = []
    renewal.renew([_layer(http_server.base)], _grid(440000, 4400000, 30000), cache_dir, said.append)
    text = "\n".join(said)
    assert "Listing USGS's bucket" in text and "listing the TNM index" in text and "finding the zones" in text
    assert "requests to the bucket" in text and " header reads so far" in text
    assert "Asking the index of Test 1 m again" in text and " answers, " in text and "Index renewed:" in text


# 8. A search never renews

def test_a_search_asks_nothing_and_makes_no_list(http_server, tmp_path, monkeypatch, renewing):
    """With cached answers a search (the layer's estimate, listing, download and files) asks the index nothing and
    lists no bucket, the list missing; with --update stale it asks only the answers older than the index's 180 days,
    and never makes the list."""
    tnm, files, cache_dir = _start(tmp_path, monkeypatch, http_server)
    grid = _grid()
    _layer(http_server.base).download(grid, cache_dir, None, "test")
    tnm.asked.clear()
    layer = _layer(http_server.base)
    layer.estimate(grid, cache_dir, None)
    layer.to_download(grid, cache_dir, None)
    layer.download(grid, cache_dir, None, "test")
    layer.files(grid, cache_dir)
    assert tnm.asked == [] and http_server.log == [] and not os.path.exists(tb.unlisted_path(cache_dir))
    tiles = index_tiles(grid)
    for t in tiles:
        _age(cache_dir, layer.index.index_path(cache_dir, *t), 100)
    _layer(http_server.base).estimate(grid, cache_dir, "stale")
    assert tnm.asked == [] and http_server.log == []
    for t in tiles:
        _age(cache_dir, layer.index.index_path(cache_dir, *t), 200)
    _layer(http_server.base).estimate(grid, cache_dir, "stale")
    assert len(tnm.tile_requests()) == len(tiles) and http_server.log == []
    assert not os.path.exists(tb.unlisted_path(cache_dir))


# 9. What a renewal changes in the blocks

def _block_files(folder):
    return sorted(os.listdir(folder))


def test_prune_deletes_a_block_whose_year_changed(tmp_path):
    """A block cached under another newest year with the same key (a file's year changed, its name did not) is the
    older file of the block: deleted; one of another key too, as before; the block's own file stays."""
    versions = ComposedBlocks("usa/x", 1000, 1.0)
    cache_dir = str(tmp_path)
    new = Block("EPSG:26913", 474, 4424, 1000, 2021, "abcd1234")
    paths = [versions.path(cache_dir, b) for b in (new, Block("EPSG:26913", 474, 4424, 1000, 2020, "abcd1234"),
                                                   Block("EPSG:26913", 474, 4424, 1000, 2019, "ffff0000"),
                                                   Block("EPSG:26913", 475, 4424, 1000, 2020, "abcd1234"))]
    for path in paths:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        open(path, "wb").close()
    assert versions.prune(cache_dir, [new]) == 2
    assert [os.path.exists(p) for p in paths] == [True, False, False, True]


def _mosaic(layer, grid, cache_dir, tmp_path, name):
    return src.build_mosaic(layer.files(grid, cache_dir), grid, str(tmp_path / f"{name}.npy"), "test")


def _blocks_equal(a_dir, b_dir):
    """The cached blocks of two data folders: the same names, values and tags."""
    a = os.path.join(a_dir, "usa", "test1m", "epsg26913", "47_442")
    b = os.path.join(b_dir, "usa", "test1m", "epsg26913", "47_442")
    assert _block_files(a) == _block_files(b)
    for name in _block_files(a):
        with rio.open(os.path.join(a, name)) as x, rio.open(os.path.join(b, name)) as y:
            assert np.array_equal(x.read(1), y.read(1)) and x.tags().get("sources") == y.tags().get("sources")


def _fake_listing(monkeypatch, state):
    """tnmbucket.make_unlisted writing state["list"] (its own tests list a stand-in bucket): the renewal's rules are
    tested here with files the blocks can read (local paths)."""
    def make(cache_dir, **kwargs):
        state.setdefault("made", 0)
        state["made"] += 1
        path = tb.unlisted_path(cache_dir)
        tb.write_list(path, {"made_at": cache.now_iso(), "files": len(state["list"]), "listed": 1, "left_out": []},
                      list(state["list"]), "b", "a", "d")
        cache.record(cache_dir, path, url="b")
        tb.forget_unlisted()
        return {"requests": {"bucket": 1, "index": 1, "headers": 0}, "answer_bytes": {"bucket": 1, "index": 1},
                "seconds_by_part": {"bucket": 0.0, "index": 0.0, "headers": 0.0}}
    monkeypatch.setattr(tb, "make_unlisted", make)


def test_a_file_the_index_lists_since_reorders_its_blocks(tmp_path, monkeypatch, renewing):
    """Two files of one year over the same blocks: the unlisted one first (its upload time is the later date), then
    the index lists it with an earlier date and it leaves the list. The blocks keep their name (the same files, the
    same newest year) but their order flips: a renewal deletes them, and the blocks read again equal those a data
    folder that never had the list makes."""
    tnm, files = Tnm(), tmp_path / "files"
    monkeypatch.setattr(requests, "get", tnm.get)
    _tile_1m(tnm, files, "CO_Bee_2020", 1001, published="2024-01-01")                        # listed
    unlisted = _tile_1m(FakeTnm(), files, "CO_Ay_2020", 1002, name="USGS_1M_13_x47y443_CO_Ay_2020.tif")
    state = {"list": [tile_item(unlisted, 13, "2026-02-12T17:17:41.000Z")]}
    _fake_listing(monkeypatch, state)
    layer, grid, cache_dir = _layer(), _grid(), str(tmp_path / "cache")
    renewal.renew([layer], grid, cache_dir, lambda text: None)
    layer.download(grid, cache_dir, None, "test")
    folder = os.path.join(cache_dir, "usa", "test1m", "epsg26913", "47_442")
    names = _block_files(folder)
    assert len(names) == 4 and (_mosaic(layer, grid, cache_dir, tmp_path, "a") == 1002).all()

    tnm.add(unlisted, "EPSG:26913", EXTENT, published="2023-06-01")   # the index lists it now, dated before 2024
    state["list"] = []
    _age(cache_dir, tb.unlisted_path(cache_dir), 29)
    _settle(cache_dir)
    done = renewal.renew([_layer()], grid, cache_dir, lambda text: None)
    assert (done.list, done.departed, done.reread) == ("made", 1, 4)
    assert _block_files(folder) == []                                  # the four read again when needed
    again = _layer()
    again.download(grid, cache_dir, None, "test")
    assert _block_files(folder) == names and (_mosaic(again, grid, cache_dir, tmp_path, "b") == 1001).all()
    fresh_dir = str(tmp_path / "fresh")
    _layer().download(grid, fresh_dir, None, "test")
    _blocks_equal(cache_dir, fresh_dir)


def test_a_file_that_left_the_list_stays_outside_the_renewed_area(tmp_path, monkeypatch, renewing):
    """A file that left the list because the index lists it now is asked again in every cached answer it reaches,
    also where the renewal's area is elsewhere: it never drops out of the blocks there (their key stays)."""
    tnm, files = Tnm(), tmp_path / "files"
    monkeypatch.setattr(requests, "get", tnm.get)
    _tile_1m(tnm, files, "CO_Full_2013", 1013)
    unlisted = _tile_1m(FakeTnm(), files, "CO_New_2025", 1025, name="USGS_1M_13_x47y443_CO_New_2025.tif")
    state = {"list": [tile_item(unlisted, 13, "2026-02-12T17:17:41.000Z")]}
    _fake_listing(monkeypatch, state)
    layer, grid, cache_dir = _layer(), _grid(), str(tmp_path / "cache")
    renewal.renew([layer], grid, cache_dir, lambda text: None)
    layer.download(grid, cache_dir, None, "test")
    keys = {(b.i, b.j): b.key for b in layer.tiles(grid)}

    tnm.add(unlisted, "EPSG:26913", EXTENT, published="2026-03-01")
    state["list"] = []
    _age(cache_dir, tb.unlisted_path(cache_dir), 29)
    _settle(cache_dir)
    elsewhere = _grid(400100, 4424100)                                 # x40: 70 km west
    done = renewal.renew([_layer()], elsewhere, cache_dir, lambda text: None)
    assert done.departed == 1
    fresh = _layer()
    fresh._use(cache_dir, None)
    assert {(b.i, b.j): b.key for b in fresh.tiles(grid)} == keys
    assert all("USGS_1M_13_x47y443_CO_New_2025" in [n for n, _, _ in b.files] for b in fresh.tiles(grid))


def test_cache_update_reads_again_a_block_whose_order_changed(tmp_path, monkeypatch):
    """update_index_tile (cache update): a listed file published again with another date flips the order of two files
    of one year; the block keeps its name and is read again."""
    import osm
    from rasterio.warp import transform_bounds
    tnm, files = Tnm(), tmp_path / "files"
    monkeypatch.setattr(requests, "get", tnm.get)
    _tile_1m(tnm, files, "CO_Bee_2020", 1001, published="2024-01-01")
    _tile_1m(tnm, files, "CO_Cee_2020", 1003, published="2025-01-01")
    layer, grid, cache_dir = _layer(), _grid(), str(tmp_path / "cache")
    layer.download(grid, cache_dir, None, "test")
    assert (_mosaic(layer, grid, cache_dir, tmp_path, "a") == 1003).all()
    tnm.products[1]["publicationDate"] = "2023-01-01"
    results = [_layer().update_index_tile(cache_dir, lat, lon)
               for lat, lon in osm.tiles(*transform_bounds("EPSG:26913", "EPSG:4326", *grid.bounds))]
    assert sum(r[0] for r in results) == 4
    assert (_mosaic(_layer(), grid, cache_dir, tmp_path, "b") == 1001).all()
    fresh_dir = str(tmp_path / "fresh")
    _layer().download(grid, fresh_dir, None, "test")
    _blocks_equal(cache_dir, fresh_dir)


# 7. cache update and cache status

def _usa_cache(tmp_path, monkeypatch, list_days=None, answer_days=100, ifsar_days=100):
    """A data folder with a cached answer of the 1 m DEM and one of the IfSAR (and the list, made list_days ago),
    their rows aged; the layers' update_index_tile and the renewal's list recorded instead of asked."""
    import update
    cache_dir = str(tmp_path / "data" / "cache")
    cache.check_layout(cache_dir)
    one_m, ifsar = src.SOURCES["usa"].nmt, src.SOURCES["alaska_ifsar"].nmt
    paths = [one_m.index_path(cache_dir, 40.0, -105.5), ifsar.index_path(cache_dir, 60.0, -150.0)]
    for path, days in zip(paths, (answer_days, ifsar_days)):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"sheets": []}, f)
        cache.record(cache_dir, path, url="x")
        _age(cache_dir, path, days)
    if list_days is not None:
        tb.write_list(tb.unlisted_path(cache_dir), {"made_at": "x", "listed": 1, "left_out": []}, [], "b", "a", "d")
        cache.record(cache_dir, tb.unlisted_path(cache_dir), url="b")
        _age(cache_dir, tb.unlisted_path(cache_dir), list_days)
    order = []
    monkeypatch.setattr(one_m, "update_index_tile", lambda c, lat, lon: order.append(("1m", lat, lon)) or (0, 0.0, 0))
    monkeypatch.setattr(ifsar, "update_index_tile", lambda c, lat, lon: order.append(("ifsar", lat, lon)) or (0, 0.0, 0))
    monkeypatch.setattr(renewal, "renew_list", lambda layer, c, say, force=False: order.append(("list", force))
                        or renewal.Renewal(list="made"))
    return update, cache_dir, order


def test_cache_update_checks_the_list_first_and_the_1m_answers_after_28_days(tmp_path, monkeypatch):
    """The list (29 days old) is checked before the answers; the 1 m DEM's answers are due after 28 days (100 days
    old: due, 180 before), IfSAR's after the sheet index's 180 (100 days: not due); 27 days: neither."""
    update, cache_dir, order = _usa_cache(tmp_path, monkeypatch, list_days=29)
    assert update.run_update(cache_dir, "usa") == 0
    assert order == [("list", False), ("1m", 40.0, -105.5)]
    update, cache_dir, order = _usa_cache(tmp_path / "b", monkeypatch, list_days=27, answer_days=27)
    assert [c.what for c in update.checks(cache_dir, "usa")] == []
    update, cache_dir, order = _usa_cache(tmp_path / "c", monkeypatch, list_days=27, answer_days=29, ifsar_days=181)
    assert [c.path.split("/")[2] for c in update.checks(cache_dir, "usa")] == ["dem1m", "ifsar5m"]


def test_cache_update_makes_a_missing_list_and_spares_another_place(tmp_path, monkeypatch, capsys):
    """No list made yet while 1 m answers are cached: a check of its own (--all forces it); --point elsewhere checks
    no list; `cache status` says in one line what list is used."""
    update, cache_dir, order = _usa_cache(tmp_path, monkeypatch)
    checks = update.checks(cache_dir, "usa")
    assert checks[0].first and checks[0].path == "usa/sheet-index/bucket1m/unlisted.json"
    assert update.run_update(cache_dir, "usa", "all") == 0 and order[0] == ("list", True)
    assert [c.path for c in update.checks(cache_dir, "usa", bbox=(10.0, 50.0, 10.0, 50.0))] == []
    assert "bucket1m" in update.checks(cache_dir, "usa", bbox=(-105.4, 40.1, -105.4, 40.1))[0].path
    update.status(cache_dir, str(tmp_path / "data" / "runs"), "usa")
    assert "the list of the files its index does not list: none made yet" in capsys.readouterr().out


def test_cache_status_line_of_a_made_list(tmp_path):
    cache_dir = str(tmp_path)
    tb.write_list(tb.unlisted_path(cache_dir), {"made_at": "x", "files": 3, "listed": 1, "left_out": []}, [], "b", "a",
                  "d")
    cache.record(cache_dir, tb.unlisted_path(cache_dir), url="b")
    _age(cache_dir, tb.unlisted_path(cache_dir), 5)
    text = tb.list_status(cache_dir)
    assert "(5 days ago, 3 files); made again after 28 days" in text
    tb.write_failed(cache_dir, "TNM API: HTTP 503")
    assert "the last try failed" in tb.list_status(cache_dir) and "HTTP 503" in tb.list_status(cache_dir)


# 6. The country count (the call; the resume: tests/test_country.py)

def test_country_renews_its_layers_and_fallbacks(tmp_path, monkeypatch):
    """country._renew: the bands' layers and the source's fall-backs that renew (alaska: its 1 m DEM and Alaska's
    IfSAR), the note in country.json; the config hash untouched."""
    import country
    asked = []
    monkeypatch.setattr(renewal, "renew", lambda layers, grid, cache_dir, say, done: asked.append(
        [layer.description for layer in renewal.renewing(layers)]) or renewal.Renewal(asked=3))
    plan = SimpleNamespace(layers=[src.SOURCES["alaska"].nmt], grid=_grid(), paths=SimpleNamespace(cache="c"))
    state = {"hash": "h", "config": {"id": "x"}}
    folder = str(tmp_path)
    country._renew(SimpleNamespace(source="alaska"), {"S": plan, "M": plan}, folder, state, print)
    assert asked == [["3DEP 1 m DEM (terrain)"], ["3DEP 1 m DEM (terrain)"], ["3DEP Alaska IfSAR 5 m DTM (terrain)"]]
    with open(os.path.join(folder, "country.json"), encoding="utf-8") as f:
        written = json.load(f)
    assert written["hash"] == "h" and [r["asked"] for r in written["index_renewed"]["renewals"]] == [3, 3, 3]
    asked.clear()
    plain = SimpleNamespace(layers=[src.SOURCES["usgs10m"].nmt], grid=_grid(), paths=SimpleNamespace(cache="c"))
    country._renew(SimpleNamespace(source="usgs10m"), {"S": plain}, str(tmp_path / "b"), {}, print)
    assert asked == [] and not os.path.exists(tmp_path / "b" / "country.json")


# 10. The web process

def test_web_process_never_imports_the_renewal(tmp_path):
    """The web process serves its pages without importing the renewal (nor the list)."""
    import subprocess
    repo = os.path.dirname(HERE)
    code = (f"import sys; sys.path.insert(0, {repo!r}); import web\n"
            "from fastapi.testclient import TestClient\n"
            f"c = TestClient(web.create_app({str(tmp_path)!r}, token='t', start_scheduler=False), "
            "base_url='http://127.0.0.1:8765')\n"
            "c.get('/?token=t'); c.get('/api/sources')\n"
            "print('sources.renewal' in sys.modules, 'sources.layers.tnmbucket' in sys.modules)")
    env = {**os.environ, "HTTP_PROXY": "http://127.0.0.1:9", "HTTPS_PROXY": "http://127.0.0.1:9", "NO_PROXY": ""}
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120, env=env)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().splitlines()[-1] == "False False"
