"""GDAL's remote reads give up a connection that never comes after net.GDAL_CONNECT_TIMEOUT_S
(GDAL_HTTP_CONNECTTIMEOUT in net._gdal_http) and never cut a slow answer of a server that answers.

Offline: the address that never answers is TEST-NET-1 (192.0.2.1, RFC 5737: reserved for documentation, never
routed, so no host receives anything); where the system answers "unreachable" at once (no route, a firewall
that rejects), the test asserts only the error and the upper bound. The slow server is a socket server of this
module on 127.0.0.1 (tests/http_server.py writes an answer at once).
"""

import contextlib
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np
import pytest
import rasterio as rio
import rasterio.cache
from affine import Affine
from rasterio.transform import from_origin

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
from http_server import _ranges  # noqa: E402
from sources import net  # noqa: E402
from sources.readers import windows  # noqa: E402

CRS = "EPSG:2180"
CONNECT_S = 1  # the connect timeout of these tests (the app's: net.GDAL_CONNECT_TIMEOUT_S)
PAUSE_S = 1.5  # each answer of the slow server: half its body, this pause, the rest (longer than CONNECT_S)


def test_the_settings():
    """The connect timeout is set for every remote read of _gdal_http; the read timeout stays 120 s."""
    with net._gdal_http():
        options = rio.env.getenv()
    assert options["GDAL_HTTP_CONNECTTIMEOUT"] == str(net.GDAL_CONNECT_TIMEOUT_S) == "5"
    assert options["GDAL_HTTP_TIMEOUT"] == "120" and options["GDAL_HTTP_MAX_RETRY"] == str(net.RETRIES)


@pytest.fixture
def no_retries(monkeypatch):
    """CONNECT_S as the connect timeout and no retries inside GDAL (the attempts and pauses of the app's settings
    are counted in net.GDAL_CONNECT_TIMEOUT_S's comment), no proxy between, no pause between our attempts."""
    monkeypatch.setattr(net, "GDAL_CONNECT_TIMEOUT_S", CONNECT_S)
    original = windows._gdal_http

    @contextlib.contextmanager
    def single(serial=False):
        with original(serial), rio.Env(GDAL_HTTP_MAX_RETRY="0"):
            yield
    monkeypatch.setattr(windows, "_gdal_http", single)
    monkeypatch.setattr(net, "_sleep", lambda attempt: None)
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost,192.0.2.1")


def test_an_address_that_never_answers(no_retries, tmp_path):
    """A block of a file at an address that never answers fails as the readers' other failed reads do (RuntimeError
    "Could not read ..."), within the attempts' connect timeouts: GDAL asks the file's size twice when it opens
    it, each one attempt here. Where the connection timed out, it waited about CONNECT_S per attempt."""
    url = "http://192.0.2.1/never/M_DEAD2023.TIF"
    rasterio.cache.invalidate(url)
    start = time.monotonic()
    with pytest.raises(RuntimeError, match="Could not read dead") as error:
        windows._read_block([("dead", url, 2023)], CRS, Affine(0.5, 0, 0, 0, -0.5, 0), (20, 20),
                            str(tmp_path / "dead.tif"), "dead")
    seconds = time.monotonic() - start
    assert seconds < 2 * CONNECT_S + 3, (seconds, str(error.value))
    if "timed out" in str(error.value).lower():
        assert seconds >= CONNECT_S * 0.9, (seconds, str(error.value))
    assert not os.path.exists(tmp_path / "dead.tif")


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


def test_a_slow_answer_is_read_whole(no_retries, slow_server, tmp_path):
    """A server whose every answer takes longer than the connect timeout (PAUSE_S in the middle of its body) is read
    to the end, without a retry (none allowed here): the block equals a local read's."""
    url, path, answers = slow_server
    rasterio.cache.invalidate(url)
    transform = Affine(0.5, 0, 1000.0 + 100, 0, -0.5, 2000.0 - 20)  # over both tiles
    windows._read_block([("slow", url, 2023)], CRS, transform, (100, 300), str(tmp_path / "remote.tif"), "slow")
    windows._read_block([("slow", str(path), 2023)], CRS, transform, (100, 300), str(tmp_path / "local.tif"), "slow")
    with rio.open(tmp_path / "remote.tif") as a, rio.open(tmp_path / "local.tif") as b:
        assert np.array_equal(a.read(1), b.read(1), equal_nan=True)
    assert answers and min(answers) > CONNECT_S
