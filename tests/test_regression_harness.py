"""tests/regression.py's harness, offline (no real search: `run` and `run_osm` stubbed, `measure` fed canned output):
the coastline source stored with a baseline (H1), the outcomes ok, unverified and DIFFERENT (H2) and their exit codes
(H3), the --update guard (H4), the refusal of a cache other than the real one without --cold (H5), seeding a scratch
cache from the real one by hard links (H6), the run log (H7), R17's list of differences (H8), entries run by name
only (H9), the requests per host and the test lock's token in the run log (H10), and the data record per entry
(H11: read from canned run.json files in the shape of run.json's "identity" keys, the side file
tests/regression-data.json, the line explaining a difference, the run log's "data", --update and --update-data)."""

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
from types import SimpleNamespace

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
    as stored afterwards). Its cache is the real cache (FINDALINE_DATA on tmp_path): run without --cold."""
    monkeypatch.setenv("FINDALINE_DATA", str(tmp_path))
    cache_dir = _layout(tmp_path / "cache")
    tests_file = tmp_path / "regression.json"
    results = {}

    def write(tests):
        tests_file.write_text(json.dumps(tests), encoding="utf-8")

    monkeypatch.setattr(regression, "TESTS", str(tests_file))
    monkeypatch.setattr(regression, "DATA_FILE", str(tmp_path / "regression-data.json"))  # never the repository's
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
    main.data_file = tmp_path / "regression-data.json"
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


def _not_real_refusal(folder, real) -> str:
    """The refusal of a cache folder other than the real one, without --cold."""
    return (f"the cache folder {folder} is not the real cache: pass --cache {real} to verify a change, or --cold to "
            f"run on this folder (it downloads what the folder lacks, after seeding it from the real cache; add "
            f"--no-seed on a branch that changes the cache's tile encoding, which must not get the real cache's tiles "
            f"by link)")


def _refused(out: str, folder, real) -> bool:
    """Whether the output holds that refusal (whitespace joined: the console may wrap it)."""
    return _not_real_refusal(folder, real) in " ".join(out.split())


def test_an_empty_cache_is_refused_without_cold(harness, tmp_path, capsys, monkeypatch):
    """A missing or empty folder other than the real cache: the new refusal (it replaced "is missing/empty"), its
    three parts; nothing runs, no LAYOUT is written, no run log line. With --cold the run goes on."""
    harness.write({"R1": _entry(_expected())})
    harness.results.update(R1=_result())
    real = regression.real_cache_dir()
    assert regression.same_folder(real, harness.cache)  # the fixture's cache is the real one
    monkeypatch.setattr(regression, "run", lambda *args: pytest.fail("a search ran"))
    for folder in (tmp_path / "missing", tmp_path / "empty"):
        if folder.name == "empty":
            folder.mkdir()
        code, out, _ = harness("R1", "--cache", str(folder), capsys=capsys)
        assert code == 2 and _refused(out, folder, real), out
        text = " ".join(out.split())
        assert f"the cache folder {folder} is not the real cache" in text  # the folder
        assert f"pass --cache {real} to verify a change" in text  # the real cache
        assert "or --cold to run on this folder" in text and "--no-seed" in text  # --cold, seeding, --no-seed
        assert not (folder / "LAYOUT").exists() and not (tmp_path / "locks" / regression.RUN_LOG).exists()
    monkeypatch.setattr(regression, "run", lambda tests, test_id, work, cache, browser: dict(harness.results[test_id]))
    code, out, _ = harness("R1", "--cache", str(tmp_path / "missing"), "--cold", "--no-seed", capsys=capsys)
    assert code == 0 and os.path.isfile(tmp_path / "missing" / "LAYOUT")


def test_a_filled_scratch_cache_needs_cold(harness, tmp_path, capsys, monkeypatch):
    """W3 "b": a cache other than the real one is refused without --cold whatever it holds (a LAYOUT file and
    data); with --cold it runs (seeding what it lacks), and the run log says it was not the real cache."""
    real = _real_cache(tmp_path / "real")
    monkeypatch.setattr(regression, "real_cache_dir", lambda: real)
    harness.write({"R1": _entry(_expected())})
    harness.results.update(R1=_result())
    scratch = _layout(tmp_path / "scratch" / "cache")
    (tmp_path / "scratch" / "cache" / "fabdem").mkdir()
    (tmp_path / "scratch" / "cache" / "fabdem" / "x.tif").write_bytes(b"x")
    code, out, _ = harness("R1", "--cache", scratch, capsys=capsys)
    assert code == 2 and _refused(out, scratch, real), out
    assert not (tmp_path / "locks" / regression.RUN_LOG).exists()
    code, out, _ = harness("R1", "--cache", scratch, "--cold", capsys=capsys)
    assert code == 0 and "R1: ok" in out and f"Seeded {scratch}" in out
    with open(tmp_path / "locks" / regression.RUN_LOG, encoding="utf-8") as f:
        record = json.loads(f.read().splitlines()[-1])
    assert record["real_cache"] is False and record["cold"] is True and record["seeded"]


def test_the_real_cache_and_a_link_to_it_need_no_cold(harness, tmp_path, capsys):
    """The real cache, and a junction (or link) to it, run without --cold; no seeding."""
    harness.write({"R1": _entry(_expected())})
    harness.results.update(R1=_result())
    code, out, _ = harness("R1", "--cache", harness.cache, capsys=capsys)
    assert code == 0 and "R1: ok" in out and "Seeded" not in out
    linked = str(tmp_path / "link")
    regression.link(harness.cache, linked)
    try:
        code, out, _ = harness("R1", "--cache", linked, capsys=capsys)
        assert code == 0 and "R1: ok" in out and "Seeded" not in out
    finally:
        if os.name == "nt":
            os.rmdir(linked)  # the junction only
        else:
            os.unlink(linked)


def test_the_default_cache_other_than_the_real_one_is_refused(harness, tmp_path, capsys, monkeypatch):
    """No --cache: cache/ of FINDALINE_DATA (or of the checkout); when the real cache is elsewhere (a worktree's own
    cache/ against the main checkout's) it is refused without --cold too."""
    data = tmp_path / "worktree"
    _layout(data / "cache")
    monkeypatch.setenv("FINDALINE_DATA", str(data))
    real = str(tmp_path / "cache")  # the fixture's
    monkeypatch.setattr(regression, "real_cache_dir", lambda: real)
    harness.write({"R1": _entry(_expected())})
    harness.results.update(R1=_result())
    monkeypatch.setattr(sys, "argv", ["regression.py", "R1"])  # the fixture would add --cache: main() directly
    with pytest.raises(SystemExit) as ended:
        regression.main()
    out = capsys.readouterr()
    assert ended.value.code == 2 and _refused(out.err, os.path.join(str(data), "cache"), real), out.err


def test_cold_never_seeds_the_main_checkouts_cache(harness, tmp_path, capsys, monkeypatch):
    """A3: FINDALINE_DATA naming another data folder makes that folder's cache the real one; --cold on the main
    checkout's cache would seed it from there: a usage error unless --no-seed (main_cache_dir pointed at a tmp
    folder: no test touches the real one)."""
    real = _real_cache(tmp_path / "data" / "cache")
    monkeypatch.setenv("FINDALINE_DATA", str(tmp_path / "data"))
    main_cache = _layout(tmp_path / "main" / "cache")
    monkeypatch.setattr(regression, "main_cache_dir", lambda: main_cache)
    assert regression.same_folder(regression.real_cache_dir(), real)
    harness.write({"R1": _entry(_expected())})
    harness.results.update(R1=_result())
    code, out, _ = harness("R1", "--cache", main_cache, capsys=capsys)
    assert code == 2 and _refused(out, main_cache, os.path.join(str(tmp_path / "data"), "cache")), out
    code, out, _ = harness("R1", "--cache", main_cache, "--cold", capsys=capsys)
    assert code == 2 and "is the main checkout's cache and the real cache is" in " ".join(out.split())
    assert os.listdir(main_cache) == ["LAYOUT"]  # nothing seeded
    code, out, _ = harness("R1", "--cache", main_cache, "--cold", "--no-seed", capsys=capsys)
    assert code == 0 and "R1: ok" in out and os.listdir(main_cache) == ["LAYOUT"]
    # without FINDALINE_DATA the main checkout's cache is the real one: nothing needed, nothing seeded
    monkeypatch.delenv("FINDALINE_DATA")
    code, out, _ = harness("R1", "--cache", main_cache, "--cold", capsys=capsys)
    assert code == 0 and f"Not seeded: {main_cache} is the real cache" in out


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
        assert f"pass --cache {regression.real_cache_dir()}, or an empty folder with --cold" in out, argv
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


def test_the_main_checkout_found_without_git(tmp_path, monkeypatch):
    """When git gives no answer (not on PATH, a timeout) a linked worktree still names the main checkout's cache,
    from its own .git file and that folder's `commondir`: its own cache/ never counts as the real cache. A main
    checkout (its .git a folder) names its own."""
    monkeypatch.delenv("FINDALINE_DATA", raising=False)
    monkeypatch.setattr(regression, "_git", lambda *args: None)
    main, worktree = tmp_path / "main", tmp_path / "main" / ".claude" / "worktrees" / "w"
    git_dir = main / ".git" / "worktrees" / "w"
    git_dir.mkdir(parents=True)
    (git_dir / "commondir").write_text("../..\n", encoding="utf-8")
    worktree.mkdir(parents=True)
    (worktree / ".git").write_text(f"gitdir: {git_dir.as_posix()}\n", encoding="utf-8")
    monkeypatch.setattr(regression, "REPO", str(worktree))
    assert os.path.normcase(regression.main_cache_dir()) == os.path.normcase(str(main / "cache"))
    assert not regression.same_folder(str(worktree / "cache"), regression.real_cache_dir())
    monkeypatch.setattr(regression, "REPO", str(main))  # the main checkout: .git is a folder
    assert os.path.normcase(regression.main_cache_dir()) == os.path.normcase(str(main / "cache"))
    (worktree / ".git").write_text("not a pointer\n", encoding="utf-8")  # files that say nothing: this checkout's
    monkeypatch.setattr(regression, "REPO", str(worktree))
    assert os.path.normcase(regression.main_cache_dir()) == os.path.normcase(str(worktree / "cache"))


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
    _failing_link(monkeypatch, "water_polygons.shp")  # the .dbf links first, then the .shp fails (names sorted)
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


def test_seed_places_files_in_one_order(tmp_path, monkeypatch):
    """Whatever order the file system lists a folder in (unsorted on Linux), files are placed by name: what a failed
    link leaves placed, and the counts seed prints, never depend on it (the CI's Ubuntu job of 2026-11-24)."""
    source, target = tmp_path / "source", tmp_path / "target"
    for name in ("b/2.tif", "b/1.tif", "a/9.tif"):
        (source / name).parent.mkdir(parents=True, exist_ok=True)
        (source / name).write_bytes(b"x")
    real_walk = os.walk

    def backwards(top):
        for folder, folders, names in real_walk(top):
            folders.sort(reverse=True)
            yield folder, folders, sorted(names, reverse=True)

    monkeypatch.setattr(regression.os, "walk", backwards)
    placed, error = regression._seed_files(str(source), str(target), "copy")
    assert error is None
    assert [os.path.relpath(p, target).replace(os.sep, "/") for p in placed] == ["a/9.tif", "b/1.tif", "b/2.tif"]


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
    assert record["real_cache"] is True and record["cold"] is False and record["seeded"] == []  # the fixture's
    assert record["args"] == {"ids": [], "all": True, "sets": [], "update": False, "browser": False}
    assert record["entries"]["R1"]["outcome"] == "ok" and record["entries"]["R1"]["coastline"] == WORLD_FILE
    assert record["entries"]["R2"] == {"outcome": "unverified", "seconds": record["entries"]["R2"]["seconds"],
                                       "reason": f"coastline: {FALLBACK}; the baseline's: {WORLD_FILE}",
                                       "coastline": FALLBACK, "data": None}
    assert record["entries"]["R3"]["data"] is None and record["entries"]["R1"]["data"] is None  # no record stored
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


def test_r17_is_the_entry_run_by_name_only():
    """R17 compares a dated extract with live Overpass (12 queries a run): out of --all by the user's decision of
    2026-11-24, run by name or with --set network after a change of osm.py or osmextract.py."""
    tests = regression.load()
    assert [t for t, test in tests.items() if test.get("by_name")] == ["R17"]

    def selected(ids=(), sets=(), every=False):
        return regression.select(tests, SimpleNamespace(ids=list(ids), set=list(sets), all=every, write_doc=False,
                                                        update=False))

    ids, by_name = selected(every=True)
    assert "R17" not in ids and by_name == ["R17"] and len(ids) == len(tests) - 1
    assert "R17" not in selected()[0]  # the quick set
    for chosen in (selected(ids=["R17"]), selected(sets=["network"]), selected(ids=["R17"], every=True)):
        assert "R17" in chosen[0] and chosen[1] == []


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


# H11: the data record per entry (wave 4: run.json's "identity" keys, the side file, the explanation)


A, B, C, D = ("a" * 64, "b" * 64, "c" * 64, "d" * 64)
NMT = "poland/nmt"
TILE = "osm/themes/coastline/N50E019.geojson"


def _meta(terrain=None, identity=True, coastline=None, area=None, source="geoportal", gdal="3.10.0",
          access_skipped=None, mixed=False) -> dict:
    """A canned run.json in the shape of contract-wave4.md's table "The record": the terrain's files {name:
    checksum} in NMT, the coastline's identity (a coastline entry when given), the area block, the source; identity
    False: a run.json of before (no "identity" key anywhere)."""
    terrain = {f"{NMT}/a.tif": A, f"{NMT}/b.tif": B} if terrain is None else terrain
    paths = sorted(terrain)
    entry = {"layer": "NMT (digital terrain model)", "folder": NMT, "files": len(paths),
             "fetched": {"oldest": "2026-11-06T17:47:25+00:00", "newest": "2026-11-17T16:34:58+00:00"},
             "paths": paths, "credit": {"data": "NMT / NMPT (GUGiK, Poland)", "url": "https://example.org/licence"}}
    if identity:
        entry["identity"] = {"sha256": [terrain[p] for p in paths]}
    data = [entry]
    if coastline is not None:
        shore = {"layer": WORLD_FILE if "edition" in coastline else OVERPASS, "credit": {"data": "OpenStreetMap"}}
        if identity:
            shore["identity"] = coastline
        data.append(shore)
    meta = {"id": "x", "name": "n", "created": "2026-11-24T10:00:00+00:00", "center": {"lat": 50.1, "lon": 19.7},
            "area": area or {"type": "circle", "lat": 50.1, "lon": 19.7, "radius": 1000.0},
            "source": {"id": source, "name": "geoportal.gov.pl", "description": "GUGiK"}, "data": data,
            "params": {}, "summary": {}}
    if identity:
        meta["identity"] = {"v": 1, "gdal": gdal, "proj": "9.5.0", "rasterio": "1.4.3", **({"mixed": True} if mixed
                                                                                          else {})}
    if access_skipped:
        meta["access_skipped"] = access_skipped
    return meta


def _polygon(spec=None, inputs=None, ring=((14.2, 36.06), (14.27, 36.06), (14.27, 36.085), (14.2, 36.06))) -> dict:
    area = {"type": "polygon", "spec": spec, "geometry": {"type": "Polygon", "coordinates": [[list(p) for p in ring]]}}
    if inputs is not None:
        area["identity"] = inputs
    return area


def _inputs(tile=A, answer=B, query="Fungus Rock") -> dict:
    return {"paths": [TILE], "sha256": [tile], "nominatim": [{"table": "search", "query": query, "sha256": answer}]}


def test_record_of_reads_the_identity():
    record = regression.record_of(_meta(coastline={"edition": "2026-10-23"}, access_skipped="memory"))
    circle = {"lat": 50.1, "lon": 19.7, "radius": 1000.0}
    assert record == {
        "access_skipped": "memory",
        "area": {"type": "circle", "inputs": None, "shape": regression.hashlib.sha256(
            json.dumps(circle, sort_keys=True, separators=(",", ":")).encode()).hexdigest()},
        "coastline": {"edition": "2026-10-23"},
        "folders": {NMT: {"files": {f"{NMT}/a.tif": A, f"{NMT}/b.tif": B}, "layers": ["NMT (digital terrain model)"]}},
        "left_out": [], "mixed": False, "source": "geoportal",
        "versions": {"gdal": "3.10.0", "proj": "9.5.0", "rasterio": "1.4.3"}}
    text = json.dumps(record)
    for never in ("2026-11-06T", "2026-11-24T", "https://", "GUGiK", "credit", "fetched"):  # no time, URL, credit
        assert never not in text, never
    assert regression.record_of(_meta(mixed=True))["mixed"] is True
    tiles = regression.record_of(_meta(coastline={"paths": [TILE], "sha256": [C]}))["coastline"]
    assert tiles == {"tiles": {TILE: C}}


def test_record_of_a_run_json_without_identity():
    """A search of before, or a build without the record: the names, every checksum not known."""
    record = regression.record_of(_meta(identity=False, coastline={"edition": "2026-10-23"}, area=_polygon()))
    assert record["folders"][NMT]["files"] == {f"{NMT}/a.tif": None, f"{NMT}/b.tif": None}
    assert record["versions"] is None and record["mixed"] is False and record["coastline"] == {}
    assert record["area"]["inputs"] is None and record["area"]["shape"] is not None and record["left_out"] == []
    assert regression.record_of(_meta(coastline=None))["coastline"] is None  # no coastline entry at all


def test_record_of_a_checksum_list_of_another_length():
    meta = _meta()
    meta["data"][0]["identity"]["sha256"] = [A]  # two names, one checksum: none of them trusted
    assert regression.record_of(meta)["folders"][NMT]["files"] == {f"{NMT}/a.tif": None, f"{NMT}/b.tif": None}
    meta["data"][0]["identity"]["sha256"] = [A, "B" * 64]  # not as the index stores it (lower case)
    assert regression.record_of(meta)["folders"][NMT]["files"] == {f"{NMT}/a.tif": A, f"{NMT}/b.tif": None}


def test_two_entries_of_one_folder_are_merged():
    """A fallback's terrain and the surface made from it: two entries of one folder, both layers kept."""
    meta = _meta()
    meta["data"].append({**meta["data"][0], "layer": "surface from the terrain", "paths": [f"{NMT}/c.tif"],
                         "identity": {"sha256": [C]}})
    place = regression.record_of(meta)["folders"][NMT]
    assert place == {"files": {f"{NMT}/a.tif": A, f"{NMT}/b.tif": B, f"{NMT}/c.tif": C},
                     "layers": ["NMT (digital terrain model)", "surface from the terrain"]}


@pytest.mark.parametrize("name", ["C:/Users/someone/cache/poland/nmt/a.tif", "/home/someone/cache/a.tif",
                                  "poland\\nmt\\a.tif", "poland/nmt/../../a.tif", "c:a.tif", ""])
def test_record_of_leaves_out_a_name_not_relative_to_the_cache(name):
    """A part with a name that is not relative to the cache is left out whole and named; the name is nowhere."""
    meta = _meta({f"{NMT}/a.tif": A, name: B} if name else {name: B})
    record = regression.record_of(meta)
    assert record["folders"] == {} and record["left_out"] == ["NMT (digital terrain model)"]
    meta = _meta(coastline={"paths": [TILE, name], "sha256": [A, B]}, area=_polygon(inputs={
        "paths": [name], "sha256": [A], "nominatim": []}))
    meta["data"][0]["folder"] = "C:/cache/poland/nmt" if name else NMT
    record = regression.record_of(meta)
    assert record["coastline"] == {} and record["area"]["inputs"] is None
    assert record["left_out"] == sorted(["the coastline", "the search area's inputs"]
                                        + (["NMT (digital terrain model)"] if name else []))
    if name:
        assert name not in json.dumps(record) and "C:/cache" not in json.dumps(record)


def test_the_area_shape_never_holds_its_spec():
    """The outline's digest is the geometry's alone: the same entry with two --area file paths gives one digest."""
    one = regression.record_of(_meta(area=_polygon(spec="C:/Users/someone/area.geojson")))
    two = regression.record_of(_meta(area=_polygon(spec="tests/data/r1_circle.geojson")))
    assert one["area"]["shape"] == two["area"]["shape"] and len(one["area"]["shape"]) == 64
    assert "area.geojson" not in json.dumps(one) and "r1_circle" not in json.dumps(two)
    moved = regression.record_of(_meta(area=_polygon(ring=((14.2, 36.06), (14.28, 36.06), (14.27, 36.085),
                                                           (14.2, 36.06)))))
    assert moved["area"]["shape"] != one["area"]["shape"]
    assert regression.record_of(_meta(area=_polygon(inputs=_inputs())))["area"]["inputs"] == \
        {"tiles": {TILE: A}, "nominatim": {"search": {"Fungus Rock": B}}}
    unnamed = _inputs()
    del unnamed["nominatim"][0]["table"]  # the table may be left unnamed
    assert regression.record_of(_meta(area=_polygon(inputs=unnamed)))["area"]["inputs"]["nominatim"] == \
        {"": {"Fungus Rock": B}}


def test_run_reads_the_record_of_its_run_json(tmp_path, monkeypatch):
    """run(): the record of the run.json the search wrote (record_of), None without one (a failed search)."""
    meta = _meta(coastline={"edition": "2026-10-23"})

    def search(cmd, **kwargs):
        runs = os.path.join(cmd[cmd.index("--data-dir") + 1], "runs", "2026-11-24_x")
        os.makedirs(runs)
        with open(os.path.join(runs, "run.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(regression.subprocess, "run", search)
    monkeypatch.setattr(regression, "link", lambda target, path: os.makedirs(path))
    monkeypatch.setattr(regression, "measure", lambda output, runs: {"store_problems": []})
    monkeypatch.setattr(regression, "check_map", lambda runs, found: [])
    found = regression.run({"R1": _entry(_expected())}, "R1", str(tmp_path / "work"), str(tmp_path / "cache"), False)
    assert found["data_record"] == regression.record_of(meta)
    assert regression.read_record(str(tmp_path / "nothing")) is None


def test_the_record_is_never_a_result(harness, capsys):
    """The record never enters the compared or stored values (R17 stores every key of found)."""
    harness.write({"R1": _entry(_expected())})
    harness.results.update(R1=_result(data_record=regression.record_of(_meta())))
    code, out, tests = harness("R1", "--update", capsys=capsys)
    assert code == 0 and "R1: ok" in out and tests["R1"]["expected"] == _expected()


# H2: the side file


def _record(terrain=None, **more) -> dict:
    return regression.record_of(_meta(terrain, **more))


def test_the_side_file_is_written_whole_and_stably(tmp_path):
    path = str(tmp_path / "regression-data.json")
    tests = {"R1": {}, "R2": {}, "R3": {}}
    data = {"R2": _record(coastline={"paths": [TILE], "sha256": [C]}), "R1": _record(), "R9": _record()}
    regression.write_data(data, tests, path)
    raw = open(path, "rb").read()
    assert raw.endswith(b"}\n") and b"\r" not in raw and raw.decode("utf-8")
    loaded = regression.load_data(path)
    assert list(loaded) == ["R1", "R2"]  # the order of regression.json; R9 is no entry: dropped
    assert loaded["R1"] == data["R1"] and loaded["R2"] == data["R2"]
    for line in raw.decode().splitlines():  # one file name per line
        assert line.count(".tif") + line.count(".geojson") <= 1, line
    for record in loaded.values():  # every mapping sorted (json keeps the file's order)
        assert list(record) == sorted(record) and list(record["area"]) == sorted(record["area"])
        assert list(record["folders"][NMT]["files"]) == sorted(record["folders"][NMT]["files"])
    regression.write_data(loaded, tests, path)
    assert open(path, "rb").read() == raw  # written again with nothing changed: the same bytes
    assert os.listdir(tmp_path) == ["regression-data.json"]  # no temporary file left
    regression.write_data({}, tests, path)
    assert open(path, "rb").read() == b"{}\n"


@pytest.mark.parametrize("text", ["{", "[]", '{"R1": []}', '{"R1": {"folders": {}}}'])
def test_a_broken_side_file_is_a_usage_error(harness, capsys, text):
    harness.write({"R1": _entry(_expected())})
    harness.results.update(R1=_result())
    harness.data_file.write_text(text, encoding="utf-8")
    code, out, _ = harness("R1", capsys=capsys)
    assert code == 2 and f"{harness.data_file} is broken" in out


def test_a_missing_side_file_is_an_empty_one(harness, capsys):
    harness.write({"R1": _entry(_expected())})
    harness.results.update(R1=_result(lines=9, data_record=_record()))
    code, out, _ = harness("R1", capsys=capsys)
    assert code == 1 and "\n    no data record stored" in out
    assert not harness.data_file.exists()  # without --update and --update-data never written


# H3: explaining a difference


def _explained(old: dict, new: dict) -> str:
    return regression.data_line(regression.compare_records(old, new))


def test_data_as_the_baselines():
    assert _explained(_record(), _record()) == "data as the baseline's"
    assert _explained(_record(), _record(identity=False)) == "data as the baseline's (2 files not known)"
    assert _explained(_record(identity=False), _record()) == "data as the baseline's (2 files not known)"


def test_data_differ_per_folder():
    old = _record({f"{NMT}/a.tif": A, f"{NMT}/b.tif": B})
    new = _record({f"{NMT}/a.tif": D, f"{NMT}/c.tif": C})
    assert _explained(old, new) == "data differ: poland/nmt 2 of 2 files, 1 new, 1 replaced under their names"
    # a checksum not known never counts: only the file not read
    assert _explained(old, _record({f"{NMT}/a.tif": A}, identity=False)) == "data differ: poland/nmt 1 of 2 files"
    meta = _meta()
    meta["data"].append({"layer": "Copernicus water body mask", "folder": "copernicus30/2021/wbm",
                         "paths": ["copernicus30/2021/wbm/N49E019.tif"], "identity": {"sha256": [C]}})
    assert _explained(old, regression.record_of(meta)) == "data differ: copernicus30/2021/wbm 0 of 0 files, 1 new"


def test_data_differ_in_every_other_part():
    old = _record(coastline={"edition": "2026-10-23"}, area=_polygon(inputs=_inputs()))
    new = _record(coastline={"edition": "2026-11-30"}, area=_polygon(inputs=_inputs(tile=C, answer=D)),
                  source="europe", gdal="3.11.0", access_skipped="memory", mixed=True)
    assert _explained(old, new) == (
        "data differ: coastline (the world file of 2026-10-23 -> the world file of 2026-11-30); the search area's "
        "inputs (OSM tiles, Nominatim); the source (geoportal -> europe); GDAL 3.10.0 -> 3.11.0; the access mark left "
        "out; sessions read different data")
    tiles = _record(coastline={"paths": [TILE], "sha256": [A]})
    assert _explained(tiles, _record(coastline={"paths": [TILE], "sha256": [B]})) == \
        "data differ: coastline 1 of 1 tiles, 1 replaced under their names"
    assert _explained(old, _record(coastline={"paths": [TILE], "sha256": [B]}, area=_polygon(inputs=_inputs()))) == \
        "data differ: coastline (the world file of 2026-10-23 -> 1 OSM tiles)"
    assert _explained(old, _record(area=_polygon(inputs=_inputs()))) == \
        "data differ: coastline (the world file of 2026-10-23 -> none)"
    assert _explained(_record(access_skipped="memory"), _record()) == \
        "data differ: the access mark left out in the baseline"


def test_the_search_area_itself():
    """The outline's digest is named only when the inputs are equal or not known (then "code or OSM")."""
    moved = ((14.2, 36.06), (14.28, 36.06), (14.27, 36.085), (14.2, 36.06))
    old = _record(area=_polygon(inputs=_inputs()))
    assert _explained(old, _record(area=_polygon(inputs=_inputs(), ring=moved))) == "data differ: the search area"
    assert _explained(old, _record(area=_polygon(ring=moved))) == "data differ: the search area (code or OSM)"
    assert _explained(old, _record(area=_polygon(inputs=_inputs(query="Gozo"), ring=moved))) == \
        "data differ: the search area's inputs (Nominatim)"
    gone = _inputs(answer=None)  # the stored answer's row gone: not known
    assert _explained(old, _record(area=_polygon(inputs=gone))) == "data as the baseline's (1 files not known)"


def test_a_part_left_out_is_not_known():
    meta = _meta({"C:/cache/poland/nmt/a.tif": A, f"{NMT}/b.tif": B})
    assert _explained(_record(), regression.record_of(meta)) == (
        "data as the baseline's; left out of the record (a name not relative to the cache): NMT (digital terrain "
        "model)")


def test_the_line_under_an_entry_through_main(harness, capsys):
    """Under a DIFFERENT or unverified entry with a run.json, one line after its differences; an ok entry, or one
    without a run.json (a failed search), prints nothing more; the outcome, reason and exit code stay."""
    harness.write({"R1": _entry(_expected()), "R2": _entry(_expected()), "R3": _entry(_expected()),
                   "R4": _entry(_expected()), "R5": _entry(_expected())})
    harness.data_file.write_text(json.dumps({t: _record() for t in ("R1", "R2", "R3", "R4")}), encoding="utf-8")
    harness.results.update(
        R1=_result(lines=9, data_record=_record()),
        R2=_result(FALLBACK, lines=9, warned=True, data_record=_record({f"{NMT}/a.tif": A})),
        R3=_result(data_record=_record({f"{NMT}/a.tif": C})),
        R4=_result(None, exit_code=1),
        R5=_result(lines=9, data_record=_record()))
    code, out, _ = harness("R1", "R2", "R3", "R4", "R5", capsys=capsys)
    assert code == 1
    assert "R1: DIFFERENT (" in out and "\n    lines: 10 -> 9\n    data as the baseline's\n" in out
    assert (f"R2: unverified (coastline: {FALLBACK}; the baseline's: {WORLD_FILE}) (" in out
            and "\n    lines: 10 -> 9\n    data differ: poland/nmt 1 of 2 files\n" in out)
    assert "R3: ok (" in out and "R3: ok" + out.split("R3: ok", 1)[1].split("\n", 1)[0] + "\nR4" in out
    assert "\n    exit code 1\nR5" in out  # R4: no run.json, no line
    assert "\n    no data record stored\n" in out  # R5
    record = _log_line(harness.data_file.parent)
    assert {t: e["data"] for t, e in record["entries"].items()} == \
        {"R1": "same", "R2": "differs", "R3": "differs", "R4": None, "R5": None}


def test_run_log_data_unknown(harness, capsys):
    """Nothing comparable (every checksum not known on one side): "unknown", for an ok entry too."""
    harness.write({"R1": _entry(_expected())})
    harness.data_file.write_text(json.dumps({"R1": _record()}), encoding="utf-8")
    harness.results.update(R1=_result(data_record=_record(identity=False)))
    code, out, _ = harness("R1", capsys=capsys)
    assert code == 0 and "data" not in out.split("R1: ok", 1)[1].split("\n\n", 1)[0]
    assert _log_line(harness.data_file.parent)["entries"]["R1"]["data"] == "unknown"


# H5: --update stores the record with the results


def test_update_stores_the_record_with_the_results(harness, capsys):
    harness.write({"R1": _entry(_expected()), "R2": _entry(_expected()), "R3": _entry(_expected()),
                   "R4": _entry(_expected())})
    old = {t: _record(gdal="3.9.0") for t in ("R1", "R2", "R3", "R4")}
    harness.data_file.write_text(json.dumps(old), encoding="utf-8")
    harness.results.update(
        R1=_result(lines=11, data_record=_record()),  # stored: its record too
        R2=_result(lines=11),  # stored without a record (no run.json): the old one removed
        R3=_result(FALLBACK, lines=9, warned=True, data_record=_record()),  # unverified: refused, its record kept
        R4=_result(lines=11, problems=["lines.arrow has 9 lines, the export 11"], data_record=_record()))  # not stored
    code, out, tests = harness("R1", "R2", "R3", "R4", "--update", capsys=capsys)
    assert code == 3 and tests["R1"]["expected"]["lines"] == 11 and "R3: not stored (" in out
    stored = regression.load_data(str(harness.data_file))
    assert stored == {"R1": _record(), "R3": old["R3"], "R4": old["R4"]}
    assert f"Data records updated in {harness.data_file}" in out


# H6: --update-data


def test_update_data_stores_only_the_records(harness, capsys):
    harness.write({"R1": _entry(_expected()), "R2": _entry(_expected()), "R3": _entry(_expected()),
                   "R4": _entry(_expected()), "R5": _entry(_expected(), needs_env="FINDALINE_NOT_SET_ANYWHERE")})
    harness.data_file.write_text(json.dumps({"R2": _record(), "R3": _record(gdal="3.9.0")}), encoding="utf-8")
    harness.results.update(R1=_result(data_record=_record()), R2=_result(data_record=_record()),
                           R3=_result(lines=9, data_record=_record()), R4=_result())  # R4: ok, no run.json
    tests_before = open(regression.TESTS, "rb").read()
    code, out, tests = harness("R1", "R2", "R3", "R4", "R5", "--update-data", capsys=capsys)
    assert code == 1  # the run's own: R3 differs
    assert open(regression.TESTS, "rb").read() == tests_before  # regression.json never written
    assert "R3: not stored (DIFFERENT: a data record is stored for an ok test only)" in out
    assert (f"Data records: 2 stored (1 of them changed), 3 tests left as they were; in {harness.data_file}"
            in out)
    assert regression.load_data(str(harness.data_file)) == \
        {"R1": _record(), "R2": _record(), "R3": _record(gdal="3.9.0")}
    first = harness.data_file.read_bytes()
    code, out, _ = harness("R1", "R2", "R4", "--update-data", capsys=capsys)
    assert code == 0 and "2 stored (0 of them changed), 1 tests left as they were" in out
    assert harness.data_file.read_bytes() == first


def test_update_data_is_refused_with_update_and_off_the_real_cache(harness, tmp_path, capsys, monkeypatch):
    harness.write({"R1": _entry(_expected())})
    harness.results.update(R1=_result(data_record=_record()))
    monkeypatch.setattr(regression, "seed", lambda *args: pytest.fail("seeded"))
    code, out, _ = harness("R1", "--update-data", "--update", capsys=capsys)
    assert code == 2 and "--update-data stores only the data records" in out
    scratch = str(tmp_path / "scratch" / "cache")
    code, out, _ = harness("R1", "--update-data", "--cache", scratch, "--cold", capsys=capsys)
    assert code == 2 and "--update-data stores the data records of runs on the real cache only" in " ".join(out.split())
    assert not harness.data_file.exists() and not os.path.exists(scratch)


# The real side file


def test_the_side_files_entries_are_regression_entries():
    tests = regression.load()
    data = regression.load_data()
    assert set(data) <= set(tests) and list(data) == [t for t in tests if t in data]
    for test_id, record in data.items():
        names = [n for place in record["folders"].values() for n in place["files"]] + list(record["folders"])
        names += list((record["coastline"] or {}).get("tiles", {}))
        names += list((record["area"]["inputs"] or {}).get("tiles", {}))
        assert all(regression.cache_name(n) for n in names), test_id
