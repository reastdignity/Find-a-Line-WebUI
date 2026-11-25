"""The 3D view's loading line counts its megabytes as every size the pages show (line volume's round 7, step 2d as
reduced; view3d/main.ts `mb`, fetchPatch's `say`): a MB is 10^6 bytes, so a patch of 200 000 000 bytes with
30 000 000 of them in reads "30.0 of 200.0 MB" (with 2^20 bytes a MB it read "28.6 of 190.7 MB").

Playwright's Edge over the local app on a thread (test_web's `_server`) with the clip's run, offline; an init script
stands in for the patch's request (download.ts' XMLHttpRequest), which never ends: the page stays at its download
stage and never draws, so no wait counts its frames (test_view3d.UNTIL_JS is for the --dump-dom tests; the Playwright
tests of the 3D page wait with wait_for_function, as this one). Run from PowerShell (.claude/rules/browser-tests.md)."""

import os
import sys
from urllib.parse import quote

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

pytest.importorskip("httpx2")

from test_rename_home_page import NAME_A, RUN_A, WORDS, Browser  # noqa: E402
from test_shell_c import copy_clip  # noqa: E402
from test_shell_c_view_map import DESKTOP, view_clip  # noqa: E402,F401
from test_shell_c_view_map import WAIT as VIEW_WAIT  # noqa: E402
from test_web import EDGE, _lines_of, _playwright, _server  # noqa: E402

pytestmark = pytest.mark.skipif(not os.path.exists(EDGE) or not _playwright(),
                                reason="needs Microsoft Edge and Playwright (group ui)")
# The deadline of every wait for the page, ms (FINDALINE_SIZE_PAGE_WAIT lowers it for a run against a page without
# the change)
WAIT = int(os.environ.get("FINDALINE_SIZE_PAGE_WAIT", VIEW_WAIT))

# The patch's request (/api/patch) never sent: after the page's first 100 ms (download.ts reports no progress before)
# it answers "headers in" with a body of 200 000 000 bytes (Content-Length, nothing compressed) and one progress
# event of 30 000 000, then nothing (as tools/ui_shots.py's RUN_STORE_LOADING does for a run's store)
PATCH_LOADING = r"""(() => {
  const open = XMLHttpRequest.prototype.open, send = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function (method, url) {
    this.patchStandIn = new URL(String(url), location.href).pathname === '/api/patch';
    return open.apply(this, arguments);
  };
  XMLHttpRequest.prototype.send = function () {
    if (!this.patchStandIn) return send.apply(this, arguments);
    window.PATCH_ASKED = (window.PATCH_ASKED || 0) + 1;
    setTimeout(() => {
      Object.defineProperties(this, {readyState: {value: XMLHttpRequest.HEADERS_RECEIVED}, status: {value: 200}});
      this.getResponseHeader = (name) => name.toLowerCase() === 'content-length' ? '200000000' : null;
      this.onreadystatechange?.(new Event('readystatechange'));
      this.onprogress?.(new ProgressEvent('progress', {lengthComputable: true, loaded: 30000000, total: 200000000}));
    }, Math.max(0, 101 - performance.now()));
  };
})();"""
# The status over the stage: the root's stage, the message, the bar's value
STATUS = """() => { const root = document.getElementById('view3d'), bar = root.querySelector('.v3-status .v3-prog');
  return {stage: root.dataset.stage, message: (root.querySelector('.v3-status .v3-message') || {}).textContent,
          now: bar && bar.getAttribute('aria-valuenow'), asked: window.PATCH_ASKED || 0}; }"""


def test_the_terrains_download_in_megabytes(tmp_path, view_clip):
    """While the patch downloads (200 000 000 bytes, 30 000 000 of them in) the 3D view says "Downloading the
    terrain… 30.0 of 200.0 MB" over the stage, its bar at 15: megabytes of 10^6 bytes, with the catalogue's text."""
    data = tmp_path / "local"
    data.mkdir()
    copy_clip(view_clip, data, RUN_A, NAME_A)
    line = ",".join(f"{v:.7f}" for v in _lines_of(data, RUN_A)[0][:4])
    with _server(data) as port:
        site = f"http://127.0.0.1:{port}"
        with Browser(site) as browser:
            page = browser.page(DESKTOP, None, PATCH_LOADING)
            page.set_default_timeout(WAIT)
            page.goto(f"{site}/view3d?level=full#run={quote(RUN_A, safe='')}&line={quote(line, safe='')}")
            page.wait_for_function("() => { const root = document.getElementById('view3d'); return root && root.dataset.stage === 'download' "
                                   "&& root.querySelector('.v3-status .v3-prog')?.getAttribute('aria-valuenow') === '15'; }")
            status = page.evaluate(STATUS)
    assert status == {"stage": "download", "message": "Downloading the terrain… 30.0 of 200.0 MB", "now": "15", "asked": 1}, status
    assert WORDS["ui.view3d.loading_download"] == "Downloading the terrain… {{done}} of {{total}} MB"
