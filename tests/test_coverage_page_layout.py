"""The coverage page's layout (/coverage of the local app; viewer/src/coverage/page) on a phone and a desktop in
Playwright's Edge: the user's picks of step 3c, group C (2026-11-19). L1: on a phone the list is one 48 px row per
area, the whole row a button opening the card, a wide screen keeps the table; L2: a country's regions in its card are
the kit's chips, 44 px on a touch screen; L6: the header scrolls away on a phone and stays on a wide screen; the
stars are drawn (three of the kit's icon per level, the ones not reached marked), no "★" character on the page.
The fix round (2026-11-20): a phone's row says its level to a screen reader; a row's press keeps the list's place on
a phone (the card is a sheet over it) and closing the card comes back to the row, on a wide screen the page goes to
the map and back; a country covered only in some regions has a row "(rest of the country)"; the empty stars hold 3:1
on every ground; the header scrolls away on a phone held sideways too; the scale's segments are as wide as their
words.
Every wait is an event with a deadline; a finger's taps keep test_shell_c_view_map's spacing (_tap, _tap_on). The
contexts ask for reduced motion: the page then scrolls to its map at once after a pick (CoveragePage.tsx), not
smoothly under the next tap."""

import json
import os
import re

import pytest

from test_shell_c_view_map import _tap, _tap_on
from test_web import EDGE, WAIT, _playwright, _server

pytestmark = pytest.mark.skipif(not os.path.exists(EDGE) or not _playwright(),
                                reason="needs Microsoft Edge and Playwright (group ui)")

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOUCH = {"device_scale_factor": 3, "is_mobile": True, "has_touch": True}
SMALL_PHONE = {"viewport": {"width": 390, "height": 664}, **TOUCH}  # tools/ui_shots.py's iPhone: the least room
TALL_PHONE = {"viewport": {"width": 390, "height": 844}, **TOUCH}
SIDE_PHONE = {"viewport": {"width": 844, "height": 390}, **TOUCH}  # a phone held sideways: wide (the table), 390 px high
TABLET = {"viewport": {"width": 1180, "height": 820}, **TOUCH}  # a touch screen that is no phone
DESKTOP = {"viewport": {"width": 1400, "height": 900}}
STARS_SCALE = ".cov-scale button:nth-child(3)"  # the scale's switch: words, life, stars (card.tsx SCALES)
# A click on a shape of the flat map, as tools/ui_shots.py COVERAGE_CLICK sends it
SHAPE_CLICK = "(key) => document.querySelector(`.cov-shape[data-key=\"${key}\"]`).dispatchEvent(new MouseEvent('click', {bubbles: true}))"
CARD_NAME = "() => document.querySelector('.cov-card .cov-h')?.textContent || ''"

with open(os.path.join(REPO, "viewer", "src", "coverage", "coverage.json"), encoding="utf-8") as _f:
    COVERAGE = json.load(_f)
with open(os.path.join(REPO, "locales", "coverage", "en.json"), encoding="utf-8") as _f:
    WORDS = json.load(_f)
AREAS = COVERAGE["areas"]
# The countries covered only in some regions and not as a whole: each has a row "<country> (rest of the country)"
REST = [country for country in COVERAGE["partly"] if country not in AREAS]
ROWS = len(AREAS) + len(REST) + 1  # the list's rows: the areas, those countries, the rest of the world

# The list as it is drawn: the table (its rows' count and name buttons) and the phone's rows (each button's box, the
# boxes of its list and of its list item, the classes of its parts; its name as drawn, without the words kept for a
# screen reader), and what scrolls
LIST_JS = """() => { const $$ = (s) => [...document.querySelectorAll(s)], box = (e) => { const r = e.getBoundingClientRect(); return [r.left, r.top, r.width, r.height]; };
  const drawn = (e) => { if (!e) return ''; const copy = e.cloneNode(true); copy.querySelectorAll('.u-sr').forEach((s) => s.remove()); return copy.textContent; };
  const rows = document.querySelector('.cov-rows');
  return {tables: $$('.cov-table').length, tableRows: $$('.cov-table tbody tr').length,
          nameLinks: $$('.cov-table tbody tr > th > button.cov-link.cov-name-link').length,
          names: Object.fromEntries($$('.cov-table tbody tr > th > button.cov-name-link').map((b) => [b.dataset.row, b.textContent])),
          lists: $$('.cov-rows').length, list: rows ? box(rows) : null,
          rows: $$('.cov-rows > li > button.cov-row').map((b) => ({key: b.dataset.row, box: box(b), name: drawn(b.querySelector('.cov-rname')),
                  level: Number((b.querySelector('.cov-sw').className.match(/cov-sw([123])/) || [])[1]), detail: b.querySelector('.cov-rdet')?.textContent || '',
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
# Where the page is: how far it is scrolled, the open card's name, what has the focus (a row of the list by its key,
# else its class; "body" for none)
PLACE_JS = """() => { const a = document.activeElement;
  return {y: scrollY, card: document.querySelector('.cov-card .cov-h')?.textContent || null,
          focus: !a || a === document.body ? 'body' : a.dataset.row ? 'row ' + a.dataset.row : String(a.className.baseVal ?? a.className)}; }"""
# A row of the list (a phone's row, a table's name) brought to `block` of the screen, `down` px lower when given;
# its box [left, top, width, height]
ROW_TO_JS = """([key, block, down]) => { const b = document.querySelector(`.cov-list button[data-row="${key}"]`); b.scrollIntoView({block});
  if (down) scrollBy(0, -down);
  const r = b.getBoundingClientRect(); return [r.left, r.top, r.width, r.height]; }"""
# The open card and its close button: the card's box [top, bottom], the button's centre, and whether the button is
# what a finger or a pointer meets there (else what is)
CARD_JS = """() => { const card = document.querySelector('.cov-card'), x = card.querySelector('.cov-x'), c = card.getBoundingClientRect(), r = x.getBoundingClientRect();
  const at = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2), top = document.querySelector('.cov-top').getBoundingClientRect();
  const row = at && at.closest('[data-row]');
  return {card: [c.top, c.bottom], position: getComputedStyle(card).position, x: [r.left + r.width / 2, r.top + r.height / 2], hit: !!at && x.contains(at),
          met: !at ? null : row ? 'row ' + row.dataset.row : String(at.className.baseVal ?? at.className), window: innerHeight, header: top.bottom}; }"""
# Three animation frames from now: what the page left for its next frame (a pick's and a close's scroll and focus,
# CoveragePage.tsx) has run (frame callbacks run in the order they were asked for)
FRAMES_JS = "() => new Promise((done) => requestAnimationFrame(() => requestAnimationFrame(() => requestAnimationFrame(done))))"
CARD_FOCUSED = "() => !!document.querySelector('.cov-card') && document.activeElement === document.querySelector('.cov-card')"
NO_CARD = "() => !document.querySelector('.cov-card')"
# The scale's segments: each one's words, its box, what it holds against what it shows, the lines of its words, the
# room inside its padding and the width of its words
SCALE_JS = """() => [...document.querySelectorAll('.cov-scale button')].map((b) => { const r = b.getBoundingClientRect(), cs = getComputedStyle(b), range = document.createRange();
  range.selectNodeContents(b);
  return {text: b.textContent, box: [r.left, r.top, r.right, r.bottom], scroll: b.scrollWidth, client: b.clientWidth, lines: range.getClientRects().length,
          room: r.width - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight) - parseFloat(cs.borderLeftWidth) - parseFloat(cs.borderRightWidth),
          words: range.getBoundingClientRect().width, least: parseFloat(cs.minWidth) || 0}; })"""
# The colours as drawn: a colour of any notation resolved to [r, g, b, a] of sRGB by painting one pixel of a canvas
# (a `color-mix` comes back as `color(srgb …)`); an element's ground, the nearest opaque background behind it
PAINT_JS = """() => { const canvas = document.createElement('canvas'); canvas.width = canvas.height = 1;
  const pen = canvas.getContext('2d', {willReadFrequently: true});
  window.rgbOf = (colour) => { pen.clearRect(0, 0, 1, 1); pen.fillStyle = '#000'; pen.fillStyle = colour; pen.fillRect(0, 0, 1, 1); return [...pen.getImageData(0, 0, 1, 1).data]; };
  window.groundOf = (e) => { for (let p = e; p; p = p.parentElement) { const b = rgbOf(getComputedStyle(p).backgroundColor); if (b[3]) return b; }
    return rgbOf(getComputedStyle(document.body).backgroundColor); }; }"""
# The stars' colours: every empty star's colour (its fill and its stroke: currentColor) with its ground, by where it
# stands; a filled star's colour and the level-1 colour of the map (--cov-l1)
STAR_COLOURS_JS = """() => { const $$ = (s) => [...document.querySelectorAll(s)];
  const one = (e) => { const cs = getComputedStyle(e); return {star: rgbOf(cs.fill), stroke: rgbOf(cs.stroke), colour: rgbOf(cs.color), ground: groundOf(e)}; };
  const place = (e) => e.closest('.cov-legend') ? 'legend' : e.closest('.cov-card') ? 'card' : e.closest('.cov-row-on') ? 'selected row' : e.closest('.cov-list') ? 'row' : 'elsewhere';
  const filled = document.querySelector('.cov-legend .cov-star:not(.cov-off)'), root = getComputedStyle(document.querySelector('.cov'));
  return {empty: $$('.cov-star.cov-off').map((e) => ({place: place(e), ...one(e)})), filled: one(filled).star, l1: rgbOf(root.getPropertyValue('--cov-l1')),
          theme: document.querySelector('.cov').dataset.theme}; }"""


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


def _page(site, context: dict, lang: str = "en"):
    """The page in `lang` in a fresh browser context of `context` (nothing kept: the flat view, the words' scale), its
    outlines loaded: the shapes are drawn whatever the list looks like."""
    browser, url = site
    page = browser.new_context(reduced_motion="reduce", **context).new_page()
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)[:300]))
    page.goto(url.replace("lang=en", f"lang={lang}"))
    page.wait_for_selector(".cov-shape[data-key='pl']", state="attached", timeout=WAIT)
    page.wait_for_selector(".cov-list", timeout=WAIT)
    return page


def _centre(box: list) -> tuple:
    """The centre of a box [left, top, width, height]."""
    return box[0] + box[2] / 2, box[1] + box[3] / 2


def _spoken(page, key: str) -> str:
    """The accessible name of the list's row of `key`, as Playwright's accessibility snapshot gives it."""
    snapshot = page.locator(f'.cov-list button[data-row="{key}"]').aria_snapshot()
    found = re.match(r'- button "([^"]*)"', snapshot)
    assert found, snapshot
    return found.group(1)


def _escape(page):
    """Escape pressed on the keyboard, once the open card listens for it: the page adds that listener in an effect,
    which Preact runs after the frame that drew the card (.claude/rules/browser-tests.md, pitfall 1), so a key sent
    in the same frame would be lost."""
    page.evaluate(FRAMES_JS)
    page.keyboard.press("Escape")


def _contrast(a: list, b: list) -> float:
    """WCAG's contrast ratio of two sRGB colours [r, g, b, …] of 0 to 255."""
    def luminance(colour):
        linear = [c / 255 / 12.92 if c / 255 <= 0.04045 else ((c / 255 + 0.055) / 1.055) ** 2.4 for c in colour[:3]]
        return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]
    light, dark = sorted((luminance(a), luminance(b)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


def test_list_is_rows_on_a_phone(site):
    """L1 on a phone (390 x 664, touch): no table; one row per area of coverage.json, one per country covered only
    in some regions and one for the rest of the world, each a button as wide as the list and at least 48 px high with
    the level's colour, the name, the resolution and an icon; a finger's tap on a row opens the card of that area (a
    country, then a region, whose row names its country in brackets and whose card does not). The card is a sheet
    over the list's lower part, which stays where it is: each row is brought to the screen's top before its tap."""
    page = _page(site, SMALL_PHONE)
    found = page.evaluate(LIST_JS)
    assert found["coarse"], found
    assert found["tables"] == 0 and found["lists"] == 1, (found["tables"], found["lists"])
    rows = found["rows"]
    assert len(rows) == ROWS, len(rows)
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
        page.evaluate(ROW_TO_JS, [rows[names.index(name)]["key"], "start"])
        _tap_on(page, f".cov-rows > li:nth-child({names.index(name) + 1}) > button.cov-row")
        page.wait_for_function(f"(title) => ({CARD_NAME})() === title", arg=title, timeout=WAIT)
        on = page.evaluate("() => [...document.querySelectorAll('.cov-row.cov-row-on')].map((e) => e.dataset.row)")
        assert on == [rows[names.index(name)]["key"]], on  # the tapped row alone is marked
    assert page.errors == [], page.errors
    page.context.close()


def test_list_is_a_table_on_a_desktop(site):
    """L1 on a wide screen (1400 x 900): the table with the same count of rows, each name a button of its own, and
    no list of rows; a click on a name opens its card."""
    page = _page(site, DESKTOP)
    found = page.evaluate(LIST_JS)
    assert found["lists"] == 0 and found["rows"] == [] and found["tables"] == 1, found
    assert found["tableRows"] == found["nameLinks"] == ROWS, found
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
    assert len(rows) == ROWS, len(rows)
    for level, stars in rows:
        assert level in (1, 2, 3) and stars == [[3, level - 1, 0, ""]], (level, stars)
    for level in (1, 2):
        assert sum(1 for row in rows if row[0] == level) == sum(1 for a in AREAS.values() if a["level"] == level) > 0, level
    assert rows[-1] == [3, [[3, 2, 0, ""]]], rows[-1]  # the rest of the world
    assert found["small"] == [True, True], found["small"]
    assert "★" not in found["text"] and "☆" not in found["text"], found["text"][:300]
    assert page.errors == [], page.errors
    page.context.close()


def test_a_row_says_its_level(site):
    """The fix round's point 1, on a phone (390 x 664): a row's accessible name holds, after the area's name, its
    level's word in the chosen scale and "only in parts" for a partial area: Australia (level 2, partial) "Detailed,
    only in parts" and with the stars "Good, only in parts"; Austria (level 1, whole) "Very detailed" and "Best",
    never "only in parts"; the row is found by its role and those words. Nothing of it is drawn: the words lie in a
    1 px clipped box, the row is still 48 px high and its name one line."""
    partly = WORDS["legend.partial"].lower()
    assert AREAS["au"]["level"] == 2 and AREAS["au"]["partial"] and AREAS["at"]["level"] == 1 and not AREAS["at"]["partial"]
    page = _page(site, SMALL_PHONE)
    for scale in ("level", "stars"):  # the words' scale (the page's first), then the stars'
        if scale == "stars":
            page.click(STARS_SCALE)
            page.wait_for_function("() => !!document.querySelector('.cov-rows .cov-stars')", timeout=WAIT)
        good, best = WORDS[f"{scale}.2"], WORDS[f"{scale}.1"]
        assert (good, best) == (("Detailed", "Very detailed") if scale == "level" else ("Good", "Best")), (good, best)
        australia, austria = _spoken(page, "au"), _spoken(page, "at")
        assert australia.startswith("Australia") and f", {good}, {partly}," in australia, australia
        assert austria.startswith("Austria") and f", {best}," in austria and partly not in austria, austria
        by_role = page.get_by_role("button", name=re.compile(rf"^Australia\b.*\b{good}, {partly}\b"))
        assert by_role.count() == 1 and by_role.get_attribute("data-row") == "au", (scale, by_role.count())
    look = page.evaluate("""() => ['au', 'at'].map((key) => { const b = document.querySelector(`.cov-rows button[data-row="${key}"]`), words = b.querySelector('.cov-rname .u-sr');
        const box = words.getBoundingClientRect(), cs = getComputedStyle(words);
        return {row: b.getBoundingClientRect().height, name: b.querySelector('.cov-rname').getBoundingClientRect().height,
                words: [box.width, box.height, cs.position, cs.overflow]}; })""")
    for row in look:
        assert row["row"] == 48 and row["name"] < 24, row  # one line of 14 px (20.3 px measured)
        assert row["words"] == [1, 1, "absolute", "hidden"], row
    assert page.errors == [], page.errors
    page.context.close()


@pytest.mark.parametrize("close", ["button", "escape"])
@pytest.mark.parametrize("phone", [SMALL_PHONE, TALL_PHONE], ids=["390x664", "390x844"])
def test_row_press_keeps_the_place_on_a_phone(site, phone, close):
    """The fix round's point 2 on a phone (390 x 664 and 390 x 844, touch): a row in the middle of the list tapped,
    the card opens as a sheet at the screen's bottom and the page stays where it was (scrollY within 1 px); the card
    closed by a finger's tap on its button, or by Escape: no card, the page still there, the focus on the tapped
    row. The sheet lies over the list's rows: its close button is what a finger meets at the button's place."""
    page = _page(site, phone)
    key = "fr"
    box = page.evaluate(ROW_TO_JS, [key, "start", 100])  # the row 100 px under the screen's top: over the sheet to come
    assert 90 <= box[1] <= 110, box
    before = page.evaluate(PLACE_JS)
    assert before["y"] > 1000 and before["card"] is None, before  # far down the list (2202 and 2310 px measured)
    _tap(page, *_centre(box))
    page.wait_for_function(CARD_FOCUSED, timeout=WAIT)  # the last thing a pick does (its frame)
    opened, card = page.evaluate(PLACE_JS), page.evaluate(CARD_JS)
    assert opened["card"] == "France" and abs(opened["y"] - before["y"]) <= 1, (before, opened)
    assert card["position"] == "fixed" and abs(card["card"][1] - card["window"]) <= 1 and card["card"][0] > box[1] + box[3], (card, box)
    if close == "button":
        assert card["hit"], f"the sheet's close button is under {card['met']}: {card}"
        _tap(page, *card["x"])
    else:
        _escape(page)
    page.wait_for_function(NO_CARD, timeout=WAIT)
    page.evaluate(FRAMES_JS)
    closed = page.evaluate(PLACE_JS)
    assert closed["card"] is None and abs(closed["y"] - before["y"]) <= 1, (before, closed)
    assert closed["focus"] == f"row {key}", closed
    assert page.errors == [], page.errors
    page.context.close()


def test_row_press_goes_to_the_map_and_back_on_a_desktop(site):
    """The fix round's point 2 on a wide screen (1400 x 900; reduced motion, so the page scrolls at once): a name
    far down the table clicked, the page scrolls to the map and the card is whole on the screen under the header;
    the card closed by its button: the page back where it was (within 2 px) and the focus on that name. A region's
    chip pressed in a card opened from a row keeps the row: closed by Escape, the page is back at Germany's row and
    the focus on it."""
    page = _page(site, DESKTOP)
    # a row, its card closed by the button
    box = page.evaluate(ROW_TO_JS, ["si", "center"])
    before = page.evaluate(PLACE_JS)
    assert before["y"] > 1000 and before["card"] is None, before  # 3499 px measured
    page.mouse.click(*_centre(box))
    page.wait_for_function(CARD_FOCUSED, timeout=WAIT)
    opened, card = page.evaluate(PLACE_JS), page.evaluate(CARD_JS)
    assert opened["card"] == "Slovenia" and opened["y"] < before["y"] - 1000, (before, opened)  # at the map: 220 px measured
    assert card["position"] == "absolute" and card["header"] <= card["card"][0] and card["card"][1] <= card["window"], card
    assert card["hit"], card
    page.mouse.click(*card["x"])
    page.wait_for_function(NO_CARD, timeout=WAIT)
    page.evaluate(FRAMES_JS)
    closed = page.evaluate(PLACE_JS)
    assert closed["card"] is None and abs(closed["y"] - before["y"]) <= 2, (before, closed)
    assert closed["focus"] == "row si", closed
    # Germany's row, a chip of its card, Escape
    box = page.evaluate(ROW_TO_JS, ["de", "center"])
    before = page.evaluate(PLACE_JS)
    assert before["y"] > 1000 and abs(before["y"] - opened["y"]) > 1000, (before, opened)
    page.mouse.click(*_centre(box))
    page.wait_for_function(f"() => ({CARD_FOCUSED})() && ({CARD_NAME})() === 'Germany'", timeout=WAIT)
    page.click(".cov-card .cov-regions button:text-is('Bavaria')")
    page.wait_for_function(f"() => ({CARD_FOCUSED})() && ({CARD_NAME})() === 'Bavaria'", timeout=WAIT)
    chip = page.evaluate(PLACE_JS)
    assert abs(chip["y"] - opened["y"]) <= 2, (chip, opened)  # still at the map
    _escape(page)
    page.wait_for_function(NO_CARD, timeout=WAIT)
    page.evaluate(FRAMES_JS)
    closed = page.evaluate(PLACE_JS)
    assert abs(closed["y"] - before["y"]) <= 2 and closed["focus"] == "row de", (before, closed)
    assert page.errors == [], page.errors
    page.context.close()


def test_card_from_the_map_closes_in_place(site):
    """The fix round's point 2, a card opened on the map (1400 x 900): closed, the page does not move and no row of
    the list gets the focus. With nothing before it (a click on Poland's shape, the page scrolled by 150 px), and
    after a row's press: Slovenia's name clicked far down the table (the page goes to the map), then Poland's
    shape, then Escape: the page stays at the map and does not return to the row."""
    page = _page(site, DESKTOP)
    page.evaluate("() => scrollTo(0, 150)")
    page.wait_for_function("() => scrollY === 150", timeout=WAIT)
    page.evaluate(SHAPE_CLICK, "pl")
    page.wait_for_function(f"() => ({CARD_NAME})() === 'Poland'", timeout=WAIT)
    _escape(page)
    page.wait_for_function(NO_CARD, timeout=WAIT)
    page.evaluate(FRAMES_JS)
    closed = page.evaluate(PLACE_JS)
    assert closed["y"] == 150 and not closed["focus"].startswith("row "), closed
    box = page.evaluate(ROW_TO_JS, ["si", "center"])
    row = page.evaluate(PLACE_JS)
    page.mouse.click(*_centre(box))
    page.wait_for_function(CARD_FOCUSED, timeout=WAIT)
    page.evaluate(SHAPE_CLICK, "pl")
    page.wait_for_function(f"() => ({CARD_NAME})() === 'Poland'", timeout=WAIT)
    at_map = page.evaluate(PLACE_JS)
    assert at_map["y"] < row["y"] - 1000, (row, at_map)
    _escape(page)
    page.wait_for_function(NO_CARD, timeout=WAIT)
    page.evaluate(FRAMES_JS)
    closed = page.evaluate(PLACE_JS)
    assert closed["y"] == at_map["y"] and not closed["focus"].startswith("row "), (at_map, closed)
    assert page.errors == [], page.errors
    page.context.close()


def test_rows_for_countries_covered_in_parts(site):
    """The fix round's point 13: a country covered only in some regions (coverage.json's "partly", not an area of
    its own: on 2026-11-20 Germany, the United Kingdom, Japan and Portugal) has a row in both forms of the list,
    "<country> (rest of the country)" at the world's level (the third swatch, 30 m), so the list has the areas,
    those countries and the rest of the world (83 + 4 + 1 that day). On a phone a tap on the United Kingdom's row
    opens its card with its regions as chips (four); on a desktop Germany's row by the keyboard (Enter on its
    button) opens its card with its sixteen; in Polish the row reads "(reszta kraju)"."""
    assert {"de", "gb"} <= set(REST), REST  # the two rows pressed below (the data may gain or lose others)
    note = f" ({WORDS['page.list.rest']})"
    assert note == " (rest of the country)", note
    # a phone: the rows, a tap
    page = _page(site, SMALL_PHONE)
    rows = {row["key"]: row for row in page.evaluate(LIST_JS)["rows"]}
    assert len(rows) == ROWS == len(AREAS) + len(REST) + 1 and set(REST) <= set(rows), (len(rows), REST)
    for country in REST:
        row = rows[country]
        assert row["name"].endswith(note) and row["level"] == 3 and row["detail"].replace(" ", " ") == "30 m", row
    assert rows["de"]["name"] == "Germany" + note and rows["gb"]["name"] == "United Kingdom" + note, (rows["de"], rows["gb"])
    page.evaluate(ROW_TO_JS, ["gb", "start"])
    _tap_on(page, '.cov-rows button[data-row="gb"]')
    page.wait_for_function(f"() => ({CARD_NAME})() === 'United Kingdom'", timeout=WAIT)
    chips = page.evaluate("() => [...document.querySelectorAll('.cov-card .cov-regions > li > button.u-chip')].map((b) => b.textContent)")
    assert len(chips) == len(COVERAGE["partly"]["gb"]) > 1 and "Scotland" in chips, chips
    assert page.errors == [], page.errors
    page.context.close()
    # a desktop: the table's rows, Germany's by the keyboard
    page = _page(site, DESKTOP)
    found = page.evaluate(LIST_JS)
    assert found["tableRows"] == ROWS and len(found["names"]) == ROWS, found["tableRows"]
    for country in REST:
        assert found["names"][country].endswith(note), found["names"][country]
    assert found["names"]["de"] == "Germany" + note, found["names"]["de"]
    page.focus('.cov-table button[data-row="de"]')
    page.keyboard.press("Enter")
    page.wait_for_function(f"() => ({CARD_FOCUSED})() && ({CARD_NAME})() === 'Germany'", timeout=WAIT)
    chips = page.evaluate("() => [...document.querySelectorAll('.cov-card .cov-regions > li > button.u-chip')].map((b) => b.textContent)")
    assert len(chips) == len(COVERAGE["partly"]["de"]) > 1 and "Bavaria" in chips, chips
    assert page.errors == [], page.errors
    page.context.close()
    # Polish, both forms
    for context in (SMALL_PHONE, DESKTOP):
        page = _page(site, context, lang="pl")
        found = page.evaluate(LIST_JS)
        names = {row["key"]: row["name"] for row in found["rows"]} or found["names"]
        assert len(names) == ROWS, len(names)
        assert names["de"] == "Niemcy (reszta kraju)" and all(names[c].endswith(" (reszta kraju)") for c in REST), [names[c] for c in REST]
        page.context.close()


@pytest.mark.parametrize("device", ["phone", "desktop"])
def test_empty_stars_hold_contrast(site, device):
    """The fix round's point 4, from the colours as drawn (the stars' scale; the rest of the world's row pressed,
    so its card and its selected row are there): in the light and in the dark theme of the page's own switch, every
    empty star (.cov-off: its fill and stroke) holds WCAG's 3:1 against the ground it stands on, in the legend (a
    raised box on a desktop, the page's ground on a phone), the card, a row of the list and the selected row; a
    filled star is still the map's level-1 colour (--cov-l1)."""
    page = _page(site, SMALL_PHONE if device == "phone" else DESKTOP)
    page.evaluate(PAINT_JS)
    page.click(STARS_SCALE)
    page.evaluate(ROW_TO_JS, ["world", "center"])
    page.click('.cov-list button[data-row="world"]')
    page.wait_for_function(CARD_FOCUSED, timeout=WAIT)
    grounds = {}
    for theme, button in (("light", 2), ("dark", 3)):  # the header's second switch: Auto, Light, Dark
        page.evaluate("(n) => document.querySelectorAll('.cov-top .u-seg')[1].querySelector(`button:nth-child(${n})`).click()", button)
        page.wait_for_function("(theme) => document.querySelector('.cov').dataset.theme === theme", arg=theme, timeout=WAIT)
        found = page.evaluate(STAR_COLOURS_JS)
        assert found["filled"] == found["l1"] and found["l1"][3] == 255, found
        places = {star["place"] for star in found["empty"]}
        assert places == {"legend", "card", "row", "selected row"}, places
        for star in found["empty"]:
            assert star["star"] == star["stroke"] == star["colour"] and star["star"][3] == 255 and star["ground"][3] == 255, star
            assert star["star"] != found["filled"], star
            ratio = _contrast(star["star"], star["ground"])
            assert ratio >= 3.0, (theme, star, round(ratio, 2))
            grounds[theme, star["place"]] = tuple(star["ground"][:3])
    # the grounds differ: the page's, the raised surface and the selected fill were all measured
    assert len({grounds["light", place] for place in ("card", "row", "selected row")}) == 3, grounds
    assert len({grounds["dark", place] for place in ("card", "row", "selected row")}) == 3, grounds
    assert page.errors == [], page.errors
    page.context.close()


def test_header_scrolls_away_on_a_phone_held_sideways(site):
    """The fix round's point 6: on a phone held sideways (844 x 390, touch: wide, so the table, but 390 px high) the
    header is part of the page too: scrolled by 300 px its bottom edge is above the screen's top; after a tap on a
    name of the table the card's close button is what a finger meets at its centre (no header over it) and a tap
    there closes the card. On a touch tablet (1180 x 820) and on a desktop the header stays at the top."""
    page = _page(site, SIDE_PHONE)
    assert page.evaluate(LIST_JS)["tables"] == 1
    page.evaluate("() => window.scrollTo(0, 300)")
    page.wait_for_function("() => scrollY === 300", timeout=WAIT)
    side = page.evaluate(TOP_JS)
    assert side["position"] == "static" and side["bottom"] < 0, side  # -231 px measured
    box = page.evaluate(ROW_TO_JS, ["fr", "center"])
    _tap(page, *_centre(box))
    page.wait_for_function(CARD_FOCUSED, timeout=WAIT)
    card = page.evaluate(CARD_JS)
    assert card["hit"] and card["header"] < 0 and 0 <= card["x"][1] <= card["window"], card
    _tap(page, *card["x"])
    page.wait_for_function(NO_CARD, timeout=WAIT)
    assert page.errors == [], page.errors
    page.context.close()
    for name, context in (("tablet", TABLET), ("desktop", DESKTOP)):
        page = _page(site, context)
        page.evaluate("() => window.scrollTo(0, 300)")
        page.wait_for_function("() => scrollY === 300", timeout=WAIT)
        top = page.evaluate(TOP_JS)
        assert top["position"] == "sticky" and abs(top["top"]) <= 0.5 and top["bottom"] > 40, (name, top)
        page.context.close()


@pytest.mark.parametrize("lang", ["en", "pl"])
def test_scale_segments_fit_their_words(site, lang):
    """The fix round's point 7 on a phone (390 x 664, touch), in English and in Polish: each segment of the scale's
    switch is as wide as its words (the room inside its padding is its words' width, unless the touch minimum of
    44 px is wider), the words on one line and none cut (scrollWidth within clientWidth); no two segments overlap."""
    page = _page(site, SMALL_PHONE, lang=lang)
    segments = page.evaluate(SCALE_JS)
    assert len(segments) == 3 and all(s["text"] for s in segments), segments
    for s in segments:
        assert s["scroll"] <= s["client"] and s["lines"] == 1, s
        assert abs(s["room"] - s["words"]) <= 1 or abs(s["box"][2] - s["box"][0] - s["least"]) <= 0.5, s
    for a in segments:
        for b in segments:
            if a is not b:
                apart = a["box"][2] <= b["box"][0] or b["box"][2] <= a["box"][0] or a["box"][3] <= b["box"][1] or b["box"][3] <= a["box"][1]
                assert apart, (a, b)
    assert len({round(s["box"][2] - s["box"][0]) for s in segments}) > 1, segments  # not three equal parts
    assert page.errors == [], page.errors
    page.context.close()
