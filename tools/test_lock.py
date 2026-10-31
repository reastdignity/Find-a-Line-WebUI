"""
Run by hand (or by agents): a command under the shared test lock of all checkouts of the repository.

Parallel sessions and agents (each in its own worktree) share the cores, the memory and a few
other things. A command waits in one first-come-first-served queue until it may start:

- shared (the default): pytest, builds, regression runs compared by checksums only. At most
  SLOTS at once, each with the threads of numba, OpenMP, BLAS and GDAL capped to cores / SLOTS
  (the results do not depend on them: tests/test_units.py::test_kernels_independent_of_threads).
- --exclusive: nothing else runs, all cores: measured times or memory (tools/perf_*.py,
  the times of tests/regression.py), comparisons of tiled areas without a fixed --tile-size
  (the tiles follow the free memory), large searches, the CI replay in Docker Desktop.
- --resource NAME (repeatable): also one at a time with every other command naming it, e.g.
  `data` (the real data folder: cache update, osm update, migrations), `docker`, `opentopo`
  (the demo key's 50 calls a day).

A command waits for a running one it conflicts with (either exclusive, or a resource in common)
and for every earlier waiting one it conflicts with, so a waiting --exclusive keeps new shared
commands out, and shared commands take the free slots in their order. The queue is a SQLite
database in the git common directory (<.git>/findaline-locks/, the same for every worktree,
never in `git status`); every entry holds an OS lock (filelock) for as long as its wrapper
lives, so the entry of a killed wrapper is dropped by the next one that looks. Killing the
wrapper itself leaves its command running: stop a hung command, not the wrapper.

    python tools/test_lock.py run [--exclusive] [--resource data] [--owner NAME] -- pytest
    python tools/test_lock.py status

Runs with the standard library and filelock (any Python of the repository's environment;
run it from the main checkout's path, a worktree of an older branch may not have it).
Exit codes: the command's, 75 gave up waiting (--wait), 124 killed after --timeout, 130 Ctrl-C.
"""

import argparse
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
from typing import List, Optional, Sequence

from filelock import FileLock, Timeout

SLOTS = int(os.environ.get("FINDALINE_TEST_SLOTS", "3"))
POLL = float(os.environ.get("FINDALINE_TEST_LOCK_POLL", "2"))  # seconds between looks at the queue
REPORT = 300                                                    # seconds between "still waiting" lines
TIMEOUT = {"shared": 3600, "exclusive": 3 * 3600}               # default --timeout per mode
WAIT = 4 * 3600                                                 # default --wait
THREAD_VARS = ("NUMBA_NUM_THREADS", "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
               "GDAL_NUM_THREADS")
TASKKILL = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "taskkill.exe")

SCHEMA = """CREATE TABLE IF NOT EXISTS entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT, token TEXT NOT NULL, mode TEXT NOT NULL,
    resources TEXT NOT NULL, owner TEXT NOT NULL, pid INTEGER NOT NULL, command TEXT NOT NULL,
    queued REAL NOT NULL, started REAL)"""


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
    started: Optional[float]  # None while waiting


def conflicts(a: Entry, b: Entry) -> bool:
    """May the two never run at the same time."""
    return a.mode == "exclusive" or b.mode == "exclusive" or bool(set(a.resources) & set(b.resources))


def may_start(entry: Entry, others: Sequence[Entry], slots: int = SLOTS) -> bool:
    """Whether a waiting entry may start now, given the other live entries: no running one it
    conflicts with, no earlier waiting one it conflicts with (first come, first served), and
    for a shared one a slot left after the running shared ones and the earlier waiting ones."""
    running = [e for e in others if e.started is not None]
    ahead = [e for e in others if e.started is None and e.id < entry.id]
    if any(conflicts(entry, e) for e in running + ahead):
        return False
    if entry.mode == "shared":
        used = sum(e.mode == "shared" for e in running) + sum(e.mode == "shared" for e in ahead)
        return used < slots
    return True


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
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute(SCHEMA)

    def _entries(self) -> List[Entry]:
        rows = self.db.execute("SELECT id, token, mode, resources, owner, pid, command, queued, started "
                               "FROM entries ORDER BY id").fetchall()
        return [Entry(i, t, m, [r for r in res.split(",") if r], o, p, c, q, s)
                for i, t, m, res, o, p, c, q, s in rows]

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

    def add(self, token: str, mode: str, resources: Sequence[str], owner: str, command: str) -> int:
        cursor = self.db.execute("INSERT INTO entries (token, mode, resources, owner, pid, command, queued) "
                                 "VALUES (?, ?, ?, ?, ?, ?, ?)",
                                 (token, mode, ",".join(sorted(set(resources))), owner, os.getpid(), command,
                                  time.time()))
        return cursor.lastrowid

    def try_start(self, token: str) -> tuple:
        """(started, entries ahead of it that it waits for)."""
        self.db.execute("BEGIN IMMEDIATE")
        try:
            entries = self.live(own=token)
            entry = next(e for e in entries if e.token == token)
            others = [e for e in entries if e.token != token]
            if may_start(entry, others):
                self.db.execute("UPDATE entries SET started = ? WHERE id = ?", (time.time(), entry.id))
                return True, []
            blocking = [e for e in others if (e.started is not None or e.id < entry.id)
                        and (conflicts(entry, e) or e.mode == entry.mode == "shared")]
            return False, blocking
        finally:
            self.db.execute("COMMIT")

    def remove(self, token: str) -> None:
        self.db.execute("DELETE FROM entries WHERE token = ?", (token,))


def _describe(entry: Entry, now: float) -> str:
    state = (f"running {(now - entry.started) / 60:.0f} min" if entry.started is not None
             else f"waiting {(now - entry.queued) / 60:.0f} min")
    resources = f" +{','.join(entry.resources)}" if entry.resources else ""
    return f"#{entry.id} {entry.mode}{resources} {state} owner={entry.owner} pid={entry.pid}: {entry.command}"


def _environment(mode: str) -> dict:
    env = dict(os.environ, FINDALINE_TEST_LOCK=mode)
    if mode == "shared":
        threads = str(max(1, (os.cpu_count() or 1) // SLOTS))
        env.update({name: threads for name in THREAD_VARS})
    return env


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
        queue.add(token, mode, args.resource, args.owner, text)
        start, reported = time.time(), None
        while True:
            started, blocking = queue.try_start(token)
            if started:
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
        process = subprocess.Popen(command, env=_environment(mode), start_new_session=os.name != "nt")
        try:
            return process.wait(timeout=args.timeout)
        except subprocess.TimeoutExpired:
            print(f"test lock: command still running after {args.timeout / 60:.0f} min, killing its process tree",
                  file=sys.stderr)
            _kill_tree(process)
            return 124
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
        print(f"  {_describe(entry, now)}")
    if not entries:
        print("  (empty)")
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0].strip(),
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="action", required=True)
    runner = commands.add_parser("run", help="run a command under the lock")
    runner.add_argument("--exclusive", action="store_true", help="nothing else at the same time, all cores")
    runner.add_argument("--resource", action="append", default=[], metavar="NAME",
                        help="also one at a time with every command naming it (data, docker, opentopo, ...)")
    runner.add_argument("--owner", default="agent", help="who runs it (a session or agent name)")
    runner.add_argument("--timeout", type=float, help="seconds before the command's process tree is killed "
                                                      f"(default {TIMEOUT['shared']} shared, "
                                                      f"{TIMEOUT['exclusive']} exclusive)")
    runner.add_argument("--wait", type=float, default=WAIT, help=f"seconds to wait at most (default {WAIT})")
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
