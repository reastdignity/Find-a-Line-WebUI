"""The pages around a result in the result view (?view=b; step 3d of docs/line-volume/spec-view.md part B: the view
loses nothing of today's result page): today's checks of the access mark's page parts, Download, a share link's page,
a run's own map.html and the public site's people, ported to the view where the view's own tests lacked them
(the parity list: local/line-volume-6/C2/parity.md, one row per check, each assertion here names its row). Today's
tests stay as they are (tests/test_access_page.py, test_shell_c_download.py, test_store_share.py, test_disk_notice.py,
test_web.py::test_run_map*, test_public.py::test_signed_in_app_and_shared_map_in_edge); their helpers and answers are
imported, not copied. Playwright's browsers (Edge; WebKit and Chromium as the two phones) over the app's server or
the public site on a thread, offline, on the result view's clip run (clip_runs.view_clip). Every wait is an event with
a deadline. Run from PowerShell (.claude/rules/browser-tests.md)."""

import json
import os
import re
import socket
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

pytest.importorskip("httpx2")  # test_public's fake providers

from test_public import RUN_A, RUN_B, account_settings, copy_run, session_of  # noqa: E402,F401
from test_shell_c import BIG, HELPERS as SCRIPT_HELPERS, copy_clip, stub_page  # noqa: E402,F401
from test_shell_c_download import (BUSY, DOWNLOAD, ERROR, FAILED, FAILURES, IDLE_ROWS, INTRO_SEEN,  # noqa: E402
                                   MARK_EXPORTS, NO_RING, NO_WORKER, NO_WORKER_TEXT, PREPARING, PREPARING_LABEL, ROW,
                                   SETTLED, STATE, WHAT, Export, _browser_of, _escape, _file_routes, _listening, _menu,
                                   _press, _rows)
from test_shell_c_view_map import DESKTOP, FLAG, HELPERS, PHONE, WAIT, WORDS, _open, _state, view_clip  # noqa: E402,F401
from test_web import CREDITS_HEAD, CSP_STUB, EDGE, TOKEN, XSS_NAME, _playwright, _server, store_with  # noqa: E402

pytestmark = pytest.mark.skipif(not os.path.exists(EDGE) or not _playwright(),
                                reason="needs Microsoft Edge and Playwright (group ui)")

OTHER = "2026-10-30_120000_Other_00000000000000e5"     # the clip's run again: a second run the view can open
TAGGED = "2026-10-31_090000_Tag_00000000000000e6"      # the clip's run named like an HTML tag (Compare's list)
CREDITED = "2026-10-31_100000_Credited_00000000000000e7"  # the clip's run with credits of markup (test_web's)

# Today's Download state (test_shell_c_download.STATE) read from the view's model, not today's
STATE_VIEW = STATE.replace("result = window.FINDALINE_RESULT;", "result = window.FINDALINE_VIEW && window.FINDALINE_VIEW.view;")
assert STATE_VIEW != STATE and "result.model.data.fromStore" in STATE_VIEW
FIELD = ".vl-tree .r-sort"  # a field the desktop view always has: "All spots"' sort
# Where the attention is (test_shell_c_download.ATTENTION, with the view's run and field)
ATTENTION_VIEW = """() => { const at = document.activeElement, pop = at && at.closest('.r-pop');
  const button = document.querySelector(DOWNLOAD);
  return {tag: at && at.tagName, pop: pop && pop.getAttribute('aria-label'),
          pops: [...document.querySelectorAll('.r-pop')].map((p) => p.getAttribute('aria-label')),
          onDownload: !!button && at === button, onField: !!at && at.matches(FIELD),
          kept: button && (button.dataset.kept ?? null), run: window.FINDALINE_VIEW?.view.model.runId ?? null,
          phone: !!document.querySelector('.c-result-phone'), bars: document.querySelectorAll('.r-actions').length}; }"""
ATTENTION_VIEW = ATTENTION_VIEW.replace("DOWNLOAD", json.dumps(DOWNLOAD)).replace("FIELD", json.dumps(FIELD))


def _errors(page) -> list:
    return [e for e in page.errors if not e.startswith("ResizeObserver loop")]


@pytest.fixture
def pages(tmp_path, view_clip):
    """A data folder with the clip's run (BIG) and the same run again (OTHER), served by the local app; yields the
    app page's address (its stubs: test_shell_c.C_STUBS, the CSP's violations counted), the root and the folder."""
    folder = tmp_path / "data"
    copy_clip(view_clip, folder, BIG, "Clip")
    copy_clip(view_clip, folder, OTHER, "Other run")
    page_path = stub_page(folder, "paritypages")
    with _server(folder) as port:
        root = f"http://127.0.0.1:{port}"
        yield {"app": f"{root}/{page_path}?ui=c", "root": root, "data": folder}


# ---- D: Download in the view (RunActions.tsx, shared; today's: tests/test_shell_c_download.py) ----------------------

def _dl(browser, url: str, prepare=None, **context):
    """The view of a run at `url` (its Download button drawn) and the export requests it sent (heard from before the
    page loads); `prepare(page)` sets the page's routes or scripts first."""
    page = browser.new_page(**context)
    page.add_init_script(INTRO_SEEN + FLAG + HELPERS)
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)[:300]))
    asked = []
    page.on("request", lambda request: "/export" in request.url and asked.append(request.url))
    if prepare:
        prepare(page)
    page.goto(url)
    page.wait_for_function("() => !!window.FINDALINE_VIEW", timeout=WAIT)
    page.wait_for_selector(DOWNLOAD, timeout=WAIT)
    return page, asked


def _state_of(page) -> dict:
    return page.evaluate(STATE_VIEW)


def test_download_request_and_the_preparing_state(pages):
    """D1-D4 (today's test_request_and_the_preparing_state), in the view's header (desktop) and its phone's pill: the
    one Download button last of the run's actions, its menu's two rows; a press sends one POST /api/runs/<id>/export
    with the format and the page's token; while it waits the row prepares, the other is off, and with the menu closed
    the button holds the ring and the waiting's name; an answer that never comes ends it with one red line."""
    from playwright.sync_api import sync_playwright
    r = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            for name, context in (("desktop", DESKTOP), ("phone", PHONE)):
                page, asked = _dl(browser, f"{pages['app']}#run={BIG}", **context)
                export = Export(page)
                found = r[name] = {"start": _state_of(page), "bars": page.evaluate("() => document.querySelectorAll('.r-actions').length"),
                                   "where": page.evaluate("() => !!document.querySelector('.c-result-top .r-actions, .c-pill .r-actions')")}
                _menu(page)
                found["menu"] = _state_of(page)
                _press(page, 0)
                found["waiting"] = _state_of(page)
                page.keyboard.press("Escape")
                page.wait_for_selector(".r-pop", state="detached", timeout=WAIT)
                page.wait_for_selector(DOWNLOAD + " .r-spin", state="attached", timeout=WAIT)
                found["closed"] = _state_of(page)
                _menu(page)
                page.wait_for_selector(BUSY, timeout=WAIT)
                found["reopened"] = _state_of(page)
                export.release(None)
                page.wait_for_selector(ERROR, timeout=WAIT)
                page.wait_for_function(SETTLED, timeout=WAIT)
                found["ended"] = _state_of(page)
                found["requests"], found["asked"] = export.requests, asked
                found["csp"], found["errors"] = page.evaluate("() => window.CSP_VIOLATIONS || []"), _errors(page)
                page.context.close()
        finally:
            browser.close()
    for name, found in r.items():
        assert found["bars"] == 1 and found["where"], (name, "D1: one bar of the run's actions, in the header or the pill")
        idle = {"text": "Download", "label": None} if name == "desktop" else {"text": "", "label": "Download"}
        for step in ("start", "menu", "ended"):
            button = found[step]["button"]
            assert {k: button[k] for k in idle} == idle and button["icon"] and not button["ring"], ("D1", name, step, button)
        assert found["start"]["fromStore"] is True and not found["start"]["open"], ("D1", name, found["start"])
        assert [a for a in found["start"]["actions"] if a[0] or a[1]][-1] in (["Download", None], ["", "Download"]), ("D1 last", name)
        assert _rows(found["menu"]) == IDLE_ROWS and found["menu"]["links"] == [], ("D1", name, found["menu"])
        assert found["menu"]["button"]["expanded"] == "true" and found["menu"]["errors"] == [], ("D1", name)
        for step in ("waiting", "reopened"):
            got = found[step]
            assert _rows(got) == [["CSV", PREPARING, True, False, True, False],
                                  ["GeoJSON", WHAT[1], False, True, False, True]], ("D3", name, step, got)
            assert got["open"] and got["allErrors"] == 0, ("D3", name, step, got)
            assert got["button"]["ring"] and got["button"]["label"] == PREPARING_LABEL, ("D3", name, step, got)
        closed = found["closed"]
        assert not closed["open"] and closed["pops"] == 0 and closed["rows"] == [], ("D3", name, closed)
        assert closed["button"]["ring"] and not closed["button"]["icon"], ("D3", name, closed)
        assert closed["button"]["label"] == PREPARING_LABEL == "Download: preparing the file", ("D3", name, closed)
        assert closed["button"]["text"] == idle["text"] and closed["button"]["expanded"] == "false", ("D3", name, closed)
        ended = found["ended"]
        assert ended["open"] and ended["errors"] == [FAILED] and ended["allErrors"] == 1, ("D4", name, ended)
        assert _rows(ended) == IDLE_ROWS, ("D4", name, ended)
        assert found["requests"] == [{"method": "POST", "path": f"/api/runs/{BIG}/export",
                                      "body": json.dumps({"format": "csv"}, separators=(",", ":")),
                                      "token": TOKEN}], ("D2", name, found["requests"])
        assert TOKEN and len(found["asked"]) == 1, ("D2", name, found["asked"])
        assert found["csp"] == [] and found["errors"] == [], ("X1/X2", name, found["csp"], found["errors"])


@pytest.mark.parametrize("kind", ["edge", "iphone", "pixel"])
def test_download_ready_file_is_saved(pages, kind):
    """D5 (today's test_ready_file_is_saved): the answer {"url": the file's address}, released after the press
    returned, makes the browser save that address (Edge on a desktop, WebKit as an iPhone 13, Chromium as a Pixel 7);
    the page stays, the rows idle, no red line, the menu still open; a second press (GeoJSON) asks and saves again."""
    from playwright.sync_api import sync_playwright
    files = [f"/api/runs/{BIG}/export/{'a' * 22}.csv", f"/api/runs/{BIG}/export/{'b' * 22}.geojson"]
    r = {"saved": [], "after": []}
    with sync_playwright() as p:
        browser, options = _browser_of(p, kind)
        try:
            page, asked = _dl(browser, f"{pages['app']}#run={BIG}", _file_routes, **options)
            export = Export(page)
            r["start"] = _state_of(page)
            _menu(page)
            for row, path in enumerate(files):
                _press(page, row)
                r.setdefault("waiting", _state_of(page))
                with page.expect_download(timeout=WAIT) as download:
                    export.release((200, {"url": path}))
                r["saved"].append(download.value.url)
                page.wait_for_function(SETTLED, timeout=WAIT)
                r["after"].append(_state_of(page))
            r["requests"], r["location"] = export.requests, page.evaluate("() => location.pathname + location.hash")
            r["view"] = page.evaluate("() => !!window.FINDALINE_VIEW && !window.FINDALINE_RESULT")
        finally:
            browser.close()
    assert r["start"]["fromStore"] is True and r["view"], ("D5", r["start"])
    assert [row[2:5] for row in _rows(r["waiting"])] == [[True, False, True], [False, True, False]], ("D5", r["waiting"])
    assert len(r["saved"]) == 2 and all(saved.endswith(path) for saved, path in zip(r["saved"], files)), ("D5", r["saved"])
    for after in r["after"]:
        assert _rows(after) == IDLE_ROWS and after["allErrors"] == 0 and after["open"], ("D5", kind, after)
        assert not after["button"]["ring"] and after["button"]["icon"], ("D5", kind, after)
    assert [(q["method"], q["path"], json.loads(q["body"]), q["token"]) for q in r["requests"]] == [
        ("POST", f"/api/runs/{BIG}/export", {"format": "csv"}, TOKEN),
        ("POST", f"/api/runs/{BIG}/export", {"format": "geojson"}, TOKEN)], ("D5", r["requests"])
    assert r["location"].endswith(f"#run={BIG}"), ("D5: the page stayed", r["location"])


def _empty_map_point(page):
    """A point of the view's map a press reaches (no control, no menu, no line within reach), in the viewport."""
    return page.evaluate("""() => { const {map} = window.FINDALINE_VIEW, box = window.FINDALINE_MAP.getContainer().getBoundingClientRect();
      const f = T.free(), controls = T.controls();
      for (let y = f[3] - 60; y > f[1] + 60; y -= 17) for (let x = f[0] + 60; x < f[2] - 60; x += 23) { const vx = x + box.left, vy = y + box.top;
        if (controls.some((c) => vx > c.left - 24 && vx < c.right + 24 && vy > c.top - 24 && vy < c.bottom + 24)) continue;
        const hit = document.elementFromPoint(vx, vy);
        if (!hit || !hit.closest('.leaflet-container') || hit.closest('.r-pop, .leaflet-control, [data-map-control]')) continue;
        if (map.pickAt(x, y, false).length === 0) return {x: vx, y: vy}; }
      return null; }""")


def test_download_failures_and_the_closed_menu(pages):
    """D6, D13, D7 on one desktop page of the view (today's test_failure_is_one_line_by_the_answer,
    test_only_the_runs_own_export_address_is_saved, test_failure_opens_a_closed_menu_again): every failed answer is one
    red line worded by the answer and the rows work again at once; a 200 answer whose address is not this run's own
    export is a failure and saves nothing; a failure while the menu is closed (Escape; a press on the map) opens it
    again with the line, and closing takes the line away."""
    from playwright.sync_api import sync_playwright
    r, downloads = {}, []
    answers = [("no url", {}), ("another site", {"url": "https://example.org/x.csv"}),
               ("another run", {"url": f"/api/runs/{OTHER}/export/{'a' * 22}.csv"}),
               ("a longer id", {"url": f"/api/runs/{BIG}x/export/{'a' * 22}.csv"})]
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page, asked = _dl(browser, f"{pages['app']}#run={BIG}", _file_routes, **DESKTOP)
            page.on("download", lambda download: downloads.append(download.url))
            export = Export(page)
            _menu(page)
            for k, (name, answer, _) in enumerate(FAILURES):
                _press(page, k % 2)
                waiting = _state_of(page)
                export.release(answer)
                page.wait_for_selector(ERROR, timeout=WAIT)
                page.wait_for_function(SETTLED, timeout=WAIT)
                r[name] = [waiting, _state_of(page)]
            for name, body in answers:
                _press(page, 0)
                export.release((200, body))
                page.wait_for_selector(ERROR, timeout=WAIT)
                page.wait_for_function(SETTLED, timeout=WAIT)
                r["own " + name] = [_state_of(page), list(downloads)]
            r["sent"] = len(export.requests)
            for way in ("escape", "map"):
                _menu(page)
                _press(page, 1)
                if way == "escape":
                    page.keyboard.press("Escape")
                else:
                    at = _empty_map_point(page)
                    assert at, "D7: no empty point of the map to press"
                    page.mouse.click(at["x"], at["y"])
                page.wait_for_selector(".r-pop", state="detached", timeout=WAIT)
                page.wait_for_selector(DOWNLOAD + " .r-spin", state="attached", timeout=WAIT)
                closed = _state_of(page)
                export.release(NO_WORKER)
                page.wait_for_selector(".r-pop " + ERROR, timeout=WAIT)
                page.wait_for_function(SETTLED, timeout=WAIT)
                failed = _state_of(page)
                _listening(page)
                _escape(page)
                _menu(page)
                again = _state_of(page)
                _escape(page)
                r[way] = [closed, failed, again]
            r["requests"], r["asked"] = export.requests, asked
            r["where"] = page.evaluate("() => location.pathname + location.hash")
            r["csp"], r["errors"] = page.evaluate("() => window.CSP_VIOLATIONS || []"), _errors(page)
        finally:
            browser.close()
    for k, (name, answer, text) in enumerate(FAILURES):
        waiting, ended = r[name]
        assert waiting["allErrors"] == 0 and waiting["rows"][k % 2]["busy"], ("D6", name, waiting)
        assert waiting["rows"][1 - k % 2]["disabled"], ("D6", name, waiting)
        assert ended["errors"] == [text] and ended["allErrors"] == 1, ("D6", name, ended["errors"], text)
        assert _rows(ended) == IDLE_ROWS and ended["open"], ("D6", name, ended)
        assert not ended["button"]["ring"] and ended["button"]["label"] is None, ("D6", name, ended)
    assert r[FAILURES[4][0]][1]["errors"] == ["The search service is busy: no answer in 150 s. Try again later."], "D6"
    for name, _ in answers:
        found, saved = r["own " + name]
        assert found["errors"] == [FAILED] and found["allErrors"] == 1 and _rows(found) == IDLE_ROWS, ("D13", name, found)
        assert found["open"] and not found["button"]["ring"] and saved == [], ("D13", name, found, saved)
    assert downloads == [] and r["sent"] == len(FAILURES) + len(answers), ("D13", downloads, r["sent"])
    assert r["where"].endswith(f"#run={BIG}"), ("D13: the page stayed", r["where"])
    for way in ("escape", "map"):
        closed, failed, again = r[way]
        assert not closed["open"] and closed["button"]["ring"] and closed["button"]["label"] == PREPARING_LABEL, ("D7", way, closed)
        assert failed["open"] and failed["errors"] == [NO_WORKER_TEXT] and _rows(failed) == IDLE_ROWS, ("D7", way, failed)
        assert not failed["button"]["ring"] and failed["button"]["expanded"] == "true", ("D7", way, failed)
        assert again["open"] and again["allErrors"] == 0 and _rows(again) == IDLE_ROWS, ("D7", way, again)
    formats = [json.loads(q["body"])["format"] for q in r["requests"]]
    assert formats == [("csv", "geojson")[k % 2] for k in range(len(FAILURES))] + ["csv"] * len(answers) + ["geojson"] * 2, ("D6", formats)
    assert all(q["method"] == "POST" and q["token"] == TOKEN for q in r["requests"]) and len(r["asked"]) == len(r["requests"]), "D6"
    assert r["csp"] == [] and r["errors"] == [], ("X1/X2", r["csp"], r["errors"])


def test_download_wait_across_the_layout_switch(pages):
    """D9 and D14 (today's test_wait_goes_on_across_the_layout_switch, test_seen_line_goes_with_a_layout_switch): CSV
    pressed in the desktop view, then the window narrowed to 390 px while the answer waits (the view draws its phone:
    the Download button in the pill): that button holds the ring and the waiting's name, its menu shows CSV preparing,
    a press on the busy row sends nothing; the menu closed, a failure opens it by itself with the red line. Then a
    failure's line seen in the desktop's menu goes with the switch: the phone's menu opens without it."""
    from playwright.sync_api import sync_playwright
    r = {}
    phone_button = ".c-result-phone .c-pill " + DOWNLOAD
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page, asked = _dl(browser, f"{pages['app']}#run={BIG}", **DESKTOP)
            export = Export(page)
            _menu(page)
            _press(page, 0)
            r["wide"] = [_state_of(page), page.evaluate(ATTENTION_VIEW)]
            page.set_viewport_size({"width": 390, "height": 844})
            page.wait_for_selector(phone_button + " .r-spin", state="attached", timeout=WAIT)
            r["narrow"] = [_state_of(page), page.evaluate(ATTENTION_VIEW)]
            _menu(page)
            page.wait_for_selector(BUSY, timeout=WAIT)
            r["menu"] = _state_of(page)
            page.click(ROW % 0)
            r["pressed"], r["sent"] = _state_of(page), len(export.requests)
            _escape(page)
            r["closed"] = _state_of(page)
            export.release(NO_WORKER)
            page.wait_for_selector(".r-pop " + ERROR, timeout=WAIT)
            page.wait_for_function(SETTLED, timeout=WAIT)
            r["failed"] = _state_of(page)
            r["requests"] = export.requests
            r["errors"] = _errors(page)
            page.context.close()
            # D14: a line seen in the desktop's menu
            page, asked = _dl(browser, f"{pages['app']}#run={BIG}", **DESKTOP)
            export = Export(page)
            _menu(page)
            _press(page, 0)
            export.release(NO_WORKER)
            page.wait_for_selector(".r-pop " + ERROR, timeout=WAIT)
            page.wait_for_function(SETTLED, timeout=WAIT)
            r["shown"] = _state_of(page)
            page.set_viewport_size({"width": 390, "height": 844})
            page.wait_for_selector(phone_button, state="attached", timeout=WAIT)
            r["seen narrow"] = _state_of(page)
            _menu(page)
            r["seen menu"], r["seen sent"] = _state_of(page), len(export.requests)
            r["errors"] += _errors(page)
        finally:
            browser.close()
    preparing = [["CSV", PREPARING, True, False, True, False], ["GeoJSON", WHAT[1], False, True, False, True]]
    assert _rows(r["wide"][0]) == preparing and not r["wide"][1]["phone"], ("D9", r["wide"])
    narrow, attention = r["narrow"]
    assert attention["phone"] and attention["bars"] == 1 and narrow["button"]["ring"] and not narrow["button"]["icon"], ("D9", r["narrow"])
    assert narrow["button"]["label"] == PREPARING_LABEL and narrow["button"]["text"] == "", ("D9", narrow)
    for step in ("menu", "pressed"):
        assert _rows(r[step]) == preparing and r[step]["open"] and r[step]["allErrors"] == 0, ("D9", step, r[step])
    assert r["sent"] == 1, ("D9: the busy row asks nothing again", r["requests"])
    assert not r["closed"]["open"] and r["closed"]["button"]["ring"] and r["closed"]["button"]["label"] == PREPARING_LABEL, ("D9", r["closed"])
    failed = r["failed"]
    assert failed["open"] and failed["errors"] == [NO_WORKER_TEXT] and _rows(failed) == IDLE_ROWS, ("D9", failed)
    assert not failed["button"]["ring"] and failed["button"]["icon"] and failed["button"]["label"] == "Download", ("D9", failed)
    assert [json.loads(q["body"]) for q in r["requests"]] == [{"format": "csv"}], ("D9", r["requests"])
    assert r["shown"]["open"] and r["shown"]["errors"] == [NO_WORKER_TEXT], ("D14", r["shown"])
    assert not r["seen narrow"]["open"] and not r["seen narrow"]["button"]["ring"], ("D14", r["seen narrow"])
    found = r["seen menu"]
    assert found["open"] and found["errors"] == [] and found["allErrors"] == 0, ("D14", found)
    assert _rows(found) == IDLE_ROWS and not found["button"]["ring"] and r["seen sent"] == 1, ("D14", found, r["seen sent"])
    assert r["errors"] == [], ("X2", r["errors"])


def _go_view(page, run_id: str):
    """Another run opened by the hash in the view: its view drawn with its Download button."""
    page.evaluate("(id) => { location.hash = 'run=' + id; }", run_id)
    page.wait_for_function("([id, button]) => { const v = window.FINDALINE_VIEW; return !!v && v.view.model.runId === id "
                           "&& !!document.querySelector(button); }", arg=[run_id, DOWNLOAD], timeout=WAIT)


def _marked(page):
    """The file routes and the count of export answers the page has dealt with (test_shell_c_download's _marked)."""
    _file_routes(page)
    page.add_init_script(MARK_EXPORTS)


def test_download_wait_across_a_run_change(pages):
    """D10 (today's test_wait_goes_on_across_a_run_change): a file asked for on run A in the view, then run B opened
    by the hash while the answer waits: B's Download has no ring and idle rows; A's file is still saved and B's page
    shows nothing new. A failure while B is on the page: nothing on B's page; back on A its button has no ring and
    did not open, its menu shows the red line, which goes when the menu is closed."""
    from playwright.sync_api import sync_playwright
    path = f"/api/runs/{BIG}/export/{'a' * 22}.csv"
    r = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            url = f"{pages['app']}#run={BIG}"
            page, asked = _dl(browser, url, _file_routes, **DESKTOP)
            export = Export(page)
            _menu(page)
            _press(page, 0)
            _go_view(page, OTHER)
            r["other"] = _state_of(page)
            _menu(page)
            r["other menu"] = _state_of(page)
            with page.expect_download(timeout=WAIT) as download:
                export.release((200, {"url": path}))
            r["saved"] = download.value.url
            r["other after"] = [_state_of(page), page.evaluate(ATTENTION_VIEW)]
            r["requests a"] = export.requests
            r["errors"] = _errors(page)
            page.context.close()
            page, asked = _dl(browser, url, _marked, **DESKTOP)
            export = Export(page)
            _menu(page)
            _press(page, 1)
            _go_view(page, OTHER)
            before = page.evaluate("() => window.__exports")
            export.release(NO_WORKER)
            page.wait_for_function("(before) => window.__exports > before", arg=before, timeout=WAIT)
            r["other failed"] = [_state_of(page), page.evaluate(ATTENTION_VIEW)]
            _go_view(page, BIG)
            page.wait_for_function(NO_RING, timeout=WAIT)
            r["back"] = _state_of(page)
            _menu(page)
            r["back menu"] = _state_of(page)
            _escape(page)
            _menu(page)
            r["again"] = _state_of(page)
            r["requests b"] = export.requests
            r["errors"] += _errors(page)
        finally:
            browser.close()
    other = r["other"]
    assert other["fromStore"] is True and not other["button"]["ring"] and other["button"]["icon"], ("D10", other)
    assert other["button"]["label"] is None and not other["open"], ("D10", other)
    assert _rows(r["other menu"]) == IDLE_ROWS and r["other menu"]["allErrors"] == 0, ("D10", r["other menu"])
    assert r["saved"].endswith(path), ("D10", r["saved"])
    after, attention = r["other after"]
    assert attention["run"] == OTHER and _rows(after) == IDLE_ROWS and after["allErrors"] == 0, ("D10", r["other after"])
    assert not after["button"]["ring"] and attention["pops"] == ["Download"], ("D10", r["other after"])
    assert [q["path"] for q in r["requests a"]] == [f"/api/runs/{BIG}/export"], ("D10", r["requests a"])
    failed, attention = r["other failed"]
    assert attention["run"] == OTHER and attention["pops"] == [] and failed["allErrors"] == 0, ("D10", r["other failed"])
    assert not failed["button"]["ring"] and not failed["open"], ("D10", failed)
    back = r["back"]
    assert not back["button"]["ring"] and not back["open"] and back["pops"] == 0, ("D10", back)
    assert r["back menu"]["errors"] == [NO_WORKER_TEXT] and _rows(r["back menu"]) == IDLE_ROWS, ("D10", r["back menu"])
    assert r["again"]["open"] and r["again"]["allErrors"] == 0 and _rows(r["again"]) == IDLE_ROWS, ("D10", r["again"])
    assert [(q["path"], json.loads(q["body"])) for q in r["requests b"]] == \
        [(f"/api/runs/{BIG}/export", {"format": "geojson"})], ("D10", r["requests b"])
    assert r["errors"] == [], ("X2", r["errors"])


def test_download_failure_waits_for_the_attention(pages):
    """D11 (today's test_failure_waits_while_something_else_has_the_attention): a failure while the Download menu is
    closed and Compare's menu is open, or the focus is in a field of the view ("All spots"' sort), opens nothing and
    moves nothing; the button loses its ring; its menu opened afterwards shows the red line (gone once closed)."""
    from playwright.sync_api import sync_playwright
    r = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            for way in ("compare", "field"):
                page, asked = _dl(browser, f"{pages['app']}#run={BIG}", **DESKTOP)
                export = Export(page)
                _menu(page)
                _press(page, 0)
                _escape(page)
                if way == "compare":
                    page.click(".c-result-top .r-actions button:has-text('Compare')")
                    page.wait_for_function("""() => { const p = document.querySelector('.r-pop[aria-label="Compare with other runs"]');
                        return !!p && p.contains(document.activeElement); }""", timeout=WAIT)
                else:
                    page.focus(FIELD, timeout=WAIT)
                    page.wait_for_function("(field) => !!document.activeElement && document.activeElement.matches(field)",
                                           arg=FIELD, timeout=WAIT)
                before = [_state_of(page), page.evaluate(ATTENTION_VIEW)]
                export.release(NO_WORKER)
                page.wait_for_function(NO_RING, timeout=WAIT)
                after = [_state_of(page), page.evaluate(ATTENTION_VIEW)]
                _menu(page)
                opened = [_state_of(page), page.evaluate(ATTENTION_VIEW)]
                _escape(page)
                _menu(page)
                r[way] = [before, after, opened, _state_of(page), len(export.requests), _errors(page)]
                page.context.close()
        finally:
            browser.close()
    for way, (before, after, opened, again, sent, errors) in r.items():
        assert before[0]["button"]["ring"] and not before[0]["open"], ("D11", way, before)
        assert not after[0]["button"]["ring"] and after[0]["button"]["icon"] and not after[0]["open"], ("D11", way, after)
        assert after[0]["allErrors"] == 0 and after[1] == before[1], ("D11: nothing moved", way, before[1], after[1])
        assert opened[1]["pops"] == ["Download"] and opened[0]["errors"] == [NO_WORKER_TEXT], ("D11", way, opened)
        assert _rows(opened[0]) == IDLE_ROWS and again["allErrors"] == 0 and sent == 1, ("D11", way, opened, again, sent)
        assert errors == [], ("X2", way, errors)
    attention = r["compare"][1][1]
    assert attention["pops"] == ["Compare with other runs"] and attention["pop"] == "Compare with other runs", ("D11", attention)
    attention = r["field"][1][1]
    assert attention["pops"] == [] and attention["onField"] and attention["tag"] == "SELECT", ("D11", attention)


def test_download_phone_button_keeps_the_focus(pages):
    """D12 (today's test_phone_button_keeps_the_focus_when_the_file_is_ready): the view on a phone of 390 px, CSV
    pressed, the menu closed by Escape (the focus on the pill's Download button, which holds the ring); the file
    ready: saved, and the focus still on the same button, now with its icon, no ring and the name "Download"."""
    from playwright.sync_api import sync_playwright
    path = f"/api/runs/{BIG}/export/{'a' * 22}.csv"
    r = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page, asked = _dl(browser, f"{pages['app']}#run={BIG}", _file_routes, **PHONE)
            export = Export(page)
            _menu(page)
            _press(page, 0)
            _escape(page)
            page.wait_for_function("(button) => document.activeElement === document.querySelector(button)", arg=DOWNLOAD,
                                   timeout=WAIT)
            page.evaluate("(button) => { document.querySelector(button).dataset.kept = '1'; }", DOWNLOAD)
            r["waiting"] = [_state_of(page), page.evaluate(ATTENTION_VIEW)]
            with page.expect_download(timeout=WAIT) as download:
                export.release((200, {"url": path}))
            r["saved"] = download.value.url
            page.wait_for_function(NO_RING, timeout=WAIT)
            r["ready"] = [_state_of(page), page.evaluate(ATTENTION_VIEW)]
            r["pill"] = page.evaluate("(button) => !!document.querySelector(button).closest('.c-pill')", DOWNLOAD)
            r["errors"] = _errors(page)
        finally:
            browser.close()
    waiting, attention = r["waiting"]
    assert r["pill"] and attention["phone"] and attention["onDownload"] and attention["kept"] == "1", ("D12", r["waiting"])
    assert waiting["button"]["ring"] and waiting["button"]["label"] == PREPARING_LABEL and not waiting["open"], ("D12", waiting)
    assert r["saved"].endswith(path), ("D12", r["saved"])
    ready, attention = r["ready"]
    assert attention["onDownload"] and attention["kept"] == "1" and attention["tag"] == "BUTTON", ("D12", r["ready"])
    assert attention["pops"] == [] and ready["allErrors"] == 0, ("D12", r["ready"])
    button = ready["button"]
    assert button["icon"] and not button["ring"] and button["label"] == "Download" and button["text"] == "", ("D12", button)
    assert r["errors"] == [], ("X2", r["errors"])


# ---- A: the access mark's page parts (today's: tests/test_access_page.py) -------------------------------------------

def _kept_list(width: int) -> str:
    """A kept layout (localStorage "findaline.layout", the view's and today's) with the list `width` px wide
    (test_access_page._layout's)."""
    return json.dumps({"v": 1, "list": {"w": width, "open": True}, "details": {"w": 380, "open": True},
                       "profile": {"h": 260, "folded": False, "l": 12, "r": 12}})


# The view's lists as drawn at a kept width: the list's width, its rows' cells of the mark (the dots inside the cell)
# and whether a row's parts overlap or a value is cut (its text wider than its cell)
NARROW = """() => { const list = document.querySelector('.c-col-list'), c = window.FINDALINE_VIEW.view.model.data.columns;
  const parts = (b) => [...b.children].filter((e) => !e.classList.contains('u-sr') && e.getClientRects().length && !e.classList.contains('vl-over-words'));
  const overlap = (a, b) => a.left < b.right - 0.5 && b.left < a.right - 0.5 && a.top < b.bottom - 0.5 && b.top < a.bottom - 0.5;
  const rows = [...document.querySelectorAll('.vl-tree .vl-main, .vl-topblock .vl-main')].slice(0, 16).map((b) => {
    const row = +b.dataset.row, cell = b.querySelector('.vl-cell-acc'), box = cell && cell.getBoundingClientRect();
    const boxes = parts(b).map((e) => e.getBoundingClientRect());
    return {row, line: [c.access1.at(row), c.access2.at(row)],
            dots: cell ? [...cell.querySelectorAll('svg.ac')].map((d) => d.getAttribute('class')) : null,
            inside: cell ? [...cell.querySelectorAll('svg.ac')].every((d) => { const r = d.getBoundingClientRect();
              return r.left >= box.left - 1 && r.right <= box.right + 1; }) : null,
            overlaps: boxes.some((a, i) => boxes.some((x, k) => k > i && overlap(a, x))),
            cut: [...b.querySelectorAll('.vl-v')].filter((v) => v.scrollWidth > v.clientWidth + 1).map((v) => v.textContent),
            within: boxes.every((r) => r.right <= b.getBoundingClientRect().right + 1)}; });
  return {width: list ? Math.round(list.getBoundingClientRect().width) : null, rows,
          heads: [...document.querySelectorAll('.vl-tree .vl-cols > span')].map((s) => s.textContent).filter(Boolean),
          headsCut: [...document.querySelectorAll('.vl-tree .vl-cols > span')].filter((h) => h.scrollWidth > h.clientWidth + 1).map((h) => h.textContent),
          classes: [...document.querySelectorAll('.vl-tree .vl-rows')].map((u) => u.classList.contains('vl-with-acc'))}; }"""


GAP_G1 = "gap G1: fixed by B3 fix round 5"  # parity.md A2/A3; the planner removes the mark when B3's fix is merged


@pytest.mark.parametrize("width", [None, 340, pytest.param(280, marks=pytest.mark.xfail(strict=True, reason=GAP_G1)),
                                   pytest.param(260, marks=pytest.mark.xfail(strict=True, reason=GAP_G1))],
                         ids=["default", "340", "280", "260"])
def test_access_column_at_kept_list_widths(pages, width):
    """A1-A3 (today's test_list_column_and_its_widths): the view's list of a marked run at its default width and kept
    at 340 px draws the column "Anchors" (before "Lines"), every row's two dots inside their cell; kept under 300 px
    (280, 260: layout.ts LIMITS lets a list be 260 px) the column is left out, as on today's page (the planner, gap G1:
    B3's fix round 5), and the mark stays in the map's legend and the details of a selected line. At every width no
    part of a row over another, no value and no column head wider than its cell (its text drawn over the next)."""
    from playwright.sync_api import sync_playwright
    narrow = width is not None and width < 300
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            script = "" if width is None else                 f"try {{ localStorage.setItem('findaline.layout', {json.dumps(_kept_list(width))}); }} catch (e) {{}}"
            page = _open(browser, f"{pages['app']}#run={BIG}", DESKTOP, script=script)
            page.wait_for_selector(".vl-tree .vl-main", state="attached", timeout=WAIT)
            _state(page)
            found = page.evaluate(NARROW)
            # a line selected whose anchors are in view, the profile's card closed (it folds the legend: 4 a)
            _state(page, "view.select(view.inView.best[0] ?? view.order[0]); view.model.closeProfile();")
            page.wait_for_selector(".vl-details .vl-acc", state="attached", timeout=WAIT)
            page.wait_for_selector(".v-legend [data-kind='access-2']", state="attached", timeout=WAIT)
            marked = page.evaluate("() => [[...document.querySelectorAll('.v-legend [data-kind^=access-]')].map((e) => e.dataset.kind), "
                                   "document.querySelectorAll('.vl-details .vl-acc .vl-acc-row').length]")
            errors = _errors(page)
        finally:
            browser.close()
    assert found["width"] == (width or 372), ("the kept width taken", width, found["width"])
    assert len(found["rows"]) >= 8, ("A1", width, len(found["rows"]))
    heads = found["heads"]
    if narrow:
        assert found["classes"] and not any(found["classes"]), ("A3: the column left out", width, found["classes"])
        assert heads[-1] == WORDS["ui.list.col.lines"] and WORDS["ui.list.col.anchors"] not in heads, ("A3", width, heads)
        assert all(row["dots"] is None for row in found["rows"]), ("A3: no row's cell of the mark", width)
    else:
        assert found["classes"] and all(found["classes"]), ("A1/A2: the column", width, found["classes"])
        assert heads[-2:] == [WORDS["ui.list.col.anchors"], WORDS["ui.list.col.lines"]], ("A1/A2", width, heads)
        for row in found["rows"]:
            a1, a2 = row["line"]
            assert row["dots"] == [f"ac ac-{a1}", f"ac ac-{a2}"] and row["inside"], ("A1/A2: the dots inside their cell", width, row)
    for row in found["rows"]:
        assert not row["overlaps"] and row["within"], ("A1-A3: no part over its neighbour", width, row)
    assert found["headsCut"] == [], ("A2/A3: a column head over the next one", width, found["headsCut"])
    assert [row["cut"] for row in found["rows"] if row["cut"]] == [], ("A2/A3: a value over the next one", width)
    assert marked == [["access-2", "access-1", "access-0"], 2], ("A3: the mark in the legend and the details", width, marked)
    assert errors == [], ("X2", width, errors)


def test_access_a_real_search_too_wide_in_the_view(tmp_path, monkeypatch):
    """A13 (today's test_a_real_search_too_wide_for_the_mark_on_the_page, the run's half): a search with --access whose
    memory cannot hold the access grid, made and saved for real (search.plan_search, search_lines, save_run): its
    store's head carries `access_skipped`, and the view (not today's page) opens it with today's muted line "Anchors'
    access not marked: the search area was too wide." once and nothing else of the mark, on a desktop and a phone,
    with nothing selected and with a spot selected. (The estimate's half is the search form: today's test.)"""
    from datetime import datetime
    from playwright.sync_api import sync_playwright
    import runs as rn
    import search
    from params import SearchParams
    from test_access_search import LEFT, SIZE, TOP, scene
    from test_offline import OFFLINE_ENV, write_raster
    for key, value in OFFLINE_ENV.items():
        monkeypatch.setenv(key, value)
    write_raster(tmp_path / "wide.tif", scene(), LEFT, TOP)
    values = dict(elevation_file=str(tmp_path / "wide.tif"), northing=TOP - SIZE / 2, easting=LEFT + SIZE / 2, radius=135,
                  resolution=1, nmpt="off", water="off", fill_gaps="off", min_length=10, max_length=80,
                  slope_threshold=60, prominence_span=10, drop_radius=10, ortho="never")
    monkeypatch.setattr(search, "available_memory", lambda: 10_000)
    data = tmp_path / "data"
    paths = search.Paths(str(data), str(data / "work"))
    os.makedirs(paths.work)
    plan = search.plan_search(SearchParams(**values, access=True, name="Too wide"), paths, lambda kind, text: None)
    assert plan.access_skipped == "memory"
    lines, _ = search.search_lines(plan)
    run_id = "2026-11-16_120000_Too-wide_00000000000000d1"
    folder = data / "runs" / run_id
    folder.mkdir(parents=True)
    search.save_run(plan, lines, {"id": run_id, "path": str(folder), "created": datetime(2026, 11, 16, 12), "name": "Too wide"})
    rn.write_index(str(data / "runs"))
    page_path = stub_page(data, "accesswide")
    mark = ("svg.ac, .ac-none, .ac-hint, .ac-info, .ac-help, .vl-cell-acc, .vl-acc, .v-anchor-mark, .ac-map-icon, "
            "[data-kind^='access-'], .r-legend-acc, .r-acc, .r-cell-acc")
    result = """() => { const lines = [...document.querySelectorAll('.r-acc-skipped')].filter((e) => e.getClientRects().length);
        const v = window.FINDALINE_VIEW && window.FINDALINE_VIEW.view;
        return [v ? v.model.data.access_skipped : null, v ? v.count > 20 : null, lines.map((e) => e.textContent),
                document.querySelectorAll(%s).length, !!window.FINDALINE_RESULT]; }""" % json.dumps(mark)
    r = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            with _server(data) as port:
                for name, context in (("desktop", DESKTOP), ("phone", PHONE)):
                    page = _open(browser, f"http://127.0.0.1:{port}/{page_path}?ui=c#run={run_id}", context)
                    page.wait_for_selector(".r-acc-skipped", state="attached", timeout=WAIT)
                    r[name] = page.evaluate(result)
                    page.evaluate("() => { const v = window.FINDALINE_VIEW.view; v.select(v.order[0]); }")
                    page.wait_for_selector(".vl-details", state="attached", timeout=WAIT)
                    _state(page)
                    r[name + "-selected"] = page.evaluate(result)
                    r[name + "-errors"] = _errors(page)
                    page.context.close()
        finally:
            browser.close()
    line = [WORDS["ui.access.skipped"]]
    assert line == ["Anchors' access not marked: the search area was too wide."]
    for name in ("desktop", "desktop-selected", "phone", "phone-selected"):
        assert r[name] == ["memory", True, line, 0, False], ("A13", name, r[name])
    assert r["desktop-errors"] == r["phone-errors"] == [], ("X2", r)
