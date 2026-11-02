"""New Zealand: LINZ's national 1 m DEM and DSM composites, read in blocks from their Topo50 sheets on the
nz-elevation bucket (Registry of Open Data on AWS, no key); LINZ's contour-interpolated 8 m DEM fills their
gaps."""

from typing import List

from ..credit import Credit
from ..source import ReadmeRow, Source
from ..layers.fileblocks import FileBlocks

# NZTM2000, the CRS of the files: one transverse Mercator for the main islands (173° E, scale 0.9996), so its
# scale error stays within about -0.04 % (Castle Hill -0.03 %) and +0.15 % (the Darrans, Fiordland)
NZTM = "EPSG:2193"

# LINZ's national composites "New Zealand LiDAR 1m DEM" and "... 1m DSM" (the newest survey of each place,
# 2008-2026) on the bucket nz-elevation: one cloud-optimized GeoTIFF per Topo50 sheet of 24 x 36 km
# (24 000 x 36 000 px, float32, LERC with a Z error of 1 mm, 512 px tiles, nodata -9999; the sea is nodata),
# NZTM2000 with NZVD2016 heights, pixel edges on whole metres; 424 sheets each (2026-11-02), read in windows by
# HTTP range requests. A sheet without a file answers 404 and its blocks are missing. LINZ rewrites a sheet in
# place when a new survey is added to it (S3 Last-Modified of 2024-12 to 2026-09 side by side), so the cache
# folders are "live": cache update reads their blocks again after cache.TTL_DAYS["live"]. No request limits
# published (the registry: "No AWS account required").
NZ_ELEVATION = "https://nz-elevation.s3.ap-southeast-2.amazonaws.com/new-zealand"
# LINZ is the licensor of the composites and of the 8 m DEM (its attribution page and the STAC collections'
# providers); the page asks for "Sourced from LINZ. CC BY 4.0" in web applications with a link to it (the
# map links the licence to url)
LINZ_ATTRIBUTION_PAGE = ("https://www.linz.govt.nz/products-services/data/licensing-and-using-data/"
                         "attributing-elevation-or-aerial-imagery-data")
LINZ_ATTRIBUTION = "Sourced from LINZ. CC BY 4.0"


def _linz_credit(data: str, title: str) -> Credit:
    return Credit(data, LINZ_ATTRIBUTION, "CC BY 4.0", LINZ_ATTRIBUTION_PAGE,
                  notice=f"{title}: sourced from the LINZ Data Service and licensed by Toitū Te Whenua Land "
                         "Information New Zealand for re-use under the Creative Commons Attribution 4.0 "
                         "International licence.")


LIDAR_CREDIT = _linz_credit("New Zealand LiDAR 1m DEM / DSM (LINZ)",
                            "New Zealand LiDAR 1m DEM and New Zealand LiDAR 1m DSM")
CONTOUR_CREDIT = _linz_credit("New Zealand Contour-Interpolated 8m DEM (LINZ)",
                              "New Zealand Contour-Interpolated 8m DEM")

# The Topo50 sheet division: sheets of 24 km (east) x 36 km (north) from the north-west corner (988 000,
# 6 810 000) of NZTM2000, named by their row from the north as two letters of SHEET_LETTERS (BW: row 44) and
# their column from the west as two digits (BW21 Castle Hill, BQ31 Wellington). It names every sheet of the
# collections (tests/test_new_zealand.py). The Chatham Islands lie in another CRS (NZTM is not theirs) and are
# left out (the source's bbox).
SHEET_ORIGIN = (988000, 6810000)
SHEET_SIZE = (24000, 36000)
SHEET_LETTERS = "ABCDEFGHJKLMNPQRSTUVWXYZ"


def topo50_sheet(e: int, n: int) -> str:
    """The name of the Topo50 sheet holding the point (e, n) of NZTM2000 in whole metres (a sheet holds its
    west and south edges); "" outside the division."""
    column = (e - SHEET_ORIGIN[0]) // SHEET_SIZE[0]
    row = (SHEET_ORIGIN[1] - 1 - n) // SHEET_SIZE[1]
    if not (0 <= column <= 99 and 0 <= row < len(SHEET_LETTERS) ** 2):
        return ""
    return f"{SHEET_LETTERS[row // len(SHEET_LETTERS)]}{SHEET_LETTERS[row % len(SHEET_LETTERS)]}{column:02d}"


def sheet_files(folder: str, block_m: int, origin=(0, 0)):
    """The file of a block of block_m from origin (its edges on the sheets' edges, so a block lies inside one
    sheet): the sheet holding its lower-left corner, in folder of the bucket. The survey years are not in the
    files (0)."""
    def files(i: int, j: int):
        name = topo50_sheet(i * block_m + origin[0], j * block_m + origin[1])
        return [(name, f"{NZ_ELEVATION}/{folder}/{name}.tiff", 0)] if name else []
    return files


# Blocks of 1 km (1000 x 1000 px, 4-9 of the files' 512 px tiles): about 2.5 MB each
BLOCK_M = 1000
NZ_DEM = FileBlocks("LINZ LiDAR 1 m DEM (terrain)", "new_zealand/dem1m/live", NZTM, 1.0, BLOCK_M,
                    sheet_files("new-zealand/dem_1m/2193", BLOCK_M), bytes_per_tile=2.5e6)
NZ_DSM = FileBlocks("LINZ LiDAR 1 m DSM (trees, buildings)", "new_zealand/dsm1m/live", NZTM, 1.0, BLOCK_M,
                    sheet_files("new-zealand/dsm_1m/2193", BLOCK_M), bytes_per_tile=2.5e6)
# The 8 m DEM interpolated from the 20 m contours of the Topo50 map (Geographx for LINZ, 2012; LINZ: "Suitable
# for cartographic visualisation purposes only. Not suitable for terrain analysis."): only the gaps of the
# 1 m DEM. The same sheets (3000 x 4500 px, LERC, nodata -9999; 449 of them), never rewritten ("completed").
# Blocks of 4 km (500 x 500 px) from (0, 2000): the largest whose edges stay on the sheets' edges
CONTOUR_BLOCK_M, CONTOUR_ORIGIN = 4000, (0, 2000)
NZ_DEM_8M = FileBlocks("LINZ contour-interpolated 8 m DEM (terrain)", "new_zealand/dem8m/2012", NZTM, 8.0,
                       CONTOUR_BLOCK_M, sheet_files("new-zealand-contour/dem_8m/2193", CONTOUR_BLOCK_M,
                                                    CONTOUR_ORIGIN),
                       origin=CONTOUR_ORIGIN, bytes_per_tile=1e6)

# The main islands with Stewart Island and the near islands (the Chatham Islands, the Kermadecs and the
# subantarctic islands are not on the NZTM sheets): --source auto takes the source only here
NZ_BOX = (-47.6, -34.0, 166.0, 178.9)
NZ_NOTE = ("Data: LINZ, CC BY 4.0. Only the main islands with Stewart Island (not the Chatham Islands). The "
           "national 1 m models join the newest survey of each place (2008-2026); where there is no lidar "
           "survey yet (parts of Fiordland, the Darrans among them) the gaps are filled from LINZ's 8 m DEM "
           "interpolated from contours, which is not reliable for lines.")


SOURCES: List[Source] = [
    Source(
        id="new_zealand", name="LINZ (New Zealand LiDAR 1m DEM / DSM)",
        description="LINZ (New Zealand): national 1 m lidar DEM and DSM, the newest survey of each place "
                    "(2008-2026), NZTM2000, NZVD2016 heights; gaps from the contour-interpolated 8 m DEM",
        # The sheets read in blocks on their own pixels, so the working grid is NZTM2000 too
        nmt=NZ_DEM, nmpt=NZ_DSM, countries=("nz",), bbox=NZ_BOX, crs=NZTM, credits=(LIDAR_CREDIT,),
        fallback="nz8m",
        listing=ReadmeRow("New Zealand (main islands)", "LINZ LiDAR 1m DEM (national composite)",
                          "LINZ LiDAR 1m DSM (national composite)", "– (LINZ Basemaps needs a key)"),
        offline=(("nz", NZ_BOX),), sample=(-43.2280, 171.7180),
        note=NZ_NOTE),
    Source(
        id="nz8m", name="LINZ (New Zealand 8m DEM)",
        description="LINZ (New Zealand): DEM 8 m interpolated from the 20 m contours of the Topo50 map (2012), "
                    "NZTM2000",
        nmt=NZ_DEM_8M, crs=NZTM, credits=(CONTOUR_CREDIT,),
        note="Data: LINZ, CC BY 4.0. The 8 m DEM is interpolated from contours (LINZ: suitable for cartographic "
             "visualisation only): lines from it are not reliable.",
        listing=ReadmeRow("New Zealand (main islands)", "LINZ contour-interpolated 8m DEM (2012)"),
        sample=(-43.2280, 171.7180)),
]
