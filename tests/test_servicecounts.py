"""The counts of the requests to outside services (servicecounts.py; docs/monitoring.md F11): the
outcomes, the totals in jobs.sqlite (Jobs.add_service_requests, migration 14), nothing counted
unless the web worker turns the counting on (the command line, tests/regression.py), and the
hooks of the code that asks outside services, against the local HTTP server (tests/http_server.py)."""

import os
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
    """The command line never enables the counting: record() keeps nothing, flush() writes nothing."""
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
