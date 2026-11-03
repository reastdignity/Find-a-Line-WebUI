"""Canada: British Columbia's LidarBC surveys (a region source), NRCan's HRDEM national mosaic (1 m, then 2 m) and
MRDEM-30 for the gaps, read in blocks from their COGs (no key)."""

from typing import Dict, List, Tuple

from ..credit import Credit
from ..source import Coverage, ReadmeRow, Source
from ..layers.fileblocks import FileBlocks
from ..layers.lidarbc import LidarBcBlocks, bc_utm_crs
from .arctic import ARCTIC_ACKNOWLEDGEMENT
from .world import COPERNICUS_NOTICE

# NAD83(CSRS) / Canada Atlas Lambert, the CRS of all of NRCan's mosaics: the working grid too, so the pixels are
# copied as they are (the mosaic was already resampled once, from the surveys' UTM and MTM zones). Its standard
# parallels are 49° N and 77° N: lengths on it are off by its scale, k - 1 = -0.26 % at Squamish, -0.75 % at
# Canmore, +1.75 % on the Niagara Escarpment (Lion's Head), +3.4 % at Lake Erie, about -3 % at 60-65° N
# (Yellowknife, Whitehorse, Iqaluit)
CANADA_LCC = "EPSG:3979"
CANELEVATION = "https://canelevation-dem.s3.ca-central-1.amazonaws.com"
# OGL - Canada 2.0: the statement of a provider that names none (NRCan names none for the mosaics or MRDEM)
OGL_CANADA = ("OGL - Canada 2.0", "https://open.canada.ca/en/open-government-licence-canada")
OGL_STATEMENT = "Contains information licensed under the Open Government Licence – Canada."
HRDEM_CREDIT = Credit("HRDEM national mosaic, DTM / DSM 1 m and 2 m (NRCan)", OGL_STATEMENT, *OGL_CANADA)
# The 2 m mosaic's own credit: its surface model of the far north (the cells with a DSM only, Baffin's) is ArcticDEM v4.1 moved to
# CGVD2013 (wave 0 of batch 3: HRDEM 2 m DSM = ArcticDEM - N to 5 cm), so PGC's acknowledgement goes with it
HRDEM_2M_CREDIT = Credit("HRDEM national mosaic, DTM / DSM 2 m (NRCan)", OGL_STATEMENT, *OGL_CANADA,
                         notice="In the far north its surface model is ArcticDEM v4.1 (Polar Geospatial Center): "
                                + ARCTIC_ACKNOWLEDGEMENT)
# MRDEM's record (open.canada.ca 18752265-bda3-498c-a4ba-9dfe68cb98da) asks for the Copernicus sentence too: its
# DTM outside the lidar is Copernicus GLO-30 with forests and settlements removed
# (with its disclaimer, in the record's words)
MRDEM_CREDIT = Credit("MRDEM-30, DTM / DSM 30 m (NRCan)",
                      f"{OGL_STATEMENT} This product was in part {COPERNICUS_NOTICE}.", *OGL_CANADA,
                      notice="The organisations in charge of the Copernicus program by law or by delegation do not "
                             "incur any liability for any use of the Copernicus WorldDEM-30.")

# The HRDEM mosaics (hrdem-mosaic-1m, hrdem-mosaic-2m): one COG per 500 km cell of EPSG:3979 and model,
# <I>_<J>-mosaic-<res>m-<dtm|dsm>.tif with I = floor(x / 500 km) + 6, J = floor(y / 500 km) + 3 (float32, LZW,
# 512 px tiles, nodata -32767, the sea and lakes too; up to 1 TB a file: read in windows only), pixel edges on
# whole metres. A cell without a file answers 404 (its blocks are missing). NRCan rebuilds every file in place as
# new surveys come in (all 58 of the 1 m in 2026: January, May, October) and adds files for new cells (4_7, 6_9 on
# 2026-10-26), so the folders are "live" (cache update reads their blocks again after cache.TTL_DAYS["live"]) and
# the cells come from the formula, not from a list. The STAC (datacube.services.geo.ca, collections
# hrdem-mosaic-1m/-2m) lists the files with their extents: a few cells are larger, reaching 50 km into a cell that
# has no file of its own; a block there is read from the larger file first. A new larger file is missing outside
# its own cell until it is listed here.
HRDEM_CELL_M = 500000
CellExtents = Dict[str, Tuple[float, float, float, float]]  # name: (left, bottom, right, top)
LARGER_1M: CellExtents = {"5_3": (-500000, -50000, 0, 500000),  # 550 000 rows: 50 km south, no 5_2
                          "7_8": (500000, 2500000, 1050000, 3000000),  # 550 000 columns: 50 km east, no 8_8
                          "11_4": (2500000, 500000, 3050000, 1000000)}  # 50 km east, no 12_4
# The 2 m mosaic (2026-11-02: 64 files): the same cells and larger ones, and six cells of the far north with a
# DSM only (4_8, 4_9, 5_5, 5_9, 6_10, 9_6; their DTM answers 404), 6_10 reaching 50 km west and east
LARGER_2M: CellExtents = {**LARGER_1M, "6_10": (-50000, 3500000, 550000, 4000000)}
# MRDEM-30's extent, a little more than the land of Canada: blocks outside it make no request
CANADA_EXTENT = (-2500020.0, -1000020.0, 3056580.0, 4000020.0)


def hrdem_files(res: int, kind: str, larger: CellExtents, block_m: float):
    """The files of a block of block_m (a divisor of 50 km) of the HRDEM mosaic of res metres, DTM or DSM
    (kind "dtm"/"dsm"): a larger file reaching over the block first, then the file of the block's own cell.
    The survey years are not in the files (0)."""
    def files(i: int, j: int):
        x, y = i * block_m, j * block_m  # the block's lower-left corner
        names = [name for name, (left, bottom, right, top) in larger.items()
                 if left <= x < right and bottom <= y < top]
        own = f"{int(x // HRDEM_CELL_M) + 6}_{int(y // HRDEM_CELL_M) + 3}"
        if own not in names:
            names.append(own)
        return [(f"{name}-mosaic-{res}m-{kind}.tif", f"{CANELEVATION}/hrdem-mosaic-{res}m/{name}-mosaic-{res}m-{kind}.tif",
                 0) for name in names]
    return files


def _hrdem(res: int, kind: str, description: str, larger: CellExtents) -> FileBlocks:
    # Blocks of 1000 x 1000 px (1 km at 1 m, 2 km at 2 m): up to nine of the files' 512 px tiles, about 2 MB
    block_m = 1000 * res
    return FileBlocks(description, f"canada/hrdem-{res}m-{kind}/live", CANADA_LCC, float(res), block_m,
                      hrdem_files(res, kind, larger, block_m), extent=CANADA_EXTENT, bytes_per_tile=2e6,
                      credit=HRDEM_2M_CREDIT if res == 2 else HRDEM_CREDIT)


# MRDEM-30 (NRCan, 2024): one COG per model for all of Canada (mrdem-30-dtm.tif, 83.9 GB; float32, LZW, 512 px
# tiles, nodata -32767 (the open sea), pixel edges on multiples of 30 m from 0), lidar where there is some and
# Copernicus GLO-30 elsewhere, CGVD2013; the files keep their address when they are made again: "live"
def _mrdem(kind: str, description: str) -> FileBlocks:
    # Blocks of 15 km (500 x 500 px), about 0.5 MB
    return FileBlocks(description, f"canada/mrdem-30-{kind}/live", CANADA_LCC, 30.0, 15000,
                      f"{CANELEVATION}/mrdem-30/mrdem-30-{kind}.tif", extent=CANADA_EXTENT, bytes_per_tile=5e5,
                      credit=MRDEM_CREDIT)


# British Columbia: GeoBC's LidarBC (the provincial lidar programme of 2023-2026 and the older surveys of NDMP, BCTS,
# FAIB and purchased ones, 2011-2024): DEM (bare earth) and DSM GeoTIFFs of 1 m (2 m for BCTS 2016) per BCGS 1:20 000
# sheet (0.1° x 0.2°) or 1:2 500 tile and survey year, in NAD83(CSRS) / UTM of zones 8-11 (2023+ files name the
# compound CRS with CGVD2013 height, EPSG:6653/6654), CGVD2013 heights (the accuracy reports; BC's 2016 and 2019 files
# equal NRCan's CGVD2013 projects at the Stawamus Chief to the millimetre), nodata -32767 (-9999 in NDMP 2019),
# pixel edges on whole metres but for NDMP 2017 (fractional origins, read bilinearly). Files of anonymous S3
# (https://nrs.objectstore.gov.bc.ca/gdwuts/<NNN>/<NNNl>/<year>/<dem|dsm>/bc_<sheet>...tif), listed by the LidarBC
# index, an ArcGIS FeatureServer (LiDAR_BC_S3_Public: DEM layers 6 (1:20 000) and 5 (1:2 500), DSM 3 and 1; "Access
# Only": queried, its answers cached in the worker, never published), each entry confirmed by a listing of the
# bucket (its wrong entries drop out). A sheet holds several partial surveys clipped to their flights: composed
# newest first per 1 km block. Three layouts: COGs (2015, 2020-2021), 512 px tiles (2016-2019), one-row strips
# (2022+: a 1 km block of a 1:2 500 tile reads about half of its 2-8 MB file).
# The "PixelIsPoint" files (2015-2018, 2021-2022) are read as GDAL reads them (their tie point at the pixel's
# centre): wave 0 found them half a pixel off the "Area" files (BC 2016 against BC 2019 at the Chief: best shift
# (-0.5, +0.5) px, median |d| 0.238 m against 0.302 m at (0, 0); BC 2017 against BC 2024 at Skaha: (+0.5, -0.5) px,
# 0.086 against 0.283 m), and reading them with GTIFF_POINT_GEO_IGNORE (the tie point at the corner) did not remove
# it (2026-11-03: Chief (-1, 0) px, 0.238 m, 0.449 at (0, 0); Skaha (0, -1) px, 0.087 m, 0.338 at (0, 0)), so the
# composition keeps such offsets where an older survey fills a newer one's holes.
# Limits: none published (OGL-BC's API Terms of Use, v1.1 of 2025-04-11: the provider "may, without notice, impose
# and or adjust limits on your access or use of the API"; the LidarBC pages and catalogue records, read 2026-11-03):
# net.HOST_SLOTS_OF caps the bucket at 4. The licence names no statement of LidarBC's own: OGL-BC's default one.
LIDARBC_FS = "https://services6.arcgis.com/ubm4tcTYICKBpist/arcgis/rest/services/LiDAR_BC_S3_Public/FeatureServer"
LIDARBC_BUCKET = "https://nrs.objectstore.gov.bc.ca/gdwuts"
OGL_BC = ("OGL - British Columbia 2.0",
          "https://www2.gov.bc.ca/gov/content/data/policy-standards/open-data/open-government-licence-bc")
LIDARBC_CREDIT = Credit("LidarBC DEM / DSM 1 m (GeoBC, Province of British Columbia)",
                        "Contains information licensed under the Open Government Licence – British Columbia.", *OGL_BC)


def _lidarbc(kind: str, layers: Tuple[int, int], description: str) -> LidarBcBlocks:
    # Blocks of 1 km on the files' whole metres: a block of a strip file reads its rows whole (2-4 MB)
    return LidarBcBlocks(description, LIDARBC_FS, layers, LIDARBC_BUCKET, f"lidarbc-{kind}", f"canada/lidarbc-{kind}",
                         bytes_per_tile=4e6)


# British Columbia in region boxes inside Canada's (they come first): the province west of 120° W (Haida Gwaii and
# the panhandle side west of 129.9° W and north of 51° N go to Alaska's box, which comes before, and the strip south
# of 49.4° N with Vancouver and Victoria to the USA's: offline only, as for canada), the Okanagan and the Kootenays
# east of it to 116° W, the Elk Valley to 114.6° W, the Columbia valley at Golden and Valemount west of the divide
# (Banff, Lake Louise and Jasper stay in Alberta)
BC_BOXES = (("ca-bc", (49.0, 60.0, -139.1, -120.0)), ("ca-bc", (48.2, 49.0, -125.0, -123.2)),
            ("ca-bc", (49.0, 51.0, -120.0, -116.0)), ("ca-bc", (49.0, 50.3, -116.0, -114.6)),
            ("ca-bc", (51.0, 51.8, -118.5, -116.6)), ("ca-bc", (51.0, 53.8, -120.0, -118.5)))

CA_SCALE_NOTE = ("Lengths are measured on NRCan's grid, Canada Atlas Lambert (EPSG:3979), whose scale makes them "
                 "about 0.3 % short at Squamish, 0.7 % short at Canmore, 1.7 % long on the Niagara Escarpment and "
                 "3 % short around 60-65° N.")
CA_NO_ORTHO = "– (no national orthophoto service)"

SOURCES: List[Source] = [
    Source(
        id="british_columbia", name="LidarBC (DTM / DSM 1 m, British Columbia)",
        description="GeoBC's LidarBC: lidar terrain and surface models 1 m of the provincial programme 2023-2026 "
                    "and older surveys, newest first, NAD83(CSRS) / UTM, CGVD2013 heights; gaps from NRCan's HRDEM "
                    "mosaic 1 m, then 2 m, then MRDEM-30",
        nmt=_lidarbc("dem", (6, 5), "LidarBC DEM 1 m (terrain)"),
        nmpt=_lidarbc("dsm", (3, 1), "LidarBC DSM 1 m (trees, buildings)"),
        countries=("ca",), regions=("ca-bc",), local_crs=bc_utm_crs, credits=(LIDARBC_CREDIT,),
        # Never FABDEM (its terms are not open): HRDEM, then its 2 m version, then MRDEM-30. canada is no neighbour
        # (either way): it is the first gap filler here, and as a neighbour of canada this source would fill the
        # border gaps of a search on HRDEM inside British Columbia (R41 at the Chief: 33 pixels from LidarBC, the
        # filled area 0.01 -> 0 km2), not across a border
        fallback="canada", more_fallbacks=("canada_2m", "mrdem30"),
        neighbours=("usa", "alaska", "alaska_ifsar"),
        listing=ReadmeRow("British Columbia (CA), where it has lidar", "GeoBC LidarBC DEM 2011-2026, 1 m",
                          "GeoBC LidarBC DSM, 1 m", CA_NO_ORTHO),
        offline=BC_BOXES, sample=(49.432, -119.557),  # Skaha Bluffs, Penticton
        note="Data: GeoBC, Open Government Licence - British Columbia. LidarBC covers the provincial programme's "
             "surveys (much of the province since 2023, published monthly) and older ones; gaps are filled from "
             "NRCan's HRDEM mosaic (1 m, then 2 m), then from MRDEM-30 (30 m). Its surface model equals the terrain "
             "on bare ground; where only the gap filler has one, the surface is another survey. No open orthophoto "
             "of British Columbia: the map shows its own base layers.",
        coverage=Coverage(provider="GeoBC", added="2026-11-03", partial=True, rest=(2.0, 30.0), survey="lidar")),
    Source(
        id="canada", name="NRCan HRDEM mosaic (DTM / DSM 1 m)",
        description="NRCan HRDEM national mosaic: lidar terrain and surface models 1 m, NAD83(CSRS) / Canada Atlas "
                    "Lambert (EPSG:3979, lengths off by its scale: -0.3 % at Squamish, -0.7 % at Canmore, +1.7 % on "
                    "the Niagara Escarpment, about -3 % at 60-65° N), CGVD2013 heights; gaps from the 2 m mosaic, "
                    "then MRDEM-30",
        # The mosaic read in blocks on its own pixels (edges on whole metres), so the working grid is EPSG:3979
        nmt=_hrdem(1, "dtm", "HRDEM mosaic DTM 1 m (terrain)", LARGER_1M),
        nmpt=_hrdem(1, "dsm", "HRDEM mosaic DSM 1 m (trees, buildings)", LARGER_1M),
        countries=("ca",), crs=CANADA_LCC, credits=(HRDEM_CREDIT,),
        fallback="canada_2m", more_fallbacks=("mrdem30",), neighbours=("usa", "alaska", "alaska_ifsar", "nunavut"),
        listing=ReadmeRow("Canada, where it has lidar", "NRCan HRDEM national mosaic DTM, 1 m",
                          "NRCan HRDEM national mosaic DSM, 1 m", CA_NO_ORTHO),
        # Rough boxes (the first holding a point wins, and the USA's and Alaska's come first: southern Ontario
        # and Quebec, Haida Gwaii and the Yukon west of 129.9° W are taken for the USA offline)
        offline=(("ca", (48.9, 60.0, -139.1, -52.6)), ("ca", (48.2, 48.9, -125.0, -123.2)),
                 ("ca", (46.0, 48.9, -95.2, -74.3)), ("ca", (41.6, 46.0, -83.6, -74.3)),
                 ("ca", (43.3, 48.9, -74.3, -52.6)), ("ca", (60.0, 83.2, -141.0, -61.0))),
        sample=(49.6820, -123.1430),
        note="Data: NRCan, Open Government Licence - Canada. The mosaic covers the lidar surveys (much of the "
             "south, little of the north); gaps are filled from its 2 m version, then from MRDEM-30 (30 m). "
             + CA_SCALE_NOTE + " No orthophoto of Canada: the map shows its own base layers.",
        coverage=Coverage(provider="NRCan", added="2026-11-02", partial=True, rest=(2.0, 30.0), survey="lidar")),
    Source(
        id="canada_2m", name="NRCan HRDEM mosaic (DTM / DSM 2 m)",
        description="NRCan HRDEM national mosaic 2 m: lidar terrain and surface models (in the far north a surface "
                    "model only, from ArcticDEM's satellite stereo), EPSG:3979, CGVD2013 heights; gaps from MRDEM-30",
        nmt=_hrdem(2, "dtm", "HRDEM mosaic DTM 2 m (terrain)", LARGER_2M),
        nmpt=_hrdem(2, "dsm", "HRDEM mosaic DSM 2 m (trees, buildings)", LARGER_2M),
        crs=CANADA_LCC, credits=(HRDEM_2M_CREDIT,), fallback="mrdem30",
        listing=ReadmeRow("Canada, where it has lidar", "NRCan HRDEM national mosaic DTM, 2 m",
                          "NRCan HRDEM national mosaic DSM, 2 m", CA_NO_ORTHO),
        sample=(49.6820, -123.1430),
        note="Data: NRCan, Open Government Licence - Canada. " + CA_SCALE_NOTE),
    Source(
        id="mrdem30", name="NRCan MRDEM-30 (DTM / DSM 30 m)",
        description="NRCan MRDEM-30: terrain and surface models 30 m of all of Canada (lidar and Copernicus GLO-30), "
                    "EPSG:3979, CGVD2013 heights",
        nmt=_mrdem("dtm", "MRDEM-30 DTM (terrain)"), nmpt=_mrdem("dsm", "MRDEM-30 DSM (trees, buildings)"),
        # It covers all of Canada and a little more: no fallback (FABDEM's terms are not open)
        crs=CANADA_LCC, credits=(MRDEM_CREDIT,), fallback=None,
        listing=ReadmeRow("Canada", "NRCan MRDEM-30 DTM, 30 m", "NRCan MRDEM-30 DSM, 30 m", CA_NO_ORTHO),
        sample=(49.6820, -123.1430),
        note="Data: NRCan, Open Government Licence - Canada; contains Copernicus WorldDEM-30. At 30 m only long "
             "lines can be found reliably. " + CA_SCALE_NOTE),
]
