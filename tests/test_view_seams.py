"""The result view's seams of step 3c (viewer/src/result/view/SpotColumns.tsx, SpotPanels.tsx) as the frame fills
them: the run's actions in the header and in a phone's pill, the selected line's profile in a card over the desktop's
map (the measured profile's dock in a phone's sheet comes only with a measured line); the slots of the details
(the selected line's actions, a phone's dock: SpotDetails.tsx) as view-3c drew them; the elements around the slots
are the ones they were. Today's page still shows its run's actions and a selected line's profile (the card on a
desktop, the dock in a phone's sheet). Playwright's Edge over the app's server, offline, on the result view's clip
run (clip_runs.view_clip). Every wait is an event with a deadline. Run from PowerShell
(.claude/rules/browser-tests.md)."""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_shell_c import BIG  # noqa: E402
from test_shell_c_view_map import DESKTOP, PHONE, WAIT, _open, _state, site, view_clip  # noqa: E402,F401
from test_web import EDGE, _playwright  # noqa: E402

pytestmark = pytest.mark.skipif(not os.path.exists(EDGE) or not _playwright(),
                                reason="needs Microsoft Edge and Playwright (group ui)")

# What today's page draws of the features step 3c joins into the view: the run's actions, a line's profile (its card,
# its dock, its chart) and the line's buttons in today's details
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
         "r-actions", "r-card", "u-grow")
# The view's elements that hold the slots and those around them, with their children: per device, at first and with a
# spot selected. The frame's own (step 3c's frame): the run's actions after the header's grow (desktop) and the
# pill's name (phone), the profile's card last in the map's column with a selection (desktop). The details' own as
# view-3c drew them (their slots are SpotDetails.tsx's)
FRAME = {
    "desktop first": {".v-result": ["c-result-top", "c-cols"], ".c-result-top": ["c-back", "c-run-title", "u-grow", "r-actions"],
                      ".c-cols": ["c-col-list", "c-col-map", "c-col-details"], ".c-col-map": ["c-leaflet", "v-switch", "v-foot"]},
    "desktop selected": {".c-col-map": ["c-leaflet", "v-switch", "v-foot", "r-card"]},
    "phone first": {".v-result": ["c-col-map", "c-phone-top", "u-sheet"], ".c-phone-top": ["c-pill"],
                    ".c-pill": ["c-back", "c-pill-name", "r-actions"], ".c-col-map": ["c-leaflet", "v-switch", "v-foot"]},
    "phone selected": {},
}
DETAILS = {
    "desktop first": {".c-col-dbody": ["vl-empty"]},
    "desktop selected": {".c-col-dbody": ["vl-details"]},
    "phone first": {".u-sheet-body": ["vl-list"]},
    "phone selected": {".u-sheet-body": ["vl-details", "vl-list"]},
}
# Which of today's features (TODAY) each state shows: the frame's, then the details' (step 3c's details: the line's
# copy and 3D buttons under "Stands for", a phone's dock of the line under the tiles; B2's for-others)
FRAME_TODAY = {"desktop first": [".r-actions"], "desktop selected": [".r-actions", ".r-card", ".r-dock", ".fal-profile-chart"],
               "phone first": [".r-actions"], "phone selected": [".r-actions"]}
DETAILS_TODAY = {"desktop first": [], "desktop selected": [".r-copy", ".r-view3d"], "phone first": [],
                 "phone selected": [".r-dock", ".fal-profile-chart", ".r-copy", ".r-view3d"]}


def _holds(page, state: str):
    """Every element of the state's lists has the children they name (a later list of the same element wins: the
    first state's lists hold in the second unless it names them again), and the page shows exactly the state's
    features of today's page."""
    device = state.split()[0]
    want = {**FRAME[f"{device} first"], **DETAILS[f"{device} first"], **FRAME[state], **DETAILS[state]}
    assert {selector: _children(page, selector, NAMES) for selector in want} == want, state
    assert _present(page) == sorted(set(FRAME_TODAY[state] + DETAILS_TODAY[state]), key=TODAY.index), state


def test_view_slots_hold_their_features(site):
    """The view on a desktop and on a phone, at first and with a spot selected: the header, the columns, the map's
    column, the details' column, a phone's top bar and its sheet's body hold the frame's features of step 3c (the run's
    actions, the profile's card) and otherwise what they held before the seams."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            for context, device, details in ((DESKTOP, "desktop", ".c-col-dbody .vl-details"),
                                             (PHONE, "phone", ".u-sheet-body .vl-details")):
                page = _open(browser, f"{site}#run={BIG}", context)
                _state(page)
                _holds(page, f"{device} first")
                _state(page, "view.setLevel('spots'); view.select(view.order[0]);")
                page.wait_for_selector(details, timeout=WAIT)
                page.wait_for_selector(".c-col-map > .r-card .fal-profile-chart" if device == "desktop"
                                       else ".u-sheet-body .vl-details .r-dock .fal-profile-chart", timeout=WAIT)
                _holds(page, f"{device} selected")
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
