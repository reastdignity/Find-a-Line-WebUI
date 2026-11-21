"""Who sees which of the run's actions in the result view (step 3c's frame: RunActions in the header; its rules are
today's page's, unchanged: Share's owner check, mayExport), on the public site: the owner signed in has Share and
Download on the app's page; another signed-in user opening the owner's demo run has no Share; a visitor not signed
in on the demo run's map.html and anyone on a share link's page have neither Share nor Download. Today's tests of these
rules: test_shell_c.py::test_shell_c_public (Share), test_store_share.py::test_share_links_read_the_store_in_edge (no
Download on a share link and a demo run); this file takes their fixtures (test_public's people and runs) with the view's
clip run. Playwright's Edge over the public app on a thread (uvicorn), offline. Run from PowerShell
(.claude/rules/browser-tests.md)."""

import os
import socket
import sys
import threading
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

pytest.importorskip("httpx2")

from test_public import RUN_A, account_settings, session_of  # noqa: E402,F401
from test_shell_c import copy_clip  # noqa: E402
from test_shell_c_view_map import DESKTOP, WAIT, view_clip  # noqa: E402,F401
from test_web import EDGE, _playwright  # noqa: E402

pytestmark = pytest.mark.skipif(not os.path.exists(EDGE) or not _playwright(),
                                reason="needs Microsoft Edge and Playwright (group ui)")
SHARE_TOKEN = "AbCdEf0123456789-share_token-view3cXYZ01"  # a share link's token (token_urlsafe's alphabet)
FLAG = "try { localStorage.setItem('findaline.view', 'b'); } catch (e) {}"
ACTIONS = "() => [...document.querySelectorAll('.c-result-top .r-actions button')].map((b) => b.textContent.trim() || b.getAttribute('aria-label'))"


@pytest.fixture
def public_site(tmp_path, view_clip, account_settings):
    """The public app over a data folder with the view's clip run as A's run, shared by a link and a demo run; yields
    (the site's address, {person: session cookie})."""
    import uvicorn

    import accounts as ac
    import web
    from jobs import Jobs
    from settings import PublicSettings
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    site = f"http://localhost:{port}"
    data = tmp_path / "data"
    data.mkdir()
    copy_clip(view_clip, data, RUN_A, "A's run")
    jobs = Jobs(str(data))
    cookies = {}
    for who in ("a", "b"):
        user_id, cookie, _ = session_of(data, account_settings, who)
        cookies[who] = cookie
        if who == "a":
            jobs.add_run(RUN_A, user_id, 1)
    jobs.set_share(RUN_A, ac.digest(SHARE_TOKEN))
    jobs.set_visibility(RUN_A, "demo")
    settings = PublicSettings(public_url=site, trusted_proxy="127.0.0.1", contact="admin@example.org")
    app = web.create_app(str(data), public=settings, accounts=account_settings)

    from fastapi.responses import RedirectResponse

    @app.get("/test-sign-in/{who}")
    def sign_in(who: str):  # the session's cookie as the sign-in sets it (a browser takes no __Host- cookie from a script)
        response = RedirectResponse("/", 302)
        response.set_cookie(ac.SESSION_COOKIE, cookies[who], secure=True, httponly=True, path="/", samesite="lax")
        return response
    server =uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 30
        while not server.started:
            assert time.monotonic() < deadline, "the server did not start"
            time.sleep(0.05)
        yield site, cookies
    finally:
        server.should_exit = True
        thread.join(10)


def _actions(browser, site: str, path: str, who: str | None = None) -> list:
    """The view's header actions on a page of the site (the view's flag set; signed in as `who`), once the page has
    asked all it asks."""
    context = browser.new_context(**DESKTOP)
    try:
        context.add_init_script(FLAG)
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        if who:
            page.goto(f"{site}/test-sign-in/{who}")
            assert any(c["name"].startswith("__Host-") for c in context.cookies()), "not signed in"
        page.goto(site + path)
        page.wait_for_function("() => !!window.FINDALINE_VIEW && !!document.querySelector('.c-result-top .r-actions')", timeout=WAIT)
        page.wait_for_load_state("networkidle", timeout=WAIT)  # the list of runs answered (Share's owner check)
        got = page.evaluate(ACTIONS)
        assert errors == [], errors
        return got
    finally:
        context.close()


# the app's job list answered with a finished job of A's run (AppC's editJob: "Edit & run again" in the pill)
JOBS = """
const realFetchOfJobs = window.fetch;
window.fetch = (url, init) => String(url).replace(/^https?:\\/\\/[^/]+/, '').split('?')[0] !== '/api/jobs' || (init && init.method && init.method !== 'GET')
  ? realFetchOfJobs(url, init)
  : Promise.resolve(new Response(JSON.stringify({jobs: [{id: 'job-1', status: 'done', run_id: '%s', name: "A's run",
      created: '2026-10-01T10:00:00', finished: '2026-10-01T10:05:00', own: true}], seq: 1, worker: true}), {headers: {'content-type': 'application/json'}}));
""" % RUN_A


def _kit_icon(name: str) -> str:
    """The kit's icon's markup (viewer/src/ui/icons.tsx ICONS), as written there."""
    import re
    with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "viewer", "src", "ui", "icons.tsx"),
              encoding="utf-8") as f:
        return re.search(r"\n  %s: '([^']*)'" % name, f.read()).group(1)


@pytest.mark.parametrize("size", [(390, 664), (412, 839)], ids=["390", "412"])
def test_owner_phone_pill(public_site, size):
    """The owner's phone pill with "Edit & run again" and the run's three actions: the run's name keeps 133 px or more
    (the second design review's N2: 118 px, the mock-up 150), Edit is the kit's "refresh" icon (polish 12), the icons
    are 44 px targets, and Share's menu opens on the screen, under the whole pill (fix round 1)."""
    from playwright.sync_api import sync_playwright
    site, _ = public_site
    phone = {"viewport": {"width": size[0], "height": size[1]}, "device_scale_factor": 3, "is_mobile": True, "has_touch": True}
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        context = browser.new_context(**phone)
        try:
            context.add_init_script(FLAG + JOBS)
            page = context.new_page()
            page.goto(f"{site}/test-sign-in/a")
            page.goto(f"{site}/?ui=c#run={RUN_A}")
            page.wait_for_selector(".c-pill [aria-label='Share']", timeout=WAIT)
            page.wait_for_selector(".c-pill a[aria-label='Edit & run again']", timeout=WAIT)
            pill = page.evaluate("""() => { const r = (s) => document.querySelector(s).getBoundingClientRect();
                const svg = document.querySelector(".c-pill a[aria-label='Edit & run again'] svg");
                return {name: Math.round(r('.c-pill-name').width), names: [...document.querySelectorAll('.c-pill a, .c-pill button')].map((b) => b.getAttribute('aria-label')),
                        icons: [...document.querySelectorAll('.c-pill .r-actions button, .c-pill a')].map((b) => Math.round(Math.min(b.getBoundingClientRect().width, b.getBoundingClientRect().height))),
                        edit: svg.innerHTML}; }""")
            page.tap(".c-pill [aria-label='Share']")
            page.wait_for_selector(".r-share", timeout=WAIT)
            menu = page.evaluate("() => { const m = document.querySelector('.c-pill .r-pop').getBoundingClientRect(), p = document.querySelector('.c-pill').getBoundingClientRect(); "
                                 "return [Math.round(m.left), Math.round(m.right), Math.round(p.left), Math.round(p.right), innerWidth]; }")
        finally:
            context.close()
            browser.close()
    import re
    refresh = re.search(r'd="([^"]+)"', _kit_icon("refresh")).group(1)  # the kit's "refresh" by its path
    assert pill["names"][-4:] == ["Edit & run again", "Measure", "Share", "Download"], pill
    assert pill["name"] >= 133 and min(pill["icons"]) >= 44, pill
    assert f'd="{refresh}"' in pill["edit"], (refresh, pill["edit"])
    assert menu[0] >= 0 and menu[1] <= menu[4] and menu[:2] == menu[2:4], menu


def test_who_sees_which_actions_in_the_view(public_site):
    """The owner: Share and Download; another user on the owner's demo run: no Share; a visitor on the demo run's
    map.html and anyone on the share link's page: no Share, no Download."""
    from playwright.sync_api import sync_playwright
    site, _ = public_site
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            owner = _actions(browser, site, f"/?ui=c#run={RUN_A}", "a")
            other = _actions(browser, site, f"/?ui=c#run={RUN_A}", "b")
            visitor = _actions(browser, site, f"/runs/{RUN_A}/map.html")
            shared = _actions(browser, site, f"/s/{SHARE_TOKEN}/map.html")
        finally:
            browser.close()
    assert owner == ["Measure", "Compare", "Share", "Download"], owner
    assert "Share" not in other and "Compare" in other, other
    for got in (visitor, shared):  # (the view's header drawn: _actions waits for its actions' bar)
        assert "Share" not in got and "Download" not in got, got
