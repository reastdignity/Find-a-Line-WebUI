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
# ends), the page reading hidden first when CUT is "hidden"; with HOLD the next one waits for RELEASE(); with
# HANG_PROFILES the first profiles.arrow request is never answered (as iOS may leave a suspended request), with
# HANG_RETRY neither of the second try's two
STUBS = r"""
window.VIS = 'visible'; window.STORE_ASKED = 0; window.PROFILES_ASKED = 0; window.HELD = null;
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
  if (/\/profiles\.arrow$/.test(this.storeUrl || '')) {
    window.PROFILES_ASKED++;
    if (window.HANG_PROFILES && window.PROFILES_ASKED === 1) return;
    if (window.HANG_RETRY && window.PROFILES_ASKED === 2) return;
  }
  if (window.HANG_RETRY && window.STORE_ASKED === 2 && /\/lines\.arrow$/.test(this.storeUrl || '')) return;
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


def test_a_hanging_request_never_keeps_the_page_waiting(site):
    """The cut while hidden leaves the store's other request hanging (profiles.arrow never answered): once visible the
    whole store is asked again at once and the run is shown (the hanging request is ended, not waited for)."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _open(browser, f"{site}#run={BIG}", DESKTOP, flag=None,
                         script=STUBS + "window.CUT = 'hidden'; window.HANG_PROFILES = true; "
                         "try { localStorage.setItem('findaline.view', 'b'); } catch (e) {}")
            page.wait_for_function("() => window.STORE_ASKED === 1 && window.PROFILES_ASKED === 1 && window.VIS === 'hidden'", timeout=WAIT)
            page.evaluate(FRAMES)
            assert page.evaluate(WAITING)
            page.evaluate("() => setVisibility('visible')")
            page.wait_for_function(SHOWN["view"], timeout=WAIT)
            assert page.evaluate("() => [window.STORE_ASKED, window.PROFILES_ASKED]") == [2, 2]
            assert FAILED not in page.evaluate("() => document.body.innerText") and page.errors == []
        finally:
            browser.close()


def test_a_hanging_retry_ends_in_the_message(site):
    """The try after a cut hangs itself (neither file answered): after load.ts STALL_MS (30 s) without an answer or a
    byte while visible, today's message, never a spinner for ever; at 20 s still waiting (the page's clock run on by
    Playwright's fake one, installed once the page was hidden)."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _open(browser, f"{site}#run={BIG}", DESKTOP, flag=None,
                         script=STUBS + "window.CUT = 'hidden'; window.HANG_RETRY = true; "
                         "try { localStorage.setItem('findaline.view', 'b'); } catch (e) {}")
            page.wait_for_function("() => window.STORE_ASKED === 1 && window.PROFILES_ASKED === 1 && window.VIS === 'hidden'", timeout=WAIT)
            page.clock.install()
            page.evaluate("() => setVisibility('visible')")
            page.wait_for_function("() => window.STORE_ASKED === 2 && window.PROFILES_ASKED === 2", timeout=WAIT, polling=100)
            page.clock.run_for(20000)  # within the deadline: still waiting, no message
            assert page.evaluate("() => !document.querySelector('.c-error')")
            page.clock.run_for(12000)  # past STALL_MS, and the page's render after it (its timers are the fake clock's too:
            # a wait that polls the page would wait for that clock)
            assert page.evaluate("() => !!document.querySelector('.c-error')")
            assert page.evaluate("() => document.querySelector('.c-error').textContent") == FAILED
            assert page.evaluate("() => window.STORE_ASKED") == 2
        finally:
            browser.close()
