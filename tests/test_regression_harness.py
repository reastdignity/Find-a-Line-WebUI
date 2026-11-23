"""tests/regression.py's harness, offline (no real search: `run` and `run_osm` stubbed, `measure` fed canned output):
the coastline source stored with a baseline (H1), the outcomes ok, unverified and DIFFERENT (H2) and their exit codes
(H3), the --update guard (H4), the refusal of an empty cache without --cold (H5), seeding a scratch cache from the
real one by hard links (H6), the run log (H7), R17's list of differences (H8) and entries run by name only (H9)."""

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

WORLD_FILE = "OpenStreetMap water polygons (world file)"
FALLBACK = "Copernicus water body mask (fallback)"


@pytest.fixture(autouse=True)
def _own_run_log(tmp_path, monkeypatch):
    """No test appends to the real run log (the test lock's folder)."""
    monkeypatch.setenv("FINDALINE_TEST_LOCK_DIR", str(tmp_path / "locks"))


def _layout(folder) -> str:
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "LAYOUT"), "w") as f:
        f.write("1\n")
    return str(folder)


def _result(coastline=WORLD_FILE, lines=10, exit_code=0, unanswered=None, **more) -> dict:
    found = {"anchors": 5, "lines": lines, "csv_sha256": "a" * 64, "exit": exit_code, "problems": []}
    if coastline is not None:
        found["coastline"] = coastline
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
        return ended.value.code, out.out + out.err, json.loads(tests_file.read_text(encoding="utf-8"))

    main.write, main.results, main.cache = write, results, cache_dir
    return main


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


def test_stored_keeps_the_searchs_own_text():
    assert regression.stored(_result("anything at all"), {})["coastline"] == "anything at all"
    assert "coastline" not in regression.stored(_result(coastline=None), {"coastline": WORLD_FILE})


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


def test_outcomes():
    test = _entry(_expected())
    assert regression.outcome(test, _result("OpenStreetMap coastline (Overpass or extracts)"), []) == ("ok", None)
    assert regression.outcome(test, _result(FALLBACK), ["lines: 10 -> 9"]) == \
        ("unverified", f"coastline: {FALLBACK}; the baseline's: {WORLD_FILE}")
    assert regression.outcome(test, _result(), ["lines: 10 -> 9"]) == ("DIFFERENT", None)
    assert regression.outcome(_entry(_expected(coastline=None)), _result(FALLBACK), ["x"]) == ("DIFFERENT", None)
    # a search that printed no coastline (it failed before) is not unverified by the coastline
    assert regression.outcome(test, _result(coastline=None), ["x"]) == ("DIFFERENT", None)
    assert regression.outcome(test, _result(None, exit_code=1, unanswered="a data provider did not answer: x"),
                              ["exit code 1"]) == ("unverified", "a data provider did not answer: x")
    assert regression.outcome(test, _result(None, exit_code=1), ["exit code 1"]) == ("DIFFERENT", None)


def test_r17s_coastline_count_is_still_compared():
    """R17's "coastline" is a count of features, a result: compared, never taken for a coastline source."""
    tests = regression.load()
    expected = tests["R17"]["expected"]
    assert isinstance(expected["coastline"], int)
    found = {**expected, "coastline": expected["coastline"] + 1}
    assert regression.compare(expected, found) == [f"coastline: {expected['coastline']} -> {expected['coastline'] + 1}"]
    assert regression.outcome(tests["R17"], found, ["x"]) == ("DIFFERENT", None)
    assert regression.compare(_expected(), _result("other"), ("coastline",)) == []


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


def _closed_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


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
    assert text.startswith("Area: 503 Server Error")
    assert regression.unanswered(text).startswith("Nominatim or Overpass did not answer: Area: 503 Server Error")


def test_unanswered_connection_refused():
    import requests
    with pytest.raises(requests.ConnectionError) as error:
        requests.get(f"http://127.0.0.1:{_closed_port()}/x", timeout=10)
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
    server, url = _serve(503) if status else (None, f"http://127.0.0.1:{_closed_port()}")
    try:
        with net._gdal_http(), pytest.raises(rasterio.errors.RasterioIOError) as error:
            rasterio.open(f"/vsicurl/{url}/x.tif")
    finally:
        if server:
            server.shutdown()
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
    "",
])
def test_not_a_sign_of_no_answer(text):
    """Only a positive sign makes a run unverified: answers, our own queues and caps, a crash, the search's own
    errors, a certificate refused and a name that does not resolve stay DIFFERENT."""
    assert regression.unanswered(text) is None


def test_unanswered_reads_the_whole_message():
    """A server's answer in the message may hold line breaks: the text from the prefix to the end is read."""
    text = "[Download] 3 of 4\nDownload failed: Could not download T tile 1_1: HTTP 502: <html>\n<body>bad</body>\n"
    assert regression.unanswered(text) == "a data provider did not answer: Download failed: Could not download T " \
                                          "tile 1_1: HTTP 502: <html>"


def test_unverified_is_reported_apart_and_kept(harness, capsys):
    harness.write({"R1": _entry(_expected()), "R2": _entry(_expected())})
    harness.results.update(R1=_result(FALLBACK, lines=9), R2=_result())
    code, out, _ = harness("R1", "R2", capsys=capsys)
    assert code == 3
    assert f"R1: unverified (coastline: {FALLBACK}; the baseline's: {WORLD_FILE})" in out
    assert "\n    lines: 10 -> 9" in out  # the differences listed below it, as for DIFFERENT
    assert "1 ok, 0 different, 1 unverified, 0 skipped; logs in " in out


# H3: exit codes


def test_exit_codes(harness, capsys):
    harness.write({"R1": _entry(_expected()), "R2": _entry(_expected()), "R3": _entry(_expected())})
    harness.results.update(R1=_result(), R2=_result(lines=9), R3=_result(FALLBACK, lines=9))
    assert harness("R1", capsys=capsys)[0] == 0
    assert harness("R1", "R2", "R3", capsys=capsys)[0] == 1  # something different wins over unverified
    assert harness("R1", "R3", capsys=capsys)[0] == 3
    harness.write({"R1": _entry(_expected()), "R4": _entry(_expected(), needs_env="FINDALINE_NOT_SET_ANYWHERE")})
    code, out, _ = harness("R1", "R4", capsys=capsys)
    assert code == 0 and "1 ok, 0 different, 0 unverified, 1 skipped; logs removed" in out


# H4: the --update guard


def test_update_stores_nothing_of_an_unverified_entry(harness, capsys):
    harness.write({"R1": _entry(_expected()), "R2": _entry(_expected())})
    harness.results.update(R1=_result(FALLBACK, lines=9), R2=_result(lines=11))
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


def test_the_real_cache_named(tmp_path, monkeypatch):
    monkeypatch.delenv("FINDALINE_DATA", raising=False)
    common = subprocess.run(["git", "rev-parse", "--git-common-dir"], cwd=REPO, capture_output=True, text=True,
                            check=True).stdout.strip()
    main = os.path.dirname(os.path.abspath(os.path.join(REPO, common)))
    assert regression.real_cache_dir() == os.path.join(main, "cache")  # a worktree names the main checkout's
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
    assert out.startswith(f"Seeded {scratch} from {real}: osm/water-polygons/2026-10-23 (2 files), osm/themes "
                          f"(1 files), fabdem/v1-2 (1 files)")
    assert "by hard links; osm/nominatim.sqlite (2 rows), 3 index rows by copy" in out
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
    linked = str(tmp_path / "link")
    regression.link(real, linked)
    try:
        assert regression.seed(linked, real) == [] and capsys.readouterr().out == ""
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
    assert "Not seeded: fabdem/v1-2 (R11's own source); copernicus30/2021/dem (R11's own source)" in \
        capsys.readouterr().out
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
    assert "by copies (another volume)" in out and "Not seeded: osm/water-polygons/2026-10-23 (another volume" in out


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
    monkeypatch.setenv("FINDALINE_FAKE_SECRET", "s3cr3t-value")
    harness.write({"R1": _entry(_expected()), "R2": _entry(_expected()), "R3": _entry(_expected(), needs_env="NOPE"),
                   "R4": _entry(_expected(), sets=["quick"], by_name=True)})
    harness.results.update(R1=_result(), R2=_result(FALLBACK, lines=9))
    code, out, _ = harness("--all", capsys=capsys)
    assert code == 3
    with open(tmp_path / "locks" / regression.RUN_LOG, encoding="utf-8") as f:
        lines = f.read().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert set(record) == {"v", "time", "seconds", "commit", "branch", "worktree", "cache", "cache_real",
                           "real_cache", "cold", "seeded", "args", "entries", "counts", "exit"}
    assert record["v"] == 1 and record["exit"] == 3 and record["cache"] == harness.cache
    assert record["time"].endswith("+00:00") and record["worktree"] == os.path.basename(REPO)
    assert record["real_cache"] is False and record["cold"] is False and record["seeded"] == []
    assert record["args"] == {"ids": [], "all": True, "sets": [], "update": False, "browser": False}
    assert record["entries"]["R1"]["outcome"] == "ok" and record["entries"]["R1"]["coastline"] == WORLD_FILE
    assert record["entries"]["R2"] == {"outcome": "unverified", "seconds": record["entries"]["R2"]["seconds"],
                                       "reason": f"coastline: {FALLBACK}; the baseline's: {WORLD_FILE}",
                                       "coastline": FALLBACK}
    assert record["entries"]["R3"]["outcome"] == "skipped" and "R4" not in record["entries"]
    assert record["counts"] == {"ok": 1, "different": 0, "unverified": 1, "skipped": 1, "by_name": 1}
    assert "s3cr3t-value" not in lines[0]


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
    from shapely.geometry import Point
    import osm
    import osmextract
    cache_dir = harness.cache
    os.makedirs(os.path.join(cache_dir, "malta", "osm-extract"))
    open(os.path.join(cache_dir, "malta", "osm-extract", "malta.osm.pbf"), "w").close()
    os.makedirs(os.path.join(cache_dir, "osm"), exist_ok=True)
    open(os.path.join(cache_dir, "osm", "geofabrik-index.json"), "w").close()
    sides = {"extract": {"way/1": Point(0, 0), "way/2": Point(1, 1), "way/3": Point(2, 2)},
             "overpass": {"way/2": Point(1, 1), "way/3": Point(2, 3), "way/4": Point(4, 4)}}

    def written(folder, theme, lat, lon):
        path = osm.theme_path(folder, theme, lat, lon)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write("{}")
        return True

    side = lambda folder: "extract" if f"{os.sep}extract{os.sep}" in folder else "overpass"  # noqa: E731
    monkeypatch.setattr(osm, "tiles", lambda *box: [(36.0, 14.0)])
    monkeypatch.setattr(osmextract, "build_tile", written)
    monkeypatch.setattr(osm, "fetch_tile", lambda theme, lat, lon, folder: written(folder, theme, lat, lon))
    monkeypatch.setattr(osm, "theme", lambda theme, w, s, e, n, folder: [
        {"id": k, "geometry": g} for k, g in sides[side(folder)].items()])
    harness.write({"R17": {"place": "x", "kind": "osm", "region": "malta", "bbox": [14.15, 35.78, 14.6, 36.1],
                           "themes": ["coastline"], "sets": ["network"], "expected": {"coastline": 3, "same": True}}})
    code, out, tests = harness("R17", "--update", capsys=capsys)
    assert "R17: DIFFERENT" in out and "\n    same: True -> False" in out
    assert "\n    coastline: 1 only in the extract, 1 only in Overpass, 1 in both with another geometry" in out
    assert "\n        only in the extract: way/1" in out and "\n        in both with another geometry: way/3" in out
    assert tests["R17"]["expected"] == {"coastline": 3, "same": False}  # the ids are no expected value
    work = out.rsplit("logs in ", 1)[1].strip()
    folder = os.path.join(work, "R17")
    with open(os.path.join(folder, "differences.json"), encoding="utf-8") as f:
        assert json.load(f) == {"coastline": {"only_extract": ["way/1"], "only_overpass": ["way/4"],
                                              "other_geometry": ["way/3"]}}
    for name in ("extract", "overpass"):  # both trees are still there when the run has ended
        assert os.path.isfile(osm.theme_path(os.path.join(folder, name, "cache"), "coastline", 36.0, 14.0)), name
    if os.path.isjunction(os.path.join(folder, "extract", "cache", "malta")):
        os.rmdir(os.path.join(folder, "extract", "cache", "malta"))
    shutil.rmtree(work)


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
