"""
Elevation data sources.

A source provides a terrain model (NMT/DTM, ground only) and optionally a surface
model (NMPT/DSM, with trees and buildings), plus optionally an orthophoto service.
Every layer is downloaded in tiles into its own folder of the cache, so switching
between sources never downloads again what is already there.

Kinds of layers:
- WcsTiles: square tiles from an OGC WCS 2.0 service on a fixed grid in the
  service's coordinate system (Malta, IGN Spain).
- IndexedTiles: files found through an index, newest survey per sheet or tile:
  SheetTiles (map sheets from a WFS sheet index, geoportal.gov.pl) and StacTiles
  (tiles of a STAC collection, swisstopo).
- GridTiles: our own tiles on a fixed grid (Slovakia, made by tools/sk_tiles.py), from
  a local mirror (FINDALINE_MIRROR) or, once uploaded, from Hugging Face.
- TnmBlocks: blocks of the big files of The National Map (USGS 3DEP, the USA), found
  through its API and read by HTTP range requests, composed newest survey first; and
  DegreeBlocks: blocks of 1° files at a fixed URL (3DEP's 1/3″ DEM).
- DegreeTiles: 1°×1° GeoTIFF tiles in WGS84 (Copernicus DEM, FABDEM) and
  OpenTopography's global DEM API (NASADEM).
- FileLayer: a local raster file (GeoTIFF, ASC...), e.g. NASADEM from OpenTopography.

To add a national source, add a Source with WcsTiles layers to SOURCES (see the
Malta entries) and its country code to `countries`; see README, "Data sources".
The layers of a search are downloaded together (download_layers: one pool for all their
tiles). Searches of one data folder may download at once: each tile under its own lock
(tile_lock; the second search waits, then finds it cached) and at most HOST_SLOTS tiles
from one host at a time across all of them (host_slot), both lock files in cache/locks.

Every source and every layer used for filling (the water mask, the gap filling
source) names its licence and the notice its data must be shown with (`Credit`):
each run records them for the layers it used (run.json, the map, ATTRIBUTION.txt).
"""

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

from . import catalogue, choose, credit, layer, layers, net, source
from .layers import blocks, degree, files, gridtiles, indexed, sheets, stac, tnm, wcs
from .catalogue import malta, poland, slovakia, spain, switzerland, usa, world
from .net import (HOST_SLOTS, HOST_SLOTS_OF, LOCK_WAIT_S, RETRIES, TILE_LOCKS, _gdal_http, _locks, _part, _remote,
                  host_slot, tile_lock)
from .credit import CC_BY, Credit, OSM_CREDIT
from .layer import Fetched, Layer, VALID_MIN, _clean, _hemi, _write_tile, download_layers
from .source import MIN_RESOLUTION, OrthoService, Source
from .layers.wcs import WcsTiles, _extract_multipart
from .layers.gridtiles import GridTiles, MIRROR_ENV, grid_tile_name
from .layers.degree import DegreeTiles, OpenTopographyTiles
from .layers.indexed import IndexedTiles, Sheet, _sheet_order
from .layers.sheets import SHEET_CRS, SHEET_FORMATS, SheetTiles, _xyz_grid
from .layers.stac import StacTiles
from .layers.blocks import DegreeBlocks, _read_block, _read_window, _same_crs
from .layers.tnm import Block, IfsarBlocks, TNM_API, TnmBlocks, Usgs1mBlocks, _survey_year, _utm_zone_of
from .layers.files import FileLayer
from .catalogue.poland import GEOPORTAL, GUGIK_CREDIT
from .catalogue.switzerland import SWISSIMAGE, SWISSTOPO_CREDIT, SWISSTOPO_STAC
from .catalogue.slovakia import SLOVAK_TILES, UGKK_CREDIT, ZBGIS_ORTHO
from .catalogue.malta import MALTA, MALTA_2012_SHIFT, MALTA_CREDITS, MSDI, _malta
from .catalogue.spain import IGN_CREDIT, SPAIN_MDS, SPAIN_MDT, SPAIN_ORTHO, _spain
from .catalogue.usa import (ALASKA_BOX, USA_NOTE, USGS_13, USGS_13_CREDIT, USGS_1M, USGS_1M_CREDIT, USGS_3DEP,
                            USGS_IFSAR, USGS_IFSAR_CREDIT, USGS_ORTHO, USGS_TERMS)
from .catalogue.world import (COPERNICUS, COPERNICUS_CREDIT, COPERNICUS_DISCLAIMER, COPERNICUS_LICENCE,
                              COPERNICUS_NOTICE, FABDEM, FABDEM_CREDIT, NASADEM_CREDIT, WATER_MASK,
                              WATER_MASK_CREDIT, _copernicus_url, _fabdem_url)
from .catalogue import SOURCES
from .choose import OFFLINE_BOXES, choose_source, source_unavailable


# Threads of GDAL's reprojection of a mosaic (the same values with any number: checked on FABDEM over
# a 7600 px grid, 2.6 s on one thread, 0.8 s on 4, 0.5 s on 8): the cores numba may use
# (NUMBA_NUM_THREADS, WORKER_CPUS in the container), at most 8
WARP_THREADS = max(1, min(8, int(os.environ.get("NUMBA_NUM_THREADS") or os.cpu_count() or 1)))


# What the layers prepared in this process came from (Layer.used), saved with the run
used_data: List[Dict] = []


def prepare_layer(layer: Layer, grid: Grid, cache_dir: str, out_path: str, label: str,
                  update: Optional[str] = None, download: bool = True) -> str:
    """Download what is missing (unless done already: download False) and bring the layer
    onto the working grid (.npy)."""
    if download:
        layer.download(grid, cache_dir, update, label)
    tiles = (layer.tiles(grid) or []) if layer.folder else []  # local files are not in the cache
    empty = sum(cache.state(cache_dir, layer.tile_path(cache_dir, t)) == "missing" for t in tiles)
    if empty:  # normal over the sea; on land a sign of a lost tile (see the regression tests)
        print(f"{layer.description}: {empty} of {len(tiles)} tiles without data (the service has none there)")
    build_mosaic(layer.files(grid, cache_dir), grid, out_path, label, shift=layer.shift)
    used_data.append(layer.used(grid, cache_dir))
    return out_path


def build_mosaic(files: List[str], grid: Grid, out_path: str, label: str,
                 categorical: bool = False, shift: Tuple[float, float] = (0.0, 0.0)) -> np.ndarray:
    """Stitch rasters into a memory-mapped array covering the grid.

    Tiles already on the grid are copied; others are reprojected, averaging when
    the data is finer than the grid and interpolating bilinearly when it is coarser
    (categorical rasters, such as a water mask, use the nearest value instead).
    """
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    mosaic = np.lib.format.open_memmap(out_path, mode="w+", dtype=np.float32,
                                       shape=(grid.height, grid.width))
    mosaic[:] = np.nan
    progress.compute.start(f"stitching {label}", len(files), unit="tile")
    for path in files:
        progress.compute.update(1)
        with rio.open(path) as src:
            _place(src, grid, mosaic, categorical, shift)
    mosaic.flush()
    progress.compute.finish()
    return mosaic


def _place(src, grid: Grid, mosaic: np.ndarray, categorical: bool = False,
           shift: Tuple[float, float] = (0.0, 0.0)):
    clean = (lambda band: band.astype(np.float32)) if categorical else _clean
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
                values = clean(src.read(1, window=window, masked=True).astype(np.float32).filled(np.nan))
                target = mosaic[r0:r1, c0:c1]
                mosaic[r0:r1, c0:c1] = np.where(np.isnan(target), values, target)
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
    window_transform = from_origin(grid.left + c0 * grid.res, grid.top - r0 * grid.res, grid.res, grid.res)
    values = np.full((r1 - r0, c1 - c0), np.nan, dtype=np.float32)

    # Read only the part of the raster under the grid (plus a margin for resampling)
    area = transform_bounds(grid.crs, src_crs, *grid.bounds)
    area = (area[0] - shift[0], area[1] - shift[1], area[2] - shift[0], area[3] - shift[1])
    margin = 3 * max(abs(src.res[0]), abs(src.res[1]))
    window = from_bounds(area[0] - margin, area[1] - margin, area[2] + margin, area[3] + margin,
                         src.transform).round_offsets().round_lengths()
    window = window.intersection(rio.windows.Window(0, 0, src.width, src.height))
    band = src.read(1, window=window, masked=True).astype(np.float32).filled(np.nan)
    reproject(clean(band), values, src_transform=moved * src.window_transform(window), src_crs=src_crs,
              dst_transform=window_transform, dst_crs=grid.crs,
              src_nodata=np.nan, dst_nodata=np.nan, resampling=resampling, num_threads=WARP_THREADS)
    target = mosaic[r0:r1, c0:c1]
    mosaic[r0:r1, c0:c1] = np.where(np.isnan(target), values, target)


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
              exclude: Optional[np.ndarray] = None, name: str = "gap") -> Tuple[str, int]:
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
    """
    from scipy import ndimage

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
        pairs.append((surface, fallback.nmpt or fallback.nmt, f"{name}_nmpt.npy"))
    for target, layer, name in pairs:
        gaps = np.isnan(target) if exclude is None else np.isnan(target) & ~exclude
        if not gaps.any():
            continue
        other = np.asarray(np.load(prepare_layer(layer, grid, cache_dir, os.path.join(work, name),
                                                 f"gap fill ({fallback.name})", update), mmap_mode="r"))
        values = np.asarray(target)
        gy, gx = np.gradient(np.where(np.isfinite(values), values, other), grid.res)
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
        target[gaps] = other[gaps] + offsets[labels[gaps]]
        target.flush()
    filled &= np.isfinite(elevation)
    np.save(out_path, filled)
    return out_path, int(filled.sum())


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
