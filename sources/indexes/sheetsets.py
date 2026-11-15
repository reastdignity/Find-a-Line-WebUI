"""SheetSets: a version policy of a cached index whose files are whole map sheets of one or more fixed cell sizes,
several files per sheet (surveys of different years, two deliveries of one year): each sheet composed from all of
them, newest first (SheetSetFile)."""

import glob
import hashlib
import os
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import requests
from rasterio.transform import from_origin
from rasterio.warp import transform_bounds

import cache
import osm
from grid import Grid

from ..readers.sheetsets import SheetSetRequest
from .cached import CachedIndex, Versions, index_tiles
from .tilings import MetricCellTiling

File = Tuple[str, str, int, int]  # name, url, survey year, bytes


@dataclass(frozen=True)
class SheetSet:
    """A sheet of one level (a cell (i, j) of its tiling) and the files composed into it, newest year first. The
    key stands for its set of files (their names carry their ETags): a new or re-uploaded file gives it another
    key, so it is read again. year: of its newest file."""
    level: str
    i: int
    j: int
    year: int
    key: str
    files: Tuple[File, ...] = ()

    @property
    def bytes(self) -> int:
        """The bytes of the files certainly read: those of the newest year (older ones only for holes)."""
        return sum(f[3] for f in self.files if f[2] == self.year)


class SheetSets(Versions):
    """Sheets of the levels (name -> MetricCellTiling: its cells, their names and the folder under which they are
    cached), each composed from the files listed for it. The listed items are {name, url, level, cell: [i, j],
    year, size} (the name unique per file and version: the ETag in it). Cached as
    <folder>/<level>/<the cell's folders>/<year>_<code>_<key>.tif (the year first, as IndexedTiles.used reads it;
    the folders and the code from the level's names: s/OF/04/2019_08OF0485_1a2b3c4d.tif).

    Newest first across the levels too: the mosaic places the sheets in the order given (the first wins), sorted
    by year; a sheet of one level whose files are both newer and older than a sheet of another level over it is
    split there into two sheets of its own (the files of each side), so an older file never wins over a newer
    survey of the other level (Shizuoka: 39 sheets of 400 x 300 m of FY2021 and FY2025 under FY2022's 1000 x 750 m
    sheets, 2026-11-15)."""

    def __init__(self, folder: str, crs: str, native_res: float, levels: Dict[str, MetricCellTiling]):
        self.folder, self.crs, self.native_res, self.levels = folder, crs, native_res, levels

    # --- the sets of files -------------------------------------------------------------------------------
    @staticmethod
    def _key(files: Sequence[File]) -> str:
        return hashlib.sha1(",".join(sorted(f[0] for f in files)).encode()).hexdigest()[:8]

    def _box(self, level: str, i: int, j: int) -> Tuple[float, float, float, float]:
        return self.levels[level].edges((i, j))

    def _overlapping(self, level: str, i: int, j: int, groups: Dict[Tuple[str, int, int], List[Dict]]) -> List[int]:
        """The years of the files of other levels' sheets over a sheet."""
        left, bottom, right, top = self._box(level, i, j)
        years = []
        for other, tiling in self.levels.items():
            if other == level:
                continue
            (i0, j0), (i1, j1) = tiling.cell_of(left + 1e-6, bottom + 1e-6), tiling.cell_of(right - 1e-6, top - 1e-6)
            for oi in range(i0, i1 + 1):
                for oj in range(j0, j1 + 1):
                    years += [item["year"] for item in groups.get((other, oi, oj), ())]
        return years

    def sets(self, items: Sequence[Dict]) -> List[SheetSet]:
        """The sheets of the listed files, newest first (then by level and place), each split where a sheet of
        another level holds a year between its files' years."""
        groups: Dict[Tuple[str, int, int], List[Dict]] = {}
        seen = set()
        for item in items:
            if item["url"] in seen:
                continue
            seen.add(item["url"])
            groups.setdefault((item["level"], *item["cell"]), []).append(item)
        found = []
        for (level, i, j), files in groups.items():
            barriers = self._overlapping(level, i, j, groups)
            parts: Dict[int, List[File]] = {}
            for item in files:
                part = sum(1 for b in set(barriers) if item["year"] < b)
                parts.setdefault(part, []).append((item["name"], item["url"], item["year"], item["size"]))
            for part in parts.values():
                part.sort(key=lambda f: (-f[2], f[0]))
                found.append(SheetSet(level, i, j, part[0][2], self._key(part), tuple(part)))
        return sorted(found, key=lambda s: (-s.year, s.level, -s.j, s.i))

    def _within(self, sheets: List[SheetSet], grid: Grid) -> List[SheetSet]:
        """The sheets over the grid's box, and under its outline when it has one."""
        g_left, g_bottom, g_right, g_top = transform_bounds(grid.crs, self.crs, *grid.bounds)
        shape = None
        if grid.area_shape is not None:
            import shapely
            from area import project
            from shapely.geometry import box
            shape = project(grid.area_shape, grid.crs, self.crs).intersection(box(g_left, g_bottom, g_right, g_top))
            shapely.prepare(shape)
        kept = []
        for s in sheets:
            left, bottom, right, top = self._box(s.level, s.i, s.j)
            if not (left < g_right and right > g_left and bottom < g_top and top > g_bottom):
                continue
            if shape is not None:
                from shapely.geometry import box
                if not shape.intersects(box(left, bottom, right, top)):
                    continue
            kept.append(s)
        return kept

    def query(self, index: CachedIndex, grid: Grid, cache_dir: str, update: Optional[str]) -> list:
        items = [item for lat, lon in index_tiles(grid) for item in index.answers(cache_dir, lat, lon, update)]
        return self._within(self.sets(items), grid)

    # --- the cached files ------------------------------------------------------------------------------------
    def path(self, cache_dir: str, tile: SheetSet) -> str:
        folders, _, code = self.levels[tile.level].name(tile.i, tile.j).rpartition("/")
        return os.path.join(cache_dir, self.folder, tile.level, *folders.split("/"),
                            f"{tile.year}_{code}_{tile.key}.tif")

    def request(self, tile: SheetSet) -> SheetSetRequest:
        left, bottom, right, top = self._box(tile.level, tile.i, tile.j)
        res = self.native_res
        return SheetSetRequest(tile.files, self.crs, from_origin(left, top, res, res),
                               (round((top - bottom) / res), round((right - left) / res)),
                               self.levels[tile.level].name(tile.i, tile.j).rsplit("/", 1)[-1])

    def _sheet_of(self, path: str) -> Optional[SheetSet]:
        """The sheet of a cached file (without its files), None when it is not one."""
        parts = re.split(r"[\\/]", path)
        match = re.fullmatch(r"(\d+)_([^_]+)_([0-9a-f]+)\.tif", parts[-1])
        if not match:
            return None
        for depth in range(0, min(len(parts) - 1, 6)):  # the folders between the level's folder and the file
            level = parts[-depth - 2]
            tiling = self.levels.get(level)
            if tiling is None:
                continue
            name = "/".join(parts[len(parts) - depth - 1:-1] + [match.group(2)])
            cell = tiling.parse(name)
            if cell is not None and tiling.name(*cell) == name:
                return SheetSet(level, cell[0], cell[1], int(match.group(1)), match.group(3))
        return None

    def _cached_paths(self, cache_dir: str) -> List[str]:
        return glob.glob(os.path.join(cache_dir, self.folder, "**", "*.tif"), recursive=True)

    def cached(self, grid: Grid, cache_dir: str) -> list:
        sheets = [s for s in (self._sheet_of(p) for p in self._cached_paths(cache_dir)) if s is not None]
        return sorted(self._within(sheets, grid), key=lambda s: (-s.year, s.level, -s.j, s.i))

    def _others(self, cache_dir: str, sheet: SheetSet, keep: set) -> List[str]:
        """The cached files of the same sheet made from other sets of files than those in keep."""
        folder = os.path.dirname(self.path(cache_dir, sheet))
        found = [os.path.join(folder, n) for n in os.listdir(folder)] if os.path.isdir(folder) else []
        return [p for p in found if (s := self._sheet_of(p)) is not None and (s.level, s.i, s.j) == (sheet.level, sheet.i, sheet.j)
                and s.key not in keep]

    def prune(self, cache_dir: str, tiles: List[SheetSet]) -> int:
        """Delete the cached files of the sheets made from sets no longer listed (a sheet split in two keeps
        both parts); how many."""
        keys: Dict[Tuple[str, int, int], set] = {}
        for s in tiles:
            keys.setdefault((s.level, s.i, s.j), set()).add(s.key)
        older, done = [], set()
        for s in tiles:
            place = (s.level, s.i, s.j)
            if place in done or not os.path.exists(self.path(cache_dir, s)):
                continue
            done.add(place)
            older += self._others(cache_dir, s, keys[place])
        cache.forget(cache_dir, older)
        return len(older)

    def update_tile(self, index: CachedIndex, cache_dir: str, lat: float, lon: float) -> Tuple[list, list]:
        """The cached sheets (centred in the 0.25° tile) whose sets of files changed: read again, their older
        files deleted then."""
        items = index.answers(cache_dir, lat, lon, "all")
        now: Dict[Tuple[str, int, int], List[SheetSet]] = {}
        for s in self.sets(items):
            now.setdefault((s.level, s.i, s.j), []).append(s)
        todo, keep = [], []
        for path in self._cached_paths(cache_dir):
            cached = self._sheet_of(path)
            if cached is None:
                continue
            west, south, east, north = transform_bounds(self.crs, "EPSG:4326", *self._box(cached.level, cached.i, cached.j))
            if not (lat <= (south + north) / 2 < lat + osm.TILE_DEG and lon <= (west + east) / 2 < lon + osm.TILE_DEG):
                continue
            current = now.get((cached.level, cached.i, cached.j), [])
            for s in current:
                if s not in keep:
                    keep.append(s)
                if s.key != cached.key and s not in todo and not os.path.exists(self.path(cache_dir, s)):
                    todo.append(s)
        return todo, keep

    def has_data_near(self, index: CachedIndex, lat: float, lon: float, cache_dir: str,
                      metres: float = 2000) -> Optional[bool]:
        try:
            items = [item for tile in osm.tiles(lon, lat, lon, lat) for item in index.answers(cache_dir, *tile)]
        except requests.RequestException:
            return None
        import rasterio.warp
        xs, ys = rasterio.warp.transform("EPSG:4326", self.crs, [lon], [lat])
        x, y = xs[0], ys[0]
        for item in items:
            left, bottom, right, top = self._box(item["level"], *item["cell"])
            if left - metres <= x <= right + metres and bottom - metres <= y <= top + metres:
                return True
        return False
