"""
The data checks of a new source (or download path) as one command (run by hand; docs/regression-tests.md,
"Data checks for a new source or download path").

    uv run tools/check_source.py SOURCE --lat LAT --lon LON [--radius 1500] [--resolution 10]
        [--layers nmt,nmpt] [--reference auto|fabdem|copernicus|FILE] [--shift-range 200]
        [--shift-step M] [--samples 3] [--data-dir DIR] [--elevation-file F --surface-file F] [--json OUT]

For each layer of the source (terrain: nmt, surface: nmpt), on a grid built as a search builds
it (search.plan_search without margin, water and gap filling), downloading through the
layer's own path into the cache of --data-dir:

1. shift: the layer mosaicked over the grid enlarged by --shift-range (sources.prepare_layer: with the layer's
   floor and height offset, the heights a search uses), compared with a
   reference on the grid (auto: the terrain with FABDEM, the surface with Copernicus GLO-30;
   or a raster file) at whole-pixel shifts; the best shift is the correction to add to the
   layer's `shift` (data placed 56 m east needs -56). WARN if it is more than 30 m away.
2. valid: the share of pixels with data (after the layer's floor) inside the circle (at most 500 m) at 1 m and at 5 m;
   WARN if 5 m is more than 1 percentage point below 1 m (a server that loses data when it
   downsamples).
3. files: --samples cached tiles against their source files read through GDAL (/vsicurl/,
   /vsizip/): the largest difference, the share of equal values, the same pixels without
   data (blocks: against the newest file with data there; a layer of heights above the ellipsoid
   against the files after its geoid's correction, as it caches them; a member of a remote ZIP
   (ZipMemberTiles, PackageTiles) read again by Range and opened by GDAL, with the layer's floor rule applied, in
   the tile's own CRS when it names one; a ".lem" sheet by the check's own parser, placed by its CSV header;
   "id,x,y,z,flag" rows by the check's own parser, every row kept; a sheet of several files (surveys of several
   years, two deliveries) composed again as the layer composes it, newest first, the fuller of one year first).
   n/a for WCS tiles and local files. Both sides as the provider gave them: a floor or a height offset applied
   where the tiles are read onto the grid (Layer.floor_of,
   Layer.height_offset) is on neither.
4. alignment: the cached tiles' pixel edges against Source.grid_origin, their pixel size and CRS.
5. precision: the share of whole-metre and whole-centimetre heights; WARN above 90% whole metres.
6. missing: tiles the service had no data for (normal over the sea; on land a lost tile).

Each check is PASS, WARN, FAIL or n/a; the exit code is 1 when one FAILs. --json writes the
numbers. The tool writes only into the cache of --data-dir (use a scratch folder for a new
source) and a work folder there, deleted at the end.
"""

import argparse
import contextlib
import gc
import io
import json
import math
import os
import re
import sys
import zipfile
from typing import Dict, List, Optional, Tuple

import numpy as np
import rasterio as rio
import rasterio.cache
import rasterio.io
from rasterio.enums import Resampling
from rasterio.vrt import WarpedVRT

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

import area as ar  # noqa: E402
import cache  # noqa: E402
import search  # noqa: E402
import sources as src  # noqa: E402
from sources.layers.cellsheets import CellSheetTiles  # noqa: E402
from sources.layers.s3sheets import S3SheetSets  # noqa: E402
from sources.layers.wmsr import WmsrTiles  # noqa: E402
from sources.readers import windows  # noqa: E402
from sources.readers.zipmember import drop_below, xyz_rows  # noqa: E402
from params import SearchParams  # noqa: E402
from progress import progress  # noqa: E402

PASS, WARN, FAIL, NA = "PASS", "WARN", "FAIL", "n/a"
SHIFT_WARN_M = 30          # a best shift further than this from (0, 0) is a warning
VALID_RADIUS_MAX = 500     # the circle of the valid shares at 1 and 5 m
VALID_DROP_PP = 1.0        # 5 m may lose this many percentage points against 1 m
WHOLE_METRES_WARN = 0.9    # share of whole-metre heights above which the precision is a warning
EQUAL_M = 0.01             # a cached tile and its source file differ by at most this (the tiles are LERC within
                           # 5 mm of what was read: the share of equal values is no longer 100 %)
ALIGN_TILES = 20           # cached tiles looked at for the alignment and the precision
LAYER_NAMES = {"nmt": "terrain", "nmpt": "surface"}


# --- metrics (pure functions, unit-tested) ---

def shift_table(raw: np.ndarray, reference: np.ndarray, margin_px: int, step_px: int = 1,
                mask: Optional[np.ndarray] = None) -> Dict[Tuple[int, int], Tuple[float, float, int]]:
    """Medians of |d| and d (d = layer - reference) over the inner window for every correction
    (i, j) in pixels (east, north) within margin_px, in steps of step_px: the layer corrected by
    (i, j) has at [r, c] the raw value at [r + j, c - i]. raw and reference are on the same
    grid; the inner window leaves margin_px on every side; mask (of the inner window) limits
    the pixels compared. Corrections without common pixels are left out."""
    h, w = reference.shape
    inner = reference[margin_px:h - margin_px, margin_px:w - margin_px]
    keep = np.isfinite(inner) if mask is None else np.isfinite(inner) & mask
    table = {}
    for j in range(-margin_px, margin_px + 1, step_px):
        for i in range(-margin_px, margin_px + 1, step_px):
            moved = raw[margin_px + j:h - margin_px + j, margin_px - i:w - margin_px - i]
            both = keep & np.isfinite(moved)
            if both.any():
                d = moved[both].astype(np.float64) - inner[both]
                table[(i, j)] = (float(np.median(np.abs(d))), float(np.median(d)), int(both.sum()))
    return table


def best_shift(table: Dict[Tuple[int, int], Tuple[float, float, int]]) -> Tuple[int, int]:
    """The correction with the smallest median |d| (the nearest to (0, 0) among equals)."""
    return min(table, key=lambda k: (round(table[k][0], 6), k[0] ** 2 + k[1] ** 2, k))


def valid_share(values: np.ndarray, mask: np.ndarray) -> float:
    """The share of the masked pixels that have data."""
    return float(np.isfinite(values[mask]).mean()) if mask.any() else 0.0


def precision(values: np.ndarray) -> Tuple[float, float]:
    """(whole metres, whole centimetres): the shares of the heights with data that are such."""
    v = values[np.isfinite(values)].astype(np.float64)
    if not v.size:
        return 0.0, 0.0
    return (float((np.abs(v - np.round(v)) < 1e-4).mean()),
            float((np.abs(v * 100 - np.round(v * 100)) < 1e-2).mean()))


def compare(tile: np.ndarray, source: np.ndarray, source_only: bool = False) -> Dict:
    """A cached tile against its source on the same pixels: the largest |difference|, the
    share of equal values (where both have data) and of pixels where both agree on having
    data; source_only: only where the source has data (a block composed from several files)."""
    both = np.isfinite(tile) & np.isfinite(source)
    d = np.abs(tile[both].astype(np.float64) - source[both]) if both.any() else np.zeros(0)
    where = np.isfinite(source) if source_only else np.ones(tile.shape, bool)
    same = (np.isfinite(tile) == np.isfinite(source))[where]
    return {"pixels": int(both.sum()), "max_abs_m": float(d.max()) if d.size else None,
            "equal": float((d == 0).mean()) if d.size else None,
            "same_nodata": float(same.mean()) if same.size else None}


def origin_offset(transform, res: float, origin: Tuple[float, float]) -> float:
    """How far (metres, at most res / 2) the pixel edges of a raster are from origin modulo res."""
    worst = 0.0
    for value, o in ((transform.c, origin[0]), (transform.f, origin[1])):
        off = (value - o) % res
        worst = max(worst, min(off, res - off))
    return worst


# --- helpers ---

class Check(dict):
    def __init__(self, name: str, status: str, text: str, **values):
        super().__init__(name=name, status=status, text=text, **values)


def _quiet(kind: str, text: str):
    if kind == "warning":
        print(f"Warning: {text}")


def _plan(args, data: str, work: str, radius: float, resolution: float):
    params = SearchParams(lat=args.lat, lon=args.lon, radius=radius, resolution=resolution, source=args.source,
                          elevation_file=args.elevation_file, surface_file=args.surface_file, water="off",
                          fill_gaps="off", ortho="never", no_html=True)
    return search.plan_search(params, search.Paths(data, work), _quiet, with_margin=False)


def _mosaic(layer: src.Layer, grid, cache_dir: str, work: str, name: str) -> np.ndarray:
    path = src.prepare_layer(layer, grid, cache_dir, os.path.join(work, f"{name}.npy"), name)
    values = np.load(path)  # into memory: the work folder is deleted at the end (Windows)
    gc.collect()
    return values


def _reference(args, kind: str) -> src.Layer:
    choice = args.reference
    if choice == "auto":
        choice = "fabdem" if kind == "nmt" else "copernicus"
    if choice == "fabdem":
        return src.SOURCES["europe"].nmt
    if choice == "copernicus":
        return src.SOURCES["europe"].nmpt
    return src.FileLayer("Reference file", choice)


def _cached_tiles(layer: src.Layer, grid, cache_dir: str) -> List:
    tiles = layer.tiles(grid) or []
    return [t for t in tiles if cache.state(cache_dir, layer.tile_path(cache_dir, t), layer.processing) == "ok"]


def _spread(items: List, n: int) -> List:
    """n items spread over the list (all when there are fewer)."""
    if len(items) <= n:
        return list(items)
    return [items[k * len(items) // n] for k in range(n)]


def _gdal_path(url: str) -> str:
    """GDAL's path of a source file: a remote one by /vsicurl/, a ZIP (or a member of one: <zip>/<member>) by
    /vsizip/."""
    path = f"/vsicurl/{url}" if url.startswith(("http://", "https://")) else url
    return f"/vsizip/{path}" if url.lower().endswith(".zip") or ".zip/" in url.lower() else path


def _read_source(url: str, profile: Dict, resampling: Resampling = Resampling.nearest,
                 cache_dir: Optional[str] = None, warp: Optional[Dict[str, str]] = None) -> np.ndarray:
    """A source file's values on the pixels of a cached tile (nearest: the same pixels when the
    tile is on the file's own grid; average for a layer that averages its files' pixels, as its
    Download does), NaN without data. A read GDAL could not complete although it
    returned (src.net.gdal_errors: what it could not fetch comes back as nodata or zeros) raises
    RuntimeError with GDAL's error, never a false difference. GDAL's settings as
    src.net._gdal_http's (retries of requests without an answer, the open's fewer: net.open_gdal, the connect
    timeout, a one-connection host's ranges one after another: net.single_connection, the blocks read in this
    thread) but for the extensions: the sources here include zips and ASCII grids. With cache_dir the read holds a
    slot of the host (net.host_slot) as the layers' reads do. warp: GDAL warp options for the WarpedVRT (an OPR
    file's cubic: windows.opr_scale; the WarpedVRT takes them as keywords, not through warp_extras=)."""
    env = rio.Env(GDAL_HTTP_USERAGENT=cache.http_headers()["User-Agent"], GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
                  GDAL_HTTP_TIMEOUT="120", GDAL_HTTP_MAX_RETRY=str(src.net.RETRIES), GDAL_HTTP_RETRY_DELAY="2",
                  GDAL_HTTP_CONNECTTIMEOUT=str(src.net.CONNECT_TIMEOUT_S),
                  GDAL_HTTP_MULTIRANGE="SERIAL" if src.net.single_connection(url) else "YES",
                  GDAL_HTTP_RETRY_CODES=src.net.GDAL_RETRY_CODES, GDAL_NUM_THREADS="1")
    slot = src.net.host_slot(cache_dir, url) if cache_dir else contextlib.nullcontext()
    try:
        with slot, env, src.net.gdal_errors() as errors:
            src.net.rate_turn(url)  # the file's read counts as one request where its host has a rate (HOST_RATES_OF)
            with src.net.open_gdal(_gdal_path(url)) as source:
                # ASCII grids name no CRS, Caribbean Netherlands' AHN files only a local one (the layer forces its
                # own)
                local = source.crs is None or windows._local(source.crs)
                kwargs = {"src_crs": profile["crs"]} if local else {}
                with WarpedVRT(source, crs=profile["crs"], transform=profile["transform"], width=profile["width"],
                               height=profile["height"], resampling=resampling, **kwargs, **(warp or {})) as vrt:
                    values = vrt.read(1, masked=True).astype(np.float32).filled(np.nan)
        if errors:
            raise RuntimeError("not read completely: " + "; ".join(dict.fromkeys(errors)))
    except (RuntimeError, rio.errors.RasterioError):
        if url.startswith(("http://", "https://")):
            rio.cache.invalidate(url)  # not the short answer again from GDAL's cache
        raise
    values[values < -500] = np.nan  # as the layers clean their tiles (sources.layer.VALID_MIN)
    return values


def _read_ranged(url: str, profile: Dict, resampling: Resampling = Resampling.nearest,
                 cache_dir: Optional[str] = None) -> np.ndarray:
    """A source file of a layer that reads its files through our own range requests (Windows(ranged=True):
    Estonia's PHP download address, which GDAL's /vsicurl/ does not take for a .tif) on the pixels of a cached tile,
    through ranges.open_remote (the first bytes a TIFF's) and a WarpedVRT; NaN without data. Raises RuntimeError
    when a range could not be read whole. With cache_dir under a slot of the host (net.host_slot); every range takes
    its turn (ranges.get_range)."""
    from sources.readers import ranges
    slot = src.net.host_slot(cache_dir, url) if cache_dir else contextlib.nullcontext()
    with slot, src.net.gdal_errors() as errors, ranges.open_remote(url, tiff_only=True) as (source, file):
        with WarpedVRT(source, crs=profile["crs"], transform=profile["transform"], width=profile["width"],
                       height=profile["height"], resampling=resampling) as vrt:
            values = vrt.read(1, masked=True).astype(np.float32).filled(np.nan)
    if errors or file.error is not None:
        raise RuntimeError("not read completely: " + cache.clean_error(file.error or "; ".join(dict.fromkeys(errors))))
    values[values < -500] = np.nan  # as the layers clean their tiles (sources.layer.VALID_MIN)
    return values


def _read_zip(layer: src.ZippedTiles, url: str, profile: Dict) -> np.ndarray:
    """The members of a ZippedTiles layer's ZIP that make its tiles, each read by GDAL (its GeoTIFF or XYZ
    driver, not the layer's own parser) on the pixels of a cached tile, in the layer's CRS as the
    layer forces it; NaN where no member has data. The ZIP is downloaded whole (GDAL's /vsizip/ cannot
    list members whose names carry a year without reading the ZIP's directory, nor merge them)."""
    response = src.net._get(url, binary_types=("zip", "octet"))
    if response is None:
        raise RuntimeError(f"{cache.clean_url(url)}: not found")
    values = np.full((profile["height"], profile["width"]), np.nan, dtype=np.float32)
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        for info in archive.infolist():
            name = info.filename.rsplit("/", 1)[-1]
            if info.is_dir() or not re.search(layer.members, name, re.I):
                continue
            ext = os.path.splitext(name)[1].lower()
            with rio.io.MemoryFile(archive.read(info), ext=ext) as memfile, memfile.open() as source:
                with WarpedVRT(source, src_crs=profile["crs"], crs=profile["crs"], transform=profile["transform"],
                               width=profile["width"], height=profile["height"],
                               nodata=-9999.0, resampling=Resampling.nearest) as vrt:  # NaN beyond the member
                    part = vrt.read(1, masked=True).astype(np.float32).filled(np.nan)
            values = np.where(np.isnan(values), part, values)
    values[values < -500] = np.nan  # as the layers clean their tiles (sources.layer.VALID_MIN)
    return values


def _read_lem(url: str, profile: Dict, cache_dir: Optional[str] = None) -> np.ndarray:
    """A sheet ZIP of fixed-width ".lem" heights (Kanagawa's MESH grids), downloaded (net._get, the host's rate turn,
    under a slot of the host in the data folder) and read by _lem_values."""
    slot = src.net.host_slot(cache_dir, url) if cache_dir else contextlib.nullcontext()
    with slot:
        response = src.net._get(url, binary_types=("zip", "octet"))
    if response is None:
        raise RuntimeError(f"{cache.clean_url(url)}: not found")
    return _lem_values(response.content, profile)


def _lem_values(data: bytes, profile: Dict) -> np.ndarray:
    """A ".lem" sheet ZIP by the check's own rules, not the layer's parser (sources.readers.sheetfile._lem_grid) nor
    its sheet code: the place from the ZIP's cp932 CSV header (the corners in cm, X northward, Y eastward; the counts
    and the spacing), each line split into 5-character integers after its 10-character record number, -9999 and
    -1111 as no data, 0.1 m; placed on the cached tile's pixels. RuntimeError (check_files' WARN line) for a ZIP
    without its .lem or .csv member, a header without a key it needs, a byte that is not text or a line that is
    not the header's count of integers."""
    from rasterio.transform import Affine
    from rasterio.warp import reproject
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = archive.namelist()
            lem = next((n for n in names if n.lower().endswith(".lem")), None)
            csv = next((n for n in names if n.lower().endswith(".csv")), None)
            if lem is None or csv is None:
                raise RuntimeError(f"no .lem and .csv members in {names[:5]}")
            header = dict(line.split(",", 1) for line in archive.read(csv).decode("cp932").splitlines() if "," in line)
            lines = archive.read(lem).decode("ascii").splitlines()
        columns, rows = int(header["東西方向の点数"]), int(header["南北方向の点数"])
        step = float(header["東西方向のデータ間隔"])
        left, top = int(header["区画左下Y座標"]) / 100, int(header["区画右上X座標"]) / 100
        if len(lines) < rows or any(len(line) < 10 + 5 * columns for line in lines[:rows]):
            raise RuntimeError(f"{len(lines)} lines, {rows} of {10 + 5 * columns} characters expected")
        codes = np.array([[int(line[10 + 5 * k:15 + 5 * k]) for k in range(columns)] for line in lines[:rows]],
                         dtype=np.float64)
    except KeyError as e:
        raise RuntimeError(f"the header has no {e}") from None
    except ValueError as e:  # UnicodeDecodeError too
        raise RuntimeError(f"not a .lem sheet ({e})") from None
    heights = np.where((codes == -9999) | (codes == -1111), np.nan, codes / 10).astype(np.float32)
    values = np.full((profile["height"], profile["width"]), np.nan, dtype=np.float32)
    reproject(heights, values, src_transform=Affine(step, 0, left, 0, -step, top), src_crs=profile["crs"],
              dst_transform=profile["transform"], dst_crs=profile["crs"], src_nodata=np.nan, dst_nodata=np.nan,
              resampling=Resampling.nearest)
    return values


# A first line of five comma-separated numbers: "id,x,y,z,flag" rows (Miyagi's 1 m sheets, VIRTUAL SHIZUOKA's CSV)
BOM = b"\xef\xbb\xbf"  # a UTF-8 byte order mark a text may start with
_CSV_ROW =re.compile(rb"\s*-?\d+(\s*,\s*[-+.\deE]+){4}\s*$")


def _read_text_sheet(url: str, profile: Dict, cache_dir: Optional[str] = None) -> np.ndarray:
    """A sheet ZIP of text, downloaded once (net._get, which takes the host's rate turn, under a slot of the host
    in the data folder, as the layer's own download): "id,x,y,z,flag" rows by _csv_values (GDAL's XYZ driver would
    take id, x, y as the columns), "x y z" lines by GDAL's XYZ driver on the cached tile's pixels."""
    slot = src.net.host_slot(cache_dir, url) if cache_dir else contextlib.nullcontext()
    with slot:
        response = src.net._get(url, binary_types=("zip", "octet"))
    if response is None:
        raise RuntimeError(f"{cache.clean_url(url)}: not found")
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        names = [n for n in archive.namelist() if n.lower().endswith(".txt")]
        if not names:
            raise RuntimeError(f"no .txt member in {archive.namelist()[:5]}")
        data = archive.read(names[0])
    first = data.lstrip(BOM).split(b"\n", 1)[0]
    if _CSV_ROW.match(first):
        return _csv_values(data, profile)
    with rio.io.MemoryFile(data.lstrip(BOM), ext=".xyz") as memfile, memfile.open() as source:
        with WarpedVRT(source, src_crs=profile["crs"], crs=profile["crs"], transform=profile["transform"],
                       width=profile["width"], height=profile["height"], nodata=-9999.0,
                       resampling=Resampling.nearest) as vrt:
            values = vrt.read(1, masked=True).astype(np.float32).filled(np.nan)
    values[values < -500] = np.nan  # as the layers clean their tiles (sources.layer.VALID_MIN)
    return values


def _csv_values(data: bytes, profile: Dict) -> np.ndarray:
    """The "id,x,y,z,flag" rows of a text sheet by the check's own rule: every row's z (whatever its flag) in the
    pixel of the cached tile holding its x, y; NaN where no row lies. RuntimeError for rows that are not five
    numbers."""
    try:
        rows = np.loadtxt(io.BytesIO(data.lstrip(BOM)), delimiter=",", ndmin=2)
    except ValueError as e:
        raise RuntimeError(f"not id,x,y,z,flag rows ({e})") from None
    if rows.shape[1] != 5:
        raise RuntimeError(f"rows of {rows.shape[1]} columns, 5 expected")
    t = profile["transform"]
    values = np.full((profile["height"], profile["width"]), np.nan, dtype=np.float32)
    cols = np.floor((rows[:, 1] - t.c) / t.a).astype(np.int64)
    lines = np.floor((rows[:, 2] - t.f) / t.e).astype(np.int64)
    inside = (cols >= 0) & (cols < profile["width"]) & (lines >= 0) & (lines < profile["height"])
    values[lines[inside], cols[inside]] = rows[inside, 3]
    values[values < -500] = np.nan  # as the layers clean their tiles (sources.layer.VALID_MIN)
    return values


def _read_xyz(url: str, profile: Dict) -> np.ndarray:
    """A plain XYZ file of a GeoJsonTiles layer read by GDAL's XYZ driver (not the layer's own parser) on the
    pixels of a cached tile; its server needs net.verify (an incomplete TLS chain), so it is downloaded by
    src.net._get, not read by /vsicurl/."""
    response = src.net._get(url, binary_types=("text/plain",))
    if response is None:
        raise RuntimeError(f"{cache.clean_url(url)}: not found")
    with rio.io.MemoryFile(response.content, ext=".xyz") as memfile, memfile.open() as source:
        with WarpedVRT(source, src_crs=profile["crs"], crs=profile["crs"], transform=profile["transform"],
                       width=profile["width"], height=profile["height"], nodata=-9999.0,
                       resampling=Resampling.nearest) as vrt:
            values = vrt.read(1, masked=True).astype(np.float32).filled(np.nan)
    values[values < -500] = np.nan  # as the layers clean their tiles (sources.layer.VALID_MIN)
    return values


ZONE_PREFIXED = 10_000_000  # an easting above this carries a UTM zone's two digits in front (Bremerhaven's 32466000.5)


def _zone_free(transform):
    """A member's transform with a two-digit UTM zone taken off its easting (32466000 is 466000 of zone 32), the
    zone read from the value itself: check_source's own rule, not the layer's fix, so the file check finds a fix
    that puts a tile elsewhere; any other transform as it is."""
    from rasterio.transform import Affine
    if transform.c < ZONE_PREFIXED:
        return transform
    zone = int(transform.c // 1_000_000)
    return Affine(transform.a, transform.b, transform.c - zone * 1_000_000, transform.d, transform.e, transform.f)


def _read_member(layer: src.ZipMemberTiles, tile, profile: Dict) -> np.ndarray:
    """A tile's member of a remote ZIP read again by the layer's Range reader (its inflating and CRC-32
    check), then opened by GDAL on the pixels of the cached tile (nearest: an origin off by float noise, Hamburg's
    552999.9999999999, lands on the same pixels), with the layer's floor rule applied as the layer applies it (its
    0 m patches would differ otherwise). The member's own georeferencing, not the layer's fix: a member without a CRS
    (XYZ text) in the tile's, an easting with the zone in front without it (_zone_free), moved only by a shift the
    fix declares as deliberate (TransformFix.shift: Bremerhaven's DOM1 half a pixel onto its terrain's grid; taken on
    trust, so a wrong shift passes; its offset and rounding are not taken, so a wrong one is found); an XYZ member in
    columns with points missing (GDAL refuses it) read in rows (zipmember.xyz_rows: only the lines' order). A tile that
    names its own CRS (PackageTiles: its zone's) takes the member's pixels in it, as the layer writes them (the
    files name it otherwise: NAD83 for NAD83(CSRS), a compound CRS). GDAL's /vsizip/ is not used: its requests
    would read the archive's directory outside sources.net."""
    data, _ = layer.reader._member(tile, f"{layer.description} tile {tile.godlo}")
    own = getattr(tile, "crs", None)
    shift = _declared_shift(layer)
    try:
        values = _member_values(data, profile, own, shift)
    except rio.errors.RasterioError:
        rows = xyz_rows(data)
        if rows is None:
            raise
        values = _member_values(rows, profile, own, shift)
    values[values < -500] = np.nan  # as the layers clean their tiles (sources.layer.VALID_MIN)
    return drop_below(values, getattr(layer, "floor", None), getattr(layer, "ring", 0))


def _member_values(data: bytes, profile: Dict, own: Optional[str] = None,
                   shift: Tuple[float, float] = (0.0, 0.0)) -> np.ndarray:
    """The member's pixels on the cached tile's; own: the tile's CRS taken for the member's (its transform as it
    is), else the member's own georeferencing (_read_member), moved by shift (the fix's declared deliberate one)."""
    from rasterio.transform import Affine
    with rio.io.MemoryFile(data) as memfile, memfile.open() as source:
        if own:
            moved = {"src_crs": own}
        elif source.crs is not None and source.transform.c < ZONE_PREFIXED and shift == (0.0, 0.0):
            moved = {}
        else:
            moved = {"src_crs": source.crs or profile["crs"],
                     "src_transform": Affine.translation(*shift) @ _zone_free(source.transform)}
        with WarpedVRT(source, crs=profile["crs"], transform=profile["transform"], width=profile["width"],
                       height=profile["height"], resampling=Resampling.nearest, **moved) as vrt:
            return vrt.read(1, masked=True).astype(np.float32).filled(np.nan)


def _read_grid(layer: src.InegiSheets, url: str, tile, profile: Dict) -> np.ndarray:
    """An INEGI sheet's ZIP (downloaded whole by src.net._get: GDAL's /vsizip/ over /vsicurl/ would read it by ranges
    outside sources.net, and the names carry backslashes) whose ArcInfo GRID is unpacked here by zipfile and read by
    GDAL on the pixels of a cached tile, in the sheet's CRS (the GRID names none); the pixels outside the sheet's
    cell grown by the reader's margin are left out, as the layer leaves them out (its cut, done again here from the
    cell's edges)."""
    import shutil
    import tempfile
    from rasterio.features import geometry_mask
    from shapely.geometry import box
    response = src.net._get(url, binary_types=("zip", "octet"))
    if response is None:
        raise RuntimeError(f"{cache.clean_url(url)}: not found")
    folder = tempfile.mkdtemp(prefix="inegi-")
    try:
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            names = {i.filename.replace("\\", "/"): i for i in archive.infolist() if not i.is_dir()}
            grid = next(n for n in names if n.lower().endswith("/hdr.adf"))[:-len("hdr.adf")]
            for name, info in names.items():
                if name.startswith(grid) and "/" not in name[len(grid):]:
                    with open(os.path.join(folder, name[len(grid):]), "wb") as out:
                        out.write(archive.read(info))
        with rio.open(folder) as source:
            with WarpedVRT(source, src_crs=tile.crs, crs=profile["crs"], transform=profile["transform"],
                           width=profile["width"], height=profile["height"], resampling=Resampling.nearest) as vrt:
                values = vrt.read(1, masked=True).astype(np.float32).filled(np.nan)
    finally:
        shutil.rmtree(folder, ignore_errors=True)
    west, south, east, north = layer.index.edges(tile)
    cell = ar.project(box(west, south, east, north).segmentize(0.002), "EPSG:4326", tile.crs)
    values[geometry_mask([cell.buffer(layer.reader.margin_m)], values.shape, profile["transform"])] = np.nan
    values[values < -500] = np.nan  # as the layers clean their tiles (sources.layer.VALID_MIN)
    return values


def _sheet_files(layer: src.Layer, tile) -> List[Tuple[str, int]]:
    """(url, year) of every file a sheet of a sheet-set layer is composed from (S3SheetSets, CellSheetTiles), newest
    year first; [] for any other layer."""
    if isinstance(layer, S3SheetSets):
        files = tile.files
    elif isinstance(layer, CellSheetTiles):
        request = layer.index.request(tile)
        files = request.files if request is not None else ()
    else:
        return []
    return [(f[1], f[2]) for f in files]


def _composed(read, files: List[Tuple[str, int]]) -> np.ndarray:
    """A sheet composed from its files as SheetSetFile does: newest year first, an older year read only while the
    sheet has holes, within one year the fuller file first; read(url) is a file's raster on the tile's pixels."""
    band = None
    for year in sorted({y for _, y in files}, reverse=True):
        if band is not None and not np.isnan(band).any():
            break
        rasters = sorted((read(url) for url, y in files if y == year), key=lambda r: -np.count_nonzero(~np.isnan(r)))
        for raster in rasters:
            band = raster.copy() if band is None else np.where(np.isnan(band), raster, band)
    return band


def _read_file(layer, url: str, profile: Dict, cache_dir: str) -> np.ndarray:
    """One file of a sheet-set layer's sheet by the check's rules of its kind (as check_files' own dispatch)."""
    if getattr(layer, "members", None) == r"\.lem$":
        return _read_lem(url, profile, cache_dir)
    if getattr(layer, "members", None) == r"\.txt$" and url.lower().endswith(".zip"):
        return _read_text_sheet(url, profile, cache_dir)
    return _read_source(url, profile, Resampling.nearest, cache_dir)


def _sources_of(layer: src.Layer, tile) -> Optional[List[str]]:
    """The files a cached tile comes from, newest first; None: no file to compare with."""
    if isinstance(layer, (src.WcsTiles, src.GeoWcsTiles, src.LercTiles, src.ZipSheetTiles, WmsrTiles,
                          src.ImageServerTiles, src.FileLayer, src.OpenTopographyTiles)):
        return None  # a service's answer, a local file, or the API's limited calls
    if isinstance(layer, (src.TnmBlocks, src.S3Blocks)):
        return [url for _, url, _ in tile.files]
    if isinstance(layer, src.GridTiles):
        base = layer.tile_url(tile)
        return [f"{base}/{src.grid_tile_name(*tile[1:])}"] if base else None  # a tile (res, i, j)
    url = layer.tile_url(tile)
    if isinstance(layer, src.CartotecaTiles) and url:  # its ZIP holds the grid and the owner's licence (a PDF)
        return [f"{url}/{layer.index.request(tile).name}.asc"]
    return [url] if url else None


# --- the checks ---

def check_shift(layer, reference, args, data, work, cache_dir) -> Check:
    plan = _plan(args, data, work, args.radius + args.shift_range, args.resolution)
    grid, res = plan.grid, plan.resolution
    margin = math.ceil(args.shift_range / res - 1e-9)
    step = max(1, round((args.shift_step or res) / res))
    raw = _mosaic(layer, grid, cache_dir, work, "layer")
    ref = _mosaic(reference, grid, cache_dir, work, "reference")
    mask = ar.Circle(args.lat, args.lon, args.radius).mask(grid)
    mask = mask[margin:grid.height - margin, margin:grid.width - margin]
    table = shift_table(raw, ref, margin, step, mask)
    if (0, 0) not in table:
        return Check("shift", FAIL, f"no pixels with data in both the layer and {reference.description}")
    i, j = best_shift(table)
    best, zero = table[(i, j)], table[(0, 0)]
    shift = (i * res, j * res)
    total = (layer.shift[0] + shift[0], layer.shift[1] + shift[1])
    status = WARN if math.hypot(*shift) > SHIFT_WARN_M else PASS
    text = (f"best ({shift[0]:g}, {shift[1]:g}) m against {reference.description}: median |d| {best[0]:.2f} m, "
            f"median d {best[1]:+.2f} m; at (0, 0): {zero[0]:.2f} m, {zero[1]:+.2f} m")
    if shift != (0, 0):
        text += f"; correction: shift=({total[0]:g}, {total[1]:g})"
    return Check("shift", status, text, best_m=list(shift), shift=list(total), reference=reference.description,
                 median_abs_m=best[0], median_m=best[1], zero_median_abs_m=zero[0], zero_median_m=zero[1],
                 pixels=best[2], grid_m=res, range_m=margin * res)


def check_valid(layer, args, data, work, cache_dir) -> Check:
    radius = min(args.radius, VALID_RADIUS_MAX)
    shares, notes = {}, []
    for res in (1.0, 5.0):
        try:
            plan = _plan(args, data, work, radius, res)
        except search.SearchError as e:  # a WCS that serves no finer grid than its own
            notes.append(f"{res:g} m: {e}")
            continue
        values = _mosaic(layer, plan.grid, cache_dir, work, f"valid-{res:g}")
        shares[res] = valid_share(values, plan.area.mask(plan.grid))
    if not shares:
        return Check("valid", NA, "; ".join(notes))
    text = ", ".join(f"{100 * share:.2f}% at {res:g} m" for res, share in shares.items()) + f" (radius {radius:g} m)"
    status = PASS
    if not any(shares.values()):
        status = FAIL
    elif 1.0 in shares and 5.0 in shares and 100 * (shares[1.0] - shares[5.0]) > VALID_DROP_PP:
        status = WARN
        text += ": less data at 5 m"
    if notes:
        text += "; " + "; ".join(notes)
    return Check("valid", status, text, **{f"valid_{res:g}m": share for res, share in shares.items()})


def _declared_shift(layer) -> Tuple[float, float]:
    """The deliberate shift a layer's fix declares (TransformFix.shift: Bremerhaven's DOM1), (0, 0) without one."""
    return tuple(float(v) for v in getattr(getattr(getattr(layer, "reader", None), "fix", None), "shift", (0.0, 0.0)))


def check_files(layer, grid, cache_dir, samples: int) -> Check:
    """A few cached tiles against their source files read again by the check's own rules (the values, the place the
    files give them, a zone in front of an easting): it proves the values and the offset, never a shift the layer's
    fix declares, which it takes from that fix and names in its line (a wrong declared shift passes)."""
    if isinstance(layer, src.FileLayer):  # not in the cache (it may lie on another drive): nothing to compare
        return Check("files", NA, "a local file")
    tiles = _cached_tiles(layer, grid, cache_dir)
    if not tiles or _sources_of(layer, tiles[0]) is None:
        why = "no cached tiles" if not tiles else f"{type(layer).__name__}: no source file to compare with"
        return Check("files", NA, why)
    results, problems = [], []
    for tile in _spread(tiles, samples):
        path = layer.tile_path(cache_dir, tile)
        with rio.open(path) as cached:
            values = cached.read(1, masked=True).astype(np.float32).filled(np.nan)
            profile = {"crs": cached.crs, "transform": cached.transform, "width": cached.width,
                       "height": cached.height}
        name = cache.relative(cache_dir, path)
        blocks = isinstance(layer, (src.TnmBlocks, src.S3Blocks))
        result = None
        sheets = _sheet_files(layer, tile)
        if len(sheets) > 1:  # a sheet of several files: composed again from the check's own reads of each
            try:
                source = _composed(lambda url: _read_file(layer, url, profile, cache_dir), sheets)
                results.append({"tile": name, "file": " + ".join(cache.clean_url(u) for u, _ in sheets),
                                **compare(values, source)})
            except (rio.errors.RasterioError, RuntimeError, zipfile.BadZipFile) as e:
                problems.append(f"{name}: {cache.clean_error(e)}")
            continue
        for url in _sources_of(layer, tile):
            try:
                resampling = Resampling.average if getattr(layer, "average", 1) > 1 else Resampling.nearest
                # A layer that warps its files onto its blocks (Cyprus: nearest for the DTM, average for the DSM)
                resampling = getattr(getattr(layer, "reader", None), "warp", None) or resampling
                # USGS's OPR DEMs (Windows(opr=)): each file by the method its own header takes, its heights times
                # its survey's factor (without them the check compared a 0.5 m file's nearest pixel with the block's
                # average, and heights in feet with metres: 15 m and 2,044 m on 2026-11-27)
                rule = getattr(getattr(layer, "reader", None), "opr", None)
                rule = rule(url) if rule else None
                warp = None
                if rule is not None:
                    with src.net._gdal_http(), src.net.open_gdal(_gdal_path(url)) as head:
                        method, _ = windows.opr_method(head, profile["crs"], profile["transform"])
                        if method == "cubic":  # the kernel's scale as the reader fixes it
                            warp = windows.opr_scale(head.transform, head.crs, profile["transform"])
                    if method is None:
                        continue
                    resampling = {"copy": Resampling.nearest, "average": Resampling.average,
                                  "cubic": Resampling.cubic}[method]
                # A ZippedTiles layer without members reads plain files (Trento's ASCII grids)
                if isinstance(layer, src.ZippedTiles) and layer.members is not None:
                    source = _read_zip(layer, url, profile)
                elif isinstance(layer, src.GeoJsonTiles):
                    source = _read_xyz(url, profile)
                elif isinstance(layer, (src.ZipMemberTiles, src.PackageTiles)):
                    source = _read_member(layer, tile, profile)
                elif isinstance(layer, src.InegiSheets):
                    source = _read_grid(layer, url, tile, profile)
                elif getattr(layer, "members", None) == r"\.lem$":
                    source = _read_lem(url, profile, cache_dir)
                elif getattr(layer, "members", None) == r"\.txt$" and url.lower().endswith(".zip"):
                    source = _read_text_sheet(url, profile, cache_dir)
                elif getattr(getattr(layer, "reader", None), "ranged", False) and url.startswith("http"):
                    source = _read_ranged(url, profile, resampling, cache_dir)
                else:
                    source = _read_source(url, profile, resampling, cache_dir, warp)
                if rule is not None:
                    source = source * np.float32(rule[0])
                geoid = getattr(layer, "geoid", None)
                if geoid is not None:  # heights above the ellipsoid: the layer caches them above its geoid
                    source -= geoid.undulation(profile["crs"], profile["transform"],
                                               (profile["height"], profile["width"]), grid=geoid.ensure(cache_dir))
            except (rio.errors.RasterioError, RuntimeError, zipfile.BadZipFile) as e:
                problems.append(f"{name}: {cache.clean_error(e)}")
                break
            if blocks and not np.isfinite(source).any():
                continue  # the newest file with data there
            result = {"tile": name, "file": cache.clean_url(url), **compare(values, source, source_only=blocks)}
            break
        if result:
            results.append(result)
    if not results:
        return Check("files", WARN, "could not read the source files: " + "; ".join(problems), problems=problems)
    worst = max((r["max_abs_m"] or 0.0) for r in results)
    same = min((r["same_nodata"] if r["same_nodata"] is not None else 1.0) for r in results)
    equal = min((r["equal"] if r["equal"] is not None else 1.0) for r in results)
    status = PASS if worst <= EQUAL_M and same >= 0.999 and not problems else WARN
    text = (f"{len(results)} tiles against their files: max |d| {worst:.4f} m, equal {100 * equal:.2f}%, "
            f"same pixels without data {100 * same:.2f}%")
    shift = _declared_shift(layer)
    if shift != (0.0, 0.0):  # taken from the layer's own fix: the check cannot tell a wrong shift
        text += f" (the layer's declared shift of ({shift[0]:g}, {shift[1]:g}) m allowed for)"
    if problems:
        text += "; " + "; ".join(problems)
    return Check("files", status, text, tiles=results, problems=problems)


def _layer_rasters(layer, grid, cache_dir) -> List[str]:
    if isinstance(layer, src.FileLayer):
        return layer.files(grid, cache_dir)
    return [layer.tile_path(cache_dir, t) for t in _spread(_cached_tiles(layer, grid, cache_dir), ALIGN_TILES)]


def check_alignment(layer, source, plan, cache_dir) -> Check:
    paths = _layer_rasters(layer, plan.grid, cache_dir)
    if not paths:
        return Check("alignment", NA, "no cached tiles")
    working = rio.crs.CRS.from_user_input(plan.crs)
    worst, sizes, crss, other = 0.0, set(), set(), False
    for path in paths:
        with rio.open(path) as raster:
            res = abs(raster.res[0])
            sizes.add(round(res, 6))
            crss.add(raster.crs.to_string() if raster.crs else "none")
            if raster.crs is not None and raster.crs == working:
                worst = max(worst, origin_offset(raster.transform, res, source.grid_origin))
            else:
                other = True
    size_text = ", ".join(f"{s:g}" for s in sorted(sizes))
    text = (f"{len(paths)} rasters in {', '.join(sorted(crss))} (working grid {plan.crs}), pixels {size_text} "
            f"(native_res {layer.native_res:g}), edges {worst:.3f} m from grid_origin "
            f"({source.grid_origin[0]:g}, {source.grid_origin[1]:g})")
    if other:
        text += "; some in another CRS: reprojected onto the grid"
    status = WARN if worst > min(sizes) / 100 else PASS
    return Check("alignment", status, text, crs=sorted(crss), pixel_sizes=sorted(sizes), edge_offset_m=worst,
                 grid_origin=list(source.grid_origin), native_res=layer.native_res)


def check_precision(layer, grid, cache_dir) -> Check:
    paths = _layer_rasters(layer, grid, cache_dir)
    if not paths:
        return Check("precision", NA, "no cached tiles")
    values = []
    for path in paths[:5]:
        with rio.open(path) as raster:
            band = raster.read(1, masked=True).astype(np.float32).filled(np.nan)
        values.append(band[np.isfinite(band)][:2_000_000])
    metres, cm = precision(np.concatenate(values))
    status = WARN if metres > WHOLE_METRES_WARN else PASS
    text = f"whole metres {100 * metres:.1f}%, whole centimetres {100 * cm:.1f}%"
    if status == WARN:
        text += ": heights in whole metres make slopes and clearances coarser"
    return Check("precision", status, text, whole_metres=metres, whole_cm=cm)


def check_missing(layer, grid, cache_dir) -> Check:
    if isinstance(layer, src.FileLayer):
        return Check("missing", NA, "a local file")
    tiles = layer.tiles(grid)
    if tiles is None:
        return Check("missing", NA, "the index could not be reached")
    empty = [cache.relative(cache_dir, layer.tile_path(cache_dir, t)) for t in tiles
             if cache.state(cache_dir, layer.tile_path(cache_dir, t), layer.processing) == "missing"]
    text = f"{len(empty)} of {len(tiles)} tiles without data"
    if empty:
        text += " (normal over the sea; on land a lost tile): " + ", ".join(empty[:5])
    return Check("missing", WARN if empty else PASS, text, tiles=len(tiles), missing=empty)


def check_layer(kind: str, args, data: str, work: str) -> Dict:
    cache_dir = os.path.join(data, "cache")
    plan = _plan(args, data, work, args.radius + args.shift_range, args.resolution)
    source = plan.source
    layer = getattr(source, kind)
    checks = []

    def run(name, fn, *a):
        try:
            checks.append(fn(*a))
        except (RuntimeError, ValueError, OSError, search.SearchError) as e:
            checks.append(Check(name, FAIL, cache.clean_error(e)))

    run("shift", check_shift, layer, _reference(args, kind), args, data, work, cache_dir)
    run("valid", check_valid, layer, args, data, work, cache_dir)
    run("files", check_files, layer, plan.grid, cache_dir, args.samples)
    run("alignment", check_alignment, layer, source, plan, cache_dir)
    run("precision", check_precision, layer, plan.grid, cache_dir)
    run("missing", check_missing, layer, plan.grid, cache_dir)
    return {"layer": kind, "description": layer.description, "checks": checks}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().split("\n\n")[0])
    parser.add_argument("source", help="the source's id (sources/catalogue/), or files with --elevation-file")
    parser.add_argument("--lat", type=float, required=True)
    parser.add_argument("--lon", type=float, required=True)
    parser.add_argument("--radius", type=float, default=1500, help="metres (default 1500)")
    parser.add_argument("--resolution", type=float, default=10, help="grid of the shift search, m (default 10)")
    parser.add_argument("--layers", default="nmt,nmpt", help="nmt, nmpt or both (default: the source's)")
    parser.add_argument("--reference", default="auto",
                        help="auto (terrain: fabdem, surface: copernicus), fabdem, copernicus or a raster file")
    parser.add_argument("--shift-range", type=float, default=200, help="largest shift tried, m (default 200)")
    parser.add_argument("--shift-step", type=float, help="step of the shifts, m (default: the resolution)")
    parser.add_argument("--samples", type=int, default=3, help="cached tiles compared with their files")
    parser.add_argument("--data-dir", help="data folder whose cache is used (a scratch folder for a new source)")
    parser.add_argument("--elevation-file", help="with SOURCE files: the terrain raster")
    parser.add_argument("--surface-file", help="with SOURCE files: the surface raster")
    parser.add_argument("--json", help="write the results to this file")
    args = parser.parse_args(argv)
    data = cache.data_dir(args.data_dir)
    work = cache.new_work(data)
    results = []
    try:
        with progress.bars():
            plan = _plan(args, data, work, args.radius + args.shift_range, args.resolution)
            source = plan.source
            kinds = [k for k in args.layers.split(",") if getattr(source, k.strip(), None) is not None]
            for kind in kinds:
                results.append(check_layer(kind.strip(), args, data, work))
    finally:
        gc.collect()
        cache.remove_work(work)

    print(f"\n{source.id}: {source.name} at {args.lat:g}, {args.lon:g}; radius {args.radius:g} m, "
          f"{plan.resolution:g} m grid in {plan.crs}")
    counts = {PASS: 0, WARN: 0, FAIL: 0, NA: 0}
    for result in results:
        print(f"{LAYER_NAMES.get(result['layer'], result['layer']).capitalize()}: {result['description']}")
        for check in result["checks"]:
            counts[check["status"]] += 1
            print(f"  {check['status']:<4}  {check['name']:<9}  {check['text']}")
    print(", ".join(f"{n} {status}" for status, n in counts.items()))
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump({"source": source.id, "lat": args.lat, "lon": args.lon, "radius": args.radius,
                       "resolution": plan.resolution, "crs": plan.crs, "layers": results}, f, indent=1)
    return 1 if counts[FAIL] else 0


if __name__ == "__main__":
    from progress import utf8_output
    utf8_output()  # redirected output in UTF-8, not the Windows code page (no "²" there)
    sys.exit(main())
