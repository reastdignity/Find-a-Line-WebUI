"""The tiles of an Esri tile cache in Web Mercator (ArcGIS Online's standard tiling, level/row/col) at the level
that suits a grid, and a static mask of the cells such a cache holds data in (TileCells, made by
tools/lerc_coverage.py): no service asked."""

import math
import os
import re
from typing import Optional, Tuple

import numpy as np
from rasterio.warp import transform_bounds

from grid import Grid

from ..composed import Index
from ..readers.lerc import CELLS, MERCATOR, ORIGIN, resolution
from .tilings import _outline, cells_under, remembered

Box = Tuple[float, float, float, float]  # (left, bottom, right, top) in EPSG:3857


def tile_box(level: int, row: int, col: int) -> Box:
    """The cells of a tile in EPSG:3857 (its corners, the outer samples' positions)."""
    size = CELLS * resolution(level)
    left, top = -ORIGIN + col * size, ORIGIN - row * size
    return left, top - size, left + size, top


def tile_pixels(level: int, row: int, col: int) -> Box:
    """The pixels of a cached tile in EPSG:3857: its cells moved half a cell west and north (the samples are the
    pixel centres, the shared last row and column dropped: readers.lerc.tile_transform)."""
    half = resolution(level) / 2
    left, bottom, right, top = tile_box(level, row, col)
    return left - half, bottom + half, right - half, top + half


def level_for(res: float, lat: float, max_level: int, min_level: int = 0) -> int:
    """The coarsest level whose cell on the ground (Web Mercator's metres times the cosine of the latitude) is not
    coarser than res metres, at most max_level (the finest the data have) and at least min_level: at 55° N a 1 m
    grid takes level 17 (0.68 m), a 5 m grid level 15 (2.7 m); at 23° S a 5 m grid level 15 (4.40 m)."""
    scale = max(math.cos(math.radians(lat)), 1e-6)
    for level in range(min_level, max_level + 1):
        if resolution(level) * scale <= res * (1 + 1e-9):
            return level
    return max_level


class TileCells:
    """A static mask of where an Esri tile cache holds data: the tiles of `level` from (col0, row0), each split into
    per_tile x per_tile cells, a cell True when one of its valid samples lies in it (an .npz of
    tools/lerc_coverage.py: `bits`, numpy's packbits of the mask, its `shape` (rows, columns), `level`, `per_tile`,
    `origin` (col0, row0)). Outside the mask's rectangle: no data."""

    def __init__(self, path: str):
        self.path = path
        self._loaded = None

    def _load(self):
        if self._loaded is None:
            with np.load(self.path) as stored:
                shape = tuple(int(n) for n in stored["shape"])
                mask = np.unpackbits(stored["bits"], count=shape[0] * shape[1]).reshape(shape).astype(bool)
                level, per_tile = int(stored["level"]), int(stored["per_tile"])
                col0, row0 = (int(n) for n in stored["origin"])
            cell = CELLS * resolution(level) / per_tile
            self._loaded = (mask, cell, -ORIGIN + col0 * per_tile * cell, ORIGIN - row0 * per_tile * cell)
        return self._loaded

    def any_within(self, box: Box) -> bool:
        """Whether a cell with data meets the box (EPSG:3857; a cell touching it counts)."""
        mask, cell, x0, y0 = self._load()
        left, bottom, right, top = box
        c0, c1 = math.floor((left - x0) / cell), math.floor((right - x0) / cell)
        r0, r1 = math.floor((y0 - top) / cell), math.floor((y0 - bottom) / cell)
        c0, r0, c1, r1 = max(c0, 0), max(r0, 0), min(c1, mask.shape[1] - 1), min(r1, mask.shape[0] - 1)
        return bool(c0 <= c1 and r0 <= r1 and mask[r0:r1 + 1, c0:c1 + 1].any())

    def near(self, lat: float, lon: float, metres: float) -> bool:
        """Whether a cell with data lies within metres of a point (a square of +-metres on the ground)."""
        (x,), (y,) = _to_mercator([lon], [lat])
        half = metres / max(math.cos(math.radians(lat)), 1e-6)  # Web Mercator's metres at the latitude
        return self.any_within((x - half, y - half, x + half, y + half))


def _to_mercator(lons, lats):
    from rasterio.warp import transform
    return transform("EPSG:4326", MERCATOR, lons, lats)


class MercatorTiling(Index):
    """The tiles (level, row, col) of an Esri tile cache over a grid, at level_for the grid's resolution at its
    centre (at most max_level), cached as <folder>/<level>/<row>/<col>.tif. Only tiles meeting extent (the
    service's, EPSG:3857; None: anywhere) and, with cells, those within a cell of a cell with data (TileCells: the
    coast of Northern Ireland, so a coastal search asks no tile of the open sea or inland), so a tile left out
    makes no request; the fallback fills its area as any missing tile's."""

    def __init__(self, folder: str, max_level: int, extent: Optional[Box] = None,
                 cells: Optional[TileCells] = None):
        self.folder, self.max_level, self.extent, self.cells = folder, max_level, extent, cells
        self.crs = MERCATOR

    def level(self, grid: Grid) -> int:
        (lon,), (lat,) = _centre_wgs84(grid)
        return level_for(grid.res, lat, self.max_level)

    def tiles(self, grid: Grid) -> list:
        return remembered(self, grid, lambda: self._tiles(grid))

    def _tiles(self, grid: Grid) -> list:
        level = self.level(grid)
        size = CELLS * resolution(level)
        last = 2 ** level - 1
        left, bottom, right, top = transform_bounds(grid.crs, MERCATOR, *grid.bounds)
        half = resolution(level) / 2  # the tiles' pixels lie half a cell west and north of their cells

        def cell(x, y):  # (col, -row) of the tile whose pixels hold the point; -row grows northwards (cells_under)
            return math.floor((x + ORIGIN + half) / size), -math.floor((ORIGIN + half - y) / size)

        edge = half / 500  # a tile reaching less than a thousandth of a pixel into the box holds none of its pixels
        (c0, j0), (c1, j1) = cell(left + edge, bottom + edge), cell(right - edge, top - edge)
        c0, c1, j0, j1 = max(c0, 0), min(c1, last), max(j0, -last), min(j1, 0)
        shape = _outline(grid, MERCATOR)
        if shape is not None:  # the tiles of the grid's box under its outline, part by part
            x0, y0 = -ORIGIN - half, ORIGIN + half
            found = cells_under(shape, cell, lambda ii, jj: (x0 + ii * size, y0 + (jj - 1) * size,
                                                            x0 + (ii + 1) * size, y0 + jj * size), (c0, j0, c1, j1))
        else:
            found = [(c, j) for j in range(j0, j1 + 1) for c in range(c0, c1 + 1)]
        tiles = sorted((level, -j, c) for c, j in found)
        return [t for t in tiles if self._kept(t)]

    def _kept(self, tile) -> bool:
        box = tile_pixels(*tile)
        if self.extent is not None:
            left, bottom, right, top = self.extent
            if box[0] >= right or box[2] <= left or box[1] >= top or box[3] <= bottom:
                return False
        if self.cells is not None:
            _, cell, _, _ = self.cells._load()
            if not self.cells.any_within((box[0] - cell, box[1] - cell, box[2] + cell, box[3] + cell)):
                return False
        return True

    def path(self, cache_dir: str, tile) -> str:
        level, row, col = tile
        return os.path.join(cache_dir, self.folder, str(level), str(row), f"{col}.tif")

    def tile_of(self, path: str):
        match = re.fullmatch(rf"{re.escape(self.folder)}/(\d+)/(\d+)/(\d+)\.tif", path)
        if not match:
            return None
        level, row, col = (int(g) for g in match.groups())
        return (level, row, col) if level <= self.max_level and max(row, col) < 2 ** level else None

    def bounds_wgs84(self, tile) -> Tuple[float, float, float, float]:
        return transform_bounds(MERCATOR, "EPSG:4326", *tile_pixels(*tile))

    def has_data_near(self, lat: float, lon: float, cache_dir: str, metres: float = 1000) -> Optional[bool]:
        """Whether the mask holds data within metres of the point; None without one."""
        return None if self.cells is None else self.cells.near(lat, lon, metres)


def _centre_wgs84(grid: Grid):
    from rasterio.warp import transform
    left, bottom, right, top = grid.bounds
    return transform(grid.crs, "EPSG:4326", [(left + right) / 2], [(bottom + top) / 2])
