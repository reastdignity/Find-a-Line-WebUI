"""Per-host request rates (sources.net.rate_turn, HOST_RATES_OF) and slot caps (HOST_SLOTS_OF):
the turns spread evenly over threads and processes, every attempt of the download code waits for
one, a 429 or 503 backs off longer, and the probe asks a WCS as its reader does (version, keys).

conftest.py empties HOST_RATES_OF for every other test module; here each test sets its own hosts
and moves the bucket into tmp_path (net.RATES_DB)."""

import contextlib
import inspect
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
GAP_MS = 1000 * GAP
SLACK = 0.02  # the bucket's clock (whole ms of time_ns) against the test's monotonic one


@pytest.fixture
def rates(tmp_path, monkeypatch):
    """Only the test host has a rate; the bucket in tmp_path."""
    monkeypatch.setattr(net, "HOST_RATES_OF", {HOST: PER_MINUTE})
    monkeypatch.setattr(net, "RATES_DB", str(tmp_path / "rates.sqlite"))
    return tmp_path


def _gaps(stamps):
    stamps = sorted(stamps)
    return [b - a for a, b in zip(stamps, stamps[1:])]


# The turns are measured as the bucket grants them: the time (ms) each granted permit carries, which
# the bucket compares under its file lock. A clock read by the caller after rate_turn returned measured
# the way from the permit to the read too: a thread or process descheduled there for 50 ms (a busy
# machine) put two reads 52 ms apart, with turns 100 ms apart. The permit carries the time it was asked
# at only because rate_turn polls with timeout 0: pyrate-limiter's own wait stamps the time it planned
# to wake at (the comment in net.rate_turn), so the tests also check that nothing waits inside it.
def permit_recorders(permits, waits):
    """SQLiteBucket.put and Limiter.try_acquire that note each granted permit's time (ms) in permits
    and each try_acquire's timeout in waits (also run by the child processes below)."""
    from pyrate_limiter import Limiter, SQLiteBucket
    put, acquire = SQLiteBucket.put, Limiter.try_acquire

    def recorded(self, item):
        granted = put(self, item)
        if granted:
            permits.append(item.timestamp)
        return granted

    def asked(self, *args, **kwargs):
        waits.add(kwargs.get("timeout", args[3] if len(args) > 3 else -1))  # name, weight, blocking, timeout
        return acquire(self, *args, **kwargs)
    return recorded, asked


def _record_permits(monkeypatch):
    from pyrate_limiter import Limiter, SQLiteBucket
    permits, waits = [], set()
    recorded, asked = permit_recorders(permits, waits)
    monkeypatch.setattr(SQLiteBucket, "put", recorded)
    monkeypatch.setattr(Limiter, "try_acquire", asked)
    return permits, waits


def test_turns_spread_over_threads(rates, monkeypatch):
    """Four threads, five requests each: one turn every 60/n s, never two closer."""
    permits, waits = _record_permits(monkeypatch)

    def ask():
        for _ in range(5):
            net.rate_turn(f"https://{HOST}/file.tif")
    threads = [threading.Thread(target=ask) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(permits) == 20 and waits == {0}
    assert min(_gaps(permits)) >= GAP_MS
    assert max(permits) - min(permits) >= 19 * GAP_MS


_CHILD = inspect.getsource(permit_recorders) + r'''
import sys
from pyrate_limiter import Limiter, SQLiteBucket
sys.path.insert(0, sys.argv[1])
from sources import net
net.RATES_DB = sys.argv[2]
net.HOST_RATES_OF = {sys.argv[3]: int(sys.argv[4])}
permits, waits = [], set()
SQLiteBucket.put, Limiter.try_acquire = permit_recorders(permits, waits)
for _ in range(6):
    net.rate_turn(f"https://{sys.argv[3]}/x")
assert len(permits) == 6 and waits == {0}, (permits, waits)
with open(sys.argv[5], "w") as f:
    f.write("\n".join(repr(s) for s in permits))
'''


def test_turns_spread_over_processes(rates):
    """Two processes share the bucket: their turns together are 60/n s apart."""
    script = rates / "child.py"
    script.write_text(_CHILD, encoding="utf-8")
    outs = [rates / f"stamps{n}.txt" for n in range(2)]
    children = [subprocess.Popen([sys.executable, str(script), REPO, net.RATES_DB, HOST, str(PER_MINUTE), str(out)])
                for out in outs]
    assert [c.wait(timeout=120) for c in children] == [0, 0]
    stamps = [int(line) for out in outs for line in out.read_text().split()]
    assert len(stamps) == 12
    assert min(_gaps(stamps)) >= GAP_MS


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


def test_a_share_of_the_rate_takes_turns_of_its_own(rates, monkeypatch):
    """share < 1 takes the host's turn and then one of a bucket at that share of the rate (at least 1 a minute):
    six such requests at a third of 600 a minute are 300 ms apart; the host's own requests keep its rate."""
    asked = []
    turn = net._turn
    monkeypatch.setattr(net, "_turn", lambda host, per_minute: (asked.append(per_minute), turn(host, per_minute)))
    start = time.monotonic()
    for _ in range(6):
        net.rate_turn(f"https://{HOST}/piece", share=1 / 3)
    assert time.monotonic() - start >= 5 * 0.3 - SLACK
    assert asked == [600, 200] * 6
    asked.clear()
    net.rate_turn(f"https://{HOST}/tile")
    net.rate_turn("https://other.example/piece", share=1 / 3)  # no rate: nothing
    assert asked == [600]
    monkeypatch.setattr(net, "HOST_RATES_OF", {HOST: 2})
    asked.clear()
    net.rate_turn(f"https://{HOST}/x", share=0.1)
    assert asked == [2, 1]


def test_split_pieces_take_the_lower_rate(monkeypatch):
    """A piece of a split WCS tile asks its turn at SPLIT_RATE_SHARE of the host's rate (England's 429s at the full
    rate, November 2026)."""
    from sources.readers import wcsreader
    turns = []
    monkeypatch.setattr(net, "rate_turn", lambda url, share=1.0: turns.append(share))

    class Answer:
        status_code, headers, content, text = 200, {"content-type": "image/tiff"}, b"II*\x00", ""
    monkeypatch.setattr(wcsreader.requests, "get", lambda *a, **kw: Answer())
    reader = wcsreader.WcsReader("test", "https://ea.example/wcs", "dtm", "EPSG:27700", 1.0, 250, "image/tiff",
                                 ("E", "N"), None, False, split_on_error=True)
    assert reader._request_piece(0, 0, 250, 250, 1.0).content == b"II*\x00"
    assert turns == [wcsreader.SPLIT_RATE_SHARE] and 0 < wcsreader.SPLIT_RATE_SHARE < 1


def test_the_threads_of_a_process_queue_for_the_slots_in_turn():
    """net._Queue gives its places in the order asked: a thread releasing a place and asking again at once goes
    behind those already waiting (threading.Semaphore let it take the place back, so a waiter could lose for an
    hour: Slovenia's pass, 8 threads for ARSO's 2 slots, 2026-11-13)."""
    queue, order = net._Queue(1), []
    queue.acquire()

    def wait(name):
        queue.acquire()
        order.append(name)
        queue.release()
    threads = []
    for name in "abc":
        tickets = queue.next_ticket
        threads.append(threading.Thread(target=wait, args=(name,)))
        threads[-1].start()
        while queue.next_ticket == tickets:  # its ticket taken: it waits
            time.sleep(0.001)
    queue.release()
    queue.acquire()  # at once again: behind a, b and c
    order.append("main")
    queue.release()
    for t in threads:
        t.join()
    assert order == ["a", "b", "c", "main"]


def test_slots_of_a_process_never_time_out_on_its_own_threads(tmp_path, monkeypatch):
    """Eight threads of one process for a host of 2 slots, each holding it for longer than LOCK_WAIT_S: they wait
    for each other in the queue, never for the file locks (which LOCK_WAIT_S bounds: other processes)."""
    monkeypatch.setitem(net.HOST_SLOTS_OF, "queue.example", 2)
    monkeypatch.setattr(net, "LOCK_WAIT_S", 0.05)
    errors, inside, most = [], [0], [0]
    lock = threading.Lock()

    def download():
        try:
            with net.host_slot(str(tmp_path), "https://queue.example/x"):
                with lock:
                    inside[0] += 1
                    most[0] = max(most[0], inside[0])
                time.sleep(0.1)
                with lock:
                    inside[0] -= 1
        except RuntimeError as e:
            errors.append(e)
    threads = [threading.Thread(target=download) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == [] and most[0] == 2


def _queued(queue, n):
    """Wait until n tickets are taken (their threads wait in the queue)."""
    while queue.next_ticket < n:
        time.sleep(0.001)


def test_a_waiter_that_times_out_gives_its_ticket_up():
    """A waiter whose time runs out leaves the queue: the ticket behind it is served when a place frees, not
    stuck behind a ticket nobody will take."""
    queue, got = net._Queue(1), []
    queue.acquire()
    late = threading.Thread(target=lambda: got.append(("late", queue.acquire(0.05))))
    late.start()
    _queued(queue, 2)
    after = threading.Thread(target=lambda: got.append(("after", queue.acquire(30))))
    after.start()
    _queued(queue, 3)
    late.join()
    queue.release()
    after.join()
    assert got == [("late", False), ("after", True)] and queue.abandoned == set()


def test_a_waiter_leaving_by_an_exception_gives_its_ticket_up(monkeypatch):
    """Any exception in the wait (an interrupt) leaves the ticket unserved: the next one is not stuck behind it."""
    queue, got = net._Queue(1), []
    queue.acquire()
    real_wait, first = queue.cond.wait, [True]

    def wait(timeout=None):
        if threading.current_thread().name == "broken" and first[0]:
            first[0] = False
            raise KeyboardInterrupt
        return real_wait(timeout)
    monkeypatch.setattr(queue.cond, "wait", wait)

    def broken():
        try:
            queue.acquire()
        except KeyboardInterrupt:
            got.append("interrupted")
    t1 = threading.Thread(target=broken, name="broken")
    t1.start()
    t1.join()
    t2 = threading.Thread(target=lambda: got.append(queue.acquire(30)))
    t2.start()
    _queued(queue, 3)
    queue.release()
    t2.join()
    assert got == ["interrupted", True]


def test_a_hung_sibling_is_an_error_after_the_queue_wait(tmp_path, monkeypatch):
    """A thread waiting longer than QUEUE_WAIT_S for its process's own downloads from a host: an error saying so,
    not the message of other searches; the place it waited for still serves the next thread."""
    monkeypatch.setitem(net.HOST_SLOTS_OF, "hang.example", 1)
    monkeypatch.setattr(net, "QUEUE_WAIT_S", 0.05)
    release, holding = threading.Event(), threading.Event()

    def hung():
        with net.host_slot(str(tmp_path), "https://hang.example/x"):
            holding.set()
            release.wait(30)
    t = threading.Thread(target=hung)
    t.start()
    holding.wait(30)
    with pytest.raises(RuntimeError, match="hang.example is busy with this process's own downloads"):
        with net.host_slot(str(tmp_path), "https://hang.example/x"):
            pass
    release.set()
    t.join()
    with net.host_slot(str(tmp_path), "https://hang.example/x"):
        pass


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
                                 "environment.data.gov.uk": 180, "data.geopf.fr": 2160,
                                 "tiles-eu1.arcgis.com": 54, "basisdata.nl": 54,
                                 "mirror.findaline.lukawski.org": 600}
    assert net.HOST_SLOTS_OF == {"data.bev.gv.at": 2, "www.nic.funet.fi": 4, "mirrors.nic.funet.fi": 4,
                                 "servicios.idee.es": 4,
                                 "wcs-mds.idee.es": 4, "malta.coverage.wetransform.eu": 4,
                                 "www.geodaten-mv.de": 4, "geoservices9.civis.bz.it": 4,
                                 "wcs.geonorge.no": 4,
                                 "ags.cuzk.gov.cz": 4,
                                 "geocloud.landesvermessung.sachsen.de": 4, "opengeodata.lgl-bw.de": 4,
                                 "www.wcs.nrw.de": 4, "siatservices.provincia.tn.it": 4,
                                 "data.source.coop": 4, "mapy.geoportal.gov.pl": 4,
                                 "inspire.brandenburg.de": 4,
                                 "geodaten.schleswig-holstein.de": 4, "gis.arso.gov.si": 2,
                                 "spatial-img.information.qld.gov.au": 4, "geodata.npolar.no": 4,
                                 "ftp.natt.is": 4, "gis.natt.is": 4,
                                 "www.shop.lvgl.saarland.de": 2, "nrs.objectstore.gov.bc.ca": 4,
                                 "data.slackmap.com": 2, "api.slackmap.com": 1, "services.ga.gov.au": 2,
                                 "visualizador.ide.uy": 2, "tinitaly.pi.ingv.it": 2,
                                 "webgis.regione.sardegna.it": 2,
                                 "service.pdok.nl": 4, "basisdata.nl": 1, "cdn.foroyakort.fo": 2,
                                 "www.inegi.org.mx": 2, "eservices.dls.moi.gov.cy": 2, "geoportaal.maaruum.ee": 2, "www502.regione.toscana.it": 2,
                                 "tiles-eu1.arcgis.com": 2, "tiles.arcgis.com": 2, "admin.opendatani.gov.uk": 2,
                                 "www.daten-hamburg.de": 2, "ws.gisetl.lrc.gov.on.ca": 2, "gdi2.geo.bremen.de": 2,
                                 "gic-tokyo.s3.ap-northeast-1.amazonaws.com": 2,
                                 "virtual-shizuoka.s3.ap-northeast-1.amazonaws.com": 2,
                                 "japan-pointcloud.s3.ap-northeast-1.amazonaws.com": 2,
                                 "kanagawa-pointcloud.s3.ap-northeast-1.amazonaws.com": 2,
                                 "gic-miyagi.s3.ap-northeast-1.amazonaws.com": 2, "miyagi.dataeye.jp": 2,
                                 "gsic-opendata.s3.ap-northeast-1.amazonaws.com": 2, "www.geospatial.jp": 2,
                                 "bulkdata.csdi.gov.hk": 2, "portal.csdi.gov.hk": 2,
                                 "mirror.findaline.lukawski.org": 2}
    assert all(n < net.HOST_SLOTS for n in net.HOST_SLOTS_OF.values())


def test_catalogue_hosts_named():
    """Every host with a rate or a cap is one the catalogue names (a renamed host would lose its
    limit); of Funet's two names of the same servers, one is enough. SlackMap's hosts are those of
    tools/slackmap_data.py (the truth check), not the catalogue's; the project's data server is
    sources/readers/tilebases.py's MIRROR_URL."""
    import inspect
    import sources.catalogue as catalogue
    import sources.readers.tilebases as tilebases
    text = "".join(inspect.getsource(m) for m in (*catalogue.FAMILIES, tilebases))
    funet = {"www.nic.funet.fi", "mirrors.nic.funet.fi"}
    tools = {"data.slackmap.com", "api.slackmap.com"}
    with open(os.path.join(REPO, "tools", "slackmap_data.py"), encoding="utf-8") as f:
        tool = f.read()
    for host in tools:
        assert re.search(rf"//{re.escape(host)}\b", tool), host
    for host in set(net.HOST_RATES_OF) | set(net.HOST_SLOTS_OF) - funet - tools:
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


@pytest.fixture(scope="module")
def ahn_like(tmp_path_factory):
    """A file of the Caribbean AHN's kind (float32 0.5 m, tiled 256, DEFLATE, overviews), 600 x 600 px."""
    import numpy as np
    import rasterio as rio
    from rasterio.transform import from_origin
    path = tmp_path_factory.mktemp("ahn") / "M_TEST2023.TIF"
    rows, cols = np.mgrid[0:600, 0:600]
    with rio.open(path, "w", driver="GTiff", width=600, height=600, count=1, dtype="float32", crs="EPSG:2180",
                  transform=from_origin(2000.0, 4000.0, 0.5, 0.5), tiled=True, blockxsize=256, blockysize=256,
                  compress="deflate", nodata=3.4e38) as dst:
        dst.write((100 + rows * 0.3 + cols * 0.1 + np.sin(cols / 7.0)).astype(np.float32), 1)
        dst.build_overviews([2, 4])
    return path


def _block_reads(http_server, ahn_like, tmp_path, slots: int, threads: int = 4):
    """Four blocks of 100 m (200 px, over one to four of the file's 256 px tiles) of a FileBlocks layer whose file is on
    the test server, downloaded by `threads` threads at once as a search downloads them (_download_and_record: the
    tile's lock, the host's slot, the reader), the host at `slots` slots. Every answer waits 30 ms, so requests
    answered at once show in peak(). Returns the layer and its tiles."""
    from sources.layers.fileblocks import FileBlocks
    from http_server import Answer
    import grid as gd
    body = ahn_like.read_bytes()

    def slow(request):
        time.sleep(0.03)
        return Answer(200, body, {"Content-Type": "image/tiff"})
    http_server.route("/ahn/", slow)
    net.HOST_SLOTS_OF["127.0.0.1"] = slots
    layer = FileBlocks("AHN test", "test/ahn/1", "EPSG:2180", 0.5, 100, http_server.url("/ahn/M_TEST2023.TIF"),
                       extent=(2000.0, 3700.0, 2300.0, 4000.0), force_crs=True)
    tiles = layer.tiles(gd.Grid(left=2000.0, top=4000.0, res=0.5, height=400, width=400, crs="EPSG:2180"))[:4]
    assert len(tiles) == 4
    cache_dir = str(tmp_path / f"cache{slots}")
    os.makedirs(cache_dir)
    workers = [threading.Thread(target=layer._download_and_record, args=(tile, cache_dir)) for tile in tiles]
    for t in workers[:threads]:
        t.start()
    for t in workers[:threads]:
        t.join()
    return layer, tiles, cache_dir


def test_window_reads_take_turns_and_serial_ranges(http_server, ahn_like, tmp_path, monkeypatch):
    """Each block read through GDAL's /vsicurl/ of a host with a rate takes one turn of it (net.rate_turn, inside
    the host's slot: _download_and_record holds it), and a host of one slot never has two requests answered at once:
    not two blocks (the slot), not two ranges of one block (net.single_connection: GDAL's ranges one after another,
    where GDAL_HTTP_MULTIRANGE=YES asks them on several connections at once). Not one connection: GDAL keeps one
    per thread (such a host is read through our own ranges: test_ranged_reads_one_connection_a_turn_per_request).
    The values are a local read's."""
    import numpy as np
    import rasterio as rio
    import rasterio.cache
    monkeypatch.setattr(net, "HOST_SLOTS_OF", dict(net.HOST_SLOTS_OF))
    turns, inside = [], []
    holding = threading.local()
    host_slot = net.host_slot

    @contextlib.contextmanager
    def slot(cache_dir, url):
        with host_slot(cache_dir, url):
            holding.on = True
            try:
                yield
            finally:
                holding.on = False
    import sources.layer
    monkeypatch.setattr(sources.layer, "host_slot", slot)
    monkeypatch.setattr(net, "rate_turn", lambda url, share=1.0: (turns.append(url),
                                                                  inside.append(getattr(holding, "on", False))))
    url = http_server.url("/ahn/M_TEST2023.TIF")
    rasterio.cache.invalidate(url)
    layer, tiles, cache_dir = _block_reads(http_server, ahn_like, tmp_path, slots=1)
    assert turns == [url] * 4 and all(inside)
    assert http_server.peak("/ahn/") == 1 and len(http_server.requests("/ahn/")) > 4
    local = type(layer)("AHN test", "test/ahn/1", "EPSG:2180", 0.5, 100, str(ahn_like),
                        extent=(2000.0, 3700.0, 2300.0, 4000.0), force_crs=True)
    for tile in tiles:
        path = str(tmp_path / "local.tif")
        local.download_tile(tile, path)
        with rio.open(layer.tile_path(cache_dir, tile)) as a, rio.open(path) as b:
            assert np.array_equal(a.read(1), b.read(1), equal_nan=True)


def test_window_reads_overlap_without_the_cap(http_server, ahn_like, tmp_path, monkeypatch):
    """The control of the test above: at 8 slots the same reads have requests answered at once (blocks in parallel
    and GDAL's parallel ranges), so peak() would see an overlap at one slot."""
    import rasterio.cache
    monkeypatch.setattr(net, "HOST_SLOTS_OF", dict(net.HOST_SLOTS_OF))
    rasterio.cache.invalidate(http_server.url("/ahn/M_TEST2023.TIF"))
    _block_reads(http_server, ahn_like, tmp_path, slots=8)
    assert http_server.peak("/ahn/") > 1


def test_single_connection_hosts():
    """basisdata.nl takes one connection; a host of the default slots, a local path and no address do not."""
    assert net.single_connection("https://basisdata.nl/hwh-ortho/x.TIF")
    assert not net.single_connection("https://service.pdok.nl/x.tif")
    assert not net.single_connection("C:/data/x.tif") and not net.single_connection(None)


def test_probe_time_per_source():
    """Two minutes per source: swisstopo's STAC pages alone take about 40 s at 36 requests a minute."""
    import inspect
    assert probe.TIMEOUT_S == 120
    assert inspect.signature(probe.run).parameters["timeout"].default == 120


class Counting:
    """A local HTTP server of one file (single ranges, as our own range requests ask them) that counts the TCP
    connections it accepted and the most open at once, idle keep-alive ones included, and its requests; with
    `to`, every request is answered 307 to that address instead (as basisdata.nl answers to its object storage)."""

    def __init__(self, body: bytes = b"", to: str = ""):
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        from http_server import _ranges
        self.open = self.most = self.accepted = 0
        self.requests = []
        lock, server = threading.Lock(), self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args):
                pass

            def setup(self):
                super().setup()
                with lock:
                    server.open, server.accepted = server.open + 1, server.accepted + 1
                    server.most = max(server.most, server.open)

            def finish(self):
                try:
                    super().finish()
                finally:
                    with lock:
                        server.open -= 1

            def do_GET(self):
                with lock:
                    server.requests.append(self.headers.get("Range"))
                time.sleep(0.01)
                if to:
                    self.send_response(307)
                    self.send_header("Location", to)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                (first, last), = _ranges(self.headers["Range"], len(body))
                part = body[first:last + 1]
                self.send_response(206)
                self.send_header("Content-Type", "image/tiff")
                self.send_header("Content-Range", f"bytes {first}-{last}/{len(body)}")
                self.send_header("Content-Length", str(len(part)))
                self.end_headers()
                self.wfile.write(part)

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.httpd.daemon_threads = True
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}/f/M_TEST2023.TIF"
        threading.Thread(target=self.httpd.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True).start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


@pytest.fixture
def redirected(ahn_like, monkeypatch):
    """The file on a server behind another that answers every request with 307 to it (the second on "localhost",
    so the two are two hosts to requests); the first at one slot."""
    target = Counting(ahn_like.read_bytes())
    target.url = target.url.replace("127.0.0.1", "localhost")
    front = Counting(to=target.url)
    monkeypatch.setattr(net, "HOST_SLOTS_OF", dict(net.HOST_SLOTS_OF, **{"127.0.0.1": 1}))
    monkeypatch.setattr(net, "_shared", {})
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    yield front, target
    front.close()
    target.close()


def test_ranged_reads_one_connection_a_turn_per_request(redirected, ahn_like, tmp_path, monkeypatch):
    """A layer of a host of one slot read through our own ranges (FileBlocks(ranged=True): the Caribbean islands'),
    four blocks by four download threads at once: every range request takes exactly one turn of the host (in
    ranges.get_range, none in _read_block on top), each is one request to the host and one to the address it
    redirects to, and at no moment is more than one TCP connection open to either (net.session(url): one session
    of one connection per pool), although each thread read; the blocks are a local read's."""
    import numpy as np
    import rasterio as rio
    import grid as gd
    from sources.layers.fileblocks import FileBlocks
    front, target = redirected
    turns = []
    monkeypatch.setattr(net, "rate_turn", lambda url, share=1.0: turns.append(url))

    def layer(where, ranged=True):
        return FileBlocks("AHN test", "test/ahn/1", "EPSG:2180", 0.5, 100, where,
                          extent=(2000.0, 3700.0, 2300.0, 4000.0), force_crs=True, ranged=ranged)
    remote = layer(front.url)
    tiles = remote.tiles(gd.Grid(left=2000.0, top=4000.0, res=0.5, height=400, width=400, crs="EPSG:2180"))[:4]
    cache_dir = str(tmp_path / "cache")
    os.makedirs(cache_dir)
    errors = []

    def read(tile):
        try:
            remote._download_and_record(tile, cache_dir)
        except Exception as e:  # noqa: BLE001 - asserted below
            errors.append(e)
    workers = [threading.Thread(target=read, args=(tile,)) for tile in tiles]
    for t in workers:
        t.start()
    for t in workers:
        t.join()
    assert errors == []
    assert turns == [front.url] * len(front.requests) and len(front.requests) == len(target.requests) > 4
    assert (front.most, target.most) == (1, 1), (front.accepted, target.accepted)
    local = layer(str(ahn_like), ranged=False)
    for tile in tiles:
        path = str(tmp_path / "local.tif")
        local.download_tile(tile, path)
        with rio.open(remote.tile_path(cache_dir, tile)) as a, rio.open(path) as b:
            assert np.array_equal(a.read(1), b.read(1), equal_nan=True)


def test_one_connection_needs_the_shared_session(redirected, monkeypatch):
    """The control of the test above: the same reads on a session per thread (net.session as before) have more than
    one connection open at once, so the count above would see it."""
    front, target = redirected
    from sources.readers import ranges
    plain = net.session
    monkeypatch.setattr(net, "session", lambda url=None: plain())
    monkeypatch.setattr(net, "rate_turn", lambda url, share=1.0: None)
    barrier = threading.Barrier(4)

    def read():
        barrier.wait()
        ranges.get_range(front.url, 0, 999)
        barrier.wait()  # all four connections still open
    workers = [threading.Thread(target=read) for _ in range(4)]
    for t in workers:
        t.start()
    for t in workers:
        t.join()
    assert front.most > 1


def test_gdal_reads_take_a_turn_per_attempt(http_server, tmp_path, monkeypatch):
    """A block read through GDAL whose header came cut short (Incomplete: the file of tests/test_windows.py, its
    tiles' offsets beyond GDAL's first read) is read again, and every attempt takes its own turn of the host's
    rate: two attempts, two turns."""
    import numpy as np
    import rasterio as rio
    import rasterio.cache
    from rasterio.transform import from_origin
    from sources.readers import windows
    turns = []
    monkeypatch.setattr(net, "rate_turn", lambda url, share=1.0: turns.append(url))
    monkeypatch.setattr(net, "_sleep", lambda attempt: None)
    path = tmp_path / "big.tif"
    band = (np.arange(2048 * 2048, dtype=np.float32).reshape(2048, 2048) % 5000) + 100
    with rio.open(path, "w", driver="GTiff", width=2048, height=2048, count=1, dtype="float32", crs="EPSG:3035",
                  transform=from_origin(0, 2048, 1, 1), tiled=True, blockxsize=16, blockysize=16) as dst:
        dst.write(band, 1)
    http_server.add("/cut/big.tif", path.read_bytes(), "image/tiff")
    http_server.fault("/cut/big.tif", "truncate", lambda n, r: n == 1)
    url = http_server.url("/cut/big.tif")
    rasterio.cache.invalidate(url)
    windows._read_block([("cut", url, 2020)], "EPSG:3035", from_origin(1000, 1048, 1, 1), (40, 40),
                        str(tmp_path / "block.tif"), "test")
    assert turns == [url, url]
    with rio.open(tmp_path / "block.tif") as block:
        assert (block.read(1) == band[1000:1040, 1000:1040]).all()


@pytest.fixture
def one_slot_tools(http_server, ahn_like, monkeypatch):
    """The AHN-like file on the test server, its host at one slot; net.host_slot, net.rate_turn and net.gdal_open
    recorded: the slots held (data folder, url), the turns, GDAL's options at each open."""
    import rasterio as rio
    sys.path.insert(0, os.path.join(REPO, "tools"))
    monkeypatch.setattr(net, "HOST_SLOTS_OF", dict(net.HOST_SLOTS_OF, **{"127.0.0.1": 1}))
    http_server.add("/tools/M_TEST2023.TIF", ahn_like.read_bytes(), "image/tiff")
    seen = {"slots": [], "turns": [], "opens": []}
    slot, gdal_open = net.host_slot, net.gdal_open

    @contextlib.contextmanager
    def held(cache_dir, url):
        with slot(cache_dir, url):
            seen["slots"].append((cache_dir, url))
            yield

    @contextlib.contextmanager
    def opening():
        with gdal_open():
            seen["opens"].append(dict(rio.env.getenv()))
            yield
    monkeypatch.setattr(net, "host_slot", held)
    monkeypatch.setattr(net, "gdal_open", opening)
    monkeypatch.setattr(net, "rate_turn", lambda url, share=1.0: seen["turns"].append(url))
    return http_server.url("/tools/M_TEST2023.TIF"), seen


def _one_slot_open(options):
    """GDAL's options of an open of a one-slot host's file: the connect timeout, one retry, serial ranges."""
    return (options["GDAL_HTTP_CONNECTTIMEOUT"], options["GDAL_HTTP_MAX_RETRY"], options["GDAL_HTTP_MULTIRANGE"]) == \
        (str(net.CONNECT_TIMEOUT_S), str(net.OPEN_RETRIES), "SERIAL")


def test_check_source_reads_under_the_limits(one_slot_tools, ahn_like, tmp_path):
    """tools/check_source.py's two readers of a source file: GDAL's (_read_source) holds the host's slot, takes a
    turn and opens with the connect timeout, one retry and serial ranges; ours (_read_ranged) holds the slot and
    takes a turn per range request. Both give the file's values."""
    import numpy as np
    import check_source as cs
    from affine import Affine
    url, seen = one_slot_tools
    profile = {"crs": "EPSG:2180", "transform": Affine(0.5, 0, 2050.0, 0, -0.5, 3950.0), "width": 100,
               "height": 100}
    cache_dir = str(tmp_path / "cache")
    local = cs._read_source(str(ahn_like), profile)
    seen["turns"].clear()
    remote = cs._read_source(url, profile, cache_dir=cache_dir)
    assert seen["slots"] == [(cache_dir, url)] and seen["turns"] == [url] and _one_slot_open(seen["opens"][-1])
    assert np.array_equal(remote, local, equal_nan=True)
    seen["slots"].clear()
    seen["turns"].clear()
    ranged = cs._read_ranged(url, profile, cache_dir=cache_dir)
    assert seen["slots"] == [(cache_dir, url)] and len(seen["turns"]) >= 2 and set(seen["turns"]) == {url}
    assert np.array_equal(ranged, local, equal_nan=True)


def test_obstacle_study_reads_under_the_limits(one_slot_tools, tmp_path):
    """tools/obstacle_study.py's on_grid: the host's slot in the given data folder, a turn per attempt, the open
    with the connect timeout, one retry and serial ranges."""
    import numpy as np
    import obstacle_study
    from rasterio.warp import Resampling
    url, seen = one_slot_tools
    grid = {"crs": "EPSG:2180", "res": 1.0, "left": 2010.0, "top": 3990.0, "width": 50, "height": 50}
    cache_dir = str(tmp_path / "cache")
    values = obstacle_study.on_grid([url], grid, Resampling.max, cache_dir)
    assert values is not None and np.isfinite(values).all()
    assert seen["slots"] == [(cache_dir, url)] and seen["turns"] == [url] and _one_slot_open(seen["opens"][0])


def test_perf_window_reads_predicted_under_the_limits(one_slot_tools, tmp_path):
    """tools/perf_window_reads.py's predicted: each file in its host's slot (held once per host) and its turn,
    opened with one retry; its table says when a rate made the seconds wait."""
    import perf_window_reads as pw
    import grid as gd
    from sources.layers.fileblocks import FileBlocks
    url, seen = one_slot_tools
    layer = FileBlocks("AHN test", "test/ahn/1", "EPSG:2180", 0.5, 100, url, extent=(2000.0, 3700.0, 2300.0, 4000.0))
    tiles = layer.tiles(gd.Grid(left=2001.0, top=3999.0, res=0.5, height=398, width=398, crs="EPSG:2180"))
    cache_dir = str(tmp_path / "cache")
    net.HOST_SLOTS_OF["127.0.0.1"] = 2  # a host of one slot is not measured through GDAL (the test below)
    assert pw.predicted(layer, tiles, cache_dir)["file_tiles"] > 0
    assert seen["slots"] == [(cache_dir, url)] and seen["turns"] == [url]
    assert seen["opens"][0]["GDAL_HTTP_MAX_RETRY"] == str(net.OPEN_RETRIES)
    result = {"source": "bq", "mode": "default", "blocks": 4, "seconds": 9.0, "rate": 54, "peak_memory": 2 ** 20,
              "network": {"bytes": 1e6, "gets": 9, "heads": 1}, "cache": {"bytes": 1e6, "km2": 1.0}}
    assert "bq: its host has a rate of 54 requests a minute" in pw.table([result])
    assert "rate of" not in pw.table([dict(result, rate=None)])


def test_probe_window_serial_for_one_slot(one_slot_tools, tmp_path, monkeypatch):
    """The probe's window read of a one-slot host's file through GDAL asks its ranges one after another
    (_gdal_http(serial=True)) and opens with one retry; another host's in parallel as before."""
    from sources import probe
    from sources.layers.fileblocks import FileBlocks
    import grid as gd
    url, seen = one_slot_tools
    asked = []
    original = probe._gdal_http
    monkeypatch.setattr(probe, "host_slot", lambda cache_dir, url: contextlib.nullcontext())
    monkeypatch.setattr(probe, "_gdal_http", lambda serial=False: (asked.append(serial), original(serial))[1])
    for where, serial in ((url, True), (url.replace("127.0.0.1", "localhost"), False)):
        layer = FileBlocks("AHN test", "test/ahn/1", "EPSG:2180", 0.5, 100, where,
                           extent=(2000.0, 3700.0, 2300.0, 4000.0))
        tile = layer.tiles(gd.Grid(left=2001.0, top=3999.0, res=0.5, height=10, width=10, crs="EPSG:2180"))[0]
        assert probe._window(str(tmp_path), layer, tile).endswith("% with data")
        assert asked[-1] is serial and seen["opens"][-1]["GDAL_HTTP_MAX_RETRY"] == str(net.OPEN_RETRIES)


def test_perf_window_reads_skips_one_connection_layers(one_slot_tools, tmp_path, capsys):
    """predicted never reads through GDAL a layer read through our own ranges, nor one whose host takes one
    connection (GDAL would ask its ranges on several): it says so in a line and gives nothing, no request."""
    import perf_window_reads as pw
    import grid as gd
    from sources.layers.fileblocks import FileBlocks
    url, seen = one_slot_tools
    g = gd.Grid(left=2001.0, top=3999.0, res=0.5, height=398, width=398, crs="EPSG:2180")
    for ranged in (False, True):  # the host at one slot; then a ranged layer on a host of 2
        net.HOST_SLOTS_OF["127.0.0.1"] = 2 if ranged else 1
        layer = FileBlocks("AHN test", "test/ahn/1", "EPSG:2180", 0.5, 100, url,
                           extent=(2000.0, 3700.0, 2300.0, 4000.0), ranged=ranged)
        assert pw.predicted(layer, layer.tiles(g), str(tmp_path / "cache")) is None
        assert "not measured through GDAL" in capsys.readouterr().out
    assert seen["opens"] == [] and seen["turns"] == []
