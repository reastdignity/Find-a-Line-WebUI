"""The result view's scrollers scroll on the browser's scrolling thread (gate 2, the user's iPhone of 2026-11-22: the
phone's sheet scrolled at 1-3 fps on a spot with 420 tree rows, today's page fluid; the user's variants named the rows'
`position: relative` as the cause and a layer of the sheet's body as a cure). iOS WebKit's scrolling thread cannot be
measured here (headless WebKit on Windows has none), so the tests check what makes it possible, as built: the view's
scrollers have a layer of their own (computed `will-change: transform`; today's page, which shares the kit's sheet, is
left as it is). Playwright's WebKit with the iPhone 13 profile and Edge with a phone's, over the app's server, offline,
on the result view's clip run. Every wait is an event with a deadline. Run from PowerShell
(.claude/rules/browser-tests.md)."""

import os
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_shell_c import BIG  # noqa: E402
from test_shell_c_view_map import PHONE, WAIT, _open, site, view_clip  # noqa: E402,F401
from test_view_details import SCRIPT, _select, _sheet, _view  # noqa: E402
from test_web import EDGE, _playwright  # noqa: E402

pytestmark = pytest.mark.skipif(not os.path.exists(EDGE) or not _playwright(),
                                reason="needs Microsoft Edge and Playwright (group ui)")
ENGINES = ["webkit", "chromium"]


def _browser(p, engine):
    if engine == "webkit":
        if not os.path.exists(p.webkit.executable_path):
            pytest.skip("Playwright's webkit is not installed")
        # the offline proxy of the tests' environment would also take WebKit's requests to the server
        return p.webkit.launch(env={k: v for k, v in os.environ.items() if k not in ("HTTP_PROXY", "HTTPS_PROXY")})
    return p.chromium.launch(channel="msedge", headless=True)


def _phone(p, engine):
    return {k: v for k, v in p.devices["iPhone 13"].items() if k != "default_browser_type"} if engine == "webkit" else PHONE


@pytest.mark.parametrize("engine", ENGINES)
def test_the_phone_sheet_has_its_own_layer(site, engine):
    """A phone: the view's sheet body (its scroller: the details and the list) computes `will-change: transform`, at
    the sheet's full stop with a spot selected; today's page's sheet body (the kit's) stays `auto`."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = _browser(p, engine)
        try:
            page = _open(browser, f"{site}#run={BIG}", _phone(p, engine), script=SCRIPT)
            _view(page)
            _select(page)
            _sheet(page, "full")
            assert page.evaluate("() => getComputedStyle(document.querySelector('.v-result .u-sheet-body')).willChange") == "transform"
            page.context.close()
            page = _open(browser, f"{site}#run={BIG}", _phone(p, engine), flag=False)
            page.wait_for_function("() => !!window.FINDALINE_RESULT && !!document.querySelector('.u-sheet-body')", timeout=WAIT)
            assert page.evaluate("() => !document.querySelector('.v-result')")
            assert page.evaluate("() => getComputedStyle(document.querySelector('.u-sheet-body')).willChange") == "auto"
        finally:
            browser.close()


@pytest.mark.parametrize("engine", ENGINES)
def test_the_desktop_columns_have_their_own_layer(site, engine):
    """A desktop (Safari on a Mac also scrolls on its own thread): the view's list body and details body compute
    `will-change: transform`; today's page's columns stay `auto`."""
    from playwright.sync_api import sync_playwright
    from test_shell_c_view_map import DESKTOP
    with sync_playwright() as p:
        browser = _browser(p, engine)
        try:
            page = _open(browser, f"{site}#run={BIG}", DESKTOP, script=SCRIPT)
            _view(page)
            _select(page)
            layers = page.evaluate("""() => ['.v-result .c-col-body', '.v-result .c-col-dbody'].map((s) => {
              const e = document.querySelector(s); return e && [getComputedStyle(e).overflowY, getComputedStyle(e).willChange]; })""")
            assert layers == [["auto", "transform"], ["auto", "transform"]], layers
            page.context.close()
            page = _open(browser, f"{site}#run={BIG}", DESKTOP, flag=False)
            page.wait_for_function("() => !!window.FINDALINE_RESULT && !!document.querySelector('.c-col-body')", timeout=WAIT)
            today = page.evaluate("() => [...document.querySelectorAll('.c-col-body, .c-col-dbody')].map((e) => getComputedStyle(e).willChange)")
            assert today and set(today) == {"auto"}, today
        finally:
            browser.close()


# The rows of a scroller: their computed position, and whether each row's hidden names (u-sr, absolute) lie inside
# the row after the scroller moved (their containing block scrolls with them)
ROWS = r"""async (sel) => { const box = document.querySelector(sel); box.scrollTop = 0;
  await new Promise((ok) => requestAnimationFrame(() => requestAnimationFrame(ok)));
  box.scrollTop = Math.min(300, box.scrollHeight - box.clientHeight);
  await new Promise((ok) => requestAnimationFrame(() => requestAnimationFrame(ok)));
  const rows = [...box.querySelectorAll('.vl-rows > li .vl-main')].filter((r) => { const b = r.getBoundingClientRect(); return b.height > 0; });
  const out = {scrolled: box.scrollTop, rows: rows.length, positions: [...new Set(rows.map((r) => getComputedStyle(r).position))], outside: 0, names: 0};
  for (const r of rows) { const b = r.getBoundingClientRect();
    for (const s of r.querySelectorAll('.u-sr')) { out.names++; const c = s.getBoundingClientRect();
      if (c.top < b.top - 1 || c.bottom > b.bottom + 1) out.outside++; } }
  return out; }"""


@pytest.mark.parametrize("engine", ENGINES)
def test_the_rows_are_not_positioned(site, engine):
    """The rows (`.vl-main`) are not positioned (the user's variant 3: hundreds of positioned rows made iOS WebKit
    scroll the sheet on the main thread), in a phone's sheet and the desktop's list; each row's hidden names (u-sr,
    absolute) still lie inside their row once the scroller moved 300 px (their containing block is the scroller's
    layer, so they scroll with the rows)."""
    from playwright.sync_api import sync_playwright
    from test_shell_c_view_map import DESKTOP
    with sync_playwright() as p:
        browser = _browser(p, engine)
        try:
            for context, scroller in ((_phone(p, engine), ".v-result .u-sheet-body"), (DESKTOP, ".v-result .c-col-list .vl-body")):
                page = _open(browser, f"{site}#run={BIG}", context, script=SCRIPT)
                _view(page)
                _select(page)
                if context is not DESKTOP:
                    _sheet(page, "full")
                got = page.evaluate(ROWS, scroller)
                assert got["scrolled"] > 0 and got["rows"] > 5 and got["names"] > 5, (scroller, got)
                assert got["positions"] == ["static"] and got["outside"] == 0, (scroller, got)
                page.context.close()
        finally:
            browser.close()
