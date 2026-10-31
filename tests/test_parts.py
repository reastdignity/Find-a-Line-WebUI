"""The parts of the layers (sources/indexes, sources/readers, sources/composed.py) and the local HTTP
server they are tested against (tests/http_server.py)."""

import os
import sys

import numpy as np
import rasterio as rio
import requests
from rasterio.windows import Window

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cache  # noqa: E402
import sources as src  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
CLIP = os.path.join(HERE, "data", "zabi_kon_nmt.tif")


# The local server

def test_server_ranges(http_server):
    body = bytes(range(256)) * 4
    http_server.add("/f.bin", body)
    http_server.add("/q?b=2&a=1", b"query", "text/plain")
    url, headers = http_server.url("/f.bin"), cache.http_headers()
    whole = requests.get(url, headers=headers)
    assert whole.status_code == 200 and whole.content == body and whole.headers["Accept-Ranges"] == "bytes"
    one = requests.get(url, headers={**headers, "Range": "bytes=10-19"})
    assert one.status_code == 206 and one.content == body[10:20]
    assert one.headers["Content-Range"] == f"bytes 10-19/{len(body)}"
    tail = requests.get(url, headers={"Range": "bytes=-5"})
    assert tail.status_code == 206 and tail.content == body[-5:]
    several = requests.get(url, headers={"Range": "bytes=0-3, 100-103"})
    assert several.status_code == 206 and several.headers["Content-Type"].startswith("multipart/byteranges")
    assert body[0:4] in several.content and body[100:104] in several.content
    assert b"Content-Range: bytes 100-103/1024" in several.content
    beyond = requests.get(url, headers={"Range": "bytes=5000-"})
    assert beyond.status_code == 416 and beyond.headers["Content-Range"] == "bytes */1024"
    head = requests.head(url)
    assert head.status_code == 200 and head.headers["Content-Length"] == "1024" and not head.content
    assert requests.get(http_server.url("/q"), params={"a": "1", "b": "2"}).text == "query"
    assert http_server.requests("/f.bin")[0].user_agent == headers["User-Agent"]
    assert not http_server.stray()
    assert requests.get(http_server.url("/nothing")).status_code == 404
    assert [r.path for r in http_server.stray()] == ["/nothing"]


def test_server_windows_through_gdal(http_server):
    """GDAL's /vsicurl/ reads a window of a file on the server as a local read gives it, with
    our User-Agent."""
    http_server.add_folder("/files", os.path.dirname(CLIP))
    window = Window(30, 40, 50, 60)
    with rio.open(CLIP) as local:
        expected = local.read(1, window=window)
    with src.net._gdal_http(), rio.open(src.net._remote(http_server.url("/files/zabi_kon_nmt.tif"))) as remote:
        assert np.array_equal(remote.read(1, window=window), expected, equal_nan=True)
    asked = http_server.requests("/files/zabi_kon_nmt.tif")
    assert asked and all(r.user_agent == cache.http_headers()["User-Agent"] for r in asked)
    assert any("range" in r.headers for r in asked)
    assert not http_server.stray()

