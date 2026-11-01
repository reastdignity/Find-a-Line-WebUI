"""Fixed tilings: the tiles over a grid computed from its bounds, no service asked."""

import math
import os
import re
from typing import Callable, Optional, Sequence, Tuple, Union

from rasterio.transform import from_origin
from rasterio.warp import transform_bounds

from grid import Grid

from ..layer import _hemi
from ..composed import Index
from ..readers.tilebases import grid_tile_name
from ..readers.windows import BlockRequest


class MetricTiling(Index):
    """Square tiles of tile_m on a fixed grid in a metric CRS, cached as
    <folder>/<grid_tile_name>: tile (i, j) covers [i, i + 1) x [j, j + 1) tile sizes."""

    def __init__(self, crs: str, folder: str, tile_m: float):
        self.crs, self.folder, self.tile_m = crs, folder, tile_m

    def tiles(self, grid: Grid):
        left, bottom, right, top = transform_bounds(grid.crs, self.crs, *grid.bounds)
        shape = None
        if grid.area_shape is not None:
            from area import project
            shape = project(grid.area_shape, grid.crs, self.crs)
        found = []
        for j in range(math.floor(bottom / self.tile_m), math.floor(top / self.tile_m) + 1):
            for i in range(math.floor(left / self.tile_m), math.floor(right / self.tile_m) + 1):
                if shape is not None:
                    from shapely.geometry import box
                    if not shape.intersects(box(i * self.tile_m, j * self.tile_m,
                                                (i + 1) * self.tile_m, (j + 1) * self.tile_m)):
                        continue
                found.append((i, j))
        return found

    def path(self, cache_dir: str, tile) -> str:
        return os.path.join(cache_dir, self.folder, grid_tile_name(*tile))


class DegreeTiling(Index):
    """1°×1° tiles in WGS84 (lat, lon of the south-west corner), cached as <folder>/N50E019.tif."""

    def __init__(self, folder: str):
        self.folder = folder

    def tiles(self, grid: Grid):
        west, south, east, north = transform_bounds(grid.crs, "EPSG:4326", *grid.bounds)
        return [(lat, lon) for lat in range(math.floor(south), math.floor(north) + 1)
                for lon in range(math.floor(west), math.floor(east) + 1)]

    def path(self, cache_dir: str, tile) -> str:
        lat, lon = tile
        return os.path.join(cache_dir, self.folder, f"{_hemi(lat, 'N', 'S', 2)}{_hemi(lon, 'E', 'W', 3)}.tif")


def degree_tile_name(i: int, j: int) -> str:
    """The 1° tile of a block of 0.1°, named by its north-west corner (n38w120: 37-38° N, 120-119° W)."""
    return f"{_hemi(j // 10 + 1, 'n', 's', 2)}{_hemi(i // 10, 'e', 'w', 3)}"


class TenthDegreeTiling(Index):
    """Blocks of 0.1° in a geographic CRS of 1° files at a fixed URL per file (url(name of
    the 1° tile)): block (i, j) covers [i, i + 1) × [j, j + 1) tenths of a degree, cached in
    <folder>/<1° tile>/<i>_<j>.tif, read on the files' own pixels (px_per_degree)."""

    def __init__(self, crs: str, folder: str, px_per_degree: int, url: Callable[[str], str]):
        self.crs, self.folder, self.px_per_degree, self.url = crs, folder, px_per_degree, url

    def tiles(self, grid: Grid) -> list:
        west, south, east, north = transform_bounds(grid.crs, self.crs, *grid.bounds)
        shape = None
        if grid.area_shape is not None:
            from area import project
            shape = project(grid.area_shape, grid.crs, self.crs)
        found = []
        for j in range(math.floor(south * 10), math.floor(north * 10) + 1):
            for i in range(math.floor(west * 10), math.floor(east * 10) + 1):
                if shape is not None:
                    from shapely.geometry import box
                    if not shape.intersects(box(i / 10, j / 10, (i + 1) / 10, (j + 1) / 10)):
                        continue
                found.append((i, j))
        return found

    def path(self, cache_dir: str, tile) -> str:
        return os.path.join(cache_dir, self.folder, degree_tile_name(*tile), f"{tile[0]}_{tile[1]}.tif")

    def tile_of(self, path: str):
        match = re.fullmatch(rf"{re.escape(self.folder)}/([ns]\d\d[ew]\d\d\d)/(-?\d+)_(-?\d+)\.tif", path)
        if not match or degree_tile_name(int(match.group(2)), int(match.group(3))) != match.group(1):
            return None
        return int(match.group(2)), int(match.group(3))

    def bounds_wgs84(self, tile) -> Tuple[float, float, float, float]:
        i, j = tile
        return i / 10, j / 10, (i + 1) / 10, (j + 1) / 10

    def request(self, tile) -> BlockRequest:
        i, j = tile
        name = degree_tile_name(i, j)
        px = self.px_per_degree // 10
        transform = from_origin(i / 10, (j + 1) / 10, 1 / self.px_per_degree, 1 / self.px_per_degree)
        return BlockRequest([(name, self.url(name), 0)], self.crs, transform, (px, px))


FileList = Sequence[Tuple[str, str, int]]  # (name, url, survey year), newest first


class FileBlockTiling(Index):
    """Blocks of block_m in a metric CRS, on the pixels of big fixed files (pixel size res,
    pixel edges on origin + multiples of res: (0.5, 0.5) for files whose pixel centres are on
    whole metres) read by HTTP range requests (the Windows reader).

    Block (i, j) covers [i, i + 1) x [j, j + 1) block sizes from origin, cached as
    <folder>/<i // GROUP>_<j // GROUP>/<i>_<j>.tif (at most GROUP² blocks per folder). The
    files of a block, newest first, come from files(i, j); a block must lie inside each of
    them (a fixed grid of files: block_m divides the files' size, and neighbouring files that
    overlap by one pixel still hold their blocks whole). A block without files is missing
    without a request, and so is one outside extent (left, bottom, right, top in crs; None:
    anywhere). files may be the address of one file (a national COG) instead, read by every
    block.
    """
    GROUP = 50

    def __init__(self, crs: str, folder: str, res: float, block_m: float,
                 files: Union[str, Callable[[int, int], FileList]], origin: Tuple[float, float] = (0.0, 0.0),
                 extent: Optional[Tuple[float, float, float, float]] = None, year: int = 0):
        self.crs, self.folder, self.res, self.block_m, self.origin = crs, folder, res, block_m, origin
        self.extent = extent
        if isinstance(files, str):
            one = [(files.rstrip("/").rsplit("/", 1)[-1], files, year)]

            def files(i: int, j: int) -> FileList:
                return one
        self.files = files
        self.px = round(block_m / res)
        if not math.isclose(self.px * res, block_m):
            raise ValueError(f"blocks of {block_m} m are not whole pixels of {res} m")

    def _edges(self, i: int, j: int) -> Tuple[float, float, float, float]:
        """(left, bottom, right, top) of a block."""
        ox, oy = self.origin
        return (i * self.block_m + ox, j * self.block_m + oy, (i + 1) * self.block_m + ox,
                (j + 1) * self.block_m + oy)

    def _within_extent(self, i: int, j: int) -> bool:
        if self.extent is None:
            return True
        left, bottom, right, top = self._edges(i, j)
        e_left, e_bottom, e_right, e_top = self.extent
        return left < e_right and right > e_left and bottom < e_top and top > e_bottom

    def tiles(self, grid: Grid) -> list:
        left, bottom, right, top = transform_bounds(grid.crs, self.crs, *grid.bounds)
        ox, oy = self.origin
        shape = None
        if grid.area_shape is not None:
            from area import project
            shape = project(grid.area_shape, grid.crs, self.crs)
        found = []
        for j in range(math.floor((bottom - oy) / self.block_m), math.floor((top - oy) / self.block_m) + 1):
            for i in range(math.floor((left - ox) / self.block_m), math.floor((right - ox) / self.block_m) + 1):
                if shape is not None:
                    from shapely.geometry import box
                    if not shape.intersects(box(*self._edges(i, j))):
                        continue
                found.append((i, j))
        return found

    def path(self, cache_dir: str, tile) -> str:
        i, j = tile
        return os.path.join(cache_dir, self.folder, f"{i // self.GROUP}_{j // self.GROUP}", f"{i}_{j}.tif")

    def tile_of(self, path: str):
        match = re.fullmatch(rf"{re.escape(self.folder)}/(-?\d+)_(-?\d+)/(-?\d+)_(-?\d+)\.tif", path)
        if not match:
            return None
        gi, gj, i, j = (int(g) for g in match.groups())
        return (i, j) if (gi, gj) == (i // self.GROUP, j // self.GROUP) else None

    def bounds_wgs84(self, tile) -> Tuple[float, float, float, float]:
        return transform_bounds(self.crs, "EPSG:4326", *self._edges(*tile))

    def request(self, tile) -> BlockRequest:
        left, _, _, top = self._edges(*tile)
        files = list(self.files(*tile)) if self._within_extent(*tile) else []
        return BlockRequest(files, self.crs, from_origin(left, top, self.res, self.res),
                            (self.px, self.px))


class WcsTiling(Index):
    """Square tiles of tile_px pixels on a fixed grid in the service's CRS, at fetch_res
    (None: the working resolution), cached as <folder>/<crs>-<res>m-<px>px-<format>/<i>_<j>.tif.
    Tile (i, j) covers [i, i + 1) x [j, j + 1) tile sizes from origin (x, y in metres: the
    pixel edges of a coverage whose edges are not on whole multiples of its resolution, so
    tiles are requested on its own pixels; (0, 0) for most services). A tiling with an origin
    has it in its folder's name too (-o<x>_<y>), and one whose reader drops edge_px pixels at
    the edges of the data (WcsReader) -e<edge_px>.

    The tiles of a circle are those reaching into the circle inscribed in the grid's box;
    of an area, those under its outline. Tiles hold the data where the service puts it,
    i.e. before the shift correction of the layer.
    """

    def __init__(self, crs: str, folder: str, tile_px: int, fmt: str, fetch_res: Optional[float],
                 shift: Tuple[float, float] = (0.0, 0.0), origin: Tuple[float, float] = (0.0, 0.0),
                 edge_px: int = 0):
        self.crs, self.folder, self.tile_px, self.fmt = crs, folder, tile_px, fmt
        self.fetch_res, self.shift, self.origin, self.edge_px = fetch_res, shift, origin, edge_px

    def edges(self, tile) -> Tuple[float, float, float, float]:
        """(left, bottom, right, top) of a tile in the service's CRS."""
        res, i, j = tile
        size = self.tile_px * res
        ox, oy = self.origin
        return i * size + ox, j * size + oy, (i + 1) * size + ox, (j + 1) * size + oy

    def tiles(self, grid: Grid):
        res = self.fetch_res or grid.res
        size = self.tile_px * res
        left, bottom, right, top = transform_bounds(grid.crs, self.crs, *grid.bounds)
        # Tiles hold the data where the service puts it, i.e. before the shift correction;
        # the centre is counted from the tiling's origin
        ox, oy = self.origin
        cx, cy = (left + right) / 2 - self.shift[0] - ox, (bottom + top) / 2 - self.shift[1] - oy
        radius = (right - left) / 2
        shape = None
        if grid.area_shape is not None:
            from area import project
            from shapely.affinity import translate
            shape = translate(project(grid.area_shape, grid.crs, self.crs), -self.shift[0] - ox, -self.shift[1] - oy)
        tiles = []
        for i in range(math.floor((cx - radius) / size), math.floor((cx + radius) / size) + 1):
            for j in range(math.floor((cy - radius) / size), math.floor((cy + radius) / size) + 1):
                if shape is not None:  # any area: the tiles under its outline
                    from shapely.geometry import box
                    if shape.intersects(box(i * size, j * size, (i + 1) * size, (j + 1) * size)):
                        tiles.append((res, i, j))
                    continue
                dx = max(i * size - cx, 0, cx - (i + 1) * size)  # nearest point of the tile
                dy = max(j * size - cy, 0, cy - (j + 1) * size)
                if dx * dx + dy * dy <= radius * radius:
                    tiles.append((res, i, j))
        return tiles

    def _tiling(self, res: float) -> str:
        # The tiling in the path: tiles of another CRS, size or format never mix
        fmt = "asc" if re.search(r"aaigrid|asc", self.fmt) else "tif"
        origin = f"-o{self.origin[0]:g}_{self.origin[1]:g}" if self.origin != (0.0, 0.0) else ""
        edge = f"-e{self.edge_px}" if self.edge_px else ""
        return f"{self.crs.lower().replace(':', '')}-{res:g}m-{self.tile_px}px-{fmt}{origin}{edge}"

    def path(self, cache_dir: str, tile) -> str:
        res, i, j = tile
        return os.path.join(cache_dir, self.folder, self._tiling(res), f"{i}_{j}.tif")

    def tile_of(self, path: str):
        match = re.fullmatch(rf"{re.escape(self.folder)}/([^/]+)/(-?\d+)_(-?\d+)\.tif", path)
        if not match:
            return None
        res = float(re.search(r"-([\d.]+)m-", match.group(1)).group(1))
        return (res, int(match.group(2)), int(match.group(3))) if match.group(1) == self._tiling(res) else None

    def bounds_wgs84(self, tile) -> Tuple[float, float, float, float]:
        """(west, south, east, north) of a tile."""
        return transform_bounds(self.crs, "EPSG:4326", *self.edges(tile))
