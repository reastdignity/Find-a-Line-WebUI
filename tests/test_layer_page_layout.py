"""The highline layer's page (#layer of C; viewer/src/app/c/LayerPage.tsx, LayerHistograms.tsx, c.css) on a desktop
and on phones in Playwright's Edge, on the real local server over test_country_web's two sample cubes (the app's page
with test_shell_c's stubs, as test_layer_hints_by_pointer serves it): the user's picks of step 3c, group C
(2026-11-19). L3: a chart with 32 px or more of its width per bar shows each bar's count and every tick, a narrower
one no counts and every other tick; two charts a row on a desktop with the length chart across both; a phone's
enlarged chart has its counts. L5: the panels' default widths are 340 and 485 px, a kept layout of version 1 gives
up that version's defaults and keeps a dragged width. L4: on a phone 600 px high or more the map stays at the top of
the scrolling column, held sideways it scrolls away. Every wait is an event with a deadline; a finger's taps keep
test_shell_c_view_map's spacing (_tap_on)."""

import json
import os

import pytest

from test_shell_c_view_map import _tap_on
from test_web import EDGE, WAIT, _playwright, _server

pytestmark = pytest.mark.skipif(not os.path.exists(EDGE) or not _playwright(),
                                reason="needs Microsoft Edge and Playwright (group ui)")

TOUCH = {"device_scale_factor": 3, "is_mobile": True, "has_touch": True}
SMALL_PHONE = {"viewport": {"width": 390, "height": 664}, **TOUCH}  # tools/ui_shots.py's iPhone: the least room
SIDE_PHONE = {"viewport": {"width": 667, "height": 375}, **TOUCH}  # a phone on its side: the narrow frame, under 600 px high
DESKTOP = {"viewport": {"width": 1400, "height": 900}}
LAYOUT_KEY = "findaline.layer.layout"  # result/view/layout.ts LAYER_LAYOUT_KEY
PER_BAR = 32  # px of a chart's width per bar from which its counts and every tick show (c.css; the pick L3 b)
CHARTS = 16  # the sample cube's charts (test_country_web.test_layer_page_in_edge)

# The page drawn from its last answers: every chart there, none dimmed, the total written (no pick changes these)
SETTLED = ("() => document.querySelectorAll('.c-layer-hist').length === %d && !document.querySelector('.c-layer-waiting') "
           "&& /in view/.test(document.querySelector('.c-layer-total')?.textContent || '')" % CHARTS)
# Every chart: its name, its bars (data-bars and the bars drawn), its content box's width (the open chart of a desktop
# has a padding), its box, its bars' counts shown (computed display), its ticks hidden (one digit per tick), and the
# counts and ticks whose text is wider than their box where they show
CHARTS_JS = """() => [...document.querySelectorAll('.c-layer-hist')].map((h) => {
  const cs = getComputedStyle(h), r = h.getBoundingClientRect();
  const counts = [...h.querySelectorAll('.c-layer-bar-n')], ticks = [...h.querySelectorAll('.c-layer-hist-axis span')];
  const shown = (e) => getComputedStyle(e).display !== 'none' && getComputedStyle(e).visibility !== 'hidden';
  const cut = (list) => list.filter((e) => shown(e) && e.scrollWidth > e.clientWidth + 1).map((e) => [e.textContent, e.scrollWidth, e.clientWidth]);
  return {name: h.dataset.hist, bars: Number(h.dataset.bars), drawn: h.querySelectorAll('.c-layer-bar').length,
          width: r.width - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight) - parseFloat(cs.borderLeftWidth) - parseFloat(cs.borderRightWidth),
          box: [r.left, r.top, r.width, r.height], open: h.classList.contains('c-layer-hist-open'),
          container: cs.containerName, counts: counts.length, shown: counts.filter((n) => getComputedStyle(n).display !== 'none').length,
          withText: counts.filter((n) => n.textContent).length,
          fonts: [...new Set(counts.concat(ticks).filter(shown).map((e) => getComputedStyle(e).fontSize))],
          hidden: ticks.map((t) => getComputedStyle(t).visibility === 'hidden' ? '1' : '0').join(''),
          cutCounts: cut(counts), cutTicks: cut(ticks)};
})"""
# The charts' grids (a desktop): each topic's columns and its content's width
GRIDS_JS = """() => [...document.querySelectorAll('.c-layer-charts')].map((g) =>
  ({columns: getComputedStyle(g).gridTemplateColumns.split(' ').length, width: g.getBoundingClientRect().width,
    charts: [...g.querySelectorAll(':scope > .c-layer-hist')].map((h) => h.dataset.hist)}))"""
# The panels' and the map's widths, the frame, the kept layout
PANELS_JS = """(key) => { const w = (s) => { const e = document.querySelector(s); return e ? e.getBoundingClientRect().width : null; };
  return {left: w('.c-mappage-3 > .c-col-left'), right: w('.c-mappage-3 > .c-col-right'), map: w('.c-mappage-3 > .c-newmap'),
          rails: document.querySelectorAll('.c-mappage-3 .c-rail').length, narrow: !!document.querySelector('.ui.c-narrow'),
          kept: localStorage.getItem(key), window: innerWidth}; }"""
# The phone's column and its map: how far it is scrolled and may be, the map's box against the column's, what lies
# at the map's centre
MAP_JS = """() => { const column = document.querySelector('.c-mappage-3'), map = column.querySelector(':scope > .c-newmap');
  const m = map.getBoundingClientRect(), c = column.getBoundingClientRect();
  const at = document.elementFromPoint((m.left + m.right) / 2, (m.top + m.bottom) / 2);
  return {scrolled: column.scrollTop, room: column.scrollHeight - column.clientHeight, top: m.top - c.top, height: m.height,
          bottom: m.bottom, columnTop: c.top, mapAtCentre: !!at && !!at.closest('.c-newmap'),
          position: getComputedStyle(map).position, padding: getComputedStyle(column).scrollPaddingTop,
          narrow: !!document.querySelector('.ui.c-narrow'), window: [innerWidth, innerHeight]}; }"""


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    """A data folder with test_country_web's two sample cubes on a real server, the app's page with the stubs in it,
    and Playwright's Edge: (browser, the address of #layer)."""
    from playwright.sync_api import sync_playwright
    from test_country_web import OUTLINE2, sample_cube
    from test_shell_c import stub_page
    data = tmp_path_factory.mktemp("layer")
    sample_cube(data)
    sample_cube(data, "testland", "Testland", seed=3, outline=OUTLINE2, neighbours=("slovakia",))
    path = stub_page(data, "layerlayout")
    with _server(data) as port, sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            yield browser, f"http://127.0.0.1:{port}/{path}?ui=c#layer"
        finally:
            browser.close()


def _page(site, context: dict, kept: dict | None = None):
    """#layer in a fresh browser context of `context` (an empty localStorage, or `kept` as the layer's kept layout
    before the page's scripts run), settled: its sixteen charts drawn from the answers."""
    browser, url = site
    ctx = browser.new_context(**context)
    if kept is not None:
        ctx.add_init_script("try { localStorage.setItem(%s, %s); } catch (e) {}" % (json.dumps(LAYOUT_KEY), json.dumps(json.dumps(kept))))
    page = ctx.new_page()
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)[:300]))
    page.goto(url)
    page.wait_for_function(SETTLED, timeout=2 * WAIT)
    return page


def _numbers_rule(chart: dict) -> list:
    """What is wrong with a chart's counts and ticks by the rule of 32 px a bar ([] when nothing): at PER_BAR px or
    more of its content's width per bar every bar's count shows and no tick is hidden; under it no count shows and
    every even tick is hidden, every odd one shown."""
    wrong, ticks = [], chart["hidden"]
    if chart["bars"] != chart["drawn"] or chart["counts"] != chart["bars"] or not 2 <= chart["bars"] <= 16:
        wrong.append("bars")
    if chart["width"] >= PER_BAR * chart["bars"]:
        if chart["shown"] != chart["counts"]:
            wrong.append("counts hidden in a wide chart")
        if "1" in ticks:
            wrong.append("a tick hidden in a wide chart")
    else:
        if chart["shown"]:
            wrong.append("counts shown in a narrow chart")
        if ticks != "".join("01"[k % 2] for k in range(len(ticks))):
            wrong.append("not every other tick in a narrow chart")
    return wrong


def _open_chart(page, name: str):
    """A phone's chart enlarged by a finger's tap on its name (brought under the sticky map first); waits for it."""
    page.evaluate("(name) => document.querySelector(`.c-layer-hist[data-hist=${name}]`).scrollIntoView({block: 'center', inline: 'center'})", name)
    _tap_on(page, f".c-layer-hist[data-hist={name}] .c-layer-hist-name")
    page.wait_for_function("(name) => document.querySelector(`.c-layer-hist[data-hist=${name}]`).classList.contains('c-layer-hist-open')",
                           arg=name, timeout=WAIT)


def test_charts_on_a_desktop(site):
    """L3 on a desktop (1400 x 900, the default layout): each chart says how many bars it has (data-bars) and is a
    container of its own; the charts stand two a row (each topic's grid has two columns, a pair shares its top) and
    the length chart lies across both; a chart with 32 px or more of its width per bar shows every bar's count and
    every tick (the six-bar charts and the length chart), a narrower one no count and every other tick (the
    seven-bar charts: 212.5 px of the 224 they would need), all at 12 px."""
    page = _page(site, DESKTOP)
    charts = {c["name"]: c for c in page.evaluate(CHARTS_JS)}
    grids = page.evaluate(GRIDS_JS)
    assert len(charts) == CHARTS and "length" in charts, list(charts)
    assert all(c["container"] == "layer-hist" for c in charts.values()), charts
    # two a row, the length chart across both
    assert grids and all(g["columns"] == 2 for g in grids), grids
    length, first = charts["length"], next(g for g in grids if "length" in g["charts"])
    assert abs(length["width"] - first["width"]) <= 1, (length, first)
    assert first["charts"][:3] == ["length", "clearance", "height"], first
    left, right = charts["clearance"], charts["height"]
    assert left["box"][1] == right["box"][1] > length["box"][1] and right["box"][0] >= left["box"][0] + left["box"][2], (left, right)
    assert abs(left["width"] - right["width"]) <= 0.5 and length["width"] >= 2 * left["width"], (length, left, right)
    # the counts and the ticks by the chart's width per bar
    wrong = {name: (_numbers_rule(c), c) for name, c in charts.items() if _numbers_rule(c)}
    assert not wrong, wrong
    wide = [name for name, c in charts.items() if c["shown"]]
    narrow = [name for name, c in charts.items() if not c["shown"]]
    assert "length" in wide and len(wide) >= 2 and narrow, (wide, narrow)  # both sides of the rule are on the page
    # no chart stands within a pixel of its threshold (the rule is read from a width measured here)
    assert all(abs(c["width"] - PER_BAR * c["bars"]) > 1 for c in charts.values()), charts
    assert all(c["fonts"] == ["12px"] for c in charts.values()), {n: c["fonts"] for n, c in charts.items()}
    assert any(c["withText"] for c in charts.values()), charts  # the bars have counts to show
    assert page.errors == [], page.errors
    page.context.close()


def test_chart_numbers_fit_their_bars(site):
    """Where a chart shows its counts (32 px a bar or more), no count and no tick is wider than its box: on a
    desktop's default panel and in a phone's enlarged charts (the length chart and a six-bar one)."""
    cut = {}
    page = _page(site, DESKTOP)
    shown = [c for c in page.evaluate(CHARTS_JS) if c["shown"]]
    assert len(shown) >= 2 and any(c["withText"] for c in shown), shown
    cut["desktop"] = [(c["name"], c["cutCounts"], c["cutTicks"]) for c in shown if c["cutCounts"] or c["cutTicks"]]
    page.context.close()
    page = _page(site, SMALL_PHONE)
    for name in ("length", "clearance"):
        _open_chart(page, name)
        chart = next(c for c in page.evaluate(CHARTS_JS) if c["name"] == name)
        assert chart["open"] and chart["shown"] == chart["counts"], chart
        if chart["cutCounts"] or chart["cutTicks"]:
            cut["phone", name] = (chart["cutCounts"], chart["cutTicks"])
    page.context.close()
    assert cut == {"desktop": []}, cut


def test_charts_on_a_phone(site):
    """L3 on a phone (390 x 664, touch): the strips' small charts (148 px, the length chart 236 px: under 32 px a
    bar) show no count and every other tick; a tap on a chart's name enlarges it (272 px, the length chart 300 px),
    and the enlarged chart alone shows its counts and every tick; the others stay as they were."""
    page = _page(site, SMALL_PHONE)
    assert page.evaluate(PANELS_JS, LAYOUT_KEY)["narrow"]
    small = {c["name"]: c for c in page.evaluate(CHARTS_JS)}
    assert len(small) == CHARTS and not any(c["open"] for c in small.values()), small
    for name, chart in small.items():
        assert chart["width"] == (236 if name == "length" else 148), chart
        assert chart["shown"] == 0 and not _numbers_rule(chart), (chart, _numbers_rule(chart))
    for name, width in (("clearance", 272), ("length", 300)):
        _open_chart(page, name)
        charts = {c["name"]: c for c in page.evaluate(CHARTS_JS)}
        assert [n for n, c in charts.items() if c["open"]] == [name], charts
        opened = charts[name]
        assert opened["width"] == width and opened["width"] >= PER_BAR * opened["bars"], opened
        assert opened["shown"] == opened["counts"] == opened["bars"] and "1" not in opened["hidden"], opened
        assert opened["fonts"] == ["12px"] and not _numbers_rule(opened), opened
        for other, chart in charts.items():
            if other != name:
                assert chart["shown"] == 0 and chart["width"] == small[other]["width"] and not _numbers_rule(chart), chart
    assert page.errors == [], page.errors
    page.context.close()


def test_default_panel_widths(site):
    """L5 on a desktop (1400 x 900): with nothing kept the left panel is 340 px and the right 485 px, the map between
    them at least 570 px (575); a kept layout of version 1 with that version's defaults (400 and 620) gives the same;
    one of version 1 with dragged widths (450 and 520) keeps them, so the kept value is read; one of version 2 with
    400 and 620 keeps them as the user's."""
    cases = {"empty": None,
             "old defaults": {"v": 1, "left": {"w": 400, "open": True}, "right": {"w": 620, "open": True}},
             "old dragged": {"v": 1, "left": {"w": 450, "open": True}, "right": {"w": 520, "open": True}},
             "new dragged": {"v": 2, "left": {"w": 400, "open": True}, "right": {"w": 620, "open": True}}}
    found = {}
    for name, kept in cases.items():
        page = _page(site, DESKTOP, kept)
        found[name] = page.evaluate(PANELS_JS, LAYOUT_KEY)
        assert page.errors == [], (name, page.errors)
        page.context.close()
    widths = {name: (f["left"], f["right"], f["map"]) for name, f in found.items()}
    assert all(f["window"] == 1400 and not f["narrow"] and f["rails"] == 0 for f in found.values()), found
    assert found["empty"]["kept"] is None, found["empty"]
    assert widths["empty"] == (340, 485, 575), widths
    assert widths["empty"][2] >= 570, widths
    assert found["old defaults"]["kept"] is not None, found["old defaults"]  # the page had a kept value to read
    assert widths["old defaults"] == (340, 485, 575), widths
    assert widths["old dragged"] == (450, 520, 430), widths
    assert widths["new dragged"] == (400, 620, 380), widths


def test_map_stays_on_a_phone(site):
    """L4: on a phone 600 px high or more (390 x 664) the map is sticky at the top of the scrolling column: with the
    column scrolled to its end the map's top is still the column's and the map lies over the panel (it is what is at
    its own centre), and what is scrolled into view stops under it (scroll-padding: its 34vh); on a phone held
    sideways (667 x 375) it is not sticky and moves up with the column."""
    page = _page(site, SMALL_PHONE)
    before = page.evaluate(MAP_JS)
    assert before["narrow"] and before["window"] == [390, 664], before
    assert before["scrolled"] == 0 and abs(before["top"]) <= 1 and before["room"] > 600, before
    page.evaluate("() => { const column = document.querySelector('.c-mappage-3'); column.scrollTop = column.scrollHeight; }")
    page.wait_for_function("() => { const c = document.querySelector('.c-mappage-3'); "
                           "return c.scrollTop > 0 && c.scrollTop >= c.scrollHeight - c.clientHeight - 1; }", timeout=WAIT)
    end = page.evaluate(MAP_JS)
    assert end["scrolled"] > 600 and abs(end["top"]) <= 1, end
    assert end["mapAtCentre"] and end["position"] == "sticky", end
    assert abs(end["height"] - before["height"]) <= 0.5 and end["height"] > 200, (before, end)
    # the map's 34vh and 8 px, so that what is scrolled into view stands clear of the map's edge (c.css)
    assert abs(float(end["padding"].rstrip("px")) - (0.34 * 664 + 8)) <= 0.5, end
    assert page.errors == [], page.errors
    page.context.close()
    page = _page(site, SIDE_PHONE)
    before = page.evaluate(MAP_JS)
    assert before["narrow"] and before["window"] == [667, 375], before
    assert before["scrolled"] == 0 and abs(before["top"]) <= 1 and before["room"] > 300, before
    page.evaluate("() => { document.querySelector('.c-mappage-3').scrollTop = 300; }")
    page.wait_for_function("() => document.querySelector('.c-mappage-3').scrollTop === 300", timeout=WAIT)
    moved = page.evaluate(MAP_JS)
    assert abs(moved["top"] + 300) <= 1 and moved["bottom"] < moved["columnTop"], moved  # scrolled away whole
    assert moved["position"] != "sticky" and not moved["mapAtCentre"], moved
    assert page.errors == [], page.errors
    page.context.close()
