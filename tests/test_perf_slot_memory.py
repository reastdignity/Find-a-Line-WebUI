"""tools/perf_slot_memory.py: its parts that need no search (the sampler of a process tree, finding the search's
process below a launcher, the sums of a sample, the stages, the unique sets plus the hand-over files once). The
search itself runs by hand (docs/performance.md, "The memory constant")."""

import os
import subprocess
import sys
import time

import psutil
import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "tools"))

import perf_slot_memory as psm  # noqa: E402

SLEEPER = "import time; time.sleep(30)"


@pytest.fixture
def tree():
    """A launcher-like process (its command line holds --child) with the 'search' below it (--child too) and two
    'saving children' below that."""
    inner = (f"import subprocess, sys, time; kids = [subprocess.Popen([sys.executable, '-c', {SLEEPER!r}]) "
             f"for _ in range(2)]; time.sleep(30)")
    outer = (f"import subprocess, sys, time; subprocess.Popen([sys.executable, '-c', {inner!r}, '{psm.CHILD}', "
             f"'search']); time.sleep(30)")
    root = subprocess.Popen([sys.executable, "-c", outer, psm.CHILD, "launcher"])
    proc = psutil.Process(root.pid)
    for _ in range(200):  # until the search and its two children run (a venv's python.exe may add launchers)
        search = psm.find_search(proc)
        p = psutil.Process(search) if search else None
        if p and "search" in p.cmdline() and len(p.children(recursive=True)) >= 2:
            break
        time.sleep(0.1)
    yield proc
    for p in proc.children(recursive=True) + [proc]:
        try:
            p.kill()
        except psutil.Error:
            pass
    root.wait()


def test_sampler_follows_the_tree(tree):
    rows = psm.sample(tree, uss=True)
    pids = [r[0] for r in rows]
    assert pids[0] == tree.pid and set(pids) == {tree.pid} | {p.pid for p in tree.children(recursive=True)}
    assert len(rows) >= 4 and all(r[1] > 0 for r in rows)  # every working set read
    assert all(0 < r[3] <= r[1] for r in rows)  # the unique set within the working set
    assert all(r[3] == 0 for r in psm.sample(tree))  # without --uss: none read
    search = psm.find_search(tree)
    p = psutil.Process(search)
    assert "search" in p.cmdline() and psm.CHILD in p.cmdline()  # not the launcher above it
    assert not any(psm.CHILD in c.cmdline() for c in p.children(recursive=True))  # the lowest one
    t = psm.totals(rows, search)
    assert t["processes"] == len(rows) and t["rss"] == sum(r[1] for r in rows)
    assert t["main_rss"] == next(r[1] for r in rows if r[0] == search)
    assert t["children_rss"] == sum(r[1] for r in rows[1:] if r[0] != search)  # the root (a launcher) apart


def test_sums_stages_and_the_hand_over_once():
    mb = psm.MB
    events = [(10.0, "search start"), (11.0, "Step 3/5: evaluating anchor pairs | Compute anchor pairs"),
              (12.0, "HOOK saving.save start"), (12.5, "Step 5/5: saving the run and the map | Compute saving results"),
              (14.0, "HOOK linestore.write start")]
    assert psm.stage_at(events, 9.0) == "before the search's first event"
    assert psm.stage_at(events, 12.6).startswith("Step 5/5") and psm.stage_at(events, 14.0).startswith("HOOK lines")
    assert psm.stage_key("HOOK linestore.write start") == "HOOK linestore.write"
    assert psm.stage_key("Tile 2/9 · Step 3/5: evaluating anchor pairs | Compute anchor pairs") == \
        "Step 3/5: evaluating anchor pairs"

    def totals(rss, uss, main, kids):
        return {"rss": rss * mb, "private": rss * mb, "uss": uss * mb, "main_rss": main * mb, "main_private": main * mb,
                "children_rss": kids * mb, "children_private": 10 * mb, "processes": 5}
    # four children map a hand-over of 300 MB: their working sets count it four times, their unique sets not at all
    series = [(11.5, totals(900, 800, 900, 0), 20000 * mb), (13.0, totals(2600, 700, 1000, 1600), 23000 * mb),
              (14.5, totals(1300, 1250, 1300, 0), 21000 * mb)]
    out = psm.summarise(series, events, 300 * mb, uss=True)
    assert out["peak_tree_rss_mb"] == 2600 and out["peak_tree_rss_at"].startswith("Step 5/5")
    assert out["peak_tree_uss_mb"] == 1250 and out["peak_tree_uss_at"] == "HOOK linestore.write start"
    assert out["tree_uss_at_rss_peak_mb"] == 700 and out["uss_plus_handover_mb"] == 1000  # 700 + 300 once
    assert out["handover_mb"] == 300 and out["peak_used_mb"] == 23000 and out["used_start_mb"] == 20000
    assert out["stage_peaks_mb"]["Step 5/5: saving the run and the map"] == [2600, 2600, 1000, 10, 700]
    assert out["stage_peaks_mb"]["HOOK linestore.write"][0] == 1300
    assert "uss_plus_handover_mb" not in psm.summarise(series, events, 300 * mb, uss=False)
    assert psm.uss_plus_handover(5, None) == 5 and psm.summarise([], events, None, True) == {}


def test_option():
    args = ["--lat", "50", "--data-dir", "C:/x", "--radius"]
    assert psm.option(args, "--data-dir") == "C:/x" and psm.option(args, "--radius") is None
    assert psm.option(args, "--name") is None
