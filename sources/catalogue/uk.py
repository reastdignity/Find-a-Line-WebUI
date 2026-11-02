"""The United Kingdom by region: England (Environment Agency's LIDAR Composite, WCS), Wales (Welsh Government's
LiDAR 2020-22, one national COG each) and Scotland (the Scottish Remote Sensing Portal's 0.5 m collections in an
open S3 bucket, composed newest first)."""

from typing import List

from ..credit import Credit
from ..source import ReadmeRow, Source
from ..indexes.osgrid import os_prefixes, os_tile_extent
from ..layers.fileblocks import FileBlocks
from ..layers.s3blocks import S3Blocks
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
# No attribution is stated in the metadata (Copyright: None): the OGL v3.0's default sentence for a provider
# that names none
WALES_CREDIT = Credit("Welsh Government LiDAR 2020-22 DTM / DSM 1 m (DataMapWales)",
                      "Contains public sector information licensed under the Open Government Licence v3.0", *OGL)


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
# Defra's Data Services Platform Fair Use Policy, §7: "Clearly indicate if you have modified the original data"
EA_CREDIT = Credit("LIDAR Composite DTM / First Return DSM 2022, 1 m (Environment Agency, England)",
                   "© Environment Agency copyright and/or database right 2022. All rights reserved. "
                   "Modified: resampled onto the working grid.", *OGL)


def _england(service: str, coverage: str, kind: str, description: str) -> WcsTiles:
    return WcsTiles(description, f"{EA_WCS}/{service}/wcs", coverage, BNG, f"england/lidar-composite-{kind}/2022",
                    native_res=1.0, fetch_res=1.0, axes=("E", "N"))


NO_ORTHO = "– (no open orthophoto)"

# Scotland: the Scottish Remote Sensing Portal's open bucket (Scottish Government and JNCC, an AWS Open Data
# Sponsorship bucket listable anonymously: ListObjectsV2), lidar/<collection>/<dtm|dsm>/27700/gridded/<OS 1 km
# tile>_50cm_<DTM|DSM>_<suffix>.tif. Only the three collections of 1 km files at 0.5 m in British National Grid
# (no vertical CRS named: ODN on the mainland, the islands' datums unchecked), composed newest first per 1 km
# block (the years of their flights, from the portal's catalogue, api.remotesensing.data.gov.scot, read
# 2026-11-02): the coastal survey of 17 Feb - 31 Mar 2026 (256 px tiles, nodata -9999), the National LiDAR
# Programme flown from 19 May 2025 (COGs, LZW, nodata -32767; tiles at the coast clipped to their data; released
# in parts every six months or so, about 10 % of Scotland in 2026-10) and Orkney Islands Council's of June 2023
# (uncompressed strips, PixelIsPoint with corners on whole metres). They overlap where the coastal survey meets
# the programme (203 tiles of the DTM). Never the files' overviews (the programme's are no 2 x 2 means); about
# 16-20 MB read a km². Phases 1-6 (1 m and 0.5 m, 2011-2019), the Outer Hebrides 2019 and HES's surveys are left
# out (other tilings, odd pixel sizes, non-commercial licences). No published request limits (S3's own per-prefix
# rates only). The portal re-uploads files (the programme's in 2026-04 and 2026-09): a file's ETag is in its name,
# so the folders need no date.
SCT_BUCKET = "https://srsp-open-data.s3.eu-west-2.amazonaws.com"
SCT_COLLECTIONS = (("lidar/coastal/coastal-2025-2026/{}/27700/gridded/", 2026),
                   ("lidar/national-lidar-programme/{}/27700/gridded/", 2025),
                   ("lidar/orkney-islands-council-23/{}/27700/gridded/", 2023))
# The catalogue's use constraints: the programme's "The following attribution statement must be used to
# acknowledge the source of the information: Crown copyright Scottish Government © Crown copyright and database
# right (2025)." (the coastal survey's is its first part); Orkney's names only the OGL v3.0, whose default sentence
# follows
SCT_CREDIT = Credit("Scottish LiDAR: National LiDAR Programme 2025, Coastal LiDAR Survey 2025-26, Orkney Islands "
                    "Council 2023 (DTM / DSM 0.5 m, Scottish Remote Sensing Portal)",
                    "Crown copyright Scottish Government © Crown copyright and database right (2025); Orkney "
                    "Islands Council LiDAR 2023: contains public sector information licensed under the Open "
                    "Government Licence v3.0", *OGL)


def _scotland(kind: str, description: str) -> S3Blocks:
    # Blocks of 1 km on the files' own tiles (2000 x 2000 px)
    return S3Blocks(description, SCT_BUCKET, tuple((c.format(kind), year) for c, year in SCT_COLLECTIONS),
                    f"srsp-{kind}", f"scotland/srsp-{kind}", BNG, 0.5, 1000, 16e6, os_prefixes, _sct_extent)


def _sct_extent(stem: str):
    """The 1 km square of a file (<tile>_50cm_...): None for any other name."""
    tile = stem.split("_", 1)[0]
    extent = os_tile_extent(tile) if len(tile) == 6 else None
    return extent if extent and extent[2] - extent[0] == 1000 else None

SOURCES: List[Source] = [
    # Scotland and Wales first: their offline boxes win where they overlap England's
    Source(
        id="scotland", name="Scottish LiDAR (DTM / DSM 0.5 m)",
        description="Scottish Government LiDAR (Scottish Remote Sensing Portal): the National LiDAR Programme "
                    "2025, the coastal survey 2025-26 and Orkney 2023, terrain and surface models 0.5 m, newest "
                    "first, British National Grid, ODN heights",
        nmt=_scotland("dtm", "Scottish LiDAR DTM 0.5 m (terrain)"),
        nmpt=_scotland("dsm", "Scottish LiDAR DSM 0.5 m (trees, buildings)"),
        countries=("gb",), regions=("gb-sct",), crs=BNG, credits=(SCT_CREDIT,),
        neighbours=("england",),
        listing=ReadmeRow("Scotland (GB)", "Scottish LiDAR DTM 2023-2026, 0.5 m (about 10 % of Scotland)",
                          "Scottish LiDAR DSM, 0.5 m", NO_ORTHO),
        # The mainland and islands north of England's box, Kintyre and Islay west of it, Galloway west of 3.6° W
        # (Cumbria's coast, the Isle of Man and Northern Ireland outside)
        offline=(("gb-sct", (55.82, 60.86, -8.65, -0.73)), ("gb-sct", (55.35, 55.82, -8.65, -5.85)),
                 ("gb-sct", (54.63, 55.82, -5.85, -3.6))),
        sample=(55.636, -5.206),
        note="Scotland's 0.5 m LiDAR covers about a tenth of Scotland so far (Galloway, Kintyre, Arran, Islay, the "
             "coasts of Fife, Angus and Aberdeenshire, the Small Isles, Coll, Tiree, Orkney, parts of the north "
             "coast; more is released about every six months): elsewhere FABDEM fills the search. Data: Scottish "
             "Government, OGL v3.0. No open orthophoto of Scotland: the map shows its own base layers."),
    Source(
        id="wales", name="Welsh Government LiDAR (DTM / DSM)",
        description="Welsh Government LiDAR 2020-22, terrain and surface models 1 m, British National Grid, "
                    "ODN heights",
        nmt=_wales("dtm", "Welsh LiDAR DTM 1 m (terrain)"), nmpt=_wales("dsm", "Welsh LiDAR DSM 1 m (trees, buildings)"),
        countries=("gb",), regions=("gb-wls",), crs=BNG, credits=(WALES_CREDIT,),
        neighbours=("england",),
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
        neighbours=("wales", "scotland"),
        listing=ReadmeRow("England (GB)", "Environment Agency LIDAR Composite DTM 2022, 1 m",
                          "EA LIDAR Composite First Return DSM 2022, 1 m", NO_ORTHO),
        offline=(("gb-eng", (49.85, 55.82, -5.75, 1.77)),), sample=(53.3569, -1.6484),
        note="Data: Environment Agency, OGL v3.0. The composite merges surveys of 2000-2022 (about 99 % of "
             "England); no open orthophoto of England: the map shows its own base layers."),
]
