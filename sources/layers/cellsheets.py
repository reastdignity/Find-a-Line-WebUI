"""CellSheetTiles: sheets that are the cells of a metric grid of any cell size, each one or more ZIPs named by the
publisher's scheme and listed in a static table (Tokyo's 400 x 300 m grid sheets)."""

from typing import Callable, Optional, Sequence, Tuple

from rasterio.transform import from_origin

from ..composed import ComposedLayer
from ..layer import Fetched
from ..indexes.tilings import MetricCellTiling
from ..readers.sheetsets import SheetSetFile, SheetSetRequest

# The files of a cell: (name, url, survey year), newest first; empty: the publisher has none
CellFiles = Callable[[int, int], Sequence[Tuple[str, str, int]]]


class CellSheetTiling(MetricCellTiling):
    """A MetricCellTiling whose cell (i, j) is made of the ZIPs files(i, j) (a static table of the publisher's;
    empty: no file there, and no tile), composed on the cell's pixels of res by SheetSetFile."""

    def __init__(self, crs: str, folder: str, cell: Tuple[float, float], name: Callable[[int, int], Optional[str]],
                 parse: Callable[[str], Optional[Tuple[int, int]]], res: float, files: CellFiles,
                 origin: Tuple[float, float] = (0.0, 0.0)):
        super().__init__(crs, folder, cell, name, parse, origin)
        self.res, self.files = res, files

    def _tiles(self, grid) -> list:
        """The cells of the table only: a cell without a file is no tile (no estimate, no record, no request)."""
        return [cell for cell in super()._tiles(grid) if self.files(*cell)]

    def request(self, tile) -> Optional[SheetSetRequest]:
        files = self.files(*tile)
        if not files:
            return None
        left, bottom, right, top = self.edges(tile)
        return SheetSetRequest(tuple((name, url, year, 0) for name, url, year in files), self.crs,
                               from_origin(left, top, self.res, self.res),
                               (round((top - bottom) / self.res), round((right - left) / self.res)),
                               self.name(*tile).rsplit("/", 1)[-1])


class CellSheetTiles(ComposedLayer):
    """Sheets that are the cells (cell: width, height in metres from origin) of a grid in a metric CRS, each made of
    the ZIPs files(i, j) whose members matching the regex members are placed on the cell's pixels by their own
    coordinates (SheetSetFile: in crs whatever the members name, so a file naming a CRS without its EPSG code is
    read as crs; a file smaller than its cell fills its part): the newest first, an older one only while the cell
    has holes (Tokyo's sheets on the line between Tama's and the wards' surveys are in both folders, each partial).
    A cell without a file in the table is no tile, never asked; a file of the table the server does not give
    (403, 404 or any other error) is an error of that tile, asked again by the next search, never recorded as
    missing. Cached as <folder>/<name(i, j)>.tif (MetricCellTiling). height_offset: Layer.height_offset (Hong Kong's
    datum), applied where the tiles are read onto the grid, never to the cached files."""

    def __init__(self, description: str, folder: str, crs: str, cell: Tuple[float, float], native_res: float,
                 name: Callable[[int, int], Optional[str]], parse: Callable[[str], Optional[Tuple[int, int]]],
                 files: CellFiles, members: str, origin: Tuple[float, float] = (0.0, 0.0),
                 bytes_per_tile: float = 2e6, height_offset: float = 0.0):
        self.description, self.folder, self.crs, self.cell = description, folder, crs, cell
        self.native_res, self._bytes, self.members = native_res, bytes_per_tile, members
        self.height_offset = height_offset
        self.index = CellSheetTiling(crs, folder, cell, name, parse, native_res, files, origin)
        self.reader = SheetSetFile(description, members)

    def tile_url(self, tile) -> Optional[str]:
        request = self.index.request(tile)
        return None if request is None else self.reader.url(request)

    def download_tile(self, tile, path: str) -> Fetched:
        request = self.index.request(tile)
        if request is None:  # not in the publisher's table: missing without a request
            return Fetched(0)
        return self.reader.fetch(request, path)
