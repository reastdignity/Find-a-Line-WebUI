"""Blocks of big remote files read by HTTP range requests, and DegreeBlocks: blocks of 1° files at a fixed URL."""

import math
import os
import re
from typing import Callable, Dict, Optional, Sequence, Tuple

import numpy as np
import rasterio as rio
from affine import Affine
from rasterio.transform import from_origin
from rasterio.warp import Resampling, reproject, transform_bounds
from rasterio.windows import Window

import cache
from grid import Grid

from ..net import _gdal_http, _remote
from ..credit import Credit
from ..layer import Fetched, Layer, _clean, _hemi, _write_tile


def _same_crs(a, b) -> bool:
    """Whether two CRSs are the same; also when one names only the ellipsoid of the other's
    datum (Alaska's IfSAR files: Alaska Albers on "GRS80, datum not specified")."""
    a, b = rio.crs.CRS.from_user_input(a), rio.crs.CRS.from_user_input(b)
    if a == b or (a.to_epsg() is not None and a.to_epsg() == b.to_epsg()):
        return True
    ellipsoid = {"NAD83": "GRS80", "WGS84": "WGS84"}

    def plain(crs) -> Dict:
        d = {k: v for k, v in crs.to_dict().items() if k not in ("no_defs", "type", "towgs84")}
        if "datum" in d:
            d["ellps"] = ellipsoid.get(d.pop("datum"), "?")
        return d
    pa, pb = plain(a), plain(b)
    return pa.keys() == pb.keys() and all(
        math.isclose(v, pb[k]) if isinstance(v, (int, float)) and isinstance(pb[k], (int, float)) else v == pb[k]
        for k, v in pa.items())


def _read_window(src, transform: Affine, shape: Tuple[int, int]) -> np.ndarray:
    """The values of an open raster on the pixels of transform and shape (in its CRS), NaN
    where it has none: read as they are when the pixels coincide (the usual case: the
    blocks are on the files' own pixels), resampled bilinearly otherwise."""
    t = src.transform
    out = np.full(shape, np.nan, dtype=np.float32)
    col, row = (transform.c - t.c) / t.a, (transform.f - t.f) / t.e
    if math.isclose(t.a, transform.a, rel_tol=1e-6) and math.isclose(t.e, transform.e, rel_tol=1e-6) \
            and abs(col - round(col)) < 0.01 and abs(row - round(row)) < 0.01:
        r0, c0 = round(row), round(col)
        r1, c1 = max(r0, 0), max(c0, 0)
        r2, c2 = min(r0 + shape[0], src.height), min(c0 + shape[1], src.width)
        if r1 < r2 and c1 < c2:
            part = src.read(1, window=Window(c1, r1, c2 - c1, r2 - r1), masked=True)
            out[r1 - r0:r2 - r0, c1 - c0:c2 - c0] = _clean(part.astype(np.float32).filled(np.nan))
        return out
    left, top = transform.c, transform.f
    right, bottom = left + shape[1] * transform.a, top + shape[0] * transform.e
    c1 = max(math.floor((left - t.c) / t.a) - 2, 0)
    c2 = min(math.ceil((right - t.c) / t.a) + 2, src.width)
    r1 = max(math.floor((top - t.f) / t.e) - 2, 0)
    r2 = min(math.ceil((bottom - t.f) / t.e) + 2, src.height)
    if r1 < r2 and c1 < c2:
        window = Window(c1, r1, c2 - c1, r2 - r1)
        band = _clean(src.read(1, window=window, masked=True).astype(np.float32).filled(np.nan))
        reproject(band, out, src_transform=src.window_transform(window), src_crs=src.crs,
                  dst_transform=transform, dst_crs=src.crs, src_nodata=np.nan, dst_nodata=np.nan,
                  resampling=Resampling.bilinear)
    return out


def _read_block(files: Sequence[Tuple[str, str, int]], crs: str, transform: Affine, shape: Tuple[int, int],
                path: str, what: str) -> Fetched:
    """Compose a block from windows of remote files (name, url, survey year), newest first:
    each file fills only the pixels still without data, and the next one is read only while
    some remain. Saved to path with the names and years of the files used (tags "sources",
    "years"); no file when none of them has data there."""
    block = np.full(shape, np.nan, dtype=np.float32)
    used, years = [], []
    with _gdal_http():
        for name, url, year in files:
            try:
                with rio.open(_remote(url)) as src:
                    if src.crs is not None and not _same_crs(src.crs, crs):
                        print(f"{what}: {name} is in {src.crs.to_string()}, not {crs}; not used")
                        continue
                    values = _read_window(src, transform, shape)
            except rio.errors.RasterioIOError as e:
                if re.search(r"\b404\b|No such file", str(e)):
                    continue  # listed, but not (or no longer) there
                raise RuntimeError(f"Could not read {what} {name}: {cache.clean_error(e)}")
            new = np.isnan(block) & np.isfinite(values)
            if new.any():
                block[new] = values[new]
                used.append(name)
                years.append(str(year))
            if not np.isnan(block).any():
                break
    url = files[0][1] if files else None
    if not used:
        return Fetched(0, url)
    _write_tile(path, block, crs, transform, tags={"sources": ",".join(used), "years": ",".join(years)})
    return Fetched(os.path.getsize(path), url)


class DegreeBlocks(Layer):
    """Blocks of 1°×1° cloud-optimized GeoTIFFs at a fixed URL per tile (3DEP's seamless 1/3″
    DEM, NAD83 geographic), read by HTTP range requests: a tile is about 450 MB, a block of
    0.1° about 2 MB. Block (i, j) covers [i, i + 1) × [j, j + 1) tenths of a degree, cached in
    <folder>/<tile>/<i>_<j>.tif; a tile the service does not have (404: sea, Canada) is missing.
    """

    def __init__(self, description: str, folder: str, url: Callable[[str], str], crs: str,
                 px_per_degree: int, native_res: float, bytes_per_tile: float = 2e6, credit: Optional[Credit] = None):
        self.description, self.folder, self.url, self.crs = description, folder, url, crs
        self.px_per_degree, self.native_res, self._bytes = px_per_degree, native_res, bytes_per_tile
        self.credit = credit

    @staticmethod
    def tile_name(i: int, j: int) -> str:
        """The 1° tile of a block, named by its north-west corner (n38w120: 37-38° N, 120-119° W)."""
        return f"{_hemi(j // 10 + 1, 'n', 's', 2)}{_hemi(i // 10, 'e', 'w', 3)}"

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

    def tile_path(self, cache_dir: str, tile) -> str:
        return os.path.join(cache_dir, self.folder, self.tile_name(*tile), f"{tile[0]}_{tile[1]}.tif")

    def tile_of(self, path: str):
        match = re.fullmatch(rf"{re.escape(self.folder)}/([ns]\d\d[ew]\d\d\d)/(-?\d+)_(-?\d+)\.tif", path)
        if not match or self.tile_name(int(match.group(2)), int(match.group(3))) != match.group(1):
            return None
        return int(match.group(2)), int(match.group(3))

    def bounds_wgs84(self, tile) -> Tuple[float, float, float, float]:
        i, j = tile
        return i / 10, j / 10, (i + 1) / 10, (j + 1) / 10

    def bytes_per_tile(self) -> float:
        return self._bytes

    def tile_url(self, tile) -> Optional[str]:
        return self.url(self.tile_name(*tile))

    def download_tile(self, tile, path: str) -> Fetched:
        i, j = tile
        name = self.tile_name(i, j)
        px = self.px_per_degree // 10
        transform = from_origin(i / 10, (j + 1) / 10, 1 / self.px_per_degree, 1 / self.px_per_degree)
        return _read_block([(name, self.url(name), 0)], self.crs, transform, (px, px), path, self.description)
