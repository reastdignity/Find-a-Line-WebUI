"""The result view's seams of step 3c (viewer/src/result/view/SpotColumns.tsx, SpotPanels.tsx): its empty slots (the
run's actions in the header and in a phone's pill, the profile card over the map, the profile's dock in a phone's
sheet, the selected line's actions after the details) draw nothing, so the view (?view=b) shows none of today's
features yet, also with a spot selected, and the elements around the slots are the ones they were; today's page
still shows its run's actions and a selected line's profile (the card on a desktop, the dock in a phone's sheet).
Playwright's Edge over the app's server, offline, on the result view's clip run (clip_runs.view_clip). Every wait
is an event with a deadline. Run from PowerShell (.claude/rules/browser-tests.md)."""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_shell_c import BIG  # noqa: E402
from test_shell_c_view_map import DESKTOP, PHONE, WAIT, _open, _state, site, view_clip  # noqa: E402,F401
from test_web import EDGE, _playwright  # noqa: E402

pytestmark = pytest.mark.skipif(not os.path.exists(EDGE) or not _playwright(),
                                reason="needs Microsoft Edge and Playwright (group ui)")

# What today's page draws of the features the view leaves out until step 3c joins them: the run's actions, a line's
# profile (its card, its dock, its chart) and the line's buttons in today's details
TODAY = (".r-actions", ".r-card", ".r-dock", ".fal-profile-chart", ".r-acts", ".r-copy", ".r-view3d", ".r-reprofile")

# The children of an element, each as its tag and its classes in their order
CHILDREN = r"""(selector) => { const el = document.querySelector(selector);
  return el ? Array.from(el.children, (c) => [c.tagName.toLowerCase(), ...c.classList].join('.')) : null; }"""


def _children(page, selector: str, names: tuple) -> list:
    """The children of `selector`, each named by the first of `names` among its classes (else by its tag and all its
    classes: a child nobody expected)."""
    kids = page.evaluate(CHILDREN, selector)
    assert kids is not None, f"no {selector}"
    return [next((n for n in names if n in kid.split(".")[1:]), kid) for kid in kids]


def _present(page) -> list:
    """Which of today's features (TODAY) the page shows."""
    return page.evaluate("(sels) => sels.filter((s) => !!document.querySelector(s))", list(TODAY))


# The classes that name a child in CHILDREN's lists, the most particular first ("u-grow" also stands on the pill's
# name)
NAMES = ("c-result-top", "c-cols", "c-col-list", "c-col-map", "c-col-details", "c-back", "c-run-title", "c-leaflet",
         "v-switch", "v-foot", "vl-details", "vl-empty", "vl-list", "c-phone-top", "c-pill", "c-pill-name", "u-sheet",
         "r-actions", "u-grow")
# The view's elements that hold the slots and those around them, with their children as main drew them before the
# seams (e5967f6a; a dump of every element's tag and classes in these states was the same before and after): per
# device, at first and with a spot selected
DESKTOP_FIRST = {".v-result": ["c-result-top", "c-cols"], ".c-result-top": ["c-back", "c-run-title", "u-grow"],
                 ".c-cols": ["c-col-list", "c-col-map", "c-col-details"],
                 ".c-col-map": ["c-leaflet", "v-switch", "v-foot"], ".c-col-dbody": ["vl-empty"]}
DESKTOP_SELECTED = {**DESKTOP_FIRST, ".c-col-dbody": ["vl-details"]}
PHONE_FIRST = {".v-result": ["c-col-map", "c-phone-top", "u-sheet"], ".c-phone-top": ["c-pill"],
               ".c-pill": ["c-back", "c-pill-name"], ".c-col-map": ["c-leaflet", "v-switch", "v-foot"],
               ".u-sheet-body": ["vl-list"]}
PHONE_SELECTED = {**PHONE_FIRST, ".u-sheet-body": ["vl-details", "vl-list"]}


def _holds(page, want: dict):
    """Every element of `want` has the children it names, and none of today's features is on the page."""
    assert {selector: _children(page, selector, NAMES) for selector in want} == want
    assert _present(page) == []


def test_view_draws_no_slot(site):
    """The view on a desktop and on a phone, at first and with a spot selected: none of today's features, and the
    header, the columns, the map's column, the details' column, a phone's top bar and its sheet's body hold what they
    held before the seams."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            for context, first, selected, details in ((DESKTOP, DESKTOP_FIRST, DESKTOP_SELECTED, ".c-col-dbody .vl-details"),
                                                      (PHONE, PHONE_FIRST, PHONE_SELECTED, ".u-sheet-body .vl-details")):
                page = _open(browser, f"{site}#run={BIG}", context)
                _state(page)
                _holds(page, first)
                _state(page, "view.setLevel('spots'); view.select(view.order[0]);")
                page.wait_for_selector(details, timeout=WAIT)
                _holds(page, selected)
                assert page.errors == []
                page.context.close()
        finally:
            browser.close()


def test_today_keeps_its_features(site):
    """Today's page on a desktop and on a phone: the run's actions at first (after the header's title; on a phone
    beside the pill), and a selected line's profile (the card over the map on a desktop, the dock in the sheet on a
    phone) with its chart."""
    from playwright.sync_api import sync_playwright
    select = "() => { const m = window.FINDALINE_RESULT.model; m.select(m.rows[0].group); }"
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            for context, top, profile in (
                    (DESKTOP, {".c-result-top": ["c-back", "c-run-title", "u-grow", "r-actions"]},
                     ".c-col-map > .r-card .fal-profile-chart"),
                    (PHONE, {".c-phone-top": ["c-pill", "r-actions"]}, ".u-sheet-body .r-dock .fal-profile-chart")):
                page = _open(browser, f"{site}#run={BIG}", context, flag=False)
                page.wait_for_function("() => !!window.FINDALINE_RESULT", timeout=WAIT)
                page.wait_for_selector(".r-actions", timeout=WAIT)
                assert page.evaluate("() => !!window.FINDALINE_VIEW") is False
                assert {selector: _children(page, selector, NAMES) for selector in top} == top
                page.evaluate(select)
                page.wait_for_selector(profile, timeout=WAIT)
                assert page.errors == []
                page.context.close()
        finally:
            browser.close()
