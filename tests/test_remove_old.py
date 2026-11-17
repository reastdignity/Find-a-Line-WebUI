"""`findaline.py runs remove-old (--dry-run | --yes) [--data-dir DIR]` (docs/line-volume/spec-store.md 2.2-2.10,
store wave 4): an old run is a run folder with run.json and no lines.arrow of the current format with the result
view's columns; the dry run lists them (and the leftovers runs/index.html, findaline_map.html) and writes nothing at
all; --yes deletes them with their database rows and favourite lines (Jobs.delete_run), keeps everything else, and
rewrites runs.js. Old runs are made by tests/old_runs.py from a copy of the clip's run."""

import contextlib
import gc
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
import cache  # noqa: E402
import clip_runs  # noqa: E402
import findaline  # noqa: E402
import jobs as jb  # noqa: E402
import old_runs  # noqa: E402
import runs as rn  # noqa: E402

PREFIX = "2026-10-01_000000_"
OLD = {kind: f"{PREFIX}{kind.replace('_', '')}_000000000000000{n}" for n, kind in
       enumerate(("data_js", "no_html", "tiled", "no_view", "unreadable"), 1)}
KEPT = {name: f"{PREFIX}{name}_00000000000000{n}" for n, name in
        enumerate(("withtext", "running", "unsaved", "newer"), 10)}


def _data(tmp_path_factory, name: str, database: bool = True):
    """A data folder: the clip's run (current) and a run of every kind of spec 2.2 copied from it, the leftovers,
    and (database) a jobs.sqlite with rows of owners, a share link, a demo, favourites, a folder, jobs and a report,
    and an accounts.sqlite whose user's name and e-mail must never be listed. Returns (data folder, current id)."""
    source = clip_runs.view_clip(tmp_path_factory, f"remove-old-src-{name}")
    data = tmp_path_factory.mktemp(f"remove-old-{name}")
    runs = data / "runs"
    runs.mkdir()
    current = source.name
    shutil.copytree(source, runs / current)
    shutil.copytree(source.parent / "_viewer", runs / "_viewer")
    for kind, run_id in OLD.items():
        folder = old_runs.copy_run(source, runs, run_id)
        if kind == "unreadable":
            (folder / "lines.arrow").write_bytes(b"not an arrow file")
        else:
            old_runs.make_old(folder, kind)
    old_runs.make_old(old_runs.copy_run(source, runs, KEPT["withtext"]), "with_text")
    old_runs.make_running(old_runs.make_old(old_runs.copy_run(source, runs, KEPT["running"]), "data_js"))
    old_runs.make_unsaved(old_runs.copy_run(source, runs, KEPT["unsaved"]))
    old_runs.newer_store(old_runs.copy_run(source, runs, KEPT["newer"]))
    old_runs.make_leftovers(data)
    rn.write_index(str(runs))
    if database:
        jobs = jb.Jobs(str(data))
        for run_id, user in ((OLD["data_js"], 7), (OLD["no_html"], 8), (current, 7), (KEPT["withtext"], None)):
            jobs.add_run(run_id, user, 1000)
        jobs.set_share(OLD["data_js"], "f" * 64)
        jobs.set_visibility(OLD["no_html"], "demo")
        folder = jobs.add_folder(7, "Trip")
        jobs.set_favourite(7, OLD["data_js"], "1,2,3,4", {"len": 50.0}, folder)
        jobs.set_favourite(7, OLD["data_js"], "1,2,3,5", {"len": 51.0})
        jobs.set_favourite(7, current, "1,2,3,6", {"len": 52.0}, folder)
        for run_id in (OLD["data_js"], current):
            job = jobs.add({"params": {}, "geometry": None}, "a search", 7)
            with contextlib.closing(sqlite3.connect(jobs.path)) as db, db:
                db.execute("UPDATE jobs SET status = 'done', run_id = ? WHERE id = ?", (run_id, job))
        jobs.add_report(7, "result", "a report", {"run": OLD["data_js"]})
        with contextlib.closing(sqlite3.connect(data / "accounts.sqlite")) as db, db:
            db.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT, email TEXT)")
            db.execute("INSERT INTO users VALUES (7, 'Jane Private', 'jane@example.org')")
        del jobs
        gc.collect()  # the connections closed: no -wal, -shm left by this process
        assert not [n for n in os.listdir(data) if n.startswith("jobs.sqlite-")]
    return data, current


def _state(data) -> dict:
    """Every file of the data folder (but the runs lock's own file) with its bytes' sha256 and mtime."""
    state = {}
    for root, _, files in os.walk(data):
        for name in files:
            path = os.path.join(root, name)
            if name == cache.RUNS_LOCK:
                continue
            with open(path, "rb") as f:
                state[os.path.relpath(path, data)] = (hashlib.sha256(f.read()).hexdigest(), os.stat(path).st_mtime_ns)
    return state


def _run(data, *flags) -> tuple:
    """findaline.py runs remove-old in a process of its own: (exit status, output)."""
    result = subprocess.run([sys.executable, "findaline.py", "runs", "remove-old", *flags, "--data-dir", str(data)],
                            cwd=REPO, capture_output=True, text=True, encoding="utf-8", timeout=300,
                            env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    return result.returncode, result.stdout + result.stderr


def test_finds_the_old_runs(tmp_path_factory):
    """runs.old_runs: every kind of spec 2.2 and an unreadable store are old; the current store, the text files
    beside a current store, a run being saved, a tiled search running and a store of a newer format are not."""
    data, current = _data(tmp_path_factory, "find", database=False)
    found = rn.old_runs(str(data / "runs"))
    assert sorted(r["id"] for r in found["old"]) == sorted(OLD.values())
    assert [r["id"] for r in found["old"] if r["unreadable"]] == [OLD["unreadable"]]
    assert sorted(found["current"]) == sorted([current, KEPT["withtext"]])
    assert dict(found["skipped"]) == {KEPT["running"]: "a tiled search still running",
                                      KEPT["unsaved"]: "being saved: no run.json",
                                      KEPT["newer"]: "made by a newer Find-a-Line"}


def test_dry_run_writes_nothing(tmp_path_factory):
    """--dry-run lists exactly the old runs, the leftovers and the skipped ones, with their owner (user id), share,
    demo and favourite lines and the totals, never a name or an e-mail, and changes no byte and no time of any
    file (jobs.sqlite read read-only: no -wal or -shm left)."""
    data, current = _data(tmp_path_factory, "dry")
    before = _state(data)
    status, output = _run(data, "--dry-run")
    assert status == 0, output
    assert _state(data) == before
    lines = output.splitlines()
    assert lines[0] == f"Old runs in {data / 'runs'}: 5 (saved before the current store; they will no longer open)"
    for run_id in OLD.values():
        assert any(line.startswith(run_id) for line in lines), run_id
    row = next(line for line in lines if line.startswith(OLD["data_js"])).split()
    assert row[-4:] == ["7", "yes", "no", "2"], row
    row = next(line for line in lines if line.startswith(OLD["no_html"])).split()
    assert row[-4:] == ["8", "no", "yes", "0"], row
    assert any(line.startswith(OLD["unreadable"] + " (store unreadable)") for line in lines)
    for run_id in (current, *KEPT.values()):
        assert not any(line.startswith(run_id) for line in lines), run_id  # skipped ones are indented
    assert any(line.startswith("Total: 5 runs, ") and line.endswith(", 2 favourite lines, 1 search leaves the list "
                                                                      "on Home.") for line in lines), output
    assert "Also deleted: runs/index.html, findaline_map.html (they list or open old runs only)." in lines
    assert "Kept: 2 runs with the current store." in output
    for reason in ("being saved: no run.json", "a tiled search still running", "made by a newer Find-a-Line"):
        assert reason in output
    assert lines[-1] == ("Nothing was deleted (--dry-run). To delete these runs: findaline.py runs remove-old --yes "
                         f'--data-dir "{data}"')
    assert "Jane" not in output and "@" not in output


def test_yes_deletes_the_old_runs_only(tmp_path_factory):
    """--yes deletes the old runs' folders, their runs rows and favourite lines and the leftovers; keeps every other
    folder, the folder of favourites, the jobs' rows (the one that saved an old run marked removed) and the report;
    runs.js lists no removed run; a second --yes finds nothing."""
    data, current = _data(tmp_path_factory, "yes")
    status, output = _run(data, "--yes")
    assert status == 0, output
    assert sorted(os.listdir(data / "runs")) == sorted(["_viewer", "runs.js", cache.RUNS_LOCK, current,
                                                        *KEPT.values()]) or \
        sorted(os.listdir(data / "runs")) == sorted(["_viewer", "runs.js", current, *KEPT.values()])
    assert not (data / "findaline_map.html").exists()
    listed = json.loads((data / "runs" / "runs.js").read_text("utf-8").partition(" = ")[2].rstrip().rstrip(";"))
    assert sorted(r["id"] for r in listed) == sorted([current, KEPT["withtext"], KEPT["running"], KEPT["newer"]])
    jobs = jb.Jobs(str(data))
    assert sorted(r["run_id"] for r in jobs.all_runs()) == sorted([current, KEPT["withtext"]])
    assert [f["run_id"] for f in jobs.favourites(7)] == [current]
    assert [f["name"] for f in jobs.folders(7)] == ["Trip"]
    assert len(jobs.reports()) == 1
    removed = {j["run_id"]: j["removed_at"] for j in jobs.all()}
    assert removed[OLD["data_js"]] and not removed[current]
    assert "Jane" not in output and "@" not in output
    status, output = _run(data, "--yes")
    assert status == 0 and output.splitlines()[0] == f"Old runs in {data / 'runs'}: 0", output


def test_without_a_database(tmp_path_factory):
    """A data folder of the command line alone (no jobs.sqlite): the list has no owner, share, demo or favourites,
    the dry run writes nothing, --yes deletes the folders."""
    data, current = _data(tmp_path_factory, "plain", database=False)
    before = _state(data)
    status, output = _run(data, "--dry-run")
    assert status == 0 and _state(data) == before, output
    assert "Owner" not in output and "favourite" not in output.lower()
    assert not (data / "jobs.sqlite").exists()
    status, output = _run(data, "--yes")
    assert status == 0, output
    assert not any((data / "runs" / run_id).exists() for run_id in OLD.values())
    assert (data / "runs" / current).is_dir() and not (data / "jobs.sqlite").exists()


def test_usage(tmp_path):
    """Neither flag, both, or another verb: a usage error (exit 2); a data folder without runs/ lists nothing and
    makes no folder."""
    for argv in (["remove-old"], ["remove-old", "--dry-run", "--yes"], ["list"]):
        with pytest.raises(SystemExit) as stop:
            findaline.runs_main(argv)
        assert stop.value.code == 2
    assert findaline.runs_main(["remove-old", "--dry-run", "--data-dir", str(tmp_path)]) == 0
    assert os.listdir(tmp_path) == []
