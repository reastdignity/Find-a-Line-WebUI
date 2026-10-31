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


def entry(id, mode="shared", resources=(), started=True):
    return tl.Entry(id, f"t{id}", mode, list(resources), "x", 1, "c", 0.0, 1.0 if started else None)


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
