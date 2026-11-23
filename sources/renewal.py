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
   refused writes tnmbucket.failed_path and is not tried again for tnmbucket.FAILED_RETRY_DAYS by any process. The
   new list is made beside the cached one and replaces it only once what left it is decided (_departures): a file
   the index lists now stays in the list ("carried") until the cached answers of every tile its own box meets hold
   its URL (_tiles_met: the API answers a tile by its box, so a tile reached only within a margin may never hold
   it), and only those answers lacking it are asked, each at most once per listing (_settle_carried, on every
   renewal, so a stop after the list was written is made good at the next start; meanwhile an answer's item of a
   file wins over the list's in every tile: versions.keep_item); a file the bucket's listing lacks has its project
   listed again at once and leaves only when that listing lacks it too; a file left out this time without a zone
   keeps its item of before. So at no
   moment, in no process, is a file some cached block was composed from missing from both the list and the answers;
2. every index answer under the grid (cached.index_tiles) asked again (CachedIndex.ask_again: written only when its
   request succeeded and the rule of dropped files lets it through: CachedIndex.confirms_drops; under the tile's
   lock, skipped when it was checked at or after `since`); a failed answer keeps the cached one and prints one line,
   any fault of one tile is that tile's, and after FAILED_IN_A_ROW failures in a row the API counts as down for the
   rest of the start (every later call returns at once with its tiles left: one line), as the layer's renewal does
   after OWN_FAULTS_IN_A_ROW faults of one type that are no request error (a fault of this code: every answer would
   be fetched and thrown away);
3. the cached blocks whose files stay but whose order changes (a file's date or year moved: the index's date in
   place of its upload time) deleted before the answer or the list that changes their order is written
   (ComposedBlocks.reordered; per tile, _reorder_first; for the list, _reorder_list), so a stop at any point leaves
   the change still to be seen or the blocks gone (read again when next needed); a block that cannot be deleted
   keeps the change pending. A block whose set of files or newest year changed has another name and is read again
   anyway (prune deletes the old one).

Nothing fails the caller: it lists and downloads as before with what the index holds then. What it did is returned
(Renewal: answers asked, changed, failed; the list made, kept or failed and why files left it; requests, bytes,
seconds) and told through `say` while it runs (the parts of the listing and the answers as counts, every
PROGRESS_SECONDS), so a listing of minutes never looks like a hang. The callers: tools/area_download.py (the passes
of every start of a row until its renewal went through, `since` the start's time), country.py (after its "Start?"
question, before a cube's first tile), update.py (`cache update`: the list as a check of its own, the answers after
cache.TTL_DAYS["usgs-1m-index"]). A search never renews. The web process never imports this module.
"""

import contextlib
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, List, Optional, Set, Tuple

import requests
from filelock import FileLock, Timeout

import cache
import osm

from . import net
from .indexes.cached import INDEX_MARGIN_DEG, CachedIndex, DroppedFiles, index_tiles, merge_items
from .indexes.versions import ComposedBlocks, moved_items

# How long a renewal waits for another process making the list (a listing takes about 8 minutes at 4 requests at a
# time, 33 one at a time): after that it goes on with the list there is
LIST_LOCK_WAIT_S = 2700
FAILED_IN_A_ROW = 5      # failed answers in a row after which the API counts as down for the rest of the start
# Faults of one type in a row that are no request error (a fault of this code, as in before_store, or of this
# machine) after which a layer's renewal stops for the rest of the start: every answer would be fetched and thrown
# away at every start
OWN_FAULTS_IN_A_ROW = 5
PROGRESS_SECONDS = 30    # between the progress lines of a listing's part and of the answers
RELIST_PAGES = 100       # the bucket's pages for listing again the projects of files a listing lacked

Say = Callable[[str], None]


@dataclass
class Renewal:
    """What a renewal did. list: "made", "kept" (fresh enough, made by another process meanwhile, a failure less than
    a day old, or the wait for another process ended), "failed", or "" (no layer with a list, or the list off)."""
    asked: int = 0     # answers asked and written
    changed: int = 0   # of those, whose listed files changed
    failed: int = 0    # answers whose request failed, or not confirmed, or whose blocks could not be deleted (kept)
    left: int = 0      # answers not asked after FAILED_IN_A_ROW failures in a row (the cached ones kept)
    skipped: int = 0   # answers asked since the renewal's `since` (another renewal, an earlier pass of the start)
    list: str = ""
    departed: int = 0  # files of the list before that the new listing lacked, of which:
    indexed: int = 0   # the index lists them now (carried: those of them kept until their answers hold them)
    carried: int = 0
    gone: int = 0      # the bucket no longer holds them (its project listed again agrees): dropped
    relisted: int = 0  # the bucket's project listed again holds them after all: kept
    zoneless: int = 0  # left out this time without a zone (a header read refused): kept with their item of before
    moved: int = 0     # files staying in the list with another year or date
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
            parts.append(f"{self.skipped:,} asked already since the renewal began")
        if self.list:
            parts.append(f"the list of unlisted files {self.list}")
        if self.departed:
            parts.append(f"{self.departed:,} files left the list ({self.indexed:,} listed by the index now, "
                         f"{self.gone:,} gone from the bucket; {self.relisted + self.zoneless:,} kept)")
        if self.reread:
            parts.append(f"{self.reread:,} blocks to be read again")
        total = self.seconds.get("total", sum(self.seconds.values()))
        return "; ".join(parts) + f" ({sum(self.requests.values()):,} requests, " \
            f"{sum(self.bytes.values()) / 1e6:.1f} MB, {total:.0f} s)"

    def as_dict(self) -> Dict:
        return {"asked": self.asked, "changed": self.changed, "failed": self.failed, "left": self.left,
                "skipped": self.skipped, "list": self.list, "departed": self.departed, "indexed": self.indexed,
                "carried": self.carried, "gone": self.gone, "relisted": self.relisted, "zoneless": self.zoneless,
                "moved": self.moved, "reread": self.reread, "requests": dict(self.requests),
                "bytes": dict(self.bytes), "seconds": dict(self.seconds)}


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


def _tiles_met(item: Dict) -> List[Tuple[float, float]]:
    """The 0.25° index tiles a file's own extent meets (its WGS84 box, no margin): those whose answer holds it, the
    TNM API answering a tile by its own box (every product of the 413 real pages of 2026-11-22 whose box met a
    leaf box by more than 0° came back in that box's answer: 97,733 pairs, none missing)."""
    from rasterio.warp import transform_bounds
    west, south, east, north = transform_bounds(item["crs"], "EPSG:4326", *item["extent"], densify_pts=21)
    return [(lat, lon) for lat, lon in osm.tiles(west, south, east, north)
            if lat < north and lat + osm.TILE_DEG > south and lon < east and lon + osm.TILE_DEG > west]


def _reorder_first(layer, cache_dir: str, lat: float, lon: float, result: Renewal):
    """CachedIndex.ask_again's before_store for one tile: the cached blocks whose files stay but whose order the new
    answer changes (a file's date or year moved: ComposedBlocks.reordered) deleted before the answer is written, so
    a stop at any point leaves either the change unwritten (seen again by the next renewal) or the blocks gone (read
    again when next needed). A block that cannot be deleted (Windows: open in another process) raises: the tile
    fails and its cached answer stays."""
    index: CachedIndex = layer.index
    versions = index.versions

    def before_store(old: Optional[List[Dict]], answer: Dict):
        if old is None or not isinstance(versions, ComposedBlocks):
            return
        extra = index.extra(cache_dir, lat, lon)
        before, after = merge_items(old, extra), merge_items(answer["sheets"], extra)
        moved = moved_items(before, after)
        if not moved:
            return
        blocks = versions.reordered(index, cache_dir, {(lat, lon): before}, moved, {(lat, lon): after})
        for block in blocks:
            cache.forget(cache_dir, [versions.path(cache_dir, block)])
            result.reread += 1
    return before_store


def _ask_answers(layer, cache_dir: str, tiles: List[Tuple[float, float]], since: str, asked: Set[tuple],
                 result: Renewal, say: Say, what: str):
    """The answers of these tiles asked again (those not asked by this renewal yet), counted into result; before each
    answer is written the blocks whose order it changes are deleted (_reorder_first). Any failure of one tile but a
    KeyboardInterrupt (a request, a dropped file not confirmed, a locked database, a block that cannot be deleted)
    is that tile's: its cached answer stays, one line. After FAILED_IN_A_ROW requests in a row that did not reach the
    service (a requests.RequestException; not DroppedFiles, not a fault of this machine: those neither add to the
    streak nor end it) the API counts as down for the rest of the start (("down", its URL) in asked): this and every
    later call for it count their tiles as left at once, one line each."""
    index: CachedIndex = layer.index
    todo = [t for t in tiles if (index.top, index.prefix, t) not in asked]
    down, broken = ("down", index.listing.url), ("broken", index.top, index.prefix)
    if down in asked or broken in asked:
        if todo:
            result.left += len(todo)
            say(f"{layer.description}: " + (f"the index did not answer {FAILED_IN_A_ROW} times in a row"
                                            if down in asked else f"its renewal failed {OWN_FAULTS_IN_A_ROW} times "
                                            f"in a row in the same way") +
                f" in this start: {len(todo):,} answers keep their cached ones ({what})")
        return
    in_a_row, last = 0, time.monotonic()
    own, own_type = 0, None  # faults of one type in a row that are no request error
    for k, (lat, lon) in enumerate(todo):
        asked.add((index.top, index.prefix, (lat, lon)))
        try:
            changed = index.ask_again(cache_dir, lat, lon, since, _reorder_first(layer, cache_dir, lat, lon, result))
        except Exception as e:  # noqa: BLE001 (one tile's fault: the rest of the grid is still asked)
            result.failed += 1
            # Only the service not answering counts toward its being down: a fault of this machine (a block open in
            # another process, a locked database, the tile's lock) or answers that disagree (DroppedFiles: it did
            # answer, twice) neither adds to the streak nor ends it
            if isinstance(e, requests.RequestException) and not isinstance(e, DroppedFiles):
                in_a_row += 1
            if isinstance(e, requests.RequestException):
                own, own_type = 0, None
            else:
                own, own_type = (own + 1 if type(e) is own_type else 1), type(e)
            print(f"{layer.description}: the index answer of {osm.tile_name(lat, lon)} could not be asked again "
                  f"({cache.clean_error(f'{type(e).__name__}: {e}')[:300]}); the cached one is kept", flush=True)
            if own >= OWN_FAULTS_IN_A_ROW:
                asked.add(broken)
                result.left += len(todo) - k - 1
                say(f"{layer.description}: its renewal failed {own} times in a row with {own_type.__name__}: it stops "
                    f"for this start, the other {len(todo) - k - 1:,} answers keep their cached ones")
                break
            if in_a_row >= FAILED_IN_A_ROW:
                asked.add(down)
                if k + 1 < len(todo):
                    result.left += len(todo) - k - 1
                    say(f"{layer.description}: {in_a_row} answers in a row could not be asked again: the other "
                        f"{len(todo) - k - 1:,} keep their cached answers, and so do the later ones of this start")
                break
            continue
        in_a_row, own, own_type = 0, 0, None
        if changed is None:
            result.skipped += 1
        else:
            result.asked += 1
            result.changed += bool(changed)
        if time.monotonic() - last >= PROGRESS_SECONDS:
            last = time.monotonic()
            say(f"  {what}: {k + 1:,} of {len(todo):,} answers, {result.changed:,} changed, {result.failed:,} failed")


def renew_list(layer, cache_dir: str, say: Say = print, result: Optional[Renewal] = None,
               asked: Optional[Set[tuple]] = None, since: Optional[str] = None, force: bool = False,
               allow_drop: bool = False) -> Renewal:
    """Step 1 of renew for one layer (its index has a list: tnm.UnlistedIndex), also `cache update`'s check of the
    list and tools/usa_unlisted.py --cached's. force: made whatever its age (`cache update --all`, the tool); a
    failure less than a day old still waits. allow_drop: make_unlisted's (the tool's --allow-drop).

    The new list is made into a file beside the cached one (make_unlisted(out=)), and what left the list is decided
    before it replaces the cached one (_departures): no moment, in no process, finds a file some cached block was
    composed from in neither the list nor the cached answers it reaches. The blocks whose order the new list changes
    are deleted before it is written (_reorder_list). Then the files the list carries have the answers lacking them
    asked (_settle_carried; also when the list is kept, so a stop after the list was written is made good by the next
    start)."""
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
        _settle_carried(layer, cache_dir, say, result, asked, since)
        return result
    failed = tb.failed_recently(cache_dir, top)
    if failed is not None:
        result.list = "kept"
        say(f"The list of the 1 m files the TNM index does not list is not made again before a day has passed since "
            f"its last try failed ({failed['at']:%Y-%m-%d %H:%M} UTC: {failed['error'][:200]}): the list there is "
            f"is used")
        _settle_carried(layer, cache_dir, say, result, asked, since)
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
    path = tb.unlisted_path(cache_dir, top)
    tmp = f"{path}.new"
    try:
        now_age = tb.unlisted_age_days(cache_dir, top)
        if now_age < age or (not force and now_age <= tb.LIST_MAX_AGE_DAYS):
            tb.forget_unlisted()  # made by another process while this one waited: read it
            result.list = "kept"
            say("The list of the 1 m files the TNM index does not list was made by another process meanwhile: kept")
        elif tb.failed_recently(cache_dir, top) is not None:
            result.list = "kept"
            say(f"The list of the 1 m files the TNM index does not list could not be made by another process "
                f"meanwhile ({tb.failed_recently(cache_dir, top)['error'][:200]}): the list there is is used")
        else:
            _make_list(layer, cache_dir, path, tmp, say, result, allow_drop)
    finally:
        with contextlib.suppress(OSError):
            os.remove(tmp)
        lock.release()
    if result.list != "failed":
        _settle_carried(layer, cache_dir, say, result, asked, since)
    layer.index._listed.clear()
    return result


def _make_list(layer, cache_dir: str, path: str, tmp: str, say: Say, result: Renewal, allow_drop: bool = False):
    """renew_list's listing, under the list's lock: made into tmp, its departures decided, the reordered blocks
    deleted, then written in place of the cached list (atomically) and recorded."""
    from .layers import tnmbucket as tb
    index = layer.index
    top = index.top
    tb.forget_unlisted()  # the list on disk now, not this process's memo of it
    old_tiles = tb.list_tiles(cache_dir, top)  # the list in use until now (a snapshot: it stays as it is)
    old = {item["url"]: item for items in old_tiles.values() for item in items}
    bucket = index.bucket or tb.BUCKET
    started = time.monotonic()
    found: Dict = {}
    try:
        with _Ticker(say) as ticker:
            summary = tb.make_unlisted(cache_dir, out=tmp, bucket=bucket, api=index.listing.url,
                                       dataset=index.listing.dataset, regions=index.regions or tb.REGIONS,
                                       log=say, budgets=ticker.watch, found=found, allow_drop=allow_drop)
        new, _ = tb.read_list(tmp)
        final, carried = _departures(layer, cache_dir, old, new, summary, found, say, result)
        final = _reorder_list(layer, cache_dir, old_tiles, old, final, say, result)
        summary["carried"] = carried
        tb.write_list(path, summary, sorted(final, key=lambda item: item["url"]), bucket, index.listing.url,
                      index.listing.dataset)
    except Exception as e:  # noqa: BLE001 (any failure of the listing: the pass goes on with the list there is)
        tb.write_failed(cache_dir, f"{type(e).__name__}: {e}", top)
        result.list = "failed"
        result.seconds["list"] = round(time.monotonic() - started, 1)
        say(f"The list of the 1 m files the TNM index does not list could not be made "
            f"({cache.clean_error(e)[:300]}): the list there is is used; tried again after "
            f"{tb.FAILED_RETRY_DAYS:g} day")
        return
    cache.record(cache_dir, path, url=bucket)
    with contextlib.suppress(OSError):
        os.remove(tb.refused_path(cache_dir, top))
    tb.clear_failed(cache_dir, top)
    tb.forget_unlisted()
    result.list = "made"
    for part in ("bucket", "index", "headers"):
        result.requests[f"list {part}"] = summary["requests"].get(part, 0)
        result.seconds[f"list {part}"] = summary["seconds_by_part"].get(part, 0.0)
        if part in summary["answer_bytes"]:
            result.bytes[f"list {part}"] = summary["answer_bytes"][part]
    if result.departed:
        say(f"{result.departed:,} files left the list: {result.indexed:,} because the index lists them now "
            f"({result.carried:,} of them kept in the list until the cached answers they reach hold them), "
            f"{result.gone:,} because the bucket no longer holds them; kept: {result.relisted:,} the bucket listed "
            f"again, {result.zoneless:,} whose zone was not found this time")


def _lacking(index, cache_dir: str, item: Dict) -> List[Tuple[float, float]]:
    """The index tiles a file's extent meets (_tiles_met) whose cached answer does not hold its URL (tiles without
    one: none). A tile it reaches only within INDEX_MARGIN_DEG may never hold it (the API answers by the tile's own
    box): counted, the file would be carried for good (the second review's D1)."""
    out = []
    for lat, lon in _tiles_met(item):
        sheets = index._cached_sheets(index.index_path(cache_dir, lat, lon))
        if sheets is not None and item["url"] not in {s["url"] for s in sheets}:
            out.append((lat, lon))
    return out


def _departures(layer, cache_dir: str, old: Dict[str, Dict], new: List[Dict], summary: Dict, found: Dict, say: Say,
                result: Renewal) -> Tuple[List[Dict], List[str]]:
    """The files of the new list and those of the old one that stay in it, and the URLs it carries; why files left
    it (counted in result):
    - the index lists it now (its name among the index's): carried (its old item kept, its URL in the list's
      "carried") while a cached answer of a tile its box meets lacks its URL (_lacking); else dropped;
    - the bucket no longer holds it: its project's folder listed again at once (PageBudget RELIST_PAGES); gone there
      too: dropped (the blocks over it get another key and are read again without it; prune deletes the old ones),
      there after all (a page of the listing missing) or the listing failing: kept with its old item;
    - left out this time without a zone (a header read refused) while the list before had it with one: kept with its
      old item."""
    from .layers import tnmbucket as tb
    from .indexes.s3listing import PageBudget
    index = layer.index
    urls = {item["url"] for item in new}
    departed = [item for url, item in old.items() if url not in urls]
    result.departed += len(departed)
    kept: List[Dict] = []
    gone: List[Dict] = []
    carried: List[str] = []
    for item in departed:
        name = item["url"].rsplit("/", 1)[-1]
        if name in found["listed"]:
            result.indexed += 1
            if _lacking(index, cache_dir, item):
                carried.append(item["url"])
                kept.append(item)
        elif name not in found["bucket"]:
            gone.append(item)
        else:  # in the bucket, not listed: left out (no zone found this time)
            result.zoneless += 1
            kept.append(item)
    if gone:
        projects = sorted({tb.project_of(item["url"]) for item in gone})
        budget = PageBudget("USGS's bucket (1 m DEM), the projects listed again", RELIST_PAGES)
        try:
            there = {obj.key.rsplit("/", 1)[-1] for obj in tb.bucket_files(cache_dir, index.bucket or tb.BUCKET,
                                                                           budget, projects)}
        except Exception as e:  # noqa: BLE001 (not asked: the files stay in the list)
            say(f"The {len(projects):,} projects of {len(gone):,} files the bucket's listing lacked could not be "
                f"listed again ({cache.clean_error(e)[:200]}): the files stay in the list")
            there = {item["url"].rsplit("/", 1)[-1] for item in gone}
        result.requests["list recheck"] = budget.used
        for item in gone:
            if item["url"].rsplit("/", 1)[-1] in there:
                result.relisted += 1
                kept.append(item)
            else:
                result.gone += 1
    result.carried += len(carried)
    return new + kept, carried


def _reorder_list(layer, cache_dir: str, old_tiles: Dict, old: Dict[str, Dict], final: List[Dict], say: Say,
                  result: Renewal) -> List[Dict]:
    """The files that stay in the list with another year or date (C7 of the review: an upload time that changed, a
    year taken from the project's siblings now): the cached blocks whose order of files that changes deleted before
    the list is written. A file whose blocks cannot all be deleted (open in another process) keeps its old item in
    the list (one line): the next listing sees the change again."""
    from .layers import tnmbucket as tb
    index = layer.index
    versions = index.versions
    moved = moved_items(list(old.values()), final)
    if not moved or not isinstance(versions, ComposedBlocks):
        return final
    new_tiles = tb._by_tile(final)
    before, after = {}, {}
    for lat, lon in dict.fromkeys(t for item in moved for t in _tiles_of(item)):
        sheets = index._cached_sheets(index.index_path(cache_dir, lat, lon))
        if sheets is not None:
            key = tb.tile_key(lat, lon)
            before[(lat, lon)] = merge_items(sheets, old_tiles.get(key, []))
            after[(lat, lon)] = merge_items(sheets, new_tiles.get(key, []))
    back = {}
    for item in moved:
        try:
            for block in versions.reordered(index, cache_dir, before, [item], after):
                cache.forget(cache_dir, [versions.path(cache_dir, block)])
                result.reread += 1
        except Exception as e:  # noqa: BLE001 (that file's change waits for the next listing)
            back[item["url"]] = old[item["url"]]
            say(f"The blocks of {item['name']} could not be deleted to be read in their new order "
                f"({cache.clean_error(e)[:200]}): the list keeps its date of before until the next listing")
    result.moved += len(moved) - len(back)
    return [back.get(item["url"], item) for item in final]


def _settle_carried(layer, cache_dir: str, say: Say, result: Renewal, asked: Set[tuple], since: str):
    """The answers that lack a file the list carries (the index lists it now) asked again: only the tiles its extent
    meets whose cached answer lacks its URL, and of those only the ones not asked since the list was made (its row's
    check time), so a file that stays carried for a real reason (an index product that maps to no item) costs at most
    one ask of each lacking tile per listing. A carried file stays in the list (the merge drops it by URL wherever an
    answer holds it, and an answer's item wins over its item in another tile: versions.keep_item); the next listing
    drops it once every cached answer of the tiles it meets holds it."""
    from .layers import tnmbucket as tb
    index = layer.index
    carried = tb.carried_urls(cache_dir, index.top)
    if not carried:
        return
    items = tb.list_items(cache_dir, index.top)
    made = (cache.info(cache_dir, tb.unlisted_path(cache_dir, index.top)) or {}).get("checked_at") or ""

    def unasked(tile) -> bool:
        row = cache.info(cache_dir, index.index_path(cache_dir, *tile))
        return not (made and row and (row.get("checked_at") or "") >= made)
    tiles = [t for t in dict.fromkeys(t for url in carried if url in items for t in _lacking(index, cache_dir,
                                                                                            items[url]))
             if unasked(t)]
    if not tiles:
        return
    failed, mark = result.failed + result.left, time.monotonic()
    listing = layer.index.listing
    sent, received = getattr(listing, "requests", 0), getattr(listing, "bytes", 0)
    _ask_answers(layer, cache_dir, tiles, since, asked, result, say, "the answers over files the index lists since")
    part = "answers over departed files"
    result.seconds[part] = round(result.seconds.get(part, 0) + time.monotonic() - mark, 1)
    result.requests[part] = result.requests.get(part, 0) + getattr(listing, "requests", 0) - sent
    result.bytes[part] = result.bytes.get(part, 0) + getattr(listing, "bytes", 0) - received
    say(f"{len(carried):,} files the index lists since the list was made: the {len(tiles):,} cached answers lacking "
        f"them asked again" + (f"; {result.failed + result.left - failed} could not be (the list keeps those files "
                               f"until they are)" if result.failed + result.left > failed else ""))


def renew(layers: Iterable, grid, cache_dir: str, say: Say = print, asked: Optional[Set[tuple]] = None,
          since: Optional[str] = None) -> Renewal:
    """Bring the index of an area up to date for the layers that renew (the module's docstring); the others are
    left alone. asked: the (top, prefix, tile) of the answers a caller's renewal asked already (several plans of one
    start share it). since (cache.now_iso's form; now unless given): an answer checked at or after it is not asked
    (CachedIndex.ask_again), so a download row's later passes of one start, given the start's time
    (tools/area_download.py), ask only the answers that start has not yet asked successfully. Returns what it did;
    nothing raises for a failed request."""
    result = Renewal()
    layers = renewing(layers)
    if not layers:
        return result
    asked = set() if asked is None else asked
    since = since or cache.now_iso()
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
        _ask_answers(layer, cache_dir, tiles, since, asked, result, say, f"the index of {layer.description}")
        layer.index._listed.clear()  # what tiles() found before the renewal
    result.seconds["answers"] = round(time.monotonic() - mark, 1)
    departed = "answers over departed files"  # counted apart by _settle_carried
    result.requests["answers"] = sum(getattr(listing, "requests", 0) - n for listing, n, _ in listings.values()) \
        - result.requests.get(departed, 0)
    result.bytes["answers"] = sum(getattr(listing, "bytes", 0) - b for listing, _, b in listings.values()) \
        - result.bytes.get(departed, 0)
    result.seconds["total"] = round(time.monotonic() - started, 1)
    say(f"Index renewed: {result.text()}")
    return result
