"""WmsrTiles: square tiles of raw heights from a WMS GetMap (IGN's WMS-R), on a fixed grid in the service's
CRS, fetched at a resolution chosen for the working grid."""

from typing import Dict, Optional, Sequence, Tuple

from grid import Grid

from ..composed import ComposedLayer, Index
from ..indexes.tilings import WcsTiling
from ..readers.wmsr import MapRequest, WmsrReader


class ResolutionTiling(Index):
    """Square tiles of tile_m metres from origin (x, y: the service's pixel edges) in crs, at one of the
    fetch resolutions: the coarsest not coarser than the working grid (the finest for a finer grid), so a
    grid of 1 m or more reads 1 m tiles where the service answers 1 m as the exact mean of its 0.5 m
    pixels. Per resolution a WcsTiling of tile_m / res pixels (its cache folder, paths, tile_of and
    edges): tile (res, i, j) covers [i, i + 1) x [j, j + 1) tile sizes from origin, cached as
    <folder>/<crs>-<res>m-<px>px-tif[-o<x>_<y>]/<i>_<j>.tif, so the resolutions never mix."""

    def __init__(self, crs: str, folder: str, tile_m: float, fetch_res: Sequence[float],
                 origin: Tuple[float, float] = (0.0, 0.0)):
        self.crs, self.folder, self.tile_m, self.origin = crs, folder, tile_m, origin
        self.fetch_res = tuple(sorted(fetch_res))
        self.tilings: Dict[float, WcsTiling] = {}
        for res in self.fetch_res:
            px = round(tile_m / res)
            if px * res != tile_m:
                raise ValueError(f"tiles of {tile_m} m are not whole pixels of {res} m")
            self.tilings[res] = WcsTiling(crs, folder, px, "image/tiff", res, origin=origin)

    def resolution(self, grid_res: float) -> float:
        """The fetch resolution of a working grid."""
        return max((r for r in self.fetch_res if r <= grid_res + 1e-9), default=self.fetch_res[0])

    def tiles(self, grid: Grid) -> list:
        return self.tilings[self.resolution(grid.res)].tiles(grid)

    def path(self, cache_dir: str, tile) -> str:
        return self.tilings[tile[0]].path(cache_dir, tile)

    def tile_of(self, path: str):
        # A tiling's tile_of reads the resolution from the folder's name: the tiling of that resolution only
        return next((t for res, tiling in self.tilings.items() for t in [tiling.tile_of(path)]
                     if t and t[0] == res), None)

    def bounds_wgs84(self, tile) -> Tuple[float, float, float, float]:
        return self.tilings[tile[0]].bounds_wgs84(tile)

    def request(self, tile) -> MapRequest:
        tiling = self.tilings[tile[0]]
        left, bottom, right, top = tiling.edges(tile)
        return MapRequest(left, bottom, right, top, tiling.tile_px, tiling.tile_px)


class WmsrTiles(ComposedLayer):
    """Tiles of a raster layer of a WMS whose GetMap answers raw heights as GeoTIFF (IGN's WMS-R): a
    ResolutionTiling read by WmsrReader. native_res: the layer's own pixels; fetch_res: the resolutions
    tiles are fetched at (the server's answer at a coarser one must be the mean of its pixels: checked for
    IGN's LiDAR HD at 1 m); origin: the pixel edges of the layer when they are not on multiples of its
    resolution (LiDAR HD: x on .75, y on .25); params: more GetMap parameters (see WmsrReader);
    bytes_per_tile: a tile's download, for estimates (at the coarsest fetch resolution)."""

    def __init__(self, description: str, url: str, layer: str, crs: str, folder: str, native_res: float,
                 fetch_res: Sequence[float], tile_m: float = 1000, origin: Tuple[float, float] = (0.0, 0.0),
                 params: Optional[Tuple[Tuple[str, str], ...]] = None, bytes_per_tile: float = 0):
        self.description, self.url, self.crs, self.folder = description, url, crs, folder
        self.native_res, self.tile_m, self.origin = native_res, tile_m, origin
        self.index = ResolutionTiling(crs, folder, tile_m, fetch_res, origin)
        self.fetch_res = self.index.fetch_res
        self.reader = WmsrReader(description, url, layer, crs) if params is None else \
            WmsrReader(description, url, layer, crs, params)
        self._bytes = bytes_per_tile
