"""A run's store download cut while the page was hidden is tried again once the page is visible (viewer/src/result/
load.ts downloadStore, shared by the result view and today's page; gate 2's item 5: on the user's iPhone the load
failed when the screen went off and the page said "This result could not be loaded."). The page's visibility and the
store's requests are stubbed (an XMLHttpRequest of lines.arrow fails as iOS fails it, while the page reads hidden):
the page waits with its progress while hidden, starts the whole download again when visible (the progress again), and
shows the run; a failure while the page stays visible shows today's message at once and asks no more. Playwright's
Edge over the app's server, offline, on the result view's clip run. Every wait is an event with a deadline. Run from
PowerShell (.claude/rules/browser-tests.md)."""

import json
import os
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_shell_c import BIG  # noqa: E402
from test_shell_c_view_map import DESKTOP, PHONE, WAIT, _open, site, view_clip  # noqa: E402,F401
from test_web import EDGE, _playwright  # noqa: E402

pytestmark = pytest.mark.skipif(not os.path.exists(EDGE) or not _playwright(),
                                reason="needs Microsoft Edge and Playwright (group ui)")
with open(os.path.join(REPO, "locales", "en.json"), encoding="utf-8") as _f:
    FAILED = json.load(_f)["ui.result.store_failed"]

# The page's visibility as the test sets it (setVisibility: the property and its event), and the run's lines.arrow
# requests counted (STORE_ASKED); with CUT the first one fails (an XHR "error" event, as a suspended page's request
# ends), the page reading hidden first when CUT is "hidden"; with HOLD the next one waits for RELEASE()
STUBS = r"""
window.VIS = 'visible'; window.STORE_ASKED = 0; window.HELD = null;
Object.defineProperty(Document.prototype, 'visibilityState', {configurable: true, get() { return window.VIS; }});
Object.defineProperty(Document.prototype, 'hidden', {configurable: true, get() { return window.VIS === 'hidden'; }});
window.setVisibility = (v) => { window.VIS = v; document.dispatchEvent(new Event('visibilitychange')); };
window.RELEASE = () => { const f = window.HELD; window.HELD = null; if (f) f(); };
const realOpen = XMLHttpRequest.prototype.open, realSend = XMLHttpRequest.prototype.send;
XMLHttpRequest.prototype.open = function (method, url, ...rest) { this.storeUrl = String(url); return realOpen.call(this, method, url, ...rest); };
XMLHttpRequest.prototype.send = function (...args) {
  if (/\/lines\.arrow$/.test(this.storeUrl || '')) {
    window.STORE_ASKED++;
    if (window.CUT && window.STORE_ASKED === 1) {
      if (window.CUT === 'hidden') setVisibility('hidden');
      setTimeout(() => this.dispatchEvent(new ProgressEvent('error')), 0);
      return;
    }
    if (window.HOLD && window.STORE_ASKED === 2) { window.HELD = () => realSend.apply(this, args); return; }
  }
  return realSend.apply(this, args);
};
"""
SHOWN = {"view": "() => !!window.FINDALINE_VIEW", "today": "() => !!window.FINDALINE_RESULT"}
WAITING = "() => !!document.querySelector('.c-loading [role=progressbar]') && !document.querySelector('.c-error')"
FRAMES = "() => new Promise((ok) => requestAnimationFrame(() => requestAnimationFrame(() => setTimeout(ok, 0))))"


@pytest.mark.parametrize("page_kind", ["view", "today"])
@pytest.mark.parametrize("device", [DESKTOP, PHONE], ids=["desktop", "phone"])
def test_a_cut_while_hidden_is_tried_again(site, page_kind, device):
    """Hidden: the store's first request fails; the page shows its progress, no error, and asks nothing more while it
    stays hidden. Visible: the store is asked for again at once, the progress shows while it comes (the request held),
    then the run is shown (the view, or today's page with ?view=today), never the error."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            view = "b" if page_kind == "view" else "today"
            page = _open(browser, f"{site}#run={BIG}", device, flag=None,
                         script=STUBS + f"window.CUT = 'hidden'; window.HOLD = true; "
                         f"try {{ localStorage.setItem('findaline.view', '{view}'); }} catch (e) {{}}")
            page.wait_for_function("() => window.STORE_ASKED === 1 && window.VIS === 'hidden'", timeout=WAIT)
            page.evaluate(FRAMES)
            page.evaluate(FRAMES)
            assert page.evaluate(WAITING), page.evaluate("() => document.body.innerText.slice(0, 300)")
            assert page.evaluate("() => window.STORE_ASKED") == 1
            page.evaluate("() => setVisibility('visible')")
            page.wait_for_function("() => window.STORE_ASKED === 2 && !!window.HELD", timeout=WAIT)
            page.evaluate(FRAMES)
            assert page.evaluate(WAITING)  # the progress again while the store comes
            page.evaluate("() => RELEASE()")
            page.wait_for_function(SHOWN[page_kind], timeout=WAIT)
            assert FAILED not in page.evaluate("() => document.body.innerText")
            assert page.evaluate("() => window.STORE_ASKED") == 2 and page.errors == []
        finally:
            browser.close()


@pytest.mark.parametrize("page_kind", ["view", "today"])
def test_a_failure_while_visible_shows_the_error(site, page_kind):
    """The store's request fails while the page is visible: today's message at once (the page's alert), and the store
    is not asked for again."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            view = "b" if page_kind == "view" else "today"
            page = _open(browser, f"{site}#run={BIG}", DESKTOP, flag=None,
                         script=STUBS + f"window.CUT = 'visible'; try {{ localStorage.setItem('findaline.view', '{view}'); }} catch (e) {{}}")
            page.wait_for_selector(".c-error", timeout=WAIT)
            assert page.evaluate("() => document.querySelector('.c-error').textContent") == FAILED
            page.evaluate(FRAMES)
            assert page.evaluate("() => window.STORE_ASKED") == 1
        finally:
            browser.close()
