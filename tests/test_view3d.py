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
