"""
Downloads the elevation models of a whole area into the cache of a data folder and does nothing else: no search,
no tiles counted, no weights (`findaline.py country run` does those, and finds the data cached). For a download of
days or weeks, so it survives what happens in that time, and can be followed.

- A supervisor (`run`) starts one pass after another, each a process of its own: what a process keeps (an index
  that could not be reached is remembered as None by sources.indexes.cached.CachedIndex.tiles, which would skip the
  whole layer) ends with it. A pass that did not finish is followed by another after RETRY_SECONDS, and what is
  cached stays: restarting costs the listing only.
- A tile that fails does not stop the others (sources.download_layers(on_error=)). FAILURES_IN_A_ROW failed tasks with
  no tile between them end the pass (the service or the disk is away), and so does a disk with less than --min-free-gb.
- When the same tiles fail in ATTENTION_PASSES passes in a row, the area stops as "needs attention" with them in
  <name>.failed.json: everything else is downloaded by then.

The state goes to --state-dir: <name>.state.json every STATE_SECONDS, <name>.history.csv and status.html (one page
for every area of the folder, for a browser from disk) every HISTORY_SECONDS, <name>.log (the passes' output).

    uv run tools/area_download.py run poland --area osm:Polska --source geoportal --resolution 1 \\
        --data-dir <data> --state-dir <state> --host-slots opendata.geoportal.gov.pl=2
    uv run tools/area_download.py status --state-dir <state> --watch 30
    uv run tools/area_download.py stop poland --state-dir <state>     # `run` again resumes

The requests go out as those of a search (cache.http_headers); FINDALINE_CONTACT in the environment adds a contact.
"""

import argparse
import contextlib
import csv
import glob
import html
import json
import os
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
EXIT_STOPPED = 4   # a pass that gave up: the index could not be reached, the failures in a row, the disk
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
FINISHED = ("done", "stopped", "needs attention")


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


def read_history(state_dir: str, name: str) -> List[Tuple[float, float, float]]:
    """(seconds, tiles done, MB) of <name>.history.csv."""
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
    """The pass cannot go on for now: the text says why."""


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

    def __init__(self, area: Area, number: int, plan, failures: Failures, clock=time.time):
        self.area, self.plan, self.failures, self.clock = area, plan, failures, clock
        before = read_state(area.state_dir, area.name)
        self.mb_before = before.get("mb", 0.0) if before.get("source") == area.source else 0.0
        self.tiles_total = self.tiles_cached = self.mb_pass = self.tiles_pass = 0
        self.free_gb: Optional[float] = None
        self.state = {"name": area.name, "area": area.area, "source": area.source, "resolution": area.resolution,
                      "stage": "listing", "pass": number, "pid": os.getpid(), "started": _now(), "message": "",
                      "tiles_done": 0, "tiles_total": 0, "failed": 0, "mb": self.mb_before}
        self.next_minute = 0.0
        self.lock = threading.Lock()  # the thread and the end of the pass both write
        self.quit = threading.Event()
        self.thread = threading.Thread(target=self._beat, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.quit.set()
        self.thread.join()

    def _beat(self):
        while not self.quit.wait(STATE_SECONDS):
            try:
                self.write()
            except OSError as e:  # the next round tries again
                print(f"The state was not written: {e}", flush=True)

    def _index_counts(self) -> Tuple[int, int]:
        """The index answers of 0.25° tiles there are (over the box of the grid, all layers), and how many."""
        import osm
        from rasterio.warp import transform_bounds
        from sources.indexes.cached import CachedIndex
        grid = self.plan.grid
        tiles = osm.tiles(*transform_bounds(grid.crs, "EPSG:4326", *grid.bounds))
        got = total = 0
        for layer in self.plan.layers:
            index = getattr(layer, "index", None)
            if isinstance(index, CachedIndex) and tiles:
                folder = os.path.dirname(index.index_path(self.plan.paths.cache, *tiles[0]))
                got += len(glob.glob(os.path.join(folder, "*.json")))
                total += len(tiles)
        return got, total

    def _free(self) -> Optional[float]:
        """GB free where the tiles go; None when that cannot be asked (a share that is away)."""
        try:
            folder = os.path.join(self.plan.paths.cache, self.plan.layers[0].folder)
            os.makedirs(folder, exist_ok=True)
            return shutil.disk_usage(folder).free / 1e9
        except OSError:
            return None

    def write(self):
        with self.lock:
            state = self.state
            state["failed"] = len(self.failures.tiles)
            state["mb"] = self.mb_before + self.mb_pass
            if self.tiles_total:
                state["tiles_total"] = self.tiles_total
                state["tiles_done"] = self.tiles_cached + self.tiles_pass
            elif state["stage"] == "listing":
                state["index_done"], state["index_total"] = self._index_counts()
            now = self.clock()
            minute = now >= self.next_minute
            if minute:
                self.next_minute = now + HISTORY_SECONDS
                self.free_gb = state["free_gb"] = self._free()
            write_state(self.area.state_dir, self.area.name, dict(state))
            if minute and self.tiles_total:
                with open(self.area.file(".history.csv"), "a", encoding="utf-8", newline="") as f:
                    csv.writer(f).writerow([round(now), state["tiles_done"], round(state["mb"], 1)])
            if minute:
                write_page(self.area.state_dir)

    def __call__(self, bar: Dict):
        """A change of a progress bar (progress.subscribe), in the thread downloading."""
        if bar["bar"] != "Download" or bar["unit"] != "tile" or not bar["count"] or bar["done"]:
            return  # a finished bar stands at its total, with the tiles that failed
        self.failures.in_a_row = 0
        self.tiles_pass = bar["count"]
        with contextlib.suppress(KeyError, ValueError):
            self.mb_pass = float(bar["extra"]["MB"])
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
    import search
    from params import SearchParams
    params = SearchParams(area=outline(area), source=area.source, resolution=area.resolution, nmpt="mark")
    work = os.path.join(area.data_dir, "work", f"area-download-{area.name}")
    return search.plan_search(params, search.Paths(area.data_dir, work), lambda kind, text: print(text), tiled=False)


def _set_host_slots(area: Area):
    """The connections this process opens to a host, also below what the app keeps for it. The threads beyond them
    would only wait, holding their tiles."""
    import sources as src
    if area.host_slots:
        src.net.HOST_SLOTS_OF.update(dict(area.host_slots))
        src.layer.DOWNLOAD_THREADS = min(src.layer.DOWNLOAD_THREADS, *(n for _, n in area.host_slots))


def _remove_parts(plan) -> int:
    """The temporary files of killed passes in the layers' folders."""
    removed = 0
    limit = time.time() - PART_AGE_SECONDS
    for layer in plan.layers:
        for folder, _, names in os.walk(os.path.join(plan.paths.cache, layer.folder)):
            for name in names:
                path = os.path.join(folder, name)
                if name.endswith(".part") and os.path.getmtime(path) < limit:
                    os.remove(path)
                    removed += 1
    return removed


def run_pass(area: Area, number: int) -> int:
    """One pass over everything still missing: EXIT_DONE, EXIT_FAILED or EXIT_STOPPED."""
    import country
    import progress as bars
    import sources as src
    bars.TEXT_INTERVAL = PROGRESS_SECONDS
    print(f"=== pass {number} of {area.name}, {_now()}, {cache.http_headers()['User-Agent']} ===", flush=True)
    _set_host_slots(area)
    plan = plan_of(area)
    cache_dir, grid = plan.paths.cache, plan.grid
    failures = Failures(cache_dir)
    layers = list(zip(plan.layers, ("terrain", "surface")))
    code = EXIT_DONE
    with Reporter(area, number, plan, failures) as reporter:
        try:
            print(f"{area.name}: {grid.width} x {grid.height} px, listing the tiles", flush=True)
            # to_download, not Layer.estimate: that opens every cached file of a layer whose index cannot be reached
            listed = src.layer.each_layer(plan.layers, lambda layer: layer.to_download(grid, cache_dir, None))
            for layer, _ in layers:
                if layer.tiles(grid) is None:
                    raise Stop(f"the index of {layer.description} could not be reached")
            reporter.state["layers"] = [{"label": label, "tiles": len(layer.tiles(grid)), "to_download": len(todo)}
                                        for (layer, label), (todo, _) in zip(layers, listed)]
            reporter.tiles_total = sum(row["tiles"] for row in reporter.state["layers"])
            reporter.tiles_cached = reporter.tiles_total - sum(row["to_download"] for row in reporter.state["layers"])
            reporter.state["stage"] = "downloading"
            reporter.write()
            bars.progress.subscribe(reporter)
            src.download_layers(layers, grid, cache_dir, None, group_m=country.PREFETCH_GROUP_M, on_error=failures)
            if failures.tiles:
                code = EXIT_FAILED
            else:
                print(f"{_remove_parts(plan)} temporary files of earlier passes removed", flush=True)
                reporter.state["stage"] = "done"
        except Stop as e:
            print(f"Stopped: {e}", flush=True)
            reporter.state["message"] = str(e)
            code = EXIT_STOPPED
        finally:
            with contextlib.suppress(ValueError):
                bars.progress.unsubscribe(reporter)
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


def _set_stage(area: Area, stage: str, message: str = ""):
    state = read_state(area.state_dir, area.name) or {"name": area.name, "area": area.area, "source": area.source}
    state.update(stage=stage, message=message, pid=os.getpid())
    write_state(area.state_dir, area.name, state)
    write_page(area.state_dir)


def _wait_or_stop(area: Area, seconds: float) -> bool:
    """False when the stop file came meanwhile."""
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if os.path.exists(area.file(".stop")):
            return False
        time.sleep(min(POLL_SECONDS, seconds))
    return True


def supervise(area: Area, command: Sequence[str], retry_seconds: float = RETRY_SECONDS) -> int:
    """Passes (`command` with the pass's number after it) until one finds nothing left, the same tiles keep failing
    or the stop file comes. Exit: 0 done or stopped, 1 running already, 2 needs attention."""
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
        failed, same, number = None, 0, 0
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
                _say(log, f"pass {number} ended with {code}")
                if code == EXIT_DONE:
                    return 0
                message = read_state(area.state_dir, area.name).get("message", "") or f"pass {number} ended with {code}"
                if code == EXIT_FAILED:
                    with open(area.file(".failed.json"), encoding="utf-8") as f:
                        now = set(json.load(f))
                    same = same + 1 if now == failed else 1
                    failed = now
                    message = f"{len(now)} tiles failed in pass {number}"
                    if same >= ATTENTION_PASSES:
                        _say(log, f"needs attention: {message}, {same} passes in a row")
                        _set_stage(area, "needs attention", f"{message}, the same in {same} passes: "
                                                            f"{os.path.basename(area.file('.failed.json'))}")
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
            "updated": updated, "pass": state.get("pass"), "source": state.get("source", "")}


def duration(seconds: Optional[float]) -> str:
    if seconds is None:
        return "-"
    if seconds >= 86400:
        return f"{seconds / 86400:.1f} d"
    if seconds >= 3600:
        return f"{seconds / 3600:.1f} h"
    return f"{seconds / 60:.0f} min"


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
    lines = [f"{'area':<10} {'stage':<16} {'tiles':<34} {'GB':>8} {'MB/s':>6} {'left':>8} {'failed':>6} {'free GB':>8}"]
    for r in rows:
        speed = f"{r['mb_s']:.1f}" if r["mb_s"] is not None else "-"
        free = f"{r['free_gb']:.0f}" if r["free_gb"] is not None else "-"
        stage = r["stage"] + (" (stale)" if r["stale"] else "")
        lines.append(f"{r['name']:<10} {stage:<16} {_tiles_text(r):<34} {r['gb']:>8.1f} {speed:>6} "
                     f"{duration(r['eta']):>8} {r['failed']:>6} {free:>8}")
        if r["message"]:
            lines.append(f"{'':<10} {r['message']}")
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
    return Area(args.name, args.area, args.source, args.resolution, os.path.abspath(args.data_dir),
                os.path.abspath(args.state_dir), tuple(slots), args.min_free_gb)


def _pass_command(args) -> List[str]:
    command = [sys.executable, os.path.abspath(__file__), "pass", args.name, "--area", args.area, "--source",
               args.source, "--resolution", str(args.resolution), "--data-dir", os.path.abspath(args.data_dir),
               "--state-dir", os.path.abspath(args.state_dir), "--min-free-gb", str(args.min_free_gb)]
    for item in args.host_slots or ():
        command += ["--host-slots", item]
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
    args = parser.parse_args(argv)
    if args.command == "run":
        return supervise(_area_of(args), _pass_command(args))
    if args.command == "pass":
        return run_pass(_area_of(args), args.number)
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
