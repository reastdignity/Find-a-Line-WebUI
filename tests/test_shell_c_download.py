"""Download of a run's lines on the result page (viewer/src/result/view/RunActions.tsx: mayExport, Export, Download),
in Playwright's browsers over the app's server, offline. A run read from its store on the app's page (which has the
token): the two rows ask the server for the file (POST /api/runs/<id>/export), wait ("Preparing the file…", the ring
on the button while the menu is closed), then the browser saves the answered address; a failure is one red line
under the rows, worded by the answer. A run without a store, and a store whose file answers 404, keep the two links
to lines.csv and lines.geojson; a run with a store on its own map.html (no token there) has no Download at all.

The export's route is answered in the browser (page.route), so no worker runs: an answer is held until the test
releases it, which is how the waiting state is looked at. Every wait is an event with a deadline. Run from
PowerShell (.claude/rules/browser-tests.md).

Not driven here: the public site's pages (a signed-in user's map.html, a visitor's demo run, a share link's page).
`_server` is the local app, and test_public's `_public_server` answers as https://lines.example.org, which no
browser of a test reaches. A signed-in user's and a visitor's map.html are the same map.html without the token meta
as the local one of test_store_run_on_its_own_map_has_no_download (mayExport reads only the token and `fromStore`).
A share link's page reads data.js (result/load.ts storeOf: no list of runs under /s/), so it is a run without a
store to the page: the two links of test_run_without_a_store_keeps_its_two_links."""

import json
import os
import sys
from urllib.parse import urlsplit

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_shell_c import BIG, SMALL, copy_clip, drop_store, small_copy, stub_page  # noqa: E402
from test_web import EDGE, TOKEN, _playwright, _server  # noqa: E402

pytestmark = pytest.mark.skipif(not os.path.exists(EDGE) or not _playwright(),
                                reason="needs Microsoft Edge and Playwright (group ui)")
WAIT = 30000  # ms: the deadline of every wait for the page
DESKTOP = {"viewport": {"width": 1400, "height": 900}}
PHONE = {"viewport": {"width": 390, "height": 844}, "device_scale_factor": 3, "is_mobile": True, "has_touch": True}
OLD = "2026-10-29_120000_Old_00000000000000d1"  # SMALL's lines in a run without a store (data.js)
with open(os.path.join(REPO, "locales", "en.json"), encoding="utf-8") as _f:
    EN = json.load(_f)
PREPARING, PREPARING_LABEL = EN["ui.result.export_preparing"], EN["ui.result.export_preparing_label"]
FAILED = EN["error.export_failed"]
WHAT = ["table, every line", "for GIS and map apps"]  # the rows' small texts while nothing is asked

# The run's Download button: the last of the actions (Measure, Compare, Share, Download) where the page has one
DOWNLOAD = ".r-actions > .r-popwrap:last-child > button"
ROW = ".r-downloads > button.u-btn >> nth=%d"  # 0: CSV, 1: GeoJSON
BUSY = ".r-downloads > button.u-btn[aria-busy=true]"
ERROR = ".r-downloads > p.u-small.r-error[role=alert]"
SETTLED = "() => !document.querySelector('.r-downloads > button[aria-busy=true]')"
# The result's intro (ui/Intro.tsx) put away: a run's map.html has no stubs that do it, and its dialog covers the page
INTRO_SEEN = "try { localStorage.setItem('findaline.intro.result', 'seen'); } catch (e) {}"

# Download as the page draws it: the actions' buttons, the Download button, the panel's rows, links and red line
STATE = """() => { const $ = (s) => document.querySelector(s), $$ = (s) => [...document.querySelectorAll(s)];
  const named = (b) => [b.textContent.trim(), b.getAttribute('aria-label')];
  const button = $('.r-actions > .r-popwrap:last-child > button'), result = window.FINDALINE_RESULT;
  return {fromStore: result ? result.model.data.fromStore ?? null : 'no FINDALINE_RESULT',
          actions: $$('.r-actions > * > button').map(named), open: !!$('.r-pop .r-downloads'), pops: $$('.r-pop').length,
          button: button && {text: button.textContent.trim(), label: button.getAttribute('aria-label'),
                             ring: !!button.querySelector('.r-spin'), icon: !!button.querySelector('svg'),
                             expanded: button.getAttribute('aria-expanded')},
          rows: $$('.r-downloads > button.u-btn').map((b) => ({
            name: b.textContent.trim().split(' ')[0], small: b.querySelector('.u-small').textContent,
            busy: b.getAttribute('aria-busy') === 'true', disabled: b.disabled, ring: !!b.querySelector('.r-spin'),
            icon: !!b.querySelector('svg')})),
          links: $$('.r-downloads > a.u-btn').map((a) => [a.getAttribute('href'), a.hasAttribute('download')]),
          csv: $$('a.u-btn[href$="lines.csv"][download]').length,
          geojson: $$('a.u-btn[href$="lines.geojson"][download]').length,
          errors: $$('.r-downloads > p.u-small.r-error[role=alert]').map((p) => p.textContent),
          allErrors: $$('.r-downloads .r-error').length}; }"""


@pytest.fixture(scope="module")
def clip(tmp_path_factory):
    """The folder of a run of the Żabi Koń clip (test_shell_c's big_clip arguments: the search that module made),
    computed once per session, offline."""
    import clip_runs
    data = os.path.join(REPO, "tests", "data")
    folder = clip_runs.data_copy(tmp_path_factory, "c-download", [
        "--elevation-file", os.path.join(data, "zabi_kon_nmt.tif"),
        "--surface-file", os.path.join(data, "zabi_kon_nmpt.tif"), "--northing", "254608", "--easting", "553966",
        "--radius", "150", "--model", "sag", "--fall-zone", "3", "--water", "off", "--fill-gaps", "off",
        "--no-plot", "--yes", "--ortho", "never"])
    runs = folder / "runs"
    return next(runs / d for d in os.listdir(runs) if (runs / d / "run.json").is_file())


def _listed(folder) -> dict:
    """The runs of the data folder as runs.js lists them (the list result/load.ts storeOf reads), by id."""
    text = (folder / "runs" / "runs.js").read_text("utf-8")
    start = text.index("window.FINDALINE_RUNS = ") + len("window.FINDALINE_RUNS = ")
    return {run["id"]: run for run in json.JSONDecoder().raw_decode(text, start)[0]}


def _data(tmp_path, clip, old: bool = False):
    """A data folder with the clip's run (BIG) and its first 300 lines with a store (SMALL), with `old` the same
    lines as a run without a store too (OLD: no block "store" in run.json, so none in runs.js, and no store
    files); the app's page for the tests (its head has the token: api.ts canChange)."""
    folder = tmp_path / "data"
    copy_clip(clip, folder, BIG, "Big run")
    small_copy(folder, BIG)
    if old:
        small_copy(folder, BIG, small=OLD, name="Old run")
        drop_store(folder, OLD)
        for name in ("lines.arrow", "profiles.arrow"):
            (folder / "runs" / OLD / name).unlink(missing_ok=True)
    listed = _listed(folder)
    assert listed[SMALL].get("store"), ("the clip's run has no store: the page would read data.js", listed[SMALL])
    assert not old or "store" not in listed[OLD], listed[OLD]
    page_path = stub_page(folder, "downloadtest")
    html = (folder / page_path).read_text("utf-8")
    assert f'<meta name="findaline-token" content="{TOKEN}">' in html, "the app's page has no token: no export there"
    assert "findaline-token" not in (folder / "runs" / SMALL / "map.html").read_text("utf-8")
    return folder, page_path


class Export:
    """The export's route of a page, answered by the test: every request is recorded (method, path, body, token);
    its answer is the next one released, kept waiting until the test releases one (release before or after the
    request arrived: no wait for the route itself)."""

    def __init__(self, page):
        self.requests, self.kept, self.answers = [], [], []
        page.route("**/api/runs/*/export", self.handle)

    def handle(self, route):
        request = route.request
        self.requests.append({"method": request.method, "path": urlsplit(request.url).path, "body": request.post_data,
                              "token": request.headers.get("x-findaline-token")})
        if self.answers:
            self.answer(route, self.answers.pop(0))
        else:
            self.kept.append(route)

    @staticmethod
    def answer(route, answer):
        if answer is None:  # no network: the request fails
            route.abort()
        else:
            status, body = answer
            route.fulfill(status=status, content_type="application/json", body=json.dumps(body))

    def release(self, answer):
        """Answer the waiting request (or the next one): (status, the JSON body), or None to break it off."""
        if self.kept:
            self.answer(self.kept.pop(0), answer)
        else:
            self.answers.append(answer)


def _open(browser, url: str, prepare=None, **context):
    """The result's page (its list drawn) and the addresses of the export requests it sent (heard from before
    the page loads); `prepare(page)` sets the page's routes first."""
    page = browser.new_page(**context)
    page.add_init_script(INTRO_SEEN)
    asked = []
    page.on("request", lambda request: "/export" in request.url and asked.append(request.url))
    if prepare:
        prepare(page)
    page.goto(url)
    page.wait_for_selector(".r-rows .r-row", state="attached", timeout=WAIT)
    page.wait_for_function("() => !!window.FINDALINE_RESULT", timeout=WAIT)
    return page, asked


def _menu(page):
    """Download's panel open (the button's press closes an open one: pressed only when it is closed)."""
    if not page.query_selector(".r-pop .r-downloads"):
        page.click(DOWNLOAD)
    _listening(page)


def _listening(page):
    """Download's panel open and listening: it hears Escape and a press outside from its effect, which runs after
    the paint and moves the focus into the panel; a key sent before that is not heard (no person is that fast)."""
    page.wait_for_selector(".r-pop .r-downloads", timeout=WAIT)
    page.wait_for_function("() => { const p = document.querySelector('.r-pop'); return !!p && p.contains(document.activeElement); }",
                           timeout=WAIT)


def _press(page, row: int):
    """A row pressed (0: CSV, 1: GeoJSON) and the page waiting for its file."""
    page.click(ROW % row)
    page.wait_for_selector(BUSY, timeout=WAIT)


def _rows(found) -> list:
    return [[r["name"], r["small"], r["busy"], r["disabled"], r["ring"], r["icon"]] for r in found["rows"]]


IDLE_ROWS = [["CSV", WHAT[0], False, False, False, True], ["GeoJSON", WHAT[1], False, False, False, True]]


def test_request_and_the_preparing_state(tmp_path, clip):
    """A press of "CSV" on the app's page of a run read from its store, on a desktop and a phone of 390 px: one
    POST /api/runs/<id>/export with {"format": "csv"} and the page's token. While the answer waits: the pressed row
    is busy (aria-busy, a ring instead of its icon, "Preparing the file…"), the other row disabled, the menu open,
    no red line; with the menu closed (Escape) the Download button holds the ring and is named "Download: preparing
    the file" (the phone's icon button too); opened again, the row still prepares. An answer that never comes
    (the request broken off) ends it with the one red line, both rows enabled and the button as before."""
    from playwright.sync_api import sync_playwright
    folder, page_path = _data(tmp_path, clip)
    r = {}
    with _server(folder) as port, sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            url = f"http://127.0.0.1:{port}/{page_path}?ui=c#run={SMALL}"
            for name, context in (("desktop", DESKTOP), ("phone", PHONE)):
                page, asked = _open(browser, url, **context)
                export = Export(page)
                found = r[name] = {"start": page.evaluate(STATE)}
                _menu(page)
                found["menu"] = page.evaluate(STATE)
                _press(page, 0)
                found["waiting"] = page.evaluate(STATE)
                page.keyboard.press("Escape")
                page.wait_for_selector(".r-pop", state="detached", timeout=WAIT)
                page.wait_for_selector(DOWNLOAD + " .r-spin", state="attached", timeout=WAIT)
                found["closed"] = page.evaluate(STATE)
                _menu(page)
                page.wait_for_selector(BUSY, timeout=WAIT)
                found["reopened"] = page.evaluate(STATE)
                export.release(None)
                page.wait_for_selector(ERROR, timeout=WAIT)
                page.wait_for_function(SETTLED, timeout=WAIT)
                found["ended"] = page.evaluate(STATE)
                found["requests"], found["asked"] = export.requests, asked
                page.close()
        finally:
            browser.close()
    for name, found in r.items():
        idle = {"text": "Download", "label": None} if name == "desktop" else {"text": "", "label": "Download"}
        for step in ("start", "menu", "ended"):
            button = found[step]["button"]
            assert {k: button[k] for k in idle} == idle and button["icon"] and not button["ring"], (name, step, button)
        assert found["start"]["fromStore"] is True and not found["start"]["open"], (name, found["start"])
        assert _rows(found["menu"]) == IDLE_ROWS and found["menu"]["links"] == [], (name, found["menu"])
        assert found["menu"]["button"]["expanded"] == "true" and found["menu"]["errors"] == [], (name, found["menu"])
        for step in ("waiting", "reopened"):
            got = found[step]
            assert _rows(got) == [["CSV", PREPARING, True, False, True, False],
                                  ["GeoJSON", WHAT[1], False, True, False, True]], (name, step, got)
            assert got["open"] and got["allErrors"] == 0, (name, step, got)
            # the button while the menu is open: the ring and the waiting's name too
            assert got["button"]["ring"] and got["button"]["label"] == PREPARING_LABEL, (name, step, got)
        closed = found["closed"]
        assert not closed["open"] and closed["pops"] == 0 and closed["rows"] == [], (name, closed)
        assert closed["button"]["ring"] and not closed["button"]["icon"], (name, closed)
        assert closed["button"]["label"] == PREPARING_LABEL == "Download: preparing the file", (name, closed)
        assert closed["button"]["text"] == idle["text"] and closed["button"]["expanded"] == "false", (name, closed)
        ended = found["ended"]
        assert ended["open"] and ended["errors"] == [FAILED] and ended["allErrors"] == 1, (name, ended)
        assert _rows(ended) == IDLE_ROWS, (name, ended)
        assert found["requests"] == [{"method": "POST", "path": f"/api/runs/{SMALL}/export",
                                      "body": json.dumps({"format": "csv"}, separators=(",", ":")),
                                      "token": TOKEN}], (name, found["requests"])
        assert TOKEN and len(found["asked"]) == 1, (name, found["asked"])


def _browser_of(p, kind: str):
    """(the browser, its context's options) of a kind of test_ready_file_is_saved; skips where the browser is not
    installed (`uv run playwright install chromium webkit`)."""
    from playwright.sync_api import Error
    engine, launch, profile = {"edge": (p.chromium, {"channel": "msedge", "headless": True}, None),
                               "iphone": (p.webkit, {}, "iPhone 13"), "pixel": (p.chromium, {}, "Pixel 7")}[kind]
    options = dict(p.devices[profile]) if profile else dict(DESKTOP)
    options.pop("default_browser_type", None)
    try:
        return engine.launch(**launch), options
    except Error as e:
        if kind == "edge":
            raise
        pytest.skip(f"Playwright's browser of {profile} is not installed: {str(e).splitlines()[0]}")


@pytest.mark.parametrize("kind", ["edge", "iphone", "pixel"])
def test_ready_file_is_saved(tmp_path, clip, kind):
    """The answer {"url": the file's address} makes the browser save that address (a download, the page stays):
    Edge on a desktop, WebKit as an iPhone 13, Chromium as a Pixel 7. The answer is released after the press
    returned, so the download starts outside the press (no user gesture is at hand then: the way a real answer
    of the worker arrives). Afterwards nothing is said: both rows enabled, no red line, the menu still open; a
    second press (GeoJSON) asks and saves again."""
    from playwright.sync_api import sync_playwright
    folder, page_path = _data(tmp_path, clip)
    files = [f"/api/runs/{SMALL}/export/{'a' * 22}.csv", f"/api/runs/{SMALL}/export/{'b' * 22}.geojson"]
    r = {"saved": [], "after": [], "sent": []}
    with _server(folder) as port, sync_playwright() as p:
        browser, options = _browser_of(p, kind)
        try:
            def send(route):
                r["sent"].append(urlsplit(route.request.url).path)
                route.fulfill(status=200, body="length,height\n25.0,12.5\n",
                              headers={"Content-Disposition": 'attachment; filename="x.csv"', "Content-Type": "text/csv"})

            def routes(page):
                page.route("**/api/runs/*/export/*", send)
            page, asked = _open(browser, f"http://127.0.0.1:{port}/{page_path}?ui=c#run={SMALL}", routes, **options)
            export = Export(page)
            r["start"] = page.evaluate(STATE)
            _menu(page)
            for row, path in enumerate(files):
                _press(page, row)  # the press's handler has returned: the page waits
                r.setdefault("waiting", page.evaluate(STATE))
                with page.expect_download(timeout=WAIT) as download:
                    export.release((200, {"url": path}))
                r["saved"].append(download.value.url)
                page.wait_for_function(SETTLED, timeout=WAIT)
                r["after"].append(page.evaluate(STATE))
            r["requests"], r["location"] = export.requests, page.evaluate("() => location.pathname + location.hash")
        finally:
            browser.close()
    assert r["start"]["fromStore"] is True, r["start"]
    assert [row[2:5] for row in _rows(r["waiting"])] == [[True, False, True], [False, True, False]], r["waiting"]
    assert len(r["saved"]) == 2 and all(saved.endswith(path) for saved, path in zip(r["saved"], files)), r["saved"]
    # (the file's own request is the browser's download: Chromium does not pass it through page.route, so the
    # download's address above is the check; the route only keeps a browser that does ask it from the server)
    for after in r["after"]:
        assert _rows(after) == IDLE_ROWS and after["allErrors"] == 0 and after["open"], (kind, after)
        assert not after["button"]["ring"] and after["button"]["icon"], (kind, after)
    assert [(q["method"], q["path"], json.loads(q["body"]), q["token"]) for q in r["requests"]] == [
        ("POST", f"/api/runs/{SMALL}/export", {"format": "csv"}, TOKEN),
        ("POST", f"/api/runs/{SMALL}/export", {"format": "geojson"}, TOKEN)], r["requests"]
    assert r["location"] == f"/{page_path}#run={SMALL}", r["location"]  # the page stayed


def _coded(code: str, **params) -> dict:
    """An error answer's body with a code (web.error_detail); its message is not the catalogue's: the page words
    the code itself."""
    return {"detail": {"message": f"the server's own words of {code}", "code": code, "params": params}}


# (name, status and body or None for no network, the line the page shows): web.py export_run's answers
FAILURES = [
    ("no worker, the public site", (503, _coded("no_worker")), EN["ui.result.export_no_worker"]),
    ("no worker, the local app", (503, _coded("no_worker_local")), EN["ui.result.export_no_worker_local"]),
    ("another quick task waits", (429, _coded("quick_waiting")), EN["error.quick_waiting"]),
    ("too many downloads", (429, _coded("rate_export")), EN["error.rate_export"]),
    ("the lane is busy", (504, _coded("busy", seconds=150)), EN["error.busy"].replace("{{seconds}}", "150")),
    ("the disk is full", (503, _coded("export_disk_full")), EN["error.export_disk_full"]),
    ("500 with a text", (500, {"detail": "the worker gave no export"}), FAILED),
    ("504 without a code", (504, {"detail": "Gateway Time-out"}), FAILED),
    ("400", (400, {"detail": "format: csv or geojson"}), FAILED),
    ("409 export_failed", (409, _coded("export_failed")), FAILED),
    ("401", (401, {"detail": "not signed in"}), FAILED),
    ("no network", None, FAILED),
]


def test_failure_is_one_line_by_the_answer(tmp_path, clip):
    """Every failed answer of the export shows one red line under the rows (role alert), worded by the answer: the
    two "no worker" cases in the export's own words, a waiting quick task, the rate, a busy lane (with its seconds)
    and a full disk in the catalogue's words of the code, everything else (a 500, a 504 without a code, 400, 409,
    401, no network) "The file could not be made. Try again in a moment." The rows work again at once: the next
    press takes the line away while it waits and sends another request."""
    from playwright.sync_api import sync_playwright
    assert EN["error.busy"].count("{{seconds}}") == 1
    assert EN["ui.result.export_no_worker_local"].endswith("findaline.py worker")
    assert len({text for _, _, text in FAILURES}) == 7  # the table's seven lines, each its own
    folder, page_path = _data(tmp_path, clip)
    r = {}
    with _server(folder) as port, sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page, asked = _open(browser, f"http://127.0.0.1:{port}/{page_path}?ui=c#run={SMALL}", **DESKTOP)
            export = Export(page)
            _menu(page)
            for k, (name, answer, _) in enumerate(FAILURES):
                _press(page, k % 2)
                waiting = page.evaluate(STATE)  # the line of the failure before is gone
                export.release(answer)
                page.wait_for_selector(ERROR, timeout=WAIT)
                page.wait_for_function(SETTLED, timeout=WAIT)
                r[name] = [waiting, page.evaluate(STATE)]
            r["requests"], r["asked"] = export.requests, asked
        finally:
            browser.close()
    for k, (name, answer, text) in enumerate(FAILURES):
        waiting, ended = r[name]
        assert waiting["allErrors"] == 0 and waiting["rows"][k % 2]["busy"], (name, waiting)
        assert waiting["rows"][1 - k % 2]["disabled"], (name, waiting)
        assert ended["errors"] == [text] and ended["allErrors"] == 1, (name, ended["errors"], text)
        assert _rows(ended) == IDLE_ROWS and ended["open"], (name, ended)
        assert not ended["button"]["ring"] and ended["button"]["label"] is None, (name, ended)
    assert r[FAILURES[4][0]][1]["errors"] == ["The search service is busy: no answer in 150 s. Try again later."]
    # a request per press, CSV and GeoJSON in turn
    assert [json.loads(q["body"])["format"] for q in r["requests"]] == \
        [("csv", "geojson")[k % 2] for k in range(len(FAILURES))], r["requests"]
    assert all(q["method"] == "POST" and q["token"] == TOKEN for q in r["requests"]), r["requests"]
    assert len(r["asked"]) == len(FAILURES), r["asked"]


def test_failure_opens_a_closed_menu_again(tmp_path, clip):
    """The menu closed while the file is prepared (Escape; a press on the map), then a failure: the panel opens
    again by itself with the red line and both rows enabled, the button without its ring; closing the menu takes
    the line away (opened again: none)."""
    from playwright.sync_api import sync_playwright
    folder, page_path = _data(tmp_path, clip)
    text = EN["ui.result.export_no_worker_local"]
    r = {}
    with _server(folder) as port, sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page, asked = _open(browser, f"http://127.0.0.1:{port}/{page_path}?ui=c#run={SMALL}", **DESKTOP)
            export = Export(page)
            for way in ("escape", "map"):
                _menu(page)
                _press(page, 1)
                if way == "escape":
                    page.keyboard.press("Escape")
                else:  # the map's upper edge, in its middle: free of the map's buttons and of the profile's card
                    box = page.locator(".c-col-map .c-leaflet").bounding_box()
                    page.mouse.click(box["x"] + box["width"] / 2, box["y"] + 30)
                page.wait_for_selector(".r-pop", state="detached", timeout=WAIT)
                page.wait_for_selector(DOWNLOAD + " .r-spin", state="attached", timeout=WAIT)
                closed = page.evaluate(STATE)
                export.release((503, _coded("no_worker_local")))
                page.wait_for_selector(".r-pop " + ERROR, timeout=WAIT)
                page.wait_for_function(SETTLED, timeout=WAIT)
                failed = page.evaluate(STATE)
                _listening(page)
                page.keyboard.press("Escape")
                page.wait_for_selector(".r-pop", state="detached", timeout=WAIT)
                _menu(page)
                again = page.evaluate(STATE)
                page.keyboard.press("Escape")
                page.wait_for_selector(".r-pop", state="detached", timeout=WAIT)
                r[way] = [closed, failed, again]
            r["requests"] = export.requests
        finally:
            browser.close()
    for way in ("escape", "map"):
        closed, failed, again = r[way]
        assert not closed["open"] and closed["button"]["ring"], (way, closed)
        assert closed["button"]["label"] == PREPARING_LABEL, (way, closed)
        assert failed["open"] and failed["errors"] == [text] and _rows(failed) == IDLE_ROWS, (way, failed)
        assert not failed["button"]["ring"] and failed["button"]["expanded"] == "true", (way, failed)
        assert again["open"] and again["allErrors"] == 0 and _rows(again) == IDLE_ROWS, (way, again)
    assert [json.loads(q["body"]) for q in r["requests"]] == [{"format": "geojson"}] * 2, r["requests"]


def test_run_without_a_store_keeps_its_two_links(tmp_path, clip):
    """A run without a store (no block "store" in runs.js: the page read its data.js, `fromStore` not set) keeps
    Download's two links to its own files, lines.csv and lines.geojson with `download`, on the app's page (a
    desktop and a phone) and on its own map.html; no row that asks the server, and no export request. The run with
    a store beside it has the two rows and no link (`fromStore` true)."""
    from playwright.sync_api import sync_playwright
    folder, page_path = _data(tmp_path, clip, old=True)
    r = {}
    with _server(folder) as port, sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            site = f"http://127.0.0.1:{port}"
            for name, url, context in (("app", f"{site}/{page_path}?ui=c#run={OLD}", DESKTOP),
                                       ("app phone", f"{site}/{page_path}?ui=c#run={OLD}", PHONE),
                                       ("map", f"{site}/runs/{OLD}/map.html", DESKTOP),
                                       ("map phone", f"{site}/runs/{OLD}/map.html", PHONE),
                                       ("store", f"{site}/{page_path}?ui=c#run={SMALL}", DESKTOP)):
                page, asked = _open(browser, url, **context)
                _menu(page)
                r[name] = [page.evaluate(STATE), asked,
                           page.evaluate("() => !!document.querySelector('meta[name=findaline-token]')")]
                page.close()
        finally:
            browser.close()
    for name, files in (("app", f"/runs/{OLD}/"), ("app phone", f"/runs/{OLD}/"), ("map", ""), ("map phone", "")):
        found, asked, token = r[name]
        assert found["fromStore"] is None and token == name.startswith("app"), (name, found, token)
        assert found["links"] == [[files + "lines.csv", True], [files + "lines.geojson", True]], (name, found)
        assert found["csv"] == 1 and found["geojson"] == 1 and found["rows"] == [], (name, found)
        assert found["allErrors"] == 0 and asked == [], (name, found, asked)
    found, asked, token = r["store"]
    assert found["fromStore"] is True and token and _rows(found) == IDLE_ROWS, found
    assert found["links"] == [] and found["csv"] == 0 and found["geojson"] == 0 and asked == [], (found, asked)


def test_store_run_on_its_own_map_has_no_download(tmp_path, clip):
    """A run read from its store on its own map.html (/runs/<id>/map.html: no token there, the server would
    refuse the request): no Download among the actions at all, on a desktop and a phone, no link to the kept
    files either, and no export request. The same page of the public site (a signed-in user's map.html, a
    visitor's demo run) differs in nothing the rule reads."""
    from playwright.sync_api import sync_playwright
    folder, _ = _data(tmp_path, clip)
    r = {}
    with _server(folder) as port, sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            for name, context in (("desktop", DESKTOP), ("phone", PHONE)):
                page, asked = _open(browser, f"http://127.0.0.1:{port}/runs/{SMALL}/map.html", **context)
                page.wait_for_selector(".leaflet-container", state="attached", timeout=WAIT)  # the map is drawn
                files = page.evaluate("""() => performance.getEntriesByType('resource')
                    .map((e) => new URL(e.name).pathname.split('/').pop())
                    .filter((f) => /\\.arrow$|^data\\.js$/.test(f)).sort()""")
                r[name] = [page.evaluate(STATE), asked, files,
                           page.evaluate("() => !!document.querySelector('meta[name=findaline-token]')")]
                page.close()
        finally:
            browser.close()
    for name, (found, asked, files, token) in r.items():
        assert found["fromStore"] is True and not token, (name, found)
        assert files == ["lines.arrow", "profiles.arrow"], (name, files)
        names = [word for action in found["actions"] for word in action if word]
        assert not any("Download" in word for word in names), (name, found["actions"])
        assert found["pops"] == 0 and found["rows"] == [] and found["links"] == [], (name, found)
        assert found["csv"] == 0 and found["geojson"] == 0 and not found["open"], (name, found)
        assert asked == [], (name, asked)


def test_store_that_answers_404_keeps_the_two_links(tmp_path, clip):
    """A run whose store's file is missing (lines.arrow answers 404) is read from its data.js (result/load.ts
    fromServer), so the app's page shows the two links to its kept files, not the rows that ask the server for a
    file made from the store; no export request."""
    from playwright.sync_api import sync_playwright
    folder, page_path = _data(tmp_path, clip)
    missing = []

    def routes(page):
        def gone(route):
            missing.append(urlsplit(route.request.url).path)
            route.fulfill(status=404, content_type="text/plain", body="Not Found")
        page.route(f"**/runs/{SMALL}/lines.arrow", gone)
    with _server(folder) as port, sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page, asked = _open(browser, f"http://127.0.0.1:{port}/{page_path}?ui=c#run={SMALL}", routes, **DESKTOP)
            _menu(page)
            found = page.evaluate(STATE)
        finally:
            browser.close()
    assert missing == [f"/runs/{SMALL}/lines.arrow"], missing
    assert found["fromStore"] is None and found["rows"] == [], found
    assert found["links"] == [[f"/runs/{SMALL}/lines.csv", True], [f"/runs/{SMALL}/lines.geojson", True]], found
    assert found["csv"] == 1 and found["geojson"] == 1 and asked == [], (found, asked)
