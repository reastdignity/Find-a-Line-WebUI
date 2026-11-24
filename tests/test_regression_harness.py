"""tests/regression.py's harness, offline (no real search: `run` and `run_osm` stubbed, `measure` fed canned output):
the coastline source stored with a baseline (H1), the outcomes ok, unverified and DIFFERENT (H2) and their exit codes
(H3), the --update guard (H4), the refusal of an empty cache without --cold (H5), seeding a scratch cache from the
real one by hard links (H6), the run log (H7), R17's list of differences (H8), entries run by name only (H9) and the
requests per host and the test lock's token in the run log (H10)."""

import contextlib
import http.server
import importlib.util
import json
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import threading

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location("regression_harness_tool", os.path.join(REPO, "tests", "regression.py"))
regression = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(regression)

WORLD_FILE = regression.coast.SOURCE_WORLD
OVERPASS = regression.coast.SOURCE_OVERPASS
FALLBACK = regression.coast.SOURCE_FALLBACK
NO_SEA = regression.coast.SOURCE_NO_SEA
WARNING_LINE = (f"WARNING: {regression.coast.FALLBACK_WARNING} (502 Server Error: Bad Gateway for url: "
                f"https://overpass-api.de/api/interpreter?...). Using the Copernicus water body mask instead")


@pytest.fixture(autouse=True)
def _own_run_log(tmp_path, monkeypatch):
    """No test appends to the real run log (the test lock's folder)."""
    monkeypatch.setenv("FINDALINE_TEST_LOCK_DIR", str(tmp_path / "locks"))


def _layout(folder) -> str:
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "LAYOUT"), "w") as f:
        f.write("1\n")
    return str(folder)


def _result(coastline=WORLD_FILE, lines=10, exit_code=0, unanswered=None, warned=False, **more) -> dict:
    """What run() gives for a search: its output's coastline line and warning read by measure itself (warned: True
    for a 502 of Overpass, or the text of another cause)."""
    warning = WARNING_LINE if warned is True else (f"WARNING: {regression.coast.FALLBACK_WARNING} ({warned}). Using "
                                                   f"the Copernicus water body mask instead")
    output = (f"Coastline: {coastline}\n" if coastline is not None else "") + (f"{warning}\n" if warned else "")
    found = {**regression.measure(output, "none"), "anchors": 5, "lines": lines, "csv_sha256": "a" * 64,
             "exit": exit_code, "problems": []}
    found.pop("empty_tiles")
    if exit_code:
        found["unanswered"] = unanswered
        found.pop("problems")
    return {**found, **more}


def _expected(coastline=WORLD_FILE, lines=10) -> dict:
    found = {"anchors": 5, "lines": lines, "csv_sha256": "a" * 64}
    return {**found, "coastline": coastline} if coastline else found


@pytest.fixture
def harness(tmp_path, monkeypatch):
    """main() on tests of our own (written to a copy of regression.json) with a stubbed search: `results[id]` is
    what the search of an id gives; returns a function running main with argv, giving (exit code, output, tests
    as stored afterwards)."""
    cache_dir = _layout(tmp_path / "cache")
    tests_file = tmp_path / "regression.json"
    results = {}

    def write(tests):
        tests_file.write_text(json.dumps(tests), encoding="utf-8")

    monkeypatch.setattr(regression, "TESTS", str(tests_file))
    monkeypatch.setattr(regression, "run", lambda tests, test_id, work, cache, browser: dict(results[test_id]))
    monkeypatch.setattr(regression, "write_doc", lambda tests: None)

    def main(*argv, capsys):
        monkeypatch.setattr(sys, "argv", ["regression.py", *argv, *(() if "--cache" in argv else
                                                                  ("--cache", cache_dir))])
        with pytest.raises(SystemExit) as ended:
            regression.main()
        out = capsys.readouterr()
        kept.extend(line.rsplit("logs in ", 1)[1].strip() for line in out.out.splitlines() if "; logs in " in line)
        return ended.value.code, out.out + out.err, json.loads(tests_file.read_text(encoding="utf-8"))

    kept = []

    main.write, main.results, main.cache = write, results, cache_dir
    yield main
    for work in kept:  # the log folders main kept (a difference): their links removed as links first
        for root, dirs, _ in os.walk(work):
            for name in [d for d in dirs if os.path.isjunction(os.path.join(root, d))]:
                os.rmdir(os.path.join(root, name))
                dirs.remove(name)
        shutil.rmtree(work, ignore_errors=True)


def _entry(expected, sets=("quick",), **more) -> dict:
    return {"place": "x", "args": "--lat 1 --lon 2", "sets": list(sets), "expected": expected, "seconds": 1.0, **more}


# H1: the coastline source


def test_measure_reads_the_coastline_line():
    found = regression.measure(f"Data: X (y) - z\nCoastline: {WORLD_FILE}\nFound 3 potential anchors\n", "none")
    assert found["coastline"] == WORLD_FILE and found["anchors"] == 3
    assert regression.measure("Coastline: no sea in the area\n", "none")["coastline"] == "no sea in the area"
    assert "coastline" not in regression.measure("Found 3 potential anchors\n", "none")  # --water without fill
    # two different lines of one search (never seen) are both kept, not one chosen
    assert regression.measure(f"Coastline: a\nCoastline: a\nCoastline: {FALLBACK}\n", "none")["coastline"] \
        == f"a; {FALLBACK}"


def _warning(cause: str) -> str:
    """coast's fallback note carrying `cause`, as findaline.print_event prints it."""
    return (f"\n{'!' * 60}\nWARNING: {regression.coast.FALLBACK_WARNING} ({cause}). Using the Copernicus water body "
            f"mask instead: its shoreline is only accurate to about 70 m\n{'!' * 60}\n")


def _day_cap_text(tmp_path, monkeypatch, limit: int) -> str:
    """osm.OverpassDayMax's own text, raised by osm._count_query when the folder's day is used up."""
    import osm
    monkeypatch.setenv("FINDALINE_OVERPASS_DAY_MAX", str(limit))
    folder = str(tmp_path / f"cap{limit}")
    for _ in range(limit):
        osm._count_query(folder)
    with pytest.raises(osm.OverpassDayMax) as raised:
        osm._count_query(folder)
    return str(raised.value)


@pytest.mark.parametrize("cause", [
    "502 Server Error: Bad Gateway for url: https://overpass-api.de/api/interpreter?...",
    "HTTPSConnectionPool(host='overpass-api.de', port=443): Read timed out. (read timeout=120)",
    "HTTPConnectionPool(host='127.0.0.1', port=9): Max retries exceeded with url: /?... (Caused by "
    "NewConnectionError(\"HTTPConnection(host='127.0.0.1', port=9): Failed to establish a new connection: "
    "[WinError 10061] No connection could be made because the target machine actively refused it\"))",
    "504 Server Error: Gateway Timeout for url: https://overpass-api.de/api/interpreter?...",
])
def test_the_warning_of_an_overpass_that_did_not_answer(cause):
    assert regression.measure(_warning(cause), "none").get("coast_warning") is True


def test_the_warning_of_the_day_cap(tmp_path, monkeypatch):
    """Overpass's day cap of the folder (the search did not ask): its text from osm itself, any number."""
    for limit in (0, 3):
        cause = _day_cap_text(tmp_path, monkeypatch, limit)
        assert regression.measure(_warning(cause), "none").get("coast_warning") is True, cause


@pytest.mark.parametrize("cause", [
    "Expecting value: line 1 column 1 (char 0)",  # a broken theme tile (osm.theme's json.load)
    "could not convert string to float: 'x'",  # another ValueError of our own code
    "",  # nothing in the parentheses
    "500 Server Error: Internal Server Error for url: https://overpass-api.de/api/interpreter?... (timed out)",
    "HTTPSConnectionPool(host='overpass-api.de', port=443): Max retries exceeded (Caused by NameResolutionError("
    "\"Failed to resolve 'overpass-api.de'\"))",
])
def test_the_warning_of_our_own_error_excuses_nothing(cause):
    assert "coast_warning" not in regression.measure(_warning(cause), "none")


def test_measure_reads_the_fallback_warning():
    """The positive sign of the fallback: coast's own note, as findaline.print_event prints it."""
    assert regression.measure(f"\n{'!' * 60}\n{WARNING_LINE}\n{'!' * 60}\n", "none")["coast_warning"] is True
    assert "coast_warning" not in regression.measure(f"Coastline: {FALLBACK}\n", "none")
    assert "coast_warning" not in regression.measure("WARNING: something else could not be downloaded (x)\n", "none")


def test_stored_keeps_the_searchs_own_text():
    assert regression.stored(_result("anything at all"), {}, ok=False)["coastline"] == "anything at all"
    assert "coastline" not in regression.stored(_result(coastline=None), {"coastline": WORLD_FILE}, ok=False)
    assert regression.stored(_result(OVERPASS), {"coastline": WORLD_FILE}, ok=True)["coastline"] == WORLD_FILE
    assert regression.stored(_result(OVERPASS), {"coastline": WORLD_FILE}, ok=False)["coastline"] == OVERPASS
    assert regression.stored(_result(OVERPASS), {}, ok=True)["coastline"] == OVERPASS  # a first baseline


def test_every_stored_coastline_is_a_named_text():
    """Every baseline's coastline is one of coast.py's named texts: a reword there fails here, instead of making
    every baseline's source unknown (and every difference DIFFERENT, never excused)."""
    coast = regression.coast
    named = {coast.SOURCE_WORLD, coast.SOURCE_OVERPASS, coast.SOURCE_FALLBACK, coast.SOURCE_COPERNICUS,
             coast.SOURCE_NO_SEA, coast.SOURCE_NO_COAST}
    stored = {t: test["expected"]["coastline"] for t, test in regression.load().items()
              if test.get("kind") != "osm" and "coastline" in test["expected"]}
    assert len(stored) >= 91
    assert {t: s for t, s in stored.items() if s not in named} == {}
    assert not [t for t, s in stored.items() if s == coast.SOURCE_FALLBACK]


def test_the_coastline_texts_are_coasts(monkeypatch):
    """The texts the harness reads are coast.sea_mask's: "(fallback)" only where Overpass failed, never for an entry
    asking for the Copernicus mask itself."""
    import numpy as np
    import requests
    import coast
    sea = np.array([[True, False]])
    assert coast.sea_mask(None, "unused", "copernicus", sea)[1] == "Copernicus water body mask"
    assert regression.FALLBACK not in coast.sea_mask(None, "unused", "copernicus", sea)[1]
    assert coast.sea_mask(None, "unused", "overpass", np.zeros((1, 2), bool))[1] == "no sea in the area"

    def down(*args):
        raise requests.ConnectionError("down")

    monkeypatch.setattr(coast, "world_file", lambda cache_dir: None)
    monkeypatch.setattr(coast, "_osm_coastline", down)
    assert coast.sea_mask(None, "unused", "overpass", sea)[1] == FALLBACK


# H2: the outcomes


REWORDED = "OSM water polygons (world file)"


@pytest.mark.parametrize("stored, source, world, warned, excused", [
    # a baseline on the world file: Overpass where the folder holds no world file, the fallback with its warning
    (WORLD_FILE, OVERPASS, False, False, True),
    (WORLD_FILE, OVERPASS, True, False, False),  # the real cache holds the world file: only changed code
    (WORLD_FILE, FALLBACK, False, True, True),
    (WORLD_FILE, FALLBACK, False, False, False),  # no warning: no positive sign
    (WORLD_FILE, FALLBACK, True, True, False),
    (WORLD_FILE, WORLD_FILE, True, False, False),  # the same source
    # a baseline on live Overpass
    (OVERPASS, WORLD_FILE, True, False, False),  # a run on the world file is never excused (the reference)
    (OVERPASS, WORLD_FILE, False, False, False),
    (OVERPASS, FALLBACK, True, True, False),  # nothing where the folder holds the world file
    (OVERPASS, FALLBACK, False, True, True),
    # "no sea in the area" is a result, a reworded or unknown text no source, a fallback or no baseline never excuses
    (WORLD_FILE, NO_SEA, False, False, False),
    (NO_SEA, WORLD_FILE, True, False, False),
    (NO_SEA, OVERPASS, False, False, False),
    (WORLD_FILE, REWORDED, True, False, False),
    (REWORDED, OVERPASS, False, False, False),
    (FALLBACK, WORLD_FILE, True, False, False),
    (None, OVERPASS, False, False, False),
    (WORLD_FILE, None, False, False, False),
    (WORLD_FILE, regression.coast.SOURCE_COPERNICUS, False, False, False),
    (WORLD_FILE, f"{OVERPASS}; {FALLBACK}", False, True, False),
])
def test_coastline_excuse(stored, source, world, warned, excused):
    reason = regression.coastline_excuse(stored, source, world, warned)
    assert reason == (f"coastline: {source}; the baseline's: {stored}" if excused else None)


def _judge(test, found, values, problems=(), cross=(), world_file=False, unverified=()):
    """outcome() with every argument given (the code has no defaults: a caller must say each)."""
    return regression.outcome(test, found, list(values), list(problems), list(cross), world_file, tuple(unverified))


def test_outcomes():
    test = _entry(_expected())
    assert _judge(test, _result(OVERPASS), []) == ("ok", None)  # no difference: ok, whatever the source
    assert _judge(test, _result(OVERPASS), [], world_file=True) == ("ok", None)
    assert _judge(test, _result(FALLBACK, warned=True), ["lines: 10 -> 9"]) == \
        ("unverified", f"coastline: {FALLBACK}; the baseline's: {WORLD_FILE}")
    assert _judge(test, _result(), ["lines: 10 -> 9"], world_file=True) == ("DIFFERENT", None)
    assert _judge(_entry(_expected(coastline=None)), _result(FALLBACK, warned=True), ["x"]) == \
        ("DIFFERENT", None)
    assert _judge(test, _result(coastline=None), ["x"]) == ("DIFFERENT", None)
    assert _judge(test, _result(None, exit_code=1, unanswered="a data provider did not answer: x"),
                              [], ["exit code 1"]) == ("unverified", "a data provider did not answer: x")
    assert _judge(test, _result(None, exit_code=1), [], ["exit code 1"]) == ("DIFFERENT", None)
    # the store's, check_profiles' and --browser's problems are never excused by the coastline
    for problem in ("lines.arrow has 9 lines, the export 10", "the map shows 3 spots, the export has 4",
                    "profile of the line at 1.000000, 2.000000 computed again differs in ['clearance']"):
        assert _judge(test, _result(OVERPASS), [], [problem]) == ("DIFFERENT", None)
        assert _judge(test, _result(OVERPASS), ["lines: 10 -> 9"], [problem]) == ("DIFFERENT", None)
    # same_as / without_access_as: excused only by this test or the other one being unverified in this run
    cross = [("the CSV export differs from that of R1", "R1")]
    assert _judge(test, _result(OVERPASS), [], [], cross) == ("DIFFERENT", None)
    assert _judge(test, _result(OVERPASS), [], [], cross, unverified=("R1",)) == \
        ("unverified", "R1 unverified in this run")
    assert _judge(test, _result(OVERPASS), ["lines: 10 -> 9"], [], cross) == \
        ("unverified", f"coastline: {OVERPASS}; the baseline's: {WORLD_FILE}")
    assert _judge(test, _result(OVERPASS), ["lines: 10 -> 9"], [], cross, world_file=True) == \
        ("DIFFERENT", None)


def _plant_world_file(cache_dir: str):
    """A world file in a cache folder, as coast.world_file finds it (the real cache holds one)."""
    path = os.path.join(cache_dir, "osm", "water-polygons", "2026-10-23", regression.coast.WORLD_SHAPEFILE)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "w").close()
    assert regression.coast.world_file(cache_dir) == path


@pytest.mark.parametrize("stored, found, world, outcome, code", [
    # the code review's cases (review-scratch/check_outcomes.py) and the brief's list, each through main
    (WORLD_FILE, _result(NO_SEA, lines=7), False, "DIFFERENT", 1),  # a coastal entry turned inland
    (NO_SEA, _result(WORLD_FILE, lines=7, sea_km2=0.4), True, "DIFFERENT", 1),  # an inland entry that finds sea
    (WORLD_FILE, _result(REWORDED, lines=9), True, "DIFFERENT", 1),  # the source's text reworded
    (WORLD_FILE, _result(OVERPASS, problems=["lines.arrow has 9 lines, the export 10"]), False, "DIFFERENT", 1),
    (WORLD_FILE, _result(OVERPASS, problems=["the map shows 3 spots, the export has 4"]), False, "DIFFERENT", 1),
    (WORLD_FILE, _result(OVERPASS, lines=9), True, "DIFFERENT", 1),  # the real cache: Overpass only by changed code
    (WORLD_FILE, _result(FALLBACK, lines=9, warned=True), True, "DIFFERENT", 1),  # the real cache: the fallback
    (WORLD_FILE, _result(OVERPASS, lines=9), False, "unverified", 3),  # a scratch cache without the world file
    (WORLD_FILE, _result(FALLBACK, lines=9, warned=True), False, "unverified", 3),
    (WORLD_FILE, _result(FALLBACK, lines=9), False, "DIFFERENT", 1),  # the fallback without its warning
    (OVERPASS, _result(WORLD_FILE, lines=9), True, "DIFFERENT", 1),  # a baseline on Overpass, the real cache
    (OVERPASS, _result(FALLBACK, lines=9, warned=True), False, "unverified", 3),  # Overpass failed this time
    (OVERPASS, _result(FALLBACK, lines=9, warned=True), True, "DIFFERENT", 1),
    (WORLD_FILE, _result(FALLBACK, lines=9, warned="Expecting value: line 1 column 1 (char 0)"), False,
     "DIFFERENT", 1),  # the fallback after our own error (a broken theme tile)
    (FALLBACK, _result(WORLD_FILE, lines=9), True, "DIFFERENT", 1),
    (None, _result(OVERPASS, lines=9), False, "DIFFERENT", 1),
    (WORLD_FILE, _result(OVERPASS), True, "ok", 0),  # no difference: ok on any source
])
def test_outcome_through_main(harness, capsys, stored, found, world, outcome, code):
    if world:
        _plant_world_file(harness.cache)
    harness.write({"R1": _entry({**_expected(coastline=stored), "sea_km2": 0} if stored == NO_SEA else
                                _expected(coastline=stored))})
    harness.results.update(R1=found)
    status, out, _ = harness("R1", capsys=capsys)
    assert (status, out.split("\n", 1)[0].split(" (")[0]) == (code, f"R1: {outcome}"), out


def test_same_as_through_main(harness, capsys):
    """A same_as mismatch is DIFFERENT unless the other test is unverified in the same run (a scratch cache)."""
    tests = {"R1": _entry(_expected()), "R14": _entry({"anchors": 5, "lines": 10}, same_as="R1")}
    harness.write(tests)
    harness.results.update(R1=_result(OVERPASS), R14=_result(OVERPASS, csv_sha256="b" * 64))
    code, out, _ = harness("R1", "R14", capsys=capsys)
    assert code == 1 and "R1: ok" in out and "R14: DIFFERENT" in out
    harness.results.update(R1=_result(OVERPASS, lines=9, csv_sha256="b" * 64),
                           R14=_result(OVERPASS, csv_sha256="c" * 64))
    code, out, _ = harness("R1", "R14", capsys=capsys)
    assert code == 3 and "R1: unverified (coastline: " in out and "R14: unverified (R1 unverified in this run)" in out
    _plant_world_file(harness.cache)  # the real cache: both DIFFERENT
    code, out, _ = harness("R1", "R14", capsys=capsys)
    assert code == 1 and "R1: DIFFERENT" in out and "R14: DIFFERENT" in out
    # without_access_as alike
    harness.write({"R16": _entry(_expected()), "R83": _entry({"anchors": 5}, without_access_as="R16")})
    harness.results.update(R16=_result(OVERPASS), R83=_result(OVERPASS, csv_sha256_without_access="d" * 64))
    code, out, _ = harness("R16", "R83", capsys=capsys)
    assert code == 1 and "R83: DIFFERENT" in out


def test_r17s_coastline_count_is_still_compared():
    """R17's "coastline" is a count of features, a result: compared, never taken for a coastline source."""
    tests = regression.load()
    expected = tests["R17"]["expected"]
    assert isinstance(expected["coastline"], int)
    found = {**expected, "coastline": expected["coastline"] + 1}
    assert regression.value_differences(expected, found) == \
        [f"coastline: {expected['coastline']} -> {expected['coastline'] + 1}"]
    assert _judge(tests["R17"], found, ["x"]) == ("DIFFERENT", None)
    assert regression.value_differences(_expected(), _result("other"), ("coastline",)) == []


def _serve(status: int):
    """A local server answering every request with `status`; returns (server, its base URL)."""
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(status)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"answer")

        do_HEAD = do_GET

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_port}"


@contextlib.contextmanager
def _refusing_port():
    """A local port that refuses every connection while the block runs: bound, never listening, and held, so the
    system gives it to no other process meanwhile. A port only found free was taken by another worker's test server
    between GDAL's tries of a read in a parallel run (2026-11-24: that server's 400 instead of a refusal)."""
    with socket.socket() as holder:
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):  # Windows: no second bind of the port, SO_REUSEADDR or not
            holder.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        holder.bind(("127.0.0.1", 0))
        yield holder.getsockname()[1]


def _download_failed(error: Exception) -> str:
    """The command line's last line for a download that failed with `error`: a reader's RuntimeError as
    search.download_data wraps it ("Download failed: ..."), then findaline.py main's sys.exit(str(e))."""
    import cache
    return f"Download failed: Could not download Test tile 0_0: {cache.clean_error(error)}\n"


def _net_error(url: str) -> Exception:
    from sources import net
    original = net._sleep
    net._sleep = lambda attempt: None
    try:
        net._get(url + "/tile.tif?key=1", retries=1)
    except RuntimeError as e:
        return e
    finally:
        net._sleep = original
    raise AssertionError("no error")


@pytest.mark.parametrize("status", [429, 502, 503, 504])
def test_unanswered_http_status_of_net_get(status):
    server, url = _serve(status)
    try:
        text = _download_failed(_net_error(url))
    finally:
        server.shutdown()
        server.server_close()
    assert text.startswith(f"Download failed: Could not download Test tile 0_0: HTTP {status}")
    assert regression.unanswered(text).startswith("a data provider did not answer: Download failed: ")


@pytest.mark.parametrize("status", [400, 403, 404, 500])
def test_answered_http_status_stays_different(status):
    """A 404 (_get gives None: a file gone), a 4xx and a 500 are answers: DIFFERENT."""
    import cache
    import requests
    server, url = _serve(status)
    try:
        with pytest.raises(requests.HTTPError) as error:
            requests.get(url + "/x", timeout=10).raise_for_status()
        net_error = _net_error(url) if status != 404 else RuntimeError("HTTP 404: answer")
    finally:
        server.shutdown()
        server.server_close()
    assert regression.unanswered(_download_failed(net_error)) is None
    assert regression.unanswered(f"Area: {cache.clean_error(error.value)}\n") is None


def test_unanswered_status_of_raise_for_status():
    """requests' raise_for_status (Nominatim, Overpass): '503 Server Error: ...' under 'Area: '."""
    import cache
    import requests
    server, url = _serve(503)
    try:
        response = requests.get(url + "/search?q=Gozo&format=json", timeout=10)
        try:
            response.raise_for_status()
        except requests.HTTPError as e:
            text = f"Area: {cache.clean_error(e)}\n"
    finally:
        server.shutdown()
        server.server_close()
    assert text.startswith("Area: 503 Server Error")
    assert regression.unanswered(text).startswith("Nominatim or Overpass did not answer: Area: 503 Server Error")


def test_unanswered_connection_refused():
    import requests
    with _refusing_port() as port, pytest.raises(requests.ConnectionError) as error:
        requests.get(f"http://127.0.0.1:{port}/x", timeout=10)
    text = _download_failed(error.value)
    assert regression.unanswered(text), text


def test_unanswered_read_timeout():
    """A server that takes the connection and never answers: requests' 'Read timed out'."""
    import requests
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    try:
        with pytest.raises(requests.Timeout) as error:
            requests.get(f"http://127.0.0.1:{listener.getsockname()[1]}/x", timeout=0.5)
    finally:
        listener.close()
    assert "timed out" in str(error.value)
    assert regression.unanswered(_download_failed(error.value))


def test_unanswered_connection_aborted():
    import requests
    error = requests.ConnectionError("('Connection aborted.', RemoteDisconnected('Remote end closed connection "
                                     "without response'))")
    assert regression.unanswered(_download_failed(error))


@pytest.mark.parametrize("status", [None, 503])
def test_unanswered_gdal_remote_read(status):
    """A GDAL window read (sources/readers/windows.py: 'Could not read <what> <name>: <GDAL's error>') of a host that
    refuses the connection (curl's words) or answers 503."""
    import rasterio
    from sources import net
    with contextlib.ExitStack() as stack:  # the refusing port is held over every try of the read
        server, url = _serve(503) if status else (None, f"http://127.0.0.1:{stack.enter_context(_refusing_port())}")
        try:
            with net._gdal_http(), pytest.raises(rasterio.errors.RasterioIOError) as error:
                rasterio.open(f"/vsicurl/{url}/x.tif")
        finally:
            if server:
                server.shutdown()
                server.server_close()
    text = f"Download failed: Could not read Test block 1_2: {error.value}\n"
    assert regression.unanswered(text), text


@pytest.mark.parametrize("kind", ["no answer", "no answer in time", "the connection broke"])
def test_unanswered_data_server(kind):
    """sources.readers.tilebases: 'the data server at <host> does not answer (<kind>)'."""
    import requests
    from sources.readers import tilebases
    error = RuntimeError("x")
    error.status = None
    error.last = {"no answer": requests.ConnectionError("refused"), "no answer in time": requests.Timeout("slow"),
                  "the connection broke": requests.exceptions.ChunkedEncodingError("cut")}[kind]
    failed = tilebases._server_failed("https://mirror.example/tiles", error)
    assert str(failed).endswith(f"does not answer ({kind})")
    assert regression.unanswered(f"Download failed: Could not download Test tile 0_0: {failed}\n")


@pytest.mark.parametrize("kind, sign", [("timed out", True), ("refused or no route", True), ("name not found", False)])
def test_unanswered_host_not_connected_to(kind, sign):
    """sources.net.Unreachable's own message as a search prints it ("Download failed: <host> could not be connected
    to (<kind>)"): a provider that did not answer, but for a name that was not found (a wrong address in our own code
    looks the same: DIFFERENT). The text comes from net's template, so a reword there keeps this test honest."""
    from sources import net
    assert kind in net.CONNECT_KINDS
    text = f"Download failed: {net.UNREACHABLE_TEXT.format(host='files.example', kind=kind)}\n"
    assert bool(regression.unanswered(text)) is sign, text


def test_unanswered_the_message_of_a_refused_host():
    """The message net.unreachable really makes of a refused connection (both readers raise it through it)."""
    import requests
    from sources import net
    with _refusing_port() as port, pytest.raises(requests.ConnectionError) as error:
        url = f"http://127.0.0.1:{port}/x.tif"
        requests.get(url, timeout=10)
    failed = net.unreachable(url, error.value)
    assert str(failed) == net.UNREACHABLE_TEXT.format(host="127.0.0.1", kind=net.REFUSED)
    assert regression.unanswered(f"Download failed: {failed}\n"), str(failed)


def test_the_day_cap_pattern_is_osms_own_text():
    """The cap's pattern comes from osm's template, any number, and matches nothing else."""
    import osm
    pattern = regression._day_cap_pattern()
    assert regression.re.match(pattern, osm.DAY_MAX_TEXT.format(limit=75) + " (FINDALINE_OVERPASS_DAY_MAX): ...")
    assert not regression.re.match(pattern, "the Overpass queries of today (UTC) are used up")
    assert not regression.re.match(pattern, "Expecting value: line 1 column 1 (char 0)")


@pytest.mark.parametrize("text", [
    "Download failed: Could not download Test tile 0_0: HTTP 404: gone\n",
    "Download failed: Could not download Test tile 0_0: the answer is not a TIFF\n",
    "Download failed: Could not download Test tile 0_0: HTTPSConnectionPool(host='x', port=443): Max retries "
    "exceeded with url: /a (Caused by SSLError(SSLCertVerificationError(1, 'certificate verify failed')))\n",
    "Download failed: Could not download Test tile 0_0: HTTPSConnectionPool(host='x', port=443): Max retries "
    "exceeded with url: /a (Caused by NameResolutionError(\"Failed to resolve 'x' ([Errno 11001] getaddrinfo "
    "failed)\"))\n",
    "Download failed: Could not download Test tile 0_0: x.example is busy with the requests of other searches "
    "(waited 10 min); try again later\n",
    "Area: Overpass is busy with the queries of another search (waited 15 min); try again later\n",
    "Area: the 75 Overpass queries of today (UTC) are used up\n",
    "Not enough steep terrain. Try a lower --slope-threshold or a larger --radius.\n",
    "Traceback (most recent call last):\n  File \"x.py\", line 1\nrequests.exceptions.ReadTimeout: Read timed out.\n",
    "Download failed: HTTP 503: busy\nTraceback (most recent call last):\nKeyError: 'x'\n",
    "Download failed: Could not download T tile 0_0: HTTP 500: upstream timed out\n",  # an answer's own words
    "Download failed: Could not download T tile 0_0: HTTP 400: <p>503 Service Unavailable: connection refused</p>\n",
    "Area: 404 Client Error: Not Found for url: https://nominatim.example/search?... (timed out before)\n",
    # a name that does not resolve, in urllib3 1's words too (which name the failed connection)
    "Download failed: Could not download T tile 0_0: HTTPSConnectionPool(host='x', port=443): Max retries exceeded "
    "with url: /a (Caused by NewConnectionError('<urllib3.connection.HTTPSConnection object at 0x1>: Failed to "
    "establish a new connection: [Errno 11001] getaddrinfo failed'))\n",
    "Download failed: Could not read T block 1_2: CURL error: Could not resolve host: x.example\n",
    # a service that answered with its own error text, saying "timed out" itself
    "Download failed: Could not download T tile 0_0: the service answered an error instead of an image: "
    "Request timed out\n",
    "Download failed: sheet E14A: the index answered no JSON (b'upstream timed out')\n",
    "",
])
def test_not_a_sign_of_no_answer(text):
    """Only a positive sign makes a run unverified: answers, our own queues and caps, a crash, the search's own
    errors, a certificate refused and a name that does not resolve stay DIFFERENT."""
    assert regression.unanswered(text) is None


def test_unanswered_reads_only_its_own_line():
    """Only the search's own error line counts: never a line after it (a thread still logging), nor the rest of a
    server's answer on further lines."""
    text = "[Download] 3 of 4\nDownload failed: Could not download T tile 1_1: HTTP 502: <html>\n<body>bad</body>\n"
    assert regression.unanswered(text) == "a data provider did not answer: Download failed: Could not download T " \
                                          "tile 1_1: HTTP 502: <html>"
    later = ("Download failed: Could not download X tile 1_2: the answer is not a TIFF\n"
             "Retrying (Retry(total=2)) after connection broken by 'ReadTimeoutError(\"Read timed out. "
             "(read timeout=60)\")'\n")
    assert regression.unanswered(later) is None
    assert regression.unanswered("Download failed: Could not download T tile 1_1: HTTP 404: <html>\n"
                                 "<p>upstream timed out</p>\n") is None


def test_unverified_is_reported_apart_and_kept(harness, capsys):
    harness.write({"R1": _entry(_expected()), "R2": _entry(_expected())})
    harness.results.update(R1=_result(FALLBACK, lines=9, warned=True), R2=_result())  # no world file there
    code, out, _ = harness("R1", "R2", capsys=capsys)
    assert code == 3
    assert f"R1: unverified (coastline: {FALLBACK}; the baseline's: {WORLD_FILE})" in out
    assert "\n    lines: 10 -> 9" in out  # the differences listed below it, as for DIFFERENT
    assert "1 ok, 0 different, 1 unverified, 0 skipped; logs in " in out


# H3: exit codes


def test_exit_codes(harness, capsys):
    harness.write({"R1": _entry(_expected()), "R2": _entry(_expected()), "R3": _entry(_expected())})
    harness.results.update(R1=_result(), R2=_result(lines=9), R3=_result(FALLBACK, lines=9, warned=True))
    assert harness("R1", capsys=capsys)[0] == 0
    assert harness("R1", "R2", "R3", capsys=capsys)[0] == 1  # something different wins over unverified
    assert harness("R1", "R3", capsys=capsys)[0] == 3
    harness.write({"R1": _entry(_expected()), "R4": _entry(_expected(), needs_env="FINDALINE_NOT_SET_ANYWHERE")})
    code, out, _ = harness("R1", "R4", capsys=capsys)
    assert code == 0 and "1 ok, 0 different, 0 unverified, 1 skipped; logs removed" in out


# H4: the --update guard


def test_update_stores_nothing_of_an_unverified_entry(harness, capsys):
    harness.write({"R1": _entry(_expected()), "R2": _entry(_expected())})
    harness.results.update(R1=_result(FALLBACK, lines=9, warned=True), R2=_result(lines=11))
    code, out, tests = harness("R1", "R2", "--update", capsys=capsys)
    assert code == 3
    assert f"R1: not stored (coastline: {FALLBACK}; the baseline's: {WORLD_FILE})" in out
    assert tests["R1"]["expected"] == _expected() and tests["R1"]["seconds"] == 1.0
    assert tests["R2"]["expected"]["lines"] == 11 and tests["R2"]["expected"]["coastline"] == WORLD_FILE
    harness.results.update(R1=_result(None, exit_code=1, unanswered="a data provider did not answer: x"))
    code, out, tests = harness("R1", "--update", capsys=capsys)
    assert code == 3 and "R1: not stored (a data provider did not answer: x)" in out


def test_update_never_stores_a_fallback_first_baseline(harness, capsys):
    harness.write({"R1": _entry(_expected(coastline=None)), "R2": _entry(_expected(coastline=None))})
    harness.results.update(R1=_result(FALLBACK, lines=9), R2=_result(WORLD_FILE))
    code, out, tests = harness("R1", "R2", "--update", capsys=capsys)
    assert code == 3
    assert f"R1: not stored (coastline: {FALLBACK}; a baseline is never stored on a fallback)" in out
    assert tests["R1"]["expected"] == _expected(coastline=None)
    assert tests["R2"]["expected"]["coastline"] == WORLD_FILE  # a first coastline stored, no other value moved
    assert {k: v for k, v in tests["R2"]["expected"].items() if k != "coastline"} == _expected(coastline=None)


def test_update_stores_an_entry_asking_for_the_copernicus_mask(harness, capsys):
    harness.write({"R1": _entry(_expected(coastline=None), args="--lat 1 --lon 2 --coastline copernicus")})
    harness.results.update(R1=_result("Copernicus water body mask"))
    code, out, tests = harness("R1", "--update", capsys=capsys)
    assert code == 0 and "not stored" not in out
    assert tests["R1"]["expected"]["coastline"] == "Copernicus water body mask"
    harness.results.update(R1=_result("Copernicus water body mask", lines=12))  # a re-baseline of its own
    code, out, tests = harness("R1", "--update", capsys=capsys)
    assert code == 0 and tests["R1"]["expected"]["lines"] == 12


def test_update_of_an_ok_run_keeps_the_stored_coastline(harness, capsys):
    """An ok run on another source (live Overpass on a scratch cache) never moves the baseline's coastline."""
    harness.write({"R1": _entry(_expected())})
    harness.results.update(R1=_result(OVERPASS))
    code, out, tests = harness("R1", "--update", capsys=capsys)
    assert code == 0 and "R1: ok" in out and tests["R1"]["expected"] == _expected()


def test_update_of_a_different_run_stores_its_coastline(harness, capsys):
    """A DIFFERENT run stored by --update stores the source it printed with its values (a re-baseline on the world
    file); on a cache folder holding the world file, live Overpass's text is refused (only changed code takes it
    there) and so is the fallback."""
    _plant_world_file(harness.cache)
    harness.write({"R1": _entry(_expected()), "R2": _entry(_expected()), "R3": _entry(_expected())})
    harness.results.update(R1=_result(OVERPASS, lines=12), R2=_result(FALLBACK, lines=12, warned=True),
                           R3=_result(WORLD_FILE, lines=12))
    code, out, tests = harness("R1", "R2", "R3", "--update", capsys=capsys)
    assert code == 3 and "R1: DIFFERENT" in out and "R2: DIFFERENT" in out and "R3: DIFFERENT" in out
    assert (f"R1: not stored (coastline: {OVERPASS}; the cache folder holds the world file, which the search did not "
            f"take)") in out
    assert tests["R1"]["expected"] == _expected()
    assert f"R2: not stored (coastline: {FALLBACK}; a baseline is never stored on a fallback)" in out
    assert tests["R2"]["expected"] == _expected()
    assert tests["R3"]["expected"] == _expected(lines=12)


def test_update_of_a_first_baseline_on_overpass_without_the_world_file(harness, capsys):
    """A first baseline taken on a folder without the world file may store live Overpass's text; with the world file
    in the folder it may not."""
    harness.write({"R1": _entry(_expected(coastline=None))})
    harness.results.update(R1=_result(OVERPASS, lines=12))
    code, out, tests = harness("R1", "--update", capsys=capsys)
    assert code == 0 and tests["R1"]["expected"] == _expected(coastline=OVERPASS, lines=12)
    harness.write({"R1": _entry(_expected(coastline=None))})
    _plant_world_file(harness.cache)
    code, out, tests = harness("R1", "--update", capsys=capsys)
    assert code == 3 and "R1: not stored (coastline: " in out and tests["R1"]["expected"] == _expected(coastline=None)


def test_update_of_a_different_entry_exits_as_before(harness, capsys):
    harness.write({"R1": _entry(_expected())})
    harness.results.update(R1=_result(lines=12))
    code, out, tests = harness("R1", "--update", capsys=capsys)
    assert code == 0 and "R1: DIFFERENT" in out and tests["R1"]["expected"]["lines"] == 12


# H5: the cold-cache refusal


def test_an_empty_cache_is_refused_without_cold(harness, tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("FINDALINE_DATA", raising=False)
    harness.write({"R1": _entry(_expected())})
    harness.results.update(R1=_result())
    for folder in (tmp_path / "missing", tmp_path / "empty"):
        if folder.name == "empty":
            folder.mkdir()
        code, out, _ = harness("R1", "--cache", str(folder), capsys=capsys)
        assert code == 2
        assert f"the cache folder {folder} is {folder.name}" in out
        assert f"pass --cache {regression.real_cache_dir()}, or --cold to download" in out
    # with --cold the run goes on (on a cache with data too: harmless)
    code, out, _ = harness("R1", "--cache", str(tmp_path / "missing"), "--cold", "--no-seed", capsys=capsys)
    assert code == 0 and os.path.isfile(tmp_path / "missing" / "LAYOUT")
    code, out, _ = harness("R1", "--cold", "--no-seed", capsys=capsys)
    assert code == 0


def test_a_folder_with_files_but_no_layout_is_a_usage_error(harness, tmp_path, capsys, monkeypatch):
    """--cold or not, a folder holding files but no LAYOUT file ends before anything runs, exit code 2."""
    folder = tmp_path / "stray"
    folder.mkdir()
    (folder / "notes.txt").write_text("x")
    harness.write({"R1": _entry(_expected())})
    monkeypatch.setattr(regression, "run", lambda *args: pytest.fail("a search ran"))
    for argv in (("--cold",), ("--cold", "--no-seed"), ()):
        code, out, _ = harness("R1", "--cache", str(folder), *argv, capsys=capsys)
        assert code == 2 and f"the folder {folder} holds files but no LAYOUT file" in out, argv
        assert not (folder / "LAYOUT").exists() and not (tmp_path / "locks" / regression.RUN_LOG).exists()


def test_an_empty_real_cache_says_so(harness, tmp_path, capsys, monkeypatch):
    """FINDALINE_DATA naming a new folder: the real cache itself is empty; the refusal does not send the user to the
    same folder, and --cold runs, seeding nothing and saying so."""
    monkeypatch.setenv("FINDALINE_DATA", str(tmp_path / "data"))
    real = os.path.join(str(tmp_path / "data"), "cache")
    assert regression.real_cache_dir() == real
    harness.write({"R1": _entry(_expected())})
    harness.results.update(R1=_result())
    code, out, _ = harness("R1", "--cache", real, capsys=capsys)
    assert code == 2 and f"the cache folder {real} is the real cache and it is missing" in out
    assert "--cache" not in out.split("error:", 1)[1]
    code, out, _ = harness("R1", "--cache", real, "--cold", capsys=capsys)
    assert code == 0 and f"Not seeded: {real} is the real cache" in out and "R1: ok" in out
    scratch = str(tmp_path / "scratch" / "cache")  # a scratch cache beside an empty real one
    shutil.rmtree(real)
    code, out, _ = harness("R1", "--cache", scratch, "--cold", capsys=capsys)
    assert code == 0 and f"Not seeded: the real cache {real} is empty (no LAYOUT file)" in out


def test_the_real_cache_named(tmp_path, monkeypatch):
    monkeypatch.delenv("FINDALINE_DATA", raising=False)
    parts = os.path.normpath(REPO).split(os.sep)  # a worktree is <main>/.claude/worktrees/<name>: its main checkout's
    at = next((k for k in range(len(parts) - 1) if parts[k] == ".claude" and parts[k + 1] == "worktrees"), None)
    main = os.sep.join(parts[:at]) if at is not None else REPO
    assert os.path.normcase(regression.real_cache_dir()) == os.path.normcase(os.path.join(main, "cache"))
    monkeypatch.setenv("FINDALINE_DATA", str(tmp_path / "data"))
    assert regression.real_cache_dir() == os.path.join(str(tmp_path / "data"), "cache")


def test_no_refusal_without_a_search(harness, tmp_path, capsys, monkeypatch):
    """--write-doc alone searches nothing; R17 alone reads only its extract (skipped without it, as before)."""
    harness.write({"R1": _entry(_expected()),
                   "R17": {"place": "x", "kind": "osm", "region": "malta", "bbox": [1, 2, 3, 4],
                           "themes": ["coastline"], "sets": ["network"], "expected": {"coastline": 1, "same": True}}})
    code, out, _ = harness("--write-doc", "--cache", str(tmp_path / "missing"), capsys=capsys)
    assert code == 0 and "cache folder" not in out
    code, out, _ = harness("R17", "--cache", str(tmp_path / "missing"), capsys=capsys)
    assert code == 0 and "R17: skipped (the malta extract is not downloaded" in out


# H6: seeding


def _real_cache(root) -> str:
    """A small real cache: the shared data, an entry's own source, the limits' files and locks."""
    import cache
    import osm
    real = _layout(root)
    files = {"osm/water-polygons/2026-01-01/water-polygons-split-4326/water_polygons.shp": b"old",
             "osm/water-polygons/2026-10-23/water-polygons-split-4326/water_polygons.shp": b"shp",
             "osm/water-polygons/2026-10-23/water-polygons-split-4326/water_polygons.dbf": b"dbf",
             "osm/themes/coastline/N35E014.geojson": b"{}",
             "fabdem/v1-2/N50E019.tif": b"fabdem", "copernicus30/2021/dem/N50E019.tif": b"dem",
             "copernicus30/2021/wbm/N50E019.tif": b"wbm", "geoid/egm2008/us_nga_egm08_25.tif": b"geoid",
             "malta/dtm/2018/1_2.tif": b"own source", "osm/overpass-day.sqlite": b"day",
             "osm/nominatim-rate.sqlite": b"rate", "locks/hosts/x.0.lock": b"", "fabdem/v1-2/N51E019.tif.x.part": b"p"}
    for name, data in files.items():
        path = os.path.join(real, *name.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)
    cache.record(real, os.path.join(real, "fabdem", "v1-2", "N50E019.tif"), url="https://x")
    cache.record(real, os.path.join(real, "fabdem", "v1-2", "S10E019.tif"), status="missing")
    cache.record(real, os.path.join(real, "malta", "dtm", "2018", "1_2.tif"))
    cache.record(real, os.path.join(real, "copernicus30", "2021", "dem", "N50E019.tif"))
    db = osm._nominatim_db(real)
    with db:
        db.execute("INSERT INTO reverse VALUES ('1,2', '{}', '2026-11-01')")
        db.execute("INSERT INTO search VALUES ('Gozo', '[]', '2026-11-01')")
    db.close()
    return real


def _rows(cache_dir: str, table: str) -> dict:
    """The Nominatim answers of a table of a cache, closed afterwards (Windows deletes no open database)."""
    db = sqlite3.connect(os.path.join(cache_dir, "osm", "nominatim.sqlite"))
    try:
        return dict(db.execute(f"SELECT query, answer FROM {table}").fetchall())
    finally:
        db.close()


def test_seed_links_the_shared_data(tmp_path, capsys):
    import cache
    real = _real_cache(tmp_path / "real")
    scratch = _layout(tmp_path / "scratch")
    seeded = regression.seed(scratch, real)
    out = capsys.readouterr().out
    assert seeded == ["osm/water-polygons/2026-10-23", "osm/themes", "fabdem/v1-2", "copernicus30/2021/dem",
                      "copernicus30/2021/wbm", "geoid/egm2008", "osm/nominatim.sqlite"]
    assert out == (f"Seeded {scratch} from {real}: osm/water-polygons/2026-10-23 linked (2 files), osm/themes "
                   f"linked (1 files), fabdem/v1-2 linked (1 files), copernicus30/2021/dem linked (1 files), "
                   f"copernicus30/2021/wbm linked (1 files), geoid/egm2008 linked (1 files); osm/nominatim.sqlite "
                   f"(2 rows) and 3 index rows copied\n")
    for name in ("fabdem/v1-2/N50E019.tif", "osm/themes/coastline/N35E014.geojson",
                 "osm/water-polygons/2026-10-23/water-polygons-split-4326/water_polygons.dbf"):
        linked = os.path.join(scratch, *name.split("/"))
        assert os.path.samefile(linked, os.path.join(real, *name.split("/")))  # a hard link
        assert not os.path.islink(linked) and not os.path.isjunction(os.path.dirname(linked))
    for name in ("osm/water-polygons/2026-01-01", "malta", "osm/overpass-day.sqlite", "osm/nominatim-rate.sqlite",
                 "locks", "fabdem/v1-2/N51E019.tif.x.part"):
        assert not os.path.exists(os.path.join(scratch, *name.split("/"))), name
    # copies: the Nominatim answers (no link), the index rows of the seeded folders only ("missing" too)
    assert not os.path.samefile(os.path.join(scratch, "osm", "nominatim.sqlite"),
                                os.path.join(real, "osm", "nominatim.sqlite"))
    assert _rows(scratch, "search") == {"Gozo": "[]"}
    assert cache.info(scratch, os.path.join(scratch, "fabdem", "v1-2", "N50E019.tif"))["url"] == "https://x"
    assert cache.state(scratch, os.path.join(scratch, "fabdem", "v1-2", "S10E019.tif")) == "missing"
    assert not os.path.exists(os.path.join(scratch, "malta"))
    # the search finds the linked files cached; deleting the scratch cache leaves the real files
    assert not cache.due(scratch, os.path.join(scratch, "copernicus30", "2021", "wbm", "N50E019.tif"))
    shutil.rmtree(scratch)
    assert open(os.path.join(real, "fabdem", "v1-2", "N50E019.tif"), "rb").read() == b"fabdem"
    assert os.path.isfile(os.path.join(real, "osm", "nominatim.sqlite"))


def test_seed_again_adds_only_what_is_missing(tmp_path, capsys):
    import osm
    real = _real_cache(tmp_path / "real")
    scratch = _layout(tmp_path / "scratch")
    db = osm._nominatim_db(scratch)
    with db:
        db.execute("INSERT INTO search VALUES ('Gozo', '[\"mine\"]', '2026-11-20')")
        db.execute("INSERT INTO search VALUES ('Comino', '[]', '2026-11-20')")
    db.close()
    os.makedirs(os.path.join(scratch, "fabdem", "v1-2"))
    with open(os.path.join(scratch, "fabdem", "v1-2", "N50E019.tif"), "wb") as f:
        f.write(b"its own")
    regression.seed(scratch, real)
    assert open(os.path.join(scratch, "fabdem", "v1-2", "N50E019.tif"), "rb").read() == b"its own"
    assert _rows(scratch, "search") == {"Gozo": '["mine"]', "Comino": "[]"}
    assert "osm/nominatim.sqlite (3 rows)" in capsys.readouterr().out


def test_seed_nothing_into_the_real_cache_or_a_link_to_it(tmp_path, capsys):
    real = _real_cache(tmp_path / "real")
    assert regression.seed(real, real) == []
    assert capsys.readouterr().out == f"Not seeded: {real} is the real cache\n"
    linked = str(tmp_path / "link")
    regression.link(real, linked)
    try:
        assert regression.seed(linked, real) == []
        assert capsys.readouterr().out == f"Not seeded: {linked} is the real cache\n"
        assert os.listdir(real) == os.listdir(linked)  # nothing added
    finally:
        if os.name == "nt":
            os.rmdir(linked)  # the junction only
        else:
            os.unlink(linked)


def test_seed_leaves_out_an_entrys_own_source(tmp_path, capsys):
    tests = regression.load()
    own = regression.own_world_folders(tests, ["R1", "R11", "R12", "R72", "R16", "R17"])
    assert own == {"fabdem/v1-2": ["R11"], "copernicus30/2021/dem": ["R11"]}  # R11: europe; R12 reads NASADEM
    real = _real_cache(tmp_path / "real")
    scratch = _layout(tmp_path / "scratch")
    seeded = regression.seed(scratch, real, own)
    assert "fabdem/v1-2" not in seeded and "copernicus30/2021/wbm" in seeded
    assert not os.path.exists(os.path.join(scratch, "fabdem", "v1-2"))
    out = capsys.readouterr().out
    assert "Not seeded: fabdem/v1-2 (R11's own source); copernicus30/2021/dem (R11's own source)" in out
    assert "fabdem/v1-2 left out, " in out and "copernicus30/2021/dem left out, " in out
    import cache
    assert cache.info(scratch, os.path.join(scratch, "fabdem", "v1-2", "S10E019.tif")) is None  # its rows neither


def test_seed_on_another_volume_copies_what_is_small(tmp_path, capsys, monkeypatch):
    real = _real_cache(tmp_path / "real")
    scratch = _layout(tmp_path / "scratch")
    monkeypatch.setattr(regression, "_other_volume", lambda a, b: True)
    monkeypatch.setattr(regression, "SEED_COPY_MAX_BYTES", 4)
    seeded = regression.seed(scratch, real)
    out = capsys.readouterr().out
    assert "osm/themes" in seeded and "fabdem/v1-2" not in seeded  # 2 bytes against 6
    assert not os.path.samefile(os.path.join(scratch, "osm", "themes", "coastline", "N35E014.geojson"),
                                os.path.join(real, "osm", "themes", "coastline", "N35E014.geojson"))
    assert "osm/themes copied (1 files)" in out and "osm/water-polygons/2026-10-23 left out" in out
    assert "Not seeded: osm/water-polygons/2026-10-23 (another volume, 0 MB, over 0 MB)" in out


def _failing_link(monkeypatch, word: str):
    """os.link failing for the files whose path holds `word` (too many links of a file, a junction to another
    drive), as Windows refuses it."""
    real_link = os.link

    def link(source, target):
        if word in source:
            raise OSError(1142, "An attempt was made to create more links on a file than the file system supports")
        real_link(source, target)

    monkeypatch.setattr(regression.os, "link", link)


def test_seed_copies_a_folder_whose_link_fails_only_when_small(tmp_path, capsys, monkeypatch):
    real = _real_cache(tmp_path / "real")
    scratch = _layout(tmp_path / "scratch")
    _failing_link(monkeypatch, "fabdem")
    monkeypatch.setattr(regression, "SEED_COPY_MAX_BYTES", 4)  # FABDEM's folder: 7 bytes
    seeded = regression.seed(scratch, real)
    out = capsys.readouterr().out
    assert "fabdem/v1-2" not in seeded
    assert not [f for _, _, names in os.walk(os.path.join(scratch, "fabdem", "v1-2")) for f in names]
    assert "fabdem/v1-2 left out, copernicus30/2021/dem linked (1 files)" in out
    assert "Not seeded: fabdem/v1-2 (a hard link failed: " in out and "7 bytes" not in out
    monkeypatch.setattr(regression, "SEED_COPY_MAX_BYTES", 100)
    seeded = regression.seed(scratch, real)
    out = capsys.readouterr().out
    copied = os.path.join(scratch, "fabdem", "v1-2", "N50E019.tif")
    assert "fabdem/v1-2" in seeded and "fabdem/v1-2 copied (1 files)" in out and "Not seeded" not in out
    assert open(copied, "rb").read() == b"fabdem"
    assert not os.path.samefile(copied, os.path.join(real, "fabdem", "v1-2", "N50E019.tif"))


def test_seed_takes_back_the_links_of_a_folder_left_out(tmp_path, capsys, monkeypatch):
    """A link that fails after others in the same folder: a small folder is linked and copied, a large one left
    out with the links already made taken back (never the real files)."""
    real = _real_cache(tmp_path / "real")
    scratch = _layout(tmp_path / "scratch")
    _failing_link(monkeypatch, "water_polygons.shp")  # the .dbf links first, then the .shp fails (os.walk order)
    monkeypatch.setattr(regression, "SEED_COPY_MAX_BYTES", 1)
    regression.seed(scratch, real)
    out = capsys.readouterr().out
    assert "osm/water-polygons/2026-10-23 left out" in out
    assert not [f for _, _, names in os.walk(os.path.join(scratch, "osm", "water-polygons")) for f in names]
    assert open(os.path.join(real, "osm", "water-polygons", "2026-10-23", "water-polygons-split-4326",
                             "water_polygons.dbf"), "rb").read() == b"dbf"
    monkeypatch.setattr(regression, "SEED_COPY_MAX_BYTES", 100)
    regression.seed(scratch, real)
    out = capsys.readouterr().out
    assert "osm/water-polygons/2026-10-23 linked and copied (2 files)" in out


def test_seed_names_follow_the_code(tmp_path):
    """Each name of SEED_LINKED and SEED_COPIED is a folder or file the catalogue, coast.py, osm.py or
    sources/vertical.py writes into the cache."""
    import coast
    import osm
    from sources import vertical
    from sources.catalogue import world
    known = {layer.folder for source in world.SOURCES for layer in (source.nmt, source.nmpt)
             if layer is not None and hasattr(layer, "folder")}
    known |= {world.WATER_MASK.folder, vertical.EGM2008.folder}
    cache_dir = str(tmp_path)
    shapefile = os.path.join(cache_dir, "osm", "water-polygons", "2026-10-23", coast.WORLD_SHAPEFILE)
    os.makedirs(os.path.dirname(shapefile))
    open(shapefile, "w").close()
    assert coast.world_file(cache_dir) == shapefile
    known.add(regression.cache.relative(cache_dir, os.path.dirname(os.path.dirname(os.path.dirname(shapefile)))))
    known.add(regression.cache.relative(cache_dir, os.path.dirname(os.path.dirname(
        osm.theme_path(cache_dir, "coastline", 35.0, 14.0)))))
    for name in regression.SEED_LINKED:
        assert name in known, name
    osm._nominatim_db(cache_dir).close()
    for name in regression.SEED_COPIED:
        assert os.path.isfile(os.path.join(cache_dir, *name.split("/"))), name


def test_cold_seeds_before_the_first_search(harness, tmp_path, capsys, monkeypatch):
    real = _real_cache(tmp_path / "real")
    monkeypatch.setattr(regression, "real_cache_dir", lambda: real)
    harness.write({"R1": _entry(_expected())})
    seen = {}

    def search(tests, test_id, work, cache_dir, browser):
        seen["layout"] = os.path.isfile(os.path.join(cache_dir, "LAYOUT"))
        seen["linked"] = os.path.isfile(os.path.join(cache_dir, "osm", "themes", "coastline", "N35E014.geojson"))
        return _result()

    monkeypatch.setattr(regression, "run", search)
    scratch = str(tmp_path / "cold" / "cache")
    code, out, _ = harness("R1", "--cache", scratch, "--cold", capsys=capsys)
    assert code == 0 and seen == {"layout": True, "linked": True} and f"Seeded {scratch}" in out
    scratch = str(tmp_path / "bare" / "cache")
    code, out, _ = harness("R1", "--cache", scratch, "--cold", "--no-seed", capsys=capsys)
    assert code == 0 and seen == {"layout": True, "linked": False} and "Seeded" not in out


# H7: the run log


def test_run_log_line(harness, tmp_path, capsys, monkeypatch):
    # A service key in the process (settings.ServiceKeys reads it): an entry needs it, and a provider's error text
    # quoting it reaches a reason; its value is nowhere in the line
    key = "k3y-of-the-test-0123"
    monkeypatch.setenv("OPENTOPOGRAPHY_API_KEY", key)
    monkeypatch.delenv(regression.LOCK_TOKEN_ENV, raising=False)  # not run under the test lock: null
    harness.write({"R1": _entry(_expected(), needs_env="OPENTOPOGRAPHY_API_KEY"), "R2": _entry(_expected()),
                   "R3": _entry(_expected(), needs_env="NOPE"), "R4": _entry(_expected(), sets=["quick"], by_name=True),
                   "R5": _entry(_expected())})
    harness.results.update(R1=_result(), R2=_result(FALLBACK, lines=9, warned=True),
                           R5=_result(None, exit_code=1, unanswered=f"a data provider did not answer: Download failed: "
                                                                    f"HTTP 503 for ?key={key}"))
    code, out, _ = harness("--all", capsys=capsys)
    assert code == 3
    with open(tmp_path / "locks" / regression.RUN_LOG, encoding="utf-8") as f:
        lines = f.read().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert set(record) == {"v", "time", "seconds", "commit", "branch", "worktree", "cache", "cache_real",
                           "real_cache", "cold", "seeded", "args", "entries", "counts", "exit", "lock_token", "hosts"}
    assert record["lock_token"] is None and record["hosts"] == {}  # the stubbed searches counted nothing
    assert record["v"] == 1 and record["exit"] == 3 and record["cache"] == harness.cache
    assert record["time"].endswith("+00:00") and record["worktree"] == os.path.basename(REPO)
    assert record["real_cache"] is False and record["cold"] is False and record["seeded"] == []
    assert record["args"] == {"ids": [], "all": True, "sets": [], "update": False, "browser": False}
    assert record["entries"]["R1"]["outcome"] == "ok" and record["entries"]["R1"]["coastline"] == WORLD_FILE
    assert record["entries"]["R2"] == {"outcome": "unverified", "seconds": record["entries"]["R2"]["seconds"],
                                       "reason": f"coastline: {FALLBACK}; the baseline's: {WORLD_FILE}",
                                       "coastline": FALLBACK}
    assert record["entries"]["R3"]["outcome"] == "skipped" and "R4" not in record["entries"]
    assert record["counts"] == {"ok": 1, "different": 0, "unverified": 2, "skipped": 1, "by_name": 1}
    assert record["entries"]["R5"]["reason"] == "a data provider did not answer: Download failed: HTTP 503 for ?key=***"
    assert key not in lines[0] and os.environ["OPENTOPOGRAPHY_API_KEY"] == key


def test_run_log_never_fails_a_run(tmp_path, monkeypatch, capsys):
    (tmp_path / "locks" / regression.RUN_LOG).mkdir(parents=True)  # a folder where the file would be
    regression.write_run_log({"v": 1})
    assert capsys.readouterr().out.startswith("WARNING: the run log was not written")
    monkeypatch.setattr(regression, "_lock_dir", lambda: None)  # no git: no file, no word
    regression.write_run_log({"v": 1})
    assert capsys.readouterr().out == ""


def test_run_log_lines_are_never_torn(tmp_path):
    def write(k):
        for n in range(20):
            regression.write_run_log({"v": 1, "writer": k, "n": n, "padding": "x" * 5000})

    threads = [threading.Thread(target=write, args=(k,)) for k in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    with open(tmp_path / "locks" / regression.RUN_LOG, encoding="utf-8") as f:
        lines = f.read().splitlines()
    assert len(lines) == 80 and all(json.loads(line)["padding"] == "x" * 5000 for line in lines)


# H8: R17's differences


def test_r17_lists_its_differences_and_keeps_both_trees(harness, tmp_path, capsys, monkeypatch):
    """run_osm with the real readers: the extract's tile built by osmextract.build_tile from a small themes.json,
    Overpass's fetched by osm.fetch_tile from a local stand-in (FINDALINE_OVERPASS_URL); both trees written by the
    code under test stay in the kept log folder."""
    import osm
    cache_dir = harness.cache
    extract = os.path.join(cache_dir, "malta", "osm-extract")
    os.makedirs(extract)
    open(os.path.join(extract, "malta.osm.pbf"), "w").close()
    tile = {"type": "Polygon", "coordinates": [[[13.9, 35.9], [14.4, 35.9], [14.4, 36.4], [13.9, 36.4], [13.9, 35.9]]]}
    with open(os.path.join(extract, "malta.geojson"), "w", encoding="utf-8") as f:
        json.dump(tile, f)  # the outline holds the whole tile: the extract gives all of it

    def line(*points):
        return {"type": "LineString", "coordinates": [list(p) for p in points]}

    ours = {"way/1": line((14.01, 36.01), (14.02, 36.02)), "way/2": line((14.05, 36.05), (14.06, 36.06)),
            "way/3": line((14.1, 36.1), (14.11, 36.11))}
    with open(os.path.join(extract, "malta.themes.json"), "w", encoding="utf-8") as f:
        json.dump({"timestamp": "2026-11-07T00:00:00Z", "themes": {"coastline": [
            {"type": "Feature", "geometry": g, "properties": {"id": k, "tags": {"natural": "coastline"}}}
            for k, g in ours.items()], "cliff": []}}, f)
    os.makedirs(os.path.join(cache_dir, "osm"), exist_ok=True)
    with open(os.path.join(cache_dir, "osm", "geofabrik-index.json"), "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": []}, f)

    def way(number, *points):
        return {"type": "way", "id": number, "tags": {"natural": "coastline"},
                "geometry": [{"lon": lon, "lat": lat} for lon, lat in points]}

    theirs = json.dumps({"elements": [way(2, (14.05, 36.05), (14.06, 36.06)), way(3, (14.1, 36.1), (14.12, 36.11)),
                                      way(4, (14.2, 36.2), (14.21, 36.21))]}).encode()

    class Overpass(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(theirs)

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Overpass)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setenv("FINDALINE_OVERPASS_URL", f"http://127.0.0.1:{server.server_port}/api/interpreter")
    harness.write({"R17": {"place": "x", "kind": "osm", "region": "malta", "bbox": [14.0, 36.0, 14.2, 36.2],
                           "themes": ["coastline"], "sets": ["network"], "expected": {"coastline": 3, "same": True}}})
    try:
        code, out, tests = harness("R17", "--update", capsys=capsys)
    finally:
        server.shutdown()
        server.server_close()
    assert "R17: DIFFERENT" in out and "\n    same: True -> False" in out, out
    assert "\n    coastline: 1 only in the extract, 1 only in Overpass, 1 in both with another geometry" in out
    assert "\n        only in the extract: way/1" in out and "\n        in both with another geometry: way/3" in out
    assert tests["R17"]["expected"] == {"coastline": 3, "same": False}  # the ids are no expected value
    asked = len(list(osm.tiles(14.0, 36.0, 14.2, 36.2)))  # one Overpass query per theme tile (osm.fetch_tile)
    hosts = _log_line(tmp_path)["entries"]["R17"]["hosts"]  # counted in this process; the stand-in's address hidden
    assert hosts == {"ip-address": {"requests": asked, "bytes": hosts["ip-address"]["bytes"], "failed": 0}}
    assert asked >= 1 and hosts["ip-address"]["bytes"] == asked * len(theirs)
    work = out.rsplit("logs in ", 1)[1].strip()
    folder = os.path.join(work, "R17")
    with open(os.path.join(folder, "differences.json"), encoding="utf-8") as f:
        assert json.load(f) == {"coastline": {"only_extract": ["way/1"], "only_overpass": ["way/4"],
                                              "other_geometry": ["way/3"]}}
    for name in ("extract", "overpass"):  # both trees, as the readers wrote them, are there when the run has ended
        path = osm.theme_path(os.path.join(folder, name, "cache"), "coastline", 36.0, 14.0)
        with open(path, encoding="utf-8") as f:
            assert len(json.load(f)["features"]) == 3, name


def test_run_hands_stderr_to_unanswered(tmp_path, monkeypatch):
    """run(): a failed search's stderr goes to unanswered (the search's process replaced by a canned result)."""
    calls = []

    def search(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 1, stdout="Coastline: no sea in the area\n",
                                           stderr="[Download] 1 of 2\nDownload failed: Could not download T tile 0_0: "
                                                  "HTTP 503: busy\n")

    monkeypatch.setattr(regression.subprocess, "run", search)
    monkeypatch.setattr(regression, "link", lambda target, path: os.makedirs(path))  # no junction under basetemp
    tests = {"R1": _entry(_expected())}
    found = regression.run(tests, "R1", str(tmp_path / "work"), str(tmp_path / "cache"), False)
    assert calls and found["exit"] == 1 and found["coastline"] == NO_SEA
    assert found["unanswered"] == ("a data provider did not answer: Download failed: Could not download T tile 0_0: "
                                   "HTTP 503: busy")
    monkeypatch.setattr(regression.subprocess, "run", lambda cmd, **kwargs: subprocess.CompletedProcess(
        cmd, 1, stdout="", stderr="Not enough steep terrain. Try a lower --slope-threshold or a larger --radius.\n"))
    found = regression.run(tests, "R1", str(tmp_path / "work2"), str(tmp_path / "cache"), False)
    assert found["exit"] == 1 and found["unanswered"] is None
    with open(tmp_path / "work2" / "R1" / "output.log", encoding="utf-8") as f:
        assert "Not enough steep terrain" in f.read()


def test_describe_differences_shows_ten_ids_at_most():
    lines = regression.describe_differences({"cliff": {"only_extract": [f"way/{k}" for k in range(12)],
                                                       "only_overpass": [], "other_geometry": []}})
    assert lines[0] == "cliff: 12 only in the extract, 0 only in Overpass, 0 in both with another geometry"
    assert lines[1] == "    only in the extract: " + ", ".join(f"way/{k}" for k in range(10)) + " (+2 more)"


# H9: entries run by name only


def test_entries_run_by_name_only(harness, capsys):
    harness.write({"R1": _entry(_expected()), "R5": _entry(_expected(), sets=["quick", "pl"], by_name=True)})
    harness.results.update(R1=_result(), R5=_result())
    code, out, _ = harness("--all", capsys=capsys)
    assert code == 0 and "R5: not run (by name only)" in out and "R5: ok" not in out
    assert "1 ok, 0 different, 0 unverified, 0 skipped, 1 by name only;" in out
    code, out, _ = harness(capsys=capsys)  # the quick set leaves it out too
    assert "R5" not in out and "R1: ok" in out
    for argv in (("R5",), ("--set", "pl"), ("--all", "R5")):
        code, out, _ = harness(*argv, capsys=capsys)
        assert "R5: ok" in out and "by name only" not in out, argv


def test_no_entry_is_run_by_name_only_yet():
    assert not [t for t, test in regression.load().items() if test.get("by_name")]


# H10: requests and bytes per host, the test lock's token


def _counts(hosts: dict, downloaded=0, cached=0) -> dict:
    return {"hosts": hosts, "tiles": {"downloaded": downloaded, "cached": cached}}


def _log_line(tmp_path) -> dict:
    with open(tmp_path / "locks" / regression.RUN_LOG, encoding="utf-8") as f:
        lines = f.read().splitlines()
    return json.loads(lines[-1])


def test_counts_in_the_run_log(harness, tmp_path, capsys, monkeypatch):
    """Each entry's `hosts` and `tiles` as its search counted them, the run's `hosts` summed (`reads` where any entry
    has it), R17 counted in the harness's process (also when it is skipped after asking), the lock's token; with
    --update nothing of it goes into regression.json."""
    import servicecounts
    monkeypatch.setenv(regression.LOCK_TOKEN_ENV, "0123456789abcdef")
    harness.write({"R1": _entry(_expected()), "R2": _entry(_expected()), "R3": _entry(_expected()),
                   "R17": {"place": "x", "kind": "osm", "region": "malta", "bbox": [14.0, 36.0, 14.2, 36.2],
                           "themes": ["coastline"], "sets": ["quick"], "expected": {"coastline": 3, "same": True}},
                   "R18": {"place": "x", "kind": "osm", "region": "malta", "bbox": [14.0, 36.0, 14.2, 36.2],
                           "themes": ["coastline"], "sets": ["quick"], "expected": {"coastline": 3, "same": True}}})
    harness.results.update(
        R1=_result(service_counts=_counts({"a.example": {"requests": 3, "bytes": 300, "failed": 1}}, 2, 5)),
        R2=_result(lines=9, service_counts=_counts({"a.example": {"requests": 1, "bytes": 0, "failed": 0,
                                                                  "reads": True},
                                                    "b.example": {"requests": 2, "bytes": 20, "failed": 0}})),
        R3=_result(service_counts=None))  # no counts file: no counts for it

    def run_osm(test, work, cache_dir):
        assert servicecounts.enabled()
        servicecounts.record("https://overpass-api.de/api/interpreter?data=x", "ok", 100)
        if test["themes"] == ["coastline"] and work.endswith("R18"):
            servicecounts.record("https://overpass-api.de/api/interpreter?data=x", "timeout")
            return {"skipped": "Overpass did not answer (timed out)"}
        return {"coastline": 3, "same": True}

    monkeypatch.setattr(regression, "run_osm", run_osm)
    code, out, tests = harness("--update", capsys=capsys)
    assert code == 0, out
    record = _log_line(tmp_path)
    entries = record["entries"]
    assert record["v"] == 1 and record["lock_token"] == "0123456789abcdef"
    assert entries["R1"]["hosts"] == {"a.example": {"requests": 3, "bytes": 300, "failed": 1}}
    assert entries["R1"]["tiles"] == {"downloaded": 2, "cached": 5} and entries["R1"]["outcome"] == "ok"
    assert entries["R2"]["hosts"]["a.example"]["reads"] is True and entries["R2"]["outcome"] == "different"
    assert "hosts" not in entries["R3"] and "tiles" not in entries["R3"]
    assert entries["R17"]["hosts"] == {"overpass-api.de": {"requests": 1, "bytes": 100, "failed": 0}}
    assert entries["R17"]["tiles"] == {"downloaded": 0, "cached": 0}
    assert entries["R18"]["outcome"] == "skipped"
    assert entries["R18"]["hosts"] == {"overpass-api.de": {"requests": 2, "bytes": 100, "failed": 1}}
    assert record["hosts"] == {"a.example": {"requests": 4, "bytes": 300, "failed": 1, "reads": True},
                               "b.example": {"requests": 2, "bytes": 20, "failed": 0},
                               "overpass-api.de": {"requests": 3, "bytes": 200, "failed": 1}}
    assert not servicecounts.enabled()
    for test_id, test in tests.items():
        assert not {"service_counts", "hosts", "tiles"} & set(test["expected"]), test_id
    assert tests["R17"]["expected"] == {"coastline": 3, "same": True}


def test_run_names_the_counts_file(tmp_path, monkeypatch):
    """run(): the search gets COUNTS_FILE in its log folder through the variable, and its counts are read from it."""
    seen = {}

    def search(cmd, env=None, **kwargs):
        seen["path"] = env["FINDALINE_SERVICE_COUNTS"]
        with open(seen["path"], "w", encoding="utf-8") as f:
            json.dump(_counts({"services.example": {"requests": 2, "bytes": 2_400_000, "failed": 0}}, 1, 0), f)
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="Not enough steep terrain.\n")

    monkeypatch.setattr(regression.subprocess, "run", search)
    monkeypatch.setattr(regression, "link", lambda target, path: os.makedirs(path))  # no junction under basetemp
    found = regression.run({"R1": _entry(_expected())}, "R1", str(tmp_path / "work"), str(tmp_path / "cache"), False)
    assert seen["path"] == str(tmp_path / "work" / "R1" / regression.COUNTS_FILE)
    assert found["service_counts"] == _counts({"services.example": {"requests": 2, "bytes": 2_400_000, "failed": 0}},
                                              1, 0)


def test_run_adds_the_checks_requests(tmp_path, monkeypatch):
    """run(): what the harness's checks after a search ask in this process (here check_map, standing in for a named
    region's lookup or the profiles' tiles) is added to the search's counts; with no counts file, to none."""
    import servicecounts

    def check_map(runs, found):
        servicecounts.record("https://nominatim.example/search", "ok", 10)
        servicecounts.record("https://services.example/wcs", "timeout")
        return []

    for written in (True, False):
        def search(cmd, env=None, **kwargs):
            if written:
                with open(env["FINDALINE_SERVICE_COUNTS"], "w", encoding="utf-8") as f:
                    json.dump(_counts({"services.example": {"requests": 2, "bytes": 200, "failed": 0}}, 1, 3), f)
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        monkeypatch.setattr(regression.subprocess, "run", search)
        monkeypatch.setattr(regression, "link", lambda target, path: os.makedirs(path))
        monkeypatch.setattr(regression, "measure", lambda output, runs: {"store_problems": []})
        monkeypatch.setattr(regression, "check_map", check_map)
        work = tmp_path / f"work-{written}"
        found = regression.run({"R1": _entry(_expected())}, "R1", str(work), str(tmp_path / "cache"), False)
        nominatim = {"requests": 1, "bytes": 10, "failed": 0}
        if written:
            assert found["service_counts"] == _counts({"services.example": {"requests": 3, "bytes": 200, "failed": 1},
                                                       "nominatim.example": nominatim}, 1, 3)
        else:
            assert found["service_counts"] == _counts({"services.example": {"requests": 1, "bytes": 0, "failed": 1},
                                                       "nominatim.example": nominatim})
        assert found["problems"] == [] and not servicecounts.enabled()


@pytest.mark.parametrize("text", ["", "{", "[]", '{"hosts": []}', '{"hosts": {"a": {"requests": 1}}}',
                                  '{"hosts": {}, "tiles": {"downloaded": "x"}}'])
def test_a_broken_counts_file_is_no_counts(tmp_path, text):
    path = tmp_path / "counts.json"
    path.write_text(text, encoding="utf-8")
    assert regression.read_counts(str(path)) is None
    assert regression.read_counts(str(tmp_path / "missing.json")) is None


def test_read_counts_keeps_host_names_only(tmp_path):
    path = tmp_path / "counts.json"
    path.write_text(json.dumps(_counts({"10.0.0.5": {"requests": 1, "bytes": 2, "failed": 0, "reads": "yes"},
                                        "a.example": {"requests": 1, "bytes": 2, "failed": 0, "extra": 1}})),
                    encoding="utf-8")
    assert regression.read_counts(str(path)) == _counts({"ip-address": {"requests": 1, "bytes": 2, "failed": 0},
                                                         "a.example": {"requests": 1, "bytes": 2, "failed": 0}})


def test_the_lock_token_variable_is_the_locks():
    spec = importlib.util.spec_from_file_location("lock_tool_of_the_test", os.path.join(REPO, "tools", "test_lock.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert regression.LOCK_TOKEN_ENV == module.TOKEN_ENV
