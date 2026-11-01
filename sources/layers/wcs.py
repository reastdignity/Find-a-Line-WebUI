"""WcsTiles: square tiles from an OGC WCS 2.0 (or 1.0) service on a fixed grid in the service's CRS."""

from typing import Optional, Tuple

from ..composed import ComposedLayer
from ..indexes.tilings import WcsTiling
from ..readers.wcsreader import WcsReader


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
    the WCS version the service speaks, "2.0.1" or "1.0.0" (see WcsReader).
    """

    def __init__(self, description: str, url: str, coverage: str, crs: str, folder: str,
                 native_res: float, tile_px: int = 2000, fmt: str = "image/tiff",
                 axes: Tuple[str, str] = ("x", "y"), fetch_res: Optional[float] = None,
                 interpolation: Optional[str] = None, zero_is_nodata: bool = False,
                 bytes_per_px: float = 4, shift: Tuple[float, float] = (0.0, 0.0),
                 origin: Tuple[float, float] = (0.0, 0.0), params: Tuple[Tuple[str, str], ...] = (),
                 edge_px: int = 0, key_params: Tuple[Tuple[str, str], ...] = (), version: str = "2.0.1"):
        self.description, self.url, self.coverage, self.crs = description, url, coverage, crs
        self.folder, self.native_res, self.tile_px, self.fmt = folder, native_res, tile_px, fmt
        self.axes, self.fetch_res, self.interpolation = axes, fetch_res, interpolation
        self.zero_is_nodata, self.bytes_per_px, self.shift = zero_is_nodata, bytes_per_px, shift
        self.origin, self.params, self.edge_px = origin, tuple(params), edge_px
        self._bytes = tile_px ** 2 * bytes_per_px
        self.index = WcsTiling(crs, folder, tile_px, fmt, fetch_res, shift, origin, edge_px)
        self.reader = WcsReader(description, url, coverage, crs, native_res, tile_px, fmt, axes, interpolation,
                                zero_is_nodata, origin, params, edge_px, key_params, version)

    def coverage_extent(self) -> Optional[tuple]:
        """(left, bottom, right, top) of the coverage in the service CRS, or None if unknown."""
        return self.reader.coverage_extent()
