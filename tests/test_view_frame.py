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
from test_shell_c_view_map import (COARSE, DESKTOP, HELPERS, PHONE, SMALL_PHONE, WAIT, WORDS, _open, _state,  # noqa: E402,F401
                                   _tap, _tap_on, view_clip)
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
            if device is DESKTOP:  # (Measure where the canvas can measure and the page can ask profiles)
                got = F_actions(page, ".c-result-top")
                assert "Compare" in got and set(got) <= {"Measure", "Compare"}, got
            else:
                got = page.evaluate("() => [...document.querySelectorAll('.c-pill .r-actions button')].map((b) => b.getAttribute('aria-label'))")
                assert set(got) <= {"Measure"}, got
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
                        fav: getComputedStyle(q('[data-kind="fav"] .r-sw')).backgroundColor,
                        area: [getComputedStyle(q('[data-kind="area"] .v-dash rect')).fill, getComputedStyle(q('[data-kind="area"] .v-dash path')).stroke,
                               getComputedStyle(q('[data-kind="area"] .v-dash path')).strokeDasharray],
                        run: [getComputedStyle(q('[data-kind="run"] .r-sw')).backgroundColor, getComputedStyle(q('[data-kind="run"] .v-dash path')).stroke,
                              l.runs.length ? rgb(l.runs[0].color) : null]}; }""")
            assert page.errors == [], page.errors
        finally:
            browser.close()
    assert got["shapes"].get("fav") and got["shapes"].get("area") and [r["name"] for r in got["runs"]] == ["Other run"], got
    access = ["access-2", "access-1", "access-0"] if got["shapes"].get("ends") else []
    k = got["kinds"].index("fav")
    assert got["kinds"][k:] == ["fav", "area", "run"] + access, got["kinds"]
    area = WORDS["ui.view.map.lg_area_short" if phone else "ui.view.map.lg_area"]
    assert got["words"][k:k + 3] == [WORDS["ui.result.legend_favourite"], area, "Other run"], got["words"]
    assert got["fav"] == "rgb(255, 212, 0)", got["fav"]  # #FFD400
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
      head: !!document.querySelector('.r-profile .fal-profile-head')}))));
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
            # today's dock as it was: the profile's head row with its close, none in the bar
            assert got["controls"] and min(got["controls"]) >= 44 and got["bar"] == [] and got["head"] is True, got
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
    for got in (line, measured):
        assert got["head"] is False and got["sr"].strip() and got["under"] is True, got
        assert got["close"] and got["close"][1:] == [44, 44] and got["bar"][-1] == "button.r-note-x", got
        assert got["bar"][0] == "b." and "button.u-chip" in got["bar"] and "span.u-small.r-hint" not in got["bar"], got
        assert got["chartTop"] < got["height"], got  # the chart's top on the screen at half
    assert line["close"][0] == line["selRight"] and line["facts"] is None, line  # polish 10; the tiles hold the facts
    assert measured["facts"], measured
