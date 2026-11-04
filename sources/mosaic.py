"""Layers brought onto the working grid: downloads, mosaics, a slope file; the record of the data used."""

import math
import os
from typing import Dict, List, Optional, Tuple

import numpy as np
import rasterio as rio
from affine import Affine
from rasterio.transform import from_origin
from rasterio.warp import Resampling, reproject, transform_bounds
from rasterio.windows import from_bounds

import cache
from grid import Grid
from progress import progress

from .layer import Layer, _clean

# Threads of GDAL's reprojection of a mosaic (the same values with any number: checked on FABDEM over
# a 7600 px grid, 2.6 s on one thread, 0.8 s on 4, 0.5 s on 8): the cores numba may use
# (NUMBA_NUM_THREADS, WORKER_CPUS in the container), at most 8
WARP_THREADS = max(1, min(8, int(os.environ.get("NUMBA_NUM_THREADS") or os.cpu_count() or 1)))


# What the layers prepared in this process came from (Layer.used), saved with the run
used_data: List[Dict] = []

# A categorical mosaic (build_mosaic: the water body mask's categories 0-3) is uint8 with this code
# where no raster has a value (NaN in the float32 mosaics)
NODATA = 255


def prepare_layer(layer: Layer, grid: Grid, cache_dir: str, out_path: str, label: str,
                  update: Optional[str] = None, download: bool = True, quiet: bool = False,
                  rows: Optional[int] = None) -> str:
    """Download what is missing (unless done already: download False) and bring the layer
    onto the working grid (.npy). quiet: no line about its tiles without data (a neighbour
    filling the gaps at a border has none beyond it). rows: the mosaic in strips (build_mosaic)."""
    if download:
        layer.download(grid, cache_dir, update, label)
    tiles = (layer.tiles(grid) or []) if layer.folder and not quiet else []  # local files are not in the cache
    empty = sum(cache.state(cache_dir, layer.tile_path(cache_dir, t)) == "missing" for t in tiles)
    if empty:  # normal over the sea; on land a sign of a lost tile (see the regression tests)
        print(f"{layer.description}: {empty} of {len(tiles)} tiles without data (the service has none there)")
    build_mosaic(layer.files(grid, cache_dir), grid, out_path, label, shift=layer.shift, rows=rows)
    used_data.append(layer.used(grid, cache_dir))
    return out_path


def build_mosaic(files: List[str], grid: Grid, out_path: str, label: str,
                 categorical: bool = False, shift: Tuple[float, float] = (0.0, 0.0),
                 rows: Optional[int] = None) -> np.ndarray:
    """Stitch rasters into a memory-mapped array covering the grid.

    Tiles already on the grid are copied; others are reprojected, averaging when
    the data is finer than the grid and interpolating bilinearly when it is coarser
    (categorical rasters, such as a water mask, use the nearest value instead: their
    mosaic is uint8, NODATA where no raster has a value, the categories below it).
    rows: a raster reprojected onto more rows of the grid than that is warped in strips of
    that many rows (the area of a tiled search: no temporary of the whole grid). Bilinear and
    nearest give the same values as the whole; `average` may differ by about a millimetre
    at a strip's edge (GDAL warps a large part in chunks of its own anyway).
    """
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    mosaic = np.lib.format.open_memmap(out_path, mode="w+", dtype=np.uint8 if categorical else np.float32,
                                       shape=(grid.height, grid.width))
    if rows is None:
        mosaic[:] = NODATA if categorical else np.nan
    else:
        for r0 in range(0, grid.height, rows):
            mosaic[r0:r0 + rows] = NODATA if categorical else np.nan
    progress.compute.start(f"stitching {label}", len(files), unit="tile")
    for path in files:
        progress.compute.update(1)
        # The cached files' blocks decoded on WARP_THREADS (GDAL reads it when the file is opened;
        # decompression: the same values). Local files only: remote reads keep one thread (net._gdal_http)
        with rio.Env(GDAL_NUM_THREADS=str(WARP_THREADS)), rio.open(path) as src:
            _place(src, grid, mosaic, categorical, shift, rows)
    mosaic.flush()
    progress.compute.finish()
    return mosaic


def _read_band(src, window) -> np.ndarray:
    """Band 1 of src in window as float32 with NaN where it is masked: the values of
    src.read(1, window=window, masked=True).astype(np.float32).filled(np.nan) without its two
    copies (the read's own array converted in place when it is float32 already)."""
    band = src.read(1, window=window, masked=True)
    values = band.data.astype(np.float32, copy=False)
    mask = np.ma.getmask(band)
    if mask is not np.ma.nomask:
        np.copyto(values, np.nan, where=mask)
    return values


def _put(target: np.ndarray, values: np.ndarray, categorical: bool):
    """values (float32, NaN for none) into the pixels of target (a part of the mosaic) that have
    none yet: a raster placed before wins (np.where(np.isnan(target), values, target) in place)."""
    if categorical:  # uint8: NODATA for NaN, the categories (whole numbers below NODATA) as they are
        np.copyto(target, values, where=(target == NODATA) & ~np.isnan(values), casting="unsafe")
    else:
        np.copyto(target, values, where=np.isnan(target))


def _place(src, grid: Grid, mosaic: np.ndarray, categorical: bool = False,
           shift: Tuple[float, float] = (0.0, 0.0), rows: Optional[int] = None):
    clean = (lambda band: band) if categorical else (lambda band: _clean(band, copy=False))
    grid_crs = rio.crs.CRS.from_user_input(grid.crs)
    src_crs = src.crs or grid_crs
    moved = Affine.translation(*shift)
    src_bounds = rio.coords.BoundingBox(src.bounds.left + shift[0], src.bounds.bottom + shift[1],
                                        src.bounds.right + shift[0], src.bounds.top + shift[1])
    same_grid = src_crs == grid_crs and shift == (0.0, 0.0) and math.isclose(abs(src.res[0]), grid.res) \
        and math.isclose(abs(src.res[1]), grid.res)
    if same_grid:
        row_off = int(round((grid.top - src.bounds.top) / grid.res))
        col_off = int(round((src.bounds.left - grid.left) / grid.res))
        if abs(row_off * grid.res - (grid.top - src.bounds.top)) < grid.res / 100:
            r0, c0 = max(row_off, 0), max(col_off, 0)
            r1, c1 = min(row_off + src.height, grid.height), min(col_off + src.width, grid.width)
            if r0 < r1 and c0 < c1:
                window = rio.windows.Window(c0 - col_off, r0 - row_off, c1 - c0, r1 - r0)
                _put(mosaic[r0:r1, c0:c1], clean(_read_band(src, window)), categorical)
            return

    # Part of the grid covered by this raster
    left, bottom, right, top = transform_bounds(src_crs, grid.crs, *src_bounds)
    c0 = max(0, int(math.floor((left - grid.left) / grid.res)))
    c1 = min(grid.width, int(math.ceil((right - grid.left) / grid.res)))
    r0 = max(0, int(math.floor((grid.top - top) / grid.res)))
    r1 = min(grid.height, int(math.ceil((grid.top - bottom) / grid.res)))
    if r0 >= r1 or c0 >= c1:
        return
    src_res = abs(src.res[0]) * (111320 if src_crs.is_geographic else 1)
    if categorical:
        resampling = Resampling.nearest
    else:
        resampling = Resampling.average if src_res < grid.res * 0.75 else Resampling.bilinear
    if rows is None or r1 - r0 <= rows:
        # Read only the part of the raster under the grid (plus a margin for resampling)
        values = _warp(src, src_crs, grid, moved, shift, clean, (r0, r1, c0, c1), grid.bounds, resampling)
        _put(mosaic[r0:r1, c0:c1], values, categorical)
        return
    for s0 in range(r0, r1, rows):  # strips of the part: the raster read under each strip
        s1 = min(r1, s0 + rows)
        bounds = (grid.left + c0 * grid.res, grid.top - s1 * grid.res, grid.left + c1 * grid.res,
                  grid.top - s0 * grid.res)
        values = _warp(src, src_crs, grid, moved, shift, clean, (s0, s1, c0, c1), bounds, resampling)
        _put(mosaic[s0:s1, c0:c1], values, categorical)


def _warp(src, src_crs, grid: Grid, moved: Affine, shift: Tuple[float, float], clean, part: Tuple[int, int, int, int],
          bounds: Tuple[float, float, float, float], resampling: Resampling) -> np.ndarray:
    """The raster reprojected onto part (r0, r1, c0, c1) of the grid, float32 with NaN: the raster
    read under bounds (of the grid's CRS) plus a margin for the resampling."""
    r0, r1, c0, c1 = part
    window_transform = from_origin(grid.left + c0 * grid.res, grid.top - r0 * grid.res, grid.res, grid.res)
    values = np.full((r1 - r0, c1 - c0), np.nan, dtype=np.float32)
    area = transform_bounds(grid.crs, src_crs, *bounds)
    area = (area[0] - shift[0], area[1] - shift[1], area[2] - shift[0], area[3] - shift[1])
    margin = 3 * max(abs(src.res[0]), abs(src.res[1]))
    window = from_bounds(area[0] - margin, area[1] - margin, area[2] + margin, area[3] + margin,
                         src.transform).round_offsets().round_lengths()
    try:
        window = window.intersection(rio.windows.Window(0, 0, src.width, src.height))
    except rio.errors.WindowError:  # a strip the raster does not reach: nothing from it
        return values
    if window.width <= 0 or window.height <= 0:
        return values
    band = clean(_read_band(src, window))
    reproject(band, values, src_transform=moved @ src.window_transform(window), src_crs=src_crs,
              dst_transform=window_transform, dst_crs=grid.crs,
              src_nodata=np.nan, dst_nodata=np.nan, resampling=resampling, num_threads=WARP_THREADS)
    del band
    return values


def load_slope_file(slope_file: str, grid: Grid, out_path: str) -> str:
    """Resample a user supplied slope raster (degrees) onto the working grid."""
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    slope = np.lib.format.open_memmap(out_path, mode="w+", dtype=np.float32,
                                      shape=(grid.height, grid.width))
    slope[:] = np.nan
    with rio.open(slope_file) as src:
        src_crs = src.crs
        if src_crs is None:
            print(f"  {slope_file} has no coordinate system, assuming {grid.crs}")
            src_crs = grid.crs
        reproject(rio.band(src, 1), slope, src_crs=src_crs, src_transform=src.transform,
                  src_nodata=src.nodata, dst_transform=grid.transform, dst_crs=grid.crs,
                  dst_nodata=np.nan, resampling=Resampling.average)
    slope.flush()
    return out_path
