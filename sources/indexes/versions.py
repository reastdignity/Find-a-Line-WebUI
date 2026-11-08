"""Version policies of a cached index: the newest survey per sheet or tile (NewestPerSheet), or blocks
composed from every file over them, newest first (ComposedBlocks)."""

import glob
import hashlib
import math
import os
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import rasterio as rio
import rasterio.warp
import requests
from rasterio.transform import from_origin
from rasterio.warp import transform_bounds

import cache
import osm
from grid import Grid

from ..readers.windows import BlockRequest, _same_crs
from .cached import CachedIndex, Versions, index_tiles


@dataclass(frozen=True)
class Sheet:
    """One file of a tile index: a map sheet or a tile of one survey (see NewestPerSheet)."""
    year: int
    name: str   # file name without extension, e.g. 77532_1356765_M-34-64-D-a-1-1
    godlo: str  # the sheet or tile it covers; the newest survey of each is used
    url: str
    crs: str
    res: float
    sha256: Optional[str] = None  # of the file, when the index gives it


def _sheet_order(sheet: Sheet) -> tuple:
    """Newer year first; within a year, the later publication (higher numbers in the file name)."""
    return (sheet.year,) + tuple(int(n) for n in re.findall(r"\d+", sheet.name)[:2])


def _answers(index: CachedIndex, cache_dir: str, tiles: List[Tuple[float, float]],
             update: Optional[str]) -> List[List[Dict]]:
    """The listed versions of each 0.25° tile (south-west corners), in the order of the tiles.
    A listing that says so (`tiles_at_once`: WfsSheets, whose requests take slots of their host)
    is asked for that many tiles at once, each under its tile's lock (CachedIndex.answers), and
    first told the data folder (`use`); the others one tile after another, as before. An error
    is the first in the order of the tiles."""
    listing = index.listing
    use = getattr(listing, "use", None)
    if use is not None:
        use(index, cache_dir, update)
    at_once = min(getattr(listing, "tiles_at_once", 1), len(tiles))
    if at_once <= 1:
        return [index.answers(cache_dir, lat, lon, update) for lat, lon in tiles]
    with ThreadPoolExecutor(max_workers=at_once, thread_name_prefix="index-tiles") as pool:
        return list(pool.map(lambda tile: index.answers(cache_dir, *tile, update), tiles))


class NewestPerSheet(Versions):
    """One file per sheet or tile (godło) and survey; for every godło only the newest survey
    is used, and the files are ordered newest first, so where sheets of different series
    overlap the newest data wins in the mosaic. Each file is cached as a GeoTIFF named
    <year>_<name>.tif in folder. The listed extents are in index_crs.

    With sizes (bytes per tile of each resolution used: swisstopo's tiles at 0.5 and 2 m) a
    godło is a tile at one resolution, so the newest survey and pruning work per resolution;
    a grid uses the coarsest resolution not coarser than itself (res_for), cached in
    <folder>/<res>m/. A listed sha256 is kept with its sheet.
    """

    def __init__(self, folder: str, index_crs: str, native_res: float, sizes: Optional[Dict[float, float]] = None):
        self.folder, self.index_crs, self.native_res, self.sizes = folder, index_crs, native_res, sizes
        self._versions: Dict[str, set] = {}  # every listed survey of a godło

    def sheet(self, item: Dict) -> Sheet:
        if self.sizes:
            return Sheet(item["year"], item["godlo"], f"{item['godlo']}/{item['res']:g}m", item["url"],
                         item["crs"], item["res"], item.get("sha256"))
        url = item["url"]
        return Sheet(item["year"], re.sub(r"(\.[a-z]+)+$", "", url.rsplit("/", 1)[-1], flags=re.I),
                     item["godlo"], url, item["crs"], item["res"])

    def res_for(self, grid: Grid) -> float:
        """The resolution used for a grid: the coarsest one not coarser than the grid."""
        fitting = [r for r in self.sizes if r <= grid.res + 1e-6]
        return max(fitting) if fitting else min(self.sizes)

    def _wanted(self, sheet: Sheet, grid: Grid) -> bool:
        """Whether a listed file is used for this grid."""
        return sheet.res == self.res_for(grid) if self.sizes else True

    def query(self, index: CachedIndex, grid: Grid, cache_dir: str, update: Optional[str]) -> list:
        """The newest sheet per godło over the grid, newest first."""
        g_left, g_bottom, g_right, g_top = transform_bounds(grid.crs, self.index_crs, *grid.bounds)
        shape = None
        if grid.area_shape is not None:
            import shapely
            from area import project
            from shapely.geometry import box
            shape = project(grid.area_shape, grid.crs, self.index_crs).intersection(
                box(g_left, g_bottom, g_right, g_top))
            shapely.prepare(shape)  # tested against every sheet listed, a country's outline has many vertices
        newest: Dict[str, Sheet] = {}
        for items in _answers(index, cache_dir, index_tiles(grid), update):
            for item in items:
                left, bottom, right, top = item["extent"]
                if not (left < g_right and right > g_left and bottom < g_top and top > g_bottom):
                    continue
                if shape is not None and not shape.intersects(box(left, bottom, right, top)):
                    continue
                sheet = self.sheet(item)
                if not self._wanted(sheet, grid):
                    continue
                self._versions.setdefault(sheet.godlo, set()).add(sheet)
                old = newest.get(sheet.godlo)
                if old is None or _sheet_order(sheet) > _sheet_order(old):
                    newest[sheet.godlo] = sheet
        return sorted(newest.values(), key=_sheet_order, reverse=True)

    def path(self, cache_dir: str, tile) -> str:
        if self.sizes:
            return os.path.join(cache_dir, self.folder, f"{tile.res:g}m", f"{tile.year}_{tile.name}.tif")
        return os.path.join(cache_dir, self.folder, f"{tile.year}_{tile.name}.tif")

    def prune(self, cache_dir: str, tiles: List[Sheet]) -> int:
        older = []
        for sheet in tiles:
            if os.path.exists(self.path(cache_dir, sheet)):
                older += [self.path(cache_dir, v) for v in self._versions.get(sheet.godlo, ())
                          if v != sheet and os.path.exists(self.path(cache_dir, v))]
        cache.forget(cache_dir, older)
        return len(older)

    def update_tile(self, index: CachedIndex, cache_dir: str, lat: float, lon: float) -> Tuple[list, list]:
        """The newer surveys of the cached sheets of one tile, and the newest of every sheet."""
        listed = [self.sheet(item) for item in _answers(index, cache_dir, [(lat, lon)], "all")[0]]
        newest: Dict[str, Sheet] = {}
        for sheet in listed:
            self._versions.setdefault(sheet.godlo, set()).add(sheet)
            if sheet.godlo not in newest or _sheet_order(sheet) > _sheet_order(newest[sheet.godlo]):
                newest[sheet.godlo] = sheet
        cached = {s.godlo for s in listed if os.path.exists(self.path(cache_dir, s))}
        todo = [s for g, s in newest.items() if g in cached and not os.path.exists(self.path(cache_dir, s))]
        return todo, list(newest.values())

    def _cached_files(self, grid: Grid, cache_dir: str) -> Tuple[List[str], float]:
        """The cached files that could be used for this grid, and their resolution."""
        if self.sizes:
            res = self.res_for(grid)
            return glob.glob(os.path.join(cache_dir, self.folder, f"{res:g}m", "*.tif")), res
        return glob.glob(os.path.join(cache_dir, self.folder, "*.tif")), self.native_res

    def cached(self, grid: Grid, cache_dir: str) -> list:
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


@dataclass(frozen=True)
class Block:
    """A square of a TnmBlocks layer: (i, j) on a grid of `size` metres in crs, composed from
    the files (name, url, survey year), newest first. The key tells sets of files apart: a new survey over
    the block gives it another key, so it is read again."""
    crs: str
    i: int
    j: int
    size: float
    year: int  # of the newest file
    key: str
    files: Tuple[Tuple[str, str, int], ...] = ()


class ComposedBlocks(Versions):
    """Squares of block_m on a fixed grid in the CRS of the listed files, each composed from
    every file over it, newest first (Windows reads them), cached as a GeoTIFF of its own:
    <folder>/<epsg>/<i // 10>_<j // 10>/<year>_<i>_<j>_<key>.tif, the key standing for its set
    of files. A new file over a block changes its key, so the block is read again (update.py,
    or a search after the answer was renewed) and the file of the older set deleted. Blocks
    in the working CRS come first: copied onto the grid as they are, they win where a tile
    is delivered in two UTM zones. The listed items are {name, url, crs, extent (in crs),
    year, published}.
    """

    def __init__(self, folder: str, block_m: float, native_res: float):
        self.folder, self.block_m, self.native_res = folder, block_m, native_res

    def _items(self, index: CachedIndex, cache_dir: str, west: float, south: float, east: float, north: float,
               update: Optional[str] = None) -> List[Dict]:
        """The listed files of the index tiles over a box (WGS84)."""
        return self._items_of(index, cache_dir, osm.tiles(west, south, east, north), update)

    @staticmethod
    def _items_of(index: CachedIndex, cache_dir: str, tiles: List[Tuple[float, float]],
                  update: Optional[str] = None) -> List[Dict]:
        """The listed files of the given index tiles (south-west corners), each file once."""
        items: Dict[str, Dict] = {}
        for lat, lon in tiles:
            for item in index.answers(cache_dir, lat, lon, update):
                items[item["url"]] = item
        return list(items.values())

    def _blocks(self, items: List[Dict], bounds: Dict[str, tuple], shape=None) -> List[Block]:
        """The blocks within bounds (per CRS: left, bottom, right, top), and under the shape
        (in WGS84) if given, with the files over each, newest first."""
        size = self.block_m
        over: Dict[tuple, List[Dict]] = {}
        for item in items:
            if item["crs"] not in bounds:
                continue
            left, bottom, right, top = bounds[item["crs"]]
            e_left, e_bottom, e_right, e_top = item["extent"]
            left, bottom, right, top = max(left, e_left), max(bottom, e_bottom), min(right, e_right), min(top, e_top)
            if left >= right or bottom >= top:
                continue
            for i in range(math.floor(left / size), math.ceil(right / size)):
                for j in range(math.floor(bottom / size), math.ceil(top / size)):
                    over.setdefault((item["crs"], i, j), []).append(item)
        if shape is not None:
            import shapely
            from area import project
            from shapely.geometry import box
            projected = {crs: project(shape, "EPSG:4326", crs) for crs in bounds}
            for outline in projected.values():
                shapely.prepare(outline)  # tested against every block: a country's outline has many vertices
            over = {k: v for k, v in over.items()
                    if projected[k[0]].intersects(box(k[1] * size, k[2] * size, (k[1] + 1) * size, (k[2] + 1) * size))}
        blocks = []
        for (crs, i, j), files in over.items():
            files = sorted(files, key=lambda f: (f["year"], f.get("published", ""), f["name"]), reverse=True)
            key = hashlib.sha1(",".join(sorted(f["name"] for f in files)).encode()).hexdigest()[:8]
            blocks.append(Block(crs, i, j, size, files[0]["year"], key,
                                tuple((f["name"], f["url"], f["year"]) for f in files)))
        return blocks

    def query(self, index: CachedIndex, grid: Grid, cache_dir: str, update: Optional[str]) -> list:
        items = self._items_of(index, cache_dir, index_tiles(grid), update)
        bounds = {crs: transform_bounds(grid.crs, crs, *grid.bounds) for crs in {item["crs"] for item in items}}
        shape = None
        if grid.area_shape is not None:
            from area import project
            shape = project(grid.area_shape, grid.crs, "EPSG:4326")
        # Blocks in the working CRS first: copied onto the grid as they are, they win where
        # a tile is delivered in two UTM zones
        return sorted(self._blocks(items, bounds, shape),
                      key=lambda b: (not _same_crs(b.crs, grid.crs), b.crs, b.j, b.i))

    def path(self, cache_dir: str, tile) -> str:
        return os.path.join(cache_dir, self.folder, tile.crs.lower().replace(":", ""),
                            f"{tile.i // 10}_{tile.j // 10}", f"{tile.year}_{tile.i}_{tile.j}_{tile.key}.tif")

    def request(self, tile) -> BlockRequest:
        px = round(tile.size / self.native_res)
        transform = from_origin(tile.i * tile.size, (tile.j + 1) * tile.size, self.native_res, self.native_res)
        return BlockRequest(tile.files, tile.crs, transform, (px, px))

    def _block_of(self, path: str) -> Optional[Block]:
        """The block of a cached file (without its files)."""
        match = re.search(r"[\\/](epsg\d+)[\\/]-?\d+_-?\d+[\\/](\d+)_(-?\d+)_(-?\d+)_([0-9a-f]+)\.tif$", path)
        if not match:
            return None
        return Block(match.group(1).upper().replace("EPSG", "EPSG:"), int(match.group(3)), int(match.group(4)),
                     self.block_m, int(match.group(2)), match.group(5))

    def _cached_paths(self, cache_dir: str) -> List[str]:
        return glob.glob(os.path.join(cache_dir, self.folder, "epsg*", "*", "*.tif"))

    def cached(self, grid: Grid, cache_dir: str) -> list:
        blocks = []
        for path in self._cached_paths(cache_dir):
            block = self._block_of(path)
            if block is None:
                continue
            s = block.size
            left, bottom, right, top = transform_bounds(block.crs, grid.crs, block.i * s, block.j * s,
                                                        (block.i + 1) * s, (block.j + 1) * s)
            g_left, g_bottom, g_right, g_top = grid.bounds
            if left < g_right and right > g_left and bottom < g_top and top > g_bottom:
                blocks.append(block)
        return sorted(blocks, key=lambda b: (not _same_crs(b.crs, grid.crs), -b.year, b.crs, b.j, b.i))

    def _others(self, cache_dir: str, block: Block) -> List[str]:
        """The cached files of the same block made from other sets of files."""
        folder = os.path.dirname(self.path(cache_dir, block))
        found = [os.path.join(folder, n) for n in os.listdir(folder)] if os.path.isdir(folder) else []
        return [p for p in found if (b := self._block_of(p)) is not None and (b.i, b.j) == (block.i, block.j)
                and b.key != block.key]

    def prune(self, cache_dir: str, tiles: List[Block]) -> int:
        older = []
        for block in tiles:
            if os.path.exists(self.path(cache_dir, block)):
                older += self._others(cache_dir, block)
        cache.forget(cache_dir, older)
        return len(older)

    def _block_wgs84(self, block: Block) -> Tuple[float, float, float, float]:
        s = block.size
        return transform_bounds(block.crs, "EPSG:4326", block.i * s, block.j * s, (block.i + 1) * s, (block.j + 1) * s)

    def update_tile(self, index: CachedIndex, cache_dir: str, lat: float, lon: float) -> Tuple[list, list]:
        """The cached blocks (centred in the tile) over which the set of files changed: read
        again, and their older files deleted."""
        index.answers(cache_dir, lat, lon, "all")
        todo = []
        for path in self._cached_paths(cache_dir):
            block = self._block_of(path)
            if block is None:
                continue
            west, south, east, north = self._block_wgs84(block)
            if not (lat <= (south + north) / 2 < lat + osm.TILE_DEG and lon <= (west + east) / 2 < lon + osm.TILE_DEG):
                continue
            s = block.size
            inner = (block.i * s + s / 4, block.j * s + s / 4, (block.i + 1) * s - s / 4, (block.j + 1) * s - s / 4)
            now = [b for b in self._blocks(self._items(index, cache_dir, west, south, east, north), {block.crs: inner})
                   if (b.i, b.j) == (block.i, block.j)]
            if now and now[0].key != block.key and not os.path.exists(self.path(cache_dir, now[0])):
                todo.append(now[0])
        return todo, todo

    def has_data_near(self, index: CachedIndex, lat: float, lon: float, cache_dir: str,
                      metres: float = 2000) -> Optional[bool]:
        try:
            items = self._items(index, cache_dir, lon, lat, lon, lat)
        except requests.RequestException:
            return None
        for item in items:
            x, y = rio.warp.transform("EPSG:4326", item["crs"], [lon], [lat])
            left, bottom, right, top = item["extent"]
            if left - metres <= x[0] <= right + metres and bottom - metres <= y[0] <= top + metres:
                return True
        return False
