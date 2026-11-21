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
from test_view_frame import HELP, OPEN_LINK, PIXEL, SELECTED_ENDS, STILL, UNDER8, _one_clear  # noqa: E402
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
    return b && {off: b.disabled, label: b.getAttribute('aria-label'), size: [Math.round(r.width), Math.round(r.height)], bottom: Math.round(r.bottom)}; };
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
    that goes off hands the focus to its twin (Enter on the keyboard). Smallest first, the steps follow the tree's new
    order."""
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
            # back by the keyboard: at the first spot "Previous spot" goes off, the focus to "Next spot"
            page.focus(".vl-dhead .vl-spot-prev")
            for k in (2, 1, 0):
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
    assert back["k"] == 0 and back["prev"]["off"] and "vl-spot-next" in back["focus"], back
    assert closed == "false" and into["open"] == "true" and into["pressed"] == "true" and into["inView"], (closed, into)
    assert end["k"] == len(tree) - 1 and end["next"]["off"] and "vl-spot-prev" in end["focus"], end
    assert asc != tree and reversed_step["k"] == 1 and reversed_step["spot"] == asc[1], reversed_step


@pytest.mark.parametrize("device", [SMALL_PHONE, PIXEL], ids=["390", "412"])
def test_spot_stepper_phone(site, device):
    """P1 on a phone: the pair in the sheet's head, beside the spot's title, 44 x 44, inside the sheet's visible part at
    its lowest stop, where a press steps to the next spot of the tree (its shown line selected)."""
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
            assert page.errors == []
        finally:
            browser.close()
    print("spot stepper, phone:", device.get("viewport"), "sheet", snap, sheet, "start", {k: start[k] for k in ("prev", "next")},
          "stepped", {k: stepped[k] for k in ("spot", "k", "row", "shown", "prev")})
    assert start["prev"]["size"] == [44, 44] and start["next"]["size"] == [44, 44], start
    assert start["prev"]["off"] and not start["next"]["off"], start
    assert start["next"]["bottom"] <= sheet[1], (start, sheet)
    assert stepped["k"] == 1 and stepped["row"] == stepped["shown"] and not stepped["prev"]["off"], stepped
