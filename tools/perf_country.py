"""
Run by hand: the measurements for a country-wide, offline layer of line and spot counts
(docs/country-precompute.md): how much data and computing it would take.

bench builds a synthetic area offline (the Żabi Koń clip of tests/data mirrored into an N x N
mosaic, 4800 x 4800 px by default), runs a tiny search to compile numba, then two fixed searches
through perf_profile.py (S: short lines, M: long lines with the sag estimator) and the S search K
times at once as processes. Writes <out>/bench.json and prints a summary; no network. Meant to
compare machines: about 5-10 minutes on 6 cores.

    uv run tools/perf_country.py bench --out <scratch>/bench [--processes 1 3 6] [--grid 8]

profile runs one search through perf_profile.py (its stage table) and records it with its grid,
tiles, funnel and counts into <out>/samples.json under NAME (an entry of that name is replaced).
--tension-by-length gives the sag estimator a pretension that grows with the span (metres:kN,
linear between the points, clamped at both ends) instead of --pretension.

    uv run tools/perf_country.py profile --out <scratch>/pl --name tatry-1m [--cores 6] \\
        [--tension-by-length 300:2.5,1500:6,5000:15] -- --lat .. --lon .. --data-dir <scratch>/data ...

compare counts the lines and spots of runs of samples.json per cell and length band against a
reference run (a finer grid, other parameters): the ratio of the totals, the Spearman correlation
of the spots per cell, the share of cells with a spot that the other run lacks.

    uv run tools/perf_country.py compare --samples <scratch>/pl/samples.json tatry-1m tatry-2m [--cells 500 1000]

cube counts how many keys (cell, filter bins) a sparse counter cube of the lines and spots would
hold, per km², and the bytes of an 8-byte key with a 4-byte count.

    uv run tools/perf_country.py cube --samples <scratch>/pl/samples.json tatry-1m [--cell 1000] [--dims length clearance]

estimate turns the samples into country totals: for each country of an inputs file (its area,
its terrain classes and the samples standing for them, its data per km² and its download service),
length variant (bands S, M, L), grid strategy, with and without the DSM, machine (its bench.json
against the reference's) and scenario (low, high: the samples of each class): the data, the
download days and the computing days of a run that keeps only counts. A sample is named
<place>-<band>-<res>m; a missing resolution is scaled from the place's nearest one by the median
ratio of the places measured at both.

    uv run tools/perf_country.py estimate --inputs docs/country-precompute/inputs.json \\
        --samples <scratch>/samples/samples.json [--json PATH]

The options after "--" are findaline.py's; --no-plot, --yes and --ortho never are added. Give
--data-dir there to keep the runs out of the repository's runs/.
"""

import argparse
import csv
import dataclasses
import json
import math
import os
import platform
import re
import subprocess
import sys
import time
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import psutil

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "tools"))

CLIP_NMT = os.path.join(HERE, "tests", "data", "zabi_kon_nmt.tif")
CLIP_NMPT = os.path.join(HERE, "tests", "data", "zabi_kon_nmpt.tif")
# Length bands of compare and cube (m): [low, high)
BANDS = [(30, 60), (60, 100), (100, 150), (150, 300), (300, 600), (600, 1000), (1000, 2000), (2000, 3000),
         (3000, 5000)]
INF = math.inf
# The edges of the bins of cube's dimensions: a value v is in bin k when edges[k] <= v < edges[k + 1];
# values below the first or above the last edge go to the first or last bin, a missing value
# (an empty cell of lines.csv) to its own bin -1
EDGES = {
    "length": [b[0] for b in BANDS] + [BANDS[-1][1]],
    "clearance": [0, 2, 5, 10, 20, INF],
    "height": [0, 10, 20, 50, 100, INF],
    "prominence": [0, 5, 10, 20, 50, INF],
    "wall": [0, 30, 45, 60, 90],
}
FLAGS = ("trees", "water")  # cube's boolean dimensions: over trees or buildings, over water
DIMS = tuple(EDGES) + FLAGS
KEY_BYTES, COUNT_BYTES = 8, 4  # a sparse store: a 64-bit key and a 32-bit count
# Offline: the water mask and the gap filling would ask OpenStreetMap or Copernicus
OFFLINE = ["--water", "off", "--fill-gaps", "off"]


# ---------------------------------------------------------------- machine and commit

def cpu_name() -> str:
    """The processor's name: PowerShell's Win32_Processor (wmic as fallback) on Windows,
    /proc/cpuinfo on Linux, sysctl on macOS; platform.processor() otherwise."""
    commands = {"win32": [["powershell", "-NoProfile", "-Command",
                           "(Get-CimInstance Win32_Processor | Select-Object -First 1).Name"],
                          ["wmic", "cpu", "get", "name"]],
                "darwin": [["sysctl", "-n", "machdep.cpu.brand_string"]]}
    if sys.platform.startswith("linux"):
        try:
            with open("/proc/cpuinfo", encoding="utf-8") as f:
                for line in f:
                    if line.lower().startswith("model name"):
                        return line.split(":", 1)[1].strip()
        except OSError:
            pass
    for command in commands.get(sys.platform, []):
        try:
            out = subprocess.run(command, capture_output=True, text=True, timeout=30).stdout
        except (OSError, subprocess.SubprocessError):
            continue
        lines = [line.strip() for line in out.splitlines() if line.strip() and line.strip().lower() != "name"]
        if lines:
            return lines[0]
    return platform.processor() or "unknown"


def machine() -> Dict:
    return {"cpu": cpu_name(), "physical_cores": psutil.cpu_count(logical=False),
            "logical_cores": psutil.cpu_count(), "ram_gb": round(psutil.virtual_memory().total / 2**30, 1),
            "os": platform.platform(), "python": platform.python_version()}


def commit() -> Optional[str]:
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=HERE, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    return (out.stdout.strip() or None) if out.returncode == 0 else None


# ---------------------------------------------------------------- the synthetic mosaic

def mosaic(out: str, n: int) -> Tuple[str, str, Tuple[float, float]]:
    """The clip's terrain and surface mirrored into n x n copies: a copy in an odd row is flipped
    upside down, one in an odd column left to right, so every seam joins equal pixels. Written as
    DEFLATE GeoTIFFs with the clip's CRS and top-left corner. Returns (terrain, surface, centre as
    (easting, northing))."""
    import rasterio as rio
    os.makedirs(out, exist_ok=True)
    paths = []
    for clip, name in ((CLIP_NMT, "nmt"), (CLIP_NMPT, "nmpt")):
        with rio.open(clip) as src:
            band, profile, transform = src.read(1), src.profile, src.transform
        rows = [np.hstack([band[::-1 if i % 2 else 1, ::-1 if j % 2 else 1] for j in range(n)]) for i in range(n)]
        whole = np.vstack(rows)
        profile.update(width=whole.shape[1], height=whole.shape[0], compress="deflate", tiled=True,
                       blockxsize=256, blockysize=256, BIGTIFF="IF_SAFER")
        path = os.path.join(out, f"mosaic{n}_{name}.tif")
        with rio.open(path, "w", **profile) as dst:
            dst.write(whole, 1)
        paths.append(path)
    centre = (transform.c + transform.a * whole.shape[1] / 2, transform.f + transform.e * whole.shape[0] / 2)
    return paths[0], paths[1], centre


# ---------------------------------------------------------------- perf_profile.py

def run_profile(out: str, name: str, search_args: List[str], cores: Optional[int] = None) -> Dict:
    """One search through perf_profile.main (in this process); its stages and totals from the CSV
    files it writes."""
    import perf_profile
    argv = sys.argv
    sys.argv = ["perf_profile.py", "--out", out, "--name", name] + (["--cores", str(cores)] if cores else []) \
        + ["--", *search_args]
    try:
        perf_profile.main()
    finally:
        sys.argv = argv
    return read_profile(out, name)


def read_profile(out: str, name: str) -> Dict:
    """{"stages": [...], "total": {...}} of perf_profile's <name>-stages.csv and <name>.csv."""
    stages = []
    with open(os.path.join(out, f"{name}-stages.csv"), newline="") as f:
        for row in csv.DictReader(f):
            number = lambda k: float(row[k]) if row[k] else None  # noqa: E731
            stages.append({"stage": row["stage"], "wall_s": number("wall_s"), "cpu_s": number("cpu_s"),
                           "cores": number("cores"), "peak_rss_mb": number("peak_rss_mb")})
    with open(os.path.join(out, f"{name}.csv"), newline="") as f:
        samples = [(float(r["t"]), float(r["cpu_s"]), float(r["rss_mb"])) for r in csv.DictReader(f)]
    total = {"wall_s": round(samples[-1][0] - samples[0][0], 2), "cpu_s": round(samples[-1][1] - samples[0][1], 2),
             "peak_rss_mb": max(s[2] for s in samples)}
    return {"stages": stages, "total": total}


# ---------------------------------------------------------------- T(L) and the plan

def parse_tension(text: str) -> List[Tuple[float, float]]:
    """"300:2.5,1500:6" -> [(300, 2.5), (1500, 6)], sorted by the span."""
    points = []
    for part in text.split(","):
        span, kn = part.split(":")
        points.append((float(span), float(kn)))
    if not points:
        raise ValueError("--tension-by-length needs at least one span:kN point")
    return sorted(points)


def tension_at(points: Sequence[Tuple[float, float]], span: float) -> float:
    """The pretension (kN) at a span: linear between the points, clamped at both ends."""
    return float(np.interp(span, [p[0] for p in points], [p[1] for p in points]))


def tension_table(points: Sequence[Tuple[float, float]], base=None):
    """A subclass of sag.EnvelopeTable whose envelope of each span is solved with the pretension
    T(span). linesearch reads only min() and rig.fall_zone of the table besides __call__, and the
    final decision calls the table itself, so the search uses T(span) throughout."""
    import sag as sg
    from progress import progress
    base = base or sg.EnvelopeTable

    class TensionTable(base):
        def __init__(self, rig, min_span: float, max_span: float):  # base.__init__ with rig_for(span)
            self.rig = rig
            rig_for = lambda span: dataclasses.replace(rig, pretension=tension_at(points, span))  # noqa: E731
            n = max(2, math.ceil(math.log(max_span / min_span) / math.log(self.SPAN_STEP)) + 1)
            self.spans = min_span * self.SPAN_STEP ** np.arange(n)
            self.fractions = np.linspace(0, 1, sg.ENVELOPE_POINTS + 2)
            self.sag = np.empty((len(self.spans), len(self.RATIOS), len(self.fractions)))
            progress.compute.start("sag estimator table", len(self.spans), unit="length")
            for i, span in enumerate(self.spans):
                for j, ratio in enumerate(self.RATIOS):
                    self.sag[i, j] = sg.envelope(span, ratio * span, rig_for(span))[1]
                progress.compute.update(1)
            progress.compute.finish()

    return TensionTable


class Hooks:
    """The T(L) table assigned as sag.EnvelopeTable (search.py looks it up at call time) and
    search.plan_search wrapped to keep the Plan; uninstall puts both back."""

    def __init__(self, tension: Optional[str]):
        import sag as sg
        import search
        self.sg, self.search = sg, search
        self.tension = parse_tension(tension) if tension else None
        self.table, self.plan_search = sg.EnvelopeTable, search.plan_search
        self.plan = None

    def _plan_search(self, *args, **kwargs):
        self.plan = self.plan_search(*args, **kwargs)
        return self.plan

    def install(self):
        if self.tension:
            self.sg.EnvelopeTable = tension_table(self.tension, self.table)
        self.search.plan_search = self._plan_search

    def uninstall(self):
        self.sg.EnvelopeTable, self.search.plan_search = self.table, self.plan_search


def plan_grid(plan) -> Dict:
    import area as ar
    if isinstance(plan.area, ar.Circle):
        km2 = math.pi * plan.params.radius ** 2 / 1e6
    else:
        km2 = ar.size_km2(plan.area.geometry)
    return {"width": plan.grid.width, "height": plan.grid.height, "res": plan.resolution, "crs": plan.crs,
            "tiles": len(plan.tiles) if plan.tiles else 1, "area_km2": round(km2, 4)}


def option(args: List[str], name: str) -> Optional[str]:
    """The value of a findaline.py option in args (--name value or --name=value)."""
    for k, arg in enumerate(args):
        if arg == name and k + 1 < len(args):
            return args[k + 1]
        if arg.startswith(name + "="):
            return arg.split("=", 1)[1]
    return None


def newest_run(data_dir: str, since: float = 0) -> Optional[str]:
    """The newest run of the data folder saved at or after since (a time.time()); None if there is
    none: a search that found no lines saves no run."""
    runs = os.path.join(data_dir, "runs")
    folders = [os.path.join(runs, d) for d in os.listdir(runs)
               if d != "_viewer" and os.path.isfile(os.path.join(runs, d, "run.json"))] if os.path.isdir(runs) else []
    folders = [d for d in folders if os.path.getmtime(os.path.join(d, "run.json")) >= since]
    return max(folders, key=lambda d: os.path.getmtime(os.path.join(d, "run.json"))) if folders else None


def load_samples(path: str) -> Dict:
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def profile(out: str, name: str, search_args: List[str], cores: Optional[int] = None,
            tension: Optional[str] = None) -> Dict:
    """One measured search, recorded into <out>/samples.json under name."""
    os.makedirs(out, exist_ok=True)
    hooks = Hooks(tension)
    hooks.install()
    started = time.time()
    try:
        measured = run_profile(out, name, list(search_args), cores)
    finally:
        hooks.uninstall()
    if hooks.plan is None:
        raise SystemExit("the search ended before its plan")
    data_dir = os.path.abspath(option(search_args, "--data-dir") or HERE)
    run = newest_run(data_dir, since=started)
    summary = {"lines": 0, "spots": 0}
    if run is not None:
        with open(os.path.join(run, "run.json"), encoding="utf-8") as f:
            meta = json.load(f)
        summary = {"lines": meta["summary"]["lines"], "spots": meta["summary"]["spots"]}
    entry = {"args": list(search_args), "cores": cores, "tension_by_length": tension, "data_dir": data_dir,
             "run": run, "machine": machine(), "commit": commit(), "summary": summary,
             "grid": plan_grid(hooks.plan), "funnel": dict(hooks.plan.funnel), **measured}
    if run is None:  # the stages and the funnel still tell the cost of the search
        entry["note"] = "no run saved: the search found no lines (or it stopped, see its output)"
    path = os.path.join(out, "samples.json")
    samples = load_samples(path)
    samples[name] = entry
    with open(path, "w", encoding="utf-8") as f:
        json.dump(samples, f, indent=1)
    print(f"\n{name}: {entry['summary']['lines']} lines, {entry['summary']['spots']} spots, "
          f"{entry['grid']['width']} x {entry['grid']['height']} px, {entry['grid']['tiles']} tile(s), "
          f"{entry['total']['wall_s']:.0f} s -> {path}")
    return entry


# ---------------------------------------------------------------- bench

def bench_args(nmt: str, nmpt: str, centre: Tuple[float, float], data_dir: str, model: str) -> List[str]:
    """The options of the fixed searches S (short lines) and M (long lines, the sag estimator)."""
    easting, northing = centre
    args = ["--elevation-file", nmt, "--surface-file", nmpt, "--northing", f"{northing:.1f}",
            "--easting", f"{easting:.1f}", "--radius", "2000", "--resolution", "1", "--slope-threshold", "60",
            "--no-html", "--data-dir", data_dir, *OFFLINE]
    if model == "S":
        return args + ["--min-length", "30", "--max-length", "300"]
    return args + ["--min-length", "300", "--max-length", "2000", "--model", "sag", "--pretension", "6"]


def parallel(out: str, make_args, k: int, threads: int) -> Dict:
    """A search k times at once as processes, each with its own data folder (make_args(data folder):
    its options)."""
    env = {**os.environ, "FINDALINE_PROGRESS": "text", "PYTHONIOENCODING": "utf-8"}
    processes = []
    started = time.monotonic()
    for i in range(k):
        data_dir = os.path.join(out, f"parallel-{k}", f"data-{i}")
        os.makedirs(data_dir, exist_ok=True)
        log = open(os.path.join(out, f"parallel-{k}", f"search-{i}.log"), "w", encoding="utf-8")
        command = [sys.executable, os.path.join(HERE, "findaline.py"), *make_args(data_dir), "--threads", str(threads),
                   "--no-plot", "--yes", "--ortho", "never"]
        processes.append((subprocess.Popen(command, cwd=HERE, env=env, stdout=log, stderr=subprocess.STDOUT),
                          log, time.monotonic()))
    times = []
    for process, log, start in processes:
        code = process.wait()
        times.append(time.monotonic() - start)
        log.close()
        if code != 0:
            raise SystemExit(f"a parallel search ended with {code}: see {log.name}")
    wall = time.monotonic() - started
    return {"K": k, "threads": threads, "wall_s": round(wall, 2), "per_search_s": round(sum(times) / k, 2)}


def bench(out: str, processes: Optional[List[int]], n: int) -> Dict:
    out = os.path.abspath(out)
    os.makedirs(out, exist_ok=True)
    if 2000 + 300 > n * 300:  # the circle and its margin (the prominence span) within the mosaic
        raise SystemExit(f"--grid {n}: the circle of 2000 m and its margin of 300 m need at least --grid 8")
    print(f"Mosaic of {n} x {n} clips...")
    nmt, nmpt, centre = mosaic(os.path.join(out, "mosaic"), n)
    print("Warm-up (numba compiles)...")
    clip = ["--elevation-file", CLIP_NMT, "--northing", "254608", "--easting", "553966", "--radius", "100",
            "--no-html", "--data-dir", os.path.join(out, "data-warmup"), *OFFLINE]
    run_profile(os.path.join(out, "warmup"), "warmup", clip)
    searches = {}
    for key in ("S", "M"):
        print(f"\nSearch {key}...")
        searches[key] = run_profile(out, key, bench_args(nmt, nmpt, centre, os.path.join(out, f"data-{key}"), key))
    physical = psutil.cpu_count(logical=False) or 1
    counts = processes or sorted({1, max(1, physical // 2), physical})
    results = []
    for k in counts:
        print(f"\n{k} S searches at once...")
        results.append(parallel(out, lambda data_dir: bench_args(nmt, nmpt, centre, data_dir, "S"), k,
                                max(1, physical // k)))
    report = {"version": 1, "commit": commit(), "machine": machine(), "searches": searches, "parallel": results}
    with open(os.path.join(out, "bench.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, indent=1)
    m = report["machine"]
    print(f"\n{m['cpu']}, {m['physical_cores']} cores ({m['logical_cores']} logical), {m['ram_gb']} GB")
    for key, s in searches.items():
        t = s["total"]
        print(f"  {key}: {t['wall_s']:.1f} s wall, {t['cpu_s']:.1f} s CPU, peak {t['peak_rss_mb']:.0f} MB")
    for r in results:
        print(f"  {r['K']} at once ({r['threads']} threads each): {r['wall_s']:.1f} s, "
              f"{r['per_search_s']:.1f} s per search, {3600 * r['K'] / r['wall_s']:.0f} searches per hour")
    print(f"-> {os.path.join(out, 'bench.json')}")
    return report


# ---------------------------------------------------------------- lines.csv

def read_lines(run: str) -> Dict[str, np.ndarray]:
    """The columns of a run's lines.csv that compare and cube use, as arrays (NaN: empty)."""
    numbers = ("group", "length_m", "clearance_m", "water_m", "height_max_m", "anchor1_northing",
               "anchor1_easting", "anchor1_wall_angle", "anchor2_wall_angle", "anchor1_prominence_m",
               "anchor2_prominence_m")
    flags = ("representative", "over_trees_buildings")
    values = {k: [] for k in numbers + flags}
    if run is None:  # a search without lines (profile saved no run)
        columns = {k: np.zeros(0, dtype=float) for k in numbers}
        columns.update({k: np.zeros(0, dtype=bool) for k in flags})
        columns["group"] = columns["group"].astype(np.int64)
        return columns
    with open(os.path.join(run, "lines.csv"), newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            for k in numbers:
                values[k].append(float(row[k]) if row[k] else math.nan)
            for k in flags:
                values[k].append(row[k] == "True")
    columns = {k: np.array(values[k], dtype=float) for k in numbers}
    columns.update({k: np.array(values[k], dtype=bool) for k in flags})
    columns["group"] = columns["group"].astype(np.int64)
    return columns


def run_crs(run: Optional[str]) -> Optional[str]:
    """The CRS of a run's coordinates; None for a search without lines (no run)."""
    if run is None:
        return None
    with open(os.path.join(run, "run.json"), encoding="utf-8") as f:
        return json.load(f)["center"]["crs"]


def cells_of(lines: Dict[str, np.ndarray], cell: float) -> np.ndarray:
    """The cell of each line: (column, row) of its first anchor, in the run's CRS."""
    return np.column_stack([np.floor(lines["anchor1_easting"] / cell),
                            np.floor(lines["anchor1_northing"] / cell)]).astype(np.int64)


def parse_bands(texts: Optional[List[str]]) -> List[Tuple[float, float]]:
    if not texts:
        return list(BANDS)
    return [tuple(float(v) for v in t.split("-")) for t in texts]


# ---------------------------------------------------------------- compare

def cell_counts(cells: np.ndarray) -> Dict[Tuple[int, int], int]:
    keys, counts = np.unique(cells, axis=0, return_counts=True) if len(cells) else (np.empty((0, 2)), [])
    return {(int(a), int(b)): int(c) for (a, b), c in zip(keys, counts)}


def compare(samples: Dict, ref: str, others: List[str], cells: List[float],
            bands: List[Tuple[float, float]]) -> Dict:
    """Per band (and "all") and cell size: the lines and spots of each run, their ratio to ref,
    the Spearman correlation of the spots per cell (over the cells with a line of the band in any
    of the runs, zeros included), the share of ref's cells with a spot where the other run has
    none ("lost") and of the other's cells with a spot where ref has none ("new")."""
    from scipy.stats import spearmanr
    names = [ref, *others]
    missing = [n for n in names if n not in samples]
    if missing:
        raise SystemExit(f"not in samples.json: {', '.join(missing)}")
    runs = {n: samples[n]["run"] for n in names}
    crs = {n: run_crs(r) for n, r in runs.items() if r is not None}
    if len(set(crs.values())) > 1:
        raise SystemExit("the runs use different coordinate systems: "
                         + ", ".join(f"{n} {c}" for n, c in crs.items()))
    lines = {n: read_lines(r) for n, r in runs.items()}
    result = {"ref": ref, "others": others, "crs": next(iter(crs.values()), None), "rows": []}
    for cell in cells:
        for band in [None, *bands]:
            per_run = {}
            for n, ls in lines.items():
                keep = np.ones(len(ls["length_m"]), bool) if band is None else \
                    (ls["length_m"] >= band[0]) & (ls["length_m"] < band[1])
                c = cells_of(ls, cell)
                per_run[n] = {"lines": int(keep.sum()), "spots": int((keep & ls["representative"]).sum()),
                              "line_cells": cell_counts(c[keep]),
                              "spot_cells": cell_counts(c[keep & ls["representative"]])}
            every = sorted(set().union(*(set(p["line_cells"]) | set(p["spot_cells"]) for p in per_run.values())))
            r = per_run[ref]
            for other in others:
                o = per_run[other]
                a = np.array([r["spot_cells"].get(k, 0) for k in every])
                b = np.array([o["spot_cells"].get(k, 0) for k in every])
                rho = None
                if len(every) > 1 and a.std() > 0 and b.std() > 0:
                    rho = round(float(spearmanr(a, b).statistic), 4)
                ratio = lambda x, y: round(x / y, 4) if y else None  # noqa: E731
                result["rows"].append({
                    "cell": cell, "band": "all" if band is None else f"{band[0]:g}-{band[1]:g}", "other": other,
                    "ref_lines": r["lines"], "other_lines": o["lines"], "lines_ratio": ratio(o["lines"], r["lines"]),
                    "ref_spots": r["spots"], "other_spots": o["spots"], "spots_ratio": ratio(o["spots"], r["spots"]),
                    "cells": len(every), "spearman": rho,
                    "lost": ratio(int(((a > 0) & (b == 0)).sum()), int((a > 0).sum())),
                    "new": ratio(int(((b > 0) & (a == 0)).sum()), int((b > 0).sum()))})
    return result


def markdown(rows: List[Dict], columns: List[str]) -> str:
    text = lambda v: "" if v is None else f"{v:g}" if isinstance(v, float) else str(v)  # noqa: E731
    lines = ["| " + " | ".join(columns) + " |", "|" + "---|" * len(columns)]
    lines += ["| " + " | ".join(text(r[c]) for c in columns) + " |" for r in rows]
    return "\n".join(lines)


# ---------------------------------------------------------------- cube

def bins(values: np.ndarray, edges: Sequence[float]) -> np.ndarray:
    """The bin of each value (EDGES): clamped to the first and last bin, -1 for NaN."""
    inner = np.asarray(edges[1:-1], dtype=float)
    out = np.searchsorted(inner, values, side="right").astype(np.int64)
    out[np.isnan(values)] = -1
    return out


def line_values(ls: Dict[str, np.ndarray]) -> Dict[str, np.ndarray]:
    """Each line's value per dimension: the prominence is the smaller of its anchors', the wall
    angle the larger (a line passes a filter when both anchors do)."""
    return {"length": ls["length_m"], "clearance": ls["clearance_m"], "height": ls["height_max_m"],
            "prominence": np.fmin(ls["anchor1_prominence_m"], ls["anchor2_prominence_m"]),
            "wall": np.fmax(ls["anchor1_wall_angle"], ls["anchor2_wall_angle"]),
            "trees": ls["over_trees_buildings"], "water": ls["water_m"] > 0}


def spot_values(ls: Dict[str, np.ndarray], values: Dict[str, np.ndarray]) -> Tuple[np.ndarray, Dict[str, np.ndarray]]:
    """Each group once: the index of its representative (its cell and length) and per dimension
    the value of the group's best member for a lower-bound filter: the largest clearance, height
    and prominence, the smallest wall angle, "not over trees" and "not over water" when any member
    is not. A filter that keeps any member keeps the spot."""
    group = ls["group"]
    order = np.argsort(group, kind="stable")
    starts = np.flatnonzero(np.r_[True, group[order][1:] != group[order][:-1]]) if len(group) else np.empty(0, int)
    rep = np.flatnonzero(ls["representative"])
    rep = rep[np.argsort(group[rep], kind="stable")]
    best = {"length": values["length"][rep]}
    for name, reduce in (("clearance", np.fmax), ("height", np.fmax), ("prominence", np.fmax), ("wall", np.fmin)):
        best[name] = reduce.reduceat(values[name][order], starts) if len(starts) else np.empty(0)
    for name in FLAGS:  # over trees (water) only when every member is
        best[name] = np.logical_and.reduceat(values[name][order], starts) if len(starts) else np.empty(0, bool)
    return rep, best


def keys(cells: np.ndarray, values: Dict[str, np.ndarray], dims: Sequence[str]) -> int:
    """The number of distinct (cell, bins of dims) keys."""
    columns = [cells[:, 0], cells[:, 1]]
    for d in dims:
        columns.append(values[d].astype(np.int64) if d in FLAGS else bins(values[d], EDGES[d]))
    if not len(cells):
        return 0
    return len(np.unique(np.column_stack(columns), axis=0))


def cube(samples: Dict, names: List[str], cell: float, dims: Sequence[str]) -> Dict:
    """Per sample: the non-empty keys of a sparse cube of the lines and of the spots per km²
    (the grid's area_km2) and the bytes per km² of KEY_BYTES + COUNT_BYTES per key."""
    unknown = [d for d in dims if d not in DIMS]
    if unknown:
        raise SystemExit(f"unknown dimensions: {', '.join(unknown)} (choose from {', '.join(DIMS)})")
    rows = []
    for name in names:
        if name not in samples:
            raise SystemExit(f"not in samples.json: {name}")
        sample = samples[name]
        ls = read_lines(sample["run"])
        values = line_values(ls)
        cells = cells_of(ls, cell)
        rep, best = spot_values(ls, values)
        km2 = sample["grid"]["area_km2"]
        line_keys, spot_keys = keys(cells, values, dims), keys(cells[rep], best, dims)
        per = lambda v: round(v / km2, 4) if km2 else None  # noqa: E731
        rows.append({"name": name, "cell": cell, "dims": " ".join(dims), "area_km2": km2,
                     "lines": len(ls["length_m"]), "line_keys": line_keys, "line_keys_km2": per(line_keys),
                     "line_bytes_km2": per(line_keys * (KEY_BYTES + COUNT_BYTES)),
                     "spots": len(rep), "spot_keys": spot_keys, "spot_keys_km2": per(spot_keys),
                     "spot_bytes_km2": per(spot_keys * (KEY_BYTES + COUNT_BYTES))})
    return {"cell": cell, "dims": list(dims), "edges": {d: [e if e != INF else "inf" for e in EDGES[d]] for d in dims if d in EDGES}, "rows": rows}


# ---------------------------------------------------------------- main

# ---------------------------------------------------------------- estimate

# What a country run that keeps only counts takes of a sample's stages (perf_profile's labels):
# the grid (steps 1-2 without the downloads, which belong to the download estimate), the line
# search (step 3) and the counts (step 4's groups and metres over water). The coordinates,
# profiles and files of steps 4-5 are not needed, nor the start (imports, plan, index answers)
GRID = re.compile(r"^Step [12]: (Compute|\(between bars\))")
LINE = re.compile(r"^Step 3: ")
COUNT = re.compile(r"^Step 4: Compute (grouping lines|over water)")
DOWNLOAD = re.compile(r"Download")
STEP1_BETWEEN = "Step 1: (between bars)"  # also holds the index answers when the sample downloaded
LINE_BYTES = 450  # search.LINE_BYTES at 221dd10: the lines of a tile while it is counted
SERIAL_EFFICIENCY = 0.85  # processes at once on as many cores: the share of a core each keeps
OVERLAP_SHARE = 0.25  # the part of the shorter of serial and parallel time that the longer does not hide


def sample_geometry(args: List[str]):
    """A sample's search area in metres: a circle of --radius around (0, 0), or the polygon of
    --area in the UTM zone of its centre."""
    from shapely.geometry import Point, shape
    from shapely.ops import transform, unary_union
    from pyproj import Transformer
    radius = option(args, "--radius")
    path = option(args, "--area")
    if path and os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        features = data["features"] if data.get("type") == "FeatureCollection" else [data]
        geometry = unary_union([shape(f.get("geometry", f)) for f in features])
        c = geometry.centroid
        utm = f"EPSG:{32600 + int((c.x + 180) // 6) + 1 if c.y >= 0 else 32700 + int((c.x + 180) // 6) + 1}"
        return transform(Transformer.from_crs("EPSG:4326", utm, always_xy=True).transform, geometry)
    return Point(0, 0).buffer(float(radius or 1000), 256)


def edge_fraction(geometry, reach: float, n: int = 1500, m: int = 48, seed: int = 0) -> float:
    """The mean share of the disc of radius reach around a uniform point of the area that lies
    inside the area (Monte Carlo): what a sample finds of partners and lines near its edge, against
    a point deep inside a country, where nothing is cut off."""
    from shapely import contains_xy
    if reach <= 0:
        return 1.0
    rng = np.random.default_rng(seed)
    left, bottom, right, top = geometry.bounds
    points = np.empty((0, 2))
    while len(points) < n:
        xy = rng.uniform((left, bottom), (right, top), size=(4 * n, 2))
        points = np.vstack([points, xy[contains_xy(geometry, xy[:, 0], xy[:, 1])]])
    points = points[:n]
    radius, angle = reach * np.sqrt(rng.uniform(size=(n, m))), rng.uniform(0, 2 * np.pi, size=(n, m))
    x, y = points[:, :1] + radius * np.cos(angle), points[:, 1:] + radius * np.sin(angle)
    return float(contains_xy(geometry, x.ravel(), y.ravel()).mean())


def sample_metrics(sample: Dict, reach: float) -> Dict:
    """Per Mpx and per km² what a sample measured (on its machine, all threads, one at a time):
    the grid's wall seconds, the line search's CPU and wall seconds, the counts' seconds, the
    lines and spots; the km² values divided by edge_fraction for the band's longest line."""
    stages = sample["stages"]
    wall = lambda s: s["wall_s"] or 0.0  # noqa: E731
    downloaded = sum(wall(s) for s in stages if DOWNLOAD.search(s["stage"]))
    grid = sum(wall(s) for s in stages if GRID.match(s["stage"]) and not DOWNLOAD.search(s["stage"])
               and not (s["stage"] == STEP1_BETWEEN and downloaded > 1))
    line_cpu = sum(s["cpu_s"] or 0.0 for s in stages if LINE.match(s["stage"]))
    line_wall = sum(wall(s) for s in stages if LINE.match(s["stage"]))
    count = sum(wall(s) for s in stages if COUNT.match(s["stage"]))
    mpx = sample["grid"]["width"] * sample["grid"]["height"] / 1e6
    km2 = sample["grid"]["area_km2"]
    f = edge_fraction(sample_geometry(sample["args"]), reach)
    return {"mpx": mpx, "km2": km2, "edge_fraction": round(f, 4), "grid_s_per_mpx": grid / mpx,
            "line_cpu_per_km2": line_cpu / (km2 * f), "line_cores": line_cpu / line_wall if line_wall else None,
            "count_s_per_km2": count / (km2 * f), "lines_per_km2": sample["summary"]["lines"] / (km2 * f),
            "spots_per_km2": sample["summary"]["spots"] / (km2 * f)}


def machine_factors(bench_file: str, reference_file: str) -> Dict:
    """How a machine compares with the reference from their bench.json files (the M search): its
    single-core stages' wall time (saving, prominence), the CPU seconds of the pair search, and the
    cores the pair search keeps busy."""
    with open(bench_file, encoding="utf-8") as f:
        mine = json.load(f)
    with open(reference_file, encoding="utf-8") as f:
        ref = json.load(f)
    stage = lambda d, label: next(s for s in d["searches"]["M"]["stages"] if s["stage"] == label)  # noqa: E731
    serial = [stage(mine, k)["wall_s"] / stage(ref, k)["wall_s"]
              for k in ("Step 5: Compute saving results", "Step 2: Compute anchor prominence and drop")]
    pairs_mine, pairs_ref = stage(mine, "Step 3: Compute anchor pairs"), stage(ref, "Step 3: Compute anchor pairs")
    return {"serial": float(np.mean(serial)), "cpu": pairs_mine["cpu_s"] / pairs_ref["cpu_s"],
            "parallel_cores": pairs_mine["cpu_s"] / pairs_mine["wall_s"],
            "physical_cores": mine["machine"]["physical_cores"]}


def resolution_ratio(metrics: Dict[str, Dict], band: str, res_from: float, res_to: float, key: str) -> Optional[float]:
    """The median ratio of a per-km² metric between two resolutions over the places measured at
    both (names <place>-<band>-<res>m)."""
    ratios = []
    for name, m in metrics.items():
        place, b, res = name.rsplit("-", 2)[0], name.rsplit("-", 2)[1], name.rsplit("-", 2)[2]
        if b != band or res != f"{res_from:g}m":
            continue
        other = metrics.get(f"{place}-{band}-{res_to:g}m")
        if other and m[key] > 0:
            ratios.append(other[key] / m[key])
    return float(np.median(ratios)) if ratios else None


def place_metrics(metrics: Dict[str, Dict], place: str, band: str, res: float) -> Optional[Dict]:
    """A place's metrics of a band at a resolution: measured, or from the place's nearest measured
    resolution scaled by resolution_ratio (the grid's per-Mpx cost as it is); None if neither."""
    exact = metrics.get(f"{place}-{band}-{res:g}m")
    if exact:
        return exact
    measured = sorted((float(n.rsplit("-", 1)[1][:-1]), m) for n, m in metrics.items()
                      if n.startswith(f"{place}-{band}-") and n.endswith("m") and n.count("-") == place.count("-") + 2)
    for res_from, m in sorted(measured, key=lambda rm: abs(math.log(rm[0] / res))):
        scaled = dict(m)
        for key in ("line_cpu_per_km2", "count_s_per_km2", "lines_per_km2", "spots_per_km2"):
            ratio = resolution_ratio(metrics, band, res_from, res, key)
            if ratio is None:
                break
            scaled[key] = m[key] * ratio
        else:
            scaled["scaled_from"] = f"{res_from:g} m"
            return scaled
    return None


def band_time(inputs: Dict, metrics: Dict[str, Dict], country: Dict, band: str, res: float, scenario: str,
              dsm: bool, factors: Dict, memory_gb: float) -> Optional[Dict]:
    """The wall time of one band of a country at a resolution on a machine: over candidate tile
    cores, the grid (single-core, K tiles at once as memory allows) and the line search (all
    cores), combined; the core with the shortest time wins."""
    low, high = inputs["bands"][band]
    overlap = high + inputs["margin_m"] + 2 * res
    serial_km2 = line_cpu = count = lines = spots = 0.0
    km2 = country["area_km2"]
    for cls in country["classes"].values():
        # A class may name other places for a band ("high_L"): a sample big enough for its lines
        for place, weight in cls.get(f"{scenario}_{band}", cls[scenario]).items():
            m = place_metrics(metrics, place, band, res)
            if m is None:
                return None
            share = cls["share"] * weight
            grid_factor = 1.0 if dsm else inputs.get("dsm_off_grid_factor", 1.0)
            serial_km2 += share * m["grid_s_per_mpx"] * grid_factor / res ** 2  # s per km² of core, no overlap
            line_cpu += share * km2 * m["line_cpu_per_km2"]
            count += share * km2 * m["count_s_per_km2"]
            lines += share * km2 * m["lines_per_km2"]
            spots += share * km2 * m["spots_per_km2"]
    best = None
    lines_km2_max = lines / km2
    for core_km in inputs["cores_km"]:
        core = core_km * 1000.0
        side = core + 2 * overlap
        tile_bytes = (side / res) ** 2 * inputs["pixel_bytes"] + lines_km2_max * core_km ** 2 * LINE_BYTES
        k = min(int(memory_gb * 1e9 // tile_bytes), factors["physical_cores"])
        if k < 1:
            continue
        serial = (serial_km2 * km2 * (side / core) ** 2 + count) * factors["serial"]
        parallel = line_cpu * factors["cpu"] / factors["parallel_cores"]
        a, b = serial / (k * SERIAL_EFFICIENCY), parallel
        wall = max(a, b) + OVERLAP_SHARE * min(a, b)
        if best is None or wall < best["wall_s"]:
            best = {"band": band, "res": res, "core_km": core_km, "tile_gb": round(tile_bytes / 1e9, 2), "tiles_at_once": k,
                    "serial_s": round(serial), "line_wall_s": round(parallel), "wall_s": round(wall),
                    "lines": round(lines), "spots": round(spots)}
    return best


def estimate(inputs: Dict, samples: Dict, base: str) -> Dict:
    """Country totals: for each country, length variant, grid strategy, with and without the DSM,
    machine and scenario (low, high): the data, the download and the computing time."""
    metrics = {}
    for name, sample in samples.items():
        band = name.rsplit("-", 2)[1] if name.count("-") >= 2 else None
        if band in inputs["bands"] and not name.endswith(("-45", "-50", "-nodsm", "-axiom", "-tiger", "-floors")):
            metrics[name] = sample_metrics(sample, inputs["bands"][band][1])
    # The grid without the DSM (one mosaic less): the mean ratio of the <name>-nodsm samples to theirs
    pairs = [(n[:-len("-nodsm")], n) for n in samples if n.endswith("-nodsm") and n[:-len("-nodsm")] in samples]
    if pairs and "dsm_off_grid_factor" not in inputs:
        grid_of = lambda n: sample_metrics(samples[n], 0)["grid_s_per_mpx"]  # noqa: E731
        inputs = {**inputs, "dsm_off_grid_factor": float(np.mean([grid_of(b) / grid_of(a) for a, b in pairs]))}
    factors = {}
    reference = os.path.join(base, inputs["machines"][inputs["reference"]]["bench"])
    for name, machine_ in inputs["machines"].items():
        factors[name] = machine_factors(os.path.join(base, machine_["bench"]), reference)
    rows = []
    for code, country in inputs["countries"].items():
        for variant, bands in inputs["variants"].items():
            for strategy, res_of in inputs["strategies"].items():
                finest = min(res_of[b] for b in bands)
                for dsm in (True, False):
                    # The coarsest data the finest grid of the strategy can use (e.g. 2 m files for 5 m)
                    usable = sorted((k for k in country["data"] if float(k) <= finest), key=float)
                    data = country["data"][usable[-1] if usable else min(country["data"], key=float)]
                    layers = {k: v for k, v in data.items() if dsm or k != "surface"}
                    download_mb = sum(v["download_mb_km2"] for v in layers.values()) * country["area_km2"]
                    cache_mb = sum(v["cache_mb_km2"] for v in layers.values()) * country["area_km2"]
                    files = sum(v["files_per_km2"] for v in layers.values()) * country["area_km2"]
                    service = country["service"]
                    seconds = download_mb / min(service["mb_s"], inputs["link_mb_s"])
                    if service.get("requests_per_min"):
                        seconds = max(seconds, files / service["requests_per_min"] * 60)
                    seconds += service.get("index_s", 0)
                    for machine_name, machine_ in inputs["machines"].items():
                        for scenario in ("low", "high"):
                            parts = [band_time(inputs, metrics, country, b, res_of[b], scenario, dsm,
                                               factors[machine_name], machine_["memory_gb"]) for b in bands]
                            rows.append({
                                "country": code, "variant": variant, "strategy": strategy, "dsm": dsm,
                                "machine": machine_name, "scenario": scenario,
                                "download_tb": round(download_mb / 1e6, 3), "cache_tb": round(cache_mb / 1e6, 3),
                                "download_days": round(seconds / 86400, 2),
                                "compute_days": None if None in parts else round(sum(p["wall_s"] for p in parts) / 86400, 2),
                                "compute_hours": None if None in parts else round(sum(p["wall_s"] for p in parts) / 3600, 2),
                                "lines": None if None in parts else sum(p["lines"] for p in parts),
                                "spots": None if None in parts else sum(p["spots"] for p in parts),
                                "bands": parts})
    return {"metrics": metrics, "factors": factors, "dsm_off_grid_factor": inputs.get("dsm_off_grid_factor"),
            "rows": rows}


def write_json(path: Optional[str], data: Dict):
    if path:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("bench", help="the offline benchmark of a machine")
    b.add_argument("--out", required=True)
    b.add_argument("--processes", type=int, nargs="+", help="searches at once (default: 1, physical cores // 2, "
                   "physical cores)")
    b.add_argument("--grid", type=int, default=8, help="copies of the clip per side (default 8: 4800 x 4800 px)")
    p = sub.add_parser("profile", help="one measured search into <out>/samples.json")
    p.add_argument("--out", required=True)
    p.add_argument("--name", required=True)
    p.add_argument("--cores", type=int, help="perf_profile.py's --cores")
    p.add_argument("--tension-by-length", help="pretension by span, span:kN points, e.g. 300:2.5,1500:6,5000:15")
    p.add_argument("args", nargs=argparse.REMAINDER, help="-- and the options of findaline.py")
    c = sub.add_parser("compare", help="counts per cell against a reference run")
    c.add_argument("--samples", required=True)
    c.add_argument("ref")
    c.add_argument("others", nargs="+")
    c.add_argument("--cells", type=float, nargs="+", default=[500, 1000], help="cell sizes in metres")
    c.add_argument("--bands", nargs="+", help="length bands as low-high in metres (default: 30-60 ... 3000-5000)")
    c.add_argument("--json", help="write the result here too")
    q = sub.add_parser("cube", help="the size of a sparse counter cube")
    q.add_argument("--samples", required=True)
    q.add_argument("names", nargs="+")
    q.add_argument("--cell", type=float, default=1000, help="cell size in metres")
    q.add_argument("--dims", nargs="+", default=list(DIMS), help=f"dimensions of the key ({', '.join(DIMS)})")
    q.add_argument("--json", help="write the result here too")
    e = sub.add_parser("estimate", help="country totals from the samples")
    e.add_argument("--inputs", required=True, help="the countries, bands, strategies and machines (JSON)")
    e.add_argument("--samples", required=True)
    e.add_argument("--json", help="write the result here too")
    args = parser.parse_args()

    if args.command == "bench":
        bench(args.out, args.processes, args.grid)
    elif args.command == "profile":
        search_args = args.args[1:] if args.args[:1] == ["--"] else args.args
        profile(args.out, args.name, search_args, args.cores, args.tension_by_length)
    elif args.command == "compare":
        result = compare(load_samples(args.samples), args.ref, args.others, args.cells, parse_bands(args.bands))
        write_json(args.json, result)
        print(markdown(result["rows"], ["cell", "band", "other", "ref_lines", "other_lines", "lines_ratio",
                                        "ref_spots", "other_spots", "spots_ratio", "cells", "spearman", "lost",
                                        "new"]))
    elif args.command == "estimate":
        with open(args.inputs, encoding="utf-8") as f:
            inputs = json.load(f)
        result = estimate(inputs, load_samples(args.samples), os.path.dirname(os.path.abspath(args.inputs)))
        write_json(args.json, result)
        rows = [{**r, "lines": r["lines"], "bands": " ".join(f"{p['band']}:{p['core_km']}km×{p['tiles_at_once']}"
                                                             for p in r["bands"] if p)} for r in result["rows"]]
        print(markdown(rows, ["country", "variant", "strategy", "dsm", "machine", "scenario", "download_tb",
                              "cache_tb", "download_days", "compute_days", "lines", "spots", "bands"]))
    else:
        result = cube(load_samples(args.samples), args.names, args.cell, args.dims)
        write_json(args.json, result)
        print(markdown(result["rows"], ["name", "cell", "dims", "area_km2", "lines", "line_keys", "line_keys_km2",
                                        "line_bytes_km2", "spots", "spot_keys", "spot_keys_km2", "spot_bytes_km2"]))


if __name__ == "__main__":
    main()
