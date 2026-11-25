"""
Run by hand: the access grid's memory and seconds (docs/performance.md, "The access grid's memory"; the task "An
access grid that needs less memory"). It imports search and access and changes neither.

    uv run tools/perf_access.py <command> --out <folder> --name <name> [--cores N] [--memory BYTES] ...
                                -- <findaline.py options, with --data-dir>

Options before "--" are the tool's, after it findaline.py's (--no-plot, --yes and --ortho never are added). --memory
BYTES makes search.available_memory answer that, before the search is planned (as tools/perf_profile.py): the budget
of the access grid (search._access_budget: a search planned without limits takes the memory free) and the tiles of an
area without --tile-size. --cores N pins the process to N cores (one per physical core while there are enough) and
numba's threads to N, before numba is imported. Every command writes <out>/<name>.json and prints a table. The search's
work folder is <data-dir>/work/perf-access-<name>, made new and removed at the end (--keep-work keeps it).

Commands:
- plan: the search planned, no elevation data read: the grid's pixels, the tiles, the estimate's download and work
  folder (search.estimate_search), what search.access_memory asks, the budget, and what the rule gives (at once,
  blocks of which side, or the mark left out), with the disk free under the data folder.
- stages: step 1 (search.prepare_data, in strips for a tiled plan), then the access grid by access.access_grid
  ("once") and by access.block_grid with the rule's block side ("blocks"), in the order of --order (default
  "once,blocks"; "blocks,once,blocks" gives the blocks straight after step 1 as a search makes them, then after the
  grid at once as docs/performance.md's figures of 2026-11-15 were made); --step1-only stops after step 1. A sidecar
  process samples this process every 20 ms (numba's kernels hold the GIL: a thread here could not): the working set
  and the private bytes (Windows' commit; on Linux RssAnon of /proc, with RssFile beside), in a container also the
  cgroup's memory.current and from memory.stat anon, file, file_mapped and file_dirty, and the work folder's files.
  Reported per part above the stage's start: step 1 per progress bar; the grid-wide pass split into the whole-metre
  sample, the water's copy, the flat lakes (mask, labels, bounds, percentiles, write), the open ground and its
  smoothed twin (mask, labels, write); every block (its window's pixels, from the end of the block before to the end
  of its own measure: the window's reads, the measure and the previous block's write); the seconds, the samples and
  their longest gap, bytes per pixel of the grid (grid-wide) and of the largest window (blocks), the work folder's
  files at each part's peak and its own peak on disk. The split comes from wrapping access.py's private functions
  of today's pass (looked up by name; those missing are listed under "hooks" and the split is coarser); the grid at
  once and the blocks are compared pixel by pixel ("differ").
  "blocks" is the grid as the search makes it (search._access_grid): on a tree whose block_grid takes `needed`
  (E, wave 2b) the search area is passed as the search passes it (Data.mask; nothing with Data.partner), so the blocks
  left out (access.NOT_COMPUTED, 255) are in the stage's seconds and memory; its JSON has the blocks computed
  ("blocks"), those left out ("left_out") and the pixels left out, and the area's blocks' table apart as the part
  "needed". The grid at once against it by rule (a), as the search reads it ("rule_a", also "compare_with_once"):
  0 pixels differ where a block was computed, no pixel of the area is 255, and the 255s are exactly the blocks left
  out. "full" (an --order entry of its own) is block_grid without `needed`, every block, not split and not to be
  read for seconds: rule (b), "rule_b", compares it with the grid at once at every pixel.
  The columns since the masks are bits (wave 2b, access._Mask: read and written by file calls, never mapped): the
  masks' pages are no longer in the process's working set, so "WS" (the working set above the stage's start, the
  rule's measure) and "WS less private" (the file pages) no longer hold them: they lie in the system's file cache,
  which no column of the process shows. Their size is kept apart: the mark's files on disk per pixel of the grid
  (the work folder's peak less its size at the stage's start, from the sidecar's listings), in the pass and in the
  blocks ("needed": mark_files_pass_b_per_px, mark_files_blocks_b_per_px); on Linux the cgroup's file pages beside.
- pieces: step 1, then the real grid-wide pass (access.block_grid, stopped before its first block) with
  access._region_areas wrapped: per mask (flat, open ground, smoothed open ground) the pieces ndimage.label gives
  strip by strip with the pass's strips (total, most in one strip, most labels in a strip's last row), and the
  regions of today's labels; the share of pixels with heights and of the search area; per strip the share of its
  width inside the span of columns with heights (its rows and access.HALO rows each side) grown by access.HALO
  columns each side (mean, and the share of strips without heights: F); the share of blocks whose core holds a pixel
  of the search area (Data.mask: E) for the rule's block side and 2, 4 and 8 km; --anchors: the share holding an
  anchor (each tile's anchors as search._estimate_tiles finds them: E2). --capture DIR keeps the pass's final masks
  (<name>-water.npy, -og.npy, -og2.npy) for `masks`, and each mask as its regions are found, always as bool .npy
  (a tree that keeps its masks as bits has them unpacked: mask_as_bool).
- masks: one mask kept three ways, each in a fresh child process: "memmap" (a memory-mapped bool .npy, as the pass
  keeps it today; one mapping open over all windows, as block_grid), "bits" (one bit per pixel, np.packbits by row,
  in the process's own memory), "file" (a plain uint8 file written and read with file calls, never mapped). Each
  written in strips, then read window by window in the block layout (--block-px and access.margin_px(--res)): the
  peak working set and private bytes above the child's start (sampled every 20 ms, and the OS's own peak counters),
  the seconds of writing and reading (the windows' hashing apart), the bytes kept; the windows' hashes of the three
  ways compared. The mask: --mask PATH (a .npy of `pieces --capture`) or --made-up H W (random, seeded per strip).
- compare: step 1, the grid at once and the grid in blocks, the pixels that differ (and the first few, as row and
  column); --files A B compares two saved grids instead.

Measure one command at a time under the test lock's --exclusive (docs/workflow.md): the working sets follow what else
the machine holds.
"""

import argparse
import dataclasses
import gc
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import threading
import time
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np
import psutil

# The code measured: this checkout's, or another checkout's (PERF_ACCESS_REPO: a tree of before, measured by this
# file's code; its modules first on the path)
HERE = os.environ.get("PERF_ACCESS_REPO") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

INTERVAL = 0.02  # seconds between samples
MB = 2 ** 20
STRIP_PX = 4_000_000  # access.STRIP_PX's value: the strips of `masks` when access.py is not imported (its children)
HALO = 16  # access.HALO's value, the same use
BLOCK_KM = (0.5, 1, 2, 4, 8)  # pieces: the blocks' sides of E (and E2) besides the rule's
CGROUP = "/sys/fs/cgroup"
PROC = "/proc"
# access.py's private functions of today's grid-wide pass that `stages` wraps for its split and `pieces` for the
# masks; a name missing (a later access.py) is listed under "hooks" and its part is not split
# (until gate 0: _region_areas, _region_bounds and the label files; since wave 1 of 2026-11-24: _Regions' sweeps,
# _spread_large for B)
# (wave 2b: _blocks_needed, the search area's blocks, before the pass)
HOOKS = ("_whole_metres_rows", "_flat_lakes_rows", "_region_areas", "_region_bounds", "_spread_flat",
         "_open_ground_rows", "_answers", "_Regions.__init__", "_Regions._backward", "_Regions.visit",
         "_spread_large", "_Regions._label", "_blocks_needed")
NOT_COMPUTED = 255  # access.NOT_COMPUTED (wave 2b): a pixel of a block left out
GROUPS = {"access_flat.npy": "flat lakes", "access_og_g.npy": "open ground", "access_og2_g.npy": "smoothed open ground",
          "access_og.npy": "open ground", "access_og2.npy": "smoothed open ground"}
# access._answers' parameters as the per-block hook mirrors them (another signature: the blocks are not split)
ANSWERS_PARAMETERS = ["z", "water", "data", "res", "wm", "og", "alpine", "og2", "s"]


# ---------------------------------------------------------------- readers (no search needed)

def strips(h: int, w: int, strip_px: int = STRIP_PX):
    """The strips of rows of access._strips: about strip_px pixels, at least 64 rows."""
    rows = max(64, strip_px // max(w, 1))
    for r0 in range(0, h, rows):
        yield r0, min(h, r0 + rows)


# cgroup v1 (Docker Desktop on WSL2 here) under the v2 names: usage_in_bytes is memory.current, max_usage_in_bytes
# memory.peak; memory.stat's hierarchical totals rss, cache, mapped_file, dirty, shmem are anon, file, file_mapped,
# file_dirty, shmem
V1_STAT = {"total_rss": "anon", "total_cache": "file", "total_mapped_file": "file_mapped", "total_dirty": "file_dirty",
           "total_shmem": "shmem"}


def _read_int(path: str) -> Optional[int]:
    try:
        with open(path) as f:
            text = f.read().strip()
        return -1 if text == "max" else int(text)
    except (OSError, ValueError):
        return None


def _cgroup_kind(root: str) -> Optional[Tuple[int, str]]:
    """(2, folder) for cgroup v2's memory files in root, (1, folder) for v1's in root/memory or root; None."""
    if os.path.exists(os.path.join(root, "memory.current")):
        return 2, root
    for folder in (os.path.join(root, "memory"), root):
        if os.path.exists(os.path.join(folder, "memory.usage_in_bytes")):
            return 1, folder
    return None


def cgroup_sample(root: str = CGROUP) -> Optional[Dict[str, int]]:
    """The container's cgroup memory now (bytes), under cgroup v2's names: current, peak and from memory.stat anon,
    file, file_mapped, file_dirty, shmem (v1: V1_STAT); "v" the version; None outside a cgroup with memory files."""
    kind = _cgroup_kind(root)
    if kind is None:
        return None
    version, folder = kind
    current = _read_int(os.path.join(folder, "memory.current" if version == 2 else "memory.usage_in_bytes"))
    if current is None:
        return None
    out = {"v": version, "current": current}
    peak = _read_int(os.path.join(folder, "memory.peak" if version == 2 else "memory.max_usage_in_bytes"))
    if peak is not None:
        out["peak"] = peak
    names = {k: k for k in ("anon", "file", "file_mapped", "file_dirty", "shmem")} if version == 2 else V1_STAT
    try:
        with open(os.path.join(folder, "memory.stat")) as f:
            for line in f:
                key, _, value = line.partition(" ")
                if key in names:
                    out[names[key]] = int(value)
    except (OSError, ValueError):
        pass
    return out


def cgroup_events(root: str = CGROUP) -> Optional[Dict[str, int]]:
    """The cgroup's events and limit: v2 memory.events (low, high, max, oom, oom_kill) and memory.max; v1
    memory.oom_control's under_oom and oom_kill, limit_in_bytes as memory.max (an unlimited v1 cgroup reads about
    9.2e18), and two counts of charges that met a limit: "failcnt" (memory.failcnt: the memory limit's) and
    "memsw.failcnt" (memory.memsw.failcnt: memory and swap together). With --memory-swap equal to --memory (no swap,
    as compose.yaml) the memory-and-swap limit is met first, so memory.failcnt stays 0 and memsw.failcnt counts the
    squeeze (measured at gate 0: 0 and 2 459 237 under a limit of 1.17 GB); None outside a cgroup."""
    kind = _cgroup_kind(root)
    if kind is None:
        return None
    version, folder = kind
    name = "memory.events" if version == 2 else "memory.oom_control"
    try:
        with open(os.path.join(folder, name)) as f:
            out = {k: int(v) for k, v in (line.split() for line in f if line.strip())}
    except (OSError, ValueError):
        out = {}
    out["v"] = version
    if version == 1:
        out["failcnt"] = _read_int(os.path.join(folder, "memory.failcnt"))
        out["memsw.failcnt"] = _read_int(os.path.join(folder, "memory.memsw.failcnt"))
    limit = _read_int(os.path.join(folder, "memory.max" if version == 2 else "memory.limit_in_bytes"))
    if limit is not None:
        out["memory.max"] = limit
    return out


def proc_status(pid, root: str = PROC) -> Optional[Dict[str, int]]:
    """RssAnon, RssFile and VmHWM (the peak resident set) of /proc/<pid>/status in bytes; None without /proc."""
    try:
        with open(os.path.join(root, str(pid), "status")) as f:
            out = {}
            for line in f:
                key, _, value = line.partition(":")
                if key in ("RssAnon", "RssFile", "VmHWM", "VmRSS"):
                    out[key] = int(value.split()[0]) * 1024
            return out
    except (OSError, ValueError, IndexError):
        return None


def memory_now(proc: psutil.Process) -> Dict[str, Optional[int]]:
    """A process's memory now: rss (working set), private (Windows' private bytes; on Linux RssAnon), file (Linux
    RssFile), and the OS's lifetime peaks (Windows peak_wset, peak_pagefile; Linux VmHWM)."""
    m = proc.memory_info()
    out = {"rss": m.rss, "private": getattr(m, "private", None), "file": None,
           "os_peak_rss": getattr(m, "peak_wset", None), "os_peak_private": getattr(m, "peak_pagefile", None)}
    status = proc_status(proc.pid) if os.name != "nt" else None
    if status:
        out["private"], out["file"] = status.get("RssAnon"), status.get("RssFile")
        out["os_peak_rss"] = status.get("VmHWM")
    return out


def work_files(work: str) -> Dict[str, int]:
    """The work folder's files (path below it: bytes), its subfolders too; files that vanish meanwhile left out."""
    out = {}
    for folder, _, names in os.walk(work):
        for name in names:
            path = os.path.join(folder, name)
            try:
                out[os.path.relpath(path, work).replace("\\", "/")] = os.path.getsize(path)
            except OSError:
                pass
    return out


# ---------------------------------------------------------------- the sidecar sampler

SAMPLE_KEYS = ("t", "rss", "private", "file", "cg_current", "cg_anon", "cg_file", "cg_mapped", "cg_dirty", "disk")


def sampler_main(argv: Sequence[str]):
    """The sidecar: samples process `pid` every INTERVAL into a JSON-lines file until the stop file exists or the
    process ends: {"m": [SAMPLE_KEYS values]} per sample and {"t": .., "files": {...}} whenever the work folder's
    files change. Its own affinity is every CPU (it must not take the measured process's cores)."""
    pid, out_path, stop_path, work = int(argv[0]), argv[1], argv[2], argv[3]
    try:
        psutil.Process().cpu_affinity([])
    except (psutil.Error, AttributeError, ValueError):
        pass
    proc = psutil.Process(pid)
    last_files = None
    with open(out_path, "w", encoding="utf-8") as f:
        tick = time.time()
        while not os.path.exists(stop_path):
            t = time.time()
            try:
                m = memory_now(proc)
            except psutil.Error:
                break
            cg = cgroup_sample() or {}
            files = work_files(work) if work else {}
            f.write(json.dumps({"m": [t, m["rss"], m["private"], m["file"], cg.get("current"), cg.get("anon"),
                                      cg.get("file"), cg.get("file_mapped"), cg.get("file_dirty"),
                                      sum(files.values())]}) + "\n")
            if files != last_files:
                f.write(json.dumps({"t": t, "files": files}) + "\n")
                last_files = files
            tick += INTERVAL
            time.sleep(max(0.0, tick - time.time()))


class Sidecar:
    """The sampler process of this process (sampler_main) and its records once stopped."""

    def __init__(self, folder: str, work: str):
        os.makedirs(folder, exist_ok=True)
        self.out = os.path.join(folder, f"samples-{os.getpid()}.jsonl")
        self.stop_path = self.out + ".stop"
        for p in (self.out, self.stop_path):
            if os.path.exists(p):
                os.remove(p)
        self.proc = subprocess.Popen([sys.executable, os.path.abspath(__file__), "_sampler", str(os.getpid()),
                                      self.out, self.stop_path, work])
        for _ in range(200):  # until its first sample
            if os.path.exists(self.out) and os.path.getsize(self.out):
                break
            time.sleep(0.05)

    def stop(self, keep: bool = False) -> Tuple[List[List], List[Tuple[float, Dict[str, int]]]]:
        """(samples, listings of the work folder), both in time order; the files removed (keep: the samples' file
        stays, for a run whose end is not reached or read)."""
        open(self.stop_path, "w").close()
        try:
            self.proc.wait(30)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        samples, listings = [], []
        with open(self.out, encoding="utf-8") as f:
            for line in f:
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue  # a line cut by a kill
                if "m" in rec:
                    samples.append(rec["m"])
                else:
                    listings.append((rec["t"], rec["files"]))
        for p in (self.stop_path,) if keep else (self.out, self.stop_path):
            os.remove(p)
        return samples, listings


# ---------------------------------------------------------------- parts from samples

def _above(value, base):
    return None if value is None or base is None else value - base


def summarise(samples: Sequence[Sequence], listings, events: Sequence[Tuple[float, str]], t_end: float,
              base: Dict[str, Optional[int]], cg_base: Optional[Dict[str, int]]) -> Dict[str, Dict]:
    """Per label (events: (t, label), the part running from then on until the next event or t_end): its seconds,
    samples and the longest gap between samples (from the part's start to its end), the peak working set and private
    bytes above the stage's start (base), the work folder's files at the working set's peak and the folder's own
    peak on disk, in a container the cgroup's peak above its start with memory.stat's split there. A part without a
    sample has no peaks (None) and no files ("no sample" in the table), never another part's sample."""
    i = {k: n for n, k in enumerate(SAMPLE_KEYS)}
    lt = [t for t, _ in listings]
    out: Dict[str, Dict] = {}
    for k, (t0, label) in enumerate(events):
        t1 = events[k + 1][0] if k + 1 < len(events) else t_end
        if t1 < t0:
            continue
        inside = [s for s in samples if t0 <= s[0] <= t1]
        row = out.setdefault(label, {"s": 0.0, "samples": 0, "max_gap_s": 0.0, "peak_rss": None, "peak_private": None,
                                     "peak_disk": None})
        row["s"] += t1 - t0
        row["samples"] += len(inside)
        edges = [t0] + [s[0] for s in inside] + [t1]
        row["max_gap_s"] = max(row["max_gap_s"], max(b - a for a, b in zip(edges, edges[1:])))
        if not inside:
            continue
        top = max(inside, key=lambda s: s[i["rss"]] or 0)
        if row["peak_rss"] is None or top[i["rss"]] > row["peak_rss"]:
            row["peak_rss"] = top[i["rss"]]
            j = _bisect(lt, top[0])
            row["files_at_peak"] = listings[j][1] if j >= 0 else {}
            row["peak_at_s"] = round(top[0] - t0, 2)
        priv = [s[i["private"]] for s in inside if s[i["private"]] is not None]
        if priv:
            row["peak_private"] = max(row["peak_private"] or 0, max(priv))
            # the working set less the private bytes (Windows: private bytes are commit, so a lower bound of the
            # file pages resident; it shows them apart from private pages faulted back after an emptied start)
            fp = max(s[i["rss"]] - s[i["private"]] for s in inside if s[i["private"]] is not None)
            row["peak_ws_less_private"] = fp if row.get("peak_ws_less_private") is None else max(
                row["peak_ws_less_private"], fp)
        row["peak_disk"] = max(row["peak_disk"] or 0, max(s[i["disk"]] or 0 for s in inside))
        cgs = [s for s in inside if s[i["cg_current"]] is not None]
        if cgs:
            c = max(cgs, key=lambda s: s[i["cg_current"]])
            if row.get("cg_peak") is None or c[i["cg_current"]] > row["cg_peak"]:
                row["cg_peak"] = c[i["cg_current"]]
                row["cg_split_at_peak"] = {"anon": c[i["cg_anon"]], "file": c[i["cg_file"]],
                                           "file_mapped": c[i["cg_mapped"]], "file_dirty": c[i["cg_dirty"]]}
    for row in out.values():
        row["s_raw"] = row["s"]  # the event times' own difference, unrounded (sums of parts are judged on these)
        row["s"] = round(row["s"], 3)
        row["max_gap_s"] = round(row["max_gap_s"], 3)
        row["peak_rss_above_start"] = _above(row.pop("peak_rss"), base.get("rss"))
        row["peak_private_above_start"] = _above(row.pop("peak_private"), base.get("private"))
        if "peak_ws_less_private" in row:
            start_fp = (base["rss"] - base["private"]) if base.get("private") is not None else None
            row["peak_ws_less_private_above_start"] = _above(row.pop("peak_ws_less_private"), start_fp)
        if "cg_peak" in row:
            row["cg_peak_above_start"] = _above(row["cg_peak"], (cg_base or {}).get("current"))
    return out


def _bisect(times: Sequence[float], t: float) -> int:
    """The index of the last time at or before t (-1: none)."""
    import bisect
    return bisect.bisect_right(times, t) - 1


def merge(parts: Dict[str, Dict], prefix: str) -> Optional[Dict]:
    """The parts whose label starts with prefix as one: seconds and samples summed, the peaks the largest."""
    rows = [r for label, r in parts.items() if label.startswith(prefix)]
    if not rows:
        return None
    # a part without a sample never wins, also when every sampled peak lies below the stage's start (negative)
    best = max(rows, key=lambda r: float("-inf") if r["peak_rss_above_start"] is None else r["peak_rss_above_start"])
    out = {"s": round(sum(r["s"] for r in rows), 3), "samples": sum(r["samples"] for r in rows),
           "max_gap_s": max(r["max_gap_s"] for r in rows),
           "peak_rss_above_start": best["peak_rss_above_start"],
           "peak_private_above_start": max((r["peak_private_above_start"] for r in rows
                                            if r["peak_private_above_start"] is not None), default=None),
           "peak_disk": max((r["peak_disk"] for r in rows if r["peak_disk"] is not None), default=None),
           "peak_part": next(label for label, r in parts.items() if r is best),
           "files_at_peak": best.get("files_at_peak", {})}
    cgs = [r for r in rows if r.get("cg_peak") is not None]
    if cgs:
        c = max(cgs, key=lambda r: r["cg_peak"])
        out.update(cg_peak=c["cg_peak"], cg_peak_above_start=c.get("cg_peak_above_start"),
                   cg_split_at_peak=c["cg_split_at_peak"])
    return out


SCRATCH_FILES = ("access_regions.bin", "access_bits.bin")


def file_peaks(listings, t0: float, t1: float, pixels: int) -> Dict:
    """The largest size each scratch file of the pass (SCRATCH_FILES) reached during a stage, as the sidecar's
    listings of the work folder saw it (a listing at every change, sampled every 20 ms: a file that lived under 20 ms
    may be missed), in bytes and per pixel of the grid."""
    out = {}
    for t, files in listings:
        if t0 <= t <= t1:
            for name in SCRATCH_FILES:
                if name in files:
                    out[name] = max(out.get(name, 0), files[name])
    return {name: {"bytes": b, "b_per_px": round(b / pixels, 4)} for name, b in out.items()}


def per_px(value: Optional[int], pixels: Optional[int]) -> Optional[float]:
    return None if value is None or not pixels else round(value / pixels, 2)


# ---------------------------------------------------------------- pure counts (pieces, shares, compare)

def strip_pieces(mask, strip_rows: Sequence[Tuple[int, int]]) -> Dict[str, int]:
    """The pieces ndimage.label (8 neighbours) gives a mask strip by strip: their total, the most in one strip and the
    most labels in a strip's last row (the pieces a strip hands to the next across the seam)."""
    from scipy import ndimage
    total = most = last = 0
    for r0, r1 in strip_rows:
        labels, n = ndimage.label(np.asarray(mask[r0:r1], bool), structure=np.ones((3, 3), bool))
        total += n
        most = max(most, n)
        if r1 < mask.shape[0]:  # the grid's last row hands nothing on
            row = labels[-1]
            last = max(last, int(np.unique(row[row > 0]).size))
    return {"pieces": int(total), "most_in_a_strip": int(most), "most_in_a_last_row": int(last),
            "strips": len(strip_rows)}


def data_shares(z, mask, strip_rows: Sequence[Tuple[int, int]], halo: int = HALO, water=None,
                filled=None) -> Dict[str, float]:
    """The share of pixels with heights (finite z: the search's filled terrain, the sea's fill included) and of the
    search area (mask, None: not counted); per strip the share of its width inside the span of columns with heights
    in its rows and `halo` rows each side, grown by `halo` columns each side and clipped to the grid: their mean over
    the strips and the share of strips without heights. The same for the land: the measure's data (access._data_rows'
    `data` with the search's inputs: heights, not a filled pixel unless water) that is not the search's water (the
    flat lakes of float heights not taken off: on float heights a superset of the open-ground passes' mask). Also the
    share of pixels with that data at all (with_own_data) and of the pixels filled from other data (filled: the
    search's filled pixels, Data.filled_pixels)."""
    h, w = z.shape
    counts = {"heights": 0, "land": 0, "own_data": 0, "filled": 0}
    widths = {"heights": [], "land": []}
    area = 0

    def kinds(r0, r1):
        zz = np.asarray(z[r0:r1], np.float32)
        finite = np.isfinite(zz)
        wet = np.asarray(water[r0:r1], bool) if water is not None else np.zeros(zz.shape, bool)
        fill = np.asarray(filled[r0:r1], bool) if filled is not None else np.zeros(zz.shape, bool)
        data = finite & ~(fill & ~wet)
        return {"heights": finite, "land": data & ~wet, "own_data": data, "filled": fill}

    for r0, r1 in strip_rows:
        own = kinds(r0, r1)
        for k in counts:
            counts[k] += int(own[k].sum())
        if mask is not None:
            area += int(np.count_nonzero(np.asarray(mask[r0:r1])))
        a, b = max(0, r0 - halo), min(h, r1 + halo)
        around = kinds(a, b)
        for k in widths:
            cols = np.flatnonzero(around[k].any(axis=0))
            if not cols.size:
                widths[k].append(None)
                continue
            lo, hi = max(0, int(cols[0]) - halo), min(w, int(cols[-1]) + 1 + halo)
            widths[k].append((hi - lo) / w)
    n = len(strip_rows)
    out = {"pixels": h * w, "strips": n}
    for k, name in (("heights", "heights"), ("land", "land")):
        got = [x or 0.0 for x in widths[k]]
        out[f"with_{name}"] = round(counts[k] / (h * w), 4)
        out[f"strip_width_with_{name}_mean"] = round(float(np.mean(got)), 4) if n else 0.0
        out[f"strips_without_{name}"] = round(sum(x is None for x in widths[k]) / n, 4) if n else 0.0
    out["with_own_data"] = round(counts["own_data"] / (h * w), 4)
    out["filled"] = round(counts["filled"] / (h * w), 4)
    if mask is not None:
        out["search_area"] = round(area / (h * w), 4)
    return out


def blocks_holding(mask, block_px: int) -> Dict[str, float]:
    """The blocks of block_px (as access.block_grid lays them, from the grid's corner) whose core holds a pixel of
    mask: their count, of how many, and the share."""
    h, w = mask.shape
    starts = np.arange(0, w, block_px)
    held = total = 0
    for r0 in range(0, h, block_px):
        cols = np.zeros(w, bool)
        for a in range(r0, min(h, r0 + block_px), 2048):  # rows in pieces: a memory-mapped mask is read once
            cols |= np.asarray(mask[a:min(h, r0 + block_px, a + 2048)], bool).any(axis=0)
        held += int(np.logical_or.reduceat(cols, starts).sum())
        total += len(starts)
    return {"block_px": int(block_px), "blocks": total, "holding": held, "share": round(held / total, 4)}


def blocks_holding_points(rows: np.ndarray, cols: np.ndarray, shape, block_px: int) -> Dict[str, float]:
    """The blocks of block_px whose core holds one of the points (rows, cols): their count and share."""
    h, w = shape
    nr, nc = -(-h // block_px), -(-w // block_px)
    held = np.unique((rows // block_px) * nc + cols // block_px).size if len(rows) else 0
    return {"block_px": int(block_px), "blocks": nr * nc, "holding": int(held), "share": round(held / (nr * nc), 4)}


def compare_grids(a, b, first: int = 5) -> Dict:
    """The pixels where two grids of the same shape differ, row by row in pieces: their count and the first few
    (row, column)."""
    if a.shape != b.shape:
        raise ValueError(f"the grids differ in shape: {a.shape} and {b.shape}")
    h, w = a.shape
    count, where = 0, []
    for r0, r1 in strips(h, w):
        d = np.asarray(a[r0:r1]) != np.asarray(b[r0:r1])
        n = int(d.sum())
        if n and len(where) < first:
            rr, cc = np.nonzero(d)
            where += [[int(r + r0), int(c)] for r, c in zip(rr[:first - len(where)], cc[:first - len(where)])]
        count += n
    return {"differ": count, "first": where, "pixels": h * w}


def compare_rule_a(once, blocks, area, first: int = 5) -> Dict:
    """Rule (a), the grid in blocks as the search reads it: against the grid at once (None: not compared) only where
    a block was computed (not NOT_COMPUTED), and the pixels NOT_COMPUTED, those of them in the search area (`area`,
    bool or None: not counted) and the grid at once's own NOT_COMPUTED values (none expected: a value it never
    holds). "differ" counts the computed pixels that differ; the rule holds when it and "left_out_in_area" are 0."""
    h, w = blocks.shape
    if once is not None and once.shape != blocks.shape:
        raise ValueError(f"the grids differ in shape: {once.shape} and {blocks.shape}")
    count, where, left, in_area, once_255 = 0, [], 0, 0, 0
    for r0, r1 in strips(h, w):
        b = np.asarray(blocks[r0:r1])
        off = b == NOT_COMPUTED
        left += int(off.sum())
        if area is not None:
            in_area += int((off & np.asarray(area[r0:r1], bool)).sum())
        if once is not None:
            o = np.asarray(once[r0:r1])
            once_255 += int((o == NOT_COMPUTED).sum())
            d = (o != b) & ~off
            n = int(d.sum())
            if n and len(where) < first:
                rr, cc = np.nonzero(d)
                where += [[int(r + r0), int(c)] for r, c in zip(rr[:first - len(where)], cc[:first - len(where)])]
            count += n
    return {"rule": "a", "differ": count if once is not None else None, "first": where, "pixels": h * w,
            "computed_px": h * w - left, "left_out_px": left,
            "left_out_in_area": in_area if area is not None else None, "once_not_computed": once_255}


def mask_as_bool(path: str, shape: Tuple[int, int]) -> np.ndarray:
    """A mask file of the pass as a bool grid of `shape`: a bool (or 0/1 uint8) .npy as it is, a .npy of packed bits
    (wave 2b's access._Mask: uint8 rows of ceil(w / 8) bytes, np.packbits by row) unpacked."""
    h, w = int(shape[0]), int(shape[1])
    a = np.load(path)
    if a.shape == (h, w):
        return a.astype(bool, copy=False)
    if a.dtype == np.uint8 and a.shape == (h, -(-w // 8)):
        return np.unpackbits(a, axis=1, count=w).view(bool)
    raise ValueError(f"{path}: {a.dtype} {a.shape} is neither a mask of {shape} nor its bits")


def save_bool(dest: str, rows: Callable[[int, int], np.ndarray], shape: Tuple[int, int]) -> None:
    """A bool .npy of `shape` written strip by strip from rows(r0, r1) with file calls (never mapped)."""
    h, w = int(shape[0]), int(shape[1])
    with open(dest, "wb") as f:
        np.lib.format.write_array_header_1_0(f, {"descr": "|b1", "fortran_order": False, "shape": (h, w)})
        for r0, r1 in strips(h, w):
            f.write(np.ascontiguousarray(rows(r0, r1), bool).tobytes())


# ---------------------------------------------------------------- masks: three ways, each in a child process

def windows(h: int, w: int, block_px: int, margin: int):
    """The windows of access.block_grid's blocks: (a, b, c, d) rows a..b, columns c..d."""
    for r0 in range(0, h, block_px):
        for c0 in range(0, w, block_px):
            r1, c1 = min(h, r0 + block_px), min(w, c0 + block_px)
            yield max(0, r0 - margin), min(h, r1 + margin), max(0, c0 - margin), min(w, c1 + margin)


def npy_layout(path: str) -> Tuple[Tuple[int, int], np.dtype, int]:
    """(shape, dtype, offset of the data) of a C-ordered .npy file."""
    with open(path, "rb") as f:
        version = np.lib.format.read_magic(f)
        reader = np.lib.format.read_array_header_1_0 if version == (1, 0) else np.lib.format.read_array_header_2_0
        shape, fortran, dtype = reader(f)
        if fortran:
            raise ValueError(f"{path}: a Fortran-ordered array")
        return tuple(shape), dtype, f.tell()


class MaskSource:
    """The rows of the mask a child writes: a .npy read with file calls (never mapped, so its pages stay out of the
    child's working set), or made up (random, seeded per strip: the same rows for every way)."""

    def __init__(self, path: Optional[str], made_up: Optional[Sequence[int]], seed: int = 7):
        self.path, self.seed = path, seed
        if path:
            self.shape, dtype, self.offset = npy_layout(path)
            if dtype.itemsize != 1:
                raise ValueError(f"{path}: a mask of one byte a pixel expected, not {dtype}")
            self.file = open(path, "rb", buffering=0)
        else:
            self.shape = (int(made_up[0]), int(made_up[1]))

    def rows(self, r0: int, r1: int) -> np.ndarray:
        h, w = self.shape
        if self.path:
            out = np.empty((r1 - r0, w), np.uint8)
            self.file.seek(self.offset + r0 * w)
            self.file.readinto(memoryview(out).cast("B"))
            return out.view(bool) if out.max(initial=0) <= 1 else out != 0
        rng = np.random.default_rng(self.seed + r0)
        return rng.random((r1 - r0, w)) < 0.3


class Peaks:
    """A thread sampling this process every INTERVAL: the peak working set and private bytes since reset."""

    def __init__(self):
        self.proc = psutil.Process()
        self.peak = {"rss": 0, "private": 0}
        self.stopped = threading.Event()
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def run(self):
        while not self.stopped.wait(INTERVAL):
            m = memory_now(self.proc)
            for k in self.peak:
                if m[k] is not None:
                    self.peak[k] = max(self.peak[k], m[k])

    def stop(self):
        self.stopped.set()
        self.thread.join()


def mask_child(way: str, spec: Dict) -> Dict:
    """One way of keeping a mask (memmap, bits, file): written in strips, read window by window; memory and seconds
    above this process's start, the bytes kept and each window's hash."""
    src = MaskSource(spec.get("mask"), spec.get("made_up"))
    h, w = src.shape
    block, margin = int(spec["block_px"]), int(spec["margin"])
    path = os.path.join(spec["work"], f"mask-{way}-{os.getpid()}" + (".npy" if way == "memmap" else ".bin"))
    proc = psutil.Process()
    gc.collect()
    start = memory_now(proc)
    peaks = Peaks()
    hashing = 0.0
    hashes = []
    t0 = time.perf_counter()
    if way == "memmap":
        out = np.lib.format.open_memmap(path, mode="w+", dtype=bool, shape=(h, w))
        for r0, r1 in strips(h, w):
            out[r0:r1] = src.rows(r0, r1)
        out.flush()
        del out
        kept = os.path.getsize(path)
    elif way == "bits":
        packed = np.empty((h, (w + 7) // 8), np.uint8)
        for r0, r1 in strips(h, w):
            packed[r0:r1] = np.packbits(src.rows(r0, r1), axis=1)
        kept = packed.nbytes
    elif way == "file":
        with open(path, "wb", buffering=0) as f:
            for r0, r1 in strips(h, w):
                f.write(memoryview(np.ascontiguousarray(src.rows(r0, r1), dtype=np.uint8)).cast("B"))
        kept = os.path.getsize(path)
    else:
        raise ValueError(f"unknown way {way!r}")
    t1 = time.perf_counter()
    write_peak = dict(peaks.peak)
    if way == "memmap":
        grid = np.load(path, mmap_mode="r")  # one mapping over every window, as block_grid keeps its masks
    elif way == "file":
        f = open(path, "rb", buffering=0)
    count = 0
    for a, b, c, d in windows(h, w, block, margin):
        if way == "memmap":
            win = np.array(grid[a:b, c:d])
        elif way == "bits":
            b0 = c // 8
            win = np.ascontiguousarray(np.unpackbits(packed[a:b, b0:(d + 7) // 8], axis=1)[:, c - 8 * b0:d - 8 * b0])
            win = win.view(bool)
        else:
            win = np.empty((b - a, d - c), np.uint8)
            for k, r in enumerate(range(a, b)):
                f.seek(r * w + c)
                f.readinto(memoryview(win[k]).cast("B"))
            win = win.view(bool)
        th = time.perf_counter()
        hashes.append(hashlib.sha1(np.ascontiguousarray(win).view(np.uint8)).hexdigest()[:16])
        hashing += time.perf_counter() - th
        count += win.size
        del win
    t2 = time.perf_counter()
    if way == "memmap":
        del grid
    elif way == "file":
        f.close()
    peaks.stop()
    end = memory_now(proc)
    if way == "bits":
        del packed
    if way != "bits":
        gc.collect()
        os.remove(path)
    out = {"way": way, "shape": [h, w], "kept_bytes": int(kept), "kept_bytes_per_px": round(kept / (h * w), 4),
           "lives": {"memmap": "a memory-mapped bool .npy in the work folder (its pages in the working set as read)",
                     "bits": "np.packbits by row, in the process's own memory (private bytes)",
                     "file": "a plain uint8 file in the work folder, os file calls (the system's file cache)"}[way],
           "write_s": round(t1 - t0, 3), "read_s": round(t2 - t1 - hashing, 3), "hash_s": round(hashing, 3),
           "windows": len(hashes), "window_px_read": count,
           "write_peak_rss_above_start": write_peak["rss"] - start["rss"],
           "peak_rss_above_start": max(peaks.peak["rss"], end["rss"]) - start["rss"],
           "peak_private_above_start": (max(peaks.peak["private"], end["private"] or 0) - start["private"]
                                        if start["private"] is not None else None),
           "os_peak_rss_above_start": (end["os_peak_rss"] - start["rss"]) if end["os_peak_rss"] else None,
           "os_peak_private_above_start": ((end["os_peak_private"] - start["private"])
                                           if end["os_peak_private"] and start["private"] is not None else None),
           "hashes": hashes}
    headline(out)
    return out


def headline(m: Dict) -> Dict:
    """A way's headline peaks: the larger of the 20 ms thread's sample and the OS's own peak counter above the
    child's start (a fresh process: the counter is exact; the thread waits for the GIL and misses short peaks, as
    the bits way's two window copies). The thread's own figures stay as sampled_*. Works on a record of before too."""
    for key in ("rss", "private"):
        sampled = m.get(f"sampled_peak_{key}_above_start", m.get(f"peak_{key}_above_start"))
        m[f"sampled_peak_{key}_above_start"] = sampled
        os_peak = m.get(f"os_peak_{key}_above_start")
        values = [v for v in (sampled, os_peak) if v is not None]
        m[f"peak_{key}_above_start"] = max(values) if values else None
    return m


def run_masks(args) -> Dict:
    """The three ways, each in a fresh child process, and the comparison of their windows."""
    if not args.mask and not args.made_up:
        raise SystemExit("masks: give --mask PATH or --made-up H W")
    work = os.path.abspath(args.work or os.path.join(args.out, f"{args.name}-masks"))
    os.makedirs(work, exist_ok=True)
    margin = int(math.ceil((MARGIN_M() + 6 * args.res) / args.res))
    spec = {"mask": os.path.abspath(args.mask) if args.mask else None, "made_up": args.made_up,
            "block_px": args.block_px, "margin": margin, "work": work}
    ways = {}
    for way in ("memmap", "bits", "file"):
        done = subprocess.run([sys.executable, os.path.abspath(__file__), "_mask-child", way, json.dumps(spec)],
                              capture_output=True, text=True, encoding="utf-8")
        if done.returncode:
            raise SystemExit(f"the child of {way} failed:\n{done.stderr}")
        ways[way] = json.loads(done.stdout.strip().splitlines()[-1])
    first = ways["memmap"]["hashes"]
    equal = all(ways[k]["hashes"] == first for k in ways)
    unequal = {k: next((n for n, (x, y) in enumerate(zip(ways[k]["hashes"], first)) if x != y), None)
               for k in ways if ways[k]["hashes"] != first}
    for k in ways:
        ways[k]["hash_of_hashes"] = hashlib.sha1("".join(ways[k].pop("hashes")).encode()).hexdigest()[:16]
    if not os.listdir(work):
        os.rmdir(work)
    shape = ways["memmap"]["shape"]
    return {"command": "masks", "mask": spec["mask"], "made_up": args.made_up, "shape": shape, "res": args.res,
            "block_px": args.block_px, "margin_px": margin, "windows_equal": equal,
            "first_unequal_window": unequal, "ways": ways}


def MARGIN_M() -> float:
    """access.MARGIN_M without importing access (numba) into the parent of `masks`: REACH_M + STAND_M + 30."""
    return 500.0 + 3.0 + 30.0


# ---------------------------------------------------------------- the search's side

class Search:
    """A planned search of the tool's findaline options, its work folder and step 1."""

    def __init__(self, args, emit=None):
        import cache
        import params as pm
        import search
        self.search = search
        # the names patched for this search, restored by close() (a second search in the process starts clean)
        self._patched = {name: getattr(search, name) for name in ("available_memory", "ACCESS_AREA_BYTES",
                                                                  "_access_budget")}
        if args.memory:
            search.available_memory = lambda: int(args.memory)  # before plan_search: _check_access and the tiles
        self.area_fixed = int(getattr(args, "area_fixed", None) or 0)
        if getattr(args, "area_bytes", None) is not None:  # the rule with another per-pixel constant, this run only
            search.ACCESS_AREA_BYTES = float(args.area_bytes)
        if self.area_fixed:  # and a fixed term: the budget less it, for the check and for the blocks' side
            real_budget = search._access_budget
            search._access_budget = lambda plan: real_budget(plan) - self.area_fixed
        searches, options = pm.parse_cli(list(args.search) + ["--no-plot", "--yes", "--ortho", "never"])
        if len(searches) != 1:
            raise SystemExit("one search only")
        self.params = searches[0]
        if not self.params.access:
            raise SystemExit("the search needs --access")
        data_dir = cache.data_dir(options.data_dir)
        self.work = os.path.join(data_dir, "work", f"perf-access-{args.name}")
        if os.path.exists(self.work):
            shutil.rmtree(self.work)
        os.makedirs(self.work)
        self.events: List[str] = []
        self.data = None
        try:
            self.plan = search.plan_search(self.params, search.Paths(data_dir, self.work),
                                           emit or (lambda kind, text: self.events.append(str(text))), reach=True)
        except BaseException:
            self.close()
            raise

    @property
    def pixels(self) -> int:
        return self.plan.grid.width * self.plan.grid.height

    def rule(self) -> Dict:
        """What the access rule makes of this plan with its budget (search._access_budget)."""
        import access
        s, plan = self.search, self.plan
        margin = access.margin_px(plan.resolution)
        block = s._access_block_px(plan)
        out = {"budget": int(s._access_budget(plan)), "access_memory": int(s.access_memory(plan)),
               "access_skipped": plan.access_skipped, "at_once": block is None, "block_px": block,
               "margin_px": margin, "ACCESS_AREA_BYTES": s.ACCESS_AREA_BYTES, "area_fixed": self.area_fixed,
               "ACCESS_WINDOW_BYTES": s.ACCESS_WINDOW_BYTES, "ACCESS_DISK_BYTES": s.ACCESS_DISK_BYTES}
        if self.area_fixed:
            out["budget"] += self.area_fixed  # the budget given; the rule's check used it less the fixed term
            out["access_memory"] += self.area_fixed
        if block:
            h, w = plan.grid.height, plan.grid.width
            out["blocks"] = (-(-h // block)) * (-(-w // block))
            out["block_m"] = block * plan.resolution
            out["window_px_max"] = min(h, block + 2 * margin) * min(w, block + 2 * margin)
            # what the rule counts for this search in blocks: the constant per pixel of the grid, the fixed term and
            # the window bytes per pixel of its window
            out["counts_bytes"] = int(s.ACCESS_AREA_BYTES * self.pixels + self.area_fixed
                                      + s.ACCESS_WINDOW_BYTES * out["window_px_max"])
        return out

    def describe(self) -> Dict:
        plan = self.plan
        tiles = plan.tiles or []
        largest = max((t for _, t in tiles), key=lambda t: t.width * t.height, default=None)
        return {"grid": [plan.grid.height, plan.grid.width], "grid_px": self.pixels, "res": plan.resolution,
                "source": plan.source.id,
                "tiles": len(tiles), "largest_tile_px": largest.width * largest.height if largest else None,
                "box_km": [round(plan.grid.width * plan.resolution / 1000, 2),
                           round(plan.grid.height * plan.resolution / 1000, 2)]}

    def step1(self):
        self.data = self.search.prepare_data(self.plan, strips=bool(self.plan.tiles))
        return self.data

    def inputs(self):
        """access's inputs, as search._access_grid gives them."""
        d = self.data
        return d.elevation, d.water, self.plan.resolution, d.filled_pixels()

    def needed(self):
        """block_grid's `needed` as search._access_grid passes it (wave 2b, E): the search area (Data.mask), nothing
        with partner anchors beyond the outline (Data.partner)."""
        d = self.data
        return d.mask if getattr(d, "partner", None) is None else None

    def close(self, keep: bool = False):
        self.data = None
        for name, value in getattr(self, "_patched", {}).items():
            setattr(self.search, name, value)
        gc.collect()
        if not keep:
            for _ in range(50):
                try:
                    shutil.rmtree(self.work)
                    return
                except FileNotFoundError:
                    return
                except PermissionError:
                    gc.collect()
                    time.sleep(0.1)


def _owner(module, name: str):
    """(the object holding `name`, its attribute): a module function, or "Class.method" of a class in the module."""
    if "." in name:
        cls, attr = name.split(".", 1)
        return getattr(module, cls, None), attr
    return module, name


def _lookup(module, name: str):
    owner, attr = _owner(module, name)
    return getattr(owner, attr, None) if owner is not None else None


class Marks:
    """The labels of the parts against time (time.time(), the sidecar's clock), and the hooks into access.py."""

    def __init__(self):
        self.events: List[Tuple[float, str]] = []
        self.restore: List[Tuple[str, Callable]] = []
        self.windows: List[int] = []
        self.found: List[str] = []
        self.readings: Dict[str, Dict] = {}  # label: this process's memory when the part starts (the blocks')
        self.large: List[Dict] = []
        self.counts: Dict[str, Dict] = {}
        self.labels_dtypes = set()
        self.proc = psutil.Process()

    def mark(self, label: str, reading: bool = False):
        if reading:
            self.readings[label] = memory_now(self.proc)
        self.events.append((time.time(), label))

    def hook(self, access):
        """Wrap the grid-wide pass's functions and the blocks' _answers: each only switches the label (no argument is
        kept: a kept view of a memory-mapped mask would hold its file on Windows). Two trees, one cut (wave 2a's
        brief, fixed before any number): per pass (flat lakes, open ground, smoothed open ground)
        - "mask": from the pass function's entry to the regions' start;
        - "regions": the base's _region_areas ("regions: labels"; the lakes also _region_bounds, "regions: bounds"),
          S's _Regions.__init__ (its forward sweep with the writes, "regions: forward", and its backward sweep,
          "regions: backward");
        - "after": from the regions' end to the pass function's exit (the base: the write, its flush and the
          removals, the lakes' percentiles; S: the visits, the close, the removal, the lakes' gather in
          _spread_flat with _spread_large apart as "after: B", and the last writes).
        The rest of the pass as before: the whole-metre sample, the water's copy, "masks opened". On S also counted
        per pass: the records and the regions' scratch file (at _Regions.__init__'s end), the visits' windows and the
        pixels they label again, the questions answered in the sweep and those left (at _spread_flat), and B's
        regions and passes (sources.filling._select's reads). Names are looked up; one missing is left out of
        "hooks". (Wave 1's tree, e6d8489c, is no longer served by this cut.)"""
        self.found = [n for n in HOOKS if callable(_lookup(access, n))]
        self.large = []  # B: per large region its pixels, strips, passes, the visits' windows, seconds
        self.counts = {}  # S: per pass its records, scratch bytes, visits' windows and pixels, questions
        self.labels_dtypes = set()  # S: the dtypes of the strips' labels _Regions._label returned
        state = {"in_b": False}

        def wrap(name, enter=None, leave=None):
            owner, attr = _owner(access, name)
            real = getattr(owner, attr, None) if owner is not None else None
            if not callable(real):
                return

            def hooked(*a, **k):
                if enter:
                    label = enter(a, k)
                    if label:
                        self.mark(label)
                try:
                    return real(*a, **k)
                finally:
                    if leave:
                        label = leave(a, k)
                        if label:
                            self.mark(label)
            self.restore.append((name, real))
            setattr(owner, attr, hooked)

        def group(a, k):
            return GROUPS.get(os.path.basename(str(a[0] if a else k.get("mask_path"))), "mask")

        def of_mask(mask):  # a _Mask's pass: its file
            return GROUPS.get(os.path.basename(str(getattr(mask, "path", ""))), "mask")

        def of_regions(a, k):  # a _Regions method's group: its mask's file
            return GROUPS.get(os.path.basename(str(getattr(getattr(a[0], "mask", None), "path", ""))), "mask")

        def og(a, k):
            name = a[6] if len(a) > 6 else k.get("name")
            return "smoothed open ground" if name == "og2" else "open ground"

        def count(g):
            return self.counts.setdefault(g, {"records": 0, "record_bytes": 0, "scratch_bytes": 0, "visits": 0,
                                              "visit_px": 0, "b_visits": 0, "b_visit_px": 0})

        def regions_leave(a, k):  # S: the regions found; their records and scratch file counted
            regions = a[0]
            c = count(of_regions(a, k))
            c["records"] += int(sum(m for _, m in getattr(regions, "_records", [])))
            c["record_bytes"] = c["records"] * 4 * int(getattr(access, "_REC", 8))
            try:
                c["scratch_bytes"] = max(c["scratch_bytes"], os.path.getsize(regions.path))
            except OSError:
                pass
            c["questions"] = len(regions.questions["pixels"])
            return f"grid-wide: {of_regions(a, k)}: after: visits"

        regions_cls = getattr(access, "_Regions", None)

        def spread_enter(a, k):
            # S: (regions, z, keep, done): the questions answered in the sweep and those left; the base's is
            # (labels, z, regions, count, keep), its labels a map
            if regions_cls is not None and isinstance(a[0] if a else None, regions_cls):
                done = a[3]
                c = count("flat lakes")
                c["questions_in_sweep"], c["questions_left"] = int(done.sum()), int((~done).sum())
                return "grid-wide: flat lakes: after: gather"
            return "grid-wide: flat lakes: after: percentiles"

        def large_enter(a, k):
            regions, q = a[0], a[2] if len(a) > 2 else k["q"]
            qs = regions.questions
            self.large.append({"pixels": int(qs["pixels"][q]), "strips": int(qs["last"][q] - qs["first"][q] + 1),
                               "passes": 0, "visits": 0, "visit_px": 0, "t0": time.time()})
            state["in_b"] = True
            return "grid-wide: flat lakes: after: B"

        def large_leave(a, k):
            row = self.large[-1]
            row["s"] = round(time.time() - row.pop("t0"), 3)
            state["in_b"] = False
            return "grid-wide: flat lakes: after: gather"

        wrap("_whole_metres_rows", leave=lambda a, k: "grid-wide: water (copy, flush)")
        wrap("_flat_lakes_rows", enter=lambda a, k: "grid-wide: flat lakes: mask",
             leave=lambda a, k: "grid-wide: water (copy, flush)")
        wrap("_open_ground_rows", enter=lambda a, k: f"grid-wide: {og(a, k)}: mask",
             leave=lambda a, k: "grid-wide: masks opened")
        # the base (1c8c839f): the labels file and the bounds
        wrap("_region_areas", enter=lambda a, k: f"grid-wide: {group(a, k)}: regions: labels",
             leave=lambda a, k: (f"grid-wide: {group(a, k)}: regions: bounds" if group(a, k) == "flat lakes"
                                 else f"grid-wide: {group(a, k)}: after: write"))
        wrap("_region_bounds", enter=lambda a, k: "grid-wide: flat lakes: regions: bounds",
             leave=lambda a, k: "grid-wide: flat lakes: after: write")
        # S (wave 2a): _Regions.__init__ = the forward sweep with its writes, then the backward sweep
        wrap("_Regions.__init__", enter=lambda a, k: f"grid-wide: {of_mask(a[1] if len(a) > 1 else k['mask'])}: "
                                                     "regions: forward", leave=regions_leave)
        wrap("_Regions._backward", enter=lambda a, k: f"grid-wide: {of_regions(a, k)}: regions: backward")
        wrap("_spread_large", enter=large_enter, leave=large_leave)
        wrap("_spread_flat", enter=spread_enter, leave=lambda a, k: "grid-wide: flat lakes: after: write")
        # E (wave 2b): the search area's blocks, read before the pass: a part of the stage of its own
        wrap("_blocks_needed", enter=lambda a, k: "needed: the search area's blocks")
        owner, attr = _owner(access, "_Regions._label")
        real_label = getattr(owner, attr, None) if owner is not None else None
        if callable(real_label):
            def hooked_label(regions, s):  # the labels' type as the regions really use it, observed per call
                got = real_label(regions, s)
                self.labels_dtypes.add(str(got[0].dtype))
                return got
            self.restore.append(("_Regions._label", real_label))
            setattr(owner, attr, hooked_label)
        owner, attr = _owner(access, "_Regions.visit")
        real_visit = getattr(owner, attr, None) if owner is not None else None
        if callable(real_visit):
            def hooked_visit(regions, s, records):  # a generator: each window counted as it is handed on
                g = GROUPS.get(os.path.basename(str(getattr(getattr(regions, "mask", None), "path", ""))), "mask")
                c = count(g)
                for item in real_visit(regions, s, records):
                    px = (item[1] - item[0]) * (item[3] - item[2])
                    if state["in_b"]:
                        c["b_visits"] += 1
                        c["b_visit_px"] += px
                        self.large[-1]["visits"] += 1
                        self.large[-1]["visit_px"] += px
                    else:
                        c["visits"] += 1
                        c["visit_px"] += px
                    yield item
                    del item
            self.restore.append(("_Regions.visit", real_visit))
            setattr(owner, attr, hooked_visit)
        try:  # B's passes: each read of the region's heights by the selection
            from sources import filling
        except ImportError:
            filling = None
        real_select = getattr(filling, "_select", None)
        if callable(real_select) and callable(getattr(access, "_spread_large", None)):
            def hooked_select(chunks, *a, **k):
                if not state["in_b"] or state.get("selecting"):  # a call _select makes of itself: counted already
                    return real_select(chunks, *a, **k)

                def counted():
                    self.large[-1]["passes"] += 1
                    yield from chunks()
                state["selecting"] = True
                try:
                    return real_select(counted, *a, **k)
                finally:
                    state["selecting"] = False
            self.restore.append(("_select", real_select))
            filling._select = hooked_select
            self._filling = filling
        real_answers = getattr(access, "_answers", None)
        if callable(real_answers):
            import inspect
            if list(inspect.signature(real_answers).parameters) != ANSWERS_PARAMETERS:
                self.found = [n for n in self.found if n != "_answers"]  # another signature: no per-block parts
                return

            def hooked_answers(z, water, data, res, wm, og, alpine, og2=None, s=None):
                # the windows of the open ground are handed on without a reference of this frame (popped from a
                # list into the call): _answers' own `del og` / `del og2` free them as in a call without the hook
                self.windows.append(int(z.shape[0] * z.shape[1]))
                box = [s, og2, og]
                del og, og2, s
                try:
                    return real_answers(z, water, data, res, wm, box.pop(), alpine, og2=box.pop(), s=box.pop())
                finally:
                    self.mark(f"blocks: block {len(self.windows) + 1}", reading=True)
            self.restore.append(("_answers", real_answers))
            access._answers = hooked_answers

    def unhook(self, access):
        for name, real in reversed(self.restore):
            if name == "_select":
                self._filling._select = real
                continue
            owner, attr = _owner(access, name)
            setattr(owner, attr, real)
        self.restore.clear()


def set_cores(cores: Optional[int]) -> Dict:
    """Pin this process to `cores` cores (one logical CPU per physical core while there are enough, as
    tools/perf_profile.py) and numba to as many threads; before numba is imported."""
    if cores:
        n = psutil.cpu_count()
        step = 2 if 2 * cores <= n and psutil.cpu_count(False) < n else 1
        psutil.Process().cpu_affinity(list(range(0, step * cores, step)))
        os.environ["NUMBA_NUM_THREADS"] = str(cores)
    import numba
    if cores:
        numba.set_num_threads(min(cores, numba.config.NUMBA_NUM_THREADS))
    try:
        affinity = psutil.Process().cpu_affinity()
    except (psutil.Error, AttributeError):
        affinity = None
    return {"cores": cores, "affinity": affinity, "numba_threads": numba.get_num_threads(),
            "cpu_count": psutil.cpu_count(), "platform": sys.platform}


def warm_up():
    """access_grid once on a small made-up grid: numba's kernels compiled or loaded from their cache before a timed
    stage (whole metres and float heights: every kernel)."""
    import access
    rng = np.random.default_rng(3)
    z = (np.cumsum(rng.normal(0, 1, (120, 120)), axis=0) * 3 + 100).astype(np.float32)
    access.access_grid(z, None, 5.0)
    access.access_grid(np.round(z), None, 5.0)


def empty_working_set() -> Optional[Dict]:
    """Windows: the process's working set emptied (psapi.EmptyWorkingSet): every page leaves it, file pages and
    private ones (those fault back when touched). Returns the memory before and after; None elsewhere."""
    if os.name != "nt":
        return None
    import ctypes
    from ctypes import wintypes
    proc = psutil.Process()
    before = memory_now(proc)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    # the pseudo-handle of this process is (HANDLE)-1: typed, or ctypes passes a 32-bit int and the call fails
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    kernel32.K32EmptyWorkingSet.argtypes = [wintypes.HANDLE]
    kernel32.K32EmptyWorkingSet.restype = wintypes.BOOL
    done = bool(kernel32.K32EmptyWorkingSet(kernel32.GetCurrentProcess()))
    return {"done": done, "error": 0 if done else ctypes.get_last_error(), "before": before,
            "after": memory_now(proc)}


def run_stage(s: Search, sidecar_events: Marks, kind: str, k: int, access, block_px: Optional[int],
              empty_start: bool = False, keep_grid: Optional[str] = None) -> Dict:
    """One stage of `stages` ("once" or "blocks"): its result and the grid's file. empty_start: the working set
    emptied just before the start reading (a start that holds none of the files the stage reads)."""
    z, water, res, filled = s.inputs()
    out = {"stage": kind, "run": k, "grid_px": s.pixels, "window_bytes": s.search.ACCESS_WINDOW_BYTES}
    proc = psutil.Process()
    gc.collect()
    if empty_start:
        out["emptied"] = empty_working_set()
        if out["emptied"] is not None and not out["emptied"]["done"]:
            raise RuntimeError(f"EmptyWorkingSet failed (error {out['emptied']['error']})")
    out["start"] = memory_now(proc)
    out["cg_start"] = cgroup_sample()
    out["work_bytes_at_start"] = sum(work_files(s.work).values())  # step 1's grids (and earlier stages' outputs)
    t0 = time.time()
    if kind == "once":
        sidecar_events.mark(f"once {k}")
        grid = access.access_grid(z, water, res, filled, alpine=True)
        t1 = time.time()
        path = os.path.join(s.work, f"once-{k}.npy")
        sidecar_events.mark(f"once {k}: save")
        np.save(path, grid)
        del grid
    elif kind == "full":  # rule (b): every block, no `needed`, not split (its seconds not to be read)
        sidecar_events.mark(f"full {k}")
        path = os.path.join(s.work, f"full-{k}.npy")
        done = access.block_grid(z, water, res, filled, path, s.work, block_px, alpine=True)
        t1 = time.time()
        out["untimed"] = True
        out["block_px"], out["blocks"], out["left_out"] = block_px, done["blocks"], done.get("left_out", 0)
    else:
        path = os.path.join(s.work, "access.npy")  # search.ACCESS_FILE
        import inspect
        takes = "needed" in inspect.signature(access.block_grid).parameters
        needed = s.needed() if takes else None
        # E (wave 2b): the search area as search._access_grid passes it; a tree before E computes every block
        extra = {"needed": needed} if takes else {}
        out["needed_passed"] = "search area" if needed is not None else ("none (every block)" if takes else
                                                                         "a tree without needed")
        before = set(work_files(s.work))
        start = len(sidecar_events.events)
        sidecar_events.windows = []
        sidecar_events.readings = {}
        sidecar_events.hook(access)

        def on_part(name):
            if name == "blocks":  # the level when the blocks begin: the first block's own start
                sidecar_events.mark("blocks: block 1", reading=True)
            else:
                sidecar_events.mark("grid-wide: whole-metre sample" if name == "grid-wide" else name)
        try:
            done = access.block_grid(z, water, res, filled, path, s.work, block_px, alpine=True, on_part=on_part,
                                     **extra)
        finally:
            sidecar_events.unhook(access)
            del needed, extra
        t1 = time.time()
        sidecar_events.mark(f"blocks {k}: after")
        out["block_px"], out["blocks"], out["window_px"] = block_px, done["blocks"], done["window_px"]
        out["left_out"] = done.get("left_out", 0)  # blocks computed: "blocks"; left out (E): "left_out"
        out["whole_metres"] = bool(done["whole_metres"])
        out["windows"] = list(sidecar_events.windows)
        out["readings"] = dict(sidecar_events.readings)
        out["large_regions"] = list(sidecar_events.large)  # B: each large flat region's passes and seconds
        out["counts"] = dict(sidecar_events.counts)  # S: per pass its records, scratch bytes, visits, questions
        out["labels_dtypes"] = sorted(sidecar_events.labels_dtypes)  # S: observed; [] on the base
        out["hooks"] = sidecar_events.found
        out["first_event"] = start
        gc.collect()
        out["left_in_work"] = sorted(set(work_files(s.work)) - before - {"access.npy"})
        renamed = os.path.join(s.work, f"blocks-{k}.npy")
        os.replace(path, renamed)
        path = renamed
        if keep_grid and k == 1:  # after the stage's clock: the grid for a comparison with another tree's
            shutil.copyfile(path, keep_grid)
            out["kept_grid"] = keep_grid
    out["s"] = round(t1 - t0, 2)
    out["t0"], out["t1"] = t0, t1
    out["end"] = memory_now(proc)
    out["cg_end"] = cgroup_sample()  # memory.peak since the container started, at the stage's end
    out["path"] = path
    return out


def stage_report(stage: Dict, parts: Dict[str, Dict], pixels: int) -> Dict:
    """The parts of a stage with bytes per pixel: the grid-wide ones per pixel of the grid, the blocks' per pixel of
    their window and of the largest window."""
    rows = {}
    for label, row in parts.items():
        r = dict(row)
        r["rss_b_per_grid_px"] = per_px(r["peak_rss_above_start"], pixels)
        r["private_b_per_grid_px"] = per_px(r["peak_private_above_start"], pixels)
        rows[label] = r
    out = {k: v for k, v in stage.items() if k not in ("t0", "t1", "path", "first_event")}
    out["parts"] = rows
    whole = merge(parts, "")
    out["peak_rss_above_start"] = whole["peak_rss_above_start"] if whole else None
    out["peak_private_above_start"] = whole["peak_private_above_start"] if whole else None
    out["rss_b_per_grid_px"] = per_px(out["peak_rss_above_start"], pixels)
    out["private_b_per_grid_px"] = per_px(out["peak_private_above_start"], pixels)
    if whole and whole.get("cg_peak") is not None:
        out.update(cg_peak=whole["cg_peak"], cg_peak_above_start=whole["cg_peak_above_start"],
                   cg_split_at_peak=whole["cg_split_at_peak"])
    if stage["stage"] == "blocks":
        g = merge(parts, "grid-wide")
        if g:
            g["rss_b_per_grid_px"] = per_px(g["peak_rss_above_start"], pixels)
            g["private_b_per_grid_px"] = per_px(g["peak_private_above_start"], pixels)
        out["grid_wide"] = g
        out["blocks_list"] = block_rows(stage, parts)
        b = merge({k: v for k, v in parts.items() if k.startswith("blocks: block ")
                   and int(k.rsplit(" ", 1)[1]) <= len(stage.get("windows", []))}, "blocks: block ")
        if b:
            largest = stage.get("window_px") or max(stage.get("windows", [0]) or [0])
            b["largest_window_px"] = largest
            # above the blocks STAGE's start (what is resident when the blocks begin and piles up block after block
            # included): comparable with 2026-11-15's figures, not a window's own cost
            b["stage_rss_b_per_largest_window_px"] = per_px(b["peak_rss_above_start"], largest)
            b["stage_private_b_per_largest_window_px"] = per_px(b["peak_private_above_start"], largest)
            level = (stage.get("readings") or {}).get("blocks: block 1")
            if level:
                start = stage["start"]
                b["level_rss"], b["level_private"] = level["rss"], level["private"]
                b["peak_rss_above_level"] = _shift(b["peak_rss_above_start"], start["rss"], level["rss"])
                b["peak_private_above_level"] = _shift(b["peak_private_above_start"], start["private"],
                                                       level["private"])
                b["level_rss_b_per_largest_window_px"] = per_px(b["peak_rss_above_level"], largest)
                b["level_private_b_per_largest_window_px"] = per_px(b["peak_private_above_level"], largest)
        out["blocks_part"] = b
        out["needed"] = constant_needed(out, pixels, stage.get("window_bytes", 50))
        out["pass_parts"] = pass_parts(parts, g["s"] if g else None)
        rows = [r for r in out["blocks_list"] if r.get("ws_less_private_b_per_grid_px") is not None]
        if rows:  # the file pages (WS less private) above the start: when the blocks begin and at the last block
            lv = (stage.get("readings") or {}).get("blocks: block 1")
            st0 = stage["start"]
            if lv and lv.get("private") is not None and st0.get("private") is not None:
                out["ws_less_private_at_level_b_per_grid_px"] = per_px(
                    (lv["rss"] - lv["private"]) - (st0["rss"] - st0["private"]), pixels)
            out["ws_less_private_last_block_b_per_grid_px"] = rows[-1]["ws_less_private_b_per_grid_px"]
    return out


def constant_needed(st: Dict, pixels: int, window_bytes: float = 50) -> Dict:
    """What the rule's per-pixel constant must cover on a blocks stage (the working set above the stage's start, as
    the rule counts it): the grid-wide pass's peak per pixel of the grid, and the blocks' peak less window_bytes (the
    tree's search.ACCESS_WINDOW_BYTES) per pixel of the largest window measured, per pixel of the grid; the larger of
    the two is "the constant needed". Above the stage's START: a start that already holds pages of the files the
    stage reads (step 1 ran in the process) shows less than a cold one (`--empty-start`; code review G1-1). Also the blocks' with the window at its measured private bytes (above the level when the blocks
    begin) instead of 50. Beside them the pass's private peak in MiB and the mark's files: the work folder's peak
    during the stage less what it held at the stage's start, per pixel of the grid."""
    g, b = st.get("grid_wide") or {}, st.get("blocks_part") or {}
    largest = b.get("largest_window_px")
    out = {"pass_ws_b_per_px": per_px(g.get("peak_rss_above_start"), pixels)}
    if b.get("peak_rss_above_start") is not None and largest:
        out["window_bytes"] = window_bytes
        out["blocks_beyond_50_b_per_px"] = per_px(b["peak_rss_above_start"] - window_bytes * largest, pixels)
        if b.get("peak_private_above_level") is not None:
            out["blocks_beyond_private_b_per_px"] = per_px(b["peak_rss_above_start"] - b["peak_private_above_level"],
                                                           pixels)
    values = [v for v in (out["pass_ws_b_per_px"], out.get("blocks_beyond_50_b_per_px")) if v is not None]
    out["constant_needed"] = max(values) if values else None
    out["decided_by"] = None if not values else ("grid-wide pass" if out["constant_needed"] == out["pass_ws_b_per_px"]
                                                 else "blocks beyond their window")
    out["pass_private_mib"] = (round(g["peak_private_above_start"] / MB, 1)
                               if g.get("peak_private_above_start") is not None else None)
    disks = [r["peak_disk"] for r in st["parts"].values() if r.get("peak_disk") is not None]
    if disks and st.get("work_bytes_at_start") is not None:
        out["mark_files_bytes"] = max(disks) - st["work_bytes_at_start"]
        out["mark_files_b_per_px"] = per_px(out["mark_files_bytes"], pixels)
        # wave 2b: the masks are not mapped, so their bytes are in no working-set column; on disk, in the pass and in
        # the blocks apart (the work folder's peak in those parts less its size at the stage's start); the pass without
        # "masks opened", where block_grid makes the blocks' output grid (1 B/px, seen there or not by the sidecar)
        for key, head in (("pass", "grid-wide"), ("blocks", "blocks: ")):
            got = [r["peak_disk"] for label, r in st["parts"].items()
                   if label.startswith(head) and label != "grid-wide: masks opened" and r.get("peak_disk") is not None]
            if got:
                out[f"mark_files_{key}_bytes"] = max(got) - st["work_bytes_at_start"]
                out[f"mark_files_{key}_b_per_px"] = per_px(out[f"mark_files_{key}_bytes"], pixels)
    return out


PASSES = ("flat lakes", "open ground", "smoothed open ground")


def pass_parts(parts: Dict[str, Dict], pass_s: Optional[float]) -> Dict:
    """The grid-wide pass's seconds cut as wave 2a's brief fixes it, on either tree: per pass "mask", "regions" (with
    its sub-parts: the base's labels and bounds, S's forward and backward sweep) and "after" (with S's B apart); the
    rest (the whole-metre sample, the water's copy, "masks opened"); their sum against the pass; and "the span the
    wide box's line judges": regions + after of the two open-ground passes."""
    out, total, total_raw, span_raw = {}, 0.0, 0.0, 0.0
    for g in PASSES:
        row = {"mask": 0.0, "regions": 0.0, "after": 0.0, "sub": {}}
        for label, r in parts.items():
            for part in ("mask", "regions", "after"):
                head = f"grid-wide: {g}: {part}"
                if label == head or label.startswith(head + ":"):
                    row[part] += r["s"]
                    total_raw += r.get("s_raw", r["s"])
                    if part != "mask" and g in ("open ground", "smoothed open ground"):
                        span_raw += r.get("s_raw", r["s"])
                    if label != head:
                        row["sub"][label[len(head) + 2:]] = round(row["sub"].get(label[len(head) + 2:], 0) + r["s"], 3)
        if any(row[p] for p in ("mask", "regions", "after")):
            out[g] = {k: (round(v, 3) if not isinstance(v, dict) else v) for k, v in row.items()}
            total += row["mask"] + row["regions"] + row["after"]
    rest = {}
    for name in ("whole-metre sample", "water (copy, flush)", "masks opened"):
        r = parts.get(f"grid-wide: {name}")
        if r:
            rest[name] = round(r["s"], 3)
            total += r["s"]
            total_raw += r.get("s_raw", r["s"])
    other = {label[11:]: round(r["s"], 3) for label, r in parts.items() if label.startswith("grid-wide: ")
             and not any(label.startswith(f"grid-wide: {g}: ") for g in PASSES)
             and label[11:] not in rest}
    total += sum(other.values())
    total_raw += sum(r.get("s_raw", r["s"]) for label, r in parts.items() if label.startswith("grid-wide: ")
                     and label[11:] in other)
    out["rest"] = rest
    if other:
        out["other"] = other  # a label of neither cut (a hook of another tree): shown, never dropped
    out["sum_s"] = round(total, 3)
    out["pass_s"] = pass_s
    # unrounded, from the event times: the pass (the grid-wide parts are contiguous, from on_part("grid-wide") to
    # on_part("blocks")) and the judged span; a margin under the parts' rounding is decided on these
    out["pass_s_raw"] = total_raw
    out["judged_span_s_raw"] = span_raw
    out["judged_span_s"] = round(sum(out[g]["regions"] + out[g]["after"] for g in ("open ground", "smoothed open ground")
                                     if g in out), 3)
    return out


def _shift(above_start: Optional[int], start: Optional[int], base: Optional[int]) -> Optional[int]:
    """A peak given above one base, above another: above_start + start - base."""
    return None if above_start is None or start is None or base is None else above_start + start - base


def block_rows(stage: Dict, parts: Dict[str, Dict]) -> List[Dict]:
    """Per block: its window, seconds, samples; its peak working set and private bytes above the blocks STAGE's start
    (`stage_*`, as 2026-11-15 counted), above the level when the blocks begin (`level_*`: what the grid-wide pass left
    resident taken off: the window's figure); per pixel of the window each. No figure above a block's own start: the
    previous window's arrays are still alive at that moment, so it read low and could go negative (code review N1).
    A block whose part has no sample has no peaks."""
    rows = []
    readings = stage.get("readings") or {}
    start = stage["start"]
    level = readings.get("blocks: block 1")
    for n, window in enumerate(stage.get("windows", []), 1):
        r = parts.get(f"blocks: block {n}")
        if not r:
            continue
        row = {"block": n, "window_px": window, "s": r["s"], "samples": r["samples"], "max_gap_s": r["max_gap_s"],
               "stage_rss": r["peak_rss_above_start"], "stage_private": r["peak_private_above_start"]}
        row["level_rss"] = _shift(r["peak_rss_above_start"], start["rss"], level and level["rss"])
        row["ws_less_private_above_start"] = r.get("peak_ws_less_private_above_start")
        row["ws_less_private_b_per_grid_px"] = per_px(row["ws_less_private_above_start"], stage.get("grid_px"))
        row["level_private"] = _shift(r["peak_private_above_start"], start["private"], level and level["private"])
        for key in ("stage", "level"):
            row[f"{key}_rss_b_per_window_px"] = per_px(row[f"{key}_rss"], window)
            row[f"{key}_private_b_per_window_px"] = per_px(row[f"{key}_private"], window)
        rows.append(row)
    return rows


def run_stages(args) -> Dict:
    machine = set_cores(args.cores)
    import access
    from progress import progress
    s = Search(args)
    out = {"command": "stages", "machine": machine, "plan": s.describe(), "rule": s.rule(), "events": s.events,
           "order": [] if args.step1_only else [x for x in args.order.split(",") if x]}
    if args.block_px:
        out["rule"]["block_px_given"] = args.block_px
    block_px = args.block_px or out["rule"]["block_px"]
    unknown = [x for x in out["order"] if x not in ("once", "blocks", "full")]
    if unknown:
        raise SystemExit(f"--order: once, blocks or full, not {unknown}")
    if any(x in ("blocks", "full") for x in out["order"]) and not block_px:
        out["note"] = "the rule makes the grid at once (or leaves the mark out): no blocks without --block-px"
        out["order"] = [x for x in out["order"] if x not in ("blocks", "full")]
    if out["order"]:
        warm_up()
    marks = Marks()
    sidecar = Sidecar(os.path.join(args.out, "samples"), s.work)
    stage_on = {"label": None}

    def listener(state):  # step 1's progress bars as parts
        if stage_on["label"] is None or not state["bar"]:
            return
        if state["done"]:
            label = "step 1: (between bars)"
        elif state["count"] == 0 and state["stage"]:
            label = f"step 1: {state['bar']} {state['stage']}"
        else:
            return
        if label != stage_on["label"]:
            stage_on["label"] = label
            marks.mark(label)
    progress.subscribe(listener)
    stages, raw = [], []
    try:
        gc.collect()
        step1 = {"stage": "step 1", "start": memory_now(psutil.Process()), "cg_start": cgroup_sample()}
        stage_on["label"] = "step 1: start"
        marks.mark("step 1: start")
        t0 = time.time()
        s.step1()
        t1 = time.time()
        stage_on["label"] = None
        marks.mark("after step 1")
        step1.update(s=round(t1 - t0, 2), t0=t0, t1=t1, end=memory_now(psutil.Process()),
                     work_after=work_files(s.work), first_event=0, cg_end=cgroup_sample())
        raw.append((step1, len(marks.events)))
        if args.estimate_first:  # as a web job of a tiled area: the estimate between step 1 and the access grid
            out["estimate"] = run_estimate(s)
        counts = {}
        for kind in out["order"]:
            counts[kind] = counts.get(kind, 0) + 1
            first = len(marks.events)
            st = run_stage(s, marks, kind, counts[kind], access, block_px, args.empty_start, args.keep_grid)
            st["first_event"] = first
            raw.append((st, len(marks.events)))
            stages.append(st)
    finally:
        samples, listings = sidecar.stop(args.keep_samples)
    # parts: each stage's events from its first to its end, within its seconds
    reports = []
    for st, end_event in raw:
        events = [e for e in marks.events[st["first_event"]:end_event] if st["t0"] <= e[0] <= st["t1"]]
        if not events or events[0][0] > st["t0"]:
            events.insert(0, (st["t0"], st["stage"]))
        if st["stage"] == "blocks":  # the part after the last block's measure: its write, the flush, the removal
            n = len(st.get("windows", []))
            events = [(t, "blocks: flush and removal" if label == f"blocks: block {n + 1}" else label)
                      for t, label in events]
        parts = summarise(samples, listings, events, st["t1"], st["start"], st.get("cg_start"))
        rep = stage_report(st, parts, s.pixels)
        rep["file_peaks"] = file_peaks(listings, st["t0"], st["t1"], s.pixels)
        reports.append(rep)
    out["step1"] = reports[0]
    out["step1"]["work_after"] = raw[0][0]["work_after"]
    out["stages"] = reports[1:]
    out["samples"] = len(samples)
    # after every stage's clock: the blocks by rule (a) (also without a grid at once: the pixels left out and those in
    # the area), "full" by rule (b)
    once = [st for st in stages if st["stage"] == "once"]
    once_grid = np.load(once[0]["path"], mmap_mode="r") if once else None
    area = s.data.mask if s.data is not None else None
    for st, rep in zip(stages, out["stages"]):
        if st["stage"] == "blocks":
            rep["rule_a"] = compare_rule_a(once_grid, np.load(st["path"], mmap_mode="r"), area)
            rep["left_out_px"] = rep["rule_a"]["left_out_px"]
            if once_grid is not None:  # the comparison the judges read: rule (a)
                rep["compare_with_once"] = rep["rule_a"]
        elif st["stage"] == "full" and once_grid is not None:
            rep["rule_b"] = dict(compare_grids(once_grid, np.load(st["path"], mmap_mode="r")), rule="b")
    del once_grid, area
    gc.collect()
    out["cg_events"] = cgroup_events()
    out["cg_final"] = cgroup_sample()
    out["work"] = s.work
    s.close(args.keep_work)
    return out


def run_estimate(s: Search) -> Dict:
    """search._estimate_tiles(plan, area) between step 1 and the stage, as search_lines runs it in a web job of a
    tiled area (where search._samples is true: the tool's plan has no limits, so it is called directly; without
    limits and Plan.memory its decision refuses nothing). Its seconds and this process's memory before and after."""
    proc = psutil.Process()
    if not s.plan.tiles:
        return {"run": False, "why": "a plan without tiles: the estimate of one grid runs inside _lines"}
    gc.collect()
    before = memory_now(proc)
    t0 = time.time()
    s.search._estimate_tiles(s.plan, s.data)
    out = {"run": True, "s": round(time.time() - t0, 2), "before": before}
    gc.collect()
    out["after"] = memory_now(proc)
    out["funnel_estimate"] = s.plan.funnel.get("estimate")
    return out


def run_plan(args) -> Dict:
    machine = set_cores(args.cores)
    s = Search(args)
    estimate = s.search.estimate_search(s.plan)
    data_dir = s.plan.paths.data
    out = {"command": "plan", "machine": machine, "plan": s.describe(), "rule": s.rule(), "events": s.events,
           "estimate": {"download_mb": round(estimate.download_mb), "work_gb": round(estimate.work_gb, 1),
                        "reasons": estimate.reasons},
           "work_gb_with_access_disk": round((estimate.work_gb * 1e9 + (0 if s.plan.access_on else
                                              s.pixels * s.search.ACCESS_DISK_BYTES)) / 1e9, 1),
           "step1_labels_gb": round(s.pixels * 4 / 1e9, 2),
           "disk_free_gb": round(shutil.disk_usage(data_dir).free / 1e9, 1), "data_dir": data_dir}
    s.close()
    return out


def run_pieces(args) -> Dict:
    machine = set_cores(args.cores)
    import access
    s = Search(args)
    out = {"command": "pieces", "machine": machine, "plan": s.describe(), "rule": s.rule()}
    t0 = time.time()
    data = s.step1()
    out["step1_s"] = round(time.time() - t0, 1)
    z, water, res, filled = s.inputs()
    h, w = z.shape
    own = getattr(access, "_strips", None)
    strip_rows = list(own(h, w)) if callable(own) else list(strips(h, w, getattr(access, "STRIP_PX", STRIP_PX)))
    halo = getattr(access, "HALO", HALO)
    mask = data.mask if data.mask is not None else s.plan.area.mask(s.plan.grid)
    out["shares"] = data_shares(z, mask, strip_rows, halo, water, filled)
    sides = {"rule": out["rule"]["block_px"]} if out["rule"]["block_px"] else {}
    sides.update({f"{km} km": int(round(km * 1000 / res)) for km in BLOCK_KM})
    out["blocks_with_area"] = {name: blocks_holding(mask, px) for name, px in sides.items()}
    if args.anchors:
        t_anchors = time.time()
        rows, cols = anchors_of(s)
        out["anchors_s"] = round(time.time() - t_anchors, 1)  # step 2 over the tiles (their windows copied, as the
        out["anchors_tiles"] = len(s.plan.tiles or [])         # estimate does), or of the one grid
        out["anchors_found_by_tiles"] = int(len(rows))  # each tile's, the overlaps' counted once a tile
        unique = np.unique(rows * w + cols)
        rows, cols = unique // w, unique % w
        out["anchors"] = int(len(rows))  # each pixel once
        out["blocks_with_anchor"] = {name: blocks_holding_points(rows, cols, (h, w), px) for name, px in sides.items()}
    # the real grid-wide pass, stopped before its first block; each mask's strip pieces before today's labels
    masks = {}
    real = getattr(access, "_region_areas", None)

    class Stop(Exception):
        pass

    def on_part(name):
        if name == "blocks":
            raise Stop

    extra = [0.0]
    if callable(real):
        def region_areas(mask_path, *a, **k):
            t = time.time()  # the tool's own counting and copy: taken off the pass's seconds (pass_s)
            m = np.load(mask_path, mmap_mode="r")
            row = strip_pieces(m, strip_rows)
            row["true_pixels"] = int(sum(np.count_nonzero(np.asarray(m[r0:r1])) for r0, r1 in strip_rows))
            del m
            extra[0] += time.time() - t
            labels, n, count = real(mask_path, *a, **k)
            t = time.time()
            row["regions"] = int(n)
            minimum = access.FLAT_WATER_MIN_M2 if "flat" in os.path.basename(mask_path) else access.OPEN_MIN_M2
            row["regions_kept_by_size"] = int((count[1:] * res * res >= minimum).sum())
            row["table_bytes_at_4_per_piece"] = 4 * row["pieces"]
            row["table_b_per_grid_px"] = round(4 * row["pieces"] / (h * w), 4)
            masks[GROUPS.get(os.path.basename(mask_path), os.path.basename(mask_path))] = row
            if args.capture:  # the mask as labelled (before the regions' size), for a check of these counts
                os.makedirs(args.capture, exist_ok=True)
                row["captured"] = os.path.join(args.capture, f"{args.name}-{os.path.basename(mask_path)}")
                shutil.copyfile(mask_path, row["captured"])
            extra[0] += time.time() - t
            return labels, n, count
        access._region_areas = region_areas
    regions_cls = getattr(access, "_Regions", None)
    real_init = regions_cls.__init__ if regions_cls is not None and not callable(real) else None
    if real_init is not None:  # wave 1's code: the regions found by _Regions, its own counts and scratch file
        def regions_init(self, mask, path, judge, *a, **k):
            t = time.time()
            row = strip_pieces(_MaskRows(mask), strip_rows)
            row["true_pixels"] = int(sum(np.count_nonzero(mask.rows(r0, r1)) for r0, r1 in strip_rows))
            name = os.path.basename(mask.path)
            if args.capture:  # the mask as its regions are found (before the regions' size), for a check: a bool
                os.makedirs(args.capture, exist_ok=True)  # .npy from its rows (wave 2b's masks are bits in the file)
                row["captured"] = os.path.join(args.capture, f"{args.name}-{name}")
                save_bool(row["captured"], mask.rows, mask.shape)
            judged = {"regions": 0, "not_dropped": 0}

            def counted(pixels, lowest, highest):
                verdict = np.asarray(judge(pixels, lowest, highest))
                judged["regions"] += len(verdict)
                judged["not_dropped"] += int((verdict != access.DROP).sum())
                return verdict
            extra[0] += time.time() - t
            real_init(self, mask, path, counted, *a, **k)
            t = time.time()
            tables = self._tables  # per strip: offset, pieces, classes carried in, classes
            row["regions"] = judged["regions"]
            row["regions_kept_by_size"] = judged["not_dropped"]  # kept or an open question (the flat lakes')
            row["regions_by_tables"] = int(sum(k_ - (tables[j + 1][2] if j + 1 < len(tables) else 0)
                                               for j, (_, _, _, k_) in enumerate(tables)))
            row["pieces_by_regions"] = int(sum(n_ for _, n_, _, _ in tables))
            row["most_carried"] = int(max((nc for _, _, nc, _ in tables), default=0))
            row["scratch_file_bytes"] = os.path.getsize(path)
            row["scratch_b_per_grid_px"] = round(row["scratch_file_bytes"] / (h * w), 4)
            row["table_bytes_at_4_per_piece"] = 4 * row["pieces"]
            row["table_b_per_grid_px"] = round(4 * row["pieces"] / (h * w), 4)
            masks[GROUPS.get(name, name)] = row
            extra[0] += time.time() - t
        regions_cls.__init__ = regions_init
    t0 = time.time()
    try:  # the blocks' side does not matter: the pass stops before the first block
        access.block_grid(z, water, res, filled, os.path.join(s.work, "access.npy"), s.work,
                          int(math.ceil(500 / res)), alpine=True, on_part=on_part)
    except Stop:
        pass
    finally:
        if callable(real):
            access._region_areas = real
        if real_init is not None:
            regions_cls.__init__ = real_init
    out["pass_s"] = round(time.time() - t0 - extra[0], 1)  # the pass alone
    out["tool_s_in_pass"] = round(extra[0], 1)  # the pieces' counting and the --capture copies, taken off
    out["hooks"] = ["_region_areas"] if callable(real) else ["_Regions.__init__"] if real_init else []
    out["masks"] = masks
    gc.collect()
    if args.capture:
        os.makedirs(args.capture, exist_ok=True)
        out["captured"] = {}
        for name in ("water", "og", "og2"):
            p = os.path.join(s.work, f"access_{name}.npy")
            if os.path.exists(p):  # as a bool .npy whatever the tree keeps (wave 2b: bits, unpacked)
                dest = os.path.join(args.capture, f"{args.name}-{name}.npy")
                grid = mask_as_bool(p, (h, w))
                save_bool(dest, lambda r0, r1: grid[r0:r1], (h, w))
                del grid
                os.remove(p)
                out["captured"][name] = dest
    del data, z, water, filled, mask
    s.close(args.keep_work)
    return out


class _MaskRows:
    """A _Mask (wave 1) read by rows as an array: mask[r0:r1] and .shape, as strip_pieces reads a mapped mask."""

    def __init__(self, mask):
        self.mask, self.shape = mask, mask.shape

    def __getitem__(self, rows: slice):
        return self.mask.rows(rows.start, rows.stop)


def anchors_of(s: Search) -> Tuple[np.ndarray, np.ndarray]:
    """The anchors (rows, columns of the search's grid) as search._estimate_tiles finds them: each tile's window of
    the area's grids (search._tile_data) and its step 2 (search._anchors, quiet; prominence and drop left out: the
    same anchors without --min-prominence, --min-prominence-both and --min-drop); one grid's own without tiles."""
    search, plan = s.search, s.plan
    quiet = dataclasses.replace(plan, emit=search._no_event, funnel={})
    rows, cols = [], []
    if not plan.tiles:
        found = search._anchors(quiet, s.data, quiet=True, deferred=True)
        a = found.anchors if found is not None else np.zeros((0, 2), np.int64)
        return a[:, 0].astype(np.int64), a[:, 1].astype(np.int64)
    for k, (core, tile) in enumerate(plan.tiles):
        work = os.path.join(plan.paths.work, f"sample{k}")
        os.makedirs(work, exist_ok=True)
        tile_plan = dataclasses.replace(quiet, grid=tile, paths=search.Paths(plan.paths.data, work), tiles=None)
        data = search._tile_data(s.data, plan.grid, tile, work, None)
        found = search._anchors(tile_plan, data, quiet=True, deferred=True)
        if found is not None:
            r, c = search._tile_window(plan.grid, tile)
            rows.append(found.anchors[:, 0].astype(np.int64) + r.start)
            cols.append(found.anchors[:, 1].astype(np.int64) + c.start)
        del data, found
        gc.collect()
        shutil.rmtree(work, ignore_errors=True)
    if not rows:
        return np.zeros(0, np.int64), np.zeros(0, np.int64)
    return np.concatenate(rows), np.concatenate(cols)


def run_compare(args) -> Dict:
    if args.files:
        return {"command": "compare", "files": args.files,
                **compare_grids(np.load(args.files[0], mmap_mode="r"), np.load(args.files[1], mmap_mode="r"))}
    machine = set_cores(args.cores)
    import access
    s = Search(args)
    out = {"command": "compare", "machine": machine, "plan": s.describe(), "rule": s.rule()}
    block = args.block_px or out["rule"]["block_px"]
    if not block:
        raise SystemExit("the rule makes the grid at once here: give --block-px (or a smaller --memory)")
    s.step1()
    z, water, res, filled = s.inputs()
    once = os.path.join(s.work, "once.npy")
    np.save(once, access.access_grid(z, water, res, filled, alpine=True))
    blocks = os.path.join(s.work, "access.npy")
    done = access.block_grid(z, water, res, filled, blocks, s.work, block, alpine=True)
    out.update(block_px=block, blocks=done["blocks"], window_px=done["window_px"])
    out.update(compare_grids(np.load(once, mmap_mode="r"), np.load(blocks, mmap_mode="r")))
    del z, water, filled
    s.close(args.keep_work)
    return out


# ---------------------------------------------------------------- printing

def _mb(v) -> str:
    return "" if v is None else f"{v / MB:,.0f}"


def print_table(out: Dict):
    cmd = out["command"]
    if "plan" in out:
        p, r = out["plan"], out["rule"]
        print(f"grid {p['grid'][1]} x {p['grid'][0]} px ({p['grid_px'] / 1e6:.1f} Mpx, {p['box_km'][0]} x "
              f"{p['box_km'][1]} km at {p['res']:g} m), tiles {p['tiles']}")
        how = ("left out (memory)" if r["access_skipped"] else "at once" if r["at_once"] else
               f"{r['blocks']} blocks of {r['block_px']} px ({r['block_m']:g} m), windows up to "
               f"{r['window_px_max'] / 1e6:.1f} Mpx")
        print(f"access: needs {r['access_memory'] / 1e9:.2f} GB at least, budget {r['budget'] / 1e9:.2f} GB: {how}")
    if cmd == "plan":
        e = out["estimate"]
        print(f"estimate: download {e['download_mb']} MB, work folder {e['work_gb']} GB "
              f"({out['work_gb_with_access_disk']} GB with the access grid's files); step 1's labels "
              f"{out['step1_labels_gb']} GB; disk free {out['disk_free_gb']} GB")
    elif cmd == "stages":
        print("\nMiB = 2^20 bytes; peaks above the stage's start; B/px of the grid (WS, private)")
        print(f"{'part':52} {'s':>7} {'n':>5} {'gap':>5} {'WS MiB':>7} {'prv MiB':>7} {'B/px':>6} {'B/px p':>6}"
              f" {'diskMiB':>8}")
        for st in [out["step1"]] + out["stages"]:
            name = st["stage"] + (f" {st['run']}" if "run" in st else "")
            print(f"{name:52} {st['s']:7.1f} {'':5} {'':5} {_mb(st['peak_rss_above_start']):>7} "
                  f"{_mb(st['peak_private_above_start']):>7} {st['rss_b_per_grid_px'] or '':>6} "
                  f"{st['private_b_per_grid_px'] or '':>6}")
            for label, r in st["parts"].items():
                if label.startswith("blocks: block ") or r["s"] < 0.05:
                    continue
                if not r["samples"]:
                    print(f"  {label[:50]:50} {r['s']:7.1f} {0:5} {r['max_gap_s']:5.2f} no sample")
                    continue
                print(f"  {label[:50]:50} {r['s']:7.1f} {r['samples']:5} {r['max_gap_s']:5.2f} "
                      f"{_mb(r['peak_rss_above_start']):>7} {_mb(r['peak_private_above_start']):>7} "
                      f"{r['rss_b_per_grid_px'] or '':>6} {r['private_b_per_grid_px'] or '':>6} "
                      f"{_mb(r['peak_disk']):>8}")
            if st["stage"] == "blocks":
                g, b = st.get("grid_wide"), st.get("blocks_part")
                if g:
                    print(f"  {'= grid-wide pass':50} {g['s']:7.1f} {g['samples']:5} {g['max_gap_s']:5.2f} "
                          f"{_mb(g['peak_rss_above_start']):>7} {_mb(g['peak_private_above_start']):>7} "
                          f"{g['rss_b_per_grid_px'] or '':>6} {g['private_b_per_grid_px'] or '':>6} "
                          f"{_mb(g['peak_disk']):>8}")
                if b:
                    print(f"  {'= blocks, above the stage start: B/px largest window':50}"
                          f" {b['s']:7.1f} {b['samples']:5} "
                          f"{b['max_gap_s']:5.2f} {_mb(b['peak_rss_above_start']):>7} "
                          f"{_mb(b['peak_private_above_start']):>7} {b['stage_rss_b_per_largest_window_px'] or '':>6} "
                          f"{b['stage_private_b_per_largest_window_px'] or '':>6}")
                    if b.get("peak_rss_above_level") is not None:
                        print(f"  {'= blocks, above the level when they begin':50} {'':7} {'':5} {'':5} "
                              f"{_mb(b['peak_rss_above_level']):>7} {_mb(b['peak_private_above_level']):>7} "
                              f"{b['level_rss_b_per_largest_window_px'] or '':>6} "
                              f"{b['level_private_b_per_largest_window_px'] or '':>6}")
                if st.get("ws_less_private_last_block_b_per_grid_px") is not None:
                    print(f"  WS less private above the start: {st.get('ws_less_private_at_level_b_per_grid_px')} B/px "
                          f"when the blocks begin, {st['ws_less_private_last_block_b_per_grid_px']} at the last block"
                          + (" (emptied start)" if st.get("emptied") else ""))
                n = st.get("needed") or {}
                if n:
                    print(f"  constant needed {n.get('constant_needed')} B/px ({n.get('decided_by')}): pass "
                          f"{n.get('pass_ws_b_per_px')}, blocks beyond 50 B a window pixel "
                          f"{n.get('blocks_beyond_50_b_per_px')}, beyond their private bytes "
                          f"{n.get('blocks_beyond_private_b_per_px')}; pass private {n.get('pass_private_mib')} MiB; "
                          f"the mark's files {n.get('mark_files_b_per_px')} B/px")
                for r in st.get("large_regions") or []:
                    print(f"  B: a large flat region of {r['pixels'] / 1e6:.1f} Mpx over {r['strips']} strips: "
                          f"{r.get('passes')} passes, {r.get('visits')} windows visited, {r['s']} s")
                pp = st.get("pass_parts") or {}
                for g in PASSES:
                    if g in pp:
                        print(f"  {g}: mask {pp[g]['mask']} s, regions {pp[g]['regions']} s, after {pp[g]['after']} s "
                              f"{pp[g]['sub']}")
                if pp:
                    print(f"  the pass {pp['sum_s']} s in parts (rest {pp['rest']}); the judged span (regions + after "
                          f"of the open ground's passes) {pp['judged_span_s']} s; scratch peaks {st.get('file_peaks')}")
                c = st.get("compare_with_once")
                print(f"  {st['blocks']} blocks of {st['block_px']} px, largest window {st['window_px'] / 1e6:.1f} "
                      f"Mpx; left in work: {st['left_in_work'] or 'nothing'}"
                      + (f"; differ from once: {c['differ']}" if c else ""))
    elif cmd == "pieces":
        sh = out["shares"]
        print(f"with heights {sh['with_heights']:.3f}, search area {sh.get('search_area', 0):.3f}, strips' width "
              f"with heights {sh['strip_width_with_heights_mean']:.3f}, strips without {sh['strips_without_heights']:.3f}")
        print(f"land (data, not water) {sh['with_land']:.3f}, strips' width with land "
              f"{sh['strip_width_with_land_mean']:.3f}, strips without {sh['strips_without_land']:.3f}")
        for name, b in out["blocks_with_area"].items():
            a = out.get("blocks_with_anchor", {}).get(name)
            print(f"blocks of {name} ({b['block_px']} px): {b['holding']}/{b['blocks']} hold the area"
                  + (f", {a['holding']} an anchor" if a else ""))
        print(f"\n{'mask':24} {'pieces':>10} {'most/strip':>10} {'last row':>9} {'regions':>9} {'kept':>7} "
              f"{'tableMiB':>9} {'B/px':>7}")
        for name, m in out["masks"].items():
            print(f"{name:24} {m['pieces']:10} {m['most_in_a_strip']:10} {m['most_in_a_last_row']:9} "
                  f"{m['regions']:9} {m['regions_kept_by_size']:7} {m['table_bytes_at_4_per_piece'] / MB:9.1f} "
                  f"{m['table_b_per_grid_px']:7.4f}")
    elif cmd == "masks":
        print(f"mask {out['shape'][1]} x {out['shape'][0]}, windows of blocks of {out['block_px']} px + "
              f"{out['margin_px']}; equal windows: {out['windows_equal']}")
        print("MiB = 2^20 bytes; WS and private: the larger of the sampled peak and the OS's peak counter")
        print(f"{'way':8} {'keptMiB':>8} {'write s':>8} {'read s':>8} {'WS MiB':>7} {'prvMiB':>8} {'smp WS':>8} "
              f"{'smp prv':>8}")
        for way, m in out["ways"].items():
            print(f"{way:8} {m['kept_bytes'] / MB:8.1f} {m['write_s']:8.2f} {m['read_s']:8.2f} "
                  f"{_mb(m['peak_rss_above_start']):>7} {_mb(m['peak_private_above_start']):>8} "
                  f"{_mb(m['sampled_peak_rss_above_start']):>8} {_mb(m['sampled_peak_private_above_start']):>8}")
    elif cmd == "compare":
        print(f"pixels that differ: {out['differ']} of {out['pixels']}" + (f", first {out['first']}"
                                                                           if out["first"] else ""))


# ---------------------------------------------------------------- main

COMMANDS = {"plan": run_plan, "stages": run_stages, "pieces": run_pieces, "masks": run_masks, "compare": run_compare}


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.strip().split("\n\n")[0])
    p.add_argument("command", choices=list(COMMANDS))
    p.add_argument("--out", required=True, help="folder of the JSON file")
    p.add_argument("--name", required=True, help="name of the JSON file and the work folder")
    p.add_argument("--memory", type=float, help="bytes that search.available_memory answers (before planning)")
    p.add_argument("--cores", type=int, help="run on this many cores and numba threads")
    p.add_argument("--keep-work", action="store_true", help="keep the work folder")
    p.add_argument("--keep-grid", help="stages: copy the first blocks stage's finished access grid (.npy) here")
    p.add_argument("--keep-samples", action="store_true", help="stages: keep the sidecar's samples (<out>/samples)")
    p.add_argument("--order", default="once,blocks", help="stages: the stages after step 1, e.g. blocks,once,blocks; "
                                                          "full: every block without the search area (rule (b))")
    p.add_argument("--step1-only", action="store_true", help="stages: step 1 alone")
    p.add_argument("--empty-start", action="store_true",
                   help="stages: the working set emptied before each stage's start (Windows: EmptyWorkingSet)")
    p.add_argument("--estimate-first", action="store_true",
                   help="stages: the tiles' estimate (search._estimate_tiles) between step 1 and the stages")
    p.add_argument("--block-px", type=int, help="stages, compare, masks: the blocks' side instead of the rule's")
    p.add_argument("--area-bytes", type=float, help="the rule with this search.ACCESS_AREA_BYTES (this run only)")
    p.add_argument("--area-fixed", type=int, help="and this fixed term of the rule in bytes (this run only)")
    p.add_argument("--anchors", action="store_true", help="pieces: the share of blocks holding an anchor too")
    p.add_argument("--capture", help="pieces: keep the pass's final masks in this folder")
    p.add_argument("--mask", help="masks: the mask (.npy, one byte a pixel)")
    p.add_argument("--made-up", type=int, nargs=2, metavar=("H", "W"), help="masks: a made-up mask of H x W")
    p.add_argument("--res", type=float, default=1.0, help="masks: metres a pixel (the windows' margin)")
    p.add_argument("--work", help="masks: the folder of the children's files (default <out>/<name>-masks)")
    p.add_argument("--files", nargs=2, metavar=("A", "B"), help="compare: two saved grids (.npy)")
    p.epilog = "after the tool's options: -- and findaline.py's options, with --data-dir"
    return p


def main(argv: Optional[Sequence[str]] = None) -> Dict:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["_sampler"]:
        sampler_main(argv[1:])
        return {}
    if argv[:1] == ["_mask-child"]:
        result = mask_child(argv[1], json.loads(argv[2]))
        print(json.dumps(result))
        return result
    cut = argv.index("--") if "--" in argv else len(argv)
    args = parser().parse_args(argv[:cut])
    args.search = argv[cut + 1:]
    if args.command == "masks" and not args.block_px:
        raise SystemExit("masks: give --block-px")
    args.out = os.path.abspath(args.out)
    os.makedirs(args.out, exist_ok=True)
    os.environ.setdefault("FINDALINE_PROGRESS", "text")
    out = COMMANDS[args.command](args)
    out["argv"] = argv
    out["when"] = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(os.path.join(args.out, f"{args.name}.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, default=str)
    print_table(out)
    return out


if __name__ == "__main__":
    from progress import utf8_output
    utf8_output()  # redirected output in UTF-8, not the Windows code page
    main()
