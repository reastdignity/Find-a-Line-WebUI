"""The result view's frame of step 3c (viewer/src/result/view/SpotColumns.tsx, MapBar.tsx, RunActions.tsx,
ProfileCard.tsx; docs/line-volume/spec-view.md part B, the user's gate-1 answers of 2026-11-20): the run's actions in
the desktop header and in a phone's pill, the header without its line count (W8), measuring (the tip beside "Cancel"
on a desktop, the status line's first line on a phone, the sheet low while measuring, the measured profile in the
card or first in the sheet at half), the profile's card over the desktop map with the short foot while it is open
(4 a), the map's one "i" (7 b: a desktop's both texts, a phone's three parts), the legend's rows of what is drawn
besides the spots and the access rows only while an anchor of the selected line is in view (L b, W6, W13), the
status texts (W1, W14), the boxes' help (S c) and A1's two gaps (the sheet's check of a frame left, a link's note
after the window crossed the phone's width). Playwright's Edge over the app's server, offline, on the result view's
clip run (clip_runs.view_clip) and the same search without the access mark. Every wait is an event with a deadline
(one exception, said where it is). Run from PowerShell (.claude/rules/browser-tests.md).

The frame uses the canvas's members of step 3c as they are (SpotMap.ts: Measure's, zoomToLine, setCovered,
drawMeasured, the legend's `fav`, `area`, `ends` and `runs`); a new selection ends a measured line (viewlink.ts)."""

import json
import os
import sys
import urllib.parse

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_shell_c import BIG, copy_clip, stub_page  # noqa: E402
from test_shell_c_view_map import (BOXES, COARSE, DESKTOP, HELPERS, PHONE, SMALL_PHONE, WAIT, WORDS, _apart, _open,  # noqa: E402,F401
                                   _state, _tap, _tap_on, boxes_site, view_clip)
from test_web import EDGE, _playwright, _server  # noqa: E402

pytestmark = pytest.mark.skipif(not os.path.exists(EDGE) or not _playwright(),
                                reason="needs Microsoft Edge and Playwright (group ui)")
PLAIN = "2026-10-28_110000_Plain_00000000000000f3"  # the view clip's search without --access
PIXEL = {"viewport": {"width": 412, "height": 839}, "device_scale_factor": 2.625, "is_mobile": True, "has_touch": True}

# A line outside the run (as the 3D view's moved anchors give it) and the server's profile of two points, stubbed: an
# 80 m line (the profile of any two measured points has the same five samples)
OUTSIDE = "49.5,19.1,49.5004,19.1005"
PROFILE_STUB = """
window.PROFILES = 0;
const realFetchOfFrame = window.fetch;
window.fetch = (url, init) => {
  if (!String(url).startsWith("/api/profile")) return realFetchOfFrame(url, init);
  PROFILES++;
  return Promise.resolve(new Response(JSON.stringify({d: [0, 20, 40, 60, 80], z: [300, 296, 292, 296, 301], min: [40, 7.5],
    water_m: 0, filled_m: 0}), {headers: {"content-type": "application/json"}}));
};
"""
# The same, held until the page's FAIL() answers it with a refusal (a measurement that fails later)
PROFILE_HELD = """
window.FAIL = null;
const realFetchOfHeld = window.fetch;
window.fetch = (url, init) => String(url).startsWith("/api/profile")
  ? new Promise((ok) => { window.FAIL = () => ok(new Response(JSON.stringify({detail: "no profile here"}),
                                                               {status: 400, headers: {"content-type": "application/json"}})); })
  : realFetchOfHeld(url, init);
"""

# The same, each answer held until the page's RELEASE(k) gives request k the stub's profile (a late answer)
PROFILE_LATE = """
window.HELD = []; window.ANSWERED = 0;
const realFetchOfLate = window.fetch;
window.fetch = (url, init) => String(url).startsWith("/api/profile")
  ? new Promise((ok) => { HELD.push(() => { ok(new Response(JSON.stringify({d: [0, 20, 40, 60, 80], z: [300, 296, 292, 296, 301],
      min: [40, 7.5], water_m: 0, filled_m: 0}), {headers: {"content-type": "application/json"}})); ANSWERED++; }); })
  : realFetchOfLate(url, init);
window.RELEASE = (k) => HELD[k]();
"""

# The frame's helpers (window.F), beside test_shell_c_view_map's T
FRAME = r"""
window.F = {
  v() { return window.FINDALINE_VIEW; },
  rect(sel) { const e = document.querySelector(sel), r = e && e.getBoundingClientRect(); return r && r.width && r.height ? [r.left, r.top, r.right, r.bottom] : null; },
  // the run's actions as drawn: each button's words or name, in their order
  actions(sel) { return [...document.querySelectorAll(sel + " .r-actions button")].map((b) => (b.textContent.trim() || b.getAttribute("aria-label"))); },
  // a phone's sheet: its stop and whether it rests
  snap() { const s = document.querySelector(".u-sheet"); return s ? ["peek", "half", "full"].find((k) => s.classList.contains("u-" + k)) : null; },
  rest() { const s = document.querySelector(".u-sheet"); return !!s && Math.abs(s.getBoundingClientRect().height - parseFloat(s.style.height)) < 1; },
  // a line's ends (lat1, lon1, lat2, lon2) in the viewport
  ends(l) { const m = window.FINDALINE_MAP, b = m.getContainer().getBoundingClientRect();
    return [[l.lat1, l.lon1], [l.lat2, l.lon2]].map(([a, o]) => { const q = m.latLngToContainerPoint([a, o]); return [q.x + b.left, q.y + b.top]; }); },
  // the part of the map free of the bar and of what covers the map's bottom (the foot, a card, a sheet), viewport px
  room() { const b = window.FINDALINE_MAP.getContainer().getBoundingClientRect(), top = this.rect(".v-map .v-switch"), foot = this.rect(".v-map .v-foot");
    const sheet = this.rect(".u-sheet"), card = this.rect(".c-col-map > .r-card");
    return [b.left, top ? top[3] : b.top, b.right, Math.min(b.bottom, foot ? foot[1] : b.bottom, sheet ? sheet[1] : b.bottom, card ? card[1] : b.bottom)]; },
  inRoom(l) { const r = this.room(); return this.ends(l).every(([x, y]) => x >= r[0] && x <= r[2] && y >= r[1] && y <= r[3]); },
  // the legend's items: each one's kind and words
  legend() { return [...document.querySelectorAll(".v-legend [data-kind]")].map((e) => [e.dataset.kind, e.textContent.trim()]); },
  // the canvas's legend given more than it draws (the members of step 3c: B1's), as the canvas would tell it
  legendWith(extra) { const {map} = this.v(), own = map.legend.bind(map);
    map.legend = () => { const l = own(); return {...l, shapes: {...l.shapes, ...extra.shapes}, runs: extra.runs ?? l.runs ?? []}; };
    map.listeners.forEach((f) => f()); },
  // an empty point of the map in its free room, `r` px clear of every control, and `apart` px or more from `from` (a
  // point taken before: two presses of a measurement at two places)
  empty(r, from = null, apart = 80) { const room = this.room(), box = window.FINDALINE_MAP.getContainer().getBoundingClientRect(), {map} = this.v();
    const boxes = T.controls();
    for (let y = room[3] - 40; y > room[1] + 40; y -= 17) for (let x = room[0] + 40; x < room[2] - 40; x += 23) {
      if (from && Math.hypot(x - from.x, y - from.y) < apart) continue;
      if (boxes.some((c) => x > c.left - r && x < c.right + r && y > c.top - r && y < c.bottom + r)) continue;
      if (map.pickAt(x - box.left, y - box.top, false).length === 0) return {x, y}; }
    return null; },
  // a spot in view whose shown line has both anchors in the map's top `share` of its height (well above where the
  // card comes), else null; `low`: one whose lower anchor lies in the bottom 100 px instead
  spotAt(share, low = false) { const {view} = this.v(), box = window.FINDALINE_MAP.getContainer().getBoundingClientRect();
    for (const spot of Array.from(view.inView.spots)) { const e = T.ends(view.shownOf(spot));
      const ys = [e[1], e[3]], xs = [e[0], e[2]];
      if (xs.some((x) => x < 40 || x > box.width - 40) || ys.some((y) => y < 60)) continue;
      if (low ? Math.max(...ys) > box.height - 100 && Math.max(...ys) < box.height - 10 : Math.max(...ys) < box.height * share) return spot; }
    return null; },
};
"""


@pytest.fixture(scope="module")
def plain_clip(tmp_path_factory):
    """The view clip's search without the access mark (clip_runs.VIEW_CLIP_ARGS without --access), once per module."""
    import clip_runs
    folder = clip_runs.data_copy(tmp_path_factory, "frame-plain", [a for a in clip_runs.VIEW_CLIP_ARGS if a != "--access"])
    runs = folder / "runs"
    return next(runs / d for d in os.listdir(runs) if (runs / d / "run.json").is_file())


@pytest.fixture
def site(tmp_path, view_clip, plain_clip):
    """A data folder with the marked run (BIG) and the run without the mark (PLAIN), served by the app; yields the
    address of the app's page."""
    folder = tmp_path / "data"
    copy_clip(view_clip, folder, BIG, "Clip")
    copy_clip(plain_clip, folder, PLAIN, "Clip without the mark")
    page_path = stub_page(folder, "frametest")
    with _server(folder) as port:
        yield f"http://127.0.0.1:{port}/{page_path}?ui=c"


def _view(browser, site: str, context: dict, run: str = BIG, line: str | None = None, script: str = ""):
    """The view of a run (at a line's link) with the helpers."""
    url = f"{site}#run={run}" + (f"&line={urllib.parse.quote(line, safe='')}" if line else "")
    return _open(browser, url, context, script=FRAME + script)


def _has_measure(page) -> bool:
    """The canvas can measure (Measure's members of step 3c, B1's)."""
    return page.evaluate("() => typeof window.FINDALINE_VIEW.map.startMeasure === 'function'")


def test_header_actions_and_title(site):
    """The desktop header: the run's name and date without the line count (W8), then the run's actions after the
    caller's, in today's order (Measure where the canvas can measure, Compare, Download; Share only for the owner on the
    public site, not on the local app); a phone's pill: the name, then the actions as icons without boxes of their own,
    no Compare (as today)."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _view(browser, site, DESKTOP)
            _state(page)
            measure = _has_measure(page)
            assert measure  # the canvas of step 3c measures
            head =page.evaluate("""() => ({meta: document.querySelector('.c-run-title .u-small').textContent,
                order: [...document.querySelector('.c-result-top').children].map((e) => e.className.split(' ')[0])})""")
            assert "line" not in head["meta"] and head["meta"].strip(), head
            assert head["order"][-1] == "r-actions", head
            assert F_actions(page, ".c-result-top") == (["Measure"] if measure else []) + ["Compare", "Download"]
            page.context.close()
            page = _view(browser, site, PHONE)
            _state(page)
            pill = page.evaluate("""() => [...document.querySelectorAll('.c-pill .r-actions button')].map((b) =>
                [b.getAttribute('aria-label'), b.classList.contains('u-plain'), Math.round(b.getBoundingClientRect().height)])""")
            assert [name for name, _, _ in pill] == (["Measure"] if measure else []) + ["Download"], pill
            assert all(plain and height >= 44 for _, plain, height in pill), pill
            assert page.evaluate("() => !!document.querySelector('.c-phone-top > .r-actions')") is False  # in the pill, not beside it
            assert page.errors == []
        finally:
            browser.close()


def F_actions(page, sel: str) -> list:
    return page.evaluate("([sel]) => F.actions(sel)", [sel])


@pytest.mark.parametrize("device", [DESKTOP, PHONE], ids=["desktop", "phone"])
def test_map_page_actions(site, device):
    """A run's own map.html in the view: today's rules of who sees what (RunActions: mayExport, the spec store's U9):
    no Download (the page has no token to ask the worker for the files) and no Share (the local app has no owner's
    link); the header's or the pill's other actions as on the app's page."""
    from playwright.sync_api import sync_playwright
    root = site.split("/runs/")[0]
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _open(browser, f"{root}/runs/{urllib.parse.quote(BIG)}/map.html", device, script=FRAME)
            _state(page)
            # (Measure: the app serves the map page, whose profiles it computes)
            if device is DESKTOP:
                assert F_actions(page, ".c-result-top") == ["Measure", "Compare"]
            else:
                got = page.evaluate("() => [...document.querySelectorAll('.c-pill .r-actions button')].map((b) => b.getAttribute('aria-label'))")
                assert got == ["Measure"], got
            assert page.errors == []
        finally:
            browser.close()


def test_profile_card_and_short_foot(site):
    """A desktop with a line selected: its profile in a card over the map's bottom (the chart, "Rigging and layers",
    fold, close), the card standing on the run's credits' line (8 px above them), the scale above the card, the bar's
    foot above the scale, and the foot the short one (4 a): the legend behind "Legend" (folded until it is asked
    for), the run's data credits folded. "Legend" shows the legend above the card, nothing covering another. The fold
    makes the card its bar; the close takes it away (model.profileClosed: the full foot again), showProfile brings it
    back, and a new selection opens it again."""
    from playwright.sync_api import sync_playwright
    layout = """() => ({card: F.rect('.c-col-map > .r-card'), credits: F.rect('.v-map .leaflet-control-attribution'), scale: F.rect('.v-map .leaflet-control-scale'),
        foot: F.rect('.v-map .v-foot'), legend: !!document.querySelector('.v-legend'), fold: document.querySelector('.v-fold')?.getAttribute('aria-expanded') ?? null,
        on: document.querySelector('.c-col-map').classList.contains('c-card-on'), chart: !!document.querySelector('.r-card .fal-profile-chart'),
        closed: window.FINDALINE_VIEW.view.model.profileClosed})"""
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _view(browser, site, DESKTOP)
            before = page.evaluate(layout)
            assert before["card"] is None and before["legend"] and before["fold"] is None and not before["on"], before
            _state(page, "view.setLevel('auto'); view.select(view.inView.best[0] ?? view.order[0]);")
            page.wait_for_selector(".r-card .fal-profile-chart", timeout=WAIT)
            page.evaluate("() => T.frames()")
            s = page.evaluate(layout)
            assert s["on"] and s["chart"] and not s["legend"] and s["fold"] == "false", s
            card, credits, scale, foot = s["card"], s["credits"], s["scale"], s["foot"]
            assert abs(credits[1] - card[3] - 8) <= 1.5, (card, credits)  # on the credits' line
            assert scale[3] <= card[1] and foot[3] <= scale[1] + 0.5, (card, scale, foot)  # the scale above it, the foot above that
            # the bar's controls and the card's: "Rigging and layers", fold, close
            assert page.evaluate("() => [...document.querySelectorAll('.r-card .r-dock-bar button')].map((b) => b.getAttribute('aria-label') || b.textContent.trim())") == \
                ["Rigging and layers", "Fold the profile", "Close the profile"]
            # "Legend": the legend above the card, no control of the map on another
            page.click(".v-fold")
            page.wait_for_selector(".v-legend", timeout=WAIT)
            page.evaluate("() => T.frames()")
            opened = page.evaluate(layout)
            boxes = page.evaluate("() => T.boxes()")
            assert opened["foot"][3] <= opened["card"][1], opened
            names = sorted(boxes)
            crossing = [(a, b) for k, a in enumerate(names) for b in names[k + 1:]
                        if min(boxes[a][2], boxes[b][2]) - max(boxes[a][0], boxes[b][0]) > 0.5 and min(boxes[a][3], boxes[b][3]) - max(boxes[a][1], boxes[b][1]) > 0.5]
            assert crossing == [], (crossing, boxes)
            # folded: its bar only; unfolded again
            page.click(".r-card .r-fold")
            page.wait_for_function("() => document.querySelector('.r-card').classList.contains('r-card-folded')", timeout=WAIT)
            assert page.evaluate("() => document.querySelector('.r-card').getBoundingClientRect().height") < 100
            page.click(".r-card .r-fold")
            page.wait_for_function("() => !document.querySelector('.r-card').classList.contains('r-card-folded')", timeout=WAIT)
            # closed: the card gone, the full foot, the model's state; shown again; a new selection opens it again
            page.click(".r-card .r-dock-bar [aria-label='Close the profile']")
            page.wait_for_selector(".r-card", state="detached", timeout=WAIT)
            page.evaluate("() => T.frames()")
            closed = page.evaluate(layout)
            assert closed["closed"] and closed["legend"] and closed["fold"] is None and not closed["on"], closed
            page.evaluate("() => window.FINDALINE_VIEW.view.model.showProfile()")
            page.wait_for_selector(".r-card .fal-profile-chart", timeout=WAIT)
            page.click(".r-card .r-dock-bar [aria-label='Close the profile']")
            page.wait_for_selector(".r-card", state="detached", timeout=WAIT)
            _state(page, "view.select(view.order[1]);")
            page.wait_for_selector(".r-card .fal-profile-chart", timeout=WAIT)
            assert page.evaluate(layout)["closed"] is False
            assert page.errors == []
        finally:
            browser.close()


def test_card_moves_the_map_only_for_a_line_under_it(site):
    """A desktop's selection opens the card: a line with both anchors well above it leaves the map as it is (its zoom
    and centre); a line with an anchor where the card comes is brought out from under it (today's page's keepFree: a
    fit), both anchors then above the card's top."""
    from playwright.sync_api import sync_playwright
    where = "() => { const m = window.FINDALINE_MAP, c = m.getCenter(); return [m.getZoom(), +c.lat.toFixed(7), +c.lng.toFixed(7)]; }"
    above = """() => { const {view} = window.FINDALINE_VIEW, e = T.ends(view.selected.row), card = F.rect('.c-col-map > .r-card'), b = T.box();
      return Math.max(e[1], e[3]) + b.top <= card[1]; }"""
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _view(browser, site, DESKTOP)
            _state(page, "view.setLevel('spots');")
            spot = page.evaluate("() => F.spotAt(0.4)")
            assert spot is not None, "no line with both anchors in the map's top 40 %"
            before = page.evaluate(where)
            _state(page, f"view.select({spot});")
            page.wait_for_selector(".r-card .fal-profile-chart", timeout=WAIT)
            page.wait_for_function("() => !window.FINDALINE_MAP._animatingZoom", timeout=WAIT)
            page.evaluate("() => T.frames()")
            assert page.evaluate(where) == before and page.evaluate(above)
            _state(page, "view.select(null);")
            page.wait_for_selector(".r-card", state="detached", timeout=WAIT)
            # the map moved so that the line's lower anchor lies 50 px above the map's bottom, where the card comes
            _state(page, f"const e = T.ends(view.shownOf({spot})), b = T.box(); leaflet.panBy([0, Math.round(Math.max(e[1], e[3]) - (b.height - 50))], {{animate: false}});")
            assert page.evaluate(f"() => F.spotAt(0, true) !== null && Math.max(T.ends(window.FINDALINE_VIEW.view.shownOf({spot}))[1], T.ends(window.FINDALINE_VIEW.view.shownOf({spot}))[3]) > T.box().height - 100")
            _state(page, f"view.select({spot});")
            page.wait_for_selector(".r-card .fal-profile-chart", timeout=WAIT)
            page.wait_for_function(f"() => !window.FINDALINE_MAP._animatingZoom && ({above})()", timeout=WAIT)
            assert page.errors == []
        finally:
            browser.close()


def test_card_is_not_in_view(site):
    """The card's height goes to the canvas (setCovered: B1's covered term), so what lies under it is not "in view":
    the canvas's covered px are the map's bottom up to the card's top, 0 once the card is closed."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _view(browser, site, DESKTOP)
            _state(page, "view.setLevel('spots'); view.select(view.order[0]);")
            page.wait_for_selector(".r-card .fal-profile-chart", timeout=WAIT)
            page.evaluate("() => T.frames()")
            got = page.evaluate("""() => { const m = window.FINDALINE_MAP.getContainer().getBoundingClientRect(), c = F.rect('.c-col-map > .r-card');
                return [window.FINDALINE_VIEW.map.covered, Math.round(m.bottom - c[1])]; }""")
            assert got[0] == got[1] > 100, got
            page.click(".r-card .r-dock-bar [aria-label='Close the profile']")
            page.wait_for_selector(".r-card", state="detached", timeout=WAIT)
            page.wait_for_function("() => window.FINDALINE_VIEW.map.covered === 0", timeout=WAIT)
            assert page.errors == []
        finally:
            browser.close()


def test_measuring_desktop(site):
    """A desktop: Measure becomes "Cancel" with the tip beside it, before it (W12's words); two clicks on the map are
    the points; the measured profile in the card (the server's profile asked once), the frame's measured line; its
    close clears it (and model.measuredLink)."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _view(browser, site, DESKTOP, script=PROFILE_STUB)
            _state(page, "view.setLevel('spots');")
            page.click(".c-result-top .r-actions button:has-text('Measure')")
            page.wait_for_selector(".r-act .r-tip-beside", timeout=WAIT)
            tip = page.evaluate("""() => { const t = document.querySelector('.r-act .r-tip-beside'), b = t.parentElement.querySelector('button');
                return [t.textContent, b.textContent.trim(), b.getAttribute('aria-pressed'), t.getBoundingClientRect().right <= b.getBoundingClientRect().left]; }""")
            assert tip == [WORDS["ui.result.measure_tip"], "Cancel", "true", True], tip
            first = page.evaluate("() => F.empty(30)")
            second = page.evaluate("([p]) => F.empty(30, p)", [first])
            assert first and second, "no two empty points on the map"
            for at in (first, second):  # two places 80 px or more apart (no double click)
                page.mouse.click(at["x"], at["y"])
                page.evaluate("() => T.frames()")
            page.wait_for_function("() => !!window.FINDALINE_VIEW.measured", timeout=WAIT)
            page.wait_for_selector(".r-card .fal-profile-chart", timeout=WAIT)
            got = page.evaluate("() => [document.querySelector('.r-card .r-dock-bar b').textContent, window.PROFILES, !!document.querySelector('.r-act .r-tip')]")
            assert got == ["Measured profile", 1, False], got
            page.click(".r-card .r-dock-bar [aria-label='Close the profile']")
            page.wait_for_selector(".r-card", state="detached", timeout=WAIT)
            # (FINDALINE_VIEW.measured is written by an effect after the paint that took the card away)
            page.wait_for_function("() => window.FINDALINE_VIEW.measured === null", timeout=WAIT)
            assert page.evaluate("() => [window.FINDALINE_VIEW.measured, window.FINDALINE_VIEW.view.model.measuredLink, "
                                 "window.FINDALINE_VIEW.map.drawn().measured.length]") == [None, None, 0]
            assert page.errors == []
        finally:
            browser.close()


def test_measuring_phone(site):
    """A phone with the sheet at half: Measure (the pill's ruler) lowers the sheet, its tip is the status line's first
    line in a tap's words (W12) and the pill draws none; two taps are the points; the measured profile first in the
    sheet's body, the sheet at half, the measured line in the map's room above it."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _view(browser, site, PHONE, script=PROFILE_STUB)
            _state(page, "view.setLevel('spots');")
            page.focus(".u-sheet-handle")
            page.keyboard.press("ArrowUp")
            page.wait_for_function("() => F.snap() === 'half' && F.rest()", timeout=WAIT)
            _tap_on(page, ".c-pill [aria-label='Measure']")
            page.wait_for_function("() => F.snap() === 'peek' && F.rest()", timeout=WAIT)
            tip = page.evaluate("() => [document.querySelector('.v-status').firstElementChild.className, document.querySelector('.v-status .v-tip')?.textContent, "
                                "!!document.querySelector('.c-pill .r-tip')]")
            assert tip == ["v-msg v-tip", WORDS["ui.result.measure_tip_touch"], False], tip
            first = page.evaluate("() => F.empty(30)")
            second = page.evaluate("([p]) => F.empty(30, p)", [first])
            assert first and second, "no two empty points on the map"
            for at in (first, second):  # two places 80 px or more apart
                _tap(page, at["x"], at["y"])
            page.wait_for_function("() => !!window.FINDALINE_VIEW.measured && F.snap() === 'half' && F.rest()", timeout=WAIT)
            page.wait_for_function("() => !window.FINDALINE_MAP._animatingZoom", timeout=WAIT)
            page.evaluate("() => T.frames()")
            got = page.evaluate("""() => { const first = document.querySelector('.u-sheet-body').firstElementChild;
                return [first.classList.contains('r-dock'), first.querySelector('.r-dock-bar b')?.textContent, F.inRoom(window.FINDALINE_VIEW.measured),
                        !!document.querySelector('.v-status .v-tip')]; }""")
            assert got == [True, "Measured profile", True, False], got
            assert page.errors == []
        finally:
            browser.close()


@pytest.mark.parametrize("device", [DESKTOP, PHONE], ids=["desktop", "phone"])
def test_link_measured_line_is_fitted(site, device):
    """A link to a line outside the run (measured, stubbed): its profile in the card (desktop) or first in the sheet at
    half (phone), the line drawn and fitted into the map's room."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _view(browser, site, device, line=OUTSIDE, script=PROFILE_STUB)
            page.wait_for_function("() => !!window.FINDALINE_VIEW.measured && !window.FINDALINE_MAP._animatingZoom", timeout=WAIT)
            where = ".r-card" if device is DESKTOP else ".u-sheet-body > .r-dock:first-child"
            page.wait_for_selector(f"{where} .fal-profile-chart", timeout=WAIT)
            if device is PHONE:
                page.wait_for_function("() => F.snap() === 'half' && F.rest()", timeout=WAIT)
            page.evaluate("() => T.frames()")
            assert page.evaluate("() => F.inRoom(window.FINDALINE_VIEW.measured)") is True
            assert page.errors == []
        finally:
            browser.close()


# A measured line as the page shows it: the frame's, model.measuredLink, the canvas's points drawn, the profiles'
# titles (the card's, every dock's) and the number of docks in a phone's sheet
MEASURED_NOW = """() => { const {view, map, measured} = window.FINDALINE_VIEW;
  return {line: !!measured, link: view.model.measuredLink, points: map.drawn().measured.length,
          titles: [...document.querySelectorAll('.r-dock-bar b')].map((b) => b.textContent),
          docks: document.querySelectorAll('.u-sheet-body .r-dock').length}; }"""


@pytest.mark.parametrize("how, device", [("measure", DESKTOP), ("measure", PHONE), ("link", DESKTOP), ("link", PHONE)],
                         ids=["measure-desktop", "measure-phone", "link-desktop", "link-phone"])
def test_new_selection_ends_a_measured_line(site, how, device):
    """A measured line ends with a new selection, Measure's and a link's alike (viewlink.ts: the frame's measured line
    and model.measuredLink; the canvas clears its own: B1's): neither the canvas (drawn().measured) nor the card or a
    phone's dock shows it, and the selected line's profile stands in its place (on a phone the details' dock, one dock
    in the sheet). A deselection keeps a completed measurement (Measure's: a spot selected before it; while measured,
    a phone's sheet holds one dock, the measured one). The planner's seam of 2026-11-20."""
    from playwright.sync_api import sync_playwright
    measured_title = "Measured profile"  # ProfileDock's words (not in the catalogue)
    phone = device is PHONE
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _view(browser, site, device, line=OUTSIDE if how == "link" else None, script=PROFILE_STUB)
            if how == "measure":
                _state(page, "view.setLevel('spots'); view.select(view.order[0]);")
                if phone:
                    _tap_on(page, ".c-pill [aria-label='Measure']")
                    page.wait_for_function("() => F.snap() === 'peek' && F.rest()", timeout=WAIT)
                else:
                    page.click(".c-result-top .r-actions button:has-text('Measure')")
                first = page.evaluate("() => F.empty(30)")
                second = page.evaluate("([p]) => F.empty(30, p)", [first])
                assert first and second, "no two empty points on the map"
                for at in (first, second):  # two places 80 px or more apart
                    if phone:
                        _tap(page, at["x"], at["y"])
                    else:
                        page.mouse.click(at["x"], at["y"])
                        page.evaluate("() => T.frames()")
            page.wait_for_function("() => !!window.FINDALINE_VIEW.measured", timeout=WAIT)
            page.wait_for_selector(".fal-profile-chart", timeout=WAIT)
            page.evaluate("() => T.frames()")
            on = page.evaluate(MEASURED_NOW)
            assert on["line"] and on["points"] == 2 and on["titles"] == [measured_title], on
            assert on["link"] == (OUTSIDE if how == "link" else None) and on["docks"] == (1 if phone else 0), on
            if how == "measure":  # a deselection keeps it
                kept = _state(page, "view.select(null);")
                assert kept["selected"] is None
                page.evaluate("() => T.frames()")
                assert page.evaluate(MEASURED_NOW) == on
            _state(page, "view.setLevel('spots'); view.select(view.order[1]);")
            page.wait_for_function("() => !window.FINDALINE_VIEW.measured", timeout=WAIT)
            page.wait_for_selector(".u-sheet-body .vl-details .r-dock .fal-profile-chart" if phone else ".c-col-map > .r-card .fal-profile-chart",
                                   timeout=WAIT)
            page.evaluate("() => T.frames()")
            off = page.evaluate(MEASURED_NOW)
            assert (off["line"], off["link"], off["points"], off["docks"]) == (False, None, 0, 1 if phone else 0), off
            assert len(off["titles"]) == 1 and off["titles"][0].startswith("Profile · "), off  # the selected line's
            assert page.errors == []
        finally:
            browser.close()


LATE_NOW = """() => { const {view, map, measured} = window.FINDALINE_VIEW;
  return {measuring: map.isMeasuring, points: map.drawn().measured.length, frameMeasured: !!measured,
          selected: view.selected ? view.selected.row : null, titles: [...document.querySelectorAll('.r-dock-bar b')].map((b) => b.textContent)}; }"""


def _measure_two(page, phone=False):
    """Measure pressed and two points taken (80 px or more apart, empty of spots)."""
    if phone:
        _tap_on(page, ".c-pill [aria-label='Measure']")
    else:
        page.click(".c-result-top .r-actions button:has-text('Measure')")
    page.wait_for_function("() => window.FINDALINE_VIEW.map.isMeasuring", timeout=WAIT)
    first = page.evaluate("() => F.empty(30)")
    second = page.evaluate("([p]) => F.empty(30, p)", [first])
    assert first and second, "no two empty points on the map"
    for at in (first, second):
        if phone:
            _tap(page, at["x"], at["y"])
        else:
            page.mouse.click(at["x"], at["y"])
            page.evaluate("() => T.frames()")
    return first


@pytest.mark.parametrize("after", ["measure", "select"])
def test_late_measure_answer_is_dropped(site, after):
    """Measure's answer that comes late (the server's profile still on its way) is dropped once it is not the latest
    measurement's (Measure pressed again, one point taken: it goes on) or a new line was selected meanwhile (its card
    keeps the selected line's profile: the planner's seam). The code review of the catch-up, findings 2 and 3."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _view(browser, site, DESKTOP, script=PROFILE_LATE)
            _state(page, "view.setLevel('spots');")
            first = _measure_two(page)
            page.wait_for_function("() => HELD.length === 1", timeout=WAIT)
            if after == "measure":
                page.click(".c-result-top .r-actions button:has-text('Measure')")
                page.wait_for_selector(".r-act .r-tip-beside", timeout=WAIT)
                third = page.evaluate("([p]) => F.empty(30, p, 120)", [first])
                page.mouse.click(third["x"], third["y"])
            else:
                _state(page, "view.select(view.order[0]);")
                page.wait_for_selector(".c-col-map > .r-card .fal-profile-chart", timeout=WAIT)
            page.evaluate("() => T.frames()")
            before = page.evaluate(LATE_NOW)
            page.evaluate("() => RELEASE(0)")
            page.wait_for_function("() => ANSWERED === 1", timeout=WAIT)
            page.evaluate("() => T.frames()")
            page.evaluate("() => T.frames()")
            got = page.evaluate(LATE_NOW)
            assert page.errors == []
        finally:
            browser.close()
    assert got == before, (before, got)  # the late answer changed nothing
    if after == "measure":
        assert (got["measuring"], got["points"], got["frameMeasured"]) == (True, 1, False), got
    else:
        assert got["selected"] is not None and (got["points"], got["frameMeasured"]) == (0, False), got
        assert len(got["titles"]) == 1 and got["titles"][0].startswith("Profile · "), got


def test_phone_measured_line_kept_in_sight_with_a_selection(site):
    """A phone at the low stop with a spot selected whose lower anchor lies under the half stop's top: Measure, two
    points near the top of the map's room; the sheet rises to half for the measured profile, and once it rests the
    measured line (whose profile is shown) is in the map's room, the selected line not brought back over it (the
    desktop's keepFree likewise). The code review of the catch-up, finding 1."""
    from playwright.sync_api import sync_playwright
    pick = """() => { const {view} = window.FINDALINE_VIEW, b = T.box();
      for (const spot of Array.from(view.inView.spots)) { const e = T.ends(view.shownOf(spot));
        if (Math.min(e[0], e[2]) < 60 || Math.max(e[0], e[2]) > b.width - 60) continue;
        if (Math.abs(e[1] - e[3]) > 90 || Math.min(e[1], e[3]) < 150) continue;
        return spot; } return null; }"""
    top_points = """() => { const room = F.room(), boxes = T.controls(), r = 30, out = [];
      for (let y = room[1] + 40; y < room[1] + 130; y += 11) for (let x = room[0] + 40; x < room[2] - 40; x += 13) {
        if (boxes.some((c) => x > c.left - r && x < c.right + r && y > c.top - r && y < c.bottom + r)) continue;
        if (out.length && Math.hypot(x - out[0].x, y - out[0].y) < 120) continue;
        out.push({x, y}); if (out.length === 2) return out; }
      return out; }"""
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _view(browser, site, PHONE, script=PROFILE_STUB)
            page.wait_for_function("() => F.snap() === 'peek' && F.rest()", timeout=WAIT)
            _state(page, "view.setLevel('spots');")
            spot = page.evaluate(pick)
            assert spot is not None, "no short line in view"
            _state(page, f"view.select({spot});")
            if page.evaluate("() => F.snap()") != "peek":
                page.focus(".u-sheet-handle")
                page.keyboard.press("ArrowDown")
            page.wait_for_function("() => F.snap() === 'peek' && F.rest()", timeout=WAIT)
            # the selected line's lower anchor 60 px under the half stop's top (above the low stop's top)
            _state(page, """const e = T.ends(view.selected.row), b = T.box(), half = b.height - Math.max(132, b.height * 0.5);
              leaflet.panBy([0, Math.round(Math.max(e[1], e[3]) - (half + 60))], {animate: false});""")
            checks = page.evaluate("() => Number(document.querySelector('.c-col-map').dataset.sheetChecks || 0)")
            _tap_on(page, ".c-pill [aria-label='Measure']")
            page.wait_for_function("() => window.FINDALINE_VIEW.map.isMeasuring", timeout=WAIT)
            pts = page.evaluate(top_points)
            assert len(pts) == 2, pts
            for at in pts:
                _tap(page, at["x"], at["y"])
            page.wait_for_function("() => !!window.FINDALINE_VIEW.measured && F.snap() === 'half' && F.rest()", timeout=WAIT)
            page.wait_for_function(f"() => Number(document.querySelector('.c-col-map').dataset.sheetChecks || 0) > {checks} && "
                                   "!window.FINDALINE_MAP._animatingZoom && !(window.FINDALINE_MAP._panAnim && window.FINDALINE_MAP._panAnim._inProgress)",
                                   timeout=WAIT)
            page.evaluate("() => T.frames()")
            got = page.evaluate("() => ({measuredInRoom: F.inRoom(window.FINDALINE_VIEW.measured), selected: window.FINDALINE_VIEW.view.selected !== null})")
            assert page.errors == []
        finally:
            browser.close()
    assert got == {"measuredInRoom": True, "selected": True}, got


def test_phone_measured_line_moved_away_stays_away(site):
    """A phone: Measure's line shown at half, then the person pans it out of the map and moves the sheet down and up
    again: the map is left as they left it (the sheet's check keeps a measured line in sight only at the rest after its
    first show: "a move of theirs is never undone")."""
    from playwright.sync_api import sync_playwright
    centre = "() => { const c = window.FINDALINE_MAP.getCenter(); return [c.lat, c.lng, window.FINDALINE_MAP.getZoom()]; }"
    checks = "() => Number(document.querySelector('.c-col-map').dataset.sheetChecks || 0)"
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _view(browser, site, PHONE, script=PROFILE_STUB)
            _state(page, "view.setLevel('spots');")
            _measure_two(page, phone=True)
            page.wait_for_function("() => !!window.FINDALINE_VIEW.measured && F.snap() === 'half' && F.rest()", timeout=WAIT)
            page.wait_for_function("() => !window.FINDALINE_MAP._animatingZoom", timeout=WAIT)
            _state(page, "leaflet.panBy([0, -600], {animate: false});")  # the person's move: the line out of the map
            moved = page.evaluate(centre)
            assert page.evaluate("() => F.inRoom(window.FINDALINE_VIEW.measured)") is False
            for key, stop in (("ArrowDown", "peek"), ("ArrowUp", "half")):
                before = page.evaluate(checks)
                page.focus(".u-sheet-handle")
                page.keyboard.press(key)
                page.wait_for_function(f"() => F.snap() === '{stop}' && F.rest()", timeout=WAIT)
                page.wait_for_function(f"() => ({checks})() > {before}", timeout=WAIT)
            page.evaluate("() => T.frames()")
            after = page.evaluate(centre)
            assert page.errors == []
        finally:
            browser.close()
    assert after == moved, (moved, after)


def test_link_answer_during_a_measurement(site):
    """A link's line outside the run, its profile on its way; Measure pressed and one point taken; then the link's
    answer comes: the measurement goes on (Measure's start clears model.measuredLink, so openLinked drops the late
    answer: the second code review's finding)."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _view(browser, site, DESKTOP, line=OUTSIDE, script=PROFILE_LATE)
            page.wait_for_function("() => HELD.length === 1", timeout=WAIT)
            page.click(".c-result-top .r-actions button:has-text('Measure')")
            page.wait_for_function("() => window.FINDALINE_VIEW.map.isMeasuring", timeout=WAIT)
            first = page.evaluate("() => F.empty(30)")
            page.mouse.click(first["x"], first["y"])
            page.evaluate("() => T.frames()")
            before = page.evaluate(LATE_NOW)
            page.evaluate("() => RELEASE(0)")
            page.wait_for_function("() => ANSWERED === 1", timeout=WAIT)
            page.evaluate("() => T.frames()")
            page.evaluate("() => T.frames()")
            after = page.evaluate(LATE_NOW)
            assert page.errors == []
        finally:
            browser.close()
    assert (before["measuring"], before["points"]) == (True, 1), before
    assert (after["measuring"], after["points"], after["frameMeasured"]) == (True, 1, False), after


# Every control's box over the map (T.CONTROLS), and whether a point lies inside one (viewport px)
UNDER = """([x, y]) => [...document.querySelectorAll(T.CONTROLS)].map((e) => e.getBoundingClientRect())
  .filter((r) => r.width && r.height && x >= r.left && x <= r.right && y >= r.top && y <= r.bottom).length"""


def _ends_clear(page) -> list:
    """The measured line's two ends in the viewport and the number of control boxes each lies in."""
    ends = page.evaluate("() => F.ends(window.FINDALINE_VIEW.measured)")
    return [[round(x), round(y), page.evaluate(UNDER, [x, y])] for x, y in ends]


def test_phone_rest_fit_brings_the_ends_clear(site):
    """A phone (390 x 664): Measure's points pressed at the low stop, one where the status line stands once the sheet
    is at half; the answer comes, the sheet rises, and at its rest the measured line is moved so that both ends lie
    clear of every control (the fit at the first rest firing; the second design review's N1)."""
    from playwright.sync_api import sync_playwright
    centre = "() => { const c = window.FINDALINE_MAP.getCenter(); return [c.lat, c.lng, window.FINDALINE_MAP.getZoom()]; }"
    checks = "() => Number(document.querySelector('.c-col-map').dataset.sheetChecks || 0)"
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _view(browser, site, SMALL_PHONE, script=PROFILE_STUB)
            _state(page, "view.setLevel('spots');")
            # where the status line stands at half (read at half, then back to the low stop)
            page.focus(".u-sheet-handle")
            page.keyboard.press("ArrowUp")
            page.wait_for_function("() => F.snap() === 'half' && F.rest()", timeout=WAIT)
            page.evaluate("() => T.frames()")
            status = page.evaluate("() => F.rect('.v-status')")
            page.keyboard.press("ArrowDown")
            page.wait_for_function("() => F.snap() === 'peek' && F.rest()", timeout=WAIT)
            page.evaluate("() => T.frames()")
            _tap_on(page, ".c-pill [aria-label='Measure']")
            page.wait_for_function("() => window.FINDALINE_VIEW.map.isMeasuring", timeout=WAIT)
            a = [status[2] - 20, (status[1] + status[3]) / 2]  # under the status line at half; free map at the low stop
            assert page.evaluate(UNDER, a) == 0, (a, status)
            b = [a[0] - 150, a[1] + 60]
            before = page.evaluate(centre)
            checked = page.evaluate(checks)
            for at in (a, b):
                _tap(page, at[0], at[1])
            page.wait_for_function("() => !!window.FINDALINE_VIEW.measured && F.snap() === 'half' && F.rest()", timeout=WAIT)
            page.wait_for_function(f"() => ({checks})() > {checked} && !window.FINDALINE_MAP._animatingZoom", timeout=WAIT)
            page.evaluate("() => T.frames()")
            ends = _ends_clear(page)
            after = page.evaluate(centre)
            fits = page.evaluate("() => Number(document.querySelector('.c-col-map').dataset.measuredFits || 0)")
            assert page.errors == []
        finally:
            browser.close()
    print("rest fits", fits, "moved", after != before, "ends", ends)
    assert after != before and fits >= 1, (fits, "the rest did not move the map for the line")  # the fit at the first rest fired
    assert all(n == 0 for _, _, n in ends), ends


def test_fit_due_not_left_over_a_later_move(site):
    """A phone: Measure's answer comes at the low stop (the sheet rises for it), the sheet is sent back to the low stop
    before it rests at half; the person then pans the measured line out of the map and raises the sheet to half: the
    map stays as they left it, and no rest kept the measured line in sight (the fit belongs to the rest after the first
    show only: the second code review; without the reset at the sheet's other stop the low stop's rest fitted it, the
    third code review's test map: `data-measured-rests` counts those rests whether or not the map moved)."""
    from playwright.sync_api import sync_playwright
    centre = "() => { const c = window.FINDALINE_MAP.getCenter(); return [c.lat, c.lng, window.FINDALINE_MAP.getZoom()]; }"
    checks = "() => Number(document.querySelector('.c-col-map').dataset.sheetChecks || 0)"
    still = "() => !window.FINDALINE_MAP._animatingZoom && !(window.FINDALINE_MAP._panAnim && window.FINDALINE_MAP._panAnim._inProgress)"
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _view(browser, site, PHONE, script=PROFILE_LATE)
            page.wait_for_function("() => F.snap() === 'peek' && F.rest()", timeout=WAIT)
            _state(page, "view.setLevel('spots');")
            _measure_two(page, phone=True)
            page.wait_for_function("() => HELD.length === 1", timeout=WAIT)
            page.wait_for_function("() => F.snap() === 'peek' && F.rest()", timeout=WAIT)
            # the answer, and the sheet sent back to the low stop as soon as its stop is half (in the same task as that
            # render: no frame, so no rest of the sheet, comes between)
            sent = page.evaluate("""() => new Promise((ok) => { const sheet = document.querySelector('.u-sheet');
              const watch = new MutationObserver(() => { if (!sheet.classList.contains('u-half')) return; watch.disconnect();
                const at = {rest: F.rest(), rests: Number(document.querySelector('.c-col-map').dataset.measuredRests || 0)};
                document.querySelector('.u-sheet-handle').dispatchEvent(new KeyboardEvent('keydown', {key: 'ArrowDown', bubbles: true}));
                ok(at); });
              watch.observe(sheet, {attributes: true, attributeFilter: ['class']}); RELEASE(0); })""")
            rested = sent["rest"] or sent["rests"] > 0
            page.wait_for_function("() => F.snap() === 'peek' && F.rest()", timeout=WAIT)
            page.wait_for_function(still, timeout=WAIT)
            page.evaluate("() => T.frames()")
            _state(page, "leaflet.panBy([0, -600], {animate: false});")
            moved = page.evaluate(centre)
            before = page.evaluate(checks)
            page.focus(".u-sheet-handle")
            page.keyboard.press("ArrowUp")
            page.wait_for_function("() => F.snap() === 'half' && F.rest()", timeout=WAIT)
            page.wait_for_function(f"() => ({checks})() > {before}", timeout=WAIT)
            page.wait_for_function(still, timeout=WAIT)
            page.evaluate("() => T.frames()")
            after = page.evaluate(centre)
            rests = page.evaluate("() => Number(document.querySelector('.c-col-map').dataset.measuredRests || 0)")
            assert page.errors == []
        finally:
            browser.close()
    assert rested is False, "the sheet rested at half before it was sent back: the sequence was not reached"
    assert after == moved, (moved, after)
    assert rests == 0, f"{rests} rests kept the measured line in sight after the sheet was sent elsewhere"


STILL = "() => !window.FINDALINE_MAP._animatingZoom && !(window.FINDALINE_MAP._panAnim && window.FINDALINE_MAP._panAnim._inProgress)"
LINE_LEAST = 120  # px: SpotColumns' floor of a measured line's length on the screen (the planner's rule)

# The bar's padding as the frame reads it (barPadding: under the switch, above the foot; a desktop's foot stands above
# its card, a phone's above its sheet), map container px
BAR = r"""() => { const col = document.querySelector('.c-col-map'), box = col.getBoundingClientRect();
  const bar = col.querySelector('.v-switch')?.getBoundingClientRect(), foot = col.querySelector('.v-foot')?.getBoundingClientRect();
  const sheet = document.querySelector('.u-sheet'), covered = sheet ? Math.max(0, Math.round(box.bottom - sheet.getBoundingClientRect().top)) : 0;
  return {top: bar && bar.height ? Math.round(bar.bottom - box.top) + 4 : 40, right: 0, left: 0,
          bottom: foot && foot.height ? Math.max(60 + covered, Math.round(box.bottom - foot.top) + 4) : 60 + covered}; }"""
# Each end of the measured line as a fit into the bar's room alone puts it (the frame before the second design
# review's N1: no control counted, no endsClear): viewport px and the number of control boxes it lies in; the map put
# back as it was
PLAIN_FIT = r"""([pad]) => { const m = window.FINDALINE_MAP, keep = [m.getCenter(), m.getZoom()], l = window.FINDALINE_VIEW.measured;
  window.FINDALINE_VIEW.map.zoomToLine(l, pad);
  const ends = F.ends(l).map(([x, y]) => [Math.round(x), Math.round(y), [...document.querySelectorAll(T.CONTROLS)]
    .map((e) => e.getBoundingClientRect()).filter((r) => r.width && r.height && x >= r.left && x <= r.right && y >= r.top && y <= r.bottom).length]);
  m.setView(keep[0], keep[1], {animate: false}); return ends; }"""


def _length(ends) -> float:
    """The on-screen length between two ends ([x, y, ...] each)."""
    return round(((ends[0][0] - ends[1][0]) ** 2 + (ends[0][1] - ends[1][1]) ** 2) ** 0.5, 1)


def _centre_line(browser, site: str, dlat: float, dlon: float) -> str:
    """A line from the centre of the run with both coast boxes (where its boxes or chips stay in view), `dlat` x `dlon`
    degrees long: the text of a link's line."""
    page = _open(browser, f"{site}#run={BOXES}", DESKTOP, script=FRAME)
    c = page.evaluate("() => window.FINDALINE_VIEW.view.model.data.center")
    page.context.close()
    return f"{c[0]:.6f},{c[1]:.6f},{c[0] + dlat:.6f},{c[1] + dlon:.6f}"


def _link_at_rest(browser, site: str, device: dict, line: str):
    """The run with both coast boxes opened at a link's line (measured: the profile stubbed), fitted and, on a phone,
    the sheet at half and resting with its check made; the page."""
    page = _open(browser, f"{site}#run={BOXES}&line={urllib.parse.quote(line, safe='')}", device, script=FRAME + PROFILE_STUB)
    page.wait_for_function("() => !!window.FINDALINE_VIEW && !!window.FINDALINE_VIEW.measured", timeout=WAIT)
    if device is not DESKTOP:
        page.wait_for_function("() => F.snap() === 'half' && F.rest()", timeout=WAIT)
        page.wait_for_function("() => Number(document.querySelector('.c-col-map').dataset.sheetChecks || 0) > 0", timeout=WAIT)
    page.wait_for_function(STILL, timeout=WAIT)
    page.evaluate("() => T.frames()")
    return page


# A link's line from the run's centre whose fit into the bar's room alone puts an end under a coast box (measured,
# B3's probe_fix3): a flat one on the desktop (its west end under the shore's box), a north-west to south-east one on
# 412 x 839 (its north-west end under the chips)
FLAT, NWSE = (0.0001, 0.0016), (-0.0006, 0.0012)


@pytest.mark.parametrize("device, shape", [(DESKTOP, FLAT), (PIXEL, NWSE)], ids=["desktop", "412"])
def test_fitted_measured_line_clear_of_controls(boxes_site, device, shape):
    """A link's measured line (always fitted) on the run with both coast boxes (the uncertain shore's, the coarser
    terrain's), at the run's centre so that the boxes or chips stay in view, and shaped so that a fit into the bar's
    room alone puts an end under one of them (checked on the page: the frame before the second design review's N1).
    Once fitted (a phone: the sheet at half and resting) both its ends lie outside every control's box, and the line
    is not squeezed: at least LINE_LEAST px and at least half the plain fit's length (the third code review: the fit
    goes into the bar's room, endsClear moves it from under the controls)."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            line = _centre_line(browser, boxes_site, *shape)
            page = _link_at_rest(browser, boxes_site, device, line)
            ends = _ends_clear(page)
            plain = page.evaluate(PLAIN_FIT, [page.evaluate(BAR)])
            assert page.errors == []
        finally:
            browser.close()
    print("link fitted", device.get("viewport"), "ends", ends, _length(ends), "px; plain fit", plain, _length(plain), "px")
    assert any(n > 0 for _, _, n in plain), ("the plain fit puts no end under a control: the state tests nothing", plain)
    assert all(n == 0 for _, _, n in ends), ends
    assert _length(ends) >= LINE_LEAST and _length(ends) >= _length(plain) / 2, (_length(ends), _length(plain))


@pytest.mark.parametrize("where", ["centre", "outside"])
@pytest.mark.parametrize("device", [SMALL_PHONE, PIXEL], ids=["390", "412"])
def test_link_line_keeps_the_floor_at_rest(boxes_site, device, where):
    """A link's measured line on the run with both coast boxes, the sheet at half and resting: at least LINE_LEAST px
    long on the screen (the planner's floor; an end may then lie under a control, printed for the gate). At the run's
    centre both chips stay in view (the third code review's 27 px on 390 x 664: a wide, short free strip chosen by
    area); outside the run they are gone (its 9.2 px: the first show squeezed the line into a band predicted from the
    low stop)."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            line = _centre_line(browser, boxes_site, 0.0004, 0.0005) if where == "centre" else OUTSIDE
            page = _link_at_rest(browser, boxes_site, device, line)
            ends = _ends_clear(page)
            counts = page.evaluate("() => { const d = document.querySelector('.c-col-map').dataset; return [d.measuredRests || 0, d.measuredFits || 0]; }")
            assert page.errors == []
        finally:
            browser.close()
    print("link at rest", device.get("viewport"), where, "length", _length(ends), "px; ends", ends, "rests, fits", counts)
    assert _length(ends) >= LINE_LEAST, ends


# The rows' ends in the viewport and the number of control boxes each lies in (T.ends: map container px)
ROW_UNDER = r"""([row]) => { const e = T.ends(row), b = T.box();
  return [[e[0], e[1]], [e[2], e[3]]].map(([x, y]) => [Math.round(x + b.left), Math.round(y + b.top), [...document.querySelectorAll(T.CONTROLS)]
    .map((c) => c.getBoundingClientRect()).filter((r) => r.width && r.height && x + b.left >= r.left && x + b.left <= r.right && y + b.top >= r.top && y + b.top <= r.bottom).length]); }"""


def test_selected_fit_clear_of_controls_card_open(boxes_site):
    """1400 x 900, the run with both coast boxes, a line's card open: the frame's padding counts the controls over the
    map (the third code review's finding 3: the halves are taken of the part of the map in view, above the card; with
    the column's halves it stayed the bar's), and a line of the run opened by its link is fitted with both ends
    outside every control's box, where a fit into the bar's room alone puts an end under one (that line found on the
    page first, among the first 120 of the list's order)."""
    from playwright.sync_api import sync_playwright
    pick = r"""([pad]) => { const {view, map} = window.FINDALINE_VIEW, m = window.FINDALINE_MAP, keep = [m.getCenter(), m.getZoom()];
      const under = (row) => ROW(row).filter((e) => e[2] > 0).length;
      let found = null;
      for (const spot of Array.from(view.order).slice(0, 120)) { const row = view.shownOf(spot);
        map.zoomTo(row, pad); const a = under(row); map.zoomTo(row, map.options.padding()); const b = under(row);
        if (a > 0 && b === 0) { found = [spot, row]; break; } }
      m.setView(keep[0], keep[1], {animate: false}); return found; }"""
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _open(browser, f"{boxes_site}#run={BOXES}", DESKTOP, script=FRAME + f"window.ROW = (row) => ({ROW_UNDER})([row]);")
            _state(page, "view.select(view.order[0]);")
            page.wait_for_selector(".c-col-map > .r-card .fal-profile-chart", timeout=WAIT)
            page.wait_for_function(STILL, timeout=WAIT)
            page.evaluate("() => T.frames()")
            found = page.evaluate(pick, [page.evaluate(BAR)])
            assert found is not None, "no line of the list whose plain fit has an end under a control"
            spot, row = found
            _state(page, f"view.select({spot});")
            page.wait_for_function(f"() => new URLSearchParams(location.hash.slice(1)).get('line') && window.FINDALINE_VIEW.view.selected?.row === {row}", timeout=WAIT)
            line = page.evaluate("() => new URLSearchParams(location.hash.slice(1)).get('line')")
            page.context.close()
            page = _open(browser, f"{boxes_site}#run={BOXES}&line={urllib.parse.quote(line, safe='')}", DESKTOP,
                         script=FRAME + f"window.ROW = (row) => ({ROW_UNDER})([row]);")
            page.wait_for_selector(".c-col-map > .r-card .fal-profile-chart", timeout=WAIT)
            page.wait_for_function(STILL, timeout=WAIT)
            page.evaluate("() => T.frames()")
            got = page.evaluate("""([row]) => ({selected: window.FINDALINE_VIEW.view.selected?.row ?? null, ends: ROW(row),
              own: window.FINDALINE_VIEW.map.options.padding()})""", [row])
            bar = page.evaluate(BAR)
            assert page.errors == []
        finally:
            browser.close()
    print("selected fit, card open: row", row, "ends", got["ends"], _length(got["ends"]), "px; padding", got["own"], "bar", bar)
    assert got["selected"] == row, got
    assert got["own"]["top"] > bar["top"], (got["own"], bar)
    assert all(n == 0 for _, _, n in got["ends"]), got["ends"]


def test_selected_fit_clear_of_controls_phone_half(site):
    """412 x 839 at half (the view clip's run: no coast chips): the frame's padding counts the layers button under the
    switch (the column's halves left it the bar's: the third code review), and a line chosen in the list while its
    line is out of the map is brought back (the list's reveal, with that padding) with both ends outside every
    control's box. Not reachable (measured, B3's probe_fix3): 390 x 664 at half, whose bar leaves 97 px (under
    CLEAR_ROOM), either phone at half with both coast chips (76 px), and this one with a level held ("Back to Auto"
    in the foot: 108 px); there the bar's padding stays. Here the bar's
    padding alone also keeps the ends clear (the fit's 60 px margin): the padding's top is what fails without the fix."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _view(browser, site, PIXEL, script=f"window.ROW = (row) => ({ROW_UNDER})([row]);")
            page.wait_for_function("() => F.snap() === 'peek' && F.rest()", timeout=WAIT)
            # (under Auto: a level held adds "Back to Auto" to the foot, and the room left is then under CLEAR_ROOM)
            page.focus(".u-sheet-handle")
            page.keyboard.press("ArrowUp")
            page.wait_for_function("() => F.snap() === 'half' && F.rest()", timeout=WAIT)
            page.wait_for_function(STILL, timeout=WAIT)
            page.evaluate("() => T.frames()")
            own, bar = page.evaluate("() => window.FINDALINE_VIEW.map.options.padding()"), page.evaluate(BAR)
            layers = page.evaluate("() => { const r = F.rect('.v-map .leaflet-control-layers'), b = T.box(); return r && [r[1] - b.top, r[3] - b.top]; }")
            _state(page, "leaflet.panBy([0, -3000], {animate: false});")  # every line out of the map
            row = page.evaluate("() => Number(document.querySelector('.vl-list .vl-rows .vl-main').dataset.row)")
            _tap_on(page, ".vl-list .vl-rows .vl-main >> nth=0")
            page.wait_for_function(f"() => window.FINDALINE_VIEW.view.selected?.row === {row}", timeout=WAIT)
            page.wait_for_function(STILL, timeout=WAIT)
            page.evaluate("() => T.frames()")
            ends = page.evaluate("([row]) => ROW(row)", [row])
            room = page.evaluate("() => F.room()")
            snap = page.evaluate("() => F.snap()")
            assert page.errors == []
        finally:
            browser.close()
    print("selected fit at half: padding", own, "bar", bar, "layers", layers, "ends", ends, _length(ends), "px; sheet", snap)
    assert layers and own["top"] >= round(layers[1]) + 8 - 1 and own["top"] > bar["top"], (own, bar, layers)
    assert snap == "half" and all(n == 0 for _, _, n in ends), (snap, ends)
    assert all(room[1] <= y <= room[3] for _, y, _ in ends), (ends, room)


def test_low_desktop_card_folded_keeps_controls_apart(boxes_site):
    """A 1024 x 768 desktop with both coast boxes and a line selected: with the card folded by the person no control
    covers another (T.boxes); the card open at that size (the map is higher than today's low threshold, LIMITS.low
    420 px, so it opens) leaves controls covered, printed for the gate (the second design review's N4)."""
    from playwright.sync_api import sync_playwright
    low = {"viewport": {"width": 1024, "height": 768}}
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _open(browser, f"{boxes_site}#run={BOXES}", low, script=FRAME)
            page.evaluate("() => { window.FINDALINE_MAP.zoomOut(1, {animate: false}); }")
            # (under Auto: no level held, so no "Back to Auto", which _apart sizes for a finger)
            _state(page, "view.select(view.inView.best[0] ?? view.order[0]);")
            page.wait_for_selector(".c-col-map > .r-card .fal-profile-chart", timeout=WAIT)
            page.evaluate("() => T.frames()")
            opened = page.evaluate("() => T.boxes()")
            page.click(".r-card .r-fold")
            page.wait_for_selector(".r-card.r-card-folded", timeout=WAIT)
            page.evaluate("() => T.frames()")  # the foot rides down with the card a frame later
            page.evaluate("() => T.frames()")
            _apart(page, "1024 x 768, the card folded")
            assert page.errors == []
        finally:
            browser.close()
    names = sorted(opened)
    covered = [(a, b) for k, a in enumerate(names) for b in names[k + 1:]
               if min(opened[a][2], opened[b][2]) - max(opened[a][0], opened[b][0]) > 0.5
               and min(opened[a][3], opened[b][3]) - max(opened[a][1], opened[b][1]) > 0.5]
    print("1024 x 768, the card open: covered pairs", covered, {n: opened[n] for n in names})


TABLET = {"viewport": {"width": 1024, "height": 768}, "is_mobile": True, "has_touch": True, "device_scale_factor": 2}


@pytest.mark.parametrize("device", [{"viewport": {"width": 1024, "height": 768}}, TABLET], ids=["mouse", "touch"])
def test_list_at_1024_keeps_heads_and_values_apart(site, device):
    """A 1024 px desktop (the list 320 px wide), with a mouse and with a touch screen (a tablet held sideways: the
    star 44 px): no head or value of the list's rows overlaps its neighbour in the same row, no value is cut, and each
    head stands over its values (its right edge on theirs, in every block of heads), in "Best in view" and in the tree,
    sorted by length, by the highest point and by clearance (the second design review's N3: the row star's room taken
    from the rows' gaps and edges in a narrow list; the third code review's finding 2: on a touch screen the heads
    kept a mouse's 24 px for the star, 5 to 20 px off, and 30 values were cut)."""
    from playwright.sync_api import sync_playwright
    read = """() => { const r = (e) => e.getBoundingClientRect(), bad = [], cut = [], off = [];
      const row = (cells) => { for (let k = 1; k < cells.length; k++) { const a = r(cells[k - 1]), b = r(cells[k]);
          if (a.width && b.width && a.bottom > b.top + 0.5 && b.bottom > a.top + 0.5 && a.right > b.left + 0.5)
            bad.push([cells[k - 1].textContent.trim().slice(0, 14), cells[k].textContent.trim().slice(0, 14)]); } };
      const own = (m) => [...m.children].filter((c) => !c.classList.contains('u-sr'));
      const heads = [...document.querySelectorAll('.c-col-list .vl-cols')], rows = [...document.querySelectorAll('.c-col-list .vl-main')];
      heads.forEach((h) => row([...h.children]));
      rows.forEach((m) => row(own(m)));
      rows.forEach((m) => m.querySelectorAll('.vl-v').forEach((v) => { if (v.scrollWidth > v.clientWidth + 1) cut.push(v.textContent.trim().slice(0, 14)); }));
      heads.forEach((h) => { const m = h.parentElement.querySelector('.vl-rows .vl-main'); if (!m) return;
        const hc = [...h.children], mc = own(m).filter((c) => !c.classList.contains('vl-lab'));
        for (let k = 2; k < Math.min(hc.length, mc.length); k++) { const d = Math.round(r(hc[k]).right - r(mc[k]).right); if (d) off.push([hc[k].textContent.trim(), d]); } });
      return {list: Math.round(r(document.querySelector('.c-col-list')).width), heads: heads.length, rows: rows.length,
              coarse: matchMedia('(pointer: coarse)').matches, star: Math.round(r(document.querySelector('.c-col-list .vl-star')).width),
              tree: document.querySelectorAll('.c-col-list .vl-tree .vl-main').length, bad, cut, off}; }"""
    got = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _view(browser, site, device)
            for sort in ("len", "hmax", "clr"):
                _state(page, f"view.setLevel('spots'); view.setSort('{sort}');")
                got[sort] = page.evaluate(read)
            assert page.errors == []
        finally:
            browser.close()
    touch = device is TABLET
    for sort, g in got.items():
        assert g["coarse"] is touch and g["star"] == (44 if touch else 24), (sort, g)
        assert g["list"] <= 360 and g["heads"] >= 2 and g["rows"] > 10 and g["tree"] > 0, (sort, g)
        assert g["bad"] == [] and g["cut"] == [] and g["off"] == [], (sort, g)


def test_today_page_drops_a_late_answer(site):
    """Today's page (no flag) shares Measure's guard: Measure, two points, its profile shown; Measure again, two points
    (answer A held), Measure again and one point, A comes: still measuring and the dock as it was (the second code
    review's probe of today's branch)."""
    from playwright.sync_api import sync_playwright
    points = """([k]) => { const r = document.querySelector('.c-col-map .leaflet-container').getBoundingClientRect();
      return {x: r.left + r.width * (0.3 + 0.1 * k), y: r.top + r.height * (0.35 + 0.05 * k)}; }"""
    now = """() => ({measuring: window.FINDALINE_RESULT.view.isMeasuring,
                    titles: [...document.querySelectorAll('.r-dock-bar b')].map((b) => b.textContent)})"""
    measure = ".c-result-top .r-actions button:has-text('Measure')"
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _open(browser, f"{site}#run={BIG}", DESKTOP, flag=False, script=FRAME + PROFILE_LATE)
            page.wait_for_function("() => !!window.FINDALINE_RESULT && !!document.querySelector('.c-col-map .leaflet-container')", timeout=WAIT)

            def take(ks):
                page.click(measure)
                page.wait_for_function("() => window.FINDALINE_RESULT.view.isMeasuring", timeout=WAIT)
                for k in ks:
                    at = page.evaluate(points, [k])
                    page.mouse.click(at["x"], at["y"])
                    page.evaluate("() => T.frames()")
            take((0, 3))
            page.wait_for_function("() => HELD.length === 1", timeout=WAIT)
            page.evaluate("() => RELEASE(0)")
            page.wait_for_selector(".r-dock-bar b:has-text('Measured profile')", timeout=WAIT)
            first = page.evaluate(now)
            take((1, 4))
            page.wait_for_function("() => HELD.length === 2", timeout=WAIT)
            take((2,))
            before = page.evaluate(now)
            page.evaluate("() => RELEASE(1)")
            page.wait_for_function("() => ANSWERED === 2", timeout=WAIT)
            page.evaluate("() => T.frames()")
            page.evaluate("() => T.frames()")
            after = page.evaluate(now)
            assert page.errors == []
        finally:
            browser.close()
    assert first["measuring"] is False and "Measured profile" in first["titles"], first
    assert before["measuring"] is True and after == before, (before, after)


def test_late_answer_after_crossing_the_phone_width(site):
    """Measure's answer that comes after the window crossed the phone's width (Measure on a desktop, the answer on a
    phone) is shown as any measured line there: the sheet at half with its dock first, the line in the map's room; a
    measured line kept across the width is drawn again by the new canvas, its profile in the card (the code review's
    finding 6; B3's probe of the catch-up)."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _view(browser, site, {**DESKTOP, "viewport": {"width": 1280, "height": 820}}, script=PROFILE_LATE)
            _state(page, "view.setLevel('spots');")
            _measure_two(page)
            page.wait_for_function("() => HELD.length === 1", timeout=WAIT)
            page.set_viewport_size({"width": 600, "height": 820})
            page.wait_for_selector(".c-result-phone", timeout=WAIT)
            page.wait_for_function("() => F.snap() === 'peek' && F.rest()", timeout=WAIT)
            page.evaluate("() => RELEASE(0)")
            page.wait_for_function("() => !!window.FINDALINE_VIEW.measured && F.snap() === 'half' && F.rest()", timeout=WAIT)
            page.wait_for_selector(".u-sheet-body > .r-dock:first-child .fal-profile-chart", timeout=WAIT)
            page.wait_for_function("() => !window.FINDALINE_MAP._animatingZoom", timeout=WAIT)
            page.evaluate("() => T.frames()")
            phone = page.evaluate("() => ({inRoom: F.inRoom(window.FINDALINE_VIEW.measured), points: window.FINDALINE_VIEW.map.drawn().measured.length, "
                                  "title: document.querySelector('.u-sheet-body > .r-dock:first-child .r-dock-bar b').textContent})")
            # back across: the card shows it and the new canvas draws its points
            page.set_viewport_size({"width": 1280, "height": 820})
            page.wait_for_selector(".c-col-map > .r-card .fal-profile-chart", timeout=WAIT)
            page.evaluate("() => T.frames()")
            wide = page.evaluate("() => ({points: window.FINDALINE_VIEW.map.drawn().measured.length, title: document.querySelector('.r-card .r-dock-bar b').textContent})")
            assert page.errors == []
        finally:
            browser.close()
    assert phone == {"inRoom": True, "points": 2, "title": "Measured profile"}, phone
    assert wide == {"points": 2, "title": "Measured profile"}, wide


@pytest.mark.parametrize("device", [DESKTOP, PHONE], ids=["desktop", "phone"])
def test_closing_a_measured_profile_clears_it(site, device):
    """A link's measured line (outside the run): its profile's close, in the desktop's card or the phone's dock first
    in the sheet, clears the frame's measured line, model.measuredLink and the canvas's points (the brief's "its close
    clears model.measuredLink"); Measure's own line likewise on a phone."""
    from playwright.sync_api import sync_playwright
    now = """() => ({measured: window.FINDALINE_VIEW.measured, link: window.FINDALINE_VIEW.view.model.measuredLink,
                     points: window.FINDALINE_VIEW.map.drawn().measured.length})"""
    where = ".c-col-map > .r-card" if device is DESKTOP else ".u-sheet-body > .r-dock:first-child"
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _view(browser, site, device, line=OUTSIDE, script=PROFILE_STUB)
            page.wait_for_selector(f"{where} .fal-profile-chart", timeout=WAIT)
            opened = page.evaluate(now)
            press = (lambda sel: page.click(sel)) if device is DESKTOP else (lambda sel: _tap_on(page, sel))
            press(f"{where} .r-dock-bar [aria-label='Close the profile']")
            page.wait_for_function("() => window.FINDALINE_VIEW.measured === null", timeout=WAIT)
            closed = page.evaluate(now)
            measure = None
            if device is PHONE:  # Measure's own line: its dock's close
                _state(page, "view.setLevel('spots');")
                _measure_two(page, phone=True)
                page.wait_for_selector(f"{where} .fal-profile-chart", timeout=WAIT)
                _tap_on(page, f"{where} .r-dock-bar [aria-label='Close the profile']")
                page.wait_for_function("() => window.FINDALINE_VIEW.measured === null", timeout=WAIT)
                measure = page.evaluate(now)
            assert page.errors == []
        finally:
            browser.close()
    assert opened["measured"] and opened["link"] == OUTSIDE and opened["points"] == 2, opened
    assert closed == {"measured": None, "link": None, "points": 0}, closed
    assert measure in (None, {"measured": None, "link": None, "points": 0}), measure


def test_measure_fit_desktop(site):
    """A desktop: Measure's line pressed near the map's top stays where it is when its profile's card comes (the person
    pressed its points there; the map does not move); pressed near the bottom, where the card then lies, the map moves
    so that the line is in the room above the card (useMeasuredShown; today's page never moves for Measure's line)."""
    from playwright.sync_api import sync_playwright
    points = """([top]) => { const room = F.room(), boxes = T.controls(), r = 30, out = [];
      const ys = top ? [room[1] + 60, room[1] + 140] : [room[3] - 60, room[3] - 120];
      for (const y of ys) for (let x = room[0] + 60; x < room[2] - 60; x += 13) {
        if (boxes.some((c) => x > c.left - r && x < c.right + r && y > c.top - r && y < c.bottom + r)) continue;
        if (out.length && Math.hypot(x - out[0].x, y - out[0].y) < 160) continue;
        out.push({x, y}); break; }
      return out; }"""
    centre = "() => { const c = window.FINDALINE_MAP.getCenter(); return [c.lat, c.lng, window.FINDALINE_MAP.getZoom()]; }"
    found = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            for where in ("top", "bottom"):
                page = _view(browser, site, DESKTOP, script=PROFILE_STUB)
                _state(page, "view.setLevel('spots');")
                page.click(".c-result-top .r-actions button:has-text('Measure')")
                page.wait_for_function("() => window.FINDALINE_VIEW.map.isMeasuring", timeout=WAIT)
                pts = page.evaluate(points, [where == "top"])
                assert len(pts) == 2, pts
                before = page.evaluate(centre)
                for at in pts:
                    page.mouse.click(at["x"], at["y"])
                    page.evaluate("() => T.frames()")
                page.wait_for_selector(".c-col-map > .r-card .fal-profile-chart", timeout=WAIT)
                page.wait_for_function("() => !window.FINDALINE_MAP._animatingZoom", timeout=WAIT)
                page.evaluate("() => T.frames()")
                found[where] = {"moved": page.evaluate(centre) != before, "inRoom": page.evaluate("() => F.inRoom(window.FINDALINE_VIEW.measured)")}
                assert page.errors == []
                page.context.close()
        finally:
            browser.close()
    assert found == {"top": {"moved": False, "inRoom": True}, "bottom": {"moved": True, "inRoom": True}}, found


def test_today_measure_tip_below(site):
    """Today's page (no flag): Measure's tip stands under its button in the catalogue's words (W12; RunActions'
    default `tip`)."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _open(browser, f"{site}#run={BIG}", DESKTOP, flag=False, script=FRAME)
            page.wait_for_function("() => !!window.FINDALINE_RESULT", timeout=WAIT)
            page.click(".c-result-top .r-actions button:has-text('Measure')")
            page.wait_for_selector(".r-act .r-tip", timeout=WAIT)
            got = page.evaluate("""() => { const t = document.querySelector('.r-act .r-tip'), b = t.parentElement.querySelector('button');
                return [t.textContent, t.classList.contains('r-tip-beside'), t.getBoundingClientRect().top >= b.getBoundingClientRect().bottom - 1]; }""")
            assert page.errors == []
        finally:
            browser.close()
    assert got == [WORDS["ui.result.measure_tip"], False, True], got


def test_short_foot_access_key_follows_the_anchors(site):
    """A desktop's short foot (the card open: the user's 4 a) holds the access key's "i" only while an anchor of the
    selected line is in view, as the full legend's three rows (the user's L b; the scope review's 3.2)."""
    from playwright.sync_api import sync_playwright
    key = "() => !!document.querySelector('.v-foot .v-help-button .ac-info, .v-foot .v-help-button button')"
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _view(browser, site, DESKTOP)
            _state(page, "view.setLevel('spots'); view.select(view.inView.best[0]);")
            page.wait_for_selector(".c-col-map > .r-card .fal-profile-chart", timeout=WAIT)
            page.wait_for_function("() => window.FINDALINE_VIEW.map.legend().shapes.ends === true", timeout=WAIT)
            shown = page.evaluate(key)
            _state(page, "const s = view.selected.line; leaflet.setView([s.lat1 + 0.01, s.lon1 + 0.01], leaflet.getZoom(), {animate: false});")
            page.wait_for_function("() => !window.FINDALINE_VIEW.map.legend().shapes.ends", timeout=WAIT)
            page.evaluate("() => T.frames()")
            gone = page.evaluate(key)
            assert page.errors == []
        finally:
            browser.close()
    assert (shown, gone) == (True, False), (shown, gone)


def test_maps_help_desktop(site):
    """A desktop: the map's one "i" at the switch's end (7 b) opens a box under the switch with the texts of the levels
    and of Best (the catalogue's), at Area also why Best is off (W11), Best greyed; Esc closes it and nothing else (the
    selection stays)."""
    from playwright.sync_api import sync_playwright
    texts = "() => [...document.querySelectorAll('.v-about p')].map((p) => p.textContent)"
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _view(browser, site, DESKTOP)
            _state(page, "view.setLevel('spots'); view.select(view.order[0]);")
            place = page.evaluate("() => [F.rect('.v-about-button'), F.rect('.v-best'), F.rect('.v-levels'), document.querySelector('.v-info').getAttribute('aria-label')]")
            info, best, levels, name = place
            assert info[0] >= best[2] and abs((info[1] + info[3]) / 2 - (levels[1] + levels[3]) / 2) <= 2 and name == WORDS["ui.view.map.about"], place
            page.click(".v-info")
            page.wait_for_selector(".v-about", timeout=WAIT)
            lev = f"{WORDS['ui.view.map.help_levels']}. {WORDS['ui.view.map.levels_help']}"
            best_text = f"{WORDS['ui.view.map.help_best']}. {WORDS['ui.view.map.best_help']}."
            assert page.evaluate(texts) == [lev, best_text]
            assert page.evaluate("() => [document.querySelector('.v-info').getAttribute('aria-expanded'), F.rect('.v-about')[1] >= F.rect('.v-levels')[3]]") == ["true", True]
            _state(page, "view.setLevel('area');")
            assert page.evaluate(texts) == [lev, f"{best_text} {WORDS['ui.view.map.best_area']}"]
            assert page.evaluate("() => document.querySelector('.v-best select').disabled") is True
            page.keyboard.press("Escape")
            page.wait_for_selector(".v-about", state="detached", timeout=WAIT)
            assert _state(page)["selected"] is not None
            # its close (the mock-up's ×, "Close"): the box goes, the focus back on the "i"
            page.click(".v-info")
            page.wait_for_selector(".v-about", timeout=WAIT)
            assert page.evaluate("() => document.querySelector('.v-about .v-about-x').getAttribute('aria-label')") == WORDS["ui.view.map.help_close"]
            page.click(".v-about .v-about-x")
            page.wait_for_selector(".v-about", state="detached", timeout=WAIT)
            assert page.evaluate("() => document.activeElement === document.querySelector('.v-info')")
            # Esc with the focus inside the help (on its ×): it closes, the focus back on the "i" (the code review's
            # finding 4, the design review's F7)
            page.click(".v-info")
            page.wait_for_selector(".v-about", timeout=WAIT)
            page.evaluate("() => T.frames()")  # (the help's Esc listener comes with an effect after the paint)
            page.focus(".v-about .v-about-x")
            page.keyboard.press("Escape")
            page.wait_for_selector(".v-about", state="detached", timeout=WAIT)
            assert page.evaluate("() => document.activeElement === document.querySelector('.v-info')")
            assert _state(page)["selected"] is not None
            assert page.errors == []
        finally:
            browser.close()


def test_maps_help_phone(site):
    """A phone: the foot's "i" is the map's (7 b), "About the map": its panel's parts "Auto, Area, Spots, Lines",
    "Best" and "Anchors", one always open (the open part's head pressed keeps it; another's opens that one: the
    mock-up's), opening on "Anchors" (the access key, the button's meaning before); Best's part at Area says why Best
    is off; its × closes it. A run without the mark: two parts, opening on the first (the planner's choice). The
    desktop's "i" is not drawn."""
    from playwright.sync_api import sync_playwright
    parts = """() => [...document.querySelectorAll('.v-about .v-part')].map((b) => [b.dataset.part, b.getAttribute('aria-expanded'),
        b.nextElementSibling?.classList.contains('v-part-text') ? b.nextElementSibling.textContent : null])"""
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _view(browser, site, SMALL_PHONE)
            _state(page, "view.setLevel('spots');")
            assert page.evaluate("() => [!!document.querySelector('.v-about-button'), document.querySelector('.v-help-button .v-info').getAttribute('aria-label')]") == \
                [False, WORDS["ui.view.map.about"]]
            _tap_on(page, ".v-help-button .v-info")
            page.wait_for_selector(".v-over > .v-about", timeout=WAIT)
            got = page.evaluate(parts)
            assert [(k, e) for k, e, _ in got] == [("levels", "false"), ("best", "false"), ("anchors", "true")], got
            assert WORDS["ui.access.help"] in got[2][2], got
            # opened on Anchors (its longest part) it stops under the level switch's row, which it explains (the
            # mock-up's 7 b; the design review's F3)
            under = page.evaluate("() => [F.rect('.v-over > .v-about')[1], F.rect('.v-switch')[3]]")
            assert under[0] >= under[1], under
            _tap_on(page, ".v-part[data-part='levels']")
            got = page.evaluate(parts)
            assert [e for _, e, _ in got] == ["true", "false", "false"] and got[0][2] == WORDS["ui.view.map.levels_help"], got
            _tap_on(page, ".v-part[data-part='levels']")  # the open part's head pressed: it stays open (one always is)
            assert [e for _, e, _ in page.evaluate(parts)] == ["true", "false", "false"]
            _state(page, "view.setLevel('area');")
            _tap_on(page, ".v-part[data-part='best']")
            got = page.evaluate(parts)
            assert [e for _, e, _ in got] == ["false", "true", "false"], got
            assert got[1][2] == f"{WORDS['ui.view.map.best_help']}. {WORDS['ui.view.map.best_area']}", got
            _tap_on(page, ".v-help-button .v-info")
            page.wait_for_selector(".v-about", state="detached", timeout=WAIT)
            # its close (the mock-up's ×): 44 px on a touch screen
            _tap_on(page, ".v-help-button .v-info")
            page.wait_for_selector(".v-over > .v-about", timeout=WAIT)
            assert page.evaluate("() => { const r = document.querySelector('.v-about .v-about-x').getBoundingClientRect(); return [Math.round(r.width), Math.round(r.height)]; }") == [44, 44]
            _tap_on(page, ".v-about .v-about-x")
            page.wait_for_selector(".v-about", state="detached", timeout=WAIT)
            # Esc with the focus on a part: closed, the focus back on the "i"
            _tap_on(page, ".v-help-button .v-info")
            page.wait_for_selector(".v-over > .v-about", timeout=WAIT)
            page.evaluate("() => T.frames()")  # (the help's Esc listener comes with an effect after the paint)
            page.focus(".v-part[data-part='best']")
            page.keyboard.press("Escape")
            page.wait_for_selector(".v-about", state="detached", timeout=WAIT)
            assert page.evaluate("() => document.activeElement === document.querySelector('.v-help-button .v-info')")
            # opened, then the sheet at full (the map not seen, the help not drawn): the help is closed, so a later Esc
            # is the frame's (the code review's finding 5)
            _tap_on(page, ".v-help-button .v-info")
            page.wait_for_selector(".v-over > .v-about", timeout=WAIT)
            page.focus(".u-sheet-handle")
            page.keyboard.press("ArrowUp")
            page.wait_for_function("() => F.snap() === 'half'", timeout=WAIT)
            page.keyboard.press("ArrowUp")
            page.wait_for_function("() => F.snap() === 'full'", timeout=WAIT)
            page.evaluate("() => T.frames()")
            assert page.evaluate("() => document.querySelector('.v-help-button .v-info').getAttribute('aria-expanded')") == "false"
            page.context.close()
            page = _view(browser, site, SMALL_PHONE, run=PLAIN)
            _state(page)
            _tap_on(page, ".v-help-button .v-info")
            page.wait_for_selector(".v-over > .v-about", timeout=WAIT)
            assert [(k, e) for k, e, _ in page.evaluate(parts)] == [("levels", "true"), ("best", "false")]
            assert page.errors == []
        finally:
            browser.close()


@pytest.mark.parametrize("device", [DESKTOP, SMALL_PHONE], ids=["desktop", "phone"])
def test_legend_rows_of_what_is_drawn(site, device):
    """The legend's rows of what the canvas draws besides the spots, as the canvas's legend says (given here: the
    members of step 3c are the canvas's): "Favourite" with the favourite's colour, "Search area" (a phone's "search
    area", W13) with the dashed sign, each other run of Compare by its name in its colour (the bar and the dashes); the
    access mark's three rows only while an anchor of the selected line is in view (`ends`, L b), none without it; a
    phone's legend at Area says "start here" (W6)."""
    from playwright.sync_api import sync_playwright
    phone = device is SMALL_PHONE
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _view(browser, site, device)
            _state(page, "view.setLevel('spots');")
            if phone:
                page.wait_for_selector(".v-legend", timeout=WAIT)
            plain = page.evaluate("() => F.legend()")
            assert not any(k.startswith("access-") for k, _ in plain), plain
            page.evaluate("""() => F.legendWith({shapes: {fav: true, area: true, ends: true}, runs: [{id: 'r2', name: 'Another run', color: '#1f77b4'}]})""")
            page.evaluate("() => T.frames()")
            rows = page.evaluate("() => F.legend()")
            kinds = [k for k, _ in rows]
            assert kinds[-6:] == ["fav", "area", "run", "access-2", "access-1", "access-0"], rows
            area = WORDS["ui.view.map.lg_area_short" if phone else "ui.view.map.lg_area"]
            assert rows[-6][1] == WORDS["ui.result.legend_favourite"] and rows[-5][1] == area and rows[-4][1] == "Another run", rows
            colours = page.evaluate("""() => { const run = document.querySelector('.v-legend [data-kind="run"]');
                return [getComputedStyle(run.querySelector('.r-sw')).backgroundColor, getComputedStyle(run.querySelector('.v-dash path')).stroke]; }""")
            assert colours == ["rgb(31, 119, 180)"] * 2, colours
            if phone:  # the access rows on a line of their own
                assert page.evaluate("() => [...document.querySelectorAll('.v-lg-line')].pop().querySelectorAll('[data-kind^=\"access-\"]').length") == 3
            page.evaluate("() => F.legendWith({shapes: {ends: undefined}})")
            page.evaluate("() => T.frames()")
            assert not any(k.startswith("access-") for k, _ in page.evaluate("() => F.legend()"))
            if phone:
                _state(page, "view.setLevel('area');")
                page.wait_for_selector(".v-legend [data-kind='P']", timeout=WAIT)
                assert page.evaluate("() => document.querySelector('.v-legend [data-kind=\"P\"]').textContent.trim()") == "P1" + WORDS["ui.view.map.lg_pick_short"]
            assert page.errors == []
        finally:
            browser.close()


@pytest.mark.parametrize("device", [DESKTOP, SMALL_PHONE], ids=["desktop", "phone"])
def test_legend_rows_from_the_canvas(site, device):
    """The legend's rows as the canvas really draws (B1's legend(), no stand-in): the whole search area in view with
    Compare's other run beside it (this run's lines moved east, as test_view_map_3c's) and the selected line a
    favourite: "Favourite" in the map's own gold (style.ts COLORS.favourite, not the theme's --fav), "Search area" with
    the dashed sign on the map's paper in the map's ink (unlike the dashed ring of "Here"), the other run by its name in
    its colour (the bar and the dashes), then the access rows exactly while the canvas says an anchor is in view."""
    from playwright.sync_api import sync_playwright
    phone = device is SMALL_PHONE
    info = {"id": "2026-11-20_120000_Other_00000000000000b1", "name": "Other run", "created": "2026-11-20T12:00:00", "has_lines": True}
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _view(browser, site, device)
            _state(page)
            page.evaluate("""async ([info]) => { const {view, map} = window.FINDALINE_VIEW, m = view.model, c = m.data.columns, NC = c.lon1.constructor;
                const b = map.areaBounds(), d = (b.getEast() - b.getWest()) * 0.6;
                const shift = (col) => new NC(Float64Array.from({length: c.length}, (_, i) => col.at(i) + d), 0);
                const area = JSON.parse(JSON.stringify(m.data.area)), move = (q) => { if (typeof q[0] === 'number') q[0] += d; else q.forEach(move); };
                const walk = (o) => { if (!o) return; if (o.coordinates) move(o.coordinates); else if (o.geometry) walk(o.geometry); else if (o.features) o.features.forEach((f) => walk(f.geometry)); else if (o.geometries) o.geometries.forEach(walk); };
                walk(area);
                window.FINDALINE_MAP.fitBounds([[b.getSouth(), b.getWest()], [b.getNorth(), b.getEast() + d]], {animate: false});
                m.addRun(info, {...m.data, area, columns: {...c, lon1: shift(c.lon1), lon2: shift(c.lon2)}}); }""", [info])
            _state(page, "view.setLevel('spots');")
            page.evaluate("""async () => { const {view} = window.FINDALINE_VIEW, m = view.model, spot = view.inView.best[0];
                await m.toggleFavourite(m.lineAt(view.shownOf(spot))); view.select(spot); m.closeProfile(); }""")
            page.evaluate("() => T.frames()")
            if page.query_selector(".v-fold[aria-expanded='false']"):
                (_tap_on if phone else lambda pg, sel: pg.click(sel))(page, ".v-fold")
            page.wait_for_selector(".v-legend [data-kind='fav']", timeout=WAIT)
            page.evaluate("() => T.frames()")
            got = page.evaluate("""() => { const {map} = window.FINDALINE_VIEW, l = map.legend(), q = (s) => document.querySelector('.v-legend ' + s);
                const rgb = (c) => { const e = document.createElement('i'); e.style.color = c; document.body.append(e); const v = getComputedStyle(e).color; e.remove(); return v; };
                return {shapes: l.shapes, runs: l.runs, kinds: F.legend().map(([k]) => k), words: F.legend().map(([, w]) => w),
                        fav: [getComputedStyle(q('[data-kind="fav"] .v-fav')).backgroundColor, getComputedStyle(q('[data-kind="fav"] .v-fav i')).backgroundColor],
                        // "Anchors" and its three marks on one row (their middles within 2 px)
                        group: (() => { const g = [...document.querySelectorAll('.v-legend .v-lg-group > *')].map((e) => { const r = e.getBoundingClientRect(); return (r.top + r.bottom) / 2; });
                                        return g.length ? [g.length, Math.max(...g) - Math.min(...g) <= 2] : null; })(),
                        area: [getComputedStyle(q('[data-kind="area"] .v-dash rect')).fill, getComputedStyle(q('[data-kind="area"] .v-dash path')).stroke,
                               getComputedStyle(q('[data-kind="area"] .v-dash path')).strokeDasharray],
                        run: [getComputedStyle(q('[data-kind="run"] .r-sw')).backgroundColor, getComputedStyle(q('[data-kind="run"] .v-dash path')).stroke,
                              l.runs.length ? rgb(l.runs[0].color) : null]}; }""")
            assert page.errors == [], page.errors
        finally:
            browser.close()
    assert got["shapes"].get("fav") and got["shapes"].get("area") and [r["name"] for r in got["runs"]] == ["Other run"], got
    # the selected line's anchors are in view in this state (the canvas's `ends`): the access rows come last
    assert got["shapes"].get("ends") is True, got["shapes"]
    k = got["kinds"].index("fav")
    assert got["kinds"][k:] == ["fav", "area", "run", "access-2", "access-1", "access-0"], got["kinds"]
    area = WORDS["ui.view.map.lg_area_short" if phone else "ui.view.map.lg_area"]
    assert got["words"][k:k + 3] == [WORDS["ui.result.legend_favourite"], area, "Other run"], got["words"]
    # the favourite's sign: the line (style.ts COLORS.clean) inside its gold band (COLORS.favourite #FFD400): F5
    assert got["fav"] == ["rgb(255, 212, 0)", "rgb(255, 16, 240)"], got["fav"]
    if not phone:  # "Anchors" with its three marks on one row: F4
        assert got["group"] == [4, True], got["group"]
    assert got["area"] == ["rgb(255, 255, 255)", "rgb(27, 37, 48)", "4px, 3px"], got["area"]  # the paper, the ink #1b2530
    assert got["run"][0] == got["run"][1] == got["run"][2], got["run"]


def test_legend_access_rows_follow_the_selection(site):
    """The access mark's rows in the legend of a marked run (L b), as the canvas draws: none with nothing selected; a
    line selected with its anchors in view: the three rows; the map moved so that both anchors are out of view: none
    again (the canvas's `ends`)."""
    from playwright.sync_api import sync_playwright
    access = "() => F.legend().filter(([k]) => k.startsWith('access-')).map(([k]) => k)"
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _view(browser, site, DESKTOP)
            _state(page, "view.setLevel('spots'); view.model.closeProfile();")
            assert page.evaluate(access) == []
            _state(page, "view.select(view.inView.best[0]); view.model.closeProfile();")
            page.wait_for_selector(".v-legend [data-kind='access-2']", timeout=WAIT)
            assert page.evaluate(access) == ["access-2", "access-1", "access-0"]
            _state(page, "const s = view.selected.line; leaflet.setView([s.lat1 + 0.01, s.lon1 + 0.01], leaflet.getZoom(), {animate: false});")
            page.wait_for_function(f"() => ({access})().length === 0", timeout=WAIT)
            assert page.errors == []
        finally:
            browser.close()


def test_status_texts(site):
    """The status line: a level held says "Kept while you zoom." (W1); while no line passes the filters, at any
    level, "No line passes the filters." (W14), the map drawing no line."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _view(browser, site, DESKTOP)
            held = _state(page, "view.setLevel('spots');")
            assert WORDS["ui.view.map.held"] in held["bar"] and held["status"].startswith("Spots"), held["bar"]
            for level in ("spots", "area", "lines"):
                none = _state(page, f"const m = view.model; m.setFilters({{...m.filters, lenMin: 100000}}); view.setLevel('{level}');")
                assert none["status"] == WORDS["ui.view.map.status_none_pass"] and none["strokes"] == 0 and none["numbers"] == [], (level, none["status"])
            assert page.errors == []
        finally:
            browser.close()


@pytest.mark.parametrize("device", [DESKTOP, PHONE], ids=["desktop", "phone"])
@pytest.mark.parametrize("flag", [True, False], ids=["view", "today"])
def test_boxes_help_size(site, device, flag):
    """The shore's and the coarser terrain's help (S c, on both pages): 24 px with its 16 px icon on every screen;
    on a touch screen an invisible 44 px target (its ::after: 44 x 44, away from the shore box's fold button, within
    the coarser box's padding). The boxes are the tests' stand-ins with the page's classes (the clip has neither)."""
    from playwright.sync_api import sync_playwright
    shore = """() => { const holder = document.createElement("div"); holder.className = "leaflet-control u-shore-ctl";
      const box = holder.appendChild(document.createElement("div")); box.className = "u-shore";
      const head = box.appendChild(document.createElement("div")); head.className = "u-shore-head";
      head.appendChild(document.createElement("b")).textContent = "Uncertain shore in view";
      const help = head.appendChild(document.createElement("button")); help.type = "button"; help.className = "u-ib u-plain u-shore-help";
      help.innerHTML = '<svg class="u-ic" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9"/></svg>';
      (document.querySelector(".v-map .leaflet-top.leaflet-left") || document.querySelector(".leaflet-top.leaflet-left")).appendChild(holder); }"""
    size = """() => [...document.querySelectorAll('.u-shore-help')].map((b) => { const r = b.getBoundingClientRect(), i = b.querySelector('.u-ic').getBoundingClientRect(),
        a = getComputedStyle(b, '::after'), px = (v) => parseFloat(v) || 0;
        return [Math.round(r.width), Math.round(r.height), Math.round(i.width), a.content === 'none' ? null :
                [Math.round(r.width - px(a.left) - px(a.right)), Math.round(r.height - px(a.top) - px(a.bottom))]]; })"""
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _open(browser, f"{site}#run={BIG}", device, flag=flag, script=FRAME)
            if not flag:
                page.wait_for_function("() => !!window.FINDALINE_RESULT", timeout=WAIT)
                page.wait_for_selector(".leaflet-top.leaflet-left", timeout=WAIT)
            page.evaluate(shore)
            page.evaluate(COARSE.replace(".v-map .leaflet-top.leaflet-left", ".leaflet-top.leaflet-left"))
            page.evaluate("() => new Promise((ok) => requestAnimationFrame(() => requestAnimationFrame(ok)))")
            got = page.evaluate(size)
            touch = device is PHONE
            assert got == [[24, 24, 16, [44, 44] if touch else None]] * 2, got
            assert page.errors == []
        finally:
            browser.close()


def test_shore_title_stays_over_its_text(site):
    """A phone's opened shore box in the view scrolls under its sticky title: no padding above the title (the box's
    own is the title's), so a scrolled text never shows above it (A3's note)."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _view(browser, site, SMALL_PHONE)
            got = page.evaluate("""() => { const holder = document.createElement("div"); holder.className = "leaflet-control u-shore-ctl";
                const box = holder.appendChild(document.createElement("div")); box.className = "u-shore";
                const head = box.appendChild(document.createElement("div")); head.className = "u-shore-head";
                head.appendChild(document.createElement("b")).textContent = "Uncertain shore in view";
                document.querySelector(".v-map .leaflet-top.leaflet-left").appendChild(holder);
                const b = getComputedStyle(box), h = getComputedStyle(head);
                return [b.paddingTop, h.position, h.paddingTop, h.paddingLeft, b.paddingLeft]; }""")
            assert got == ["0px", "sticky", "8px", "12px", "12px"], got
            assert page.errors == []
        finally:
            browser.close()


def test_sheet_check_leaves_a_left_frame_alone(site):
    """A1's gap (its second code review): the result page left while the sheet's check waits for the sheet to rest (its
    move slowed to 6 s): after the phone's frame left the page, the check reads nothing of the old map (it ran once more
    before the frame's cleanup and read the selected line's ends there)."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _view(browser, site, PHONE)
            page.wait_for_function("() => F.snap() === 'peek' && F.rest()", timeout=WAIT)
            _state(page, "view.setLevel('spots'); view.select(view.inView.best[0] ?? view.order[0]);")
            page.evaluate("""() => { const m = window.FINDALINE_MAP, root = document.querySelector('.c-result-phone');
                window.LEFT = {gone: false, reads: 0};
                const own = m.latLngToContainerPoint; m.latLngToContainerPoint = function (...a) { if (LEFT.gone) LEFT.reads++; return own.apply(this, a); };
                new MutationObserver(() => { if (!root.isConnected) LEFT.gone = true; }).observe(document.body, {childList: true, subtree: true});
                document.querySelector('.u-sheet').style.transition = 'height 6s linear';
                document.querySelector('.u-sheet-handle').click(); }""")
            page.evaluate("() => T.frames()")  # the check waits for the sheet to rest, frame by frame
            page.evaluate("() => { location.hash = '#home'; }")
            page.wait_for_function("() => LEFT.gone && !document.querySelector('.v-map')", timeout=WAIT)
            # the frames after leaving: the check's next frame would read the old map then (one wait of frames, not
            # of a time: the cleanup comes after the paint)
            page.evaluate("() => new Promise((ok) => { let n = 0; const f = () => (++n > 10 ? ok() : requestAnimationFrame(f)); f(); })")
            assert page.evaluate("() => LEFT.reads") == 0
            assert page.errors == []
        finally:
            browser.close()


def test_note_after_crossing_the_phone_width(site):
    """A1's gap (its second code review): a link to a line outside the run opened on a desktop, the window narrowed to
    a phone's while the line is measured, the measurement then refused: the note shows, and the phone's sheet rises from
    its low start to half to show it."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _view(browser, site, {**DESKTOP}, line=OUTSIDE, script=PROFILE_HELD)
            page.wait_for_function("() => typeof window.FAIL === 'function' && !!window.FINDALINE_VIEW.view.model.measuredLink", timeout=WAIT)
            page.set_viewport_size({"width": 390, "height": 844})
            page.wait_for_function("() => !!document.querySelector('.c-result-phone') && F.snap() === 'peek'", timeout=WAIT)
            page.evaluate("() => T.frames()")
            page.evaluate("() => window.FAIL()")
            page.wait_for_function("() => !!window.FINDALINE_VIEW.view.model.note && F.snap() === 'half'", timeout=WAIT)
            assert page.evaluate("() => window.FINDALINE_VIEW.view.model.note.text").startswith("The line of the link could not be measured")
            assert page.errors == []
        finally:
            browser.close()


def test_profile_text_and_touch_sizes(site):
    """The profile's leftovers (the user's "12 a"): the chart's text 12 px (the axes, the labels), its labels apart by
    2 px or more (the glyphs' boxes); on a touch screen the profile's controls 44 px high (the 1:1 scale, the rigging's
    fields, the layers' rows) and its bar's buttons 44 x 44: in the view's measured dock (a link's line outside the run,
    first in the phone's sheet) and in today's page's dock (the same component)."""
    from playwright.sync_api import sync_playwright
    chart = """() => { const svg = document.querySelector('.fal-profile-chart svg'), texts = [...svg.querySelectorAll('text')];
      const labels = [...svg.querySelectorAll('text.fal-label')].map((t) => t.getBoundingClientRect());
      let apart = Infinity;
      labels.forEach((a, k) => labels.slice(k + 1).forEach((b) => { const dx = Math.max(b.left - a.right, a.left - b.right), dy = Math.max(b.top - a.bottom, a.top - b.bottom);
        apart = Math.min(apart, Math.max(dx, dy)); }));
      // the glyphs' cells above and below the baseline (Profile.tsx LABEL_BOXES' ascent and descent stand for them)
      const top = svg.getBoundingClientRect().top, cells = [...svg.querySelectorAll('text.fal-label')].map((t) => { const r = t.getBoundingClientRect(), y = +t.getAttribute('y');
        return [Math.round((y - (r.top - top)) * 10) / 10, Math.round((r.bottom - top - y) * 10) / 10]; });
      return {sizes: [...new Set(texts.map((t) => getComputedStyle(t).fontSize))], labels: labels.length, apart, cells}; }"""
    controls = """() => { document.querySelector('.r-dock-bar .u-chip')?.click(); return new Promise((ok) => requestAnimationFrame(() => requestAnimationFrame(() => ok({
      controls: [...document.querySelectorAll('.r-profile .fal-scale, .r-profile .fal-profile-head button, .r-profile .fal-profile-controls input[type=number], .r-profile .fal-layers label')]
        .filter((e) => e.getBoundingClientRect().height).map((e) => Math.round(e.getBoundingClientRect().height)),
      bar: [...document.querySelectorAll('.r-dock-bar .r-note-x')].map((e) => [Math.round(e.getBoundingClientRect().width), Math.round(e.getBoundingClientRect().height)]),
      head: !!document.querySelector('.r-profile .fal-profile-head'),
      close: [...document.querySelectorAll('.r-profile .fal-close')].map((e) => [Math.round(e.getBoundingClientRect().width), Math.round(e.getBoundingClientRect().height)])}))));
      }"""
    tablet = {**PHONE, "viewport": {"width": 1180, "height": 820}, "device_scale_factor": 2}  # the columns with a finger
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _view(browser, site, DESKTOP)
            _state(page, "view.setLevel('spots'); view.select(view.order[0]);")
            page.wait_for_selector(".r-card .fal-profile-chart svg text.fal-label", timeout=WAIT)
            page.evaluate("() => T.frames()")
            got = page.evaluate(chart)
            print("the chart's labels: glyph cells above and below the baseline", got["cells"], "nearest apart", got["apart"])
            assert got["sizes"] == ["12px"] and got["labels"] >= 2 and got["apart"] >= 2, got
            page.context.close()
            # a tablet's card (the columns with a finger): its bar's fold and close and the profile's controls
            page = _view(browser, site, tablet)
            _state(page, "view.setLevel('spots'); view.select(view.order[0]);")
            page.wait_for_selector(".r-card .fal-profile-chart", timeout=WAIT)
            got = page.evaluate(controls)
            assert got["controls"] and min(got["controls"]) >= 44 and got["bar"] == [[44, 44], [44, 44]], got
            assert page.errors == []
            page.context.close()
            # the view's phone: the measured profile's dock (the frame's own: a selected line's dock is the details')
            page = _view(browser, site, PHONE, line=OUTSIDE, script=PROFILE_STUB)
            page.wait_for_selector(".u-sheet-body > .r-dock:first-child .fal-profile-chart", timeout=WAIT)
            got = page.evaluate(controls)
            # compact (the mock-up's 4 d): no head row, the close in the bar
            assert got["controls"] and min(got["controls"]) >= 44 and got["bar"] == [[44, 44]] and got["head"] is False, got
            assert page.errors == []
            page.context.close()
            # today's page on a phone: the selected line's dock in the sheet
            page = _open(browser, f"{site}#run={BIG}", PHONE, flag=False, script=FRAME)
            page.wait_for_function("() => !!window.FINDALINE_RESULT", timeout=WAIT)
            page.evaluate("() => { const m = window.FINDALINE_RESULT.model; m.select(m.rows[0].group); }")
            page.wait_for_selector(".r-dock .fal-profile-chart", timeout=WAIT)
            got = page.evaluate(controls)
            # today's dock as it was: the profile's head row with its close (44 x 44 on touch: the design review's F2),
            # none in the bar
            assert got["controls"] and min(got["controls"]) >= 44 and got["bar"] == [] and got["head"] is True, got
            assert got["close"] == [[44, 44]], got
            assert page.errors == []
        finally:
            browser.close()


@pytest.mark.parametrize("device", [SMALL_PHONE, PIXEL], ids=["390", "412"])
def test_phone_dock_compact(site, device):
    """A phone's docks in the view are compact (ProfileDock `compact`: B2's design review F1 and F2, the mock-up's 4 d
    and polish 10 and 13): the selected line's dock in the details at half has no head row (the full title for screen
    readers only), its bar holds the title, "Rigging and layers" and the close ("Close the profile", 44 px) in the
    column of the selection's close, the words on reading the chart stand under it, and the chart's top is on the
    screen at half (it was below the fold); the measured line's dock likewise, its facts on a row under the bar."""
    from playwright.sync_api import sync_playwright
    read = """() => { const d = document.querySelector('.u-sheet-body .r-dock'), r = (e) => e && e.getBoundingClientRect();
      const x = d.querySelector('.r-dock-bar [aria-label="Close the profile"]'), sel = document.querySelector('.vl-dclose');
      return {head: !!d.querySelector('.fal-profile-head'), sr: d.querySelector('.fal-profile-title')?.textContent ?? '',
              bar: [...d.querySelector('.r-dock-bar').children].filter((e) => r(e).width && !e.classList.contains('u-grow')).map((e) => e.tagName.toLowerCase() + '.' + [...e.classList].join('.')),
              close: x && [Math.round(r(x).right), Math.round(r(x).width), Math.round(r(x).height)], selRight: sel && Math.round(r(sel).right),
              under: d.lastElementChild.classList.contains('r-hint-under') && r(d.querySelector('.r-hint-under')).top >= r(d.querySelector('.fal-profile-chart')).bottom,
              // the need row ("no A-frame needed" ...) under the chart too, where the line has one (the design review's F1)
              need: d.querySelector('.fal-need') ? r(d.querySelector('.fal-need')).top >= r(d.querySelector('.fal-profile-chart')).bottom : null,
              facts: d.querySelector('.r-facts')?.textContent ?? null, chartTop: Math.round(r(d.querySelector('.fal-profile-chart')).top), height: innerHeight}; }"""
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _view(browser, site, device)
            _state(page, "view.setLevel('spots'); view.select(view.order[0]);")
            if page.evaluate("() => F.snap()") == "peek":
                page.focus(".u-sheet-handle")
                page.keyboard.press("ArrowUp")
            page.wait_for_function("() => F.snap() === 'half' && F.rest()", timeout=WAIT)
            page.wait_for_selector(".u-sheet-body .vl-details .r-dock .fal-profile-chart", timeout=WAIT)
            line = page.evaluate(read)
            page.context.close()
            page = _view(browser, site, device, line=OUTSIDE, script=PROFILE_STUB)
            page.wait_for_function("() => !!window.FINDALINE_VIEW.measured && F.snap() === 'half' && F.rest()", timeout=WAIT)
            page.wait_for_selector(".u-sheet-body > .r-dock:first-child .fal-profile-chart", timeout=WAIT)
            measured = page.evaluate(read)
            assert page.errors == []
        finally:
            browser.close()
    print("chart tops at half", device["viewport"], "line", line["chartTop"], "measured", measured["chartTop"])
    assert line["need"] is True, line  # BIG's first line has a need row
    for got in (line, measured):
        assert got["head"] is False and got["sr"].strip() and got["under"] is True and got["need"] in (True, None), got
        assert got["close"] and got["close"][1:] == [44, 44] and got["bar"][-1] == "button.r-note-x", got
        assert got["bar"][0] == "b." and "button.u-chip" in got["bar"] and "span.u-small.r-hint" not in got["bar"], got
        assert got["chartTop"] < got["height"], got  # the chart's top on the screen at half
    assert line["close"][0] == line["selRight"] and line["facts"] is None, line  # polish 10; the tiles hold the facts
    assert measured["facts"], measured
