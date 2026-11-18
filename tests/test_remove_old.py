"""`findaline.py runs remove-old (--dry-run | --yes) [--data-dir DIR]` (docs/line-volume/spec-store.md 2.2-2.10,
store wave 4): an old run is a run folder with run.json and no lines.arrow of the current format with the result
view's columns (a run whose view columns failed at saving, run.json's view_columns_failed, is a run of today); the
dry run lists them (and the leftovers runs/index.html, findaline_map.html, runs/_removing-<id>) and writes nothing in
the data folder; --yes deletes them with their database rows and favourite lines, keeps everything else, and
rewrites runs.js. A run is never deleted on a read error (it is skipped), and a removal is a rename first (a file
held open keeps the run whole; a folder left after the rename is finished by the next --yes). Old runs are made by
tests/old_runs.py from a copy of the clip's run."""

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
import linestore  # noqa: E402
import old_runs  # noqa: E402
import runs as rn  # noqa: E402

PREFIX = "2026-10-01_000000_"
OLD = {kind: f"{PREFIX}{kind.replace('_', '')}_000000000000000{n}" for n, kind in
       enumerate(("data_js", "no_html", "tiled", "no_view", "unreadable"), 1)}
KEPT = {name: f"{PREFIX}{name}_00000000000000{n}" for n, name in
        enumerate(("withtext", "running", "unsaved", "newer", "viewfail"), 10)}
FACTS = ("1 a tiled search still running", "1 being saved: no run.json", "1 made by a newer Find-a-Line")


def _data(tmp_path_factory, name: str, database: bool = True):
    """A data folder: the clip's run (current) and a run of every kind of spec 2.2 copied from it, the leftovers,
    a run whose view columns failed (current), and (database) a jobs.sqlite with rows of owners, a share link, a
    demo, favourites, a folder, jobs and a report, and an accounts.sqlite whose user's name and e-mail must never be
    listed. Returns (data folder, current id)."""
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
    failed = old_runs.copy_run(source, runs, KEPT["viewfail"])  # saved by today's code, its view columns failed
    old_runs.drop_view(failed)
    meta = json.loads((failed / "run.json").read_text("utf-8"))
    (failed / "run.json").write_text(json.dumps({**meta, rn.VIEW_FAILED: True}), "utf-8")
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
    """Every folder and file of the data folder (but the runs lock's own file), a file with its bytes' sha256 and
    mtime: a folder the dry run made shows too (a folder's own mtime is left out: the runs lock's file, made and
    removed in runs/, moves it)."""
    state = {}
    for root, folders, files in os.walk(data):
        for name in folders:
            state[os.path.relpath(os.path.join(root, name), data) + os.sep] = "folder"
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


def _in_process(data, *flags, capsys) -> tuple:
    """runs_main in this process (so a test can inject a failure): (exit status, its output alone)."""
    capsys.readouterr()  # what the fixture printed before
    status = findaline.runs_main(["remove-old", *flags, "--data-dir", str(data)])
    return status, capsys.readouterr().out


def _listed(data) -> list:
    text = (data / "runs" / "runs.js").read_text("utf-8")
    return sorted(r["id"] for r in json.loads(text.partition(" = ")[2].rstrip().rstrip(";")))


def test_finds_the_old_runs(tmp_path_factory):
    """runs.old_runs: every kind of spec 2.2 and an unreadable store are old; the current store, the text files
    beside a current store, a run whose view columns failed, a run being saved, a tiled search running and a store
    of a newer format are not."""
    data, current = _data(tmp_path_factory, "find", database=False)
    found = rn.old_runs(str(data / "runs"))
    assert sorted(r["id"] for r in found["old"]) == sorted(OLD.values())
    assert [r["id"] for r in found["old"] if r["unreadable"]] == [OLD["unreadable"]]
    assert sorted(found["current"]) == sorted([current, KEPT["withtext"], KEPT["viewfail"]])
    assert dict(found["skipped"]) == {KEPT["running"]: "a tiled search still running",
                                      KEPT["unsaved"]: "being saved: no run.json",
                                      KEPT["newer"]: "made by a newer Find-a-Line"}
    assert found["removing"] == []


def test_store_state_never_calls_a_read_error_broken(tmp_path, monkeypatch):
    """linestore.store_state: a file that cannot be opened or read now (OSError: a file held by another program, a
    disk error; MemoryError) is "cannot_read", never "unreadable"; a file that opens and is no Arrow file of ours is
    "unreadable"; a store of today's format without the view's columns is "no_view"."""
    import pyarrow as pa
    (tmp_path / "lines.arrow").write_bytes(b"not an arrow file")
    assert linestore.store_state(str(tmp_path)) == "unreadable"
    real = pa.OSFile
    for error in (PermissionError(13, "held by another program"), OSError(5, "I/O error"), MemoryError()):
        def failing(path, mode="rb", error=error):
            raise error
        monkeypatch.setattr(linestore.pa, "OSFile", failing)
        assert linestore.store_state(str(tmp_path)) == "cannot_read", error
    monkeypatch.setattr(linestore.pa, "OSFile", real)
    assert linestore.store_state(str(tmp_path / "none")) == "missing"


def test_a_read_error_keeps_a_current_run(tmp_path_factory, monkeypatch, capsys):
    """A current run whose lines.arrow cannot be read while --yes scans (a held file, a disk error) is skipped as
    "cannot read now" and kept with its row and favourites; the dry run says so in its Skipped line."""
    import pyarrow as pa
    data, current = _data(tmp_path_factory, "readerror")
    real = pa.OSFile

    def held(path, *args, **kwargs):
        if current in str(path):
            raise PermissionError(13, "held by another program", str(path))
        return real(path, *args, **kwargs)
    monkeypatch.setattr(linestore.pa, "OSFile", held)
    status, output = _in_process(data, "--dry-run", capsys=capsys)
    assert status == 0 and "Skipped: 4 (" in output and "1 cannot read now" in output, output
    status, output = _in_process(data, "--yes", capsys=capsys)
    assert status == 0, output
    assert (data / "runs" / current / "run.json").is_file()
    jobs = jb.Jobs(str(data))
    assert jobs.run(current) and [f["run_id"] for f in jobs.favourites(7)] == [current]


def test_dry_run_writes_nothing(tmp_path_factory):
    """--dry-run lists exactly the old runs and the leftovers, with their owner (user id), share, demo and favourite
    lines and the totals, the skipped and kept runs in one line (the accepted draft's words), never a name or an
    e-mail, and changes no file, no folder and no time of either (jobs.sqlite read from a copy)."""
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
        assert run_id not in output, run_id
    assert any(line.startswith("Total: 5 runs, ") and line.endswith(", 2 favourite lines, 1 search leaves the list "
                                                                      "on Home.") for line in lines), output
    assert "Also deleted: runs/index.html, findaline_map.html (they list or open old runs only)." in lines
    skipped = next(line for line in lines if line.startswith("Skipped: 3 ("))
    assert skipped.endswith(").  Kept: 3 runs with the current store.") and all(f in skipped for f in FACTS), skipped
    assert lines[-1] == ("Nothing was deleted (--dry-run). To delete these runs: findaline.py runs remove-old --yes "
                         f'--data-dir "{data}"')
    assert "Jane" not in output and "@" not in output


def test_yes_deletes_the_old_runs_only(tmp_path_factory):
    """--yes deletes the old runs' folders, their runs rows and favourite lines and the leftovers, and prints the
    table of what it deleted; keeps every other folder (the run whose view columns failed too), the folder of
    favourites, the jobs' rows (the one that saved an old run marked removed) and the report; runs.js lists no
    removed run; a second --yes finds nothing."""
    data, current = _data(tmp_path_factory, "yes")
    status, output = _run(data, "--yes")
    assert status == 0, output
    lines = output.splitlines()
    assert lines[0] == f"Deleted from {data / 'runs'}: 5 runs (saved before the current store)", output
    for run_id in OLD.values():
        assert any(line.startswith(run_id) for line in lines), run_id
    assert any(line.startswith("Total: 5 runs, ") for line in lines), output
    assert "Also deleted: runs/index.html, findaline_map.html." in lines and "Not deleted" not in output
    assert sorted(set(os.listdir(data / "runs")) - {cache.RUNS_LOCK}) == sorted(["_viewer", "runs.js", current,
                                                                                *KEPT.values()])
    assert not (data / "findaline_map.html").exists()
    assert _listed(data) == sorted([current, KEPT["withtext"], KEPT["running"], KEPT["newer"], KEPT["viewfail"]])
    jobs = jb.Jobs(str(data))
    assert sorted(r["run_id"] for r in jobs.all_runs()) == sorted([current, KEPT["withtext"]])
    assert [f["run_id"] for f in jobs.favourites(7)] == [current]
    assert [f["name"] for f in jobs.folders(7)] == ["Trip"]
    assert len(jobs.reports()) == 1
    removed = {j["run_id"]: j["removed_at"] for j in jobs.all()}
    assert removed[OLD["data_js"]] and not removed[current]
    assert "Jane" not in output and "@" not in output
    status, output = _run(data, "--yes")
    assert status == 0 and output.splitlines()[0] == f"Deleted from {data / 'runs'}: 0 runs", output


def test_a_held_file_keeps_the_run_whole(tmp_path_factory, monkeypatch, capsys):
    """A file held open in an old run (Windows refuses the rename of its folder): that run is reported "Not deleted"
    and stays whole (its run.json, its row and favourites), the others go, the leftovers go and runs.js is written
    again, exit status 1; once the file is free the next --yes deletes it. Elsewhere than Windows the rename is made
    to fail instead."""
    data, current = _data(tmp_path_factory, "held")
    folder = data / "runs" / OLD["data_js"]
    real = rn.park_run
    if os.name != "nt":
        def park(runs_dir, run_id):
            if run_id == OLD["data_js"]:
                raise PermissionError(13, "held", run_id)
            return real(runs_dir, run_id)
        monkeypatch.setattr(rn, "park_run", park)
    with open(folder / "lines.csv", "rb"):
        status, output = _in_process(data, "--yes", capsys=capsys)
    assert status == 1 and "Not deleted: 1" in output and f"  {OLD['data_js']}: PermissionError" in output, output
    assert (folder / "run.json").is_file() and (folder / "data.js").is_file()
    assert not any((data / "runs" / run_id).exists() for kind, run_id in OLD.items() if kind != "data_js")
    assert not (data / "runs" / "index.html").exists() and OLD["data_js"] in _listed(data)
    jobs = jb.Jobs(str(data))
    assert jobs.run(OLD["data_js"]) and len(jobs.favourites(7)) == 3
    monkeypatch.setattr(rn, "park_run", real)
    status, output = _in_process(data, "--yes", capsys=capsys)
    assert status == 0 and not folder.exists() and not jobs.run(OLD["data_js"]), output


def test_an_unfinished_removal_is_finished_later(tmp_path_factory, monkeypatch, capsys):
    """A folder that cannot be deleted after its rename (a file held then): the run is gone (its row, its
    favourites, runs.js), its bytes stay as runs/_removing-<id>, said with exit status 1; the runs lock is free while
    the folder is deleted (a search saving meanwhile never waits for it); the dry run lists the folder, and the next
    --yes deletes it."""
    from filelock import FileLock
    data, current = _data(tmp_path_factory, "unfinished")
    real = rn.finish_removal
    free = []

    def finish(parked):
        lock = FileLock(os.path.join(str(data / "runs"), cache.RUNS_LOCK))
        lock.acquire(timeout=0)  # raises filelock.Timeout while remove-old holds the lock
        lock.release()
        free.append(parked)
        if parked and parked.endswith(OLD["tiled"]):
            raise PermissionError(32, "held", parked)
        return real(parked)
    monkeypatch.setattr(rn, "finish_removal", finish)
    status, output = _in_process(data, "--yes", capsys=capsys)
    parked = data / "runs" / f"{rn.REMOVING}{OLD['tiled']}"
    assert status == 1 and "Left on disk (a file held open): 1." in output and parked.is_dir(), output
    assert len(free) == 5 and OLD["tiled"] not in _listed(data)
    assert not jb.Jobs(str(data)).run(OLD["tiled"])
    status, output = _in_process(data, "--dry-run", capsys=capsys)
    assert (f"Also deleted: runs/{rn.REMOVING}{OLD['tiled']} (left by a removal that did not finish)."
            in output.splitlines()), output
    monkeypatch.setattr(rn, "finish_removal", real)
    status, output = _in_process(data, "--yes", capsys=capsys)
    assert status == 0 and not parked.exists() and f"runs/{rn.REMOVING}{OLD['tiled']}" in output, output


def test_a_database_error_keeps_the_run_and_goes_on(tmp_path_factory, monkeypatch, capsys):
    """The database failing for one run (a locked database): its folder is renamed back, so the run stays whole with
    its row (never a row of a missing run); the other runs go, the leftovers go and runs.js is written again; exit
    status 1."""
    data, current = _data(tmp_path_factory, "dberror")
    real = jb.Jobs.forget_run

    def forget(self, run_id):
        if run_id == OLD["no_html"]:
            raise sqlite3.OperationalError("database is locked")
        return real(self, run_id)
    monkeypatch.setattr(jb.Jobs, "forget_run", forget)
    status, output = _in_process(data, "--yes", capsys=capsys)
    assert status == 1 and f"  {OLD['no_html']}: OperationalError: database is locked" in output, output
    assert (data / "runs" / OLD["no_html"] / "run.json").is_file() and jb.Jobs(str(data)).run(OLD["no_html"])
    assert not (data / "runs" / f"{rn.REMOVING}{OLD['no_html']}").exists()
    assert not (data / "runs" / OLD["data_js"]).exists() and not (data / "findaline_map.html").exists()
    assert OLD["no_html"] in _listed(data) and OLD["data_js"] not in _listed(data)


def test_the_apps_delete_renames_first(tmp_path_factory, monkeypatch):
    """Jobs.delete_run (also the app's "Delete…"): a rename that fails raises and changes nothing (the folder whole,
    its row kept); a folder that cannot be deleted after the rename is returned, the run gone (its row, its
    favourites), its folder runs/_removing-<id>."""
    data, current = _data(tmp_path_factory, "delete")
    runs_dir = str(data / "runs")
    jobs = jb.Jobs(str(data))
    folder = data / "runs" / OLD["data_js"]
    if os.name == "nt":
        with open(folder / "data.js", "rb"), pytest.raises(OSError):
            jobs.delete_run(OLD["data_js"], runs_dir)
        assert (folder / "run.json").is_file() and jobs.run(OLD["data_js"])
    real = rn.finish_removal

    def held(parked):
        raise PermissionError(32, "held", parked)
    monkeypatch.setattr(rn, "finish_removal", held)
    left = jobs.delete_run(OLD["data_js"], runs_dir)
    assert left == os.path.join(runs_dir, rn.REMOVING + OLD["data_js"]) and os.path.isdir(left)
    assert not folder.exists() and not jobs.run(OLD["data_js"]) and len(jobs.favourites(7)) == 1
    monkeypatch.setattr(rn, "finish_removal", real)
    assert jobs.delete_run(current, runs_dir) is None and not (data / "runs" / current).exists()


def test_yes_writes_no_runs_js_where_none_was(tmp_path_factory):
    """The public site's data folder has no runs/runs.js (the worker writes none): --yes writes none either."""
    data, current = _data(tmp_path_factory, "public")
    os.remove(data / "runs" / "runs.js")
    status, output = _run(data, "--yes")
    assert status == 0 and not (data / "runs" / "runs.js").exists(), output


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


def _facts_database(path):
    """A jobs.sqlite as Jobs makes it, with one run of user 7 and one favourite line in it."""
    jobs = jb.Jobs(str(path))
    jobs.add_run("r1", 7, 100)
    jobs.set_favourite(7, "r1", "1,2,3,4", {"len": 50.0})
    del jobs
    gc.collect()
    return path / "jobs.sqlite"


def test_run_facts_reads_a_live_database(tmp_path):
    """run_facts with the app's connection open (its -wal beside the database, not checkpointed: the live server's
    case): the copy holds the -wal's rows; the data folder gets no file."""
    database = _facts_database(tmp_path)
    live = sqlite3.connect(database)
    try:
        live.execute("PRAGMA journal_mode=WAL")
        live.execute("PRAGMA wal_autocheckpoint=0")
        live.execute("INSERT INTO favourites (user_id, run_id, line, data, created) VALUES (8, 'r1', 'x', '{}', 'now')")
        live.execute("INSERT INTO runs (run_id, user_id, bytes, created) VALUES ('r2', 9, 1, 'now')")
        live.commit()
        assert (tmp_path / "jobs.sqlite-wal").stat().st_size > 0
        before = sorted(os.listdir(tmp_path))
        facts = jb.run_facts(str(database))
        assert sorted(os.listdir(tmp_path)) == before
    finally:
        live.close()
    assert facts["r1"]["favourites"] == 2 and facts["r1"]["user_id"] == 7 and facts["r2"]["user_id"] == 9


def test_run_facts_of_an_older_schema_and_failures(tmp_path, monkeypatch):
    """run_facts: a database of an older schema (no runs or favourites tables) reads as no facts, never an error; a
    copy that cannot be made, or a copy that fails its check, is made again FACTS_TRIES times and then gives None
    (the listing goes on without the facts); its temporary copies are gone on every path."""
    older = tmp_path / "older"
    older.mkdir()
    with contextlib.closing(sqlite3.connect(older / "jobs.sqlite")) as db, db:
        db.execute("CREATE TABLE jobs (id TEXT PRIMARY KEY, status TEXT)")
    assert jb.run_facts(str(older / "jobs.sqlite")) == {}
    database = _facts_database(tmp_path)
    made = []
    real_mkdtemp = jb.tempfile.mkdtemp
    monkeypatch.setattr(jb.tempfile, "mkdtemp", lambda **kwargs: made.append(real_mkdtemp(**kwargs)) or made[-1])
    tries = []

    def failing_copy(source, target):
        tries.append(source)
        open(target, "wb").close()
        raise OSError(28, "No space left on device")
    monkeypatch.setattr(jb.shutil, "copyfile", failing_copy)
    assert jb.run_facts(str(database)) is None and len(tries) == jb.FACTS_TRIES
    assert len(made) == jb.FACTS_TRIES and not any(os.path.exists(folder) for folder in made)
    monkeypatch.undo()
    monkeypatch.setattr(jb.tempfile, "mkdtemp", lambda **kwargs: made.append(real_mkdtemp(**kwargs)) or made[-1])
    real_connect = jb.sqlite3.connect

    class Broken:  # a copy whose check fails (pages copied from two moments)
        def __init__(self, path, **kwargs):
            self.db = real_connect(path, **kwargs)

        def execute(self, query):
            if query.startswith("PRAGMA quick_check"):
                raise sqlite3.DatabaseError("database disk image is malformed")
            return self.db.execute(query)

        def close(self):
            self.db.close()
    monkeypatch.setattr(jb.sqlite3, "connect", Broken)
    assert jb.run_facts(str(database)) is None
    assert not any(os.path.exists(folder) for folder in made)


def test_dry_run_without_the_databases_facts(tmp_path_factory, monkeypatch, capsys):
    """When jobs.sqlite cannot be read (run_facts gives None), the dry run lists the runs without the facts' columns
    and says so, never a traceback."""
    data, current = _data(tmp_path_factory, "nofacts")
    monkeypatch.setattr(jb, "run_facts", lambda path: None)
    status, output = _in_process(data, "--dry-run", capsys=capsys)
    assert status == 0 and "Owner" not in output and findaline.FACTS_NOTE in output.splitlines(), output


def test_usage(tmp_path):
    """Neither flag, both, or another verb: a usage error (exit 2); a data folder without runs/ lists nothing and
    makes no folder."""
    for argv in (["remove-old"], ["remove-old", "--dry-run", "--yes"], ["list"]):
        with pytest.raises(SystemExit) as stop:
            findaline.runs_main(argv)
        assert stop.value.code == 2
    assert findaline.runs_main(["remove-old", "--dry-run", "--data-dir", str(tmp_path)]) == 0
    assert os.listdir(tmp_path) == []


def test_a_stopped_removal_loses_its_rows_too(tmp_path_factory, capsys):
    """A removal stopped between the rename and the rows (a kill: the folder parked, its row and favourites still
    there): the next --yes finishes the folder and deletes the rows, since no runs/<id> came back; a parked folder
    whose run id exists again (a restored backup) keeps that run's rows."""
    data, current = _data(tmp_path_factory, "stopped")
    runs_dir = str(data / "runs")
    rn.park_run(runs_dir, OLD["data_js"])  # the kill: no forget_run
    jobs = jb.Jobs(str(data))
    assert jobs.run(OLD["data_js"]) and len(jobs.favourites(7)) == 3
    shutil.copytree(data / "runs" / current, data / "runs" / f"{rn.REMOVING}{current}")  # a parked copy of a run
    status, output = _in_process(data, "--yes", capsys=capsys)
    assert status == 0, output
    assert not jobs.run(OLD["data_js"]) and [f["run_id"] for f in jobs.favourites(7)] == [current]
    assert jobs.run(current) and (data / "runs" / current / "run.json").is_file()
    assert not [n for n in os.listdir(runs_dir) if n.startswith(rn.REMOVING)]


def test_ctrl_c_still_says_what_went(tmp_path_factory, monkeypatch, capsys):
    """Ctrl+C during --yes (here while the third run's folder is deleted): the runs deleted so far are printed in
    the table, the leftovers and runs.js are still done, and the exit status is not 0."""
    data, current = _data(tmp_path_factory, "ctrlc")
    real = rn.finish_removal
    calls = []

    def finish(parked):
        calls.append(parked)
        if len(calls) == 3:
            raise KeyboardInterrupt
        return real(parked)
    monkeypatch.setattr(rn, "finish_removal", finish)
    status, output = _in_process(data, "--yes", capsys=capsys)
    assert status == 130 and output.splitlines()[0].startswith(f"Deleted from {data / 'runs'}: 3 runs"), output
    assert "Stopped (Ctrl+C)" in output.splitlines()[-1] and not (data / "findaline_map.html").exists()
    gone = [run_id for run_id in OLD.values() if not (data / "runs" / run_id).exists()]
    assert len(gone) == 3 and all(any(line.startswith(run_id) for line in output.splitlines()) for run_id in gone)
    assert not set(gone) & set(_listed(data))


def test_yes_rechecks_each_run(tmp_path_factory, monkeypatch, capsys):
    """--yes checks each run again under the lock before its removal: a run in the list that is not old any more
    (here a current run listed by a scan that went wrong) is kept and named."""
    data, current = _data(tmp_path_factory, "recheck")
    real = rn.old_runs

    def scan(runs_dir):
        found = real(runs_dir)
        found["old"].append({"id": current, "created": "", "lines": 1, "bytes": 1, "unreadable": False})
        return found
    monkeypatch.setattr(rn, "old_runs", scan)
    status, output = _in_process(data, "--yes", capsys=capsys)
    assert status == 0 and f"Kept, changed since the list: 1 ({current}: current)." in output, output
    assert (data / "runs" / current / "run.json").is_file() and jb.Jobs(str(data)).run(current)


def test_park_and_finish(tmp_path):
    """runs.park_run over a parked folder of the same id finishes that first; finish_removal removes a link or a
    junction inside a run, and a parked folder that is itself one, without touching what it points to."""
    runs_dir = tmp_path / "runs"
    (runs_dir / "a").mkdir(parents=True)
    (runs_dir / "a" / "run.json").write_text("{}")
    (runs_dir / f"{rn.REMOVING}a").mkdir()
    (runs_dir / f"{rn.REMOVING}a" / "left.txt").write_text("x")
    parked = rn.park_run(str(runs_dir), "a")
    assert sorted(os.listdir(parked)) == ["run.json"] and not (runs_dir / "a").exists()
    assert rn.park_run(str(runs_dir), "none") is None
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keep.txt").write_text("kept")

    def link(target, at):
        if os.name == "nt":  # a junction needs no privilege
            subprocess.run(["cmd", "/c", "mklink", "/J", str(at), str(target)], check=True, capture_output=True)
        else:
            os.symlink(target, at, target_is_directory=True)
    link(outside, os.path.join(parked, "tiles"))
    rn.finish_removal(parked)
    assert not os.path.lexists(parked) and (outside / "keep.txt").read_text() == "kept"
    linked = runs_dir / f"{rn.REMOVING}b"
    link(outside, linked)
    rn.finish_removal(str(linked))
    assert not os.path.lexists(linked) and (outside / "keep.txt").read_text() == "kept"


def test_the_apps_delete_renames_back(tmp_path_factory, monkeypatch):
    """Jobs.delete_run: the database failing after the rename puts the folder back under its name and raises, the
    run whole with its row."""
    data, current = _data(tmp_path_factory, "renameback")
    jobs = jb.Jobs(str(data))

    def locked(self, run_id):
        raise sqlite3.OperationalError("database is locked")
    monkeypatch.setattr(jb.Jobs, "forget_run", locked)
    with pytest.raises(sqlite3.OperationalError):
        jobs.delete_run(current, str(data / "runs"))
    assert (data / "runs" / current / "run.json").is_file() and not (data / "runs" / f"{rn.REMOVING}{current}").exists()
    assert jobs.run(current)


def test_housekeeping_finishes_stopped_removals(tmp_path_factory, capsys):
    """The worker's housekeeping finishes a parked folder older than runs.REMOVING_AGE (a restart of the web in the
    middle of a Delete): its rows and its folder go; a fresh one (a Delete still at work) is left alone."""
    from settings import Limits
    data, current = _data(tmp_path_factory, "housekeeping")
    runs_dir = str(data / "runs")
    stale = rn.park_run(runs_dir, OLD["data_js"])
    old = __import__("time").time() - rn.REMOVING_AGE - 60
    os.utime(stale, (old, old))
    fresh = rn.park_run(runs_dir, current)
    scheduler = jb.Scheduler(jb.Jobs(str(data)), worker_id="w-house", limits=Limits())
    scheduler.housekeeping()
    jobs = jb.Jobs(str(data))
    assert not os.path.exists(stale) and not jobs.run(OLD["data_js"])
    assert os.path.isdir(fresh) and jobs.run(current)


def test_cache_status_skips_parked_folders(tmp_path_factory):
    """`findaline.py cache status` (update.changed_runs) reads no folder starting with "_" or ".", as list_runs."""
    import update
    data, current = _data(tmp_path_factory, "cachestatus", database=False)
    rn.park_run(str(data / "runs"), OLD["data_js"])
    meta = json.loads((data / "runs" / current / "run.json").read_text("utf-8"))
    meta["data"] = [{"paths": ["missing/file.tif"]}]
    (data / "runs" / current / "run.json").write_text(json.dumps(meta), "utf-8")
    parked = data / "runs" / f"{rn.REMOVING}{OLD['data_js']}" / "run.json"
    parked.write_text(json.dumps(meta), "utf-8")
    assert [name for name, _, _ in update.changed_runs(str(data / "cache"), str(data / "runs"))] == [current]
