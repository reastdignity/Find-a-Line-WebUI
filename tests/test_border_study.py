"""The border study (tools/border_study.py): the classes of a line by the countries holding its anchors,
and a study of the Żabi Koń clip split into two countries by a meridian through its tower, counted
offline: its classes add up to one count of the box, the lines across the border are those a brute
force finds, a run resumes and refuses another definition; spots reframed into another CRS match
themselves; a cube's lines near a border and the estimate of the report."""

import json
import os
import sys

import numpy as np
import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools"))
import border_study as bs  # noqa: E402
import countcube as cc  # noqa: E402

DATA = os.path.join(REPO, "tests", "data")
CLIP = os.path.join(DATA, "zabi_kon_nmt.tif")
OFFLINE_ENV = {"HTTP_PROXY": "http://127.0.0.1:9", "HTTPS_PROXY": "http://127.0.0.1:9", "NO_PROXY": "",
               "FINDALINE_PROGRESS": "text"}
BOX = "50.1546,19.7522,50.1580,19.7590"  # the clip's square of tests/test_country.py
BORDER_LON = 19.7561  # just west of the tower: lines from it to the rocks west of it cross the border


def _polygon_file(path, west, east) -> str:
    ring = [[west, 50.13], [east, 50.13], [east, 50.18], [west, 50.18], [west, 50.13]]
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"type": "Feature", "properties": {}, "geometry": {"type": "Polygon", "coordinates": [ring]}}, f)
    return str(path)


def _config():
    import country
    return country.Country.from_config(
        {"id": "borderland", "name": "Borderland", "source": "files", "area": "unused",
         "bands": [{"name": "S", "lengths": [30, 150], "resolution": 1.0, "model": "formula",
                    "slope_threshold": 45, "core_m": 200, "layer": True},
                   {"name": "M", "lengths": [150, 300], "resolution": 2.0, "model": "sag",
                    "slope_threshold": 45, "core_m": 400, "layer": True}],
         "tension": [[30, 2.5], [300, 6.0]], "rig": {"webbing_weight": 41.0, "stretch": 2.1},
         "options": {"nmpt": "off", "water": "off", "coastline": "copernicus", "fill_gaps": "off",
                     "elevation_file": CLIP}})


@pytest.fixture(scope="module")
def study(tmp_path_factory):
    """A run of the split clip: West (A) and East (B), both from the clip (no neighbour to fill)."""
    saved = {k: os.environ.get(k) for k in OFFLINE_ENV}
    os.environ.update(OFFLINE_ENV)
    base = tmp_path_factory.mktemp("border")
    west = bs.Side("files", _polygon_file(base / "west.geojson", 19.70, BORDER_LON), "West")
    east = bs.Side("files", _polygon_file(base / "east.geojson", BORDER_LON, 19.81), "East")
    place = bs.Place("clip", "Żabi Koń split", BOX, west, east, "a meridian")
    data, out = str(base / "data"), str(base / "out")
    folder = bs.run_place(place, "files", out, data, config=_config(), say=lambda text: None)
    yield {"place": place, "data": data, "out": out, "folder": folder, "config": _config()}
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


def test_line_classes():
    k1 = np.array([1, 2, 1, 2, 0, 1, 3, 3])
    k2 = np.array([1, 2, 2, 1, 1, 0, 1, 3])
    assert bs.line_classes(k1, k2).tolist() == [0, 1, 2, 2, 3, 3, 3, 3]
    assert bs.CLASSES[2] == "ab"


def _one_grid(study, band):
    """The lines of one grid over the band's grown area with first anchors in the counted box: the
    TileCounter of them all, and the parts themselves."""
    import country
    import search
    folder, data, config = study["folder"], study["data"], study["config"]
    d = json.load(open(os.path.join(folder, "study.json"), encoding="utf-8"))["definition"]
    b = config.band(band)
    work = os.path.join(data, "work", f"reference-{band}")
    os.makedirs(work, exist_ok=True)
    plan = bs._band_plan(config, b, "files", os.path.join(folder, f"area-{band}.geojson"), data, work,
                         lambda kind, text: None)
    counted = tuple(d["counted"])
    counter = cc.TileCounter(plan.grid, tuple(d["origin"]), counted, b.lengths, False)
    parts = []

    def sink(part):
        counter(part)
        parts.append({k: np.asarray(part.columns[k]).copy() for k in ("a1", "a2", "length")})

    search.count_tile(plan, search.prepare_data(plan), counted, sink, country.tension_table(config, b, plan))
    return plan, counter.result(), parts, d


@pytest.mark.parametrize("band", ["S", "M"])
def test_classes_add_up_to_one_grid(study, band):
    """The classes of the tiles add up to the count of one grid (lines per key, spots merged), the
    lines across the border are those whose anchors' pixel centres lie one in each outline, and
    each side's heights came from the file itself."""
    import area as ar
    import shapely
    folder = study["folder"]
    plan, reference, parts, d = _one_grid(study, band)
    paths = [p for name in bs.CLASSES for p in bs._class_tiles(folder, band, name)]
    keys, counts, ids, records = bs._merged(paths)
    assert reference.lines > 50
    assert np.array_equal(keys, reference.line_keys) and np.array_equal(counts, reference.line_counts)
    assert np.array_equal(ids, reference.spot_ids) and np.array_equal(records, reference.spot_records)
    # brute force: the anchors' centres in the outlines (in the grid's CRS), the counted lines only
    outlines = {k: ar.project(bs.outline_of(s, os.path.join(study["data"], "cache")), "EPSG:4326", plan.crs)
                for k, s in (("a", study["place"].a), ("b", study["place"].b))}
    a1 = np.concatenate([p["a1"] for p in parts])
    a2 = np.concatenate([p["a2"] for p in parts])
    length = np.concatenate([p["length"] for p in parts])
    x1, y1 = plan.grid.pixel_to_xy(a1[:, 0], a1[:, 1])
    x2, y2 = plan.grid.pixel_to_xy(a2[:, 0], a2[:, 1])
    first = (x1 < x2) | ((x1 == x2) & (y1 <= y2))
    fx, fy = np.where(first, x1, x2), np.where(first, y1, y2)
    left, bottom, right, top = d["counted"]
    lo, hi = study["config"].band(band).lengths
    kept = (fx >= left) & (fx < right) & (fy >= bottom) & (fy < top) & (length >= lo) & (length < hi)
    code = lambda x, y: (shapely.contains_xy(outlines["a"], x, y).astype(int)
                         | (shapely.contains_xy(outlines["b"], x, y).astype(int) << 1))
    classes = bs.line_classes(code(x1, y1), code(x2, y2))[kept]
    for k, name in enumerate(bs.CLASSES):
        _, n, _, _ = bs._merged(bs._class_tiles(folder, band, name))
        assert int(n.sum()) == int(np.count_nonzero(classes == k)), name
    assert np.count_nonzero(classes == 0) and np.count_nonzero(classes == 1) and np.count_nonzero(classes == 2)
    metas = [json.load(open(os.path.join(folder, "tiles", band, f), encoding="utf-8"))
             for f in os.listdir(os.path.join(folder, "tiles", band)) if f.endswith(".json")]
    for side in ("a", "b"):
        fill = {k: sum(m["fill"][side][k] for m in metas) for k in ("pixels", "own", "neighbour", "fallback", "none")}
        assert fill["pixels"] > 0 and fill["own"] == fill["pixels"]


def test_resume_and_definition(study, monkeypatch):
    """A run again counts no tile; another definition is refused unless reset."""
    import search
    monkeypatch.setattr(search, "count_tile", lambda *a, **k: pytest.fail("a done tile was counted again"))
    bs.run_place(study["place"], "files", study["out"], study["data"], config=study["config"], say=lambda t: None)
    import dataclasses
    other = dataclasses.replace(study["place"], box="50.1550,19.7522,50.1580,19.7590")
    with pytest.raises(ValueError, match="another definition"):
        bs.run_place(other, "files", study["out"], study["data"], config=study["config"], say=lambda t: None)


def test_reframed_spots():
    """Spots moved into another CRS and back match themselves within a cluster; in their own frame
    they keep their ids."""
    from pyproj import Transformer
    rng = np.random.default_rng(3)
    to = Transformer.from_crs("EPSG:4326", "EPSG:2180", always_xy=True)
    x, y = to.transform(20.0 + rng.random(200) * 0.05, 49.2 + rng.random(200) * 0.03)
    angle = rng.random(200) * 2 * np.pi
    span = 100 + rng.random(200) * 2000
    origin = cc.origin_of((min(x) - 6000, min(y) - 6000, 0, 0))
    ids = np.unique(cc.spot_ids(x, y, x + span * np.cos(angle), y + span * np.sin(angle), origin))
    assert np.array_equal(np.sort(bs.reframed_spots(ids, origin, "EPSG:2180", origin, "EPSG:2180")), ids)
    krovak = Transformer.from_crs("EPSG:2180", "EPSG:8353", always_xy=True)
    kx, ky = krovak.transform(min(x) - 6000, min(y) - 6000)
    other = cc.origin_of((kx - 10000, ky - 10000, 0, 0))
    there = bs.reframed_spots(ids, origin, "EPSG:2180", other, "EPSG:8353")
    back = np.unique(bs.reframed_spots(np.unique(there), other, "EPSG:8353", origin, "EPSG:2180"))
    import band_study
    assert band_study.matched(ids, back, 2).all()
    assert band_study.matched(ids, np.unique(there), 0).mean() < 0.5  # another frame: other ids


def test_exposure_and_report(study, monkeypatch):
    """A cube of the lines of A has every line within reach of B's border (the clip is small); the
    report's estimate holds the run's lines and spots across the border as measured, and carries the
    ratio over to the cube's lines outside the box; study.md and the picture are written."""
    folder, data, out = study["folder"], study["data"], study["out"]
    d = json.load(open(os.path.join(folder, "study.json"), encoding="utf-8"))["definition"]
    cube_dir = os.path.join(data, "countries", "west", "cube")  # where the report finds the exposure's cube
    aa = [p for band in ("S", "M") for p in bs._class_tiles(folder, band, "aa")]
    cc.build(aa, cube_dir, {"id": "west", "name": "West", "crs": d["crs"], "origin": d["origin"]})
    with open(os.path.join(cube_dir, "area.geojson"), "w", encoding="utf-8") as f:
        source = json.load(open(study["place"].a.area, encoding="utf-8"))
        json.dump({**source, "properties": {"area": study["place"].a.area}}, f)
    exposed = bs.exposure(cube_dir, {"East": study["place"].b.area}, os.path.join(data, "cache"))
    # the meridian over 50.13-50.18 (5.56 km) and the 200 m of the top and bottom edges next to it
    assert exposed["border_km"]["East"] == pytest.approx(5.96, abs=0.1)
    lines = exposed["lines"]["bins"]
    assert sum(b["all"] for b in lines) == int(bs._merged(aa)[1].sum()) > 0
    assert all(b["near"]["East"] == b["all"] for b in lines)
    bs._write_json(os.path.join(out, "exposure.json"), exposed)
    monkeypatch.setattr(bs, "MIN_NEAR", 0)  # the clip has few lines: carry every bin's ratio over
    assert bs.analyse(out, data, say=lambda t: None) == 0
    result = json.load(open(os.path.join(out, "study.json"), encoding="utf-8"))
    run = result["runs"][0]
    assert run["border_km"] > 0.3 and run["km2_a"] > 0 and run["km2_b"] > 0
    found = result["estimates"][0]
    ab = sum(e["classes"]["ab"]["lines"] for e in run["bands"].values())
    assert found["boxes"] == ["clip-files"] and found["measured"] == ab > 0
    # the cube's lines (the run's of A, all near the border) whose cell's centre lies outside the box: the
    # rest, carried over with the run's ratio in every bin with lines of A near the border
    keys, counts = cc.Cube(cube_dir).array("lines", 1).T
    x, y = bs._cell_centres(keys, tuple(d["origin"])).T
    left, bottom, right, top = d["counted"]
    in_box = (x >= left) & (x < right) & (y >= bottom) & (y < top)
    assert found["rest"] == int(counts[~in_box].sum())
    for b in found["bins"]:
        assert b["estimate"] == b["measured"] + (round(b["ratio"] * b["rest"]) if b["carried"] else 0)
        assert b["carried"] == (b["aa_near"] > 0)
    assert found["estimate"] >= found["measured"]
    assert found["spots"]["measured"] == run["spots"]["ab"] > 0 and found["spots"]["estimate"] >= run["spots"]["ab"]
    assert found["check"] == {"cube": "west", "bins": []}  # no 1 km cell lies wholly inside the small box
    assert exposed["lines"]["near_total"]["East"] == exposed["lines"]["total"]
    text = open(os.path.join(out, "study.md"), encoding="utf-8").read()
    assert "Żabi Koń split" in text and "| S | 30-60 m |" in text and "Estimate with the ratio of clip-files" in text
    assert os.path.exists(os.path.join(out, "pictures", "clip-files.png"))


def test_resampling_runs_and_report(study, tmp_path, monkeypatch):
    """A run with a resampling method counts into its own folder with sources.filling's setting on
    (and off again afterwards), the method in its definition; the report compares every run with the
    run of the other primary that has no method: here copies of one count, so every spot is found."""
    import shutil
    import search
    import sources.filling as filling
    out, data, place = str(tmp_path / "out"), study["data"], study["place"]
    shutil.copytree(study["folder"], os.path.join(out, "clip-files"))
    seen, real = [], search.count_tile
    monkeypatch.setattr(search, "count_tile",
                        lambda *a, **k: (seen.append(filling.NEIGHBOUR_RESAMPLING), real(*a, **k))[1])
    folder = bs.run_place(place, "files", out, data, config=study["config"], say=lambda t: None, resampling="nearest")
    assert os.path.basename(folder) == "clip-files-nearest" and seen and set(seen) == {"nearest"}
    assert filling.NEIGHBOUR_RESAMPLING is None
    assert json.load(open(os.path.join(folder, "study.json"), encoding="utf-8"))["definition"]["resampling"] == "nearest"
    with pytest.raises(ValueError, match="resampling"):
        bs.run_place(place, "files", out, data, config=study["config"], say=lambda t: None, resampling="lanczos")
    for band in ("S", "M"):  # the clip has no neighbour: the same count
        for name in bs.CLASSES:
            for mine, theirs in zip(bs._merged(bs._class_tiles(folder, band, name)),
                                    bs._merged(bs._class_tiles(study["folder"], band, name))):
                assert np.array_equal(mine, theirs)
    # the same count once more as the run of another primary, the source of B
    other = os.path.join(out, "clip-east")
    shutil.copytree(study["folder"], other)
    state = json.load(open(os.path.join(other, "study.json"), encoding="utf-8"))
    state["definition"]["primary"] = state["definition"]["place"]["b"]["source"] = "east"
    bs._write_json(os.path.join(other, "study.json"), state)
    assert bs.analyse(out, data, say=lambda t: None) == 0
    result = json.load(open(os.path.join(out, "study.json"), encoding="utf-8"))
    rows = result["resampling"]
    assert {(r["run"], r["reference"], r["class"]) for r in rows} == {
        ("clip-files", "clip-east", "bb"), ("clip-files", "clip-east", "ab"),
        ("clip-files-nearest", "clip-east", "bb"), ("clip-files-nearest", "clip-east", "ab"),
        ("clip-east", "clip-files", "aa"), ("clip-east", "clip-files", "ab")}
    assert len(rows) == 12 and {r["band"] for r in rows} == {"S", "M"} and sum(r["spots"][0] for r in rows) > 20
    for r in rows:
        assert r["resampling"] == ("nearest" if r["run"].endswith("nearest") else None)
        assert r["lines"][0] == r["lines"][1] > 0
        assert r["spots"][0] == r["spots"][1]  # those with both ends in the small box less 100 m: none in some
        assert r["reference_found"] == r["run_found"] == (1.0 if r["spots"][0] else None)
        assert r["cpu_seconds"] > 0 and r["seconds"] >= r["prepare_seconds"] > 0
        assert r["memory"]["rss"] > 0 and r["memory"]["private"] > 0
    # the two runs without a method of the place's two primaries are still compared as before
    assert {(a["band"], tuple(a["primaries"])) for a in result["agreements"]} == {("M", ("east", "files")),
                                                                                  ("S", ("east", "files"))}
    text = open(os.path.join(out, "study.md"), encoding="utf-8").read()
    assert "## The resampling of the neighbour's data" in text
    assert "| clip | M | clip-files-nearest | nearest | side |" in text and "| clip | S | clip-east | own | across |" in text
    assert "the neighbour's data resampled nearest" in text


def _outline(area):
    """An area of the coverage map's shapes (its covered part)."""
    import json
    from shapely.geometry import shape
    with open(bs.SHAPES, encoding="utf-8") as f:
        return next(shape(x["geometry"]).buffer(0) for x in json.load(f)["features"]
                    if x["properties"]["id"] == area and not x["properties"].get("rest"))


def test_neighbour_boxes_along_the_borders():
    """strip_share: of the neighbour's land within reach of the source's, the share inside its rough
    boxes; box_reach: every declared pair of the catalogue with an outline, from the coverage map's
    shapes (offline)."""
    from shapely.geometry import box
    a, b = box(10.0, 50.0, 11.0, 51.0), box(11.0, 50.0, 12.0, 51.0)  # b east of a
    whole = bs.strip_share(a, b, [(49.0, 52.0, 9.0, 13.0)])
    assert whole["share"] == pytest.approx(1.0) and whole["km2"] == pytest.approx(5.0 * 111.2, rel=0.03)
    half = bs.strip_share(a, b, [(49.0, 50.5, 9.0, 13.0)])  # (south, north, west, east): the southern half
    assert half["share"] == pytest.approx(0.5, abs=0.01) and half["km2"] == whole["km2"]
    assert bs.strip_share(a, b, [(49.0, 52.0, 11.5, 13.0)])["share"] == 0.0  # the box starts 35 km east of the border
    assert bs.strip_share(a, b, [])["share"] == 0.0
    assert bs.strip_share(a, box(11.2, 50.0, 12.0, 51.0), [(49.0, 52.0, 9.0, 13.0)]) is None  # 14 km apart
    # a region inside the other shape (a country holding it) is taken out of it first
    inside = bs.strip_share(box(10.0, 50.0, 12.0, 51.0), b, [(49.0, 52.0, 9.0, 13.0)])
    assert inside["km2"] == pytest.approx(whole["km2"], rel=0.02) and inside["share"] == pytest.approx(1.0)

    rows = bs.box_reach()
    import sources as src
    by_id = {s.id: s for s in (src.SOURCES.values() if isinstance(src.SOURCES, dict) else src.SOURCES)}
    declared = {(s.id, n) for s in by_id.values() for n in s.neighbours or () if s.coverage and by_id[n].coverage}
    assert {(r["source"], r["neighbour"]) for r in rows} == declared
    assert all(r["km2"] > 1 and (r["share"] is None or 0.0 <= r["share"] <= 1.0) for r in rows)
    share = {(r["source"], r["neighbour"]): r["share"] for r in rows}
    # Measured on 2026-11-05: Czechia's offline boxes keep inside the country, 20-42 % of its border strips
    # (the Saxon grid got 30 m data at Hrensko); since 2026-11-06 the border boxes (Source.border_boxes) hold
    # the rest, and every declared neighbour reaches its borders
    short = {pair: round(value, 3) for pair, value in share.items() if value is not None and value < 0.97}
    assert not short, short
    offline_only = bs.strip_share(*[_outline(i) for i in ("de-sn", "cz")],
                                  [b for _, b in src.SOURCES["czechia"].offline])
    assert offline_only["share"] < 0.5 and share[("saxony", "czechia")] > 0.97
    # the USA's outline is taken without Alaska, whose border is the source alaska's
    assert share[("british_columbia", "usa")] > 0.97 and share[("british_columbia", "alaska")] > 0.97
    report = bs.box_reach_report(rows)
    assert any(line.startswith("| saxony | czechia |") for line in report)
    assert sum(line.startswith("| ") for line in report) == len(rows) + 2  # the head and its rule
