"""WcsTiles: square tiles from an OGC WCS 2.0 service on a fixed grid in the service's CRS."""

from typing import Optional, Tuple

from ..composed import ComposedLayer
from ..indexes.tilings import WcsTiling
from ..readers.wcsreader import WcsReader


class WcsTiles(ComposedLayer):
    """Square tiles from a WCS 2.0 service, on a fixed grid in the service CRS: a WcsTiling
    read by WcsReader (clipped to the coverage where the service refuses a request beyond it).

    fetch_res=None requests tiles at the working resolution (the server
    downsamples); a number requests tiles at that resolution, cached independently
    of the working resolution and downsampled locally.
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
        self._bytes = tile_px ** 2 * bytes_per_px
        self.index = WcsTiling(crs, folder, tile_px, fmt, fetch_res, shift)
        self.reader = WcsReader(description, url, coverage, crs, native_res, tile_px, fmt, axes, interpolation,
                                zero_is_nodata)

    def coverage_extent(self) -> Optional[tuple]:
        """(left, bottom, right, top) of the coverage in the service CRS, or None if unknown."""
        return self.reader.coverage_extent()
