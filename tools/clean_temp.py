"""
Removes what tests and Claude Code sessions leave behind in the system's temporary folder, which
otherwise only grows (270 GB on 2026-11-03), by kind:

- regression: tests/regression.py's folders (findaline-regression-*), kept after a difference or with --keep;
- ui-shots: the data folders of tools/ui_shots.py runs that did not end (ui-shots-*);
- browser: the extension packages a new Edge or Chrome profile unpacks (`Cr24` <uuid>.tmp), left behind
  when the browser stops before it is done;
- scratchpad: the folders of this repository's Claude Code sessions (<temp>/claude/<project>/<session>/)
  whose session ended: no running process in any ~/.claude*/sessions/<pid>.json (nor $CLAUDE_CONFIG_DIR's)
  names it; without any such file no session counts as ended. A session resumed later finds it empty.

Only what nothing wrote into for --hours (scratchpads: --session-hours) is removed. Junctions and symbolic
links inside (a regression test's cache/ is a junction to the real cache) are removed as links, never
followed: Windows PowerShell 5.1's `Remove-Item -Recurse` would delete what they point to.

    uv run tools/clean_temp.py              # what it would remove, by kind, with sizes
    uv run tools/clean_temp.py -v           # ... and every path
    uv run tools/clean_temp.py --delete     # removes it
"""

import argparse
import glob
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass

import psutil

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KINDS = ("regression", "ui-shots", "browser", "scratchpad")
UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
CRX_MAGIC = b"Cr24"  # the first bytes of a Chromium extension package (CRX3)


@dataclass
class Item:
    kind: str
    path: str
    bytes: int
    newest: float  # the latest modification inside, seconds since the epoch


def _is_link(path: str) -> bool:
    return os.path.islink(path) or os.path.isjunction(path)


def scan(path: str) -> tuple[int, float]:
    """Bytes and the latest modification time of a file or a folder; links are neither followed nor counted."""
    if _is_link(path):
        return 0, 0.0
    st = os.stat(path)
    if not stat.S_ISDIR(st.st_mode):
        return st.st_size, st.st_mtime
    size, newest, stack = 0, st.st_mtime, [path]
    while stack:
        try:
            with os.scandir(stack.pop()) as entries:
                for entry in entries:
                    try:
                        # a junction is no symlink to is_symlink() and a folder to is_dir(follow_symlinks=False)
                        if entry.is_junction() or entry.is_symlink():
                            continue
                        st = entry.stat(follow_symlinks=False)
                        newest = max(newest, st.st_mtime)
                        if entry.is_dir(follow_symlinks=False):
                            stack.append(entry.path)
                        else:
                            size += st.st_size
                    except OSError:
                        pass
        except OSError:
            pass
    return size, newest


def remove(path: str) -> list[str]:
    """Removes a file or a folder; links inside are removed as links (shutil.rmtree follows no junction
    since Python 3.8), read-only files made writable first. The paths it could not remove (in use)."""
    failed = []

    def retry(function, name, error):
        try:
            if function is os.path.islink:  # a symbolic link to a folder (rmtree of Python 3.12): the link only
                os.unlink(name)
            else:
                os.chmod(name, stat.S_IWRITE)
                function(name)
        except OSError:
            failed.append(name)

    if _is_link(path) or not os.path.isdir(path):
        try:
            os.unlink(path)
        except OSError as error:
            retry(os.unlink, path, error)
    else:
        shutil.rmtree(path, onexc=retry)
    return failed


def config_dirs() -> list[str]:
    """Claude Code's config folders: every ~/.claude* folder and $CLAUDE_CONFIG_DIR."""
    folders = glob.glob(os.path.join(os.path.expanduser("~"), ".claude*"))
    if os.environ.get("CLAUDE_CONFIG_DIR"):
        folders.append(os.environ["CLAUDE_CONFIG_DIR"])
    return sorted({os.path.abspath(f) for f in folders if os.path.isdir(f)})


def live_sessions(configs: list[str]) -> set[str] | None:
    """The ids of the sessions whose process runs, from the config folders' sessions/<pid>.json; None
    when there is no such file at all (nothing is known, so no session counts as ended)."""
    files = [p for folder in configs for p in glob.glob(os.path.join(folder, "sessions", "*.json"))]
    if not files:
        return None
    live = set()
    for path in files:
        try:
            with open(path, encoding="utf-8") as f:
                info = json.load(f)
            session, pid, started = info["sessionId"], int(info["pid"]), info["startedAt"] / 1000
        except (OSError, ValueError, KeyError, TypeError):
            continue
        try:
            # a process started after the session did has taken over the pid of an ended one
            if psutil.Process(pid).create_time() <= started + 1:
                live.add(session)
        except psutil.AccessDenied:  # another user's process: rather alive
            live.add(session)
        except psutil.Error:
            pass
    return live


def project_name() -> str:
    """The folder name Claude Code gives this repository's main checkout ("C:\\a\\b-c" -> "C--a-b-c");
    the names of its worktrees' folders go on with "--claude-worktrees-<name>"."""
    main = REPO
    try:
        common = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=REPO,
                                capture_output=True, text=True, check=True).stdout.strip()
        main = os.path.dirname(os.path.normpath(common))
    except (OSError, subprocess.CalledProcessError):
        pass
    return re.sub(r"[^A-Za-z0-9]", "-", main)


def _kind(entry: os.DirEntry) -> str | None:
    """The kind of a leftover directly in the temporary folder, or None."""
    if entry.is_junction() or entry.is_symlink():
        return None
    if entry.is_dir():
        if entry.name.startswith("findaline-regression-"):
            return "regression"
        if entry.name.startswith("ui-shots-"):
            return "ui-shots"
    elif entry.name.endswith(".tmp") and UUID.match(entry.name[:-4]):
        try:
            with open(entry.path, "rb") as f:
                return "browser" if f.read(len(CRX_MAGIC)) == CRX_MAGIC else None
        except OSError:  # still being written
            return None
    return None


def find(temp: str, project: str, configs: list[str], now: float, hours: float, session_hours: float,
         kinds=KINDS) -> list[Item]:
    """What to remove: the leftovers of `kinds` nothing wrote into for `hours`, and the scratchpads of
    `project`'s ended sessions nothing wrote into for `session_hours`."""
    items = []
    with os.scandir(temp) as entries:
        for entry in entries:
            kind = _kind(entry)
            if kind in kinds:
                size, newest = scan(entry.path)
                if now - newest >= hours * 3600:
                    items.append(Item(kind, entry.path, size, newest))
    root = os.path.join(temp, "claude")
    live = live_sessions(configs) if "scratchpad" in kinds and os.path.isdir(root) else None
    if live is None:
        return items
    name = project.lower()
    for folder in os.scandir(root):
        if not (folder.name.lower() == name or folder.name.lower().startswith(name + "--claude-worktrees-")):
            continue
        if folder.is_junction() or folder.is_symlink() or not folder.is_dir():
            continue
        for session in os.scandir(folder.path):
            if (not UUID.match(session.name) or session.name in live or session.is_junction()
                    or session.is_symlink() or not session.is_dir()):
                continue
            size, newest = scan(session.path)
            if now - newest >= session_hours * 3600:
                items.append(Item("scratchpad", session.path, size, newest))
    return items


def _gb(n: int) -> str:
    return f"{n / 2**30:.2f} GB"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0].strip(),
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--delete", action="store_true", help="remove them (default: only list them)")
    parser.add_argument("--hours", type=float, default=2,
                        help="the test and browser leftovers nothing wrote into for this long (default 2)")
    parser.add_argument("--session-hours", type=float, default=24,
                        help="the scratchpads of ended sessions nothing wrote into for this long (default 24)")
    parser.add_argument("--only", default=",".join(KINDS), help="of these kinds (comma-separated; default all)")
    parser.add_argument("-v", "--verbose", action="store_true", help="every path, with its size")
    parser.add_argument("--temp", default=tempfile.gettempdir(), help="the temporary folder (default: the system's)")
    args = parser.parse_args(argv)
    kinds = [k for k in args.only.split(",") if k]
    unknown = set(kinds) - set(KINDS)
    if unknown:
        parser.error(f"unknown kinds: {', '.join(sorted(unknown))} (of {', '.join(KINDS)})")
    configs = config_dirs()
    items = find(args.temp, project_name(), configs, time.time(), args.hours, args.session_hours, kinds)
    if "scratchpad" in kinds and live_sessions(configs) is None:
        print("scratchpads left alone: no sessions/<pid>.json in " + (", ".join(configs) or "any ~/.claude*"))
    total = freed = 0
    failed = []
    for kind in kinds:
        mine = sorted((i for i in items if i.kind == kind), key=lambda i: i.newest)
        if not mine:
            continue
        size = sum(i.bytes for i in mine)
        total += size
        latest = time.strftime("%Y-%m-%d %H:%M", time.localtime(mine[-1].newest))
        print(f"{kind:11s} {len(mine):5d}  {_gb(size):>10s}  (latest written {latest})", flush=True)
        for item in mine:
            if args.verbose:
                print(f"    {_gb(item.bytes):>10s}  {item.path}", flush=True)
            if args.delete:
                left = remove(item.path)
                failed += left
                if not left:
                    freed += item.bytes
    if args.delete:
        print(f"removed {_gb(freed)} of {_gb(total)}")
        if failed:
            print(f"{len(failed)} paths could not be removed (in use?), e.g.:\n    " + "\n    ".join(failed[:5]))
    else:
        print(f"total {_gb(total)}: nothing removed, --delete removes it")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
