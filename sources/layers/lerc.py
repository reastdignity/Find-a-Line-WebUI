"""LercTiles: the tiles of an Esri elevation tile cache (an ArcGIS ImageServer of cacheType "Elevation", LERC1
tiles of 257 x 257 corner samples in Web Mercator), at the level that suits the working grid."""

from typing import Optional, Tuple

from ..composed import ComposedLayer
from ..indexes.mercator import MercatorTiling, TileCells
from ..readers.lerc import LercTileReader


class LercTiles(ComposedLayer):
    """An Esri elevation tile cache at `url` (the ImageServer's address): MercatorTiling (the level whose cell on
    the ground is the coarsest not coarser than the working grid's pixel, at most max_level: the finest level the
    data fill) read by LercTileReader (a tile of 256 x 256 px in EPSG:3857 on its own samples; NaN where the LERC
    mask says no data and below floor). The mosaic reprojects the tiles onto the working grid, the one resampling
    of the data on our side. The provider's LERC tolerance (tileInfo's `lercError`) comes on top: every sample within
    it of the provider's value (DAERA's Northern Ireland coastal DTM 0.1 m, IPP's Rio de Janeiro DTM 0.05 m).

    native_res: the data's own resolution in metres (the source's default resolution); bytes_per_tile: an answer's
    size, for the estimates (LERC1: 8-60 kB in 2026-11, 70 bytes without data). extent: the service's
    fullExtent in EPSG:3857 (tiles outside it make no request). cells: an .npz of tools/lerc_coverage.py, the
    cells the cache holds data in, for has_data_near (within near_m of the centre) and to leave out the tiles far
    from any (see MercatorTiling); None: every tile is asked, has_data_near unknown.

    Tiles meet edge to edge, so a bilinear reprojection takes the half sample along each tile's edge from that
    tile's outer samples alone (no neighbour's sample in one file's warp), as for every tiled layer the mosaic
    reprojects."""

    def __init__(self, description: str, url: str, folder: str, native_res: float, max_level: int,
                 floor: Optional[float] = None, extent: Optional[Tuple[float, float, float, float]] = None,
                 cells: Optional[str] = None, near_m: float = 1000, bytes_per_tile: float = 50e3):
        self.description, self.url, self.folder, self.native_res = description, url, folder, native_res
        self.max_level, self.floor, self.cells, self.near_m = max_level, floor, cells, near_m
        self._bytes = bytes_per_tile
        self.index = MercatorTiling(folder, max_level, extent, TileCells(cells) if cells else None)
        self.reader = LercTileReader(description, url, floor)

    def has_data_near(self, lat: float, lon: float, cache_dir: str) -> Optional[bool]:
        return self.index.has_data_near(lat, lon, cache_dir, self.near_m)
