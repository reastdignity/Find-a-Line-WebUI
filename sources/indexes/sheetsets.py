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

from ..readers.sheetsets import SheetSetRequest, set_files
from .cached import CachedIndex, Versions, index_tiles
from .tilings import MetricCellTiling

File = Tuple[str, str, int, int]  # name, url, survey year, bytes


def _stem(name: str) -> str:
    """A listed file's name without its version (the ETag after "@")."""
    return name.split("@", 1)[0]


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
    by year. A sheet of a level is split at each of its level's `splits` years (the years of another level's
    survey, Shizuoka's FY2022 on its quadrant sheets): its files newer and older than such a year make two sheets
    of their own, so an older file never wins over a newer survey of the other level (39 sheets of 400 x 300 m of
    FY2021 and FY2025 under FY2022's 1000 x 750 m sheets, 2026-11-15). The split is decided from the sheet's own
    files and these fixed years, never from the other level's items seen: a sheet's sets, and so its keys, are the
    same whichever index tiles a grid touches (until 2026-11-16 a sheet was split only when the quadrant sheet
    over it was among the items seen, so two searches gave it two keys and each pruned the other's file); a sheet
    of FY2021 and FY2025 outside the quadrant sheets (5 of 44) is split as well, its FY2021 part then read even
    without holes in FY2025's.

    A file listed twice (a sheet straddling two index tiles whose answers were asked at different times, the file
    re-uploaded in between) is taken from the answer with its newer upload (LastModified, then the newer listing),
    so it gets one key whichever answer comes first."""

    def __init__(self, folder: str, crs: str, native_res: float, levels: Dict[str, MetricCellTiling],
                 splits: Optional[Dict[str, Sequence[int]]] = None):
        self.folder, self.crs, self.native_res, self.levels = folder, crs, native_res, levels
        self.splits = {level: tuple(years) for level, years in (splits or {}).items()}

    # --- the sets of files -------------------------------------------------------------------------------
    @staticmethod
    def _key(files: Sequence[File]) -> str:
        return hashlib.sha1(",".join(sorted(f[0] for f in files)).encode()).hexdigest()[:8]

    def _box(self, level: str, i: int, j: int) -> Tuple[float, float, float, float]:
        return self.levels[level].edges((i, j))

    def sets(self, items: Sequence[Dict]) -> List[SheetSet]:
        """The sheets of the listed files, newest first (then by level and place), each split at its level's
        `splits` years; a file listed more than once taken from its newest upload."""
        newest: Dict[str, Dict] = {}
        for item in items:
            old = newest.get(item["url"])
            if old is None or (item.get("modified", ""), item.get("listed", "")) > \
                    (old.get("modified", ""), old.get("listed", "")):
                newest[item["url"]] = item
        groups: Dict[Tuple[str, int, int], List[Dict]] = {}
        for item in newest.values():
            groups.setdefault((item["level"], *item["cell"]), []).append(item)
        found = []
        for (level, i, j), files in groups.items():
            barriers = self.splits.get(level, ())
            parts: Dict[int, List[File]] = {}
            for item in files:
                part = sum(1 for b in barriers if item["year"] < b)
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
        """The sheets over the grid. A sheet over the grid that reaches into index tiles the grid does not touch
        is made from the answers of all of its tiles (asked if not cached), so its set is the same whichever of
        its tiles a grid touches (a file uploaded again between two tiles' answers: the newer upload)."""
        tiles = index_tiles(grid)
        items = [item for lat, lon in tiles for item in index.answers(cache_dir, lat, lon, update)]
        g_left, g_bottom, g_right, g_top = transform_bounds(grid.crs, self.crs, *grid.bounds)
        more = set()
        for item in items:
            left, bottom, right, top = self._box(item["level"], *item["cell"])
            if left < g_right and right > g_left and bottom < g_top and top > g_bottom:
                west, south, east, north = transform_bounds(self.crs, "EPSG:4326", left, bottom, right, top)
                more.update(osm.tiles(west, south, east, north))
        for lat, lon in sorted(more - set(tiles)):
            items += index.answers(cache_dir, lat, lon, update)
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

    def prune(self, cache_dir: str, tiles: List[SheetSet]) -> int:
        """Delete the cached files of the sheets that hold only older versions of the files of a current, cached
        set of the same sheet (every file name of theirs, without its ETag, is one of that set's, under another
        ETag or not at all): an upload in place, a survey added. A file another current key of the sheet names is
        never deleted, nor one of other files (a part of a split sheet); how many."""
        current: Dict[Tuple[str, int, int], List[SheetSet]] = {}
        for s in tiles:
            if os.path.exists(self.path(cache_dir, s)):
                current.setdefault((s.level, s.i, s.j), []).append(s)
        older = []
        for place, sheets in current.items():
            keys = {s.key for s in sheets}
            folder = os.path.dirname(self.path(cache_dir, sheets[0]))
            for name in os.listdir(folder):
                path = os.path.join(folder, name)
                other = self._sheet_of(path)
                if other is None or (other.level, other.i, other.j) != place or other.key in keys:
                    continue
                stems = {_stem(n) for n in set_files(path)}
                if stems and any(stems <= {_stem(f[0]) for f in s.files} for s in sheets):
                    older.append(path)
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
            box = self._box(cached.level, cached.i, cached.j)
            west, south, east, north = transform_bounds(self.crs, "EPSG:4326", *box)
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
