"""The 3D view's page in headless Edge (docs/3d-view-contract.md, "Wave 2", V2a): the local app with a worker
over a run of the Żabi Koń clip (tests/test_patch.py's fixture), /view3d#run=…&line=… for a line of that run:
the terrain drawn (triangles in the last frame, the vertices within the budget), the readout filled from
/api/profile, no violation of the Content-Security-Policy. Run from PowerShell (headless Edge prints nothing
from Git Bash)."""

import json
import os
import re
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_patch import _offline_env, clip_data  # noqa: E402,F401 (the fixture)
from test_web import CSP_STUB, EDGE, LOCAL, TOKEN, _lines_of, _server, _violations, web  # noqa: E402

# The waits of the page scripts below: until(test, ms, then) calls then(true) once test() holds, then(false) after
# ms / 100 polls, each over one of the browser's animation frames. Under a virtual time budget headless Edge runs
# timers in virtual time, which jumps ahead while nothing loads, and animation frames in real time (each drawn by
# software GL here, seconds apart on a starved machine): behind plain timers the page's first frame often never
# came, and even with a small file loading all the while the virtual time leaked ahead between two loads, 16 s of
# it while one frame was drawn (6 copies of a test and 14 CPU burners). So the waits count frames, never virtual
# time: a pause of t ms spans t / 100 real frames, and a frame the page asked for before a poll has come by the
# poll's end (the browser runs every frame callback asked for before the frame: a probe saw the page's and a poll's
# run together, never more than one poll's frame between the page's asking and its frame). While a poll waits for
# its frame a small file is loading, again and again (which holds the virtual time), and a timer 1 virtual ms ahead
# is armed: what leaks between two loads then stops at that timer, never jumping to the page's next timer or to the
# budget's end. Each poll ends with 100 virtual ms for the page's own timers (e.g. a debounce). So the virtual
# time the waits take stays far within the tests' --virtual-time-budget (VIRTUAL_BUDGET); in real time a wait
# takes as long as the frames (EDGE_SECONDS). `frameTick` is the browser's own requestAnimationFrame, taken before
# any wrapper of a script, so the polls' frames are not counted as the page's.
UNTIL_JS = """
  let n = 0;
  const frameTick = window.requestAnimationFrame.bind(window), pollId = Math.random().toString(36).slice(2);
  const tick = (then) => {
    let framed = false, ended = false;
    frameTick(() => { framed = true; });
    const guard = () => { if (!ended) setTimeout(guard, 1); };
    const load = () => fetch("stubs.js?poll=" + pollId + "-" + (++n)).then(next, next);  // never from the cache
    const next = () => { if (!framed) load(); else { ended = true; then(); } };
    guard();
    load();
  };
  const until = (test, ms, then) => {
    let left = Math.ceil(ms / 100);
    const poll = () => {
      if (test()) then(true);
      else if (left-- <= 0) then(false);
      else tick(() => setTimeout(poll, 100));  // and 100 virtual ms for the page's own timers (e.g. a debounce)
    };
    poll();
  };
"""
# The virtual time budget of the page tests: a ceiling only (once the page idles, Edge runs its virtual time to the
# end at once), far above what leaks while the waits above hold it (74 virtual seconds at most in the test of the
# first frame at 6 copies and 14 CPU burners, about 2 s for each frame drawn; the ring's draws many more)
VIRTUAL_BUDGET = 3_600_000
# The real seconds an Edge run of these tests may take: the waits count frames, which a starved machine draws
# slowly (the ring's at level full took up to 331 s at 6 copies of the tests and 14 CPU burners)
EDGE_SECONDS = 900


def _with_until(script: str) -> str:
    """A page script with UNTIL_JS in place of its line `/* until */`."""
    assert "  /* until */\n" in script
    return script.replace("  /* until */\n", UNTIL_JS.lstrip("\n"))


# On the page after the bundle: waits for the page's ready marker (the terrain drawn and the profile in), then
# writes what it found into <pre id="result">
READY_SCRIPT = _with_until("""
(function () {
  const root = document.getElementById("view3d");
  const done = (what) => {
    const out = document.createElement("pre");
    out.id = "result";
    out.textContent = JSON.stringify(what);
    document.body.appendChild(out);
  };
  // The loading's stages as the status named them (main.ts Stage): the first is set before this script runs
  const stages = root.dataset.stage ? [root.dataset.stage] : [];
  new MutationObserver(() => {
    const stage = root.dataset.stage;
    if (stage && stages[stages.length - 1] !== stage) stages.push(stage);
  }).observe(root, {attributes: true, attributeFilter: ["data-stage"]});
  /* until */
  // The page's animation frames asked for and not run yet (it asks for them after this script: the patch comes
  // first); the polls' own frames are not among them
  const waiting = new Set(), raf = window.requestAnimationFrame.bind(window), caf = window.cancelAnimationFrame.bind(window);
  window.requestAnimationFrame = (fn) => {
    const id = raf((time) => { waiting.delete(id); fn(time); });
    waiting.add(id);
    return id;
  };
  window.cancelAnimationFrame = (id) => { waiting.delete(id); caf(id); };
  // settled: no frame drawn and none asked for during ten polls (each over a frame), at most `ms`
  const settled = (ms, then) => {
    let frames = root.dataset.frames, still = 0;
    until(() => {
      if (root.dataset.frames !== frames || waiting.size) { frames = root.dataset.frames; still = 0; return false; }
      return ++still > 10;
    }, ms, then);
  };
  until(() => root.dataset.ready === "1", 25000, (ready) => {
    if (!ready) {
      done({ready: false, status: (document.querySelector(".v3-status") || {}).textContent, data: {...root.dataset}});
      return;
    }
    settled(15000, (still) => {
      const frames = Number(root.dataset.frames);
      // two seconds of loading: a frame would come if the page asked for one
      until(() => false, 2000, () => done({ready: true, settled: still, stages, frames: [frames, Number(root.dataset.frames)], triangles: Number(root.dataset.triangles), vertices: Number(root.dataset.vertices),
        maxError: Number(root.dataset.maxError), readout: (document.querySelector(".v3-readout") || {}).textContent,
        filled: (document.querySelector(".v3-readout") || {dataset: {}}).dataset.filled || null,
        profileError: root.dataset.profileError || null, toolbar: document.querySelectorAll(".v3-toolbar input[type=range]").length,
        note: (document.querySelector(".v3-note") || {}).textContent, status: (document.querySelector(".v3-status") || {}).className,
        canvas: document.querySelectorAll("canvas.v3-canvas").length}));
    });
  });
})();
""")


def _page(data, run_id: str) -> str:
    """The app's /view3d page with the CSP stub before its bundle and the ready script after it, in a folder of
    runs/ (served as it is locally)."""
    from fastapi.testclient import TestClient
    folder = data / "runs" / "view3dtest"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "stubs.js").write_text(CSP_STUB, encoding="utf-8")
    (folder / "test.js").write_text(READY_SCRIPT, encoding="utf-8")
    app = web.create_app(str(data), token=TOKEN, start_scheduler=False)
    with TestClient(app, base_url=LOCAL) as client:
        page = client.get("/view3d").text
    script = '<script src="/app/view3d.js"></script>'
    assert script in page
    (folder / "index.html").write_text(page.replace(
        script, f'<script src="stubs.js"></script>{script}<script src="test.js"></script>'), encoding="utf-8")
    return "runs/view3dtest/index.html"


@pytest.mark.skipif(not os.path.exists(EDGE), reason="needs Microsoft Edge")
@pytest.mark.parametrize("level", ["full", "phone"])
def test_view3d_draws_the_line(clip_data, tmp_path, monkeypatch, level):
    data, meta = clip_data
    for key, value in _offline_env().items():
        monkeypatch.setenv(key, value)
    row = _lines_of(data, meta["id"])[0]
    line = ",".join(f"{v:.7f}" for v in row[:4])
    page = _page(data, meta["id"])
    with _server(data, start_scheduler=True) as port:
        dom = subprocess.run(
            [EDGE, "--headless", "--disable-gpu", f"--user-data-dir={tmp_path / 'edge'}", "--no-first-run",
             "--window-size=1200,800", f"--virtual-time-budget={VIRTUAL_BUDGET}", "--dump-dom",
             f"http://127.0.0.1:{port}/{page}?level={level}#run={meta['id']}&line={line}"],
            capture_output=True, text=True, encoding="utf-8", timeout=EDGE_SECONDS).stdout
    found = re.search(r'<pre id="result">(.*?)</pre>', dom, re.S)
    assert found, dom[-3000:]
    result = json.loads(found.group(1).replace("&quot;", '"').replace("&amp;", "&"))
    print(level, result)
    assert result["ready"] and result["settled"], result
    assert result["stages"] == ["server", "download", "unpacking", "building", "done"], result
    assert result["triangles"] > 0 and result["canvas"] == 1
    assert result["frames"][0] == result["frames"][1] < 10  # drawn on demand: nothing while nothing changes
    assert 0 < result["vertices"] <= (300_000 if level == "full" else 130_000)
    assert result["filled"] == "1" and result["profileError"] is None, result
    assert "m long" in result["readout"] and "m clear of the terrain" in result["readout"]
    assert "m of sag with the walker" in result["readout"]
    assert result["toolbar"] == 1 and result["note"].startswith("A visual preview")
    assert "v3-hidden" in result["status"]
    assert _violations(dom) == []


# On the page after the bundle: once ready, the controls of the level and the pin's state; at level full an anchor
# dragged by synthetic pointer events (the readout "edited", the moved line's profile asked for and shown), back
# to the found line, then the walk's buttons; the findings go into <pre id="result">
INTERACT_SCRIPT = _with_until("""
(function () {
  const root = document.getElementById("view3d");
  const out = {};
  const done = () => {
    const pre = document.createElement("pre");
    pre.id = "result";
    pre.textContent = JSON.stringify(out);
    document.body.appendChild(pre);
  };
  const readout = () => (document.querySelector(".v3-readout") || {}).innerText;
  // polls over the browser's frames (UNTIL_JS): the frame of the canvas resized by the filled readout, which places
  // the handles, comes before the drag
  /* until */
  // settled: no frame drawn during ten polls, each over a frame (the handles where the last frame put them), at
  // most `ms`
  const settled = (ms, then) => {
    let frames = root.dataset.frames, still = 0;
    until(() => {
      if (root.dataset.frames !== frames) { frames = root.dataset.frames; still = 0; return false; }
      return ++still > 10;
    }, ms, then);
  };
  const pointer = (type, target, x, y) => target.dispatchEvent(new PointerEvent(type, {clientX: x, clientY: y,
    pointerId: 7, button: 0, buttons: type === "pointerup" ? 0 : 1, bubbles: true, cancelable: true, isPrimary: true}));
  // the walk's stepping is tested in Node (test_viewer.py), here its button and state
  const walk = () => {
    const button = document.querySelector(".v3-walk");
    button.click();
    out.walking = [root.dataset.walk, button.textContent];
    document.querySelector(".v3-speed").click();
    out.speed4 = document.querySelector(".v3-speed").textContent;
    button.click();
    out.stopped = [root.dataset.walk, button.textContent];
    done();
  };
  until(() => root.dataset.ready === "1", 25000, (ready) => settled(15000, (still) => {
    out.ready = ready;
    out.settled = still;
    out.handles = document.querySelectorAll(".v3-handle").length;
    out.walkButton = document.querySelectorAll(".v3-walk").length;
    out.reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
    out.walkHidden = document.querySelector(".v3-walk").classList.contains("v3-hidden");
    out.reducedNote = !document.querySelector(".v3-reduced").classList.contains("v3-hidden");
    out.speed = (document.querySelector(".v3-speed") || {}).textContent;
    out.hint = document.querySelectorAll(".v3-hint").length;
    out.pin = root.dataset.pin;
    out.edit = root.dataset.edit;
    // the pin's tip and its leader (round 2, point 1): the leader from the walker's head up to the tip, the pin's
    // rotated box ending in the tip
    const leader = document.querySelector(".v3-leader"), tipBox = document.querySelector(".v3-pin-tip"), pinEl = document.querySelector(".v3-pin");
    if (leader && tipBox && pinEl) {
      const lr = leader.getBoundingClientRect(), tr = tipBox.getBoundingClientRect(), pr = pinEl.getBoundingClientRect();
      out.leader = {height: leader.style.height, transform: leader.style.transform, width: lr.width, top: lr.top, bottom: lr.bottom,
                    tipY: tr.top, pinBottom: pr.bottom, pinTop: pr.top, opacity: getComputedStyle(leader).backgroundColor};
    }
    if (!ready || !out.handles) { if (ready) walk(); else done(); return; }
    const [h1, h2] = [...document.querySelectorAll(".v3-handle")].map((h) => h.getBoundingClientRect());
    const handle = document.querySelectorAll(".v3-handle")[1];
    const x0 = h2.left + h2.width / 2, y0 = h2.top + h2.height / 2;
    const x1 = x0 + (h1.left + h1.width / 2 - x0) * 0.2, y1 = y0 + (h1.top + h1.height / 2 - y0) * 0.2;
    out.found = readout();
    pointer("pointerdown", handle, x0, y0);
    out.moving = root.dataset.edit;
    pointer("pointermove", handle, (x0 + x1) / 2, (y0 + y1) / 2);
    pointer("pointermove", handle, x1, y1);
    out.dragged = readout();
    out.reset = !document.querySelector(".v3-reset").classList.contains("v3-hidden");
    pointer("pointerup", handle, x1, y1);
    out.released = root.dataset.edit;
    until(() => root.dataset.edit === "checked" || root.dataset.edit === "error", 20000, () => {
      out.checked = root.dataset.edit;
      out.edited = readout();
      const box = document.querySelector(".v3-readout"), css = getComputedStyle(root);
      out.verdict = box.dataset.verdict;
      out.colour = box.dataset.colour;
      out.tokens = {bad: css.getPropertyValue("--bad").trim(), clear: css.getPropertyValue("--clear").trim(),
                    trees: css.getPropertyValue("--trees").trim()};
      out.filled = document.querySelector(".v3-readout").dataset.filled;
      document.querySelector(".v3-reset").click();
      out.back = readout();
      out.afterReset = root.dataset.edit;
      walk();
    });
  }));
})();
""")


def _interact_page(data) -> str:
    """The app's /view3d page with the CSP stub before its bundle and INTERACT_SCRIPT after it (as `_page`)."""
    from fastapi.testclient import TestClient
    folder = data / "runs" / "view3dinteract"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "stubs.js").write_text(CSP_STUB, encoding="utf-8")
    (folder / "test.js").write_text(INTERACT_SCRIPT, encoding="utf-8")
    app = web.create_app(str(data), token=TOKEN, start_scheduler=False)
    with TestClient(app, base_url=LOCAL) as client:
        page = client.get("/view3d").text
    script = '<script src="/app/view3d.js"></script>'
    (folder / "index.html").write_text(page.replace(
        script, f'<script src="stubs.js"></script>{script}<script src="test.js"></script>'), encoding="utf-8")
    return "runs/view3dinteract/index.html"


@pytest.mark.skipif(not os.path.exists(EDGE), reason="needs Microsoft Edge")
@pytest.mark.parametrize("level, reduced", [pytest.param("full", False, id="full"),
                                            pytest.param("phone", False, id="phone"),
                                            pytest.param("phone", True, id="phone-reduced")])
def test_view3d_interaction(clip_data, tmp_path, monkeypatch, level, reduced):
    """Level full: the anchors' handles, the hint, an anchor dragged (edited, its profile asked for after the
    release and shown), back to the found line; both levels: the walk's buttons (Walk / Stop, the speed), the pin shows
    over the walker at the first framing (it is a few pixels high); phone: no handle, no hint. Edge is told the
    user's motion preference: CI's Windows runner reports reduced motion (its animations are off), under which the
    walk does not start; with it, the walk's buttons hidden, its note shown and Walk starting nothing."""
    data, meta = clip_data
    for key, value in _offline_env().items():
        monkeypatch.setenv(key, value)
    row = _lines_of(data, meta["id"])[0]
    line = ",".join(f"{v:.7f}" for v in row[:4])
    page = _interact_page(data)
    motion = "--force-prefers-reduced-motion" if reduced else "--force-prefers-no-reduced-motion"
    with _server(data, start_scheduler=True) as port:
        dom = subprocess.run(
            [EDGE, "--headless", "--disable-gpu", f"--user-data-dir={tmp_path / 'edge'}", "--no-first-run",
             "--window-size=1200,800", f"--virtual-time-budget={VIRTUAL_BUDGET}", motion, "--dump-dom",
             f"http://127.0.0.1:{port}/{page}?level={level}#run={meta['id']}&line={line}"],
            capture_output=True, text=True, encoding="utf-8", timeout=EDGE_SECONDS).stdout
    found = re.search(r'<pre id="result">(.*?)</pre>', dom, re.S)
    assert found, dom[-3000:]
    result = json.loads(found.group(1).replace("&quot;", '"').replace("&amp;", "&"))
    print(level, result)
    assert result["ready"] and result["settled"], result
    assert result["pin"] == "1" and result["edit"] == ""
    leader = result["leader"]
    assert leader["height"].endswith("px") and float(leader["height"][:-2]) >= 2.5 and "rotate(" in leader["transform"], leader
    assert abs(leader["top"] - leader["tipY"]) <= 2 and leader["tipY"] < leader["bottom"], leader  # from the tip down to the head
    assert abs(leader["pinBottom"] - leader["tipY"]) <= 1.5 and leader["pinTop"] < leader["tipY"], leader  # the pin ends in its tip
    assert leader["opacity"].startswith("rgba(255, 255, 255, 0.65"), leader
    assert result["walkButton"] == 1 and result["speed"] == "×1"
    assert result["reduced"] is reduced, result
    assert result["walkHidden"] is reduced and result["reducedNote"] is reduced, result
    walking = ["0", "Walk"] if reduced else ["1", "Stop"]
    assert result["walking"] == walking and result["stopped"] == ["0", "Walk"] and result["speed4"] == "×4"
    if level == "phone":
        assert result["handles"] == 0 and result["hint"] == 0
    else:
        assert result["handles"] == 2 and result["hint"] == 1
        assert result["moving"] == "moving" and result["reset"] and result["released"] == "waiting"
        assert "Anchors moved: not saved" in result["dragged"] and "clear of the terrain" not in result["dragged"]
        assert result["checked"] == "checked" and result["filled"] == "1", result
        # the moved line of the clip runs into the terrain (about -2.8 m): it does not fit, in --bad
        assert "Anchors moved: not saved" in result["edited"] and "Does not fit: the clearance is -" in result["edited"]
        assert "m clear of the terrain" not in result["edited"] and "trees" not in result["edited"]
        assert result["verdict"] == "no_fit" and "#" + result["colour"] == result["tokens"]["bad"].lower(), result
        assert result["edited"] != result["found"]
        assert result["afterReset"] == "" and result["back"] == result["found"]
    assert _violations(dom) == []


# On the page after the bundle: once ready, Edges chosen in the imagery control (the root's data-imagery and
# data-edges, the triangles of a frame: the terrain twice and the pass's quad, the frames still once drawn), then
# Shaded again (the pass gone, a frame of one draw); the findings go into <pre id="result">
EDGES_SCRIPT = _with_until("""
(function () {
  const root = document.getElementById("view3d");
  const out = {errors: []};
  const error = console.error.bind(console);
  console.error = (...args) => { out.errors.push(args.map(String).join(" ").slice(0, 300)); error(...args); };
  const done = () => {
    const pre = document.createElement("pre");
    pre.id = "result";
    pre.textContent = JSON.stringify(out);
    document.body.appendChild(pre);
  };
  /* until */
  const button = (text) => [...document.querySelectorAll(".v3-toolbar [role=radio]")].find((b) => b.textContent.trim() === text);
  const state = () => ({imagery: root.dataset.imagery || null, edges: root.dataset.edges || null,
                        triangles: Number(root.dataset.triangles), frames: Number(root.dataset.frames)});
  until(() => root.dataset.ready === "1", 25000, (ready) => {
    out.ready = ready;
    out.buttons = [...document.querySelectorAll(".v3-toolbar .u-row [role=radio]")].map((b) => b.textContent.trim());
    if (!ready || !button("Edges")) { done(); return; }
    until(() => false, 1000, () => {
      out.shaded = state();
      button("Edges").click();
      until(() => Number(root.dataset.frames) > out.shaded.frames, 15000, () => {
        out.edges = state();
        out.checked = button("Edges").getAttribute("aria-checked");
        until(() => false, 2000, () => {  // loading meanwhile: a frame would come if one were asked for
          out.edgesLater = state();
          button("Shaded").click();
          until(() => Number(root.dataset.frames) > out.edgesLater.frames, 15000, () => {
            out.back = state();
            until(() => false, 2000, () => { out.backLater = state(); done(); });
          });
        });
      });
    });
  });
})();
""")


def _script_page(data, name: str, script: str) -> str:
    """The app's /view3d page with the CSP stub before its bundle and `script` after it (as `_page`), in
    runs/<name>/."""
    from fastapi.testclient import TestClient
    folder = data / "runs" / name
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "stubs.js").write_text(CSP_STUB, encoding="utf-8")
    (folder / "test.js").write_text(script, encoding="utf-8")
    app = web.create_app(str(data), token=TOKEN, start_scheduler=False)
    with TestClient(app, base_url=LOCAL) as client:
        page = client.get("/view3d").text
    script_tag = '<script src="/app/view3d.js"></script>'
    assert script_tag in page
    (folder / "index.html").write_text(page.replace(
        script_tag, f'<script src="stubs.js"></script>{script_tag}<script src="test.js"></script>'), encoding="utf-8")
    return f"runs/{name}/index.html"


@pytest.mark.skipif(not os.path.exists(EDGE), reason="needs Microsoft Edge")
@pytest.mark.parametrize("level", ["full", "phone"])
def test_view3d_edges(clip_data, tmp_path, monkeypatch, level):
    """The "Edges" look (docs/3d-view-contract.md, "Wave E"): the fourth kind of the imagery control (the clip's
    run has no orthophoto: Shaded and Edges), chosen it draws the pass (data-imagery="edges", data-edges="on",
    a frame of more triangles: the terrain once more and the pass's quad), only on demand (no frame while nothing
    changes), no violation of the CSP; back to Shaded the pass is gone (a frame of the scene's triangles)."""
    data, meta = clip_data
    for key, value in _offline_env().items():
        monkeypatch.setenv(key, value)
    row = _lines_of(data, meta["id"])[0]
    line = ",".join(f"{v:.7f}" for v in row[:4])
    page = _script_page(data, "view3dedges", EDGES_SCRIPT)
    with _server(data, start_scheduler=True) as port:
        dom = subprocess.run(
            [EDGE, "--headless", "--disable-gpu", f"--user-data-dir={tmp_path / 'edge'}", "--no-first-run",
             "--window-size=1200,800", f"--virtual-time-budget={VIRTUAL_BUDGET}", "--dump-dom",
             f"http://127.0.0.1:{port}/{page}?level={level}#run={meta['id']}&line={line}"],
            capture_output=True, text=True, encoding="utf-8", timeout=EDGE_SECONDS).stdout
    found = re.search(r'<pre id="result">(.*?)</pre>', dom, re.S)
    assert found, dom[-3000:]
    result = json.loads(found.group(1).replace("&quot;", '"').replace("&amp;", "&"))
    print(level, result)
    assert result["ready"], result
    assert result["buttons"] == ["Shaded", "Edges"], result
    assert result["errors"] == [], result["errors"]  # e.g. a shader that does not compile
    shaded, edges, later, back, back_later = (result[k] for k in ("shaded", "edges", "edgesLater", "back", "backLater"))
    assert shaded["imagery"] == "shaded" and shaded["edges"] is None
    assert edges["imagery"] == "edges" and edges["edges"] == "on" and result["checked"] == "true"
    # the terrain drawn twice (the colour and the normals) and the pass's two triangles
    assert edges["triangles"] > shaded["triangles"] + 2, result
    assert edges["frames"] > shaded["frames"] and later["frames"] == edges["frames"], result  # on demand only
    assert back["imagery"] == "shaded" and back["edges"] is None
    assert back["triangles"] == shaded["triangles"] and back_later["frames"] == back["frames"], result
    assert _violations(dom) == []


# On the page after the bundle, in a narrow window: once ready, the readout's clipping and the bar's controls'
# rectangles (each visible control of the toolbar, the readout's items and the bar's notes: none overlapping
# another or leaving the window), the imagery's select (shown instead of the segmented control, in sync with it),
# then again with the imagery's longest labels added to the select (four kinds: the clip's run has Shaded and Edges
# only) and, at level full, "Back to the found line" shown; the findings go into <pre id="result">
NARROW_SCRIPT = _with_until("""
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
  const shown = (e) => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  const name = (e) => (e.className || e.tagName) + ":" + (e.textContent || e.value || "").trim().slice(0, 30);
  const measure = () => {
    const readout = document.querySelector(".v3-readout");
    const items = [...document.querySelectorAll(".v3-toolbar input, .v3-toolbar button, .v3-toolbar select, " +
                                                ".v3-toolbar .u-small, .v3-toolbar .v3-reduced, .v3-toolbar .v3-zoom-value, " +
                                                ".v3-read, .v3-bar > .v3-note")]
      .filter(shown);
    const boxes = items.map((e) => [name(e), e.getBoundingClientRect()]);
    const overlaps = [], outside = [];
    for (let i = 0; i < boxes.length; i++) {
      const [a, r] = boxes[i];
      if (r.left < -0.5 || r.right > innerWidth + 0.5) outside.push(a);
      for (let j = i + 1; j < boxes.length; j++) {
        const [b, s] = boxes[j];
        const w = Math.min(r.right, s.right) - Math.max(r.left, s.left), h = Math.min(r.bottom, s.bottom) - Math.max(r.top, s.top);
        if (w > 0.5 && h > 0.5) overlaps.push([a, b]);
      }
    }
    const clipped = [readout, ...document.querySelectorAll(".v3-read")].filter(shown)
      .filter((e) => e.scrollWidth > e.clientWidth + 1).map(name);
    const stage = document.querySelector(".v3-stage").getBoundingClientRect();
    return {readout: readout.innerText, clipped, overlaps, outside, count: boxes.length,
            stage: stage.height / innerHeight, scroll: document.scrollingElement.scrollWidth - innerWidth,
            slider: document.querySelector(".v3-slider").getBoundingClientRect().width, view: root.dataset.view};
  };
  until(() => root.dataset.ready === "1", 25000, (ready) => {
    out.ready = ready;
    out.width = innerWidth;
    if (!ready) { done(); return; }
    const select = document.querySelector(".v3-select");
    out.select = !!select && shown(select);
    out.seg = [...document.querySelectorAll(".v3-toolbar .u-row .u-seg")].some(shown);
    out.options = select ? [...select.options].map((o) => o.textContent) : [];
    out.value = select && [select.value, root.dataset.imagery];
    out.first = measure();
    if (!select) { done(); return; }
    select.value = "edges";
    select.dispatchEvent(new Event("change"));
    until(() => root.dataset.edges === "on", 15000, () => {
      out.edges = [root.dataset.imagery, document.querySelector(".v3-toolbar .u-row [role=radio][aria-checked=true]")?.textContent];
      select.prepend(new Option("Satellite (Esri)", "x-esri"), new Option("Orthophoto", "x-ortho"));
      document.querySelector(".v3-reset")?.classList.remove("v3-hidden");
      out.four = measure();
      // the run's data credits folded behind their button, the button inside the window; unfolded by a click
      const toggle = document.querySelector(".v3-credits .u-credits-toggle"), folded = document.querySelector(".v3-credits .u-credits");
      out.credits = {toggle: !!toggle && shown(toggle), expanded: toggle?.getAttribute("aria-expanded"),
                     folded: !!folded && !shown(folded), right: toggle ? toggle.getBoundingClientRect().right <= innerWidth : null};
      toggle?.click();
      const after = document.querySelector(".v3-credits .u-credits");
      out.unfolded = {shown: !!after && shown(after), expanded: document.querySelector(".v3-credits .u-credits-toggle")?.getAttribute("aria-expanded"),
                      text: (after?.textContent || "").slice(0, 40)};
      // the walker's views as they come (the labels and Back to the found line as at the start): the switch, the
      // zoom (and the phone's motion) on a row of their own, the slider as wide as in the orbit
      select.querySelectorAll("option[value^=x-]").forEach((o) => o.remove());
      document.querySelector(".v3-reset")?.classList.add("v3-hidden");
      out.orbit = measure();
      const view = (name, then) => {
        const before = Number(root.dataset.frames);
        document.querySelector(`.v3-views [data-view=${name}]`).click();
        until(() => Number(root.dataset.frames) > before, 15000, () => { out[name] = measure(); then(); });
      };
      view("eyes", () => view("behind", done));
    });
  });
})();
""")


@pytest.mark.skipif(not os.path.exists(EDGE), reason="needs Microsoft Edge")
@pytest.mark.parametrize("level", ["full", "phone"])
def test_view3d_narrow_bar(clip_data, tmp_path, monkeypatch, level):
    """The bar under 600 px (docs/3d-view-contract.md, "Wave 4", V4a; headless Edge goes no narrower than about
    500 px): the readout's short form, nothing clipped (no hidden scroll), no control overlapping another or leaving
    the window, the imagery's select instead of the segmented control and in sync with it, the note that there is
    no imagery on a line of its own; the same with four kinds' labels and Back to the found line; the canvas keeps
    most of the height; the run's data credits (given to the clip's run here) folded behind their button and shown
    after a click."""
    data, meta = clip_data
    run_json = data / "runs" / meta["id"] / "run.json"
    saved = run_json.read_text("utf-8")
    run_json.write_text(json.dumps({**json.loads(saved), "attribution": [
        {"data": "Test model", "attribution": "Test survey", "licence": "CC BY 4.0", "url": "https://example.org/"}]}),
        encoding="utf-8")
    for key, value in _offline_env().items():
        monkeypatch.setenv(key, value)
    row = _lines_of(data, meta["id"])[0]
    line = ",".join(f"{v:.7f}" for v in row[:4])
    page = _script_page(data, "view3dnarrow", NARROW_SCRIPT)
    with _server(data, start_scheduler=True) as port:
        dom = subprocess.run(
            [EDGE, "--headless", "--disable-gpu", f"--user-data-dir={tmp_path / 'edge'}", "--no-first-run",
             "--window-size=500,900", f"--virtual-time-budget={VIRTUAL_BUDGET}", "--dump-dom",
             f"http://127.0.0.1:{port}/{page}?level={level}#run={meta['id']}&line={line}"],
            capture_output=True, text=True, encoding="utf-8", timeout=EDGE_SECONDS).stdout
    run_json.write_text(saved, encoding="utf-8")
    found = re.search(r'<pre id="result">(.*?)</pre>', dom, re.S)
    assert found, dom[-3000:]
    result = json.loads(found.group(1).replace("&quot;", '"').replace("&amp;", "&"))
    print(level, result)
    assert result["ready"], result
    assert result["width"] <= 600, result
    assert result["credits"] == {"toggle": True, "expanded": "false", "folded": True, "right": True}, result
    assert result["unfolded"]["shown"] and result["unfolded"]["expanded"] == "true", result
    assert result["unfolded"]["text"].startswith("Data: Test survey"), result
    assert result["select"] and not result["seg"], result
    assert result["options"] == ["Shaded", "Edges"] and result["value"] == ["shaded", "shaded"]
    assert result["edges"] == ["edges", "Edges"], result  # the select's choice marks the segmented control too
    first, four = result["first"], result["four"]
    assert "m clear" in first["readout"] and "sag " in first["readout"] and "of the terrain" not in first["readout"]
    for state in (first, four):
        assert state["clipped"] == [] and state["overlaps"] == [] and state["outside"] == [], state
        assert state["scroll"] <= 0 and state["stage"] > 0.6, state
    assert four["count"] == first["count"] + (1 if level == "full" else 0), result
    # the walker's views (docs/3d-view-contract.md, "Wave P"): nothing clipped, overlapping or outside, the zoom's
    # -, indicator and + shown, the walker's slider at least 40% of the window wide in every view (the switch on a
    # row of its own, in the walker's views with the zoom; at 412 px about 190 px, before about 74 px) and as wide as
    # in the orbit; at the phone level the bar as high in every view (its note and the look hint take turns)
    orbit = result["orbit"]
    assert orbit["view"] == "orbit" and orbit["slider"] >= 0.4 * result["width"], result
    for name in ("eyes", "behind"):
        state = result[name]
        assert state["view"] == name, result
        assert state["clipped"] == [] and state["overlaps"] == [] and state["outside"] == [], state
        assert state["scroll"] <= 0 and state["stage"] > 0.6, state
        assert state["count"] == orbit["count"] + 3, state
        assert state["slider"] >= 0.4 * result["width"] and abs(state["slider"] - orbit["slider"]) <= 0.5, state
        if level == "phone":
            assert abs(state["stage"] - orbit["stage"]) < 1e-6, state
    assert _violations(dom) == []


# On the page after the bundle: once ready, the views' switch (its buttons, the orbit's camera), the walker's eyes
# chosen (a frame drawn with its camera: the field of view, no handle or grip, the look hint), a drag on the canvas
# (the gaze turns, the eyes stay), the walker moved by its slider (the camera follows), behind the walker, then
# the orbit again (its camera as it was, the handles back); between the steps nothing is drawn while nothing
# changes; the findings go into <pre id="result">
VIEWS_SCRIPT = _with_until("""
(function () {
  const root = document.getElementById("view3d");
  const out = {errors: []};
  const error = console.error.bind(console);
  console.error = (...args) => { out.errors.push(args.map(String).join(" ").slice(0, 300)); error(...args); };
  const done = () => {
    const pre = document.createElement("pre");
    pre.id = "result";
    pre.textContent = JSON.stringify(out);
    document.body.appendChild(pre);
  };
  /* until */
  const frames = () => Number(root.dataset.frames);
  const shown = (sel) => [...document.querySelectorAll(sel)].filter((e) => getComputedStyle(e).display !== "none" &&
    e.getBoundingClientRect().width > 0).length;
  const state = () => ({view: root.dataset.view, camera: root.dataset.camera, frames: frames(),
    checked: [...document.querySelectorAll(".v3-views [role=radio]")].map((b) => b.getAttribute("aria-checked")),
    handles: shown(".v3-handle"), grips: shown(".v3-grip.v3-grab"), hint: shown(".v3-hint"), lookHint: shown(".v3-look-hint"),
    lookText: (document.querySelector(".v3-look-hint") || {}).textContent || null,
    phoneNote: shown(".v3-phone-note"), motion: shown(".v3-motion")});
  // a step: `act`, then the frame it asks for, then a pause in which no other frame may come
  const step = (name, act, then) => {
    const before = frames();
    act();
    until(() => frames() > before, 15000, () => {
      out[name] = state();
      until(() => false, 1500, () => { out[name].later = frames(); then(); });
    });
  };
  const pointer = (type, target, x, y) => target.dispatchEvent(new PointerEvent(type, {clientX: x, clientY: y,
    pointerId: 9, button: 0, buttons: type === "pointerup" ? 0 : 1, bubbles: true, cancelable: true, isPrimary: true}));
  const view = (name) => document.querySelector(`.v3-views [data-view=${name}]`);
  until(() => root.dataset.ready === "1", 25000, (ready) => {
    out.ready = ready;
    out.labels = [...document.querySelectorAll(".v3-views [role=radio]")].map((b) => b.getAttribute("aria-label"));
    if (!ready || !view("eyes")) { done(); return; }
    until(() => false, 1000, () => {
      out.orbit = state();
      step("eyes", () => view("eyes").click(), () => {
        const canvas = document.querySelector("canvas.v3-canvas"), r = canvas.getBoundingClientRect();
        const x = r.left + r.width / 2, y = r.top + r.height / 2;
        step("dragged", () => {
          pointer("pointerdown", canvas, x, y);
          pointer("pointermove", canvas, x + 120, y + 40);
          pointer("pointerup", canvas, x + 120, y + 40);
        }, () => {
          const slider = document.querySelector(".v3-slider");
          step("walked", () => { slider.value = String(Number(slider.max) * 0.25); slider.dispatchEvent(new Event("input")); }, () => {
            step("behind", () => view("behind").click(), () => {
              step("back", () => view("orbit").click(), done);
            });
          });
        });
      });
    });
  });
})();
""")


@pytest.mark.skipif(not os.path.exists(EDGE), reason="needs Microsoft Edge")
@pytest.mark.parametrize("level", ["full", "phone"])
def test_view3d_walker_views(clip_data, tmp_path, monkeypatch, level):
    """The walker's views (docs/3d-view-contract.md, "Wave F"): the switch (orbit first and chosen), the walker's
    eyes (data-view="eyes", its field of view 60° wide, no anchor's handle, no grip and no edit hint, the look hint, at
    the phone level in place of its note), a drag on the canvas turns the gaze and keeps the eyes where they are, the walker's slider moves the
    camera with it, behind the walker another camera and field of view, back to the orbit its camera exactly as it
    was and the handles back at level full; each step draws, and nothing more while nothing changes; no motion
    button without a touch screen, no violation of the CSP."""
    data, meta = clip_data
    for key, value in _offline_env().items():
        monkeypatch.setenv(key, value)
    row = _lines_of(data, meta["id"])[0]
    line = ",".join(f"{v:.7f}" for v in row[:4])
    page = _script_page(data, "view3dviews", VIEWS_SCRIPT)
    with _server(data, start_scheduler=True) as port:
        dom = subprocess.run(
            [EDGE, "--headless", "--disable-gpu", f"--user-data-dir={tmp_path / 'edge'}", "--no-first-run",
             "--window-size=1200,800", f"--virtual-time-budget={VIRTUAL_BUDGET}", "--dump-dom",
             f"http://127.0.0.1:{port}/{page}?level={level}#run={meta['id']}&line={line}"],
            capture_output=True, text=True, encoding="utf-8", timeout=EDGE_SECONDS).stdout
    found = re.search(r'<pre id="result">(.*?)</pre>', dom, re.S)
    assert found, dom[-3000:]
    result = json.loads(found.group(1).replace("&quot;", '"').replace("&amp;", "&"))
    print(level, result)
    assert result["ready"], result
    assert result["errors"] == [], result["errors"]
    assert result["labels"] == ["Orbit", "Walker's eyes", "Behind the walker"]
    cam = {k: [float(v) for v in result[k]["camera"].split(",")] for k in ("orbit", "eyes", "dragged", "walked",
                                                                          "behind", "back")}
    orbit, eyes, dragged, walked, behind, back = (result[k] for k in ("orbit", "eyes", "dragged", "walked", "behind",
                                                                      "back"))
    full = level == "full"
    assert orbit["view"] == "orbit" and orbit["checked"] == ["true", "false", "false"]
    assert orbit["handles"] == (2 if full else 0) and orbit["hint"] == (1 if full else 0) and orbit["lookHint"] == 0
    assert orbit["grips"] == (1 if full else 0) and orbit["motion"] == 0 and orbit["phoneNote"] == (0 if full else 1)
    assert eyes["view"] == "eyes" and eyes["checked"] == ["false", "true", "false"] and cam["eyes"][7] == 60
    assert eyes["handles"] == eyes["grips"] == eyes["hint"] == eyes["phoneNote"] == 0 and eyes["lookHint"] == 1
    assert eyes["motion"] == 0  # no touch screen here
    assert eyes["lookText"] == "Drag to look around, scroll to zoom."  # a fine pointer (the wheel), at both levels
    assert cam["eyes"][4] < 0  # a little down at first
    assert cam["dragged"][:3] == cam["eyes"][:3] and cam["dragged"][3:6] != cam["eyes"][3:6]  # the gaze turned
    assert cam["dragged"][4] > cam["eyes"][4]  # dragged down: looking up (grabbing the world)
    assert cam["walked"][:3] != cam["dragged"][:3] and cam["walked"][3:6] == cam["dragged"][3:6]  # follows
    assert behind["view"] == "behind" and cam["behind"][6] == 60 and cam["behind"][4] < 0
    assert cam["behind"][8] == 5  # the default distance (the clip's terrain is below that camera)
    assert behind["handles"] == behind["grips"] == 0
    assert back["view"] == "orbit" and cam["back"] == cam["orbit"], result  # the orbit's camera as it was
    assert back["handles"] == orbit["handles"] and back["lookHint"] == 0 and back["phoneNote"] == orbit["phoneNote"]
    for state in (eyes, dragged, walked, behind, back):
        assert state["later"] == state["frames"], result  # drawn on demand only
    assert _violations(dom) == []


# On the page after the bundle: once ready, the zoom's box hidden in the orbit; the walker's eyes chosen, the
# wheel (towards the screen: nearer), the + button, a two-finger pinch spreading the fingers (the angle narrower,
# the gaze not turned) and the - button, each a frame with its camera and the indicator; behind the walker the
# wheel (away: farther) and +; the eyes again (their zoom kept), the orbit (the box hidden, its camera as it was);
# the findings go into <pre id="result">
ZOOM_SCRIPT = _with_until("""
(function () {
  const root = document.getElementById("view3d");
  const out = {errors: []};
  const error = console.error.bind(console);
  console.error = (...args) => { out.errors.push(args.map(String).join(" ").slice(0, 300)); error(...args); };
  const done = () => {
    const pre = document.createElement("pre");
    pre.id = "result";
    pre.textContent = JSON.stringify(out);
    document.body.appendChild(pre);
  };
  /* until */
  const frames = () => Number(root.dataset.frames);
  const box = () => document.querySelector(".v3-zoom");
  const state = () => ({view: root.dataset.view, camera: root.dataset.camera,
    box: !!box() && getComputedStyle(box()).display !== "none",
    value: document.querySelector(".v3-zoom-value")?.textContent,
    labels: [...document.querySelectorAll(".v3-zoom button")].map((b) => b.getAttribute("aria-label"))});
  const step = (name, act, then) => {
    const before = frames();
    act();
    until(() => frames() > before, 15000, () => { out[name] = state(); until(() => false, 500, then); });
  };
  const canvas = () => document.querySelector("canvas.v3-canvas");
  const pointer = (type, id, x, y, primary) => canvas().dispatchEvent(new PointerEvent(type, {clientX: x, clientY: y,
    pointerId: id, pointerType: "touch", button: 0, buttons: type === "pointerup" ? 0 : 1, bubbles: true,
    cancelable: true, isPrimary: primary}));
  const wheel = (deltaY) => canvas().dispatchEvent(new WheelEvent("wheel", {deltaY, deltaMode: 0, bubbles: true, cancelable: true}));
  const click = (sel) => document.querySelector(sel).click();
  until(() => root.dataset.ready === "1", 25000, (ready) => {
    out.ready = ready;
    if (!ready) { done(); return; }
    until(() => false, 1000, () => {
      out.orbit = state();
      step("eyes", () => click(".v3-views [data-view=eyes]"), () => {
        step("wheeled", () => { out.wheelCancelled = !wheel(-200); }, () => {
          step("plus", () => click(".v3-zoom-in"), () => {
            const r = canvas().getBoundingClientRect(), x = r.left + r.width / 2, y = r.top + r.height / 2;
            step("pinched", () => {
              pointer("pointerdown", 21, x - 40, y, true);
              pointer("pointerdown", 22, x + 40, y, false);
              pointer("pointermove", 22, x + 120, y + 30, false);
              pointer("pointermove", 21, x - 120, y - 30, true);
            }, () => {
              pointer("pointerup", 22, x + 120, y + 30, false);
              pointer("pointermove", 21, x - 20, y + 60, true);  // the finger left after a pinch turns nothing
              pointer("pointerup", 21, x - 20, y + 60, true);
              step("minus", () => click(".v3-zoom-out"), () => {
                step("behind", () => click(".v3-views [data-view=behind]"), () => {
                  step("farther", () => wheel(300), () => {
                    step("nearer", () => click(".v3-zoom-in"), () => {
                      step("eyesAgain", () => click(".v3-views [data-view=eyes]"), () => {
                        step("back", () => click(".v3-views [data-view=orbit]"), done);
                      });
                    });
                  });
                });
              });
            });
          });
        });
      });
    });
  });
})();
""")


@pytest.mark.skipif(not os.path.exists(EDGE), reason="needs Microsoft Edge")
def test_view3d_walker_zoom(clip_data, tmp_path, monkeypatch):
    """The zoom of the walker's views (docs/3d-view-contract.md, "Wave F2"): hidden in the orbit; in the eyes the
    wheel, the + button and a two-finger pinch narrow the horizontal angle (60° at first, the vertical one from the
    canvas's aspect), the pinch without turning the gaze, the - button widens it, the indicator a factor; behind
    the walker the wheel moves the camera farther and + nearer (its distance in data-camera, the indicator in
    metres); each view keeps its zoom; the orbit's camera unchanged; no violation of the CSP."""
    data, meta = clip_data
    for key, value in _offline_env().items():
        monkeypatch.setenv(key, value)
    row = _lines_of(data, meta["id"])[0]
    line = ",".join(f"{v:.7f}" for v in row[:4])
    page = _script_page(data, "view3dzoom", ZOOM_SCRIPT)
    with _server(data, start_scheduler=True) as port:
        dom = subprocess.run(
            [EDGE, "--headless", "--disable-gpu", f"--user-data-dir={tmp_path / 'edge'}", "--no-first-run",
             "--window-size=1200,800", f"--virtual-time-budget={VIRTUAL_BUDGET}", "--dump-dom",
             f"http://127.0.0.1:{port}/{page}?level=full#run={meta['id']}&line={line}"],
            capture_output=True, text=True, encoding="utf-8", timeout=EDGE_SECONDS).stdout
    found = re.search(r'<pre id="result">(.*?)</pre>', dom, re.S)
    assert found, dom[-3000:]
    result = json.loads(found.group(1).replace("&quot;", '"').replace("&amp;", "&"))
    print(result)
    assert result["ready"], result
    assert result["errors"] == [], result["errors"]
    names = ("orbit", "eyes", "wheeled", "plus", "pinched", "minus", "behind", "farther", "nearer", "eyesAgain", "back")
    cam = {k: [float(v) for v in result[k]["camera"].split(",")] for k in names}
    assert not result["orbit"]["box"] and not result["back"]["box"]
    assert result["eyes"]["box"] and result["eyes"]["labels"] == ["Zoom out", "Zoom in"]
    # eyes: 60° wide, the vertical angle from the aspect (wider than tall here)
    vertical, horizontal = cam["eyes"][6], cam["eyes"][7]
    assert horizontal == 60 and vertical < 60 and result["eyes"]["value"] == "×1"
    assert result["wheelCancelled"]  # the page keeps the wheel in the walker's views
    assert cam["wheeled"][7] < 60 and cam["wheeled"][:6] == cam["eyes"][:6]
    assert cam["plus"][7] < cam["wheeled"][7] and result["plus"]["value"] == "×2"  # onto the grid: ×1.5 → ×2
    assert cam["pinched"][7] < cam["plus"][7] and cam["pinched"][3:6] == cam["plus"][3:6]  # zoomed, not turned
    assert cam["minus"][7] > cam["pinched"][7] and cam["minus"][3:6] == cam["plus"][3:6]
    assert result["minus"]["value"].startswith("×")
    # behind: 5 m at first, the wheel away from the screen farther, + nearer
    assert result["behind"]["value"] == "5 m" and cam["behind"][6] == 60
    assert cam["farther"][8] > cam["behind"][8] and cam["nearer"][8] < cam["farther"][8]
    assert result["farther"]["value"].endswith(" m") and result["nearer"]["value"] == "7.1 m"  # 9.1 m, onto the grid
    assert cam["eyesAgain"][7] == cam["minus"][7] and result["eyesAgain"]["value"] == result["minus"]["value"]
    assert cam["back"] == cam["orbit"] and len(cam["orbit"]) == 8
    assert _violations(dom) == []


# On the page after the bundle, in a desktop window (round 2, points 2 and 6): once ready, the activity pill (an
# element of the stage with role "status", hidden: the clip's run has no orthophoto, so no tiles are counted here;
# the count is tested on a fake scene in test_viewer.py), no status element of the imagery in the toolbar, and the
# credits box: its data credits open behind their button at this width, the box's type and surface, a click folding
# them (the choice kept in localStorage, the focus on the new button) and another unfolding them
CREDITS_SCRIPT = """
(function () {
  const root = document.getElementById("view3d");
  const out = {};
  const done = () => {
    const pre = document.createElement("pre");
    pre.id = "result";
    pre.textContent = JSON.stringify(out);
    document.body.appendChild(pre);
  };
  const shown = (e) => { if (!e) return false; const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  const store = () => { try { return localStorage.getItem("findaline.view3d.credits"); } catch (e) { return "error"; } };
  const state = () => {
    const toggle = document.querySelector(".v3-credits .u-credits-toggle"), body = document.querySelector(".v3-credits .u-credits");
    return {toggle: shown(toggle), expanded: toggle && toggle.getAttribute("aria-expanded"), body: shown(body),
            focused: !!toggle && document.activeElement === toggle, stored: store(), text: body ? body.textContent.slice(0, 40) : null};
  };
  let n = 0;
  const until = (test, ms, then) => {
    const started = Date.now();
    const poll = () => {
      if (test()) then(true);
      else if (Date.now() - started > ms) then(false);
      else fetch("stubs.js?poll=" + (++n)).then(() => setTimeout(poll, 100), () => setTimeout(poll, 100));
    };
    poll();
  };
  try { localStorage.removeItem("findaline.view3d.credits"); } catch (e) { /* none */ }
  until(() => root.dataset.ready === "1", 25000, (ready) => {
    out.ready = ready;
    if (!ready) { done(); return; }
    const pill = document.querySelector(".v3-stage > .v3-activity");
    out.pill = {role: pill && pill.getAttribute("role"), hidden: !shown(pill)};
    out.statusInToolbar = document.querySelectorAll(".v3-toolbar .v3-imagery-status").length;
    out.width = innerWidth;
    out.start = state();
    const box = document.querySelector(".v3-credits"), css = getComputedStyle(box), page = getComputedStyle(root);
    out.box = {fontSize: css.fontSize, border: css.borderTopWidth, background: css.backgroundColor,
               surface: page.getPropertyValue("--surface").trim(), shadow: css.boxShadow !== "none",
               first: box === box.parentElement.firstElementChild, parent: box.parentElement.className,
               inStage: box.getBoundingClientRect().right <= innerWidth && box.getBoundingClientRect().bottom <= innerHeight};
    document.querySelector(".v3-credits .u-credits-toggle").click();
    out.folded = state();
    document.querySelector(".v3-credits .u-credits-toggle").click();
    out.unfolded = state();
    done();
  });
})();
"""


@pytest.mark.skipif(not os.path.exists(EDGE), reason="needs Microsoft Edge")
@pytest.mark.parametrize("level", ["full", "phone"])
def test_view3d_credits_and_pill(clip_data, tmp_path, monkeypatch, level):
    """Round 2, points 2 and 6, in a desktop window: the imagery's count is no longer an element of the toolbar and
    the activity pill is there (role status, hidden while nothing loads); the data credits (given to the clip's run
    here) behind their button at this width too, open at the start, folded and unfolded by clicks with the choice
    kept in the browser and the focus on the button; the box at 12.5 px on the surface with a border and a shadow,
    the first child of the stage's bottom column, inside the window."""
    data, meta = clip_data
    run_json = data / "runs" / meta["id"] / "run.json"
    saved = run_json.read_text("utf-8")
    run_json.write_text(json.dumps({**json.loads(saved), "attribution": [
        {"data": "Test model", "attribution": "Test survey", "licence": "CC BY 4.0", "url": "https://example.org/"}]}),
        encoding="utf-8")
    for key, value in _offline_env().items():
        monkeypatch.setenv(key, value)
    row = _lines_of(data, meta["id"])[0]
    line = ",".join(f"{v:.7f}" for v in row[:4])
    page = _script_page(data, "view3dcredits", CREDITS_SCRIPT)
    with _server(data, start_scheduler=True) as port:
        dom = subprocess.run(
            [EDGE, "--headless", "--disable-gpu", f"--user-data-dir={tmp_path / 'edge'}", "--no-first-run",
             "--window-size=1200,800", "--virtual-time-budget=90000", "--dump-dom",
             f"http://127.0.0.1:{port}/{page}?level={level}#run={meta['id']}&line={line}"],
            capture_output=True, text=True, encoding="utf-8", timeout=300).stdout
    run_json.write_text(saved, encoding="utf-8")
    found = re.search(r'<pre id="result">(.*?)</pre>', dom, re.S)
    assert found, dom[-3000:]
    result = json.loads(found.group(1).replace("&quot;", '"').replace("&amp;", "&"))
    print(level, result)
    assert result["ready"], result
    assert result["pill"] == {"role": "status", "hidden": True} and result["statusInToolbar"] == 0, result
    assert result["width"] >= 768
    start = result["start"]
    assert start["toggle"] and start["expanded"] == "true" and start["body"] and start["stored"] is None, result
    assert start["text"].startswith("Data: Test survey"), result
    box = result["box"]
    assert box["fontSize"] == "12.5px" and box["border"] == "1px" and box["shadow"] and box["first"], result
    assert box["parent"] == "v3-bottom" and box["inStage"], result
    assert box["background"].startswith("rgb("), result  # the surface's full colour, not a translucent one
    folded = result["folded"]
    assert folded["toggle"] and folded["expanded"] == "false" and not folded["body"], result
    assert folded["stored"] == "folded" and folded["focused"], result
    unfolded = result["unfolded"]
    assert unfolded["expanded"] == "true" and unfolded["body"] and unfolded["stored"] == "open" and unfolded["focused"]
    assert _violations(dom) == []
