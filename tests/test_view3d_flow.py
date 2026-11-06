"""Round 2 of the 3D view end to end (docs/3d-view-contract.md, "Round 2"): the page against the app's own routes,
where the tests of each side use stubbed answers. On a run of the Żabi Koń clip given its surface model: with "Only
valid lines" on, the reach of anchor 1 comes from GET /api/reach and shows; with "Trees and buildings" on, the block
comes from GET /api/patch?part=canopy and is drawn; no Content-Security-Policy violation. Run it from PowerShell
(headless Edge prints nothing from Git Bash)."""

import json
import os
import re
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_patch import _offline_env, clip_data  # noqa: E402,F401 (a run of the clip, computed once)
from test_reach import with_surface  # noqa: E402
from test_view3d import EDGE_SECONDS, VIRTUAL_BUDGET, _with_until  # noqa: E402 (the frame-counted waits)
from test_web import EDGE, _lines_of, _server, _violations  # noqa: E402

# After the page is ready: the tool "valid" on and the reach of anchor 1 awaited (the first reach of a quick lane
# loads numba and builds the sag table), then the tool "trees" on and the canopy awaited. The waits count the
# browser's frames (test_view3d.UNTIL_JS).
FLOW_SCRIPT = _with_until(r"""
(() => {
  const root = document.getElementById("view3d"), out = {};
  const done = () => {
    const pre = document.createElement("pre");
    pre.id = "result";
    pre.textContent = JSON.stringify(out);
    document.body.appendChild(pre);
  };
  /* until */
  const tool = (id) => document.querySelector('.v3-tool[data-tool="' + id + '"]');
  const trees = () => {
    const button = tool("trees");
    out.treesTool = !!button;
    if (!button) { done(); return; }
    button.click();
    until(() => root.dataset.trees === "on" || root.dataset.trees === "failed", 60000, () => {
      out.trees = root.dataset.trees;
      out.treesTriangles = root.dataset.treesTriangles || "";
      out.treesPressed = button.getAttribute("aria-pressed");
      out.notes = [...document.querySelectorAll(".v3-note")].map((p) => p.textContent);
      done();
    });
  };
  until(() => root.dataset.ready === "1", 40000, (ready) => {
    out.ready = ready;
    out.stage = root.dataset.stage;
    out.tools = [...document.querySelectorAll(".v3-tool")].map((b) => b.dataset.tool);
    if (!ready) { done(); return; }
    const valid = tool("valid");
    out.validTool = !!valid;
    if (!valid) { trees(); return; }
    valid.click();
    out.pill = !document.querySelector(".v3-activity").classList.contains("v3-hidden");
    until(() => root.dataset.reach === "1" || document.querySelector(".v3-reach-failed:not(.v3-hidden)"), 90000, () => {
      out.reach = root.dataset.reach;
      out.reachFailed = document.querySelector(".v3-reach-failed:not(.v3-hidden)")?.textContent || "";
      out.validPressed = valid.getAttribute("aria-pressed");
      trees();
    });
  });
})();
""")


def _flow_page(data) -> str:
    """The app's /view3d page with the CSP stub before its bundle and FLOW_SCRIPT after it (as test_view3d's)."""
    from fastapi.testclient import TestClient
    from test_web import CSP_STUB, LOCAL, TOKEN, web
    folder = data / "runs" / "view3dflow"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "stubs.js").write_text(CSP_STUB, encoding="utf-8")
    (folder / "test.js").write_text(FLOW_SCRIPT, encoding="utf-8")
    app = web.create_app(str(data), token=TOKEN, start_scheduler=False)
    with TestClient(app, base_url=LOCAL) as client:
        page = client.get("/view3d").text
    script = '<script src="/app/view3d.js"></script>'
    assert script in page
    (folder / "index.html").write_text(page.replace(
        script, f'<script src="stubs.js"></script>{script}<script src="test.js"></script>'), encoding="utf-8")
    return "runs/view3dflow/index.html"


@pytest.mark.skipif(not os.path.exists(EDGE), reason="needs Microsoft Edge")
def test_valid_lines_and_trees_against_the_app(clip_data, tmp_path, monkeypatch):
    data, meta = clip_data
    for key, value in _offline_env().items():
        monkeypatch.setenv(key, value)
    # The run with the clip's surface model (the fixture's run has none): the page then offers the trees
    (data / "runs" / meta["id"] / "run.json").write_text(json.dumps(with_surface(meta, "mark")), encoding="utf-8")
    row = _lines_of(data, meta["id"])[0]
    line = ",".join(str(v) for v in row[:4])  # keys.ts lineCoords
    page = _flow_page(data)
    with _server(data, start_scheduler=True) as port:
        dom = subprocess.run(
            [EDGE, "--headless", "--disable-gpu", f"--user-data-dir={tmp_path / 'edge'}", "--no-first-run",
             "--window-size=1200,800", f"--virtual-time-budget={VIRTUAL_BUDGET}", "--force-prefers-no-reduced-motion", "--dump-dom",
             f"http://127.0.0.1:{port}/{page}?level=full#run={meta['id']}&line={line}"],
            capture_output=True, text=True, encoding="utf-8", timeout=EDGE_SECONDS).stdout
    found = re.search(r'<pre id="result">(.*?)</pre>', dom, re.S)
    assert found, dom[-3000:]
    r = json.loads(found.group(1).replace("&quot;", '"').replace("&amp;", "&"))
    print(r)
    assert r["ready"], r
    assert r["validTool"] and r["treesTool"], r  # the run has a surface model: both tools
    assert {"valid", "trees", "profile", "save"} <= set(r["tools"]), r  # their places come from the CSS order
    # the reach of anchor 1 from the server's route
    assert r["pill"] and r["reach"] == "1" and r["reachFailed"] == "" and r["validPressed"] == "true", r
    # the canopy from the server's route, drawn
    assert r["trees"] == "on" and int(r["treesTriangles"]) > 0 and r["treesPressed"] == "true", r
    assert _violations(dom) == []
