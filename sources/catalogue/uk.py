"""The United Kingdom by region: England (Environment Agency's LIDAR Composite, WCS), Wales (Welsh Government's
LiDAR 2020-22, one national COG each), Scotland (the Scottish Remote Sensing Portal's 0.5 m collections in an
open S3 bucket, composed newest first) and Northern Ireland's coast (DAERA's 2021 coastal survey DTM, an Esri
elevation tile cache)."""

import json
import os
from typing import List

from ..credit import Credit
from ..source import Coverage, ReadmeRow, Source
from ..indexes.osgrid import os_prefixes, os_tile_extent
from ..layers.fileblocks import FileBlocks
from ..layers.lerc import LercTiles
from ..layers.zipsheets import ZipSheetTiles
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
# The service answers HTTP 500 ({"message":"Internal server error"}, application/json) for any GetCoverage box
# not wholly covered by its granules, which follow England's outline (Wales and the open sea beyond a line are
# absent, while DescribeCoverage gives a rectangle: E 80000-656000, N 4000-665000 for the DTM, E 133000-656000,
# N 11000-657601 for the DSM), also for a box straddling that rectangle's edge; the 500 is positional and
# deterministic, the service up meanwhile, and transient 500s exist too (a DescribeCoverage answered 500 once
# and 200 six minutes later). Measured 2026-11-08 at Hay-on-Wye (tile 161_121, corner 322000/242000, on the
# Welsh border): the 2 km tile and its four 1000 px quarters answered 500, 500 and 250 px pieces on its English
# side 200 with valid heights, 16 px boxes 500 where 100 px answered 200. So a 500 never makes a tile
# "missing": the tiles are asked again in pieces down to SPLIT_MIN_PX (WcsReader's split_on_error). Where
# granules exist but hold nothing (open sea 20 km off Northumberland, Cardiff) the service answers 0.0 without a
# nodata tag: zero_is_nodata stays False (fill_water takes them as water at sea; over Wales the neighbour fill
# applies only where the grid has no England data), noted in docs/roadmap.md, "To check".
EA_WCS = "https://environment.data.gov.uk/spatialdata"
# Defra's Data Services Platform Fair Use Policy, §7: "Clearly indicate if you have modified the original data"
EA_CREDIT = Credit("LIDAR Composite DTM / First Return DSM 2022, 1 m (Environment Agency, England)",
                   "© Environment Agency copyright and/or database right 2022. All rights reserved. "
                   "Modified: resampled onto the working grid.", *OGL)


def _england(service: str, coverage: str, kind: str, description: str) -> WcsTiles:
    return WcsTiles(description, f"{EA_WCS}/{service}/wcs", coverage, BNG, f"england/lidar-composite-{kind}/2022",
                    native_res=1.0, fetch_res=1.0, axes=("E", "N"), split_on_error=True)


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


# Northern Ireland: DAERA's "2021 NI 3D Coastal Survey - 3D Elevation Layer" (ArcGIS item
# 442cbde42ebe49a3b0d46cd7ce5c8ea2, service Full_NI_Elevation): the bare-earth DTM of the survey's lidar (0.25 m;
# the intertidal zone and about 200 m inland, the whole coast with Lough Foyle, Belfast and Strangford Loughs, Rathlin;
# Fair Head's crag and plateau), published only as an Esri elevation tile cache (LERC1 tiles in Web Mercator, levels
# 0-23, cached to 1:564, lercError 0.1 m: every sample within 0.1 m of the survey's value), no download of the
# rasters ("exportTilesAllowed": false is Esri's export operation; the tiles load without a key). Heights above
# Belfast Lough datum. Read at the level that suits the working grid (17 for 1 m: 0.68 m on the ground at 55° N), at
# most 19 (0.17 m: the first level finer than the data), and reprojected once onto Irish Transverse Mercator: ITM
# (EPSG:2157, IRENET95, i.e. ETRS89, which PROJ takes as WGS84 like Web Mercator's datum) needs no datum shift, while
# the Irish Grid (TM75 or TM65) needs a Helmert shift of about 1 m accuracy; ITM's scale error over Northern Ireland
# stays within about -0.02 % (its central meridian, 8° W) and +0.02 % (the Ards peninsula), and one zone covers it
# all (UTM splits it at 6° W). The cache is DAERA's, not a download service: no published limits (the item, the
# service and OpenDataNI's pages, read 2026-11-15), asked gently (net.HOST_RATES_OF: at most one request a second, as
# the mail to DAERA of 2026-11-15 promises). The service's extent (EPSG:3857): tiles outside it are never asked; the
# cells with data (tools/lerc_coverage.py) decide where the source is chosen and which tiles a search asks. Folder
# live: DAERA may add newer surveys to the layer (the 2022 post-storm models are pictures only so far).
NI_DTM_URL = "https://tiles-eu1.arcgis.com/kswen6BYexuc1SUk/arcgis/rest/services/Full_NI_Elevation/ImageServer"
NI_EXTENT = (-815794.4751765616, 7171282.93937308, -600897.7231999885, 7424282.448916508)
NI_CELLS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "northern_ireland_dtm_cells.npz")
NI_DTM = LercTiles("DAERA 2021 coastal lidar DTM (terrain)", NI_DTM_URL, "northern_ireland/coastal-dtm/live",
                   native_res=0.25, max_level=19, extent=NI_EXTENT, cells=NI_CELLS, near_m=100)
ITM = "EPSG:2157"
# The item's licenseInfo and accessInformation (credits), verbatim (read 2026-11-15)
NI_CREDIT = Credit("2021 NI 3D Coastal Survey, 3D Elevation Layer (DTM 0.25 m; DAERA)",
                   "Department of Agriculture, Environment and Rural Affairs (DAERA), Bluesky; contains public sector "
                   "information licensed under the Open Government Licence v3.0", *OGL)
# Northern Ireland and Rathlin west of 5.85 W, the Antrim coast south of 55.00 N with Islandmagee, Larne, the
# Copelands and the Ards peninsula east of it: the Mull of Kintyre (55.31 N, 5.80 W), Southend and Sanda stay
# Scotland's. Also holding Donegal's Inishowen and Ireland's border counties, which have no source of their own: gb
# there offline, then nothing near in the coastal DTM
NI_BOXES = (("gb-nir", (54.00, 55.32, -8.20, -5.85)), ("gb-nir", (54.00, 55.00, -5.85, -5.40)))

# Northern Ireland, national: OSNI's "OSNI Open Data - 10M DTM" (Land & Property Services, OpenDataNI; "an
# interpolated dataset from the OSNI Enhanced DTM from 2014-2016"), six ZIP archives of 41-51 members, one per
# sheet of OSNI's 10k grid (Sheet<nnn>v<version>.txt; sheets 51-100 under a folder, one name with a space before
# ".txt", sheet 11 also in a member "011a" that lies just west of the sheet's box; no member for sheets 287 and 290):
# "x y z" lines of 10 m cell centres on x5 of the Irish Grid (pixel edges on multiples of 10 m: the grid copies the
# sheets), heights in metres with four decimals above Belfast Lough datum (OSNI's), no points at sea. A member is
# 0.03-4.7 MB deflated (up to 29 MB of text), read by one Range of its archive (sources/layers/zipsheets.py): one to
# four sheets a search. The archives' stable links (CKAN's downloads) redirect to signed URLs of Cloudflare R2 valid
# for 7 days, which answer GET with Range (206) but not HEAD (403): each read resolves the link again. OGL v3.0 (CKAN's
# license_id uk-ogl; no attribution of its own is stated, so the OGL's default sentence). Limits: none published
# (OpenDataNI's packages and terms, read 2026-11-15): two at once (net.HOST_SLOTS_OF). A re-upload changes a member's
# CRC-32, so the cached sheet's name: the folder needs no date (the 51-100 archive was replaced on 2026-01-29).
NI_10M_ARCHIVES = tuple(
    f"https://admin.opendatani.gov.uk/dataset/{package}/resource/{resource}/download/osni_10m_dtm_sheets_{sheets}.zip"
    for package, resource, sheets in (
        ("bea57cd0-c9aa-45cd-b048-3b6d60b04fbe", "2974c9cb-0027-4ee4-9095-02c50b6b73a7", "1-50"),
        ("260f5296-2469-4eea-959d-dbbca9c29c0f", "42604b59-22ca-45d0-9dfe-8b6e961e1961", "51-100"),
        ("64ccceb5-c06c-484d-8b9c-699357fc6b13", "a48821ab-8388-48ef-a9aa-97b8158cbc9b", "101-150"),
        ("adea7269-2a86-4953-94bd-7b4434baba26", "a6392f75-d45a-4d2b-a8e8-678d86419f7a", "151-200"),
        ("e0e15a4a-32a4-4f43-8bb0-1233262fee06", "beddd617-b078-495f-a856-2f1b8d550d59", "201-250"),
        ("93fb6a92-f6eb-4f38-b6db-9ba5b880c02b", "653b468d-f582-4bca-88a7-66a5a4f2b289", "251-293")))
NI_10M_MEMBER = r"(?i)(?:^|/)Sheet(?P<sheet>\d{3})[a-z]?v\d+\s*\.txt$"
# OSNI's 10k grid (its "Coverage Grid - 10K" GeoJSON, read 2026-11-15): the box of each of the 292 sheets, the union
# of its quarters of 4.8 x 3.2 km (Irish Grid metres; edge sheets are halves or quarters), and sheet 293, which the
# grid lacks: the box of its member's 49 points (a beach just west of sheet 1, read 2026-11-15)
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "northern_ireland_10k_sheets.json"),
          encoding="utf-8") as _sheets_file:
    NI_10K_SHEETS = {int(k): tuple(v) for k, v in json.load(_sheets_file).items()}
# The Irish Grid on the 1975 Mapping Adjustment (TM75), OSNI's grid
IRISH_GRID = "EPSG:29903"
NI_10M = ZipSheetTiles("OSNI 10 m DTM (terrain)", NI_10M_ARCHIVES, NI_10M_MEMBER, NI_10K_SHEETS, IRISH_GRID,
                       "northern_ireland/osni-dtm10m", "osni-dtm10m", 10.0, margin=1000.0, bytes_per_tile=3e6)
NI_10M_CREDIT = Credit("OSNI Open Data 10m DTM (Land & Property Services, Ordnance Survey of Northern Ireland)",
                       "Contains public sector information licensed under the Open Government Licence v3.0", *OGL)


def _sct_extent(stem: str):
    """The 1 km square of a file (<tile>_50cm_...): None for any other name."""
    tile = stem.split("_", 1)[0]
    extent = os_tile_extent(tile) if len(tile) == 6 else None
    return extent if extent and extent[2] - extent[0] == 1000 else None

SOURCES: List[Source] = [
    # Northern Ireland first: its offline box holds the Ards peninsula and Islandmagee, which England's box and
    # Scotland's third box hold too. Scotland and Wales next: their offline boxes win where they overlap England's
    Source(
        id="northern_ireland", name="DAERA 2021 coastal lidar DTM (Northern Ireland)",
        description="DAERA's 2021 NI 3D Coastal Survey: the bare-earth DTM of its lidar (0.25 m, the coast and about "
                    "200 m inland) from its elevation tile cache, reprojected onto Irish Transverse Mercator, "
                    "Belfast Lough datum; inland FABDEM",
        nmt=NI_DTM, countries=("gb",), regions=("gb-nir",), crs=ITM, credits=(NI_CREDIT,),
        listing=ReadmeRow("Northern Ireland (GB), its coast",
                          "DAERA 2021 NI 3D Coastal Survey DTM, 0.25 m (elevation tiles)", "–", NO_ORTHO),
        offline=NI_BOXES, sample=(55.2240, -6.1570),  # Fair Head (R74)
        # Its gaps (inland of the survey's strip) from OSNI's 10 m DTM, then FABDEM
        fallback="northern_ireland_10m", more_fallbacks=("europe",),
        # Inland (Belfast's centre, the Mournes, Binevenagh) the DTM's cells hold nothing within about 100 m (the
        # cells are about 350 m on the ground, so 100-450 m): OSNI's 10 m DTM instead
        instead_without_data="northern_ireland_10m",
        note="Data: DAERA, Bluesky, OGL v3.0; OSNI (Land & Property Services), OGL v3.0. The 2021 coastal survey's "
             "DTM covers the coast only (the intertidal zone and about 200 m inland; Fair Head's crag and plateau): "
             "elsewhere OSNI's 10 m DTM fills the search, and a search centred inland uses that alone. Its tiles "
             "hold heights within 0.1 m of the survey's. No surface model: trees and buildings are not in the data.",
        # Partial: the coast only, OSNI's 10 m DTM elsewhere
        coverage=Coverage(provider="DAERA", added="2026-11-15", partial=True, rest=(10.0,), survey="2021")),
    Source(
        id="northern_ireland_10m", name="OSNI 10 m DTM (Northern Ireland)",
        description="OSNI Open Data 10 m DTM (Land & Property Services; interpolated from OSNI's Enhanced DTM of "
                    "2014-2016), sheets of OpenDataNI's archives read by Range, Irish Grid (TM75), Belfast Lough "
                    "datum",
        # Inland Northern Ireland (northern_ireland's instead_without_data) and that source's gaps; chosen by
        # --source auto only through it (no offline boxes of its own: northern_ireland's come first)
        nmt=NI_10M, countries=("gb",), regions=("gb-nir",), crs=IRISH_GRID, default_resolution=10.0,
        credits=(NI_10M_CREDIT,),
        listing=ReadmeRow("Northern Ireland (GB), inland and the coastal DTM's gaps",
                          "OSNI Open Data 10 m DTM (interpolated from the Enhanced DTM 2014-2016)"),
        sample=(55.1100, -6.9150),  # Binevenagh's escarpment (R82)
        note="Data: OSNI (Land & Property Services), OGL v3.0. A 10 m terrain model interpolated from OSNI's "
             "Enhanced DTM of 2014-2016: walls are smoothed and only long lines over big cliffs can be found; no "
             "surface model: trees and buildings are not in the data."),
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
        # Dumfriesshire's east and the Borders up to the English border (they hold Northumberland's north)
        border_boxes=((54.95, 55.2, -3.6, -2.65), (55.2, 55.5, -3.6, -2.15), (55.5, 55.82, -3.6, -2.0)),
        sample=(55.636, -5.206),
        note="Scotland's 0.5 m LiDAR covers about a tenth of Scotland so far (Galloway, Kintyre, Arran, Islay, the "
             "coasts of Fife, Angus and Aberdeenshire, the Small Isles, Coll, Tiree, Orkney, parts of the north "
             "coast; more is released about every six months): elsewhere FABDEM fills the search. Data: Scottish "
             "Government, OGL v3.0. No open orthophoto of Scotland: the map shows its own base layers.",
        # Partial: about a tenth of Scotland so far
        coverage=Coverage(provider="Scottish Government", added="2026-11-02", partial=True, survey="2023–2026")),
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
        note="Data: Welsh Government, OGL v3.0. No open orthophoto of Wales: the map shows its own base layers.",
        coverage=Coverage(provider="Welsh Government", added="2026-11-01", survey="2020–2022")),
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
             "England); no open orthophoto of England: the map shows its own base layers.",
        coverage=Coverage(provider="Environment Agency", added="2026-11-01", survey="2000–2022")),
]
