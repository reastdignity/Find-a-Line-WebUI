"""Renaming a run on Home (line volume's round 7, step 2g's page half; the accepted mock-up's points 5, 7, 8, 9, 11,
25 and its texts T1 to T6, T9): the card's menu item "Rename…" after "Share…" with the pencil ("Edit & run again"
takes the circular arrow), the card's panel with the form (the whole name selected, Save off while empty or unchanged,
Enter saves, Esc closes, the focus back on the menu's button), the waiting state, the server's answers (the name as
stored; 400: the catalogue's error.run_name; 409: "in use"; anything else: the request's error text) and the panel
and a low card's menu scrolled into view on a small phone. Who gets the item: the owner on the public site, never
the local app nor a card of another user's search.

Playwright's Edge over the public app on a thread (uvicorn) with the real route POST /api/runs/<id>
(tests/test_run_rename.py tests the route itself), offline. Run from PowerShell (.claude/rules/browser-tests.md).
This module's fixture `rename_site` and its helpers serve the other tests of the round's page half."""

import json
import os
import re
import socket
import sys
import threading
import time
from contextlib import contextmanager

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

pytest.importorskip("httpx2")

from test_public import RUN_A, RUN_B, account_settings, session_of  # noqa: E402,F401
from test_shell_c import copy_clip  # noqa: E402
from test_shell_c_view_map import DESKTOP, SMALL_PHONE, WAIT, view_clip  # noqa: E402,F401
from test_web import EDGE, _playwright  # noqa: E402

pytestmark = pytest.mark.skipif(not os.path.exists(EDGE) or not _playwright(),
                                reason="needs Microsoft Edge and Playwright (group ui)")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHARE_TOKEN = "AbCdEf0123456789-share_token-rename7XYZ1"  # a share link's token (token_urlsafe's alphabet)
NAME_A, NAME_B = "A's run", "Second run"  # run.json's names (the stores' heads keep the clip's)
FLAG = "try { localStorage.setItem('findaline.view', 'b'); } catch (e) {}"
with open(os.path.join(REPO, "locales", "en.json"), encoding="utf-8") as _f:
    WORDS = json.load(_f)
REFUSED = WORDS["error.run_name"].replace("{{max}}", "100")


def jobs_stub(run: str, own: bool = True) -> str:
    """An init script: the app's job list answered with one finished job of `run` (its card on Home is the job's,
    with "Edit & run again"; `own` False: another user's search, as an administrator's list has it)."""
    return """
const realFetchOfJobs = window.fetch;
window.fetch = (url, init) => String(url).replace(/^https?:\\/\\/[^/]+/, '').split('?')[0] !== '/api/jobs' || (init && init.method && init.method !== 'GET')
  ? realFetchOfJobs(url, init)
  : Promise.resolve(new Response(JSON.stringify({jobs: [{id: 'job-1', status: 'done', run_id: '%s', title: 'A search',
      created: '2026-10-01T10:00:00', finished: '2026-10-01T10:05:00', own: %s}], seq: 1, worker: true}), {headers: {'content-type': 'application/json'}}));
""" % (run, "true" if own else "false")


def kit_icon(name: str) -> str:
    """The path data of a kit icon (viewer/src/ui/icons.tsx ICONS), as written there."""
    with open(os.path.join(REPO, "viewer", "src", "ui", "icons.tsx"), encoding="utf-8") as f:
        markup = re.search(r"\n  %s: '([^']*)'" % name, f.read()).group(1)
    return re.search(r'd="([^"]+)"', markup).group(1)


def serve(app, port: int):
    """The app on a thread (uvicorn) until the generator is closed."""
    import uvicorn
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 30
        while not server.started:
            assert time.monotonic() < deadline, "the server did not start"
            time.sleep(0.05)
        yield
    finally:
        server.should_exit = True
        thread.join(10)


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture
def rename_site(tmp_path, view_clip, account_settings):
    """The public app over a data folder with two runs of A (RUN_A, a demo run shared by a link; RUN_B), both the
    view's clip run under names of their own; yields (the site's address, the data folder). `/test-sign-in/<who>`
    signs a browser in as one of test_public's PEOPLE."""
    import accounts as ac
    import web
    from fastapi.responses import RedirectResponse
    from jobs import Jobs
    from settings import PublicSettings
    port = free_port()
    site = f"http://localhost:{port}"
    data = tmp_path / "data"
    data.mkdir()
    copy_clip(view_clip, data, RUN_A, NAME_A)
    copy_clip(view_clip, data, RUN_B, NAME_B)
    jobs = Jobs(str(data))
    cookies = {}
    for who in ("a", "b", "admin"):
        user_id, cookie, _ = session_of(data, account_settings, who)
        cookies[who] = cookie
        if who == "a":
            jobs.add_run(RUN_A, user_id, 1)
            jobs.add_run(RUN_B, user_id, 1)
    jobs.set_share(RUN_A, ac.digest(SHARE_TOKEN))
    jobs.set_visibility(RUN_A, "demo")
    settings = PublicSettings(public_url=site, trusted_proxy="127.0.0.1", contact="admin@example.org")
    app = web.create_app(str(data), public=settings, accounts=account_settings)

    @app.get("/test-sign-in/{who}")
    def sign_in(who: str):  # the session's cookie as the sign-in sets it (a browser takes no __Host- cookie from a script)
        response = RedirectResponse("/", 302)
        response.set_cookie(ac.SESSION_COOKIE, cookies[who], secure=True, httponly=True, path="/", samesite="lax")
        return response
    yield from ((site, data) for _ in serve(app, port))


class Browser:
    """Playwright's Edge for one test: `page(device, who, script)` gives a page of a fresh context, signed in as
    `who` (None: a visitor), with the view's flag and `script` as init scripts; page errors fail the test at close."""

    def __init__(self, site: str):
        self.site, self.errors, self.contexts = site, [], []

    def __enter__(self):
        from playwright.sync_api import sync_playwright
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(channel="msedge", headless=True)
        return self

    def __exit__(self, kind, *rest):
        for context in self.contexts:
            context.close()
        self.browser.close()
        self.playwright.stop()
        if kind is None:
            assert self.errors == [], self.errors

    def page(self, device: dict = DESKTOP, who: str | None = "a", script: str = ""):
        context = self.browser.new_context(**device)
        self.contexts.append(context)
        context.add_init_script(FLAG + script)
        page = context.new_page()
        page.set_default_timeout(WAIT)
        page.on("pageerror", lambda e: self.errors.append(str(e)))
        if who:
            page.goto(f"{self.site}/test-sign-in/{who}")
            assert any(c["name"].startswith("__Host-") for c in context.cookies()), "not signed in"
        return page


def card(run: str) -> str:
    return f".c-card[data-run='{run}']"


def open_home(page, site: str, run: str = RUN_A):
    """Home with the card of `run` drawn."""
    page.goto(f"{site}/?ui=c")
    page.wait_for_selector(card(run))


def open_menu(page, run: str) -> list:
    """The card's menu opened: its items' words."""
    page.click(f"{card(run)} .c-card-menu")
    page.wait_for_selector(f"{card(run)} [role=menu]")
    return page.evaluate("(sel) => [...document.querySelectorAll(sel + ' [role=menuitem]')].map((i) => i.textContent.trim())", card(run))


def open_rename(page, run: str):
    """"Rename…" pressed in the card's menu: the panel's field, once it has the focus with its whole name selected."""
    open_menu(page, run)
    page.click(f"{card(run)} [role=menuitem]:has-text('Rename…')")
    page.wait_for_selector(f"{card(run)} .c-card-panel .c-rename input")
    # the form takes the focus and selects the name in an effect, after the paint: waited for (the tests then read it)
    page.wait_for_function("(sel) => { const i = document.querySelector(sel + ' .c-rename input'); "
                           "return document.activeElement === i && i.selectionStart === 0 && i.selectionEnd === i.value.length; }",
                           arg=card(run))
    return page.locator(f"{card(run)} .c-rename input")


def the_held(page, held: list):
    """The request a route's handler put into `held` (not answered yet), once it is there: Playwright calls the
    handler while the page is waited on."""
    deadline = time.monotonic() + WAIT / 1000
    while not held:
        assert time.monotonic() < deadline, "the request was not sent"
        page.wait_for_timeout(10)
    return held.pop()


FORM = """(sel) => { const f = document.querySelector(sel + ' .c-rename'), i = f.querySelector('input'), b = [...f.querySelectorAll('button')];
  return {value: i.value, readonly: i.readOnly, invalid: i.getAttribute('aria-invalid'), max: i.getAttribute('maxlength'),
          label: i.getAttribute('aria-label'), labels: f.querySelectorAll('label').length,
          buttons: b.map((x) => x.textContent.trim()), off: b.map((x) => x.disabled), busy: b[0].getAttribute('aria-busy'),
          ring: !!b[0].querySelector('.r-spin'), line: (f.querySelector('[role=alert]') || {}).textContent || '',
          described: i.getAttribute('aria-describedby') === (f.querySelector('[role=alert]') || {}).id,
          focus: document.activeElement === i, selected: [i.selectionStart, i.selectionEnd]}; }"""
NAME = "(sel) => document.querySelector(sel + ' .c-card-name').textContent"
ON_MENU_BUTTON = "(sel) => document.activeElement === document.querySelector(sel + ' .c-card-menu')"
# The form's own signal that its effect after a failure ran: the focus in the field, the caret collapsed at the end
BACK_IN_FIELD = """(sel) => { const i = document.querySelector(sel + ' .c-rename input');
  return !!i && !i.readOnly && document.activeElement === i && i.selectionStart === i.value.length
    && i.selectionEnd === i.value.length; }"""


@contextmanager
def line_before_typing(page, form: str):
    """For a failure whose line the test then types after, in the same field (`form`: a selector holding the
    .c-rename form): the held answer is let go inside the block. Before it, once the request waits (the field
    read-only), the field loses the focus, as a press elsewhere takes it; after it, the line drawn, the test waits for
    the form's own signal that its effect after the failure ran (RenameForm: the focus back in the field, the caret
    after what was typed). Preact runs that effect after the paint, a frame after the line (at most 35 ms + a task
    without a frame): a fill in between had the whole name selected by Playwright, the caret then put at its end by
    the effect, and its text appended ("Waiting nameTab\\there"). Without the blur the field would show the signal
    already before the effect (the focus never left it, the caret at the end after the fill)."""
    page.wait_for_function("(sel) => document.querySelector(sel + ' .c-rename input').readOnly", arg=form)
    page.evaluate("(sel) => document.querySelector(sel + ' .c-rename input').blur()", form)
    yield
    page.wait_for_selector(f"{form} .c-rename [role=alert]")
    page.wait_for_function(BACK_IN_FIELD, arg=form)


def closed(page, run: str) -> bool:
    """The card's panel gone; then whether the focus came to the menu's button (the page puts it there in an effect,
    after the paint: waited for, at most WAIT)."""
    from playwright.sync_api import TimeoutError as PlaywrightTimeout
    page.wait_for_selector(f"{card(run)} .c-card-panel", state="detached")
    try:
        page.wait_for_function(ON_MENU_BUTTON, arg=card(run))
    except PlaywrightTimeout:
        return False
    return True


def test_the_menu_has_rename_for_the_owner(rename_site):
    """An own run's card (a demo run's owner too): "Rename…" after "Share…" with the pencil, "Edit & run again" with
    the circular arrow. Another user's search on an administrator's Home (a card without its run) and another user
    signed in: no "Rename…"."""
    site, _ = rename_site
    with Browser(site) as browser:
        page = browser.page(script=jobs_stub(RUN_A))
        open_home(page, site)
        items = open_menu(page, RUN_A)
        icons = page.evaluate("(sel) => Object.fromEntries([...document.querySelectorAll(sel + ' [role=menuitem]')]"
                              ".map((i) => [i.textContent.trim(), i.querySelector('svg').innerHTML]))", card(RUN_A))
        page.keyboard.press("Escape")
        second = open_menu(page, RUN_B)  # a run without its search's card: no "Edit & run again"
        admin = browser.page(who="admin", script=jobs_stub(RUN_B, own=False))
        admin.goto(f"{site}/?ui=c")
        admin.wait_for_selector(".c-card[data-job='job-1']")
        other = admin.evaluate("() => { const c = document.querySelector(\".c-card[data-job='job-1']\"); "
                               "c.querySelector('.c-card-menu').click(); return c.dataset.run || ''; }")
        admin.wait_for_selector(".c-card[data-job='job-1'] [role=menu]")
        theirs = admin.evaluate("() => [...document.querySelectorAll(\".c-card[data-job='job-1'] [role=menuitem]\")].map((i) => i.textContent.trim())")
    assert items == ["Open the result", "Edit & run again", "Share…", "Rename…", "Report a problem…", "Delete…"], items
    assert second == ["Open the result", "Share…", "Rename…", "Report a problem…", "Delete…"], second
    assert f'd="{kit_icon("edit")}"' in icons["Rename…"], icons["Rename…"]
    assert f'd="{kit_icon("refresh")}"' in icons["Edit & run again"], icons["Edit & run again"]
    # another user's finished search, as an administrator lists it: a card without its run, nothing of the owner's
    assert other == "" and "Rename…" not in theirs and "Share…" not in theirs and "Delete…" not in theirs, theirs
    assert "Edit & run again" in theirs, theirs


def test_rename_on_a_card(rename_site):
    """"Rename…" opens the card's panel (a dialog named "Rename the run"): the field named "The run's name" with the
    whole name selected and no label, no maxlength, Save and Cancel. Save is off while the field is unchanged
    (also with spaces added) or empty. Esc closes it and Cancel too, the focus back on the menu's button. Enter
    saves: the card shows the name as the server stored it (spaces joined and trimmed), the panel is closed, the
    focus is on the menu's button, run.json holds the name; the run's id and its card's address stay."""
    site, data = rename_site
    with Browser(site) as browser:
        page = browser.page()
        open_home(page, site)
        field = open_rename(page, RUN_A)
        panel = page.evaluate("(sel) => { const p = document.querySelector(sel + ' .c-card-panel'); "
                              "return [p.getAttribute('role'), p.getAttribute('aria-label'), p.querySelectorAll('.u-h4, h1, h2, h3, b').length]; }",
                              card(RUN_A))
        opened = page.evaluate(FORM, card(RUN_A))
        field.fill("  A's   run ")
        spaced = page.evaluate(FORM, card(RUN_A))
        field.fill("   ")
        empty = page.evaluate(FORM, card(RUN_A))
        field.fill("Another name")
        typed = page.evaluate(FORM, card(RUN_A))
        page.keyboard.press("Escape")
        escaped = [page.evaluate(NAME, card(RUN_A)), closed(page, RUN_A)]
        open_rename(page, RUN_A)
        page.click(f"{card(RUN_A)} .c-rename button:has-text('Cancel')")
        cancelled = [page.evaluate(NAME, card(RUN_A)), closed(page, RUN_A)]
        field = open_rename(page, RUN_A)
        field.fill("  The north   side ")
        with page.expect_response(lambda r: r.request.method == "POST" and r.url.endswith(f"/api/runs/{RUN_A}")) as answer:
            page.keyboard.press("Enter")
        on_button = closed(page, RUN_A)
        saved = [page.evaluate(NAME, card(RUN_A)), on_button]
        href = page.evaluate("(sel) => document.querySelector(sel + ' a.c-card-open').getAttribute('href')", card(RUN_A))
        sent = answer.value.request.post_data_json
    assert panel == ["dialog", "Rename the run", 0], panel
    assert opened["value"] == NAME_A and opened["focus"] and opened["selected"] == [0, len(NAME_A)], opened
    assert opened["label"] == "The run's name" and opened["labels"] == 0 and opened["max"] is None, opened
    assert opened["buttons"] == ["Save", "Cancel"] and opened["off"] == [True, False] and not opened["line"], opened
    assert spaced["off"] == [True, False] and empty["off"] == [True, False] and typed["off"] == [False, False], (spaced, empty, typed)
    assert escaped == [NAME_A, True] and cancelled == [NAME_A, True], (escaped, cancelled)
    assert sent == {"name": "  The north   side "}, sent  # as typed: the server's rule decides
    assert saved == ["The north side", True], saved
    assert RUN_A in href, href
    with open(data / "runs" / RUN_A / "run.json", encoding="utf-8") as f:
        assert json.load(f)["name"] == "The north side"


def test_rename_with_the_keyboard_alone(rename_site):
    """The keyboard's way, no pointer: the focus on the card's menu button, Enter opens the menu with the focus on its
    first item; the arrow keys reach "Rename…" (End, then up past "Delete…" and "Report a problem…"); Enter opens the
    panel with the name selected, typing replaces it, Enter saves; the focus is back on the menu's button and the card
    shows the new name. Tab from the field reaches Save, then Cancel."""
    site, _ = rename_site
    at = "() => (document.activeElement.textContent || document.activeElement.getAttribute('aria-label') || '').trim()"
    with Browser(site) as browser:
        page = browser.page()
        open_home(page, site)
        page.focus(f"{card(RUN_A)} .c-card-menu")
        page.keyboard.press("Enter")
        page.wait_for_function("(sel) => document.activeElement === document.querySelector(sel + ' [role=menuitem]')", arg=card(RUN_A))
        first = page.evaluate(at)
        page.keyboard.press("End")
        last = page.evaluate(at)
        page.keyboard.press("ArrowUp")
        page.keyboard.press("ArrowUp")
        item = page.evaluate(at)
        page.keyboard.press("Enter")
        page.wait_for_function("(sel) => { const i = document.querySelector(sel + ' .c-rename input'); "
                               "return !!i && document.activeElement === i && i.selectionStart === 0 && i.selectionEnd === i.value.length; }",
                               arg=card(RUN_A))
        page.keyboard.type("Typed with keys")
        typed = page.evaluate(FORM, card(RUN_A))
        page.keyboard.press("Tab")
        save = page.evaluate(at)
        page.keyboard.press("Tab")
        cancel = page.evaluate(at)
        page.keyboard.press("Shift+Tab")
        page.keyboard.press("Shift+Tab")
        page.keyboard.press("Enter")
        on_button = closed(page, RUN_A)
        name = page.evaluate(NAME, card(RUN_A))
    assert (first, last, item) == ("Open the result", "Delete…", "Rename…"), (first, last, item)
    assert typed["value"] == "Typed with keys" and typed["off"] == [False, False], typed
    assert (save, cancel) == ("Save", "Cancel"), (save, cancel)
    assert on_button and name == "Typed with keys", (on_button, name)


def test_a_long_name_is_not_cut(rename_site):
    """A name of 100 characters outside the basic plane (200 UTF-16 units) is the server's to take: the field cuts
    nothing, the card shows all of it."""
    site, _ = rename_site
    name = "\U0001F9D7" * 100
    with Browser(site) as browser:
        page = browser.page()
        open_home(page, site)
        field = open_rename(page, RUN_A)
        field.fill(name)
        page.keyboard.press("Enter")
        page.wait_for_selector(f"{card(RUN_A)} .c-card-panel", state="detached")
        shown = page.evaluate(NAME, card(RUN_A))
    assert shown == name, len(shown)


def test_waiting_and_the_refusals(rename_site):
    """While the request waits the field cannot be changed, Save shows the ring and both buttons are off, and Esc
    does not close the panel. A refused name (a tab: the server's 400) shows the catalogue's words of
    error.run_name under the buttons, the typed name kept, the field marked and described by the line, the focus in
    it; typing takes the line away. 409 shows "The run is in use. Try again in a moment."; another failure the
    request's error text. Save is on again each time, and the card keeps its name."""
    site, _ = rename_site
    held = []
    with Browser(site) as browser:
        page = browser.page()
        open_home(page, site)
        field = open_rename(page, RUN_A)
        page.route(f"**/api/runs/{RUN_A}", lambda route: held.append(route) if route.request.method == "POST" else route.continue_())
        field.fill("Waiting name")
        page.keyboard.press("Enter")
        page.wait_for_function("(sel) => document.querySelector(sel + ' .c-rename input').readOnly", arg=card(RUN_A))
        waiting = page.evaluate(FORM, card(RUN_A))
        page.keyboard.press("Escape")
        still = page.evaluate("(sel) => !!document.querySelector(sel + ' .c-card-panel .c-rename')", card(RUN_A))
        with line_before_typing(page, card(RUN_A)):
            the_held(page, held).fulfill(status=409, content_type="application/json",
                                         body=json.dumps({"detail": "the run is in use: try again in a moment"}))
        in_use = page.evaluate(FORM, card(RUN_A))
        field.press("End")
        field.type("!")
        cleared = page.evaluate(FORM, card(RUN_A))
        page.keyboard.press("Enter")
        with line_before_typing(page, card(RUN_A)):
            the_held(page, held).fulfill(status=500, content_type="application/json", body=json.dumps({"detail": "made-up failure"}))
        failed = page.evaluate(FORM, card(RUN_A))
        page.unroute(f"**/api/runs/{RUN_A}")
        field.fill("Tab\there")
        page.keyboard.press("Enter")
        page.wait_for_selector(f"{card(RUN_A)} .c-rename [role=alert]")
        refused = page.evaluate(FORM, card(RUN_A))
        name = page.evaluate(NAME, card(RUN_A))
    assert waiting["readonly"] and waiting["off"] == [True, True] and waiting["busy"] == "true" and waiting["ring"], waiting
    assert waiting["value"] == "Waiting name" and still, (waiting, still)
    assert in_use["line"] == "The run is in use. Try again in a moment." and in_use["off"] == [False, False], in_use
    assert in_use["value"] == "Waiting name" and in_use["focus"] and in_use["selected"] == [12, 12] and not in_use["readonly"], in_use
    assert cleared["line"] == "" and cleared["invalid"] is None and cleared["value"] == "Waiting name!", cleared
    assert failed["line"] == "made-up failure" and failed["off"] == [False, False], failed
    assert refused["line"] == REFUSED == "Give the run a name of 1 to 100 characters, with no tab or invisible character.", refused
    assert refused["value"] == "Tab\there" and refused["invalid"] == "true" and refused["described"] and refused["focus"], refused
    assert name == NAME_A, name


def test_a_small_phone_keeps_the_menu_and_the_line_in_sight(rename_site):
    """On a 390 by 664 phone the menu of a card low on the screen is scrolled into view whole, above the bottom
    bar, when it opens; so is the card's panel when it opens. A name's refusal (two lines) then stands above the bar
    too, but on this phone it would fit without the panel's second scroll: that scroll is
    test_a_small_phone_keeps_a_long_line_in_sight's."""
    site, _ = rename_site
    box = ("(sel) => { const b = document.querySelector(sel).getBoundingClientRect(), "
           "bar = document.querySelector('.u-bnav').getBoundingClientRect(), "
           "top = document.querySelector('.c-main').getBoundingClientRect().top; "
           "return {top: Math.round(b.top), bottom: Math.round(b.bottom), bar: Math.round(bar.top), page: Math.round(top)}; }")
    with Browser(site) as browser:
        page = browser.page(device=SMALL_PHONE)
        open_home(page, site)
        last = page.evaluate("() => [...document.querySelectorAll('.c-cards > .c-card')].pop().dataset.run")
        page.evaluate("() => { document.querySelector('.c-main').scrollTop = 0; }")
        before = page.evaluate(box, f"{card(last)} .c-card-menu")
        page.tap(f"{card(last)} .c-card-menu")
        page.wait_for_selector(f"{card(last)} [role=menu]")
        page.wait_for_function("(sel) => document.querySelector(sel).getBoundingClientRect().bottom <= "
                               "document.querySelector('.u-bnav').getBoundingClientRect().top", arg=f"{card(last)} .r-pop")
        menu = page.evaluate(box, f"{card(last)} .r-pop")
        sizes = page.evaluate("(sel) => [...document.querySelectorAll(sel + ' [role=menuitem]')].map((i) => Math.round(i.getBoundingClientRect().height))",
                              card(last))
        page.tap(f"{card(last)} [role=menuitem]:has-text('Rename…')")
        field = page.locator(f"{card(last)} .c-rename input")
        field.wait_for()
        panel = page.evaluate(box, f"{card(last)} .c-card-panel")
        field.fill("Tab\there")
        page.tap(f"{card(last)} .c-rename button:has-text('Save')")
        page.wait_for_selector(f"{card(last)} .c-rename [role=alert]")
        page.wait_for_function("(sel) => document.querySelector(sel).getBoundingClientRect().bottom <= "
                               "document.querySelector('.u-bnav').getBoundingClientRect().top", arg=f"{card(last)} .c-rename [role=alert]")
        line = page.evaluate(box, f"{card(last)} .c-rename [role=alert]")
        controls = page.evaluate("(sel) => [...document.querySelectorAll(sel + ' .c-rename input, ' + sel + ' .c-rename button')]"
                                 ".map((c) => Math.round(c.getBoundingClientRect().height))", card(last))
    # the card low enough: the menu, opened where its button stood, would have reached under the bar
    assert before["bottom"] + (menu["bottom"] - menu["top"]) > before["bar"], (before, menu)
    assert menu["bottom"] <= menu["bar"] and menu["top"] >= menu["page"], (before, menu)
    assert min(sizes) >= 44, sizes
    assert panel["bottom"] <= panel["bar"], panel
    assert line["bottom"] <= line["bar"], line
    assert min(controls) >= 44, controls


# A failure's words long enough for four lines in a small phone's card panel (a server's long message)
LONG_FAILURE = ("A made-up failure whose words are long enough to take four lines in the card's narrow panel on a small "
                "phone, as a long message of the server would, so that its line is taller.")


def test_a_small_phone_keeps_a_long_line_in_sight(rename_site):
    """On a 390 by 664 phone the panel of the last card, opened from its menu, leaves less room above the bottom bar
    than a failure's line of four lines (a server's long message) takes: once that line is drawn the panel is
    scrolled into view again and the line stands whole above the bar (where the page stood, it would end under the
    bar)."""
    site, _ = rename_site
    box = ("(sel) => { const b = document.querySelector(sel).getBoundingClientRect(), "
           "bar = document.querySelector('.u-bnav').getBoundingClientRect(), main = document.querySelector('.c-main'); "
           "return {top: Math.round(b.top), bottom: Math.round(b.bottom), bar: Math.round(bar.top), "
           "page: Math.round(main.getBoundingClientRect().top), scroll: Math.round(main.scrollTop)}; }")
    above = ("(sel) => document.querySelector(sel).getBoundingClientRect().bottom <= "
             "document.querySelector('.u-bnav').getBoundingClientRect().top")
    with Browser(site) as browser:
        page = browser.page(device=SMALL_PHONE)
        open_home(page, site)
        last = page.evaluate("() => [...document.querySelectorAll('.c-cards > .c-card')].pop().dataset.run")
        page.route(f"**/api/runs/{last}", lambda route: route.fulfill(status=500, content_type="application/json",
                                                                       body=json.dumps({"detail": LONG_FAILURE}))
                   if route.request.method == "POST" else route.continue_())
        page.evaluate("() => { document.querySelector('.c-main').scrollTop = 0; }")
        page.tap(f"{card(last)} .c-card-menu")
        page.wait_for_selector(f"{card(last)} [role=menu]")
        page.wait_for_function(above, arg=f"{card(last)} .r-pop")
        page.tap(f"{card(last)} [role=menuitem]:has-text('Rename…')")
        # the panel's effects ran (the focus in the field: the panel scrolled into view in the same effect)
        page.wait_for_function("(sel) => { const i = document.querySelector(sel + ' .c-rename input'); "
                               "return !!i && document.activeElement === i; }", arg=card(last))
        panel = page.evaluate(box, f"{card(last)} .c-card-panel")
        page.locator(f"{card(last)} .c-rename input").fill("Another name")
        page.tap(f"{card(last)} .c-rename button:has-text('Save')")
        page.wait_for_selector(f"{card(last)} .c-rename [role=alert]")
        page.wait_for_function(above, arg=f"{card(last)} .c-rename [role=alert]")
        line = page.evaluate(box, f"{card(last)} .c-rename [role=alert]")
        words = page.evaluate("(sel) => document.querySelector(sel).textContent", f"{card(last)} .c-rename [role=alert]")
    assert words == LONG_FAILURE, words
    assert panel["bottom"] <= panel["bar"], panel
    # the room under the panel at its opening is less than the line's height: the line cannot fit without a scroll;
    # where the page stood then, the line would end under the bar
    assert panel["bar"] - panel["bottom"] < line["bottom"] - line["top"], (panel, line)
    assert line["bottom"] + (line["scroll"] - panel["scroll"]) > line["bar"], (panel, line)
    assert line["bottom"] <= line["bar"] and line["top"] >= line["page"], line


def test_the_local_app_has_no_rename(tmp_path, view_clip):
    """The local app: a run's card has no "Rename…" (nor Share or Delete): renaming is the public site's."""
    from test_web import _server
    data = tmp_path / "local"
    data.mkdir()
    copy_clip(view_clip, data, RUN_A, NAME_A)
    with _server(data) as port:
        site = f"http://127.0.0.1:{port}"
        with Browser(site) as browser:
            page = browser.page(who=None)
            open_home(page, site)
            items = open_menu(page, RUN_A)
    assert items == ["Open the result"], items
