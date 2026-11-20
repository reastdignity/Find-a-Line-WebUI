"""tools/view_numbers.py: the page's placement of the view's numbers run again in Python under other rules. The
greedy and the overlaps on made-up numbers (offline, no browser); then the tool on the result view's clip run
(clip_runs.view_clip) in Edge, on the desktop and a phone's profile: in every state the greedy at today's rule gives
exactly the page's own numbers (labels and places), the rules' counts add up, and the pictures of a sheet show the
page's numbers where the page draws them. Run from PowerShell (.claude/rules/browser-tests.md)."""

import json
import os
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import view_numbers as vn  # noqa: E402


def _n(label, cand, fan=False, kind=None):
    kind = kind or label[0]
    w, h = (19, 13.5) if kind == "P" else (17.5, 10.5) if kind == "L" else (15 if len(label) > 2 else 12.5, 10.5)
    return {"label": label, "kind": kind, "w": w, "h": h, "cand": [list(c) for c in cand], "fan": fan}


def test_place_follows_the_page_and_the_rules():
    """The first number takes its first place; a place a quarter of a box from another is kept today (not nearer
    than a quarter), left out under a third; a number without a free piece has no room; a number tries its places
    in order until one is a box away; a fan number has one place, never left out today, left out under "quarter"."""
    numbers = [_n("B1", [(100, 100)]), _n("B2", [(108, 100)]), _n("B3", []),
               _n("B4", [(100, 103), (200, 200), (300, 300)]), _n("L1", [(101, 100)], fan=True)]
    today = {n["label"]: n for n in vn.place(numbers, "today")}
    assert [today[k]["status"] for k in ("B1", "B2", "B3", "B4", "L1")] == ["drawn", "drawn", "no room", "drawn", "drawn"]
    assert (today["B2"]["apart"], today["B4"]["x"], today["B4"]["y"]) == (0.25, 200, 200)  # 8 px is a quarter of 32
    third = {n["label"]: n["status"] for n in vn.place(numbers, "third")}
    assert third == {"B1": "drawn", "B2": "left out", "B3": "no room", "B4": "drawn", "L1": "left out"}
    assert {n["label"]: n["status"] for n in vn.place(numbers, "quarter")}["L1"] == "left out"
    never = vn.place(numbers, "never")
    assert [n["status"] for n in never] == ["drawn", "drawn", "no room", "drawn", "drawn"]
    # the farthest place wins when none is a box away
    far = vn.place([_n("B1", [(0, 0)]), _n("B2", [(4, 0), (12, 0), (8, 0)])], "today")
    assert (far[1]["status"], far[1]["x"], far[1]["apart"]) == ("drawn", 12, 12 / 32)


def test_overlaps_count_by_the_smaller_box():
    """B1 and B2 8 px apart side by side share 17 × 21 px of a 25 × 21 box (68 %); a P diamond's box and a B box
    touching at an edge share nothing; the shares are of the smaller box."""
    s = vn.summary_of([_n("B1", [(100, 100)]), _n("B2", [(108, 100)]), _n("P1", [(100, 100 + 10.5 + 13.5)])], "never")
    o = s["overlaps"]
    assert (s["drawn"], o["any"], o[">1/4"], o[">1/3"], o[">1/2"]) == (3, 1, 1, 1, 1)
    assert o["pairs"][0]["px2"] == 17 * 21 and o["pairs"][0]["of_smaller"] == round(17 * 21 / (25 * 21), 4)
    small = vn.overlaps([{"label": "B10", "status": "drawn", "x": 0, "y": 0, "w": 15, "h": 10.5},
                         {"label": "L1", "status": "drawn", "x": 30, "y": 0, "w": 17.5, "h": 10.5}])
    assert small["any"] == 1 and small[">1/4"] == 0  # 2.5 × 21 px of the 30 × 21 box


def test_today_matches_names_the_difference():
    numbers = [_n("B1", [(10, 10)]), _n("B2", [(11, 10), (100, 10)])]
    assert vn.today_matches(numbers, [{"label": "B1", "x": 10, "y": 10}, {"label": "B2", "x": 100, "y": 10}]) == (True, "")
    ok, why = vn.today_matches(numbers, [{"label": "B1", "x": 10, "y": 10}])
    assert not ok and "labels" in why
    ok, why = vn.today_matches(numbers, [{"label": "B1", "x": 10, "y": 10}, {"label": "B2", "x": 99, "y": 10}])
    assert not ok and "B2" in why


def test_a_run_without_a_store_is_left_out(tmp_path):
    """A run saved before the store (data.js only) cannot open in the view: left out with the reason, no browser."""
    run = tmp_path / "runs" / "2026-10-25_085353_Old"
    run.mkdir(parents=True)
    (run / "run.json").write_text(json.dumps({"id": run.name, "params": {}}), "utf-8")
    assert vn.find_run(run.name, str(tmp_path), None) == str(run)
    result = vn.measure_runs([str(run)], str(tmp_path / "out"), str(tmp_path / "data"), ["desktop"], [1], [10])
    assert result["runs"][0]["left_out"].startswith("the run has no store")
    assert "Left out" in (tmp_path / "out" / "view_numbers.md").read_text("utf-8")


from test_web import EDGE, _playwright  # noqa: E402


@pytest.fixture(scope="module")
def view_clip(tmp_path_factory):
    import clip_runs
    return clip_runs.view_clip(tmp_path_factory, "view-numbers")


@pytest.mark.skipif(not os.path.exists(EDGE) or not _playwright(), reason="needs Microsoft Edge and Playwright (group ui)")
def test_the_clip_run_on_a_desktop_and_a_phone(tmp_path, view_clip):
    """The tool on the clip run in Edge (the desktop's and Pixel 7's profiles): every state measured, the greedy at a
    quarter equal to the page's numbers in each; the counts add up per rule; the fan opened with two rows or more;
    the sheets made, the page's numbers in them as counted and today's numbers drawn over the bare map where the
    page draws its own."""
    out = tmp_path / "out"
    result = vn.measure_runs([str(view_clip)], str(out), str(tmp_path / "data"), ["desktop", "pixel"], [1], [10, 30],
                             sheets=True, launch=lambda pw, engine: pw.chromium.launch(channel="msedge", headless=True))
    entry = result["runs"][0]
    assert not entry.get("left_out") and set(entry["devices"]) == {"desktop", "pixel"}
    for device, d in entry["devices"].items():
        assert not d.get("error") and d["page_errors"] == [], (device, d.get("error"), d.get("page_errors"))
        states = d["states"]
        assert {s["case"] for s in states} == {"map", "fan"} and {s["stop"] for s in states} == {0, 1}
        for s in states:
            assert s["today_matches"] and s["rules"], (device, s.get("error"))
            for rule, r in s["rules"].items():
                assert r["drawn"] + r["left_out"] + r["no_room"] == s["wanted"], (device, rule)
                assert r["no_room"] == s["rules"]["never"]["no_room"] and (rule != "never" or r["left_out"] == 0)
            if s["case"] == "fan":
                assert s["fan_rows"] >= 2 and s["wanted_fan"] == s["fan_rows"]
        assert sum(s["wanted"] for s in states if s["case"] == "map") > 0
        for p in d["pictures"]:
            assert p["same_numbers_as_counted"] and (out / p["sheet"]).is_file(), p
            if p["case"] == "map":  # the numbers lie on top of the page's canvas: the overlay redraws them as they are
                assert p["today_over_bare_vs_page"]["pixels_apart"] < 0.002, p
    text = (out / "view_numbers.md").read_text("utf-8")
    assert "| first view | map |" in text and "fan (" in text
    assert vn.not_measured(result) == 0
    # the clip's run is named after its place's coordinates: none of them in an output or a file's name
    assert entry["run"] == entry["label"] == "run 1"
    names = " ".join(os.listdir(out / "pictures") + os.listdir(out / "sheets"))
    for written in (text, (out / "view_numbers.json").read_text("utf-8"), names):
        assert view_clip.name not in written and not vn.COORDINATES.search(written)
    # the zoom stops with the run's best spot in the middle of the map: measured as well
    best = vn.measure_runs([str(view_clip)], str(tmp_path / "best"), str(tmp_path / "data"), ["desktop"], [1], [10],
                           launch=lambda pw, engine: pw.chromium.launch(channel="msedge", headless=True), around="best")
    states = best["runs"][0]["devices"]["desktop"]["states"]
    assert best["around"] == "best" and vn.not_measured(best) == 0 and {s["stop"] for s in states} == {0, 1}
    assert all(s["today_matches"] for s in states)
