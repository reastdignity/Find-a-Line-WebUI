"""tools/perf_lines_memory.py: its step 5 is what search.save_run writes since store wave 4 (the result view's
columns and the store, no text file), and it never imports saving.py (gone with wave 4). The measurements
themselves run by hand (docs/performance.md)."""

import inspect
import os
import sys
import types

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


def _lines(n=500):
    lines = _fake_lines(n)
    for name in sh.PIXEL_COLUMNS:  # gone before saving (LineTable.without_pixels)
        lines.columns.pop(name)
    return lines, mp.group_lines(lines, 20, "clearance")


def test_step5_runs_no_text_writer_and_no_saving(tmp_path, monkeypatch):
    """Step 5 is the store's write alone: runs.save_results, mapping.save_map and write_map_scripts (what step 5
    called before store wave 4) are never reached, and saving.py is never imported."""
    def refuse(*a, **k):
        raise AssertionError("a text writer in step 5")
    monkeypatch.setattr(rn, "save_results", refuse)
    monkeypatch.setattr(mp, "save_map", refuse)
    monkeypatch.setattr(mp, "write_map_scripts", refuse)
    lines, groups = _lines()
    assert plm.save_step5(np, mp, rn, lines, groups, str(tmp_path / "out"), len(lines)) == sorted(linestore.FILES)
    source = inspect.getsource(plm)
    assert "import saving" not in source and "saving." not in source.replace("saving.py", "")


def test_step5_of_older_checkouts(tmp_path, monkeypatch):
    """A --repo without linestore.py writes its text files; one with the store but without mapping.view_columns
    (store wave 2 before view B1) writes the store without the result view's columns."""
    lines, groups = _lines(300)
    old = types.SimpleNamespace(map_head=mp.map_head)  # a mapping of before view_columns
    files = plm.save_step5(np, old, rn, lines, groups, str(tmp_path / "wave2"), len(lines))
    assert files == sorted(linestore.FILES)
    back, head = linestore.read(str(tmp_path / "wave2"), profiles=False)
    assert "spot" not in back.columns and "sectors" not in head and len(back) == len(lines)
    monkeypatch.setitem(sys.modules, "linestore", None)  # a checkout before the store: import linestore fails
    files = plm.save_step5(np, mp, rn, lines, groups, str(tmp_path / "text"), len(lines))
    assert {"lines.csv", "lines.geojson", "run.json", "data.js", "lines.js", "map.html"} <= set(files)
    assert not set(linestore.FILES) & set(files)
