"""Store wave 4 (docs/line-volume/spec-store.md 1.2): a new run keeps its lines only in its store. A search writes
lines.arrow, profiles.arrow, map.html (not with --no-html), ATTRIBUTION.txt and run.json, in that order (run.json
last, with its block "store"), and none of data.js, lines.js, lines.csv, lines.geojson; no runs/index.html and no
findaline_map.html; a run that cannot be saved whole fails the search (run_not_saved) and keeps no run; view columns
that cannot be computed leave a store without them and a coded warning (view_columns_failed). Also tests/old_runs.py,
the old runs the tests of `runs remove-old` make, and tests/old_scripts.py, the frozen writer of a run's data.js and
lines.js the tools' tests use."""

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
import old_scripts  # noqa: E402
import search  # noqa: E402
from test_access_search import _plan, offline, scene  # noqa: E402,F401 - offline is a fixture

NEW_FILES = {"lines.arrow", "profiles.arrow", "map.html", "ATTRIBUTION.txt", "run.json"}
# The catalogue's texts as the user approved them (2026-11-17, Q1a) and as main had them (jobs of before), read from
# locales/en.json itself: messages.text gives the key back for an entry that is missing
RUN_NOT_SAVED = "The run could not be saved: its lines could not be written. Try again; if it happens again, report it."
STORE_FAILED = ("The run is saved, but without the file that loads its lines fastest (lines.arrow). The map opens it "
                "from its other files.")


def catalogue_text(key: str) -> str:
    with open(os.path.join(REPO, "locales", "en.json"), encoding="utf-8") as f:
        return json.load(f)[key]


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
    """A store that cannot be written fails the search with the code run_not_saved (the page's text from the
    catalogue, no exception text in it: it may hold paths), and the run folder is removed."""
    plan, lines = scene_lines

    def failing(run_path, lines, head, view=None):
        open(os.path.join(run_path, linestore.LINES_FILE + linestore.PART), "wb").close()
        raise OSError(r"no space at C:\secret\path")
    monkeypatch.setattr(linestore, "write", failing)
    with pytest.raises(search.SearchError) as error:
        _save(plan, lines, tmp_path, "failed")
    assert error.value.code == "run_not_saved" and "OSError" in str(error.value)
    assert error.value.web_text() == catalogue_text("error.run_not_saved") == RUN_NOT_SAVED
    assert "secret" not in error.value.web_text()
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
    """tests/old_runs.py makes each kind of run of before store wave 4 from a run with a store, with the files of its
    time but data.js and lines.js (no reader is left of them); an old kind's map.html is the page of before (no disk
    notice). tests/old_scripts.py's data.js and lines.js written from the store equal what its frozen writer gives
    from the search's own lines (the heads mapping.map_head gives the search's arguments), byte for byte."""
    plan, lines = scene_lines
    path, result = _save(plan, lines, tmp_path, "r0ld5x")
    reference = tmp_path / "reference"
    reference.mkdir()
    _reference_scripts(plan, result, reference)
    kinds = {}
    for kind in old_runs.KINDS:
        kinds[kind] = old_runs.copy_run(path, tmp_path / "runs", f"r0ld5x-{kind}")
        old_runs.make_old(kinds[kind], kind)
    copy = kinds["with_text"]
    old_scripts.write_scripts(copy)
    for name in old_scripts.MAP_FILES:
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


def test_a_failure_after_the_store_keeps_no_run(scene_lines, tmp_path, monkeypatch):
    """Anything that fails after the store is written (here run.json's write: a disk full) fails the search with
    run_not_saved and removes the run's folder, store included: a folder without run.json is never left behind. A
    tiled run (its search's folder) keeps its work state (tiles, progress.json "running") to be resumed, and loses
    only what the save wrote."""
    import runs as rn
    plan, lines = scene_lines
    real = rn.save_results

    def failing(run_path, lines, groups, meta, *args, **kwargs):
        if "run.json" in kwargs.get("files", ()):
            raise OSError(28, "No space left on device")
        return real(run_path, lines, groups, meta, *args, **kwargs)
    monkeypatch.setattr(rn, "save_results", failing)
    with pytest.raises(search.SearchError) as error:
        _save(plan, lines, tmp_path, "after")
    assert error.value.code == "run_not_saved" and not (tmp_path / "runs" / "after").exists()
    tiled = tmp_path / "runs" / "tiled"
    (tiled / "tiles").mkdir(parents=True)
    (tiled / "tiles" / "0.table.pkl.gz").write_bytes(b"tile")
    (tiled / "progress.json").write_text('{"status": "running"}', "utf-8")
    run = {"id": "tiled", "path": str(tiled), "created": datetime(2026, 11, 17, 12), "name": "tiled", "search": "k",
           "tile_core": 150}
    with pytest.raises(search.SearchError) as error:
        search.save_run(plan, lines, run)
    assert error.value.code == "run_not_saved"
    assert sorted(os.listdir(tiled)) == ["progress.json", "tiles"]
    assert json.loads((tiled / "progress.json").read_text("utf-8"))["status"] == "running"


def test_the_saving_stage(scene_lines, tmp_path, monkeypatch):
    """Step 5's one Compute stage "saving results" (no "saving the map" since store wave 4): it starts with the lines
    as its total and ends done at that count."""
    import progress
    plan, lines = scene_lines
    seen = []
    monkeypatch.setattr(progress, "_listeners", [*progress._listeners, seen.append])
    _save(plan, lines, tmp_path, "stage")
    stages = [e for e in seen if e["bar"] == "Compute" and e["stage"].startswith("saving")]
    assert {e["stage"] for e in stages} == {"saving results"}
    n = len(lines.results)
    assert stages[0]["count"] == 0 and stages[0]["total"] == n and not stages[0]["done"]
    assert stages[-1]["done"] and stages[-1]["count"] == n


@pytest.fixture(scope="module")
def scene_lines_with_ends(tmp_path_factory, offline):  # noqa: F811
    """The access scene's search with the access mark, the no-fall zone, A-frames and the square rule: (plan, lines)."""
    folder = tmp_path_factory.mktemp("store-only-ends")
    plan = _plan(folder, scene(), "e", access=True, end_zone=5, anchor_lift=2, same_line_square=5)
    lines, _ = search.search_lines(plan)
    return plan, lines


def test_old_runs_with_ends_are_todays_files(scene_lines_with_ends, tmp_path):
    """tests/old_scripts.py's data.js and lines.js of a run with "ends" (the A-frame heights, the access mark, the square
    rule's count: the heads it builds by hand) equal its frozen writer's from the search's own lines, byte for byte."""
    plan, lines = scene_lines_with_ends
    path, result = _save(plan, lines, tmp_path, "r0ld5e")
    assert {"lift_needed", "access1", "stands_for"} <= set(result.results.columns)
    reference = tmp_path / "reference"
    reference.mkdir()
    _reference_scripts(plan, result, reference)
    old_scripts.write_scripts(path)
    for name in old_scripts.MAP_FILES:
        text = (path / name).read_text("utf-8")
        assert '"ends":["lift_needed","lift_no_zone","access1","access2","stands_for"]' in text, name
        assert text == (reference / name).read_text("utf-8"), name


def _reference_scripts(plan, result, folder):
    """data.js and lines.js of the search's own lines (result.results) by tests/old_scripts.py's frozen writer, their
    heads from mapping.map_head of the search's arguments, as mapping.save_map wrote them before store wave 4."""
    p = plan.params
    head = mapping.map_head(plan.area, str(folder / "map.html"), result.meta, plan.crs, plan.group_distance,
                            p.group_by, None, None, p.model, plan.rigging, high_above=p.high_above)
    old_scripts.write_map_scripts(result.results, str(folder), old_scripts.heads_of(head, result.meta))


class _Stub:
    def __init__(self, **values):
        self.__dict__.update(values)


def _main_output(monkeypatch, capsys, tmp_path, **options) -> str:
    """findaline.main with the search stubbed (no grid, no lines): what it prints after a run is saved."""
    import findaline
    import params as pm
    monkeypatch.setattr(search, "plan_search", lambda params, paths, emit: _Stub(group_distance=20))
    monkeypatch.setattr(search, "estimate_search", lambda plan: _Stub(reasons=[]))
    monkeypatch.setattr(search, "search_lines", lambda plan: (None, None))
    monkeypatch.setattr(findaline, "print_lines", lambda *args: [])
    monkeypatch.setattr(search, "save_run", lambda plan, lines, run: _Stub(meta={"id": "2026-11-17_run"}))
    monkeypatch.setattr(search, "orthophoto_lines", lambda plan, lines: [])
    monkeypatch.setattr(search, "download_orthophoto", lambda plan, spots, confirm: None)
    params = pm.SearchParams(lat=50.1, lon=19.7, no_html=options.pop("no_html", False))
    findaline.main(params, pm.CliOptions(no_plot=True, yes=True, **options), search.Paths(str(tmp_path), str(tmp_path)))
    return capsys.readouterr().out


def test_the_last_lines(monkeypatch, capsys, tmp_path):
    """A search ends with the command that opens its run, once: also with --html (store U10: accepted for one
    release, it says it is no longer used and writes nothing) and with --no-html (the app opens such a run too)."""
    out = _main_output(monkeypatch, capsys, tmp_path)
    assert out.count("findaline.py view 2026-11-17_run") == 1 and "View it: findaline.py view 2026-11-17_run\n" in out
    out = _main_output(monkeypatch, capsys, tmp_path, html=str(tmp_path / "latest.html"))
    assert out.count("findaline.py view 2026-11-17_run") == 1, out
    assert "--html is no longer used: maps open through the app.\nView it: findaline.py view 2026-11-17_run" in out
    assert not (tmp_path / "latest.html").exists()
    out = _main_output(monkeypatch, capsys, tmp_path, no_html=True)
    assert out.count("View it: findaline.py view 2026-11-17_run") == 1, out


def test_the_two_codes_and_their_texts():
    """error.run_not_saved holds the user's approved words; error.store_failed keeps main's text (the warnings of jobs
    of before still read right), both in locales/en.json itself."""
    assert catalogue_text("error.run_not_saved") == RUN_NOT_SAVED
    assert catalogue_text("error.store_failed") == STORE_FAILED
    assert messages.Note("cli", "store_failed").web_text() == STORE_FAILED


def test_run_json_is_written_whole(tmp_path, monkeypatch):
    """runs.save_results writes run.json whole or not at all (it marks a finished run): a write stopped half way
    leaves the run.json of before (or none) and no temporary file, never a part of the new one."""
    import helpers as sh
    import mapping as mp
    import runs as rn
    lines, groups = sh.LineTable.empty(), mp.Groups.each_alone(0)
    meta = {"id": "r", "name": "r", "attribution": [], "params": {}}
    real = json.dump

    def half(value, f, **kwargs):
        f.write('{"id": "r", "na')
        raise OSError(28, "No space left on device")
    monkeypatch.setattr(rn.json, "dump", half)
    with pytest.raises(OSError):
        rn.save_results(str(tmp_path), lines, groups, meta, files=("run.json",))
    assert os.listdir(tmp_path) == []
    monkeypatch.setattr(rn.json, "dump", real)
    rn.save_results(str(tmp_path), lines, groups, {**meta, "name": "before"}, files=("run.json",))
    monkeypatch.setattr(rn.json, "dump", half)
    with pytest.raises(OSError):
        rn.save_results(str(tmp_path), lines, groups, meta, files=("run.json",))
    assert os.listdir(tmp_path) == ["run.json"]
    assert json.loads((tmp_path / "run.json").read_text("utf-8"))["name"] == "before"
