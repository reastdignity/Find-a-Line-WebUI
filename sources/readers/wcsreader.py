"""WcsReader: a tile from an OGC WCS 2.0 (or 1.0) service (GetCoverage), clipped to the coverage where the service needs it."""

import math
import re
from collections import deque
from typing import List, Optional, Tuple

import numpy as np
import requests
from rasterio.io import MemoryFile
from scipy import ndimage
from rasterio.transform import from_origin
from rasterio.warp import Resampling, reproject

import cache
import servicecounts
import settings

from .. import net
from ..layer import Fetched, _clean, _write_tile
from ..composed import Reader

# The smallest piece of a tile asked again after an HTTP 5xx (split_on_error), in pixels a side: the Environment
# Agency's WCS answered 500 for a 2 km tile at Hay-on-Wye (322000/242000, on the Welsh border) and for its four
# 1000 px quarters, 200 with valid heights for 500 and 250 px pieces on its English side, and 500 for a 16 px box
# where 100 px answered 200 (measured 2026-11-08); below about 250 px the service misbehaves on its own
SPLIT_MIN_PX = 250


class WcsReader(Reader):
    """GetCoverage of a tile (res, i, j) of a WcsTiling (with the same tile_px and origin),
    saved on the tile's own pixels (resampled by nearest neighbour when the service answers
    on others).

    Some services (Malta) refuse a request that reaches beyond the coverage with a 404,
    which would make every tile at the edge of the data "missing" (the whole north
    coast of Gozo). Then the request is clipped to the coverage extent
    (DescribeCoverage), on whole pixels of the tile grid, and the rest of the tile
    stays without data.

    Others (the Environment Agency's) answer a request wholly outside the coverage with an
    error (HTTP 500), not a 404: when a request fails, the tile is missing if it does not
    reach into the coverage extent, and a box straddling the extent's edge is asked again
    clipped to it, as after a 404. Once the extent is known (asked after the first 404 or
    failure, once per reader), a tile wholly outside it is missing without a request.

    split_on_error: a box that still fails with an HTTP 5xx is asked again as a quadtree of
    smaller boxes down to SPLIT_MIN_PX pixels a side, composed on the tile's pixels; a piece
    failing at the floor stays without data (the fallback fills it), and a tile none of whose
    pieces answered is an error as before, never "missing". For the Environment Agency's WCS,
    whose 500 comes for any box not wholly covered by its granules, which follow England's
    outline (a tile of real land at the border lost whole otherwise; 2026-11-08).

    params: more parameters of every GetCoverage (GeoServer's GEOTIFF:COMPRESSION=DEFLATE
    makes South Tyrol's float32 tiles a quarter of their size).

    edge_px: pixels within this many (a 3 x 3 neighbourhood, edge_px times) of no data are
    dropped, so the fallback fills them (South Tyrol's pixels at the edge of the province
    are blended with zero). The tile is requested edge_px pixels larger on each side and cut
    back after the erosion, so a tile border inside the data is no edge: the same pixels as
    one request of the whole area.

    key_params: (query parameter, secret) pairs put into every request at request time, the
    secret a field of settings.ServiceKeys (Denmark: ("apikey", "datafordeler_api_key")); the
    reader's keys, so the layer is unavailable without them. The value is read when a request is
    made and never kept: errors and the cache's index name the request without it (cache.clean_url,
    cache.clean_error).

    version: "2.0.1" (SUBSET, SCALESIZE, COVERAGEID) or "1.0.0" (COVERAGE, CRS, BBOX on the pixel
    edges, WIDTH and HEIGHT; DescribeCoverage's gml:Envelope in the coverage's CRS; axes and
    interpolation of 2.0.1 do not apply: 1.0.0's axes are always x, y).
    """
    rewrites = True  # the cached tile is written by _write_tile: reencode / cache migrate may convert it

    def __init__(self, description: str, url: str, coverage: str, crs: str, native_res: float, tile_px: int,
                 fmt: str, axes: Tuple[str, str], interpolation: Optional[str], zero_is_nodata: bool,
                 origin: Tuple[float, float] = (0.0, 0.0), params: Tuple[Tuple[str, str], ...] = (),
                 edge_px: int = 0, key_params: Tuple[Tuple[str, str], ...] = (), version: str = "2.0.1",
                 split_on_error: bool = False):
        if version not in ("2.0.1", "1.0.0"):
            raise ValueError(f"WCS version {version} is not spoken (2.0.1 or 1.0.0)")
        self.description, self.service_url, self.coverage, self.crs = description, url, coverage, crs
        self.native_res, self.tile_px, self.fmt, self.axes = native_res, tile_px, fmt, axes
        self.interpolation, self.zero_is_nodata, self.origin = interpolation, zero_is_nodata, origin
        self.params, self.edge_px = tuple(params), edge_px
        self.key_params, self.version = tuple(key_params), version
        self.split_on_error = split_on_error
        self.keys = tuple(name for _, name in self.key_params)
        self._extent: Optional[tuple] = None  # (left, bottom, right, top) of the coverage; () if unknown

    def _keys(self) -> List[Tuple[str, str]]:
        """The key parameters with their values, read now; RuntimeError when one is not set."""
        missing = settings.missing_keys(self.keys)
        if missing:
            raise RuntimeError(f"{self.description} needs a key of its service, {missing}")
        return [(param, settings.service_key(name)) for param, name in self.key_params]

    def describe_params(self) -> List[Tuple[str, str]]:
        """The parameters of DescribeCoverage, the keys included (read now)."""
        if self.version == "1.0.0":
            params = [("SERVICE", "WCS"), ("VERSION", "1.0.0"), ("REQUEST", "DescribeCoverage"),
                      ("COVERAGE", self.coverage)]
        else:
            params = [("SERVICE", "WCS"), ("VERSION", "2.0.1"), ("REQUEST", "DescribeCoverage"),
                      ("COVERAGEID", self.coverage)]
        return params + self._keys()

    def coverage_extent(self) -> Optional[tuple]:
        """(left, bottom, right, top) of the coverage in the service CRS, or None if unknown."""
        if self._extent is None:
            try:
                net.rate_turn(self.service_url)  # a RuntimeError (no turn in time): the extent unknown
                response = servicecounts.get(self.service_url, timeout=60, headers=cache.http_headers(),
                                             params=self.describe_params())
                response.raise_for_status()
                self._extent = self._parse_extent(response.text)
            except (requests.RequestException, RuntimeError, AttributeError, ValueError, IndexError):
                self._extent = ()
        return self._extent or None

    def _parse_extent(self, text: str) -> tuple:
        if self.version == "1.0.0":
            # The spatial domain's envelope in the coverage's CRS (srsName "EPSG:25832", an URN or
            # an http URI ending in the code), easting and northing; the lonLatEnvelope is not it
            code = self.crs.split(":")[-1]
            for srs, body in re.findall(r'<gml:Envelope\w*\s[^>]*srsName="([^"]*)"[^>]*>(.*?)</gml:Envelope', text,
                                        re.S):
                if re.search(rf"(?<!\d){code}$", srs):
                    corners = [[float(v) for v in p.split()] for p in re.findall(r"<gml:pos>([^<]+)<", body)]
                    return corners[0][0], corners[0][1], corners[1][0], corners[1][1]
            raise ValueError("no envelope in the coverage's CRS")
        lower = [float(v) for v in re.search(r"<gml:lowerCorner>([^<]+)<", text).group(1).split()]
        upper = [float(v) for v in re.search(r"<gml:upperCorner>([^<]+)<", text).group(1).split()]
        labels = re.search(r'axisLabels="([^"]+)"', text)
        if labels and labels.group(1).split()[0] == self.axes[1]:  # northing first
            lower, upper = lower[::-1], upper[::-1]
        # To the millimetre: LGB's MapServer (Brandenburg) gives 248000.00001 / 5689999.99999997 -
        # 466000.00001003 / 5936000 for edges on whole metres, and a tile beyond such an edge (answered
        # HTTP 400) must not count as reaching into the coverage, nor a clip drop a whole pixel for 0.01 mm
        return tuple(round(v, 3) for v in (lower[0], lower[1], upper[0], upper[1]))

    def url(self, tile) -> Optional[str]:
        return self.service_url

    def coverage_params(self, left: float, bottom: float, right: float, top: float,
                        res: float) -> List[Tuple[str, str]]:
        """The parameters of the GetCoverage of a box at res, the keys included (read now)."""
        if self.version == "1.0.0":
            params = [("SERVICE", "WCS"), ("VERSION", "1.0.0"), ("REQUEST", "GetCoverage"),
                      ("COVERAGE", self.coverage), ("CRS", self.crs),
                      ("BBOX", f"{left:.3f},{bottom:.3f},{right:.3f},{top:.3f}"),
                      ("WIDTH", str(round((right - left) / res))), ("HEIGHT", str(round((top - bottom) / res))),
                      ("FORMAT", self.fmt)]
            return params + list(self.params) + self._keys()
        ax, ay = self.axes
        params = [("SERVICE", "WCS"), ("VERSION", "2.0.1"), ("REQUEST", "GetCoverage"),
                  ("COVERAGEID", self.coverage), ("FORMAT", self.fmt),
                  ("SUBSET", f"{ax}({left:.3f},{right:.3f})"),
                  ("SUBSET", f"{ay}({bottom:.3f},{top:.3f})")]
        if not math.isclose(res, self.native_res):
            params.append(("SCALESIZE", f"{ax}({round((right - left) / res)}),{ay}({round((top - bottom) / res)})"))
            if self.interpolation:
                params.append(("INTERPOLATION", self.interpolation))
        return params + list(self.params) + self._keys()

    def _request(self, left: float, bottom: float, right: float, top: float, res: float):
        """GetCoverage of a box; None if the service has no data there (404)."""
        return net._get(self.service_url, self.coverage_params(left, bottom, right, top, res))

    def fetch(self, tile, path: str) -> Fetched:
        res, i, j = tile
        size, px = self.tile_px * res, self.tile_px
        left, bottom = i * size + self.origin[0], j * size + self.origin[1]
        # The box requested: the tile, with edge_px pixels more on each side (none by default)
        e, margin = self.edge_px, self.edge_px * res
        req_left, req_bottom, req_size, req_px = left - margin, bottom - margin, size + 2 * margin, px + 2 * e
        box = (req_left, req_bottom, req_left + req_size, req_bottom + req_size)
        if self._extent and not _overlaps(box, self._extent):  # known to lie outside: nothing asked
            return Fetched(0, self.service_url)
        where = f"{self.description} tile {i}_{j}"
        try:
            got = self._fetch_box(box, res, (req_px, req_px), where)
        except RuntimeError as error:
            raise RuntimeError(f"Could not download {where}: {error}")
        if got is None:
            return Fetched(0, self.service_url)
        band, fetched = got
        band = _clean(band, self.zero_is_nodata)
        dst_transform = from_origin(req_left, req_bottom + req_size, res, res)
        if e:
            # Off within e pixels of no data; beyond the box counts as data (it is e pixels from
            # the tile, so the tile's pixels see only what was requested), then back to the tile
            keep = ndimage.binary_erosion(np.isfinite(band), structure=np.ones((3, 3), bool), iterations=e,
                                          border_value=1)
            band = np.where(keep, band, np.float32(np.nan))[e:e + px, e:e + px]
            dst_transform = from_origin(left, bottom + size, res, res)
        _write_tile(path, band, self.crs, dst_transform)
        return fetched

    def _fetch_box(self, box: tuple, res: float, shape: Tuple[int, int],
                   where: str) -> Optional[Tuple[np.ndarray, Fetched]]:
        """GetCoverage of a box on its own pixels (shape rows and columns): the band and what was
        received, or None where the service has no data (a 404, also of the part inside the coverage
        extent). After a failed request the box is missing when it lies outside the extent; a box
        straddling the extent's edge is asked again clipped to it (the part inside, on whole pixels), as
        after a 404; what still fails with an HTTP 5xx is asked in pieces with split_on_error (_pieces),
        and raises otherwise."""
        failed = None
        try:
            response = self._request(*box, res)
        except RuntimeError as e:
            failed = e
            response = None
        if response is not None:
            return self._band(response, box, res, shape), Fetched.of(response)
        extent = self.coverage_extent()
        if failed is not None and extent and not _overlaps(box, extent):
            return None
        inner = _inner(box, extent, res) if extent else None
        if inner is not None and inner != box:
            try:
                response = self._request(*inner, res)
            except RuntimeError as e:
                if not self._splits(e):
                    raise
                return self._pieces(inner, box, res, shape, where, e)
            if response is None:
                return None
            return self._band(response, box, res, shape), Fetched.of(response)
        if failed is None:
            return None
        if not self._splits(failed):
            raise failed
        return self._pieces(box, box, res, shape, where, failed)

    def _splits(self, error: RuntimeError) -> bool:
        """Whether a failed request is asked again in pieces: split_on_error and the service's own error (an
        HTTP 5xx after net._get's retries), never a connection or rate failure."""
        return self.split_on_error and re.match(r"HTTP 5\d\d", str(error)) is not None

    def _pieces(self, box: tuple, frame: tuple, res: float, shape: Tuple[int, int], where: str,
                error: RuntimeError) -> Tuple[np.ndarray, Fetched]:
        """GetCoverage of a box that failed with an HTTP 5xx as a quadtree of smaller boxes, composed on the
        pixels of frame (shape): a piece failing so is halved along each side whose half has SPLIT_MIN_PX
        pixels or more, one failing at the floor stays without data, any other error raises. The band and
        the bytes received; RuntimeError when no piece answered (the service's error, as for one request).
        One line printed per tile: the pieces asked and those that failed."""
        band = np.full(shape, np.nan, dtype=np.float32)
        col, row = round((box[0] - frame[0]) / res), round((frame[3] - box[3]) / res)
        todo = deque(_halves(col, row, round((box[2] - box[0]) / res), round((box[3] - box[1]) / res)))
        if not todo:  # too small to split: the error as for one request
            raise error
        answered = failed = received = 0
        while todo:
            c, r, w, h = todo.popleft()
            piece = (frame[0] + c * res, frame[3] - (r + h) * res, frame[0] + (c + w) * res, frame[3] - r * res)
            try:
                response = self._request(*piece, res)
            except RuntimeError as e:
                if not self._splits(e):
                    raise
                error = e
                smaller = _halves(c, r, w, h)
                if smaller:
                    todo.extend(smaller)
                else:
                    failed += 1
                continue
            answered += 1
            if response is None:  # no data in the piece
                continue
            received += len(response.content)
            band[r:r + h, c:c + w] = self._band(response, piece, res, (h, w))
        if not answered:
            raise RuntimeError(f"its {failed} pieces of {SPLIT_MIN_PX} px and more failed too: {error}")
        print(f"{where}: asked in {answered + failed} pieces down to {SPLIT_MIN_PX} px, {failed} failed "
              f"(the service's error) and left without data")
        return band, Fetched(received, self.service_url)

    def _band(self, response, box: tuple, res: float, shape: Tuple[int, int]) -> np.ndarray:
        """The coverage of a response on the pixels of box (shape rows and columns at res): as served when
        the service answered on them, resampled by nearest neighbour otherwise (an answer on the service's
        own pixels, or of the part inside the coverage)."""
        data = response.content
        content_type = response.headers.get("content-type", "")
        if "multipart" in content_type:
            data = _extract_multipart(data, content_type)

        ext = ".asc" if "aaigrid" in self.fmt else ".tif"
        with MemoryFile(data, ext=ext) as memfile, memfile.open() as src:
            band = src.read(1, masked=True).astype(np.float32).filled(np.nan)
            src_crs = src.crs or self.crs  # ASCII grids come without a CRS
            src_transform = src.transform
        dst_transform = from_origin(box[0], box[3], res, res)
        if band.shape != shape or not src_transform.almost_equals(dst_transform):
            resampled = np.full(shape, np.nan, dtype=np.float32)
            reproject(band, resampled, src_transform=src_transform, src_crs=src_crs,
                      dst_transform=dst_transform, dst_crs=self.crs,
                      src_nodata=np.nan, dst_nodata=np.nan, resampling=Resampling.nearest)
            band = resampled
        return band


def _halves(c: int, r: int, w: int, h: int) -> List[Tuple[int, int, int, int]]:
    """A piece (column, row, width, height in pixels) halved along each side whose half has SPLIT_MIN_PX pixels
    or more: its 4 or 2 pieces, or none when neither side can be halved."""
    halves = [n // 2 if n // 2 >= SPLIT_MIN_PX else 0 for n in (w, h)]
    if not any(halves):
        return []
    cols = [(c, halves[0]), (c + halves[0], w - halves[0])] if halves[0] else [(c, w)]
    rows = [(r, halves[1]), (r + halves[1], h - halves[1])] if halves[1] else [(r, h)]
    return [(cc, rr, ww, hh) for rr, hh in rows for cc, ww in cols]


def _inner(box: tuple, extent: tuple, res: float) -> Optional[tuple]:
    """The part of a box inside the coverage extent, on whole pixels of the box's grid; None when empty."""
    inner = (box[0] + math.ceil(max(0.0, extent[0] - box[0]) / res) * res,
             box[1] + math.ceil(max(0.0, extent[1] - box[1]) / res) * res,
             box[2] - math.ceil(max(0.0, box[2] - extent[2]) / res) * res,
             box[3] - math.ceil(max(0.0, box[3] - extent[3]) / res) * res)
    return inner if inner[0] < inner[2] and inner[1] < inner[3] else None


def _overlaps(box: tuple, extent: tuple) -> bool:
    """Whether two boxes (left, bottom, right, top) share more than an edge."""
    return box[0] < extent[2] and extent[0] < box[2] and box[1] < extent[3] and extent[1] < box[3]


def _extract_multipart(content: bytes, content_type: str) -> bytes:
    """Pull the coverage out of a multipart/related WCS response.

    Part headers end with an empty line of CRLF or of a bare LF (Saxony-Anhalt's ArcGIS
    server); a part's body ends with exactly one line break of the same kind before the next
    boundary, so only that is removed (an uncompressed TIFF may end in the bytes 0x0A or 0x0D).
    """
    boundary = re.search(r'boundary="?([^";]+)"?', content_type).group(1).encode()
    for part in content.split(b"--" + boundary):
        blank = re.search(rb"\r?\n\r?\n", part)
        if not blank:
            continue
        head, body = part[:blank.start()], part[blank.end():]
        kind = re.search(rb"Content-Type:\s*([^\r\n;]+)", head, re.I)
        # The coverage itself (image/tiff, image/x-aaigrid, application/asc...), not its XML description
        if kind and not re.search(rb"xml|gml|text/", kind.group(1), re.I):
            eol = b"\r\n" if blank.group().startswith(b"\r") else b"\n"
            return body[:-len(eol)] if body.endswith(eol) else body
    raise RuntimeError("WCS response did not contain coverage data")
