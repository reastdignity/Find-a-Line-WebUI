"""A result page that cannot load (line volume's round 7, extra A6; map/main.tsx LoadedMap, result/view/RunLoading.tsx,
the last function of result/view/ResultColumns.tsx, result/load.ts failureOf): a run's own map.html shows the Back
button "Find-a-Line" while the run loads and when it failed, leading to "/" (the app when signed in, the sign-in page
for a visitor), never to the run in the app; a store that could not be loaded says "This result could not be
loaded." with "Try again", which loads it again in the page and, failing again, puts the focus back on the button; a
store too large for the browser or made by a newer Find-a-Line has no "Try again". A share link's visitor has no
Back: "Try again" and a sentence what else to do. The app's own page keeps its Back "Home" and gets "Try again" too.

Playwright's Edge over the public app on a thread (test_rename_home_page's `rename_site`), offline; the store's
lines.arrow answered by a route (held: still loading; 500: could not be loaded; the bytes of a store of the next
format: newer) or an init script (an XHR body the browser could not hold: too large). Run from PowerShell
(.claude/rules/browser-tests.md). A map.html opened from disk is test_disk_notice's."""

import html
import json
import os
import re
import sys
import urllib.parse

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

pytest.importorskip("httpx2")

from test_rename_home_page import (NAME_A, RUN_A, SHARE_TOKEN, WORDS, Browser, card, rename_site,  # noqa: E402,F401
                                   the_held)
from test_public import account_settings  # noqa: E402,F401
from test_shell_c_view_map import DESKTOP, SMALL_PHONE, view_clip  # noqa: E402,F401
from test_shell_c_view_map import WAIT as VIEW_WAIT  # noqa: E402
from test_web import EDGE, _playwright  # noqa: E402

pytestmark = pytest.mark.skipif(not os.path.exists(EDGE) or not _playwright(),
                                reason="needs Microsoft Edge and Playwright (group ui)")
# The deadline of every wait for the page, ms (FINDALINE_FAILED_PAGE_WAIT lowers it for a run against a page without
# the change, where many waits run out)
WAIT = int(os.environ.get("FINDALINE_FAILED_PAGE_WAIT", VIEW_WAIT))
# RUN_A's store's first file: its own map.html's and the app's, the share link's
STORE = re.compile(r"/(%s|%s)/lines\.arrow$" % (re.escape(RUN_A), re.escape(SHARE_TOKEN)))
OLD_WORDS = "Reload the page to try again."  # ui.result.store_failed's second sentence before A6

# lines.arrow's XHR answered with a null body although its bytes came (an ArrayBuffer the browser could not
# allocate: result/load.ts TooLarge), as test_shell_c.TOO_LARGE_STUBS without its other stubs
TOO_LARGE = r"""
const realOpenOfStore = XMLHttpRequest.prototype.open;
const realResponseOfStore = Object.getOwnPropertyDescriptor(XMLHttpRequest.prototype, "response");
XMLHttpRequest.prototype.open = function (method, url) { this.lines = /lines\.arrow$/.test(String(url)); return realOpenOfStore.apply(this, arguments); };
Object.defineProperty(XMLHttpRequest.prototype, "response",
                      {configurable: true, get() { return this.lines ? null : realResponseOfStore.get.call(this); }});
"""

# What the page shows while the run loads or failed: whether the box's first element is Back, Back's words, the
# sentence and its role, "Try again", the second sentence, the loading bar, the controls in the box, the focus on
# "Try again", the old words anywhere on the page
BOX = """() => { const box = document.querySelector('.c-result-wait'); if (!box) return null;
  const one = (sel) => box.querySelector(sel), words = (sel) => one(sel) ? one(sel).textContent.trim() : null;
  return {first: box.firstElementChild ? box.firstElementChild.classList.contains('c-back') : false,
          back: words('.c-back'), error: words('p.c-error'), alert: one('p.c-error') ? one('p.c-error').getAttribute('role') : null,
          retry: words('.c-retry'), more: words('.c-wait-more'), loading: !!one('.c-loading'),
          controls: box.querySelectorAll('button, a[href], input, select, textarea').length,
          focus: !!document.activeElement && document.activeElement === one('.c-retry'),
          old: document.body.innerText.includes(%s)}; }""" % json.dumps(OLD_WORDS)
FAILED = ".c-result-wait p.c-error"
SHOWN = "() => !!window.FINDALINE_VIEW && !!document.querySelector('.c-result-top .c-run-name')"
HEAD_NAME = "() => document.querySelector('.c-result-top .c-run-name').textContent"
COULD_NOT = "This result could not be loaded."
TOO_LARGE_WORDS = "This result is too large for this browser."
NEWER_WORDS = "This result was made by a newer Find-a-Line. Update Find-a-Line to open it."
ASK = "If it still does not open, ask the person who sent you the link."


class Store:
    """The answers to a page's lines.arrow (Playwright's route): "hold" keeps the request unanswered in `held` (the
    run still loads), "fail" answers 500, "newer" answers the bytes of a store of the next format (`newer`), "pass"
    lets the real file through; `asked` counts the requests."""

    def __init__(self, mode: str, newer: bytes = b""):
        self.mode, self.newer, self.held, self.asked = mode, newer, [], 0

    def __call__(self, route):
        self.asked += 1
        if self.mode == "hold":
            self.held.append(route)
        elif self.mode == "fail":
            route.fulfill(status=500, content_type="text/plain", body="made-up failure")
        elif self.mode == "newer":
            route.fulfill(status=200, content_type="application/vnd.apache.arrow.file", body=self.newer)
        else:
            route.continue_()


@pytest.fixture
def named_site(rename_site):
    """rename_site with RUN_A's map.html titled by its name, as a run saved or renamed under it has it (runs.rename_run
    to the name run.json holds: the fixture's copies keep the clip's title); (the site's address, the data folder)."""
    import runs as rn
    site, data = rename_site
    rn.rename_run(str(data / "runs"), RUN_A, NAME_A)
    assert f"<title>{html.escape(NAME_A)} - Find-a-Line</title>" in (data / "runs" / RUN_A / "map.html").read_text("utf-8")
    return site, data


def newer_store(data, tmp_path) -> bytes:
    """RUN_A's lines.arrow with its metadata saying the next format (linestore.FORMAT + 1): a store made by a newer
    Find-a-Line, as test_viewer.test_store_of_a_newer_format_is_refused writes one."""
    import pyarrow as pa
    import linestore
    with pa.OSFile(str(data / "runs" / RUN_A / "lines.arrow"), "rb") as f:
        table = pa.ipc.open_file(f).read_all()
    meta = json.loads(table.schema.metadata[linestore.META_KEY])
    meta["format"] = linestore.FORMAT + 1
    path = tmp_path / "newer-lines.arrow"
    linestore._write_file(str(path), table.replace_schema_metadata({linestore.META_KEY: json.dumps(meta).encode("utf-8")}))
    return path.read_bytes()


def opened(browser, url: str, store: Store | None, who: str | None = "a", device: dict = DESKTOP, script: str = ""):
    """A page of `url` (signed in as `who`, None: a visitor) whose RUN_A's lines.arrow `store` answers (None: as
    served)."""
    page = browser.page(device, who, script)
    page.set_default_timeout(WAIT)
    if who:
        page.goto("about:blank")  # Home of the sign-in ends here: the route sees no request of its mini maps
    if store:
        page.route(STORE, store)
    page.goto(url)
    return page


def own_map(site: str) -> str:
    return f"{site}/runs/{RUN_A}/map.html"


def shared_map(site: str) -> str:
    return f"{site}/s/{SHARE_TOKEN}/map.html"


def app_page(site: str) -> str:
    return f"{site}/?ui=c#run={RUN_A}"


def back_to_the_start(page, site: str, store: Store) -> dict:
    """Back pressed on a run's map.html (the store's later requests let through: Home's mini maps as served; a held
    one stays unanswered, as an unroute would let it through and the run would show): where the browser went (the
    URL, its path) and what "/" answered there (the app's page has the session's token, the sign-in page its own
    main)."""
    store.mode = "pass"
    page.click(".c-result-wait .c-back")
    page.wait_for_url(lambda url: urllib.parse.urlsplit(url).path == "/")
    page.wait_for_load_state()
    return {"url": page.url, "path": urllib.parse.urlsplit(page.url).path, "site": page.url.startswith(site + "/"),
            "app": page.evaluate("() => !!document.querySelector('meta[name=findaline-token]')"),
            "signin": page.evaluate("() => !!document.querySelector('main.p-signin')")}


def test_own_map_while_it_loads(named_site):
    """A run's own map.html while its store still loads, for its owner and for a visitor (a demo run): the Back button
    "Find-a-Line" (the catalogue's ui.map.back) first in the box and the loading bar. Back leads to the site's "/",
    never to the run in the app (no #run=): the app's Home for the owner (its cards drawn), the sign-in page for the
    visitor (the server answers "/" with it, no redirect)."""
    site, _ = named_site
    found = {}
    with Browser(site) as browser:
        for who in ("a", None):
            store = Store("hold")
            page = opened(browser, own_map(site), store, who=who)
            the_held(page, store.held)
            loading = page.evaluate(BOX)
            went = back_to_the_start(page, site, store)
            if who:
                page.wait_for_selector(card(RUN_A))  # Home with the run's card
            found[who or "visitor"] = (loading, went)
    for who, (loading, went) in found.items():
        assert loading is not None and loading["back"] == "Find-a-Line" and loading["first"], (who, loading)
        assert loading["loading"] and loading["error"] is None and loading["retry"] is None, (who, loading)
        assert went["path"] == "/" and went["site"] and "run=" not in went["url"], (who, went)
    assert found["a"][1]["app"] and not found["a"][1]["signin"], found["a"]
    assert found["visitor"][1]["signin"] and not found["visitor"][1]["app"], found["visitor"]
    assert WORDS["ui.map.back"] == "Find-a-Line"


def test_own_map_that_could_not_be_loaded(named_site):
    """A run's own map.html whose store could not be loaded (a 500): the Back button "Find-a-Line" first in the box,
    the sentence "This result could not be loaded." (the catalogue's ui.result.store_failed, announced: role alert),
    the button "Try again"; no second sentence, and the words "Reload the page to try again." nowhere on the page. Back
    leads to the app's "/" (Home), not to the run in the app."""
    site, _ = named_site
    with Browser(site) as browser:
        store = Store("fail")
        page = opened(browser, own_map(site), store)
        page.wait_for_selector(FAILED)
        failed = page.evaluate(BOX)
        went = back_to_the_start(page, site, store)
        page.wait_for_selector(card(RUN_A))
    assert failed["first"] and failed["back"] == "Find-a-Line", failed
    assert failed["error"] == COULD_NOT and failed["alert"] == "alert", failed
    assert failed["retry"] == "Try again" and failed["more"] is None and not failed["loading"], failed
    assert not failed["old"], failed
    assert went["path"] == "/" and "run=" not in went["url"] and went["app"], went
    assert WORDS["ui.result.store_failed"] == COULD_NOT and WORDS["ui.actions.try_again"] == "Try again"


def test_try_again_loads_the_store_in_the_page(named_site):
    """"Try again" on a run's own map.html loads the store again in the page (no new document: a mark set on the
    window stays): while it loads the button is gone and the loading bar shows under Back; a try that fails too
    shows the sentence and the button again with the focus on the button; a try that gets the file shows the run,
    its name (map.html's title: run.json's name) in the head. Each try asks for lines.arrow once."""
    site, _ = named_site
    with Browser(site) as browser:
        store = Store("fail")
        page = opened(browser, own_map(site), store)
        page.wait_for_selector(".c-result-wait .c-retry")
        first = page.evaluate(BOX)
        page.evaluate("() => { window.SAME_PAGE = true; }")
        store.mode = "hold"
        page.click(".c-result-wait .c-retry")
        held = the_held(page, store.held)
        page.wait_for_selector(".c-result-wait .c-loading")
        again = page.evaluate(BOX)
        held.fulfill(status=500, content_type="text/plain", body="made-up failure")
        page.wait_for_selector(".c-result-wait .c-retry")
        page.wait_for_function("() => document.activeElement === document.querySelector('.c-result-wait .c-retry')")
        failed_again = page.evaluate(BOX)
        store.mode = "pass"
        page.click(".c-result-wait .c-retry")
        page.wait_for_function(SHOWN)
        name = page.evaluate(HEAD_NAME)
        same = page.evaluate("() => window.SAME_PAGE === true")
        asked = store.asked
    assert first["retry"] == "Try again" and not first["focus"], first
    assert again["retry"] is None and again["error"] is None and again["loading"] and again["back"] == "Find-a-Line", again
    assert not again["focus"], again
    assert failed_again["error"] == COULD_NOT and failed_again["retry"] == "Try again", failed_again
    assert failed_again["focus"] and failed_again["back"] == "Find-a-Line", failed_again
    assert same, "the page was loaded again"
    assert name == NAME_A, name
    assert asked == 3, asked


def test_own_map_too_large_or_newer(named_site, tmp_path):
    """A run's own map.html whose store the browser cannot hold ("This result is too large for this browser.") or
    whose store was made by a newer Find-a-Line (lines.arrow of the next format: ui.result.newer_store's words): the
    Back button "Find-a-Line" and the sentence, no "Try again" (a new try cannot help), no second sentence."""
    site, data = named_site
    newer = newer_store(data, tmp_path)
    with Browser(site) as browser:
        page = opened(browser, own_map(site), None, script=TOO_LARGE)
        page.wait_for_selector(FAILED)
        large = page.evaluate(BOX)
        page = opened(browser, own_map(site), Store("newer", newer))
        page.wait_for_selector(FAILED)
        late = page.evaluate(BOX)
    for got, words in ((large, TOO_LARGE_WORDS), (late, NEWER_WORDS)):
        assert got["error"] == words and got["alert"] == "alert", got
        assert got["first"] and got["back"] == "Find-a-Line", got
        assert got["retry"] is None and got["more"] is None and got["controls"] == 1, got  # the Back button alone
    assert WORDS["ui.result.too_large"] == TOO_LARGE_WORDS and WORDS["ui.result.newer_store"] == NEWER_WORDS


def test_share_link_page(named_site):
    """A share link's page (/s/<token>/map.html) for a visitor: no Back while the run loads (the loading bar alone)
    nor when it failed. Could not be loaded: the sentence, "Try again" and the second sentence "If it still does not
    open, ask the person who sent you the link." (ui.result.store_failed_shared); "Try again" loads the store again in
    the page and shows the run, its name the page's title's (run.json's, not the store's head's). Too large: the
    sentence alone, no control at all."""
    site, _ = named_site
    with Browser(site) as browser:
        store = Store("hold")
        page = opened(browser, shared_map(site), store, who=None)
        the_held(page, store.held)
        loading = page.evaluate(BOX)
        store = Store("fail")
        page = opened(browser, shared_map(site), store, who=None)
        page.wait_for_selector(FAILED)
        failed = page.evaluate(BOX)
        page.evaluate("() => { window.SAME_PAGE = true; }")
        store.mode = "pass"
        page.click(".c-result-wait .c-retry")
        page.wait_for_function(SHOWN)
        name = page.evaluate(HEAD_NAME)
        same = page.evaluate("() => window.SAME_PAGE === true")
        page = opened(browser, shared_map(site), None, who=None, script=TOO_LARGE)
        page.wait_for_selector(FAILED)
        large = page.evaluate(BOX)
    assert loading["back"] is None and loading["loading"] and loading["controls"] == 0, loading
    assert failed["back"] is None and failed["error"] == COULD_NOT and failed["alert"] == "alert", failed
    assert failed["retry"] == "Try again" and failed["controls"] == 1 and failed["more"] == ASK, failed
    assert not failed["old"], failed
    assert same and name == NAME_A, (same, name)
    assert large["error"] == TOO_LARGE_WORDS and large["controls"] == 0, large
    assert large["back"] is None and large["retry"] is None and large["more"] is None, large
    assert WORDS["ui.result.store_failed_shared"] == ASK


def test_app_page_back_and_try_again(named_site):
    """The app's own result page (?ui=c#run=<id>) as before with its Back "Home" (ui.app.home) while the run loads;
    a store that could not be loaded: Back "Home", "This result could not be loaded." and "Try again", which loads it
    again in the page (the view shown once the file comes through); Back leads to Home (#home, the cards drawn). Too
    large: Back "Home" and the sentence, no "Try again"."""
    site, _ = named_site
    with Browser(site) as browser:
        store = Store("hold")
        page = opened(browser, app_page(site), store)
        held = the_held(page, store.held)
        loading = page.evaluate(BOX)
        held.fulfill(status=500, content_type="text/plain", body="made-up failure")
        page.wait_for_selector(FAILED)
        failed = page.evaluate(BOX)
        page.evaluate("() => { window.SAME_PAGE = true; }")
        store.mode = "pass"
        page.click(".c-result-wait .c-retry")
        page.wait_for_function("() => !!window.FINDALINE_VIEW")
        same = page.evaluate("() => window.SAME_PAGE === true")
        store = Store("fail")
        page = opened(browser, app_page(site), store)
        page.wait_for_selector(FAILED)
        store.mode = "pass"  # Home's mini maps as served
        page.click(".c-result-wait .c-back")
        page.wait_for_function("() => location.hash === '#home'")
        page.wait_for_selector(card(RUN_A))
        home = urllib.parse.urlsplit(page.url)
        page = opened(browser, app_page(site), None, script=TOO_LARGE)
        page.wait_for_selector(FAILED)
        large = page.evaluate(BOX)
    assert loading["back"] == "Home" and loading["first"] and loading["loading"], loading
    assert failed["back"] == "Home" and failed["first"] and failed["error"] == COULD_NOT, failed
    assert failed["retry"] == "Try again" and failed["more"] is None and not failed["old"], failed
    assert same, "the page was loaded again"
    assert home.path == "/" and home.fragment == "home", home
    assert large["back"] == "Home" and large["error"] == TOO_LARGE_WORDS, large
    assert large["retry"] is None and large["more"] is None, large
    assert WORDS["ui.app.home"] == "Home"


def test_failed_page_on_a_small_phone(named_site):
    """On a 390 by 664 phone a run's own map.html that could not be loaded keeps its controls large enough to touch
    (Back and "Try again" at least 44 px high) and inside the screen: nothing in the box reaches past either edge, and
    the page scrolls no way sideways."""
    site, _ = named_site
    with Browser(site) as browser:
        page = opened(browser, own_map(site), Store("fail"), device=SMALL_PHONE)
        page.wait_for_selector(".c-result-wait .c-retry")
        sizes = page.evaluate("""() => { const box = document.querySelector('.c-result-wait'),
          high = (sel) => Math.round(box.querySelector(sel).getBoundingClientRect().height);
          return {back: high('.c-back'), retry: high('.c-retry'), scroll: document.documentElement.scrollWidth, width: innerWidth,
                  outside: [box, ...box.querySelectorAll('*')].filter((e) => { const r = e.getBoundingClientRect();
                    return Math.round(r.left) < 0 || Math.round(r.right) > innerWidth; }).map((e) => e.getAttribute('class') || e.tagName)}; }""")
    assert sizes["back"] >= 44 and sizes["retry"] >= 44, sizes
    assert sizes["outside"] == [] and sizes["scroll"] <= sizes["width"], sizes
