"""Japan: the Forestry Agency's lidar DEMs of the local bodies' surveys (林野庁加工), 0.5 m, one big tiled GeoTIFF per
quarter of a 1/50000 sheet, read in small windows as a search needs them: one source per prefecture (`mie`)."""

import math
import os
from functools import lru_cache
from typing import Dict, List, NamedTuple, Optional, Sequence, Tuple

import numpy as np

from ..credit import Credit
from ..indexes.tilings import FileBlockTiling, FileList
from ..layers.fileblocks import FileBlocks
from ..source import Coverage, ReadmeRow, Source
from . import japan

# The Forestry Agency (林野庁, organisation `rinya` on G-Spatial's CKAN, www.geospatial.jp) publishes the airborne lidar
# of local bodies' surveys it processed under the forest GIS forum's specification as DEM (ground), DCHM (canopy
# height), tree species and a CS map: one record per forest planning area (and per disaster survey), its DEM as one
# GeoTIFF per quarter of a 1/50000 sheet of the plane rectangular grid, dem_<zone><row><column><quarter>_2025.tif
# (quarters 1 north-west, 2 north-east, 3 south-west, 4 south-east: 20 x 15 km; 06NE4 = zone VI, x 20 000-40 000,
# y -120 000..-105 000, rf_box), in the listable bucket gsic-opendata (AWS ap-northeast-1, run for G-Spatial by
# AIGID: the bucket's owner is not stated) under ckan/resources/<resource id>/ or, for some files over about 1 GB,
# national-gov/maff/forestry-agency/...: plain unsigned addresses (CKAN's own download link answers 302 to a signed
# one on the same key). The files read so far (2026-11-27): BigTIFF, float32, Deflate with predictor 2, nodata
# -9999, "Area", 0.5 m pixels with their edges on whole metres, tiled 512 x 512, no overviews; the tile offsets and
# byte counts lie in the first 57 KB, so GDAL's open asks a HEAD and three 16 KB ranges and a window then reads
# its tiles, a range per row of tiles (Windows, serial, through /vsicurl/: the recorded test's requests). A file is
# clipped to its data's rows and columns on its quarter (06ME4 starts at y -83 400) and may hold one pixel more to
# the east and south (40 001 x 30 001 px: the next quarter's first column and row). The CRS is read from each
# file's tags into the table (Kitaise's record names EPSG:6675, its files are EPSG:6674). Kitaise's scale and tie
# point carry float noise (0.4999999999999944, 19999.9999999998): within Windows' test of the files' own pixels
# (windows._coincide: 1e-6 relative, 0.01 px), so blocks are read as they are, never resampled. Heights T.P.
# (presumed as for the other Japanese sources: no document names the datum).
RF_BUCKET = "https://gsic-opendata.s3.ap-northeast-1.amazonaws.com"
RF_TABLE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "japan_forest_files.npz")
# The edition in every file's name ("_2025"): the version label a user sees. A file the Agency uploads again in place
# keeps its name and address (Kitaise's keys were all uploaded again on 2026-10-01/02, the research's listing): the
# reader asks no ETag (GDAL's /vsicurl/ reads the live file), so blocks cached from the old file stay and blocks read
# later come from the new one, and a search over both meets the two at block edges; the mask stays the old table's.
# So a record's blocks are cached in a folder stamped with the newest Last-Modified date of its files in the shipped
# table (rf_stamp: <source>/<record>-dem/<edition>-<YYYYMMDD>, Austria's BEV_EDITION pattern): tools/forest_files.py
# reports a replaced file (another size, ETag or address), the table made again moves the record to a new folder, its
# blocks are read again from the new files and with the new mask. The folder of before stays until removed by hand.
RF_EDITION = 2025
QUARTER = (20_000, 15_000)  # a quarter of a 1/50000 sheet, metres (w, h)
RF_RES = 0.5
# Blocks of 500 m (1000 px) on whole multiples from the zone's origin: inside one quarter each (20 000 and 15 000
# are multiples of 500), so a block reads its own quarter's file, and the one-pixel overlap of a neighbour only
# where that file has no data in the block's first column or row (rf_files)
RF_BLOCK_M = 500


def rf_quarter(zone: int, x: float, y: float) -> Optional[str]:
    """The quarter of a 1/50000 sheet holding a point (x, y in the zone's metres): "06NE4"; None outside the scheme."""
    found = japan._sheet_offsets(math.floor(x) - japan.JP_LEFT, japan.JP_TOP - math.ceil(y))
    if found is None:
        return None
    row, column, dx, down = found
    quarter = 1 + (dx >= QUARTER[0]) + 2 * (down >= QUARTER[1])
    return f"{zone:02d}{japan.JP_ROWS[row]}{japan.JP_COLUMNS[column]}{quarter}"


def rf_box(code: str) -> Tuple[int, float, float, float, float]:
    """(zone, left, bottom, right, top) of a quarter's code in the zone's metres; ValueError for no such code."""
    if len(code) != 5 or not code[:2].isdigit() or code[2] not in japan.JP_ROWS or code[3] not in japan.JP_COLUMNS \
            or code[4] not in "1234":
        raise ValueError(f"{code}: no quarter of a 1/50000 sheet")
    q = int(code[4]) - 1
    left = japan.JP_LEFT + japan.JP_COLUMNS.index(code[3]) * 40_000 + q % 2 * QUARTER[0]
    top = japan.JP_TOP - japan.JP_ROWS.index(code[2]) * 30_000 - q // 2 * QUARTER[1]
    return int(code[:2]), left, top - QUARTER[1], left + QUARTER[0], top


class RfFile(NamedTuple):
    """A file of the table (tools/forest_files.py): its record and quarter, its key in the bucket, what the bucket
    said of it (size, ETag, Last-Modified), what its tags say (EPSG code, pixel size a and e, the corner c and f,
    width and height, the mask's cell in px: a tiled file's tiles, 512 x 512 px cells for a strip file read whole, a
    strip across the file for a larger one), its data mask (True: the cell holds data), the edition in its name and
    whether every block over it reads its own pixels (windows._coincide)."""
    record: str
    code: str
    key: str
    size: int
    etag: str
    modified: str
    epsg: int
    a: float
    e: float
    c: float
    f: float
    width: int
    height: int
    tile_w: int
    tile_h: int
    mask: Optional[np.ndarray]
    edition: int = RF_EDITION
    on_pixels: bool = True

    def window(self, box: Tuple[float, float, float, float]) -> Optional[Tuple[int, int, int, int]]:
        """The file's pixels (column, row from, to: c1, r1, c2, r2) under a box (left, bottom, right, top), None when
        none (a pixel only touching the box's edge is not under it; float noise of the tags within 1e-6 px)."""
        left, bottom, right, top = box
        c1, c2 = math.floor((left - self.c) / self.a + 1e-6), math.ceil((right - self.c) / self.a - 1e-6)
        r1, r2 = math.floor((top - self.f) / self.e + 1e-6), math.ceil((bottom - self.f) / self.e - 1e-6)
        c1, r1, c2, r2 = max(c1, 0), max(r1, 0), min(c2, self.width), min(r2, self.height)
        return (c1, r1, c2, r2) if c1 < c2 and r1 < r2 else None

    def has_data(self, box: Tuple[float, float, float, float]) -> bool:
        """Whether a cell of the mask under a box holds data (a file without a mask: never)."""
        found = self.window(box)
        if found is None or self.mask is None:
            return False
        c1, r1, c2, r2 = found
        return bool(self.mask[r1 // self.tile_h:(r2 - 1) // self.tile_h + 1,
                              c1 // self.tile_w:(c2 - 1) // self.tile_w + 1].any())


@lru_cache(maxsize=None)
def rf_table() -> Tuple[RfFile, ...]:
    """The shipped table (japan_forest_files.npz, tools/forest_files.py)."""
    return load_table(RF_TABLE)


def load_table(path: str) -> Tuple[RfFile, ...]:
    """A table written by tools/forest_files.py save(): its rows with their masks unpacked."""
    with np.load(path) as t:
        bits = np.unpackbits(t["masks"])
        rows = []
        for k in range(len(t["code"])):
            tw, th = int(t["tile_w"][k]), int(t["tile_h"][k])
            mask = None
            if tw and th:
                nx, ny = -(-int(t["width"][k]) // tw), -(-int(t["height"][k]) // th)
                start = int(t["mask_start"][k])
                mask = bits[start:start + nx * ny].astype(bool).reshape(ny, nx)
            rows.append(RfFile(str(t["record"][k]), str(t["code"][k]), str(t["key"][k]), int(t["size"][k]),
                               str(t["etag"][k]), str(t["modified"][k]), int(t["epsg"][k]),
                               *(float(v) for v in t["transform"][k]), int(t["width"][k]), int(t["height"][k]),
                               tw, th, mask, int(t["edition"][k]),
                               bool(t["on_pixels"][k]) if "on_pixels" in t.files else False))
    return tuple(rows)


def rf_stamp(record: str) -> str:
    """The stamp of a record's state in the shipped table: the newest Last-Modified date of its files, YYYYMMDD
    (the cache folder's, RF_EDITION's comment); ValueError for a record without files there."""
    from email.utils import parsedate_to_datetime
    dates = [parsedate_to_datetime(r.modified) for r in rf_table() if r.record == record]
    if not dates:
        raise ValueError(f"{record}: no file in the table {RF_TABLE}")
    return max(dates).strftime("%Y%m%d")


def rf_rows(records: Sequence[str], zone: int) -> List[RfFile]:
    """The files of the records in a zone (EPSG:6668 + zone by their tags), the records in their order; a strip file
    is one too (its mask on cells of 512 px from its pixels; a 500 m block of it reads 1 000 rows across the file:
    0.06-0.13 MB at the median, 4.7 MB at most). A file whose blocks would not read its own pixels (on_pixels False:
    Tokushima's, 0.49999987 m with corners 1-2 cm off) is refused: ValueError, until its source says how such files
    are read."""
    order = {r: k for k, r in enumerate(records)}
    found = sorted((r for r in rf_table() if r.record in order and r.epsg == 6668 + zone and r.mask is not None),
                   key=lambda r: order[r.record])
    off = [f"{r.record} {r.code}" for r in found if not r.on_pixels]
    if off:
        raise ValueError(f"the blocks of {', '.join(off)} would not read the files' own pixels (windows._coincide): "
                         f"their source must say how such files are read")
    return found


def rf_files(records: Sequence[str], zone: int, years: Dict[str, int], block_m: float = RF_BLOCK_M):
    """files(i, j) of FileBlocks for the records' files in a zone: the files with data under block (i, j) by their
    masks (none: no request), the block's own quarter's files first (the records newest first: their order), then
    a neighbour whose extra column or row (a 40 001 x 30 001 px file) reaches into the block, to fill only what the
    own file leaves without data there (Windows reads a file only while the block has holes). Computed at each call
    (about 0.1 ms: the table's rows of the zone, each mask a slice), so a patched table or bucket is seen."""
    def files(i: int, j: int) -> FileList:
        box = (i * block_m, j * block_m, (i + 1) * block_m, (j + 1) * block_m)
        own = rf_quarter(zone, box[0] + block_m / 2, box[1] + block_m / 2)
        found = [r for r in rf_rows(records, zone) if r.has_data(box)]
        found.sort(key=lambda r: r.code != own)  # stable: the records' order within each
        return [(f"{r.record}_{r.code}", f"{RF_BUCKET}/{r.key}", years[r.record]) for r in found]
    return files


class RfBlockTiling(FileBlockTiling):
    """A FileBlockTiling over the Agency's files of some records in a zone: a block without a file with data (the
    masks) is no tile (no estimate, no record, no request), and has_data_near answers from the masks."""

    def __init__(self, folder: str, records: Sequence[str], zone: int, years: Dict[str, int]):
        super().__init__(f"EPSG:{6668 + zone}", folder, RF_RES, RF_BLOCK_M, rf_files(records, zone, years))
        self.records, self.zone = tuple(records), zone

    def _tiles(self, grid) -> list:
        return [tile for tile in super()._tiles(grid) if self.files(*tile)]

    def has_data_near(self, lat: float, lon: float, cache_dir: str, metres: float = 2000.0) -> Optional[bool]:
        """Whether a tile with data lies within `metres` of the point (a square of 2 x metres around it in the zone's
        CRS), from the masks alone: no request (Source.instead_without_data, Miyagi's rule)."""
        from rasterio.warp import transform
        xs, ys = transform("EPSG:4326", self.crs, [lon], [lat])
        box = (xs[0] - metres, ys[0] - metres, xs[0] + metres, ys[0] + metres)
        return any(r.has_data(box) for r in rf_rows(self.records, self.zone))


class RfBlocks(FileBlocks):
    """Blocks of RF_BLOCK_M of the Agency's 0.5 m DEM files of some records in a zone (FileBlocks, read range by
    range: serial, as Austria's big tiled files), the blocks and has_data_near from the shipped table's masks."""

    def __init__(self, description: str, folder: str, records: Sequence[str], zone: int, years: Dict[str, int],
                 bytes_per_tile: float, credit: Optional[Credit] = None):
        super().__init__(description, folder, f"EPSG:{6668 + zone}", RF_RES, RF_BLOCK_M,
                         rf_files(records, zone, years), year=max(years.values()), bytes_per_tile=bytes_per_tile,
                         credit=credit, serial=True)
        self.index = RfBlockTiling(folder, records, zone, years)


# The licence (every record's notes, read 2026-11-27): 「本サイトのコンテンツには特段の記載が無い限り公共データ利用規約（第1.0版）
# （PDL1.0）が適用されています」 (CKAN's license_id says ogl, 政府標準利用規約); the record's 「公共データ利用規約（第１.0版）に関する
# 重要情報」 (variant for the local bodies' surveys, 2026-10-01): 「出典：地方公共団体等名称・データ名称（林野庁加工）（当該ページの
# URL）、PDL1.0（規約原文ページの URL）」, and for an edited work, beside it, that it was edited (「…（林野庁加工）（当該ページの URL）を
# もとに●●株式会社が作成」), never as if the local bodies or the Agency had made it. PDL1.0 allows copying, public
# transmission and adaptation, commercial use too, and use under CC BY 4.0. Its sentence on the Survey Act (approval
# under Articles 43 or 44 when the DEM is used for surveying) concerns surveying, not a credit. No request limits
# published (the notes, the important-notes PDF, PDL1.0, G-Spatial's terms https://front.geospatial.jp/about/: Art. 6
# forbids obstructing the servers, no number); who pays the bucket's egress is not stated: two connections at once
PDL = ("PDL 1.0", "https://www.digital.go.jp/resources/open_data/public_data_license_v1.0")
RF_EDITED = "をもとにFind-a-Lineが作成"  # the edited work's sentence (イ), after the source's own credit


def rf_credit(data: str, bodies: str, name: str, record_url: str, approval: str = "") -> Credit:
    """The credit of a record (variant for the local bodies' surveys): 出典：<bodies>・<name>（林野庁加工）<approval>
    （<record>）、PDL1.0（<terms>）, the bodies' names as the record's notes give them, approval a sentence the record
    asks for (Inadani's); the notice says the data were edited, by whom, and that neither the bodies nor the Agency made
    it."""
    source = f"{bodies}・{name}（林野庁加工）{approval}（{record_url}）"
    return Credit(data, f"出典：{source}、PDL1.0（{PDL[1]}）", *PDL,
                  notice=f"出典：{source}{RF_EDITED}。Edited by Find-a-Line (resampled and combined onto a working "
                         f"grid); not made by the local bodies named nor by the Forestry Agency.")


def rf_agency_credit(data: str, record_url: str) -> Credit:
    """The credit of a record of the Agency's own survey (the important-notes PDF's other variant, h28, r2, r6):
    出典：林野庁（<record>）、PDL1.0（<terms>）; the notice as rf_credit's."""
    source = f"林野庁（{record_url}）"
    return Credit(data, f"出典：{source}、PDL1.0（{PDL[1]}）", *PDL,
                  notice=f"出典：{source}{RF_EDITED}。Edited by Find-a-Line (resampled and combined onto a working "
                         f"grid); not made by the Forestry Agency.")


# --- Mie: Kitaise (北伊勢森林計画区) ------------------------------------------------------------------------------------
# The record kitaise_081 (「三重県（北伊勢森林計画区）・樹種ポリゴン/林相識別図/DCHM/DEM/微地形表現図（林野庁加工）」, modified
# 2026-09-08): the lidar of nine surveys of 2013-2023 (the record's data sheet, read by the research of 2026-11-26)
# that the Agency received from MLIT's cadastral survey division, the Tokai Regional Agricultural Administration
# Office's Kiso river land improvement office, Mie Prefecture's forestry division, Tsu city and Komono town. 13 DEM
# files in zone VI (EPSG:6674), 4.95 GB (2026-11-27); they cover the Suzuka range's eastern side from Komono to the
# Nunobiki hills and Tsu's western hills: the data are the forest planning area's forests, the rest of each quarter
# (the Ise plain, the towns, the sea) no data, filled from the fallback. Where no tile with data lies within 2 km of a
# search's centre, --source auto takes europe (instead_without_data, the masks: no request; the user's decision
# "5. a" of 2026-11-27, Miyagi's rule). No neighbour source (Kyoto's and Shiga's are not built)
KS_RECORD = "https://www.geospatial.jp/ckan/dataset/kitaise_081"
KS_ZONE = 6
KS_CRS = "EPSG:6674"
KS_YEARS = {"kitaise": 2023}  # the order of a block's files by record (one record): its newest survey
KS_CREDIT = rf_credit("Forestry Agency DEM 0.5 m, Kitaise forest planning area (Mie; local bodies' surveys, "
                      "processed by the Forestry Agency)",
                      "国土交通省土地・建設産業局地籍整備課、東海農政局木曽川水系土地改良調査管理事務所、三重県森林・林業経営課、"
                      "津市農林水産部林業振興室、菰野町産業観光課",
                      "三重県（北伊勢森林計画区）DEM", KS_RECORD)
# bytes_per_tile: a block of 500 m reads the 2-3 x 2-3 tiles under it (256 m each): 5.5 MB for the 9 tiles of a full
# block of 06NE4 read alone (2026-11-27); range by range (serial) a tile shared with the block beside is read once:
# R100's cold search read 16 blocks, 81 distinct tiles of 37.1 MB by 06NE4's header (2.3 MB a block, the mountains'
# full blocks); over the whole record 4.95 GB for the 3 563 blocks that meet a tile with data (1.4 MB).
# The masks (tools/forest_files.py, made again on 2026-11-27 after the code review): a tile whose byte count is not
# its class's empty size is data; the 1 603 empty-sized tiles beside data tiles (across the files' edges too) were read
# in 876 ranges (2.5 MB) and compared byte for byte with their class's empty tile, and none held data (a tile of one
# constant height compresses to exactly the empty size: the review's finding), so 12 161 of the 51 305 tiles hold
# data, as before. What the rule cannot see: constant ground wholly enclosed by empty tiles is called empty (the 30 m
# source fills it). 890 requests, 4.0 MB, for the 13 files' headers and those tiles.
KS_DTM = RfBlocks("Forestry Agency DEM 0.5 m, Kitaise (terrain)",
                  f"mie/kitaise-dem/{RF_EDITION}-{rf_stamp('kitaise')}", ("kitaise",), KS_ZONE, KS_YEARS,
                  bytes_per_tile=2.3e6, credit=KS_CREDIT)

# Offline boxes (south, north, west, east): bands of 0.05 degrees cut into columns of 0.01 degree, a cell kept when a
# tile with data (the masks of the shipped table, 2026-11-27) meets it, runs of kept cells a box: where the data are,
# not Mie's outline. They hold 1 103 of Mie's 5 819 km² (Natural Earth's admin-1; the data's tiles 785 km²) and 156 km²
# of the neighbours' land along the Suzuka range's ridge and at Iga (Shiga 76, Gifu 69, Nara 11: no source there)
KS_BOXES = tuple(("jp-24", box) for box in (
    (34.40, 34.45, 136.20, 136.26), (34.45, 34.50, 136.20, 136.35), (34.50, 34.55, 136.15, 136.37),
    (34.55, 34.60, 136.16, 136.40), (34.60, 34.65, 136.24, 136.33), (34.60, 34.65, 136.34, 136.43),
    (34.65, 34.70, 136.25, 136.35), (34.70, 34.75, 136.28, 136.38), (34.75, 34.80, 136.31, 136.40),
    (34.80, 34.85, 136.27, 136.41), (34.85, 34.90, 136.27, 136.45), (34.90, 34.95, 136.35, 136.49),
    (34.95, 35.00, 136.38, 136.55), (35.00, 35.05, 136.41, 136.57), (35.05, 35.10, 136.41, 136.55),
    (35.10, 35.15, 136.43, 136.49), (35.15, 35.20, 136.40, 136.49), (35.15, 35.20, 136.52, 136.62),
    (35.20, 35.25, 136.41, 136.57)))

# --- Yamagata: Shonai (庄内森林計画区) -----------------------------------------------------------------------------------
# The record 028_syounai (「山形県（庄内森林計画区）・樹種ポリゴン/林相識別図/DCHM/DEM/微地形表現図（林野庁加工）」, modified
# 2026-09-08): the lidar the Agency received from Yamagata Prefecture's forestry division and Shonai town (the notes'
# 「山形県森林ノミクス課及び庄内町農林課」), surveyed in FY2022 (令和4年度: the record's data sheet, read by the research of
# 2026-11-26; the notes name no year). 17 DEM files in zone X (EPSG:6678), 2.05 GB, three of them one-row strip files
# (10NB1, 10NC4, 10PB3: read whole for their masks, 13.8 MB); the data are the planning area's private forests (the
# Dewa hills, the Asahi range's north-west foot, Chokai's and Gassan's lower slopes; the national forests of the high
# ranges have none), 1 192 km² of data cells. Tobishima's (10MB3) lie off the coast. No neighbour source: Miyagi's sheets lie 21 km from Shonai's data
# (gate 5, the masks against miyagi_sheets.npz)
SY_RECORD = "https://www.geospatial.jp/ckan/dataset/028_syounai"
SY_ZONE = 10
SY_CRS = "EPSG:6678"
SY_YEARS = {"syounai": 2022}
SY_CREDIT = rf_credit("Forestry Agency DEM 0.5 m, Shonai forest planning area (Yamagata; local bodies' surveys, "
                      "processed by the Forestry Agency)", "山形県森林ノミクス課及び庄内町農林課", "山形県（庄内森林計画区）DEM",
                      SY_RECORD)
# bytes_per_tile: what GDAL downloaded in R101's cold search (2026-11-28): 7.59 MB for 12 blocks, 0.63 MB a block
SY_DTM = RfBlocks("Forestry Agency DEM 0.5 m, Shonai (terrain)",
                  f"yamagata/syounai-dem/{RF_EDITION}-{rf_stamp('syounai')}", ("syounai",), SY_ZONE, SY_YEARS,
                  bytes_per_tile=0.63e6, credit=SY_CREDIT)
# Offline boxes: made as mie's, cells of 0.05 x 0.01 degree meeting a cell of data, kept where Yamagata's land is at
# least each neighbouring prefecture's (or none: the sea, Tobishima), runs of kept cells a box. They hold 1 752 of
# Yamagata's 9 244 km² and 12 km² of Niigata's and Akita's land, where Shonai's files hold data: online (Nominatim) a
# centre there is Niigata's or Akita's and runs on europe; offline (the boxes, the first holding it) on yamagata
SY_BOXES = tuple(("jp-06", box) for box in (
    (38.40, 38.45, 139.74, 139.80), (38.45, 38.50, 139.70, 139.72), (38.45, 38.50, 139.74, 139.83),
    (38.50, 38.55, 139.61, 139.74), (38.50, 38.55, 139.75, 139.92), (38.50, 38.55, 139.96, 140.04),
    (38.55, 38.60, 139.54, 139.96), (38.55, 38.60, 139.99, 140.04), (38.60, 38.65, 139.56, 140.01),
    (38.65, 38.70, 139.59, 139.84), (38.65, 38.70, 139.87, 140.00), (38.70, 38.75, 139.65, 139.82),
    (38.70, 38.75, 139.90, 140.01), (38.70, 38.75, 140.03, 140.06), (38.75, 38.80, 139.70, 139.80),
    (38.75, 38.80, 139.95, 140.09), (38.80, 38.85, 139.76, 139.82), (38.80, 38.85, 139.96, 140.12),
    (38.85, 38.90, 139.78, 139.84), (38.85, 38.90, 139.93, 140.13), (38.90, 38.95, 139.80, 139.85),
    (38.90, 38.95, 139.93, 140.15), (38.95, 39.00, 139.82, 139.88), (38.95, 39.00, 139.93, 140.15),
    (39.00, 39.05, 139.84, 139.89), (39.00, 39.05, 139.90, 140.13), (39.05, 39.10, 139.86, 139.98),
    (39.05, 39.10, 140.00, 140.06), (39.10, 39.15, 139.86, 139.89), (39.15, 39.20, 139.52, 139.57),
    (39.20, 39.25, 139.54, 139.57)))


# --- Nagano: Inadani (伊那谷森林計画区) -----------------------------------------------------------------------------------
# The record inatani_067 (「長野県（伊那谷森林計画区）・樹種ポリゴン/DCHM/DEM/微地形表現図（林野庁加工）」, modified 2026-09-08):
# the lidar the Agency received from Nagano Prefecture (the notes' 「長野県森林政策課及び同県森林づくり推進課」), the
# prefecture's 2013 survey (H24 予防治山 contracts 27, 28 and 32: the record's data sheet, read by the research of
# 2026-11-26; the notes name no year), whole decimetres. The notes' important information asks that the credit show
# the data are published by the Agency with the approval of Nagano's forestry department, 「出典明記は、林野庁が長野県林務部
# の承認を得て公開しているデータであることが分かるよう「長野県・微地形表現図マップタイル（長野県林務部長承認（承認番号７森政第51-2号）に基
# づき林野庁作成）」などとしてください。」: a sentence on the record's data as a whole, the map tiles its example, so the DEM's
# credit carries the approval. 23 files in zone VIII (EPSG:6676), 40 000 x 30 000 px (no overlap), 6.39 GB, 3 451 km²
# of data cells: the Ina valley's two flanks, the Central Alps' east foot and the Southern Alps' west foot (the
# record's index has two quarters without files, 08JC2 and 08KC3: Komagatake's Senjojiki lies in 08KC3).
# The stack to come (the user's decision "4 a"): `nagano` will be the prefecture's 2021-22 set (R3-4 50cmDEM) on top,
# this record below it, the 2013-14 set (nagano-dem, the same 2013 contracts processed otherwise) at the bottom, each
# filling the holes of the ones above: then Inadani's pixels give way where the 2021-22 set has data (its coverage of
# the alps is not known), and its holes (6.7 % at the research's sheet 08KC9523) are filled from the 2013 set instead
# of the 30 m model. This layer and its folder are named by the record, so the stack can hold it as it is.
# Neighbours: yamanashi and shizuoka (both ways): Inadani's data cells meet their offline boxes (which stand for
# where their sheets are; measured on the masks, 2026-11-28): Yamanashi's at 0 m in 08KD2 and 08KD3, 73 km² of cells
# within 2 km; Shizuoka's at 0 m in 08LD3, 08MC2-08MC4 and 08MD1, 159 km² within 2 km; so a border gap of either is
# filled from the other
INA_RECORD = "https://www.geospatial.jp/ckan/dataset/inatani_067"
INA_ZONE = 8
INA_CRS = "EPSG:6676"
INA_YEARS = {"inatani": 2013}
INA_CREDIT = rf_credit("Forestry Agency DEM 0.5 m, Inadani forest planning area (Nagano; the prefecture's survey, "
                       "processed by the Forestry Agency)", "長野県森林政策課及び同県森林づくり推進課",
                       "長野県（伊那谷森林計画区）DEM", INA_RECORD,
                       approval="（長野県林務部長承認（承認番号７森政第51-2号）に基づき林野庁作成）")
# bytes_per_tile: what GDAL downloaded in R105's cold search (2026-11-28): 10.83 MB for 16 blocks, 0.68 MB a block
INA_DTM = RfBlocks("Forestry Agency DEM 0.5 m, Inadani (terrain)",
                   f"nagano/inatani-dem/{RF_EDITION}-{rf_stamp('inatani')}", ("inatani",), INA_ZONE, INA_YEARS,
                   bytes_per_tile=0.68e6, credit=INA_CREDIT)
# Offline boxes: as Yamagata's: 3 986 of Nagano's 13 695 km², 36 km² of the neighbours' land (Shizuoka 13,
# Yamanashi 11, Aichi 8, Gifu 4). Offline, the first box holding a point wins and the japan family comes first, so
# Yamanashi's and Shizuoka's boxes (cut when Nagano had no source) take some of Nagano's land: on a lattice of 0.005
# degree, points at least 300 m inside Nagano, 478 go to shizuoka and 60 to yamanashi, 23 of Yamanashi's to nagano
# (2026-11-28). Border boxes: Nagano's land within 5 km of Yamanashi and Shizuoka in bands of 0.05 degree, for their
# gap filling only
INA_BOXES = tuple(("jp-20", box) for box in (
    (35.20, 35.25, 137.54, 137.86), (35.25, 35.30, 137.55, 137.94), (35.30, 35.35, 137.57, 138.04),
    (35.35, 35.40, 137.62, 138.11), (35.40, 35.45, 137.61, 138.09), (35.45, 35.50, 137.62, 138.07),
    (35.50, 35.55, 137.64, 138.14), (35.55, 35.60, 137.68, 138.13), (35.60, 35.65, 137.71, 138.12),
    (35.65, 35.70, 137.79, 137.82), (35.65, 35.70, 137.84, 138.15), (35.70, 35.75, 137.84, 138.16),
    (35.75, 35.80, 137.84, 138.18), (35.80, 35.85, 137.83, 138.16), (35.80, 35.85, 138.17, 138.20),
    (35.85, 35.90, 137.84, 138.30), (35.90, 35.95, 137.84, 138.33), (35.95, 36.00, 137.86, 138.37),
    (36.00, 36.05, 137.87, 138.36), (36.05, 36.10, 137.92, 137.98), (36.05, 36.10, 137.99, 138.35),
    (36.10, 36.15, 138.02, 138.25), (36.15, 36.20, 138.05, 138.14)))
INA_BORDER_BOXES = (
    (35.15, 35.20, 137.72, 137.84), (35.20, 35.25, 137.72, 137.92), (35.25, 35.30, 137.78, 138.02),
    (35.30, 35.35, 137.86, 138.12), (35.35, 35.40, 137.96, 138.14), (35.40, 35.45, 138.03, 138.15),
    (35.45, 35.50, 138.04, 138.16), (35.50, 35.55, 138.05, 138.15), (35.55, 35.60, 138.05, 138.20),
    (35.60, 35.65, 138.08, 138.21), (35.65, 35.70, 138.09, 138.20), (35.70, 35.75, 138.09, 138.22),
    (35.75, 35.80, 138.10, 138.22), (35.80, 35.85, 138.10, 138.29), (35.85, 35.90, 138.13, 138.73),
    (35.90, 35.95, 138.17, 138.73), (35.95, 36.00, 138.26, 138.58), (36.00, 36.05, 138.30, 138.44))

# --- Hiroshima and Okayama: the record h30 (平成30年7月豪雨) -----------------------------------------------------------
# The record h30_7_gouu (「平成30年7月豪雨・DEM/微地形表現図/グラウンドデータ（林野庁加工）」, modified 2026-09-08): after the
# July 2018 rains the Agency's own lidar and Okayama Prefecture's published grid data, the notes:
# 「平成30年７月豪雨（岡山県・広島県）の発災後に林野庁が実施した航空レーザ測量データ及び、岡山県(https://i-box.pref.okayama.jp/datasets/251)が
# 公開したグリッドデータを基に、林野庁が作成したDEM」; its important notes are the local bodies' variant, so the credit names what
# the notes name, 林野庁 and 岡山県, the same wording for both sources (one record). The survey year is the title's, 2018
# (the notes name none). 65 files, 26.32 GB: 24 in zone III (EPSG:6671) over Hiroshima, 41 in zone V (EPSG:6673) over
# Okayama (by the files' tags; the record's list suggests 21 and 44), of them four strip files (03QE1, 03QE3, 03QG2
# one-row Deflate in zone III; 05MB4 uncompressed in zone V), read whole for their masks (22.9 MB, 2026-11-28).
# Zone V's files reach into Tottori (about 230 km² of data cells) and Hyogo (about 57): `okayama` holds all 41, so a
# search centred in Okayama reads the data across those borders; online (Nominatim) a centre in Tottori or Hyogo is
# not okayama's (no source there yet: the user's question) and runs on europe, offline (the boxes) a centre in the
# 110 km² of their and Hiroshima's land inside okayama's boxes runs on okayama. Kojima's water (05PD1, the lake west
# of the bay's dike) is in the data, flat at -0.2 to 0.0 m: a search centred on it (radius 400 m, 2026-11-28) found no
# anchor on the water and no line, 61.5 % of its area from the source (the files' tiles without data at sea filled
# from the fallback model).
# The table's run of 2026-11-28: 65 files, 3 762 requests and 30.4 MB; 12 331 empty-sized tiles
# and strips beside data read, none data; every file on the blocks' pixels
H30_RECORD = "https://www.geospatial.jp/ckan/dataset/h30_7_gouu"
H30_YEARS = {"h30": 2018}
H30_CREDIT = rf_credit("Forestry Agency DEM 0.5 m, the July 2018 rains (Hiroshima and Okayama; the Agency's survey and "
                       "Okayama Prefecture's grid data, processed by the Forestry Agency)", "林野庁、岡山県",
                       "平成30年7月豪雨 DEM", H30_RECORD)
HI_ZONE, OK_ZONE = 3, 5
HI_CRS, OK_CRS = "EPSG:6671", "EPSG:6673"
# bytes_per_tile: what GDAL downloaded in R102's cold search (2026-11-28): 26.76 MB for 16 blocks, 1.67 MB a block
HI_DTM = RfBlocks("Forestry Agency DEM 0.5 m, July 2018 rains, Hiroshima (terrain)",
                  f"hiroshima/h30-dem/{RF_EDITION}-{rf_stamp('h30')}", ("h30",), HI_ZONE, H30_YEARS,
                  bytes_per_tile=1.67e6, credit=H30_CREDIT)
# bytes_per_tile: what GDAL downloaded in R103's cold search (2026-11-28): 6.62 MB for 12 blocks, 0.55 MB a block
OK_DTM = RfBlocks("Forestry Agency DEM 0.5 m, July 2018 rains, Okayama (terrain)",
                  f"okayama/h30-dem/{RF_EDITION}-{rf_stamp('h30')}", ("h30",), OK_ZONE, H30_YEARS,
                  bytes_per_tile=0.55e6, credit=H30_CREDIT)
# Offline boxes, as Yamagata's (cells meeting data, kept where the prefecture's land is at least each other's):
# Hiroshima's: 3 431 of its 8 301 km², none of the neighbours' land
HI_BOXES = tuple(("jp-34", box) for box in (
    (34.00, 34.05, 132.51, 132.54), (34.05, 34.10, 132.44, 132.57), (34.10, 34.15, 132.38, 132.60),
    (34.15, 34.20, 132.38, 132.58), (34.15, 34.20, 132.63, 132.65), (34.20, 34.25, 132.38, 132.50),
    (34.20, 34.25, 132.51, 132.78), (34.25, 34.30, 132.37, 132.80), (34.25, 34.30, 132.83, 132.87),
    (34.30, 34.35, 132.41, 132.46), (34.30, 34.35, 132.47, 133.09), (34.35, 34.40, 132.46, 133.30),
    (34.40, 34.45, 132.31, 133.30), (34.45, 34.50, 132.30, 133.25), (34.50, 34.55, 132.33, 133.27),
    (34.55, 34.60, 132.37, 133.28), (34.60, 34.65, 132.39, 132.50), (34.60, 34.65, 132.51, 132.53),
    (34.60, 34.65, 132.60, 132.69), (34.60, 34.65, 132.78, 133.24), (34.65, 34.70, 132.87, 133.22),
    (34.70, 34.75, 133.09, 133.20), (34.75, 34.80, 133.12, 133.17)))
# Okayama's: 6 819 of its 6 934 km², 110 km² of the neighbours' (Tottori 77, Hiroshima 19, Hyogo 14)
OK_BOXES = tuple(("jp-33", box) for box in (
    (34.25, 34.30, 133.52, 133.54), (34.30, 34.35, 133.49, 133.55), (34.30, 34.35, 133.56, 133.59),
    (34.35, 34.40, 133.48, 133.60), (34.40, 34.45, 133.47, 133.55), (34.40, 34.45, 133.69, 133.70),
    (34.40, 34.45, 133.74, 133.84), (34.40, 34.45, 133.85, 133.87), (34.40, 34.45, 133.90, 133.94),
    (34.45, 34.50, 133.45, 133.97), (34.45, 34.50, 134.00, 134.03), (34.50, 34.55, 133.44, 134.03),
    (34.55, 34.60, 133.41, 134.17), (34.55, 34.60, 134.18, 134.21), (34.60, 34.65, 133.39, 134.22),
    (34.65, 34.70, 133.38, 134.33), (34.70, 34.75, 133.36, 134.31), (34.75, 34.80, 133.36, 134.31),
    (34.80, 34.85, 133.34, 134.26), (34.85, 34.90, 133.31, 134.26), (34.90, 34.95, 133.31, 134.26),
    (34.95, 35.00, 133.31, 134.26), (35.00, 35.05, 133.28, 134.29), (35.05, 35.10, 133.30, 134.34),
    (35.10, 35.15, 133.38, 134.38), (35.15, 35.20, 133.50, 134.16), (35.15, 35.20, 134.22, 134.39),
    (35.20, 35.25, 133.52, 134.14), (35.25, 35.30, 133.56, 133.78), (35.25, 35.30, 133.86, 134.09),
    (35.30, 35.35, 133.95, 133.99)))
# No neighbour pair: zone III's data (hiroshima) and zone V's (okayama) lie 11.3 km apart at their nearest, no
# data of either within 5 km of the other's (gate 5, the masks), beyond the fill's reach; no other source borders them


# --- Ishikawa: the record r6 (令和6年能登半島地震) ------------------------------------------------------------------------
# The record r6_noto-peninsula-earthquake (「令和6年能登半島地震・DEM/微地形表現図/グラウンドデータ（林野庁加工）」, modified
# 2026-09-08): after the Noto earthquake of 1 January 2024 the Agency's lidar with the GSI, the notes:
# 「令和６年能登半島地震の発災後に林野庁と国土地理院が連携して実施した航空レーザ測量データを基に、林野庁が作成したDEM」; its important
# notes are the Agency's own variant (出典：林野庁（当該ページの URL）、PDL1.0（規約原文ページの URL）). The notes' sentence
# 「公共測量に用いる場合は、別途、国土地理院が保有する成果の使用承認を得てください。」 concerns use in a public survey, not a credit.
# The survey year is the title's, 2024. 32 files: 21 in zone VII (EPSG:6675) over Noto and Kaga's north, of which about
# 490 km² of data cells lie in Toyama (07GD3, 07GD4, 07HD1, 07HD2, 07HD3: `ishikawa` holds them; online a centre in
# Toyama is not ishikawa's, offline one in the 7 km² of Toyama inside ishikawa's boxes is), and 11 in zone VIII
# (EPSG:6676) over Niigata's Chuetsu, which no source uses yet (the user's question). The table's run: 32 files, 2 003
# requests and 11.4 MB; 3 582 empty-sized tiles beside data read, none data; every file on the blocks' pixels
R6_RECORD = "https://www.geospatial.jp/ckan/dataset/r6_noto-peninsula-earthquake"
R6_YEARS = {"r6": 2024}
R6_CREDIT = rf_agency_credit("Forestry Agency DEM 0.5 m, the Noto Peninsula earthquake of 2024 (the Agency's survey "
                             "with the GSI)", R6_RECORD)
ISH_ZONE, ISH_CRS = 7, "EPSG:6675"
# bytes_per_tile: what GDAL downloaded in R104's cold search (2026-11-28): 21.63 MB for 16 blocks, 1.35 MB a block
ISH_DTM = RfBlocks("Forestry Agency DEM 0.5 m, Noto earthquake 2024, Ishikawa (terrain)",
                   f"ishikawa/r6-dem/{RF_EDITION}-{rf_stamp('r6')}", ("r6",), ISH_ZONE, R6_YEARS,
                   bytes_per_tile=1.35e6, credit=R6_CREDIT)
# Offline boxes, as Yamagata's: 2 188 of Ishikawa's 4 113 km², 7 km² of Toyama's land
ISH_BOXES = tuple(("jp-17", box) for box in (
    (36.60, 36.65, 136.60, 136.68), (36.60, 36.65, 136.69, 136.77), (36.65, 36.70, 136.62, 136.78),
    (36.70, 36.75, 136.66, 136.78), (36.75, 36.80, 136.69, 136.82), (36.80, 36.85, 136.72, 136.83),
    (36.80, 36.85, 137.07, 137.08), (36.85, 36.90, 136.74, 136.85), (36.90, 36.95, 136.74, 136.89),
    (36.90, 36.95, 137.04, 137.05), (36.95, 37.00, 136.75, 137.06), (37.00, 37.05, 136.72, 137.06),
    (37.05, 37.10, 136.71, 137.06), (37.10, 37.15, 136.66, 137.07), (37.15, 37.20, 136.66, 136.93),
    (37.15, 37.20, 136.96, 137.06), (37.20, 37.25, 136.67, 137.09), (37.25, 37.30, 136.70, 137.24),
    (37.30, 37.35, 136.71, 137.28), (37.35, 37.40, 136.74, 137.28), (37.40, 37.45, 136.83, 136.92),
    (37.40, 37.45, 136.93, 137.37), (37.45, 37.50, 137.04, 137.37), (37.50, 37.55, 137.14, 137.37)))

SOURCES: List[Source] = [
    Source(
        id="mie", name="Mie (Forestry Agency lidar 0.5 m)",
        description="Mie Prefecture, the Kitaise forest planning area: the Forestry Agency's DEM 0.5 m "
                    "(terrain) of the local bodies' lidar surveys of 2013-2023, JGD2011 / Japan Plane Rectangular "
                    "CS VI; the forests only, no surface model",
        nmt=KS_DTM, countries=("jp",), regions=("jp-24",), crs=KS_CRS, credits=(KS_CREDIT,),
        listing=ReadmeRow("Mie (JP), the Kitaise forests", "Forestry Agency DEM 0.5 m, Kitaise (2013-2023)", "–",
                          "–"),
        offline=KS_BOXES, sample=(35.0217, 136.4281),  # Gozaisho, the Fujiuchi wall (R100)
        # Where no tile with data lies within 2 km of the centre (the Ise plain, Yokkaichi, Tsu's centre, the south
        # of Mie), --source auto takes europe
        instead_without_data="europe",
        note="Data: Forestry Agency (processed) from the lidar of MLIT, the Tokai Regional Agricultural "
             "Administration Office, Mie Prefecture, Tsu city and Komono town, PDL 1.0. Terrain only (no surface "
             "model: trees and buildings are not in the data). Nine surveys of 2013-2023 of the Kitaise forest "
             "planning area's forests (the Suzuka range's eastern side, the hills west of Tsu); the plain, the towns "
             "and the sea have no data and are filled from the fallback model.",
        coverage=Coverage(provider="Forestry Agency", added="2026-11-27", partial=True, survey="2013–2023")),
    Source(
        id="yamagata", name="Yamagata (Forestry Agency lidar 0.5 m)",
        description="Yamagata Prefecture, the Shonai forest planning area: the Forestry Agency's DEM 0.5 m (terrain) "
                    "of the local bodies' lidar survey of FY2022, JGD2011 / Japan Plane Rectangular CS X; the forests "
                    "only, no surface model",
        nmt=SY_DTM, countries=("jp",), regions=("jp-06",), crs=SY_CRS, credits=(SY_CREDIT,),
        listing=ReadmeRow("Yamagata (JP), the Shonai forests", "Forestry Agency DEM 0.5 m, Shonai (FY2022)", "–", "–"),
        offline=SY_BOXES, sample=(38.6013, 139.7778),  # the Asahi range's north-west foot (R101)
        instead_without_data="europe",
        note="Data: Forestry Agency (processed) from the lidar of Yamagata Prefecture and Shonai town, PDL 1.0. "
             "Terrain only (no surface model: trees and buildings are not in the data). The Shonai forest planning "
             "area's private forests, surveyed in FY2022; the high ranges' national forests, the plain, the towns and "
             "the sea have no data and are filled from the fallback model.",
        coverage=Coverage(provider="Forestry Agency", added="2026-11-28", partial=True, survey="2022")),
    Source(
        id="nagano", name="Nagano (Forestry Agency lidar 0.5 m, Inadani)",
        description="Nagano Prefecture, the Inadani forest planning area: the Forestry Agency's DEM 0.5 m (terrain) "
                    "of the prefecture's lidar survey of 2013, JGD2011 / Japan Plane Rectangular CS VIII; the forests "
                    "only, no surface model",
        nmt=INA_DTM, countries=("jp",), regions=("jp-20",), crs=INA_CRS, credits=(INA_CREDIT,),
        listing=ReadmeRow("Nagano (JP), the Inadani forests", "Forestry Agency DEM 0.5 m, Inadani (2013)", "–", "–"),
        offline=INA_BOXES, border_boxes=INA_BORDER_BOXES, neighbours=("yamanashi", "shizuoka"),
        sample=(35.7448, 137.8643),  # the Central Alps' east slope (R105)
        instead_without_data="europe",
        note="Data: Forestry Agency (processed) from Nagano Prefecture's lidar of 2013, published with the approval "
             "of Nagano's forestry department, PDL 1.0. Terrain only (no surface model: trees and buildings are not "
             "in the data). The Inadani forest planning area's forests (the Ina valley, the Central and Southern "
             "Alps' lower slopes); the rest of Nagano, the high alps and the towns have no data and are filled from "
             "the fallback model.",
        coverage=Coverage(provider="Forestry Agency", added="2026-11-28", partial=True, survey="2013")),
    Source(
        id="hiroshima", name="Hiroshima (Forestry Agency lidar 0.5 m)",
        description="Hiroshima Prefecture: the Forestry Agency's DEM 0.5 m (terrain) of its lidar after the July 2018 "
                    "rains, JGD2011 / Japan Plane Rectangular CS III; the surveyed areas only, no surface model",
        nmt=HI_DTM, countries=("jp",), regions=("jp-34",), crs=HI_CRS, credits=(H30_CREDIT,),
        listing=ReadmeRow("Hiroshima (JP), where the 2018 rains were surveyed", "Forestry Agency DEM 0.5 m, July 2018 "
                          "rains (2018)", "–", "–"),
        offline=HI_BOXES, sample=(34.5400, 132.4017),  # the Ota river's valley at Asa-cho Kuji (R102)
        instead_without_data="europe",
        note="Data: Forestry Agency (processed) from its own lidar after the July 2018 rains and Okayama Prefecture's "
             "grid data, PDL 1.0. Terrain only (no surface model: trees and buildings are not in the data). Surveyed "
             "in 2018 over the areas the rains struck; the rest of Hiroshima has no data and is filled from the "
             "fallback model.",
        coverage=Coverage(provider="Forestry Agency", added="2026-11-28", partial=True, survey="2018")),
    Source(
        id="okayama", name="Okayama (Forestry Agency lidar 0.5 m)",
        description="Okayama Prefecture: the Forestry Agency's DEM 0.5 m (terrain) of its lidar after the July 2018 "
                    "rains and the prefecture's grid data, JGD2011 / Japan Plane Rectangular CS V; no surface model",
        nmt=OK_DTM, countries=("jp",), regions=("jp-33",), crs=OK_CRS, credits=(H30_CREDIT,),
        listing=ReadmeRow("Okayama (JP), where the 2018 rains were surveyed", "Forestry Agency DEM 0.5 m, July 2018 "
                          "rains (2018)", "–", "–"),
        offline=OK_BOXES, sample=(34.8181, 133.3989),  # below the Nariwa river's dam (R103)
        instead_without_data="europe",
        note="Data: Forestry Agency (processed) from its own lidar after the July 2018 rains and Okayama Prefecture's "
             "grid data, PDL 1.0. Terrain only (no surface model: trees and buildings are not in the data). Surveyed "
             "in 2018; the data reach into Tottori and Hyogo along the borders. Parts of the coast, the towns and "
             "the sea have no data and are filled from the fallback model; the water of Kojima's lake is in the data "
             "at about 0 m.",
        coverage=Coverage(provider="Forestry Agency", added="2026-11-28", partial=True, survey="2018")),
    Source(
        id="ishikawa", name="Ishikawa (Forestry Agency lidar 0.5 m, Noto)",
        description="Ishikawa Prefecture, the Noto peninsula and Kaga's north: the Forestry Agency's DEM 0.5 m "
                    "(terrain) of its lidar after the 2024 earthquake, JGD2011 / Japan Plane Rectangular CS VII; no "
                    "surface model",
        nmt=ISH_DTM, countries=("jp",), regions=("jp-17",), crs=ISH_CRS, credits=(R6_CREDIT,),
        listing=ReadmeRow("Ishikawa (JP), Noto", "Forestry Agency DEM 0.5 m, Noto earthquake (2024)", "–", "–"),
        offline=ISH_BOXES, sample=(37.3658, 136.7806),  # the coast at Kami-Ozawa, Wajima (R104)
        instead_without_data="europe",
        note="Data: Forestry Agency (processed) from its lidar with the GSI after the Noto Peninsula earthquake of "
             "2024, PDL 1.0. Terrain only (no surface model: trees and buildings are not in the data). Surveyed in "
             "2024 over Noto and Kaga's north, the data reaching into Toyama along the border; the towns, the sea and "
             "the rest of Ishikawa have no data and are filled from the fallback model.",
        coverage=Coverage(provider="Forestry Agency", added="2026-11-28", partial=True, survey="2024")),
]
