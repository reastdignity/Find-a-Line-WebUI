"""The parity of today's result page and the result view (step 3d of docs/line-volume/spec-view.md part B): the checks
today's tests make of today's page (tests/test_shell_c.py, test_shell_c_flows.py, test_same_lines.py, test_viewer.py's
test_result_map_in_edge, test_web.py's kit), made again of the view where no test of the view made them. Each
assertion and each wait names the row of the parity list it stands for (C1's list, H2 … X2) in its message; the list
gives each row its verdict. Seven walks: the desktop's header and map (the store read, credits, corners, the dark
theme, Compare, the coarser terrain's "Show on map", Edit & run again), the desktop's kept layout (the panels' edges
and rails, the card's height, width and fold, the credits' button, a reload), a narrow and low window (and a narrow
window widened), a line's details and its profile (presses beside lines, the card's text and steadiness, its point on
the map, a thin line pressed, the line stepper's focus, the facts against today's, a measured link, a tight line's
card, a new folder, Measure cancelled and refused), the list's head and filters, a phone's frame, and the loading's
failures with the flag set. Playwright's Edge over the app's server, offline, on the result view's clip run
(clip_runs.view_clip); a wait is for the state read next, at every frame, with a deadline (`Q.until`, `_wait`), but
in two helpers of other files (test_shell_c_view_map._crowded's own frames, test_shell_c.STEADY_JS's frames, which are
what it measures); no CSP violation and no page error anywhere. Run from PowerShell (.claude/rules/browser-tests.md)."""

import math
import os
import re
import sys
import urllib.parse

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_shell_c import (BIG, C_STUBS, CARD_JS, CORNERS_JS, CORNERS_SETTLED, EDITOR_JS, STEADY_JS,  # noqa: E402
                          TOO_LARGE_STUBS, add_credits, copy_clip, drop_store, stub_page)
from test_shell_c_view_list import _count  # noqa: E402
from test_shell_c_view_map import (BOXES, DESKTOP, FLAG, PHONE, WAIT, WORDS, _crowded, _open,  # noqa: E402,F401
                                   _with_boxes, view_clip)
from test_web import EDGE, _playwright, _server, store_with  # noqa: E402

pytestmark = pytest.mark.skipif(not os.path.exists(EDGE) or not _playwright(),
                                reason="needs Microsoft Edge and Playwright (group ui)")
COMPARED = "2026-10-30_120000_Compared_00000000000000e1"  # the clip's run again, for Compare
NOSTORE = "2026-10-29_120000_Old_00000000000000d1"        # a run without a store (has_lines false)
NOFOUND = "2026-10-28_130000_Plain_00000000000000c2"      # the clip's run with no `found` in its head
RUN_DATA = ("lines.arrow", "profiles.arrow", "data.js", "lines.js")
POINT = [50.1559508, 19.7562722]  # the job's centre (Edit & run again)
WIDE = {"viewport": {"width": 1400, "height": 900}}
NARROW = {"viewport": {"width": 900, "height": 460}}
# A line outside the run (the 3D view's moved anchors) and the server's profile of it, stubbed (80 m), every ask kept
# (today's test_shell_c_link_outside_the_run)
OUTSIDE = "49.5,19.1,49.5004,19.1005"
PROFILE_STUB = """
window.PROFILE_ASKS = [];
const fetchBeforeProfiles = window.fetch;
window.fetch = (url, init) => {
  if (!String(url).startsWith("/api/profile")) return fetchBeforeProfiles(url, init);
  PROFILE_ASKS.push(decodeURIComponent(String(url).split("line=")[1]));
  return Promise.resolve(new Response(JSON.stringify({d: [0, 20, 40, 60, 80], z: [300, 296, 292, 296, 301], min: [40, 7.5],
    water_m: 0, filled_m: 0}), {headers: {"content-type": "application/json"}}));
};
"""
# The server refuses every profile (a measurement that fails)
REFUSE_STUB = """window.fetch = ((real) => (url, init) => String(url).startsWith('/api/profile')
  ? Promise.resolve(new Response(JSON.stringify({detail: 'no profile here'}), {status: 400, headers: {'content-type': 'application/json'}}))
  : real(url, init))(window.fetch);"""

# The walks' helpers (window.Q), beside test_shell_c_view_map's T: today's LAYOUT_JS, MAP_JS and HELPERS as they apply
PARITY = r"""
window.Q = {
  v() { return window.FINDALINE_VIEW.view; },
  m() { return this.v().model; },
  /** `ok()` truthy (its value returned), checked at every frame; rejected after `ms` with `what` (the row's ID) and the
   *  layout's state (read so that it never throws: a column may be missing). */
  until(ok, what, ms = 30000) { const start = performance.now();
    return new Promise((done, fail) => { const tick = () => { let v = false; try { v = ok(); } catch (e) { v = false; }
      if (v) { done(v); return; }
      if (performance.now() - start > ms) {
        let state = "";
        try { state = `; list ${document.querySelector(".c-col-list")?.offsetWidth}, details ${document.querySelector(".c-col-details")?.offsetWidth}, kept ${localStorage.getItem("findaline.layout")}`; } catch (e) { state = ""; }
        fail(new Error(`${what}: not reached in ${ms} ms${state}`)); return; }
      requestAnimationFrame(tick); }; tick(); }); },
  /** `get()` (a promise) asked again at every frame until `ok(value)`; its value, or rejected after `ms` with `what`. */
  async poll(get, ok, what, ms = 30000) { const start = performance.now();
    for (;;) { const value = await get(); if (ok(value)) return value;
      if (performance.now() - start > ms) throw new Error(`${what}: not reached in ${ms} ms: ${JSON.stringify(value).slice(0, 200)}`);
      await new Promise((next) => requestAnimationFrame(next)); } },
  text(s) { return (document.querySelector(s) || {}).textContent || ""; },
  kept() { return JSON.parse(localStorage.getItem("findaline.layout") || "null"); },
  sep(side) { return document.querySelector(`.c-col-${side} > .c-split`); },
  rail(side) { return document.querySelector(`.c-col-${side} > .c-rail`); },
  width(side) { return document.querySelector(`.c-col-${side}`).offsetWidth; },
  aria(el) { return ["valuenow", "valuemin", "valuemax"].map((a) => Number(el.getAttribute("aria-" + a))); },
  key(el, k, shift = false) { el.dispatchEvent(new KeyboardEvent("keydown", {key: k, shiftKey: shift, bubbles: true, cancelable: true})); },
  pointer(el, type, x, y) { el.dispatchEvent(new PointerEvent(type, {bubbles: true, cancelable: true, pointerId: 1, pointerType: "mouse",
    button: 0, buttons: type === "pointerup" ? 0 : 1, clientX: x, clientY: y})); },
  /** A drag of `el` by dx, dy (today's drag): once `moved()` shows the page followed the pointer, the layout kept while
   *  the pointer is still down is read (returned); then released. */
  async drag(el, dx, dy, moved, what) { const r = el.getBoundingClientRect(), x = r.left + r.width / 2, y = r.top + Math.min(r.height / 2, 40);
    this.pointer(el, "pointerdown", x, y); this.pointer(el, "pointermove", x + dx / 2, y + dy / 2); this.pointer(el, "pointermove", x + dx, y + dy);
    await this.until(moved, what); const during = this.kept(); this.pointer(el, "pointerup", x + dx, y + dy); return during; },
  /** The card's height and its left edge in the map's column, px. */
  card() { const c = document.querySelector(".r-card"); if (!c) return null;
    return {height: c.offsetHeight, left: Math.round(c.getBoundingClientRect().left - document.querySelector(".c-col-map").getBoundingClientRect().left),
            folded: c.classList.contains("r-card-folded")}; },
  shown(s) { const e = document.querySelector(s); return !!e && e.getClientRects().length > 0; },
  credits() { return {toggle: this.shown(".u-credits-toggle"), credits: this.shown(".u-credits")}; },
  rect(s) { const e = document.querySelector(s); if (!e) return null; const b = e.getBoundingClientRect(); return [b.left, b.top, b.right, b.bottom]; },
  /** The run's files the page asked for (its resource timing). */
  files(id) { return performance.getEntriesByType("resource").map((e) => new URL(e.name).pathname)
    .filter((p) => p.startsWith("/runs/" + encodeURIComponent(id) + "/")).map((p) => p.split("/").pop()); },
  /** The facts' table in its order: each row's label and its values (no-break spaces as spaces); a group's row has no
   *  values. */
  facts() { return [...document.querySelectorAll(".vl-facts tbody tr")].map((tr) => { const th = tr.querySelector("th");
    return [th.firstChild ? th.firstChild.textContent.trim() : th.textContent.trim(),
            [...tr.querySelectorAll("td")].map((td) => td.textContent.replace(/[  ]/g, " ").trim())]; }); },
  /** A point a mouse's press takes alone for `spot` (`want`), `offset` px beside the spot's shown line (in the part of
   *  the map a person sees, clear of the controls by 24 px and of every number's shape): {x, y} in the viewport; null:
   *  none now (the canvas may not have drawn yet: asked again at every frame by until). `finger`: the press reaches as a
   *  finger's, and a mouse's must reach nothing there. */
  beside(spot, offset, finger) { const {view, map} = window.FINDALINE_VIEW, leaflet = window.FINDALINE_MAP, box = T.box(), f = T.free(), controls = T.controls();
    const e = T.ends(view.shownOf(spot)), len = Math.hypot(e[2] - e[0], e[3] - e[1]);
    if (len < 60) return null;
    for (let t = 0.3; t <= 0.7; t += 0.05) for (const side of [1, -1]) {
      const x = Math.round(e[0] + (e[2] - e[0]) * t - side * offset * (e[3] - e[1]) / len), y = Math.round(e[1] + (e[3] - e[1]) * t + side * offset * (e[2] - e[0]) / len);
      if (x < f[0] + 30 || y < f[1] + 30 || x > f[2] - 30 || y > f[3] - 30) continue;
      const vx = x + box.left, vy = y + box.top;
      if (controls.some((c) => vx > c.left - 24 && vx < c.right + 24 && vy > c.top - 24 && vy < c.bottom + 24)) continue;
      const lp = leaflet.containerPointToLayerPoint([x, y]);
      if (map.markAt(lp.x, lp.y, true) || map.markAt(lp.x, lp.y, false)) continue;
      const mouse = map.pick(lp.x, lp.y, false).found;
      if (finger) { const reach = map.pick(lp.x, lp.y, true).found;
        if (reach.length === 1 && reach[0].spot === spot && mouse.length === 0) return {x: vx, y: vy, spot}; }
      else if (mouse.length === 1 && mouse[0].spot === spot) return {x: vx, y: vy, spot}; }
    return null; },
  /** The first spot in view (but `not`) with such a point: its point. */
  besideAny(offset, finger, not = -1) { for (const spot of Array.from(this.v().inView.spots)) { if (spot === not) continue;
    const at = this.beside(spot, offset, finger); if (at) return at; } return null; },
  /** A point on a thin line of the selected spot (one of its other passing lines) where a mouse's press takes that line
   *  alone, no number's shape there: {x, y, row} in the viewport, or null now. */
  thin() { const {view, map} = window.FINDALINE_VIEW, leaflet = window.FINDALINE_MAP, sel = view.selected;
    const rows = Array.from(view.passingOf(sel.spot)).filter((r) => r !== sel.row), box = T.box(), controls = T.controls(), f = T.free();
    for (const row of rows) { const e = T.ends(row);
      for (let t = 0.2; t <= 0.8; t += 0.05) { const x = e[0] + (e[2] - e[0]) * t, y = e[1] + (e[3] - e[1]) * t;
        if (x < f[0] + 30 || y < f[1] + 30 || x > f[2] - 30 || y > f[3] - 30) continue;
        const vx = x + box.left, vy = y + box.top;
        if (controls.some((k) => vx > k.left - 8 && vx < k.right + 8 && vy > k.top - 8 && vy < k.bottom + 8)) continue;
        const lp = leaflet.containerPointToLayerPoint([x, y]);
        if (map.markAt(lp.x, lp.y, false)) continue;
        const hit = map.pick(lp.x, lp.y, false).found;
        if (hit.length === 1 && hit[0].row === row) return {x: vx, y: vy, row}; } }
    return null; },
};
// every script of a run's data.js or lines.js the page adds (the document itself observed: this runs before its element)
window.DATA_SCRIPTS = [];
new MutationObserver((changes) => changes.forEach((c) => c.addedNodes.forEach((n) => {
  if (n.tagName === "SCRIPT" && /(data|lines)\.js/.test(n.src || "")) DATA_SCRIPTS.push(n.src);
}))).observe(document, {childList: true, subtree: true});
"""

# What the browser sends at a point for a click of the mouse, a finger's tap, and WebKit's tap (a "mouse" click after a
# "touch" press): the spot each selects (null: none), the selection ended before each
TAPS_JS = """(b) => { const {view} = window.FINDALINE_VIEW, el = document.elementFromPoint(b.x, b.y);
  const init = {bubbles: true, cancelable: true, clientX: b.x, clientY: b.y, view: window}, out = {};
  const press = (down, click) => { view.select(null); el.dispatchEvent(new PointerEvent('pointerdown', {...init, pointerType: down}));
    el.dispatchEvent(new PointerEvent('pointerup', {...init, pointerType: down}));
    el.dispatchEvent(click === 'mouse' && down === 'mouse' ? new MouseEvent('click', init) : new PointerEvent('click', {...init, pointerType: click}));
    return view.selected ? view.selected.spot : null; };
  out.mouse = press('mouse', 'mouse'); out.finger = press('touch', 'touch'); out.webkit = press('touch', 'mouse');
  el.dispatchEvent(new PointerEvent('pointerdown', {...init, pointerType: 'mouse'})); view.select(null);
  return out; }"""


def _wait(page, js: str, row: str, arg=None):
    """page.wait_for_function with the row's ID in its failure."""
    from playwright.sync_api import TimeoutError as PlaywrightTimeout
    try:
        page.wait_for_function(js, arg=arg, timeout=WAIT)
    except PlaywrightTimeout as e:
        raise AssertionError(f"{row}: not reached in {WAIT} ms: {js[:200]}") from e


def _sel(page, selector: str, row: str, state: str = "visible"):
    """page.wait_for_selector with the row's ID in its failure."""
    from playwright.sync_api import TimeoutError as PlaywrightTimeout
    try:
        page.wait_for_selector(selector, state=state, timeout=WAIT)
    except PlaywrightTimeout as e:
        raise AssertionError(f"{row}: {selector} not {state} in {WAIT} ms") from e


def _click(page, selector: str, row: str):
    """page.click with the row's ID in its failure (the click waits for its element)."""
    from playwright.sync_api import TimeoutError as PlaywrightTimeout
    try:
        page.click(selector, timeout=WAIT)
    except PlaywrightTimeout as e:
        raise AssertionError(f"{row}: {selector} not pressable in {WAIT} ms") from e


def _chip(page, words: str, row: str):
    """A filter chip of the view pressed by its words, the row's ID in a failure."""
    from playwright.sync_api import TimeoutError as PlaywrightTimeout
    try:
        page.locator(".vl-filters .u-chip", has_text=words).first.click(timeout=WAIT)
    except PlaywrightTimeout as e:
        raise AssertionError(f"{row}: the chip {words!r} not pressable in {WAIT} ms") from e


def _corners_of(page, row: str) -> dict:
    """The map's scale and credits once settled (test_shell_c's CORNERS_SETTLED: the credits shown, the scale right above
    them where they run under it), the row's ID in a failure."""
    _wait(page, CORNERS_SETTLED, row)
    return page.evaluate(CORNERS_JS)


@pytest.fixture
def parity_site(tmp_path, view_clip):
    """A data folder served by the app: the clip's run (BIG) with a source's data credits and a finished job that made
    it (Edit & run again), the same run for Compare (COMPARED), a run without a store (NOSTORE), the clip's run with no
    `found` in its head (NOFOUND) and the clip's run with an uncertain shore and coarser terrain in its head (BOXES:
    test_shell_c_view_map's); yields the app page's address and the job."""
    from jobs import Jobs
    folder = tmp_path / "data"
    copy_clip(view_clip, folder, BIG, "Clip")
    copy_clip(view_clip, folder, COMPARED, "Compared run")
    copy_clip(view_clip, folder, NOSTORE, "Old run")
    drop_store(folder, NOSTORE)
    copy_clip(view_clip, folder, NOFOUND, "Clip without found")
    store_with(folder / "runs" / NOFOUND, head={"found": None})
    copy_clip(view_clip, folder, BOXES, "Clip with the boxes")
    _with_boxes(folder / "runs" / BOXES)
    add_credits(folder, BIG)
    jobs = Jobs(str(folder))
    job = jobs.add({"params": {"lat": POINT[0], "lon": POINT[1], "radius": 150}, "geometry": None}, "Clip")
    jobs.set(job, "done", run_id=BIG)
    page_path = stub_page(folder, "paritytest")
    with _server(folder) as port:
        yield {"url": f"http://127.0.0.1:{port}/{page_path}?ui=c", "job": job}


def _view(browser, site: dict, context: dict, run: str = BIG, script: str = "", row: str = "the view"):
    """The view of a run with the helpers, drawn (the row's ID in a failure to draw it)."""
    from playwright.sync_api import TimeoutError as PlaywrightTimeout
    try:
        page = _open(browser, f"{site['url']}#run={run}", context, script=PARITY + script)
    except PlaywrightTimeout as e:
        raise AssertionError(f"{row}: the view was not drawn in {WAIT} ms") from e
    _sel(page, ".vl-main", row)
    return page


def _clean(page, rows: str):
    """No CSP violation and no page error on the page (every walk)."""
    assert page.evaluate("() => window.CSP_VIOLATIONS") == [], f"Q1 ({rows}): {page.evaluate('() => window.CSP_VIOLATIONS')}"
    assert page.errors == [], f"Q2 ({rows}): {page.errors}"


def _meet(a, b) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def test_desktop_header_and_map(parity_site):
    """A desktop (1400 x 900): the run read from its store's two files, the download measured as the store's (X0); the
    run's data credits in the map's attribution, not folded without the card, with the link to its ATTRIBUTION.txt
    (M2); the scale right above the credits where they run under it, also after a zoom out and in (M5: the first
    placement; the credits run under the scale at every zoom here); the map's controls in the dark theme, zoom and
    layers alike, never Leaflet's light grey, focused and disabled shown (M7); Compare lists the runs with a store and
    offers no run without one (C1), a ticked run is read from its lines.arrow alone, every line of it (C2), Esc in its
    menu closes it, the focus back on "Compare" and the selection kept (C3); the coarser terrain's note's "Show on map"
    fits its regions into the map (M19); "Edit & run again" opens the form with the job's request (H3)."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _view(browser, parity_site, WIDE)
            store = page.evaluate(f"""() => ({{files: Q.files({BIG!r}),
                downloads: performance.getEntriesByName('fal:run:download').map((e) => e.detail && e.detail.store === true)}})""")
            assert sorted(f for f in store["files"] if f in RUN_DATA) == ["lines.arrow", "profiles.arrow"], f"X0: {store}"
            assert store["downloads"] == [True], f"X0: {store}"
            credits = page.evaluate("""() => ({text: Q.text('.leaflet-control-attribution'), toggle: getComputedStyle(document.querySelector('.u-credits-toggle')).display,
                links: [...document.querySelectorAll('.leaflet-control-attribution a')].map((a) => a.getAttribute('href'))})""")
            assert "FABDEM V1-2 © University of Bristol" in credits["text"] and credits["toggle"] == "none", f"M2: {credits}"
            assert f"/runs/{BIG}/ATTRIBUTION.txt" in credits["links"], f"M2: {credits['links']}"
            # the corners: the scale right above the credits (they run under it at this width), after a zoom out and in
            for name, by in (("start", 0), ("out", -3), ("in", 3)):
                page.evaluate(f"() => window.FINDALINE_MAP.setZoom(window.FINDALINE_MAP.getZoom() + {by}, {{animate: false}})")
                found = _corners_of(page, f"M5 ({name})")
                assert found["under"] and 0 <= found["attribution"][1] - found["scale"][3] <= 10, f"M5 ({name}): {found}"
            # the dark theme: the zoom and the layers button alike and dark, the focused button apart, the disabled marked
            dark = page.evaluate("""async () => { const root = document.querySelector('.ui'), m = window.FINDALINE_MAP;
                const colour = (q) => getComputedStyle(document.querySelector(q)).backgroundColor;
                const light = {panel: colour('.c-col-list'), zoom: colour('.leaflet-control-zoom-in')};
                root.dataset.theme = 'dark'; m.setZoom(m.getMaxZoom(), {animate: false});
                await Q.until(() => document.querySelector('.leaflet-control-zoom-in').classList.contains('leaflet-disabled') && colour('.c-col-list') !== light.panel,
                              'M7: the dark theme at the last zoom');
                const out = document.querySelector('.leaflet-control-zoom-out'); out.focus();
                await Q.until(() => document.activeElement === out, 'M7: the zoom out focused');
                const r = {light, panel: colour('.c-col-list'), zoom: colour('.leaflet-control-zoom-in'), layers: colour('.leaflet-control-layers'),
                           disabled: document.querySelector('.leaflet-control-zoom-in').classList.contains('leaflet-disabled'), focused: colour('.leaflet-control-zoom-out')};
                out.blur(); delete root.dataset.theme;
                await Q.until(() => colour('.c-col-list') === light.panel, 'M7: the light theme again'); return r; }""")
            assert dark["disabled"] and dark["zoom"] == dark["layers"], f"M7: {dark}"
            assert dark["zoom"] not in ("rgb(255, 255, 255)", "rgb(244, 244, 244)", dark["light"]["zoom"]), f"M7: {dark}"
            assert dark["panel"] != dark["light"]["panel"] and dark["focused"] not in (dark["zoom"], "rgb(244, 244, 244)"), f"M7: {dark}"
            page.evaluate("() => window.FINDALINE_MAP.setZoom(window.FINDALINE_MAP.getZoom() - 3, {animate: false})")
            # Compare's menu: Esc closes it, the focus back on its button, the selection kept
            selected = page.evaluate("() => { const v = Q.v(); v.select(Array.from(v.order)[0]); return v.selected.row; }")
            compare = ".c-result-top .r-actions button:has-text('Compare')"
            _click(page, compare, "C3")
            _wait(page, "() => !!document.activeElement.closest('.r-pop')", "C3: the focus in Compare's menu")
            page.keyboard.press("Escape")
            _sel(page, ".r-pop", "C3: Compare's menu closed by Esc", "detached")
            back = page.evaluate("() => [document.activeElement.textContent.trim(), Q.v().selected && Q.v().selected.row]")
            assert back == ["Compare", selected], f"C3: {back}"
            # the other runs: a run with a store listed, one without not offered; ticked, read from its lines.arrow alone
            _click(page, compare, "C1")
            _sel(page, ".r-other", "C1: Compare's list")
            listed = page.evaluate("() => [...document.querySelectorAll('.r-other')].map((o) => o.textContent.split(' · ')[0])")
            assert "Compared run" in listed and "Old run" not in listed, f"C1: {listed}"
            page.evaluate("() => [...document.querySelectorAll('.r-other')].find((o) => /Compared run/.test(o.textContent)).querySelector('input').click()")
            _wait(page, "() => Q.m().others.size === 1 && ![...document.querySelectorAll('.r-other')].some((o) => /loading/.test(o.textContent))",
                  "C2: the other run loaded")
            got = page.evaluate(f"""() => ({{others: Object.fromEntries([...Q.m().others.values()].map((o) => [o.info.id, o.count])),
                lines: Q.v().count, compared: Q.files({COMPARED!r}), old: Q.files({NOSTORE!r})}})""")
            assert got["others"] == {COMPARED: got["lines"]}, f"C2: {got['others']}"
            assert [f for f in got["compared"] if f in RUN_DATA] == ["lines.arrow"] and got["old"] == [], f"C1, C2: {got}"
            page.keyboard.press("Escape")
            _sel(page, ".r-pop", "C1: Compare's menu closed", "detached")
            # Edit & run again: the form with the job's request
            _click(page, ".c-result-top a:has-text('Edit & run again')", "H3")
            _wait(page, f"() => location.hash.startsWith('#new&edit={parity_site['job']}') && !!document.querySelector('.c-subtitle') "
                        "&& !!window.FINDALINE_SEARCH && !!window.FINDALINE_SEARCH.point", "H3: the form of the job")
            edit = page.evaluate("() => [document.querySelector('.c-subtitle').textContent, window.FINDALINE_SEARCH.point]")
            assert edit[0] == "Edit & run again" and [round(v, 5) for v in edit[1]] == [round(v, 5) for v in POINT], f"H3: {edit}"
            _clean(page, "W1")
            page.context.close()
            # the coarser terrain (the run with the boxes): the head's note's "Show on map" fits every region into the map
            page = _view(browser, parity_site, WIDE, run=BOXES, row="M19")
            _sel(page, ".r-coarse button", "M19: the coarser terrain's note")
            fit = page.evaluate("""async () => { const m = window.FINDALINE_MAP, ring = Q.m().data.terrain_sources.regions[0].rings[0];
                const lats = ring.map((p) => p[1]), lons = ring.map((p) => p[0]);
                const s = Math.min(...lats), n = Math.max(...lats), w = Math.min(...lons), e = Math.max(...lons);
                const holds = () => { const b = m.getBounds(); return b.getSouth() <= s && b.getNorth() >= n && b.getWest() <= w && b.getEast() >= e; };
                const apart = () => { const b = m.getBounds(); return b.getSouth() > n || b.getNorth() < s || b.getWest() > e || b.getEast() < w; };
                m.setView([n + 0.05, e + 0.05], 15, {animate: false});
                await Q.until(apart, 'M19: the map moved off the region');
                document.querySelector('.r-coarse button').click();
                await Q.until(holds, 'M19: the region fitted');
                return [document.querySelector('.r-coarse button').textContent, holds()]; }""")
            assert fit == [WORDS["ui.coarse.show"], True], f"M19: {fit}"
            _clean(page, "W1, the coarser terrain")
        finally:
            browser.close()


def test_desktop_layout_kept(parity_site):
    """A desktop (1400 x 900), as today's test_shell_c_layout: the list's edge by keys (±16, Shift ±64, Home, End), a
    double click its default, a drag, kept when released (KB1, KB2), the details' too; the tab and the rail collapse
    and expand a panel, the focus to the rail and then the edge, Enter on the edge, the rails' labels, the map's width
    with the list's rail (KB3); a selection leaves the collapsed details collapsed, its rail naming the spot (KB4); the
    card's height (Home: its least, the chart then 120 px, its bounds by aria; ArrowUp, a drag) and its left edge by
    keys, its fold, all kept (P4, P5); the data credits' button with the card open (M4); the layout found again after a
    reload (KB5)."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _view(browser, parity_site, WIDE)
            r = page.evaluate("""async () => { const listMax = () => Math.min(560, document.querySelector('.c-cols').clientWidth - 360 - 380);
              await Q.until(() => Q.sep('list') && Q.sep('details') && Q.width('list') === 372 && Q.width('details') === 380, 'KB1: the start');
              const r = {}, kept = (side) => (Q.kept() || {})[side] || {};
              r.start = {cols: document.querySelector('.c-cols').clientWidth, list: Q.width('list'), details: Q.width('details'), kept: Q.kept(),
                         listAria: Q.aria(Q.sep('list')), detailsAria: Q.aria(Q.sep('details')), tabInSeparator: !!Q.sep('list').querySelector('button'),
                         tabs: [document.querySelector('.c-col-list > .c-col-tab').getAttribute('aria-label'), document.querySelector('.c-col-details > .c-col-tab').getAttribute('aria-label')]};
              Q.key(Q.sep('list'), 'ArrowRight'); await Q.until(() => Q.width('list') === 388, 'KB1: ArrowRight');
              Q.key(Q.sep('list'), 'ArrowRight', true); await Q.until(() => Q.width('list') === 452 && kept('list').w === 452, 'KB1: Shift+ArrowRight');
              r.listKeys = {width: Q.width('list'), aria: Q.aria(Q.sep('list')), kept: kept('list').w};
              Q.key(Q.sep('list'), 'Home'); await Q.until(() => Q.width('list') === 260, 'KB1: Home'); r.listHome = Q.width('list');
              Q.key(Q.sep('list'), 'End'); await Q.until(() => Q.width('list') === listMax(), 'KB1: End'); r.listEnd = Q.width('list');
              Q.sep('list').dispatchEvent(new MouseEvent('dblclick', {bubbles: true, cancelable: true}));
              await Q.until(() => Q.width('list') === 372 && kept('list').w === 372, 'KB1: a double click');
              r.listReset = [Q.width('list'), kept('list').w];
              const during = await Q.drag(Q.sep('list'), 40, 0, () => Q.width('list') === 412, 'KB2: the list followed the pointer');
              await Q.until(() => kept('list').w === 412, 'KB2: the list kept when released');
              r.listDrag = {width: Q.width('list'), during: during.list.w, kept: kept('list').w};
              Q.sep('list').dispatchEvent(new MouseEvent('dblclick', {bubbles: true, cancelable: true}));
              await Q.until(() => Q.width('list') === 372 && kept('list').w === 372, 'KB1: a double click again');
              Q.key(Q.sep('details'), 'ArrowLeft'); await Q.until(() => Q.width('details') === 396 && kept('details').w === 396, 'KB1: the details by a key');
              r.detailsKey = [Q.width('details'), kept('details').w];
              const d2 = await Q.drag(Q.sep('details'), -30, 0, () => Q.width('details') === 426, 'KB2: the details followed the pointer');
              await Q.until(() => kept('details').w === 426, 'KB2: the details kept when released');
              r.detailsDrag = {width: Q.width('details'), during: d2.details.w, kept: kept('details').w};
              Q.sep('details').dispatchEvent(new MouseEvent('dblclick', {bubbles: true, cancelable: true}));
              await Q.until(() => Q.width('details') === 380 && kept('details').w === 380, 'KB1: the details by a double click');
              r.detailsReset = [Q.width('details'), kept('details').w];
              document.querySelector('.c-col-list > .c-col-tab').click();
              await Q.until(() => document.querySelector('.c-col-list.c-collapsed') && document.activeElement === Q.rail('list') && kept('list').open === false, 'KB3: the tab');
              r.listRail = {collapsed: document.querySelector('.c-col-list').className, width: Q.width('list'), focus: document.activeElement === Q.rail('list'),
                            label: Q.text('.c-col-list > .c-rail .c-rail-text'), auto: !!document.querySelector('.c-col-list .c-rail-auto'), kept: kept('list').open,
                            mapWidth: document.querySelector('.c-col-map').offsetWidth};
              Q.rail('list').click();
              await Q.until(() => !document.querySelector('.c-col-list.c-collapsed') && document.activeElement === Q.sep('list') && kept('list').open === true, 'KB3: the rail');
              r.listOpen = {open: !document.querySelector('.c-col-list.c-collapsed'), focus: document.activeElement === Q.sep('list'), kept: kept('list').open};
              Q.key(Q.sep('details'), 'Enter');
              await Q.until(() => document.querySelector('.c-col-details.c-collapsed') && document.activeElement === Q.rail('details') && kept('details').open === false, 'KB3: Enter');
              r.detailsRail = {collapsed: !!document.querySelector('.c-col-details.c-collapsed'), focus: document.activeElement === Q.rail('details'),
                               label: Q.text('.c-col-details > .c-rail .c-rail-text'), kept: kept('details').open};
              r.lines = Q.v().counts.lines;
              return r; }""")
            s = r["start"]
            assert (s["list"], s["details"]) == (372, 380) and s["kept"] is None, f"KB1: {s}"
            list_max, details_max = min(560, s["cols"] - 360 - 380), min(600, s["cols"] - 360 - 372)
            assert s["listAria"] == [372, 260, list_max] and s["detailsAria"] == [380, 300, details_max], f"KB1: {s}"
            assert s["tabs"] == ["Collapse the list", "Collapse the details"] and not s["tabInSeparator"], f"KB3: {s}"
            assert r["listKeys"] == {"width": 452, "aria": [452, 260, list_max], "kept": 452}, f"KB1: {r['listKeys']}"
            assert (r["listHome"], r["listEnd"], r["listReset"]) == (260, list_max, [372, 372]), f"KB1: {r}"
            assert r["listDrag"] == {"width": 412, "during": 372, "kept": 412}, f"KB2: {r['listDrag']}"
            assert r["detailsKey"] == [396, 396] and r["detailsDrag"] == {"width": 426, "during": 396, "kept": 426}, f"KB1, KB2: {r}"
            assert r["detailsReset"] == [380, 380], f"KB1: {r['detailsReset']}"
            lr = r["listRail"]
            assert "c-collapsed" in lr["collapsed"] and "c-forced" not in lr["collapsed"] and lr["width"] == 36, f"KB3: {lr}"
            assert lr["focus"] and not lr["auto"] and lr["kept"] is False, f"KB3: {lr}"
            assert lr["mapWidth"] == s["cols"] - 36 - 380, f"KB3 (the map's width): {lr['mapWidth']}, {s['cols']}"
            assert lr["label"] == WORDS["ui.view.map.rail_list"].replace("{{n}}", _count(r["lines"])), f"KB3: {lr['label']}"
            assert r["listOpen"] == {"open": True, "focus": True, "kept": True}, f"KB3: {r['listOpen']}"
            assert r["detailsRail"] == {"collapsed": True, "focus": True, "label": WORDS["ui.view.map.rail_details"], "kept": False}, f"KB3: {r['detailsRail']}"
            # a selection: the details stay collapsed, their rail names the spot; the rail opens them, the focus to the edge
            page.evaluate("() => { const v = Q.v(); v.select(Array.from(v.order)[0]); }")
            _wait(page, "() => /Spot/.test(Q.text('.c-col-details > .c-rail .c-rail-text'))", "KB4: the rail names the spot")
            sel = page.evaluate("() => [!!document.querySelector('.c-col-details.c-collapsed'), Q.text('.c-col-details > .c-rail .c-rail-text'), Q.v().label(Q.v().selected.spot)]")
            assert sel[0] and sel[1] == WORDS["ui.view.map.rail_spot"].replace("{{label}}", sel[2]), f"KB4: {sel}"
            page.evaluate("() => Q.rail('details').click()")
            _wait(page, "() => !document.querySelector('.c-col-details.c-collapsed') && document.activeElement === Q.sep('details')", "KB4: the details opened")
            # the card: its least height, ArrowUp, a drag of its top; its left edge; its fold; the credits' button
            _sel(page, ".r-card .fal-profile-chart", "P4: the card")
            c = page.evaluate("""async () => { const card = () => document.querySelector('.r-card'), top = () => document.querySelector('.r-card .r-card-top');
              const profile = () => (Q.kept() || {}).profile || {}, r = {};
              await Q.until(() => card() && card().offsetHeight > 100 && Q.credits().toggle && !Q.credits().credits, 'P4, M4: the card and the credits folded');
              r.credits = Q.credits();
              Q.key(top(), 'Home');
              await Q.until(() => { const a = Q.aria(top()); return profile().h === card().offsetHeight && a[0] === card().offsetHeight && a[0] === a[1]; }, 'P4: Home');
              r.home = {height: card().offsetHeight, kept: profile().h, aria: Q.aria(top()), chart: card().querySelector('.fal-profile-chart').clientHeight,
                        map: document.querySelector('.c-col-map').clientHeight};
              const h = card().offsetHeight;
              Q.key(top(), 'ArrowUp'); await Q.until(() => card().offsetHeight === h + 16 && profile().h === h + 16, 'P4: ArrowUp');
              r.up = {height: card().offsetHeight, kept: profile().h};
              const during = await Q.drag(top(), 0, -40, () => card().offsetHeight === h + 56, 'P4: the card followed the pointer');
              await Q.until(() => profile().h === h + 56, 'P4: the card kept when released');
              r.drag = {height: card().offsetHeight, during: during.profile.h, kept: profile().h};
              Q.key(document.querySelector('.r-card .r-card-l'), 'ArrowRight');
              await Q.until(() => Q.card().left === 28 && profile().l === 28, 'P4: the left edge');
              r.left = {left: Q.card().left, kept: [profile().l, profile().r]};
              document.querySelector('.r-card .r-fold').click(); await Q.until(() => Q.card().folded && profile().folded === true, 'P5: folded');
              r.folded = [Q.card().folded, profile().folded];
              document.querySelector('.r-card .r-fold').click(); await Q.until(() => !Q.card().folded && profile().folded === false, 'P5: unfolded');
              r.unfolded = [Q.card().folded, profile().folded];
              return r; }""")
            assert c["credits"] == {"toggle": True, "credits": False}, f"M4: {c['credits']}"
            home = c["home"]
            assert home["height"] == home["kept"] == home["aria"][1] == home["aria"][0], f"P4: {home}"
            # its bounds: at least 160 px, at most 70 % of the map; the chart at its least, 120 px (today's "under 250 px"
            # was of another run: on this one today's card is 261 px at Home, the view's 258)
            assert home["aria"][1] >= 160 and home["aria"][2] == round(0.7 * home["map"]) and 119 <= home["chart"] <= 121, f"P4: {home}"
            h = home["height"]
            assert c["up"] == {"height": h + 16, "kept": h + 16}, f"P4: {c['up']}"
            assert c["drag"] == {"height": h + 56, "during": h + 16, "kept": h + 56}, f"P4: {c['drag']}"
            assert c["left"] == {"left": 28, "kept": [28, 12]}, f"P4: {c['left']}"
            assert c["folded"] == [True, True] and c["unfolded"] == [False, False], f"P5: {c}"
            # the data credits' button while the card is open: they open, and fold again
            _click(page, ".u-credits-toggle", "M4")
            _wait(page, "() => document.querySelector('.u-credits-toggle').getAttribute('aria-expanded') === 'true'", "M4: the credits opened")
            assert page.evaluate("() => Q.credits()") == {"toggle": True, "credits": True}, "M4: the credits opened"
            _click(page, ".u-credits-toggle", "M4")
            _wait(page, "() => document.querySelector('.u-credits-toggle').getAttribute('aria-expanded') === 'false'", "M4: the credits folded")
            assert page.evaluate("() => Q.credits()") == {"toggle": True, "credits": False}, "M4: the credits folded again"
            # a layout to find again: the list collapsed, wider details, a taller card, its left edge further in
            before = page.evaluate("""async () => { const kept = (side) => (Q.kept() || {})[side] || {};
              document.querySelector('.c-col-list > .c-col-tab').click(); await Q.until(() => kept('list').open === false, 'KB5: the list collapsed');
              Q.key(Q.sep('details'), 'ArrowLeft', true); await Q.until(() => Q.width('details') === 444 && kept('details').w === 444, 'KB5: the details wider');
              const h = Q.card().height; Q.key(document.querySelector('.r-card .r-card-top'), 'ArrowUp', true);
              await Q.until(() => Q.card().height === h + 64 && kept('profile').h === h + 64, 'KB5: the card taller');
              Q.key(document.querySelector('.r-card .r-card-l'), 'ArrowRight', true); await Q.until(() => Q.card().left === 92 && kept('profile').l === 92, 'KB5: the left edge');
              return Q.kept(); }""")
            assert before["list"]["open"] is False and before["details"]["w"] == 444 and before["profile"]["l"] == 92, f"KB5: {before}"
            _clean(page, "W2")
            page.reload()
            _wait(page, "() => !!window.FINDALINE_VIEW && !!document.querySelector('.r-card .fal-profile-chart') && !!document.querySelector('.c-col-list > .c-rail')",
                  "KB5: the view drawn again after the reload")
            page.evaluate("() => Q.until(() => Q.card() && Q.card().left === 92 && Q.card().height === Q.kept().profile.h && Q.width('details') === 444, 'KB5: the layout after the reload')")
            again = page.evaluate("""() => ({list: document.querySelector('.c-col-list').className, details: Q.width('details'), kept: Q.kept(),
                card: Math.round(document.querySelector('.r-card').getBoundingClientRect().height),
                left: Math.round(document.querySelector('.r-card').getBoundingClientRect().left - document.querySelector('.c-col-map').getBoundingClientRect().left)})""")
            assert "c-collapsed" in again["list"] and again["details"] == 444 and again["kept"] == before, f"KB5: {again}"
            assert again["card"] == before["profile"]["h"] and again["left"] == 92, f"KB5: {again}"
            _clean(page, "W2, after the reload")
        finally:
            browser.close()


def test_narrow_and_low_window(parity_site):
    """A window of 900 x 460, as today's test_shell_c_layout's narrow one: the details collapsed by the window with
    the mark "auto", never kept; expanding them collapses the list instead (KB6); in a map lower than 420 px a
    selection's card opens folded, and what is changed there (unfolded, its height and left edge) is not kept (P7). A
    narrow window (390 x 844, no phone's profile) widened to a desktop's: the sheet gone, the scale right above the
    credits where they run under it (M6b, today's test_shell_c_filter_editor_and_sorted_column)."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _view(browser, parity_site, NARROW)
            r = page.evaluate("""async () => { await Q.until(() => document.querySelector('.c-col-details.c-forced') && Q.width('list') === 372, 'KB6: the details collapsed by the window');
              const r = {};
              r.forced = {details: document.querySelector('.c-col-details').className, auto: Q.text('.c-col-details .c-rail-auto'),
                          list: [!document.querySelector('.c-col-list.c-collapsed'), Q.width('list')], kept: Q.kept()};
              Q.rail('details').click();
              await Q.until(() => !document.querySelector('.c-col-details.c-collapsed') && document.querySelector('.c-col-list.c-forced') && document.activeElement === Q.sep('details'),
                            'KB6: the details expanded, the list collapsed');
              r.preferred = {details: [!document.querySelector('.c-col-details.c-collapsed'), Q.width('details')], list: document.querySelector('.c-col-list').className,
                             auto: !!document.querySelector('.c-col-list .c-rail-auto'), focus: document.activeElement === Q.sep('details'), kept: Q.kept()};
              return r; }""")
            f = r["forced"]
            assert "c-collapsed" in f["details"] and "c-forced" in f["details"] and f["auto"] == "auto", f"KB6: {f}"
            assert f["list"] == [True, 372] and f["kept"] is None, f"KB6: {f}"
            pr = r["preferred"]
            assert pr["details"] == [True, 380] and "c-forced" in pr["list"] and pr["auto"], f"KB6: {pr}"
            assert pr["focus"] and pr["kept"]["list"]["open"] is True, f"KB6: {pr}"
            # a low map: the card opens folded; nothing done there is kept
            low = page.evaluate("""async () => { const before = localStorage.getItem('findaline.layout'), {view} = window.FINDALINE_VIEW;
              view.select(Array.from(view.order)[0]); await Q.until(() => Q.card() && Q.credits().toggle, 'P7: the card');
              const r = {folded: Q.card().folded, mapHeight: document.querySelector('.c-col-map').clientHeight, credits: Q.credits()};
              document.querySelector('.r-card .r-fold').click(); await Q.until(() => !Q.card().folded, 'P7: unfolded'); r.unfolded = !Q.card().folded;
              const top = document.querySelector('.r-card .r-card-top');
              Q.key(top, 'Home'); await Q.until(() => { const a = Q.aria(top); return a[0] === a[1]; }, 'P7: Home');
              const h = Q.card().height, most = Math.round(0.7 * document.querySelector('.c-col-map').clientHeight);
              await Q.drag(top, 0, -20, () => Q.card().height !== h || h >= most - 1, 'P7: the card followed the pointer');
              Q.key(document.querySelector('.r-card .r-card-l'), 'ArrowRight'); await Q.until(() => Q.card().left === 28, 'P7: the left edge');
              r.same = localStorage.getItem('findaline.layout') === before;
              r.left = Q.card().left;
              return r; }""")
            assert low["folded"] and low["mapHeight"] < 420 and low["credits"] == {"toggle": True, "credits": False}, f"P7: {low}"
            assert low["unfolded"] and low["same"] and low["left"] == 28, f"P7: {low}"
            _clean(page, "W3")
            page.context.close()
            # a narrow window widened to a desktop's: the sheet's corners undone, the columns' taken over
            page = _view(browser, parity_site, {"viewport": {"width": 390, "height": 844}}, row="M6b")
            _sel(page, ".u-sheet", "M6b: the narrow window's sheet")
            page.set_viewport_size({"width": 1280, "height": 900})
            _sel(page, ".u-sheet", "M6b: the sheet gone", "detached")
            _sel(page, ".c-col-map .leaflet-container", "M6b: the columns' map")
            widened = _corners_of(page, "M6b")
            gap = widened["attribution"][1] - widened["scale"][3]
            assert (widened["under"] and 0 <= gap <= 10) or (not widened["under"] and not _meet(widened["scale"], widened["attribution"])), f"M6b: {widened}"
            assert widened["under"], f"M6b (the credits run under the scale here, as on today's page): {widened}"
            _clean(page, "W3, widened")
        finally:
            browser.close()


def test_details_and_profile(parity_site):
    """A desktop: 14 px beside a line a finger's tap takes it and the mouse's click does not, also as WebKit sends a
    tap (M11); with a spot selected, a click 4 px beside another spot's line takes that spot (M8), and Esc on the table
    of spots closes it and the selection stays (M13); the card's compact form (no head row, the line's facts in its bar
    and its title "Profile: …", the legend and the 1:1 scale under "Rigging and layers", toggled) (P3); its bar and
    readout show their whole text, the chart at least 120 px, the scale and the credits clear of the card, for the first
    spot's line and the longest spot's (two lines), and the card, chart and readout steady under a moving cursor at the
    default width and at the narrowest and lowest (P9); a touch on the chart puts the point on the map, gone with the
    next line (P12, M23); the line stepper's › keeps the focus, and at the spot's last line hands it to ‹ (KB8); a thin
    line of the selected spot pressed selects that line (M8b); the card closed by its x and brought back by "Profile"
    (D14, P6); the facts' values are today's for the same line (D15: the anchors, angle, prominence, drop, over trees,
    height difference, above the ground, rigging, "Stands for"; no water or filled gaps on this clip); a link to a line
    outside the run measured with today's bar and title, asked once (P13); a tight line's card writes its clearance
    rounded down as the rows do (P10); the star's "New folder" makes a folder and saves the line into it (F2); Measure's
    "Cancel" ends the measuring (E7); a measurement the server refuses shows "Not computed: …" (E4)."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _view(browser, parity_site, WIDE)
            # 14 px beside a line: a finger's tap takes it, the mouse's click does not; WebKit's tap too
            page.evaluate("() => Q.v().setLevel('spots')")
            beside = page.evaluate("() => Q.until(() => Q.besideAny(14, true), 'M11: no point 14 px beside a line that a finger alone reaches')")
            taps = page.evaluate(TAPS_JS, beside)
            assert taps == {"mouse": None, "finger": beside["spot"], "webkit": beside["spot"]}, f"M11: {taps}"
            # a spot selected; a click 4 px beside another spot's line takes that spot
            chosen = page.evaluate("() => { const v = Q.v(); v.select(Array.from(v.order)[0]); return v.selected.spot; }")
            other = page.evaluate(f"() => Q.until(() => Q.besideAny(4, false, {chosen}), 'M8: no point 4 px beside another spot\\'s line')")
            page.mouse.click(other["x"], other["y"])
            _wait(page, f"() => Q.v().selected && Q.v().selected.spot === {other['spot']}", "M8: the other spot selected")
            # Esc on the table of spots (several spots under a click) closes it; the selection stays
            page.evaluate(f"() => Q.v().select({chosen})")
            at = _crowded(page, False)
            assert at, "M13: no point where a click reaches several spots"
            page.mouse.click(at["x"], at["y"])
            _sel(page, ".vl-choose:not(.vl-choose-new)", "M13: the table of spots")
            _wait(page, "() => !!document.activeElement.closest('.vl-choose')", "M13: the focus in the table")
            page.keyboard.press("Escape")
            _sel(page, ".vl-choose", "M13: the table closed by Esc", "detached")
            assert page.evaluate("() => Q.v().selected && Q.v().selected.spot") == chosen, "M13: Esc on the table ended the selection"
            # the card of the first spot of several lines
            page.evaluate("() => { const v = Q.v(); v.select(Array.from(v.order).find((s) => v.passingCount(s) >= 3)); }")
            _sel(page, ".r-card .fal-profile-chart svg", "P3: the card")
            _wait(page, "() => /FABDEM/.test(document.querySelector('.leaflet-control-attribution').textContent)", "P9: the credits")
            compact = page.evaluate("""() => ({head: !!document.querySelector('.r-card .fal-profile-head'), title: Q.text('.r-card .fal-profile-title'),
                facts: Q.text('.r-card .r-facts'), factsTitle: document.querySelector('.r-card .r-facts').getAttribute('title'),
                legend: Q.shown('.r-card .fal-profile-legend'), scale: Q.shown('.r-card .fal-scale')})""")
            assert not compact["head"] and compact["title"].startswith("Profile: ") and compact["facts"].startswith("min. clearance "), f"P3: {compact}"
            assert compact["factsTitle"] == compact["title"] and compact["title"].endswith(compact["facts"].split(" · ")[0]), f"P3: {compact}"
            assert not compact["legend"] and not compact["scale"], f"P3: {compact}"
            _click(page, ".r-card .r-dock-bar .u-chip", "P3")
            _wait(page, "() => Q.shown('.r-card .fal-profile-legend') && Q.shown('.r-card .fal-scale')", "P3: Rigging and layers")
            before = page.evaluate("() => Q.text('.r-card .fal-scale')")
            _click(page, ".r-card .fal-scale", "P3")
            _wait(page, f"() => Q.text('.r-card .fal-scale') !== {before!r}", "P3: the scale toggled")
            rig = page.evaluate("() => [Q.text('.r-card .fal-scale'), !!document.querySelector('.r-card .fal-profile-controls .fal-key .fal-scale')]")
            assert before.startswith("1:1 scale") and rig == ["Auto scale", True], f"P3: {before}, {rig}"
            _click(page, ".r-card .fal-scale", "P3")
            _click(page, ".r-card .r-dock-bar .u-chip", "P3")
            _wait(page, "() => !Q.shown('.r-card .fal-profile-legend')", "P3: Rigging and layers closed")
            # the card's text whole, the chart's height, clear of the scale and the credits: the first spot's line, then
            # the longest spot's (its shown line the longest in view)
            cards = {"first": _card_text(page, "first")}
            # a touch on the chart: its point on the map; the next line takes it away
            touch = page.evaluate("""async () => { const {view, map} = window.FINDALINE_VIEW, h = document.querySelector('.r-card .fal-hover'), b = h.getBoundingClientRect();
                h.dispatchEvent(new PointerEvent('pointerdown', {pointerType: 'touch', pointerId: 7, bubbles: true, clientX: b.left + b.width / 2, clientY: b.top + 5}));
                await Q.until(() => !!map.marker, 'P12, M23: the point on the map');
                const r = {dot: !!map.marker, readout: Q.text('.r-card .fal-profile-readout')};
                const row = view.selected.row; view.step(1);
                await Q.until(() => view.selected.row !== row && !map.marker, 'M23: the point gone with the next line');
                r.gone = !map.marker; r.stepped = view.selected.row !== row; return r; }""")
            assert touch["dot"] and " from A1" in touch["readout"], f"P12, M23: {touch}"
            assert touch["gone"] and touch["stepped"], f"M23: {touch}"
            # the longest spot's line (its shown line the longest of the run's spots)
            page.evaluate("""() => { const v = Q.v(); let best = -1, len = -1;
                for (const s of Array.from(v.order)) { const l = v.values.len[v.shownOf(s)]; if (l > len) { len = l; best = s; } }
                v.select(best); }""")
            _wait(page, "() => Q.v().selected && Q.text('.r-card .fal-profile-title').includes(String(Math.round(Q.v().selected.line.len)) + ' m')",
                  "P9: the longest spot's card")
            cards["longest"] = _card_text(page, "longest")
            assert cards["first"]["facts"] != cards["longest"]["facts"], f"P9 (two lines): {cards}"
            steady = {"default": page.evaluate(STEADY_JS)}
            for edge in (".r-card .r-card-l", ".r-card .r-card-top"):
                page.focus(edge)
                page.keyboard.press("Home")
            wide = steady["default"][0]["card"]
            _wait(page, f"() => document.querySelector('.r-card').getBoundingClientRect().width < {wide[2] - wide[0] - 50}", "P9: the card at its narrowest")
            steady["narrow"] = page.evaluate(STEADY_JS)
            for name, states in steady.items():
                assert len({(tuple(s["card"]), tuple(s["chart"]), tuple(s["readout"])) for s in states}) == 1, f"P9 ({name}): {states}"
                assert all(s["inside"] and s["cut"] == [] for s in states) and any(" from A1" in s["text"] for s in states), f"P9 ({name}): {states}"
            # the line stepper's focus (a spot of three lines or more): › keeps it; at the spot's last line it goes to ‹
            # (the keyboard's Enter on the focused ›, each once the details show the line it starts from: data-row)
            spot, rows = page.evaluate("""() => { const v = Q.v(), spot = Array.from(v.order).find((s) => v.passingCount(s) >= 3);
                const rows = Array.from(v.passingOf(spot)); v.select(spot, rows[0]); return [spot, rows]; }""")
            assert len(rows) >= 3, f"KB8: {rows}"
            row_of = "() => +(document.querySelector('.vl-details') || {dataset: {}}).dataset.row"
            _wait(page, f"() => ({row_of})() === {rows[0]} && !document.querySelector('.vl-next').disabled", "KB8: the first line")
            page.focus(".vl-next")
            page.keyboard.press("Enter")
            _wait(page, f"() => ({row_of})() === {rows[1]}", "KB8: the next line")
            kept = page.evaluate("() => document.activeElement === document.querySelector('.vl-next')")
            page.evaluate(f"() => Q.v().select({spot}, {rows[-2]})")
            _wait(page, f"() => ({row_of})() === {rows[-2]} && !document.querySelector('.vl-next').disabled", "KB8: the line before the last")
            page.focus(".vl-next")
            page.keyboard.press("Enter")
            _wait(page, f"() => ({row_of})() === {rows[-1]} && document.querySelector('.vl-next').disabled", "KB8: the last line")
            _wait(page, "() => document.activeElement === document.querySelector('.vl-prev')", "KB8: the focus handed to the line before")
            assert kept, "KB8: › kept the focus after a step"
            # a thin line of the selected spot, pressed: that line selected
            page.evaluate("""() => { const {view} = window.FINDALINE_VIEW, c = view.model.data.columns, sel = view.selected;
                const ends = Array.from(view.passingOf(sel.spot)).flatMap((r) => [[c.lat1.at(r), c.lon1.at(r)], [c.lat2.at(r), c.lon2.at(r)]]);
                window.FINDALINE_MAP.fitBounds(ends, {animate: false, padding: [80, 80]}); }""")
            spot = page.evaluate("() => Q.v().selected.spot")
            thin = page.evaluate("() => Q.until(() => Q.thin(), 'M8b: no point on a thin line of the selected spot takes it alone')")
            page.mouse.click(thin["x"], thin["y"])
            _wait(page, f"() => Q.v().selected && Q.v().selected.row === {thin['row']}", "M8b: the thin line selected")
            assert page.evaluate("() => [Q.v().selected.spot, Q.v().selected.row]") == [spot, thin["row"]], f"M8b: {thin}"
            # the card closed by its x: "Profile" among the line's actions brings it back (a desktop's button, as today's)
            _sel(page, ".r-card .fal-profile-chart", "D14, P6: the card")
            _click(page, ".r-card .r-dock-bar [aria-label='Close the profile']", "D14, P6")
            _sel(page, ".r-card", "D14, P6: the card closed", "detached")
            _sel(page, ".c-col-details .r-reprofile", "D14, P6: Profile")
            assert page.evaluate("() => [Q.text('.c-col-details .r-reprofile'), Q.m().profileClosed]") == ["Profile", True], "D14, P6: the closed card's button"
            _click(page, ".c-col-details .r-reprofile", "D14, P6")
            _sel(page, ".r-card .fal-profile-chart", "D14, P6: the card back")
            assert page.evaluate("() => [!!document.querySelector('.r-reprofile'), Q.m().profileClosed]") == [False, False], "D14, P6: the card back"
            # the facts of the selected line against today's page's for the same line
            link = page.evaluate("() => Q.m().lineLink(Q.v().selected.line)")
            _sel(page, ".vl-facts", "D15: the facts")
            facts = page.evaluate("() => Q.facts()")
            stands = page.evaluate("() => Q.v().selected.line.stands_for")
            stands_text = page.evaluate("() => Q.text('.vl-stands')")
            _clean(page, "W4")
            page.context.close()
            today = _open(browser, f"{parity_site['url']}#run={BIG}&line={urllib.parse.quote(link, safe='')}", WIDE, flag=False, script=PARITY)
            _sel(today, ".c-col-details .r-kv", "D15: today's facts")
            kv = today.evaluate("""() => Object.fromEntries([...document.querySelectorAll('.r-kv dt')].map((dt) =>
                [dt.textContent, dt.nextElementSibling.textContent.replace(/[\\u00a0\\u202f]/g, ' ')]))""")
            _clean(today, "W4, today's page")
            today.context.close()
            _facts_hold(facts, kv, stands, stands_text)
            # a link to a line outside the run: measured, the dock's bar and the profile's title as today's, asked once, no
            # note, nothing selected, the link kept
            page = _open(browser, f"{parity_site['url']}#run={BIG}&line={urllib.parse.quote(OUTSIDE, safe='')}", WIDE, script=PARITY + PROFILE_STUB)
            _sel(page, ".r-card .fal-profile-chart svg", "P13: the measured card")
            measured = page.evaluate("""() => ({bar: Q.text('.r-card .r-dock-bar > b'), title: Q.text('.r-card .fal-profile-title'), asked: window.PROFILE_ASKS,
                link: Q.m().measuredLink, note: Q.m().note, selected: !!Q.v().selected, hash: decodeURIComponent(location.hash), lift: Q.m().data.lift || 0})""")
            # the anchors' heights are the stub's ends raised by the run's A-frames (2 m here; today's test ran a run
            # without them: "A1 300.0 m → A2 301.0 m"; today's page shows the same title on this run)
            title = f"Measured: 80 m, A1 {300 + measured['lift']:.1f} m → A2 {301 + measured['lift']:.1f} m"
            assert measured["bar"] == "Measured profile" and measured["title"].startswith(title), f"P13: {measured}"
            assert measured["asked"] == ["49.5000000,19.1000000,49.5004000,19.1005000"], f"P13: {measured}"
            assert measured["link"] == OUTSIDE and measured["note"] is None and measured["selected"] is False, f"P13: {measured}"
            assert measured["hash"] == f"#run={BIG}&line={OUTSIDE}", f"P13: {measured}"
            _clean(page, "W4, the measured link")
            page.context.close()
            # a tight line's card: its clearance rounded down as the rows write it
            page = _view(browser, parity_site, WIDE)
            tight = page.evaluate("""() => { const v = Q.v(); const s = Array.from(v.order).find((x) => v.values.clr[v.shownOf(x)] < 1);
                return s === undefined ? null : {spot: s, clr: v.values.clr[v.shownOf(s)]}; }""")
            assert tight, "P10: the clip has no spot whose shown line is tight"
            page.evaluate(f"() => Q.v().select({tight['spot']})")
            _sel(page, ".r-card .fal-profile-title", "P10: the card", "attached")
            shown = f"{math.floor(tight['clr'] * 10 + 1e-9) / 10:.1f}"
            title = page.evaluate("() => Q.text('.r-card .fal-profile-title')")
            assert f"min. clearance {shown} m" in title, f"P10: {title} (clr {tight['clr']})"
            # the star's "New folder": the folder made, the line saved into it, the star named "Favourite"
            _wait(page, "() => Q.m().favouritesOn", "F2: the page keeps favourites")
            _click(page, ".vl-dhead .r-fav", "F2")
            _sel(page, ".r-pop .r-folder", "F2: the folders")
            picker = page.evaluate("() => [...document.querySelectorAll('.r-pop .r-folder')].map((b) => b.textContent.trim())")
            page.evaluate("() => [...document.querySelectorAll('.r-pop button')].find((b) => b.textContent.trim().startsWith('New folder')).click()")
            _sel(page, ".r-newfolder input", "F2: the new folder's name")
            page.fill(".r-newfolder input", "Trip")
            _click(page, ".r-newfolder button[type=submit]", "F2")
            _wait(page, "() => document.querySelector('.vl-dhead .r-fav').getAttribute('aria-label') === 'Favourite'", "F2: the star filled")
            saved = page.evaluate("""() => Q.poll(() => fetch('/api/favourites').then((r) => r.json()), (b) => b.favourites.length === 1 && b.folders.length === 1,
                'F2: the line saved on the server').then((b) => [b.folders.map((f) => f.name), b.favourites[0].folder_id === b.folders[0].id,
                b.favourites[0].line === Q.m().lineLink(Q.v().selected.line)])""")
            assert picker == ["Favourites (top level)"] and saved == [["Trip"], True, True], f"F2: {picker}, {saved}"
            _clean(page, "W4, the tight line and the folder")
            page.context.close()
            # Measure: "Cancel" ends the measuring; then refused by the server: its line under the button
            page = _view(browser, parity_site, WIDE, script=REFUSE_STUB)
            page.evaluate("() => Q.v().setLevel('spots')")
            measure = ".c-result-top .r-actions .r-act button"
            _click(page, measure, "E7")
            _wait(page, "() => window.FINDALINE_VIEW.map.isMeasuring", "E7: measuring")
            first = page.evaluate("() => Q.until(() => T.empty(false), 'E7: no empty point on the map')")
            page.mouse.click(first["x"], first["y"])
            _wait(page, "() => window.FINDALINE_VIEW.map.drawn().measured.length === 1", "E7: the first point")
            label = page.evaluate(f"() => document.querySelector({measure!r}).textContent.trim()")
            _click(page, measure, "E7")
            _wait(page, "() => !window.FINDALINE_VIEW.map.isMeasuring", "E7: Cancel ended the measuring")
            cancelled = page.evaluate(f"() => [window.FINDALINE_VIEW.map.drawn().measured.length, document.querySelector({measure!r}).textContent.trim()]")
            assert label == "Cancel" and cancelled == [0, "Measure"], f"E7: {label}, {cancelled}"
            _click(page, measure, "E4")
            _wait(page, "() => window.FINDALINE_VIEW.map.isMeasuring", "E4: measuring")
            page.mouse.click(first["x"], first["y"])
            second = page.evaluate("([x, y]) => { const b = T.box(); return {x: x > b.left + b.width / 2 ? x - 120 : x + 120, y}; }", [first["x"], first["y"]])
            page.mouse.click(second["x"], second["y"])
            _sel(page, ".r-act .r-error", "E4: the refusal's line")
            error = page.evaluate("() => [Q.text('.r-act .r-error'), document.querySelector('.r-act .r-error').getAttribute('role')]")
            assert error == ["Not computed: no profile here", "alert"], f"E4: {error}"
            _clean(page, "W4, Measure")
        finally:
            browser.close()


def _card_text(page, which: str) -> dict:
    """P9 for the selected line's card: its bar and readout show their whole text with the summary and with the
    cursor's long readout, the chart at least 120 px, the scale and the credits clear of the card (today's CARD_JS);
    the summary's boxes and texts returned."""
    _sel(page, ".r-card .fal-profile-chart svg", f"P9 ({which})")
    summary = page.evaluate(CARD_JS)
    assert summary["cut"] == [] and summary["chart"] >= 120, f"P9 ({which}): {summary}"
    assert not _meet(summary["card"], summary["scale"]) and not _meet(summary["card"], summary["credits"]), f"P9 ({which}): {summary}"
    page.evaluate("""() => { const h = document.querySelector('.r-card .fal-hover'), b = h.getBoundingClientRect();
        h.dispatchEvent(new MouseEvent('mousemove', {clientX: b.left + b.width * 0.4, clientY: b.top + 5, bubbles: true})); }""")
    _wait(page, "() => / from A1 /.test(Q.text('.r-card .fal-profile-readout'))", f"P9 ({which}): the cursor's readout")
    cursor = page.evaluate(CARD_JS)
    assert cursor["cut"] == [] and cursor["chart"] >= 120, f"P9 ({which}, the cursor's readout): {cursor}"
    page.evaluate("() => document.querySelector('.r-card .fal-hover').dispatchEvent(new MouseEvent('mouseleave', {bubbles: true}))")
    return summary


def _facts_hold(facts: list, kv: dict, stands, stands_text: str):
    """D15: the view's facts (its table's rows in order) hold today's values for the same line (today's `lineFacts`,
    `kv`): the anchors' places, heights and percentiles, the angle to the wall, prominence and drop, over trees, the
    height difference, above the ground, over water and filled gaps (neither on this clip: absent on both), the rigging
    (the same numbers in the same order: the zone, the A-frame, what the line needs, without the zone) and "Stands for"
    (its count, in the view's words: W5 a)."""
    view = {label: values for label, values in facts}
    lat, lon, elev = view[WORDS["ui.view.fact.lat"]], view[WORDS["ui.view.fact.lon"]], view[WORDS["ui.view.fact.elev"]]
    pct = view[WORDS["ui.view.fact.pct"]]
    for k, name in ((0, "Anchor 1"), (1, "Anchor 2")):
        known = "(percentile not known)" if pct[k] == WORDS["ui.view.fact.pct_none"] else f"({pct[k]} percentile)"
        assert kv[name].startswith(f"{lat[k]}, {lon[k]} · {elev[k]}") and known in kv[name], f"D15 (anchor {k + 1}): {kv[name]} / {lat, lon, elev, pct}"
    # the angle to the wall: today's "A1 18°, A2 19° (0° straight out)"; the view's a value per anchor
    angle = view.get(WORDS["ui.view.fact.angle"])
    assert (angle is None) == ("Angle to the wall" not in kv), f"D15 (angle): {angle}, {kv.get('Angle to the wall')}"
    if angle is not None:
        assert kv["Angle to the wall"].startswith(f"A1 {angle[0]}, A2 {angle[1]}"), f"D15 (angle): {angle}, {kv['Angle to the wall']}"
    # prominence and drop: today's "prominence 0 m / 9 m · drop 54 m / 50 m"
    prom, drop = view.get(WORDS["ui.view.fact.prom"]), view.get(WORDS["ui.view.fact.drop"])
    assert (prom is None) == (drop is None) == ("Anchors stand out" not in kv), f"D15 (prominence, drop): {prom}, {drop}, {kv.get('Anchors stand out')}"
    if prom is not None:
        assert kv["Anchors stand out"] == f"prominence {prom[0]} / {prom[1]} · drop {drop[0]} / {drop[1]}", f"D15 (prominence, drop): {prom}, {drop}, {kv['Anchors stand out']}"
    for label in (WORDS["ui.details.dh"], WORDS["ui.details.above"]):
        assert view.get(label) == ([kv[label]] if label in kv else None), f"D15 ({label}): {view.get(label)} / {kv.get(label)}"
    assert view.get(WORDS["ui.view.fact.over"]) == ([kv["Over trees/buildings"]] if "Over trees/buildings" in kv else None), \
        f"D15 (over trees): {view.get(WORDS['ui.view.fact.over'])}, {kv.get('Over trees/buildings')}"
    for today_label, key in (("Over water", "ui.view.fact.water"), ("Over filled gaps", "ui.view.fact.filled")):
        assert today_label not in kv and WORDS[key] not in view, f"D15 ({today_label}: not on this clip): {kv}, {view}"
    # the rigging: the group in both, the same numbers in the same order
    rigging = WORDS["ui.details.rigging"]
    assert (rigging in kv) == (rigging in view), f"D15 (rigging): {kv.get(rigging)}, {facts}"
    if rigging in kv:
        at = [label for label, _ in facts].index(rigging)
        numbers = lambda text: re.findall(r"\d+(?:\.\d+)?", text)  # noqa: E731
        mine = numbers(" ".join(v for _, values in facts[at + 1:] for v in values))
        assert mine == numbers(kv[rigging]), f"D15 (rigging's values): {facts[at:]}, {kv[rigging]}"
    # "Stands for": the same count in the view's words (W5 a) and today's
    joined = lambda text: re.sub(r"(?<=\d)[\s  ](?=\d)", "", text)  # noqa: E731 (a count's thousands)
    if stands == 1:
        assert stands_text == WORDS["ui.view.stands_for_n_one"] and kv[WORDS["ui.details.stands_for"]] == WORDS["ui.details.stands_for_n_one"], \
            f"D15 (stands for): {stands_text}, {kv}"
    else:
        assert stands_text == WORDS["ui.view.stands_for_n_other"].replace("{{n}}", _count(stands)), f"D15 (stands for): {stands_text}"
        assert joined(kv[WORDS["ui.details.stands_for"]]).startswith(f"{stands} "), f"D15 (stands for): {kv}"


def test_list_and_filters(parity_site):
    """The list's head and filters as today's tests use them: the Clearance chip's editor takes a typed value, the lines
    that pass fall, the chip says it, its × removes it (L16); the editor's × on neither row's number or unit, the two
    rows in one column, on a desktop and on a touch phone (its × 40 px) (L18); "N found. Why so many?" with its title,
    the box's text, its three rows adding up to the lines and its bar (L2); "Top level only" off, a class cleared hides
    exactly its lines, counted hidden by filters in the headline, "Clear all" shows them again (L3); the tight mark's
    key in its words with the A-frames and without (L14); the map moved off the run: the list's "No spots in view." and
    the map's status (X6); the desktop's "Home" leaves the result (H2); a run without `found` shows no found line and no
    box (L4)."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _view(browser, parity_site, WIDE)
            before = page.evaluate("() => Q.v().counts.lines")
            _chip(page, WORDS["ui.view.chip.clearance"], "L16")
            _sel(page, ".r-editor input[type=number]", "L16: the editor")
            page.evaluate("""() => { const input = document.querySelector('.r-editor input[type=number]'); input.value = '5';
                input.dispatchEvent(new Event('change', {bubbles: true})); }""")
            _wait(page, f"() => Q.v().counts.lines < {before}", "L16: the lines that pass fell")
            chips = page.evaluate("() => [...document.querySelectorAll('.vl-filters .u-chip.u-on')].map((c) => c.textContent.trim())")
            assert any(c.startswith(WORDS["ui.view.chip.clearance_min"].replace("{{a}}", "5.0")) for c in chips), f"L16: {chips}"
            _click(page, f".vl-filters .u-chip-x[aria-label=\"{WORDS['ui.view.chip.clearance_remove']}\"]", "L16")
            _wait(page, f"() => Q.v().counts.lines === {before}", "L16: the filter removed")
            # the Length editor: its × clear of the rows' numbers and units, the two rows in one column
            _chip(page, WORDS["ui.view.chip.length"], "L18")
            _sel(page, ".r-editor .r-editor-x", "L18: the editor")
            editors = {"desktop": page.evaluate(EDITOR_JS)}
            _click(page, ".r-editor .r-editor-x", "L18")
            _sel(page, ".r-editor", "L18: the editor closed", "detached")
            # "N found. Why so many?": the title, the box's text, its rows and its bar (today's test_same_lines)
            head = page.evaluate("""() => ({line: Q.text('.r-found-line'), title: document.querySelector('.r-found').title, found: Q.m().data.found,
                square: Q.m().data.square, lines: Q.v().count, count: Q.m().count})""")
            assert head["line"] == f"{WORDS['ui.result.found'].replace('{{n}}', _count(head['found']))} {WORDS['ui.result.why']}", f"L2: {head}"
            assert head["title"] == WORDS["ui.result.found_title"].replace("{{m}}", str(head["square"])) and "5 m anchor squares" in head["title"], f"L2: {head}"
            _click(page, ".r-why-link", "L2")
            _sel(page, "#r-why .r-why-row input", "L2: the box")
            why = page.evaluate("""() => ({text: Q.text('.r-why-text'), rows: [...document.querySelectorAll('.r-why-row')].map((r) => r.textContent),
                bar: !!document.querySelector('.r-why-bar'), needs: Q.m().needCounts()})""")
            assert head["count"] == head["lines"], f"L2: {head}"
            assert why["text"] == (WORDS["ui.result.why_text"].replace("{{found}}", _count(head["found"])) + " "
                                   + WORDS["ui.result.why_of"].replace("{{n}}", _count(head["lines"]))), f"L2: {why}"
            needs = why["needs"]
            assert needs and sum(needs) == head["lines"] and len(why["rows"]) == 3 and why["bar"], f"L2: {why}"
            assert why["rows"][2].startswith(f"{_count(needs[2])} need") and why["rows"][2].endswith("A-framesShow"), f"L2: {why}"
            # a class cleared, "Top level only" off (so the headline counts the class alone): exactly its lines hidden
            page.evaluate("() => Q.v().setTopOnly(false)")
            _wait(page, "() => Q.v().counts.hidden === 0", "L3: Top level only off")
            k = needs.index(max(needs))
            page.evaluate(f"() => document.querySelectorAll('#r-why .r-why-row input')[{k}].click()")
            _wait(page, f"() => Q.v().counts.hidden === {needs[k]}", "L3: the class's lines hidden")
            hidden = page.evaluate("() => [Q.v().counts.hidden, Q.text('.vl-count'), [...document.querySelectorAll('#r-why .r-why-row input')].map((i) => i.checked)]")
            assert hidden[0] == needs[k] and hidden[1].endswith(WORDS["ui.result.hidden"].replace("{{n}}", _count(needs[k]))), f"L3: {hidden}, {needs}"
            assert hidden[2] == [j != k for j in range(3)], f"L3: {hidden}"
            _click(page, ".vl-clear", "L3")
            _wait(page, "() => Q.v().counts.hidden === 0", "L3: Clear all")
            assert page.evaluate("() => [...document.querySelectorAll('#r-why .r-why-row input')].every((i) => i.checked)"), "L3: Clear all"
            page.evaluate("() => Q.v().setTopOnly(true)")
            # the tight mark's key under the list: its words with the run's A-frames, and without them (the run's head
            # given no A-frames in the page: the key is drawn again with the next selection)
            tight = page.evaluate("() => { const v = Q.v(); return Array.from(v.order).find((s) => v.values.clr[v.shownOf(s)] < 1); }")
            assert tight is not None, "L14: the clip has no spot whose shown line is tight"
            page.evaluate(f"() => Q.v().select({tight})")
            _sel(page, ".vl-key", "L14: the key", "attached")
            lift = WORDS["ui.tight.key_lift"].replace("{{m}}", "1").replace("{{lift}}", "2")
            assert page.evaluate("() => Q.text('.vl-key')") == lift, f"L14: {page.evaluate('() => Q.text(\".vl-key\")')}"
            page.evaluate(f"() => {{ Q.m().data.lift = 0; Q.v().select(null); Q.v().select({tight}); }}")
            plain = WORDS["ui.tight.key"].replace("{{m}}", "1")
            _wait(page, f"() => Q.text('.vl-key') === {plain!r}", "L14: the key without A-frames")
            page.evaluate(f"() => {{ Q.m().data.lift = 2; Q.v().select(null); }}")
            # the map moved off the run: no spot in view, the list and the map say so
            page.evaluate("""() => { const m = window.FINDALINE_MAP, c = m.getCenter(); m.setView([c.lat + 1, c.lng + 1], m.getZoom(), {animate: false}); }""")
            _wait(page, f"() => Q.text('.v-status-text') === {WORDS['ui.view.map.status_empty']!r}", "X6: the map's status")
            assert page.evaluate("() => Q.text('.vl-topblock .vl-note')") == WORDS["ui.view.none_in_view"], f"X6: {page.evaluate('() => Q.text(\".vl-topblock\")')}"
            _clean(page, "W5")
            # the desktop's "Home" leaves the result
            assert page.evaluate("() => [...document.querySelectorAll('.c-result-top .c-back')].map((b) => b.textContent.trim())") == ["Home"], "H2: the desktop's way back"
            _click(page, ".c-result-top .c-back", "H2")
            _wait(page, "() => location.hash === '#home' && !document.querySelector('.c-col-map')", "H2: Home")
            _clean(page, "W5, Home")
            page.context.close()
            # a run without `found`: no found line, no box
            page = _view(browser, parity_site, WIDE, run=NOFOUND, row="L4")
            none = page.evaluate("() => [Q.m().data.found ?? null, !!document.querySelector('.r-found-line'), !!document.querySelector('.r-why-link')]")
            assert none == [None, False, False], f"L4: {none}"
            _clean(page, "W5, the run without found")
            page.context.close()
            # a touch phone: the editor's × 40 px, clear of the rows
            page = _view(browser, parity_site, PHONE, row="L18")
            page.focus(".u-sheet-handle")
            page.keyboard.press("ArrowUp")
            page.keyboard.press("ArrowUp")
            _wait(page, "() => document.querySelector('.u-sheet').classList.contains('u-full')", "L18: the sheet at full")
            _wait(page, "() => { const s = document.querySelector('.u-sheet'); return Math.abs(s.getBoundingClientRect().height - parseFloat(s.style.height)) < 1; }",
                  "L18: the sheet at rest")
            _chip(page, WORDS["ui.view.chip.length"], "L18")
            _sel(page, ".r-editor .r-editor-x", "L18: the phone's editor")
            editors["phone"] = page.evaluate(EDITOR_JS)
            _clean(page, "W5, the phone")
        finally:
            browser.close()
    for kind, editor in editors.items():
        assert len(editor["rows"]) == 2, f"L18 ({kind}): {editor}"
        assert not any(_meet(editor["x"], b) for row in editor["rows"] for b in row), f"L18 ({kind}): {editor}"
        (num1, unit1), (num2, unit2) = editor["rows"]
        assert (num1[0], num1[2], unit1[2]) == (num2[0], num2[2], unit2[2]), f"L18 ({kind}): {editor}"
    assert editors["phone"]["x"][2] - editors["phone"]["x"][0] == 40, f"L18 (a touch screen's ×): {editors['phone']}"


def test_phone_frame(parity_site):
    """A phone (390 x 844, touch), as today's phone tests: a map with a sheet under a top bar, no bottom navigation,
    nothing wider than the window (Ph1, Q3); the data credits folded behind "Data credits" (M3); a selected line's 3D
    view in the sheet with the spot's other lines (D13); the sheet at full below the top bar (Ph3); its head's shadow
    once the body scrolls and none at the top, neither box moving (Ph4); "Home" in the pill returns (H2)."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _view(browser, parity_site, PHONE)
            frame = page.evaluate("""() => { const t = document.querySelector('.u-credits-toggle'), c = document.querySelector('.u-credits');
                return {sheet: !!document.querySelector('.u-sheet'), columns: !!document.querySelector('.c-col-list'), nav: !!document.querySelector('.u-bnav'),
                        pill: !!document.querySelector('.c-phone-top .c-pill'), wider: document.documentElement.scrollWidth > innerWidth,
                        toggle: getComputedStyle(t).display, label: t.textContent.trim(), folded: getComputedStyle(c).display}; }""")
            assert [frame[k] for k in ("sheet", "columns", "nav", "pill", "wider")] == [True, False, False, True, False], f"Ph1, Q3: {frame}"
            assert frame["toggle"] != "none" and frame["label"] == "Data credits" and frame["folded"] == "none", f"M3: {frame}"
            page.evaluate("() => { const v = Q.v(); v.select(Array.from(v.order).find((s) => v.passingCount(s) >= 2)); }")
            _sel(page, ".u-sheet .r-view3d", "D13: the 3D view in the sheet", "attached")
            view3d = page.evaluate("""() => { const a = document.querySelector('.u-sheet .r-view3d'), {view} = window.FINDALINE_VIEW, m = view.model;
                return [a.getAttribute('href'), '/view3d#run=' + encodeURIComponent(m.runId) + '&line=' + encodeURIComponent(m.lineLink(view.selected.line))]; }""")
            assert view3d[0].startswith(view3d[1] + "&also="), f"D13: {view3d}"
            page.focus(".u-sheet-handle")
            page.keyboard.press("ArrowUp")
            page.keyboard.press("ArrowUp")
            _wait(page, "() => document.querySelector('.u-sheet').classList.contains('u-full')", "Ph3: the sheet at full")
            _wait(page, "() => { const s = document.querySelector('.u-sheet'); return Math.abs(s.getBoundingClientRect().height - parseFloat(s.style.height)) < 1; }",
                  "Ph3: the sheet at rest")
            sheet = """() => { const box = (e) => { const r = e.getBoundingClientRect(); return [r.left, r.top, r.right, r.bottom].map(Math.round); };
                const h = document.querySelector('.u-sheet .u-sheet-head'), b = document.querySelector('.u-sheet .u-sheet-body');
                return {shadow: getComputedStyle(h).boxShadow, head: box(h), body: box(b), top: b.scrollTop,
                        bar: document.querySelector('.c-phone-top').getBoundingClientRect().bottom, sheet: document.querySelector('.u-sheet').getBoundingClientRect().top}; }"""
            top = page.evaluate(sheet)
            assert top["sheet"] >= top["bar"], f"Ph3: {top}"
            page.evaluate("() => { document.querySelector('.u-sheet .u-sheet-body').scrollTop = 120; }")
            _wait(page, "() => getComputedStyle(document.querySelector('.u-sheet .u-sheet-head')).boxShadow !== 'none'", "Ph4: the shadow")
            scrolled = page.evaluate(sheet)
            page.evaluate("() => { document.querySelector('.u-sheet .u-sheet-body').scrollTop = 0; }")
            _wait(page, "() => getComputedStyle(document.querySelector('.u-sheet .u-sheet-head')).boxShadow === 'none'", "Ph4: no shadow at the top")
            back = page.evaluate(sheet)
            assert top["shadow"] == "none" and scrolled["shadow"] != "none" and scrolled["top"] > 0, f"Ph4: {top}, {scrolled}"
            assert top["head"] == scrolled["head"] == back["head"] and top["body"] == scrolled["body"] == back["body"], f"Ph4: {top}, {scrolled}, {back}"
            assert not page.evaluate("() => document.documentElement.scrollWidth > innerWidth"), "Q3: wider than the window with a spot selected"
            _clean(page, "W6")
            back = page.evaluate("() => [...document.querySelectorAll('.c-phone-top .c-back')].map((b) => b.getAttribute('aria-label'))")
            assert back == ["Home"], f"H2: {back}"
            _click(page, ".c-phone-top .c-back", "H2")
            _wait(page, "() => location.hash === '#home' && !!document.querySelector('.u-bnav')", "H2: Home")
            assert page.evaluate("() => [location.hash, !!document.querySelector('.u-sheet')]") == ["#home", False], "H2: Home left the result"
            _clean(page, "W6, Home")
        finally:
            browser.close()


def test_load_failures_with_the_flag(parity_site):
    """With the view asked for (the flag set): a run whose store's body the browser cannot hold shows "This result is
    too large for this browser." as an alert, no view and no model (X1); a run without a store shows that it could not
    be loaded, its store's two files asked for (X2); neither asks for a data.js or lines.js (Q4)."""
    from playwright.sync_api import sync_playwright
    # the null body of lines.arrow: today's stubs from its XMLHttpRequest on (C_STUBS is the page's own stubs.js, and
    # its observer of the scripts is PARITY's, which observes the document: an init script runs before its element)
    xhr = TOO_LARGE_STUBS[TOO_LARGE_STUBS.index("const realOpen"):]
    assert TOO_LARGE_STUBS.startswith(C_STUBS) and "XMLHttpRequest.prototype.open" in xhr and "MutationObserver" not in xhr
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            for run, script, words, rows in ((BIG, xhr, WORDS["ui.result.too_large"], "X1"), (NOSTORE, "", WORDS["ui.result.store_failed"], "X2")):
                page = _open(browser, f"{parity_site['url']}#run={run}", WIDE, flag=False, script=FLAG + PARITY + script)
                _wait(page, "() => !!Q.text('.c-result-wait .c-error')", f"{rows}: the loading's error")
                got = page.evaluate(f"""() => ({{text: Q.text('.c-result-wait .c-error'), role: document.querySelector('.c-result-wait .c-error').getAttribute('role'),
                    flag: localStorage.getItem('findaline.view'), view: !!window.FINDALINE_VIEW, model: !!window.FINDALINE_RESULT,
                    files: Q.files({run!r}), scripts: window.DATA_SCRIPTS}})""")
                assert got["flag"] == "b" and got["text"] == words and not got["view"] and not got["model"], f"{rows}: {got}"
                if run == BIG:
                    assert got["role"] == "alert", f"X1: {got}"
                else:
                    assert sorted(f for f in got["files"] if f in RUN_DATA) == ["lines.arrow", "profiles.arrow"], f"X2: {got}"
                assert got["scripts"] == [] and not any(f in ("data.js", "lines.js") for f in got["files"]), f"Q4 ({rows}): {got}"
                _clean(page, f"W7, {rows}")
                page.context.close()
        finally:
            browser.close()
