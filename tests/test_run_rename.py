"""Renaming a run (docs/line-volume/spec-store.md section 5, step 2g; the public site only): the map page's template
in runs.py, where the web process may import it (runs.map_page, kept in mapping under its names), the name rule
(runs.run_name), runs.rename_run and the route POST /api/runs/<id>."""

import html
import json
import os
import subprocess
import sys

import mapping
import runs as rn

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# mapping.MAP_HTML at b1434458 (before the template moved to runs.py): a search's map.html stays byte for byte this
FROZEN_MAP_HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} - Find-a-Line</title>
<link rel="stylesheet" href="../{viewer}/viewer.css">
</head><body><div id="map"></div>
<script src="../runs.js"></script>
<script src="../{viewer}/viewer.js"></script>
<main id="{notice_id}" class="ui fal-disk" data-run="{run}"><div class="fal-disk-box">
<h1 class="fal-disk-name">{title}</h1>
<p class="fal-disk-text">{notice}</p>
<pre class="fal-disk-command"><code>findaline.py view {run}</code></pre>
</div></main>
</body></html>
"""

# The modules the web process never imports (CLAUDE.md "Always"; the template's move keeps mapping out of it)
WORKERS_MODULES = ("mapping", "search", "numba", "linestore", "pyarrow", "linesearch")


def test_the_map_page_moved_unchanged():
    """runs.map_page writes what mapping.map_page wrote at b1434458 (the frozen template, the same escaping), and
    mapping keeps every moved name as the same object."""
    import messages
    for name in ("DISK_NOTICE", "MAP_HTML", "VIEWER_FOLDER", "map_page"):
        assert getattr(mapping, name) is getattr(rn, name), name
    assert (rn.VIEWER_FOLDER, rn.DISK_NOTICE) == ("_viewer", "disk-notice")
    for run in ({"id": "2026-11-23_100000_X_0123456789abcdef", "name": "Żabi Koń"},
                {"id": "r<1>", "name": 'A <b>&amp; "quoted" \'one\''}):
        expected = FROZEN_MAP_HTML.format(title=html.escape(run["name"]), viewer="_viewer", notice_id="disk-notice",
                                          run=html.escape(run["id"]),
                                          notice=html.escape(messages.text("ui.map.disk_notice")))
        assert rn.map_page(run) == expected == mapping.map_page(run)


def _modules_of_the_web_process(tmp_path, extra: str = "") -> list:
    """The modules of WORKERS_MODULES a fresh process holds after importing web, making the local app, listing the
    runs and running `extra` (code with `c`, the TestClient, and `rn`, runs)."""
    (tmp_path / "local").mkdir(exist_ok=True)
    code = (f"import json, sys; sys.path.insert(0, {REPO!r}); import web\n"
            "import runs as rn\n"
            "from fastapi.testclient import TestClient\n"
            f"c = TestClient(web.create_app({str(tmp_path / 'local')!r}, token='t', start_scheduler=False), "
            "base_url='http://127.0.0.1:8765')\n"
            "assert c.get('/api/runs').status_code == 200\n"
            "rn.map_page({'id': 'r', 'name': 'n'})\n"
            f"{extra}\n"
            f"print(json.dumps(sorted(m for m in sys.modules if m.split('.')[0] in {WORKERS_MODULES!r})))")
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout.strip().splitlines()[-1])


def test_web_process_writes_the_map_page_without_mapping(tmp_path):
    """The web process makes a run's map page (runs.map_page) without importing mapping, the search, numba or the
    store's modules."""
    assert _modules_of_the_web_process(tmp_path) == []
