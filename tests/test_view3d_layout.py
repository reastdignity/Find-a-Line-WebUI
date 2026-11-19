"""The 3D view's three phone layouts the user picked on a mock-up (docs/3d-view-contract.md, "Step 3c, group B: the
phone's layout"; docs/DESIGN.md rows 37 to 39), in Playwright with a phone's profile (Pixel 7: touch, a coarse
pointer), each test failing when its pick is taken out:

- held sideways the bar's controls stand in one row, in every view, with two and with four kinds of imagery;
- the profile's card steps aside where it would reach the tool strip, and keeps its width where it would not;
- on a phone the notes that explain are out of the bar, behind the "About this view" button.

Headless Edge through Playwright: run from PowerShell (headless Edge prints nothing from Git Bash)."""

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
          notes: [...root.querySelectorAll('.v3-bar > .v3-note, .v3-bar .v3-imagery-note')].filter(shown).map(name)};
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
# the phone level; the clip's run has four and two): a copy of the first tool added to the strip
FIFTH = """() => { const tool = document.querySelector('.v3-tool'), copy = tool.cloneNode(true);
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
            .map((p) => p.className)};
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


def _apart(a, b):
    """Whether two boxes [left, top, right, bottom] share no more than half a pixel."""
    return min(a[2], b[2]) - max(a[0], b[0]) <= 0.5 or min(a[3], b[3]) - max(a[1], b[1]) <= 0.5


def test_view3d_sideways_one_row(clip_data, monkeypatch):
    """Row 37 ("A: one row"): on a phone held sideways (844 x 390 and 667 x 375, touch) the bar's controls stand in
    one row in the orbit, the athlete's eyes and behind the athlete, with two kinds of imagery and with four: no
    control over another or outside the window, the views' switch and the tools as icons, the imagery's select and
    never its segment, and the bar as high in every one of those states (no resize of the canvas with the view).
    Without the pick the wide bar's words stand there and the speed lies under the imagery's segment."""
    from playwright.sync_api import sync_playwright
    data, path, line = _site(clip_data, monkeypatch, "view3dsideways")
    with _server(data, start_scheduler=True) as port, sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            for width, height in ((844, 390), (667, 375)):
                page = _open(browser, f"http://127.0.0.1:{port}/{path}{line}", _phone(p, width, height))
                states = {}
                for kinds in ("two", "four"):
                    if kinds == "four":
                        page.evaluate(FOUR)
                    for view in ("eyes", "behind", "orbit"):
                        page.evaluate(VIEW, view)
                        page.wait_for_function(VIEWED, arg=view, timeout=WAIT)
                        states[kinds, view] = page.evaluate(BAR)
                for key, state in states.items():
                    where = (width, key, state)
                    assert state["view"] == key[1] and state["rows"] == 1, where
                    assert state["overlaps"] == [] and state["outside"] == [], where
                    assert state["words"] == 0 and state["select"] and not state["segment"], where
                    # the athlete's views add the zoom's three pieces (and the phone's motion where there is one)
                    assert state["count"] >= states[kinds, "orbit"]["count"] + (0 if key[1] == "orbit" else 3), where
                    assert state["slider"] >= 64, where
                heights = {state["bar"] for state in states.values()}
                assert len(heights) == 1 and heights.pop() < 90, (width, states)
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


def test_view3d_phone_notes_in_the_box(clip_data, monkeypatch):
    """Row 39 ("A: info button beside \"Data credits\""): on a phone (390 x 664) no note that explains stands in the
    bar; the button "About this view" stands in the credits' box, 44 px, and a tap opens a box inside the stage with
    the preview's note (its sentence "Check every line on the spot") and the phone level's; the bar keeps its height
    when the box opens and when the view changes, and the box then shows the look hint in place of the phone
    level's note; the button says whether the box is open, the focus goes into the box, Escape closes it and gives
    the focus back (and ends nothing else: "Lines from a point" stays on), and so does the box's own button; a
    failure's note stays in the bar. A desktop keeps its lines
    in the bar and has no button."""
    from playwright.sync_api import sync_playwright
    data, path, line = _site(clip_data, monkeypatch, "view3dinfo")
    with _server(data, start_scheduler=True) as port, sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            url = f"http://127.0.0.1:{port}/{path}{line}"
            page = _open(browser, url, _phone(p, 390, 664))
            closed = page.evaluate(INFO)
            assert closed["inBar"] == [] and closed["box"] is None and closed["copies"] == 0, closed
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
            assert any("Check every line on the spot." in text for text in opened["lines"]), opened
            assert "Simplified view on phones: anchors cannot be dragged." in opened["lines"], opened
            assert not any("pinch to zoom" in text for text in opened["lines"]), opened
            assert "v3-infobox-close" in opened["focus"] and opened["bar"] == closed["bar"], opened
            # the view changed with the box open: the look hint in the phone note's place, the bar as high
            page.evaluate(VIEW, "eyes")
            page.wait_for_function(VIEWED, arg="eyes", timeout=WAIT)
            eyes = page.evaluate(INFO)
            assert "Drag to look around, pinch to zoom." in eyes["lines"], eyes
            assert "Simplified view on phones: anchors cannot be dragged." not in eyes["lines"], eyes
            assert eyes["bar"] == closed["bar"] and eyes["inBar"] == [], eyes
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
            assert "v3-note" in desk["inBar"] and any("v3-imagery-note" in cls for cls in desk["inBar"]), desk
            page.context.close()
        finally:
            browser.close()


def test_view3d_sideways_credits_start_folded(clip_data, monkeypatch):
    """On a phone held sideways the run's data credits start folded also from 768 px of width (scene.ts wideScreen:
    open they covered 139 of the stage's 248 px at 844 x 390, the "About this view" button inside them); on a
    desktop of that width and on a touch tablet they start open, as before."""
    import json
    from playwright.sync_api import sync_playwright
    data, path, line = _site(clip_data, monkeypatch, "view3dcredits")
    run_json = data / "runs" / clip_data[1]["id"] / "run.json"  # data credits for the run (as test_view3d_touch_targets)
    saved = run_json.read_text("utf-8")
    run_json.write_text(json.dumps({**json.loads(saved), "attribution": [
        {"data": "Test model", "attribution": "Test survey", "licence": "CC BY 4.0", "url": "https://example.org/"}]}),
        encoding="utf-8")
    expanded = "() => document.querySelector('.v3-credits .u-credits-toggle').getAttribute('aria-expanded')"
    try:
        with _server(data, start_scheduler=True) as port, sync_playwright() as p:
            browser = p.chromium.launch(channel="msedge", headless=True)
            try:
                url = f"http://127.0.0.1:{port}/{path}{line}"
                for context, want in ((_phone(p, 844, 390), "false"), (_phone(p, 1024, 600), "true"),
                                      ({"viewport": {"width": 844, "height": 390}}, "true")):
                    page = _open(browser, url, context)
                    assert page.evaluate(expanded) == want, (context["viewport"], want)
                    page.context.close()
            finally:
                browser.close()
    finally:
        run_json.write_text(saved, encoding="utf-8")
