"""Japan: five prefectures' lidar grids, one ZIP per small map sheet of the plane rectangular grid: Tokyo's (the
Tokyo Digital Twin's point cloud grids, GeoTIFF), Shizuoka's (VIRTUAL SHIZUOKA's LP grids, text), Yamanashi's (its
point cloud grids, GeoTIFF: terrain and a surface model), Kanagawa's (its point cloud data's MESH grids, fixed-width
.lem text), all 0.5 m, and Miyagi's 1 m grid (text)."""

import os
import re
from functools import lru_cache
from typing import Dict, List, Optional, Tuple

import numpy as np

from ..credit import CC_BY, Credit
from ..indexes.tilings import MetricCellTiling
from ..layers.cellsheets import CellSheetTiles
from ..layers.s3sheets import S3SheetSets
from ..source import Coverage, ReadmeRow, Source

# The national basic map sheets (国土基本図図郭) of a zone of the Japanese plane rectangular coordinate system
# (JGD2011, EPSG:6669 + zone - 1): 1/50000 sheets of 40 x 30 km, columns A-H eastwards from x = -160 km and rows
# A-T southwards from y = +300 km (rows go on past T for the islands south of -300 km: Hachijojima U, Aogashima X);
# in each 10 x 10 1/5000 sheets of 4 x 3 km (the row digit, then the column digit), in each 10 x 10 1/500 sheets of
# 400 x 300 m (row, column). 08OF0485 = x 58 000-58 400, y -122 700..-122 400 in zone VIII. A finer level of
# Shizuoka's FY2022 survey halves the 1/5000 sheet twice instead (quadrant digits 1 north-west, 2 north-east,
# 3 south-west, 4 south-east): 1000 x 750 m (08LD3341 has its north-west corner at (-26 000, -40 500), 08LD3343 at
# (-26 000, -41 250)). An eight-character code alone does not say its level: 08LD3341 is also a 1/500 sheet (row 4,
# column 1). Checked against the publishers' files (wave 0 findings of 2026-11-15, and the tests).
JP_ROWS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
JP_COLUMNS = "ABCDEFGH"
JP_LEFT, JP_TOP = -160_000, 300_000  # the north-west corner of sheet AA in every zone
SHEET_500 = (400, 300)    # a 1/500 sheet, metres (w, h)
SHEET_QUAD = (1000, 750)  # a quadrant sheet of Shizuoka's FY2022 level


def _sheet_offsets(x: int, down: int) -> Optional[Tuple[int, int, int, int]]:
    """The 1/50000 sheet (row, column) of a point x east of JP_LEFT and `down` south of JP_TOP, and the point's
    offsets in it (x, down); None outside the scheme's letters."""
    if not (0 <= x < len(JP_COLUMNS) * 40_000 and 0 <= down < len(JP_ROWS) * 30_000):
        return None
    return down // 30_000, x // 40_000, x % 40_000, down % 30_000


def jp_sheet(zone: int, i: int, j: int) -> Optional[str]:
    """The 1/500 sheet of cell (i, j) of 400 x 300 m from the zone's origin (j northwards): "08OF0485"; None
    outside the scheme."""
    w, h = SHEET_500
    found = _sheet_offsets(i * w - JP_LEFT, JP_TOP - (j + 1) * h)
    if found is None:
        return None
    row, column, x, down = found
    return (f"{zone:02d}{JP_ROWS[row]}{JP_COLUMNS[column]}{down // 3000}{x // 4000}"
            f"{down % 3000 // 300}{x % 4000 // 400}")


def jp_quad_sheet(zone: int, i: int, j: int) -> Optional[str]:
    """The quadrant sheet of cell (i, j) of 1000 x 750 m from the zone's origin: "08LD3341"; None outside."""
    w, h = SHEET_QUAD
    found = _sheet_offsets(i * w - JP_LEFT, JP_TOP - (j + 1) * h)
    if found is None:
        return None
    row, column, x, down = found
    qx, qy = x % 4000, down % 3000
    first = 1 + (qx >= 2000) + 2 * (qy >= 1500)
    second = 1 + (qx % 2000 >= 1000) + 2 * (qy % 1500 >= 750)
    return f"{zone:02d}{JP_ROWS[row]}{JP_COLUMNS[column]}{down // 3000}{x // 4000}{first}{second}"


def _code_parts(code: str, zone: int) -> Optional[Tuple[int, int, int, int, int, int]]:
    if len(code) != 8 or code[:2] != f"{zone:02d}" or code[2] not in JP_ROWS or code[3] not in JP_COLUMNS \
            or not code[4:].isdigit():
        return None
    return (JP_ROWS.index(code[2]), JP_COLUMNS.index(code[3])) + tuple(int(c) for c in code[4:])


def jp_cell(zone: int, code: str) -> Optional[Tuple[int, int]]:
    """The cell (i, j) of a 1/500 sheet's code, None when it is not one of the zone."""
    parts = _code_parts(code, zone)
    if parts is None:
        return None
    row, column, r5, c5, r, c = parts
    w, h = SHEET_500
    cell = ((JP_LEFT + column * 40_000 + c5 * 4000 + c * 400) // w,
            (JP_TOP - row * 30_000 - r5 * 3000 - r * 300) // h - 1)
    return cell if jp_sheet(zone, *cell) == code else None


def jp_quad_cell(zone: int, code: str) -> Optional[Tuple[int, int]]:
    """The cell (i, j) of a quadrant sheet's code, None when it is not one of the zone."""
    parts = _code_parts(code, zone)
    if parts is None or not (1 <= parts[4] <= 4 and 1 <= parts[5] <= 4):
        return None
    row, column, r5, c5, first, second = parts
    w, h = SHEET_QUAD
    left = JP_LEFT + column * 40_000 + c5 * 4000 + (first - 1) % 2 * 2000 + (second - 1) % 2 * 1000
    top = JP_TOP - row * 30_000 - r5 * 3000 - (first - 1) // 2 * 1500 - (second - 1) // 2 * 750
    cell = left // w, top // h - 1
    return cell if jp_quad_sheet(zone, *cell) == code else None


def sheet_name(code: Optional[str]) -> Optional[str]:
    """A sheet's cached file under its layer's folder (without .tif): <1/50000 letters>/<1/5000 digits>/<code>."""
    return None if code is None else f"{code[2:4]}/{code[4:6]}/{code}"


def code_of_name(name: str) -> str:
    """The code at the end of a cached name (sheet_name), '' when there is none."""
    return name.rsplit("/", 1)[-1]


# --- Tokyo ------------------------------------------------------------------------------------------------------
# The Tokyo Digital Twin's point cloud data (東京都デジタルツイン), its 0.5 m grids (「グリッドデータ（0.50m）」): one ZIP of
# one GeoTIFF per 1/500 sheet of zone IX (EPSG:6677) at <TK_BUCKET>/<folder>/dig/grd50/<sheet>.zip, the folder 2023
# for Tama and the Izu islands (surveyed 2022-07 to 2023-01) and 2024 for the 23 wards (2023-03 to 04); Ogasawara was
# not surveyed. Each GeoTIFF is 800 x 600 px of float32 on the sheet's box. Tama's and the islands' name EPSG:6677,
# "Area", nodata 1.70141e38; the wards' name a PROJCS "JGD2011 / Japan Plane Rectangular CS IX" without an EPSG code,
# AREA_OR_POINT=Point (GDAL's transform lands on the sheet's box: tests/test_japan.py) and nodata -32767: read in
# EPSG:6677 whatever they name. Island coasts hold bathymetry (Mikurajima's 09RD8410: -12.2 to -6.5 m on 1.6 % of
# the sheet): kept as water at their heights next to the sea filled at 0 m where a sheet has no data, it made false
# lines (at Mikurajima, radius 800 m, 2026-11-15: 12 % of the data below 0 m, 49 of 341 lines, 4 of 26 spots, joined
# two points of that 0 m fill across the seabed). So heights below TK_ISLAND_FLOOR are no data on the Izu islands'
# sheets (the user's decision of 2026-11-16, the rule of france.OVERSEAS_FLOOR): inside the sea zone the sea fill puts
# 0 m there, outside it they are gaps on land filled from the fallback; the water above the floor and the land are
# kept (R92 at Mikurajima, 2026-11-16: 310 lines in 24 spots without the floor, 47 of them on that fill; 263 in 20
# with it, the same lines but those 47). Applied where the tiles are read onto the grid (TokyoSheets.floor_of, mosaic.prepare_layer), never when one
# is written: a sheet cached before gives what a fresh one gives. Not on the mainland's sheets: the eastern wards
# hold real land down to -4.42 m. The bucket denies listing, so a missing key answers 403: a static table of the
# sheets (tools/tokyo_sheets.py, from the publisher's index vector tiles) says which exist, a sheet outside it is
# never asked, a 403 or 404 for one in it is an error of that tile. Files may be smaller than their sheet (the edge
# of a survey), and the sheets along the line between Tama and the wards are in both folders: each sheet is composed
# on its box (CellSheetTiles), the newer folder first. The surveys are frozen: a versioned folder, the table
# refreshed by hand.
TK_BUCKET = "https://gic-tokyo.s3.ap-northeast-1.amazonaws.com"
TK_CRS = "EPSG:6677"
TK_ZONE = 9
TK_SHEETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tokyo_sheets.npz")


@lru_cache(maxsize=None)
def _tk_table() -> Dict[str, Tuple[int, ...]]:
    """The folders of each sheet, newest first (tokyo_sheets.npz)."""
    table: Dict[str, Tuple[int, ...]] = {}
    with np.load(TK_SHEETS) as saved:
        for code, folder in zip(saved["codes"], saved["folders"]):
            table[code.decode()] = table.get(code.decode(), ()) + (int(folder),)
    return table


def tk_files(i: int, j: int) -> List[Tuple[str, str, int]]:
    """The ZIPs of the sheet of cell (i, j), newest folder first: (name, url, folder); none when Tokyo has none
    (not in the table). The 85 sheets along the line between Tama and the 23 wards are in both folders, each file
    partial (09KD8388: 188 013 pixels in 2023's, 9 414 in 2024's)."""
    code = jp_sheet(TK_ZONE, i, j)
    folders = () if code is None else _tk_table().get(code, ())
    return [(f"{folder}_{code}", f"{TK_BUCKET}/{folder}/dig/grd50/{code}.zip", folder) for folder in folders]


# The Izu islands' sheets lie south of TK_ISLANDS_NORTH (metres north of zone IX's origin: the northern edge of the
# 1/50000 row N), the mainland's north of it: the mainland's southernmost sheet (09LD8148) ends at y = -55 500,
# Oshima's northernmost (09OC4931) at y = -132 900, 77.4 km of sea between them (tests/test_japan.py checks every
# sheet of the table against TK_MAINLAND_BOXES and TK_ISLAND_BOXES)
TK_ISLANDS_NORTH = -90_000
TK_ISLAND_FLOOR = -1.0


def tk_island(i: int, j: int) -> bool:
    """Whether the sheet of cell (i, j) is one of the Izu islands' (its box south of TK_ISLANDS_NORTH)."""
    return (j + 1) * SHEET_500[1] <= TK_ISLANDS_NORTH


class TokyoSheets(CellSheetTiles):
    """Tokyo's grid sheets, with heights below TK_ISLAND_FLOOR as no data on the Izu islands' sheets only."""

    def floor_of(self, path: str) -> Optional[float]:
        """The floor of a cached sheet by its code (the file's name): TK_ISLAND_FLOOR on an island's sheet, none on
        the mainland's; a file that is no sheet of zone IX is an error."""
        cell = jp_cell(TK_ZONE, os.path.splitext(os.path.basename(path))[0])
        if cell is None:
            raise ValueError(f"{os.path.basename(path)}: no sheet of Tokyo's grid")
        return TK_ISLAND_FLOOR if tk_island(*cell) else None


# bytes_per_tile: the ZIPs of a land sheet are 1.4-1.9 MB (wave 0's samples); 169 MB for 117 sheets at Okutama
# (tools/check_source.py, 2026-11-15): 1.45 MB a sheet; 1.7 MB, in the upper part of the samples' range, so the
# estimate (and the quota) errs on the side of more
TK_DTM = TokyoSheets("Tokyo Digital Twin grid 0.5 m (terrain)", "tokyo/grd50/2022-2023", TK_CRS, SHEET_500, 0.5,
                     lambda i, j: sheet_name(jp_sheet(TK_ZONE, i, j)),
                     lambda name: jp_cell(TK_ZONE, code_of_name(name)), tk_files, r"\.tif$", bytes_per_tile=1.7e6)

# The Tokyo Open Data terms (東京都オープンデータ利用規約, https://portal.data.metro.tokyo.lg.jp/terms/, of 2017-03-24, read
# 2026-11-15): CC BY 4.0, credited as 「【ライセンスされている著作物のタイトル】、東京都・【その他の著作権者】、クリエイティブ・コモンズ・
# ライセンス 表示4.0国際（https://creativecommons.org/licenses/by/4.0/deed.ja）」; a changed work adds before it 「この
# 【作品・アプリ・データベース等】は、以下の著作物を改変して利用しています。」, which credit.PROCESSED_NOTE says with every run; and
# 「編集・加工をした情報を、東京都又は都内区市町村…が作成したかのような態様で公表・利用することを禁止します。」 (nothing of ours says
# Tokyo made it). The catalogue's records (t000029d0000000020, 19, 24) are CC BY 4.0. No request limits published
# (the terms and the catalogue's records); the bucket is Tokyo's own (it pays the egress): two connections at once
TK_TERMS = "https://portal.data.metro.tokyo.lg.jp/terms/"
TK_CREDIT = Credit("Tokyo Digital Twin point cloud data, 0.5 m grids (Tokyo Metropolitan Government)",
                   "東京都デジタルツイン 多摩地域点群データ、東京都デジタルツイン 島しょ地域点群データ、東京都デジタルツイン実現"
                   "プロジェクト 区部点群データ、東京都、クリエイティブ・コモンズ・ライセンス 表示4.0国際"
                   "（https://creativecommons.org/licenses/by/4.0/deed.ja）",
                   *CC_BY, notice=f"Tokyo Open Data terms of use: {TK_TERMS}")

# Offline boxes (south, north, west, east): Tokyo's mainland in bands of 0.05 degrees of its outline and of its
# sheets (keeping off Kanagawa's, Yamanashi's and Saitama's land where a band allows), and the Izu islands by groups
# (Oshima; Toshima, Niijima, Shikinejima; Kozushima; Miyakejima, Mikurajima and the rocks west of them; Hachijojima
# and Aogashima), clear of Shizuoka's boxes: every sheet of the table lies in them (tests/test_japan.py)
TK_MAINLAND_BOXES = (
    (35.48, 35.55, 139.42, 139.86), (35.54, 35.60, 139.34, 139.86), (35.60, 35.65, 139.16, 139.89),
    (35.65, 35.70, 139.05, 139.93), (35.70, 35.75, 138.99, 139.93), (35.75, 35.80, 138.97, 139.90),
    (35.79, 35.85, 138.94, 139.85), (35.85, 35.91, 138.93, 139.18))
TK_ISLAND_BOXES = (
    (34.60, 34.85, 139.33, 139.47), (34.30, 34.60, 139.17, 139.32), (34.15, 34.30, 139.05, 139.22),
    (33.75, 34.15, 139.04, 139.65), (32.40, 33.20, 139.60, 139.90))
TK_BOXES = tuple(("jp-13", box) for box in TK_MAINLAND_BOXES + TK_ISLAND_BOXES)
# Tokyo's land along Yamanashi's border west of those boxes (they keep off Yamanashi's land), for Yamanashi's gap
# filling only (tools/border_study.py boxes: 94 % without it, 2026-11-26), and along Kanagawa's border south of
# Hachioji and west of Machida (94 % without it, 2026-11-27)
TK_BORDER_BOXES = ((35.60, 35.92, 138.90, 139.20), (35.55, 35.60, 139.22, 139.35))


# --- Shizuoka ---------------------------------------------------------------------------------------------------
# VIRTUAL SHIZUOKA (the prefecture's point clouds, s3://virtual-shizuoka, AWS Open Data): the LP (land lidar) grid
# data 「LPデータ グリッドデータ」, 0.5 m points as text, one ZIP per sheet of zone VIII (EPSG:6676) at
# <SZ_BUCKET>/<FY>/LP/Grid/08/<1/50000 letters>/<1/5000 digits>/<sheet>[_2].zip, the folders FY2019, 2020, 2021,
# 2025 on 1/500 sheets (400 x 300 m) and FY2022 (the Southern Alps) on quadrant sheets (1000 x 750 m). Points on
# .25/.75 m (pixel edges on whole metres), x fastest, rows north to south, missing points left out; "x y z" lines
# (millimetres or centimetres; the FY2022 members up to 87 MB of text) or "n,x,y,z,flag" CSV (FY2021's centre and
# west, about 15 000 files of 18 MB, and FY2025's north-west: decimetres; SheetFile's CSV branch). A sheet can be in
# two surveys and as a plain and a `_2` file of one survey, each with points the other lacks (08NF7013 in FY2019 and
# FY2020): composed newest survey first, the older only for holes, the fuller of a pair first (SheetSets,
# SheetSetFile). The sea is left out (LP); the ALB (bathymetric lidar) grids hold the seabed below the cliffs and are
# not used. No surface model as rasters (LAS only). Objects were uploaded again in place (2025-06, 2025-10,
# 2026-11-04): the ETag is part of each file's name. Listed 2026-11-15: 64 304 LP grid keys, 63 010 distinct 1/500
# sheets and 695 quadrant sheets, 379 GB.
SZ_BUCKET = "https://virtual-shizuoka.s3.ap-northeast-1.amazonaws.com"
SZ_CRS = "EPSG:6676"
SZ_ZONE = 8
SZ_QUAD_YEARS = (2022,)  # the surveys on quadrant sheets
_SZ_KEY = re.compile(r"(\d{4})/LP/Grid/08/([A-Z]{2})/(\d\d)/(08[A-Z]{2}\d{4})(_2)?\.zip")


def block_prefixes(head: str, box: Tuple[float, float, float, float]) -> List[str]:
    """The prefixes <head><1/50000 letters>/ of the 1/50000 sheets (40 x 30 km) over a box (left, bottom, right,
    top in the zone's metres)."""
    left, bottom, right, top = box
    columns = range(max(0, int((left - JP_LEFT) // 40_000)),
                    min(len(JP_COLUMNS) - 1, int((right - JP_LEFT) // 40_000)) + 1)
    rows = range(max(0, int((JP_TOP - top) // 30_000)), min(len(JP_ROWS) - 1, int((JP_TOP - bottom) // 30_000)) + 1)
    return [f"{head}{JP_ROWS[r]}{JP_COLUMNS[c]}/" for r in rows for c in columns]


def sz_prefixes(folder: str, box: Tuple[float, float, float, float]) -> List[str]:
    """The prefixes of a survey's folder ("2019/") under which the files of a box (left, bottom, right, top in
    zone VIII) lie: one per 1/50000 sheet (40 x 30 km) over it."""
    return block_prefixes(f"{folder}LP/Grid/08/", box)


def sz_key(key: str) -> Optional[Tuple[int, str, Tuple[int, int]]]:
    """(survey year, level "q" or "s", cell) of a listed key, None when it is not an LP grid sheet."""
    match = _SZ_KEY.fullmatch(key)
    if not match or match.group(2) != match.group(4)[2:4] or match.group(3) != match.group(4)[4:6]:
        return None
    year = int(match.group(1))
    level = "q" if year in SZ_QUAD_YEARS else "s"
    cell = (jp_quad_cell if level == "q" else jp_cell)(SZ_ZONE, match.group(4))
    return None if cell is None else (year, level, cell)


SZ_FOLDER = "shizuoka/lp-grid"
SZ_LEVELS = {
    "s": MetricCellTiling(SZ_CRS, f"{SZ_FOLDER}/s", SHEET_500, lambda i, j: sheet_name(jp_sheet(SZ_ZONE, i, j)),
                          lambda name: jp_cell(SZ_ZONE, code_of_name(name))),
    "q": MetricCellTiling(SZ_CRS, f"{SZ_FOLDER}/q", SHEET_QUAD, lambda i, j: sheet_name(jp_quad_sheet(SZ_ZONE, i, j)),
                          lambda name: jp_quad_cell(SZ_ZONE, code_of_name(name))),
}

# The README of the data (https://github.com/aigidjp/opendata_virtualshizuoka, read 2026-11-15): "The datasets of
# Virtual Shizuoka is distributed a dual license: CC-BY 4.0 and ODbL." (the prefecture's page: 「CC BY 4.0に基づいた
# 「オープンデータ」として公開しています」): we take CC BY 4.0; no wording prescribed, so the dataset and its owner. The record of
# FY2022's survey (CKAN shizuoka-2022-pointcloud) adds 「本成果の作成に当たっては、関東森林管理局長の承認を得て、航空レーザ
# 計測データを使用した。（承認番号 5関治第142号-1）」: a run that used a FY2022 sheet carries it (S3SheetSets' level credit).
# No request limits published (the README, the AWS registry entry, the prefecture's page); the bucket is
# sponsored by AWS Open Data: two connections at once as a courtesy
SZ_README = "https://github.com/aigidjp/opendata_virtualshizuoka"
SZ_CREDIT = Credit("VIRTUAL SHIZUOKA point cloud data, LP grids (Shizuoka Prefecture)",
                   "VIRTUAL SHIZUOKA point cloud data (Shizuoka Prefecture), CC BY 4.0", *CC_BY,
                   notice=f"VIRTUAL SHIZUOKA open data: {SZ_README}")
SZ_2022_CREDIT = Credit("VIRTUAL SHIZUOKA point cloud data, LP grids FY2022 (Shizuoka Prefecture)",
                        "VIRTUAL SHIZUOKA point cloud data (Shizuoka Prefecture), CC BY 4.0. 本成果の作成に当たっては、"
                        "関東森林管理局長の承認を得て、航空レーザ計測データを使用した。（承認番号 5関治第142号-1）", *CC_BY,
                        notice=f"VIRTUAL SHIZUOKA open data: {SZ_README}")
# The listed bytes of a sheet's newest survey are the estimate (S3SheetSets.estimate); the mean over every LP grid
# key (379 GB / 64 304, 2026-11-15) stands for a sheet whose listing is not at hand
SZ_DTM = S3SheetSets("VIRTUAL SHIZUOKA LP grid 0.5 m (terrain)", SZ_BUCKET, r"\d{4}/", sz_prefixes, sz_key,
                     "lp-grid", SZ_FOLDER, SZ_CRS, 0.5, SZ_LEVELS, r"\.txt$", bytes_per_tile=5.9e6,
                     level_credits={"q": ("FY2022 Southern Alps", SZ_2022_CREDIT)}, credit=SZ_CREDIT,
                     splits={"s": SZ_QUAD_YEARS})

# Offline boxes: Shizuoka's outline in bands of 0.05 degrees (with its sea), cut east of Atami and Hatsushima to
# keep off Kanagawa's land; Yamanashi's land south of Mount Fuji's five lakes and of Minobu stays in some bands
SZ_BOXES = tuple(("jp-22", box) for box in (
    (34.37, 34.40, 137.53, 139.01), (34.40, 34.45, 137.52, 139.06), (34.45, 34.50, 137.51, 139.10),
    (34.50, 34.55, 137.50, 139.11), (34.54, 34.60, 137.49, 139.14), (34.60, 34.65, 137.48, 139.17),
    (34.65, 34.70, 137.48, 139.19), (34.70, 34.75, 137.47, 139.19), (34.75, 34.80, 137.47, 139.19),
    (34.79, 34.85, 137.48, 139.19), (34.85, 34.90, 137.55, 139.19), (34.90, 34.95, 137.64, 139.19),
    (34.95, 35.05, 137.68, 139.18), (35.04, 35.10, 137.73, 139.10), (35.10, 35.15, 137.79, 139.10),
    (35.15, 35.20, 137.80, 139.05), (35.20, 35.25, 137.82, 139.00), (35.25, 35.30, 137.88, 139.01),
    (35.29, 35.35, 137.99, 139.02), (35.35, 35.40, 138.09, 139.02), (35.40, 35.45, 138.11, 139.01),
    (35.45, 35.50, 138.11, 138.26), (35.50, 35.55, 138.13, 138.27), (35.54, 35.60, 138.14, 138.26),
    (35.60, 35.65, 138.20, 138.25)))


# --- Yamanashi --------------------------------------------------------------------------------------------------
# Yamanashi Prefecture's point clouds (山梨県点群データ（航空LP・MMS）, G-Spatial's CKAN record yamanashi-pointcloud-2024,
# the prefecture's 新事業チャレンジ推進課): airborne lidar of the whole prefecture, surveyed in 2019-2022 (令和1-4年) by the
# prefecture and, for parts, by MLIT's Fujikawa sabo office and by Tokyo (the record's notes), as 0.5 m grids: one ZIP
# of one GeoTIFF per 1/500 sheet of zone VIII (EPSG:6676) in AIGID's bucket japan-pointcloud (AWS Open Data, the
# sister of virtual-shizuoka; it also holds Tokyo's, Hyogo's and others' point clouds) at
# Yamanashi/<YM_PUBLICATION>/<sequence>/LP/Grid/TIFF/08/<1/50000 letters>/<1/5000 digits>/<sheet>.zip. The sequence
# folders are products (AIGID's README calls them sequence numbers; the record's index layers map them): 03 the
# ground model (「グラウンドデータを基に作成」), 01 DSM1 (classes 1 and 9: the surface with pylons and power lines), 02
# DSM2 (class 1: the surface); a TXT variant beside TIFF is not used. Each GeoTIFF is float32, uncompressed, "Area",
# nodata 1.70141e38, its pixel edges on the sheet's 0.5 m lattice; a sheet on the prefecture's border is smaller
# than its box (08KD3949: 763 x 600 px, 08LD4359: 1 x 3 px) and is composed on its box. Lakes are no data in the
# ground model (a sheet wholly water is listed with no valid pixel: 08LE9188, mid Lake Motosu) and the water's
# surface in both surface models (899.3 m there); a search fills such a gap as land from the fallback (mid Lake
# Kawaguchi, radius 300 m, 2026-11-26: 33 % of the area from the source, 0.90 km² filled from FABDEM + Copernicus,
# lakes 0.00 km², shore from surface 0 px). Heights are orthometric; none below 0 m.
# Versions (2026-11-26): the record's published range "旧" (old: part of the prefecture) is the first publication of
# 2025-03, gic-yamanashi/2024/gridtif/<sheet>.zip indexed by the vector tiles .../2024/Vectortile/gridtif/; "新" (new:
# the whole prefecture) is japan-pointcloud, indexed by .../2024/Vectortile2026/<layer>/ (2026-02-27; layers gridtif,
# dsm1gridtif, dsm2gridtif with MESH_NO and URL). The old files were moved to DEEP_ARCHIVE (not readable without a
# restore) and copied unchanged (08KE3233: the same ETag) into japan-pointcloud with the rest of the prefecture on
# 2025-12-11; every key of 03 and 02 carries that date, versioning is off (version ids null). The files are found
# by the bucket's listing (S3SheetSets, as Shizuoka's): a sheet that is not listed is never asked (the bucket answers
# 404 NoSuchKey), a listed key that answers 404 is its sheet's error; the ETag is part of each file's name, so a file
# uploaded again in place is read again. A 0.25° tile's listing is kept cache.TTL_DAYS["sheet-index"] (180) days:
# a sheet published later is seen when its owner tile is listed again (update.py, or a search after that), the
# listing's pages the only cost of "no sheet here". The listing of the bucket's top folders sees "Yamanashi/" only:
# the publication folder and the sequence are fixed here, a new publication is set by hand (new cache folders).
# No holes on the cliffs where looked (Mizugaki's 08KE3281: 100 % valid, slopes to 88°; 08KD3949 none inside its
# data). No orthophoto: the record offers its 0.25 m orthophoto as per-sheet ZIPs (index tiles .../ortho/) and the
# lidar as 3D Tiles (yamanashi-tile.geospatial.jp), no XYZ, WMTS or WMS service.
# Listed 2026-11-26: 03 37 929 sheets, 36.0 GB; 02 the same sheets, 50.4 GB (11 blocks KD-NE). A block's listing is
# up to 10 pages of 1 000 keys (LE: 10 000 sheets), asked per product for each 0.25° tile a grid touches: a first search
# asked 76 requests for 61 sheets at R95 (77.8 MB) and 142 for 60 sheets at Shichiri-iwa (88.3 MB).
YM_BUCKET = "https://japan-pointcloud.s3.ap-northeast-1.amazonaws.com"
YM_CRS = "EPSG:6676"
YM_ZONE = 8
YM_ROOT = "Yamanashi/"   # the prefecture's top folder in the bucket
YM_PUBLICATION = 2024    # its publication folder
YM_TERRAIN = "03"        # the ground model's sequence folder
YM_SURFACES = {"01": "dsm1", "02": "dsm2"}  # the surface models' sequence folders and their cache names
# The surface model a search reads (nmpt): DSM2 (02, without power lines and pylons) or DSM1 (01, with them). The
# user's choice is pending (agent Y's report of 2026-11-26 gives both); the baselines rest on DSM2. The two are not
# one plus the wires (the cached sheets, 2026-11-26): over a 500 kV line's valley east of Kofu (西群馬幹線) and a
# 154 kV line at Shichiri-iwa, DSM1 lies below DSM2 on 2-5 % of each sheet's pixels (a median of -0.05 to -0.1 m,
# down to -10 m) and the wires stand as swaths up to 305 m above DSM2 (8 954-12 843 pixels in a sheet the 500 kV
# line crosses); inside R95's circle both hold the same values (its lines are equal byte for byte with either)
YM_SURFACE = "02"
YM_SURFACE_TEXT = {"01": "DSM1: ground, trees, buildings, power lines and pylons",
                   "02": "DSM2: ground, trees and buildings, without power lines and pylons"}
_YM_KEY = re.compile(r"Yamanashi/(\d{4})/(\d\d)/LP/Grid/TIFF/08/([A-Z]{2})/(\d\d)/(08[A-Z]{2}\d{4})\.zip")


def ym_product(sequence: str) -> str:
    """The cache name of a sequence folder's product: dem, dsm1, dsm2."""
    return "dem" if sequence == YM_TERRAIN else YM_SURFACES[sequence]


def ym_prefixes(sequence: str):
    """The prefixes function of a product (S3SheetSets): under the top folder YM_ROOT, the product's folder of the
    publication, one prefix per 1/50000 sheet over the box; none under any other top folder (Tokyo's, Hyogo's)."""
    def prefixes(folder: str, box: Tuple[float, float, float, float]) -> List[str]:
        if folder != YM_ROOT:
            return []
        return block_prefixes(f"{YM_ROOT}{YM_PUBLICATION}/{sequence}/LP/Grid/TIFF/08/", box)
    return prefixes


def ym_key(sequence: str):
    """The key parser of a product (S3SheetSets): (the publication's year, level "s", cell) of a sheet's ZIP in the
    product's folder of the publication, None for any other key."""
    def parse(key: str) -> Optional[Tuple[int, str, Tuple[int, int]]]:
        match = _YM_KEY.fullmatch(key)
        if not match or int(match.group(1)) != YM_PUBLICATION or match.group(2) != sequence \
                or match.group(3) != match.group(5)[2:4] or match.group(4) != match.group(5)[4:6]:
            return None
        cell = jp_cell(YM_ZONE, match.group(5))
        return None if cell is None else (YM_PUBLICATION, "s", cell)
    return parse


# The record (package_show, modified 2026-09-14, read 2026-11-26): 「データは、CC BY 4.0/ODbL のデュアルライセンスです」,
# license_id cc-by, 「利用規約及び免責事項による」: the terms PDF (YM_TERMS, 2025-03-27: a disclaimer, prohibited conduct,
# compliance with laws, changes without notice, Japanese law; no credit wording, no request limits). No resource
# description, nor the index ZIP's maps (sakuinzu.zip: four index PDFs), nor AIGID's README or the AWS registry entry
# (japan_pointcloud.yaml: CC BY 4.0) prescribes a credit or names an approval: we take CC BY 4.0 (as for Shizuoka),
# credited with the dataset's title and its owner, the terms linked
YM_RECORD = "https://www.geospatial.jp/ckan/dataset/yamanashi-pointcloud-2024"
YM_TERMS = "https://gic-yamanashi.s3.ap-northeast-1.amazonaws.com/2024/doc/license.pdf"
YM_CREDIT = Credit("Yamanashi Prefecture point cloud data (airborne LP), 0.5 m grids (Yamanashi Prefecture)",
                   "山梨県点群データ（航空LP・MMS）、山梨県、CC BY 4.0", *CC_BY,
                   notice=f"Yamanashi Prefecture point cloud data: {YM_RECORD}; terms of use and disclaimer: "
                          f"{YM_TERMS}")
# bytes_per_tile: the mean listed ZIP (2026-11-26): 03 36.0 GB / 37 929 = 0.95 MB, 02 50.4 GB / 37 929 = 1.33 MB,
# 01 50.4 GB (the survey's count); the listed bytes are the estimate where a listing is at hand
_YM_BYTES = {"03": 0.95e6, "01": 1.33e6, "02": 1.33e6}


def ym_layer(sequence: str) -> S3SheetSets:
    """The layer of a product (a sequence folder): its sheets listed under the publication's folder, cached as
    yamanashi/<product>/<publication>/s/<letters>/<digits>/<year>_<sheet>_<key>.tif, its index answers under
    yamanashi/sheet-index/<product>/."""
    product = ym_product(sequence)
    folder = f"yamanashi/{product}/{YM_PUBLICATION}"
    kind = "terrain" if sequence == YM_TERRAIN else f"surface, {product.upper()}"
    levels = {"s": MetricCellTiling(YM_CRS, f"{folder}/s", SHEET_500, lambda i, j: sheet_name(jp_sheet(YM_ZONE, i, j)),
                                    lambda name: jp_cell(YM_ZONE, code_of_name(name)))}
    return S3SheetSets(f"Yamanashi point cloud grid 0.5 m ({kind})", YM_BUCKET, re.escape(YM_ROOT),
                       ym_prefixes(sequence), ym_key(sequence), product, folder, YM_CRS, 0.5, levels, r"\.tif$",
                       bytes_per_tile=_YM_BYTES[sequence], credit=YM_CREDIT)


YM_DTM = ym_layer(YM_TERRAIN)
YM_DSM = ym_layer(YM_SURFACE)

# Offline boxes (south, north, west, east): bands of 0.05 degrees cut into columns of 0.01 degree, a cell kept when
# it holds a sheet's centre (the listing of 2026-11-26) and Yamanashi's land (Natural Earth's admin-1) is at least
# each neighbour's there, runs of kept cells a box. They hold 4 386 of Yamanashi's 4 520 km² and 2 191 of its 37 929
# sheets lie outside them (border cells), against 118 km² of the neighbours' land (Shizuoka 44, Nagano 27, Saitama 19,
# Tokyo 15, Kanagawa 13; the whole bands held 810). Shizuoka's boxes hold Yamanashi's land south of the five lakes
# and Tokyo's its eastern edge: `yamanashi` comes before both in SOURCES (the first box holding a point wins), its
# boxes keeping off their land as above. YM_BORDER_BOXES, the whole bands, hold the rest along the borders (the
# neighbours' gap filling only)
YM_BOXES = tuple(("jp-19", box) for box in (
    (35.15, 35.20, 138.41, 138.49), (35.20, 35.25, 138.38, 138.51), (35.25, 35.30, 138.36, 138.51),
    (35.30, 35.35, 138.24, 138.51), (35.35, 35.40, 138.23, 138.52), (35.35, 35.40, 138.65, 138.87),
    (35.40, 35.45, 138.24, 138.92), (35.45, 35.50, 138.24, 139.01), (35.50, 35.55, 138.25, 139.10),
    (35.55, 35.60, 138.23, 139.11), (35.60, 35.65, 138.21, 139.12), (35.65, 35.70, 138.19, 139.08),
    (35.70, 35.75, 138.19, 139.00), (35.75, 35.80, 138.18, 138.97), (35.80, 35.85, 138.20, 138.94),
    (35.85, 35.90, 138.30, 138.60), (35.85, 35.90, 138.69, 138.76), (35.90, 35.95, 138.33, 138.44)))
YM_BORDER_BOXES = (
    (35.15, 35.20, 138.37, 138.54), (35.20, 35.25, 138.35, 138.54), (35.25, 35.30, 138.24, 138.53),
    (35.30, 35.35, 138.22, 138.54), (35.35, 35.40, 138.22, 138.92), (35.40, 35.45, 138.23, 138.96),
    (35.45, 35.50, 138.23, 139.07), (35.50, 35.55, 138.23, 139.12), (35.55, 35.60, 138.21, 139.14),
    (35.60, 35.65, 138.18, 139.14), (35.65, 35.70, 138.16, 139.14), (35.70, 35.75, 138.16, 139.07),
    (35.75, 35.80, 138.17, 139.01), (35.80, 35.85, 138.18, 138.98), (35.85, 35.90, 138.21, 138.96),
    (35.90, 35.95, 138.31, 138.79), (35.95, 36.00, 138.34, 138.45))


def ym_source(surface: str, nmpt: Optional[S3SheetSets] = None) -> Source:
    """The source `yamanashi` with the surface model of a sequence folder (YM_SURFACE's values): its layer (nmpt, or
    a new ym_layer) and every text naming it (description, README row, note) follow the one value."""
    return Source(
        id="yamanashi", name="Yamanashi (lidar 0.5 m)",
        description="Yamanashi Prefecture: point cloud data, airborne lidar grids 0.5 m of the whole prefecture "
                    f"(surveys of 2019-2022), terrain and surface ({YM_SURFACE_TEXT[surface]}), JGD2011 / Japan "
                    "Plane Rectangular CS VIII; lakes are no data in the terrain",
        nmt=YM_DTM, nmpt=nmpt or ym_layer(surface), countries=("jp",), regions=("jp-19",), crs=YM_CRS,
        credits=(YM_CREDIT,),
        listing=ReadmeRow("Yamanashi (JP)", "Yamanashi point cloud grid 0.5 m (2019-2022)",
                          f"Yamanashi point cloud grid 0.5 m, {ym_product(surface).upper()} (2019-2022)", "–"),
        offline=YM_BOXES, border_boxes=YM_BORDER_BOXES, neighbours=("tokyo", "shizuoka", "kanagawa", "nagano"),
        sample=(35.8946, 138.5948),  # Mizugaki-yama, 300 m east of R95's centre
        note="Data: Yamanashi Prefecture point cloud data, CC BY 4.0. Airborne lidar of the whole prefecture "
             "(2019-2022; parts flown by MLIT's Fujikawa sabo office and by Tokyo). The surface model is "
             f"{YM_SURFACE_TEXT[surface]}. Lakes have no terrain data.",
        coverage=Coverage(provider="Yamanashi Prefecture", added="2026-11-26", survey="2019–2022"))




# --- Kanagawa --------------------------------------------------------------------------------------------------
# Kanagawa Prefecture's 3D point cloud data (神奈川県 3次元点群データ, six G-Spatial CKAN records kanagawa-2019-pointcloud,
# -2020-1-, -2020-2-, -2021-, -2022- and -2024-pointcloud, the prefecture's デジタル戦略本部室): airborne lidar for its
# forest resources (4 points/m² or more), the forests surveyed in parts from 2019 to 2024 (令和元年度-令和6年度); the
# records' `quality`: no data were taken over towns and harbours without forest, nor over national forests and the
# areas of military bases (yet central Yokohama has data: 95.4 % of a 300 m circle at its station, 2026-11-27). Its
# 0.5 m ground grid (「グリッドデータ（メッシュ形式）」) is one ZIP per quadrant sheet of zone IX (1000 x 750 m, EPSG:6677)
# in AIGID's bucket kanagawa-pointcloud (AWS Open Data) at
# <year>/<nn>/LP/Grid/MESH/09/<1/50000 letters>/<1/5000 digits>/<sheet>.zip: a `.lem` member (_lem_grid: 1 500 rows of
# 2 000 heights in 0.1 m; -9999 no ground: the water of the sea, of lakes and rivers and an unexplained block at
# Owakudani; -1111 outside the survey; heights below 0 m are real, down to -0.5 m at Jogashima) and a `.csv` header
# in cp932 (the survey year, the counts, the corners: equal to the code's box on the seven sheets read, 2026-11-27;
# not read). Lake Ashi is -9999 (its sheet 09MC9132 holds 330 valid cells of 3 000 000), the open sea -1111 and the
# water along the shore -9999: a gap a search fills as land from the fallback, or as sea in its sea zone. Heights
# T.P. (Tokyo Bay mean sea level); pixel edges on whole metres. The folders KG_FOLDERS are composed newest first,
# the older only for holes (Shizuoka's rule): 2024/01 holds every sheet of 2019/01 and 384 of 2020/02's 385, newer
# and with 27 000 more valid cells on 09NC1242 than 2019's; 2020/01 and 2020/02 (one year, two areas, 47 sheets in
# both) go the fuller first (SheetSetFile). Not used: 2022/02 (a 1 m grid of 2022's area), 2019/02 (orthophotos),
# the CSV variant (`n,x,y,z,flag`, 7.6 times the bytes, the water with interpolated heights), 2021's centimetre
# DEM text and the DSM of 2022's area only (2021/01/LP/DSM: no surface model here). Versions (listed 2026-11-27):
# every key of 2019-2022 carries one LastModified, 2025-12-08, and of 2024 2026-07-30, while the ZIPs' members are
# dated 2020-03 to 2025-03: objects are uploaded again in place, so the bucket's listing decides what exists and the
# ETag is part of each file's name (S3SheetSets, as Shizuoka's); a sheet that is not listed is never asked (the
# bucket answers 404 NoSuchKey for a key it does not have), the 0.25° tile's listing kept
# cache.TTL_DAYS["sheet-index"] days. A new year folder is set here by hand (KG_FOLDERS). Listed 2026-11-27: 4 649
# keys of the six folders, 7.99 GB, 3 282 distinct sheets (1 268 in two to four folders); 39 KB is a sheet without a
# valid cell (09MD5023: -1111 but 12 cells of -9999).
KG_BUCKET = "https://kanagawa-pointcloud.s3.ap-northeast-1.amazonaws.com"
KG_CRS = "EPSG:6677"
KG_ZONE = 9
# The year folders and their subfolders of the 0.5 m MESH grid, newest first: a sheet's files go by year (the
# order of the years here); the two subfolders of 2020 are one year, so their files go the fuller first
# (SheetSetFile) and the order inside a year's tuple decides nothing (on 09LC8521, 2026-11-27: 57 242 cells, 2024's
# holes, have both, differing by up to 3.7 m; 2020/02 the fuller there)
KG_FOLDERS: Dict[int, Tuple[str, ...]] = {2024: ("01",), 2022: ("01",), 2021: ("01",), 2020: ("02", "01"),
                                          2019: ("01",)}
_KG_KEY = re.compile(r"(\d{4})/(\d\d)/LP/Grid/MESH/09/([A-Z]{2})/(\d\d)/(09[A-Z]{2}\d{4})\.zip")


def kg_prefixes(folder: str, box: Tuple[float, float, float, float]) -> List[str]:
    """The prefixes of a year folder ("2020/") under which the MESH sheets of a box (left, bottom, right, top in
    zone IX) lie: one per subfolder of KG_FOLDERS and 1/50000 sheet over the box; none for another year."""
    year = int(folder[:4]) if re.fullmatch(r"\d{4}/", folder) else None
    return [p for sub in KG_FOLDERS.get(year, ()) for p in block_prefixes(f"{folder}{sub}/LP/Grid/MESH/09/", box)]


def kg_key(key: str) -> Optional[Tuple[int, str, Tuple[int, int]]]:
    """(year, level "q", cell) of a MESH sheet's ZIP in one of KG_FOLDERS, None for any other key."""
    match = _KG_KEY.fullmatch(key)
    if not match or match.group(2) not in KG_FOLDERS.get(int(match.group(1)), ()) \
            or match.group(3) != match.group(5)[2:4] or match.group(4) != match.group(5)[4:6]:
        return None
    cell = jp_quad_cell(KG_ZONE, match.group(5))
    return None if cell is None else (int(match.group(1)), "q", cell)


KG_FOLDER = "kanagawa/grid-mesh"
KG_LEVELS = {"q": MetricCellTiling(KG_CRS, f"{KG_FOLDER}/q", SHEET_QUAD,
                                   lambda i, j: sheet_name(jp_quad_sheet(KG_ZONE, i, j)),
                                   lambda name: jp_quad_cell(KG_ZONE, code_of_name(name)))}

# The records (package_show, 2026-11-27): license_id cc-by; 2019-2022 prescribe in `restriction` 「本データを利用した制作物
# には「データ提供：（神奈川県環境農政局緑政部森林再生課）」と明示すること。」 beside two conditions (not for crime or other
# wrongful acts; the prefecture is not liable for any damage); the 2024 record (神奈川県 令和6年度県西部、相模原3次元点群
# データ) leaves `restriction` empty: its sheets carry the same line (our choice). AIGID's README and the AWS registry
# entry (kanagawa_pointcloud.yaml) say CC BY 4.0. No request limits published (the records, the README, the
# registry entry, the prefecture's catalogue terms https://www.pref.kanagawa.jp/documents/37447/riyoukiyaku.pdf of
# 2024-02, which no record links); the bucket is in AWS Open Data: two connections at once as a courtesy
KG_RECORDS = "https://www.geospatial.jp/ckan/dataset/kanagawa-2019-pointcloud"  # one of the five with the conditions
KG_RECORD_2024 = "https://www.geospatial.jp/ckan/dataset/kanagawa-2024-pointcloud"
KG_CREDIT = Credit("Kanagawa Prefecture 3D point cloud data, 0.5 m grids 2019-2024 (Kanagawa Prefecture)",
                   "神奈川県 3次元点群データ（令和元年度～令和6年度）グリッドデータ、神奈川県、CC BY 4.0。"
                   "データ提供：（神奈川県環境農政局緑政部森林再生課）", *CC_BY,
                   notice=f"Kanagawa Prefecture 3D point cloud data (G-Spatial Information Center): {KG_RECORDS} "
                          f"and the records of 2020-2022 state these conditions: not to be used for crime or other "
                          f"wrongful acts; Kanagawa Prefecture is not liable for any damage arising from the use of "
                          f"the data (the 2024 record, {KG_RECORD_2024}, states none)")
# bytes_per_tile: the mean listed ZIP of the six folders (7.99 GB / 4 649, 2026-11-27); the listed bytes of a
# sheet's newest file are the estimate where a listing is at hand
KG_DTM = S3SheetSets("Kanagawa point cloud grid 0.5 m (terrain)", KG_BUCKET, r"\d{4}/", kg_prefixes, kg_key,
                     "grid-mesh", KG_FOLDER, KG_CRS, 0.5, KG_LEVELS, r"\.lem$", bytes_per_tile=1.72e6, credit=KG_CREDIT)

# Offline boxes (south, north, west, east): made as Yamanashi's, bands of 0.05 degrees cut into columns of 0.01
# degree, a cell kept when a listed sheet's box meets it (a sheet is 1 km wide: a centre leaves every tenth column
# empty) and Kanagawa's land (the coverage map's outlines, Natural Earth's admin-1) is at least each neighbour's there,
# runs of kept cells a box (the listing of 2026-11-27), and one box more for 1.2 km² of Tanzawa's north with sheets,
# 1.2 km from Yamanashi, that its cell's rule left out (35.50-35.51 N). They hold 2 282 of Kanagawa's 2 423 km²; of the
# 144 km² left out (5.9 %), 60 km² have no sheet (Tokyo Bay's coast of Kawasaki and Yokohama 55, the column of
# Odawara's town 4.4, Oiso's coast 0.7) and 84 km² (3.5 %) lie in cells along the borders where a neighbour's land
# wins (Machida's side 18, Lake Yamanaka's south 18, Kawasaki's bank of the Tama 8.5, the Chitose river at Yugawara
# 7.4, Doshi 5.8, and 26 more in pieces under 5.5). Against 50 km² of the neighbours' land (Tokyo 30, Yamanashi 11,
# Shizuoka 9). Tokyo's and Shizuoka's boxes hold some of Kanagawa's land and Yamanashi's
# 13 km² of it: `kanagawa` comes first in SOURCES. KG_BORDER_BOXES, the whole bands of the sheets, hold the rest along
# the borders (the neighbours' gap filling only), two of them grown east over Kawasaki's coast to 139.80 (no sheet
# there, but Tokyo's border strip asks: tools/border_study.py boxes 93 % without it, 2026-11-27)
KG_BOXES = tuple(("jp-14", box) for box in (
    (35.10, 35.15, 139.07, 139.17), (35.10, 35.15, 139.60, 139.70), (35.15, 35.20, 138.99, 139.17),
    (35.15, 35.20, 139.58, 139.70), (35.20, 35.25, 138.97, 139.16), (35.20, 35.25, 139.56, 139.76),
    (35.25, 35.30, 138.99, 139.17), (35.25, 35.30, 139.18, 139.31), (35.25, 35.30, 139.40, 139.43),
    (35.25, 35.30, 139.47, 139.50), (35.25, 35.30, 139.51, 139.76), (35.30, 35.35, 139.00, 139.68),
    (35.35, 35.40, 138.99, 139.68), (35.40, 35.45, 138.92, 139.70), (35.45, 35.50, 139.00, 139.66),
    (35.50, 35.51, 139.06, 139.09), (35.50, 35.55, 139.09, 139.43), (35.50, 35.55, 139.47, 139.71),
    (35.55, 35.60, 139.11, 139.30), (35.55, 35.60, 139.48, 139.62), (35.60, 35.65, 139.12, 139.18)))
KG_BORDER_BOXES = (
    (35.10, 35.15, 139.02, 139.70), (35.15, 35.20, 138.97, 139.70), (35.20, 35.25, 138.96, 139.76),
    (35.25, 35.30, 138.96, 139.76), (35.30, 35.35, 138.99, 139.68), (35.35, 35.40, 138.90, 139.68),
    (35.40, 35.45, 138.90, 139.70), (35.45, 35.50, 138.92, 139.80), (35.50, 35.55, 139.03, 139.80),
    (35.55, 35.60, 139.10, 139.69), (35.60, 35.65, 139.11, 139.66), (35.65, 35.70, 139.11, 139.23))


# --- Miyagi -----------------------------------------------------------------------------------------------------
# Miyagi Prefecture's 3D point cloud data (【宮城県】3次元点群データ, dataset 915 of the prefecture's open data portal
# miyagi.dataeye.jp, its 防災砂防課; published 2025-03-25), labelled 2023 (the files are dated 2024-01 to 03; the
# survey years per area are not published): its 1 m grid 「グリッドデータ」, one ZIP per quadrant sheet of zone X
# (1000 x 750 m, EPSG:6678) in the prefecture's bucket gic-miyagi at <MG_BUCKET>/2024/1mcsv/<region>/<sheet>.zip, one
# member <sheet>_1g.txt of "id,x,y,z,flag" rows (SheetFile's CSV branch, every row kept as Shizuoka's): 750 000 rows of
# cell centres on .5 m (pixel edges on whole metres), north-west first, z in 0.1 m; the flag is undocumented and
# measured on 2026-11-27 on six sheets: 1 (48-86 % of a sheet) and 0 (14-52 %) on all kinds of ground, 0 rarer on
# flat water (perhaps cells with and without ground points: a guess), -9999 cells without ground, heights
# interpolated across them (the Okura dam's lake flat at 269.1-269.8 m on 10QD1731, a block of 464 cells on Banji-iwa
# across the seam of 10QD3311 and 10QD3312, the coast at -0.4 m on 10QE1532); no sheet holds a z of no data. The rows
# flagged -9999 keep the heights the provider interpolated: the user's decision of 2026-11-27 (at R98's place 115 lines
# in 14 spots with them, 98 in 12 with them as no data: 17 lines anchored on that block). A sheet on the coast or at
# the survey's edge holds fewer rows (10QE3444: 183): the rest is no data. The bucket denies listing and answers 403 for a key it does not have, and the region
# folder 01-07 cannot be derived from a code: the static table miyagi_sheets.npz (tools/miyagi_sheets.py, from the
# portal's list, resource 1523) says which exist where, a sheet outside it is never asked, a 403 or 404 for one in it
# is an error of that tile (CellSheetTiles, as Tokyo's). 10PE0822 is listed in 02 and 03 (two files, composed the
# fuller first). The table holds 9 570 sheets (48.8 GB listed, 2026-11-27): the mountainous west whole, the eastern
# lowlands and coast in parts (the sheet index's 1 157 sheets without a grid lie there: Wakabayashi's plain 3.6 km and
# Kinkasan 1.6 km from the nearest sheet); where no sheet lies within 2 km of a centre, --source auto takes `europe`
# (instead_without_data, the table's has_data_near: no request; the user's decision of 2026-11-27, as for Mexico's
# partial lidar). Heights T.P.
# (presumed: not published; the coast's rows near 0 m agree); no surface model is published. Versions: a single
# publication (Last-Modified 2025-03-18 on the sheets read): cached as <MG_FOLDER>/<name>.tif in a versioned folder,
# the table refreshed by hand (a re-published sheet is not read again unless its tile is deleted).
MG_BUCKET = "https://gic-miyagi.s3.ap-northeast-1.amazonaws.com"
MG_CRS = "EPSG:6678"
MG_ZONE = 10
MG_YEAR = 2023  # the dataset's label: the order of a sheet's two files (one year: the fuller first)
MG_SHEETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "miyagi_sheets.npz")
MG_FOLDER = "miyagi/1mcsv/2023"


@lru_cache(maxsize=None)
def _mg_table() -> Dict[str, Tuple[int, ...]]:
    """The region folders of each sheet (miyagi_sheets.npz)."""
    table: Dict[str, Tuple[int, ...]] = {}
    with np.load(MG_SHEETS) as saved:
        for code, folder in zip(saved["codes"], saved["folders"]):
            table[code.decode()] = table.get(code.decode(), ()) + (int(folder),)
    return table


def mg_files(i: int, j: int) -> List[Tuple[str, str, int]]:
    """The ZIPs of the quadrant sheet of cell (i, j): (name, url, year); none when Miyagi has none (not in the
    table)."""
    code = jp_quad_sheet(MG_ZONE, i, j)
    folders = () if code is None else _mg_table().get(code, ())
    return [(f"{folder:02d}_{code}", f"{MG_BUCKET}/2024/1mcsv/{folder:02d}/{code}.zip", MG_YEAR) for folder in folders]


# bytes_per_tile: the mean listed ZIP (48.79 GB / 9 571, 2026-11-27): 5.1 MB, the median 5.1 MB too
MG_DTM = CellSheetTiles("Miyagi point cloud grid 1 m (terrain)", MG_FOLDER, MG_CRS, SHEET_QUAD, 1.0,
                        lambda i, j: sheet_name(jp_quad_sheet(MG_ZONE, i, j)),
                        lambda name: jp_quad_cell(MG_ZONE, code_of_name(name)), mg_files, r"\.txt$",
                        bytes_per_tile=5.1e6)

# The portal's terms (https://miyagi.dataeye.jp/pages/terms, read 2026-11-27): its content is CC BY 4.0 unless noted
# (the grid list's resource page: 「ライセンス CC BY 4.0（クリエイティブ・コモンズ表示4.0国際）」), and a user is asked to
# show the source as 「①データセットのメタデータの作成者欄に記載する組織名、②リソースの名称及び③リソースのURL」: 宮城県, the
# list's resource and its page. The dataset's description (not the grid list's) prints 「測量法に基づく国土地理院長承認（使用）
# R6JHs966」, as does the description of its CS map list (resource 1521): carried as Shizuoka's approval sentence is.
# No request limits published (the terms, the dataset's and the resource's pages); the bucket is the prefecture's own
# (it pays the egress): two connections at once, and tools/miyagi_sheets.py asks the portal once a run
MG_RESOURCE = "https://miyagi.dataeye.jp/resources/1523"
MG_TERMS = "https://miyagi.dataeye.jp/pages/terms"
# Offline boxes (south, north, west, east): made as Kanagawa's, cells of 0.05 x 0.01 degree kept where a sheet of the
# table meets them and Miyagi's land is at least each neighbouring prefecture's (Iwate, Akita, Yamagata, Fukushima;
# Natural Earth's admin-1). They hold 6 911 of Miyagi's 7 513 km² (the rest mostly the eastern lowlands without a
# sheet, where a centre goes to europe anyway: instead_without_data) against 118 km² of the neighbours' land (Iwate 54,
# Yamagata 29, Fukushima 20, Akita 14). No neighbours are declared (none of them has a source): no border boxes
MG_BOXES = tuple(("jp-04", box) for box in (
    (37.75, 37.80, 140.74, 140.78), (37.80, 37.85, 140.68, 140.85), (37.85, 37.90, 140.67, 140.86),
    (37.90, 37.95, 140.47, 140.88), (37.95, 38.00, 140.27, 140.88), (38.00, 38.05, 140.28, 140.88),
    (38.05, 38.10, 140.37, 140.88), (38.10, 38.15, 140.43, 140.91), (38.15, 38.20, 140.46, 140.86),
    (38.20, 38.25, 140.46, 140.91), (38.25, 38.30, 140.47, 141.11), (38.25, 38.30, 141.47, 141.55),
    (38.30, 38.35, 140.51, 141.18), (38.30, 38.35, 141.40, 141.55), (38.35, 38.40, 140.54, 141.20),
    (38.35, 38.40, 141.35, 141.55), (38.40, 38.45, 140.57, 141.55), (38.45, 38.50, 140.58, 141.46),
    (38.50, 38.55, 140.56, 141.43), (38.55, 38.60, 140.55, 141.46), (38.60, 38.65, 140.54, 141.48),
    (38.65, 38.70, 140.60, 141.41), (38.70, 38.75, 140.61, 141.53), (38.75, 38.80, 140.61, 141.18),
    (38.75, 38.80, 141.26, 141.51), (38.80, 38.85, 140.57, 141.12), (38.80, 38.85, 141.45, 141.55),
    (38.85, 38.90, 140.59, 140.99), (38.85, 38.90, 141.45, 141.60), (38.90, 38.95, 140.71, 140.88),
    (38.90, 38.95, 141.48, 141.60), (38.95, 39.00, 141.49, 141.60)))
MG_CREDIT = Credit("Miyagi Prefecture 3D point cloud data, 1 m grid 2023 (Miyagi Prefecture)",
                   f"宮城県、【宮城県】3次元点群データ_データ一覧_グリッドデータ_CSV_2023（{MG_RESOURCE}）、CC BY 4.0。"
                   "測量法に基づく国土地理院長承認（使用）R6JHs966", *CC_BY,
                   notice=f"Miyagi Prefecture and municipalities open data portal, terms of use: {MG_TERMS}")


# Kanagawa, then Yamanashi first: their offline boxes overlap Tokyo's and Shizuoka's (and Yamanashi's Kanagawa's)
# over their own land (KG_BOXES, YM_BOXES); the first box holding a point wins
SOURCES: List[Source] = [
    Source(
        id="kanagawa", name="Kanagawa (lidar 0.5 m)",
        description="Kanagawa Prefecture: 3D point cloud data, airborne lidar grids 0.5 m (terrain) of its forests, "
                    "surveys of 2019-2024 composed newest first, JGD2011 / Japan Plane Rectangular CS IX; no "
                    "surface model; parts of towns and harbours, national forests and the areas of military bases "
                    "were not surveyed; water is no data",
        nmt=KG_DTM, countries=("jp",), regions=("jp-14",), crs=KG_CRS, credits=(KG_CREDIT,),
        listing=ReadmeRow("Kanagawa (JP)", "Kanagawa point cloud grid 0.5 m (forests, 2019-2024)", "–", "–"),
        offline=KG_BOXES, border_boxes=KG_BORDER_BOXES, neighbours=("tokyo", "shizuoka", "yamanashi"),
        sample=(35.1317, 139.6232),  # Jogashima's south coast (R97's centre)
        note="Data: Kanagawa Prefecture 3D point cloud data, CC BY 4.0. Terrain only (no surface model: trees and "
             "buildings are not in the data). Surveyed for the forests (2019-2024), most of the prefecture: parts of "
             "towns and harbours, national forests and the areas around military bases have no data, nor have "
             "lakes, rivers and the sea; the sea is filled at 0 m within the search's sea zone, the other gaps "
             "(lakes and rivers too) from the fallback model as land.",
        coverage=Coverage(provider="Kanagawa Prefecture", added="2026-11-27", partial=True, survey="2019–2024")),
    ym_source(YM_SURFACE, YM_DSM),
    Source(
        id="tokyo", name="Tokyo (Digital Twin lidar 0.5 m)",
        description="Tokyo Metropolitan Government: Tokyo Digital Twin point cloud grids 0.5 m (terrain) of Tama "
                    "(2022-2023), the Izu islands (2022-2023) and the 23 wards (2023), JGD2011 / Japan Plane "
                    "Rectangular CS IX; no surface model; on the Izu islands' sheets heights below -1 m (the seabed "
                    "along their coasts) are taken as no data",
        nmt=TK_DTM, countries=("jp",), regions=("jp-13",), crs=TK_CRS, credits=(TK_CREDIT,),
        listing=ReadmeRow("Tokyo (JP)", "Tokyo Digital Twin lidar grid 0.5 m (Tama, Izu islands 2022-2023; "
                                        "23 wards 2023)", "– (point clouds only)", "–"),
        offline=TK_BOXES, sample=(35.8179, 139.0875),  # Okutama (R84)
        note="Data: Tokyo Metropolitan Government, Tokyo Digital Twin point cloud data, CC BY 4.0 (Tokyo Open Data "
             "terms). Terrain only (no surface model: trees and buildings are not in the data). Ogasawara was not "
             "surveyed. Near the Izu islands' coasts the grids hold some seabed heights: there heights below -1 m are "
             "taken as no data, filled as sea at 0 m in the search's sea zone and outside it as gaps on land from "
             "the fallback model.",
        coverage=Coverage(provider="Tokyo Metropolitan Government", added="2026-11-15", partial=True,
                          survey="2022–2023"),
        neighbours=("yamanashi", "kanagawa"), border_boxes=TK_BORDER_BOXES),
    Source(
        id="shizuoka", name="Shizuoka (VIRTUAL SHIZUOKA lidar 0.5 m)",
        description="Shizuoka Prefecture: VIRTUAL SHIZUOKA land lidar (LP) grids 0.5 m (terrain), surveys of "
                    "FY2019-2022 and FY2025 composed newest first, JGD2011 / Japan Plane Rectangular CS VIII; no "
                    "surface model; decimetre heights in the centre, west and north-west; the sea is left out (the "
                    "bathymetric ALB grids are not used)",
        nmt=SZ_DTM, countries=("jp",), regions=("jp-22",), crs=SZ_CRS, credits=(SZ_CREDIT, SZ_2022_CREDIT),
        listing=ReadmeRow("Shizuoka (JP)", "VIRTUAL SHIZUOKA lidar grid 0.5 m (FY2019-2022, FY2025)",
                          "– (point clouds only)", "–"),
        offline=SZ_BOXES, sample=(34.8937, 139.1368),  # Jogasaki (R85)
        note="Data: VIRTUAL SHIZUOKA point cloud data (Shizuoka Prefecture), CC BY 4.0. Terrain only (no surface "
             "model: trees and buildings are not in the data). In the centre, west and north-west the heights are "
             "given to the decimetre. The sea is left out; the bathymetric (ALB) grids are not used.",
        coverage=Coverage(provider="Shizuoka Prefecture", added="2026-11-15", survey="2019–2025"),
        neighbours=("yamanashi", "kanagawa", "nagano")),
    Source(
        id="miyagi", name="Miyagi (lidar 1 m)",
        description="Miyagi Prefecture: 3D point cloud data, airborne lidar grid 1 m (terrain), labelled 2023, "
                    "JGD2011 / Japan Plane Rectangular CS X; the mountainous west whole, the eastern lowlands and "
                    "coast in parts; no surface model",
        nmt=MG_DTM, countries=("jp",), regions=("jp-04",), crs=MG_CRS, credits=(MG_CREDIT,),
        listing=ReadmeRow("Miyagi (JP), where it has lidar", "Miyagi point cloud grid 1 m (2023)", "–", "–"),
        offline=MG_BOXES, sample=(38.2955, 140.5330),  # Banji-iwa (R98)
        # Where no sheet lies within 2 km of the centre (Wakabayashi's and the Natori plain; Kinkasan's eastern
        # half, while its western half lies within 2 km of the Oshika peninsula's sheets), --source auto takes europe
        instead_without_data="europe",
        note="Data: Miyagi Prefecture 3D point cloud data, CC BY 4.0 (approved under the Survey Act by the GSI, "
             "R6JHs966). Terrain only (no surface model: trees and buildings are not in the data). The whole "
             "mountainous west; much of the eastern lowlands and the coast (the Sendai plain, the Oshika and "
             "Sanriku coast, Kinkasan) has no grid, filled from the fallback model. The publisher labels the "
             "survey 2023.",
        coverage=Coverage(provider="Miyagi Prefecture", added="2026-11-27", partial=True, survey="2023")),
]
