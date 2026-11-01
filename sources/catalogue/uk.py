"""The United Kingdom by region: England (Environment Agency's LIDAR Composite, WCS) and Wales (Welsh Government's
LiDAR 2020-22, one national COG each)."""

from typing import List

from ..credit import Credit
from ..source import ReadmeRow, Source
from ..layers.fileblocks import FileBlocks
from ..layers.wcs import WcsTiles

OGL = ("OGL v3.0", "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/")
# British National Grid (OSGB36, ODN heights) is the CRS of both: its scale error over England and
# Wales stays within -0.04 % (central meridian, 2° W) and +0.05 % (Land's End, the Norfolk coast)
BNG = "EPSG:27700"

# Wales: Welsh Government LiDAR 2020-22 (DataMapWales), one cloud-optimized GeoTIFF per model (float32,
# Deflate, 256 px tiles, nodata -9999, centimetre heights; 191 007 x 233 000 px, about 50 GB each), its
# pixel edges on whole metres. A single release (both files last modified 2024-10-04): a new one would
# replace the files in place, so the folders carry the release's date (a new date here, a new folder).
WALES_RELEASE = "20241004"
WALES_COGS = "https://dmwproductionblob.blob.core.windows.net/cogs/lidar"
WALES_EXTENT = (164993.0, 164000.0, 356000.0, 397000.0)  # the files' bounds: blocks outside make no request
# No attribution is stated in the metadata (Copyright: None); the OGL's own form for the provider
WALES_CREDIT = Credit("Welsh Government LiDAR 2020-22 DTM / DSM 1 m (DataMapWales)",
                      "Contains Welsh Government information licensed under the Open Government Licence v3.0", *OGL)


def _wales(kind: str, description: str) -> FileBlocks:
    # Blocks of 1 km on the file's pixels (25 of its 256 px tiles at most: they start at 164 993 m), about
    # 2 MB each
    return FileBlocks(description, f"wales/lidar-{kind}/{WALES_RELEASE}", BNG, 1.0, 1000,
                      f"{WALES_COGS}/wales_{kind}_32bit_cog.tif", extent=WALES_EXTENT, year=2022,
                      bytes_per_tile=2e6)


# England: the Environment Agency's LIDAR Composite 2022 (surveys of 2000-2022 merged, newest on top) through
# its WCS 2.0.1 (axes E and N; GeoTIFF float32 on the coverage's pixels, edges on whole metres, nodata
# -3.4e38; millimetre heights). Tiles of 2 km on the native grid, 16.8 MB uncompressed in about 2 s
# (geotiff:compression=Deflate gives 10.4 MB but takes longer to make). The composite is not updated.
EA_WCS = "https://environment.data.gov.uk/spatialdata"
EA_CREDIT = Credit("LIDAR Composite DTM / First Return DSM 2022, 1 m (Environment Agency, England)",
                   "© Environment Agency copyright and/or database right 2022. All rights reserved.", *OGL)


def _england(service: str, coverage: str, kind: str, description: str) -> WcsTiles:
    return WcsTiles(description, f"{EA_WCS}/{service}/wcs", coverage, BNG, f"england/lidar-composite-{kind}/2022",
                    native_res=1.0, fetch_res=1.0, axes=("E", "N"))


NO_ORTHO = "– (no open orthophoto)"

SOURCES: List[Source] = [
    # Wales first: its offline box wins where it overlaps England's
    Source(
        id="wales", name="Welsh Government LiDAR (DTM / DSM)",
        description="Welsh Government LiDAR 2020-22, terrain and surface models 1 m, British National Grid, "
                    "ODN heights",
        nmt=_wales("dtm", "Welsh LiDAR DTM 1 m (terrain)"), nmpt=_wales("dsm", "Welsh LiDAR DSM 1 m (trees, buildings)"),
        countries=("gb",), regions=("gb-wls",), crs=BNG, credits=(WALES_CREDIT,),
        listing=ReadmeRow("Wales (GB)", "Welsh Government LiDAR 2020-22 DTM, 1 m", "Welsh Government LiDAR DSM, 1 m",
                          NO_ORTHO),
        offline=(("gb-wls", (51.33, 53.45, -5.35, -2.64)),), sample=(53.0917, -4.0488),
        note="Data: Welsh Government, OGL v3.0. No open orthophoto of Wales: the map shows its own base layers."),
    Source(
        id="england", name="Environment Agency LIDAR Composite (DTM / DSM)",
        description="Environment Agency LIDAR Composite 2022 (surveys of 2000-2022), terrain and first-return "
                    "surface models 1 m, British National Grid, ODN heights",
        nmt=_england("lidar-composite-digital-terrain-model-dtm-1m",
                     "13787b9a-26a4-4775-8523-806d13af58fc__Lidar_Composite_Elevation_DTM_1m", "dtm",
                     "EA LIDAR Composite DTM 1 m (terrain)"),
        nmpt=_england("lidar-composite-digital-surface-model-first-return-dsm-1m",
                      "df4e3ec3-315e-48aa-aaaf-b5ae74d7b2bb__Lidar_Composite_Elevation_FZ_DSM_1m", "dsm",
                      "EA LIDAR Composite First Return DSM 1 m (trees, buildings)"),
        countries=("gb",), regions=("gb-eng",), crs=BNG, credits=(EA_CREDIT,),
        listing=ReadmeRow("England (GB)", "Environment Agency LIDAR Composite DTM 2022, 1 m",
                          "EA LIDAR Composite First Return DSM 2022, 1 m", NO_ORTHO),
        offline=(("gb-eng", (49.85, 55.82, -5.75, 1.77)),), sample=(53.3569, -1.6484),
        note="Data: Environment Agency, OGL v3.0. The composite merges surveys of 2000-2022 (about 99 % of "
             "England); no open orthophoto of England: the map shows its own base layers."),
]
