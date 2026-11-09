"""tools/truth_analysis.py: the tolerance, the matching (either way round, a radius per line, the length
check, the nearest and the best by clearance), every reason of a miss on a synthetic capture whose found lines
are production's (linesearch.find_valid_lines on the same grid and anchors), a structure at an end, the zones
and lifts of a clearance miss, analyse and report (offline). No SlackMap data: the known lines are made up."""

import dataclasses
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
ROWS, COLS = 330, 130
GRID = {"crs": CRS, "left": LEFT, "top": TOP, "res": RES, "shape": [ROWS, COLS]}
PARAMS = {"resolution": RES, "min_length": 20.0, "max_length": 120.0, "max_anchor_diff": 20.0,
          "max_anchor_diff_m": 50.0, "slope_threshold": 45.0, "min_elevation": None, "max_elevation": None,
          "high_above": 20.0, "min_height": None, "min_mean_height": None, "min_high_share": None,
          "max_wall_angle": 10.0, "min_prominence": None, "min_prominence_both": None, "min_drop": None,
          "nmpt": "reject", "model": "formula"}
RIGGING = {"pretension": 2.5, "stretch": 5.0, "webbing_weight": 70.0, "athlete_mass": 80.0, "fall_zone": 3.0}
SAG_PARAMS = {**PARAMS, "model": "sag", "rigging": RIGGING}  # the sag estimator, findaline.py's default rigging
# The regions of the synthetic canyon (rows): a known line across the middle of each
R_MATCHED, R_NEAR, R_MID, R_FILTERED, R_SEAM, R_WATER, R_SURFACE, R_HEIGHT = (range(30 * k, 30 * k + 30)
                                                                              for k in range(8))
R_WALL = range(240, 300)
R_RAMP = range(300, 330)  # the left wall a slope of 4.5 m a metre (77 deg) from the rim down to the floor
TOWER = (22, 13)          # a pixel of the left plateau where the surface stands 4 m above the terrain


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
    z[R_RAMP.start:R_RAMP.stop, 31:42] = 100.0 - 4.5 * np.arange(1, 12)  # 95.5 ... 50.5, then the floor
    z = z.astype(np.float32)
    surface = z.copy()
    surface[R_SURFACE.start:R_SURFACE.stop, 58:63] = 95.0  # trees 45 m tall on the floor
    surface[TOWER] = z[TOWER] + 4.0                  # a structure on the plateau (a tower, a building)
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


def found_lines(z, surface, anchors, sag_table=None):
    """Production's lines of the grid (find_valid_lines with PARAMS and the sag table), as lines.npz holds them."""
    import helpers as sh
    import linesearch as ls
    table = ls.find_valid_lines(z, surface, anchors, RES, PARAMS["min_length"], PARAMS["max_length"],
                                nmpt_mode="reject", threads=2, sag_table=sag_table,
                                max_dh_ratio=PARAMS["max_anchor_diff"] / 100,
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
        (known("tower", (22, 12), (22, 90)), "structure_anchor", "a"),             # the 4 m bump within 1 px
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
        (known("ramp", (315, 30), (315, 90)), "clearance_near_anchor", None),     # 1.65 m short at the first step
        (known("coarse", (-300, -300), (-300, -200), decimals=3, flags=("coarse_anchor",)), "unverifiable", None),
    ]


FAILED_MESSAGE = "Download failed: HTTP 503: <html><body>\nNo server | is `free`</body></html>\n"


def write_capture(folder, cases, status="done", model="formula", state=None):
    """A cluster folder of the contract's capture format (truth_study.py run's); model "sag": the sag
    estimator with RIGGING (grid.json as truth_study.write_grid writes it, the lines found with its table);
    state: more keys of capture.json (a failed search's error and message)."""
    z, surface, filled, water, mask = terrain()
    anchors = anchors_of(z, filled, mask)
    cap = os.path.join(folder, "capture")
    os.makedirs(cap, exist_ok=True)
    params = SAG_PARAMS if model == "sag" else PARAMS
    grid = {**GRID, "params": params, "nmpt": "reject", "obstacles": None, "model": model,
            "rigging": RIGGING if model == "sag" else None, "slope_threshold": PARAMS["slope_threshold"],
            "fall": RIGGING["fall_zone"] if model == "sag" else 6.0, "layer_meta": {"source": "testland"},
            "source": "testland", "area_wgs84": [0, 0, 0, 0]}
    sag_table = ta.sag_table_of(grid)
    with open(os.path.join(cap, "grid.json"), "w") as f:
        json.dump(grid, f)
    np.savez_compressed(os.path.join(cap, "grids.npz"), elevation=z, surface=surface,
                        filled=filled.astype(np.uint8), joined=np.zeros(z.shape, np.uint8),
                        water=water.astype(np.uint8), mask=mask.astype(np.uint8))
    np.save(os.path.join(cap, "anchors.npy"), anchors)
    np.savez_compressed(os.path.join(cap, "lines.npz"), **found_lines(z, surface, anchors, sag_table))
    import dataclasses
    with open(os.path.join(folder, "known.json"), "w", encoding="utf-8") as f:
        json.dump([dataclasses.asdict(line) for line, *_ in cases], f)
    with open(os.path.join(folder, "capture.json"), "w") as f:
        json.dump({"status": status, "seconds": 1.0, "options": "--lat 0 --lon 0", **(state or {})}, f)
    return folder


@pytest.fixture(scope="module")
def study(tmp_path_factory):
    out = tmp_path_factory.mktemp("truth")
    cases = known_lines()
    write_capture(str(out / "testland-001"), cases)
    write_capture(str(out / "testland-002"), cases[:1], status="failed",  # listed, not counted
                  state={"error": "download_failed", "message": FAILED_MESSAGE})
    return str(out), cases


@pytest.fixture(scope="module")
def sag_study(tmp_path_factory):
    """The canyon searched with the sag model (testland-sag), and a place of the formula model beside it."""
    out = tmp_path_factory.mktemp("truth-sag")
    cases = known_lines()
    write_capture(str(out / "testland-sag"), cases, model="sag")
    write_capture(str(out / "testland-zformula"), cases[:2])
    return str(out), cases


def spy_pairs(monkeypatch):
    """The pairs _funnel hands to _zone_lift (lo, hi), kept in the returned dict by the record's id."""
    seen, real = {}, ta._zone_lift

    def spy(c, lo, hi, results):
        seen["pairs"] = (np.array(lo), np.array(hi))
        return real(c, lo, hi, results)

    monkeypatch.setattr(ta, "_zone_lift", spy)
    return seen


def brute_zone_lift(c, lo, hi):
    """valid[zone][lift] of the pairs by helpers.evaluate_line at that end zone and lift itself (is_valid: the
    search's decision, the surface under "reject"), the pairs over the wall-angle limit left out."""
    import helpers as sh
    down = sh.downslope(c.elevation, np.vstack([lo, hi]), c.res)
    a1, a2 = sh.wall_angles(lo, hi, down[:len(lo)], down[len(lo):])
    keep = np.flatnonzero(np.maximum(a1, a2) <= c.params["max_wall_angle"])
    return [[any(sh.is_valid(sh.evaluate_line(lo[i], hi[i], c.elevation, c.res, c.surface, c.sag_table,
                                              end_zone=z, lift=h), c.nmpt) for i in keep)
             for h in ta.LIFTS] for z in ta.ZONES]


def test_tolerance():
    line = known("t", (0, 0), (0, 50))
    assert ta.tolerance(line) == 10.0                                          # the floor
    assert ta.tolerance(known("t", (0, 0), (0, 50), stated=200.0)) == pytest.approx(20.0)  # 10 % of L
    coarse = known("t", (0, 0), (0, 50), decimals=3, flags=("coarse_anchor",))
    assert ta.tolerance(coarse) == pytest.approx(111.0)                        # the quantum of 0.001 deg
    assert ta.tolerance(known("t", (0, 0), (0, 50), decimals=2, flags=("coarse_anchor",))) == pytest.approx(1110.0)
    assert ta.tolerance(known("t", (0, 0), (0, 50), decimals=4)) == 10.0      # not coarse: no quantum
    assert ta.length_bin(29.9) == "0-30" and ta.length_bin(30) == "30-50" and ta.length_bin(500) == "500+"


def _found(pairs, clearance=None, rep=None):
    """FoundLines of (row, col) pixel pairs of GRID (their lengths those of the pixels, as the search's)."""
    a1 = np.array([latlon(*p) for p, _ in pairs]).reshape(-1, 2)
    a2 = np.array([latlon(*q) for _, q in pairs]).reshape(-1, 2)
    n = len(pairs)
    length = np.array([np.hypot(q[0] - p[0], q[1] - p[1]) * RES for p, q in pairs], dtype=np.float64)
    return ta.FoundLines(a1=a1, a2=a2, length=length,
                         clearance=np.ones(n) if clearance is None else np.asarray(clearance, dtype=np.float64),
                         clearance_nmpt=np.full(n, np.nan), over=np.zeros(n, bool),
                         rep=np.ones(n, bool) if rep is None else np.asarray(rep, dtype=bool), group=np.arange(n),
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


def test_length_check():
    """A found line is a candidate only with its length within the tolerance too. A known line of 32 m (tol
    10 m) and found lines with both ends within 10 m of its anchors: one of 20 m (each end 6 m inwards: |20 -
    32| = 12 m) is rejected, one of 25 m (ends 3 and 4 m inwards: |25 - 32| = 7 m, within the 10 m) matches;
    the anchors' distance counts as well as the stated length (a line stated 50 m on anchors 32 m apart)."""
    line = known("len", (100, 40), (100, 72))
    assert ta.tolerance(line) == 10.0 and line.length_m == pytest.approx(32.0, abs=0.05)
    short = _found([((100, 46), (100, 66))])
    assert short.lengths.tolist() == [20.0]
    ka, kb = ta._xy(GRID, [line.a]), ta._xy(GRID, [line.b])
    assert coverage_contrast.matched(ka, kb, short.xy1, short.xy2, 10.0).tolist() == [True]  # the ends alone fit
    assert ta.match([line], short, GRID) == [None]
    both = _found([((100, 46), (100, 66)), ((100, 43), (100, 68))])
    assert ta.match([line], both, GRID) == [1] and [c.tolist() for c in ta.candidates([line], both, GRID)] == [[1]]
    stated = known("stated", (100, 40), (100, 72), stated=50.0)
    assert ta.tolerance(stated) == 10.0 and ta.known_lengths(stated) == (50.0, pytest.approx(32.0, abs=0.05))
    exact = _found([((100, 40), (100, 72)), ((100, 46), (100, 66))])
    assert ta.match([stated], exact, GRID) == [0]  # |32 - 50| > 10, but on the anchors themselves
    nan = dataclasses.replace(short, length=np.array([np.nan]))  # no length column: the anchors' distance
    assert nan.lengths.tolist() == pytest.approx([20.0], abs=0.01) and ta.match([line], nan, GRID) == [None]


def test_best_match(study):
    """match is the nearest candidate, best_match the one of the highest clearance (the nearest of a tie);
    whether the nearest is a representative and whether any candidate is; the report's quantiles and over-trees
    share take the best match, the wall angles the nearest."""
    out, _ = study
    c = ta.load_capture(os.path.join(out, "testland-001"))
    line = next(k for k in c.known if k.id == "m1")
    found = _found([((15, 30), (15, 90)),       # 0: on the anchors
                    ((17, 30), (15, 90)),       # 1: 2 m off at a, clearance 5
                    ((14, 31), (16, 89)),       # 2: 1.4 m off at both, clearance 5 too
                    ((15, 30), (15, 60))],      # 3: 30 m off at b: no candidate
                   clearance=[1.0, 5.0, 5.0, 9.0], rep=[False, True, False, True])
    assert [x.tolist() for x in ta.candidates([line], found, c.grid)] == [[0, 1, 2]]
    assert ta.best_candidate([0, 1, 2], found) == 1 and ta.best_candidate([], found) is None
    r = ta.diagnose(dataclasses.replace(c, found=found, _cache={}), line, 0)
    m, b = r["match"], r["best_match"]
    assert m["index"] == 0 and m["clearance"] == 1.0 and m["candidates"] == 3 and m["within_base"]
    assert m["rep"] is False and m["rep_any"] is True
    assert b["index"] == 1 and b["clearance"] == 5.0 and b["rep"] is True and b["nearest"] is False
    assert b["d"] == [pytest.approx(2.0, abs=0.01), pytest.approx(0.0, abs=0.01)]
    s = ta.stats([ta._plain(r)])
    assert s["clearance"] == [5.0, 5.0, 5.0] and s["wall_angle"] == [pytest.approx(m["wall"], abs=0.01)] * 3
    assert s["matched_rep"] == 0 and s["matched_rep_any"] == 1


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
    assert ta.REASONS.index("water_pixel") + 1 == ta.REASONS.index("structure_anchor")
    assert ta.REASONS.index("structure_anchor") + 1 == ta.REASONS.index("no_steep_pixel")
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
    tower = got["tower"]  # the end on the plateau: no anchor, no steep pixel, the surface 4 m up 1 px away
    assert tower["ends"][0]["structure_m"] == pytest.approx(4.0) and tower["ends"][0]["structure"]
    assert tower["ends"][0]["steep"] is False and tower["ends"][0]["anchors"] == 0 and tower["ends"][1]["anchors"] > 0
    assert tower["structure"] == [pytest.approx(4.0), 0.0] and tower["on_terrain"] is False
    assert all(r["on_terrain"] for name, r in got.items() if name != "tower")
    assert got["flat"]["ends"][0]["structure_m"] == 0.0 and got["coarse"]["structure"] == [None, None]
    assert got["m1"]["best_match"]["clearance"] >= got["m1"]["match"]["clearance"]
    assert got["ramp"]["zone_lift"] is not None and got["mid"]["zone_lift"] is not None
    assert all(got[k]["zone_lift"] is None for k in ("trees", "dh", "wall", "flat", "m1"))


def test_structure(study):
    """The largest height of the surface above the terrain within STRUCTURE_PX (1) pixel of an end's pixel."""
    out, _ = study
    c = ta.load_capture(os.path.join(out, "testland-001"))
    row, col = TOWER
    assert ta._structure(c, (row, col - 1)) == pytest.approx(4.0)   # 1 px away
    assert ta._structure(c, (row + 1, col + 1)) == pytest.approx(4.0)  # diagonally
    assert ta._structure(c, (row, col - 2)) == 0.0                 # 2 px away: the terrain
    assert ta._structure(c, (-1, 5)) is None and ta._structure(c, (row, COLS)) is None  # outside the grid
    assert ta._structure(dataclasses.replace(c, surface=None, _cache={}), TOWER) is None
    assert ta._structure(c, (105, 13)) == 0.0 and ta._structure(c, (105, 11)) is None  # NaN pixels left out
    line = next(k for k in c.known if k.id == "tower")
    low = dataclasses.replace(c, surface=np.where(c.surface > c.elevation + 3.5, c.elevation + 2.9, c.surface),
                              _cache={})
    r = ta.diagnose(low, line, None)  # 2.9 m: no structure
    assert r["reason"] == "no_steep_pixel" and r["which"] == "a" and r["on_terrain"]


def test_zone_lift(study, monkeypatch):
    """A clearance miss's pairs at each zone and lift. The ramp (a slope of 4.5 m a metre below its rim, so 1.65 m
    too high at the first step: 100 - 6 - 0.15 - 95.5) needs 1.65 m of A-frames without a zone and none with a
    zone of 5 m (its first step then needs only the webbing above it); the ledge of "near" (97 m for 15 m below
    a 100 m rim) needs more than 3 m up to a zone of 10 m, and none at 20 m: the zone is at most a quarter of a
    line, 15 steps of the straight 60 m pair, but 16 of a slightly diagonal one (helpers.zone_steps rounds
    15.000...2 up), which then covers the ledge's 15th step too."""
    import end_zone_study as ezs
    out, _ = study
    c = ta.load_capture(os.path.join(out, "testland-001"))
    by_id = {k.id: k for k in c.known}
    seen = spy_pairs(monkeypatch)
    r = ta.diagnose(c, by_id["ramp"], None)
    assert r["reason"] == "clearance_near_anchor" and r["best"]["rule_failure"]["from_a1"] == pytest.approx(1.0)
    zl = r["zone_lift"]
    assert zl["valid"] == brute_zone_lift(c, *seen["pairs"])  # the bucket minima give the rule's own decision
    assert zl["zones"] == [0.0, 5.0, 10.0, 20.0] and zl["lifts"] == [0.0, 1.0, 2.0, 3.0] and zl["pairs"] > 0
    assert zl["valid"] == [[False, False, True, True]] + [[True] * 4] * 3
    assert zl["lift"][0] == pytest.approx(1.65, abs=1e-5) and zl["lift"][1:] == [0.0, 0.0, 0.0]
    assert r["best"]["staircase"][0]["lift"] == pytest.approx(zl["lift"][0])  # the best pair's own staircase
    near = ta.diagnose(c, by_id["near"], None)
    assert near["zone_lift"]["lift"] == [None, None, None, 0.0]
    assert near["zone_lift"]["valid"] == [[False] * 4] * 3 + [[True] * 4]
    mid = ta.diagnose(c, by_id["mid"], None)
    assert mid["reason"] == "clearance_mid" and mid["zone_lift"]["lift"] == [None] * 4
    s = ta.stats([ta._plain(x) for x in (r, near, mid)])
    rows = s["zone_lift"]["rows"]
    found = [[0, 0, 1, 1], [1] * 4, [1] * 4, [2] * 4]
    assert rows["clearance_near_anchor"] == {"misses": 2, "found": found}
    assert rows["clearance_mid"] == {"misses": 1, "found": [[0] * 4] * 4}
    assert rows["both"] == {"misses": 3, "found": found}
    rng = np.random.default_rng(1)  # _needed is end_zone_study.needed_lift row by row
    buckets = rng.normal(0, 3, (40, 4))
    buckets[3, 2], buckets[5, 0], buckets[7, 1] = np.nan, np.inf, np.inf
    for j in range(4):
        expected = [ezs.needed_lift(row, j, 6.0) for row in buckets]
        assert ta._needed(buckets, j, 6.0).tolist() == expected


def test_analyse_and_report(study):
    out, cases = study
    data = ta.analyse(out)
    assert os.path.exists(os.path.join(out, "testland-001", "analysis.json"))
    assert os.path.exists(os.path.join(out, "analysis.json"))
    places = {s["cluster"]: s for s in data["clusters"]}
    assert places["testland-002"]["analysed"] is False and places["testland-002"]["known"] == 1
    assert (places["testland-002"]["search_error"], places["testland-002"]["search_message"]) == \
        ("download_failed", FAILED_MESSAGE)  # the search's own, from capture.json
    assert "search_error" not in places["testland-001"]
    one = places["testland-001"]
    assert one["known"] == len(cases) and one["matched"] == 3 and one["source"] == "testland"
    assert 0 < one["spots_without_known"] < one["found_spots"]
    assert len(data["records"]) == len(cases)  # the failed cluster's line is not counted
    text = ta.report(out)
    study_json = json.load(open(os.path.join(out, "study.json"), encoding="utf-8"))
    overall = study_json["overall"]
    assert overall["all"]["known"] == 17 and overall["all"]["matched"] == 3 and overall["all"]["verifiable"] == 16
    assert overall["highline"]["known"] == 15 and overall["midline"]["known"] == 2
    assert overall["midline"]["matched"] == 0
    assert overall["all"]["reasons"]["unverifiable"] == 1 and overall["midline"]["reasons"]["clearance_mid"] == 1
    assert overall["all"]["reasons"]["structure_anchor"] == 1 and overall["all"]["misses"] == 14
    assert overall["all"]["recall"] == pytest.approx(3 / 16, abs=1e-4)
    assert overall["all"]["known_clean"] == 15 and overall["all"]["matched_clean"] == 2
    # the terrain recall leaves out the tower (a structure at an end); the coarse line is on terrain, unverifiable
    assert (overall["all"]["known_terrain"], overall["all"]["verifiable_terrain"],
            overall["all"]["matched_terrain"]) == (16, 15, 3)
    assert overall["all"]["recall_terrain"] == pytest.approx(3 / 15, abs=1e-4)
    assert overall["highline"]["known_terrain"] == 14 and overall["midline"]["recall_terrain"] == 0.0
    assert sum(overall["all"]["reasons"].values()) == 14
    matched = [r for r in data["records"] if r["outcome"] == "matched"]
    assert overall["all"]["matched_rep"] == sum(r["match"]["rep"] for r in matched)
    assert overall["all"]["matched_rep_any"] == sum(r["match"]["rep_any"] for r in matched)
    assert overall["all"]["clearance"] == ta._quantiles([r["best_match"]["clearance"] for r in matched])
    doubtful = overall["all"]["doubtful_tolerance"]  # m3: a length mismatch, matched at the floor's 10 m
    assert overall["all"]["matched_doubtful"] == 1 and doubtful["bins"] == {"10-100": 1, "100-1000": 0, "1000+": 0}
    assert doubtful["tolerances"] == [10.0] and doubtful["within_base"] == 1 and doubtful["largest"] == 10.0
    zone_lift = overall["all"]["zone_lift"]["rows"]
    assert zone_lift["both"]["misses"] == 3 and zone_lift["both"]["found"][0] == [0, 0, 1, 1]
    assert overall["midline"]["zone_lift"]["rows"]["clearance_mid"] == {"misses": 1, "found": [[0] * 4] * 4}
    assert set(study_json["by"]) == {"country", "source", "length", "resolution"}
    assert study_json["by"]["country"]["SK"]["all"]["known"] == 17
    assert study_json["by"]["resolution"]["1 m"]["midline"]["known"] == 2
    assert [s["cluster"] for s in study_json["failed"]] == ["testland-002"]
    place = study_json["places"][0]
    assert place["known_by_type"] == {"highline": 15, "midline": 2} and place["matched_by_type"]["highline"] == 3
    entries = study_json["misses"]["testland-001"]
    assert len(entries) == 14 and [e["n"] for e in entries] == [n for n, (_, outcome, _) in enumerate(cases, 1)
                                                                if outcome != "matched"]
    assert "\n".join(ta.markdown(study_json)) == text  # study.md is study.json's alone
    assert "# Truth check" in text and "## By country" in text and "highline / midline" in text
    assert "precision proxy" in text and "clearance_near_anchor" in text and "structure_anchor" in text
    assert "- **Recall** (matched of verifiable known lines): highline 21% (3 of 14), midline 0% (0 of 2); " \
           "all 19% (3 of 16)." in text
    assert "Midlines hang below the fall allowance by construction" in text
    assert "## Clearance misses with a no-fall zone or A-frames" in text and "| 0 m | 0 (0 / 0) |" in text
    assert "best match" in text and "coarse anchors (at most 3 decimals)" in text
    assert "surface 4.0 m above the terrain" in text
    assert study_json["model"] == {"model": "formula", "fall": 6.0, "rigging": None, "same": True,
                                   "variants": [{"model": "formula", "rigging": None, "fall": 6.0, "places": 1}]}
    assert "\n\nSearches with the formula model (a fall allowance of 6.0 m).\n\n" in text
    assert "smallest lift of any pair: zone 0 m: 1." in text and "zone 5 m: 0.0 m" in text
    pictures = os.path.join(out, "pictures")
    assert os.path.exists(os.path.join(pictures, "testland-001-map.png"))
    chips = [p for p in study_json["pictures"] if "-miss-" in p]
    assert len(chips) >= 8 and all(os.path.exists(os.path.join(out, p)) for p in chips)
    assert "pictures/testland-001-map.png" in text
    ta.report(out, pictures=False)  # without pictures: the same tables
    assert json.load(open(os.path.join(out, "study.json"), encoding="utf-8"))["pictures"] == []
    # the failed search listed with its error and message (one line, a code span: the HTML and "|" kept as text)
    failure = ("- testland-002 (1 known line): search failed: download_failed; `Download failed: HTTP 503: "
               "<html><body> No server | is 'free'</body></html>`")
    assert "\n## Failed searches\n" in text and failure in text.splitlines()
    assert "1 place not analysed, 1 known line left out; by cause: search failed: download_failed 1." in text
    assert "| testland-002 | search failed: download_failed | | | | | 1 | |" in text
    path = os.path.join(out, "analysis.json")  # an analysis.json of before: report reads capture.json
    kept = open(path, encoding="utf-8").read()
    old = json.loads(kept)
    for s in old["clusters"]:
        s.pop("search_error", None), s.pop("search_message", None)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(old, f)
    try:
        assert failure in ta.report(out, pictures=False).splitlines()
    finally:
        with open(path, "w", encoding="utf-8") as f:
            f.write(kept)


def test_sag_model(sag_study, monkeypatch):
    """The analysis under the sag model: the run's envelope table (sag_table_of), the fall zone as the fall
    allowance, the found lines' clearances given back exactly, the reasons, the zones and lifts (the rule's own
    decision at each zone and lift), and the report's head naming the model and its rigging."""
    out, cases = sag_study
    c = ta.load_capture(os.path.join(out, "testland-sag"))
    assert c.sag_table is not None and c.fall == RIGGING["fall_zone"] == c.sag_table.rig.fall_zone
    assert c.namespace.sag_table is c.sag_table and c.sag_table.spans[0] == SAG_PARAMS["min_length"]
    import studylib
    f = c.found
    for k in range(0, len(f), max(1, len(f) // 40)):  # production's clearance, evaluated again on the capture
        lo, hi = sorted([studylib.to_pixel(c.grid, *f.a1[k]), studylib.to_pixel(c.grid, *f.a2[k])])
        assert ta._evaluate(c, lo, hi)[3] == f.clearance[k]
    seen = spy_pairs(monkeypatch)
    got = {}
    for line, k in zip(c.known, ta.match(c.known, c.found, c.grid)):
        got[line.id] = ta.diagnose(c, line, k)
        if line.id == "near":
            pairs = seen["pairs"]
    for line, expected, which in cases:  # the formula's reasons, but the ramp: found with a fall zone of 3 m
        expected = "matched" if line.id == "ramp" else expected
        r = got[line.id]
        assert (r["outcome"] if expected == "matched" else r["reason"]) == expected, (line.id, r["reason"])
    near = got["near"]  # 3 m below the rim: the sagged webbing's sag (2.6 m at 15 m) without the fall zone
    assert near["best"]["clearance_rule"] == pytest.approx(-2.596, abs=0.01)
    assert near["zone_lift"]["lift"][:3] == [pytest.approx(-near["best"]["clearance_rule"])] * 3
    assert near["zone_lift"]["valid"] == brute_zone_lift(c, *pairs)
    assert near["zone_lift"]["valid"][0] == [False, False, False, True]
    assert near["best"]["staircase"][0]["lift"] == pytest.approx(near["zone_lift"]["lift"][0])
    assert got["nodata"]["exact"] is None  # an end without data: no line (the sag table takes no NaN)
    ta.analyse(out)
    text = ta.report(out)
    study_json = json.load(open(os.path.join(out, "study.json"), encoding="utf-8"))
    model = study_json["model"]
    assert model["model"] == "sag" and model["rigging"] == RIGGING and model["fall"] == 3.0 and not model["same"]
    assert sorted((v["model"], v["places"]) for v in model["variants"]) == [("formula", 1), ("sag", 1)]
    assert text.startswith("# Truth check: the search against known lines\n\nSearches with the sag model (the sag "
                           "estimator): pretension 2.5 kN, stretch 5.0 % at 10 kN, webbing 70 g/m, athlete 80 kg, a "
                           "fall zone of 3.0 m below the sagged webbing (the fall allowance). The places' searches "
                           "differ: ")
    assert "the formula model (a fall allowance of 6.0 m) in 1 place" in text
    chips = [p for p in study_json["pictures"] if "-miss-" in p]
    assert chips and all(os.path.exists(os.path.join(out, p)) for p in chips)


def test_length_range(study):
    """A known line whose anchor pairs all lie outside the search's min_length..max_length (20-120 m): a line
    of 210 m down the left rim (tol 21 m, so no pair shorter than 168 m) with anchors at both ends."""
    assert ta.REASONS.index("length_range") == ta.REASONS.index("anchor_filtered") + 1
    assert ta.REASONS.index("length_range") + 1 == ta.REASONS.index("height_difference")
    out, _ = study
    c = ta.load_capture(os.path.join(out, "testland-001"))
    line = known("long", (5, 30), (215, 30))
    assert ta.match([line], c.found, c.grid) == [None]
    r = ta.diagnose(c, line, None)
    assert r["reason"] == "length_range" and r["note"] is None and r["which"] is None
    assert r["ends"][0]["anchors"] > 0 and r["ends"][1]["anchors"] > 0
    assert r["funnel"]["pairs"] > 0 and r["funnel"]["length"] == 0 and "height" not in r["funnel"]
    assert r["best"]["stage"] == "length" and r["best"]["length"] > PARAMS["max_length"]
    assert "length_range" in ta._miss_line(ta._miss_entry(1, ta._plain(r)), ta.rules())
    apart = known("apart", (15, 22), (15, 98))  # 76 m: its anchors' pairs, 58-62 m, none within its 10 m
    r = ta.diagnose(c, apart, None)
    assert r["reason"] == "length_range" and r["note"] == "known_length"
    assert r["ends"][0]["anchors"] > 0 and r["ends"][1]["anchors"] > 0
    assert r["funnel"]["pairs"] > 0 and r["funnel"]["known_length"] == 0 and r["funnel"]["length"] == 0


def test_profile_folders(tmp_path):
    """--profiles' data folders: the run's (<out>/data), its cache linked to the given cache once and unlinked
    on leaving; a real cache or an existing link used as it is and left."""
    import regression
    from types import SimpleNamespace
    cache_dir = tmp_path / "cache"
    (cache_dir / "layer").mkdir(parents=True)
    out = tmp_path / "out"
    (out / "data" / "runs" / "r1").mkdir(parents=True)
    with_run = SimpleNamespace(run=str(out / "data" / "runs" / "r1"), folder=str(out / "c1"))
    without = SimpleNamespace(run=None, folder=str(out / "c2"))
    link = out / "data" / "cache"
    with ta.ProfileFolders(str(cache_dir)) as folders:
        data = folders.data_of(with_run)
        assert data == str(out / "data") and folders.data_of(without) == data
        assert os.path.isdir(link / "layer") and len(folders.ready) == 1
    assert not os.path.lexists(link) and (cache_dir / "layer").is_dir()
    regression.link(str(cache_dir), str(link))  # a run's link: used, never removed here
    with ta.ProfileFolders(str(tmp_path / "other")) as folders:
        assert folders.data_of(without) == str(out / "data")
    assert os.path.isdir(link / "layer")
    ta.studylib._unlink(str(link))
    own = tmp_path / "own"
    (own / "data" / "cache").mkdir(parents=True)  # a run with --no-cache-link: its own cache
    with ta.ProfileFolders(str(cache_dir)) as folders:
        assert folders.data_of(SimpleNamespace(run=str(own / "data" / "runs" / "r"), folder="x")) == str(own / "data")
    assert (own / "data" / "cache").is_dir() and not ta._is_link(str(own / "data" / "cache"))
    assert ta.run_folder(str(out / "c1"), {"run": "data/runs/r1"}) == str(out / "data" / "runs" / "r1")
    assert ta.run_folder(str(out / "c1"), {"run": None}) is None


def test_view_box():
    """A place's picture: the search area's box and the known lines' ends, padded, within the grid."""
    mask = np.zeros((ROWS, COLS), dtype=bool)
    mask[100:161, 40:101] = True                                   # a square area of 61 x 61 px
    assert ta.view_box(mask, GRID, []) == (80, 181, 20, 121)        # padded by 20 px
    line = known("k", (90.5, 30.5), (150, 128.6))                   # ends above, left of and beyond the area
    r0, r1, c0, c1 = ta.view_box(mask, GRID, [line])
    assert (r0, c0) == (70, 10) and r1 == 181 and c1 == COLS        # floor(90.5 - 20), ...; the grid's edge
    assert ta.view_box(np.zeros_like(mask), GRID, [line]) == (0, ROWS, 0, COLS)
    big = np.zeros((2000, 2000), dtype=bool)
    big[500:1501, 500:1501] = True
    assert ta.view_box(big, GRID, []) == (450, 1551, 450, 1551)     # 5 % of 1000 px


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
