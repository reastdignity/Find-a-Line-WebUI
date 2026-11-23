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


# --- gate 2's answers (the user's iPhone test, 2026-11-22) ---

@pytest.mark.parametrize("device", [SMALL_PHONE, PIXEL], ids=["390", "412"])
def test_layers_menu_lowers_the_sheet(boxes_site, device):
    """9 a: the map's layers menu (the run with both coast boxes: its base maps and two overlays) opened by a tap while
    the sheet is at half drops the sheet to its low stop, and every row of the menu lies inside the window and on top
    (a press at its middle reaches it); closing the menu leaves the sheet low. The pill's Download menu has the kit's
    raised shadow and an edge."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _open(browser, boxes_site + f"#run={BOXES}", device, script=HELP)
            page.wait_for_function("() => F.snap() === 'peek' && F.rest()", timeout=WAIT)
            _stop(page, "half")
            _tap_on(page, ".v-map .leaflet-control-layers-toggle")
            page.wait_for_selector(".v-map .leaflet-control-layers-expanded", timeout=WAIT)
            page.wait_for_function("() => F.snap() === 'peek' && F.rest()", timeout=WAIT)
            rows = page.evaluate(HIT, ".v-map .leaflet-control-layers-expanded label")
            height = page.evaluate("() => innerHeight")
            # closed again (Leaflet's collapse, as a tap on the map does): the sheet stays low
            page.evaluate("() => document.querySelector('.v-map .leaflet-control-layers').classList.remove('leaflet-control-layers-expanded')")
            page.evaluate("() => T.frames()")
            after = page.evaluate("() => F.snap()")
            # the pill's Download menu
            page.evaluate("() => [...document.querySelectorAll('.c-pill .r-actions button[aria-expanded]')].pop().click()")
            page.wait_for_selector(".c-pill .r-pop", timeout=WAIT)
            look = page.evaluate("() => { const s = getComputedStyle(document.querySelector('.c-pill .r-pop')); return [s.boxShadow, s.borderTopWidth, s.borderTopStyle]; }")
            assert page.errors == []
        finally:
            browser.close()
    print("layers at half:", device.get("viewport"), rows, "after", after, "download menu", look)
    assert rows and all(r["on"] and r["y"][0] >= 0 and r["y"][1] <= height for r in rows), rows
    assert after == "peek", after
    assert look[0] != "none" and look[1] == "1px" and look[2] == "solid", look


# The first open sector's heads after its rows were scrolled under the scroller's top (`box`: the list's scroller):
# their top against the scroller's, and what a press at the middle of each of their cells reaches
STICKY = r"""([box]) => { const scroller = document.querySelector(box), sec = (window.HEAD_SEC = window.HEAD_SEC ?? document.querySelector('.vl-tree .vl-sec .vl-rows').closest('.vl-sec').dataset.sector, document.querySelector(`.vl-tree .vl-sec[data-sector="${window.HEAD_SEC}"]`));
  const heads = sec.querySelector(':scope > .vl-cols'), rows = sec.querySelector('.vl-rows');
  scroller.scrollTop += rows.getBoundingClientRect().top - scroller.getBoundingClientRect().top + 200;
  const h = heads.getBoundingClientRect(), s = scroller.getBoundingClientRect(), r = rows.getBoundingClientRect();
  const cells = [...heads.children].map((c) => { const b = c.getBoundingClientRect(), hit = document.elementFromPoint((b.left + b.right) / 2, (b.top + b.bottom) / 2);
    return !!hit && heads.contains(hit); });
  const right = document.elementFromPoint(s.right - 20, (h.top + h.bottom) / 2);
  return {heads: Math.round(h.top), scroller: Math.round(s.top), rowsAbove: Math.round(s.top - r.top), cells, right: !!right && heads.contains(right) || !!(right && right.closest('.vl-cols'))}; }"""


@pytest.mark.parametrize("device", ["desktop", "390", "412"])
def test_heads_stay_at_the_top(site, device):
    """11 a: the tree's first sector scrolled so that 200 px of its rows lie above the list's scroller (a desktop's list
    body; a phone's sheet body, the sheet at full): its column heads stand at the scroller's top, and a press anywhere
    on them (each cell, and the right end where the rows' stars stand) reaches the heads, not a row."""
    from playwright.sync_api import sync_playwright
    context = {"desktop": DESKTOP, "390": SMALL_PHONE, "412": PIXEL}[device]
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _open(browser, site + f"#run={BIG}", context, script=HELP)
            if device != "desktop":
                page.wait_for_function("() => F.snap() === 'peek' && F.rest()", timeout=WAIT)
                _stop(page, "full")
            page.wait_for_selector(".vl-tree .vl-sec .vl-rows", timeout=WAIT)
            got = page.evaluate(STICKY, [".vl-body" if device == "desktop" else ".u-sheet-body"])
            assert page.errors == []
        finally:
            browser.close()
    print("sticky heads:", device, got)
    assert got["rowsAbove"] >= 150, got  # (the state tests something: rows scrolled under the scroller's top)
    assert abs(got["heads"] - got["scroller"]) <= 1, got
    assert all(got["cells"]) and got["right"], got


# The heads of the sector first open when first read (window.HEAD_SEC: that sector stays open once one of its heads
# was pressed): each one's name, pressed state, class and height; the view's sort and direction, the Sort box's value
# and the direction button's name
HEADS = r"""() => { const v = window.FINDALINE_VIEW.view, heads = [...(window.HEAD_SEC = window.HEAD_SEC ?? document.querySelector('.vl-tree .vl-sec .vl-rows').closest('.vl-sec').dataset.sector, document.querySelector(`.vl-tree .vl-sec[data-sector="${window.HEAD_SEC}"]`)).querySelectorAll(':scope > .vl-cols .vl-head')];
  return {sort: v.sort, desc: v.desc, box: document.querySelector('.vl-tree select.r-sort').value, dir: document.querySelector('.vl-tree .vl-dir').getAttribute('aria-label'),
    heads: heads.map((b) => ({name: b.getAttribute('aria-label'), pressed: b.getAttribute('aria-pressed'), asc: b.parentElement.classList.contains('vl-asc'),
                              h: Math.round(b.getBoundingClientRect().height), hidden: !!b.closest('[aria-hidden="true"]')})),
    best: Array.from(v.inView.best), order: Array.from(v.order)}; }"""
HEAD = r"""() => (window.HEAD_SEC = window.HEAD_SEC ?? document.querySelector('.vl-tree .vl-sec .vl-rows').closest('.vl-sec').dataset.sector, document.querySelector(`.vl-tree .vl-sec[data-sector="${window.HEAD_SEC}"]`)).querySelectorAll(':scope > .vl-cols .vl-head')"""


@pytest.mark.parametrize("device", ["desktop", "phone"])
def test_heads_sort_the_tree(site, device):
    """12 a: the tree's heads are buttons. A press on a column's name sorts the tree by it, largest first (each key's
    first direction); a second press reverses it; the Sort box and the direction button follow, and a change of the Sort
    box moves the heads' mark. The sorted head's name carries the order in today's words; the heads are not hidden from
    a screen reader; Enter on a focused head sorts too; 44 px high on a touch phone. "Best in view" keeps its order
    (best first) when the direction is reversed."""
    from playwright.sync_api import sync_playwright
    context = DESKTOP if device == "desktop" else SMALL_PHONE
    names = [WORDS["ui.list.col.length"], WORDS["ui.list.col.mean"], WORDS["ui.view.col.clear"], WORDS["ui.list.col.lines"]]
    keys = ["len", "hmean", "clr", "n"]
    steps = []
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _open(browser, site + f"#run={BIG}", context, script=HELP)
            if device == "phone":
                page.wait_for_function("() => F.snap() === 'peek' && F.rest()", timeout=WAIT)
                _stop(page, "full")
            page.wait_for_selector(".vl-tree .vl-sec .vl-cols .vl-head", timeout=WAIT)
            start = page.evaluate(HEADS)

            def press(k):
                if device == "phone":
                    # (the sector's heads brought into the sheet's view first: a finger presses what it sees; once the
                    # last press's head was put back: its frames)
                    page.evaluate("() => T.frames().then(() => T.frames()).then(() => T.frames()).then(() => T.frames())")
                    box = page.evaluate(f"() => {{ const e = ({HEAD})()[{k}]; e.scrollIntoView({{block: 'center'}}); const r = e.getBoundingClientRect(); return [(r.left + r.right) / 2, (r.top + r.bottom) / 2]; }}")
                    page.wait_for_function("() => performance.now() - (window.TOUCHED || -1000) > 700", timeout=WAIT)
                    page.touchscreen.tap(box[0], box[1])
                    page.evaluate("() => { window.TOUCHED = performance.now(); }")
                else:
                    page.evaluate(f"() => ({HEAD})()[{k}].click()")
                page.evaluate("() => T.frames()")
                return page.evaluate(HEADS)
            # each head: largest first; again: smallest first (the heads' order: length, height, clearance, lines;
            # the anchors' name is no head)
            for k, key in enumerate(keys):
                first = press(k)
                again = press(k)
                steps.append((key, first, again))
            # by the keyboard: Enter on the length's head
            page.evaluate(f"() => ({HEAD})()[0].focus()")
            page.keyboard.press("Enter")
            page.evaluate("() => T.frames()")
            keyed = page.evaluate(HEADS)
            # the Sort box moves the heads' mark
            page.select_option(".vl-tree select.r-sort", "clr")
            page.wait_for_function("() => window.FINDALINE_VIEW.view.sort === 'clr'", timeout=WAIT)
            page.evaluate("() => T.frames()")
            boxed = page.evaluate(HEADS)
            assert page.errors == []
        finally:
            browser.close()
    print("heads sort:", device, [(k, f["sort"], f["desc"], a["desc"], a["heads"][keys.index(k)]["name"]) for k, f, a in steps])
    assert [h["name"] for h in start["heads"]] == [names[0], names[1] + WORDS["ui.list.sorted_desc"], names[2], names[3]], start["heads"]
    assert not any(h["hidden"] for h in start["heads"]), start
    for (key, first, again), name in zip(steps, names):
        k = keys.index(key)
        assert first["sort"] == key and first["box"] == key and first["desc"] and first["dir"] == WORDS["ui.view.dir_desc"], (key, first)
        assert first["heads"][k]["pressed"] == "true" and first["heads"][k]["name"] == name + WORDS["ui.list.sorted_desc"], (key, first["heads"])
        assert sum(h["pressed"] == "true" for h in first["heads"]) == 1, first["heads"]
        assert again["sort"] == key and not again["desc"] and again["dir"] == WORDS["ui.view.dir_asc"], (key, again)
        assert again["heads"][k]["asc"] and again["heads"][k]["name"] == name + WORDS["ui.list.sorted_asc"], (key, again["heads"])
        assert again["order"] == first["order"] and again["best"] == first["best"], key  # Best in view: best first
    assert keyed["sort"] == "len" and keyed["desc"], keyed
    assert boxed["sort"] == "clr" and boxed["heads"][2]["pressed"] == "true" and boxed["desc"], boxed
    if device == "phone":
        assert all(h["h"] >= 44 for h in start["heads"]), start["heads"]


@pytest.mark.parametrize("device", ["desktop", "phone"])
def test_list_star_opens_the_folders(site, device):
    """13 a: a row's star in the list opens the same folder list as the details' star (FavouritePicker: "Save to a
    folder", its folders, "New folder"), under the row's right end, not a direct save; "New folder" with a name makes
    the folder and saves the row's line into it (on the server), and the star then shows it a favourite. Esc closes the
    picker with nothing saved, the row's plain star back with the focus."""
    from playwright.sync_api import sync_playwright
    context = DESKTOP if device == "desktop" else SMALL_PHONE
    name = "Gate two folder"
    saved = """([run]) => fetch('/api/runs/' + encodeURIComponent(run) + '/favourites').then((r) => r.json()).then((b) => Array.isArray(b) ? {lines: b, in: {}} : b)"""
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _open(browser, site + f"#run={BIG}", context, script=HELP)
            page.wait_for_function("() => window.FINDALINE_VIEW.view.model.favouritesOn", timeout=WAIT)
            if device == "phone":
                page.wait_for_function("() => F.snap() === 'peek' && F.rest()", timeout=WAIT)
                _stop(page, "full")
            star = ".vl-tree .vl-rows > li:nth-child(2) .vl-star"
            page.wait_for_selector(star, timeout=WAIT)
            row = page.evaluate(f"() => Number(document.querySelector('{star}').closest('li').querySelector('.vl-main').dataset.row)")
            before = page.evaluate(saved, [BIG])
            page.evaluate(f"() => document.querySelector('{star}').click()")
            page.wait_for_selector(".vl-tree .vl-row .r-picker", timeout=WAIT)
            opened = page.evaluate("""() => { const p = document.querySelector('.vl-row .r-pop'), li = p.closest('li'), r = p.getBoundingClientRect(), l = li.getBoundingClientRect();
              return {title: p.querySelector('.u-h4').textContent, folders: p.querySelectorAll('.r-folder').length, right: Math.round(l.right - r.right), below: r.top >= li.querySelector('.vl-main').getBoundingClientRect().top}; }""")
            nothing = page.evaluate(saved, [BIG])
            # Esc closes it, nothing saved
            page.wait_for_function("() => !!document.activeElement.closest('.r-pop')", timeout=WAIT)
            page.keyboard.press("Escape")
            page.wait_for_selector(".vl-row .r-picker", state="detached", timeout=WAIT)
            # the row's plain star again, with the focus
            page.wait_for_function(f"() => document.activeElement === document.querySelector('{star}')", timeout=WAIT)
            # again, "New folder": a name, Create
            page.evaluate(f"() => document.querySelector('{star}').click()")
            page.wait_for_selector(".vl-row .r-picker", timeout=WAIT)
            page.evaluate("() => [...document.querySelectorAll('.vl-row .r-picker .u-btn')].find((b) => b.textContent.includes('New folder')).click()")
            page.wait_for_selector(".vl-row .r-newfolder input", timeout=WAIT)
            page.fill(".vl-row .r-newfolder input", name)
            page.evaluate("() => document.querySelector('.vl-row .r-newfolder button[type=submit]').click()")
            page.wait_for_selector(".vl-row .r-picker", state="detached", timeout=WAIT)
            link = page.evaluate(f"() => {{ const m = window.FINDALINE_VIEW.view.model; return m.lineLink(m.lineAt({row})); }}")
            page.wait_for_function(f"([run]) => fetch('/api/runs/' + encodeURIComponent(run) + '/favourites').then((r) => r.json()).then((b) => (Array.isArray(b) ? b : b.lines).includes({json.dumps(link)}))",
                                   arg=[BIG], timeout=WAIT)
            folder = page.evaluate(f"""() => {{ const m = window.FINDALINE_VIEW.view.model, f = m.folderOf(m.lineAt({row}));
              return f === undefined ? 'none' : f === null ? 'top' : m.tree.path(f); }}""")
            page.wait_for_selector(f"{star}[aria-pressed='true']", timeout=WAIT)
            filled = page.evaluate(f"() => !!document.querySelector('{star} svg.u-fav')")
            assert page.errors == []
        finally:
            browser.close()
    print("the list's star:", device, opened, "folder", folder, "filled", filled)
    assert opened["title"] == "Save to a folder" and opened["folders"] >= 1 and abs(opened["right"]) <= 24 and opened["below"], opened
    assert nothing == before, (before, nothing)  # the press saved nothing by itself
    assert folder == name and filled, (folder, filled)


# Is the upright notice shown over the page: its display, the words, and what a press at the window's middle reaches
UPRIGHT = """() => { const n = document.querySelector('.v-upright'), hit = document.elementFromPoint(innerWidth / 2, innerHeight / 2);
  return {shown: !!n && getComputedStyle(n).display !== 'none', text: n ? n.textContent.trim() : null, over: !!n && !!hit && n.contains(hit)}; }"""


@pytest.mark.parametrize("case", ["iphone-side", "pixel-side", "iphone-upright", "pixel-upright", "desktop-side", "tablet-side"])
def test_phone_held_sideways_is_asked_upright(site, case):
    """4 a: a phone held sideways (a touch screen, the window wider than high and lower than 500 px: the iPhone 13 at
    844 x 390, the Pixel at 839 x 412) shows "Turn your phone upright to use this page." over the whole page; upright it
    does not; a desktop window of 844 x 390 with a mouse and a tablet on its side (1024 x 768, touch) do not either."""
    from playwright.sync_api import sync_playwright
    contexts = {
        "iphone-side": {"viewport": {"width": 844, "height": 390}, "device_scale_factor": 3, "is_mobile": True, "has_touch": True},
        "pixel-side": {"viewport": {"width": 839, "height": 412}, "device_scale_factor": 2.625, "is_mobile": True, "has_touch": True},
        "iphone-upright": {"viewport": {"width": 390, "height": 844}, "device_scale_factor": 3, "is_mobile": True, "has_touch": True},
        "pixel-upright": PIXEL,
        "desktop-side": {"viewport": {"width": 844, "height": 390}},
        "tablet-side": {"viewport": {"width": 1024, "height": 768}, "device_scale_factor": 2, "is_mobile": True, "has_touch": True},
    }
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _open(browser, site + f"#run={BIG}", contexts[case], script=HELP)
            page.evaluate("() => T.frames()")
            got = page.evaluate(UPRIGHT)
            assert page.errors == []
        finally:
            browser.close()
    print("upright notice:", case, got)
    if case.endswith("-side") and case.split("-")[0] in ("iphone", "pixel"):
        assert got["shown"] and got["over"] and got["text"] == WORDS["ui.view.upright"], got
    else:
        assert not got["shown"], got


# The page's zoom (the visual viewport's scale) and the map's
ZOOMS = "() => [window.visualViewport ? window.visualViewport.scale : 1, window.FINDALINE_MAP.getZoom()]"


def _pinch(page, x: float, y: float, scale: float = 2.0):
    """A finger's pinch out at (x, y) (Chromium's synthesized touch pinch, CDP: the command answers once the gesture's
    events were sent), then the page drawn and the map still."""
    cdp = page.context.new_cdp_session(page)
    cdp.send("Input.synthesizePinchGesture", {"x": x, "y": y, "scaleFactor": scale, "relativeSpeed": 800, "gestureSourceType": "touch"})
    cdp.detach()
    page.evaluate("() => T.frames()")
    page.wait_for_function(STILL, timeout=WAIT)
    page.evaluate("() => T.frames()")


@pytest.mark.parametrize("device", [SMALL_PHONE, PIXEL], ids=["390", "412"])
def test_no_page_zoom_outside_the_map(site, device):
    """6 b: on a phone a pinch on the sheet (its body at half) does not zoom the page (the visual viewport's scale stays
    1), nor does a double tap there; a pinch on the map zooms the map, not the page. The frame takes panning only
    (touch-action), and a gesturestart outside the map (iOS Safari's pinch) is stopped, on the map not."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _open(browser, site + f"#run={BIG}", device, script=HELP)
            page.wait_for_function("() => F.snap() === 'peek' && F.rest()", timeout=WAIT)
            _stop(page, "half")
            start = page.evaluate(ZOOMS)
            body = page.evaluate("() => { const r = document.querySelector('.u-sheet-body').getBoundingClientRect(); return [(r.left + r.right) / 2, r.top + 60]; }")
            _pinch(page, *body)
            pinched = page.evaluate(ZOOMS)
            # a double tap: the second tap's click awaited (a counter of the page's clicks), then the page drawn
            page.evaluate("() => { window.CLICKS = 0; document.addEventListener('click', () => { window.CLICKS++; }, true); }")
            page.touchscreen.tap(*body)
            page.touchscreen.tap(*body)
            page.wait_for_function("() => window.CLICKS >= 2", timeout=WAIT)
            page.evaluate("() => T.frames()")
            page.wait_for_function(STILL, timeout=WAIT)
            tapped = page.evaluate(ZOOMS)
            m = page.evaluate("() => { const r = window.FINDALINE_MAP.getContainer().getBoundingClientRect(), s = document.querySelector('.u-sheet').getBoundingClientRect(); return [(r.left + r.right) / 2, (r.top + 120 + s.top) / 2]; }")
            _pinch(page, *m)
            page.wait_for_function(f"() => window.FINDALINE_MAP.getZoom() !== {start[1]}", timeout=WAIT)
            page.wait_for_function(STILL, timeout=WAIT)
            mapped = page.evaluate(ZOOMS)
            gestures = page.evaluate("""() => ['.u-sheet-body', '.leaflet-container'].map((sel) => { const e = new Event('gesturestart', {bubbles: true, cancelable: true});
              document.querySelector(sel).dispatchEvent(e); return e.defaultPrevented; })""")
            action = page.evaluate("() => getComputedStyle(document.querySelector('.c-result-phone')).touchAction")
            assert page.errors == []
        finally:
            browser.close()
    print("page zoom:", device.get("viewport"), {"start": start, "pinched": pinched, "tapped": tapped, "map": mapped, "gestures": gestures, "action": action})
    assert pinched[0] == 1 and tapped[0] == 1, (pinched, tapped)
    assert mapped[0] == 1 and mapped[1] > start[1], (start, mapped)  # the map's own pinch
    assert gestures == [True, False] and action == "pan-x pan-y", (gestures, action)


# --- gate 2's fix round (the code review's round 4, the design review's gate 2 changes) ---

FOCUSED_HEAD = "() => { const a = document.activeElement; return a && a.classList.contains('vl-head') ? [a.dataset.col, a.getAttribute('aria-label')] : (a ? a.tagName : null); }"


@pytest.mark.parametrize("device", ["desktop", "phone"])
def test_head_keeps_the_focus_when_it_reverses(site, device):
    """The design review's G2-F1: the first sector's length head pressed by the keyboard (Enter) sorts by length; Enter
    again reverses it, and the focus stays on that head (it fell to the page's body: the new order moves the sectors);
    a third Enter reverses it back."""
    from playwright.sync_api import sync_playwright
    context = DESKTOP if device == "desktop" else SMALL_PHONE
    got = []
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _open(browser, site + f"#run={BIG}", context, script=HELP)
            if device == "phone":
                page.wait_for_function("() => F.snap() === 'peek' && F.rest()", timeout=WAIT)
                _stop(page, "full")
            page.wait_for_selector(".vl-tree .vl-sec .vl-cols .vl-head", timeout=WAIT)
            page.evaluate(f"() => ({HEAD})()[0].focus()")
            for desc in (True, False, True):
                page.keyboard.press("Enter")
                page.wait_for_function(f"() => window.FINDALINE_VIEW.view.sort === 'len' && window.FINDALINE_VIEW.view.desc === {str(desc).lower()}", timeout=WAIT)
                page.evaluate("() => T.frames().then(() => T.frames()).then(() => T.frames())")
                got.append(page.evaluate(FOCUSED_HEAD))
            assert page.errors == []
        finally:
            browser.close()
    print("the head's focus:", device, got)
    assert [g[0] if isinstance(g, list) else g for g in got] == ["len", "len", "len"], got
    assert got[1][1] == WORDS["ui.list.col.length"] + WORDS["ui.list.sorted_asc"], got


def test_heads_at_least_24_px_on_a_desktop(site):
    """The design review's G2-F2: on a desktop every sort head of the tree is at least 24 px high (R2) and as tall as
    the others (Length, Clearance and Lines were 20 px beside a two-line "Mean height")."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _open(browser, site + f"#run={BIG}", DESKTOP, script=HELP)
            page.wait_for_selector(".vl-tree .vl-sec .vl-cols .vl-head", timeout=WAIT)
            got = page.evaluate(HEADS)["heads"]
            assert page.errors == []
        finally:
            browser.close()
    heights = [h["h"] for h in got]
    print("desktop heads' heights:", heights)
    assert min(heights) >= 24 and max(heights) - min(heights) <= 1, heights


def test_row_picker_ends_with_its_row(site):
    """The code review's G1: a row's folder picker open (the star of "Best in view"'s first row) when its row leaves the
    list (the map moved away: the row is no longer among the best in view) ends with it: the focus does not fall to the
    page's body, and when the map comes back the row draws its plain star, no picker open by itself."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _open(browser, site + f"#run={BIG}", DESKTOP, script=HELP)
            page.wait_for_function("() => window.FINDALINE_VIEW.view.model.favouritesOn", timeout=WAIT)
            _state(page, "view.setLevel('spots');")
            star = ".vl-topblock .vl-rows > li:first-child > .vl-star"
            page.wait_for_selector(star, timeout=WAIT)
            row_id = page.evaluate(f"() => document.querySelector('{star}').closest('li').id")
            page.evaluate(f"() => document.querySelector('{star}').click()")
            page.wait_for_selector(".vl-topblock .vl-row .r-picker", timeout=WAIT)
            page.wait_for_function("() => !!document.activeElement.closest('.r-pop')", timeout=WAIT)
            home = page.evaluate(CENTRE)
            _state(page, "leaflet.panBy([4000, 3000], {animate: false});")
            page.wait_for_function(f"() => !document.getElementById('{row_id}')", timeout=WAIT)
            page.evaluate("() => T.frames().then(() => T.frames())")
            away = page.evaluate("() => [document.activeElement ? document.activeElement.tagName : null, !!document.querySelector('.r-picker')]")
            _state(page, f"leaflet.setView([{home[0]}, {home[1]}], {home[2]}, {{animate: false}});")
            page.wait_for_function(f"() => !!document.getElementById('{row_id}')", timeout=WAIT)
            page.evaluate("() => T.frames()")
            back = page.evaluate(f"() => [!!document.querySelector('.r-picker'), !!document.querySelector('#{row_id} > .vl-star')]")
            assert page.errors == []
        finally:
            browser.close()
    print("the row's picker:", {"away": away, "back": back})
    assert away[0] != "BODY" and not away[1], away
    assert back == [False, True], back


@pytest.mark.parametrize("width", [260, 340, 372, 500])
def test_list_never_scrolls_sideways(site, width):
    """The code review's G2: the sticky heads' ground (its layer past the heads' sides) does not widen the desktop list's
    scroller: at every kept list width the list body is as wide as its content (no sideways scroll); a phone's sheet
    body neither."""
    from playwright.sync_api import sync_playwright
    layout = ("try { localStorage.setItem('findaline.layout', JSON.stringify({v: 1, list: {w: %d, open: true}, details: {w: 380, open: true}, "
              "profile: {h: 300, folded: false, l: 12, r: 12}})); } catch (e) {}" % width)
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _open(browser, site + f"#run={BIG}", {"viewport": {"width": 1400, "height": 900}}, script=HELP + layout)
            page.wait_for_selector(".vl-tree .vl-sec .vl-cols .vl-head", timeout=WAIT)
            got = page.evaluate("() => { const b = document.querySelector('.vl-body'); b.scrollLeft = 60; return [b.scrollWidth, b.clientWidth, b.scrollLeft, Math.round(b.getBoundingClientRect().width)]; }")
            page.context.close()
            page = _open(browser, site + f"#run={BIG}", SMALL_PHONE, script=HELP)
            page.wait_for_function("() => F.snap() === 'peek' && F.rest()", timeout=WAIT)
            _stop(page, "full")
            phone = page.evaluate("() => { const b = document.querySelector('.u-sheet-body'); b.scrollLeft = 60; return [b.scrollWidth, b.clientWidth, b.scrollLeft]; }")
            assert page.errors == []
        finally:
            browser.close()
    print("sideways:", width, "desktop", got, "phone", phone)
    assert got[0] <= got[1] and got[2] == 0, got
    assert phone[0] <= phone[1] and phone[2] == 0, phone


def test_layers_hover_leaves_the_sheet(boxes_site):
    """The code review's G3: a narrow window with a mouse (760 x 900: the phone frame, no touch), the sheet at half: the
    mouse passing over the layers button opens the menu (Leaflet's hover) but leaves the sheet at half; a click on it
    (and Enter on its button) opened by a press drops the sheet to its low stop (9 a)."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _open(browser, boxes_site + f"#run={BOXES}", {"viewport": {"width": 760, "height": 900}}, script=HELP)
            page.wait_for_function("() => F.snap() === 'peek' && F.rest()", timeout=WAIT)
            _stop(page, "half")
            box = page.evaluate("() => { const r = document.querySelector('.v-map .leaflet-control-layers').getBoundingClientRect(); return [(r.left + r.right) / 2, (r.top + r.bottom) / 2]; }")
            page.mouse.move(*box)
            page.wait_for_selector(".v-map .leaflet-control-layers-expanded", timeout=WAIT)
            page.evaluate("() => T.frames().then(() => T.frames())")
            hovered = page.evaluate("() => F.snap()")
            page.mouse.move(5, 450)  # away: Leaflet closes it
            page.wait_for_selector(".v-map .leaflet-control-layers-expanded", state="detached", timeout=WAIT)
            # by the keyboard: Enter on the layers' button opens it by a press
            page.focus(".v-map .leaflet-control-layers-toggle")
            page.keyboard.press("Enter")
            page.wait_for_selector(".v-map .leaflet-control-layers-expanded", timeout=WAIT)
            page.wait_for_function("() => F.snap() === 'peek' && F.rest()", timeout=WAIT)
            keyed = page.evaluate("() => F.snap()")
            assert page.errors == []
        finally:
            browser.close()
    print("layers by hover and by a key:", hovered, keyed)
    assert hovered == "half" and keyed == "peek", (hovered, keyed)


@pytest.mark.parametrize("selected", [True, False], ids=["selected", "none"])
def test_head_press_keeps_its_place(site, selected):
    """The code review's G4 (the final design check's F4 for the heads): with a spot selected (the tree's second-last;
    and with none, in the tree's first sector), a press on a head for a new key, then on it again (the reverse), leaves
    the heads where they were under the pointer (they ran to y 2 before: the list scrolled to the selected row; with
    none, the new order put other sectors above it), and a selected row is still drawn."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _open(browser, site + f"#run={BIG}", DESKTOP, script=HELP)
            tree = page.evaluate("() => window.FINDALINE_VIEW.view.sectors.flatMap((s) => s.spots)")
            spot = tree[-2] if selected else tree[0]
            if selected:
                _state(page, f"view.select({spot});")
            page.wait_for_selector(f"#vl-row-{spot} > .vl-main", timeout=WAIT)
            sector = page.evaluate(f"() => window.FINDALINE_VIEW.view.sectorOf({spot})")
            head = f".vl-sec[data-sector='{sector}'] > .vl-cols .vl-head[data-col='len']"
            page.evaluate(f"() => {{ const h = document.querySelector(\"{head}\"), box = h.closest('.vl-body'); box.scrollTop += h.getBoundingClientRect().top - box.getBoundingClientRect().top - 200; }}")
            page.evaluate("() => T.frames()")
            top = lambda: page.evaluate(f"() => Math.round(document.querySelector(\"{head}\").getBoundingClientRect().top)")
            places = [top()]
            # (with a spot selected a mouse's press; with none the keyboard's: Enter on the focused head, twice)
            if not selected:
                page.evaluate(f"() => document.querySelector(\"{head}\").focus({{preventScroll: true}})")
            for desc in (True, False):
                if selected:
                    page.click(head)
                else:
                    page.keyboard.press("Enter")
                page.wait_for_function(f"() => window.FINDALINE_VIEW.view.sort === 'len' && window.FINDALINE_VIEW.view.desc === {str(desc).lower()}", timeout=WAIT)
                page.evaluate("() => T.frames().then(() => T.frames()).then(() => T.frames())")
                places.append(top())
            drawn = page.evaluate(f"() => !!document.querySelector('#vl-row-{spot} > .vl-main[aria-pressed=\"true\"]')")
            assert page.errors == []
        finally:
            browser.close()
    print("the head's place:", selected, places, "row drawn", drawn)
    assert max(places) - min(places) <= 1, places
    assert drawn or not selected


@pytest.mark.parametrize("width", [260, 300])
def test_row_picker_inside_a_narrow_list(site, width):
    """The code review's note on 13 a: with the list kept at 260 (and 300) px, a row's folder picker stays inside the
    window and inside the list's column."""
    from playwright.sync_api import sync_playwright
    layout = ("try { localStorage.setItem('findaline.layout', JSON.stringify({v: 1, list: {w: %d, open: true}, details: {w: 380, open: true}, "
              "profile: {h: 300, folded: false, l: 12, r: 12}})); } catch (e) {}" % width)
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _open(browser, site + f"#run={BIG}", DESKTOP, script=HELP + layout)
            page.wait_for_function("() => window.FINDALINE_VIEW.view.model.favouritesOn", timeout=WAIT)
            star = ".vl-tree .vl-rows > li:nth-child(2) > .vl-star"
            page.wait_for_selector(star, timeout=WAIT)
            page.evaluate(f"() => document.querySelector('{star}').click()")
            page.wait_for_selector(".vl-row .r-picker", timeout=WAIT)
            got = page.evaluate("""() => { const p = document.querySelector('.vl-row .r-pop').getBoundingClientRect(), l = document.querySelector('.c-col-list').getBoundingClientRect();
              return {pop: [Math.round(p.left), Math.round(p.right)], list: [Math.round(l.left), Math.round(l.right)], window: innerWidth}; }""")
            assert page.errors == []
        finally:
            browser.close()
    print("the picker in a narrow list:", width, got)
    assert got["pop"][0] >= 0 and got["pop"][1] <= got["window"], got
    assert got["pop"][0] >= got["list"][0] and got["pop"][1] <= got["list"][1], got


# The bottom of each head's words in the first open sector (a text range's last line box): the buttons' and the
# anchors' name
WORD_BOTTOMS = """() => { const sec = document.querySelector('.vl-tree .vl-sec .vl-rows').closest('.vl-sec'), out = {};
  for (const e of sec.querySelectorAll(':scope > .vl-cols > .vl-hcell .vl-head, :scope > .vl-cols > .vl-cell-acc')) {
    const r = document.createRange(); r.selectNodeContents(e); const rects = [...r.getClientRects()].filter((x) => x.width > 0);
    out[e.textContent.trim()] = Math.round(Math.max(...rects.map((x) => x.bottom)) * 10) / 10; }
  return out; }"""


@pytest.mark.parametrize("device", ["desktop", "390", "412"])
def test_anchors_head_on_the_heads_line(site, device):
    """The design review's G2-F5: in a sector's heads the anchors' name (no sort head) stands on the line of the sort
    heads' words (it stood about 2 to 4 px lower on the phones): the bottoms of their words within 1 px."""
    from playwright.sync_api import sync_playwright
    context = {"desktop": DESKTOP, "390": SMALL_PHONE, "412": PIXEL}[device]
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _open(browser, site + f"#run={BIG}", context, script=HELP)
            if device != "desktop":
                page.wait_for_function("() => F.snap() === 'peek' && F.rest()", timeout=WAIT)
                _stop(page, "full")
            page.wait_for_selector(".vl-tree .vl-sec .vl-cols .vl-head", timeout=WAIT)
            got = page.evaluate(WORD_BOTTOMS)
            assert page.errors == []
        finally:
            browser.close()
    print("the heads' word bottoms:", device, got)
    anchors = got.pop(WORDS["ui.list.col.anchors"])
    assert got and all(abs(anchors - b) <= 1 for b in got.values()), (anchors, got)


# The sideways notice: its words, the words of each of its lines, what in the frame is inert, and where Tab goes
NOTICE = """() => { const n = document.querySelector('.v-upright'), p = n && n.querySelector('p'), text = p && p.firstChild, lines = [];
  if (text) { let at = 0; for (const word of text.textContent.split(' ')) { const r = document.createRange(); r.setStart(text, at); r.setEnd(text, at + word.length); at += word.length + 1;
    const top = Math.round(r.getBoundingClientRect().top); const line = lines.find((l) => Math.abs(l.top - top) <= 2); if (line) line.words.push(word); else lines.push({top, words: [word]}); } }
  const frame = n.parentElement;
  return {role: n.getAttribute('role'), text: p ? p.textContent : null, lines: lines.map((l) => l.words.length),
          inert: Array.from(frame.children).filter((e) => e !== n).every((e) => e.inert), others: frame.children.length - 1}; }"""


@pytest.mark.parametrize("device", ["iphone", "pixel"])
def test_sideways_notice_hides_the_page(site, device):
    """The design review's G2-F4: a phone held sideways: the notice is an alert region holding its words (put in when
    it shows, so a screen reader announces it), the rest of the view's frame is inert (Tab reaches nothing behind it),
    and no word stands alone on its last line ("page."). Upright again: nothing inert, the words gone from the region."""
    from playwright.sync_api import sync_playwright
    size = {"iphone": (844, 390, 3), "pixel": (839, 412, 2.625)}[device]
    context = {"viewport": {"width": size[0], "height": size[1]}, "device_scale_factor": size[2], "is_mobile": True, "has_touch": True}
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _open(browser, site + f"#run={BIG}", context, script=HELP)
            page.evaluate("() => T.frames()")
            side = page.evaluate(NOTICE)
            tabbed = []
            for _ in range(6):
                page.keyboard.press("Tab")
                tabbed.append(page.evaluate("() => { const a = document.activeElement; return !a || a === document.body ? 'body' : (a.closest('.v-upright') ? 'notice' : a.className.toString().slice(0, 30)); }"))
            page.set_viewport_size({"width": size[1], "height": size[0]})
            page.wait_for_function("() => !document.querySelector('.v-upright p')", timeout=WAIT)
            upright = page.evaluate(NOTICE)
            assert page.errors == []
        finally:
            browser.close()
    print("the sideways notice:", device, side, tabbed, upright)
    assert side["role"] == "alert" and side["text"] == WORDS["ui.view.upright"] and side["inert"] and side["others"] > 0, side
    assert len(side["lines"]) == 1 or side["lines"][-1] >= 2, side
    assert all(t in ("body", "notice") for t in tabbed), tabbed
    assert upright["text"] is None and not upright["inert"], upright


def test_head_quick_presses_keep_its_place(site):
    """A head's two quick presses by the keyboard (Enter, Enter: a new key, then the reverse, before the first was put
    back): the head stays where it stood before the first, with the focus (the second press took the first's place to
    keep; before, it kept the place the first press's new order had pushed it to)."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _open(browser, site + f"#run={BIG}", DESKTOP, script=HELP)
            page.wait_for_selector(".vl-tree .vl-sec .vl-cols .vl-head", timeout=WAIT)
            page.evaluate(f"() => {{ const h = ({HEAD})()[0]; h.scrollIntoView({{block: 'center'}}); h.focus(); }}")
            read = f"() => {{ const h = ({HEAD})()[0]; return [Math.round(h.getBoundingClientRect().top), document.activeElement === h]; }}"
            before = page.evaluate(read)
            page.keyboard.press("Enter")
            page.keyboard.press("Enter")
            page.wait_for_function("() => window.FINDALINE_VIEW.view.sort === 'len' && !window.FINDALINE_VIEW.view.desc", timeout=WAIT)
            page.evaluate("() => T.frames().then(() => T.frames()).then(() => T.frames()).then(() => T.frames())")
            after = page.evaluate(read)
            assert page.errors == []
        finally:
            browser.close()
    print("two quick presses:", before, after)
    assert abs(after[0] - before[0]) <= 1 and after[1], (before, after)


# --- gate 2's last small round (the design re-check's G2-F6, G2-F7; the notice's focus) ---

# The sorted head's mark: its box, its own head's box, the first line of its own word, and the text box of the head
# before it (the neighbour's words)
MARK = """() => { const sec = document.querySelector('.vl-tree .vl-sec .vl-rows').closest('.vl-sec');
  const heads = [...sec.querySelectorAll(':scope > .vl-cols > .vl-hcell > .vl-head')], at = heads.findIndex((h) => h.querySelector('.u-ic'));
  const head = heads[at], icon = head.querySelector('.u-ic').getBoundingClientRect(), box = head.getBoundingClientRect();
  const words = (e) => { const r = document.createRange(); r.selectNodeContents(e.querySelector('.vl-head-t') || e); return [...r.getClientRects()].filter((x) => x.width > 2); };
  const own = words(head).filter((x) => x.width > icon.width + 2), lines = [...new Set(own.map((x) => Math.round(x.top)))].sort((a, b) => a - b);
  const before = at > 0 ? words(heads[at - 1]) : [];
  return {col: head.dataset.col, icon: [icon.left, icon.top, icon.right, icon.bottom], box: [box.left, box.top, box.right, box.bottom],
          firstLine: lines[0], lines: lines.length, gap: before.length ? icon.left - Math.max(...before.map((x) => x.right)) : null}; }"""


# The sorted head of the first open sector: its mark's box, its own words' boxes, its own box, and the words of the
# heads before and after it
MARKS = """() => { const sec = document.querySelector('.vl-tree .vl-sec .vl-rows').closest('.vl-sec');
  const heads = [...sec.querySelectorAll(':scope > .vl-cols > .vl-hcell > .vl-head, :scope > .vl-cols > .vl-cell-acc')];
  const at = heads.findIndex((h) => h.querySelector('.u-ic')), head = heads[at];
  const rect = (r) => [r.left, r.top, r.right, r.bottom];
  const words = (e) => { const r = document.createRange(); r.selectNodeContents(e.querySelector('.vl-head-t') || e);
    return [...r.getClientRects()].filter((x) => x.width > 2 && x.height > 2); };
  const icon = head.querySelector('.u-ic').getBoundingClientRect(), own = words(head).filter((x) => Math.abs(x.width - icon.width) > 0.5);
  const lines = [...new Set(own.map((x) => Math.round(x.top)))].sort((a, b) => a - b);
  const prev = at > 0 ? words(heads[at - 1]) : [], next = at < heads.length - 1 ? words(heads[at + 1]) : [];
  const before = (xs) => prev.length ? Math.min(...xs.map((x) => x.left)) - Math.max(...prev.map((x) => x.right)) : null;
  const after = (xs) => next.length ? Math.min(...next.map((x) => x.left)) - Math.max(...xs.map((x) => x.right)) : null;
  return {col: head.dataset.col, text: head.textContent.trim(), box: rect(head.getBoundingClientRect()), icon: rect(icon), own: own.map(rect),
          firstLine: lines[0], markBefore: before([icon]), markAfter: after([icon]), wordsBefore: before(own), wordsAfter: after(own)}; }"""
SORT_CASES = [(k, d) for k in ("hmean", "hmax", "len", "clr", "n") for d in (True, False)]


@pytest.mark.parametrize("device", ["260", "300", "372", "390", "412"])
def test_sort_mark_by_its_own_word(site, device):
    """The design re-check's G2-F6 and the code review's round 6: for every sort key, in either direction, the sorted
    head's mark and words stay inside its own head's box, the mark above or before the first line of its own word, the
    mark's box at least 2 px clear of the neighbours' words and its words never over theirs (sorted by clearance or lines
    "↓Clearance" ran 6-13 px over the word before it) - on a desktop with the list at 260, 300 and 372 px, and on both
    phones with the sheet at full."""
    from playwright.sync_api import sync_playwright
    phone = device in ("390", "412")
    context = {"390": SMALL_PHONE, "412": PIXEL}[device] if phone else DESKTOP
    layout = "" if phone else ("try { localStorage.setItem('findaline.layout', JSON.stringify({v: 1, list: {w: %s, open: true}, details: {w: 380, open: true}, "
                               "profile: {h: 300, folded: false, l: 12, r: 12}})); } catch (e) {}" % device)
    got = []
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _open(browser, site + f"#run={BIG}", context, script=HELP + layout)
            if phone:
                page.wait_for_function("() => F.snap() === 'peek' && F.rest()", timeout=WAIT)
                _stop(page, "full")
            page.wait_for_selector(".vl-tree .vl-sec .vl-cols .vl-head .u-ic", timeout=WAIT)
            for key, desc in SORT_CASES:
                page.evaluate(f"() => {{ const v = window.FINDALINE_VIEW.view; v.setSort('{key}'); v.setDesc({str(desc).lower()}); }}")
                page.evaluate("() => T.frames()")
                got.append([key, desc, page.evaluate(MARKS)])
            assert page.errors == []
        finally:
            browser.close()
    bad = []
    for key, desc, m in got:
        b, i = m["box"], m["icon"]
        inside = all(b[0] - 0.5 <= r[0] and r[2] <= b[2] + 0.5 and b[1] - 0.5 <= r[1] and r[3] <= b[3] + 0.5 for r in [i, *m["own"]])
        # the mark's box at least 2 px clear of the neighbours' words (its arrow is drawn in the middle of its 12 px box:
        # the ink keeps 5 px more), its own words never over theirs (at 260 and 300 px the columns' words themselves come
        # within 2 or 3 px of each other: the grid's 4 px gap, sorted or not)
        apart = all(g is None or g >= 2 for g in (m["markBefore"], m["markAfter"])) and all(g is None or g >= 1 for g in (m["wordsBefore"], m["wordsAfter"]))
        placed = i[1] <= m["firstLine"] + 8  # the mark on or above its word's first line
        if not (inside and apart and placed):
            bad.append([key, desc, m["text"], [None if g is None else round(g, 1) for g in (m["markBefore"], m["markAfter"], m["wordsBefore"], m["wordsAfter"])],
                        inside, placed])
    print("the sort marks:", device, len(got), "cases; bad:", bad)
    assert not bad, bad


# The star of the lowest row in view of the phone's sheet body (its li's id)
LOWEST_STAR = """() => { const box = document.querySelector('.u-sheet-body').getBoundingClientRect();
  const stars = [...document.querySelectorAll('.vl-rows > li > .vl-star')].filter((s) => { const r = s.getBoundingClientRect(); return r.height && r.top >= box.top && r.bottom <= box.bottom; });
  const low = stars.sort((a, b) => b.getBoundingClientRect().bottom - a.getBoundingClientRect().bottom)[0]; return low ? low.closest('li').id : null; }"""
# Each item of the open row picker: inside the window and the sheet body's view, and a press at its middle reaching it
PICKER_ITEMS = """() => { const pop = document.querySelector('.vl-row .r-pop'), box = document.querySelector('.u-sheet-body').getBoundingClientRect();
  return [...pop.querySelectorAll('button')].map((b) => { const r = b.getBoundingClientRect(), hit = document.elementFromPoint((r.left + r.right) / 2, (r.top + r.bottom) / 2);
    return {name: b.textContent.trim().slice(0, 20), y: [Math.round(r.top), Math.round(r.bottom)], inside: r.top >= box.top - 0.5 && r.bottom <= Math.min(box.bottom, innerHeight) + 0.5,
            on: !!hit && b.contains(hit)}; }); }"""


@pytest.mark.parametrize("stop", ["half", "full"])
@pytest.mark.parametrize("device", [SMALL_PHONE, PIXEL], ids=["390", "412"])
def test_row_picker_whole_from_the_lowest_row(site, device, stop):
    """The design re-check's G2-F7: on a phone (the sheet at half or at full) the star of the lowest row in view opens
    its folder list (the sheet rises to full for it) whole in the sheet's view: every item inside the window and
    pressable, no swipe needed (it ran past the screen's foot: "New folder" below it); also from the list's very last
    row, where the list cannot scroll further (the list opens upward)."""
    from playwright.sync_api import sync_playwright
    got = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            for case in ("lowest", "last"):
                page = _open(browser, site + f"#run={BIG}", device, script=HELP)
                page.wait_for_function("() => window.FINDALINE_VIEW.view.model.favouritesOn", timeout=WAIT)
                page.wait_for_function("() => F.snap() === 'peek' && F.rest()", timeout=WAIT)
                _stop(page, stop)
                if case == "last":
                    # the tree's last sector opened, the list at its end: its last row is the list's last
                    page.evaluate("() => { const t = [...document.querySelectorAll('.vl-tree .vl-sec')].pop().querySelector('.vl-toggle'); if (t.getAttribute('aria-expanded') !== 'true') t.click(); }")
                    page.evaluate("() => T.frames()")
                    page.evaluate("() => { const b = document.querySelector('.u-sheet-body'); b.scrollTop = b.scrollHeight; }")
                    page.evaluate("() => T.frames()")
                else:
                    # the first sector's rows brought to the sheet's foot: its tenth row the lowest in view
                    page.evaluate("""() => { const b = document.querySelector('.u-sheet-body'), r = document.querySelector('.vl-tree .vl-sec .vl-rows > li:nth-child(10)');
                      b.scrollTop += r.getBoundingClientRect().bottom - b.getBoundingClientRect().bottom + 2; }""")
                    page.evaluate("() => T.frames()")
                row = page.evaluate(LOWEST_STAR)
                assert row, "no row's star in the sheet's view"
                page.evaluate(f"() => document.querySelector('#{row} > .vl-star').click()")
                page.wait_for_selector(".vl-row .r-picker", timeout=WAIT)
                page.wait_for_function("() => F.snap() === 'full' && F.rest()", timeout=WAIT)
                page.wait_for_function(f"""() => {{ const p = document.querySelector('.vl-row .r-pop'), b = document.querySelector('.u-sheet-body').getBoundingClientRect();
                  return p && p.getBoundingClientRect().bottom <= Math.min(b.bottom, innerHeight) + 0.5; }}""", timeout=WAIT)
                page.evaluate("() => T.frames()")
                got[case] = page.evaluate(PICKER_ITEMS)
                assert page.errors == []
                page.context.close()
        finally:
            browser.close()
    print("the lowest row's picker:", device.get("viewport"), stop, got)
    for case, items in got.items():
        assert len(items) >= 2 and all(i["inside"] and i["on"] for i in items), (case, items)


FOCUS_NOW = "() => { const a = document.activeElement; return !a || a === document.body ? 'body' : a.className.toString().slice(0, 40); }"


@pytest.mark.parametrize("turn", ["same-frame", "other-frame"])
def test_focus_back_after_the_sideways_notice(site, turn):
    """The sideways notice's focus (the design re-check): a phone upright with the focus on the sheet's handle, turned
    sideways (the notice over an inert page: the focus leaves the handle), and upright again: the focus is back on the
    handle (375 x 667 <-> 667 x 375: the same phone frame), or, where turning drew the other frame and the handle went
    with it (390 x 844 <-> 844 x 390), on the new frame's first stop, never on the page's body."""
    from playwright.sync_api import sync_playwright
    up, side = ((375, 667), (667, 375)) if turn == "same-frame" else ((390, 844), (844, 390))
    context = {"viewport": {"width": up[0], "height": up[1]}, "device_scale_factor": 3, "is_mobile": True, "has_touch": True}
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _open(browser, site + f"#run={BIG}", context, script=HELP)
            page.wait_for_function("() => F.snap() === 'peek' && F.rest()", timeout=WAIT)
            page.focus(".u-sheet-handle")
            before = page.evaluate(FOCUS_NOW)
            page.set_viewport_size({"width": side[0], "height": side[1]})
            page.wait_for_selector(".v-upright p", timeout=WAIT)
            during = page.evaluate(FOCUS_NOW)
            page.set_viewport_size({"width": up[0], "height": up[1]})
            page.wait_for_function("() => !document.querySelector('.v-upright p')", timeout=WAIT)
            page.wait_for_function("() => document.activeElement && document.activeElement !== document.body", timeout=WAIT)
            after = page.evaluate(FOCUS_NOW)
            first = page.evaluate("() => { const f = document.querySelector('.v-result'); const e = f.querySelector(\"button:not([disabled]), [href], input:not([disabled]), select, [tabindex]:not([tabindex='-1'])\"); return e ? e.className.toString().slice(0, 40) : null; }")
            assert page.errors == []
        finally:
            browser.close()
    print("the focus around the notice:", turn, before, during, after, "first stop", first)
    assert "u-sheet-handle" in before and "u-sheet-handle" not in during, (before, during)
    assert after == (before if turn == "same-frame" else first), (after, before, first)


def test_layers_press_inside_then_hover_leaves_the_sheet(boxes_site):
    """The code review's round 5: in a narrow window with a mouse (760 x 900) the sheet at half: the layers menu opened
    by hover, a press inside it (a layer's row), the mouse out (Leaflet closes it) and back at once (a hover reopens it
    within 800 ms of that press): the sheet stays at half (the press counted for the reopening before)."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _open(browser, boxes_site + f"#run={BOXES}", {"viewport": {"width": 760, "height": 900}}, script=HELP)
            page.wait_for_function("() => F.snap() === 'peek' && F.rest()", timeout=WAIT)
            _stop(page, "half")
            box = page.evaluate("() => { const r = document.querySelector('.v-map .leaflet-control-layers').getBoundingClientRect(); return [(r.left + r.right) / 2, (r.top + r.bottom) / 2]; }")
            page.mouse.move(*box)
            page.wait_for_selector(".v-map .leaflet-control-layers-expanded", timeout=WAIT)
            row = page.evaluate("() => { const r = document.querySelectorAll('.v-map .leaflet-control-layers-expanded label')[1].getBoundingClientRect(); return [(r.left + r.right) / 2, (r.top + r.bottom) / 2]; }")
            page.mouse.move(*row)
            page.mouse.down()
            page.mouse.up()
            page.mouse.move(5, 450)
            page.wait_for_selector(".v-map .leaflet-control-layers-expanded", state="detached", timeout=WAIT)
            page.mouse.move(*box)
            page.wait_for_selector(".v-map .leaflet-control-layers-expanded", timeout=WAIT)
            page.evaluate("() => T.frames().then(() => T.frames())")
            snap = page.evaluate("() => F.snap()")
            assert page.errors == []
        finally:
            browser.close()
    print("press inside, then hover:", snap)
    assert snap == "half", snap


# The pressed head's top at every animation frame after its press, for ten frames (window.TOPS)
FRAME_TOPS = """(sel) => new Promise((ok) => { const out = [], h = () => document.querySelector(sel); let n = 10;
  const step = () => { const e = h(); out.push(e ? Math.round(e.getBoundingClientRect().top) : null); if (--n > 0) requestAnimationFrame(step); else ok(out); };
  h().click(); requestAnimationFrame(step); })"""


def test_head_new_key_never_jumps(site):
    """A head's new key with a spot selected (the tree's second-last; the code review's round 5 on sortBy's `still`):
    the head is drawn where it stood in every frame after the press. (Measured: this holds also without `still`, the
    put-back alone holds the head in the first frame, so the test guards the put-back, not `still`.)"""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _open(browser, site + f"#run={BIG}", DESKTOP, script=HELP)
            tree = page.evaluate("() => window.FINDALINE_VIEW.view.sectors.flatMap((s) => s.spots)")
            spot = tree[-2]
            _state(page, f"view.select({spot});")
            page.wait_for_selector(f"#vl-row-{spot} > .vl-main", timeout=WAIT)
            sector = page.evaluate(f"() => window.FINDALINE_VIEW.view.sectorOf({spot})")
            head = f".vl-sec[data-sector='{sector}'] > .vl-cols .vl-head[data-col='clr']"
            page.evaluate(f"() => {{ const h = document.querySelector(\"{head}\"), box = h.closest('.vl-body'); box.scrollTop += h.getBoundingClientRect().top - box.getBoundingClientRect().top - 200; }}")
            page.evaluate("() => T.frames()")
            start = page.evaluate(f"() => Math.round(document.querySelector(\"{head}\").getBoundingClientRect().top)")
            tops = page.evaluate(FRAME_TOPS, head)
            assert page.evaluate("() => window.FINDALINE_VIEW.view.sort") == "clr"
            assert page.errors == []
        finally:
            browser.close()
    print("the head's top frame by frame:", start, tops)
    assert all(t is not None and abs(t - start) <= 1 for t in tops), (start, tops)


def test_notice_record_ends_with_the_view(site):
    """The code review's round 6: the view left while the phone is sideways (the notice up: its focus record kept),
    the phone turned upright on the page it went to, and a run opened again: the new view does not take the focus by
    itself (it focused its map, the old record's fallback)."""
    from playwright.sync_api import sync_playwright
    side = {"viewport": {"width": 844, "height": 390}, "device_scale_factor": 3, "is_mobile": True, "has_touch": True}
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _open(browser, site + f"#run={BIG}", {**side, "viewport": {"width": 390, "height": 844}}, script=HELP)
            page.wait_for_function("() => F.snap() === 'peek' && F.rest()", timeout=WAIT)
            page.focus(".u-sheet-handle")
            page.set_viewport_size({"width": 844, "height": 390})
            page.wait_for_selector(".v-upright p", timeout=WAIT)
            page.evaluate("() => { location.hash = ''; }")
            page.wait_for_function("() => !document.querySelector('.v-result')", timeout=WAIT)
            page.set_viewport_size({"width": 390, "height": 844})
            page.evaluate("() => T.frames()")
            page.evaluate(f"() => {{ location.hash = '#run={BIG}'; }}")
            page.wait_for_function("() => !!document.querySelector('.v-result') && !!window.FINDALINE_VIEW", timeout=WAIT)
            page.wait_for_function("() => F.snap() === 'peek' && F.rest()", timeout=WAIT)
            page.evaluate("() => T.frames().then(() => T.frames()).then(() => T.frames())")
            focus = page.evaluate(FOCUS_NOW)
            assert page.errors == []
        finally:
            browser.close()
    print("the focus in a view opened again:", focus)
    assert "leaflet-container" not in focus, focus


@pytest.fixture
def credits_site(tmp_path, view_clip):
    """The clip's run with a source's data credits (test_shell_c's add_credits), served by the app; the page's address."""
    from test_shell_c import add_credits, copy_clip, stub_page
    from test_web import _server
    folder = tmp_path / "data"
    copy_clip(view_clip, folder, BIG, "Clip")
    add_credits(folder, BIG)
    page_path = stub_page(folder, "creditstest")
    with _server(folder) as port:
        yield f"http://127.0.0.1:{port}/{page_path}?ui=c"


# The run's "Data credits" button: its state, its box, the credits shown, and the scale's bottom against the credits'
CREDITS = """() => { const b = document.querySelector('.v-map .u-credits-toggle'), r = b.getBoundingClientRect(), s = getComputedStyle(b);
  const attr = document.querySelector('.v-map .leaflet-control-attribution').getBoundingClientRect(), scale = document.querySelector('.v-map .leaflet-control-scale');
  const sc = scale && scale.getBoundingClientRect();
  return {expanded: b.getAttribute('aria-expanded'), open: !!document.querySelector('.v-map .u-credits.u-open'), box: [r.left, r.top, r.right, r.bottom],
          fill: s.backgroundColor, attrHeight: attr.height, inside: r.bottom <= attr.bottom + 0.5 && r.top >= attr.top - 0.5, markFirst: b.querySelector('.u-credits-mark').getBoundingClientRect().left < r.left + 12, scaleAbove: !sc || !sc.height || sc.bottom <= attr.top + 1 || sc.right <= attr.left || sc.left >= attr.right}; }"""


@pytest.mark.parametrize("device", ["desktop", "390", "412"])
def test_data_credits_fold_back(credits_site, device):
    """Gate 2's second check ("after expanding data notice on 2d map it can not be collapsed back. Make it similiar to
    3d map."): the run's "Data credits" (a phone; a desktop with the card open) is a pill like the 3D view's (a filled
    button, its arrow before the words, on a touch screen a 44 px target around it; in the columns within the credits'
    line, inside the map): a press opens the credits, a press folds them back, a press
    opens them again, aria-expanded following; a finger's tap 8 px above the pill (within its target) counts; the scale
    stays above the credits each time; then Enter folds them, the focus kept on the button, its ring inside it."""
    from playwright.sync_api import sync_playwright
    context = {"desktop": DESKTOP, "390": SMALL_PHONE, "412": PIXEL}[device]
    steps, above = [], []
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _open(browser, credits_site + f"#run={BIG}", context, script=HELP)
            if device == "desktop":
                _state(page, "view.select(view.order[0]);")
                page.wait_for_selector(".c-col-map.c-card-on", timeout=WAIT)
            else:
                page.wait_for_function("() => F.snap() === 'peek' && F.rest()", timeout=WAIT)
            page.wait_for_selector(".v-map .u-credits-toggle", timeout=WAIT)
            page.evaluate("() => T.frames()")
            steps.append(page.evaluate(CREDITS))
            for want in ("true", "false", "true"):
                b = steps[-1]["box"]
                x = (b[0] + b[2]) / 2
                if device == "desktop":
                    page.mouse.click(x, (b[1] + b[3]) / 2)
                else:
                    page.wait_for_function("() => performance.now() - (window.TOUCHED || -1000) > 700", timeout=WAIT)
                    # above the pill, inside its 44 px target, where no credit's link lies (a link keeps its own
                    # press there); none such: the pill's middle
                    up = page.evaluate("""(b) => { const t = document.querySelector('.v-map .u-credits-toggle');
                      for (let x = b[0] + 4; x <= b[2] - 4; x += 2) { const h = document.elementFromPoint(x, b[1] - 8); if (h && t.contains(h)) return x; }
                      return null; }""", b)
                    page.touchscreen.tap(up, b[1] - 8) if up is not None else page.touchscreen.tap(x, (b[1] + b[3]) / 2)
                    above.append(up is not None)
                    page.evaluate("() => { window.TOUCHED = performance.now(); }")
                page.wait_for_function(f"() => document.querySelector('.v-map .u-credits-toggle').getAttribute('aria-expanded') === '{want}'", timeout=WAIT)
                page.evaluate("() => T.frames().then(() => T.frames())")
                steps.append(page.evaluate(CREDITS))
            # the keyboard: Enter on the button (focused after its press) folds them, the focus stays on the new
            # button, its ring inside it (folded it stands at the map's or the sheet's edge, which cut a ring outside)
            page.keyboard.press("Enter")
            page.wait_for_function("() => document.querySelector('.v-map .u-credits-toggle').getAttribute('aria-expanded') === 'false'", timeout=WAIT)
            keys = page.evaluate("() => { const b = document.querySelector('.v-map .u-credits-toggle'); return {focused: document.activeElement === b, "
                                 "ring: b.matches(':focus-visible') ? getComputedStyle(b).boxShadow : null}; }")
            assert page.errors == []
        finally:
            browser.close()
    assert keys["focused"] and keys["ring"] and "inset" in keys["ring"], keys
    print("the data credits:", device, "taps above the pill:", above, [(s["expanded"], s["open"], round(s["box"][3] - s["box"][1]), round(s["attrHeight"]), s["markFirst"], s["inside"], s["scaleAbove"]) for s in steps])
    assert [s["expanded"] for s in steps] == ["false", "true", "false", "true"] and [s["open"] for s in steps] == [False, True, False, True], steps
    # (a phone's pill 26 px high, R2's floor for its target the 44 px around it; the columns' pill as high as the
    # credits' line, drawn whole inside them)
    tall = 13.5 if device == "desktop" else 24
    assert all(s["fill"] not in ("rgba(0, 0, 0, 0)", "transparent") and s["box"][3] - s["box"][1] >= tall for s in steps), steps
    assert all(s["markFirst"] and s["inside"] for s in steps), steps
    assert all(s["scaleAbove"] for s in steps), steps
