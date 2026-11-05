"""ImageServerTiles: square tiles from an ArcGIS ImageServer (exportImage) on the service's own pixels, or in
the zone of the working grid (zones)."""

from typing import Dict, Optional, Sequence, Tuple

from grid import Grid

from ..composed import ComposedLayer, Index, Reader
from ..indexes.tilings import WcsTiling
from ..layer import Fetched
from ..readers.imageserver import ImageServerReader


class ZonedTiling(Index):
    """The same WcsTiling in several CRSs (the zones of one projection, e.g. GDA94 / MGA 54-56), the first the
    default: a grid in one of them gets its tiles in its own CRS, any other grid those of the default. A tile is
    (crs, tile of that CRS's tiling); each CRS has its own folder in the cache (WcsTiling names it)."""

    def __init__(self, tilings: Dict[str, WcsTiling]):
        self.tilings = tilings
        self.default = next(iter(tilings))

    def zone(self, crs: str) -> str:
        """The CRS of the tiles of a grid in crs."""
        crs = crs.upper()
        return crs if crs in self.tilings else self.default

    def tiles(self, grid: Grid) -> list:
        crs = self.zone(grid.crs)
        return [(crs, tile) for tile in self.tilings[crs].tiles(grid)]

    def path(self, cache_dir: str, tile) -> str:
        crs, inner = tile
        return self.tilings[crs].path(cache_dir, inner)

    def tile_of(self, path: str):
        for crs, tiling in self.tilings.items():
            inner = tiling.tile_of(path)
            if inner is not None:
                return crs, inner
        return None

    def bounds_wgs84(self, tile) -> Tuple[float, float, float, float]:
        crs, inner = tile
        return self.tilings[crs].bounds_wgs84(inner)


class ZonedReader(Reader):
    """The readers of a ZonedTiling's CRSs: a tile (crs, tile) is fetched by the reader of its CRS."""
    rewrites = True  # the cached tile is written by _write_tile: reencode / cache migrate may convert it

    def __init__(self, readers: Dict[str, Reader]):
        self.readers = readers

    def url(self, request) -> Optional[str]:
        crs, inner = request
        return self.readers[crs].url(inner)

    def fetch(self, request, path: str) -> Fetched:
        crs, inner = request
        return self.readers[crs].fetch(inner, path)


class ImageServerTiles(ComposedLayer):
    """Square tiles of tile_px pixels from an ArcGIS ImageServer, a WcsTiling at the service's resolution
    (native_res) from origin (the pixel edges of the service's grid, x and y modulo native_res) read by
    ImageServerReader: every tile on the stored pixels, cached as
    <folder>/<crs>-<res>m-<px>px-tif[-o<x>_<y>]/<i>_<j>.tif whatever the working resolution (coarser grids
    are averaged locally, finer ones interpolated). sr, nodata, mosaic_rule, lock_raster_ids and params: see
    ImageServerReader.

    zones: more CRSs to ask the service for (a service that reprojects on request, whose stored pixels are in
    none of them, e.g. Queensland's in Web Mercator): crs and each zone get a tiling of the same tile_px,
    native_res and origin, and a grid in one of them is served in its own CRS (ZonedTiling: a tile is then
    (crs, (res, i, j)), sr each zone's WKID); readers holds the reader of every CRS, crs's the default.
    """

    def __init__(self, description: str, url: str, crs: str, folder: str, native_res: float,
                 tile_px: int = 1000, origin: Tuple[float, float] = (0.0, 0.0), sr: Optional[str] = None,
                 nodata: float = -9999.0, mosaic_rule: Optional[Dict] = None, lock_raster_ids: Sequence[int] = (),
                 params: Tuple[Tuple[str, str], ...] = (), zero_is_nodata: bool = False,
                 bytes_per_px: float = 3, zones: Sequence[str] = (), interpolation: str = "RSP_NearestNeighbor"):
        self.description, self.url, self.crs, self.folder = description, url, crs, folder
        self.native_res, self.tile_px, self.origin = native_res, tile_px, origin
        self.zones = tuple(z for z in dict.fromkeys(z.upper() for z in zones) if z != crs.upper())
        self._bytes = tile_px ** 2 * bytes_per_px

        def reader(zone: str, zone_sr: Optional[str]) -> ImageServerReader:
            return ImageServerReader(description, url, zone, native_res, tile_px, origin, zone_sr, nodata,
                                     interpolation=interpolation, mosaic_rule=mosaic_rule,
                                     lock_raster_ids=lock_raster_ids, params=params, zero_is_nodata=zero_is_nodata)

        self.readers = {crs: reader(crs, sr), **{zone: reader(zone, None) for zone in self.zones}}
        if not self.zones:
            self.index = WcsTiling(crs, folder, tile_px, "image/tiff", native_res, origin=origin)
            self.reader = self.readers[crs]
            return
        self.index = ZonedTiling({zone: WcsTiling(zone, folder, tile_px, "image/tiff", native_res, origin=origin)
                                  for zone in self.readers})
        self.reader = ZonedReader(self.readers)
