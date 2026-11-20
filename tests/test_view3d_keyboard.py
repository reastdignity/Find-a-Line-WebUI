"""The 3D view's keyboard and touch leftovers of step 3d, group G1 (docs/DESIGN.md rows 82 and 84), in Playwright:

- the views' and the imagery's switches are one Tab stop each and the arrows move the focus and choose (WAI-ARIA's
  radio group, ui/radios.ts); on a phone the open "About this view" closes on Shift+Tab out of it with the focus on
  its button;
- the tool strip's buttons stand in the DOM in their order, so the Tab order is the order on screen;
- on a touch screen an anchor's handle and another line's label near the stage's edge keep their whole target inside
  the stage (as the fan's dots);
- an anchor's handle stays under the finger at the first move of a drag on a phone (Pixel 7 in Edge, iPhone 13 in
  WebKit): the bar keeps its height while the drag lasts, its new row comes after the release.

Headless Edge through Playwright: run from PowerShell (headless Edge prints nothing from Git Bash)."""

import json
import os
import subprocess
import sys
from urllib.parse import quote

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_patch import _offline_env, clip_data  # noqa: E402,F401 (the fixture of the 3D page's tests)
from test_view3d import _script_page  # noqa: E402
from test_view3d_layout import FRAMES, STAGE, _open, _phone, _site  # noqa: E402
from test_view3d_others import _key_of  # noqa: E402
from test_web import EDGE, WAIT, _lines_of, _playwright, _server  # noqa: E402

pytestmark = pytest.mark.skipif(not os.path.exists(EDGE) or not _playwright(), reason="needs Microsoft Edge and Playwright")

# The radio groups of the bar (views.ts, imagery.ts): each one's label, its radios' tab stops, its checked radio and
# the focused one
BAR_GROUPS = r"""() => [...document.querySelectorAll('.v3-bar [role=radiogroup]')].filter((g) => g.getBoundingClientRect().width > 0)
  .map((g) => { const rs = [...g.querySelectorAll('[role=radio]')];
    return {label: g.getAttribute('aria-label'), stops: rs.map((r) => r.tabIndex),
            checked: rs.findIndex((r) => r.getAttribute('aria-checked') === 'true'), focused: rs.indexOf(document.activeElement)}; })"""
INFO_STATE = r"""() => { const box = document.querySelector('.v3-infobox'), r = box.getBoundingClientRect(), a = document.activeElement;
  return {open: r.width > 0 && r.height > 0, expanded: document.querySelector('.v3-info').getAttribute('aria-expanded'),
          focus: a ? String(a.className) : ''}; }"""


def test_view3d_keyboard(clip_data, monkeypatch):
    """Rows 82 and 84: the views' switch and the imagery's are one Tab stop each (their checked radio); → ↓ ← ↑, End
    and Home move the focus and choose (the view shown follows: data-view; the imagery: data-imagery); no handler
    of the page takes those keys (before: every radio a stop, the arrows did nothing). On a phone the open "About
    this view" closes on Shift+Tab from "Close" and from the box itself, with the focus on its button (before:
    Shift+Tab from "Close" went to "Save line": the credits that hold the button are out of the Tab order while the
    box covers them)."""
    from playwright.sync_api import sync_playwright
    data, path, line = _site(clip_data, monkeypatch, "view3dkeys")
    with _server(data, start_scheduler=True) as port, sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            url = f"http://127.0.0.1:{port}/{path}"
            page = _open(browser, url + "?level=full" + line, {"viewport": {"width": 1400, "height": 900}})
            groups = page.evaluate(BAR_GROUPS)
            assert [g["label"] for g in groups] == ["View", "Imagery"], groups
            for g in groups:
                assert g["stops"] == [0 if i == g["checked"] else -1 for i in range(len(g["stops"]))], g
            views = len(groups[0]["stops"])
            page.evaluate("() => document.querySelector('.v3-views [role=radio][tabindex=\"0\"]').focus()")
            at = groups[0]["checked"]
            for key, step in (("ArrowRight", 1), ("ArrowDown", 1), ("ArrowLeft", -1), ("End", None), ("Home", None),
                              ("ArrowUp", -1)):
                page.keyboard.press(key)
                page.evaluate(FRAMES)
                at = (views - 1 if key == "End" else 0) if step is None else (at + step) % views
                now = page.evaluate(BAR_GROUPS)[0]
                assert now["focused"] == at and now["checked"] == at and now["stops"].count(0) == 1, (key, now)
                shown = page.evaluate("() => [document.getElementById('view3d').dataset.view, document.activeElement.dataset.view]")
                assert shown[0] == shown[1], (key, shown)
            page.evaluate("() => document.querySelector('.v3-bar [aria-label=Imagery] [role=radio][tabindex=\"0\"]').focus()")
            before = page.evaluate("() => document.getElementById('view3d').dataset.imagery")
            page.keyboard.press("ArrowRight")
            page.evaluate(FRAMES)
            after, now = page.evaluate("() => document.getElementById('view3d').dataset.imagery"), page.evaluate(BAR_GROUPS)[1]
            assert after != before and now["focused"] == now["checked"] != groups[1]["checked"], (before, after, now)
            assert page.evaluate("() => window.ERRORS") == [] and page.errors == [], page.errors
            page.context.close()
            page = _open(browser, url + line, _phone(p, 390, 664))
            for start in ("close", "box"):
                page.evaluate("() => document.querySelector('.v3-info').focus()")
                page.keyboard.press("Enter")
                assert page.evaluate(INFO_STATE)["open"], start
                if start == "box":
                    page.evaluate("() => document.querySelector('.v3-infobox').focus()")
                page.keyboard.press("Shift+Tab")
                back = page.evaluate(INFO_STATE)
                assert not back["open"] and back["expanded"] == "false" and "v3-info" in back["focus"].split(), (start, back)
            assert page.evaluate("() => window.ERRORS") == [] and page.errors == [], page.errors
            page.context.close()
        finally:
            browser.close()


def test_view3d_tool_strip_in_order(tmp_path):
    """Row 84: the tool strip's buttons stand in the DOM in their order (chrome.ts createTools), so the Tab order is
    the order on screen; a tool of the same order comes after those added before it, and no button carries a CSS
    `order` (before: added at the end with `style.order`, so "Trees and buildings", added late with order 3, came
    last in the Tab order and third on screen)."""
    from playwright.sync_api import sync_playwright
    from test_viewer import VIEWER
    bundle = tmp_path / "chrome.js"
    subprocess.run(["node", "-e", "require('esbuild').buildSync({entryPoints: ['src/view3d/chrome.ts'], bundle: true, "
                                  "format: 'iife', globalName: 'chrome', platform: 'browser', outfile: %s})"
                    % json.dumps(str(bundle))], cwd=VIEWER, check=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = browser.new_page()
            page.set_content('<div id="box"></div>')
            page.add_script_tag(path=str(bundle))
            got = page.evaluate("""() => { const tools = chrome.createTools(document.getElementById('box'));
              [['save', 6], ['valid', 1], ['trees', 3], ['others', 4], ['copy', 3], ['point', 2]].forEach(([id, order]) =>
                tools.add({id, label: id, icon: 'M0 0h16', order, toggle: true, onClick() {}}));
              const buttons = [...document.querySelectorAll('#box > button')];
              return {dom: buttons.map((b) => b.dataset.tool), styled: buttons.filter((b) => b.style.order !== '').length}; }""")
            assert got == {"dom": ["valid", "point", "trees", "copy", "others", "save"], "styled": 0}, got
        finally:
            browser.close()


# The marks over the stage (the anchors' handles, the other lines' labels): each one's drawn box and its touch target
# (the box joined with its absolutely positioned ::after, whose insets count from inside the border), the stage (the
# canvas: the overlay clips at its edges)
MARKS = r"""() => { const st = document.querySelector('.v3-canvas').getBoundingClientRect(), stage = [st.left, st.top, st.right, st.bottom];
  return [...document.querySelectorAll('.v3-handle, .v3-other')].filter((e) => { const r = e.getBoundingClientRect();
    return r.width > 0 && r.height > 0 && !e.closest('.v3-hidden'); }).map((e) => {
    const r = e.getBoundingClientRect(), own = [r.left, r.top, r.right, r.bottom], a = getComputedStyle(e, '::after');
    let target = own;
    if (a.content !== 'none' && a.position === 'absolute') {
      const cs = getComputedStyle(e), l = r.left + parseFloat(cs.borderLeftWidth) + parseFloat(a.left),
            t = r.top + parseFloat(cs.borderTopWidth) + parseFloat(a.top);
      target = [Math.min(own[0], l), Math.min(own[1], t), Math.max(own[2], l + parseFloat(a.width)), Math.max(own[3], t + parseFloat(a.height))]; }
    return {kind: e.classList.contains('v3-handle') ? 'handle' : 'label', own, target, stage}; }); }"""


def test_view3d_marks_targets_inside_the_stage(clip_data, monkeypatch):
    """Row 84 (as the fan's dots, screen.ts targetInside): on a touch screen an anchor's handle and another line's label
    near the stage's edge keep their whole target (44 px; a label's 8 px beyond its box) inside the stage while it
    still covers the mark. The camera is zoomed in step by step (the wheel on the stage) until both kinds stand nearer
    to an edge than their target reaches beyond them; at each step every mark whose drawn box lies inside the stage
    has its target inside too (before: the target was centred on the mark and the stage's edge cut it)."""
    from playwright.sync_api import TimeoutError as PlaywrightTimeout
    from playwright.sync_api import sync_playwright
    data, path, line = _site(clip_data, monkeypatch, "view3dmarks")
    keys = [_key_of(r) for r in _lines_of(data, clip_data[1]["id"])]
    also = f"&also={quote(';'.join(keys[1:3]), safe='')}"
    with _server(data, start_scheduler=True) as port, sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _open(browser, f"http://127.0.0.1:{port}/{path}?level=full{line}{also}", _phone(p, 412, 839))
            page.wait_for_function("() => Number(document.getElementById('view3d').dataset.others) > 0", timeout=WAIT)
            stage = page.evaluate(STAGE)
            near, checked = set(), 0
            for _ in range(24):
                for m in page.evaluate(MARKS):
                    own, target, st = m["own"], m["target"], m["stage"]
                    if own[0] < st[0] or own[1] < st[1] or own[2] > st[2] or own[3] > st[3]:
                        continue  # the mark itself is cut: no target can cover it and stay inside
                    checked += 1
                    room = min(own[0] - st[0], own[1] - st[1], st[2] - own[2], st[3] - own[3])
                    if room < (44 - (own[3] - own[1])) / 2 - 0.5:
                        near.add(m["kind"])  # nearer to an edge than its target reaches beyond it
                    assert target[0] >= st[0] - 0.5 and target[1] >= st[1] - 0.5, m
                    assert target[2] <= st[2] + 0.5 and target[3] <= st[3] + 0.5, m
                    assert target[0] <= own[0] and target[1] <= own[1] and target[2] >= own[2] and target[3] >= own[3], m
                    assert min(target[2] - target[0], target[3] - target[1]) >= 43.5, m
                if near == {"handle", "label"}:
                    break
                # the wheel above the stage's middle (the walker's grip stands at the middle and would take it)
                page.mouse.move((stage[0] + stage[2]) / 2, (stage[1] + stage[3]) / 2 - 150)
                frames = page.evaluate("() => Number(document.getElementById('view3d').dataset.frames)")
                page.mouse.wheel(0, -240)
                try:  # a frame drawn at the new zoom (none when the controls' nearest distance is reached)
                    page.wait_for_function(f"() => Number(document.getElementById('view3d').dataset.frames) > {frames}", timeout=3000)
                except PlaywrightTimeout:
                    break
                page.evaluate(FRAMES)
            assert near == {"handle", "label"}, (near, checked)  # the case: both kinds of marks near an edge
            assert page.evaluate("() => window.ERRORS") == [] and page.errors == [], page.errors
            page.context.close()
        finally:
            browser.close()


HANDLE = r"""(k) => { const r = document.querySelectorAll('.v3-handle')[k].getBoundingClientRect();
  return [r.left + r.width / 2, r.top + r.height / 2]; }"""


@pytest.mark.parametrize("device, engine", [("Pixel 7", "chromium"), ("iPhone 13", "webkit")])
def test_view3d_handle_stays_under_the_finger(clip_data, monkeypatch, device, engine):
    """Row 84 (the planner's decision: the stage keeps its size while a drag lasts): on a phone at the full level an
    anchor's handle pressed at its centre and moved 1 px moves at most 2 px more than the finger, the stage keeps its
    height through the drag, and the bar's new row ("Back to the found line") shows after the release, the stage
    lower then (before: the first move made the bar 44 px higher and put the handle 24 px off the finger,
    docs/known-bugs.md; measured (11.4, -21.1) px on the Pixel)."""
    from playwright.sync_api import sync_playwright
    data, path, line = _site(clip_data, monkeypatch, "view3ddrag1")
    with _server(data, start_scheduler=True) as port, sync_playwright() as p:
        kind = getattr(p, engine)
        if engine == "webkit" and not os.path.exists(kind.executable_path):
            pytest.skip("Playwright's webkit is not installed")
        # the offline proxy of the tests' environment (_offline_env) would also take WebKit's requests to the server
        browser = (kind.launch(env={k: v for k, v in os.environ.items() if k not in ("HTTP_PROXY", "HTTPS_PROXY")})
                   if engine == "webkit" else kind.launch(channel="msedge", headless=True))
        try:
            context = {k: v for k, v in p.devices[device].items() if k != "default_browser_type"}
            for anchor in (0, 1):
                page = _open(browser, f"http://127.0.0.1:{port}/{path}?level=full{line}", context)
                x, y = page.evaluate(HANDLE, anchor)
                stages = [page.evaluate(STAGE)]
                page.mouse.move(x, y)
                page.mouse.down()
                page.mouse.move(x + 1, y, steps=1)
                page.evaluate(FRAMES)
                during = page.evaluate(HANDLE, anchor)
                stages.append(page.evaluate(STAGE))
                page.mouse.move(x + 12, y, steps=3)
                page.evaluate(FRAMES)
                stages.append(page.evaluate(STAGE))
                page.mouse.up()
                page.wait_for_function("() => !document.querySelector('.v3-reset').classList.contains('v3-hidden')", timeout=WAIT)
                page.evaluate(FRAMES)
                after = page.evaluate(STAGE)
                off = ((during[0] - x - 1) ** 2 + (during[1] - y) ** 2) ** 0.5
                assert off <= 2, (device, anchor, [x, y], during, stages)
                assert all(s == stages[0] for s in stages), (device, anchor, stages)
                assert after[3] - after[1] < stages[0][3] - stages[0][1] - 20, (device, anchor, stages, after)  # the row came after
                assert page.evaluate("() => window.ERRORS") == [] and page.errors == [], page.errors
                page.context.close()
        finally:
            browser.close()
