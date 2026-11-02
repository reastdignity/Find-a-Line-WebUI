"""MetalinkTiles: square tiles of a download service listed in Metalink documents (LDBV Bavaria, LVermGeo RP)."""

from typing import Dict, Optional, Sequence, Tuple

from grid import Grid

from ..indexes.metalink import MetalinkFiles, MetalinkIndex, ShaPerTile, years_of
from ..readers.download import Download
from .indexed import IndexedTiles


class MetalinkTiles(IndexedTiles):
    """Square tiles of tile_m on a metric grid, whole files of a download service listed in Metalink
    documents (RFC 5854) that cover the region: name, a regular expression of the file names with
    the groups east and north (in tile_m units of crs) and year if they carry one. The documents
    are read once per TTL and kept (MetalinkFiles); each file is checked against its SHA-256, and
    a file is known by it (ShaPerTile: a file replaced in place, or by a newer survey, is read
    again). Cached in <folder>/<east // 10>_<north // 10>/<east>_<north>[_<year>]_<sha8>.tif.

    average and force_crs are Download's average and crs: a file of native_res / average metres
    averaged to native_res (LDBV's DOM20), or written in force_crs's name (LVermGeo RP's DGM1 names
    a compound CRS). bytes_per_tile is the download of a tile, for estimates without the index
    (the listed sizes otherwise)."""

    def __init__(self, description: str, metalinks: Sequence[str], name: str, folder: str, crs: str,
                 prefix: str, native_res: float = 1.0, tile_m: float = 1000, bytes_per_tile: float = 3e6,
                 average: int = 1, force_crs: Optional[str] = None):
        super().__init__(description, metalinks[0], prefix, folder, native_res=native_res,
                         bytes_per_tile=bytes_per_tile)
        self.metalinks, self.name, self.index_crs, self.crs, self.tile_m = tuple(metalinks), name, crs, crs, tile_m
        self.average, self.force_crs = average, force_crs
        self.index = MetalinkIndex(description, MetalinkFiles(metalinks, name, crs, native_res, folder.split("/")[0],
                                                              prefix, tile_m),
                                   ShaPerTile(folder, crs, tile_m), prefix, folder.split("/")[0])
        self.reader = Download(description, self._url_of, self._label, binary_types=("tiff", "octet"),
                               sha256=self._sha256, average=average, crs=force_crs)

    @staticmethod
    def _url_of(tile) -> str:
        return tile.url

    @staticmethod
    def _label(tile) -> str:
        return f"tile {tile.godlo}" + (f" ({tile.year})" if tile.year else "")

    @staticmethod
    def _sha256(tile) -> Optional[str]:
        return tile.sha256

    def bounds_wgs84(self, tile) -> Tuple[float, float, float, float]:
        from rasterio.warp import transform_bounds
        m = self.tile_m
        return transform_bounds(self.crs, "EPSG:4326", tile.east * m, tile.north * m, (tile.east + 1) * m,
                                (tile.north + 1) * m)

    def estimate(self, grid: Grid, cache_dir: str, update: Optional[str]) -> Tuple[int, int, float]:
        self._use(cache_dir, update)
        if self.tiles(grid) is None:
            return super().estimate(grid, cache_dir, update)
        missing = self.missing(grid, cache_dir, update)
        return len(self.tiles(grid)), len(missing), sum(t.size or self._bytes for t in missing) / 1e6

    def source_date(self, tile) -> Optional[str]:
        return str(tile.year) if tile.year else None

    def used(self, grid: Grid, cache_dir: str) -> Dict:
        info = super(IndexedTiles, self).used(grid, cache_dir)
        years = years_of(self.files(grid, cache_dir))
        info["survey_years"] = [min(years), max(years)] if years else None
        return info
