"""Phase 4's findings of the line-volume task (docs/line-volume/spec.md section 7), fixed: an unfinished tiled
sag job resumes after migration 17 of jobs.sqlite (search._search_keys), the funnel counts of a search the square
rule's early check stops, and the truth analysis' reason for a known line the square rule dropped."""

import json
import os
import sys
from types import SimpleNamespace

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import jobs as jb  # noqa: E402
import params as pm  # noqa: E402
import search  # noqa: E402

AREA = {"area": "coast", "within": "osm:Gozo"}  # no file path: the hashes hold in every checkout
CLI = ["--area", "coast", "--within", "osm:Gozo"]

# The hashes of main c8a079a (before the fix), web requests as the worker reads them (jobs.search_params of the
# stored JSON), command-line ones from params.parse_cli; source geoportal, resolution 2 m. The fix moves none.
WEB = {"sag, fall_zone 3": ({"model": "sag", "fall_zone": 3}, "829cd2e55c16a9e7", "ea8791ac80a2a352"),
       "sag, fall_zone 4.5": ({"model": "sag", "fall_zone": 4.5}, "55135368e473d7c0", "967a6a8e3d9b8d40"),
       "sag, default (6 m)": ({"model": "sag"}, "8cd584ec6285fb9c", "0f7399a5897bbb87"),
       "formula": ({}, "c2815824f4b9a796", "08f4bceb300b72ac"),
       "formula, fall_zone 3": ({"fall_zone": 3}, "6630d85d9cde2074", "ef1b56f1a7a21d06")}
COMMAND_LINE = {"sag --fall-zone 3": (["--model", "sag", "--fall-zone", "3"], "173c1c5395ba26b5", "a6dfefeb63327a5f"),
                "sag": (["--model", "sag"], "ed4f6442b52e1d6b", "355dd0484e2e5500"),
                "formula": ([], "31c28f8c91eecd44", "7e6ddbb80feb7f39")}
# A web sag request without a fall zone, hashed before migration 17 (8c6fccc~1, the default's int 3)
BEFORE = {None: "48404ab58fd24175", 7: "58018a4c32966889"}


def _plan(params, owner=None, runs=None):
    return SimpleNamespace(params=params, source=SimpleNamespace(id="geoportal"), resolution=2.0, owner=owner,
                           paths=SimpleNamespace(runs=runs), tile_core=400, tiles=[None] * 4,
                           emit=lambda kind, text: None)


def _web(values):
    return jb.search_params(json.loads(json.dumps({"params": {**AREA, **values}})))


def _migrated():
    """A stored web sag request of before 2026-11-14 without a fall zone, as migration 17 leaves it."""
    params = {**AREA, "model": "sag"}
    request = json.loads(json.dumps({"params": params}))
    if request["params"].get("model") == "sag" and "fall_zone" not in request["params"]:
        request["params"]["fall_zone"] = jb.FALL_ZONE_BEFORE
    return jb.search_params(json.loads(json.dumps(request)))


@pytest.mark.parametrize("owner", [None, 7])
def test_hashes_stay(owner):
    """_search_hash of every request is today's; the key of before is only a second key of a sag search at 3 m."""
    column = 1 if owner is None else 2
    for name, row in WEB.items():
        assert search._search_hash(_plan(_web(row[0]), owner)) == row[column], name
    for name, row in COMMAND_LINE.items():
        [params], _ = pm.parse_cli(CLI + row[0])
        assert search._search_hash(_plan(params, owner)) == row[column], name
    migrated = _plan(_migrated(), owner)
    assert search._search_hash(migrated) == WEB["sag, fall_zone 3"][column]  # as today
    assert search._search_keys(migrated) == [WEB["sag, fall_zone 3"][column], BEFORE[owner]]
    [cli3], _ = pm.parse_cli(CLI + ["--model", "sag", "--fall-zone", "3"])
    assert search._search_keys(_plan(cli3, owner))[0] == COMMAND_LINE["sag --fall-zone 3"][column]
    for values in ({"model": "sag", "fall_zone": 4.5}, {"model": "sag"}, {}, {"fall_zone": 3}):
        assert search._search_keys(_plan(_web(values), owner)) == [search._search_hash(_plan(_web(values), owner))]


def _unfinished(runs, key, name="unfinished"):
    folder = os.path.join(runs, name)
    os.makedirs(os.path.join(folder, "tiles"))
    with open(os.path.join(folder, "progress.json"), "w", encoding="utf-8") as f:
        json.dump({"status": "running", "search": key, "tile_core": 400, "name": "Gozo",
                   "created": "2026-11-13T10:00:00"}, f)
    return folder


def _state(folder):
    with open(os.path.join(folder, "progress.json"), encoding="utf-8") as f:
        return json.load(f)


@pytest.mark.parametrize("owner", [None, 7])
def test_migrated_job_resumes_the_run_of_before(tmp_path, owner):
    """A run written under the hash of before resumes for the migrated request, and its progress.json then holds
    today's key (so a later resume finds it under that one)."""
    runs = str(tmp_path)
    folder = _unfinished(runs, BEFORE[owner])
    plan = _plan(_migrated(), owner, runs)
    run = search._open_run(plan)
    assert run["path"] == folder and run["search"] == search._search_hash(plan)
    assert _state(folder)["search"] == search._search_hash(plan)
    assert {k: v for k, v in _state(folder).items() if k != "search"} == {
        "status": "running", "tile_core": 400, "name": "Gozo", "created": "2026-11-13T10:00:00"}
    assert search._open_run(_plan(_migrated(), owner, runs))["path"] == folder  # again, under today's key
    assert os.listdir(runs) == ["unfinished"]


def test_run_under_todays_key_is_not_rewritten(tmp_path):
    runs = str(tmp_path)
    plan = _plan(_migrated(), None, runs)
    folder = _unfinished(runs, search._search_hash(plan))
    before = os.path.getmtime(os.path.join(folder, "progress.json"))
    os.utime(os.path.join(folder, "progress.json"), (before - 100, before - 100))
    assert search._open_run(plan)["path"] == folder
    assert os.path.getmtime(os.path.join(folder, "progress.json")) == before - 100


@pytest.mark.parametrize("params, owner", [
    (lambda: _web({"model": "sag", "fall_zone": 4.5, "name": "other"}), None),  # another fall zone
    (lambda: _web({"model": "sag", "name": "other"}), None),  # today's default, 6 m
    (lambda: _web({"fall_zone": 3, "name": "other"}), None),  # the formula at 3 m
    (lambda: _web({"model": "sag", "fall_zone": 3, "name": "other"}), 8),  # another owner
])
def test_no_other_search_resumes_the_run_of_before(tmp_path, params, owner):
    """The run of before (owner 7 or none, sag at the default 3 m) is not resumed by another search or owner."""
    runs = str(tmp_path)
    _unfinished(runs, BEFORE[None], "local")
    _unfinished(runs, BEFORE[7], "owner7")
    run = search._open_run(_plan(params(), owner, runs))
    assert os.path.basename(run["path"]) not in ("local", "owner7")
    assert _state(os.path.join(runs, "local"))["search"] == BEFORE[None]
    assert _state(os.path.join(runs, "owner7"))["search"] == BEFORE[7]


# --- the funnel counts of a search the square rule's early check stops ---

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
POINT = {"northing": 254608, "easting": 553966, "radius": 150}
# Plan.funnel of the clip's search stopped by the early check, parts of 32 anchors and 50 pairs (its "estimate"
# follows the seed of the search's hash, which holds the clip's path: left out). Without the square rule at a line
# limit of 300 as on main c8a079a (before the fix); with it at 40 kept lines, where main c8a079a had only the first
# three counts (find_valid_lines' sink stopped before adding its own)
STOPPED_WITHOUT_RULE = {"grids": 1, "anchors": 6990, "anchors_kept": 6990, "open": 442, "todo": 442, "candidates": 4518,
                        "checked": 2981, "found": 639, "valid": 350, "left_out": 0}
STOPPED_WITH_RULE = {"grids": 1, "anchors": 6990, "anchors_kept": 6990, "open": 442, "todo": 442, "candidates": 2436,
                     "checked": 1511, "found": 284, "valid": 284, "left_out": 0}


def _stopped(tmp_path, name, limits=None, **values):
    """A search of the clip in this process: (its Plan.funnel without "estimate", the SearchError or None)."""
    import gc
    from params import SearchParams
    params = SearchParams(elevation_file=os.path.join(DATA, "zabi_kon_nmt.tif"), max_length=150, water="off",
                          fill_gaps="off", ortho="never", **POINT, **values)
    paths = search.Paths(str(tmp_path / name), str(tmp_path / name / "work"))
    os.makedirs(paths.work, exist_ok=True)
    plan = search.plan_search(params, paths, lambda kind, text: None, limits=limits)
    error = None
    try:
        lines, _ = search.search_lines(plan)
        del lines
    except search.SearchError as e:
        error = e
    gc.collect()  # the memory-mapped grids closed before the next search writes its own (Windows)
    return {k: v for k, v in plan.funnel.items() if k != "estimate"}, error


@pytest.fixture
def small_parts(monkeypatch):
    """The clip's search in many small parts, checked after each, and the estimate before the pairs refusing
    nothing (the search's own checks decide)."""
    import linesearch
    import samelines
    monkeypatch.setattr(linesearch, "SINK_CHUNK", 32)
    monkeypatch.setattr(linesearch, "EVAL_PART", 50)
    monkeypatch.setattr(samelines, "CHECK_ROWS", 1)
    monkeypatch.setattr(search, "REFUSE_FACTOR", float("inf"))


def test_funnel_of_a_search_the_square_rules_check_stops(tmp_path, small_parts):
    """The square rule's reducer stops the search midway (the line limit, early): Plan.funnel has the line search's
    counts up to the stop (all but "lines", which only a finished search counts), the same with one thread; the
    refusal is today's."""
    from settings import Limits
    import jobs as jb
    full, error = _stopped(tmp_path, "full", same_line_square=5)
    assert error is None and full["lines"] == 122
    funnel, error = _stopped(tmp_path, "stopped", Limits(lines_max=40), same_line_square=5)
    assert error.code == "too_many_lines_early" and error.params["n"] == 56 and error.params["max"] == 40
    assert funnel == STOPPED_WITH_RULE
    assert set(funnel) == set(jb.FUNNEL_STEPS) - {"lines", "estimate"}
    assert funnel["open"] == full["open"] and funnel["candidates"] < full["candidates"]  # stopped midway
    assert error.params["n"] <= funnel["valid"] < full["valid"]  # the kept lines are among the valid ones
    one_thread, error = _stopped(tmp_path, "one-thread", Limits(lines_max=40), same_line_square=5, threads=1)
    assert one_thread == STOPPED_WITH_RULE and error.params["n"] == 56


def test_funnel_of_a_search_stopped_without_the_rule_as_before(tmp_path, small_parts):
    from settings import Limits
    funnel, error = _stopped(tmp_path, "stopped", Limits(lines_max=300))
    assert error.code == "too_many_lines_early" and error.params["n"] == 350
    assert funnel == STOPPED_WITHOUT_RULE


# --- the truth analysis' reason for a known line the square rule dropped (made-up data: the synthetic canyon of
# tests/test_truth_analysis.py, no known line of SlackMap) ---

def _canyon(tmp_path, side, keep):
    """test_truth_analysis's canyon with its known line "m1" (row 15, from the left rim to the right one), as a
    search with the square rule of `side` metres saved it (None: without the rule): production's found lines
    less every line within m1's tolerance, the others kept where keep(lines.npz's rows of anchor pixels) holds."""
    import dataclasses as dc
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
    import test_truth_analysis as tta
    import truth_analysis as ta
    cases = [case for case in tta.known_lines() if case[0].id == "m1"]
    folder = tta.write_capture(str(tmp_path / f"canyon-{side}"), cases)
    c = ta.load_capture(folder)
    if side is not None:
        c.grid["params"] = {**c.grid["params"], "same_line_square": side, "same_line_side": float(side)}
    line = c.known[0]
    near = set(ta.candidates([line], c.found, c.grid)[0].tolist())
    assert near  # the search without the rule finds m1
    pixels = np.array([[*_pixel(c, p), *_pixel(c, q)] for p, q in zip(c.found.xy1, c.found.xy2)])
    rows = [k for k in range(len(c.found)) if k not in near and keep(pixels[k])]
    f = c.found
    found = dc.replace(f, **{name: getattr(f, name)[rows] for name in ("a1", "a2", "length", "clearance",
                                                                    "clearance_nmpt", "over", "rep", "group",
                                                                    "xy1", "xy2")})
    return ta, dc.replace(c, found=found, _cache={}), line, pixels[rows]


def _pixel(c, xy):
    return (int(round((c.grid["top"] - xy[1]) / c.res - 0.5)), int(round((xy[0] - c.grid["left"]) / c.res - 0.5)))


def test_truth_analysis_names_a_line_the_square_rule_dropped(tmp_path):
    """A known line whose valid pair the search found, and whose pair of 20 m squares kept another line outside
    its tolerance: same_line_square (with the funnel's square_kept and that pair as the best); the same capture
    read as a search without the rule: unexplained, as before; with the rule but no line kept in the squares of
    any pair within the tolerance (rows 5-25 there: the squares of rows 0-39 hold no kept line): unexplained too."""
    # the canyon's lines at rows 1-4 lie in m1's squares (rows 0-19, cols 20-39 and 80-99) 11-14 m from its ends
    ta, c, line, kept = _canyon(tmp_path, 20, lambda p: True)
    assert ta.REASONS[-2:] == ("same_line_square", "unexplained")
    assert ((kept[:, 0] < 5) & (kept[:, 2] < 5)).any()
    r = ta.diagnose(c, line, None)
    assert r["outcome"] == "missed" and r["reason"] == "same_line_square", (r["reason"], r["note"])
    assert r["note"] is None
    assert 0 < r["funnel"]["square_kept"] <= r["funnel"]["limits"] and r["best"]["stage"] == "square"
    assert max(r["best"]["d_known"]) <= ta.tolerance(line) and r["best"]["clearance_rule"] > 0
    assert json.loads(json.dumps(ta._plain(r)))["reason"] == "same_line_square"
    assert ta.stats([ta._plain(r)])["reasons"]["same_line_square"] == 1

    ta, c, line, _ = _canyon(tmp_path, None, lambda p: True)
    r = ta.diagnose(c, line, None)
    assert r["reason"] == "unexplained" and r["note"] == "a_pair_passes" and "square_kept" not in r["funnel"]

    ta, c, line, kept = _canyon(tmp_path, 20, lambda p: p[0] >= 40 and p[2] >= 40)
    assert len(kept)
    r = ta.diagnose(c, line, None)
    assert r["reason"] == "unexplained" and r["note"] == "a_pair_passes" and r["funnel"]["square_kept"] == 0


def test_truth_analysis_squares_are_the_rules(tmp_path):
    """The analysis' squares are the rule's: production's lines of the canyon reduced by samelines.reduce_table
    (5 m squares), read back as lines.npz holds them (WGS84 to 7 decimals): every line found shares the squares
    of a kept line, a pair in squares no kept line has does not (R_FILTERED of the canyon has no anchors; a pair
    1 m long)."""
    import dataclasses as dc
    import helpers as sh
    import linesearch as ls
    import samelines
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
    import test_truth_analysis as tta
    import truth_analysis as ta
    folder = tta.write_capture(str(tmp_path / "canyon"), [case for case in tta.known_lines() if case[0].id == "m1"])
    c = ta.load_capture(folder)
    c.grid["params"] = {**c.grid["params"], "same_line_square": 5, "same_line_side": 5.0}
    p = tta.PARAMS
    table = ls.find_valid_lines(c.elevation, c.surface, c.anchors, tta.RES, p["min_length"], p["max_length"],
                                nmpt_mode="reject", threads=2, max_dh_ratio=p["max_anchor_diff"] / 100,
                                max_dh=p["max_anchor_diff_m"], high_above=p["high_above"],
                                limits=sh.LineLimits(max_wall_angle=p["max_wall_angle"]))
    a1, a2 = table.columns["a1"].copy(), table.columns["a2"].copy()

    def centre(px):
        return np.column_stack([tta.LEFT + (px[:, 1] + 0.5) * tta.RES, tta.TOP - (px[:, 0] + 0.5) * tta.RES])

    kept = sh.LineTable({"a1_xy": centre(a1), "a2_xy": centre(a2), "a1": a1, "a2": a2,
                         "length": table.columns["length"].copy(),
                         "height_mean": table.columns["height_mean"].copy(),
                         samelines.COLUMN: np.ones(len(a1), dtype=np.int64)})
    samelines.reduce_table(kept, 5.0)
    assert 0 < len(kept) < len(a1) / 2
    k = kept.columns
    found = tta._found([(tuple(p), tuple(q)) for p, q in zip(k["a1"].tolist(), k["a2"].tolist())])
    c = dc.replace(c, found=found, _cache={})
    assert ta._square_kept(c, a1, a2).all()
    assert not ta._square_kept(c, np.array([[105, 30], [5, 30]]), np.array([[105, 90], [5, 31]])).any()
    assert ta._square_kept(dc.replace(c, grid={**c.grid, "params": tta.PARAMS}, _cache={}), a1, a2).sum() == 0
