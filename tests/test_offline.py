"""Searches on local files only, no network (any request goes to a closed port).

- A synthetic canyon: two plateaus 40 m above a 50 m wide floor, with a block of
  "trees" taller than the plateaus in its northern third.
- A 600 x 600 m clip of Żabi Koń (tests/data, see make_fixture.py) with known results.
"""

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
               "FINDALINE_PROGRESS": "text", "PYTHONIOENCODING": "utf-8"}


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
    assert len(glob.glob(str(tmp_path / "tiled" / "runs" / "*" / "tiles" / "*.pkl.gz"))) > 1
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
