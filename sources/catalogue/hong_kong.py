"""Hong Kong: the Civil Engineering and Development Department's 2020 lidar terrain and surface models at 0.5 m, one
ZIP per 1:1000 map sheet (750 x 600 m) of the Hong Kong 1980 Grid, read on demand from the CSDI Portal's bulk-data
host."""

import os
import re
from functools import lru_cache
from typing import Dict, List, Optional, Tuple

import numpy as np

from ..credit import Credit
from ..layers.cellsheets import CellSheetTiles
from ..source import Coverage, ReadmeRow, Source

# The 1:1000 sheets of the Hong Kong 1980 Grid (EPSG:2326), as CEDD's files name them (7SW25C): a 1:20000 map (1-16
# in four rows of four from the north-west, each 15 x 12 km from (800 000, 800 000), and 17 east of 4), its quarter
# (NW, NE, SW, SE: 7.5 x 6 km), a block of it (1-25, row by row from the north-west: 1.5 x 1.2 km) and the block's
# quarter (A north-west, B north-east, C south-west, D south-east): 750 x 600 m. 7SW25C = x 836 000-836 750,
# y 824 000-824 600 (its file's header). Checked on every row of the CSDI Portal's index (3 253 terrain and 3 310
# surface sheets, 2026-11-16: tools/hong_kong_sheets.py checks each footprint against its code's box).
HK_CRS = "EPSG:2326"
HK_LEFT, HK_BOTTOM = 800_000, 800_000  # the south-west corner of map 13
HK_MAP = (15_000, 12_000)
HK_SHEET = (750, 600)
HK_MAPS: Dict[int, Tuple[int, int]] = {
    **{n: (HK_LEFT + (n - 1) % 4 * HK_MAP[0], HK_BOTTOM + (3 - (n - 1) // 4) * HK_MAP[1]) for n in range(1, 17)},
    17: (HK_LEFT + 4 * HK_MAP[0], HK_BOTTOM + 3 * HK_MAP[1])}
_HK_MAP_AT = {corner: n for n, corner in HK_MAPS.items()}
HK_QUARTERS = {"NW": (0, 1), "NE": (1, 1), "SW": (0, 0), "SE": (1, 0)}  # (column, row from the south): a map's
_HK_QUARTER_AT = {v: k for k, v in HK_QUARTERS.items()}
HK_LETTERS = {"A": (0, 1), "B": (1, 1), "C": (0, 0), "D": (1, 0)}       # the same: a block's quarters
_HK_LETTER_AT = {v: k for k, v in HK_LETTERS.items()}
_HK_CODE = re.compile(r"(\d{1,2})(NW|NE|SW|SE)(\d{1,2})([ABCD])")


def hk_sheet(i: int, j: int) -> Optional[str]:
    """The 1:1000 sheet of cell (i, j) of 750 x 600 m from (HK_LEFT, HK_BOTTOM), j northwards: "7SW25C"; None off
    the 17 maps."""
    x, y = HK_LEFT + i * HK_SHEET[0], HK_BOTTOM + j * HK_SHEET[1]  # the cell's south-west corner
    corner = (HK_LEFT + (x - HK_LEFT) // HK_MAP[0] * HK_MAP[0], HK_BOTTOM + (y - HK_BOTTOM) // HK_MAP[1] * HK_MAP[1])
    n = _HK_MAP_AT.get(corner)
    if n is None:
        return None
    dx, dy = x - corner[0], y - corner[1]
    qx, qy = dx % 7_500, dy % 6_000
    block = (4 - qy // 1_200) * 5 + qx // 1_500 + 1
    quarter, letter = _HK_QUARTER_AT[(dx // 7_500, dy // 6_000)], _HK_LETTER_AT[(qx % 1_500 // 750, qy % 1_200 // 600)]
    return f"{n}{quarter}{block}{letter}"


def hk_cell(code: str) -> Optional[Tuple[int, int]]:
    """The cell (i, j) of a sheet's code, None when it is not one of the scheme ("7SW05C" neither)."""
    match = _HK_CODE.fullmatch(code)
    if not match or int(match.group(1)) not in HK_MAPS or not 1 <= int(match.group(3)) <= 25:
        return None
    (mx, my), (qc, qr), block = HK_MAPS[int(match.group(1))], HK_QUARTERS[match.group(2)], int(match.group(3)) - 1
    lc, lr = HK_LETTERS[match.group(4)]
    left = mx + qc * 7_500 + block % 5 * 1_500 + lc * 750
    bottom = my + qr * 6_000 + (4 - block // 5) * 1_200 + lr * 600
    cell = (left - HK_LEFT) // HK_SHEET[0], (bottom - HK_BOTTOM) // HK_SHEET[1]
    return cell if hk_sheet(*cell) == code else None


def hk_name(code: Optional[str]) -> Optional[str]:
    """A sheet's cached file under its layer's folder (without .tif): <map and quarter>/<code>, "7SW/7SW25C"."""
    match = None if code is None else _HK_CODE.fullmatch(code)
    return None if match is None else f"{match.group(1)}{match.group(2)}/{code}"


def hk_cell_of_name(name: str) -> Optional[Tuple[int, int]]:
    """The cell of a cached name (hk_name), None when it is not one."""
    cell = hk_cell(name.rsplit("/", 1)[-1])
    return cell if cell is not None and hk_name(hk_sheet(*cell)) == name else None


# The files of each sheet: CEDD's file names carry the code and two pairs of kilometres, e.g.
# 7SW25C(e836n824,e836n824).zip: the south-west and the north-east corner of the sheet floored to the kilometre
# (equal in 316 of 3 253 terrain sheets); in 8 terrain and 9 surface sheets of map 17 a pair is a kilometre off
# (17NW12A(e861n844,...) lies at x 861 500, y 845 000), so the names are kept as published, never computed. The table
# (hong_kong_sheets.npz, tools/hong_kong_sheets.py) holds every sheet of the CSDI Portal's index (four requests): a
# sheet outside it is never asked, a 404 for one in it is an error of that tile, asked again by the next search
# (CellSheetTiles). Every listed file answered 200 on 2026-11-16 (a HEAD of the first 2 857 terrain files of the index,
# made once that day; not a step of the table's tool). 57 sheets have a surface model and no terrain (coastal sheets,
# most of them on Deep Bay's mudflats and fishponds and on Lantau's west coast): a search there gets the fallback's
# terrain under the 0.5 m lidar surface.
HK_BULK = "https://bulkdata.csdi.gov.hk/cedd/lidar"
HK_FOLDERS = {"dtm": "2020dtm", "dsm": "2020dsm"}
HK_SHEETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hong_kong_sheets.npz")
HK_YEAR = 2020
# Metres added to every height of both models (Layer.height_offset): mean sea level "is about 1.30m above HKPD" (the
# Lands Department's Explanatory Notes on Geodetic Datums in Hong Kong, quoted below)
HK_DATUM_OFFSET = -1.30


@lru_cache(maxsize=None)
def _hk_table() -> Dict[str, Dict[str, str]]:
    """The file name of each sheet, per layer ("dtm", "dsm": hong_kong_sheets.npz)."""
    with np.load(HK_SHEETS) as saved:
        return {layer: {code.decode(): name.decode() for code, name in zip(saved[f"{layer}_codes"],
                                                                          saved[f"{layer}_files"])}
                for layer in HK_FOLDERS}


def hk_files(layer: str, i: int, j: int) -> List[Tuple[str, str, int]]:
    """The ZIP of the sheet of cell (i, j) in a layer ("dtm", "dsm"): [(code, url, 2020)]; none when the table has
    none."""
    code = hk_sheet(i, j)
    name = None if code is None else _hk_table()[layer].get(code)
    return [] if name is None else [(code, f"{HK_BULK}/{HK_FOLDERS[layer]}/{name}", HK_YEAR)]


# The CSDI Portal's dataset "LiDAR Data" (cedd_rcd_1629267205233_87895, https://portal.csdi.gov.hk/csdi-webpage/
# dataset/cedd_rcd_1629267205233_87895, read 2026-11-16): the Civil Engineering and Development Department's
# Geotechnical Engineering Office, the second survey "from ... a Helicopter between 20th December 2019 and 2nd
# February 2020", covering all of Hong Kong; its layers DTM_2020 and DSM_2020. Each ZIP holds one GeoTIFF of 1500 x
# 1200 px of float32 at 0.5 m on its sheet's box (EPSG:2326, "Area", pixel edges on whole metres: grid_origin 0;
# uncompressed, 128 px tiles, 7 868 582 B), nodata -9999. Heights above the Hong Kong Principal Datum (HKPD), which
# the app's sea at 0 m does not match: the Lands Department's "Explanatory Notes on Geodetic Datums in Hong Kong"
# (https://www.geodetic.gov.hk/common/data/pdf/explanatorynotes.pdf, read 2026-11-16): "Based on the tide data
# recorded by Quarry Bay tide gauge station in Victoria Harbour during the recent 19-year cycle (1997 to 2015), the
# mean sea level is about 1.30m above HKPD." So every height, terrain and surface alike, is lowered by
# HK_DATUM_OFFSET (the user's decision of 2026-11-16) where the tiles are read onto the grid (Layer.height_offset,
# mosaic.prepare_layer): heights about mean sea level; the cache keeps CEDD's heights, so nothing is fetched again
# (2026-11-16: R91 the same 8 lines, each anchor 1.30 m lower; at Cape D'Aguilar, radius 400 m, the same 8 lines and
# clearances, 1 988 anchors fewer: the fringe's step down to the sea's 0 m fill is gone, its pixels now water).
# The sea and the land beyond Hong Kong's boundary are nodata in both models (2NE20D on the Shenzhen River: 73.9 %
# nodata, the same pixels in both; 12SW22A's surface off Tung Lung Chau: 97.1 %, its lowest pixel 0.738 m), with a
# fringe of water at +1.1 to +1.3 m above HKPD along the shore (-0.2 to 0 m once lowered: water, as is any data in
# the sea zone at most filling.SEA_LEVEL_TOLERANCE high) and a few pixels below 0 m at the sea's edge (above
# HKPD, 16NW3A: 1 796 in [-1, 0) m, 115 below -1 m, the lowest -2.07 m, within 19 m of the nodata; at 1 m around it
# 500 of the 514 below 0 m lie in the OSM coastline's sea zone). No constant, no seabed. Land below -1 m exists: three
# hollows in Kowloon's 11NE6D and 11NE7C (954 m² down to -2.97 m; 388 and 402 m² down to -6.57 and -6.02 m above
# HKPD among heights of 5-6 m; in both models), so no floor (Layer.nodata_below) is set: a floor at -1 m would take
# them and change 24 px of the sea zone at 16NW3A (the 51 sheets cached at Lion Rock and Tung Lung Chau,
# 2026-11-16). The data are frozen (Last-Modified 2022-01-14): a versioned folder, the table refreshed by hand.
#
# The CSDI Portal's Terms and Conditions of Use (https://portal.csdi.gov.hk/csdi-webpage/doc/TNC, read 2026-11-16):
# "You are allowed to browse, download, distribute, reproduce, hyperlink to and print the Data for both commercial
# and non-commercial purposes on a free-of-charge basis on the condition that:- you shall comply with the Terms of
# Use; you shall identify clearly the Government and the CSDI Portal as the source of the Data and acknowledge the
# Government and the relevant organisations' ownership of the intellectual property rights in the Data and in all
# copies thereof including but not limited to paper copies, digital copies and copies placed on other websites; you
# shall indemnify the Government and the relevant organisations ..." (the GEO Data Portal's terms,
# https://www.ginfo.cedd.gov.hk/GEOOpenData/eng/TnC.aspx, grant the same). The terms do not name modifying. Our use
# is downloading and reproducing: each sheet is downloaded once into the user's own cache, its heights re-encoded
# within 5 mm (LERC), and lines, profiles and maps are computed from them (credit.PROCESSED_NOTE says so with every
# run); nothing is redistributed (no mirror copy: a mail to CEDD, drafted for the user, asks about one). The FAQ
# (https://portal.csdi.gov.hk/csdi-webpage/info/FAQ): "Attribution must be to “Common Spatial Data Infrastructure
# (CSDI) Portal”. Attribution must also make it clear that the data is available under the CSDI terms and
# conditions. This may be done by making the text “CSDI Portal” linked to
# https://portal.csdi.gov.hk/csdi-webpage/doc/TNC": the credit's licence is that text, linked to the terms (the
# map shows "<attribution> (<licence linked to its url>)"). No request limits published (the terms, the FAQ, the
# GEO Data Portal's terms; bulkdata.csdi.gov.hk has no robots.txt): two connections at once (net.HOST_SLOTS_OF).
HK_TERMS = "https://portal.csdi.gov.hk/csdi-webpage/doc/TNC"
HK_CREDIT = Credit("LiDAR Data 2020, DTM and DSM (Civil Engineering and Development Department, Hong Kong)",
                   "LiDAR Data (2020), Civil Engineering and Development Department; intellectual property rights of "
                   "the Government of the Hong Kong Special Administrative Region and the Civil Engineering and "
                   "Development Department; source: the Government of the Hong Kong Special Administrative Region "
                   "(Civil Engineering and Development Department), through the Common Spatial Data Infrastructure "
                   "(CSDI) Portal, available under the CSDI terms and conditions",
                   "CSDI Portal", HK_TERMS,
                   notice=f"CSDI Portal Terms and Conditions of Use: {HK_TERMS}")

# bytes_per_tile: the sizes the 2 857 terrain files' answers of 2026-11-16 gave (above): mean 4.31 MB, median 5.54,
# 75th percentile 5.76, 90th 5.87, largest 6.11 (14 % under 1 MB: coastal sheets mostly sea); a surface sheet's ZIP is
# about as large as its terrain's (12SW22D 5 764 768 B against 5 765 771). 5.8 MB, the upper range, as a search
# inland takes whole land sheets (42 at Lion Rock: 238 MB, 5.7 MB each), so the estimate (and the quota) errs on the
# side of more
HK_DTM = CellSheetTiles("CEDD lidar DTM 2020 0.5 m (terrain)", "hong_kong/dtm-2020", HK_CRS, HK_SHEET, 0.5,
                        lambda i, j: hk_name(hk_sheet(i, j)), hk_cell_of_name, lambda i, j: hk_files("dtm", i, j),
                        r"\.tif$", origin=(HK_LEFT, HK_BOTTOM), bytes_per_tile=5.8e6, height_offset=HK_DATUM_OFFSET)
HK_DSM = CellSheetTiles("CEDD lidar DSM 2020 0.5 m (surface)", "hong_kong/dsm-2020", HK_CRS, HK_SHEET, 0.5,
                        lambda i, j: hk_name(hk_sheet(i, j)), hk_cell_of_name, lambda i, j: hk_files("dsm", i, j),
                        r"\.tif$", origin=(HK_LEFT, HK_BOTTOM), bytes_per_tile=5.8e6, height_offset=HK_DATUM_OFFSET)

# No orthophoto: the Lands Department's Imagery Map API (XYZ tiles, https://portal.csdi.gov.hk/csdi-webpage/apidoc/
# ImageryMapAPI, read 2026-11-16) requires "Lands Department logo on the map face and Copyright Notice", which the map's
# text attribution cannot give, under terms of its own behind an "I have read and agreed" (its domain
# mapapi.geodata.gov.hk is deprecated on 2027-03-15 for mapapi.hkmapservice.gov.hk)

# Offline boxes (south, north, west, east): a staircase along Hong Kong's boundary, as Hamburg's: the OSM outline (the
# administrative boundary with the territorial waters, relation 913110, osm.search "Hong Kong" of 2026-11-16) cut in
# bands of 0.04 degree south of 22.45 N and of 0.004 degree north of it (the Shenzhen River and Deep Bay), each band's
# pieces as longitude intervals rounded outward to 0.001 degree. Against Natural Earth's admin-1 (10m): 99.93 % of
# Hong Kong's land (1 035.5 of 1 036.2 km²) lies in them, and 7.5 km² of other land (0.72 % of the land in them: strips
# of Shenzhen within a band of the river; Luohu's station at 22.533, 114.117 lies in one); Futian, Luohu, Shekou,
# Yantian and Macau lie outside (tests/test_hong_kong.py). Every sheet of the table meets a box (the least: 12 % of
# 3NE8A, on the border)
HK_BOXES = tuple(("cn-hk", box) for box in (
    (22.13, 22.17, 113.853, 114.503), (22.17, 22.21, 113.820, 114.503), (22.21, 22.25, 113.817, 114.503),
    (22.25, 22.29, 113.831, 114.503), (22.29, 22.33, 113.853, 114.503), (22.33, 22.37, 113.867, 114.503),
    (22.37, 22.41, 113.869, 114.501), (22.41, 22.45, 113.869, 114.482), (22.45, 22.454, 113.907, 114.464),
    (22.454, 22.458, 113.914, 114.462), (22.458, 22.462, 113.921, 114.460), (22.462, 22.466, 113.929, 114.458),
    (22.466, 22.47, 113.936, 114.457), (22.47, 22.474, 113.943, 114.455), (22.474, 22.478, 113.949, 114.455),
    (22.478, 22.482, 113.954, 114.455), (22.482, 22.486, 113.959, 114.455), (22.486, 22.49, 113.964, 114.455),
    (22.49, 22.494, 113.940, 113.947), (22.49, 22.494, 113.969, 114.455), (22.494, 22.498, 113.940, 113.947),
    (22.494, 22.498, 113.974, 114.455), (22.498, 22.502, 113.943, 113.947), (22.498, 22.502, 113.979, 114.455),
    (22.502, 22.506, 113.943, 113.947), (22.502, 22.506, 113.984, 114.009), (22.502, 22.506, 114.016, 114.456),
    (22.506, 22.51, 113.989, 114.004), (22.506, 22.51, 114.023, 114.035), (22.506, 22.51, 114.056, 114.456),
    (22.51, 22.514, 113.994, 113.999), (22.51, 22.514, 114.057, 114.456), (22.514, 22.518, 114.060, 114.456),
    (22.518, 22.522, 114.069, 114.456), (22.522, 22.526, 114.065, 114.069), (22.522, 22.526, 114.075, 114.456),
    (22.526, 22.53, 114.076, 114.456), (22.53, 22.534, 114.078, 114.456), (22.534, 22.538, 114.086, 114.107),
    (22.534, 22.538, 114.116, 114.456), (22.538, 22.542, 114.122, 114.456), (22.542, 22.546, 114.135, 114.145),
    (22.542, 22.546, 114.148, 114.456), (22.546, 22.55, 114.149, 114.227), (22.546, 22.55, 114.234, 114.454),
    (22.55, 22.554, 114.149, 114.225), (22.55, 22.554, 114.236, 114.449), (22.554, 22.558, 114.151, 114.220),
    (22.554, 22.558, 114.244, 114.444), (22.558, 22.562, 114.157, 114.178), (22.558, 22.562, 114.255, 114.439),
    (22.562, 22.566, 114.266, 114.434), (22.566, 22.569, 114.290, 114.371)))

SOURCES: List[Source] = [
    Source(
        id="hong_kong", name="Hong Kong (CEDD lidar 0.5 m)",
        description="Civil Engineering and Development Department (CEDD): LiDAR Data 2020 (helicopter survey "
                    "2019-12-20 to 2020-02-02), terrain (DTM) and surface (DSM) 0.5 m, Hong Kong 1980 Grid; heights "
                    "above the Hong Kong Principal Datum lowered by 1.30 m to about mean sea level (mean sea level "
                    "is about 1.30 m above HKPD, Lands Department); the sea and the land beyond the boundary have "
                    "no data; 57 coastal sheets have a surface model only",
        nmt=HK_DTM, nmpt=HK_DSM, countries=("cn",), regions=("cn-hk",), crs=HK_CRS, credits=(HK_CREDIT,),
        listing=ReadmeRow("Hong Kong (CN)", "CEDD lidar DTM 0.5 m (2020; heights above HKPD lowered by 1.30 m to "
                                            "about mean sea level)",
                          "CEDD lidar DSM 0.5 m (2020, lowered alike; 57 coastal sheets without terrain: europe's "
                          "under it)", "–"),
        offline=HK_BOXES, sample=(22.352, 114.187),  # Lion Rock (R91)
        note="Data: Civil Engineering and Development Department, LiDAR Data (2020), from the CSDI Portal under its "
             "terms and conditions (processed: every height lowered by 1.30 m). Heights are about mean sea level: "
             "the data give them above the Hong Kong Principal Datum, and the Lands Department puts mean sea level "
             "about 1.30 m above it. 57 coastal sheets have a surface model and no terrain: there the terrain comes "
             "from the fallback.",
        coverage=Coverage(provider="CEDD", added="2026-11-16", areas=("hk",), survey="2019–2020")),
]
