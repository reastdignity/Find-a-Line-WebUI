"""Estonia: the Land and Spatial Development Board's (Maa- ja Ruumiamet) lidar DTM of 1 m, 5 km sheets read by our own
range requests through its PHP download address, and its DSM of 1 m, 1 km sheets downloaded whole."""

from functools import lru_cache
from typing import FrozenSet, List, Optional, Tuple

from ..credit import YEAR, Credit
from ..source import Coverage, OrthoService, ReadmeRow, Source
from ..layers.fileblocks import FileBlocks
from ..layers.metricsheets import MetricSheetTiles

# Estonian Coordinate System of 1997 (L-EST97, EPSG:3301), the files' own; heights EH2000 (above the sea)
EE_CRS = "EPSG:3301"

# The geoportal's download address (geoportaal.maaruum.ee; the older geoportaal.maaamet.ee answers 302 to it, so it is
# not used): index.php with the sheet's number, the product and the file's name; no `no_cache` token needed. Behind
# Cloudflare; the files of every sheet were uploaded again on 2026-04-09 (Last-Modified), each with an ETag. A file
# comes as image/tiff and honours Range (206 with its Content-Range); an error comes as an HTML page with HTTP 206
# and the page's own Content-Range ("Error: map sheet numbers of 1:10000 scale are between 44744 and 74331") when a
# Range was asked, with HTTP 200 without one ("Map sheet not found." for a sheet in the sea): checked as TIFFs,
# never cached (ranges.NotTiff, Download(tiff_only=True)). Read 2026-11-15.
EE_URL = ("https://geoportaal.maaruum.ee/index.php?lang_id=2&plugin_act=otsing&kaardiruut={sheet}&andmetyyp={kind}"
          "&dl=1&f={sheet}_{model}_1m.tif&page_id=664")
# A new upload of the whole country (a new Last-Modified) is a new folder, set by hand, here and in the cache
EE_RELEASE = "20260409"


def ee_dtm_url(sheet: str) -> str:
    return EE_URL.format(sheet=sheet, kind="dem_1m_geotiff", model="dtm")


def ee_dsm_url(sheet: str) -> str:
    return EE_URL.format(sheet=sheet, kind="ndsm_abs_1m_geotiff", model="dsm")


# The DTM: sheets of 5 km of the 1:10 000 grid, 5000 x 5000 px float32, DEFLATE with a float predictor, 512 px
# tiles with overviews, nodata -9999, pixel edges on whole kilometres (PixelIsArea), 26-76 MB. A sheet's number
# d1 d2 d3 d4 q names its lower-left corner: E = 200 + 100 d2 + 10 d4 km, N = 5900 + 100 d1 + 10 d3 km, and the
# quarter q of that 10 km square (1 south-west, 2 south-east, 3 north-west, 4 north-east: 5 km more east for 2
# and 4, north for 3 and 4); checked on all 2 073 sheets of EE_SHEETS (the formula's names round trip) and on the
# tie points of 64442, 73041, 51681 and 63944 (2026-11-15)
def ee_sheet(e_km: int, n_km: int) -> str:
    """The number of the 5 km DTM sheet holding the point (e_km, n_km) in kilometres of L-EST97."""
    r, c = (n_km - 5900) // 10, (e_km - 200) // 10
    q = 1 + (e_km % 10 >= 5) + 2 * (n_km % 10 >= 5)
    return f"{r // 10}{c // 10}{r % 10}{c % 10}{q}"


def ee_corner(sheet: str) -> Optional[Tuple[int, int]]:
    """The lower-left corner (E, N) in kilometres of a DTM sheet's number, None when it is not one."""
    if len(sheet) != 5 or not sheet.isdigit() or sheet[4] not in "1234":
        return None
    d1, d2, d3, d4, q = (int(c) for c in sheet)
    return 200 + 100 * d2 + 10 * d4 + 5 * (q in (2, 4)), 5900 + 100 * d1 + 10 * d3 + 5 * (q in (3, 4))


@lru_cache(maxsize=None)
def ee_sheets() -> FrozenSet[Tuple[int, int]]:
    """The lower-left corners (E, N) in kilometres of the DTM sheets the Board publishes (EE_SHEETS)."""
    found = set()
    for row in EE_SHEETS.split():
        n, runs = row.split(":")
        for run in runs.split(","):
            first, _, last = run.partition("-")
            found.update((e, int(n)) for e in range(int(first), int(last or first) + 1, 5))
    return frozenset(found)


def _has_sheet(e_km: int, n_km: int) -> bool:
    return (e_km // 5 * 5, n_km // 5 * 5) in ee_sheets()


def ee_dtm_files(i: int, j: int):
    """files(i, j) of FileBlocks: the DTM sheet under block (i, j) of EE_BLOCK_M, if the Board has it."""
    e_km, n_km = i * EE_BLOCK_M // 1000, j * EE_BLOCK_M // 1000
    if not _has_sheet(e_km, n_km):
        return []
    sheet = ee_sheet(e_km, n_km)
    return [(sheet, ee_dtm_url(sheet), 0)]  # surveys of 2021-2024, the year of a sheet not published


def ee_dsm_sheet(i: int, j: int) -> Optional[str]:
    """The 1 km DSM sheet of tile (i, j) (its lower-left corner in kilometres): the number <N - 6000><E> of the
    1:2 000 grid (541645: 645 km E, 6 541 km N), None outside the DTM's sheets (no request)."""
    if not _has_sheet(i, j) or not (0 <= j - 6000 <= 999 and 100 <= i <= 999):
        return None
    return f"{j - 6000:03d}{i}"


# Blocks of 1.25 km (four per sheet side, each inside its sheet): a block's window covers 3 x 3 or 4 x 4 of the
# sheet's 512 px tiles, about 5.5 MB a km² read (2.8 MB a km² whole). The PHP address is no .tif for GDAL's /vsicurl/
# (CPL_VSIL_CURL_ALLOWED_EXTENSIONS) and its errors are 206 pages: read through our own range requests
# (Windows(ranged=True): every answer checked whole, the first bytes a TIFF's)
EE_BLOCK_M = 1250
EE_EXTENT = (365_000.0, 6_375_000.0, 740_000.0, 6_635_000.0)
EE_DTM = FileBlocks("Maa- ja Ruumiamet DTM 1 m (terrain)", f"estonia/dtm-1m/{EE_RELEASE}", EE_CRS, 1.0, EE_BLOCK_M,
                    ee_dtm_files, extent=EE_EXTENT, bytes_per_tile=8.5e6, ranged=True)
# The DSM ("absolute height", from the spring and summer flights): sheets of 1 km, 1000 x 1000 px float32,
# uncompressed strips, no nodata (the sea at -0.25 to -0.11 m), edges on whole kilometres, 4 MB: downloaded whole.
# A sheet in the sea is answered "Map sheet not found." (an HTML page): missing
EE_DSM = MetricSheetTiles("Maa- ja Ruumiamet DSM 1 m (trees, buildings)", f"estonia/dsm-1m/{EE_RELEASE}", EE_CRS,
                          1000, 1.0, ee_dsm_sheet, ee_dsm_url, bytes_per_tile=4e6,
                          binary_types=("tiff", "text/html"), not_found=r"Map sheet not found")

# The Board's open data licence (https://geoportaal.maaruum.ee/opendata-licence, "opendata licence 01.01.2025", read
# 2026-11-15): derivatives, commercial use and redistribution allowed; "The reference must include the name of the
# licensor, the title of the data and the age of the data (or the date of data extraction)", its own example
# "Elevation data 2021-2024: Republic of Estonia Land and Spatial Development Board"; the licence or its reference
# attached when data are passed on
EE_LICENCE = "https://geoportaal.maaruum.ee/opendata-licence"
EE_CREDIT = Credit("Elevation data 2021-2024, DTM / DSM 1 m (Land and Spatial Development Board, Estonia)",
                   "Elevation data 2021-2024: Republic of Estonia Land and Spatial Development Board",
                   "Land and Spatial Development Board open data licence", EE_LICENCE,
                   notice=f"Licence: {EE_LICENCE}")
# The Board's orthophoto tiles (WMTS layer "foto" on the GoogleMapsCompatible matrix set GMC, the same tiles as its
# TMS foto@GMC with y flipped; to zoom 18, Access-Control-Allow-Origin *), under the same licence: the licensor
# and the year of the extraction
EE_ORTHO = OrthoService(
    "Orthophoto (Maa- ja Ruumiamet)", None, "", "estonia/ortho/live",
    f"Orthophoto: Republic of Estonia Land and Spatial Development Board {YEAR}", attribution_url=EE_LICENCE,
    base_url="https://tiles.maaamet.ee/tm/wmts/1.0.0/foto/default/GMC/{z}/{y}/{x}.jpg", base_max_zoom=18)

# Estonia with its islands; the box also holds the north of Latvia and a strip of Russia beyond the Narva and Lake
# Peipus (no sources there: their tiles are missing and the fallback fills them) and no Finnish land
EE_BOX = (57.50, 59.70, 21.75, 28.25)

SOURCES: List[Source] = [
    Source(
        id="estonia", name="Maa- ja Ruumiamet DTM 1 m (Estonia)",
        description="Land and Spatial Development Board (Maa- ja Ruumiamet): lidar DTM and DSM 1 m of 2021-2024, "
                    "L-EST97, EH2000 heights",
        nmt=EE_DTM, nmpt=EE_DSM, countries=("ee",), crs=EE_CRS, ortho=EE_ORTHO, credits=(EE_CREDIT,),
        listing=ReadmeRow("Estonia", "Maa- ja Ruumiamet DTM, 1 m (lidar 2021-2024)", "Maa- ja Ruumiamet DSM, 1 m",
                          "Maa- ja Ruumiamet orthophoto"),
        offline=(("ee", EE_BOX),), sample=(59.3890, 24.0380),  # Pakri cliff at Paldiski (R79)
        note="Elevation data 2021-2024: Republic of Estonia Land and Spatial Development Board "
             "(https://geoportaal.maaruum.ee/opendata-licence).",
        coverage=Coverage(provider="Maa- ja Ruumiamet", added="2026-11-15", survey="2021–2024")),
]

# The DTM's sheets (Mapterhorn's list of the 2 073 download addresses, source-catalog/ee/file_list.txt, read
# 2026-11-15; every number in 44744-74331, the range the server names) as the lower-left corners of their 5 km
# squares, runs "<N>:<E0>-<E1>,<E2> ..." in kilometres in steps of 5. A block outside it is missing without a request
EE_SHEETS = (
    "6375:645-655 6380:635-665,685-700 6385:630-700 6390:630-700 6395:625-700 6400:455,620-710 "
    "6405:450-455,620-710 6410:520-525,605-710 6415:380,520-525,595-725 6420:380-385,520-540,590-725 "
    "6425:380-390,520-555,570-575,585-715 6430:380-390,525-560,570-715 6435:385-395,495,525-715 "
    "6440:385-395,405-415,495-500,525-710 6445:385-395,405-410,425-430,495-500,510,525-710 "
    "6450:380-425,490,505,525-705 6455:370-430,500-515,525-700 6460:370-435,490-515,530-610,625-700 "
    "6465:365-440,480-515,525-615,625-700 6470:370-445,480-705 6475:370-460,475-705 6480:370-460,475-685 "
    "6485:370-380,390-685 6490:395-685 6495:410-685 6500:410-415,440-685 6505:410-420,450,465-680 "
    "6510:405-430,440-450,460-680 6515:405-450,460-675 6520:405-450,460-670 6525:390-445,460-670 "
    "6530:385-445,455-670 6535:385-675 6540:405-690,710-715 6545:415-425,445-715 6550:415-420,430-435,470-715 "
    "6555:470-715 6560:470-720 6565:470-720 6570:460-465,480-720 6575:485-730 6580:495-735 6585:510-735 "
    "6590:515-735 6595:530,540-660,725-730 6600:525-530,540-550,560-570,585-655 6605:525-530,540,555-630 "
    "6610:550-555,570,580-615 6615:555,595-600,640 6630:630 "
)
