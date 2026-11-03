"""
Run by hand (or by agents): a command under the shared test lock of all checkouts of the repository.

Parallel sessions and agents (each in its own worktree) share the cores, the memory and a few
other things. A command waits in one first-come-first-served queue until it may start:

- shared (the default): pytest, builds, regression runs compared by checksums only. At most
  SLOTS at once, below the normal priority (their processes inherit it, so the desktop and an
  exclusive command come first), each with the threads of numba, OpenMP, BLAS and GDAL capped
  to cores / THREAD_SHARE whatever the slots (the results do not depend on them:
  tests/test_units.py::test_kernels_independent_of_threads; most shared commands keep about one
  core busy, so the slots are more than cores / threads).
- --exclusive: nothing else runs, all cores, normal priority: measured times or memory
  (tools/perf_*.py, the times of tests/regression.py), comparisons of tiled areas without a
  fixed --tile-size (the tiles follow the free memory), large searches, the CI replay in
  Docker Desktop.
- --resource NAME (repeatable): also one at a time with every other command naming it, e.g.
  `data` (the real data folder: cache update, osm update, migrations), `docker`, `opentopo`
  (the demo key's 50 calls a day).
- --first: waits ahead of every waiting command (never of a running one; several of them in
  their order). Only with the user's permission.

A command waits for a running one it conflicts with (either exclusive, or a resource in common)
and for every earlier waiting one it conflicts with, so a waiting --exclusive keeps new shared
commands out, and shared commands take the free slots in their order. One exception (backfill):
a waiting command held up by running ones has a reservation, the time the last of the running
ones that did not pass it is expected to end; a later command may pass it when it is expected
to end at most SLACK after that, so the slots left free meanwhile are used and the one passed
starts at most SLACK later. Those that passed it never move its reservation (once only they
hold it up, a later one has to end before they do). A command's expected time is --expect, or
the longest of the last runs of the same command, or the 90th percentile of the last runs of
its kind (pytest of chosen tests, pytest-all, regression.py, perf_profile.py, ...), from the
table `history`; to pass, the longest of its kind's last runs (one too short delays the one
passed). Without one it passes nobody, and a running command without one, or past it, leaves
only SLACK to pass in. An estimate can be wrong: the command passed is then late by the overrun.
The queue is a SQLite database in the git common directory (<.git>/findaline-locks/, the same
for every worktree, never in `git status`); every entry holds an OS lock (filelock) for as long
as its wrapper lives, so the entry of a killed wrapper is dropped by the next one that looks.
Killing the wrapper itself leaves its command running: stop a hung command, not the wrapper.

    python tools/test_lock.py run [--exclusive] [--resource data] [--owner NAME] [--expect S] [--first] -- pytest
    python tools/test_lock.py status

Runs with the standard library and filelock (any Python of the repository's environment;
run it from the main checkout's path, a worktree of an older branch may not have it).
Exit codes: the command's, 75 gave up waiting (--wait), 124 killed after --timeout, 130 Ctrl-C.
"""

import argparse
import ntpath
import os
import secrets
import shlex
import signal
import sqlite3
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Dict, List, Optional, Sequence, Set

from filelock import FileLock, Timeout

SLOTS = int(os.environ.get("FINDALINE_TEST_SLOTS", "6"))
THREAD_SHARE = 3      # a shared command's threads: cores / THREAD_SHARE, as with the 3 slots before 2026-11-03
                      # (the lock monitor of 2026-11-01..03: a median of 0.8 cores busy per shared command)
NICE = 10             # the niceness of shared commands on POSIX (Windows: below normal)
SLACK = 120.0         # seconds a command passing a waiting one may end after that one's reservation
POLL = float(os.environ.get("FINDALINE_TEST_LOCK_POLL", "2"))  # seconds between looks at the queue
REPORT = 300                                                    # seconds between "still waiting" lines
TIMEOUT = {"shared": 3600, "exclusive": 3 * 3600}               # default --timeout per mode
WAIT = 4 * 3600                                                 # default --wait
SAME_RUNS = 5         # an estimate: the longest of the last runs of the same command,
KIND_RUNS = 10        # else the 90th percentile of the last runs of its kind (the longest to pass)
HISTORY_ROWS = 2000   # rows of `history` kept
WRAPPERS = ("uv", "uvx", "run", "-m", "-I", "-u", "-B")   # skipped to find the kind of a command
UV = ("uv", "uvx")    # after them, uv's own options are skipped too (uv run --frozen pytest)
UV_VALUES = ("--project", "--directory", "--with", "--with-editable", "--with-requirements", "--group",
             "--only-group", "--no-group", "--extra", "--no-extra", "--python", "-p", "--package",
             "--env-file", "--index", "--config-file", "--cache-dir")   # uv's options taking a value
QUEUE_VERSION = 1     # PRAGMA user_version of the queue: 1 = history's kinds with uv's options skipped
PYTEST_VALUES = ("-p", "-W", "-o", "-c", "-n", "-r", "--deselect", "--ignore", "--ignore-glob", "--rootdir",
                 "--tb", "--maxfail", "--basetemp", "--timeout", "--durations")  # options taking a value
THREAD_VARS = ("NUMBA_NUM_THREADS", "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
               "GDAL_NUM_THREADS")
TASKKILL = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "taskkill.exe")

SCHEMA = """CREATE TABLE IF NOT EXISTS entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT, token TEXT NOT NULL, mode TEXT NOT NULL,
    resources TEXT NOT NULL, owner TEXT NOT NULL, pid INTEGER NOT NULL, command TEXT NOT NULL,
    queued REAL NOT NULL, started REAL);
CREATE TABLE IF NOT EXISTS history (
    id INTEGER PRIMARY KEY AUTOINCREMENT, key TEXT NOT NULL, kind TEXT, seconds REAL NOT NULL,
    code INTEGER NOT NULL, ended REAL NOT NULL);
CREATE INDEX IF NOT EXISTS history_key ON history (key);
CREATE INDEX IF NOT EXISTS history_kind ON history (kind)"""


@dataclass
class Entry:
    id: int
    token: str
    mode: str                 # "shared" or "exclusive"
    resources: List[str]
    owner: str
    pid: int
    command: str
    queued: float
    started: Optional[float]        # None while waiting
    expect: Optional[float] = None  # seconds given by --expect
    first: bool = False             # --first: ahead of the waiting ones without it


def order(entry: Entry) -> tuple:
    """The order of the queue: --first ones, then the others, each in the order they came."""
    return (not entry.first, entry.id)


def conflicts(a: Entry, b: Entry) -> bool:
    """May the two never run at the same time."""
    return a.mode == "exclusive" or b.mode == "exclusive" or bool(set(a.resources) & set(b.resources))


def startable(entries: Sequence[Entry], now: float, estimate: Callable[[Entry], Optional[float]],
              slots: int = SLOTS, passing: Optional[Callable[[Entry], Optional[float]]] = None,
              slack: float = SLACK) -> Set[int]:
    """The ids of the waiting entries that may start now. The waiting ones are taken in their
    order, each one admitted counting as started: one may start with no running or admitted one
    it conflicts with and, if shared, a slot left by them; and with no earlier waiting one it
    conflicts with, unless it is expected (by `passing`, else `estimate`) to end in time for
    that one (backfill). In time: at most `slack` after the latest expected end of the running
    and admitted ones it conflicts with that did not pass it (their start plus their estimate,
    not before now, and now when unknown), and in any case before the latest of all it
    conflicts with; with only those that passed it, before the latter, so the ones passing it
    never push it back further. Passed it: later in the order and started after it came."""
    started = {e.id: e.started for e in entries if e.started is not None}
    by_id = {e.id: e for e in entries}
    seconds = {e.id: estimate(e) for e in entries}
    passing = passing or estimate

    def end(id: int) -> float:
        return now if seconds[id] is None else max(now, started[id] + seconds[id])

    held: Dict[int, float] = {}   # waiting ones not admitted → the end a later one passing them may not exceed
    for entry in sorted((e for e in entries if e.started is None), key=order):
        blocking = [i for i in started if conflicts(entry, by_id[i])]
        full = entry.mode == "shared" and sum(by_id[i].mode == "shared" for i in started) >= slots
        passed = [i for i in held if conflicts(entry, by_id[i])]
        own = passing(entry) if passed else None
        passes = all(own is not None and now + own <= held[i] for i in passed)
        if not blocking and not full and passes:
            started[entry.id] = now
        else:
            before = [end(i) for i in blocking if order(by_id[i]) < order(entry) or started[i] <= entry.queued]
            latest = max((end(i) for i in blocking), default=now)
            held[entry.id] = max(latest, max(before) + slack) if before else latest
    return {i for i in started if by_id[i].started is None}


def may_start(entry: Entry, others: Sequence[Entry], slots: int = SLOTS,
              estimate: Callable[[Entry], Optional[float]] = lambda e: None, now: Optional[float] = None) -> bool:
    """Whether a waiting entry may start now, given the other live entries (startable)."""
    return entry.id in startable([entry, *others], time.time() if now is None else now, estimate, slots)


def command_key(command: Sequence[str]) -> str:
    """The command as text, its program by name only (the same in every checkout)."""
    return shlex.join([_name(command[0]), *command[1:]]) if command else ""


def command_kind(command: Sequence[str]) -> Optional[str]:
    """pytest, pytest-all, regression.py, npm, ...: the program, or the script run by Python or uv;
    None for `python -c`. A pytest of the whole suite (no test named or selected) is pytest-all:
    it takes ten minutes where most chosen tests take seconds. uv's own options are skipped
    (`uv run --frozen --project X pytest`): an option of it taking a value not in UV_VALUES
    gives the kind of its value."""
    i, uv = 0, False  # uv: between uv and the program it runs, where its own options stand
    while i < len(command):
        word, name = command[i], _name(command[i])
        if name in UV:
            uv = True
        elif uv and word.startswith("-"):
            i += word in UV_VALUES  # its value too
        elif word in WRAPPERS or name.startswith("python"):
            uv = uv and word == "run"
        else:
            break
        i += 1
    if i == len(command) or command[i].startswith("-"):
        return None
    kind = _name(command[i])
    return "pytest-all" if kind == "pytest" and not _selects(command[i + 1:]) else kind


def _selects(args: Sequence[str]) -> bool:
    """Whether pytest's arguments name or select tests (paths, node ids, -k, -m), not only deselect."""
    value = False  # the next one is an option's value
    for arg in args:
        if value:
            value = False
        elif arg in ("-k", "-m") or (arg[:2] in ("-k", "-m") and not arg.startswith("--")):
            return True
        elif arg in PYTEST_VALUES:
            value = True
        elif not arg.startswith("-"):
            return True
    return False


def _name(path: str) -> str:
    name = ntpath.basename(path)  # after / or \: a Windows path names its program on Linux too
    return name[:-4] if name.lower().endswith(".exe") else name


def lock_dir() -> str:
    """<git common directory>/findaline-locks: one for the main checkout and all its worktrees."""
    folder = os.environ.get("FINDALINE_TEST_LOCK_DIR")
    if not folder:
        here = os.path.dirname(os.path.abspath(__file__))
        common = subprocess.run(["git", "rev-parse", "--git-common-dir"], cwd=here, capture_output=True,
                                text=True, check=True).stdout.strip()
        folder = os.path.join(os.path.abspath(os.path.join(here, common)), "findaline-locks")
    os.makedirs(folder, exist_ok=True)
    return folder


def _holder(folder: str, token: str) -> FileLock:
    # An OS lock only: a lock file left by a killed process must not count as held
    return FileLock(os.path.join(folder, f"holder.{token}.lock"), fallback_to_soft=False)


def _release(lock: FileLock) -> None:
    """Releases a holder's lock and removes its file (filelock keeps it on POSIX)."""
    lock.release()
    try:
        os.remove(lock.lock_file)
    except OSError:
        pass


class Queue:
    def __init__(self, folder: str):
        self.folder = folder
        self.db = sqlite3.connect(os.path.join(folder, "queue.sqlite"), timeout=60, isolation_level=None)
        # One at a time: wrappers setting up a new queue together get "database is locked" at once,
        # without the busy timeout (switching to WAL, creating the schema)
        with FileLock(os.path.join(folder, "setup.lock"), fallback_to_soft=False):
            self.db.execute("PRAGMA journal_mode=WAL")
            self.db.executescript(SCHEMA)
            columns = [row[1] for row in self.db.execute("PRAGMA table_info(entries)")]
            for column, kind in (("expect", "REAL"), ("first", "INTEGER")):
                if column not in columns:  # wrappers of older checkouts leave it NULL
                    self.db.execute(f"ALTER TABLE entries ADD COLUMN {column} {kind}")
            if self.db.execute("PRAGMA user_version").fetchone()[0] < QUEUE_VERSION:
                self._migrate()

    def _migrate(self) -> None:
        """Version 1: the kinds of the runs before it again, with uv's options skipped (they had none)."""
        self.db.execute("BEGIN IMMEDIATE")
        try:
            for id, key, kind in self.db.execute("SELECT id, key, kind FROM history").fetchall():
                try:
                    new = command_kind(shlex.split(key))
                except ValueError:
                    continue
                if new != kind:
                    self.db.execute("UPDATE history SET kind = ? WHERE id = ?", (new, id))
            self.db.execute(f"PRAGMA user_version = {QUEUE_VERSION}")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise
        self.db.execute("COMMIT")

    def _entries(self) -> List[Entry]:
        rows = self.db.execute("SELECT id, token, mode, resources, owner, pid, command, queued, started, expect, "
                               "first FROM entries ORDER BY id").fetchall()
        return [Entry(i, t, m, [r for r in res.split(",") if r], o, p, c, q, s, x, bool(f))
                for i, t, m, res, o, p, c, q, s, x, f in rows]

    def live(self, own: Optional[str] = None) -> List[Entry]:
        """The entries whose wrapper still holds its lock (the others are deleted); call it inside
        a write transaction. own: the token of the caller, whose lock is not tried."""
        alive = []
        for entry in self._entries():
            if entry.token == own:
                alive.append(entry)
                continue
            lock = _holder(self.folder, entry.token)
            try:
                lock.acquire(timeout=0)
            except Timeout:
                alive.append(entry)
                continue
            _release(lock)
            self.db.execute("DELETE FROM entries WHERE id = ?", (entry.id,))
        return alive

    def add(self, token: str, mode: str, resources: Sequence[str], owner: str, command: str,
            expect: Optional[float] = None, first: bool = False) -> int:
        cursor = self.db.execute("INSERT INTO entries (token, mode, resources, owner, pid, command, queued, expect, "
                                 "first) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                                 (token, mode, ",".join(sorted(set(resources))), owner, os.getpid(), command,
                                  time.time(), expect, int(first)))
        return cursor.lastrowid

    def estimate(self, entry: Entry, passing: bool = False) -> Optional[float]:
        """The seconds the entry's command is expected to take (see the module's docstring);
        passing: to pass a waiting one, from its kind the longest of the last runs."""
        if entry.expect is not None:
            return entry.expect
        try:
            command = shlex.split(entry.command)
        except ValueError:  # not written by shlex.join: no estimate
            return None
        same =self.db.execute("SELECT max(seconds) FROM (SELECT seconds FROM history WHERE key = ? "
                               "ORDER BY id DESC LIMIT ?)", (command_key(command), SAME_RUNS)).fetchone()[0]
        kind = command_kind(command)
        if same is not None or kind is None:
            return same
        runs = sorted(s for (s,) in self.db.execute("SELECT seconds FROM history WHERE kind = ? "
                                                     "ORDER BY id DESC LIMIT ?", (kind, KIND_RUNS)))
        if not runs:
            return None
        return runs[-1] if passing else runs[(9 * len(runs) + 9) // 10 - 1]   # the nearest rank

    def record(self, command: Sequence[str], seconds: float, code: int) -> None:
        """A finished command's time, for the estimates."""
        self.db.execute("INSERT INTO history (key, kind, seconds, code, ended) VALUES (?, ?, ?, ?, ?)",
                        (command_key(command), command_kind(command), seconds, code, time.time()))
        self.db.execute("DELETE FROM history WHERE id <= (SELECT max(id) FROM history) - ?", (HISTORY_ROWS,))

    def try_start(self, token: str) -> tuple:
        """(started, the entries it waits for or, once started, the earlier waiting ones it passed)."""
        self.db.execute("BEGIN IMMEDIATE")
        try:
            entries = self.live(own=token)
            entry = next(e for e in entries if e.token == token)
            others = [e for e in entries if e.token != token]
            now = time.time()
            if entry.id in startable(entries, now, self.estimate, passing=lambda e: self.estimate(e, passing=True)):
                self.db.execute("UPDATE entries SET started = ? WHERE id = ?", (now, entry.id))
                result = True, [e for e in others if e.started is None and order(e) < order(entry)
                                and conflicts(entry, e)]
            else:
                result = False, [e for e in others if (e.started is not None or order(e) < order(entry))
                                 and (conflicts(entry, e) or e.mode == entry.mode == "shared")]
        except BaseException:
            if self.db.in_transaction:
                self.db.execute("ROLLBACK")
            raise
        self.db.execute("COMMIT")
        return result

    def remove(self, token: str) -> None:
        self.db.execute("DELETE FROM entries WHERE token = ?", (token,))


def _describe(entry: Entry, now: float, expected: Optional[float] = None) -> str:
    state = (f"running {(now - entry.started) / 60:.0f} min" if entry.started is not None
             else f"waiting {(now - entry.queued) / 60:.0f} min")
    if expected is not None:
        state += f" (takes ~{expected / 60:.1f} min)"
    resources = f" +{','.join(entry.resources)}" if entry.resources else ""
    first = " first" if entry.first else ""
    return f"#{entry.id} {entry.mode}{resources}{first} {state} owner={entry.owner} pid={entry.pid}: {entry.command}"


def _environment(mode: str) -> dict:
    env = dict(os.environ, FINDALINE_TEST_LOCK=mode)
    if mode == "shared":
        threads = str(max(1, (os.cpu_count() or 1) // THREAD_SHARE))
        env.update({name: threads for name in THREAD_VARS})
    return env


def _priority(mode: str) -> dict:
    """Popen's arguments for the priority of the command: shared below the normal one, exclusive
    the normal one (its processes inherit it; on POSIX an exclusive one keeps the wrapper's)."""
    if os.name == "nt":
        return {"creationflags": subprocess.BELOW_NORMAL_PRIORITY_CLASS if mode == "shared"
                else subprocess.NORMAL_PRIORITY_CLASS}
    return {"preexec_fn": lambda: os.nice(NICE)} if mode == "shared" else {}


def _kill_tree(process: subprocess.Popen) -> None:
    if os.name == "nt":
        subprocess.call([TASKKILL, "/T", "/F", "/PID", str(process.pid)],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    process.wait()


def run(args) -> int:
    mode = "exclusive" if args.exclusive else "shared"
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    text = shlex.join(command)
    queue = Queue(lock_dir())
    token = secrets.token_hex(8)
    holder = _holder(queue.folder, token)
    holder.acquire(timeout=0)  # before the entry exists, so nobody takes it for a dead one
    process = None
    try:
        queue.add(token, mode, args.resource, args.owner, text, args.expect, args.first)
        start, reported, trouble = time.time(), None, None
        while True:
            try:
                started, blocking = queue.try_start(token)
            except sqlite3.OperationalError as error:  # e.g. a disk I/O error on Windows just after a wrapper was killed
                if str(error) != trouble:
                    trouble = str(error)
                    print(f"test lock: the queue could not be read ({error}), trying again", file=sys.stderr)
                started, blocking = False, []
            if started:
                if blocking:
                    print(f"test lock: {mode} starts ahead of #{', #'.join(str(e.id) for e in blocking)}, "
                          f"expected to end in time for them (at most {SLACK:.0f} s after they could start)",
                          file=sys.stderr)
                break
            now = time.time()
            if now - start >= args.wait:
                print(f"test lock: gave up after {(now - start) / 60:.0f} min of waiting", file=sys.stderr)
                return 75
            if reported is None or now - reported >= REPORT:
                reported = now
                print(f"test lock: {mode} waits for", file=sys.stderr)
                for entry in blocking:
                    print(f"  {_describe(entry, now)}", file=sys.stderr)
                sys.stderr.flush()
            time.sleep(POLL)
        began = time.time()
        process = subprocess.Popen(command, env=_environment(mode), start_new_session=os.name != "nt",
                                   **_priority(mode))
        try:
            code = process.wait(timeout=args.timeout)
        except subprocess.TimeoutExpired:
            print(f"test lock: command still running after {args.timeout / 60:.0f} min, killing its process tree",
                  file=sys.stderr)
            _kill_tree(process)
            code = 124
        queue.record(command, time.time() - began, code)  # not after Ctrl-C: cut short
        return code
    except KeyboardInterrupt:
        if process is not None:
            _kill_tree(process)
        return 130
    finally:
        queue.remove(token)
        _release(holder)


def status(_args) -> int:
    queue = Queue(lock_dir())
    queue.db.execute("BEGIN IMMEDIATE")
    try:
        entries = queue.live()
    finally:
        queue.db.execute("COMMIT")
    now = time.time()
    print(f"{queue.folder} ({SLOTS} shared slots, {datetime.now():%H:%M:%S})")
    for entry in entries:
        print(f"  {_describe(entry, now, queue.estimate(entry))}")
    if not entries:
        print("  (empty)")
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0].strip(),
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="action", required=True)
    runner = commands.add_parser("run", help="run a command under the lock")
    runner.add_argument("--exclusive", action="store_true",
                        help="nothing else at the same time, all cores, normal priority (shared: below it)")
    runner.add_argument("--resource", action="append", default=[], metavar="NAME",
                        help="also one at a time with every command naming it (data, docker, opentopo, ...)")
    runner.add_argument("--owner", default="agent", help="who runs it (a session or agent name)")
    runner.add_argument("--timeout", type=float, help="seconds before the command's process tree is killed "
                                                      f"(default {TIMEOUT['shared']} shared, "
                                                      f"{TIMEOUT['exclusive']} exclusive)")
    runner.add_argument("--wait", type=float, default=WAIT, help=f"seconds to wait at most (default {WAIT})")
    runner.add_argument("--expect", type=float, metavar="SECONDS",
                        help="how long the command takes (default: from the runs before); a command with an "
                             f"estimate may pass waiting ones if it ends at most {SLACK:.0f} s after they may start")
    runner.add_argument("--first", action="store_true",
                        help="wait ahead of every waiting command (never ahead of a running one); only with "
                             "the user's permission")
    runner.add_argument("command", nargs=argparse.REMAINDER)
    commands.add_parser("status", help="the running and waiting commands")
    args = parser.parse_args(argv)
    if args.action == "status":
        return status(args)
    if not [c for c in args.command if c != "--"]:
        parser.error("no command")
    if args.timeout is None:
        args.timeout = TIMEOUT["exclusive" if args.exclusive else "shared"]
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
