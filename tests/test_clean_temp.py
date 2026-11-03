"""tools/clean_temp.py: what it finds in a temporary folder, and that it removes links, never what they point to."""

import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
import clean_temp  # noqa: E402

PROJECT = "C--repos-Find-a-Line"
LIVE, ENDED, RECENT, WORKTREE, OTHER = (f"{n:08x}-0000-4000-8000-000000000000" for n in range(1, 6))


def link(target, path):
    """A directory link as tests/regression.py makes it (a junction on Windows)."""
    if os.name == "nt":
        import _winapi
        _winapi.CreateJunction(str(target), str(path))
    else:
        os.symlink(target, path)


def write(path, content=b"x" * 100):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(content)


def age(path, hours):
    """Files and folders under path as last written `hours` ago (links left alone)."""
    when = time.time() - hours * 3600
    if os.path.isfile(path):
        os.utime(path, (when, when))
    folders = []
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if not clean_temp._is_link(os.path.join(root, d))]
        folders.append(root)
        for name in files:
            os.utime(os.path.join(root, name), (when, when))
    for folder in reversed(folders):  # after their files, the deepest first
        os.utime(folder, (when, when))


def make_temp(tmp_path):
    """A temporary folder with one of each kind, old and new, and a real cache outside it."""
    cache = tmp_path / "real-cache"
    write(cache / "LAYOUT", b"layout")
    temp = tmp_path / "temp"
    old = temp / "findaline-regression-old"
    write(old / "R1" / "runs" / "lines.csv")
    link(cache, old / "R1" / "cache")
    write(temp / "findaline-regression-new" / "R13" / "output.log")
    write(temp / "ui-shots-old" / "jobs.sqlite")
    write(temp / f"{LIVE}.tmp", b"Cr24" + b"\0" * 200)  # an extension package
    write(temp / f"{ENDED}.tmp", b"PK\3\4")  # a .tmp of the same name that is no package
    write(temp / "unrelated" / "file.txt")
    claude = temp / "claude"
    for project, session in ((PROJECT, LIVE), (PROJECT, ENDED), (PROJECT, RECENT),
                             (PROJECT + "--claude-worktrees-x", WORKTREE), ("C--repos-Other", OTHER)):
        write(claude / project / session / "scratchpad" / "data.bin")
    for path in temp.iterdir():
        age(path, 30)
    age(temp / "findaline-regression-new", 0.5)
    age(claude / PROJECT / RECENT, 10)
    return temp, cache


def registry(tmp_path, sessions):
    """A config folder whose sessions/<pid>.json name the sessions: (id, started) of this process's pid."""
    folder = tmp_path / ".claude-test"
    for k, (session, started) in enumerate(sessions):
        write(folder / "sessions" / f"{k}.json",
              json.dumps({"pid": os.getpid(), "sessionId": session, "startedAt": started * 1000}).encode())
    os.makedirs(folder, exist_ok=True)
    return str(folder)


def test_find_and_remove(tmp_path):
    temp, cache = make_temp(tmp_path)
    # LIVE started after this process did: its session; ENDED before it did: this process only reuses its pid
    configs = [registry(tmp_path, [(LIVE, time.time()), (ENDED, 0)])]
    items = clean_temp.find(str(temp), PROJECT, configs, time.time(), hours=2, session_hours=24)
    found = sorted((i.kind, os.path.relpath(i.path, temp)) for i in items)
    assert found == [("browser", f"{LIVE}.tmp"),
                     ("regression", "findaline-regression-old"),
                     ("scratchpad", os.path.join("claude", PROJECT + "--claude-worktrees-x", WORKTREE)),
                     ("scratchpad", os.path.join("claude", PROJECT, ENDED)),
                     ("ui-shots", "ui-shots-old")]
    regression = next(i for i in items if i.kind == "regression")
    assert regression.bytes == 100  # the cache behind the link not counted
    for item in items:
        assert clean_temp.remove(item.path) == []
        assert not os.path.exists(item.path)
    assert (cache / "LAYOUT").read_bytes() == b"layout"  # the junction removed, not what it points to
    left = sorted(p.name for p in temp.iterdir())
    assert left == [f"{ENDED}.tmp", "claude", "findaline-regression-new", "unrelated"]
    assert sorted(p.name for p in (temp / "claude" / PROJECT).iterdir()) == [LIVE, RECENT]
    assert (temp / "claude" / "C--repos-Other" / OTHER).exists()


def test_kinds_hours_and_no_registry(tmp_path):
    temp, _ = make_temp(tmp_path)
    now = time.time()
    # no sessions/<pid>.json anywhere: no session is known to have ended, so no scratchpad is removed
    items = clean_temp.find(str(temp), PROJECT, [str(tmp_path / "nothing")], now, hours=2, session_hours=24)
    assert {i.kind for i in items} == {"browser", "regression", "ui-shots"}
    configs = [registry(tmp_path, [(LIVE, now)])]
    items = clean_temp.find(str(temp), PROJECT, configs, now, hours=0.25, session_hours=5, kinds=("regression",
                                                                                                    "scratchpad"))
    assert sorted(os.path.basename(i.path) for i in items) == [
        ENDED, RECENT, WORKTREE, "findaline-regression-new", "findaline-regression-old"]


def test_dry_run_removes_nothing(tmp_path, capsys):
    temp, _ = make_temp(tmp_path)
    before = sorted(p.name for p in temp.iterdir())
    assert clean_temp.main(["--temp", str(temp), "--only", "regression,browser,ui-shots"]) == 0
    out = capsys.readouterr().out
    assert re.search(r"^regression\s+1\s", out, re.M) and "nothing removed" in out
    assert sorted(p.name for p in temp.iterdir()) == before
    assert clean_temp.main(["--temp", str(temp), "--only", "regression", "--delete"]) == 0
    assert not (temp / "findaline-regression-old").exists() and (temp / "ui-shots-old").exists()
