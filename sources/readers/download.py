"""Download: a tile that is a whole file at a URL, saved as it comes (checked against its sha256 if known), or
written again: in another CRS's name, or averaged to coarser pixels."""

import hashlib
import os
from typing import Callable, Optional, Sequence

import numpy as np
from affine import Affine
import rasterio as rio
from rasterio.windows import Window

from .. import net
from ..net import RETRIES, _part
from ..layer import Fetched, VALID_MIN, _write_tile, copied_tags, float_band
from ..composed import Reader

# The rows of the coarser pixels averaged at a time (average): a band of factor * AVERAGE_ROWS rows of the
# file is read, so a 5000 x 5000 float32 file is never held whole as an array (about 30 MB at its peak for
# LDBV's DOM20, eight tiles of a download at once)
AVERAGE_ROWS = 50


class Download(Reader):
    """One GET per tile (net._get, with its retries), the answer saved as the tile; a tile the
    service does not have (404) is missing. With sha256 (of a tile: the digest its index
    gives, or None), a file that does not match is asked again (RETRIES times, with backoff)
    and never kept.

    With average (an integer factor above 1) the file (a single-band raster) is not kept as it
    comes: each square of average x average of its own pixels becomes one pixel, the mean of its
    valid values (no data where none is valid; nodata and values below VALID_MIN are not valid),
    written as a float32 GeoTIFF (NaN for no data) at average times the file's pixel size: LDBV's
    DOM20 of 0.2 m, 49 MB a km², cached at 1 m. A file whose width or height is not a multiple of
    average is an error. With crs, the file is written in that CRS's name whatever it names (a
    compound CRS with heights: LVermGeo RP's DGM1), its values as they are (float32, NaN for no
    data). The checksum is that of the file downloaded; the file is read again from a temporary
    file next to the tile (its .part), not from memory.

    A file that is a float raster of one band is written again as the cache's other tiles are (the
    _write_tile profile; its overviews dropped, its nodata and values below VALID_MIN as NaN, its CRS,
    transform and tags kept), after the checksum was checked on the bytes downloaded.

    url_of gives a tile's URL; label names it in messages ("tile 50,19")."""
    # A float raster of one band is written again by _write_tile whatever its file was (the cached file is no
    # longer the provider's byte for byte); an integer raster (NASADEM, the water mask), a raster of several bands
    # and anything that is not a raster are kept as they came. So reencode / cache migrate may convert a file of
    # this layer, and old_encoding tells which.
    rewrites = True

    def __init__(self, description: str, url_of: Callable[[object], str], label: Callable[[object], str],
                 binary_types: Optional[Sequence[str]] = None,
                 sha256: Optional[Callable[[object], Optional[str]]] = None,
                 average: int = 1, crs: Optional[str] = None):
        if not isinstance(average, int) or average < 1:
            raise ValueError(f"average must be a positive integer, not {average!r}")
        self.description, self.url_of, self.label = description, url_of, label
        self.binary_types, self.sha256 = binary_types, sha256
        self.average, self.crs = average, crs

    def url(self, tile) -> Optional[str]:
        return self.url_of(tile)

    def fetch(self, tile, path: str) -> Fetched:
        url = self.url_of(tile)
        expected = self.sha256(tile) if self.sha256 else None
        for attempt in range(RETRIES):
            try:
                response = net._get(url) if self.binary_types is None else \
                    net._get(url, binary_types=tuple(self.binary_types))
            except RuntimeError as e:
                raise RuntimeError(f"Could not download {self.description} {self.label(tile)}: {e}")
            if response is None:  # no tile there (sea)
                return Fetched(0, url)
            if not expected or hashlib.sha256(response.content).hexdigest() == expected:
                break
            net._sleep(attempt)
        else:
            raise RuntimeError(f"{self.description} {self.label(tile)}: wrong checksum")
        fetched = Fetched.of(response, url)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = _part(path + ".raw")  # _write_tile writes the tile through _part(path)
        with open(tmp, "wb") as f:
            f.write(response.content)
        if self.average > 1 or self.crs or _is_float_raster(tmp):
            del response  # the answer (49 MB of a DOM20 file) is not held while it is read again
            try:
                self._rewrite(tmp, path, f"{self.description} {self.label(tile)}")
            finally:
                os.remove(tmp)
            return fetched
        os.replace(tmp, path)  # an integer raster or anything else: as it came
        return fetched

    def _rewrite(self, raw: str, path: str, where: str):
        """The downloaded raster (the file raw) written again to path (averaged and in self.crs's name)."""
        f = self.average
        with rio.open(raw) as src:
            if src.count != 1:
                raise RuntimeError(f"{where}: {src.count} bands, one expected")
            if src.width % f or src.height % f:
                raise RuntimeError(f"{where}: {src.width} x {src.height} px cannot be averaged {f} x {f}")
            crs = self.crs or src.crs
            if f == 1:
                _write_tile(path, float_band(src), crs, src.transform, tags=copied_tags(src))
                return
            band = np.empty((src.height // f, src.width // f), dtype=np.float32)
            for row in range(0, band.shape[0], AVERAGE_ROWS):
                rows = min(AVERAGE_ROWS, band.shape[0] - row)
                part = src.read(1, masked=True, window=Window(0, row * f, src.width, rows * f))
                values = part.astype(np.float64).filled(np.nan)
                values[values < VALID_MIN] = np.nan
                band[row:row + rows] = _block_means(values, f)
            _write_tile(path, band, crs, src.transform @ Affine.scale(f))


def _is_float_raster(path: str) -> bool:
    """Whether a downloaded file is a raster of one band of floats (not an integer raster, a raster of several
    bands or something else: Download keeps those as they came)."""
    try:
        with rio.open(path) as src:
            return src.count == 1 and bool(np.issubdtype(np.dtype(src.dtypes[0]), np.floating))
    except Exception:
        return False


def _block_means(values: np.ndarray, f: int) -> np.ndarray:
    """The mean of the finite values of each f x f block (NaN where none is finite)."""
    blocks = values.reshape(values.shape[0] // f, f, values.shape[1] // f, f)
    valid = np.isfinite(blocks)
    count = valid.sum(axis=(1, 3))
    total = np.where(valid, blocks, 0.0).sum(axis=(1, 3))
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(count > 0, total / count, np.nan)
