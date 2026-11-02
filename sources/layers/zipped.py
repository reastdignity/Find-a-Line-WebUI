"""ZippedTiles: tiles of a fixed grid published as ZIP files whose names come from their coordinates (GeoSN's and
LGL's 2 km tiles)."""

import re
from typing import Callable, NamedTuple, Tuple

from ..composed import ComposedLayer
from ..indexes.tilings import MetricTiling
from ..readers.sheetfile import SheetFile
from ..readers.tilebases import grid_tile_name


class ZipSheet(NamedTuple):
    """What SheetFile needs to fetch one tile: its URL, its name in messages, CRS and pixel size."""
    url: str
    godlo: str
    crs: str
    res: float


class ZipTiling(MetricTiling):
    """A MetricTiling whose tile (i, j) is the ZIP at url(left, bottom) (the tile's lower-left
    corner in metres of crs), read by SheetFile at the pixel size res."""

    def __init__(self, crs: str, folder: str, tile_m: float, res: float, url: Callable[[float, float], str],
                 origin: Tuple[float, float] = (0.0, 0.0)):
        super().__init__(crs, folder, tile_m, origin)
        self.res, self.url = res, url

    def request(self, tile) -> ZipSheet:
        left, bottom, _, _ = self.edges(tile)
        url = self.url(left, bottom)
        return ZipSheet(url, url.rsplit("/", 1)[-1], self.crs, self.res)

    def tile_of(self, path: str):
        match = re.fullmatch(rf"{re.escape(self.folder)}/(-?\d+_-?\d+/(-?\d+)_(-?\d+)\.tif)", path)
        if not match:
            return None
        tile = int(match.group(2)), int(match.group(3))
        return tile if grid_tile_name(*tile) == match.group(1) else None


class ZippedTiles(ComposedLayer):
    """Square tiles of tile_m on a fixed grid from origin in a metric CRS, each a ZIP at
    url(left, bottom) whose members matching the regex members (GeoTIFF, XYZ or ASCII grids on
    the same pixels of native_res) are merged into the tile (SheetFile); a tile the server does
    not have (404) is missing. Cached as <folder>/<grid_tile_name>."""

    def __init__(self, description: str, folder: str, crs: str, tile_m: float, native_res: float,
                 url: Callable[[float, float], str], members: str, origin: Tuple[float, float] = (0.0, 0.0),
                 bytes_per_tile: float = 16e6):
        self.description, self.folder, self.crs, self.tile_m = description, folder, crs, tile_m
        self.native_res, self._bytes, self.members = native_res, bytes_per_tile, members
        self.index = ZipTiling(crs, folder, tile_m, native_res, url, origin)
        self.reader = SheetFile(description, members=members)
