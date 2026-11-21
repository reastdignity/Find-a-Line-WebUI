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

from test_public import RUN_A, RUN_B, account_settings, session_of  # noqa: E402,F401
from test_shell_c import BIG, copy_clip, stub_page  # noqa: E402
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


# ---- M: a run's own map.html (map/main.tsx; today's: test_web.py::test_run_map*, test_disk_notice.py, ...) ---------

# A line outside nothing: the server's profile of two measured points, stubbed (the local app runs no worker here)
PROFILE_STUB = """
window.PROFILES = 0;
const realFetchOfParity = window.fetch;
window.fetch = (url, init) => {
  if (!String(url).startsWith("/api/profile")) return realFetchOfParity(url, init);
  PROFILES++;
  return Promise.resolve(new Response(JSON.stringify({d: [0, 20, 40, 60, 80], z: [300, 296, 292, 296, 301], min: [40, 7.5],
    water_m: 0, filled_m: 0}), {headers: {"content-type": "application/json"}}));
};
"""

# The run's credits as the map shows them (test_web.MAP_HELPERS' credits), and whether they are folded
CREDITS = """() => { const control = document.querySelector('.v-map .leaflet-control-attribution');
  const shown = (s) => { const e = control.querySelector(s); return e ? getComputedStyle(e).display : null; };
  return {text: control.textContent, links: [...control.querySelectorAll('a')].map((a) => a.getAttribute('href')),
          imgs: control.querySelectorAll('img').length, button: shown('.u-credits-toggle'), credits: shown('.u-credits'),
          visibleLinks: [...control.querySelectorAll('a')].filter((a) => a.offsetParent !== null).map((a) => a.getAttribute('href')),
          expanded: control.querySelector('.u-credits-toggle')?.getAttribute('aria-expanded') ?? null,
          focused: document.activeElement === control.querySelector('.u-credits-toggle')}; }"""


@pytest.fixture
def map_pages(tmp_path, view_clip):
    """A data folder for the map.html checks, served by the local app: the clip's run with today's credits of markup
    (CREDITED: test_web.CREDITS_HEAD), the same run named like an HTML tag (TAGGED: Compare's other run)."""
    folder = tmp_path / "data"
    copy_clip(view_clip, folder, CREDITED, "Credited clip")
    store_with(folder / "runs" / CREDITED, head=CREDITS_HEAD)
    copy_clip(view_clip, folder, TAGGED, XSS_NAME)
    with _server(folder) as port:
        yield {"root": f"http://127.0.0.1:{port}", "data": folder}


def _map_url(root: str, run_id: str) -> str:
    return f"{root}/runs/{urllib.parse.quote(run_id)}/map.html"


def _empty_point(page, away=None, apart: int = 80):
    """A point of the view's map a press reaches (no control, no menu, no line within reach), in the viewport; `apart`
    px or more from `away` (a point taken before)."""
    return page.evaluate("""([away, apart]) => { const {map} = window.FINDALINE_VIEW, box = window.FINDALINE_MAP.getContainer().getBoundingClientRect();
      const f = T.free(), controls = T.controls();
      for (let y = f[3] - 60; y > f[1] + 60; y -= 17) for (let x = f[0] + 60; x < f[2] - 60; x += 23) { const vx = x + box.left, vy = y + box.top;
        if (away && Math.hypot(vx - away.x, vy - away.y) < apart) continue;
        if (controls.some((c) => vx > c.left - 24 && vx < c.right + 24 && vy > c.top - 24 && vy < c.bottom + 24)) continue;
        const hit = document.elementFromPoint(vx, vy);
        if (!hit || !hit.closest('.leaflet-container') || hit.closest('.r-pop, .leaflet-control, [data-map-control]')) continue;
        if (map.pickAt(x, y, false).length === 0) return {x: vx, y: vy}; }
      return null; }""", [away, apart])


def test_map_page_in_the_view(map_pages):
    """M4-M13, D8 on a run's own map.html in the view, a desktop (today's test_web::test_run_map and
    test_shell_c_download::test_store_run_on_its_own_map_has_no_download): the way back "Find-a-Line" to the app's
    #run=; the run's credits as text (no markup, http(s) links only, ATTRIBUTION.txt beside the page, the processed
    note, OSM's links), not folded while no card is shown and folded behind "Data credits" while it is; the base
    layers without the satellite key and the orthophoto's credit as text; the actions Measure and Compare, no
    Download, no export asked; the store's two files read; a favourite kept by the server; Compare's other run named
    like an HTML tag listed and its lines added without running its name; measuring; no CSP violation, no error."""
    from playwright.sync_api import sync_playwright
    root, run = map_pages["root"], CREDITED
    r = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _open(browser, _map_url(root, run), DESKTOP, script=CSP_STUB + PROFILE_STUB)
            asked = []
            page.on("request", lambda request: "/export" in request.url and asked.append(request.url))
            _state(page)
            page.wait_for_function("() => document.querySelector('.v-map .leaflet-control-attribution').textContent.includes('FABDEM')",
                                   timeout=WAIT)
            r["back"] = page.evaluate("() => [...document.querySelectorAll('.c-back')].map((b) => b.getAttribute('aria-label') || b.textContent.trim())")
            r["credits"] = page.evaluate(CREDITS)
            r["layers"] = page.evaluate("() => [...document.querySelectorAll('.leaflet-control-layers-base label')].map((l) => l.textContent.trim())")
            page.evaluate("""() => [...document.querySelectorAll('.leaflet-control-layers-base label')]
                .find((l) => l.textContent.trim() === 'Ortho test').querySelector('input').click()""")
            page.wait_for_function("() => document.querySelector('.v-map .leaflet-control-attribution').textContent.includes('© Test')", timeout=WAIT)
            r["ortho"] = page.evaluate(CREDITS)
            page.evaluate("""() => [...document.querySelectorAll('.leaflet-control-layers-base label')]
                .find((l) => l.textContent.trim() === 'OpenTopoMap').querySelector('input').click()""")
            r["actions"] = page.evaluate("() => [...document.querySelectorAll('.c-result-top .r-actions button')].map((b) => b.textContent.trim() || b.getAttribute('aria-label'))")
            r["download"] = page.evaluate("() => [document.querySelectorAll('.r-downloads, a[href$=\"lines.csv\"], a[href$=\"lines.geojson\"]').length, "
                                          "!!document.querySelector('meta[name=findaline-token]')]")
            # a selection: its card, the credits folded; a favourite kept by the server
            _state(page, "view.select(view.order[0]);")
            page.wait_for_selector(".r-card .fal-profile-chart", timeout=WAIT)
            page.wait_for_function("() => getComputedStyle(document.querySelector('.v-map .u-credits')).display === 'none'", timeout=WAIT)
            r["withCard"] = page.evaluate(CREDITS)
            page.wait_for_function("() => window.FINDALINE_VIEW.view.model.favouritesOn", timeout=WAIT)
            page.click(".vl-dhead .r-fav")
            page.wait_for_selector(".r-picker .r-folder", timeout=WAIT)
            page.click(".r-picker .r-folder")
            link = page.evaluate("() => { const v = window.FINDALINE_VIEW.view; return v.model.lineLink(v.selected.line); }")
            page.wait_for_function("""(link) => fetch('/api/runs/' + encodeURIComponent(window.FINDALINE_VIEW.view.model.runId) + '/favourites')
                .then((a) => a.json()).then((b) => (Array.isArray(b) ? b : b.lines).includes(link))""", arg=link, timeout=WAIT)
            r["favourite"] = True
            # Compare: the other run named like a tag
            _state(page, "view.select(null);")
            page.click(".c-result-top .r-actions button:has-text('Compare')")
            page.wait_for_selector(".r-other input", timeout=WAIT)
            r["others"] = page.evaluate("() => [...document.querySelectorAll('.r-other')].map((o) => o.textContent)")
            page.click(".r-other input")
            page.wait_for_function("() => window.FINDALINE_VIEW.view.model.others.size === 1", timeout=WAIT)
            r["compared"] = page.evaluate("() => [[...window.FINDALINE_VIEW.view.model.others.values()][0].count, window.XSS || null, "
                                          "document.querySelectorAll('.r-others img').length]")
            page.click(".c-result-top .r-actions button:has-text('Compare')")
            page.wait_for_selector(".r-pop", state="detached", timeout=WAIT)
            # measuring: two presses on the map, the measured profile in the card
            page.click(".c-result-top .r-actions button:has-text('Measure')")
            first = _empty_point(page)
            second = _empty_point(page, first)
            assert first and second, "no two empty points on the map"
            for at in (first, second):
                page.mouse.click(at["x"], at["y"])
                page.evaluate("() => T.frames()")
            page.wait_for_function("() => !!window.FINDALINE_VIEW.measured", timeout=WAIT)
            page.wait_for_selector(".r-card .fal-profile-chart", timeout=WAIT)
            r["measured"] = page.evaluate("() => [document.querySelector('.r-card .r-dock-bar b').textContent, window.PROFILES, "
                                          "Math.round(window.FINDALINE_VIEW.measured.len) > 0]")
            r["files"] = page.evaluate("""(folder) => performance.getEntriesByType('resource').map((e) => new URL(e.name).pathname)
                .filter((p) => p.startsWith(folder)).map((p) => p.split('/').pop()).filter((f) => /\\.arrow$|^data\\.js$|^lines\\.js$/.test(f)).sort()""",
                                       f"/runs/{urllib.parse.quote(run)}/")
            r["csp"], r["errors"], r["asked"] = page.evaluate("() => window.CSP_VIOLATIONS || []"), _errors(page), asked
            r["view"] = page.evaluate("() => !!window.FINDALINE_VIEW && !window.FINDALINE_RESULT")
            # the way back: the app at the run
            page.click(".c-back")
            page.wait_for_url(re.compile(r".*/#run=" + re.escape(urllib.parse.quote(run))), timeout=WAIT)
            r["backTo"] = urllib.parse.urlsplit(page.url)[2:]
        finally:
            browser.close()
    assert r["view"], "the view opened map.html"
    assert r["back"] == ["Find-a-Line"] and r["backTo"] == ("/", "", f"run={urllib.parse.quote(run)}"), ("M5", r["back"], r["backTo"])
    credits = r["credits"]
    assert "Data: FABDEM V1-2 © University of Bristol (CC BY-NC-SA 4.0)" in credits["text"], ("M6", credits)
    assert "<img src=x onerror=window.XSS=1> (<b>x</b>)" in credits["text"] and credits["imgs"] == 0, ("M6", credits)
    assert "https://creativecommons.org/licenses/by-nc-sa/4.0/" in credits["links"] and "ATTRIBUTION.txt" in credits["links"], ("M6", credits)
    assert not any(link.startswith("javascript") for link in credits["links"] if link), ("M6", credits)
    assert "resampled and combined onto a working grid (changed)" in credits["text"], ("M6", credits)
    assert {"https://www.openstreetmap.org/copyright", "https://www.openstreetmap.org/fixthemap"} <= set(credits["links"]), ("M6", credits)
    assert credits["button"] == "none" and credits["credits"] == "inline", ("M10: not folded while no card", credits)
    assert r["layers"] == ["OpenTopoMap", "OpenStreetMap", "Ortho test"], ("M7", r["layers"])
    assert "<img src=x onerror=window.XSS=3> © Test" in r["ortho"]["text"] and r["ortho"]["imgs"] == 0, ("M7", r["ortho"])
    assert "https://example.invalid/terms" in r["ortho"]["links"], ("M7", r["ortho"])
    assert r["withCard"]["button"] != "none" and r["withCard"]["credits"] == "none", ("M10: folded while the card shows", r["withCard"])
    assert r["actions"] == ["Measure", "Compare"], ("M4", r["actions"])
    assert r["download"] == [0, False] and r["asked"] == [], ("D8", r["download"], r["asked"])
    assert r["files"] == ["lines.arrow", "profiles.arrow"], ("D8", r["files"])
    assert r["favourite"], "M11"
    assert len(r["others"]) == 1 and XSS_NAME in r["others"][0], ("M12", r["others"])
    assert r["compared"][0] > 0 and r["compared"][1:] == [None, 0], ("M12", r["compared"])
    assert r["measured"] == ["Measured profile", 1, True], ("M13", r["measured"])
    assert r["csp"] == [] and r["errors"] == [], ("X1/X2", r["csp"], r["errors"])


def test_map_page_phone_credits_in_the_view(map_pages):
    """M14 without the satellite key (today's test_web::test_run_map_on_a_phone_with_the_satellite_key, its credits'
    half; the key's layer comes from baselayers.ts, which both pages use): a run's map.html in the view on a phone of
    390 px: the run's data credits folded behind "Data credits" (aria-expanded false, ATTRIBUTION.txt not shown), the
    tile credits (OSM's with its fixthemap link) in sight; the button opens them (the focus kept on it) and folds them
    again; no CSP violation."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _open(browser, _map_url(map_pages["root"], CREDITED), PHONE, script=CSP_STUB)
            _state(page)
            toggle = ".v-map .u-credits-toggle"
            page.wait_for_selector(toggle, state="attached", timeout=WAIT)
            folded = page.evaluate(CREDITS)
            page.evaluate("(t) => document.querySelector(t).click()", toggle)
            page.wait_for_function("(t) => document.querySelector(t).getAttribute('aria-expanded') === 'true'", arg=toggle, timeout=WAIT)
            opened = page.evaluate(CREDITS)
            page.evaluate("(t) => document.querySelector(t).click()", toggle)
            page.wait_for_function("(t) => document.querySelector(t).getAttribute('aria-expanded') === 'false'", arg=toggle, timeout=WAIT)
            again = page.evaluate(CREDITS)
            layers = page.evaluate("() => [...document.querySelectorAll('.leaflet-control-layers-base label')].map((l) => l.textContent.trim())")
            csp, errors = page.evaluate("() => window.CSP_VIOLATIONS || []"), _errors(page)
        finally:
            browser.close()
    osm = {"https://www.openstreetmap.org/copyright", "https://www.openstreetmap.org/fixthemap"}
    assert folded["button"] != "none" and folded["expanded"] == "false" and folded["credits"] == "none", ("M14", folded)
    assert "ATTRIBUTION.txt" not in folded["visibleLinks"] and osm <= set(folded["visibleLinks"]), ("M14", folded)
    assert opened["credits"] != "none" and opened["focused"] and "ATTRIBUTION.txt" in opened["visibleLinks"], ("M14", opened)
    assert again["credits"] == "none" and osm <= set(again["visibleLinks"]), ("M14", again)
    assert layers == ["OpenTopoMap", "OpenStreetMap", "Ortho test"], ("M14: no satellite layer without the key", layers)
    assert csp == [] and errors == [], ("X1/X2", csp, errors)


UNLISTED = "2026-11-01_100000_Unlisted_00000000000000f4"  # a run runs.js does not name
MISSING = "2026-11-01_110000_Missing_00000000000000f5"    # a run without its store (saved before it)
NEWER = "2026-11-01_120000_Newer_00000000000000f6"        # a store of a newer format
BROKEN = "2026-11-01_130000_Broken_00000000000000f7"      # a store whose lines.arrow is not an Arrow file

# The loading's texts a page showed (test_web.LOAD_SCRIPT's, from the page's start), the store's files it asked
LOADING = """
window.SEEN = [];
new MutationObserver(() => { const e = document.querySelector('.c-loading .u-progress'), label = e && e.textContent;
  if (label && SEEN[SEEN.length - 1] !== label) SEEN.push(label); }).observe(document, {childList: true, subtree: true, characterData: true});
"""
LOADED = """() => ({seen: window.SEEN, error: (document.querySelector('.c-result-wait .c-error') || {}).textContent || '',
  alert: document.querySelector('.c-result-wait .c-error')?.getAttribute('role') ?? null,
  view: !!window.FINDALINE_VIEW, today: !!window.FINDALINE_RESULT, count: window.FINDALINE_VIEW ? window.FINDALINE_VIEW.view.count : null,
  files: performance.getEntriesByType('resource').map((e) => new URL(e.name).pathname.split('/').pop()).filter((f) => /\\.arrow$|^data\\.js$|^lines\\.js$/.test(f)).sort(),
  lists: performance.getEntriesByType('resource').map((e) => new URL(e.name).pathname).filter((p) => p.endsWith('/runs.js')),
  measures: performance.getEntriesByType('measure').filter((m) => m.name.startsWith('fal:run:')).map((m) => [m.name, m.detail]),
  csp: window.CSP_VIOLATIONS || []})"""


def test_map_page_loading_and_its_failures(tmp_path, view_clip):
    """M15-M18 with the view asked for (today's test_web::test_run_map_loads_its_store,
    test_store_share::test_unlisted_runs_read_the_store_in_edge, test_shell_c::test_shell_c_too_large,
    ::test_shell_c_map_says_why_a_store_failed): a run's map.html loads its store itself (its two files with their
    bytes, the loading's texts) and the view opens with every line; a run runs.js does not name is read from its store
    with runs.js asked once; a run without a store says ui.result.store_failed after the two 404s; a store the browser
    cannot hold, one of a newer format, one that cannot be read: each its own words, and neither page opens. These
    failures come before the page is chosen (map/main.tsx LoadedMap): the flag changes nothing there."""
    from playwright.sync_api import sync_playwright
    import old_runs
    import runs as rn
    from test_shell_c import TOO_LARGE_STUBS
    from test_store_share import _unlist
    # (an init script runs before the document has its root element: the stubs' observer watches the document)
    too_large = TOO_LARGE_STUBS.replace("observe(document.documentElement,", "observe(document,")
    assert too_large != TOO_LARGE_STUBS
    data = tmp_path / "data"
    for run_id, name in ((BIG, "Clip"), (UNLISTED, "Unlisted"), (MISSING, "Missing"), (NEWER, "Newer"), (BROKEN, "Broken")):
        copy_clip(view_clip, data, run_id, name)
    old_runs.drop_store(data / "runs" / MISSING)
    path = data / "runs" / NEWER / "run.json"
    meta = json.loads(path.read_text("utf-8"))
    meta["store"]["format"] += 1
    path.write_text(json.dumps(meta), "utf-8")
    (data / "runs" / BROKEN / "lines.arrow").write_bytes(b"not an Arrow file " * 100)
    rn.write_index(str(data / "runs"))
    _unlist(data, UNLISTED)
    lines = json.loads((data / "runs" / BIG / "run.json").read_text("utf-8"))["store"]["lines"]
    sizes = sum((data / "runs" / BIG / name).stat().st_size for name in ("lines.arrow", "profiles.arrow"))
    r = {}
    with _server(data) as port, sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            for name, run_id, stubs in (("store", BIG, CSP_STUB), ("unlisted", UNLISTED, CSP_STUB), ("missing", MISSING, CSP_STUB),
                                        ("newer", NEWER, CSP_STUB), ("broken", BROKEN, CSP_STUB), ("large", BIG, too_large)):
                ok = name in ("store", "unlisted")
                page = _open(browser, _map_url(f"http://127.0.0.1:{port}", run_id), DESKTOP, flag=False,
                             script=FLAG + stubs + LOADING)
                page.wait_for_function("() => !!window.FINDALINE_VIEW || !!document.querySelector('.c-result-wait .c-error')"
                                       " || !!window.FINDALINE_RESULT", timeout=WAIT)
                if ok:
                    _state(page)
                r[name] = page.evaluate(LOADED)
                r[name]["errors"] = _errors(page)
                if name == "large":
                    r[name]["scripts"] = page.evaluate("() => window.DATA_SCRIPTS")
                page.context.close()
        finally:
            browser.close()
    store = r["store"]
    assert store["view"] and not store["today"] and store["count"] == lines and store["error"] == "", ("M15", store)
    assert any(label.startswith("Downloading the run… ") and " of " in label for label in store["seen"]), ("M15", store["seen"])
    assert WORDS["ui.result.loading_parse"] in store["seen"] and WORDS["ui.result.loading_groups"] in store["seen"], ("M15", store["seen"])
    found = dict((name, detail) for name, detail in store["measures"])
    assert found["fal:run:download"] == {"bytes": sizes, "store": True} and "fal:run:script" not in found, ("M15", found)
    assert store["files"] == ["lines.arrow", "profiles.arrow"] and store["lists"] == ["/runs/runs.js"], ("M15", store)
    unlisted = r["unlisted"]
    assert unlisted["view"] and unlisted["count"] == lines and unlisted["files"] == ["lines.arrow", "profiles.arrow"], ("M16", unlisted)
    assert unlisted["lists"] == ["/runs/runs.js"], ("M16: runs.js once", unlisted["lists"])
    words = {"missing": WORDS["ui.result.store_failed"], "newer": WORDS["ui.result.newer_store"],
             "broken": WORDS["ui.result.store_failed"], "large": WORDS["ui.result.too_large"]}
    for name, text in words.items():
        got = r[name]
        assert got["error"] == text and not got["view"] and not got["today"] and "data.js" not in got["error"], (name, got)
    assert r["missing"]["files"] == ["lines.arrow", "profiles.arrow"], ("M15: the store's two 404s, nothing else", r["missing"])
    assert r["large"]["alert"] == "alert" and r["large"]["scripts"] == [], ("M17", r["large"])
    for name, got in r.items():
        assert got["csp"] == [] and got["errors"] == [], ("X1/X2", name, got["csp"], got["errors"])


# Over http, from the page's start (test_disk_notice.HTTP_HEAD as an init script): the notice's style at each change
NOTICE_SEEN = """
window.NOTICE_SEEN = [];
new MutationObserver(() => {
  const notice = document.getElementById("disk-notice");
  if (notice) NOTICE_SEEN.push(getComputedStyle(notice).display);
}).observe(document, {childList: true, subtree: true, attributes: true});
"""


def test_disk_notice_with_the_view(map_pages, tmp_path):
    """M1-M3 (today's test_disk_notice::test_disk_notice_never_shows_over_http, ::test_notice_hidden_when_a_module_fails,
    ::test_disk_notice_from_disk) with the view asked for: over http the notice is hidden whenever observed and removed,
    the page marked served, the run read from its store into the view, no CSP violation; a module of the bundle that
    fails leaves the page marked served and the notice never shown; from disk the notice stands over the whole window with the run's
    name, the sentence and the command, and nothing loads (no XHR, no script of data, an empty #map, no page)."""
    from playwright.sync_api import sync_playwright
    import mapping
    from test_disk_notice import FAILING_HEAD, RECORDER, SENTENCE
    run = CREDITED
    folder = map_pages["data"] / "runs" / run
    meta = json.loads((folder / "run.json").read_text("utf-8"))
    (folder / "map.html").write_text(mapping.map_page(meta), "utf-8")  # the page as a search writes it for this run
    assert mapping.DISK_NOTICE in (folder / "map.html").read_text("utf-8")
    r = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _open(browser, _map_url(map_pages["root"], run), DESKTOP, script=CSP_STUB + RECORDER + NOTICE_SEEN)
            page.wait_for_function("() => !document.getElementById('disk-notice') && window.FINDALINE_VIEW.view.count > 0", timeout=WAIT)
            r["http"] = page.evaluate("""() => ({seen: window.NOTICE_SEEN, served: document.documentElement.classList.contains('fal-served'),
                files: performance.getEntriesByType('resource').map((e) => e.name.split('/').pop()).filter((f) => /\\.arrow$|^data\\.js$|^lines\\.js$/.test(f)).sort(),
                csp: window.CSP_VIOLATIONS || []})""")
            r["http"]["errors"] = _errors(page)
            page.context.close()
            # M3: a module of the bundle that throws while it loads (Leaflet's `window.L = …` refused)
            page = _open(browser, _map_url(map_pages["root"], run), DESKTOP, flag=False, script=FLAG + FAILING_HEAD)
            page.wait_for_load_state("load")
            page.wait_for_function("() => window.FAILED.length > 0 && !!document.getElementById('disk-notice')", timeout=WAIT)
            r["failing"] = page.evaluate("""() => ({failed: window.FAILED, seen: window.NOTICE_SEEN, served: document.documentElement.classList.contains('fal-served'),
                display: getComputedStyle(document.getElementById('disk-notice')).display})""")
            page.context.close()
            context = browser.new_context(viewport={"width": 1280, "height": 800})
            context.add_init_script(INTRO_SEEN + FLAG + RECORDER)
            page = context.new_page()
            page.goto((folder / "map.html").as_uri())
            page.wait_for_load_state("load")
            page.wait_for_function("() => !!document.getElementById('disk-notice')", timeout=WAIT)
            r["disk"] = page.evaluate("""() => { const n = document.getElementById('disk-notice'), b = n.getBoundingClientRect(), t = (s) => (document.querySelector(s) || {}).textContent || '';
                return {display: getComputedStyle(n).display, size: [Math.round(b.width), Math.round(b.height), innerWidth, innerHeight],
                        run: n.dataset.run, name: t('.fal-disk-name'), text: t('.fal-disk-text'), command: t('.fal-disk-command'),
                        map: document.getElementById('map').childElementCount, loading: !!document.querySelector('.c-loading, .c-result-wait, .c-error'),
                        page: !!(window.FINDALINE_VIEW || window.FINDALINE_RESULT), asked: window.ASKED,
                        flag: (() => { try { return localStorage.getItem('findaline.view'); } catch (e) { return 'blocked'; } })()}; }""")
            context.close()
        finally:
            browser.close()
    http = r["http"]
    assert http["seen"] and set(http["seen"]) == {"none"} and http["served"], ("M2: never shown", http)
    assert http["files"] == ["lines.arrow", "profiles.arrow"] and http["csp"] == [] and http["errors"] == [], ("M2", http)
    failing = r["failing"]
    assert any("a module failed to load" in m for m in failing["failed"]), ("M3: the bundle did fail", failing)
    assert failing["served"] and failing["seen"] and set(failing["seen"]) == {"none"} and failing["display"] == "none", ("M3", failing)
    disk = r["disk"]
    assert disk["display"] != "none" and disk["size"][:2] == disk["size"][2:], ("M1: the whole window", disk)
    assert disk["run"] == run and disk["name"] == "Credited clip" and disk["text"] == SENTENCE, ("M1", disk)
    assert disk["command"] == f"findaline.py view {run}", ("M1", disk)
    assert disk["map"] == 0 and not disk["loading"] and not disk["page"] and disk["asked"] == [], ("M1: nothing loaded", disk)
    assert disk["flag"] in ("b", "blocked"), ("M1: the view was asked for", disk["flag"])


# ---- S, P: a share link's page and the public site's people (today's: test_store_share.py, test_public.py) ---------

SHARE_A = "ParityShare0123456789-token_abcdefXYZ0"   # RUN_A's link (token_urlsafe's alphabet)
SHARE_B = SHARE_A[::-1]                               # RUN_B's link: a run without a store


@pytest.fixture
def public(tmp_path, view_clip, account_settings):
    """The public site (uvicorn on a thread) over a data folder with A's run (the view's clip run: shared by a link and
    a demo run) and A's second run without a store (shared too), people A and B signed in by /test-sign-in/<who>;
    yields the site's address, the folder, the settings and the people's ids."""
    import uvicorn
    from fastapi.responses import RedirectResponse

    import accounts as ac
    import old_runs
    import web
    from jobs import Jobs
    from settings import PublicSettings
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    site = f"http://localhost:{port}"
    data = tmp_path / "data"
    data.mkdir()
    copy_clip(view_clip, data, RUN_A, "A's run")
    copy_clip(view_clip, data, RUN_B, "B's run")
    old_runs.drop_store(data / "runs" / RUN_B)
    jobs = Jobs(str(data))
    cookies, ids = {}, {}
    for who in ("a", "b"):
        ids[who], cookies[who], _ = session_of(data, account_settings, who)
    for run_id, token in ((RUN_A, SHARE_A), (RUN_B, SHARE_B)):
        jobs.add_run(run_id, ids["a"], 1)
        jobs.set_share(run_id, ac.digest(token))
    jobs.set_visibility(RUN_A, "demo")
    settings = PublicSettings(public_url=site, trusted_proxy="127.0.0.1", contact="admin@example.org")
    app = web.create_app(str(data), public=settings, accounts=account_settings)

    @app.get("/test-sign-in/{who}")
    def sign_in(who: str):  # the session's cookie as the sign-in sets it (a browser takes no __Host- cookie from a script)
        response = RedirectResponse("/", 302)
        response.set_cookie(ac.SESSION_COOKIE, cookies[who], secure=True, httponly=True, path="/", samesite="lax")
        return response
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 30
        while not server.started:
            assert time.monotonic() < deadline, "the server did not start"
            time.sleep(0.05)
        yield {"site": site, "data": data, "accounts": account_settings, "ids": ids}
    finally:
        server.should_exit = True
        thread.join(10)


def _status(url: str) -> int:
    try:
        with urllib.request.urlopen(url, timeout=30) as answer:
            return answer.status
    except urllib.error.HTTPError as e:
        return e.code


def _public_page(browser, site: str, path: str, context: dict, flag: bool, who: str | None = None, script: str = ""):
    """A page of the public site (`flag`: the view asked for; signed in as `who`), once it shows a run or a load's error."""
    ctx = browser.new_context(**context)
    ctx.add_init_script(HELPERS + CSP_STUB + (FLAG if flag else "") + script)
    page = ctx.new_page()
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)[:300]))
    if who:
        page.goto(f"{site}/test-sign-in/{who}")
        assert any(c["name"].startswith("__Host-") for c in ctx.cookies()), "not signed in"
    page.goto(site + path)
    page.wait_for_function("() => !!(window.FINDALINE_VIEW || window.FINDALINE_RESULT) || !!document.querySelector('.c-result-wait .c-error')",
                           timeout=WAIT)
    page.wait_for_function("() => !!document.querySelector('.r-actions') || !!document.querySelector('.c-result-wait .c-error')", timeout=WAIT)
    page.wait_for_load_state("networkidle", timeout=WAIT)  # the list of runs answered (Share's owner check)
    return page


# What a page of a run shows of who may do what: the run's actions, the way back, the page's flags and lines
WHO = """() => { const v = window.FINDALINE_VIEW, t = window.FINDALINE_RESULT;
  return {page: v ? 'view' : t ? 'today' : null, app: window.FINDALINE_APP ?? null, runs: window.FINDALINE_RUNS === undefined,
          actions: [...document.querySelectorAll('.r-actions button')].map((b) => b.textContent.trim() || b.getAttribute('aria-label')),
          back: [...document.querySelectorAll('.c-back')].map((b) => b.getAttribute('aria-label') || b.textContent.trim()),
          lines: v ? v.view.count : t ? t.model.shown.lines : 0,
          error: (document.querySelector('.c-result-wait .c-error') || {}).textContent || '', csp: window.CSP_VIOLATIONS || []}; }"""


@pytest.mark.parametrize("device", [DESKTOP, PHONE], ids=["desktop", "phone"])
def test_share_page_in_the_view(public, device):
    """S1, S2, S4, S7 (today's test_store_share::test_share_links_read_the_store_in_edge,
    test_public::test_signed_in_app_and_shared_map_in_edge, test_disk_notice::test_share_link_hides_the_notice) on
    a share link's page in the view, as on today's page of the same link: the flags {profiles: false, favourites:
    false}, no Measure, Compare, Share or Download, no way back, the run's lines; the run read from its store only, the
    only list /s/runs.js (FINDALINE_RUNS undefined), nothing of /runs/ or another run asked; the disk notice never
    shown; a shared run without a store says ui.result.store_failed after its store's two 404s; no CSP violation."""
    from playwright.sync_api import sync_playwright
    site = public["site"]
    asked = """(folder) => { const all = performance.getEntriesByType('resource').map((e) => new URL(e.name).pathname);
      return {files: all.filter((p) => p.startsWith(folder)).map((p) => p.split('/').pop()).filter((f) => /\\.arrow$|^data\\.js$|^lines\\.js$/.test(f)).sort(),
              lists: all.filter((p) => p.endsWith('/runs.js')),
              others: all.filter((p) => p.startsWith('/runs/') || (p.startsWith('/s/') && !p.startsWith(folder) && p !== '/s/runs.js' && !p.startsWith('/s/_viewer/'))),
              seen: window.NOTICE_SEEN, served: document.documentElement.classList.contains('fal-served')}; }"""
    r = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            for name, token, flag in (("view", SHARE_A, True), ("today", SHARE_A, False), ("old", SHARE_B, True)):
                folder = f"/s/{token}/"
                page = _public_page(browser, site, folder + "map.html", device, flag, script=NOTICE_SEEN)
                if name != "old":
                    page.wait_for_function("() => !document.getElementById('disk-notice')", timeout=WAIT)
                r[name] = {**page.evaluate(WHO), **page.evaluate(asked, folder), "errors": _errors(page)}
                page.context.close()
        finally:
            browser.close()
    view, today, old = r["view"], r["today"], r["old"]
    assert view["page"] == "view" and today["page"] == "today", (view["page"], today["page"])
    assert view["app"] == today["app"] == {"profiles": False, "favourites": False}, ("S4", view["app"], today["app"])
    assert view["actions"] == today["actions"] == [] and view["back"] == today["back"] == [], ("S4", view, today)
    assert view["lines"] > 0 and today["lines"] > 0, ("S4", view["lines"], today["lines"])
    assert view["files"] == ["lines.arrow", "profiles.arrow"] and view["lists"] == ["/s/runs.js"], ("S1", view)
    assert view["runs"] is True and view["others"] == [], ("S1", view)
    assert view["seen"] and set(view["seen"]) == {"none"} and view["served"], ("S7", view["seen"])
    assert old["page"] is None and old["error"] == WORDS["ui.result.store_failed"], ("S2", old)
    assert old["files"] == ["lines.arrow", "profiles.arrow"] and old["lists"] == ["/s/runs.js"] and old["others"] == [], ("S2", old)
    for name, got in r.items():
        assert got["csp"] == [] and got["errors"] == [], ("X1/X2", name, got["csp"], got["errors"])


def test_share_action_in_the_view(public):
    """S8 (today's test_shell_c::test_shell_c_public, the result's Share; the server's side: test_public::test_share_links)
    in the view's header, the owner signed in: Share's menu of a run shared already says so and offers "New link" and
    "Stop sharing"; a new link is shown once in its field and opens the run in the view, and the old link answers 404;
    "Stop sharing" ends it (404, the menu offers "Make a link"); a link made again stops working once its owner is
    blocked (404)."""
    from playwright.sync_api import sync_playwright
    import accounts as ac
    site = public["site"]
    share = ".c-result-top .r-actions button:has-text('Share')"
    menu = "() => { const s = document.querySelector('.r-share'); return s && {buttons: [...s.querySelectorAll('button')].map((b) => b.textContent.trim()), " \
           "text: [...s.querySelectorAll('p.u-small')].map((e) => e.textContent), link: s.querySelector('.r-linkfield input')?.value ?? null}; }"
    r = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _public_page(browser, site, f"/?ui=c#run={RUN_A}", DESKTOP, True, who="a")
            page.wait_for_selector(share, timeout=WAIT)
            page.click(share)
            page.wait_for_selector(".r-share", timeout=WAIT)
            r["shared"] = page.evaluate(menu)
            page.click(".r-share button:has-text('New link')")
            page.wait_for_selector(".r-share .r-linkfield input", timeout=WAIT)
            r["renewed"] = page.evaluate(menu)
            link = r["renewed"]["link"]
            r["statuses"] = [_status(f"{site}/s/{SHARE_A}/map.html"), _status(link)]
            visitor = _public_page(browser, site, link.replace(site, ""), DESKTOP, True)
            r["opened"] = visitor.evaluate(WHO)
            visitor.context.close()
            page.click(".r-share button:has-text('Stop sharing')")
            page.wait_for_function("() => [...document.querySelectorAll('.r-share button')].some((b) => b.textContent.trim() === 'Make a link')",
                                   timeout=WAIT)
            r["stopped"] = [page.evaluate(menu), _status(link)]
            page.click(".r-share button:has-text('Make a link')")
            page.wait_for_function("(old) => { const i = document.querySelector('.r-share .r-linkfield input'); return !!i && i.value !== old; }",
                                   arg=link, timeout=WAIT)
            again = page.evaluate(menu)["link"]
            before = _status(again)
            ac.Accounts(str(public["data"]), public["accounts"]).set_status(public["ids"]["a"], "blocked")
            r["blocked"] = [before, _status(again)]
            r["csp"], r["errors"] = page.evaluate("() => window.CSP_VIOLATIONS || []"), _errors(page)
        finally:
            browser.close()
    assert r["shared"]["buttons"] == ["New link", "Stop sharing"] and r["shared"]["link"] is None, ("S8", r["shared"])
    assert "Shared by a link. A new link replaces the old one." in r["shared"]["text"], ("S8", r["shared"])
    link = r["renewed"]["link"]
    assert link.startswith(f"{site}/s/") and link.endswith("/map.html") and SHARE_A not in link, ("S8", link)
    assert r["statuses"] == [404, 200], ("S8: the old link ends, the new opens", r["statuses"])
    assert r["opened"]["page"] == "view" and r["opened"]["lines"] > 0 and r["opened"]["actions"] == [], ("S8", r["opened"])
    stopped, status = r["stopped"]
    assert stopped["buttons"] == ["Make a link"] and status == 404, ("S8: stopped", r["stopped"])
    assert r["blocked"] == [200, 404], ("S9: a blocked owner's link", r["blocked"])
    assert r["csp"] == [] and r["errors"] == [], ("X1/X2", r["csp"], r["errors"])


def test_visitor_and_another_user_in_the_view(public):
    """P2, P3, D17 (today's test_public::test_signed_in_app_and_shared_map_in_edge, the demo run's half; the server:
    test_exports_of_the_public_site) in the view against today's page of the same address: a visitor without a session
    on the demo run's map.html: the flags {profiles: false, favourites: false}, no Measure, Compare, Share or
    Download, the way back "Find-a-Line", the run's lines; B signed in on A's demo run in the app: no Share, and the
    other actions today's page has (Measure, Compare, Download: a signed-in visitor of a demo may export)."""
    from playwright.sync_api import sync_playwright
    site = public["site"]
    r = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            for flag in (True, False):
                for name, path, who in (("visitor", f"/runs/{RUN_A}/map.html", None), ("other", f"/?ui=c#run={RUN_A}", "b")):
                    page = _public_page(browser, site, path, DESKTOP, flag, who=who)
                    r[(name, flag)] = {**page.evaluate(WHO), "errors": _errors(page)}
                    page.context.close()
        finally:
            browser.close()
    for name in ("visitor", "other"):
        view, today = r[(name, True)], r[(name, False)]
        assert view["page"] == "view" and today["page"] == "today", (name, view["page"], today["page"])
        assert view["actions"] == today["actions"] and view["back"] == today["back"], (name, view, today)
        assert view["lines"] > 0 and today["lines"] > 0, (name, view["lines"], today["lines"])
        for got in (view, today):
            assert got["csp"] == [] and got["errors"] == [], ("X1/X2", name, got["csp"], got["errors"])
    visitor = r[("visitor", True)]
    assert visitor["app"] == {"profiles": False, "favourites": False} and visitor["actions"] == [], ("P3", visitor)
    assert visitor["back"] == ["Find-a-Line"], ("P3", visitor["back"])
    other = r[("other", True)]
    assert other["actions"] == ["Measure", "Compare", "Download"], ("P2/D17", other["actions"])
