"""MetricSheetTiles: sheets of a fixed metric grid, each a whole GeoTIFF named from its place in the grid (Estonia's
1 km DSM sheets)."""

import re
from typing import Callable, Optional, Sequence, Tuple

from ..composed import ComposedLayer
from ..layer import Fetched
from ..indexes.tilings import MetricTiling
from ..readers.download import Download
from ..readers.tilebases import grid_tile_name


class SheetTiling(MetricTiling):
    """A MetricTiling whose tile (i, j) is the sheet sheet(i, j) (None: the publisher has none there, so its request
    is None and it is missing without one), downloaded from url(name). Cached as <folder>/<grid_tile_name>."""

    def __init__(self, crs: str, folder: str, tile_m: float, sheet: Callable[[int, int], Optional[str]],
                 url: Callable[[str], str], origin: Tuple[float, float] = (0.0, 0.0)):
        super().__init__(crs, folder, tile_m, origin)
        self.sheet, self.url = sheet, url

    def request(self, tile) -> Optional[Tuple[str, str]]:
        """(sheet name, URL) of a tile, None without a sheet."""
        name = self.sheet(*tile)
        return None if name is None else (name, self.url(name))

    def tile_of(self, path: str):
        match = re.fullmatch(rf"{re.escape(self.folder)}/(-?\d+_-?\d+/(-?\d+)_(-?\d+)\.tif)", path)
        if not match:
            return None
        tile = int(match.group(2)), int(match.group(3))
        return tile if grid_tile_name(*tile) == match.group(1) else None


class MetricSheetTiles(ComposedLayer):
    """Square sheets of tile_m on a fixed grid from origin in a metric CRS, each one GeoTIFF downloaded whole from
    url(sheet(i, j)) (Download: a one-band float file written again as the cache's tiles, its own pixels kept). A
    tile without a sheet (sheet None: not in the publisher's table) is missing without a request, and so is a sheet
    answered 404 or with a page matching not_found. Only TIFFs are kept (Download(tiff_only=True)): Estonia's
    download address answers an error as an HTML page (with HTTP 200 or 206), never cached as a tile."""

    def __init__(self, description: str, folder: str, crs: str, tile_m: float, native_res: float,
                 sheet: Callable[[int, int], Optional[str]], url: Callable[[str], str],
                 origin: Tuple[float, float] = (0.0, 0.0), bytes_per_tile: float = 4e6,
                 binary_types: Sequence[str] = ("tiff",), not_found: Optional[str] = None):
        self.description, self.folder, self.crs, self.tile_m = description, folder, crs, tile_m
        self.native_res, self._bytes = native_res, bytes_per_tile
        self.index = SheetTiling(crs, folder, tile_m, sheet, url, origin)
        self.reader = Download(description, lambda request: request[1], lambda request: f"sheet {request[0]}",
                               binary_types=tuple(binary_types), tiff_only=True, not_found=not_found)

    def tile_url(self, tile) -> Optional[str]:
        request = self.index.request(tile)
        return None if request is None else request[1]

    def download_tile(self, tile, path: str) -> Fetched:
        request = self.index.request(tile)
        if request is None:  # no such sheet: missing without a request
            return Fetched(0)
        return self.reader.fetch(request, path)
