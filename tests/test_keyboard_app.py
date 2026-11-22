"""The keyboard, the focus rings and touch tablets on the app's free screens (step 3d, group G1; docs/DESIGN.md rows
81 to 83), in Playwright's Edge on the real local server (the app's page with test_shell_c's stubs) and the coverage
page:

- every focus ring a Tab press reaches lies whole inside its scroll boxes and the window and clear of the phones'
  bottom bar (the browser scrolls a focused control in with room for its ring: ui.css `scroll-margin`; the credits'
  links and the bottom bar's items draw their ring inside);
- with forced colours (Windows' contrast themes, which draw no shadow) every stop shows an outline;
- "Coverage map"'s ring in the dark theme holds 3:1 on every side;
- the radio groups (the kit's Segmented, the goal cards, the coverage page's scale) are one Tab stop each and the
  arrows move the focus and choose (WAI-ARIA's radio group; ui/radios.ts);
- a focused segment's ring lies above the selected segment beside it;
- the coverage's outlines on the place map are no Tab stops (Chromium made each SVG shape with Leaflet's focus
  listener one: 83 before the map's controls) and keep their tooltip;
- a touch tablet (the desktop's arrangement with a finger): the coverage box's 32 px button takes a tap anywhere in
  its invisible 44 px target;
- the return dialog's actions stay inside it on a 390 px and a 360 px phone ("Stay in Advanced" was cut).

Headless Edge through Playwright: run from PowerShell (headless Edge prints nothing from Git Bash). Every wait is an
event with a deadline; a finger's taps keep test_shell_c_view_map's spacing (_tap)."""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_shell_c_view_map import _tap  # noqa: E402
from test_web import EDGE, WAIT, _playwright, _server  # noqa: E402

pytestmark = pytest.mark.skipif(not os.path.exists(EDGE) or not _playwright(),
                                reason="needs Microsoft Edge and Playwright (group ui)")

DESKTOP = {"viewport": {"width": 1400, "height": 900}}
PHONE_KEYS = {"viewport": {"width": 390, "height": 664}}  # a phone's frame with a keyboard (the bottom bar)
PHONE_LOW = {"viewport": {"width": 390, "height": 320}}  # the same, low: Home longer than the screen
TOUCH = {"device_scale_factor": 3, "is_mobile": True, "has_touch": True}
TABLET = {"has_touch": True, "is_mobile": False}  # a touch tablet: a coarse pointer, the desktop's arrangement
# The intros put away (ui/Intro.tsx) and the coverage layer as asked (coverageLayer.ts STORAGE_KEY)
SEEN = ("try { localStorage.setItem('findaline.intro.search', 'seen'); localStorage.setItem('findaline.intro.result', 'seen');"
        " localStorage.setItem('findaline.layer.coverage', %s); } catch (e) {}")
POINT = "() => window.FINDALINE_PLACE.map.fire('click', {latlng: {lat: 50.1559508, lng: 19.7562722}})"
FRAMES = "() => new Promise((done) => requestAnimationFrame(() => requestAnimationFrame(() => done(true))))"
# A temporary element at the start of <body> holds the focus, so the first Tab goes to the page's first control
START = """() => { document.activeElement?.blur?.(); const s = document.createElement('span'); s.id = 'kb-start'; s.tabIndex = -1;
  document.body.prepend(s); s.focus(); window.KB = window.KB || {ids: new WeakMap(), n: 0}; }"""
# The focused element: an id of its own, its name, whether it is the place map itself (its ring waits for line volume's
# round 6: docs/known-bugs.md) or a coverage outline; its ring's box (the box grown by the ring's outer extent: the
# widest outset shadow without blur or offset, or the outline; an inset ring: the box), the part of the page that shows
# it (the window and every clipping ancestor's inner box) and the phones' bottom bar over it
RING = r"""() => {
  const e = document.activeElement;
  if (!e || e === document.body || e.id === 'kb-start') return null;
  if (!KB.ids.has(e)) KB.ids.set(e, ++KB.n);
  const cs = getComputedStyle(e), r = e.getBoundingClientRect();
  let far = 0, ring = false;
  for (const part of cs.boxShadow === 'none' ? [] : cs.boxShadow.split(/,(?![^(]*\))/)) {
    const n = (part.replace(/rgba?\([^)]*\)/g, '').match(/-?[\d.]+px/g) || []).map(parseFloat);
    if (n.length < 4 || n[0] || n[1] || n[2]) continue;
    ring = true;
    if (!/inset/.test(part)) far = Math.max(far, n[3]);
  }
  if (cs.outlineStyle !== 'none' && parseFloat(cs.outlineWidth) > 0) {
    ring = true; far = Math.max(far, parseFloat(cs.outlineOffset) + parseFloat(cs.outlineWidth)); }
  let l = 0, t = 0, rr = innerWidth, b = innerHeight, fixed = cs.position === 'fixed';
  for (let a = e.parentElement; a && !fixed; a = a.parentElement) {
    const s = getComputedStyle(a);
    if (s.overflowX !== 'visible' || s.overflowY !== 'visible') { const ar = a.getBoundingClientRect();
      l = Math.max(l, ar.left + a.clientLeft); t = Math.max(t, ar.top + a.clientTop);
      rr = Math.min(rr, ar.left + a.clientLeft + a.clientWidth); b = Math.min(b, ar.top + a.clientTop + a.clientHeight); }
    if (s.position === 'fixed' || a.matches(':modal, :popover-open')) break;
  }
  const box = [r.left - far, r.top - far, r.right + far, r.bottom + far];
  const nav = document.querySelector('.u-bnav');
  let under = 0;
  if (nav && !nav.contains(e)) { const n = nav.getBoundingClientRect(); under = Math.max(0, Math.min(box[3], n.bottom) - Math.max(box[1], n.top)); }
  return {id: KB.ids.get(e), tag: e.tagName.toLowerCase(), cls: String(e.className.baseVal ?? e.className),
          name: (e.getAttribute('aria-label') || e.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 40),
          map: e.classList.contains('c-placemap'), outline: e.classList.contains('n-coverage-area'),
          ring, box, vis: [l, t, rr, b], under, tabindex: e.getAttribute('tabindex'),
          forced: matchMedia('(forced-colors: active)').matches,
          ol: [cs.outlineStyle, parseFloat(cs.outlineWidth)], clip: [r.left - 6, r.top - 6, r.width + 12, r.height + 12]};
}"""


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    """The app's page with test_shell_c's stubs (no event stream; estimates answered) and the coverage page on a real
    server over an empty data folder, and Playwright's Edge: (playwright, browser, the server's address, the page's
    path)."""
    from playwright.sync_api import sync_playwright
    from test_shell_c import stub_page
    data = tmp_path_factory.mktemp("keyboard")
    path = stub_page(data, "keyboard")
    with _server(data) as port, sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            yield p, browser, f"http://127.0.0.1:{port}", path
        finally:
            browser.close()


def _open(site, where: str, context: dict, coverage: bool = False, **extra):
    """A fresh page: "search" (#new, the centre set at the clip's place), "more" (#new's Advanced with More settings
    and its topic Anchors open), "home" (#), "coverage" (the coverage page)."""
    p, browser, base, path = site
    ctx = browser.new_context(reduced_motion="reduce", **context, **extra)
    ctx.add_init_script(SEEN % ("'1'" if coverage else "'0'"))
    page = ctx.new_page()
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)[:300]))
    if where == "coverage":
        page.goto(f"{base}/coverage?lang=en")
        page.wait_for_selector(".cov-list", timeout=WAIT)
        return page
    page.goto(f"{base}/{path}?ui=c" + ("" if where == "home" else "#new"))
    if where == "home":
        page.wait_for_selector(".c-home, .c-main", timeout=WAIT)
        return page
    page.wait_for_function("() => !!window.FINDALINE_PLACE && !!document.querySelector('.s-panel')", timeout=WAIT)
    page.evaluate(POINT)
    if where == "more":
        page.click(".s-tabs [data-tab=advanced]")
        page.click(".s-more-head")
        page.click(".s-topic:nth-of-type(2) > summary")
    return page


def _tab(page):
    """One Tab press, then two frames: the focus's scroll (at once: reduced motion) and its style are in place."""
    page.keyboard.press("Tab")
    page.evaluate("() => document.getElementById('kb-start')?.remove()")
    page.evaluate(FRAMES)


def _walk(page, limit: int = 220) -> list:
    """The stops of real Tab presses from the page's start until the focus comes back to a stop already seen."""
    page.mouse.move(1, 1)
    page.evaluate(START)
    stops, seen = [], set()
    for _ in range(limit):
        _tab(page)
        stop = page.evaluate(RING)
        if stop is None:
            continue
        if stop["id"] in seen:
            break
        seen.add(stop["id"])
        stops.append(stop)
    return stops


def _cut(stop: dict) -> dict:
    """The sides of a stop's ring outside what shows it, by more than half a pixel, and the bottom bar over it."""
    box, vis = stop["box"], stop["vis"]
    sides = {s: round(d, 1) for s, d in (("left", vis[0] - box[0]), ("top", vis[1] - box[1]), ("right", box[2] - vis[2]),
                                          ("bottom", box[3] - vis[3])) if d > 0.5}
    if stop["under"] > 0.5:
        sides["under the bottom bar"] = round(stop["under"], 1)
    return sides


@pytest.mark.parametrize("where, context", [("search", DESKTOP), ("more", DESKTOP), ("coverage", DESKTOP),
                                            ("search", PHONE_KEYS), ("home", PHONE_KEYS), ("home", PHONE_LOW)],
                         ids=["search", "more-settings", "coverage", "search-phone", "home-phone", "home-phone-low"])
def test_rings_whole_after_the_focus_scroll(site, where, context):
    """Row 81: every Tab stop's ring lies inside its scroll boxes and the window, and clear of the phones' bottom bar
    (before: the form's goal cards, fields and "?" at the column's foot 3.7 to 4.5 px cut, the map's credits' links
    2.4 px at the map's foot, the coverage page's list rows and footer links 3 to 4 px at the window's foot, the
    bottom bar's items 4 px at the screen's edges; a low phone's Home, longer than its screen, scrolled a focused
    control under the bottom bar). The place map's own ring waits for line volume's round 6 (docs/known-bugs.md); a
    control with no ring of its own (the range, whose thumb has it) is not measured."""
    page = _open(site, where, context)
    stops = _walk(page)
    assert len(stops) > (4 if where == "home" else 8), stops  # the case: a page with its controls
    if where in ("search", "more"):
        assert any(s["name"] == "OpenStreetMap" for s in stops), stops  # the map's credits' links
    if where == "home":
        assert sum("u-bnav-item" in s["cls"] for s in stops) == 3, stops
    if context is PHONE_LOW:  # the case: Home scrolls under the bottom bar
        assert page.evaluate("() => { const m = document.querySelector('.c-main'); return m.scrollHeight - m.clientHeight; }") > 64
    cut = [(s["tag"], s["cls"][:40], s["name"], _cut(s)) for s in stops
           if s["ring"] and not s["map"] and not s["outline"] and _cut(s)]
    assert cut == [], cut
    assert page.errors == [], page.errors
    page.context.close()


@pytest.mark.parametrize("where, context", [("search", DESKTOP), ("coverage", DESKTOP), ("home", PHONE_KEYS)],
                         ids=["search", "coverage", "home-phone"])
def test_forced_colours_show_an_outline(site, where, context):
    """Row 81: in forced colours (Playwright's forced_colors="active": the shadows are not drawn) every Tab stop has an
    outline of 2 px, whole (inside where the ring is: the bottom bar's items at the screen's edges), and its pixels
    change around it when it takes the focus (before: an outline nowhere, the ring a shadow with `outline: none`).
    Left out of the whole outline: the place map itself (A7) and its zoom buttons, whose inside ring lives in line
    volume's round 6's `mapbar.css` (docs/known-bugs.md)."""
    import numpy as np
    from PIL import Image
    import io
    page = _open(site, where, context, forced_colors="active")
    stops = _walk(page, limit=60)
    assert stops and all(s["forced"] for s in stops), stops
    bare = [(s["tag"], s["cls"][:40], s["name"], s["ol"]) for s in stops if s["ol"][0] == "none" or s["ol"][1] < 2]
    assert bare == [], bare
    cut = [(s["tag"], s["cls"][:40], s["name"], _cut(s)) for s in stops
           if not s["map"] and "leaflet-control-zoom" not in s["cls"] and _cut(s)]
    assert cut == [], cut
    # the pixels: the stop focused, then blurred (some stops, spread over the page)
    page.mouse.move(1, 1)
    page.evaluate(START)
    unchanged = []
    for n in range(min(len(stops), 40)):
        _tab(page)
        stop = page.evaluate(RING)
        if stop is None or stop["map"]:
            continue
        x, y, w, h = stop["clip"]
        x, y = max(0, x), max(0, y)
        w, h = min(w, context["viewport"]["width"] - x), min(h, context["viewport"]["height"] - y)
        if w < 2 or h < 2:
            continue
        clip = {"x": x, "y": y, "width": w, "height": h}
        focused = np.asarray(Image.open(io.BytesIO(page.screenshot(clip=clip, scale="css"))).convert("RGB")).astype(int)
        page.evaluate("() => { window.KBEL = document.activeElement; document.activeElement.blur(); }")
        page.evaluate(FRAMES)
        blurred = np.asarray(Image.open(io.BytesIO(page.screenshot(clip=clip, scale="css"))).convert("RGB")).astype(int)
        page.evaluate("() => window.KBEL.focus({preventScroll: true})")
        if not (np.abs(focused - blurred).max(axis=2) > 40).any():
            unchanged.append((stop["tag"], stop["cls"][:40], stop["name"]))
    assert unchanged == [], unchanged
    page.context.close()


# Each radio group shown on the page: its label, its radios' tab stops and which is checked
GROUPS = r"""() => [...document.querySelectorAll('[role=radiogroup]')].filter((g) => g.getBoundingClientRect().width > 0)
  .map((g) => { const rs = [...g.querySelectorAll('[role=radio]')];
    return {label: g.getAttribute('aria-label'), n: rs.length, stops: rs.map((r) => r.tabIndex),
            checked: rs.findIndex((r) => r.getAttribute('aria-checked') === 'true'), disabled: rs.map((r) => r.disabled),
            cards: g.classList.contains('s-cards')}; })"""
# The group `k` of GROUPS: the focused radio's index and the checked one's
STATE = r"""(k) => { const g = [...document.querySelectorAll('[role=radiogroup]')].filter((g) => g.getBoundingClientRect().width > 0)[k];
  const rs = [...g.querySelectorAll('[role=radio]')];
  return [rs.indexOf(document.activeElement), rs.findIndex((r) => r.getAttribute('aria-checked') === 'true'),
          rs.filter((r) => r.tabIndex === 0).length]; }"""


@pytest.mark.parametrize("where", ["search", "coverage"])
def test_radio_groups_take_the_arrows(site, where):
    """Row 82 (the planner's decision: WAI-ARIA's radio group): each radio group is one Tab stop, its checked radio
    (or the first when none is: the goal cards of Advanced's own values); → and ↓ move the focus to the next radio and
    choose it, ← and ↑ to the one before (round the group), End and Home to the last and the first. The search page's
    "Where" (the kit's Segmented) and the goal cards, whose arrows move the focus only (the planner, 2026-11-21:
    test_goal_cards_arrows_move_the_focus_only); the coverage page's language, theme and view (Segmented) and the
    quality scale (card.tsx). Before: every radio a Tab stop, the arrows did nothing."""
    from playwright.sync_api import TimeoutError as PlaywrightTimeout
    page = _open(site, where, DESKTOP)
    groups = page.evaluate(GROUPS)
    labels = [g["label"] for g in groups]
    if where == "search":
        assert "Where" in labels and any("look" in (l or "").lower() for l in labels), labels
    else:
        assert len(groups) == 4, labels
    for k, g in enumerate(groups):
        cards = g["cards"]  # the goal cards: the choice stays where it was
        enabled = [i for i in range(g["n"]) if not g["disabled"][i]]
        stop = g["checked"] if g["checked"] >= 0 and not g["disabled"][g["checked"]] else enabled[0]
        assert g["stops"] == [0 if i == stop else -1 for i in range(g["n"])], g
        # the focus by Tab: the group's stop
        page.evaluate("(k) => [...document.querySelectorAll('[role=radiogroup]')].filter((g) => g.getBoundingClientRect().width > 0)[k]"
                      ".querySelector('[role=radio][tabindex=\"0\"]').focus()", k)
        at = enabled.index(stop)
        for key, step in (("ArrowRight", 1), ("ArrowDown", 1), ("ArrowLeft", -1), ("ArrowUp", -1), ("End", None), ("Home", None)):
            page.keyboard.press(key)
            at = (len(enabled) - 1 if key == "End" else 0) if step is None else (at + step) % len(enabled)
            want = stop if cards else enabled[at]
            try:  # the choice's render (a group's own state, a page's language) settled on the expected radio
                page.wait_for_function(f"([k, i, c]) => {{ const s = ({STATE})(k); return s[0] === i && s[1] === c; }}",
                                       arg=[k, enabled[at], want], timeout=WAIT)
            except PlaywrightTimeout:
                pass  # the assertion below says what is there
            focused, checked, stops = page.evaluate(STATE, k)
            assert focused == enabled[at] and checked == want and stops == 1, (g["label"], key, focused, checked, stops)
    page.context.close()


SETTINGS = "() => JSON.stringify([window.FINDALINE_SEARCH.request, window.FINDALINE_SEARCH.preset, window.FINDALINE_SEARCH.goal])"
FOCUSED_CARD = "() => [document.activeElement?.dataset.goal || null, document.querySelector('.s-cards [aria-checked=true]')?.dataset.goal || null]"


def test_goal_cards_arrows_move_the_focus_only(site):
    """Row 82 (the planner, 2026-11-21, after the design review's answer (a)): on the search form's goal cards the
    arrows move the focus only and Space or Enter chooses; the cards stay one Tab stop, the checked card's. In Advanced
    with the user's own values ("Custom" checked) an arrow changes no setting (before: the first arrow applied the next
    card's values over them, with no way back); in Basic an arrow moves the focus and Space chooses the focused card."""
    page = _open(site, "search", DESKTOP)
    page.wait_for_function("() => !!window.FINDALINE_SEARCH", timeout=WAIT)
    # Basic: an arrow moves the focus, the choice stays; Space chooses
    page.evaluate("() => document.querySelector('.s-cards [role=radio][tabindex=\"0\"]').focus()")
    first = page.evaluate(FOCUSED_CARD)
    page.keyboard.press("ArrowRight")
    moved = page.evaluate(FOCUSED_CARD)
    assert moved[0] != first[0] and moved[1] == first[1], (first, moved)
    page.keyboard.press("Space")
    page.wait_for_function("() => document.activeElement?.getAttribute('aria-checked') === 'true'", timeout=WAIT)
    assert page.evaluate(FOCUSED_CARD) == [moved[0], moved[0]]
    # Advanced with the user's own values: "Custom" checked, an arrow changes nothing but the focus
    page.evaluate("() => document.querySelector('.s-tabs [data-tab=advanced]').click()")
    page.evaluate("() => (window.FINDALINE_SEARCH.setValue('min_length', 45), window.FINDALINE_SEARCH.setValue('min_drop', 40))")
    page.wait_for_function("() => document.querySelector('.s-cards [aria-checked=true]')?.dataset.goal === 'custom'", timeout=WAIT)
    page.evaluate("() => document.querySelector('.s-cards [role=radio][tabindex=\"0\"]').focus()")
    assert page.evaluate(FOCUSED_CARD) == ["custom", "custom"]
    before = page.evaluate(SETTINGS)
    for key in ("ArrowRight", "ArrowRight", "ArrowLeft", "End", "Home"):
        page.keyboard.press(key)
        page.evaluate(FRAMES)
        now = page.evaluate(FOCUSED_CARD)
        assert now[1] == "custom" and page.evaluate(SETTINGS) == before, (key, now)
    assert page.evaluate(FOCUSED_CARD)[0] != "custom"  # the focus did move
    # Tab out and Shift+Tab back: the stop is the checked card
    page.keyboard.press("Tab")
    page.keyboard.press("Shift+Tab")
    assert page.evaluate(FOCUSED_CARD) == ["custom", "custom"]
    page.context.close()


def test_arrows_pass_over_a_disabled_radio(site):
    """Row 82 (ui/radios.ts: only the radios that can be pressed): on the coverage page's theme switch with its middle
    radio disabled, → from the first goes to the third and ← back to the first; in the goal cards (focus only) likewise.
    The code review's F5: no test had a disabled radio."""
    page = _open(site, "coverage", DESKTOP)
    state = "() => { const rs = [...document.querySelectorAll('[aria-label=Theme] [role=radio]')]; return [rs.indexOf(document.activeElement), rs.findIndex((r) => r.getAttribute('aria-checked') === 'true')]; }"
    page.evaluate("() => { const rs = document.querySelectorAll('[aria-label=Theme] [role=radio]'); rs[0].click(); }")
    page.wait_for_function(f"() => ({state})()[1] === 0", timeout=WAIT)
    page.evaluate("() => { const rs = document.querySelectorAll('[aria-label=Theme] [role=radio]'); rs[1].disabled = true; rs[0].focus(); }")
    page.keyboard.press("ArrowRight")
    page.wait_for_function(f"() => ({state})()[1] === 2", timeout=WAIT)
    assert page.evaluate(state) == [2, 2]
    page.keyboard.press("ArrowLeft")
    page.wait_for_function(f"() => ({state})()[1] === 0", timeout=WAIT)
    assert page.evaluate(state) == [0, 0]
    page.context.close()
    page = _open(site, "search", DESKTOP)
    page.evaluate("() => { const cs = document.querySelectorAll('.s-cards [role=radio]'); cs[1].disabled = true; cs[0].focus(); }")
    page.keyboard.press("ArrowRight")
    ids = page.evaluate("() => [...document.querySelectorAll('.s-cards [role=radio]')].map((c) => c.dataset.goal)")
    assert page.evaluate(FOCUSED_CARD)[0] == ids[2], ids
    page.context.close()


def test_focused_segment_lies_above_the_selected_one(site):
    """Row 81: the search's tabs (WAI-ARIA's tabs: the arrows move the focus only) with the focus on Advanced, beside
    the selected Basic: the focused segment stands above its neighbours (before: no stacking, the selected segment
    drawn over the ring's side next to it)."""
    page = _open(site, "search", DESKTOP)
    page.focus(".s-tabs [data-tab=basic]")
    page.keyboard.press("ArrowRight")
    got = page.evaluate("""() => { const a = document.activeElement, cs = getComputedStyle(a);
      return {tab: a.dataset.tab, selected: a.getAttribute('aria-selected'), visible: a.matches(':focus-visible'),
              position: cs.position, z: cs.zIndex}; }""")
    assert got == {"tab": "advanced", "selected": "false", "visible": True, "position": "relative", "z": "1"}, got
    page.context.close()


AREAS = "() => document.querySelectorAll('.n-coverage-area').length"


HIT = """() => { for (const p of document.querySelectorAll('.n-coverage-area')) { const r = p.getBoundingClientRect();
  if (r.width < 30 || r.height < 30 || r.left < 0 || r.top < 0 || r.right > innerWidth - 300 || r.bottom > innerHeight) continue;
  for (const [fx, fy] of [[.5, .5], [.4, .5], [.5, .4], [.6, .6]]) { const x = r.left + r.width * fx, y = r.top + r.height * fy;
    if (document.elementFromPoint(x, y) === p) return [x, y]; } } return null; }"""
EUROPE = "() => window.FINDALINE_PLACE.map.setZoom(5, {animate: false})"
WIDE = "() => [...document.querySelectorAll('.n-coverage-area')].some((p) => p.getBoundingClientRect().width > 30)"
PRESSED = """() => { const a = document.activeElement, c = window.FINDALINE_PLACE.map.getCenter();
  return {map: a.classList.contains('c-placemap'), outline: a.classList.contains('n-coverage-area'),
          centre: [c.lat, c.lng], point: JSON.stringify(window.FINDALINE_SEARCH?.point ?? null)}; }"""


def test_coverage_outlines_are_no_tab_stops(site):
    """Row 81: with "Data coverage" on, its outlines (Leaflet's paths with a tooltip) are out of the Tab order (each
    tabindex -1, again after the coverage is switched off and on: each drawing makes new elements) and the coverage
    box's link to the coverage page is the keyboard's way; a pointer over an outline still shows its tooltip. Before:
    83 Tab stops before the pin and every control of the map (Chromium makes an SVG shape with a focus listener
    focusable, and Leaflet listens for the focus on a path with a tooltip)."""
    page = _open(site, "search", DESKTOP, coverage=True)
    page.wait_for_function(f"() => ({AREAS})() > 20", timeout=WAIT)
    all_out = "() => [...document.querySelectorAll('.n-coverage-area')].every((p) => p.getAttribute('tabindex') === '-1')"
    assert page.evaluate(all_out)
    stops = _walk(page)
    assert [s for s in stops if s["outline"] or s["tag"] == "path"] == []
    assert any("n-coverage-link" in s["cls"] for s in stops), [s["cls"] for s in stops]
    # off and on: new elements, out of the Tab order again
    page.evaluate("() => document.querySelector('.n-coverage-btn').click()")
    page.wait_for_function(f"() => ({AREAS})() === 0", timeout=WAIT)
    page.evaluate("() => document.querySelector('.n-coverage-btn').click()")
    page.wait_for_function(f"() => ({AREAS})() > 20", timeout=WAIT)
    assert page.evaluate(all_out)
    assert [s for s in _walk(page) if s["outline"] or s["tag"] == "path"] == []
    # the tooltip: the pointer over a point of an outline, the map zoomed out to Europe (ui_shots' c-new-coverage)
    page.evaluate(EUROPE)
    page.wait_for_function(WIDE, timeout=WAIT)
    hit = page.evaluate(HIT)
    assert hit, "a point on an outline"
    page.mouse.move(hit[0], hit[1])
    page.mouse.move(hit[0] + 2, hit[1] + 1)
    page.wait_for_selector(".leaflet-tooltip", timeout=WAIT)
    page.context.close()


@pytest.mark.parametrize("engine, pointer", [("chromium", "mouse"), ("chromium", "touch"), ("webkit", "mouse"), ("webkit", "touch")])
def test_coverage_outline_press_keeps_the_map_focused(site, engine, pointer):
    """Row 81 (the fix round, the code review's F4): a press on a coverage outline (a click, a finger's tap) moves the
    search's point there as any press on the map and leaves the focus on the map (Leaflet's on every press), so after
    a click the arrow keys pan the map, and a drag begun on an outline pans it; in WebKit as on main (measured with
    main's bundles: the same focus, tooltip and point), where the outline was not focusable. Before the fix round its
    tabindex made WebKit focus the outline on a press (the arrows dead); in Chromium a press focused the outline on
    main already (now the map, as in WebKit: a deviation from main, docs/known-bugs.md)."""
    p, edge, base, path = site
    browser = edge if engine == "chromium" else p.webkit.launch(
        env={k: v for k, v in os.environ.items() if k not in ("HTTP_PROXY", "HTTPS_PROXY")})
    try:
        if pointer == "touch" and engine == "webkit":
            context = {**{k: v for k, v in p.devices["iPhone 13"].items() if k != "default_browser_type"},
                       "viewport": {"width": 1024, "height": 900}}
        else:
            context = {**DESKTOP, **({"has_touch": True} if pointer == "touch" else {})}
        page = _open(site, "search", context, coverage=True) if engine == "chromium" else None
        if page is None:  # the same page in WebKit
            ctx = browser.new_context(reduced_motion="reduce", **context)
            ctx.add_init_script(SEEN % "'1'")
            page = ctx.new_page()
            page.goto(f"{base}/{path}?ui=c#new")
            page.wait_for_function("() => !!window.FINDALINE_PLACE && !!document.querySelector('.s-panel')", timeout=WAIT)
            page.evaluate(POINT)
        page.wait_for_function(f"() => ({AREAS})() > 20", timeout=WAIT)
        page.evaluate(EUROPE)
        page.wait_for_function(WIDE, timeout=WAIT)
        page.evaluate(FRAMES)
        hit = page.evaluate(HIT)
        assert hit, "a point on an outline"
        before = page.evaluate(PRESSED)
        if pointer == "touch":
            page.touchscreen.tap(*hit)
        else:
            page.mouse.move(*hit)
            page.mouse.down()
            page.mouse.up()
        page.evaluate(FRAMES)
        pressed = page.evaluate(PRESSED)
        assert pressed["map"] and not pressed["outline"], (engine, pointer, pressed)
        assert pressed["point"] != before["point"], (engine, pointer, before, pressed)  # the press moved the point
        if pointer == "mouse":
            for _ in range(3):
                page.keyboard.press("ArrowRight")
            page.wait_for_function(f"(c) => window.FINDALINE_PLACE.map.getCenter().lng !== c", arg=pressed["centre"][1], timeout=WAIT)
            # a drag begun on an outline pans the map (the press's default prevented does not stop Leaflet's dragging)
            page.evaluate(FRAMES)
            start = page.evaluate(HIT)
            assert start, "a point on an outline to drag from"
            centre = page.evaluate("() => window.FINDALINE_PLACE.map.getCenter().lng")
            page.mouse.move(*start)
            page.mouse.down()
            page.mouse.move(start[0] - 60, start[1] + 20, steps=6)
            page.mouse.move(start[0] - 120, start[1] + 40, steps=6)
            page.mouse.up()
            page.wait_for_function("(c) => window.FINDALINE_PLACE.map.getCenter().lng !== c", arg=centre, timeout=WAIT)
        page.context.close()
    finally:
        if engine == "webkit":
            browser.close()


def _ratio(a, b) -> float:
    """WCAG's contrast ratio of two sRGB colours."""
    def lum(c):
        v = [x / 255 for x in c[:3]]
        v = [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in v]
        return 0.2126 * v[0] + 0.7152 * v[1] + 0.0722 * v[2]
    hi, lo = sorted((lum(a), lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def test_coverage_link_ring_in_the_dark_theme(site):
    """Row 81 (the scope's A10): "Coverage map", the coverage box's link, focused by Tab in the dark theme: on each side
    its ring (the kit's: 2 px of the surface, then 2 px of the accent) reaches 3:1 against what lies just outside it
    (R3's non-text contrast). Measured 7.71:1 on every side at db84edbc (the review's 1.38:1 at the bottom was not
    reproduced): pinned here, no change made."""
    import io

    import numpy as np
    from PIL import Image
    page = _open(site, "search", DESKTOP, coverage=True, color_scheme="dark")
    page.wait_for_selector(".n-coverage-link:not([hidden])", timeout=WAIT)
    page.mouse.move(1, 1)
    page.evaluate(START)
    for _ in range(60):
        _tab(page)
        if page.evaluate("() => document.activeElement?.classList.contains('n-coverage-link')"):
            break
    got = page.evaluate("""() => { const e = document.activeElement, r = e.getBoundingClientRect();
      return {link: e.classList.contains('n-coverage-link'), visible: e.matches(':focus-visible'), box: [r.left, r.top, r.right, r.bottom],
              accent: getComputedStyle(e).getPropertyValue('--accent').trim()}; }""")
    assert got["link"] and got["visible"] and got["accent"] == "#62c3cc", got  # the case: the dark theme's ring
    shot = np.asarray(Image.open(io.BytesIO(page.screenshot(scale="css"))).convert("RGB")).astype(int)
    left, top, right, bottom = got["box"]
    mx, my = int((left + right) / 2), int((top + bottom) / 2)
    # the pixel 3 px out (in the accent's band, 2 to 4 px out) and the one 7 px out, at each side's middle
    sides = {"left": ((int(left - 3), my), (int(left - 7), my)), "right": ((int(right + 3), my), (int(right + 7), my)),
             "top": ((mx, int(top - 3)), (mx, int(top - 7))), "bottom": ((mx, int(bottom + 3)), (mx, int(bottom + 7)))}
    found = {}
    for side, ((rx, ry), (ox, oy)) in sides.items():
        ring, outside = shot[ry, rx], shot[oy, ox]
        found[side] = (list(ring), list(outside), round(_ratio(ring, outside), 2))
        assert np.abs(ring - np.array([0x62, 0xc3, 0xcc])).max() <= 40, (side, found)  # the ring's pixel
        assert found[side][2] >= 3, (side, found)
    page.context.close()


# The coverage box's button: its own box and its target (the box joined with an absolutely positioned ::after; the
# button has no border), the box's edges
TARGET = r"""() => { const b = document.querySelector('.n-coverage-btn'), r = b.getBoundingClientRect(), a = getComputedStyle(b, '::after');
  let t = [r.left, r.top, r.right, r.bottom];
  if (a.content !== 'none' && a.position === 'absolute') {
    const l = r.left + parseFloat(a.left), top = r.top + parseFloat(a.top);
    t = [Math.min(t[0], l), Math.min(t[1], top), Math.max(t[2], l + parseFloat(a.width)), Math.max(t[3], top + parseFloat(a.height))]; }
  return {own: [r.left, r.top, r.right, r.bottom], target: t, coarse: matchMedia('(pointer: coarse)').matches}; }"""
CATCH = """() => { window.CLICKS = []; document.addEventListener('click', (e) => {
  const c = e.target.closest('button, a'); window.CLICKS.push(c ? String(c.className) : e.target.tagName);
  e.preventDefault(); e.stopPropagation(); }, true); }"""


@pytest.mark.parametrize("size", [(1024, 768), (1180, 820)], ids=["1024x768", "1180x820"])
def test_touch_tablet_coverage_button_target(site, size):
    """Row 83 (the planner's decision: invisible targets, as the user's pick for the 3D view's marks): on a touch
    tablet, which keeps the desktop's box among the map's controls, the coverage box's 32 px button takes a finger's
    tap anywhere in its 44 px target, 2 px inside its top and its bottom edge (before: the target was the 32 px
    button)."""
    page = _open(site, "search", {"viewport": {"width": size[0], "height": size[1]}, **TABLET}, coverage=True)
    page.wait_for_selector(".n-coverage-btn", timeout=WAIT)
    got = page.evaluate(TARGET)
    own, target = got["own"], got["target"]
    assert got["coarse"] and own[3] - own[1] < 40, got  # the case: a coarse pointer, the drawn button under 44 px
    assert target[3] - target[1] >= 43.5 and target[2] - target[0] >= 43.5, got
    page.evaluate(CATCH)
    for y in (target[1] + 2, target[3] - 2):
        page.evaluate("() => { window.CLICKS = []; }")
        _tap(page, (own[0] + own[2]) / 2, y)
        page.wait_for_function("() => window.CLICKS.length > 0", timeout=WAIT)
        assert "n-coverage-btn" in page.evaluate("() => window.CLICKS[0]"), (y, got)
    page.context.close()


# The place map's coverage legend (step 3d G2: the kit's legend, docs/DESIGN.md row 90): its swatches, its items' size,
# the land swatch's edge; in the layers' box the box's width and the items' places
PLACE_LEGEND = r"""(root) => { const $$ = (s) => [...document.querySelectorAll(root + ' ' + s)];
  const box = document.querySelector('.c-placemap .leaflet-control-layers').getBoundingClientRect();
  return {swatches: $$('.u-legend-sw').map((e) => { const r = e.getBoundingClientRect(); return [r.width, r.height]; }),
          items: $$('.u-legend-item').map((e) => { const r = e.getBoundingClientRect(); return [getComputedStyle(e).fontSize, Math.round(r.left), Math.round(r.top)]; }),
          land: getComputedStyle(document.querySelector(root + ' .n-coverage-sw3')).boxShadow,
          line: getComputedStyle(document.querySelector('.c-placemap')).getPropertyValue('--line').trim(),
          layers: [box.width, box.height]}; }"""
SHOWN = "(root) => [...document.querySelectorAll(root + ' .u-legend-sw')].some((e) => e.getBoundingClientRect().width > 0)"


def test_place_map_coverage_legend(site):
    """The coverage box on a desktop (1400 x 900, the layer on): the kit's legend, its three swatches 16 x 12 px and
    its items 13 px; "Everywhere else" (transparent) drawn by an inset edge of --line (the user's "Restore 1.85:1",
    2026-11-22; the kit's 12 % ink edge gave 1.26:1)."""
    page = _open(site, "search", DESKTOP, coverage=True)
    page.wait_for_function(SHOWN, arg=".c-placemap .n-coverage-legend", timeout=WAIT)
    got = page.evaluate(PLACE_LEGEND, ".c-placemap .n-coverage-legend")
    assert got["swatches"] == [[16, 12]] * 3 and [i[0] for i in got["items"]] == ["13px"] * 3, got
    assert got["land"].startswith("rgb(179, 193, 194) 0px 0px 0px 1px inset") and got["line"] == "#b3c1c2", got
    page.context.close()


@pytest.mark.parametrize("context", [{"viewport": {"width": 700, "height": 1300}},
                                     {"viewport": {"width": 412, "height": 1300}, **TOUCH}], ids=["700x1300", "412x1300-touch"])
def test_layers_box_coverage_legend_keeps_its_width(site, context):
    """The design review's F1: in the phone's arrangement with a map 420 px high or more (a narrow tall window, a tall
    phone), the layers' box opened with the coverage on shows the legend under the coverage's row one item a line, and
    the box keeps its width (main: 222 px; the kit's line of three made it 490 and 404 px, over the zoom)."""
    page = _open(site, "search", context, coverage=True)
    toggle = ".c-placemap .leaflet-control-layers-toggle"
    page.wait_for_selector(toggle, timeout=WAIT)
    if context.get("has_touch"):
        page.tap(toggle)
    else:  # a mouse opens Leaflet's box by hovering (it opens under the pointer: no wait for the toggle to stay put)
        box = page.locator(toggle).bounding_box()
        page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.wait_for_selector(".c-placemap .leaflet-control-layers-expanded", timeout=WAIT)
    root = ".c-placemap .leaflet-control-layers .n-coverage-legend"
    page.wait_for_function(SHOWN, arg=root, timeout=WAIT)
    got = page.evaluate(PLACE_LEGEND, root)
    assert got["swatches"] == [[16, 12]] * 3, got
    assert len({left for _, left, _ in got["items"]}) == 1 and len({top for _, _, top in got["items"]}) == 3, got
    assert got["layers"][0] <= 260, got
    page.context.close()


@pytest.mark.parametrize("size", [(390, 664), (360, 640)], ids=["390x664", "360x640"])
def test_return_dialog_actions_inside(site, size):
    """Going back to Basic with values Basic cannot show asks first (the return dialog); on a 390 px and a 360 px phone
    both its actions lie inside the dialog and the window (before: "Stay in Advanced" 5.6 px out of the dialog at
    390 px and 18.6 px out of the window at 360 px, its row of two wider than the dialog)."""
    page = _open(site, "search", {"viewport": {"width": size[0], "height": size[1]}, **TOUCH})
    page.wait_for_function("() => !!window.FINDALINE_SEARCH", timeout=WAIT)
    page.evaluate("() => document.querySelector('.s-tabs [data-tab=advanced]').click()")
    page.evaluate("() => (window.FINDALINE_SEARCH.setValue('pretension', 4), window.FINDALINE_SEARCH.setValue('min_drop', 50))")
    page.evaluate("() => document.querySelector('.s-tabs [data-tab=basic]').click()")
    page.wait_for_selector(".s-return-dialog .n-actions button", timeout=WAIT)
    got = page.evaluate("""() => { const d = document.querySelector('.s-return-dialog'), r = d.getBoundingClientRect();
      return {dialog: [r.left + d.clientLeft, r.right - d.clientLeft], buttons: [...d.querySelectorAll('.n-actions button')].map((b) => {
        const q = b.getBoundingClientRect(); return [b.textContent.trim(), q.left, q.right]; })}; }""")
    assert len(got["buttons"]) == 2, got
    for name, left, right in got["buttons"]:
        assert left >= got["dialog"][0] - 0.5 and right <= got["dialog"][1] + 0.5 and left >= 0 and right <= size[0], (name, got)
    page.context.close()


HEADER = "() => { const h = document.querySelector('.cov-top'); return getComputedStyle(h).position === 'sticky' ? h.getBoundingClientRect().bottom : 0; }"


def test_coverage_list_shift_tab_clear_of_the_header(site):
    """Row 81 (the fix round, the design review's F3): on a wide screen, going back up the coverage page's list with
    Shift+Tab, every stop below the sticky header has its ring clear of it (the window's scroll-padding-top is the
    header's height, CoveragePage.tsx --cov-top; before: 11 of 102 stops wholly under the header, out of sight)."""
    page = _open(site, "coverage", DESKTOP)
    forward = _walk(page)
    assert len(forward) > 60, len(forward)  # the case: the list's rows and the footer
    under = []
    for _ in range(len(forward)):
        page.keyboard.press("Shift+Tab")
        page.evaluate(FRAMES)
        stop = page.evaluate(RING)
        if stop is None:
            continue
        if page.evaluate("() => !!document.activeElement.closest('.cov-top')"):
            break  # back in the header itself
        bottom = page.evaluate(HEADER)
        if stop["box"][1] < bottom - 0.5:
            under.append((stop["cls"][:30], stop["name"], round(bottom - stop["box"][1], 1)))
    assert under == [], under
    page.context.close()


def test_credit_link_ring_clear_of_its_letters(site):
    """Row 81 (the fix round, the design review's F1): a map credit's link focused by Tab on the desktop has 3 px of
    room each side inside its ring (its margin gives them back: the credits' line keeps its place), as much above and
    below as the credits and the map's edge leave (1 and 1.5 px: the ring whole inside the map) and no underline while
    the ring stands in its place; before, the 9.75 px letters ran into the ring's sides ("Leafle", "OpenTopoMar")."""
    page = _open(site, "search", DESKTOP)
    page.mouse.move(1, 1)
    page.evaluate(START)
    for _ in range(40):
        _tab(page)
        if page.evaluate("() => document.activeElement?.textContent === 'OpenTopoMap'"):
            break
    got = page.evaluate("""() => { const a = document.activeElement, cs = getComputedStyle(a), r = a.getBoundingClientRect();
      const c = a.closest('.leaflet-control-attribution').getBoundingClientRect(), m = a.closest('.leaflet-container').getBoundingClientRect();
      const range = document.createRange(); range.selectNodeContents(a); const t = range.getBoundingClientRect();
      return {visible: a.matches(':focus-visible'), pad: [cs.paddingTop, cs.paddingRight, cs.paddingBottom, cs.paddingLeft].map(parseFloat),
              decoration: cs.textDecorationLine, box: [r.left, r.top, r.right, r.bottom], text: [t.left, t.top, t.right, t.bottom],
              credits: [c.left, c.top, c.right, c.bottom], map: m.bottom}; }""")
    assert got["visible"] and got["decoration"] == "none", got
    assert got["box"][0] <= got["text"][0] - 3 + 0.5 and got["box"][2] >= got["text"][2] + 3 - 0.5, got  # 3 px each side
    assert got["box"][3] <= got["map"] + 0.5 and got["pad"][0] >= 1 and got["pad"][2] >= 1.5, got
    page.evaluate("() => document.activeElement.blur()")
    page.evaluate(FRAMES)
    credits = page.evaluate("() => { const c = document.querySelector('.c-placemap .leaflet-control-attribution').getBoundingClientRect(); return [c.left, c.top, c.right, c.bottom]; }")
    assert credits == got["credits"], (credits, got)  # the credits' line did not move with the focus
    page.context.close()


@pytest.fixture(scope="module")
def wsite(site):
    """The site's app page in Playwright's WebKit (Safari's engine), the same server and Playwright."""
    p, edge, base, path = site
    if not os.path.exists(p.webkit.executable_path):
        pytest.skip("Playwright's webkit is not installed")
    # the offline proxy of the tests' environment would also take WebKit's requests to the server
    browser = p.webkit.launch(env={k: v for k, v in os.environ.items() if k not in ("HTTP_PROXY", "HTTPS_PROXY")})
    try:
        yield p, browser, base, path
    finally:
        browser.close()


@pytest.mark.parametrize("where, size", [("search", (390, 664)), ("more", (390, 664)), ("more", (1024, 768)),
                                         ("more", (1400, 900))], ids=["search-390", "more-390", "more-1024", "more-1400"])
def test_webkit_fields_whole_at_the_column_foot(wsite, where, size):
    """Row 81 (the fix round, the design review's F4 and the scope review's finding 1): in WebKit (Safari's engine; its
    Tab reaches form controls) a text or number field Tab brings in at the form column's foot shows its whole ring:
    WebKit scrolls a focused field in only to about 12 px above its own foot and leaves the kit's scroll-margin aside,
    so the column keeps 24 px of scroll-padding at its foot while such a field has the focus (before: "Go to a place"
    and More settings' fields 11.8 to 15.7 px under the edge, at every size); with no field focused it has none, so
    no other scroll in the column moves (the column-wide padding moved 19 of ui_shots' 80 form pictures)."""
    page = _open(wsite, where, {"viewport": {"width": size[0], "height": size[1]}})
    stops = _walk(page)
    assert sum(s["tag"] == "input" for s in stops) >= (1 if where == "search" else 8), stops  # the case: the fields
    cut = [(s["tag"], s["cls"][:40], s["name"], _cut(s)) for s in stops
           if s["ring"] and not s["map"] and not s["outline"] and _cut(s)]
    assert cut == [], cut
    padding = "() => getComputedStyle(document.querySelector('.c-newsearch .c-form')).scrollPaddingBottom"
    page.evaluate("() => document.querySelector('.c-newsearch .c-form input:not([type=checkbox], [type=radio], [type=range])').focus()")
    assert page.evaluate(padding) == "24px"
    page.evaluate("() => document.activeElement?.blur()")
    assert page.evaluate(padding) in ("auto", "0px")
    page.context.close()
