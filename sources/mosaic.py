"""Layers brought onto the working grid: downloads, mosaics, a slope file; the record of the data used."""

import math
import os
from typing import Dict, List, Optional, Tuple

import numpy as np
import rasterio as rio
from affine import Affine
from rasterio.enums import MaskFlags
from rasterio.transform import from_origin
from rasterio.warp import Resampling, reproject, transform_bounds
from rasterio.windows import from_bounds

import cache
from grid import Grid
from progress import progress

from .layer import VALID_MIN, Layer, _clean

# Threads of GDAL's reprojection of a mosaic (the same values with any number: checked on FABDEM over
# a 7600 px grid, 2.6 s on one thread, 0.8 s on 4, 0.5 s on 8): the cores numba may use
# (NUMBA_NUM_THREADS, WORKER_CPUS in the container), at most 8
WARP_THREADS = max(1, min(8, int(os.environ.get("NUMBA_NUM_THREADS") or os.cpu_count() or 1)))


# What the layers prepared in this process came from (Layer.used), saved with the run
used_data: List[Dict] = []

# A categorical mosaic (build_mosaic: the water body mask's categories 0-3) is uint8 with this code
# where no raster has a value (NaN in the float32 mosaics)
NODATA = 255

# The memory-mapped grids of step 1 when they are done (flush_grid): written to disk at once, or,
# as a list (a worker of the country layer), each view kept in it until the grids are deleted.
# Nothing reads a grid but through the system's cache, so its values do not depend on this. On
# Windows a grid's pages go to the disk when the last view that wrote them closes, even if the
# file is deleted seconds later, and never while it stays open and the view closes just before the
# delete (4 grids of 150 MB: 600 MB written against 2): a tile's 300-500 MB that nobody reads back
HELD_GRIDS: Optional[List[np.memmap]] = None

# The methods a mosaic of heights may be asked to reproject with (build_mosaic's `resampling`)
# instead of its own choice: the neighbour's data at a border (filling.NEIGHBOUR_RESAMPLING,
# measured with tools/border_study.py: docs/country-precompute/contract.md, section 6, step 0)
RESAMPLINGS = {"nearest": Resampling.nearest, "bilinear": Resampling.bilinear, "cubic": Resampling.cubic,
               "average": Resampling.average}
# A raster reprojected onto the grid is "finer" below FINER of the grid's resolution (averaged) and "at the
# grid's resolution" up to SAME of it (bilinear, or build_mosaic's `same_resolution`); coarser: bilinear.
# SAME lies between the two measured cases of nearest for a neighbour's data (docs/performance.md, "The
# resampling of a neighbour's data"): right at 1.0 of the grid's resolution, wrong at 1.25 (2.5 m data on a
# 2 m grid: every step between two coarse pixels a wall, 1.7 times the lines and 2.5 times the spots)
FINER, SAME = 0.75, 1.1


def flush_grid(grid: np.memmap):
    if HELD_GRIDS is None:
        grid.flush()
    else:
        HELD_GRIDS.append(grid)


def prepare_layer(layer: Layer, grid: Grid, cache_dir: str, out_path: str, label: str,
                  update: Optional[str] = None, download: bool = True, quiet: bool = False,
                  rows: Optional[int] = None, resampling: Optional[str] = None,
                  same_resolution: Optional[str] = None) -> str:
    """Download what is missing (unless done already: download False) and bring the layer
    onto the working grid (.npy). quiet: no line about its tiles without data (a neighbour
    filling the gaps at a border has none beyond it). rows: the mosaic in strips (build_mosaic).
    resampling, same_resolution: build_mosaic's."""
    if download:
        layer.download(grid, cache_dir, update, label)
    tiles = (layer.tiles(grid) or []) if layer.folder and not quiet else []  # local files are not in the cache
    empty = cache.states(cache_dir, [layer.tile_path(cache_dir, t) for t in tiles]).count("missing")
    if empty:  # normal over the sea; on land a sign of a lost tile (see the regression tests)
        print(f"{layer.description}: {empty} of {len(tiles)} tiles without data (the service has none there)")
    build_mosaic(layer.files(grid, cache_dir), grid, out_path, label, shift=layer.shift, rows=rows,
                 resampling=resampling, same_resolution=same_resolution)
    used_data.append(layer.used(grid, cache_dir))
    return out_path


def build_mosaic(files: List[str], grid: Grid, out_path: str, label: str,
                 categorical: bool = False, shift: Tuple[float, float] = (0.0, 0.0),
                 rows: Optional[int] = None, resampling: Optional[str] = None,
                 same_resolution: Optional[str] = None) -> np.ndarray:
    """Stitch rasters into a memory-mapped array covering the grid.

    Tiles already on the grid are copied; others are reprojected, averaging when
    the data is finer than the grid and interpolating bilinearly when it is coarser
    (categorical rasters, such as a water mask, use the nearest value instead: their
    mosaic is uint8, NODATA where no raster has a value, the categories below it).
    rows: a raster reprojected onto more rows of the grid than that is warped in strips of
    that many rows (the area of a tiled search: no temporary of the whole grid). Bilinear and
    nearest give the same values as the whole; `average` may differ by about a millimetre
    at a strip's edge (GDAL warps a large part in chunks of its own anyway).
    resampling: one of RESAMPLINGS for the rasters of heights that are reprojected, instead of
    that choice (None: the choice above; a raster on the grid is copied either way).
    same_resolution: one of RESAMPLINGS instead of bilinear for the reprojected rasters at about
    the grid's resolution only (FINER to SAME of it): a neighbour's data, whose cliff edges a
    bilinear reprojection at one resolution smooths (filling.NEIGHBOUR_SAME_RESOLUTION).
    """
    for method in (resampling, same_resolution):
        if method is not None and (categorical or method not in RESAMPLINGS):
            raise ValueError(f"resampling must be one of {', '.join(RESAMPLINGS)} for a mosaic of heights")
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
        # decompression: the same values). Local files only: remote reads keep one thread (net._gdal_http).
        # No listing of the file's folder on its opening (GDAL_DISABLE_READDIR_ON_OPEN): GDAL looks for a
        # sidecar file (.aux.xml, .ovr, .msk) by its name instead, so it opens the same dataset; a folder
        # of 100 tiles listed for every file took 1.6 of the 2.8 ms an opening took (an L tile opens 256)
        with rio.Env(GDAL_NUM_THREADS=str(WARP_THREADS), GDAL_DISABLE_READDIR_ON_OPEN="TRUE"), \
                rio.open(path) as src:
            _place(src, grid, mosaic, categorical, shift, rows, resampling, same_resolution)
    flush_grid(mosaic)
    progress.compute.finish()
    return mosaic


def _nan_nodata(src) -> bool:
    """Is band 1 of src float32 with NaN as its nodata and no other mask (GDAL's mask of it is its NaN pixels:
    every cached tile of ours, _write_tile's)?"""
    return src.dtypes[0] == "float32" and src.nodata is not None and math.isnan(src.nodata) \
        and list(src.mask_flag_enums[0]) == [MaskFlags.nodata]


def _read_band(src, window, clean: bool = False) -> np.ndarray:
    """Band 1 of src in window as float32 with NaN where it is masked: the values of
    src.read(1, window=window, masked=True).astype(np.float32).filled(np.nan) without its two
    copies (the read's own array converted in place when it is float32 already); clean: and
    with NaN below VALID_MIN (layer._clean). A float32 band whose nodata is NaN (_nan_nodata) is
    read without GDAL's mask, which decodes every block a second time to find the pixels that are
    NaN already: its NaN pixels set to np.nan (the masked read's bits), with clean in the same pass."""
    if _nan_nodata(src):
        values = src.read(1, window=window)
        np.copyto(values, np.nan, where=~(values >= VALID_MIN) if clean else np.isnan(values))
        return values
    band = src.read(1, window=window, masked=True)
    values = band.data.astype(np.float32, copy=False)
    mask = np.ma.getmask(band)
    if mask is not np.ma.nomask:
        np.copyto(values, np.nan, where=mask)
    return _clean(values, copy=False) if clean else values


def _put(target: np.ndarray, values: np.ndarray, categorical: bool):
    """values (float32, NaN for none) into the pixels of target (a part of the mosaic) that have
    none yet: a raster placed before wins (np.where(np.isnan(target), values, target) in place)."""
    if categorical:  # uint8: NODATA for NaN, the categories (whole numbers below NODATA) as they are
        np.copyto(target, values, where=(target == NODATA) & ~np.isnan(values), casting="unsafe")
    else:
        np.copyto(target, values, where=np.isnan(target))


def _place(src, grid: Grid, mosaic: np.ndarray, categorical: bool = False,
           shift: Tuple[float, float] = (0.0, 0.0), rows: Optional[int] = None, method: Optional[str] = None,
           same: Optional[str] = None):
    clean = not categorical
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
                _put(mosaic[r0:r1, c0:c1], _read_band(src, window, clean), categorical)
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
    elif method is not None:
        resampling = RESAMPLINGS[method]
    elif src_res < grid.res * FINER:
        resampling = Resampling.average
    elif same is not None and src_res <= grid.res * SAME:
        resampling = RESAMPLINGS[same]
    else:
        resampling = Resampling.bilinear
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


def _warp(src, src_crs, grid: Grid, moved: Affine, shift: Tuple[float, float], clean: bool,
          part: Tuple[int, int, int, int],
          bounds: Tuple[float, float, float, float], resampling: Resampling) -> np.ndarray:
    """The raster reprojected onto part (r0, r1, c0, c1) of the grid, float32 with NaN: the raster
    read under bounds (of the grid's CRS) plus a margin for the resampling; clean: _read_band's."""
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
    band = _read_band(src, window, clean)
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
