"""The coverage page's layout (/coverage of the local app; viewer/src/coverage/page) on a phone and a desktop in
Playwright's Edge: the user's picks of step 3c, group C (2026-11-19). L1: on a phone the list is one 48 px row per
area, the whole row a button opening the card, a wide screen keeps the table; L2: a country's regions in its card are
the kit's chips, 44 px on a touch screen; L6: the header scrolls away on a phone and stays on a wide screen; the
stars are drawn (three of the kit's icon per level, the ones not reached marked), no "★" character on the page.
Every wait is an event with a deadline; a finger's taps keep test_shell_c_view_map's spacing (_tap_on). The contexts
ask for reduced motion: the page then scrolls to its map at once after a pick (CoveragePage.tsx), not smoothly under
the next tap."""

import json
import os

import pytest

from test_shell_c_view_map import _tap_on
from test_web import EDGE, WAIT, _playwright, _server

pytestmark = pytest.mark.skipif(not os.path.exists(EDGE) or not _playwright(),
                                reason="needs Microsoft Edge and Playwright (group ui)")

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOUCH = {"device_scale_factor": 3, "is_mobile": True, "has_touch": True}
SMALL_PHONE = {"viewport": {"width": 390, "height": 664}, **TOUCH}  # tools/ui_shots.py's iPhone: the least room
DESKTOP = {"viewport": {"width": 1400, "height": 900}}
STARS_SCALE = ".cov-scale button:nth-child(3)"  # the scale's switch: words, life, stars (card.tsx SCALES)
# A click on a shape of the flat map, as tools/ui_shots.py COVERAGE_CLICK sends it
SHAPE_CLICK = "(key) => document.querySelector(`.cov-shape[data-key=\"${key}\"]`).dispatchEvent(new MouseEvent('click', {bubbles: true}))"
CARD_NAME = "() => document.querySelector('.cov-card .cov-h')?.textContent || ''"

with open(os.path.join(REPO, "viewer", "src", "coverage", "coverage.json"), encoding="utf-8") as _f:
    COVERAGE = json.load(_f)
AREAS = COVERAGE["areas"]

# The list as it is drawn: the table (its rows' count and name buttons) and the phone's rows (each button's box, the
# boxes of its list and of its list item, the classes of its parts), and what scrolls
LIST_JS = """() => { const $$ = (s) => [...document.querySelectorAll(s)], box = (e) => { const r = e.getBoundingClientRect(); return [r.left, r.top, r.width, r.height]; };
  const rows = document.querySelector('.cov-rows');
  return {tables: $$('.cov-table').length, tableRows: $$('.cov-table tbody tr').length,
          nameLinks: $$('.cov-table tbody tr > th > button.cov-link.cov-name-link').length,
          lists: $$('.cov-rows').length, list: rows ? box(rows) : null,
          rows: $$('.cov-rows > li > button.cov-row').map((b) => ({box: box(b), name: b.querySelector('.cov-rname')?.textContent || '',
                  parts: [!!b.querySelector('.cov-sw'), !!b.querySelector('.cov-rdet'), !!b.querySelector('svg')]})),
          coarse: matchMedia('(pointer: coarse)').matches}; }"""
# The stars of the legend, the card and the list: per group of stars [drawn stars, the ones not reached, other
# children, its own text]; the list's by row with the level of the row's swatch (cov-sw1..3)
STARS_JS = """() => { const $$ = (s, root = document) => [...root.querySelectorAll(s)];
  const one = (e) => [e.querySelectorAll(':scope > svg.cov-star').length, e.querySelectorAll(':scope > svg.cov-star.cov-off').length,
                      e.children.length - e.querySelectorAll(':scope > svg.cov-star').length, e.textContent];
  const level = (row) => { const sw = row.querySelector('.cov-sw'); return sw ? Number((sw.className.match(/cov-sw([123])/) || [])[1]) : null; };
  return {legend: $$('.cov-legend .cov-it').filter((it) => it.querySelector('.cov-stars')).map((it) => [level(it), one(it.querySelector('.cov-stars'))]),
          card: $$('.cov-card .cov-stars').map(one),
          list: $$('.cov-rows > li, .cov-table tbody tr').map((row) => [level(row), $$('.cov-stars', row).map(one)]),
          small: [$$('.cov-legend .cov-stars').every((e) => e.classList.contains('cov-stars-s')),
                  $$('.cov-list .cov-stars').every((e) => e.classList.contains('cov-stars-s'))],
          text: document.querySelector('.cov').textContent}; }"""
TOP_JS = """() => { const r = document.querySelector('.cov-top').getBoundingClientRect();
  return {y: scrollY, top: r.top, bottom: r.bottom, room: document.documentElement.scrollHeight - innerHeight,
          position: getComputedStyle(document.querySelector('.cov-top')).position}; }"""


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    """The local app on a real server over an empty data folder and Playwright's Edge: (browser, the page's address)."""
    from playwright.sync_api import sync_playwright
    with _server(tmp_path_factory.mktemp("coverage")) as port, sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            yield browser, f"http://127.0.0.1:{port}/coverage?lang=en"
        finally:
            browser.close()


def _page(site, context: dict):
    """The page in a fresh browser context of `context` (nothing kept: the flat view, the words' scale), its outlines
    loaded: the shapes are drawn whatever the list looks like."""
    browser, url = site
    page = browser.new_context(reduced_motion="reduce", **context).new_page()
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)[:300]))
    page.goto(url)
    page.wait_for_selector(".cov-shape[data-key='pl']", state="attached", timeout=WAIT)
    page.wait_for_selector(".cov-list", timeout=WAIT)
    return page


def test_list_is_rows_on_a_phone(site):
    """L1 on a phone (390 x 664, touch): no table; one row per area of coverage.json and one for the rest of the
    world, each a button as wide as the list and at least 48 px high with the level's colour, the name, the
    resolution and an icon; a finger's tap on a row opens the card of that area (a country, then a region, whose row
    names its country in brackets and whose card does not)."""
    page = _page(site, SMALL_PHONE)
    found = page.evaluate(LIST_JS)
    assert found["coarse"], found
    assert found["tables"] == 0 and found["lists"] == 1, (found["tables"], found["lists"])
    rows = found["rows"]
    assert len(rows) == len(AREAS) + 1, len(rows)
    left, _, width, _ = found["list"]
    assert width >= 340, found["list"]  # the screen's 390 less the page's gutters
    for row in rows:
        x, _, w, h = row["box"]
        assert h >= 47.5, row
        assert abs(w - width) <= 0.5 and abs(x - left) <= 0.5, (row, found["list"])
        assert row["name"] and row["parts"] == [True, True, True], row
    names = [row["name"] for row in rows]
    assert names[-1] == "Rest of the world" and "Poland" in names and "Bavaria (Germany)" in names, names
    for name, title in (("Poland", "Poland"), ("Bavaria (Germany)", "Bavaria")):
        _tap_on(page, f".cov-rows > li:nth-child({names.index(name) + 1}) > button.cov-row")
        page.wait_for_function(f"(title) => ({CARD_NAME})() === title", arg=title, timeout=WAIT)
        on = page.evaluate("() => [...document.querySelectorAll('.cov-row.cov-row-on .cov-rname')].map((e) => e.textContent)")
        assert on == [name], on  # the tapped row alone is marked
    assert page.errors == [], page.errors
    page.context.close()


def test_list_is_a_table_on_a_desktop(site):
    """L1 on a wide screen (1400 x 900): the table with the same count of rows, each name a button of its own, and
    no list of rows; a click on a name opens its card."""
    page = _page(site, DESKTOP)
    found = page.evaluate(LIST_JS)
    assert found["lists"] == 0 and found["rows"] == [] and found["tables"] == 1, found
    assert found["tableRows"] == found["nameLinks"] == len(AREAS) + 1, found
    page.click(".cov-table tbody tr > th > button.cov-name-link:text-is('Poland')")
    page.wait_for_function(f"() => ({CARD_NAME})() === 'Poland'", timeout=WAIT)
    assert page.errors == [], page.errors
    page.context.close()


def test_regions_are_chips(site):
    """L2 on a phone: the card of a country covered in parts (Germany, by a click on its shape) lists its regions
    (coverage.json's "partly") as the kit's chips, each at least 44 px high; a finger's tap on one opens that
    region's card."""
    regions = COVERAGE["partly"]["de"]
    assert len(regions) > 3, regions
    page = _page(site, SMALL_PHONE)
    page.evaluate(SHAPE_CLICK, "de")
    page.wait_for_function(f"() => ({CARD_NAME})() === 'Germany'", timeout=WAIT)
    buttons = page.evaluate("""() => [...document.querySelectorAll('.cov-card .cov-regions > li > button')].map((b) =>
        ({name: b.textContent, chip: b.classList.contains('u-chip'), link: b.classList.contains('cov-link'), height: b.getBoundingClientRect().height}))""")
    assert len(buttons) == len(regions), (buttons, regions)
    for button in buttons:
        assert button["chip"] and not button["link"] and button["height"] >= 43.5, button
    names = [b["name"] for b in buttons]
    assert "Bavaria" in names, names
    _tap_on(page, f".cov-card .cov-regions > li:nth-child({names.index('Bavaria') + 1}) > button.u-chip")
    page.wait_for_function(f"() => ({CARD_NAME})() === 'Bavaria'", timeout=WAIT)
    assert page.evaluate("() => document.querySelectorAll('.cov-card .cov-regions').length") == 0  # a region has none
    assert page.errors == [], page.errors
    page.context.close()


def test_header_scrolls_away_on_a_phone(site):
    """L6: on a phone the header is part of the page (scrolled by 400 px, its bottom edge is above the screen's top);
    on a wide screen it is sticky and stays at the top."""
    found = {}
    for name, context in (("phone", SMALL_PHONE), ("desktop", DESKTOP)):
        page = _page(site, context)
        before = page.evaluate(TOP_JS)
        assert before["y"] == 0 and abs(before["top"]) <= 0.5 and before["bottom"] > 40, (name, before)
        assert before["room"] > 600, (name, before)  # the page is long enough to scroll by 400
        page.evaluate("() => window.scrollTo(0, 400)")
        page.wait_for_function("() => scrollY === 400", timeout=WAIT)
        found[name] = page.evaluate(TOP_JS)
        page.context.close()
    phone, desktop = found["phone"], found["desktop"]
    assert phone["y"] == 400 and phone["bottom"] <= 0, phone
    assert phone["position"] == "static", phone
    assert desktop["y"] == 400 and abs(desktop["top"]) <= 0.5 and desktop["bottom"] > 40, desktop
    assert desktop["position"] == "sticky", desktop


@pytest.mark.parametrize("device", ["phone", "desktop"])
def test_stars_are_drawn(site, device):
    """The stars' scale chosen: the legend, an area's card and every row of the list show a level as three drawn
    stars (svg.cov-star and nothing else), the ones not reached marked (.cov-off): none for a level-1 area, one for
    level 2, two for the rest of the world; the small size in the legend and the list; no "★" in the page's text."""
    page = _page(site, SMALL_PHONE if device == "phone" else DESKTOP)
    page.click(STARS_SCALE)
    page.wait_for_function("() => document.querySelector('.cov-scale button:nth-child(3)').getAttribute('aria-checked') === 'true'",
                           timeout=WAIT)
    assert page.evaluate("() => document.querySelector('.cov-scale').classList.contains('u-seg') "
                         "&& [...document.querySelectorAll('.cov-scale button.u-on')].length === 1 "
                         "&& document.querySelector('.cov-scale button:nth-child(3)').classList.contains('u-on')")
    page.evaluate(SHAPE_CLICK, "pl")
    page.wait_for_function(f"() => ({CARD_NAME})() === 'Poland'", timeout=WAIT)
    found = page.evaluate(STARS_JS)
    # the legend: its three levels, [drawn, not reached, other children, text]
    assert found["legend"] == [[1, [3, 0, 0, ""]], [2, [3, 1, 0, ""]], [3, [3, 2, 0, ""]]], found["legend"]
    assert found["card"] == [[3, 0, 0, ""]], found["card"]  # Poland: level 1
    rows = found["list"]
    assert len(rows) == len(AREAS) + 1, len(rows)
    for level, stars in rows:
        assert level in (1, 2, 3) and stars == [[3, level - 1, 0, ""]], (level, stars)
    for level in (1, 2):
        assert sum(1 for row in rows if row[0] == level) == sum(1 for a in AREAS.values() if a["level"] == level) > 0, level
    assert rows[-1] == [3, [[3, 2, 0, ""]]], rows[-1]  # the rest of the world
    assert found["small"] == [True, True], found["small"]
    assert "★" not in found["text"] and "☆" not in found["text"], found["text"][:300]
    assert page.errors == [], page.errors
    page.context.close()
