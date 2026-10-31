"""StacTiles: tiles of a STAC collection (swisstopo)."""

from typing import Dict, Optional, Tuple

from grid import Grid

from ..indexes.cached import CachedIndex
from ..indexes.listings import StacItems
from ..indexes.versions import NewestPerSheet
from ..readers.download import Download
from .indexed import IndexedTiles


class StacTiles(IndexedTiles):
    """Square tiles of a STAC collection, one item per tile and survey year (swisstopo).

    An item (`<product>_<year>_<E>-<N>`, E and N in km) holds the tile as a
    cloud-optimized GeoTIFF at one or more resolutions (swissALTI3D: 0.5 and 2 m): the
    coarsest one not coarser than the working grid is used, cached in
    <folder>/<res>m/<year>_<E>-<N>.tif as published. Every file is checked against the
    sha256 of its item (file:checksum). The index answers (items per 0.25° tile) are
    cached and updated like a sheet index, so a newer survey of a tile replaces the
    older one. A CachedIndex of StacItems with NewestPerSheet per resolution, read by
    Download with the checksums.
    """

    def __init__(self, description: str, api: str, collection: str, folder: str, crs: str,
                 sizes: Dict[float, float], tile_m: float = 1000):
        """sizes: bytes per tile of every resolution used."""
        super().__init__(description, f"{api}/collections/{collection}/items", collection, folder,
                         native_res=min(sizes), bytes_per_tile=max(sizes.values()))
        self.index_crs, self.crs, self.sizes, self.tile_m = crs, crs, sizes, tile_m
        self.index = CachedIndex(description, StacItems(self.index_url, crs, sizes, tile_m),
                                 NewestPerSheet(folder, crs, self.native_res, sizes), collection,
                                 folder.split("/")[0])
        self.reader = Download(description, self._url_of, self._label, binary_types=("tiff", "octet"),
                               sha256=self._sha256)

    @staticmethod
    def _url_of(tile) -> str:
        return tile.url

    @staticmethod
    def _label(tile) -> str:
        return f"tile {tile.godlo} ({tile.year})"

    @staticmethod
    def _sha256(tile) -> Optional[str]:
        return tile.sha256

    def res_for(self, grid: Grid) -> float:
        """The resolution used for a grid: the coarsest one not coarser than the grid."""
        return self.index.versions.res_for(grid)

    def estimate(self, grid: Grid, cache_dir: str, update: Optional[str]) -> Tuple[int, int, float]:
        self._use(cache_dir, update)
        if self.tiles(grid) is None:
            return super().estimate(grid, cache_dir, update)
        missing = self.missing(grid, cache_dir, update)
        return len(self.tiles(grid)), len(missing), sum(self.sizes[t.res] for t in missing) / 1e6
