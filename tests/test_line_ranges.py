"""The ranges of a kept line's copies (the square rule's step 2e: samelines.RANGED) in the search: the pair search's
table without lines keeps their columns in their places, and the tiled search's work state (progress.json) marks
tiles that carry them, so a search with the rule never resumes tiles saved before them and joins its own (a
search without the rule writes the work state of before). The reducer's own tests: tests/test_same_lines.py."""

import dataclasses
import gc
import glob
import json
import os
import sys

import numpy as np
import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
DATA = os.path.join(REPO, "tests", "data")

import helpers as sh  # noqa: E402
import samelines  # noqa: E402
import search  # noqa: E402
from test_same_lines import SETTINGS, SQUARE, _export, _range_names, _search, _store_table  # noqa: E402

TODAYS_KEYS = {"status", "search", "tile_core", "name", "created"}  # progress.json of a search without the rule


def _plan(tmp_path, name: str, **values) -> "search.Plan":
    """The plan of a search of the clip's square (test_same_lines._search's), not run."""
    from params import SearchParams
    area = tmp_path / "square.geojson"
    if not area.exists():
        area.write_text(json.dumps({"type": "Feature", "properties": {}, "geometry": SQUARE}))
    params = SearchParams(**{"elevation_file": os.path.join(DATA, "zabi_kon_nmt.tif"), "max_length": 150,
                             "water": "off", "fill_gaps": "off", "ortho": "never", "area": str(area), **values})
    paths = search.Paths(str(tmp_path / name), str(tmp_path / name / "work"))
    os.makedirs(paths.work, exist_ok=True)
    return search.plan_search(params, paths, lambda kind, text: None)


@pytest.mark.parametrize("setting", list(SETTINGS))
def test_pair_search_without_lines_keeps_the_columns(tmp_path, monkeypatch, setting):
    """search._pair_search with the square rule: its table of no line (no part reached the reducer) has the columns
    of a table of lines, in the same order and of the same types (the count, the ranges, with the no-fall zone and
    A-frames their heights and their ranges between them), so LineTable.join of tiles never meets a table without
    them."""
    import linesearch
    plan = _plan(tmp_path, setting, same_line_square=5, **SETTINGS[setting])
    data = search.prepare_data(plan)
    found = search._anchors(plan, data)
    p = plan.params
    table = search._sag_table(dataclasses.astuple(plan.rigging), p.min_length, p.max_length) if p.model == "sag" else None
    lines = search._pair_search(plan, data, found, None, table)
    assert len(lines) and len(_range_names(lines)) == (12 if SETTINGS[setting] else 8)
    monkeypatch.setattr(linesearch, "find_valid_lines", lambda *args, **kwargs: None)  # no part at all
    empty = search._pair_search(plan, data, found, None, table)
    assert len(empty) == 0 and list(empty.columns) == list(lines.columns)
    assert [empty.columns[name].dtype for name in empty.columns] == [lines.columns[name].dtype for name in lines.columns]
    joined = sh.LineTable.join([empty, lines.take(np.arange(len(lines)))])
    assert all(np.array_equal(joined.columns[name], lines.columns[name], equal_nan=True) for name in lines.columns
               if lines.columns[name].dtype.kind == "f")
    del data
    gc.collect()


def _state(folder: str) -> dict:
    with open(os.path.join(folder, "progress.json"), encoding="utf-8") as f:
        return json.load(f)


def _unfinished(plan, name: str, **extra) -> str:
    """A tiled run of the plan's search left running, as a search before the ranges wrote it (extra: more keys)."""
    folder = os.path.join(plan.paths.runs, name)
    os.makedirs(os.path.join(folder, "tiles"))
    with open(os.path.join(folder, "progress.json"), "w", encoding="utf-8") as f:
        json.dump({"status": "running", "search": search._search_hash(plan), "tile_core": plan.tile_core,
                   "name": "Clip", "created": "2026-11-20T10:00:00", **extra}, f)
    return folder


def test_tiled_work_state_of_before_the_ranges(tmp_path):
    """A tiled search with the square rule marks its progress.json ("ranges": search.TILE_RANGES) and resumes only a
    run so marked: one left running before the ranges (its tiles without them) is not resumed, a new run is made. A
    search without the rule writes today's keys only and resumes the run of before as it did."""
    on = _plan(tmp_path, "data", same_line_square=5, tile_size=150)
    off = _plan(tmp_path, "data", tile_size=150)
    assert on.tiles and off.tiles and on.square and not off.square
    before_on = _unfinished(on, "before-on")
    before_off = _unfinished(off, "before-off")
    run = search._open_run(on)
    assert run["path"] not in (before_on, before_off)
    assert _state(run["path"]) == {**{k: _state(before_on)[k] for k in ("status", "search", "tile_core")},
                                   "name": run["name"], "created": run["created"].isoformat(),
                                   "ranges": search.TILE_RANGES}
    assert "ranges" not in _state(before_on)  # left as it was
    assert search._open_run(on)["path"] == run["path"]  # the marked run is resumed
    resumed = search._open_run(off)
    assert resumed["path"] == before_off and set(_state(before_off)) == TODAYS_KEYS
    fresh = _plan(tmp_path, "fresh", tile_size=150)
    assert set(_state(search._open_run(fresh)["path"])) == TODAYS_KEYS
    search._progress(resumed, "done")
    assert set(_state(before_off)) == TODAYS_KEYS and _state(before_off)["status"] == "done"
    search._progress(run, "done")
    assert _state(run["path"])["ranges"] == search.TILE_RANGES and _state(run["path"])["status"] == "done"


def test_resumed_tiled_search_joins_its_ranges(tmp_path, monkeypatch):
    """A tiled search with the square rule stopped after its first tile and started again resumes its run (its tile
    file carries the ranges) and saves the lines, the counts and the ranges of one grid, bit for bit."""
    values = SETTINGS["sag"]
    one, _, _ = _search(tmp_path, "one", same_line_square=5, **values)
    real, calls = search._lines, []

    def stopped(*args, **kwargs):
        calls.append(1)
        if len(calls) == 2:
            raise RuntimeError("the process stops")
        return real(*args, **kwargs)
    monkeypatch.setattr(search, "_lines", stopped)
    with pytest.raises(RuntimeError):
        _search(tmp_path, "tiled", same_line_square=5, tile_size=150, **values)
    gc.collect()
    calls.clear()
    monkeypatch.setattr(search, "_lines", lambda *args, **kwargs: calls.append(1) or real(*args, **kwargs))
    [folder] = [os.path.dirname(p) for p in glob.glob(str(tmp_path / "tiled" / "runs" / "*" / "progress.json"))]
    assert _state(folder)["status"] == "running" and _state(folder)["ranges"] == search.TILE_RANGES
    [tile] = glob.glob(os.path.join(folder, "tiles", search.TILE_FILE.format("*")))
    saved = search._load_tile(tile)
    assert len(_range_names(saved)) == 12 and samelines.COLUMN in saved.columns
    run, _, plan = _search(tmp_path, "tiled", same_line_square=5, tile_size=150, **values)
    assert os.path.samefile(run, folder) and len(plan.tiles) > 2 and len(calls) == len(plan.tiles) - 1  # the first tile: its file
    assert _store_table(run).equals(_store_table(one)) and _export(run) == _export(one)
    assert json.loads(open(os.path.join(run, "run.json"), encoding="utf-8").read())["summary"] == \
        json.loads(open(os.path.join(one, "run.json"), encoding="utf-8").read())["summary"]
