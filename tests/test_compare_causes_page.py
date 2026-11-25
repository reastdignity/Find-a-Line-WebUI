"""Compare in the result view (line volume's round 7, extra A7: docs/known-bugs.md's two Compare entries). A run Compare
cannot show says why after its row's words: "too large for this browser" and "made by a newer Find-a-Line" with its
box off, "could not be loaded" with its box on, a press trying again; a run that loads is shown as before. The list of
other runs follows the page without a reload: a search that ended in the same tab offers its run, a run deleted on
Home is gone and a run renamed there has its new name; while the list did not change, an opening keeps the rows and
asks for no list.

Playwright's Edge over the public app on a thread (test_rename_home_page's `rename_site`: the user "a" with RUN_A and
RUN_B, both copies of the view's clip run, so each is "here" for the other), offline. Run from PowerShell
(.claude/rules/browser-tests.md)."""

import json
import os
import re
import sys
from urllib.parse import urlparse

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

pytest.importorskip("httpx2")

from test_public import RUN_A, RUN_B, account_settings  # noqa: E402,F401
from test_rename_home_page import NAME_B, WORDS, Browser, card, open_menu, open_rename, rename_site, the_held  # noqa: E402,F401
from test_shell_c import copy_clip  # noqa: E402
from test_shell_c_view_map import WAIT, view_clip  # noqa: E402,F401
from test_web import EDGE, _playwright  # noqa: E402

pytestmark = pytest.mark.skipif(not os.path.exists(EDGE) or not _playwright(),
                                reason="needs Microsoft Edge and Playwright (group ui)")
WAIT_MS = int(os.environ.get("FINDALINE_COMPARE_TEST_WAIT_MS", WAIT))  # a shorter deadline for a run on the old page only
RUN_TOO = "2026-10-02_100000_Too_00000000000000d1"    # its lines.arrow's body not held by the browser (TOO_LARGE)
RUN_NEW = "2026-10-02_100000_New_00000000000000d2"    # a store of a newer format (newer)
RUN_FAIL = "2026-10-02_100000_Fail_00000000000000d3"  # its lines.arrow answered 500 (a route)
RUN_C = "2026-10-02_100000_C_00000000000000cc"        # the run of a search that ends while the page is open
NAME_TOO, NAME_NEW, NAME_FAIL, NAME_C = "Too large run", "Newer run", "Failing run", "Third run"
# The causes as the catalogue words them (ui.actions.other_*), pinned
CAUSES = {"too_large": "too large for this browser", "newer": "made by a newer Find-a-Line", "failed": "could not be loaded"}
LOADING, NONE = WORDS["ui.actions.loading"], WORDS["ui.actions.runs_none"]
COMPARE = ".c-result-top .r-actions button:has-text('Compare')"
BOX = '.r-pop[aria-label="%s"]' % WORDS["ui.actions.compare_label"]

# An XMLHttpRequest of one run's lines.arrow whose body the browser could not hold (a null ArrayBuffer although its
# bytes came: result/load.ts TooLarge), as test_shell_c's TOO_LARGE_STUBS for that run only
TOO_LARGE = """
{
  const tooLarge = "/runs/%s/lines.arrow";
  const realOpen = XMLHttpRequest.prototype.open;
  const realResponse = Object.getOwnPropertyDescriptor(XMLHttpRequest.prototype, "response");
  XMLHttpRequest.prototype.open = function (method, url) {
    this.tooLarge = new URL(String(url), location.href).pathname === tooLarge;
    return realOpen.apply(this, arguments);
  };
  Object.defineProperty(XMLHttpRequest.prototype, "response",
                        {configurable: true, get() { return this.tooLarge ? null : realResponse.get.call(this); }});
}
"""

# Compare's rows by the run's name: the small line (" · <day> · here[ · <cause>]"), the box ticked, the box off
ROWS = """() => Object.fromEntries([...document.querySelectorAll('.r-pop .r-other')].map((o) => { const box = o.querySelector('input');
  return [o.querySelector('.u-grow').firstChild.textContent,
          {line: o.querySelector('.u-small').textContent, checked: box.checked, off: box.disabled}]; }))"""
ROW = "(name) => [...document.querySelectorAll('.r-pop .r-other')].find((o) => o.querySelector('.u-grow').firstChild.textContent === name)"
SETTLED = "([name, loading]) => { const o = (%s)(name); return !!o && !o.querySelector('.u-small').textContent.endsWith(loading); }" % ROW
SHOWN = "() => [...window.FINDALINE_VIEW.view.model.others.keys()].sort()"
DAY = re.compile(r" · [^·]+ · here")  # a row's small line without a cause
# Where the focus is: a row's box by its run's id, the page's body, the list's box, or another control by its words
AT = ("() => { const a = document.activeElement; return a === document.body ? 'body' : a.matches('.r-pop') ? 'the list' "
      ": a.dataset.other || a.textContent.trim(); }")
# A row's box by its run's id: how it is off (aria-disabled, disabled), ticked, and drawn (the ring, the look, its size),
# with the token --surface-2 as its .ui root holds it
BOX_STATE = """(id) => { const box = document.querySelector(`.r-pop input[data-other="${id}"]`);
  const s = getComputedStyle(box), r = box.getBoundingClientRect();
  return {aria: box.getAttribute('aria-disabled'), disabled: box.disabled, checked: box.checked, ring: box.matches(':focus-visible'),
          outline: [s.outlineStyle, s.outlineWidth], appearance: [s.appearance, s.webkitAppearance], background: s.backgroundColor,
          size: [r.width, r.height], surface2: getComputedStyle(box.closest('.ui')).getPropertyValue('--surface-2').trim()}; }"""
ORDER = "() => [...document.querySelectorAll('.r-pop .r-other input')].map((i) => i.dataset.other)"  # the rows' boxes in order
ON_COMPARE = ("() => document.activeElement.matches('.c-result-top .r-actions button') "
              "&& document.activeElement.textContent.trim() === 'Compare'")


def add_run(clip, data, run: str, name: str):
    """The clip's run as another run of the user "a" (RUN_A's owner), as a search of theirs saves it."""
    from jobs import Jobs
    copy_clip(clip, data, run, name)
    jobs = Jobs(str(data))
    jobs.add_run(run, jobs.run(RUN_A)["user_id"], 1)


def open_view(browser, site: str, script: str = ""):
    """A's page of the result view of RUN_A on a desktop, drawn, with a mark that a reload would take away."""
    page = browser.page(script=script)
    page.set_default_timeout(WAIT_MS)
    page.goto(f"{site}/?ui=c#run={RUN_A}")
    page.wait_for_function("() => !!window.FINDALINE_VIEW")
    page.evaluate("() => { window.samePage = true; }")
    return page


def open_compare(page) -> dict:
    """Compare pressed in the view's header, once its box shows the rows or "No other runs with lines.": the rows."""
    page.click(COMPARE)
    page.wait_for_function("([sel, none]) => { const p = document.querySelector(sel); return !!p && (!!p.querySelector('.r-others') "
                           "|| [...p.querySelectorAll('p')].some((x) => x.textContent === none)); }", arg=[BOX, NONE])
    return page.evaluate(ROWS)


def close_compare(page):
    """Compare's button pressed again (Esc right after the opening can come before the box listens for it)."""
    page.click(COMPARE)
    page.wait_for_selector(BOX, state="detached")


def tick(page, name: str):
    page.locator(".r-pop label.r-other", has_text=name).locator("input").click()


def settled(page, *names: str):
    """The rows of `names` no longer loading."""
    for name in names:
        page.wait_for_function(SETTLED, arg=[name, LOADING])


def go_home(page):
    """Home through the view's way back (the same page)."""
    page.click(".c-result-top .c-back")
    page.wait_for_selector(card(RUN_A))


def back_to_view(page):
    """RUN_A's view again from its card on Home (the same page)."""
    page.click(f"{card(RUN_A)} a.c-card-open")
    page.wait_for_function("() => !!window.FINDALINE_VIEW && !!document.querySelector('.c-result-top .r-actions')")


def same_page(page) -> bool:
    return page.evaluate("() => window.samePage === true")


def listed_first(data, *runs: str):
    """run.json's time of `runs` moved later, the first the latest: the list of runs (newest first) has them in this
    order before RUN_B (the copies share the clip's time, and the server's order of a tie may differ per process)."""
    from datetime import datetime, timedelta
    for days, run in enumerate(reversed(runs), 1):
        path = data / "runs" / run / "run.json"
        meta = json.loads(path.read_text(encoding="utf-8"))
        meta["created"] = (datetime.fromisoformat(meta["created"]) + timedelta(days=days)).isoformat()
        path.write_text(json.dumps(meta), encoding="utf-8")


def answered(page):
    """A request of the page sent and answered: one the page sent before it (a press's lines.arrow) has been seen."""
    page.evaluate("() => fetch('/api/usage').then((r) => r.status)")


def press_on(page, selector: str):
    """A mouse press in the middle of the element (page.mouse: a locator's click would wait for an off box's label to be
    enabled, Playwright's own check)."""
    box = page.locator(selector).bounding_box()
    page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)


def rgb(token: str) -> str:
    """A token's colour as written ("#e5ebeb") in the form getComputedStyle gives a colour ("rgb(229, 235, 235)")."""
    assert re.fullmatch(r"#[0-9a-fA-F]{6}", token), token
    return "rgb(%d, %d, %d)" % tuple(int(token[i:i + 2], 16) for i in (1, 3, 5))


def test_compare_says_why_a_run_cannot_be_shown(rename_site, view_clip):
    """Four other runs, each "here": a body too large for the browser, a store of a newer format, a store the server
    answers with 500, and RUN_B. Ticked, the first three end their row's small line with " · too large for this
    browser", " · made by a newer Find-a-Line" and " · could not be loaded", unticked; the first two boxes are off, the
    third on; RUN_B is shown (its box ticked, no cause, among the view's other runs), the others not; the box says
    "no lines" nowhere. A press on the third tries again: while its request waits it is ticked and "loading…"; the
    server failing again, the cause is back, its box on and unticked; the failure gone, a press shows it. The
    catalogue words the three causes and has no ui.actions.no_lines."""
    site, data = rename_site
    for run, name in ((RUN_TOO, NAME_TOO), (RUN_NEW, NAME_NEW), (RUN_FAIL, NAME_FAIL)):
        add_run(view_clip, data, run, name)
    path = data / "runs" / RUN_NEW / "run.json"  # its store's format one higher (runs.js lists run.json's block)
    meta = json.loads(path.read_text(encoding="utf-8"))
    meta["store"]["format"] += 1
    path.write_text(json.dumps(meta), encoding="utf-8")
    held, hold = [], []

    def fail(route):  # RUN_FAIL's lines.arrow: a server error, held while `hold` says so
        if hold:
            held.append(route)
        else:
            route.fulfill(status=500, body="made-up failure")
    with Browser(site) as browser:
        page = open_view(browser, site, TOO_LARGE % RUN_TOO)
        page.route(f"**/runs/{RUN_FAIL}/lines.arrow", fail)
        first = open_compare(page)
        for name in (NAME_B, NAME_TOO, NAME_NEW, NAME_FAIL):
            tick(page, name)
        settled(page, NAME_B, NAME_TOO, NAME_NEW, NAME_FAIL)
        failed, shown = page.evaluate(ROWS), page.evaluate(SHOWN)
        words = page.evaluate("(sel) => document.querySelector(sel).textContent", BOX)
        # again, the server failing again: loading while the request waits, then the cause back
        hold.append(True)
        tick(page, NAME_FAIL)
        request = the_held(page, held)
        waiting = page.evaluate(ROWS)[NAME_FAIL]
        hold.clear()
        request.fulfill(status=500, body="made-up failure")
        settled(page, NAME_FAIL)
        again = page.evaluate(ROWS)[NAME_FAIL]
        # the failure gone: a press shows the run
        page.unroute(f"**/runs/{RUN_FAIL}/lines.arrow")
        tick(page, NAME_FAIL)
        page.wait_for_function("(id) => window.FINDALINE_VIEW.view.model.others.has(id)", arg=RUN_FAIL)
        settled(page, NAME_FAIL)
        fixed, shown_after = page.evaluate(ROWS)[NAME_FAIL], page.evaluate(SHOWN)
    assert sorted(first) == sorted([NAME_B, NAME_TOO, NAME_NEW, NAME_FAIL]), first
    for name, row in first.items():
        assert DAY.fullmatch(row["line"]) and not row["checked"] and not row["off"], (name, row)
    day = {name: row["line"] for name, row in first.items()}
    assert failed[NAME_TOO] == {"line": day[NAME_TOO] + " · too large for this browser", "checked": False, "off": True}, failed
    assert failed[NAME_NEW] == {"line": day[NAME_NEW] + " · made by a newer Find-a-Line", "checked": False, "off": True}, failed
    assert failed[NAME_FAIL] == {"line": day[NAME_FAIL] + " · could not be loaded", "checked": False, "off": False}, failed
    assert failed[NAME_B] == {"line": day[NAME_B], "checked": True, "off": False}, failed
    assert shown == [RUN_B], shown
    assert "no lines" not in words, words
    assert waiting == {"line": day[NAME_FAIL] + " · " + LOADING, "checked": True, "off": False}, waiting
    assert LOADING == "loading…"
    assert again == failed[NAME_FAIL], again
    assert fixed == {"line": day[NAME_FAIL], "checked": True, "off": False}, fixed
    assert shown_after == sorted([RUN_B, RUN_FAIL]), shown_after
    assert {key: WORDS.get(f"ui.actions.other_{key}") for key in CAUSES} == CAUSES
    assert "ui.actions.no_lines" not in WORDS


def test_a_search_ended_in_the_page_is_offered(rename_site, view_clip):
    """A's search computing while RUN_A's view is open: Compare offers RUN_B only. The search saves its run and ends
    (the job "done" through the server's event stream, as the worker sets it): the page lists the runs again, and
    Compare opened again in the same view, without a reload, offers the new run too, "here" and with no cause."""
    from jobs import Jobs
    site, data = rename_site
    jobs = Jobs(str(data))
    job = jobs.add({"lat": 50.1559508, "lon": 19.7562722}, "A search", user_id=jobs.run(RUN_A)["user_id"])
    jobs.set(job, "computing")
    with Browser(site) as browser:
        page = open_view(browser, site)
        before = open_compare(page)
        close_compare(page)
        add_run(view_clip, data, RUN_C, NAME_C)  # the search's run saved, then its job done
        with page.expect_request(lambda r: r.method == "GET" and urlparse(r.url).path == "/api/runs"):
            jobs.set(job, "done", run_id=RUN_C, error=None)  # AppC's effect: forgetRunList, then the runs listed again
        page.click(COMPARE)
        page.wait_for_function(f"(name) => !!({ROW})(name)", arg=NAME_C)
        after = page.evaluate(ROWS)
        kept = same_page(page)
    assert list(before) == [NAME_B], before
    assert sorted(after) == sorted([NAME_B, NAME_C]), after
    assert DAY.fullmatch(after[NAME_C]["line"]) and not after[NAME_C]["checked"] and not after[NAME_C]["off"], after
    assert kept, "the page was loaded again"


def test_a_run_deleted_on_home_is_gone(rename_site, view_clip):
    """RUN_A's view with Compare offering RUN_B and a third run; Home in the same page, RUN_B deleted through its
    card's "Delete…"; RUN_A's view again from its card, without a reload: Compare offers the third run only (a list
    read again, not one that failed: that one would offer none)."""
    site, data = rename_site
    add_run(view_clip, data, RUN_C, NAME_C)
    with Browser(site) as browser:
        page = open_view(browser, site)
        before = open_compare(page)
        close_compare(page)
        go_home(page)
        open_menu(page, RUN_B)
        page.click(f"{card(RUN_B)} [role=menuitem]:has-text('Delete…')")
        page.click(f"{card(RUN_B)} .c-confirm-delete")
        page.wait_for_selector(card(RUN_B), state="detached")
        back_to_view(page)
        after = open_compare(page)
        kept = same_page(page)
    assert sorted(before) == sorted([NAME_B, NAME_C]), before
    assert list(after) == [NAME_C], after
    assert DAY.fullmatch(after[NAME_C]["line"]) and not after[NAME_C]["checked"], after
    assert kept, "the page was loaded again"


def test_a_run_renamed_on_home_is_renamed(rename_site):
    """RUN_A's view with Compare offering RUN_B as "Second run"; Home in the same page, RUN_B renamed through its
    card's "Rename…"; RUN_A's view again from its card, without a reload: Compare's row of RUN_B has the new name, and
    no row the old one."""
    site, _ = rename_site
    with Browser(site) as browser:
        page = open_view(browser, site)
        before = open_compare(page)
        close_compare(page)
        go_home(page)
        field = open_rename(page, RUN_B)
        field.fill("The north face")
        with page.expect_response(lambda r: r.request.method == "POST" and r.url.endswith(f"/api/runs/{RUN_B}")):
            page.keyboard.press("Enter")
        page.wait_for_selector(f"{card(RUN_B)} .c-card-panel", state="detached")
        back_to_view(page)
        after = open_compare(page)
        kept = same_page(page)
    assert list(before) == [NAME_B], before
    assert list(after) == ["The north face"], after
    assert kept, "the page was loaded again"


def test_compare_keeps_its_rows_while_the_list_is_the_same(rename_site, view_clip):
    """Nothing changes in the page: Compare opened, RUN_B ticked (shown) and a run too large for the browser ticked
    (its cause, its box off: announced off while the press's focus is on it, aria-disabled, not disabled), closed and
    opened again: the same rows, RUN_B ticked and the other run with its cause and its box off (now disabled); the
    second opening asks for no list of runs (/runs/runs.js), the first for one at most (the view's own load may have
    read it before)."""
    site, data = rename_site
    add_run(view_clip, data, RUN_TOO, NAME_TOO)
    lists = []
    with Browser(site) as browser:
        page = open_view(browser, site, TOO_LARGE % RUN_TOO)
        page.on("request", lambda r: lists.append(r.url) if urlparse(r.url).path == "/runs/runs.js" else None)
        open_compare(page)
        opened = len(lists)
        for name in (NAME_B, NAME_TOO):
            tick(page, name)
        page.wait_for_function("(id) => window.FINDALINE_VIEW.view.model.others.has(id)", arg=RUN_B)
        settled(page, NAME_B, NAME_TOO)
        ticked, held = page.evaluate(ROWS), page.evaluate(BOX_STATE, RUN_TOO)["aria"]
        close_compare(page)
        second = open_compare(page)
        held_after = page.evaluate(BOX_STATE, RUN_TOO)["aria"]
        # a request sent after the opening and answered: a list asked for by the opening would have come before it
        page.evaluate("() => fetch('/api/usage').then((r) => r.status)")
        again, shown, kept = len(lists), page.evaluate(SHOWN), same_page(page)
    assert opened <= 1 and again == opened, lists
    # (since the fix round: the box pressed off with the mouse keeps the focus, announced off by aria-disabled and not
    # disabled, until the focus leaves it, then it is a disabled box: the design review's finding 2)
    assert ticked[NAME_TOO] == {**second[NAME_TOO], "off": False} and (held, held_after) == ("true", None), \
        (ticked, second, held, held_after)
    assert second.keys() == ticked.keys() and second[NAME_B] == ticked[NAME_B], (second, ticked)
    assert second[NAME_B]["checked"] and not second[NAME_B]["off"] and DAY.fullmatch(second[NAME_B]["line"]), second
    assert second[NAME_TOO]["line"].endswith(" · too large for this browser") and second[NAME_TOO]["off"], second
    assert not second[NAME_TOO]["checked"], second
    assert shown == [RUN_B], shown
    assert kept, "the page was loaded again"


def test_the_keyboard_keeps_its_place_when_a_box_goes_off(rename_site, view_clip):
    """Three other runs listed in this order: a third run, a run too large for the browser, RUN_B. The too large one
    ticked with the keyboard (Tab from the third run's box to its own, Space): once its cause is written the focus is
    still on its box, which is announced off (aria-disabled, unchecked) and not disabled, with the kit's ring (it
    matches :focus-visible, a 2 px solid outline) and drawn off (no native look, the fill of --surface-2, 20 by 20 px).
    A press does nothing: Space again leaves it unchecked, asks for no lines.arrow of that run and keeps the cause. The
    next Tab reaches the next row's box (RUN_B's), not the list's first control; the box left is then a disabled box as
    the others (no aria-disabled), and Shift+Tab passes it, to the third run's box. A mouse press on the row's words
    does nothing either. Esc closes Compare with the focus back on its button."""
    site, data = rename_site
    add_run(view_clip, data, RUN_C, NAME_C)
    add_run(view_clip, data, RUN_TOO, NAME_TOO)
    listed_first(data, RUN_C, RUN_TOO)
    arrows = []  # the requests of the too large run's lines.arrow
    with Browser(site) as browser:
        page = open_view(browser, site, TOO_LARGE % RUN_TOO)
        page.on("request", lambda r: arrows.append(r.url) if urlparse(r.url).path == f"/runs/{RUN_TOO}/lines.arrow" else None)
        open_compare(page)
        order = page.evaluate(ORDER)
        page.locator(f".r-pop input[data-other='{RUN_C}']").focus()
        page.keyboard.press("Tab")
        reached = page.evaluate(AT)
        page.keyboard.press("Space")
        settled(page, NAME_TOO)
        at_off, off, row = page.evaluate(AT), page.evaluate(BOX_STATE, RUN_TOO), page.evaluate(ROWS)[NAME_TOO]
        page.keyboard.press("Space")
        answered(page)
        at_pressed, pressed, sent = page.evaluate(AT), page.evaluate(BOX_STATE, RUN_TOO), len(arrows)
        row_pressed = page.evaluate(ROWS)[NAME_TOO]
        page.keyboard.press("Tab")
        tabbed, left = page.evaluate(AT), page.evaluate(BOX_STATE, RUN_TOO)
        page.keyboard.press("Shift+Tab")
        back = page.evaluate(AT)
        press_on(page, f".r-pop label.r-other:has(input[data-other='{RUN_TOO}']) .u-grow")
        answered(page)
        clicked, row_clicked, sent_after = page.evaluate(BOX_STATE, RUN_TOO), page.evaluate(ROWS)[NAME_TOO], len(arrows)
        page.keyboard.press("Escape")
        page.wait_for_selector(BOX, state="detached")
        page.wait_for_function(ON_COMPARE)
    assert order == [RUN_C, RUN_TOO, RUN_B], order
    assert reached == RUN_TOO, reached
    assert at_off == RUN_TOO, at_off  # still on its box: not the body, not the list's box
    assert (off["aria"], off["disabled"], off["checked"]) == ("true", False, False), off
    assert row["line"].endswith(" · too large for this browser") and WORDS["ui.actions.other_too_large"] == CAUSES["too_large"], row
    assert off["ring"] and off["outline"] == ["solid", "2px"], off  # the kit's ring (ui.css .u-check:focus-visible)
    assert "none" in off["appearance"] and off["background"] == rgb(off["surface2"]) and off["size"] == [20, 20], off
    assert at_pressed == RUN_TOO, at_pressed
    assert (pressed["aria"], pressed["disabled"], pressed["checked"]) == ("true", False, False), pressed
    assert row_pressed == row and sent == 1, (row_pressed, arrows)
    assert tabbed == RUN_B, tabbed  # the next row's box, not the list's first control (the third run's)
    assert (left["aria"], left["disabled"], left["checked"]) == (None, True, False), left
    assert back == RUN_C, back
    assert (clicked["aria"], clicked["disabled"], clicked["checked"]) == (None, True, False), clicked
    assert row_clicked["line"] == row["line"] and sent_after == 1, (row_clicked, arrows)


def test_a_box_pressed_off_with_the_mouse_keeps_the_focus(rename_site, view_clip):
    """A run too large for the browser ticked with the mouse (the press focuses its box): once its cause is written the
    focus is still on its box, not on the page's body nor the list's box, and the box is announced off (aria-disabled,
    unchecked), not disabled. A mouse press on the row's words then does nothing: unchecked, the cause kept, no
    lines.arrow of that run asked for again. A press elsewhere in Compare's box (its heading) takes the focus away and
    leaves Compare open: the row's box is then a disabled box as the others, its cause kept."""
    site, data = rename_site
    add_run(view_clip, data, RUN_TOO, NAME_TOO)
    arrows = []  # the requests of the too large run's lines.arrow
    with Browser(site) as browser:
        page = open_view(browser, site, TOO_LARGE % RUN_TOO)
        page.on("request", lambda r: arrows.append(r.url) if urlparse(r.url).path == f"/runs/{RUN_TOO}/lines.arrow" else None)
        open_compare(page)
        tick(page, NAME_TOO)
        settled(page, NAME_TOO)
        at_off, off, row = page.evaluate(AT), page.evaluate(BOX_STATE, RUN_TOO), page.evaluate(ROWS)[NAME_TOO]
        press_on(page, f".r-pop label.r-other:has(input[data-other='{RUN_TOO}']) .u-grow")
        answered(page)
        words, row_words, sent = page.evaluate(BOX_STATE, RUN_TOO), page.evaluate(ROWS)[NAME_TOO], len(arrows)
        page.click(f"{BOX} .r-others > b")
        at_left, left, row_left = page.evaluate(AT), page.evaluate(BOX_STATE, RUN_TOO), page.evaluate(ROWS)[NAME_TOO]
        still = page.is_visible(BOX)
    assert at_off == RUN_TOO, at_off
    assert (off["aria"], off["disabled"], off["checked"]) == ("true", False, False), off
    assert row["line"].endswith(" · too large for this browser"), row
    assert not words["checked"] and row_words["line"] == row["line"] and sent == 1, (words, row_words, arrows)
    assert at_left != RUN_TOO and at_left != "body" and still, (at_left, still)
    assert (left["aria"], left["disabled"], left["checked"]) == (None, True, False), left
    assert row_left["line"] == row["line"], (row_left, row)
