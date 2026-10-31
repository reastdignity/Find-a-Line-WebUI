"""IndexedTiles: files found through an index of the service, the newest survey per sheet or tile."""

import os
from typing import Dict, List, Optional, Tuple

from grid import Grid

from ..composed import ComposedLayer
from ..indexes.cached import CachedIndex


class IndexedTiles(ComposedLayer):
    """Files found through an index of the service (a CachedIndex): one per sheet or tile and
    survey, the newest survey of each used (NewestPerSheet), or blocks composed from every
    file over them (ComposedBlocks).

    The index answers are cached per 0.25° tile (osm.tiles) in
    <top folder>/sheet-index/<prefix>/<tile>.json with every listed version and its
    extent (in index_crs), so a search in a known place asks the index nothing. Without
    the index (offline) and without its cached answer, the cached files over the area
    are used. An update asks the index again and replaces older surveys (update.py).

    Subclasses build the index (a listing and a version policy) and the reader.
    """
    index_crs = ""  # CRS of the extents in the cached index answers
    index: CachedIndex

    def __init__(self, description: str, index_url: str, prefix: str, folder: str,
                 native_res: float, bytes_per_tile: float):
        self.description, self.index_url, self.prefix = description, index_url, prefix
        self.folder, self.native_res, self._bytes = folder, native_res, bytes_per_tile

    def index_path(self, cache_dir: str, lat: float, lon: float) -> str:
        """The cached index answer of one 0.25° tile."""
        return self.index.index_path(cache_dir, lat, lon)

    def update_index_tile(self, cache_dir: str, lat: float, lon: float) -> Tuple[int, int, int]:
        """Ask the index again for one tile and download the newer versions of the cached
        tiles there (the older files are deleted). Returns (new tiles, MB, deleted)."""
        todo, keep = self.index.update_tile(cache_dir, lat, lon)
        received = sum(self._download_and_record(t, cache_dir) for t in todo)
        return len(todo), received / 1e6, self.index.prune(cache_dir, keep)

    def _use(self, cache_dir: str, update: Optional[str] = None):
        """What tiles() needs (it gets only the grid)."""
        self.index.use(cache_dir, update)

    def missing(self, grid: Grid, cache_dir: str, update: Optional[str]) -> list:
        self._use(cache_dir, update)
        if self.tiles(grid) is None:
            return []
        return super().missing(grid, cache_dir, update)

    def estimate(self, grid: Grid, cache_dir: str, update: Optional[str]) -> Tuple[int, int, float]:
        self._use(cache_dir, update)
        if self.tiles(grid) is None:
            return len(self.index.cached(grid, cache_dir)), 0, 0.0
        return super().estimate(grid, cache_dir, update)

    def to_download(self, grid: Grid, cache_dir: str, update: Optional[str]) -> Tuple[list, Optional[str]]:
        self._use(cache_dir, update)
        if self.tiles(grid) is None:
            return [], None  # the index cannot be reached: the cached files are used
        return super().to_download(grid, cache_dir, update)

    def downloaded(self, grid: Grid, cache_dir: str):
        sheets = self.tiles(grid)
        if sheets is not None:
            pruned = self.index.prune(cache_dir, sheets)
            if pruned:
                print(f"{self.description}: {pruned} older surveys replaced by newer ones (deleted)")

    def files(self, grid: Grid, cache_dir: str) -> List[str]:
        self._use(cache_dir, self.index.update)
        if self.tiles(grid) is None:
            return [self.tile_path(cache_dir, s) for s in self.index.cached(grid, cache_dir)]
        return super().files(grid, cache_dir)

    def source_date(self, tile) -> Optional[str]:
        return str(tile.year)

    def used(self, grid: Grid, cache_dir: str) -> Dict:
        info = super().used(grid, cache_dir)
        years = [int(os.path.basename(p).split("_", 1)[0]) for p in self.files(grid, cache_dir)]
        info["survey_years"] = [min(years), max(years)] if years else None
        return info
