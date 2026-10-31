"""DegreeTiles: 1°×1° GeoTIFF tiles in WGS84 (Copernicus DEM, FABDEM), and OpenTopography's global DEM API."""

import math
import os
from typing import Callable, Optional

from rasterio.warp import transform_bounds

from grid import Grid
from messages import ServiceError

from .. import net
from ..net import _part
from ..credit import Credit
from ..layer import Fetched, Layer, _hemi


class DegreeTiles(Layer):
    """1°×1° tiles in WGS84, downloaded whole at native resolution."""

    def __init__(self, description: str, folder: str, url: Callable[[int, int], str],
                 native_res: float = 30, bytes_per_tile: float = 15e6, credit: Optional[Credit] = None):
        self.description, self.folder, self.url = description, folder, url
        self.native_res, self._bytes = native_res, bytes_per_tile
        self.credit = credit

    def tiles(self, grid: Grid):
        west, south, east, north = transform_bounds(grid.crs, "EPSG:4326", *grid.bounds)
        return [(lat, lon) for lat in range(math.floor(south), math.floor(north) + 1)
                for lon in range(math.floor(west), math.floor(east) + 1)]

    def tile_path(self, cache_dir: str, tile) -> str:
        lat, lon = tile
        return os.path.join(cache_dir, self.folder, f"{_hemi(lat, 'N', 'S', 2)}{_hemi(lon, 'E', 'W', 3)}.tif")

    def bytes_per_tile(self) -> float:
        return self._bytes

    def tile_url(self, tile) -> Optional[str]:
        return self.url(*tile)

    def download_tile(self, tile, path: str) -> Fetched:
        lat, lon = tile
        url = self.url(lat, lon)
        try:
            response = net._get(url)
        except RuntimeError as e:
            raise RuntimeError(f"Could not download {self.description} tile {lat},{lon}: {e}")
        if response is None:  # no tile there (sea)
            return Fetched(0, url)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = _part(path)
        with open(tmp, "wb") as f:
            f.write(response.content)
        os.replace(tmp, path)
        return Fetched.of(response, url)


class OpenTopographyTiles(DegreeTiles):
    """Global DEMs from the OpenTopography API (needs a free API key)."""
    API = "https://portal.opentopography.org/API/globaldem"
    api_key: Optional[str] = None

    def __init__(self, description: str, folder: str, demtype: str, native_res: float = 30):
        super().__init__(description, folder, self._url, native_res, bytes_per_tile=8e6)
        self.demtype = demtype

    def _url(self, lat: int, lon: int) -> str:
        if not self.api_key:
            raise ServiceError("an OpenTopography API key is needed: set OPENTOPOGRAPHY_API_KEY "
                               "or use --opentopo-key (free at portal.opentopography.org)", "opentopo_key")
        return (f"{self.API}?demtype={self.demtype}&south={lat}&north={lat + 1}&west={lon}"
                f"&east={lon + 1}&outputFormat=GTiff&API_Key={self.api_key}")
