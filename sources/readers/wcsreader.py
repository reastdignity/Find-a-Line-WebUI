"""WcsReader: a tile from an OGC WCS 2.0 (or 1.0) service (GetCoverage), clipped to the coverage where the service needs it."""

import math
import re
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
    reach into the coverage extent. Once the extent is known (asked after the first 404 or
    failure, once per reader), a tile wholly outside it is missing without a request.

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

    def __init__(self, description: str, url: str, coverage: str, crs: str, native_res: float, tile_px: int,
                 fmt: str, axes: Tuple[str, str], interpolation: Optional[str], zero_is_nodata: bool,
                 origin: Tuple[float, float] = (0.0, 0.0), params: Tuple[Tuple[str, str], ...] = (),
                 edge_px: int = 0, key_params: Tuple[Tuple[str, str], ...] = (), version: str = "2.0.1"):
        if version not in ("2.0.1", "1.0.0"):
            raise ValueError(f"WCS version {version} is not spoken (2.0.1 or 1.0.0)")
        self.description, self.service_url, self.coverage, self.crs = description, url, coverage, crs
        self.native_res, self.tile_px, self.fmt, self.axes = native_res, tile_px, fmt, axes
        self.interpolation, self.zero_is_nodata, self.origin = interpolation, zero_is_nodata, origin
        self.params, self.edge_px = tuple(params), edge_px
        self.key_params, self.version = tuple(key_params), version
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
        return lower[0], lower[1], upper[0], upper[1]

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
        try:
            try:
                response = self._request(*box, res)
            except RuntimeError:
                extent = self.coverage_extent()
                if extent and not _overlaps(box, extent):
                    return Fetched(0, self.service_url)
                raise
            extent = self.coverage_extent() if response is None else None
            if extent:
                # Inside the coverage, on whole pixels of the tile
                inner = (box[0] + math.ceil(max(0.0, extent[0] - box[0]) / res) * res,
                         box[1] + math.ceil(max(0.0, extent[1] - box[1]) / res) * res,
                         box[2] - math.ceil(max(0.0, box[2] - extent[2]) / res) * res,
                         box[3] - math.ceil(max(0.0, box[3] - extent[3]) / res) * res)
                if inner[0] < inner[2] and inner[1] < inner[3] and inner != box:
                    response = self._request(*inner, res)
        except RuntimeError as e:
            raise RuntimeError(f"Could not download {self.description} tile {i}_{j}: {e}")
        if response is None:
            return Fetched(0, self.service_url)
        data = response.content
        content_type = response.headers.get("content-type", "")
        if "multipart" in content_type:
            data = _extract_multipart(data, content_type)

        ext = ".asc" if "aaigrid" in self.fmt else ".tif"
        with MemoryFile(data, ext=ext) as memfile, memfile.open() as src:
            band = src.read(1, masked=True).astype(np.float32).filled(np.nan)
            src_crs = src.crs or self.crs  # ASCII grids come without a CRS
            src_transform = src.transform
        dst_transform = from_origin(req_left, req_bottom + req_size, res, res)
        if band.shape != (req_px, req_px) or not src_transform.almost_equals(dst_transform):
            resampled = np.full((req_px, req_px), np.nan, dtype=np.float32)
            reproject(band, resampled, src_transform=src_transform, src_crs=src_crs,
                      dst_transform=dst_transform, dst_crs=self.crs,
                      src_nodata=np.nan, dst_nodata=np.nan, resampling=Resampling.nearest)
            band = resampled
        band = _clean(band, self.zero_is_nodata)
        if e:
            # Off within e pixels of no data; beyond the box counts as data (it is e pixels from
            # the tile, so the tile's pixels see only what was requested), then back to the tile
            keep = ndimage.binary_erosion(np.isfinite(band), structure=np.ones((3, 3), bool), iterations=e,
                                          border_value=1)
            band = np.where(keep, band, np.float32(np.nan))[e:e + px, e:e + px]
            dst_transform = from_origin(left, bottom + size, res, res)
        _write_tile(path, band, self.crs, dst_transform)
        return Fetched.of(response)


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
