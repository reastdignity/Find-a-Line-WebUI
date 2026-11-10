"""
Run by hand (or by agents): a command under the shared test lock of all checkouts of the repository.

Parallel sessions and agents (each in its own worktree) share the cores, the memory and a few
other things. A command waits in one first-come-first-served queue until it may start:

- shared (the default): pytest, builds, regression runs compared by checksums only, small
  searches. At most SLOTS at once, below the normal priority (their processes inherit it, so the
  desktop and an exclusive command come first), each with the threads of numba, OpenMP, BLAS and
  GDAL capped to cores / THREAD_SHARE whatever the slots (the results do not depend on them:
  tests/test_units.py::test_kernels_independent_of_threads; most shared commands keep about one
  core busy, so the slots are more than cores / threads).
- --heavy: a big run that measures nothing (a production `country run`, a large search or
  run_batch compared by checksum, the CI replay in Docker Desktop with --resource docker): one
  heavy at a time, beside the shared ones (it takes no slot and keeps none of them out), normal
  priority and all threads; a new one with --memory GB (its peak until the history knows it).
- --exclusive: nothing else runs, all cores, normal priority: anything whose seconds or memory
  are read (tools/perf_*.py, the times of tests/regression.py, --tracemalloc), comparisons of
  tiled areas without a fixed --tile-size (the tiles follow the free memory).
- --resource NAME (repeatable): also one at a time with every other command naming it, e.g.
  `data` (the real data folder: cache update, osm update, migrations), `docker`, `opentopo`
  (the demo key's 50 calls a day).
- --first: waits ahead of every waiting command (never of a running one; several of them in
  their order). Only with the user's permission.

A command waits for a running one it conflicts with (either exclusive, both heavy, or a resource
in common) and for every earlier waiting one it conflicts with, so a waiting --exclusive keeps new
shared commands out, a waiting --heavy only new heavy and exclusive ones, and shared commands take
the free slots in their order. One exception (backfill):
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

The RAM guard (with psutil; without it nothing is guarded): each wrapper samples the RSS of its
command's process tree every POLL, writes it to its row (entries.rss_bytes) and its peak into
`history` (peak_bytes). A shared or heavy command whose expected peak is known (--memory GB, else
the largest peak of the same command's last runs, else the 90th percentile of its kind's, as the
times) starts only when it fits the budget: of the available memory less RAM_MARGIN and of
the share of all memory less what is used, the smaller (`memory_limit`), less what the running
commands with a known peak may still grow by (their peak less their RSS now) and the peaks of
those admitted before it. The share is the user's setting: RAM_SHARE (0.8) unless `ram-share`
(or the page's "RAM limit" choice) sets another between SHARE_MIN and SHARE_MAX; it is stored in
the queue's table `settings` and read at every look, so a change reaches the waiting wrappers
at once (`ram-share` prints it, `ram-share 90` sets it, `ram-share --reset` clears it). `status`
and the page show the limit, what the running commands may still grow by, and the budget. One that does not fit waits "for memory" (counted toward --wait) with a reservation
from the running shared and heavy ones with a known peak: a later shared one passes it when it
fits itself, a later heavy or exclusive one it conflicts with only by its estimate. Exclusive
commands and those without a known peak are not guarded.

The default --timeout: TIMEOUT of the mode, or TIMEOUT_FACTOR times the command's estimate when
that is longer (a line says so).

The user's state (STATES, from the most to the least permissive; set by the test lock page,
tools/test_lock_page.py, or by `state`) says whether they are using the PC, so agents queue
their measurements instead of asking:
- free (also when never set): as above.
- heavy-ok: no waiting exclusive command starts; a heavy one starts tamed (below the normal
  priority, at most HEAVY_TAMED_THREADS threads, FINDALINE_TEST_LOCK=heavy-tamed); shared ones
  as free. The state when it starts decides: a heavy one started while free keeps its threads
  and priority ("running untamed" in `status` and on the page, which can stop it).
- busy: no waiting exclusive or heavy command starts (measurements and big runs wait); it is not
  admissible and holds nobody up, so shared ones behind it start as if it were not there, and it
  has no reservation.
- quiet: no waiting command starts.
Running commands are never touched by it, and --first keeps its meaning among the admissible
ones. A state may last until a time and then become another (free unless given): every reader
resolves it (user_state), no timer anywhere. The time a command is held by the state does not
count toward --wait, so a measurement queued in the morning still waits in the evening.
The page may also ask the wrapper of a running command to stop it (entries.stop): the wrapper
kills the command's process tree and exits 125; such a run never goes into `history`.

The queue is a SQLite database in the git common directory (<.git>/findaline-locks/, the same
for every worktree, never in `git status`); every entry holds an OS lock (filelock) for as long
as its wrapper lives, so the entry of a killed wrapper is dropped by the next one that looks.
Killing the wrapper itself leaves its command running: stop a hung command, not the wrapper.

    python tools/test_lock.py run [--exclusive | --heavy] [--memory GB] [--resource data] [--owner NAME]
                                  [--expect S] [--first] [--timeout S] [--wait S] -- pytest
    python tools/test_lock.py status
    python tools/test_lock.py state [free|heavy-ok|busy|quiet] [--until 18:00|'2026-11-09 07:00'|+2h|+90m]
                                    [--after STATE] [--note TEXT]

Runs with the standard library and filelock, psutil when there (any Python of the repository's
environment; run it from the main checkout's path, a worktree of an older branch may not have it).
Exit codes: the command's, 75 gave up waiting (--wait, the time held by the user's state not
counted), 124 killed after --timeout, 125 stopped from the test lock page, 130 Ctrl-C.
"""

import argparse
import ntpath
import os
import re
import secrets
import shlex
import signal
import sqlite3
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable, Dict, List, Optional, Sequence, Set

from filelock import FileLock, Timeout

try:  # the RAM guard: without psutil nothing is sampled or guarded
    import psutil
except ImportError:
    psutil = None

MODES = ("shared", "heavy", "exclusive")
SLOTS = int(os.environ.get("FINDALINE_TEST_SLOTS", "6"))
THREAD_SHARE = 3      # a shared command's threads: cores / THREAD_SHARE, as with the 3 slots before 2026-11-03
                      # (the lock monitor of 2026-11-01..03: a median of 0.8 cores busy per shared command)
HEAVY_TAMED_THREADS = 16  # the threads of a heavy command started while the user is heavy-ok (at most the cores)
NICE = 10             # the niceness of shared and tamed commands on POSIX (Windows: below normal)
SLACK = 120.0         # seconds a command passing a waiting one may end after that one's reservation
POLL = float(os.environ.get("FINDALINE_TEST_LOCK_POLL", "2"))  # seconds between looks at the queue
REPORT = 300                                                    # seconds between "still waiting" lines
TIMEOUT = {"shared": 3600, "heavy": 3 * 3600, "exclusive": 3 * 3600}   # default --timeout per mode,
TIMEOUT_FACTOR = 1.5                                            # or this times the estimate when longer
WAIT = 4 * 3600                                                 # default --wait
GB = 2 ** 30          # --memory is in GiB
RAM_SHARE = 0.8       # the RAM guard: the share of all memory the PC may use with the lock's commands,
RAM_MARGIN = 2 * GB   # and the bytes left available whatever the share (binds on a PC under 10 GiB)
SHARE_MIN, SHARE_MAX = 0.5, 0.98   # what `ram-share` and the page accept (the user's setting, read at every look)
TREE_EVERY = 10.0     # seconds between listings of a command's process tree (75 ms with 600 processes on
                      # Windows); its known processes' RSS is read at every look (microseconds)
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
STATES = ("free", "heavy-ok", "busy", "quiet")   # the user's state, from the most to the least permissive
FREE = "free"
HOLDS = {"busy": "the PC is in use",              # what holds a waiting command besides the others (try_start)
         "quiet": "the user asked for quiet",
         "memory": "not enough free memory"}
STATE_HOLDS = ("busy", "quiet")                   # those of the user's state (held): not counted toward --wait
STOPPED = 125         # the exit code of a command stopped from the test lock page

SCHEMA = """CREATE TABLE IF NOT EXISTS entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT, token TEXT NOT NULL, mode TEXT NOT NULL,
    resources TEXT NOT NULL, owner TEXT NOT NULL, pid INTEGER NOT NULL, command TEXT NOT NULL,
    queued REAL NOT NULL, started REAL);
-- newer columns come from the ALTER loop of Queue.__init__ (ENTRY_COLUMNS, HISTORY_COLUMNS)
CREATE TABLE IF NOT EXISTS history (
    id INTEGER PRIMARY KEY AUTOINCREMENT, key TEXT NOT NULL, kind TEXT, seconds REAL NOT NULL,
    code INTEGER NOT NULL, ended REAL NOT NULL);
CREATE INDEX IF NOT EXISTS history_key ON history (key);
CREATE INDEX IF NOT EXISTS history_kind ON history (kind);
CREATE TABLE IF NOT EXISTS state (
    key TEXT PRIMARY KEY, value TEXT NOT NULL, since REAL NOT NULL, until REAL, after TEXT, note TEXT);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value REAL NOT NULL)"""
ENTRY_COLUMNS = (("expect", "REAL"), ("first", "INTEGER"), ("stop", "REAL"), ("memory", "INTEGER"),
                 ("tamed", "INTEGER"), ("rss_bytes", "INTEGER"))   # added to `entries` in this order
HISTORY_COLUMNS = (("peak_bytes", "INTEGER"),)                       # added to `history`

Peak = Callable[["Entry"], Optional[float]]   # the bytes an entry's command is expected to take at most


@dataclass
class Entry:
    id: int
    token: str
    mode: str                 # one of MODES
    resources: List[str]
    owner: str
    pid: int
    command: str
    queued: float
    started: Optional[float]        # None while waiting
    expect: Optional[float] = None  # seconds given by --expect
    first: bool = False             # --first: ahead of the waiting ones without it
    stop: Optional[float] = None    # when the test lock page asked to stop it (running ones only)
    memory: Optional[int] = None    # bytes given by --memory
    tamed: bool = False             # a heavy one started while the user's state was heavy-ok
    rss: Optional[int] = None       # the RSS of a running one's command tree at its wrapper's last look


def order(entry: Entry) -> tuple:
    """The order of the queue: --first ones, then the others, each in the order they came."""
    return (not entry.first, entry.id)


def conflicts(a: Entry, b: Entry) -> bool:
    """May the two never run at the same time: either exclusive, both heavy, or a resource in common."""
    return (a.mode == "exclusive" or b.mode == "exclusive" or a.mode == b.mode == "heavy"
            or bool(set(a.resources) & set(b.resources)))


def held(entry: Entry, state: str) -> Optional[str]:
    """What of the user's state holds a waiting entry (a key of HOLDS), None when nothing:
    quiet holds every one, busy the exclusive and heavy ones, heavy-ok the exclusive ones (a
    heavy one starts tamed then: tames)."""
    if state == "quiet":
        return "quiet"
    if entry.mode == "exclusive" and state in ("busy", "heavy-ok") or entry.mode == "heavy" and state == "busy":
        return "busy"
    return None


def tames(mode: str, state: str) -> bool:
    """Whether a command of the mode starting while the user's state is `state` runs tamed: a heavy
    one while heavy-ok (below the normal priority, at most HEAVY_TAMED_THREADS threads)."""
    return mode == "heavy" and state == "heavy-ok"


def untamed(entry: Entry, state: str) -> bool:
    """A heavy one running untamed (started while free) although the user's state now asks for
    less (heavy-ok or busy): its threads and priority cannot change, the page can stop it."""
    return entry.mode == "heavy" and entry.started is not None and not entry.tamed and state in ("heavy-ok", "busy")


def memory_limit(memory: tuple, share: float = RAM_SHARE, margin: float = RAM_MARGIN) -> float:
    """The bytes the lock's commands may still take before the running ones' growth is counted:
    of the available memory less `margin` and of `share` of all memory less what is used, the smaller."""
    available, total = memory
    return min(available - margin, share * total - (total - available))


def memory_budget(entries: Sequence[Entry], memory: Optional[tuple], peak: Optional[Peak],
                  share: float = RAM_SHARE, margin: float = RAM_MARGIN) -> Optional[float]:
    """The bytes the waiting commands may still take (the RAM guard): of the available memory less
    `margin` and of `share` of all memory less what is used, the smaller, less what each running
    command with an expected peak may still grow by (its peak less its RSS now, the whole peak
    when its RSS is unknown, nothing without a peak). None when `memory` (available, total) or
    `peak` is None: nothing is guarded."""
    if memory is None or peak is None:
        return None
    budget = memory_limit(memory, share, margin)
    for entry in entries:
        if entry.started is not None:
            expected = peak(entry)
            if expected is not None:
                budget -= expected if entry.rss is None else max(0, expected - entry.rss)
    return budget


def startable(entries: Sequence[Entry], now: float, estimate: Callable[[Entry], Optional[float]],
              slots: int = SLOTS, passing: Optional[Callable[[Entry], Optional[float]]] = None,
              slack: float = SLACK, state: str = FREE, memory: Optional[tuple] = None, peak: Optional[Peak] = None,
              share: float = RAM_SHARE, margin: float = RAM_MARGIN,
              room: Optional[Dict[int, tuple]] = None) -> Set[int]:
    """The ids of the waiting entries that may start now. The waiting ones are taken in their
    order, each one admitted counting as started: one may start with no running or admitted one
    it conflicts with and, if shared, a slot left by them; and with no earlier waiting one it
    conflicts with, unless it is expected (by `passing`, else `estimate`) to end in time for
    that one (backfill). In time: at most `slack` after the latest expected end of the running
    and admitted ones it conflicts with that did not pass it (their start plus their estimate,
    not before now, and now when unknown), and in any case before the latest of all it
    conflicts with; with only those that passed it, before the latter, so the ones passing it
    never push it back further. Passed it: later in the order and started after it came.
    One held by the user's `state` (held) is not admissible and holds nobody up: the later ones
    are taken as if it were not there (it has no reservation).
    The RAM guard, with `memory` (available, total bytes) and `peak`: a shared or heavy one with
    an expected peak starts only when that fits the budget (memory_budget, less the peaks of the
    ones admitted before it); one that does not is held with a reservation that also counts the
    running and admitted shared and heavy ones with an expected peak (it waits for their memory),
    so a later shared one passes it when it fits itself, a later one it conflicts with only by
    its estimate. Exclusive ones and those without a peak are not guarded. `room` gets each
    guarded one's (expected peak, budget left for it)."""
    started = {e.id: e.started for e in entries if e.started is not None}
    by_id = {e.id: e for e in entries}
    seconds = {e.id: estimate(e) for e in entries}
    passing = passing or estimate
    peaks: Dict[int, Optional[float]] = {}

    def peak_of(entry: Entry) -> Optional[float]:
        if entry.id not in peaks:
            peaks[entry.id] = peak(entry)
        return peaks[entry.id]

    budget = memory_budget(entries, memory, peak_of if peak is not None else None, share, margin)

    def end(id: int) -> float:
        return now if seconds[id] is None else max(now, started[id] + seconds[id])

    held_up: Dict[int, float] = {}   # waiting ones not admitted → the end a later one passing them may not exceed
    for entry in sorted((e for e in entries if e.started is None), key=order):
        if held(entry, state) is not None:
            continue
        blocking = [i for i in started if conflicts(entry, by_id[i])]
        full = entry.mode == "shared" and sum(by_id[i].mode == "shared" for i in started) >= slots
        passed = [i for i in held_up if conflicts(entry, by_id[i])]
        own = passing(entry) if passed else None
        passes = all(own is not None and now + own <= held_up[i] for i in passed)
        need = peak_of(entry) if budget is not None and entry.mode != "exclusive" else None
        if need is not None and room is not None:
            room[entry.id] = (need, budget)
        tight = need is not None and need > budget
        if not blocking and not full and passes and not tight:
            started[entry.id] = now
            if need is not None:
                budget -= need
        else:
            if tight:  # it waits for the memory of the running and admitted ones with a peak too
                blocking += [i for i in started if i not in blocking and by_id[i].mode != "exclusive"
                             and peak_of(by_id[i]) is not None]
            before = [end(i) for i in blocking if order(by_id[i]) < order(entry) or started[i] <= entry.queued]
            latest = max((end(i) for i in blocking), default=now)
            held_up[entry.id] = max(latest, max(before) + slack) if before else latest
    return {i for i in started if by_id[i].started is None}


def may_start(entry: Entry, others: Sequence[Entry], slots: int = SLOTS,
              estimate: Callable[[Entry], Optional[float]] = lambda e: None, now: Optional[float] = None,
              state: str = FREE) -> bool:
    """Whether a waiting entry may start now, given the other live entries (startable)."""
    return entry.id in startable([entry, *others], time.time() if now is None else now, estimate, slots,
                                 state=state)


def blockers(entry: Entry, entries: Sequence[Entry], state: str = FREE, peak: Optional[Peak] = None) -> List[Entry]:
    """The live entries a waiting one waits for (besides the user's state): the running ones it
    conflicts with or shares the slots with, and the earlier waiting ones of those the state
    does not hold (one it holds holds nobody up); with `peak` (one held by the RAM guard) also
    the running shared and heavy ones with an expected peak, whose memory it waits for."""
    return [e for e in entries if e.id != entry.id
            and (e.started is not None or (order(e) < order(entry) and held(e, state) is None))
            and (conflicts(entry, e) or e.mode == entry.mode == "shared"
                 or (peak is not None and e.started is not None and e.mode != "exclusive" and peak(e) is not None))]


@dataclass
class UserState:
    value: str                    # one of STATES
    since: Optional[float]        # when it began (written, or its `until` passed); None: never set
    until: Optional[float] = None
    after: Optional[str] = None   # the state from `until` on (with `until` only)
    note: Optional[str] = None


def resolve_state(row: Optional[tuple], now: float) -> UserState:
    """The user's state at `now` from the row (value, since, until, after, note) of the table
    `state`: none is free; once `until` has passed, `after` (free when NULL) since `until`."""
    if row is None:
        return UserState(FREE, None)
    value, since, until, after, note = row
    if until is not None and now >= until:
        return UserState(after or FREE, until)
    if until is None:
        return UserState(value, since, note=note)
    return UserState(value, since, until, after or FREE, note)


def parse_until(text: str, now: Optional[float] = None) -> float:
    """The epoch seconds of `--until`: HH:MM (today, or tomorrow once past), 'YYYY-MM-DD HH:MM'
    (not past), or a duration from now: +2h, +90m, +1h30m, +1.5h."""
    now = time.time() if now is None else now
    text = text.strip()
    match = re.fullmatch(r"\+\s*(?:(\d+(?:\.\d+)?)\s*h)?\s*(?:(\d+(?:\.\d+)?)\s*m(?:in)?)?", text)
    if match and (match.group(1) or match.group(2)):
        return now + float(match.group(1) or 0) * 3600 + float(match.group(2) or 0) * 60
    try:
        clock = datetime.strptime(text, "%H:%M")
    except ValueError:
        pass
    else:
        at = datetime.fromtimestamp(now).replace(hour=clock.hour, minute=clock.minute, second=0, microsecond=0)
        if at.timestamp() <= now:
            at += timedelta(days=1)
        return at.timestamp()
    try:
        at = datetime.strptime(text, "%Y-%m-%d %H:%M").timestamp()
    except ValueError:
        raise ValueError(f"not a time: {text!r} (HH:MM, 'YYYY-MM-DD HH:MM', +2h or +90m)") from None
    if at <= now:
        raise ValueError(f"{text} has passed")
    return at


def _clock(at: float, now: float) -> str:
    """A time of day, with its day when not today's."""
    day = datetime.fromtimestamp(at)
    days = (day.date() - datetime.fromtimestamp(now).date()).days
    prefix = {0: "", -1: "yesterday ", 1: "tomorrow "}.get(days, f"{day:%Y-%m-%d} ")
    return f"{prefix}{day:%H:%M}"


def describe_state(state: UserState, now: float) -> str:
    """'busy since 14:02, until 18:00, then free; note: ...' (just 'free' when never set)."""
    text = state.value if state.since is None else f"{state.value} since {_clock(state.since, now)}"
    if state.until is not None:
        text += f", until {_clock(state.until, now)}, then {state.after or FREE}"
    return f"{text}; note: {state.note}" if state.note else text


def command_key(command: Sequence[str]) -> str:
    """The command as text, its program by name only (the same in every checkout)."""
    return shlex.join([_name(command[0]), *command[1:]]) if command else ""


def command_kind(command: Sequence[str]) -> Optional[str]:
    """pytest, pytest-all, regression.py, npm, ...: the program, or the script run by Python or uv;
    None for `python -c`. A pytest of the whole suite (no test named or selected) is pytest-all:
    it takes ten minutes where most chosen tests take seconds. uv's own options are skipped
    (`uv run --frozen --project X pytest`): an option of it taking a value not in UV_VALUES
    gives the kind of its value."""
    i = program_index(command)
    if i == len(command) or command[i].startswith("-"):
        return None
    kind = _name(command[i])
    return "pytest-all" if kind == "pytest" and not _selects(command[i + 1:]) else kind


def program_index(command: Sequence[str]) -> int:
    """Where the program or script that a command runs stands, after Python, uv and their
    options (command_kind); len(command) when there is none, at `-c` for `python -c`."""
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
    return min(i, len(command))


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
                                text=True, encoding="utf-8", check=True).stdout.strip()  # git's paths: UTF-8
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
        # What the last try_start read: the user's state, the entry itself, whether it started tamed,
        # and for one held by the RAM guard (its expected peak, the budget left for it, available, total)
        self.state = UserState(FREE, None)
        self.me: Optional[Entry] = None
        self.tamed = False
        self.room: Optional[tuple] = None
        self.db = sqlite3.connect(os.path.join(folder, "queue.sqlite"), timeout=60, isolation_level=None)
        # One at a time: wrappers setting up a new queue together get "database is locked" at once,
        # without the busy timeout (switching to WAL, creating the schema)
        with FileLock(os.path.join(folder, "setup.lock"), fallback_to_soft=False):
            self.db.execute("PRAGMA journal_mode=WAL")
            self.db.executescript(SCHEMA)
            for table, added in (("entries", ENTRY_COLUMNS), ("history", HISTORY_COLUMNS)):
                columns = [row[1] for row in self.db.execute(f"PRAGMA table_info({table})")]
                for column, kind in added:
                    if column not in columns:  # wrappers of older checkouts leave it NULL
                        self.db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {kind}")
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
                               "first, stop, memory, tamed, rss_bytes FROM entries ORDER BY id").fetchall()
        return [Entry(i, t, m, [r for r in res.split(",") if r], o, p, c, q, s, x, bool(f), stop, mem, bool(tamed), rss)
                for i, t, m, res, o, p, c, q, s, x, f, stop, mem, tamed, rss in rows]

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
            expect: Optional[float] = None, first: bool = False, memory: Optional[int] = None) -> int:
        cursor = self.db.execute("INSERT INTO entries (token, mode, resources, owner, pid, command, queued, expect, "
                                 "first, memory) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                                 (token, mode, ",".join(sorted(set(resources))), owner, os.getpid(), command,
                                  time.time(), expect, int(first), memory))
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

    def peak(self, entry: Entry) -> Optional[int]:
        """The bytes the entry's command is expected to take at most (the RAM guard): --memory, else
        the largest peak of the last SAME_RUNS runs of the same command with one, else the 90th
        percentile of the last KIND_RUNS runs of its kind with one; None without (not guarded)."""
        if entry.memory is not None:
            return entry.memory
        try:
            command = shlex.split(entry.command)
        except ValueError:  # not written by shlex.join: no peak
            return None
        same = self.db.execute("SELECT max(peak_bytes) FROM (SELECT peak_bytes FROM history WHERE key = ? AND "
                               "peak_bytes IS NOT NULL ORDER BY id DESC LIMIT ?)",
                               (command_key(command), SAME_RUNS)).fetchone()[0]
        kind = command_kind(command)
        if same is not None or kind is None:
            return same
        runs = sorted(p for (p,) in self.db.execute("SELECT peak_bytes FROM history WHERE kind = ? AND peak_bytes "
                                                     "IS NOT NULL ORDER BY id DESC LIMIT ?", (kind, KIND_RUNS)))
        return runs[(9 * len(runs) + 9) // 10 - 1] if runs else None

    def record(self, command: Sequence[str], seconds: float, code: int, peak: Optional[int] = None) -> None:
        """A finished command's time and the peak RSS of its process tree (None: not sampled), for
        the estimates."""
        self.db.execute("INSERT INTO history (key, kind, seconds, code, ended, peak_bytes) VALUES (?, ?, ?, ?, ?, ?)",
                        (command_key(command), command_kind(command), seconds, code, time.time(), peak))
        self.db.execute("DELETE FROM history WHERE id <= (SELECT max(id) FROM history) - ?", (HISTORY_ROWS,))

    def admission(self, entries: Sequence[Entry], now: float, state: str, memory: Optional[tuple]) -> tuple:
        """(the ids of the waiting entries that may start now (startable with the history's estimates
        and peaks), what holds each waiting one besides the others: None or a key of HOLDS, by id,
        the RAM guard's (expected peak, budget left for it) of each guarded waiting one). "memory":
        held by the RAM guard, so admitted without it (memory None)."""
        estimates: Dict[tuple, Optional[float]] = {}
        peaks: Dict[int, Optional[int]] = {}

        def estimate(entry: Entry, passing: bool = False) -> Optional[float]:
            if (entry.id, passing) not in estimates:
                estimates[entry.id, passing] = self.estimate(entry, passing)
            return estimates[entry.id, passing]

        def peak(entry: Entry) -> Optional[int]:
            if entry.id not in peaks:
                peaks[entry.id] = self.peak(entry)
            return peaks[entry.id]

        share = self.ram_share()

        def admit(memory: Optional[tuple], room: Optional[dict] = None) -> Set[int]:
            return startable(entries, now, estimate, passing=lambda e: estimate(e, True), state=state,
                             memory=memory, peak=peak, share=share, room=room)

        room: Dict[int, tuple] = {}
        admitted = admit(memory, room)
        unguarded = None
        holds: Dict[int, Optional[str]] = {}
        for entry in entries:
            if entry.started is None:
                hold = held(entry, state)
                if hold is None and entry.id in room and entry.id not in admitted:
                    unguarded = admit(None) if unguarded is None else unguarded
                    hold = "memory" if entry.id in unguarded else None
                holds[entry.id] = hold
        return admitted, holds, room

    def try_start(self, token: str) -> tuple:
        """(started, the entries it waits for or, once started, the earlier waiting ones it passed,
        what holds it besides them: None or a key of HOLDS). What it read: self.state (the user's
        state), self.me (the entry), self.tamed (started tamed), self.room (held by the RAM guard:
        its expected peak, the budget left for it, the available and the total memory)."""
        self.db.execute("BEGIN IMMEDIATE")
        try:
            entries = self.live(own=token)
            entry = self.me = next(e for e in entries if e.token == token)
            others = [e for e in entries if e.token != token]
            now = time.time()
            self.state = self.user_state(now)
            state = self.state.value
            memory = _memory()
            admitted, holds, room = self.admission(entries, now, state, memory)
            self.room = None
            if entry.id in admitted:
                self.tamed = tames(entry.mode, state)
                self.db.execute("UPDATE entries SET started = ?, tamed = ? WHERE id = ?",
                                (now, int(self.tamed), entry.id))
                result = True, [e for e in others if e.started is None and order(e) < order(entry)
                                and conflicts(entry, e) and held(e, state) is None], None
            else:
                hold = holds[entry.id]
                if hold == "memory":
                    self.room = (*room[entry.id], *memory, self.ram_share())
                result = False, blockers(entry, entries, state, self.peak if hold == "memory" else None), hold
        except BaseException:
            if self.db.in_transaction:
                self.db.execute("ROLLBACK")
            raise
        self.db.execute("COMMIT")
        return result

    def remove(self, token: str) -> None:
        self.db.execute("DELETE FROM entries WHERE token = ?", (token,))

    def ram_share(self) -> float:
        """The share of all memory the RAM guard allows (the user's setting, else RAM_SHARE), read
        at every look: a change takes effect for the waiting wrappers at once."""
        row = self.db.execute("SELECT value FROM settings WHERE key = 'ram_share'").fetchone()
        return RAM_SHARE if row is None or not SHARE_MIN <= row[0] <= SHARE_MAX else row[0]

    def set_ram_share(self, share: Optional[float]) -> float:
        """Sets the RAM guard's share (SHARE_MIN to SHARE_MAX; None: the default RAM_SHARE again)
        and returns it. ValueError for one outside."""
        if share is None:
            self.db.execute("DELETE FROM settings WHERE key = 'ram_share'")
        else:
            if isinstance(share, bool) or not SHARE_MIN <= share <= SHARE_MAX:
                raise ValueError(f"the share of memory: {SHARE_MIN * 100:.0f} to {SHARE_MAX * 100:.0f} %")
            self.db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('ram_share', ?)", (float(share),))
        return self.ram_share()

    def user_state(self, now: Optional[float] = None) -> UserState:
        """The user's state now (resolve_state)."""
        row = self.db.execute("SELECT value, since, until, after, note FROM state WHERE key = 'user'").fetchone()
        return resolve_state(row, time.time() if now is None else now)

    def set_state(self, value: str, until: Optional[float] = None, after: Optional[str] = None,
                  note: Optional[str] = None, now: Optional[float] = None) -> UserState:
        """Sets the user's state from now: `value` until `until` (epoch seconds, None: no end), then
        `after` (free when None). ValueError for an unknown state, a past `until` or one more
        than a year ahead, or `after` without `until`."""
        now = time.time() if now is None else now
        for state in (value, after):
            if state is not None and state not in STATES:
                raise ValueError(f"unknown state {state!r} (one of {', '.join(STATES)})")
        if after is not None and until is None:
            raise ValueError("a state after needs a time until")
        if until is not None and until <= now:
            raise ValueError("the time until has passed")
        if until is not None and until > now + 366 * 86400:
            raise ValueError("the time until is more than a year ahead")
        self.db.execute("INSERT OR REPLACE INTO state (key, value, since, until, after, note) "
                        "VALUES ('user', ?, ?, ?, ?, ?)", (value, now, until, after, note or None))
        return self.user_state(now)

    def request_stop(self, id: int) -> bool:
        """Asks the wrapper of a running entry to stop its command (the test lock page); False
        for an entry that is not live or still waits."""
        self.db.execute("BEGIN IMMEDIATE")
        try:
            entry = next((e for e in self.live() if e.id == id), None)
            if entry is not None and entry.started is not None:
                self.db.execute("UPDATE entries SET stop = coalesce(stop, ?) WHERE id = ?", (time.time(), id))
        except BaseException:
            if self.db.in_transaction:
                self.db.execute("ROLLBACK")
            raise
        self.db.execute("COMMIT")
        return entry is not None and entry.started is not None

    def stop_requested(self, token: str) -> bool:
        """Whether the page asked to stop the entry's command."""
        return self.touch(token, None)

    def touch(self, token: str, rss: Optional[int]) -> bool:
        """The look of a running entry's wrapper every POLL: writes the RSS of its command's tree
        (when known; autocommit, outside any transaction) and says whether the page asked to stop
        it. A database error is let go (the next look tries again)."""
        try:
            if rss is not None:
                self.db.execute("UPDATE entries SET rss_bytes = ? WHERE token = ?", (rss, token))
            row = self.db.execute("SELECT stop FROM entries WHERE token = ?", (token,)).fetchone()
        except sqlite3.OperationalError:
            return False
        return row is not None and row[0] is not None


def _memory() -> Optional[tuple]:
    """(available, total) bytes of the PC's memory; None without psutil (the RAM guard is off)."""
    if psutil is None:
        return None
    try:
        memory = psutil.virtual_memory()
    except Exception:  # noqa: BLE001 (no guard rather than no lock)
        return None
    return memory.available, memory.total


def _tree(pid: int) -> list:
    """psutil's processes of a process tree: the process and its descendants ([] once gone or
    without psutil)."""
    if psutil is None:
        return []
    try:
        root = psutil.Process(pid)
        return [root, *root.children(recursive=True)]
    except psutil.Error:
        return []


def _tree_rss(pid: int, tree: Optional[list] = None) -> Optional[int]:
    """The RSS of a process tree: the sum over the process and its descendants, those that ended
    left out; tree: its processes as listed before (_tree), so they are not listed again. None
    without psutil or once nothing of it is left."""
    if psutil is None:
        return None
    total, seen = 0, False
    for process in _tree(pid) if tree is None else tree:
        try:
            total += process.memory_info().rss
            seen = True
        except psutil.Error:
            continue
    return total if seen else None


def _describe(entry: Entry, now: float, expected: Optional[float] = None, hold: Optional[str] = None,
              peak: Optional[float] = None, state: str = FREE) -> str:
    text = (f"running {(now - entry.started) / 60:.0f} min" if entry.started is not None
            else f"waiting {(now - entry.queued) / 60:.0f} min")
    details = []
    if expected is not None:
        details.append(f"takes ~{expected / 60:.1f} min")
    if peak is not None:
        details.append(f"~{peak / GB:.1f} GB")
    if entry.started is not None and entry.rss is not None:
        details.append(f"uses {entry.rss / GB:.1f} GB")
    if details:
        text += f" ({', '.join(details)})"
    if entry.mode == "heavy" and entry.tamed:
        text += " (tamed)"
    elif untamed(entry, state):
        text += " (running untamed)"
    if hold is not None:
        text += f" (held: {HOLDS[hold]})"
    if entry.stop is not None:
        text += " (asked to stop)"
    resources = f" +{','.join(entry.resources)}" if entry.resources else ""
    first = " first" if entry.first else ""
    return f"#{entry.id} {entry.mode}{resources}{first} {text} owner={entry.owner} pid={entry.pid}: {entry.command}"


def _room_text(room: tuple) -> str:
    """What the RAM guard holds a command by: its expected peak, the budget left for it, the use."""
    need, budget, available, total, share = room
    return (f"needs ~{need / GB:.1f} GB, {max(0.0, budget) / GB:.1f} GB free for it (RAM "
            f"{(total - available) / GB:.1f} of {total / GB:.1f} GB used, limit {share * 100:.0f} %)")


def _tamed_threads() -> int:
    return max(1, min(HEAVY_TAMED_THREADS, os.cpu_count() or 1))


def _environment(mode: str, tamed: bool = False) -> dict:
    """The command's environment: FINDALINE_TEST_LOCK names its mode (heavy-tamed for a tamed heavy
    one); the threads of numba, OpenMP, BLAS and GDAL capped for a shared or tamed one, all the
    cores otherwise."""
    env = dict(os.environ, FINDALINE_TEST_LOCK="heavy-tamed" if tamed else mode)
    if mode == "shared" or tamed:
        threads = str(_tamed_threads() if tamed else max(1, (os.cpu_count() or 1) // THREAD_SHARE))
        env.update({name: threads for name in THREAD_VARS})
    return env


def _priority(mode: str, tamed: bool = False) -> dict:
    """Popen's arguments for the priority of the command: shared and tamed heavy ones below the
    normal one, exclusive and heavy ones the normal one (its processes inherit it; on POSIX they
    keep the wrapper's)."""
    low = mode == "shared" or tamed
    if os.name == "nt":
        return {"creationflags": subprocess.BELOW_NORMAL_PRIORITY_CLASS if low else subprocess.NORMAL_PRIORITY_CLASS}
    return {"preexec_fn": lambda: os.nice(NICE)} if low else {}


def _timeout(given: Optional[float], mode: str, expected: Optional[float]) -> float:
    """The seconds before the command's tree is killed: --timeout when given, else TIMEOUT of the
    mode, or TIMEOUT_FACTOR times the command's estimate when that is longer."""
    if given is not None:
        return given
    if expected is None:
        return TIMEOUT[mode]
    return max(TIMEOUT[mode], TIMEOUT_FACTOR * expected)


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
    mode = "exclusive" if args.exclusive else "heavy" if args.heavy else "shared"
    memory = None if args.memory is None else int(args.memory * GB)
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    text = shlex.join(command)
    queue = Queue(lock_dir())
    token = secrets.token_hex(8)
    holder = _holder(queue.folder, token)
    holder.acquire(timeout=0)  # before the entry exists, so nobody takes it for a dead one
    process = None
    try:
        queue.add(token, mode, args.resource, args.owner, text, args.expect, args.first, memory)
        start = looked = time.time()
        reported, said, trouble = None, None, None
        on_hold = 0.0   # seconds held by the user's state: not counted toward --wait
        while True:
            try:
                started, blocking, hold = queue.try_start(token)
            except sqlite3.OperationalError as error:  # e.g. a disk I/O error on Windows just after a wrapper was killed
                if str(error) != trouble:
                    trouble = str(error)
                    print(f"test lock: the queue could not be read ({error}), trying again", file=sys.stderr)
                started, blocking, hold = False, [], None
            now = time.time()
            if hold in STATE_HOLDS:
                on_hold += now - looked
            looked = now
            if started:
                if blocking:
                    print(f"test lock: {mode} starts ahead of #{', #'.join(str(e.id) for e in blocking)}, "
                          f"expected to end in time for them (at most {SLACK:.0f} s after they could start)",
                          file=sys.stderr)
                break
            if now - start - on_hold >= args.wait:
                held_for = f" (and {on_hold / 60:.0f} min held by the user's state)" if on_hold else ""
                print(f"test lock: gave up after {(now - start - on_hold) / 60:.0f} min of waiting{held_for}",
                      file=sys.stderr)
                return 75
            if reported is None or now - reported >= REPORT or hold != said:
                reported, said = now, hold
                if hold == "memory" and queue.room is not None:
                    print(f"test lock: {mode} waits for memory: {_room_text(queue.room)}", file=sys.stderr)
                elif hold is not None:
                    print(f"test lock: {mode} waits: {HOLDS[hold]} ({describe_state(queue.state, now)})",
                          file=sys.stderr)
                if blocking or hold is None:
                    print(f"test lock: {mode} waits for", file=sys.stderr)
                    for entry in blocking:
                        expected_peak = queue.peak(entry) if hold == "memory" else None
                        print(f"  {_describe(entry, now, peak=expected_peak)}", file=sys.stderr)
                sys.stderr.flush()
            time.sleep(POLL)
        tamed = queue.tamed
        expected = queue.estimate(queue.me) if queue.me is not None else None
        timeout = _timeout(args.timeout, mode, expected)
        if args.timeout is None and timeout > TIMEOUT[mode]:
            print(f"test lock: timeout {timeout / 60:.0f} min, {TIMEOUT_FACTOR:g} x the expected "
                  f"{expected / 60:.0f} min", file=sys.stderr)
        if tamed:
            print(f"test lock: heavy starts tamed (the user's state is heavy-ok): below the normal priority, "
                  f"{_tamed_threads()} threads", file=sys.stderr)
        began = time.time()
        deadline = began + timeout
        process = subprocess.Popen(command, env=_environment(mode, tamed), start_new_session=os.name != "nt",
                                   **_priority(mode, tamed))
        code, peak = None, None
        tree, listed = [], None   # the command's processes, listed at that time (TREE_EVERY)
        while code is None:  # in rounds of POLL: its tree's RSS, and a stop asked by the test lock page
            try:
                code = process.wait(timeout=max(0.0, min(POLL, deadline - time.time())))
            except subprocess.TimeoutExpired:
                at = time.time()
                if psutil is not None and (listed is None or at - listed >= min(TREE_EVERY, max(0.0, listed - began))):
                    tree, listed = _tree(process.pid), at   # again after as long as it ran before, at most TREE_EVERY
                rss = _tree_rss(process.pid, tree)
                if rss is not None:
                    peak = rss if peak is None else max(peak, rss)
                if at >= deadline:
                    print(f"test lock: command still running after {timeout / 60:.0f} min, killing its "
                          "process tree", file=sys.stderr)
                    _kill_tree(process)
                    code = 124
                elif queue.touch(token, rss):
                    print("test lock: stopped by the user from the test lock page", file=sys.stderr)
                    _kill_tree(process)
                    code = STOPPED
        if code != STOPPED:  # a stopped run would shorten the estimates
            queue.record(command, time.time() - began, code, peak)  # not after Ctrl-C: cut short
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
        now = time.time()
        state = queue.user_state(now)
        memory = _memory()
        _, holds, _ = queue.admission(entries, now, state.value, memory)
        share = queue.ram_share()
        budget = memory_budget(entries, memory, queue.peak, share)
    finally:
        queue.db.execute("COMMIT")
    print(f"User: {describe_state(state, now)}")
    print(ram_line(memory, budget, share))
    print(f"{queue.folder} ({SLOTS} shared slots, {datetime.now():%H:%M:%S})")
    for entry in entries:
        print(f"  {_describe(entry, now, queue.estimate(entry), holds.get(entry.id), queue.peak(entry), state.value)}")
    if not entries:
        print("  (empty)")
    return 0


def ram_line(memory: Optional[tuple], budget: Optional[float], share: float = RAM_SHARE) -> str:
    """'RAM: 31.2 GB free of 64.0, limit 80 % leaves 12.2 GB, running commands may still grow by
    5.0 GB, budget for the lock 7.2 GB' (memory_limit, memory_budget), or unknown."""
    if memory is None:
        return "RAM: unknown (no psutil)"
    available, total = memory
    limit = memory_limit(memory, share)
    return (f"RAM: {available / GB:.1f} GB free of {total / GB:.1f}, limit {share * 100:.0f} % leaves "
            f"{max(0.0, limit) / GB:.1f} GB, running commands may still grow by "
            f"{max(0.0, limit - budget) / GB:.1f} GB, budget for the lock {max(0.0, budget) / GB:.1f} GB")


def parse_share(text: str) -> float:
    """The share of `ram-share`: 90, 90% or 0.9."""
    try:
        value = float(text.strip().rstrip("%"))
    except ValueError:
        raise ValueError(f"not a share: {text!r} (90, 90% or 0.9)") from None
    return value / 100 if value > 1 else value


def ram_share_command(args, parser: argparse.ArgumentParser) -> int:
    """Prints the RAM guard's share, or sets it (at once for every waiting command) or resets it."""
    queue = Queue(lock_dir())
    try:
        if args.reset:
            share = queue.set_ram_share(None)
        elif args.value is not None:
            share = queue.set_ram_share(parse_share(args.value))
        else:
            share = queue.ram_share()
    except ValueError as error:
        parser.error(str(error))
    print(f"RAM guard: {share * 100:.0f} % of all memory" + (" (the default)" if share == RAM_SHARE else ""))
    return 0


def state_command(args, parser: argparse.ArgumentParser) -> int:
    """Prints the user's state, or sets it."""
    if args.value is None and (args.until or args.after or args.note):
        parser.error("--until, --after and --note go with a state")
    if args.after and not args.until:
        parser.error("--after needs --until")
    queue = Queue(lock_dir())
    now = time.time()
    if args.value is None:
        print(f"User: {describe_state(queue.user_state(now), now)}")
        return 0
    try:
        until = parse_until(args.until, now) if args.until else None
        state = queue.set_state(args.value, until, args.after, args.note, now)
    except ValueError as error:
        parser.error(str(error))
    print(f"User: {describe_state(state, now)}")
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0].strip(),
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="action", required=True)
    runner = commands.add_parser("run", help="run a command under the lock")
    modes = runner.add_mutually_exclusive_group()
    modes.add_argument("--exclusive", action="store_true",
                       help="nothing else at the same time, all cores, normal priority (shared: below it): "
                            "anything whose seconds or memory are read")
    modes.add_argument("--heavy", action="store_true",
                       help="a big run that measures nothing (a production country run, a large search compared "
                            "by checksum, the Docker CI replay): one at a time beside the shared ones, all cores, "
                            "normal priority; while the user's state is heavy-ok it starts tamed (below the normal "
                            f"priority, at most {HEAVY_TAMED_THREADS} threads), while busy it waits")
    runner.add_argument("--memory", type=float, metavar="GB",
                        help="the most memory the command takes, in GiB (default: the peaks of its runs before): a "
                             "shared or heavy one starts only when that much fits under the RAM guard")
    runner.add_argument("--resource", action="append", default=[], metavar="NAME",
                        help="also one at a time with every command naming it (data, docker, opentopo, ...)")
    runner.add_argument("--owner", default="agent", help="who runs it (a session or agent name)")
    runner.add_argument("--timeout", type=float, help="seconds before the command's process tree is killed "
                                                      f"(default {TIMEOUT['shared']} shared, {TIMEOUT['heavy']} "
                                                      f"heavy, {TIMEOUT['exclusive']} exclusive, or "
                                                      f"{TIMEOUT_FACTOR:g} x its expected time when longer)")
    runner.add_argument("--wait", type=float, default=WAIT, help=f"seconds to wait at most (default {WAIT})")
    runner.add_argument("--expect", type=float, metavar="SECONDS",
                        help="how long the command takes (default: from the runs before); a command with an "
                             f"estimate may pass waiting ones if it ends at most {SLACK:.0f} s after they may start")
    runner.add_argument("--first", action="store_true",
                        help="wait ahead of every waiting command (never ahead of a running one); only with "
                             "the user's permission")
    runner.add_argument("command", nargs=argparse.REMAINDER)
    commands.add_parser("status", help="the user's state and the running and waiting commands")
    stater = commands.add_parser(
        "state", help="the user's state: print it, or set it",
        description="free: everything runs; heavy-ok: no measurements (exclusive commands wait), heavy ones start "
                    f"tamed (below your programs' priority, at most {HEAVY_TAMED_THREADS} threads), tests keep "
                    "running; busy: no exclusive or heavy command starts, shared ones keep running below your "
                    "programs' priority; quiet: no waiting command starts. Running commands are never touched.")
    stater.add_argument("value", nargs="?", choices=STATES, help="the state to set (none: print it)")
    stater.add_argument("--until", metavar="T", help="until when: HH:MM (today, or tomorrow once past), "
                                                     "'YYYY-MM-DD HH:MM', or from now: +2h, +90m")
    stater.add_argument("--after", choices=STATES, help="the state once --until has passed (default free)")
    stater.add_argument("--note", help="a note shown with the state")
    sharer = commands.add_parser(
        "ram-share", help="the share of all memory the RAM guard allows: print it, or set it",
        description=f"Takes effect at once for every waiting command. {SHARE_MIN * 100:.0f} to "
                    f"{SHARE_MAX * 100:.0f} %, default {RAM_SHARE * 100:.0f} %.")
    sharer.add_argument("value", nargs="?", help="90, 90% or 0.9 (none: print it)")
    sharer.add_argument("--reset", action="store_true", help=f"the default, {RAM_SHARE * 100:.0f} %% again")
    args = parser.parse_args(argv)
    if args.action == "ram-share":
        return ram_share_command(args, sharer)
    if args.action == "status":
        return status(args)
    if args.action == "state":
        return state_command(args, stater)
    if not [c for c in args.command if c != "--"]:
        parser.error("no command")
    if args.memory is not None and not 0 <= args.memory < float("inf"):
        parser.error("--memory: GiB, 0 or more")
    return run(args)   # the default --timeout once the estimate is known (_timeout)


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):  # UTF-8 when redirected (progress.utf8_output, inline)
        stream.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
