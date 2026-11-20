"""tools/view_numbers.py: the page's placement of the view's numbers run again in Python under other rules. The
greedy, today's third (the fan's numbers too; a quarter before 2026-11-20), the overlaps in both readings (compared
unrounded), the check against the page, the command line (offline, no browser); then the tool on the result view's
clip run (clip_runs.view_clip) in Edge, on the desktop and a phone's profile: in every state the greedy at today's
rule gives exactly the page's own numbers (labels, places, sizes), in one of them today's third and the quarter of
before give different numbers (the page's threshold is pinned), a fan
state is counted once, and the sheets show the page's numbers as the page draws them. Run from PowerShell
(.claude/rules/browser-tests.md)."""

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
    """The first number takes its first place; a place a quarter of a box from another is left out today (nearer
    than a third: the user's N1 b), kept under "before" (the page's quarter until 2026-11-20); a number without a free
    piece has no room; a number tries its places in order until one is a box away; a fan number has one place, left
    out today and under "quarter" (the user's N2 a), never under "before"."""
    numbers = [_n("B1", [(100, 100)]), _n("B2", [(108, 100)]), _n("B3", []),
               _n("B4", [(100, 103), (200, 200), (300, 300)]), _n("L1", [(101, 100)], fan=True)]
    before = {n["label"]: n for n in vn.place(numbers, "before")}
    assert [before[k]["status"] for k in ("B1", "B2", "B3", "B4", "L1")] == ["drawn", "drawn", "no room", "drawn", "drawn"]
    assert (before["B2"]["apart"], before["B4"]["x"], before["B4"]["y"]) == (0.25, 200, 200)  # 8 px is a quarter of 32
    today = {n["label"]: n["status"] for n in vn.place(numbers, "today")}
    assert today == {"B1": "drawn", "B2": "left out", "B3": "no room", "B4": "drawn", "L1": "left out"}
    assert {n["label"]: n["status"] for n in vn.place(numbers, "quarter")}["L1"] == "left out"
    never = vn.place(numbers, "never")
    assert [n["status"] for n in never] == ["drawn", "drawn", "no room", "drawn", "drawn"]
    # the farthest place wins when none is a box away
    far = vn.place([_n("B1", [(0, 0)]), _n("B2", [(4, 0), (12, 0), (8, 0)])], "today")
    assert (far[1]["status"], far[1]["x"], far[1]["apart"]) == ("drawn", 12, 12 / 32)


def test_the_third_is_the_line_today():
    """Today's rule (a third, SpotMap.ts APART_MIN) leaves a number out at 0.30 of a box (dx 9.6 px), keeps one at
    0.34 (10.88 px); vertically the box is 23 px (0.30: 6.9 px out, 0.34: 7.82 px kept); "before" (a quarter) kept
    both at 0.30 and left out at 0.24. A fan number is left out today at 0.30 of a box from a B number, kept at 0.34."""
    numbers = [_n("B1", [(0, 0)]), _n("B2", [(0.30 * 32, 0)]), _n("B3", [(100, 0)]), _n("B4", [(100 + 0.34 * 32, 0)]),
               _n("B5", [(300, 0)]), _n("B6", [(300, 0.30 * 23)]), _n("B7", [(500, 0)]), _n("B8", [(500, 0.34 * 23)]),
               _n("B9", [(700, 0)]), _n("B10", [(700 + 0.24 * 32, 0)]),
               _n("L1", [(0, 0.30 * 23 + 300)], fan=True), _n("L2", [(0, 300 + 23)], fan=True),
               _n("L3", [(0.34 * 32, 300 + 23)], fan=True)]
    today = [n["status"] for n in vn.place(numbers, "today")]
    assert today == ["drawn", "left out", "drawn", "drawn", "drawn", "left out", "drawn", "drawn", "drawn", "left out",
                     "drawn", "drawn", "drawn"]
    numbers[10]["cand"] = [[0, 0.30 * 23]]  # L1 at 0.30 of a box under B1: left out today, never before
    assert vn.place(numbers, "today")[10]["status"] == "left out" and vn.place(numbers, "before")[10]["status"] == "drawn"
    assert [n["status"] for n in vn.place(numbers, "before")][:10] == ["drawn"] * 9 + ["left out"]
    s = vn.summary_of(numbers, "today")
    assert (s["drawn"], s["left_out"], s["left_out_marks"], s["left_out_fan"]) == (9, 4, 3, 1)
    assert vn.RULES["today"] == (1 / 3, 1 / 3)


def test_overlaps_count_both_readings_unrounded():
    """B1 and B2 8 px apart side by side share 17 × 21 px: 68 % of a 25 × 21 box, 48.5 % of the page's 32 × 23 box;
    a P diamond's box and a B box touching at an edge share nothing; a share a hair over a bound is over it (compared
    before any rounding)."""
    s = vn.summary_of([_n("B1", [(100, 100)]), _n("B2", [(108, 100)]), _n("P1", [(100, 100 + 10.5 + 13.5)])], "never")
    o = s["overlaps"]
    assert (s["drawn"], o["any"]) == (3, 1)
    assert o["smaller"] == {">1/4": 1, ">1/3": 1, ">1/2": 1} and o["box"] == {">1/4": 1, ">1/3": 1, ">1/2": 0}
    assert o["pairs"][0]["px2"] == 17 * 21 and o["pairs"][0]["of_box"] == round(17 * 21 / (32 * 23), 4)
    small = vn.overlaps([{"label": "B10", "status": "drawn", "x": 0, "y": 0, "w": 15, "h": 10.5},
                         {"label": "L1", "status": "drawn", "x": 30, "y": 0, "w": 17.5, "h": 10.5}])
    assert small["any"] == 1 and small["smaller"][">1/4"] == 0  # 2.5 × 21 px of the 30 × 21 box
    for bound, name in ((0.25, ">1/4"), (1 / 3, ">1/3"), (0.5, ">1/2")):
        dx = 25 - (bound + 3e-5) * 25  # a share of the smaller box 0.00003 over the bound
        hair = vn.overlaps([{"label": "B1", "status": "drawn", "x": 0.0, "y": 0.0, "w": 12.5, "h": 10.5},
                            {"label": "B2", "status": "drawn", "x": dx, "y": 0.0, "w": 12.5, "h": 10.5}])
        assert hair["smaller"][name] == 1 and hair["pairs"][0]["of_smaller"] == round(bound + 3e-5, 4), name


def test_today_matches_names_the_difference():
    numbers = [_n("B1", [(10, 10)]), _n("B2", [(11, 10), (100, 10)])]
    page = [{"label": "B1", "x": 10, "y": 10, "w": 12.5, "h": 10.5}, {"label": "B2", "x": 100, "y": 10, "w": 12.5, "h": 10.5}]
    assert vn.today_matches(numbers, page) == (True, "")
    ok, why = vn.today_matches(numbers, page[:1])
    assert not ok and "labels" in why
    ok, why = vn.today_matches(numbers, [page[0], {**page[1], "x": 99}])
    assert not ok and "B2" in why
    # a wrong copy of the shapes' sizes is caught though every place agrees
    ok, why = vn.today_matches([dict(n, w=20, h=5) for n in numbers], page)
    assert not ok and "40" in why and "25" in why


def _old_run(tmp_path):
    run = tmp_path / "runs" / "2026-10-25_085353_Old"
    run.mkdir(parents=True)
    (run / "run.json").write_text(json.dumps({"id": run.name, "params": {}}), "utf-8")
    return run


def test_a_run_without_a_store_is_left_out(tmp_path):
    """A run saved before the store (data.js only) cannot open in the view: left out with the reason, no browser."""
    run = _old_run(tmp_path)
    assert vn.find_run(run.name, str(tmp_path), None) == str(run)
    result = vn.measure_runs([str(run)], str(tmp_path / "out"), str(tmp_path / "data"), ["desktop"], [1], [10])
    assert result["runs"][0]["left_out"].startswith("the run has no store")
    assert "Left out" in (tmp_path / "out" / "view_numbers.md").read_text("utf-8")


def test_the_command_line(tmp_path):
    """The command line on a run without a store (offline, no browser): exit 0 (left out is no failure), the label
    and the note in the md and the JSON, the command and the commit recorded in both; a --label or --note without
    "=" is the parser's error."""
    run = _old_run(tmp_path)
    out = tmp_path / "out"
    args = ["--out", str(out), "--runs", str(run), "--data-dir", str(tmp_path / "data"), "--label", f"{run.name}=old",
            "--note", f"{run.name}=A run saved before the store."]
    assert vn.main(args) == 0
    result = json.loads((out / "view_numbers.json").read_text("utf-8"))
    entry, made = result["runs"][0], result["made_by"]
    assert (entry["label"], entry["note"]) == ("old", "A run saved before the store.")
    assert made["command"].startswith("tools/view_numbers.py --out ") and "--note" in made["command"]
    assert made["commit"] and len(made["commit"]) == 40
    text = (out / "view_numbers.md").read_text("utf-8")
    assert "## old" in text and "A run saved before the store." in text and made["commit"] in text
    for bad in (["--label", "old"], ["--note", f"{run.name}="]):
        with pytest.raises(SystemExit):
            vn.main(["--out", str(out), "--runs", str(run)] + bad)


def test_main_passes_stub_tiles(tmp_path, monkeypatch):
    """`--stub-tiles` on the command line reaches measure_runs as stub_tiles=True (the pictures offline); without the
    flag, False (the base map's tiles, as before)."""
    run = _old_run(tmp_path)
    seen = []

    def fake(*args, **kwargs):
        seen.append(kwargs.get("stub_tiles"))
        return {"runs": []}
    monkeypatch.setattr(vn, "measure_runs", fake)
    base = ["--out", str(tmp_path / "out"), "--runs", str(run), "--data-dir", str(tmp_path / "data")]
    assert vn.main(base + ["--stub-tiles"]) == 0 and vn.main(base) == 0
    assert seen == [True, False]


def test_stub_tile_is_one_plain_picture():
    """The stub tile (offline pictures: `--stub-tiles`): a 256 x 256 PNG, every pixel the map's background colour."""
    import io
    from PIL import Image
    img = Image.open(io.BytesIO(vn.stub_tile()))
    assert img.format == "PNG" and img.size == (256, 256)
    assert img.convert("RGB").getcolors() == [(256 * 256, vn.STUB_TILE_RGB)]


def test_default_launch_launches_the_engine():
    class Engine:
        def launch(self):
            return ("launched", self.name)
    pw = type("Pw", (), {})()
    for name in ("chromium", "webkit"):
        engine = Engine()
        engine.name = name
        setattr(pw, name, engine)
    assert vn.default_launch(pw, "webkit") == ("launched", "webkit")


from test_web import EDGE, _playwright  # noqa: E402


@pytest.fixture(scope="module")
def view_clip(tmp_path_factory):
    import clip_runs
    return clip_runs.view_clip(tmp_path_factory, "view-numbers")


@pytest.mark.skipif(not os.path.exists(EDGE) or not _playwright(), reason="needs Microsoft Edge and Playwright (group ui)")
def test_the_clip_run_on_a_desktop_and_a_phone(tmp_path, view_clip):
    """The tool on the clip run in Edge (the desktop's and Pixel 7's profiles), Best 10 and 100: every state
    measured, the greedy at today's rule (a third, the fan's numbers too) equal to the page's numbers (labels,
    places, sizes) in each; in some state today's rule and "before" (a quarter, the fan's never) give different
    numbers, so the page's threshold is today's; a fan state counted once
    (another stop that reached it names it); the sheets made under the label, with the note, the page's numbers in
    them as counted and today's numbers drawn over the bare map as the page draws them (map and fan). Offline: every
    request outside the local server is answered by the tool's stub (`stub_tiles`), so the pictures hold the numbers
    and lines over a plain map and do not depend on the internet's tiles or their timing."""
    out = tmp_path / "out"
    edge = lambda pw, engine: pw.chromium.launch(channel="msedge", headless=True)  # noqa: E731
    result = vn.measure_runs([str(view_clip)], str(out), str(tmp_path / "data"), ["desktop", "pixel"], [1], [10, 100],
                             sheets=True, launch=edge, labels={view_clip.name: "clip"},
                             notes={view_clip.name: "The result view's clip run."}, stub_tiles=True)
    entry = result["runs"][0]
    assert not entry.get("left_out") and set(entry["devices"]) == {"desktop", "pixel"}
    assert (entry["label"], entry["note"]) == ("clip", "The result view's clip run.")
    pinned = 0
    for device, d in entry["devices"].items():
        assert not d.get("error") and d["page_errors"] == [], (device, d.get("error"), d.get("page_errors"))
        states = d["states"]
        assert {s["case"] for s in states} == {"map", "fan"} and {s["stop"] for s in states} == {0, 1}
        for s in states:
            if "same_as_stop" in s:  # the fan fitted the map: the state of an earlier stop, named there
                first = next(f for f in states if f["case"] == "fan" and f["stop"] == s["same_as_stop"] and "rules" in f)
                assert s["stop"] in first["also_stops"] and s["zoom"] == first["zoom"] and "rules" not in s
                continue
            assert s["today_matches"] and s["rules"], (device, s.get("error"))
            pinned += s["rules"]["today"]["drawn"] != s["rules"]["before"]["drawn"]
            if s["case"] == "fan":
                assert s["fan_rows"] >= 2 and s["wanted_fan"] == s["fan_rows"]
        for p in d["pictures"]:
            assert p["same_numbers_as_counted"] and (out / p["sheet"]).is_file() and "clip-" in p["sheet"], p
            # the overlay redraws the page's numbers as they are (one number missing is about 0.0005 of the pixels)
            assert p["today_over_bare_vs_page"]["pixels_apart"] < 1e-4, p
    assert pinned >= 1, "no state where today's third and the quarter of before differ: the page's threshold is not pinned"
    text = (out / "view_numbers.md").read_text("utf-8")
    assert "| first view |" in text and "Lines from here" in text and "The result view's clip run." in text
    assert "the page's box of 32 × 23 px" in text and result["made_by"]["commit"] in text
    assert vn.not_measured(result) == 0
    # the clip's run is named after its place's coordinates: none of them in an output or a file's name
    assert entry["run"] == "clip"
    names = " ".join(os.listdir(out / "pictures") + os.listdir(out / "sheets"))
    for written in (text, (out / "view_numbers.json").read_text("utf-8"), names):
        assert view_clip.name not in written and not vn.COORDINATES.search(written)
    # the zoom stops with the run's best spot in the middle of the map: measured as well
    best = vn.measure_runs([str(view_clip)], str(tmp_path / "best"), str(tmp_path / "data"), ["desktop"], [1], [10],
                           launch=edge, around="best", stub_tiles=True)
    states = best["runs"][0]["devices"]["desktop"]["states"]
    assert best["around"] == "best" and vn.not_measured(best) == 0 and {s["stop"] for s in states} == {0, 1}
    assert all(s["today_matches"] for s in states if "same_as_stop" not in s)
