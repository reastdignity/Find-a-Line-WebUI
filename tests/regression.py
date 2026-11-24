"""Regression tests: run saved searches and compare the results with tests/regression.json.

    python tests/regression.py                 # the quick set (R13)
    python tests/regression.py R1 R7           # chosen tests
    python tests/regression.py R80 --mirror-url http://127.0.0.1:8080   # our own tiles from that data server
    python tests/regression.py --set pl        # a set: quick, pl, search, sources, water, network
    python tests/regression.py --all           # everything (R12 only with OPENTOPOGRAPHY_API_KEY)
    python tests/regression.py R1 --update     # store the new results as expected
    python tests/regression.py --write-doc     # rewrite the table in docs/regression-tests.md
    python tests/regression.py R1 --browser    # also count the spots of the map in a headless browser (the app)
    python tests/regression.py R72 --cache <scratch>/cache --cold   # a scratch cache: downloads (seeded first)

Each test runs with its own temporary data folder (runs, map, work) whose cache/ links
to the real cache (or to --cache, e.g. an empty folder to test downloads). A cache folder that is
missing or holds no LAYOUT file is refused unless --cold (a worktree's own cache/ is empty: pass
--cache <main checkout>/cache); with --cold an empty folder is first seeded from the real cache
(SEED_LINKED by hard link per file, SEED_COPIED and the index rows by copy; --no-seed: truly empty),
so a download test fetches its own source only. The project's data
server is never asked (FINDALINE_MIRROR_URL off) unless --mirror-url names one (a local copy of
the mirror stack): the entries that read our own tiles (needs_path) then run without the local
mirror folder too, which FINDALINE_MIRROR may hold first (clear it to test the server). The output
of every search is in the log folder printed at the end, which is removed when no test
differs, unless --keep.

What is compared (expected values in regression.json):
- the counts of the search: anchors, open anchors, checked pairs, lines, spots, water...;
- the content of the results: the sha256 of the CSV that the export (linestore.export, as a
  download makes it) writes from the run's store, the bytes the runs' lines.csv held before store
  wave 4 (a run keeps no text file since), with readable totals (length, clearances, lines over
  trees) that show what changed when the checksum does;
- the data: the share of the search area with elevation data before any filling, and
  the tiles without data (a lost tile shows here, e.g. the north coast of Gozo);
- "same_as": the CSV export identical to that of another test (tiles against one grid);
- "without_access_as": the CSV export less its columns access1, access2 identical to that of another test (the run
  without --access), with the marks of the line ends counted ("access_ends": hard access, cannot tell, easy access);
- "count_anchors_in": osm:<name> or S,W,N,E: the lines with an anchor in it (lines_in_region),
  e.g. the lines reaching an islet.
Always checked, without expected values: the store (lines.arrow a row per line of the export,
profiles.arrow a row per saved profile: for every line of a circle whose run.json says "profiles":
"all", else for the line shown for each group; the export's seconds are not the test's), and with
"check_profiles" that profiles computed again from the cache
(search.profile_of_line) equal the saved ones. A test more than twice as slow as its
recorded time gets a warning. Tests of kind "osm" compare the theme tiles built from a
Geofabrik extract with those from Overpass (network); when they differ, the feature ids that
differ are printed per theme and written to differences.json in the test's log folder.

Each test's outcome:
- ok: every expected value equal (whatever the coastline source was);
- unverified (reason): differences only for a reason outside the code: the search ended because a
  data provider or an OSM service did not answer (unanswered: NO_ANSWER's signs in its own error
  line only), or the compared values differ on a cache folder without the world file and the
  coastline source (the search's "Coastline:" line, stored as "coastline") explains it
  (coastline_excuse): live Overpass against a baseline of the world file, or the fallback, whose
  warning carries a cause outside the code (warning_cause: Overpass did not answer, or its day
  cap), against a baseline of the world file or of live Overpass; a same_as or without_access_as
  mismatch only when one of the two tests is unverified in this run; never a pass, its
  differences listed as for DIFFERENT;
- DIFFERENT: any other difference (a crash, the search's own errors, the store's, check_profiles'
  and --browser's problems, "no sea in the area" against a source, a reworded source text, a run
  on the world file, and anything where the folder holds the world file, as the real cache does);
- skipped: its needs not met here (needs_env, needs_path), or R17's extract or Overpass missing.
An entry with "by_name": true runs only when named or through --set (--all and the quick set leave it out).
--update stores nothing for an unverified entry, nor a coastline taken from a fallback, nor live Overpass's
where the cache folder holds the world file; an ok run keeps the
stored coastline, a DIFFERENT one stores its own with its values, a first baseline what the search printed.

Exit code: 0 nothing different and nothing unverified (skips allowed); 1 something different (with
--update: 0 as before, the new values are stored); 3 nothing different but something unverified, or
--update refused to store an entry; 2 argparse's usage error (also a cache refused without --cold).

Each run appends one JSON line to regression-runs.jsonl in the test lock's folder
(tools/test_lock.py lock_dir(): commit, cache folder, each entry's outcome and reason; RUN_LOG_VERSION),
with each entry's requests and bytes per host and its tiles (its search counts them into COUNTS_FILE in
its log folder, servicecounts.counted_into, and the checks after it in this process: merged_counts; R17 is
counted in this process), their sum per host, and the
test lock's token of the run that wrapped this one (LOCK_TOKEN_ENV).
"""

import argparse
import contextlib
import csv
import glob
import hashlib
import io
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import sqlite3
import time
import urllib.request
from datetime import datetime, timezone
from typing import Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cache  # noqa: E402
import coast  # noqa: E402  (its source texts, never copied here)
import servicecounts  # noqa: E402  (the searches' requests per host: counted_into, counting)

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS = os.path.join(REPO, "tests", "regression.json")
DOC = os.path.join(REPO, "docs", "regression-tests.md")
TABLE_START, TABLE_END = "<!-- regression-table:start -->", "<!-- regression-table:end -->"
SLOWER = 2.0  # a test this many times slower than its recorded time gets a warning
BROWSERS = [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe", "msedge", "google-chrome", "chromium"]

PATTERNS = {
    "source": (r"^Data: (.+) \([^()]*\) - ", str),  # "Data: <name> (<reason>) - <description>"
    "coverage": (r"Elevation data: ([\d.]+)% of the search area", float),
    "anchors": (r"Found (\d+) potential anchors", int),
    "open": (r"Anchors with an open direction: (\d+)", int),
    "checked": (r"Checked pixel by pixel: (\d+)", int),
    "filled_km2": (r"Filled ([\d.]+) km² of gaps", float),
    "filled_from": (r"Filled [\d.]+ km² of gaps in the data from (.+)$", str),
    "sea_km2": (r"filling sea and lakes.*done.*sea ([\d.]+) km²", float),
}
# Stored by --update when found; the others only when they were expected already (see stored)
ALWAYS = ("anchors", "open", "checked", "lines", "spots", "csv_sha256", "length_km", "clearance_min",
          "clearance_mean", "clearance_max", "over_trees", "coverage", "empty_tiles")
# search.prepare_data's line naming where the sea came from (coast.sea_mask's texts): stored as "coastline" of a
# search entry, never compared as a result (coastline_excuse decides when another source excuses a difference)
COASTLINE = r"^Coastline: (.+)$"
FALLBACK = coast.SOURCE_FALLBACK  # taken because Overpass failed: never stored by --update
# The search's own warning that Overpass failed and the fallback was taken (coast's note, printed by
# findaline.print_event as "WARNING: ..."); the error in its parentheses must be a positive sign (warning_cause)
COAST_WARNING = r"^(?:WARNING: )?" + re.escape(coast.FALLBACK_WARNING) + r" \("
# A search that ended (exit code not 0) because a data provider or an OSM service did not answer. The command line
# prints only the text of search.SearchError (findaline.py main: sys.exit(str(e))), so its codes are read from the
# prefixes their texts start with: download_failed ("Download failed: ", a RuntimeError of a download) and
# area_failed ("Area: ", a named area or a coast area: Nominatim, Overpass); any other ending is DIFFERENT
FAILED_PREFIXES = (("Download failed: ", "a data provider"), ("Area: ", "Nominatim or Overpass"))
# ... and inside that text, a positive sign that the service did not answer (requests', urllib3's, GDAL's curl and
# sources.readers.tilebases' words; one test each in tests/test_regression_harness.py). Not here, so DIFFERENT: a
# 404 or another 4xx, a 500, an answer that is not the data, a refused certificate, a name that does not resolve,
# our own queues ("is busy with the requests of other searches", "busy with the queries of another search") and
# Overpass's day cap of our own (OverpassDayMax). One more sign is made from the code's own template: a download's
# "<host> could not be connected to (timed out | refused or no route)" (_unreachable_pattern)
NO_ANSWER = (
    r"\bHTTP (?:response code: )?(?:429|502|503|504)\b",  # net._get's "HTTP 503: ...", GDAL's curl
    r"\b(?:429|502|503|504) (?:Client|Server) Error\b",  # requests' raise_for_status (Nominatim, Overpass)
    r"(?i)\btimed out\b",  # requests' "Read timed out", urllib3's "Connection to ... timed out", curl's "Timed out"
    r"Failed to establish a new connection|Failed to connect to|Could(?:n't| not) connect to server",
    r"(?i)connection (?:refused|reset|aborted)|RemoteDisconnected|actively refused|forcibly closed",
    r"does not answer \((?:no answer|no answer in time|the connection broke|HTTP (?:429|502|503|504))\)",  # tilebases
)
# A status named in the text (net._get's "HTTP 500: <the server's text>", requests' "500 Server Error"): the first
# decides, so the words of an answered error's page ("upstream timed out" in a 500) never count as no answer
HTTP_STATUS = r"\bHTTP (?:response code: )?(\d{3})\b|\b(\d{3}) (?:Client|Server) Error\b"
NO_ANSWER_STATUSES = (429, 502, 503, 504)
# ... and words that rule a sign out, so DIFFERENT: a name that does not resolve (urllib3 2's NameResolutionError,
# urllib3 1's "Failed to establish a new connection: ... getaddrinfo failed", curl's "Could not resolve host"), and a
# service that answered with its own error text (sources/readers/imageserver.py, sources/layers/inegi.py), which may
# say "timed out" itself
NOT_NO_ANSWER = (
    r"getaddrinfo failed|Failed to resolve|Name or service not known|Could(?:n't| not) resolve host|"
    r"NameResolutionError|nodename nor servname",
    r"answered an error instead of|the index answered",
)
# The shared data a scratch cache gets from the real one with --cold (seed): folders below the cache, by hard link
# per file (never a junction: a recursive delete of the scratch cache then cannot reach the real files). They follow
# the code that writes them (tests/test_regression_harness.py checks each): coast.world_file (the OSM water polygons;
# only the newest <date> folder), osm.theme_path (the theme tiles), sources/catalogue/world.py (FABDEM, Copernicus
# GLO-30 and its water body mask, the gap fillers) and sources/vertical.py (EGM2008). Never an entry's own source
# data (own_world_folders), the Overpass day counter, rate files or locks.
SEED_LINKED = ("osm/water-polygons", "osm/themes", "fabdem/v1-2", "copernicus30/2021/dem", "copernicus30/2021/wbm",
               "geoid/egm2008")
SEED_COPIED = ("osm/nominatim.sqlite",)  # osm._nominatim_db, through SQLite's backup (a WAL is never torn)
SEED_COPY_MAX_BYTES = 200 * 2 ** 20  # another volume (no hard link): a folder up to this size is copied, not larger
SEED_SKIP = re.compile(r"^index\.sqlite(?:-wal|-shm|-journal)?$|\.part$|\.lock$|-rate\.sqlite|overpass-day\.sqlite")
RUN_LOG = "regression-runs.jsonl"  # in tools/test_lock.py lock_dir(): one line per run
RUN_LOG_VERSION = 1  # "v" of each line: a field added later (wave 2's "hosts") needs no new version
COUNTS_FILE = "service-counts.json"  # in an entry's log folder: its search's requests and tiles (read_counts)
LOCK_TOKEN_ENV = "FINDALINE_TEST_LOCK_TOKEN"  # tools/test_lock.py TOKEN_ENV: the queue entry wrapping this run


def load() -> dict:
    with open(TESTS, encoding="utf-8") as f:
        return json.load(f)


def full_args(tests: dict, test_id: str) -> list:
    test = tests[test_id]
    base = full_args(tests, test["extends"]) if "extends" in test else []
    return base + shlex.split(test["args"])


def measure(output: str, run_dir: str) -> dict:
    found = {}
    for key, (pattern, kind) in PATTERNS.items():
        match = re.search(pattern, output, re.M)
        if match:
            found[key] = kind(match.group(1))
    coastlines = list(dict.fromkeys(m.strip() for m in re.findall(COASTLINE, output, re.M)))
    if coastlines:  # one line per search (step 1 of the whole grid); two different ones joined, never chosen
        found["coastline"] = "; ".join(coastlines)
    warning = re.search(COAST_WARNING, output, re.M)
    if warning and warning_cause(_parenthesised(output, warning.end() - 1)):
        found["coast_warning"] = True  # the fallback because Overpass did not answer (or its day cap), not our error
    empty = {}  # per layer, the most tiles without data seen (tiled areas report every tile)
    for layer, n in re.findall(r"^(.+): (\d+) of \d+ tiles without data", output, re.M):
        empty[layer] = max(empty.get(layer, 0), int(n))
    found["empty_tiles"] = sum(empty.values())
    folders = [os.path.dirname(p) for p in glob.glob(os.path.join(run_dir, "*", "run.json"))]
    table = None
    if folders:
        started = time.time()
        table, found["store_problems"] = check_export(folders[0])
        found["store_seconds"] = time.time() - started  # not the search's: left out of its seconds
    if table is not None:
        found["table"] = table  # the export's text, for count_in_region (popped before results are compared)
        found["csv_sha256"] = hashlib.sha256(table).hexdigest()
        rows = list(csv.DictReader(io.StringIO(table.decode("utf-8-sig"), newline="")))
        found["lines"] = len(rows)
        found["spots"] = sum(r["representative"] == "True" for r in rows)
        found["water_lines"] = sum(float(r["water_m"]) > 0 for r in rows)
        found["water_spots"] = sum(float(r["water_m"]) > 0 and r["representative"] == "True" for r in rows)
        clearances = [float(r["clearance_m"]) for r in rows]
        found["length_km"] = round(sum(float(r["length_m"]) for r in rows) / 1000, 3)
        found["clearance_min"] = min(clearances, default=0.0)
        found["clearance_mean"] = round(sum(clearances) / len(clearances), 3) if clearances else 0.0
        found["clearance_max"] = max(clearances, default=0.0)
        found["over_trees"] = sum(r["over_trees_buildings"] == "True" for r in rows)
        if rows and "access1" in rows[0]:  # --access: the marks of the line ends, and lines.csv without them
            ends = [r[f"access{k}"] for r in rows for k in (1, 2)]
            found["access_ends"] = [ends.count(str(state)) for state in (0, 1, 2)]
            found["csv_sha256_without_access"] = hashlib.sha256(without_access(table)).hexdigest()
    return found


def without_access(table: bytes) -> bytes:
    """lines.csv without its columns access1 and access2 (a run made with --access): the bytes of the run
    without the option."""
    rows = table.split(b"\r\n")
    header = rows[0].split(b",")
    drop = {header.index(b"access1"), header.index(b"access2")}
    return b"\r\n".join(b",".join(v for k, v in enumerate(row.split(b",")) if k not in drop) if row else row
                         for row in rows)


def check_export(folder: str) -> tuple:
    """(the CSV that linestore.export makes from the run's store, as the download of an export makes it:
    the text whose sha256 the regression keeps, docs/line-volume/spec-store.md 1.7; problems as text). Until
    store wave 4 every run also wrote its lines.csv, which the export equalled byte for byte on every entry;
    since then the export is the only text. A run without a store: (None, its problem)."""
    import linestore
    if not os.path.isfile(os.path.join(folder, linestore.LINES_FILE)):
        return None, ["the run has no store (lines.arrow)"]
    out = os.path.join(os.path.dirname(folder), "export.csv")  # beside the run folder, never in it
    try:
        with contextlib.redirect_stdout(io.StringIO()):  # the grouping's progress
            linestore.export(folder, "csv", out)
        with open(out, "rb") as f:
            table = f.read()
    finally:
        with contextlib.suppress(OSError):
            os.remove(out)
    return table, []


def count_in_region(table: bytes, where: str, cache_dir: str) -> int:
    """Lines of the CSV export `table` with at least one anchor in a region (area.region: osm:<name> or S,W,N,E)."""
    import area
    from shapely.geometry import Point
    region = area.region(where, cache_dir)
    rows = csv.DictReader(io.StringIO(table.decode("utf-8-sig"), newline=""))
    return sum(any(region.contains(Point(float(r[f"anchor{k}_lon"]), float(r[f"anchor{k}_lat"]))) for k in (1, 2))
               for r in rows)


def check_map(run_dir: str, found: dict) -> list:
    """The store agrees with the CSV export: a row of lines.arrow per line, a row of profiles.arrow per saved profile
    (every line of a circle whose run.json says "profiles": "all", else one per spot): problems as text."""
    import pyarrow as pa
    import linestore
    folders = [os.path.dirname(p) for p in glob.glob(os.path.join(run_dir, "*", "run.json"))]
    if not folders:
        return []
    folder = folders[0]
    with open(os.path.join(folder, "run.json"), encoding="utf-8") as f:
        meta = json.load(f)
    circle = meta["params"].get("radius") is not None
    every = meta["summary"].get("profiles", "all" if circle else "representatives") == "all"
    wanted = found.get("lines") if every else found.get("spots")
    problems, counts = [], {}
    for name in linestore.FILES:  # the store (also without a map): a row per line, a row per saved profile
        with contextlib.suppress(OSError), pa.OSFile(os.path.join(folder, name), "rb") as f:
            counts[name] = pa.ipc.open_file(f).read_all().num_rows
    if counts.get(linestore.LINES_FILE) != found.get("lines"):
        problems.append(f"lines.arrow has {counts.get(linestore.LINES_FILE)} lines, the export {found.get('lines')}")
    if counts.get(linestore.PROFILES_FILE) != wanted:
        problems.append(f"profiles.arrow has {counts.get(linestore.PROFILES_FILE)} profiles, expected {wanted} "
                        f"({'circle' if circle else 'area'}, profiles of {'every line' if every else 'the spots'})")
    return problems


def check_profiles(run_dir: str, work: str, count: int) -> list:
    """Profiles computed again from the cache equal the saved ones (the first `count` lines with a profile, in the
    store's row order, as data.js held them before store wave 4): the store's anchors (int32 of 1e-7 degree: the
    doubles of data.js's 7-decimal text) and profiles, each through the JSON text data.js gave it."""
    import helpers
    import linestore
    import search
    folder = os.path.dirname(glob.glob(os.path.join(run_dir, "*", "run.json"))[0])
    with open(os.path.join(folder, "run.json"), encoding="utf-8") as f:
        meta = json.load(f)
    lines, _ = linestore.read(folder)
    encoder = json.JSONEncoder(separators=(",", ":"))
    problems = []
    for k in sorted(lines.profiles)[:count]:
        saved = json.loads(encoder.encode(helpers.profile_dict(lines.profiles[k])))
        a1, a2 = (tuple(lines.columns[name][k].tolist()) for name in ("anchor1", "anchor2"))
        paths = search.Paths(os.path.dirname(run_dir), os.path.join(work, "profile-work"))
        os.makedirs(paths.work, exist_ok=True)
        with contextlib.redirect_stdout(io.StringIO()):  # the messages of building the grids
            again = search.profile_of_line(meta, paths, a1, a2)
        shutil.rmtree(paths.work, ignore_errors=True)
        if again != saved:
            keys = [key for key in saved if again.get(key) != saved[key]]
            problems.append(f"profile of the line at {a1[0]:.6f}, {a1[1]:.6f} computed again differs in {keys}")
    return problems


def check_browser(run_dir: str, work: str, found: dict) -> list:
    """The spot count of the map in a headless browser equals the export's: the run's map.html through the local
    app over http (findaline.py web on a free port of its own, without a worker, stopped afterwards), as a run
    opens since store wave 4 (from disk a map loads nothing)."""
    browser = next((b for b in BROWSERS if os.path.exists(b) or shutil.which(b)), None)
    if browser is None:
        return ["no headless browser found (Edge or Chrome)"]
    maps = glob.glob(os.path.join(run_dir, "*", "map.html"))
    if not maps:
        return ["the run has no map.html"]
    folder = os.path.dirname(maps[0])
    with open(os.path.join(folder, "zz_check.js"), "w", encoding="utf-8") as f:
        # The viewer loads data.js after the page's load event and builds the model after that: asked until shown
        f.write('var zzTries = 0, zzShow = function() {'
                'var count = document.querySelector(".r-summary-count");'
                'if (!count && ++zzTries < 150) return setTimeout(zzShow, 100);'
                'var p = document.createElement("pre"); p.id = "result";'
                'p.textContent = count ? count.textContent : "";'
                'document.body.appendChild(p); };'
                'window.addEventListener("load", zzShow);')
    with open(os.path.join(folder, "map.html"), encoding="utf-8") as f:
        page = f.read().replace("</body>", '<script src="zz_check.js"></script></body>')
    with open(os.path.join(folder, "zz_check.html"), "w", encoding="utf-8") as f:
        f.write(page)
    import socket
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    app = subprocess.Popen([sys.executable, "findaline.py", "web", "--no-browser", "--no-worker", "--port", str(port),
                            "--data-dir", os.path.dirname(run_dir)], cwd=REPO, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
    try:
        deadline = time.time() + 120
        while True:  # until the app answers (it starts in a few seconds)
            with socket.socket() as s:
                if s.connect_ex(("127.0.0.1", port)) == 0:
                    break
            if time.time() > deadline or app.poll() is not None:
                return ["the app did not start for the browser check"]
            time.sleep(0.2)
        # today's page pinned (tools/today_page.py): its count of spots is the export's grouping
        sys.path.insert(0, os.path.join(REPO, "tools"))
        import today_page
        url = today_page.today(f"http://127.0.0.1:{port}/runs/{os.path.basename(folder)}/zz_check.html")
        result = subprocess.run([shutil.which(browser) or browser, "--headless", "--disable-gpu",
                                 f"--user-data-dir={os.path.join(work, 'browser-profile')}",
                                 "--virtual-time-budget=20000", "--dump-dom", url],
                                capture_output=True, text=True, encoding="utf-8", timeout=300)
    finally:
        app.kill()
        app.wait(30)
    match = re.search(r'id="result">(\d+) spots', result.stdout)
    if not match:
        return ["the map did not show its spots in the browser"]
    if int(match.group(1)) != found.get("spots"):
        return [f"the map shows {match.group(1)} spots, the export has {found.get('spots')}"]
    return []


def link(target: str, link_path: str):
    """A directory link (a junction on Windows: no special rights needed)."""
    if os.name == "nt":
        import _winapi
        _winapi.CreateJunction(os.path.abspath(target), link_path)
    else:
        os.symlink(os.path.abspath(target), link_path)


def run(tests: dict, test_id: str, work: str, cache_dir: str, browser: bool) -> dict:
    out = os.path.join(work, test_id)
    os.makedirs(out, exist_ok=True)
    os.makedirs(cache_dir, exist_ok=True)
    link(cache_dir, os.path.join(out, "cache"))
    # Orthophoto tiles are not compared and can take many minutes to fetch (R9: 15 000 tiles)
    cmd = [sys.executable, "findaline.py", *full_args(tests, test_id), "--no-plot", "--yes", "--ortho", "never",
           "--data-dir", out]
    counts = os.path.join(out, COUNTS_FILE)
    env = {**os.environ, "FINDALINE_PROGRESS": "text", "PYTHONIOENCODING": "utf-8",
           servicecounts.COUNTS_FILE_ENV: counts}
    result = subprocess.run(cmd, cwd=REPO, env=env, capture_output=True, text=True, encoding="utf-8")
    with open(os.path.join(out, "output.log"), "w", encoding="utf-8") as f:
        f.write(result.stdout + result.stderr)
    runs = os.path.join(out, "runs")
    found = measure(result.stdout, runs)
    found["exit"] = result.returncode
    if result.returncode:
        found["unanswered"] = unanswered(result.stderr)
    table = found.pop("table", None)
    checks: dict = {}
    if not result.returncode:
        # The checks run here, in this process (a named region's Nominatim answer, the profiles' tiles): counted too
        with servicecounts.counting() as checks:
            problems = found.pop("store_problems", []) + check_map(runs, found)
            if tests[test_id].get("count_anchors_in"):
                found["lines_in_region"] = count_in_region(table, tests[test_id]["count_anchors_in"], cache_dir)
            if tests[test_id].get("check_profiles"):
                problems += check_profiles(runs, out, tests[test_id]["check_profiles"])
            if browser:
                problems += check_browser(runs, out, found)
        found["problems"] = problems
    found["service_counts"] = merged_counts(read_counts(counts), checks)
    return found


def unanswered(stderr: str) -> Optional[str]:
    """What did not answer, when a search ended because a data provider or an OSM service did not answer: its own
    error line (the last line of stderr starting with one of FAILED_PREFIXES, as findaline.py's
    sys.exit(str(error)) printed it; never a line after it, which a thread still logging may have written, and never
    the rest of a server's answer on further lines) holding one of NO_ANSWER's signs; else None (a crash, the
    search's own error, a failure that cannot be told). Conservative: only a positive sign counts."""
    if "Traceback (most recent call last)" in stderr:
        return None
    lines = stderr.splitlines()
    for k in range(len(lines) - 1, -1, -1):
        who = next((who for prefix, who in FAILED_PREFIXES if lines[k].startswith(prefix)), None)
        if who is not None:
            text = lines[k].strip()
            if no_answer_sign(text):
                return f"{who} did not answer: {text[:200] + ('...' if len(text) > 200 else '')}"
            return None
    return None


def no_answer_sign(text: str) -> bool:
    """Whether an error's text is a positive sign that a service did not answer: the first HTTP status it names is
    one of NO_ANSWER_STATUSES (a 500 whose page says "timed out" is an answer), none of NOT_NO_ANSWER's words, one of
    NO_ANSWER's signs."""
    status = re.search(HTTP_STATUS, text)
    if status and int(status.group(1) or status.group(2)) not in NO_ANSWER_STATUSES:
        return False
    if any(re.search(words, text) for words in NOT_NO_ANSWER):
        return False
    return any(re.search(sign, text) for sign in NO_ANSWER + (_unreachable_pattern(),))


def _parenthesised(text: str, start: int) -> str:
    """The text inside the parentheses that open at text[start] (balanced: an error names its own calls), or "" when
    they never close on that line."""
    depth = 0
    for k in range(start, len(text)):
        if text[k] == "\n":
            return ""
        depth += {"(": 1, ")": -1}.get(text[k], 0)
        if depth == 0:
            return text[start + 1:k]
    return ""


def _from_template(template: str, **fields: str) -> str:
    """The pattern of a text made from a format template of the code (never a copy of its words): each {field}
    replaced by its pattern, the rest literal."""
    pattern = re.escape(template)
    for name, field in fields.items():
        pattern = pattern.replace(re.escape("{" + name + "}"), field)
    return pattern


def _day_cap_pattern() -> str:
    """How osm.OverpassDayMax's text starts, any number of queries (osm.DAY_MAX_TEXT, osm's own template)."""
    import osm
    return _from_template(osm.DAY_MAX_TEXT, limit=r"\d+")


def _unreachable_pattern() -> str:
    """sources.net.Unreachable's message (net.UNREACHABLE_TEXT, net's own template) for a host that could not be
    connected to in time or was refused; a name that was not found is no sign here (a wrong address in our own code
    looks the same: DIFFERENT)."""
    from sources import net  # at the first use, after main has set the data server's variable
    kinds = "|".join(re.escape(kind) for kind in (net.TIMED_OUT, net.REFUSED))
    return _from_template(net.UNREACHABLE_TEXT, host=r"\S+", kind=f"(?:{kinds})")


def warning_cause(error: str) -> bool:
    """Whether the error coast's fallback warning carries is a cause outside the code: a positive sign that Overpass
    did not answer (no_answer_sign), or Overpass's day cap (osm.OverpassDayMax: the search did not ask). Anything
    else (a JSON error of a broken theme tile, another ValueError of our own, nothing) is not."""
    return bool(error) and (no_answer_sign(error) or re.match(_day_cap_pattern(), error) is not None)


def coastline_excuse(stored_source: Optional[str], source: Optional[str], world_file: bool,
                     warned: bool) -> Optional[str]:
    """The reason another coastline source excuses differences in the compared values, or None: only for a cause
    outside the code, and never where the folder holds the world file (world_file: the reference every baseline rests
    on; on the real cache nothing is excused). A run on live Overpass against a baseline of the world file; a run on
    the fallback, whose warning names a cause outside the code (warned), against a baseline of the world file or of
    live Overpass. A run on the world file, "no sea in the area", an unknown or reworded text never."""
    on_overpass = source == coast.SOURCE_OVERPASS and stored_source == coast.SOURCE_WORLD
    on_fallback = (source == coast.SOURCE_FALLBACK and warned
                   and stored_source in (coast.SOURCE_WORLD, coast.SOURCE_OVERPASS))
    if world_file or not (on_overpass or on_fallback):
        return None
    return f"coastline: {source}; the baseline's: {stored_source}"


def outcome(test: dict, found: dict, values: list, problems: list, cross: list, world_file: bool,
            unverified: tuple) -> tuple:
    """("ok" | "unverified" | "DIFFERENT", reason or None) of a test that ran (not skipped). values: the differences
    of the compared values (value_differences); problems: the other own differences (the exit code, the store's,
    check_profiles', --browser's: never excused by the coastline); cross: (difference, the other test) of same_as
    and without_access_as, excused only when this test or the other one is unverified in this run (unverified: the
    ids so far); world_file: whether the cache folder holds the world file after the search."""
    if not (values or problems or cross):
        return "ok", None
    if test.get("kind") == "osm":
        return "DIFFERENT", None
    if found.get("exit"):
        return ("unverified", found["unanswered"]) if found.get("unanswered") else ("DIFFERENT", None)
    if problems:
        return "DIFFERENT", None
    excuse = coastline_excuse(test["expected"].get("coastline"), found.get("coastline"), world_file,
                              bool(found.get("coast_warning"))) if values else None
    if values and not excuse:
        return "DIFFERENT", None
    others = sorted({other for _, other in cross})
    if not excuse and any(other not in unverified for other in others):
        return "DIFFERENT", None
    return "unverified", excuse or f"{', '.join(others)} unverified in this run"


def run_osm(test: dict, work: str, cache_dir: str) -> dict:
    """Theme tiles of a box built from a Geofabrik extract and fetched from Overpass, compared. When they differ,
    found["differences"] holds per theme the feature ids only in the extract, only in Overpass and in both with
    another geometry, also written to differences.json in `work` (the test's log folder, kept with both trees)."""
    import osm
    import osmextract
    import requests
    region, (west, south, east, north) = test["region"], test["bbox"]
    from_extract = os.path.join(work, "extract", "cache")
    from_overpass = os.path.join(work, "overpass", "cache")
    for folder in (from_extract, from_overpass):
        os.makedirs(os.path.join(folder, "osm"), exist_ok=True)
    index = os.path.join(cache_dir, "osm", "geofabrik-index.json")
    country = next((os.path.basename(os.path.dirname(os.path.dirname(p))) for p in
                    glob.glob(os.path.join(cache_dir, "*", "osm-extract", f"{region}.osm.pbf"))), None)
    if country is None or not os.path.exists(index):
        return {"skipped": f"the {region} extract is not downloaded (findaline.py osm download {region})"}
    shutil.copy(index, os.path.join(from_extract, "osm", "geofabrik-index.json"))
    link(os.path.join(cache_dir, country), os.path.join(from_extract, country))
    found, same, differences = {}, True, {}
    for theme in test["themes"]:
        features = {}
        for name, folder in (("extract", from_extract), ("overpass", from_overpass)):
            for lat, lon in osm.tiles(west, south, east, north):
                if name == "extract":
                    if not osmextract.build_tile(folder, theme, lat, lon):
                        return {"skipped": f"the {region} extract does not cover the tile {lat}, {lon}"}
                else:
                    try:
                        osm.fetch_tile(theme, lat, lon, folder)  # no extract here: Overpass
                    except requests.RequestException as e:
                        return {"skipped": f"Overpass did not answer ({e})"}
            features[name] = {f["id"]: f["geometry"] for f in osm.theme(theme, west, south, east, north, folder)}
        found[theme] = len(features["extract"])
        a, b = features["extract"], features["overpass"]
        theirs = {"only_extract": sorted(set(a) - set(b), key=str), "only_overpass": sorted(set(b) - set(a), key=str),
                  "other_geometry": sorted((k for k in set(a) & set(b) if not a[k].equals(b[k])), key=str)}
        if any(theirs.values()):
            differences[theme] = theirs
        same &= set(a) == set(b) and all(a[k].equals(b[k]) for k in a)
    found["same"] = same
    if differences:
        found["differences"] = differences
        with open(os.path.join(work, "differences.json"), "w", encoding="utf-8", newline="\n") as f:
            json.dump(differences, f, ensure_ascii=False, indent=1, default=str)
            f.write("\n")
    return found


def describe_differences(differences: dict, most: int = 10) -> List[str]:
    """R17's differences per theme, as lines: the counts, then up to `most` ids of each kind."""
    words = (("only_extract", "only in the extract"), ("only_overpass", "only in Overpass"),
             ("other_geometry", "in both with another geometry"))
    lines = []
    for theme, theirs in differences.items():
        lines.append(f"{theme}: " + ", ".join(f"{len(theirs[key])} {text}" for key, text in words))
        for key, text in words:
            if theirs[key]:
                more = f" (+{len(theirs[key]) - most} more)" if len(theirs[key]) > most else ""
                lines.append(f"    {text}: {', '.join(map(str, theirs[key][:most]))}{more}")
    return lines


def value_differences(expected: dict, found: dict, ignore: tuple = ()) -> list:
    """The compared values that differ, as 'key: expected -> found'; the keys of `ignore` are not results (a search's
    "coastline")."""
    diffs = []
    for key, value in expected.items():
        if key in ignore:
            continue
        got = found.get(key)
        same = got is not None and (abs(got - value) < 1e-9 if isinstance(value, float) else got == value)
        if not same:
            diffs.append(f"{key}: {value} -> {got}")
    return diffs


def own_problems(found: dict) -> list:
    """A test's differences that no data explain: its exit code and its problems (the store's, check_profiles',
    --browser's)."""
    return ([f"exit code {found['exit']}"] if found.get("exit") else []) + list(found.get("problems", []))


def stored(found: dict, old: dict, ok: bool) -> dict:
    """What --update keeps: the always-present values plus the optional values that matter. The coastline: an ok
    run keeps the stored one (its values equal the baseline's whatever source it ran on); a run that differs, or a
    first baseline, stores the source the search printed (not_storable refuses a fallback first)."""
    keep = {k: found[k] for k in ALWAYS if k in found}
    for key in ("source", "filled_km2", "filled_from"):
        if key in found and (key in old or key != "source"):
            keep[key] = found[key]
    for key in ("sea_km2", "water_lines", "water_spots"):
        if key in old or found.get(key):
            keep[key] = found.get(key, 0)
    if "lines_in_region" in found:
        keep["lines_in_region"] = found["lines_in_region"]
    if "access_ends" in found:
        keep["access_ends"] = found["access_ends"]
    if ok and "coastline" in old:
        keep["coastline"] = old["coastline"]
    elif "coastline" in found:  # the search's own text (none printed: none stored)
        keep["coastline"] = found["coastline"]
    return keep


def not_storable(test: dict, found: dict, status: str, reason: Optional[str], world_file: bool) -> Optional[str]:
    """Why --update must not store this run (None: it may): an unverified run; a search entry whose coastline came
    from a fallback (a first baseline too; an entry asking for another coastline, --coastline copernicus, prints no
    "(fallback)"); or one on live Overpass where the cache folder holds the world file (world_file: only changed
    code takes Overpass there; a first baseline on a folder without it may store Overpass's text)."""
    if status == "unverified":
        return reason
    source = found.get("coastline") if test.get("kind") != "osm" else None
    if source and FALLBACK in source:
        return f"coastline: {source}; a baseline is never stored on a fallback"
    if source and coast.SOURCE_OVERPASS in source and world_file:
        return f"coastline: {source}; the cache folder holds the world file, which the search did not take"
    return None


def number(n) -> str:
    return f"{n:,}".replace(",", " ")


def unmet_needs(test: dict, mirror_url: Optional[str] = None):
    """Why a test cannot run here, or None: its needs_env not set, or a folder of its needs_path (below the folder
    that variable names: our own tiles' mirror, e.g. "madeira/dtm/2m") missing there, as in a mirror with
    Slovakia's tiles only (the VPS) or a process's stale value of the variable. With mirror_url (--mirror-url) an
    entry that names its mirror folders (needs_path) runs: the data server has them."""
    env = test.get("needs_env")
    if mirror_url and test.get("needs_path"):
        return None
    if env and not os.environ.get(env):
        return f"{env} not set"
    missing = [p for p in test.get("needs_path", ())
               if not os.path.isdir(os.path.join(os.environ.get(env, ""), *p.split("/")))]
    return f"{env} has no {', '.join(missing)}" if missing else None


def _git(*args: str) -> Optional[str]:
    """A git command's output in the repository, or None (no git, not a checkout)."""
    try:
        done = subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True, encoding="utf-8", timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout.strip() if done.returncode == 0 else None


def real_cache_dir() -> str:
    """The real cache: FINDALINE_DATA's cache when set, else that of the main checkout (the git common directory's
    folder, found as tools/test_lock.py lock_dir() finds it, so a worktree names the main checkout's), else this
    checkout's."""
    if os.environ.get("FINDALINE_DATA"):
        return os.path.join(cache.data_dir(), "cache")
    common = _git("rev-parse", "--git-common-dir")
    main = os.path.dirname(os.path.abspath(os.path.join(REPO, common))) if common else REPO
    return os.path.join(main, "cache")


def same_folder(a: str, b: str) -> bool:
    """Whether two paths are one folder (a junction or a link to it too)."""
    return os.path.normcase(os.path.realpath(a)) == os.path.normcase(os.path.realpath(b))


def holds_cache(cache_dir: str) -> bool:
    """Whether a folder is a cache (its LAYOUT file: cache.check_layout writes it into a new one)."""
    return os.path.isfile(os.path.join(cache_dir, "LAYOUT"))


def _option(args: List[str], name: str) -> Optional[str]:
    """The value of an option's last occurrence in a test's arguments (the later wins, as in argparse)."""
    values = [args[k + 1] for k in range(len(args) - 1) if args[k] == name]
    return values[-1] if values else None


def own_world_folders(tests: dict, ids: List[str]) -> Dict[str, List[str]]:
    """The folders of SEED_LINKED that are the own source of a test to run, each with those tests (never seeded):
    the layers of the source its --source names, or for --source auto at a point that no source's offline box holds
    (sources.choose: no national source, so `europe`) FABDEM and Copernicus DEM (R11's). Offline: a point outside
    every box is taken for europe even where Nominatim would name a source of its country (then a little more is
    downloaded, never less)."""
    import sources as src
    from sources.choose import OFFLINE_BOXES
    own: Dict[str, List[str]] = {}
    for test_id in ids:
        if tests[test_id].get("kind") == "osm":
            continue
        args = full_args(tests, test_id)
        name = _option(args, "--source") or "auto"
        if name == "auto":
            lat, lon = _option(args, "--lat"), _option(args, "--lon")
            if lat is None or lon is None or any(s <= float(lat) <= n and w <= float(lon) <= e
                                                 for _, (s, n, w, e) in OFFLINE_BOXES):
                continue
            name = "europe"
        source = src.SOURCES.get(name)
        for layer in ((source.nmt, source.nmpt) if source else ()):
            folder = getattr(layer, "folder", None)
            if folder in SEED_LINKED:
                own.setdefault(folder, []).append(test_id)
    return own


def _read_only(path: str) -> sqlite3.Connection:
    """A read-only connection to a database of the real cache (a WAL is read, never written or checkpointed)."""
    return sqlite3.connect("file:" + urllib.request.pathname2url(os.path.abspath(path)) + "?mode=ro", uri=True,
                           timeout=30)


def _newest_water_polygons(real: str) -> Optional[str]:
    """The newest folder of the OSM world water polygons that holds the shapefile (coast.world_file's), relative."""
    import coast
    shapefile = coast.world_file(real)
    if not shapefile:
        return None
    return cache.relative(real, os.path.dirname(os.path.dirname(shapefile)))


def _seed_files(source: str, target: str, how: str) -> tuple:
    """Link (how "link") or copy ("copy") every file below source to the same place below target, where target has
    none yet; skips SEED_SKIP's names and files gone meanwhile. Returns (the paths placed below target, the error
    that stopped it or None): the first link or copy that fails stops it (seed decides what then)."""
    placed = []
    for folder, _, names in os.walk(source):
        for name in names:
            if SEED_SKIP.search(name):
                continue
            path = os.path.join(folder, name)
            out = os.path.join(target, os.path.relpath(path, source))
            if os.path.lexists(out):
                continue
            try:
                os.makedirs(os.path.dirname(out), exist_ok=True)
                if how == "link":
                    os.link(path, out)
                else:
                    shutil.copy2(path, out)
                placed.append(out)
            except FileNotFoundError:  # gone meanwhile (a tile replaced, a .part renamed)
                continue
            except OSError as error:  # too many links of a file, a junction to another drive, a full disk
                return placed, error
    return placed, None


def _unplace(paths: List[str]):
    """Remove files seed placed (links or copies in the scratch cache: never the real files)."""
    for path in paths:
        with contextlib.suppress(OSError):
            os.remove(path)


def _other_volume(a: str, b: str) -> bool:
    """Whether two folders lie on different volumes (no hard link between them)."""
    return os.stat(a).st_dev != os.stat(b).st_dev


def _folder_bytes(folder: str) -> int:
    total = 0
    for root, _, names in os.walk(folder):
        for name in names:
            with contextlib.suppress(OSError):
                total += os.path.getsize(os.path.join(root, name))
    return total


def _copy_rows(real: str, cache_dir: str, folders: List[str]) -> int:
    """The index rows (cache.py: a file's status, times, sha256; "missing" for a tile a service has no data for) of
    the seeded folders, from the real cache's index.sqlite of each top-level folder into the scratch cache's (rows
    it has already stay): one consistent read each. Returns the rows added."""
    added = 0
    by_top: Dict[str, List[str]] = {}
    for folder in folders:
        top, _, inner = folder.partition("/")
        by_top.setdefault(top, []).append(inner + "/")
    for top, prefixes in by_top.items():
        index = os.path.join(real, top, "index.sqlite")
        if not os.path.isfile(index):
            continue
        source = _read_only(index)
        try:
            rows = [row for row in source.execute("SELECT * FROM files")
                    if any(row[0].startswith(prefix) for prefix in prefixes)]
        finally:
            source.close()
        target = cache._connect(cache_dir, top)
        try:
            with target:
                before = target.total_changes
                target.executemany("INSERT OR IGNORE INTO files VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows)
                added += target.total_changes - before
        finally:
            target.close()
    return added


def _copy_database(path: str, out: str) -> int:
    """A SQLite database of the real cache copied whole through SQLite's backup (out new), or its rows added to
    out's tables of the same names (out there already; rows it has stay). Returns the rows in out afterwards."""
    source = _read_only(path)
    try:
        os.makedirs(os.path.dirname(out), exist_ok=True)
        fresh = not os.path.exists(out)
        target = sqlite3.connect(out, timeout=30)
        try:
            tables = [t for (t,) in source.execute("SELECT name FROM sqlite_master WHERE type = 'table'")]
            if fresh:
                source.backup(target)
            else:
                theirs = {t for (t,) in target.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
                with target:
                    for table in tables:
                        if table in theirs:
                            rows = source.execute(f'SELECT * FROM "{table}"').fetchall()
                            if rows:
                                marks = ",".join("?" * len(rows[0]))
                                target.executemany(f'INSERT OR IGNORE INTO "{table}" VALUES ({marks})', rows)
            return sum(target.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for t in tables
                       if target.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                                         (t,)).fetchone())
        finally:
            target.close()
    finally:
        source.close()


def seed(cache_dir: str, real: str, own: Optional[Dict[str, List[str]]] = None) -> List[str]:
    """Seed a scratch cache from the real one (--cold): SEED_LINKED by hard link per file, SEED_COPIED through
    SQLite's backup and the seeded folders' index rows by copy, never what is there already. Where a hard link
    cannot be made (another volume, or a link that fails) a folder is copied only when the whole folder is at most
    SEED_COPY_MAX_BYTES, else left out; `own` (folder -> tests): folders left out as a test's own source. Prints for
    each name whether it was linked, copied or left out, and a line naming what was not seeded and why; returns the
    names seeded."""
    if same_folder(cache_dir, real):
        print(f"Not seeded: {cache_dir} is the real cache", flush=True)
        return []
    if not holds_cache(real):
        print(f"Not seeded: the real cache {real} is empty (no LAYOUT file)", flush=True)
        return []
    own = own or {}
    other_volume = _other_volume(real, cache_dir)
    cap = f"over {SEED_COPY_MAX_BYTES / 2 ** 20:.0f} MB"
    seeded, left, said, folders = [], [], [], []
    for name in SEED_LINKED:
        if name in own:
            left.append(f"{name} ({', '.join(own[name])}'s own source)")
            said.append(f"{name} left out")
            continue
        folder = _newest_water_polygons(real) if name == "osm/water-polygons" else name
        source = os.path.join(real, *folder.split("/")) if folder else None
        if not source or not os.path.isdir(source):
            continue  # not in the real cache either
        target = os.path.join(cache_dir, *folder.split("/"))
        if other_volume:
            size = _folder_bytes(source)
            if size > SEED_COPY_MAX_BYTES:
                left.append(f"{folder} (another volume, {size / 2 ** 20:.0f} MB, {cap})")
                said.append(f"{folder} left out")
                continue
            placed, error = _seed_files(source, target, "copy")
            how = "copied"
        else:
            placed, error = _seed_files(source, target, "link")
            how = "linked"
            if error is not None:  # a hard link failed: the whole folder copied only when small
                size = _folder_bytes(source)
                if size > SEED_COPY_MAX_BYTES:
                    _unplace(placed)
                    left.append(f"{folder} (a hard link failed: {error}; {size / 2 ** 20:.0f} MB, {cap})")
                    said.append(f"{folder} left out")
                    continue
                more, error = _seed_files(source, target, "copy")
                how = "linked and copied" if placed else "copied"
                placed += more
        if error is not None:
            _unplace(placed)
            left.append(f"{folder} ({error})")
            said.append(f"{folder} left out")
            continue
        seeded.append(folder)
        folders.append(folder)
        said.append(f"{folder} {how} ({len(placed)} files)")
    rows = 0
    try:
        rows = _copy_rows(real, cache_dir, folders)
    except sqlite3.Error as e:
        left.append(f"the index rows ({e}; the files are adopted when used)")
    copies = []
    for name in SEED_COPIED:
        path = os.path.join(real, *name.split("/"))
        if os.path.isfile(path):
            try:
                copies.append(f"{name} ({_copy_database(path, os.path.join(cache_dir, *name.split('/')))} rows)")
                seeded.append(name)
            except (sqlite3.Error, OSError) as e:
                left.append(f"{name} ({e})")
    print(f"Seeded {cache_dir} from {real}: " + (", ".join(said) or "no folder") + "; "
          + " and ".join(copies + [f"{rows} index rows"]) + " copied", flush=True)
    if left:
        print("Not seeded: " + "; ".join(left), flush=True)
    return seeded


def _lock_dir() -> Optional[str]:
    """tools/test_lock.py lock_dir() (FINDALINE_TEST_LOCK_DIR moves it), or None (no git, no such folder)."""
    import importlib.util
    try:
        spec = importlib.util.spec_from_file_location("findaline_test_lock",
                                                      os.path.join(REPO, "tools", "test_lock.py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.lock_dir()
    except Exception:  # no git, not a checkout, the tool missing: no log
        return None


def read_counts(path: str) -> Optional[dict]:
    """A search's counts file (servicecounts.summary, written by findaline.py's search): {"hosts": {host: {"requests",
    "bytes", "failed"[, "reads": true]}}, "tiles": {"downloaded", "cached"}}; None when it is missing or not of that
    shape (no counts for the entry, never an error). Host names only (servicecounts.written_host again)."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        hosts = {}
        for host, values in data["hosts"].items():
            found = {key: int(values[key]) for key in ("requests", "bytes", "failed")}
            if values.get("reads") is True:
                found["reads"] = True
            hosts[servicecounts.written_host(str(host))] = found
        return {"hosts": hosts, "tiles": {key: int(data["tiles"][key]) for key in ("downloaded", "cached")}}
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return None


def merged_counts(search: Optional[dict], checks: Optional[dict]) -> Optional[dict]:
    """An entry's counts: its search's (read_counts) plus those of the harness's checks after it (a summary of
    servicecounts.counting); None while the search's are unknown and the checks asked nothing."""
    if not search and not (checks and checks.get("hosts")):
        return search
    parts = [part for part in (search, checks) if part]
    return {"hosts": hosts_summed(dict(enumerate(parts))),
            "tiles": {key: sum(part.get("tiles", {}).get(key, 0) for part in parts) for key in ("downloaded", "cached")}}


def with_counts(entry: dict, counts: Optional[dict]) -> dict:
    """An entry of the run log with its search's requests per host and tiles (`hosts`, `tiles`), when counted."""
    if counts:
        entry["hosts"], entry["tiles"] = counts.get("hosts", {}), counts.get("tiles", {"downloaded": 0, "cached": 0})
    return entry


def hosts_summed(entries: dict) -> dict:
    """The run's requests, bytes and failed attempts per host, summed over its entries (`reads` where any has it)."""
    total: Dict[str, dict] = {}
    for entry in entries.values():
        for host, values in entry.get("hosts", {}).items():
            found = total.setdefault(host, {"requests": 0, "bytes": 0, "failed": 0})
            for key in ("requests", "bytes", "failed"):
                found[key] += values[key]
            if values.get("reads"):
                found["reads"] = True
    return total


def write_run_log(record: dict):
    """Append one JSON line to RUN_LOG in the test lock's folder, under a file lock (two runs ending at once never
    tear a line). Never fails a run: an error is one warning line; no lock folder, no file."""
    try:
        from filelock import FileLock
        folder = _lock_dir()
        if folder is None:
            return
        from settings import redact
        path = os.path.join(folder, RUN_LOG)
        # a key's value masked wherever it is (a reason quotes a provider's error text, cleaned by the search already)
        line = redact(json.dumps(record, ensure_ascii=False, separators=(",", ":"), default=str))
        with FileLock(path + ".lock", timeout=10):
            with open(path, "a", encoding="utf-8", newline="\n") as f:
                f.write(line + "\n")
    except Exception as e:
        print(f"WARNING: the run log was not written ({type(e).__name__}: {e})")


def write_doc(tests: dict):
    rows = ["| ID | Place / what it covers | Arguments | Anchors | Open anchors / checked pairs | Lines / spots | Also check |",
            "| --- | --- | --- | --- | --- | --- | --- |"]
    for test_id, test in tests.items():
        e = test["expected"]
        if test.get("kind") == "osm":
            rows.append(f"| {test_id} | {test['place']} | extract `{test['region']}`, box {test['bbox']} | | | | "
                        + "; ".join(f"{e.get(t)} {t} features" for t in test["themes"])
                        + ", the same from Overpass |")
            continue
        args = f"{test['extends']} + `{test['args']}`" if "extends" in test else f"`{test['args']}`"
        also = []
        if "source" in e:
            also.append(f"source `{e['source']}`")
        if "coverage" in e:
            also.append(f"data {e['coverage']:g}%" + (f", {e['empty_tiles']} tiles without data"
                                                      if e.get("empty_tiles") else ""))
        if "filled_km2" in e:
            also.append(f"`Filled {e['filled_km2']:.2f} km² ... from {e.get('filled_from', '')}`")
        if e.get("sea_km2"):
            also.append(f"sea {e['sea_km2']:.2f} km²")
        if e.get("water_spots"):
            also.append(f"{number(e['water_spots'])} spots over water")
        if e.get("water_lines"):
            also.append(f"{number(e['water_lines'])} lines with `water_m > 0`")
        if test.get("same_as"):
            also.append(f"the CSV export identical to {test['same_as']}")
        if "access_ends" in e:
            hard, unsure, easy = e["access_ends"]
            also.append(f"line ends: {number(easy)} easy access, {number(unsure)} cannot tell, {number(hard)} hard "
                        f"access")
        if test.get("without_access_as"):
            also.append(f"the CSV export less access1, access2 identical to {test['without_access_as']}")
        if test.get("check_profiles"):
            also.append(f"{test['check_profiles']} profiles computed again")
        if "lines_in_region" in e:
            also.append(f"{number(e['lines_in_region'])} lines with an anchor in {test['count_anchors_in']}")
        if test.get("notes"):
            also.append(test["notes"])
        rows.append(f"| {test_id} | {test['place']} | {args} | {number(e['anchors'])} | "
                    f"{number(e['open'])} / {number(e['checked'])} | {number(e['lines'])} / {number(e['spots'])} | "
                    f"{'; '.join(also)} |")
    with open(DOC, encoding="utf-8") as f:
        text = f.read()
    start, end = text.index(TABLE_START) + len(TABLE_START), text.index(TABLE_END)
    with open(DOC, "w", encoding="utf-8", newline="\n") as f:
        f.write(text[:start] + "\n" + "\n".join(rows) + "\n" + text[end:])
    print(f"Table written to {DOC}")


def select(tests: dict, args) -> tuple:
    """(the ids to run, the ids left out as by name only): the ids named, the sets, --all (every test but those with
    "by_name"), else the quick set (also without them); an entry run by name only runs when named or in a --set."""
    ids = list(args.ids)
    for name in args.set:
        ids += [t for t, test in tests.items() if name in test["sets"]]
    by_name = []
    if args.all:
        by_name = [t for t, test in tests.items() if test.get("by_name") and t not in ids]
        ids += [t for t in tests if t not in by_name]
    if not ids and not (args.write_doc and not args.update):
        ids = [t for t, test in tests.items() if "quick" in test["sets"] and not test.get("by_name")]
    return list(dict.fromkeys(ids)), by_name


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("ids", nargs="*", help="test IDs (default: the quick set)")
    parser.add_argument("--set", action="append", default=[], help="run a named set (repeatable)")
    parser.add_argument("--all", action="store_true", help="run every test (not those run by name only)")
    parser.add_argument("--update", action="store_true", help="store the results of the run tests as expected "
                                                              "(never those of an unverified test)")
    parser.add_argument("--write-doc", action="store_true", help="rewrite the table in docs/regression-tests.md")
    parser.add_argument("--browser", action="store_true", help="also check the map in a headless browser")
    parser.add_argument("--keep", action="store_true",
                        help="keep the log folder (runs, maps, output) also when no test differs")
    parser.add_argument("--cache", help="cache folder for the searches (default: cache/ in FINDALINE_DATA or this "
                                         "checkout; a worktree's own is empty: pass the main checkout's)")
    parser.add_argument("--cold", action="store_true",
                        help="run on a missing or empty cache folder too (downloads), seeding it first from the real "
                             "cache; harmless on a cache that has data already (only what it lacks is seeded)")
    parser.add_argument("--no-seed", action="store_true", help="with --cold: no seeding, a truly empty cache")
    parser.add_argument("--mirror-url", help="the project's data server for our own tiles (a local copy of the "
                                              "mirror stack, http://...); default: none, it is never asked")
    args = parser.parse_args()
    # The searches (and the profiles checked here) ask only the data server named: none by default
    os.environ["FINDALINE_MIRROR_URL"] = args.mirror_url or "off"

    tests = load()
    ids, by_name = select(tests, args)
    unknown = [t for t in ids if t not in tests]
    if unknown:
        sys.exit(f"Unknown tests: {', '.join(unknown)}")

    cache_dir = args.cache or os.path.join(cache.data_dir(), "cache")
    real = real_cache_dir()
    searches = [t for t in ids if tests[t].get("kind") != "osm"]  # R17 alone reads only its extract (as before)
    if searches and not holds_cache(cache_dir):
        state = "missing" if not os.path.isdir(cache_dir) else "empty" if not os.listdir(cache_dir) else None
        if state is None:  # files but no LAYOUT: no cache of this layout, --cold or not (cache.check_layout's case)
            parser.error(f"the folder {cache_dir} holds files but no LAYOUT file: it is no cache of this layout; "
                         f"pass --cache {real} or an empty folder")
        if not args.cold:
            if same_folder(cache_dir, real):
                parser.error(f"the cache folder {cache_dir} is the real cache and it is {state} (no LAYOUT file): "
                             f"fill it, or pass --cold to download")
            parser.error(f"the cache folder {cache_dir} is {state} (no LAYOUT file): pass --cache {real}, or --cold "
                         f"to download")
    started, start_time, seeded = time.time(), datetime.now(timezone.utc), []
    if searches and args.cold:
        cache.check_layout(cache_dir)  # a new cache gets its LAYOUT (a seeded one must have it before its files)
        if not args.no_seed:
            seeded = seed(cache_dir, real, own_world_folders(tests, searches))

    work = tempfile.mkdtemp(prefix="findaline-regression-")
    failed, unverified, skipped, refused, results, entries = [], [], [], [], {}, {}
    for test_id in by_name:
        print(f"{test_id}: not run (by name only)")
    for test_id in ids:
        test = tests[test_id]
        osm_kind = test.get("kind") == "osm"
        unmet = unmet_needs(test, args.mirror_url)
        if unmet:
            print(f"{test_id}: skipped ({unmet})")
            skipped.append(test_id)
            entries[test_id] = {"outcome": "skipped", "reason": unmet, "coastline": None, "seconds": 0}
            continue
        start = time.time()
        if osm_kind:
            with servicecounts.counting() as counted:  # R17's Overpass queries, in this process
                found = run_osm(test, os.path.join(work, test_id), cache_dir)
            found["service_counts"] = counted or None
        else:
            found = run(tests, test_id, work, cache_dir, args.browser)
        seconds = time.time() - start - found.pop("store_seconds", 0)  # the export check is not the search's
        found.pop("store_problems", None)  # a failed search's: its exit code says it
        counts = found.pop("service_counts", None)  # never a compared or stored value
        if "skipped" in found:
            print(f"{test_id}: skipped ({found['skipped']})")
            skipped.append(test_id)
            entries[test_id] = with_counts({"outcome": "skipped", "reason": found["skipped"], "coastline": None,
                                            "seconds": round(seconds, 1)}, counts)
            continue
        differences = found.pop("differences", None)  # R17's feature ids, printed below
        results[test_id] = found
        values = value_differences(test["expected"], found, () if osm_kind else ("coastline",))
        problems = own_problems(found)
        cross = []  # (difference, the other test)
        other = test.get("same_as")
        if other:
            sha = results.get(other, {}).get("csv_sha256") or tests[other]["expected"].get("csv_sha256")
            if found.get("csv_sha256") != sha:
                cross.append((f"the CSV export differs from that of {other}", other))
        base = test.get("without_access_as")
        if base:
            sha = results.get(base, {}).get("csv_sha256") or tests[base]["expected"].get("csv_sha256")
            if found.get("csv_sha256_without_access") != sha:
                cross.append((f"the CSV export without access1, access2 differs from that of {base}", base))
        if differences:
            values += describe_differences(differences)
        world_file = not osm_kind and coast.world_file(cache_dir) is not None  # after the search: as it ran
        status, reason = outcome(test, found, values, problems, cross, world_file, tuple(unverified))
        diffs = (own_problems({"exit": found.get("exit")}) + values + list(found.get("problems", []))
                 + [line for line, _ in cross])  # in the order printed before
        slow = test.get("seconds") and seconds > SLOWER * test["seconds"] and seconds - test["seconds"] > 5
        print(f"{test_id}: {status}" + (f" ({reason})" if reason else "") + f" ({seconds:.0f} s"
              + (f", WARNING: recorded {test['seconds']:.0f} s" if slow else "")
              + ")" + "".join(f"\n    {d}" for d in diffs), flush=True)
        (failed if status == "DIFFERENT" else unverified if status == "unverified" else []).append(test_id)
        entries[test_id] = with_counts({"outcome": status.lower(), "reason": reason,
                                        "coastline": None if osm_kind else found.get("coastline"),
                                        "seconds": round(seconds, 1)}, counts)
        if args.update:
            why = not_storable(test, found, status, reason, world_file)
            if why:
                print(f"{test_id}: not stored ({why})", flush=True)
                refused.append(test_id)
            elif not found.get("exit") and not found.get("problems"):
                test["expected"] = ({k: v for k, v in found.items() if k not in ("exit", "unanswered")} if osm_kind
                                    else stored(found, test["expected"], ok=status == "ok"))
                test["seconds"] = round(seconds, 1)
    if args.update:
        with open(TESTS, "w", encoding="utf-8", newline="\n") as f:
            json.dump(tests, f, ensure_ascii=False, indent=2)
            f.write("\n")
        print(f"Expected values updated in {TESTS}")
    if args.write_doc:
        write_doc(tests)
    if failed or unverified or args.keep:
        where = f"logs in {work}"
    else:  # rmtree removes the cache links as links, never what they point to
        shutil.rmtree(work, ignore_errors=True)
        where = f"some of the logs left in {work}" if os.path.exists(work) else "logs removed (--keep keeps them)"
    ok = len(ids) - len(failed) - len(unverified) - len(skipped)
    if ids:
        print(f"\n{ok} ok, {len(failed)} different, {len(unverified)} unverified, {len(skipped)} skipped"
              + (f", {len(by_name)} by name only" if by_name else "") + f"; {where}")
    if args.update:
        code = 3 if refused else 0
    else:
        code = 1 if failed else 3 if unverified else 0
    if ids:
        write_run_log({
            "v": RUN_LOG_VERSION, "time": start_time.isoformat(timespec="seconds"),
            "seconds": round(time.time() - started, 1), "commit": _git("rev-parse", "HEAD"),
            "branch": _git("rev-parse", "--abbrev-ref", "HEAD"), "worktree": os.path.basename(REPO),
            "cache": cache_dir, "cache_real": os.path.realpath(cache_dir), "real_cache": same_folder(cache_dir, real),
            "cold": args.cold, "seeded": seeded,
            "args": {"ids": args.ids, "all": args.all, "sets": args.set, "update": args.update,
                     "browser": args.browser},
            "entries": entries,
            "counts": {"ok": ok, "different": len(failed), "unverified": len(unverified), "skipped": len(skipped),
                       "by_name": len(by_name)},
            "exit": code, "lock_token": os.environ.get(LOCK_TOKEN_ENV) or None, "hosts": hosts_summed(entries)})
    sys.exit(code)


if __name__ == "__main__":
    from progress import utf8_output
    utf8_output()  # redirected output in UTF-8, not the Windows code page (no "²" there)
    main()
