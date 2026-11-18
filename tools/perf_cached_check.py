"""
Run by hand: where the time between the start of a download's pass and its first tile goes (docs/performance.md,
"The check of cached tiles"). A pass of tools/area_download.py lists the tiles of its outline and asks the cache
about each, twice (run_pass for its counts, then sources.download_layers), before anything is downloaded: on Utah
that took 15 min with nothing cached and 73 min with 199 466 tiles cached, at every restart of a pass.

For one area of a state folder (its state names the area, the source and the resolution; its outline is there), on
the area's real data folder, each step timed apart, in this order (the first to touch the tiles' disk pays for a
cold one: on a share, Windows keeps a folder's entries for seconds only):

  plan       the plan of a search over the outline (area_download.plan_of, its work folder under --work)
  tiles      layer.tiles(grid): the tiles under the outline, from the cached index answers where the layer has an
             index; and again, as every later call finds them
  paths      the tiles' paths in the cache (Layer.tile_path)
  files      os.path.exists of every tile, as cache._state asks (through the link, when the tiles are on a share)
  folders    the same answers from one os.scandir per folder of tiles
  rows       one SELECT a tile on the layer's index.sqlite, as cache._state asks, on a read-only connection
  rows-all   the same answers from one SELECT of the folder's rows
  check      layer.to_download(grid, cache_dir, None), what a pass calls: everything above together (after the
             steps above, so its disk is warm); with --by-folder as a pass asks since 2026-11-18
             (sources.layer.EXISTING), without as every search does
  prune      layer.downloaded's question at the end of a pass, the older surveys of the cached tiles
             (index.prune), with nothing deleted: cache.forget only counts here

It prints the seconds and the milliseconds a tile of each, and whether the two ways of each pair agree. Nothing is
downloaded: every index answer must be cached (it stops before `tiles` when one is missing, unless --allow-index).
The cache is written only where a search would write it too: a tile without a row of the index is adopted by `check`
(--no-check leaves that step and `prune` out, and the cache as it is).

    uv run tools/perf_cached_check.py utah --state-dir <state> --data-dir <data> --work <scratch> [--json <file>] \\
        [--by-folder] [--only check]

Under the test lock with --exclusive: the seconds are what is read.
"""

import argparse
import json
import os
import sqlite3
import sys
import time
from typing import Callable, Dict, List, Sequence, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, REPO)
sys.path.insert(0, HERE)

import area_download as ad  # noqa: E402
import cache  # noqa: E402


def timed(call: Callable) -> Tuple[float, object]:
    start = time.perf_counter()
    answer = call()
    return time.perf_counter() - start, answer


def files_each(paths: List[str]) -> List[bool]:
    """As cache._state: one os.path.exists a tile."""
    return [os.path.exists(path) for path in paths]


def files_by_folder(paths: List[str]) -> List[bool]:
    """The same answers from one listing of each folder that holds a tile."""
    names: Dict[str, set] = {}
    for folder in {os.path.dirname(path) for path in paths}:
        try:
            with os.scandir(folder) as entries:
                names[folder] = {entry.name for entry in entries}
        except OSError:
            names[folder] = set()
    return [os.path.basename(path) in names[os.path.dirname(path)] for path in paths]


def _read_only(cache_dir: str, top: str) -> sqlite3.Connection:
    path = os.path.join(cache_dir, top, "index.sqlite").replace("\\", "/")
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=60)


def rows_each(cache_dir: str, paths: List[str]) -> List[tuple]:
    """As cache._state: one SELECT a tile; (status, processing), None without a row."""
    if not paths:
        return []
    top = cache._split(cache_dir, paths[0])[0]
    db = _read_only(cache_dir, top)
    try:
        return [db.execute("SELECT status, processing FROM files WHERE path = ?",
                           (cache._split(cache_dir, path)[1],)).fetchone() for path in paths]
    finally:
        db.close()


def rows_at_once(cache_dir: str, paths: List[str], folder: str) -> List[tuple]:
    """The same answers from one SELECT of the rows under the layer's folder."""
    if not paths:
        return []
    top, inner = cache._split(cache_dir, os.path.join(cache_dir, *folder.split("/"), "x"))
    prefix = inner[:-1]   # the folder inside its top-level folder, with its last slash
    db = _read_only(cache_dir, top)
    try:
        found = {path: (status, processing) for path, status, processing in db.execute(
            "SELECT path, status, processing FROM files WHERE path >= ? AND path < ?", (prefix, prefix + "￿"))}
    finally:
        db.close()
    return [found.get(cache._split(cache_dir, path)[1]) for path in paths]


def index_missing(plan, cache_dir: str) -> int:
    """How many index answers of the plan's 0.25 degree tiles are not cached (0 for layers without an index)."""
    reporter = ad.Reporter.__new__(ad.Reporter)
    reporter.plans, reporter._indexes = [plan], None
    got, total = reporter._index_counts()
    return total - got


def dry_prune(layer, cache_dir: str, tiles: list) -> int:
    """index.prune of the layer over its tiles with cache.forget replaced: how many files it would delete, none
    deleted. -1 for a layer without an index that prunes."""
    prune = getattr(getattr(layer, "index", None), "prune", None)
    if prune is None:
        return -1
    found: List[str] = []
    forget, cache.forget = cache.forget, lambda cache_dir, paths: found.extend(paths)
    try:
        prune(cache_dir, tiles)
    finally:
        cache.forget = forget
    return len(found)


def measure(area: ad.Area, work: str, check: bool = True, allow_index: bool = False, by_folder: bool = False,
            only: Sequence[str] = ()) -> List[Dict]:
    """The steps of the module's docstring for every layer of the area's plan: rows of
    {"layer", "step", "tiles", "seconds", "note"}. only: just these of the steps after `paths`."""
    import sources as src
    from sources.indexes import versions
    cache_dir = os.path.join(area.data_dir, "cache")
    rows: List[Dict] = []

    def wanted(step: str) -> bool:
        return not only or step in only

    def row(layer: str, step: str, tiles: int, seconds: float, note: str = ""):
        rows.append({"layer": layer, "step": step, "tiles": tiles, "seconds": round(seconds, 3), "note": note})
        per = f"{1000 * seconds / tiles:8.3f} ms a tile" if tiles else ""
        print(f"{layer:<28} {step:<9} {tiles:>9,} tiles {seconds:9.2f} s {per}  {note}", flush=True)

    seconds, plan = timed(lambda: ad.plan_of(area, work))
    row("", "plan", 0, seconds, f"{plan.grid.width} x {plan.grid.height} px")
    missing = index_missing(plan, cache_dir)
    if missing and not allow_index:
        raise SystemExit(f"{missing} index answers of {area.name} are not cached: `tiles` would ask the service "
                         "(--allow-index to let it)")
    for layer in plan.layers:
        name = layer.description[:28]
        use = getattr(layer, "_use", None)
        if use is not None:
            use(cache_dir, None)   # as IndexedTiles.to_download: tiles() gets only the grid
        seconds, tiles = timed(lambda: layer.tiles(plan.grid))
        if tiles is None:
            raise SystemExit(f"the index of {layer.description} could not be reached")
        row(name, "tiles", len(tiles), seconds, "the first call")
        row(name, "tiles", len(tiles), timed(lambda: layer.tiles(plan.grid))[0], "again")
        seconds, paths = timed(lambda: [layer.tile_path(cache_dir, tile) for tile in tiles])
        row(name, "paths", len(paths), seconds, f"{len({os.path.dirname(p) for p in paths}):,} folders")
        each = None
        if wanted("files"):
            seconds, each = timed(lambda: files_each(paths))
            row(name, "files", len(paths), seconds, f"{sum(each):,} there")
        if wanted("folders"):
            seconds, listed = timed(lambda: files_by_folder(paths))
            same = "" if each is None else "the same answers" if listed == each else "ANSWERS DIFFER"
            row(name, "folders", len(paths), seconds, same or f"{sum(listed):,} there")
        selected = None
        if wanted("rows"):
            seconds, selected = timed(lambda: rows_each(cache_dir, paths))
            row(name, "rows", len(paths), seconds, f"{sum(r is not None for r in selected):,} rows")
        if wanted("rows-all"):
            seconds, at_once = timed(lambda: rows_at_once(cache_dir, paths, layer.folder))
            same = "" if selected is None else "the same answers" if at_once == selected else "ANSWERS DIFFER"
            row(name, "rows-all", len(paths), seconds, same or f"{sum(r is not None for r in at_once):,} rows")
        if check and wanted("check"):
            before, src.layer.EXISTING = src.layer.EXISTING, versions.existing if by_folder else None
            try:
                seconds, (todo, _) = timed(lambda: layer.to_download(plan.grid, cache_dir, None))
            finally:
                src.layer.EXISTING = before
            row(name, "check", len(paths), seconds,
                f"{len(todo):,} to download, asked {'by folder' if by_folder else 'file by file'}")
        if check and wanted("prune"):
            seconds, older = timed(lambda: dry_prune(layer, cache_dir, tiles))
            row(name, "prune", len(paths), seconds, "no prune" if older < 0 else f"{older:,} older files (kept)")
    return rows


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Times the check of cached tiles before a download's first tile.")
    parser.add_argument("name", help="the area's name in the state folder")
    parser.add_argument("--state-dir", required=True, help="the state folder of the area's download")
    parser.add_argument("--data-dir", required=True, help="the data folder whose cache holds the area's tiles")
    parser.add_argument("--work", required=True, help="a scratch folder for the plan's work files")
    parser.add_argument("--no-check", action="store_true", help="leave out the steps that may adopt files")
    parser.add_argument("--by-folder", action="store_true", help="`check` asks as a pass of area_download does")
    parser.add_argument("--only", action="append", default=[], metavar="STEP",
                        help="only this step of files, folders, rows, rows-all, check, prune (repeatable)")
    parser.add_argument("--allow-index", action="store_true", help="index answers not cached may be asked")
    parser.add_argument("--json", help="write the rows there too")
    args = parser.parse_args(argv)
    state = ad.read_state(args.state_dir, args.name)
    if not state:
        raise SystemExit(f"no state of {args.name} in {args.state_dir}")
    area = ad.Area(args.name, state["area"], state["source"], float(state["resolution"]),
                   os.path.abspath(args.data_dir), os.path.abspath(args.state_dir))
    rows = measure(area, os.path.abspath(args.work), not args.no_check, args.allow_index, args.by_folder, args.only)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump({"area": args.name, "source": area.source, "rows": rows}, f, indent=1)
    return 0


if __name__ == "__main__":
    from progress import utf8_output
    utf8_output()
    sys.exit(main())
