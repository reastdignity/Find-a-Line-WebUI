"""The rename's fix round on the page (line volume's round 7; the code review's F1 to F4, the scope review's S-PG3 and
the three changes without a test of its section 2): an old list of runs that arrives after a rename or a delete is
not written back (the view and window.FINDALINE_RUNS have the new list); a 200 that is no rename renames nothing
and shows a line; a failure that came with no words of its own shows FAILED_TEXT's words ("The run was not renamed.
Try again in a moment.", on a card and in the view); only a refused name (the server's 400) marks the field invalid;
the name shown is the server's answer, not the page's own form of what was
typed; a rename while the run still loads reaches its view; a rename that ends after its form is gone (another
panel opened, Home left) names the card; the view's Share and Rename ask for the user's runs once.

Playwright's Edge over the public app on a thread (uvicorn) with the real route POST /api/runs/<id>, offline; the
fixture and helpers are tests/test_rename_home_page.py's and tests/test_rename_view_page.py's. Run from PowerShell
(.claude/rules/browser-tests.md)."""

import json
import os
import sys
from urllib.parse import urlparse

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

pytest.importorskip("httpx2")

from test_compare_causes_page import NAME_C, RUN_C, add_run, open_compare  # noqa: E402
from test_public import RUN_A, RUN_B, account_settings  # noqa: E402,F401
from test_rename_home_page import (FORM, NAME, NAME_A, NAME_B, REFUSED, REPO, WORDS, Browser, card,  # noqa: E402,F401
                                   open_home, open_menu, open_rename, rename_site, the_held)
from test_rename_view_page import BOX, BUTTON, TEXT, TITLE, open_box, renamed, settled, view_of  # noqa: E402
from test_shell_c_view_map import DESKTOP, view_clip  # noqa: E402,F401
from test_shell_c_view_map import WAIT as PAGE_WAIT  # noqa: E402
from test_web import EDGE, _playwright  # noqa: E402

pytestmark = pytest.mark.skipif(not os.path.exists(EDGE) or not _playwright(),
                                reason="needs Microsoft Edge and Playwright (group ui)")
# ms: the deadline of every wait for the page (lowered through the variable only to see the tests fail sooner on a
# checkout without the fixes)
WAIT = int(os.environ.get("RENAME_FIXES_WAIT_MS", PAGE_WAIT))
# The line of a failure that came with no words of its own: the user's text T22 (2026-11-25, answer 1), the words of
# the key FAILED_TEXT names (ui.rename.failed: test_rename_fixes_units.py), pinned here as the page shows them
FAILED_WORDS = "The run was not renamed. Try again in a moment."
IN_USE = WORDS["ui.rename.in_use"]
NEW = "North face"  # a new name with nothing of the old ones in it
TYPED = "Name typed here"  # what a test types where no rename is stored
RUNS_JS = "**/runs/runs.js"
SHARE_PANEL = '.c-card-panel[aria-label="%s"]' % WORDS["ui.card.share_title"]
# The card's form at rest again after a send (the field writable), with its line drawn; or the card's panel gone
ENDED = """(sel) => { const p = document.querySelector(sel + ' .c-card-panel'); if (!p) return true;
  const i = p.querySelector('.c-rename input'), l = p.querySelector('.c-rename [role=alert]'); return !!i && !i.readOnly && !!l; }"""
# The same for the view's box
BOX_ENDED = """(sel) => { const p = document.querySelector(sel); if (!p) return true;
  const i = p.querySelector('.c-rename input'), l = p.querySelector('.c-rename [role=alert]'); return !!i && !i.readOnly && !!l; }"""
READ_ONLY = "(sel) => { const i = document.querySelector(sel + ' .c-rename input'); return !!i && i.readOnly; }"
PANEL = "(sel) => document.querySelectorAll(sel + ' .c-card-panel').length"
COUNT = "(sel) => document.querySelectorAll(sel).length"


def page_of(browser, device: dict = DESKTOP, who: str | None = "a", script: str = ""):
    """The model's page (signed in as `who`, the view's flag set) with this file's deadline."""
    page = browser.page(device, who, script)
    page.set_default_timeout(WAIT)
    return page


def fresh(page):
    """The page away from Home of the sign-in (about:blank): a route added now sees no request of that page."""
    page.goto("about:blank")


def hold_first(page, pattern: str, read: bool = False) -> list:
    """The first request of `pattern` held (with `read`, its answer read from the server at once: (route, answer));
    every later one let through. The list the held request is put into (the_held takes it)."""
    held, seen = [], []

    def handler(route):
        if seen:
            return route.continue_()
        seen.append(route)
        held.append((route, route.fetch()) if read else route)
    page.route(pattern, handler)
    return held


def stored_name(data, run: str) -> str:
    with open(data / "runs" / run / "run.json", encoding="utf-8") as f:
        return json.load(f)["name"]


def rename_answer(run: str = RUN_A):
    """The answer of the run's rename (POST /api/runs/<id>)."""
    return lambda response: renamed(response, run)


# C-F1: an old list of runs is not written back

def test_an_old_list_is_not_written_back_after_a_rename(rename_site):
    """Home's request for the list of runs (/runs/runs.js, its mini maps') unanswered while RUN_B is renamed on its
    card; then that old answer arrives (the list as it was before the rename). RUN_B opened from its card in the same
    page: the view's head shows the new name, and window.FINDALINE_RUNS, once the view is drawn, holds the new name
    and not the old one."""
    site, _ = rename_site
    with Browser(site) as browser:
        page = page_of(browser)
        fresh(page)
        held = hold_first(page, RUNS_JS, read=True)
        open_home(page, site, RUN_B)
        route, old = the_held(page, held)  # Home's mini maps asked for the list: held, its answer read now
        old_list = old.text()
        field = open_rename(page, RUN_B)
        field.fill(NEW)
        with page.expect_response(rename_answer(RUN_B)):
            page.keyboard.press("Enter")
        page.wait_for_selector(f"{card(RUN_B)} .c-card-panel", state="detached")
        card_name = page.evaluate(NAME, card(RUN_B))
        route.fulfill(response=old)  # the old list arrives after the rename
        page.wait_for_function("() => Array.isArray(window.FINDALINE_RUNS)")  # its script ran (and a newer one, if asked)
        page.click(f"{card(RUN_B)} a.c-card-open")
        view_of(page, RUN_B)
        head = page.evaluate(TEXT, TITLE)
        listed = page.evaluate("() => window.FINDALINE_RUNS.map((r) => r.name)")
    assert NAME_B in old_list and NEW not in old_list, old_list  # (else the old answer would not be an old one)
    assert card_name == NEW, card_name
    assert head == NEW, f"the view shows {head!r}; window.FINDALINE_RUNS {listed}"
    assert NEW in listed and NAME_B not in listed, listed


def test_an_old_list_does_not_bring_back_a_deleted_run(rename_site, view_clip):
    """Three runs of A (RUN_A, RUN_B and a third one, all "here" for each other). Home's request for the list of runs
    unanswered while RUN_B is deleted on its card; then that old answer (with RUN_B) arrives. RUN_A's view opened
    from its card in the same page: window.FINDALINE_RUNS, once the view is drawn, lists RUN_A and the third run, not
    RUN_B; Compare offers the third run only."""
    site, data = rename_site
    add_run(view_clip, data, RUN_C, NAME_C)
    with Browser(site) as browser:
        page = page_of(browser)
        fresh(page)
        held = hold_first(page, RUNS_JS, read=True)
        open_home(page, site, RUN_B)
        route, old = the_held(page, held)
        old_list = old.text()
        open_menu(page, RUN_B)
        page.click(f"{card(RUN_B)} [role=menuitem]:has-text('Delete…')")
        with page.expect_response(lambda r: r.request.method == "DELETE" and r.url.endswith(f"/api/runs/{RUN_B}")):
            page.click(f"{card(RUN_B)} .c-confirm-delete")
        page.wait_for_selector(card(RUN_B), state="detached")
        route.fulfill(response=old)  # the old list arrives after the delete
        page.wait_for_function("() => Array.isArray(window.FINDALINE_RUNS)")
        page.click(f"{card(RUN_A)} a.c-card-open")
        view_of(page, RUN_A)
        listed = page.evaluate("() => window.FINDALINE_RUNS.map((r) => r.id)")
        rows = open_compare(page)
    assert RUN_B in old_list, old_list  # (the old answer lists the deleted run)
    assert list(rows) == [NAME_C], rows
    assert sorted(listed) == sorted([RUN_A, RUN_C]), listed


# C-F2: a 200 that is no rename

NO_RENAME = {"html": ("text/html", "<html><body>A proxy's page</body></html>"),
             "ok-only": ("application/json", json.dumps({"ok": True})),
             "empty-name": ("application/json", json.dumps({"ok": True, "name": ""})),
             "number": ("application/json", json.dumps({"ok": True, "name": 5}))}


def answer_with(kind: str, body: str):
    """A route's handler: the rename's POST answered 200 with `body`; every other request let through."""
    return lambda route: route.fulfill(status=200, content_type=kind, body=body) if route.request.method == "POST" \
        else route.continue_()


@pytest.mark.parametrize("answer", list(NO_RENAME))
def test_a_200_that_is_no_rename_on_a_card(rename_site, answer):
    """The rename's POST answered 200 with an HTML page (a proxy's), with {"ok": true} alone, with an empty name or
    with a name that is no text: the card keeps its name, the panel stays open with the typed name, Save is on again,
    a line (role=alert) shows FAILED_TEXT's words, the field is not marked invalid, and run.json keeps its name."""
    site, data = rename_site
    with Browser(site) as browser:
        page = page_of(browser)
        open_home(page, site)
        field = open_rename(page, RUN_A)
        page.route(f"**/api/runs/{RUN_A}", answer_with(*NO_RENAME[answer]))
        field.fill(TYPED)
        page.keyboard.press("Enter")
        page.wait_for_function(ENDED, arg=card(RUN_A))
        panel = page.evaluate(PANEL, card(RUN_A))
        form = page.evaluate(FORM, card(RUN_A)) if panel else None
        name = page.evaluate(NAME, card(RUN_A))
    assert name == NAME_A, f"{answer}: the card shows {name!r}; panel {panel}, form {form}"
    assert panel == 1 and form["value"] == TYPED and form["off"] == [False, False], (answer, form)
    assert form["line"] == FAILED_WORDS and form["invalid"] is None and form["described"], (answer, form)
    assert stored_name(data, RUN_A) == NAME_A


def test_a_200_that_is_no_rename_in_the_view(rename_site):
    """The view's box: the rename's POST answered 200 with an HTML page (a proxy's): the title keeps the run's name,
    the box stays open with the typed name and FAILED_TEXT's words in its line, Save on again, the field not marked
    invalid."""
    site, data = rename_site
    with Browser(site) as browser:
        page = page_of(browser)
        page.goto(f"{site}/?ui=c#run={RUN_A}")
        view_of(page, RUN_A)
        field = open_box(page)
        page.route(f"**/api/runs/{RUN_A}", answer_with(*NO_RENAME["html"]))
        field.fill(TYPED)
        page.keyboard.press("Enter")
        page.wait_for_function(BOX_ENDED, arg=BOX)
        box = page.evaluate(COUNT, BOX)
        form = page.evaluate(FORM, ".c-run-title") if box else None
        title = page.evaluate(TEXT, TITLE)
    assert title == NAME_A, f"the title shows {title!r}; box {box}, form {form}"
    assert box == 1 and form["value"] == TYPED and form["off"] == [False, False], form
    assert form["line"] == FAILED_WORDS and form["invalid"] is None, form
    assert stored_name(data, RUN_A) == NAME_A


# C-F3: a failure with no words

# The rename's fetch answered with an error page that is no JSON and has no reason phrase (as an HTTP/2 answer of
# nginx's own 502 page has none: a Response made in the page has statusText ""); held until the test lets it go
# (window.RENAME_HELD), so the form's waiting state is seen before the answer
BAD_GATEWAY = """
window.RENAME_HELD = [];
const realFetchOfRename = window.fetch;
window.fetch = (url, init) => init && init.method === 'POST' && /\\/api\\/runs\\/[^/]+$/.test(String(url).split('?')[0])
  ? new Promise((answer) => window.RENAME_HELD.push(() => answer(new Response('<html><body>502 Bad Gateway</body></html>',
      {status: 502, headers: {'content-type': 'text/html'}}))))
  : realFetchOfRename(url, init);
"""


def test_a_failure_without_words_shows_a_line(rename_site):
    """A rename answered with a 502 page that is no JSON and has no reason phrase: the form shows a line with
    FAILED_TEXT's words, Save is on again, the typed name is kept, the focus is in the field, the field is not marked
    invalid, and the card keeps its name."""
    site, _ = rename_site
    with Browser(site) as browser:
        page = page_of(browser, script=BAD_GATEWAY)
        open_home(page, site)
        field = open_rename(page, RUN_A)
        field.fill(TYPED)
        page.keyboard.press("Enter")
        page.wait_for_function("(sel) => window.RENAME_HELD.length === 1 && (%s)(sel)" % READ_ONLY, arg=card(RUN_A))
        reason = page.evaluate("() => { window.RENAME_HELD.pop()(); return new Response('', {status: 502}).statusText; }")
        page.wait_for_function("(sel) => !document.querySelector(sel + ' .c-rename input').readOnly", arg=card(RUN_A))
        form = page.evaluate(FORM, card(RUN_A))
        name = page.evaluate(NAME, card(RUN_A))
    assert reason == "", reason  # (the page's own Response, as the fake 502 makes it, has no reason phrase)
    assert form["line"] == FAILED_WORDS, form
    assert form["off"] == [False, False] and form["value"] == TYPED and form["focus"], form
    assert form["invalid"] is None and form["described"], form
    assert name == NAME_A, name


def test_a_failure_without_words_in_the_view(rename_site):
    """The view's box: a rename answered with a 502 page that is no JSON and has no reason phrase: the box stays open
    with the typed name and FAILED_TEXT's words in its line, Save on again, the focus in the field, the field not
    marked invalid, and the title keeps the run's name."""
    site, data = rename_site
    with Browser(site) as browser:
        page = page_of(browser, script=BAD_GATEWAY)
        page.goto(f"{site}/?ui=c#run={RUN_A}")
        view_of(page, RUN_A)
        field = open_box(page)
        field.fill(TYPED)
        page.keyboard.press("Enter")
        page.wait_for_function("(sel) => window.RENAME_HELD.length === 1 && (%s)(sel)" % READ_ONLY, arg=BOX)
        page.evaluate("() => window.RENAME_HELD.pop()()")
        page.wait_for_function(BOX_ENDED, arg=BOX)
        box = page.evaluate(COUNT, BOX)
        form = page.evaluate(FORM, ".c-run-title") if box else None
        title = page.evaluate(TEXT, TITLE)
    assert title == NAME_A, f"the title shows {title!r}; box {box}, form {form}"
    assert box == 1 and form["value"] == TYPED and form["off"] == [False, False] and form["focus"], form
    assert form["line"] == FAILED_WORDS and form["invalid"] is None and form["described"], form
    assert stored_name(data, RUN_A) == NAME_A


# C-F4: aria-invalid only for a refused name

def test_only_a_refused_name_marks_the_field(rename_site):
    """A run in use (409) shows the catalogue's "The run is in use. Try again in a moment." with the field not marked
    invalid and still described by the line; a server error with words (500) shows them, the field not marked; a
    failure on the network shows a line, the field not marked; a name the server refuses (a tab: its 400) shows the
    catalogue's error.run_name and marks the field invalid."""
    site, _ = rename_site
    held = []
    with Browser(site) as browser:
        page = page_of(browser)
        open_home(page, site)
        field = open_rename(page, RUN_A)
        page.route(f"**/api/runs/{RUN_A}", lambda route: held.append(route) if route.request.method == "POST" else route.continue_())
        alert = f"{card(RUN_A)} .c-rename [role=alert]"
        seen = {}
        for name, typed, answer in (("in use", "Waiting name", lambda r: r.fulfill(
                                         status=409, content_type="application/json",
                                         body=json.dumps({"detail": "the run is in use: try again in a moment"}))),
                                    ("server", "Waiting name!", lambda r: r.fulfill(
                                         status=500, content_type="application/json", body=json.dumps({"detail": "made-up failure"}))),
                                    ("network", "Waiting name!?", lambda r: r.abort())):
            field.fill(typed)  # (the line of before goes with the typing)
            page.wait_for_selector(alert, state="detached")
            page.keyboard.press("Enter")
            page.wait_for_function(READ_ONLY, arg=card(RUN_A))
            answer(the_held(page, held))
            page.wait_for_selector(alert)
            seen[name] = page.evaluate(FORM, card(RUN_A))
        page.unroute(f"**/api/runs/{RUN_A}")
        field.fill("Tab\there")
        page.wait_for_selector(alert, state="detached")
        with page.expect_response(rename_answer()) as sent:
            page.keyboard.press("Enter")
        page.wait_for_selector(alert)
        refused = page.evaluate(FORM, card(RUN_A))
        status = sent.value.status
    in_use, server, network = seen["in use"], seen["server"], seen["network"]
    assert in_use["line"] == IN_USE == "The run is in use. Try again in a moment.", in_use
    assert in_use["invalid"] is None and in_use["described"], in_use
    assert server["line"] == "made-up failure" and server["invalid"] is None and server["described"], server
    assert network["line"] != "" and network["invalid"] is None and network["described"], network
    assert status == 400, status
    assert refused["line"] == REFUSED and refused["invalid"] == "true" and refused["described"], refused


# S-PG3: the answer's name is shown

STORED = "Stored by the server"
SPACED = "  typed   here "  # the page's own stored form of it would be "typed here"


def test_the_answers_name_is_shown_on_the_card(rename_site):
    """The rename's POST answered 200 with the name "Stored by the server" while "  typed   here " was typed (whose
    stored form on the page's side would be "typed here"): the card shows exactly "Stored by the server"."""
    site, _ = rename_site
    with Browser(site) as browser:
        page = page_of(browser)
        open_home(page, site)
        field = open_rename(page, RUN_A)
        page.route(f"**/api/runs/{RUN_A}", answer_with("application/json", json.dumps({"ok": True, "name": STORED})))
        field.fill(SPACED)
        page.keyboard.press("Enter")
        page.wait_for_selector(f"{card(RUN_A)} .c-card-panel", state="detached")
        name = page.evaluate(NAME, card(RUN_A))
    assert name == STORED, name


def test_the_answers_name_is_shown_in_the_view(rename_site):
    """The view's box: the rename's POST answered 200 with the name "Stored by the server" while "  typed   here "
    was typed: the box closes and the title shows exactly "Stored by the server"."""
    site, _ = rename_site
    with Browser(site) as browser:
        page = page_of(browser)
        page.goto(f"{site}/?ui=c#run={RUN_A}")
        view_of(page, RUN_A)
        field = open_box(page)
        page.route(f"**/api/runs/{RUN_A}", answer_with("application/json", json.dumps({"ok": True, "name": STORED})))
        field.fill(SPACED)
        page.keyboard.press("Enter")
        page.wait_for_selector(BOX, state="detached")
        title = page.evaluate(TEXT, TITLE)
    assert title == STORED, title


# The code review's section 2: three changes without a test

def test_a_rename_while_the_run_loads_reaches_its_view(rename_site):
    """RUN_A's view opened in the app's page while its lines.arrow is held (the run still loads, the list's name
    already taken); Home through the loading page's Back ("Home"), RUN_A renamed on its card, the file let through,
    the run opened from its card in the same page: the head shows the new name, not the one the load took from the
    list before the rename."""
    site, _ = rename_site
    with Browser(site) as browser:
        page = page_of(browser)
        fresh(page)
        held = hold_first(page, f"**/runs/{RUN_A}/lines.arrow")  # the view's download; Home's mini map's goes through
        page.goto(f"{site}/?ui=c#run={RUN_A}")
        lines = the_held(page, held)
        page.wait_for_selector(".c-result-wait .c-loading")
        taken = page.evaluate("(run) => (window.FINDALINE_RUNS || []).find((r) => r.id === run).name", RUN_A)
        back = page.evaluate(TEXT, ".c-result-wait .c-back")
        page.click(".c-result-wait .c-back")
        field = open_rename(page, RUN_A)
        field.fill(NEW)
        with page.expect_response(rename_answer()):
            page.keyboard.press("Enter")
        page.wait_for_selector(f"{card(RUN_A)} .c-card-panel", state="detached")
        with page.expect_response(lambda r: r.url.endswith(f"/runs/{RUN_A}/lines.arrow")):
            lines.continue_()
        page.click(f"{card(RUN_A)} a.c-card-open")
        view_of(page, RUN_A)
        head = page.evaluate(TEXT, TITLE)
    assert taken == NAME_A, taken  # (the load named the run before the rename)
    assert back.strip() == WORDS["ui.app.home"] == "Home", back
    assert head == NEW, head


def test_a_rename_that_ends_after_its_form_is_gone(rename_site):
    """On Home the rename's POST held; while it waits the card's menu opened and "Share…" pressed (the rename's form
    gone, Share's panel shown); the POST then answered by the server: the card shows the new name and Share's panel
    is still open."""
    site, data = rename_site
    held = []
    with Browser(site) as browser:
        page = page_of(browser)
        open_home(page, site)
        field = open_rename(page, RUN_A)
        page.route(f"**/api/runs/{RUN_A}", lambda route: held.append(route) if route.request.method == "POST" else route.continue_())
        field.fill(NEW)
        page.keyboard.press("Enter")
        page.wait_for_function(READ_ONLY, arg=card(RUN_A))
        rename = the_held(page, held)
        open_menu(page, RUN_A)
        page.click(f"{card(RUN_A)} [role=menuitem]:has-text('Share…')")
        page.wait_for_selector(f"{card(RUN_A)} {SHARE_PANEL}")
        forms = page.evaluate(COUNT, f"{card(RUN_A)} .c-rename")
        with page.expect_response(rename_answer()):
            rename.continue_()
        shown = settled(page, "([sel, name]) => document.querySelector(sel + ' .c-card-name').textContent === name", [card(RUN_A), NEW])
        name = page.evaluate(NAME, card(RUN_A))
        share = page.evaluate(COUNT, f"{card(RUN_A)} {SHARE_PANEL}")
    assert forms == 0, forms  # (the form was gone when the answer came)
    assert shown and name == NEW, name
    assert share == 1, share
    assert stored_name(data, RUN_A) == NEW


def test_a_rename_that_ends_after_home_was_left(rename_site):
    """On Home the rename's POST held; Favourites opened (#favourites: Home and the form gone), the POST then
    answered by the server; Home again, with its new request for the list of runs held: the card shows the new name
    (the rename's own answer, not the list's), and still once the list has answered."""
    site, _ = rename_site
    held = []
    with Browser(site) as browser:
        page = page_of(browser)
        open_home(page, site)
        field = open_rename(page, RUN_A)
        page.route(f"**/api/runs/{RUN_A}", lambda route: held.append(route) if route.request.method == "POST" else route.continue_())
        field.fill(NEW)
        page.keyboard.press("Enter")
        page.wait_for_function(READ_ONLY, arg=card(RUN_A))
        rename = the_held(page, held)
        page.click(".c-nav a[href='#favourites']")
        page.wait_for_selector(".c-favs-page")
        page.wait_for_selector(card(RUN_A), state="detached")
        with page.expect_response(rename_answer()):
            rename.continue_()
        lists = hold_first(page, "**/api/runs")  # Home's next list of runs (GET /api/runs) held, later ones let through
        page.click(".c-nav a[href='#home']")
        page.wait_for_selector(card(RUN_A))
        listing = the_held(page, lists)  # Home asks for the list again: held
        named = "([sel, name]) => document.querySelector(sel + ' .c-card-name').textContent === name"
        while_held = [settled(page, named, [card(RUN_A), NEW]), page.evaluate(NAME, card(RUN_A))]
        with page.expect_response(lambda r: r.request.method == "GET" and r.url.endswith("/api/runs")):
            listing.continue_()
        after = [settled(page, named, [card(RUN_A), NEW]), page.evaluate(NAME, card(RUN_A))]
    assert while_held == [True, NEW], while_held
    assert after == [True, NEW], after


def test_the_views_share_and_rename_ask_for_the_runs_once(rename_site):
    """The owner's desktop opening <site>/?ui=c#run=<RUN_A> sends GET /api/runs twice: once for the app's start and
    once for the view's Share and Rename together, counted until both are drawn and the network is idle."""
    site, _ = rename_site
    with Browser(site) as browser:
        page = page_of(browser)
        fresh(page)
        sent = []
        page.on("request", lambda r: sent.append(r.url) if r.method == "GET" and r.url.split("?")[0].endswith("/api/runs") else None)
        page.goto(f"{site}/?ui=c#run={RUN_A}")
        view_of(page, RUN_A)
        page.wait_for_selector(BUTTON)
        page.wait_for_selector(".c-result-top .r-actions button:has-text('Share')")
        page.wait_for_load_state("networkidle")
        count = len(sent)
    assert count == 2, sent


def test_an_old_list_that_fails_is_asked_for_again(rename_site):
    """The same, but the old request for the list fails (aborted) after the rename instead of answering: nothing of it
    is kept and no empty list either; the list is asked for again, and RUN_B opened from its card shows the new name
    in the view's head and in window.FINDALINE_RUNS."""
    site, _ = rename_site
    with Browser(site) as browser:
        page = page_of(browser)
        fresh(page)
        held = hold_first(page, RUNS_JS)
        open_home(page, site, RUN_B)
        route = the_held(page, held)
        field = open_rename(page, RUN_B)
        field.fill(NEW)
        with page.expect_response(rename_answer(RUN_B)):
            page.keyboard.press("Enter")
        page.wait_for_selector(f"{card(RUN_B)} .c-card-panel", state="detached")
        with page.expect_response(lambda r: urlparse(r.url).path == "/runs/runs.js"):  # asked for again, answered
            route.abort()
        page.wait_for_function("() => Array.isArray(window.FINDALINE_RUNS)")
        page.click(f"{card(RUN_B)} a.c-card-open")
        view_of(page, RUN_B)
        head = page.evaluate(TEXT, TITLE)
        listed = page.evaluate("() => window.FINDALINE_RUNS.map((r) => r.name)")
    assert head == NEW, f"the view shows {head!r}; window.FINDALINE_RUNS {listed}"
    assert NEW in listed and NAME_B not in listed, listed
