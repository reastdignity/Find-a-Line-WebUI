"""tools/test_lock.py: a full pytest under the lock runs its files in parallel processes (pytest-xdist,
`-n MODE_WORKERS[mode] --dist loadfile` added after the word pytest) unless the caller chose; its kind,
estimates and peaks apart from serial runs', its workers' threads, the slots a shared one counts and
keeps reserved while it waits (later one-slot commands pass it only in time), and the wrapper making
a real full pytest parallel (its own queue in tmp_path)."""

import os
import sqlite3
import subprocess
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "tools"))

import test_lock as tl  # noqa: E402

TOOL = os.path.join(REPO, "tools", "test_lock.py")
PY = r"C:\x\.venv\Scripts\python.exe"
G = tl.GB


def entry(id, command="c", mode="shared", started=True, at=1.0, expect=None, tamed=False):
    return tl.Entry(id, f"t{id}", mode, [], "x", 1, command, 0.0, at if started else None, expect, tamed=tamed)


def parallel(workers=4):
    return tl.shlex.join([PY, "-m", "pytest", "-n", str(workers), "--dist", "loadfile", "-q"])


def test_a_full_pytest_gets_workers():
    """`-n K --dist loadfile` right after the word pytest, in the python, uv and plain forms; the kind
    pytest-all-xdist, a key of its own."""
    assert tl.parallel_command([PY, "-m", "pytest", "-q", "-W", "default"], 4) == \
        [PY, "-m", "pytest", "-n", "4", "--dist", "loadfile", "-q", "-W", "default"]
    assert tl.parallel_command(["uv", "run", "--frozen", "pytest", "-q"], 8) == \
        ["uv", "run", "--frozen", "pytest", "-n", "8", "--dist", "loadfile", "-q"]
    assert tl.parallel_command(["pytest", "--junitxml", "out.xml", "--basetemp", r"C:\fal\x"], 4)[:5] == \
        ["pytest", "-n", "4", "--dist", "loadfile"]
    command = tl.parallel_command([PY, "-I", "-m", "pytest", "-p", "no:cacheprovider", "--deselect", "tests/a.py"], 4)
    assert tl.command_kind(command) == tl.PARALLEL_KIND and tl.pytest_workers(command) == 4
    assert tl.command_kind([PY, "-m", "pytest", "-q"]) == "pytest-all"
    assert tl.command_key(command) != tl.command_key([PY, "-I", "-m", "pytest", "-p", "no:cacheprovider",
                                                      "--deselect", "tests/a.py"])


@pytest.mark.parametrize("args", [
    ["-n", "4"], ["-n", "0"], ["-n4"], ["-n", "auto"], ["--numprocesses=2"], ["--numprocesses", "2"],
    ["--dist", "loadscope"], ["--dist=load"], ["--tx", "popen"], ["--maxprocesses", "2"],
    ["-p", "no:xdist"], ["-pno:xdist"], ["--pdb"], ["--trace"], ["-s"], ["-xs"], ["-sv"], ["--capture=no"],
    ["--capture", "no"], ["--co"], ["--collect-only"], ["-f"], ["--looponfail"], ["--sw"], ["--stepwise"],
    ["--sw-skip"], ["--stepwise-skip"], ["tests/test_web.py"], ["-k", "grouping"], ["-m", "slow"]])
def test_what_keeps_a_pytest_as_given(args):
    """The caller's own choice (an -n, a distribution, xdist off), what xdist cannot run with, and a
    pytest of chosen tests: nothing added."""
    assert tl.parallel_command([PY, "-m", "pytest", "-q", *args], 4) is None


def test_workers_counted_as_pytest_xdist_counts_them(monkeypatch):
    assert tl.pytest_workers([PY, "-m", "pytest", "-q"]) is None
    assert tl.pytest_workers([PY, "-m", "pytest", "-n", "0"]) == 0
    assert tl.pytest_workers([PY, "-m", "pytest", "-n=6"]) == 6
    assert tl.command_kind([PY, "-m", "pytest", "-n", "0"]) == "pytest-all"   # serial: the serial runs' kind
    assert tl.command_kind([PY, "-m", "pytest", "-n", "2", "tests/a.py"]) == "pytest"
    assert tl.parallel_command([PY, "-m", "pytest"], 1) is None                 # one worker: nothing to gain
    monkeypatch.setattr(tl.psutil, "cpu_count", lambda logical=True: 24 if logical else 12)
    assert tl.pytest_workers([PY, "-m", "pytest", "-n", "auto"]) == 12
    assert tl.pytest_workers([PY, "-m", "pytest", "-n", "logical"]) == 24


def test_estimates_and_peaks_apart_from_serial_runs(tmp_path):
    """A parallel full pytest is estimated from its own runs (the same command, else its kind), never
    from serial ones; with none its peak is MEMORY_BASE_GB + MEMORY_PER_WORKER_GB a worker."""
    queue = tl.Queue(str(tmp_path))
    try:
        serial = [PY, "-m", "pytest", "-q"]
        queue.record(serial, 2400.0, 0, peak=int(3.7 * G))
        waiting = entry(1, parallel(4), started=False)
        assert queue.estimate(waiting) is None
        assert queue.peak(waiting) == int((tl.MEMORY_BASE_GB + 4 * tl.MEMORY_PER_WORKER_GB) * G)
        assert queue.peak(entry(2, parallel(8), started=False)) == int((tl.MEMORY_BASE_GB + 8 * 0.65) * G)
        queue.record(tl.shlex.split(parallel(8)), 340.0, 0, peak=int(9.5 * G))
        assert queue.estimate(waiting) == 340.0 and queue.peak(waiting) == int(9.5 * G)   # its kind's
        queue.record(tl.shlex.split(parallel(4)), 640.0, 0, peak=int(8.3 * G))
        assert queue.estimate(waiting) == 640.0 and queue.peak(waiting) == int(8.3 * G)   # the same command's
        assert queue.estimate(entry(3, tl.shlex.join(serial), started=False)) == 2400.0
        kinds = dict(queue.db.execute("SELECT key, kind FROM history"))
        assert kinds[tl.command_key(tl.shlex.split(parallel(4)))] == tl.PARALLEL_KIND
    finally:
        queue.db.close()


def test_parallel_runs_of_before_migrated(tmp_path):
    """A queue of version 1 gets the kind pytest-all-xdist for its full pytest runs with -n (recorded as
    pytest-all); a serial one keeps its kind."""
    queue = tl.Queue(str(tmp_path))
    rows = (("python -m pytest -n 6 --dist loadfile -q", "pytest-all"), ("python -m pytest -q", "pytest-all"),
            ("python -m pytest -n 0", "pytest-all"))
    for key, kind in rows:
        queue.db.execute("INSERT INTO history (key, kind, seconds, code, ended) VALUES (?, ?, 1, 0, 0)", (key, kind))
    queue.db.execute("PRAGMA user_version = 1")
    queue.db.close()
    queue = tl.Queue(str(tmp_path))
    try:
        assert [k for (k,) in queue.db.execute("SELECT kind FROM history ORDER BY id")] == \
            [tl.PARALLEL_KIND, "pytest-all", "pytest-all"]
        assert queue.db.execute("PRAGMA user_version").fetchone()[0] == tl.QUEUE_VERSION == 2
    finally:
        queue.db.close()


def test_threads_of_the_workers(monkeypatch):
    """Each worker gets WORKER_THREADS whatever the mode; a tamed heavy one has fewer workers and at most
    HEAVY_TAMED_THREADS in all; other commands as before."""
    monkeypatch.setattr(tl.os, "cpu_count", lambda: 24)
    for mode in ("shared", "heavy", "exclusive"):
        env = tl._environment(mode, workers=tl.MODE_WORKERS[mode])
        assert {env[name] for name in tl.THREAD_VARS} == {str(tl.WORKER_THREADS)}
    assert tl._environment("shared")["NUMBA_NUM_THREADS"] == str(24 // tl.THREAD_SHARE)
    assert "NUMBA_NUM_THREADS" not in tl._environment("heavy") or \
        tl._environment("heavy")["NUMBA_NUM_THREADS"] == os.environ.get("NUMBA_NUM_THREADS")
    workers = tl.tamed_workers(8)
    assert workers * tl.worker_threads(workers, tamed=True) <= tl.HEAVY_TAMED_THREADS and workers >= 2
    assert tl.with_workers(tl.shlex.split(parallel(8)), workers)[3:5] == ["-n", str(workers)]


def test_slots_of_a_parallel_pytest():
    """A shared parallel pytest counts ceil(workers / WORKERS_PER_SLOT) slots (at most all of them);
    other commands one; two of them with 4 workers fit 6 slots together, beside two one-slot ones."""
    assert tl.slot_weight(entry(1, parallel(4))) == 2
    assert tl.slot_weight(entry(1, parallel(5))) == 3
    assert tl.slot_weight(entry(1, parallel(64)), slots=6) == 6
    assert tl.slot_weight(entry(1, parallel(8), mode="heavy")) == 1
    assert tl.slot_weight(entry(1, tl.shlex.join([PY, "-m", "pytest", "-n", "0"]))) == 1
    assert tl.slot_weight(entry(1, "pytest tests/a.py -n 4")) == 1
    waiting = [entry(1, parallel(4), started=False), entry(2, parallel(4), started=False),
               entry(3, started=False), entry(4, started=False), entry(5, started=False)]
    assert tl.startable(waiting, 10.0, lambda e: e.expect, slots=6) == {1, 2, 3, 4}
    text = tl._describe(entry(7, parallel(4)), 70.0)
    assert "(4 workers x 3 threads, 2 slots)" in text and "-n 4 --dist loadfile" in text


def test_a_waiting_parallel_pytest_is_not_starved():
    """Waiting for its 2 slots behind running one-slot commands, it keeps them reserved: later one-slot
    commands take a free slot only if they end in time (backfill), and it starts as soon as enough end."""
    running = [entry(1, expect=100.0), entry(2, expect=100.0)]      # 2 of 3 slots, both end at 101
    suite = entry(3, parallel(4), started=False)
    later = [entry(4, started=False), entry(5, started=False)]      # no estimate: they pass nobody
    assert tl.startable([*running, suite, *later], 10.0, lambda e: e.expect, slots=3) == set()
    quick = entry(6, started=False, expect=50.0)                    # ends at 60, before the suite's slots
    assert tl.startable([*running, suite, *later, quick], 10.0, lambda e: e.expect, slots=3) == {6}
    slow = entry(6, started=False, expect=500.0)
    assert tl.startable([*running, suite, slow], 10.0, lambda e: e.expect, slots=3) == set()
    # one of the running ends: the suite takes its 2 slots, the later ones still wait
    assert tl.startable([running[1], suite, *later], 110.0, lambda e: e.expect, slots=3) == {3}
    # with one-slot commands only, the order is as before: the first waiting one takes the free slot
    assert tl.startable([*running, entry(4, started=False), entry(5, started=False)], 10.0,
                        lambda e: e.expect, slots=3) == {4}


def test_xdist_found_in_the_commands_python(tmp_path):
    assert tl.xdist_available([sys.executable, "-m", "pytest"])     # a dev dependency of the repository
    assert not tl.xdist_available([str(tmp_path / "python.exe"), "-m", "pytest"])
    assert not tl.xdist_available([str(tmp_path / "pytest.exe")])   # no python beside it


def test_the_wrapper_runs_a_full_pytest_in_parallel(tmp_path):
    """A full pytest of a small project under the lock: its line, `-n 4 --dist loadfile` in the run's
    history (kind pytest-all-xdist), WORKER_THREADS threads in each of its 4 workers; `-n 0` serial."""
    project = tmp_path / "project"
    (project / "tests").mkdir(parents=True)
    (project / "pytest.ini").write_text("[pytest]\ntestpaths = tests\n", encoding="utf-8")
    for k in range(4):
        (project / "tests" / f"test_{k}.py").write_text(
            "import os\n"
            "def test_threads():\n"
            "    out = os.path.join(os.environ['OUT'], os.environ.get('PYTEST_XDIST_WORKER', 'serial') + '.txt')\n"
            "    open(out, 'w').write(os.environ['NUMBA_NUM_THREADS'])\n", encoding="utf-8")
    out = tmp_path / "out"
    out.mkdir()
    env = dict(os.environ, FINDALINE_TEST_LOCK_DIR=str(tmp_path / "locks"), FINDALINE_TEST_LOCK_POLL="0.05",
               OUT=str(out))
    env.pop("PYTEST_ADDOPTS", None)
    command = [sys.executable, TOOL, "run", "--expect", "60", "--", sys.executable, "-m", "pytest", "-q",
               "-p", "no:cacheprovider"]
    result = subprocess.run(command, cwd=project, env=env, capture_output=True, text=True, encoding="utf-8",
                            timeout=300)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "test lock: the full pytest runs in parallel: 4 workers x 3 threads" in result.stderr
    assert sorted(os.listdir(out)) == [f"gw{k}.txt" for k in range(4)]
    assert {(out / name).read_text() for name in os.listdir(out)} == {str(tl.WORKER_THREADS)}
    db = sqlite3.connect(str(tmp_path / "locks" / "queue.sqlite"))
    key, kind = db.execute("SELECT key, kind FROM history").fetchone()
    db.close()
    assert "pytest -n 4 --dist loadfile -q" in key and kind == tl.PARALLEL_KIND
    for name in os.listdir(out):
        os.remove(out / name)
    result = subprocess.run([*command, "-n", "0"], cwd=project, env=env, capture_output=True, text=True,
                            encoding="utf-8", timeout=300)
    assert result.returncode == 0 and "in parallel" not in result.stderr, result.stderr
    assert os.listdir(out) == ["serial.txt"]
