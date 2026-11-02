"""The parts of the layers (sources/indexes, sources/readers, sources/composed.py) and the local HTTP
server they are tested against (tests/http_server.py)."""

import json
import os
import sys
import threading
import time
from urllib.parse import urlencode, urlsplit

import numpy as np
import pytest
import rasterio as rio
import requests
from rasterio.windows import Window

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cache  # noqa: E402
import sources as src  # noqa: E402
from grid import Grid  # noqa: E402
from http_server import key_of  # noqa: E402
from sources.indexes.cached import IndexUnavailable  # noqa: E402
from sources.indexes.listings import ows_exception  # noqa: E402

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


def _recorded(case):
    with open(os.path.join(RECORDED, case, "answers.json"), encoding="utf-8") as f:
        return json.load(f)


ANSWER_CASES = [case for case in CASES if "raises" not in _recorded(case)]
ERROR_CASES = [case for case in CASES if "raises" in _recorded(case)]


def _on_server(layer, server, years=None):
    """A layer as the catalogue's, but asking its index on the local server (a WFS sheet
    index: these year layers instead of those of its capabilities, if given)."""
    path = urlsplit(layer.index_url).path
    if isinstance(layer, src.SheetTiles):
        layer = src.SheetTiles(layer.description, server.url(path), layer.prefix, layer.folder, layer.native_res,
                               layer.min_res)
        if years:
            layer.index.listing._years = list(years)
        return layer
    if isinstance(layer, src.StacTiles):
        api = path[:path.index("/collections/")]
        return src.StacTiles(layer.description, server.url(api), layer.prefix, layer.folder, layer.crs,
                             layer.sizes, layer.tile_m, layer.asset, layer.item)
    if isinstance(layer, src.TnmBlocks):
        return type(layer)(layer.description, layer.dataset, layer.prefix, layer.folder, layer.native_res,
                           layer.block_m, layer.bytes_per_tile(), api=server.url(path))
    raise AssertionError(f"no recorded case for {type(layer).__name__}")


def test_recorded_cases_exist():
    assert CASES == ["stac/lgln-dgm1", "stac/swisstopo-swissalti3d", "tnm/dem1m", "tnm/ifsar5m",
                     "wfs/geoportal-error", "wfs/geoportal-nmt"]
    assert ERROR_CASES == ["wfs/geoportal-error"]


@pytest.mark.parametrize("case", ANSWER_CASES)
def test_recorded_index_answers(case, http_server, tmp_path):
    """The recorded answers of a service give the index JSON of the code that recorded them,
    byte for byte, with the same requests and nothing else asked."""
    folder = os.path.join(RECORDED, case)
    recorded = _recorded(case)
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
    expected = [key_of(a["method"], urlsplit(a["url"])._replace(scheme="", netloc="").geturl())
                for a in recorded["answers"]]
    if case.startswith("wfs/"):  # the capabilities first, then the year layers at once, in any order
        assert asked[0] == expected[0] and sorted(asked) == sorted(expected)
    else:
        assert asked == expected
    assert {r.user_agent for r in http_server.log} == {cache.http_headers()["User-Agent"]}


def test_recorded_lgln_newest_per_tile(http_server, tmp_path):
    """LGLN's items (ids dgm1_32_<E>_<N>_1_ni_<year>, one asset without gsd or checksum): every
    1 km tile of the recorded answer has two surveys, and the newest of each is used."""
    folder = os.path.join(RECORDED, "stac", "lgln-dgm1")
    http_server.add_cassette(folder)
    layer = _on_server(src.SOURCES["lower_saxony"].nmt, http_server)
    cache_dir = str(tmp_path / "cache")
    layer.update_index_tile(cache_dir, 52.75, 11.5)
    with open(os.path.join(folder, "expected.json"), encoding="utf-8") as f:
        listed = json.load(f)["sheets"]
    assert len(listed) == 30 and {s["res"] for s in listed} == {1.0} and {s["sha256"] for s in listed} == {None}
    surveys = {}
    for s in listed:
        surveys.setdefault(s["godlo"], set()).add(s["year"])
    import grid as gd
    # A grid over the listed tiles within the recorded 0.25° tile (the sheets reach beyond it)
    grid = gd.make_grid((668500, 5868500, 671500, 5875200), 10.0, "EPSG:25832")
    layer._use(cache_dir, None)
    tiles = layer.tiles(grid)
    surveys = {g: y for g, y in surveys.items()
               if any(s["godlo"] == g and s["extent"][0] < 671500 and s["extent"][2] > 668500
                      and s["extent"][1] < 5875200 and s["extent"][3] > 5868500 for s in listed)}
    assert len(tiles) == len(surveys) == 7
    assert {t.godlo: t.year for t in tiles} == {f"{g}/1m": max(y) for g, y in surveys.items()}
    assert all(len(y) == 2 for y in surveys.values())
    assert all(os.path.basename(layer.tile_path(cache_dir, t)) == f"{t.year}_{t.name}.tif" for t in tiles)
    assert not http_server.stray()


def test_ows_exception():
    with open(os.path.join(RECORDED, "wfs", "geoportal-error", "001.xml"), "rb") as f:
        assert "TYPENAME 'SkorowidzNMT1900' doesn't exist" in ows_exception(f.read())
    assert ows_exception(b"<?xml version='1.0'?>\n<!-- old -->\n<ServiceExceptionReport version='1.2.0'>"
                         b"<ServiceException code='x'> busy </ServiceException></ServiceExceptionReport>") == "busy"
    assert ows_exception(b"<ows:ExceptionReport xmlns:ows='o'/>") == "an exception report"
    for answer in ("wfs/geoportal-nmt/001.xml", "wfs/geoportal-nmt/003.xml"):  # capabilities, features
        with open(os.path.join(RECORDED, answer), "rb") as f:
            assert ows_exception(f.read()) is None
    assert ows_exception(b"") is None and ows_exception(b"<html>busy</html>") is None


@pytest.mark.parametrize("case", ERROR_CASES)
def test_recorded_error_answers(case, http_server, tmp_path, capsys):
    """A recorded exception report of a WFS sheet index caches nothing, whether the service
    answers it with an error status (as geoportal does) or with HTTP 200; with an older
    cached answer of the tile, the search goes on without the index."""
    recorded = _recorded(case)
    http_server.add_cassette(os.path.join(RECORDED, case))
    lat, lon = recorded["case"]["lat"], recorded["case"]["lon"]
    catalogue = getattr(src.SOURCES[recorded["case"]["source"]], recorded["case"]["layer"])
    cache_dir = str(tmp_path / "cache")

    layer = _on_server(catalogue, http_server, recorded["case"]["years"])
    with pytest.raises(requests.RequestException) as raised:
        layer.update_index_tile(cache_dir, lat, lon)
    assert type(raised.value).__name__ == recorded["raises"]
    path = layer.index_path(cache_dir, lat, lon)
    assert not os.path.exists(path)

    # The same report with HTTP 200
    entry, = recorded["answers"]
    with open(os.path.join(RECORDED, case, entry["body"]), "rb") as f:
        report = f.read()
    url = urlsplit(entry["url"])._replace(scheme="", netloc="").geturl()
    http_server.add(url, report, entry["content_type"])
    layer = _on_server(catalogue, http_server, recorded["case"]["years"])
    with pytest.raises(IndexUnavailable, match="doesn't exist"):
        layer.update_index_tile(cache_dir, lat, lon)
    assert not os.path.exists(path)

    # An older answer of the tile stays; the search uses the cached files
    os.makedirs(os.path.dirname(path))
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"layers": [], "sheets": []}, f)
    cache.record(cache_dir, path, url=layer.index.listing.url)
    layer = _on_server(catalogue, http_server, recorded["case"]["years"])
    grid = Grid(left=475500.0, top=778500.0, res=5.0, height=100, width=100, crs="EPSG:2180")  # in the tile
    assert layer.to_download(grid, cache_dir, "all") == ([], None)
    assert "index not available (IndexUnavailable); using the cached files" in capsys.readouterr().out
    with open(path, encoding="utf-8") as f:
        assert json.load(f) == {"layers": [], "sheets": []}
    assert not http_server.stray()
    assert {r.user_agent for r in http_server.log} == {cache.http_headers()["User-Agent"]}


def _slow_cassettes(server, *cases):
    """The recorded answers of the cases, each GetFeature answered the later the older its year
    layer (so the years finish in the reverse order of their requests); the most requests the
    server had at once is `peak[0]`."""
    for case in cases:
        server.add_cassette(os.path.join(RECORDED, case))
    recorded, server.answers = dict(server.answers), {}
    lock, active, peak = threading.Lock(), [0], [0]

    def slow(request):
        typename = dict(request.query).get("TYPENAMES", "")
        with lock:
            active[0] += 1
            peak[0] = max(peak[0], active[0])
        try:
            time.sleep(0.04 * (2027 - int(typename[-4:])) if typename else 0)
            return recorded.get(("GET", request.path, tuple(sorted(request.query))))
        finally:
            with lock:
                active[0] -= 1
    server.route("/", slow)
    return peak


def _asked(server, request):
    return [dict(r.query).get("TYPENAMES") for r in server.log if dict(r.query).get("REQUEST") == request]


def test_wfs_year_layers_at_once(http_server, tmp_path, monkeypatch):
    """The GetFeature requests of a tile's year layers go several at once, no more than the slots
    of their host (net.host_slot), and the later years answering first change nothing: the cached
    answer is the recorded case's expected.json, byte for byte; every year layer asked once."""
    folder = os.path.join(RECORDED, "wfs", "geoportal-nmt")
    recorded = _recorded("wfs/geoportal-nmt")
    peak = _slow_cassettes(http_server, "wfs/geoportal-nmt")
    monkeypatch.setitem(src.net.HOST_SLOTS_OF, "127.0.0.1", 2)
    layer = _on_server(src.SOURCES["geoportal"].nmt, http_server)
    assert layer.index.listing.threads == 4
    cache_dir = str(tmp_path / "cache")
    lat, lon = recorded["case"]["lat"], recorded["case"]["lon"]
    assert layer.update_index_tile(cache_dir, lat, lon) == (0, 0, 0)
    with open(layer.index_path(cache_dir, lat, lon), "rb") as f, open(os.path.join(folder, "expected.json"), "rb") as e:
        assert f.read().replace(http_server.base.encode(), b"https://mapy.geoportal.gov.pl") == e.read()
    years = [f"gugik:SkorowidzNMT{y}" for y in range(2018, 2027)]
    assert sorted(_asked(http_server, "GetFeature")) == years and len(_asked(http_server, "GetCapabilities")) == 1
    assert peak[0] == 2  # at once, within the host's slots
    assert not http_server.stray()


def test_index_tiles_at_once(tmp_path):
    """The 0.25° tiles of a grid are asked several at once when the listing says so
    (NewestPerSheet.query: tiles_at_once), the first tiles answering last, and merged in the
    order of the tiles as one after another: of equal surveys, the first tile's is used."""
    import osm
    from rasterio.warp import transform_bounds
    from sources.indexes.cached import CachedIndex, Listing
    from sources.indexes.versions import NewestPerSheet
    grid = Grid(left=500000.0, top=700000.0, res=100.0, height=500, width=500, crs="EPSG:2180")
    order = osm.tiles(*transform_bounds(grid.crs, "EPSG:4326", *grid.bounds))
    asked, lock, active, peak = [], threading.Lock(), [0], [0]

    class Tiles(Listing):
        tiles_at_once = 3

        def fetch(self, lat, lon):
            with lock:
                asked.append((lat, lon))
                active[0] += 1
                peak[0] = max(peak[0], active[0])
            time.sleep(0.02 * (len(order) - order.index((lat, lon))))
            with lock:
                active[0] -= 1
            return {"sheets": [{"year": 2020, "godlo": "A", "url": f"https://x.example/{lat}_{lon}/A.asc",
                                "crs": "EPSG:2180", "res": 1.0, "extent": [400000, 600000, 600000, 800000]}]}
    index = CachedIndex("test", Tiles(), NewestPerSheet("t/sheets", "EPSG:2180", 1.0), "t", "t")
    index.use(str(tmp_path / "cache"), None)
    sheets = index.tiles(grid)
    assert len(order) > 6 and sorted(asked) == sorted(order) and peak[0] == 3
    assert [s.url for s in sheets] == [f"https://x.example/{order[0][0]}_{order[0][1]}/A.asc"]


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
