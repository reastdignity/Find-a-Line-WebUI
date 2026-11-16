"""PackageTiles: 1 km tiles that are members of a province's package ZIPs in several UTM zones, listed through a
FeatureServer of the packages' footprints and read one member at a time by HTTP Range (Ontario's DTM and DSM,
Lidar-Derived)."""

import threading
from typing import Dict, Optional, Tuple

import requests
from rasterio.transform import Affine
from rasterio.warp import transform_bounds

from grid import Grid

from ..indexes.packages import (TILE_M, PackageIndex, PackageListing, PackageTile, PackageVersions, forget_answers,
                                package_years)
from ..readers.zipmember import ZipMember
from .indexed import IndexedTiles

# How far a member's origin and size may lie off its tile's box, in pixels (float noise of the files' transforms)
PLACE_TOLERANCE_PX = 1e-3


class PackageMember(ZipMember):
    """ZipMember for the tiles of PackageVersions: written in the CRS of the tile's zone (the files name it in
    other ways: EPSG:26917 for NAD83(CSRS) in ERDAS Imagine files, a compound CRS with CGVD2013 in GeoTIFFs), and
    refused unless the member covers its tile's 1 km box exactly as GDAL places it (a "PixelIsPoint" file with
    its tie point at the first pixel's centre lands on the box; one with the tie point at the corner would lie
    half a pixel off and is never cached)."""

    def placed(self, transform: Affine, width: int, height: int, request, where: str):
        if transform.b != 0 or transform.d != 0 or transform.a <= 0 or transform.e >= 0:
            raise RuntimeError(f"{where}: not a north-up raster ({transform})")
        res = transform.a
        x, y = request.east * TILE_M, (request.north + 1) * TILE_M
        off = max(abs(transform.c - x), abs(transform.f - y), abs(width * res - TILE_M),
                  abs(height * -transform.e - TILE_M)) / res
        if abs(transform.e + res) / res > PLACE_TOLERANCE_PX or off > PLACE_TOLERANCE_PX:
            raise RuntimeError(f"{where}: the member lies off its tile's box ({transform}, {width} x {height} px; "
                               f"the box's corner {x}, {y})")


class PackageTiles(IndexedTiles):
    """1 km tiles of a province's lidar models, each a member (a GeoTIFF or an ERDAS Imagine file) of one of the
    package ZIPs its FeatureServer lists (featureserver: the layer of the packages' footprints; packages: the
    folder all package links must lie in), in NAD83(CSRS) / UTM of the zone its name gives (zones: zone ->
    EPSG code). dates: each project's end of acquisition (ISO), which orders the surveys of a place (the newest
    wins whole: PackageVersions); exclude: members left out (a copy in another height datum). The packages over a
    0.25° tile and their directories are kept for ttl_days (PackageListing); a member is read by one Range of its
    local header and data (PackageMember) and known by its CRC-32. Cached in
    <folder>/epsg<code>/<east // 10>_<north // 10>/<east>_<north>_<year>_<crc8>.tif at the member's own resolution.

    A 404 of a package or a member not where its directory said makes that package's directory be read again
    and the member tried once more from there (the 0.25° answers are forgotten then)."""

    def __init__(self, description: str, featureserver: str, packages: str, folder: str, prefix: str,
                 zones: Dict[int, str], dates: Dict[str, str], exclude: Optional[str] = None,
                 native_res: float = 0.5, bytes_per_tile: float = 9e6, ttl_days: float = 60):
        super().__init__(description, featureserver, prefix, folder, native_res=native_res,
                         bytes_per_tile=bytes_per_tile)
        self.featureserver, self.packages, self.zones, self.dates = featureserver, packages, dict(zones), dict(dates)
        self.index_crs = ""  # every listed tile names its zone's CRS
        top = folder.split("/")[0]
        self.listing = PackageListing(featureserver, packages, zones, dates, top, prefix, native_res, exclude,
                                      ttl_days)
        self.index = PackageIndex(description, self.listing, PackageVersions(folder), prefix, top, ttl_days=ttl_days)
        self.reader = PackageMember(description, renew=self._renew)
        self._renew_lock = threading.Lock()

    def _renew(self, tile: PackageTile) -> Optional[PackageTile]:
        """After a 404 or a moved member: the member where its package's directory, read again now, says it is
        (None when it says the same, or lists it no more, or its CRC-32 changed: the tile's key is its CRC-32)."""
        cache_dir = self.index.cache_dir
        if not cache_dir:
            return None
        self.listing.cache_dir = cache_dir
        with self._renew_lock:
            try:
                kept = self.listing.directory(tile.url, force=True, slot=False)  # the download holds a slot
            except requests.RequestException as e:
                print(f"{self.description}: the package's directory cannot be read again ({type(e).__name__})")
                return None
            forget_answers(cache_dir, self.listing.top, self.prefix)
            self.index._listed.clear()
        for name, method, flags, crc, size, usize, offset in kept["members"]:
            if name == tile.member and crc == tile.crc and (offset, kept["length"]) != (tile.offset, tile.length):
                return PackageTile(tile.crs, tile.east, tile.north, tile.year, tile.key, tile.date, tile.project,
                                   tile.url, name, offset, method, flags, crc, size, usize, kept["length"])
        return None

    def bounds_wgs84(self, tile) -> Tuple[float, float, float, float]:
        x, y = tile.east * TILE_M, tile.north * TILE_M
        return transform_bounds(tile.crs, "EPSG:4326", x, y, x + TILE_M, y + TILE_M)

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
        years = package_years(self.files(grid, cache_dir))
        info["survey_years"] = [min(years), max(years)] if years else None
        return info
