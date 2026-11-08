"""CachedIndex: the answers of an index service cached per 0.25° tile, and a policy for the versions they list."""

import json
import os
from typing import Dict, List, Optional, Tuple

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
    an area), the tiles under the outline only: for each part of it (shapely.get_parts: the islands
    of a country, the pieces of a coast) the tiles of the part's own box grown by INDEX_MARGIN_DEG,
    kept where the tile's box grown by the margin intersects the outline.

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
    margin = INDEX_MARGIN_DEG
    found = set()
    for part in shapely.get_parts(shape):
        p_west, p_south, p_east, p_north = part.bounds
        if p_east - p_west > 180:  # across 180°
            corners = osm.tiles(west, max(south, p_south - margin), east, min(north, p_north + margin))
        else:
            corners = osm.tiles(p_west - margin, p_south - margin, p_east + margin, p_north + margin)
        if not corners:
            continue
        lats = np.array([lat for lat, _ in corners])
        lons = np.array([lon for _, lon in corners])
        boxes = shapely.box(lons - margin, lats - margin, lons + osm.TILE_DEG + margin, lats + osm.TILE_DEG + margin)
        found.update(corner for corner, hit in zip(corners, shapely.intersects(shape, boxes)) if hit)
    return sorted(found)


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
    (ttl_days: "sheet-index" unless the index publishes more often) or with an update.

    tiles() gets only the grid: use() gives it the cache folder and the update mode first.
    """

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
