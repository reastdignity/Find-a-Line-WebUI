"""SheetSets: a version policy of a cached index whose files are whole map sheets of one or more fixed cell sizes,
several files per sheet (surveys of different years, two deliveries of one year): each sheet composed from all of
them, newest first (SheetSetFile)."""

import glob
import hashlib
import json
import math
import os
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import rasterio as rio
import rasterio.warp
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

    One answer decides everything about a sheet: every sheet has one owner index tile, the 0.25 degree tile holding
    the sheet's centre (owner(); from the sheet's place, no request), and only its owner's answer is read for it,
    in query, update_tile, prune and offline (cached), so a sheet's sets and keys never depend on which tiles a grid
    touches or when they were listed (until 2026-11-16 a sheet near a tile's edge was in two answers, listed at
    different times: keys alternated and each search pruned the other's file). An answer keeps only the sheets its
    tile owns (S3SheetSets' listing), and the items of an answer cached before that are filtered so when read.

    Newest first across the levels too: the mosaic places the sheets in the order given (the first wins), sorted
    by year. A sheet of a level is split at each of its level's `splits` years (the years of another level's
    survey, Shizuoka's FY2022 on its quadrant sheets): its files newer and older than such a year make two sheets
    of their own, so an older file never wins over a newer survey of the other level (39 sheets of 400 x 300 m of
    FY2021 and FY2025 under FY2022's 1000 x 750 m sheets, 2026-11-15); decided from the sheet's own files, a sheet of
    FY2021 and FY2025 outside the quadrant sheets (5 of 44) is split as well."""

    def __init__(self, folder: str, crs: str, native_res: float, levels: Dict[str, MetricCellTiling],
                 splits: Optional[Dict[str, Sequence[int]]] = None):
        self.folder, self.crs, self.native_res, self.levels = folder, crs, native_res, levels
        self.splits = {level: tuple(years) for level, years in (splits or {}).items()}
        self.index: Optional[CachedIndex] = None  # bound by the layer: cached() reads the owners' answers

    # --- owners ------------------------------------------------------------------------------------------------
    def owners(self, level: str, cells: Sequence[Tuple[int, int]]) -> List[Tuple[float, float]]:
        """The owner index tile (south-west corner, as osm.tiles gives it) of each sheet: the tile holding its
        centre."""
        if not len(cells):
            return []
        w, h = self.levels[level].cell
        x0, y0 = self.levels[level].origin
        xs = [x0 + (i + 0.5) * w for i, _ in cells]
        ys = [y0 + (j + 0.5) * h for _, j in cells]
        lons, lats = rasterio.warp.transform(self.crs, "EPSG:4326", xs, ys)
        size = osm.TILE_DEG
        return [(math.floor(lat / size) * size, math.floor(lon / size) * size) for lat, lon in zip(lats, lons)]

    def owned(self, items: Sequence[Dict], lat: float, lon: float) -> List[Dict]:
        """The items of an answer whose sheets the tile (lat, lon) owns."""
        by_level: Dict[str, List[Dict]] = {}
        for item in items:
            by_level.setdefault(item["level"], []).append(item)
        kept = []
        for level, its in by_level.items():
            for item, owner in zip(its, self.owners(level, [tuple(it["cell"]) for it in its])):
                if owner == (lat, lon):
                    kept.append(item)
        return kept

    def _answer(self, index: CachedIndex, cache_dir: str, lat: float, lon: float,
                update: Optional[str] = None) -> List[Dict]:
        """The items of the sheets a tile owns, from its answer (asked when not cached)."""
        return self.owned(index.answers(cache_dir, lat, lon, update), lat, lon)

    def tiles_to_ask(self, grid: Grid) -> List[Tuple[float, float]]:
        """The owner tiles of the sheets the grid meets: its own index tiles (index_tiles: a sheet whose centre lies
        in the grid's box, or within 0.01 degree of its outline, is owned by one of them) and the owners of the
        sheets across the edges of its box (their centres may lie in a tile beyond)."""
        found = set(index_tiles(grid))
        left, bottom, right, top = transform_bounds(grid.crs, self.crs, *grid.bounds)
        for level, tiling in self.levels.items():
            (i0, j0), (i1, j1) = tiling.cell_of(left, bottom), tiling.cell_of(right, top)
            edge = {(i, j) for i in range(i0, i1 + 1) for j in (j0, j1)} | \
                {(i, j) for j in range(j0, j1 + 1) for i in (i0, i1)}
            edge = [c for c in edge if tiling.name(*c) is not None]
            if grid.area_shape is not None and edge:  # only the sheets under the outline
                import shapely
                from area import project
                shape = project(grid.area_shape, grid.crs, self.crs)
                hit = shapely.intersects(shape, shapely.box(*np.array([tiling.edges(c) for c in edge]).T))
                edge = [c for c, h in zip(edge, hit) if h]
            found.update(self.owners(level, edge))
        return sorted(found)

    # --- the sets of files -------------------------------------------------------------------------------
    @staticmethod
    def _key(files: Sequence[File]) -> str:
        return hashlib.sha1(",".join(sorted(f[0] for f in files)).encode()).hexdigest()[:8]

    def _box(self, level: str, i: int, j: int) -> Tuple[float, float, float, float]:
        return self.levels[level].edges((i, j))

    def sets(self, items: Sequence[Dict]) -> List[SheetSet]:
        """The sheets of the listed files (of their owners' answers), newest first (then by level and place),
        each split at its level's `splits` years; a file listed twice taken once."""
        groups: Dict[Tuple[str, int, int], List[Dict]] = {}
        seen = set()
        for item in items:
            if item["url"] in seen:
                continue
            seen.add(item["url"])
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
        """The sheets over the grid, each from its owner's answer only."""
        items = [item for lat, lon in self.tiles_to_ask(grid) for item in self._answer(index, cache_dir, lat, lon,
                                                                                         update)]
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
        return glob.glob(os.path.join(glob.escape(cache_dir), self.folder, "**", "*.tif"), recursive=True)

    def _named(self, cache_dir: str, sheets: List[SheetSet]) -> Dict[Tuple[str, int, int], set]:
        """The keys the owners' cached answers name for each of these sheets (no request; a sheet whose owner's
        answer is not cached has none)."""
        named: Dict[Tuple[str, int, int], set] = {}
        if self.index is None:
            return named
        places = sorted({(s.level, s.i, s.j) for s in sheets})
        by_owner: Dict[Tuple[float, float], List[Tuple[str, int, int]]] = {}
        for level in {p[0] for p in places}:
            cells = [(i, j) for lv, i, j in places if lv == level]
            for cell, owner in zip(cells, self.owners(level, cells)):
                by_owner.setdefault(owner, []).append((level, *cell))
        for (lat, lon), owned in by_owner.items():
            path = self.index.index_path(cache_dir, lat, lon)
            try:
                with open(path, encoding="utf-8") as f:
                    items = self.owned(json.load(f)["sheets"], lat, lon)
            except (OSError, ValueError, KeyError):
                continue
            wanted = set(owned)
            for s in self.sets(items):
                if (s.level, s.i, s.j) in wanted:
                    named.setdefault((s.level, s.i, s.j), set()).add(s.key)
        return named

    def cached(self, grid: Grid, cache_dir: str) -> list:
        """The cached sheets over the grid (the index cannot be asked), by survey as a search orders them (newest
        first, then level and place). A set the owner's last known answer no longer names goes behind a named set
        only when that one is the newer upload of the same files (the same sheet, file names and years, another
        ETag); otherwise it keeps its place by year (an upload whose newer download is not cached yet is read)."""
        sheets = self._within([s for s in (self._sheet_of(p) for p in self._cached_paths(cache_dir)) if s is not None],
                              grid)
        named = self._named(cache_dir, sheets)
        stems: Dict[SheetSet, frozenset] = {}

        def stems_of(s: SheetSet) -> frozenset:
            if s not in stems:
                try:
                    with rio.open(self.path(cache_dir, s)) as src:
                        tags = src.tags()
                    stems[s] = frozenset(n.split("@", 1)[0] for n in (tags.get("files") or tags.get("sources", ""))
                                         .split(",") if n)
                except rio.errors.RasterioIOError:
                    stems[s] = frozenset()
            return stems[s]

        def superseded(s: SheetSet) -> bool:
            keys = named.get((s.level, s.i, s.j))
            if keys is None or s.key in keys:
                return False
            return any(o.key in keys and (o.level, o.i, o.j) == (s.level, s.i, s.j) and o.year == s.year
                       and stems_of(o) == stems_of(s) for o in sheets)
        return sorted(sheets, key=lambda s: (-s.year, s.level, -s.j, s.i, superseded(s)))

    def prune(self, cache_dir: str, tiles: List[SheetSet]) -> int:
        """Once every current set of a sheet (tiles: those of its owner's answer) is cached (or recorded as without
        data), delete the sheet's
        other cached files (an older upload, a set whose newest file is gone, a file of before a split); never
        before the current ones are in place, never a file of another sheet; how many."""
        current: Dict[Tuple[str, int, int], List[SheetSet]] = {}
        for s in tiles:
            current.setdefault((s.level, s.i, s.j), []).append(s)
        older = []
        places = list(current.items())
        paths = [self.path(cache_dir, s) for _, sheets in places for s in sheets]
        # in place: a file, or recorded as missing (a current set without data: nothing more will come)
        due = dict(zip(paths, cache.due_many(cache_dir, paths))) if paths else {}
        for place, sheets in places:
            if not all(os.path.exists(self.path(cache_dir, s)) or not due[self.path(cache_dir, s)] for s in sheets):
                continue
            keys = {s.key for s in sheets}
            folder = os.path.dirname(self.path(cache_dir, sheets[0]))
            if not os.path.isdir(folder):  # every current set without data, never a file there (a lake's sheet)
                continue
            for name in os.listdir(folder):
                other = self._sheet_of(os.path.join(folder, name))
                if other is not None and (other.level, other.i, other.j) == place and other.key not in keys:
                    older.append(os.path.join(folder, name))
        cache.forget(cache_dir, older)
        return len(older)

    def update_tile(self, index: CachedIndex, cache_dir: str, lat: float, lon: float) -> Tuple[list, list]:
        """For the cached sheets the tile owns, asked again: the current sets not cached yet (to read), and every
        current set of those sheets (prune keeps them and deletes the rest once they are all cached). The same
        sets and keys as a search's, which reads the same answer."""
        now: Dict[Tuple[str, int, int], List[SheetSet]] = {}
        for s in self.sets(self._answer(index, cache_dir, lat, lon, "all")):
            now.setdefault((s.level, s.i, s.j), []).append(s)
        cached = {(c.level, c.i, c.j) for c in (self._sheet_of(p) for p in self._cached_paths(cache_dir))
                  if c is not None}
        todo, keep = [], []
        for place in sorted(cached & set(now)):
            for s in now[place]:
                keep.append(s)
                if not os.path.exists(self.path(cache_dir, s)):
                    todo.append(s)
        return todo, keep

    def has_data_near(self, index: CachedIndex, lat: float, lon: float, cache_dir: str,
                      metres: float = 2000) -> Optional[bool]:
        """Whether a listed sheet lies within `metres` of the point (the answers of the tiles within that reach,
        each read for the sheets it owns)."""
        xs, ys = rasterio.warp.transform("EPSG:4326", self.crs, [lon], [lat])
        x, y = xs[0], ys[0]
        west, south, east, north = transform_bounds(self.crs, "EPSG:4326", x - metres, y - metres, x + metres,
                                                    y + metres)
        try:
            items = [item for tile in osm.tiles(west, south, east, north)
                     for item in self._answer(index, cache_dir, *tile)]
        except requests.RequestException:
            return None
        for item in items:
            left, bottom, right, top = self._box(item["level"], *item["cell"])
            if left - metres <= x <= right + metres and bottom - metres <= y <= top + metres:
                return True
        return False
