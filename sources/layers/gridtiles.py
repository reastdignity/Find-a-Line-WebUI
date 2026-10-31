"""GridTiles: our own tiles on a fixed grid (Slovakia), from a local mirror or a remote copy."""

from typing import List, Optional

from ..composed import ComposedLayer
from ..indexes.tilings import MetricTiling
from ..readers.tilebases import TileBases


class GridTiles(ComposedLayer):
    """Square tiles on a fixed grid in a metric CRS, our own hosted tiles (tools/sk_tiles.py),
    as <base>/<grid_tile_name>: a MetricTiling read by TileBases (the local mirror first,
    then the URLs). Tile (i, j) covers [i, i + 1) x [j, j + 1) tile sizes in the CRS.
    """

    def __init__(self, description: str, urls: List[str], crs: str, folder: str, tile_m: float,
                 native_res: float, bytes_per_tile: float, mirror: Optional[str] = None):
        self.description, self.urls, self.crs, self.folder = description, urls, crs, folder
        self.tile_m, self.native_res, self._bytes, self.mirror = tile_m, native_res, bytes_per_tile, mirror
        self.index = MetricTiling(crs, folder, tile_m)
        self.reader = TileBases(description, urls, mirror)

    def bases(self) -> List[str]:
        """Where the tiles come from, in order (see TileBases.bases)."""
        return self.reader.bases()
