"""Gate 2's findings in the result view (the user's iPhone test of 2026-11-22), guarded: the 3D view's other lines
(`&also=`) never hold a line the filters hide (finding 1, not reproduced: the rule as built, kept by a test), and no
stylesheet or inline style of ours is refused by the app's CSP in WebKit (finding 10: WebKit's own refusal of every
`<select>`, bug 327212, is the one allowed). Playwright over the app's server, offline, on the result view's clip run
(clip_runs.view_clip). Every wait is an event with a deadline. Run from PowerShell (.claude/rules/browser-tests.md)."""

import os
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_shell_c import BIG, copy_clip  # noqa: E402
from test_shell_c_view_map import DESKTOP, PHONE, WAIT, _open, site, view_clip  # noqa: E402,F401
from test_view_details import SCRIPT, _select, _sheet, _view  # noqa: E402
from test_web import EDGE, _playwright, _server  # noqa: E402

pytestmark = pytest.mark.skipif(not os.path.exists(EDGE) or not _playwright(),
                                reason="needs Microsoft Edge and Playwright (group ui)")
OTHERS_MAX = 20  # view3d/page.ts OTHERS_MAX

# The 3D view's link of the selected line read back: its `&also=` keys as rows of the selected spot (each key compared
# with the link of every line of the spot), whether each passes the filters now, its `top`, and whether the map drew
# it as a line of the selected spot (SpotMap's presses' targets of its last full paint: `trow`)
ALSO = r"""() => {
  const v = D.v(), m = D.m(), s = v.selected, top = m.data.view.top, a = document.querySelector('.r-view3d');
  const href = a.getAttribute('href'), at = href.indexOf('&also=');
  const keys = at < 0 ? [] : decodeURIComponent(href.slice(at + 6)).split(';');
  const byKey = new Map(Array.from(v.linesOf(s.spot)).map((r) => [D.link(r), r]));
  const drawn = new Set(window.FINDALINE_VIEW.map.trow);
  const rows = keys.map((k) => byKey.has(k) ? byKey.get(k) : -1);
  return {keys: keys.length, unknown: rows.filter((r) => r < 0).length, hidden: rows.filter((r) => r >= 0 && !v.passes(r)).length,
          top0: rows.filter((r) => r >= 0 && top[r] === 0).length, undrawn: rows.filter((r) => r >= 0 && !drawn.has(r)).length,
          self: rows.includes(s.row), passing: v.passingCount(s.spot), topOnly: v.topOnly};
}"""


def test_3d_view_other_lines_pass_the_filters(site):
    """A guard of the rule as built (gate 2's finding 1 was not reproduced: the planner's item 1, closed as C): the
    3D view's link of a selected line carries as `&also=` only lines of its spot that pass every filter in force now,
    "Top level only" included, never the line itself, at most OTHERS_MAX of the spot's passing lines, each one the map
    draws for the selected spot. A length filter hides most of a spot that has a line of `top` 0 (a window of lengths
    around that line, read from the run's columns: at least three lines of `top` 1 in it, the line of `top` 0 among
    the window's first OTHERS_MAX + 1 in the spot's order); with the chip on no line of `top` 0 and no line outside the
    window is among the others, with it off the line of `top` 0 is."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _open(browser, f"{site}#run={BIG}", DESKTOP, script=SCRIPT)
            _view(page)
            window = page.evaluate("""(max) => { const v = D.v(), top = v.model.data.view.top, len = v.values.len;
              for (let s = 0; s < v.spotCount; s++) {
                const rows = Array.from(v.linesOf(s)), zero = rows.find((r) => top[r] === 0);
                if (zero === undefined) continue;
                // the nearest lengths around the line of top 0, widened until three lines of top 1 are in
                const near = rows.slice().sort((a, b) => Math.abs(len[a] - len[zero]) - Math.abs(len[b] - len[zero]));
                for (let k = 4; k <= near.length; k++) {
                  const lo = Math.min(...near.slice(0, k).map((r) => len[r])) - 0.01, hi = Math.max(...near.slice(0, k).map((r) => len[r])) + 0.01;
                  const inside = rows.filter((r) => len[r] >= lo && len[r] <= hi);
                  if (inside.filter((r) => top[r] === 1).length >= 3 && inside.indexOf(zero) <= max && inside.length < rows.length)
                    return {spot: s, lo, hi, inside: inside.length, lines: rows.length};
                }
              }
              return null; }""", OTHERS_MAX)
            assert window is not None, "the clip has no spot with a line of top 0 that a length window can single out"
            page.evaluate("([lo, hi]) => { const m = D.m(); m.setFilters({...m.filters, lenMin: lo, lenMax: hi}); }",
                          [window["lo"], window["hi"]])
            page.wait_for_function("(s) => D.v().passingCount(s) > 0", arg=window["spot"], timeout=WAIT)
            _select(page, str(window["spot"]))
            page.wait_for_selector(".r-view3d", timeout=WAIT)

            def also():
                page.evaluate("() => T.frames()")
                return page.evaluate(ALSO)
            on = also()
            assert on["topOnly"] and on["keys"] == min(OTHERS_MAX, on["passing"] - 1) >= 2, (on, window)
            assert on["unknown"] == on["hidden"] == on["top0"] == on["undrawn"] == 0 and not on["self"], (on, window)
            assert on["passing"] < window["lines"], (on, window)  # the filter hides some of the spot's lines
            page.evaluate("() => D.v().setTopOnly(false)")
            page.wait_for_function("() => !D.v().topOnly", timeout=WAIT)
            off = also()
            assert off["keys"] == min(OTHERS_MAX, off["passing"] - 1) and off["top0"] > 0, (off, window)
            assert off["unknown"] == off["hidden"] == off["undrawn"] == 0 and not off["self"], (off, window)
            assert off["passing"] == window["inside"], (off, window)  # the window's lines, the line of top 0 now too
            assert page.errors == []
        finally:
            browser.close()


# Every violation of the page's CSP (directive, blocked address, sample) and every <select> made by a script
# (document.createElement / createElementNS): WebKit reports one style-src-attr violation for each <select> made
WATCH = r"""
window.CSPV = []; window.SELECTS = 0;
document.addEventListener('securitypolicyviolation', (e) => CSPV.push([e.effectiveDirective, e.blockedURI, e.sample || '']));
const madeBy = (f) => function (...a) { const e = f.apply(this, a); if (e && e.localName === 'select') SELECTS++; return e; };
Document.prototype.createElement = madeBy(Document.prototype.createElement);
Document.prototype.createElementNS = madeBy(Document.prototype.createElementNS);
"""
BARE = """<!doctype html><html><head><meta charset="utf-8"><title>bare</title></head><body>
<script>window.CSPV = []; document.addEventListener('securitypolicyviolation', (e) => CSPV.push(e.effectiveDirective));</script>
<select><option>One</option></select></body></html>"""


@pytest.fixture
def clip_app(tmp_path, view_clip):
    """The app over a data folder with the view's clip run (BIG); yields its address."""
    folder = tmp_path / "data"
    copy_clip(view_clip, folder, BIG, "Clip")
    with _server(folder) as port:
        yield f"http://127.0.0.1:{port}/"


def test_no_style_refused_in_webkit(clip_app):
    """No stylesheet, <style> or inline style of ours is refused by the app's CSP (style-src 'self') in WebKit on Home
    (a phone and the desktop), a run in the view (both) and today's page (both): gate 2's finding 10, Safari's
    "Refused to apply a stylesheet because its hash, its nonce, or 'unsafe-inline' does not appear in the style-src
    directive". That message is WebKit's own: WebKit bug 327212 ("Creating a select triggers a CSP style-src violation
    from its UA shadow tree", a regression of WebKit's commit 321159: an inline style on the button slot of the
    select's user-agent shadow tree). M's proof (2026-11-22, SESSION/M/explore4c.py): a bare page under style-src
    'self' with one parsed <select>, or one made by a script and never attached, gets exactly one style-src-attr
    violation in Playwright's WebKit, none without the CSP, and the select is drawn pixel for pixel the same; alone on
    the app's Home only a <select> of every form control causes it. So the test allows exactly one style-src-attr
    violation (blocked "inline") per <select> the page made (by a script, or in the served HTML), and only while a bare
    <select> in the same browser is refused too (the engine's bug present); nothing else, and none at all once WebKit
    is fixed."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        if not os.path.exists(p.webkit.executable_path):
            pytest.skip("Playwright's webkit is not installed")
        # the offline proxy of the tests' environment would also take WebKit's requests to the server
        browser = p.webkit.launch(env={k: v for k, v in os.environ.items() if k not in ("HTTP_PROXY", "HTTPS_PROXY")})
        try:
            # the engine's bug: a bare <select> under the same style-src
            probe = browser.new_page()
            probe.route("http://bare.test/", lambda route, _request=None: route.fulfill(
                status=200, body=BARE, headers={"content-type": "text/html",
                                                "content-security-policy": "default-src 'self'; script-src 'unsafe-inline'; style-src 'self'"}))
            probe.goto("http://bare.test/")
            probe.wait_for_function("() => document.readyState === 'complete'", timeout=WAIT)
            probe.evaluate("() => new Promise((ok) => requestAnimationFrame(() => requestAnimationFrame(() => setTimeout(ok, 0))))")
            bug = probe.evaluate("() => CSPV")
            assert bug in ([], ["style-src-attr"]), bug
            probe.close()
            parsed = browser.new_page().request.get(clip_app).text().count("<select")
            phone = {k: v for k, v in p.devices["iPhone 13"].items() if k != "default_browser_type"}
            pages = (("Home", clip_app + "?ui=c", "() => !!document.querySelector('#app > *')"),
                     ("the view", clip_app + f"?ui=c&view=b#run={BIG}", "() => !!window.FINDALINE_VIEW"),
                     ("today's page", clip_app + f"?ui=c&view=today#run={BIG}", "() => !!window.FINDALINE_RESULT"))
            seen = {}
            for name, url, ready in pages:
                for device, context in (("phone", phone), ("desktop", DESKTOP)):
                    ctx = browser.new_context(**context)
                    ctx.add_init_script(WATCH)
                    page = ctx.new_page()
                    page.goto(url)
                    page.wait_for_function(ready, timeout=WAIT)
                    # the violations of the selects made so far, then two frames and a task more for any other
                    if bug:
                        page.wait_for_function(f"() => CSPV.length >= SELECTS + {parsed}", timeout=WAIT)
                    page.evaluate("() => new Promise((ok) => requestAnimationFrame(() => requestAnimationFrame(() => setTimeout(ok, 0))))")
                    made = page.evaluate("() => SELECTS") + parsed
                    found = page.evaluate("() => CSPV")
                    seen[f"{name}, {device}"] = (made, found)
                    allowed = made if bug else 0
                    assert found == [["style-src-attr", "inline", ""]] * allowed, (name, device, made, found)
                    ctx.close()
            print("the engine's bug present:", bool(bug), "| selects made and violations:", seen)
        finally:
            browser.close()


# One step to the spot's next line, its work counted: the map's draws (SpotMap.paint wrapped: `full` true is a full
# draw with the presses' targets measured, false a draw of the picture alone, as a hover asks) and the Lines the model
# made, from the press until two frames and a task after it
COUNT_DRAWS = r"""() => { const m = window.FINDALINE_VIEW.map, paint = m.paint.bind(m); window.DRAWS = [];
  m.paint = (full, pass = 0) => { DRAWS.push(full ? 'full' : 'picture'); return paint(full, pass); }; }"""
STEP_WORK = r"""async () => { window.DRAWS = []; const made = D.m().madeLines;
  document.querySelector('.vl-next').click();
  await new Promise((ok) => requestAnimationFrame(() => requestAnimationFrame(() => setTimeout(ok, 0))));
  return {full: DRAWS.filter((d) => d === 'full').length, picture: DRAWS.filter((d) => d === 'picture').length,
          made: D.m().madeLines - made, row: D.v().selected.row}; }"""


@pytest.mark.parametrize("device", [DESKTOP, PHONE], ids=["desktop", "phone"])
def test_a_step_draws_the_map_once(site, device):
    """A step through a spot's lines (Next line) draws the map in full once (a second full draw may follow when the
    profile's card changes its height: the map's covered part), never again for the picture alone, and makes one Line
    (gate 2's item 2, the user's "stepping through a big spot's lines is laggy"; SESSION/M/speed.md): the profile's
    card or dock clears its point under the finger at every new line (ProfileDock's effect), which drew the whole map
    once more though no point was shown (SpotMap.hoverAt; on Gozo's spot 1.409 a full canvas at the phone's pixel
    ratio). Counted, not timed."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _open(browser, f"{site}#run={BIG}", device, script=SCRIPT)
            _view(page)
            many = page.evaluate("() => { const v = D.v(); return Array.from(v.order).find((s) => v.passingCount(s) > 4); }")
            _select(page, str(many))
            if device is PHONE:
                _sheet(page, "half")
                page.wait_for_selector(".vl-dock", timeout=WAIT)
            else:
                page.wait_for_selector(".r-card", timeout=WAIT)
            page.evaluate("() => T.frames()")
            page.evaluate(COUNT_DRAWS)
            rows = []
            for _ in range(3):
                work = page.evaluate(STEP_WORK)
                rows.append(work["row"])
                assert work["picture"] == 0 and 1 <= work["full"] <= 2 and work["made"] == 1, work
            assert len(set(rows)) == 3 and page.errors == []
        finally:
            browser.close()
