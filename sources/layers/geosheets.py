"""GeoSheetTiles: sheets of a fixed geographic grid, each a whole file named from its place in the grid (IDE Uruguay's
2.5 m DTM)."""

from typing import Callable, Optional, Tuple

from ..composed import ComposedLayer
from ..layer import Fetched
from ..indexes.tilings import GeoSheetTiling
from ..readers.download import Download


class GeoSheetTiles(ComposedLayer):
    """Sheets that are the cells (cell: width, height in degrees from origin) of a geographic grid in crs, each
    downloaded whole from url(i, j) (Download: a one-band float file is written again as the cache's tiles, in its
    own CRS and on its own pixels, which the mosaic resamples onto the working grid). A cell whose url is None
    (not in the publisher's table of sheets) is missing without a request, and so is a sheet answered 404.
    Cached as <folder>/<sheet(i, j)>.tif (GeoSheetTiling)."""

    def __init__(self, description: str, folder: str, crs: str, cell: Tuple[float, float],
                 origin: Tuple[float, float], native_res: float, sheet: Callable[[int, int], Optional[str]],
                 parse_sheet: Callable[[str], Optional[Tuple[int, int]]], url: Callable[[int, int], Optional[str]],
                 within: Optional[Tuple[int, int, int, int]] = None, bytes_per_tile: float = 20e6):
        self.description, self.folder, self.crs = description, folder, crs
        self.native_res, self._bytes = native_res, bytes_per_tile
        self.index = GeoSheetTiling(crs, folder, cell, origin, sheet, parse_sheet, url, within)
        self.reader = Download(description, lambda tile: url(*tile), lambda tile: f"sheet {sheet(*tile)}")

    def tile_url(self, tile) -> Optional[str]:
        return None if self.index.request(tile) is None else self.reader.url(tile)

    def download_tile(self, tile, path: str) -> Fetched:
        if self.index.request(tile) is None:  # no such sheet: missing without a request
            return Fetched(0)
        return self.reader.fetch(tile, path)
