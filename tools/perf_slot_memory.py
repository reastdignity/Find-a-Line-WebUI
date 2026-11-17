"""
Run by hand: the memory of one search as a compute slot holds it, its whole process tree (docs/performance.md, "The
memory constant"; search.LINE_BYTES). perf_profile.py only follows the search's own process; this one starts the
search in a child process (tools/perf_profile.py in it, with hooks) and samples the tree from outside every 0.2 s:
- each process's working set (rss), private bytes (Windows' commit) and, with --uss, unique set (USS: the pages no
  other process maps; slower to read), and the machine's used memory;
- in the search's process (hooks): the stages (progress bars), `mapping.view_columns`, `linestore.write` (step 5:
  what a search saves since store wave 4), the plan (the grid's and the largest tile's pixels, Plan.memory, whether
  the early check is on) and the square rule's reducers (`BestPerSquarePair.counts()`: peak_rows, kept, found).
The measure of `LINE_BYTES` is the unique sets summed (`peak_tree_uss_mb`, with --uss; `tree_uss_at_rss_peak_mb` at
the working sets' peak). Until store wave 4 (2026-11-17) step 5's peak was in saving.py's children, which
memory-mapped the same hand-over files, and the measure added those files once ("uss_plus_handover_mb", the hooks
`saving.save` and `saving.hand_over`); since then a search writes no text file, saving.py is gone and no two
processes of a search share such pages, so the hooks and the term went with it. A record made before compares with
one made after only through that key (docs/performance.md, "The memory constant").

    uv run tools/perf_slot_memory.py --out <folder> --name <name> [--cores 7] [--memory BYTES] [--worker] [--uss]
                                     [--remove-run] -- <findaline.py options, with --data-dir>

--cores and --memory are perf_profile.py's (the VPS worker's 7 CPUs; a compute slot's
budget: the tiles of an area as the worker sizes them). --worker plans the search as the web worker does: the public
limits (Limits.load(public=True)) and Plan.memory of one of 3 compute slots in 17 GiB free with 2 download slots
(search.slot_memory), so the early check and the 2 % sample before the pairs run; only the search's own plan, not the
plans of single lines' profiles (with_margin=False: at a tiled search's join), which are not recorded either. A search
refused (a SearchError of plan_search, estimate_search, search_lines or save_run) shows as "outcome": "refused" with
its code; a missing record of the hooks or a missing run is a warning, in the JSON and on stderr. The folders of --out
and --data-dir (also --data-dir=X) are made absolute first: the child runs in the tool's checkout. --remove-run deletes
the run's folder after its run.json and file sizes are read (a run of millions of lines takes gigabytes). Writes
<out>/<name>.json
(the peaks, where each fell, the plan, the reducers, the run's summary and files) and <out>/<name>-tree.csv, and
perf_profile.py's <name>.csv, <name>-stages.csv and <name>.png. Measure one search at a time under the test lock's
--exclusive (docs/workflow.md): the working sets follow what else the machine holds.
"""

import argparse
import bisect
import json
import os
import runpy
import shutil
import subprocess
import sys
import time
from typing import Dict, List, Optional, Sequence, Tuple

import psutil

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MB = 2 ** 20
INTERVAL = 0.2
CHILD = "--child"
# The names the child patches, each called through its module's attribute by the search (a rename must fail
# tests/test_perf_slot_memory.py, or the record would silently miss it)
HOOKED = (("mapping", "view_columns"), ("linestore", "write"), ("search", "plan_search"),
          ("samelines.BestPerSquarePair", "counts"))
HOOKED_SEARCH = ("plan_search", "estimate_search", "search_lines", "save_run")  # their SearchError: the refusal
GIB = 2 ** 30
SLOTS_FREE_GIB, COMPUTE_SLOTS, DOWNLOAD_SLOTS = 17, 3, 2  # --worker: an 18 GiB worker, 1 GiB for its own processes


# ---------------------------------------------------------------- the parent: sampling and summing

Sample = Tuple[int, int, int, int]  # pid, rss, private, uss (bytes; 0 where not read)


def sample(root: psutil.Process, uss: bool = False) -> List[Sample]:
    """The memory of root and every process below it now; a process that ends meanwhile is left out."""
    procs = [root]
    try:
        procs += root.children(recursive=True)
    except psutil.Error:
        pass
    rows = []
    for p in procs:
        try:
            m = p.memory_full_info() if uss else p.memory_info()
            rows.append((p.pid, m.rss, getattr(m, "private", 0), getattr(m, "uss", 0)))
        except psutil.Error:
            pass
    return rows


def find_search(root: psutil.Process) -> Optional[int]:
    """The pid of the search's process: the one whose command line holds CHILD (a venv's python.exe on Windows may be
    a launcher with the real interpreter as its child)."""
    try:
        procs = [root] + root.children(recursive=True)
    except psutil.Error:
        return None
    marked = {}
    for p in procs:
        try:
            if CHILD in p.cmdline():
                marked[p.pid] = p.ppid()
        except psutil.Error:
            continue
    # the lowest one: the interpreter below a launcher repeats the launcher's command line
    lowest = [pid for pid in marked if pid not in marked.values()]
    return lowest[0] if lowest else None


def totals(rows: Sequence[Sample], search: Optional[int]) -> Dict[str, int]:
    """One sample summed: the tree, the search's process, and the others below it (a child process of the search,
    none since store wave 4; a launcher above the search's process holds a few MB and counts in the tree only)."""
    main = [r for r in rows if r[0] == search]
    under = [r for r in rows[1:] if r[0] != search] if search is not None else []
    return {"rss": sum(r[1] for r in rows), "private": sum(r[2] for r in rows), "uss": sum(r[3] for r in rows),
            "main_rss": sum(r[1] for r in main), "main_private": sum(r[2] for r in main),
            "children_rss": sum(r[1] for r in under), "children_private": sum(r[2] for r in under),
            "processes": len(rows)}


def stage_at(events: Sequence[Tuple[float, str]], t: float) -> str:
    """The stage running at time t: the last event at or before it."""
    times = [e[0] for e in events]
    k = bisect.bisect_right(times, t) - 1
    return events[k][1] if k >= 0 else "before the search's first event"


def stage_key(label: str) -> str:
    """A stage's group in the peaks per stage: a hook as it is, else the step ("Step 5/5: saving the run ...")."""
    if label.startswith("HOOK"):
        return label.rsplit(" ", 1)[0]
    return label.split(" | ")[0].split("·")[-1].strip()[:40] or "between steps"


def summarise(series: Sequence[Tuple[float, Dict[str, int], int]], events: Sequence[Tuple[float, str]],
              uss: bool) -> Dict:
    """The peaks of a run's samples (t, totals, the machine's used bytes) in MB, where each fell, the peaks per stage
    (rss, private, the search's process rss, the children's private, uss) and, with uss, the unique sets' peak (the
    measure of LINE_BYTES) and their sum at the working sets' peak."""
    if not series:
        return {}
    top = max(series, key=lambda s: s[1]["rss"])
    out = {"samples": len(series),
           "peak_tree_rss_mb": round(top[1]["rss"] / MB), "peak_tree_rss_at": stage_at(events, top[0]),
           "peak_tree_rss_processes": top[1]["processes"],
           "peak_tree_private_mb": round(max(s[1]["private"] for s in series) / MB),
           "peak_main_rss_mb": round(max(s[1]["main_rss"] for s in series) / MB),
           "peak_children_rss_mb": round(max(s[1]["children_rss"] for s in series) / MB),
           "peak_children_private_mb": round(max(s[1]["children_private"] for s in series) / MB),
           "used_start_mb": round(series[0][2] / MB), "peak_used_mb": round(max(s[2] for s in series) / MB)}
    peaks: Dict[str, List[int]] = {}
    for t, x, _ in series:
        p = peaks.setdefault(stage_key(stage_at(events, t)), [0, 0, 0, 0, 0])
        for k, v in enumerate((x["rss"], x["private"], x["main_rss"], x["children_private"], x["uss"])):
            p[k] = max(p[k], v)
    out["stage_peaks_mb"] = {k: [round(v / MB) for v in p] for k, p in peaks.items()}
    if uss:
        utop = max(series, key=lambda s: s[1]["uss"])
        out.update(peak_tree_uss_mb=round(utop[1]["uss"] / MB), peak_tree_uss_at=stage_at(events, utop[0]),
                   tree_uss_at_rss_peak_mb=round(top[1]["uss"] / MB))
    return out


def option(args: Sequence[str], name: str) -> Optional[str]:
    """The value of a findaline.py option, given as "--name value" or "--name=value" (the last one wins)."""
    found = None
    for k, arg in enumerate(args):
        if arg == name and k + 1 < len(args):
            found = args[k + 1]
        elif arg.startswith(name + "="):
            found = arg[len(name) + 1:]
    return found


def absolute(args: Sequence[str], name: str) -> List[str]:
    """The options with the folder of `name` made absolute (the child runs in the tool's checkout, the parent
    reads the folder from its own working folder): "--name value" and "--name=value" alike."""
    out = list(args)
    for k, arg in enumerate(out):
        if arg == name and k + 1 < len(out):
            out[k + 1] = os.path.abspath(out[k + 1])
        elif arg.startswith(name + "="):
            out[k] = f"{name}={os.path.abspath(arg[len(name) + 1:])}"
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--cores", type=int, help="perf_profile.py's --cores (the VPS worker: 7)")
    ap.add_argument("--memory", type=int, help="perf_profile.py's --memory: the bytes available_memory answers")
    ap.add_argument("--worker", action="store_true", help="plan as the web worker: public limits, a slot's memory")
    ap.add_argument("--uss", action="store_true", help="also each process's unique set size (slower)")
    ap.add_argument("--remove-run", action="store_true", help="delete the run's folder once measured")
    ap.add_argument("args", nargs=argparse.REMAINDER, help="-- and the options of findaline.py")
    a = ap.parse_args()
    search_args = absolute(a.args[1:] if a.args[:1] == ["--"] else a.args, "--data-dir")
    a.out = os.path.abspath(a.out)
    os.makedirs(a.out, exist_ok=True)
    info_path = os.path.join(a.out, f"{a.name}-info.json")
    data_dir = option(search_args, "--data-dir")
    runs = os.path.join(data_dir, "runs") if data_dir else None
    before = set(os.listdir(runs)) if runs and os.path.isdir(runs) else set()
    pp = ["--out", a.out, "--name", a.name] + (["--cores", str(a.cores)] if a.cores else []) \
        + (["--memory", str(a.memory)] if a.memory else [])
    cmd = [sys.executable, os.path.abspath(__file__), CHILD, info_path] + (["--worker"] if a.worker else []) \
        + ["--"] + pp + ["--", *search_args]
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    tree = []
    started = time.time()
    with open(os.path.join(a.out, f"{a.name}.log"), "w", encoding="utf-8") as f:
        proc = subprocess.Popen(cmd, cwd=HERE, stdout=f, stderr=subprocess.STDOUT, env=env)
        root = psutil.Process(proc.pid)
        search = None
        while proc.poll() is None:
            if search is None:
                search = find_search(root)
            tree.append((time.time(), totals(sample(root, a.uss), search), psutil.virtual_memory().used))
            time.sleep(INTERVAL)
    info = json.load(open(info_path, encoding="utf-8")) if os.path.exists(info_path) else {}
    events = [tuple(e) for e in info.get("events", [])]
    with open(os.path.join(a.out, f"{a.name}-tree.csv"), "w", encoding="utf-8") as f:
        keys = ("processes", "rss", "private", "uss", "main_rss", "main_private", "children_rss", "children_private")
        f.write("t," + ",".join(f"{k}_mb" if k != "processes" else k for k in keys) + ",used_mb,stage\n")
        for t, x, used in tree:
            cells = [str(x[k] if k == "processes" else round(x[k] / MB)) for k in keys]
            f.write(f"{t - started:.2f},{','.join(cells)},{round(used / MB)},\"{stage_at(events, t)}\"\n")
    refused = info.get("refused")
    result = {"name": a.name, "args": search_args, "exit": proc.returncode, "wall_s": round(time.time() - started, 1),
              "outcome": "refused" if refused else "failed" if proc.returncode or not info else "done",
              "refused": refused, "warnings": [],
              "cores": a.cores, "memory": a.memory, "worker": a.worker, "uss": a.uss,
              "lock": os.environ.get("FINDALINE_TEST_LOCK"), "plan": info.get("plan"),
              "slot_memory": info.get("slot_memory"), "reducers": info.get("reducers"),
              **summarise(tree, events, a.uss)}
    new = sorted(n for n in (set(os.listdir(runs)) - before if runs and os.path.isdir(runs) else ())
                 if os.path.isfile(os.path.join(runs, n, "run.json")))
    if new:
        folder = os.path.join(runs, new[-1])
        with open(os.path.join(folder, "run.json"), encoding="utf-8") as f:
            meta = json.load(f)
        result.update(run=new[-1], summary=meta.get("summary"), store=meta.get("store"),
                      files={n: os.path.getsize(os.path.join(folder, n)) for n in os.listdir(folder)
                             if os.path.isfile(os.path.join(folder, n))})
        if a.remove_run:
            shutil.copy(os.path.join(folder, "run.json"), os.path.join(a.out, f"{a.name}-run.json"))
            shutil.rmtree(folder, ignore_errors=True)
    if not info:
        result["warnings"].append(f"no {info_path}: the hooks' record is missing (no stages, plan or reducers)")
    if not new and not refused:
        result["warnings"].append("no new run found in " + (runs or "a data folder: give --data-dir"))
    if len(new) > 1:
        result["warnings"].append(f"{len(new)} new runs in {runs}: measured {new[-1]}; measure one search at a time")
    with open(os.path.join(a.out, f"{a.name}.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, indent=1)
    s = result.get("summary") or {}
    print(json.dumps({k: result.get(k) for k in ("name", "outcome", "refused", "exit", "wall_s", "peak_tree_rss_mb",
                                                   "peak_tree_rss_at", "peak_tree_uss_mb", "peak_tree_uss_at")}
                     | {"lines": s.get("lines"), "found": s.get("found")}))
    for warning in result["warnings"]:
        print(f"WARNING: {warning}", file=sys.stderr)


# ---------------------------------------------------------------- the child: the search with hooks

def child(argv: List[str]):
    """The search's process: perf_profile.py run here (argv: <info.json> [--worker] -- <its arguments>), with the
    hooks of the module docstring; their record is written to info.json when it ends."""
    info_path, rest = argv[0], argv[1:]
    worker = "--worker" in rest[:rest.index("--")]
    rest = rest[rest.index("--") + 1:]
    sys.path.insert(0, HERE)
    info: Dict = {"events": [], "reducers": [], "worker": worker}

    def event(label):
        info["events"].append([time.time(), label])

    last = {"key": None}

    def listener(state):
        key = (state["step"], state["bar"], state["stage"], bool(state["done"]))
        if key != last["key"]:
            last["key"] = key
            event(f"{state['step']} | {state['bar']} {state['stage']}{' (done)' if state['done'] else ''}")

    from progress import progress
    progress.subscribe(listener)
    import linestore
    import mapping
    import samelines
    import search
    from settings import Limits
    slot = search.slot_memory(Limits(compute_slots=COMPUTE_SLOTS, download_slots=DOWNLOAD_SLOTS),
                              total=int(SLOTS_FREE_GIB * GIB)) if worker else None
    info["slot_memory"] = slot
    plan_search = search.plan_search

    def planned(params, paths, on_event=None, **kw):
        # a line's profile (profile_of_line and its kin, also at a tiled search's join) plans a patch of its own
        # with with_margin=False: neither recorded nor given the worker's limits
        if kw.get("with_margin", True) is False:
            return plan_search(params, paths, on_event, **kw)
        if worker:
            kw.update(limits=Limits.load(public=True), memory=slot)
        plan = plan_search(params, paths, on_event, **kw)
        tiles = [t for _, t in plan.tiles] if plan.tiles else []
        whole = plan.grid.width * plan.grid.height
        info["plan"] = {"grid_px": whole, "tiles": len(tiles),
                        "tile_px_max": max((t.width * t.height for t in tiles), default=whole),
                        "memory": plan.memory, "square": plan.square,
                        "early_check": search._early_check(plan, 0, 0) is not None,
                        "lines_max": plan.limits.lines_max if plan.limits else None}
        return plan

    search.plan_search = planned
    counts = samelines.BestPerSquarePair.counts

    def counted(self):
        c = counts(self)
        info["reducers"].append(dict(c, t=time.time()))
        return c

    samelines.BestPerSquarePair.counts = counted

    def hooked(module, name, after=None):
        real = getattr(module, name)

        def run(*a, **kw):
            event(f"HOOK {module.__name__}.{name} start")
            try:
                out = real(*a, **kw)
                if after:
                    after(*a)
                return out
            finally:
                event(f"HOOK {module.__name__}.{name} end")
        setattr(module, name, run)

    def refusals(name):
        real = getattr(search, name)

        def run(*a, **kw):
            try:
                return real(*a, **kw)
            except search.SearchError as e:
                if kw.get("with_margin", True) is not False:  # not a line's profile (see planned)
                    info["refused"] = {"code": getattr(e, "code", None), "message": str(e)[:300], "at": name}
                raise
        setattr(search, name, run)

    for name in HOOKED_SEARCH:  # as findaline.py calls them: a refusal ends the search with exit 0 in perf_profile
        refusals(name)
    hooked(mapping, "view_columns")  # the store's view columns, just before linestore.write
    hooked(linestore, "write")
    event("search start")
    sys.argv = [os.path.join(HERE, "tools", "perf_profile.py"), *rest]
    try:
        runpy.run_path(sys.argv[0], run_name="__main__")
    finally:
        event("search end")
        with open(info_path, "w", encoding="utf-8") as f:
            json.dump(info, f)


if __name__ == "__main__":
    sys.path.insert(0, HERE)
    from progress import utf8_output
    utf8_output()  # the stage labels and warnings in UTF-8, not the Windows code page
    if len(sys.argv) > 1 and sys.argv[1] == CHILD:
        child(sys.argv[2:])
    else:
        main()
