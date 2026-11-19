"""The 3D view's controls and marks on a touch screen (docs/DESIGN.md, "The pilot's look", rows 43 and 45; R2), in
Playwright with a phone's profile (Pixel 7: touch, a coarse pointer) and on a desktop: the tools, the views' switch,
the speed, the data credits' button, the list's heads and rows 44 px on touch; the marks over the stage (the fan's
dots, the other lines' labels, the anchors' handles) keep their drawn size while their invisible targets are 44 px on
touch and 24 px with a mouse; a finger's tap inside a target but outside the drawn box reaches the control. Headless
Edge through Playwright: run from PowerShell (headless Edge prints nothing from Git Bash)."""

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
# Each shown element of `sel`: its own box and its target (the box joined with an absolutely positioned ::after,
# whose insets count from inside the element's border), [left, top, right, bottom]
BOXES = r"""(sel) => [...document.querySelectorAll(sel)].filter((e) => {
    const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0 && !e.closest('.v3-hidden'); }).map((e) => {
  const r = e.getBoundingClientRect(), own = [r.left, r.top, r.right, r.bottom], a = getComputedStyle(e, '::after');
  if (a.content === 'none' || a.position !== 'absolute') return {own, target: own};
  const cs = getComputedStyle(e), l = r.left + parseFloat(cs.borderLeftWidth) + parseFloat(a.left),
        t = r.top + parseFloat(cs.borderTopWidth) + parseFloat(a.top);
  return {own, target: [Math.min(own[0], l), Math.min(own[1], t), Math.max(own[2], l + parseFloat(a.width)),
                        Math.max(own[3], t + parseFloat(a.height))]}; })"""
# The control a click reaches, recorded and not acted on (a capture listener on the document) while CATCHING
CATCH = """() => { window.CLICKS = []; window.CATCHING = true; document.addEventListener('click', (e) => {
  if (!window.CATCHING) return;
  const c = e.target.closest('button, .v3-handle'); window.CLICKS.push(c ? c.className : e.target.tagName);
  e.preventDefault(); e.stopPropagation(); }, true); }"""
POINT_CLICK = """() => { const r = document.querySelector('.v3-handle').getBoundingClientRect(),
  c = document.querySelector('.v3-canvas'), at = {clientX: r.left + r.width / 2, clientY: r.top + r.height / 2,
  pointerId: 7, button: 0, bubbles: true, isPrimary: true};
  c.dispatchEvent(new PointerEvent('pointerdown', at)); c.dispatchEvent(new PointerEvent('pointerup', at)); }"""


def _size(box):
    return box[2] - box[0], box[3] - box[1]


def _open(browser, url, context):
    ctx = browser.new_context(**context)
    page = ctx.new_page()
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)[:300]))
    page.goto(url)
    page.wait_for_function(READY, timeout=WAIT * 4)
    return page


def _tapped(page, x, y):
    """The classes of the control a finger's tap at (x, y) reaches (CATCH installed)."""
    page.evaluate("() => { window.CLICKS = []; }")
    _tap(page, x, y)
    page.wait_for_function("() => window.CLICKS.length > 0", timeout=WAIT)
    return page.evaluate("() => window.CLICKS[0]")


def test_view3d_touch_targets(clip_data, tmp_path, monkeypatch):
    from playwright.sync_api import sync_playwright
    data, meta = clip_data
    for key, value in _offline_env().items():
        monkeypatch.setenv(key, value)
    keys = [_key_of(r) for r in _lines_of(data, meta["id"])]
    page_path = _script_page(data, "view3dtouch", "")
    run_json = data / "runs" / meta["id"] / "run.json"  # data credits for the run (as test_view3d_credits_and_pill)
    saved = run_json.read_text("utf-8")
    run_json.write_text(json.dumps({**json.loads(saved), "attribution": [
        {"data": "Test model", "attribution": "Test survey", "licence": "CC BY 4.0", "url": "https://example.org/"}]}),
        encoding="utf-8")
    try:
        _touch_targets(data, meta, keys, page_path)
    finally:
        run_json.write_text(saved, encoding="utf-8")


def _touch_targets(data, meta, keys, page_path):
    from playwright.sync_api import sync_playwright
    with _server(data, start_scheduler=True) as port, sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            phone = {k: v for k, v in p.devices["Pixel 7"].items() if k != "default_browser_type"}
            base = f"http://127.0.0.1:{port}/{page_path}"
            # the phone level: the tools, the views' buttons and the speed 44 px each way; the data credits' button
            # keeps its drawn height and takes a tap 8 px above its box
            page = _open(browser, f"{base}#run={meta['id']}&line={quote(keys[0], safe='')}", phone)
            assert page.evaluate("() => document.getElementById('view3d').classList.contains('v3-phone')")
            for sel in (".v3-tool", ".v3-views button", ".v3-speed"):
                boxes = page.evaluate(BOXES, sel)
                assert boxes and all(min(_size(b["own"])) >= 43.5 for b in boxes), (sel, boxes)
            toggle = page.evaluate(BOXES, ".v3-credits .u-credits-toggle")[0]
            assert _size(toggle["own"])[1] < 40 and _size(toggle["target"])[1] >= 43.5, toggle
            page.evaluate(CATCH)
            own = toggle["own"]
            assert "u-credits-toggle" in _tapped(page, (own[0] + own[2]) / 2, own[1] - 8)
            assert page.errors == [], page.errors
            page.context.close()
            # the full level with two lines of the address: the handles (22 px drawn) and the labels (28 px high)
            # with 44 px targets; a tap 8 px below a label reaches it; the lines from a point: the dots (18 px drawn)
            # with 44 px targets, a tap 16 px beside a dot's centre reaches a dot; the list's heads and rows 44 px
            url = (f"{base}?level=full#run={meta['id']}&line={quote(keys[0], safe='')}"
                   f"&also={quote(';'.join(keys[1:3]), safe='')}")
            page = _open(browser, url, phone)
            page.wait_for_function("() => Number(document.getElementById('view3d').dataset.others) > 0", timeout=WAIT)
            handles, labels = page.evaluate(BOXES, ".v3-handle"), page.evaluate(BOXES, ".v3-other")
            assert len(handles) == 2 and all(_size(h["own"]) == (22, 22) for h in handles), handles
            assert all(min(_size(h["target"])) >= 43.5 for h in handles), handles
            assert labels and all(_size(b["own"])[1] < 40 and min(_size(b["target"])) >= 43.5 for b in labels), labels
            page.evaluate(CATCH)
            own = labels[0]["own"]
            assert "v3-other" in _tapped(page, (own[0] + own[2]) / 2, own[3] + 8)
            page.evaluate("() => { document.querySelectorAll('.v3-other').forEach((b) => b.closest('.v3-other-at').remove()); }")
            page.evaluate("() => { window.CATCHING = false; document.querySelector('.v3-tool[data-tool=point]').click(); }")
            page.evaluate(POINT_CLICK)
            page.wait_for_function("() => Number(document.getElementById('view3d').dataset.point) > 0", timeout=WAIT * 2)
            dots = page.evaluate(BOXES, ".v3-opt-dot")
            assert dots and all(_size(d["own"]) == (18, 18) and min(_size(d["target"])) >= 43.5 for d in dots), dots
            for sel in (".v3-opt-sort", ".v3-opt-row td"):
                boxes = page.evaluate(BOXES, sel)
                assert boxes and all(_size(b["own"])[1] >= 43.5 for b in boxes), (sel, boxes)
            own = dots[0]["own"]
            page.evaluate("() => { window.CATCHING = true; }")
            assert "v3-opt-dot" in _tapped(page, (own[0] + own[2]) / 2 + 16, (own[1] + own[3]) / 2)
            # the synthetic press on the terrain (POINT_CLICK) has no pointer for the page's capture: its error only
            assert [e for e in page.errors if "setPointerCapture" not in e] == [], page.errors
            page.context.close()
            # a desktop: the marks' targets 24 px, the labels as drawn (28 px)
            page = _open(browser, url, {"viewport": {"width": 1200, "height": 800}})
            page.wait_for_function("() => Number(document.getElementById('view3d').dataset.others) > 0", timeout=WAIT)
            handles, labels = page.evaluate(BOXES, ".v3-handle"), page.evaluate(BOXES, ".v3-other")
            assert all(_size(h["target"]) == (24, 24) for h in handles), handles
            assert labels and all(b["target"] == b["own"] and _size(b["own"])[1] >= 28 for b in labels), labels
            page.context.close()
        finally:
            browser.close()
