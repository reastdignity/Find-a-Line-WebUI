"""The access mark on the result page and in a cell's search form (viewer/src/access.tsx; step 1d-P), in Playwright's
Edge over the app's server, offline: a run of the Żabi Koń clip made with --access (the three states are in it) and
the same run made without. What the page draws of the mark: the list's column "Anchors" with its three widths, the
details' block and the phone head's pair, the legend's row with its place on a phone, the map's two marks of the
selected line; a run without the mark draws none of it. And the highline layer's "Search a cell" opens the form with
the mark on. Every wait is an event with a deadline. Run from PowerShell (.claude/rules/browser-tests.md)."""

import json
import os
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_shell_c import BIG, SMALL, copy_clip, small_copy, stub_page  # noqa: E402
from test_web import EDGE, _basic_page, _playwright, _search_page, _server  # noqa: E402
sys.path.insert(0, os.path.join(REPO, "tools"))
import today_page  # noqa: E402  (the pin of today's page)

pytestmark = pytest.mark.skipif(not os.path.exists(EDGE) or not _playwright(),
                                reason="needs Microsoft Edge and Playwright (group ui)")
WAIT = 30000  # ms: the deadline of every wait for the page
DESKTOP = {"viewport": {"width": 1400, "height": 900}}
PHONE = {"viewport": {"width": 390, "height": 844}, "device_scale_factor": 3, "is_mobile": True, "has_touch": True}
WORDS = {0: "hard access", 1: "cannot tell", 2: "easy access"}


def _clip(tmp_path_factory, name: str, *more: str):
    """The folder of a run of the Żabi Koń clip (test_shell_c's big_clip arguments, so the search without `more` is
    the one that module made), computed once per session, offline."""
    import clip_runs
    data = os.path.join(REPO, "tests", "data")
    folder = clip_runs.data_copy(tmp_path_factory, name, [
        "--elevation-file", os.path.join(data, "zabi_kon_nmt.tif"),
        "--surface-file", os.path.join(data, "zabi_kon_nmpt.tif"), "--northing", "254608", "--easting", "553966",
        "--radius", "150", "--model", "sag", "--fall-zone", "3", "--water", "off", "--fill-gaps", "off",
        "--no-plot", "--yes", "--ortho", "never", *more])
    runs = folder / "runs"
    return next(runs / d for d in os.listdir(runs) if (runs / d / "run.json").is_file())


@pytest.fixture(scope="module")
def marked_clip(tmp_path_factory):
    return _clip(tmp_path_factory, "access-page-on", "--access")


@pytest.fixture(scope="module")
def plain_clip(tmp_path_factory):
    return _clip(tmp_path_factory, "access-page-off")


def _data(tmp_path, clip):
    """A data folder with the clip's run (BIG) and its first 300 lines (SMALL), and the app's page for the tests."""
    folder = tmp_path / "data"
    copy_clip(clip, folder, BIG, "Big run")
    small_copy(folder, BIG)
    return folder, stub_page(folder, "accesstest")


def _layout(width: int) -> str:
    """A kept layout of the result (localStorage "findaline.layout") with the list `width` px wide."""
    return json.dumps({"v": 1, "list": {"w": width, "open": True}, "details": {"w": 380, "open": True},
                       "profile": {"h": 260, "folded": False, "l": 12, "r": 12}})


def _open(browser, url: str, kept: int | None = None, **context):
    """The result's page (today's, pinned: tools/today_page.py; its list drawn), with a kept layout of the list's
    width `kept`."""
    page = browser.new_page(**context)
    page.add_init_script(today_page.SCRIPT)
    if kept:
        page.add_init_script(f"localStorage.setItem('findaline.layout', {json.dumps(_layout(kept))})")
    page.goto(url)
    page.wait_for_selector(".r-rows .r-row", state="attached", timeout=WAIT)
    page.wait_for_function("() => !!window.FINDALINE_RESULT", timeout=WAIT)
    return page


# The list as the page draws it: the table's classes and width, the heading's cells, each row's cell of the mark
# (the dots' classes and labels, or the "–" with its role and name) beside the same row's line of the model
LIST = """() => { const $ = (s) => document.querySelector(s), $$ = (s) => [...document.querySelectorAll(s)];
  const model = window.FINDALINE_RESULT.model, table = $('.r-table');
  const rows = $$('.r-rows > .r-spot > .r-row').slice(0, 12).map((row, k) => { const cell = row.querySelector('.r-cell-acc');
    const line = model.rows[k].line;
    return {line: [line.access1 ?? null, line.access2 ?? null], cells: row.children.length,
            dots: cell ? [...cell.querySelectorAll('svg.ac')].map((d) => [d.getAttribute('class'), d.getAttribute('aria-label'),
                          Math.round(d.getBoundingClientRect().width), d.children.length]) : null,
            none: cell ? [...cell.querySelectorAll('.ac-none')].map((n) => [n.textContent, n.getAttribute('role'), n.getAttribute('aria-label')]) : null,
            // the cell's content stays inside the cell (no overlap with its neighbours)
            inside: cell ? cell.scrollWidth <= cell.clientWidth + 1 : null}; });
  return {classes: table.className.split(' ').sort(), width: Math.round(table.getBoundingClientRect().width),
          // the heading as shown: its visually hidden part (the sorted column's order, said in its name) left out
          head: $$('.r-table .r-head > *').map((c) => [c.tagName, [...c.childNodes]
            .filter((n) => !n.classList?.contains('u-sr')).map((n) => n.textContent).join('').trim().replace(/[\\u00a0 ]*[↓↑]$/, ''), c.classList.contains('r-cell-acc')]),
          rows, hasAccess: model.hasAccess, legend: !!$('.r-legend-acc'),
          scroll: [document.documentElement.scrollWidth, innerWidth]}; }"""


def test_list_column_and_its_widths(tmp_path, marked_clip):
    """The list's column "Anchors" of a run made with --access: before "Lines", its heading no button, in every
    row two dots of 20 px with the row's line's states (anchor 1, anchor 2: the model's values) and their names;
    full at the default width (the list 372 px), tighter in a list kept at 340 px (under 356 px of table), left out
    in one of 280 px (under 300 px: the rows as a run without the mark, the legend's row stays); full on a phone of
    390 px, whose page does not scroll sideways."""
    from playwright.sync_api import sync_playwright
    folder, page_path = _data(tmp_path, marked_clip)
    r = {}
    with _server(folder) as port, sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            url = f"http://127.0.0.1:{port}/{page_path}?ui=c#run={SMALL}"
            for name, kept, context in (("default", None, DESKTOP), ("w340", 340, DESKTOP), ("w280", 280, DESKTOP),
                                        ("phone", None, PHONE)):
                page = _open(browser, url, kept, **context)
                # the width is measured after the first layout: the column's class follows it
                want = {"default": "r-with-acc", "w340": "r-acc-tight", "phone": "r-with-acc"}.get(name)
                if want:
                    page.wait_for_selector(f".r-table.{want}", state="attached", timeout=WAIT)
                else:
                    page.wait_for_function("() => !document.querySelector('.r-table.r-with-acc')", timeout=WAIT)
                r[name] = page.evaluate(LIST)
                page.close()
        finally:
            browser.close()
    for name in ("default", "w340", "phone"):
        found = r[name]
        assert found["hasAccess"] and found["legend"], (name, found)
        heads = [h[1] for h in found["head"]]
        assert heads[-3:-1] == ["Anchors", "Lines"] and heads[1] == "Length", (name, heads)
        assert found["head"][-3] == ["SPAN", "Anchors", True], (name, found["head"])  # no button: not sortable
        assert len(found["rows"]) >= 8, (name, len(found["rows"]))
        for row in found["rows"]:
            a1, a2 = row["line"]
            assert a1 in WORDS and a2 in WORDS and row["none"] == [] and row["inside"], (name, row)
            assert [d[:3] for d in row["dots"]] == [[f"ac ac-{a1}", f"Anchor 1: {WORDS[a1]}", 20],
                                                    [f"ac ac-{a2}", f"Anchor 2: {WORDS[a2]}", 20]], (name, row)
            assert all(d[3] >= 3 for d in row["dots"]), (name, row)  # a title, the dot's circle and a sign in every dot
            assert row["cells"] == 7, (name, row)
    # more than one state in the rows looked at (the clip's run has all three)
    assert len({s for row in r["default"]["rows"] for s in row["line"]}) >= 2
    assert r["default"]["classes"] == ["r-table", "r-with-acc"] and r["default"]["width"] >= 356, r["default"]
    assert r["w340"]["classes"] == ["r-acc-tight", "r-table", "r-with-acc"] and 300 <= r["w340"]["width"] < 356, r["w340"]
    assert r["phone"]["classes"] == ["r-table", "r-with-acc"], r["phone"]
    assert r["phone"]["scroll"][0] <= r["phone"]["scroll"][1], r["phone"]
    narrow = r["w280"]
    assert narrow["classes"] == ["r-table"] and narrow["width"] < 300, narrow
    assert narrow["hasAccess"] and narrow["legend"], narrow  # the marks stay in the legend (and the details)
    assert [h[1] for h in narrow["head"]][-2] == "Lines" and not any(h[2] for h in narrow["head"]), narrow["head"]
    assert all(row["dots"] is None and row["cells"] == 6 for row in narrow["rows"]), narrow["rows"]


# The details of the selected line and the legend, as drawn
DETAILS = """() => { const $ = (s) => document.querySelector(s), $$ = (s) => [...document.querySelectorAll(s)];
  const line = window.FINDALINE_RESULT.model.selected.line, block = $('.r-acc');
  const dot = (d) => d ? [d.getAttribute('class'), d.getAttribute('aria-label'), Math.round(d.getBoundingClientRect().width)] : null;
  const stats = $('.r-details .u-stats'), acts = $('.r-details .r-acts');
  return {line: [line.access1, line.access2],
          title: block && block.querySelector('.r-acc-h').firstChild.textContent,
          hint: block && [block.querySelector('.r-acc-h .ac-hint').getAttribute('aria-label'), block.querySelector('.ac-hint').getAttribute('aria-expanded')],
          rows: block ? [...block.querySelectorAll('.r-acc-row')].map((row) => [dot(row.querySelector('svg.ac')), row.children[1].textContent, row.children[2].textContent]) : [],
          // under the four numbers, above the line's actions
          placed: !!(block && stats && acts) && !!(stats.compareDocumentPosition(block) & 4) && !!(block.compareDocumentPosition(acts) & 4),
          head: $$('.r-dtitle .ac-pair svg.ac').map(dot), heads: $$('.r-dtitle').length,
          headOneLine: (() => { const t = $('.r-dtitle'), p = t.querySelector('.ac-pair'); if (!p) return null;
                                const a = t.getBoundingClientRect(), b = p.getBoundingClientRect(); return b.top >= a.top - 1 && b.bottom <= a.bottom + 1 && b.right <= a.right + 1; })(),
          help: $$('.r-acc .ac-help .ac-key-row').length}; }"""

LEGEND = """() => { const $ = (s) => document.querySelector(s), $$ = (s) => [...document.querySelectorAll(s)];
  const rows = $$('.r-legend-acc').filter((e) => e.getClientRects().length), legend = rows[0];
  if (!legend) return {count: 0, colours: $$('.r-legend:not(.r-legend-acc)').length};
  const items = [...legend.children], last = items[items.length - 1], hint = legend.querySelector('.ac-hint');
  const top = (e) => Math.round(e.getBoundingClientRect().top + e.getBoundingClientRect().height / 2);
  const filters = $('.r-filters'), table = $('.r-table'), sheet = legend.closest('.u-sheet-body'), head = legend.closest('.c-col-head');
  return {count: rows.length, label: items[0].textContent,
          // each state's own words (its text nodes: the dot's <title> repeats them)
          states: items.slice(1).map((s) => [s.querySelector('svg.ac').getAttribute('class'),
                                             [...s.childNodes].filter((n) => n.nodeType === 3).map((n) => n.textContent).join('')]),
          hint: [hint.getAttribute('aria-label'), hint.getAttribute('aria-expanded'), hint.textContent],
          // the "?" stands in the last state's item and on its line: never alone on a line of its own
          hintWithLast: last.contains(hint) && Math.abs(top(hint) - top(last.querySelector('svg.ac'))) <= 4,
          // the row's visual lines: items whose vertical ranges overlap stand on one line. (Until 2026-11-19 the
          // count was the distinct Math.round(top / 8): the label's top is 0.94 px under the dots' on the same line,
          // and with the row 0.72 px lower (step 3c's sizes: tops 132.09 and 131.16) the two fell on both sides of a
          // rounding, 3 for a row of 2 lines; measured on both codes, local/ux-design-2026-11-16/3c-a/legend.)
          lines: (() => { let n = 0, bottom = -1e9;
            for (const b of items.map((e) => e.getBoundingClientRect()).sort((a, c) => a.top - c.top)) {
              if (b.top >= bottom - 1) n++;
              bottom = Math.max(bottom, b.bottom); }
            return n; })(),
          beforeFilters: !!(filters && (legend.compareDocumentPosition(filters) & 4)), beforeList: !!(legend.compareDocumentPosition(table) & 4),
          inSheet: !!sheet, inHead: !!head, inSummary: !!legend.closest('.r-summary'),
          colours: $$('.r-legend:not(.r-legend-acc)').filter((e) => e.getClientRects().length).length,
          fits: legend.scrollWidth <= legend.clientWidth + 12, helps: $$('.ac-help').length,
          scroll: [document.documentElement.scrollWidth, innerWidth]}; }"""


def test_details_block_and_the_phone_heads_pair(tmp_path, marked_clip):
    """A selected line of a marked run: "Reaching the anchors" under the four numbers and above the actions, a row
    per anchor (the dot of the line's state with its name, "Anchor 1", the state's words) and its "?" (the help of
    the three states opens in the block); the head carries the two dots only on a phone (the sheet's head), on the
    title's line."""
    from playwright.sync_api import sync_playwright
    folder, page_path = _data(tmp_path, marked_clip)
    r = {}
    with _server(folder) as port, sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            url = f"http://127.0.0.1:{port}/{page_path}?ui=c#run={SMALL}"
            page = _open(browser, url, **DESKTOP)
            page.click(".r-rows .r-row")
            page.wait_for_selector(".c-col-details .r-acc", timeout=WAIT)
            r["desktop"] = page.evaluate(DETAILS)
            page.click(".r-acc .ac-hint")
            page.wait_for_selector(".r-acc .ac-help", timeout=WAIT)
            r["help"] = page.evaluate(DETAILS)
            page.close()
            phone = _open(browser, url, **PHONE)
            phone.evaluate("() => { const m = window.FINDALINE_RESULT.model; m.select(m.groups[0]); }")
            phone.wait_for_selector(".u-sheet .r-acc", state="attached", timeout=WAIT)
            r["phone"] = phone.evaluate(DETAILS)
            phone.close()
        finally:
            browser.close()
    for name in ("desktop", "phone"):
        found = r[name]
        a1, a2 = found["line"]
        assert found["title"] == "Reaching the anchors" and found["placed"], (name, found)
        assert found["hint"] == ["About reaching the anchors", "false"], (name, found)
        assert found["rows"] == [[[f"ac ac-{a1}", f"Anchor 1: {WORDS[a1]}", 20], "Anchor 1", WORDS[a1]],
                                 [[f"ac ac-{a2}", f"Anchor 2: {WORDS[a2]}", 20], "Anchor 2", WORDS[a2]]], (name, found)
    assert r["desktop"]["head"] == [] and r["desktop"]["headOneLine"] is None, r["desktop"]  # a desktop: no pair in the head
    a1, a2 = r["phone"]["line"]
    assert r["phone"]["head"] == [[f"ac ac-{a1}", f"Anchor 1: {WORDS[a1]}", 20],
                                  [f"ac ac-{a2}", f"Anchor 2: {WORDS[a2]}", 20]], r["phone"]
    assert r["phone"]["headOneLine"] is True, r["phone"]
    assert r["help"]["help"] == 3 and r["help"]["hint"][1] == "true" and r["desktop"]["help"] == 0, r["help"]


def test_legend_row_and_its_place_on_a_phone(tmp_path, marked_clip):
    """The legend's row of the mark: "Anchors", the three states with their dots (easy access, cannot tell, hard
    access) and the "?", which stays with the last state on its line (never alone on a line of its own: a phone
    of 390 px, the desktop's list of 372 px) and opens the help under the row. On a desktop in the list's head under
    the colours' legend; on a phone above the filters and the list, alone while nothing is selected (the sheet's
    head shows the summary without a legend) and in the summary's legend once a line is."""
    from playwright.sync_api import sync_playwright
    folder, page_path = _data(tmp_path, marked_clip)
    r = {}
    with _server(folder) as port, sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            url = f"http://127.0.0.1:{port}/{page_path}?ui=c#run={SMALL}"
            page = _open(browser, url, **DESKTOP)
            page.wait_for_selector(".r-legend-acc", timeout=WAIT)
            r["desktop"] = page.evaluate(LEGEND)
            page.click(".r-legend-acc .ac-hint")
            page.wait_for_selector(".r-legend-box .ac-help", timeout=WAIT)
            r["help"] = page.evaluate("""() => { const box = document.querySelector('.r-legend-box'), help = box.querySelector('.ac-help');
                return [[...help.querySelectorAll('.ac-key-row b')].map((b) => b.textContent), help.querySelector('p').textContent.slice(0, 40),
                        box.querySelector('.ac-hint').getAttribute('aria-expanded'),
                        !!(box.querySelector('.r-legend-acc').compareDocumentPosition(help) & 4)]; }""")
            page.close()
            phone = _open(browser, url, **PHONE)
            phone.wait_for_selector(".u-sheet .r-legend-acc", state="attached", timeout=WAIT)
            r["phone"] = phone.evaluate(LEGEND)
            phone.evaluate("() => { const m = window.FINDALINE_RESULT.model; m.select(m.groups[0]); }")
            phone.wait_for_selector(".u-sheet .r-summary .r-legend-acc", state="attached", timeout=WAIT)
            r["phoneSelected"] = phone.evaluate(LEGEND)
            phone.close()
        finally:
            browser.close()
    states = [["ac ac-2", "easy access"], ["ac ac-1", "cannot tell"], ["ac ac-0", "hard access"]]
    for name in ("desktop", "phone", "phoneSelected"):
        found = r[name]
        assert found["count"] == 1 and found["label"] == "Anchors" and found["states"] == states, (name, found)
        assert found["hint"] == ["About reaching the anchors", "false", "?"], (name, found)
        assert found["hintWithLast"] and found["fits"], (name, found)
        assert found["beforeFilters"] and found["beforeList"], (name, found)
        assert found["scroll"][0] <= found["scroll"][1], (name, found)
    assert r["desktop"]["inHead"] and r["desktop"]["inSummary"] and r["desktop"]["colours"] == 1, r["desktop"]
    assert r["desktop"]["lines"] <= 2 and r["phone"]["lines"] <= 2, r  # the last state takes its "?" with it
    # a phone, nothing selected: the row alone above the filters (no summary's legend there)
    assert r["phone"]["inSheet"] and not r["phone"]["inSummary"] and r["phone"]["colours"] == 0, r["phone"]
    assert r["phoneSelected"]["inSheet"] and r["phoneSelected"]["inSummary"] and r["phoneSelected"]["colours"] == 1
    assert r["help"] == [["easy access:", "cannot tell:", "hard access:"], "The site judges from the terrain if you ",
                         "true", True], r["help"]


MARKS = """() => [...document.querySelectorAll('.leaflet-marker-pane .ac-map-icon')].map((icon) => {
  const svg = icon.querySelector('svg'), r = icon.getBoundingClientRect(), x = r.left + r.width / 2, y = r.top + r.height / 2;
  const hit = document.elementFromPoint(x, y);
  return {cls: svg.getAttribute('class'), label: svg.getAttribute('aria-label'), size: [Math.round(r.width), Math.round(r.height)],
          events: [getComputedStyle(icon).pointerEvents, getComputedStyle(svg).pointerEvents],
          under: hit ? hit.tagName : null, inIcon: !!(hit && hit.closest('.ac-map-icon')), x, y}; })"""
SELECTED = "() => { const s = window.FINDALINE_RESULT.model.selected; return s ? [s.line.access1 ?? null, s.line.access2 ?? null] : null; }"


def test_map_marks_of_the_selected_line(tmp_path, marked_clip):
    """The selected line's two anchors on the map are the mark (24 px, the state's class and name, anchor 1 then
    anchor 2): made by a selection, made again for another one (never more than two), gone when the selection ends;
    they take no pointer events (the map's canvas lies under their centres: a click there goes to the map, and the
    page goes on working)."""
    from playwright.sync_api import sync_playwright
    folder, page_path = _data(tmp_path, marked_clip)
    r = {}
    with _server(folder) as port, sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _open(browser, f"http://127.0.0.1:{port}/{page_path}?ui=c#run={SMALL}", **DESKTOP)
            marks = "() => document.querySelectorAll('.ac-map-icon').length === %d"
            r["start"] = page.evaluate(MARKS)
            page.click(".r-rows .r-row")
            page.wait_for_function(marks % 2, timeout=WAIT)
            r["first"] = [page.evaluate(SELECTED), page.evaluate(MARKS)]
            at = r["first"][1][0]
            page.mouse.click(at["x"], at["y"])  # at a mark's centre: the map takes it (its line, or a choice of spots)
            page.keyboard.press("Escape")       # a choice of spots closed, if one opened
            page.evaluate("() => window.FINDALINE_RESULT.model.select(null)")
            page.wait_for_function(marks % 0, timeout=WAIT)
            r["ended"] = page.evaluate(MARKS)
            for k in (2, 3, 4):  # three more spots, one after another
                page.click(f".r-rows .r-spot:nth-child({k}) > .r-row")
                page.wait_for_function(f"() => {{ const m = window.FINDALINE_RESULT.model; return m.selected && m.selected.group === m.rows[{k - 1}].group; }}",
                                       timeout=WAIT)
            page.wait_for_function(marks % 2, timeout=WAIT)
            r["later"] = [page.evaluate(SELECTED), page.evaluate(MARKS)]
            r["csp"] = page.evaluate("() => window.CSP_VIOLATIONS || []")
            page.close()
        finally:
            browser.close()
    assert r["start"] == [] and r["ended"] == [], r
    for name in ("first", "later"):
        (a1, a2), found = r[name]
        assert [(m["cls"], m["label"]) for m in found] == [(f"ac-map ac-{a1}", f"Anchor 1: {WORDS[a1]}"),
                                                           (f"ac-map ac-{a2}", f"Anchor 2: {WORDS[a2]}")], (name, r[name])
        assert all(m["size"] == [24, 24] and m["events"] == ["none", "none"] for m in found), (name, found)
        assert all(m["under"] == "CANVAS" and not m["inIcon"] for m in found), (name, found)
    assert r["csp"] == [], r


def test_run_without_the_mark_draws_none_of_it(tmp_path, plain_clip):
    """A run made without --access: no column (the list's six cells of before), no legend's row, no block in a
    selected line's details, no pair in a phone's head, and the selected line's anchors are not the mark (the map
    draws its white dots on the canvas, as before)."""
    from playwright.sync_api import sync_playwright
    folder, page_path = _data(tmp_path, plain_clip)
    r = {}
    with _server(folder) as port, sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            url = f"http://127.0.0.1:{port}/{page_path}?ui=c#run={SMALL}"
            page = _open(browser, url, **DESKTOP)
            r["list"] = page.evaluate(LIST)
            page.click(".r-rows .r-row")
            page.wait_for_selector(".c-col-details .r-acts", timeout=WAIT)
            r["selected"] = page.evaluate("""() => [window.FINDALINE_RESULT.model.selected.line.access1 ?? null,
                document.querySelectorAll('.r-acc').length, document.querySelectorAll('.ac-map-icon').length,
                document.querySelectorAll('svg.ac, .ac-none, .ac-hint, .r-legend-acc').length]""")
            page.close()
            phone = _open(browser, url, **PHONE)
            phone.evaluate("() => { const m = window.FINDALINE_RESULT.model; m.select(m.groups[0]); }")
            phone.wait_for_selector(".u-sheet .r-dtitle", state="attached", timeout=WAIT)
            r["phone"] = phone.evaluate("() => document.querySelectorAll('svg.ac, .ac-none, .ac-hint, .r-legend-acc, .r-acc').length")
            phone.close()
        finally:
            browser.close()
    found = r["list"]
    assert found["classes"] == ["r-table"] and not found["hasAccess"] and not found["legend"], found
    assert [h[1] for h in found["head"]][1:-1] == ["Length", "Mean height", "Clear.", "Lines"], found["head"]
    assert all(row["dots"] is None and row["cells"] == 6 and row["line"] == [None, None] for row in found["rows"]), found
    assert r["selected"] == [None, 0, 0, 0] and r["phone"] == 0, r


CELL_REQUEST = {"params": {"min_length": 20, "max_length": 100, "max_anchor_diff_m": 10, "resolution": 2.0,
                           "model": "sag", "end_zone": 5},
                "geometry": {"type": "Polygon", "coordinates": [[[19.75, 50.15], [19.76, 50.15], [19.76, 50.16],
                                                                 [19.75, 50.16], [19.75, 50.15]]]}}


def test_search_a_cell_opens_with_the_mark_on(tmp_path):
    """"Search a cell" of the highline layer (#new&cell=…: the cell's request has no access mark) opens in Advanced
    with the mark on (the user's word of 2026-11-16): the field ticked without a dot, the request carrying
    `access: true`; "Edit & run again" of a search stored without the mark keeps it off (with a dot)."""
    from playwright.sync_api import sync_playwright
    from jobs import Jobs
    _search_page(tmp_path, "", folder_name="basictest")
    old = Jobs(str(tmp_path)).add(CELL_REQUEST, "old", None)
    state = """() => { const s = window.FINDALINE_SEARCH;
        return [s.tab, s.values.access ?? null, s.differs('access'), typeof s.request === 'string' ? s.request : s.request.params.access ?? null,
                document.querySelector('.c-subtitle').textContent, s.values.resolution]; }"""
    r = {}
    with _server(tmp_path) as port, sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            context = browser.new_context(viewport={"width": 1280, "height": 900})
            asked = []

            def answer(route):
                asked.append(route.request.url)
                route.fulfill(status=200, content_type="application/json", body=json.dumps(CELL_REQUEST))
            context.route("**/api/countries/*/request*", answer)
            page = _basic_page(tmp_path, port, context, "#new&cell=slovakia:S:8:3:4")
            page.wait_for_function("() => !!window.FINDALINE_SEARCH", timeout=WAIT)
            r["cell"] = page.evaluate(state)
            # its field under More settings, Anchors: ticked, no dot
            page.click(".s-more-head")
            page.click(".s-topic[data-topic=anchors] > summary")
            page.wait_for_selector(".s-pane [data-field=access] input", timeout=WAIT)
            r["field"] = page.evaluate("""() => { const box = document.querySelector('.s-pane [data-field=access]');
                return [box.querySelector('input').checked, box.classList.contains('s-is-changed')]; }""")
            page.close()
            page = _basic_page(tmp_path, port, context, f"#new&edit={old}")
            page.wait_for_function("() => !!window.FINDALINE_SEARCH", timeout=WAIT)
            r["edit"] = page.evaluate(state)
            page.close()
            # an address with both (made by hand): the stored search as stored, the cell's default not applied
            page = _basic_page(tmp_path, port, context, f"#new&edit={old}&cell=slovakia:S:8:3:4")
            page.wait_for_function("() => !!window.FINDALINE_SEARCH", timeout=WAIT)
            r["both"] = page.evaluate(state)
            r["asked"] = asked
        finally:
            browser.close()
    assert len(r["asked"]) == 1 and "band=S" in r["asked"][0] and "level=8" in r["asked"][0], r
    assert r["cell"] == ["advanced", True, False, True, "Search a cell", 2], r
    assert r["field"] == [True, False], r
    assert r["edit"] == ["advanced", None, True, None, "Edit & run again", 2], r
    assert r["both"] == r["edit"], r


SKIPPED_NOTE = ["warning", "The anchors' access will not be marked: this search's area is too wide for it (about 7.7 GiB of "
                "memory needed, 4.6 GiB here). The search itself is not affected.",
                {"code": "access_skipped", "params": {"need": 7.7, "have": 4.6}}]


def test_receipt_of_a_search_too_wide_for_the_mark(tmp_path):
    """An estimate whose messages carry the code "access_skipped" (the area too wide for the access grid: the search
    runs without the mark): the receipt's part reads "access not marked: area too wide" on a desktop, "access not
    marked" on a phone, still opens the field in Advanced (ticked: the request asks for the mark as before), and the
    note counts among the estimate's warnings; without the code the part reads "access marked"."""
    from playwright.sync_api import sync_playwright
    from test_web import POINT_JS, SEARCH_STUBS, _ready
    stubs = SEARCH_STUBS.replace("messages: []", "messages: window.TEST_MESSAGES || []")
    assert stubs != SEARCH_STUBS
    _search_page(tmp_path, "", stubs=stubs, folder_name="basictest")
    receipt = """() => [document.querySelector('.s-receipt').innerText, document.querySelector('.s-bar-line')?.textContent ?? '',
                       window.FINDALINE_SEARCH.request.params.access]"""
    wide = {"viewport": {"width": 1280, "height": 900}}
    r = {}
    with _server(tmp_path) as port, sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            for name, messages, context in (("desktop", [SKIPPED_NOTE], wide), ("phone", [SKIPPED_NOTE], PHONE),
                                            ("marked", [["warning", "another note", {"code": "other_note", "params": {}}]], wide)):
                ctx = browser.new_context(**context)
                ctx.add_init_script(f"window.TEST_MESSAGES = {json.dumps(messages)};")
                page = _basic_page(tmp_path, port, ctx)
                page.evaluate(POINT_JS)
                _ready(page)
                if name == "phone":
                    page.click(".s-sum")
                    page.wait_for_function("() => getComputedStyle(document.querySelector('.s-receipt')).display !== 'none'",
                                           timeout=WAIT)
                r[name] = page.evaluate(receipt)
                if name == "desktop":  # the part still opens its field
                    page.click(".s-receipt button[data-field=access]")
                    page.wait_for_function("() => document.activeElement?.closest('[data-field=access]')", timeout=WAIT)
                    r["field"] = page.evaluate("() => [window.FINDALINE_SEARCH.tab, document.activeElement.checked]")
                ctx.close()
        finally:
            browser.close()
    assert r["desktop"][0].endswith("no A-frames · access not marked: area too wide"), r
    assert r["phone"][0].endswith("no A-frames · access not marked"), r
    assert r["marked"][0].endswith("no A-frames · access marked, no line filtered out"), r
    assert all("1 warning(s)" in r[name][1] and r[name][2] is True for name in ("desktop", "phone", "marked")), r
    assert r["field"] == ["advanced", True], r


def test_run_whose_mark_was_left_out(tmp_path, plain_clip):
    """A run whose head says the mark was asked for and left out (`access_skipped`: the search area too wide): one
    muted line "Anchors' access not marked: the search area was too wide." where the legend's row of the mark
    stands (a desktop: the list's head, under the colours' legend; a phone: above the filters, also while nothing is
    selected), and nothing else of the mark: no "?", no column, no block, no marks on the map."""
    from playwright.sync_api import sync_playwright
    from test_web import store_with
    folder, page_path = _data(tmp_path, plain_clip)
    store_with(folder / "runs" / SMALL, head={"access_skipped": "memory"})  # the store's head the page reads
    state = """() => { const $ = (s) => document.querySelector(s), $$ = (s) => [...document.querySelectorAll(s)];
        const lines = $$('.r-acc-skipped').filter((e) => e.getClientRects().length), line = lines[0];
        const filters = $('.r-filters'), colours = $$('.r-legend').filter((e) => e.getClientRects().length)[0];
        return {key: window.FINDALINE_RESULT.model.data.access_skipped, count: lines.length, text: line && line.textContent,
                beforeFilters: !!(line && filters && (line.compareDocumentPosition(filters) & 4)),
                afterColours: !!(line && colours && (colours.compareDocumentPosition(line) & 4)),
                inHead: !!(line && line.closest('.c-col-head')), inSheet: !!(line && line.closest('.u-sheet-body')),
                mark: $$('svg.ac, .ac-none, .ac-hint, .r-legend-acc, .r-acc, .r-cell-acc, .ac-map-icon').length,
                table: $('.r-table').className}; }"""
    r = {}
    with _server(folder) as port, sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            url = f"http://127.0.0.1:{port}/{page_path}?ui=c#run={SMALL}"
            page = _open(browser, url, **DESKTOP)
            page.wait_for_selector(".r-acc-skipped", timeout=WAIT)
            r["desktop"] = page.evaluate(state)
            page.click(".r-rows .r-row")
            page.wait_for_selector(".c-col-details .r-acts", timeout=WAIT)
            r["selected"] = page.evaluate(state)
            page.close()
            phone = _open(browser, url, **PHONE)
            phone.wait_for_selector(".u-sheet .r-acc-skipped", state="attached", timeout=WAIT)
            r["phone"] = phone.evaluate(state)
            phone.evaluate("() => { const m = window.FINDALINE_RESULT.model; m.select(m.groups[0]); }")
            phone.wait_for_selector(".u-sheet .r-summary .r-acc-skipped", state="attached", timeout=WAIT)
            r["phoneSelected"] = phone.evaluate(state)
            phone.close()
        finally:
            browser.close()
    for name, found in r.items():
        assert found["key"] == "memory" and found["count"] == 1, (name, found)
        assert found["text"] == "Anchors' access not marked: the search area was too wide.", (name, found)
        assert found["beforeFilters"] and found["mark"] == 0 and found["table"] == "r-table", (name, found)
    assert r["desktop"]["inHead"] and r["desktop"]["afterColours"] and r["selected"]["inHead"], r
    assert r["phone"]["inSheet"] and not r["phone"]["afterColours"], r["phone"]  # alone above the filters
    assert r["phoneSelected"]["inSheet"] and r["phoneSelected"]["afterColours"], r["phoneSelected"]


def test_a_real_search_too_wide_for_the_mark_on_the_page(tmp_path, monkeypatch):
    """The two halves together (the search side: tests/test_access_search.py): a search with --access whose memory
    cannot hold the access grid. Its real estimate (jobs.quick_estimate: the messages as the form gets them, the
    public site's wording too) turns the form's receipt into "access not marked: area too wide"; its real run (the
    key `access_skipped` in the store's head, which the page reads) shows the muted line and nothing else of the
    mark, on a desktop and a phone."""
    from datetime import datetime
    from playwright.sync_api import sync_playwright
    import jobs
    import runs as rn
    import search
    from params import SearchParams
    from test_access_search import LEFT, SIZE, TOP, scene
    from test_offline import OFFLINE_ENV, write_raster
    from test_web import POINT_JS, SEARCH_STUBS, _ready
    for key, value in OFFLINE_ENV.items():
        monkeypatch.setenv(key, value)
    write_raster(tmp_path / "wide.tif", scene(), LEFT, TOP)
    values = dict(elevation_file=str(tmp_path / "wide.tif"), northing=TOP - SIZE / 2, easting=LEFT + SIZE / 2, radius=135,
                  resolution=1, nmpt="off", water="off", fill_gaps="off", min_length=10, max_length=80,
                  slope_threshold=60, prominence_span=10, drop_radius=10, ortho="never")
    # the estimate of the request, as the form's quick lane answers it: locally and on the public site
    monkeypatch.setattr(jobs, "SLOT_MEMORY", 10_000)
    estimates = {}
    for public in (False, True):
        monkeypatch.setattr(jobs, "PUBLIC_TEXTS", public)
        os.makedirs(tmp_path / "est", exist_ok=True)
        estimates[public] = jobs.quick_estimate(str(tmp_path / "est"), {"params": {**values, "access": True}})["messages"]
    assert all(any(len(m) == 3 and m[2]["code"] == "access_skipped" for m in found) for found in estimates.values())
    # the two shapes of the note's info: locally its params, on the public site the public reading's key and no params
    noted = {public: next(m for m in found if len(m) == 3 and m[2]["code"] == "access_skipped") for public, found in estimates.items()}
    assert set(noted[False][2]["params"]) == {"need", "have"} and "key" not in noted[False][2] and "GiB" in noted[False][1]
    assert noted[True][2] == {"code": "access_skipped", "key": "error.access_skipped_public", "params": {}}
    assert "GiB" not in noted[True][1], noted[True]
    # the run of the same search with too little memory for the access grid
    monkeypatch.setattr(search, "available_memory", lambda: 10_000)
    data = tmp_path / "data"
    paths = search.Paths(str(data), str(data / "work"))
    os.makedirs(paths.work)
    plan = search.plan_search(SearchParams(**values, access=True, name="Too wide"), paths, lambda kind, text: None)
    assert plan.access_skipped == "memory"
    lines, _ = search.search_lines(plan)
    run_id = "2026-11-16_120000_Too-wide_00000000000000d1"
    folder = data / "runs" / run_id
    folder.mkdir(parents=True)
    search.save_run(plan, lines, {"id": run_id, "path": str(folder), "created": datetime(2026, 11, 16, 12), "name": "Too wide"})
    rn.write_index(str(data / "runs"))
    assert json.loads((folder / "run.json").read_text("utf-8")).get("store"), "the page reads the store's head"
    page_path = stub_page(data, "accesstest")
    stubs = SEARCH_STUBS.replace("messages: []", "messages: window.TEST_MESSAGES || []")
    _search_page(tmp_path, "", stubs=stubs, folder_name="basictest")
    result = """() => { const $$ = (s) => [...document.querySelectorAll(s)], lines = $$('.r-acc-skipped').filter((e) => e.getClientRects().length);
        return [window.FINDALINE_RESULT.model.data.access_skipped, window.FINDALINE_RESULT.model.count > 20, lines.map((e) => e.textContent),
                $$('svg.ac, .ac-none, .ac-hint, .r-legend-acc, .r-acc, .r-cell-acc, .ac-map-icon').length]; }"""
    r = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            with _server(tmp_path) as port:
                for public, messages in estimates.items():
                    ctx = browser.new_context(viewport={"width": 1280, "height": 900})
                    ctx.add_init_script(f"window.TEST_MESSAGES = {json.dumps(messages)};")
                    page = _basic_page(tmp_path, port, ctx)
                    page.evaluate(POINT_JS)
                    _ready(page)
                    r[f"receipt-{public}"] = page.evaluate("() => document.querySelector('.s-receipt').innerText")
                    ctx.close()
            with _server(data) as port:
                url = f"http://127.0.0.1:{port}/{page_path}?ui=c#run={run_id}"
                for name, context in (("desktop", DESKTOP), ("phone", PHONE)):
                    page = _open(browser, url, **context)
                    page.wait_for_selector(".r-acc-skipped", state="attached", timeout=WAIT)
                    r[name] = page.evaluate(result)
                    page.evaluate("() => { const m = window.FINDALINE_RESULT.model; m.select(m.groups[0]); }")
                    page.wait_for_selector(".r-dtitle", state="attached", timeout=WAIT)
                    r[name + "-selected"] = page.evaluate(result)
                    page.close()
        finally:
            browser.close()
    assert r["receipt-False"].endswith("access not marked: area too wide") and r["receipt-True"] == r["receipt-False"], r
    line = ["Anchors' access not marked: the search area was too wide."]
    for name in ("desktop", "desktop-selected", "phone", "phone-selected"):
        assert r[name] == ["memory", True, line, 0], (name, r[name])
