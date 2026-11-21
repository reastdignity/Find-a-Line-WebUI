"""The highline layer's page (#layer of C; viewer/src/app/c/LayerPage.tsx, LayerHistograms.tsx, c.css) on a desktop
and on phones in Playwright's Edge, on the real local server over test_country_web's two sample cubes (the app's page
with test_shell_c's stubs, as test_layer_hints_by_pointer serves it): the user's picks of step 3c, group C
(2026-11-19). L3: a chart with 32 px or more of its width per bar shows each bar's count and every tick, a narrower
one no counts and every other tick; two charts a row on a desktop with the length chart across both; a phone's
enlarged chart has its counts. L5: the panels' default widths are 340 and 485 px, a kept layout of version 1 gives
up that version's defaults and keeps a dragged width. L4: on a phone 600 px high or more the map stays at the top of
the scrolling column, held sideways it scrolls away.
The fix round (2026-11-20): a cell tapped on the phone's sticky map brings its card right under the map; the map is
sticky after a turn of the phone (no inline position from Leaflet); the collapse tab shows the keyboard's ring;
counts are parted by semicolons; the rails lead their counts with a colon and say "Expand the …" after their
label; a bar's accessible name is the count it writes, its range and count, and in a chart too narrow for its
counts a bar shows its own on the keyboard's focus; one container rule per count of bars from 1 to 24, a phone's
enlarged chart 32 px a bar; a chart whose filter is off for the cubes in view has no bar to pick.
Every wait is an event with a deadline; a finger's taps keep test_shell_c_view_map's spacing (_tap, _tap_on)."""

import json
import os
import re

import pytest

from test_shell_c_view_map import _tap, _tap_on
from test_web import EDGE, WAIT, _playwright, _server

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
C_CSS = os.path.join(REPO, "viewer", "src", "app", "c", "c.css")
TOUCH = {"device_scale_factor": 3, "is_mobile": True, "has_touch": True}
SMALL_PHONE = {"viewport": {"width": 390, "height": 664}, **TOUCH}  # tools/ui_shots.py's iPhone: the least room
SIDE_PHONE = {"viewport": {"width": 667, "height": 375}, **TOUCH}  # a phone on its side: the narrow frame, under 600 px high
KEYBOARD_PHONE = {"viewport": {"width": 390, "height": 664}}  # the phone's frame with a keyboard and no touch
DESKTOP = {"viewport": {"width": 1400, "height": 900}}
LAYOUT_KEY = "findaline.layer.layout"  # result/view/layout.ts LAYER_LAYOUT_KEY
PER_BAR = 32  # px of a chart's width per bar from which its counts and every tick show (c.css; the pick L3 b)
MOST_BARS = 24  # the most bars c.css has a rule for (one @container rule per count of bars from 1)
CHARTS = 16  # the sample cube's charts (test_country_web.test_layer_page_in_edge)
# The filters the sample cubes cannot answer (no surface model; counted without the A-frames): their selects are
# disabled (LayerPage.tsx filterOff)
OFF = ("clearance_trees", "lift_needed", "lift_no_zone")

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
# Three animation frames from now: the effects of the page's last render have run (Preact runs them after the next
# frame), and what they scrolled is in place
FRAMES_JS = "() => new Promise((done) => requestAnimationFrame(() => requestAnimationFrame(() => requestAnimationFrame(done))))"
# A point of the map as it stands, inside a whole cell of Slovakia's own (`cells`: an answer of /cells; not a cell the
# border cuts, not a partner's row), the nearest to the map's centre that is 30 px inside the map with the cells'
# canvas on top: {x, y, count} in the window's px
CELL_POINT_JS = """(cells) => { const map = window.FINDALINE_PLACE.map, box = map.getContainer().getBoundingClientRect(), size = map.getSize();
  let best = null;
  for (const r of cells.cells) {
    if (r[11] || cells.cut[r[0] + ',' + r[1]]) continue;
    const p = map.latLngToContainerPoint([(r[3] + r[5] + r[7] + r[9]) / 4, (r[4] + r[6] + r[8] + r[10]) / 4]);
    if (p.x < 30 || p.y < 30 || p.x > size.x - 30 || p.y > size.y - 30) continue;
    const at = document.elementFromPoint(box.left + p.x, box.top + p.y);
    if (!at || at.tagName !== 'CANVAS') continue;
    const d = Math.hypot(p.x - size.x / 2, p.y - size.y / 2);
    if (!best || d < best.d) best = {x: box.left + p.x, y: box.top + p.y, d, count: r[2]};
  }
  return best; }"""
# The scrolling column with the selected cell's card: how far it is scrolled, the map's box and position (computed,
# and written on the element), the card's top and words
COLUMN_JS = """() => { const column = document.querySelector('.c-mappage-3'), map = column.querySelector(':scope > .c-newmap'), m = map.getBoundingClientRect();
  const card = document.querySelector('.c-layer-cell');
  return {scrolled: column.scrollTop, room: column.scrollHeight - column.clientHeight, columnTop: column.getBoundingClientRect().top,
          mapTop: m.top, mapBottom: m.bottom, position: getComputedStyle(map).position, inline: map.style.position,
          cellTop: card ? card.getBoundingClientRect().top : null, card: card ? card.innerText : null,
          narrow: !!document.querySelector('.ui.c-narrow'), window: [innerWidth, innerHeight]}; }"""
# The kit's colours as the page computes them: {accent, surface} as "rgb(r, g, b)"
TOKENS_JS = """() => { const probe = document.createElement('span'), out = {}; document.querySelector('.c-mappage-3').appendChild(probe);
  for (const name of ['accent', 'surface']) { probe.style.color = `var(--${name})`; out[name] = getComputedStyle(probe).color; }
  probe.remove(); return out; }"""
# Every bar that can be picked: its chart, its accessible name (aria-label), its tooltip, its data-count, the count
# written in it, its value
BARS_JS = """() => [...document.querySelectorAll('button.c-layer-bar')].map((b) => ({hist: b.closest('.c-layer-hist').dataset.hist,
  label: b.getAttribute('aria-label'), title: b.title, count: b.dataset.count, written: b.querySelector('.c-layer-bar-n').textContent, value: Number(b.dataset.value)}))"""
# The heights of every chart's bars' fills, by chart
FILLS_JS = """() => Object.fromEntries([...document.querySelectorAll('.c-layer-hist')].map((h) =>
  [h.dataset.hist, [...h.querySelectorAll('.c-layer-bar-fill')].map((f) => f.getBoundingClientRect().height)]))"""
# The bar with the focus (null when the focus is elsewhere): its chart (enlarged?), its place among the chart's
# bars, its data-count, whether the keyboard's ring shows, whether the chart shows its counts, the label of its
# ::after (content, position, top), its fill's height
FOCUSED_BAR_JS = """() => { const b = document.activeElement; if (!b || !b.matches('button.c-layer-bar')) return null;
  const h = b.closest('.c-layer-hist'), after = getComputedStyle(b, '::after');
  return {hist: h.dataset.hist, open: h.classList.contains('c-layer-hist-open'), k: [...h.querySelectorAll('.c-layer-bar')].indexOf(b), count: b.dataset.count,
          visible: b.matches(':focus-visible'), counts: getComputedStyle(b.querySelector('.c-layer-bar-n')).display !== 'none',
          after: after.content, label: [after.position, after.top], fill: b.querySelector('.c-layer-bar-fill').getBoundingClientRect().height}; }"""


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    """A data folder with test_country_web's two sample cubes on a real server, the app's page with the stubs in it,
    and Playwright's Edge: (browser, the address of #layer). Without Edge or Playwright the tests that ask for it
    are skipped (the one that reads c.css alone runs everywhere)."""
    if not os.path.exists(EDGE) or not _playwright():
        pytest.skip("needs Microsoft Edge and Playwright (group ui)")
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
    before the page's scripts run), settled: its sixteen charts drawn from the answers. `page.cells` holds the
    answers of Slovakia's /cells as they came (_cell_point reads the last)."""
    browser, url = site
    ctx = browser.new_context(**context)
    if kept is not None:
        ctx.add_init_script("try { localStorage.setItem(%s, %s); } catch (e) {}" % (json.dumps(LAYOUT_KEY), json.dumps(json.dumps(kept))))
    page = ctx.new_page()
    page.errors, page.cells = [], []
    page.on("pageerror", lambda e: page.errors.append(str(e)[:300]))
    page.on("response", lambda r: page.cells.append(r) if "/api/countries/slovakia/cells" in r.url and r.ok else None)
    page.goto(url)
    page.wait_for_function(SETTLED, timeout=2 * WAIT)
    return page


def _numbers_rule(chart: dict) -> list:
    """What is wrong with a chart's counts and ticks by the rule of 32 px a bar ([] when nothing): at PER_BAR px or
    more of its content's width per bar every bar's count shows and no tick is hidden; under it no count shows and
    every even tick is hidden, every odd one shown. A chart has 1 to MOST_BARS bars: the counts c.css has a rule for
    (2 to 16 before the fix round, which wrote the rules for 1 and for 17 to 24:
    test_one_container_rule_per_count_of_bars)."""
    wrong, ticks = [], chart["hidden"]
    if chart["bars"] != chart["drawn"] or chart["counts"] != chart["bars"] or not 1 <= chart["bars"] <= MOST_BARS:
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
    bar) show no count and every other tick; a tap on a chart's name enlarges it (272 px for its six bars, the
    length chart 300 px for its nine: over the 288 px of c.css's rule for nine bars), and the enlarged chart alone
    shows its counts and every tick; the others stay as they were."""
    page = _page(site, SMALL_PHONE)
    assert page.evaluate(PANELS_JS, LAYOUT_KEY)["narrow"]
    small = {c["name"]: c for c in page.evaluate(CHARTS_JS)}
    assert len(small) == CHARTS and not any(c["open"] for c in small.values()), small
    for name, chart in small.items():
        assert chart["width"] == (236 if name == "length" else 148), chart
        assert chart["shown"] == 0 and not _numbers_rule(chart), (chart, _numbers_rule(chart))
    for name, width, bars in (("clearance", 272, 6), ("length", 300, 9)):
        _open_chart(page, name)
        charts = {c["name"]: c for c in page.evaluate(CHARTS_JS)}
        assert [n for n, c in charts.items() if c["open"]] == [name], charts
        opened = charts[name]
        assert opened["bars"] == bars, opened
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


def _scroll_column(page, top: int):
    """The phone's column scrolled to `top` px; waits for it."""
    page.evaluate("(top) => { document.querySelector('.c-mappage-3').scrollTop = top; }", top)
    page.wait_for_function("(top) => document.querySelector('.c-mappage-3').scrollTop === top", arg=top, timeout=WAIT)


def _cell_point(page) -> dict:
    """A point of the map as it stands inside a whole cell of Slovakia's own, near the map's centre (CELL_POINT_JS
    over the last answer of /cells): {x, y, count}."""
    assert page.cells, "no answer of Slovakia's /cells"
    point = page.evaluate(CELL_POINT_JS, page.cells[-1].json())
    assert point, "no whole cell of Slovakia's own under the map"
    return point


def _tab_to(page, what: str, most: int = 150) -> int:
    """Real presses of Tab until the element with the focus fits `what` (a script's expression of `e`, that
    element); how many it took."""
    held = "() => { const e = document.activeElement; return !!e && e !== document.body && !!(%s); }" % what
    for presses in range(most + 1):
        if page.evaluate(held):
            return presses
        page.keyboard.press("Tab")
    raise AssertionError(f"{most} presses of Tab did not reach {what}; the focus is on "
                         + page.evaluate("() => document.activeElement.outerHTML.slice(0, 200)"))


def _layers(shadow: str) -> list:
    """The layers of a computed box-shadow (parted at the commas outside brackets); none: []."""
    return [] if shadow == "none" else re.split(r",\s*(?![^()]*\))", shadow)


def test_tapped_cell_comes_under_the_sticky_map(site):
    """The fix round's point 3. On a phone (390 x 664, touch) with the column scrolled by 600 px under the sticky
    map, a finger's tap on a cell of the map selects it and the column scrolls at once so that the cell's card
    stands right under the map: its top within 2 px of the map's bottom edge and 8 px (285.7 against 277.75 + 8
    measured, the column at 1454 px). Held sideways (667 x 375) the map is not sticky and the page scrolls nothing:
    after a tap on a cell with the column at its top, the column is still at its top (0 px before and after,
    measured) and the card far under it (1457 px), not brought to the column's top."""
    page = _page(site, SMALL_PHONE)
    _scroll_column(page, 600)
    point, before = _cell_point(page), page.evaluate(COLUMN_JS)
    assert before["narrow"] and before["position"] == "sticky" and before["scrolled"] == 600 and before["cellTop"] is None, before
    _tap(page, point["x"], point["y"])
    page.wait_for_selector(".c-layer-cell", timeout=WAIT)
    page.evaluate(FRAMES_JS)
    after = page.evaluate(COLUMN_JS)
    assert f"{point['count']:,} lines" in after["card"], (point, after)  # the tapped cell's card
    assert abs(after["cellTop"] - (after["mapBottom"] + 8)) <= 2, (before, after)
    assert after["scrolled"] != 600 and abs(after["mapTop"] - after["columnTop"]) <= 1, after  # the column moved, the map stayed
    assert page.errors == [], page.errors
    page.context.close()
    page = _page(site, SIDE_PHONE)
    point, before = _cell_point(page), page.evaluate(COLUMN_JS)
    assert before["narrow"] and before["position"] != "sticky" and before["scrolled"] == 0 and before["room"] > 600, before
    _tap(page, point["x"], point["y"])
    page.wait_for_selector(".c-layer-cell", timeout=WAIT)
    page.evaluate(FRAMES_JS)
    after = page.evaluate(COLUMN_JS)
    assert f"{point['count']:,} lines" in after["card"], (point, after)
    assert after["scrolled"] == 0 and after["cellTop"] - after["columnTop"] > 600, (before, after)
    assert page.errors == [], page.errors
    page.context.close()


def test_map_is_sticky_after_a_turn(site):
    """The fix round's point 8: the page loaded with the phone held sideways (667 x 375: the map not sticky) and
    the phone then turned upright (the window 375 x 667): with the column scrolled by 600 px the map is sticky, its
    top at the column's; the map's element carries no position of its own in either state (Leaflet writes one on a
    map it finds static, and that one would outrank the sticky rule: c.css gives the map `position: relative`)."""
    page = _page(site, SIDE_PHONE)
    before = page.evaluate(COLUMN_JS)
    assert before["narrow"] and before["window"] == [667, 375] and before["position"] != "sticky", before
    page.set_viewport_size({"width": 375, "height": 667})
    page.wait_for_function("() => innerWidth === 375 && innerHeight === 667", timeout=WAIT)
    page.evaluate(FRAMES_JS)
    _scroll_column(page, 600)
    after = page.evaluate(COLUMN_JS)
    assert after["narrow"] and after["position"] == "sticky", (before, after)
    assert after["scrolled"] == 600 and abs(after["mapTop"] - after["columnTop"]) <= 1, after
    assert before["inline"] == "" and after["inline"] == "" and before["position"] == "relative", (before, after)
    assert page.errors == [], page.errors
    page.context.close()


def test_collapse_tab_shows_the_keyboard_ring(site):
    """The fix round's point 9 on a desktop, the focus brought by real presses of Tab: the left panel's collapse
    tab keeps its own shadow (two layers) and adds the kit's ring after it (2 px of the surface, 4 px of the
    accent: four layers). (The map's ring is not drawn inside its box: Leaflet focuses the map on a press, which
    the browsers mark :focus-visible, so such a ring showed after every press: docs/known-bugs.md.)"""
    page = _page(site, DESKTOP)
    tab, shadow = ".c-mappage-3 > .c-col-left > .c-col-tab", "(s) => getComputedStyle(document.querySelector(s)).boxShadow"
    colours = page.evaluate(TOKENS_JS)
    assert re.fullmatch(r"rgb\(\d+, \d+, \d+\)", colours["accent"]) and colours["accent"] != colours["surface"], colours
    plain = _layers(page.evaluate(shadow, tab))
    assert len(plain) == 2 and not any(colours["accent"] in layer for layer in plain), plain
    presses = _tab_to(page, f"e.matches('{tab}')")
    assert presses > 0 and page.evaluate("() => document.activeElement.matches(':focus-visible')")
    focused = _layers(page.evaluate(shadow, tab))
    assert focused == plain + [f"{colours['surface']} 0px 0px 0px 2px", f"{colours['accent']} 0px 0px 0px 4px"], (plain, focused)
    assert page.errors == [], page.errors
    page.context.close()


# The open panels' collapse tabs: each one's drawn box and its target (the box joined with an absolutely positioned
# ::after, whose insets count from inside its 1 px edge), whether the pointer is coarse
TABS_JS = """() => [...document.querySelectorAll('.c-mappage-3 .c-col-tab')].map((b) => {
  const r = b.getBoundingClientRect(), own = [r.left, r.top, r.right, r.bottom], a = getComputedStyle(b, '::after'), cs = getComputedStyle(b);
  let t = own;
  if (a.content !== 'none' && a.position === 'absolute') {
    const l = r.left + parseFloat(cs.borderLeftWidth) + parseFloat(a.left), top = r.top + parseFloat(cs.borderTopWidth) + parseFloat(a.top);
    t = [Math.min(own[0], l), Math.min(own[1], top), Math.max(own[2], l + parseFloat(a.width)), Math.max(own[3], top + parseFloat(a.height))]; }
  return {name: b.getAttribute('aria-label'), own, target: t, coarse: matchMedia('(pointer: coarse)').matches}; })"""


# The controls beside a tab (within 30 px of its drawn box, at its height): each one's name and the point of its own
# box nearest to the tab that lies on neither the drawn tab nor the splitter's strip (null when none: a control under
# them), and what that point reaches (elementFromPoint)
NEAR_JS = """(own) => { const [l, t, r, b] = own, split = [...document.querySelectorAll('.c-mappage-3 .c-split')].map((s) => s.getBoundingClientRect());
  const inside = (x, y, q) => x >= q[0] && x <= q[2] && y >= q[1] && y <= q[3];
  const blocked = (x, y) => inside(x, y, own) || split.some((s) => inside(x, y, [s.left, s.top, s.right, s.bottom]));
  const out = [];
  for (const e of document.querySelectorAll('button, select, input, a[href], [role=button]')) {
    if (e.classList.contains('c-col-tab') || e.closest('.c-split')) continue;
    const q = e.getBoundingClientRect();
    if (!q.width || !q.height || q.right < l - 30 || q.left > r + 30 || q.bottom < t || q.top > b) continue;
    let best = null;
    for (let y = Math.max(q.top + 2, t); y <= Math.min(q.bottom - 2, b); y += 2)
      for (let x = q.left + 2; x <= q.right - 2; x += 1) {
        if (blocked(x, y)) continue;
        const d = Math.abs(x - (l + r) / 2) + Math.abs(y - (t + b) / 2) / 4;
        if (!best || d < best.d) best = {x, y, d}; }
    if (!best) continue;
    const at = document.elementFromPoint(best.x, best.y);
    out.push({name: (e.getAttribute('aria-label') || e.textContent || e.className).trim().slice(0, 30), x: best.x, y: best.y,
              hit: !!at && (at === e || e.contains(at))}); }
  return out; }"""


@pytest.mark.parametrize("size", [(1024, 768), (1180, 820)], ids=["1024x768", "1180x820"])
def test_collapse_tabs_take_a_finger_on_a_tablet(site, size):
    """Step 3d's B1 (docs/DESIGN.md row 83; the planner's decision: invisible targets, as the user's pick for the 3D
    view's marks): a touch tablet keeps the desktop's columns, and each panel's collapse tab, 24 px wide as drawn,
    takes a finger's tap anywhere in its 44 px target, 2 px inside its left and its right edge (before: 24 x 44 px,
    under R2's 44 px); its target grows towards the map only, so a tap on a control of the panel beside it (a select's
    right end, a chart's bar: within 30 px of the tab) reaches that control (the fix round: the first build's target
    grew 10 px into the panel too and took those taps, the code review's F2)."""
    page = _page(site, {"viewport": {"width": size[0], "height": size[1]}, "has_touch": True, "is_mobile": False})
    tabs = page.evaluate(TABS_JS)
    assert len(tabs) == 2 and all(t["coarse"] and t["own"][2] - t["own"][0] < 30 for t in tabs), tabs  # the case
    page.evaluate("""() => { window.CLICKS = []; document.addEventListener('click', (e) => {
      const c = e.target.closest('button, select, input, a[href], [role=button]');
      window.CLICKS.push(c ? (String(c.className) || c.tagName) + '|' + (c.getAttribute('aria-label') || c.textContent || '').trim().slice(0, 30) : e.target.tagName);
      e.preventDefault(); e.stopPropagation(); }, true); }""")
    beside = 0
    for tab in tabs:
        t = tab["target"]
        assert t[2] - t[0] >= 43.5 and t[3] - t[1] >= 43.5, tab
        for x in (t[0] + 2, t[2] - 2):
            page.evaluate("() => { window.CLICKS = []; }")
            _tap(page, x, (t[1] + t[3]) / 2)
            page.wait_for_function("() => window.CLICKS.length > 0", timeout=WAIT)
            assert "c-col-tab" in page.evaluate("() => window.CLICKS[0]"), (tab, x)
        for c in page.evaluate(NEAR_JS, tab["own"]):
            beside += 1
            assert c["hit"], (tab["name"], c)  # the control itself at that point, no target over it
            page.evaluate("() => { window.CLICKS = []; }")
            _tap(page, c["x"], c["y"])
            page.wait_for_function("() => window.CLICKS.length > 0", timeout=WAIT)
            got = page.evaluate("() => window.CLICKS[0]")
            assert "c-col-tab" not in got and c["name"][:12] in got, (tab["name"], c, got)
    assert beside > 0  # the case: controls beside the tabs
    assert page.errors == [], page.errors
    page.context.close()


def test_counts_are_parted_by_semicolons(site):
    """The fix round's point 10 on a desktop: the counts hold thousands commas, so a semicolon parts them: the
    totals line "N lines; M spots in view" and its split "… lines across the border; K of them beyond it", a cell's
    tooltip "N lines; D per km²" (the pointer over a cell), the selected cell's card "N lines; M spots; D lines per
    km²" (that cell clicked); no ", " follows a count's noun."""
    page = _page(site, DESKTOP)
    total = page.inner_text(".c-layer-total")
    assert re.match(r"[\d,]+ lines; [\d,]+ spots in view\n", total), total
    assert re.search(r"of them [\d,]+ lines across the border; [\d,]+ of them beyond it\n", total), total
    assert not re.search(r"(lines|spots|border), \d", total), total
    point = _cell_point(page)
    page.mouse.move(point["x"], point["y"])
    page.wait_for_selector(".c-mappage-3 .leaflet-tooltip", timeout=WAIT)
    tip = page.inner_text(".c-mappage-3 .leaflet-tooltip")
    assert re.fullmatch(rf"{point['count']:,} lines; [\d.,]+ per km²", tip), (tip, point)
    page.mouse.click(point["x"], point["y"])
    page.wait_for_selector(".c-layer-cell", timeout=WAIT)
    card = page.inner_text(".c-layer-cell")
    assert re.search(rf"\n{point['count']:,} lines; [\d,]+ spots; [\d.,]+ lines per km²\n", card), (card, point)
    assert not re.search(r"(lines|spots), \d", card), card
    assert page.errors == [], page.errors
    page.context.close()


def test_rails_lead_their_counts_with_a_colon(site):
    """The fix round's point 5 on a desktop, the panels collapsed by the kept layout: the left rail reads "Filters:
    N set" and the right one "Histograms: N lines in view"; a rail's accessible name is its visible label, then
    ". Expand the filters" (". Expand the histograms"): the rail is found by its role and that name."""
    for side, kept, words, name in (
            ("left", {"v": 2, "left": {"w": 340, "open": False}, "right": {"w": 485, "open": True}}, r"Filters: \d+ set", "filters"),
            ("right", {"v": 2, "left": {"w": 340, "open": False}, "right": {"w": 485, "open": False}},
             r"Histograms: \d[\d.,]*( [kM])? lines in view", "histograms")):
        page = _page(site, DESKTOP, kept)
        rails = page.evaluate("() => [...document.querySelectorAll('.c-mappage-3 .c-rail')].length")
        assert rails == (1 if side == "left" else 2), rails
        text = page.locator(f".c-mappage-3 > .c-col-{side} > .c-rail .c-rail-text").text_content()
        assert re.fullmatch(words, text), text
        named = page.get_by_role("button", name=f"{text}. Expand the {name}", exact=True)
        assert named.count() == 1, (text, [r.aria_snapshot() for r in page.locator(".c-mappage-3 .c-rail").all()])
        assert named.evaluate("(e) => e.matches('.c-mappage-3 > .c-col-%s > .c-rail')" % side)
        assert page.errors == [], page.errors
        page.context.close()


def test_a_narrow_chart_bar_shows_its_count_on_focus(site):
    """The fix round's point 11. Every bar that can be picked has an accessible name, the short count it writes
    and its tooltip's words (its range and its count: "5.7M, 30–60 m: 5,656,181 lines"; a bar of none: the tooltip's
    words alone), and its short count in data-count. In the phone's frame with
    a keyboard (390 x 664, no touch), where no small chart shows its counts, a bar reached by real presses of Tab
    (the length chart's first, then a six-bar chart's first) shows its own count as a raised label at the chart's
    top (its ::after: content its data-count) and its fill keeps its height; in that chart enlarged by the keyboard
    (Shift+Tab to its name, Enter), which shows its counts, the focused bar has no such label, nor has a desktop's
    bar of a chart that shows its counts."""
    page = _page(site, KEYBOARD_PHONE)
    frame = page.evaluate("() => [!!document.querySelector('.ui.c-narrow'), matchMedia('(pointer: coarse)').matches]")
    assert frame == [True, False], frame
    bars = page.evaluate(BARS_JS)
    assert len(bars) >= 60 and {b["hist"] for b in bars}.isdisjoint(OFF), len(bars)
    for bar in bars:
        # the name begins with the count the bar writes (shown where its chart has room: a label in its name, axe's
        # label-content-name-mismatch), then its tooltip's words
        assert bar["label"] == (f'{bar["written"]}, {bar["title"]}' if bar["written"] else bar["title"]), bar
        assert re.search(r": [\d,]+ lines$", bar["label"]), bar
        assert bar["count"] and (bar["count"] == bar["written"] or (bar["value"] == 0 and bar["count"] == "0" and bar["written"] == "")), bar
    fills = page.evaluate(FILLS_JS)

    def labelled(bar):
        """A focused bar of a chart without counts: the keyboard's ring, its count on its ::after, its fill as before."""
        assert bar["visible"] and not bar["open"] and not bar["counts"], bar
        assert bar["count"] and bar["after"] == f'"{bar["count"]}"' and bar["label"] == ["absolute", "0px"], bar
        assert abs(bar["fill"] - fills[bar["hist"]][bar["k"]]) <= 0.01 and bar["fill"] > 0, (bar, fills[bar["hist"]])

    _tab_to(page, "e.matches('button.c-layer-bar')")
    first = page.evaluate(FOCUSED_BAR_JS)
    assert first["hist"] == "length" and first["k"] == 0, first
    labelled(first)
    _tab_to(page, "e.matches('button.c-layer-bar') && e.closest('.c-layer-hist').dataset.hist !== 'length'")
    small = page.evaluate(FOCUSED_BAR_JS)
    assert small["k"] == 0, small
    labelled(small)
    page.keyboard.press("Shift+Tab")
    assert page.evaluate("(name) => document.activeElement.matches(`.c-layer-hist[data-hist=${name}] .c-layer-hist-name`)", small["hist"])
    page.keyboard.press("Enter")
    page.wait_for_function("(name) => document.querySelector(`.c-layer-hist[data-hist=${name}]`).classList.contains('c-layer-hist-open')",
                           arg=small["hist"], timeout=WAIT)
    page.keyboard.press("Tab")
    opened = page.evaluate(FOCUSED_BAR_JS)
    assert opened and opened["hist"] == small["hist"] and opened["k"] == 0 and opened["open"], opened
    assert opened["visible"] and opened["counts"] and opened["after"] == "none", opened
    assert page.errors == [], page.errors
    page.context.close()
    page = _page(site, DESKTOP)
    _tab_to(page, "e.matches('button.c-layer-bar')")
    wide = page.evaluate(FOCUSED_BAR_JS)
    assert wide["visible"] and wide["counts"] and wide["after"] == "none", wide
    assert page.errors == [], page.errors
    page.context.close()


def test_one_container_rule_per_count_of_bars():
    """The fix round's point 12, read from c.css (no browser): a container query takes no variable, so the rule of
    32 px a bar is written once per count of bars, and there is exactly one `@container layer-hist (min-width:
    32 n px)` for every n from 1 to 24 and none else; each names `[data-bars="n"]` alone, for the bars' counts
    (shown), the ticks (every one visible) and the focused bar's label (::after: none, as the counts show); the
    label itself is one rule for a bar with the keyboard's focus."""
    with open(C_CSS, encoding="utf-8") as f:
        css = f.read()
    rules = re.findall(r"^@container layer-hist \(min-width: (\d+)px\) \{(.*)\}[ \t]*$", css, re.M)
    assert len(rules) == css.count("@container layer-hist") == MOST_BARS, (len(rules), css.count("@container layer-hist"))
    assert [int(width) for width, _ in rules] == [PER_BAR * n for n in range(1, MOST_BARS + 1)], [width for width, _ in rules]
    for width, body in rules:
        n = int(width) // PER_BAR
        chart = f'.ui .c-layer-hist[data-bars="{n}"]'
        assert set(re.findall(r'data-bars="(\d+)"', body)) == {str(n)}, (width, body)
        assert body.count("{") == body.count("}") == 3, body
        for rule in (f"{chart} .c-layer-bar-n {{ display: block; }}", f"{chart} .c-layer-hist-axis span {{ visibility: visible; overflow: hidden; }}",
                     f"{chart} .c-layer-bar::after {{ content: none; }}"):
            assert body.count(rule) == 1, (width, rule)
    assert set(re.findall(r'data-bars="(\d+)"', css)) == {str(n) for n in range(1, MOST_BARS + 1)}
    assert css.count(".ui .c-layer-bar:focus-visible::after { content: attr(data-count);") == 1
    assert css.count("::after { content: attr(data-count)") == 1


def test_enlarged_chart_grows_with_its_bars(site):
    """The fix round's point 12 on a phone (390 x 664, touch): a chart enlarged by a tap on its name is 272 px wide
    (the length chart 300 px), or 32 px a bar where it has more bars, up to the screen's width less the gutters
    (358 px). The sample cube's charts have six and nine bars: the others are tried by setting the chart's `--bars`
    (LayerHistograms.tsx writes it from the cube's bins) on the enlarged chart."""
    page = _page(site, SMALL_PHONE)
    widths = """(counts) => { const chart = document.querySelector('.c-layer-hist-open'), own = chart.style.getPropertyValue('--bars'), out = {};
      for (const n of counts) { chart.style.setProperty('--bars', n); out[n] = chart.getBoundingClientRect().width; }
      chart.style.setProperty('--bars', own); return {own, bars: chart.dataset.bars, now: chart.getBoundingClientRect().width, widths: out}; }"""
    for name, bars, expected in (("clearance", 6, {6: 272, 8: 272, 9: 288, 10: 320, 11: 352, 12: 358, 24: 358}),
                                 ("length", 9, {6: 300, 9: 300, 10: 320, 11: 352, 12: 358, 24: 358})):
        _open_chart(page, name)
        found = page.evaluate(widths, list(expected))
        assert found["own"] == found["bars"] == str(bars) and found["now"] == expected[bars], found
        assert found["widths"] == {str(n): width for n, width in expected.items()}, (name, found)
    assert page.errors == [], page.errors
    page.context.close()


def test_charts_of_filters_that_are_off_have_no_bar_to_pick(site):
    """The fix round's point 13b on a desktop: a filter the cubes in view cannot answer (the clearance over trees
    without a surface model, the two A-frame filters of a cube counted without A-frames) has its select disabled,
    and its chart holds no bar that can be picked: every bar is a `span.c-layer-bar-off`, none a button. The other
    charts keep their buttons (all but the bar of the unknown bin)."""
    page = _page(site, DESKTOP)
    charts = {c["name"]: c for c in page.evaluate("""() => [...document.querySelectorAll('.c-layer-hist')].map((h) => {
        const select = document.getElementById('layer-' + h.dataset.hist);
        return {name: h.dataset.hist, bars: Number(h.dataset.bars), buttons: h.querySelectorAll('button.c-layer-bar').length,
                off: h.querySelectorAll('span.c-layer-bar.c-layer-bar-off').length, select: select ? select.disabled : null}; })""")}
    assert len(charts) == CHARTS and set(OFF) < set(charts), list(charts)
    for name, chart in charts.items():
        assert chart["buttons"] + chart["off"] == chart["bars"] > 0, chart
        if name in OFF:
            assert chart["select"] is True and chart["buttons"] == 0, chart
        else:
            assert chart["select"] is not True and chart["buttons"] >= chart["bars"] - 1, chart
    assert charts["length"]["buttons"] == charts["length"]["bars"], charts["length"]
    assert sum(1 for c in charts.values() if c["select"] is False) >= 10, charts  # the other charts' selects are there, enabled
    assert page.errors == [], page.errors
    page.context.close()


def test_strip_brings_a_focused_chart_name_into_view(site):
    """docs/DESIGN.md row 81 (the fix round, the design review's P4): on a phone with a keyboard, every chart's name
    Tab reaches in the swiped strips lies wholly inside the window (LayerHistograms.tsx revealInStrip brings its chart
    to the strip's start; before: the browser's focus scroll and the strip's snapping left 22 to 98 px of a name
    outside the window)."""
    page = _page(site, KEYBOARD_PHONE)
    page.evaluate("() => { const s = document.createElement('span'); s.id = 'st'; s.tabIndex = -1; document.body.prepend(s); s.focus(); }")
    names, out = 0, []
    for _ in range(200):
        page.keyboard.press("Tab")
        page.evaluate(FRAMES_JS)
        got = page.evaluate("""() => { const e = document.activeElement; if (!e?.classList.contains('c-layer-hist-name')) return null;
          const r = e.getBoundingClientRect(); return {name: e.textContent.trim(), left: r.left, right: r.right, w: innerWidth}; }""")
        if got is None:
            if names and page.evaluate("() => !document.activeElement?.closest('.c-col-right')"):
                break
            continue
        names += 1
        if got["left"] < -0.5 or got["right"] > got["w"] + 0.5:
            out.append(got)
    assert names >= 10, names  # the case: the strips' names
    assert out == [], out
    assert page.errors == [], page.errors
    page.context.close()
