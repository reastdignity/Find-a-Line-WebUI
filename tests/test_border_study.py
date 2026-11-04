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


def test_exposure_and_report(study, tmp_path):
    """A cube of the lines of A has every line within reach of B's border (the clip is small); the
    report's estimate from the run is then the run's lines across the border; study.md and the
    picture are written."""
    folder, data, out = study["folder"], study["data"], study["out"]
    d = json.load(open(os.path.join(folder, "study.json"), encoding="utf-8"))["definition"]
    cube_dir = str(tmp_path / "cube")
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
    assert bs.analyse(out, data, say=lambda t: None) == 0
    result = json.load(open(os.path.join(out, "study.json"), encoding="utf-8"))
    run = result["runs"][0]
    assert run["border_km"] > 0.3 and run["km2_a"] > 0 and run["km2_b"] > 0
    # every cell of the small box lies within reach of the border, so the cube's lines near it are the
    # run's lines of A near it: the estimate is the run's lines across the border (in the bins with A's)
    expected = 0
    for k in range(cc.LENGTH_BINS):
        ab = sum(e["classes"]["ab"]["bins"][k] for e in run["bands"].values())
        aa = sum(e["classes"]["aa"]["bins"][k] for e in run["bands"].values())
        expected += ab if aa else 0
    assert result["estimates"][0]["estimate"] == expected > 0
    text = open(os.path.join(out, "study.md"), encoding="utf-8").read()
    assert "Żabi Koń split" in text and "| S | 30-60 m |" in text and "Estimate from clip-files" in text
    assert os.path.exists(os.path.join(out, "pictures", "clip-files.png"))
