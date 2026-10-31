"""IndexedTiles: files found through an index of the service, the newest survey per sheet or tile."""

import glob
import json
import os
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import rasterio as rio
import requests
from rasterio.warp import transform_bounds

import cache
import osm
from grid import Grid

from ..net import tile_lock
from ..layer import Layer


@dataclass(frozen=True)
class Sheet:
    """One file of a tile index: a map sheet or a tile of one survey (see IndexedTiles)."""
    year: int
    name: str   # file name without extension, e.g. 77532_1356765_M-34-64-D-a-1-1
    godlo: str  # the sheet or tile it covers; the newest survey of each is used
    url: str
    crs: str
    res: float
    sha256: Optional[str] = None  # of the file, when the index gives it


class IndexedTiles(Layer):
    """Files found through an index of the service, one per sheet or tile and survey.

    For every sheet or tile (godło) only the newest survey is used, and the files are
    ordered newest first, so where sheets of different series overlap the newest data
    wins in the mosaic. Each file is cached as a GeoTIFF named <year>_<name>.tif.

    The index answers are cached too, per 0.25° tile (osm.tiles) in
    <top folder>/sheet-index/<prefix>/<tile>.json with every listed version and its
    extent (in index_crs), so a search in a known place asks the index nothing. Without
    the index (offline) and without its cached answer, the cached files over the area
    are used. An update asks the index again and replaces older surveys (update.py).

    Subclasses ask the index (_fetch_tile) and download a file (download_tile).
    """
    index_crs = ""  # CRS of the extents in the cached index answers

    def __init__(self, description: str, index_url: str, prefix: str, folder: str,
                 native_res: float, bytes_per_tile: float):
        self.description, self.index_url, self.prefix = description, index_url, prefix
        self.folder, self.native_res, self._bytes = folder, native_res, bytes_per_tile
        self._listed: Dict[tuple, list] = {}
        self._versions: Dict[str, set] = {}  # every listed survey of a godło
        self._cache_dir: Optional[str] = None  # set by the methods that get it (tiles() does not)
        self._update: Optional[str] = None

    def _fetch_tile(self, lat: float, lon: float, path: str):
        """Every usable version listed by the index in one 0.25° tile, saved as JSON
        ({"sheets": [{"year", "godlo", "url", "crs", "res", "extent"}, ...]})."""
        raise NotImplementedError

    def index_path(self, cache_dir: str, lat: float, lon: float) -> str:
        """The cached index answer of one 0.25° tile."""
        top = self.folder.split("/")[0]
        return os.path.join(cache_dir, top, "sheet-index", self.prefix, f"{osm.tile_name(lat, lon)}.json")

    def _index_tile(self, cache_dir: str, lat: float, lon: float, update: Optional[str] = None) -> List[Dict]:
        """The sheets listed in one tile, asking the index when not cached or stale."""
        path = self.index_path(cache_dir, lat, lon)
        due = lambda: cache.due(cache_dir, path, update=update, ttl=cache.TTL_DAYS["sheet-index"])  # noqa: E731
        if due():
            with tile_lock(cache_dir, path):  # another search may be asking for it now
                if due():
                    self._fetch_tile(lat, lon, path)
                    cache.record(cache_dir, path, url=self.index_url)
        with open(path, encoding="utf-8") as f:
            return json.load(f)["sheets"]

    def _sheet(self, item: Dict) -> Sheet:
        url = item["url"]
        return Sheet(item["year"], re.sub(r"(\.[a-z]+)+$", "", url.rsplit("/", 1)[-1], flags=re.I),
                     item["godlo"], url, item["crs"], item["res"])

    def _wanted(self, sheet: Sheet, grid: Grid) -> bool:
        """Whether a listed file is used for this grid."""
        return True

    def _query(self, grid: Grid, cache_dir: str) -> list:
        """The newest sheet per godło over the grid, newest first."""
        west, south, east, north = transform_bounds(grid.crs, "EPSG:4326", *grid.bounds)
        g_left, g_bottom, g_right, g_top = transform_bounds(grid.crs, self.index_crs, *grid.bounds)
        shape = None
        if grid.area_shape is not None:
            from area import project
            from shapely.geometry import box
            shape = project(grid.area_shape, grid.crs, self.index_crs).intersection(
                box(g_left, g_bottom, g_right, g_top))
        newest: Dict[str, Sheet] = {}
        for lat, lon in osm.tiles(west, south, east, north):
            for item in self._index_tile(cache_dir, lat, lon, self._update):
                left, bottom, right, top = item["extent"]
                if not (left < g_right and right > g_left and bottom < g_top and top > g_bottom):
                    continue
                if shape is not None and not shape.intersects(box(left, bottom, right, top)):
                    continue
                sheet = self._sheet(item)
                if not self._wanted(sheet, grid):
                    continue
                self._versions.setdefault(sheet.godlo, set()).add(sheet)
                old = newest.get(sheet.godlo)
                if old is None or _sheet_order(sheet) > _sheet_order(old):
                    newest[sheet.godlo] = sheet
        return sorted(newest.values(), key=_sheet_order, reverse=True)

    def _prune(self, cache_dir: str, sheets: List[Sheet]) -> int:
        """Delete cached older surveys of sheets whose newest survey is cached; how many."""
        older = []
        for sheet in sheets:
            if os.path.exists(self.tile_path(cache_dir, sheet)):
                older += [self.tile_path(cache_dir, v) for v in self._versions.get(sheet.godlo, ())
                          if v != sheet and os.path.exists(self.tile_path(cache_dir, v))]
        cache.forget(cache_dir, older)
        return len(older)

    def update_index_tile(self, cache_dir: str, lat: float, lon: float) -> Tuple[int, int, int]:
        """Ask the index again for one tile and download the newer surveys of the cached
        sheets there (the older files are deleted). Returns (new sheets, MB, deleted)."""
        listed = [self._sheet(item) for item in self._index_tile(cache_dir, lat, lon, "all")]
        newest: Dict[str, Sheet] = {}
        for sheet in listed:
            self._versions.setdefault(sheet.godlo, set()).add(sheet)
            if sheet.godlo not in newest or _sheet_order(sheet) > _sheet_order(newest[sheet.godlo]):
                newest[sheet.godlo] = sheet
        cached = {s.godlo for s in listed if os.path.exists(self.tile_path(cache_dir, s))}
        todo = [s for g, s in newest.items() if g in cached and not os.path.exists(self.tile_path(cache_dir, s))]
        received = sum(self._download_and_record(s, cache_dir) for s in todo)
        return len(todo), received / 1e6, self._prune(cache_dir, list(newest.values()))

    def _cached_files(self, grid: Grid, cache_dir: str) -> Tuple[List[str], float]:
        """The cached files that could be used for this grid, and their resolution."""
        return glob.glob(os.path.join(cache_dir, self.folder, "*.tif")), self.native_res

    def _cached(self, grid: Grid, cache_dir: str) -> list:
        """Cached sheets over the grid, newest first (when the index cannot be reached)."""
        sheets = []
        paths, res = self._cached_files(grid, cache_dir)
        for path in paths:
            with rio.open(path) as src:
                left, bottom, right, top = transform_bounds(src.crs, grid.crs, *src.bounds)
            g_left, g_bottom, g_right, g_top = grid.bounds
            if left < g_right and right > g_left and bottom < g_top and top > g_bottom:
                year, name = os.path.basename(path)[:-4].split("_", 1)
                sheets.append(Sheet(int(year), name, "", "", "", res))
        return sorted(sheets, key=_sheet_order, reverse=True)

    def tiles(self, grid: Grid) -> list:
        key = (grid.crs, tuple(grid.bounds), grid.res, self._update)
        if key not in self._listed:
            try:
                self._listed[key] = self._query(grid, self._cache_dir)
            except requests.RequestException as e:
                print(f"{self.description}: index not available ({type(e).__name__}); "
                      "using the cached files")
                self._listed[key] = None
        return self._listed[key]

    def _use(self, cache_dir: str, update: Optional[str] = None):
        """What tiles() needs (it gets only the grid)."""
        self._cache_dir, self._update = cache_dir, update

    def missing(self, grid: Grid, cache_dir: str, update: Optional[str]) -> list:
        self._use(cache_dir, update)
        if self.tiles(grid) is None:
            return []
        return super().missing(grid, cache_dir, update)

    def estimate(self, grid: Grid, cache_dir: str, update: Optional[str]) -> Tuple[int, int, float]:
        self._use(cache_dir, update)
        if self.tiles(grid) is None:
            return len(self._cached(grid, cache_dir)), 0, 0.0
        return super().estimate(grid, cache_dir, update)

    def to_download(self, grid: Grid, cache_dir: str, update: Optional[str]) -> Tuple[list, Optional[str]]:
        self._use(cache_dir, update)
        if self.tiles(grid) is None:
            return [], None  # the index cannot be reached: the cached files are used
        return super().to_download(grid, cache_dir, update)

    def downloaded(self, grid: Grid, cache_dir: str):
        sheets = self.tiles(grid)
        if sheets is not None:
            pruned = self._prune(cache_dir, sheets)
            if pruned:
                print(f"{self.description}: {pruned} older surveys replaced by newer ones (deleted)")

    def tile_url(self, tile) -> Optional[str]:
        return tile.url

    def files(self, grid: Grid, cache_dir: str) -> List[str]:
        self._use(cache_dir, self._update)
        if self.tiles(grid) is None:
            return [self.tile_path(cache_dir, s) for s in self._cached(grid, cache_dir)]
        return super().files(grid, cache_dir)

    def tile_path(self, cache_dir: str, tile) -> str:
        return os.path.join(cache_dir, self.folder, f"{tile.year}_{tile.name}.tif")

    def source_date(self, tile) -> Optional[str]:
        return str(tile.year)

    def used(self, grid: Grid, cache_dir: str) -> Dict:
        info = super().used(grid, cache_dir)
        years = [int(os.path.basename(p).split("_", 1)[0]) for p in self.files(grid, cache_dir)]
        info["survey_years"] = [min(years), max(years)] if years else None
        return info

    def bytes_per_tile(self) -> float:
        return self._bytes


def _sheet_order(sheet: Sheet) -> tuple:
    """Newer year first; within a year, the later publication (higher numbers in the file name)."""
    return (sheet.year,) + tuple(int(n) for n in re.findall(r"\d+", sheet.name)[:2])
