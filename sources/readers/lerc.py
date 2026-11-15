"""LercTileReader: one tile of an Esri elevation tile cache (an ArcGIS ImageServer of cacheType "Elevation",
`<service>/tile/{level}/{row}/{col}` in Web Mercator), answered as `image/lerc`: a LERC1 blob ("CntZImage") of
257 x 257 float samples on the corners of the tile's 256 x 256 cells, decoded by GDAL's MRF driver.

What the two services of 2026-11-15 answered (DAERA's 2021 NI coastal DTM and IPP's 5 m DTM of Rio de Janeiro),
which this module relies on:
- The tiling is the standard Web Mercator one of ArcGIS Online (tileInfo: 256 x 256, origin -20037508.342787,
  20037508.342787, the LOD resolutions 156543.033928 / 2^level), so a tile spans 256 resolutions and its 257
  samples sit at its corners and at every resolution between them: the last column of samples is the east tile's
  first (equal within the LERC tolerance: 0.04 m on average against 2.1 m for the next column, on Pão de Açúcar's
  slope), the last row the south tile's first. A sample is a pixel centre: the tile's pixel grid starts half a
  resolution west and north of its corner, and the shared last row and column are dropped, so the cached tiles
  meet edge to edge (256 x 256 px, nothing resampled here; the mosaic resamples once onto the working grid).
- The LERC1 blob carries a validity mask: the sea and everything outside the survey are invalid samples (a tile
  without any valid sample is a 70-byte blob). GDAL gives invalid samples the value 0.0 unless the open option NDV
  names another, so the blob is decoded with NDV = NO_DATA and those become NaN; valid samples of 0.0 m exist (a
  dozen at Rio's shore in one tile) and stay heights. Without DATATYPE=Float32 the MRF driver reads the blob as
  bytes (wrong values).
- A tile beyond the service's cache (outside its extent, a level above its finest) answers 404 (an HTML page):
  missing, as a tile without any valid sample.
"""

import re
import struct
from typing import Optional, Tuple

import numpy as np
import requests
from rasterio.io import MemoryFile
from rasterio.transform import Affine

import cache
import servicecounts

from .. import net
from ..layer import Fetched, _clean, _write_tile
from ..composed import Reader

LERC1_MAGIC = b"CntZImage "  # the first bytes of a LERC1 blob (Esri's CntZImage), then version, type, height, width
SAMPLES = 257                # samples a side of a tile: its 256 cells' corners
CELLS = SAMPLES - 1
NO_DATA = -9999.0            # what GDAL writes into the invalid samples (MRF's open option NDV), then NaN
# Web Mercator (EPSG:3857) as ArcGIS Online's tile caches use it: the origin of the tiles (the north-west corner of
# the world) and the resolution of level 0 (tileInfo of both services)
MERCATOR = "EPSG:3857"
ORIGIN = 20037508.342787
LEVEL0_RES = 2 * ORIGIN / CELLS
# The largest answer read for one tile: 257 x 257 float32 samples are 264 kB uncompressed (the largest of the
# tiles read in 2026-11 was 60 kB), so anything near this is not a tile; the read stops there
TILE_BYTES_MAX = 1_000_000
TILE_TIMEOUT = 120  # seconds


def resolution(level: int) -> float:
    """Metres of Web Mercator between two samples (a cell) at a level."""
    return LEVEL0_RES / 2 ** level


def tile_transform(level: int, row: int, col: int) -> Affine:
    """The pixel grid of a tile in EPSG:3857: its samples are the pixel centres, so the grid starts half a cell
    west and north of the tile's corner."""
    res = resolution(level)
    return Affine(res, 0.0, -ORIGIN + col * CELLS * res - res / 2, 0.0, -res, ORIGIN - row * CELLS * res + res / 2)


def tile_url(service: str, level: int, row: int, col: int) -> str:
    return f"{service.rstrip('/')}/tile/{level}/{row}/{col}"


def lerc1_shape(data: bytes) -> Tuple[int, int]:
    """(height, width) from a LERC1 blob's header; ValueError when it is not one (its magic, a header cut short)."""
    if not data.startswith(LERC1_MAGIC) or len(data) < len(LERC1_MAGIC) + 16:
        raise ValueError(f"not a LERC1 tile (it starts with {data[:12]!r})")
    _, _, height, width = struct.unpack_from("<4i", data, len(LERC1_MAGIC))
    return height, width


def decode(data: bytes) -> np.ndarray:
    """The samples of a LERC1 tile as float32, NaN where the blob's mask marks them invalid. ValueError when the
    blob is not a LERC1 tile of SAMPLES x SAMPLES or GDAL cannot decode it whole (a blob cut short)."""
    height, width = lerc1_shape(data)
    if (height, width) != (SAMPLES, SAMPLES):
        raise ValueError(f"a LERC1 tile of {width} x {height} samples, {SAMPLES} x {SAMPLES} expected")
    with net.gdal_errors() as errors:
        try:
            with MemoryFile(data) as memfile, memfile.open(DATATYPE="Float32", NDV=f"{NO_DATA:g}") as src:
                band = src.read(1)
        except Exception as e:  # rasterio's errors of a broken blob
            raise ValueError(f"LERC1 tile not decoded: {e}") from None
    if errors:
        raise ValueError(f"LERC1 tile not decoded: {errors[0]}")
    if band.shape != (SAMPLES, SAMPLES):
        raise ValueError(f"LERC1 tile decoded as {band.shape}")
    band = band.astype(np.float32, copy=False)
    band[band == NO_DATA] = np.nan
    return band


class LercTileReader(Reader):
    """One tile (level, row, col) of an Esri elevation tile cache at `service` (the ImageServer's address), one
    GET without a Range: at most TILE_BYTES_MAX read (streamed, given up beyond it); the answer must start with
    the LERC1 magic, and an answer cut short (fewer bytes than its Content-Length, a blob GDAL cannot decode) is
    asked again (net.RETRIES, net._sleep), then an error. A 404 or a tile without a valid sample is missing (no
    file). Samples below `floor` are no data too (Rio's tiles hold artefacts down to -348 m at the sea), as are
    those below VALID_MIN (layer._clean). The tile is written in EPSG:3857 on its own samples, 256 x 256 px
    (tile_transform: the shared last row and column dropped)."""
    rewrites = True  # the cached tile is written by _write_tile: reencode / cache migrate may convert it

    def __init__(self, description: str, service: str, floor: Optional[float] = None):
        self.description, self.service, self.floor = description, service.rstrip("/"), floor

    def url(self, request) -> Optional[str]:
        return tile_url(self.service, *request)

    def _get(self, url: str):
        """(body, response) of one attempt; (None, response) for a 404. Raises RuntimeError or requests' errors."""
        net.rate_turn(url)
        with servicecounts.request(url) as counted, \
                net.session().get(url, timeout=TILE_TIMEOUT, headers=cache.http_headers(), verify=net.verify(url),
                                  stream=True) as response:
            counted.got(response, read=False)
            if response.status_code == 404:
                return None, response
            if response.status_code != 200:
                text = " ".join(response.raw.read(300, decode_content=True).decode("utf-8", "replace").split())
                if response.status_code in (429, 503):
                    raise _SlowDown(f"HTTP {response.status_code}: {text[:200]}")
                raise RuntimeError(f"HTTP {response.status_code}: {text[:200]}")
            body = bytearray()
            for chunk in response.iter_content(65536):
                counted.add(len(chunk))
                body += chunk
                if len(body) > TILE_BYTES_MAX:
                    counted.outcome = "other"
                    raise RuntimeError(f"more than {TILE_BYTES_MAX} bytes: not a tile")
            length = response.headers.get("content-length")
            if length and re.fullmatch(r"\d+", length) and int(length) != len(body) \
                    and "content-encoding" not in response.headers:
                counted.outcome = "connection"
                raise RuntimeError(f"the answer was cut short ({len(body)} of {length} bytes)")
            if not body.startswith(LERC1_MAGIC):
                counted.outcome = "other"
                kind = response.headers.get("content-type", "")
                raise RuntimeError(f"not a LERC1 tile ({kind or 'no content type'}: {bytes(body[:60])!r})")
            return bytes(body), response

    def fetch(self, request, path: str) -> Fetched:
        level, row, col = request
        url = self.url(request)
        where = f"{self.description} tile {level}/{row}/{col}"
        last = None
        for attempt in range(net.RETRIES):
            slow_down = False
            try:
                body, response = self._get(url)
                if body is None:  # beyond the cache: missing
                    return Fetched(0, url)
                samples = decode(body)
                break
            except (requests.RequestException, RuntimeError, ValueError) as e:
                last, slow_down = e, isinstance(e, _SlowDown)
            net._sleep(attempt + 3 if slow_down else attempt)
        else:
            raise RuntimeError(f"Could not download {where}: {cache.clean_error(last)}")
        band = _clean(samples[:CELLS, :CELLS])  # the shared last row and column are the neighbours' first
        if self.floor is not None:
            band[band < self.floor] = np.nan
        if not np.isfinite(band).any():  # no survey here (the sea, inland): missing
            return Fetched(0, url)
        _write_tile(path, band, MERCATOR, tile_transform(level, row, col))
        return Fetched(len(body), url, response.headers.get("ETag"), response.headers.get("Last-Modified"))


class _SlowDown(RuntimeError):
    """The service asked us to slow down (HTTP 429 or 503): the next attempt waits longer."""
