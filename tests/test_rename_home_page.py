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
    """"Rename…" pressed in the card's menu: the panel's field."""
    open_menu(page, run)
    page.click(f"{card(run)} [role=menuitem]:has-text('Rename…')")
    page.wait_for_selector(f"{card(run)} .c-card-panel .c-rename input")
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
        page.wait_for_selector(f"{card(RUN_A)} .c-card-panel", state="detached")
        escaped = [page.evaluate(NAME, card(RUN_A)), page.evaluate(ON_MENU_BUTTON, card(RUN_A))]
        open_rename(page, RUN_A)
        page.click(f"{card(RUN_A)} .c-rename button:has-text('Cancel')")
        page.wait_for_selector(f"{card(RUN_A)} .c-card-panel", state="detached")
        cancelled = [page.evaluate(NAME, card(RUN_A)), page.evaluate(ON_MENU_BUTTON, card(RUN_A))]
        field = open_rename(page, RUN_A)
        field.fill("  The north   side ")
        with page.expect_response(lambda r: r.request.method == "POST" and r.url.endswith(f"/api/runs/{RUN_A}")) as answer:
            page.keyboard.press("Enter")
        page.wait_for_selector(f"{card(RUN_A)} .c-card-panel", state="detached")
        saved = [page.evaluate(NAME, card(RUN_A)), page.evaluate(ON_MENU_BUTTON, card(RUN_A))]
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
        the_held(page, held).fulfill(status=409, content_type="application/json",
                           body=json.dumps({"detail": "the run is in use: try again in a moment"}))
        page.wait_for_selector(f"{card(RUN_A)} .c-rename [role=alert]")
        in_use = page.evaluate(FORM, card(RUN_A))
        field.press("End")
        field.type("!")
        cleared = page.evaluate(FORM, card(RUN_A))
        page.keyboard.press("Enter")
        the_held(page, held).fulfill(status=500, content_type="application/json", body=json.dumps({"detail": "made-up failure"}))
        page.wait_for_selector(f"{card(RUN_A)} .c-rename [role=alert]")
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
    bar, when it opens; so is the card's panel, and again when a refusal's line makes it taller."""
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
    assert menu["bottom"] <= menu["bar"] and menu["top"] >= menu["page"], (before, menu)
    assert min(sizes) >= 44, sizes
    assert panel["bottom"] <= panel["bar"], panel
    assert line["bottom"] <= line["bar"], line
    assert min(controls) >= 44, controls


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
