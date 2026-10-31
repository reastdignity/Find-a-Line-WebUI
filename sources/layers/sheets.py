"""SheetTiles: map sheets from a WFS sheet index (geoportal.gov.pl)."""

from ..indexes.cached import CachedIndex
from ..indexes.listings import WfsSheets
from ..indexes.versions import NewestPerSheet
from ..readers.sheetfile import SheetFile
from .indexed import IndexedTiles


class SheetTiles(IndexedTiles):
    """Map sheets listed in a WFS sheet index, downloaded as files (geoportal.gov.pl): a
    CachedIndex of WfsSheets with NewestPerSheet, read by SheetFile.

    The index has one layer per year (`<prefix><year>`); every sheet links to a file
    (ASCII grid or XYZ, sometimes zipped). Extents are cached in EPSG:2180.
    """
    index_crs = "EPSG:2180"

    def __init__(self, description: str, index_url: str, prefix: str, folder: str,
                 native_res: float, min_res: float = 0.5, bytes_per_tile: float = 30e6):
        """Sheets with a resolution between min_res and native_res are used (finer ones
        are huge as text: a 0.15 m sheet is about 2 GB)."""
        super().__init__(description, index_url, prefix, folder, native_res, bytes_per_tile)
        self.min_res = min_res
        self.index = CachedIndex(description, WfsSheets(index_url, prefix, native_res, min_res),
                                 NewestPerSheet(folder, self.index_crs, native_res), prefix, folder.split("/")[0])
        self.reader = SheetFile(description)
