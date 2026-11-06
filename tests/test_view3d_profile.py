"""The 3D view's profile card and saving (docs/3d-view-contract.md, "Round 2", decisions 4 and 5): the pure parts
in Node (the keys of a line, its measured Line, the address of a link, a link outside the run measured by the 2D
result's model) and the page in headless Edge (the tools `profile` and `save`, the chart in its card, its cursor
and the walker following each other, a favourite saved and removed, a moved line saved, the links following it, no
Content-Security-Policy violation). Run the Edge test from PowerShell (headless Edge prints nothing from Git Bash)."""

import json
import os
import re
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_patch import _offline_env, clip_data  # noqa: E402,F401 (the fixture of the 3D page's tests)
from test_viewer import VIEWER, clip_data as run_data, run_ts  # noqa: E402,F401 (the run's data.js: the model)
from test_view3d import EDGE_SECONDS, VIRTUAL_BUDGET, _page, _with_until  # noqa: E402
from test_web import EDGE, _lines_of, _server, _violations  # noqa: E402

node = pytest.mark.skipif(not os.path.isdir(os.path.join(VIEWER, "node_modules", "esbuild")),
                          reason="needs Node and `npm install` in viewer/")


@node
def test_keys_lines_and_links(tmp_path):
    """save.ts: a key as the 2D result writes it (JavaScript's numbers), the measured line of a key and its profile
    (lineCoords is the key; `over` from the verdict; null where an anchor has no terrain), the line of the page for
    the found line and for moved anchors; page.ts: the way back and the link follow the line, the level only as the
    address asked for it."""
    found = run_ts(tmp_path, "view3d/save", """
const profile = (zEnd, minN) => ({d: [0, 40, 80], z: [300.5, 290, zEnd], min: [40, 12.5], min_nmpt: minN === null ? undefined : [40, minN],
                                  water_m: 0, filled_m: 0, max_height: [20, 7]});
const key = "50.1559508,19.7562722,50.1561234,19.7571230";
const out = {canonical: [m.canonicalKey(key), m.canonicalKey("50.1000000,19.5,-1.0e-7,3")]};
const l = m.lineOfKey(m.canonicalKey(key), profile(310, 4));
out.line = {coords: [l.lat1, l.lon1, l.lat2, l.lon2].join(","), len: l.len, clr: l.clr, e1: l.e1, e2: l.e2, over: l.over, prof: l.prof !== null};
out.over = [m.lineOfKey(key, profile(310, -2)).over, m.lineOfKey(key, profile(310, 3)).over, m.lineOfKey(key, profile(310, null)).over];
out.nodata = m.lineOfKey(key, {...profile(310, 4), z: [null, 1, 2]});
// The page's current line: the found one, then moved anchors (lonLat gives [lon, lat] of grid metres)
const view = {anchors: [{x: 0, y: 0, h: 1}, {x: 10, y: 20, h: 2}], edited: false, profile: null};
const lonLat = (x, y) => [19.5 + x * 1e-5, 50 + y * 1e-5];
const cur = m.currentOf(lonLat, view, key);
out.found = {key: cur.key(), line: cur.line()};
view.profile = profile(310, 4);
const a = cur.line(), b = cur.line();
out.cached = [a === b, a.lat1];
view.edited = true;
view.profile = null;
out.movedWaiting = [cur.key(), cur.line()];
view.profile = profile(305, 4);
const moved = cur.line();
out.moved = {key: cur.key(), line: [moved.lat1, moved.lon1, moved.lat2, moved.lon2].join(","), same: cur.line() === moved};
console.log(JSON.stringify(out));""")
    assert found["canonical"] == ["50.1559508,19.7562722,50.1561234,19.757123", "50.1,19.5,-1e-7,3"]
    key = "50.1559508,19.7562722,50.1561234,19.757123"
    assert found["line"]["coords"] == key and found["line"]["prof"] is True
    assert (found["line"]["len"], found["line"]["clr"], found["line"]["e1"], found["line"]["e2"]) == (80, 12.5, 300.5, 310)
    assert found["over"] == [True, False, False]  # the surface model's clearance <= 0 over a fitting terrain
    assert found["nodata"] is None
    assert found["found"] == {"key": key, "line": None}
    assert found["cached"] == [True, 50.1559508]
    assert found["movedWaiting"] == ["50,19.5,50.0002,19.5001", None]
    assert found["moved"]["key"] == "50,19.5,50.0002,19.5001"
    assert found["moved"]["line"] == found["moved"]["key"] and found["moved"]["same"] is True

    page = run_ts(tmp_path, "view3d/page", """
const hash = "#run=" + encodeURIComponent("run 1") + "&line=1.5,2.5,3.5,4.5";
const p = m.parsePage("?level=phone", hash, false), p2 = m.parsePage("", hash, true);
const moved = "50,19.5,50.0002,19.5001";
console.log(JSON.stringify({back: [m.backUrl(p), m.backUrl(p, moved), m.backUrl(p, null)],
  view: [m.viewUrl(p, moved, "?level=phone"), m.viewUrl(p2, moved, ""), m.viewUrl(p2, null, "?level=bogus&x=1"),
         m.viewUrl(p, moved, "?x=1&level=full")]}));""")
    assert page["back"] == ["/#run=run%201&line=1.5%2C2.5%2C3.5%2C4.5", "/#run=run%201&line=50%2C19.5%2C50.0002%2C19.5001",
                            "/#run=run%201"]
    assert page["view"] == ["/view3d?level=phone#run=run%201&line=50%2C19.5%2C50.0002%2C19.5001",
                            "/view3d#run=run%201&line=50%2C19.5%2C50.0002%2C19.5001",
                            "/view3d#run=run%201",
                            "/view3d?level=full#run=run%201&line=50%2C19.5%2C50.0002%2C19.5001"]


MODEL_LINK_SCRIPT = r"""
const data = JSON.parse(require("fs").readFileSync(PATH, "utf-8"));
const tick = () => new Promise((r) => setTimeout(r, 5));
const profile = {d: [0, 40, 80], z: [300.5, 290, 310], min: [40, 12.5], min_nmpt: [40, 4], water_m: 0, filled_m: 0};
const out = {};
(async () => {
  const asked = [];
  const api = {loadFavourites: async () => [], saveFavourite: async () => {},
               profile: async (run, key) => { asked.push(key); return profile; }};
  const known = data.lines[0].slice(0, 4).join(",");
  const outside = "49.5,19.1,49.5004,19.1005";
  // Where profiles can be asked: a link outside the run is measured, as two clicked points are
  let model = new m.ResultModel(data, {favourites: false, api, profiles: true});
  let measured = [];
  out.inRun = !!model.openLinked(known, (l) => measured.push(l));
  const r = model.openLinked(outside, (l) => measured.push(l));
  out.returned = r;
  out.during = [model.measuredLink, model.note];
  await tick();
  out.measured = measured.map((l) => [l.lat1, l.lon1, l.lat2, l.lon2, l.len, l.clr, l.e1, l.e2, l.prof === profile]);
  out.asked = asked;
  out.note = model.note;
  // Without the callback, and where the page cannot ask for profiles: today's note
  model = new m.ResultModel(data, {favourites: false, api, profiles: true});
  out.plain = [model.openLinked(outside), model.note && model.note.text];
  model = new m.ResultModel(data, {favourites: false, api, profiles: false});
  let called = 0;
  out.noProfiles = [model.openLinked(outside, () => called++), model.note && model.note.text, called];
  // Not four numbers: the note
  model = new m.ResultModel(data, {favourites: false, api, profiles: true});
  out.garbage = [model.openLinked("1,2,3", () => called++), model.note && model.note.text];
  // A measurement that fails: the note says so, and an answer for an older link is dropped
  const failing = {...api, profile: async () => { throw new Error("no terrain data"); }};
  model = new m.ResultModel(data, {favourites: false, api: failing, profiles: true});
  model.openLinked(outside, () => called++);
  await tick();
  out.failed = [model.measuredLink, model.note && model.note.text, called];
  let slow;
  const late = {...api, profile: () => new Promise((resolve) => { slow = resolve; })};
  model = new m.ResultModel(data, {favourites: false, api: late, profiles: true});
  const got = [];
  model.openLinked(outside, (l) => got.push(l));
  model.openLinked(known, (l) => got.push(l));  // the link moved on to a line of the run
  slow(profile);
  await tick();
  out.dropped = [got.length, model.measuredLink];
  console.log(JSON.stringify(out));
})();
"""


@node
def test_link_outside_the_run_is_measured(tmp_path, run_data):
    """result/model.ts openLinked: a line of a link that is not among the run's is measured where profiles can be
    asked (the callback gets the measured line, `measuredLink` names the link meanwhile), else today's note."""
    text, data = run_data
    path = tmp_path / "data.json"
    path.write_text(text, encoding="utf-8")
    out = run_ts(tmp_path, "result/model", MODEL_LINK_SCRIPT.replace("PATH", json.dumps(str(path))))
    assert out["inRun"] is True and out["returned"] is None
    assert out["during"] == ["49.5,19.1,49.5004,19.1005", None]
    assert out["measured"] == [[49.5, 19.1, 49.5004, 19.1005, 80, 12.5, 300.5, 310, True]]
    assert out["asked"] == ["49.5000000,19.1000000,49.5004000,19.1005000"] and out["note"] is None
    missing = "The line of the link is not in this run."
    assert out["plain"] == [None, missing]
    assert out["noProfiles"] == [None, missing, 0]
    assert out["garbage"] == [None, missing]
    assert out["failed"] == [None, "The line of the link could not be measured: no terrain data", 0]
    assert out["dropped"] == [0, None]


# On the page after the bundle: once ready, the tools, the card opened and its chart, the chart's cursor and the walker
# following each other, the line saved and removed (the favourites the server keeps), and at level full a moved line
# saved with the readout's sentence, the links following it; the findings go into <pre id="result">
PROFILE_SCRIPT = _with_until("""
(function () {
  const root = document.getElementById("view3d");
  const out = {};
  const done = () => {
    const pre = document.createElement("pre");
    pre.id = "result";
    pre.textContent = JSON.stringify(out);
    document.body.appendChild(pre);
  };
  /* until */
  const settled = (ms, then) => settledOn(() => root.dataset.frames, ms, then);  // ten polls over frames, none drawn
  const pointer = (type, target, x, y) => target.dispatchEvent(new PointerEvent(type, {clientX: x, clientY: y,
    pointerId: 7, button: 0, buttons: type === "pointerup" ? 0 : 1, bubbles: true, cancelable: true, isPrimary: true}));
  const run = decodeURIComponent(location.hash.match(/run=([^&]*)/)[1]);
  const favourites = () => fetch("/api/runs/" + encodeURIComponent(run) + "/favourites").then((r) => r.json());
  const tool = (id) => document.querySelector('.v3-tool[data-tool="' + id + '"]');
  const box = () => { const r = document.querySelector("canvas.v3-canvas").getBoundingClientRect(); return [r.width, r.height]; };
  const cursorX = () => { const c = document.querySelector(".fal-cursor"); return c ? Number(c.getAttribute("x1")) : null; };
  const slider = () => document.querySelector(".v3-slider");
  const sentence = () => (document.querySelector(".v3-readout .v3-edited .v3-long") || {}).textContent;
  const hold = (p) => p.then((v) => v, (e) => { out.error = String(e); return null; });

  // 4: the card and the chart
  const chart = () => {
    out.size = [box()];
    tool("profile").click();
    until(() => document.querySelector(".v3-card .fal-profile-chart svg"), 10000, (shown) => {
      out.chart = shown;
      out.size.push(box());
      out.stored = localStorage.getItem("findaline.view3d.profile");
      out.pressed = tool("profile").getAttribute("aria-pressed");
      out.legend = !!document.querySelector(".v3-card .fal-key");
      out.order = [...document.querySelectorAll(".v3-tool")].map((b) => [b.dataset.tool, getComputedStyle(b).order]);
      const span = Number(slider().max), hover = document.querySelector(".v3-card .fal-hover");
      const r = hover.getBoundingClientRect();
      out.span = span;
      out.sliderBefore = Number(slider().value);
      hover.dispatchEvent(new MouseEvent("mousemove", {clientX: r.left + r.width * 0.25, clientY: r.top + 5, bubbles: true}));
      out.sliderHover = Number(slider().value);
      until(() => cursorX() !== null && document.querySelector(".v3-card .fal-profile-title"), 5000, () => {
        out.title = document.querySelector(".v3-card .fal-profile-title").textContent;
        out.facts = (document.querySelector(".v3-card .v3-pcard-facts") || {}).textContent;
        out.cursorHover = cursorX();
        hover.dispatchEvent(new MouseEvent("mouseleave", {bubbles: true}));
        const x1 = out.cursorHover;
        slider().value = String(span * 0.75);
        slider().dispatchEvent(new Event("input", {bubbles: true}));
        until(() => cursorX() !== null && Math.abs(cursorX() - x1) > 20, 5000, (moved) => {
          out.cursorWalker = [moved, cursorX()];
          // opened and folded again: the canvas keeps its size, the choice is kept
          tool("profile").click();
          out.folded = [document.querySelector(".v3-card").childElementCount, localStorage.getItem("findaline.view3d.profile"),
                        tool("profile").getAttribute("aria-pressed")];
          out.size.push(box());
          save();
        });
      });
    });
  };

  // 5: saving
  const save = () => {
    const button = tool("save");
    out.saveShown = !!button && !button.classList.contains("v3-hidden");
    until(() => !button.classList.contains("v3-hidden") && !button.disabled, 10000, (enabled) => {
      out.enabled = enabled;
      out.label0 = button.title;
      button.click();
      until(() => button.dataset.saved === "1", 10000, async (saved) => {
        out.saved = saved;
        out.favs = (await hold(favourites())).lines;
        out.label1 = [button.title, button.getAttribute("aria-pressed")];
        button.click();
        until(() => button.dataset.saved === "", 10000, async () => {
          out.favsAfter = (await hold(favourites())).lines;
          out.label2 = button.title;
          button.click();  // saved again: the moved line is a second favourite
          until(() => button.dataset.saved === "1", 10000, () => moved());
        });
      });
    });
  };

  // a moved line (level full): dragged, its profile in, saved, the sentence and the links
  const moved = () => {
    tool("profile").click();  // open again: the card says so while the moved line's profile is asked for
    let sawWait = false;
    new MutationObserver(() => { if (document.querySelector(".v3-card .v3-pcard-wait")) sawWait = true; })
      .observe(document.querySelector(".v3-card"), {childList: true, subtree: true});
    const handles = [...document.querySelectorAll(".v3-handle")];
    out.handles = handles.length;
    out.back0 = document.querySelector(".v3-back").getAttribute("href");
    if (!handles.length) { done(); return; }
    const [h1, h2] = handles.map((h) => h.getBoundingClientRect());
    const handle = handles[1];
    const x0 = h2.left + h2.width / 2, y0 = h2.top + h2.height / 2;
    const x1 = x0 + (h1.left + h1.width / 2 - x0) * 0.2, y1 = y0 + (h1.top + h1.height / 2 - y0) * 0.2;
    pointer("pointerdown", handle, x0, y0);
    pointer("pointermove", handle, (x0 + x1) / 2, (y0 + y1) / 2);
    pointer("pointermove", handle, x1, y1);
    pointer("pointerup", handle, x1, y1);
    until(() => root.dataset.edit === "checked" || root.dataset.edit === "error", 20000, () => {
      out.waiting = sawWait;
      const button = tool("save");
      until(() => !button.disabled && document.querySelector(".v3-card svg"), 10000, async () => {
        out.chartAgain = !!document.querySelector(".v3-card svg");
        out.movedLabel = [button.title, button.getAttribute("aria-pressed"), button.dataset.saved];
        out.editedText = sentence();
        out.back1 = document.querySelector(".v3-back").getAttribute("href");
        button.click();
        until(() => button.dataset.saved === "1", 10000, async (saved) => {
          out.movedSaved = saved;
          out.movedFavs = (await hold(favourites())).lines;
          out.savedText = [sentence(), document.querySelector(".v3-readout .v3-edited .v3-short").textContent,
                           button.title, button.getAttribute("aria-pressed")];
          document.querySelector(".v3-reset").click();
          out.afterReset = [button.title, button.getAttribute("aria-pressed"), sentence(), document.querySelector(".v3-back").getAttribute("href")];
          // moved again: the sentence is the plain one when that line is not a favourite
          const p = handle.getBoundingClientRect();
          pointer("pointerdown", handle, p.left + p.width / 2, p.top + p.height / 2);
          pointer("pointermove", handle, p.left + p.width / 2 + 25, p.top + p.height / 2 - 25);
          pointer("pointerup", handle, p.left + p.width / 2 + 25, p.top + p.height / 2 - 25);
          out.movedAgain = [button.title, sentence()];
          out.copy = !!document.querySelector(".v3-copy");
          try { document.querySelector(".v3-copy").click(); } catch (e) { out.copyError = String(e); }
          setTimeout(() => { out.copyText = document.querySelector(".v3-copy").textContent; done(); }, 500);
        });
      });
    });
  };

  until(() => root.dataset.ready === "1", 25000, (ready) => settled(15000, (still) => {
    out.ready = ready;
    out.settled = still;
    out.tools = [...document.querySelectorAll(".v3-tool")].map((b) => b.dataset.tool);
    out.cardEmpty = document.querySelector(".v3-card").childElementCount === 0;
    out.run = run;
    out.hash = location.hash;
    if (!ready) { done(); return; }
    chart();
  }));
})();
""")


def _clear_favourites(port: int, run: str) -> list:
    """Remove the local user's favourites of `run` through the app (the data folder is the module's, shared by the
    levels); the lines that were there."""
    import urllib.request
    from urllib.parse import quote
    open_ = urllib.request.build_opener(urllib.request.ProxyHandler({})).open  # the test env's proxy is a dead end
    base = f"http://127.0.0.1:{port}"
    url = f"{base}/api/runs/{quote(run, safe='')}/favourites"
    with open_(url) as response:
        body = json.loads(response.read())
    for line in body["lines"]:
        request = urllib.request.Request(url, json.dumps({"line": line, "favourite": False}).encode(), method="POST", headers={
            "Content-Type": "application/json", "X-Findaline-Token": body["token"], "Origin": base})
        open_(request).read()
    return body["lines"]


def _profile_page(data) -> str:
    """The app's /view3d page with the CSP stub before its bundle and PROFILE_SCRIPT after it (as test_view3d's)."""
    from fastapi.testclient import TestClient
    from test_web import CSP_STUB, LOCAL, TOKEN, web
    folder = data / "runs" / "view3dprofile"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "stubs.js").write_text(CSP_STUB, encoding="utf-8")
    (folder / "test.js").write_text(PROFILE_SCRIPT, encoding="utf-8")
    app = web.create_app(str(data), token=TOKEN, start_scheduler=False)
    with TestClient(app, base_url=LOCAL) as client:
        page = client.get("/view3d").text
    script = '<script src="/app/view3d.js"></script>'
    assert script in page
    (folder / "index.html").write_text(page.replace(
        script, f'<script src="stubs.js"></script>{script}<script src="test.js"></script>'), encoding="utf-8")
    return "runs/view3dprofile/index.html"


@pytest.mark.skipif(not os.path.exists(EDGE), reason="needs Microsoft Edge")
@pytest.mark.parametrize("level", ["full", "phone"])
def test_view3d_profile_card_and_saving(clip_data, tmp_path, monkeypatch, level):
    """The tools `profile` (order 5) and `save` (6); the card folded, the chart in it once opened, the canvas the same
    size open and folded, the choice kept in the browser; the chart's cursor moves the walker and the walker the
    chart's cursor; the found line saved (the key the 2D result has) and removed; at level full a moved line saved
    (a second favourite, the readout saying so, the way back and the link following the moved anchors)."""
    data, meta = clip_data
    for key, value in _offline_env().items():
        monkeypatch.setenv(key, value)
    row = _lines_of(data, meta["id"])[0]
    line = ",".join(str(v) for v in row[:4])  # keys.ts lineCoords
    page = _profile_page(data)
    with _server(data, start_scheduler=True) as port:
        _clear_favourites(port, meta["id"])
        dom = subprocess.run(
            [EDGE, "--headless", "--disable-gpu", f"--user-data-dir={tmp_path / 'edge'}", "--no-first-run",
             "--window-size=1200,800", f"--virtual-time-budget={VIRTUAL_BUDGET}", "--force-prefers-no-reduced-motion", "--dump-dom",
             f"http://127.0.0.1:{port}/{page}?level={level}#run={meta['id']}&line={line}"],
            capture_output=True, text=True, encoding="utf-8", timeout=EDGE_SECONDS).stdout
    found = re.search(r'<pre id="result">(.*?)</pre>', dom, re.S)
    assert found, dom[-3000:]
    r = json.loads(found.group(1).replace("&quot;", '"').replace("&amp;", "&"))
    print(level, r)
    assert r["ready"] and r["settled"] and "error" not in r, r
    # the two tools of this file among the strip's (the others of round 2 have tests of their own)
    assert [t for t in r["tools"] if t in ("profile", "save")] == ["profile", "save"], r
    assert [o for o in r["order"] if o[0] in ("profile", "save")] == [["profile", "5"], ["save", "6"]], r
    assert r["cardEmpty"], r  # folded by default
    # the chart
    assert r["chart"] and r["stored"] == "open" and r["pressed"] == "true", r
    assert r["title"].startswith("Profile: ") and "min. clearance" in r["facts"] and r["legend"], r
    assert r["size"][0] == r["size"][1] == r["size"][2], r  # the card lies over the canvas
    assert r["folded"] == [0, "folded", "false"], r
    # the chart's cursor moved the walker, and the walker moved the chart's cursor
    assert abs(r["sliderHover"] - r["span"] * 0.25) < r["span"] * 0.03 and r["sliderHover"] != r["sliderBefore"], r
    assert r["cursorWalker"][0] and r["cursorWalker"][1] > r["cursorHover"] + 20, r
    # saving: the found line under the key of the address; removed again
    assert r["saveShown"] and r["enabled"] and r["label0"] == "Save line", r
    assert r["saved"] and r["favs"] == [line], r
    assert r["label1"] == ["Saved", "true"] and r["favsAfter"] == [] and r["label2"] == "Save line", r
    if level == "phone":
        assert r["handles"] == 0, r
    else:
        assert r["handles"] == 2 and r["waiting"] is True and r["chartAgain"] is True, r
        assert r["movedLabel"] == ["Save moved line", "false", ""], r
        assert r["editedText"] == "Anchors moved: not saved", r
        assert r["movedSaved"] and len(r["movedFavs"]) == 2 and line in r["movedFavs"], r
        moved = next(k for k in r["movedFavs"] if k != line)
        assert r["savedText"][0] == "Moved line saved to favourites" and r["savedText"][1] == "Moved, saved", r
        assert r["savedText"][3] == "true" and r["savedText"][2] == "Saved", r
        from urllib.parse import quote
        assert r["back0"].endswith("&line=" + quote(line, safe="")), r
        assert r["back1"].endswith("&line=" + quote(moved, safe="")) and r["back1"] != r["back0"], r
        assert r["afterReset"][0] == "Saved" and r["afterReset"][1] == "true" and r["afterReset"][3] == r["back0"], r
        assert r["movedAgain"] == ["Save moved line", "Anchors moved: not saved"] and r["copy"], r
        assert r["copyText"] in ("Copy link", "Link copied") and "copyError" not in r, r
    assert _violations(dom) == []
