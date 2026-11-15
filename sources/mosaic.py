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
# reproject()'s threads: GDAL's warp kernel on WARP_THREADS threads of its global pool (the warp option
# NUM_THREADS, passed after rasterio's own), the chunks of a warp one after another in the calling thread
# (num_threads=1: rasterio's ChunkAndWarpImage). rasterio's num_threads > 1 runs ChunkAndWarpMulti, which
# starts a joinable thread per chunk, and on Windows GDAL before 3.14 a thread that ends before
# CreateThread() has returned frees its own record, which CPLJoinThread() then frees again: 0xC0000374
# (OSGeo/gdal#15452, fixed on GDAL's master by #15451, in no release of 3.12 or 3.13). A destination strip
# its source covers only in part (a mosaic of two degree tiles) is split into 40-55 chunks, many with no
# source pixel, so the country layer's workers died at about 1.4 of 1000 such stitches (12 workers on 24
# logical cores); 41 times in 15 minutes of a stress of 12 processes, never with these options (the same
# values bit for bit: the kernel splits the rows of a chunk among its threads, the chunk list is the same).
WARP_KWARGS = {"num_threads": 1, "NUM_THREADS": WARP_THREADS}


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
    files = layer.files(grid, cache_dir)
    # Which files wrote a pixel, for a layer that credits its files' owners by the pixels they gave (Tuscany's)
    wrote: Optional[List[bool]] = [] if layer.credits_by_pixels else None
    build_mosaic(files, grid, out_path, label, shift=layer.shift, rows=rows, resampling=resampling,
                 same_resolution=same_resolution, wrote=wrote, below=layer.nodata_below)
    used_data.extend(layer.used_entries(grid, cache_dir, None if wrote is None else dict(zip(files, wrote))))
    return out_path


def build_mosaic(files: List[str], grid: Grid, out_path: str, label: str,
                 categorical: bool = False, shift: Tuple[float, float] = (0.0, 0.0),
                 rows: Optional[int] = None, resampling: Optional[str] = None,
                 same_resolution: Optional[str] = None, wrote: Optional[List[bool]] = None,
                 below: Optional[float] = None) -> np.ndarray:
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
    wrote: a list given, whether each file wrote at least one pixel (one more pass over each part it covers: off
    unless asked; the mosaic's values the same either way) is appended to it, in the order of files.
    below: heights below it are no data, in each raster's own pixels before any resampling (Layer.nodata_below);
    None: none.
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
    written: List[Tuple[int, int, int, int]] = []  # the parts of the mosaic the rasters wrote into (_first_here)
    for path in files:
        progress.compute.update(1)
        # The cached files' blocks decoded on WARP_THREADS (GDAL reads it when the file is opened;
        # decompression: the same values). Local files only: remote reads keep one thread (net._gdal_http).
        # No listing of the file's folder on its opening (GDAL_DISABLE_READDIR_ON_OPEN): GDAL looks for a
        # sidecar file (.aux.xml, .ovr, .msk) by its name instead, so it opens the same dataset; a folder
        # of 100 tiles listed for every file took 1.6 of the 2.8 ms an opening took (an L tile opens 256)
        with rio.Env(GDAL_NUM_THREADS=str(WARP_THREADS), GDAL_DISABLE_READDIR_ON_OPEN="TRUE"), \
                rio.open(path) as src:
            gave = _place(src, grid, mosaic, categorical, shift, rows, resampling, same_resolution, written,
                          count=wrote is not None, below=below)
        if wrote is not None:
            wrote.append(gave)
    flush_grid(mosaic)
    progress.compute.finish()
    return mosaic


def _nan_nodata(src) -> bool:
    """Is band 1 of src float32 with NaN as its nodata and no other mask (GDAL's mask of it is its NaN pixels:
    every cached tile of ours, _write_tile's)?"""
    return src.dtypes[0] == "float32" and src.nodata is not None and math.isnan(src.nodata) \
        and list(src.mask_flag_enums[0]) == [MaskFlags.nodata]


def _read_band(src, window, clean: bool = False, below: Optional[float] = None) -> np.ndarray:
    """Band 1 of src in window as float32 with NaN where it is masked: the values of
    src.read(1, window=window, masked=True).astype(np.float32).filled(np.nan) without its two
    copies (the read's own array converted in place when it is float32 already); clean: and
    with NaN below VALID_MIN (layer._clean). A float32 band whose nodata is NaN (_nan_nodata) is
    read without GDAL's mask, which decodes every block a second time to find the pixels that are
    NaN already: its NaN pixels set to np.nan (the masked read's bits), with clean in the same pass. below:
    NaN below it too (Layer.nodata_below)."""
    if _nan_nodata(src):
        values = src.read(1, window=window)
        np.copyto(values, np.nan, where=~(values >= VALID_MIN) if clean else np.isnan(values))
        return _below(values, below)
    band = src.read(1, window=window, masked=True)
    values = band.data.astype(np.float32, copy=False)
    mask = np.ma.getmask(band)
    if mask is not np.ma.nomask:
        np.copyto(values, np.nan, where=mask)
    return _below(_clean(values, copy=False) if clean else values, below)


def _below(values: np.ndarray, below: Optional[float]) -> np.ndarray:
    """values with NaN where they are below `below`, in place (None: as they are)."""
    if below is not None:
        with np.errstate(invalid="ignore"):
            np.copyto(values, np.nan, where=values < below)
    return values


def _first_here(written: Optional[List[Tuple[int, int, int, int]]], part: Tuple[int, int, int, int]) -> bool:
    """Whether no raster wrote into part (r0, r1, c0, c1) of the mosaic before, whose pixels then all hold the
    mosaic's NaN still (written: the parts written so far, to which part is added; None: not known, False)."""
    if written is None:
        return False
    r0, r1, c0, c1 = part
    first = not any(a0 < r1 and r0 < a1 and b0 < c1 and c0 < b1 for a0, a1, b0, b1 in written)
    written.append(part)
    return first


def _put(target: np.ndarray, values: np.ndarray, categorical: bool, first: bool = False,
         count: bool = False) -> bool:
    """values (float32, NaN for none) into the pixels of target (a part of the mosaic) that have
    none yet: a raster placed before wins (np.where(np.isnan(target), values, target) in place).
    first: no raster wrote into target before (_first_here): every pixel takes its value, a copy.
    count: whether a value went into a pixel that had none is returned (False without count)."""
    if categorical:  # uint8: NODATA for NaN, the categories (whole numbers below NODATA) as they are
        where = (target == NODATA) & ~np.isnan(values)
        np.copyto(target, values, where=where, casting="unsafe")
        return count and bool(where.any())
    if first:
        target[...] = values
        return count and not bool(np.isnan(values).all())
    where = np.isnan(target)
    gave = count and bool((where & ~np.isnan(values)).any())
    np.copyto(target, values, where=where)
    return gave


def _place(src, grid: Grid, mosaic: np.ndarray, categorical: bool = False,
           shift: Tuple[float, float] = (0.0, 0.0), rows: Optional[int] = None, method: Optional[str] = None,
           same: Optional[str] = None, written: Optional[List[Tuple[int, int, int, int]]] = None,
           count: bool = False, below: Optional[float] = None) -> bool:
    """Raster src into the mosaic where it has no value yet. written: build_mosaic's parts written so far
    (_first_here): a part no raster wrote into is copied, and a raster on the grid of float32 heights with
    NaN as nodata is read straight into it (no array of its own; its NaN pixels and those below VALID_MIN
    set to np.nan in place, _read_band's values). count: whether it wrote a pixel is returned (else False).
    below: heights below it are no data (build_mosaic's), before any resampling."""
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
                target = mosaic[r0:r1, c0:c1]
                first = _first_here(written, (r0, r1, c0, c1))
                if first and clean and _nan_nodata(src):
                    src.read(1, window=window, out=target)
                    np.copyto(target, np.nan, where=~(target >= VALID_MIN))
                    _below(target, below)
                    return count and not bool(np.isnan(target).all())
                return _put(target, _read_band(src, window, clean, below), categorical, first, count)
            return False

    # Part of the grid covered by this raster
    left, bottom, right, top = transform_bounds(src_crs, grid.crs, *src_bounds)
    c0 = max(0, int(math.floor((left - grid.left) / grid.res)))
    c1 = min(grid.width, int(math.ceil((right - grid.left) / grid.res)))
    r0 = max(0, int(math.floor((grid.top - top) / grid.res)))
    r1 = min(grid.height, int(math.ceil((grid.top - bottom) / grid.res)))
    if r0 >= r1 or c0 >= c1:
        return False
    resampling = _resampling(src_pixel_m(src, src_crs, grid), grid.res, categorical, method, same)
    if rows is None or r1 - r0 <= rows:
        # Read only the part of the raster under the grid (plus a margin for resampling)
        values = _warp(src, src_crs, grid, moved, shift, clean, (r0, r1, c0, c1), grid.bounds, resampling, below)
        return _put(mosaic[r0:r1, c0:c1], values, categorical, _first_here(written, (r0, r1, c0, c1)), count)
    gave = False
    for s0 in range(r0, r1, rows):  # strips of the part: the raster read under each strip
        s1 = min(r1, s0 + rows)
        bounds = (grid.left + c0 * grid.res, grid.top - s1 * grid.res, grid.left + c1 * grid.res,
                  grid.top - s0 * grid.res)
        values = _warp(src, src_crs, grid, moved, shift, clean, (s0, s1, c0, c1), bounds, resampling, below)
        gave = _put(mosaic[s0:s1, c0:c1], values, categorical, _first_here(written, (s0, s1, c0, c1)), count) or gave
    return gave


def src_pixel_m(src, src_crs, grid: Grid) -> float:
    """A raster's pixel in metres, for the choice of its resampling (_resampling): its CRS's units; degrees as
    111 320 m (a degree of latitude: a degree of longitude is less, by the cosine of the latitude, which is not
    applied, so a geographic raster counts coarser than it is east-west; existing results rest on it); Web Mercator's
    metres (EPSG:3857: Esri's elevation tiles, LercTiles) times the cosine of the grid centre's latitude, their size
    on the ground (at 55° N a 1.19 m pixel is 0.68 m: averaged onto a 1 m grid, not interpolated)."""
    size = abs(src.res[0])
    if src_crs.is_geographic:
        return size * 111320
    if src_crs.to_epsg() == 3857:
        from rasterio.warp import transform
        left, bottom, right, top = grid.bounds
        (_,), (lat,) = transform(grid.crs, "EPSG:4326", [(left + right) / 2], [(bottom + top) / 2])
        return size * math.cos(math.radians(lat))
    return size


def _resampling(src_m: float, grid_res: float, categorical: bool = False, method: Optional[str] = None,
                same: Optional[str] = None) -> Resampling:
    """How a raster of pixels of src_m metres is reprojected onto a grid of grid_res (build_mosaic: nearest for a
    categorical one, the asked method, average when finer than FINER of the grid's, `same` at about the grid's,
    bilinear otherwise)."""
    if categorical:
        return Resampling.nearest
    if method is not None:
        return RESAMPLINGS[method]
    if src_m < grid_res * FINER:
        return Resampling.average
    if same is not None and src_m <= grid_res * SAME:
        return RESAMPLINGS[same]
    return Resampling.bilinear


def _warp(src, src_crs, grid: Grid, moved: Affine, shift: Tuple[float, float], clean: bool,
          part: Tuple[int, int, int, int],
          bounds: Tuple[float, float, float, float], resampling: Resampling,
          below: Optional[float] = None) -> np.ndarray:
    """The raster reprojected onto part (r0, r1, c0, c1) of the grid, float32 with NaN: the raster
    read under bounds (of the grid's CRS) plus a margin for the resampling; clean, below: _read_band's
    (applied to the raster's own pixels, before the resampling)."""
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
    band = _read_band(src, window, clean, below)
    reproject(band, values, src_transform=moved @ src.window_transform(window), src_crs=src_crs,
              dst_transform=window_transform, dst_crs=grid.crs,
              src_nodata=np.nan, dst_nodata=np.nan, resampling=resampling, **WARP_KWARGS)
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
