"""
Cache commands of findaline.py: what is cached, and updating it; the probe of the sources.

    python findaline.py cache status [FOLDER]
    python findaline.py cache update [FOLDER] [--all] [--bbox S,W,N,E | --point LAT,LON]
    python findaline.py cache migrate [FOLDER] [--dry-run]
    python findaline.py osm download REGION
    python findaline.py osm update [REGION]
    python findaline.py sources check [ID ...] [--deep]   (sources/probe.py)

Nothing is updated during a search unless it is asked for (--update stale|all of a
search checks the data of its area). How each kind of data is checked:

    never        versioned releases (Copernicus 2021, FABDEM v1-2, NASADEM, Malta 2012/2018)
    after TTL    tiles of services that serve the current state (IGN Spain, the orthophoto
                 WMS of geoportal.gov.pl and IGN) and OSM theme tiles from Overpass: downloaded
                 again; the same content only changes the check time
    sheet index  geoportal.gov.pl: the index is asked again; newer surveys of the cached sheets
                 are downloaded and the older files deleted (the USA's 1 m DEM after 28 days, the
                 list of the files its index does not list checked first: sources/renewal.py)
    newer file   OSM water polygons of the world (regenerated daily: checked after a year,
                 downloaded again when the server's file is newer than the folder's date)
    diffs        Geofabrik OSM extracts (osmextract.py); theme tiles built from them follow

`migrate` writes the cached elevation tiles that are still in the older encoding (deflate, or a provider's
file as it came) again as LERC_ZSTD, the cache's encoding now (sources.layer.reencode); a search does it for
the tiles it reads, this does the rest at once, to free the disk space. It is safe to repeat; tiles another
process has open (Windows) are left and make the exit code 1.

`status` ends with the saved runs computed on data that has changed since (changed_runs), one line each: for
a run whose run.json holds the data record (its `identity` keys: each file's sha256 as the index held it, the
coastline, the area's inputs, local files) exactly, against the index now; files written again in another
encoding (`cache migrate`: another checksum, fetched no later than the run read them) apart; an older run by
fetch times, marked approximate. That part only reads; the rest of `status` still writes as before (it adopts
the world water polygons' files, and cache.rows opens each index for writing).

The intervals are cache.TTL_DAYS; "missing" tiles of data that can change are checked
again after cache.MISSING_TTL_DAYS. `update` without --all checks only what is older
than its interval (stale); --all checks everything that can change.
"""

import argparse
import glob
import hashlib
import json
import os
import sqlite3
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from functools import lru_cache
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional, Tuple

import requests

import cache
import coast
import orthophoto
import osm
import osmextract
import settings
import sources as src
from progress import progress
from sources.layer import old_encoding, reencode

THREADS = 4
MIGRATE_THREADS = 8  # tiles converted at a time (LERC encoding is CPU work done outside the GIL)


@dataclass
class Check:
    """One file (or set of files) an update would check."""
    what: str                     # kind of data, for the listing
    path: str                     # in the cache, relative
    extent: Optional[Tuple[float, float, float, float]]  # (west, south, east, north); None: everywhere
    action: Callable[[], object]  # True: changed (otherwise a new fetch time of the file tells)
    parallel: bool = True
    first: bool = False           # checked before the others (the list of the USA's unlisted 1 m files)


@lru_cache(maxsize=None)
def _live_layers() -> List[src.Layer]:
    layers = {id(layer): layer for s in src.SOURCES.values() for layer in (s.nmt, s.nmpt)
              if layer is not None and layer.ttl_days is not None}
    return list(layers.values())


@lru_cache(maxsize=None)
def _sheet_layers() -> List[src.IndexedTiles]:
    layers = {id(layer): layer for s in src.SOURCES.values() for layer in (s.nmt, s.nmpt)
              if isinstance(layer, src.IndexedTiles)}
    return list(layers.values())


@lru_cache(maxsize=None)
def _ortho_services() -> List[src.OrthoService]:
    return list({s.ortho.folder: s.ortho for s in src.SOURCES.values()
                 if s.ortho is not None and s.ortho.ttl_days is not None}.values())


def _tile_extent(name: str) -> Tuple[float, float, float, float]:
    lat, lon = osmextract._tile_corner(name)
    return lon, lat, lon + osm.TILE_DEG, lat + osm.TILE_DEG


def _check(cache_dir: str, row: Dict, update: str) -> Optional[Check]:
    """The check of an index row, or None if it is not due (or its data never changes)."""
    path, full = row["path"], os.path.join(cache_dir, row["path"])
    for layer in _live_layers():
        tile = layer.tile_of(path)
        if tile is not None:
            if not cache.stale(row, layer.ttl_days, update):
                return None
            return Check(layer.description, path, layer.bounds_wgs84(tile),
                         lambda: layer._download_and_record(tile, cache_dir))
    for layer in _sheet_layers():
        top = layer.folder.split("/")[0]
        if path.startswith(f"{top}/sheet-index/{layer.prefix}/"):
            ttl = getattr(layer, "update_ttl_days", None) or getattr(layer.index, "ttl_days",
                                                                     cache.TTL_DAYS["sheet-index"])
            if not cache.stale(row, ttl, update):
                return None
            name = os.path.basename(path)[:-len(".json")]
            lat, lon = osmextract._tile_corner(name)
            return Check(f"{layer.description}: sheet index", path, _tile_extent(name),
                         lambda: _sheets(layer, cache_dir, lat, lon), parallel=False)
    for service in _ortho_services():
        tile = orthophoto.tile_of(path) if path.startswith(service.folder + "/wm256/") else None
        if tile is not None:
            if not cache.stale(row, service.ttl_days, update):
                return None

            def ortho(service=service, tile=tile):
                orthophoto._download_tile(service, *tile, full)
                cache.record(cache_dir, full, url=service.url or service.base_url)
            return Check(service.name, path, orthophoto.bounds_wgs84(*tile), ortho)
    parts = path.split("/")
    if parts[:2] == ["osm", "themes"] and len(parts) == 4:
        if osm.from_extract(row) or not cache.stale(row, cache.TTL_DAYS["osm-theme"], update):
            return None
        lat, lon = osmextract._tile_corner(parts[3][:-len(".geojson")])
        return Check(f"OSM {parts[2]} tiles (Overpass)", path, _tile_extent(parts[3][:-len(".geojson")]),
                     lambda: osm.fetch_tile(parts[2], lat, lon, cache_dir), parallel=False)
    if parts[:2] == ["osm", "water-polygons"] and path.endswith(".shp"):
        if not cache.stale(row, cache.TTL_DAYS["water-polygons"], update):
            return None
        return Check("OSM water polygons (world)", path, None,
                     lambda: coast.world_polygons(cache_dir, update), parallel=False)
    if len(parts) == 3 and parts[1] == "osm-extract" and path.endswith(".osm.pbf"):
        if not cache.stale(row, cache.TTL_DAYS["osm-extract"], update):
            return None
        rid = parts[2][:-len(".osm.pbf")]
        outline = full[:-len(".osm.pbf")] + ".geojson"
        extent = osmextract._load(outline).bounds if os.path.exists(outline) else None
        return Check(f"OSM extract {rid}", path, extent, lambda: osmextract.update(cache_dir, rid, full),
                     parallel=False)
    return None


def _sheets(layer: src.IndexedTiles, cache_dir: str, lat: float, lon: float) -> bool:
    new, mb, deleted = layer.update_index_tile(cache_dir, lat, lon)
    if new:
        print(f"  {osm.tile_name(lat, lon)}: {new} newer sheets ({mb:.0f} MB), {deleted} older deleted")
    return new > 0


@lru_cache(maxsize=None)
def _layers_with_folders() -> List[src.Layer]:
    layers = {id(layer): layer for s in src.SOURCES.values() for layer in (s.nmt, s.nmpt) if layer is not None}
    layers[id(src.WATER_MASK)] = src.WATER_MASK
    return [layer for layer in layers.values() if getattr(layer, "folder", "")]


def rewriting_layer(path: str) -> Optional[src.Layer]:
    """The layer with `rewrites` that caches the file at path (relative to the cache, with /), or None: a file of
    another layer, of a layer whose files are not ours to rewrite (the Slovak mirror's copies) or of no layer. The
    layers whose folder holds the path; of several the one whose tile_of knows the path, then the deepest folder."""
    inside = [layer for layer in _layers_with_folders() if path.startswith(layer.folder.rstrip("/") + "/")]
    if len(inside) > 1:
        known = [layer for layer in inside if layer.tile_of(path) is not None]
        inside = known or inside
    layer = max(inside, key=lambda layer: len(layer.folder), default=None)
    return layer if layer is not None and layer.rewrites else None


def old_tiles(cache_dir: str, folder: Optional[str] = None) -> Dict[str, List[str]]:
    """The cached files still in the old encoding (sources.layer.old_encoding) of the layers that rewrite their
    tiles, by top-level folder, full paths (only the folders that have some)."""
    candidates: Dict[str, List[str]] = {}
    for top in _tops(cache_dir, folder):
        paths = [os.path.join(cache_dir, row["path"]) for row in cache.rows(cache_dir, top)
                 if row["status"] == "ok" and rewriting_layer(row["path"]) is not None]
        if paths:
            candidates[top] = paths
    found = {}
    with ThreadPoolExecutor(max_workers=MIGRATE_THREADS) as pool:
        for top, paths in candidates.items():
            old = [p for p, is_old in zip(paths, pool.map(old_encoding, paths)) if is_old]
            if old:
                found[top] = old
    return found


def migrate(cache_dir: str, folder: Optional[str] = None, dry_run: bool = False) -> int:
    """Write the old-encoded tiles of the cache again (sources.layer.reencode), each top-level folder with its tiles
    and GB before and after. Returns the number of tiles left because another process has them open (dry_run:
    only counts what would be converted, returns 0)."""
    found = old_tiles(cache_dir, folder)
    if not found:
        print("Nothing to migrate: every cached tile of ours is in the current encoding")
        return 0
    left = 0
    for top, paths in found.items():
        was = {p: os.path.getsize(p) for p in paths}
        if dry_run:
            print(f"{top}: {len(paths)} tiles, {sum(was.values()) / 1e9:.2f} GB to convert")
            continue
        now: Dict[str, int] = {}

        def convert(path):
            done = reencode(cache_dir, path)
            if done:
                now[path] = os.path.getsize(path)
            progress.download.update(1)
            return done
        progress.download.start(f"re-encoding {top}", len(paths), unit="tile")
        with ThreadPoolExecutor(max_workers=MIGRATE_THREADS) as pool:
            list(pool.map(convert, paths))
            # still old: held open by another process (not those another process converted meanwhile)
            skipped = sum(pool.map(old_encoding, [p for p in paths if p not in now]))
        progress.download.finish(f"{len(now)} converted")
        left += skipped
        print(f"{top}: {len(now)} of {len(paths)} tiles converted, {sum(was.values()) / 1e9:.2f} GB -> "
              f"{(sum(was.values()) - sum(was[p] - n for p, n in now.items())) / 1e9:.2f} GB"
              + (f", {skipped} left (open elsewhere)" if skipped else ""))
    return left


def _tops(cache_dir: str, folder: Optional[str]) -> List[str]:
    found = sorted(d for d in os.listdir(cache_dir) if os.path.isdir(os.path.join(cache_dir, d))
                   and d != cache.LOCKS) if os.path.isdir(cache_dir) else []
    if folder:
        if folder not in found:
            raise SystemExit(f"No folder {folder} in {cache_dir} (there are: {', '.join(found) or 'none'})")
        return [folder]
    return found


def _adopt_world(cache_dir: str):
    """Index the files of a world water polygons folder that was put there by hand."""
    shapefile = coast.world_file(cache_dir)
    if shapefile:
        for path in glob.glob(os.path.join(os.path.dirname(os.path.dirname(shapefile)), "**", "*"), recursive=True):
            if os.path.isfile(path):
                cache.state(cache_dir, path)


def _list_check(cache_dir: str, layer: src.IndexedTiles, rows: List[Dict], update: str) -> Optional[Check]:
    """The check of a layer's list of the files its index does not list (the USA's 1 m DEM: tnmbucket), or None when
    it is not due: made again after tnmbucket.LIST_MAX_AGE_DAYS (--all: now), or when none was made yet while
    answers of the layer are cached (the copy shipped with the code does not count). Checked before the answers
    (Check.first), so they are read with the new list; a file that left it has the answers it reaches asked again
    at once (sources/renewal.py renew_list)."""
    from sources.layers import tnmbucket as tb
    top = layer.index.top
    path = tb.unlisted_path(cache_dir, top)
    relative = cache.relative(cache_dir, path)
    row = next((r for r in rows if r["path"] == relative), None)
    if row is None:
        prefix = f"{top}/sheet-index/{layer.prefix}/"
        if not any(r["path"].startswith(prefix) for r in rows):
            return None
    elif not cache.stale(row, tb.LIST_MAX_AGE_DAYS, update):
        return None

    def make() -> bool:
        from sources import renewal
        done = renewal.renew_list(layer, cache_dir, print, force=update == "all")
        if done.list == "failed":
            raise RuntimeError("the list could not be made (the line above says why); the list there is is used")
        return done.list == "made"
    return Check(f"{layer.description}: the list of the files its index does not list", relative, None, make,
                 parallel=False, first=True)


def checks(cache_dir: str, folder: Optional[str] = None, update: str = "stale",
           bbox: Optional[Tuple[float, float, float, float]] = None) -> List[Check]:
    """What an update would check; bbox (west, south, east, north) limits it to a place. The lists of the files an
    index does not list come first (Check.first); with a bbox a list is checked only when an answer of its layer
    in that place is."""
    _adopt_world(cache_dir)
    found = []
    for top in _tops(cache_dir, folder):
        rows = cache.rows(cache_dir, top)
        for row in rows:
            check = _check(cache_dir, row, update)
            if check is None:
                continue
            if bbox and check.extent:
                w, s, e, n = check.extent
                if w > bbox[2] or e < bbox[0] or s > bbox[3] or n < bbox[1]:
                    continue
            found.append(check)
        for layer in _sheet_layers():
            if not getattr(layer.index, "has_list", False) or layer.index.top != top:
                continue
            prefix = f"{top}/sheet-index/{layer.prefix}/"
            if bbox and not any(c.path.startswith(prefix) for c in found):
                continue
            check = _list_check(cache_dir, layer, rows, update)
            if check is not None and check.path not in {c.path for c in found}:
                found.append(check)
    return sorted(found, key=lambda c: not c.first)  # stable: the order of before otherwise


def run_update(cache_dir: str, folder: Optional[str] = None, update: str = "stale",
               bbox: Optional[Tuple[float, float, float, float]] = None) -> int:
    """Check and update; returns the number of failed checks (each is reported, none stops the rest)."""
    todo = checks(cache_dir, folder, update, bbox)
    if not todo:
        print("Nothing to check" + (" (everything was checked recently; --all checks it anyway)"
                                    if update == "stale" else ""))
        return 0
    groups: Dict[str, List[Check]] = {}
    for check in todo:
        groups.setdefault(check.what, []).append(check)
    failed = 0
    for what, group in groups.items():
        before = {c.path: (cache.info(cache_dir, os.path.join(cache_dir, c.path)) or {}).get("fetched_at")
                  for c in group}
        print(f"{what}: {len(group)} to check")
        errors = []
        progress.download.start(what, len(group), unit="file")

        reported = set()

        def run(check):
            try:
                if check.action() is True:
                    reported.add(check.path)
            except (RuntimeError, OSError, ValueError, requests.RequestException) as e:
                errors.append(f"{check.path}: {cache.clean_error(e)}")
            progress.download.update(1, failed=len(errors))
        if group[0].parallel:
            with ThreadPoolExecutor(max_workers=THREADS) as pool:
                for future in as_completed([pool.submit(run, c) for c in group]):
                    future.result()
        else:
            for check in group:
                run(check)
        changed = sum(p in reported or (cache.info(cache_dir, os.path.join(cache_dir, p)) or {}).get("fetched_at")
                      != fetched for p, fetched in before.items())
        progress.download.finish(f"{changed} changed")
        print(f"  {changed} of {len(group)} changed" + (f", {len(errors)} failed (e.g. {errors[0][:200]})"
                                                       if errors else ""))
        failed += len(errors)
    return failed


def _size(folder: str) -> int:
    total = 0
    for root, _, files in os.walk(folder):
        total += sum(os.path.getsize(os.path.join(root, f)) for f in files)
    return total


def _date(timestamp: Optional[str]) -> str:
    return timestamp[:10] if timestamp else "-"


NOMINATIM_TABLES = ("search", "reverse", "places")  # the tables of osm.MIGRATIONS (nominatim.sqlite)
NOMINATIM_TIMEOUT = 5  # s a read of nominatim.sqlite waits for a writer's lock (then its answers are not known)
_IN_CHUNK = 500  # paths asked of an index in one query
NOT_READ = "its run.json cannot be read (not checked)"


@dataclass
class RunChange:
    """What changed under one saved run's data since it was made (changed_runs). files/changed/reencoded/unknown
    count the files of its data layers (run.json's `data` entries with `paths`); notes say the rest in words: the
    coastline, the search area's inputs, local files, a resumed search's sessions."""
    name: str                  # the run's folder
    files: int = 0
    changed: int = 0           # gone, its index row gone, or other content fetched after the run read it
    reencoded: int = 0         # other content fetched no later than the run read it: written again (cache migrate)
    unknown: int = 0           # no checksum on one side (a file adopted by hand): neither changed nor the same
    approximate: bool = False  # a run made before the data record: today's rule by fetch times (_approximate)
    notes: List[str] = field(default_factory=list)
    unreadable: bool = False   # its run.json cannot be read, or not judged (an error): named, never left out

    def listed(self) -> bool:
        """Whether status names the run: a file changed or re-encoded, another input changed, or its run.json
        unreadable (a run with only files "not known" is not named)."""
        return bool(self.unreadable or self.changed or self.reencoded or self.notes)

    def line(self) -> str:
        """The run's line of `cache status`, in words a user can act on."""
        if self.unreadable:
            return f"{self.name}: {NOT_READ}"
        parts = []
        if self.changed or self.reencoded or (self.unknown and not self.approximate):
            files = f"{self.changed} of {self.files} file{'' if self.files == 1 else 's'} changed"
            files += f", {self.reencoded} re-encoded" if self.reencoded else ""
            parts.append(files + (f", {self.unknown} not known" if self.unknown else ""))
        parts += self.notes or []
        return f"{self.name}: {'; '.join(parts)}" + (" (approximate: a run made before the data record)"
                                                     if self.approximate else "")


def _uri(db_path: str, mode: str) -> str:
    """An SQLite URI of a file: a drive path as file:///C:/..., a network path (\\\\server\\share\\...) as
    file:////server/share/... (pathlib's file://server/share/... is refused by SQLite: "invalid uri authority"), a
    Linux path as file:///...; "%", "?", "#", spaces and letters outside ASCII percent-encoded (UTF-8)."""
    path = os.path.abspath(db_path).replace("\\", "/")
    quoted = urllib.parse.quote(path, safe="/:")
    return f"file:{'//' if path.startswith('/') else '///'}{quoted}?{mode}"  # /x on Linux, //server/.. or C:/..


def _read_only(db_path: str, mode: Optional[str] = None, timeout: float = 60) -> Optional[sqlite3.Connection]:
    """A connection to an existing SQLite file that writes nothing beside it, or None when there is no file. A
    read-only open of a WAL database leaves its -shm and -wal files behind, so a WAL database (the indexes: the
    file's header says it) without a -wal file, which then holds everything, is read as immutable (no lock, no side
    file); one with a -wal file (another connection has it open, rows may still be in the WAL) and a database of a
    rollback journal (nominatim.sqlite) read-only, which reads the WAL and waits for a writer's lock. The one case
    where a read leaves a file: a -wal left by a killed writer without its -shm (SQLite makes the -shm)."""
    if not os.path.isfile(db_path):
        return None
    if mode is None:
        with open(db_path, "rb") as f:
            header = f.read(20)
        wal = len(header) == 20 and header[18] == 2
        mode = "immutable=1" if wal and not os.path.exists(db_path + "-wal") else "mode=ro"
    return sqlite3.connect(_uri(db_path, mode), uri=True, timeout=timeout)


def _query(db_path: str, ask: Callable[[sqlite3.Connection], Dict], timeout: float = 60) -> Dict:
    """ask(connection) on _read_only(db_path); {} without the file or without the table asked (an index made and
    never written). An immutable read that fails (a checkpoint of another process writing into the file while it
    was read; the checkpoint at a writer's close removes the -wal too) is read once more read-only; a read that
    fails again is raised (as cache.rows, earlier in `status`, raises it). What an immutable read cannot see: a
    commit made in the instant between the look for a -wal file and the read, still in the WAL; the next `cache
    status` sees it."""
    db = _read_only(db_path, timeout=timeout)
    for attempt in range(2):
        if db is None:
            return {}
        try:
            return ask(db)
        except sqlite3.DatabaseError as e:
            if str(e).startswith("no such table"):
                return {}
            if attempt == 1:
                raise
        finally:
            db.close()
        db = _read_only(db_path, "mode=ro", timeout)
    return {}


def _index_rows(cache_dir: str, paths: List[str]) -> Dict[str, Tuple]:
    """The index rows of paths (relative to the cache, with /): path -> (status, fetched_at, sha256); a path
    without a row is left out. One read-only connection per top-level folder, never one per file; a folder or an
    index that is not there is not made."""
    by_top: Dict[str, List[str]] = {}
    for path in dict.fromkeys(paths):
        top, _, inner = path.partition("/")
        by_top.setdefault(top, []).append(inner)
    found: Dict[str, Tuple] = {}
    for top, inners in by_top.items():
        def ask(db, top=top, inners=inners):
            rows = {}
            for k in range(0, len(inners), _IN_CHUNK):
                chunk = inners[k:k + _IN_CHUNK]
                rows.update({f"{top}/{p}": (status, fetched, sha) for p, status, fetched, sha in db.execute(
                    f"SELECT path, status, fetched_at, sha256 FROM files WHERE path IN ({','.join('?' * len(chunk))})",
                    chunk)})
            return rows
        found.update(_query(os.path.join(cache_dir, top, "index.sqlite"), ask))
    return found


def _nominatim_answers(cache_dir: str, asked: List[Tuple[str, str]]) -> Optional[Dict[Tuple[str, str], str]]:
    """The sha256 of each stored Nominatim answer (table, query) -> hex of its text as UTF-8; a row gone is left
    out. Read-only, never through osm._nominatim_db (which creates and migrates the file). None when the file
    cannot be read (a hot journal left by a killed writer, a writer's lock held over NOMINATIM_TIMEOUT, no
    database): the answers are then not known."""
    wanted = sorted(set(asked))

    def ask(db):
        found = {}
        for table, query in wanted:
            row = db.execute(f"SELECT answer FROM {table} WHERE query = ?", (query,)).fetchone()
            if row is not None and isinstance(row[0], str):
                found[(table, query)] = hashlib.sha256(row[0].encode("utf-8")).hexdigest()
        return found
    if not wanted:
        return {}
    try:
        return _query(os.path.join(cache_dir, "osm", "nominatim.sqlite"), ask, NOMINATIM_TIMEOUT)
    except sqlite3.Error:
        return None


def _time(text) -> Optional[datetime]:
    """A stored time in UTC (one without an offset as local time, as cache.utc_iso), None if it is none."""
    try:
        return datetime.fromisoformat(text).astimezone(timezone.utc) if isinstance(text, str) and text else None
    except ValueError:
        return None


def _later(fetched: Optional[str], moment: Optional[datetime]) -> bool:
    fetched = _time(fetched)
    return fetched is not None and moment is not None and fetched > moment


def _read_at(entry: Dict, created: Optional[datetime]) -> Optional[datetime]:
    """The time by which a run had read an entry's files: no content fetched later can be what it read. The
    entry's `fetched.newest` (cache.touch, in the lookup that gave the checksums: no file of the entry had a later
    fetch time then), or the run's `created` if earlier (a tiled run sets it before its first tile; a one-grid run
    when it saves), or the one of the two there is; None without both."""
    fetched = entry.get("fetched") if isinstance(entry.get("fetched"), dict) else {}
    times = [t for t in (_time(fetched.get("newest")), created) if t is not None]
    return min(times, default=None)


def _file_state(cache_dir: str, path: str, recorded, row: Optional[Tuple], read_at: Optional[datetime]) -> str:
    """"changed", "reencoded", "unknown" or "same" for one file a run with the data record read (path relative
    to the cache, recorded: the checksum its run.json holds). Gone, or its row gone or not "ok": changed, whatever
    was recorded. A checksum missing on either side: not known. Another checksum: re-encoded when the row's fetch
    time is not later than read_at (_read_at: cache.reencoded keeps the fetch time, `cache migrate`, a search's
    reencode, tools/sk_tiles.py), changed when it is later (cache.record_many gives new content the fetch time of
    now) or when either time is missing: never re-encoded for want of a time."""
    if row is None or row[0] != "ok" or not os.path.isfile(os.path.join(cache_dir, path)):
        return "changed"
    if not isinstance(recorded, str) or not recorded or not row[2]:
        return "unknown"
    if recorded == row[2]:
        return "same"
    fetched = _time(row[1])
    return "reencoded" if fetched is not None and read_at is not None and fetched <= read_at else "changed"


def _strings(values) -> List[str]:
    return [v for v in values if isinstance(v, str)] if isinstance(values, list) else []


def _parallel(paths, sums) -> List[Tuple[str, Optional[str]]]:
    """(path, recorded checksum) pairs; checksums that are not a list as long as the paths are none."""
    if not isinstance(paths, list):
        return []
    sums = sums if isinstance(sums, list) and len(sums) == len(paths) else [None] * len(paths)
    return [(p, s) for p, s in zip(paths, sums) if isinstance(p, str)]


def _local_file(path, identity) -> Optional[str]:
    """"missing", "may have changed" or None (the same size and modification time, nothing recorded, or a path
    that is not absolute: a --slope-file given relative to a folder cannot be found from another) for a local file
    (--elevation-file, --surface-file, --slope-file): a size or a time that differs is not proof."""
    if not isinstance(path, str) or not os.path.isabs(path) or not isinstance(identity, dict) or "size" not in identity:
        return None
    try:
        st = os.stat(path)
    except OSError:
        return "missing"
    modified = datetime.fromtimestamp(st.st_mtime, timezone.utc).isoformat(timespec="seconds")
    return None if (st.st_size, modified) == (identity.get("size"), identity.get("modified")) else "may have changed"


def _entries(meta: Dict) -> List[Dict]:
    return [e for e in meta.get("data") if isinstance(e, dict)] if isinstance(meta.get("data"), list) else []


def _identity(owner) -> Dict:
    return owner.get("identity") if isinstance(owner, dict) and isinstance(owner.get("identity"), dict) else {}


def _approximate(cache_dir: str, meta: Dict, rows: Dict[str, Tuple], change: RunChange,
                 created: Optional[datetime]):
    """A run made before the data record (no `identity` in its run.json): a file counts as changed when it or its
    row is gone or the row's fetch time is later than the run (the rule before the record; wrong both ways: a file
    a command-line tiled run downloaded itself counts, a file replaced with an older fetch time does not)."""
    for entry in _entries(meta):
        for path in _strings(entry.get("paths")):
            change.files += 1
            row = rows.get(path)
            if row is None or not os.path.exists(os.path.join(cache_dir, path)) or _later(row[1], created):
                change.changed += 1


def _tiles_note(what: str, pairs, rows, cache_dir) -> Optional[str]:
    """OSM tiles (never re-encoded): another checksum is a change whatever the times."""
    states = [_file_state(cache_dir, p, s, rows.get(p), None) for p, s in pairs]
    changed = sum(state in ("changed", "reencoded") for state in states)
    return f"{what}: {changed} of {len(states)} OSM tile{'' if len(states) == 1 else 's'} changed" if changed else None


def _asked(identity: Dict) -> List[Dict]:
    """The Nominatim items of an area's record that can be looked up: a known table, a query that is text."""
    items = identity.get("nominatim") if isinstance(identity.get("nominatim"), list) else []
    return [a for a in items if isinstance(a, dict) and a.get("table") in NOMINATIM_TABLES
            and isinstance(a.get("query"), str)]


def _exact(cache_dir: str, meta: Dict, rows: Dict[str, Tuple], answers: Optional[Dict], newest: Optional[str],
           change: RunChange, created: Optional[datetime]):
    """A run with the data record (contract of wave 4: run.json's `identity` keys): each file by its checksum,
    the coastline by its world file's edition (newest: the edition in the cache now) or its tiles, the area's OSM
    tiles and Nominatim's answers (answers None: not readable), local files by size and modification time, a
    resumed search's mark."""
    for entry in _entries(meta):
        identity = _identity(entry)
        if entry.get("paths"):
            read_at = _read_at(entry, created)
            for path, recorded in _parallel(entry["paths"], identity.get("sha256")):
                change.files += 1
                state = _file_state(cache_dir, path, recorded, rows.get(path), read_at)
                if state != "same":
                    setattr(change, state, getattr(change, state) + 1)
        elif isinstance(identity.get("edition"), str):
            if newest is None:
                change.notes.append("coastline: the world file is gone")
            elif newest != identity["edition"]:
                change.notes.append("coastline: newer edition" if newest > identity["edition"]
                                    else "coastline: another edition")
        elif identity.get("paths"):
            note = _tiles_note("coastline", _parallel(identity["paths"], identity.get("sha256")), rows, cache_dir)
            change.notes += [note] if note else []
        elif entry.get("file"):
            state = _local_file(entry["file"], identity)
            if state:
                layer = entry.get("layer") if isinstance(entry.get("layer"), str) and entry.get("layer") else "local file"
                change.notes.append(f"{layer.lower()} {state}")
    identity = _identity(meta.get("area"))
    note = _tiles_note("area", _parallel(identity.get("paths"), identity.get("sha256")), rows, cache_dir)
    change.notes += [note] if note else []
    asked = [a for a in _asked(identity) if isinstance(a.get("sha256"), str) and a["sha256"]]
    if asked and answers is None:
        change.notes.append("area: the place name answers could not be read")
    elif asked:
        differ = sum(answers.get((a["table"], a["query"])) != a["sha256"] for a in asked)
        if differ:
            change.notes.append(f"area: {differ} of {len(asked)} place name "
                                f"answer{'' if len(asked) == 1 else 's'} changed")
    top = _identity(meta)
    params = meta.get("params") if isinstance(meta.get("params"), dict) else {}
    state = _local_file(params.get("slope_file"), top.get("slope_file"))
    change.notes += [f"slope file {state}"] if state else []
    if top.get("mixed") is True:
        change.notes.append("its sessions read different data (a resumed search)")


def _recorded(meta: Dict) -> bool:
    """Whether a run.json holds the data record (made after it was added): an `identity` key at its top level or
    in a data entry."""
    return isinstance(meta.get("identity"), dict) or any(_identity(entry) for entry in _entries(meta))


def _wanted(meta: Dict) -> Tuple[List[str], List[Tuple[str, str]]]:
    """The cached files a run's checks ask the index about, and its Nominatim answers (table, query)."""
    paths = []
    for entry in _entries(meta):
        paths += _strings(entry.get("paths")) + _strings(_identity(entry).get("paths"))
    identity = _identity(meta.get("area"))
    paths += _strings(identity.get("paths"))
    return paths, [(a["table"], a["query"]) for a in _asked(identity)]


def _read_runs(runs_dir: str) -> List[Tuple[str, Optional[Dict]]]:
    """(folder, run.json as an object, or None when it cannot be read or is no object), in the folders' order;
    folders starting with "_" or "." are no runs (runs.list_runs' rule)."""
    found = []
    for path in sorted(glob.glob(os.path.join(runs_dir, "*", "run.json"))):
        name = os.path.basename(os.path.dirname(path))
        if name.startswith((".", "_")):
            continue
        try:
            with open(path, encoding="utf-8") as f:
                meta = json.load(f)
        except (OSError, ValueError):
            meta = None
        found.append((name, meta if isinstance(meta, dict) else None))
    return found


def changed_runs(cache_dir: str, runs_dir: str) -> List[RunChange]:
    """The saved runs computed on data that has changed since, in the order of their folders (RunChange.listed).
    Exact for a run with the data record (_exact: the checksums the search noted against the index's now); a run
    made before it by fetch times, marked approximate (_approximate); a run whose run.json cannot be read, or that
    cannot be judged (an error), named as not checked, never left out. Reads only: every index and Nominatim's
    answers with one read-only connection per file for all the runs (_index_rows), no folder, index or table is
    made (the one file a read can leave: _read_only)."""
    runs, paths, asked = [], [], []
    for name, meta in _read_runs(runs_dir):
        try:
            wanted = _wanted(meta) if meta is not None else ([], [])
        except Exception:  # a shape nobody foresaw: this run is not checked, the others are
            meta, wanted = None, ([], [])
        runs.append((name, meta))
        paths += wanted[0]
        asked += wanted[1]
    rows = _index_rows(cache_dir, paths)
    answers = _nominatim_answers(cache_dir, asked)
    newest = coast.world_file(cache_dir)
    newest = os.path.basename(os.path.dirname(os.path.dirname(newest))) if newest else None
    found = []
    for name, meta in runs:
        change = RunChange(name, unreadable=meta is None)
        if meta is not None:
            try:
                created = _time(meta.get("created"))
                change.approximate = not _recorded(meta)
                if change.approximate:
                    _approximate(cache_dir, meta, rows, change, created)
                else:
                    _exact(cache_dir, meta, rows, answers, newest, change, created)
            except Exception:  # a shape nobody foresaw: this run is named as not checked, the listing goes on
                change = RunChange(name, unreadable=True)
        if change.listed():
            found.append(change)
    return found


def status(cache_dir: str, runs_dir: str, folder: Optional[str] = None):
    """Print the cached folders, what an update would check and the runs on changed data."""
    tops = _tops(cache_dir, folder)
    _adopt_world(cache_dir)
    print(f"Cache: {cache_dir}")
    print(f"{'Folder':<14} {'Size':>9} {'Files':>7}  {'Fetched':<23}  {'Last used':<10}  To check (stale)")
    for top in tops:
        rows = cache.rows(cache_dir, top)
        fetched = [r["fetched_at"] for r in rows if r["fetched_at"]]
        used = max((r["last_used_at"] for r in rows if r["last_used_at"]), default=None)
        due: Dict[str, int] = {}
        for row in rows:
            check = _check(cache_dir, row, "stale")
            if check:
                due[check.what] = due.get(check.what, 0) + 1
        span = f"{_date(min(fetched, default=None))} - {_date(max(fetched, default=None))}"
        print(f"{top:<14} {_size(os.path.join(cache_dir, top)) / 1e9:>7.2f}GB {len(rows):>7}  {span:<23}  "
              f"{_date(used):<10}  " + ("; ".join(f"{w}: {n}" for w, n in due.items()) or "-"))
    lists = {layer.index.top: layer for layer in _sheet_layers()
             if getattr(layer.index, "has_list", False) and layer.index.top in tops}
    for top, layer in lists.items():
        from sources.layers import tnmbucket as tb
        print(f"\n{layer.description}, the list of the files its index does not list: {tb.list_status(cache_dir, top)}")
    found = [(rid, pbf) for rid, pbf in osmextract.extracts(cache_dir)
             if not folder or cache.relative(cache_dir, pbf).startswith(folder + "/")]
    if found:
        print("\nOSM extracts:")
        for rid, pbf in found:
            row = cache.info(cache_dir, pbf) or {}
            print(f"  {rid}: {os.path.getsize(pbf) / 1e9:.2f} GB, data of {(row.get('source_date') or '?')[:16]}, "
                  f"checked {_date(row.get('checked_at'))}")
    old = old_tiles(cache_dir, folder)
    if old:
        count = sum(len(paths) for paths in old.values())
        gigabytes = sum(os.path.getsize(p) for paths in old.values() for p in paths) / 1e9
        print(f"\nTiles in the older encoding: {count} ({gigabytes:.2f} GB; {', '.join(old)}). A search writes the "
              f"ones it reads again; `findaline.py cache migrate` does all of them.")
    runs = changed_runs(cache_dir, runs_dir)
    if runs:
        print("\nRuns computed on data that has changed since (run them again to use the new data):")
        for change in runs:
            print(f"  {change.line()}")
    print("\n`findaline.py cache update` checks what is stale; delete a folder to free its space "
          "(it is downloaded again when needed).")


def _box(text: str) -> Tuple[float, float, float, float]:
    """--bbox S,W,N,E or --point LAT,LON as (west, south, east, north)."""
    values = [float(v) for v in text.split(",")]
    if len(values) == 2:
        return values[1], values[0], values[1], values[0]
    south, west, north, east = values
    return west, south, east, north


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(prog="findaline.py", description="Cache, OpenStreetMap and source commands.")
    parser.add_argument("--data-dir", help="data folder (default: FINDALINE_DATA or the folder of the scripts)")
    commands = parser.add_subparsers(dest="group", required=True)
    cache_cmd = commands.add_parser("cache", help="what is cached, and updating it")
    cache_sub = cache_cmd.add_subparsers(dest="command", required=True)
    st = cache_sub.add_parser("status", help="folders, sizes, what is stale, runs on changed data")
    st.add_argument("folder", nargs="?", help="one top-level folder (e.g. poland, osm)")
    up = cache_sub.add_parser("update", help="check the stale data again (--all: everything that can change)")
    up.add_argument("folder", nargs="?", help="one top-level folder (e.g. poland, osm)")
    up.add_argument("--all", action="store_true", help="check everything that can change, however recent")
    place = up.add_mutually_exclusive_group()
    place.add_argument("--bbox", help="only data over S,W,N,E (WGS84)")
    place.add_argument("--point", help="only data at LAT,LON (WGS84)")
    mg = cache_sub.add_parser("migrate", help="write the cached tiles in the older encoding again as LERC_ZSTD "
                                              "(saves disk space; a search does it for the tiles it reads)")
    mg.add_argument("folder", nargs="?", help="one top-level folder (e.g. poland, switzerland)")
    mg.add_argument("--dry-run", action="store_true", help="only count what would be converted")
    osm_cmd = commands.add_parser("osm", help="OpenStreetMap extracts from Geofabrik")
    osm_sub = osm_cmd.add_subparsers(dest="command", required=True)
    dl = osm_sub.add_parser("download", help="download the extract of a country or region (e.g. poland, malta); "
                                             "the theme tiles (coastline, cliffs) are then built from it")
    dl.add_argument("region", help="Geofabrik id or name, see https://download.geofabrik.de")
    ou = osm_sub.add_parser("update", help="apply the daily diffs to the downloaded extracts")
    ou.add_argument("region", nargs="?", help="only this extract")
    sources_cmd = commands.add_parser("sources", help="the data sources")
    sources_sub = sources_cmd.add_subparsers(dest="command", required=True)
    sc = sources_sub.add_parser("check", help="whether the services of the sources still answer (a few small "
                                              "requests each; nothing is written to the cache)")
    sc.add_argument("ids", nargs="*", metavar="ID", help="only these sources (nasadem only when named)")
    sc.add_argument("--deep", action="store_true", help="also download the first tile of every layer")
    for sub in (st, up, mg, dl, ou, sc):
        sub.add_argument("--data-dir", default=argparse.SUPPRESS, help="data folder")
    args = parser.parse_args(argv)

    data = cache.data_dir(args.data_dir)
    cache_dir = os.path.join(data, "cache")
    cache.check_layout(cache_dir)
    try:
        with progress.bars():
            if args.group == "cache" and args.command == "status":
                status(cache_dir, os.path.join(data, "runs"), args.folder)
            elif args.group == "cache" and args.command == "migrate":
                return 1 if migrate(cache_dir, args.folder, args.dry_run) else 0
            elif args.group == "cache":
                where = args.bbox or args.point
                return 1 if run_update(cache_dir, args.folder, "all" if args.all else "stale",
                                       _box(where) if where else None) else 0
            elif args.group == "sources":
                from sources import probe
                return probe.run(cache_dir, args.ids, args.deep, settings.opentopography_key())
            elif args.command == "download":
                osmextract.download(cache_dir, args.region)
            else:
                found = [(rid, pbf) for rid, pbf in osmextract.extracts(cache_dir)
                         if not args.region or rid == args.region]
                if not found:
                    raise SystemExit("No such extract downloaded (`findaline.py osm download REGION`)"
                                     if args.region else "No extracts downloaded (`findaline.py osm download REGION`)")
                for rid, pbf in found:
                    osmextract.update(cache_dir, rid, pbf)
    except (ValueError, RuntimeError, requests.RequestException) as e:
        raise SystemExit(f"Failed: {cache.clean_error(e)}")
    return 0
