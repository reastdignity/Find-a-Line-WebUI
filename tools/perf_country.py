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

relief reads Copernicus DEM GLO-30 (downloaded into the data folder's cache where missing) over
each country of an inputs file (its OpenStreetMap outline) and over every sample: per block of
about 1 km the relief and the share of steep pixels, over windows of 1, 3 and 5 blocks. It keeps
the countries' km² per fine bin of each proxy and each sample's 1 km cells (area, edge fraction,
lines, spots, proxies), and prints the Spearman correlation of each proxy with the lines per km².

    uv run tools/perf_country.py relief --inputs docs/country-precompute/inputs.json \\
        --samples <scratch>/samples/samples.json --data-dir <scratch>/data --out docs/country-precompute/relief.json

estimate turns the samples into country totals: for each country of an inputs file (its area, its
data per km² and its download service), length variant (bands S, M, L), grid strategy, with and
without the DSM, machine (its bench.json against the reference's) and scenario: the data, the
download days and the computing days of a run that keeps only counts. A band's lines and spots
come from relief's strata (the country's km² per stratum of the band's proxy times the samples'
lines per km² there; low, mid and high from a bootstrap over the places), its times from the
places measured at that resolution. A sample is named <place>-<band>-<res>m; a band's counts at
another resolution than its base are scaled by the median ratio of the places measured at both.

    uv run tools/perf_country.py estimate --inputs docs/country-precompute/inputs.json \\
        --samples <scratch>/samples/samples.json [--json PATH]

The options after "--" are findaline.py's; --no-plot, --yes and --ortho never are added. Give
--data-dir there to keep the runs out of the repository's runs/.
"""

import argparse
import csv
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
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=HERE, capture_output=True, text=True, encoding="utf-8",
                             timeout=30)
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
    """"300:2.5,1500:6" -> [(300, 2.5), (1500, 6)], sorted by the span (sag.parse_tension)."""
    import sag as sg
    return sg.parse_tension(text)


def tension_at(points: Sequence[Tuple[float, float]], span: float) -> float:
    """The pretension (kN) at a span: linear between the points, clamped at both ends (sag.tension_at)."""
    import sag as sg
    return sg.tension_at(points, span)


def tension_table(points: Sequence[Tuple[float, float]]):
    """A class with the constructor of sag.EnvelopeTable (rig, min_span, max_span) making a
    sag.TensionTable of these points: the envelope of each span solved with the pretension T(span).
    linesearch reads only the table's arrays and rig.fall_zone besides __call__, and the final
    decision calls the table itself, so the search uses T(span) throughout."""
    import sag as sg

    class Table(sg.TensionTable):
        def __init__(self, rig, min_span: float, max_span: float):
            super().__init__(rig, min_span, max_span, points)

    return Table


def lean_save_results(run_path: str, lines, groups, meta: Dict, on_lines=lambda n, file: None):
    """runs.save_results for the measurements: run.json and lines.npz with the columns compare and
    cube read, in the order of lines.csv (group by group, the representative first), as float32;
    no lines.csv or lines.geojson (in steep terrain tens of millions of lines are tens of GB)."""
    import runs as rn
    order, number, is_rep, _ = rn.row_order(groups, 0, len(groups.members), rn.rep_positions(groups))
    c = lines.columns
    pick = lambda name, k=None: (c[name][order] if k is None else c[name][order, k]).astype(np.float32)  # noqa: E731
    np.savez(os.path.join(run_path, "lines.npz"), group=number.astype(np.int64), representative=is_rep,
             length_m=pick("length"), clearance_m=pick("clearance"), water_m=pick("water_m"),
             height_max_m=pick("height_max"), anchor1_northing=pick("a1_xy", 1), anchor1_easting=pick("a1_xy", 0),
             anchor1_wall_angle=pick("angle1"), anchor2_wall_angle=pick("angle2"),
             anchor1_prominence_m=pick("prom1"), anchor2_prominence_m=pick("prom2"),
             over_trees_buildings=c["over_obstacles"][order].astype(bool))
    with open(os.path.join(run_path, "run.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    on_lines(0, "run.json")


class Hooks:
    """The T(L) table assigned as sag.EnvelopeTable (search.py looks it up at call time),
    search.plan_search wrapped to keep the Plan, and with lean runs.save_results replaced by
    lean_save_results; uninstall puts them back."""

    def __init__(self, tension: Optional[str], lean: bool = False):
        import runs as rn
        import sag as sg
        import search
        self.sg, self.search, self.rn = sg, search, rn
        self.tension = parse_tension(tension) if tension else None
        self.lean = lean
        self.table, self.plan_search, self.save_results = sg.EnvelopeTable, search.plan_search, rn.save_results
        self.plan = None

    def _plan_search(self, *args, **kwargs):
        self.plan = self.plan_search(*args, **kwargs)
        return self.plan

    def install(self):
        if self.tension:
            self.sg.EnvelopeTable = tension_table(self.tension)
        self.search.plan_search = self._plan_search
        if self.lean:
            self.rn.save_results = lean_save_results

    def uninstall(self):
        self.sg.EnvelopeTable, self.search.plan_search = self.table, self.plan_search
        self.rn.save_results = self.save_results


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
            tension: Optional[str] = None, lean: bool = False) -> Dict:
    """One measured search, recorded into <out>/samples.json under name; with lean its run keeps
    lines.npz instead of lines.csv and lines.geojson (lean_save_results)."""
    os.makedirs(out, exist_ok=True)
    hooks = Hooks(tension, lean)
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
    packed = os.path.join(run, "lines.npz")
    if not os.path.exists(packed) and os.path.getsize(os.path.join(run, "lines.csv")) > 200e6:
        # A big lines.csv of before: its columns packed once with pandas (the csv module would take
        # minutes and gigabytes of Python floats), the same values lean_save_results writes
        import pandas as pd
        table = pd.read_csv(os.path.join(run, "lines.csv"), usecols=list(numbers + flags), encoding="utf-8-sig")
        np.savez(packed, **{k: (table[k].to_numpy(np.int64) if k == "group" else table[k].to_numpy(bool)
                                if k in flags else table[k].to_numpy(np.float32)) for k in numbers + flags})
    if os.path.exists(packed):
        with np.load(packed) as data:
            columns = {k: data[k].astype(float) for k in numbers}
            columns.update({k: data[k].astype(bool) for k in flags})
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


# ---------------------------------------------------------------- relief

# The relief of a country and of the samples' cells, from Copernicus DEM GLO-30 (the catalogue's
# surface layer of "europe", cached like a search's tiles): per block of about BLOCK_M its highest
# and lowest point and its share of steep pixels (slope at 30 m of STEEP_DEG or more); per window of
# 1, 3 or 5 blocks (about the reach of the bands' lines) the relief (highest minus lowest) and the
# steep share. estimate stratifies a country by the steep share of a window and, where hardly a pixel
# is steep, by its relief (strata_of), and takes each stratum's lines and spots per km² from the
# samples' cells in it.
BLOCK_M = 1000
STEEP_DEG = (30, 45)
WINDOWS = (1, 3, 5)
PROXIES = tuple(f"relief{w}" for w in WINDOWS) + tuple(f"steep{d}_{w}" for d in STEEP_DEG for w in WINDOWS)
# The fine bins a country's area is kept in (strata edges must be among them): relief in metres,
# steep shares (an own bin for none at all)
HIST_EDGES = {
    "relief": [25.0 * k for k in range(41)] + [1000.0 + 100 * k for k in range(1, 11)] + [INF],
    "steep": [0.0, 1e-6] + [0.0005 * k for k in range(1, 41)] + [0.02 + 0.005 * k for k in range(1, 17)]
             + [0.1 + 0.02 * k for k in range(1, 46)] + [INF]}
JOINT = "steep45"  # the joint histograms of steep45_<w> and relief<w>
EARTH_M_PER_DEG = 6371000 * math.pi / 180
CELL_M = 1000  # the samples' cells
EDGE_POINTS, EDGE_PARTNERS = 160, 8  # Monte Carlo of a cell's edge fraction


def relief_layer():
    import sources
    return sources.SOURCES["europe"].nmpt


def degree_tiles(geometry) -> List[Tuple[int, int]]:
    """The 1° tiles (lat, lon of the south-west corner) a WGS84 geometry touches."""
    from shapely.geometry import box
    west, south, east, north = geometry.bounds
    return [(lat, lon) for lat in range(math.floor(south), math.floor(north) + 1)
            for lon in range(math.floor(west), math.floor(east) + 1)
            if geometry.intersects(box(lon, lat, lon + 1, lat + 1))]


def fetch_relief_tiles(tiles: List[Tuple[int, int]], cache_dir: str) -> Dict[Tuple[int, int], Optional[str]]:
    """The cached GLO-30 file of each tile, downloaded where missing (None: no data there, sea)."""
    from concurrent.futures import ThreadPoolExecutor
    layer = relief_layer()
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda tile: layer._download_and_record(tile, cache_dir, None, True), tiles))
    paths = {tile: layer.tile_path(cache_dir, tile) for tile in tiles}
    return {tile: path if os.path.exists(path) else None for tile, path in paths.items()}


def _block_edges(n: int, metres: float) -> np.ndarray:
    count = max(1, round(n * metres / BLOCK_M))
    return np.linspace(0, n, count + 1).round().astype(np.int64)


def tile_blocks(path: str) -> Dict[str, np.ndarray]:
    """A GLO-30 tile in blocks of about BLOCK_M: their edges in degrees (lat from the north, lon from
    the west), centres, km² and the proxies (2-D arrays, block rows from the north)."""
    import rasterio
    from scipy.ndimage import maximum_filter, minimum_filter, uniform_filter
    with rasterio.open(path) as src:
        z = src.read(1).astype(np.float64)
        if src.nodata is not None:
            z[z == src.nodata] = np.nan
        west, south, east, north = src.bounds
    h, w = z.shape
    lat = north - (np.arange(h) + 0.5) * (north - south) / h
    dy = (north - south) / h * EARTH_M_PER_DEG
    dx = (east - west) / w * EARTH_M_PER_DEG * np.cos(np.radians(lat))
    gy, gx = np.gradient(z, axis=0) / dy, np.gradient(z, axis=1) / dx[:, None]
    slope = np.degrees(np.arctan(np.hypot(gx, gy)))
    rows, cols = _block_edges(h, dy), _block_edges(w, float(np.mean(dx)))
    valid = ~np.isnan(z)

    def reduce(a, ufunc):
        return ufunc.reduceat(ufunc.reduceat(a, rows[:-1], axis=0), cols[:-1], axis=1)

    zmax, zmin = reduce(np.where(valid, z, -np.inf), np.maximum), reduce(np.where(valid, z, np.inf), np.minimum)
    n = reduce(valid.astype(np.float64), np.add)
    lat_edges = north - rows * (north - south) / h
    lon_edges = west + cols * (east - west) / w
    lat_c = (lat_edges[:-1] + lat_edges[1:]) / 2
    lon_c = (lon_edges[:-1] + lon_edges[1:]) / 2
    km2 = (np.diff(rows) * dy)[:, None] * (np.diff(cols)[None, :] * (east - west) / w * EARTH_M_PER_DEG
                                          * np.cos(np.radians(lat_c))[:, None]) / 1e6
    out = {"lat_edges": lat_edges, "lon_edges": lon_edges, "lat": np.repeat(lat_c[:, None], len(lon_c), axis=1),
           "lon": np.repeat(lon_c[None, :], len(lat_c), axis=0), "km2": km2, "valid": n > 0}
    for window in WINDOWS:
        high = maximum_filter(zmax, size=window, mode="nearest")
        low = minimum_filter(zmin, size=window, mode="nearest")
        out[f"relief{window}"] = np.where(np.isfinite(high) & np.isfinite(low), high - low, np.nan)
        pixels = uniform_filter(n, size=window, mode="nearest")
        for degrees in STEEP_DEG:
            steep = uniform_filter(reduce((slope >= degrees).astype(np.float64), np.add), size=window, mode="nearest")
            out[f"steep{degrees}_{window}"] = np.where(pixels > 0, steep / np.maximum(pixels, 1e-9), np.nan)
    return out


def proxies_at(blocks: Dict[Tuple[int, int], Dict], lon: np.ndarray, lat: np.ndarray) -> Dict[str, np.ndarray]:
    """The proxies of the blocks holding the points (NaN where no tile)."""
    out = {p: np.full(len(lon), np.nan) for p in PROXIES}
    tiles = np.column_stack([np.floor(lat), np.floor(lon)]).astype(np.int64)
    for key in {tuple(t) for t in tiles.tolist()}:
        b = blocks.get(key)
        if b is None:
            continue
        at = np.flatnonzero((tiles[:, 0] == key[0]) & (tiles[:, 1] == key[1]))
        row = np.clip(np.searchsorted(-b["lat_edges"], -lat[at], side="right") - 1, 0, len(b["lat_edges"]) - 2)
        col = np.clip(np.searchsorted(b["lon_edges"], lon[at], side="right") - 1, 0, len(b["lon_edges"]) - 2)
        for p in PROXIES:
            out[p][at] = b[p][row, col]
    return out


def _edges_json(edges: Sequence[float]) -> List:
    return [e if e != INF else "inf" for e in edges]


def histogram(values: np.ndarray, km2: np.ndarray, proxy: str) -> Dict:
    edges = HIST_EDGES["relief" if proxy.startswith("relief") else "steep"]
    keep = ~np.isnan(values)
    k = bins(values[keep], edges)
    return {"edges": _edges_json(edges),
            "km2": np.bincount(k, weights=km2[keep], minlength=len(edges) - 1).round(3).tolist()}


def joint_histogram(steep: np.ndarray, relief_: np.ndarray, km2: np.ndarray) -> Dict:
    """km² per (fine steep bin, fine relief bin), the non-empty bins only, as [i, j, km²]."""
    keep = ~np.isnan(steep) & ~np.isnan(relief_)
    i, j = bins(steep[keep], HIST_EDGES["steep"]), bins(relief_[keep], HIST_EDGES["relief"])
    nj = len(HIST_EDGES["relief"]) - 1
    total = np.bincount(i * nj + j, weights=km2[keep])
    found = np.flatnonzero(total > 0)
    return {"steep_edges": _edges_json(HIST_EDGES["steep"]), "relief_edges": _edges_json(HIST_EDGES["relief"]),
            "bins": [[int(k // nj), int(k % nj), round(float(total[k]), 3)] for k in found]}


def sample_area(sample: Dict):
    """A sample's search area in its grid's CRS: the circle of --lat/--lon/--radius, or --area."""
    from shapely.geometry import Point, shape
    from shapely.ops import unary_union
    import area as ar
    crs, args = sample["grid"]["crs"], sample["args"]
    path = option(args, "--area")
    if path:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        features = data["features"] if data.get("type") == "FeatureCollection" else [data]
        return ar.project(unary_union([shape(f.get("geometry", f)) for f in features]), "EPSG:4326", crs)
    centre = ar.project(Point(float(option(args, "--lon")), float(option(args, "--lat"))), "EPSG:4326", crs)
    return centre.buffer(float(option(args, "--radius")), 256)


def cell_edge_fraction(area, cell, low: float, high: float, rng) -> float:
    """The share of a cell's partners at low..high metres (uniform over that ring) that lie inside
    the area, for points of the cell inside it (Monte Carlo)."""
    from shapely import contains_xy
    left, bottom, right, top = cell.bounds
    points = np.empty((0, 2))
    while len(points) < EDGE_POINTS:
        xy = rng.uniform((left, bottom), (right, top), size=(4 * EDGE_POINTS, 2))
        points = np.vstack([points, xy[contains_xy(cell, xy[:, 0], xy[:, 1])]])
    points = points[:EDGE_POINTS]
    r = np.sqrt(rng.uniform(low ** 2, high ** 2, size=(EDGE_POINTS, EDGE_PARTNERS)))
    a = rng.uniform(0, 2 * np.pi, size=(EDGE_POINTS, EDGE_PARTNERS))
    x, y = points[:, :1] + r * np.cos(a), points[:, 1:] + r * np.sin(a)
    return float(contains_xy(area, x.ravel(), y.ravel()).mean())


def sample_cells(sample: Dict, low: float, high: float, blocks: Dict, lines: Optional[Dict] = None,
                 scale: Tuple[float, float] = (1.0, 1.0)) -> Dict:
    """A sample's cells of CELL_M: area inside its search area (km²), edge fraction for lines of
    low..high metres, lines and spots (their first anchor's cell; times scale when they come from
    another resolution's run) and the proxies at the cell's centre."""
    from pyproj import Transformer
    from shapely.geometry import box
    shape_ = sample_area(sample)
    crs = sample["grid"]["crs"]
    ls = read_lines(sample["run"]) if lines is None else lines
    counts = {}
    for name, keep in (("lines", np.ones(len(ls["length_m"]), bool)), ("spots", ls["representative"])):
        cells, n = np.unique(cells_of(ls, CELL_M)[keep], axis=0, return_counts=True)
        counts[name] = {tuple(c): int(k) for c, k in zip(cells.tolist(), n.tolist())}
    rng = np.random.default_rng(0)
    left, bottom, right, top = shape_.bounds
    rows = []
    for i in range(math.floor(left / CELL_M), math.floor(right / CELL_M) + 1):
        for j in range(math.floor(bottom / CELL_M), math.floor(top / CELL_M) + 1):
            cell = shape_.intersection(box(i * CELL_M, j * CELL_M, (i + 1) * CELL_M, (j + 1) * CELL_M))
            if cell.area < 0.05 * CELL_M ** 2:
                continue
            c = cell.representative_point()
            rows.append({"cell": (i, j), "km2": cell.area / 1e6, "edge": cell_edge_fraction(shape_, cell, low, high, rng),
                         "lines": counts["lines"].get((i, j), 0) * scale[0],
                         "spots": counts["spots"].get((i, j), 0) * scale[1], "x": c.x, "y": c.y})
    if not rows:
        return {"columns": [], "cells": []}
    to_wgs84 = Transformer.from_crs(crs, "EPSG:4326", always_xy=True).transform
    lon, lat = to_wgs84(np.array([r["x"] for r in rows]), np.array([r["y"] for r in rows]))
    proxies = proxies_at(blocks, np.asarray(lon), np.asarray(lat))
    columns = ["km2", "edge", "lines", "spots", *PROXIES]
    table = [[round(r["km2"], 4), round(r["edge"], 4), round(r["lines"], 2), round(r["spots"], 2),
              *(None if np.isnan(proxies[p][k]) else round(float(proxies[p][k]), 4) for p in PROXIES)]
             for k, r in enumerate(rows)]
    return {"columns": columns, "cells": table}


def relief(inputs: Dict, samples: Dict, data_dir: str) -> Dict:
    """The countries' area per fine bin of each proxy (blocks whose centre lies inside their OSM
    outline) and the cells of every sample <place>-<band>-<res>m (variants left out); a sample
    without a run but with lines (rebuilt from its output) takes the cells of the same place and
    band at another resolution, scaled to its totals."""
    from shapely import contains_xy, prepare
    from shapely.ops import unary_union
    import area as ar
    cache_dir = os.path.join(data_dir, "cache")
    blocks: Dict[Tuple[int, int], Dict] = {}

    def load(tiles):
        missing = [t for t in tiles if t not in blocks]
        for tile, path in fetch_relief_tiles(missing, cache_dir).items():
            blocks[tile] = tile_blocks(path) if path else None

    result = {"block_m": BLOCK_M, "proxies": list(PROXIES), "countries": {}, "samples": {}}
    for code, country in inputs["countries"].items():
        outline = unary_union([ar.region(f"osm:{name}", cache_dir) for name in country["osm"]])
        prepare(outline)
        tiles = degree_tiles(outline)
        load(tiles)
        values = {p: [] for p in PROXIES}
        km2 = []
        for tile in tiles:
            b = blocks[tile]
            if b is None:
                continue
            inside = b["valid"] & contains_xy(outline, b["lon"], b["lat"])
            km2.append(b["km2"][inside])
            for p in PROXIES:
                values[p].append(b[p][inside])
        km2 = np.concatenate(km2)
        values = {p: np.concatenate(v) for p, v in values.items()}
        result["countries"][code] = {
            "osm": country["osm"], "outline_km2": round(ar.size_km2(outline)), "blocks_km2": round(float(km2.sum())),
            "tiles": len(tiles), "tiles_without_data": sum(blocks[t] is None for t in tiles),
            "hist": {p: histogram(values[p], km2, p) for p in PROXIES},
            "joint": {str(w): joint_histogram(values[f"{JOINT}_{w}"], values[f"relief{w}"], km2) for w in WINDOWS}}
        print(f"{code}: {len(tiles)} tiles, outline {result['countries'][code]['outline_km2']} km², "
              f"blocks {result['countries'][code]['blocks_km2']} km²")
    for name, sample in sorted(samples.items()):
        if name.count("-") < 2 or name.endswith(VARIANTS):
            continue
        place, band, res = name.rsplit("-", 2)
        if band not in inputs["bands"]:
            continue
        low, high = inputs["bands"][band]
        load(degree_tiles(ar.project(sample_area(sample), sample["grid"]["crs"], "EPSG:4326")))
        lines, scale, source = None, (1.0, 1.0), None
        if sample["run"] is None and sample["summary"]["lines"] > 0:
            siblings = sorted(n for n, s in samples.items() if n.startswith(f"{place}-{band}-") and s["run"]
                              and n.count("-") == name.count("-") and s["summary"]["lines"] > 0)
            if not siblings:
                print(f"{name}: no run and no other resolution of {place}-{band}: left out")
                continue
            source = siblings[0]
            other = samples[source]["summary"]
            scale = (sample["summary"]["lines"] / other["lines"], sample["summary"]["spots"] / max(other["spots"], 1))
            lines = read_lines(samples[source]["run"])
        cells = sample_cells(sample, low, high, blocks, lines, scale)
        result["samples"][name] = {"place": place, "band": band, "res": float(res[:-1]), "cells_from": source, **cells}
        print(f"{name}: {len(cells['cells'])} cells" + (f" (from {source})" if source else ""))
    for name, s in virtual_cells(result["samples"], samples, inputs).items():
        result["samples"][name] = s
        print(f"{name}: {len(s['cells'])} cells, from {s['cells_from']}")
    return result


def virtual_cells(found: Dict[str, Dict], samples: Dict, inputs: Dict) -> Dict[str, Dict]:
    """For a place measured in a band only at another resolution than the band's base one (Zion's
    M band, whose 2 m search ran out of memory): its cells at the base resolution, the lines and
    spots times the median ratio of the totals of the places measured at both resolutions."""
    added = {}
    for band, spec in inputs.get("strata", {}).items():
        base = float(spec["res"])
        mine = {n: s for n, s in found.items() if s["band"] == band}
        at_base = {s["place"] for s in mine.values() if s["res"] == base}
        for name, s in sorted(mine.items(), key=lambda kv: abs(math.log(kv[1]["res"] / base))):
            if s["place"] in at_base or not s["cells"]:
                continue
            ratios = {"lines": [], "spots": []}
            for other in mine.values():
                if other["res"] != s["res"] or other["place"] == s["place"]:
                    continue
                pair = samples.get(f"{other['place']}-{band}-{base:g}m"), samples.get(f"{other['place']}-{band}-{s['res']:g}m")
                if pair[0] and pair[1]:
                    for key in ratios:
                        if pair[1]["summary"][key]:
                            ratios[key].append(pair[0]["summary"][key] / pair[1]["summary"][key])
            if not ratios["lines"] or not ratios["spots"]:
                continue
            scale = {key: float(np.median(v)) for key, v in ratios.items()}
            c = s["columns"]
            cells = [[round(v * scale["lines"], 2) if k == c.index("lines") else round(v * scale["spots"], 2)
                      if k == c.index("spots") else v for k, v in enumerate(row)] for row in s["cells"]]
            added[f"{s['place']}-{band}-{base:g}m"] = {
                **s, "res": base, "cells": cells,
                "cells_from": f"{name} × {scale['lines']:.3g} lines, × {scale['spots']:.3g} spots (median of "
                              f"{len(ratios['lines'])} places measured at both)"}
            at_base.add(s["place"])
    return added


def proxy_correlations(relief_data: Dict, inputs: Dict) -> List[Dict]:
    """Per band and resolution, the Spearman correlation over the samples' cells (edge fraction of
    at least min_edge) between each proxy and the lines (spots) per effective km²."""
    from scipy.stats import spearmanr
    rows = []
    groups: Dict[Tuple[str, float], List[List]] = {}
    for s in relief_data["samples"].values():
        if s["cells"]:
            groups.setdefault((s["band"], s["res"]), []).extend(s["cells"])
    columns = ["km2", "edge", "lines", "spots", *relief_data["proxies"]]
    for (band, res), cells in sorted(groups.items()):
        t = np.array([[np.nan if v is None else v for v in c] for c in cells], dtype=float)
        keep = t[:, 1] >= inputs.get("min_edge", {}).get(band, 0.5)
        t = t[keep]
        eff = t[:, 0] * t[:, 1]
        row = {"band": band, "res": res, "cells": len(t)}
        for p in relief_data["proxies"]:
            v = t[:, columns.index(p)]
            ok = ~np.isnan(v)
            for what in ("lines", "spots"):
                d = t[ok, columns.index(what)] / eff[ok]
                row[f"{p}:{what}"] = round(float(spearmanr(v[ok], d).statistic), 3) if ok.sum() > 2 and d.std() > 0 else None
        rows.append(row)
    return rows


# ---------------------------------------------------------------- estimate

# What a country run that keeps only counts takes of a sample's stages (perf_profile's labels):
# the grid (steps 1-2 without the downloads, which belong to the download estimate), the line
# search (step 3) and the counts (step 4's groups and metres over water). The coordinates,
# profiles and files of steps 4-5 are not needed, nor the start (imports, plan, index answers)
GRID = re.compile(r"^Step [12]: (Compute|\(between bars\))")
LINE = re.compile(r"^Step 3: ")
COUNT = re.compile(r"^Step 4: Compute over water")
GROUPS = re.compile(r"^Step 4: Compute grouping lines")  # today's spots: apart, it may not scale
DOWNLOAD = re.compile(r"Download")
STEP1_BETWEEN = "Step 1: (between bars)"  # also holds the index answers when the sample downloaded
LINE_BYTES = 450  # search.LINE_BYTES at 221dd10: the lines of a tile while it is counted
SERIAL_EFFICIENCY = 0.85  # processes at once on as many cores: the share of a core each keeps
OVERLAP_SHARE = 0.25  # the part of the shorter of serial and parallel time that the longer does not hide
VARIANTS = ("-45", "-50", "-nodsm", "-axiom", "-tiger", "-floors")  # samples of other parameters
SCENARIOS = ("low", "mid", "high")


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
    groups = sum(wall(s) for s in stages if GROUPS.match(s["stage"]))
    mpx = sample["grid"]["width"] * sample["grid"]["height"] / 1e6
    km2 = sample["grid"]["area_km2"]
    f = edge_fraction(sample_geometry(sample["args"]), reach)
    return {"mpx": mpx, "km2": km2, "edge_fraction": round(f, 4), "grid_s_per_mpx": grid / mpx,
            "line_cpu_per_km2": line_cpu / (km2 * f), "line_cores": line_cpu / line_wall if line_wall else None,
            "count_s_per_km2": count / (km2 * f), "group_s_per_km2": groups / (km2 * f),
            "lines_per_km2": sample["summary"]["lines"] / (km2 * f),
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


def band_of(name: str) -> Optional[Tuple[str, str, float]]:
    """(place, band, resolution) of a sample <place>-<band>-<res>m, None for any other name."""
    parts = name.rsplit("-", 2)
    if len(parts) < 3 or not parts[2].endswith("m"):
        return None
    try:
        return parts[0], parts[1], float(parts[2][:-1])
    except ValueError:
        return None


def _edges(values: Sequence) -> List[float]:
    return [INF if e == "inf" else float(e) for e in values]


def strata_of(steep: np.ndarray, relief_: np.ndarray, spec: Dict) -> np.ndarray:
    """The stratum of each (steep share, relief) of a band's spec: where the steep share is below
    the first of steep_edges, a bin of relief_edges (strata 0 .. len(relief_edges)); above, a bin of
    steep_edges (the strata after them, the last one open)."""
    steep_edges, relief_edges = _edges(spec["steep_edges"]), _edges(spec["relief_edges"])
    steep, relief_ = np.asarray(steep, dtype=float), np.asarray(relief_, dtype=float)
    return np.where(steep < steep_edges[0], np.searchsorted(relief_edges, relief_, side="right"),
                    len(relief_edges) + np.searchsorted(steep_edges, steep, side="right")).astype(np.int64)


def strata_labels(spec: Dict) -> List[str]:
    steep_edges, relief_edges = _edges(spec["steep_edges"]), _edges(spec["relief_edges"])
    flat = f"steep < {steep_edges[0] * 100:g} %"
    relief_bins = [0.0, *relief_edges, INF]
    labels = [f"{flat}, relief {lo:g}-{hi:g} m" if hi != INF else f"{flat}, relief >= {lo:g} m"
              for lo, hi in zip(relief_bins[:-1], relief_bins[1:])]
    steep_bins = [*steep_edges, INF]
    return labels + [f"steep {lo * 100:g}-{hi * 100:g} %" if hi != INF else f"steep >= {lo * 100:g} %"
                     for lo, hi in zip(steep_bins[:-1], steep_bins[1:])]


def strata_areas(country_relief: Dict, spec: Dict) -> np.ndarray:
    """A country's km² per stratum of a band's spec, from its joint histogram of the window: a fine
    bin goes to the stratum of its lower edges (the strata edges are among the fine ones)."""
    joint = country_relief["joint"][str(spec["window"])]
    steep_edges, relief_edges = np.array(_edges(joint["steep_edges"])), np.array(_edges(joint["relief_edges"]))
    cells = np.array(joint["bins"], dtype=float).reshape(-1, 3)
    i, j = cells[:, 0].astype(np.int64), cells[:, 1].astype(np.int64)
    k = strata_of(steep_edges[i] + 1e-9, relief_edges[j] + 1e-6, spec)
    n = len(spec["relief_edges"]) + 1 + len(spec["steep_edges"])
    return np.bincount(k, weights=cells[:, 2], minlength=n)


def place_cells(relief_data: Dict, band: str, spec: Dict, min_edge: float) -> Dict[str, np.ndarray]:
    """Per place, its cells of the band at the spec's resolution with an edge fraction of at least
    min_edge, as rows of (stratum, effective km² = km² inside × edge fraction, lines, spots)."""
    steep, relief_ = f"{JOINT}_{spec['window']}", f"relief{spec['window']}"
    out = {}
    for s in relief_data["samples"].values():
        if s["band"] != band or s["res"] != float(spec["res"]) or not s["cells"]:
            continue
        c = s["columns"]
        t = np.array([[np.nan if v is None else v for v in row] for row in s["cells"]], dtype=float)
        t = t[(t[:, c.index("edge")] >= min_edge) & ~np.isnan(t[:, c.index(steep)]) & ~np.isnan(t[:, c.index(relief_)])]
        if len(t):
            out[s["place"]] = np.column_stack([strata_of(t[:, c.index(steep)], t[:, c.index(relief_)], spec),
                                               t[:, c.index("km2")] * t[:, c.index("edge")],
                                               t[:, c.index("lines")], t[:, c.index("spots")]])
    return out


def _per_stratum(tables: List[np.ndarray], n: int) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    t = np.vstack(tables)
    k = t[:, 0].astype(np.int64)
    return (np.bincount(k, t[:, 1], n), np.bincount(k, t[:, 2], n), np.bincount(k, t[:, 3], n))


def _filled(density: np.ndarray) -> np.ndarray:
    """A stratum without cells takes the density of the nearest stratum with cells (the lower one
    when both are as near)."""
    known = np.flatnonzero(~np.isnan(density))
    if not len(known):
        return np.zeros_like(density)
    out = density.copy()
    for k in np.flatnonzero(np.isnan(density)):
        out[k] = density[known[np.argmin(np.abs(known - k) + 0.1 * (known > k))]]
    return out


def band_counts(relief_data: Dict, inputs: Dict, code: str, band: str) -> Optional[Dict]:
    """A country's lines and spots of a band at the band's base resolution: per stratum of the
    band's proxy the country's km² times the lines (spots) per effective km² of the samples' cells
    in it; low, mid and high: the 10th, 50th and 90th percentile of the line total over a bootstrap
    of the places (with their spots), mid the plain estimate."""
    spec = inputs["strata"][band]
    res = float(spec["res"])
    by_place = place_cells(relief_data, band, spec, inputs.get("min_edge", {}).get(band, 0.5))
    if not by_place:
        return None
    labels = strata_labels(spec)
    places, n = sorted(by_place), len(labels)
    areas = strata_areas(relief_data["countries"][code], spec)
    # The outline holds water (the Baltic's territorial sea, the Great Salt Lake), which is flat: the
    # blocks' excess over the country's area comes off the flattest stratum; a shortfall (blocks at the
    # border left out) is spread over all
    land = inputs["countries"][code]["area_km2"]
    if areas.sum() > land:
        areas[0] = max(0.0, areas[0] - (areas.sum() - land))
    else:
        areas *= land / areas.sum()

    def densities(tables):
        km2, lines, spots = _per_stratum(tables, n)
        with np.errstate(invalid="ignore", divide="ignore"):
            return np.where(km2 > 0, lines / km2, np.nan), np.where(km2 > 0, spots / km2, np.nan), km2

    lines_d, spots_d, cells_km2 = densities([by_place[p] for p in places])
    lines_f, spots_f = _filled(lines_d), _filled(spots_d)
    rng = np.random.default_rng(0)
    totals = []
    for _ in range(inputs.get("bootstrap", 400)):
        pick = rng.choice(len(places), len(places))
        dl, ds, _km2 = densities([by_place[places[i]] for i in pick])
        totals.append((float(areas @ np.where(np.isnan(dl), lines_f, dl)), float(areas @ np.where(np.isnan(ds), spots_f, ds))))
    totals.sort()
    at = lambda q: totals[min(len(totals) - 1, int(q * len(totals)))]  # noqa: E731
    return {"band": band, "res": res, "window": spec["window"], "strata": labels, "places": places,
            "km2": areas.round(1).tolist(), "cells_km2": cells_km2.round(2).tolist(),
            "lines_per_km2": [None if np.isnan(v) else round(float(v), 2) for v in lines_d],
            "spots_per_km2": [None if np.isnan(v) else round(float(v), 3) for v in spots_d],
            "lines": {"low": at(0.1)[0], "mid": float(areas @ lines_f), "high": at(0.9)[0]},
            "spots": {"low": at(0.1)[1], "mid": float(areas @ spots_f), "high": at(0.9)[1]}}


def time_model(metrics: Dict[str, Dict], band: str, res: float) -> Optional[Dict]:
    """How the stages of a band at a resolution grow, from the places measured there: the grid's
    seconds per Mpx (median), the line search's CPU seconds per km² as a + b × lines per km² (least
    squares over the places, a and b at least 0) and the counts' and groups' seconds per line."""
    ms = [m for name, m in metrics.items() if (band_of(name) or (None, None, None))[1:] == (band, res)]
    if not ms:
        return None
    lam = np.array([m["lines_per_km2"] for m in ms])
    cpu = np.array([m["line_cpu_per_km2"] for m in ms])
    if len(ms) >= 2 and lam.std() > 0:
        b, a = (float(v) for v in np.polyfit(lam, cpu, 1))
        if a < 0:
            a, b = 0.0, float(cpu.sum() / lam.sum())
        if b < 0:
            a, b = float(cpu.mean()), 0.0
    elif lam.sum() > 0:
        a, b = 0.0, float(cpu.sum() / lam.sum())
    else:
        a, b = float(cpu.mean()), 0.0
    per_line = lambda key: float(sum(m[key] for m in ms) / lam.sum()) if lam.sum() > 0 else 0.0  # noqa: E731
    return {"places": len(ms), "grid_s_per_mpx": float(np.median([m["grid_s_per_mpx"] for m in ms])),
            "cpu_a": a, "cpu_b": b, "count_s_per_line": per_line("count_s_per_km2"),
            "group_s_per_line": per_line("group_s_per_km2")}


def band_time(inputs: Dict, model: Dict, lines: float, spots: float, km2: float, band: str, res: float, dsm: bool,
              factors: Dict, memory_gb: float) -> Dict:
    """The wall time of one band of a country at a resolution on a machine: over candidate tile
    cores, the grid (single-core, K tiles at once as memory allows) and the line search (all
    cores), combined; the core with the shortest time wins. A run that keeps only counts holds a
    tile's grids, not its lines (lines_gb_today: what today's search would hold); wall_groups_s
    adds today's grouping into spots (single-core), which may not scale to such counts."""
    low, high = inputs["bands"][band]
    overlap = high + inputs["margin_m"] + 2 * res
    grid_factor = 1.0 if dsm else inputs.get("dsm_off_grid_factor", 1.0)
    serial_km2 = model["grid_s_per_mpx"] * grid_factor / res ** 2  # s per km² of core, no overlap
    line_cpu = model["cpu_a"] * km2 + model["cpu_b"] * lines
    count, groups = model["count_s_per_line"] * lines, model["group_s_per_line"] * lines
    best = None
    combine = lambda a, b: max(a, b) + OVERLAP_SHARE * min(a, b)  # noqa: E731
    for core_km in inputs["cores_km"]:
        core = core_km * 1000.0
        side = core + 2 * overlap
        tile_bytes = (side / res) ** 2 * inputs["pixel_bytes"]
        k = min(int(memory_gb * 1e9 // tile_bytes), factors["physical_cores"])
        if k < 1:
            continue
        serial = (serial_km2 * km2 * (side / core) ** 2 + count) * factors["serial"]
        parallel = line_cpu * factors["cpu"] / factors["parallel_cores"]
        wall = combine(serial / (k * SERIAL_EFFICIENCY), parallel)
        if best is None or wall < best["wall_s"]:
            best = {"band": band, "res": res, "core_km": core_km, "tile_gb": round(tile_bytes / 1e9, 2), "tiles_at_once": k,
                    "serial_s": round(serial), "line_wall_s": round(parallel), "wall_s": round(wall),
                    "wall_groups_s": round(combine((serial + groups * factors["serial"]) / (k * SERIAL_EFFICIENCY),
                                                   parallel)),
                    "lines": round(lines), "spots": round(spots),
                    "lines_gb_today": round(lines / km2 * core_km ** 2 * LINE_BYTES / 1e9, 1)}
    return best


def estimate(inputs: Dict, samples: Dict, base: str) -> Dict:
    """Country totals: for each country, length variant, grid strategy, with and without the DSM,
    machine and scenario (low, mid, high: band_counts): the data, the download and the computing
    time. A band's counts at another resolution than its base are scaled by the median ratio of
    the places measured at both; a band at a resolution without samples has no estimate (None)."""
    metrics = {}
    for name, sample in samples.items():
        found = band_of(name)
        if found and found[1] in inputs["bands"] and not name.endswith(VARIANTS):
            metrics[name] = sample_metrics(sample, inputs["bands"][found[1]][1])
    # The grid without the DSM (one mosaic less): the mean ratio of the <name>-nodsm samples to theirs
    pairs = [(n[:-len("-nodsm")], n) for n in samples if n.endswith("-nodsm") and n[:-len("-nodsm")] in samples]
    if pairs and "dsm_off_grid_factor" not in inputs:
        grid_of = lambda n: sample_metrics(samples[n], 0)["grid_s_per_mpx"]  # noqa: E731
        inputs = {**inputs, "dsm_off_grid_factor": float(np.mean([grid_of(b) / grid_of(a) for a, b in pairs]))}
    factors = {}
    reference = os.path.join(base, inputs["machines"][inputs["reference"]]["bench"])
    for name, machine_ in inputs["machines"].items():
        factors[name] = machine_factors(os.path.join(base, machine_["bench"]), reference)
    with open(os.path.join(base, inputs["relief"]), encoding="utf-8") as f:
        relief_data = json.load(f)
    resolutions = {(b, float(r)) for s in inputs["strategies"].values() for b, r in s.items() if b in inputs["bands"]}
    models = {key: time_model(metrics, *key) for key in sorted(resolutions)}
    strata, counts = {}, {}
    for code in inputs["countries"]:
        for band in inputs["bands"]:
            found = band_counts(relief_data, inputs, code, band)
            strata[f"{code} {band}"] = found
            for b, res in resolutions:
                if b != band or found is None:
                    continue
                scale = {key: 1.0 if res == found["res"] else resolution_ratio(metrics, band, found["res"], res,
                                                                                  f"{key}_per_km2")
                         for key in ("lines", "spots")}
                counts[(code, band, res)] = None if None in scale.values() else \
                    {s: (found["lines"][s] * scale["lines"], found["spots"][s] * scale["spots"]) for s in SCENARIOS}
    rows = []
    for code, country in inputs["countries"].items():
        km2 = country["area_km2"]
        for variant, bands in inputs["variants"].items():
            for strategy, res_of in inputs["strategies"].items():
                finest = min(res_of[b] for b in bands)
                for dsm in (True, False):
                    # The coarsest data the finest grid of the strategy can use (e.g. 2 m files for 5 m)
                    usable = sorted((k for k in country["data"] if float(k) <= finest), key=float)
                    data = country["data"][usable[-1] if usable else min(country["data"], key=float)]
                    layers = {k: v for k, v in data.items() if dsm or k != "surface"}
                    download_mb = sum(v["download_mb_km2"] for v in layers.values()) * km2
                    cache_mb = sum(v["cache_mb_km2"] for v in layers.values()) * km2
                    files = sum(v["files_per_km2"] for v in layers.values()) * km2
                    service = country["service"]
                    # A local copy (Slovakia's mirror) does not cross the internet link
                    seconds = download_mb / (service["mb_s"] if service.get("local") else min(service["mb_s"], inputs["link_mb_s"]))
                    if service.get("requests_per_min"):
                        seconds = max(seconds, files / service["requests_per_min"] * 60)
                    seconds += service.get("index_s", 0)
                    for machine_name, machine_ in inputs["machines"].items():
                        for scenario in SCENARIOS:
                            parts = []
                            for b in bands:
                                res = float(res_of[b])
                                model, found = models.get((b, res)), counts.get((code, b, res))
                                parts.append(None if model is None or found is None else
                                             band_time(inputs, model, *found[scenario], km2, b, res, dsm,
                                                       factors[machine_name], machine_["memory_gb"]))
                            done = None not in parts
                            rows.append({
                                "country": code, "variant": variant, "strategy": strategy, "dsm": dsm,
                                "machine": machine_name, "scenario": scenario,
                                "download_tb": round(download_mb / 1e6, 3), "cache_tb": round(cache_mb / 1e6, 3),
                                "download_days": round(seconds / 86400, 4),
                                "compute_days": round(sum(p["wall_s"] for p in parts) / 86400, 2) if done else None,
                                "compute_hours": round(sum(p["wall_s"] for p in parts) / 3600, 2) if done else None,
                                "compute_days_with_groups":
                                    round(sum(p["wall_groups_s"] for p in parts) / 86400, 2) if done else None,
                                "lines": sum(p["lines"] for p in parts) if done else None,
                                "spots": sum(p["spots"] for p in parts) if done else None,
                                "bands": parts})
    return {"metrics": metrics, "factors": factors, "dsm_off_grid_factor": inputs.get("dsm_off_grid_factor"),
            "models": {f"{b} {r:g} m": m for (b, r), m in models.items()}, "strata": strata, "rows": rows}


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
    p.add_argument("--lean", action="store_true", help="the run keeps lines.npz (the columns compare and cube "
                   "read) instead of lines.csv and lines.geojson")
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
    r = sub.add_parser("relief", help="the countries' relief and the samples' cells (Copernicus GLO-30)")
    r.add_argument("--inputs", required=True)
    r.add_argument("--samples", required=True)
    r.add_argument("--data-dir", required=True, help="the data folder whose cache keeps the GLO-30 tiles")
    r.add_argument("--out", required=True, help="the relief JSON (inputs.json names it as relief)")
    e = sub.add_parser("estimate", help="country totals from the samples")
    e.add_argument("--inputs", required=True, help="the countries, bands, strategies and machines (JSON)")
    e.add_argument("--samples", required=True)
    e.add_argument("--json", help="write the result here too")
    args = parser.parse_args()

    if args.command == "bench":
        bench(args.out, args.processes, args.grid)
    elif args.command == "profile":
        search_args = args.args[1:] if args.args[:1] == ["--"] else args.args
        profile(args.out, args.name, search_args, args.cores, args.tension_by_length, args.lean)
    elif args.command == "compare":
        result = compare(load_samples(args.samples), args.ref, args.others, args.cells, parse_bands(args.bands))
        write_json(args.json, result)
        print(markdown(result["rows"], ["cell", "band", "other", "ref_lines", "other_lines", "lines_ratio",
                                        "ref_spots", "other_spots", "spots_ratio", "cells", "spearman", "lost",
                                        "new"]))
    elif args.command == "relief":
        with open(args.inputs, encoding="utf-8") as f:
            inputs = json.load(f)
        result = relief(inputs, load_samples(args.samples), os.path.abspath(args.data_dir))
        write_json(args.out, result)
        rows = proxy_correlations(result, inputs)
        columns = ["band", "res", "cells"] + [k for k in rows[0] if ":" in k] if rows else []
        print(markdown(rows, columns))
    elif args.command == "estimate":
        with open(args.inputs, encoding="utf-8") as f:
            inputs = json.load(f)
        result = estimate(inputs, load_samples(args.samples), os.path.dirname(os.path.abspath(args.inputs)))
        write_json(args.json, result)
        rows = [{**r, "bands": " ".join(f"{p['band']}:{p['core_km']}km×{p['tiles_at_once']}" for p in r["bands"] if p)}
                for r in result["rows"]]
        print(markdown(rows, ["country", "variant", "strategy", "dsm", "machine", "scenario", "download_tb",
                              "cache_tb", "download_days", "compute_hours", "lines", "spots", "bands"]))
    else:
        result = cube(load_samples(args.samples), args.names, args.cell, args.dims)
        write_json(args.json, result)
        print(markdown(result["rows"], ["name", "cell", "dims", "area_km2", "lines", "line_keys", "line_keys_km2",
                                        "line_bytes_km2", "spots", "spot_keys", "spot_keys_km2", "spot_bytes_km2"]))


if __name__ == "__main__":
    from progress import utf8_output
    utf8_output()  # redirected output in UTF-8, not the Windows code page (no "²" there)
    main()
