"""DegreeTiles: 1°×1° GeoTIFF tiles in WGS84 (Copernicus DEM, FABDEM), and OpenTopography's global DEM API."""

from typing import Callable, Optional

from messages import ServiceError

from ..credit import Credit
from ..composed import ComposedLayer
from ..indexes.tilings import DegreeTiling
from ..readers.download import Download


class DegreeTiles(ComposedLayer):
    """1°×1° tiles in WGS84, downloaded whole at native resolution: a DegreeTiling read by
    Download from url(lat, lon)."""

    def __init__(self, description: str, folder: str, url: Callable[[int, int], str],
                 native_res: float = 30, bytes_per_tile: float = 15e6, credit: Optional[Credit] = None):
        self.description, self.folder, self.url = description, folder, url
        self.native_res, self._bytes = native_res, bytes_per_tile
        self.credit = credit
        self.index = DegreeTiling(folder)
        self.reader = Download(description, self._tile_url, self._label)

    def _tile_url(self, tile) -> str:
        return self.url(*tile)

    @staticmethod
    def _label(tile) -> str:
        return f"tile {tile[0]},{tile[1]}"


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
