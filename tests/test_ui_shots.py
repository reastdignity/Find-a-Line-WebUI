"""tools/ui_shots.py: its data edits (the browser passes run by hand, .claude/rules/viewer.md "Verifying changes")."""

import hashlib
import json
import os
import sys

import numpy as np

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


class FakePage:
    """A Playwright page for the step runner: `true` the expressions that hold (waits for the others time out),
    `shown` the selectors a click finds, `stuck` those whose click fails, `throws` the scripts that raise."""

    def __init__(self, true=(), shown=(), stuck=(), throws=()):
        self.true, self.shown, self.stuck, self.throws = set(true), set(shown) | set(stuck), set(stuck), set(throws)
        self.calls, self.closed, self.default_timeout = [], False, None

    def set_default_timeout(self, ms):
        self.default_timeout = ms

    def set_default_navigation_timeout(self, ms):
        self.navigation_timeout = ms

    def add_init_script(self, script):
        self.calls.append(("init", script))

    def goto(self, url):
        self.calls.append(("goto", url))

    def wait_for_timeout(self, ms):
        self.calls.append(("sleep", ms))

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

    def screenshot(self, path, full_page=False, timeout=None):
        self.calls.append(("shot", path, full_page))
        with open(path, "wb") as f:
            f.write(b"png")

    def close(self):
        self.closed = True


class FakeContext:
    def __init__(self, **page):
        self.page, self.pages, self.cookies = page, [], []

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
    context = FakeContext(true={"leaflet-tile", ui_shots.NEED_READY, "u-shore-ctl"})
    assert _shoot(context, "c-result-shore-folded", tmp_path)["outcome"] == "saved"
    assert not hasattr(ui_shots, "NEED_WAIT_MS")


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

    first, jobs, times = prepare()
    assert search.calls == 1 and len(cubes) == 1 and set(times) == {"accounts and jobs", "the clip's search",
                                                                     "the cubes"}
    assert ui_shots.read_marker(data) == {"key": ui_shots.data_key(), "run": first}
    again, jobs, times = prepare()
    assert again == first and search.calls == 1 and len(cubes) == 1 and set(times) == {"accounts and jobs"}
    assert sorted(os.listdir(runs)) == [first] and len(jobs.reports()) == 1
    meta = json.loads(open(os.path.join(runs, first, "run.json"), encoding="utf-8").read())
    assert [d["layer"] for d in meta["data"]].count("Surface file") == 1
    assert jobs.shared_run(digest) == first

    other = _run_json(tmp_path / "saved" / "2026-01-01_000000_Other_0", {"end_zone": 5})
    shown, jobs, _ = prepare(run_folder=other)  # the token moves (share_hash is UNIQUE), the clip stays the marker's
    assert shown == "2026-01-01_000000_Other_0" and jobs.shared_run(digest) == shown and search.calls == 1
    assert ui_shots.read_marker(data)["run"] == first and len(cubes) == 1
    again, jobs, _ = prepare()
    assert again == first and jobs.shared_run(digest) == first and search.calls == 1

    fresh, jobs, _ = prepare(fresh=True)
    assert fresh != first and search.calls == 2 and len(cubes) == 2 and jobs.shared_run(digest) == fresh
    os.remove(os.path.join(data, ui_shots.MARKER))  # a folder of the old tool: its runs, no marker
    old, jobs, _ = prepare()
    assert old not in (first, fresh) and search.calls == 3 and ui_shots.read_marker(data)["run"] == old
    monkeypatch.setattr(ui_shots, "data_key", lambda: "another")  # the code changed
    new, jobs, _ = prepare()
    assert new not in (first, fresh, old) and search.calls == 4 and len(cubes) == 4
    assert len(jobs.reports()) == 1 and len(Jobs(data, public=True).reports()) == 1
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
