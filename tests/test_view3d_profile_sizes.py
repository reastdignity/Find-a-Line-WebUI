"""The 3D view's profile card after Profile.tsx's "12 a" (step 3c; Profile.tsx serves the 2D result and this card:
.claude/rules/viewer.md): the chart's text 12 px with its labels 2 px apart or more on a desktop, and on a touch phone
with "Rigging and layers" open the profile's controls a finger's 44 px high (the 1:1 scale, the rigging's fields, a
layer's row). Playwright's Edge over the app on the clip (test_patch's clip_data, as test_view3d_profile's card test).
Run from PowerShell (.claude/rules/browser-tests.md)."""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_patch import _offline_env, clip_data  # noqa: E402,F401 (the fixture of the 3D page's tests)
from test_web import EDGE, _lines_of, _playwright, _server  # noqa: E402

pytestmark = pytest.mark.skipif(not os.path.exists(EDGE) or not _playwright(),
                                reason="needs Microsoft Edge and Playwright (group ui)")

# the chart's text sizes and the nearest two labels' gap (their glyph boxes), as test_view_frame's
CHART = """() => { const svg = document.querySelector('.v3-card .fal-profile-chart svg'), texts = [...svg.querySelectorAll('text')];
  const labels = [...svg.querySelectorAll('text.fal-label')].map((t) => t.getBoundingClientRect());
  let apart = Infinity;
  labels.forEach((a, k) => labels.slice(k + 1).forEach((b) => { const dx = Math.max(b.left - a.right, a.left - b.right), dy = Math.max(b.top - a.bottom, a.top - b.bottom);
    apart = Math.min(apart, Math.max(dx, dy)); }));
  return {sizes: [...new Set(texts.map((t) => getComputedStyle(t).fontSize))], labels: labels.length, apart}; }"""
# the profile's controls drawn in the card (with "Rigging and layers" open), each one's height
CONTROLS = """() => [...document.querySelectorAll('.v3-card .r-profile .fal-scale, .v3-card .r-profile .fal-profile-controls input[type=number], .v3-card .r-profile .fal-layers label')]
  .filter((e) => e.getBoundingClientRect().height).map((e) => [e.className || e.tagName, Math.round(e.getBoundingClientRect().height)])"""


def _open_card(page, port, run, line):
    page.goto(f"http://127.0.0.1:{port}/view3d#run={run}&line={line}")
    page.wait_for_function("() => document.getElementById('view3d')?.dataset.ready === '1'", timeout=90000)
    if not page.query_selector(".v3-card .fal-profile-chart"):
        page.click(".v3-tool[data-tool=profile]")
    page.wait_for_selector(".v3-card .fal-profile-chart svg text.fal-label", timeout=30000)


def test_view3d_card_text_and_touch_sizes(clip_data, monkeypatch):
    """The 3D card: the chart's text 12 px and its labels apart (desktop); its controls 44 px on a touch phone."""
    from playwright.sync_api import sync_playwright
    from test_web import DESKTOP, PHONE
    data, meta = clip_data
    for key, value in _offline_env().items():
        monkeypatch.setenv(key, value)
    line = ",".join(str(v) for v in _lines_of(data, meta["id"])[0][:4])
    with _server(data, start_scheduler=True) as port, sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = browser.new_page(**DESKTOP)
            _open_card(page, port, meta["id"], line)
            chart = page.evaluate(CHART)
            page.close()
            page = browser.new_page(**PHONE)
            _open_card(page, port, meta["id"], line)
            page.tap(".v3-pcard-head .u-chip")
            page.wait_for_function("() => !!document.querySelector('.v3-card .v3-pcard.r-rigging')", timeout=30000)
            controls = page.evaluate(CONTROLS)
            page.close()
        finally:
            browser.close()
    assert chart["sizes"] == ["12px"] and chart["labels"] >= 2 and chart["apart"] >= 2, chart
    assert controls and min(h for _, h in controls) >= 44, controls
