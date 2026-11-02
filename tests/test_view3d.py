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

# On the page after the bundle: waits for the page's ready marker (the terrain drawn and the profile in), then
# writes what it found into <pre id="result">
READY_SCRIPT = """
(function () {
  const root = document.getElementById("view3d");
  const done = (what) => {
    const out = document.createElement("pre");
    out.id = "result";
    out.textContent = JSON.stringify(what);
    document.body.appendChild(out);
  };
  const started = Date.now();
  const wait = () => {
    if (root.dataset.ready === "1") {
      const frames = Number(root.dataset.frames);
      setTimeout(() => done({ready: true, frames: [frames, Number(root.dataset.frames)], triangles: Number(root.dataset.triangles), vertices: Number(root.dataset.vertices),
        maxError: Number(root.dataset.maxError), readout: (document.querySelector(".v3-readout") || {}).textContent,
        filled: (document.querySelector(".v3-readout") || {dataset: {}}).dataset.filled || null,
        profileError: root.dataset.profileError || null, toolbar: document.querySelectorAll(".v3-toolbar input[type=range]").length,
        note: (document.querySelector(".v3-note") || {}).textContent, status: (document.querySelector(".v3-status") || {}).className,
        canvas: document.querySelectorAll("canvas.v3-canvas").length}), 2000);
    } else if (Date.now() - started > 25000) {
      done({ready: false, status: (document.querySelector(".v3-status") || {}).textContent, data: {...root.dataset}});
    } else setTimeout(wait, 100);
  };
  wait();
})();
"""


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
             "--window-size=1200,800", "--virtual-time-budget=60000", "--dump-dom",
             f"http://127.0.0.1:{port}/{page}?level={level}#run={meta['id']}&line={line}"],
            capture_output=True, text=True, encoding="utf-8", timeout=240).stdout
    found = re.search(r'<pre id="result">(.*?)</pre>', dom, re.S)
    assert found, dom[-3000:]
    result = json.loads(found.group(1).replace("&quot;", '"').replace("&amp;", "&"))
    print(level, result)
    assert result["ready"], result
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
INTERACT_SCRIPT = """
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
  const until = (test, ms, then) => {
    const started = Date.now();
    const poll = () => { if (test()) then(true); else if (Date.now() - started > ms) then(false); else setTimeout(poll, 100); };
    poll();
  };
  const pointer = (type, target, x, y) => target.dispatchEvent(new PointerEvent(type, {clientX: x, clientY: y,
    pointerId: 7, button: 0, buttons: type === "pointerup" ? 0 : 1, bubbles: true, cancelable: true, isPrimary: true}));
  // headless Edge draws no animation frames under a virtual time budget: the walk's stepping is tested in Node
  // (test_viewer.py), here its button and state
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
  until(() => root.dataset.ready === "1", 25000, (ready) => {
    out.ready = ready;
    out.handles = document.querySelectorAll(".v3-handle").length;
    out.walkButton = document.querySelectorAll(".v3-walk").length;
    out.speed = (document.querySelector(".v3-speed") || {}).textContent;
    out.hint = document.querySelectorAll(".v3-hint").length;
    out.pin = root.dataset.pin;
    out.edit = root.dataset.edit;
    if (!ready || !out.handles) { setTimeout(() => { if (ready) walk(); else done(); }, 500); return; }
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
      out.filled = document.querySelector(".v3-readout").dataset.filled;
      document.querySelector(".v3-reset").click();
      out.back = readout();
      out.afterReset = root.dataset.edit;
      walk();
    });
  });
})();
"""


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
@pytest.mark.parametrize("level", ["full", "phone"])
def test_view3d_interaction(clip_data, tmp_path, monkeypatch, level):
    """Level full: the anchors' handles, the hint, an anchor dragged (edited, its profile asked for after the
    release and shown), back to the found line; both levels: the walk's buttons (Walk / Stop, the speed), the pin shows
    over the walker at the first framing (it is a few pixels high); phone: no handle, no hint."""
    data, meta = clip_data
    for key, value in _offline_env().items():
        monkeypatch.setenv(key, value)
    row = _lines_of(data, meta["id"])[0]
    line = ",".join(f"{v:.7f}" for v in row[:4])
    page = _interact_page(data)
    with _server(data, start_scheduler=True) as port:
        dom = subprocess.run(
            [EDGE, "--headless", "--disable-gpu", f"--user-data-dir={tmp_path / 'edge'}", "--no-first-run",
             "--window-size=1200,800", "--virtual-time-budget=90000", "--dump-dom",
             f"http://127.0.0.1:{port}/{page}?level={level}#run={meta['id']}&line={line}"],
            capture_output=True, text=True, encoding="utf-8", timeout=300).stdout
    found = re.search(r'<pre id="result">(.*?)</pre>', dom, re.S)
    assert found, dom[-3000:]
    result = json.loads(found.group(1).replace("&quot;", '"').replace("&amp;", "&"))
    print(level, result)
    assert result["ready"], result
    assert result["pin"] == "1" and result["edit"] == ""
    assert result["walkButton"] == 1 and result["speed"] == "×1"
    assert result["walking"] == ["1", "Stop"] and result["stopped"] == ["0", "Walk"] and result["speed4"] == "×4"
    if level == "phone":
        assert result["handles"] == 0 and result["hint"] == 0
    else:
        assert result["handles"] == 2 and result["hint"] == 1
        assert result["moving"] == "moving" and result["reset"] and result["released"] == "waiting"
        assert "Anchors moved: not saved" in result["dragged"] and "clear of the terrain" not in result["dragged"]
        assert result["checked"] == "checked" and result["filled"] == "1", result
        assert "Anchors moved: not saved" in result["edited"] and "m clear of the terrain" in result["edited"]
        assert result["edited"] != result["found"]
        assert result["afterReset"] == "" and result["back"] == result["found"]
    assert _violations(dom) == []
