"""WcsTiles: square tiles from an OGC WCS 2.0 service on a fixed grid in the service's CRS."""

import math
import os
import re
from typing import Optional, Tuple

import numpy as np
import requests
from rasterio.io import MemoryFile
from rasterio.transform import from_origin
from rasterio.warp import Resampling, reproject, transform_bounds

import cache
from grid import Grid

from .. import net
from ..layer import Fetched, Layer, _clean, _write_tile


class WcsTiles(Layer):
    """Square tiles from a WCS 2.0 service, on a fixed grid in the service CRS.

    fetch_res=None requests tiles at the working resolution (the server
    downsamples); a number requests tiles at that resolution, cached independently
    of the working resolution and downsampled locally.

    Some services (Malta) refuse a request that reaches beyond the coverage with a 404,
    which would make every tile at the edge of the data "missing" (the whole north
    coast of Gozo). Then the request is clipped to the coverage extent
    (DescribeCoverage), on whole pixels of the tile grid, and the rest of the tile
    stays without data.
    """

    def __init__(self, description: str, url: str, coverage: str, crs: str, folder: str,
                 native_res: float, tile_px: int = 2000, fmt: str = "image/tiff",
                 axes: Tuple[str, str] = ("x", "y"), fetch_res: Optional[float] = None,
                 interpolation: Optional[str] = None, zero_is_nodata: bool = False,
                 bytes_per_px: float = 4, shift: Tuple[float, float] = (0.0, 0.0)):
        self.description, self.url, self.coverage, self.crs = description, url, coverage, crs
        self.folder, self.native_res, self.tile_px, self.fmt = folder, native_res, tile_px, fmt
        self.axes, self.fetch_res, self.interpolation = axes, fetch_res, interpolation
        self.zero_is_nodata, self.bytes_per_px, self.shift = zero_is_nodata, bytes_per_px, shift
        self._res = None
        self._extent: Optional[tuple] = None  # (left, bottom, right, top) of the coverage; () if unknown

    def _tile_res(self, grid: Grid) -> float:
        return self.fetch_res or grid.res

    def tiles(self, grid: Grid):
        self._res = res = self._tile_res(grid)
        size = self.tile_px * res
        left, bottom, right, top = transform_bounds(grid.crs, self.crs, *grid.bounds)
        # Tiles hold the data where the service puts it, i.e. before the shift correction
        cx, cy, radius = (left + right) / 2 - self.shift[0], (bottom + top) / 2 - self.shift[1], (right - left) / 2
        shape = None
        if grid.area_shape is not None:
            from area import project
            from shapely.affinity import translate
            shape = translate(project(grid.area_shape, grid.crs, self.crs), -self.shift[0], -self.shift[1])
        tiles = []
        for i in range(math.floor((cx - radius) / size), math.floor((cx + radius) / size) + 1):
            for j in range(math.floor((cy - radius) / size), math.floor((cy + radius) / size) + 1):
                if shape is not None:  # any area: the tiles under its outline
                    from shapely.geometry import box
                    if shape.intersects(box(i * size, j * size, (i + 1) * size, (j + 1) * size)):
                        tiles.append((res, i, j))
                    continue
                dx = max(i * size - cx, 0, cx - (i + 1) * size)  # nearest point of the tile
                dy = max(j * size - cy, 0, cy - (j + 1) * size)
                if dx * dx + dy * dy <= radius * radius:
                    tiles.append((res, i, j))
        return tiles

    def _tiling(self, res: float) -> str:
        # The tiling in the path: tiles of another CRS, size or format never mix
        fmt = "asc" if re.search(r"aaigrid|asc", self.fmt) else "tif"
        return f"{self.crs.lower().replace(':', '')}-{res:g}m-{self.tile_px}px-{fmt}"

    def tile_path(self, cache_dir: str, tile) -> str:
        res, i, j = tile
        return os.path.join(cache_dir, self.folder, self._tiling(res), f"{i}_{j}.tif")

    def tile_of(self, path: str):
        match = re.fullmatch(rf"{re.escape(self.folder)}/([^/]+)/(-?\d+)_(-?\d+)\.tif", path)
        if not match:
            return None
        res = float(re.search(r"-([\d.]+)m-", match.group(1)).group(1))
        return (res, int(match.group(2)), int(match.group(3))) if match.group(1) == self._tiling(res) else None

    def bounds_wgs84(self, tile) -> Tuple[float, float, float, float]:
        """(west, south, east, north) of a tile."""
        res, i, j = tile
        size = self.tile_px * res
        return transform_bounds(self.crs, "EPSG:4326", i * size, j * size, (i + 1) * size, (j + 1) * size)

    def bytes_per_tile(self) -> float:
        return self.tile_px ** 2 * self.bytes_per_px

    def coverage_extent(self) -> Optional[tuple]:
        """(left, bottom, right, top) of the coverage in the service CRS, or None if unknown."""
        if self._extent is None:
            try:
                response = requests.get(self.url, timeout=60, headers=cache.http_headers(), params={
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

    def tile_url(self, tile) -> Optional[str]:
        return self.url

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
        return net._get(self.url, params)

    def download_tile(self, tile, path: str) -> Fetched:
        res, i, j = tile
        size, px = self.tile_px * res, self.tile_px
        left, bottom = i * size, j * size
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
            return Fetched(0, self.url)
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
