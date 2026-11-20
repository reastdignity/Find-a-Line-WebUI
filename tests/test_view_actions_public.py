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
