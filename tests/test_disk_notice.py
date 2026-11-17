"""The disk notice of a run's map.html (store wave 4; docs/line-volume/spec-store.md 1.2, 1.4, 1.7): a map written since
then (mapping.map_page) carries the run's name, the sentence of `ui.map.disk_notice` and the command
`findaline.py view <run id>`; opened from disk (file://) it shows that and loads nothing (no data.js, no store, no
list's lines); over http the notice never shows, not when it is parsed and not after, and is removed while the run is
read from its store, under the page's CSP. A map.html written before (tests/old_runs.py) opens from disk as before:
test_web.py::test_run_map_from_disk. In headless Edge with the Żabi Koń clip's run (test_public's clip_run)."""

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

from test_public import clip_run  # noqa: E402,F401
from test_shell_c import copy_clip  # noqa: E402
from test_web import CSP_STUB, EDGE, INTROS_SEEN, MAP_HELPERS, _result_in, _server, _violations  # noqa: E402

RUN = "2026-10-20_120000_Disk_00000000000000d5"
NAME = 'A <b>bold</b> & "quoted" run'  # escaped in the title, the heading and the command's neighbours
SENTENCE = "This map opens through Find-a-Line. Run:"  # the user's accepted words (spec-store 1.2)


def test_map_page_carries_the_notice():
    """map_page: the notice's element with its id and the run's, the name, the catalogue's sentence and the command,
    each escaped; no style attribute or element (the CSP), the literal tags test_web._map_page replaces."""
    page = mapping.map_page({"id": RUN, "name": NAME})
    assert messages.text("ui.map.disk_notice") == SENTENCE
    assert f'<div id="{mapping.DISK_NOTICE}" class="ui fal-disk" data-run="{RUN}">' in page
    assert f'<h1 class="fal-disk-name">{html.escape(NAME)}</h1>' in page
    assert f'<p class="fal-disk-text">{SENTENCE}</p>' in page
    assert f"<code>findaline.py view {RUN}</code>" in page
    assert f"<title>{html.escape(NAME)} - Find-a-Line</title>" in page and "<b>" not in page
    assert "<style" not in page and " style=" not in page and "<head>" in page
    assert '<script src="../runs.js"></script>' in page
    # after the viewer's script: the viewer runs before the notice is parsed
    assert page.index("viewer.js") < page.index(mapping.DISK_NOTICE)


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

# After the notice, from disk: what shows once the page is loaded (the bundle decides at DOMContentLoaded, before it)
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
  result.files = performance.getEntriesByType("resource").map((e) => e.name.split("/").pop())
    .filter((f) => /\\.arrow$|^data\\.js$|^lines\\.js$/.test(f));
  step = "end";
  show();
}, 0));
"""


def _edge_file(path, profile) -> str:
    return subprocess.run(
        [EDGE, "--headless", "--disable-gpu", f"--user-data-dir={profile}", "--no-first-run", "--window-size=1280,800",
         "--allow-file-access-from-files", "--virtual-time-budget=20000", "--dump-dom", path.as_uri()],
        capture_output=True, text=True, encoding="utf-8", timeout=180).stdout


@pytest.mark.skipif(not os.path.exists(EDGE), reason="needs Microsoft Edge")
def test_disk_notice_from_disk(disk_data, tmp_path):
    """From disk a new run's map shows the notice over the whole window (the run's name, the sentence, the command
    with its id) and loads nothing: no data file asked for, no script of data added, no loading or error, the map
    empty; with a stored theme (the app's Light or Dark) the notice takes it, on the tokens' --bg."""
    folder = disk_data / "runs" / RUN
    page = _page_with(folder, "disk", INTROS_SEEN + RECORDER, DISK_END)
    r = _result_in(_edge_file(folder / page, tmp_path / "edge-disk"))
    assert "error" not in r and r["at"] == "end", r
    n = r["notice"]
    assert n["display"] != "none" and (n["width"], n["height"]) == (n["vw"], n["vh"]), r
    assert n["run"] == RUN and n["name"] == NAME and n["text"] == SENTENCE, r
    assert n["command"] == f"findaline.py view {RUN}" and n["theme"] is None, r
    assert r["map"] == 0 and not r["loading"] and not r["run"], r
    assert r["asked"] == [] and r["files"] == [], r
    for theme, background in (("light", "rgb(243, 245, 242)"), ("dark", "rgb(14, 19, 17)")):  # ui/tokens.css --bg
        themed = _page_with(folder, theme, INTROS_SEEN + f'localStorage.setItem("findaline-theme", "{theme}");'
                            + RECORDER, DISK_END)
        t = _result_in(_edge_file(folder / themed, tmp_path / f"edge-{theme}"))
        assert "error" not in t and t["asked"] == [] and t["map"] == 0, t
        assert t["notice"]["theme"] == theme and t["notice"]["background"] == background, t


# Over http, first in the head: the notice's style each time it is added or changed, and whether it was ever shown
HTTP_HEAD = CSP_STUB + RECORDER + """
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
    r = _result_in(dom)
    assert "error" not in r and "timeout" not in r and r["at"] == "end", r
    assert r["parsed"] and r["seen"] and set(r["seen"]) == {"none"}, r  # observed, never shown
    assert r["served"] and r["rows"] > 0 and r["files"] == ["lines.arrow", "profiles.arrow"], r
    assert _violations(dom) == []
