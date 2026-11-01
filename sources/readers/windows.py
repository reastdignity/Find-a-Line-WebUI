"""Windows: blocks read from big remote files by HTTP range requests (GDAL's /vsicurl/), composed newest first."""

import math
import os
import re
from typing import Dict, NamedTuple, Optional, Sequence, Tuple

import numpy as np
import rasterio as rio
import rasterio.cache
from affine import Affine
from rasterio.warp import Resampling, reproject
from rasterio.windows import Window

import cache
import servicecounts

from .. import net
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


class Incomplete(RuntimeError):
    """A read that GDAL could not complete although it returned values (net.gdal_errors)."""


def _read_file(url: str, crs: str, transform: Affine, shape: Tuple[int, int], name: str,
               what: str) -> Optional[np.ndarray]:
    """The values of one file on a block's pixels (_read_window); None if the file is in another
    CRS. Raises Incomplete when GDAL signalled an error while opening or reading it: values it
    could not fetch come back as nodata or zeros without an exception (net.gdal_errors)."""
    with net.gdal_errors() as errors:
        src = rio.open(_remote(url))
    with src:
        if src.crs is not None and not _same_crs(src.crs, crs):
            print(f"{what}: {name} is in {src.crs.to_string()}, not {crs}; not used")
            return None
        with net.gdal_errors() as reading:
            values = _read_window(src, transform, shape)
    if errors or reading:
        raise Incomplete("; ".join(dict.fromkeys(errors + reading)))
    return values


def _read_block(files: Sequence[Tuple[str, str, int]], crs: str, transform: Affine, shape: Tuple[int, int],
                path: str, what: str) -> Fetched:
    """Compose a block from windows of remote files (name, url, survey year), newest first:
    each file fills only the pixels still without data, and the next one is read only while
    some remain. Saved to path with the names and years of the files used (tags "sources",
    "years"); no file when none of them has data there. A read GDAL could not complete
    although it returned (Incomplete: an answer cut short) is made up to RETRIES times, then
    raises: never a block of what GDAL made of the missing bytes. (Answers that never came GDAL
    asks again itself: net.GDAL_RETRY_CODES; a read it reports as failed raises at once.) After
    any failure GDAL's cache of the file's ranges is dropped (rasterio.cache.invalidate), or
    the next read in this process would find the same short answer there."""
    block = np.full(shape, np.nan, dtype=np.float32)
    used, years = [], []
    with _gdal_http():
        for name, url, year in files:
            for attempt in range(net.RETRIES):
                # One request counted per file read for the block, every attempt (servicecounts;
                # GDAL's own HTTP requests, their bytes and its retries are not seen)
                with servicecounts.request(url) as counted:
                    try:
                        values = _read_file(url, crs, transform, shape, name, what)
                        break
                    except rio.errors.RasterioIOError as e:
                        _forget(url)
                        if re.search(r"\b404\b|No such file", str(e)):
                            counted.outcome = "not_found"
                            values = None
                            break  # listed, but not (or no longer) there
                        counted.outcome = "http_5xx" if re.search(r"\b5\d\d\b", str(e)) else "other"
                        raise RuntimeError(f"Could not read {what} {name}: {cache.clean_error(e)}")
                    except Incomplete as e:
                        _forget(url)
                        counted.outcome = "connection"
                        if attempt == net.RETRIES - 1:
                            raise RuntimeError(f"Could not read {what} {name} completely: "
                                               f"{cache.clean_error(e)}")
                net._sleep(attempt)
            if values is None:
                continue
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


def _forget(url: str):
    """Drop GDAL's cached ranges of a remote file (/vsicurl/ keeps them for the process)."""
    if re.match(r"https?://", url):
        rasterio.cache.invalidate(url)


class Windows(Reader):
    """Reads a BlockRequest: windows of its files composed newest first (_read_block)."""

    def __init__(self, description: str):
        self.description = description

    def url(self, request: BlockRequest) -> Optional[str]:
        return request.files[0][1] if request.files else None

    def fetch(self, request: BlockRequest, path: str) -> Fetched:
        return _read_block(request.files, request.crs, request.transform, request.shape, path, self.description)
