"""Water and gaps: the water body mask, water filled to the surface level, gaps from fallback sources."""

import math
import os
from typing import List, Optional, Tuple

import numpy as np
from rasterio.warp import transform_bounds

import cache
from grid import Grid
from progress import progress

from .source import Source
from .catalogue.world import WATER_MASK
from .mosaic import build_mosaic, prepare_layer, used_data

# Copernicus water body mask, 1°×1° tiles next to the DEM tiles: 1 ocean, 2 lake, 3 river
OCEAN, LAKE = 1, 2
GAP_RING = 3  # pixels around a gap used to match the filling source's heights
GAP_MATCH_SLOPE = 15  # degrees; only gentler ground is used to match heights
GAP_MAX_LOCAL_SHIFT = 3  # m; local height offsets differing more from the overall one are ignored
SHORE_BUFFER = 45  # m around water in the mask that may still be water (the mask is 30 m)
SEA_LEVEL_TOLERANCE = 1.0  # m; data at most this high inside the sea counts as water


def water_body_mask(grid: Grid, cache_dir: str, out_path: str, update: Optional[str] = None,
                    download: bool = True) -> np.ndarray:
    """Copernicus water body mask on the grid (OCEAN, LAKE...), open sea where tiles are missing
    (downloaded first unless done already: download False)."""
    if download:
        WATER_MASK.download(grid, cache_dir, update, "water mask")
    wbm = build_mosaic(WATER_MASK.files(grid, cache_dir), grid, out_path, "water mask", categorical=True)
    used_data.append(WATER_MASK.used(grid, cache_dir))
    for tile in WATER_MASK.tiles(grid):
        if cache.state(cache_dir, WATER_MASK.tile_path(cache_dir, tile)) == "missing":
            lat, lon = tile
            left, bottom, right, top = transform_bounds("EPSG:4326", grid.crs, lon, lat, lon + 1, lat + 1)
            c0, c1 = max(0, int((left - grid.left) // grid.res)), min(grid.width, int((right - grid.left) // grid.res) + 1)
            r0, r1 = max(0, int((grid.top - top) // grid.res)), min(grid.height, int((grid.top - bottom) // grid.res) + 1)
            if r0 < r1 and c0 < c1:
                block = wbm[r0:r1, c0:c1]
                block[np.isnan(block)] = OCEAN
    return np.asarray(wbm)


def near(mask: np.ndarray, metres: float, res: float) -> np.ndarray:
    """The mask grown by about `metres` (square neighbourhood)."""
    from scipy import ndimage
    if metres <= 0:
        return mask
    return ndimage.binary_dilation(mask, structure=np.ones((3, 3)), iterations=max(1, math.ceil(metres / res)))


def fill_water(elevation_path: str, surface_path: Optional[str], grid: Grid, wbm: np.ndarray,
               sea_zone: np.ndarray, out_path: str) -> str:
    """Give the sea and lakes an elevation where the data has none.

    National LiDAR models have no data over water, so lines across the sea (and
    the edges of sea cliffs, whose slope needs the neighbouring pixels) would be
    missed. Pixels without data in sea_zone (the sea mask of coast.py grown by
    --shore-buffer, see near) get 0 m. Pixels without data next to lakes of the
    Copernicus mask (within SHORE_BUFFER, as the mask is 30 m) get the level of
    the lake's shore (the median elevation around it). The exact shoreline comes
    from the elevation data itself; gaps in the data on land stay without data.
    Saves a boolean water mask (filled pixels, and lakes that have data) to out_path.
    """
    from scipy import ndimage

    elevation = np.load(elevation_path, mmap_mode="r+")
    surface = np.load(surface_path, mmap_mode="r+") if surface_path else None
    progress.compute.start("filling sea and lakes", 3, unit="step")
    empty = np.isnan(elevation)
    sea_fill = empty & sea_zone
    progress.compute.update(1)
    lake = empty & near(wbm == LAKE, SHORE_BUFFER, grid.res) & ~sea_fill
    progress.compute.update(1)

    elevation[sea_fill] = 0.0
    if surface is not None:
        surface[sea_fill & np.isnan(surface)] = 0.0
    water = sea_fill.copy()
    lake_px = 0
    labels, _ = ndimage.label(lake, structure=np.ones((3, 3)))
    for index, region in enumerate(ndimage.find_objects(labels), 1):
        if region is None:
            continue
        rows = slice(max(region[0].start - 1, 0), region[0].stop + 1)
        cols = slice(max(region[1].start - 1, 0), region[1].stop + 1)
        area = labels[rows, cols] == index
        shore = ndimage.binary_dilation(area) & ~empty[rows, cols]
        heights = elevation[rows, cols][shore]
        heights = heights[np.isfinite(heights)]
        if heights.size == 0:
            continue
        level = float(np.median(heights))
        block = elevation[rows, cols]
        block[area] = level
        if surface is not None:
            sblock = surface[rows, cols]
            sblock[area & np.isnan(sblock)] = level
        water[rows, cols] |= area
        lake_px += int(area.sum())
    # Water that the elevation data covers: lakes measured by LiDAR, and sea given as
    # about 0 m by the data itself (e.g. IGN Spain)
    water |= (wbm == LAKE) & ~empty
    water |= sea_zone & ~empty & (np.asarray(elevation) <= SEA_LEVEL_TOLERANCE)
    elevation.flush()
    if surface is not None:
        surface.flush()
    np.save(out_path, water)
    progress.compute.update(1)
    km2 = lambda px: px * grid.res ** 2 / 1e6
    progress.compute.finish(f"sea {km2(int(sea_fill.sum())):.2f} km², lakes {km2(lake_px):.2f} km²")
    return out_path


def fill_gaps(elevation_path: str, surface_path: Optional[str], grid: Grid, fallback: "Source",
              cache_dir: str, out_path: str, update: Optional[str] = None,
              exclude: Optional[np.ndarray] = None, name: str = "gap",
              window: Optional[Tuple[slice, slice]] = None, surface_from_terrain: bool = True) -> Tuple[str, int]:
    """Fill the remaining gaps in the data on land from another source.

    Each gap gets the other source shifted by the median height difference in a
    ring of pixels around that gap, so it joins its surroundings without a step
    (different surveys and height systems differ by up to a few metres). Only
    gentle slopes are used for this: on a cliff, a shift of a metre between two
    surveys changes the height by tens of metres. A local offset more than
    GAP_MAX_LOCAL_SHIFT from the overall median is not trusted.
    Saves a boolean mask of the filled pixels to out_path; returns
    (out_path, number of filled pixels). Pixels in `exclude` (the sea) are left alone.
    The fallback's grids are saved next to out_path as <name>_nmt.npy and <name>_nmpt.npy.
    window (rows, columns): the fallback is brought onto that part of the grid only (a
    neighbour: around the gaps at the border), nothing is filled outside it. Without a surface
    model of its own the fallback fills the surface gaps from its terrain, unless
    surface_from_terrain is False (a neighbour: they are left to the next source).
    """
    work = os.path.dirname(out_path)
    elevation = np.load(elevation_path, mmap_mode="r+")
    filled = np.isnan(elevation)
    if exclude is not None:
        filled &= ~exclude
    if not filled.any():
        np.save(out_path, filled)
        return out_path, 0
    pairs = [(elevation, fallback.nmt, f"{name}_nmt.npy")]
    if surface_path:
        surface = np.load(surface_path, mmap_mode="r+")
        layer = fallback.nmpt or (fallback.nmt if surface_from_terrain else None)
        if layer is not None:
            pairs.append((surface, layer, f"{name}_nmpt.npy"))
    sub = _subgrid(grid, window) if window is not None else grid
    for target, layer, name in pairs:
        gaps = np.isnan(target) if exclude is None else np.isnan(target) & ~exclude
        if not gaps.any():
            continue
        path = prepare_layer(layer, sub, cache_dir, os.path.join(work, name), f"gap fill ({fallback.name})", update)
        if window is None:
            other = np.asarray(np.load(path, mmap_mode="r"))
        else:
            other = np.full(target.shape, np.nan, np.float32)
            other[window] = np.load(path, mmap_mode="r")
        _fill(target, other, gaps, grid.res)
    filled &= np.isfinite(elevation)
    np.save(out_path, filled)
    return out_path, int(filled.sum())


def _subgrid(grid: Grid, window: Tuple[slice, slice]) -> Grid:
    """The part of the grid in window (rows, columns), its tiles those under the grid's own
    footprint (the area, or the circle inscribed in the grid) within that part."""
    from shapely.geometry import box
    rows, cols = window
    sub = Grid(left=grid.left + cols.start * grid.res, top=grid.top - rows.start * grid.res, res=grid.res,
               height=rows.stop - rows.start, width=cols.stop - cols.start, crs=grid.crs)
    sub.area_shape = box(*sub.bounds).intersection(_footprint_shape(grid))
    return sub


def _footprint_shape(grid: Grid):
    """The outline the grid's data tiles are picked under (sources/indexes/tilings.py): its area,
    or the circle inscribed in its box."""
    from shapely.geometry import Point
    if grid.area_shape is not None:
        return grid.area_shape
    left, bottom, right, top = grid.bounds
    return Point((left + right) / 2, (bottom + top) / 2).buffer(min(right - left, top - bottom) / 2)


def _fill(target: np.ndarray, other: np.ndarray, gaps: np.ndarray, res: float) -> int:
    """Fill the gaps of target (a memory-mapped grid) from other, each gap shifted to the heights
    around it (fill_gaps); returns the number of pixels filled."""
    from scipy import ndimage

    values = np.asarray(target)
    gy, gx = np.gradient(np.where(np.isfinite(values), values, other), res)
    flat = np.degrees(np.arctan(np.hypot(gx, gy))) < GAP_MATCH_SLOPE
    both = ~gaps & np.isfinite(values) & np.isfinite(other) & flat
    overall = float(np.median(values[both] - other[both])) if both.any() else 0.0
    # Offset of every gap from the ring of pixels around it
    labels, count = ndimage.label(gaps, structure=np.ones((3, 3)))
    ring = ndimage.grey_dilation(labels, size=(GAP_RING * 2 + 1,) * 2) * (both & (labels == 0))
    offsets = np.full(count + 1, overall)
    if ring.any():
        # Only the ring pixels: scipy sorts every pixel it is given (10 s for a 58 Mpx tile)
        near = ring > 0
        local = ndimage.median(values[near] - other[near], ring[near], index=np.arange(1, count + 1))
        local = np.asarray(local, dtype=float)
        # A local offset far from the overall one comes from misaligned edges, not heights
        usable = np.isfinite(local) & (np.abs(local - overall) <= GAP_MAX_LOCAL_SHIFT)
        offsets[1:] = np.where(usable, local, overall)
    count = int((gaps & np.isfinite(other)).sum())
    target[gaps] = other[gaps] + offsets[labels[gaps]]
    target.flush()
    return count


def fill_gaps_chain(elevation_path: str, surface_path: Optional[str], grid: Grid, fallbacks: List["Source"],
                    cache_dir: str, out_path: str, update: Optional[str] = None,
                    exclude: Optional[np.ndarray] = None) -> Tuple[str, List[Tuple["Source", int]]]:
    """Fill the gaps on land from each fallback in turn (fill_gaps), each only what the ones
    before it left (most sources have one; Alaska: its IfSAR, then the 1/3″ DEM). Saves the
    mask of all filled pixels to out_path; returns (out_path, [(fallback, filled pixels)])."""
    filled, counts = None, []
    for n, fallback in enumerate(fallbacks):
        step = out_path if n == 0 else f"{os.path.splitext(out_path)[0]}{n}.npy"
        _, pixels = fill_gaps(elevation_path, surface_path, grid, fallback, cache_dir, step, update,
                              exclude=exclude, name="gap" if n == 0 else f"gap{n}")
        counts.append((fallback, pixels))
        if n == 0:
            filled = np.load(step)
        elif pixels:
            filled |= np.load(step)
            np.save(out_path, filled)
    return out_path, counts
