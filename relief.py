"""
The relief of a country from Copernicus DEM GLO-30 (the catalogue's surface layer of "europe", cached
like a search's tiles): per block of about BLOCK_M its highest and lowest point and its share of
steep pixels (a slope at 30 m of STEEP_DEG or more); per window of 1, 3 or 5 blocks the relief
(highest minus lowest) and the steep share.

Two users: `country run` weighs the tiles of a band no tile of which is done yet by the steep km² of
their cores (country._relief_weights: claimed heaviest first, docs/performance.md "Round 4"), and
tools/perf_country.py's relief and estimate stratify a country by these proxies. numpy, SciPy,
rasterio, pyproj and shapely only (no numba).
"""

import math
import os
from typing import Dict, List, NamedTuple, Optional, Sequence, Tuple

import numpy as np

BLOCK_M = 1000
STEEP_DEG = (30, 45)
WINDOWS = (1, 3, 5)
PROXIES = tuple(f"relief{w}" for w in WINDOWS) + tuple(f"steep{d}_{w}" for d in STEEP_DEG for w in WINDOWS)
EARTH_M_PER_DEG = 6371000 * math.pi / 180


def relief_layer():
    import sources
    return sources.SOURCES["europe"].nmpt


def degree_tiles(geometry) -> List[Tuple[int, int]]:
    """The 1° tiles (lat, lon of the south-west corner) a WGS84 geometry touches."""
    from shapely.geometry import box
    west, south, east, north = geometry.bounds
    return [(lat, lon) for lat in range(math.floor(south), math.floor(north) + 1)
            for lon in range(math.floor(west), math.floor(east) + 1)
            if geometry.intersects(box(lon, lat, lon + 1, lat + 1))]


def fetch_relief_tiles(tiles: List[Tuple[int, int]], cache_dir: str) -> Dict[Tuple[int, int], Optional[str]]:
    """The cached GLO-30 file of each tile, downloaded where missing (None: no data there, sea)."""
    from concurrent.futures import ThreadPoolExecutor
    layer = relief_layer()
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda tile: layer._download_and_record(tile, cache_dir, None, True), tiles))
    paths = {tile: layer.tile_path(cache_dir, tile) for tile in tiles}
    return {tile: path if os.path.exists(path) else None for tile, path in paths.items()}


def _block_edges(n: int, metres: float) -> np.ndarray:
    count = max(1, round(n * metres / BLOCK_M))
    return np.linspace(0, n, count + 1).round().astype(np.int64)


def tile_blocks(path: str) -> Dict[str, np.ndarray]:
    """A GLO-30 tile in blocks of about BLOCK_M: their edges in degrees (lat from the north, lon from
    the west), centres, km² and the proxies (2-D arrays, block rows from the north)."""
    import rasterio
    from scipy.ndimage import maximum_filter, minimum_filter, uniform_filter
    with rasterio.open(path) as src:
        z = src.read(1).astype(np.float64)
        if src.nodata is not None:
            z[z == src.nodata] = np.nan
        west, south, east, north = src.bounds
    h, w = z.shape
    lat = north - (np.arange(h) + 0.5) * (north - south) / h
    dy = (north - south) / h * EARTH_M_PER_DEG
    dx = (east - west) / w * EARTH_M_PER_DEG * np.cos(np.radians(lat))
    gy, gx = np.gradient(z, axis=0) / dy, np.gradient(z, axis=1) / dx[:, None]
    slope = np.degrees(np.arctan(np.hypot(gx, gy)))
    rows, cols = _block_edges(h, dy), _block_edges(w, float(np.mean(dx)))
    valid = ~np.isnan(z)

    def reduce(a, ufunc):
        return ufunc.reduceat(ufunc.reduceat(a, rows[:-1], axis=0), cols[:-1], axis=1)

    zmax, zmin = reduce(np.where(valid, z, -np.inf), np.maximum), reduce(np.where(valid, z, np.inf), np.minimum)
    n = reduce(valid.astype(np.float64), np.add)
    lat_edges = north - rows * (north - south) / h
    lon_edges = west + cols * (east - west) / w
    lat_c = (lat_edges[:-1] + lat_edges[1:]) / 2
    lon_c = (lon_edges[:-1] + lon_edges[1:]) / 2
    km2 = (np.diff(rows) * dy)[:, None] * (np.diff(cols)[None, :] * (east - west) / w * EARTH_M_PER_DEG
                                          * np.cos(np.radians(lat_c))[:, None]) / 1e6
    out = {"lat_edges": lat_edges, "lon_edges": lon_edges, "lat": np.repeat(lat_c[:, None], len(lon_c), axis=1),
           "lon": np.repeat(lon_c[None, :], len(lat_c), axis=0), "km2": km2, "valid": n > 0}
    for window in WINDOWS:
        high = maximum_filter(zmax, size=window, mode="nearest")
        low = minimum_filter(zmin, size=window, mode="nearest")
        out[f"relief{window}"] = np.where(np.isfinite(high) & np.isfinite(low), high - low, np.nan)
        pixels = uniform_filter(n, size=window, mode="nearest")
        for degrees in STEEP_DEG:
            steep = uniform_filter(reduce((slope >= degrees).astype(np.float64), np.add), size=window, mode="nearest")
            out[f"steep{degrees}_{window}"] = np.where(pixels > 0, steep / np.maximum(pixels, 1e-9), np.nan)
    return out


def proxies_at(blocks: Dict[Tuple[int, int], Dict], lon: np.ndarray, lat: np.ndarray) -> Dict[str, np.ndarray]:
    """The proxies of the blocks holding the points (NaN where no tile)."""
    out = {p: np.full(len(lon), np.nan) for p in PROXIES}
    tiles = np.column_stack([np.floor(lat), np.floor(lon)]).astype(np.int64)
    for key in {tuple(t) for t in tiles.tolist()}:
        b = blocks.get(key)
        if b is None:
            continue
        at = np.flatnonzero((tiles[:, 0] == key[0]) & (tiles[:, 1] == key[1]))
        row = np.clip(np.searchsorted(-b["lat_edges"], -lat[at], side="right") - 1, 0, len(b["lat_edges"]) - 2)
        col = np.clip(np.searchsorted(b["lon_edges"], lon[at], side="right") - 1, 0, len(b["lon_edges"]) - 2)
        for p in PROXIES:
            out[p][at] = b[p][row, col]
    return out


class SteepBlocks(NamedTuple):
    """The blocks of steep_blocks: their centres in a CRS, their steep km², the degree tiles read."""
    x: np.ndarray
    y: np.ndarray
    steep: np.ndarray
    tiles: int


def steep_blocks(outline, crs: str, cache_dir: str, degrees: int = 45) -> SteepBlocks:
    """The blocks of the GLO-30 tiles touching an outline (WGS84) whose centre lies inside it: their
    centres in a CRS and their steep km² (the block's km² times its share of pixels of a slope of
    `degrees` or more, window 1)."""
    from pyproj import Transformer
    from shapely import contains_xy, prepare
    if degrees not in STEEP_DEG:
        raise ValueError(f"steep shares are measured at {STEEP_DEG} degrees, not {degrees}")
    prepare(outline)
    tiles = degree_tiles(outline)
    lon, lat, steep = [], [], []
    for path in fetch_relief_tiles(tiles, cache_dir).values():
        if path is None:
            continue
        b = tile_blocks(path)
        inside = b["valid"] & contains_xy(outline, b["lon"], b["lat"])
        lon.append(b["lon"][inside])
        lat.append(b["lat"][inside])
        steep.append(b["km2"][inside] * b[f"steep{degrees}_1"][inside])
    if not lon:
        return SteepBlocks(np.zeros(0), np.zeros(0), np.zeros(0), len(tiles))
    x, y = Transformer.from_crs("EPSG:4326", crs, always_xy=True).transform(np.concatenate(lon), np.concatenate(lat))
    return SteepBlocks(np.asarray(x, dtype=np.float64), np.asarray(y, dtype=np.float64), np.concatenate(steep),
                       len(tiles))


def per_core(x: np.ndarray, y: np.ndarray, values: np.ndarray, cores: Sequence[Sequence[float]]) -> np.ndarray:
    """The sums of the values of the points (x, y) inside each core (left, bottom, right, top;
    half-open, left and bottom inside) of a lattice of equal squares at whole multiples of their side
    (search.fixed_tiles' cores of a band)."""
    cores = np.asarray(cores, dtype=np.float64).reshape(-1, 4)
    out = np.zeros(len(cores))
    if not len(cores) or not len(x):
        return out
    side = cores[0, 2] - cores[0, 0]
    index = {(int(round(c[0] / side)), int(round(c[1] / side))): k for k, c in enumerate(cores)}
    i, j = np.floor(np.asarray(x) / side).astype(np.int64), np.floor(np.asarray(y) / side).astype(np.int64)
    at = np.array([index.get(key, -1) for key in zip(i.tolist(), j.tolist())], dtype=np.int64)
    keep = at >= 0
    return np.bincount(at[keep], weights=np.asarray(values, dtype=np.float64)[keep], minlength=len(cores))
