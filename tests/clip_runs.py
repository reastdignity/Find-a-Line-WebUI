"""Searches of the Żabi Koń clip shared by the test modules: each distinct `findaline.py` command runs once per
pytest session, and every module gets its own copy of the data folder it made.

Six module fixtures (`clip_data` of test_patch, test_reach, test_device_page and test_viewer, `clip_run` of
test_public, `big_clip` of test_shell_c) are imported by name into other modules, and pytest builds a module
fixture again in every module that uses it: the same search ran 19 times for 4 distinct commands. `data_copy`
runs a command once into a store under the session's base temp folder and copies the data folder (cache/,
runs/<id>/, work/, findaline_map.html; mtimes kept) into a new `tmp_path_factory.mktemp(name)` folder each time it
is called. A new test module that wants a run of the clip calls it (or uses one of those fixtures), never a
`findaline.py` of its own.

- **The store is never a test's folder.** Tests write into their data folder (favourites, the app's databases,
  recorded pages): a module that changed the store would change the start of every module after it, so only
  copies are handed out, taken after the command's lock is released.
- **Shared by pytest-xdist's workers.** The store is `<root>/clip-runs/<key>/`, `<root>` the session's base temp
  folder: `getbasetemp()` in a serial run, its parent under xdist (a worker's is `<basetemp>/popen-gwN`). A
  `filelock` per command makes the other workers wait for the one that searches (xdist's recipe for data made once
  per session). pytest clears the base temp folder, so no store outlives its session.
- **The command as the fixtures ran it**: `sys.executable findaline.py <args> --data-dir <store>` in the
  repository, offline (`os.environ` at the moment of the search with HTTP_PROXY and HTTPS_PROXY at a dead port and
  NO_PROXY empty), the output captured, 600 s at most. `<key>` is a label and the sha256 of the arguments, so
  equal commands from different fixtures share one search.
- **A failed search fails every module that needs it**, as when each ran its own: the first gets the assertion
  with the command's output (or the exception: a timeout), the result is stored, and every later caller gets the
  same assertion at once, without searching again.
- `log.txt` in `<root>/clip-runs/` holds a line per search and per copy (pid, xdist worker, seconds waited on
  the lock: by a copy that did not search, the wait for another worker's search).
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Sequence

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OFFLINE = {"HTTP_PROXY": "http://127.0.0.1:9", "HTTPS_PROXY": "http://127.0.0.1:9", "NO_PROXY": ""}
SEARCH_TIMEOUT = 600
LOCK_TIMEOUT = 1500  # a waiting worker: the search's own timeout and some queueing, never forever


def store_root(tmp_path_factory) -> Path:
    """`<root>/clip-runs`: under the session's base temp folder, shared by xdist's workers."""
    base = tmp_path_factory.getbasetemp()
    root = base.parent if os.environ.get("PYTEST_XDIST_WORKER") else base
    folder = root / "clip-runs"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def key_of(args: Sequence[str]) -> str:
    label = "-".join(a.lstrip("-") for a in args if a in ("--surface-file", "--model") or a in ("sag", "formula"))
    return f"{label or 'clip'}-{hashlib.sha256(json.dumps(list(args)).encode()).hexdigest()[:12]}"


def _log(root: Path, text: str):
    """A line of log.txt, under its own lock: appends of several processes at once lose lines on Windows."""
    from filelock import FileLock
    worker = os.environ.get("PYTEST_XDIST_WORKER", "serial")
    with FileLock(str(root / "log.txt.lock"), timeout=LOCK_TIMEOUT):
        with open(root / "log.txt", "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%H:%M:%S')} pid={os.getpid()} worker={worker} {text}\n")


def _search(root: Path, key: str, args: List[str]) -> dict:
    """Run the command into the store (the caller holds its lock) and store its result."""
    data = root / key / "data"
    if data.exists():  # a search cut off before it stored a result
        shutil.rmtree(data)
    data.mkdir(parents=True)
    started = time.monotonic()
    try:
        result = subprocess.run(
            [sys.executable, "findaline.py", *args, "--data-dir", str(data)],
            cwd=REPO, capture_output=True, text=True, encoding="utf-8", timeout=SEARCH_TIMEOUT,
            env={**os.environ, **OFFLINE})
        outcome = {"returncode": result.returncode, "output": result.stdout + result.stderr}
    except Exception as e:  # a timeout: stored as a failure, raised to this caller
        outcome = {"returncode": None, "output": f"{type(e).__name__}: {e}"}
        outcome["seconds"] = round(time.monotonic() - started, 2)
        (root / key / "result.json").write_text(json.dumps(outcome), "utf-8")
        _log(root, f"search {key} failed after {outcome['seconds']} s: {type(e).__name__}")
        raise
    outcome["seconds"] = round(time.monotonic() - started, 2)
    (root / key / "result.json").write_text(json.dumps(outcome), "utf-8")
    _log(root, f"search {key} returncode={outcome['returncode']} {outcome['seconds']} s")
    return outcome


def data_copy(tmp_path_factory, name: str, args: Sequence[str]) -> Path:
    """A new folder `tmp_path_factory.mktemp(name)` holding a copy of the data folder of
    `findaline.py <args> --data-dir <folder>` (the clip's search, run once per session)."""
    from filelock import FileLock
    args = [str(a) for a in args]
    root = store_root(tmp_path_factory)
    key = key_of(args)
    asked = time.monotonic()
    with FileLock(str(root / f"{key}.lock"), timeout=LOCK_TIMEOUT):
        waited = time.monotonic() - asked
        stored = root / key / "result.json"
        if stored.is_file():
            outcome = json.loads(stored.read_text("utf-8"))
            searched = False
        else:
            outcome = _search(root, key, args)
            searched = True
    assert outcome["returncode"] == 0, outcome["output"]
    folder = tmp_path_factory.mktemp(name)
    started = time.monotonic()
    shutil.copytree(root / key / "data", folder, dirs_exist_ok=True)
    _log(root, f"copy {key} -> {folder.name} searched={searched} lock_wait={waited:.2f} s "
               f"copy={time.monotonic() - started:.2f} s")
    return folder
