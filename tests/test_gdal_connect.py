"""Remote reads give up a connection that never comes after net.CONNECT_TIMEOUT_S (GDAL_HTTP_CONNECTTIMEOUT in
net._gdal_http; requests' connect timeout in ranges.get_range) and never cut a slow answer of a server that
answers; opening a file is retried net.OPEN_RETRIES times, the reads after it net.RETRIES (net.gdal_open); a
download stops asking a host it could not connect to (net.UnreachableHosts, net.connect_failed).

Offline: the address that never answers is TEST-NET-1 (192.0.2.1, RFC 5737: reserved for documentation, never
routed, so no host receives anything); where the system answers "unreachable" at once (no route, a firewall
that rejects), the tests assert the error and the upper bound only. A refused connection is a closed local port.
The slow server is a socket server of this module on 127.0.0.1 (tests/http_server.py writes an answer at once).
"""

import contextlib
import os
import re
import socket
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np
import pytest
import rasterio as rio
import rasterio.cache
import requests
import urllib3.exceptions
from affine import Affine
from rasterio.transform import from_origin

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
import grid as gd  # noqa: E402
import sources as src  # noqa: E402
from http_server import Answer, _ranges  # noqa: E402
from sources import net  # noqa: E402
from sources.layers.fileblocks import FileBlocks  # noqa: E402
from sources.readers import ranges, windows  # noqa: E402

CRS = "EPSG:2180"
CONNECT_S = 1  # the connect timeout of these tests (the app's: net.CONNECT_TIMEOUT_S)
PAUSE_S = 1.5  # each answer of the slow server: half its body, this pause, the rest (longer than CONNECT_S)
DEAD = "http://192.0.2.1/never/M_DEAD2023.TIF"
# net.Unreachable's message: the host and its kind, nothing that varies (the regression harness matches it)
MESSAGE = r"^(\S+) could not be connected to \((timed out|refused or no route|name not found)\)$"


def test_the_settings():
    """The connect timeout is set for every remote read of _gdal_http, the read timeout stays 120 s; an open inside
    gdal_open is retried once, and the options are back to RETRIES after it (rasterio's environments nest)."""
    with net._gdal_http():
        options = rio.env.getenv()
        with net.gdal_open():
            opening = rio.env.getenv()
        after = rio.env.getenv()
    assert options["GDAL_HTTP_CONNECTTIMEOUT"] == str(net.CONNECT_TIMEOUT_S) == "5"
    assert options["GDAL_HTTP_TIMEOUT"] == "120" and options["GDAL_HTTP_MAX_RETRY"] == str(net.RETRIES) == "3"
    assert opening["GDAL_HTTP_MAX_RETRY"] == str(net.OPEN_RETRIES) == "1" and after == options


@pytest.fixture
def short(monkeypatch):
    """CONNECT_S as the connect timeout, GDAL's pause between attempts 0.1 s (its attempts as the app's: the open
    OPEN_RETRIES + 1, a read RETRIES + 1), no pause between our attempts, no proxy between."""
    monkeypatch.setattr(net, "CONNECT_TIMEOUT_S", CONNECT_S)
    original = windows._gdal_http

    @contextlib.contextmanager
    def quick(serial=False):
        with original(serial), rio.Env(GDAL_HTTP_RETRY_DELAY="0.1"):
            yield
    monkeypatch.setattr(windows, "_gdal_http", quick)
    monkeypatch.setattr(net, "_sleep", lambda attempt: None)
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost,192.0.2.1")
    return quick


def test_an_address_that_never_answers(short, tmp_path):
    """A block of a file at an address that never answers fails within the open's attempts' connect timeouts (GDAL
    asks the file's size twice when it opens it, each OPEN_RETRIES + 1 attempts: 4 x CONNECT_S), as net.Unreachable
    (a RuntimeError "Could not read ...", what the readers raise). Where it timed out, it waited for them."""
    rasterio.cache.invalidate(DEAD)
    start = time.monotonic()
    with pytest.raises(net.Unreachable, match=r"^192\.0\.2\.1 could not be connected to ") as error:
        windows._read_block([("dead", DEAD, 2023)], CRS, Affine(0.5, 0, 0, 0, -0.5, 0), (20, 20),
                            str(tmp_path / "dead.tif"), "dead")
    seconds = time.monotonic() - start
    assert seconds < 4 * CONNECT_S + 3, (seconds, str(error.value))
    if "timed out" in str(error.value).lower():
        assert seconds >= 4 * CONNECT_S * 0.9, (seconds, str(error.value))
    assert not os.path.exists(tmp_path / "dead.tif")


def test_a_ranged_open_of_an_address_that_never_answers(short, monkeypatch):
    """Our own range requests (ranges.open_remote: the islands' reader) give up the connection after CONNECT_S, not
    after the read timeout of 120 s, and the first request (opening the file) makes OPEN_RETRIES + 1 attempts, each
    in its turn: net.Unreachable within 2 x CONNECT_S."""
    turns = []
    monkeypatch.setattr(net, "rate_turn", lambda url, share=1.0: turns.append(url))
    start = time.monotonic()
    with pytest.raises(net.Unreachable):
        with ranges.open_remote(DEAD, tiff_only=True):
            pass
    seconds = time.monotonic() - start
    assert turns == [DEAD] * (net.OPEN_RETRIES + 1) and seconds < 2 * CONNECT_S + 2, seconds


@pytest.fixture(scope="module")
def small_file(tmp_path_factory):
    """600 x 600 px of float32 in 256 px tiles: GDAL's open reads its header in its first 16 KB, its tiles lie
    beyond."""
    path = tmp_path_factory.mktemp("small") / "S_TEST2023.TIF"
    rows, cols = np.mgrid[0:600, 0:600]
    with rio.open(path, "w", driver="GTiff", width=600, height=600, count=1, dtype="float32", crs=CRS,
                  transform=from_origin(2000.0, 4000.0, 0.5, 0.5), tiled=True, blockxsize=256, blockysize=256,
                  compress="deflate", nodata=-9999.0) as dst:
        noise = np.random.default_rng(1).normal(0, 0.05, (600, 600))  # tiles of their own size, beyond 16 KB
        dst.write((100 + rows * 0.3 + cols * 0.1 + noise).astype(np.float32), 1)
    return path


@pytest.mark.parametrize("in_thread", [False, True])
def test_the_open_once_again_the_reads_three_times(short, http_server, small_file, tmp_path, in_thread):
    """Opening a file is retried once (net.open_gdal): a header answered 503 every time fails the open after two
    requests. The reads keep three retries: every data range answered 503 twice is asked a third time and the block
    is the file's (the code review's case of 2026-11-24: GDAL keeps a file's retries from its open, so the reads of a
    file opened at one retry failed). In the main thread and in another (a download's pool thread: rasterio
    keeps GDAL's options per thread there)."""
    if in_thread:
        outcome = []

        def run():
            try:
                _open_and_read(http_server, small_file, tmp_path)
                outcome.append(None)
            except BaseException as e:  # noqa: BLE001 - raised below
                outcome.append(e)
        worker = threading.Thread(target=run)
        worker.start()
        worker.join()
        if outcome[0] is not None:
            raise outcome[0]
        return
    _open_and_read(http_server, small_file, tmp_path)


def _open_and_read(http_server, small_file, tmp_path):
    body = small_file.read_bytes()
    seen = {"/open/": {}, "/read/": {}}  # range -> times asked

    def route(path):
        def answer(request):
            asked = request.headers.get("range")
            if asked and (path == "/open/" or int(asked.split("=")[1].split("-")[0]) >= 16384):
                seen[path][asked] = seen[path].get(asked, 0) + 1
                if path == "/open/" or seen[path][asked] <= 2:  # every data range twice: two retries of it
                    return Answer(503, b"busy", {"Content-Type": "text/plain"})
            return Answer(200, body, {"Content-Type": "image/tiff"})
        return answer
    for path in seen:
        http_server.route(path, route(path))
    transform = Affine(0.5, 0, 2000.0 + 50, 0, -0.5, 4000.0 - 50)
    with pytest.raises(RuntimeError, match="Could not read open"):
        windows._read_block([("open", http_server.url("/open/S.tif"), 2023)], CRS, transform, (200, 200),
                            str(tmp_path / "open.tif"), "open")
    assert sum(seen["/open/"].values()) == net.OPEN_RETRIES + 1
    windows._read_block([("read", http_server.url("/read/S.tif"), 2023)], CRS, transform, (200, 200),
                        str(tmp_path / "read.tif"), "read")
    windows._read_block([("local", str(small_file), 2023)], CRS, transform, (200, 200), str(tmp_path / "local.tif"),
                        "local")
    with rio.open(tmp_path / "read.tif") as a, rio.open(tmp_path / "local.tif") as b:
        assert np.array_equal(a.read(1), b.read(1), equal_nan=True)
    assert seen["/read/"] and max(seen["/read/"].values()) == 3  # the range read at its third try


def test_the_second_open_sends_nothing(short, http_server, small_file, tmp_path, monkeypatch):
    """net.open_gdal's second open (with the caller's retries) sends no request: GDAL's cache of the first answers
    it. A block costs the requests and bytes of one open (net.open_gdal a plain rio.open, as before 2026-11-24)."""
    from http_server import _ranges
    size = os.path.getsize(small_file)
    http_server.add("/twice/S.tif", small_file.read_bytes(), "image/tiff")
    url = http_server.url("/twice/S.tif")
    after_first = []
    first = net.gdal_open

    @contextlib.contextmanager
    def noting():
        with first():
            yield
        after_first.append(len(http_server.requests("/twice/")))
    monkeypatch.setattr(net, "gdal_open", noting)
    rasterio.cache.invalidate(url)
    with windows._gdal_http():
        net.open_gdal(net._remote(url)).close()
    assert after_first and len(http_server.requests("/twice/")) == after_first[0] > 0
    transform = Affine(0.5, 0, 2000.0 + 50, 0, -0.5, 4000.0 - 50)

    def block(name):
        rasterio.cache.invalidate(url)
        before = len(http_server.requests("/twice/"))
        windows._read_block([("t", url, 2023)], CRS, transform, (200, 200), str(tmp_path / f"{name}.tif"), name)
        asked = http_server.requests("/twice/")[before:]
        ranges_ = [_ranges(r.headers["range"], size) for r in asked if "range" in r.headers]
        return len(asked), sum(b - a + 1 for found in ranges_ for a, b in found)
    twice = block("twice")
    monkeypatch.setattr(net, "open_gdal", lambda path, **kwargs: rio.open(path, **kwargs))
    assert twice == block("once")


GDAL_TEXTS = [  # curl's texts as GDAL passes them on: the first two seen on Windows (192.0.2.1, a closed port gives
    # the second's form); the others are curl's wording, not seen here
    ("CURL error: Connection timed out after 5012 milliseconds", True),
    ("CURL error: Failed to connect to 192.0.2.1 port 80 after 21032 ms: Could not connect to server", True),
    ("CURL error: Failed to connect to 127.0.0.1 port 9 after 2040 ms: Couldn't connect to server", True),
    ("CURL error: Could not resolve host: basisdata.invalid", True),
    ("CURL error: Couldn't resolve host name", True),   # curl's general text of the same error
    ("CURL error: Operation timed out after 120000 milliseconds with 5 out of 10 bytes received", False),
    ("HTTP response code: 503", False),
    ("CURL error: Recv failure: Connection was reset", False),
    ("Read failed. See previous exception for details.", False),
]


@pytest.mark.parametrize("text, expected", GDAL_TEXTS)
def test_gdal_connect_failures(text, expected):
    """net.GDAL_CONNECT_FAILURES, a case each: no connection made trips; a read timeout, a status, a reset, a short
    answer or an unclear text never. Only in GDAL's report of curl's own error: never in a RuntimeError of ours,
    which may carry a server's body."""
    assert net.connect_failed(rio.errors.RasterioIOError(text)) is expected
    assert net.connect_failed(RuntimeError(f"Could not read terrain x: {text}")) is False


def _pool_error(reason):
    return requests.exceptions.ConnectionError(urllib3.exceptions.MaxRetryError(None, "/x", reason))


@pytest.mark.parametrize("error, expected", [
    (requests.exceptions.ConnectTimeout("connect timeout"), True),
    (_pool_error(urllib3.exceptions.NewConnectionError(None, "refused")), True),
    (_pool_error(urllib3.exceptions.NameResolutionError("x.invalid", None, OSError("not found"))), True),
    (_pool_error(urllib3.exceptions.ConnectTimeoutError(None, "connect timeout")), True),
    (requests.exceptions.ReadTimeout("read timeout"), False),
    (requests.exceptions.ConnectionError(urllib3.exceptions.ProtocolError("Connection aborted.")), False),
    (_pool_error(urllib3.exceptions.ProtocolError("Connection aborted.")), False),
    (requests.exceptions.ChunkedEncodingError("cut short"), False),
    (RuntimeError("HTTP 503 for bytes 0-65535: busy"), False),
    (None, False),
])
def test_requests_connect_failures(error, expected):
    """requests' errors: only a connect timeout or a connection that could not be made (refused, no route, the name
    not found) trips; a read timeout, a connection aborted after it was made, a short answer, a status never."""
    assert net.connect_failed(error) is expected


@pytest.fixture
def refusing_port():
    """A local port that refuses every connection for the whole test: bound, never listening, and held, so the
    system gives it to no other process meanwhile. A port only found free was taken by another worker's test server
    between the tries of a read in a parallel run (2026-11-24: that server's answer instead of a refusal)."""
    with socket.socket() as holder:
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):  # Windows: no second bind of the port, SO_REUSEADDR or not
            holder.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        holder.bind(("127.0.0.1", 0))
        yield holder.getsockname()[1]


def test_a_refused_connection_trips(monkeypatch, refusing_port):
    """A real refused connection (a closed local port), through GDAL and through our own range requests: the errors
    say no connection was made (connect_failed)."""
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.setattr(net, "_sleep", lambda attempt: None)
    url = f"http://127.0.0.1:{refusing_port}/x/M_TEST2023.TIF"
    with net._gdal_http(), rio.Env(GDAL_HTTP_MAX_RETRY="0"), pytest.raises(rio.errors.RasterioIOError) as error:
        rio.open(net._remote(url))
    assert net.connect_failed(error.value), str(error.value)
    with pytest.raises(net.Unreachable):
        ranges.get_range(url, 0, 99, attempts=1)


def _dead_layer(url):
    """A layer of the islands' kind (our own ranges, a LOCAL_CS forced) whose file is at url: 8 blocks of 100 m."""
    layer = FileBlocks("AHN dead", "test/dead/1", CRS, 0.5, 100, url, extent=(2000.0, 3800.0, 2400.0, 4000.0),
                       force_crs=True, ranged=True)
    grid = gd.Grid(left=2001.0, top=3999.0, res=2.0, height=99, width=199, crs=CRS)
    assert len(layer.tiles(grid)) == 8
    return layer, grid


def _download(layer, grid, cache_dir):
    """download_layers of the layer's 8 blocks, every task's error collected (on_error: the pool goes on)."""
    errors = []
    src.download_layers([(layer, "terrain")], grid, cache_dir, on_error=lambda layer, tiles, e: errors.append(e),
                        reencode_cached=False)
    return errors


def test_a_download_stops_asking_a_dead_host(short, tmp_path, monkeypatch):
    """8 blocks of an address that never answers, its host at one slot (basisdata.nl's): the first block's open
    fails (net.Unreachable), the other 7 fail at once with the same error and send nothing, so the download takes
    about one failed open (at most 1.5 times it) and the attempts of one block. The next download asks again."""
    monkeypatch.setattr(net, "HOST_SLOTS_OF", dict(net.HOST_SLOTS_OF, **{"192.0.2.1": 1}))
    attempts = []
    monkeypatch.setattr(net, "rate_turn", lambda url, share=1.0: attempts.append(url))  # each attempt takes one
    start = time.monotonic()
    with pytest.raises(net.Unreachable):
        with ranges.open_remote(DEAD):
            pass
    one = time.monotonic() - start
    layer, grid = _dead_layer(DEAD)
    for k in (1, 2):
        attempts.clear()
        start = time.monotonic()
        errors = _download(layer, grid, str(tmp_path / f"cache{k}"))
        seconds = time.monotonic() - start
        assert len(errors) == 8 and all(isinstance(e, net.Unreachable) for e in errors)
        assert len({str(e) for e in errors}) == 1 and re.match(MESSAGE, str(errors[0])).group(1) == "192.0.2.1"
        assert attempts == [DEAD] * (net.OPEN_RETRIES + 1), attempts
        assert seconds <= 1.5 * one + 0.5, (seconds, one)


def test_a_busy_host_trips_nothing(short, http_server, tmp_path, monkeypatch):
    """A host that answers 503 is no dead host: each of the 8 blocks asks it (its open's attempts) and fails with
    its own RuntimeError, never net.Unreachable."""
    monkeypatch.setattr(net, "HOST_SLOTS_OF", dict(net.HOST_SLOTS_OF, **{"127.0.0.1": 1}))
    http_server.route("/busy/", lambda request: Answer(503, b"busy", {"Content-Type": "text/plain"}))
    layer, grid = _dead_layer(http_server.url("/busy/M_BUSY2023.TIF"))
    errors = _download(layer, grid, str(tmp_path / "cache"))
    assert len(errors) == 8 and not any(isinstance(e, net.Unreachable) for e in errors)
    assert len(http_server.requests("/busy/")) == 8 * (net.OPEN_RETRIES + 1)


@pytest.fixture
def slow_server(tmp_path):
    """A server of one small GeoTIFF (two tiles of 256 px) on 127.0.0.1 that sends each answer's body in two
    halves PAUSE_S apart; `answers` holds how long each GET took, headers to last byte."""
    path = tmp_path / "S_SLOW2023.TIF"
    rows, cols = np.mgrid[0:256, 0:512]
    with rio.open(path, "w", driver="GTiff", width=512, height=256, count=1, dtype="float32", crs=CRS,
                  transform=from_origin(1000.0, 2000.0, 0.5, 0.5), tiled=True, blockxsize=256, blockysize=256,
                  nodata=-9999.0) as dst:
        dst.write((50 + rows * 0.2 + cols * 0.05).astype(np.float32), 1)
    body = path.read_bytes()
    answers = []

    class Slow(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):
            pass

        def do_HEAD(self):
            self._answer(head=True)

        def do_GET(self):
            self._answer(head=False)

        def _answer(self, head: bool):
            start = time.monotonic()
            status, part, headers = 200, body, {"Accept-Ranges": "bytes"}
            asked = _ranges(self.headers["Range"], len(body)) if "Range" in self.headers else None
            if asked:
                (first, last), = asked  # GDAL_HTTP_MULTIRANGE=YES: one range per request
                status, part = 206, body[first:last + 1]
                headers["Content-Range"] = f"bytes {first}-{last}/{len(body)}"
            self.send_response(status)
            for name, value in {"Content-Type": "image/tiff", "Content-Length": str(len(part)), **headers}.items():
                self.send_header(name, value)
            self.end_headers()
            if head:
                return
            self.wfile.write(part[:len(part) // 2])
            self.wfile.flush()
            time.sleep(PAUSE_S)
            self.wfile.write(part[len(part) // 2:])
            self.wfile.flush()
            answers.append(time.monotonic() - start)

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Slow)
    httpd.daemon_threads = True
    thread = threading.Thread(target=httpd.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}/f/S_SLOW2023.TIF", path, answers
    httpd.shutdown()
    httpd.server_close()


def test_a_slow_answer_is_read_whole(short, slow_server, tmp_path):
    """A server whose every answer takes longer than the connect timeout (PAUSE_S in the middle of its body) is read
    to the end: the block equals a local read's, and no answer was asked twice."""
    url, path, answers = slow_server
    rasterio.cache.invalidate(url)
    transform = Affine(0.5, 0, 1000.0 + 100, 0, -0.5, 2000.0 - 20)  # over both tiles
    windows._read_block([("slow", url, 2023)], CRS, transform, (100, 300), str(tmp_path / "remote.tif"), "slow")
    windows._read_block([("slow", str(path), 2023)], CRS, transform, (100, 300), str(tmp_path / "local.tif"), "slow")
    with rio.open(tmp_path / "remote.tif") as a, rio.open(tmp_path / "local.tif") as b:
        assert np.array_equal(a.read(1), b.read(1), equal_nan=True)
    assert answers and min(answers) > CONNECT_S


@pytest.mark.parametrize("error, kind", [
    (requests.exceptions.ConnectTimeout("connect timeout"), net.TIMED_OUT),
    (_pool_error(urllib3.exceptions.ConnectTimeoutError(None, "connect timeout")), net.TIMED_OUT),
    (_pool_error(urllib3.exceptions.NameResolutionError("x.invalid", None, OSError("not found"))), net.NO_NAME),
    (_pool_error(urllib3.exceptions.NewConnectionError(None, "refused")), net.REFUSED),
    (rio.errors.RasterioIOError("CURL error: Connection timed out after 5012 milliseconds"), net.TIMED_OUT),
    (rio.errors.RasterioIOError("CURL error: Failed to connect to h port 80 after 2 ms: Could not connect to server"),
     net.REFUSED),
    (rio.errors.RasterioIOError("CURL error: Could not resolve host: basisdata.invalid"), net.NO_NAME),
    (requests.exceptions.ReadTimeout("read timeout"), None),
])
def test_connect_kinds(error, kind):
    """The kind of a failed connection, one of net.CONNECT_KINDS, from requests' errors and curl's texts alike."""
    assert net.connect_kind(error) == kind


def _caused(error, cause):
    error.__cause__ = cause
    return error


@pytest.mark.parametrize("cause, kind", [
    (ConnectionRefusedError(10061, "refused"), net.REFUSED),
    (OSError(101, "Network is unreachable"), net.REFUSED),
    (TimeoutError(110, "timed out"), net.TIMED_OUT),
])
def test_connect_kind_from_the_system_error(cause, kind):
    """A NewConnectionError's kind by the system's error under it: refused or no route, or timed out."""
    error = _caused(urllib3.exceptions.NewConnectionError(None, "Failed to establish a new connection"), cause)
    assert net.connect_kind(_pool_error(error)) == kind


def test_both_readers_say_the_same(short, tmp_path, refusing_port):
    """A closed local port read through GDAL and through our own ranges, twice: net.Unreachable with one message,
    the host and the kind (refused, or timed out where the system's refusal takes longer than CONNECT_S), equal
    every time and from both readers."""
    url = f"http://127.0.0.1:{refusing_port}/x/M_TEST2023.TIF"
    messages = []
    for ranged in (False, True, True):
        rasterio.cache.invalidate(url)
        with pytest.raises(net.Unreachable) as error:
            windows._read_block([("x", url, 2023)], CRS, Affine(0.5, 0, 0, 0, -0.5, 0), (20, 20),
                                str(tmp_path / "x.tif"), "x", ranged=ranged)
        messages.append(str(error.value))
    assert len(set(messages)) == 1 and re.match(MESSAGE, messages[0]).group(1) == "127.0.0.1", messages


def test_a_dead_host_and_a_live_one_in_one_download(short, http_server, small_file, tmp_path, monkeypatch):
    """One download (with on_error, as tools/area_download.py) of a dead host's 8 blocks and a live host's 6:
    on_error once per task of the dead host, each with the same error; connection attempts for one of its tasks
    only; the live host's blocks all downloaded."""
    monkeypatch.setattr(net, "HOST_SLOTS_OF", dict(net.HOST_SLOTS_OF, **{"192.0.2.1": 1}))
    attempts = []
    monkeypatch.setattr(net, "rate_turn", lambda url, share=1.0: attempts.append(url))
    http_server.add("/live/S_TEST2023.TIF", small_file.read_bytes(), "image/tiff")
    dead, grid = _dead_layer(DEAD)
    live = FileBlocks("AHN live", "test/live/1", CRS, 0.5, 100, http_server.url("/live/S_TEST2023.TIF"),
                      extent=(2000.0, 3700.0, 2300.0, 4000.0), ranged=True)
    cache_dir = str(tmp_path / "cache")
    calls = []
    src.download_layers([(dead, "terrain"), (live, "surface")], grid, cache_dir,
                        on_error=lambda layer, tiles, e: calls.append((layer, len(tiles), e)), reencode_cached=False)
    assert len(calls) == 8 and all(layer is dead and n == 1 for layer, n, _ in calls)
    assert len({str(e) for _, _, e in calls}) == 1 and all(isinstance(e, net.Unreachable) for _, _, e in calls)
    assert attempts.count(DEAD) == net.OPEN_RETRIES + 1
    assert sum(os.path.exists(live.tile_path(cache_dir, tile)) for tile in live.tiles(grid)) == 6  # 2 beyond the file


def test_a_servers_words_are_no_failed_connection(http_server, monkeypatch):
    """A 502 whose body says what curl says of a failed connection (a gateway's words about its own backend) is an
    HTTP status: a RuntimeError, never net.Unreachable (the code review's case of 2026-11-24); nor in GDAL's report
    of a status."""
    monkeypatch.setattr(net, "_sleep", lambda attempt: None)
    body = b"Failed to connect to backend port 8080: Connection refused"
    http_server.route("/gw/", lambda r: Answer(502, body, {"Content-Type": "text/plain"}))
    with pytest.raises(RuntimeError, match="HTTP 502") as error:
        ranges.get_range(http_server.url("/gw/x.tif"), 0, 99, attempts=1)
    assert not isinstance(error.value, net.Unreachable)
    assert net.connect_kind(rio.errors.RasterioIOError(f"HTTP response code: 502 - {body.decode()}")) is None


@pytest.mark.parametrize("text, host", [
    ("CURL error: Failed to connect to fsn1.your-objectstorage.com port 443 after 21 ms: Could not connect to server",
     "fsn1.your-objectstorage.com"),
    ("CURL error: Could not resolve host: basisdata.invalid", "basisdata.invalid"),
    ("CURL error: Connection timed out after 5012 milliseconds", None),
])
def test_the_host_curl_names(text, host):
    """The host GDAL's report of curl's error names, when it names one."""
    assert net.failed_host(rio.errors.RasterioIOError(text)) == host


def test_a_dead_redirect_target(short, http_server, tmp_path, monkeypatch, refusing_port):
    """The front answers 307 and its target does not answer: the message names the target (requests' error tells
    it), and the download still marks the front's other blocks, which send nothing."""
    target = f"http://localhost:{refusing_port}/t/M_DEAD2023.TIF"
    http_server.route("/front/", lambda r: Answer(307, b"", {"Location": target, "Content-Type": "text/plain"}))
    front = http_server.url("/front/M_DEAD2023.TIF")
    with pytest.raises(net.Unreachable, match=MESSAGE) as error:
        ranges.get_range(front, 0, 99, attempts=1)
    assert re.match(MESSAGE, str(error.value)).group(1) == "localhost"
    monkeypatch.setattr(net, "HOST_SLOTS_OF", dict(net.HOST_SLOTS_OF, **{"127.0.0.1": 1}))
    layer, grid = _dead_layer(front)
    errors = _download(layer, grid, str(tmp_path / "cache"))
    assert len(errors) == 8 and {str(e) for e in errors} == {str(error.value)}
    assert len(http_server.requests("/front/")) == 1 + net.OPEN_RETRIES + 1  # the call above, then one block's
