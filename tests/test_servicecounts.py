"""The counts of the requests to outside services (servicecounts.py; docs/monitoring.md F11): the
outcomes, the totals in jobs.sqlite (Jobs.add_service_requests, migration 14), the tiles of the
elevation layers (F18: Jobs.add_layer_downloads, migration 15), nothing counted
unless the web worker turns the counting on or a command-line search names a file
(FINDALINE_SERVICE_COUNTS: counted_into, its summary; tests/regression.py), and the
hooks of the code that asks outside services, against the local HTTP server (tests/http_server.py)."""

import json
import os
import re
import runpy
import sqlite3
import sys

import pytest
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import jobs as jb  # noqa: E402
import servicecounts as sc  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
CLIP = os.path.join(HERE, "data", "zabi_kon_nmt.tif")


@pytest.fixture
def counting(tmp_path):
    """The counting turned on into a scratch jobs.sqlite (no flushing thread); returns a function giving
    {(host, outcome): (requests, bytes)} after a flush."""
    jobs = jb.Jobs(str(tmp_path))
    sc.enable(jobs.add_service_requests, interval=False)

    def totals():
        sc.flush()
        db = sqlite3.connect(tmp_path / "jobs.sqlite")
        try:
            return {(h, o): (n, b) for h, o, n, b in
                    db.execute("SELECT host, outcome, requests, bytes FROM service_requests")}
        finally:
            db.close()
    yield totals
    sc.disable()


def test_outcomes():
    assert [sc.outcome_of_status(s) for s in (200, 206, 304, 404, 403, 429, 500, 503)] == [
        "ok", "ok", "ok", "not_found", "http_4xx", "http_4xx", "http_5xx", "http_5xx"]
    assert sc.outcome_of_error(requests.ConnectTimeout()) == "timeout"  # also a ConnectionError
    assert sc.outcome_of_error(requests.ReadTimeout()) == "timeout"
    assert sc.outcome_of_error(requests.ConnectionError()) == "connection"
    assert sc.outcome_of_error(RuntimeError("x")) == "other"
    assert sc.host_of("https://Sheets.Example.org:8443/a?b=1") == "sheets.example.org"
    assert sc.host_of("C:/mirror/slovakia/a.tif") is None and sc.host_of("/data/a.tif") is None
    assert set(sc.OUTCOMES) == {"ok", "not_found", "http_4xx", "http_5xx", "timeout", "connection", "other"}


def test_nothing_counted_unless_enabled(tmp_path):
    """Off by default (the command line without FINDALINE_SERVICE_COUNTS): record() keeps nothing, flush() writes
    nothing."""
    assert not sc.enabled()
    sc.record("https://example.org/a", "ok", 10, 1.0)
    assert sc.take() == []
    jb.Jobs(str(tmp_path))
    sc.flush()
    db = sqlite3.connect(tmp_path / "jobs.sqlite")
    assert db.execute("SELECT COUNT(*) FROM service_requests").fetchone()[0] == 0
    db.close()


def test_totals_add_up(counting, tmp_path):
    """Flushes add to the running totals per (host, outcome); a failed write keeps the counts for the next."""
    sc.record("https://a.example/x", "ok", 100, 0.5)
    sc.record("https://a.example/y", "ok", 50, 0.25)
    sc.record("https://a.example/z", "http_5xx")
    sc.record("https://b.example/", "bogus")  # an unknown outcome is "other"
    sc.record("C:/local/file.tif", "ok", 7)   # not counted
    assert counting() == {("a.example", "ok"): (2, 150), ("a.example", "http_5xx"): (1, 0),
                          ("b.example", "other"): (1, 0)}
    sc.record("https://a.example/x", "ok", 1, 0.1)
    assert counting()[("a.example", "ok")] == (3, 151)
    jobs = jb.Jobs(str(tmp_path))

    def broken(rows):
        raise sqlite3.OperationalError("database is locked")
    sc.enable(broken, interval=False)
    sc.record("https://a.example/x", "ok", 1)
    sc.flush()
    sc.enable(jobs.add_service_requests, interval=False)
    assert counting()[("a.example", "ok")] == (4, 152)


def test_request_context(counting):
    """sc.request: the status noted, else the exception, else ok; an outcome set by the caller wins."""
    with sc.request("https://h.example/1") as counted:
        counted.status, counted.bytes = 503, 3
    with pytest.raises(requests.ReadTimeout):
        with sc.request("https://h.example/2"):
            raise requests.ReadTimeout()
    with sc.request("https://h.example/3") as counted:
        counted.add(5)
    with pytest.raises(RuntimeError):
        with sc.request("https://h.example/4") as counted:
            counted.status = 200
            counted.outcome = "other"
            raise RuntimeError("an error page")
    assert counting() == {("h.example", "http_5xx"): (1, 3), ("h.example", "timeout"): (1, 0),
                          ("h.example", "ok"): (1, 5), ("h.example", "other"): (1, 0)}


def test_get_with_retries(counting, http_server, monkeypatch):
    """sources.net._get counts every attempt: a 500 retried three times, a 404, a 200 that is not data
    (an error page: other) and one with data; the bytes of the bodies."""
    from sources import net
    monkeypatch.setattr(net, "_sleep", lambda attempt: None)
    http_server.add("/bad", b"busy", "text/plain", status=500)
    http_server.add("/page", b"<html>error</html>", "text/html")
    http_server.add("/tile.tif", b"x" * 1000, "image/tiff")
    for path in ("/bad", "/page"):
        with pytest.raises(RuntimeError):
            net._get(http_server.url(path))
    assert net._get(http_server.url("/missing")) is None
    assert net._get(http_server.url("/tile.tif")).content == b"x" * 1000
    found = counting()
    assert found == {("127.0.0.1", "http_5xx"): (3, 12), ("127.0.0.1", "other"): (3, 54),
                     ("127.0.0.1", "not_found"): (1, found[("127.0.0.1", "not_found")][1]),
                     ("127.0.0.1", "ok"): (1, 1000)}


def test_connection_refused(counting, monkeypatch):
    """A host that refuses the connection: one `connection` per attempt."""
    import socket

    from sources import net
    monkeypatch.setattr(net, "_sleep", lambda attempt: None)
    monkeypatch.setenv("NO_PROXY", "127.0.0.1")
    with socket.socket() as s:  # a free port nobody listens on
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    with pytest.raises(RuntimeError):
        net._get(f"http://127.0.0.1:{port}/x", timeout=5)
    assert counting() == {("127.0.0.1", "connection"): (net.RETRIES, 0)}


def test_hooks(counting, http_server, monkeypatch, tmp_path):
    """The other places that ask outside services count their requests: Nominatim (osm._ask), an
    index listing (StacItems), WcsReader's DescribeCoverage, the orthophoto tiles, a streamed download
    (osmextract's extract, its bytes as read) and the windows of a remote file (Windows, one request
    per file of a block; a local file is not counted)."""
    import orthophoto
    import osm
    import osmextract
    from sources.indexes.listings import StacItems
    from sources.readers.wcsreader import WcsReader
    from sources.readers.windows import _read_block
    monkeypatch.setattr(osm, "_nominatim_turn", lambda cache_dir: None)
    monkeypatch.setattr(osm, "BEFORE_REQUEST", None)  # a quota left by another test's process
    monkeypatch.setattr(orthophoto.time, "sleep", lambda s: None)
    http_server.add("/search?q=x", b"[]", "application/json")
    assert osm._ask(http_server.url("/search"), {"q": "x"}, 10, str(tmp_path)) == []
    http_server.add("/stac?limit=100&bbox=19.0,50.0,19.25,50.25", b'{"features": [], "links": []}', "application/json")
    assert StacItems(http_server.url("/stac"), "EPSG:2056", {2.0: 1000}, 1000).fetch(50.0, 19.0) == {"sheets": []}
    reader = WcsReader("test", http_server.url("/wcs"), "dem", "EPSG:3035", 1.0, 100, "image/tiff", ("x", "y"),
                       None, False)
    assert reader.coverage_extent() is None  # 404: unknown extent
    http_server.add("/tile.jpg", b"\xff\xd8 jpeg", "image/jpeg")
    assert orthophoto._get(http_server.url("/tile.jpg"), None, 1, 0, 0) == b"\xff\xd8 jpeg"
    http_server.add("/region.osm.pbf", b"p" * 3000)
    monkeypatch.setattr(osmextract, "region", lambda cache_dir, name: {
        "properties": {"id": "r", "urls": {"pbf": http_server.url("/region.osm.pbf")}}, "geometry": None})
    monkeypatch.setattr(osmextract, "_index", lambda cache_dir: {})
    monkeypatch.setattr(osmextract, "_country", lambda regions, rid: "r")
    monkeypatch.setattr(osmextract, "_finish", lambda *args: None)
    monkeypatch.setattr(osmextract.cache, "record", lambda *args, **kwargs: None)
    osmextract.download(str(tmp_path / "cache"), "r")
    with open(CLIP, "rb") as f:
        http_server.add("/clip.tif", f.read(), "image/tiff")
    import rasterio as rio
    with rio.open(CLIP) as clip:
        crs, transform = clip.crs.to_string(), clip.transform
    _read_block([("clip", http_server.url("/clip.tif"), 2020), ("gone", http_server.url("/gone.tif"), 2019),
                 ("local", CLIP, 2018)], crs, transform, (10, 10), str(tmp_path / "block.tif"), "test")
    found = counting()
    assert found[("127.0.0.1", "ok")][0] == 5  # Nominatim, STAC, the tile, the extract, the window
    assert found[("127.0.0.1", "not_found")][0] == 1  # DescribeCoverage (/gone.tif not read: the block was full)
    assert found[("127.0.0.1", "ok")][1] >= 3000 + 2 + len(b"\xff\xd8 jpeg")


def test_windows_missing_file(counting, http_server, tmp_path):
    """A file of a block that is not there (404 through GDAL) counts as not_found."""
    import rasterio as rio
    from sources.readers.windows import _read_block
    with rio.open(CLIP) as clip:
        crs, transform = clip.crs.to_string(), clip.transform
    _read_block([("gone", http_server.url("/gone.tif"), 2019)], crs, transform, (10, 10),
                str(tmp_path / "block.tif"), "test")
    assert counting() == {("127.0.0.1", "not_found"): (1, 0)}


def test_metrics_of_the_totals(counting, tmp_path):
    """The web process's metrics read the totals: requests per host and outcome, bytes and seconds per host."""
    import metrics
    from prometheus_client import generate_latest
    sc.record("https://a.example/", "ok", 100, 1.5)
    sc.record("https://a.example/", "timeout", 0, 120.0)
    counting()
    text = generate_latest(metrics.registry(str(tmp_path))).decode()
    assert 'findaline_service_requests_total{host="a.example",outcome="ok"} 1.0' in text
    assert 'findaline_service_requests_total{host="a.example",outcome="timeout"} 1.0' in text
    assert 'findaline_service_bytes_total{host="a.example"} 100.0' in text
    assert 'findaline_service_seconds_total{host="a.example"} 121.5' in text


def _clip_layer():
    """A layer of two tiles: the Żabi Koń clip (600 × 600 px of 1 m) and one without data."""
    import shutil

    import sources as src

    class Clip(src.Layer):
        description, folder = "Clip", "test/clip"

        def tiles(self, grid):
            return [0, 1]

        def tile_path(self, cache_dir, tile):
            return os.path.join(cache_dir, "test", "clip", f"{tile}.tif")

        def tile_url(self, tile):
            return f"https://tiles.example/{tile}.tif"

        def download_tile(self, tile, path):
            if tile == 1:
                return src.Fetched(0)  # the service has no data there
            os.makedirs(os.path.dirname(path), exist_ok=True)
            shutil.copyfile(CLIP, path)
            return src.Fetched(1234, self.tile_url(tile))
    return Clip()


def test_tiles_of_the_layers(tmp_path):
    """download_layers counts each layer's tiles by role (F18): downloaded with their pixels and km² from
    the cached file's header, bytes and seconds; those found in the cache the next time; nothing while
    the counting is off; a failed write keeps them."""
    import sources as src
    jobs = jb.Jobs(str(tmp_path))
    cache_dir = str(tmp_path / "cache")
    os.makedirs(cache_dir)
    layer = _clip_layer()
    src.download_layers([(layer, "terrain")], None, cache_dir)  # not counting: nothing kept
    assert sc.take_tiles() == []

    def rows():
        db = sqlite3.connect(tmp_path / "jobs.sqlite")
        try:
            return {(r[0], r[1]): r[2:] for r in db.execute("SELECT * FROM layer_downloads")}
        finally:
            db.close()
    sc.enable(jobs.add_service_requests, interval=False, tile_writer=jobs.add_layer_downloads)
    try:
        other = str(tmp_path / "other-cache")
        os.makedirs(other)
        src.download_layers([(layer, "gap fill (FABDEM)")], None, other)
        sc.flush()
        tiles, cached, pixels, km2, size, seconds, waited = rows()[("test/clip", "gap fill")]
        assert (tiles, cached, pixels, size) == (2, 0, 360_000, 1234)
        assert km2 == pytest.approx(0.36) and seconds >= 0 and waited >= 0
        src.download_layers([(layer, "terrain"), (layer, "surface")], None, other)  # cached: the first role
        sc.flush()
        assert rows()[("test/clip", "terrain")][:2] == (0, 2) and ("test/clip", "surface") not in rows()

        def broken(rows):
            raise sqlite3.OperationalError("database is locked")
        sc.enable(jobs.add_service_requests, interval=False, tile_writer=broken)
        sc.tiles("test/clip", "bogus", cached=3)  # an unknown role is "other"
        sc.flush()
        sc.enable(jobs.add_service_requests, interval=False, tile_writer=jobs.add_layer_downloads)
        sc.flush()
        assert rows()[("test/clip", "other")][:2] == (0, 3)
    finally:
        sc.disable()
    assert sc.role_of("water mask") == "water mask" and sc.role_of("gap fill (Copernicus DEM)") == "gap fill"
    assert sc.role_of("fake") == "other"


# The command line's counts into a file (FINDALINE_SERVICE_COUNTS: counted_into, summary)


def _read(path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def test_summary_per_host():
    """Requests, bytes and failed attempts (outcome not ok or not_found) per host, the tiles summed over the layers
    and roles, an IP address written as ADDRESS_HOST, the reads mark only where GDAL read files."""
    rows = [("a.example", "ok", 3, 300, 1.0), ("a.example", "not_found", 1, 10, 0.1), ("a.example", "http_5xx", 2, 5, 0),
            ("b.example", "timeout", 1, 0, 60.0), ("10.1.2.3", "ok", 1, 7, 0), ("::1", "connection", 2, 0, 0)]
    tiles = [("x/a", "terrain", 2, 5, 0, 0.0, 0, 0.0, 0.0), ("x/b", "gap fill", 1, 0, 0, 0.0, 0, 0.0, 0.0)]
    assert sc.summary(rows, tiles, {"b.example"}) == {
        "hosts": {"a.example": {"requests": 6, "bytes": 315, "failed": 2},
                  "b.example": {"requests": 1, "bytes": 0, "failed": 1, "reads": True},
                  sc.ADDRESS_HOST: {"requests": 3, "bytes": 7, "failed": 2}},
        "tiles": {"downloaded": 3, "cached": 5}}
    assert sc.summary([], []) == {"hosts": {}, "tiles": {"downloaded": 0, "cached": 0}}
    assert sc.written_host("sheets.example.org") == "sheets.example.org" and sc.written_host("[::1]") == sc.ADDRESS_HOST


def test_counted_into_a_file(http_server, monkeypatch, tmp_path):
    """The web worker's counting, reused: every attempt of our own requests with its bytes (a 500 asked three times:
    failed), the files of a block read through GDAL counted as one request each without bytes and marked as reads,
    the tiles; written when the body ends, also by a stop with a message (a failed search's counts matter most); the
    file holds no URL, path or address. Nothing counted after it."""
    import rasterio as rio

    from sources import net
    from sources.readers.windows import _read_block
    monkeypatch.setattr(net, "_sleep", lambda attempt: None)
    http_server.add("/bad", b"busy", "text/plain", status=500)
    http_server.add("/tile.tif", b"x" * 1000, "image/tiff")
    path = tmp_path / "counts.json"
    with pytest.raises(SystemExit, match="stopped"):
        with sc.counted_into(str(path)):
            assert sc.enabled()
            assert net._get(http_server.url("/tile.tif")).content == b"x" * 1000
            with pytest.raises(RuntimeError):
                net._get(http_server.url("/bad"))
            sc.tiles("test/clip", "terrain", downloaded=2, cached=1)
            raise SystemExit("stopped")
    assert not sc.enabled() and sc.take() == []
    assert _read(path) == {"hosts": {sc.ADDRESS_HOST: {"requests": 1 + net.RETRIES, "bytes": 1000 + 4 * net.RETRIES,
                                                       "failed": net.RETRIES}},
                           "tiles": {"downloaded": 2, "cached": 1}}
    with open(CLIP, "rb") as f:
        http_server.add("/clip.tif", f.read(), "image/tiff")
    with rio.open(CLIP) as clip:
        crs, transform = clip.crs.to_string(), clip.transform
    with sc.counted_into(str(path)):
        _read_block([("clip", http_server.url("/clip.tif"), 2020), ("local", CLIP, 2018)], crs, transform, (10, 10),
                    str(tmp_path / "block.tif"), "test")
    text = path.read_text(encoding="utf-8")
    assert json.loads(text) == {"hosts": {sc.ADDRESS_HOST: {"requests": 1, "bytes": 0, "failed": 0, "reads": True}},
                                "tiles": {"downloaded": 0, "cached": 0}}
    assert not re.search(r"127\.0\.0\.1|http|clip|tif|[/\\]", text)


def test_a_crash_writes_its_counts_too(http_server, tmp_path):
    http_server.add("/a.json", b"{}", "application/json")
    path = tmp_path / "counts.json"
    with pytest.raises(ZeroDivisionError):
        with sc.counted_into(str(path)):
            sc.get(http_server.url("/a.json"))
            1 / 0
    assert _read(path)["hosts"] == {sc.ADDRESS_HOST: {"requests": 1, "bytes": 2, "failed": 0}}


def test_no_file_no_counting(http_server, tmp_path):
    """Without a file nothing is counted; with the web worker's counting on, its writer gets the rows as ever and
    no file is written (never mixed)."""
    http_server.add("/a.json", b"{}", "application/json")
    with sc.counted_into(None):
        assert not sc.enabled()
        sc.get(http_server.url("/a.json"))
    assert sc.take() == []
    rows = []
    sc.enable(rows.extend, interval=False)
    path = tmp_path / "counts.json"
    with sc.counted_into(str(path)):
        sc.get(http_server.url("/a.json"))
    assert sc.enabled() and not path.exists()
    sc.flush()
    assert [r[:4] for r in rows] == [("127.0.0.1", "ok", 1, 2)]


def test_a_file_that_cannot_be_written_is_a_warning(tmp_path, capsys):
    folder = tmp_path / "counts.json"
    folder.mkdir()  # a folder where the file would be
    with sc.counted_into(str(folder)):
        sc.record("https://a.example/", "ok", 1)
    assert capsys.readouterr().out.startswith("WARNING: the service counts were not written")


@pytest.mark.parametrize("ending", ["SearchError", "RuntimeError"])
def test_a_command_line_search_counts_into_the_file(ending, http_server, monkeypatch, tmp_path):
    """findaline.py's search (its __main__, the search stubbed after one request): with FINDALINE_SERVICE_COUNTS the
    requests go into that file, also for a search that ends with its message or crashes; without it nothing is
    counted and no file is written."""
    import progress
    import search
    http_server.add("/index.json", b"[1, 2]", "application/json")
    seen = []

    def plan(*args, **kwargs):
        seen.append(sc.enabled())
        sc.get(http_server.url("/index.json"))
        raise search.SearchError("Download failed: test") if ending == "SearchError" else RuntimeError("crash")

    monkeypatch.setattr(search, "plan_search", plan)
    monkeypatch.setattr(progress, "utf8_output", lambda: None)
    path = tmp_path / "counts.json"
    data = tmp_path / "data"
    argv = ["findaline.py", "--lat", "50.1559508", "--lon", "19.7562722", "--no-plot", "--yes", "--data-dir", str(data)]
    script = os.path.join(os.path.dirname(HERE), "findaline.py")
    for env in (str(path), None):
        if env:
            monkeypatch.setenv(sc.COUNTS_FILE_ENV, env)
        else:
            monkeypatch.delenv(sc.COUNTS_FILE_ENV)
        monkeypatch.setattr(sys, "argv", argv)
        with pytest.raises(SystemExit if ending == "SearchError" else RuntimeError):
            runpy.run_path(script, run_name="__main__")
        if env:
            assert _read(path)["hosts"] == {sc.ADDRESS_HOST: {"requests": 1, "bytes": 6, "failed": 0}}
            path.unlink()
    assert seen == [True, False] and not path.exists() and not sc.enabled()


def test_the_reads_mark_is_the_readers_own_word():
    """A host is marked "reads" only where the reader said so (`request(url, read=True)`), never by what a request
    happened to note: a request that noted no answer and no bytes (osmextract's urllib answers; one cut off by
    Ctrl+C) is a plain request."""
    with sc.counting() as found:
        with sc.request("https://gdal.example/a.tif", read=True):
            pass
        with sc.request("https://plain.example/state.txt"):  # nothing noted, no bytes, no error
            pass
        with pytest.raises(KeyboardInterrupt):
            with sc.request("https://stopped.example/x"):
                raise KeyboardInterrupt
    assert found["hosts"]["gdal.example"] == {"requests": 1, "bytes": 0, "failed": 0, "reads": True}
    assert "reads" not in found["hosts"]["plain.example"] and "reads" not in found["hosts"]["stopped.example"]


def test_only_gdals_reader_marks_its_requests_as_reads():
    """In the code, sources/readers/windows.py alone passes read=True (a file read through GDAL: one request
    counted, its own HTTP requests and bytes unseen)."""
    root = os.path.dirname(HERE)
    marked = []
    for folder, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in (".git", ".venv", "node_modules", "tests", "cache", "runs", "work",
                                                ".claude", "viewer", "local")]
        for name in files:
            if name.endswith(".py") and name != "servicecounts.py":
                with open(os.path.join(folder, name), encoding="utf-8") as f:
                    text = f.read()
                if re.search(r"servicecounts\.request\([^)]*read=True", text):
                    marked.append(os.path.relpath(os.path.join(folder, name), root).replace(os.sep, "/"))
    assert marked == ["sources/readers/windows.py"], marked
