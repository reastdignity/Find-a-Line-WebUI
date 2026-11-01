"""WcsReader: a tile from an OGC WCS 2.0 service (GetCoverage), clipped to the coverage where the service needs it."""

import math
import re
from typing import Optional, Tuple

import numpy as np
import requests
from rasterio.io import MemoryFile
from rasterio.transform import from_origin
from rasterio.warp import Resampling, reproject

import cache
import servicecounts

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
    """

    def __init__(self, description: str, url: str, coverage: str, crs: str, native_res: float, tile_px: int,
                 fmt: str, axes: Tuple[str, str], interpolation: Optional[str], zero_is_nodata: bool,
                 origin: Tuple[float, float] = (0.0, 0.0)):
        self.description, self.service_url, self.coverage, self.crs = description, url, coverage, crs
        self.native_res, self.tile_px, self.fmt, self.axes = native_res, tile_px, fmt, axes
        self.interpolation, self.zero_is_nodata, self.origin = interpolation, zero_is_nodata, origin
        self._extent: Optional[tuple] = None  # (left, bottom, right, top) of the coverage; () if unknown

    def coverage_extent(self) -> Optional[tuple]:
        """(left, bottom, right, top) of the coverage in the service CRS, or None if unknown."""
        if self._extent is None:
            try:
                response = servicecounts.get(self.service_url, timeout=60, headers=cache.http_headers(), params={
                    "SERVICE": "WCS", "VERSION": "2.0.1", "REQUEST": "DescribeCoverage", "COVERAGEID": self.coverage})
                response.raise_for_status()
                text = response.text
                lower = [float(v) for v in re.search(r"<gml:lowerCorner>([^<]+)<", text).group(1).split()]
                upper = [float(v) for v in re.search(r"<gml:upperCorner>([^<]+)<", text).group(1).split()]
                labels = re.search(r'axisLabels="([^"]+)"', text)
                if labels and labels.group(1).split()[0] == self.axes[1]:  # northing first
                    lower, upper = lower[::-1], upper[::-1]
                self._extent = (lower[0], lower[1], upper[0], upper[1])
            except (requests.RequestException, AttributeError, ValueError, IndexError):
                self._extent = ()
        return self._extent or None

    def url(self, tile) -> Optional[str]:
        return self.service_url

    def _request(self, left: float, bottom: float, right: float, top: float, res: float):
        """GetCoverage of a box; None if the service has no data there (404)."""
        ax, ay = self.axes
        params = [("SERVICE", "WCS"), ("VERSION", "2.0.1"), ("REQUEST", "GetCoverage"),
                  ("COVERAGEID", self.coverage), ("FORMAT", self.fmt),
                  ("SUBSET", f"{ax}({left:.3f},{right:.3f})"),
                  ("SUBSET", f"{ay}({bottom:.3f},{top:.3f})")]
        if not math.isclose(res, self.native_res):
            params.append(("SCALESIZE", f"{ax}({round((right - left) / res)}),{ay}({round((top - bottom) / res)})"))
            if self.interpolation:
                params.append(("INTERPOLATION", self.interpolation))
        return net._get(self.service_url, params)

    def fetch(self, tile, path: str) -> Fetched:
        res, i, j = tile
        size, px = self.tile_px * res, self.tile_px
        left, bottom = i * size + self.origin[0], j * size + self.origin[1]
        try:
            response = self._request(left, bottom, left + size, bottom + size, res)
            extent = self.coverage_extent() if response is None else None
            if extent:
                # Inside the coverage, on whole pixels of the tile
                inner = (left + math.ceil(max(0.0, extent[0] - left) / res) * res,
                         bottom + math.ceil(max(0.0, extent[1] - bottom) / res) * res,
                         left + size - math.ceil(max(0.0, left + size - extent[2]) / res) * res,
                         bottom + size - math.ceil(max(0.0, bottom + size - extent[3]) / res) * res)
                if inner[0] < inner[2] and inner[1] < inner[3] and inner != (left, bottom, left + size, bottom + size):
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
        dst_transform = from_origin(left, bottom + size, res, res)
        if band.shape != (px, px) or not src_transform.almost_equals(dst_transform):
            resampled = np.full((px, px), np.nan, dtype=np.float32)
            reproject(band, resampled, src_transform=src_transform, src_crs=src_crs,
                      dst_transform=dst_transform, dst_crs=self.crs,
                      src_nodata=np.nan, dst_nodata=np.nan, resampling=Resampling.nearest)
            band = resampled
        _write_tile(path, _clean(band, self.zero_is_nodata), self.crs, dst_transform)
        return Fetched.of(response)


def _extract_multipart(content: bytes, content_type: str) -> bytes:
    """Pull the coverage out of a multipart/related WCS response."""
    boundary = re.search(r'boundary="?([^";]+)"?', content_type).group(1).encode()
    for part in content.split(b"--" + boundary):
        head, _, body = part.partition(b"\r\n\r\n")
        kind = re.search(rb"Content-Type:\s*([^\r\n;]+)", head, re.I)
        # The coverage itself (image/tiff, image/x-aaigrid, application/asc...), not its XML description
        if kind and not re.search(rb"xml|gml|text/", kind.group(1), re.I):
            return body.rstrip(b"\r\n")
    raise RuntimeError("WCS response did not contain coverage data")
