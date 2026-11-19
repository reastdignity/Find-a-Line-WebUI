"""The new search's page (#new of C) on phones and desktops in Playwright's Edge, over the app's page with test_web's
stubs (no event stream, the estimates answered here): the place map's two arrangements of its controls (step 3c, the
user's pick A2 of 2026-11-19: viewer/src/app/PlaceMap.ts, coverageLayer.ts) and the phone's unfolded bar (the summary
as plain words and one "Change settings": search/SearchPanel.tsx EstimateBar), and no control of the phone's page
covering another. Every wait is an event with a deadline; a finger's taps keep test_shell_c_view_map's spacing (_tap)."""

import json
import os

import pytest

from test_shell_c_view_map import _tap, _tap_on
from test_web import EDGE, POINT_JS, QUEUE_FULL, WAIT, _playwright, _ready, _search_page, _server

pytestmark = pytest.mark.skipif(not os.path.exists(EDGE) or not _playwright(),
                                reason="needs Microsoft Edge and Playwright (group ui)")

TOUCH = {"device_scale_factor": 3, "is_mobile": True, "has_touch": True}
SMALL_PHONE = {"viewport": {"width": 390, "height": 664}, **TOUCH}  # tools/ui_shots.py's iPhone: the least room
PHONE = {"viewport": {"width": 390, "height": 844}, **TOUCH}
SIDE_PHONE = {"viewport": {"width": 667, "height": 375}, **TOUCH}  # a phone on its side: the narrow frame, a low map
WIDE_SIDE_PHONE = {"viewport": {"width": 844, "height": 390}, **TOUCH}  # on its side, 768 px or more: the columns
DESKTOP = {"viewport": {"width": 1400, "height": 900}}
KEY = "findaline.layer.coverage"  # coverageLayer.ts STORAGE_KEY: the coverage remembered ("1"/"0")
COVERAGE = "Data coverage"  # ui.coverage.layer: the button's words (a desktop), the row's (a phone)
PHONE_RECEIPT = "30–300 m · anchors within 10 m of height · Rig: sag, no-fall zone 5 m, no A-frames · access marked"
LONG_NAME = ("A long name for a trip to the far valley with its many walls and its two lakes over the old huts x")[:100]
# Advanced's values that each add a part of their own to the receipt (search/basic.ts receiptParts), "clear of trees"
# (shown on a phone too, where "trees marked" is not) and two values no part covers ("+ 2 more settings")
LONG_VALUES = {"min_height": 30, "min_high_share": 50, "max_wall_angle": 70, "min_drop": 40, "nmpt": "reject",
               "same_line_square": 3, "max_anchor_diff": 4}

# The place map's controls and the phone page's other controls, each by its own class: [name, its box as it shows
# (clipped to what scrolls it: the layers' list, the form's column; left out when scrolled away), its whole box]; the
# map's box, the layers' box, and the list's scrolling
CONTROLS_JS = """() => {
  const rect = (e) => { const r = e.getBoundingClientRect(); return [r.left, r.top, r.right, r.bottom]; };
  const shown = (e) => !!e && e.getClientRects().length > 0 && getComputedStyle(e).visibility !== 'hidden' && !e.closest('[hidden]');
  const clip = (a, b) => [Math.max(a[0], b[0]), Math.max(a[1], b[1]), Math.min(a[2], b[2]), Math.min(a[3], b[3])];
  const out = [];
  const add = (name, e, within) => { if (!shown(e)) return; const whole = rect(e), r = within ? clip(whole, rect(within)) : whole;
    if (r[2] - r[0] > 0.5 && r[3] - r[1] > 0.5) out.push([name, r, whole]); };
  const $ = (s) => document.querySelector(s), $$ = (s) => [...document.querySelectorAll(s)];
  const map = $('.c-placemap'), layers = map.querySelector('.leaflet-control-layers'), list = layers.querySelector('.leaflet-control-layers-list');
  add('zoom in', map.querySelector('.leaflet-control-zoom-in'));
  add('zoom out', map.querySelector('.leaflet-control-zoom-out'));
  add('layers button', map.querySelector('.leaflet-control-layers-toggle'));
  for (const label of list.querySelectorAll('label')) add('row ' + label.textContent.trim(), label, list);
  add('coverage link', list.querySelector('.n-coverage-extra .n-coverage-link'), list);
  add('coverage box', map.querySelector('.n-coverage'));
  add('scale', map.querySelector('.leaflet-control-scale'));
  add('credits', map.querySelector('.leaflet-control-attribution'));
  const form = $('.c-form');
  if (form) {
    for (const tab of $$('.s-tabs [role=tab]')) add('tab ' + tab.dataset.tab, tab, form);
    add('how searching works', $('.s-intro .n-intro-link'), form);
    for (const card of $$('.c-form .s-card')) add('goal ' + card.dataset.goal, card, form);
  }
  add("bar's line", $('.s-sum'));
  add("size's ?", $('.s-size .u-hint'));
  add('change settings', $('.s-change'));
  add('start search', $('.s-start'));
  return {controls: out, map: rect(map), box: shown(layers) ? rect(layers) : null, phone: map.classList.contains('c-map-phone'),
          expanded: layers.classList.contains('leaflet-control-layers-expanded'), listShown: shown(list),
          list: [list.scrollHeight, list.clientHeight, getComputedStyle(list).overflowY], viewport: [innerWidth, innerHeight]};
}"""
# The coverage's state on the place map: PlaceMap.coverage.on, its group on the map, the remembered key, the row's
# checkbox (null without a row), the link shown, the desktop's box and button (aria-pressed), the legend shown
COVERAGE_JS = """(key) => { const place = window.FINDALINE_PLACE, c = place.coverage, $ = (s) => document.querySelector(s);
  const shown = (e) => !!e && e.getClientRects().length > 0 && !e.closest('[hidden]');
  const row = [...document.querySelectorAll('.leaflet-control-layers-overlays label')].find((l) => l.textContent.trim() === %s);
  const link = $('.c-placemap .n-coverage-link'), legend = $('.c-placemap .n-coverage-legend');
  return {on: c.on, onMap: place.map.hasLayer(c.areas), key: localStorage.getItem(key), row: row ? row.querySelector('input').checked : null,
          rows: document.querySelectorAll('.leaflet-control-layers-overlays label').length,
          link: !!link && !link.hidden, linkShown: shown(link), linkInRow: !!link && !!link.closest('.leaflet-control-layers-overlays'),
          box: !!$('.n-coverage'), button: $('.n-coverage-btn')?.getAttribute('aria-pressed') ?? null,
          buttonShown: shown($('.n-coverage-btn')), legend: !!legend && !legend.hidden, legendShown: shown(legend),
          phone: place.map.getContainer().classList.contains('c-map-phone')}; }""" % json.dumps(COVERAGE)
# The coverage's row in the layers' box: the boxes of its checkbox, its words and the link at its end, and what lies
# at the words' middle (the row's label or the link)
ROW_JS = """() => { const rect = (e) => { const r = e.getBoundingClientRect(); return [r.left, r.top, r.right, r.bottom]; };
  const label = [...document.querySelectorAll('.leaflet-control-layers-overlays label')].find((l) => l.textContent.trim() === %s);
  const words = label.querySelector('input + span'), link = document.querySelector('.leaflet-control-layers-overlays .n-coverage-link');
  const w = rect(words), at = document.elementFromPoint((w[0] + w[2]) / 2, (w[1] + w[3]) / 2);
  return {label: rect(label), input: rect(label.querySelector('input')), words: w, link: link && !link.hidden ? rect(link) : null,
          fonts: [...document.querySelectorAll('.leaflet-control-layers-list label span span')].map((s) => getComputedStyle(s).fontSize),
          wordsReach: at ? (at.closest('.n-coverage-link') ? 'link' : at.closest('label') === label ? 'row' : at.className) : null}; }""" % json.dumps(COVERAGE)
STATUS_EMPTY = "() => !document.querySelector('.c-placemap .n-coverage-status')?.textContent"  # the outlines loaded
SHOWN = "(s) => { const e = document.querySelector(s); return !!e && e.getClientRects().length > 0; }"


def _page(browser, port, context: dict, before: str = ""):
    """The new search (#new of C) in a fresh browser context of `context`, `before` run ahead of the page's scripts;
    waits for the form."""
    ctx = browser.new_context(**context)
    if before:
        ctx.add_init_script(before)
    page = ctx.new_page()
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)[:300]))
    page.goto(f"http://127.0.0.1:{port}/runs/basictest/index.html?ui=c#new")
    page.wait_for_selector(".s-panel .s-tabs", timeout=WAIT)
    page.wait_for_selector(".c-placemap .leaflet-control-zoom-in", timeout=WAIT)
    return page


def _overlaps(found: dict, known: set = frozenset()) -> list:
    """The pairs of controls whose boxes (as they show) intersect by more than half a pixel, but for `known` pairs."""
    controls, wrong = found["controls"], []
    for k, (a, p, _) in enumerate(controls):
        for b, q, _ in controls[k + 1:]:
            if frozenset((a, b)) in known:
                continue
            if min(p[2], q[2]) - max(p[0], q[0]) > 0.5 and min(p[3], q[3]) - max(p[1], q[1]) > 0.5:
                wrong.append((a, p, b, q))
    return wrong


MAP_CONTROLS = ("zoom", "layers", "row ", "coverage", "scale", "credits")


def _outside_map(found: dict) -> list:
    """The place map's controls (as they show) and the opened layers' box that leave the map's box."""
    m, out = found["map"], []
    boxes = [(name, r) for name, r, _ in found["controls"] if name.startswith(MAP_CONTROLS)]
    if found["box"]:
        boxes.append(("layers' box", found["box"]))
    for name, r in boxes:
        if r[0] < m[0] - 0.5 or r[1] < m[1] - 0.5 or r[2] > m[2] + 0.5 or r[3] > m[3] + 0.5:
            out.append((name, r, m))
    return out


def _named(found: dict, name: str):
    """A control's whole box by its name (None when it is not shown)."""
    return next((whole for n, _, whole in found["controls"] if n == name), None)


# The link to the coverage page stands at the end of the coverage's row (coverageLayer.css): the one pair allowed to
# meet; ROW_JS checks that it leaves the row's checkbox and words free
LINK_IN_ROW = frozenset({"coverage link", f"row {COVERAGE}"})


def test_place_map_on_a_phone(tmp_path):
    """The place map's phone arrangement (390 x 664 and 390 x 844, touch; PlaceMap.ts PHONE): the layers' box starts
    closed (Leaflet's collapsed control), there is no "Data coverage" box of its own, the zoom's two buttons and the
    layers button are each at least 44 x 44 px, and no map control covers another or leaves the map; a tap on the
    layers button opens the box (its rows at least 44 px high, their words 13 px, the box inside the map, nothing
    covered); ticking "Data
    coverage" (Leaflet's own checkbox of an overlay) puts the layer on the map, shows the link to the coverage page at
    the row's end (clear of the row's checkbox and words) and remembers it ("1"); unticking reverses all three ("0");
    the box stays inside the map after each. A tap on the map closes the box and, in the Point mode, leaves
    the search's centre where it was (PlaceMap skips the click that closes the box; taps on the button and the rows
    leave the centre alone too); the next tap on the map, the box closed, moves the centre to the tapped point. With the key "1" before the page loads the
    layer is on and its row ticked once the box opens. On a phone held sideways (667 x 375, the narrow frame; 844 x 390,
    the columns, the phone's arrangement by the query's second clause) the opened box ends above the map's bottom
    edge and its list scrolls inside where its rows do not fit."""
    from playwright.sync_api import sync_playwright
    _search_page(tmp_path, "", folder_name="basictest")
    r = {}
    with _server(tmp_path) as port, sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            for size, context in (("390x664", SMALL_PHONE), ("390x844", PHONE)):
                page = _page(browser, port, context)
                closed = r[size, "closed"] = page.evaluate(CONTROLS_JS)
                assert closed["phone"] and not closed["expanded"] and not closed["listShown"], (size, closed)
                assert not page.evaluate(COVERAGE_JS, KEY)["box"], size  # the row stands in for the box of its own
                for name in ("zoom in", "zoom out", "layers button"):
                    box = _named(closed, name)
                    assert box and box[2] - box[0] >= 43.5 and box[3] - box[1] >= 43.5, (size, name, box)
                # the zoom's two side by side at the top left, the layers button at the top right
                zin, zout, button, m = _named(closed, "zoom in"), _named(closed, "zoom out"), _named(closed, "layers button"), closed["map"]
                assert zin[1] == zout[1] and zout[0] >= zin[2] - 0.5 and zin[0] - m[0] < 20 and m[2] - button[2] < 20, (size, closed)
                assert button[1] - m[1] < 20 and zin[1] - m[1] < 20, (size, closed)
                assert not _overlaps(closed) and not _outside_map(closed), (size, _overlaps(closed), _outside_map(closed))
                # the centre set; the box opened by a tap on its button (the centre stays)
                page.evaluate(POINT_JS)
                _ready(page)
                centre = page.evaluate("() => window.FINDALINE_SEARCH.point")
                _tap_on(page, ".leaflet-control-layers-toggle")
                page.wait_for_selector(".leaflet-control-layers-expanded", timeout=WAIT)
                opened = r[size, "opened"] = page.evaluate(CONTROLS_JS)
                rows = [(name, whole) for name, _, whole in opened["controls"] if name.startswith("row ")]
                assert [name for name, _ in rows] == ["row OpenTopoMap", "row OpenStreetMap", f"row {COVERAGE}"], (size, rows)
                assert all(whole[3] - whole[1] >= 43.5 for _, whole in rows), (size, rows)
                assert not _overlaps(opened) and not _outside_map(opened), (size, _overlaps(opened), _outside_map(opened))
                before = page.evaluate(COVERAGE_JS, KEY)
                assert (before["on"], before["row"], before["link"], before["key"]) == (False, False, False, None), (size, before)
                # ticked: a tap on the row's words
                words = page.evaluate(ROW_JS)["words"]
                _tap(page, (words[0] + words[2]) / 2, (words[1] + words[3]) / 2)
                page.wait_for_function("() => window.FINDALINE_PLACE.coverage.on", timeout=WAIT)
                page.wait_for_function(STATUS_EMPTY, timeout=WAIT)
                on = r[size, "on"] = page.evaluate(COVERAGE_JS, KEY)
                assert (on["onMap"], on["key"], on["row"], on["link"], on["linkShown"], on["linkInRow"]) == \
                    (True, "1", True, True, True, True), (size, on)
                ticked = r[size, "ticked"] = page.evaluate(CONTROLS_JS)
                assert ticked["expanded"], size  # the box stays open
                assert not _overlaps(ticked) and not _outside_map(ticked), \
                    (size, _overlaps(ticked), _outside_map(ticked))
                row = r[size, "row"] = page.evaluate(ROW_JS)  # the link's place: checked at the end (_link_at_row_end)
                # unticked: a tap on the row's checkbox
                box = row["input"]
                _tap(page, (box[0] + box[2]) / 2, (box[1] + box[3]) / 2)
                page.wait_for_function("() => !window.FINDALINE_PLACE.coverage.on", timeout=WAIT)
                off = r[size, "off"] = page.evaluate(COVERAGE_JS, KEY)
                assert (off["onMap"], off["key"], off["row"], off["link"], off["linkShown"]) == (False, "0", False, False, False), (size, off)
                assert page.evaluate("() => window.FINDALINE_SEARCH.point") == centre, size  # taps in the box
                unticked = page.evaluate(CONTROLS_JS)
                assert unticked["expanded"] and not _overlaps(unticked) and not _outside_map(unticked), (size, unticked)
                # a tap on the map, clear of its controls: the box closes and the centre stays; a second tap moves it there
                m = unticked["map"]
                x, y = m[0] + 120, (m[1] + m[3]) / 2
                tapped = page.evaluate("([x, y]) => { const map = window.FINDALINE_PLACE.map, b = map.getContainer().getBoundingClientRect(); "
                                       "const at = map.containerPointToLatLng([x - b.left, y - b.top]); return [at.lat, at.lng]; }", [x, y])
                assert page.evaluate("([x, y]) => !!document.elementFromPoint(x, y)?.closest('.leaflet-tile-pane, .leaflet-container') && "
                                     "!document.elementFromPoint(x, y)?.closest('.leaflet-control')", [x, y]), size
                _tap(page, x, y)
                page.wait_for_selector(".leaflet-control-layers-expanded", state="detached", timeout=WAIT)
                assert page.evaluate("() => window.FINDALINE_SEARCH.point") == centre, size  # the closing tap sets no centre
                _tap(page, x, y)
                page.wait_for_function("(c) => String(window.FINDALINE_SEARCH.point) !== String(c)", arg=centre, timeout=WAIT)
                moved = r[size, "moved"] = page.evaluate("() => window.FINDALINE_SEARCH.point")
                assert moved != centre and abs(moved[0] - tapped[0]) < 1e-4 and abs(moved[1] - tapped[1]) < 1e-4, (size, centre, moved, tapped)
                again = page.evaluate(CONTROLS_JS)
                assert not again["expanded"] and not again["listShown"], size
                assert page.errors == [], (size, page.errors)
                page.context.close()
            # the key "1" before the page loads: the layer on, its row ticked once the box opens
            page = _page(browser, port, PHONE, f"try {{ localStorage.setItem('{KEY}', '1'); }} catch (e) {{}}")
            _tap_on(page, ".leaflet-control-layers-toggle")
            page.wait_for_selector(".leaflet-control-layers-expanded", timeout=WAIT)
            r["remembered"] = page.evaluate(COVERAGE_JS, KEY)
            assert (r["remembered"]["on"], r["remembered"]["onMap"], r["remembered"]["row"], r["remembered"]["linkShown"]) == \
                (True, True, True, True), r["remembered"]
            page.context.close()
            # sideways: the opened box ends above the map's bottom edge; its list scrolls where its rows do not fit
            for size, context in (("667x375", SIDE_PHONE), ("844x390", WIDE_SIDE_PHONE)):
                page = _page(browser, port, context)
                page.evaluate(POINT_JS)
                _ready(page)
                _tap_on(page, ".leaflet-control-layers-toggle")
                page.wait_for_selector(".leaflet-control-layers-expanded", timeout=WAIT)
                side = r[size, "side"] = page.evaluate(CONTROLS_JS)
                assert side["phone"], (size, side)
                assert side["box"][3] <= side["map"][3] + 0.5 and not _outside_map(side) and not _overlaps(side), (size, side)
                height, room, overflow = side["list"]
                # three rows of 44 px and the rule between them (143 px): under the 128 px map of the narrow frame they do
                # not fit and the list scrolls; in the columns (a 196 px map) the box shows them all, 8 px above the edge
                if size == "667x375":
                    assert height > room and overflow in ("auto", "scroll"), (size, side)
                else:
                    assert height <= room + 0.5 and side["map"][3] - side["box"][3] >= 7.5, (size, side)
                # ticked (the row scrolled into view first, as a finger would): the link at the row's end
                page.evaluate("() => [...document.querySelectorAll('.leaflet-control-layers-overlays label')].pop().scrollIntoView({block: 'nearest'})")
                words = page.evaluate(ROW_JS)["words"]
                _tap(page, (words[0] + words[2]) / 2, (words[1] + words[3]) / 2)
                page.wait_for_function("() => window.FINDALINE_PLACE.coverage.on", timeout=WAIT)
                page.wait_for_function(STATUS_EMPTY, timeout=WAIT)
                ticked = r[size, "side ticked"] = page.evaluate(CONTROLS_JS)
                assert ticked["box"][3] <= ticked["map"][3] + 0.5 and not _outside_map(ticked), (size, ticked)
                r[size, "row"] = page.evaluate(ROW_JS)
                r[size, "side overlaps"] = _overlaps(ticked)
                assert page.errors == [], (size, page.errors)
                page.context.close()
        finally:
            browser.close()
    print("the place map on phones: " + json.dumps({" ".join(k) if isinstance(k, tuple) else k: v for k, v in r.items()}))
    # the link to the coverage page at the coverage row's end (coverageLayer.css), at every size: within the row's
    # band, clear of the row's checkbox and words (a tap on the words reaches the row, not the link), over no other row
    # and the box's rows' words at R1's 13 px (result/view/mapbar.css: "their words 13 px"); both findings in one
    # message, so neither hides the other
    sizes = ("390x664", "390x844", "667x375", "844x390")
    misplaced = {size: r[size, "row"] for size in sizes if not _link_at_row_end(r[size, "row"])}
    fonts = {size: r[size, "row"]["fonts"] for size in sizes if set(r[size, "row"]["fonts"]) != {"13px"}}
    assert not misplaced and not fonts, {"link not at the row's end": misplaced, "rows' words not 13 px": fonts}
    assert r["667x375", "side overlaps"] == r["844x390", "side overlaps"] == [], r


def _link_at_row_end(row: dict) -> bool:
    """ROW_JS's boxes: the link shown, its middle within the row's height, left of it the row's checkbox and words
    whole, and a tap on the words' middle reaching the row."""
    link, label = row["link"], row["label"]
    return bool(link) and label[1] - 0.5 <= (link[1] + link[3]) / 2 <= label[3] + 0.5 and \
        link[0] >= row["input"][2] - 0.5 and link[0] >= row["words"][2] - 0.5 and row["wordsReach"] == "row"


def test_place_map_on_a_desktop(tmp_path):
    """The place map's desktop arrangement (1400 x 900, a mouse): the zoom's buttons hold the kit's icons (an svg, no
    "+" or "−"); the box "Data coverage" with its button among the controls at the bottom right, and no coverage row
    in the layers' box; the button switches the layer (PlaceMap.coverage.on), its aria-pressed, the legend and the link
    to the coverage page, and the remembered key. Made 390 x 664 and back, the same PlaceMap follows (PlaceMap.ts:
    the media query's change): the row in the layers' box (ticked) and no box of its own on the phone's width, the
    box with its button pressed back on the desktop's, the layer on through both changes. The key is set to "0" behind
    the page after the layer is switched on, so a page that read it again would show the layer off."""
    from playwright.sync_api import sync_playwright
    _search_page(tmp_path, "", folder_name="basictest")
    r = {}
    with _server(tmp_path) as port, sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _page(browser, port, DESKTOP)
            r["zoom"] = page.evaluate("""() => [...document.querySelectorAll('.c-placemap .leaflet-control-zoom a')].map((a) =>
                [a.className.split(' ')[0], !!a.querySelector('svg.u-ic'), a.textContent.trim()])""")
            r["first"] = page.evaluate(COVERAGE_JS, KEY)
            r["corner"] = page.evaluate("() => !!document.querySelector('.leaflet-bottom.leaflet-right .n-coverage .n-coverage-btn') && "
                                        "!document.querySelector('.leaflet-control-layers .n-coverage-extra')")
            page.click(".n-coverage-btn")
            page.wait_for_function("() => window.FINDALINE_PLACE.coverage.on", timeout=WAIT)
            page.wait_for_function(STATUS_EMPTY, timeout=WAIT)
            r["on"] = page.evaluate(COVERAGE_JS, KEY)
            page.click(".n-coverage-btn")
            page.wait_for_function("() => !window.FINDALINE_PLACE.coverage.on", timeout=WAIT)
            r["off"] = page.evaluate(COVERAGE_JS, KEY)
            page.click(".n-coverage-btn")
            page.wait_for_function("() => window.FINDALINE_PLACE.coverage.on", timeout=WAIT)
            page.evaluate(f"() => {{ window.PLACE_BEFORE = window.FINDALINE_PLACE; localStorage.setItem('{KEY}', '0'); }}")
            page.set_viewport_size({"width": 390, "height": 664})
            page.wait_for_selector(".c-placemap.c-map-phone", timeout=WAIT)
            r["narrow"] = page.evaluate(COVERAGE_JS, KEY)
            r["narrow_same"] = page.evaluate("() => window.FINDALINE_PLACE === window.PLACE_BEFORE")
            page.set_viewport_size({"width": 1400, "height": 900})
            page.wait_for_selector(".c-placemap:not(.c-map-phone) .n-coverage-btn", timeout=WAIT)
            r["wide"] = page.evaluate(COVERAGE_JS, KEY)
            r["wide_same"] = page.evaluate("() => window.FINDALINE_PLACE === window.PLACE_BEFORE")
            r["errors"] = page.errors
        finally:
            browser.close()
    assert r["zoom"] == [["leaflet-control-zoom-in", True, ""], ["leaflet-control-zoom-out", True, ""]], r
    first = r["first"]
    assert not first["phone"] and first["box"] and first["buttonShown"] and first["rows"] == 0 and r["corner"], r
    assert (first["on"], first["button"], first["legend"], first["link"], first["key"]) == (False, "false", False, False, None), r
    on = r["on"]
    assert (on["on"], on["onMap"], on["button"], on["legendShown"], on["linkShown"], on["linkInRow"], on["key"]) == \
        (True, True, "true", True, True, False, "1"), r
    off = r["off"]
    assert (off["on"], off["onMap"], off["button"], off["legendShown"], off["linkShown"], off["key"]) == \
        (False, False, "false", False, False, "0"), r
    narrow = r["narrow"]
    assert narrow["phone"] and not narrow["box"] and narrow["rows"] == 1 and narrow["row"] is True, r
    assert (narrow["on"], narrow["onMap"], narrow["key"]) == (True, True, "0") and r["narrow_same"], r
    wide = r["wide"]
    assert not wide["phone"] and wide["box"] and wide["rows"] == 0 and wide["button"] == "true" and wide["legendShown"], r
    assert (wide["on"], wide["onMap"]) == (True, True) and r["wide_same"], r
    assert r["errors"] == [], r


RECEIPT_JS = """() => { const receipt = document.querySelector('.s-receipt'), shown = (e) => e.getClientRects().length > 0;
  const changes = [...document.querySelectorAll('.s-change')].filter(shown);
  return {text: receipt.innerText, parts: [...receipt.querySelectorAll('[data-field]')].filter(shown).map((e) => e.textContent).join(' · '),
          controls: receipt.querySelectorAll('button, a, input, [tabindex]').length, changes: changes.map((b) => [b.textContent.trim(),
          b.getBoundingClientRect().height]), open: !!document.querySelector('.s-bar.s-open'),
          expanded: document.querySelector('.s-sum')?.getAttribute('aria-expanded') ?? null,
          tab: document.querySelector('.s-tabs [aria-selected=true]').dataset.tab}; }"""
# "Start search" whole inside the viewport and what a tap at its middle reaches; the summary's box and its scrolling
START_JS = """() => { const s = document.querySelector('.s-start').getBoundingClientRect(), x = (s.left + s.right) / 2, y = (s.top + s.bottom) / 2;
  const receipt = document.querySelector('.s-receipt'), r = receipt.getBoundingClientRect();
  return {start: [s.left, s.top, s.right, s.bottom], viewport: [innerWidth, innerHeight], reaches: !!document.elementFromPoint(x, y)?.closest('.s-start'),
          receipt: [r.top, r.bottom, receipt.scrollHeight, receipt.clientHeight, getComputedStyle(receipt).overflowY], text: receipt.innerText,
          middle: [x, y]}; }"""


def test_unfolded_bar_on_a_phone(tmp_path):
    """The phone's bar (the user's pick of 2026-11-19): unfolded, the summary is plain words (no button, link or field
    in it), its text the parts joined by " · " as before; one "Change settings" shows, at least 44 px high; a tap on it
    opens the Advanced tab and folds the bar, where it is not displayed. On a desktop no "Change settings" shows and the
    summary's parts are buttons that open their setting. With the longest summary the page makes (Advanced: a value
    for every part of its own, two more settings, a name of 100 characters), at 390 x 664 and 667 x 375 unfolded,
    "Start search" lies whole inside the viewport and a tap at its middle starts the search (its request sent, with the
    name), and the summary scrolls inside its box where it does not fit (667 x 375) and never reaches over "Start
    search"."""
    from playwright.sync_api import sync_playwright
    _search_page(tmp_path, "", folder_name="basictest")
    r = {}
    with _server(tmp_path) as port, sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _page(browser, port, PHONE)
            page.evaluate(POINT_JS)
            _ready(page)
            r["folded"] = page.evaluate(RECEIPT_JS)
            _tap_on(page, ".s-sum")
            page.wait_for_function("() => getComputedStyle(document.querySelector('.s-receipt')).display !== 'none'", timeout=WAIT)
            r["unfolded"] = page.evaluate(RECEIPT_JS)
            _tap_on(page, ".s-change")
            page.wait_for_function("() => window.FINDALINE_SEARCH.tab === 'advanced'", timeout=WAIT)
            page.wait_for_function("() => !document.querySelector('.s-bar.s-open')", timeout=WAIT)
            r["changed"] = page.evaluate(RECEIPT_JS)
            r["errors"] = page.errors
            page.context.close()
            # a desktop: no "Change settings", the parts are buttons that open their setting
            page = _page(browser, port, DESKTOP)
            page.evaluate(POINT_JS)
            _ready(page)
            r["desktop"] = page.evaluate(RECEIPT_JS)
            r["desktop_buttons"] = page.evaluate("() => [...document.querySelectorAll('.s-receipt button[data-field]')].map((b) => b.dataset.field)")
            page.click(".s-receipt button[data-field=max_anchor_diff_m]")
            page.wait_for_function("() => document.activeElement?.closest('[data-field=max_anchor_diff_m]')", timeout=WAIT)
            r["desktop_opened"] = page.evaluate("() => window.FINDALINE_SEARCH.tab")
            page.context.close()
            # the longest summary: Start whole in the viewport and reached by a tap; the summary scrolls inside
            for size, context in (("390x664", SMALL_PHONE), ("667x375", SIDE_PHONE)):
                page = _page(browser, port, context)
                sent = []
                page.route("**/api/jobs", lambda route: (sent.append(route.request.post_data_json),
                                                         route.fulfill(status=409, content_type="application/json", body=json.dumps(QUEUE_FULL)))
                           if route.request.method == "POST" else route.continue_())
                page.evaluate(POINT_JS)
                _ready(page)
                _tap_on(page, ".s-tabs [data-tab=advanced]")
                page.wait_for_function("() => window.FINDALINE_SEARCH.tab === 'advanced'", timeout=WAIT)
                asked = page.evaluate("() => ESTIMATES.length")
                page.evaluate("(values) => { for (const [k, v] of Object.entries(values)) window.FINDALINE_SEARCH.setValue(k, v); }", LONG_VALUES)
                page.fill(".s-pane input[placeholder='from OpenStreetMap']", LONG_NAME)
                page.wait_for_function(f"() => ESTIMATES.length > {asked} && document.querySelector('.s-bar').dataset.estimate === 'ready' "
                                       f"&& window.FINDALINE_SEARCH.request.params?.name === {json.dumps(LONG_NAME)}", timeout=WAIT)
                _tap_on(page, ".s-sum")
                page.wait_for_function("() => getComputedStyle(document.querySelector('.s-receipt')).display !== 'none'", timeout=WAIT)
                found = r[size] = page.evaluate(START_JS)
                s, (w, h) = found["start"], found["viewport"]
                assert s[0] >= 0 and s[1] >= 0 and s[2] <= w and s[3] <= h and found["reaches"], (size, found)
                _tap(page, *found["middle"])
                page.wait_for_selector(".s-bar-error", timeout=WAIT)  # the refused start (QUEUE_FULL) says so
                r[size, "sent"] = [body["params"].get("name") for body in sent]
                r[size, "errors"] = page.errors
                page.context.close()
        finally:
            browser.close()
    assert r["folded"]["changes"] == [] and not r["folded"]["open"] and r["folded"]["expanded"] == "false", r
    unfolded = r["unfolded"]
    assert unfolded["open"] and unfolded["controls"] == 0, r  # plain words: nothing to press in the summary
    assert unfolded["text"] == unfolded["parts"] == PHONE_RECEIPT, r
    assert len(unfolded["changes"]) == 1 and unfolded["changes"][0][0] == "Change settings" and unfolded["changes"][0][1] >= 43.5, r
    changed = r["changed"]
    assert changed["tab"] == "advanced" and not changed["open"] and changed["expanded"] == "false" and changed["changes"] == [], r
    assert r["errors"] == [], r
    desktop = r["desktop"]
    assert desktop["changes"] == [] and desktop["controls"] >= 5 and desktop["expanded"] is None, r
    assert r["desktop_buttons"][:3] == ["min_length", "max_anchor_diff_m", "nmpt"] and r["desktop_opened"] == "advanced", r
    for size in ("390x664", "667x375"):
        found = r[size]  # Start whole in the viewport and reached: asserted before its tap
        top, bottom, height, room, overflow = found["receipt"]
        s = found["start"]
        assert bottom <= s[1] + 0.5, (size, found)  # the summary never reaches over Start
        assert "clear of trees" in found["text"] and "+ 2 more settings" in found["text"] and LONG_NAME in found["text"], (size, found)
        assert height <= room + 1 or overflow in ("auto", "scroll"), (size, found)
        assert r[size, "sent"] == [LONG_NAME] and r[size, "errors"] == [], (size, r[size, "sent"], r[size, "errors"])
    # on its side the summary has no room for its lines: it scrolls inside its box
    assert r["667x375"]["receipt"][2] > r["667x375"]["receipt"][3], r["667x375"]
    print("the longest summary: " + json.dumps({k: r[k] for k in ("390x664", "667x375")}))


def test_phone_search_controls_apart(tmp_path):
    """A small phone (390 x 664, touch) on the new search, the bar folded and unfolded, the layers' box closed and
    opened: no two controls' boxes intersect (each named by its own class: the zoom's two buttons, the layers button or
    the box's rows, the scale and the credits, the tabs, "How searching works", the goal cards, the bar's line, the size
    word's "?", "Change settings", "Start search"), and the map's controls stay inside the map. The form's column
    scrolls under nothing but its own edges (it is a grid row of its own between the map and the bar): a control of
    the form counts with the part of it the column shows (clipped to the column's box), and one scrolled out of the
    column does not count; the bar's and the map's controls count whole."""
    from playwright.sync_api import sync_playwright
    _search_page(tmp_path, "", folder_name="basictest")
    seen = {}
    with _server(tmp_path) as port, sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _page(browser, port, SMALL_PHONE)
            page.evaluate(POINT_JS)
            _ready(page)
            for bar in ("folded", "unfolded"):
                if bar == "unfolded":
                    _tap_on(page, ".s-sum")
                    page.wait_for_function("() => document.querySelector('.s-bar.s-open')", timeout=WAIT)
                for box in ("closed", "opened"):
                    if box == "opened":
                        _tap_on(page, ".leaflet-control-layers-toggle")
                        page.wait_for_selector(".leaflet-control-layers-expanded", timeout=WAIT)
                    found = seen[bar, box] = page.evaluate(CONTROLS_JS)
                    names = {name for name, _, _ in found["controls"]}
                    want = {"zoom in", "zoom out", "tab basic", "tab advanced", "how searching works", "bar's line", "size's ?",
                            "start search", "scale", "credits"}
                    want |= {"layers button"} if box == "closed" else {"row OpenTopoMap", "row OpenStreetMap", f"row {COVERAGE}"}
                    want |= {"change settings"} if bar == "unfolded" else set()
                    assert want <= names, (bar, box, sorted(want - names))
                    assert ("change settings" in names) == (bar == "unfolded"), (bar, box, sorted(names))
                    assert any(name.startswith("goal ") for name in names), (bar, box, sorted(names))
                    assert not _overlaps(found), (bar, box, _overlaps(found))
                    assert not _outside_map(found), (bar, box, _outside_map(found))
                    if box == "opened":  # closed again by a tap on the map (the centre stays)
                        m = found["map"]
                        _tap(page, m[0] + 120, (m[1] + m[3]) / 2)
                        page.wait_for_selector(".leaflet-control-layers-expanded", state="detached", timeout=WAIT)
            assert page.errors == [], page.errors
        finally:
            browser.close()
    print("phone 390 x 664, the search page's controls: " + json.dumps({" ".join(k): v["controls"] for k, v in seen.items()}))
