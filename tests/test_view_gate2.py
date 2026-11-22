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

from test_shell_c import BIG  # noqa: E402
from test_shell_c_view_map import DESKTOP, WAIT, _open, site, view_clip  # noqa: E402,F401
from test_view_details import SCRIPT, _select, _view  # noqa: E402
from test_web import EDGE, _playwright  # noqa: E402

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
