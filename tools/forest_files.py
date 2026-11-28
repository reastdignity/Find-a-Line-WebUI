"""The Forestry Agency's lidar DEM files (林野庁加工; the sources of sources/catalogue/japan_forest.py): a static table of
every file of the chosen records, with each file's data mask, next to the catalogue
(sources/catalogue/japan_forest_files.npz), read by the sources' layers: a block is read only from a file whose mask
holds data under it, and --source auto takes the 30 m source far from any (has_data_near).

Per record (RECORDS: our name -> its CKAN name on www.geospatial.jp), one package_show lists its resources (only CKAN
maps a bucket key to its record); every `dem_<zone><row><column><quarter>_<edition>.tif` among them is asked at its
plain address in the bucket gsic-opendata (ckan/resources/<id>/<file>, or the record's own national-gov/... address)
for its first HEAD_BYTES (one range; once more up to MAX_HEAD_BYTES when its tags or tile entries lie beyond): the
answer gives the file's size, ETag and Last-Modified, the bytes its tags (read by GDAL from memory: rasterio's
MemoryFile). Each file must name the EPSG code of its code's zone (6668 + zone: the tags decide, never the record's
notes), pixels of 0.5 m (1e-6 relative) and lie on its quarter (sources.catalogue.japan_forest.rf_box, one pixel more
and 1 m of slack on every side), or the tool stops. Each file is also checked against the blocks' pixels by the
reader's own test (windows._coincide, at the file's first block and at its far corner): `on_pixels` in the table;
the catalogue refuses a file that is not (Tokushima's 0.49999987 m pixels with corners 1-2 cm off: every block would
be resampled bilinearly) unless its source says how such files are read.

The data mask, one cell per tile (256 m at 0.5 m), comes from the files themselves, never from a byte count alone.
Per file and class of tile (the tiles of one shape of valid pixels: full, the last row, the last column, the corner)
the class's empty tile is the first tile that decodes to nodata only (Deflate, predictor 1 or 2, float32), tried in
ascending size up to EMPTY_SIZES distinct sizes, EMPTY_TRIES tiles of each (a flat tile can be as small as an empty
one, or smaller); none found, every tile of the class is data. A tile whose byte count is not its class's empty size
is data; a tile of the empty size is read and compared byte for byte with the empty tile when it is a neighbour (8
directions, across a file's edge too) of a data tile, of the files read or of the rows kept from the table (other
records), and one that differs is data and has its own neighbours read in turn, until nothing new is found (a tile
of one constant height compresses to exactly the empty size: 1 757 of 6 000 heights at the Agency's zlib level 9,
the code review of 2026-11-27). What stays possible: constant ground wholly enclosed by empty tiles is called empty
(the 30 m source fills it). A tile without bytes (offset or count 0) is sparse and empty, but only when the file's
tile entries were read whole: entries GDAL cannot name in fewer bytes than the file has are an error. A file of
strips (Shonai's 10NB1, 10NC4, 10PB3; h30's 03QE1, 03QE3, 03QG2, one row each, Deflate; h30's 05MB4, 432 x 150 px of
4-row strips, uncompressed) of at most STRIP_WHOLE_BYTES is read whole (0.3-10 MB each) and masked from its decoded
pixels on cells of CELL_PX x CELL_PX px, as a tiled file's tiles: a cell with a pixel that is not nodata is data, so
the blocks, has_data_near and the offline boxes see where its data are. A larger strip file falls back to the rule of
the tiles with a strip as its cell (its strips the tiles of one class, a cell the strip's rows across the whole file;
the tool says so), an uncompressed one to data in every cell, since sizes cannot tell it (more requests, none lost).

Requests: one at a time, under the host's slot in the data folder and its turn (net.host_slot, net.rate_turn), our
User-Agent, every answer's length checked and capped, a row without a Last-Modified date refused (the catalogue reads
the dates when it is imported); per file one header range (a second when needed), a tile per
class, and the empty-sized neighbours of data tiles, adjacent ones merged into one range of at most MAX_RUN_BYTES.
A strip file read whole is one range. The first 429 or 503 stops the run. Kitaise's run of 2026-11-27: the
comment above japan_forest.KS_DTM.

It prints what changed against the whole table it replaces (files added, removed, replaced: another size, ETag or
address; masks changed). A file the Agency re-published in place: the blocks of a record are cached in a folder
stamped with the newest Last-Modified date of the record's files in the table (japan_forest.rf_stamp), so a table
made again after a replacement sends every block of that record to a new folder; until then blocks cached from the
old file are used and new ones read from the new file (the comment above japan_forest.RF_EDITION). Without
--record every record of the shipped table (SHIPPED) is made in one run, so records that touch always seed each
other's search; --record reads the records named and keeps the rows of the other records from the table it replaces
(their data tiles seed the search, their own masks are not revised). A record whose listing names no DEM file is an
error, never a table without its rows. --strips reads only the table's strip files that are still masked strip by
strip whole again (their size, ETag and Last-Modified must be the table's) and keeps every other row.

    uv run tools/forest_files.py [--record kitaise ...] [--strips] [--out sources/catalogue/japan_forest_files.npz]
                                 [--no-save] [--data-dir <folder>] [--max-requests N]
"""

import argparse
import json
import math
import os
import re
import sys
import urllib.parse
import warnings
import zlib
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

CKAN = "https://www.geospatial.jp/ckan/api/3/action/package_show"
BUCKET = "https://gsic-opendata.s3.ap-northeast-1.amazonaws.com"
# Our record names and their CKAN names (the organisation rinya). Not Aichi's (owarinishimikawa_078,
# higashimikawa_079) nor Oita's (oita_aerial_laser): held by the user until their files can be downloaded again
RECORDS: Dict[str, str] = {
    "kitaise": "kitaise_081", "syounai": "028_syounai", "h30": "h30_7_gouu", "r6": "r6_noto-peninsula-earthquake",
    "inatani": "inatani_067", "tokushima": "tokushima_aerial_laser", "yoshinokawa": "yoshinokawa_116"}
SHIPPED = ("kitaise", "syounai", "inatani", "h30", "r6")  # the records of the shipped table, made in one run
HEAD_BYTES = 65536
MAX_HEAD_BYTES = 2 ** 20
MAX_JSON_BYTES = 5_000_000
MAX_TILE_BYTES = 2 ** 20  # a tile decoded to find a class's empty size (the smallest of its class: a few KB)
MAX_RUN_BYTES = 2 ** 20   # adjacent empty-sized tiles read in one range up to this
EMPTY_TRIES = 8           # tiles of one size decoded, in row order, to find a class's empty tile
EMPTY_SIZES = 4           # the class's smallest distinct sizes tried, ascending (a flat tile can be smaller)
STRIP_WHOLE_BYTES = 32 * 2 ** 20  # a strip file up to this is read whole, its mask from its pixels
CELL_PX = 512             # the mask's cell of a strip file read whole (a tiled file's: its own 512 x 512 px tiles)
_NAME = re.compile(r"dem_(\d\d[A-Z][A-Z][1-4])_(\d{4})\.tiff?", re.I)

# What a fetch gives: (bytes, total size of the file, ETag, Last-Modified)
Got = Tuple[bytes, int, str, str]
RangeGet = Callable[[str, int, int], Got]


def dem_resources(package: dict) -> List[Tuple[str, str, int]]:
    """(code, key in the bucket, edition) of every DEM GeoTIFF of a record's package_show answer ("result"), sorted by
    code; a DEM file whose address is in neither the bucket nor CKAN's download of a resource is an error."""
    found = []
    for r in package["resources"]:
        url = (r.get("url") or "").split("?")[0]
        base = urllib.parse.unquote(url.rsplit("/", 1)[-1])
        match = _NAME.fullmatch(base)
        if not match:
            continue
        if url.startswith(BUCKET + "/"):
            key = url[len(BUCKET) + 1:]
        elif url.startswith("https://gsic-opendata.s3.amazonaws.com/"):
            key = url.split(".amazonaws.com/", 1)[1]
        elif "/ckan/dataset/" in url and "/download/" in url:
            key = f"ckan/resources/{r['id']}/{base}"
        else:
            raise ValueError(f"{base}: an address in neither the bucket nor CKAN's download: {url}")
        found.append((match.group(1).upper(), urllib.parse.unquote(key), int(match.group(2))))
    return sorted(found)


def skipped_dems(package: dict) -> List[str]:
    """The names of a record's resources that look like DEM files (dem_..._<year>) but whose address dem_resources
    does not take: Yoshinokawa's 14 files behind CKAN's own download (www.geospatial.jpdem_04fe4_2025.tif, answering
    500 and absent from the bucket's listing on 2026-11-27)."""
    taken = {code for code, _, _ in dem_resources(package)}
    return sorted(r["name"] for r in package["resources"]
                  if re.fullmatch(r"dem_\w+_\d{4}(\.tiff?)?", r.get("name") or "", re.I)
                  and r["name"].split("_")[1].upper() not in taken)


def _classes(src) -> Dict[Tuple[int, int], List[Tuple[int, int, int, int]]]:
    """The tiles of an open tiled file by the shape of their valid pixels: (rows, cols) -> [(x, y, offset, size)];
    a tile GDAL names no offset or size for gets 0 (sparse: file_row has made sure the entries were read whole)."""
    th, tw = src.block_shapes[0]
    nx, ny = -(-src.width // tw), -(-src.height // th)
    found: Dict[Tuple[int, int], List[Tuple[int, int, int, int]]] = {}
    for y in range(ny):
        for x in range(nx):
            offset = src.get_tag_item(f"BLOCK_OFFSET_{x}_{y}", "TIFF", bidx=1)
            size = src.get_tag_item(f"BLOCK_SIZE_{x}_{y}", "TIFF", bidx=1)
            shape = (min(th, src.height - y * th), min(tw, src.width - x * tw))
            found.setdefault(shape, []).append((x, y, int(offset or 0), int(size or 0)))
    return found


def _unnamed(src) -> int:
    """How many tiles or strips of an open file GDAL names no offset for (sparse, or beyond the bytes at hand)."""
    th, tw = src.block_shapes[0]
    return sum(src.get_tag_item(f"BLOCK_OFFSET_{x}_{y}", "TIFF", bidx=1) is None
               for y in range(-(-src.height // th)) for x in range(-(-src.width // tw)))


def decode_tile(raw: bytes, shape: Tuple[int, int], tile: Tuple[int, int], predictor: int,
                little: bool) -> np.ndarray:
    """A Deflate tile of float32 (predictor 1 or 2) as its valid pixels (shape of rows, columns); a strip file's last
    strip holds only its own rows (shape[0] x tw values)."""
    th, tw = tile
    words = np.frombuffer(zlib.decompress(raw), dtype="<u4" if little else ">u4")
    if words.size == shape[0] * tw and shape[0] < th:
        th = shape[0]
    if words.size != th * tw:
        raise ValueError(f"a tile of {words.size} values, not {th} x {tw}")
    words = words.reshape(th, tw)
    if predictor == 2:
        words = np.cumsum(words, axis=1, dtype=words.dtype)
    return words.view("<f4" if little else ">f4")[:shape[0], :shape[1]]


def class_empty(row: Dict, shape: Tuple[int, int], read: Callable[[int, int], bytes]) -> Optional[bytes]:
    """The empty tile of a class of a file's tiles: the bytes of the first tile, read(offset, size), that decodes to the
    file's nodata only, among the class's EMPTY_SIZES smallest distinct sizes in ascending order (a tile of one constant
    height compresses as small as an empty one, a sea flattened at 0.0 m smaller: 1 039 bytes at zlib 9 against 1 626),
    up to EMPTY_TRIES tiles of each size in row order; None when none of them is (no empty tile: every tile of the
    class is data, more requests but none lost)."""
    cid = row["class_ids"][shape]
    present = sorted((int(row["sizes"][y, x]), int(y), int(x))
                     for y, x in zip(*np.nonzero((row["shapes"] == cid) & (row["sizes"] > 0))))
    nodata = row["nodata"]
    for size in sorted({t[0] for t in present})[:EMPTY_SIZES]:
        if size > MAX_TILE_BYTES:
            break  # no empty tile is that large
        for _, y, x in [t for t in present if t[0] == size][:EMPTY_TRIES]:
            raw = read(int(row["offsets"][y, x]), size)
            values = decode_tile(raw, shape, (row["tile_h"], row["tile_w"]), row["predictor"], row["little"])
            if np.isnan(values).all() if nodata is None or np.isnan(nodata) else (values == nodata).all():
                return raw
    return None


def _tile_box(row: Dict, x: int, y: int) -> Tuple[float, float, float, float]:
    """(left, bottom, right, top) of a file's tile in its CRS, cut at the file's edges."""
    a, e, c, f = row["transform"]
    left, top = c + x * row["tile_w"] * a, f + y * row["tile_h"] * e
    return left, max(top + row["tile_h"] * e, f + row["height"] * e), min(left + row["tile_w"] * a,
                                                                           c + row["width"] * a), top


def _tiles_meeting(row: Dict, box: Tuple[float, float, float, float]) -> List[Tuple[int, int]]:
    """The tiles (x, y) of a file whose boxes meet a box (left, bottom, right, top in its CRS)."""
    a, e, c, f = row["transform"]
    left, bottom, right, top = box
    if c + row["width"] * a < left or c > right or f + row["height"] * e > top or f < bottom:
        return []
    w, h = row["tile_w"] * a, -row["tile_h"] * e
    ny, nx = row["sizes"].shape
    x0, x1 = max(math.floor((left - c) / w), 0), min(math.floor((right - c) / w), nx - 1)
    y0, y1 = max(math.floor((f - top) / h), 0), min(math.floor((f - bottom) / h), ny - 1)
    return [(x, y) for y in range(y0, y1 + 1) for x in range(x0, x1 + 1)]


def _runs(row: Dict, tiles) -> List[List[Tuple[int, int]]]:
    """Tiles of a file in runs of adjacent bytes (each run one range of at most MAX_RUN_BYTES)."""
    runs: List[List[Tuple[int, int]]] = []
    for x, y in sorted(tiles, key=lambda t: row["offsets"][t[1], t[0]]):
        offset, size = int(row["offsets"][y, x]), int(row["sizes"][y, x])
        if runs:
            (lx, ly), (fx, fy) = runs[-1][-1], runs[-1][0]
            end = int(row["offsets"][ly, lx] + row["sizes"][ly, lx])
            if end == offset and offset + size - int(row["offsets"][fy, fx]) <= MAX_RUN_BYTES:
                runs[-1].append((x, y))
                continue
        runs.append([(x, y)])
    return runs


def whole_mask(data: bytes, cell: int = CELL_PX) -> np.ndarray:
    """The data mask of a file read whole (a strip file) on cells of cell x cell px: a cell holding a pixel that is
    neither nodata nor NaN is data, from the pixels GDAL decodes from memory, cell rows at a time."""
    import rasterio
    from rasterio.io import MemoryFile
    from rasterio.windows import Window
    with rasterio.Env(), MemoryFile(data) as mem, mem.open() as src:
        ny, nx = -(-src.height // cell), -(-src.width // cell)
        mask = np.zeros((ny, nx), dtype=bool)
        for y in range(ny):
            values = src.read(1, window=Window(0, y * cell, src.width, min(cell, src.height - y * cell)))
            valid = ~np.isnan(values)
            if src.nodata is not None and not np.isnan(src.nodata):
                valid &= values != src.nodata
            columns = np.zeros(nx * cell, dtype=bool)
            columns[:src.width] = valid.any(axis=0)
            mask[y] = columns.reshape(nx, cell).any(axis=1)
    return mask


def masks(rows: Sequence[Dict], read: Callable[[Dict, int, int], bytes], report=print,
          kept: Sequence[Dict] = ()) -> Dict[str, int]:
    """The data masks of the tiled rows of one run (row["mask"] and row["empties"] set in place), by the rule of the
    docstring: every class's empty tile decoded, then the empty-sized tiles beside data tiles read (adjacent ones in
    one range: read(row, first, last)) and compared byte for byte with their class's empty tile, across the files'
    edges, until no new data tile is found. A strip file of at most STRIP_WHOLE_BYTES is read whole first and masked
    from its pixels (whole_mask: its tile_w and tile_h become the cell's); its data cells seed the search, as do the
    data tiles of kept rows (rows of other records kept from the table, with their masks). Returns the counts: tiles
    read, ranges asked, bytes, empty-sized tiles that held data, strip files read whole."""
    counts = {"read": 0, "ranges": 0, "bytes": 0, "data": 0, "whole": 0}
    whole = []
    for r in rows:
        if r.get("tiled", True):
            continue
        if r["size"] > STRIP_WHOLE_BYTES:
            report(f"{r['record']} {r['code']}: a strip file of {r['size']} bytes, over {STRIP_WHOLE_BYTES}: masked "
                   f"strip by strip (a strip a cell)")
            continue
        data = read(r, 0, r["size"] - 1)
        counts["ranges"], counts["bytes"], counts["whole"] = counts["ranges"] + 1, counts["bytes"] + len(data), \
            counts["whole"] + 1
        r.update(mask=whole_mask(data), tile_w=CELL_PX, tile_h=CELL_PX, empties={}, whole=len(data))
        whole.append(r)
    seen = {id(r) for r in whole}
    tiled = [r for r in rows if r["tile_w"] and id(r) not in seen]
    empty_of: Dict[Tuple[int, int], Optional[bytes]] = {}
    state: Dict[int, np.ndarray] = {}  # 1 data, 0 empty, -1 empty-sized and not read
    for k, r in enumerate(tiled):
        decided = np.ones(r["sizes"].shape, dtype=np.int8)
        decided[r["sizes"] <= 0] = 0  # sparse
        for shape, cid in r["class_ids"].items():
            empty_of[k, cid] = None
            if r["compression"] != "DEFLATE":  # uncompressed: every cell the same size, data in every cell
                continue
            asked = []
            empty = class_empty(r, shape, lambda offset, size, r=r: asked.append(size) or read(r, offset,
                                                                                               offset + size - 1))
            counts["read"], counts["ranges"] = counts["read"] + len(asked), counts["ranges"] + len(asked)
            empty_of[k, cid] = empty
            if empty is not None:
                decided[(r["shapes"] == cid) & (r["sizes"] == len(empty))] = -1
        state[k] = decided
    queue = [(tiled[k], int(x), int(y)) for k in state for y, x in zip(*np.nonzero(state[k] == 1))]
    queue += [(r, int(x), int(y)) for r in list(kept) + whole if r.get("tile_w") and r.get("mask") is not None
              for y, x in zip(*np.nonzero(r["mask"]))]
    while queue:
        wanted: Dict[int, set] = {}
        for seed, x, y in queue:
            left, bottom, right, top = _tile_box(seed, x, y)
            grown = (left - 1.0, bottom - 1.0, right + 1.0, top + 1.0)
            for j, other in enumerate(tiled):
                if other["epsg"] == seed["epsg"]:
                    wanted.setdefault(j, set()).update(t for t in _tiles_meeting(other, grown)
                                                       if state[j][t[1], t[0]] == -1)
        queue = []
        for j, tiles in wanted.items():
            r = tiled[j]
            for run in _runs(r, tiles):
                start = int(r["offsets"][run[0][1], run[0][0]])
                end = int(r["offsets"][run[-1][1], run[-1][0]] + r["sizes"][run[-1][1], run[-1][0]])
                data = read(r, start, end - 1)
                counts["ranges"] += 1
                counts["bytes"] += len(data)
                for x, y in run:
                    offset, size = int(r["offsets"][y, x]) - start, int(r["sizes"][y, x])
                    counts["read"] += 1
                    if data[offset:offset + size] == empty_of[j, int(r["shapes"][y, x])]:
                        state[j][y, x] = 0
                    else:
                        state[j][y, x] = 1
                        counts["data"] += 1
                        queue.append((r, x, y))
    for k, r in enumerate(tiled):
        r["mask"] = state[k] == 1  # an empty-sized tile never read (no data tile beside it) is empty
        r["empties"] = {shape: (None if empty_of[k, cid] is None else len(empty_of[k, cid]))
                        for shape, cid in r["class_ids"].items()}
    report(f"masks: {counts['read']} tiles read in {counts['ranges']} ranges ({counts['bytes']} bytes beside the "
           f"classes' empty tiles, strip files read whole included: {counts['whole']}); {counts['data']} empty-sized "
           f"tiles held data")
    return counts


def on_pixels(src, block_m: float) -> bool:
    """Whether every block of block_m (0.5 m pixels, edges on whole multiples) over a file reads the file's own pixels
    by the reader's own test (windows._coincide): the block at the file's first corner and those at its far edges
    (an offset off the grid grows linearly over the file)."""
    from affine import Affine
    from sources.readers.windows import _coincide
    t = src.transform
    far_x, far_y = t.c + src.width * t.a, t.f + src.height * t.e
    for x in (math.floor(t.c / block_m) * block_m, math.floor((far_x - 1e-3) / block_m) * block_m):
        for y in (math.ceil(t.f / block_m) * block_m, math.ceil((far_y + 1e-3) / block_m) * block_m):
            if _coincide(src, Affine(0.5, 0, x, 0, -0.5, y)) is None:
                return False
    return True


def http_date(text: str, what: str) -> str:
    """A Last-Modified date as the table stores it: parsed here (any HTTP date form, RFC 1123, RFC 850 or asctime,
    with or without a zone: one without, or -0000, is GMT as HTTP's dates are) and written again in GMT (RFC 1123);
    ValueError for one that cannot be parsed, so a table the tool makes never breaks the catalogue's import (rf_stamp
    reads every date when it is imported, and compares them)."""
    from datetime import timezone
    from email.utils import format_datetime, parsedate_to_datetime
    try:
        when = parsedate_to_datetime(text)
    except (TypeError, ValueError, IndexError):
        raise ValueError(f"{what}: no Last-Modified date in the answer ({text!r}): not saved, so a table made by the "
                         f"tool never breaks the catalogue's import")
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return format_datetime(when.astimezone(timezone.utc), usegmt=True)


def file_row(record: str, code: str, key: str, edition: int, head: Got,
             more: Optional[Callable[[int], Got]] = None) -> Dict:
    """A file's row of the table from its first bytes (head; more(n): its first n bytes, asked once when its tags or
    tile entries lie beyond them), without its mask (masks makes it); ValueError when its tags do not fit its code
    (CRS, pixel size, place), or when tile entries stay unnamed in fewer bytes than the file has."""
    import rasterio
    from rasterio.io import MemoryFile
    from sources.catalogue.japan_forest import RF_BLOCK_M, RF_RES, rf_box
    zone, left, bottom, right, top = rf_box(code)
    data, size, etag, modified = head
    modified = http_date(modified, f"{record} {code}")
    while True:
        try:
            with warnings.catch_warnings(), rasterio.Env(), MemoryFile(data) as mem:
                # a header cut before its geokeys opens without a transform: read more (below), not a warning
                warnings.simplefilter("ignore", rasterio.errors.NotGeoreferencedWarning)
                with mem.open() as src:
                    unnamed = _unnamed(src)
                    if more is not None and len(data) < min(MAX_HEAD_BYTES, size) and (src.crs is None or unnamed):
                        raise EOFError("tags or tile entries beyond the bytes at hand")  # a strip file's arrays first
                    if unnamed and len(data) < size:
                        raise ValueError(f"{record} {code}: {unnamed} tile entries not named in the first "
                                         f"{len(data)} bytes of {size}")
                    epsg = src.crs.to_epsg() if src.crs else None
                    if epsg != 6668 + zone:
                        raise ValueError(f"{record} {code}: its tags name {src.crs}, not EPSG:{6668 + zone} of "
                                         f"zone {zone}")
                    t = src.transform
                    if abs(t.a - RF_RES) > RF_RES * 1e-6 or abs(-t.e - RF_RES) > RF_RES * 1e-6 or t.b or t.d:
                        raise ValueError(f"{record} {code}: pixels of {t.a} x {-t.e} m, not {RF_RES} m")
                    far_x, far_y = t.c + src.width * t.a, t.f + src.height * t.e
                    slack = RF_RES + 1.0
                    if not (left - slack <= t.c and far_x <= right + slack and bottom - slack <= far_y
                            and t.f <= top + slack and t.c < far_x and far_y < t.f):
                        raise ValueError(f"{record} {code}: the file ({t.c}, {far_y})-({far_x}, {t.f}) does not lie "
                                         f"on its quarter ({left}, {bottom})-({right}, {top})")
                    th, tw = src.block_shapes[0]
                    tiled = bool(src.profile.get("tiled", False))
                    st = src.tags(ns="IMAGE_STRUCTURE")
                    row = {"record": record, "code": code, "key": key, "edition": edition, "size": size,
                           "etag": etag, "modified": modified, "epsg": epsg, "transform": (t.a, t.e, t.c, t.f),
                           "width": src.width, "height": src.height, "tile_w": tw,
                           "tile_h": th, "mask": None, "empties": {},
                           "strip_rows": None if tiled else th, "compression": st.get("COMPRESSION"),
                           "tiled": tiled, "on_pixels": on_pixels(src, RF_BLOCK_M)}
                    if st.get("COMPRESSION", "NONE") not in ("DEFLATE", "NONE") \
                            or st.get("PREDICTOR", "1") not in ("1", "2") or src.dtypes[0] != "float32":
                        raise ValueError(f"{record} {code}: no mask rule for {st.get('COMPRESSION')}, predictor "
                                         f"{st.get('PREDICTOR')}, {src.dtypes[0]}")
                    ny, nx = -(-src.height // th), -(-src.width // tw)
                    sizes, offsets = np.zeros((ny, nx), np.int64), np.zeros((ny, nx), np.int64)
                    shapes, class_ids = np.zeros((ny, nx), np.int16), {}
                    for shape, tiles in _classes(src).items():
                        cid = class_ids.setdefault(shape, len(class_ids))
                        for x, y, offset, n in tiles:
                            shapes[y, x] = cid
                            if offset > 0 and n > 0:
                                sizes[y, x], offsets[y, x] = n, offset
                    row.update(sizes=sizes, offsets=offsets, shapes=shapes, class_ids=class_ids,
                               predictor=int(st.get("PREDICTOR", "1")), little=data[:2] == b"II", nodata=src.nodata)
                    return row
        except (EOFError, rasterio.errors.RasterioIOError) as e:
            if more is None or len(data) >= min(MAX_HEAD_BYTES, size):
                raise ValueError(f"{record} {code}: the header does not fit in {len(data)} bytes ({e})")
            data, more = more(min(MAX_HEAD_BYTES, size))[0], None  # once


def save(path: str, rows: Sequence[Dict]):
    """The table: one entry per file, sorted by record and code, the masks packed as bits in one array."""
    rows = sorted(rows, key=lambda r: (r["record"], r["code"]))
    bits, starts, at = [], [], 0
    for r in rows:
        starts.append(at)
        if r["mask"] is not None:
            bits.append(r["mask"].ravel())
            at += r["mask"].size
    np.savez_compressed(
        path, record=np.array([r["record"] for r in rows]), code=np.array([r["code"] for r in rows]),
        key=np.array([r["key"] for r in rows]), edition=np.array([r["edition"] for r in rows], dtype=np.int16),
        size=np.array([r["size"] for r in rows], dtype=np.int64), etag=np.array([r["etag"] for r in rows]),
        modified=np.array([r["modified"] for r in rows]), epsg=np.array([r["epsg"] for r in rows], dtype=np.int32),
        transform=np.array([r["transform"] for r in rows], dtype=np.float64).reshape(len(rows), 4),
        width=np.array([r["width"] for r in rows], dtype=np.int32),
        height=np.array([r["height"] for r in rows], dtype=np.int32),
        tile_w=np.array([r["tile_w"] for r in rows], dtype=np.int32),
        tile_h=np.array([r["tile_h"] for r in rows], dtype=np.int32),
        on_pixels=np.array([bool(r["on_pixels"]) for r in rows], dtype=bool),
        mask_start=np.array(starts, dtype=np.int64),
        masks=np.packbits(np.concatenate(bits) if bits else np.zeros(0, dtype=bool)))


def load(path: str) -> Dict[Tuple[str, str], Dict]:
    """A saved table by (record, code) (empty when there is none), each row as save takes it."""
    if not os.path.exists(path):
        return {}
    from sources.catalogue.japan_forest import load_table
    return {(r.record, r.code): {"record": r.record, "code": r.code, "key": r.key, "edition": r.edition,
                                 "size": r.size, "etag": r.etag, "modified": r.modified, "epsg": r.epsg,
                                 "transform": (r.a, r.e, r.c, r.f), "width": r.width, "height": r.height,
                                 "tile_w": r.tile_w, "tile_h": r.tile_h, "on_pixels": r.on_pixels, "mask": r.mask}
            for r in load_table(path)}


def changes(old: Dict[Tuple[str, str], Dict], new: Dict[Tuple[str, str], Dict]) -> List[str]:
    """What a new table changes against the old one, as lines: files added, removed, replaced (another size, ETag or
    address), masks changed (the tiles with data now and before)."""
    added = sorted(set(new) - set(old))
    removed = sorted(set(old) - set(new))
    replaced = sorted(k for k in set(old) & set(new)
                      if any(old[k][f] != new[k][f] for f in ("size", "etag", "key")))
    masked = []
    for k in sorted(set(old) & set(new)):
        a, b = old[k]["mask"], new[k]["mask"]
        if (a is None) != (b is None) or a is not None and (a.shape != b.shape or (a != b).any()):
            masked.append((k, None if a is None else int(a.sum()), None if b is None else int(b.sum())))
    name = lambda ks: [f"{r} {c}" for r, c in ks[:10]]  # noqa: E731
    return [f"files added: {len(added)} {name(added)}", f"files removed: {len(removed)} {name(removed)}",
            f"files replaced (size, ETag or address): {len(replaced)} {name(replaced)}",
            f"masks changed: {len(masked)} {[(f'{r} {c}', a, b) for (r, c), a, b in masked[:10]]}"]


class Fetcher:
    """The tool's requests: one at a time, each under its host's slot in the data folder and its turn of the host's
    rate (net.host_slot, net.rate_turn), our User-Agent, every answer capped and its length checked; a 429 or 503
    stops the run."""

    def __init__(self, cache_dir: str, max_requests: Optional[int] = None):
        self.cache_dir, self.requests, self.bytes, self.max_requests = cache_dir, 0, 0, max_requests

    def _count(self, url: str):
        """One more request, never past max_requests (the run stops before the request is made: RuntimeError)."""
        if self.max_requests is not None and self.requests >= self.max_requests:
            raise RuntimeError(f"stopped before request {self.requests + 1}: the run may make {self.max_requests} "
                               f"(--max-requests); nothing saved")
        self.requests += 1

    @staticmethod
    def _status(url: str, status: int, wanted: int):
        if status in (429, 503):
            raise RuntimeError(f"{url}: HTTP {status}: stopped (the host asks to slow down)")
        if status != wanted:
            raise RuntimeError(f"{url}: HTTP {status}")

    def json(self, url: str) -> dict:
        import cache
        from sources import net
        with net.host_slot(self.cache_dir, url):
            net.rate_turn(url)
            self._count(url)  # every attempt, failed ones too
            with net.session().get(url, headers=cache.http_headers(), timeout=120, stream=True) as response:
                self._status(url, response.status_code, 200)
                data = response.raw.read(MAX_JSON_BYTES + 1, decode_content=True)
        self.bytes += len(data)
        if len(data) > MAX_JSON_BYTES:
            raise RuntimeError(f"{url}: more than {MAX_JSON_BYTES} bytes")
        return json.loads(data)

    def range(self, url: str, first: int, last: int) -> Got:
        import cache
        from sources import net
        headers = {**cache.http_headers(), "Range": f"bytes={first}-{last}"}
        with net.host_slot(self.cache_dir, url):
            net.rate_turn(url)
            self._count(url)  # every attempt, failed ones too
            with net.session().get(url, headers=headers, timeout=120, stream=True) as response:
                self._status(url, response.status_code, 206)
                data = response.raw.read(last - first + 2)
                total = int((response.headers.get("Content-Range") or "/0").rsplit("/", 1)[-1])
                etag = (response.headers.get("ETag") or "").strip('"')
                modified = response.headers.get("Last-Modified") or ""
        self.bytes += len(data)
        if len(data) != min(last, total - 1) - first + 1:
            raise RuntimeError(f"{url}: {len(data)} bytes for the range {first}-{last}")
        return data, total, etag, modified


def record_rows(record: str, package: dict, get: RangeGet, report=print) -> List[Dict]:
    """The rows of a record's DEM files (its package_show "result") without their masks, each file's header asked
    through get(url, first, last)."""
    rows = []
    skipped = skipped_dems(package)
    if skipped:
        report(f"{record}: {len(skipped)} DEM files without a plain address in the bucket, left out: {skipped}")
    listed = dem_resources(package)
    if not listed:
        raise ValueError(f"{record}: its listing names no DEM file: nothing saved (a table without the record's rows "
                         f"would break the catalogue's import)")
    for code, key, edition in listed:
        url = f"{BUCKET}/{key}"
        rows.append(file_row(record, code, key, edition, get(url, 0, HEAD_BYTES - 1),
                             lambda n, url=url: get(url, 0, n - 1)))
    return rows


def describe(row: Dict) -> str:
    """A row as one line of the tool's report."""
    cell = "cells" if row.get("whole") else "tiles"
    return (f"{row['record']} {row['code']}: EPSG:{row['epsg']} {row['width']} x {row['height']} px, {row['size']} "
            f"bytes, {'on' if row['on_pixels'] else 'OFF'} the blocks' pixels, "
            + (f"{cell} {row['tile_w']} x {row['tile_h']}, {int(row['mask'].sum())} of {row['mask'].size} with data, "
               f"empty sizes {dict(sorted(row['empties'].items()))}" if row["mask"] is not None
               else f"strips of {row['strip_rows']} rows, {row['compression']}: no mask")
            + ("" if row["tiled"] else f" (strips of {row['strip_rows']} rows, {row['compression']}"
               + (f", read whole: {row['whole']} bytes)" if row.get("whole") else ")")))


def refresh_strips(old: Dict[Tuple[str, str], Dict], get: RangeGet, report=print) -> List[Dict]:
    """The table's strip files still masked strip by strip (a cell as wide as the file) and of at most
    STRIP_WHOLE_BYTES, read whole again (one range each) and masked from their pixels (whole_mask), in place; their
    size, ETag and Last-Modified must be the table's (another: RuntimeError, the record must be made again). Returns
    the rows changed."""
    done = []
    for (record, code), row in sorted(old.items()):
        if row["mask"] is None or row["tile_w"] != row["width"] or row["tile_h"] == row["tile_w"]:
            continue  # a tiled file (square tiles), or a strip file masked on square cells already
        if row["size"] > STRIP_WHOLE_BYTES:
            report(f"{record} {code}: a strip file of {row['size']} bytes, over {STRIP_WHOLE_BYTES}: kept strip by "
                   f"strip")
            continue
        data, total, etag, modified = get(f"{BUCKET}/{row['key']}", 0, row["size"] - 1)
        if (total, etag, http_date(modified, f"{record} {code}")) != (row["size"], row["etag"], row["modified"]):
            raise RuntimeError(f"{record} {code}: the bucket's file is not the table's ({total}, {etag}, {modified}): "
                               f"make the record again (--record {record})")
        before = int(row["mask"].sum())
        row.update(mask=whole_mask(data), tile_w=CELL_PX, tile_h=CELL_PX)
        report(f"{record} {code}: read whole ({len(data)} bytes): strips with data {before}, cells of {CELL_PX} px "
               f"with data {int(row['mask'].sum())} of {row['mask'].size}")
        done.append(row)
    return done


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--record", action="append", choices=sorted(RECORDS),
                        help=f"a record to read (repeatable; default: {', '.join(SHIPPED)}); the table keeps the other "
                             f"records' rows")
    parser.add_argument("--out", default=os.path.join(HERE, "sources", "catalogue", "japan_forest_files.npz"))
    parser.add_argument("--no-save", action="store_true", help="print the rows and changes only")
    parser.add_argument("--data-dir", help="the data folder whose host slots the requests take (default: the app's)")
    parser.add_argument("--max-requests", type=int, help="stop the run before more requests than this (nothing saved)")
    parser.add_argument("--strips", action="store_true",
                        help="read only the table's strip files still masked strip by strip whole again, keep the rest")
    args = parser.parse_args(argv)
    import cache
    cache_dir = os.path.join(cache.data_dir(args.data_dir), "cache")
    cache.check_layout(cache_dir)  # a new cache is marked first: the host slots' lock files would make it unusable
    fetch = Fetcher(cache_dir, args.max_requests)
    if args.strips:
        old = load(args.out)
        before = {k: dict(v) for k, v in old.items()}
        done = refresh_strips(old, fetch.range)
        for line in changes(before, old):
            print(line)
        print(f"{len(done)} strip files read whole; {fetch.requests} requests, {fetch.bytes} bytes")
        if done and not args.no_save:
            save(args.out, list(old.values()))
            print(f"written {args.out}")
        return
    records = args.record or list(SHIPPED)
    rows = []
    for record in records:
        package = fetch.json(f"{CKAN}?id={urllib.parse.quote(RECORDS[record])}")["result"]
        rows += record_rows(record, package, fetch.range)
    old = load(args.out)
    kept = [row for (record, _), row in old.items() if record not in records]
    masks(rows, lambda row, first, last: fetch.range(f"{BUCKET}/{row['key']}", first, last)[0], kept=kept)
    for row in rows:
        print(describe(row))
    new = {(r["record"], r["code"]): r for r in rows + kept}
    print(f"kept from the table: {len(kept)} rows of the records not read")
    for line in changes(old, new):
        print(line)
    print(f"{len(rows)} files read, {sum(r['size'] for r in rows) / 1e9:.2f} GB; {fetch.requests} requests, "
          f"{fetch.bytes} bytes")
    if not args.no_save:
        save(args.out, list(new.values()))
        print(f"written {args.out}")


if __name__ == "__main__":
    from progress import utf8_output
    utf8_output()  # redirected output in UTF-8, not the Windows code page
    main()
