"""tools/truth_study.py: the clusters of known lines (the link, the cap's bisection, the radius and length
rules, midlines clustered with highlines), the sources chosen offline, the places against a copy of
tests/regression.json, the delegation to tools/truth_analysis.py, the one data folder of a run (its cache
linked once, unlinked afterwards, also after an interruption; a cluster searched again keeps only its new
run), cluster --extra, and a run of the Żabi Koń clip offline with the formula and with the sag model (a
search with lines, one without, a resumed pass) with the capture's files as the analysis reads them (the found
anchors back on their pixels, their clearances evaluated again; analyse --profiles on the saved run).
Synthetic lines only: invented ids and coordinates (no SlackMap data in the repository)."""

import gzip

import dataclasses
import json
import math
import os
import random
import subprocess
import sys
import types
from decimal import Decimal

import numpy as np
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


def test_run_shares_one_data_folder(monkeypatch, tmp_path):
    """run: every search in <out>/data, its cache/ linked once and unlinked at the end, also after an
    interruption (Ctrl+C in the second search); capture.json names each saved run relative to <out>; a cluster
    searched again keeps only its new run, the work folders the searches left are removed. The child is a stand-in
    that saves a run and a complete capture."""
    cache_dir = tmp_path / "cache"
    (cache_dir / "layer").mkdir(parents=True)
    (cache_dir / "layer" / "tile.txt").write_text("tile", encoding="utf-8")
    out = tmp_path / "out"
    seen, stop, counter = [], {"at": None}, iter(range(1, 100))

    def child(command, **kwargs):
        capture, data = command[command.index("--out") + 1], command[command.index("--data-dir") + 1]
        name = os.path.basename(os.path.dirname(capture))
        seen.append((name, data, _is_link(os.path.join(data, "cache")),
                     os.path.exists(os.path.join(data, "cache", "layer", "tile.txt"))))
        if name == stop["at"]:
            raise KeyboardInterrupt
        run_dir = os.path.join(data, "runs", f"2026-11-08_{name}_{next(counter)}")
        os.makedirs(run_dir)
        os.makedirs(os.path.join(data, "work", f"left-by-{name}", "grids"))  # as findaline.py leaves it on Windows
        with open(os.path.join(run_dir, "run.json"), "w", encoding="utf-8") as f:
            json.dump({"id": os.path.basename(run_dir)}, f)
        os.makedirs(capture)
        with open(os.path.join(capture, "result.json"), "w", encoding="utf-8") as f:
            json.dump({"complete": True, "lines": 3, "error": None, "run": run_dir}, f)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(ts.subprocess, "run", child)
    items = [{"id": name, "options": "--lat 50 --lon 20", "known": [{"id": f"{name}-1"}]} for name in ("c1", "c2")]
    quiet = lambda text: None  # noqa: E731
    found = ts.run(str(out), items, str(cache_dir), say=quiet)
    data = str(out / "data")
    assert seen == [("c1", data, True, True), ("c2", data, True, True)]
    assert not os.path.lexists(out / "data" / "cache") and (cache_dir / "layer" / "tile.txt").exists()
    assert [found[n]["status"] for n in ("c1", "c2")] == ["done", "done"]
    assert found["c1"]["run"] == "data/runs/2026-11-08_c1_1" and (out / found["c1"]["run"] / "run.json").exists()
    assert not (out / "c1" / "data").exists()  # no data folder per cluster
    assert os.listdir(out / "data" / "work") == []  # the work folders the searches left removed

    seen.clear()
    ts.run(str(out), items, str(cache_dir), say=quiet)  # captured already: nothing searched, nothing linked
    assert seen == [] and not os.path.lexists(out / "data" / "cache")

    found = ts.run(str(out), items[:1], str(cache_dir), again=True, say=quiet)  # c1 again: its old run removed
    assert found["c1"]["run"] == "data/runs/2026-11-08_c1_3" and seen[-1][0] == "c1"
    assert sorted(os.listdir(out / "data" / "runs")) == ["2026-11-08_c1_3", "2026-11-08_c2_2"]

    (out / "data" / "work" / "another").mkdir()  # not left by a search of this run: kept
    stop["at"] = "c2"
    with pytest.raises(KeyboardInterrupt):
        ts.run(str(out), items, str(cache_dir), again=True, say=quiet)
    assert seen[-1] == ("c2", data, True, True)  # the link was there while the search ran
    assert not os.path.lexists(out / "data" / "cache") and (cache_dir / "layer" / "tile.txt").exists()
    assert not (out / "c2" / "capture.json").exists()  # an interrupted cluster is searched on the next pass
    assert ts.captured(str(out / "c2"), items[1]["options"], ["c2-1"]) is None
    assert os.listdir(out / "data" / "work") == ["another"]


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


@pytest.mark.parametrize("model", ["formula", "sag"])
def test_run_zabi_kon_clip(tmp_path, model):
    """run --place on the Żabi Koń clip offline (no cache link): a search with lines and one without (status
    no_lines, every array of lines.npz empty), known.json back as KnownLines, a second pass skips both; with
    the formula and with the sag model (the analysis then evaluates with the run's envelope table: the found
    lines' clearances given back exactly)."""
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
    grid_none, lines_none, _ = check_capture(out / "zk-none", tuple(grid["shape"]), model)
    assert all(len(v) == 0 for v in lines_none.values())

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
