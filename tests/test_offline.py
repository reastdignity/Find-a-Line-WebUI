"""Searches on local files only, no network (any request goes to a closed port).

- A synthetic canyon: two plateaus 40 m above a 50 m wide floor, with a block of
  "trees" taller than the plateaus in its northern third.
- A 600 x 600 m clip of Żabi Koń (tests/data, see make_fixture.py) with known results.
"""

import collections
import csv
import glob
import json
import os
import re
import subprocess
import sys

import numpy as np
import pytest
import rasterio as rio
from rasterio.transform import from_origin

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(REPO, "tests", "data")
OFFLINE_ENV = {"HTTP_PROXY": "http://127.0.0.1:9", "HTTPS_PROXY": "http://127.0.0.1:9", "NO_PROXY": "",
               "FINDALINE_PROGRESS": "text"}


def run_search(tmp_path, *args) -> tuple:
    """Run findaline.py offline; return (output, rows of lines.csv)."""
    env = {**os.environ, **OFFLINE_ENV}
    result = subprocess.run(
        [sys.executable, "findaline.py", *args, "--water", "off", "--fill-gaps", "off", "--no-plot", "--yes",
         "--data-dir", str(tmp_path)],
        cwd=REPO, env=env, capture_output=True, text=True, encoding="utf-8", timeout=600)
    assert result.returncode == 0, result.stdout + result.stderr
    runs = glob.glob(str(tmp_path / "runs" / "*" / "lines.csv"))
    assert len(runs) == 1, runs
    with open(runs[0], encoding="utf-8-sig") as f:
        return result.stdout, list(csv.DictReader(f))


def write_raster(path, band, left, top):
    with rio.open(path, "w", driver="GTiff", width=band.shape[1], height=band.shape[0], count=1,
                  dtype="float32", crs="EPSG:2180", transform=from_origin(left, top, 1, 1)) as dst:
        dst.write(band.astype(np.float32), 1)


def test_synthetic_canyon(tmp_path):
    left, top, size = 500000, 300000, 300
    terrain = np.full((size, size), 240.0)
    terrain[:, 120:170] = 200.0                 # canyon floor, columns 120-169
    surface = terrain.copy()
    surface[:100, 120:170] = 245.0              # trees above the plateaus in the north
    write_raster(tmp_path / "nmt.tif", terrain, left, top)
    write_raster(tmp_path / "nmpt.tif", surface, left, top)

    output, rows = run_search(tmp_path, "--elevation-file", str(tmp_path / "nmt.tif"),
                              "--surface-file", str(tmp_path / "nmpt.tif"),
                              "--northing", str(top - size / 2), "--easting", str(left + size / 2),
                              "--radius", "140", "--resolution", "1", "--min-length", "20", "--max-length", "200")
    assert rows, output
    for row in rows:
        east = sorted([float(row["anchor1_easting"]), float(row["anchor2_easting"])])
        assert east[0] - left < 120 and east[1] - left >= 170, row   # one anchor on each rim
        assert float(row["length_m"]) >= 50, row
        assert float(row["clearance_m"]) >= 25, row                   # 40 m deep, minus fall zone and sag
    shortest = min(float(r["length_m"]) for r in rows)
    assert shortest == pytest.approx(51, abs=0.5)                     # pixel centres 119.5 and 170.5
    north = [r for r in rows if max(float(r["anchor1_northing"]), float(r["anchor2_northing"])) > top - 90]
    south = [r for r in rows if max(float(r["anchor1_northing"]), float(r["anchor2_northing"])) < top - 110]
    assert north and all(r["over_trees_buildings"] == "True" for r in north)
    assert south and all(r["over_trees_buildings"] == "False" for r in south)


def test_rock_rims_are_no_obstacles(tmp_path):
    """The canyon with its walls inside pixels 120 and 169, its surface model made as the services
    make theirs (the highest point of each pixel): the rim stands in the first pixel of every line,
    which no longer marks a line (obstacles.py), while the trees on the floor of the northern rows
    still do. run.json records the rule; a profile computed again uses its run's rule, for a run
    from before it the surface model as it is."""
    import search
    left, top, size = 500000, 300000, 300
    ground = lambda x: np.where((x >= 120.35) & (x < 169.65), 200.0, 240.0)  # noqa: E731
    terrain = np.tile(ground(np.arange(size) + 0.5), (size, 1))
    surface = np.tile(ground((np.arange(size * 10) + 0.5) / 10).reshape(size, 10).max(axis=1), (size, 1))
    assert surface[0, 120] - terrain[0, 120] == 40 and surface[0, 169] - terrain[0, 169] == 40
    surface[:100, 125:165] = 245.0  # trees on the floor in the north, away from the walls
    write_raster(tmp_path / "nmt.tif", terrain, left, top)
    write_raster(tmp_path / "nmpt.tif", surface, left, top)

    output, rows = run_search(tmp_path, "--elevation-file", str(tmp_path / "nmt.tif"),
                              "--surface-file", str(tmp_path / "nmpt.tif"),
                              "--northing", str(top - size / 2), "--easting", str(left + size / 2),
                              "--radius", "140", "--resolution", "1", "--min-length", "20", "--max-length", "200")
    # Both anchors in the north: the line crosses the trees (a steep line from row 89 may pass below them)
    north = [r for r in rows if min(float(r["anchor1_northing"]), float(r["anchor2_northing"])) > top - 60]
    south = [r for r in rows if max(float(r["anchor1_northing"]), float(r["anchor2_northing"])) < top - 110]
    assert north and all(r["over_trees_buildings"] == "True" for r in north)
    assert south and all(r["over_trees_buildings"] == "False" for r in south)

    meta = json.load(open(glob.glob(str(tmp_path / "runs" / "*" / "run.json"))[0], encoding="utf-8"))
    assert meta["params"]["obstacles"] == {"radius": 2, "min_height": 1.0}
    line = next(r for r in south if r["anchor1_northing"] == r["anchor2_northing"])  # its first pixel 1 m out
    anchors = [(float(line[f"anchor{k}_lat"]), float(line[f"anchor{k}_lon"])) for k in (1, 2)]
    for rule, expected in ((meta["params"]["obstacles"], float(line["clearance_nmpt_m"])), (None, -6.15)):
        meta["params"]["obstacles"] = rule
        paths = search.Paths(str(tmp_path), str(tmp_path / f"profile-work-{rule is None}"))
        os.makedirs(paths.work, exist_ok=True)
        profile = search.profile_of_line(meta, paths, *anchors)
        assert profile["min_nmpt"][1] == pytest.approx(expected, abs=0.01), rule


# Known results of the Żabi Koń clip (update together with a deliberate change)
ZABI_KON = {"anchors": 11609, "open": 620, "checked": 11313, "lines": 1301, "spots": 43}


def test_zabi_kon_clip(tmp_path):
    output, rows = run_search(tmp_path, "--elevation-file", os.path.join(DATA, "zabi_kon_nmt.tif"),
                              "--surface-file", os.path.join(DATA, "zabi_kon_nmpt.tif"),
                              "--northing", "254608", "--easting", "553966", "--radius", "290")
    found = {
        "anchors": int(re.search(r"Found (\d+) potential anchors", output).group(1)),
        "open": int(re.search(r"Anchors with an open direction: (\d+)", output).group(1)),
        "checked": int(re.search(r"Checked pixel by pixel: (\d+)", output).group(1)),
        "lines": len(rows),
        "spots": sum(r["representative"] == "True" for r in rows),
    }
    assert found == ZABI_KON, output
    assert "[Download]" not in output  # nothing fetched (and requests would fail anyway)
    # Local files: no credits of ours, ATTRIBUTION.txt says to credit the files' own sources
    folder = os.path.dirname(glob.glob(str(tmp_path / "runs" / "*" / "run.json"))[0])
    read = lambda name: (tmp_path / "runs" / os.path.basename(folder) / name).read_text(encoding="utf-8")  # noqa: E731
    assert json.loads(read("run.json"))["attribution"] == []
    assert "zabi_kon_nmt.tif" in read("ATTRIBUTION.txt") and "as their own licences require" in read("ATTRIBUTION.txt")
    assert json.loads(read("data.js").partition(" = ")[2].rstrip().rstrip(";"))["attribution"] == []


def _lines(rows):
    return {tuple(sorted([(r["anchor1_easting"], r["anchor1_northing"]), (r["anchor2_easting"], r["anchor2_northing"])]))
            for r in rows}


def test_height_limits_filter_the_lines(tmp_path):
    """--min-height/--min-mean-height/--min-high-share keep exactly the lines of the search
    without them that reach the limits, with the same values (groups may differ)."""
    common = ["--elevation-file", os.path.join(DATA, "zabi_kon_nmt.tif"), "--northing", "254608",
              "--easting", "553966", "--radius", "290", "--high-above", "15"]
    _, everything = run_search(tmp_path / "all", *common)
    output, high = run_search(tmp_path / "high", *common, "--min-height", "30.3", "--min-mean-height", "20.3",
                              "--min-high-share", "60.3")
    line_values = lambda r: {k: v for k, v in r.items() if k not in ("group", "representative", "group_size")}
    expected = [line_values(r) for r in everything if float(r["height_max_m"]) >= 30.3
                and float(r["height_mean_m"]) >= 20.3 and float(r["high_pct"]) >= 60.3]
    assert 0 < len(expected) < len(everything) / 2
    key = lambda r: (r["anchor1_easting"], r["anchor1_northing"], r["anchor2_easting"], r["anchor2_northing"])
    assert sorted(map(line_values, high), key=key) == sorted(expected, key=key)
    left_out = int(re.search(r"Left out by the line limits \(.*\): (\d+)", output).group(1))
    assert left_out == len(everything) - len(high)
    # The wall angle: pairs are dropped before their pixels are checked, with the same result
    # (lines.csv rounds angles to 0.1°: lines within 0.05° of the limit may go either way)
    _, straight = run_search(tmp_path / "straight", *common, "--max-wall-angle", "40")
    angle = lambda r: max(float(r["anchor1_wall_angle"]), float(r["anchor2_wall_angle"]))
    clear = lambda rows: sorted((line_values(r) for r in rows if abs(angle(r) - 40) > 0.05), key=key)
    expected = [r for r in everything if angle(r) <= 40]
    assert 0 < len(expected) < len(everything)
    assert clear(straight) == clear(expected) and all(angle(r) <= 40.05 for r in straight)
    # Prominence and drop: anchors are left out before the pairs (one prominent anchor is enough
    # for --min-prominence, both must reach --min-prominence-both and --min-drop)
    _, standing = run_search(tmp_path / "standing", *common, "--min-prominence", "3.03", "--min-drop", "35.03")
    value = lambda r, k: float(r[k]) if r[k] else float("nan")
    expected = [line_values(r) for r in everything
                if max(value(r, "anchor1_prominence_m"), value(r, "anchor2_prominence_m")) >= 3.03
                and min(value(r, "anchor1_drop_m"), value(r, "anchor2_drop_m")) >= 35.03]
    assert 0 < len(expected) < len(everything) / 2
    assert sorted(map(line_values, standing), key=key) == sorted(expected, key=key)
    _, both = run_search(tmp_path / "both", *common, "--min-prominence-both", "0.53")
    expected = [line_values(r) for r in everything
                if min(value(r, "anchor1_prominence_m"), value(r, "anchor2_prominence_m")) >= 0.53]
    assert 0 < len(expected) < len(everything)
    assert sorted(map(line_values, both), key=key) == sorted(expected, key=key)


def _search_here(tmp_path, monkeypatch, **values) -> tuple:
    """A search in this process (offline, the lines not saved): (plan.funnel, the lines'
    LineTable with its unrounded columns, the printed texts)."""
    for key, v in OFFLINE_ENV.items():
        monkeypatch.setenv(key, v)
    import search
    from params import SearchParams
    texts = []
    params = SearchParams(water="off", fill_gaps="off", **values)
    plan = search.plan_search(params, search.Paths(str(tmp_path), str(tmp_path / "work")),
                              lambda kind, text: texts.append(text))
    lines, _ = search.search_lines(plan)
    return plan.funnel, lines.results, texts


def _sorted_columns(table) -> dict:
    """The value columns of a LineTable (and the anchors' coordinates), the lines in the order of
    their anchors' coordinates."""
    from helpers import LINE_VALUES
    c = table.columns
    order = np.lexsort((c["a2_xy"][:, 1], c["a2_xy"][:, 0], c["a1_xy"][:, 1], c["a1_xy"][:, 0]))
    return {name: c[name][order] for name in (*LINE_VALUES, "a1_xy", "a2_xy")}


def test_elevation_band_filters_the_lines(tmp_path, monkeypatch):
    """--min-elevation/--max-elevation keep exactly the lines of the search without them whose
    anchors both lie in the band (compared in float32, the grid's type), with the same values;
    the band leaves the anchors out before the pairs (the funnel's "anchors_kept")."""
    import search
    common = {"elevation_file": os.path.join(DATA, "zabi_kon_nmt.tif"), "northing": 254608, "easting": 553966,
              "radius": 290, "high_above": 15}
    funnel, everything, _ = _search_here(tmp_path / "all", monkeypatch, **common)
    same = lambda a, b: a.keys() == b.keys() and all(  # noqa: E731
        np.array_equal(a[k], b[k], equal_nan=True) for k in a)
    for lo, hi in ((330.333, None), (None, 340.333), (325.333, 345.333)):
        band, table, texts = _search_here(tmp_path / f"{lo}-{hi}", monkeypatch, **common,
                                          min_elevation=lo, max_elevation=hi)
        c = everything.columns
        inside = np.ones(len(everything), dtype=bool)
        for z in (c["elev_a1"], c["elev_a2"]):
            if lo is not None:
                inside &= z >= float(np.float32(lo))
            if hi is not None:
                inside &= z <= float(np.float32(hi))
        assert 0 < inside.sum() < len(everything)
        assert same(_sorted_columns(table), _sorted_columns(everything.take(np.flatnonzero(inside))))
        assert band["anchors"] == funnel["anchors"] == ZABI_KON["anchors"]
        assert band["anchors_kept"] < funnel["anchors_kept"]
        # no prominence or drop limits here: the anchors within the band are those kept
        assert f"Anchors within the elevation limits: {band['anchors_kept']}" in texts
        assert any(t.startswith("Anchor elevation: ") for t in texts)
    # A band holding every anchor changes nothing, not even the order of the lines
    wide, table, texts = _search_here(tmp_path / "wide", monkeypatch, **common, min_elevation=100,
                                      max_elevation=1000)
    assert wide == funnel and same(table.columns, everything.columns)
    assert not any(t.startswith("Anchors within") for t in texts)
    # No anchor in the band: its own error, not "not enough steep terrain"
    with pytest.raises(search.SearchError) as error:
        _search_here(tmp_path / "none", monkeypatch, **common, min_elevation=1000)
    assert error.value.code == "no_anchors_in_elevation_range"


def test_elevation_band_in_tiles(tmp_path):
    """An area with an elevation band gives the same lines in tiles as in one grid."""
    square = {"type": "Polygon", "coordinates": [[[19.7522, 50.1546], [19.7590, 50.1546], [19.7590, 50.1580],
                                                  [19.7522, 50.1580], [19.7522, 50.1546]]]}
    path = tmp_path / "square.geojson"
    path.write_text(json.dumps({"type": "Feature", "properties": {}, "geometry": square}))
    common = ["--elevation-file", os.path.join(DATA, "zabi_kon_nmt.tif"), "--area", str(path),
              "--max-length", "150", "--min-elevation", "325.333", "--max-elevation", "345.333"]
    one_out, one = run_search(tmp_path / "one", *common)
    tiled_out, tiled = run_search(tmp_path / "tiled", *common, "--tile-size", "150")
    assert "one grid" in one_out and "tiles)" in tiled_out
    assert "Anchor elevation: 325.333–345.333 m a.s.l." in one_out and "Anchors within the elevation limits" in one_out
    assert one and one == tiled  # every column, the order of the anchors too
    assert len(glob.glob(str(tmp_path / "tiled" / "runs" / "*" / "tiles" / "*.pkl.gz"))) > 1
    assert all(325.33 <= float(r[f"anchor{k}_elev_m"]) <= 345.34 for r in one for k in (1, 2))


def test_area_in_tiles(tmp_path):
    """An area computed in tiles gives exactly the lines of one grid."""
    square = {"type": "Polygon", "coordinates": [[[19.7522, 50.1546], [19.7590, 50.1546], [19.7590, 50.1580],
                                                  [19.7522, 50.1580], [19.7522, 50.1546]]]}
    path = tmp_path / "square.geojson"
    path.write_text(json.dumps({"type": "Feature", "properties": {}, "geometry": square}))
    common = ["--elevation-file", os.path.join(DATA, "zabi_kon_nmt.tif"), "--area", str(path),
              "--max-length", "150"]
    one_out, one = run_search(tmp_path / "one", *common)
    tiled_out, tiled = run_search(tmp_path / "tiled", *common, "--tile-size", "150")
    assert "one grid" in one_out and "tiles)" in tiled_out
    assert one and _lines(one) == _lines(tiled)
    assert one == tiled  # every column, the order of the anchors too (their pixels depend on it)
    tile_files = glob.glob(str(tmp_path / "tiled" / "runs" / "*" / "tiles" / "*.pkl.gz"))
    assert len(tile_files) > 1
    # The terrain of the area (hypsometry.py) from the tiles' cores: exactly that of one grid
    assert sorted(f.replace(".table.pkl.gz", "") for f in tile_files) == sorted(
        f.replace(".terrain.npz", "") for f in glob.glob(str(tmp_path / "tiled" / "runs" / "*" / "tiles" / "*.npz")))
    terrain = _terrain(tmp_path / "one")
    assert terrain["run.json"] is not None and _terrain(tmp_path / "tiled") == terrain
    # the prominence and drop of the anchors too, so their limits give one grid's lines as well
    limits = ["--min-prominence", "2", "--min-drop", "30"]
    _, one_limited = run_search(tmp_path / "one-limited", *common, *limits)
    _, tiled_limited = run_search(tmp_path / "tiled-limited", *common, "--tile-size", "150", *limits)
    assert one_limited and one_limited == tiled_limited and len(one_limited) < len(one)
    # The map of an area keeps the profiles of the lines shown for the groups, no others
    for name, rows in (("one", one), ("tiled", tiled)):
        data = glob.glob(str(tmp_path / name / "runs" / "*" / "data.js"))[0]
        lines = json.loads(open(data, encoding="utf-8").read().partition(" = ")[2].rstrip().rstrip(";"))["lines"]
        with_profile = {tuple(round(v, 7) for v in line[:4]) for line in lines if line[-1]}
        reps = {tuple(float(r[k]) for k in ("anchor1_lat", "anchor1_lon", "anchor2_lat", "anchor2_lon"))
                for r in rows if r["representative"] == "True"}
        assert with_profile == reps, name


def _script(path) -> dict:
    """The object of a run's data.js or lines.js (from its first " = {")."""
    text = open(path, encoding="utf-8").read()
    return json.loads(text[text.index(" = {") + 3:].rstrip().rstrip(";"))


ENDS = ["--end-zone", "5", "--anchor-lift", "2"]


def test_end_zone_and_lift(tmp_path):
    """--end-zone and --anchor-lift: the lines of the search without them and more, the same anchors; the
    rule printed, recorded in run.json (params, description) and in the heads of data.js and lines.js, the
    saved profiles carrying "zone" and "lift"; a profile computed again (search.profile_of_line) applies the
    run's rule and equals the saved one. Without them none of it is there."""
    import search
    common = ["--elevation-file", os.path.join(DATA, "zabi_kon_nmt.tif"),
              "--surface-file", os.path.join(DATA, "zabi_kon_nmpt.tif"),
              "--northing", "254608", "--easting", "553966", "--radius", "290", "--ortho", "never"]
    plain_out, plain = run_search(tmp_path / "plain", *common)
    ends_out, ends = run_search(tmp_path / "ends", *common, *ENDS)
    anchors = lambda out: int(re.search(r"Found (\d+) potential anchors", out).group(1))  # noqa: E731
    assert anchors(plain_out) == anchors(ends_out) == ZABI_KON["anchors"] and len(plain) == ZABI_KON["lines"]
    assert _lines(plain) < _lines(ends)  # a strict superset
    assert "Ends: no-fall zone 5 m, A-frames 2 m" in ends_out and "Ends:" not in plain_out
    folders = {name: os.path.dirname(glob.glob(str(tmp_path / name / "runs" / "*" / "run.json"))[0])
               for name in ("plain", "ends")}
    metas = {name: json.load(open(os.path.join(folder, "run.json"), encoding="utf-8")) for name, folder in folders.items()}
    assert (metas["ends"]["params"]["end_zone"], metas["ends"]["params"]["anchor_lift"]) == (5, 2)
    assert "end_zone" not in metas["plain"]["params"] and "anchor_lift" not in metas["plain"]["params"]
    assert metas["ends"]["description"].endswith(", no-fall zone 5 m at the ends, A-frames 2 m")
    ends_keys = {"end_zone": 5, "lift": 2, "ends": ["lift_needed", "lift_no_zone"]}
    for name, keys in (("plain", {}), ("ends", ends_keys)):
        for script in ("data.js", "lines.js"):
            head = _script(os.path.join(folders[name], script))
            assert {k: head[k] for k in ("end_zone", "lift", "ends") if k in head} == keys, (name, script)
            assert {len(line) for line in head["lines"]} == {25 + len(keys.get("ends", [])) + (script == "data.js")}
    # The A-frame heights each line needs, with the run's zone and without one: in all four files of the run
    # with the options (after clearance_nmpt_m; before the profile in the scripts), in none of the other's
    assert "lift_needed_m" not in plain[0] and "lift_no_zone_m" not in plain[0]
    header = open(os.path.join(folders["ends"], "lines.csv"), encoding="utf-8-sig").readline().strip().split(",")
    at = header.index("clearance_nmpt_m")
    assert header[at + 1:at + 3] == ["lift_needed_m", "lift_no_zone_m"]
    features = json.load(open(os.path.join(folders["ends"], "lines.geojson"), encoding="utf-8"))["features"]
    plain_features = json.load(open(os.path.join(folders["plain"], "lines.geojson"), encoding="utf-8"))["features"]
    assert "lift_needed_m" not in plain_features[0]["properties"]
    key = lambda values: tuple(round(float(v), 7) for v in values)  # noqa: E731
    lifts = {key(r[k] for k in ("anchor1_lat", "anchor1_lon", "anchor2_lat", "anchor2_lon")):
             (float(r["lift_needed_m"]), float(r["lift_no_zone_m"])) for r in ends}
    assert len(lifts) == len(ends) == len(features)
    assert lifts == {key((f["properties"]["anchor1_lat"], f["properties"]["anchor1_lon"], f["properties"]["anchor2_lat"],
                          f["properties"]["anchor2_lon"])): (f["properties"]["lift_needed_m"],
                                                             f["properties"]["lift_no_zone_m"]) for f in features}
    for script in ("data.js", "lines.js"):
        assert lifts == {key(line[:4]): (line[25], line[26]) for line in _script(os.path.join(folders["ends"], script))["lines"]}
    # with A-frames of 2 m the rule's clearance is 2 less the height needed (exactly so before rounding), and
    # the lines of the search without the options need none; some lines need the zone (more than 2 m without it)
    anchors_of = lambda r: key(r[k] for k in ("anchor1_lat", "anchor1_lon", "anchor2_lat", "anchor2_lon"))  # noqa: E731
    standing = set(map(anchors_of, plain))
    consistent = lambda needed, value: (abs(value - (2 - needed)) <= 0.011 if needed > 0  # noqa: E731
                                        else value >= 2 - 0.006)
    for r in ends:
        needed, no_zone, clearance = float(r["lift_needed_m"]), float(r["lift_no_zone_m"]), float(r["clearance_m"])
        assert 0 <= needed <= 2 and no_zone >= needed and consistent(needed, clearance), r
        if anchors_of(r) in standing:
            assert needed == no_zone == 0, r
    assert any(no_zone > 2 for _, no_zone in lifts.values()) and any(needed > 0 for needed, _ in lifts.values())
    for line in _script(os.path.join(folders["ends"], "data.js"))["lines"]:  # and the profiles' smallest value
        if line[-1]:
            assert consistent(line[25], line[-1]["min"][1]), line[:4]
    # the profiles the map keeps (of the spots' lines here: those of every line would be too many)
    lines = [line for line in _script(os.path.join(folders["ends"], "data.js"))["lines"] if line[-1]]
    assert lines
    assert all("zone" not in line[-1] for line in _script(os.path.join(folders["plain"], "data.js"))["lines"] if line[-1])
    for line in lines:
        assert line[-1]["lift"] == 2 and 0 < line[-1]["zone"] <= 5, line[-1]
    # Profiles computed again: those of lines only the rule finds, and others, equal the saved ones
    found_plain = {tuple(round(float(r[k]), 7) for k in ("anchor1_lat", "anchor1_lon", "anchor2_lat", "anchor2_lon"))
                   for r in plain}
    only = [line for line in lines if tuple(line[:4]) not in found_plain]
    assert only
    paths = search.Paths(str(tmp_path / "ends"), str(tmp_path / "profile-work"))
    os.makedirs(paths.work)
    for line in only[:3] + [line for line in lines if tuple(line[:4]) in found_plain][:2]:
        profile = search.profile_of_line(metas["ends"], paths, tuple(line[0:2]), tuple(line[2:4]))
        assert json.loads(json.dumps(profile)) == line[-1], line[:4]
        assert profile["min"][1] > 0  # the rule's decision value: valid
    # The same lines computed again without the rule: those only the rule finds are not valid
    del metas["ends"]["params"]["end_zone"], metas["ends"]["params"]["anchor_lift"]
    for line in only[:3]:
        profile = search.profile_of_line(metas["ends"], paths, tuple(line[0:2]), tuple(line[2:4]))
        assert "zone" not in profile and profile["min"][1] <= 0, line[:4]


def test_end_zone_in_tiles(tmp_path):
    """An area with an end zone and A-frames gives the same lines in tiles as in one grid."""
    square = {"type": "Polygon", "coordinates": [[[19.7522, 50.1546], [19.7590, 50.1546], [19.7590, 50.1580],
                                                  [19.7522, 50.1580], [19.7522, 50.1546]]]}
    path = tmp_path / "square.geojson"
    path.write_text(json.dumps({"type": "Feature", "properties": {}, "geometry": square}))
    common = ["--elevation-file", os.path.join(DATA, "zabi_kon_nmt.tif"), "--area", str(path),
              "--max-length", "150", *ENDS]
    one_out, one = run_search(tmp_path / "one", *common)
    tiled_out, tiled = run_search(tmp_path / "tiled", *common, "--tile-size", "150")
    assert "one grid" in one_out and "tiles)" in tiled_out
    # Every column of every line in the same order, its group and representative too: with the rule the clearance
    # of many lines is set at the first step from an anchor, so parallel lines tie exactly (clearance and length),
    # and search._fixed_order breaks such ties by the anchors' pixels, as tiles and one grid share them
    assert one and one == tiled and "lift_needed_m" in one[0]
    ties = collections.Counter((r["clearance_m"], r["length_m"]) for r in one)
    assert max(ties.values()) > 1  # the case the order is fixed for
    for name in ("data.js", "lines.js", "lines.geojson"):  # the files too, from their lines on
        texts = []
        for run in ("one", "tiled"):
            text = open(glob.glob(str(tmp_path / run / "runs" / "*" / name))[0], encoding="utf-8").read()
            texts.append(text[text.index('"lines":['):] if name.endswith(".js") else text[:text.index('"findaline"')])
        assert texts[0] == texts[1], name
    assert len(glob.glob(str(tmp_path / "tiled" / "runs" / "*" / "tiles" / "*.pkl.gz"))) > 1
    # the profiles of the groups' lines in the map, those at tile edges too (profile_of_line), carry the rule
    profiles = {}
    for name in ("one", "tiled"):
        lines = _script(glob.glob(str(tmp_path / name / "runs" / "*" / "data.js"))[0])["lines"]
        profiles[name] = {tuple(line[:4]): line[-1] for line in lines if line[-1]}
        assert profiles[name] and all(p["lift"] == 2 for p in profiles[name].values())
    assert profiles["one"] == profiles["tiled"]


def test_search_hash_without_the_ends():
    """_search_hash at --end-zone 0 and --anchor-lift 0 is the hash of before (computed with the code before
    the two fields, abc807e), so an unfinished tiled search resumes; with either set it differs."""
    import types
    import search
    from params import SearchParams

    def hash_of(owner=None, **values):
        params = SearchParams(lat=50.1559508, lon=19.7562722, radius=300, max_length=150, **values)
        return search._search_hash(types.SimpleNamespace(params=params, source=types.SimpleNamespace(id="geoportal"),
                                                         resolution=1.0, owner=owner))
    assert hash_of() == hash_of(end_zone=0, anchor_lift=0) == "e8dc08d333d941ab"
    assert hash_of(owner=7) == "0129d3c3e76f7a68"
    assert len({hash_of(), hash_of(end_zone=5), hash_of(anchor_lift=2), hash_of(end_zone=5, anchor_lift=2)}) == 4


def _terrain(data_dir) -> dict:
    """The terrain of the one run in data_dir as run.json, data.js and lines.js have it (all equal)."""
    folder = glob.glob(str(data_dir / "runs" / "*" / "run.json"))[0].rsplit(os.sep, 1)[0]
    read = lambda name: open(os.path.join(folder, name), encoding="utf-8").read()  # noqa: E731
    found = {"run.json": json.loads(read("run.json"))["terrain"],
             "data.js": json.loads(read("data.js").partition(" = ")[2].rstrip().rstrip(";"))["terrain"],
             "lines.js": json.loads(read("lines.js").partition("] = ")[2].rstrip().rstrip(";"))["terrain"]}
    assert found["run.json"] == found["data.js"] == found["lines.js"]
    return found


def test_terrain_of_the_clip(tmp_path):
    """The Żabi Koń clip's terrain: 101 quantiles in order, the land of the circle, every anchor
    between the lowest and the highest bin; printed after step 5, saved after the summary."""
    output, rows = run_search(tmp_path, "--elevation-file", os.path.join(DATA, "zabi_kon_nmt.tif"),
                              "--northing", "254608", "--easting", "553966", "--radius", "290")
    terrain = _terrain(tmp_path)["run.json"]
    q = terrain["quantiles"]
    assert len(q) == 101 and q == sorted(q) and q[0] < terrain["mean"] < q[100]
    assert terrain["km2"] == pytest.approx(np.pi * 0.29 ** 2, rel=0.01)  # all land with data
    heights = [float(r[f"anchor{k}_elev_m"]) for r in rows for k in (1, 2)]
    assert rows and q[0] <= min(heights) and max(heights) < q[100] + 0.1
    line = f"Terrain of the search area: {q[0]:.0f}–{q[100]:.0f} m, mean {terrain['mean']:.0f} m, "            f"median {q[50]:.0f} m ({terrain['km2']:.2f} km² of land with data)"
    assert line in output.splitlines(), output
    meta = json.load(open(glob.glob(str(tmp_path / "runs" / "*" / "run.json"))[0], encoding="utf-8"))
    assert list(meta).index("terrain") == list(meta).index("summary") + 1
    runs_js = (tmp_path / "runs" / "runs.js").read_text(encoding="utf-8")
    assert '"terrain"' not in runs_js and '"summary"' in runs_js


def test_terrain_of_a_resumed_area(tmp_path, monkeypatch):
    """A tiled area resumed finds its tiles' terrain files and gives the same terrain; a tile
    finished without one (saved before the statistics) leaves the run's terrain unknown."""
    for key, v in OFFLINE_ENV.items():
        monkeypatch.setenv(key, v)
    import search
    from params import SearchParams
    square = {"type": "Polygon", "coordinates": [[[19.7522, 50.1546], [19.7590, 50.1546], [19.7590, 50.1580],
                                                  [19.7522, 50.1580], [19.7522, 50.1546]]]}
    path = tmp_path / "square.geojson"
    path.write_text(json.dumps({"type": "Feature", "properties": {}, "geometry": square}))
    params = SearchParams(elevation_file=os.path.join(DATA, "zabi_kon_nmt.tif"), area=str(path), max_length=150,
                          tile_size=150, water="off", fill_gaps="off", no_html=True)
    paths = search.Paths(str(tmp_path), str(tmp_path / "work"))

    def terrain():
        plan = search.plan_search(params, paths, lambda kind, text: None)
        assert plan.tiles
        return search.search_lines(plan)[0].terrain

    first = terrain()  # the run stays unfinished (no save_run): the next call resumes it
    assert first is not None and terrain() == first
    files = sorted(glob.glob(str(tmp_path / "runs" / "*" / "tiles" / "*.terrain.npz")))
    assert len(files) > 1
    os.remove(files[0])
    assert terrain() is None


def test_two_points(tmp_path):
    """Two --point searches in one call: one run each, with its own name and data record."""
    env = {**os.environ, **OFFLINE_ENV}
    result = subprocess.run(
        [sys.executable, "findaline.py", "--elevation-file", os.path.join(DATA, "zabi_kon_nmt.tif"),
         "--point", "50.15624,19.75569,West", "--point", "50.15600,19.75630,East", "--radius", "100",
         "--water", "off", "--fill-gaps", "off", "--no-plot", "--yes", "--data-dir", str(tmp_path)],
        cwd=REPO, env=env, capture_output=True, text=True, encoding="utf-8", timeout=600)
    assert result.returncode == 0, result.stdout + result.stderr
    runs = sorted(glob.glob(str(tmp_path / "runs" / "*" / "run.json")))
    assert len(runs) == 2, result.stdout
    metas = [json.load(open(path, encoding="utf-8")) for path in runs]
    assert {m["name"] for m in metas} == {"West", "East"}
    assert all(len(m["data"]) == 1 for m in metas)  # each run records only its own data
    assert not os.listdir(tmp_path / "work")       # both work folders deleted


def test_year_of_the_run_in_credits(tmp_path, monkeypatch):
    """A credit, orthophoto or note naming sources.YEAR gets the year of the run (LGLN's
    "© GeoBasis-DE/LGLN <year>"): in run.json, ATTRIBUTION.txt, lines.geojson and the map's data.js;
    a credit without it is recorded as it is. The run's time is patched to another year."""
    from datetime import datetime as real_datetime
    import search
    import sources as src
    from params import SearchParams

    class Later(real_datetime):
        @classmethod
        def now(cls, tz=None):
            return real_datetime(2031, 3, 4, 12, 0, 0)
    monkeypatch.setattr(search, "datetime", Later)
    dated = src.Credit("Dated data", f"© Someone {src.YEAR}, changed", "CC BY 4.0", notice=f"Got {src.YEAR}.")
    plain = src.FABDEM_CREDIT
    events = []
    paths = search.Paths(str(tmp_path), str(tmp_path / "work"))
    params = SearchParams(elevation_file=os.path.join(DATA, "zabi_kon_nmt.tif"), water="off", fill_gaps="off",
                          ortho="never", nmpt="off", northing=254608, easting=553966, radius=120)
    for name, value in OFFLINE_ENV.items():
        monkeypatch.setenv(name, value)
    choose = src.choose_source

    def with_ortho_and_note(*args, **kwargs):  # the local files' source with LGLN's orthophoto and a note
        source, reason = choose(*args, **kwargs)
        source.ortho, source.note = src.SOURCES["lower_saxony"].ortho, f"Data © Someone {src.YEAR}."
        return source, reason
    monkeypatch.setattr(src, "choose_source", with_ortho_and_note)
    plan = search.plan_search(params, paths, lambda kind, text: events.append(text))
    data = search.prepare_data(plan)
    lines = search.find_lines(plan, data)
    used = [{"layer": "Dated", "credit": dated.as_dict()}, {"layer": "Plain", "credit": plain.as_dict()}]
    monkeypatch.setattr(search, "_merged_data", lambda: used)
    result = search.save_run(plan, lines)
    folder = result.run["path"]
    assert os.path.basename(folder).startswith("2031")
    read = lambda name: open(os.path.join(folder, name), encoding="utf-8").read()  # noqa: E731
    meta = json.loads(read("run.json"))
    assert meta["attribution"] == [{**dated.as_dict(), "attribution": "© Someone 2031, changed", "notice": "Got 2031."},
                                   plain.as_dict()]
    assert [d["credit"] for d in meta["data"]] == meta["attribution"]
    text = read("ATTRIBUTION.txt")
    assert "Notice: © Someone 2031, changed" in text and "Got 2031." in text and src.YEAR not in text
    assert f"Notice: {plain.attribution}" in text
    geojson = json.loads(read("lines.geojson"))["findaline"]
    assert geojson["attribution"] == meta["attribution"]
    js = json.loads(read("data.js").partition(" = ")[2].rstrip().rstrip(";"))
    assert js["attribution"] == meta["attribution"]
    assert js["ortho"]["attribution"] == "LGLN (2031), CC BY 4.0"
    assert src.SOURCES["lower_saxony"].ortho.attribution == f"LGLN ({src.YEAR}), CC BY 4.0"  # the catalogue unchanged
    # the console's note names the year of a run made now
    assert "Note: Data © Someone 2031." in "\n".join(events)


def _water_and_fallback(tmp_path, monkeypatch, water: np.ndarray, fallback: np.ndarray, left: float, top: float):
    """Offline: the Copernicus water body mask from the uint8 raster `water` (OCEAN, LAKE) and a
    fallback source with the terrain `fallback`, both on EPSG:2180 at 1 m from (left, top), for the
    source of local files (the fallback fills its gaps on land)."""
    import sources as src
    write_raster(tmp_path / "fallback.tif", fallback, left, top)
    with rio.open(tmp_path / "wbm.tif", "w", driver="GTiff", width=water.shape[1], height=water.shape[0], count=1,
                  dtype="uint8", crs="EPSG:2180", transform=from_origin(left, top, 1, 1)) as dst:
        dst.write(water, 1)

    class _WaterFile(src.FileLayer):  # the water body mask from a file: no tiles of the cache
        def tiles(self, grid):
            return []

        def files(self, grid, cache_dir):
            return [self.path]

    mask = _WaterFile("Water body mask file", str(tmp_path / "wbm.tif"))
    monkeypatch.setattr(src, "WATER_MASK", mask)
    monkeypatch.setattr(src.filling, "WATER_MASK", mask)
    credit = src.Credit("fallback", "© fallback", "CC BY 4.0", "https://example.org")
    monkeypatch.setitem(src.SOURCES, "test_fallback", src.Source(
        id="test_fallback", name="test fallback", description="fallback",
        nmt=src.FileLayer("Fallback terrain", str(tmp_path / "fallback.tif")), credits=(credit,)))
    choose = src.choose_source

    def with_fallback(*args, **kwargs):
        source, reason = choose(*args, **kwargs)
        source.fallback = "test_fallback"
        return source, reason
    monkeypatch.setattr(src, "choose_source", with_fallback)
    for name, value in OFFLINE_ENV.items():
        monkeypatch.setenv(name, value)


def _square(path, left: float, bottom: float, right: float, top: float):
    """A square of EPSG:2180 bounds as a GeoJSON area file (WGS84)."""
    from rasterio.warp import transform_bounds
    west, south, east, north = transform_bounds("EPSG:2180", "EPSG:4326", left, bottom, right, top)
    square = {"type": "Polygon", "coordinates": [[[west, south], [east, south], [east, north], [west, north],
                                                  [west, south]]]}
    path.write_text(json.dumps({"type": "Feature", "properties": {}, "geometry": square}))
    return str(path)


def test_work_estimate_counts_the_grids_written(tmp_path, monkeypatch):
    """estimate_search's working grids (search.work_bytes) are what step 1 writes into the work folder:
    terrain and surface, the obstacles, the water body mask, the water, a fallback's terrain and surface
    and its filled pixels, each the size of the grid (a sea and gaps on land that the fallback fills).
    A tiled area: the area's grids (and the area mask, among step 1's temporaries: AREA_TEMP_BYTES)
    plus one tile's copies of them (search.tile_bytes), the largest tile's."""
    import search
    import sources as src
    from params import SearchParams
    left, top, size = 500000, 300000, 240
    terrain = np.full((size, size), 240.0)
    terrain[:, 100:140] = 200.0
    terrain[:, 200:] = np.nan  # the sea (the water body mask's ocean) without data
    terrain[30:50, 30:60] = np.nan  # a gap on land: the fallback's
    surface = terrain + 3.0
    surface[150:170, 60:80] = np.nan  # a gap of the surface model only
    surface[:, 200:212] = np.linspace(199.0, 188.0, 12)  # the shore face: the surface model only, down from the edge
    write_raster(tmp_path / "nmt.tif", terrain, left, top)
    write_raster(tmp_path / "nmpt.tif", surface, left, top)
    water = np.zeros((size, size), np.uint8)
    water[:, 205:] = src.OCEAN
    water[100:110, 20:30] = src.LAKE
    _water_and_fallback(tmp_path, monkeypatch, water, np.full((size, size), 238.0), left, top)
    paths = search.Paths(str(tmp_path), str(tmp_path / "work"))
    params = SearchParams(elevation_file=str(tmp_path / "nmt.tif"), surface_file=str(tmp_path / "nmpt.tif"),
                          water="fill", fill_gaps="on", coastline="copernicus", ortho="never",
                          northing=top - size / 2, easting=left + size / 2, radius=110, resolution=1)
    plan = search.plan_search(params, paths, lambda kind, text: None)
    assert plan.obstacles and plan.nmpt and plan.source.fallbacks == ["test_fallback"]
    data = search.prepare_data(plan)
    assert data.filled is not None and data.filled.any() and data.water.any()
    # The uncertain shore: the face from the surface model (columns 200-211 of every row) and the sea fill
    # at its foot, which the face ends 188 m above
    assert data.shore and {s["kind"] for s in data.shore["segments"]} == {"sea", "surface"}
    assert data.shore["totals"]["surface_px"] == 240 * 12 and 0 < data.shore["totals"]["sea_px"] < 100
    assert data.shore_kinds is None

    def written_in(folder, shape):
        found = {}
        for path in glob.glob(os.path.join(folder, "*.npy")):
            grid = np.load(path, mmap_mode="r")
            assert grid.shape == shape, path
            found[os.path.basename(path)] = grid.nbytes
            del grid
        return found

    written = written_in(str(tmp_path / "work"), (plan.grid.height, plan.grid.width))
    assert not glob.glob(str(tmp_path / "work" / "*" / "*.npy"))
    del data
    assert sorted(written) == ["covered.npy", "filled.npy", "gap_nmpt.npy", "gap_nmt.npy", "nmpt.npy", "nmt.npy",
                               "obstacles.npy", "water.npy", "wbm.npy"]
    pixels = plan.grid.height * plan.grid.width
    assert sum(written.values()) == search.work_bytes(plan) * pixels == 24 * pixels
    assert search.estimate_search(plan).work_gb == 24 * pixels / 1e9
    # A tiled area: step 1 once on the whole grid in strips, then a tile's contiguous copies
    area = _square(tmp_path / "square.geojson", left + 30, top - size + 30, left + size - 30, top - 30)
    tiled = SearchParams(elevation_file=str(tmp_path / "nmt.tif"), surface_file=str(tmp_path / "nmpt.tif"),
                         water="fill", fill_gaps="on", coastline="copernicus", ortho="never", area=area,
                         tile_size=100, resolution=1)
    paths = search.Paths(str(tmp_path), str(tmp_path / "work-tiled"))
    plan = search.plan_search(tiled, paths, lambda kind, text: None)
    assert plan.tiles and len(plan.tiles) == 4
    data = search.prepare_data(plan, strips=True)
    assert data.filled.any() and data.water.any() and len(data.tile_terrain) == 4 and data.mask.any()
    assert data.shore and data.shore["totals"]["surface_px"] > 0  # the area's, found strip by strip
    written = written_in(paths.work, (plan.grid.height, plan.grid.width))
    assert sorted(written) == ["covered.npy", "filled.npy", "gap_nmpt.npy", "gap_nmt.npy", "mask.npy", "nmpt.npy",
                               "nmt.npy", "obstacles.npy", "water.npy", "wbm.npy"]
    pixels = plan.grid.height * plan.grid.width
    assert sum(written.values()) == (search.work_bytes(plan) + 1) * pixels  # the mask among AREA_TEMP_BYTES
    assert 1 < search.AREA_TEMP_BYTES
    largest = max((t for _, t in plan.tiles), key=lambda t: t.width * t.height)
    os.makedirs(os.path.join(paths.work, "tile0"))
    tile = search._tile_data(data, plan.grid, largest, os.path.join(paths.work, "tile0"), data.tile_terrain[0])
    copies = written_in(os.path.join(paths.work, "tile0"), (largest.height, largest.width))
    assert sorted(copies) == ["covered.npy", "filled.npy", "nmt.npy", "surface.npy", "water.npy"]
    tile_pixels = largest.height * largest.width
    assert sum(copies.values()) == search.tile_bytes(plan) * tile_pixels == 11 * tile_pixels
    assert tile.mask.shape == (largest.height, largest.width) and tile.terrain is data.tile_terrain[0]
    assert search.estimate_search(plan).work_gb == (28 * pixels + 11 * tile_pixels) / 1e9  # the area's, a tile's
    del tile, data


def _old_fill_water_rows(elevation_path, surface_path, grid, wbm, sea_zone, out_path, sea_value, rows, bare_path):
    """sources.filling._fill_water_rows before the dry strips were left out (main d466347): the reference."""
    import math
    from scipy import ndimage
    from sources import filling as f

    elevation = np.load(elevation_path, mmap_mode="r+")
    surface = np.load(surface_path, mmap_mode="r+") if surface_path else None
    shape = elevation.shape
    f.progress.compute.start("filling sea and lakes", 3, unit="step")
    f.progress.compute.update(0, part="sea")
    water = f.new_mask(out_path, shape)
    lake_path = os.path.join(os.path.dirname(out_path), "lake.npy")
    lake = f.new_mask(lake_path, shape)
    n = max(1, math.ceil(f.SHORE_BUFFER / grid.res))
    size = 2 * n + 1
    sea_px = 0
    any_lake = False
    for r0, r1, h0, h1 in f.strips(shape[0], rows, n):
        empty = np.isnan(elevation[r0:r1])
        sea_fill = empty & np.asarray(sea_zone[r0:r1], dtype=bool)
        shore = np.asarray(wbm[h0:h1]) == f.LAKE
        if shore.any():
            shore = ndimage.maximum_filter1d(shore, size, axis=0, mode="constant", cval=0)[r0 - h0:r1 - h0]
            shore = ndimage.maximum_filter1d(shore, size, axis=1, mode="constant", cval=0)
            here = empty & shore & ~sea_fill
            if here.any():
                lake[r0:r1] = here
                any_lake = True
        del empty, shore
        if sea_fill.any():
            block = elevation[r0:r1]
            block[sea_fill] = 0.0
            if surface is not None:
                sblock = surface[r0:r1]
                sblock[sea_fill & np.isnan(sblock)] = 0.0
            water[r0:r1] = sea_fill
            sea_px += int(sea_fill.sum())
    f.progress.compute.update(1, part="lakes")
    if any_lake:
        labels = np.zeros(shape, np.int32)
        ndimage.label(lake, structure=np.ones((3, 3)), output=labels)
    del lake
    f.remove_grid(lake_path)
    f.progress.compute.update(1, part="levels")
    lake_px = 0
    for index, region in enumerate(ndimage.find_objects(labels) if any_lake else (), 1):
        if region is None:
            continue
        box_rows = slice(max(region[0].start - 1, 0), region[0].stop + 1)
        cols = slice(max(region[1].start - 1, 0), region[1].stop + 1)
        area = labels[box_rows, cols] == index
        empty = np.isnan(elevation[box_rows, cols]) | np.asarray(water[box_rows, cols])
        shore = ndimage.binary_dilation(area) & ~empty
        heights = elevation[box_rows, cols][shore]
        heights = heights[np.isfinite(heights)]
        if heights.size == 0:
            continue
        level = float(np.median(heights))
        block = elevation[box_rows, cols]
        block[area] = level
        if surface is not None:
            sblock = surface[box_rows, cols]
            sblock[area & np.isnan(sblock)] = level
        water[box_rows, cols] |= area
        lake_px += int(area.sum())
    labels = None
    bare = f.new_mask(bare_path, shape) if bare_path else None
    for r0, r1, _, _ in f.strips(shape[0], rows):
        if bare is not None:
            bare[r0:r1] = water[r0:r1]
        with_data = f.water_with_data(np.asarray(elevation[r0:r1]), wbm[r0:r1], sea_zone[r0:r1], sea_value)
        if with_data.any():
            water[r0:r1] |= with_data
    f.flush_grid(elevation)
    if surface is not None:
        f.flush_grid(surface)
    f.flush_grid(water)
    if bare is not None:
        f.flush_grid(bare)
    del water, bare
    f.progress.compute.update(1)
    km2 = lambda px: px * grid.res ** 2 / 1e6  # noqa: E731
    f.progress.compute.finish(f"sea {km2(sea_px):.2f} km², lakes {km2(lake_px):.2f} km²")
    return out_path


@pytest.mark.parametrize("scene", ["dry", "lake"])
def test_dry_tile_in_strips_as_before(tmp_path, monkeypatch, scene):
    """Step 1 in strips (prepare_data(strips=True), as country.TileWork counts a tile) gives what it gave
    before a lone water body mask tile of one category was left unreprojected (filling.constant_category)
    and the dry strips were left out of fill_water (the reference _old_fill_water_rows): every grid of
    Data, every file left in the work folder, the printed lines and the bars. "dry": no water and no gap,
    the water body mask a tile of 0 in WGS84 (both early-outs taken); "lake": a lake measured and one
    without data, a gap on land that a fallback fills (the mask is built, the strips far from the lakes
    are dry)."""
    import search
    import sources as src
    from params import SearchParams
    from rasterio.warp import transform_bounds
    from scipy import ndimage
    with rio.open(os.path.join(DATA, "zabi_kon_nmt.tif")) as s:
        terrain, left, top = s.read(1), s.bounds.left, s.bounds.top
    size = terrain.shape[0]
    fallback = (ndimage.uniform_filter(terrain, 5) + 1.5).astype(np.float32)
    if scene == "lake":
        terrain[330:360, 300:340] = np.nan  # a lake without data
        terrain[100:110, 150:170] = np.nan  # a gap on land: the fallback's
    write_raster(tmp_path / "nmt.tif", terrain, left, top)
    write_raster(tmp_path / "fallback.tif", fallback, left, top)
    west, south, east, north = transform_bounds("EPSG:2180", "EPSG:4326", left, top - size, left + size, top)
    pad = 40 / 3600  # the tile reaches 40 of its pixels beyond the clip
    origin = (west - pad, north + pad)
    shape = (int((north - south + 2 * pad) * 3600) + 1, int((east - west + 2 * pad) * 3600) + 1)
    water = np.zeros(shape, np.uint8)
    if scene == "lake":
        from pyproj import Transformer
        to_wgs84 = Transformer.from_crs("EPSG:2180", "EPSG:4326", always_xy=True)
        for (x, y), half in (((left + 320, top - 345), 1), ((left + 100, top - 450), 0)):  # without data, measured
            lon, lat = to_wgs84.transform(x, y)
            r, c = int((origin[1] - lat) * 3600), int((lon - origin[0]) * 3600)
            water[r - half:r + half + 1, c - half:c + half + 1] = src.LAKE
    with rio.open(tmp_path / "wbm.tif", "w", driver="GTiff", width=shape[1], height=shape[0], count=1, dtype="uint8",
                  crs="EPSG:4326", transform=from_origin(*origin, 1 / 3600, 1 / 3600)) as dst:
        dst.write(water, 1)

    class _WaterFile(src.FileLayer):  # the water body mask from a file: no tiles of the cache
        def tiles(self, grid):
            return []

        def files(self, grid, cache_dir):
            return [self.path]

    mask = _WaterFile("Water body mask file", str(tmp_path / "wbm.tif"))
    monkeypatch.setattr(src, "WATER_MASK", mask)
    monkeypatch.setattr(src.filling, "WATER_MASK", mask)
    monkeypatch.setitem(src.SOURCES, "test_fallback", src.Source(
        id="test_fallback", name="test fallback", description="fallback",
        nmt=src.FileLayer("Fallback terrain", str(tmp_path / "fallback.tif")),
        credits=(src.Credit("fallback", "© fallback", "CC BY 4.0", "https://example.org"),)))
    choose = src.choose_source

    def with_fallback(*args, **kwargs):
        source, reason = choose(*args, **kwargs)
        source.fallback = "test_fallback"
        return source, reason
    monkeypatch.setattr(src, "choose_source", with_fallback)
    for name, value in OFFLINE_ENV.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(src.filling, "STRIP_PX", 16 * 600)  # strips of 16 rows
    built = []
    build_mosaic = src.filling.build_mosaic
    monkeypatch.setattr(src.filling, "build_mosaic", lambda files, grid, out, label, **kw: built.append(label) or
                        build_mosaic(files, grid, out, label, **kw))
    params = SearchParams(elevation_file=str(tmp_path / "nmt.tif"), water="fill", fill_gaps="on",
                          coastline="copernicus", ortho="never", nmpt="off", northing=top - size / 2,
                          easting=left + size / 2, radius=260, resolution=1, prominence_span=20, drop_radius=20)
    fields = ("elevation", "surface", "water", "filled", "slope", "joined", "mask", "covered", "shore_kinds")

    def step1(mode):
        events, bars = [], []
        listener = lambda state: bars.append(dict(state)) if state.get("bar") else None  # noqa: E731
        work = tmp_path / mode / "work"
        os.makedirs(work)
        plan = search.plan_search(params, search.Paths(str(tmp_path / mode), str(work)),
                                  lambda kind, text: events.append((kind, str(text))))
        built.clear()
        search.progress.subscribe(listener)  # the bars' object search holds
        try:
            data = search.prepare_data(plan, statistics=False, shore="none", strips=True)
        finally:
            search.progress.unsubscribe(listener)
        grids = {f: None if getattr(data, f) is None else np.array(getattr(data, f)) for f in fields}
        assert data.terrain is None and data.tile_terrain is None and data.shore is None
        del data
        files = {}
        for path in sorted(glob.glob(str(work / "*"))):
            files[os.path.basename(path)] = np.load(path) if path.endswith(".npy") else open(path, "rb").read()
        return {"grids": grids, "files": files, "events": events, "bars": bars, "built": list(built)}

    now = step1("now")
    with monkeypatch.context() as m:
        m.setattr(src.filling, "constant_category", lambda files, grid: None)
        m.setattr(src.filling, "_fill_water_rows", _old_fill_water_rows)
        before = step1("before")
    for f in fields:
        a, b = now["grids"][f], before["grids"][f]
        assert (a is None) == (b is None), f
        if a is not None:
            assert a.dtype == b.dtype and np.array_equal(a, b, equal_nan=a.dtype.kind == "f"), f
    assert sorted(now["files"]) == sorted(before["files"])
    for name, a in now["files"].items():
        b = before["files"][name]
        assert np.array_equal(a, b, equal_nan=a.dtype.kind == "f") if isinstance(a, np.ndarray) else a == b, name
    assert now["events"] == before["events"] and now["bars"] == before["bars"]
    assert "water mask" in before["built"] and ("water mask" in now["built"]) == (scene == "lake")
    water, filled = now["grids"]["water"], now["grids"]["filled"]
    if scene == "dry":
        assert not water.any() and not filled.any() and not np.isnan(now["grids"]["elevation"]).any()
        assert not now["files"]["wbm.npy"].any()
    else:
        assert water.any() and filled.any() and not water[:150].any()  # the strips far from the lakes stay dry


def test_area_in_tiles_with_water_and_gaps(tmp_path, monkeypatch):
    """An area computed in tiles gives exactly the lines of one grid also with the sea and a lake
    filled and gaps on land filled from a fallback: step 1 runs once on the whole grid (the lake
    levels, the gap offsets and the border gaps are the area's), each tile takes its window."""
    import search
    import sources as src
    from params import SearchParams
    with rio.open(os.path.join(DATA, "zabi_kon_nmt.tif")) as s:
        terrain, left, top = s.read(1), s.bounds.left, s.bounds.top
    with rio.open(os.path.join(DATA, "zabi_kon_nmpt.tif")) as s:
        surface = s.read(1)
    from scipy import ndimage
    fallback = (ndimage.uniform_filter(terrain, 5) + 1.5).astype(np.float32)
    size = terrain.shape[0]
    terrain[:, :80] = surface[:, :80] = np.nan  # the sea in the west, without data
    terrain[200:260, 300:360] = surface[200:260, 300:360] = np.nan  # a lake
    terrain[400:430, 150:190] = surface[400:430, 150:190] = np.nan  # gaps on land
    terrain[290:310, 240:260] = surface[290:310, 240:260] = np.nan
    surface[100:140, 400:440] = np.nan  # a gap of the surface model only
    write_raster(tmp_path / "nmt.tif", terrain, left, top)
    write_raster(tmp_path / "nmpt.tif", surface, left, top)
    water = np.zeros((size, size), np.uint8)
    water[:, :85] = src.OCEAN
    water[195:265, 295:365] = src.LAKE
    _water_and_fallback(tmp_path, monkeypatch, water, fallback, left, top)
    area = _square(tmp_path / "square.geojson", left + 40, top - size + 60, left + size - 60, top - 40)
    runs = {}
    for name, tile_size in (("one", None), ("tiled", 150)):
        params = SearchParams(elevation_file=str(tmp_path / "nmt.tif"), surface_file=str(tmp_path / "nmpt.tif"),
                              area=area, max_length=150, water="fill", fill_gaps="on", coastline="copernicus",
                              ortho="never", tile_size=tile_size)
        paths = search.Paths(str(tmp_path / name), str(tmp_path / name / "work"))
        os.makedirs(paths.work)
        plan = search.plan_search(params, paths, lambda kind, text: None)
        assert bool(plan.tiles) == (tile_size is not None)
        lines, run = search.search_lines(plan)
        assert (lines.results.columns["water_m"] > 0).any() and (lines.results.columns["filled_m"] > 0).any()
        result = search.save_run(plan, lines, run)
        runs[name] = result.run["path"]
        if plan.tiles:
            assert not glob.glob(os.path.join(paths.work, "*.npy"))  # the area's grids are gone after the tiles
    read = lambda name, file: open(os.path.join(runs[name], file), "rb").read()  # noqa: E731
    assert read("one", "lines.csv") == read("tiled", "lines.csv")
    # The map's rows come in the table's order (the tiles' one after another for a tiled run): the
    # same rows, and the profiles of the same lines (one of a group joining two tiles computed
    # again on its own grid may differ a little: not here)
    for file in ("data.js", "lines.js"):
        rows = {}
        for name in ("one", "tiled"):
            text = read(name, file).decode("utf-8")
            rows[name] = json.loads(text[text.index(" = {") + 3:].rstrip().rstrip(";"))["lines"]
        assert sorted(map(json.dumps, rows["one"])) == sorted(map(json.dumps, rows["tiled"])), file
    one, tiled = (json.loads(read(name, "run.json")) for name in ("one", "tiled"))
    assert one["terrain"] == tiled["terrain"] and one["summary"]["lines"] == tiled["summary"]["lines"]
    assert len(glob.glob(os.path.join(runs["tiled"], "tiles", "*.table.pkl.gz"))) > 1
    # Where the land's terrain came from: the same counted once on the whole grid in strips; the two gaps
    # filled from the fallback, a small share (no warning), in the head of data.js too
    origins = one["terrain_sources"]
    assert origins == tiled["terrain_sources"] and 0 < origins["fallback_share"] < search.FALLBACK_WARN_SHARE
    assert [layer["role"] for layer in origins["layers"]] == ["source", "fallback"]
    assert '"terrain_sources":' in read("tiled", "data.js").decode("utf-8")


def _fake_orthophoto(http_server, monkeypatch, folder: str = "fake/ortho/live"):
    """A service of tiles only (like SWISSIMAGE) on the test server, answering every tile with one
    JPEG, attached to the source of the local files; its requests are http_server.requests("/tiles/")."""
    import io

    from PIL import Image
    from http_server import Answer
    import sources as src
    out = io.BytesIO()
    Image.new("RGB", (256, 256), (120, 140, 90)).save(out, "JPEG")
    http_server.route("/tiles/", lambda request: Answer(200, out.getvalue(), {"Content-Type": "image/jpeg"}))
    service = src.OrthoService("Fake orthophoto", None, "", folder, "Fake imagery, CC BY 4.0",
                               base_url=http_server.url("/tiles/{z}/{x}/{y}.jpg"), base_max_zoom=19)
    choose = src.choose_source

    def with_ortho(*args, **kwargs):
        source, reason = choose(*args, **kwargs)
        source.ortho = service
        return source, reason
    monkeypatch.setattr(src, "choose_source", with_ortho)
    return service


def test_orthophoto_after_the_run(tmp_path, monkeypatch, http_server):
    """The orthophoto for offline use is a step after the run: save_run writes the run and the map
    without a request (the map names the cache folder and loads a tile online until it is there),
    orthophoto_lines picks one line per group by the detail rules, download_orthophoto fetches the
    tiles not cached yet into the cache and its index and leaves the run's files as they were;
    --ortho auto asks over CONFIRM_MINUTES, --ortho never and --no-html get nothing."""
    import dataclasses

    import area as ar
    import cache
    import orthophoto as ortho
    import search
    from params import SearchParams
    for name, value in OFFLINE_ENV.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")  # the test server, not through the dead proxy
    service = _fake_orthophoto(http_server, monkeypatch)
    paths = search.Paths(str(tmp_path), str(tmp_path / "work"))
    values = dict(elevation_file=os.path.join(DATA, "zabi_kon_nmt.tif"), water="off", fill_gaps="off", nmpt="off",
                  northing=254608, easting=553966, radius=150)
    events = []
    plan = search.plan_search(SearchParams(ortho="always", **values), paths, lambda kind, text: events.append(text))
    lines = search.find_lines(plan, search.prepare_data(plan))
    result = search.save_run(plan, lines)
    assert not http_server.log  # nothing fetched for the run and its map
    folder = result.run["path"]
    read = lambda name: open(os.path.join(folder, name), "rb").read()  # noqa: E731
    files = {name: read(name) for name in os.listdir(folder) if os.path.isfile(os.path.join(folder, name))}
    data = json.loads(files["data.js"].decode("utf-8").partition(" = ")[2].rstrip().rstrip(";"))
    assert data["ortho"]["cache"] == "../../cache/fake/ortho/live/wm256" and data["ortho"]["base"]["max_zoom"] == 19

    # One line per group, the best groups first: a circle every group, --ortho-detail or the
    # service's detail that many, an area without either ORTHO_DETAIL
    reps = lines.spot_groups.rep.tolist()
    spots = search.orthophoto_lines(plan, lines)
    assert len(spots) == len(reps) > 3
    assert spots[0] == {k: lines.results.row(reps[0])[k] for k in ("anchor1", "anchor2")}
    with_params = lambda **u: dataclasses.replace(plan, params=plan.params.model_copy(update=u))  # noqa: E731
    with_service = lambda **u: dataclasses.replace(  # noqa: E731
        plan, source=dataclasses.replace(plan.source, ortho=dataclasses.replace(service, **u)))
    assert search.orthophoto_lines(with_params(ortho_detail=2), lines) == spots[:2]
    assert search.orthophoto_lines(with_service(detail=3), lines) == spots[:3]
    assert search.orthophoto_lines(dataclasses.replace(with_service(detail=3), params=plan.params.model_copy(
        update={"ortho_detail": 1})), lines) == spots[:1]  # the option over the service
    monkeypatch.setattr(search, "ORTHO_DETAIL", 2)
    area = dataclasses.replace(plan, area=ar.Polygon(plan.area.shape_wgs84()))
    assert search.orthophoto_lines(area, lines) == spots[:2]

    # The download: the tiles of the overview and of the strips, not cached yet, into the cache
    tiles_folder = ortho.cache_folder(paths.cache, service)
    wanted = ortho.tiles_to_cache(spots, plan.area, 19)
    assert len(wanted) > 16 and all(z <= 19 for z, _, _ in wanted)
    assert search.download_orthophoto(plan, spots) == len(wanted) == len(http_server.requests("/tiles/"))
    assert all(os.path.exists(ortho.tile_path(tiles_folder, *t)) for t in wanted)
    assert cache.state(paths.cache, ortho.tile_path(tiles_folder, *sorted(wanted)[0])) == "ok"
    assert {name: read(name) for name in files} == files  # the run's files as they were
    said = [e for e in events if "Orthophoto" in e]
    assert said[0].startswith(f"Orthophoto for offline use: {len(wanted)} tiles to download (~")
    assert said[1].startswith(f"Orthophoto for offline use: {len(wanted)} of {len(wanted)} tiles saved (")
    assert search.download_orthophoto(plan, spots) == 0  # all cached now
    assert len(http_server.requests("/tiles/")) == len(wanted) and events[-1].startswith("Orthophoto for offline use: 0 tiles")

    # --ortho auto over CONFIRM_MINUTES asks; no means none, yes downloads (into another folder here)
    monkeypatch.setattr(search, "CONFIRM_MINUTES", 0)
    auto = dataclasses.replace(with_service(folder="fake/ortho2/live"), params=plan.params.model_copy(update={"ortho": "auto"}))
    asked = []

    def no(kind, text):
        asked.append(kind)
        return False
    assert search.download_orthophoto(auto, spots, no) == 0 and asked == ["ortho"]
    assert len(http_server.requests("/tiles/")) == len(wanted)
    assert search.download_orthophoto(auto, spots, lambda kind, text: True) == len(wanted)
    assert len(http_server.requests("/tiles/")) == 2 * len(wanted)
    # Nothing with --ortho never or --no-html: no message either
    events.clear()
    assert search.download_orthophoto(with_params(ortho="never"), spots) == 0
    assert search.download_orthophoto(with_params(no_html=True), spots) == 0
    assert not events and len(http_server.requests("/tiles/")) == 2 * len(wanted)


def test_orthophoto_tiles_per_strip():
    """tiles_to_cache tests each strip within its own bounding box (the union's box holds mostly
    empty tiles when the lines are spread out): exactly the tiles of the union of the strips, as
    the code of before 2026-11-02 found them (kept here as the reference), whatever the overlap."""
    import math
    import random

    from shapely.geometry import LineString, box
    from shapely.ops import unary_union
    from shapely.prepared import prep
    import area as ar
    import orthophoto as ortho

    def reference_tiles_in(area, zooms):
        tiles = set()
        prepared = prep(area)
        minx, miny, maxx, maxy = area.bounds
        for z in zooms:
            size = ortho._tile_size(z)
            for x in range(math.floor((minx + ortho._EARTH) / size), math.floor((maxx + ortho._EARTH) / size) + 1):
                for y in range(math.floor((ortho._EARTH - maxy) / size), math.floor((ortho._EARTH - miny) / size) + 1):
                    left, top = x * size - ortho._EARTH, ortho._EARTH - y * size
                    if prepared.intersects(box(left, top - size, left + size, top)):
                        tiles.add((z, x, y))
        return tiles

    def reference(lines, area, max_zoom):
        scale = 1 / math.cos(math.radians(area.center[0]))
        tiles = reference_tiles_in(area.shape_mercator(), ortho.OVERVIEW_ZOOMS)
        strips = [LineString([ortho._to_mercator.transform(line["anchor1"][1], line["anchor1"][0]),
                              ortho._to_mercator.transform(line["anchor2"][1], line["anchor2"][0])]
                             ).buffer(ortho.BUFFER_M * scale) for line in lines]
        if strips:
            tiles |= reference_tiles_in(unary_union(strips), range(ortho.DETAIL_ZOOMS[0], max_zoom + 1))
        return tiles

    lat, lon = 50.1559508, 19.7562722
    rnd = random.Random(7)

    def strips(n, spread):
        found = []
        for _ in range(n):
            a1 = (lat + rnd.uniform(-spread, spread) / 111000, lon + rnd.uniform(-spread, spread) / 71000)
            length, angle = rnd.uniform(30, 600), rnd.uniform(0, 2 * math.pi)
            found.append({"anchor1": a1, "anchor2": (a1[0] + length * math.sin(angle) / 111000,
                                                      a1[1] + length * math.cos(angle) / 71000)})
        return found
    circle = ar.Circle(lat, lon, 300)
    for lines, max_zoom in ((strips(5, 300), 21), (strips(30, 150), 21), (strips(3, 100), 19), ([], 21)):
        expected = reference(lines, circle, max_zoom)
        assert ortho.tiles_to_cache(lines, circle, max_zoom) == expected
        assert max(z for z, _, _ in expected) == (max_zoom if lines else 16)


def _funnel(tmp_path, monkeypatch, **values) -> dict:
    """search.Plan.funnel of a search in this process (offline, the lines not saved)."""
    for key, v in OFFLINE_ENV.items():
        monkeypatch.setenv(key, v)
    import search
    from params import SearchParams
    params = SearchParams(water="off", fill_gaps="off", **values)
    plan = search.plan_search(params, search.Paths(str(tmp_path), str(tmp_path / "work")), lambda kind, text: None)
    lines, _ = search.search_lines(plan)
    return {**plan.funnel, "found_lines": len(lines.results)}


def test_funnel_of_the_line_search(tmp_path, monkeypatch):
    """The counts of the line search (search.Plan.funnel, F19's job_funnel) are those printed for the
    Żabi Koń clip; a tiled area sums its tiles and gives the lines of one grid."""
    import jobs as jb
    funnel = _funnel(tmp_path / "clip", monkeypatch, elevation_file=os.path.join(DATA, "zabi_kon_nmt.tif"),
                     surface_file=os.path.join(DATA, "zabi_kon_nmpt.tif"), northing=254608, easting=553966,
                     radius=290)
    assert set(funnel) - {"found_lines"} == set(jb.FUNNEL_STEPS)
    assert {k: funnel[k] for k in ("grids", "anchors", "open", "checked", "lines")} == {
        "grids": 1, "anchors": ZABI_KON["anchors"], "open": ZABI_KON["open"], "checked": ZABI_KON["checked"],
        "lines": ZABI_KON["lines"]}
    assert funnel["lines"] == funnel["valid"] == funnel["found_lines"] and funnel["left_out"] == 0
    assert funnel["anchors"] >= funnel["anchors_kept"] >= funnel["open"] >= funnel["todo"]
    assert funnel["candidates"] >= funnel["checked"] >= funnel["found"] >= funnel["valid"]
    square = {"type": "Polygon", "coordinates": [[[19.7522, 50.1546], [19.7590, 50.1546], [19.7590, 50.1580],
                                                  [19.7522, 50.1580], [19.7522, 50.1546]]]}
    path = tmp_path / "square.geojson"
    path.write_text(json.dumps({"type": "Feature", "properties": {}, "geometry": square}))
    area = {"elevation_file": os.path.join(DATA, "zabi_kon_nmt.tif"), "area": str(path), "max_length": 150}
    one = _funnel(tmp_path / "one", monkeypatch, **area)
    tiled = _funnel(tmp_path / "tiled", monkeypatch, **area, tile_size=150)
    assert one["grids"] == 1 and tiled["grids"] > 1
    assert one["lines"] == tiled["lines"] == one["found_lines"] == tiled["found_lines"] > 0
    assert tiled["valid"] >= tiled["lines"]  # the tiles' overlaps find some lines twice


def test_run_saved_by_children_as_in_process(tmp_path, monkeypatch):
    """search.save_run with the line files written by child processes (saving.py) gives every
    file of the run byte for byte as the search's own process writes it, on the Żabi Koń clip
    (the profiles of lineprofiles' batch, every line's for a circle)."""
    import dataclasses
    from datetime import datetime

    import saving
    import search
    from params import SearchParams
    for name, value in OFFLINE_ENV.items():
        monkeypatch.setenv(name, value)
    paths = search.Paths(str(tmp_path), str(tmp_path / "work"))
    values = dict(elevation_file=os.path.join(DATA, "zabi_kon_nmt.tif"),
                  surface_file=os.path.join(DATA, "zabi_kon_nmpt.tif"), water="off", fill_gaps="off",
                  northing=254608, easting=553966, radius=290)
    plan = search.plan_search(SearchParams(**values), paths, lambda kind, text: None)
    plan = dataclasses.replace(plan, index_runs=False)
    lines = search.find_lines(plan, search.prepare_data(plan))
    assert len(lines.results) == ZABI_KON["lines"] and len(lines.results.profiles) == ZABI_KON["lines"]
    created = datetime(2026, 11, 3, 12, 0, 0)
    saved = {}
    for count in (1, 4, 2):
        folder = tmp_path / "runs" / f"by{count}"
        folder.mkdir(parents=True)
        monkeypatch.setattr(saving, "MIN_LINES", 10 ** 9 if count == 1 else 0)
        monkeypatch.setattr(saving, "processes", lambda threads, count=count: count)
        result = search.save_run(plan, lines, {"id": "r", "path": str(folder), "created": created, "name": "clip"})
        assert result.map_path == str(folder / "map.html")
        saved[count] = {name: (folder / name).read_bytes() for name in os.listdir(folder)}
        assert not (tmp_path / "work" / saving.FOLDER).exists()
    assert set(saved[1]) == {"map.html", "data.js", "lines.js", "lines.csv", "lines.geojson", "run.json",
                             "ATTRIBUTION.txt"}
    assert saved[4] == saved[1] and saved[2] == saved[1]
    assert saved[1]["data.js"].count(b"null]") == 0  # a circle: every line with its profile


def test_terrain_fallback_warning(monkeypatch):
    """The warning terrain_fallback from FALLBACK_WARN_SHARE of the land filled from fallbacks, never below;
    nothing counted when nothing was filled."""
    from types import SimpleNamespace
    import search
    import sources as src
    from messages import Note
    shares = {"share": 0.0}

    def origins(*args, **kwargs):
        share = shares["share"]
        return {"land_km2": 1.0, "fallback_share": share, "regions": [], "totals": {},
                "layers": [{"role": "source", "name": "Fine 1 m", "resolution": 1.0, "share": 1 - share},
                           {"role": "fallback", "name": "Coarse 10 m", "resolution": 10.0, "share": share}]}
    monkeypatch.setattr(src.filling, "terrain_origins", origins)
    source = SimpleNamespace(name="Fine 1 m", nmt=SimpleNamespace(native_res=1.0), sea_fill=None)
    fallback = SimpleNamespace(name="Coarse 10 m", nmt=SimpleNamespace(native_res=10.0))
    for share, warned in ((0.0999, False), (0.10, True), (1.0, True)):
        events = []
        plan = SimpleNamespace(source=source, grid=None, emit=lambda kind, text: events.append((kind, text)))
        shares["share"] = share
        search._terrain_sources(plan, "nmt.npy", None, None, [], ["filled.npy"], [(fallback, 5)], None, None, None)
        notes = [text for kind, text in events if kind == "warning"]
        assert bool(notes) == warned, share
        if warned:
            assert isinstance(notes[0], Note) and notes[0].code == "terrain_fallback"
            assert notes[0].params == {"percent": round(100 * share), "source": "Fine 1 m", "fallback": "Coarse 10 m"}
        assert any(kind == "info" and text.startswith("Terrain of the search area's land: ") for kind, text in events)
    events = []
    plan = SimpleNamespace(source=source, grid=None, emit=lambda kind, text: events.append((kind, text)))
    assert search._terrain_sources(plan, "nmt.npy", None, None, [], ["filled.npy"], [(fallback, 0)],
                                   None, None, None) is None and not events
