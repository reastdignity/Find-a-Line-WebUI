"""tools/test_lock.py: the shared test lock of parallel sessions and agents (its own queue in tmp_path)."""

import os
import sqlite3
import subprocess
import sys
import time

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "tools"))

import test_lock as tl  # noqa: E402

TOOL = os.path.join(REPO, "tools", "test_lock.py")
# A command that marks its start in <name>.started and ends once <name>.go exists
CHILD = ("import os, sys, time\n"
         "folder, name = sys.argv[1], sys.argv[2]\n"
         "open(os.path.join(folder, name + '.started'), 'w').write(os.environ.get('NUMBA_NUM_THREADS', '-'))\n"
         "deadline = time.time() + 120\n"
         "while not os.path.exists(os.path.join(folder, name + '.go')) and time.time() < deadline:\n"
         "    time.sleep(0.05)\n")


def entry(id, mode="shared", resources=(), started=True, at=1.0, expect=None):
    return tl.Entry(id, f"t{id}", mode, list(resources), "x", 1, "c", 0.0, at if started else None, expect)


def admitted(entries, now=10.0, slots=3):
    return tl.startable(entries, now, lambda e: e.expect, slots)


def test_who_may_start():
    """Shared ones up to the slots, exclusive alone, resources one at a time, first come first served."""
    new = entry(9, started=False)
    assert tl.may_start(new, [], slots=3)
    assert tl.may_start(new, [entry(1), entry(2)], slots=3)
    assert not tl.may_start(new, [entry(1), entry(2), entry(3)], slots=3)
    assert not tl.may_start(new, [entry(1), entry(2, started=False), entry(3, started=False)], slots=3)
    assert tl.may_start(new, [entry(1), entry(10, started=False), entry(11, started=False)], slots=3)
    assert not tl.may_start(new, [entry(1, "exclusive")])
    assert not tl.may_start(new, [entry(2, "exclusive", started=False)])        # a waiting exclusive goes first
    assert tl.may_start(new, [entry(12, "exclusive", started=False)])           # but not one that came later
    exclusive = entry(9, "exclusive", started=False)
    assert not tl.may_start(exclusive, [entry(1)]) and tl.may_start(exclusive, [entry(10, started=False)])
    data = entry(9, resources=["data"], started=False)
    assert not tl.may_start(data, [entry(1, resources=["data", "docker"])])
    assert tl.may_start(data, [entry(1, resources=["docker"])])
    assert not tl.may_start(data, [entry(2, resources=["data"], started=False)])


def test_backfill():
    """A later entry passes a waiting one it conflicts with only when it is expected to end
    before the running ones holding that one up."""
    running = entry(1, at=0.0, expect=100.0)             # expected to end at 100
    exclusive = entry(2, "exclusive", started=False)     # so it may start at 100
    assert admitted([running, exclusive, entry(3, started=False, expect=50.0)]) == {3}   # ends at 60
    assert admitted([running, exclusive, entry(3, started=False, expect=90.0)]) == {3}   # ends at 100
    assert admitted([running, exclusive, entry(3, started=False, expect=95.0)]) == set()
    assert admitted([running, exclusive, entry(3, started=False)]) == set()              # no estimate
    unknown = entry(1, at=0.0)
    assert admitted([unknown, exclusive, entry(3, started=False, expect=1.0)]) == set()
    assert admitted([running, exclusive, entry(3, started=False, expect=1.0)], now=150.0) == set()  # overrun
    # The slots: taken by the running and the admitted, not by a waiting one that may not pass
    assert admitted([running, exclusive, *(entry(i, started=False, expect=10.0) for i in (3, 4, 5))]) == {3, 4}
    assert admitted([running, exclusive, entry(3, started=False), entry(4, started=False, expect=10.0)]) == {4}
    # Two exclusive ones waiting: the earlier reservation counts
    assert admitted([running, exclusive, entry(3, "exclusive", started=False, expect=5.0),
                     entry(4, started=False, expect=50.0)]) == {4}
    # Resources: one without them is not held up; one with them waits for the running one anyway
    data = entry(1, resources=["data"], at=0.0, expect=100.0)
    assert admitted([data, entry(2, resources=["data"], started=False), entry(3, started=False)]) == {3}
    assert admitted([data, entry(2, resources=["data"], started=False),
                     entry(3, resources=["data"], started=False, expect=1.0)]) == set()
    # A resource waiting behind an exclusive: one naming it passes only in time
    assert admitted([running, exclusive, entry(3, resources=["docker"], started=False, expect=50.0),
                     entry(4, resources=["docker"], started=False, expect=80.0)]) == {3}
    # Nothing running: the first waiting one starts, as before
    assert admitted([entry(1, "exclusive", started=False), entry(2, started=False, expect=1.0)]) == {1}


def test_command_kind_and_key():
    assert tl.command_kind(["pytest", "-q"]) == "pytest-all"
    assert tl.command_kind(["uv", "run", "pytest", "tests/test_web.py"]) == "pytest"
    assert tl.command_kind(["python", "-m", "pytest", "-q", "-W", "default::DeprecationWarning", "-p",
                            "no:cacheprovider", "--deselect", "tests/test_test_lock.py::test_x"]) == "pytest-all"
    assert tl.command_kind(["python", "-m", "pytest", "-q", "--deselect=tests/test_x.py", "-rs"]) == "pytest-all"
    assert tl.command_kind(["python", "-m", "pytest", "-q", "-k", "grouping"]) == "pytest"
    assert tl.command_kind(["python", "-m", "pytest", "-kgrouping"]) == "pytest"
    assert tl.command_kind(["python", "-m", "pytest", "-m", "slow"]) == "pytest"
    assert tl.command_kind(["python", "-m", "pytest", "tests/test_units.py::test_a"]) == "pytest"
    assert tl.command_kind([r"C:\x\.venv\Scripts\python.exe", "-I", "tests/regression.py", "--only", "R1"]) \
        == "regression.py"
    assert tl.command_kind(["uv", "run", "python", "-m", "pytest"]) == "pytest-all"
    assert tl.command_kind(["python", "tools/perf_profile.py", "--cores", "4"]) == "perf_profile.py"
    assert tl.command_kind(["npm", "run", "build"]) == "npm"
    assert tl.command_kind(["python", "-c", "print(1)"]) is None
    assert tl.command_key([r"C:\x\.venv\Scripts\python.exe", "tests/regression.py"]) == "python tests/regression.py"


def test_estimates_from_history(tmp_path):
    queue = tl.Queue(str(tmp_path))

    def estimate(command, expect=None):
        return queue.estimate(tl.Entry(1, "t", "shared", [], "x", 1, tl.shlex.join(command), 0.0, None, expect))

    assert estimate(["pytest"]) is None
    for seconds in (100, 30, 20, 10, 10, 10):                  # the longest of the last five
        queue.record(["pytest"], seconds, 0)
    assert estimate(["pytest"]) == 30
    assert estimate(["pytest"], expect=7.0) == 7.0
    for seconds in range(1, 11):                               # another pytest: its kind's 90th percentile
        queue.record(["pytest", f"tests/test_{seconds}.py"], seconds * 10.0, 0)
    assert estimate(["pytest", "tests/test_new.py"]) == 90.0
    queue.record(["python", "-c", "pass"], 1.0, 0)
    assert estimate(["python", "-c", "pass"]) == 1.0 and estimate(["python", "-c", "other"]) is None


class Runs:
    """Wrappers started with their own queue; each runs CHILD under a name."""

    def __init__(self, folder):
        self.folder = str(folder)
        self.env = dict(os.environ, FINDALINE_TEST_LOCK_DIR=os.path.join(self.folder, "locks"),
                        FINDALINE_TEST_LOCK_POLL="0.05", FINDALINE_TEST_SLOTS="3")
        self.env.pop("NUMBA_NUM_THREADS", None)
        self.processes = []

    def start(self, name, *options, command=None):
        command = command or [sys.executable, "-c", CHILD, self.folder, name]
        process = subprocess.Popen([sys.executable, TOOL, "run", "--owner", name, *options, "--", *command],
                                   env=self.env, stderr=subprocess.PIPE, text=True)
        self.processes.append(process)
        return process

    def started(self, name):
        return os.path.exists(os.path.join(self.folder, name + ".started"))

    def go(self, name):
        open(os.path.join(self.folder, name + ".go"), "w").close()

    def wait_for(self, check, seconds=60):
        deadline = time.time() + seconds
        while not check():
            assert time.time() < deadline, "timed out"
            time.sleep(0.05)

    def queued(self, mode):
        db = sqlite3.connect(os.path.join(self.env["FINDALINE_TEST_LOCK_DIR"], "queue.sqlite"))
        try:
            return db.execute("SELECT count(*) FROM entries WHERE mode = ?", (mode,)).fetchone()[0]
        finally:
            db.close()

    def stop(self):
        for name in "abcdefgh":
            self.go(name)
        for process in self.processes:
            try:
                process.wait(timeout=60)
            except subprocess.TimeoutExpired:
                process.kill()


@pytest.fixture
def runs(tmp_path):
    runs = Runs(tmp_path)
    yield runs
    runs.stop()


def test_shared_together_exclusive_alone(runs):
    """Two shared run together with capped threads; an exclusive waits for them, and a shared one
    that comes after it waits for the exclusive although a slot is free."""
    a, b = runs.start("a"), runs.start("b")
    runs.wait_for(lambda: runs.started("a") and runs.started("b"))
    threads = open(os.path.join(runs.folder, "a.started")).read()
    assert threads == str(max(1, os.cpu_count() // 3))
    e = runs.start("e", "--exclusive")
    runs.wait_for(lambda: runs.queued("exclusive") == 1)
    c = runs.start("c")
    runs.wait_for(lambda: runs.queued("shared") == 3)
    time.sleep(0.5)
    assert not runs.started("e") and not runs.started("c")
    runs.go("a")
    assert a.wait(timeout=60) == 0
    time.sleep(0.5)
    assert not runs.started("e")                                   # b still runs
    runs.go("b")
    runs.wait_for(lambda: runs.started("e"))
    assert b.wait(timeout=60) == 0
    assert open(os.path.join(runs.folder, "e.started")).read() == "-"  # all threads
    time.sleep(0.5)
    assert not runs.started("c")
    runs.go("e")
    runs.wait_for(lambda: runs.started("c"))
    assert e.wait(timeout=60) == 0
    runs.go("c")
    assert c.wait(timeout=60) == 0
    assert runs.queued("shared") == runs.queued("exclusive") == 0


def test_backfill_while_an_exclusive_waits(runs):
    """A shared one expected to end in time starts while an exclusive waits for a running one; one
    that would not, waits; a finished command's time goes into the history."""
    a = runs.start("a", "--expect", "600")
    runs.wait_for(lambda: runs.started("a"))
    e = runs.start("e", "--exclusive")
    runs.wait_for(lambda: runs.queued("exclusive") == 1)
    late = runs.start("b", "--expect", "3600")
    c = runs.start("c", "--expect", "1")
    runs.wait_for(lambda: runs.started("c"))
    runs.go("c")
    assert c.wait(timeout=60) == 0 and "starts ahead of" in c.stderr.read()
    time.sleep(0.5)
    assert not runs.started("e") and not runs.started("b")
    runs.go("a")
    runs.wait_for(lambda: runs.started("e"))
    runs.go("e")
    runs.wait_for(lambda: runs.started("b"))
    runs.go("b")
    assert a.wait(timeout=60) == e.wait(timeout=60) == late.wait(timeout=60) == 0
    db = sqlite3.connect(os.path.join(runs.env["FINDALINE_TEST_LOCK_DIR"], "queue.sqlite"))
    try:
        assert db.execute("SELECT count(*) FROM history WHERE code = 0").fetchone()[0] == 4
    finally:
        db.close()


def test_resources_one_at_a_time(runs):
    a = runs.start("a", "--resource", "data")
    runs.wait_for(lambda: runs.started("a"))
    b, c = runs.start("b", "--resource", "data"), runs.start("c", "--resource", "docker")
    runs.wait_for(lambda: runs.started("c"))
    time.sleep(0.5)
    assert not runs.started("b")
    runs.go("a")
    runs.wait_for(lambda: runs.started("b"))
    for name, process in (("b", b), ("c", c)):
        runs.go(name)
        assert process.wait(timeout=60) == 0
    assert a.wait(timeout=60) == 0


def test_a_killed_wrapper_leaves_no_entry(runs):
    """The entry of a wrapper killed without cleaning up is dropped by the next one that looks."""
    a = runs.start("a", "--exclusive")
    runs.wait_for(lambda: runs.started("a"))
    a.kill()  # the wrapper only: its command goes on (and ends with the fixture)
    a.wait(timeout=60)
    assert runs.queued("exclusive") == 1
    b = runs.start("b", "--exclusive")
    runs.wait_for(lambda: runs.started("b"))
    runs.go("b")
    assert b.wait(timeout=60) == 0
    status = subprocess.run([sys.executable, TOOL, "status"], env=runs.env, capture_output=True, text=True)
    assert "(empty)" in status.stdout


def test_timeout_and_giving_up(runs):
    """--timeout kills the command's process tree (124); --wait gives up while another runs (75)."""
    a = runs.start("a", "--exclusive", "--timeout", "1")
    runs.wait_for(lambda: runs.started("a"))
    assert a.wait(timeout=60) == 124
    b = runs.start("b", "--exclusive")
    runs.wait_for(lambda: runs.started("b"))
    c = runs.start("c", "--wait", "0.5")
    assert c.wait(timeout=60) == 75 and "waits for" in c.stderr.read()
    assert not runs.started("c")
    runs.go("b")
    assert b.wait(timeout=60) == 0
