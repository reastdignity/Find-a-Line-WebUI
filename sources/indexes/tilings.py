"""Fixed tilings: the tiles over a grid computed from its bounds, no service asked."""

import math
import os

from rasterio.warp import transform_bounds

from grid import Grid

from ..composed import Index
from ..readers.tilebases import grid_tile_name


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
