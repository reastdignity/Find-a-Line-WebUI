"""The disk notice of a run's map.html (store wave 4; docs/line-volume/spec-store.md 1.2, 1.4, 1.7): a map written since
then (mapping.map_page) carries the run's name, the sentence of `ui.map.disk_notice` and the command
`findaline.py view <run id>`; opened from disk (file://) it shows that and loads nothing (no data.js, no store, no
list's lines); over http the notice never shows, not when it is parsed and not after, and is removed while the run is
read from its store, under the page's CSP, also by a share link and when a module of the bundle fails to load. A
map.html written before (no notice: tests/old_runs.py's BASE_MAP_HTML) opened from disk shows the same notice, built by
the bundle (store wave 4's item 5: no data.js is read). In headless Edge with the Żabi Koń clip's run (test_public's
clip_run, made by a search: its own map.html is checked too)."""

import html
import json
import os
import subprocess
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mapping  # noqa: E402
import messages  # noqa: E402

pytest.importorskip("httpx2")

from test_public import account_settings, clip_run, copy_run, session_of  # noqa: E402,F401
from test_shell_c import copy_clip  # noqa: E402
from test_web import CSP_STUB, EDGE, INTROS_SEEN, MAP_HELPERS, _result_in, _server, _violations  # noqa: E402
sys.path.insert(0, os.path.join(REPO, "tools"))
import today_page  # noqa: E402  (the pin of today's page)

RUN = "2026-10-20_120000_Disk_00000000000000d5"
NAME = 'A <b>bold</b> & "quoted" run'  # escaped in the title, the heading and the command's neighbours
SENTENCE = "This map opens through Find-a-Line. Run:"  # the user's accepted words (spec-store 1.2)
TOKEN = "NoticeShare0123456789-token_abcdefXYZ"  # a share link's token (token_urlsafe's alphabet)


def test_map_page_carries_the_notice():
    """map_page: the notice's element with its id and the run's, the name, the catalogue's sentence and the command,
    each escaped; no style attribute or element (the CSP), the literal tags test_web._map_page replaces."""
    page = mapping.map_page({"id": RUN, "name": NAME})
    assert messages.text("ui.map.disk_notice") == SENTENCE
    assert f'<main id="{mapping.DISK_NOTICE}" class="ui fal-disk" data-run="{RUN}">' in page
    assert f'<h1 class="fal-disk-name">{html.escape(NAME)}</h1>' in page
    assert f'<p class="fal-disk-text">{SENTENCE}</p>' in page
    assert f"<code>findaline.py view {RUN}</code>" in page
    assert f"<title>{html.escape(NAME)} - Find-a-Line</title>" in page and "<b>" not in page
    assert "<style" not in page and " style=" not in page and "<head>" in page
    assert '<script src="../runs.js"></script>' in page
    # after the viewer's script: the viewer runs before the notice is parsed
    assert page.index("viewer.js") < page.index(mapping.DISK_NOTICE)
    # a name and an id that need escaping (an id cannot hold these today: runs._slug) stay text and attribute values
    name, run_id = '<script>alert("x")</script> & co', 'r"1<b>&'
    odd = mapping.map_page({"id": run_id, "name": name})
    assert "<script>alert" not in odd and "<b>" not in odd and odd.count("<script") == 2, odd  # runs.js, viewer.js
    assert f'data-run="{html.escape(run_id)}"' in odd and f"findaline.py view {html.escape(run_id)}</code>" in odd
    assert f'<h1 class="fal-disk-name">{html.escape(name)}</h1>' in odd
    assert f"<title>{html.escape(name)} - Find-a-Line</title>" in odd


@pytest.fixture
def disk_data(tmp_path, clip_run):
    """A data folder with the clip's run under RUN, its map.html written by map_page for its name and id."""
    data = tmp_path / "data"
    folder = copy_clip(clip_run, data, RUN, NAME)
    meta = json.loads((folder / "run.json").read_text("utf-8"))
    assert meta["store"] and not (folder / "data.js").exists()  # a run saved since store wave 4
    (folder / "map.html").write_text(mapping.map_page(meta), "utf-8")
    return data


def _page_with(folder, name: str, head: str, end: str) -> str:
    """A copy of the run's map.html with `head` first in its head and `end` last in its body (after the notice)."""
    page = (folder / "map.html").read_text("utf-8")
    (folder / f"{name}_head.js").write_text(head, "utf-8")
    (folder / f"{name}_end.js").write_text(end, "utf-8")
    (folder / f"{name}.html").write_text(
        page.replace("<head>", f'<head><script src="{name}_head.js"></script>')
            .replace("</body>", f'<script src="{name}_end.js"></script></body>'), "utf-8")
    return f"{name}.html"


# Before the bundle: every XHR and every script added to the page but its own (the test's, runs.js, viewer.js)
RECORDER = """
window.ASKED = [];
const xhrOpen = XMLHttpRequest.prototype.open;
XMLHttpRequest.prototype.open = function (method, url, ...rest) { ASKED.push("xhr " + url); return xhrOpen.call(this, method, url, ...rest); };
const OWN = ["runs.js", "viewer.js"];
new MutationObserver((changes) => changes.forEach((c) => c.addedNodes.forEach((n) => {
  const name = n.tagName === "SCRIPT" && n.src ? n.src.split("/").pop() : null;
  if (name && !OWN.includes(name) && !/_(head|end)\\.js$/.test(name)) ASKED.push("script " + name);
}))).observe(document, {childList: true, subtree: true});
"""

# After the notice, from disk: what shows once the page is loaded (the bundle decides at DOMContentLoaded, before it).
# "Loads nothing" is held by RECORDER (every XHR opened: the store's download; every script added: data.js from disk)
# and by the empty #map with no loading or error (the old path renders RunLoading at once); headless Edge records no
# resource timing from file://, so none is read here
DISK_END = MAP_HELPERS + """
step = "loaded";
addEventListener("load", () => setTimeout(() => {
  const notice = document.getElementById("disk-notice"), box = notice && notice.getBoundingClientRect();
  result.notice = notice && {display: getComputedStyle(notice).display, width: Math.round(box.width),
                             height: Math.round(box.height), vw: innerWidth, vh: innerHeight,
                             run: notice.dataset.run, theme: notice.dataset.theme || null,
                             name: text(".fal-disk-name"), text: text(".fal-disk-text"), command: text(".fal-disk-command"),
                             background: getComputedStyle(notice).backgroundColor};
  result.map = document.getElementById("map").childElementCount;
  result.loading = !!$(".c-loading, .c-result-wait, .c-error");
  result.run = window.FINDALINE_RUN !== undefined;
  result.asked = window.ASKED;
  step = "end";
  show();
}, 0));
"""


def _edge_file(path, profile) -> str:
    return subprocess.run(
        [EDGE, "--headless", "--disable-gpu", f"--user-data-dir={profile}", "--no-first-run", "--window-size=1280,800",
         "--allow-file-access-from-files", "--virtual-time-budget=20000", "--dump-dom", path.as_uri()],
        capture_output=True, text=True, encoding="utf-8", timeout=180).stdout


def _shown_from_disk(r: dict, run_id: str, name: str):
    """The notice shown over the whole window with the run's name, the sentence and the command, nothing loaded."""
    assert "error" not in r and r["at"] == "end", r
    n = r["notice"]
    assert n["display"] != "none" and (n["width"], n["height"]) == (n["vw"], n["vh"]), r
    assert n["run"] == run_id and n["name"] == name and n["text"] == SENTENCE, r
    assert n["command"] == f"findaline.py view {run_id}", r
    assert r["map"] == 0 and not r["loading"] and not r["run"] and r["asked"] == [], r


@pytest.mark.skipif(not os.path.exists(EDGE), reason="needs Microsoft Edge")
def test_disk_notice_from_disk(disk_data, tmp_path):
    """From disk a new run's map shows the notice over the whole window (the run's name, the sentence, the command
    with its id) and loads nothing: no XHR opened, no script of data added, no loading or error, the map empty; with a
    stored theme (the app's Light or Dark) the notice takes it, on the tokens' --bg."""
    folder = disk_data / "runs" / RUN
    page = _page_with(folder, "disk", INTROS_SEEN + RECORDER, DISK_END)
    r = _result_in(_edge_file(folder / page, tmp_path / "edge-disk"))
    _shown_from_disk(r, RUN, NAME)
    assert r["notice"]["theme"] is None, r
    for theme, background in (("light", "rgb(242, 245, 245)"), ("dark", "rgb(18, 26, 27)")):  # ui/tokens.css --bg
        themed = _page_with(folder, theme, INTROS_SEEN + f'localStorage.setItem("findaline-theme", "{theme}");'
                            + RECORDER, DISK_END)
        t = _result_in(_edge_file(folder / themed, tmp_path / f"edge-{theme}"))
        assert "error" not in t and t["asked"] == [] and t["map"] == 0, t
        assert t["notice"]["theme"] == theme and t["notice"]["background"] == background, t


@pytest.mark.skipif(not os.path.exists(EDGE), reason="needs Microsoft Edge")
def test_an_old_page_from_disk_shows_the_notice(disk_data, tmp_path):
    """A map.html written before store wave 4 (no notice: BASE_MAP_HTML), opened from disk, shows the same notice
    built by the bundle and loads nothing: the run's id from its folder (in the command too), its name from the list
    of runs (../runs.js) when it names the run (here another name than the page's title), else from the page's title
    (a copy runs.js does not name; a runs folder without runs.js); its data.js (left beside it) never asked for."""
    import shutil
    import old_runs
    import old_scripts
    import runs as rn
    listed_name = "Renamed in the list"  # runs.js's name, not the title's
    folder = disk_data / "runs" / RUN
    old_scripts.write_scripts(folder)  # what such a run held
    old_runs.old_map(folder)  # its title: NAME
    page_text = (folder / "map.html").read_text("utf-8")
    assert mapping.DISK_NOTICE not in page_text and listed_name not in page_text
    meta = json.loads((folder / "run.json").read_text("utf-8"))
    meta["name"] = listed_name
    (folder / "run.json").write_text(json.dumps(meta), "utf-8")
    unlisted = disk_data / "runs" / (RUN + "x")  # a copy runs.js does not name
    shutil.copytree(folder, unlisted)
    rn.write_index(str(disk_data / "runs"))
    text = (disk_data / "runs" / "runs.js").read_text("utf-8")
    assert listed_name in text and unlisted.name not in text
    alone = tmp_path / "alone" / "runs"  # a runs folder without runs.js
    shutil.copytree(disk_data / "runs" / mapping.VIEWER_FOLDER, alone / mapping.VIEWER_FOLDER)
    shutil.copytree(folder, alone / RUN)
    for where, profile, name in ((folder, "edge-old", listed_name), (unlisted, "edge-unlisted", NAME),
                                 (alone / RUN, "edge-alone", NAME)):
        page = _page_with(where, "old", INTROS_SEEN + RECORDER, DISK_END)
        _shown_from_disk(_result_in(_edge_file(where / page, tmp_path / profile)), where.name, name)


@pytest.mark.skipif(not os.path.exists(EDGE), reason="needs Microsoft Edge")
def test_a_search_writes_the_notice(clip_run, tmp_path):
    """The map.html a search wrote (search.save_run through mapping.save_map: the clip's run of tests/clip_runs.py)
    is map_page's, and from disk it shows its run's notice and loads nothing."""
    meta = json.loads((clip_run / "run.json").read_text("utf-8"))
    assert (clip_run / "map.html").read_text("utf-8") == mapping.map_page(meta)
    page = _page_with(clip_run, "searched", INTROS_SEEN + RECORDER, DISK_END)
    _shown_from_disk(_result_in(_edge_file(clip_run / page, tmp_path / "edge-searched")), meta["id"], meta["name"])


# Over http, first in the head: the notice's style each time it is added or changed, and whether it was ever shown
HTTP_HEAD = today_page.SCRIPT + CSP_STUB + RECORDER + """
window.NOTICE_SEEN = [];
new MutationObserver(() => {
  const notice = document.getElementById("disk-notice");
  if (notice) NOTICE_SEEN.push(getComputedStyle(notice).display);
}).observe(document, {childList: true, subtree: true, attributes: true});
"""

HTTP_END = MAP_HELPERS + """
step = "map";
const seenThere = () => !!document.getElementById("disk-notice");
const atEnd = seenThere();  // this script stands after the notice: it is parsed by now
wait(() => model() && rows().length > 0 && !seenThere(), () => {
  result.parsed = atEnd;
  result.seen = window.NOTICE_SEEN;
  result.rows = rows().length;
  result.served = document.documentElement.classList.contains("fal-served");
  result.files = performance.getEntriesByType("resource").map((e) => e.name.split("/").pop())
    .filter((f) => /\\.arrow$|^data\\.js$|^lines\\.js$/.test(f)).sort();
  step = "end";
  show();
});
"""


def _hidden_over_http(r: dict):
    """Seen when parsed and at every change, never shown; removed; the run read from its store."""
    assert "error" not in r and "timeout" not in r and r["at"] == "end", r
    assert r["parsed"] and r["seen"] and set(r["seen"]) == {"none"}, r  # observed, never shown
    assert r["served"] and r["rows"] > 0 and r["files"] == ["lines.arrow", "profiles.arrow"], r


@pytest.mark.skipif(not os.path.exists(EDGE), reason="needs Microsoft Edge")
def test_disk_notice_never_shows_over_http(disk_data, tmp_path):
    """Over http (the local app) the notice is hidden from the moment it is parsed (every observation of it
    display: none), removed afterwards, and the run is read from its store; no CSP violation."""
    folder = disk_data / "runs" / RUN
    page = _page_with(folder, "http", HTTP_HEAD, HTTP_END)
    with _server(disk_data) as port:
        dom = subprocess.run(
            [EDGE, "--headless", "--disable-gpu", f"--user-data-dir={tmp_path / 'edge-http'}", "--no-first-run",
             "--window-size=1280,800", "--virtual-time-budget=60000", "--dump-dom",
             f"http://127.0.0.1:{port}/runs/{RUN}/{page}"],
            capture_output=True, text=True, encoding="utf-8", timeout=240).stdout
    _hidden_over_http(_result_in(dom))
    assert _violations(dom) == []


# Over http with a module of the bundle that throws while it loads (Leaflet's `window.L = …` refused): what the
# notice looked like at each change, once the page is loaded
FAILING_HEAD = CSP_STUB + """
window.FAILED = [];
addEventListener("error", (e) => FAILED.push(e.message));
Object.defineProperty(window, "L", {configurable: true, get: () => undefined,
                                    set: () => { throw new Error("a module failed to load"); }});
window.NOTICE_SEEN = [];
new MutationObserver(() => {
  const notice = document.getElementById("disk-notice");
  if (notice) NOTICE_SEEN.push(getComputedStyle(notice).display);
}).observe(document, {childList: true, subtree: true, attributes: true});
"""

FAILING_END = """
addEventListener("load", () => setTimeout(() => {
  const notice = document.getElementById("disk-notice"), out = document.createElement("pre");
  out.id = "result";
  out.textContent = JSON.stringify({failed: window.FAILED, seen: window.NOTICE_SEEN,
                                    display: notice && getComputedStyle(notice).display,
                                    served: document.documentElement.classList.contains("fal-served")});
  document.body.appendChild(out);
}, 0));
"""


@pytest.mark.skipif(not os.path.exists(EDGE), reason="needs Microsoft Edge")
def test_notice_hidden_when_a_module_fails(disk_data, tmp_path):
    """Over http a module of the bundle that throws while it loads (here Leaflet's) still leaves the page marked
    served (map/served.ts runs first): the notice is never shown."""
    folder = disk_data / "runs" / RUN
    page = _page_with(folder, "failing", FAILING_HEAD, FAILING_END)
    with _server(disk_data) as port:
        dom = subprocess.run(
            [EDGE, "--headless", "--disable-gpu", f"--user-data-dir={tmp_path / 'edge-failing'}", "--no-first-run",
             "--window-size=1280,800", "--virtual-time-budget=40000", "--dump-dom",
             f"http://127.0.0.1:{port}/runs/{RUN}/{page}"],
            capture_output=True, text=True, encoding="utf-8", timeout=240).stdout
    r = _result_in(dom)
    assert any("a module failed to load" in m for m in r["failed"]), r  # the bundle did fail
    assert r["served"] and r["seen"] and set(r["seen"]) == {"none"} and r["display"] == "none", r


@pytest.mark.skipif(not os.path.exists(EDGE), reason="needs Microsoft Edge")
def test_share_link_hides_the_notice(tmp_path, clip_run, account_settings):
    """A share link's page on the public site (/s/<token>/map.html: the same map.html through web.RunFiles): the
    notice hidden whenever observed and removed, the run read from its store, no CSP violation."""
    import socket
    import threading
    import time

    import uvicorn
    from starlette.staticfiles import StaticFiles

    import accounts as ac
    import web
    from jobs import Jobs
    from settings import PublicSettings
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    site = f"http://localhost:{port}"
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    (stubs / "head.js").write_text(HTTP_HEAD, "utf-8")
    (stubs / "end.js").write_text(HTTP_END, "utf-8")
    data = tmp_path / "data"
    data.mkdir()
    folder = copy_run(clip_run, data, RUN, NAME)
    meta = json.loads((folder / "run.json").read_text("utf-8"))
    (folder / "map.html").write_text(
        mapping.map_page(meta).replace("<head>", '<head><script src="/test/head.js"></script>')
                              .replace("</body>", '<script src="/test/end.js"></script></body>'), "utf-8")
    jobs = Jobs(str(data))
    user_id, _, _ = session_of(data, account_settings, "a")
    jobs.add_run(RUN, user_id, 1)
    jobs.set_share(RUN, ac.digest(TOKEN))
    app = web.create_app(str(data), public=PublicSettings(public_url=site, trusted_proxy="127.0.0.1",
                                                          contact="admin@example.org"), accounts=account_settings)
    app.mount("/test", StaticFiles(directory=str(stubs)))
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 30
        while not server.started:
            assert time.monotonic() < deadline, "the server did not start"
            time.sleep(0.05)
        dom = subprocess.run(
            [EDGE, "--headless", "--disable-gpu", f"--user-data-dir={tmp_path / 'edge-share'}", "--no-first-run",
             "--window-size=1280,800", "--virtual-time-budget=60000", "--dump-dom", f"{site}/s/{TOKEN}/map.html"],
            capture_output=True, text=True, encoding="utf-8", timeout=240).stdout
    finally:
        server.should_exit = True
        thread.join(10)
    _hidden_over_http(_result_in(dom))
    assert _violations(dom) == []
