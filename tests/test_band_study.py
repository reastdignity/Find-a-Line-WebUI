"""The band study (tools/band_study.py): its definitions, the matching of spots by where they lie,
the comparison of a variant with its reference, and a small study of the Żabi Koń clip (in EPSG:8353,
with its surface model marking lines over trees) counted and compared offline."""

import json
import os
import sys

import numpy as np
import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools"))
import band_study as bs  # noqa: E402
import countcube as cc  # noqa: E402

DATA = os.path.join(REPO, "tests", "data")
OFFLINE_ENV = {"HTTP_PROXY": "http://127.0.0.1:9", "HTTPS_PROXY": "http://127.0.0.1:9", "NO_PROXY": "",
               "FINDALINE_PROGRESS": "text"}
SQUARE = {"type": "Polygon", "coordinates": [[[19.7522, 50.1546], [19.7590, 50.1546], [19.7590, 50.1580],
                                              [19.7522, 50.1580], [19.7522, 50.1546]]]}
ID = "studyland"


def test_definitions():
    """Every pair's bands exist with the same lengths on the cube's edges; the layer bands cover
    30-5000 m once; each area's configuration marks lines over trees within its square."""
    import area as ar
    import country
    from shapely.geometry import box
    names = [b.name for b in bs.BANDS]
    assert len(names) == len(set(names)) and len({n.lower() for n in names}) == len(names)
    bands = {b.name: b for b in bs.BANDS}
    for variant, reference in bs.PAIRS:
        assert bands[variant].lengths == bands[reference].lengths
        cc.Filters(length=bands[reference].lengths)
    layer = sorted(b.lengths for b in bs.BANDS if b.layer)
    assert layer[0][0] == 30 and layer[-1][1] == 5000
    assert all(a[1] == b[0] for a, b in zip(layer, layer[1:]))
    for area in bs.AREAS.values():
        config = bs.area_config(area)
        assert country.Country.from_config(config).config() == config
        assert config["options"]["nmpt"] == "mark"
        south, west, north, east = map(float, config["options"]["within"].split(","))
        assert ar.size_km2(box(west, south, east, north)) == pytest.approx(area.side_km ** 2, rel=0.01)


def test_setup_and_reset(tmp_path):
    """setup writes the configuration and the pairs; a changed definition is refused, --reset
    starts the area afresh."""
    data = str(tmp_path)
    assert bs.setup(data, ["sk-sulov"], say=lambda text: None) == 0
    path = tmp_path / "countries" / "sk-sulov" / "country.json"
    state = json.loads(path.read_text(encoding="utf-8"))
    assert state["config"] == bs.area_config(bs.AREAS["sk-sulov"])
    assert state["study"]["pairs"] == [list(p) for p in bs.PAIRS]
    assert bs.setup(data, ["sk-sulov"], say=lambda text: None) == 0
    state["config"]["bands"] = state["config"]["bands"][:1]
    path.write_text(json.dumps(state), encoding="utf-8")
    (tmp_path / "countries" / "sk-sulov" / "area.geojson").write_text("{}", encoding="utf-8")
    assert bs.setup(data, ["sk-sulov"], say=lambda text: None) == 1
    assert bs.setup(data, ["sk-sulov"], reset=True, say=lambda text: None) == 0
    assert json.loads(path.read_text(encoding="utf-8"))["config"] == bs.area_config(bs.AREAS["sk-sulov"])
    assert not (tmp_path / "countries" / "sk-sulov" / "area.geojson").exists()


def _spots(*lines):
    """The spot ids of lines given by their anchors' clusters (cx1, cy1, cx2, cy2) of the lattice."""
    a = np.array(lines, dtype=np.int64)
    return cc.cluster_spot_ids(a[:, 0], a[:, 1], a[:, 2], a[:, 3])


def test_matched():
    """A spot matches one whose ends each lie within TOLERANCE clusters (two east-west, one north-south:
    about cube v1's +-50 m), in either order; three clusters east-west or two north-south off is no
    match."""
    assert bs.TOLERANCE == (2, 1)
    ref = _spots((200, 200, 230, 200), (200, 200, 200, 240), (500, 500, 530, 500), (700, 700, 730, 700))
    var = _spots((202, 201, 228, 199),      # each end two clusters east-west and one north-south off at most
                 (200, 240, 199, 200),      # the same line north-south, its first end the other one
                 (503, 500, 533, 500),      # three clusters east-west off
                 (700, 702, 730, 702))      # two clusters north-south off
    assert bs.matched(ref, var).tolist() == [True, True, False, False]
    assert bs.matched(var, ref).tolist() == [True, True, False, False]
    assert bs.matched(ref, var, tolerance=3).tolist() == [True, True, True, True]  # one number: both axes
    assert bs.matched(ref, ref, tolerance=0).all()
    assert not bs.matched(ref, np.zeros(0, dtype=np.int64)).any()
    assert len(bs.matched(np.zeros(0, dtype=np.int64), ref)) == 0


def _counts(cells, spots, trees_over=()):
    """Counts of one line per cell (i, j) of the lattice (level 1) and of spots, of the length bin
    30-60 m; the cells in trees_over have their line over trees."""
    record = 1 << cc.LENGTH_SHIFT
    keys = np.concatenate([cc.pack_keys(np.array([i]), np.array([j]),
                                        np.array([[record | (1 << (cc.TREES_BIT + ((i, j) in trees_over))), 0]]))
                           for i, j in cells])
    ids = _spots(*spots) if spots else np.zeros(0, dtype=np.int64)
    records = np.array([[record | (1 << cc.TREES_BIT), 0]] * len(ids), dtype=np.int64).reshape(-1, 2)
    keys, n = cc.sum_keys(keys, np.ones(len(keys), dtype=np.int64))
    return bs.Counts(keys, n, ids, records)


def test_compare_counts():
    """The same counts match fully; a cell the variant misses is lost, one only it has is added."""
    ref = _counts([(1, 1), (3, 3)], [(20, 20, 21, 20), (60, 60, 61, 60)])
    same = bs.compare_counts(ref, ref)
    assert same["spots"]["recall"] == same["spots"]["precision"] == 1.0
    assert same["cells"]["1"]["lost"] == same["cells"]["1"]["added"] == 0.0
    assert same["lines"]["ratio"] == 1.0
    var = _counts([(1, 1), (5, 5)], [(20, 20, 21, 20), (100, 100, 101, 100)])
    other = bs.compare_counts(ref, var)
    assert other["spots"]["recall"] == other["spots"]["precision"] == 0.5
    assert other["cells"]["1"]["lost"] == other["cells"]["1"]["added"] == 0.5
    assert other["cells"]["4"]["lost"] == 0.0  # cells (1, 1) and (3, 3) lie in the level-4 cell (0, 0)


def test_open_filter():
    """bits(trees' "not over" bit) keeps the lines not over trees and the spots with such a line."""
    c = _counts([(1, 1), (2, 2)], [(20, 20, 21, 20)], trees_over=[(2, 2)])
    open_ = c.bits(1 << cc.TREES_BIT)
    assert len(open_.keys) == 1 and len(open_.ids) == 1


def _krovak(path, out):
    """A clip reprojected to EPSG:8353 (S-JTSK [JTSK03] / Krovak East North), 1 m."""
    import rasterio as rio
    from rasterio.warp import Resampling, calculate_default_transform, reproject
    with rio.open(path) as src:
        transform, width, height = calculate_default_transform(src.crs, "EPSG:8353", src.width, src.height,
                                                               *src.bounds, resolution=1.0)
        profile = src.profile.copy()
        profile.update(crs="EPSG:8353", transform=transform, width=width, height=height, nodata=np.nan,
                       dtype="float32")
        with rio.open(out, "w", **profile) as dst:
            reproject(rio.band(src, 1), rio.band(dst, 1), src_nodata=src.nodata, dst_nodata=np.nan,
                      resampling=Resampling.bilinear)
    return str(out)


@pytest.fixture(scope="module")
def study(tmp_path_factory):
    """The clip counted with a reference R (1 m), V (R with other tiles) and C (2 m), the surface
    model marking lines over trees, and the study's comparison of V and C with R."""
    import country
    saved = {k: os.environ.get(k) for k in OFFLINE_ENV}
    os.environ.update(OFFLINE_ENV)
    try:
        base = tmp_path_factory.mktemp("study")
        area = base / "square.geojson"
        area.write_text(json.dumps({"type": "Feature", "properties": {}, "geometry": SQUARE}))
        band = {"lengths": [30, 150], "model": "formula", "slope_threshold": 45}
        config = {"id": ID, "name": "Studyland", "source": "files", "area": str(area),
                  "bands": [{"name": "R", "resolution": 1.0, "core_m": 200, "layer": True, **band},
                            {"name": "V", "resolution": 1.0, "core_m": 400, "layer": False, **band},
                            {"name": "C", "resolution": 2.0, "core_m": 400, "layer": False, **band}],
                  "tension": [[30, 2.5], [300, 6.0]], "rig": {"webbing_weight": 41.0, "stretch": 2.1},
                  "options": {"nmpt": "mark", "water": "off", "coastline": "copernicus", "fill_gaps": "off",
                              "elevation_file": _krovak(os.path.join(DATA, "zabi_kon_nmt.tif"), base / "nmt.tif"),
                              "surface_file": _krovak(os.path.join(DATA, "zabi_kon_nmpt.tif"), base / "nmpt.tif")}}
        data = base / "data"
        folder = data / "countries" / ID
        folder.mkdir(parents=True)
        (folder / "country.json").write_text(json.dumps({"config": config,
                                                         "study": {"pairs": [["V", "R"], ["C", "R"]]}}))
        assert country.main(["run", ID, "--data-dir", str(data), "--processes", "0", "--yes"]) == 0
        out = base / "out"
        assert bs.analyse(str(data), [ID], str(out), say=lambda text: None) == 0
        yield {"data": str(data), "out": out, "results": json.loads((out / "study.json").read_text(encoding="utf-8"))}
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def test_study_of_the_clip(study):
    """V (the reference's lines in other tiles) matches R fully, over all lines and over those not
    over trees; C (2 m) is compared within [0, 1]; the surface model marked lines over trees; the
    report, the bins of 30-150 m, the bands' cost and the pictures are written."""
    result = study["results"][0]
    pairs = {p["variant"]: p for p in result["pairs"]}
    for part in ("all", "open"):
        v = pairs["V"][part]
        assert v["lines"]["ratio"] == 1.0
        assert v["spots"]["recall"] == v["spots"]["precision"] == 1.0
        assert v["cells"]["1"]["lost"] == v["cells"]["1"]["added"] == 0.0
    assert pairs["V"]["all"]["lines"]["reference"] > pairs["V"]["open"]["lines"]["reference"] > 0
    c = pairs["C"]["all"]
    assert 0.0 <= c["spots"]["recall"] <= 1.0 and 0.0 <= c["cells"]["1"]["lost"] <= 1.0
    assert sorted(pairs["C"]["bins"]) == ["100-150", "30-60", "60-100"]
    assert set(result["bands"]) == {"R", "V", "C"} and result["bands"]["R"]["seconds"] > 0
    assert all(os.path.exists(p["picture"]) for p in result["pairs"])
    text = (study["out"] / "study.md").read_text(encoding="utf-8")
    assert "Studyland (studyland)" in text and "Not over trees" in text
    # the cells named by their size at the area's latitude (50.16°: 30" are 0.60 x 0.93 km)
    assert result["cell_km"]["1"] == pytest.approx([0.595, 0.927], abs=0.005) and "Lost 0.6x0.9 km" in text
    assert result["cluster_m"] == pytest.approx([29.8, 46.3], abs=0.2) and "60 x 46 m" in text


def test_missing_band(study, tmp_path):
    """A pair whose band has tiles left is reported as missing, not compared."""
    import shutil
    import sqlite3
    data = tmp_path / "data"
    shutil.copytree(os.path.join(study["data"], "countries"), data / "countries")
    db = sqlite3.connect(str(data / "countries" / ID / "manifest.sqlite"))
    db.execute("UPDATE tiles SET status = 'pending' WHERE band = 'C'")
    db.commit()
    db.close()
    result = bs.analyse_area(str(data), ID)
    pairs = {p["variant"]: p for p in result["pairs"]}
    assert "missing" in pairs["C"] and "all" in pairs["V"]
