"""The parts of the layers (sources/indexes, sources/readers, sources/composed.py) and the local HTTP
server they are tested against (tests/http_server.py)."""

import json
import os
import sys
from urllib.parse import urlencode, urlsplit

import numpy as np
import pytest
import rasterio as rio
import requests
from rasterio.windows import Window

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cache  # noqa: E402
import sources as src  # noqa: E402
from http_server import key_of  # noqa: E402

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


# Recorded answers of the index services (tools/record_answers.py)

RECORDED = os.path.join(HERE, "data", "recorded")
CASES = sorted(os.path.relpath(folder, RECORDED).replace(os.sep, "/")
               for folder, _, files in os.walk(RECORDED) if "answers.json" in files)


def _on_server(layer, server):
    """A layer as the catalogue's, but asking its index on the local server."""
    path = urlsplit(layer.index_url).path
    if isinstance(layer, src.SheetTiles):
        return src.SheetTiles(layer.description, server.url(path), layer.prefix, layer.folder, layer.native_res,
                              layer.min_res)
    if isinstance(layer, src.StacTiles):
        api = path[:path.index("/collections/")]
        return src.StacTiles(layer.description, server.url(api), layer.prefix, layer.folder, layer.crs,
                             layer.sizes, layer.tile_m)
    if isinstance(layer, src.TnmBlocks):
        return type(layer)(layer.description, layer.dataset, layer.prefix, layer.folder, layer.native_res,
                           layer.block_m, layer.bytes_per_tile(), api=server.url(path))
    raise AssertionError(f"no recorded case for {type(layer).__name__}")


def test_recorded_cases_exist():
    assert CASES == ["stac/swisstopo-swissalti3d", "tnm/dem1m", "tnm/ifsar5m", "wfs/geoportal-nmt"]


@pytest.mark.parametrize("case", CASES)
def test_recorded_index_answers(case, http_server, tmp_path):
    """The recorded answers of a service give the index JSON of the code that recorded them,
    byte for byte, with the same requests and nothing else asked."""
    folder = os.path.join(RECORDED, case)
    with open(os.path.join(folder, "answers.json"), encoding="utf-8") as f:
        recorded = json.load(f)
    http_server.add_cassette(folder)
    lat, lon = recorded["case"]["lat"], recorded["case"]["lon"]
    layer = _on_server(getattr(src.SOURCES[recorded["case"]["source"]], recorded["case"]["layer"]), http_server)
    cache_dir = str(tmp_path / "cache")
    assert layer.update_index_tile(cache_dir, lat, lon) == (0, 0, 0)  # nothing cached: nothing downloaded
    with open(layer.index_path(cache_dir, lat, lon), "rb") as f:
        written = f.read()
    host, = recorded["hosts"]
    with open(os.path.join(folder, "expected.json"), "rb") as f:
        assert written.replace(http_server.base.encode(), host.encode()) == f.read()
    assert not http_server.stray()
    asked = [key_of(r.method, r.path + "?" + urlencode(r.query)) for r in http_server.log]
    assert asked == [key_of(a["method"], urlsplit(a["url"])._replace(scheme="", netloc="").geturl())
                     for a in recorded["answers"]]
    assert {r.user_agent for r in http_server.log} == {cache.http_headers()["User-Agent"]}


# The composed layer, with fake parts

class FakeIndex(src.composed.Index):
    """Tiles 0..n-1 of a fake grid; tile 2 is where the service has no data."""

    def __init__(self, n):
        self.n = n

    def tiles(self, grid):
        return list(range(self.n))

    def path(self, cache_dir, tile):
        return os.path.join(cache_dir, "fake", "layer", f"{tile}.bin")

    def request(self, tile):
        return {"tile": tile, "url": f"https://fake.example/{tile}.bin"}

    def tile_of(self, path):
        name = path.removeprefix("fake/layer/")
        return int(name[:-4]) if name != path and name.endswith(".bin") else None

    def bounds_wgs84(self, tile):
        return tile, 0, tile + 1, 1


class FakeReader(src.composed.Reader):
    def __init__(self):
        self.fetched = []

    def fetch(self, request, path):
        self.fetched.append(request["tile"])
        if request["tile"] == 2:
            return src.Fetched(0, request["url"])
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(b"x" * 10)
        return src.Fetched(10, request["url"])

    def url(self, request):
        return request["url"]

    def unavailable(self):
        return "not here" if not self.fetched else None


class FakeLayer(src.composed.ComposedLayer):
    description, folder, native_res, _bytes = "Fake", "fake/layer", 1.0, 1e6

    def __init__(self, n):
        self.index, self.reader = FakeIndex(n), FakeReader()


def test_composed_layer(tmp_path, capsys):
    """A composed layer is a Layer made of its index and its reader: tiles, paths, estimates,
    the download of every layer with its locks and the cache's records."""
    layer, cache_dir = FakeLayer(4), str(tmp_path)
    assert layer.tiles(None) == [0, 1, 2, 3]
    assert layer.tile_path(cache_dir, 1) == os.path.join(cache_dir, "fake", "layer", "1.bin")
    assert layer.tile_of("fake/layer/3.bin") == 3 and layer.tile_of("other/3.bin") is None
    assert layer.tile_url(1) == "https://fake.example/1.bin" and layer.bounds_wgs84(1) == (1, 0, 2, 1)
    assert layer.has_data_near(0, 0, cache_dir) is None and layer.unavailable() == "not here"
    assert layer.estimate(None, cache_dir, None) == (4, 4, 4.0)
    src.download_layers([(layer, "fake")], None, cache_dir)
    assert sorted(layer.reader.fetched) == [0, 1, 2, 3] and layer.unavailable() is None
    assert "Fake: 4 tiles (0 cached, 4 to download)" in capsys.readouterr().out
    assert [cache.state(cache_dir, layer.tile_path(cache_dir, t)) for t in range(4)] == ["ok", "ok", "missing", "ok"]
    assert layer.estimate(None, cache_dir, None) == (4, 0, 0.0)
    assert layer.used(None, cache_dir)["paths"] == ["fake/layer/0.bin", "fake/layer/1.bin", "fake/layer/3.bin"]
    layer.reader.fetched.clear()
    src.download_layers([(layer, "fake")], None, cache_dir)
    assert layer.reader.fetched == []  # all cached or missing
