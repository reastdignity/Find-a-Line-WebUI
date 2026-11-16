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

    def screenshot(self, path, full_page=False):
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


def test_a_page_from_its_load_to_its_shot(tmp_path):
    """shoot_page: the page's address, its user's cookie, its steps in order, its picture; a click that finds
    nothing leaves the page out (None, no picture)."""
    context = FakeContext(shown={".r-filters .u-chip.u-add"}, true={"leaflet-tile", "r-by"})
    path = ui_shots.shoot_page(context, SITE, "c-result-grouping", "desktop", "light", str(tmp_path))
    page = context.pages[0]
    assert path == str(tmp_path / "c-result-grouping-desktop-light.png") and os.path.isfile(path) and page.closed
    assert ("goto", "https://localhost:1/?ui=c#run=R") in page.calls
    assert ("click", ".r-filters .u-chip.u-add") in page.calls
    assert context.cookies[0]["value"] == "a"
    context = FakeContext(true={"leaflet-tile"})  # no chip on this device
    assert ui_shots.shoot_page(context, SITE, "c-result-more", "iphone", "dark", str(tmp_path)) is None
    assert context.pages[0].closed and not os.path.exists(tmp_path / "c-result-more-iphone-dark.png")
    context = FakeContext(true={"leaflet-tile"})  # a visitor: no cookie; a map's own page
    ui_shots.shoot_page(context, SITE, "page-signin", "desktop", "light", str(tmp_path))
    assert context.cookies == []
    ui_shots.shoot_page(context, SITE, "map-shared", "desktop", "light", str(tmp_path))
    assert ("goto", "https://localhost:1/s/S/map.html") in context.pages[-1].calls


def test_pages_selected_by_their_names():
    """--only: the pages whose name contains one of its parts, all for none."""
    assert list(ui_shots.select_pages()) == list(ui_shots.PAGES)
    assert set(ui_shots.select_pages("c-line,map-shared")) == {"c-line", "c-line-profile", "map-shared",
                                                                 "map-shared-credits"}


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
