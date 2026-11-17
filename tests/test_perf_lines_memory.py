"""tools/perf_lines_memory.py: its step 5 is what search.save_run writes since store wave 4 (the result view's
columns and the store, no text file), and it never imports saving.py (gone with wave 4). The measurements
themselves run by hand (docs/performance.md)."""

import inspect
import os
import sys

import numpy as np

import helpers as sh
import linestore
import mapping as mp
import runs as rn
from test_units import _fake_lines

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "tools"))

import perf_lines_memory as plm  # noqa: E402


def test_step5_writes_the_store_only(tmp_path):
    lines = _fake_lines(500)
    for name in sh.PIXEL_COLUMNS:  # gone before saving (LineTable.without_pixels)
        lines.columns.pop(name)
    groups = mp.group_lines(lines, 20, "clearance")
    out = tmp_path / "out"
    files = plm.save_step5(np, mp, rn, lines, groups, str(out), len(lines))
    assert files == sorted(linestore.FILES)  # no lines.csv, lines.geojson, data.js, lines.js, map.html
    back, head = linestore.read(str(out), profiles=False)
    assert len(back) == len(lines) and "spot" in back.columns  # with the result view's columns
    assert {"sectors", "box", "lengths"} <= set(head) and head["run"]["name"] == "memory"
    assert np.array_equal(back.columns["length"], lines.columns["length"])


def test_never_imports_saving():
    source = inspect.getsource(plm)
    assert "import saving" not in source and "saving." not in source.replace("saving.py", "")
