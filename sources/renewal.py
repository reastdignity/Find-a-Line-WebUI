"""The renewal of an area's index (wave A of the USA, part A-2): what makes a file USGS publishes after an index
answer was cached reach the cache.

An index answer (sources/indexes/cached.py) is cached per 0.25° tile and a search never asks it again, so a new
project of The National Map would stay unseen. renew(layers, grid, cache_dir) brings the index of an area up to
date, for every layer that renews (`renews`: the TNM datasets, tnm.TnmBlocks: the 1 m DEM, Alaska's IfSAR, later
OPR); any other layer is left alone, without a request:

1. the list of the bucket's 1 m files the TNM index does not list (sources/layers/tnmbucket.py), for a layer whose
   index has one (tnm.UnlistedIndex): made when the cached list is missing or older than
   tnmbucket.LIST_MAX_AGE_DAYS (28; the copy shipped with the code does not count). One process of the machine makes
   it at a time (a lock file under cache/locks/renewal, LIST_LOCK_WAIT_S at most; a second renewal waits for the first
   and then finds the list made, or after the wait goes on with the list there is). A listing that fails or is
   refused writes tnmbucket.failed_path and is not tried again for tnmbucket.FAILED_RETRY_DAYS by any process. A file
   that left the list (the index lists it now) would vanish from every cached answer that does not list it yet, so
   the cached answers of the tiles it reaches are asked again right away, wherever they are;
2. every index answer under the grid (cached.index_tiles) asked again (CachedIndex.ask_again: written only when its
   request succeeded, under the tile's lock, skipped when another renewal asked it since this one started); a failed
   answer keeps the cached one and prints one line, and after FAILED_IN_A_ROW failures in a row the rest keep theirs
   (the service is down: one line, no hours of retries);
3. the cached blocks whose files stayed but whose order changed (a file's date or year changed: the index's date in
   place of its upload time) deleted (ComposedBlocks.reordered), so they are read again when next needed; a block
   whose set of files or newest year changed has another name and is read again anyway (prune deletes the old one).

Nothing fails the caller: it lists and downloads as before with what the index holds then. What it did is returned
(Renewal: answers asked, changed, failed; the list made, kept or failed; requests, bytes, seconds) and told through
`say` while it runs (the parts of the listing and the answers as counts, every PROGRESS_SECONDS), so a listing of
minutes never looks like a hang. The callers: tools/area_download.py (the first pass of every start of a row),
country.py (before a cube's first tile), update.py (`cache update`: the list as a check of its own, the answers after
cache.TTL_DAYS["usgs-1m-index"]). A search never renews. The web process never imports this module.
"""

import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, List, Optional, Set, Tuple

import requests
from filelock import FileLock, Timeout

import cache
import osm

from . import net
from .indexes.cached import INDEX_MARGIN_DEG, CachedIndex, index_tiles, merge_items
from .indexes.versions import ComposedBlocks, moved_items

# How long a renewal waits for another process making the list (a listing takes about 8 minutes at 4 requests at a
# time, 33 one at a time): after that it goes on with the list there is
LIST_LOCK_WAIT_S = 2700
FAILED_IN_A_ROW = 5      # failed answers in a row after which the rest of the area keeps its cached answers
PROGRESS_SECONDS = 30    # between the progress lines of a listing's part and of the answers

Say = Callable[[str], None]


@dataclass
class Renewal:
    """What a renewal did. list: "made", "kept" (fresh enough, made by another process meanwhile, a failure less than
    a day old, or the wait for another process ended), "failed", or "" (no layer with a list, or the list off)."""
    asked: int = 0     # answers asked and written
    changed: int = 0   # of those, whose listed files changed
    failed: int = 0    # answers whose request failed (the cached one kept)
    left: int = 0      # answers not asked after FAILED_IN_A_ROW failures in a row (the cached ones kept)
    skipped: int = 0   # answers another renewal asked meanwhile
    list: str = ""
    departed: int = 0  # files that left the list (the index lists them now)
    reread: int = 0    # cached blocks deleted to be read again (the order of their files changed)
    requests: Dict[str, int] = field(default_factory=dict)  # by part: bucket, index, headers (the list), answers
    bytes: Dict[str, int] = field(default_factory=dict)
    seconds: Dict[str, float] = field(default_factory=dict)

    def text(self) -> str:
        """The renewal in a line."""
        parts = [f"{self.asked:,} index answers asked again, {self.changed:,} changed"]
        if self.failed or self.left:
            parts.append(f"{self.failed + self.left:,} kept as cached (failed)")
        if self.skipped:
            parts.append(f"{self.skipped:,} asked by another process meanwhile")
        if self.list:
            parts.append(f"the list of unlisted files {self.list}")
        if self.departed:
            parts.append(f"{self.departed:,} files left the list")
        if self.reread:
            parts.append(f"{self.reread:,} blocks to be read again")
        total = self.seconds.get("total", sum(self.seconds.values()))
        return "; ".join(parts) + f" ({sum(self.requests.values()):,} requests, " \
            f"{sum(self.bytes.values()) / 1e6:.1f} MB, {total:.0f} s)"

    def as_dict(self) -> Dict:
        return {"asked": self.asked, "changed": self.changed, "failed": self.failed, "left": self.left,
                "skipped": self.skipped, "list": self.list, "departed": self.departed, "reread": self.reread,
                "requests": dict(self.requests), "bytes": dict(self.bytes), "seconds": dict(self.seconds)}


def renewing(layers: Iterable) -> List:
    """The layers a renewal asks again (each once), in their order."""
    found = {}
    for layer in layers:
        if layer is not None and getattr(layer, "renews", False):
            found.setdefault(id(layer), layer)
    return list(found.values())


class _Ticker:
    """Every PROGRESS_SECONDS while a listing runs, its parts' requests so far through say."""

    def __init__(self, say: Say):
        self.say, self.budgets = say, {}
        self.quit = threading.Event()
        self.thread = threading.Thread(target=self._beat, daemon=True, name="renewal-ticker")

    def watch(self, budgets: Dict):
        self.budgets = budgets

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.quit.set()
        self.thread.join()

    def _beat(self):
        while not self.quit.wait(PROGRESS_SECONDS):
            b = self.budgets
            if b:
                self.say(f"  listing: {b['bucket'].used:,} requests to the bucket, {b['index'].used:,} to the index, "
                         f"{b['headers'].used:,} header reads so far")


def _tiles_of(item: Dict) -> List[Tuple[float, float]]:
    """The 0.25° index tiles a file's extent reaches (its WGS84 box grown by INDEX_MARGIN_DEG, as the list's)."""
    from rasterio.warp import transform_bounds
    west, south, east, north = transform_bounds(item["crs"], "EPSG:4326", *item["extent"], densify_pts=21)
    m = INDEX_MARGIN_DEG
    return osm.tiles(west - m, south - m, east + m, north + m)


def _ask(layer, cache_dir: str, tiles: List[Tuple[float, float]], since: str, asked: Set[tuple], result: Renewal,
         say: Say, what: str, before: Optional[Dict[Tuple[float, float], List[Dict]]] = None) -> List[Dict]:
    """The answers of these tiles asked again (those not asked by this renewal yet), counted into result, and the
    cached blocks over the files whose date or year moved, whose order changed, deleted (_reread). before: each
    tile's merged items before, as the caller knows them (the list of before); else read here before each
    request. Returns the moved files."""
    index: CachedIndex = layer.index
    todo = [t for t in tiles if (index.top, index.prefix, t) not in asked]
    kept: Dict[Tuple[float, float], List[Dict]] = {}
    moved: Dict[str, Dict] = {}
    in_a_row, last = 0, time.monotonic()
    for k, (lat, lon) in enumerate(todo):
        asked.add((index.top, index.prefix, (lat, lon)))
        was = before.get((lat, lon)) if before is not None else index.cached_items(cache_dir, lat, lon)
        try:
            changed = index.ask_again(cache_dir, lat, lon, since)
        except (requests.RequestException, OSError, ValueError, RuntimeError) as e:  # RuntimeError: the tile's lock
            result.failed += 1
            in_a_row += 1
            print(f"{layer.description}: the index answer of {osm.tile_name(lat, lon)} could not be asked again "
                  f"({cache.clean_error(e)[:300]}); the cached one is kept", flush=True)
            if in_a_row >= FAILED_IN_A_ROW and k + 1 < len(todo):
                result.left += len(todo) - k - 1
                say(f"{layer.description}: {in_a_row} answers in a row could not be asked again: the other "
                    f"{len(todo) - k - 1:,} keep their cached answers")
                break
            continue
        in_a_row = 0
        if changed is None:
            result.skipped += 1
        else:
            result.asked += 1
            result.changed += bool(changed)
            if was is not None:
                now = moved_items(was, index.cached_items(cache_dir, lat, lon) or [])
                if now:
                    kept[(lat, lon)] = was
                    for item in now:
                        moved[item["url"]] = item
        if time.monotonic() - last >= PROGRESS_SECONDS:
            last = time.monotonic()
            say(f"  {what}: {k + 1:,} of {len(todo):,} answers, {result.changed:,} changed, {result.failed:,} failed")
    _reread(layer, cache_dir, kept, list(moved.values()), result)
    return list(moved.values())


def _reread(layer, cache_dir: str, before: Dict[Tuple[float, float], List[Dict]], moved: List[Dict],
            result: Renewal):
    """The cached blocks over moved files whose order changed, deleted (read again when next needed)."""
    versions = layer.index.versions
    if not moved or not isinstance(versions, ComposedBlocks):
        return
    blocks = versions.reordered(layer.index, cache_dir, before, moved)
    cache.forget(cache_dir, [versions.path(cache_dir, b) for b in blocks])
    result.reread += len(blocks)


def renew_list(layer, cache_dir: str, say: Say = print, result: Optional[Renewal] = None,
               asked: Optional[Set[tuple]] = None, since: Optional[str] = None, force: bool = False) -> Renewal:
    """Step 1 of renew for one layer (its index has a list: tnm.UnlistedIndex), also `cache update`'s check of the
    list. force: made whatever its age (`cache update --all`); a failure less than a day old still waits."""
    from .layers import tnmbucket as tb
    result = Renewal() if result is None else result
    asked = set() if asked is None else asked
    since = since or cache.now_iso()
    index = layer.index
    top = index.top
    if tb.renew_off():
        return result
    age = tb.unlisted_age_days(cache_dir, top)
    if age <= tb.LIST_MAX_AGE_DAYS and not force:
        tb.forget_unlisted()  # made by another process minutes ago: read it, not this process's memo
        result.list = "kept"
        say(f"The list of the 1 m files the TNM index does not list is {age:.0f} days old: kept (made again after "
            f"{tb.LIST_MAX_AGE_DAYS:g} days)")
        return result
    failed = tb.failed_recently(cache_dir, top)
    if failed is not None:
        result.list = "kept"
        say(f"The list of the 1 m files the TNM index does not list is not made again before a day has passed since "
            f"its last try failed ({failed['at']:%Y-%m-%d %H:%M} UTC: {failed['error'][:200]}): the list there is "
            f"is used")
        return result
    lock = FileLock(f"{net._locks(cache_dir, 'renewal')}/{top}-bucket1m.lock")
    try:
        try:
            lock.acquire(blocking=False)
        except Timeout:  # said at once: a row waiting minutes for another's listing must not look hung
            say(f"Another process is making the list of the 1 m files the TNM index does not list: waiting for it "
                f"(at most {LIST_LOCK_WAIT_S // 60} min)")
            lock.acquire(timeout=LIST_LOCK_WAIT_S)
    except Timeout:
        result.list = "kept"
        say(f"Another process is making the list of the 1 m files the TNM index does not list (waited "
            f"{LIST_LOCK_WAIT_S // 60} min): the list there is is used")
        return result
    try:
        now_age = tb.unlisted_age_days(cache_dir, top)
        if now_age < age or (not force and now_age <= tb.LIST_MAX_AGE_DAYS):
            tb.forget_unlisted()  # made by another process while this one waited: read it
            result.list = "kept"
            say("The list of the 1 m files the TNM index does not list was made by another process meanwhile: kept")
            return result
        failed = tb.failed_recently(cache_dir, top)
        if failed is not None:
            result.list = "kept"
            say(f"The list of the 1 m files the TNM index does not list could not be made by another process "
                f"meanwhile ({failed['error'][:200]}): the list there is is used")
            return result
        old_tiles = tb.list_tiles(cache_dir, top)  # the list in use until now (a snapshot: it stays as it is)
        old = {item["url"]: item for items in old_tiles.values() for item in items}
        started = time.monotonic()
        try:
            with _Ticker(say) as ticker:
                summary = tb.make_unlisted(cache_dir, bucket=index.bucket or tb.BUCKET, api=index.listing.url,
                                           dataset=index.listing.dataset, regions=index.regions or tb.REGIONS,
                                           log=say, budgets=ticker.watch)
        except Exception as e:  # noqa: BLE001 (any failure of the listing: the pass goes on with the list there is)
            tb.write_failed(cache_dir, f"{type(e).__name__}: {e}", top)
            result.list = "failed"
            result.seconds["list"] = round(time.monotonic() - started, 1)
            say(f"The list of the 1 m files the TNM index does not list could not be made "
                f"({cache.clean_error(e)[:300]}): the list there is is used; tried again after "
                f"{tb.FAILED_RETRY_DAYS:g} day")
            return result
        tb.clear_failed(cache_dir, top)
        result.list = "made"
        for part in ("bucket", "index", "headers"):
            result.requests[f"list {part}"] = summary["requests"].get(part, 0)
            result.seconds[f"list {part}"] = summary["seconds_by_part"].get(part, 0.0)
            if part in summary["answer_bytes"]:
                result.bytes[f"list {part}"] = summary["answer_bytes"][part]
    finally:
        lock.release()
    new = tb.list_items(cache_dir, top)
    departed = [item for url, item in old.items() if url not in new]
    result.departed += len(departed)
    if departed:
        tiles = list(dict.fromkeys(t for item in departed for t in _tiles_of(item)))
        before = {}
        for lat, lon in tiles:  # their items of before: the cached answer with the list of before
            sheets = index._cached_sheets(index.index_path(cache_dir, lat, lon))
            if sheets is not None:  # an answer never cached is asked by whatever needs it, with the new list
                before[(lat, lon)] = merge_items(sheets, old_tiles.get(tb.tile_key(lat, lon), []))
        failed_before, mark = result.failed + result.left, time.monotonic()
        _ask(layer, cache_dir, list(before), since, asked, result, say, "the answers over the files that left the list",
             before)
        result.seconds["answers over departed files"] = round(time.monotonic() - mark, 1)
        say(f"{len(departed):,} files left the list (the index lists them now): the cached answers of the "
            f"{len(tiles):,} index tiles they reach asked again"
            + (f"; {result.failed + result.left - failed_before} could not be (those files are missing there until "
               f"the next renewal)" if result.failed + result.left > failed_before else ""))
    layer.index._listed.clear()
    return result


def renew(layers: Iterable, grid, cache_dir: str, say: Say = print, asked: Optional[Set[tuple]] = None) -> Renewal:
    """Bring the index of an area up to date for the layers that renew (the module's docstring); the others are
    left alone. asked: the (top, prefix, tile) of the answers a caller's renewal asked already (several plans of one
    start share it). Returns what it did; nothing raises for a failed request."""
    result = Renewal()
    layers = renewing(layers)
    if not layers:
        return result
    asked = set() if asked is None else asked
    since = cache.now_iso()
    listings = {id(layer): (layer.index.listing, getattr(layer.index.listing, "requests", 0),
                            getattr(layer.index.listing, "bytes", 0)) for layer in layers}
    started = time.monotonic()
    for layer in layers:
        if getattr(layer.index, "has_list", False):
            renew_list(layer, cache_dir, say, result, asked, since)
    mark = time.monotonic()
    tiles = index_tiles(grid)
    for layer in layers:
        say(f"Asking the index of {layer.description} again: {len(tiles):,} answers")
        _ask(layer, cache_dir, tiles, since, asked, result, say, f"the index of {layer.description}")
        layer.index._listed.clear()  # what tiles() found before the renewal
    result.seconds["answers"] = round(time.monotonic() - mark, 1)
    result.requests["answers"] = sum(getattr(listing, "requests", 0) - n for listing, n, _ in listings.values())
    result.bytes["answers"] = sum(getattr(listing, "bytes", 0) - b for listing, _, b in listings.values())
    result.seconds["total"] = round(time.monotonic() - started, 1)
    say(f"Index renewed: {result.text()}")
    return result
