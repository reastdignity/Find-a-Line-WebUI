"""
The country layer's driver (docs/country-precompute/contract.md, section 3): a whole country
searched offline in fixed tiles that keep only counts (countcube.py), then summed into its cube.

    findaline.py country run <id> [--processes K] [--bands S,M,L,M2] [--max-tiles N] [--redo] [--yes]
    findaline.py country status <id>
    findaline.py country profile <id>
    findaline.py country build <id> [--partial]
    findaline.py country compare <id> [--control M2] [--against L]
    findaline.py country worker <id> --slot K      (started by run, one per process)

Lines are searched in length bands (Band), each on its own grid and in its own fixed tiles
(search.fixed_tiles): a tile's plan is its band's (search.plan_search(tiled=False) of the
country's outline) on the tile's grid, step 1 as a search's (search.prepare_data), steps 2 and 3
in count mode (search.count_tile) into a countcube.TileCounter, the counts saved per tile
(countcube.save_tile). A tile is the unit of work and of resuming: the manifest (manifest.sqlite,
one row per band and tile) says which are pending, running, done or failed; `run` starts worker
processes that claim tiles from it one at a time, so an interrupted run goes on where it stopped,
and the results never depend on the number of processes or on resuming.

Data (all under <data>/countries/<id>/, nothing else of the data folder changes but the cache and
the tiles' work folders <data>/work/country-<id>/<band>-<name>/):
    country.json   the configuration (Country as JSON), the sha256 of the outline and of both
                   (the config hash every tile file records), the CRS and the cube's origin
    area.geojson   the outline (WGS84), fetched once (osm:<name> through Nominatim)
    manifest.sqlite  the tiles (schema v2, cache.migrate; WAL, claims in BEGIN IMMEDIATE, the
                   heaviest first: their weight from the lines of the tiles done already)
    run.lock       held by `run` (one run at a time; workers stop when it is free)
    logs/          run.log, worker-<k>.log, samples-<start>.csv (a run's timeline)
    tiles/<band>/<name>.npz   the counts of a tile (countcube.VERSION)
    cube/          the cube (countcube.build) and a copy of area.geojson
    compare.json   `compare`'s result
"""

import argparse
import dataclasses
import gc
import glob
import hashlib
import json
import math
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np
import psutil

import cache
import countcube

REPO = os.path.dirname(os.path.abspath(__file__))
PROGRESS_SECONDS = 30      # between the progress lines of a run
WORKER_PROGRESS_SECONDS = 600  # between the text progress lines of a worker's bars (its log)
ATTEMPTS = 2               # a tile that fails goes back to pending once, then stays failed
# The memory of a counting worker: WORKER_BASE plus COUNT_PIXEL_BYTES per pixel of its tile's grid.
# Measured on Slovakia's runs (2026-11-03): a worker's peak working set was 2.3 GiB at 38-40 Mpx in
# the bands S, M and L alike (50-53 B/px above 0.5 GiB of imports, an evaluated part of the sink and
# the counter's pending arrays), the memory-mapped grids included and the tiles of 200-400 M lines
# too (the sink holds one part at a time); both values with a margin. Not search.memory_needed: a
# count holds no table of lines, no profiles and no step 4, and that model follows the app's.
COUNT_PIXEL_BYTES = 64
WORKER_BASE = 512 << 20
RETHREAD_SECONDS = 10      # between the looks of a counting tile at the workers still busy (_Rethreading)
TILE_SAMPLE_SECONDS = 0.5  # between the samples of a counting worker's memory (_MemorySampler)
RUN_SAMPLE_SECONDS = 5     # between the rows of a run's timeline (_RunSamples: logs/samples-<start>.csv)
DISK_PIXEL_BYTES = 16      # a tile's grids in its work folder (float32 terrain, masks of water and gaps)
DISK_SPARE = 1 << 30       # free disk kept besides the work folders
RESPAWNS_PER_WORKER = 2    # workers that stopped abnormally are started again at most this often (on average)
ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


@dataclass(frozen=True)
class Band:
    """A length band of a country: its lines searched on its own grid in its own fixed tiles."""
    name: str
    lengths: Tuple[float, float]  # [lo, hi): searched with min_length lo and max_length hi
    resolution: float
    model: str                    # "formula" or "sag" (T(L): Country.tension)
    slope_threshold: float
    core_m: float                 # the side of a tile's core
    layer: bool                   # in the cube; False: a control band (country compare)


@dataclass(frozen=True)
class Country:
    id: str
    name: str
    source: str
    area: str                     # an area spec of area.from_spec, e.g. "osm:Slovensko"
    bands: Tuple[Band, ...]
    tension: Tuple[Tuple[float, float], ...]  # T(L): (span m, pretension kN), sag.tension_at
    rig: Dict[str, float] = field(default_factory=dict)      # SearchParams' webbing fields
    options: Dict[str, str] = field(default_factory=dict)    # nmpt, water, coastline, fill_gaps (elevation_file: tests)

    def config(self) -> Dict:
        """The configuration as JSON values (country.json)."""
        return json.loads(json.dumps(dataclasses.asdict(self)))

    @classmethod
    def from_config(cls, config: Dict) -> "Country":
        bands = tuple(Band(**{**b, "lengths": tuple(b["lengths"])}) for b in config["bands"])
        return cls(config["id"], config["name"], config["source"], config["area"], bands,
                   tuple(tuple(p) for p in config["tension"]), dict(config.get("rig") or {}),
                   dict(config.get("options") or {}))

    def band(self, name: str) -> Band:
        for band in self.bands:
            if band.name == name:
                return band
        raise CountryError(f"{self.id} has no band {name} (its bands: {', '.join(b.name for b in self.bands)})")

    @property
    def last_edge(self) -> float:
        return float(countcube.LENGTH_EDGES[-1])


COUNTRIES = {
    "slovakia": Country(
        id="slovakia", name="Slovakia", source="slovakia", area="osm:Slovensko",
        bands=(Band("S", (30, 300), 1.0, "formula", 60, 5000, True),
               Band("M", (300, 1000), 2.0, "sag", 60, 10000, True),
               Band("L", (1000, 5000), 5.0, "sag", 45, 20000, True),
               Band("M2", (1000, 2000), 2.0, "sag", 60, 10000, False)),
        tension=((300, 2.5), (1500, 6.0), (5000, 15.0)),
        rig={"webbing_weight": 41.0, "stretch": 2.1},  # Silk 99; the other rigging fields at their defaults
        # The pilot runs without the DSM (the user's decision of 2026-11-02)
        options={"nmpt": "off", "water": "fill", "coastline": "copernicus", "fill_gaps": "on"}),
}


class CountryError(Exception):
    """A command cannot go on; the message is meant for the user."""


# --- country.json, the outline -------------------------------------------------------------------

def folder_of(data_dir: str, country_id: str) -> str:
    if not ID_PATTERN.match(country_id):
        raise CountryError(f"{country_id!r} is not a country id (lower case letters, digits, - and _)")
    return os.path.join(data_dir, "countries", country_id)


def _sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def config_hash(config: Dict, area_sha256: str) -> str:
    """What every tile file records (meta "config"): the configuration and the outline."""
    text = json.dumps({"config": config, "area_sha256": area_sha256}, sort_keys=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_state(folder: str) -> Dict:
    """country.json."""
    path = os.path.join(folder, "country.json")
    if not os.path.exists(path):
        raise CountryError(f"{folder} has no country.json: start with `findaline.py country run <id>`")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: str, value: Dict):
    with cache.replacing(path, "w", encoding="utf-8") as f:
        json.dump(value, f, indent=1, ensure_ascii=False)


def _write_outline(country: Country, folder: str, data_dir: str):
    """area.geojson: the outline of the country's area spec, as it is (WGS84)."""
    import area as ar
    from shapely.geometry import mapping
    shape = ar.from_spec(country.area, 0.0, None, os.path.join(data_dir, "cache")).geometry
    feature = {"type": "Feature", "properties": {"id": country.id, "name": country.name, "area": country.area},
               "geometry": mapping(shape)}
    _write_json(os.path.join(folder, "area.geojson"), feature)


def _remove_results(folder: str):
    """--redo: the tiles, the cube, the manifest and the comparison."""
    for name in ("tiles", "cube"):
        shutil.rmtree(os.path.join(folder, name), ignore_errors=True)
    for name in ("manifest.sqlite", "manifest.sqlite-wal", "manifest.sqlite-shm", "compare.json"):
        path = os.path.join(folder, name)
        if os.path.exists(path):
            os.remove(path)


def setup(country_id: str, folder: str, data_dir: str, redo: bool, say) -> Tuple[Dict, Country]:
    """country.json (written the first time, from COUNTRIES or a country.json holding only "config"),
    and area.geojson (fetched once). A configuration or outline other than the tiles' is refused
    unless redo, which removes the tiles, the cube and the manifest."""
    path = os.path.join(folder, "country.json")
    state = read_state(folder) if os.path.exists(path) else {}
    if country_id in COUNTRIES:
        config = COUNTRIES[country_id].config()
    elif "config" in state:
        config = state["config"]
    else:
        raise CountryError(f"Unknown country {country_id!r}: one of {', '.join(sorted(COUNTRIES))}")
    if config["id"] != country_id:
        raise CountryError(f"{path} describes {config['id']!r}, not {country_id!r}")
    country = Country.from_config(config)
    stored = state.get("config")
    if stored is not None and stored != config and not redo:
        raise CountryError(f"The configuration of {country_id} changed since its tiles were counted: run again with "
                           f"--redo to count everything again")
    outline = os.path.join(folder, "area.geojson")
    if not os.path.exists(outline) or (stored is not None and stored.get("area") != config["area"]):
        say(f"Outline of {country.name}: {country.area}")
        _write_outline(country, folder, data_dir)
    area_sha = _sha256_file(outline)
    digest = config_hash(config, area_sha)
    if state.get("hash") not in (None, digest):
        if not redo:
            raise CountryError(f"The configuration or outline of {country_id} changed since its tiles were counted: "
                               f"run again with --redo to count everything again")
    if redo or state.get("hash") not in (None, digest):
        say("--redo: the tiles, the cube and the manifest are removed")
        _remove_results(folder)
        state.pop("origin", None)
    state.update(config=config, area_sha256=area_sha, hash=digest)
    state.setdefault("created", _now())
    return state, country


def _finish_state(state: Dict, folder: str, plans: Dict):
    """The CRS, the cube's origin (once: countcube.origin_of the outline's bounds in the CRS) and the
    outline's WGS84 bounds, then country.json."""
    plan = next(iter(plans.values()))
    state["crs"] = plan.crs
    if "origin" not in state:
        state["origin"] = list(countcube.origin_of(plan.grid.area_shape.bounds))
    state["bounds_wgs84"] = [round(v, 6) for v in plan.area.geometry.bounds]
    _write_json(os.path.join(folder, "country.json"), state)


# --- the plans of the bands ----------------------------------------------------------------------

def form_params(country: Country, band: Band) -> Dict:
    """SearchParams fields of a band, as the app's form takes them (cube.json's "params"): for a sag
    band the pretension is T at its max_length (the most tension and the least sag, so a search of a
    cell finds a superset of the lines T(L) gives)."""
    import sag as sg
    lo, hi = band.lengths
    params = {"source": country.source, "min_length": lo, "max_length": hi, "resolution": band.resolution,
              "model": band.model, "slope_threshold": band.slope_threshold}
    params.update({k: v for k, v in country.options.items() if k in ("nmpt", "water", "coastline", "fill_gaps")})
    params["pretension"] = sg.tension_at(country.tension, hi)
    params.update(country.rig)
    return params


def band_plan(country: Country, band: Band, folder: str, data_dir: str, emit=None):
    """The band's plan over the whole outline (search.plan_search(tiled=False), area.geojson)."""
    import search
    from params import SearchParams
    values = form_params(country, band)
    values["area"] = os.path.join(folder, "area.geojson")
    if country.options.get("elevation_file"):
        values["elevation_file"] = country.options["elevation_file"]
    paths = search.Paths(data_dir, os.path.join(data_dir, "work", f"country-{country.id}"))
    try:
        return search.plan_search(SearchParams(**values), paths, emit or (lambda kind, text: None), tiled=False)
    except search.SearchError as e:
        raise CountryError(f"Band {band.name}: {e}") from e


def tension_table(country: Country, band: Band, plan):
    """The sag table of a sag band (sag.TensionTable of T(L) over its lengths); None for the formula."""
    if band.model != "sag":
        return None
    import sag as sg
    return sg.TensionTable(plan.rigging, band.lengths[0], band.lengths[1], country.tension)


# --- the manifest --------------------------------------------------------------------------------

MIGRATIONS = [
    """
    CREATE TABLE tiles (
        band TEXT NOT NULL,
        name TEXT NOT NULL,
        core TEXT NOT NULL,                       -- JSON [left, bottom, right, top] in the country's CRS
        status TEXT NOT NULL DEFAULT 'pending',   -- pending | running | done | failed
        attempts INTEGER NOT NULL DEFAULT 0,      -- claims that ended (or are running), not counting interruptions
        worker TEXT, started_at TEXT, finished_at TEXT,
        seconds REAL, lines INTEGER, spots INTEGER, error TEXT,
        PRIMARY KEY (band, name));
    CREATE INDEX tiles_status ON tiles (status, band);
    -- what the workers of the current run may claim: its bands, the tiles it may still start
    -- (--max-tiles; NULL: all) and its processes (for the threads of a tile)
    CREATE TABLE run (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        bands TEXT NOT NULL, tiles_left INTEGER, processes INTEGER NOT NULL, started_at TEXT);
    """,
    # v2: the work a pending tile is expected to take (_weights, set by each run): claimed heaviest
    # first, so the long tiles never come last; NULL (nothing known) after the others, in rowid order
    """
    ALTER TABLE tiles ADD COLUMN weight REAL;
    """,
]


class Manifest:
    """manifest.sqlite: the tiles of a country and their state (WAL: workers claim while the run reads)."""

    def __init__(self, folder: str):
        self.db = sqlite3.connect(os.path.join(folder, "manifest.sqlite"), timeout=120, isolation_level=None)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA busy_timeout=120000")
        cache.migrate(self.db, MIGRATIONS)

    def close(self):
        self.db.close()

    def _write(self, work):
        """work(db) in one write transaction (BEGIN IMMEDIATE)."""
        self.db.execute("BEGIN IMMEDIATE")
        try:
            result = work(self.db)
            self.db.execute("COMMIT")
            return result
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def add_tiles(self, band: str, tiles) -> None:
        self._write(lambda db: db.executemany(
            "INSERT OR IGNORE INTO tiles (band, name, core) VALUES (?, ?, ?)",
            [(band, t.name, json.dumps(list(t.core))) for t in tiles]))

    def release_running(self, worker: Optional[str] = None) -> int:
        """Running tiles (of one worker, or all) back to pending: an interruption, not a failure."""
        where, args = ("status = 'running'", ()) if worker is None else ("status = 'running' AND worker = ?", (worker,))
        return self._write(lambda db: db.execute(
            f"UPDATE tiles SET status = 'pending', attempts = MAX(attempts - 1, 0), worker = NULL, started_at = NULL "
            f"WHERE {where}", args).rowcount)

    def set_run(self, bands: Sequence[str], tiles_left: Optional[int], processes: int):
        self._write(lambda db: db.execute(
            "INSERT OR REPLACE INTO run (id, bands, tiles_left, processes, started_at) VALUES (1, ?, ?, ?, ?)",
            (json.dumps(list(bands)), tiles_left, processes, _now())))

    def claim(self, worker: str, cores: int) -> Optional[Tuple[str, str, Tuple[float, ...], int]]:
        """The next pending tile of the run's bands (the heaviest first, by weight; then in the
        order they were added: bands as configured, rows from the north), marked running; with the
        threads its count may use (_threads). None when nothing is left to claim."""
        def work(db):
            row = db.execute("SELECT bands, tiles_left, processes FROM run WHERE id = 1").fetchone()
            if row is None or (row[1] is not None and row[1] <= 0):
                return None
            bands = json.loads(row[0])
            marks = ",".join("?" * len(bands))
            tile = db.execute(f"SELECT band, name, core FROM tiles WHERE status = 'pending' AND band IN ({marks}) "
                              f"ORDER BY weight IS NULL, weight DESC, rowid LIMIT 1", bands).fetchone()
            if tile is None:
                return None
            db.execute("UPDATE tiles SET status = 'running', attempts = attempts + 1, worker = ?, started_at = ?, "
                       "error = NULL WHERE band = ? AND name = ?", (worker, _now(), tile[0], tile[1]))
            if row[1] is not None:
                db.execute("UPDATE run SET tiles_left = tiles_left - 1 WHERE id = 1")
            return tile[0], tile[1], tuple(json.loads(tile[2])), _threads(db, bands, row[2], cores)
        return self._write(work)

    def threads(self, cores: int) -> int:
        """The threads a counting tile may use now (_threads; one when no run is set)."""
        row = self.db.execute("SELECT bands, processes FROM run WHERE id = 1").fetchone()
        return 1 if row is None else _threads(self.db, json.loads(row[0]), row[1], cores)

    def set_weights(self, weights: Dict[Tuple[str, str], float]) -> None:
        """The weights of pending tiles by (band, name) (_weights)."""
        self._write(lambda db: db.executemany(
            "UPDATE tiles SET weight = ? WHERE band = ? AND name = ? AND status = 'pending'",
            [(w, band, name) for (band, name), w in weights.items()]))

    def done(self, band: str, name: str, seconds: float, lines: int, spots: int):
        self._write(lambda db: db.execute(
            "UPDATE tiles SET status = 'done', finished_at = ?, seconds = ?, lines = ?, spots = ?, error = NULL "
            "WHERE band = ? AND name = ?", (_now(), seconds, lines, spots, band, name)))

    def fail(self, band: Optional[str], name: Optional[str], error: str, worker: Optional[str] = None) -> int:
        """A tile (or the running tiles of a worker that stopped) failed: back to pending after its
        first attempt, failed after ATTEMPTS."""
        where, args = (("band = ? AND name = ?", (band, name)) if worker is None
                       else ("status = 'running' AND worker = ?", (worker,)))
        return self._write(lambda db: db.execute(
            f"UPDATE tiles SET status = CASE WHEN attempts < {ATTEMPTS:d} THEN 'pending' ELSE 'failed' END, "
            f"worker = NULL, finished_at = ?, error = ? WHERE {where}", (_now(), error[-2000:], *args)).rowcount)

    def rows(self, band: Optional[str] = None) -> List[sqlite3.Row]:
        self.db.row_factory = sqlite3.Row
        try:
            if band is None:
                return self.db.execute("SELECT * FROM tiles ORDER BY rowid").fetchall()
            return self.db.execute("SELECT * FROM tiles WHERE band = ? ORDER BY rowid", (band,)).fetchall()
        finally:
            self.db.row_factory = None

    def counts(self) -> Dict[str, Dict[str, int]]:
        """Tiles per band and status."""
        out: Dict[str, Dict[str, int]] = {}
        for band, status, n in self.db.execute("SELECT band, status, COUNT(*) FROM tiles GROUP BY band, status"):
            out.setdefault(band, {})[status] = n
        return out


def _threads(db, bands: Sequence[str], processes: int, cores: int) -> int:
    """The threads of a counting tile: the logical cores shared by the workers still busy (the
    running and pending tiles of the run's bands, at most its processes)."""
    marks = ",".join("?" * len(bands))
    running, pending = db.execute(
        f"SELECT SUM(status = 'running'), SUM(status = 'pending') FROM tiles WHERE band IN ({marks})",
        list(bands)).fetchone()
    busy = max(1, min(processes, (running or 0) + (pending or 0)))
    return max(1, cores // busy)


def _weights(manifest: Manifest, bands: Sequence[str]) -> Dict[Tuple[str, str], float]:
    """The expected work of the pending tiles of these bands: the lines of the tiles done already
    (of any band) whose core overlaps theirs; empty when no tile is done yet. Beyond its grid, a
    tile's time goes to the pair search of its lines, and the lines of every band lie where the
    terrain is steep (Slovakia: the Tatras' tiles took 14 and 35 min, most others seconds)."""
    rows = manifest.db.execute("SELECT band, name, core, status, lines FROM tiles").fetchall()
    done = [(json.loads(core), lines or 0) for _, _, core, status, lines in rows if status == "done"]
    if not done:
        return {}
    cores = np.array([c for c, _ in done], dtype=np.float64)
    lines = np.array([n for _, n in done], dtype=np.float64)
    out = {}
    for band, name, core, status, _ in rows:
        if status == "pending" and band in bands:
            left, bottom, right, top = json.loads(core)
            over = (cores[:, 0] < right) & (left < cores[:, 2]) & (cores[:, 1] < top) & (bottom < cores[:, 3])
            out[(band, name)] = float(lines[over].sum())
    return out


class _Rethreading:
    """The sink of a tile's count that sets numba's threads as the other workers end: after a part
    (search.count_tile hands the parts over between the line search's chunks, in the thread that
    starts its kernels), at most every RETHREAD_SECONDS, the threads threads_now() gives (the
    manifest's _threads). So the tiles counted last take the cores of the workers that are done;
    the counts never depend on the threads (tests/test_units.py::test_kernels_independent_of_threads)."""

    def __init__(self, sink, threads_now: Callable[[], int], threads: int, clock=time.monotonic):
        self.sink, self.threads_now, self.threads, self.clock = sink, threads_now, threads, clock
        self.most = threads  # the most threads the count got (the tile's meta: threads_max)
        self.looked = clock()

    def __call__(self, part):
        self.sink(part)
        if self.clock() - self.looked < RETHREAD_SECONDS:
            return
        self.looked = self.clock()
        try:
            threads = self.threads_now()
        except sqlite3.Error:  # the manifest busy for longer than its timeout: the next look
            return
        if threads != self.threads:
            import numba
            self.threads = max(1, min(threads, numba.config.NUMBA_NUM_THREADS))
            numba.set_num_threads(self.threads)
            self.most = max(self.most, self.threads)


# --- the work of a tile --------------------------------------------------------------------------

def _peak_memory() -> Optional[int]:
    """The peak memory of this process so far, in bytes (Windows: the peak working set)."""
    info = psutil.Process().memory_info()
    if hasattr(info, "peak_wset"):
        return int(info.peak_wset)
    try:
        import resource
        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return int(peak if sys.platform == "darwin" else peak * 1024)
    except (ImportError, OSError):
        return None


def _commit() -> Optional[str]:
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True, timeout=10)
        return out.stdout.strip() or None if out.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def _private(memory) -> int:
    """The private bytes of a psutil memory_info: what the system cannot drop (Windows' commit; else
    the resident pages less the shared ones). The memory-mapped grids are file pages: they count in
    the working set (rss) only."""
    private = getattr(memory, "private", None)
    return int(private if private is not None else memory.rss - getattr(memory, "shared", 0))


def _io_counters() -> Tuple[int, int]:
    """Bytes read and written by this process so far (its file reads and writes; the pages of the
    memory-mapped grids the system writes are not among them)."""
    try:
        io = psutil.Process().io_counters()
        return int(io.read_bytes), int(io.write_bytes)
    except (psutil.Error, AttributeError):
        return 0, 0


class _StageClock:
    """A progress listener (progress.subscribe) summing the wall and CPU seconds of a tile per
    stage: the label of the bar running, "other" between the bars. CPU: time.process_time, every
    thread of the process, so the CPU over the wall seconds is the cores a stage used."""

    def __init__(self, clock=time.monotonic, cpu=time.process_time):
        self.clock, self.cpu = clock, cpu
        self.current = "other"
        self.since, self.cpu_since = clock(), cpu()
        self.times: Dict[str, List[float]] = {}
        self.lock = threading.Lock()  # bars may be updated from the threads of a pool

    def _add(self):
        now, cpu = self.clock(), self.cpu()
        times = self.times.setdefault(self.current, [0.0, 0.0])
        times[0] += now - self.since
        times[1] += cpu - self.cpu_since
        self.since, self.cpu_since = now, cpu

    def __call__(self, state: Dict):
        if not state.get("bar"):
            return  # the text of a step
        stage = state.get("stage") or "other"
        with self.lock:
            if not state.get("done"):
                if stage != self.current:
                    self._add()
                    self.current = stage
            elif stage == self.current:
                self._add()
                self.current = "other"

    def result(self) -> Dict[str, List[float]]:
        """{stage: [seconds, CPU seconds]} up to now."""
        with self.lock:
            self._add()
            return {name: [round(s, 3), round(c, 3)] for name, (s, c) in self.times.items()}


class _TimedSink:
    """The counter's wall and CPU seconds (numpy on one thread, between the line search's chunks
    and at its end): a sink, and its result()."""

    def __init__(self, counter):
        self.counter, self.seconds, self.cpu = counter, 0.0, 0.0

    def _timed(self, call, *args):
        t, c = time.monotonic(), time.process_time()
        try:
            return call(*args)
        finally:
            self.seconds += time.monotonic() - t
            self.cpu += time.process_time() - c

    def __call__(self, part):
        self._timed(self.counter, part)

    def result(self):
        return self._timed(self.counter.result)


class _MemorySampler(threading.Thread):
    """This process's memory while a tile is counted, every TILE_SAMPLE_SECONDS: the peak working
    set (rss) and private bytes (_private), and the peak private bytes per stage of clock."""

    def __init__(self, clock: _StageClock):
        super().__init__(daemon=True)
        self.clock, self.process, self.halt = clock, psutil.Process(), threading.Event()
        self.rss = self.private = 0
        self.stages: Dict[str, int] = {}

    def run(self):
        while not self.halt.is_set():
            self.sample()
            self.halt.wait(TILE_SAMPLE_SECONDS)

    def sample(self):
        try:
            memory = self.process.memory_info()
        except psutil.Error:
            return
        private, stage = _private(memory), self.clock.current
        self.rss, self.private = max(self.rss, int(memory.rss)), max(self.private, private)
        self.stages[stage] = max(self.stages.get(stage, 0), private)

    def stop(self) -> Dict:
        self.halt.set()
        self.join()
        self.sample()
        return {"rss": self.rss, "private": self.private, "stages": dict(self.stages)}


class TileWork:
    """Counts the tiles one process claims: the bands' plans and sag tables made once per process."""

    def __init__(self, folder: str, data_dir: str, slot: int):
        self.folder, self.data_dir = folder, data_dir
        self.state = read_state(folder)
        self.country = Country.from_config(self.state["config"])
        self.origin = tuple(self.state["origin"])
        self.worker = f"slot-{slot}"
        self.plans: Dict[str, object] = {}
        self.tables: Dict[str, object] = {}
        self.commit = _commit()
        self.cores = os.cpu_count() or 1

    def _band(self, name: str):
        band = self.country.band(name)
        if name not in self.plans:
            plan = band_plan(self.country, band, self.folder, self.data_dir)
            self.plans[name] = plan
            self.tables[name] = tension_table(self.country, band, plan)
        return band, self.plans[name], self.tables[name]

    def tile_path(self, band: str, name: str) -> str:
        return os.path.join(self.folder, "tiles", band, f"{name}.npz")

    def count(self, band_name: str, name: str, core: Tuple[float, ...], threads: int,
              threads_now: Optional[Callable[[], int]] = None) -> Dict:
        """One tile: step 1, the count, its file; returns its meta. threads_now: the threads the
        count may take as it goes on (_Rethreading), else threads throughout."""
        import search
        import sources as src
        from progress import progress
        band, plan, table = self._band(band_name)
        started = _now()
        res = plan.resolution
        grid = search.tile_grid(plan.grid, core, search._overlap(plan.params, res), res, plan.source.grid_origin)
        work = os.path.join(self.data_dir, "work", f"country-{self.country.id}", f"{band.name}-{name}")
        shutil.rmtree(work, ignore_errors=True)
        os.makedirs(work, exist_ok=True)
        # search_grid: the band's grid, as search_lines gives its tiles (the world file's water
        # polygons read once per band in this process, coast.sea_mask's extent)
        tile_plan = dataclasses.replace(plan, params=plan.params.model_copy(update={"threads": threads}), grid=grid,
                                        paths=search.Paths(self.data_dir, work), tiles=None, funnel={},
                                        tile_label=f"{band.name} {name} · ", emit=_print_event,
                                        search_grid=plan.grid)
        print(f"\n--- Band {band.name}, tile {name} ({grid.width} x {grid.height} px, {threads} threads) ---",
              flush=True)
        src.used_data.clear()
        # The profile of the tile (`country profile`): seconds and CPU per stage, the counter's
        # share, the memory sampled while it runs, its file reads and writes
        clock = _StageClock()
        sampler = _MemorySampler(clock)
        cpu0, (read0, written0) = time.process_time(), _io_counters()
        progress.subscribe(clock)
        sampler.start()
        try:
            t0 = time.time()
            data = search.prepare_data(tile_plan)
            t1 = time.time()
            counter = _TimedSink(countcube.TileCounter(grid, self.origin, core, band.lengths,
                                                       float(band.lengths[1]) >= self.country.last_edge))
            sink = counter if threads_now is None else _Rethreading(counter, threads_now, threads)
            funnel = search.count_tile(tile_plan, data, core, sink, table)
            counts = counter.result()
            t2 = time.time()
        finally:
            memory = sampler.stop()
            progress.unsubscribe(clock)
        read1, written1 = _io_counters()
        del data
        gc.collect()  # close the memory-mapped grids before their folder is removed (Windows)
        meta = {"version": countcube.VERSION, "config": self.state["hash"], "origin": list(self.origin),
                "country": self.country.id, "band": band.name, "tile": name, "core": list(core),
                "grid": {"width": grid.width, "height": grid.height, "res": res, "left": grid.left, "top": grid.top},
                "lines": counts.lines, "spots": int(len(counts.spot_ids)), "dropped": counts.dropped,
                "funnel": dict(funnel), "seconds": {"prepare": round(t1 - t0, 3), "count": round(t2 - t1, 3)},
                "stages": clock.result(), "sink": [round(counter.seconds, 3), round(counter.cpu, 3)],
                "cpu_seconds": round(time.process_time() - cpu0, 3), "memory": memory,
                "io": {"read": read1 - read0, "write": written1 - written0},
                "threads": threads, "threads_max": getattr(sink, "most", threads), "peak_memory": _peak_memory(),
                "commit": self.commit,
                "data": json.loads(json.dumps(src.used_data)), "started": started, "finished": _now()}
        path = self.tile_path(band.name, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        countcube.save_tile(path, counts, meta)
        print(f"Tile {band.name} {name}: {counts.lines} lines, {len(counts.spot_ids)} spots, "
              f"{t2 - t0:.1f} s", flush=True)
        return meta

    def cleanup(self, band: str, name: str):
        import sources as src
        gc.collect()
        shutil.rmtree(os.path.join(self.data_dir, "work", f"country-{self.country.id}", f"{band}-{name}"),
                      ignore_errors=True)
        src.used_data.clear()

    def loop(self, manifest: Manifest, run_gone=None) -> int:
        """Claim and count tiles until none is left (or the run is gone); returns the tiles done."""
        done = 0
        while True:
            if run_gone is not None and run_gone():
                print("The run is gone: this worker stops", flush=True)
                break
            claimed = manifest.claim(self.worker, self.cores)
            if claimed is None:
                break
            band, name, core, threads = claimed
            try:
                meta = self.count(band, name, core, threads, threads_now=lambda: manifest.threads(self.cores))
            except Exception as e:  # the tile fails (pending again once, then failed); the others go on
                traceback.print_exc()
                sys.stdout.flush()
                self.cleanup(band, name)
                manifest.fail(band, name, f"{type(e).__name__}: {cache.clean_error(e)}")
                continue
            seconds = meta["seconds"]["prepare"] + meta["seconds"]["count"]
            manifest.done(band, name, seconds, meta["lines"], meta["spots"])
            self.cleanup(band, name)
            done += 1
        return done


def _print_event(kind: str, text: str):
    print(("WARNING: " if kind == "warning" else "") + str(text), flush=True)


def worker(country_id: str, data_dir: str, slot: int) -> int:
    """`country worker`: a process of a run, claiming tiles until none is left. It reads only
    country.json and the manifest, and stops when the run's lock is free (the run is gone)."""
    import progress as pg
    from filelock import FileLock, Timeout
    from progress import progress
    folder = folder_of(data_dir, country_id)
    pg.TEXT_INTERVAL = WORKER_PROGRESS_SECONDS
    lock_path = os.path.join(folder, "run.lock")

    def run_gone() -> bool:
        lock = FileLock(lock_path)
        try:
            lock.acquire(timeout=0)
        except Timeout:
            return False
        lock.release()
        return True

    print(f"Worker {slot} of {country_id} started (pid {os.getpid()}, {_now()})", flush=True)
    work = TileWork(folder, data_dir, slot)
    manifest = Manifest(folder)
    try:
        with progress.bars():
            done = work.loop(manifest, run_gone)
    finally:
        manifest.close()
    print(f"Worker {slot} done: {done} tiles ({_now()})", flush=True)
    return 0


# --- run -----------------------------------------------------------------------------------------

class _Log:
    """The run's lines: printed and appended to logs/run.log."""

    def __init__(self, folder: str):
        self.path = os.path.join(folder, "logs", "run.log")
        os.makedirs(os.path.dirname(self.path), exist_ok=True)

    def __call__(self, text: str):
        print(text, flush=True)
        with open(self.path, "a", encoding="utf-8") as f:
            stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            f.write("".join(f"{stamp} {line}\n" for line in str(text).splitlines() or [""]))


def _duration(seconds: float) -> str:
    from progress import _duration as text
    return text(seconds)


def worker_count(largest_px: int, available: Optional[int] = None) -> Tuple[int, float]:
    """The processes of a run (at most the physical cores, each with the memory of the largest
    tile: WORKER_BASE plus COUNT_PIXEL_BYTES per pixel) and the bytes each needs."""
    import search
    per = WORKER_BASE + COUNT_PIXEL_BYTES * largest_px
    available = search.available_memory() if available is None else available
    cores = psutil.cpu_count(logical=False) or os.cpu_count() or 1
    return max(1, min(cores, int(available // per))), per


def _ask(question: str) -> bool:
    from progress import progress
    try:
        answer = progress.ask(question)
    except EOFError:
        answer = ""
    return answer.strip().lower() in ("y", "yes", "t", "tak")


def _prefetch(plans: Dict, say):
    """The data over the whole country into the cache (sources.download_layers of the terrain, the
    surface when used and the water mask) on the grid of each resolution (a band's grid: its tiles
    lie within it), before the workers start. Gap filling data stays with the tiles."""
    import search
    import sources as src
    largest = {}
    for plan in plans.values():
        best = largest.get(plan.resolution)
        if best is None or plan.grid.width * plan.grid.height > best.grid.width * best.grid.height:
            largest[plan.resolution] = plan
    for res, plan in sorted(largest.items()):
        layers = list(zip(plan.layers, ("terrain", "surface")))
        if plan.params.water == "fill" or search._fills_gaps(plan):
            layers.append((src.WATER_MASK, "water mask"))
        say(f"Prefetch at {res:g} m: {', '.join(label for _, label in layers)}")
        try:
            src.download_layers(layers, plan.grid, plan.paths.cache, None)
        except RuntimeError as e:
            say(f"WARNING: the prefetch failed ({cache.clean_error(e)}): the tiles download what they need")


class _Everywhere:
    """The area of the warm-up: every pixel."""

    def mask(self, grid):
        return np.ones((grid.height, grid.width), dtype=bool)


def _warm_up(country: Country, plans: Dict, folder: str, data_dir: str, say):
    """Compile the numba kernels once (cached in __pycache__) before the workers start: a tiny
    count of each model on a synthetic canyon, with the arrays as step 1 gives them (memory-mapped,
    read-only)."""
    import grid as gd
    import sag as sg
    import search
    work = os.path.join(data_dir, "work", f"country-{country.id}", "warm-up")
    os.makedirs(work, exist_ok=True)
    size = 64
    elevation = np.full((size, size), 100.0, dtype=np.float32)
    elevation[:, 20:44] = 0.0
    np.save(os.path.join(work, "nmt.npy"), elevation)
    np.save(os.path.join(work, "water.npy"), np.zeros((size, size), dtype=bool))
    data = search.Data(np.load(os.path.join(work, "nmt.npy"), mmap_mode="r"), None,
                       np.load(os.path.join(work, "water.npy"), mmap_mode="r"), None, None)
    models = {}
    for name, plan in plans.items():
        models.setdefault(plan.params.model, (country.band(name), plan))
    for model, (band, plan) in models.items():
        grid = gd.make_grid((0.0, 0.0, size * 1.0, size * 1.0), 1.0, plan.crs)
        params = plan.params.model_copy(update={"min_length": 10, "max_length": 40, "resolution": 1.0})
        small = dataclasses.replace(plan, params=params, grid=grid, resolution=1.0, area=_Everywhere(), funnel={},
                                    emit=lambda kind, text: None, paths=search.Paths(data_dir, work))
        table = sg.TensionTable(plan.rigging, 10, 40, country.tension) if model == "sag" else None
        found = []
        search.count_tile(small, data, None, found.append, table)
        say(f"Warm-up of the {model} model: {sum(len(p) for p in found)} lines")
    del data
    gc.collect()
    shutil.rmtree(work, ignore_errors=True)


def _progress_line(manifest: Manifest, bands: Sequence[str], processes: int, started: float) -> str:
    rows = manifest.db.execute("SELECT band, status, COUNT(*), SUM(lines), SUM(seconds) FROM tiles "
                               "GROUP BY band, status").fetchall()
    total: Dict[str, int] = {}
    done: Dict[str, int] = {}
    lines, left = 0, 0.0
    seconds: Dict[str, float] = {}
    for band, status, n, n_lines, n_seconds in rows:
        total[band] = total.get(band, 0) + n
        if status == "done":
            done[band] = n
            lines += n_lines or 0
            seconds[band] = (n_seconds or 0.0) / max(n, 1)
    known = True
    for band in bands:
        remaining = total.get(band, 0) - done.get(band, 0)
        if remaining:
            if band in seconds:
                left += remaining * seconds[band]
            else:
                known = False
    parts = [f"{b} {done.get(b, 0)}/{total.get(b, 0)}" for b in total]
    eta = f"~{_duration(left / max(processes, 1))} left" if known else "time left unknown yet"
    return (f"[{datetime.now():%H:%M:%S}] tiles {', '.join(parts)} · {lines:,} lines · "
            f"{_duration(time.time() - started)} elapsed, {eta}")


def _worker_process(country_id: str, data_dir: str, folder: str, slot: int) -> subprocess.Popen:
    """A `country worker` process, logging to logs/worker-<k>.log, in a process group of its own (a
    Ctrl+C of the console reaches the run only, which stops the workers itself)."""
    log = open(os.path.join(folder, "logs", f"worker-{slot}.log"), "ab")
    env = {**os.environ, "FINDALINE_PROGRESS": "text", "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"}
    kwargs = {}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    try:
        return subprocess.Popen([sys.executable, os.path.join(REPO, "findaline.py"), "country", "worker", country_id,
                                 "--slot", str(slot), "--data-dir", data_dir],
                                stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, cwd=REPO, env=env,
                                **kwargs)
    finally:
        log.close()  # the child has its own handle


def run(country_id: str, data_dir: str, processes: Optional[int] = None, bands: Optional[Sequence[str]] = None,
        max_tiles: Optional[int] = None, redo: bool = False, yes: bool = False) -> int:
    """`country run`: count the tiles still pending, then build the cube when every layer band is
    done. Returns the exit code (0 done or more to do, 1 failed tiles or refused, 130 interrupted)."""
    from filelock import FileLock, Timeout
    folder = folder_of(data_dir, country_id)
    os.makedirs(os.path.join(folder, "logs"), exist_ok=True)
    lock = FileLock(os.path.join(folder, "run.lock"))
    try:
        lock.acquire(timeout=0)
    except Timeout:
        print(f"Another run of {country_id} is going on (its lock: {lock.lock_file})")
        return 1
    say = _Log(folder)
    try:
        return _run(country_id, data_dir, folder, processes, bands, max_tiles, redo, yes, say)
    except CountryError as e:
        say(str(e))
        return 1
    finally:
        lock.release()


def _run(country_id, data_dir, folder, processes, bands, max_tiles, redo, yes, say) -> int:
    import search
    from progress import progress
    say(f"=== country run {country_id} ({_now()}) ===")
    state, country = setup(country_id, folder, data_dir, redo, say)
    names = [b.name for b in country.bands]
    selected = list(bands) if bands else names
    for name in selected:
        country.band(name)
    plans = {b.name: band_plan(country, b, folder, data_dir) for b in country.bands}
    _finish_state(state, folder, plans)
    manifest = Manifest(folder)
    try:
        largest = 0
        for band in country.bands:
            tiles = search.fixed_tiles(plans[band.name], band.core_m)
            manifest.add_tiles(band.name, tiles)
            if band.name in selected and tiles:
                largest = max(largest, max(t.grid.width * t.grid.height for t in tiles))
        stale = manifest.release_running()
        if stale:
            say(f"{stale} tiles of an interrupted run are pending again")
        weights = _weights(manifest, selected)
        if weights:
            manifest.set_weights(weights)
            say(f"The heaviest tiles first: {sum(w > 0 for w in weights.values())} of {len(weights)} pending tiles "
                f"lie under the lines of the tiles done already")
        shutil.rmtree(os.path.join(data_dir, "work", f"country-{country.id}"), ignore_errors=True)
        counts = manifest.counts()
        todo = sum(counts.get(b, {}).get("pending", 0) for b in selected)
        k, per = worker_count(largest)
        if processes is not None:
            k = processes
        elif max_tiles is not None or todo:
            k = max(1, min(k, todo, max_tiles if max_tiles is not None else todo))
        k_eff = max(1, k)  # the processes counting at once (0: this one)
        need = k_eff * largest * DISK_PIXEL_BYTES + DISK_SPARE
        free = shutil.disk_usage(data_dir).free
        for band in country.bands:
            c = counts.get(band.name, {})
            say(f"Band {band.name} {band.lengths[0]:g}-{band.lengths[1]:g} m at {band.resolution:g} m "
                f"({band.model}, {band.slope_threshold:g}°, cores of {band.core_m:g} m"
                f"{'' if band.layer else ', control'}): {sum(c.values())} tiles, {c.get('done', 0)} done, "
                f"{c.get('pending', 0)} pending, {c.get('failed', 0)} failed")
        say(f"Selected bands: {', '.join(selected)}; {todo} tiles to count"
            + (f" (at most {max_tiles} now)" if max_tiles is not None else "")
            + (f"; {k} worker processes, about {per / 2 ** 30:.1f} GiB of memory each" if k else
               "; in this process"))
        if todo and free < need:
            say(f"Not enough free disk in {data_dir}: {free / 2 ** 30:.1f} GiB, the work folders need about "
                f"{need / 2 ** 30:.1f} GiB. Free some, or use fewer --processes.")
            return 1
        if todo and not yes and not _ask("Start? [y/N] "):
            say("Not started (--yes skips this question)")
            return 1
        started = time.time()
        if todo:
            with progress.bars():
                _prefetch({n: plans[n] for n in selected}, say)
                if k:
                    _warm_up(country, {n: plans[n] for n in selected}, folder, data_dir, say)
            manifest.set_run(selected, max_tiles, k_eff)
            code = (_run_workers(country_id, data_dir, folder, manifest, k, selected, say, started) if k
                    else _run_here(folder, data_dir, manifest, say))
            if code:
                return code
            say(_progress_line(manifest, selected, k_eff, started))
        return _after(country, data_dir, manifest, selected, say)
    finally:
        manifest.close()


def _run_here(folder: str, data_dir: str, manifest: Manifest, say) -> int:
    """--processes 0: the tiles counted in this process."""
    from progress import progress
    work = TileWork(folder, data_dir, 0)
    try:
        with progress.bars():
            work.loop(manifest)
    except KeyboardInterrupt:
        n = manifest.release_running()
        say(f"Stopped: {n} tiles being counted are pending again")
        return 130
    return 0


def _disk_counters() -> Tuple[int, int]:
    """Bytes read and written by the machine's disks so far."""
    try:
        disk = psutil.disk_io_counters()
        return (int(disk.read_bytes), int(disk.write_bytes)) if disk else (0, 0)
    except (psutil.Error, RuntimeError):
        return 0, 0


class _RunSamples:
    """A run's timeline: logs/samples-<start>.csv, a row every RUN_SAMPLE_SECONDS (and at the start
    and the end) with the machine's CPU % and memory, the workers' cores (their CPU seconds over
    the interval), working set and private bytes (_private), each of a worker's process tree (a
    venv's python.exe on Windows runs the interpreter as its child), the tiles being counted, and
    the disks' read and write MB/s. `country profile` sums up the last one."""

    COLUMNS = ("time", "seconds", "machine_cpu_pct", "ram_used_gib", "ram_available_gib", "workers",
               "workers_cores", "workers_rss_gib", "workers_private_gib", "running_tiles", "disk_read_mbs",
               "disk_write_mbs")

    def __init__(self, folder: str):
        self.path = os.path.join(folder, "logs", f"samples-{datetime.now():%Y%m%d-%H%M%S}.csv")
        self.started = self.last = time.monotonic()
        psutil.cpu_percent(None)  # the first call only starts the interval
        self.disk = _disk_counters()
        self.cpu: Dict[Tuple[int, float], float] = {}
        with open(self.path, "w", encoding="utf-8") as f:
            f.write(",".join(self.COLUMNS) + "\n")

    def sample(self, pids: Sequence[int], manifest: Manifest):
        now = time.monotonic()
        interval = max(now - self.last, 1e-6)
        alive, cores, rss, private = 0, 0.0, 0, 0
        for pid in pids:
            try:
                worker = psutil.Process(pid)
                tree = [worker] + worker.children(recursive=True)
            except psutil.Error:
                continue
            alive += 1
            for process in tree:
                try:
                    key = (process.pid, process.create_time())
                    times, memory = process.cpu_times(), process.memory_info()
                except psutil.Error:
                    continue
                cpu = times.user + times.system
                cores += (cpu - self.cpu.get(key, cpu)) / interval  # nothing before a process's first sample
                self.cpu[key] = cpu
                rss, private = rss + int(memory.rss), private + _private(memory)
        disk, ram = _disk_counters(), psutil.virtual_memory()
        try:
            running = manifest.db.execute("SELECT COUNT(*) FROM tiles WHERE status = 'running'").fetchone()[0]
        except sqlite3.Error:
            running = ""
        row = (datetime.now().isoformat(timespec="seconds"), f"{now - self.started:.1f}",
               f"{psutil.cpu_percent(None):.1f}", f"{ram.used / 2 ** 30:.2f}", f"{ram.available / 2 ** 30:.2f}",
               alive, f"{cores:.2f}", f"{rss / 2 ** 30:.2f}", f"{private / 2 ** 30:.2f}", running,
               f"{(disk[0] - self.disk[0]) / interval / 1e6:.1f}", f"{(disk[1] - self.disk[1]) / interval / 1e6:.1f}")
        self.disk, self.last = disk, now
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(",".join(map(str, row)) + "\n")


def _run_workers(country_id, data_dir, folder, manifest: Manifest, k: int, selected, say, started) -> int:
    """K worker processes until none is left; a progress line every PROGRESS_SECONDS, a row of the
    run's timeline every RUN_SAMPLE_SECONDS; on Ctrl+C the workers killed (jobs.kill_tree) and
    their tiles pending again."""
    import jobs
    procs = {slot: _worker_process(country_id, data_dir, folder, slot) for slot in range(k)}
    samples = _RunSamples(folder)
    say(f"Started {k} workers (logs in {os.path.join(folder, 'logs')}, the timeline in "
        f"{os.path.basename(samples.path)})")
    samples.sample([p.pid for p in procs.values()], manifest)
    respawns, last, sampled = 0, time.time(), time.time()
    try:
        while procs:
            time.sleep(1)
            if time.time() - sampled >= RUN_SAMPLE_SECONDS:
                sampled = time.time()
                samples.sample([p.pid for p in procs.values()], manifest)
            for slot, proc in list(procs.items()):
                code = proc.poll()
                if code is None:
                    continue
                del procs[slot]
                if code == 0:
                    continue
                n = manifest.fail(None, None, f"worker {slot} stopped with exit code {code}", worker=f"slot-{slot}")
                say(f"Worker {slot} stopped with exit code {code} ({n} tiles back to pending or failed; "
                    f"see logs/worker-{slot}.log)")
                marks = ",".join("?" * len(selected))
                pending = manifest.db.execute(f"SELECT COUNT(*) FROM tiles WHERE status = 'pending' "
                                              f"AND band IN ({marks})", list(selected)).fetchone()[0]
                if pending and respawns < RESPAWNS_PER_WORKER * k:
                    respawns += 1
                    procs[slot] = _worker_process(country_id, data_dir, folder, slot)
            if time.time() - last >= PROGRESS_SECONDS:
                last = time.time()
                say(_progress_line(manifest, selected, k, started))
    except KeyboardInterrupt:
        for proc in procs.values():
            jobs.kill_tree(proc.pid)
        n = manifest.release_running()
        say(f"Stopped: the workers were stopped, {n} tiles being counted are pending again")
        return 130
    samples.sample([], manifest)  # the end
    return 0


def _after(country: Country, data_dir: str, manifest: Manifest, selected, say) -> int:
    """The end of a run: the cube when every layer band is done, else what is left."""
    counts = manifest.counts()
    failed = sum(counts.get(b, {}).get("failed", 0) for b in selected)
    layer = [b.name for b in country.bands if b.layer]
    missing = sum(n for b in layer for status, n in counts.get(b, {}).items() if status != "done")
    if failed:
        say(f"{failed} tiles failed (see `findaline.py country status {country.id}`); "
            f"`country build {country.id} --partial` builds the cube without them")
        return 1
    if missing:
        say(f"{missing} tiles of the layer bands are left: run again to go on")
        return 0
    if not all(counts.get(b) for b in layer):
        say("The layer bands have no tiles: nothing to build")
        return 1
    return build(country.id, data_dir, say=say)


# --- status, build, compare ----------------------------------------------------------------------

def status(country_id: str, data_dir: str) -> int:
    folder = folder_of(data_dir, country_id)
    state = read_state(folder)
    country = Country.from_config(state["config"])
    manifest = Manifest(folder)
    try:
        print(f"{country.name} ({country.id}): config {state.get('hash', '?')[:12]}, origin {state.get('origin')}, "
              f"{state.get('crs', '?')}")
        header = f"{'Band':<5} {'Tiles':>6} {'Done':>6} {'Run':>4} {'Pend':>6} {'Fail':>5} {'Lines':>14} " \
                 f"{'Spots':>12} {'Seconds':>10} {'Median s':>9}"
        print(header)
        errors = []
        for band in country.bands:
            rows = manifest.rows(band.name)
            by = {}
            for r in rows:
                by[r["status"]] = by.get(r["status"], 0) + 1
            done = [r for r in rows if r["status"] == "done"]
            secs = [r["seconds"] or 0.0 for r in done]
            print(f"{band.name:<5} {len(rows):>6} {by.get('done', 0):>6} {by.get('running', 0):>4} "
                  f"{by.get('pending', 0):>6} {by.get('failed', 0):>5} {sum(r['lines'] or 0 for r in done):>14,} "
                  f"{sum(r['spots'] or 0 for r in done):>12,} {sum(secs):>10.0f} "
                  f"{(float(np.median(secs)) if secs else 0.0):>9.1f}")
            errors += [r for r in rows if r["error"]]
        if errors:
            print("Errors:")
            for r in errors:
                print(f"  {r['band']} {r['name']} ({r['status']}, {r['attempts']} attempts): {r['error']}")
        cube = os.path.join(folder, "cube", "cube.json")
        if os.path.exists(cube):
            with open(cube, encoding="utf-8") as f:
                info = json.load(f)
            totals = info.get("totals", {})
            print(f"Cube built {info.get('built')}" + (" (partial)" if info.get("partial") else "")
                  + f": {totals.get('lines', 0):,} lines, {totals.get('spots', 0):,} spots")
    finally:
        manifest.close()
    return 0


def _quantiles(values) -> str:
    values = np.asarray(values, dtype=np.float64)
    return f"median {np.median(values):.2f}, p90 {np.percentile(values, 90):.2f}, max {values.max():.2f}"


def profile(country_id: str, data_dir: str) -> int:
    """`country profile`: where the time and the memory of the counted tiles went, per band and
    stage (the tiles' meta: stages, sink, cpu_seconds, memory, io, threads), and the sums of the
    last run's timeline (logs/samples-*.csv)."""
    from collections import Counter
    folder = folder_of(data_dir, country_id)
    country = Country.from_config(read_state(folder)["config"])
    gib = 2 ** 30
    for band in country.bands:
        paths = sorted(glob.glob(os.path.join(folder, "tiles", band.name, "*.npz")))
        if not paths:
            continue
        metas = [_tile_meta(p) for p in paths]
        walls = np.array([m["seconds"]["prepare"] + m["seconds"]["count"] for m in metas])
        print(f"Band {band.name}: {len(metas)} tiles, {walls.sum() / 3600:.2f} h of tile time; seconds per tile "
              f"{_quantiles(walls)}")
        profiled = [m for m in metas if "stages" in m]
        if len(profiled) < len(metas):
            print(f"  {len(metas) - len(profiled)} tiles counted before their stages were measured")
        if not profiled:
            continue
        stages: Dict[str, List[float]] = {}
        for m in profiled:
            for name, (seconds, cpu) in m["stages"].items():
                total = stages.setdefault(name, [0.0, 0.0])
                total[0] += seconds
                total[1] += cpu
        whole = sum(seconds for seconds, _ in stages.values()) or 1.0
        print(f"  {'Stage':<48} {'Hours':>7} {'Share':>6} {'Cores':>6}")
        for name, (seconds, cpu) in sorted(stages.items(), key=lambda item: -item[1][0]):
            print(f"  {name[:48]:<48} {seconds / 3600:>7.2f} {seconds / whole:>6.1%} "
                  f"{cpu / seconds if seconds else 0.0:>6.2f}")
        sink = np.array([m["sink"] for m in profiled], dtype=np.float64)
        print(f"  the counter (in 'anchor pairs' and after it): {sink[:, 0].sum() / 3600:.2f} h, "
              f"{sink[:, 0].sum() / whole:.1%} of the time")
        claimed = Counter(m["threads"] for m in profiled)
        most = Counter(m.get("threads_max", m["threads"]) for m in profiled)
        print(f"  cores of a tile on average {sum(m['cpu_seconds'] for m in profiled) / whole:.2f}; threads claimed "
              f"{dict(sorted(claimed.items()))}, at most {dict(sorted(most.items()))}")
        print(f"  memory of a tile (GiB): private {_quantiles([m['memory']['private'] / gib for m in profiled])}; "
              f"working set {_quantiles([m['memory']['rss'] / gib for m in profiled])}")
        print(f"  file reads of a tile (MB) {_quantiles([m['io']['read'] / 1e6 for m in profiled])}; "
              f"writes {_quantiles([m['io']['write'] / 1e6 for m in profiled])}")
    timelines = sorted(glob.glob(os.path.join(folder, "logs", "samples-*.csv")))
    if timelines:
        _profile_timeline(timelines[-1])
    return 0


def _profile_timeline(path: str):
    """The sums of a run's timeline (_RunSamples)."""
    import csv
    with open(path, encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r["running_tiles"] != ""]
    if len(rows) < 2:
        return

    def column(key):
        return np.array([float(r[key]) for r in rows])

    workers, running, cores = column("workers"), column("running_tiles"), column("workers_cores")
    busy = workers.max()
    print(f"The last run's timeline ({os.path.basename(path)}): {column('seconds')[-1] / 60:.1f} min, "
          f"{busy:.0f} workers; machine CPU {column('machine_cpu_pct').mean():.0f} % on average; the workers' cores "
          f"{cores.mean():.1f} on average, {cores.max():.1f} at most; memory used up to "
          f"{column('ram_used_gib').max():.1f} GiB (the workers' private bytes up to "
          f"{column('workers_private_gib').max():.1f} GiB); fewer tiles than workers {np.mean(running < busy):.0%} "
          f"of the time; disks {column('disk_read_mbs').mean():.0f} MB/s read and "
          f"{column('disk_write_mbs').mean():.0f} MB/s written on average (at most {column('disk_read_mbs').max():.0f} "
          f"and {column('disk_write_mbs').max():.0f})")


def _tile_meta(path: str) -> Dict:
    """A tile file's meta only (an .npz member is read when asked for); ValueError for another VERSION."""
    with np.load(path, allow_pickle=False) as z:
        version = int(z["version"]) if "version" in z.files else None
        if version != countcube.VERSION:
            raise ValueError(f"{path}: a tile file of version {version}, not {countcube.VERSION}: count it again")
        return json.loads(str(z["meta"]))


def _credits(metas: List[Dict], area_spec: str, year: int) -> List[Dict]:
    """The credits of the data the tiles used: merged per layer as search._merged_data does, years
    filled, each once (search._credits), and OSM for an outline from OpenStreetMap."""
    import search
    import sources as src
    saved = list(src.used_data)
    try:
        src.used_data[:] = [entry for meta in metas for entry in meta.get("data") or []]
        merged = search._merged_data()
    finally:
        src.used_data[:] = saved
    credits = [entry["credit"] for entry in search._dated_data(merged, year) if entry.get("credit")]
    if area_spec.startswith("osm:"):
        credits.append(src.OSM_CREDIT.as_dict())
    unique: Dict[str, Dict] = {}
    for credit in credits:
        unique.setdefault(json.dumps(credit, sort_keys=True), credit)
    return list(unique.values())


def build(country_id: str, data_dir: str, partial: bool = False, say=print) -> int:
    """`country build`: the cube of the layer bands' tiles (countcube.build). Refused while tiles are
    missing unless partial; every tile must have the country's origin and config."""
    folder = folder_of(data_dir, country_id)
    state = read_state(folder)
    country = Country.from_config(state["config"])
    if "origin" not in state:
        say(f"{country_id} has no tiles yet: `findaline.py country run {country_id}`")
        return 1
    manifest = Manifest(folder)
    try:
        rows = {b.name: manifest.rows(b.name) for b in country.bands}
    finally:
        manifest.close()
    paths, metas, missing, total = [], [], 0, 0
    bands_info = []
    for band in country.bands:
        done = 0
        seconds = 0.0
        for r in rows[band.name]:
            path = os.path.join(folder, "tiles", band.name, f"{r['name']}.npz")
            if r["status"] == "done" and os.path.exists(path):
                done += 1
                seconds += r["seconds"] or 0.0
                if band.layer:
                    paths.append(path)
        if band.layer:
            total += len(rows[band.name])
            missing += len(rows[band.name]) - done
        bands_info.append({"name": band.name, "lengths": list(band.lengths), "resolution": band.resolution,
                           "model": band.model, "slope_threshold": band.slope_threshold, "core_m": band.core_m,
                           "layer": band.layer, "tiles": len(rows[band.name]), "done": done,
                           "seconds": round(seconds, 1), "params": form_params(country, band)})
    if not total:
        say(f"{country_id}: the layer bands have no tiles yet")
        return 1
    if missing and not partial:
        say(f"{missing} of the {total} tiles of the layer bands are not done: run `findaline.py country run "
            f"{country_id}`, or build a partial cube with --partial")
        return 1
    origin = [float(v) for v in state["origin"]]
    for path in paths:
        try:
            meta = _tile_meta(path)
        except ValueError as e:
            say(str(e))
            return 1
        if meta.get("config") != state["hash"] or [float(v) for v in meta.get("origin", [])] != origin:
            say(f"{path} was counted with another configuration or origin: count it again "
                f"(`country run {country_id} --redo` counts everything again)")
            return 1
        metas.append(meta)
    year = datetime.now().year
    dsm = country.options.get("nmpt", "off") != "off"
    notes = [f"Only lines with both anchors inside {country.name} are counted."]
    if not dsm:
        notes.append("The surface model (trees, buildings) was not used: every line counts as not over trees "
                     "or buildings.")
    if missing:
        notes.append(f"Partial: {total - missing} of {total} tiles of the layer bands.")
    info = {"id": country.id, "name": country.name, "crs": state["crs"], "origin": origin,
            "bounds_wgs84": state["bounds_wgs84"], "bands": bands_info, "dsm": dsm,
            "water": country.options.get("water") == "fill", "partial": bool(missing), "config": state["hash"],
            "credits": _credits(metas, country.area, year), "notes": notes}
    out = os.path.join(folder, "cube")
    os.makedirs(out, exist_ok=True)
    with cache.replacing(os.path.join(out, "area.geojson")) as f, \
            open(os.path.join(folder, "area.geojson"), "rb") as source:
        shutil.copyfileobj(source, f)
    cube = countcube.build(paths, out, info)
    say(f"Cube of {country.name} built in {out}" + (" (partial)" if missing else "")
        + f": {cube['totals']['lines']:,} lines, {cube['totals']['spots']:,} spots")
    return 0


def _band_counts(folder: str, rows, band: str, mask: Optional[int]):
    """The line keys and spots of a band's done tiles, the lines and spots of the length bins of
    mask only (None: all)."""
    lines, spots = countcube._Reducer(countcube.sum_keys), countcube._Reducer(countcube.merge_spots)
    for r in rows:
        if r["status"] != "done":
            continue
        counts, _ = countcube.load_tile(os.path.join(folder, "tiles", band, f"{r['name']}.npz"))
        lines.add(counts.line_keys, counts.line_counts)
        spots.add(counts.spot_ids, counts.spot_records)
    keys, n = lines.flush()
    ids, records = spots.flush()
    if mask is not None:
        keep = ((keys >> countcube.LENGTH_SHIFT) & mask) != 0
        keys, n = keys[keep], n[keep]
        keep = ((records >> countcube.LENGTH_SHIFT) & mask) != 0
        ids = ids[keep]
    return keys, n, ids


def _per_cell(keys, n, ids, level: int) -> Tuple[Dict[int, int], Dict[int, int]]:
    """Lines and spots per cell of a level: {cell: count} with cell = i << 14 | j."""
    i = (keys >> countcube.COL_SHIFT) // level
    j = ((keys >> countcube.ROW_SHIFT) & countcube.CELL_MASK) // level
    cells, counts = countcube.sum_keys((i << countcube.CELL_BITS) | j, n)
    si, sj = countcube.spot_cells(ids)
    spot_cells, spot_counts = countcube.count_keys(((si // level) << countcube.CELL_BITS) | (sj // level))
    return dict(zip(cells.tolist(), counts.tolist())), dict(zip(spot_cells.tolist(), spot_counts.tolist()))


def compare(country_id: str, data_dir: str, control: str = "M2", against: str = "L") -> int:
    """`country compare`: the control band against its lengths' part of the other band, per cell of
    1 and 4 km (lines, spots, their ratio, the Spearman correlation of spots per cell over the cells
    with a line of either, zeros included, and "lost": the share of the control's cells with a spot
    where the other has none), with the seconds of both bands' tiles; compare.json."""
    from scipy.stats import spearmanr
    folder = folder_of(data_dir, country_id)
    state = read_state(folder)
    country = Country.from_config(state["config"])
    c_band, a_band = country.band(control), country.band(against)
    lo, hi = c_band.lengths
    try:
        mask = countcube.Filters(length=(lo, hi)).length_mask()
    except ValueError as e:
        print(f"The control band's lengths {lo:g}-{hi:g} m are not on the cube's length edges: {e}")
        return 1
    manifest = Manifest(folder)
    try:
        c_rows, a_rows = manifest.rows(control), manifest.rows(against)
    finally:
        manifest.close()
    for band, rows in ((control, c_rows), (against, a_rows)):
        done = sum(r["status"] == "done" for r in rows)
        if done < len(rows):
            print(f"Note: {done} of {len(rows)} tiles of {band} are done; the comparison covers those")
    c_keys, c_n, c_ids = _band_counts(folder, c_rows, control, None)
    a_keys, a_n, a_ids = _band_counts(folder, a_rows, against, mask)
    c_lines, a_lines = int(c_n.sum()), int(a_n.sum())
    result = {"control": control, "against": against, "lengths": [lo, hi],
              "lines": {"control": c_lines, "against": a_lines, "ratio": a_lines / c_lines if c_lines else None},
              "spots": {"control": int(len(c_ids)), "against": int(len(a_ids)),
                        "ratio": len(a_ids) / len(c_ids) if len(c_ids) else None},
              "seconds": {"control": round(sum(r["seconds"] or 0.0 for r in c_rows if r["status"] == "done"), 1),
                          "against": round(sum(r["seconds"] or 0.0 for r in a_rows if r["status"] == "done"), 1)},
              "tiles": {"control": sum(r["status"] == "done" for r in c_rows),
                        "against": sum(r["status"] == "done" for r in a_rows)},
              "cells": {}}
    for level in (1, 4):
        c_cells_lines, c_cells_spots = _per_cell(c_keys, c_n, c_ids, level)
        a_cells_lines, a_cells_spots = _per_cell(a_keys, a_n, a_ids, level)
        cells = sorted(set(c_cells_lines) | set(a_cells_lines))
        x = np.array([c_cells_spots.get(c, 0) for c in cells], dtype=float)
        y = np.array([a_cells_spots.get(c, 0) for c in cells], dtype=float)
        rho = None
        if len(cells) > 1 and x.std() > 0 and y.std() > 0:
            rho = float(spearmanr(x, y)[0])
        with_spot = [c for c in cells if c_cells_spots.get(c, 0)]
        lost = sum(1 for c in with_spot if not a_cells_spots.get(c, 0))
        result["cells"][str(level)] = {
            "km": level * countcube.CELL_M / 1000, "cells": len(cells),
            "control_cells": sum(1 for c in cells if c_cells_lines.get(c, 0)),
            "against_cells": sum(1 for c in cells if a_cells_lines.get(c, 0)),
            "spearman_spots": rho, "lost": lost / len(with_spot) if with_spot else None}
    _write_json(os.path.join(folder, "compare.json"), result)

    def ratio(v):
        return "-" if v is None else f"{v:.3f}"

    print(f"{country.name}: {control} ({c_band.resolution:g} m) against {against} ({a_band.resolution:g} m), "
          f"lengths {lo:g}-{hi:g} m")
    print(f"{'':<14} {control:>14} {against:>14} {'ratio':>8}")
    print(f"{'lines':<14} {c_lines:>14,} {a_lines:>14,} {ratio(result['lines']['ratio']):>8}")
    print(f"{'spots':<14} {len(c_ids):>14,} {len(a_ids):>14,} {ratio(result['spots']['ratio']):>8}")
    print(f"{'seconds':<14} {result['seconds']['control']:>14,.0f} {result['seconds']['against']:>14,.0f}")
    print(f"{'Cell':<6} {'cells':>8} {'Spearman':>9} {'lost':>7}")
    for level, row in result["cells"].items():
        print(f"{row['km']:>4g} km {row['cells']:>8} {ratio(row['spearman_spots']):>9} {ratio(row['lost']):>7}")
    print(f"Saved to {os.path.join(folder, 'compare.json')}")
    return 0


# --- the command line ----------------------------------------------------------------------------

def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(prog="findaline.py country",
                                     description="The country layer: a whole country searched in fixed tiles "
                                                 "that keep only counts, summed into a cube for the app's map.")
    commands = parser.add_subparsers(dest="command", required=True)
    r = commands.add_parser("run", help="count the tiles still pending (resumable), then build the cube")
    r.add_argument("--processes", type=int, help="worker processes (default: as many as the memory and the "
                                                 "physical cores allow; 0: in this process)")
    r.add_argument("--bands", help="only these bands, e.g. S,M (default: all)")
    r.add_argument("--max-tiles", type=int, help="start at most this many tiles in this run")
    r.add_argument("--redo", action="store_true", help="remove the tiles, the cube and the manifest and count "
                                                       "everything again (needed after a change of the configuration)")
    r.add_argument("--yes", action="store_true", help="do not ask before starting")
    commands.add_parser("status", help="the tiles of each band by status, lines, spots, seconds, errors")
    commands.add_parser("profile", help="where the time and the memory of the counted tiles went, per band and "
                                        "stage, and the last run's timeline")
    b = commands.add_parser("build", help="the cube of the layer bands' tiles")
    b.add_argument("--partial", action="store_true", help="build while tiles are missing")
    c = commands.add_parser("compare", help="a control band against the same lengths of another band")
    c.add_argument("--control", default="M2", help="the control band (default M2)")
    c.add_argument("--against", default="L", help="the band it is compared with (default L)")
    w = commands.add_parser("worker", help="a worker process of a run (started by run)")
    w.add_argument("--slot", type=int, required=True, help="the worker's number")
    for sub in commands.choices.values():
        sub.add_argument("id", help=f"the country ({', '.join(sorted(COUNTRIES))})")
        sub.add_argument("--data-dir", help="data folder (default: FINDALINE_DATA or the folder of the scripts)")
    args = parser.parse_args(argv)
    data_dir = cache.data_dir(args.data_dir)
    try:
        if args.command == "run":
            if args.processes is not None and args.processes < 0:
                parser.error("--processes must be 0 or more")
            bands = [s.strip() for s in args.bands.split(",") if s.strip()] if args.bands else None
            return run(args.id, data_dir, args.processes, bands, args.max_tiles, args.redo, args.yes)
        if args.command == "status":
            return status(args.id, data_dir)
        if args.command == "profile":
            return profile(args.id, data_dir)
        if args.command == "build":
            return build(args.id, data_dir, args.partial)
        if args.command == "compare":
            return compare(args.id, data_dir, args.control, args.against)
        return worker(args.id, data_dir, args.slot)
    except CountryError as e:
        print(e)
        return 1
