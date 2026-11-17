"""tools/ui_shots.py: its data edits (the browser passes run by hand, .claude/rules/viewer.md "Verifying changes")."""

import hashlib
import json
import os
import sys

import numpy as np
import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import linestore  # noqa: E402
import ui_shots  # noqa: E402


class TimeoutError(Exception):  # noqa: A001 (Playwright's error is known by this name)
    pass


class FakeElement:
    def __init__(self, page, selector):
        self.page, self.selector = page, selector

    def is_visible(self):
        return True

    def scroll_into_view_if_needed(self):
        self.page.calls.append(("scroll", self.selector))

    def click(self):
        self.page.calls.append(("click", self.selector))
        if self.selector in self.page.stuck:
            raise TimeoutError("Timeout 10000ms exceeded.\nwaiting for element to be stable")


class Clock:
    """A clock for ui_shots.time that only the fakes move (each call of theirs takes the seconds of TAKES)."""
    now = None  # the clock installed by the fixture `clock`, else None

    def __init__(self):
        self.t = 1000.0

    def perf_counter(self):
        return self.t


TAKES = {"launch": 0.3, "new_context": 0.7, "init": 0.01, "context.close": 0.2, "browser.close": 0.1,
         "goto": 1.0, "shot": 0.5}


def _take(what, seconds=None):
    if Clock.now is not None:
        Clock.now.t += TAKES[what] if seconds is None else seconds


class FakePage:
    """A Playwright page for the step runner: `true` the expressions that hold (waits for the others time out),
    `shown` the selectors a click finds, `stuck` those whose click fails, `throws` the scripts that raise,
    `interrupt` the addresses whose load is interrupted (Ctrl+C)."""

    def __init__(self, true=(), shown=(), stuck=(), throws=(), interrupt=(), shot_errors=()):
        self.true, self.shown, self.stuck, self.throws = set(true), set(shown) | set(stuck), set(stuck), set(throws)
        self.interrupt, self.shot_errors = tuple(interrupt), list(shot_errors)
        self.calls, self.closed, self.default_timeout = [], False, None

    def set_default_timeout(self, ms):
        self.default_timeout = ms

    def set_default_navigation_timeout(self, ms):
        self.navigation_timeout = ms

    def add_init_script(self, script):
        self.calls.append(("init", script))

    def goto(self, url):
        self.calls.append(("goto", url))
        _take("goto")
        if any(part in url for part in self.interrupt):
            raise KeyboardInterrupt

    def wait_for_timeout(self, ms):
        self.calls.append(("sleep", ms))
        _take("sleep", ms / 1000)

    def wait_for_function(self, expression, timeout):
        self.calls.append(("wait", expression, timeout))
        if not any(t in expression for t in self.true):
            raise TimeoutError(f"Timeout {timeout}ms exceeded.")

    def evaluate(self, script, arg=None):
        self.calls.append(("evaluate", script))
        if script in self.throws:
            raise Exception("Error: TypeError: x is null\n    at eval")
        return any(t in script for t in self.true)

    def query_selector(self, selector):
        return FakeElement(self, selector) if selector in self.shown else None

    def screenshot(self, path, full_page=False, timeout=None, scale="device"):
        self.calls.append(("shot", path, full_page) + ((scale,) if scale != "device" else ()))
        _take("shot")
        if self.shot_errors:
            raise Exception(self.shot_errors.pop(0))
        with open(path, "wb") as f:
            f.write(b"png")

    def close(self):
        self.closed = True


class FakeContext:
    def __init__(self, **page):
        self.page, self.pages, self.cookies, self.scripts, self.closed = page, [], [], [], False

    def add_init_script(self, script):
        self.scripts.append(script)
        _take("init")

    def close(self):
        self.closed = True
        _take("context.close")

    def clear_cookies(self):
        self.cookies = []

    def add_cookies(self, cookies):
        self.cookies += cookies

    def new_page(self):
        self.pages.append(FakePage(**self.page))
        return self.pages[-1]


SITE = {"url": "https://localhost:1", "cookies": {"admin": "a", "walker": "w"}, "run": "R", "share": "S",
        "line": "1,2,3,4", "also": "", "border": "#layer"}


def _shoot(context, name, tmp_path, state=None, device="desktop", theme="light"):
    state = state or ui_shots.Pass(device, theme)
    return ui_shots.shoot_page(context, SITE, name, device, theme, str(tmp_path), state)


def test_a_page_from_its_load_to_its_shot(tmp_path):
    """shoot_page: the page's address, its user's cookie, its steps in order, its picture and its record (seconds
    of each part, the outcome); clicks wait 10 s; a click that finds nothing leaves the page out (no picture)."""
    context = FakeContext(shown={".r-filters .u-chip.u-add"}, true={"leaflet-tile", "r-by"})
    row = _shoot(context, "c-result-grouping", tmp_path)
    page = context.pages[0]
    path = str(tmp_path / "c-result-grouping-desktop-light.png")
    assert row["path"] == path and os.path.isfile(path) and page.closed and row["outcome"] == "saved"
    assert page.default_timeout == ui_shots.CLICK_MS == 10000 and page.navigation_timeout == 30000  # the load's kept
    assert ("goto", "https://localhost:1/?ui=c#run=R") in page.calls
    assert ("click", ".r-filters .u-chip.u-add") in page.calls
    assert context.cookies[0]["value"] == "a"
    assert [s["outcome"] for s in row["steps"]] == ["done", "done"]
    assert all(row[k] >= 0 for k in ("load", "settle", "tiles", "shot", "seconds")) and not row["tiles_loading"]
    context = FakeContext()  # no chip on this device; the tiles still loading are a note
    row = _shoot(context, "c-result-more", tmp_path, device="iphone", theme="dark")
    assert row["outcome"] == "left out" and row["path"] is None and row["tiles_loading"] and not row["timeouts"]
    assert row["reason"] == "the device does not show .r-filters .u-chip.u-add"
    assert context.pages[0].closed and not os.path.exists(tmp_path / "c-result-more-iphone-dark.png")
    assert not ui_shots.failed([row])
    context = FakeContext(true={"leaflet-tile"})  # a visitor: no cookie; a map's own page
    _shoot(context, "page-signin", tmp_path)
    assert context.cookies == []
    _shoot(context, "map-shared", tmp_path)
    assert ("goto", "https://localhost:1/s/S/map.html") in context.pages[-1].calls


def test_a_wait_that_times_out_is_shortened_in_its_pass(tmp_path):
    """A "wait:" that timed out: noted in the record (picture saved, exit code 1); the same expression's later
    waits in the pass get a quarter of the limit, a new pass the whole limit again."""
    state = ui_shots.Pass("desktop", "light")
    context = FakeContext(true={"leaflet-tile"}, shown={".v3-views [data-view=eyes]"})
    first = _shoot(context, "view3d", tmp_path, state)
    second = _shoot(context, "view3d-eyes", tmp_path, state)
    ready = ui_shots.VIEW3D_READY[5:]
    assert first["outcome"] == second["outcome"] == "timed out" and first["path"] and second["path"]
    assert first["timeouts"] == [ready] and second["timeouts"] == [ready, "document.getElementById('view3d')?."
                                                                          "dataset.view === 'eyes'"]
    waits = [c[2] for page in context.pages for c in page.calls if c[0] == "wait" and "leaflet-tile" not in c[1]]
    assert waits == [60000, 15000, 60000]
    assert ui_shots.failed([first])
    other = ui_shots.Pass("desktop", "dark")
    assert other.limit(ready) == 60000 and state.limit(ready) == 15000


def test_strict_stops_at_the_first_timeout(tmp_path):
    """--strict: the page whose wait timed out is not shot."""
    state = ui_shots.Pass("desktop", "light", strict=True)
    context = FakeContext(true={"leaflet-tile"})
    row = _shoot(context, "view3d-shaded", tmp_path, state)
    assert row["outcome"] == "timed out" and row["path"] is None and len(row["steps"]) == 1
    assert ("evaluate", ui_shots.SHADED_ON[3:]) not in context.pages[0].calls and context.pages[0].closed


def test_a_step_that_raises_is_recorded(tmp_path):
    """A click Playwright cannot do or a script that raises: the page failed (its first line, no picture), the
    page closed, the next page goes on."""
    context = FakeContext(true={"leaflet-tile"}, stuck={".r-filters .u-chip.u-add"})
    row = _shoot(context, "c-result-more", tmp_path)
    assert row["outcome"] == "failed" and row["path"] is None and context.pages[0].closed
    assert row["error"] == "Timeout 10000ms exceeded." and row["steps"][0]["outcome"] == "failed"
    context = FakeContext(true={"leaflet-tile"}, throws={ui_shots.CELL_AT_CENTRE})
    row = _shoot(context, "c-layer-cell", tmp_path)
    assert row["outcome"] == "failed" and row["error"] == "Error: TypeError: x is null"
    assert ui_shots.failed([row])
    row = _shoot(FakeContext(true={"leaflet-tile"}), "c-home", tmp_path)
    assert row["outcome"] == "saved"
    lines = ui_shots.summary({"the server's start": 1.0}, [], [row, *[_shoot(FakeContext(true={"leaflet-tile"},
                             stuck={".r-filters .u-chip.u-add"}), "c-result-more", tmp_path)]], {}, 9.0)
    assert any(line.startswith("Failed: c-result-more (desktop light): .r-filters .u-chip.u-add: Timeout")
               for line in lines)


def test_need_waits_for_the_result_then_tests_once(tmp_path):
    """A "need:" step waits for the result's map (NEED_READY), not for its expression: false once, the page is
    left out at once, with no timeout; true, the page is shot."""
    context = FakeContext(true={"leaflet-tile", ui_shots.NEED_READY})
    row = _shoot(context, "c-result-shore-folded", tmp_path)
    page = context.pages[0]
    assert row["outcome"] == "left out" and not row["timeouts"] and row["reason"].startswith("the run does not have")
    assert [c[1] for c in page.calls if c[0] == "wait"][1:] == [f"() => ({ui_shots.NEED_READY})"]
    assert ("evaluate", "!!(document.querySelector('.u-shore-ctl:not([hidden])'))") in page.calls
    after = page.calls[page.calls.index(("wait", f"() => ({ui_shots.NEED_READY})", ui_shots.WAIT_MS)) + 1:]
    assert after == [("evaluate", "!!(document.querySelector('.u-shore-ctl:not([hidden])'))")]  # no wait, no sleep
    context = FakeContext(true={"leaflet-tile", ui_shots.NEED_READY, "u-shore-ctl"})
    assert _shoot(context, "c-result-shore-folded", tmp_path)["outcome"] == "saved"


def test_pages_selected_by_their_names():
    """--only: the pages whose name contains one of its parts, all for none; --exclude then drops those whose name
    contains one of its parts."""
    assert list(ui_shots.select_pages()) == list(ui_shots.PAGES)
    assert set(ui_shots.select_pages("c-line,map-shared")) == {"c-line", "c-line-profile", "map-shared",
                                                                 "map-shared-credits"}
    assert set(ui_shots.select_pages("c-line,map-shared", "credits,profile")) == {"c-line", "map-shared"}
    assert "c-home" not in ui_shots.select_pages(exclude="home")


def test_tables_name_pages():
    """Every page that NEEDS, LAYOUTS and LAYER_LAYOUTS name is a page of PAGES; every feature has its reason."""
    for table in (ui_shots.NEEDS, ui_shots.LAYOUTS, ui_shots.LAYER_LAYOUTS):
        assert set(table) <= set(ui_shots.PAGES), set(table) - set(ui_shots.PAGES)
    assert set(ui_shots.NEEDS.values()) == set(ui_shots.LACKS)


def _run_json(folder, params=None, shore=None):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "run.json").write_text(json.dumps({"id": folder.name, "params": params or {}, "shore": shore}),
                                     encoding="utf-8")
    return str(folder)


def test_run_features(tmp_path):
    """run_features: "lift" with a no-fall zone or A-frames, "shore" with an uncertain shore's segment, "found" with
    the square rule; the pages of the features a run lacks are left out by the run."""
    segment = {"kind": "sea", "px": 40, "m": 120.0, "ring": []}
    assert ui_shots.run_features(_run_json(tmp_path / "plain", {"end_zone": 0, "anchor_lift": 0})) == set()
    assert ui_shots.run_features(_run_json(tmp_path / "zone", {"end_zone": 5})) == {"lift"}
    assert ui_shots.run_features(_run_json(tmp_path / "frames", {"anchor_lift": 2})) == {"lift"}
    assert ui_shots.run_features(_run_json(tmp_path / "square", {"same_line_side": 10})) == {"found"}
    assert ui_shots.run_features(_run_json(tmp_path / "shore", {}, {"segments": [segment]})) == {"shore"}
    assert ui_shots.run_features(_run_json(tmp_path / "none", {}, {"segments": [], "totals": {}})) == set()
    (tmp_path / "old").mkdir()  # a run.json of before the params' keys and the shore
    (tmp_path / "old" / "run.json").write_text(json.dumps({"id": "old"}), encoding="utf-8")
    assert ui_shots.run_features(str(tmp_path / "old")) == set()
    pages = ui_shots.select_pages("c-result")
    assert ui_shots.left_out_by_run(pages, {"shore"}) == {"c-result-rigging": ui_shots.LACKS["lift"],
                                                          "c-result-why": ui_shots.LACKS["found"]}
    assert ui_shots.left_out_by_run(pages, {"lift", "shore", "found"}) == {}


def test_summary():
    """The summary: the set-up's parts, the passes, the slowest pages, the pages left out (by the run once, by a
    device per page with its passes) and every timeout."""
    def row(page, device, seconds, outcome="saved", reason=None, timeouts=()):
        return {"page": page, "device": device, "theme": "light", "outcome": outcome, "reason": reason,
                "path": "x" if outcome in ("saved", "timed out") else None, "seconds": seconds,
                "timeouts": list(timeouts), "steps": [], "error": None, "tiles_loading": False}
    rows = [row(f"p{k}", "desktop", k) for k in range(12)] + [
        row("c-menu", "desktop", 1, "left out", "the device does not show .c-account-btn"),
        row("c-menu", "iphone", 1, "left out", "the device does not show .c-account-btn"),
        row("view3d", "pixel", 70, "timed out", timeouts=["x === 1"])]
    lines = ui_shots.summary({"the clip's search": 23.04}, [{"device": "desktop", "theme": "light", "seconds": 80.0,
                                                             "saved": 12, "left_out": 1}],
                             rows, {"c-result-why": ui_shots.LACKS["found"]}, 100.0)
    text = "\n".join(lines)
    assert "Summary: 100.0 s, 13 pictures" in text and "the clip's search 23.0 s" in text
    assert "Pass desktop light: 80.0 s, 12 saved, 1 left out" in text
    assert "Slowest pages: view3d (pixel light) 70.0 s, p11 (desktop light) 11.0 s" in text and "p1 " not in text
    assert f"Left out: c-result-why: {ui_shots.LACKS['found']}" in text
    assert "Left out: c-menu: the device does not show .c-account-btn (desktop light, iphone light)" in text
    assert "Timed out: view3d (pixel light): x === 1" in text


def test_data_key_follows_the_files(tmp_path, monkeypatch):
    """data_key: the sha256 of the root *.py, the tool, the cube's test module and the clip's files; a change of
    any of them (or a new root module) changes it, another file does not."""
    for name in ["a.py", "b.py", "notes.md"] + ui_shots.KEYED:
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_bytes(name.encode())
    monkeypatch.setattr(ui_shots, "REPO", str(tmp_path))
    key = ui_shots.data_key()
    assert key == ui_shots.data_key()
    (tmp_path / "notes.md").write_text("other")
    assert ui_shots.data_key() == key
    for name in ["b.py", ui_shots.KEYED[3]]:
        before = (tmp_path / name).read_bytes()
        (tmp_path / name).write_bytes(before + b"!")
        assert ui_shots.data_key() != key
        (tmp_path / name).write_bytes(before)
    assert ui_shots.data_key() == key
    (tmp_path / "c.py").write_text("")
    assert ui_shots.data_key() != key


def test_surface_layer_added_once(tmp_path):
    """with_surface on a run.json that has its "Surface file" layer adds no second one."""
    path = tmp_path / "run.json"
    path.write_text(json.dumps({"params": {}, "data": [{"layer": "Elevation file", "file": "x.tif"}]}))
    ui_shots.with_surface(str(path))
    ui_shots.with_surface(str(path))
    layers = [d["layer"] for d in json.loads(path.read_text())["data"]]
    assert layers == ["Elevation file", "Surface file"]


class Search:
    """clip_run's search stubbed: each call writes a new minimal run folder (ids in the order of the calls)."""

    def __init__(self):
        self.calls = 0

    def __call__(self, command, **kwargs):
        self.calls += 1
        data = command[command.index("--data-dir") + 1]
        run = f"2026-01-{self.calls:02d}_000000_Zabi-Kon-clip_{self.calls:016x}"
        folder = os.path.join(data, "runs", run)
        os.makedirs(folder)
        with open(os.path.join(folder, "run.json"), "w", encoding="utf-8") as f:
            json.dump({"id": run, "params": {}, "data": [{"layer": "Elevation file", "file": "x.tif"}]}, f)
        with open(os.path.join(folder, "data.js"), "w", encoding="utf-8") as f:
            f.write('window.FINDALINE_DATA = {"lines": [[50.1, 19.7, 50.2, 19.8, []]]};\n')

        class Done:
            returncode, stdout, stderr = 0, "", ""
        return Done()


def test_a_kept_data_folder(tmp_path, monkeypatch):
    """prepare on a data folder used before: with the marker's key its clip run and cubes are kept (no second run,
    report or surface layer); --run shows another run (the share token moves to it) and keeps the marker's clip;
    --fresh, another key or a folder of the old tool (no marker) make a new clip run, and that one is shown."""
    import gc

    from jobs import Jobs
    for name, value in ui_shots.ACCOUNTS.items():
        monkeypatch.setenv(name, value)
    settings = ui_shots.account_settings()
    search, cubes = Search(), []
    monkeypatch.setattr(ui_shots.subprocess, "run", search)

    def sample_cubes(data):
        cubes.append(data)
        for country in ui_shots.CUBES:
            os.makedirs(os.path.join(data, "countries", country, "cube"), exist_ok=True)
            with open(os.path.join(data, "countries", country, "cube", "cube.json"), "w") as f:
                f.write("{}")
    monkeypatch.setattr(ui_shots, "sample_cubes", sample_cubes)
    data = str(tmp_path / "data")
    runs = os.path.join(data, "runs")
    digest = __import__("accounts").digest("ui-shots-share-" + "x" * 30)

    def prepare(**kwargs):
        times = {}
        _, run, share, jobs = ui_shots.prepare(data, settings, times=times, **kwargs)
        assert share == "ui-shots-share-" + "x" * 30
        return run, jobs, times

    def sessions():  # the sessions of each user of the tool
        import sqlite3
        with sqlite3.connect(os.path.join(data, "accounts.sqlite")) as db:
            counts = dict(db.execute("SELECT user_id, COUNT(*) FROM sessions GROUP BY user_id").fetchall())
        db.close()
        return counts

    def clips():  # the clip runs in runs/ (by their name) and in the jobs database
        return (sorted(r for r in os.listdir(runs) if "Zabi-Kon-clip" in r),
                sorted(r["run_id"] for r in Jobs(data, public=True).all_runs() if "Zabi-Kon-clip" in r["run_id"]))

    def report_runs():  # the run each of the tool's problem reports names
        return [r["context"]["run"] for r in Jobs(data, public=True).reports() if r["text"] == ui_shots.REPORT]

    base = {"accounts and jobs", "the marker"}
    built = base | {"the clip's search", "the cubes"}
    first, jobs, times = prepare()
    assert search.calls == 1 and len(cubes) == 1 and set(times) == built
    key = ui_shots.data_key()
    assert ui_shots.read_marker(data) == {"key": key, "run": first, "run_key": key, "stale": []}
    again, jobs, times = prepare()
    assert again == first and search.calls == 1 and len(cubes) == 1 and set(times) == base
    assert sorted(os.listdir(runs)) == [first] and report_runs() == [first]
    meta = json.loads(open(os.path.join(runs, first, "run.json"), encoding="utf-8").read())
    assert [d["layer"] for d in meta["data"]].count("Surface file") == 1
    assert jobs.shared_run(digest) == first
    assert set(sessions().values()) == {1} and len(sessions()) == 5  # admin, walker, the three riggers: one each

    other = _run_json(tmp_path / "saved" / "2026-01-01_000000_Other_0", {"end_zone": 5})
    shown, jobs, times = prepare(run_folder=other)  # the token moves (share_hash is UNIQUE), the clip stays
    assert shown == "2026-01-01_000000_Other_0" and jobs.shared_run(digest) == shown and search.calls == 1
    assert set(times) == base | {"the saved run's copy"}
    assert ui_shots.read_marker(data)["run"] == first and len(cubes) == 1 and clips() == ([first], [first])
    again, jobs, _ = prepare()
    assert again == first and jobs.shared_run(digest) == first and search.calls == 1

    fresh, jobs, times = prepare(fresh=True)  # the old clip run removed: its folder and its row; the report remade
    assert fresh != first and search.calls == 2 and len(cubes) == 2 and jobs.shared_run(digest) == fresh
    assert set(times) == built | {"the old clip runs' removal"}
    assert clips() == ([fresh], [fresh]) and os.path.isdir(os.path.join(runs, shown)) and report_runs() == [fresh]

    remove = Jobs.delete_run  # a removal that fails once (a file of the run held open): kept in the marker, retried
    failures = []

    def delete_run(self, run_id, runs_dir):
        if not failures:
            failures.append(run_id)
            raise PermissionError(32, "The process cannot access the file", "data.js")
        return remove(self, run_id, runs_dir)
    monkeypatch.setattr(Jobs, "delete_run", delete_run)
    held, jobs, _ = prepare(fresh=True)
    assert failures == [fresh] and clips() == (sorted([fresh, held]), sorted([fresh, held]))
    assert ui_shots.read_marker(data)["stale"] == [fresh] and report_runs() == [held]
    shown, jobs, times = prepare(run_folder=os.path.join(runs, fresh))  # a --run start, of that very run: nothing goes
    assert shown == fresh and clips() == (sorted([fresh, held]), sorted([fresh, held]))
    assert ui_shots.read_marker(data)["stale"] == [fresh] and "the old clip runs' removal" not in times
    again, jobs, times = prepare()  # the next start without --run removes it
    assert again == held and clips() == ([held], [held]) and ui_shots.read_marker(data)["stale"] == []
    assert set(times) == base | {"the old clip runs' removal"}

    with open(os.path.join(data, ui_shots.MARKER), "w", encoding="utf-8") as f:  # a marker of 4680e7a's format
        json.dump({"key": ui_shots.data_key(), "run": held}, f)
    again, jobs, times = prepare()
    assert again == held and search.calls == 3 and set(times) == base

    os.remove(os.path.join(data, ui_shots.MARKER))  # a folder of the old tool: its runs, no marker (none removed)
    old, jobs, _ = prepare()
    assert old != held and search.calls == 4 and ui_shots.read_marker(data)["run"] == old
    assert clips() == (sorted([held, old]), sorted([held, old]))
    monkeypatch.setattr(ui_shots, "data_key", lambda: "another")  # the code changed: the marker's clip removed
    new, jobs, _ = prepare()
    assert new not in (held, old) and search.calls == 5 and len(cubes) == 5
    assert clips() == (sorted([held, new]), sorted([held, new])) and report_runs() == [new]
    monkeypatch.setattr(ui_shots, "data_key", lambda: "third")  # changed again, a --run start: nothing removed
    _, jobs, times = prepare(run_folder=other)
    assert set(times) == base | {"the saved run's copy", "the cubes"}
    assert clips() == (sorted([held, new]), sorted([held, new])) and len(cubes) == 6 and search.calls == 5
    assert ui_shots.read_marker(data) == {"key": "third", "run": new, "run_key": "another", "stale": []}
    newest, jobs, _ = prepare()  # the clip made under another key: replaced; the cubes are this key's
    assert clips() == (sorted([held, newest]), sorted([held, newest])) and len(cubes) == 6 and search.calls == 6
    assert len(jobs.reports()) == 1 and report_runs() == [newest]
    assert set(sessions().values()) == {1}
    del jobs
    gc.collect()


def test_options(monkeypatch, capsys):
    """--out is required but with --list; --dark with --themes light or dark is an error; --list prints the pages
    and those the run leaves out, starts no browser and exits 0."""
    def run(*argv):
        monkeypatch.setattr(sys, "argv", ["ui_shots.py", *argv])
        return ui_shots.main()
    for argv in ([], ["--out", "x", "--dark", "--themes", "light"], ["--out", "x", "--devices", "tablet"]):
        try:
            run(*argv)
        except SystemExit as stop:
            assert stop.code == 2
        else:
            raise AssertionError(argv)
    capsys.readouterr()
    monkeypatch.setattr(ui_shots, "prepare", lambda data, settings, run, fresh, times: ({}, "R", "S", None))
    monkeypatch.setattr(ui_shots, "account_settings", lambda: None)
    monkeypatch.setattr(ui_shots, "run_features", lambda folder: {"lift"})
    assert run("--list", "--only", "c-result-rigging,c-result-why,c-result-more", "--exclude", "more") == 0
    assert capsys.readouterr().out.splitlines() == ["c-result-rigging",
                                                    f"c-result-why  left out: {ui_shots.LACKS['found']}"]


class FakeBrowser:
    def __init__(self, engine, page):
        self.engine, self.page, self.contexts, self.closed = engine, page, [], False

    def new_context(self, **options):
        _take("new_context")
        self.contexts.append(FakeContext(**self.page))
        self.contexts[-1].options = options
        return self.contexts[-1]

    def close(self):
        self.closed = True
        _take("browser.close")


class FakeEngine:
    def __init__(self, pw, name):
        self.pw, self.name = pw, name

    def launch(self):
        _take("launch")
        self.pw.browsers.append(FakeBrowser(self.name, self.pw.page))
        return self.pw.browsers[-1]


class FakePlaywright:
    """Playwright's object for the passes: its engines, the device profiles, the browsers launched (their pages
    made by FakeContext(**page))."""

    def __init__(self, **page):
        self.page, self.browsers = page, []
        self.chromium, self.webkit = FakeEngine(self, "chromium"), FakeEngine(self, "webkit")
        self.devices = {"iPhone 13": {"viewport": {"width": 390, "height": 664}, "default_browser_type": "webkit"},
                        "Pixel 7": {"viewport": {"width": 412, "height": 839}, "default_browser_type": "chromium"}}


@pytest.fixture
def clock(monkeypatch):
    """ui_shots' clock moved only by the fakes (TAKES)."""
    Clock.now = Clock()
    monkeypatch.setattr(ui_shots, "time", type("FakeTime", (), {"perf_counter": staticmethod(Clock.now.perf_counter)}))
    yield Clock.now
    Clock.now = None


def _all(pw, shown, tmp_path, devices=("desktop",), themes=("light",), strict=False, act=None, **extra):
    times, rows, passes = {}, [], []
    ui_shots.shoot_all(pw, SITE, list(shown), list(devices), list(themes), str(tmp_path), strict, times, rows, passes,
                       act, **extra)
    return times, rows, passes


def test_pass_context():
    """pass_context: the device's profile (DESKTOP for the desktop) without its browser type, the theme, HTTPS errors
    ignored, Chromium's motion sensors (none on WebKit), the theme's init script; `extra` goes on to new_context."""
    pw = FakePlaywright()
    browser = pw.chromium.launch()
    context = ui_shots.pass_context(browser, pw, "desktop", "dark", bypass_csp=True)
    assert context.options == {**ui_shots.DESKTOP, "color_scheme": "dark", "ignore_https_errors": True,
                               "permissions": ["accelerometer", "gyroscope", "magnetometer"], "bypass_csp": True}
    assert context.scripts == [ui_shots.CONTEXT_SCRIPT.format(theme='"dark"')]
    assert "localStorage.setItem('findaline-theme', \"dark\")" in context.scripts[0]
    context = ui_shots.pass_context(pw.webkit.launch(), pw, "iphone", "light")
    assert context.options == {"viewport": {"width": 390, "height": 664}, "color_scheme": "light",
                               "ignore_https_errors": True, "permissions": []}


def test_act_in_place_of_the_shot(tmp_path):
    """shoot_page with `act`: called once with the open page after the last step, in place of the screenshot; its
    dict in the row ("done", no path); an exception from it fails only its page; not called for a page left out,
    nor with --strict after a timeout; without `act` the picture's path is as before."""
    calls = []

    def act(page, name, device, theme):
        calls.append((page, name, device, theme))
        assert not page.closed
        if name == "c-result-grouping":
            assert page.calls[-1] == ("sleep", 600)  # after the last step's wait
        if name == "c-home":
            raise ValueError("no metrics here\nmore")
        return {"cls": 0.01}

    context = FakeContext(true={"leaflet-tile", "r-by"}, shown={".r-filters .u-chip.u-add"})
    row = ui_shots.shoot_page(context, SITE, "c-result-grouping", "pixel", "dark", None, ui_shots.Pass("pixel", "dark"),
                              act)
    assert row["outcome"] == "done" and row["result"] == {"cls": 0.01} and row["path"] is None
    assert row["shot"] is not None and calls == [(context.pages[0], "c-result-grouping", "pixel", "dark")]
    assert not [c for c in context.pages[0].calls if c[0] == "shot"] and context.pages[0].closed
    assert not ui_shots.failed([row])
    times, rows, passes = _all(FakePlaywright(true={"leaflet-tile"}), ["c-home", "c-result-more", "c-favourites"],
                               tmp_path, act=act)
    assert [r["outcome"] for r in rows] == ["failed", "left out", "done"] and rows[0]["error"] == "no metrics here"
    assert [c[1] for c in calls[1:]] == ["c-home", "c-favourites"]  # none for the page left out
    calls.clear()
    _all(FakePlaywright(true={"leaflet-tile"}), ["view3d", "c-home"], tmp_path, strict=True, act=act)
    assert calls == []  # the timed-out page has no act, and the run stopped
    times, rows, passes = _all(FakePlaywright(true={"leaflet-tile"}), ["c-favourites"], tmp_path)
    assert rows[0]["path"] == str(tmp_path / "c-favourites-desktop-light.png") and "result" not in rows[0]


def test_strict_stops_the_run_at_the_first_bad_row(tmp_path):
    """shoot_all with --strict stops after the first row with a timeout or a failure, whatever its outcome (a
    "need:" whose wait for the result timed out and whose page is then left out); without --strict every page of
    every pass is done (failed() True: main's exit code 1, test_timings_file)."""
    pages = ["c-result-shore-folded", "c-home", "c-favourites"]
    times, rows, passes = _all(FakePlaywright(true={"leaflet-tile"}), pages, tmp_path, ("desktop", "pixel"),
                               ("light", "dark"), strict=True)
    assert [(r["page"], r["outcome"], r["timeouts"]) for r in rows] == [
        ("c-result-shore-folded", "left out", [ui_shots.NEED_READY])]
    assert [(p["device"], p["theme"]) for p in passes] == [("desktop", "light")] and ui_shots.failed(rows)
    times, rows, passes = _all(FakePlaywright(true={"leaflet-tile"}), pages, tmp_path, ("desktop", "pixel"),
                               ("light", "dark"))
    assert len(rows) == 12 and len(passes) == 4 and ui_shots.failed(rows)
    times, rows, passes = _all(FakePlaywright(true={"leaflet-tile"}, stuck={".c-account-btn"}), ["c-menu", "c-home"],
                               tmp_path, strict=True)
    assert [r["outcome"] for r in rows] == ["failed"]
    times, rows, passes = _all(FakePlaywright(true={"leaflet-tile"}), ["c-home", "c-favourites"], tmp_path, strict=True)
    assert [r["outcome"] for r in rows] == ["saved", "saved"] and not ui_shots.failed(rows)


def test_timings_add_up(tmp_path, clock):
    """The set-up's parts (launches, contexts, closings) and the passes' seconds make up shoot_all's time once:
    nothing counted twice, nothing left out; a pass's seconds hold its pages'."""
    start = clock.t
    times, rows, passes = _all(FakePlaywright(true={"leaflet-tile"}), ["c-home", "c-favourites"], tmp_path,
                               ("desktop", "iphone"), ("light", "dark"))
    total = clock.t - start
    assert abs(sum(times.values()) + sum(p["seconds"] for p in passes) - total) < 1e-9
    assert times["context desktop light"] == pytest.approx(TAKES["new_context"] + TAKES["init"])
    assert times["close desktop light"] == pytest.approx(TAKES["context.close"])
    assert times["launch webkit (iphone)"] == pytest.approx(TAKES["launch"])
    assert times["close webkit (iphone)"] == pytest.approx(TAKES["browser.close"])
    for p in passes:
        assert p["seconds"] == pytest.approx(sum(r["seconds"] for r in rows
                                                 if (r["device"], r["theme"]) == (p["device"], p["theme"])))


def test_an_interrupt_keeps_what_was_done(tmp_path):
    """Ctrl+C on a page: the rows made before it stay, and the unfinished pass has its record."""
    rows, passes = [], []
    pw = FakePlaywright(true={"leaflet-tile"}, interrupt=("#account",))
    with pytest.raises(KeyboardInterrupt):
        ui_shots.shoot_all(pw, SITE, ["c-home", "c-favourites", "c-account"], ["desktop"], ["light"], str(tmp_path),
                           False, {}, rows, passes)
    assert [r["page"] for r in rows] == ["c-home", "c-favourites"]
    assert passes == [{"device": "desktop", "theme": "light", "seconds": passes[0]["seconds"], "saved": 2,
                       "left_out": 0, "complete": False}]
    assert pw.browsers[0].closed and pw.browsers[0].contexts[0].closed


def test_an_interrupt_outlives_a_close_that_fails(tmp_path, monkeypatch, capsys):
    """Ctrl+C while the closes raise (Playwright's driver stopped by the same Ctrl+C): the KeyboardInterrupt reaches
    the caller, the closes' errors are notes, the rows and the pass record are kept; without an error on its way a
    close's error is raised as before."""
    def gone(self):
        raise RuntimeError("Target page, context or browser has been closed\nCall log:")
    monkeypatch.setattr(FakeContext, "close", gone)
    monkeypatch.setattr(FakeBrowser, "close", gone)
    rows, passes, times = [], [], {}
    with pytest.raises(KeyboardInterrupt):
        ui_shots.shoot_all(FakePlaywright(true={"leaflet-tile"}, interrupt=("#favourites",)), SITE,
                           ["c-home", "c-favourites"], ["desktop"], ["light"], str(tmp_path), False, times, rows,
                           passes)
    assert [r["page"] for r in rows] == ["c-home"] and passes[0]["complete"] is False
    assert {"close desktop light", "close chromium (desktop)"} <= set(times)
    out = capsys.readouterr().out
    assert "close desktop light: Target page, context or browser has been closed" in out
    with pytest.raises(RuntimeError):
        ui_shots.shoot_all(FakePlaywright(true={"leaflet-tile"}), SITE, ["c-home"], ["desktop"], ["light"],
                           str(tmp_path), False, {}, [], [])


def _main(monkeypatch, tmp_path, pw, *argv):
    """main() with the site and Playwright faked."""
    import types
    from contextlib import nullcontext
    monkeypatch.setattr(ui_shots, "serve", lambda data, run, fresh, times: (SITE["url"], SITE["cookies"], "R", "S",
                                                                             lambda: None))
    monkeypatch.setattr(ui_shots, "first_line", lambda data, run, k=0: "1,2,3,4")
    monkeypatch.setattr(ui_shots, "border_view", lambda data: "#layer")
    monkeypatch.setattr(ui_shots, "run_features", lambda folder: set())
    monkeypatch.setitem(sys.modules, "playwright.sync_api", types.SimpleNamespace(sync_playwright=lambda: nullcontext(pw)))
    monkeypatch.setattr(sys, "argv", ["ui_shots.py", "--data-dir", str(tmp_path / "data"), "--out", str(tmp_path / "out"),
                                      "--timings", str(tmp_path / "t.json"), *argv])
    return ui_shots.main()


def test_timings_file(tmp_path, monkeypatch, capsys, clock):
    """main: the exit code (1 after a timeout) and the --timings file, after a whole run and after an interrupted
    one (what was done, the pass unfinished, "interrupted", also for an error that is not an interrupt); the set-up's
    and closing's parts and the passes make up the total (on the fake clock: exactly)."""
    code = _main(monkeypatch, tmp_path, FakePlaywright(true={"leaflet-tile"}), "--only", "c-home,c-result-rigging",
                 "--exclude", "limited", "--devices", "desktop")
    saved = json.loads((tmp_path / "t.json").read_text(encoding="utf-8"))
    assert code == 0 and saved["exit"] == 0 and not saved["interrupted"]
    assert [r["page"] for r in saved["pages"]] == ["c-home"] and saved["passes"][0]["complete"]
    assert saved["left_out_by_run"] == {"c-result-rigging": ui_shots.LACKS["lift"]}
    assert set(saved["setup"]) == {"the run's lines and border cell", "the run's features", "Playwright's start",
                                   "launch chromium (desktop)", "context desktop light", "close desktop light",
                                   "close chromium (desktop)", "Playwright's stop", "the server's stop"}
    assert saved["total"] > 0
    assert saved["total"] == pytest.approx(sum(saved["setup"].values()) + sum(p["seconds"] for p in saved["passes"]),
                                           abs=1e-9)
    out = capsys.readouterr().out
    assert "Summary:" in out and "Closing: close desktop light 0.2 s, close chromium (desktop) 0.1 s, " \
                                 "Playwright's stop 0.0 s, the server's stop 0.0 s" in out
    assert _main(monkeypatch, tmp_path, FakePlaywright(), "--only", "view3d-full", "--devices", "desktop") == 1
    assert json.loads((tmp_path / "t.json").read_text(encoding="utf-8"))["exit"] == 1
    with pytest.raises(KeyboardInterrupt):
        _main(monkeypatch, tmp_path, FakePlaywright(true={"leaflet-tile"}, interrupt=("#favourites",)),
              "--only", "c-home,c-favourites", "--exclude", "limited", "--devices", "desktop")
    saved = json.loads((tmp_path / "t.json").read_text(encoding="utf-8"))
    assert saved["interrupted"] and [r["page"] for r in saved["pages"]] == ["c-home"]
    assert saved["passes"][0]["complete"] is False
    assert "Summary:" in capsys.readouterr().out

    def broken(self):
        raise RuntimeError("the driver is gone")
    monkeypatch.setattr(FakeEngine, "launch", broken)  # an error that is not an interrupt ends the run
    with pytest.raises(RuntimeError):
        _main(monkeypatch, tmp_path, FakePlaywright(), "--only", "c-home", "--devices", "desktop")
    saved = json.loads((tmp_path / "t.json").read_text(encoding="utf-8"))
    assert saved["interrupted"] and saved["pages"] == [] and saved["exit"] == 0


TOO_TALL = "Page.screenshot: Cannot take screenshot larger than 32767 pixels on any dimension\nCall log:"


def test_a_page_too_tall_is_taken_at_css_pixels(tmp_path):
    """A whole page too tall for its picture at the device's pixel ratio (WebKit's 32767 px) is taken again at one
    pixel per CSS pixel: saved, "scale": "css", a note in the summary; too tall even then, or another error, or a
    viewport's shot: a failure, not retried."""
    context = FakeContext(true={"leaflet-tile"}, shot_errors=[TOO_TALL])
    row = _shoot(context, "page-coverage-full", tmp_path, device="iphone")
    shots = [c for c in context.pages[0].calls if c[0] == "shot"]
    path = str(tmp_path / "page-coverage-full-iphone-light.png")
    assert shots == [("shot", path, True), ("shot", path, True, "css")]
    assert row["outcome"] == "saved" and row["scale"] == "css" and row["path"] == path and not ui_shots.failed([row])
    assert any(line.startswith("Taken at one pixel per CSS pixel") and "page-coverage-full (iphone light)" in line
               for line in ui_shots.summary({}, [], [row], {}, 1.0))
    row = _shoot(FakeContext(true={"leaflet-tile"}, shot_errors=[TOO_TALL, TOO_TALL]), "page-coverage-full", tmp_path)
    assert row["outcome"] == "failed" and row["error"].startswith("Page.screenshot: Cannot take")
    context = FakeContext(true={"leaflet-tile"}, shot_errors=["Page.screenshot: Target closed"])
    row = _shoot(context, "page-coverage-full", tmp_path)
    assert row["outcome"] == "failed" and len([c for c in context.pages[0].calls if c[0] == "shot"]) == 1
    context = FakeContext(true={"leaflet-tile"}, shot_errors=[TOO_TALL])  # a viewport's shot: not retried
    row = _shoot(context, "page-coverage", tmp_path)
    assert row["outcome"] == "failed" and "scale" not in row
    row = _shoot(FakeContext(true={"leaflet-tile"}), "page-coverage-full", tmp_path)
    assert row["outcome"] == "saved" and "scale" not in row


def test_themes():
    """--dark and --themes to the themes of the passes: light by default; --dark both; a conflict None."""
    assert ui_shots.themes_of(False, None) == ["light"]
    assert ui_shots.themes_of(True, None) == ui_shots.themes_of(False, "both") == ["light", "dark"]
    assert ui_shots.themes_of(True, "both") == ["light", "dark"]
    assert ui_shots.themes_of(False, "dark") == ["dark"] and ui_shots.themes_of(False, "light") == ["light"]
    assert ui_shots.themes_of(True, "dark") is None and ui_shots.themes_of(True, "light") is None


def test_page_storage():
    """page_storage: a page with a kept layout sets it (as JSON in a string), the other kind removed; a page without
    either removes both."""
    script = ui_shots.page_storage("c-result-rails")
    assert f"localStorage.setItem('findaline.layout', {json.dumps(json.dumps(ui_shots.LAYOUTS['c-result-rails']))})" \
        in script and "localStorage.removeItem('findaline.layer.layout')" in script
    script = ui_shots.page_storage("c-layer-collapsed")
    assert "localStorage.removeItem('findaline.layout')" in script and \
        json.dumps(json.dumps(ui_shots.LAYER_LAYOUTS["c-layer-collapsed"])) in script
    assert ui_shots.page_storage("c-home") == ("try { localStorage.removeItem('findaline.view'); "
                                               "localStorage.removeItem('findaline.layout'); "
                                               "localStorage.removeItem('findaline.layer.layout'); } catch (e) {}")
    # the result view's flag: set for its pages, removed for every other page of the pass
    assert ui_shots.page_storage("c-view").startswith("try { localStorage.setItem('findaline.view', \"b\"); ")
    assert "localStorage.removeItem('findaline.view')" in ui_shots.page_storage("c-result-rails")


def test_credits_go_into_data_js_and_the_store(tmp_path):
    """with_credits: a run's credits in its data.js, run.json and its store's head (the page reads the store when
    run.json lists it), run.json's block "store" matching the rewritten lines.arrow; the store's lines as before."""
    from test_linestore import _hard_lines, _profiles
    from test_viewer import _store_and_script, _store_head
    lines = _hard_lines(200, False, False, np.random.default_rng(1))
    lines.profiles = _profiles(200, np.random.default_rng(2))
    folder = tmp_path / "run"
    block = _store_and_script(folder, lines, _store_head(lines, False, False))
    (folder / "run.json").write_text(json.dumps({"id": "r", "store": block}), encoding="utf-8")
    before, _ = linestore.read(str(folder))

    ui_shots.with_credits(str(folder / "data.js"))
    data = json.loads((folder / "data.js").read_text(encoding="utf-8").partition(" = ")[2].rstrip().rstrip(";"))
    meta = json.loads((folder / "run.json").read_text(encoding="utf-8"))
    after, head = linestore.read(str(folder))
    assert data["attribution"] and head["attribution"] == data["attribution"] == meta["attribution"]
    store = meta["store"]
    assert store["lines"] == 200 and store["format"] == linestore.FORMAT
    assert store["bytes"] == sum((folder / name).stat().st_size for name in linestore.FILES)
    assert store["sha256"] == hashlib.sha256((folder / linestore.LINES_FILE).read_bytes()).hexdigest()[:16]
    for name, values in before.columns.items():
        assert np.array_equal(values, after.columns[name], equal_nan=values.dtype.kind == "f"), name

    plain = tmp_path / "plain"  # a run without a store: data.js and run.json only
    plain.mkdir()
    (plain / "data.js").write_text((folder / "data.js").read_text(encoding="utf-8"), encoding="utf-8")
    (plain / "run.json").write_text(json.dumps({"id": "p"}), encoding="utf-8")
    ui_shots.with_credits(str(plain / "data.js"))
    assert "store" not in json.loads((plain / "run.json").read_text(encoding="utf-8"))
