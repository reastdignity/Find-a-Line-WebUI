"""Windows: blocks read from big remote files by HTTP range requests (GDAL's /vsicurl/), composed newest first."""

import math
import os
import re
from typing import Dict, NamedTuple, Optional, Sequence, Tuple

import numpy as np
import rasterio as rio
from affine import Affine
from rasterio.warp import Resampling, reproject
from rasterio.windows import Window

import cache
import servicecounts

from ..net import _gdal_http, _remote
from ..layer import Fetched, _clean, _write_tile
from ..composed import Reader


class BlockRequest(NamedTuple):
    """A block to read: the files over it (name, url, survey year), newest first, and its
    pixels (crs, transform, shape)."""
    files: Sequence[Tuple[str, str, int]]
    crs: str
    transform: Affine
    shape: Tuple[int, int]


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
            # One request counted per file read for the block (servicecounts; GDAL's own HTTP requests,
            # their bytes and its retries are not seen)
            with servicecounts.request(url) as counted:
                try:
                    with rio.open(_remote(url)) as src:
                        if src.crs is not None and not _same_crs(src.crs, crs):
                            print(f"{what}: {name} is in {src.crs.to_string()}, not {crs}; not used")
                            continue
                        values = _read_window(src, transform, shape)
                except rio.errors.RasterioIOError as e:
                    if re.search(r"\b404\b|No such file", str(e)):
                        counted.outcome = "not_found"
                        continue  # listed, but not (or no longer) there
                    counted.outcome = "http_5xx" if re.search(r"\b5\d\d\b", str(e)) else "other"
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


class Windows(Reader):
    """Reads a BlockRequest: windows of its files composed newest first (_read_block)."""

    def __init__(self, description: str):
        self.description = description

    def url(self, request: BlockRequest) -> Optional[str]:
        return request.files[0][1] if request.files else None

    def fetch(self, request: BlockRequest, path: str) -> Fetched:
        return _read_block(request.files, request.crs, request.transform, request.shape, path, self.description)
