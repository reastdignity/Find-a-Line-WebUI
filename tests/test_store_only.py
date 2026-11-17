"""Store wave 4 (docs/line-volume/spec-store.md 1.2): a new run keeps its lines only in its store. A search writes
lines.arrow, profiles.arrow, map.html (not with --no-html), ATTRIBUTION.txt and run.json, in that order (run.json
last, with its block "store"), and none of data.js, lines.js, lines.csv, lines.geojson; no runs/index.html and no
findaline_map.html; a store that cannot be written fails the search (store_failed) and keeps no run; view columns
that cannot be computed leave a store without them and a coded warning (view_columns_failed). Also tests/old_runs.py,
the old runs the tests make until store wave 4's item 5."""

import dataclasses
import json
import os
import sys
from datetime import datetime

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
import clip_runs  # noqa: E402
import linestore  # noqa: E402
import mapping  # noqa: E402
import messages  # noqa: E402
import old_runs  # noqa: E402
import search  # noqa: E402
from test_access_search import _plan, offline, scene  # noqa: E402,F401 - offline is a fixture

NEW_FILES = {"lines.arrow", "profiles.arrow", "map.html", "ATTRIBUTION.txt", "run.json"}


def test_a_search_keeps_its_lines_in_the_store(tmp_path_factory):
    """The clip searched by findaline.py (the result view's clip run): its folder holds exactly the new files, run.json
    with its block "store"; the runs folder runs.js and the viewer, no index.html; the data folder no
    findaline_map.html; the search ends with the command that opens the run."""
    folder = clip_runs.view_clip(tmp_path_factory, "store-only")
    data = folder.parent.parent
    assert set(os.listdir(folder)) == NEW_FILES, sorted(os.listdir(folder))
    meta = json.loads((folder / "run.json").read_text("utf-8"))
    assert meta["store"]["lines"] == meta["summary"]["lines"] > 0
    assert set(os.listdir(folder.parent)) <= {folder.name, "runs.js", mapping.VIEWER_FOLDER, "_runs.lock"}
    assert "runs.js" in os.listdir(folder.parent) and not (data / "findaline_map.html").exists()
    output = clip_runs.output_of(tmp_path_factory, clip_runs.VIEW_CLIP_ARGS)
    assert f"View it: findaline.py view {meta['id']} --data-dir " in output, output[-2000:]
    for gone in ("Interactive map saved to", "findaline_map.html", "index.html", "All runs:"):
        assert gone not in output


@pytest.fixture(scope="module")
def scene_lines(tmp_path_factory, offline):  # noqa: F811
    """The access scene's search (test_access_search), steps 1-4 once: (plan, lines)."""
    folder = tmp_path_factory.mktemp("store-only-scene")
    plan = _plan(folder, scene(), "s", access=False)
    lines, _ = search.search_lines(plan)
    return plan, lines


def _save(plan, lines, tmp_path, name: str, events=None, **values):
    """save_run of the scene's lines into a run folder of tmp_path (values: SearchParams changed)."""
    if values:
        plan = dataclasses.replace(plan, params=plan.params.model_copy(update=values))
    if events is not None:
        plan = dataclasses.replace(plan, emit=lambda kind, text: events.append((kind, text)))
    path = tmp_path / "runs" / name
    path.mkdir(parents=True)
    result = search.save_run(plan, lines, {"id": name, "path": str(path), "created": datetime(2026, 11, 17, 12),
                                           "name": name})
    return path, result


def test_run_json_is_written_last(scene_lines, tmp_path, monkeypatch):
    """While the store is written the folder holds no run.json (a run being saved: runs remove-old skips it) and no
    map.html; run.json comes last and holds the store's block; --no-html leaves map.html out, the store stays."""
    plan, lines = scene_lines
    seen = []
    write = linestore.write

    def watching(run_path, *args, **kwargs):
        seen.append(set(os.listdir(run_path)))
        return write(run_path, *args, **kwargs)
    monkeypatch.setattr(linestore, "write", watching)
    path, result = _save(plan, lines, tmp_path, "last")
    assert seen == [set()]
    assert set(os.listdir(path)) == NEW_FILES
    assert json.loads((path / "run.json").read_text("utf-8"))["store"] == result.meta["store"]
    assert result.map_path == str(path / "map.html")
    path, result = _save(plan, lines, tmp_path, "no-html", no_html=True)
    assert set(os.listdir(path)) == NEW_FILES - {"map.html"} and result.map_path is None


def test_a_store_that_fails_keeps_no_run(scene_lines, tmp_path, monkeypatch):
    """A store that cannot be written fails the search with the code store_failed (the page's text from the
    catalogue, no exception text in it: it may hold paths), and the run folder is removed."""
    plan, lines = scene_lines

    def failing(run_path, lines, head, view=None):
        open(os.path.join(run_path, linestore.LINES_FILE + linestore.PART), "wb").close()
        raise OSError(r"no space at C:\secret\path")
    monkeypatch.setattr(linestore, "write", failing)
    with pytest.raises(search.SearchError) as error:
        _save(plan, lines, tmp_path, "failed")
    assert error.value.code == "store_failed" and "OSError" in str(error.value)
    assert error.value.web_text() == messages.text("error.store_failed") and "secret" not in error.value.web_text()
    assert not (tmp_path / "runs" / "failed").exists()


def test_view_columns_that_fail_keep_the_lines(scene_lines, tmp_path, monkeypatch):
    """The view's columns that cannot be computed: the run is saved with a store without them (an old run by
    spec-store.md 2.2, which opens in today's page) and a coded warning (view_columns_failed)."""
    plan, lines = scene_lines
    events = []

    def failing(*args, **kwargs):
        raise MemoryError(r"no memory at C:\secret\path")
    monkeypatch.setattr(mapping, "view_columns", failing)
    path, _ = _save(plan, lines, tmp_path, "no-view", events)
    notes = [text for kind, text in events if kind == "warning"]
    assert len(notes) == 1 and isinstance(notes[0], messages.Note) and notes[0].code == "view_columns_failed"
    assert notes[0].web_text() == messages.text("error.view_columns_failed") and "secret" not in notes[0].web_text()
    assert set(os.listdir(path)) == NEW_FILES
    table, _ = linestore.read(str(path), profiles=False)
    assert not set(name for name, _ in linestore.VIEW) & set(table.columns)


def test_old_runs_are_todays_files(scene_lines, tmp_path):
    """tests/old_runs.py writes the old files of a run with a store as the search wrote them before store wave 4:
    data.js and lines.js equal mapping.save_map's from the search's own lines, byte for byte; each kind holds the
    files of its time; an old kind's map.html is the page of before (no disk notice)."""
    plan, lines = scene_lines
    path, result = _save(plan, lines, tmp_path, "r0ld5x")
    p = plan.params
    reference = tmp_path / "reference"
    reference.mkdir()
    mapping.save_map(result.results, plan.area, str(reference), str(tmp_path / "runs"), result.meta, plan.crs,
                     plan.group_distance, p.group_by, None, None, p.model, plan.rigging, high_above=p.high_above,
                     files=mapping.MAP_FILES)
    kinds = {}
    for kind in old_runs.KINDS:
        kinds[kind] = old_runs.copy_run(path, tmp_path / "runs", f"r0ld5x-{kind}")
        old_runs.make_old(kinds[kind], kind)
    copy = kinds["with_text"]
    for name in mapping.MAP_FILES:
        expected = (reference / name).read_text("utf-8").replace('"r0ld5x"', '"r0ld5x-with_text"')
        assert (copy / name).read_text("utf-8") == expected, name
    assert set(os.listdir(kinds["data_js"])) == {"map.html", "ATTRIBUTION.txt", "run.json", *old_runs.TEXT_FILES}
    assert set(os.listdir(kinds["no_html"])) == {"ATTRIBUTION.txt", "run.json", "lines.csv", "lines.geojson"}
    assert {"tiles", "progress.json", "shore.json"} <= set(os.listdir(kinds["tiled"]))
    assert set(os.listdir(kinds["no_view"])) == NEW_FILES | set(old_runs.TEXT_FILES)
    table, _ = linestore.read(str(kinds["no_view"]), profiles=False)
    assert "by_spot" not in table.columns
    assert "store" not in json.loads((kinds["data_js"] / "run.json").read_text("utf-8"))
    page = (kinds["data_js"] / "map.html").read_text("utf-8")
    assert page == old_runs.BASE_MAP_HTML.format(title="r0ld5x", viewer=mapping.VIEWER_FOLDER)
