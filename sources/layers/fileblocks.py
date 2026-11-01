"""FileBlocks: blocks of big fixed files in a metric CRS (a grid of COGs, or one national COG), read by HTTP range
requests."""

from typing import Callable, Optional, Tuple, Union

from ..credit import Credit
from ..composed import ComposedLayer
from ..indexes.tilings import FileBlockTiling, FileList
from ..readers.windows import Windows


class FileBlocks(ComposedLayer):
    """Blocks of block_m read from big cloud-optimized GeoTIFFs at fixed addresses in a metric
    CRS, on the files' own pixels (res, origin): a fixed grid of files (Austria's 50 km tiles,
    files(i, j) giving the files of block (i, j)) or one national file (its address as files).
    Only the blocks over the grid are read, each cached in
    <folder>/<i // 50>_<j // 50>/<i>_<j>.tif; a block without files, outside extent or outside
    the data (404, or no values) is missing. A FileBlockTiling read by Windows.
    """

    def __init__(self, description: str, folder: str, crs: str, res: float, block_m: float,
                 files: Union[str, Callable[[int, int], FileList]], origin: Tuple[float, float] = (0.0, 0.0),
                 extent: Optional[Tuple[float, float, float, float]] = None, year: int = 0,
                 bytes_per_tile: float = 3e6, credit: Optional[Credit] = None):
        self.description, self.folder, self.crs, self.native_res = description, folder, crs, res
        self.block_m, self._bytes, self.credit = block_m, bytes_per_tile, credit
        self.index = FileBlockTiling(crs, folder, res, block_m, files, origin, extent, year)
        self.reader = Windows(description)
