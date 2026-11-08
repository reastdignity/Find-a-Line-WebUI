"""tools/truth_analysis.py: the tolerance, the matching (either way round, a radius per line, the best by
the distance sum), every reason of a miss on a synthetic capture whose found lines are production's
(linesearch.find_valid_lines on the same grid and anchors), analyse and report (offline). No SlackMap data:
the known lines are made up."""

import json
import os
import sys

import numpy as np
import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools"))
import coverage_contrast  # noqa: E402
import truth_analysis as ta  # noqa: E402
from slackmap_data import KnownLine  # noqa: E402

CRS = "EPSG:32634"
LEFT, TOP, RES = 400000.0, 5500000.0, 1.0
ROWS, COLS = 300, 130
GRID = {"crs": CRS, "left": LEFT, "top": TOP, "res": RES, "shape": [ROWS, COLS]}
PARAMS = {"resolution": RES, "min_length": 20.0, "max_length": 120.0, "max_anchor_diff": 20.0,
          "max_anchor_diff_m": 50.0, "slope_threshold": 45.0, "min_elevation": None, "max_elevation": None,
          "high_above": 20.0, "min_height": None, "min_mean_height": None, "min_high_share": None,
          "max_wall_angle": 10.0, "min_prominence": None, "min_prominence_both": None, "min_drop": None,
          "nmpt": "reject", "model": "formula"}
# The regions of the synthetic canyon (rows): a known line across the middle of each
R_MATCHED, R_NEAR, R_MID, R_FILTERED, R_SEAM, R_WATER, R_SURFACE, R_HEIGHT = (range(30 * k, 30 * k + 30)
                                                                              for k in range(8))
R_WALL = range(240, 300)


def latlon(row: float, col: float):
    """[lat, lon] of a (fractional) pixel centre of GRID."""
    from pyproj import Transformer
    lon, lat = Transformer.from_crs(CRS, "EPSG:4326", always_xy=True).transform(LEFT + (col + 0.5) * RES,
                                                                               TOP - (row + 0.5) * RES)
    return [round(lat, 7), round(lon, 7)]


def known(line_id, a, b, type="highline", stated=None, decimals=7, flags=()):
    """A KnownLine between two (fractional) pixels of GRID (stated: the geodesic length unless given)."""
    from pyproj import Geod
    pa, pb = latlon(*a), latlon(*b)
    geodesic = Geod(ellps="WGS84").inv(pa[1], pa[0], pb[1], pb[0])[2]
    return KnownLine(id=line_id, a=tuple(pa), b=tuple(pb), stated_m=geodesic if stated is None else stated,
                     geodesic_m=geodesic, type=type, country="SK", decimals=decimals, flags=tuple(flags))


def terrain():
    """A canyon along the rows (rims 100 m at cols <= 30 and >= 90, a floor at 50 m, vertical walls) and
    in each region what makes its known line fail; the surface (the terrain but a band of trees), the
    masks and the area."""
    z = np.full((ROWS, COLS), 50.0)
    z[:, :31] = 100.0
    z[:, 90:] = 100.0
    z[R_NEAR.start:R_NEAR.stop, 31:46] = 97.0       # a ledge 15 m wide just below the left rim
    z[R_MID.start:R_MID.stop, 55:66] = 98.0         # a hump in the middle of the floor
    z[R_HEIGHT.start:R_HEIGHT.stop, 90:] = 160.0    # the right rim 60 m higher
    z[104:107, 10:13] = np.nan                      # no data on the left plateau
    z = z.astype(np.float32)
    surface = z.copy()
    surface[R_SURFACE.start:R_SURFACE.stop, 58:63] = 95.0  # trees 45 m tall on the floor
    filled = np.zeros(z.shape, dtype=bool)
    filled[R_SEAM.start:R_SEAM.stop, :31] = True    # a filled gap reaching the left rim
    water = np.zeros(z.shape, dtype=bool)
    water[R_WATER.start:R_WATER.stop, 31:90] = True  # a lake on the floor
    mask = np.ones(z.shape, dtype=bool)
    mask[:, 124:] = False                           # the area ends before the right edge
    return z, surface, filled, water, mask


def anchors_of(z, filled, mask):
    """Step 2 as search._anchors: the steep pixels in the area less those at the seams of filled gaps;
    the anchors of the region R_FILTERED left out as a prominence limit would."""
    import helpers as sh
    import search
    anchors = sh.find_significant_slopes(z, RES, PARAMS["slope_threshold"], mask).astype(np.int64)
    anchors = anchors[~search.at_seams(filled, anchors)]
    return np.ascontiguousarray(anchors[(anchors[:, 0] < R_FILTERED.start) | (anchors[:, 0] >= R_FILTERED.stop)])


def found_lines(z, surface, anchors):
    """Production's lines of the grid (find_valid_lines with PARAMS), as lines.npz holds them."""
    import helpers as sh
    import linesearch as ls
    table = ls.find_valid_lines(z, surface, anchors, RES, PARAMS["min_length"], PARAMS["max_length"],
                                nmpt_mode="reject", threads=2, max_dh_ratio=PARAMS["max_anchor_diff"] / 100,
                                max_dh=PARAMS["max_anchor_diff_m"], high_above=PARAMS["high_above"],
                                limits=sh.LineLimits(max_wall_angle=PARAMS["max_wall_angle"]))
    t = table.columns
    a1 = np.array([latlon(r, c) for r, c in t["a1"].tolist()])
    a2 = np.array([latlon(r, c) for r, c in t["a2"].tolist()])
    group = t["a1"][:, 0] // 10
    rep = np.zeros(len(group), dtype=bool)
    rep[np.unique(group, return_index=True)[1]] = True
    nmpt = np.array([np.nan if v is None else v for v in t["clearance_nmpt"]], dtype=np.float64)
    return {"a1": a1, "a2": a2, "length": t["length"], "clearance": t["clearance"], "clearance_nmpt": nmpt,
            "over": np.zeros(len(group), dtype=bool), "rep": rep, "group": group.astype(np.int64)}


def known_lines():
    """One known line per case, (id, expected outcome or reason, expected "which")."""
    return [
        (known("m1", (15, 30), (15, 90)), "matched", None),
        (known("m2", (15, 90), (15, 30)), "matched", None),                       # the other way round
        (known("m3", (16, 30), (16, 90), stated=95.0, flags=("length_mismatch",)), "matched", None),
        (known("flat", (12, 10), (12, 90)), "no_steep_pixel", "a"),
        (known("out", (18, 30), (18, 127)), "outside_area", "b"),
        (known("near", (45, 30), (45, 90)), "clearance_near_anchor", None),
        (known("mid", (75, 30), (75, 90), type="midline"), "clearance_mid", None),
        (known("filtered", (105, 30), (105, 90)), "anchor_filtered", "both"),
        (known("nodata", (105, 11), (105, 90)), "no_data", "a"),
        (known("seam", (135, 30), (135, 90)), "seam_pixel", "a"),
        (known("water", (165, 45), (165, 90), type="midline"), "water_pixel", "a"),
        (known("trees", (195, 30), (195, 90)), "surface_obstacle", None),
        (known("dh", (225, 30), (225, 99.8)), "height_difference", None),
        (known("wall", (250, 30), (290, 90)), "wall_angle", None),
        (known("coarse", (-300, -300), (-300, -200), decimals=3, flags=("coarse_anchor",)), "unverifiable", None),
    ]


def write_capture(folder, cases, status="done"):
    """A cluster folder of the contract's capture format (truth_study.py run's)."""
    z, surface, filled, water, mask = terrain()
    anchors = anchors_of(z, filled, mask)
    cap = os.path.join(folder, "capture")
    os.makedirs(cap, exist_ok=True)
    grid = {**GRID, "params": PARAMS, "nmpt": "reject", "obstacles": None, "model": "formula", "rigging": None,
            "slope_threshold": PARAMS["slope_threshold"], "fall": 6.0, "layer_meta": {"source": "testland"},
            "source": "testland", "area_wgs84": [0, 0, 0, 0]}
    with open(os.path.join(cap, "grid.json"), "w") as f:
        json.dump(grid, f)
    np.savez_compressed(os.path.join(cap, "grids.npz"), elevation=z, surface=surface,
                        filled=filled.astype(np.uint8), joined=np.zeros(z.shape, np.uint8),
                        water=water.astype(np.uint8), mask=mask.astype(np.uint8))
    np.save(os.path.join(cap, "anchors.npy"), anchors)
    np.savez_compressed(os.path.join(cap, "lines.npz"), **found_lines(z, surface, anchors))
    import dataclasses
    with open(os.path.join(folder, "known.json"), "w", encoding="utf-8") as f:
        json.dump([dataclasses.asdict(line) for line, *_ in cases], f)
    with open(os.path.join(folder, "capture.json"), "w") as f:
        json.dump({"status": status, "seconds": 1.0, "options": "--lat 0 --lon 0"}, f)
    return folder


@pytest.fixture(scope="module")
def study(tmp_path_factory):
    out = tmp_path_factory.mktemp("truth")
    cases = known_lines()
    write_capture(str(out / "testland-001"), cases)
    write_capture(str(out / "testland-002"), cases[:1], status="failed")  # listed, not counted
    return str(out), cases


def test_tolerance():
    line = known("t", (0, 0), (0, 50))
    assert ta.tolerance(line) == 10.0                                          # the floor
    assert ta.tolerance(known("t", (0, 0), (0, 50), stated=200.0)) == pytest.approx(20.0)  # 10 % of L
    coarse = known("t", (0, 0), (0, 50), decimals=3, flags=("coarse_anchor",))
    assert ta.tolerance(coarse) == pytest.approx(111.0)                        # the quantum of 0.001 deg
    assert ta.tolerance(known("t", (0, 0), (0, 50), decimals=2, flags=("coarse_anchor",))) == pytest.approx(1110.0)
    assert ta.tolerance(known("t", (0, 0), (0, 50), decimals=4)) == 10.0      # not coarse: no quantum
    assert ta.length_bin(29.9) == "0-30" and ta.length_bin(30) == "30-50" and ta.length_bin(500) == "500+"


def _found(pairs):
    """FoundLines of (row, col) pixel pairs of GRID."""
    a1 = np.array([latlon(*p) for p, _ in pairs]).reshape(-1, 2)
    a2 = np.array([latlon(*q) for _, q in pairs]).reshape(-1, 2)
    n = len(pairs)
    return ta.FoundLines(a1=a1, a2=a2, length=np.zeros(n), clearance=np.ones(n), clearance_nmpt=np.full(n, np.nan),
                         over=np.zeros(n, bool), rep=np.ones(n, bool), group=np.arange(n),
                         xy1=ta._xy(GRID, a1), xy2=ta._xy(GRID, a2))


def test_match():
    found = _found([((100, 30), (100, 90)),     # 0: 12 m off at a's end
                    ((88, 30), (100, 92)),      # 1: a few m off at both ends of "best"
                    ((100.5, 30), (100.5, 91)),  # 2: nearer still
                    ((200, 30), (200, 90))])    # 3
    lines = [known("narrow", (112, 30), (100, 90), stated=60.0),   # tol 10: line 0 is 12 m off at a
             known("wide", (112, 30), (100, 90), stated=150.0),    # tol 15: line 0 within
             known("best", (100, 30), (100, 90)),                  # 0, 1 and 2 within 10 m: 0 the nearest (0 m)
             known("other", (99, 90), (101, 30)),                  # the other way round: line 0 or 2
             known("none", (250, 30), (250, 90))]                  # nothing within 10 m
    index = ta.match(lines, found, GRID)
    assert index[0] is None and index[1] == 0
    assert index[2] == 0
    assert index[3] in (0, 2) and index[3] == min((0, 2), key=lambda k: ta._distances(
        ta._xy(GRID, [lines[3].a])[0], ta._xy(GRID, [lines[3].b])[0], 10.0, found)[k])
    assert index[4] is None
    assert ta.match([], found, GRID) == [] and ta.match(lines[:1], _found([]), GRID) == [None]


def test_matched_with_a_radius_per_line():
    """coverage_contrast.matched: one radius or one per line of the first set."""
    a1 = np.array([[0.0, 0.0], [100.0, 0.0]])
    a2 = np.array([[50.0, 0.0], [150.0, 0.0]])
    b1 = np.array([[12.0, 0.0], [100.0, 20.0]])
    b2 = np.array([[50.0, 0.0], [150.0, 0.0]])
    assert coverage_contrast.matched(a1, a2, b1, b2, 15).tolist() == [True, False]
    assert coverage_contrast.matched(a1, a2, b1, b2, np.array([10.0, 25.0])).tolist() == [False, True]
    assert coverage_contrast.matched(a1, a2, b1, b2, [15.0, 25.0]).tolist() == [True, True]


def test_reasons(study):
    """Every case of the synthetic capture gets its outcome and reason; the found lines are production's,
    so no "missed" line is one the search finds."""
    out, cases = study
    c = ta.load_capture(os.path.join(out, "testland-001"))
    assert len(c.found) > 100 and len(c.anchors) > 500 and c.nmpt == "reject" and c.sag_table is None
    index = ta.match(c.known, c.found, c.grid)
    got = {}
    for line, k in zip(c.known, index):
        r = ta.diagnose(c, line, k)
        got[line.id] = r
        assert r["reason"] in (None, *ta.REASONS)
        assert json.loads(json.dumps(ta._plain(r))) is not None
    for line, expected, which in cases:
        r = got[line.id]
        assert (r["outcome"] if expected == "matched" else r["reason"]) == expected, (line.id, r["reason"], r["note"])
        assert r["which"] == which, line.id
    m = got["m1"]["match"]
    assert m["d"] == [pytest.approx(0, abs=0.05)] * 2 and not m["swapped"] and m["clearance"] > 0
    assert m["angles"] == [pytest.approx(0, abs=1e-6)] * 2 and m["canopy"] == [0.0, 0.0]
    assert got["m2"]["match"]["swapped"] and got["m2"]["match"]["index"] == m["index"]
    assert got["m3"]["verifiable"] and got["coarse"]["verifiable"] is False
    near, mid = got["near"]["best"], got["mid"]["best"]
    assert near["rule_failure"]["near"] and near["rule_failure"]["from_a1"] == pytest.approx(1.0)
    assert not mid["rule_failure"]["near"] and mid["rule_failure"]["from_a1"] == pytest.approx(25.0)
    assert got["near"]["funnel"]["terrain"] == 0 and got["near"]["funnel"]["height"] > 0
    trees = got["trees"]
    assert trees["funnel"]["terrain"] > 0 and trees["funnel"]["surface"] == 0 and trees["best"]["clearance_nmpt"] < 0
    assert got["dh"]["funnel"]["height"] == 0 and abs(got["dh"]["best"]["dh"]) > got["dh"]["best"]["dh_limit"]
    wall = got["wall"]
    assert wall["funnel"]["surface"] > 0 and wall["funnel"]["wall"] == 0 and min(wall["best"]["angles"]) > 10
    assert got["seam"]["ends"][0]["steep_at_seam"] > 0 and got["seam"]["ends"][0]["anchors"] == 0
    assert got["water"]["ends"][0]["water"] and not got["water"]["ends"][0]["steep"]
    assert got["flat"]["ends"][0]["steep"] is False and got["flat"]["ends"][1]["anchors"] > 0
    assert got["filtered"]["ends"][0]["steep"] and got["filtered"]["ends"][0]["anchors"] == 0
    assert got["trees"]["ends"][0]["canopy"] == 0.0
    assert got["near"]["near"]["best"] is not None and got["near"]["exact"]["valid"] is False
    assert got["m1"]["exact"]["valid"] is True


def test_analyse_and_report(study):
    out, cases = study
    data = ta.analyse(out)
    assert os.path.exists(os.path.join(out, "testland-001", "analysis.json"))
    assert os.path.exists(os.path.join(out, "analysis.json"))
    places = {s["cluster"]: s for s in data["clusters"]}
    assert places["testland-002"]["analysed"] is False and places["testland-002"]["known"] == 1
    one = places["testland-001"]
    assert one["known"] == len(cases) and one["matched"] == 3 and one["source"] == "testland"
    assert 0 < one["spots_without_known"] < one["found_spots"]
    assert len(data["records"]) == len(cases)  # the failed cluster's line is not counted
    text = ta.report(out)
    study_json = json.load(open(os.path.join(out, "study.json"), encoding="utf-8"))
    overall = study_json["overall"]
    assert overall["all"]["known"] == 15 and overall["all"]["matched"] == 3 and overall["all"]["verifiable"] == 14
    assert overall["highline"]["known"] == 13 and overall["midline"]["known"] == 2
    assert overall["midline"]["matched"] == 0
    assert overall["all"]["reasons"]["unverifiable"] == 1 and overall["midline"]["reasons"]["clearance_mid"] == 1
    assert overall["all"]["recall"] == pytest.approx(3 / 14, abs=1e-4)
    assert overall["all"]["known_clean"] == 13 and overall["all"]["matched_clean"] == 2
    assert sum(overall["all"]["reasons"].values()) == 12
    assert set(study_json["by"]) == {"country", "source", "length", "resolution"}
    assert study_json["by"]["country"]["SK"]["all"]["known"] == 15
    assert study_json["by"]["resolution"]["1 m"]["midline"]["known"] == 2
    assert [s["cluster"] for s in study_json["failed"]] == ["testland-002"]
    assert "# Truth check" in text and "## By country" in text and "highline / midline" in text
    assert "precision proxy" in text and "clearance_near_anchor" in text
    pictures = os.path.join(out, "pictures")
    assert os.path.exists(os.path.join(pictures, "testland-001-map.png"))
    chips = [p for p in study_json["pictures"] if "-miss-" in p]
    assert len(chips) >= 8 and all(os.path.exists(os.path.join(out, p)) for p in chips)
    assert "pictures/testland-001-map.png" in text
    ta.report(out, pictures=False)  # without pictures: the same tables
    assert json.load(open(os.path.join(out, "study.json"), encoding="utf-8"))["pictures"] == []


def test_main(study):
    out, _ = study
    assert ta.main(["analyse", out, "--cluster", "testland-001"]) == 0
    assert ta.main(["report", out, "--no-pictures"]) == 0
    assert os.path.exists(os.path.join(out, "study.md"))


def test_verdicts():
    """--profiles' comparison: production's profile and the grid's exact pair, rounded alike."""
    assert ta.profile_verdict({"min": [10.0, 0.5], "min_nmpt": [10.0, -0.2]}, "mark")
    assert not ta.profile_verdict({"min": [10.0, 0.5], "min_nmpt": [10.0, -0.2]}, "reject")
    assert not ta.profile_verdict({"min": [10.0, 0.0], "min_nmpt": None}, None)
    assert ta.grid_verdict({"clearance": 0.004, "clearance_nmpt": None}, None) is False  # 0.00 rounded
    assert ta.grid_verdict({"clearance": 0.3, "clearance_nmpt": -1.0}, "reject") is False
    assert ta.grid_verdict({"clearance": 0.3, "clearance_nmpt": None}, "reject") is True
    assert ta.grid_verdict(None, None) is None


def test_sag_table_of():
    assert ta.sag_table_of({"params": {"model": "formula"}}) is None
    table = ta.sag_table_of({"model": "sag", "rigging": {"pretension": 2.5, "stretch": 5.0, "webbing_weight": 70,
                                                         "athlete_mass": 80, "fall_zone": 3.0},
                             "params": {"model": "sag", "min_length": 30.0, "max_length": 60.0}})
    assert table.rig.fall_zone == 3.0 and table.spans[0] == 30.0
