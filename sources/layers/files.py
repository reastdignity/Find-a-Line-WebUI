"""FileLayer: a local raster file."""

import os
from typing import Dict

import rasterio as rio

from grid import Grid

from ..layer import Layer


class FileLayer(Layer):
    """A local raster file; nothing to download."""

    def __init__(self, description: str, path: str):
        self.description, self.path = description, path
        with rio.open(path) as src:
            crs = src.crs
            res = abs(src.res[0])
            self.native_res = res * 111320 if crs is not None and crs.is_geographic else res

    def tiles(self, grid: Grid):
        return [self.path]

    def tile_path(self, cache_dir: str, tile) -> str:
        return tile

    def missing(self, grid, cache_dir, update):
        return []

    def used(self, grid: Grid, cache_dir: str) -> Dict:
        return {"layer": self.description, "file": os.path.abspath(self.path)}
