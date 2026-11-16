"""PackageTiles: 1 km tiles that are members of a province's package ZIPs in several UTM zones, listed through a
FeatureServer of the packages' footprints and read one member at a time by HTTP Range (Ontario's DTM and DSM,
Lidar-Derived)."""

import threading
from dataclasses import replace
from typing import Dict, Optional, Tuple

import requests
from rasterio.transform import Affine
from rasterio.warp import transform_bounds
from rasterio.windows import Window

from grid import Grid

from ..indexes.packages import (TILE_M, PackageIndex, PackageListing, PackageTile, PackageVersions, forget_answers,
                                package_years)
from ..layer import Fetched
from ..readers.zipmember import MEMBER_REMADE, WrongShape, ZipMember
from .indexed import IndexedTiles

# How far a member's origin and size may lie off its tile's box, in pixels (float noise of the files' transforms)
PLACE_TOLERANCE_PX = 1e-3


class MemberRefused(RuntimeError):
    """A member that does not lie on its tile's box (PackageMember.placed): what its bytes say, so it is the same
    on every reading."""


class PackageMember(ZipMember):
    """ZipMember for the tiles of PackageVersions: written in the CRS of the tile's zone (the files name it in
    other ways: EPSG:26917 for NAD83(CSRS) in ERDAS Imagine files, a compound CRS with CGVD2013 in GeoTIFFs), on its
    tile's 1 km box exactly: a member reaching beyond it on the same pixels is cut to it (LEAP 2009's DSM members:
    1.2 km, 100 m around their tile), the transform's float noise is dropped (Muskoka's 627999.9999999998), and a
    member that does not cover the box on whole pixels is refused ("PixelIsPoint" files with their tie point at the
    first pixel's centre land on the box as GDAL places them; one with the tie point at the corner would lie half a
    pixel off). A refused member (off its box, more than one band) is never cached: its tile is "missing" (one
    warning naming the package, the member and the reason), so the source's gap filler fills it and the search goes
    on. The tile's path carries the member's CRC-32, so the same bytes are not asked again; a changed member is
    another tile, and a change of this rule changes the layer's `processing`, which asks the missing tiles again."""

    def fetch(self, request, path: str) -> Fetched:
        try:
            return super().fetch(request, path)
        except MemberRefused as e:
            print(f"{self.description}: tile {request.godlo} left to the gap filler: package "
                  f"{request.url.rsplit('/', 1)[-1]}, member {request.member}: {e}")
            return Fetched(0, request.url)

    def _write(self, data: bytes, path: str, where: str, request=None):
        """ZipMember's, a member of more than one band refused as one off its box (what its bytes are: the read,
        network and CRC-32, is done before). One GDAL cannot open or read stays that tile's error in this search,
        never recorded (a GDAL fault may be this PC's)."""
        try:
            super()._write(data, path, where, request)
        except WrongShape as e:
            raise MemberRefused(str(e).replace(f"{where}: ", "", 1)) from None

    def placed(self, transform: Affine, width: int, height: int, request,
               where: str) -> Tuple[Affine, Optional[Window]]:
        if transform.b != 0 or transform.d != 0 or transform.a <= 0 or transform.e >= 0:
            raise MemberRefused(f"not a north-up raster ({transform})")
        res = round(transform.a, 6)
        size = TILE_M / res
        x, y = request.east * TILE_M, (request.north + 1) * TILE_M
        col, row = (x - transform.c) / res, (transform.f - y) / res
        whole = [abs(v - round(v)) for v in (col, row, size)]
        if (max(whole) > PLACE_TOLERANCE_PX or abs(transform.a - res) * width > PLACE_TOLERANCE_PX * res
                or abs(-transform.e - res) * height > PLACE_TOLERANCE_PX * res or round(col) < 0 or round(row) < 0
                or round(col) + round(size) > width or round(row) + round(size) > height):
            raise MemberRefused(f"the member lies off its tile's box ({transform}, {width} x {height} px; "
                                f"the box's corner {x}, {y})")
        exact = Affine(res, 0.0, float(x), 0.0, -res, float(y))
        if (round(col), round(row), width, height) == (0, 0, round(size), round(size)):
            return exact, None
        return exact, Window(round(col), round(row), round(size), round(size))


class PackageTiles(IndexedTiles):
    """1 km tiles of a province's lidar models, each a member (a GeoTIFF or an ERDAS Imagine file) of one of the
    package ZIPs its FeatureServer lists (featureserver: the layer of the packages' footprints; packages: the
    folder all package links must lie in), in NAD83(CSRS) / UTM of the zone its name gives (zones: zone ->
    EPSG code). dates: each project's end of acquisition (ISO), which orders the surveys of a place (the newest
    first, an older one filling its holes where the newest's member is much smaller: PackageVersions); exclude:
    members left out (a copy in another height datum). The packages over a
    0.25° tile and their directories are kept for ttl_days (PackageListing); a member is read by one Range of its
    local header and data (PackageMember) and known by its CRC-32. Cached in <folder>/epsg<code>/<east // 10>_<north
    // 10>/<east>_<north>_<year>_<date8>_<size>_<crc8>.tif (the project's date and the member's compressed size order
    the cached tiles as the listed ones) at the member's own resolution.

    A 404 of a package, a member not where its directory said or not what it said (its CRC-32) makes that
    package's directory be read again and the member tried once more from there (a member the directory now lists
    with another CRC-32 fails at once: _renew); the 0.25° answers are forgotten then, also when the package cannot
    be read again (renamed or removed: the next search lists anew)."""

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

    def _renew(self, tile: PackageTile):
        """After a 404, a moved or a changed member: the member where its package's directory, read again now, says
        it is; MEMBER_REMADE when the directory lists it with another CRC-32 or another compressed size (the tile's
        cached name holds both: the remade or recompressed member is another tile, which the next search lists and
        reads, so this one fails at once instead of asking the old bytes again or writing the new under the old
        name); None when it says the same, lists it no more or the package cannot be read again. The 0.25° answers are forgotten either way, so the next search lists the packages anew (a
        renamed package under its new name). The download holds a tile's lock and a slot of the host: the
        directory's own lock comes last, as everywhere."""
        cache_dir = self.index.cache_dir
        if not cache_dir:
            return None
        self.listing.cache_dir = cache_dir
        with self._renew_lock:
            try:
                kept = self.listing.directory(tile.url, force=True, slot=False)  # the download holds a slot
            except (requests.RequestException, RuntimeError) as e:
                print(f"{self.description}: the package {tile.url.rsplit('/', 1)[-1]} cannot be read again "
                      f"({type(e).__name__}); the next search lists the packages anew")
                kept = None
            forget_answers(cache_dir, self.listing.top, self.prefix)
            self.index._listed.clear()
        if kept is None:
            return None
        for name, method, flags, crc, size, usize, offset in kept["members"]:
            if name != tile.member:
                continue
            if (crc, size) != (tile.crc, tile.size):
                return MEMBER_REMADE
            if (offset, kept["length"]) != (tile.offset, tile.length):
                return replace(tile, offset=offset, method=method, flags=flags, usize=usize, length=kept["length"])
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
