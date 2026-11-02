"""ImageServerTiles: square tiles from an ArcGIS ImageServer (exportImage) on the service's own pixels."""

from typing import Dict, Optional, Sequence, Tuple

from ..composed import ComposedLayer
from ..indexes.tilings import WcsTiling
from ..readers.imageserver import ImageServerReader


class ImageServerTiles(ComposedLayer):
    """Square tiles of tile_px pixels from an ArcGIS ImageServer, a WcsTiling at the service's resolution
    (native_res) from origin (the pixel edges of the service's grid, x and y modulo native_res) read by
    ImageServerReader: every tile on the stored pixels, cached as
    <folder>/<crs>-<res>m-<px>px-tif[-o<x>_<y>]/<i>_<j>.tif whatever the working resolution (coarser grids
    are averaged locally, finer ones interpolated). sr, nodata, mosaic_rule, lock_raster_ids and params: see
    ImageServerReader.
    """

    def __init__(self, description: str, url: str, crs: str, folder: str, native_res: float,
                 tile_px: int = 1000, origin: Tuple[float, float] = (0.0, 0.0), sr: Optional[str] = None,
                 nodata: float = -9999.0, mosaic_rule: Optional[Dict] = None, lock_raster_ids: Sequence[int] = (),
                 params: Tuple[Tuple[str, str], ...] = (), zero_is_nodata: bool = False,
                 bytes_per_px: float = 3):
        self.description, self.url, self.crs, self.folder = description, url, crs, folder
        self.native_res, self.tile_px, self.origin = native_res, tile_px, origin
        self._bytes = tile_px ** 2 * bytes_per_px
        self.index = WcsTiling(crs, folder, tile_px, "image/tiff", native_res, origin=origin)
        self.reader = ImageServerReader(description, url, crs, native_res, tile_px, origin, sr, nodata,
                                        mosaic_rule=mosaic_rule, lock_raster_ids=lock_raster_ids, params=params,
                                        zero_is_nodata=zero_is_nodata)
