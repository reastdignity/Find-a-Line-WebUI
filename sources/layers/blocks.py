"""DegreeBlocks: blocks of 1° files at a fixed URL, read by HTTP range requests."""

from typing import Callable, Optional

from ..credit import Credit
from ..composed import ComposedLayer
from ..indexes.tilings import TenthDegreeTiling, degree_tile_name
from ..readers.windows import Windows


class DegreeBlocks(ComposedLayer):
    """Blocks of 1°×1° cloud-optimized GeoTIFFs at a fixed URL per tile (3DEP's seamless 1/3″
    DEM, NAD83 geographic), read by HTTP range requests: a tile is about 450 MB, a block of
    0.1° about 2 MB. Block (i, j) covers [i, i + 1) × [j, j + 1) tenths of a degree, cached in
    <folder>/<tile>/<i>_<j>.tif; a tile the service does not have (404: sea, Canada) is missing.
    A TenthDegreeTiling read by Windows.
    """

    def __init__(self, description: str, folder: str, url: Callable[[str], str], crs: str,
                 px_per_degree: int, native_res: float, bytes_per_tile: float = 2e6, credit: Optional[Credit] = None):
        self.description, self.folder, self.url, self.crs = description, folder, url, crs
        self.px_per_degree, self.native_res, self._bytes = px_per_degree, native_res, bytes_per_tile
        self.credit = credit
        self.index = TenthDegreeTiling(crs, folder, px_per_degree, url)
        self.reader = Windows(description)

    @staticmethod
    def tile_name(i: int, j: int) -> str:
        """The 1° tile of a block, named by its north-west corner (n38w120: 37-38° N, 120-119° W)."""
        return degree_tile_name(i, j)
