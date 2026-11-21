"""The parity of today's result page and the result view (step 3d of docs/line-volume/spec-view.md part B): the checks
today's tests make of today's page (tests/test_shell_c.py, test_shell_c_flows.py, test_same_lines.py, test_web.py's
kit), made again of the view where no test of the view made them. Each assertion names the row of the parity list it
stands for (C1's list, H2 … X2) in its message; the list gives each row its verdict. Seven walks: the desktop's header
and map (credits, corners, the dark theme, Compare, Edit & run again), the desktop's kept layout (the panels' edges
and rails, the card's height, width and fold, the credits' button, a reload), a narrow and low window, a line's
details and its profile (the card's text and steadiness, its point on the map, a thin line pressed, the facts against
today's, a tight line's card, a new folder, Measure's error), the list's filters, a phone's frame, and the loading's
failures with the flag set. Playwright's Edge over the app's server, offline, on the result view's clip run
(clip_runs.view_clip); every wait is an event with a deadline, and no CSP violation and no page error anywhere. Run
from PowerShell (.claude/rules/browser-tests.md)."""

import math
import os
import re
import sys
import urllib.parse

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_shell_c import (BIG, C_STUBS, CARD_JS, EDITOR_JS, STEADY_JS, TOO_LARGE_STUBS, _corners,  # noqa: E402
                          add_credits, copy_clip, drop_store, stub_page)
from test_shell_c_view_list import _count  # noqa: E402
from test_shell_c_view_map import DESKTOP, FLAG, PHONE, WAIT, WORDS, _open, _state, view_clip  # noqa: E402,F401
from test_web import EDGE, _playwright, _server, store_with  # noqa: E402

pytestmark = pytest.mark.skipif(not os.path.exists(EDGE) or not _playwright(),
                                reason="needs Microsoft Edge and Playwright (group ui)")
COMPARED = "2026-10-30_120000_Compared_00000000000000e1"  # the clip's run again, for Compare
NOSTORE = "2026-10-29_120000_Old_00000000000000d1"        # a run without a store (has_lines false)
NOFOUND = "2026-10-28_130000_Plain_00000000000000c2"      # the clip's run with no `found` in its head
RUN_DATA = ("lines.arrow", "profiles.arrow", "data.js", "lines.js")
POINT = [50.1559508, 19.7562722]  # the job's centre (Edit & run again)
NARROW = {"viewport": {"width": 900, "height": 460}}
WIDE = {"viewport": {"width": 1400, "height": 900}}

# The walks' helpers (window.Q), beside test_shell_c_view_map's T: today's LAYOUT_JS, MAP_JS and HELPERS as they apply
PARITY = r"""
window.Q = {
  v() { return window.FINDALINE_VIEW.view; },
  m() { return this.v().model; },
  pause(ms = 300) { return new Promise((ok) => setTimeout(ok, ms)); },
  text(s) { return (document.querySelector(s) || {}).textContent || ""; },
  kept() { return JSON.parse(localStorage.getItem("findaline.layout") || "null"); },
  sep(side) { return document.querySelector(`.c-col-${side} > .c-split`); },
  rail(side) { return document.querySelector(`.c-col-${side} > .c-rail`); },
  width(side) { return document.querySelector(`.c-col-${side}`).offsetWidth; },
  aria(el) { return ["valuenow", "valuemin", "valuemax"].map((a) => Number(el.getAttribute("aria-" + a))); },
  key(el, k, shift = false) { el.dispatchEvent(new KeyboardEvent("keydown", {key: k, shiftKey: shift, bubbles: true, cancelable: true})); },
  pointer(el, type, x, y) { el.dispatchEvent(new PointerEvent(type, {bubbles: true, cancelable: true, pointerId: 1, pointerType: "mouse",
    button: 0, buttons: type === "pointerup" ? 0 : 1, clientX: x, clientY: y})); },
  /** A drag of `el` by dx, dy: the layout kept while the pointer is down, then once released (today's drag). */
  async drag(el, dx, dy) { const r = el.getBoundingClientRect(), x = r.left + r.width / 2, y = r.top + Math.min(r.height / 2, 40);
    this.pointer(el, "pointerdown", x, y); this.pointer(el, "pointermove", x + dx / 2, y + dy / 2); this.pointer(el, "pointermove", x + dx, y + dy);
    await this.pause(); const during = this.kept(); this.pointer(el, "pointerup", x + dx, y + dy); await this.pause(); return during; },
  shown(s) { const e = document.querySelector(s); return !!e && e.getClientRects().length > 0; },
  credits() { return {toggle: this.shown(".u-credits-toggle"), credits: this.shown(".u-credits")}; },
  rect(s) { const e = document.querySelector(s); if (!e) return null; const b = e.getBoundingClientRect(); return [b.left, b.top, b.right, b.bottom]; },
  /** The run's files the page asked for (its resource timing). */
  files(id) { return performance.getEntriesByType("resource").map((e) => new URL(e.name).pathname)
    .filter((p) => p.startsWith("/runs/" + encodeURIComponent(id) + "/")).map((p) => p.split("/").pop()); },
  /** The facts' table: each row's label and its values (no-break spaces as spaces). */
  facts() { const out = {}; document.querySelectorAll(".vl-facts tbody tr").forEach((tr) => { const th = tr.querySelector("th");
    out[th.firstChild ? th.firstChild.textContent.trim() : th.textContent.trim()] = [...tr.querySelectorAll("td")].map((td) => td.textContent.replace(/[  ]/g, " ").trim()); });
    return out; },
};
// every script of a run's data.js or lines.js the page adds (the document itself observed: this runs before its element)
window.DATA_SCRIPTS = [];
new MutationObserver((changes) => changes.forEach((c) => c.addedNodes.forEach((n) => {
  if (n.tagName === "SCRIPT" && /(data|lines)\.js/.test(n.src || "")) DATA_SCRIPTS.push(n.src);
}))).observe(document, {childList: true, subtree: true});
"""


@pytest.fixture
def parity_site(tmp_path, view_clip):
    """A data folder served by the app: the clip's run (BIG) with a source's data credits and a finished job that made
    it (Edit & run again), the same run for Compare (COMPARED), a run without a store (NOSTORE) and the clip's run with
    no `found` in its head (NOFOUND); yields the app page's address and the job."""
    from jobs import Jobs
    folder = tmp_path / "data"
    copy_clip(view_clip, folder, BIG, "Clip")
    copy_clip(view_clip, folder, COMPARED, "Compared run")
    copy_clip(view_clip, folder, NOSTORE, "Old run")
    drop_store(folder, NOSTORE)
    copy_clip(view_clip, folder, NOFOUND, "Clip without found")
    store_with(folder / "runs" / NOFOUND, head={"found": None})
    add_credits(folder, BIG)
    jobs = Jobs(str(folder))
    job = jobs.add({"params": {"lat": POINT[0], "lon": POINT[1], "radius": 150}, "geometry": None}, "Clip")
    jobs.set(job, "done", run_id=BIG)
    page_path = stub_page(folder, "paritytest")
    with _server(folder) as port:
        yield {"url": f"http://127.0.0.1:{port}/{page_path}?ui=c", "job": job}


def _view(browser, site: dict, context: dict, run: str = BIG, script: str = ""):
    """The view of a run with the helpers, drawn."""
    page = _open(browser, f"{site['url']}#run={run}", context, script=PARITY + script)
    page.wait_for_selector(".vl-main", timeout=WAIT)
    return page


def _clean(page, rows: str):
    """No CSP violation and no page error on the page (every walk)."""
    assert page.evaluate("() => window.CSP_VIOLATIONS") == [], f"Q1 ({rows}): {page.evaluate('() => window.CSP_VIOLATIONS')}"
    assert page.errors == [], f"Q2 ({rows}): {page.errors}"


def _meet(a, b) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def test_desktop_header_and_map(parity_site):
    """A desktop (1400 x 900): the run's data credits in the map's attribution, not folded without the card, with the
    link to its ATTRIBUTION.txt (M2); the scale right above the credits where they run under it, also after a zoom out
    and in (M5); the map's controls in the dark theme, zoom and layers alike, never Leaflet's light grey, focused and
    disabled shown (M7); Compare lists the other runs with a store and offers no run without one (C1), a ticked run is
    read from its lines.arrow alone, every line of it (C2), Esc in its menu closes it, the focus back on "Compare" and
    the selection kept (C3); "Edit & run again" opens the form with the job's request (H3)."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _view(browser, parity_site, WIDE)
            credits = page.evaluate("""() => ({text: Q.text('.leaflet-control-attribution'), toggle: getComputedStyle(document.querySelector('.u-credits-toggle')).display,
                links: [...document.querySelectorAll('.leaflet-control-attribution a')].map((a) => a.getAttribute('href'))})""")
            assert "FABDEM V1-2 © University of Bristol" in credits["text"] and credits["toggle"] == "none", f"M2: {credits}"
            assert f"/runs/{BIG}/ATTRIBUTION.txt" in credits["links"], f"M2: {credits['links']}"
            # the corners: the scale right above the credits (they run under it at this width), after a zoom out and in
            for name, by in (("start", 0), ("out", -3), ("in", 3)):
                page.evaluate(f"() => window.FINDALINE_MAP.setZoom(window.FINDALINE_MAP.getZoom() + {by}, {{animate: false}})")
                found = _corners(page)
                assert found["under"] and 0 <= found["attribution"][1] - found["scale"][3] <= 10, f"M5 ({name}): {found}"
            # the dark theme: the zoom and the layers button alike and dark, the focused button apart, the disabled marked
            dark = page.evaluate("""async () => { const root = document.querySelector('.ui'), m = window.FINDALINE_MAP;
                const colour = (q) => getComputedStyle(document.querySelector(q)).backgroundColor;
                const light = {panel: colour('.c-col-list'), zoom: colour('.leaflet-control-zoom-in')};
                root.dataset.theme = 'dark'; m.setZoom(m.getMaxZoom(), {animate: false}); await T.frames();
                const out = document.querySelector('.leaflet-control-zoom-out'); out.focus(); await T.frames();
                const r = {light, panel: colour('.c-col-list'), zoom: colour('.leaflet-control-zoom-in'), layers: colour('.leaflet-control-layers'),
                           disabled: document.querySelector('.leaflet-control-zoom-in').classList.contains('leaflet-disabled'), focused: colour('.leaflet-control-zoom-out')};
                out.blur(); delete root.dataset.theme; await T.frames(); return r; }""")
            assert dark["disabled"] and dark["zoom"] == dark["layers"], f"M7: {dark}"
            assert dark["zoom"] not in ("rgb(255, 255, 255)", "rgb(244, 244, 244)", dark["light"]["zoom"]), f"M7: {dark}"
            assert dark["panel"] != dark["light"]["panel"] and dark["focused"] not in (dark["zoom"], "rgb(244, 244, 244)"), f"M7: {dark}"
            page.evaluate("() => window.FINDALINE_MAP.setZoom(window.FINDALINE_MAP.getZoom() - 3, {animate: false})")
            # Compare's menu: Esc closes it, the focus back on its button, the selection kept
            _state(page, "view.select(Array.from(view.order)[0]);")
            selected = page.evaluate("() => Q.v().selected.row")
            compare = ".c-result-top .r-actions button:has-text('Compare')"
            page.click(compare)
            page.wait_for_function("() => !!document.activeElement.closest('.r-pop')", timeout=WAIT)
            page.keyboard.press("Escape")
            page.wait_for_selector(".r-pop", state="detached", timeout=WAIT)
            back = page.evaluate("() => [document.activeElement.textContent.trim(), Q.v().selected && Q.v().selected.row]")
            assert back == ["Compare", selected], f"C3: {back}"
            # the other runs: a run with a store listed, one without not offered; ticked, read from its lines.arrow alone
            page.click(compare)
            page.wait_for_selector(".r-other", timeout=WAIT)
            listed = page.evaluate("() => [...document.querySelectorAll('.r-other')].map((o) => o.textContent.split(' · ')[0])")
            assert "Compared run" in listed and "Old run" not in listed, f"C1: {listed}"
            page.evaluate("() => [...document.querySelectorAll('.r-other')].find((o) => /Compared run/.test(o.textContent)).querySelector('input').click()")
            page.wait_for_function("() => Q.m().others.size === 1 && ![...document.querySelectorAll('.r-other')].some((o) => /loading/.test(o.textContent))",
                                   timeout=WAIT)
            got = page.evaluate(f"""() => ({{others: Object.fromEntries([...Q.m().others.values()].map((o) => [o.info.id, o.count])),
                lines: Q.v().count, compared: Q.files({COMPARED!r}), old: Q.files({NOSTORE!r})}})""")
            assert got["others"] == {COMPARED: got["lines"]}, f"C2: {got['others']}"
            assert [f for f in got["compared"] if f in RUN_DATA] == ["lines.arrow"] and got["old"] == [], f"C1, C2: {got}"
            page.keyboard.press("Escape")
            page.wait_for_selector(".r-pop", state="detached", timeout=WAIT)
            # Edit & run again: the form with the job's request
            page.click(".c-result-top a:has-text('Edit & run again')")
            page.wait_for_function(f"() => location.hash.startsWith('#new&edit={parity_site['job']}') && !!document.querySelector('.c-subtitle') "
                                   "&& !!window.FINDALINE_SEARCH && !!window.FINDALINE_SEARCH.point", timeout=WAIT)
            edit = page.evaluate("() => [document.querySelector('.c-subtitle').textContent, window.FINDALINE_SEARCH.point]")
            assert edit[0] == "Edit & run again" and [round(v, 5) for v in edit[1]] == [round(v, 5) for v in POINT], f"H3: {edit}"
            _clean(page, "W1")
        finally:
            browser.close()


def test_desktop_layout_kept(parity_site):
    """A desktop (1400 x 900), as today's test_shell_c_layout: the list's edge by keys (±16, Shift ±64, Home, End), a
    double click its default, a drag, kept when released (KB1, KB2), the details' too; the tab and the rail collapse
    and expand a panel, the focus to the rail and then the edge, Enter on the edge, the rails' labels (KB3); a
    selection leaves the collapsed details collapsed, its rail naming the spot (KB4); the card's height (Home: its least,
    ArrowUp, a drag) and its left edge by keys, its fold, all kept (P4, P5); the data credits' button with the card
    open (M4); the layout found again after a reload (KB5)."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _view(browser, parity_site, WIDE)
            r = page.evaluate("""async () => { await Q.pause(); const r = {};
              r.start = {cols: document.querySelector('.c-cols').clientWidth, list: Q.width('list'), details: Q.width('details'), kept: Q.kept(),
                         listAria: Q.aria(Q.sep('list')), detailsAria: Q.aria(Q.sep('details')),
                         tabs: [document.querySelector('.c-col-list > .c-col-tab').getAttribute('aria-label'), document.querySelector('.c-col-details > .c-col-tab').getAttribute('aria-label')]};
              Q.key(Q.sep('list'), 'ArrowRight'); await Q.pause(); Q.key(Q.sep('list'), 'ArrowRight', true); await Q.pause();
              r.listKeys = {width: Q.width('list'), aria: Q.aria(Q.sep('list')), kept: Q.kept().list.w};
              Q.key(Q.sep('list'), 'Home'); await Q.pause(); r.listHome = Q.width('list');
              Q.key(Q.sep('list'), 'End'); await Q.pause(); r.listEnd = Q.width('list');
              Q.sep('list').dispatchEvent(new MouseEvent('dblclick', {bubbles: true, cancelable: true})); await Q.pause();
              r.listReset = [Q.width('list'), Q.kept().list.w];
              const during = await Q.drag(Q.sep('list'), 40, 0); r.listDrag = {width: Q.width('list'), during: during.list.w, kept: Q.kept().list.w};
              Q.sep('list').dispatchEvent(new MouseEvent('dblclick', {bubbles: true, cancelable: true})); await Q.pause();
              Q.key(Q.sep('details'), 'ArrowLeft'); await Q.pause(); r.detailsKey = [Q.width('details'), Q.kept().details.w];
              const d2 = await Q.drag(Q.sep('details'), -30, 0); r.detailsDrag = {width: Q.width('details'), during: d2.details.w, kept: Q.kept().details.w};
              Q.sep('details').dispatchEvent(new MouseEvent('dblclick', {bubbles: true, cancelable: true})); await Q.pause();
              r.detailsReset = [Q.width('details'), Q.kept().details.w];
              document.querySelector('.c-col-list > .c-col-tab').click(); await Q.pause();
              r.listRail = {collapsed: document.querySelector('.c-col-list').className, width: Q.width('list'), focus: document.activeElement === Q.rail('list'),
                            label: Q.text('.c-col-list > .c-rail .c-rail-text'), auto: !!document.querySelector('.c-col-list .c-rail-auto'), kept: Q.kept().list.open};
              Q.rail('list').click(); await Q.pause();
              r.listOpen = {open: !document.querySelector('.c-col-list.c-collapsed'), focus: document.activeElement === Q.sep('list'), kept: Q.kept().list.open};
              Q.key(Q.sep('details'), 'Enter'); await Q.pause();
              r.detailsRail = {collapsed: !!document.querySelector('.c-col-details.c-collapsed'), focus: document.activeElement === Q.rail('details'),
                               label: Q.text('.c-col-details > .c-rail .c-rail-text'), kept: Q.kept().details.open};
              r.lines = Q.v().counts.lines;
              return r; }""")
            s = r["start"]
            assert (s["list"], s["details"]) == (372, 380) and s["kept"] is None, f"KB1: {s}"
            list_max, details_max = min(560, s["cols"] - 360 - 380), min(600, s["cols"] - 360 - 372)
            assert s["listAria"] == [372, 260, list_max] and s["detailsAria"] == [380, 300, details_max], f"KB1: {s}"
            assert s["tabs"] == ["Collapse the list", "Collapse the details"], f"KB3: {s['tabs']}"
            assert r["listKeys"] == {"width": 452, "aria": [452, 260, list_max], "kept": 452}, f"KB1: {r['listKeys']}"
            assert (r["listHome"], r["listEnd"], r["listReset"]) == (260, list_max, [372, 372]), f"KB1: {r}"
            assert r["listDrag"] == {"width": 412, "during": 372, "kept": 412}, f"KB2: {r['listDrag']}"
            assert r["detailsKey"] == [396, 396] and r["detailsDrag"] == {"width": 426, "during": 396, "kept": 426}, f"KB1, KB2: {r}"
            assert r["detailsReset"] == [380, 380], f"KB1: {r['detailsReset']}"
            lr = r["listRail"]
            assert "c-collapsed" in lr["collapsed"] and "c-forced" not in lr["collapsed"] and lr["width"] == 36, f"KB3: {lr}"
            assert lr["focus"] and not lr["auto"] and lr["kept"] is False, f"KB3: {lr}"
            assert lr["label"] == WORDS["ui.view.map.rail_list"].replace("{{n}}", _count(r["lines"])), f"KB3: {lr['label']}"
            assert r["listOpen"] == {"open": True, "focus": True, "kept": True}, f"KB3: {r['listOpen']}"
            assert r["detailsRail"] == {"collapsed": True, "focus": True, "label": WORDS["ui.view.map.rail_details"], "kept": False}, f"KB3: {r['detailsRail']}"
            # a selection: the details stay collapsed, their rail names the spot; the rail opens them, the focus to the edge
            _state(page, "view.select(Array.from(view.order)[0]);")
            page.wait_for_function("() => /Spot/.test(Q.text('.c-col-details > .c-rail .c-rail-text'))", timeout=WAIT)
            sel = page.evaluate("() => [!!document.querySelector('.c-col-details.c-collapsed'), Q.text('.c-col-details > .c-rail .c-rail-text'), Q.v().label(Q.v().selected.spot)]")
            assert sel[0] and sel[1] == WORDS["ui.view.map.rail_spot"].replace("{{label}}", sel[2]), f"KB4: {sel}"
            page.evaluate("() => Q.rail('details').click()")
            page.wait_for_function("() => !document.querySelector('.c-col-details.c-collapsed') && document.activeElement === Q.sep('details')", timeout=WAIT)
            # the card: its least height, ArrowUp, a drag of its top; its left edge; its fold; the credits' button
            page.wait_for_selector(".r-card .fal-profile-chart", timeout=WAIT)
            c = page.evaluate("""async () => { await Q.pause(600); const card = () => document.querySelector('.r-card'), top = () => document.querySelector('.r-card .r-card-top');
              const r = {}; r.credits = Q.credits();
              Q.key(top(), 'Home'); await Q.pause(); r.home = {height: card().offsetHeight, kept: Q.kept().profile.h, aria: Q.aria(top())};
              Q.key(top(), 'ArrowUp'); await Q.pause(); r.up = {height: card().offsetHeight, kept: Q.kept().profile.h};
              const during = await Q.drag(top(), 0, -40); r.drag = {height: card().offsetHeight, during: during.profile.h, kept: Q.kept().profile.h};
              Q.key(document.querySelector('.r-card .r-card-l'), 'ArrowRight'); await Q.pause();
              r.left = {left: Math.round(card().getBoundingClientRect().left - document.querySelector('.c-col-map').getBoundingClientRect().left), kept: [Q.kept().profile.l, Q.kept().profile.r]};
              document.querySelector('.r-card .r-fold').click(); await Q.pause(); r.folded = [card().classList.contains('r-card-folded'), Q.kept().profile.folded];
              document.querySelector('.r-card .r-fold').click(); await Q.pause(); r.unfolded = [card().classList.contains('r-card-folded'), Q.kept().profile.folded];
              return r; }""")
            assert c["credits"] == {"toggle": True, "credits": False}, f"M4: {c['credits']}"
            assert c["home"]["height"] == c["home"]["kept"] == c["home"]["aria"][1] == c["home"]["aria"][0], f"P4: {c['home']}"
            h = c["home"]["height"]
            assert c["up"] == {"height": h + 16, "kept": h + 16}, f"P4: {c['up']}"
            assert c["drag"] == {"height": h + 56, "during": h + 16, "kept": h + 56}, f"P4: {c['drag']}"
            assert c["left"] == {"left": 28, "kept": [28, 12]}, f"P4: {c['left']}"
            assert c["folded"] == [True, True] and c["unfolded"] == [False, False], f"P5: {c}"
            # the data credits' button while the card is open: they open, and fold again
            page.click(".u-credits-toggle")
            page.wait_for_function("() => document.querySelector('.u-credits-toggle').getAttribute('aria-expanded') === 'true'", timeout=WAIT)
            assert page.evaluate("() => Q.credits()") == {"toggle": True, "credits": True}, "M4: the credits opened"
            page.click(".u-credits-toggle")
            page.wait_for_function("() => document.querySelector('.u-credits-toggle').getAttribute('aria-expanded') === 'false'", timeout=WAIT)
            assert page.evaluate("() => Q.credits()") == {"toggle": True, "credits": False}, "M4: the credits folded again"
            # a layout to find again: the list collapsed, wider details, a taller card, its left edge further in
            before = page.evaluate("""async () => { document.querySelector('.c-col-list > .c-col-tab').click(); await Q.pause();
              Q.key(Q.sep('details'), 'ArrowLeft', true); await Q.pause();
              Q.key(document.querySelector('.r-card .r-card-top'), 'ArrowUp', true); await Q.pause();
              Q.key(document.querySelector('.r-card .r-card-l'), 'ArrowRight', true); await Q.pause();
              return Q.kept(); }""")
            assert before["list"]["open"] is False and before["details"]["w"] == 444 and before["profile"]["l"] == 92, f"KB5: {before}"
            _clean(page, "W2")
            page.reload()
            page.wait_for_function("() => !!window.FINDALINE_VIEW && !!document.querySelector('.r-card .fal-profile-chart') && !!document.querySelector('.c-col-list > .c-rail')",
                                   timeout=WAIT)
            page.evaluate("() => Q.pause(600)")
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
    selection's card opens folded, and what is changed there (unfolded, its height and left edge) is not kept (P7)."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _view(browser, parity_site, NARROW)
            r = page.evaluate("""async () => { await Q.pause(); const r = {};
              r.forced = {details: document.querySelector('.c-col-details').className, auto: Q.text('.c-col-details .c-rail-auto'),
                          list: [!document.querySelector('.c-col-list.c-collapsed'), Q.width('list')], kept: Q.kept()};
              Q.rail('details').click(); await Q.pause();
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
              view.select(Array.from(view.order)[0]); for (let k = 0; k < 50 && !document.querySelector('.r-card'); k++) await Q.pause(100);
              await Q.pause(); const card = () => document.querySelector('.r-card');
              const r = {folded: card().classList.contains('r-card-folded'), mapHeight: document.querySelector('.c-col-map').clientHeight, credits: Q.credits()};
              document.querySelector('.r-card .r-fold').click(); await Q.pause(); r.unfolded = !card().classList.contains('r-card-folded');
              Q.key(document.querySelector('.r-card .r-card-top'), 'Home'); await Q.pause();
              await Q.drag(document.querySelector('.r-card .r-card-top'), 0, -20);
              Q.key(document.querySelector('.r-card .r-card-l'), 'ArrowRight'); await Q.pause();
              r.same = localStorage.getItem('findaline.layout') === before;
              r.left = Math.round(card().getBoundingClientRect().left - document.querySelector('.c-col-map').getBoundingClientRect().left);
              return r; }""")
            assert low["folded"] and low["mapHeight"] < 420 and low["credits"] == {"toggle": True, "credits": False}, f"P7: {low}"
            assert low["unfolded"] and low["same"] and low["left"] == 28, f"P7: {low}"
            _clean(page, "W3")
        finally:
            browser.close()


# A point 14 px beside a spot's shown line (in view, at Spots) that a finger's reach takes alone and a mouse's reach
# misses, no number's shape there and clear of the controls: {x, y} in the viewport and the spot; null: none
BESIDE_JS = """() => { const {view, map} = window.FINDALINE_VIEW, leaflet = window.FINDALINE_MAP, box = T.box(), f = T.free(), controls = T.controls();
  for (const spot of Array.from(view.inView.spots)) { const e = T.ends(view.shownOf(spot)), len = Math.hypot(e[2] - e[0], e[3] - e[1]);
    if (len < 60) continue;
    for (let t = 0.3; t <= 0.7; t += 0.1) for (const side of [1, -1]) {
      const x = Math.round(e[0] + (e[2] - e[0]) * t - side * 14 * (e[3] - e[1]) / len), y = Math.round(e[1] + (e[3] - e[1]) * t + side * 14 * (e[2] - e[0]) / len);
      if (x < f[0] + 30 || y < f[1] + 30 || x > f[2] - 30 || y > f[3] - 30) continue;
      const vx = x + box.left, vy = y + box.top;
      if (controls.some((c) => vx > c.left - 24 && vx < c.right + 24 && vy > c.top - 24 && vy < c.bottom + 24)) continue;
      const lp = leaflet.containerPointToLayerPoint([x, y]);
      if (map.markAt(lp.x, lp.y, true) || map.markAt(lp.x, lp.y, false)) continue;
      const finger = map.pick(lp.x, lp.y, true).found, mouse = map.pick(lp.x, lp.y, false).found;
      if (finger.length === 1 && finger[0].spot === spot && mouse.length === 0) return {x: vx, y: vy, spot}; } }
  return null; }"""
# What the browser sends there for a click of the mouse, a finger's tap, and WebKit's tap (a "mouse" click after a
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


def _thin_point(page):
    """A point on a thin line of the selected spot (one of its other passing lines) where a mouse's press takes that
    line alone, no number's shape there; the map zoomed to the spot's lines first. None: no such point."""
    return page.evaluate("""async () => { const {view, map} = window.FINDALINE_VIEW, leaflet = window.FINDALINE_MAP, c = view.model.data.columns;
      const sel = view.selected, rows = Array.from(view.passingOf(sel.spot)).filter((r) => r !== sel.row);
      const ends = [sel.row, ...rows].flatMap((r) => [[c.lat1.at(r), c.lon1.at(r)], [c.lat2.at(r), c.lon2.at(r)]]);
      leaflet.fitBounds(ends, {animate: false, padding: [80, 80]}); await T.frames(); await T.frames();
      const box = T.box(), controls = T.controls(), f = T.free();
      for (const row of rows) { const e = T.ends(row);
        for (let t = 0.2; t <= 0.8; t += 0.05) { const x = e[0] + (e[2] - e[0]) * t, y = e[1] + (e[3] - e[1]) * t;
          if (x < f[0] + 30 || y < f[1] + 30 || x > f[2] - 30 || y > f[3] - 30) continue;
          const vx = x + box.left, vy = y + box.top;
          if (controls.some((k) => vx > k.left - 8 && vx < k.right + 8 && vy > k.top - 8 && vy < k.bottom + 8)) continue;
          const lp = leaflet.containerPointToLayerPoint([x, y]);
          if (map.markAt(lp.x, lp.y, false)) continue;
          const hit = map.pick(lp.x, lp.y, false).found;
          if (hit.length === 1 && hit[0].row === row) return {x: vx, y: vy, row}; } }
      return null; }""")


def test_details_and_profile(parity_site):
    """A desktop: 14 px beside a line a finger's tap takes it and the mouse's click does not, also as WebKit sends a
    tap (M11); the card's compact form (no head row, the line's facts in its bar and its title "Profile: …", the
    legend and the 1:1 scale under "Rigging and layers", toggled) (P3); its bar and readout show their whole text, the
    chart at least 120 px, the scale and the credits clear of the card, and the card, chart and readout steady under a
    moving cursor at the default width and at the narrowest and lowest (P9); a touch on the chart puts the point on the
    map, gone with the next line (P12, M23); a thin line of the selected spot pressed selects that line (M8b); the facts'
    values are today's for the same line (D15); a tight line's card writes its clearance rounded down as the rows do
    (P10); the star's "New folder" makes a folder and saves the line into it (F2); a measurement the server refuses
    shows "Not computed: …" (E4)."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _view(browser, parity_site, WIDE)
            # 14 px beside a line: a finger's tap takes it, the mouse's click does not; WebKit's tap too
            _state(page, "view.setLevel('spots');")
            beside = page.evaluate(BESIDE_JS)
            assert beside, "M11: no point 14 px beside a line that a finger alone reaches"
            taps = page.evaluate(TAPS_JS, beside)
            assert taps == {"mouse": None, "finger": beside["spot"], "webkit": beside["spot"]}, f"M11: {taps}"
            _state(page, "view.select(Array.from(view.order).find((s) => view.passingCount(s) >= 3));")
            page.wait_for_selector(".r-card .fal-profile-chart svg", timeout=WAIT)
            page.wait_for_function("() => /FABDEM/.test(document.querySelector('.leaflet-control-attribution').textContent)", timeout=WAIT)
            compact = page.evaluate("""() => ({head: !!document.querySelector('.r-card .fal-profile-head'), title: Q.text('.r-card .fal-profile-title'),
                facts: Q.text('.r-card .r-facts'), factsTitle: document.querySelector('.r-card .r-facts').getAttribute('title'),
                legend: Q.shown('.r-card .fal-profile-legend'), scale: Q.shown('.r-card .fal-scale')})""")
            assert not compact["head"] and compact["title"].startswith("Profile: ") and compact["facts"].startswith("min. clearance "), f"P3: {compact}"
            assert compact["factsTitle"] == compact["title"] and compact["title"].endswith(compact["facts"].split(" · ")[0]), f"P3: {compact}"
            assert not compact["legend"] and not compact["scale"], f"P3: {compact}"
            page.click(".r-card .r-dock-bar .u-chip")
            page.wait_for_function("() => Q.shown('.r-card .fal-profile-legend') && Q.shown('.r-card .fal-scale')", timeout=WAIT)
            before = page.evaluate("() => Q.text('.r-card .fal-scale')")
            page.click(".r-card .fal-scale")
            page.wait_for_function(f"() => Q.text('.r-card .fal-scale') !== {before!r}", timeout=WAIT)
            rig = page.evaluate("() => [Q.text('.r-card .fal-scale'), !!document.querySelector('.r-card .fal-profile-controls .fal-key .fal-scale')]")
            assert before.startswith("1:1 scale") and rig == ["Auto scale", True], f"P3: {before}, {rig}"
            page.click(".r-card .fal-scale")
            page.click(".r-card .r-dock-bar .u-chip")
            page.wait_for_function("() => !Q.shown('.r-card .fal-profile-legend')", timeout=WAIT)
            # the card's text whole, the chart's height, clear of the scale and the credits; steady under a moving cursor
            summary = page.evaluate(CARD_JS)
            assert summary["cut"] == [] and summary["chart"] >= 120, f"P9: {summary}"
            assert not _meet(summary["card"], summary["scale"]) and not _meet(summary["card"], summary["credits"]), f"P9: {summary}"
            page.evaluate("""() => { const h = document.querySelector('.r-card .fal-hover'), b = h.getBoundingClientRect();
                h.dispatchEvent(new MouseEvent('mousemove', {clientX: b.left + b.width * 0.4, clientY: b.top + 5, bubbles: true})); }""")
            page.wait_for_function("() => / from A1 /.test(Q.text('.r-card .fal-profile-readout'))", timeout=WAIT)
            cursor = page.evaluate(CARD_JS)
            assert cursor["cut"] == [] and cursor["chart"] >= 120, f"P9 (the cursor's readout): {cursor}"
            page.evaluate("() => document.querySelector('.r-card .fal-hover').dispatchEvent(new MouseEvent('mouseleave', {bubbles: true}))")
            steady = {"default": page.evaluate(STEADY_JS)}
            for edge in (".r-card .r-card-l", ".r-card .r-card-top"):
                page.focus(edge)
                page.keyboard.press("Home")
            wide = steady["default"][0]["card"]
            page.wait_for_function(f"() => document.querySelector('.r-card').getBoundingClientRect().width < {wide[2] - wide[0] - 50}", timeout=WAIT)
            steady["narrow"] = page.evaluate(STEADY_JS)
            for name, states in steady.items():
                assert len({(tuple(s["card"]), tuple(s["chart"]), tuple(s["readout"])) for s in states}) == 1, f"P9 ({name}): {states}"
                assert all(s["inside"] and s["cut"] == [] for s in states) and any(" from A1" in s["text"] for s in states), f"P9 ({name}): {states}"
            # a touch on the chart: its point on the map; the next line takes it away
            touch = page.evaluate("""async () => { const {view, map} = window.FINDALINE_VIEW, h = document.querySelector('.r-card .fal-hover'), b = h.getBoundingClientRect();
                h.dispatchEvent(new PointerEvent('pointerdown', {pointerType: 'touch', pointerId: 7, bubbles: true, clientX: b.left + b.width / 2, clientY: b.top + 5}));
                await T.frames(); const r = {dot: !!map.marker, readout: Q.text('.r-card .fal-profile-readout')};
                const row = view.selected.row; view.step(1); await T.frames(); await T.frames();
                r.gone = !map.marker; r.stepped = view.selected.row !== row; return r; }""")
            assert touch["dot"] and " from A1" in touch["readout"], f"P12, M23: {touch}"
            assert touch["gone"] and touch["stepped"], f"M23: {touch}"
            # a thin line of the selected spot, pressed: that line selected
            thin = _thin_point(page)
            assert thin, "M8b: no point on a thin line of the selected spot takes it alone"
            spot = page.evaluate("() => Q.v().selected.spot")
            page.mouse.click(thin["x"], thin["y"])
            page.wait_for_function(f"() => Q.v().selected && Q.v().selected.row === {thin['row']}", timeout=WAIT)
            assert page.evaluate("() => [Q.v().selected.spot, Q.v().selected.row]") == [spot, thin["row"]], f"M8b: {thin}"
            # the facts of the selected line against today's page's for the same line
            link = page.evaluate("() => Q.m().lineLink(Q.v().selected.line)")
            page.wait_for_selector(".vl-facts", timeout=WAIT)
            view_facts = page.evaluate("() => Q.facts()")
            stands = page.evaluate("() => Q.v().selected.line.stands_for")
            stands_text = page.evaluate("() => Q.text('.vl-stands')")
            _clean(page, "W4")
            page.context.close()
            today = _open(browser, f"{parity_site['url']}#run={BIG}&line={urllib.parse.quote(link, safe='')}", WIDE, flag=False, script=PARITY)
            today.wait_for_selector(".c-col-details .r-kv", timeout=WAIT)
            kv = today.evaluate("""() => Object.fromEntries([...document.querySelectorAll('.r-kv dt')].map((dt) =>
                [dt.textContent, dt.nextElementSibling.textContent.replace(/[\\u00a0\\u202f]/g, ' ')]))""")
            assert today.errors == [], f"Q2 (today's page): {today.errors}"
            today.context.close()
            lat, lon, elev = view_facts[WORDS["ui.view.fact.lat"]], view_facts[WORDS["ui.view.fact.lon"]], view_facts[WORDS["ui.view.fact.elev"]]
            pct = view_facts[WORDS["ui.view.fact.pct"]]
            for k, name in ((0, "Anchor 1"), (1, "Anchor 2")):
                known = "(percentile not known)" if pct[k] == WORDS["ui.view.fact.pct_none"] else f"({pct[k]} percentile)"
                assert kv[name].startswith(f"{lat[k]}, {lon[k]} · {elev[k]}") and known in kv[name], f"D15: {kv[name]} / {lat, lon, elev, pct}"
            for label in (WORDS["ui.details.dh"], WORDS["ui.details.above"]):
                assert view_facts.get(label) == ([kv[label]] if label in kv else None), f"D15 ({label}): {view_facts.get(label)} / {kv.get(label)}"
            assert view_facts.get(WORDS["ui.view.fact.over"]) == ([kv["Over trees/buildings"]] if "Over trees/buildings" in kv else None), \
                f"D15 (over trees): {view_facts}, {kv}"
            assert (WORDS["ui.details.rigging"] in kv) == (WORDS["ui.details.rigging"] in view_facts), f"D15 (rigging): {kv}, {view_facts}"
            # "Stands for": the same count in the view's words (W5 a) and today's
            joined = lambda text: re.sub(r"(?<=\d)[\s  ](?=\d)", "", text)  # noqa: E731 (a count's thousands)
            if stands == 1:
                assert stands_text == WORDS["ui.view.stands_for_n_one"] and kv[WORDS["ui.details.stands_for"]] == WORDS["ui.details.stands_for_n_one"], \
                    f"D15 (stands for): {stands_text}, {kv}"
            else:
                assert stands_text == WORDS["ui.view.stands_for_n_other"].replace("{{n}}", _count(stands)), f"D15 (stands for): {stands_text}"
                assert joined(kv[WORDS["ui.details.stands_for"]]).startswith(f"{stands} "), f"D15 (stands for): {kv}"
            # a tight line's card: its clearance rounded down as the rows write it
            page = _view(browser, parity_site, WIDE)
            tight = page.evaluate("""() => { const v = Q.v(); const s = Array.from(v.order).find((x) => v.values.clr[v.shownOf(x)] < 1);
                return s === undefined ? null : {spot: s, clr: v.values.clr[v.shownOf(s)]}; }""")
            assert tight, "P10: the clip has no spot whose shown line is tight"
            _state(page, f"view.select({tight['spot']});")
            page.wait_for_selector(".r-card .fal-profile-title", timeout=WAIT)
            shown = f"{math.floor(tight['clr'] * 10 + 1e-9) / 10:.1f}"
            title = page.evaluate("() => Q.text('.r-card .fal-profile-title')")
            assert f"min. clearance {shown} m" in title, f"P10: {title} (clr {tight['clr']})"
            # the star's "New folder": the folder made, the line saved into it, the star named "Favourite"
            page.wait_for_function("() => Q.m().favouritesOn", timeout=WAIT)
            page.click(".vl-dhead .r-fav")
            page.wait_for_selector(".r-pop .r-folder", timeout=WAIT)
            picker = page.evaluate("() => [...document.querySelectorAll('.r-pop .r-folder')].map((b) => b.textContent.trim())")
            page.evaluate("() => [...document.querySelectorAll('.r-pop button')].find((b) => b.textContent.trim().startsWith('New folder')).click()")
            page.wait_for_selector(".r-newfolder input", timeout=WAIT)
            page.fill(".r-newfolder input", "Trip")
            page.click(".r-newfolder button[type=submit]")
            page.wait_for_function("() => fetch('/api/favourites').then((r) => r.json()).then((b) => b.favourites.length === 1)", timeout=WAIT)
            saved = page.evaluate("""() => fetch('/api/favourites').then((r) => r.json()).then((b) => [b.folders.map((f) => f.name),
                b.favourites[0].folder_id === b.folders[0].id, b.favourites[0].line === Q.m().lineLink(Q.v().selected.line)])""")
            page.wait_for_function("() => document.querySelector('.vl-dhead .r-fav').getAttribute('aria-label') === 'Favourite'", timeout=WAIT)
            assert picker == ["Favourites (top level)"] and saved == [["Trip"], True, True], f"F2: {picker}, {saved}"
            _clean(page, "W4, the tight line and the folder")
            page.context.close()
            # Measure refused by the server: its line under the button
            refuse = """window.fetch = ((real) => (url, init) => String(url).startsWith('/api/profile')
              ? Promise.resolve(new Response(JSON.stringify({detail: 'no profile here'}), {status: 400, headers: {'content-type': 'application/json'}}))
              : real(url, init))(window.fetch);"""
            page = _view(browser, parity_site, WIDE, script=refuse)
            _state(page, "view.setLevel('spots');")
            page.click(".c-result-top .r-actions button:has-text('Measure')")
            page.wait_for_function("() => window.FINDALINE_VIEW.map.isMeasuring", timeout=WAIT)
            first = page.evaluate("() => T.empty(false)")
            assert first, "E4: no empty point on the map"
            page.mouse.click(first["x"], first["y"])
            second = page.evaluate("([x, y]) => { const b = T.box(); return {x: x > b.left + b.width / 2 ? x - 120 : x + 120, y}; }", [first["x"], first["y"]])
            page.mouse.click(second["x"], second["y"])
            page.wait_for_selector(".r-act .r-error", timeout=WAIT)
            error = page.evaluate("() => [Q.text('.r-act .r-error'), document.querySelector('.r-act .r-error').getAttribute('role')]")
            assert error == ["Not computed: no profile here", "alert"], f"E4: {error}"
            _clean(page, "W4, Measure")
        finally:
            browser.close()


def test_list_and_filters(parity_site):
    """The list's filters as today's tests use them: the Clearance chip's editor takes a typed value, the lines that
    pass fall, the chip says it, its × removes it (L16); the editor's × on neither row's number or unit, the two rows in
    one column, on a desktop and on a touch phone (its × 40 px) (L18); a class of "Why so many?" cleared hides its lines,
    the headline counts them hidden by filters, "Clear all" shows them again (L3); a run without `found` shows no found
    line and no box (L4)."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _view(browser, parity_site, WIDE)
            before = page.evaluate("() => Q.v().counts.lines")
            page.locator(".vl-filters .u-chip", has_text=WORDS["ui.view.chip.clearance"]).first.click()
            page.wait_for_selector(".r-editor input[type=number]", timeout=WAIT)
            page.evaluate("""() => { const input = document.querySelector('.r-editor input[type=number]'); input.value = '5';
                input.dispatchEvent(new Event('change', {bubbles: true})); }""")
            page.wait_for_function(f"() => Q.v().counts.lines < {before}", timeout=WAIT)
            chips = page.evaluate("() => [...document.querySelectorAll('.vl-filters .u-chip.u-on')].map((c) => c.textContent.trim())")
            assert any(c.startswith(WORDS["ui.view.chip.clearance_min"].replace("{{a}}", "5.0")) for c in chips), f"L16: {chips}"
            page.click(f".vl-filters .u-chip-x[aria-label=\"{WORDS['ui.view.chip.clearance_remove']}\"]")
            page.wait_for_function(f"() => Q.v().counts.lines === {before}", timeout=WAIT)
            # the Length editor: its × clear of the rows' numbers and units, the two rows in one column
            page.locator(".vl-filters .u-chip", has_text=WORDS["ui.view.chip.length"]).first.click()
            page.wait_for_selector(".r-editor .r-editor-x", timeout=WAIT)
            editors = {"desktop": page.evaluate(EDITOR_JS)}
            page.click(".r-editor .r-editor-x")
            page.wait_for_selector(".r-editor", state="detached", timeout=WAIT)
            # "Why so many?": the class most lines need, cleared; the headline counts them hidden by filters; Clear all
            page.click(".r-why-link")
            page.wait_for_selector("#r-why .r-why-row input", timeout=WAIT)
            needs = page.evaluate("() => Q.m().needCounts()")
            assert needs, "L3: the clip has no rigging classes"
            k = needs.index(max(needs))
            page.evaluate(f"() => document.querySelectorAll('#r-why .r-why-row input')[{k}].click()")
            page.wait_for_function(f"() => Q.v().counts.lines < {before} && !!document.querySelector('.vl-clear')", timeout=WAIT)
            hidden = page.evaluate("() => [Q.v().counts.hidden, Q.text('.vl-count'), [...document.querySelectorAll('#r-why .r-why-row input')].map((i) => i.checked)]")
            assert hidden[1].endswith(WORDS["ui.result.hidden"].replace("{{n}}", _count(hidden[0]))), f"L3: {hidden}"
            assert hidden[2][k] is False, f"L3: {hidden}"
            page.click(".vl-clear")
            page.wait_for_function(f"() => Q.v().counts.lines === {before}", timeout=WAIT)
            assert page.evaluate("() => [...document.querySelectorAll('#r-why .r-why-row input')].every((i) => i.checked)"), "L3: Clear all"
            _clean(page, "W5")
            page.context.close()
            # a run without `found`: no found line, no box
            page = _view(browser, parity_site, WIDE, run=NOFOUND)
            none = page.evaluate("() => [Q.m().data.found ?? null, !!document.querySelector('.r-found-line'), !!document.querySelector('.r-why-link')]")
            assert none == [None, False, False], f"L4: {none}"
            _clean(page, "W5, the run without found")
            page.context.close()
            # a touch phone: the editor's × 40 px, clear of the rows
            page = _view(browser, parity_site, PHONE)
            page.focus(".u-sheet-handle")
            page.keyboard.press("ArrowUp")
            page.keyboard.press("ArrowUp")
            page.wait_for_function("() => document.querySelector('.u-sheet').classList.contains('u-full')", timeout=WAIT)
            page.wait_for_function("() => { const s = document.querySelector('.u-sheet'); return Math.abs(s.getBoundingClientRect().height - parseFloat(s.style.height)) < 1; }",
                                   timeout=WAIT)
            page.locator(".vl-filters .u-chip", has_text=WORDS["ui.view.chip.length"]).first.click()
            page.wait_for_selector(".r-editor .r-editor-x", timeout=WAIT)
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
            _state(page, "view.select(Array.from(view.order).find((s) => view.passingCount(s) >= 2));")
            page.wait_for_selector(".u-sheet .r-view3d", state="attached", timeout=WAIT)
            view3d = page.evaluate("""() => { const a = document.querySelector('.u-sheet .r-view3d'), {view} = window.FINDALINE_VIEW, m = view.model;
                return [a.getAttribute('href'), '/view3d#run=' + encodeURIComponent(m.runId) + '&line=' + encodeURIComponent(m.lineLink(view.selected.line))]; }""")
            assert view3d[0].startswith(view3d[1] + "&also="), f"D13: {view3d}"
            page.focus(".u-sheet-handle")
            page.keyboard.press("ArrowUp")
            page.keyboard.press("ArrowUp")
            page.wait_for_function("() => document.querySelector('.u-sheet').classList.contains('u-full')", timeout=WAIT)
            page.wait_for_function("() => { const s = document.querySelector('.u-sheet'); return Math.abs(s.getBoundingClientRect().height - parseFloat(s.style.height)) < 1; }",
                                   timeout=WAIT)
            sheet = """() => { const box = (e) => { const r = e.getBoundingClientRect(); return [r.left, r.top, r.right, r.bottom].map(Math.round); };
                const h = document.querySelector('.u-sheet .u-sheet-head'), b = document.querySelector('.u-sheet .u-sheet-body');
                return {shadow: getComputedStyle(h).boxShadow, head: box(h), body: box(b), top: b.scrollTop,
                        bar: document.querySelector('.c-phone-top').getBoundingClientRect().bottom, sheet: document.querySelector('.u-sheet').getBoundingClientRect().top}; }"""
            top = page.evaluate(sheet)
            assert top["sheet"] >= top["bar"], f"Ph3: {top}"
            page.evaluate("() => { document.querySelector('.u-sheet .u-sheet-body').scrollTop = 120; }")
            page.wait_for_function("() => getComputedStyle(document.querySelector('.u-sheet .u-sheet-head')).boxShadow !== 'none'", timeout=WAIT)
            scrolled = page.evaluate(sheet)
            page.evaluate("() => { document.querySelector('.u-sheet .u-sheet-body').scrollTop = 0; }")
            page.wait_for_function("() => getComputedStyle(document.querySelector('.u-sheet .u-sheet-head')).boxShadow === 'none'", timeout=WAIT)
            back = page.evaluate(sheet)
            assert top["shadow"] == "none" and scrolled["shadow"] != "none" and scrolled["top"] > 0, f"Ph4: {top}, {scrolled}"
            assert top["head"] == scrolled["head"] == back["head"] and top["body"] == scrolled["body"] == back["body"], f"Ph4: {top}, {scrolled}, {back}"
            assert not page.evaluate("() => document.documentElement.scrollWidth > innerWidth"), "Q3: wider than the window with a spot selected"
            _clean(page, "W6")
            back = page.evaluate("() => [...document.querySelectorAll('.c-phone-top .c-back')].map((b) => b.getAttribute('aria-label'))")
            assert back == ["Home"], f"H2: {back}"
            page.click(".c-phone-top .c-back")
            page.wait_for_function("() => location.hash === '#home' && !!document.querySelector('.u-bnav')", timeout=WAIT)
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
                page.wait_for_function("() => !!Q.text('.c-result-wait .c-error')", timeout=WAIT)
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
