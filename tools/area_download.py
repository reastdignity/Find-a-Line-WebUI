"""
Downloads the elevation models of a whole area into the cache of a data folder and does nothing else: no search,
no tiles counted, no weights (`findaline.py country run` does those, and finds the data cached). For a download of
days or weeks, so it survives what happens in that time, and can be followed.

- A supervisor (`run`) starts one pass after another, each a process of its own: what a process keeps (an index
  that could not be reached is remembered as None by sources.indexes.cached.CachedIndex.tiles, which would skip the
  whole layer) ends with it. A pass that did not finish is followed by another after RETRY_SECONDS, and what is
  cached stays: restarting costs the listing only.
- A pass downloads the source's layers and, where the catalogue names one (Source.instead_without_data: alaska and
  alaska_ifsar), the stand-in's too. The window layers' groups hold the same pixels whatever the files' resolution
  (country.PREFETCH_GROUP_M at 1 m, half that for 0.5 m files), and a pass over --max-memory-gb (a quarter of the
  machine's memory unless given) ends with EXIT_RESTART and is started again at once (counted as `restarts`).
- A tile that fails does not stop the others (sources.download_layers(on_error=)). FAILURES_IN_A_ROW failed tasks with
  no tile between them end the pass (the service or the disk is away), and so does a disk with less than --min-free-gb.
- "Needs attention" (the supervisor's exit 2): the same tiles failing in ATTENTION_PASSES passes in a row (in
  <name>.failed.json: everything else is downloaded by then), a pass giving up with the same message that often (a
  key missing, an index out of reach), a crash ending on the same last line of the log, or an area without data
  (EXIT_NOTHING: no tile under the outline, or every tile without data). At its end a pass counts the tiles the service
  has no data for (the sea), so "done" says what it has.

The state goes to --state-dir: <name>.state.json every STATE_SECONDS (with the pass's memory now and at its peak),
<name>.history.csv (seconds, tiles, MB, memory GB) and status.html (one page for every area of the folder, for a browser
from disk) every HISTORY_SECONDS, <name>.log (the passes' output).

    uv run tools/area_download.py run poland --area osm:Polska --source geoportal --resolution 1 \\
        --data-dir <data> --state-dir <state> --host-slots opendata.geoportal.gov.pl=2
    uv run tools/area_download.py status --state-dir <state> --watch 30
    uv run tools/area_download.py stop poland --state-dir <state>     # `run` again resumes
    uv run --group tui tools/area_download.py tui --settings <file>   # the window: tools/area_download_tui.py

The requests go out as those of a search (cache.http_headers); FINDALINE_CONTACT in the environment adds a contact,
and a pass without one warns in its log and its state until its first tile.
"""

import argparse
import contextlib
import csv
import dataclasses
import glob
import html
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional, Sequence, Tuple

import psutil
from filelock import FileLock, Timeout

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

import cache  # noqa: E402

EXIT_DONE = 0      # a pass with nothing left to download
EXIT_FAILED = 3    # a pass to its end, with tiles that failed (<name>.failed.json)
EXIT_STOPPED = 4   # a pass that gave up: the plan, the index could not be reached, the failures in a row, the disk
EXIT_RESTART = 5   # a pass over its memory budget: the supervisor starts the next one at once
EXIT_NOTHING = 6   # an area without data: no tile under the outline, or every tile without data (needs attention)
RETRY_SECONDS = 600
POLL_SECONDS = 2
STATE_SECONDS = 10
HISTORY_SECONDS = 60
PROGRESS_SECONDS = 60       # between the progress lines of the log (progress.TEXT_INTERVAL)
FAILURES_IN_A_ROW = 50
ATTENTION_PASSES = 3
FREE_GB_MIN = 50
SPEED_ROWS = 10             # rows of the history the speed is taken over: about ten minutes
ETA_ROWS = 360              # ... and the time left: six hours, a day's rhythm of a service shows less
STALE_SECONDS = 180         # a state older than this, with its area not finished, is called stale
REPLACE_ATTEMPTS = 5
CHART_POINTS = 120
PART_AGE_SECONDS = 86400    # .part files of killed passes are removed at the end, older than this
GDAL_CACHEMAX_MB = 512      # GDAL's block cache of a pass (supervise), unless the environment sets GDAL_CACHEMAX
LOG_TAIL_BYTES = 65536      # what the supervisor reads of the log for a crashed pass's last line
FINISHED = ("done", "stopped", "needs attention")
NO_CONTACT = "no contact in the User-Agent: set the contact in the settings or export FINDALINE_CONTACT"


@dataclass(frozen=True)
class Area:
    """What is downloaded, as given to `run`."""
    name: str
    area: str         # an area spec: osm:<name>, or a GeoJSON file
    source: str
    resolution: float
    data_dir: str
    state_dir: str
    host_slots: Tuple[Tuple[str, int], ...] = ()
    min_free_gb: float = FREE_GB_MIN
    max_memory_gb: float = 0.0   # a pass over it is started again (EXIT_RESTART); 0: no budget

    def file(self, suffix: str) -> str:
        return state_file(self.state_dir, self.name, suffix)


def state_file(state_dir: str, name: str, suffix: str) -> str:
    return os.path.join(state_dir, name + suffix)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _seconds(text: str) -> float:
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()


def read_state(state_dir: str, name: str) -> Dict:
    """<name>.state.json, {} without one."""
    try:
        with open(state_file(state_dir, name, ".state.json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def write_state(state_dir: str, name: str, state: Dict):
    """<name>.state.json. Windows refuses to replace a file that `status` is reading just then: tried again, and
    left for the next round when that does not help (a state is only reported)."""
    state["updated"] = _now()
    for attempt in range(REPLACE_ATTEMPTS):
        try:
            with cache.replacing(state_file(state_dir, name, ".state.json"), "w", encoding="utf-8") as f:
                json.dump(state, f, indent=1, ensure_ascii=False)
            return
        except PermissionError:
            time.sleep(0.1 * (attempt + 1))


def memory_gb() -> float:
    """The resident memory of this process in GB: what the budget of a pass is measured on."""
    return psutil.Process().memory_info().rss / 1e9


def default_max_memory_gb() -> float:
    """A quarter of the machine's memory: several areas download at once, and GDAL's cache comes on top."""
    return round(psutil.virtual_memory().total / 4e9, 1)


def read_history(state_dir: str, name: str) -> List[Tuple[float, float, float]]:
    """(seconds, tiles done, MB) of <name>.history.csv; its fourth column (the pass's memory in GB, since
    2026-11-08) is for reading by hand, and rows without it are read as before."""
    rows = []
    try:
        with open(state_file(state_dir, name, ".history.csv"), encoding="utf-8", newline="") as f:
            for row in csv.reader(f):
                with contextlib.suppress(ValueError, IndexError):  # a line cut short by a kill
                    rows.append((float(row[0]), float(row[1]), float(row[2])))
    except OSError:
        pass
    return rows


# --- a pass ------------------------------------------------------------------------------------------------------

class Stop(Exception):
    """The pass cannot go on for now: the text says why, `code` how it ends (EXIT_STOPPED; EXIT_RESTART for a pass
    over its memory budget, started again at once; EXIT_NOTHING for an area without data)."""

    def __init__(self, text: str, code: int = EXIT_STOPPED):
        super().__init__(text)
        self.code = code


class Failures:
    """sources.download_layers' on_error: the tiles that failed, the pass stopped at too many in a row."""

    def __init__(self, cache_dir: str):
        self.cache_dir = cache_dir
        self.tiles: Dict[str, str] = {}  # path in the cache: the error
        self.in_a_row = 0

    def __call__(self, layer, tiles: Sequence, error: Exception):
        text = cache.clean_error(error)
        print(f"FAILED {len(tiles)} tile(s) of {layer.description}: {text}", flush=True)
        for tile in tiles:
            self.tiles[cache.relative(self.cache_dir, layer.tile_path(self.cache_dir, tile))] = text
        self.in_a_row += 1  # a task: a square of blocks fails as one
        if self.in_a_row >= FAILURES_IN_A_ROW:
            raise Stop(f"{self.in_a_row} failures in a row, the last: {text}")


class Reporter:
    """The state of a pass: the listener of the progress bars (the tiles, the MB) and a thread writing it down
    while nothing else happens, as during the listing of a big index."""

    def __init__(self, area: Area, number: int, plans: Sequence, failures: Failures, clock=time.time):
        self.area, self.plans, self.failures, self.clock = area, list(plans), failures, clock
        before = read_state(area.state_dir, area.name)
        self.mb_before = before.get("mb", 0.0) if before.get("source") == area.source else 0.0
        self.tiles_total = self.tiles_cached = self.mb_pass = self.tiles_pass = 0
        self.tiles_offset, self.mb_offset = 0, 0.0   # the tiles and MB of the plans downloaded before this one
        self.free_gb: Optional[float] = None
        self.memory_gb = self.memory_peak_gb = 0.0
        self.over_budget = False   # set by the beat, turned into a Stop by the next tile
        self.state = {"name": area.name, "area": area.area, "source": area.source, "resolution": area.resolution,
                      "stage": "listing", "pass": number, "pid": os.getpid(), "started": _now(), "message": "",
                      "tiles_done": 0, "tiles_total": 0, "failed": 0, "mb": self.mb_before,
                      "restarts": before.get("restarts", 0), "memory_gb": 0.0, "memory_peak_gb": 0.0,
                      "tiles_missing": 0}
        self.next_minute = 0.0  # the free space and status.html
        # the history's next row: its own timer, so a listing's beats (no tiles_total yet) do not spend the first
        # row's minute (it was written up to HISTORY_SECONDS after the listing, or never in a short pass)
        self.next_row = 0.0
        self._indexes: Optional[List[Tuple[str, set]]] = None   # _index_folders, once
        self.lock = threading.Lock()  # the thread and the end of the pass both write
        self.quit = threading.Event()
        self.thread = threading.Thread(target=self._beat, daemon=True)

    def __enter__(self):
        self.sample_memory()
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.quit.set()
        self.thread.join()

    def _beat(self):
        while not self.quit.wait(STATE_SECONDS):
            self.sample_memory()
            try:
                self.write()
            except OSError as e:  # the next round tries again
                print(f"The state was not written: {e}", flush=True)

    def sample_memory(self):
        """The process's memory now and its peak; over the budget the next tile stops the pass (EXIT_RESTART): a
        group of a window layer holds its window whole, and a pass is cheap to start again."""
        self.memory_gb = memory_gb()
        self.memory_peak_gb = max(self.memory_peak_gb, self.memory_gb)
        if self.area.max_memory_gb and self.memory_gb > self.area.max_memory_gb:
            self.over_budget = True

    def _index_folders(self) -> List[Tuple[str, set]]:
        """For every layer with a cached index: its folder of 0.25° answers and the names of this area's tiles
        there (sources.indexes.cached.index_tiles: those near the outline; the grid's whole box before it)."""
        import osm
        from rasterio.warp import transform_bounds
        from sources.indexes import cached
        found = []
        for plan in self.plans:
            grid = plan.grid
            index_tiles = getattr(cached, "index_tiles", None)
            if index_tiles is not None:
                tiles = index_tiles(grid)
            else:
                tiles = osm.tiles(*transform_bounds(grid.crs, "EPSG:4326", *grid.bounds))
            names = {f"{osm.tile_name(lat, lon)}.json" for lat, lon in tiles}
            for layer in plan.layers:
                index = getattr(layer, "index", None)
                if isinstance(index, cached.CachedIndex) and tiles:
                    found.append((os.path.dirname(index.index_path(plan.paths.cache, *tiles[0])), names))
        return found

    def _index_counts(self) -> Tuple[int, int]:
        """The index answers of this area's 0.25° tiles there are (all layers), and how many there will be. The
        tiles are listed once per pass (680 000 for the USA), and only they are counted: a folder is shared by
        every area of a source (Liechtenstein showed 48 of 8 with Austria's answers beside its own)."""
        if self._indexes is None:
            self._indexes = self._index_folders()
        got = total = 0
        for folder, names in self._indexes:
            try:
                present = set(os.listdir(folder))
            except OSError:
                present = set()
            got += len(names & present)
            total += len(names)
        return got, total

    def _free(self) -> Optional[float]:
        """GB free where the tiles go; None when that cannot be asked (a share that is away), or before the plan."""
        if not self.plans:
            return None
        try:
            plan = self.plans[0]
            folder = os.path.join(plan.paths.cache, plan.layers[0].folder)
            os.makedirs(folder, exist_ok=True)
            return shutil.disk_usage(folder).free / 1e9
        except OSError:
            return None

    def write(self):
        with self.lock:
            state = self.state
            state["failed"] = len(self.failures.tiles)
            state["mb"] = self.mb_before + self.mb_pass
            state["memory_gb"], state["memory_peak_gb"] = round(self.memory_gb, 2), round(self.memory_peak_gb, 2)
            if self.tiles_total:
                state["tiles_total"] = self.tiles_total
                state["tiles_done"] = self.tiles_cached + self.tiles_pass
            elif state["stage"] == "listing" and self.plans:
                state["index_done"], state["index_total"] = self._index_counts()
            now = self.clock()
            minute = now >= self.next_minute
            if minute:
                self.next_minute = now + HISTORY_SECONDS
                self.free_gb = state["free_gb"] = self._free()
            write_state(self.area.state_dir, self.area.name, dict(state))
            if self.tiles_total and now >= self.next_row:  # its values all of this write: now, tiles, MB, memory
                self.next_row = now + HISTORY_SECONDS
                with open(self.area.file(".history.csv"), "a", encoding="utf-8", newline="") as f:
                    csv.writer(f).writerow([round(now), state["tiles_done"], round(state["mb"], 1),
                                            round(self.memory_gb, 2)])
            if minute:
                write_page(self.area.state_dir)

    def next_plan(self):
        """The tiles and MB downloaded so far stay counted while the next plan's bar starts from 0."""
        self.tiles_offset, self.mb_offset = self.tiles_pass, self.mb_pass

    def __call__(self, bar: Dict):
        """A change of a progress bar (progress.subscribe), in the thread downloading."""
        if bar["bar"] != "Download" or bar["unit"] != "tile" or not bar["count"] or bar["done"]:
            return  # a finished bar stands at its total, with the tiles that failed
        self.failures.in_a_row = 0
        self.tiles_pass = self.tiles_offset + bar["count"]
        with contextlib.suppress(KeyError, ValueError):
            self.mb_pass = self.mb_offset + float(bar["extra"]["MB"])
        if self.state["message"] == NO_CONTACT:
            self.state["message"] = ""   # shown until the first tile
        if self.over_budget:
            raise Stop(f"memory {self.memory_gb:.1f} GB over the budget of {self.area.max_memory_gb:g} GB, "
                       "the pass is started again", EXIT_RESTART)
        if self.free_gb is not None and self.free_gb < self.area.min_free_gb:
            raise Stop(f"{self.free_gb:.0f} GB free where the tiles go, at least {self.area.min_free_gb:g} kept")


def outline(area: Area) -> str:
    """<name>.geojson, the area's outline, fetched once and never simplified (as country._write_outline, but no
    country of the data folder: a folder in countries/ would be taken off the next country's outline)."""
    import area as ar
    from shapely.geometry import mapping
    path = area.file(".geojson")
    if not os.path.exists(path):
        cache_dir = os.path.join(area.data_dir, "cache")
        cache.check_layout(cache_dir)
        geometry = ar.from_spec(area.area, 0.0, None, cache_dir, whole=True).geometry
        feature = {"type": "Feature", "properties": {"name": area.name, "area": area.area},
                   "geometry": mapping(geometry)}
        with cache.replacing(path, "w", encoding="utf-8") as f:
            json.dump(feature, f)
    return path


def plan_of(area: Area):
    """The plan of a search over the whole outline: its layers (terrain, and the surface where the source has one)
    and its grid, without tiles."""
    import area as ar
    import search
    import sources as src
    from params import SearchParams
    work = os.path.join(area.data_dir, "work", f"area-download-{area.name}")
    # The outline clipped to the source's coverage boxes (Source.coverage_boxes): the USA's holds Hawaii and
    # islands far off its 1 m DEM; the stored outline (<state>/<name>.geojson) stays as it is
    source = src.SOURCES.get(area.source)
    path, dropped = ar.clip_outline_file(outline(area), source.coverage_boxes() if source else [],
                                         os.path.join(work, "outline.geojson"))
    if dropped:
        print(f"Outline clipped to the source's coverage boxes: about {dropped:,.0f} km² outside them left out")
    params = SearchParams(area=path, source=area.source, resolution=area.resolution, nmpt="mark")
    return search.plan_search(params, search.Paths(area.data_dir, work), lambda kind, text: print(text), tiled=False)


def plans_of(area: Area) -> List:
    """The plan of the area's source and, where the catalogue names one, of its stand-in (Source.instead_without_data:
    `alaska` has no 1 m data over most of Alaska, so a search there switches to `alaska_ifsar`, which choose_source
    never does for a source given by name): both are downloaded, so a search anywhere in the area finds its data."""
    plan = plan_of(area)
    stand_in = getattr(getattr(plan, "source", None), "instead_without_data", None)
    if not stand_in or stand_in == area.source:
        return [plan]
    return [plan, plan_of(dataclasses.replace(area, source=stand_in))]


def _labels(area: Area, plans: Sequence) -> List[List[str]]:
    """The labels of each plan's layers in the state: "terrain", "surface"; a stand-in's with its id."""
    labels = []
    for k, plan in enumerate(plans):
        source = getattr(getattr(plan, "source", None), "id", area.source)
        suffix = "" if k == 0 else f" ({source})"
        labels.append([f"{kind}{suffix}" for kind, _ in zip(("terrain", "surface"), plan.layers)])
    return labels


def _set_host_slots(area: Area):
    """The connections this process opens to a host, also below what the app keeps for it. The threads beyond them
    would only wait, holding their tiles."""
    import sources as src
    if area.host_slots:
        src.net.HOST_SLOTS_OF.update(dict(area.host_slots))
        src.layer.DOWNLOAD_THREADS = min(src.layer.DOWNLOAD_THREADS, *(n for _, n in area.host_slots))


def _remove_parts(plans: Sequence) -> int:
    """The temporary files of killed passes in the layers' folders."""
    removed = 0
    limit = time.time() - PART_AGE_SECONDS
    for plan in plans:
        for layer in plan.layers:
            for folder, _, names in os.walk(os.path.join(plan.paths.cache, layer.folder)):
                for name in names:
                    path = os.path.join(folder, name)
                    if name.endswith(".part") and os.path.getmtime(path) < limit:
                        os.remove(path)
                        removed += 1
    return removed


def _group_m(area: Area, plan) -> float:
    """The window layers' groups (sources.download_layers(group_m=)) hold the same pixels whatever the data:
    country.PREFETCH_GROUP_M is sized for 1 m data, and a group's window is read on the files' own pixels, not the
    grid's (Luxembourg's and Scotland's 0.5 m float64 files, downloaded at the app's minimum of 1 m: groups of
    10 km took about 5 GB a thread, and the passes were OOM-killed at 17-49 GB on a server of 62 GB without swap,
    Luxembourg 11 times, Scotland 7, New Zealand 6, Wales 2; 2026-11-07). So 10 km at 1 m, 5 km at 0.5 m, 20 km at
    2 m, by the finest native resolution of the plan's grouped layers (the area's resolution without one)."""
    import country
    native = [getattr(layer, "native_res", None) for layer in plan.layers if getattr(layer, "groups", False)]
    return country.PREFETCH_GROUP_M * min([r for r in native if r] or [area.resolution])


def _count_missing(cache_dir: str, plans: Sequence, rows: List[Dict]):
    """How many tiles of each layer the service has no data for (the sea, a Land's edge, a sheet never flown),
    into the rows of the state: "done" then says what it has."""
    k = 0
    for plan in plans:
        for layer in plan.layers:
            tiles = layer.tiles(plan.grid) or []
            rows[k]["missing"] = cache.count_missing(cache_dir, (layer.tile_path(cache_dir, t) for t in tiles))
            k += 1


def _planned(area: Area) -> List:
    """plans_of, or a Stop with what went wrong (a source without its key, an outline Nominatim does not know):
    the pass ends with the text in the state, not a traceback as its only trace."""
    import search
    try:
        return plans_of(area)
    except (search.SearchError, ValueError, RuntimeError, OSError) as e:
        raise Stop(f"the download could not be planned: {cache.clean_error(e)}") from e


def run_pass(area: Area, number: int) -> int:
    """One pass over everything still missing: EXIT_DONE, EXIT_FAILED, EXIT_STOPPED, EXIT_RESTART or EXIT_NOTHING."""
    import progress as bars
    import sources as src
    bars.TEXT_INTERVAL = PROGRESS_SECONDS
    print(f"=== pass {number} of {area.name}, {_now()}, {cache.http_headers()['User-Agent']} ===", flush=True)
    cache_dir = os.path.join(area.data_dir, "cache")  # search.Paths(area.data_dir, ...).cache
    failures = Failures(cache_dir)
    code = EXIT_DONE
    plans: List = []
    with Reporter(area, number, plans, failures) as reporter:
        if not os.environ.get("FINDALINE_CONTACT"):
            print(f"Warning: {NO_CONTACT}", flush=True)
            reporter.state["message"] = NO_CONTACT
        try:
            _set_host_slots(area)
            plans = _planned(area)
            reporter.plans = plans
            labels = _labels(area, plans)
            rows = []
            for plan, plan_labels in zip(plans, labels):
                grid = plan.grid
                print(f"{area.name} ({plan_labels[0]}): {grid.width} x {grid.height} px, listing the tiles", flush=True)
                # to_download, not Layer.estimate: that opens every cached file of a layer whose index cannot be reached
                listed = src.layer.each_layer(plan.layers, lambda layer, g=grid: layer.to_download(g, cache_dir, None))
                for layer in plan.layers:
                    if layer.tiles(grid) is None:
                        raise Stop(f"the index of {layer.description} could not be reached")
                rows += [{"label": label, "tiles": len(layer.tiles(grid)), "to_download": len(todo), "missing": 0}
                         for layer, label, (todo, _) in zip(plan.layers, plan_labels, listed)]
            reporter.state["layers"] = rows
            reporter.tiles_total = sum(row["tiles"] for row in rows)
            reporter.tiles_cached = reporter.tiles_total - sum(row["to_download"] for row in rows)
            if not reporter.tiles_total:
                raise Stop("no tiles under the outline: the source has no data here or the listing found none",
                           EXIT_NOTHING)
            reporter.state["stage"] = "downloading"
            reporter.write()
            bars.progress.subscribe(reporter)
            for plan, plan_labels in zip(plans, labels):
                # reencode_cached False: a pass reads no tile, so those in the old encoding wait for what does
                src.download_layers(list(zip(plan.layers, plan_labels)), plan.grid, cache_dir, None,
                                    group_m=_group_m(area, plan), on_error=failures, reencode_cached=False)
                reporter.next_plan()
            _count_missing(cache_dir, plans, rows)
            reporter.state["tiles_missing"] = missing = sum(row["missing"] for row in rows)
            if failures.tiles:
                code = EXIT_FAILED
            elif missing == reporter.tiles_total:
                raise Stop(f"all {missing:,} tiles without data: the source has nothing under the outline",
                           EXIT_NOTHING)
            else:
                print(f"{_remove_parts(plans)} temporary files of earlier passes removed", flush=True)
                reporter.state["stage"] = "done"
        except Stop as e:
            print(f"Stopped: {e}", flush=True)
            reporter.state["message"] = str(e)
            code = e.code
        finally:
            with contextlib.suppress(ValueError):
                bars.progress.unsubscribe(reporter)
        if code == EXIT_DONE and reporter.state["message"] == NO_CONTACT:
            reporter.state["message"] = ""   # nothing to download: a pass that ended early keeps the warning in sight
        reporter.write()
    with cache.replacing(area.file(".failed.json"), "w", encoding="utf-8") as f:
        json.dump(failures.tiles, f, indent=1, ensure_ascii=False)
    write_page(area.state_dir)
    return code


# --- the supervisor ----------------------------------------------------------------------------------------------

def _kill_tree(process: subprocess.Popen):
    """The process and its children: a venv's python.exe on Windows runs the interpreter as its child."""
    with contextlib.suppress(psutil.NoSuchProcess):
        for child in psutil.Process(process.pid).children(recursive=True):
            with contextlib.suppress(psutil.NoSuchProcess):
                child.kill()
    process.kill()
    process.wait()


def _low_priority() -> Dict:
    """Popen's arguments for a pass: below the normal priority, the desktop and the tests go first."""
    if os.name == "nt":
        return {"creationflags": subprocess.BELOW_NORMAL_PRIORITY_CLASS}
    return {"preexec_fn": lambda: os.nice(5)}


def _say(log, text: str):
    log.write(f"[{_now()}] {text}\n")
    log.flush()


def _set_stage(area: Area, stage: str, message: str = "", **more):
    state = read_state(area.state_dir, area.name) or {"name": area.name, "area": area.area, "source": area.source}
    state.update(stage=stage, message=message, pid=os.getpid(), **more)
    write_state(area.state_dir, area.name, state)
    write_page(area.state_dir)


_SAID = re.compile(r"^\[\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ\] ")   # the supervisor's own lines of the log (_say)


def _last_line(path: str) -> str:
    """The last line a pass wrote to the log: what a crash (a code of its own, a traceback) left to go on."""
    try:
        with open(path, "rb") as f:
            f.seek(max(0, os.path.getsize(path) - LOG_TAIL_BYTES))
            lines = [line.strip() for line in f.read().decode("utf-8", errors="replace").splitlines()]
    except OSError:
        return ""
    lines = [line for line in lines if line and not _SAID.match(line)]
    return lines[-1] if lines else ""


def _wait_or_stop(area: Area, seconds: float) -> bool:
    """False when the stop file came meanwhile."""
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if os.path.exists(area.file(".stop")):
            return False
        time.sleep(min(POLL_SECONDS, seconds))
    return True


def supervise(area: Area, command: Sequence[str], retry_seconds: float = RETRY_SECONDS) -> int:
    """Passes (`command` with the pass's number after it) until one finds nothing left, the area turns out to need
    attention or the stop file comes. Exit: 0 done or stopped, 1 running already, 2 needs attention.

    A pass over its memory budget (EXIT_RESTART) is started again at once when it made progress (the state's tiles
    or MB grew since the pass before, or it was the first pass); without progress the next pass waits retry_seconds
    like any other, and ATTENTION_PASSES such restarts in a row end the area (a budget too small for a group, or a
    pass over it before its first tile, would otherwise list everything again in a hot loop). Any other pass that
    did not finish is followed by another after retry_seconds. Attention: an area without data (EXIT_NOTHING); the
    same tiles failing (EXIT_FAILED), a pass giving up with the same message (EXIT_STOPPED: Slovenia looped 37
    passes on "50 failures in a row", Denmark 13 on a missing key) or a crash (any other code) ending on the same
    line of the log, each ATTENTION_PASSES passes in a row; a restart neither counts nor breaks such a row."""
    os.makedirs(area.state_dir, exist_ok=True)
    lock = FileLock(area.file(".lock"))
    try:
        lock.acquire(blocking=False)
    except Timeout:
        print(f"{area.name} is being downloaded already")
        return 1
    try:
        with contextlib.suppress(FileNotFoundError):
            os.remove(area.file(".stop"))
        env = dict(os.environ, PYTHONUNBUFFERED="1", FINDALINE_PROGRESS="text")
        # GDAL's block cache of a pass: its default is 5 % of the machine's memory for every process, and several
        # areas download at once on one machine; the environment's own setting stays
        env.setdefault("GDAL_CACHEMAX", str(GDAL_CACHEMAX_MB))
        ended, same, number = None, 0, 0   # how the last pass ended, and how many ended that way in a row
        restarts = read_state(area.state_dir, area.name).get("restarts", 0)
        reached, stuck = None, 0   # (tiles, MB) at the last pass's end; restarts without progress in a row
        with open(area.file(".log"), "a", encoding="utf-8") as log:
            while True:
                number += 1
                _say(log, f"pass {number} starts")
                process = subprocess.Popen([*command, str(number)], stdout=log, stderr=subprocess.STDOUT, env=env,
                                           cwd=REPO, **_low_priority())
                while process.poll() is None:
                    if not _wait_or_stop(area, POLL_SECONDS):
                        _kill_tree(process)
                        _say(log, "stopped by hand")
                        _set_stage(area, "stopped", "stopped by hand: `run` resumes")
                        return 0
                code = process.returncode
                last = _last_line(area.file(".log"))
                _say(log, f"pass {number} ended with {code}")
                if code == EXIT_DONE:
                    return 0
                state = read_state(area.state_dir, area.name)
                message = state.get("message", "") or f"pass {number} ended with {code}"
                now_reached = (state.get("tiles_done", 0), state.get("mb", 0.0))
                progressed = reached is None or now_reached[0] > reached[0] or now_reached[1] > reached[1]
                reached = now_reached
                if code == EXIT_RESTART:
                    restarts += 1
                    if progressed:
                        stuck = 0
                        _say(log, f"started again at once ({restarts} restarts): {message}")
                        _set_stage(area, "waiting", message, restarts=restarts)
                        continue
                    stuck += 1
                    _say(log, f"restart without progress ({stuck} in a row, {restarts} restarts): {message}")
                    if stuck >= ATTENTION_PASSES:
                        text = (f"the memory budget of {area.max_memory_gb:g} GB is too small for this area: "
                                "raise --max-memory-gb")
                        _say(log, f"needs attention: {text}")
                        _set_stage(area, "needs attention", text, restarts=restarts)
                        return 2
                    _set_stage(area, "waiting", message, restarts=restarts)
                    if not _wait_or_stop(area, retry_seconds):
                        _say(log, "stopped by hand")
                        _set_stage(area, "stopped", "stopped by hand: `run` resumes")
                        return 0
                    continue
                if code == EXIT_NOTHING:
                    _say(log, f"needs attention: {message}")
                    _set_stage(area, "needs attention", message)
                    return 2
                if code == EXIT_FAILED:
                    with open(area.file(".failed.json"), encoding="utf-8") as f:
                        now = frozenset(json.load(f))
                    this = ("failed", now)
                    message = f"{len(now)} tiles failed in pass {number}"
                elif code == EXIT_STOPPED:
                    this = ("stopped", message.split(", the last:")[0])  # Failures' last error differs by tile
                else:  # a crash: what the log says last
                    message = f"pass {number} ended with {code}" + (f": {last}" if last else "")
                    this = ("crashed", code, last)
                same = same + 1 if this == ended else 1
                ended = this
                if same >= ATTENTION_PASSES:
                    if code == EXIT_FAILED:
                        text = f"{message}, the same in {same} passes: {os.path.basename(area.file('.failed.json'))}"
                    else:
                        text = f"{message} ({same} {'passes' if code == EXIT_STOPPED else 'crashes'} in a row)"
                    _say(log, f"needs attention: {text}")
                    _set_stage(area, "needs attention", text)
                    return 2
                _set_stage(area, "waiting", message)
                if not _wait_or_stop(area, retry_seconds):
                    _say(log, "stopped by hand")
                    _set_stage(area, "stopped", "stopped by hand: `run` resumes")
                    return 0
    finally:
        lock.release()


# --- what is shown -----------------------------------------------------------------------------------------------

def summary(state: Dict, history: Sequence[Tuple[float, float, float]], now: float) -> Dict:
    """What the table and the page show of an area: the numbers worked out from its state and history."""
    done, total = state.get("tiles_done", 0), state.get("tiles_total", 0)
    mb_s = eta = None
    recent = history[-SPEED_ROWS:]
    if len(recent) > 1 and recent[-1][0] > recent[0][0]:
        mb_s = max(0.0, (recent[-1][2] - recent[0][2]) / (recent[-1][0] - recent[0][0]))
    window = history[-ETA_ROWS:]
    if len(window) > 1 and window[-1][1] > window[0][1] and total > done:
        eta = (total - done) * (window[-1][0] - window[0][0]) / (window[-1][1] - window[0][1])
    stage = state.get("stage", "unknown")
    updated = _seconds(state["updated"]) if state.get("updated") else None
    limit = STALE_SECONDS + (RETRY_SECONDS if stage == "waiting" else 0)
    stale = stage not in FINISHED and (updated is None or now - updated > limit)
    if stage in FINISHED or stage == "waiting":
        mb_s = eta = None
    return {"name": state.get("name", ""), "stage": stage, "done": done, "total": total,
            "share": done / total if total else None, "gb": state.get("mb", 0.0) / 1000, "mb_s": mb_s, "eta": eta,
            "failed": state.get("failed", 0), "free_gb": state.get("free_gb"), "message": state.get("message", ""),
            "index_done": state.get("index_done"), "index_total": state.get("index_total"), "stale": stale,
            "updated": updated, "pass": state.get("pass"), "source": state.get("source", ""),
            "restarts": state.get("restarts", 0), "memory_gb": state.get("memory_gb"),
            "memory_peak_gb": state.get("memory_peak_gb"), "missing": state.get("tiles_missing", 0)}


def duration(seconds: Optional[float]) -> str:
    if seconds is None:
        return "-"
    if seconds >= 86400:
        return f"{seconds / 86400:.1f} d"
    if seconds >= 3600:
        return f"{seconds / 3600:.1f} h"
    return f"{seconds / 60:.0f} min"


def _notes(row: Dict) -> List[str]:
    """What the table and the page add after the numbers: the restarts over the memory budget."""
    notes = []
    if row.get("missing"):
        notes.append(f"{row['missing']:,} tiles without data")
    if row.get("restarts"):
        notes.append(f"{row['restarts']} {'restart' if row['restarts'] == 1 else 'restarts'} over the memory budget")
    return notes


def _tiles_text(row: Dict) -> str:
    if row["total"]:
        return f"{row['done']:,} / {row['total']:,} ({100 * row['share']:.1f} %)"
    if row["index_total"]:
        return f"index {row['index_done']:,} / {row['index_total']:,}"
    return "-"


def areas(state_dir: str, now: Optional[float] = None) -> List[Dict]:
    """The summaries of every area of the folder, with their histories."""
    now = time.time() if now is None else now
    rows = []
    for path in sorted(glob.glob(state_file(glob.escape(state_dir), "*", ".state.json"))):
        name = os.path.basename(path)[:-len(".state.json")]
        history = read_history(state_dir, name)
        rows.append({**summary(read_state(state_dir, name), history, now), "history": history})
    return rows


def table(state_dir: str, now: Optional[float] = None) -> str:
    rows = areas(state_dir, now)
    if not rows:
        return f"No areas in {state_dir}"
    lines = [f"{'area':<10} {'stage':<16} {'tiles':<34} {'GB':>8} {'MB/s':>6} {'left':>8} {'failed':>6} {'free GB':>8} "
             f"{'mem GB':>7}"]
    for r in rows:
        speed = f"{r['mb_s']:.1f}" if r["mb_s"] is not None else "-"
        free = f"{r['free_gb']:.0f}" if r["free_gb"] is not None else "-"
        memory = f"{r['memory_gb']:.1f}" if r["memory_gb"] is not None else "-"
        stage = r["stage"] + (" (stale)" if r["stale"] else "")
        lines.append(f"{r['name']:<10} {stage:<16} {_tiles_text(r):<34} {r['gb']:>8.1f} {speed:>6} "
                     f"{duration(r['eta']):>8} {r['failed']:>6} {free:>8} {memory:>7}")
        notes = ([r["message"]] if r["message"] else []) + _notes(r)
        if notes:
            lines.append(f"{'':<10} {'; '.join(notes)}")
    return "\n".join(lines)


def _speeds(history: Sequence[Tuple[float, float, float]]) -> List[Tuple[float, float]]:
    """(seconds, MB/s) of the history in at most CHART_POINTS steps."""
    if len(history) < 2:
        return []
    step = max(1, (len(history) - 1) // CHART_POINTS)
    picked = list(history[::step])
    if picked[-1] != history[-1]:
        picked.append(history[-1])
    return [(b[0], max(0.0, b[2] - a[2]) / (b[0] - a[0])) for a, b in zip(picked, picked[1:]) if b[0] > a[0]]


def _chart(history: Sequence[Tuple[float, float, float]]) -> str:
    speeds = _speeds(history)
    if len(speeds) < 2:
        return '<p class="note">The chart of the speed starts once there is a history.</p>'
    width, height = 720, 90
    first, last = speeds[0][0], speeds[-1][0]
    top = max(s for _, s in speeds) or 1.0
    points = [(width * (t - first) / (last - first or 1), height - 2 - (height - 6) * s / top) for t, s in speeds]
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
    days = lambda t: datetime.fromtimestamp(t).strftime("%d.%m %H:%M")  # noqa: E731
    return (f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="Download speed over time">'
            f'<polygon class="fill" points="0,{height} {line} {width},{height}"/>'
            f'<polyline class="line" points="{line}"/></svg>'
            f'<div class="axis"><span>{days(first)}</span><span>peak {top:.1f} MB/s</span>'
            f'<span>{days(last)}</span></div>')


PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta http-equiv="refresh" content="30">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Area downloads</title><style>
:root {{ --bg: #f6f7f8; --card: #fff; --ink: #1c2126; --soft: #5d6873; --rule: #dde2e6; --bar: #2f6f9f;
  --ok: #2e7d4f; --warn: #b3541e; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg: #14181c; --card: #1d2329; --ink: #e8ecef; --soft: #9aa6b1;
  --rule: #323b44; --bar: #5ba3d6; --ok: #62b98a; --warn: #e49a66; }} }}
body {{ margin: 0; padding: 24px 16px; background: var(--bg); color: var(--ink);
  font: 15px/1.45 system-ui, "Segoe UI", sans-serif; }}
main {{ max-width: 780px; margin: 0 auto; }}
h1 {{ font-size: 20px; margin: 0 0 4px; }}
.note {{ color: var(--soft); margin: 0; font-size: 13px; }}
section {{ background: var(--card); border: 1px solid var(--rule); border-radius: 8px; padding: 16px;
  margin-top: 16px; }}
h2 {{ font-size: 16px; margin: 0; display: flex; justify-content: space-between; gap: 12px; }}
.stage {{ font-weight: 500; color: var(--soft); }}
.stage.done {{ color: var(--ok); }}
.stage.bad, .warn {{ color: var(--warn); }}
.track {{ height: 10px; border-radius: 5px; background: var(--rule); margin: 12px 0 10px; overflow: hidden; }}
.track div {{ height: 100%; background: var(--bar); }}
dl {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 8px 16px; margin: 0 0 10px; }}
dt {{ color: var(--soft); font-size: 12px; }}
dd {{ margin: 0; font-variant-numeric: tabular-nums; }}
svg {{ display: block; width: 100%; height: 90px; }}
.fill {{ fill: var(--bar); opacity: .15; }}
.line {{ fill: none; stroke: var(--bar); stroke-width: 1.5; vector-effect: non-scaling-stroke; }}
.axis {{ display: flex; justify-content: space-between; color: var(--soft); font-size: 12px; }}
.message {{ margin: 0 0 10px; }}
</style></head><body><main>
<h1>Area downloads</h1><p class="note">Written {written}. The page reloads every 30 seconds.</p>
<p class="note warn" id="stale" hidden></p>
{sections}
</main><script>
const written = {written_ms};
function check() {{
  const minutes = Math.round((Date.now() - written) / 60000);
  const note = document.getElementById("stale");
  note.hidden = minutes < {stale_minutes} || {finished};
  note.textContent = "Nothing written for " + minutes + " minutes: the downloads may have stopped.";
}}
check();
setInterval(check, 30000);
</script></body></html>
"""


def _section(row: Dict) -> str:
    stage = row["stage"] + (" (stale)" if row["stale"] else "")
    kind = "done" if row["stage"] == "done" else "bad" if row["stale"] or row["stage"] in ("needs attention", "waiting") else ""
    share = 100 * row["share"] if row["share"] is not None else 0.0
    speed = f"{row['mb_s']:.1f} MB/s" if row["mb_s"] is not None else "-"
    free = f"{row['free_gb']:,.0f} GB" if row["free_gb"] is not None else "-"
    cells = [("Tiles", _tiles_text(row)), ("Downloaded", f"{row['gb']:,.1f} GB"), ("Speed", speed),
             ("Time left", duration(row["eta"])), ("Failed", f"{row['failed']:,}"), ("Free space", free)]
    if row["missing"]:
        cells.append(("Without data", f"{row['missing']:,}"))
    if row["memory_gb"] is not None:
        cells.append(("Memory", f"{row['memory_gb']:.1f} GB (peak {row['memory_peak_gb'] or 0:.1f})"))
    if row["restarts"]:
        cells.append(("Restarts", f"{row['restarts']:,}"))
    terms = "".join(f"<div><dt>{html.escape(k)}</dt><dd>{html.escape(v)}</dd></div>" for k, v in cells)
    message = f'<p class="message warn">{html.escape(row["message"])}</p>' if row["message"] else ""
    return (f'<section><h2><span>{html.escape(row["name"])} <span class="note">{html.escape(row["source"])}</span></span>'
            f'<span class="stage {kind}">{html.escape(stage)}</span></h2>'
            f'<div class="track"><div style="width: {share:.2f}%"></div></div>'
            f'{message}<dl>{terms}</dl>{_chart(row["history"])}</section>')


def page(state_dir: str, now: Optional[float] = None) -> str:
    now = time.time() if now is None else now
    rows = areas(state_dir, now)
    return PAGE.format(written=datetime.fromtimestamp(now).strftime("%d.%m.%Y %H:%M:%S"), written_ms=round(now * 1000),
                       finished="true" if rows and all(r["stage"] in FINISHED for r in rows) else "false",
                       stale_minutes=round((RETRY_SECONDS + STALE_SECONDS) / 60),
                       sections="\n".join(_section(r) for r in rows))


def write_page(state_dir: str):
    """status.html; a moment's clash with another area's process only leaves it for the next round."""
    with contextlib.suppress(OSError):
        with cache.replacing(os.path.join(state_dir, "status.html"), "w", encoding="utf-8") as f:
            f.write(page(state_dir))


# --- the commands ------------------------------------------------------------------------------------------------

def _area_of(args) -> Area:
    slots = []
    for item in args.host_slots or ():
        host, _, number = item.partition("=")
        slots.append((host, int(number)))
    budget = default_max_memory_gb() if args.max_memory_gb is None else args.max_memory_gb
    return Area(args.name, args.area, args.source, args.resolution, os.path.abspath(args.data_dir),
                os.path.abspath(args.state_dir), tuple(slots), args.min_free_gb, budget)


def _pass_command(area: Area) -> List[str]:
    """`pass` of this area, as the supervisor starts it: the budget as resolved, so every pass has the same."""
    command = [sys.executable, os.path.abspath(__file__), "pass", area.name, "--area", area.area, "--source",
               area.source, "--resolution", str(area.resolution), "--data-dir", area.data_dir,
               "--state-dir", area.state_dir, "--min-free-gb", str(area.min_free_gb),
               "--max-memory-gb", str(area.max_memory_gb)]
    for host, n in area.host_slots:
        command += ["--host-slots", f"{host}={n}"]
    return command + ["--number"]


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Downloads the elevation models of a whole area, resumably.")
    commands = parser.add_subparsers(dest="command", required=True)

    def downloading(sub):
        sub.add_argument("name", help="the area's name in the state folder")
        sub.add_argument("--area", required=True, help="osm:<name> or a GeoJSON file")
        sub.add_argument("--source", required=True, help="the catalogue's source")
        sub.add_argument("--resolution", required=True, type=float, help="metres: the finest grid that will read it")
        sub.add_argument("--data-dir", required=True, help="the data folder whose cache is filled")
        sub.add_argument("--state-dir", required=True, help="where the state, logs and status.html go")
        sub.add_argument("--host-slots", action="append", metavar="HOST=N", help="at most N connections to a host")
        sub.add_argument("--min-free-gb", type=float, default=FREE_GB_MIN, help="stop waiting below this much free")
        sub.add_argument("--max-memory-gb", type=float, help="a pass over this much memory is started again "
                         "(a quarter of the machine's memory unless given; 0: no budget)")

    downloading(commands.add_parser("run", help="download, pass after pass, until nothing is left"))
    one = commands.add_parser("pass", help="one pass (started by run)")
    downloading(one)
    one.add_argument("--number", required=True, type=int)
    status = commands.add_parser("status", help="the areas of a state folder")
    status.add_argument("--state-dir", required=True)
    status.add_argument("--watch", type=float, metavar="SECONDS", help="again every so many seconds")
    stop = commands.add_parser("stop", help="stop the areas: `run` resumes them")
    stop.add_argument("names", nargs="+")
    stop.add_argument("--state-dir", required=True)
    tui = commands.add_parser("tui", help="the window: tick the areas, start and stop them (uv sync --group tui)")
    tui.add_argument("--settings", required=True, help="the JSON file tools/area_rows.py describes")
    args = parser.parse_args(argv)
    if args.command == "run":
        area = _area_of(args)
        return supervise(area, _pass_command(area))
    if args.command == "pass":
        return run_pass(_area_of(args), args.number)
    if args.command == "tui":
        try:
            import area_download_tui
        except ModuleNotFoundError as e:
            print(f"The window needs {e.name}: uv sync --group tui", file=sys.stderr)
            return 2
        return area_download_tui.run(args.settings)
    if args.command == "stop":
        for name in args.names:
            with open(state_file(args.state_dir, name, ".stop"), "w", encoding="utf-8"):
                pass
        return 0
    while True:
        print(table(os.path.abspath(args.state_dir)), flush=True)
        if not args.watch:
            return 0
        time.sleep(args.watch)
        print()


if __name__ == "__main__":
    from progress import utf8_output
    utf8_output()  # redirected output in UTF-8, not the Windows code page (no "²" there)
    sys.exit(main())
