"""The 3D view after a long press (gate 2's item 3, the user's iPhone: "a long tap on the view causes text selection;
after it, it is impossible to gain focus for navigating the view"): the stage selects no text and shows no iOS callout
(view3d.css .v3-stage), and a press on the stage ends a selection left anywhere and takes the focus from a control
outside the stage (views.ts), after which the view turns under a drag as before. Playwright's WebKit with the iPhone 13
profile and Edge with the Pixel 7's (Playwright cannot make iOS's long press itself: the selection it leaves is
made by the page's Selection API). Every wait is an event with a deadline. Run from PowerShell
(.claude/rules/browser-tests.md)."""

import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_patch import _offline_env, clip_data  # noqa: E402,F401 (the fixture of the 3D page's tests)
from test_view3d_layout import FRAMES, _open, _site  # noqa: E402
from test_web import EDGE, WAIT, _playwright, _server  # noqa: E402

pytestmark = pytest.mark.skipif(not os.path.exists(EDGE) or not _playwright(), reason="needs Microsoft Edge and Playwright")

# The stage's rules as the browser computes them, and the text a selection of the whole stage holds (with words of
# the test's own put on the stage's overlay: the clip's stage may show none)
STAGE_TEXT = r"""() => { const stage = document.querySelector('.v3-stage'), s = getComputedStyle(stage);
  const probe = document.createElement('span'); probe.textContent = 'Words on the stage';
  (stage.querySelector('.v3-overlay') || stage).append(probe);
  const selection = getSelection(); selection.removeAllRanges(); selection.selectAllChildren(stage);
  const text = selection.toString(); selection.removeAllRanges(); probe.remove();
  return {select: s.webkitUserSelect || s.userSelect, words: probe.textContent.length, selected: text.trim().length}; }"""
# A selection over the bar's words and the focus on the bar's first shown control (what iOS's long press and a control
# pressed before leave), then the stage's middle in client pixels
LEAVE = r"""() => { const bar = document.querySelector('.v3-bar');
  const control = [...bar.querySelectorAll('button, input, select')].find((e) => e.getBoundingClientRect().width > 0 && !e.disabled);
  control.focus();
  getSelection().selectAllChildren(bar);
  const r = document.querySelector('.v3-canvas').getBoundingClientRect();
  return {selected: getSelection().toString().trim().length, focus: document.activeElement === control, x: r.left + r.width / 2, y: r.top + r.height / 2}; }"""
AFTER = "() => ({selected: getSelection().toString().length, focus: document.activeElement === document.body ? 'body' : document.activeElement.outerHTML.slice(0, 80)})"
CAMERA = "() => document.getElementById('view3d').dataset.camera || ''"


@pytest.mark.parametrize("device, engine", [("iPhone 13", "webkit"), ("Pixel 7", "chromium")])
def test_view3d_a_press_gives_the_view_back(clip_data, monkeypatch, device, engine):
    """The stage computes `user-select: none` and its rule holds `-webkit-touch-callout: none` (the iPhone's callout:
    no Windows browser computes it), so a selection of the whole stage holds none of its words; a selection over the
    bar's words and the focus on a control of the bar end with a tap on the stage (no text selected, the focus on the
    page's body); the orbit view then turns under a drag across the stage (its camera moves)."""
    from playwright.sync_api import sync_playwright
    data, path, line = _site(clip_data, monkeypatch, "view3dpress")
    with _server(data, start_scheduler=True) as port, sync_playwright() as p:
        kind = getattr(p, engine)
        if engine == "webkit" and not os.path.exists(kind.executable_path):
            pytest.skip("Playwright's webkit is not installed")
        # the offline proxy of the tests' environment (_offline_env) would also take WebKit's requests to the server
        browser = (kind.launch(env={k: v for k, v in os.environ.items() if k not in ("HTTP_PROXY", "HTTPS_PROXY")})
                   if engine == "webkit" else kind.launch(channel="msedge", headless=True))
        try:
            context = {k: v for k, v in p.devices[device].items() if k != "default_browser_type"}
            page = _open(browser, f"http://127.0.0.1:{port}/{path}{line}", context)
            page.evaluate(FRAMES)
            stage = page.evaluate(STAGE_TEXT)
            assert stage["select"] == "none" and stage["words"] > 0 and stage["selected"] == 0, stage
            css = page.evaluate("() => fetch([...document.querySelectorAll('link[rel=stylesheet]')].find((l) => /view3d/.test(l.href)).href).then((r) => r.text())")
            rule = re.search(r"\.v3-stage\{[^}]*\}", css.replace(" ", "").replace("\n", ""))
            assert rule and "-webkit-touch-callout:none" in rule.group(0), rule and rule.group(0)
            left = page.evaluate(LEAVE)
            assert left["selected"] > 0 and left["focus"] is True, left
            page.touchscreen.tap(left["x"], left["y"])
            page.evaluate(FRAMES)
            assert page.evaluate(AFTER) == {"selected": 0, "focus": "body"}
            # the view turns under a drag across the stage (the orbit controls, a mouse's pointer)
            before = page.evaluate(CAMERA)
            assert before
            page.mouse.move(left["x"], left["y"])
            page.mouse.down()
            page.mouse.move(left["x"] + 60, left["y"] + 10, steps=6)
            page.mouse.up()
            page.wait_for_function(f"(was) => ({CAMERA})() !== was", arg=before, timeout=WAIT)
            assert page.evaluate("() => window.ERRORS") == [] and page.errors == [], page.errors
        finally:
            browser.close()
