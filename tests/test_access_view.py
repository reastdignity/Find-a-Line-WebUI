"""The access mark in the result view (?view=b; docs/line-volume/spec-search.md 3.9, "Later, with the result view"),
ported from tests/test_access_page.py (today's page), and step 3c's leftovers of the view's list that go with it
(docs/roadmap.md, "Step 3c of the result view: the design review's list": items 6 and 9), in Playwright's Edge over
the app's server, offline, under the app's CSP. A run of the clip for the view with the mark (clip_runs.view_clip),
the same search without it, and that run with the head's `access_skipped`. What the view draws of the mark: the
list's column "Anchors" and its head, the details' rows A1 and A2 with the key, the column "Far end" of "Lines from
here", the marks at A1 and A2 on the map (the corners' marks and the canvas's rings), the legend's three marks and a
phone's legend of two lines with its fold, the pick "From a top edge"; a run without the mark draws none of it, and one
whose mark was left out says so in today's muted line. Then "Over trees or buildings" in words in the fan and the
table of spots (R4.2), and the kit's info icon in the uncertain shore's and the coarser terrain's boxes, on both pages
(R9). Every wait is an event with a deadline (one exception: test_shell_c_view_map._tap). Run from PowerShell
(.claude/rules/browser-tests.md)."""

import json
import os
import re
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_shell_c import BIG, copy_clip, stub_page  # noqa: E402
from test_shell_c_view_list import PIXEL  # noqa: E402
from test_shell_c_view_map import (DESKTOP, PHONE, SMALL_PHONE, WAIT, WORDS, _crowded, _open, _state, _tap,  # noqa: E402, F401
                                   _tap_on, view_clip)
from test_web import EDGE, _playwright, _server, store_with  # noqa: E402

# the browser tests (every test but the plain ones, which CI runs without the ui group)
BROWSER = pytest.mark.skipif(not os.path.exists(EDGE) or not _playwright(),
                             reason="needs Microsoft Edge and Playwright (group ui)")
PLAIN = "2026-10-28_100000_Plain_00000000000000c2"      # the same search without --access
SKIPPED = "2026-10-29_100000_Skipped_00000000000000d2"  # PLAIN with the head's access_skipped
BOXES = "2026-10-30_100000_Boxes_00000000000000e2"      # BIG with an uncertain shore and coarser terrain in its head
STATES = {0: "hard access", 1: "cannot tell", 2: "easy access"}
OVER = WORDS["ui.view.over_words"]
# everything of the mark a page can draw (the view's and today's classes)
MARK_ANY = ("svg.ac, .ac-none, .ac-hint, .ac-info, .ac-help, .vl-cell-acc, .vl-acc, .v-anchor-mark, .ac-map-icon, "
            "[data-kind^='access-'], .v-help-button, .r-legend-acc, .r-acc, .r-cell-acc")


@pytest.fixture(scope="module")
def plain_clip(tmp_path_factory):
    """The view clip's search without the access mark (clip_runs.VIEW_CLIP_ARGS without --access), once per session."""
    import clip_runs
    folder = clip_runs.data_copy(tmp_path_factory, "access-view-off", [a for a in clip_runs.VIEW_CLIP_ARGS if a != "--access"])
    runs = folder / "runs"
    return next(runs / d for d in os.listdir(runs) if (runs / d / "run.json").is_file())


def _with_boxes(folder):
    """The run's head given an uncertain shore (a segment of each kind) and coarser terrain (30 % of the land, one
    region) over its lines' box, so both boxes stand on the map of either page (as a coastal run's would)."""
    import pyarrow as pa
    import linestore
    with pa.OSFile(str(folder / linestore.LINES_FILE), "rb") as f:
        table = pa.ipc.open_file(f).read_all()
    lat, lon = (
        [v / 10 ** int(table.schema.field(name).metadata[b"decimals"]) for v in table.column(name).to_pylist()]
        for name in ("lat1", "lon1"))
    s, n, w, e = min(lat), max(lat), min(lon), max(lon)
    mid_lat, mid_lon = (s + n) / 2, (w + e) / 2

    def ring(a, b, c, d):
        return [[a, b], [c, b], [c, d], [a, d], [a, b]]
    shore = {"rim_min": 5, "totals": {"surface_m": 420, "sea_m": 260, "surface_px": 60, "sea_px": 40},
             "segments": [{"kind": "surface", "px": 60, "m": 420, "ring": ring(w, s, mid_lon, mid_lat)},
                          {"kind": "sea", "px": 40, "m": 260, "ring": ring(mid_lon, mid_lat, e, n)}]}
    sources = {"land_km2": 0.3, "fallback_share": 0.3, "totals": {"fallback_km2": 0.09, "listed_km2": 0.09},
               "layers": [{"role": "source", "name": "Own", "resolution": 1.0, "share": 0.7},
                          {"role": "fallback", "name": "Coarse", "resolution": 10.0, "share": 0.3}],
               "regions": [{"layer": 1, "km2": 0.09, "rings": [ring(w, s, e, mid_lat)]}]}
    store_with(folder, head={"shore": shore, "terrain_sources": sources})


@pytest.fixture
def site(tmp_path, view_clip, plain_clip):
    """A data folder with the marked run (BIG), the run without the mark (PLAIN), the run whose mark was left out
    (SKIPPED) and the marked run with the two boxes (BOXES), served by the app; yields the address of the app's page."""
    folder = tmp_path / "data"
    copy_clip(view_clip, folder, BIG, "Clip")
    copy_clip(plain_clip, folder, PLAIN, "Clip without the mark")
    copy_clip(plain_clip, folder, SKIPPED, "Clip whose mark was left out")
    store_with(folder / "runs" / SKIPPED, head={"access_skipped": "memory"})
    copy_clip(view_clip, folder, BOXES, "Clip with the boxes")
    _with_boxes(folder / "runs" / BOXES)
    page_path = stub_page(folder, "accessview")
    with _server(folder) as port:
        yield f"http://127.0.0.1:{port}/{page_path}?ui=c"


# The page's helpers of these checks (window.A), beside test_shell_c_view_map's T
HELP = r"""
window.A = {
  view() { return window.FINDALINE_VIEW.view; },
  frames() { return new Promise((ok) => requestAnimationFrame(() => requestAnimationFrame(() => setTimeout(ok, 0)))); },
  // the rows of a list as drawn: each one's line, its cell of the mark (the dots' class, name, width and parts; the
  // "–"s), whether the cell's content stays inside the cell
  rows(sel) { const c = this.view().model.data.columns;
    return [...document.querySelectorAll(sel + " .vl-main")].map((b) => { const row = +b.dataset.row, cell = b.querySelector(".vl-cell-acc");
      const box = cell && cell.getBoundingClientRect();
      return {row, line: [c.access1.at(row), c.access2.at(row)],
              dots: cell ? [...cell.querySelectorAll("svg.ac")].map((d) => [d.getAttribute("class"), d.getAttribute("aria-label"),
                                                                           Math.round(d.getBoundingClientRect().width), d.children.length]) : null,
              none: cell ? cell.querySelectorAll(".ac-none").length : null,
              inside: cell ? [...cell.querySelectorAll("svg.ac")].every((d) => { const r = d.getBoundingClientRect();
                return r.left >= box.left - 1 && r.right <= box.right + 1; }) : null}; }); },
  // the heads of a list's columns: the words, and whether it is the mark's column
  heads(sel) { const cols = document.querySelector(sel + " .vl-cols");
    return cols ? [...cols.children].map((s) => [s.textContent, s.classList.contains("vl-cell-acc")]).filter((h) => h[0]) : null; },
  // the words of a line over trees or buildings in a list's rows, as drawn (the row's line, its class, the words'
  // element: shown, its text and size, under the row's values, after the row's mark and swatch, inside the row)
  over(sel) { const c = this.view().model.data.columns;
    return [...document.querySelectorAll(sel + " .vl-row")].map((li) => { const b = li.querySelector(".vl-main"), row = +b.dataset.row;
      const w = b.querySelector(".vl-over-words"), r = w && w.getBoundingClientRect(), box = b.getBoundingClientRect();
      const values = [...b.querySelectorAll(":scope > .vl-v")].map((v) => v.getBoundingClientRect());
      const marks = [...b.querySelectorAll(":scope > .v-sh, :scope > .vl-num, :scope > .vl-sw")].map((v) => v.getBoundingClientRect());
      const style = w && getComputedStyle(w);
      return {row, over: c.over[row] === 1, cls: li.classList.contains("vl-over"), words: w ? w.textContent : null,
              times: b.textContent.split(%(over)s).length - 1, hidden: w ? w.classList.contains("u-sr") : null,
              shown: !!r && r.width > 0 && r.height > 0, under: !!r && values.length > 0 && values.every((v) => r.top >= v.bottom - 1),
              after: !!r && marks.every((m) => r.left >= m.right - 1), inside: !!r && r.left >= box.left - 1 && r.right <= box.right + 1 && r.bottom <= box.bottom + 1,
              oneLine: !!r && r.height <= parseFloat(style.lineHeight) + 1, whole: !w || w.scrollWidth <= w.clientWidth + 1,
              px: style ? parseFloat(style.fontSize) : null, colour: style ? style.color : null}; }); },
  // the page does not scroll sideways
  sideways() { return document.documentElement.scrollWidth > innerWidth + 1; },
  // a colour (a token's value) as [r, g, b]
  rgb(value) { const ctx = document.createElement("canvas").getContext("2d"); ctx.fillStyle = "#000"; ctx.fillStyle = value;
    const hex = ctx.fillStyle; return [1, 3, 5].map((k) => parseInt(hex.slice(k, k + 2), 16)); },
  // the canvas's pixels on the circle of an anchor's number (A1, A2: radius 10.5 px, its ring 2.4 px wide): how many
  // of 24 points around it are the token's colour (each channel within 40)
  ring(label, token) { return this.ringOf(label, getComputedStyle(window.FINDALINE_MAP.getContainer()).getPropertyValue(token).trim()); },
  // the same for a colour given as it is (the canvas's own ink of a ring with no state)
  ringOf(label, colour) { const {map} = window.FINDALINE_VIEW, n = map.drawn().numbers.find((x) => x.label === label);
    if (!n) return null;
    const canvas = map.renderer._container, ctx = canvas.getContext("2d"), cb = canvas.getBoundingClientRect();
    const sx = canvas.width / cb.width, sy = canvas.height / cb.height;
    const want = this.rgb(colour);
    const cx = (n.box.left + n.box.right) / 2, cy = (n.box.top + n.box.bottom) / 2;
    let hits = 0;
    for (let k = 0; k < 24; k++) { const a = k * Math.PI / 12, x = (cx + 10.5 * Math.cos(a) - cb.left) * sx, y = (cy + 10.5 * Math.sin(a) - cb.top) * sy;
      const p = ctx.getImageData(Math.round(x), Math.round(y), 1, 1).data;
      if (Math.abs(p[0] - want[0]) <= 40 && Math.abs(p[1] - want[1]) <= 40 && Math.abs(p[2] - want[2]) <= 40) hits++; }
    return hits; },
  // the corners' marks of the selected line (markers' icons): the dot's class and name, size, pointer events, place
  corners() { return [...document.querySelectorAll(".leaflet-marker-pane .v-anchor-mark")].map((icon) => { const svg = icon.querySelector("svg"), r = svg.getBoundingClientRect();
    return {cls: svg.getAttribute("class"), label: svg.getAttribute("aria-label"), size: [Math.round(r.width), Math.round(r.height)],
            events: [getComputedStyle(icon).pointerEvents, getComputedStyle(svg).pointerEvents], left: r.left, top: r.top}; }); },
  // T.anchors (test_shell_c_view_map.py) but for a spot other than `skip`: a spot in view selected whose shown line
  // has both anchors on the part of the map a person sees, r px clear of every control; the anchors' points
  anchors(r, skip) { const {view} = T.v(), box = T.box(), f = T.free(), controls = T.controls();
    const free = (x, y) => x > f[0] + r && y > f[1] + r && x < f[2] - r && y < f[3] - r &&
      !controls.some((c) => x + box.left > c.left - r && x + box.left < c.right + r && y + box.top > c.top - r && y + box.top < c.bottom + r);
    for (const spot of Array.from(view.inView.spots)) { if (spot === skip) continue; const row = view.shownOf(spot), e = T.ends(row);
      if (Math.hypot(e[2] - e[0], e[3] - e[1]) < 3 * r || !free(e[0], e[1]) || !free(e[2], e[3])) continue;
      view.select(spot);
      return {spot, row, ends: [{x: e[0] + box.left, y: e[1] + box.top}, {x: e[2] + box.left, y: e[3] + box.top}]}; }
    return null; },
  // the highest line on average of those that pass whose two anchors read easy access (spots.ts pick's "edge")
  edge() { const v = this.view(), c = v.model.data.columns, h = v.values.hmean; let e = -1;
    for (let r = 0; r < v.count; r++) if (v.passes(r) && c.access1.at(r) === 2 && c.access2.at(r) === 2 && h[r] === h[r] && (e < 0 || h[r] > h[e])) e = r;
    return e; },
  // the lines of the view drawn again after a change of the page's columns (as tools/ui_shots.py's VIEW_TREES)
  redraw() { const v = this.view(); v.setTopOnly(!v.topOnly); v.setTopOnly(!v.topOnly); window.FINDALINE_VIEW.map.refresh(); },
};
""" % {"over": json.dumps(OVER)}


def _view(browser, site: str, run: str, context: dict):
    page = _open(browser, f"{site}#run={run}", context, script=HELP)
    page.wait_for_selector(".vl-tree .vl-main", state="attached", timeout=WAIT)
    page.evaluate("() => A.frames()")
    return page


def _sheet(page, stop: str):
    """A phone's sheet raised to `stop` (half, full) by its handle's arrow key, awaited."""
    for _ in range({"half": 1, "full": 2}[stop]):
        if page.evaluate(f"() => document.querySelector('.u-sheet').classList.contains('u-{stop}')"):
            break
        page.focus(".u-sheet-handle")
        page.keyboard.press("ArrowUp")
        page.wait_for_function("() => !document.querySelector('.u-sheet').classList.contains('u-peek')", timeout=WAIT)
    page.wait_for_function(f"() => document.querySelector('.u-sheet').classList.contains('u-{stop}')", timeout=WAIT)


def _dots_hold(rows: list, where: str):
    """Every row of a marked run: two dots of 20 px with the row's line's states and their names, inside the cell."""
    assert len(rows) >= 8, (where, len(rows))
    for r in rows:
        a1, a2 = r["line"]
        assert a1 in STATES and a2 in STATES and r["none"] == 0 and r["inside"], (where, r)
        assert [d[:3] for d in r["dots"]] == [[f"ac ac-{a1}", f"Anchor 1: {STATES[a1]}", 20],
                                              [f"ac ac-{a2}", f"Anchor 2: {STATES[a2]}", 20]], (where, r)
        assert all(d[3] >= 3 for d in r["dots"]), (where, r)  # its title, the dot and the state's sign


@BROWSER
def test_list_column_and_its_heads(site):
    """A marked run: "Best in view" and the tree carry the column "Anchors" before "Lines" (a head, not a sort), in
    every row two dots of 20 px with the line's states (anchor 1, anchor 2: the columns' values) and their names,
    inside their cell; on a desktop and on a phone of 390 px, whose page does not scroll sideways."""
    from playwright.sync_api import sync_playwright
    r = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            for name, context in (("desktop", DESKTOP), ("phone", PHONE)):
                page = _view(browser, site, BIG, context)
                if name == "phone":
                    _sheet(page, "full")
                r[name] = page.evaluate("""() => ({top: A.rows('.vl-topblock'), tree: A.rows('.vl-tree').slice(0, 12),
                    heads: [A.heads('.vl-topblock'), A.heads('.vl-tree')], acc: A.view().model.hasAccess, sideways: A.sideways(),
                    classes: [...document.querySelectorAll('.vl-rows')].map((u) => u.classList.contains('vl-with-acc'))})""")
                r[name]["csp"] = page.evaluate("() => window.CSP_VIOLATIONS || []")
                r[name]["errors"] = page.errors
                page.close()
        finally:
            browser.close()
    for name, found in r.items():
        assert found["acc"] and found["classes"] and all(found["classes"]), (name, found["classes"])
        for heads in found["heads"]:
            words = [h[0] for h in heads]
            assert words[-2:] == [WORDS["ui.list.col.anchors"], WORDS["ui.list.col.lines"]] and heads[-2][1], (name, heads)
            assert words[0] == WORDS["ui.list.col.length"], (name, heads)
        _dots_hold(found["top"] + found["tree"], name)
        assert not found["sideways"] and found["csp"] == [] and found["errors"] == [], (name, found["csp"], found["errors"])
    states = {s for row in r["desktop"]["top"] + r["desktop"]["tree"] for s in row["line"]}
    assert len(states) >= 2, states  # the clip's run has all three


@BROWSER
def test_details_rows_a1_a2_and_the_key(site):
    """A selected spot of a marked run: the head ("Spot 1.1", its lines; the details' head on a desktop, the sheet's
    on a phone) carries the line's two dots (anchor 1, anchor 2) on the title's line, after the count; "Reaching the
    anchors" under the tiles and above "Lines from anchor A1 / A2", a row per anchor ("A1", the dot of the line's state
    with its name, the state's words); the key's "i" (the kit's info icon, no "?") opens the three states under the
    rows and closes again; on a desktop and in a phone's sheet (today's test_details_block_and_the_phone_heads_pair)."""
    from playwright.sync_api import sync_playwright
    details = """() => { const d = document.querySelector('.vl-details'), acc = d && d.querySelector('.vl-acc'), sel = A.view().selected;
      const dot = (e) => e ? [e.getAttribute('class'), e.getAttribute('aria-label'), Math.round(e.getBoundingClientRect().width)] : null;
      const tiles = d.querySelector('.vl-tiles'), acts = d.querySelector('.vl-acts'), info = acc && acc.querySelector('.vl-acc-h .ac-info');
      const heads = [...document.querySelectorAll('.vl-spot-title')], head = heads[0], pair = head && head.querySelector('.ac-pair');
      const middle = (e) => { const r = e.getBoundingClientRect(); return (r.top + r.bottom) / 2; };
      return {heads: heads.length, inSheet: !!(head && head.closest('.u-sheet')), head: pair ? [...pair.querySelectorAll('svg.ac')].map(dot) : [],
              // the pair inside the title's box, on the line of the spot's count, after it
              headLine: !!pair && (() => { const t = head.getBoundingClientRect(), b = pair.getBoundingClientRect(), n = head.querySelector('.vl-spot-count');
                return b.top >= t.top - 1 && b.bottom <= t.bottom + 1 && b.right <= t.right + 1 && Math.abs(middle(pair) - middle(n)) <= 6
                       && b.left >= n.getBoundingClientRect().right; })(),
              line: [sel.line.access1, sel.line.access2], title: acc && acc.querySelector('.vl-acc-h').firstChild.textContent,
              rows: acc ? [...acc.querySelectorAll('.vl-acc-row')].map((row) => [row.children[0].textContent, dot(row.querySelector('svg.ac')), row.children[2].textContent]) : [],
              placed: !!(acc && tiles && acts) && !!(tiles.compareDocumentPosition(acc) & 4) && !!(acc.compareDocumentPosition(acts) & 4),
              info: info && [info.getAttribute('aria-label'), info.getAttribute('aria-expanded'), info.textContent.trim(), !!info.querySelector('svg.u-ic')],
              key: [...d.querySelectorAll('.vl-acc .ac-help .ac-key-row b')].map((b) => b.textContent)}; }"""
    r = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            for name, context in (("desktop", DESKTOP), ("phone", PHONE)):
                page = _view(browser, site, BIG, context)
                if name == "phone":
                    _sheet(page, "half")
                page.evaluate("() => { const v = A.view(); v.select(v.inView.best[0] ?? v.order[0]); }")
                page.wait_for_selector(".vl-details .vl-acc", state="attached", timeout=WAIT)
                r[name] = page.evaluate(details)
                page.evaluate("() => document.querySelector('.vl-details .vl-acc-h .ac-info').click()")
                page.wait_for_selector(".vl-details .vl-acc .ac-help", state="attached", timeout=WAIT)
                r[name + "-key"] = page.evaluate(details)
                page.evaluate("() => document.querySelector('.vl-details .vl-acc-h .ac-info').click()")
                page.wait_for_selector(".vl-details .vl-acc .ac-help", state="detached", timeout=WAIT)
                assert page.errors == [], page.errors
                page.close()
        finally:
            browser.close()
    for name in ("desktop", "phone"):
        found = r[name]
        a1, a2 = found["line"]
        assert found["heads"] == 1 and found["inSheet"] == (name == "phone"), (name, found)
        assert found["head"] == [[f"ac ac-{a1}", f"Anchor 1: {STATES[a1]}", 20], [f"ac ac-{a2}", f"Anchor 2: {STATES[a2]}", 20]], (name, found)
        assert found["headLine"] is True, (name, found)
        assert found["title"] == WORDS["ui.access.title"] and found["placed"], (name, found)
        assert found["rows"] == [["A1", [f"ac ac-{a1}", f"Anchor 1: {STATES[a1]}", 20], STATES[a1]],
                                 ["A2", [f"ac ac-{a2}", f"Anchor 2: {STATES[a2]}", 20], STATES[a2]]], (name, found)
        assert found["info"] == [WORDS["ui.access.about"], "false", "", True] and found["key"] == [], (name, found)
        opened = r[name + "-key"]
        assert opened["info"][1] == "true" and opened["key"] == ["easy access:", "cannot tell:", "hard access:"], (name, opened)


@BROWSER
def test_fan_far_end(site):
    """"Lines from anchor A1" and "… A2" of a marked run: the heads end with "Far end" (the mark's column, no sort);
    each row carries the dot of its far anchor's state (the end of its line away from the point) with the name "Far
    end: {state}"."""
    from playwright.sync_api import sync_playwright
    fan = """() => { const v = A.view(), c = v.model.data.columns;
      return {heads: A.heads('.vl-fan'), model: v.fan.rows.map((r) => [r.row, r.near, r.near === 1 ? c.access2.at(r.row) : c.access1.at(r.row)]),
              rows: [...document.querySelectorAll('.vl-fan .vl-main')].map((b) => { const cell = b.querySelector('.vl-cell-acc'), d = cell && cell.querySelector('svg.ac');
                return [+b.dataset.row, d ? d.getAttribute('class') : null, d ? d.getAttribute('aria-label') : null, cell ? cell.querySelectorAll('.ac-none').length : null]; })}; }"""
    r = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _view(browser, site, BIG, DESKTOP)
            page.evaluate("() => { const v = A.view(); v.select(v.order[0]); }")
            for end in (1, 2):
                page.wait_for_selector(f".vl-from-{end}", timeout=WAIT)
                page.click(f".vl-from-{end}")
                page.wait_for_selector(".vl-fan .vl-main", timeout=WAIT)
                r[end] = page.evaluate(fan)
                page.click(".vl-fan-close")
                page.wait_for_selector(".vl-details", timeout=WAIT)
            assert page.errors == [], page.errors
        finally:
            browser.close()
    for end, found in r.items():
        assert [h[0] for h in found["heads"]][-1] == WORDS["ui.view.fan.far_end"] and found["heads"][-1][1], (end, found["heads"])
        assert len(found["rows"]) >= 2 and len(found["rows"]) == len(found["model"]), (end, found)
        for (row, cls, label, none), (want_row, near, far) in zip(found["rows"], found["model"]):
            # (a row's line may start at either of its anchors near the point: `near`, its far anchor the other one)
            assert row == want_row and near in (1, 2) and far in STATES, (end, row, near, far)
            assert (cls, label, none) == (f"ac ac-{far}", WORDS["ui.view.fan.far_end_state"].replace("{{state}}", STATES[far]), 0), (end, row)


@BROWSER
def test_marks_at_a1_and_a2_on_the_map(site):
    """The selected line of a marked run on the map: A1 and A2 carry its anchors' states, as the circle's ring in the
    state's map colour (the canvas's pixels: `--acc-map-*`) and the mark on the circle's corner (a marker's icon of
    18 px: mapbar.css, the state's class and name, anchor 1 then anchor 2, taking no pointer events); another selection makes them
    again (never more than two); "Lines from here" and the selection's end take them away."""
    from playwright.sync_api import sync_playwright
    tokens = {0: "--acc-map-hard", 1: "--acc-map-tell", 2: "--acc-map-easy"}
    r = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _view(browser, site, BIG, DESKTOP)
            _state(page, "view.setLevel('spots');")
            for name in ("first", "second"):
                skip = r["first"]["at"]["spot"] if name == "second" else -1  # another spot: the marks made again for its line
                at = page.evaluate("([skip]) => A.anchors(24, skip)", [skip])
                assert at, "no spot in view with both anchors free on the map"
                # the marks of this line (the first one on its anchor's corner), not those of the line before
                page.wait_for_function("([spot, x, y]) => { const c = A.corners(); return A.view().selected && A.view().selected.spot === spot && "
                                       "c.length === 2 && Math.abs(c[0].left - (x + 2)) <= 2 && Math.abs(c[0].top - (y - 20)) <= 2; }",
                                       arg=[at["spot"], at["ends"][0]["x"], at["ends"][0]["y"]], timeout=WAIT)
                page.evaluate("() => A.frames()")
                line = page.evaluate("() => { const l = A.view().selected.line; return [l.access1, l.access2]; }")
                r[name] = {"at": at, "line": line, "corners": page.evaluate("() => A.corners()"), "state": _state(page),
                           "rings": [page.evaluate("([label, token]) => A.ring(label, token)", [f"A{k + 1}", tokens[s]]) for k, s in enumerate(line)],
                           # the other states' colours on the same circles: not drawn there
                           "others": [max(page.evaluate("([label, token]) => A.ring(label, token)", [f"A{k + 1}", tokens[o]]) or 0
                                          for o in tokens if o != s) for k, s in enumerate(line)]}
            _state(page, "view.openFan({lat: view.selected.line.lat1, lng: view.selected.line.lon1}, {row: view.selected.row, end: 1});")
            page.wait_for_function("() => document.querySelectorAll('.v-anchor-mark').length === 0", timeout=WAIT)
            _state(page, "view.closeFan(); view.select(null);")
            r["ended"] = page.evaluate("() => document.querySelectorAll('.v-anchor-mark').length")
            r["csp"] = page.evaluate("() => window.CSP_VIOLATIONS || []")
            assert page.errors == [], page.errors
        finally:
            browser.close()
    assert r["first"]["at"]["spot"] != r["second"]["at"]["spot"]
    for name in ("first", "second"):
        found, (a1, a2) = r[name], r[name]["line"]
        assert [(c["cls"], c["label"]) for c in found["corners"]] == [(f"ac-map ac-{a1}", f"Anchor 1: {STATES[a1]}"),
                                                                     (f"ac-map ac-{a2}", f"Anchor 2: {STATES[a2]}")], (name, found["corners"])
        assert all(c["size"] == [18, 18] and c["events"] == ["none", "none"] for c in found["corners"]), (name, found["corners"])
        # each mark on its anchor's corner: the icon's top left 2 px right of and 20 px above the anchor
        for c, end in zip(found["corners"], found["at"]["ends"]):
            assert abs(c["left"] - (end["x"] + 2)) <= 2 and abs(c["top"] - (end["y"] - 20)) <= 2, (name, c, end)
        numbers = {n["label"]: n for n in found["state"]["numbers"]}
        assert {"A1", "A2"} <= set(numbers) and numbers["A1"]["off"] <= 3 and numbers["A2"]["off"] <= 3, (name, numbers)
        # the ring in the state's map colour: most of its points; the other states' colours on few or none
        assert all(hits >= 12 for hits in found["rings"]) and all(o <= 4 for o in found["others"]), (name, found["rings"], found["others"])
    assert r["ended"] == 0 and r["csp"] == []


def _legend(page) -> dict:
    return page.evaluate("""() => { const items = [...document.querySelectorAll('.v-legend [data-kind^="access-"]')];
      const label = [...document.querySelectorAll('.v-legend .v-lg b')].map((b) => b.textContent);
      return {kinds: items.map((e) => e.dataset.kind), dots: items.map((e) => e.querySelector('svg.ac')?.getAttribute('class')),
              words: items.map((e) => [...e.childNodes].filter((n) => n.nodeType === 3).map((n) => n.textContent).join('')),
              label, help: !!document.querySelector('.v-legend .ac-info, .v-help-button .ac-info'), level: A.view().level}; }""")


@BROWSER
def test_legend_lists_the_three_marks(site):
    """The map's legend of a marked run on a desktop: "Anchors" and the three marks (easy access, cannot tell, hard
    access: the dots and the words of the details and the help) after the shapes, with the key's "i" in the legend,
    at every level (Area, Spots, Lines) and with a line selected. As built, the three are listed whenever the
    run has the mark (MapBar), as the "P1 pick" row is listed whenever "Start here" has a pick in view, drawn or not
    (docs/line-volume/spec-view.md, "As built in the UX pilot"); a run without the mark lists none of them."""
    from playwright.sync_api import sync_playwright
    r = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _view(browser, site, BIG, DESKTOP)
            for level in ("area", "spots", "lines"):
                _state(page, f"view.setLevel('{level}');")
                r[level] = _legend(page)
            _state(page, "view.select(view.inView.best[0] ?? view.order[0]);")
            r["selected"] = _legend(page)
            page.close()
            page = _view(browser, site, PLAIN, DESKTOP)
            for level in ("area", "lines"):
                _state(page, f"view.setLevel('{level}');")
                r[f"plain-{level}"] = _legend(page)
            assert page.errors == [], page.errors
        finally:
            browser.close()
    for name in ("area", "spots", "lines", "selected"):
        found = r[name]
        assert found["kinds"] == ["access-2", "access-1", "access-0"] and found["dots"] == ["ac ac-2", "ac ac-1", "ac ac-0"], (name, found)
        assert found["words"] == ["easy access", "cannot tell", "hard access"] and WORDS["ui.access.legend"] in found["label"], (name, found)
        assert found["help"] is True, (name, found)
    assert r["area"]["level"] == "area" and r["lines"]["level"] == "lines"
    for name in ("plain-area", "plain-lines"):
        assert r[name]["kinds"] == [] and WORDS["ui.access.legend"] not in r[name]["label"] and r[name]["help"] is False, (name, r[name])


@BROWSER
@pytest.mark.parametrize("device", [SMALL_PHONE, PIXEL], ids=["390", "412"])
def test_phone_legend_of_two_lines(site, device):
    """A phone's legend of a marked run: unfolded at the start (the sheet low), two lines of short labels, the second
    the three marks (the dots and their words), neither wider than the legend (no sideways scroll); its fold "Legend"
    with the kit's chevron (an icon, no character) folds and unfolds it."""
    from playwright.sync_api import sync_playwright
    legend = """() => { const lines = [...document.querySelectorAll('.v-legend .v-lg-line')], fold = document.querySelector('.v-fold'), box = document.querySelector('.v-legend');
      return {lines: lines.map((l) => [...l.querySelectorAll('[data-kind]')].map((e) => e.dataset.kind)),
              // each mark's own words (its text nodes: the dot's <title> repeats them)
              words: lines.length > 1 ? [...lines[1].querySelectorAll('[data-kind^="access-"]')].map((e) =>
                [...e.childNodes].filter((n) => n.nodeType === 3).map((n) => n.textContent).join('')) : [],
              short: lines.length ? [...lines[0].querySelectorAll('.v-lg-t')].map((e) => e.textContent) : [],
              fits: lines.every((l) => l.scrollWidth <= l.clientWidth + 1) && (!box || box.scrollWidth <= box.clientWidth + 1),
              fold: fold && [fold.getAttribute('aria-expanded'), fold.textContent.trim(), !!fold.querySelector('svg.u-ic')], shown: !!box, sideways: A.sideways()}; }"""
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _view(browser, site, BIG, device)
            page.wait_for_selector(".v-legend .v-lg-line", timeout=WAIT)
            start = page.evaluate(legend)
            _tap_on(page, ".v-fold")
            page.wait_for_function("() => document.querySelector('.v-fold').getAttribute('aria-expanded') === 'false'", timeout=WAIT)
            folded = page.evaluate(legend)
            _tap_on(page, ".v-fold")
            page.wait_for_function("() => document.querySelector('.v-fold').getAttribute('aria-expanded') === 'true'", timeout=WAIT)
            again = page.evaluate(legend)
            assert page.errors == [], page.errors
        finally:
            browser.close()
    assert len(start["lines"]) == 2 and start["lines"][1][-3:] == ["access-2", "access-1", "access-0"], start
    assert start["words"] == ["easy access", "cannot tell", "hard access"] and start["fits"] and not start["sideways"], start
    shorts = {WORDS[f"ui.view.map.lg_{k}_short"] for k in ("over", "pick", "best", "pale", "anchor", "fan")} | {WORDS["ui.result.legend_clear"]}
    assert start["short"] and set(start["short"]) <= shorts, start["short"]
    assert start["fold"] == ["true", WORDS["ui.view.map.legend_fold"], True], start
    assert folded["fold"][0] == "false" and folded["shown"] is False and again["lines"] == start["lines"], (folded, again)


@BROWSER
def test_pick_from_a_top_edge(site):
    """"Start here" of a marked run at the Area level: the fifth pick "From a top edge: walk to both anchors" is the
    highest line on average whose two anchors read easy access, shown last (P5 or the last number), its row with two
    easy dots, also within 100 m of an earlier pick. The clip's highest such line is the first pick's own line (then
    the pick is left out: test_shell_c_view_list.test_list_ranking_sorts_sectors_and_chips): its anchor is marked
    "cannot tell" in the page's columns, then any earlier pick's line it falls on, until the highest such line is no
    earlier pick's. A run without the mark has no such pick."""
    from playwright.sync_api import sync_playwright
    start = """() => { const v = A.view(), rows = [...document.querySelectorAll('.vl-topblock .vl-main')];
      return {picks: v.picks().map((k) => [k.kind, k.row, k.n]), edge: A.edge(), level: v.level,
              rows: rows.map((b) => [+b.dataset.row, b.querySelector('.v-sh')?.getAttribute('aria-label') ?? null, b.querySelector('.vl-lab')?.textContent ?? null,
                                     [...b.querySelectorAll('.vl-cell-acc svg.ac')].map((d) => d.getAttribute('class'))]),
              legendP: !!document.querySelector('.v-legend [data-kind="P"]'),
              // the pick's middle to the nearest earlier pick's, grid metres
              apart: (() => { const p = v.picks(), x = v.values, mid = (r) => [(x.x1[r] + x.x2[r]) / 2, (x.y1[r] + x.y2[r]) / 2], last = p[p.length - 1];
                if (!last || p.length < 2) return null; const a = mid(last.row);
                return Math.min(...p.slice(0, -1).map((k) => { const b = mid(k.row); return Math.hypot(a[0] - b[0], a[1] - b[1]); })); })()}; }"""
    r = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _view(browser, site, BIG, DESKTOP)
            _state(page, "view.setLevel('area');")
            page.wait_for_selector(".vl-topblock .vl-lab", timeout=WAIT)
            r["before"] = page.evaluate(start)
            r["marked"] = page.evaluate("""() => { const v = A.view(), c = v.model.data.columns, out = [];
              for (let k = 0; k < 12; k++) { const e = A.edge(), picks = v.picks();
                if (e < 0 || picks.some((p) => p.kind === 'edge') || !picks.some((p) => p.row === e)) break;
                c.access1.values[e] = 1; out.push(e); A.redraw(); }
              return out; }""")
            page.evaluate("() => A.frames()")
            page.wait_for_function("() => A.view().picks().some((k) => k.kind === 'edge') && "
                                   "[...document.querySelectorAll('.vl-topblock .vl-lab')].some((e) => e.textContent === %s)"
                                   % json.dumps(WORDS["ui.view.pick.edge"]), timeout=WAIT)
            _state(page)
            r["after"] = page.evaluate(start)
            page.close()
            page = _view(browser, site, PLAIN, DESKTOP)
            _state(page, "view.setLevel('area');")
            page.wait_for_selector(".vl-topblock .vl-lab", timeout=WAIT)
            r["plain"] = page.evaluate(start)
            assert page.errors == [], page.errors
        finally:
            browser.close()
    before, after = r["before"], r["after"]
    assert before["level"] == "area" and "edge" not in [k[0] for k in before["picks"]] and before["edge"] == before["picks"][0][1], before
    assert r["marked"] and r["marked"][0] == before["edge"], r["marked"]
    kind, row, n = after["picks"][-1]
    assert kind == "edge" and row == after["edge"] >= 0 and n == len(after["picks"]) <= 5, after["picks"]
    assert row not in [k[1] for k in after["picks"][:-1]]
    last = after["rows"][-1]
    assert last[0] == row and last[1] == f"P{n}" and last[2] == WORDS["ui.view.pick.edge"], last
    assert last[3] == ["ac ac-2", "ac ac-2"] and after["legendP"], last
    # shown also within 100 m of an earlier pick (the four others are left out there): the clip's is 7 m from P1
    print(f"From a top edge: P{n}, {after['apart']:.0f} m from the nearest earlier pick")
    assert after["apart"] < 100, after["apart"]
    assert r["plain"]["picks"] and "edge" not in [k[0] for k in r["plain"]["picks"]] and r["plain"]["edge"] == -1, r["plain"]


@BROWSER
def test_run_without_the_mark_draws_none_of_it(site):
    """A run made without --access in the view: no column (the heads Length, Mean height, Clearance, Lines), no dot
    or "–" in a row, no pair in the head and no block in the details, no "Far end" in "Lines from here", no marks on
    the map's corners, no legend's marks and no key; nor the line of a mark left out; on a desktop and a phone. On
    the canvas the selected line's A1 and A2 are the circles of a line without the mark: their ring in the numbers'
    ink, not in the map colours of easy access or cannot tell, and no mark on their corners (today's
    test_run_without_the_mark_draws_none_of_it: the white dots)."""
    from playwright.sync_api import sync_playwright
    count = "() => document.querySelectorAll(%s).length" % json.dumps(MARK_ANY + ", .r-acc-skipped")
    ink = "#1b2530"  # SpotMap.ts INK: the ring of an anchor's circle with no state
    r = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _view(browser, site, PLAIN, DESKTOP)
            _state(page, "view.setLevel('spots');")
            at = page.evaluate("() => A.anchors(24, -1)")
            assert at, "no spot in view with both anchors free on the map"
            page.wait_for_function(f"() => A.view().selected && A.view().selected.spot === {at['spot']}", timeout=WAIT)
            canvas = _state(page)
            r["canvas"] = {"numbers": sorted(n["label"] for n in canvas["numbers"] if n["label"][0] == "A"),
                           "ink": [page.evaluate("([label, c]) => A.ringOf(label, c)", [label, ink]) for label in ("A1", "A2")],
                           # (not "--acc-map-hard": #2f3a45 lies within the bounds of the ink #1b2530; the corners'
                           # marks, none, tell that state apart)
                           "states": [max(page.evaluate("([label, token]) => A.ring(label, token)", [label, token]) or 0
                                          for token in ("--acc-map-tell", "--acc-map-easy")) for label in ("A1", "A2")],
                           "corners": page.evaluate("() => document.querySelectorAll('.v-anchor-mark').length")}
            page.close()
            for name, context in (("desktop", DESKTOP), ("phone", PHONE)):
                page = _view(browser, site, PLAIN, context)
                if name == "phone":
                    _sheet(page, "half")
                r[name] = {"start": page.evaluate(count), "acc": page.evaluate("() => A.view().model.hasAccess"),
                           "heads": page.evaluate("() => A.heads('.vl-tree')")}
                page.evaluate("() => { const v = A.view(); v.select(v.order[0]); }")
                page.wait_for_selector(".vl-details", state="attached", timeout=WAIT)
                page.evaluate("() => A.frames()")
                r[name]["selected"] = page.evaluate(count)
                r[name]["head"] = page.evaluate("() => [document.querySelectorAll('.vl-spot-title').length, "
                                                "document.querySelectorAll('.vl-spot-title .ac-pair, .vl-spot-title .ac-none').length]")
                page.evaluate("() => document.querySelector('.vl-from-1').click()")
                page.wait_for_selector(".vl-fan .vl-main", state="attached", timeout=WAIT)
                r[name]["fan"] = [page.evaluate(count), page.evaluate("() => A.heads('.vl-fan')")]
                assert page.errors == [], page.errors
                page.close()
        finally:
            browser.close()
    canvas = r.pop("canvas")
    assert canvas["numbers"] == ["A1", "A2"] and canvas["corners"] == 0, canvas
    assert all(hits >= 12 for hits in canvas["ink"]) and all(hits <= 4 for hits in canvas["states"]), canvas
    for name, found in r.items():
        assert found["acc"] is False and found["start"] == found["selected"] == found["fan"][0] == 0, (name, found)
        assert found["head"] == [1, 0], (name, found)  # the head is there, without a pair
        assert [h[0] for h in found["heads"]] == [WORDS[k] for k in ("ui.list.col.length", "ui.list.col.mean", "ui.view.col.clear",
                                                                    "ui.list.col.lines")], (name, found["heads"])
        assert WORDS["ui.view.fan.far_end"] not in [h[0] for h in found["fan"][1]] and not any(h[1] for h in found["fan"][1]), (name, found)


@BROWSER
def test_run_whose_mark_was_left_out(site):
    """A run whose head says the mark was asked for and left out (`access_skipped`): in the view's head today's muted
    line "Anchors' access not marked: the search area was too wide." once, after the headline and "found", before the
    filters, in today's colour (the same line on today's page, `--muted`) and at 12 px or more; on a phone in the
    sheet, also while nothing is selected (the headline then in the sheet's head); and nothing else of the mark."""
    from playwright.sync_api import sync_playwright
    state = """() => { const lines = [...document.querySelectorAll('.r-acc-skipped')].filter((e) => e.getClientRects().length), line = lines[0];
      const before = (a, b) => !!(a && b && (a.compareDocumentPosition(b) & 4));
      const model = window.FINDALINE_VIEW ? window.FINDALINE_VIEW.view.model : window.FINDALINE_RESULT.model;
      return {key: model.data.access_skipped, count: lines.length, text: line && line.textContent,
              inSummary: !!(line && line.closest('.vl-summary')), afterFound: before(document.querySelector('.r-found-line'), line),
              afterCount: before(document.querySelector('.vl-count'), line), beforeFilters: before(line, document.querySelector('.r-filters')),
              inSheet: !!(line && line.closest('.u-sheet-body')), colour: line && getComputedStyle(line).color, px: line && parseFloat(getComputedStyle(line).fontSize),
              mark: document.querySelectorAll(%s).length}; }""" % json.dumps(MARK_ANY)
    r = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _view(browser, site, SKIPPED, DESKTOP)
            page.wait_for_selector(".vl-summary .r-acc-skipped", timeout=WAIT)
            r["desktop"] = page.evaluate(state)
            page.evaluate("() => { const v = A.view(); v.select(v.order[0]); }")
            page.wait_for_selector(".vl-details", timeout=WAIT)
            r["selected"] = page.evaluate(state)
            page.close()
            phone = _view(browser, site, SKIPPED, PHONE)
            _sheet(phone, "half")
            phone.wait_for_selector(".u-sheet-body .r-acc-skipped", state="attached", timeout=WAIT)
            r["phone"] = phone.evaluate(state)
            phone.evaluate("() => { const v = A.view(); v.select(v.order[0]); }")
            phone.wait_for_selector(".u-sheet .vl-details", state="attached", timeout=WAIT)
            phone.evaluate("() => A.frames()")
            r["phoneSelected"] = phone.evaluate(state)
            assert phone.errors == [], phone.errors
            phone.close()
            # today's page on the same run: the colour the view's line must have
            today = _open(browser, f"{site}#run={SKIPPED}", DESKTOP, flag=False, script=HELP)
            today.wait_for_function("() => !!window.FINDALINE_RESULT", timeout=WAIT)
            today.wait_for_selector(".r-acc-skipped", timeout=WAIT)
            r["today"] = today.evaluate(state)
        finally:
            browser.close()
    for name in ("desktop", "selected", "phone", "phoneSelected"):
        found = r[name]
        assert found["key"] == "memory" and found["count"] == 1 and found["text"] == WORDS["ui.access.skipped"], (name, found)
        assert found["inSummary"] and found["afterFound"] and found["beforeFilters"] and found["mark"] == 0, (name, found)
        assert found["colour"] == r["today"]["colour"] and found["px"] >= 12, (name, found, r["today"]["colour"])
    assert r["desktop"]["afterCount"] and not r["desktop"]["inSheet"], r["desktop"]
    assert r["phone"]["inSheet"] and r["phoneSelected"]["inSheet"], r
    assert r["today"]["count"] == 1 and r["today"]["text"] == WORDS["ui.access.skipped"]


def _over_holds(rows: list, where: str):
    """A list's rows: a line over trees or buildings says so in the list's words, once, on a line of its own under
    the row's values, after its mark (and swatch), inside the row, at 12 px or more; a clear line's row not at all."""
    assert any(r["over"] for r in rows) and any(not r["over"] for r in rows), (where, rows)
    for r in rows:
        if r["over"]:
            assert r["cls"] and r["words"] == OVER and r["times"] == 1 and r["hidden"] is False, (where, r)
            assert r["shown"] and r["under"] and r["after"] and r["inside"] and r["oneLine"] and r["whole"] and r["px"] >= 12, (where, r)
        else:
            assert not r["cls"] and r["words"] is None and r["times"] == 0, (where, r)


@BROWSER
@pytest.mark.parametrize("device", [DESKTOP, PHONE, PIXEL], ids=["desktop", "390", "412"])
def test_over_trees_in_words_in_the_fan_and_the_table(site, device):
    """R4.2 (the design review's item 9): in "Lines from here" and in the table of spots a line over trees or
    buildings says so in words, as "Best in view", "Start here" and the tree (the same words and rule: the pilot's
    row 7), and a clear line does not; on a desktop and on phones of 390 and 412 px, whose page does not scroll
    sideways. The lines' marks are set in the page's columns (one fan row's line over trees, the next one's clear;
    one spot of the table over trees, another clear)."""
    from playwright.sync_api import sync_playwright
    phone = device is not DESKTOP
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _view(browser, site, BIG, device)
            if phone:
                _sheet(page, "half")
            # "Lines from here" at the first anchor of the best spot's shown line: its first two rows' lines over
            # trees and clear, then the fan opened again at the same point (the same rows)
            open_fan = "const row = view.shownOf(view.order[0]), c = view.model.data.columns; view.select(view.order[0]); " \
                       "view.openFan({lat: c.lat1.at(row), lng: c.lon1.at(row)}, {row, end: 1});"
            _state(page, open_fan)
            page.wait_for_selector(".vl-fan .vl-main", state="attached", timeout=WAIT)
            rows = page.evaluate("() => A.view().fan.rows.map((r) => r.row)")
            assert len(rows) >= 2, rows
            page.evaluate("([a, b]) => { const c = A.view().model.data.columns; c.over[a] = 1; c.over[b] = 0; A.redraw(); }", rows[:2])
            _state(page, open_fan)
            page.wait_for_selector(".vl-fan .vl-main", state="attached", timeout=WAIT)
            fan = page.evaluate("() => ({rows: A.over('.vl-fan'), sideways: A.sideways(), model: A.view().fan.rows.map((r) => r.row)})")
            assert fan["model"] == rows, (fan["model"], rows)
            _over_holds(fan["rows"], "fan")
            # the words' colour is the list's own (the tree's rows of lines over trees)
            tree = page.evaluate("() => A.over('.vl-tree').filter((r) => r.over)")
            assert tree and {r["colour"] for r in fan["rows"] if r["over"]} == {tree[0]["colour"]}, tree[:1]
            assert not fan["sideways"]
            _state(page, "view.closeFan(); view.select(null);")
            # the table of spots: a press where several spots are about as near (a finger: a quarter step closer than
            # the last zoom above 0.25 m per pixel, where a tap no longer zooms in: test_shell_c_view_map's
            # test_phone_touch); its first spot's lines over trees, its second's clear, then the press
            if phone:
                _state(page, "leaflet.setZoom(map.zoomOf(0.25) + 0.25, {animate: false});")
            at = _crowded(page, phone)
            assert at and len(at["spots"]) > 1, at
            page.evaluate("([a, b]) => { const v = A.view(), c = v.model.data.columns; for (let r = 0; r < v.count; r++) { "
                          "if (v.spotOf(r) === a) c.over[r] = 1; if (v.spotOf(r) === b) c.over[r] = 0; } A.redraw(); }", at["spots"][:2])
            page.evaluate("() => A.frames()")
            if phone:
                _tap(page, at["x"], at["y"])
            else:
                page.mouse.click(at["x"], at["y"])
            page.wait_for_selector(".vl-choose:not(.vl-choose-new) .vl-main", timeout=WAIT)
            table = page.evaluate("() => ({rows: A.over('.vl-choose'), spots: [...document.querySelectorAll('.vl-choose .vl-main')].map((b) => +b.dataset.spot), "
                                  "sideways: A.sideways(), docked: !!document.querySelector('.vl-choose-dock')})")
            assert set(at["spots"][:2]) <= set(table["spots"]) and table["docked"] == phone, (at["spots"], table["spots"])
            _over_holds(table["rows"], "table")
            assert not table["sideways"]
            assert page.evaluate("() => window.CSP_VIOLATIONS || []") == [] and page.errors == [], page.errors
        finally:
            browser.close()


def _kit_info() -> str:
    """The kit's "info" icon's markup (viewer/src/ui/icons.tsx ICONS.info)."""
    with open(os.path.join(REPO, "viewer", "src", "ui", "icons.tsx"), encoding="utf-8") as f:
        return re.search(r"^\s*info: '([^']*)',$", f.read(), re.M).group(1)


def test_boxes_icon_is_a_copy_of_the_kits():
    """shoreLayer.ts INFO_ICON (the boxes' help; a copy, as shoreLayer.ts is also bundled without the loader of the
    logo's .svg files that ui/icons.tsx imports) is the kit's "info" icon as icons.tsx's Icon draws it: ICONS.info's
    markup in an <svg> of the class u-ic, the viewBox 0 0 24 24 and aria-hidden "true". A plain test of the two
    sources: it runs where Playwright is not installed (CI's tests job installs the tui group, not ui)."""
    with open(os.path.join(REPO, "viewer", "src", "shoreLayer.ts"), encoding="utf-8") as f:
        shore = f.read()
    with open(os.path.join(REPO, "viewer", "src", "ui", "icons.tsx"), encoding="utf-8") as f:
        icons = f.read()
    literal = re.search(r"export const INFO_ICON = ((?:'[^']*'\s*\+?\s*)+);", shore)
    assert literal, "INFO_ICON is no longer a string literal of shoreLayer.ts"
    markup = "".join(re.findall(r"'([^']*)'", literal.group(1)))
    copy = re.fullmatch(r'<svg class="u-ic" viewBox="0 0 24 24" aria-hidden="true">(.*)</svg>', markup)
    assert copy and copy.group(1) == _kit_info(), (markup, _kit_info())
    # the kit's own wrapper (Icon): the same class, viewBox and aria-hidden (an icon without a title)
    icon = re.search(r"export function Icon\(.*?\n}\n", icons, re.S).group(0)
    assert "class={`u-ic" in icon and 'viewBox="0 0 24 24"' in icon and 'aria-hidden={title ? undefined : "true"}' in icon, icon


@BROWSER
@pytest.mark.parametrize("view", [True, False], ids=["view", "today"])
def test_boxes_help_is_the_kits_info_icon(site, view):
    """The uncertain shore's box and the coarser terrain's box (shoreLayer.ts, coarserLayer.ts) on the result view's
    map and on today's page: each one's help is the kit's info icon (its markup the kit's ICONS.info; no "?"
    character: R9, "?" being the access mark's "cannot tell"), under the same name as before, closed at first, opening
    its explanation and closing it again; 44 px or more on a phone (R2). The 3D view uses neither file."""
    from playwright.sync_api import sync_playwright
    info = _kit_info()
    # each box's help as drawn; its icon's markup against the kit's, both as the page's SVG writes them
    boxes = """(kit) => { const probe = document.createElementNS('http://www.w3.org/2000/svg', 'svg'); probe.innerHTML = kit;
      return [...document.querySelectorAll('.u-shore')].filter((b) => b.getClientRects().length).map((box) => { const h = box.querySelector('.u-shore-help'), svg = h.querySelector('svg'), r = h.getBoundingClientRect();
        return {coarse: box.classList.contains('u-coarse'), label: h.getAttribute('aria-label'), expanded: h.getAttribute('aria-expanded'), text: h.textContent.trim(),
                icon: svg && [svg.getAttribute('class'), svg.getAttribute('viewBox'), svg.getAttribute('aria-hidden'), svg.innerHTML === probe.innerHTML],
                size: [Math.round(r.width), Math.round(r.height)], more: !box.querySelector('.u-shore-more').hidden}; }); }"""
    r = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            for name, context in (("desktop", DESKTOP), ("phone", PHONE)):
                page = _open(browser, f"{site}#run={BOXES}", context, flag=view, script=HELP)
                page.wait_for_function("() => !!(window.FINDALINE_VIEW || window.FINDALINE_RESULT)", timeout=WAIT)
                page.evaluate("() => { window.FINDALINE_MAP.zoomOut(1, {animate: false}); }")  # the boxes' regions in view
                page.wait_for_selector(".u-shore-ctl:not([hidden])", timeout=WAIT)
                page.wait_for_selector(".u-coarse:not([hidden])", timeout=WAIT)
                if name == "phone":  # a phone folds the shore's box into its chip
                    page.click(".u-shore-chip")
                    page.wait_for_selector(".u-shore-ctl:not(.u-shore-folded)", timeout=WAIT)
                r[name] = page.evaluate(boxes, info)
                opened = []
                for k, help_ in enumerate((".u-shore-ctl .u-shore-help", ".u-coarse .u-shore-help")):
                    for _ in ("open", "close"):
                        if name == "desktop":  # a real press at the button's centre (Playwright's hit test: nothing covers it)
                            page.click(help_)
                        else:
                            # A phone: the script's press. The known overlaps (before this branch too; wave B's): in the
                            # view the layers button (.leaflet-control-layers) covers the coarser box's help, and on
                            # today's iPhone the coarser box runs under the scale and the credits
                            # (.leaflet-control-scale, .leaflet-control-attribution)
                            page.evaluate(f"() => document.querySelector({json.dumps(help_)}).click()")
                        page.evaluate("() => A.frames()")
                        if _ == "open":
                            opened.append(page.evaluate(boxes, info)[k])
                r[name + "-opened"], r[name + "-closed"] = opened, page.evaluate(boxes, info)
                r[name + "-csp"] = page.evaluate("() => window.CSP_VIOLATIONS || []")
                assert page.errors == [], page.errors
                page.close()
        finally:
            browser.close()
    for name in ("desktop", "phone"):
        found = r[name]
        assert [b["coarse"] for b in found] == [False, True], (name, found)
        assert [b["label"] for b in found] == [WORDS["ui.shore.help_button"], WORDS["ui.coarse.help_button"]], (name, found)
        for b in found:
            assert b["text"] == "" and b["icon"] == ["u-ic", "0 0 24 24", "true", True] and b["expanded"] == "false" and not b["more"], (name, b)
            assert min(b["size"]) >= (44 if name == "phone" else 24), (name, b)
        assert all(b["expanded"] == "true" and b["more"] for b in r[name + "-opened"]), (name, r[name + "-opened"])
        assert all(b["expanded"] == "false" and not b["more"] for b in r[name + "-closed"]), (name, r[name + "-closed"])
        assert r[name + "-csp"] == [], (name, r[name + "-csp"])
    for folder, _, files in os.walk(os.path.join(REPO, "viewer", "src", "view3d")):
        for file in files:
            with open(os.path.join(folder, file), encoding="utf-8") as f:
                assert not re.search(r"shoreLayer|coarserLayer", f.read()), file
