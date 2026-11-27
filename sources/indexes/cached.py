"""CachedIndex: the answers of an index service cached per 0.25° tile, and a policy for the versions they list."""

import json
import math
import os
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np
import requests
from rasterio.warp import transform_bounds

import cache
import osm
from grid import Grid

from ..net import _part, tile_lock
from ..composed import Index


# The margin, in degrees, around an area's outline and around each 0.25° tile in the test of which
# tiles an index must answer for it (index_tiles): the outline's edges are straight in the grid's
# CRS and only their vertices are projected, so in degrees the projected outline sags from the true
# edge; 0.01° (about 1 km) covers that for any edge of a search area, and a file listed in a tile
# only touching the outline is found either way
INDEX_MARGIN_DEG = 0.01


def index_tiles(grid: Grid) -> List[Tuple[float, float]]:
    """The 0.25° tiles (south-west corners, in osm.tiles' order) an index must answer for a grid.
    Without an outline (a circle) the tiles of the grid's box, as before. With one (grid.area_shape,
    an area), the tiles of the grid's box under the outline only: for each part of it
    (shapely.get_parts: the islands of a country, the pieces of a coast) the tiles of the part's own
    box grown by INDEX_MARGIN_DEG that are tiles of the grid's box, kept where the tile's box grown by
    the margin intersects the outline. The grid's box matters for a grid smaller than its outline (a
    tile of the country layer carries the whole country's): from 2026-11-08 to 11-11 such a grid asked
    the index for every tile under the whole outline, and the versions kept only the files over the
    grid's box anyway.

    This gives the same files as the whole box did, with far fewer requests: a versions policy keeps
    only the files under the outline (NewestPerSheet, ShaPerTile: a listed extent intersecting it;
    ComposedBlocks: the blocks under it), and such a file meets the outline at some point, which lies
    in a tile that intersects the outline, so that tile is asked and the file is in its answer (a
    listing answers every file reaching into its tile). The USA's outline (with Alaska) spans 680 152
    tiles of which 99.9 % hold no land of it: an area download asked one a second for days; now the
    tiles along and inside the coast only. A part whose longitudes span more than 180° crosses the
    antimeridian (its projected coordinates wrap): it takes the tiles of the grid's box in its own
    latitude band, as osm.tiles gives them for a box with west > east.
    """
    west, south, east, north = transform_bounds(grid.crs, "EPSG:4326", *grid.bounds)
    if grid.area_shape is None:
        return osm.tiles(west, south, east, north)
    import shapely
    from area import project
    shape = project(grid.area_shape, grid.crs, "EPSG:4326")
    shapely.prepare(shape)
    margin, size = INDEX_MARGIN_DEG, osm.TILE_DEG
    # The grid's box in tile numbers, as osm.tiles counts them: rows, and one or (across 180°) two runs of columns
    rows = math.floor(south / size), math.floor(north / size)
    columns = ([(math.floor(west / size), math.floor(east / size))] if west <= east else
               [(math.floor(west / size), math.floor((180 - size) / size)),
                (math.floor(-180 / size), math.floor(east / size))])
    found = set()
    for part in shapely.get_parts(shape):
        p_west, p_south, p_east, p_north = part.bounds
        if p_east - p_west > 180:  # across 180°
            corners = osm.tiles(west, max(south, p_south - margin), east, min(north, p_north + margin))
        else:  # osm.tiles of the part's grown box, those of the grid's box only
            r0 = max(math.floor((p_south - margin) / size), rows[0])
            r1 = min(math.floor((p_north + margin) / size), rows[1])
            c0, c1 = math.floor((p_west - margin) / size), math.floor((p_east + margin) / size)
            lons = [c for first, last in columns for c in range(max(c0, first), min(c1, last) + 1)]
            corners = [(r * size, c * size) for r in range(r0, r1 + 1) for c in lons]
        if not corners:
            continue
        lats = np.array([lat for lat, _ in corners])
        lons = np.array([lon for _, lon in corners])
        boxes = shapely.box(lons - margin, lats - margin, lons + osm.TILE_DEG + margin, lats + osm.TILE_DEG + margin)
        found.update(corner for corner, hit in zip(corners, shapely.intersects(shape, boxes)) if hit)
    return sorted(found)


EXTRA = "_extra"  # the mark of a version merged in from extra (copies; never in a cached answer or the list)


def _name(url: str) -> str:
    return url.rsplit("/", 1)[-1]  # a file's identity between the index and the list (versions.url_name)


def merge_items(items: List[Dict], extra: List[Dict]) -> List[Dict]:
    """A tile's listed versions with the extra versions added (tnm.UnlistedIndex) whose file name they do not hold
    (the same file at another URL is the same file: the list itself goes by name, tnmbucket.unlisted_objects), each
    added one a marked copy (EXTRA): where the versions of several tiles are joined, a version an index answer lists
    wins over an extra one of the same file from another tile (versions.keep_item), and an extra file tied on its
    year enters its block's key with its date (versions.block_key)."""
    if not extra:
        return items
    listed = {_name(item["url"]) for item in items}
    return items + [dict(item, **{EXTRA: True}) for item in extra if _name(item["url"]) not in listed]


class IndexUnavailable(requests.RequestException):
    """An index service cannot be asked (offline, down, an error answer). A RequestException,
    so the cached files are used (CachedIndex.tiles) and `cache update` lists it as an error;
    for listings whose client is not requests (see docs/sources-architecture.md)."""


class DroppedFiles(IndexUnavailable):
    """A fresh answer dropped files the cached answer held and the drop was not confirmed (CachedIndex._fetch): the
    cached answer stays. As such: the two fresh answers disagree, or the check of a dropped file failed (no answer
    of the bucket); DroppedStillThere: a decision of the index (a renewal counts it as asked)."""


class DroppedStillThere(DroppedFiles):
    """The two fresh answers agree in dropping a file that still exists at its URL (the index wrong, or delisting a
    file the bucket keeps): the cached answer stays, and a renewal counts the answer as asked (the user's answer of
    2026-11-23); the next listing takes the file into the list."""


# The dropped files of one tile an index checks at their URL at most (CachedIndex.check_gone, a small request each,
# in the order of their URLs): this many gone in a row take the drop of all of them, however many (a real removal of
# any size passes); the first that still answers or whose check fails keeps the cached answer, so a bad answer of
# the index (its files still there) costs one check. A project's 10 km files over a 0.25° tile are about 12
CHECK_GONE_MAX = 25


class Listing:
    """Asks an index service what it lists in one 0.25° tile."""
    url = ""  # the index's address, recorded with each cached answer

    def fetch(self, lat: float, lon: float) -> Dict:
        """Every usable version listed in the tile whose south-west corner is (lat, lon), as
        cached: {"sheets": [{...}, ...]} (and anything else the listing keeps). Raises a
        requests.RequestException when the service cannot be asked."""
        raise NotImplementedError


class Versions:
    """Which of the listed versions a grid uses, how their files are named in the cache, and
    which older ones are deleted. `index` is the CachedIndex asking (its answers)."""

    def query(self, index: "CachedIndex", grid: Grid, cache_dir: str, update: Optional[str]) -> list:
        """The tiles over a grid, in the order of their use (the first wins)."""
        raise NotImplementedError

    def path(self, cache_dir: str, tile) -> str:
        raise NotImplementedError

    def request(self, tile):
        """What the reader needs to fetch a tile."""
        return tile

    def cached(self, grid: Grid, cache_dir: str) -> list:
        """The cached tiles over a grid, in the order of their use (the index cannot be reached)."""
        raise NotImplementedError

    def prune(self, cache_dir: str, tiles: list) -> int:
        """Delete the cached older versions of the tiles that are cached; how many."""
        raise NotImplementedError

    def update_tile(self, index: "CachedIndex", cache_dir: str, lat: float, lon: float) -> Tuple[list, list]:
        """After the index of one 0.25° tile was asked again: the tiles to download, and those
        whose older versions are deleted then."""
        raise NotImplementedError

    def has_data_near(self, index: "CachedIndex", lat: float, lon: float, cache_dir: str) -> Optional[bool]:
        return None


class CachedIndex(Index):
    """The answers of an index service (listing), cached per 0.25° tile (osm.tiles) in
    <top>/sheet-index/<prefix>/<tile>.json with every listed version and its extent, so a
    search in a known place asks the index nothing; the versions policy chooses among them.
    Without the index (offline) and without its cached answer, the cached files over the
    area are used (tiles() gives None). The answers are asked again after their TTL
    (ttl_days: "sheet-index" unless the index publishes more often) or with an update.

    tiles() gets only the grid: use() gives it the cache folder and the update mode first.

    confirms_drops (the indexes of layers that renew, tnm.TnmBlocks: set per instance): an answer that replaces a cached
    one is checked for dropped files (_fetch): file names (the URL's last part: a file the index lists at another URL is
    the same file; also for Alaska's IfSAR, which has no list: the uniqueness of its names rests on the 8 recorded
    items, the 1 m DEM's on 126,767 names at as many URLs) the cached answer holds that neither the fresh answer nor the
    tile's extra versions (the bucket's unlisted files) hold. Nothing dropped: it is written (an empty answer as such is
    never refused: most tiles hold nothing). Something dropped: asked once more; a second answer that drops nothing is
    written. Else, with check_gone (the 1 m DEM's: tnmbucket.file_gone, a small request per file), it is written only
    when the two answers agree and the dropped files are gone at their URLs (a real removal, taken at once): checked in
    the order of their URLs until the first that is not gone, at most CHECK_GONE_MAX of them, that many gone in a row
    taking the drop of all. A dropped file that still answers (the index wrong, or delisting a file the bucket keeps) or
    a check that fails keeps the cached answer (DroppedFiles), until the next listing of the bucket puts such a file
    into the list (then nothing is dropped: at most 28 days, `cache update --all` at once). What slips through: more
    than CHECK_GONE_MAX dropped, the first CHECK_GONE_MAX by URL gone, a later one delisted but kept in the bucket: that
    file is out of the tile until the next listing takes it into the list (at most 28 days). Without check_gone
    (Alaska's IfSAR: no list) two agreeing answers are taken, so nothing stays refused for good. Every path that
    replaces a cached answer goes through it: answers() with an update (a search's --update: a refused tile is one
    printed line and its cached answer is read, the rest of the grid is still asked), ask_again (sources/renewal.py: the
    tile fails; one dropping a file that still exists, DroppedStillThere, counts as asked), fresh_answer
    (ComposedBlocks.update_tile, `cache update`: the tile fails). Off, an answer is fetched and written as before.
    """
    confirms_drops = False
    check_gone: Optional[Callable[[str], Optional[bool]]] = None  # url -> gone (True), there (False), not known

    def __init__(self, description: str, listing: Listing, versions: Versions, prefix: str, top: str,
                 ttl_days: Optional[float] = None):
        self.description, self.listing, self.versions, self.prefix, self.top = \
            description, listing, versions, prefix, top
        self.ttl_days = cache.TTL_DAYS["sheet-index"] if ttl_days is None else ttl_days
        self._listed: Dict[tuple, list] = {}
        self.cache_dir: Optional[str] = None  # set by use() (tiles() does not get it)
        self.update: Optional[str] = None

    def use(self, cache_dir: str, update: Optional[str] = None):
        """What tiles() needs (it gets only the grid)."""
        self.cache_dir, self.update = cache_dir, update

    def index_path(self, cache_dir: str, lat: float, lon: float) -> str:
        """The cached index answer of one 0.25° tile."""
        return os.path.join(cache_dir, self.top, "sheet-index", self.prefix, f"{osm.tile_name(lat, lon)}.json")

    def answers(self, cache_dir: str, lat: float, lon: float, update: Optional[str] = None) -> List[Dict]:
        """The versions listed in one tile, asking the index when not cached or stale."""
        path = self.index_path(cache_dir, lat, lon)
        due = lambda: cache.due(cache_dir, path, update=update, ttl=self.ttl_days)  # noqa: E731
        if due():
            with tile_lock(cache_dir, path):  # another search may be asking for it now
                if due():
                    old = self._cached_sheets(path) if self.confirms_drops else None
                    try:
                        self._store(cache_dir, path, self._fetch(cache_dir, lat, lon, old))
                    except DroppedFiles as e:  # only with a cached answer: it is read, the grid's other tiles asked
                        print(f"{self.description}: {e}", flush=True)
        with open(path, encoding="utf-8") as f:
            return json.load(f)["sheets"]

    def read_items(self, cache_dir: str, items: List[Dict]) -> List[Dict]:
        """An answer's items as answers() gives them (here as cached; tnm.OprIndex: made readable, and raising when a
        survey of them cannot be read now): ComposedBlocks.update_tile reads a fresh answer through it before writing
        it."""
        return items

    def _fetch(self, cache_dir: str, lat: float, lon: float, old: Optional[List[Dict]]) -> Dict:
        """The index's answer for a tile; with confirms_drops and a cached answer (old: its versions) the rule of
        dropped files (the class's docstring), else DroppedFiles."""
        answer = self.listing.fetch(lat, lon)
        if not self.confirms_drops or old is None:
            return answer
        names = lambda sheets: {_name(s["url"]) for s in sheets}  # noqa: E731
        held = names(old) - names(self.extra(cache_dir, lat, lon))
        if not held - names(answer["sheets"]):
            return answer
        again = self.listing.fetch(lat, lon)
        dropped_names = held - names(again["sheets"])
        if not dropped_names:
            return again
        dropped = {s["url"] for s in old if _name(s["url"]) in dropped_names}  # checked at the cached answer's URL
        tile = osm.tile_name(lat, lon)
        if names(again["sheets"]) != names(answer["sheets"]):
            raise DroppedFiles(f"the index answer of {tile} dropped {len(dropped)} of the files the cached one holds "
                               f"and, asked again at once, listed other files: the cached answer is kept")
        if self.check_gone is None:
            return again
        for url in sorted(dropped)[:CHECK_GONE_MAX]:
            gone = self.check_gone(url)
            if gone is True:
                continue
            refused = DroppedStillThere if gone is False else DroppedFiles  # a decision of the index, or not known
            raise refused(f"the index answer of {tile} dropped {len(dropped)} of the files the cached one holds, "
                          + (f"of which {url.rsplit('/', 1)[-1]} still answers at its URL: the index is wrong "
                             f"or delisted files the bucket keeps (the next listing of the bucket takes them in)"
                             if gone is False else f"and the check of {url.rsplit('/', 1)[-1]} at its URL failed")
                          + ": the cached answer is kept")
        return again

    def fresh_answer(self, cache_dir: str, lat: float, lon: float) -> Dict:
        """The index's answer for a tile now (_fetch, the cached answer read for the drop rule), asked under the tile's
        lock and not written (store writes it): ComposedBlocks.update_tile, where a refused drop raises."""
        path = self.index_path(cache_dir, lat, lon)
        with tile_lock(cache_dir, path):
            return self._fetch(cache_dir, lat, lon, self._cached_sheets(path))

    def store(self, cache_dir: str, lat: float, lon: float, answer: Dict):
        """An answer (fresh_answer's) written in place of the cached one, under the tile's lock."""
        path = self.index_path(cache_dir, lat, lon)
        with tile_lock(cache_dir, path):
            self._store(cache_dir, path, answer)

    def _store(self, cache_dir: str, path: str, answer: Dict):
        """An answer of the index written in place of the cached one (atomically) and recorded."""
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = _part(path)
        with open(tmp, "w", encoding="utf-8") as out:
            json.dump(answer, out)
        os.replace(tmp, path)
        cache.record(cache_dir, path, url=self.listing.url)

    def ask_again(self, cache_dir: str, lat: float, lon: float, since: Optional[str] = None) -> Optional[bool]:
        """Ask the index again for one tile (sources/renewal.py), under the tile's lock, and write its answer only
        when the request succeeded: a failure raises (a requests.RequestException; DroppedFiles: _fetch) and the
        cached answer stays. None when the cached answer was checked at or after `since` (a time as cache.now_iso
        gives it, the start of the renewal): another renewal asked it meanwhile, so it is not asked twice. Else
        whether the listed versions changed (compared as sets: the index's order of its products is left aside); a
        tile without a cached answer counts as changed."""
        path = self.index_path(cache_dir, lat, lon)
        with tile_lock(cache_dir, path):
            old = self._cached_sheets(path)
            if since and old is not None:
                row = cache.info(cache_dir, path)
                if row and row.get("checked_at") and row["checked_at"] >= since:
                    return None
            answer = self._fetch(cache_dir, lat, lon, old)
            self._store(cache_dir, path, answer)
        same = lambda sheets: sorted(json.dumps(s, sort_keys=True) for s in sheets)  # noqa: E731
        return old is None or same(old) != same(answer["sheets"])

    @staticmethod
    def _cached_sheets(path: str) -> Optional[List[Dict]]:
        """The versions of a cached answer as the index gave them; None without one (or one that cannot be read)."""
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)["sheets"]
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def extra(self, cache_dir: str, lat: float, lon: float) -> List[Dict]:
        """Versions a tile holds besides its cached answer (none here; tnm.UnlistedIndex: the bucket's unlisted
        files), merged in when an answer is read."""
        return []

    def tiles(self, grid: Grid) -> Optional[list]:
        key = (grid.crs, tuple(grid.bounds), grid.res, self.update)
        if key not in self._listed:
            try:
                self._listed[key] = self.versions.query(self, grid, self.cache_dir, self.update)
            except requests.RequestException as e:
                # The error's text at the end: an area download (tools/area_download.py) meets this
                # pass after pass and needs to know what the service answered
                print(f"{self.description}: index not available ({type(e).__name__}); "
                      f"using the cached files ({cache.clean_error(e)})")
                self._listed[key] = None
        return self._listed[key]

    def path(self, cache_dir: str, tile) -> str:
        return self.versions.path(cache_dir, tile)

    def request(self, tile):
        return self.versions.request(tile)

    def cached(self, grid: Grid, cache_dir: str) -> list:
        return self.versions.cached(grid, cache_dir)

    def prune(self, cache_dir: str, tiles: list) -> int:
        return self.versions.prune(cache_dir, tiles)

    def update_tile(self, cache_dir: str, lat: float, lon: float) -> Tuple[list, list]:
        return self.versions.update_tile(self, cache_dir, lat, lon)

    def has_data_near(self, lat: float, lon: float, cache_dir: str) -> Optional[bool]:
        return self.versions.has_data_near(self, lat, lon, cache_dir)
