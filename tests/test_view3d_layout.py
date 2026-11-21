"""The 3D view's three phone layouts the user picked on a mock-up (docs/3d-view-contract.md, "Step 3c, group B: the
phone's layout"; docs/DESIGN.md rows 37 to 39), in Playwright with a phone's profile (Pixel 7: touch, a coarse
pointer), each test failing when its pick is taken out:

- held sideways the bar's controls stand in one row, in every view, with two and with four kinds of imagery;
- the profile's card steps aside where it would reach the tool strip, and keeps its width where it would not;
- on a phone the notes that explain are out of the bar, behind the "About this view" button; the safety sentence
  "Check every line on the spot" stays in the bar, one line under the controls.

Headless Edge through Playwright: run from PowerShell (headless Edge prints nothing from Git Bash)."""

import contextlib
import json
import os
import sys
from urllib.parse import quote

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_patch import _offline_env, clip_data  # noqa: E402,F401 (the fixture of the 3D page's tests)
from test_shell_c_view_map import _tap  # noqa: E402
from test_view3d import _script_page  # noqa: E402
from test_view3d_others import _key_of  # noqa: E402
from test_web import EDGE, WAIT, _lines_of, _playwright, _server  # noqa: E402

pytestmark = pytest.mark.skipif(not os.path.exists(EDGE) or not _playwright(), reason="needs Microsoft Edge and Playwright")

READY = "() => document.getElementById('view3d')?.dataset.ready === '1'"
# Errors the page's own listeners would not show: a ResizeObserver whose callback resizes what it observes ends its
# round with an error event on the window (not a pageerror in Chromium)
ERRORS = "window.ERRORS = []; addEventListener('error', (e) => window.ERRORS.push(String(e.message).slice(0, 200)));"
# Two frames drawn: what answers a change of size before a frame (chrome.ts stepAside) has answered
FRAMES = "() => new Promise((done) => requestAnimationFrame(() => requestAnimationFrame(() => done(true))))"
# The bar: its height, the stage's, the toolbar's shown controls (their rows: the distinct tops of those 44 px high;
# pairs that overlap; those reaching outside the window), the views' words, the imagery's select and segment
BAR = r"""() => {
  const root = document.getElementById('view3d');
  const shown = (e) => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  const name = (e) => (e.getAttribute('aria-label') || e.textContent || e.className).trim().slice(0, 24);
  const items = [...root.querySelectorAll('.v3-toolbar button, .v3-toolbar input, .v3-toolbar select, .v3-zoom-value')]
    .filter(shown).map((e) => [name(e), e.getBoundingClientRect()]);
  const overlaps = [], outside = [], tops = new Set();
  items.forEach(([a, r], i) => {
    if (r.height >= 43.5) tops.add(Math.round(r.top));
    if (r.left < -0.5 || r.right > innerWidth + 0.5) outside.push(a);
    for (const [b, s] of items.slice(i + 1)) {
      if (Math.min(r.right, s.right) - Math.max(r.left, s.left) > 0.5 &&
          Math.min(r.bottom, s.bottom) - Math.max(r.top, s.top) > 0.5) overlaps.push([a, b]);
    }
  });
  return {view: root.dataset.view, bar: root.querySelector('.v3-bar').getBoundingClientRect().height,
          stage: root.querySelector('.v3-stage').getBoundingClientRect().height, rows: tops.size, count: items.length,
          overlaps, outside, words: [...root.querySelectorAll('.v3-views .v3-long, .v3-tool-label')].filter(shown).length,
          select: [...root.querySelectorAll('.v3-select')].some(shown),
          segment: [...root.querySelectorAll('.v3-toolbar .u-row .u-seg')].some(shown),
          selectWidth: root.querySelector('.v3-select')?.getBoundingClientRect().width,
          slider: root.querySelector('.v3-slider').getBoundingClientRect().width,
          notes: [...root.querySelectorAll('.v3-bar > .v3-note, .v3-bar .v3-imagery-note')].filter(shown)
            .map((e) => [e.innerText.trim(), Math.round(e.getBoundingClientRect().height)])};
}"""
VIEW = """(name) => { const root = document.getElementById('view3d'); window.BEFORE = Number(root.dataset.frames);
  document.querySelector(`.v3-views [data-view=${name}]`).click(); }"""
VIEWED = "(name) => { const d = document.getElementById('view3d').dataset; return d.view === name && Number(d.frames) > window.BEFORE; }"
# Four kinds of imagery as wide as they come (the clip's run has Shaded and Edges only): the two longest labels added
# to the select and the longest shown, as test_view3d_narrow_bar does
FOUR = """() => { const s = document.querySelector('.v3-select');
  s.prepend(new Option('Satellite (Esri)', 'x-esri'), new Option('Orthophoto', 'x-ortho')); s.value = 'x-esri'; }"""
# The card and the strip: the stage, each shown tool, the card, its chart, the slot's margin, the stage's class
CARD = r"""() => {
  const root = document.getElementById('view3d'), stage = root.querySelector('.v3-stage');
  const R = (e) => { const r = e.getBoundingClientRect(); return [r.left, r.top, r.right, r.bottom]; };
  const card = root.querySelector('.v3-pcard'), chart = root.querySelector('.v3-pcard .r-profile svg');
  return {stage: R(stage), tools: [...root.querySelectorAll('.v3-tool')].map(R).filter((r) => r[2] > r[0]),
          card: card && R(card), inner: card && card.clientWidth, chart: chart && chart.getBoundingClientRect().width,
          aside: stage.classList.contains('v3-aside'), strip: stage.style.getPropertyValue('--v3-strip'),
          margin: getComputedStyle(root.querySelector('.v3-card')).marginLeft, errors: window.ERRORS};
}"""
CHART = "() => !!document.querySelector('.v3-pcard .r-profile svg')"
# One tool more, as a run with a surface model has ("Trees and buildings": five tools at the full level, three at
# the phone level; the clip's run has four and two): a copy of the first shown tool added to the strip (the strip
# holds its tools in their order since step 3d: "Other saved lines", order 4 and hidden while the run has no other
# favourite, can stand before the profile's)
FIFTH = """() => { const tool = document.querySelector('.v3-tool:not(.v3-hidden)'), copy = tool.cloneNode(true);
  copy.dataset.tool = 'copy'; tool.parentElement.append(copy); }"""
# "About this view": the button, the box, its lines that show, the focus, the bar
INFO = r"""() => {
  const root = document.getElementById('view3d');
  const shown = (e) => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  const R = (e) => { const r = e.getBoundingClientRect(); return [r.left, r.top, r.right, r.bottom]; };
  const button = root.querySelector('.v3-info'), box = root.querySelector('.v3-infobox');
  return {button: shown(button) ? R(button) : null, inCredits: !!button.closest('.v3-credits'),
          expanded: button.getAttribute('aria-expanded'), controls: button.getAttribute('aria-controls') === box.id,
          name: button.getAttribute('aria-label'), box: shown(box) ? R(box) : null, role: box.getAttribute('role'),
          stage: R(root.querySelector('.v3-stage')), bar: root.querySelector('.v3-bar').getBoundingClientRect().height,
          lines: [...box.querySelectorAll('.v3-infobox-line')].filter(shown).map((p) => p.textContent),
          copies: box.querySelectorAll('.v3-infobox-line').length,
          focus: document.activeElement ? document.activeElement.className : '',
          inBar: [...root.querySelectorAll('.v3-bar > .v3-note, .v3-bar .v3-imagery-note')].filter(shown)
            .map((p) => p.className),
          inBarText: [...root.querySelectorAll('.v3-bar > .v3-note, .v3-bar .v3-imagery-note')].filter(shown)
            .map((p) => p.innerText.trim())};
}"""


def _open(browser, url, context):
    ctx = browser.new_context(**context)
    ctx.add_init_script(ERRORS)
    page = ctx.new_page()
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)[:300]))
    page.goto(url)
    page.wait_for_function(READY, timeout=WAIT * 4)
    return page


def _phone(p, width, height):
    """A phone's touch screen (Pixel 7's profile) of that viewport."""
    return {**{k: v for k, v in p.devices["Pixel 7"].items() if k != "default_browser_type"},
            "viewport": {"width": width, "height": height}}


def _site(clip_data, monkeypatch, name):
    data, meta = clip_data
    for key, value in _offline_env().items():
        monkeypatch.setenv(key, value)
    keys = [_key_of(r) for r in _lines_of(data, meta["id"])]
    return data, f"{_script_page(data, name, '')}", f"#run={meta['id']}&line={quote(keys[0], safe='')}"


# The data credits of ui_shots' clip (two sources: seven lines at 560 px), for the tests of the credits' box: the
# tests' own clip has none
CREDITS = [
    {"data": "NMT", "attribution": "Source: Główny Urząd Geodezji i Kartografii (GUGiK), geoportal.gov.pl",
     "licence": "geoportal.gov.pl terms (free use, source stated)", "url": "https://www.geoportal.gov.pl/"},
    {"data": "FABDEM", "attribution": "FABDEM V1-2 © University of Bristol; FABDEM is produced using Copernicus "
     "WorldDEM-30 © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by "
     "the European Union and ESA; all rights reserved", "licence": "CC BY-NC-SA 4.0",
     "url": "https://creativecommons.org/licenses/by-nc-sa/4.0/"}]
# The stage's bottom right corner: the credits' box (whether it is hidden; the box of its list's text) and its toggle,
# the info button (its box, its target: the box joined with an absolutely positioned ::after, whose insets count
# from inside the border; whether it is the element at its own centre), the info box (and the bottom of its notes
# with its padding: its height by its content), the tools, the focus
CORNER = r"""() => {
  const root = document.getElementById('view3d');
  const shown = (e) => { if (!e) return false; const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  const R = (e) => { if (!shown(e)) return null; const r = e.getBoundingClientRect(); return [r.left, r.top, r.right, r.bottom]; };
  const button = root.querySelector('.v3-info'), toggle = root.querySelector('.v3-credits .u-credits-toggle');
  const credits = root.querySelector('.v3-credits'), list = root.querySelector('.v3-credits-list');
  const box = root.querySelector('.v3-infobox'), lines = box.querySelector('.v3-infobox-lines');
  const b = button.getBoundingClientRect(), at = document.elementFromPoint((b.left + b.right) / 2, (b.top + b.bottom) / 2);
  const a = getComputedStyle(button, '::after'), cs = getComputedStyle(button);
  let target = [b.left, b.top, b.right, b.bottom];
  if (a.content !== 'none' && a.position === 'absolute') {
    const l = b.left + parseFloat(cs.borderLeftWidth) + parseFloat(a.left), t = b.top + parseFloat(cs.borderTopWidth) + parseFloat(a.top);
    target = [Math.min(b.left, l), Math.min(b.top, t), Math.max(b.right, l + parseFloat(a.width)), Math.max(b.bottom, t + parseFloat(a.height))];
  }
  const range = document.createRange();
  range.selectNodeContents(list);
  const text = range.getBoundingClientRect();
  return {credits: R(credits), hidden: getComputedStyle(credits).visibility === 'hidden',
          text: [text.left, text.top, text.right, text.bottom], toggle: R(toggle), open: toggle && toggle.getAttribute('aria-expanded'),
          button: R(button), target, onTop: at === button || button.contains(at), expanded: button.getAttribute('aria-expanded'),
          box: R(box), notesEnd: shown(box) ? lines.getBoundingClientRect().bottom + parseFloat(getComputedStyle(box).paddingBottom) : null,
          stage: R(root.querySelector('.v3-stage')), card: R(root.querySelector('.v3-pcard')),
          tools: [...root.querySelectorAll('.v3-tool')].map(R).filter(Boolean),
          focus: document.activeElement ? String(document.activeElement.className) : '', errors: window.ERRORS};
}"""


# An imagery credit beside the run's data credits, as a run with imagery has (put into the credits' list as
# scene.ts creditsBox renders one): beside the folded "Data credits" it wraps at 390 px
WRAPPED = """() => { const s = document.createElement('span'); s.className = 'v3-credit';
  s.textContent = 'Imagery: Geoportal orthophoto, GUGiK (free use, source stated)';
  document.querySelector('.v3-credits-list').append(' ', s); }"""


@contextlib.contextmanager
def _credits(data, run):
    """The run with data credits (CREDITS) while the block runs."""
    run_json = data / "runs" / run / "run.json"
    saved = run_json.read_text("utf-8")
    run_json.write_text(json.dumps({**json.loads(saved), "attribution": CREDITS}), encoding="utf-8")
    try:
        yield
    finally:
        run_json.write_text(saved, encoding="utf-8")


def _apart(a, b):
    """Whether two boxes [left, top, right, bottom] share no more than half a pixel."""
    return min(a[2], b[2]) - max(a[0], b[0]) <= 0.5 or min(a[3], b[3]) - max(a[1], b[1]) <= 0.5


def test_view3d_sideways_one_row(clip_data, monkeypatch):
    """Row 37 ("A: one row"): on a phone held sideways (844 x 390 and 667 x 375, touch) the bar's controls stand in
    one row in the orbit, the athlete's eyes and behind the athlete, with two kinds of imagery and with four: no
    control over another or outside the window, the views' switch and the tools as icons, the imagery's select and
    never its segment, and the bar as high in every one of those states (no resize of the canvas with the view):
    the readout's line, the row and one line of 16 px with the safety sentence "Check every line on the spot", the
    only note in the bar. Without the pick the wide bar's words stand there and the speed lies under the imagery's
    segment."""
    from playwright.sync_api import sync_playwright
    data, path, line = _site(clip_data, monkeypatch, "view3dsideways")
    with _server(data, start_scheduler=True) as port, sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            for width, height in ((844, 390), (667, 375)):
                page = _open(browser, f"http://127.0.0.1:{port}/{path}{line}", _phone(p, width, height))
                _assert_one_row(page, width)
                page.context.close()
        finally:
            browser.close()


def _bar_states(page):
    """The bar (BAR) in the athlete's eyes, behind the athlete and the orbit, with two kinds of imagery and with
    four, keyed by (kinds, view)."""
    states = {}
    for kinds in ("two", "four"):
        if kinds == "four":
            page.evaluate(FOUR)
        for view in ("eyes", "behind", "orbit"):
            page.evaluate(VIEW, view)
            page.wait_for_function(VIEWED, arg=view, timeout=WAIT)
            states[kinds, view] = page.evaluate(BAR)
    return states


def _assert_one_row(page, where):
    """Row 37's one row in every view with two and four kinds of imagery: no control over another or outside the
    window, the views' switch and the tools as icons, the imagery's select and never its segment, the safety sentence
    the only note, and the bar as high in every one of those states (96.1 px: 80.5 px for the readout's line and the
    row, 15.6 px for the sentence's line)."""
    states = _bar_states(page)
    for key, state in states.items():
        at = (where, key, state)
        assert state["view"] == key[1] and state["rows"] == 1, at
        assert state["overlaps"] == [] and state["outside"] == [], at
        assert state["words"] == 0 and state["select"] and not state["segment"], at
        # the athlete's views add the zoom's three pieces (and the phone's motion where there is one)
        assert state["count"] >= states[key[0], "orbit"]["count"] + (0 if key[1] == "orbit" else 3), at
        assert state["slider"] >= 64, at
        assert state["notes"] == [["Check every line on the spot.", 16]], at
    heights = {state["bar"] for state in states.values()}
    assert len(heights) == 1 and heights.pop() < 100, (where, states)
    assert page.evaluate("() => window.ERRORS") == [] and page.errors == [], page.errors


def test_view3d_tablet_one_row(clip_data, monkeypatch):
    """Row 37 on a touch tablet (the user, 2026-11-20: "C: the one-row bar of a phone held sideways"): at its default
    level (the phone level) upright and sideways (768 x 1024, 820 x 1180, 1024 x 600, 1180 x 820) the bar is the
    phone held sideways' one row in every view, with two and with four kinds of imagery, nothing over another or
    outside the window, one bar height (with the wide bar's words, 768 x 1024 had the walk, the speed and the
    imagery outside the window in the athlete's views, as on main). A mouse keeps the bar with words: the desktop's
    `?level=phone` (1024 x 600) shows the views' names and the imagery's segment. A phone at the full level turned
    without a reload (390 x 844 to 844 x 390 and back) takes the one row held sideways and its two rows upright
    (chrome.ts oneRow follows the window)."""
    from playwright.sync_api import sync_playwright
    data, path, line = _site(clip_data, monkeypatch, "view3dtablet")
    with _server(data, start_scheduler=True) as port, sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            url = f"http://127.0.0.1:{port}/{path}"
            for width, height in ((768, 1024), (820, 1180), (1024, 600), (1180, 820)):
                page = _open(browser, url + line, _phone(p, width, height))
                assert page.evaluate("() => document.getElementById('view3d').classList.contains('v3-phone')")
                _assert_one_row(page, (width, height))
                page.context.close()
            # a mouse at the phone level: the bar with words, the imagery's segment
            page = _open(browser, url + "?level=phone" + line, {"viewport": {"width": 1024, "height": 600}})
            mouse = page.evaluate(BAR)
            assert mouse["words"] >= 3 and mouse["segment"] and not mouse["select"], mouse
            page.context.close()
            # a phone at the full level, turned
            page = _open(browser, url + "?level=full" + line, _phone(p, 390, 844))
            rows = []
            for width, height in ((390, 844), (844, 390), (390, 844)):
                page.set_viewport_size({"width": width, "height": height})
                page.evaluate(FRAMES)
                page.evaluate(FRAMES)
                state = page.evaluate(BAR)
                rows.append((state["rows"], state["select"], state["words"], round(state["bar"])))
                assert state["overlaps"] == [] and state["outside"] == [], (width, state)
            assert rows[0] == rows[2] and rows[0][0] == 2 and rows[1][0] == 1, rows
            assert page.evaluate("() => window.ERRORS") == [] and page.errors == [], page.errors
            page.context.close()
        finally:
            browser.close()


def test_view3d_card_steps_aside(clip_data, monkeypatch):
    """Row 38 ("A: the card steps aside"): at 390 x 664 with five tools (the full level) the open profile card would
    reach the strip, so its slot starts 8 px right of the strip (60 px in) and no tool lies over the card; the chart
    fills the narrower card without a resize of the window; at 390 x 844 with three tools the card does not reach
    the strip and keeps its full width; held sideways with five tools the strip stands in two columns inside the
    stage and the card starts right of both. The choice is made at the card's full width and settles: no
    ResizeObserver error, the same answer two frames later."""
    from playwright.sync_api import sync_playwright
    data, path, line = _site(clip_data, monkeypatch, "view3daside")
    card = "() => document.querySelector('.v3-tool[data-tool=profile]').click()"
    with _server(data, start_scheduler=True) as port, sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            base = f"http://127.0.0.1:{port}/{path}"
            # 390 x 664, five tools: aside
            page = _open(browser, f"{base}?level=full{line}", _phone(p, 390, 664))
            page.evaluate(FIFTH)
            before = page.evaluate(CARD)
            assert len(before["tools"]) == 5 and not before["aside"] and before["card"] is None, before
            page.evaluate(card)
            page.wait_for_function(CHART, timeout=WAIT)
            page.evaluate(FRAMES)
            found = page.evaluate(CARD)
            right = max(t[2] for t in found["tools"])
            assert found["aside"] and found["strip"] == "60px" and found["margin"] == "60px", found
            assert abs(found["card"][0] - (right + 8)) <= 0.5 and all(_apart(t, found["card"]) for t in found["tools"]), found
            assert abs(found["card"][2] - (found["stage"][2] - 8)) <= 0.5, found
            # the chart as wide as the card's inside (its 12 px of padding each side): Profile.tsx took the new slot
            assert abs(found["chart"] - (found["inner"] - 24)) <= 1, found
            page.evaluate(FRAMES)
            again = page.evaluate(CARD)
            assert again["aside"] and again["card"] == found["card"] and again["errors"] == [], again
            # the card hidden: the class goes with it
            page.evaluate("() => document.querySelector('.v3-pcard-hide').click()")
            page.evaluate(FRAMES)
            assert not page.evaluate(CARD)["aside"]
            assert page.errors == [], page.errors
            page.context.close()
            # 390 x 844, three tools: the card clear of the strip keeps its width
            page = _open(browser, f"{base}{line}", _phone(p, 390, 844))
            page.evaluate(FIFTH)  # three tools, as a run with a surface model has at the phone level
            page.evaluate(card)
            page.wait_for_function(CHART, timeout=WAIT)
            page.evaluate(FRAMES)
            found = page.evaluate(CARD)
            assert len(found["tools"]) == 3 and not found["aside"] and found["margin"] == "8px", found
            assert abs(found["card"][0] - 8) <= 0.5 and all(_apart(t, found["card"]) for t in found["tools"]), found
            assert found["errors"] == [] and page.errors == [], (found, page.errors)
            page.context.close()
            # held sideways, five tools: two columns inside the stage, the card right of both
            page = _open(browser, f"{base}?level=full{line}", _phone(p, 844, 390))
            page.evaluate(FIFTH)
            page.evaluate(card)
            page.wait_for_function(CHART, timeout=WAIT)
            page.evaluate(FRAMES)
            found = page.evaluate(CARD)
            assert len({round(t[0]) for t in found["tools"]}) == 2, found
            assert all(t[3] <= found["stage"][3] + 0.5 for t in found["tools"]), found  # none cut by the stage's foot
            right = max(t[2] for t in found["tools"])
            assert found["aside"] and found["strip"] == f"{round(right + 8)}px", found
            assert all(_apart(t, found["card"]) for t in found["tools"]), found
            assert found["errors"] == [] and page.errors == [], (found, page.errors)
            page.context.close()
        finally:
            browser.close()


def test_view3d_card_aside_the_same_both_ways(clip_data, monkeypatch):
    """The step-aside rule is tested with its own effect off (chrome.ts stepAside: the class removed, the card
    measured at its full width, in one pass), so the answer at a window's height does not depend on where the
    window came from: a 390 px wide phone with five tools and the card open, its height swept from 600 to 800 px
    and back in steps of 8 px, gives the same answer at every height both ways, and both answers occur (aside on
    the lower windows, the full width on the higher). With the class left on during the test (the code review's
    mutation) the card stays aside on the way down where it was not on the way up."""
    from playwright.sync_api import sync_playwright
    data, path, line = _site(clip_data, monkeypatch, "view3dsweep")
    with _server(data, start_scheduler=True) as port, sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _open(browser, f"http://127.0.0.1:{port}/{path}?level=full{line}", _phone(p, 390, 600))
            page.evaluate(FIFTH)
            page.evaluate("() => document.querySelector('.v3-tool[data-tool=profile]').click()")
            page.wait_for_function(CHART, timeout=WAIT)
            heights, answers = list(range(600, 801, 8)), {"up": {}, "down": {}}
            for way, order in (("up", heights), ("down", heights[::-1])):
                for height in order:
                    page.set_viewport_size({"width": 390, "height": height})
                    page.evaluate(FRAMES)
                    page.evaluate(FRAMES)
                    found = page.evaluate(CARD)
                    answers[way][height] = found["aside"]
                    assert found["aside"] == (found["margin"] == "60px"), (way, height, found)
                    assert all(_apart(t, found["card"]) for t in found["tools"]), (way, height, found)
            assert answers["up"] == answers["down"], [h for h in heights if answers["up"][h] != answers["down"][h]]
            assert set(answers["up"].values()) == {True, False}, answers["up"]
            assert page.evaluate("() => window.ERRORS") == [] and page.errors == [], page.errors
            page.context.close()
        finally:
            browser.close()


def test_view3d_landmarks(clip_data, monkeypatch):
    """The 3D page's landmarks (docs/DESIGN.md row 48): the top bar a banner (`header`), the stage the page's one
    `main`, the bar a region with its name ("The line and its controls"), the tool strip a named toolbar; on a
    desktop and on a phone."""
    from playwright.sync_api import sync_playwright
    data, path, line = _site(clip_data, monkeypatch, "view3dlandmarks")
    marks = r"""() => { const q = (s) => document.querySelectorAll(s).length;
      const bar = document.querySelector('.v3-bar'), tools = document.querySelector('.v3-tools');
      return {mains: q('main'), stage: q('main.v3-stage'), banner: q('header.v3-top'), inMain: q('main canvas.v3-canvas'),
              bar: [bar.tagName, bar.getAttribute('aria-label')], barInMain: !!bar.closest('main'),
              tools: [tools.getAttribute('role'), tools.getAttribute('aria-label'), !!tools.closest('main')],
              title: q('header.v3-top h1')}; }"""
    with _server(data, start_scheduler=True) as port, sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            for context in ({"viewport": {"width": 1200, "height": 800}}, _phone(p, 390, 664)):
                page = _open(browser, f"http://127.0.0.1:{port}/{path}{line}", context)
                found = page.evaluate(marks)
                assert found == {"mains": 1, "stage": 1, "banner": 1, "inMain": 1,
                                 "bar": ["SECTION", "The line and its controls"], "barInMain": False,
                                 "tools": ["toolbar", "Tools", True], "title": 1}, found
                page.context.close()
        finally:
            browser.close()


def test_view3d_phone_notes_in_the_box(clip_data, monkeypatch):
    """Row 39 ("A: info button beside \"Data credits\""): on a phone (390 x 664) no note that explains stands in the
    bar, only the safety sentence "Check every line on the spot" (the user, 2026-11-20: "Keep that one sentence in
    the bar"); the button "About this view" stands in the credits' box, 44 px, and a tap opens a box inside the stage
    with the preview's note (without that sentence: nothing is said twice) and the phone level's; the bar keeps its height
    when the box opens and when the view changes, and the box then shows the look hint in place of the phone
    level's note; the button says whether the box is open, the focus goes into the box, Escape closes it and gives
    the focus back (and ends nothing else: "Lines from a point" stays on), and so does the box's own button; a
    failure's note stays in the bar. A desktop keeps its lines
    in the bar and has no button, in a mouse window under 600 px too."""
    from playwright.sync_api import sync_playwright
    data, path, line = _site(clip_data, monkeypatch, "view3dinfo")
    with _server(data, start_scheduler=True) as port, sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            url = f"http://127.0.0.1:{port}/{path}{line}"
            page = _open(browser, url, _phone(p, 390, 664))
            closed = page.evaluate(INFO)
            assert closed["inBar"] == ["v3-note v3-preview"] and closed["inBarText"] == ["Check every line on the spot."], closed
            assert closed["box"] is None and closed["copies"] == 0, closed
            button = closed["button"]
            assert button and closed["inCredits"] and closed["name"] == "About this view", closed
            assert min(button[2] - button[0], button[3] - button[1]) >= 43.5, closed
            assert closed["expanded"] == "false" and closed["controls"] and closed["role"] == "dialog", closed
            _tap(page, (button[0] + button[2]) / 2, (button[1] + button[3]) / 2)
            page.wait_for_function("() => document.querySelector('.v3-info').getAttribute('aria-expanded') === 'true'",
                                   timeout=WAIT)
            opened = page.evaluate(INFO)
            box, stage = opened["box"], opened["stage"]
            assert box and box[0] >= stage[0] and box[1] >= stage[1] and box[2] <= stage[2] and box[3] <= stage[3], opened
            assert ("A visual preview: heights and clearance come from the site's elevation data, the imagery may be "
                    "off by metres.") in opened["lines"], opened
            assert not any("on the spot" in text for text in opened["lines"]), opened
            assert opened["inBarText"] == ["Check every line on the spot."], opened
            assert "Simplified view on phones: anchors cannot be dragged." in opened["lines"], opened
            assert not any("pinch to zoom" in text for text in opened["lines"]), opened
            assert "v3-infobox-close" in opened["focus"] and opened["bar"] == closed["bar"], opened
            # the view changed with the box open: the look hint in the phone note's place, the bar as high
            page.evaluate(VIEW, "eyes")
            page.wait_for_function(VIEWED, arg="eyes", timeout=WAIT)
            eyes = page.evaluate(INFO)
            assert "Drag to look around, pinch to zoom." in eyes["lines"], eyes
            assert "Simplified view on phones: anchors cannot be dragged." not in eyes["lines"], eyes
            assert eyes["bar"] == closed["bar"] and eyes["inBarText"] == ["Check every line on the spot."], eyes
            page.keyboard.press("Escape")
            shut = page.evaluate(INFO)
            assert shut["box"] is None and shut["copies"] == 0 and shut["expanded"] == "false", shut
            assert "v3-info" in shut["focus"].split(), shut
            # opened by the keyboard (the focus is on the button), closed by the box's own button
            page.keyboard.press("Enter")
            assert page.evaluate(INFO)["box"], "Enter on the button opens the box"
            page.keyboard.press("Enter")  # the focus is on the box's close button
            shut = page.evaluate(INFO)
            assert shut["box"] is None and "v3-info" in shut["focus"].split(), shut
            # what answers a tap or failed stays in sight in the bar (here: "No other saved lines in this result.")
            page.evaluate(VIEW, "orbit")  # the note of the other lines shows in the orbit only (others.css)
            page.wait_for_function(VIEWED, arg="orbit", timeout=WAIT)
            page.evaluate("() => document.querySelector('.v3-bar > .v3-others-note').classList.remove('v3-hidden')")
            assert any("v3-alert" in cls for cls in page.evaluate(INFO)["inBar"])
            assert page.evaluate("() => window.ERRORS") == [] and page.errors == [], page.errors
            page.context.close()
            # the full level on the phone, "Lines from a point" on and the box open: one Escape closes the box and
            # leaves the tool on (the box takes the press first), the next one ends the tool
            page = _open(browser, url.replace("#", "?level=full#"), _phone(p, 390, 664))
            tool = "() => document.querySelector('.v3-tool[data-tool=point]').getAttribute('aria-pressed')"
            page.evaluate("() => document.querySelector('.v3-tool[data-tool=point]').click()")
            assert page.evaluate(tool) == "true"
            page.evaluate("() => document.querySelector('.v3-info').click()")
            assert page.evaluate(INFO)["box"]
            page.keyboard.press("Escape")
            assert page.evaluate(INFO)["box"] is None and page.evaluate(tool) == "true"
            page.keyboard.press("Escape")
            assert page.evaluate(tool) == "false"
            page.context.close()
            # a desktop: the lines in the bar, no button
            page = _open(browser, url, {"viewport": {"width": 1200, "height": 800}})
            desk = page.evaluate(INFO)
            assert desk["button"] is None and desk["box"] is None, desk
            assert any("v3-imagery-note" in cls for cls in desk["inBar"]), desk
            # the preview's note whole, one paragraph, as before
            whole = ("A visual preview: heights and clearance come from the site's elevation data, the imagery may be "
                     "off by metres. Check every line on the spot.")
            assert whole in desk["inBarText"], desk
            page.context.close()
            # a mouse window under 600 px (the full level): its compact bar keeps the three notes (no imagery, the
            # preview's whole, the anchors' hint) and has no button: the box is for touch
            page = _open(browser, url, {"viewport": {"width": 580, "height": 800}})
            narrow = page.evaluate(INFO)
            assert narrow["button"] is None and narrow["box"] is None, narrow
            assert len(narrow["inBar"]) == 3 and whole in narrow["inBarText"], narrow
            page.context.close()
            # the same window with a finger: the button, and only the sentence in the bar
            page = _open(browser, url.replace("#", "?level=full#"), _phone(p, 580, 800))
            touch = page.evaluate(INFO)
            assert touch["button"] and touch["inBarText"] == ["Check every line on the spot."], touch
            page.context.close()
        finally:
            browser.close()


def test_view3d_info_box_head_stays(clip_data, monkeypatch):
    """On a low stage (667 x 375, a phone held sideways) the info box is higher than the room and scrolls inside:
    its head stays at its top, so "Close" is whole and takes a tap with the notes scrolled to their end. More notes
    than the phone level has are made by the test (four hints of 25 words, as the full level with "Only valid lines"
    and a shore has)."""
    from playwright.sync_api import sync_playwright
    data, path, line = _site(clip_data, monkeypatch, "view3dhead")
    more = """() => { const bar = document.querySelector('.v3-bar'), text = 'Green: the line fits. Orange: it fits over ' +
      'the terrain but passes over trees or buildings. A dragged anchor stays where the line is valid.';
      for (let k = 0; k < 4; k++) { const p = document.createElement('p'); p.className = 'v3-note'; p.textContent = text;
        bar.append(p); } }"""
    head = r"""() => { const box = document.querySelector('.v3-infobox'), shut = box.querySelector('.v3-infobox-close');
      const R = (e) => { const r = e.getBoundingClientRect(); return [r.left, r.top, r.right, r.bottom]; };
      const s = R(shut), at = document.elementFromPoint((s[0] + s[2]) / 2, (s[1] + s[3]) / 2);
      return {box: R(box), shut: s, onTop: at === shut || shut.contains(at), room: [box.clientHeight, box.scrollHeight],
              scrolled: box.scrollTop, title: R(box.querySelector('.v3-infobox-title'))}; }"""
    with _server(data, start_scheduler=True) as port, sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _open(browser, f"http://127.0.0.1:{port}/{path}{line}", _phone(p, 667, 375))
            page.evaluate(more)
            button = page.evaluate(INFO)["button"]
            _tap(page, (button[0] + button[2]) / 2, (button[1] + button[3]) / 2)
            page.wait_for_function("() => document.querySelector('.v3-info').getAttribute('aria-expanded') === 'true'",
                                   timeout=WAIT)
            top = page.evaluate(head)
            assert top["room"][1] > top["room"][0] + 40, top  # the case: the box scrolls
            page.evaluate("() => { const box = document.querySelector('.v3-infobox'); box.scrollTop = box.scrollHeight; }")
            page.evaluate(FRAMES)
            end = page.evaluate(head)
            assert end["scrolled"] > 40 and end["onTop"], end
            assert end["shut"][1] >= end["box"][1] - 0.5 and end["shut"][3] - end["shut"][1] >= 43.5, end
            assert end["shut"] == top["shut"] and end["title"] == top["title"], (top, end)
            _tap(page, (end["shut"][0] + end["shut"][2]) / 2, (end["shut"][1] + end["shut"][3]) / 2)
            page.wait_for_function("() => document.querySelector('.v3-info').getAttribute('aria-expanded') === 'false'",
                                   timeout=WAIT)
            page.context.close()
        finally:
            browser.close()


def test_view3d_info_box_leaves_with_the_focus(clip_data, monkeypatch):
    """The open info box and the focus (info.ts): Tab from "Close" closes the box and the focus goes on to the next
    control (not to one the box covers while it stays open), Shift+Tab likewise backwards; a finger's tap on the
    box's text keeps it open, a tap beside it closes it; a tap on the info button while the box is open (the
    button stands above the open card then) closes it once, and it stays closed. A box that the page stops showing
    (a touch window of 590 px at the full level widened to 1200 px) closes itself, so with "Lines from a point" on
    the first Escape ends the tool."""
    from playwright.sync_api import sync_playwright
    data, path, line = _site(clip_data, monkeypatch, "view3dfocus")
    state = r"""() => { const box = document.querySelector('.v3-infobox'), a = document.activeElement;
      const r = box.getBoundingClientRect();
      return {open: r.width > 0 && r.height > 0, expanded: document.querySelector('.v3-info').getAttribute('aria-expanded'),
              inBox: box.contains(a), body: a === document.body, focus: a ? (a.className || a.tagName) : '',
              box: [r.left, r.top, r.right, r.bottom]}; }"""
    opened = "() => document.querySelector('.v3-info').getAttribute('aria-expanded') === 'true'"
    closed = "() => document.querySelector('.v3-info').getAttribute('aria-expanded') === 'false'"
    with _server(data, start_scheduler=True) as port, sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            url = f"http://127.0.0.1:{port}/{path}"
            page = _open(browser, url + line, _phone(p, 390, 664))
            # by the keyboard: Enter on the button, Tab from "Close"
            page.evaluate("() => document.querySelector('.v3-info').focus()")
            page.keyboard.press("Enter")
            first = page.evaluate(state)
            assert first["open"] and "v3-infobox-close" in first["focus"], first
            page.keyboard.press("Tab")
            after = page.evaluate(state)
            assert not after["open"] and after["expanded"] == "false", after
            assert not after["inBox"] and not after["body"], after  # the focus went on to a control
            page.evaluate("() => document.querySelector('.v3-info').focus()")
            page.keyboard.press("Enter")
            page.keyboard.press("Shift+Tab")
            back = page.evaluate(state)
            assert not back["open"] and not back["inBox"] and not back["body"], back
            # by a finger: a tap on the box's text keeps it, a tap beside it (on the stage) closes it
            button = page.evaluate(INFO)["button"]
            _tap(page, (button[0] + button[2]) / 2, (button[1] + button[3]) / 2)
            page.wait_for_function(opened, timeout=WAIT)
            box = page.evaluate(state)["box"]
            _tap(page, (box[0] + box[2]) / 2, box[3] - 30)
            page.evaluate(FRAMES)
            kept = page.evaluate(state)
            assert kept["open"] and kept["inBox"], kept
            _tap(page, (box[0] + box[2]) / 2, box[1] - 60)
            page.wait_for_function(closed, timeout=WAIT)
            # opened by a tap, its text tapped (the focus on the box itself), then the keyboard: Tab goes to "Close"
            # inside the box, the next Tab leaves and closes it (a key ends the press's hold on the box)
            _tap(page, (button[0] + button[2]) / 2, (button[1] + button[3]) / 2)
            page.wait_for_function(opened, timeout=WAIT)
            _tap(page, (box[0] + box[2]) / 2, box[3] - 30)
            page.keyboard.press("Tab")
            inside = page.evaluate(state)
            assert inside["open"] and "v3-infobox-close" in inside["focus"], inside
            page.keyboard.press("Tab")
            tabbed = page.evaluate(state)
            assert not tabbed["open"] and not tabbed["inBox"] and not tabbed["body"], tabbed
            # the card open: the info button stands above it, beside the open box; a tap on it closes the box once
            page.evaluate("() => document.querySelector('.v3-tool[data-tool=profile]').click()")
            page.wait_for_function(CHART, timeout=WAIT)
            page.evaluate(FRAMES)
            button = page.evaluate(INFO)["button"]
            _tap(page, (button[0] + button[2]) / 2, (button[1] + button[3]) / 2)
            page.wait_for_function(opened, timeout=WAIT)
            both = page.evaluate(INFO)
            assert both["button"][3] <= both["box"][1] + 0.5, both  # the case: the button is not under the box
            _tap(page, (button[0] + button[2]) / 2, (button[1] + button[3]) / 2)
            page.wait_for_function(closed, timeout=WAIT)
            page.evaluate(FRAMES)
            assert not page.evaluate(state)["open"], "the tap closed the box and did not open it again"
            assert page.evaluate("() => window.ERRORS") == [] and page.errors == [], page.errors
            page.context.close()
            # the window widened past the phone's width with the box open
            page = _open(browser, url + "?level=full" + line, _phone(p, 590, 800))
            tool = "() => document.querySelector('.v3-tool[data-tool=point]').getAttribute('aria-pressed')"
            page.evaluate("() => document.querySelector('.v3-tool[data-tool=point]').click()")
            page.evaluate("() => document.querySelector('.v3-info').click()")
            assert page.evaluate(state)["open"] and page.evaluate(tool) == "true"
            page.set_viewport_size({"width": 1200, "height": 800})
            page.wait_for_function(closed, timeout=WAIT)
            assert not page.evaluate(state)["open"]
            page.keyboard.press("Escape")
            assert page.evaluate(tool) == "false", "the first Escape ends the tool"
            assert page.evaluate("() => window.ERRORS") == [] and page.errors == [], page.errors
            page.context.close()
        finally:
            browser.close()


@pytest.mark.parametrize("device, engine", [("iPhone 13", "webkit"), ("Pixel 7", "chromium")])
def test_view3d_info_box_closes_on_a_press_beside(clip_data, monkeypatch, device, engine):
    """A press beside the open info box closes it by itself (info.ts: the document's pointerdown), also where the
    press moves no focus, so the box's focusout rule cannot close it: Safari's (Playwright's WebKit with the iPhone
    profile, a tap on the stage; measured 2026-11-20: without the press's own rule the box stayed open there, while
    in Chromium the tap moved the focus to the page and the focusout rule closed it: the code review's N2) and, in
    Edge, a tap whose mousedown does not move the focus (its default prevented by the test). The box's own text keeps
    it open."""
    from playwright.sync_api import sync_playwright
    data, path, line = _site(clip_data, monkeypatch, "view3dbeside")
    expanded = "() => document.querySelector('.v3-info').getAttribute('aria-expanded')"
    with _server(data, start_scheduler=True) as port, sync_playwright() as p:
        kind = getattr(p, engine)
        if engine == "webkit" and not os.path.exists(kind.executable_path):
            pytest.skip("Playwright's webkit is not installed")
        # the offline proxy of the tests' environment (_offline_env) would also take WebKit's requests to the server
        browser = (kind.launch(env={k: v for k, v in os.environ.items() if k not in ("HTTP_PROXY", "HTTPS_PROXY")})
                   if engine == "webkit" else kind.launch(channel="msedge", headless=True))
        try:
            context = {k: v for k, v in p.devices[device].items() if k != "default_browser_type"}
            page = _open(browser, f"http://127.0.0.1:{port}/{path}{line}", {**context, "viewport": {"width": 390, "height": 664}})
            if engine == "chromium":
                page.evaluate("() => document.addEventListener('mousedown', (e) => e.preventDefault(), true)")
            button = page.evaluate(INFO)["button"]
            _tap(page, (button[0] + button[2]) / 2, (button[1] + button[3]) / 2)
            page.wait_for_function(f"() => ({expanded})() === 'true'", timeout=WAIT)
            box = page.evaluate(INFO)["box"]
            _tap(page, (box[0] + box[2]) / 2, box[3] - 30)  # the box's own text
            page.evaluate(FRAMES)
            assert page.evaluate(expanded) == "true", "a press on the box's text keeps it"
            _tap(page, (box[0] + box[2]) / 2, box[1] - 40)  # the stage above the box
            page.evaluate(FRAMES)
            assert page.evaluate(expanded) == "false" and page.evaluate(INFO)["box"] is None, (engine, page.evaluate(INFO))
            assert page.evaluate("() => window.ERRORS") == [] and page.errors == [], page.errors
            page.context.close()
        finally:
            browser.close()


def test_view3d_info_button_and_the_credits(clip_data, monkeypatch):
    """The info button and its box with the run's data credits (open from 768 px of width as on main, a phone held
    sideways included; the user, 2026-11-20: "Open as before", "Keep open"). On a phone (390 x 664), a phone held
    sideways (844 x 390) and a touch tablet (1024 x 600), with the credits open and folded, the card open and closed:
    the button stands at the credits' box's start (its left top corner), its target 44 px, its centre on the line of
    "Data credits", is the element at its own centre (no tool, no credit over it) and a finger's tap on it opens the
    box. Open, the credits' box is as high as its text (no 8 px above and below it: the design review's P10); folded
    it keeps 8 px under its text, also when the list wraps beside an imagery credit (at 390 x 664). The
    open box is as high as its notes (P9: it grew to the credits' top before), and while it is open the credits'
    box is hidden where the box would overlap it, else stands wholly above it (also when the box holds one note less,
    as a run with imagery: lower than the credits); both happen. Escape brings the credits back with the focus on the
    button."""
    from playwright.sync_api import sync_playwright
    data, path, line = _site(clip_data, monkeypatch, "view3dcorner")
    hidden = set()

    def start(s):
        return abs(s["button"][0] - s["credits"][0]) <= 0.5 and abs(s["button"][1] - s["credits"][1]) <= 0.5

    def clear_or_hidden(s):
        hidden.add(s["hidden"])
        return s["hidden"] or s["credits"][3] <= s["box"][1] + 0.5

    def tap(page, box):
        _tap(page, (box[0] + box[2]) / 2, (box[1] + box[3]) / 2)
        page.evaluate(FRAMES)

    def button_and_box(page, where):
        s = page.evaluate(CORNER)
        assert s["button"] and start(s) and s["onTop"] and not s["hidden"], (where, s)
        assert min(s["target"][2] - s["target"][0], s["target"][3] - s["target"][1]) >= 43.5, (where, s)
        t, b = s["toggle"], s["button"]
        assert abs((t[1] + t[3]) / 2 - (b[1] + b[3]) / 2) <= 1.5, (where, s)  # on the line of "Data credits"
        if s["open"] == "true":  # the open credits' box as high as its text
            assert s["text"][1] - s["credits"][1] < 4 and s["credits"][3] - s["text"][3] < 4, (where, s)
        else:  # folded, the list keeps its 8 px under its text (it wraps beside an imagery credit)
            assert s["credits"][3] - s["text"][3] >= 6, (where, s)
        assert all(_apart(t, s["credits"]) for t in s["tools"]), (where, s)  # the credits' box right of the strip
        tap(page, s["button"])
        opened = page.evaluate(CORNER)
        assert opened["expanded"] == "true" and opened["box"] and clear_or_hidden(opened), (where, opened)
        assert opened["box"][1] >= opened["stage"][1] and opened["box"][3] <= opened["stage"][3], (where, opened)
        assert opened["box"][3] - opened["box"][1] <= opened["notesEnd"] - opened["box"][1] + 1, (where, opened)
        page.keyboard.press("Escape")
        shut = page.evaluate(CORNER)
        assert shut["box"] is None and not shut["hidden"] and "v3-info" in shut["focus"].split(), (where, shut)
        return s

    with _credits(data, clip_data[1]["id"]), _server(data, start_scheduler=True) as port, sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            for width, height in ((390, 664), (844, 390), (1024, 600)):
                page = _open(browser, f"http://127.0.0.1:{port}/{path}{line}", _phone(p, width, height))
                page.evaluate(FIFTH)  # three tools, as a run with a surface model has at the phone level
                if width < 768:  # folded credits beside an imagery credit that wraps (a run with imagery; the next
                    # render of the credits drops it)
                    page.evaluate(WRAPPED)
                page.evaluate(FRAMES)
                loaded = button_and_box(page, (width, "as loaded"))
                assert loaded["open"] == ("true" if width >= 768 else "false"), (width, loaded)  # as on main
                tap(page, loaded["toggle"])
                flipped = button_and_box(page, (width, "the credits' other state"))
                assert flipped["open"] != loaded["open"], (width, flipped)
                # the card open (it folds the credits), the credits opened again above it
                if flipped["open"] == "true":
                    tap(page, flipped["toggle"])
                page.evaluate("() => document.querySelector('.v3-tool[data-tool=profile]').click()")
                page.wait_for_function(CHART, timeout=WAIT)
                page.evaluate(FRAMES)
                carded = button_and_box(page, (width, "the card open"))
                assert carded["open"] == "false" and carded["card"], (width, carded)
                tap(page, carded["toggle"])
                both = button_and_box(page, (width, "the card and the credits open"))
                assert both["open"] == "true", (width, both)
                # one note less in the box (a run with imagery has no "No imagery for this result"), the card hidden
                page.evaluate("() => { document.querySelector('.v3-pcard-hide').click(); "
                              "document.querySelectorAll('.v3-imagery-note').forEach((n) => n.remove()); }")
                page.evaluate(FRAMES)
                lower = button_and_box(page, (width, "one note less"))
                assert lower["open"] == "true" and lower["card"] is None, (width, lower)
                assert page.evaluate("() => window.ERRORS") == [] and page.errors == [], (width, page.errors)
                page.context.close()
            assert hidden == {True, False}, hidden  # the credits hidden under the box, and clear above it
        finally:
            browser.close()


# "Lines from a point" answered: its dots are there, or its list says that the point has no valid line
FAN = """() => Number(document.getElementById('view3d').dataset.point) > 0 ||
  !!document.querySelector('.v3-optlist-title:not(.v3-hidden)')?.textContent"""
STAGE = "() => { const r = document.querySelector('.v3-stage').getBoundingClientRect(); return [r.left, r.top, r.right, r.bottom]; }"


def _fan(browser, p, url, heights=(839, 823, 807, 855, 791)):
    """A phone's page at the full level, 412 px wide, with the dots of "Lines from a point" shown: the press at
    anchor 1 (test_view3d_touch POINT_CLICK) finds lines or none by where its ray meets the terrain, which moves
    with the stage's height (measured 2026-11-20: 3 lines with a stage of 613.9 and 645.5 px, none at 629.9 and
    645.9 px), so the first of a few heights that gives dots is taken."""
    from test_view3d_touch import POINT_CLICK
    for height in heights:
        page = _open(browser, url, _phone(p, 412, height))
        page.evaluate("() => document.querySelector('.v3-tool[data-tool=point]').click()")
        page.evaluate(POINT_CLICK)
        page.wait_for_function(FAN, timeout=WAIT * 2)
        if page.evaluate("() => Number(document.getElementById('view3d').dataset.point)") > 1:
            page.evaluate(FRAMES)
            return page
        page.context.close()
    raise AssertionError(f"no lines from anchor 1 at any of the heights {heights}")


def test_view3d_dot_target_inside_the_stage(clip_data, monkeypatch):
    """A fan dot near the stage's edge keeps its whole 44 px target on a touch screen (screen.ts targetInside): on
    ui_shots' Pixel the dot of the 312 m line stood 19 px from the right edge once the notes had left the bar, and
    the screen's edge cut its target to 41.4 px. Here the window is narrowed until the rightmost dot stands 15 px
    from the stage's right edge (the scene keeps its scale with the stage's height): every dot's target lies inside
    the stage, 44 px each way, and still covers the dot."""
    from playwright.sync_api import sync_playwright
    from test_view3d_touch import BOXES
    data, path, line = _site(clip_data, monkeypatch, "view3ddots")
    with _server(data, start_scheduler=True) as port, sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _fan(browser, p, f"http://127.0.0.1:{port}/{path}?level=full{line}")
            size, stage = page.viewport_size, page.evaluate(STAGE)
            right = max((d["own"][0] + d["own"][2]) / 2 for d in page.evaluate(BOXES, ".v3-opt-dot"))
            centre = (stage[0] + stage[2]) / 2
            assert right > centre, (right, stage)
            page.set_viewport_size({"width": round(2 * (right - centre) + 30), "height": size["height"]})
            page.evaluate(FRAMES)
            dots, stage = page.evaluate(BOXES, ".v3-opt-dot"), page.evaluate(STAGE)
            near = [d for d in dots if stage[2] - (d["own"][0] + d["own"][2]) / 2 < 22]
            assert near, (stage, dots)  # the case: a dot nearer to the edge than half a target
            for d in dots:
                own, target = d["own"], d["target"]
                assert target[2] - target[0] >= 43.5 and target[3] - target[1] >= 43.5, d
                assert target[0] >= stage[0] - 0.5 and target[2] <= stage[2] + 0.5, (stage, d)
                assert target[1] >= stage[1] - 0.5 and target[3] <= stage[3] + 0.5, (stage, d)
                assert target[0] <= own[0] and target[2] >= own[2] and target[1] <= own[1] and target[3] >= own[3], d
            page.context.close()
        finally:
            browser.close()
