"""Fixed tilings: the tiles over a grid computed from its bounds, no service asked."""

import math
import os
import re
from typing import Callable, Optional, Tuple

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


class WcsTiling(Index):
    """Square tiles of tile_px pixels on a fixed grid in the service's CRS, at fetch_res
    (None: the working resolution), cached as <folder>/<crs>-<res>m-<px>px-<format>/<i>_<j>.tif.

    The tiles of a circle are those reaching into the circle inscribed in the grid's box;
    of an area, those under its outline. Tiles hold the data where the service puts it,
    i.e. before the shift correction of the layer.
    """

    def __init__(self, crs: str, folder: str, tile_px: int, fmt: str, fetch_res: Optional[float],
                 shift: Tuple[float, float] = (0.0, 0.0)):
        self.crs, self.folder, self.tile_px, self.fmt = crs, folder, tile_px, fmt
        self.fetch_res, self.shift = fetch_res, shift

    def tiles(self, grid: Grid):
        res = self.fetch_res or grid.res
        size = self.tile_px * res
        left, bottom, right, top = transform_bounds(grid.crs, self.crs, *grid.bounds)
        # Tiles hold the data where the service puts it, i.e. before the shift correction
        cx, cy, radius = (left + right) / 2 - self.shift[0], (bottom + top) / 2 - self.shift[1], (right - left) / 2
        shape = None
        if grid.area_shape is not None:
            from area import project
            from shapely.affinity import translate
            shape = translate(project(grid.area_shape, grid.crs, self.crs), -self.shift[0], -self.shift[1])
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
        return f"{self.crs.lower().replace(':', '')}-{res:g}m-{self.tile_px}px-{fmt}"

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
        res, i, j = tile
        size = self.tile_px * res
        return transform_bounds(self.crs, "EPSG:4326", i * size, j * size, (i + 1) * size, (j + 1) * size)
