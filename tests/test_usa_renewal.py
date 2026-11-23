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


def test_a_service_down_stops_once_a_start(http_server, tmp_path, monkeypatch, renewing):
    """C3: after FAILED_IN_A_ROW failures in a row every later call of the same start for the same API (another
    plan, another layer of the TNM API) returns at once: its tiles counted as left, one line, no request."""
    tnm, files, cache_dir = _start(tmp_path, monkeypatch, http_server)
    monkeypatch.setenv(tb.RENEW_ENV, "off")
    layer, grid = _layer(), _grid(440000, 4400000, 30000)
    tiles = index_tiles(grid)
    for t in tiles:
        layer.index.answers(cache_dir, *t)
    _settle(cache_dir)
    tnm.offline = True
    monkeypatch.setattr(renewal, "FAILED_IN_A_ROW", 2)
    asked, said = set(), []
    first = renewal.renew([layer], grid, cache_dir, said.append, asked)
    assert (first.failed, first.left) == (2, len(tiles) - 2)
    tnm.asked.clear()
    ifsar = src.IfsarBlocks("Test IfSAR", "Test IfSAR DEM", "testifsar", "usa/testifsar", native_res=RES,
                            block_m=1000, bytes_per_tile=1e4)
    elsewhere = _grid(400100, 4424100)                                  # x40: no tile of the first grid
    later = [renewal.renew([_layer()], elsewhere, cache_dir, said.append, asked),
             renewal.renew([ifsar], grid, cache_dir, said.append, asked)]
    assert tnm.asked == [] and [(r.asked, r.failed) for r in later] == [(0, 0), (0, 0)]
    assert later[0].left == len(index_tiles(elsewhere)) > 0 and later[1].left == len(tiles)
    assert sum("did not answer 2 times in a row in this start" in line for line in said) == 2


def test_a_fault_of_one_tile_is_that_tiles(http_server, tmp_path, monkeypatch, renewing):
    """C6: any exception of one tile but a KeyboardInterrupt (a locked database, an answer that is no dict, a block
    open in another process, answers that disagree) fails that tile alone; the rest of the grid is still asked. Such
    faults, more in a row than FAILED_IN_A_ROW, do not count as the service being down."""
    import sqlite3
    from sources.indexes.cached import CachedIndex, DroppedFiles
    tnm, files, cache_dir = _start(tmp_path, monkeypatch, http_server)
    monkeypatch.setenv(tb.RENEW_ENV, "off")
    monkeypatch.setattr(renewal, "FAILED_IN_A_ROW", 2)
    layer, grid = _layer(), _grid(430000, 4390000, 45000)
    tiles = index_tiles(grid)
    assert len(tiles) >= 6
    for t in tiles:
        layer.index.answers(cache_dir, *t)
    _settle(cache_dir)
    real, faults = CachedIndex.ask_again, [sqlite3.OperationalError("database is locked"),
                                           AttributeError("'list' object has no attribute 'get'"),
                                           PermissionError(13, "used by another process"),
                                           DroppedFiles("the index answer lacked 1 of the files")]

    def ask_again(self, cache_dir, lat, lon, *args):
        if (lat, lon) in tiles[:len(faults)]:
            raise faults[tiles.index((lat, lon))]
        return real(self, cache_dir, lat, lon, *args)
    monkeypatch.setattr(CachedIndex, "ask_again", ask_again)
    done = renewal.renew([_layer()], grid, cache_dir, lambda text: None)
    assert (done.failed, done.kept, done.asked, done.left) == (len(faults), 0, len(tiles) - len(faults), 0)
    monkeypatch.setattr(CachedIndex, "ask_again", lambda *a: (_ for _ in ()).throw(KeyboardInterrupt()))
    with pytest.raises(KeyboardInterrupt):
        renewal.renew([_layer()], grid, cache_dir, lambda text: None)


def test_a_fault_of_our_own_on_every_tile_stops_the_layer(http_server, tmp_path, monkeypatch, renewing):
    """D5: the same fault that is no request error, OWN_FAULTS_IN_A_ROW times in a row (a fault of this code, here in
    writing an answer), stops the layer's renewal for the start with one line: the rest keeps its cached answers, later
    calls of the start return at once, no answer more is fetched and thrown away."""
    tnm, files, cache_dir = _start(tmp_path, monkeypatch, http_server)
    monkeypatch.setenv(tb.RENEW_ENV, "off")
    monkeypatch.setattr(renewal, "OWN_FAULTS_IN_A_ROW", 2)
    layer, grid = _layer(), _grid(430000, 4390000, 45000)
    tiles = index_tiles(grid)
    for t in tiles:
        layer.index.answers(cache_dir, *t)
    _settle(cache_dir)

    from sources.indexes.cached import CachedIndex

    def broken(*args):
        raise TypeError("'NoneType' object is not subscriptable")
    monkeypatch.setattr(CachedIndex, "_store", broken)
    tnm.asked.clear()
    asked, said = set(), []
    done = renewal.renew([_layer()], grid, cache_dir, said.append, asked)
    assert (done.failed, done.left, done.asked) == (2, len(tiles) - 2, 0) and len(tnm.tile_requests()) == 2
    assert any("failed 2 times in a row with TypeError" in line for line in said)
    again = renewal.renew([_layer()], _grid(400100, 4424100), cache_dir, said.append, asked)
    assert again.left > 0 and len(tnm.tile_requests()) == 2


def test_renew_asks_an_ifsar_layer_too(tmp_path, monkeypatch, renewing):
    """Every TNM dataset renews: an IfSAR-kind layer (no list) has every answer under the grid asked again and a new
    product seen; its answers' requests are counted."""
    tnm = Tnm()
    monkeypatch.setattr(requests, "get", tnm.get)
    _tile_1m(tnm, tmp_path / "files", "AK_Cell_2012", 1012)
    layer = src.IfsarBlocks("Test IfSAR", "Test IfSAR DEM", "testifsar", "usa/testifsar", native_res=RES,
                            block_m=1000, bytes_per_tile=1e4)
    cache_dir, grid = str(tmp_path / "cache"), _grid()
    tiles = index_tiles(grid)
    for t in tiles:
        layer.index.answers(cache_dir, *t)
    db = cache._connect(cache_dir, "usa")
    with db:
        db.execute("UPDATE files SET checked_at = ?", (cache.now_iso(10),))
    db.close()
    _tile_1m(tnm, tmp_path / "files", "AK_Cell_2016", 1016)
    tnm.asked.clear()
    done = renewal.renew([layer], grid, cache_dir, lambda text: None)
    assert (done.asked, done.changed, done.list, done.requests["answers"]) == (len(tiles), len(tiles), "", len(tiles))
    assert all("AK_Cell_2016" in open(layer.index.index_path(cache_dir, *t), encoding="utf-8").read() for t in tiles)
    assert layer.index.confirms_drops and len(tnm.tile_requests()) == len(tiles)


class Faulty(Tnm):
    """The TNM API answering HTTP 200 with a fault for the next `times` requests of a tile: "short" (the first
    product left out of a page whose total stays), "empty" (no products, total 0), "error" (an error body),
    "dropped" (the product of `url` missing)."""

    def __init__(self):
        super().__init__()
        self.fault, self.times, self.url = None, 0, None

    def get(self, url, params=None, **kwargs):
        response = super().get(url, params=params, **kwargs)
        if not str(url).startswith(TNM_API) or not self.times:
            return response
        self.times -= 1
        page = response.json()
        if self.fault == "short":
            page["items"] = page["items"][1:]
        elif self.fault == "empty":
            page = {"total": 0, "items": [], "errors": [], "messages": []}
        elif self.fault == "error":
            page = {"errorMessage": "Internal error: the search timed out"}
        elif self.fault == "dropped":
            page["items"] = [p for p in page["items"] if p["downloadURL"] != self.url]
            page["total"] = len(page["items"])
        return Response(page)


def _two_projects(tmp_path, monkeypatch, http_server):
    """C1's scene: a tile's whole 10 km of 2013 and its western half of 2025, downloaded (the blocks: 2025 west of
    475 000, 2013 elsewhere), the answers settled; the list off. The blocks' names and the mosaic's values."""
    monkeypatch.setenv(tb.RENEW_ENV, "off")
    tnm, files = Faulty(), tmp_path / "files"
    monkeypatch.setattr(requests, "get", tnm.get)
    _tile_1m(tnm, files, "CO_Full_2013", 1013)
    newer = _tile_1m(tnm, files, "CO_West_2025", 1025, columns=slice(0, 106), published="2026-01-01")
    cache_dir, grid = str(tmp_path / "cache"), _grid()
    _layer().download(grid, cache_dir, None, "test")
    _settle(cache_dir)
    folder = os.path.join(cache_dir, "usa", "test1m", "epsg26913", "47_442")
    values = sorted(set(np.unique(_mosaic(_layer(), grid, cache_dir, tmp_path, "before")).tolist()))
    assert values == [1013.0, 1025.0]
    return tnm, newer, cache_dir, grid, folder, _block_files(folder)


def _good_blocks_used(tmp_path, cache_dir, grid, folder, names, name):
    """What the next pass does (a fresh layer's download): the good blocks stay, and they are what it reads."""
    _layer().download(grid, cache_dir, None, "test")
    assert _block_files(folder) == names
    assert sorted(set(np.unique(_mosaic(_layer(), grid, cache_dir, tmp_path, name)).tolist())) == [1013.0, 1025.0]


@pytest.mark.parametrize("fault, times", [("short", 1), ("empty", 1), ("error", 99), ("dropped", 1), ("empty", 2),
                                          ("dropped", 2)])
def test_a_bad_answer_never_replaces_a_good_one(http_server, tmp_path, monkeypatch, renewing, fault, times):
    """C1 and D3: an answer with HTTP 200 that is short (asked once more and joined), empty where files were or
    lacking a product, once (asked once more: the second, complete, is written) or twice in a row while the files
    still answer at their URLs (kept), an error body (asked again, then failed): the cached answer stays or a
    complete one is written, and the next pass leaves the good blocks in place and reads them."""
    tnm, newer, cache_dir, grid, folder, names = _two_projects(tmp_path, monkeypatch, http_server)
    answers = {t: open(_layer().index.index_path(cache_dir, *t), encoding="utf-8").read() for t in index_tiles(grid)}
    tnm.fault, tnm.times, tnm.url = fault, times, newer
    done = renewal.renew([_layer()], grid, cache_dir, lambda text: None)
    if fault == "short" or times == 1 and fault != "error":
        assert (done.asked, done.failed) == (len(answers), 0)    # asked once more: complete
    else:
        assert done.failed + done.kept == len(answers) == 1 and done.asked == 0
        assert done.kept == (fault != "error")                     # a refused drop is kept, an error body failed
    for t, text in answers.items():
        assert sorted(json.loads(text)["sheets"], key=str) == sorted(
            json.loads(open(_layer().index.index_path(cache_dir, *t), encoding="utf-8").read())["sheets"], key=str)
    _good_blocks_used(tmp_path, cache_dir, grid, folder, names, fault)


def test_a_product_dropped_twice_is_taken(http_server, tmp_path, monkeypatch, renewing):
    """A product missing from two answers asked one after the other whose file is gone at its URL is a real removal:
    taken at once, nothing to clear by hand; the next pass reads the blocks without it."""
    tnm, newer, cache_dir, grid, folder, names = _two_projects(tmp_path, monkeypatch, http_server)
    tnm.fault, tnm.times, tnm.url = "dropped", 2, newer
    os.remove(newer)                                                   # gone at its URL
    done = renewal.renew([_layer()], grid, cache_dir, lambda text: None)
    assert (done.asked, done.changed, done.failed) == (1, 1, 0)
    tile = index_tiles(grid)[0]
    assert newer not in open(_layer().index.index_path(cache_dir, *tile), encoding="utf-8").read()
    tnm.products = [p for p in tnm.products if p["downloadURL"] != newer]
    _layer().download(grid, cache_dir, None, "test")
    assert (_mosaic(_layer(), grid, cache_dir, tmp_path, "after") == 1013).all()


def test_cache_update_keeps_a_good_answer_too(http_server, tmp_path, monkeypatch, renewing):
    """The path of `cache update` (update_index_tile: a fresh answer before the blocks) refuses the same bad answers:
    an empty answer twice while the files still answer raises (the check fails), the cached answer and the blocks
    stay."""
    tnm, newer, cache_dir, grid, folder, names = _two_projects(tmp_path, monkeypatch, http_server)
    tile = index_tiles(grid)[0]
    path = _layer().index.index_path(cache_dir, *tile)
    text = open(path, encoding="utf-8").read()
    tnm.fault, tnm.times = "empty", 2
    with pytest.raises(requests.RequestException, match="still answers at its URL"):
        _layer().update_index_tile(cache_dir, *tile)
    assert open(path, encoding="utf-8").read() == text
    tnm.fault, tnm.times = "error", 99
    with pytest.raises(requests.RequestException, match="not an answer of products"):
        _layer().update_index_tile(cache_dir, *tile)
    assert open(path, encoding="utf-8").read() == text
    _good_blocks_used(tmp_path, cache_dir, grid, folder, names, "update")


def test_the_check_of_dropped_files(http_server, tmp_path, monkeypatch, renewing, capsys):
    """D3: two answers that agree in dropping a file are taken only when the file is gone at its URL; a check that
    fails (not known) keeps the cached answer, also when more files are dropped than CHECK_GONE_MAX (one check, in the
    order of the URLs: the first fails); an index without a check (IfSAR's kind) takes two agreeing answers."""
    from sources.indexes import cached as cached_module
    tnm, newer, cache_dir, grid, folder, names = _two_projects(tmp_path, monkeypatch, http_server)
    tile = index_tiles(grid)[0]
    path = _layer().index.index_path(cache_dir, *tile)
    text = open(path, encoding="utf-8").read()
    checked = []
    monkeypatch.setattr(tb, "file_gone", lambda url: checked.append(url))   # None: not known
    tnm.fault, tnm.times, tnm.url = "dropped", 2, newer
    done = renewal.renew([_layer()], grid, cache_dir, lambda text: None)
    assert (done.failed, checked) == (1, [newer]) and open(path, encoding="utf-8").read() == text
    assert "at its URL failed" in capsys.readouterr().out
    monkeypatch.setattr(cached_module, "CHECK_GONE_MAX", 1)
    checked.clear()
    _settle(cache_dir)
    tnm.fault, tnm.times = "empty", 2                                   # two dropped, more than 1: the first checked
    done = renewal.renew([_layer()], grid, cache_dir, lambda text: None)
    first = min(p["downloadURL"] for p in tnm.products)
    assert (done.failed, checked) == (1, [first]) and open(path, encoding="utf-8").read() == text
    _settle(cache_dir)
    tnm.fault, tnm.times = "empty", 2
    layer = _layer()
    layer.index.check_gone = None                                       # no check: two agreeing answers are taken
    done = renewal.renew([layer], grid, cache_dir, lambda text: None)
    assert (done.asked, done.failed) == (1, 0) and json.load(open(path, encoding="utf-8"))["sheets"] == []


def test_a_drop_of_many_files_is_checked_in_order_up_to_the_cap(tmp_path):
    """Round 2c: 30 dropped files (more than CHECK_GONE_MAX) checked in the order of their URLs: all gone, the drop
    is taken after exactly CHECK_GONE_MAX checks (a real removal of any size passes); the first still there, kept
    after one check; the 3rd check failing, kept after three."""
    from sources.indexes.cached import CHECK_GONE_MAX, CachedIndex, DroppedFiles, Listing
    files = [{"url": f"https://bucket.example/Projects/P/TIFF/f{k:02d}.tif"} for k in range(30)]

    class Answers(Listing):
        url, sheets = "https://index.example", files

        def fetch(self, lat, lon):
            return {"sheets": list(Answers.sheets)}
    index = CachedIndex("x", Answers(), None, "p", "top")
    index.confirms_drops = True
    cache_dir = str(tmp_path)
    urls = sorted(f["url"] for f in files)
    for answers, calls, taken in (({}, CHECK_GONE_MAX, True), ({urls[0]: False}, 1, False),
                                  ({urls[2]: None}, 3, False)):
        Answers.sheets = files
        assert len(index.answers(cache_dir, 50.0, 10.0, "all")) == 30   # cached: the 30 files
        checked = []
        index.check_gone = lambda url, answers=answers: (checked.append(url), answers.get(url, True))[1]
        Answers.sheets = []                                              # the index drops them all, twice
        if taken:
            assert index.ask_again(cache_dir, 50.0, 10.0) and index.answers(cache_dir, 50.0, 10.0) == []
        else:
            with pytest.raises(DroppedFiles):
                index.ask_again(cache_dir, 50.0, 10.0)
            assert len(index.answers(cache_dir, 50.0, 10.0)) == 30      # the cached answer stays
        assert checked == urls[:calls]


def test_a_file_the_index_delists_and_the_bucket_keeps(tmp_path, monkeypatch, renewing):
    """D3's way out: the index stops listing a file the bucket still holds: the answers dropping it are kept (it
    still answers); the next listing of the bucket finds it unlisted and lists it, after which nothing is dropped,
    the answer is written, and the blocks (their order: the upload date in place of the index's) equal a fresh
    folder's."""
    tnm, files = Tnm(), tmp_path / "files"
    monkeypatch.setattr(requests, "get", tnm.get)
    _tile_1m(tnm, files, "CO_Bee_2020", 1001, published="2024-01-01")
    u1 = _tile_1m(tnm, files, "CO_Ay_2020", 1002, name="USGS_1M_13_x47y443_CO_Ay_2020.tif", published="2023-06-01")
    state = {"list": []}
    _fake_listing(monkeypatch, state, tnm)
    cache_dir, grid = str(tmp_path / "cache"), _grid()
    renewal.renew([_layer()], grid, cache_dir, lambda text: None)
    _layer().download(grid, cache_dir, None, "test")
    assert (_mosaic(_layer(), grid, cache_dir, tmp_path, "a") == 1001).all()   # B (2024) before Ay (2023)
    tnm.products = [p for p in tnm.products if p["downloadURL"] != u1]          # delisted; the file stays
    _settle(cache_dir)
    done = renewal.renew([_layer()], grid, cache_dir, lambda text: None)
    assert (done.asked, done.failed, done.kept) == (0, 0, 1)
    state["list"] = [tile_item(u1, 13, "2026-02-12T17:17:41.000Z")]            # the next listing finds it
    _age(cache_dir, tb.unlisted_path(cache_dir), 29)
    _settle(cache_dir)
    done = renewal.renew([_layer()], grid, cache_dir, lambda text: None)
    assert (done.list, done.asked, done.failed) == ("made", 1, 0)
    _layer().download(grid, cache_dir, None, "test")
    assert (_mosaic(_layer(), grid, cache_dir, tmp_path, "b") == 1002).all()   # Ay uploaded 2026, read first
    _blocks_equal(cache_dir, _fresh(tmp_path, grid))


def test_a_file_the_index_lists_at_another_url_is_the_same_file(tmp_path, monkeypatch, renewing):
    """E2: the index lists a file at another URL (the name kept: a new host or folder) and adds a new file elsewhere:
    nothing is dropped (the identity is the file's name), the answer is written at the first renewal, and the blocks
    of the moved file are not read again (their names are its name's)."""
    import shutil
    tnm, files = Tnm(), tmp_path / "files"
    monkeypatch.setattr(requests, "get", tnm.get)
    monkeypatch.setenv(tb.RENEW_ENV, "off")
    bee = _tile_1m(tnm, files, "CO_Bee_2020", 1001, published="2024-01-01")
    cache_dir, grid = str(tmp_path / "cache"), _grid()
    _layer().download(grid, cache_dir, None, "test")
    folder = os.path.join(cache_dir, "usa", "test1m", "epsg26913", "47_442")
    names = _block_files(folder)
    moved = (tmp_path / "moved" / "Projects" / "CO_Bee_2020" / "TIFF" / _name(bee)).as_posix()
    os.makedirs(os.path.dirname(moved))
    shutil.copyfile(bee, moved)
    tnm.products[0]["downloadURL"] = moved                              # the old URL still answers
    _tile_1m(tnm, files, "CO_Next_2025", 1025, x=48)                    # a new file in the next cell
    _settle(cache_dir)
    done = renewal.renew([_layer()], grid, cache_dir, lambda text: None)
    assert (done.asked, done.changed, done.failed) == (1, 1, 0)
    answer = open(_layer().index.index_path(cache_dir, *index_tiles(grid)[0]), encoding="utf-8").read()
    assert moved in answer and "CO_Next_2025" in answer
    _layer().download(grid, cache_dir, None, "test")
    assert _block_files(folder) == names


def test_a_list_item_and_an_answer_item_of_one_name_are_one_file(tmp_path, monkeypatch, renewing):
    """E2: the list holds a file at one URL and an index answer the same name at another: the merge (merge_items, and
    keep_item across tiles) gives one file, the answer's, and a block names it once."""
    tnm, files = Tnm(), tmp_path / "files"
    monkeypatch.setattr(requests, "get", tnm.get)
    _tile_1m(tnm, files, "CO_Bee_2020", 1001, published="2024-01-01")
    u1 = _tile_1m(tnm, files, "CO_Ay_2020", 1002, name="USGS_1M_13_x47y443_CO_Ay_2020.tif", published="2023-06-01")
    elsewhere = "https://bucket.example/Projects/CO_Ay_2020/TIFF/" + _name(u1)
    state = {"list": [tile_item(elsewhere, 13, "2026-02-12T17:17:41.000Z")]}
    _fake_listing(monkeypatch, state, tnm)
    cache_dir, grid = str(tmp_path / "cache"), gd.make_grid((474100, 4426100, 475900, 4429900), RES, "EPSG:26913")
    renewal.renew([_layer()], grid, cache_dir, lambda text: None)
    layer = _layer()
    layer._use(cache_dir, None)
    for block in layer.tiles(grid):
        names = [n for n, _, _ in block.files]
        assert sorted(names) == sorted(set(names)) and len(names) == 2
        assert dict((n, u) for n, u, _ in block.files)["USGS_1M_13_x47y443_CO_Ay_2020"] == u1
    # the two places on their own: a tile's merge, and tiles joined with the list's item in the first one
    from sources.indexes.cached import EXTRA, merge_items
    from sources.indexes.versions import keep_item
    answer_item, list_item = tile_item(u1, 13, "2023-06-01"), tile_item(elsewhere, 13, "2026-02-12T17:17:41.000Z")
    assert merge_items([answer_item], [list_item]) == [answer_item]
    found, by_name = {}, {}
    keep_item(found, dict(list_item, **{EXTRA: True}), by_name)    # a tile whose answer lacks it
    keep_item(found, answer_item, by_name)                         # a later tile's answer holds it
    assert list(found.values()) == [answer_item]


def test_a_search_with_update_reads_a_refused_tiles_cached_answer(tmp_path, monkeypatch, renewing, capsys):
    """E3: a search with --update meets a refused drop in one tile (a file the index delisted that still answers):
    one line, that tile's cached answer is read, the grid's other tiles are still asked and written, and the layer
    is not turned to the cached files as a whole."""
    tnm, files = Tnm(), tmp_path / "files"
    monkeypatch.setattr(requests, "get", tnm.get)
    monkeypatch.setenv(tb.RENEW_ENV, "off")
    _tile_1m(tnm, files, "CO_Bee_2020", 1001, published="2024-01-01")
    u1 = _tile_1m(tnm, files, "CO_Ay_2020", 1002, name="USGS_1M_13_x47y443_CO_Ay_2020.tif", published="2023-06-01")
    cache_dir, grid = str(tmp_path / "cache"), _grid(474100, 4426100, 3800)
    tile_a, tile_b = index_tiles(grid)
    _layer().download(grid, cache_dir, None, "test")
    get = tnm.get

    def delisted_in_a(url, params=None, **kwargs):
        response = get(url, params=params, **kwargs)
        if str(url).startswith(TNM_API) and params.get("bbox") == _box(tile_a):
            page = response.json()
            page["items"] = [p for p in page["items"] if p["downloadURL"] != u1]
            page["total"] = len(page["items"])
            return Response(page)
        return response
    monkeypatch.setattr(requests, "get", delisted_in_a)
    _tile_1m(tnm, files, "CO_New_2025", 1025, published="2026-01-01")   # a new file, in both tiles' answers
    layer = _layer()
    layer._use(cache_dir, "all")
    assert layer.tiles(grid) is not None
    assert "still answers at its URL" in capsys.readouterr().out
    a_answer = open(layer.index.index_path(cache_dir, *tile_a), encoding="utf-8").read()
    b_answer = open(layer.index.index_path(cache_dir, *tile_b), encoding="utf-8").read()
    assert "CO_New_2025" not in a_answer and "CO_New_2025" in b_answer


def test_what_a_layer_found_is_forgotten_after_a_raise(tmp_path, monkeypatch, renewing):
    """E7: renew and renew_list forget what the layers found over grids (_listed) also when they raise after a list or
    an answer was written, so no caller composes from what was found before."""
    tnm, state, u1, u2, cache_dir, grid = _scene(tmp_path, monkeypatch)
    _change(tnm, state, u1, u2, cache_dir, "answer")
    layer = _layer()
    layer.index._listed[("before",)] = ["found before the list"]
    with monkeypatch.context() as m:
        m.setattr(renewal, "_settle_carried", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("locked")))
        with pytest.raises(RuntimeError):
            renewal.renew_list(layer, cache_dir, lambda text: None)
    assert layer.index._listed == {}
    # renew's own finally: the list renewed (kept now) without a raise, a Ctrl+C during the answers
    layer.index._listed[("before",)] = ["found before the answers"]
    monkeypatch.setattr(renewal, "_settle_carried", lambda *a, **k: None)
    monkeypatch.setattr(renewal, "_ask_answers", lambda *a, **k: (_ for _ in ()).throw(KeyboardInterrupt()))
    real = renewal.renew_list
    monkeypatch.setattr(renewal, "renew_list", lambda layer, *a, **k: (real(layer, *a, **k),
                                                                       layer.index._listed.update({("x",): []}))[0])
    with pytest.raises(KeyboardInterrupt):
        renewal.renew([layer], grid, cache_dir, lambda text: None)
    assert layer.index._listed == {}


def test_a_searchs_first_answer_of_an_error_body_is_not_cached(tmp_path, monkeypatch, renewing):
    """An error body is never cached as "no files" (for 180 days): a search's first fetch raises, nothing is written,
    and the layer goes on with the cached files (none here)."""
    tnm = Faulty()
    monkeypatch.setattr(requests, "get", tnm.get)
    _tile_1m(tnm, tmp_path / "files", "CO_Full_2013", 1013)
    tnm.fault, tnm.times = "error", 99
    layer, cache_dir, grid = _layer(), str(tmp_path / "cache"), _grid()
    layer._use(cache_dir, None)
    assert layer.tiles(grid) is None
    assert not os.path.exists(layer.index.index_path(cache_dir, *index_tiles(grid)[0]))


def test_other_indexes_write_what_they_get_as_before(tmp_path):
    """An index whose layer does not renew (confirms_drops off: every other country) writes an answer lacking files
    at once, one request, as before."""
    from sources.indexes.cached import CachedIndex, Listing

    class Two(Listing):
        url, asked = "https://index.example", 0

        def fetch(self, lat, lon):
            Two.asked += 1
            return {"sheets": [{"url": "a"}, {"url": "b"}][:3 - Two.asked]}
    index = CachedIndex("x", Two(), None, "p", "top")
    cache_dir = str(tmp_path)
    assert len(index.answers(cache_dir, 50.0, 10.0)) == 2
    assert index.answers(cache_dir, 50.0, 10.0, "all") == [{"url": "a"}] and Two.asked == 2
    assert src.SOURCES["usa"].nmt.index.confirms_drops and not src.SOURCES["british_columbia"].nmt.index.confirms_drops


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


def test_a_failure_dated_in_the_future_blocks_nothing(tmp_path):
    """C8: a failure record dated after now (the clock was set back after it was written) does not block a listing;
    one of an hour ago does."""
    from datetime import datetime, timedelta, timezone
    cache_dir = str(tmp_path)
    for hours, blocks in ((-1, True), (48, False)):
        os.makedirs(os.path.dirname(tb.failed_path(cache_dir)), exist_ok=True)
        with open(tb.failed_path(cache_dir), "w", encoding="utf-8") as f:
            json.dump({"at": (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat(timespec="seconds"),
                       "error": "x"}, f)
        assert (tb.failed_recently(cache_dir) is not None) == blocks


def test_two_renewals_at_once_list_once_and_ask_each_answer_once(http_server, tmp_path, monkeypatch, renewing):
    """Two renewals of one data folder at the same moment (two rows started together): the bucket is listed once,
    the second renewal takes the list the first made; every answer of an index tile is asked once."""
    tnm, files, cache_dir = _start(tmp_path, monkeypatch, http_server, delay=0.2, bucket_delay=0.2)
    grid = _grid(440000, 4400000, 30000)
    results = []
    together = threading.Barrier(2)  # both renewals start at the same moment, however loaded the machine

    def one():
        layer = _layer(http_server.base)
        together.wait()
        results.append(renewal.renew([layer], grid, cache_dir, lambda text: None))
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
    monkeypatch.setattr(renewal, "LIST_LOCK_WAIT_S", 1.0)
    lock = FileLock(os.path.join(cache_dir, cache.LOCKS, "renewal", "usa-bucket1m.lock"))
    os.makedirs(os.path.dirname(lock.lock_file), exist_ok=True)
    said, when = [], []
    started = time.monotonic()

    def say(text):
        said.append(text)
        when.append(time.monotonic() - started)
    with lock:
        done = threading.Thread(target=lambda: said.append(
            renewal.renew([_layer(http_server.base)], _grid(), cache_dir, say)))
        done.start()
        done.join()
    assert said[-1].list == "kept" and _bucket_requests(http_server) == 0
    assert "waiting for it (at most" in said[0] and "(waited" in said[1]
    assert when[1] - when[0] >= 0.9  # the first line said before the wait (of 1 s), the second after it


def test_the_catalogues_layer_lists_usgs_itself(tmp_path, monkeypatch, renewing):
    """The catalogue's 1 m layer makes its list from USGS's own bucket, index, dataset and boxes (what the tool and
    the shipped copy use); the list made, nothing else asked here."""
    asked = {}

    def make(cache_dir, **kwargs):
        asked.update(kwargs)
        raise tb.IndexUnavailable("not asked in a test")
    monkeypatch.setattr(tb, "make_unlisted", make)
    done = renewal.renew_list(src.SOURCES["usa"].nmt, str(tmp_path / "cache"), lambda text: None, force=True)
    assert done.list == "failed"
    assert (asked["bucket"], asked["api"], asked["dataset"], asked["regions"]) == (tb.BUCKET, tb.TNM_API, tb.DATASET,
                                                                                   tb.REGIONS)


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


def test_block_names_stay_without_a_tied_list_file():
    """The key rule (versions.block_key) names every block as before unless a file of the list of unlisted files
    shares its year with another file of the block: every block of every other layer and every block cached before
    keeps its name; a list file alone in its year too; a tied one enters with its date, so its date names the block."""
    import hashlib
    from sources.indexes.cached import EXTRA
    from sources.indexes.versions import block_key

    def before(files):  # the key as it always was
        return hashlib.sha1(",".join(sorted(f["name"] for f in files)).encode()).hexdigest()[:8]
    listed = [{"name": "USGS_1M_13_x47y443_CO_Bee_2020", "year": 2020, "published": "2024-01-01"},
              {"name": "USGS_1M_13_x47y443_CO_Cee_2020", "year": 2020, "published": "2025-01-01"},
              {"name": "USGS_1M_13_x47y443_CO_Full_2013", "year": 2013, "published": "2016-01-01"}]
    assert block_key(listed) == before(listed) == "7b7f6199"
    alone = listed + [{"name": "USGS_1M_13_x47y443_CO_Ay_2019", "year": 2019, "published": "2026-02-12", EXTRA: True}]
    assert block_key(alone) == before(alone)
    tied = listed + [{"name": "USGS_1M_13_x47y443_CO_Ay_2020", "year": 2020, "published": "2026-02-12", EXTRA: True}]
    moved = listed + [dict(tied[-1], published="2026-06-01")]
    assert len({block_key(tied), block_key(moved), before(tied)}) == 3


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


def _name(url):
    return url.rsplit("/", 1)[-1]


def _fake_listing(monkeypatch, state, tnm):
    """tnmbucket.make_unlisted writing state["list"] (its own tests list a stand-in bucket): the renewal's rules are
    tested here with files the blocks can read (local paths). The bucket's listing holds the list's files, the
    index's (tnm's products) and state["left_out"] (names left out without a zone), less state["missing"] (names a
    listing lacked); the index's national listing holds tnm's products and state["listed"] (names whose products
    map to no item in a tile's answer)."""
    def make(cache_dir, out=None, found=None, **kwargs):
        state.setdefault("made", 0)
        state["made"] += 1
        path = out or tb.unlisted_path(cache_dir)
        tb.write_list(path, {"made_at": cache.now_iso(), "files": len(state["list"]), "listed": 1,
                             "left_out": list(state.get("left_out", []))}, list(state["list"]), "b", "a", "d")
        if out is None:
            cache.record(cache_dir, path, url="b")
            tb.forget_unlisted()
        if found is not None:
            listed = {_name(p["downloadURL"]) for p in tnm.products} | set(state.get("listed", ()))
            found["listed"] = listed
            found["bucket"] = (listed | {_name(i["url"]) for i in state["list"]} | set(state.get("left_out", ()))) \
                - set(state.get("missing", ()))
        return {"made_at": cache.now_iso(), "files": len(state["list"]), "listed": 1,
                "left_out": list(state.get("left_out", [])),
                "requests": {"bucket": 1, "index": 1, "headers": 0}, "answer_bytes": {"bucket": 1, "index": 1},
                "seconds_by_part": {"bucket": 0.0, "index": 0.0, "headers": 0.0}}
    monkeypatch.setattr(tb, "make_unlisted", make)


def test_a_file_the_index_lists_since_reorders_its_blocks(tmp_path, monkeypatch, renewing):
    """(a), point 9c: two files of one year over the same blocks: the unlisted one first (its upload time is the later
    date), then the index lists it with an earlier date and it leaves the list. The order flips, and with it the
    blocks' names (block_key: the tied list file's date was in them): the pass after the renewal reads them under
    their new names, prunes the old ones, and they equal those of a data folder that never had the list."""
    tnm, files = Tnm(), tmp_path / "files"
    monkeypatch.setattr(requests, "get", tnm.get)
    _tile_1m(tnm, files, "CO_Bee_2020", 1001, published="2024-01-01")                        # listed
    unlisted = _tile_1m(FakeTnm(), files, "CO_Ay_2020", 1002, name="USGS_1M_13_x47y443_CO_Ay_2020.tif")
    state = {"list": [tile_item(unlisted, 13, "2026-02-12T17:17:41.000Z")]}
    _fake_listing(monkeypatch, state, tnm)
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
    assert (done.list, done.departed) == ("made", 1)
    assert _block_files(folder) == names                               # nothing deleted by the renewal
    again = _layer()
    again.download(grid, cache_dir, None, "test")
    after = _block_files(folder)
    assert len(after) == 4 and not set(after) & set(names)             # new names; the old ones pruned
    assert (_mosaic(again, grid, cache_dir, tmp_path, "b") == 1001).all()
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
    _fake_listing(monkeypatch, state, tnm)
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


U2_BEFORE, U2_AFTER = "2025-06-01T10:00:00.000Z", "2026-06-01T10:00:00.000Z"


def _scene(tmp_path, monkeypatch):
    """B listed (2020, 1001, published 2024-01-01); U1 (2020, 1002, uploaded 2026-02-12) and U2 (2020, 1004, uploaded
    2025-06-01) unlisted: the blocks read U1 first (1002). The list made, the blocks downloaded."""
    tnm, files = Tnm(), tmp_path / "files"
    monkeypatch.setattr(requests, "get", tnm.get)
    _tile_1m(tnm, files, "CO_Bee_2020", 1001, published="2024-01-01")
    u1 = _tile_1m(FakeTnm(), files, "CO_Ay_2020", 1002, name="USGS_1M_13_x47y443_CO_Ay_2020.tif")
    u2 = _tile_1m(FakeTnm(), files, "CO_Dee_2020", 1004, name="USGS_1M_13_x47y443_CO_Dee_2020.tif")
    state = {"list": [tile_item(u1, 13, "2026-02-12T17:17:41.000Z"), tile_item(u2, 13, U2_BEFORE)]}
    _fake_listing(monkeypatch, state, tnm)
    cache_dir, grid = str(tmp_path / "cache"), _grid()
    renewal.renew([_layer()], grid, cache_dir, lambda text: None)
    _layer().download(grid, cache_dir, None, "test")
    assert (_mosaic(_layer(), grid, cache_dir, tmp_path, "scene") == 1002).all()
    return tnm, state, u1, u2, cache_dir, grid


def _change(tnm, state, u1, u2, cache_dir, what="both"):
    """What changes, each alone turning the order of the blocks while their names stay (the same files, the same
    newest year), U2 read first then (1004): "answer", the index lists U1 now, dated 2023-06-01 (it leaves the list);
    "list", U2 stays in the list with a later upload date (C7: uploaded again); "both"."""
    if what in ("answer", "both"):
        tnm.add(u1, "EPSG:26913", EXTENT, published="2023-06-01")
    u1_item = [] if what in ("answer", "both") else [state["list"][0]]
    state["list"] = u1_item + [tile_item(u2, 13, U2_AFTER if what in ("list", "both") else U2_BEFORE)]
    _age(cache_dir, tb.unlisted_path(cache_dir), 29)
    _settle(cache_dir)


def _fresh(tmp_path, grid, name="fresh"):
    """A data folder that never had the list before: the list made as it is now, the blocks downloaded."""
    fresh_dir = str(tmp_path / name)
    renewal.renew([_layer()], grid, fresh_dir, lambda text: None)
    _layer().download(grid, fresh_dir, None, "test")
    return fresh_dir


def test_why_files_left_the_list(http_server, tmp_path, monkeypatch, renewing):
    """Point 2: a file the index lists now is carried until the cached answers hold it; a file the bucket's listing
    lacked has its project listed again: gone there too, it leaves (its blocks are read again without it, the old
    ones pruned); there after all (a page of the listing missing), it stays; a file left out without a zone this time
    keeps its item of before. The counts of each are returned; the blocks then equal a fresh folder's."""
    tnm, files = Tnm(), tmp_path / "files"
    monkeypatch.setattr(requests, "get", tnm.get)
    _tile_1m(tnm, files, "CO_Bee_2016", 1001, published="2024-01-01")
    unlisted = {k: _tile_1m(FakeTnm(), files, project, value, name=f"USGS_1M_13_x47y443_{project}.tif")
                for k, project, value in (("I", "CO_Eye_2020", 1020), ("G", "CO_Gee_2019", 1019),
                                          ("R", "CO_Arr_2018", 1018), ("Z", "CO_Zed_2017", 1017))}
    item = {k: tile_item(url, 13, "2026-02-12T17:17:41.000Z") for k, url in unlisted.items()}
    state = {"list": list(item.values())}
    _fake_listing(monkeypatch, state, tnm)
    relisted = (f"{tb.PROJECTS}CO_Arr_2018/TIFF/{_name(unlisted['R'])}", 1000, "2026-02-10T10:00:00.000Z")
    _bucket(http_server, tnm, [relisted])
    cache_dir, grid = str(tmp_path / "cache"), _grid()
    renewal.renew([_layer(http_server.base)], grid, cache_dir, lambda text: None)
    _layer(http_server.base).download(grid, cache_dir, None, "test")
    assert (_mosaic(_layer(), grid, cache_dir, tmp_path, "a") == 1020).all()

    tnm.add(unlisted["I"], "EPSG:26913", EXTENT, published="2026-03-01")   # the index lists I now
    state.update({"list": [], "missing": [_name(unlisted["R"])], "left_out": [_name(unlisted["Z"])]})  # G: gone
    _age(cache_dir, tb.unlisted_path(cache_dir), 29)
    _settle(cache_dir)
    said = []
    done = renewal.renew([_layer(http_server.base)], grid, cache_dir, said.append)
    assert (done.list, done.departed, done.indexed, done.carried, done.gone, done.relisted, done.zoneless) == \
        ("made", 4, 1, 1, 1, 1, 1)
    assert done.requests["list recheck"] >= 2 and "1 because the bucket no longer holds them" in "\n".join(said)
    assert sorted(_name(u) for u in tb.list_items(cache_dir)) == sorted(_name(unlisted[k]) for k in "IRZ")
    assert tb.carried_urls(cache_dir) == [unlisted["I"]]
    folder = os.path.join(cache_dir, "usa", "test1m", "epsg26913", "47_442")
    before = _block_files(folder)
    _layer(http_server.base).download(grid, cache_dir, None, "test")       # G's blocks read again without it
    assert not set(before) & set(_block_files(folder)) and len(_block_files(folder)) == 4
    state.pop("missing")
    state.update({"list": [item["R"], item["Z"]], "left_out": []})
    _blocks_equal(cache_dir, _fresh(tmp_path, grid))


def test_a_carried_file_stays_while_its_answers_fail(tmp_path, monkeypatch, renewing):
    """C2a: the index lists a file now but its answers cannot be asked: the list keeps carrying it, so the same pass
    keeps the good blocks and reads them; another process reading the list meanwhile finds it there (C2b); the next
    renewal asks the answers again and the blocks then equal a fresh folder's."""
    tnm, state, u1, u2, cache_dir, grid = _scene(tmp_path, monkeypatch)
    folder = os.path.join(cache_dir, "usa", "test1m", "epsg26913", "47_442")
    names = _block_files(folder)
    tnm.add(u1, "EPSG:26913", EXTENT, published="2023-06-01")
    state["list"] = [state["list"][1]]                                  # U2 as it was: U1 left (the index lists it)
    _age(cache_dir, tb.unlisted_path(cache_dir), 29)
    _settle(cache_dir)
    tnm.offline = True
    done = renewal.renew([_layer()], grid, cache_dir, lambda text: None)
    assert (done.list, done.indexed, done.carried, done.asked) == ("made", 1, 1, 0) and done.failed >= 1
    assert u1 in tb.list_items(cache_dir) and tb.carried_urls(cache_dir) == [u1]
    _layer().download(grid, cache_dir, None, "test")
    assert _block_files(folder) == names and (_mosaic(_layer(), grid, cache_dir, tmp_path, "b") == 1002).all()

    tnm.offline = False
    seen = []
    get = tnm.get

    def watching(url, params=None, **kwargs):                           # another process reads the list meanwhile
        tb.forget_unlisted()
        seen.append(u1 in tb.list_items(cache_dir))
        return get(url, params=params, **kwargs)
    monkeypatch.setattr(requests, "get", watching)
    _settle(cache_dir)
    done = renewal.renew([_layer()], grid, cache_dir, lambda text: None)
    assert done.list == "kept" and done.failed == 0 and done.asked >= 1 and seen and all(seen)
    _layer().download(grid, cache_dir, None, "test")
    _blocks_equal(cache_dir, _fresh(tmp_path, grid))


def test_only_the_answers_lacking_a_carried_file_are_asked(tmp_path, monkeypatch, renewing):
    """Of the cached answers a file the index lists now reaches, only those lacking its URL are asked again (the
    list's renewal alone, as `cache update` runs it)."""
    from sources.renewal import _tiles_met
    tnm, files = Tnm(), tmp_path / "files"
    monkeypatch.setattr(requests, "get", tnm.get)
    _tile_1m(tnm, files, "CO_Bee_2020", 1001)
    u1 = _tile_1m(FakeTnm(), files, "CO_Ay_2020", 1002, name="USGS_1M_13_x47y443_CO_Ay_2020.tif")
    state = {"list": [tile_item(u1, 13, "2026-02-12T17:17:41.000Z")]}
    _fake_listing(monkeypatch, state, tnm)
    cache_dir, layer = str(tmp_path / "cache"), _layer()
    renewal.renew_list(layer, cache_dir, lambda text: None)
    tiles = _tiles_met(state["list"][0])
    assert len(tiles) == 4
    layer.index.answers(cache_dir, *tiles[0])                           # cached before the index listed U1
    layer.index.answers(cache_dir, *tiles[1])
    tnm.add(u1, "EPSG:26913", EXTENT, published="2023-06-01")
    layer.index.answers(cache_dir, *tiles[2])                           # cached after: holds it; tiles[3]: none
    state["list"] = []
    _age(cache_dir, tb.unlisted_path(cache_dir), 29)
    _settle(cache_dir)
    tnm.asked.clear()
    done = renewal.renew_list(_layer(), cache_dir, lambda text: None)
    assert (done.indexed, done.carried, done.asked) == (1, 1, 2)
    assert sorted(tnm.tile_requests()) == sorted(f"{lon},{lat},{lon + 0.25},{lat + 0.25}" for lat, lon in tiles[:2])
    done = renewal.renew_list(_layer(), cache_dir, lambda text: None)  # the next start: nothing left to ask
    assert (done.list, done.asked) == ("kept", 0)


def test_a_file_whose_date_changes_in_the_list_reorders_its_blocks(tmp_path, monkeypatch, renewing):
    """(d), C7: a file that stays in the list with another date (U2 uploaded again, after U1) changes the order of the
    blocks and with it their names (U2 is tied on its year): the next pass reads them under their new names, prunes
    the old ones, and they equal a fresh folder's."""
    tnm, state, u1, u2, cache_dir, grid = _scene(tmp_path, monkeypatch)
    folder = os.path.join(cache_dir, "usa", "test1m", "epsg26913", "47_442")
    names = _block_files(folder)
    _change(tnm, state, u1, u2, cache_dir, "list")
    done = renewal.renew([_layer()], grid, cache_dir, lambda text: None)
    assert (done.list, done.departed) == ("made", 0)
    _layer().download(grid, cache_dir, None, "test")
    assert not set(names) & set(_block_files(folder))
    assert (_mosaic(_layer(), grid, cache_dir, tmp_path, "after") == 1004).all()
    _blocks_equal(cache_dir, _fresh(tmp_path, grid))


class ByBox(Tnm):
    """The TNM API answering a tile with the products whose boundingBox meets its own box (as the real one does: the
    second review's D1 stand-in)."""

    def get(self, url, params=None, **kwargs):
        if not str(url).startswith(TNM_API):
            return super().get(url, params=params, **kwargs)
        w, s, e, n = (float(v) for v in params["bbox"].split(","))
        everything = self.products
        self.products = [p for p in everything if p["boundingBox"]["minX"] < e and p["boundingBox"]["maxX"] > w
                         and p["boundingBox"]["minY"] < n and p["boundingBox"]["maxY"] > s]
        try:
            return super().get(url, params=params, **kwargs)
        finally:
            self.products = everything


AZ = (560000, 3650000, 570000, 3660000)  # zone 12, x56 y366: its box ends 0.00002° west of the tile edge -110.25


def _az_scene(tmp_path, monkeypatch):
    """D1's scene: B listed (2020, published 2024-01-01), U unlisted (2020, uploaded 2026-02-12) in one 10 km cell
    whose box meets one index tile and comes within INDEX_MARGIN_DEG of the next; the list made, the blocks of a grid
    across the tile edge downloaded; then the index lists U, dated 2023-06-01 (B read first)."""
    tnm, files = ByBox(), tmp_path / "files"
    monkeypatch.setattr(requests, "get", tnm.get)
    _tile_1m(tnm, files, "AZ_Bee_2020", 1001, zone=12, x=56, y=366, published="2024-01-01")
    u = _tile_1m(FakeTnm(), files, "AZ_Ay_2020", 1002, zone=12, x=56, y=366, name="USGS_1M_12_x56y366_AZ_Ay_2020.tif")
    state = {"list": [tile_item(u, 12, "2026-02-12T17:17:41.000Z")]}
    _fake_listing(monkeypatch, state, tnm)
    cache_dir = str(tmp_path / "cache")
    inside = gd.make_grid((568100, 3655100, 569900, 3656900), RES, "EPSG:26912")
    across = gd.make_grid((568100, 3655100, 571900, 3656900), RES, "EPSG:26912")
    assert len(index_tiles(inside)) == 1 and len(index_tiles(across)) == 2
    renewal.renew([_layer()], across, cache_dir, lambda text: None)
    _layer().download(across, cache_dir, None, "test")
    tnm.add(u, "EPSG:26912", AZ, published="2023-06-01")
    state["list"] = []
    return tnm, state, u, cache_dir, inside, across


def test_a_file_the_index_lists_since_leaves_the_list(tmp_path, monkeypatch, renewing):
    """D1 (a): over four starts with listings at the 1st and 3rd, a file the index lists now is carried only while
    the tile its box meets lacks it: that tile is asked once, the tile it reaches only through the margin never, and
    the second listing drops the file."""
    tnm, state, u, cache_dir, inside, across = _az_scene(tmp_path, monkeypatch)
    meeting, margin = index_tiles(across)
    box = lambda t: f"{t[1]},{t[0]},{t[1] + 0.25},{t[0] + 0.25}"  # noqa: E731
    asked = []
    _settle(cache_dir)
    for start, listing in enumerate((True, False, True, False), 1):
        if listing:
            _age(cache_dir, tb.unlisted_path(cache_dir), 29)
        tnm.asked.clear()
        done = renewal.renew_list(_layer(), cache_dir, lambda text: None)
        asked.append(sorted(tnm.tile_requests()))
        if start == 1:
            assert (done.list, done.indexed, done.carried) == ("made", 1, 1)
        if start == 3:
            assert (done.list, done.indexed, done.carried) == ("made", 1, 0)
    assert asked == [[box(meeting)], [], [], []]
    assert tb.carried_urls(cache_dir) == [] and u not in tb.list_items(cache_dir)


def test_a_file_carried_for_a_real_reason_costs_one_ask_a_listing(tmp_path, monkeypatch, renewing):
    """A file the index's listing names but whose product maps to no item in a tile's answer stays carried (rightly:
    the list is its only source); the tile lacking it is asked at most once per listing, not at every start."""
    tnm, state, u, cache_dir, inside, across = _az_scene(tmp_path, monkeypatch)
    tnm.products = [p for p in tnm.products if p["downloadURL"] != u]   # no tile's answer will hold it
    state["listed"] = [_name(u)]                                        # the national listing names it
    meeting = index_tiles(across)[0]
    box = f"{meeting[1]},{meeting[0]},{meeting[1] + 0.25},{meeting[0] + 0.25}"
    asked = []
    for start, listing in enumerate((True, False, False, True, False), 1):
        _settle(cache_dir)  # a later start: the answers asked 10 s ago, before this start's own time
        if listing:  # weeks later: the answers asked before are older than the new list
            _age(cache_dir, tb.unlisted_path(cache_dir), 29)
        else:        # the list made before those answers were asked (20 s ago)
            _age(cache_dir, tb.unlisted_path(cache_dir), 20 / 86400)
        tnm.asked.clear()
        done = renewal.renew_list(_layer(), cache_dir, lambda text: None)
        asked.append(sorted(tnm.tile_requests()))
        assert done.failed == 0 and tb.carried_urls(cache_dir) == [u]
    assert asked == [[box], [], [], [box], []]


def test_a_carried_files_blocks_do_not_depend_on_the_grid(tmp_path, monkeypatch, renewing):
    """D1 (b): while the list carries a file the index lists now, a tile whose answer lacks it still merges the
    list's item (its upload date); the answer's item wins whatever the grid: the same block is composed equally by a
    grid inside the cell and one across the tile edge, and as a fresh folder composes it."""
    tnm, state, u, cache_dir, inside, across = _az_scene(tmp_path, monkeypatch)
    _age(cache_dir, tb.unlisted_path(cache_dir), 29)
    _settle(cache_dir)
    done = renewal.renew_list(_layer(), cache_dir, lambda text: None)
    assert done.carried == 1 and tb.carried_urls(cache_dir) == [u]

    def files_of(grid, folder):
        layer = _layer()
        layer._use(folder, None)
        return {(b.i, b.j): [n for n, _, _ in b.files] for b in layer.tiles(grid) if (b.i, b.j) == (568, 3655)}
    fresh_dir = str(tmp_path / "fresh")
    renewal.renew([_layer()], across, fresh_dir, lambda text: None)
    fresh = files_of(across, fresh_dir)
    assert fresh == {(568, 3655): ["USGS_1M_12_x56y366_AZ_Bee_2020", "USGS_1M_12_x56y366_AZ_Ay_2020"]}
    assert files_of(inside, cache_dir) == files_of(across, cache_dir) == fresh


STOPS = ["listing made", "departures decided", "list written", "list recorded", "answer fetched", "answer written"]


def _stop_at(monkeypatch, stop, kind, fired):
    """A stop (the exception kind standing in for a kill) between two steps of the list's or an answer's renewal."""
    from sources.indexes.cached import CachedIndex

    def fire():
        fired.append(stop)
        raise kind(f"stopped: {stop}")

    def after(real):
        def wrapped(*args, **kwargs):
            out = real(*args, **kwargs)
            fire()
            return out
        return wrapped
    if stop == "listing made":
        monkeypatch.setattr(tb, "make_unlisted", after(tb.make_unlisted))
    elif stop == "departures decided":
        monkeypatch.setattr(renewal, "_departures", after(renewal._departures))
    elif stop in ("list written", "list recorded"):
        write = tb.write_list
        monkeypatch.setattr(tb, "write_list", lambda path, *a, **k: (write(path, *a, **k), not path.endswith(".new")
                                                                     and stop == "list written" and fire()))
        if stop == "list recorded":
            monkeypatch.setattr(renewal, "_settle_carried", lambda *a, **k: fire())
    elif stop == "answer fetched":
        monkeypatch.setattr(CachedIndex, "_fetch", after(CachedIndex._fetch))
    elif stop == "answer written":
        monkeypatch.setattr(CachedIndex, "_store", after(CachedIndex._store))


@pytest.mark.parametrize("kind", [RuntimeError, KeyboardInterrupt])
@pytest.mark.parametrize("stop", STOPS)
@pytest.mark.parametrize("what", ["answer", "list"])
def test_a_stop_anywhere_leaves_rightly_named_blocks(tmp_path, monkeypatch, renewing, what, stop, kind):
    """Point 3 (C2c, C7) under the key rule: a renewal stopped between any two steps of the list's renewal (made,
    departures decided, written, recorded) or of an answer's (fetched, written), by an exception or a Ctrl+C, for a
    change of the answers (a file the index lists now) and one of the list (C7) each alone; a pass then; a second
    renewal (a day later: a failed listing's record cleared) and a pass: the blocks equal a fresh folder's, the
    blocks of the old names gone. (The steps "the reordered blocks deleted" went with the deletions themselves.)"""
    tnm, state, u1, u2, cache_dir, grid = _scene(tmp_path, monkeypatch)
    _change(tnm, state, u1, u2, cache_dir, what)
    fired = []
    with monkeypatch.context() as m:
        _stop_at(m, stop, kind, fired)
        try:
            renewal.renew([_layer()], grid, cache_dir, lambda text: None)
        except kind:  # what the callers do: a fault of the renewal never stops their pass
            pass
    assert fired
    _layer().download(grid, cache_dir, None, "test")                     # a pass after the stop: right names
    tb.clear_failed(cache_dir)
    tb.forget_unlisted()
    _settle(cache_dir)
    renewal.renew([_layer()], grid, cache_dir, lambda text: None)
    _layer().download(grid, cache_dir, None, "test")
    assert (_mosaic(_layer(), grid, cache_dir, tmp_path, "after") == 1004).all()
    _blocks_equal(cache_dir, _fresh(tmp_path, grid))


def test_a_stop_in_the_settling_is_made_good_by_a_renewal_elsewhere(tmp_path, monkeypatch, renewing):
    """D2 (C2c): a renewal stopped (Ctrl+C) while it settles the carried files, after the list was written; a pass;
    then a renewal over ANOTHER grid, whose own answers do not reach the file: it settles the carried file all the
    same (the list kept), so the next pass's blocks equal a fresh folder's."""
    tnm, state, u1, u2, cache_dir, grid = _scene(tmp_path, monkeypatch)
    _change(tnm, state, u1, u2, cache_dir, "answer")
    with monkeypatch.context() as m:
        m.setattr(renewal, "_ask_answers", lambda *a, **k: (_ for _ in ()).throw(KeyboardInterrupt()))
        with pytest.raises(KeyboardInterrupt):
            renewal.renew([_layer()], grid, cache_dir, lambda text: None)
    assert tb.carried_urls(cache_dir) == [u1]
    _layer().download(grid, cache_dir, None, "test")
    elsewhere = _grid(400100, 4424100)                                 # x40: 70 km west, none of U1's tiles
    assert not set(index_tiles(elsewhere)) & set(index_tiles(grid))
    done = renewal.renew([_layer()], elsewhere, cache_dir, lambda text: None)
    assert done.list == "kept" and done.asked >= 1
    _layer().download(grid, cache_dir, None, "test")
    _blocks_equal(cache_dir, _fresh(tmp_path, grid))


GRID_B = (474100, 4428100)  # inside index tile B (40.0, -105.5); _grid() is inside tile A (39.75, -105.5)


def _down(monkeypatch, tnm, boxes):
    """The stand-in TNM index not answering for these boxes (tiles)."""
    get = tnm.get

    def answering(url, params=None, **kwargs):
        if str(url).startswith(TNM_API) and params and params.get("bbox") in boxes:
            raise requests.ConnectionError("the service does not answer this tile")
        return get(url, params=params, **kwargs)
    monkeypatch.setattr(requests, "get", answering)


def _box(tile):
    return f"{tile[1]},{tile[0]},{tile[1] + 0.25},{tile[0] + 0.25}"


def _fresh_of(tmp_path, grids, name="fresh"):
    fresh_dir = str(tmp_path / name)
    renewal.renew([_layer()], grids[0], fresh_dir, lambda text: None)
    for grid in grids:
        _layer().download(grid, fresh_dir, None, "test")
    return fresh_dir


def test_a_grid_reading_a_tile_not_renewed_yet(tmp_path, monkeypatch, renewing):
    """The third review's E1 through the real entry points: the index lists U1 now; a renewal asks tile A (its grid)
    while tile B fails; a grid reading only B then composes its blocks from the list's item of U1 (the old order),
    under the name that order has; B renewed later, a pass: the blocks of both grids equal a fresh folder's and the
    blocks of the old names are gone."""
    tnm, state, u1, u2, cache_dir, grid = _scene(tmp_path, monkeypatch)
    grid_b = _grid(*GRID_B)
    tile_a, tile_b = index_tiles(grid)[0], index_tiles(grid_b)[0]
    assert (tile_a, tile_b) == ((39.75, -105.5), (40.0, -105.5))
    _layer().download(grid_b, cache_dir, None, "test")
    folder = os.path.join(cache_dir, "usa", "test1m", "epsg26913", "47_442")
    before = _block_files(folder)
    _change(tnm, state, u1, u2, cache_dir, "answer")
    with monkeypatch.context() as m:
        _down(m, tnm, {_box(tile_b)})
        done = renewal.renew([_layer()], grid, cache_dir, lambda text: None)
    assert done.carried == 1 and done.failed == 1
    _layer().download(grid_b, cache_dir, None, "test")                 # B's blocks: the old order, their old names
    b_blocks = {n for n in before if "_4428_" in n or "_4429_" in n}
    assert b_blocks <= set(_block_files(folder))
    _settle(cache_dir)
    renewal.renew([_layer()], grid_b, cache_dir, lambda text: None)    # B renewed
    for g in (grid, grid_b):
        _layer().download(g, cache_dir, None, "test")
    assert not b_blocks & set(_block_files(folder))
    _blocks_equal(cache_dir, _fresh_of(tmp_path, [grid, grid_b]))


def test_two_grids_name_their_blocks_by_the_order_they_read(tmp_path, monkeypatch, renewing):
    """(f): while tile A's answer holds U1 (the index's date) and tile B's does not (the list's), a grid reading only
    B and a grid across A and B compose the same square in two orders, each under the name its order has (B's: U1
    first, 1002; across: U2 first, 1004); once both answers hold it, one name is left after a pass."""
    from sources.indexes.cached import EXTRA
    from sources.indexes.versions import block_key
    tnm, state, u1, u2, cache_dir, grid = _scene(tmp_path, monkeypatch)
    grid_b, across = _grid(*GRID_B), _grid(474100, 4426100, 3800)
    assert len(index_tiles(across)) == 2 and len(index_tiles(grid_b)) == 1
    _layer().download(grid_b, cache_dir, None, "test")                 # B's answer cached before the change
    _change(tnm, state, u1, u2, cache_dir, "answer")
    with monkeypatch.context() as m:
        _down(m, tnm, {_box(index_tiles(grid_b)[0])})
        renewal.renew([_layer()], grid, cache_dir, lambda text: None)

    def square(g):
        layer = _layer()
        layer._use(cache_dir, None)
        block, = [b for b in layer.tiles(g) if (b.i, b.j) == (474, 4428)]
        layer.download(g, cache_dir, None, "test")
        with rio.open(layer.tile_path(cache_dir, block)) as src:
            return block, float(src.read(1)[5, 5])
    b_block, b_value = square(grid_b)
    a_block, a_value = square(across)
    assert (b_value, a_value) == (1002.0, 1004.0) and b_block.key != a_block.key
    assert b_block.files[0][0].endswith("CO_Ay_2020") and a_block.files[0][0].endswith("CO_Dee_2020")
    # the names: U1 by its name alone where an answer gives it, with its upload date where only the list does
    plain = {"name": _name(u2)[:-4], "year": 2020, "published": U2_BEFORE, EXTRA: True}
    bee = {"name": "USGS_1M_13_x47y443_CO_Bee_2020", "year": 2020}
    assert a_block.key == block_key([bee, plain, {"name": _name(u1)[:-4], "year": 2020}])
    assert b_block.key == block_key([bee, plain, {"name": _name(u1)[:-4], "year": 2020,
                                                  "published": "2026-02-12T17:17:41.000Z", EXTRA: True}])
    _settle(cache_dir)
    renewal.renew([_layer()], grid_b, cache_dir, lambda text: None)    # B holds U1 now too
    for g in (grid_b, across):
        _layer().download(g, cache_dir, None, "test")
    folder = os.path.join(cache_dir, "usa", "test1m", "epsg26913", "47_442")
    assert [n for n in _block_files(folder) if "_474_4428_" in n] == [os.path.basename(
        _layer().tile_path(cache_dir, a_block))]


def test_cache_update_reads_the_renamed_block_and_keeps_the_old_until_then(tmp_path, monkeypatch, renewing):
    """(e) and C5 under the key rule: `cache update` on a tile whose answer now holds U1 (tied on its year, the index's
    date) reads the blocks under their new names; a read that fails leaves the old block in place (prune deletes it
    only once the new one is there) and fails the update; the next update completes it, equal to a fresh folder's."""
    tnm, state, u1, u2, cache_dir, grid = _scene(tmp_path, monkeypatch)
    folder = os.path.join(cache_dir, "usa", "test1m", "epsg26913", "47_442")
    old = {name: open(os.path.join(folder, name), "rb").read() for name in _block_files(folder)}
    tnm.add(u1, "EPSG:26913", EXTENT, published="2023-06-01")
    state["list"] = [state["list"][1]]
    tile = index_tiles(grid)[0]
    layer = _layer()
    real, calls = layer._download_and_record, []

    def flaky(block, cache_dir_, *args, **kwargs):
        calls.append(block)
        if len(calls) == 1:
            raise RuntimeError("the connection broke")
        return real(block, cache_dir_, *args, **kwargs)
    layer._download_and_record = flaky
    with pytest.raises(RuntimeError, match="the connection broke"):
        layer.update_index_tile(cache_dir, *tile)
    assert set(old) <= set(_block_files(folder))                        # nothing deleted before its replacement
    assert all(open(os.path.join(folder, n), "rb").read() == data for n, data in old.items())
    assert _layer().update_index_tile(cache_dir, *tile)[0] == 4
    assert not set(old) & set(_block_files(folder))
    _blocks_equal(cache_dir, _fresh(tmp_path, grid))


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
    assert "(5 days ago, 3 files); made again after 28 days" in text and "due" not in text
    _age(cache_dir, tb.unlisted_path(cache_dir), 29)
    assert tb.list_status(cache_dir).endswith("made again after 28 days: due")
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
            "pages = [c.get('/?token=t').status_code]\n"
            "print(pages, 'sources.layers.tnm' in sys.modules, 'sources.renewal' in sys.modules, "
            "'sources.layers.tnmbucket' in sys.modules)")
    env = {**os.environ, "HTTP_PROXY": "http://127.0.0.1:9", "HTTPS_PROXY": "http://127.0.0.1:9", "NO_PROXY": ""}
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120, env=env)
    assert result.returncode == 0, result.stderr
    # the pages were served (so the test cannot pass on a process that served nothing) and the catalogue with the
    # TNM layers was loaded, without the renewal and the list
    assert result.stdout.strip().splitlines()[-1] == "[200] True False False"
