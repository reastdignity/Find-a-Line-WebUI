"""The new search's page (#new of C) on phones and desktops in Playwright's Edge, over the app's page with test_web's
stubs (no event stream, the estimates answered here): the place map's two arrangements of its controls (step 3c, the
user's pick A2 of 2026-11-19: viewer/src/app/PlaceMap.ts, coverageLayer.ts) and the phone's unfolded bar (the summary
as plain words and one "Change settings": search/SearchPanel.tsx EstimateBar), and no control of the phone's page
covering another; the coverage's choice across a page change, the map's listeners after it, the layers' box and
the focus across a resize, the closing press by finger and by mouse, the drawing tools' row on a phone, the layers'
list cut mid-row, one box width with the coverage ticked or not, and the layers' button's icon. Every wait is an
event with a deadline; a finger's taps keep test_shell_c_view_map's spacing (_tap)."""

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
# map's box, the layers' box, and the list's scrolling. The link "Coverage map" stands beside the coverage's row's
# label in the list (coverageLayer.ts dress()) and counts only while it shows: while the layer is off it keeps its
# room hidden (coverageLayer.css: `visibility: hidden`, so the box has one width), which `shown` leaves out. The
# drawing tools (Leaflet-Geoman's buttons; Advanced, the place kind "Area") count each by its title
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
  add('coverage link', list.querySelector('.leaflet-control-layers-overlays .n-coverage-link'), list);
  add('coverage box', map.querySelector('.n-coverage'));
  for (const a of map.querySelectorAll('.leaflet-pm-toolbar a.leaflet-buttons-control-button')) add('tool ' + (a.parentElement.title || a.className), a);
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


MAP_CONTROLS = ("zoom", "layers", "row ", "coverage", "scale", "credits", "tool ")


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


# The link to the coverage page stands beside the coverage's row's label, not inside it (coverageLayer.css: the two in
# a flex row, 8 px apart; measured 2026-11-19 at 390 x 664, 390 x 844, 667 x 375 and 844 x 390: the label ends 8 px
# left of the link), so no pair of controls is allowed to meet; ROW_JS checks that it leaves the row's checkbox and
# words free


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
                assert _named(ticked, "coverage link"), (size, ticked)  # the link counts among the controls
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
                assert not _named(unticked, "coverage link"), (size, unticked)  # hidden (its room kept): not shown
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
                assert _named(ticked, "coverage link"), (size, ticked)
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


TABLET = {"viewport": {"width": 1024, "height": 768}, "device_scale_factor": 2, "is_mobile": True, "has_touch": True}
# Errors of the page's own listeners, kept by the page (a listener that throws reports to the window's "error")
ERRORS_KEPT = "window.ERRORS = []; addEventListener('error', (e) => window.ERRORS.push(String(e.message).slice(0, 300)));"
TWO_FRAMES = "() => new Promise((ok) => requestAnimationFrame(() => requestAnimationFrame(ok)))"
# The live place map's arrangement (window.FINDALINE_PLACE, the map of the page shown): the phone's class, the corner
# that holds the zoom and the one that holds the layers' button, the boxes of the map and the zoom-in, the coverage's
# own box shown, and whether the map is in the document
ARRANGED_JS = """() => { const m = window.FINDALINE_PLACE.map.getContainer(), rect = (e) => { const r = e.getBoundingClientRect(); return [r.left, r.top, r.right, r.bottom]; };
  const corner = (e) => { const c = e && e.closest('.leaflet-top, .leaflet-bottom'); return c ? c.className.replace(/\\s+/g, ' ').trim() : null; };
  const zin = m.querySelector('.leaflet-control-zoom-in');
  return {phone: m.classList.contains('c-map-phone'), connected: m.isConnected, zoom: corner(zin), layers: corner(m.querySelector('.leaflet-control-layers-toggle')),
          map: rect(m), zin: rect(zin), box: !!m.querySelector('.n-coverage') && m.querySelector('.n-coverage').getClientRects().length > 0}; }"""
# The layers' list: its box, its client height and scrolling, its rows (labels) by their words, and the link's box,
# visibility and `hidden`
LIST_JS = """() => { const rect = (e) => { const r = e.getBoundingClientRect(); return [r.left, r.top, r.right, r.bottom]; };
  const map = window.FINDALINE_PLACE.map.getContainer(), box = map.querySelector('.leaflet-control-layers'), list = box.querySelector('.leaflet-control-layers-list');
  const link = list.querySelector('.leaflet-control-layers-overlays .n-coverage-link');
  return {box: rect(box), map: rect(map), list: rect(list), height: list.scrollHeight, room: list.clientHeight, top: list.scrollTop,
          expanded: box.classList.contains('leaflet-control-layers-expanded'), rows: [...list.querySelectorAll('label')].map((l) => [l.textContent.trim(), rect(l)]),
          link: link ? {box: rect(link), visibility: getComputedStyle(link).visibility, hidden: link.hidden} : null}; }"""
# A point of the map (viewport coordinates) as the map's latitude and longitude, and whether the map's own surface
# (not a control) is there
LATLNG_JS = """([x, y]) => { const map = window.FINDALINE_PLACE.map, b = map.getContainer().getBoundingClientRect(), at = map.containerPointToLatLng([x - b.left, y - b.top]);
  const e = document.elementFromPoint(x, y); return {at: [at.lat, at.lng], free: !!e?.closest('.leaflet-container') && !e?.closest('.leaflet-control')}; }"""


def _leave_and_return(page) -> str:
    """To Home and back to the search page by the address (as the app's "Home" and "New search" go): the key while on
    Home, read once the page's map is removed (Leaflet's "unload" of that map seen); back, it waits for the new
    PlaceMap (window.FINDALINE_PLACE another object, its map in the document)."""
    page.evaluate("() => { const before = window.PLACE_BEFORE = window.FINDALINE_PLACE; window.UNLOADED = false; "
                  "before.map.on('unload', () => { window.UNLOADED = true; }); location.hash = '#home'; }")
    page.wait_for_selector(".c-home", timeout=WAIT)
    page.wait_for_function("() => window.UNLOADED", timeout=WAIT)
    away = page.evaluate(f"() => localStorage.getItem('{KEY}')")
    page.evaluate("() => { location.hash = '#new'; }")
    page.wait_for_function("() => window.FINDALINE_PLACE && window.FINDALINE_PLACE !== window.PLACE_BEFORE && "
                           "window.FINDALINE_PLACE.map.getContainer().isConnected", timeout=WAIT)
    page.wait_for_selector(".c-placemap .leaflet-control-zoom-in", timeout=WAIT)
    return away


def test_coverage_kept_across_pages(tmp_path):
    """The coverage's choice survives leaving the page (coverageLayer.ts: the map's own removal on leaving takes every
    layer off, which no longer counts as switching it off). On a desktop (1400 x 900, the box's button) and a phone
    (390 x 844, touch, the row in the layers' box): ticked, the key findaline.layer.coverage is "1" while on Home and
    after the return, and the new PlaceMap shows the layer on (coverage.on, its group on the map; the desktop's button
    pressed, the phone's row ticked); switched off, the key stays "0" the same way and the layer is off on return. A
    reload keeps either (the desktop)."""
    from playwright.sync_api import sync_playwright
    _search_page(tmp_path, "", folder_name="basictest")
    r = {}

    def kept(device: str, state: str):
        """Asserted at once (a later step would act on the wrong state): the key on Home, the layer after the return."""
        want, on = ("1", True) if state == "on" else ("0", False)
        away, back = r[f"{device} {state}", "away"], r[f"{device} {state}", "back"]
        assert away == want, (device, state, "the key while on Home", away)
        assert (back["key"], back["on"], back["onMap"]) == (want, on, on), (device, state, "back on the search page", back)
        if device == "desktop":
            assert back["button"] == str(on).lower(), (device, state, back)
        else:
            assert back["phone"] and back["row"] is on, (device, state, back)

    def reloaded(state: str):
        want, on = ("1", True) if state == "on" else ("0", False)
        found = r[f"desktop {state}", "reloaded"]
        assert (found["key"], found["on"], found["onMap"], found["button"]) == (want, on, on, str(on).lower()), (state, "reloaded", found)

    with _server(tmp_path) as port, sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _page(browser, port, DESKTOP)
            page.click(".n-coverage-btn")
            page.wait_for_function("() => window.FINDALINE_PLACE.coverage.on", timeout=WAIT)
            r["desktop on", "away"] = _leave_and_return(page)
            r["desktop on", "back"] = page.evaluate(COVERAGE_JS, KEY)
            kept("desktop", "on")
            page.reload()
            page.wait_for_selector(".c-placemap .n-coverage-btn", timeout=WAIT)
            r["desktop on", "reloaded"] = page.evaluate(COVERAGE_JS, KEY)
            reloaded("on")
            page.click(".n-coverage-btn")
            page.wait_for_function("() => !window.FINDALINE_PLACE.coverage.on", timeout=WAIT)
            r["desktop off", "away"] = _leave_and_return(page)
            r["desktop off", "back"] = page.evaluate(COVERAGE_JS, KEY)
            kept("desktop", "off")
            page.reload()
            page.wait_for_selector(".c-placemap .n-coverage-btn", timeout=WAIT)
            r["desktop off", "reloaded"] = page.evaluate(COVERAGE_JS, KEY)
            reloaded("off")
            r["desktop errors"] = page.errors
            page.context.close()
            page = _page(browser, port, PHONE)
            _tap_on(page, ".leaflet-control-layers-toggle")
            page.wait_for_selector(".leaflet-control-layers-expanded", timeout=WAIT)
            words = page.evaluate(ROW_JS)["words"]
            _tap(page, (words[0] + words[2]) / 2, (words[1] + words[3]) / 2)
            page.wait_for_function("() => window.FINDALINE_PLACE.coverage.on", timeout=WAIT)
            r["phone on", "away"] = _leave_and_return(page)
            r["phone on", "back"] = page.evaluate(COVERAGE_JS, KEY)
            kept("phone", "on")
            _tap_on(page, ".leaflet-control-layers-toggle")
            page.wait_for_selector(".leaflet-control-layers-expanded", timeout=WAIT)
            box = page.evaluate(ROW_JS)["input"]
            _tap(page, (box[0] + box[2]) / 2, (box[1] + box[3]) / 2)
            page.wait_for_function("() => !window.FINDALINE_PLACE.coverage.on", timeout=WAIT)
            r["phone off", "away"] = _leave_and_return(page)
            r["phone off", "back"] = page.evaluate(COVERAGE_JS, KEY)
            kept("phone", "off")
            r["phone errors"] = page.errors
        finally:
            browser.close()
            print("the coverage across pages: " + json.dumps({" ".join(k) if isinstance(k, tuple) else k: v for k, v in r.items()}))
    assert r["desktop errors"] == r["phone errors"] == [], r


def test_breakpoint_after_the_page_was_left(tmp_path):
    """The window's media listener goes with the map (PlaceMap.ts: removed on the map's "unload"): the search page
    entered, left to Home and entered again, the window made narrow and wide across 768 px both ways (1000 -> 600 ->
    1000 and 600 -> 1000 -> 600, a mouse) raises no error in the page (Playwright's pageerror and the page's own
    "error" events: the removed map's arrangement threw "Cannot read properties of undefined (reading 'bottomright')"),
    and the live map is arranged right at each step: narrow, the phone's class with the zoom at the top left and the
    layers' button at the top right and no coverage box; wide, the zoom and the layers' button at the bottom right
    with the coverage's own box."""
    from playwright.sync_api import sync_playwright
    _search_page(tmp_path, "", folder_name="basictest")
    r = {}
    with _server(tmp_path) as port, sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            for start, other in ((1000, 600), (600, 1000)):
                page = _page(browser, port, {"viewport": {"width": start, "height": 800}}, ERRORS_KEPT)
                _leave_and_return(page)
                steps = r[start] = []
                for width in (other, start):
                    page.set_viewport_size({"width": width, "height": 800})
                    page.wait_for_function("(phone) => window.FINDALINE_PLACE.map.getContainer().classList.contains('c-map-phone') === phone",
                                           arg=width < 768, timeout=WAIT)
                    page.evaluate(TWO_FRAMES)
                    steps.append((width, page.evaluate(ARRANGED_JS)))
                r[start, "errors"] = page.errors + page.evaluate("() => window.ERRORS")
                page.context.close()
        finally:
            browser.close()
    print("the breakpoint after leaving: " + json.dumps({" ".join(map(str, k)) if isinstance(k, tuple) else str(k): v for k, v in r.items()}))
    # the errors first: they are what the removed map's listener left
    assert r[1000, "errors"] == [] and r[600, "errors"] == [], {"1000 -> 600 -> 1000": r[1000, "errors"], "600 -> 1000 -> 600": r[600, "errors"]}
    for start in (1000, 600):
        for width, found in r[start]:
            m, z = found["map"], found["zin"]
            assert found["connected"], (start, width, found)
            if width < 768:
                assert found["phone"] and found["zoom"] == "leaflet-top leaflet-left" and found["layers"] == "leaflet-top leaflet-right", (start, width, found)
                assert z[0] - m[0] < 20 and z[1] - m[1] < 20 and not found["box"], (start, width, found)
            else:
                assert not found["phone"] and found["zoom"] == found["layers"] == "leaflet-bottom leaflet-right", (start, width, found)
                assert m[2] - z[2] < 20 and z[3] > (m[1] + m[3]) / 2 and found["box"], (start, width, found)


def test_box_and_focus_across_resizes(tmp_path):
    """An open layers' box is fitted again when the map's size changes (PlaceMap.ts: expand() again on the map's
    "resize"): opened at 390 x 844 (touch; its list does not scroll there) and turned to 667 x 375, the box ends above
    the map's bottom edge, its list scrolls (scrollHeight over clientHeight), and scrolled to its end the last row
    "Data coverage" lies whole inside the list, where a tap ticks it. With the keyboard's focus on the layers' button
    at 1000 px wide (a mouse; the box not opened), narrowing to 600 px builds the control again at the top right and
    the focus goes with it: document.activeElement is the new layers' button of the live map, not the body."""
    from playwright.sync_api import sync_playwright
    _search_page(tmp_path, "", folder_name="basictest")
    r = {}
    with _server(tmp_path) as port, sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _page(browser, port, PHONE)
            _tap_on(page, ".leaflet-control-layers-toggle")
            page.wait_for_selector(".leaflet-control-layers-expanded", timeout=WAIT)
            r["opened"] = page.evaluate(LIST_JS)
            page.set_viewport_size({"width": 667, "height": 375})
            # Leaflet's "resize" comes with the map's new size (invalidateSize from the page's ResizeObserver)
            page.wait_for_function("() => window.FINDALINE_PLACE.map.getSize().y < 200", timeout=WAIT)
            page.evaluate(TWO_FRAMES)
            r["turned"] = page.evaluate(LIST_JS)
            page.evaluate("() => { const l = window.FINDALINE_PLACE.map.getContainer().querySelector('.leaflet-control-layers-list'); l.scrollTop = l.scrollHeight; }")
            r["scrolled"] = page.evaluate(LIST_JS)
            opened, turned, scrolled = r["opened"], r["turned"], r["scrolled"]
            assert opened["expanded"] and opened["height"] <= opened["room"] + 0.5, opened  # no scrolling before the turn
            assert turned["expanded"] and turned["box"][3] <= turned["map"][3] + 0.5, ("the box past the map's edge", turned)
            assert turned["height"] > turned["room"], ("the list does not scroll", turned)
            name, row = scrolled["rows"][-1]
            top = scrolled["list"][1]
            assert name == COVERAGE and row[1] >= top - 0.5 and row[3] <= top + scrolled["room"] + 0.5, ("the last row out of reach", scrolled)
            words = page.evaluate(ROW_JS)["words"]
            _tap(page, (words[0] + words[2]) / 2, (words[1] + words[3]) / 2)
            page.wait_for_function("() => window.FINDALINE_PLACE.coverage.on", timeout=WAIT)
            r["phone errors"] = page.errors
            page.context.close()
            page = _page(browser, port, {"viewport": {"width": 1000, "height": 800}})
            page.focus(".c-placemap .leaflet-control-layers-toggle")
            r["focused"] = page.evaluate("() => [document.activeElement.className, document.querySelector('.c-placemap .leaflet-control-layers').className]")
            page.set_viewport_size({"width": 600, "height": 800})
            page.wait_for_selector(".c-placemap.c-map-phone", timeout=WAIT)
            page.evaluate(TWO_FRAMES)
            r["narrow"] = page.evaluate("""() => { const a = document.activeElement, m = window.FINDALINE_PLACE.map.getContainer();
              return {active: a ? a.tagName + '.' + a.className : null, button: a === m.querySelector('.leaflet-top.leaflet-right .leaflet-control-layers-toggle'),
                      connected: !!a && a.isConnected}; }""")
            r["desktop errors"] = page.errors
        finally:
            browser.close()
    print("the box and the focus across resizes: " + json.dumps(r))
    assert r["focused"][0] == "leaflet-control-layers-toggle" and "expanded" not in r["focused"][1], r["focused"]
    assert r["narrow"]["button"] and r["narrow"]["connected"], ("the focus left the layers' button", r["narrow"])
    assert r["phone errors"] == r["desktop errors"] == [], r


def test_closing_press_on_a_tablet_and_with_a_mouse(tmp_path):
    """The closing press (PlaceMap.ts, the "pointerdown" guard): on a touch tablet (1024 x 768, the desktop's
    arrangement: the controls at the bottom right) a tap on the map that closes the opened layers' box sets no centre
    and the next tap sets it at the tapped point (the phone's case: test_place_map_on_a_phone). With a mouse (1400 x
    900, no touch) the box opened by the keyboard (the layers' button focused, Enter), a click on the map clear of the
    controls sets the centre at the clicked point and the box closes; a click with the box closed sets it too."""
    from playwright.sync_api import sync_playwright
    _search_page(tmp_path, "", folder_name="basictest")
    r = {}
    point = "() => window.FINDALINE_SEARCH.point"
    near = lambda a, b: abs(a[0] - b[0]) < 1e-4 and abs(a[1] - b[1]) < 1e-4  # noqa: E731
    with _server(tmp_path) as port, sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _page(browser, port, TABLET)
            page.evaluate(POINT_JS)
            _ready(page)
            centre = page.evaluate(point)
            r["tablet phone"] = page.evaluate(ARRANGED_JS)["phone"]
            _tap_on(page, ".leaflet-control-layers-toggle")
            page.wait_for_selector(".leaflet-control-layers-expanded", timeout=WAIT)
            m = page.evaluate(ARRANGED_JS)["map"]
            x, y = m[0] + 120, (m[1] + m[3]) / 2
            r["tablet at"] = page.evaluate(LATLNG_JS, [x, y])
            _tap(page, x, y)
            page.wait_for_selector(".leaflet-control-layers-expanded", state="detached", timeout=WAIT)
            r["tablet closed"] = page.evaluate(point)
            _tap(page, x, y)
            page.wait_for_function("(c) => String(window.FINDALINE_SEARCH.point) !== String(c)", arg=centre, timeout=WAIT)
            r["tablet moved"] = page.evaluate(point)
            r["tablet centre"] = centre
            r["tablet errors"] = page.errors
            page.context.close()
            page = _page(browser, port, DESKTOP)
            page.evaluate(POINT_JS)
            _ready(page)
            centre = r["mouse centre"] = page.evaluate(point)
            page.focus(".c-placemap .leaflet-control-layers-toggle")
            page.keyboard.press("Enter")
            page.wait_for_selector(".leaflet-control-layers-expanded", timeout=WAIT)
            m = page.evaluate(ARRANGED_JS)["map"]
            x, y = (m[0] + m[2]) / 2 - 100, (m[1] + m[3]) / 2
            r["mouse at"] = page.evaluate(LATLNG_JS, [x, y])
            page.mouse.click(x, y)
            page.wait_for_selector(".leaflet-control-layers-expanded", state="detached", timeout=WAIT)
            page.evaluate(TWO_FRAMES)
            r["mouse open click"] = page.evaluate(point)
            x2, y2 = x - 150, y + 80
            r["mouse at 2"] = page.evaluate(LATLNG_JS, [x2, y2])
            page.mouse.click(x2, y2)
            page.wait_for_function("(c) => String(window.FINDALINE_SEARCH.point) !== String(c)", arg=r["mouse open click"], timeout=WAIT)
            r["mouse closed click"] = page.evaluate(point)
            r["mouse errors"] = page.errors
        finally:
            browser.close()
    print("the closing press: " + json.dumps(r))
    assert r["tablet phone"] is False and r["tablet at"]["free"], r
    assert r["tablet closed"] == r["tablet centre"], ("the closing tap set a centre", r)
    assert r["tablet moved"] != r["tablet centre"] and near(r["tablet moved"], r["tablet at"]["at"]), r
    assert r["mouse at"]["free"] and r["mouse at 2"]["free"], r
    assert r["mouse open click"] != r["mouse centre"] and near(r["mouse open click"], r["mouse at"]["at"]), \
        ("a mouse's click with the box open set no centre", r)
    assert near(r["mouse closed click"], r["mouse at 2"]["at"]), r
    assert r["tablet errors"] == r["mouse errors"] == [], r


# Advanced and the place kind "Area" by a script's click each (not Playwright's click: its pointer stays over the tab,
# and Leaflet closes an opened layers' box on that pointer's late "mouseout"; a finger's taps go through _tap)
AREA_JS = """() => { document.querySelector('.s-tabs [data-tab=advanced]').click();
  [...document.querySelectorAll('.s-where .u-seg [role=radio]')].find((b) => b.textContent.trim() === 'Area').click(); }"""
TOOLS = "() => document.querySelectorAll('.c-placemap .leaflet-pm-toolbar a.leaflet-buttons-control-button').length === 5"
# The drawing tools: [title, box, the map corner holding it]
TOOLS_JS = """() => [...document.querySelectorAll('.c-placemap .leaflet-pm-toolbar a.leaflet-buttons-control-button')].filter((a) => a.getClientRects().length)
  .map((a) => { const r = a.getBoundingClientRect(), c = a.closest('.leaflet-top, .leaflet-bottom');
    return [a.parentElement.title, [r.left, r.top, r.right, r.bottom], c ? c.className.replace(/\\s+/g, ' ').trim() : null]; })"""
# The visible "Cancel" of a drawing tool on (Geoman's actions): its box
CANCEL_JS = """() => { const a = [...document.querySelectorAll('.c-placemap .leaflet-pm-actions-container .action-cancel')].find((e) => e.getClientRects().length && e.offsetParent);
  if (!a) return null; const r = a.getBoundingClientRect(); return [r.left, r.top, r.right, r.bottom]; }"""
DRAWING = "() => window.FINDALINE_PLACE.map.pm.globalDrawModeEnabled()"


def test_drawing_tools_on_a_phone(tmp_path):
    """The drawing tools (Advanced, the place kind "Area": Leaflet-Geoman's five buttons, mapbar.css) in the phone's
    arrangement, at 390 x 664, 390 x 844, 667 x 375, 844 x 390 and 932 x 430 (touch): each at least 44 x 44 px, in one
    row right of the zoom (left to right, the first right of the zoom-out, every tool at the zoom's top: measured
    2026-11-19 at all five sizes, the tools 104-332 px right of the map's left edge, the zoom 8-96; the layers' button
    6 px right of the last tool at 390 px wide, 0 px (touching) at 844 x 390 and 88 px at 932 x 430, the map 384 and
    472 px wide there), no tool over another control of the map (the zoom's two, the layers' button, the scale, the
    credits) and none outside the map; a tap on the rectangle tool starts its drawing (Geoman's globalDrawModeEnabled),
    a tap on its "Cancel" ends it, and a tap on the layers' button still opens the box (open two frames later too). On
    a desktop (1400 x 900, a mouse) the tools keep Geoman's column at the bottom right: one left edge, one under
    another, each under 44 px wide."""
    from playwright.sync_api import sync_playwright
    _search_page(tmp_path, "", folder_name="basictest")
    r = {}
    sizes = {"390x664": SMALL_PHONE, "390x844": PHONE, "667x375": SIDE_PHONE, "844x390": WIDE_SIDE_PHONE,
             "932x430": {"viewport": {"width": 932, "height": 430}, **TOUCH}}
    with _server(tmp_path) as port, sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            for size, context in sizes.items():
                page = _page(browser, port, context)
                page.evaluate(AREA_JS)
                page.wait_for_function("() => window.FINDALINE_SEARCH.tab === 'advanced'", timeout=WAIT)
                page.wait_for_function(TOOLS, timeout=WAIT)
                page.evaluate(TWO_FRAMES)
                found = r[size] = page.evaluate(CONTROLS_JS)
                tools = r[size, "tools"] = page.evaluate(TOOLS_JS)
                rect = tools[0][1]
                _tap(page, (rect[0] + rect[2]) / 2, (rect[1] + rect[3]) / 2)
                page.wait_for_function(DRAWING, timeout=WAIT)
                r[size, "drawing"] = page.evaluate(DRAWING)
                cancel = r[size, "cancel"] = page.evaluate(CANCEL_JS)
                if cancel:
                    _tap(page, (cancel[0] + cancel[2]) / 2, (cancel[1] + cancel[3]) / 2)
                    page.wait_for_function("() => !window.FINDALINE_PLACE.map.pm.globalDrawModeEnabled()", timeout=WAIT)
                    r[size, "cancelled"] = True
                _tap_on(page, ".leaflet-control-layers-toggle")
                page.wait_for_selector(".leaflet-control-layers-expanded", timeout=WAIT)
                page.evaluate(TWO_FRAMES)
                r[size, "box open"] = page.evaluate(CONTROLS_JS)["expanded"]
                r[size, "errors"] = page.errors
                assert found["phone"] and not _overlaps(found) and not _outside_map(found), (size, _overlaps(found), _outside_map(found))
                page.context.close()
            page = _page(browser, port, DESKTOP)
            page.evaluate(AREA_JS)
            page.wait_for_function(TOOLS, timeout=WAIT)
            page.evaluate(TWO_FRAMES)
            r["desktop"] = page.evaluate(TOOLS_JS)
            r["desktop errors"] = page.errors
        finally:
            browser.close()
    print("the drawing tools: " + json.dumps({" ".join(k) if isinstance(k, tuple) else k: v for k, v in r.items()}))
    for size in sizes:
        found, tools = r[size], r[size, "tools"]
        assert [t[0] for t in tools] == ["Draw Rectangle", "Draw Polygons", "Edit Layers", "Drag Layers", "Remove Layers"], (size, tools)
        assert sorted(name for name, _, _ in found["controls"] if name.startswith("tool ")) == sorted("tool " + t[0] for t in tools), (size, found)
        small = [(name, box) for name, box, _ in tools if box[2] - box[0] < 43.5 or box[3] - box[1] < 43.5]
        assert not small, (size, "tools under 44 px", small)
        zin, zout = _named(found, "zoom in"), _named(found, "zoom out")
        row = [box for _, box, _ in tools]
        assert all(abs(box[1] - zin[1]) < 0.5 for box in row), (size, "not at the zoom's top", zin, row)
        assert row[0][0] >= zout[2] - 0.5 and all(b[0] >= a[2] - 0.5 for a, b in zip(row, row[1:])), (size, "not one row right of the zoom", zout, row)
        assert {corner for _, _, corner in tools} == {"leaflet-top leaflet-left"}, (size, tools)
        assert r[size, "drawing"] is True and r[size, "cancel"] and r[size, "cancelled"], (size, r[size, "cancel"])
        assert r[size, "box open"] is True, (size, "the layers' box did not stay open")
        assert r[size, "errors"] == [], (size, r[size, "errors"])
    desktop = r["desktop"]
    assert len(desktop) == 5 and {corner for _, _, corner in desktop} == {"leaflet-bottom leaflet-right"}, desktop
    boxes = sorted((box for _, box, _ in desktop), key=lambda b: b[1])
    assert all(abs(b[0] - boxes[0][0]) < 0.5 and b[2] - b[0] < 44 for b in boxes), ("not Geoman's column", desktop)
    assert all(b[1] >= a[3] - 0.5 for a, b in zip(boxes, boxes[1:])), ("not one under another", desktop)
    assert r["desktop errors"] == [], r


def test_scrolling_list_ends_mid_row(tmp_path):
    """The layers' list that scrolls ends in the middle of a row (PlaceMap.ts Layers.expand: the cut row says there is
    more): opened at 667 x 375 (touch) its client height ends inside a row's box, at least 10 px from both of that
    row's edges (measured 2026-11-19: a list of 66 px, a row and a half of 44 px rows, its edge 22 px into
    "OpenStreetMap"); at 390 x 844 the list does not scroll."""
    from playwright.sync_api import sync_playwright
    _search_page(tmp_path, "", folder_name="basictest")
    r = {}
    with _server(tmp_path) as port, sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            for size, context in (("667x375", SIDE_PHONE), ("390x844", PHONE)):
                page = _page(browser, port, context)
                _tap_on(page, ".leaflet-control-layers-toggle")
                page.wait_for_selector(".leaflet-control-layers-expanded", timeout=WAIT)
                page.evaluate(TWO_FRAMES)
                r[size] = page.evaluate(LIST_JS)
                r[size, "errors"] = page.errors
                page.context.close()
        finally:
            browser.close()
    print("the scrolling list: " + json.dumps({" ".join(k) if isinstance(k, tuple) else k: v for k, v in r.items()}))
    side = r["667x375"]
    assert side["height"] > side["room"] and side["top"] == 0, side
    edge = side["list"][1] + side["room"]  # the list's bottom edge as it shows (scrolled to its top)
    cut = [(name, box) for name, box in side["rows"] if box[1] + 10 <= edge <= box[3] - 10]
    assert len(cut) == 1, ("the list ends between rows, or near a row's edge", edge, side["rows"])
    assert r["390x844"]["height"] <= r["390x844"]["room"] + 0.5, r["390x844"]
    assert r["667x375", "errors"] == r["390x844", "errors"] == [], r


def test_change_settings_from_a_scrolled_form(tmp_path):
    """"Change settings" opens Advanced at its top (search/SearchPanel.tsx EstimateBar: the form's column scrolled to
    0 after the switch): on a phone (390 x 664, touch), the form's column (.c-form) scrolled 400 px down, the bar
    unfolded, a tap on "Change settings" selects the Advanced tab, folds the bar and leaves the form's scrollTop at 0."""
    from playwright.sync_api import sync_playwright
    _search_page(tmp_path, "", folder_name="basictest")
    r = {}
    with _server(tmp_path) as port, sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _page(browser, port, SMALL_PHONE)
            page.evaluate(POINT_JS)
            _ready(page)
            r["scrolled"] = page.evaluate("() => { const f = document.querySelector('.c-form'); f.scrollTop = 400; return [f.scrollTop, f.scrollHeight, f.clientHeight]; }")
            _tap_on(page, ".s-sum")
            page.wait_for_function("() => document.querySelector('.s-bar.s-open')", timeout=WAIT)
            r["unfolded"] = page.evaluate("() => document.querySelector('.c-form').scrollTop")
            _tap_on(page, ".s-change")
            page.wait_for_function("() => window.FINDALINE_SEARCH.tab === 'advanced'", timeout=WAIT)
            page.wait_for_function("() => !document.querySelector('.s-bar.s-open')", timeout=WAIT)
            page.wait_for_function("() => document.querySelector('.c-form').scrollTop === 0", timeout=WAIT)
            r["after"] = page.evaluate(RECEIPT_JS)
            r["top"] = page.evaluate("() => document.querySelector('.c-form').scrollTop")
            r["errors"] = page.errors
        finally:
            browser.close()
    print("change settings from a scrolled form: " + json.dumps(r))
    assert r["scrolled"][0] == 400 and r["unfolded"] == 400, r  # the form scrolled down before the tap
    assert r["after"]["tab"] == "advanced" and not r["after"]["open"] and r["top"] == 0, r
    assert r["errors"] == [], r


def test_box_width_and_hidden_link(tmp_path):
    """The layers' box keeps one width (coverageLayer.css: the link's room kept while it is hidden): at 390 x 664
    (touch) the opened box's width is the same before ticking "Data coverage", ticked and unticked again (within
    0.5 px; measured 2026-11-19: 221.84 px). While off the link is not visible (visibility: hidden) and not reached by
    the keyboard (Tab from the row's checkbox goes elsewhere); ticked it is visible, at the row's end (_link_at_row_end;
    its right edge at the base rows' right edge) and Tab from the checkbox lands on it."""
    from playwright.sync_api import sync_playwright
    _search_page(tmp_path, "", folder_name="basictest")
    r = {}
    tab = """() => { const label = [...document.querySelectorAll('.leaflet-control-layers-overlays label')].find((l) => l.textContent.trim() === %s);
      label.querySelector('input').focus(); }""" % json.dumps(COVERAGE)
    on_link = "() => !!document.activeElement?.classList.contains('n-coverage-link')"
    with _server(tmp_path) as port, sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _page(browser, port, SMALL_PHONE)
            _tap_on(page, ".leaflet-control-layers-toggle")
            page.wait_for_selector(".leaflet-control-layers-expanded", timeout=WAIT)
            r["before"] = page.evaluate(LIST_JS)
            page.evaluate(tab)
            page.keyboard.press("Tab")
            r["tab off"] = page.evaluate(on_link)
            words = page.evaluate(ROW_JS)["words"]
            _tap(page, (words[0] + words[2]) / 2, (words[1] + words[3]) / 2)
            page.wait_for_function("() => window.FINDALINE_PLACE.coverage.on", timeout=WAIT)
            page.evaluate(TWO_FRAMES)
            r["ticked"] = page.evaluate(LIST_JS)
            r["row"] = page.evaluate(ROW_JS)
            page.evaluate(tab)
            page.keyboard.press("Tab")
            r["tab on"] = page.evaluate(on_link)
            box = page.evaluate(ROW_JS)["input"]
            _tap(page, (box[0] + box[2]) / 2, (box[1] + box[3]) / 2)
            page.wait_for_function("() => !window.FINDALINE_PLACE.coverage.on", timeout=WAIT)
            page.evaluate(TWO_FRAMES)
            r["unticked"] = page.evaluate(LIST_JS)
            r["errors"] = page.errors
        finally:
            browser.close()
    print("the box's width and the link: " + json.dumps(r))
    widths = [r[k]["box"][2] - r[k]["box"][0] for k in ("before", "ticked", "unticked")]
    assert all(r[k]["expanded"] for k in ("before", "ticked", "unticked")), r
    assert max(widths) - min(widths) <= 0.5, ("the box's width changes", widths)
    for k in ("before", "unticked"):
        assert r[k]["link"]["visibility"] == "hidden" and r[k]["link"]["hidden"], (k, r[k]["link"])
    assert r["tab off"] is False, "Tab from the checkbox reached the hidden link"
    ticked = r["ticked"]
    assert ticked["link"]["visibility"] == "visible" and not ticked["link"]["hidden"], ticked["link"]
    assert _link_at_row_end(r["row"]) and abs(ticked["link"]["box"][2] - ticked["rows"][0][1][2]) <= 0.5, (r["row"], ticked)
    assert r["tab on"] is True, "Tab from the checkbox did not reach the shown link"
    assert r["errors"] == [], r


def test_layers_button_icon(tmp_path):
    """The place map's layers' button holds the kit's "layers" icon (PlaceMap.ts Layers._initLayout: an svg.u-ic,
    drawn 18 x 18 px) and no background picture (mapbar.css: background-image none, no filter), in the light and the
    dark theme (the emulated colour scheme; the map's computed color-scheme follows it), on a phone (390 x 664, touch)
    and a desktop (1400 x 900)."""
    from playwright.sync_api import sync_playwright
    _search_page(tmp_path, "", folder_name="basictest")
    r = {}
    with _server(tmp_path) as port, sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            for scheme in ("light", "dark"):
                for device, context in (("phone", SMALL_PHONE), ("desktop", DESKTOP)):
                    page = _page(browser, port, {**context, "color_scheme": scheme})
                    r[scheme, device] = page.evaluate("""() => { const a = document.querySelector('.c-placemap .leaflet-control-layers-toggle'), s = getComputedStyle(a);
                      const svg = a.querySelector('svg.u-ic'), b = svg && svg.getBoundingClientRect();
                      return {background: s.backgroundImage, filter: s.filter, svg: !!svg, size: b ? [b.width, b.height] : null,
                              scheme: getComputedStyle(document.querySelector('.c-placemap')).colorScheme}; }""")
                    r[scheme, device, "errors"] = page.errors
                    page.context.close()
        finally:
            browser.close()
    print("the layers' button: " + json.dumps({" ".join(k): v for k, v in r.items()}))
    for scheme in ("light", "dark"):
        for device in ("phone", "desktop"):
            found = r[scheme, device]
            assert found["scheme"] == scheme, (scheme, device, found)  # the theme asked for is the one drawn
            assert found["svg"] and found["size"][0] > 0 and found["size"][1] > 0, (scheme, device, found)
            assert found["background"] == "none" and found["filter"] == "none", (scheme, device, found)
            assert r[scheme, device, "errors"] == [], (scheme, device)
