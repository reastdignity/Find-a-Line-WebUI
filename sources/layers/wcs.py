"""WcsTiles: square tiles from an OGC WCS 2.0 (or 1.0) service on a fixed grid in the service's CRS; GeoWcsTiles:
tiles of a WCS 1.0.0 coverage's own pixels in a geographic CRS."""

from typing import Optional, Tuple

from ..composed import ComposedLayer
from ..indexes.tilings import GeoPixelTiling, WcsTiling
from ..readers.wcsreader import GeoWcsReader, WcsReader


class WcsTiles(ComposedLayer):
    """Square tiles from a WCS 2.0 service, on a fixed grid in the service CRS: a WcsTiling
    read by WcsReader (clipped to the coverage where the service refuses a request beyond it).

    fetch_res=None requests tiles at the working resolution (the server
    downsamples); a number requests tiles at that resolution, cached independently
    of the working resolution and downsampled locally. origin: the pixel edges of the
    coverage (x, y in metres) when they are not on multiples of fetch_res, so tiles are
    requested on its own pixels (see WcsTiling). params: more parameters of every
    GetCoverage (see WcsReader). edge_px: pixels dropped at the edges of the data, for a
    service whose edge pixels are wrong (see WcsReader). key_params: (query parameter, secret of
    settings.ServiceKeys) put into every request, the layer unavailable without them; version:
    the WCS version the service speaks, "2.0.1" or "1.0.0"; split_on_error: a tile the service
    answers with an HTTP 5xx is asked again in pieces (see WcsReader).
    """

    def __init__(self, description: str, url: str, coverage: str, crs: str, folder: str,
                 native_res: float, tile_px: int = 2000, fmt: str = "image/tiff",
                 axes: Tuple[str, str] = ("x", "y"), fetch_res: Optional[float] = None,
                 interpolation: Optional[str] = None, zero_is_nodata: bool = False,
                 bytes_per_px: float = 4, shift: Tuple[float, float] = (0.0, 0.0),
                 origin: Tuple[float, float] = (0.0, 0.0), params: Tuple[Tuple[str, str], ...] = (),
                 edge_px: int = 0, key_params: Tuple[Tuple[str, str], ...] = (), version: str = "2.0.1",
                 split_on_error: bool = False):
        self.description, self.url, self.coverage, self.crs = description, url, coverage, crs
        self.folder, self.native_res, self.tile_px, self.fmt = folder, native_res, tile_px, fmt
        self.axes, self.fetch_res, self.interpolation = axes, fetch_res, interpolation
        self.zero_is_nodata, self.bytes_per_px, self.shift = zero_is_nodata, bytes_per_px, shift
        self.origin, self.params, self.edge_px = origin, tuple(params), edge_px
        self._bytes = tile_px ** 2 * bytes_per_px
        self.index = WcsTiling(crs, folder, tile_px, fmt, fetch_res, shift, origin, edge_px)
        self.reader = WcsReader(description, url, coverage, crs, native_res, tile_px, fmt, axes, interpolation,
                                zero_is_nodata, origin, params, edge_px, key_params, version, split_on_error)

    def coverage_extent(self) -> Optional[tuple]:
        """(left, bottom, right, top) of the coverage in the service CRS, or None if unknown."""
        return self.reader.coverage_extent()


class GeoWcsTiles(ComposedLayer):
    """Tiles of tile_px x tile_px pixels of a WCS 1.0.0 coverage in a geographic CRS, on its own pixels: the
    grid's north-west corner (west, north), its pixel (dx, dy degrees, not square) and its size (columns, rows)
    as its capabilities give them (GeoPixelTiling, read by GeoWcsReader; a tile without a valid pixel is
    missing). native_res: the pixel's size in metres (the source's resolution). The mosaic reprojects the
    tiles onto the working grid. Geoscience Australia's national 5 m lidar DEM (EPSG:4283)."""

    def __init__(self, description: str, url: str, coverage: str, crs: str, folder: str, native_res: float,
                 corner: Tuple[float, float], pixel: Tuple[float, float], size: Tuple[int, int],
                 tile_px: int = 1000, fmt: str = "GeoTIFF", zero_is_nodata: bool = False,
                 params: Tuple[Tuple[str, str], ...] = ()):
        self.description, self.url, self.coverage, self.crs = description, url, coverage, crs
        self.folder, self.native_res, self.tile_px = folder, native_res, tile_px
        self._bytes = tile_px ** 2 * 4
        self.index = GeoPixelTiling(crs, folder, tile_px, corner, pixel, size)
        self.reader = GeoWcsReader(description, url, coverage, crs, fmt, zero_is_nodata, params)
