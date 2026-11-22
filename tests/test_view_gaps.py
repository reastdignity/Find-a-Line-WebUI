"""The three parity gaps of the result view the user wanted closed in step 3d (the user's answers P1 a, P3 a, P4 a of
2026-11-21; viewer/src/result/view/SpotColumns.tsx, SpotList.tsx, SpotDetails.tsx, viewstate.ts, spots.ts):

- P3: a new selection made while a phone's sheet is at full drops the sheet to half, as on today's page (ResultColumns.tsx
  Phone: useMeasureEnds' setSnap full -> half, for every new selected line): a row of the list (test_view_frame.py's
  test_selected_fit_at_full_drops_to_half), a row of "Lines from here", the line stepper, the spot stepper and a link;
  the line is then on the map above the sheet with at least one end clear of every control (B3's rule).
- P4: the sort's direction beside "Sort by": it reverses the tree "All spots" (its sectors and the spots inside each);
  another key starts largest first; "Best in view", its B numbers and the picks stay best first; kept with the sort.
- P1: Previous / Next spot in the spot's head (the user's pick A: between the star and ×), stepping through the tree's
  spots top to bottom in the list's order and direction.

Playwright's Edge over the app's server, offline, on the result view's clip runs; every wait is an event with a
deadline (the one exception is test_shell_c_view_map's _tap, said there). Run from PowerShell
(.claude/rules/browser-tests.md)."""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_shell_c import BIG  # noqa: E402
from test_shell_c_view_map import (BOXES, DESKTOP, SMALL_PHONE, WAIT, WORDS, _open, _state, _tap_on, boxes_site,  # noqa: E402,F401
                                   site, view_clip)
from test_view_frame import (BAR, CENTRE, HELP, OPEN_LINK, PICK, PIXEL, PROFILE_STUB, SELECTED_ENDS, STILL, UNDER8,  # noqa: E402
                             _measure_two, _one_clear, _opened)
from test_web import EDGE, _playwright  # noqa: E402

pytestmark = pytest.mark.skipif(not os.path.exists(EDGE) or not _playwright(),
                                reason="needs Microsoft Edge and Playwright (group ui)")

CHECKS = "() => Number(document.querySelector('.c-col-map').dataset.sheetChecks || 0)"


def _stop(page, to: str):
    """The phone's sheet moved by its handle's keys until it rests at `to` (peek, half, full)."""
    order = ["peek", "half", "full"]
    for _ in range(3):
        now = page.evaluate("() => F.snap()")
        if now == to:
            break
        page.focus(".u-sheet-handle")
        page.keyboard.press("ArrowUp" if order.index(to) > order.index(now) else "ArrowDown")
        page.wait_for_function(f"() => F.snap() !== '{now}' && F.rest()", timeout=WAIT)
    page.wait_for_function(f"() => F.snap() === '{to}' && F.rest()", timeout=WAIT)
    page.wait_for_function(STILL, timeout=WAIT)


def _dropped(page, counted: int, before_row: int) -> dict:
    """After a selection made at full: the new line selected, the sheet resting at half with its check made, the map
    still; the sheet's stop and the selected line's ends (SELECTED_ENDS)."""
    page.wait_for_function(f"() => (window.FINDALINE_VIEW.view.selected?.row ?? -1) !== {before_row}", timeout=WAIT)
    page.wait_for_function("() => F.snap() === 'half' && F.rest()", timeout=WAIT)
    page.wait_for_function(f"() => ({CHECKS})() > {counted}", timeout=WAIT)
    page.wait_for_function(STILL, timeout=WAIT)
    page.evaluate("() => T.frames()")
    page.wait_for_function(STILL, timeout=WAIT)
    return {"snap": page.evaluate("() => F.snap()"), "ends": page.evaluate(SELECTED_ENDS)}


def _selected_row(page) -> int:
    return page.evaluate("() => window.FINDALINE_VIEW.view.selected?.row ?? -1")


@pytest.mark.parametrize("device", [SMALL_PHONE, PIXEL], ids=["390", "412"])
def test_selection_at_full_drops_to_half(boxes_site, device):
    """P3, the other ways to select with the sheet at full (a row of the list: test_view_frame.py's
    test_selected_fit_at_full_drops_to_half). Today's page drops the sheet to half for each (probed 2026-11-21 on
    390 x 844 and 390 x 664: a row, the line stepper, the spot stepper, a link). In the view: a row of "Lines from
    here", the line stepper ("The next line"), the spot stepper ("Next spot", P1) and a link each bring the sheet to
    half, the new line on the map with at least one end clear of every control."""
    from playwright.sync_api import sync_playwright
    got = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _open(browser, f"{boxes_site}#run={BOXES}", device, script=HELP + UNDER8)
            page.wait_for_function("() => F.snap() === 'peek' && F.rest()", timeout=WAIT)
            _stop(page, "half")
            # the line stepper: a spot with several lines selected at half, then "The next line" at full
            spot = page.evaluate("() => { const v = window.FINDALINE_VIEW.view; return Array.from(v.order).find((s) => v.passingCount(s) > 3); }")
            _state(page, f"view.select({spot});")
            _stop(page, "full")
            row, counted = _selected_row(page), page.evaluate(CHECKS)
            _tap_on(page, ".vl-details .vl-next")
            got["line stepper"] = _dropped(page, counted, row)
            # a row of "Lines from here": opened at the selected line's first anchor, a row pressed at full
            _tap_on(page, ".vl-details .vl-from-1")
            page.wait_for_selector(".vl-fan .vl-main", timeout=WAIT)
            _stop(page, "full")
            row, counted = _selected_row(page), page.evaluate(CHECKS)
            target = page.evaluate(f"() => [...document.querySelectorAll('.vl-fan .vl-main')].map((b) => Number(b.dataset.row)).find((r) => r !== {row})")
            assert target is not None, "no row of the fan other than the selected line"
            _tap_on(page, f".vl-fan .vl-main[data-row='{target}']")
            got["fan row"] = _dropped(page, counted, row)
            # the spot stepper ("Next spot" in the sheet's head) at full
            _state(page, "view.closeFan();")
            page.wait_for_selector(".u-sheet .vl-spot-next:not([disabled])", timeout=WAIT)
            _stop(page, "full")
            row, counted = _selected_row(page), page.evaluate(CHECKS)
            _tap_on(page, ".u-sheet .vl-spot-next")
            got["spot stepper"] = _dropped(page, counted, row)
            # a link to another spot's line, opened at full
            _stop(page, "full")
            row, counted = _selected_row(page), page.evaluate(CHECKS)
            link = page.evaluate("() => { const v = window.FINDALINE_VIEW.view, s = v.order[5]; return v.model.lineLink(v.model.lineAt(v.shownOf(s))); }")
            page.evaluate(OPEN_LINK, [BOXES, link])
            got["link"] = _dropped(page, counted, row)
            assert page.errors == []
        finally:
            browser.close()
    print("selected at full:", device.get("viewport"), got)
    for how, state in got.items():
        assert state["snap"] == "half", (how, state)
        assert _one_clear(state["ends"]), (how, state)


# The tree as drawn and as the view holds it: the rows' spots of the open sectors in their order, each sector's spots
# with the sort key's value of its shown line (null: not known), the direction's button and the heads' marks, what is
# kept
TREE = r"""() => { const v = window.FINDALINE_VIEW.view, key = v.sort;
  const value = (s) => { const x = key === 'n' ? v.passingCount(s) : v.values[key][v.shownOf(s)]; return Number.isFinite(x) ? x : null; };
  const dir = document.querySelector('.vl-tree .vl-dir'), r = dir && dir.getBoundingClientRect();
  return {sort: key, desc: v.desc, level: v.level, rows: [...document.querySelectorAll('.vl-tree .vl-rows .vl-main')].map((b) => Number(b.dataset.spot)),
    sectors: v.sectors.map((s) => s.spots.map((p) => [p, value(p)])), order: Array.from(v.order), best: Array.from(v.inView.best),
    label: dir && dir.getAttribute('aria-label'), title: dir && dir.getAttribute('title'), size: r && [Math.round(r.width), Math.round(r.height)],
    edge: dir && parseFloat(getComputedStyle(dir).borderTopWidth) > 0 && getComputedStyle(dir).borderTopColor !== 'rgba(0, 0, 0, 0)',
    treeAsc: !!document.querySelector('.vl-tree .vl-by.vl-asc'), topAsc: !!document.querySelector('.vl-topblock .vl-by.vl-asc'),
    topRows: [...document.querySelectorAll('.vl-topblock .vl-rows .vl-main')].map((b) => Number(b.dataset.spot)),
    kept: (() => { try { return localStorage.getItem('findaline.view.v1'); } catch (e) { return 'blocked'; } })()}; }"""


def _ordered(sectors, desc: bool) -> bool:
    """Each sector's spots in the direction (an unknown value last, equal values the lower number first), and the
    sectors by their first spot in it."""
    def key(item):
        spot, v = item
        return (v is None, (-v if desc else v) if v is not None else 0, spot)
    if any(s != sorted(s, key=key) for s in sectors):
        return False
    firsts = [s[0] for s in sectors]
    return firsts == sorted(firsts, key=key)


@pytest.mark.parametrize("device", ["desktop", "phone"])
def test_sort_direction(site, device):
    """P4: the direction beside "Sort by" ("Largest first", today's words) pressed: the tree's rows smallest first (each
    sector's spots and the sectors' order; the rows drawn are the view's), the tree's head mark points up, the button
    says "Smallest first"; "Best in view", its rows and B numbers and its head's mark stay best first. Kept with the
    sort (findaline.view.v1, the direction written only when it is not the key's first) and read back on a reload.
    Pressed again: largest first. Another key starts largest first. On a touch phone (390 x 664, the sheet at full)
    the button is 44 x 44."""
    from playwright.sync_api import sync_playwright
    context = DESKTOP if device == "desktop" else SMALL_PHONE
    words = {k: WORDS[f"ui.view.{k}"] for k in ("dir_desc", "dir_asc")}

    def ready(page):
        page.wait_for_selector(".vl-tree .vl-dir", timeout=WAIT)
        if device == "phone":
            page.wait_for_function("() => F.snap() === 'peek' && F.rest()", timeout=WAIT)
            _stop(page, "full")

    def press(page, desc: bool):
        if device == "phone":
            _tap_on(page, ".vl-tree .vl-dir")
        else:
            page.click(".vl-tree .vl-dir")
        page.wait_for_function(f"() => window.FINDALINE_VIEW.view.desc === {str(desc).lower()}", timeout=WAIT)
        page.evaluate("() => T.frames()")

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _open(browser, site + f"#run={BIG}", context, script=HELP)
            ready(page)
            first = page.evaluate(TREE)
            press(page, False)
            asc = page.evaluate(TREE)
            page.reload()
            page.wait_for_function("() => !!window.FINDALINE_VIEW", timeout=WAIT)
            ready(page)
            reloaded = page.evaluate(TREE)
            press(page, True)
            back = page.evaluate(TREE)
            press(page, False)
            page.select_option(".vl-tree select.r-sort", "len")
            page.wait_for_function("() => window.FINDALINE_VIEW.view.sort === 'len'", timeout=WAIT)
            page.evaluate("() => T.frames()")
            other = page.evaluate(TREE)
            assert page.errors == []
        finally:
            browser.close()
    print("direction:", device, {k: {x: v[x] for x in ("sort", "desc", "label", "size", "treeAsc", "topAsc", "kept")}
                                 for k, v in (("first", first), ("asc", asc), ("reloaded", reloaded), ("back", back), ("other", other))})
    assert first["desc"] and first["label"] == words["dir_desc"] and first["title"] == words["dir_desc"], first
    assert _ordered(first["sectors"], True) and not first["treeAsc"], first["sectors"][:2]
    # smallest first: the tree reversed, drawn as the view holds it; Best in view as it was
    assert not asc["desc"] and asc["label"] == words["dir_asc"] and asc["title"] == words["dir_asc"], asc
    assert _ordered(asc["sectors"], False) and asc["sectors"] != first["sectors"], asc["sectors"][:2]
    assert asc["rows"][:5] == [s for s, _ in asc["sectors"][0][:5]], (asc["rows"][:5], asc["sectors"][0][:5])
    flat = [s for sector in asc["sectors"] for s, _ in sector]
    assert asc["rows"] == [s for s in flat if s in asc["rows"]], (asc["rows"][:10], flat[:10])
    assert asc["treeAsc"] and not asc["topAsc"], asc
    # Best in view best first: in `order`'s order (the same order as before), its rows its first spots (which spots are
    # in view may change meanwhile: a phone's sheet, as it rests, makes the canvas take its view again)
    assert asc["order"] == first["order"], "the view's order (Best in view, the B numbers) changed with the direction"
    if device == "desktop":  # (no sheet: the same spots in view)
        assert asc["best"] and asc["best"] == first["best"] and asc["topRows"] == first["topRows"], (asc["best"], first["best"])
    for state in (first, asc):
        assert state["best"] == sorted(state["best"], key=state["order"].index), state["best"]
        if state["level"] != "area":  # (at the Area level the top block holds the picks)
            assert state["topRows"] == state["best"][:len(state["topRows"])], (state["topRows"], state["best"])
    assert json.loads(asc["kept"]) == {"sort": "hmean", "hint": True, "desc": False}, asc["kept"]
    # kept: a reload reads it back
    assert not reloaded["desc"] and reloaded["sectors"] == asc["sectors"] and reloaded["label"] == words["dir_asc"], reloaded
    # pressed again: largest first, as at the start; another key starts largest first
    assert back["desc"] and back["sectors"] == first["sectors"] and back["label"] == words["dir_desc"], back
    assert json.loads(back["kept"]) == {"sort": "hmean", "hint": True}, back["kept"]
    assert other["sort"] == "len" and other["desc"] and other["label"] == words["dir_desc"] and _ordered(other["sectors"], True), other
    assert json.loads(other["kept"]) == {"sort": "len", "hint": True}, other["kept"]
    if device == "phone":
        assert first["size"] == [44, 44] and asc["size"] == [44, 44], (first["size"], asc["size"])
    assert first["edge"] and asc["edge"], (first, asc)  # an edge: a button, not the heads' mark (the design review's F5)


def test_old_kept_value_reads_largest_first(site):
    """A value of findaline.view.v1 kept before the direction (no `desc`) reads as its key's first direction: largest
    first ("Largest first" on the button, the tree as before), and reading it writes nothing."""
    from playwright.sync_api import sync_playwright
    old = "try { localStorage.setItem('findaline.view.v1', JSON.stringify({sort: 'clr', hint: false})); } catch (e) {}"
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _open(browser, site + f"#run={BIG}", DESKTOP, script=HELP + old)
            page.wait_for_selector(".vl-tree .vl-dir", timeout=WAIT)
            got = page.evaluate(TREE)
            assert page.errors == []
        finally:
            browser.close()
    assert got["sort"] == "clr" and got["desc"] and got["label"] == WORDS["ui.view.dir_desc"], got
    assert _ordered(got["sectors"], True), got["sectors"][:2]
    assert json.loads(got["kept"]) == {"sort": "clr", "hint": False}, got["kept"]


# The spot stepper's state: the selected spot and line, the spot's shown line, its place in the tree (its sectors top
# to bottom, every spot of each), the two buttons (in the details' head, else a phone's sheet head) and where the
# focus is; the tree's row of the spot: pressed, drawn whole in the list's scroller, its sector open
STEPPER = r"""() => { const v = window.FINDALINE_VIEW.view, tree = v.sectors.flatMap((s) => s.spots), sel = v.selected;
  const btn = (c) => { const b = document.querySelector('.vl-dhead .' + c + ', .vl-sheet-row .' + c), r = b && b.getBoundingClientRect();
    return b && {off: b.disabled, label: b.getAttribute('aria-label'), size: [Math.round(r.width), Math.round(r.height)], bottom: Math.round(r.bottom),
                 left: Math.round(r.left), right: Math.round(r.right)}; };
  const row = sel && document.querySelector('#vl-row-' + sel.spot + ' > .vl-main'), box = row && row.closest('.vl-body, .u-sheet-body');
  const r = row && row.getBoundingClientRect(), b = box && box.getBoundingClientRect();
  const sec = sel && document.querySelector('#vl-sec-' + (v.sectorOf(sel.spot) + 1));
  return {spot: sel ? sel.spot : null, row: sel ? sel.row : null, shown: sel ? v.shownOf(sel.spot) : null, k: sel ? tree.indexOf(sel.spot) : -1,
    tree, firsts: v.sectors.map((s) => s.spots.length), prev: btn('vl-spot-prev'), next: btn('vl-spot-next'),
    focus: document.activeElement ? document.activeElement.className : '', pressed: row ? row.getAttribute('aria-pressed') : null,
    inView: !!(r && b && r.top >= b.top - 1 && r.bottom <= b.bottom + 1), open: sec ? sec.getAttribute('aria-expanded') : null}; }"""


def _stepped(page, spot: int) -> dict:
    """The spot `spot` selected (a step), the page drawn: STEPPER."""
    page.wait_for_function(f"() => window.FINDALINE_VIEW.view.selected?.spot === {spot}", timeout=WAIT)
    page.wait_for_function(STILL, timeout=WAIT)
    page.evaluate("() => T.frames()")
    return page.evaluate(STEPPER)


def test_spot_stepper_desktop(site):
    """P1 on the desktop (1400 x 900): "Previous spot" / "Next spot" in the spot's head, between the star and × (the
    user's pick A), step through the tree's spots top to bottom (its sectors in order, every spot of each): each step
    selects the spot as a press on its row of the tree does (its shown line, that row pressed and kept in view, its
    sector opened where it was closed). "Previous spot" is off at the first spot and "Next spot" at the last; a button
    that goes off hands the focus to its twin (Enter on the keyboard); in the middle of the list "Next spot" pressed by
    the keyboard keeps the focus (today's flows test, C1's D2). Smallest first, the steps follow the tree's new order."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _open(browser, site + f"#run={BIG}", DESKTOP, script=HELP)
            tree = page.evaluate("() => window.FINDALINE_VIEW.view.sectors.flatMap((s) => s.spots)")
            _state(page, f"view.select({tree[0]});")
            start = _stepped(page, tree[0])
            order = page.evaluate("() => [...document.querySelectorAll('.vl-dhead > *')].map((e) => e.className.split(' ').find((c) => c.startsWith('vl-')) || e.tagName)")
            steps = []
            for k in (1, 2, 3):
                page.click(".vl-dhead .vl-spot-next")
                steps.append(_stepped(page, tree[k]))
            # by the keyboard in the middle of the list: "Next spot" keeps the focus (today's flows: "focus: Next spot")
            page.focus(".vl-dhead .vl-spot-next")
            page.keyboard.press("Enter")
            kept = _stepped(page, tree[4])
            # back by the keyboard: at the first spot "Previous spot" goes off, the focus to "Next spot"
            page.focus(".vl-dhead .vl-spot-prev")
            for k in (3, 2, 1, 0):
                page.keyboard.press("Enter")
                back = _stepped(page, tree[k])
            # from the last spot of the first sector into the second (closed until then)
            last = page.evaluate("() => window.FINDALINE_VIEW.view.sectors[0].spots.length") - 1
            closed = page.evaluate(f"() => document.querySelector('#vl-sec-' + (window.FINDALINE_VIEW.view.sectorOf({tree[last + 1]}) + 1)).getAttribute('aria-expanded')")
            _state(page, f"view.select({tree[last]});")
            _stepped(page, tree[last])
            page.click(".vl-dhead .vl-spot-next")
            into = _stepped(page, tree[last + 1])
            # the last spot: "Next spot" goes off, the focus to "Previous spot"
            _state(page, f"view.select({tree[-2]});")
            _stepped(page, tree[-2])
            page.focus(".vl-dhead .vl-spot-next")
            page.keyboard.press("Enter")
            end = _stepped(page, tree[-1])
            # smallest first: the steps follow the tree's order
            page.click(".vl-tree .vl-dir")
            page.wait_for_function("() => !window.FINDALINE_VIEW.view.desc", timeout=WAIT)
            asc = page.evaluate("() => window.FINDALINE_VIEW.view.sectors.flatMap((s) => s.spots)")
            _state(page, f"view.select({asc[0]});")
            _stepped(page, asc[0])
            page.click(".vl-dhead .vl-spot-next")
            reversed_step = _stepped(page, asc[1])
            assert page.errors == []
        finally:
            browser.close()
    print("spot stepper, desktop: head", order, "start", {k: start[k] for k in ("spot", "k", "prev", "next")},
          "steps", [(s["spot"], s["k"], s["pressed"], s["inView"]) for s in steps], "back", {k: back[k] for k in ("k", "prev", "focus")},
          "into", {k: into[k] for k in ("spot", "open", "pressed", "inView")}, "closed before", closed, "end", {k: end[k] for k in ("k", "next", "focus")})
    # the title first, then the star (where the page keeps favourites), the pair, ×
    assert order[0] == "vl-spot-title" and order[-2:] == ["vl-spots", "vl-dclose"] and len(order) <= 4, order
    assert start["prev"]["off"] and not start["next"]["off"], start
    assert start["prev"]["label"] == WORDS["ui.view.spot_before"] and start["next"]["label"] == WORDS["ui.view.spot_next"], start
    for k, s in zip((1, 2, 3), steps):
        assert s["k"] == k and s["row"] == s["shown"] and s["pressed"] == "true" and s["inView"], s
        assert not s["prev"]["off"] and not s["next"]["off"], s
    assert kept["k"] == 4 and "vl-spot-next" in kept["focus"], kept
    assert back["k"] == 0 and back["prev"]["off"] and "vl-spot-next" in back["focus"], back
    assert closed == "false" and into["open"] == "true" and into["pressed"] == "true" and into["inView"], (closed, into)
    assert end["k"] == len(tree) - 1 and end["next"]["off"] and "vl-spot-prev" in end["focus"], end
    assert asc != tree and reversed_step["k"] == 1 and reversed_step["spot"] == asc[1], reversed_step


@pytest.mark.parametrize("device", [SMALL_PHONE, PIXEL], ids=["390", "412"])
def test_spot_stepper_phone(site, device):
    """P1 on a phone: the pair in the sheet's head, beside the spot's title, 44 x 44, inside the sheet's visible part at
    its lowest stop, where a press steps to the next spot of the tree (its shown line selected); "Next spot" pressed by
    the keyboard in the middle of the list keeps the focus (C1's D2)."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _open(browser, site + f"#run={BIG}", device, script=HELP)
            page.wait_for_function("() => F.snap() === 'peek' && F.rest()", timeout=WAIT)
            tree = page.evaluate("() => window.FINDALINE_VIEW.view.sectors.flatMap((s) => s.spots)")
            _state(page, f"view.select({tree[0]});")
            start = _stepped(page, tree[0])
            snap = page.evaluate("() => F.snap()")
            page.wait_for_function("() => F.rest()", timeout=WAIT)
            sheet = page.evaluate("() => [Math.round(document.querySelector('.u-sheet').getBoundingClientRect().top), innerHeight]")
            start = page.evaluate(STEPPER)
            _tap_on(page, ".vl-sheet-row .vl-spot-next")
            stepped = _stepped(page, tree[1])
            # by the keyboard in the middle of the list: "Next spot" keeps the focus (today's flows, C1's D2)
            page.focus(".vl-sheet-row .vl-spot-next")
            page.keyboard.press("Enter")
            kept = _stepped(page, tree[2])
            assert page.errors == []
        finally:
            browser.close()
    print("spot stepper, phone:", device.get("viewport"), "sheet", snap, sheet, "start", {k: start[k] for k in ("prev", "next")},
          "stepped", {k: stepped[k] for k in ("spot", "k", "row", "shown", "prev")})
    assert start["prev"]["size"] == [44, 44] and start["next"]["size"] == [44, 44], start
    assert start["next"]["left"] - start["prev"]["right"] >= 8, start  # a gap between the two targets on touch (R7's 8 px)
    assert start["prev"]["off"] and not start["next"]["off"], start
    assert start["next"]["bottom"] <= sheet[1], (start, sheet)
    assert kept["k"] == 2 and "vl-spot-next" in kept["focus"], kept
    assert stepped["k"] == 1 and stepped["row"] == stepped["shown"] and not stepped["prev"]["off"], stepped


# --- fix round 1 (the code review of C4: F1-F3, the tests that did not test, the star's picker) ---

def _low_at_full(page):
    """The run with both coast chips at full, the map four levels out (a row's fit then moves it)."""
    page.wait_for_function("() => F.snap() === 'peek' && F.rest()", timeout=WAIT)
    _stop(page, "full")
    _state(page, "leaflet.setZoom(leaflet.getZoom() - 4, {animate: false});")
    page.wait_for_function(STILL, timeout=WAIT)


# A control's box (the frame's, 8 px larger) in the room the sheet at half leaves: its middle, map px
CONTROL_MID = r"""() => { const m = window.FINDALINE_MAP, size = m.getSize(), half = Math.max(132, Math.round(document.querySelector('.c-col-map').getBoundingClientRect().height * 0.5));
  const sw = document.querySelector('.v-map .v-switch').getBoundingClientRect(), at = m.getContainer().getBoundingClientRect(), top = sw.bottom - at.top + 4;
  const boxes = U8.boxes().map((b) => ({x: (b[0] + b[2]) / 2, y: (b[1] + b[3]) / 2})).filter((c) => c.y > top + 10 && c.y < size.y - half - 70 && c.x > 10 && c.x < size.x - 10);
  return boxes.length ? boxes[0] : null; }"""
# A tree row pressed at full and, while the sheet glides to half, the person's move: a pan that brings the selected
# line's first end under that control (and, with `zoom`, a pinch: half a level in around it); the map then and the
# sheet's state at that moment
MOVE_DURING_DROP = r"""async ([spot, control, zoom]) => {
  const frame = () => new Promise((r) => requestAnimationFrame(r)), s = document.querySelector('.u-sheet'), full = s.getBoundingClientRect().height;
  document.querySelector(`.vl-tree .vl-main[data-spot='${spot}']`).click();
  for (let i = 0; i < 60 && s.getBoundingClientRect().height > full - 60; i++) await frame();
  const m = window.FINDALINE_MAP, l = window.FINDALINE_VIEW.view.selected.line, q = m.latLngToContainerPoint([l.lat1, l.lon1]);
  const resting = F.rest();
  m.panBy([Math.round(q.x - control.x), Math.round(q.y - control.y)], {animate: false});
  if (zoom) m.setZoomAround(m.containerPointToLatLng([control.x, control.y]), m.getZoom() + 0.5, {animate: false});
  const c = m.getCenter(); return {at: [c.lat, c.lng, m.getZoom()], resting, under: U8.under(U8.lineEnds(l))}; }"""


@pytest.mark.parametrize("zoom", [False, True], ids=["pan", "pinch"])
@pytest.mark.parametrize("device", [SMALL_PHONE, PIXEL], ids=["390", "412"])
def test_move_during_the_drop_is_kept(boxes_site, device, zoom):
    """P3 with the rule "a move the person made is never undone" (and the user's: a pinch's zoom is kept): a tree row
    pressed at full, and while the sheet glides to half the person pans the map so that an end of the line lies under
    a control (and, separately, pinches half a level in). At the rest the map is where the person left it: the same
    centre and zoom (the code review's F1: the drop's check moved it, 0307980d)."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _open(browser, f"{boxes_site}#run={BOXES}", device, script=HELP + UNDER8)
            _low_at_full(page)
            spot = page.evaluate("() => Number(document.querySelector('.vl-tree .vl-rows .vl-main').dataset.spot)")
            control = page.evaluate(CONTROL_MID)
            assert control is not None, "no control in the room at half"
            counted = page.evaluate(CHECKS)
            moved = page.evaluate(MOVE_DURING_DROP, [spot, control, zoom])
            page.wait_for_function("() => F.snap() === 'half' && F.rest()", timeout=WAIT)
            page.wait_for_function(f"() => ({CHECKS})() > {counted}", timeout=WAIT)
            page.wait_for_function(STILL, timeout=WAIT)
            page.evaluate("() => T.frames()")
            page.wait_for_function(STILL, timeout=WAIT)
            after = page.evaluate(CENTRE)
            assert page.errors == []
        finally:
            browser.close()
    print("moved during the drop:", device.get("viewport"), "pinch" if zoom else "pan", moved, "->", after)
    assert not moved["resting"] and moved["under"] >= 1, moved  # (the state tests something: a move before the rest)
    assert after[2] == moved["at"][2] and abs(after[0] - moved["at"][0]) < 1e-9 and abs(after[1] - moved["at"][1]) < 1e-9, (moved, after)


@pytest.mark.parametrize("device", [SMALL_PHONE, PIXEL], ids=["390", "412"])
def test_press_during_the_rise_gets_its_check(boxes_site, device):
    """P3, the code review's F2: the sheet at half (checked there), raised to full, and a tree row pressed while it
    still rises: the drop to half gets its rest's check all the same; after it, a line opened by its link at half whose
    plain fit puts an end under a chip is brought clear (selectedFit's check runs at half again: no drop left over)."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _open(browser, f"{boxes_site}#run={BOXES}", device, script=HELP + UNDER8)
            page.wait_for_function("() => F.snap() === 'peek' && F.rest()", timeout=WAIT)
            _stop(page, "half")
            page.wait_for_function(f"() => ({CHECKS})() > 0", timeout=WAIT)
            _state(page, "leaflet.setZoom(leaflet.getZoom() - 4, {animate: false});")
            page.wait_for_function(STILL, timeout=WAIT)
            spot = page.evaluate("() => Number(document.querySelector('.vl-tree .vl-rows .vl-main').dataset.spot)")
            counted = page.evaluate(CHECKS)
            page.focus(".u-sheet-handle")
            page.keyboard.press("ArrowUp")
            rising = page.evaluate(r"""async ([spot]) => { const frame = () => new Promise((r) => requestAnimationFrame(r)), s = document.querySelector('.u-sheet');
              for (let i = 0; i < 60 && !s.classList.contains('u-full'); i++) await frame();
              const h = Math.round(s.getBoundingClientRect().height), target = parseFloat(s.style.height);
              document.querySelector(`.vl-tree .vl-main[data-spot='${spot}']`).click();
              return {h, target}; }""", [spot])
            page.wait_for_function("() => F.snap() === 'half' && F.rest()", timeout=WAIT)
            page.wait_for_function(f"() => ({CHECKS})() > {counted}", timeout=WAIT)
            page.wait_for_function(STILL, timeout=WAIT)
            page.evaluate("() => T.frames()")
            found = page.evaluate(PICK, [page.evaluate(BAR)])
            assert found is not None, "no line of the list whose fit with the bar's padding has an end under a control"
            _, row, plain, link = found
            page.evaluate(OPEN_LINK, [BOXES, link])
            ends = _opened(page, row)
            assert page.errors == []
        finally:
            browser.close()
    print("pressed during the rise:", device.get("viewport"), rising, "then a link at half:", ends)
    assert rising["h"] < rising["target"] - 1, rising  # (the press came before the rise's rest)
    assert all(n == 0 for _, _, n in ends), ends


@pytest.mark.parametrize("device", [SMALL_PHONE, PIXEL], ids=["390", "412"])
def test_two_steps_during_the_drop(boxes_site, device):
    """P3 with P1, the code review's F3: "Next spot" pressed at full and again two frames later (the sheet gliding to
    half). At the rest the check is for the line selected last: one end of it clear, and no end under a control where
    the same two steps with the second made at half at rest have none."""
    from playwright.sync_api import sync_playwright
    out = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            for case in ("quick", "at_rest"):
                page = _open(browser, f"{boxes_site}#run={BOXES}", device, script=HELP + UNDER8)
                page.wait_for_function("() => F.snap() === 'peek' && F.rest()", timeout=WAIT)
                tree = page.evaluate("() => window.FINDALINE_VIEW.view.sectors.flatMap((s) => s.spots)")
                _state(page, f"view.select({tree[0]});")
                _low_at_full(page)
                counted = page.evaluate(CHECKS)
                if case == "quick":
                    page.evaluate(r"""async () => { const frame = () => new Promise((r) => requestAnimationFrame(r));
                      const b = () => document.querySelector('.vl-sheet-row .vl-spot-next'); b().click(); await frame(); await frame(); b().click(); }""")
                    page.wait_for_function("() => F.snap() === 'half' && F.rest()", timeout=WAIT)
                    page.wait_for_function(f"() => ({CHECKS})() > {counted}", timeout=WAIT)
                else:
                    page.evaluate("() => document.querySelector('.vl-sheet-row .vl-spot-next').click()")
                    page.wait_for_function("() => F.snap() === 'half' && F.rest()", timeout=WAIT)
                    page.wait_for_function(f"() => ({CHECKS})() > {counted}", timeout=WAIT)
                    page.wait_for_function(STILL, timeout=WAIT)
                    page.evaluate("() => T.frames()")
                    page.evaluate("() => document.querySelector('.vl-sheet-row .vl-spot-next').click()")
                page.wait_for_function(f"() => window.FINDALINE_VIEW.view.selected?.spot === {tree[2]}", timeout=WAIT)
                page.wait_for_function(STILL, timeout=WAIT)
                page.evaluate("() => T.frames()")
                page.wait_for_function(STILL, timeout=WAIT)
                out[case] = page.evaluate(SELECTED_ENDS)
                assert page.errors == []
                page.context.close()
        finally:
            browser.close()
    print("two steps:", device.get("viewport"), out)
    assert _one_clear(out["quick"]), out
    if not any(e["under"] for e in out["at_rest"]):
        assert not any(e["under"] for e in out["quick"]), out


def test_reverse_follows_the_selected_row(site):
    """P4 with the list's follow (its order key carries the direction): a spot in the first page of a sector of more
    than 20 spots selected largest first, then the direction reversed: its row, now past the sector's first page, is
    drawn (the sector paged to it, open) and pressed. (The list scrolls to the spot's row in "Best in view" where it
    has one there: the planner's rule of 2026-11-18; not asserted here.)"""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _open(browser, site + f"#run={BIG}", DESKTOP, script=HELP)
            spot = page.evaluate("() => { const s = window.FINDALINE_VIEW.view.sectors.find((x) => x.spots.length > 24); return s ? s.spots[2] : null; }")
            assert spot is not None, "no sector of more than 24 spots"
            _state(page, f"view.select({spot});")
            page.wait_for_selector(f"#vl-row-{spot} > .vl-main", timeout=WAIT)
            page.click(".vl-tree .vl-dir")
            page.wait_for_function("() => !window.FINDALINE_VIEW.view.desc", timeout=WAIT)
            page.evaluate("() => T.frames()")
            got = page.evaluate(STEPPER)
            rank = page.evaluate(f"() => {{ const v = window.FINDALINE_VIEW.view; return v.sectors.find((s) => s.spots.includes({spot})).spots.indexOf({spot}); }}")
            assert page.errors == []
        finally:
            browser.close()
    print("reversed under a selection: spot", spot, "rank", rank, {k: got[k] for k in ("spot", "pressed", "inView", "open")})
    assert rank >= 20, rank  # (the state tests something: past the first page)
    assert got["spot"] == spot and got["pressed"] == "true" and got["open"] == "true", got


def test_unknown_values_last(site):
    """P4: a spot whose shown line has no known value of the sort's key stands last in the tree in both directions
    (the clip has none: three spots' shown lines given NaN mean heights in the page, the tree ordered again by a
    reverse)."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _open(browser, site + f"#run={BIG}", DESKTOP, script=HELP)
            got = page.evaluate(r"""() => { const v = window.FINDALINE_VIEW.view, tree = () => v.sectors.flatMap((s) => s.spots);
              const sector = v.sectors[0].spots, unknown = [sector[0], sector[3], sector[5]];
              unknown.forEach((s) => { v.values.hmean[v.shownOf(s)] = NaN; });
              v.setDesc(false); const asc = v.sectors.find((s) => s.spots.includes(unknown[0])).spots;
              v.setDesc(true); const desc = v.sectors.find((s) => s.spots.includes(unknown[0])).spots;
              return {unknown, asc: asc.slice(-3), desc: desc.slice(-3), ascAll: asc.length, sorted: v.sort}; }""")
            assert page.errors == []
        finally:
            browser.close()
    print("unknown values:", got)
    assert got["sorted"] == "hmean"
    assert got["asc"] == sorted(got["unknown"]) and got["desc"] == sorted(got["unknown"]), got  # last, by number


@pytest.mark.parametrize("device", [SMALL_PHONE, PIXEL], ids=["390", "412"])
def test_star_picker_on_a_phone_stays_in_view(site, device):
    """The star's folder picker opened by a finger's tap (no scroll into view) at the sheet's low stop: the sheet rises
    to full, the phone's frame does not scroll (it scrolled 328 px on 390 x 664 and the picker lay above the screen:
    the code review of C4, item 5, the same before C4), the picker inside the window."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _open(browser, site + f"#run={BIG}", device, script=HELP)
            page.wait_for_function("() => F.snap() === 'peek' && F.rest()", timeout=WAIT)
            _state(page, "view.select(view.order[0]);")
            page.wait_for_selector(".vl-sheet-row .r-fav", timeout=WAIT)
            page.wait_for_function("() => F.rest()", timeout=WAIT)
            b = page.evaluate("() => { const r = document.querySelector('.vl-sheet-row .r-fav').getBoundingClientRect(); return [(r.left + r.right) / 2, (r.top + r.bottom) / 2]; }")
            page.touchscreen.tap(b[0], b[1])
            page.wait_for_selector(".r-picker", timeout=WAIT)
            page.wait_for_function("() => F.snap() === 'full' && F.rest()", timeout=WAIT)
            page.wait_for_function("() => !!document.activeElement.closest('.r-pop')", timeout=WAIT)
            page.evaluate("() => T.frames()")
            got = page.evaluate("""() => { const p = document.querySelector('.r-pop').getBoundingClientRect();
              return {frame: document.querySelector('.c-result-phone').scrollTop, pop: [Math.round(p.top), Math.round(p.bottom)], height: innerHeight}; }""")
            assert page.errors == []
        finally:
            browser.close()
    print("the star's picker:", device.get("viewport"), got)
    assert got["frame"] == 0 and got["pop"][0] >= 0 and got["pop"][1] <= got["height"], got


# What a press at the picker's middle and at its "New folder" button reaches: inside the picker or not (and what)
ON_TOP = """() => { const p = document.querySelector('.r-pop'), b = document.querySelector('.r-picker > .u-btn.u-ghost');
  const at = (e) => { const r = e.getBoundingClientRect(), hit = document.elementFromPoint((r.left + r.right) / 2, (r.top + r.bottom) / 2);
    return {inside: !!(hit && p.contains(hit)), hit: hit && hit.className.toString().slice(0, 40), box: [Math.round(r.top), Math.round(r.bottom)]}; };
  const dock = document.querySelector('.u-sheet-body > .r-dock');
  return {middle: at(p), newFolder: b && at(b), dock: !!dock, dockBar: dock && dock.querySelector('.r-dock-bar b')?.textContent}; }"""


@pytest.mark.parametrize("device", [SMALL_PHONE, PIXEL], ids=["390", "412"])
def test_star_picker_over_a_measured_profile(site, device):
    """The star's folder picker opened on a phone while a measured line's profile stands first in the sheet's body (a
    spot selected, then Measure's two points): the picker is on top, a press at its middle and at its "New folder"
    reaches it (it lay under the dock's bar: the measured dock's z-index 6 drew it over the sheet's head, the picker's
    stacking context; L's iPhone walk, 2026-11-22)."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _open(browser, site + f"#run={BIG}", device, script=HELP + PROFILE_STUB)
            page.wait_for_function("() => F.snap() === 'peek' && F.rest()", timeout=WAIT)
            _state(page, "view.setLevel('spots'); view.select(view.order[0]);")
            page.wait_for_selector(".vl-sheet-row .r-fav", timeout=WAIT)
            _measure_two(page, phone=True)
            page.wait_for_function("() => !!window.FINDALINE_VIEW.measured && F.snap() === 'half' && F.rest()", timeout=WAIT)
            page.wait_for_function("() => !!window.FINDALINE_VIEW.view.selected && !!document.querySelector('.u-sheet-body > .r-dock')", timeout=WAIT)
            page.evaluate("() => T.frames()")
            b = page.evaluate("() => { const r = document.querySelector('.vl-sheet-row .r-fav').getBoundingClientRect(); return [(r.left + r.right) / 2, (r.top + r.bottom) / 2]; }")
            page.touchscreen.tap(b[0], b[1])
            page.wait_for_selector(".r-picker", timeout=WAIT)
            page.wait_for_function("() => F.snap() === 'full' && F.rest()", timeout=WAIT)
            page.wait_for_function("() => !!document.activeElement.closest('.r-pop')", timeout=WAIT)
            page.evaluate("() => T.frames()")
            got = page.evaluate(ON_TOP)
            assert page.errors == []
        finally:
            browser.close()
    print("the star's picker over a measured profile:", device.get("viewport"), got)
    assert got["dock"], got  # (the state tests something: the measured profile's dock in the sheet's body)
    assert got["middle"]["inside"] and got["newFolder"] and got["newFolder"]["inside"], got


# --- the final design review's fixes (2026-11-22: F1-F4, F8) ---

# The list's top block as the view holds it after the canvas took the map's view again (its refresh), and as drawn
IN_VIEW = """() => { const {view, map} = window.FINDALINE_VIEW; map.refresh();
  return {m: view.inView.m, best: Array.from(view.inView.best), level: view.level, snap: F.snap()}; }"""


def _tap_handle(page, to: str):
    """A finger's tap on the sheet's handle (a tap steps it up a stop: low, half, full), awaited at rest at `to`."""
    _tap_on(page, ".u-sheet-handle")
    page.wait_for_function(f"() => F.snap() === '{to}' && F.rest()", timeout=WAIT)
    page.wait_for_function(STILL, timeout=WAIT)


@pytest.mark.parametrize("device", [SMALL_PHONE, PIXEL], ids=["390", "412"])
def test_list_at_full_keeps_the_view(site, device):
    """F1 (the planner's (b)): at the sheet's full stop the list's "in view" is the one of the last stop below full
    over the same map view (the sheet's cover there), not empty ("Best in view: 0 of 0" before): raised by real taps on
    the handle from the low stop to half and to full, Best in view at full equals the list at half; from the low stop
    straight to full (a drag), the list at the low stop. Half and low are as before."""
    from playwright.sync_api import sync_playwright
    got = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _open(browser, site + f"#run={BIG}", device, script=HELP)
            page.wait_for_function("() => F.snap() === 'peek' && F.rest()", timeout=WAIT)
            page.wait_for_function(STILL, timeout=WAIT)
            got["low"] = page.evaluate(IN_VIEW)
            _tap_handle(page, "half")
            got["half"] = page.evaluate(IN_VIEW)
            _tap_handle(page, "full")
            got["full"] = page.evaluate(IN_VIEW)
            got["title"] = page.evaluate("() => document.querySelector('#vl-top-title').textContent")
            _tap_handle(page, "peek")
            got["low again"] = page.evaluate(IN_VIEW)
            # straight from the low stop to full: the handle dragged up past half
            h = page.evaluate("() => { const r = document.querySelector('.u-sheet-handle').getBoundingClientRect(); return [(r.left + r.right) / 2, (r.top + r.bottom) / 2]; }")
            page.mouse.move(h[0], h[1])
            page.mouse.down()
            page.mouse.move(h[0], 80, steps=8)
            page.mouse.up()
            page.wait_for_function("() => F.snap() === 'full' && F.rest()", timeout=WAIT)
            page.wait_for_function(STILL, timeout=WAIT)
            got["low to full"] = page.evaluate(IN_VIEW)
            assert page.errors == []
        finally:
            browser.close()
    print("in view by stop:", device.get("viewport"), {k: (v if isinstance(v, str) else (v["m"], v["best"][:4])) for k, v in got.items()})
    assert got["low"]["level"] != "area" and got["half"]["m"] > 0 and got["low"]["m"] > 0, got
    assert got["full"]["m"] == got["half"]["m"] and got["full"]["best"] == got["half"]["best"], got
    assert "0 of 0" not in got["title"], got["title"]
    assert got["low again"]["m"] == got["low"]["m"] and got["low again"]["best"] == got["low"]["best"], got
    assert got["low to full"]["m"] == got["low"]["m"] and got["low to full"]["best"] == got["low"]["best"], got


# The focused element's ring: its box-shadow and outline as drawn (none: no ring)
RING = """() => { const e = document.activeElement, s = getComputedStyle(e);
  return {label: e.getAttribute('aria-label') || e.textContent.trim().slice(0, 20), shadow: s.boxShadow, outline: s.outlineStyle, visible: e.matches(':focus-visible')}; }"""


def _tab_to(page, selector: str, k: int, limit: int = 120) -> bool:
    """Tab from where the focus is until the `k`-th element matching `selector` has it."""
    for _ in range(limit):
        if page.evaluate(f"() => document.activeElement === document.querySelectorAll({json.dumps(selector)})[{k}]"):
            return True
        page.keyboard.press("Tab")
    return False


def _ringed(r: dict) -> bool:
    return r["visible"] and (r["shadow"] not in ("none", "") or r["outline"] not in ("none", ""))


def test_run_actions_focus_rings(site):
    """F2: every run action focused by the keyboard shows the kit's ring: the phone pill's (their shadow was taken
    away by mapbar.css), and the desktop header's with a menu's button, in the view (today's page keeps its look:
    columns.css)."""
    from playwright.sync_api import sync_playwright
    phone, desk = [], []
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _open(browser, site + f"#run={BIG}", SMALL_PHONE, script=HELP)
            page.wait_for_function("() => F.snap() === 'peek' && F.rest()", timeout=WAIT)
            pill = ".c-pill .r-actions button"
            names = page.evaluate(f"() => [...document.querySelectorAll('{pill}')].map((b) => b.getAttribute('aria-label'))")
            page.focus(".c-pill .c-back")
            for k, name in enumerate(names):
                assert _tab_to(page, pill, k), name
                phone.append(page.evaluate(RING))
            page.context.close()
            page = _open(browser, site + f"#run={BIG}", DESKTOP, script=HELP)
            head = ".c-result-top .r-actions button"
            n = page.evaluate(f"() => document.querySelectorAll('{head}').length")
            page.focus(".c-result-top .c-back")
            for k in range(n):
                assert _tab_to(page, head, k), k
                desk.append(page.evaluate(RING))
            # a menu's button: Download's menu opened by the keyboard (its button the last of the header's), Tab into it
            page.keyboard.press("Enter")
            page.wait_for_selector(".c-result-top .r-pop", timeout=WAIT)
            page.wait_for_function("() => !!document.activeElement.closest('.c-result-top .r-pop')", timeout=WAIT)
            if not page.evaluate("() => document.activeElement.matches('button, a')"):
                page.keyboard.press("Tab")
            desk.append(page.evaluate(RING))
            assert page.errors == []
        finally:
            browser.close()
    print("rings: phone", phone, "desktop", desk)
    # (the test page's run shows Measure and Download in the pill, Measure, Compare and Download in the header)
    assert len(phone) >= 2 and all(_ringed(r) for r in phone), phone
    assert len(desk) >= 4 and all(_ringed(r) for r in desk), desk


def test_measure_ruler_pressed_on_a_phone(site):
    """F3: on a phone the pill's ruler takes the accent while Measure is on (aria-pressed true; the mock-up's pressed
    ruler, as the map's "i" when open), and the pill's grey on a transparent ground when off."""
    from playwright.sync_api import sync_playwright
    read = """() => { const b = document.querySelector(".c-pill [aria-label='Measure'], .c-pill .r-actions button[aria-pressed]"), s = getComputedStyle(b);
      const probe = document.createElement('span'); probe.style.background = 'var(--accent-soft)'; probe.style.color = 'var(--accent-ink)';
      b.parentElement.appendChild(probe); const want = [getComputedStyle(probe).backgroundColor, getComputedStyle(probe).color]; probe.remove();
      return {pressed: b.getAttribute('aria-pressed'), bg: s.backgroundColor, color: s.color, want}; }"""
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _open(browser, site + f"#run={BIG}", SMALL_PHONE, script=HELP)
            page.wait_for_function("() => F.snap() === 'peek' && F.rest()", timeout=WAIT)
            off = page.evaluate(read)
            page.evaluate("() => document.querySelector(\".c-pill [aria-label='Measure']\").click()")
            page.wait_for_function("() => window.FINDALINE_VIEW.map.isMeasuring", timeout=WAIT)
            page.mouse.move(5, 300)  # (no hover on the button)
            page.evaluate("() => T.frames()")
            on = page.evaluate(read)
            assert page.errors == []
        finally:
            browser.close()
    print("the ruler: off", off, "on", on)
    assert on["pressed"] == "true" and [on["bg"], on["color"]] == on["want"], on
    assert off["pressed"] in (None, "false") and off["bg"] == "rgba(0, 0, 0, 0)" and off["color"] != on["color"], off


def test_direction_press_keeps_its_place(site):
    """F4: with a spot selected (the tree's second-last), the direction pressed three times: the button stays where it
    was under the pointer (it ran to y -95 before: the list scrolled to the selected row), and the selected row is
    still drawn in the new order (the list's follow pages it)."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _open(browser, site + f"#run={BIG}", DESKTOP, script=HELP)
            tree = page.evaluate("() => window.FINDALINE_VIEW.view.sectors.flatMap((s) => s.spots)")
            spot = tree[-2]
            _state(page, f"view.select({spot});")
            page.wait_for_selector(f"#vl-row-{spot} > .vl-main", timeout=WAIT)
            page.evaluate("() => { const h = document.querySelector('.vl-tree'), box = h.closest('.vl-body'); box.scrollTop += h.getBoundingClientRect().top - box.getBoundingClientRect().top - 120; }")
            page.evaluate("() => T.frames()")
            top = lambda: page.evaluate("() => Math.round(document.querySelector('.vl-tree .vl-dir').getBoundingClientRect().top)")
            places = [top()]
            for desc in (False, True, False):
                page.click(".vl-tree .vl-dir")
                page.wait_for_function(f"() => window.FINDALINE_VIEW.view.desc === {str(desc).lower()}", timeout=WAIT)
                page.evaluate("() => T.frames()")
                places.append(top())
            drawn = page.evaluate(f"() => !!document.querySelector('#vl-row-{spot} > .vl-main[aria-pressed=\"true\"]')")
            assert page.errors == []
        finally:
            browser.close()
    print("the direction's place:", places, "row drawn", drawn)
    assert max(places) - min(places) <= 1, places
    assert drawn


@pytest.mark.parametrize("which", ["vl-cols-info", "vl-top-info"])
def test_list_info_closes_on_escape(site, which):
    """F8: the list's two "i" (the columns', "Top level only"'s) close their text on Esc while the focus is on them, as
    the access key's help does; the selection and the page stay."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _open(browser, site + f"#run={BIG}", DESKTOP, script=HELP)
            _state(page, "view.select(view.order[0]);")
            page.focus(f".{which}")
            page.keyboard.press("Enter")
            page.wait_for_function(f"() => document.querySelector('.{which}').getAttribute('aria-expanded') === 'true'", timeout=WAIT)
            page.keyboard.press("Escape")
            page.evaluate("() => T.frames()")
            got = page.evaluate(f"() => [document.querySelector('.{which}').getAttribute('aria-expanded'), !!window.FINDALINE_VIEW.view.selected]")
            assert page.errors == []
        finally:
            browser.close()
    assert got == ["false", True], got


# Is a press at an element's middle that element (or inside it)?
HIT = """(sel) => [...document.querySelectorAll(sel)].map((e) => { const r = e.getBoundingClientRect(), hit = document.elementFromPoint((r.left + r.right) / 2, (r.top + r.bottom) / 2);
  return {name: (e.getAttribute('aria-label') || e.textContent.trim()).slice(0, 24), y: [Math.round(r.top), Math.round(r.bottom)], on: !!hit && e.contains(hit),
          hit: hit && hit.className.toString().slice(0, 30)}; })"""


@pytest.mark.parametrize("device", [SMALL_PHONE, PIXEL], ids=["390", "412"])
def test_pill_menus_over_the_sheet_at_full(site, device):
    """The pill's menus (Share, Download: the run's actions that open one) are drawn over the sheet at its full stop:
    a press at each item's middle is that item (they lay under the sheet, a press reached the hint's text: L's walk on
    the merged tree); the pill's own buttons and the sheet's handle stay pressable (neither covers the other)."""
    from playwright.sync_api import sync_playwright
    got = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _open(browser, site + f"#run={BIG}", device, script=HELP)
            page.wait_for_function("() => F.snap() === 'peek' && F.rest()", timeout=WAIT)
            _stop(page, "full")
            menus = page.evaluate("() => [...document.querySelectorAll('.c-pill .r-actions button[aria-expanded]')].map((b) => b.getAttribute('aria-label'))")
            for k, name in enumerate(menus):
                page.evaluate(f"() => document.querySelectorAll('.c-pill .r-actions button[aria-expanded]')[{k}].click()")
                page.wait_for_selector(".c-pill .r-pop button, .c-pill .r-pop a", timeout=WAIT)
                page.evaluate("() => T.frames()")
                got[name] = page.evaluate(HIT, ".c-pill .r-pop button, .c-pill .r-pop a")
                page.keyboard.press("Escape")
                page.wait_for_selector(".c-pill .r-pop", state="detached", timeout=WAIT)
            got["pill"] = page.evaluate(HIT, ".c-pill .r-actions > * > button, .c-pill .r-actions > button")
            got["handle"] = page.evaluate(HIT, ".u-sheet-handle")
            assert page.errors == []
        finally:
            browser.close()
    print("the pill's menus at full:", device.get("viewport"), got)
    assert menus and all(got[m] and all(i["on"] for i in got[m]) for m in menus), got
    assert got["pill"] and all(i["on"] for i in got["pill"]) and got["handle"][0]["on"], got
