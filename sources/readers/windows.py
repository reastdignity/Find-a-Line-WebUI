"""Windows: blocks read from big remote files by HTTP range requests (GDAL's /vsicurl/), composed newest first."""

import contextlib
import math
import os
import re
import threading
from typing import Dict, Iterator, List, NamedTuple, Optional, Sequence, Tuple

import numpy as np
import rasterio as rio
import rasterio.cache
from affine import Affine
from rasterio.warp import Resampling, reproject, transform_bounds
from rasterio.windows import Window

import cache
import servicecounts

from .. import net
from ..net import _gdal_http, _remote
from ..layer import Fetched, _clean, _write_tile
from ..composed import Reader
from ..vertical import Geoid


class BlockRequest(NamedTuple):
    """A block to read: the files over it (name, url, survey year), newest first, and its
    pixels (crs, transform, shape)."""
    files: Sequence[Tuple[str, str, int]]
    crs: str
    transform: Affine
    shape: Tuple[int, int]


def _horizontal(crs: rio.crs.CRS) -> rio.crs.CRS:
    """The horizontal part of a compound CRS (EPSG:6654, NAD83(CSRS) / UTM zone 11N + CGVD2013 height: EPSG:2955),
    else the CRS itself."""
    wkt = crs.to_wkt()
    if "COMPD_CS" not in wkt and "COMPOUNDCRS" not in wkt:
        return crs
    import pyproj  # only for a compound CRS (BC's 2023+ files)
    parts = pyproj.CRS.from_wkt(wkt).sub_crs_list
    return rio.crs.CRS.from_wkt(parts[0].to_wkt()) if parts else crs


def _same_crs(a, b) -> bool:
    """Whether two CRSs are the same; also when one names only the ellipsoid of the other's
    datum (Alaska's IfSAR files: Alaska Albers on "GRS80, datum not specified"), and when one is
    a compound CRS whose horizontal part is the other (British Columbia's files of 2023 and later
    name NAD83(CSRS) / UTM + CGVD2013 height, EPSG:6653/6654: the heights are what they are, the
    pixels are those of EPSG:3157/2955)."""
    a, b = rio.crs.CRS.from_user_input(a), rio.crs.CRS.from_user_input(b)
    if a == b or (a.to_epsg() is not None and a.to_epsg() == b.to_epsg()):
        return True
    a, b = _horizontal(a), _horizontal(b)
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


def _local(crs: rio.crs.CRS) -> bool:
    """Whether a file's CRS is a bare local one (a LOCAL_CS / engineering CRS: metres with no projection or datum,
    as Caribbean Netherlands' AHN files of 2023 carry)."""
    return not crs.is_projected and not crs.is_geographic and crs.to_wkt().startswith(("LOCAL_CS", "ENGCRS",
                                                                                        "ENGINEERINGCRS"))


def _wrong_crs(src, crs: str, force_crs: bool, warp: Optional[Resampling] = None) -> bool:
    """Whether an open file's CRS rules it out for a block in crs: another CRS (_same_crs), unless force_crs and the
    file names only a local one (_local), which is then taken as crs, or warp and the file names a real one (it is
    then warped onto the block: _values_on); a file without a CRS is taken as it is."""
    if src.crs is None or _same_crs(src.crs, crs):
        return False
    if _local(src.crs):
        return not force_crs
    return warp is None


def _warped(src, crs: str, warp: Optional[Resampling]) -> bool:
    """Whether a file is read through the warper (_warp_window): warp set and the file in a real CRS other than the
    block's (a local CRS with force_crs is taken as the block's, a file without a CRS as it is)."""
    return warp is not None and src.crs is not None and not _local(src.crs) and not _same_crs(src.crs, crs)


def _warp_window(src, crs: str, transform: Affine, shape: Tuple[int, int], warp: Resampling) -> np.ndarray:
    """The values of an open raster in another CRS on the pixels of transform and shape in crs, NaN where it has
    none, resampled with warp: the file's window under the block (its box in the file's CRS, two pixels more on
    every side) read as _read_window reads one (_read_masked: no HTTP request holding the GIL), cleaned (its nodata
    and values below VALID_MIN as NaN: _clean), then reprojected from that array (no dataset behind it, so the
    warper's initialisation asks nothing), one thread (the pitfall of mosaic.WARP_KWARGS). Not a WarpedVRT: GDAL's
    warper leaves out only the file's nodata, so an average would take in other invalid values (a -9999 in a file
    whose nodata is -3.4e38). Cyprus' tiles, kept by DLS in EPSG:4258, read onto blocks of CGRS93 / Cyprus LTM."""
    out = np.full(shape, np.nan, dtype=np.float32)
    bounds = (transform.c, transform.f + shape[0] * transform.e, transform.c + shape[1] * transform.a, transform.f)
    left, bottom, right, top = transform_bounds(crs, src.crs, *bounds, densify_pts=21)
    t = src.transform
    cols = sorted(((left - t.c) / t.a, (right - t.c) / t.a))
    rows = sorted(((top - t.f) / t.e, (bottom - t.f) / t.e))
    c1, c2 = max(math.floor(cols[0]) - 2, 0), min(math.ceil(cols[1]) + 2, src.width)
    r1, r2 = max(math.floor(rows[0]) - 2, 0), min(math.ceil(rows[1]) + 2, src.height)
    if r1 >= r2 or c1 >= c2:
        return out
    window = Window(c1, r1, c2 - c1, r2 - r1)
    band = _clean(_read_masked(src, window).astype(np.float32).filled(np.nan))
    reproject(band, out, src_transform=src.window_transform(window), src_crs=src.crs, dst_transform=transform,
              dst_crs=crs, src_nodata=np.nan, dst_nodata=np.nan, resampling=warp, num_threads=1)
    return out


def _values_on(src, crs: str, transform: Affine, shape: Tuple[int, int],
               warp: Optional[Resampling] = None) -> np.ndarray:
    """The values of an open raster on a block's pixels: warped from another CRS (_warped: _warp_window), else as
    _read_window reads them."""
    if _warped(src, crs, warp):
        return _warp_window(src, crs, transform, shape, warp)
    return _read_window(src, transform, shape)


def _scan_directories(src, window: Window):
    """Make GDAL read a remote file's directories (its overviews and masks) in a call that releases the GIL, before
    src.read(..., masked=True) reads window. rasterio (1.5.2) asks the mask flags on every read, masked or not,
    holding the GIL (GDALGetMaskFlags, not under nogil), and GTiff's first such call on a dataset runs its deferred
    scan of the directories: HTTP requests whenever their bytes are not in GDAL's cache (a file that is not a COG,
    whose directories lie beyond the bytes the open fetched: Alaska's IfSAR files, 3 requests and 0.6 s a block; or
    any file once another thread's failure dropped the cache, _forget). Every other Python thread of the process
    then waits on that request; a server in the same process (the tests') cannot answer at all, and the read waited
    GDAL_HTTP_TIMEOUT 120 s times its retries (test_answers_cut_short_every_time, 2026-11-13).

    The scan is run here by a downsampled read of the whole window at factor at most 1.5 (sides ceil(n / 1.5); at
    least 3 px each way, kept inside the raster) through rasterio's private DatasetReaderBase._read, which releases the
    GIL and asks no flags: GTiff's IRasterIO asks the overview count for a downsampled read, which scans the
    directories. No overview is used: GDAL 3.12.2 takes one for a nearest read only when its factor is below 1.2 times
    the asked one plus 0.1 (GDALBandGetBestOverviewLevel2, GDAL_OVERVIEW_OVERSAMPLING_THRESHOLD unset), 1.9 at most
    here, and a file's first overview is about 2. Its tiles stay in GDAL's block cache, where the read finds them:
    the same requests and bytes per block as the read alone (measured on COGs and on a file with its directories at
    the end, multi-range and serial), and the same values (the read is rasterio's own; this one's are thrown away).
    A GDAL error here is the read's own error (inside its gdal_errors; a failure raises RasterioIOError as the read
    would). Relies on rasterio 1.5.2 and GDAL 3.12.2 (checked 2026-11-13); without a _read of that form the read goes
    on as before, and tests/test_window_gil.py fails."""
    read = getattr(src, "_read", None)
    width, height = min(max(int(window.width), 3), src.width), min(max(int(window.height), 3), src.height)
    if read is None or width < 2 or height < 2:
        return
    col = max(min(int(window.col_off), src.width - width), 0)
    row = max(min(int(window.row_off), src.height - height), 0)
    sides = [max(1, min(n - 1, math.ceil(n / 1.5))) for n in (height, width)]  # factor at most 1.5
    out = np.empty((1, *sides), dtype=src.dtypes[0])
    try:
        read([1], out, Window(col, row, width, height), src.dtypes[0])
    except TypeError:  # another rasterio: not of this form
        return


def _read_masked(src, window: Window) -> np.ma.MaskedArray:
    """src.read(1, window=window, masked=True), with no HTTP request made holding the GIL for a remote file
    (/vsicurl/: _scan_directories first)."""
    if src.name.startswith("/vsicurl/"):
        _scan_directories(src, window)
    return src.read(1, window=window, masked=True)


def _read_window(src, transform: Affine, shape: Tuple[int, int]) -> np.ndarray:
    """The values of an open raster on the pixels of transform and shape (in its CRS), NaN
    where it has none: read as they are when the pixels coincide (the usual case: the
    blocks are on the files' own pixels), resampled bilinearly otherwise."""
    t = src.transform
    out = np.full(shape, np.nan, dtype=np.float32)
    origin = _coincide(src, transform)
    if origin is not None:
        r0, c0 = origin
        r1, c1 = max(r0, 0), max(c0, 0)
        r2, c2 = min(r0 + shape[0], src.height), min(c0 + shape[1], src.width)
        if r1 < r2 and c1 < c2:
            part = _read_masked(src, Window(c1, r1, c2 - c1, r2 - r1))
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
        band = _clean(_read_masked(src, window).astype(np.float32).filled(np.nan))
        reproject(band, out, src_transform=src.window_transform(window), src_crs=src.crs,
                  dst_transform=transform, dst_crs=src.crs, src_nodata=np.nan, dst_nodata=np.nan,
                  resampling=Resampling.bilinear)
    return out


class Incomplete(RuntimeError):
    """A read that GDAL could not complete although it returned values (net.gdal_errors)."""


class WrongCrs(RuntimeError):
    """A listed file in another CRS than its block's (_same_crs): not used for the block. The block's other
    files may still serve it (the USA's 1 m DEM lists a project's files of the neighbouring zone too); a
    block none of whose files could be read for this reason is a failure, never "missing" (a PROJ that
    does not resolve the files' CRS would otherwise lose a whole layer in silence: ArcticDEM over Jan Mayen,
    "0 of 1252 tiles", 2026-11-08)."""

    def __init__(self, what: str, name: str, found: str, expected: str):
        super().__init__(f"{what}: {name} is in {found}, not {expected}")
        self.name, self.found, self.expected = name, found, expected


def _read_file(url: str, crs: str, transform: Affine, shape: Tuple[int, int], name: str,
               what: str, force_crs: bool = False, warp: Optional[Resampling] = None) -> np.ndarray:
    """The values of one file on a block's pixels (_values_on). Raises WrongCrs when the file is in
    another CRS (with force_crs, a file naming only a local CRS is taken in crs; with warp, a file in another
    real CRS is warped: _wrong_crs), Incomplete when GDAL signalled an error while opening or reading it: values
    it could not fetch come back as nodata or zeros without an exception (net.gdal_errors). The open is retried
    net.OPEN_RETRIES times, the reads after it as _gdal_http says (net.open_gdal)."""
    with net.gdal_errors() as errors:
        src = net.open_gdal(_remote(url))
    with src:
        if _wrong_crs(src, crs, force_crs, warp):
            raise WrongCrs(what, name, src.crs.to_string(), crs)
        with net.gdal_errors() as reading:
            values = _values_on(src, crs, transform, shape, warp)
    if errors or reading:
        raise Incomplete("; ".join(dict.fromkeys(errors + reading)))
    return values


def _read_ranged(url: str, crs: str, transform: Affine, shape: Tuple[int, int], name: str, what: str,
                 force_crs: bool = False, warp: Optional[Resampling] = None) -> Optional[np.ndarray]:
    """The values of one remote file on a block's pixels read through our own range requests (ranges.open_remote,
    the first bytes checked to be a TIFF's), never GDAL's /vsicurl/: a URL GDAL will not open as a .tif (Estonia's
    PHP download address) or a server that answers its errors as a part of a file (HTTP 206 with an HTML page). None
    when the file is not there (404); WrongCrs as _read_file. Every range is asked again by get_range itself
    (net.RETRIES), so a failure here raises RuntimeError at once, never a block of what came."""
    from . import ranges
    try:
        with net.gdal_errors() as errors, ranges.open_remote(url, tiff_only=True) as (src, file):
            if not errors and file.error is None:
                if _wrong_crs(src, crs, force_crs, warp):
                    raise WrongCrs(what, name, src.crs.to_string(), crs)
                values = _ranged_values(src, file, crs, transform, shape, warp)
        problem = file.error or ("; ".join(dict.fromkeys(errors)) if errors else None)
    except ranges.Missing:  # the file is not there (its first range: the open)
        return None
    except (WrongCrs, net.Unreachable):  # an Unreachable keeps its own message (net.unreachable)
        raise
    except (rio.errors.RasterioIOError, ranges.NotTiff) as e:
        raise RuntimeError(f"Could not read {what} {name}: {cache.clean_error(e)}")
    except RuntimeError as e:  # a prefetched range that could not be read whole (ranges.get_range)
        raise RuntimeError(f"Could not read {what} {name} completely: {cache.clean_error(e)}")
    if problem:
        if isinstance(file.error, net.Unreachable):
            raise file.error
        raise RuntimeError(f"Could not read {what} {name} completely: {cache.clean_error(problem)}")
    return values


def _ranged_values(src, file, crs: str, transform: Affine, shape: Tuple[int, int],
                   warp: Optional[Resampling] = None) -> np.ndarray:
    """The values of a file opened through our own ranges (ranges.open_remote) on a block's pixels: a block on the
    file's own pixels (_coincide) read as a group reads it (_group_values: in strips, each strip's tiles prefetched,
    a request per run of tiles), any other block (warped, off the file's pixels) as _values_on reads it. GDAL alone
    reads a big window through 64 KB plain reads: 37-127 requests for a block of 2000 x 2000 px of a file like
    Sint Eustatius', 11 in strips (measured 2026-11-24), each a turn of basisdata.nl's 54 a minute. A prefetched
    range that could not be read whole raises (RuntimeError, net.Unreachable), never a block of what came; a
    missing range (404) of a file that was there is such a failure, not a missing file."""
    from . import ranges
    if _warped(src, crs, warp) or _coincide(src, transform) is None:
        return _values_on(src, crs, transform, shape, warp)
    try:
        (_, values), = list(_group_values(src, [BlockRequest((), crs, transform, shape)], file, warp))
    except ranges.Missing as e:
        raise RuntimeError(f"HTTP 404 for a range of a file that was there: {cache.clean_error(e)}") from e
    return values


def _read_block(files: Sequence[Tuple[str, str, int]], crs: str, transform: Affine, shape: Tuple[int, int],
                path: str, what: str, geoid: Optional[Geoid] = None, serial: bool = False,
                force_crs: bool = False, warp: Optional[Resampling] = None, ranged: bool = False) -> Fetched:
    """Compose a block from windows of remote files (name, url, survey year), newest first:
    each file fills only the pixels still without data, and the next one is read only while
    some remain. Saved to path with the names and years of the files used (tags "sources",
    "years"); no file when none of them has data there. A read GDAL could not complete
    although it returned (Incomplete: an answer cut short) is made up to RETRIES times, then
    raises: never a block of what GDAL made of the missing bytes. (Answers that never came GDAL
    asks again itself: net.GDAL_RETRY_CODES; a read it reports as failed raises at once.) After
    any failure GDAL's cache of the file's ranges is dropped (rasterio.cache.invalidate), or
    the next read in this process would find the same short answer there.

    With geoid (heights above the ellipsoid: ArcticDEM), the block is saved as h - N, heights above that geoid
    (tag "vertical": its name); N is computed first, so a missing grid (GeoidMissing) asks no file. serial: the
    ranges one after another through GDAL's cache of ranges (net._gdal_http). A file in another CRS is not
    used (said); when no file of the block could be read for that reason, the block raises (WrongCrs).
    force_crs: a file naming only a local CRS is read in the block's CRS (_wrong_crs). warp: a file in another
    real CRS is warped onto the block's pixels with that resampling (_warp_window). ranged: each remote file read
    through our own range requests (_read_ranged), not GDAL's /vsicurl/."""
    undulation = geoid.undulation(crs, transform, shape) if geoid is not None and files else None
    block = np.full(shape, np.nan, dtype=np.float32)
    used, years = [], []
    wrong: List[WrongCrs] = []
    read = 0  # files read for the block, in its CRS (with or without data there)
    # A host of one connection (net.single_connection: basisdata.nl) has its ranges asked one after another
    with _gdal_http(serial or any(net.single_connection(url) for _, url, _ in files)):
        for name, url, year in files:
            if ranged and re.match(r"https?://", url):
                try:
                    values = _read_ranged(url, crs, transform, shape, name, what, force_crs, warp)
                    read += values is not None
                except WrongCrs as e:
                    print(f"{e}; not used")
                    wrong.append(e)
                    values = None
                if _apply(block, values, used, years, name, year):
                    break
                continue
            for attempt in range(net.RETRIES):
                # One request per file read for the block, every attempt: its turn of the host's rate
                # (net.rate_turn; the caller holds the host's slot) and counted (servicecounts; GDAL's own
                # HTTP requests, their bytes and its retries are not seen)
                net.rate_turn(url)
                with servicecounts.request(url, read=True) as counted:
                    try:
                        values = _read_file(url, crs, transform, shape, name, what, force_crs, warp)
                        read += 1
                        break
                    except WrongCrs as e:
                        print(f"{e}; not used")
                        wrong.append(e)
                        values = None
                        break
                    except rio.errors.RasterioIOError as e:
                        _forget(url)
                        if re.search(r"\b404\b|No such file", str(e)):
                            counted.outcome = "not_found"
                            values = None
                            break  # listed, but not (or no longer) there
                        counted.outcome = "http_5xx" if re.search(r"\b5\d\d\b", str(e)) else "other"
                        # No connection could be made (GDAL's own retries done): the download's other blocks
                        # of the host fail at once (net.UnreachableHosts)
                        if net.connect_failed(e):
                            raise net.unreachable(url, e)
                        raise RuntimeError(f"Could not read {what} {name}: {cache.clean_error(e)}")
                    except Incomplete as e:
                        _forget(url)
                        counted.outcome = "connection"
                        if attempt == net.RETRIES - 1:
                            raise RuntimeError(f"Could not read {what} {name} completely: "
                                               f"{cache.clean_error(e)}")
                net._sleep(attempt)
            if _apply(block, values, used, years, name, year):
                break
    if wrong and not read:
        raise RuntimeError(f"{wrong[0]}; no file of this block could be read in its CRS")
    url = files[0][1] if files else None
    tags = _finish(block, used, years, undulation, geoid)
    if tags is None:
        return Fetched(0, url)
    _write_tile(path, block, crs, transform, tags=tags)
    return Fetched(os.path.getsize(path), url)


def _apply(block: np.ndarray, values: Optional[np.ndarray], used: list, years: list, name: str, year) -> bool:
    """A file's values into the pixels of the block still without data (noting the file when it gave some);
    whether the block is full now."""
    if values is not None:
        new = np.isnan(block) & np.isfinite(values)
        if new.any():
            block[new] = values[new]
            used.append(name)
            years.append(str(year))
    return not np.isnan(block).any()


def _finish(block: np.ndarray, used: list, years: list, undulation: Optional[np.ndarray],
            geoid: Optional[Geoid]) -> Optional[Dict[str, str]]:
    """The tags of a composed block (h - N applied to it with geoid), or None when no file had data there."""
    if not used:
        return None
    tags = {"sources": ",".join(used), "years": ",".join(years)}
    if undulation is not None:
        block -= undulation
        tags["vertical"] = geoid.name
    return tags


def _coincide(src, transform: Affine) -> Optional[Tuple[int, int]]:
    """The row and column of the file where a block's first pixel lies, when the block is on the file's own
    pixels (the condition of _read_window), else None."""
    t = src.transform
    col, row = (transform.c - t.c) / t.a, (transform.f - t.f) / t.e
    if math.isclose(t.a, transform.a, rel_tol=1e-6) and math.isclose(t.e, transform.e, rel_tol=1e-6) \
            and abs(col - round(col)) < 0.01 and abs(row - round(row)) < 0.01:
        return round(row), round(col)
    return None


# Rows of a group's window read at a time (_strips): GTiff fetches the tiles of a read in one multi-range call
# only up to some size; beyond it, tile by tile (Luxembourg's 6000 x 4000 px of float64: 831 requests whole,
# 36 in strips of 512 rows, the same bytes; 2026-11-04)
STRIP_ROWS = 512
TILE_PAD = 64  # bytes prefetched before and after each tile of a strip (_tile_ranges)


def _strips(src, r1: int, r2: int) -> List[Tuple[int, int]]:
    """Rows r1..r2 of a file in strips of about STRIP_ROWS ending on the edges of its rows of internal tiles."""
    step = max(1, STRIP_ROWS // src.block_shapes[0][0]) * src.block_shapes[0][0]
    edges = [r1] + list(range((r1 // step + 1) * step, r2, step)) + [r2]
    return list(zip(edges[:-1], edges[1:]))


def _tile_ranges(src, c1: int, r1: int, c2: int, r2: int) -> List[Tuple[int, int]]:
    """(offset, size) of the file's internal tiles (or strips) under rows r1..r2 and columns c1..c2 of band 1, from
    its header (BLOCK_OFFSET/BLOCK_SIZE), with TILE_PAD bytes before and after each: GDAL reads a COG's leader and
    trailer too, and asks a row of tiles 4 bytes beyond the last one's trailer (Canada's mosaic, 2026-11-04; a range
    reaching past the prefetched bytes is fetched again whole); tiles without data (offset 0) left out."""
    bh, bw = src.block_shapes[0]
    found = []
    for ty in range(r1 // bh, (r2 - 1) // bh + 1):
        for tx in range(c1 // bw, (c2 - 1) // bw + 1):
            offset = int(src.get_tag_item(f"BLOCK_OFFSET_{tx}_{ty}", "TIFF", bidx=1) or 0)
            size = int(src.get_tag_item(f"BLOCK_SIZE_{tx}_{ty}", "TIFF", bidx=1) or 0)
            if offset > 0 and size > 0:
                found.append((max(offset - TILE_PAD, 0), size + 2 * TILE_PAD))
    return found


def _read_strips(src, c1: int, r1: int, c2: int, r2: int, file=None) -> np.ma.MaskedArray:
    """A window of a file read as src.read(1, window, masked=True) reads it, in strips (_strips), the tiles of each
    strip fetched beforehand when file can (RangeFile.prefetch)."""
    data = np.empty((r2 - r1, c2 - c1), dtype=src.dtypes[0])
    mask = np.zeros((r2 - r1, c2 - c1), dtype=bool)
    for a, b in _strips(src, r1, r2):
        if hasattr(file, "prefetch"):
            file.prefetch(_tile_ranges(src, c1, a, c2, b))
        part = src.read(1, window=Window(c1, a, c2 - c1, b - a), masked=True)
        data[a - r1:b - r1] = part.data
        mask[a - r1:b - r1] = np.ma.getmaskarray(part)
    if hasattr(file, "prefetch"):
        file.prefetch([])
    return np.ma.MaskedArray(data, mask)


def _group_values(src, blocks: Sequence[BlockRequest], file=None,
                  warp: Optional[Resampling] = None) -> Iterator[Tuple[int, np.ndarray]]:
    """The values of an open raster on the pixels of each block, as _values_on gives them, as (index, values) one
    block after another (so that the caller holds the window and one block's values, not every block's twice): the
    blocks on the file's own pixels from one window over all of them (read once, in strips, and sliced), the others
    by _values_on (warped from another CRS with warp, else _read_window)."""
    at = {}
    for k, r in enumerate(blocks):
        origin = None if _warped(src, r.crs, warp) else _coincide(src, r.transform)
        if origin is None:
            yield k, _values_on(src, r.crs, r.transform, r.shape, warp)
        else:
            at[k] = origin
    if at:
        r1 = max(min(r0 for r0, _ in at.values()), 0)
        c1 = max(min(c0 for _, c0 in at.values()), 0)
        r2 = min(max(r0 + blocks[k].shape[0] for k, (r0, _) in at.items()), src.height)
        c2 = min(max(c0 + blocks[k].shape[1] for k, (_, c0) in at.items()), src.width)
        window = _read_strips(src, c1, r1, c2, r2, file) if r1 < r2 and c1 < c2 else None
        for k, (r0, c0) in at.items():
            shape = blocks[k].shape
            values = np.full(shape, np.nan, dtype=np.float32)
            br1, bc1 = max(r0, 0), max(c0, 0)
            br2, bc2 = min(r0 + shape[0], src.height), min(c0 + shape[1], src.width)
            if window is not None and br1 < br2 and bc1 < bc2:
                part = window[br1 - r1:br2 - r1, bc1 - c1:bc2 - c1]
                values[br1 - r0:br2 - r0, bc1 - c0:bc2 - c0] = _clean(part.astype(np.float32).filled(np.nan))
            yield k, values


def read_group(blocks: Sequence[BlockRequest], what: str, geoid: Optional[Geoid] = None,
               force_crs: bool = False, warp: Optional[Resampling] = None,
               tiff_only: bool = False) -> List[Tuple[Optional[np.ndarray], Optional[Dict[str, str]]]]:
    """Compose blocks as _read_block composes each one (files newest first, each filling only the pixels still
    without data, the next one read only for the blocks with some left; tags "sources" and "years"; with geoid
    h - N), reading each file once for the blocks that need it: one window through our own range requests
    (ranges.open_remote: every answer checked whole), sliced into the blocks (_group_values). The blocks are
    those of one CRS. Returns (values, tags) per block, (None, None) where no file has data. A file of another
    CRS is not used (said) and a missing one (404) skipped, as there; a block none of whose files could be read
    for its CRS, and anything else, raises RuntimeError (the caller then reads the group's blocks one by one,
    where such a block fails alone). force_crs and warp: as _read_block's; tiff_only: a file whose first bytes
    are not a TIFF's raises (ranges.NotTiff: a server's error page served as a part of the file)."""
    from . import ranges
    state = [[np.full(r.shape, np.nan, dtype=np.float32), [], [], None, not r.files] for r in blocks]
    for s, r in zip(state, blocks):
        if geoid is not None and r.files:
            s[3] = geoid.undulation(r.crs, r.transform, r.shape)
    opened: Dict[str, Optional[tuple]] = {}
    wrong: Dict[str, WrongCrs] = {}  # the files in another CRS, by URL
    read = [False] * len(blocks)     # whether a file was read for the block
    with contextlib.ExitStack() as stack:
        for k in range(max((len(r.files) for r in blocks), default=0)):
            need: Dict[Tuple[str, str, int], List[int]] = {}
            for b, r in enumerate(blocks):
                if not state[b][4] and k < len(r.files):
                    need.setdefault(tuple(r.files[k]), []).append(b)
            for (name, url, year), members in need.items():
                if url not in opened:
                    try:
                        opened[url] = _open_for_group(stack, ranges, url, blocks[members[0]].crs, name, what,
                                                      force_crs, warp, tiff_only)
                    except WrongCrs as e:
                        print(f"{e}; not used")
                        wrong[url], opened[url] = e, None
                if opened[url] is None:
                    continue
                src, file = opened[url]
                with net.gdal_errors() as errors:
                    try:  # each block's values applied as they come: an error below discards the whole group
                        for m, v in _group_values(src, [blocks[b] for b in members], file, warp):
                            s = state[members[m]]
                            s[4] = _apply(s[0], v, s[1], s[2], name, year)
                            read[members[m]] = True
                    except rio.errors.RasterioIOError as e:
                        raise RuntimeError(f"Could not read {what} {name}: {cache.clean_error(file.error or e)}") from e
                if errors or file.error is not None:
                    raise RuntimeError(f"Could not read {what} {name} completely: "
                                       f"{cache.clean_error(file.error or '; '.join(dict.fromkeys(errors)))}")
    unserved = [next(wrong[url] for _, url, _ in r.files if url in wrong) for b, r in enumerate(blocks)
                if not read[b] and any(url in wrong for _, url, _ in r.files)]
    if unserved:
        raise RuntimeError(f"{unserved[0]}; no file of {len(unserved)} blocks could be read in its CRS")
    return [((s[0], tags) if (tags := _finish(s[0], s[1], s[2], s[3], geoid)) else (None, None)) for s in state]


def _open_for_group(stack: contextlib.ExitStack, ranges, url: str, crs: str, name: str, what: str,
                    force_crs: bool = False, warp: Optional[Resampling] = None, tiff_only: bool = False):
    """A file of a group opened through ranges.open_remote (a local path as it is), or None when it is missing;
    WrongCrs when it is in another CRS (as _read_file raises it, force_crs and warp too)."""
    try:
        with net.gdal_errors() as errors:
            if re.match(r"https?://", url):
                src, file = stack.enter_context(ranges.open_remote(url, tiff_only=tiff_only))
            else:
                src, file = stack.enter_context(rio.open(url)), None
    except ranges.Missing:
        return None
    except (rio.errors.RasterioIOError, ranges.NotTiff) as e:
        raise RuntimeError(f"Could not read {what} {name}: {cache.clean_error(e)}")
    if errors or (file is not None and file.error is not None):
        raise RuntimeError(f"Could not open {what} {name} completely: "
                           f"{cache.clean_error((file and file.error) or '; '.join(dict.fromkeys(errors)))}")
    if _wrong_crs(src, crs, force_crs, warp):
        raise WrongCrs(what, name, src.crs.to_string(), crs)
    return src, file or _LocalFile()


class _LocalFile:
    """What read_group asks of a RangeFile, for a file on disk."""
    error = None


def _forget(url: str):
    """Drop GDAL's cached ranges of a remote file (/vsicurl/ keeps them for the process)."""
    if re.match(r"https?://", url):
        rasterio.cache.invalidate(url)


# USGS's OPR DEMs (tnm.OprBlocks): each file brought onto 1 m blocks by its own header's pixel in metres (the user's
# N4, D4 and W1 of 2026-11-26/27; docs/resampling.md, "When a block or a file is read"): the method of each pixel
# class and its version. A block's key holds the versions of the methods its files' surveys' sampled headers take
# (versions.block_key, the token tnm.opr_items makes): a changed method takes a new version, and the blocks of the
# surveys whose record names that method are read again. The limit: a block holding a file outside its survey's
# sampled classes (read by its own method all the same, named once) keeps its content after a change of that
# file's method until the layer's `processing` is raised, which reads every OPR block again.
# cubic 2: the kernel's scale fixed at the file's pixel over the block's (opr_scale; the user's decision of 2026-11-27)
OPR_METHODS = {"copy": 1, "average": 1, "cubic": 2}
# Source pixels read around a block for each method: cubic's kernel, widened by GDAL for a source finer than the
# block, reaches 2.6 pixels of a 0.762 m file beyond the block's edge, more for a file turned against the zone;
# gate B-1a measured a margin of 2 already equal to a warp of a window 150 m larger (two State Plane surveys, about
# 1° against the zone); 4 is kept for files turned further (tests/test_opr_reader.py: 10°)
OPR_MARGIN = {"copy": 2, "average": 2, "cubic": 4}
OPR_REACH_M = 5.0      # a block's files: those whose box meets its square grown by this (versions.ComposedBlocks.reach)
OPR_FINER = 0.75       # below this pixel (metres) a file is averaged
OPR_MAX_PIXEL_M = 1.001  # above it a file is not read (the user's D4: "1 m or finer")
# Two linear units (metres per unit) are one for the guard of a survey's one height factor when this close
# (relative): the foot and the US survey foot (2e-6 apart) and a header storing a rounded 0.3048006 are one, metres
# and feet two (oprsurveys._distinct_units and _opr_file's guard; fix round 3)
UNIT_REL_TOL = 1e-5
_opr_named: set = set()
_opr_named_lock = threading.Lock()


def _opr_name(key: str, text: str):
    """Print a file left out once per process."""
    with _opr_named_lock:
        if key in _opr_named:
            return
        _opr_named.add(key)
    print(text, flush=True)


def opr_method(src, crs: str, transform: Affine) -> Tuple[Optional[str], str]:
    """The method an open OPR file takes onto a block (crs, transform of 1 m pixels) by its own header, and why not
    when None: on the block's pixels (_same_crs and _coincide) copied; its pixel in metres (the pixel in its CRS's
    unit times that unit) below OPR_FINER averaged, up to OPR_MAX_PIXEL_M cubic; coarser, or a geographic, local or
    missing CRS, or a geotransform with rotation terms (no file of that kind is known; its pixel is not abs(a): the
    code review's F8): not read."""
    if src.crs is None or not src.crs.is_projected:
        return None, "it has no projected CRS"
    if src.transform.b or src.transform.d:
        return None, "its geotransform is rotated"
    pixel = abs(src.transform.a) * src.crs.linear_units_factor[1]
    if _same_crs(src.crs, crs) and _coincide(src, transform) is not None:
        return "copy", ""
    if pixel < OPR_FINER:
        return "average", ""
    if pixel <= OPR_MAX_PIXEL_M:
        return "cubic", ""
    return None, f"its pixel is {pixel:.3f} m (coarser than {OPR_MAX_PIXEL_M:g} m)"


class _OprPart(NamedTuple):
    """A file's window read for a block: its values (times the survey's factor), their transform and CRS, its
    method and survey, and the file's name."""
    values: np.ndarray
    transform: Affine
    crs: rio.crs.CRS
    method: str
    survey: str
    name: str
    year: int


def _opr_read(src, crs: str, transform: Affine, shape: Tuple[int, int], method: str, factor: float):
    """An open file's values for a block: on the block's pixels (copy) as _read_window reads them, else its window
    under the block plus OPR_MARGIN[method] source pixels (clamped to the file) with its transform; the file's
    nodata and floor (_clean, in its own unit) first, then times factor. (values, transform) or None when the
    window misses the file."""
    if method == "copy":
        values = _read_window(src, transform, shape)
        return (values * np.float32(factor) if factor != 1 else values), transform
    bounds = (transform.c, transform.f + shape[0] * transform.e, transform.c + shape[1] * transform.a, transform.f)
    left, bottom, right, top = (bounds if _same_crs(src.crs, crs) else
                                transform_bounds(crs, src.crs, *bounds, densify_pts=21))
    t, m = src.transform, OPR_MARGIN[method]
    cols = sorted(((left - t.c) / t.a, (right - t.c) / t.a))
    rows = sorted(((top - t.f) / t.e, (bottom - t.f) / t.e))
    c1, c2 = max(math.floor(cols[0]) - m, 0), min(math.ceil(cols[1]) + m, src.width)
    r1, r2 = max(math.floor(rows[0]) - m, 0), min(math.ceil(rows[1]) + m, src.height)
    if r1 >= r2 or c1 >= c2:
        return None
    window = Window(c1, r1, c2 - c1, r2 - r1)
    values = _clean(_read_masked(src, window).astype(np.float32).filled(np.nan))
    if factor != 1:
        values *= np.float32(factor)
    return values, src.window_transform(window)


def _opr_file(url: str, crs: str, transform: Affine, shape: Tuple[int, int], name: str, year: int, what: str,
              rule: Tuple[float, Sequence[str], str]):
    """One OPR file's part for a block (_OprPart), or None: not there (404), or no method by its own header
    (opr_method: its pixel above OPR_MAX_PIXEL_M, a geographic or missing CRS, rotation terms; or its horizontal
    linear unit not among those of the files its survey's height unit was measured on: rule's fourth part; named
    once). Every other file is read by the method its own header takes (the user's D4 and N4), also when its survey's sampled
    headers took others (rule: the factor, those methods, the survey): then it is named once, the record is not
    changed. The open and read as _read_file's: Incomplete when GDAL signalled an error, at the open before anything
    is decided from the header (a header read cut short can look like one without a CRS: the code review's F4)."""
    factor, expected, survey = rule[:3]
    units = rule[3] if len(rule) > 3 else ()  # the sampled files' horizontal units (tnm.OprIndex.rule_of)
    with net.gdal_errors() as errors:
        src = net.open_gdal(_remote(url))
    with src:
        if errors:
            raise Incomplete("; ".join(dict.fromkeys(errors)))
        method, why = opr_method(src, crs, transform)
        if method is None:
            _opr_name(f"{url}:none", f"{what}: {name} left out: {why}")
            return None
        unit = src.crs.linear_units_factor[1]
        if units and not any(math.isclose(unit, u, rel_tol=UNIT_REL_TOL) for u in units):
            # the survey's one factor was measured on files of other units: a heuristic guard against metres beside
            # feet (a mosaic in metres beside tiles in feet; the scope review's S2); the foot and the US survey foot
            # count as one (UNIT_REL_TOL)
            _opr_name(f"{url}:unit", f"{what}: survey {survey}: file {name} left out: it is in another unit than the "
                                     f"files its height unit was measured on")
            return None
        if method not in expected:
            _opr_name(f"{url}:{method}", f"{what}: survey {survey}: file {name} takes {method}, its record says "
                                         f"{'+'.join(expected) or 'none'}")
        with net.gdal_errors() as reading:
            got = _opr_read(src, crs, transform, shape, method, factor)
            src_crs = src.crs
    if reading:
        raise Incomplete("; ".join(dict.fromkeys(reading)))
    if got is None:
        return None
    return _OprPart(got[0], got[1], src_crs, method, survey, name, year)


def _opr_file_retried(url: str, crs: str, transform: Affine, shape: Tuple[int, int], name: str, year: int,
                      what: str, rule: Tuple[float, Sequence[str], str]) -> Optional[_OprPart]:
    """_opr_file with _read_block's retries: each attempt a turn of the host's rate and counted; a 404 is no file;
    a read cut short is made up to RETRIES times, GDAL's cache of the file dropped after any failure."""
    for attempt in range(net.RETRIES):
        net.rate_turn(url)
        with servicecounts.request(url, read=True) as counted:
            try:
                return _opr_file(url, crs, transform, shape, name, year, what, rule)
            except rio.errors.RasterioIOError as e:
                _forget(url)
                if re.search(r"\b404\b|No such file", str(e)):
                    counted.outcome = "not_found"
                    return None
                counted.outcome = "http_5xx" if re.search(r"\b5\d\d\b", str(e)) else "other"
                if net.connect_failed(e):
                    raise net.unreachable(url, e)
                raise RuntimeError(f"Could not read {what} {name}: {cache.clean_error(e)}")
            except Incomplete as e:
                _forget(url)
                counted.outcome = "connection"
                if attempt == net.RETRIES - 1:
                    raise RuntimeError(f"Could not read {what} {name} completely: {cache.clean_error(e)}")
        net._sleep(attempt)
    return None


def _same_lattice(a: _OprPart, b: _OprPart) -> bool:
    """Whether two parts lie on one lattice: one survey and method, the same CRS and pixel, origins a whole number of
    pixels apart (tiles of one survey: joined before the one warp)."""
    if a.survey != b.survey or a.method != b.method or a.method == "copy" or a.crs != b.crs:
        return False
    ta, tb = a.transform, b.transform
    if not (math.isclose(ta.a, tb.a, rel_tol=1e-9) and math.isclose(ta.e, tb.e, rel_tol=1e-9)
            and ta.b == tb.b == ta.d == tb.d == 0):
        return False
    dc, dr = (tb.c - ta.c) / ta.a, (tb.f - ta.f) / ta.e
    return abs(dc - round(dc)) < 1e-3 and abs(dr - round(dr)) < 1e-3


def _join(parts: Sequence[_OprPart]) -> Tuple[np.ndarray, Affine]:
    """Parts of one lattice as one array over all of them, the earlier (newer) part winning where two hold a value."""
    t0 = parts[0].transform
    offsets = [(round((p.transform.f - t0.f) / t0.e), round((p.transform.c - t0.c) / t0.a)) for p in parts]
    r1 = min(r for r, _ in offsets)
    c1 = min(c for _, c in offsets)
    r2 = max(r + p.values.shape[0] for (r, _), p in zip(offsets, parts))
    c2 = max(c + p.values.shape[1] for (_, c), p in zip(offsets, parts))
    joined = np.full((r2 - r1, c2 - c1), np.nan, dtype=np.float32)
    for (r, c), p in zip(offsets, parts):
        view = joined[r - r1:r - r1 + p.values.shape[0], c - c1:c - c1 + p.values.shape[1]]
        empty = np.isnan(view)
        view[empty] = p.values[empty]
    return joined, t0 @ Affine.translation(c1, r1)


def opr_scale(src_transform: Affine, src_crs, dst_transform: Affine) -> Dict[str, str]:
    """The warp options of a cubic OPR file: GDAL's XSCALE and YSCALE fixed at the file's own pixel over the block's,
    per axis, the file's pixel in its CRS's unit converted to metres (0.9144 for a 3 ft file onto 1 m). GDAL otherwise
    takes the kernel's scale from each chunk's source window, so a group covering part of a block (a survey's edge,
    one file alone) got another widening than the same pixels inside the survey: up to 3.7 cm apart on a 3 ft
    survey in Montana, the joined window 8.4 mm from the fixed ratio (fix round 1, S6). Stated, the widening the user
    kept on 2026-11-26 is the same in every block (the user's decision of 2026-11-27, "Fix it at the true ratio").
    A file turned against the zone takes the same ratio on both axes (no estimate per chunk): its kernel is as wide as
    an unturned file's of that pixel, where GDAL's own estimate from a turned window's box would widen it by up to
    cos + sin of the angle (an estimate from the box's geometry: about 2 % more at 1°, 16 % at 10°; its effect
    measured on a test terrain with a 25 m step: blocks 13.5 and 23.5 cm apart at 2 and 10 degrees,
    docs/resampling.md)."""
    unit = src_crs.linear_units_factor[1]
    return {"XSCALE": f"{abs(src_transform.a) * unit / abs(dst_transform.a):.12g}",
            "YSCALE": f"{abs(src_transform.e) * unit / abs(dst_transform.e):.12g}"}


def _opr_values(group: Sequence[_OprPart], crs: str, transform: Affine, shape: Tuple[int, int]) -> np.ndarray:
    """A group's values on the block: a copy as it is, else the joined parts warped once with the group's method
    (GDAL's defaults, one thread; within the block's own CRS, which _same_crs tells, without a change of datum, as
    _read_window resamples); cubic with the kernel's scale fixed (opr_scale), average with GDAL's own."""
    if group[0].method == "copy":
        return group[0].values
    band, band_transform = _join(group) if len(group) > 1 else (group[0].values, group[0].transform)
    out = np.full(shape, np.nan, dtype=np.float32)
    src_crs = group[0].crs
    scale = opr_scale(band_transform, src_crs, transform) if group[0].method == "cubic" else {}
    reproject(band, out, src_transform=band_transform, src_crs=src_crs, dst_transform=transform,
              dst_crs=src_crs if _same_crs(src_crs, crs) else crs, src_nodata=np.nan, dst_nodata=np.nan,
              resampling=getattr(Resampling, group[0].method), num_threads=1, **scale)
    return out


def compose_opr(files: Sequence[Tuple[str, str, int]], crs: str, transform: Affine, shape: Tuple[int, int],
                what: str, rule_of) -> Tuple[np.ndarray, Optional[Dict[str, str]]]:
    """A block of USGS's OPR DEMs composed from its files (name, url, survey year), newest first: each file by the
    method its own header's pixel takes (opr_method, always; rule_of(url): the survey's factor, the methods its
    sampled headers take, the survey: a file outside them is named once), its heights times its survey's factor after its nodata and floor; the files of one survey that share
    a lattice joined into one array before the one warp, so the kernel sees across the edge between two tiles; a
    group fills only the pixels still without data, and the next is read only while some remain. Returns the block
    and its tags (sources, years) or None when no file had data.

    The files are read as _read_block reads the 1 m DEM's (the same host, tiled files): GDAL's /vsicurl/ inside
    _gdal_http, opened by net.open_gdal, net.gdal_errors checked around the open and the read (Incomplete: asked
    again, GDAL's cache of the file dropped), windows by _read_masked (the directories scanned without the GIL),
    reproject from arrays with one thread; the caller holds a slot of the host (ComposedLayer). GDAL's cache of
    ranges serves the next block of the same file: 6-9 requests a block after the first on the mosaics of 21.8 and
    29.6 GB, against 14-16 with a file opened through ranges.open_remote for each block (gate B-1a)."""
    block = np.full(shape, np.nan, dtype=np.float32)
    used, years = [], []
    group: List[_OprPart] = []

    def apply(group) -> bool:
        values = _opr_values(group, crs, transform, shape)
        new = np.isnan(block) & np.isfinite(values)
        if new.any():
            block[new] = values[new]
            for part in group:
                if np.isfinite(part.values).any() and part.name not in used:
                    used.append(part.name)
                    years.append(str(part.year))
        return not np.isnan(block).any()
    with _gdal_http():
        for name, url, year in files:
            rule = rule_of(url)
            if rule is None:
                raise RuntimeError(f"{what}: {name} has no survey record read in this process (its index answer was "
                                   f"not read)")
            part = _opr_file_retried(url, crs, transform, shape, name, year, what, rule)
            if part is None:
                continue
            if group and not _same_lattice(group[-1], part):
                if apply(group):
                    group = []
                    break
                group = []
            group.append(part)
        if group:
            apply(group)
    return block, _finish(block, used, years, None, None)


class Windows(Reader):
    """Reads a BlockRequest: windows of its files composed newest first (_read_block); with geoid, files of
    heights above the ellipsoid saved as heights above that geoid (its grid made ready by the layer:
    FileBlocks). serial: the ranges of a block one after another through GDAL's cache of ranges, and
    download_layers hands the layer's blocks to its pool in squares, so a tile shared by neighbours is fetched
    once: fewer bytes, more requests; chosen per source where that was faster too (docs/performance.md,
    "Window reads": Austria, Luxembourg, British Columbia). force_crs: files that name only a local CRS
    (LOCAL_CS: Caribbean Netherlands' AHN files) are read in their block's CRS; a file with a real CRS is
    checked as ever. warp (a Resampling): a file in another real CRS is warped onto its block's pixels with it
    (_warp_window: Cyprus' tiles in EPSG:4258 onto blocks of Cyprus LTM; nearest for its DTM of about 1 m,
    average for its DSM of 0.5 m) instead of being refused (WrongCrs). ranged: every remote file is read through
    our own range requests (_read_ranged, the first bytes checked to be a TIFF's), never GDAL's /vsicurl/:
    Estonia's PHP download address, which GDAL does not open as a .tif and which answers its errors as HTTP 206
    with an HTML page. opr (the OPR layer's rule_of: a file's URL -> its survey's factor, sampled methods and survey): the
    rule of USGS's OPR DEMs (compose_opr) in place of all of this, for tnm.OprBlocks only."""
    rewrites = True  # the cached tile is written by _write_tile: reencode / cache migrate may convert it

    def __init__(self, description: str, geoid: Optional[Geoid] = None, serial: bool = False,
                 force_crs: bool = False, warp: Optional[Resampling] = None, ranged: bool = False, opr=None):
        self.description, self.geoid, self.serial, self.force_crs = description, geoid, serial, force_crs
        self.warp, self.ranged, self.opr = warp, ranged, opr

    def url(self, request: BlockRequest) -> Optional[str]:
        return request.files[0][1] if request.files else None

    def fetch(self, request: BlockRequest, path: str) -> Fetched:
        if self.opr is not None:
            block, tags = compose_opr(request.files, request.crs, request.transform, request.shape,
                                      self.description, self.opr)
            url = self.url(request)
            if tags is None:
                return Fetched(0, url)
            _write_tile(path, block, request.crs, request.transform, tags=tags)
            return Fetched(os.path.getsize(path), url)
        return _read_block(request.files, request.crs, request.transform, request.shape, path, self.description,
                           self.geoid, self.serial, self.force_crs, self.warp, self.ranged)

    def fetch_group(self, requests: Sequence[BlockRequest]) -> List[Tuple[Optional[np.ndarray], Optional[Dict]]]:
        """Several blocks of one CRS composed in memory, each file read once over them (read_group); with opr, each
        block as fetch composes it (compose_opr)."""
        if self.opr is not None:
            out = []
            for r in requests:
                block, tags = compose_opr(r.files, r.crs, r.transform, r.shape, self.description, self.opr)
                out.append((block, tags) if tags is not None else (None, None))
            return out
        return read_group(requests, self.description, self.geoid, self.force_crs, self.warp, self.ranged)
