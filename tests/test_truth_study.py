"""tools/truth_study.py: the clusters of known lines (the link, the cap's bisection, the radius and length
rules, midlines clustered with highlines), the sources chosen offline, the places against a copy of
tests/regression.json, the delegation to tools/truth_analysis.py, the one data folder of a run (its cache
linked once, unlinked afterwards, also after an interruption; a cluster searched again keeps only its new
run; each child's own work folder removed; a saved run slimmed to its run.json unless keep_runs), run
--parallel with a stand-in child process (three at once, a failure, one without lines, a timeout, Ctrl+C:
the children's trees killed), a failed search's error and message (from result.json, else the last line of
the child's stderr, which output.log holds after its stdout), run --failed, --status and --ids @FILE,
cluster --extra, and a run of the Żabi Koń clip offline with the formula and with the sag model (a search with
lines, one without, a resumed pass; both at once giving the same captures) with the capture's files as the
analysis reads them (the found anchors back on their pixels, their clearances evaluated again; analyse
--profiles on the saved run's run.json alone), and the real child's errors there (a source that cannot serve
the place, an option findaline.py refuses).
Synthetic lines only: invented ids and coordinates (no SlackMap data in the repository)."""

import gzip

import dataclasses
import json
import math
import os
import random
import re
import subprocess
import sys
import time
import types
from decimal import Decimal

import numpy as np
import psutil
import pytest
from pyproj import Geod, Transformer

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools"))
import slackmap_data as sd  # noqa: E402
import truth_study as ts  # noqa: E402
from test_offline import DATA, OFFLINE_ENV  # noqa: E402

PL = "EPSG:2180"  # geoportal's CRS: the linking CRS of Poland's lines
TO_PL = Transformer.from_crs("EPSG:4326", PL, always_xy=True)
FROM_PL = Transformer.from_crs(PL, "EPSG:4326", always_xy=True)
BASE = TO_PL.transform(19.94, 50.06)  # metres of EPSG:2180 near Kraków: the synthetic lines start here
GEOD = Geod(ellps="WGS84")


def latlon(x: float, y: float):
    """(lat, lon) of metres east and north of BASE in EPSG:2180."""
    lon, lat = FROM_PL.transform(BASE[0] + x, BASE[1] + y)
    return lat, lon


def feature(line_id, x1, y1, x2, y2, lt="h", c="pl", stated=None) -> dict:
    """A SlackMap-like line feature between two points of EPSG:2180 (metres from BASE), its coordinates
    written with 7 decimals, its stated length the geodesic one to a decimetre unless given."""
    (lat1, lon1), (lat2, lon2) = latlon(x1, y1), latlon(x2, y2)
    length = GEOD.inv(lon1, lat1, lon2, lat2)[2] if stated is None else stated
    props = {"id": line_id, "ft": "l", "l": f"{length:.1f}m", "c": c}
    if lt is not None:
        props["lt"] = lt
    return {"type": "Feature", "properties": props,
            "geometry": {"type": "LineString", "coordinates": [[Decimal(f"{lon1:.7f}"), Decimal(f"{lat1:.7f}")],
                                                               [Decimal(f"{lon2:.7f}"), Decimal(f"{lat2:.7f}")]]}}


def line(*args, **kwargs) -> sd.KnownLine:
    return sd.normalise(feature(*args, **kwargs))


def anchors_within(c: ts.Cluster, crs: str = PL) -> float:
    """The farthest anchor of a cluster from its centre, metres of crs."""
    to = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    x0, y0 = to.transform(c.centre[1], c.centre[0])
    return max(math.hypot(to.transform(p[1], p[0])[0] - x0, to.transform(p[1], p[0])[1] - y0)
               for known in c.lines for p in (known.a, known.b))


def test_two_groups_and_the_radius():
    """Groups 1 km apart are two clusters; a cluster's radius is its farthest anchor plus the margin, at least
    RADIUS_MIN; the linking CRS of Poland is geoportal's."""
    lines = [line("a1", 0, 0, 200, 0), line("a2", 250, 0, 450, 0), line("a3", 500, 0, 600, 0),  # 50 m gaps
             line("b1", 1600, 0, 1700, 0)]
    found = ts.cluster(lines)
    assert [sorted(k.id for k in c.lines) for c in found] == [["a1", "a2", "a3"], ["b1"]]
    a, b = found
    assert a.crs == b.crs == PL and a.split == b.split == 0
    assert 350 <= a.radius <= 351 and abs(a.farthest - 300) < 0.05  # the box centre at x 300: anchors 300 m off
    assert b.radius == ts.RADIUS_MIN  # a 100 m line: 50 + 50 m, raised to the minimum
    assert a.id.startswith("pl-50.") and "n19." in a.id and a.id.endswith("e") and a.id != b.id
    assert len(ts.cluster(lines, link_m=40)) == 4  # 50 m gaps no longer link


def test_chain_split_by_the_cap():
    """A chain of 4.1 km whose lines are linked (100 m gaps) is bisected once: two clusters under the cap,
    together every line, each anchor within its circle less the margin."""
    lines = [line(f"c{k:02d}", 200 * k, 0, 200 * k + 100, 0) for k in range(21)]
    found = ts.cluster(lines)
    assert len(found) == 2 and all(c.split == 1 and c.radius <= ts.RADIUS_MAX and not c.over_cap for c in found)
    ids = [sorted(k.id for k in c.lines) for c in found]
    assert sorted(ids[0] + ids[1]) == [f"c{k:02d}" for k in range(21)] and not set(ids[0]) & set(ids[1])
    assert sorted(len(i) for i in ids) == [10, 11]
    for c in found:
        assert anchors_within(c) <= c.radius - ts.MARGIN_M + 0.05
    assert len(ts.cluster(lines, radius_max=700)) >= 4  # a smaller cap halves again
    assert all(c.radius <= 700 for c in ts.cluster(lines, radius_max=700))


def test_a_line_too_long_for_any_cluster_is_left_out():
    """Anchors farther apart than twice (cap - margin): a misplaced anchor, never a search of its own."""
    lines = [line("long", 0, 0, 3000, 0, stated=40), line("ok", 0, 500, 100, 500)]
    assert ts.reach_limit() == 2900
    assert [k.id for c in ts.cluster(lines) for k in c.lines] == ["ok"]


def test_length_rules_and_options():
    """--min-length max(15, 0.8 shortest), --max-length max(100, 1.1 longest), the stated and the geodesic
    length of each line (the stated alone when they disagree), the fixed options."""
    c = ts.cluster([line("s", 0, 0, 50, 0, stated=48), line("l", 0, 30, 200, 30, stated=205)])[0]
    lo, hi = ts.line_span(next(k for k in c.lines if k.id == "l"))
    assert lo == pytest.approx(200.1, abs=0.3) and hi == 205.0  # the geodesic and the stated length
    assert c.min_length == 38 and c.max_length == 226  # floor(0.8 * 48), ceil(1.1 * 205)
    mismatch = line("m", 0, 0, 100, 0, stated=300)
    assert mismatch.flags == ("length_mismatch",) and ts.line_span(mismatch) == (300.0, 300.0)
    c = ts.cluster([mismatch])[0]
    assert (c.min_length, c.max_length) == (240, 330)
    c = ts.cluster([line("short", 0, 0, 10, 0)])[0]
    assert (c.min_length, c.max_length) == (15, 100)  # the floors
    options = c.options
    assert options.startswith(f"--lat {c.centre[0]:.6f} --lon {c.centre[1]:.6f} --radius 200 ")
    assert "--min-length 15 --max-length 100" in options and "--source" not in options
    assert options.endswith("--no-plot --yes --ortho never")


def test_cluster_extra_options(tmp_path):
    """cluster --extra: the options added to every cluster's search after --source, before the fixed ones, and
    kept in clusters.json as "extra" (each cluster's and the params'); an unclosed quote refused."""
    c = ts.cluster([line("s", 0, 0, 50, 0)])[0]
    c.source, c.extra = "geoportal", "--model sag --pretension 3"
    assert c.options.endswith("--source geoportal --model sag --pretension 3 --no-plot --yes --ortho never")
    assert c.as_dict()["extra"] == "--model sag --pretension 3"
    import cache
    data = tmp_path / "data"
    cache_dir = str(data / "cache")
    cache.check_layout(cache_dir)  # a new cache, then SlackMap's lines file in it (no download)
    path = sd.lines_path(cache_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    features = [feature("a", 0, 0, 60, 0), feature("b", 5000, 0, 5080, 0, lt="m")]
    with gzip.open(path, "wt", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": features}, f, default=float)
    out = tmp_path / "out"
    assert ts.main(["cluster", "--out", str(out), "--data-dir", str(data), "--auto", "--extra", " --model sag "]) == 0
    written = json.loads((out / "clusters.json").read_text(encoding="utf-8"))
    assert written["params"]["extra"] == "--model sag" and len(written["clusters"]) == 2
    for c in written["clusters"]:
        assert c["extra"] == "--model sag" and c["options"].endswith(
            f"--max-length {c['max_length']:g} --model sag --no-plot --yes --ortho never")
    assert ts.main(["cluster", "--out", str(out), "--data-dir", str(data), "--auto"]) == 0
    assert all(c["extra"] == "" and "--model" not in c["options"]
               for c in json.loads((out / "clusters.json").read_text(encoding="utf-8"))["clusters"])
    assert ts.main(["cluster", "--out", str(tmp_path / "bad"), "--data-dir", str(data), "--auto",
                    "--extra", '--name "unclosed']) == 1
    assert not (tmp_path / "bad" / "clusters.json").exists()


def test_midlines_with_highlines_and_types():
    """Highlines and midlines by default, clustered together, each line keeping its type; longlines only when
    asked; covered() keeps the countries of the catalogue."""
    lines = [line("h1", 0, 0, 100, 0), line("m1", 0, 80, 100, 80, lt="m"), line("l1", 0, 160, 100, 160, lt="l")]
    (c,) = ts.cluster(lines)
    assert sorted(k.id for k in c.lines) == ["h1", "m1"] and c.types == {"highline": 1, "midline": 1}
    assert {k.id: k.type for k in c.lines} == {"h1": "highline", "m1": "midline"}
    assert c.as_dict()["types"] == {"highline": 1, "midline": 1}
    assert [k.id for k in ts.cluster(lines, types=["l"])[0].lines] == ["l1"]
    assert [k.id for k in ts.cluster(lines, types=["highline"])[0].lines] == ["h1"]
    with pytest.raises(ValueError):
        ts.type_names(["x"])
    nowhere = line("z1", 0, 0, 100, 0, c="zz")
    assert [k.id for k in ts.covered(lines + [nowhere])] == ["h1", "m1"]
    assert [k.id for k in ts.covered(lines + [nowhere], ["h", "m", "l"])] == ["h1", "m1", "l1"]


def test_ids_stable_and_file_names():
    """The same lines in another order give the same clusters and names; a name names a folder."""
    lines = [line(f"x{k}", 400 * k, 0, 400 * k + 120, 10 * k) for k in range(8)] + [line("far", 9000, 0, 9080, 0)]
    first = {c.id: sorted(k.id for k in c.lines) for c in ts.cluster(lines)}
    shuffled = lines[:]
    random.Random(3).shuffle(shuffled)
    assert {c.id: sorted(k.id for k in c.lines) for c in ts.cluster(shuffled)} == first
    assert all(ts.NAME.fullmatch(name) for name in first)
    assert ts.cluster_id("ar", -41.12345, -71.5) == "ar-41.123s71.500w"


def test_sources_offline_and_deferred(tmp_path):
    """--offline-sources: sources.choose_source on OFFLINE_BOXES alone (no Nominatim): geoportal for a cluster
    near Kraków, the radius measured in its CRS, --source in the options; --auto: none."""
    import osm
    reverse = osm.reverse
    found = ts.cluster([line("a", 0, 0, 300, 0), line("b", 0, 40, 290, 60, lt="m")])
    ts.with_sources(found, str(tmp_path / "cache"), "offline")
    assert osm.reverse is reverse  # put back
    (c,) = found
    assert c.source == "geoportal" and c.national is True and c.search_crs == PL and "PL" in c.reason
    assert "--source geoportal" in c.options and c.radius == ts.cluster(c.lines)[0].radius
    tatras = line("sk1", 0, 0, 120, 0, c="sk")  # moved below to the Slovak side of the High Tatras
    lat, lon = 49.12, 20.07  # in Poland's offline box (the first holding it) and Slovakia's
    tatras = dataclasses.replace(tatras, a=(lat, lon), b=(lat, lon + 0.0016))
    (sk,) = ts.with_sources(ts.cluster([tatras]), str(tmp_path / "cache"), "offline")
    assert sk.source == "geoportal" and sk.country == "SK"  # the offline boxes are rough at a border
    with ts.offline_lookups():  # no lookup of the regions either (Slovakia has no regional source)
        (sk,) = ts.with_sources(ts.cluster([tatras]), str(tmp_path / "cache"), "lines")
    assert sk.source in ("slovakia", "europe") and "SK" in sk.reason  # europe without the Slovak tiles' mirror
    from sources import choose
    assert choose.country_code.__module__ == "sources.choose"  # put back
    ts.with_sources(found, str(tmp_path / "cache"), "defer")
    assert c.source is None and "--source" not in c.options and c.search_crs == c.crs
    with pytest.raises(ValueError):
        ts.with_sources(found, str(tmp_path / "cache"), "guess")


def test_places_against_regression_json(tmp_path):
    """The ranking per country and source, the nearest regression test (--lat/--lon, --northing/--easting of
    EPSG:2180, extends; --area and osm tests left out), "covered by" within 2 km."""
    lines = ([line(f"a{k}", 100 * k, 0, 100 * k + 60, 0) for k in range(3)]  # three lines at the origin
             + [line("b1", 20000, 0, 20100, 0)]                              # 20 km east
             + [line("c1", 0, 40000, 80, 40000, lt="m")])                    # 40 km north
    found = ts.with_sources(ts.cluster(lines), str(tmp_path / "cache"), "offline")
    ts.write_clusters(str(tmp_path), found, {"types": ["highline", "midline"]})
    a_lat, a_lon = latlon(150, 0)
    tests = {"R1": {"args": f"--lat {a_lat:.5f} --lon {a_lon + 0.01:.5f} --resolution 2"},  # 0.7 km east of a
             "R2": {"extends": "R1", "args": "--model sag"},
             "R3": {"args": f"--northing {BASE[1] + 500:.1f} --easting {BASE[0] + 20000:.1f} --radius 500"},
             "R4": {"args": "--area coast --buffer 100 --within 36.06,14.20,36.085,14.27"},
             "R5": {"kind": "osm", "region": "malta"}}
    path = tmp_path / "regression.json"
    path.write_text(json.dumps(tests), encoding="utf-8")
    places = ts.regression_places(str(path))
    assert [p["id"] for p in places] == ["R1", "R2", "R3"]
    assert places[0]["radius"] == ts.DEFAULT_RADIUS and places[2]["radius"] == 500
    lat3, lon3 = latlon(20000, 500)
    assert places[2]["lat"] == pytest.approx(lat3, abs=2e-6) and places[2]["lon"] == pytest.approx(lon3, abs=2e-6)
    rows = ts.places(ts.load_clusters(str(tmp_path)), places)
    assert [r["count"] for r in rows] == [3, 1, 1]
    by_id = {r["id"]: r for r in rows}
    a = rows[0]
    assert a["covered_by"] == "R1" and a["distance"] < 1000 and a["source"] == "geoportal"
    assert a["where"].startswith("--lat ") and a["where"].endswith(f"--radius {a['radius']:g}")
    b = next(r for r in rows if r["covered_by"] == "R3")
    assert b["count"] == 1 and b["distance"] < 600
    c = next(r for r in by_id.values() if r["types"].get("midline"))
    assert c["covered_by"] is None and c["nearest"] in ("R1", "R2") and c["distance"] > 30000
    text = ts.write_places(str(tmp_path), str(path), top=2, per_group=1)
    assert text == (tmp_path / "places.md").read_text(encoding="utf-8")
    assert "**covered by R1**" in text and "**covered by R3**" in text and "## The top 2" in text
    assert "### PL, geoportal: 3 clusters, 5 lines (highlines 4, midlines 1); covered by R1, R3" in text
    assert "| 2 more | 2 |" in text


def test_analyse_and_report_delegate(monkeypatch, tmp_path, capsys):
    """analyse and report call tools/truth_analysis.py's functions; a missing module is said plainly."""
    calls = []
    fake = types.SimpleNamespace(analyse=lambda out, profiles=False, clusters=None, cache_dir=None: calls.append(
        ("analyse", out, profiles, clusters, cache_dir)), report=lambda out, pictures=True: calls.append(
        ("report", out, pictures)) or "the report")
    monkeypatch.setitem(sys.modules, "truth_analysis", fake)
    cache_dir = str(tmp_path / "elsewhere" / "cache")
    assert ts.main(["analyse", str(tmp_path), "--profiles", "--cluster", "pl-1", "pl-2", "--cache", cache_dir]) == 0
    assert ts.main(["analyse", str(tmp_path), "--data-dir", str(tmp_path / "data-folder")]) == 0
    assert ts.main(["report", str(tmp_path), "--no-pictures"]) == 0
    assert calls == [("analyse", str(tmp_path), True, ["pl-1", "pl-2"], cache_dir),
                     ("analyse", str(tmp_path), False, None, str(tmp_path / "data-folder" / "cache")),
                     ("report", str(tmp_path), False)]
    assert "the report" in capsys.readouterr().out
    monkeypatch.setitem(sys.modules, "truth_analysis", None)  # an import of it raises ImportError
    assert ts.main(["report", str(tmp_path)]) == 2
    assert "truth_analysis.py is missing" in capsys.readouterr().err


def _is_link(path) -> bool:
    return os.path.islink(path) or (hasattr(os.path, "isjunction") and os.path.isjunction(path))


STAND_IN = r'''"""A stand-in for search-child (tests/test_truth_study.py): the arguments of truth_study.child_command,
the work folder findaline.py leaves on Windows, a saved run and a complete capture, and a record of what it saw
in STANDIN_LOG; its behaviour by the cluster's name in the STANDIN_* variables."""
import json
import os
import sys
import time

args = sys.argv[1:]
capture, work_id = args[args.index("--out") + 1], args[args.index("--work-id") + 1]
data = args[args.index("--data-dir") + 1]
name = os.path.basename(os.path.dirname(capture))
log = os.environ["STANDIN_LOG"]


def named(key):
    return name in os.environ.get("STANDIN_" + key, "").split(",")


def count(kind):
    return sum(n.endswith(f".{kind}.json") for n in os.listdir(log))


def write(kind, record):
    path = os.path.join(log, f"{name}.{os.getpid()}.{kind}.json")
    with open(path + ".part", "w", encoding="utf-8") as f:
        json.dump(record, f)
    os.replace(path + ".part", path)


cache = os.path.join(data, "cache")
os.makedirs(os.path.join(data, "work", work_id, f"20261108-000000-{os.getpid()}", "grids"))
record = {"name": name, "pid": os.getpid(), "data": data, "work_id": work_id, "start": time.time(),
          "link": os.path.islink(cache) or (hasattr(os.path, "isjunction") and os.path.isjunction(cache)),
          "tile": os.path.exists(os.path.join(cache, "layer", "tile.txt")),
          "running": count("start") - count("end") + 1}
write("start", record)
print(f"stand-in {name}: started", flush=True)
barrier, deadline = int(os.environ.get("STANDIN_BARRIER", "0")), time.time() + 30
while count("start") < barrier and time.time() < deadline:
    time.sleep(0.02)
record["met"] = count("start") >= barrier
if named("HANG"):
    time.sleep(600)
code, result = 0, None
if named("FAIL"):
    code = 3  # no capture: a failed search
elif named("STDERR"):  # a crash before result.json: its text on stderr only, the key of a URL to mask
    sys.stderr.write("a warning\nHTTPError: 503 for url: https://x.example/a?apikey=SECRET\n\n")
    sys.stderr.flush()
    code = 1
elif named("CODED"):  # what search-child writes for a coded error, its text on stderr as well
    print("Download failed: HTTP 503", file=sys.stderr, flush=True)
    code, result = 1, {"complete": False, "lines": None, "error": "download_failed",
                       "message": "Download failed: HTTP 503", "run": None}
elif named("NO_LINES"):
    code, result = 1, {"complete": True, "lines": 0, "error": "no_lines", "message": "No lines found", "run": None}
else:
    run = os.path.join(data, "runs", f"2026-11-08_{name}_{os.getpid()}_{time.time_ns()}")
    os.makedirs(run)
    with open(os.path.join(run, "run.json"), "w", encoding="utf-8") as f:
        json.dump({"id": os.path.basename(run)}, f)
    for file in ("map.html", "data.js", "lines.js", "lines.csv", "lines.geojson", "ATTRIBUTION.txt", "notes.txt"):
        with open(os.path.join(run, file), "w", encoding="utf-8") as f:
            f.write(file)
    result = {"complete": True, "lines": 3, "error": None, "run": run}
if result is not None:
    os.makedirs(capture)
    with open(os.path.join(capture, "result.json"), "w", encoding="utf-8") as f:
        json.dump(result, f)
record["run"] = result and result["run"]
write("end", record)
sys.exit(code)
'''


def stand_in(monkeypatch, tmp_path, **behaviour):
    """search-child replaced by STAND_IN, a real child process (so the run's processes, their kill and their work
    folders are real); returns the folder of its records. behaviour: the STANDIN_<KEY> variables (barrier: wait
    until that many children have started, at most 30 s; hang, fail, stderr, coded, no_lines: the clusters named,
    by commas). A search that ends well saves a run with run.json, the line files and a notes.txt."""
    script = tmp_path / "stand_in.py"
    script.write_text(STAND_IN, encoding="utf-8")
    log = tmp_path / "records"
    log.mkdir()
    monkeypatch.setenv("STANDIN_LOG", str(log))
    for key, value in behaviour.items():
        monkeypatch.setenv(f"STANDIN_{key.upper()}", value)
    real = ts.child_command
    monkeypatch.setattr(ts, "child_command", lambda *args: [sys.executable, str(script), *real(*args)[2:]])
    return log


def records(log, kind="start"):
    """The stand-ins' records of a kind ("start", "end"), in the order they started."""
    return sorted((json.loads(path.read_text(encoding="utf-8")) for path in log.glob(f"*.{kind}.json")),
                  key=lambda r: r["start"])


def wait_for(test, seconds=60.0):
    deadline = time.time() + seconds
    while not test():
        assert time.time() < deadline, "the stand-in children did not start"
        time.sleep(0.02)


def test_run_shares_one_data_folder(monkeypatch, tmp_path):
    """run, one search at a time (the default): every search in <out>/data, its cache/ linked once and unlinked at
    the end, also after an interruption (Ctrl+C while the second search runs: its child's tree killed); the lines
    said as before; capture.json names each saved run relative to <out>; a cluster searched again keeps only its
    new run; the work folder each child was given is removed, nothing else of work/. The child is a stand-in
    process that saves a run and a complete capture."""
    cache_dir = tmp_path / "cache"
    (cache_dir / "layer").mkdir(parents=True)
    (cache_dir / "layer" / "tile.txt").write_text("tile", encoding="utf-8")
    out = tmp_path / "out"
    log = stand_in(monkeypatch, tmp_path)
    items = [{"id": name, "options": "--lat 50 --lon 20", "known": [{"id": f"{name}-1"}]} for name in ("c1", "c2")]
    said, quiet = [], (lambda text: None)
    found = ts.run(str(out), items, str(cache_dir), say=said.append)
    data = str(out / "data")
    seen = records(log)
    assert [(r["name"], r["data"], r["link"], r["tile"]) for r in seen] == [("c1", data, True, True),
                                                                            ("c2", data, True, True)]
    assert len(said) == 4 and said[0::2] == [f"[{k}/2] c{k}: searching (1 known lines) --lat 50 --lon 20"
                                             for k in (1, 2)]
    assert all(re.fullmatch(rf"\[{k}/2\] c{k}: done, 3 lines, \d+ s", said[2 * k - 1]) for k in (1, 2))
    assert not os.path.lexists(out / "data" / "cache") and (cache_dir / "layer" / "tile.txt").exists()
    assert [found[n]["status"] for n in ("c1", "c2")] == ["done", "done"]
    runs = {r["name"]: os.path.basename(r["run"]) for r in records(log, "end")}
    assert found["c1"]["run"] == f"data/runs/{runs['c1']}" and (out / found["c1"]["run"] / "run.json").exists()
    for name in ("c1", "c2"):  # each run without its line files once its capture is written: run.json kept
        assert sorted(os.listdir(out / found[name]["run"])) == ["notes.txt", "run.json"]
    assert not (out / "c1" / "data").exists()  # no data folder per cluster
    assert len({r["work_id"] for r in seen}) == 2 and all(r["work_id"].startswith("truth-") for r in seen)
    assert os.listdir(out / "data" / "work") == []  # the work folders the searches left removed
    assert (out / "c1" / "output.log").read_text(encoding="utf-8") == "stand-in c1: started\n"  # no stderr
    assert sorted(os.listdir(out / "c1")) == ["capture", "capture.json", "known.json", "output.log"]

    ts.run(str(out), items, str(cache_dir), say=quiet)  # captured already: nothing searched, nothing linked
    assert len(records(log)) == 2 and not os.path.lexists(out / "data" / "cache")

    found = ts.run(str(out), items[:1], str(cache_dir), again=True, say=quiet,  # c1 again: its old run removed
                   keep_runs=True)
    again = records(log, "end")[-1]
    assert again["name"] == "c1" and found["c1"]["run"] == "data/runs/" + os.path.basename(again["run"])
    assert sorted(os.listdir(out / "data" / "runs")) == sorted([os.path.basename(again["run"]), runs["c2"]])
    assert sorted(os.listdir(again["run"])) == sorted([*ts.RUN_FILES, "notes.txt", "run.json"])  # --keep-runs

    (out / "data" / "work" / "another").mkdir()  # not left by a search of this run: kept
    monkeypatch.setenv("STANDIN_HANG", "c2")
    before = len(records(log))

    def interrupt(text):  # Ctrl+C once the second search's child runs
        if "c2: searching" in text:
            wait_for(lambda: len(records(log)) == before + 2)
            raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        ts.run(str(out), items, str(cache_dir), again=True, say=interrupt)
    c2 = records(log)[-1]
    assert (c2["name"], c2["data"], c2["link"], c2["tile"]) == ("c2", data, True, True)  # linked while it ran
    assert not psutil.pid_exists(c2["pid"])  # its process tree ended (jobs.kill_tree)
    assert not os.path.lexists(out / "data" / "cache") and (cache_dir / "layer" / "tile.txt").exists()
    assert not (out / "c2" / "capture.json").exists()  # an interrupted cluster is searched on the next pass
    assert ts.captured(str(out / "c2"), items[1]["options"], ["c2-1"]) is None
    assert os.listdir(out / "data" / "work") == ["another"]


def test_run_in_parallel(monkeypatch, tmp_path, capsys):
    """run --parallel 3 over six places, the stand-in child: three children at once (each waits until three have
    started) and never more, started in the order given, all in the one data folder with its one cache link
    (unlinked afterwards); a failing child and one without lines leave the others going; each child's own work
    folder removed; the lines name the cluster and the searches done so far; the summary and the exit code as one
    at a time. A second pass searches only the failed place again."""
    import cache
    cache_dir = tmp_path / "cache"
    cache.check_layout(str(cache_dir))
    (cache_dir / "layer").mkdir()
    (cache_dir / "layer" / "tile.txt").write_text("tile", encoding="utf-8")
    log = stand_in(monkeypatch, tmp_path, barrier="3", fail="c2", no_lines="c5")
    out = tmp_path / "out"
    command = ["run", "--out", str(out), "--cache", str(cache_dir), "--parallel", "3"]
    for k in range(1, 7):
        command += ["--place", f"c{k}=--lat 50 --lon {20 + k}"]
    assert ts.main(command) == 1  # a failed search
    printed = capsys.readouterr().out
    assert "\n6 searches: 4 done, 1 no_lines, 1 failed\n" in printed
    seen = records(log)
    assert sorted(r["name"] for r in seen) == [f"c{k}" for k in range(1, 7)]  # each searched once
    assert {r["name"] for r in seen[:3]} == {"c1", "c2", "c3"}  # the first three at once, in the order given
    assert all(r["data"] == str(out / "data") and r["link"] and r["tile"] for r in seen)  # one folder, one link
    assert max(r["running"] for r in seen) <= 3 and all(r["met"] for r in records(log, "end"))
    assert len({r["work_id"] for r in seen}) == 6 and os.listdir(out / "data" / "work") == []
    assert not os.path.lexists(out / "data" / "cache") and (cache_dir / "layer" / "tile.txt").exists()
    states = [json.loads((out / f"c{k}" / "capture.json").read_text(encoding="utf-8")) for k in range(1, 7)]
    assert [s["status"] for s in states] == ["done", "failed", "done", "done", "no_lines", "done"]
    assert states[1]["returncode"] == 3 and states[4]["error"] == "no_lines" and states[4]["run"] is None
    assert all((out / s["run"] / "run.json").exists() for s in states if s["status"] == "done")
    assert len(os.listdir(out / "data" / "runs")) == 4
    lines = [line for line in printed.splitlines() if line.startswith("[")]
    assert len(lines) == 12
    assert lines[:3] == [f"[0/6 done] c{k}: searching (0 known lines) --lat 50 --lon {20 + k}" for k in (1, 2, 3)]
    ends = [re.fullmatch(r"\[(\d)/6 done\] (c\d): (done|failed|no_lines), [-\d]+ lines, \d+ s( \(no_lines\))?",
                         line) for line in lines if ": searching" not in line]
    assert all(ends) and [int(m.group(1)) for m in ends] == [1, 2, 3, 4, 5, 6]
    assert sorted(m.group(2) for m in ends) == [f"c{k}" for k in range(1, 7)]

    assert ts.main(command) == 1  # the failed place searched again (failing again), the others captured already
    lines = [line for line in capsys.readouterr().out.splitlines() if line.startswith("[")]
    assert len(records(log)) == 7 and records(log)[-1]["name"] == "c2"
    assert lines[:6] == ["[1/6 done] c1: captured already (done)",
                         "[1/6 done] c2: searching (0 known lines) --lat 50 --lon 22",
                         "[2/6 done] c3: captured already (done)", "[3/6 done] c4: captured already (done)",
                         "[4/6 done] c5: captured already (no_lines)", "[5/6 done] c6: captured already (done)"]
    assert len(lines) == 7 and re.fullmatch(r"\[6/6 done\] c2: failed, - lines, \d+ s", lines[6])
    assert ts.main([*command[:6], "0", *command[7:]]) == 1 and "error: --parallel 0" in capsys.readouterr().err


def test_run_parallel_timeout(monkeypatch, tmp_path):
    """--timeout is each child's own: a child past it has its process tree killed (status failed, error timeout,
    the line in its log) and its work folder removed while the other runs to its end; a fresh cache of its own
    (no cache link) is marked once before the children start."""
    import cache
    log = stand_in(monkeypatch, tmp_path, hang="slow")
    out = tmp_path / "out"
    items = [{"id": name, "options": "--lat 50 --lon 20", "known": []} for name in ("slow", "quick")]
    found = ts.run(str(out), items, None, timeout=5, say=lambda text: None, parallel=2)
    assert list(found) == ["slow", "quick"] and found["quick"]["status"] == "done"
    slow = found["slow"]
    assert slow["status"] == "failed" and slow["error"] == "timeout" and slow["returncode"] is None
    assert 5 <= slow["seconds"] < 60
    assert not psutil.pid_exists(next(r for r in records(log) if r["name"] == "slow")["pid"])
    assert (out / "slow" / "output.log").read_text(encoding="utf-8").endswith("truth_study: stopped after 5 s\n")
    assert os.listdir(out / "data" / "work") == []
    assert (out / "data" / "cache" / "LAYOUT").read_text(encoding="utf-8").strip() == str(cache.LAYOUT)
    assert not any(r["link"] for r in records(log))


def test_run_parallel_interrupted(monkeypatch, tmp_path):
    """Ctrl+C while three children run: every child's process tree killed and its work folder removed, the
    cluster finished before keeps its capture, the interrupted ones have none and the rest never started; the
    cache unlinked; the interruption goes on."""
    cache_dir = tmp_path / "cache"
    (cache_dir / "layer").mkdir(parents=True)
    log = stand_in(monkeypatch, tmp_path, hang="c2,c3,c4,c5,c6")
    out = tmp_path / "out"
    items = [{"id": f"c{k}", "options": "--lat 50 --lon 20", "known": [{"id": f"c{k}-1"}]} for k in range(1, 7)]
    said = []

    def interrupt(text):
        said.append(text)
        if "c4: searching" in text:
            wait_for(lambda: len(records(log)) == 4)  # c1 done, c2, c3 and c4 running
            raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        ts.run(str(out), items, str(cache_dir), say=interrupt, parallel=3)
    assert said[:3] == [f"[0/6 done] c{k}: searching (1 known lines) --lat 50 --lon 20" for k in (1, 2, 3)]
    assert len(said) == 5 and re.fullmatch(r"\[1/6 done\] c1: done, 3 lines, \d+ s", said[3])
    stopped = [r for r in records(log) if r["name"] != "c1"]
    assert sorted(r["name"] for r in stopped) == ["c2", "c3", "c4"]
    assert not any(psutil.pid_exists(r["pid"]) for r in stopped)  # every child's tree ended (jobs.kill_tree)
    assert json.loads((out / "c1" / "capture.json").read_text(encoding="utf-8"))["status"] == "done"
    for name in ("c2", "c3", "c4"):
        assert (out / name / "known.json").exists() and not (out / name / "capture.json").exists()
    assert not (out / "c5").exists() and not (out / "c6").exists()
    assert not os.path.lexists(out / "data" / "cache") and cache_dir.is_dir()
    assert os.listdir(out / "data" / "work") == []


def test_run_errors_seen(monkeypatch, tmp_path):
    """A failed search's error and message in capture.json and its progress line: a child that writes to stderr
    and exits 1 without result.json gives the last line of its stderr as the message (a key in a URL masked), a
    child that reports a coded error (result.json, as search-child writes it) its code and text; the stderr
    follows the stdout in output.log under the marker, the stderr file gone; a search that ends well writes no
    marker."""
    stand_in(monkeypatch, tmp_path, stderr="plain", coded="coded")
    out = tmp_path / "out"
    items = [{"id": name, "options": "--lat 50 --lon 20", "known": []} for name in ("plain", "coded", "good")]
    said = []
    found = ts.run(str(out), items, None, say=said.append)
    plain, coded, good = (found[name] for name in ("plain", "coded", "good"))
    assert (plain["status"], plain["error"], plain["returncode"]) == ("failed", None, 1)
    assert plain["message"] == "HTTPError: 503 for url: https://x.example/a?..."
    assert (coded["status"], coded["error"], coded["message"]) == ("failed", "download_failed",
                                                                   "Download failed: HTTP 503")
    assert good["status"] == "done" and good["error"] is None and good["message"] is None
    assert (out / "plain" / "output.log").read_text(encoding="utf-8") == (
        "stand-in plain: started\n\n--- stderr ---\na warning\nHTTPError: 503 for url: "
        "https://x.example/a?apikey=SECRET\n\n")  # the whole stderr in the log, as written
    assert (out / "coded" / "output.log").read_text(encoding="utf-8").endswith(
        "\n--- stderr ---\nDownload failed: HTTP 503\n")
    assert ts.STDERR_MARK not in (out / "good" / "output.log").read_text(encoding="utf-8")
    assert not any((out / name / ts.STDERR_FILE).exists() for name in ("plain", "coded", "good"))
    assert re.fullmatch(r"\[1/3\] plain: failed, - lines, \d+ s \(HTTPError: 503 for url: https://x\.example/a\?\.\.\.\)",
                        said[1])
    assert re.fullmatch(r"\[2/3\] coded: failed, - lines, \d+ s \(download_failed: Download failed: HTTP 503\)",
                        said[3])
    long = {"status": "failed", "lines": None, "seconds": 1.0, "error": None, "message": "x\n" * 300}
    assert ts._outcome(long).endswith("...)") and len(ts._outcome(long)) < 240  # on one line, shortened


def test_run_failed_and_status(monkeypatch, tmp_path, capsys):
    """run --failed searches again only the clusters whose capture.json says failed (the others kept, a cluster
    never searched left out); --status failed,no_lines those of the statuses, captured or not; --max-clusters
    then counts those; --ids @FILE the ids of a file (a BOM, a comment and a blank line skipped); wrong values
    refused."""
    import cache
    cache_dir = tmp_path / "cache"
    cache.check_layout(str(cache_dir))
    log = stand_in(monkeypatch, tmp_path, fail="c2", no_lines="c3")
    out = tmp_path / "out"
    clusters = [{"id": f"c{k}", "country": "PL", "source": "geoportal", "national": True,
                 "options": f"--lat 50 --lon {20 + k}", "known": [], "lines": []} for k in range(1, 5)]
    out.mkdir()
    (out / "clusters.json").write_text(json.dumps({"clusters": clusters}), encoding="utf-8")
    base =["run", "--out", str(out), "--cache", str(cache_dir)]

    def searched():
        return [r["name"] for r in records(log)]

    def states():
        return {f"c{k}": (out / f"c{k}" / "capture.json").read_text(encoding="utf-8")
                for k in range(1, 5) if (out / f"c{k}" / "capture.json").exists()}

    assert ts.main([*base, "--ids", "c1", "c2", "c3"]) == 1
    assert searched() == ["c1", "c2", "c3"]
    first = states()
    assert [json.loads(first[f"c{k}"])["status"] for k in (1, 2, 3)] == ["done", "failed", "no_lines"]
    capsys.readouterr()

    assert ts.main([*base, "--failed"]) == 1  # c2 failing again; c1 and c3 kept, c4 (never searched) left out
    printed = capsys.readouterr().out
    assert searched() == ["c1", "c2", "c3", "c2"]
    assert "1 of 4 searches with the status failed: searched again" in printed
    assert "\n1 searches: 0 done, 0 no_lines, 1 failed\n" in printed
    assert {k: v for k, v in states().items() if k != "c2"} == {k: v for k, v in first.items() if k != "c2"}

    assert ts.main([*base, "--status", "failed,no_lines"]) == 1  # c3 searched again though captured
    printed = capsys.readouterr().out
    assert searched()[4:] == ["c2", "c3"] and "2 of 4 searches with the status failed or no_lines" in printed
    assert states()["c1"] == first["c1"]

    ids = tmp_path / "ids.txt"
    ids.write_bytes("﻿# the clusters to search\nc4\n\n c1 \n".encode("utf-8"))
    assert ts.ids_of(["c2", f"@{ids}", "c4"]) == ["c2", "c4", "c1"]
    assert ts.main([*base, "--ids", f"@{ids}"]) == 0  # c4 searched, c1 captured already
    assert searched()[6:] == ["c4"] and "c1: captured already (done)" in capsys.readouterr().out

    assert ts.main([*base, "--status", "done", "--max-clusters", "1"]) == 0  # c1 and c4 done: c1 first by id
    assert searched()[7:] == ["c1"] and "1 of 4 searches with the status done" in capsys.readouterr().out

    assert ts.main([*base, "--status", "done", "bogus"]) == 1 and "error: --status bogus" in capsys.readouterr().err
    empty = tmp_path / "empty.txt"
    empty.write_text("# nothing\n", encoding="utf-8")
    assert ts.main([*base, "--ids", f"@{empty}"]) == 1 and "no cluster ids" in capsys.readouterr().err
    assert ts.main([*base, "--ids", f"@{tmp_path / 'missing.txt'}"]) == 1
    with pytest.raises(SystemExit):  # --again, --failed and --status exclude each other
        ts.main([*base, "--failed", "--again"])
    assert searched()[8:] == []
    assert ts.statuses_of(["failed", "no_lines,failed"]) == ("failed", "no_lines")


def test_split_options_and_status():
    assert ts.split_options(r'--elevation-file C:\data\a b.tif --name "two words"') == \
        ["--elevation-file", r"C:\data\a", "b.tif", "--name", "two words"]
    assert ts.split_options(r'--elevation-file "C:\data\a b.tif"') == ["--elevation-file", r"C:\data\a b.tif"]
    assert ts.status_of(0, {"complete": True}) == "done"
    assert ts.status_of(1, {"complete": True, "error": "no_lines"}) == "no_lines"
    assert ts.status_of(1, {"complete": True, "error": "no_steep_terrain"}) == "no_lines"
    assert ts.status_of(1, {"complete": False, "error": "no_source"}) == "failed"
    assert ts.status_of(None, None) == "failed"


GRID_KEYS = {"crs", "left", "top", "res", "shape", "params", "nmpt", "obstacles", "model", "rigging",
             "slope_threshold", "fall", "layer_meta", "source", "area_wgs84"}
LINE_KEYS = {"a1": (np.float64, 2), "a2": (np.float64, 2), "length": (np.float64, 1), "clearance": (np.float64, 1),
             "clearance_nmpt": (np.float64, 1), "over": (np.bool_, 1), "rep": (np.bool_, 1), "group": (np.int64, 1)}


def check_capture(folder, rows_cols=None, model="formula"):
    """The capture's files with the contract's keys, dtypes and shapes; returns (grid, lines)."""
    capture = folder / "capture"
    grid = json.loads((capture / "grid.json").read_text(encoding="utf-8"))
    assert GRID_KEYS <= set(grid)
    shape = tuple(grid["shape"])
    assert len(shape) == 2 and (rows_cols is None or shape == rows_cols)
    south, west, north, east = grid["area_wgs84"]
    assert south < north and west < east
    assert grid["params"]["slope_threshold"] == grid["slope_threshold"] and grid["model"] == model
    assert grid["params"]["model"] == model
    with np.load(capture / "grids.npz") as grids:
        assert grids["elevation"].dtype == np.float32 and grids["elevation"].shape == shape
        assert grids["mask"].dtype == np.uint8 and grids["mask"].shape == shape and grids["mask"].any()
        for name in set(grids.files) - {"elevation", "mask"}:
            assert name in ("surface", "filled", "joined", "water", "covered"), name
            assert grids[name].dtype == (np.float32 if name == "surface" else np.uint8) and grids[name].shape == shape
        surface = "surface" in grids.files
    anchors = np.load(capture / "anchors.npy")
    assert anchors.dtype == np.int64 and anchors.ndim == 2 and anchors.shape[1] == 2 and len(anchors) > 1
    assert (anchors >= 0).all() and (anchors < np.array(shape)).all()
    with np.load(capture / "lines.npz") as data:
        lines = {k: data[k] for k in data.files}
    n = len(lines["length"])
    for key, (dtype, ndim) in LINE_KEYS.items():
        assert lines[key].dtype == dtype and lines[key].shape == ((n, 2) if ndim == 2 else (n,)), key
    return grid, lines, surface


def same_capture(a, b):
    """Two captures of one search alike: known.json byte for byte, grid.json, every array of grids.npz, anchors.npy
    and lines.npz, capture.json but for its times and the saved run's name."""
    assert (a / "known.json").read_bytes() == (b / "known.json").read_bytes()
    grids = [json.loads((x / "capture" / "grid.json").read_text(encoding="utf-8")) for x in (a, b)]
    assert grids[0] == grids[1]
    for name in ("grids.npz", "lines.npz"):
        with np.load(a / "capture" / name) as x, np.load(b / "capture" / name) as y:
            assert sorted(x.files) == sorted(y.files), name
            for key in x.files:
                assert x[key].dtype == y[key].dtype and x[key].shape == y[key].shape, (name, key)
                assert np.array_equal(x[key], y[key], equal_nan=x[key].dtype.kind == "f"), (name, key)
    assert np.array_equal(np.load(a / "capture" / "anchors.npy"), np.load(b / "capture" / "anchors.npy"))
    states = [json.loads((x / "capture.json").read_text(encoding="utf-8")) for x in (a, b)]
    assert (states[0]["run"] is None) == (states[1]["run"] is None)
    kept = [{k: v for k, v in s.items() if k not in ("seconds", "finished", "run")} for s in states]
    assert kept[0] == kept[1]


@pytest.mark.parametrize("model", ["formula", "sag"])
def test_run_zabi_kon_clip(tmp_path, model):
    """run --place on the Żabi Koń clip offline (no cache link): a search with lines and one without (status
    no_lines, every array of lines.npz empty), known.json back as KnownLines, a second pass skips both; with
    the formula and with the sag model (the analysis then evaluates with the run's envelope table: the found
    lines' clearances given back exactly); with the formula, run --parallel 2 gives the same captures."""
    known = [line("zk1", 0, 0, 60, 0), line("zk2", 0, 20, 45, 30, lt="m")]
    known_file = tmp_path / "known.json"
    known_file.write_text(json.dumps([dataclasses.asdict(k) for k in known]), encoding="utf-8")
    clip = (f'--elevation-file "{os.path.join(DATA, "zabi_kon_nmt.tif")}" '
            f'--surface-file "{os.path.join(DATA, "zabi_kon_nmpt.tif")}" '
            "--northing 254608 --easting 553966 --radius 290 --slope-threshold 45 --water off --fill-gaps off"
            + (" --model sag" if model == "sag" else ""))
    out = tmp_path / "out"
    command = [sys.executable, os.path.join("tools", "truth_study.py"), "run", "--out", str(out),
               "--place", f"zk={clip}", "--place", f"zk-none={clip} --min-length 990 --max-length 1000",
               "--known", str(known_file), "--no-cache-link"]
    env = {**os.environ, **OFFLINE_ENV}
    result = subprocess.run(command, cwd=REPO, env=env, capture_output=True, text=True, encoding="utf-8",
                            timeout=900)
    logs = "".join((out / p / "output.log").read_text(encoding="utf-8") for p in ("zk", "zk-none")
                   if (out / p / "output.log").exists())
    assert result.returncode == 0, result.stdout + result.stderr + logs
    assert "2 searches: 1 done, 1 no_lines, 0 failed" in result.stdout

    state = json.loads((out / "zk" / "capture.json").read_text(encoding="utf-8"))
    assert state["status"] == "done" and state["options"] == clip and state["source"] == "files"
    assert {"seconds", "options"} <= set(state) and state["returncode"] == 0
    grid, lines, surface = check_capture(out / "zk", model=model)
    assert surface and grid["nmpt"] and grid["source"] == "files"
    import helpers
    assert grid["fall"] == (grid["rigging"]["fall_zone"] if model == "sag" else helpers.fall_allowance(None))
    assert grid["radius"] == 290
    n = len(lines["length"])
    assert n > 100 and n == state["lines"]
    assert (lines["group"] >= 0).all() and lines["rep"].sum() == len(np.unique(lines["group"]))
    assert len(np.unique(lines["group"][lines["rep"]])) == lines["rep"].sum()
    assert np.allclose(lines["a1"].mean(axis=0), [50.156, 19.756], atol=0.01)
    assert np.isfinite(lines["clearance"]).all() and np.isfinite(lines["clearance_nmpt"]).any()
    assert lines["a1_xy"].shape == (n, 2) and lines["angle1"].shape == (n,)  # beyond the contract: the extras
    back = [sd.KnownLine.from_dict(d) for d in json.loads((out / "zk" / "known.json").read_text(encoding="utf-8"))]
    assert back == known
    runs = list((out / "data" / "runs").glob("*/run.json"))  # the saved runs of every place: one data folder
    assert len(runs) == 1 and state["run"] == "data/runs/" + runs[0].parent.name
    assert not any((runs[0].parent / name).exists() for name in ts.RUN_FILES)  # run.json alone kept
    assert (out / "data" / "runs" / "runs.js").exists()
    assert not (out / "zk" / "data").exists() and (out / "data" / "runs" / "_viewer").is_dir()
    assert (out / "data" / "cache").is_dir() and not _is_link(out / "data" / "cache")  # --no-cache-link: its own
    assert not os.listdir(out / "data" / "work")  # also the one findaline.py leaves after no lines (Windows)
    import studylib
    anchors = {tuple(p) for p in np.load(out / "zk" / "capture" / "anchors.npy").tolist()}
    to_grid = Transformer.from_crs("EPSG:4326", grid["crs"], always_xy=True)
    for latlon_, xy in ((lines["a1"], lines["a1_xy"]), (lines["a2"], lines["a2_xy"])):
        lat, lon = latlon_[:, 0], latlon_[:, 1]
        x, y = (np.asarray(v) for v in to_grid.transform(lon, lat))
        exact = np.column_stack([(grid["top"] - y) / grid["res"] - 0.5, (x - grid["left"]) / grid["res"] - 0.5])
        assert np.abs(exact - np.rint(exact)).max() < 1e-6  # pixel centres to a micrometre: 7 decimals leave ~1 cm
        assert np.abs(np.column_stack([x, y]) - xy).max() < 1e-6  # the points of the grid's CRS columns
        pixels = [studylib.to_pixel(grid, a, b) for a, b in latlon_.tolist()]
        assert pixels == [tuple(p) for p in np.rint(exact).astype(int).tolist()]
        assert set(pixels) <= anchors  # each found line's anchors are step 2's anchors
        back = Transformer.from_crs(grid["crs"], "EPSG:4326", always_xy=True).transform(xy[:, 0], xy[:, 1])
        assert np.array_equal(lon, back[0]) and np.array_equal(lat, back[1])  # float64 as the table holds them

    state = json.loads((out / "zk-none" / "capture.json").read_text(encoding="utf-8"))
    assert state["status"] == "no_lines" and state["error"] == "no_lines" and state["lines"] == 0
    assert state["run"] is None  # no run saved without lines
    assert state["message"].startswith("No lines found")  # the SearchError's text, also on the child's stderr
    assert state["message"] in (out / "zk-none" / "output.log").read_text(encoding="utf-8").split(ts.STDERR_MARK)[1]
    grid_none, lines_none, _ = check_capture(out / "zk-none", tuple(grid["shape"]), model)
    assert all(len(v) == 0 for v in lines_none.values())

    if model == "formula":  # both places at once (--parallel 2): the same captures as one after another
        out2 = tmp_path / "out-parallel"
        both = subprocess.run([*command[:4], str(out2), *command[5:], "--parallel", "2"], cwd=REPO, env=env,
                              capture_output=True, text=True, encoding="utf-8", timeout=900)
        assert both.returncode == 0, both.stdout + both.stderr
        assert "2 searches: 1 done, 1 no_lines, 0 failed" in both.stdout
        assert "[0/2 done] zk: searching" in both.stdout and "[0/2 done] zk-none: searching" in both.stdout
        for place in ("zk", "zk-none"):
            same_capture(out / place, out2 / place)
        assert len(list((out2 / "data" / "runs").glob("*/run.json"))) == 1 and not os.listdir(out2 / "data" / "work")

    stamp = os.path.getmtime(out / "zk" / "capture.json")
    again = subprocess.run(command, cwd=REPO, env=env, capture_output=True, text=True, encoding="utf-8", timeout=300)
    assert again.returncode == 0, again.stdout + again.stderr
    assert again.stdout.count("captured already") == 2 and os.path.getmtime(out / "zk" / "capture.json") == stamp

    # analyse --profiles on the saved run: a known line copied from a found one (the table's float64 anchors)
    # is matched and production's profile agrees; a made-up line at the centre is a miss, its profile agreeing too
    rep = int(np.flatnonzero(lines["rep"])[0])
    copied = dataclasses.replace(known[0], id="copy", a=tuple(lines["a1"][rep].tolist()),
                                 b=tuple(lines["a2"][rep].tolist()), stated_m=float(lines["length"][rep]),
                                 geodesic_m=float(lines["length"][rep]), flags=())
    centre_lat, centre_lon = grid["centre"]
    flat = dataclasses.replace(known[0], id="made-up", a=(centre_lat, centre_lon), b=(centre_lat, centre_lon + 0.0005),
                               stated_m=36.0, geodesic_m=35.7, flags=())
    (out / "zk" / "known.json").write_text(json.dumps([dataclasses.asdict(k) for k in (copied, flat)]),
                                           encoding="utf-8")
    analysed = subprocess.run([sys.executable, os.path.join("tools", "truth_study.py"), "analyse", str(out),
                               "--profiles", "--cluster", "zk", "--cache", str(tmp_path / "unused-cache")],
                              cwd=REPO, env=env, capture_output=True, text=True, encoding="utf-8", timeout=600)
    assert analysed.returncode == 0, analysed.stdout + analysed.stderr
    result = json.loads((out / "zk" / "analysis.json").read_text(encoding="utf-8"))
    records = {r["id"]: r for r in result["records"]}
    assert result["matched"] == 1 and records["copy"]["outcome"] == "matched" and records["copy"]["match"]["d"] == \
        [pytest.approx(0, abs=1e-6)] * 2
    assert records["copy"]["profile"] == {**records["copy"]["profile"], "production": True, "grid": True,
                                          "agree": True}
    assert records["made-up"]["outcome"] == "missed" and "profile" in records["made-up"]
    assert "error" not in records["made-up"]["profile"] and records["made-up"]["profile"]["agree"]
    assert not (tmp_path / "unused-cache").exists() and not _is_link(out / "data" / "cache")  # its own cache used
    assert result["seconds"] > 0 and result["model"] == model
    import truth_analysis as ta
    c = ta.load_capture(out / "zk")  # the analysis's evaluation: the search's own clearance, under either model
    assert (c.sag_table is None) == (model == "formula") and c.fall == grid["fall"]
    for k in np.linspace(0, len(c.found) - 1, 40).astype(int):
        lo, hi = sorted([studylib.to_pixel(grid, *c.found.a1[k]), studylib.to_pixel(grid, *c.found.a2[k])])
        assert ta._evaluate(c, lo, hi)[3] == c.found.clearance[k]


def test_child_reports_its_error(tmp_path):
    """The real search-child at the Żabi Koń place offline, two impossible searches: a source that cannot serve
    it (Slovakia's tiles without a copy set up: a SearchError "no_source" before any download) gives capture.json
    the error's code and text, the text also the last line of output.log (the child's stderr after its stdout,
    under the marker) and in the progress line; an option findaline.py refuses (argparse's exit 2, no text of the
    child's own) gives the last line of the child's stderr as the message."""
    mirror = tmp_path / "no-mirror"  # FINDALINE_MIRROR without the Slovak tiles
    mirror.mkdir()
    where = "--northing 254608 --easting 553966 --radius 290"
    out = tmp_path / "out"
    command = [sys.executable, os.path.join("tools", "truth_study.py"), "run", "--out", str(out),
               "--place", f"zk-source={where} --source slovakia", "--place", f"zk-option={where} --no-such-option",
               "--no-cache-link"]
    env = {**os.environ, **OFFLINE_ENV, "FINDALINE_MIRROR": str(mirror)}
    result = subprocess.run(command, cwd=REPO, env=env, capture_output=True, text=True, encoding="utf-8",
                            timeout=600)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "2 searches: 0 done, 0 no_lines, 2 failed" in result.stdout

    source = json.loads((out / "zk-source" / "capture.json").read_text(encoding="utf-8"))
    assert (source["status"], source["error"], source["returncode"]) == ("failed", "no_source", 1)
    assert "no copy of the tiles is set up" in source["message"] and source["run"] is None
    stdout, stderr = (out / "zk-source" / "output.log").read_text(encoding="utf-8").split(f"\n{ts.STDERR_MARK}\n")
    assert stdout.rstrip().splitlines()[-1].startswith("truth_study: exit 1, no lines captured into")
    assert stderr.rstrip().splitlines()[-1] == source["message"]
    assert re.search(r"\[1/2\] zk-source: failed, - lines, \d+ s \(no_source: .*no copy of the tiles is set up",
                     result.stdout)
    assert json.loads((out / "zk-source" / "capture" / "result.json").read_text(encoding="utf-8"))["error"] == \
        "no_source"

    option = json.loads((out / "zk-option" / "capture.json").read_text(encoding="utf-8"))
    assert (option["status"], option["error"], option["returncode"]) == ("failed", None, 1)
    assert option["message"].endswith("error: unrecognized arguments: --no-such-option")
    log = (out / "zk-option" / "output.log").read_text(encoding="utf-8")
    assert "truth_study: findaline.py ended with exit code 2" in log.split(ts.STDERR_MARK)[0]
    assert log.rstrip().endswith(option["message"])
    assert not os.listdir(out / "data" / "work")
