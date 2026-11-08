"""tools/test_lock.py: the shared test lock of parallel sessions and agents (its own queue in tmp_path)."""

import os
import re
import sqlite3
import subprocess
import sys
import time
from datetime import datetime

import psutil
import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "tools"))

import test_lock as tl  # noqa: E402

TOOL = os.path.join(REPO, "tools", "test_lock.py")
# A command that marks its start in <name>.started (whole, through a rename: its threads and its
# priority) and ends once <name>.go exists
CHILD = ("import os, sys, time, psutil\n"
         "folder, name = sys.argv[1], sys.argv[2]\n"
         "path = os.path.join(folder, name + '.started')\n"
         "priority = int(psutil.Process().nice())\n"
         "open(path + '.part', 'w').write(f\"{os.environ.get('NUMBA_NUM_THREADS', '-')} {priority}\")\n"
         "os.replace(path + '.part', path)\n"
         "deadline = time.time() + 120\n"
         "while not os.path.exists(os.path.join(folder, name + '.go')) and time.time() < deadline:\n"
         "    time.sleep(0.05)\n")


def entry(id, mode="shared", resources=(), started=True, at=1.0, expect=None, first=False):
    return tl.Entry(id, f"t{id}", mode, list(resources), "x", 1, "c", 0.0, at if started else None, expect, first)


def admitted(entries, now=10.0, slots=3, slack=0.0, passing=None, state="free"):
    return tl.startable(entries, now, lambda e: e.expect, slots, passing, slack, state=state)


def priorities():
    """The priorities (psutil's nice()) of a shared and an exclusive command started by this process."""
    if os.name == "nt":
        return int(subprocess.BELOW_NORMAL_PRIORITY_CLASS), int(subprocess.NORMAL_PRIORITY_CLASS)
    own = os.nice(0)
    return min(19, own + tl.NICE), own


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
    # The estimate to pass may differ from the one of the running ones (Queue: its kind's longest run)
    assert admitted([running, exclusive, entry(3, started=False, expect=50.0)], passing=lambda e: 2 * e.expect) == set()


def test_backfill_slack():
    """With a slack, a later entry may end that long after the reservation of a waiting one; the
    reservation counts the running ones that came before it only, so passing never adds up."""
    running = entry(1, at=0.0, expect=100.0)             # expected to end at 100
    exclusive = entry(2, "exclusive", started=False)     # so it may start at 100, at 220 with the slack
    assert admitted([running, exclusive, entry(3, started=False, expect=95.0)], slack=120) == {3}
    assert admitted([running, exclusive, entry(3, started=False, expect=210.0)], slack=120) == {3}   # ends at 220
    assert admitted([running, exclusive, entry(3, started=False, expect=211.0)], slack=120) == set()
    # One that passed it (expected to end at 210) does not move the reservation ...
    passer = entry(3, at=10.0, expect=200.0)
    assert admitted([running, exclusive, passer, entry(4, started=False, expect=205.0)], now=15.0, slack=120) == {4}
    assert admitted([running, exclusive, passer, entry(4, started=False, expect=206.0)], now=15.0, slack=120) == set()
    # ... and once only those that passed it hold it up, a later one has to end before them
    assert admitted([exclusive, passer, entry(4, started=False, expect=195.0)], now=15.0, slack=120) == {4}
    assert admitted([exclusive, passer, entry(4, started=False, expect=196.0)], now=15.0, slack=120) == set()
    # A running one without an estimate, or past it, leaves the slack
    for before in (entry(1, at=0.0), entry(1, at=0.0, expect=5.0)):
        assert admitted([before, exclusive, entry(3, started=False, expect=120.0)], slack=120) == {3}
        assert admitted([before, exclusive, entry(3, started=False, expect=121.0)], slack=120) == set()
    # A later exclusive one still needs nothing running beside it
    assert admitted([running, exclusive, entry(3, "exclusive", started=False, expect=1.0)], slack=120) == set()


def test_first():
    """--first ones wait ahead of the others (in their order), never ahead of a running one."""
    assert admitted([entry(1), entry(2, started=False), entry(3, started=False, first=True)], slots=2) == {3}
    assert admitted([entry(1), entry(2, started=False, first=True), entry(3, started=False, first=True)],
                    slots=2) == {2}
    assert admitted([entry(1, "exclusive"), entry(2, started=False, first=True)]) == set()
    # Ahead of a waiting exclusive one; a first exclusive one keeps out the shared ones that came before it
    assert admitted([entry(1), entry(2, "exclusive", started=False), entry(3, started=False, first=True)]) == {3}
    assert admitted([entry(1), entry(2, started=False), entry(3, "exclusive", started=False, first=True)]) == set()
    # One before a waiting one in the order did not pass it: the slack counts from its end
    first = entry(3, at=5.0, expect=200.0, first=True)   # started after the exclusive one came, ends at 205
    exclusive = entry(2, "exclusive", started=False)
    assert admitted([first, exclusive, entry(4, started=False, expect=315.0)], slack=120) == {4}   # ends at 325
    assert admitted([first, exclusive, entry(4, started=False, expect=316.0)], slack=120) == set()
    # Nor did one later in the order that started before it came
    early = entry(1, at=0.0, expect=100.0)
    late = entry(2, "exclusive", started=False, first=True)
    late.queued = 5.0
    assert admitted([early, late, entry(3, started=False, expect=210.0)], slack=120) == {3}   # ends at 220
    assert admitted([early, late, entry(3, started=False, expect=211.0)], slack=120) == set()


def test_the_users_state_in_the_queue():
    """busy (and heavy-ok, before --heavy exists) holds a waiting exclusive one, which then holds
    nobody up and has no reservation; quiet holds every waiting one; running ones go on;
    --first keeps its meaning among the admissible ones."""
    running = entry(1, at=0.0, expect=100.0)
    exclusive = entry(2, "exclusive", started=False)
    assert admitted([running, exclusive, entry(3, started=False)]) == set()                # free: as before
    for state in ("busy", "heavy-ok"):
        assert tl.held(exclusive, state) == "busy" and tl.held(entry(3, started=False), state) is None
        assert admitted([exclusive], state=state) == set()                                 # nothing running
        assert admitted([entry(3, "exclusive", started=False, expect=1.0)], state=state) == set()
        # Shared ones behind it start as if it were not there: no estimate needed, its slots taken
        assert admitted([running, exclusive, entry(3, started=False)], state=state) == {3}
        assert admitted([running, exclusive, entry(3, started=False, expect=1e6)], state=state) == {3}
        assert admitted([running, exclusive, entry(3, started=False), entry(4, started=False)], state=state) == {3, 4}
        # Resources between shared ones as before; a running exclusive still keeps everything out
        data = entry(1, resources=["data"], at=0.0)
        assert admitted([data, exclusive, entry(3, resources=["data"], started=False)], state=state) == set()
        assert admitted([entry(1, "exclusive"), entry(3, started=False)], state=state) == set()
        # What a waiting one waits for: never a held one
        waiting = entry(3, started=False)
        assert [e.id for e in tl.blockers(waiting, [running, exclusive, waiting], state)] == [1]
    assert [e.id for e in tl.blockers(waiting, [running, exclusive, waiting])] == [1, 2]
    # quiet: nobody starts, whatever the slots
    assert tl.held(entry(3, started=False), "quiet") == tl.held(exclusive, "quiet") == "quiet"
    assert admitted([entry(3, started=False)], state="quiet") == set()
    assert admitted([running, entry(3, started=False, expect=1.0)], state="quiet") == set()
    assert tl.held(entry(3, started=False), "free") is None and tl.held(exclusive, "free") is None
    # --first among the admissible ones: a held --first exclusive leaves the order to the others
    first = entry(2, "exclusive", started=False, first=True)
    queue = [entry(1), first, entry(3, started=False), entry(4, started=False, first=True)]
    assert admitted(queue, slots=2, state="busy") == {4}
    assert admitted(queue, slots=2) == set()


def test_user_state(tmp_path):
    """The row of the table `state` resolved at each look: `after` (free) once `until` passed."""
    queue = tl.Queue(str(tmp_path))
    assert queue.user_state(100.0) == tl.UserState("free", None)
    queue.set_state("busy", until=200.0, note="call", now=100.0)
    assert queue.user_state(150.0) == tl.UserState("busy", 100.0, 200.0, "free", "call")
    assert queue.user_state(200.0) == tl.UserState("free", 200.0)
    queue.set_state("free", until=300.0, after="busy", now=250.0)
    assert queue.user_state(299.0).value == "free" and queue.user_state(300.0) == tl.UserState("busy", 300.0)
    queue.set_state("quiet", now=400.0)
    assert queue.user_state(1e9) == tl.UserState("quiet", 400.0)
    for bad in (dict(value="nap"), dict(value="busy", until=500.0, after="nap"), dict(value="busy", after="free"),
                dict(value="busy", until=450.0), dict(value="busy", until=460.0 + 400 * 86400)):
        with pytest.raises(ValueError):
            queue.set_state(**bad, now=450.0)
    assert queue.user_state(450.0) == tl.UserState("quiet", 400.0)
    queue.db.close()


def test_describe_and_parse_until():
    now = datetime(2026, 11, 8, 15, 0).timestamp()

    def at(hour, minute, day=8):
        return datetime(2026, 11, day, hour, minute).timestamp()

    assert tl.describe_state(tl.UserState("free", None), now) == "free"
    assert tl.describe_state(tl.UserState("busy", at(14, 2), at(18, 0), "free"), now) == \
        "busy since 14:02, until 18:00, then free"
    assert tl.describe_state(tl.UserState("free", at(22, 0, 7), at(7, 0, 9), "busy", "night"), now) == \
        "free since yesterday 22:00, until tomorrow 07:00, then busy; note: night"
    assert tl.describe_state(tl.UserState("quiet", at(9, 0, 1)), now) == "quiet since 2026-11-01 09:00"
    assert tl.parse_until("18:00", now) == at(18, 0)
    assert tl.parse_until("07:00", now) == at(7, 0, 9)                    # past today: tomorrow
    assert tl.parse_until("15:00", now) == at(15, 0, 9)
    assert tl.parse_until("2026-11-10 06:30", now) == at(6, 30, 10)
    assert tl.parse_until("+2h", now) == now + 7200 and tl.parse_until("+90m", now) == now + 5400
    assert tl.parse_until("+1h30m", now) == tl.parse_until("+1.5h", now) == now + 5400
    for bad in ("2026-11-01 10:00", "tomorrow", "+", "+2", "25:00", "18.00", ""):
        with pytest.raises(ValueError):
            tl.parse_until(bad, now)


def test_state_command(tmp_path):
    """`state` prints or sets the user's state; `status` names it first."""
    env = dict(os.environ, FINDALINE_TEST_LOCK_DIR=str(tmp_path))

    def tool(*args):
        return subprocess.run([sys.executable, TOOL, *args], env=env, capture_output=True, text=True,
                              encoding="utf-8", timeout=60)

    assert tool("state").stdout.strip() == "User: free"
    result = tool("state", "busy", "--until", "+2h", "--note", "video call")
    assert result.returncode == 0, result.stderr
    assert re.fullmatch(r"User: busy since \d\d:\d\d, until (tomorrow )?\d\d:\d\d, then free; note: video call",
                        result.stdout.strip()), result.stdout
    assert tool("state").stdout == result.stdout
    assert tool("status").stdout.splitlines()[0] == result.stdout.strip()
    for bad in (("state", "nap"), ("state", "busy", "--after", "free"), ("state", "--until", "+1h"),
                ("state", "busy", "--until", "soon"), ("state", "busy", "--until", "2020-01-01 10:00")):
        assert tool(*bad).returncode == 2, bad
    assert tool("state", "free", "--until", "07:00", "--after", "quiet").stdout.startswith("User: free since ")
    queue = tl.Queue(str(tmp_path))
    state = queue.user_state()
    assert (state.value, state.after) == ("free", "quiet") and state.until > time.time()
    queue.db.close()


def test_old_queue_gets_new_columns(tmp_path):
    """A queue made by an older wrapper gets the columns and tables of the newer one."""
    db = sqlite3.connect(str(tmp_path / "queue.sqlite"))
    db.execute("CREATE TABLE entries (id INTEGER PRIMARY KEY AUTOINCREMENT, token TEXT NOT NULL, mode TEXT NOT NULL, "
               "resources TEXT NOT NULL, owner TEXT NOT NULL, pid INTEGER NOT NULL, command TEXT NOT NULL, "
               "queued REAL NOT NULL, started REAL)")
    db.close()
    queue = tl.Queue(str(tmp_path))
    columns = [row[1] for row in queue.db.execute("PRAGMA table_info(entries)")]
    assert columns[-3:] == ["expect", "first", "stop"]
    assert queue.user_state().value == "free"
    queue.db.close()


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
    # uv's own options before the program it runs
    assert tl.command_kind(["uv", "run", "--frozen", "pytest", "-q", "-p", "no:cacheprovider"]) == "pytest-all"
    assert tl.command_kind(["uv", "run", "--frozen", "--project", ".claude/worktrees/x", "pytest", "tests/a.py"]) \
        == "pytest"
    assert tl.command_kind(["uv", "run", "--frozen", "python", "tests/regression.py", "--all"]) == "regression.py"
    assert tl.command_kind(["uv", "run", "--frozen", "tools/check_source.py", "nz", "--lat", "1"]) == "check_source.py"
    assert tl.command_kind(["uv", "--project", "x", "run", "-p", "3.12", "-m", "pytest"]) == "pytest-all"
    assert tl.command_kind(["uv", "run", "--frozen", "python", "-c", "print(1)"]) is None
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
    entry = tl.Entry(1, "t", "shared", [], "x", 1, "pytest tests/test_new.py", 0.0, None)
    assert queue.estimate(entry, passing=True) == 100.0        # to pass: the longest of its kind's
    entry.command = "pytest"
    assert queue.estimate(entry, passing=True) == 30           # the same command's as before
    queue.record(["python", "-c", "pass"], 1.0, 0)
    assert estimate(["python", "-c", "pass"]) == 1.0 and estimate(["python", "-c", "other"]) is None


def test_kinds_of_older_runs_migrated(tmp_path):
    """A queue of before version 1 gets the kinds of uv's commands, which had none."""
    queue = tl.Queue(str(tmp_path))
    for key, kind in (("uv run --frozen pytest -q", None), ("python -c pass", None), ("pytest tests/a.py", "pytest")):
        queue.db.execute("INSERT INTO history (key, kind, seconds, code, ended) VALUES (?, ?, 1, 0, 0)", (key, kind))
    queue.db.execute("PRAGMA user_version = 0")
    queue.db.close()
    queue = tl.Queue(str(tmp_path))
    kinds = queue.db.execute("SELECT kind FROM history ORDER BY id").fetchall()
    assert kinds == [("pytest-all",), (None,), ("pytest",)]
    assert queue.db.execute("PRAGMA user_version").fetchone()[0] == tl.QUEUE_VERSION
    queue.db.close()


def test_wrappers_set_up_a_new_queue_together(tmp_path):
    """Opened at the same moment by several wrappers, a new queue is set up by one at a time
    (without it SQLite answered "database is locked" at once, in about half of such starts)."""
    opener = ("import sys, time\n"
              "sys.path.insert(0, sys.argv[1]); import test_lock as tl\n"
              "time.sleep(max(0, float(sys.argv[3]) - time.time()))\n"
              "tl.Queue(sys.argv[2]).add('t', 'shared', [], 'x', 'c')\n")
    for round in range(5):
        folder = tmp_path / str(round)
        folder.mkdir()
        at = time.time() + 1.0
        processes = [subprocess.Popen([sys.executable, "-c", opener, os.path.join(REPO, "tools"), str(folder), str(at)],
                                      stderr=subprocess.PIPE, text=True) for _ in range(4)]
        errors = [p.stderr.read().strip() for p in processes if p.wait(timeout=60) != 0]
        assert not errors, errors[0]


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
            assert time.time() < deadline, f"timed out; the wrappers wrote:\n{self.stderr()}"
            time.sleep(0.05)

    def stderr(self):
        """What the wrappers wrote, once they are killed (their commands go on until stop)."""
        texts = []
        for process in self.processes:
            process.kill()
            texts.append(f"[{process.args[4]}] exit {process.wait()}: {process.stderr.read().strip()}")
        return "\n".join(texts)

    def queued(self, mode):
        deadline = time.time() + 10
        while True:
            db = sqlite3.connect(os.path.join(self.env["FINDALINE_TEST_LOCK_DIR"], "queue.sqlite"))
            try:
                return db.execute("SELECT count(*) FROM entries WHERE mode = ?", (mode,)).fetchone()[0]
            except sqlite3.OperationalError:  # a disk I/O error on Windows just after a wrapper was killed
                if time.time() > deadline:
                    raise
                time.sleep(0.1)
            finally:
                db.close()

    def queue(self):
        """The wrappers' queue (close its db)."""
        folder = self.env["FINDALINE_TEST_LOCK_DIR"]
        os.makedirs(folder, exist_ok=True)
        return tl.Queue(folder)

    def set_state(self, value, **options):
        queue = self.queue()
        try:
            queue.set_state(value, **options)
        finally:
            queue.db.close()

    def ids(self):
        """The live entries' ids by owner."""
        queue = self.queue()
        try:
            return dict(queue.db.execute("SELECT owner, id FROM entries").fetchall())
        finally:
            queue.db.close()

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
    """Two shared run together with capped threads below the normal priority; an exclusive waits
    for them, and a shared one that comes after it waits for the exclusive although a slot is free."""
    shared, exclusive = priorities()
    a, b = runs.start("a"), runs.start("b")
    runs.wait_for(lambda: runs.started("a") and runs.started("b"))
    assert open(os.path.join(runs.folder, "a.started")).read() == f"{max(1, os.cpu_count() // 3)} {shared}"
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
    assert open(os.path.join(runs.folder, "e.started")).read() == f"- {exclusive}"  # all threads
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


def test_first_ahead_of_a_waiting_exclusive(runs):
    """A --first one starts beside the running shared one while an exclusive one waits; another
    shared one waits for the exclusive one."""
    a = runs.start("a")
    runs.wait_for(lambda: runs.started("a"))
    e = runs.start("e", "--exclusive")
    runs.wait_for(lambda: runs.queued("exclusive") == 1)
    d = runs.start("d")
    runs.wait_for(lambda: runs.queued("shared") == 2)
    c = runs.start("c", "--first")
    runs.wait_for(lambda: runs.started("c"))
    status = subprocess.run([sys.executable, TOOL, "status"], env=runs.env, capture_output=True, text=True)
    assert " shared first running" in status.stdout
    time.sleep(0.5)
    assert not runs.started("e") and not runs.started("d")
    for name in "ac":
        runs.go(name)
    runs.wait_for(lambda: runs.started("e"))
    assert not runs.started("d")
    runs.go("e")
    runs.wait_for(lambda: runs.started("d"))
    runs.go("d")
    assert a.wait(timeout=60) == c.wait(timeout=60) == e.wait(timeout=60) == d.wait(timeout=60) == 0


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


def test_busy_holds_an_exclusive_not_the_shared(runs):
    """While the user is busy an exclusive one waits, saying so, without that time counting toward
    its --wait, and a shared one that came after it starts; once free, the exclusive one waits for
    the shared one, and that time counts."""
    runs.set_state("busy", note="call")
    e = runs.start("e", "--exclusive", "--wait", "1")
    runs.wait_for(lambda: runs.queued("exclusive") == 1)
    c = runs.start("c")
    runs.wait_for(lambda: runs.started("c"))
    time.sleep(2.5)
    assert e.poll() is None and not runs.started("e")             # held for longer than its --wait
    runs.set_state("free")
    assert e.wait(timeout=60) == 75
    stderr = e.stderr.read()
    assert "test lock: exclusive waits: the PC is in use (busy since " in stderr and "; note: call)" in stderr
    assert "test lock: exclusive waits for\n" in stderr and "held by the user's state" in stderr
    assert not runs.started("e")
    runs.go("c")
    assert c.wait(timeout=60) == 0


def test_quiet_holds_every_one_until_its_time(runs):
    """Quiet holds a new shared one (not one running) until its time has passed: then the queue
    is free again without anybody setting it."""
    a = runs.start("a")
    runs.wait_for(lambda: runs.started("a"))
    runs.set_state("quiet", until=time.time() + 8)
    b = runs.start("b", "--wait", "0.5")
    runs.wait_for(lambda: runs.queued("shared") == 2)
    status = subprocess.run([sys.executable, TOOL, "status"], env=runs.env, capture_output=True, text=True)
    assert status.stdout.startswith("User: quiet since ") and ", then free\n" in status.stdout
    assert " (held: the user asked for quiet) owner=b" in status.stdout
    time.sleep(1.0)
    assert not runs.started("b") and b.poll() is None
    runs.go("a")
    assert a.wait(timeout=60) == 0                                 # a running one ends as usual
    runs.wait_for(lambda: runs.started("b"))
    runs.go("b")
    assert b.wait(timeout=60) == 0
    assert "test lock: shared waits: the user asked for quiet (quiet since " in b.stderr.read()


def test_stop_from_the_page(runs):
    """A stop asked for a running entry kills its command's process tree (125, said on stderr) and
    leaves the estimates alone; one still waiting, or gone, cannot be stopped."""
    a = runs.start("a", "--exclusive")
    runs.wait_for(lambda: runs.started("a"))
    b = runs.start("b")
    runs.wait_for(lambda: runs.queued("shared") == 1)
    ids = runs.ids()
    queue = runs.queue()
    try:
        assert not queue.request_stop(ids["b"]) and not queue.request_stop(999)
        assert queue.request_stop(ids["a"])
        assert a.wait(timeout=60) == tl.STOPPED == 125
        assert "test lock: stopped by the user from the test lock page" in a.stderr.read()
        left = []
        for process in psutil.process_iter(["cmdline"]):
            command = process.info["cmdline"] or []
            if runs.folder in command and command[-1] == "a":
                left.append(command)
        assert not left                                            # the command's whole tree
        runs.wait_for(lambda: runs.started("b"))
        runs.go("b")
        assert b.wait(timeout=60) == 0
        assert queue.db.execute("SELECT code FROM history").fetchall() == [(0,)]   # b's only
    finally:
        queue.db.close()
