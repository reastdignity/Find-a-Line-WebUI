"""CachedIndex: the answers of an index service cached per 0.25° tile, and a policy for the versions they list."""

import json
import os
from typing import Dict, List, Optional, Tuple

import requests

import cache
import osm
from grid import Grid

from ..net import _part, tile_lock
from ..composed import Index


class IndexUnavailable(requests.RequestException):
    """An index service cannot be asked (offline, down, an error answer). A RequestException,
    so the cached files are used (CachedIndex.tiles) and `cache update` lists it as an error;
    for listings whose client is not requests (see docs/sources-architecture.md)."""


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
    ("sheet-index") or with an update.

    tiles() gets only the grid: use() gives it the cache folder and the update mode first.
    """

    def __init__(self, description: str, listing: Listing, versions: Versions, prefix: str, top: str):
        self.description, self.listing, self.versions, self.prefix, self.top = \
            description, listing, versions, prefix, top
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
        due = lambda: cache.due(cache_dir, path, update=update, ttl=cache.TTL_DAYS["sheet-index"])  # noqa: E731
        if due():
            with tile_lock(cache_dir, path):  # another search may be asking for it now
                if due():
                    answer = self.listing.fetch(lat, lon)
                    os.makedirs(os.path.dirname(path), exist_ok=True)
                    tmp = _part(path)
                    with open(tmp, "w", encoding="utf-8") as out:
                        json.dump(answer, out)
                    os.replace(tmp, path)
                    cache.record(cache_dir, path, url=self.listing.url)
        with open(path, encoding="utf-8") as f:
            return json.load(f)["sheets"]

    def tiles(self, grid: Grid) -> Optional[list]:
        key = (grid.crs, tuple(grid.bounds), grid.res, self.update)
        if key not in self._listed:
            try:
                self._listed[key] = self.versions.query(self, grid, self.cache_dir, self.update)
            except requests.RequestException as e:
                print(f"{self.description}: index not available ({type(e).__name__}); "
                      "using the cached files")
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
