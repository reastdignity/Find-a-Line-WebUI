"""Per-host request rates (sources.net.rate_turn, HOST_RATES_OF) and slot caps (HOST_SLOTS_OF):
the turns spread evenly over threads and processes, every attempt of the download code waits for
one, a 429 or 503 backs off longer, and the probe asks a WCS as its reader does (version, keys).

conftest.py empties HOST_RATES_OF for every other test module; here each test sets its own hosts
and moves the bucket into tmp_path (net.RATES_DB)."""

import contextlib
import os
import re
import subprocess
import sys
import threading
import time

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
import settings  # noqa: E402
import sources as src  # noqa: E402
from sources import net, probe  # noqa: E402

HOST = "rate.example"
PER_MINUTE = 600  # one turn every 100 ms
GAP = 60 / PER_MINUTE
SLACK = 0.02  # the clocks of SQLite (ms) and of the test, the way from the permit to the stamp


@pytest.fixture
def rates(tmp_path, monkeypatch):
    """Only the test host has a rate; the bucket in tmp_path."""
    monkeypatch.setattr(net, "HOST_RATES_OF", {HOST: PER_MINUTE})
    monkeypatch.setattr(net, "RATES_DB", str(tmp_path / "rates.sqlite"))
    return tmp_path


def _gaps(stamps):
    stamps = sorted(stamps)
    return [b - a for a, b in zip(stamps, stamps[1:])]


def test_turns_spread_over_threads(rates):
    """Four threads, five requests each: one turn every 60/n s, never two closer."""
    stamps, lock = [], threading.Lock()

    def ask():
        for _ in range(5):
            net.rate_turn(f"https://{HOST}/file.tif")
            with lock:
                stamps.append(time.monotonic())
    threads = [threading.Thread(target=ask) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(stamps) == 20
    assert min(_gaps(stamps)) >= GAP - SLACK
    assert max(stamps) - min(stamps) >= 19 * GAP - SLACK


_CHILD = r'''
import sys, time
sys.path.insert(0, sys.argv[1])
from sources import net
net.RATES_DB = sys.argv[2]
net.HOST_RATES_OF = {sys.argv[3]: int(sys.argv[4])}
stamps = []
for _ in range(6):
    net.rate_turn(f"https://{sys.argv[3]}/x")
    stamps.append(time.time())
with open(sys.argv[5], "w") as f:
    f.write("\n".join(repr(s) for s in stamps))
'''


def test_turns_spread_over_processes(rates):
    """Two processes share the bucket: their turns together are 60/n s apart."""
    script = rates / "child.py"
    script.write_text(_CHILD, encoding="utf-8")
    outs = [rates / f"stamps{n}.txt" for n in range(2)]
    children = [subprocess.Popen([sys.executable, str(script), REPO, net.RATES_DB, HOST, str(PER_MINUTE), str(out)])
                for out in outs]
    assert [c.wait(timeout=120) for c in children] == [0, 0]
    stamps = [float(line) for out in outs for line in out.read_text().split()]
    assert len(stamps) == 12
    assert min(_gaps(stamps)) >= GAP - SLACK


def test_other_hosts_and_paths_pay_nothing(rates):
    """A host without a rate, a local path, no address: at once, and no bucket made."""
    start = time.monotonic()
    for url in ["https://other.example/x"] * 50 + ["C:/data/tile.tif", None]:
        net.rate_turn(url)
    assert time.monotonic() - start < 0.5
    assert not os.path.exists(net.RATES_DB)


def test_no_turn_in_time(rates, monkeypatch):
    """A host with one request a minute: the second waits RATE_WAIT_S, then RuntimeError."""
    monkeypatch.setattr(net, "HOST_RATES_OF", {"slow.example": 1})
    monkeypatch.setattr(net, "RATE_WAIT_S", 0.3)
    net.rate_turn("https://slow.example/a")
    with pytest.raises(RuntimeError, match="slow.example is busy"):
        net.rate_turn("https://slow.example/b")


def test_get_waits_before_every_attempt(http_server, monkeypatch):
    """net._get asks for a turn before each attempt; a 429 or 503 backs off longer (_sleep(attempt + 3)),
    other failures as before (_sleep(attempt))."""
    events = []
    monkeypatch.setattr(net, "rate_turn", lambda url: events.append(("turn", url)))
    monkeypatch.setattr(net, "_sleep", lambda attempt: events.append(("sleep", attempt)))
    http_server.add("/busy", b"slow down", "text/plain", status=429)
    http_server.add("/down", b"unavailable", "text/plain", status=503)
    http_server.add("/broken", b"error", "text/plain", status=500)
    http_server.add("/tile.tif", b"x", "image/tiff")
    for path, sleeps in (("/busy", [3, 4, 5]), ("/down", [3, 4, 5]), ("/broken", [0, 1, 2])):
        events.clear()
        with pytest.raises(RuntimeError):
            net._get(http_server.url(path))
        url = http_server.url(path)
        assert events == [e for s in sleeps for e in (("turn", url), ("sleep", s))]
        assert len(http_server.requests(path)) == net.RETRIES
    events.clear()
    assert net._get(http_server.url("/tile.tif")).content == b"x"
    assert events == [("turn", http_server.url("/tile.tif"))]


def test_get_in_turns(rates, http_server, monkeypatch):
    """The real turns in _get: four tiles of a host with a rate take three gaps at least."""
    monkeypatch.setattr(net, "HOST_RATES_OF", {"127.0.0.1": PER_MINUTE})
    http_server.add("/tile.tif", b"x", "image/tiff")
    start = time.monotonic()
    for _ in range(4):
        net._get(http_server.url("/tile.tif"))
    assert time.monotonic() - start >= 3 * GAP - SLACK


def test_stac_pages_and_orthophoto_wait(http_server, monkeypatch):
    """A page of a STAC search and each attempt of an orthophoto tile wait for their turn; the
    orthophoto's backoff has jitter and is longer after a 503."""
    import orthophoto
    from sources.indexes.listings import StacItems
    turns, sleeps = [], []
    monkeypatch.setattr(net, "rate_turn", lambda url: turns.append(url))
    monkeypatch.setattr(orthophoto.time, "sleep", lambda s: sleeps.append(s))
    next_page = http_server.url("/stac?limit=100&page=2")
    first = b'{"features": [{"id": "other", "assets": {}}], "links": [{"rel": "next", "href": "%s"}]}'
    http_server.add("/stac?limit=100&bbox=19.0,50.0,19.25,50.25", first % next_page.encode(), "application/json")
    http_server.add("/stac?limit=100&page=2", b'{"features": [], "links": []}', "application/json")
    assert StacItems(http_server.url("/stac"), "EPSG:2056", {2.0: 1000}, 1000).fetch(50.0, 19.0) == {"sheets": []}
    assert len(turns) == 2 and turns[1] == next_page
    turns.clear()
    http_server.add("/tile.jpg", b"busy", "text/plain", status=503)
    with pytest.raises(RuntimeError):
        orthophoto._get(http_server.url("/tile.jpg"), None, 1, 0, 0)
    assert turns == [http_server.url("/tile.jpg")] * orthophoto.RETRIES
    assert [4 <= s <= 12 for s in sleeps[:1]] == [True] and all(s <= orthophoto.BACKOFF_MAX_S for s in sleeps)
    draws = {orthophoto._backoff(1) for _ in range(20)}
    assert len(draws) > 1 and all(1 <= d <= 3 for d in draws)  # jitter: 0.5-1.5 times 2 s
    assert all(orthophoto._backoff(5, True) == orthophoto.BACKOFF_MAX_S for _ in range(5))  # truncated


def test_published_limits():
    """The rates and slot caps of the providers' terms (the comments in net.py quote them)."""
    assert net.HOST_RATES_OF == {"data.geo.admin.ch": 36, "wmts.geo.admin.ch": 1080,
                                 "environment.data.gov.uk": 180, "data.geopf.fr": 2160}
    assert net.HOST_SLOTS_OF == {"data.bev.gv.at": 2, "www.nic.funet.fi": 4, "mirrors.nic.funet.fi": 4,
                                 "servicios.idee.es": 4,
                                 "wcs-mds.idee.es": 4, "malta.coverage.wetransform.eu": 4,
                                 "www.geodaten-mv.de": 4, "geoservices9.civis.bz.it": 4,
                                 "wcs.geonorge.no": 4,
                                 "ags.cuzk.gov.cz": 4,
                                 "geocloud.landesvermessung.sachsen.de": 4, "opengeodata.lgl-bw.de": 4,
                                 "www.wcs.nrw.de": 4, "siatservices.provincia.tn.it": 4,
                                 "data.source.coop": 4, "inspire.brandenburg.de": 4,
                                 "geodaten.schleswig-holstein.de": 4, "gis.arso.gov.si": 2,
                                 "spatial-img.information.qld.gov.au": 4,
                                 "ftp.natt.is": 4, "gis.natt.is": 4}
    assert all(n < net.HOST_SLOTS for n in net.HOST_SLOTS_OF.values())


def test_catalogue_hosts_named():
    """Every host with a rate or a cap is one the catalogue names (a renamed host would lose its
    limit); of Funet's two names of the same servers, one is enough."""
    import inspect
    import sources.catalogue as catalogue
    text = "".join(inspect.getsource(m) for m in catalogue.FAMILIES)
    funet = {"www.nic.funet.fi", "mirrors.nic.funet.fi"}
    for host in set(net.HOST_RATES_OF) | set(net.HOST_SLOTS_OF) - funet:
        assert re.search(rf"//{re.escape(host)}\b", text), host
    assert any(re.search(rf"//{re.escape(host)}\b", text) for host in funet)


def _wcs_requests(monkeypatch, layer):
    asked = []

    def fake(url, params=None, headers=None):
        asked.append(list(params))
        request = dict(params)["REQUEST"]
        return 200, "image/tiff" if request == "GetCoverage" else "text/xml", b"<CoverageDescription>"
    monkeypatch.setattr(probe, "_http", fake)
    assert probe._coverage("unused", layer, 56.0, 10.0) == (probe.OK, probe.OK)
    return asked


def test_probe_speaks_wcs_1_0_0_with_a_key(monkeypatch, tmp_path):
    """A 1.0.0 service with a key (Denmark): DescribeCoverage and a 16 x 16 GetCoverage in 1.0.0, the key
    in both; without the key the probe fails with the reader's message, nothing asked."""
    layer = src.WcsTiles("DHM test", "https://wcs.example/dhm", "dhm_terraen", "EPSG:25832", "fake/dhm",
                         native_res=0.4, tile_px=2000, fmt="GTiff", version="1.0.0",
                         key_params=(("apikey", "datafordeler_api_key"),))
    monkeypatch.setenv("DATAFORDELER_API_KEY", "test-key")
    monkeypatch.setattr(probe, "host_slot", lambda cache_dir, url: contextlib.nullcontext())
    describe, coverage = _wcs_requests(monkeypatch, layer)
    assert describe == [("SERVICE", "WCS"), ("VERSION", "1.0.0"), ("REQUEST", "DescribeCoverage"),
                        ("COVERAGE", "dhm_terraen"), ("apikey", "test-key")]
    params = dict(coverage)
    assert params["VERSION"] == "1.0.0" and params["COVERAGE"] == "dhm_terraen" and params["CRS"] == "EPSG:25832"
    assert params["WIDTH"] == params["HEIGHT"] == "16" and params["FORMAT"] == "GTiff"
    left, bottom, right, top = map(float, params["BBOX"].split(","))
    assert right - left == pytest.approx(6.4) and top - bottom == pytest.approx(6.4)
    assert params["apikey"] == "test-key" and "SUBSET" not in params
    monkeypatch.delenv("DATAFORDELER_API_KEY")
    monkeypatch.setattr(settings, "SECRETS_DIR", str(tmp_path))  # no Docker secret either
    with pytest.raises(RuntimeError, match="needs a key"):
        _wcs_requests(monkeypatch, layer)


def test_probe_wcs_2_0_1_as_before(monkeypatch):
    """A 2.0.1 service: the same requests the probe sent before it asked the reader."""
    monkeypatch.setattr(probe, "host_slot", lambda cache_dir, url: contextlib.nullcontext())
    layer = src.WcsTiles("WCS test", "https://wcs.example/wcs", "dtm", "EPSG:32633", "fake/wcs", native_res=1.0,
                         fetch_res=2.0, axes=("E", "N"))
    describe, coverage = _wcs_requests(monkeypatch, layer)
    assert describe == [("SERVICE", "WCS"), ("VERSION", "2.0.1"), ("REQUEST", "DescribeCoverage"),
                        ("COVERAGEID", "dtm")]
    from rasterio.warp import transform as warp
    (x,), (y,) = warp("EPSG:4326", "EPSG:32633", [10.0], [56.0])
    assert coverage == [("SERVICE", "WCS"), ("VERSION", "2.0.1"), ("REQUEST", "GetCoverage"), ("COVERAGEID", "dtm"),
                        ("FORMAT", "image/tiff"), ("SUBSET", f"E({x - 16:.3f},{x + 16:.3f})"),
                        ("SUBSET", f"N({y - 16:.3f},{y + 16:.3f})"), ("SCALESIZE", "E(16),N(16)")]


def test_describe_coverage_waits(http_server, monkeypatch):
    """WcsReader's DescribeCoverage (coverage_extent) waits for its turn; without one in time the
    extent is unknown, nothing asked."""
    from sources.readers.wcsreader import WcsReader
    turns = []
    monkeypatch.setattr(net, "rate_turn", lambda url: turns.append(url))
    http_server.add("/wcs?SERVICE=WCS&VERSION=2.0.1&REQUEST=DescribeCoverage&COVERAGEID=dem",
                    b"<gml:lowerCorner>0 0</gml:lowerCorner><gml:upperCorner>10 20</gml:upperCorner>", "text/xml")
    reader = WcsReader("test", http_server.url("/wcs"), "dem", "EPSG:3035", 1.0, 100, "image/tiff", ("x", "y"),
                       None, False)
    assert reader.coverage_extent() == (0.0, 0.0, 10.0, 20.0)
    assert turns == [http_server.url("/wcs")]

    def busy(url):
        raise RuntimeError("busy")
    monkeypatch.setattr(net, "rate_turn", busy)
    other = WcsReader("test", http_server.url("/other"), "dem", "EPSG:3035", 1.0, 100, "image/tiff", ("x", "y"),
                      None, False)
    assert other.coverage_extent() is None
    assert not http_server.requests("/other")


def test_probe_time_per_source():
    """Two minutes per source: swisstopo's STAC pages alone take about 40 s at 36 requests a minute."""
    import inspect
    assert probe.TIMEOUT_S == 120
    assert inspect.signature(probe.run).parameters["timeout"].default == 120
