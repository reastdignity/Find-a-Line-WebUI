"""Japan: two prefectures' 0.5 m lidar terrain grids, one ZIP per small map sheet of the plane rectangular grid:
Tokyo's (the Tokyo Digital Twin's point cloud grids, GeoTIFF) and Shizuoka's (VIRTUAL SHIZUOKA's LP grids, text)."""

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
# the sheet): no floor is built. The water handling keeps such data as water at their heights and fills the sea
# without data at 0 m; at Mikurajima (radius 800 m, 2026-11-15) 12 % of the data lay below 0 m, 49 of 341 lines (4
# of 26 spots) joined two points of that 0 m fill across the seabed: a floor is being decided (wave 1's report). The
# bucket denies listing, so a missing key answers 403: a static table of the sheets (tools/tokyo_sheets.py, from the
# publisher's index vector tiles) says which exist, a sheet outside it is never asked, a 403 or 404 for one in it is
# an error of that tile. Files may be smaller than their sheet (the edge of a survey), and the sheets along the line
# between Tama and the wards are in both folders: each sheet is composed on its box (CellSheetTiles), the newer
# folder first. The surveys are frozen: a versioned folder, the table refreshed by hand.
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


# bytes_per_tile: the ZIPs of a land sheet are 1.4-1.9 MB (wave 0's samples); 169 MB for 117 sheets at Okutama
# (tools/check_source.py, 2026-11-15): 1.45 MB a sheet; 1.7 MB, in the upper part of the samples' range, so the
# estimate (and the quota) errs on the side of more
TK_DTM = CellSheetTiles("Tokyo Digital Twin grid 0.5 m (terrain)", "tokyo/grd50/2022-2023", TK_CRS, SHEET_500, 0.5,
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
TK_BOXES = tuple(("jp-13", box) for box in (
    (35.48, 35.55, 139.42, 139.86), (35.54, 35.60, 139.34, 139.86), (35.60, 35.65, 139.16, 139.89),
    (35.65, 35.70, 139.05, 139.93), (35.70, 35.75, 138.99, 139.93), (35.75, 35.80, 138.97, 139.90),
    (35.79, 35.85, 138.94, 139.85), (35.85, 35.91, 138.93, 139.18),
    (34.60, 34.85, 139.33, 139.47), (34.30, 34.60, 139.17, 139.32), (34.15, 34.30, 139.05, 139.22),
    (33.75, 34.15, 139.04, 139.65), (32.40, 33.20, 139.60, 139.90)))


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


def sz_prefixes(folder: str, box: Tuple[float, float, float, float]) -> List[str]:
    """The prefixes of a survey's folder ("2019/") under which the files of a box (left, bottom, right, top in
    zone VIII) lie: one per 1/50000 sheet (40 x 30 km) over it."""
    left, bottom, right, top = box
    columns = range(max(0, int((left - JP_LEFT) // 40_000)),
                    min(len(JP_COLUMNS) - 1, int((right - JP_LEFT) // 40_000)) + 1)
    rows = range(max(0, int((JP_TOP - top) // 30_000)), min(len(JP_ROWS) - 1, int((JP_TOP - bottom) // 30_000)) + 1)
    return [f"{folder}LP/Grid/08/{JP_ROWS[r]}{JP_COLUMNS[c]}/" for r in rows for c in columns]


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

SOURCES: List[Source] = [
    Source(
        id="tokyo", name="Tokyo (Digital Twin lidar 0.5 m)",
        description="Tokyo Metropolitan Government: Tokyo Digital Twin point cloud grids 0.5 m (terrain) of Tama "
                    "(2022-2023), the Izu islands (2022-2023) and the 23 wards (2023), JGD2011 / Japan Plane "
                    "Rectangular CS IX; no surface model; island coasts carry some seabed heights",
        nmt=TK_DTM, countries=("jp",), regions=("jp-13",), crs=TK_CRS, credits=(TK_CREDIT,),
        listing=ReadmeRow("Tokyo (JP)", "Tokyo Digital Twin lidar grid 0.5 m (Tama, Izu islands 2022-2023; "
                                        "23 wards 2023)", "– (point clouds only)", "–"),
        offline=TK_BOXES, sample=(35.8179, 139.0875),  # Okutama (R84)
        note="Data: Tokyo Metropolitan Government, Tokyo Digital Twin point cloud data, CC BY 4.0 (Tokyo Open Data "
             "terms). Terrain only (no surface model: trees and buildings are not in the data). Ogasawara was not "
             "surveyed. Near the islands' coasts the grids hold some seabed heights below 0 m.",
        coverage=Coverage(provider="Tokyo Metropolitan Government", added="2026-11-15", partial=True,
                          survey="2022–2023")),
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
        coverage=Coverage(provider="Shizuoka Prefecture", added="2026-11-15", survey="2019–2025")),
]
