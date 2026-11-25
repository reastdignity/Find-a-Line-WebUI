"""The rename's own read of run.json waits as a listing's does (line volume's round 7, the user's answer 10 of
2026-11-25, "Yes, it waits too"): runs.rename_run reads the run's run.json through runs.read_meta, which opens it
again after each of runs.READ_PAUSES while Windows refuses it (PermissionError: another process holds the file for a
moment after it moved it to its name). After the last pause the rename answers as before (the route's 409, "the run
is in use"), with no file changed. Off Windows READ_PAUSES is empty: one open, as before.

The refusals come from a fake `open` of the runs module and the pauses are set by the test, as
tests/test_units.py's test_a_listing_waits_for_a_run_json_windows_refuses does, so the tests run alike on every
system."""

import inspect
import json
import os

import pytest

import runs as rn
from test_public import (RUN_A, account_settings, clip_run, providers, run_people, settings)  # noqa: F401
from test_run_rename import _as_saved, _files

PAUSES = (0.0, 0.001, 0.002)  # the test's pauses: three, so a read is tried four times
CREATED = "2026-11-25T10:00:00+00:00"
IN_USE = "the run is in use: try again in a moment"


def refusing(monkeypatch) -> tuple:
    """The runs module's `open` refusing the next opens of a run.json (PermissionError, as Windows refuses a file
    another process holds) while the returned list `refused` has entries; every open of a run.json counted in
    `opened`; READ_PAUSES the test's."""
    refused, opened = [], []

    def fake_open(path, *args, **more):
        if os.path.basename(path) == "run.json":
            opened.append(path)
            if refused:
                raise refused.pop(0)(13, "Permission denied", str(path))
        return open(path, *args, **more)
    monkeypatch.setattr(rn, "open", fake_open, raising=False)  # the name as runs.py sees it: no other module's open
    monkeypatch.setattr(rn, "READ_PAUSES", PAUSES)
    return refused, opened


@pytest.fixture
def small_run(tmp_path):
    """A runs folder with one run as a search saves its named files: run.json, ATTRIBUTION.txt (its first line the
    one attribution_text writes) and map.html (runs.map_page); (runs folder, run id, the folder)."""
    runs_dir = tmp_path / "runs"
    folder = runs_dir / "r1"
    folder.mkdir(parents=True)
    meta = {"id": "r1", "name": "Old name", "created": CREATED, "summary": {"lines": 3}}
    (folder / "run.json").write_text(json.dumps(meta, indent=2), "utf-8")
    (folder / "ATTRIBUTION.txt").write_text(rn.attribution_text(meta), "utf-8")
    (folder / "map.html").write_text(rn.map_page(meta), "utf-8")
    return runs_dir, "r1", folder


def test_a_rename_waits_for_a_run_json_windows_refuses(small_run, monkeypatch):
    """runs.rename_run's read of run.json refused twice (PermissionError): opened again after the pauses, the run is
    renamed (run.json, ATTRIBUTION.txt's first line, map.html's title). Refused past the last pause: the
    PermissionError (an OSError: the route's 409) and no file changed, nothing half renamed. Another error (no such
    file: the route's 404) at once, not tried again; with no pauses (every system but Windows) a refusal at once."""
    runs_dir, run, folder = small_run
    refused, opened = refusing(monkeypatch)
    refused[:] = [PermissionError] * 2
    meta = rn.rename_run(str(runs_dir), run, "New name")
    assert refused == [] and len(opened) == 3, opened  # refused twice, read at the third open
    assert meta["name"] == "New name" and json.loads((folder / "run.json").read_text("utf-8"))["name"] == "New name"
    assert (folder / "ATTRIBUTION.txt").read_text("utf-8").splitlines()[0] == f'Find-a-Line run "New name" ({CREATED})'
    assert "<title>New name - Find-a-Line</title>" in (folder / "map.html").read_text("utf-8")

    before = _files(folder)
    refused[:], opened[:] = [PermissionError] * 9, []
    with pytest.raises(PermissionError):
        rn.rename_run(str(runs_dir), run, "Third name")
    assert len(opened) == len(PAUSES) + 1 and len(refused) == 9 - len(PAUSES) - 1  # once and after each pause
    assert _files(folder) == before  # run.json, ATTRIBUTION.txt and map.html as they were

    refused[:], opened[:] = [FileNotFoundError, PermissionError], []
    with pytest.raises(KeyError):  # no run (the route's 404), as before
        rn.rename_run(str(runs_dir), run, "Third name")
    assert refused == [PermissionError] and len(opened) == 1  # another error: not tried again
    assert _files(folder) == before

    monkeypatch.setattr(rn, "READ_PAUSES", ())  # as on every system but Windows
    refused[:], opened[:] = [PermissionError] * 2, []
    with pytest.raises(PermissionError):
        rn.rename_run(str(runs_dir), run, "Third name")
    assert len(refused) == 1 and len(opened) == 1  # a refusal there: at once
    assert _files(folder) == before


def test_the_route_waits_and_answers_409_after_the_last_pause(run_people, tmp_path, monkeypatch):
    """POST /api/runs/<id> by the run's owner, its run.json refused twice: 200 with the name as stored, run.json
    renamed. Refused past the last pause: 409 "the run is in use: try again in a moment" (the answer of before for a
    run.json the rename cannot read now), run.json, ATTRIBUTION.txt and map.html as they were."""
    a = run_people["a"]
    folder = tmp_path / "runs" / RUN_A
    _as_saved(folder)
    refused, opened = refusing(monkeypatch)
    refused[:] = [PermissionError] * 2
    answer = a.post(f"/api/runs/{RUN_A}", json={"name": "Waited name"})
    assert answer.status_code == 200 and answer.json() == {"ok": True, "name": "Waited name"}, answer.text
    assert refused == [] and json.loads((folder / "run.json").read_text("utf-8"))["name"] == "Waited name"

    before = _files(folder)
    refused[:] = [PermissionError] * (len(PAUSES) + 1)
    in_use = a.post(f"/api/runs/{RUN_A}", json={"name": "Never stored"})
    assert in_use.status_code == 409 and in_use.json()["detail"] == IN_USE, in_use.text
    assert refused == [] and _files(folder) == before


def test_the_route_never_runs_on_the_event_loop(run_people):
    """The rename's route is a plain function (FastAPI runs it in its thread pool), so the read's pauses (up to
    1.58 s on Windows) never hold the server's event loop."""
    app = run_people["a"].app
    routes = [r for r in app.routes if getattr(r, "path", None) == "/api/runs/{run}" and "POST" in r.methods]
    assert len(routes) == 1 and not inspect.iscoroutinefunction(routes[0].endpoint), routes
