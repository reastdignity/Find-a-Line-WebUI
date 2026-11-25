"""The readers that are handed a run read its run.json through runs.read_meta (docs/known-bugs.md, "Two searches
saved at once on Windows"): Windows refuses a run.json for a moment to a reader that opens it while it is moved to
its name (cache.replacing), and a saved run's run.json may be replaced in place. Each reader opens it again after
each of runs.READ_PAUSES (Windows' only: the tests set their own, so they run alike on every system) and keeps its
own answer for a file it cannot open after the last pause. The web's readers wait off the event loop.

Each test makes the refusal with a fake `open` set as an attribute of the module that opened the file bare and of
`runs` (read_meta's), so the same test fails on the bare open and passes through read_meta; it checks that the
refusals were used up, so a pass never means that nothing was refused."""

import asyncio
import json
import os
import sys
import threading

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
import jobs as jb  # noqa: E402
import runs  # noqa: E402
import web  # noqa: E402

pytest.importorskip("httpx2")
from fastapi.testclient import TestClient  # noqa: E402
# The clip's run with its store, and the public site's people (one search for every module: clip_runs)
from test_export import HEADERS, LOCAL, TOKEN, clip_store, copy_data, exported, quick_lane  # noqa: E402,F401
from test_public import (RUN_A, account_settings, clip_run, providers, run_people,  # noqa: E402,F401
                         settings)

PAUSES = (0.0, 0.001, 0.002)  # the test's READ_PAUSES: a run.json opened 4 times before the error is raised
REFUSED_BRIEFLY = 2  # refusals the reader waits out
REFUSED_LONG = 9  # more than the pauses: the reader's own answer for a file it cannot open; 5 left after one read


def refusing(monkeypatch, *modules) -> dict:
    """The fake `open` of `modules` and of runs: an open of a run.json takes the next error of state["refused"]
    while one is left (then the file opens), counted in state["reads"], and in state["on_loop"] when it ran in a
    thread with a running event loop (the web's: a reader there would stop every request while it waits)."""
    state = {"refused": [], "reads": 0, "on_loop": 0}
    lock = threading.Lock()

    def opened(path, *args, **more):
        if os.path.basename(str(path)) == "run.json":
            try:
                asyncio.get_running_loop()
                loop = True
            except RuntimeError:  # no loop in this thread: a worker thread of run_in_threadpool, the lane's
                loop = False
            with lock:
                state["reads"] += 1
                state["on_loop"] += loop
                error = state["refused"].pop(0) if state["refused"] else None
            if error is not None:
                raise error(13, "Permission denied", str(path))
        return open(path, *args, **more)

    for module in (*modules, runs):  # the name as each module sees it, wherever the reader opens the file
        monkeypatch.setattr(module, "open", opened, raising=False)
    monkeypatch.setattr(runs, "READ_PAUSES", PAUSES)
    return state


def refuse(state: dict, times: int):
    state["refused"][:] = [PermissionError] * times


def fake_run(data_dir, run_id: str = "r1") -> str:
    """A run folder holding only a run.json with what profile_problem and the quick lane's tasks read."""
    folder = os.path.join(str(data_dir), "runs", run_id)
    os.makedirs(folder)
    meta = {"id": run_id, "name": "A run", "created": "2026-11-24T10:00:00+00:00", "source": {"id": "test"},
            "params": {"max_length": 100.0}, "area": {"type": "circle", "lat": 50.0, "lon": 19.0, "radius": 150.0},
            "store": {"lines": 7}}
    with open(os.path.join(folder, "run.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f)
    return folder


def test_profile_problem_waits(tmp_path, monkeypatch):
    """web.profile_problem (the public site's bounds of a profile, a 3D view, a reach): a run.json refused for a
    moment is read; refused past the last pause the run is one without profiles, as for any file it cannot open."""
    folder = fake_run(tmp_path)
    state = refusing(monkeypatch, web)
    points = [50.0, 19.0, 50.0003, 19.0]
    refuse(state, REFUSED_BRIEFLY)
    assert web.profile_problem(folder, points) is None and state["refused"] == []
    refuse(state, REFUSED_BRIEFLY)
    assert web.profile_problem(folder, points, patch=True) is None and state["refused"] == []
    refuse(state, REFUSED_LONG)
    assert web.profile_problem(folder, points).code == "no_profiles" and len(state["refused"]) == 5
    refuse(state, REFUSED_LONG)
    assert web.profile_problem(folder, points, patch=True).code == "patch_line" and len(state["refused"]) == 5


def test_the_public_sites_checks_wait_off_the_event_loop(run_people, tmp_path, monkeypatch):
    """/api/profile, /api/patch and /api/reach (async routes) check their points with profile_problem in a worker
    thread (run_in_threadpool), never on the event loop, where its pauses would stop every request: a run.json
    refused for a moment passes the check (on to the missing worker: 503), refused past the last pause the run has
    no profiles (400, as before). /api/reach checks twice (the line, then the anchor): two reads."""
    a = run_people["a"]
    meta = json.loads((tmp_path / "runs" / RUN_A / "run.json").read_text("utf-8"))
    lat, lon = meta["area"]["lat"], meta["area"]["lon"]
    line = f"{lat},{lon},{lat + 0.0003},{lon}"
    asks = {"profile": (f"/api/profile?run={RUN_A}&line={line}", {"x-findaline-profile": "1"}, "no_profiles", 1),
            "patch": (f"/api/patch?run={RUN_A}&line={line}", {"x-findaline-patch": "1"}, "patch_line", 1),
            "reach": (f"/api/reach?run={RUN_A}&line={line}&anchor={lat},{lon}&as=1", {"x-findaline-reach": "1"},
                      "patch_line", 2)}
    state = refusing(monkeypatch, web)
    for kind, (path, headers, code, reads) in asks.items():
        before = state["reads"]
        refuse(state, REFUSED_BRIEFLY)
        assert a.get(path, headers=headers).status_code == 503, kind
        assert state["refused"] == [] and state["reads"] - before == REFUSED_BRIEFLY + reads, kind
        assert state["on_loop"] == 0, f"{kind}: run.json read on the event loop"
        refuse(state, REFUSED_LONG)
        answer = a.get(path, headers=headers)
        assert (answer.status_code, answer.json()["detail"]["code"]) == (400, code), kind
        assert len(state["refused"]) == 5 and state["on_loop"] == 0, kind


def test_an_export_waits_off_the_event_loop(clip_store, tmp_path, monkeypatch):
    """POST /api/runs/<run>/export (has_store) and GET of its address (take_export) read run.json in a worker
    thread, never on the event loop: refused for a moment, the export is made and sent under the run's name;
    refused past the last pause, the POST fails as before (500) and the GET names the file by the run id."""
    data, run_id, folder = copy_data(clip_store, tmp_path)
    meta = json.loads((folder / "run.json").read_text("utf-8"))
    meta["name"] = "Readers wait"
    (folder / "run.json").write_text(json.dumps(meta), "utf-8")
    expected = exported(folder, "csv", tmp_path / "expected")
    app = web.create_app(str(data), token=TOKEN, start_scheduler=False)
    state = refusing(monkeypatch, web)
    with TestClient(app, base_url=LOCAL, raise_server_exceptions=False) as client, quick_lane(data, monkeypatch):
        post = lambda: client.post(f"/api/runs/{run_id}/export", json={"format": "csv"}, headers=HEADERS)  # noqa: E731
        refuse(state, REFUSED_BRIEFLY)
        answer = post()  # has_store waits; then the lane's linestore.export reads it at once
        assert answer.status_code == 200 and state["refused"] == [], answer.text
        refuse(state, REFUSED_BRIEFLY)
        sent = client.get(answer.json()["url"])
        assert sent.status_code == 200 and sent.content == expected and state["refused"] == []
        assert 'filename="Readers wait.csv"' in sent.headers["content-disposition"]
        assert state["on_loop"] == 0, "run.json read on the event loop"

        refuse(state, REFUSED_LONG)
        assert post().status_code == 500 and len(state["refused"]) == 5  # has_store's error, as before
        state["refused"].clear()
        url = post().json()["url"]
        refuse(state, REFUSED_LONG)
        sent = client.get(url)
        assert sent.status_code == 200 and sent.content == expected and len(state["refused"]) == 5
        assert f'filename="{run_id}.csv"' in sent.headers["content-disposition"]  # the id names it, as before
        assert state["on_loop"] == 0 and state["reads"] > 0


def test_the_quick_lanes_tasks_wait(clip_store, tmp_path, monkeypatch):
    """The quick lane's tasks (a profile, a 3D view's terrain and canopy, a reach: search's computing replaced here,
    which takes the run.json read; an export through linestore.export; export_bytes, the export's size) read a
    run.json refused for a moment; refused past the last pause they raise the PermissionError as before (run_quick's
    internal error)."""
    import linestore
    import search
    data, run_id, folder = copy_data(clip_store, tmp_path)
    expected = exported(folder, "geojson", tmp_path / "expected")
    monkeypatch.setattr(search, "profile_of_line", lambda meta, paths, a, b: {"run": meta["id"]})
    for name in ("patch_of_line", "canopy_of_line"):
        monkeypatch.setattr(search, name, lambda meta, paths, a, b, step, name=name: ({"run": meta["id"], "of": name},
                                                                                      b"x"))
    monkeypatch.setattr(search, "reach_of_anchor", lambda meta, paths, a, b, fixed, which: ({"run": meta["id"]}, b"x"))
    monkeypatch.setattr(jb, "LANE_LIMITS", None)
    line = {"run": run_id, "line": [50.0, 19.0, 50.0003, 19.0]}
    tasks = {
        "profile": (jb.quick_profile, line, {"run": run_id}),
        "patch": (jb.quick_patch, {**line, "step": 1}, {"meta": {"run": run_id, "of": "patch_of_line"},
                                                         "heights": "eA"}),
        "canopy": (jb.quick_patch, {**line, "step": 1, "part": "canopy"},
                   {"meta": {"run": run_id, "of": "canopy_of_line"}, "heights": "eA"}),
        "reach": (jb.quick_reach, {**line, "anchor": [50.0, 19.0], "as": 1}, {"meta": {"run": run_id}, "mask": "eA"}),
    }
    lines = json.loads((folder / "run.json").read_text("utf-8"))["store"]["lines"]
    assert lines > 0
    state = refusing(monkeypatch, jb, linestore)
    for kind, (task, request, answer) in tasks.items():
        refuse(state, REFUSED_BRIEFLY)
        assert task(str(data), request) == answer and state["refused"] == [], kind
        refuse(state, REFUSED_LONG)
        with pytest.raises(PermissionError):
            task(str(data), request)
        assert len(state["refused"]) == 5, kind

    refuse(state, REFUSED_BRIEFLY)
    assert jb.export_bytes(str(folder), "csv") == lines * jb.EXPORT_LINE_BYTES["csv"] and state["refused"] == []
    refuse(state, REFUSED_LONG)
    with pytest.raises(PermissionError):
        jb.export_bytes(str(folder), "csv")
    assert len(state["refused"]) == 5

    refuse(state, REFUSED_BRIEFLY)
    name = jb.quick_export(str(data), {"run": run_id, "format": "geojson"})["name"]
    assert state["refused"] == []
    with open(os.path.join(str(data), *jb.EXPORTS, f"{run_id}-{name}"), "rb") as f:
        assert f.read() == expected
    refuse(state, REFUSED_LONG)
    with pytest.raises(PermissionError):
        jb.quick_export(str(data), {"run": run_id, "format": "geojson"})
    assert len(state["refused"]) == 5


def test_the_export_and_view_commands_wait(clip_store, tmp_path, monkeypatch):
    """`findaline.py export` (linestore.export) and `findaline.py view`'s look at an app on the port (app_holds:
    the run's run.json against the one the app serves) read a run.json refused for a moment; refused past the last
    pause the PermissionError ends them as before."""
    import functools
    import http.server

    import findaline
    import linestore
    data, run_id, folder = copy_data(clip_store, tmp_path)
    expected = exported(folder, "csv", tmp_path / "expected")
    state = refusing(monkeypatch, linestore, findaline)
    out = tmp_path / "out.csv"
    refuse(state, REFUSED_BRIEFLY)
    assert findaline.export_main([str(folder), "--format", "csv", "--out", str(out)]) == 0
    assert out.read_bytes() == expected and state["refused"] == []
    refuse(state, REFUSED_LONG)
    with pytest.raises(PermissionError):
        findaline.export_main([str(folder), "--format", "csv", "--out", str(out)])
    assert len(state["refused"]) == 5

    class Files(http.server.SimpleHTTPRequestHandler):  # an app on a port of its own serving the data folder as
        def log_message(self, *args):  # files, as the local app serves its runs folder
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Files, directory=str(data)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        refuse(state, REFUSED_BRIEFLY)
        assert findaline.app_holds(port, str(folder)) is True and state["refused"] == []
        refuse(state, REFUSED_LONG)
        with pytest.raises(PermissionError):
            findaline.app_holds(port, str(folder))
        assert len(state["refused"]) == 5
    finally:
        server.shutdown()
        server.server_close()
        thread.join(10)
