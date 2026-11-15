"""SheetFile: a map sheet downloaded as a file (ASCII grid, XYZ or GeoTIFF, zipped once or twice, or several
members of one ZIP) and saved as a GeoTIFF."""

import io
import re
import warnings
import zipfile
from typing import List, Optional, Tuple

import numpy as np
from affine import Affine
from rasterio.errors import RasterioIOError
from rasterio.io import MemoryFile
from rasterio.transform import from_origin
from rasterio.warp import Resampling, reproject

from .. import net
from ..layer import Fetched, _clean, _write_tile
from ..composed import Reader

# The members _member_grid reads as rasters (GeoTIFF and ASCII grid by GDAL, XYZ text): a ZIP with members that
# holds none of them is no data, not an error (LGL's DOM1 ZIPs of three 1 km tiles on Baden-Württemberg's border,
# 379 KB each, dated 2026-07-03: two CSV lines of tile metadata, the licence PDF and a Meta-...txt, no raster;
# measured 2026-11-08). A .txt is metadata here, never an XYZ grid without a matching name.
RASTER_MEMBERS = (".tif", ".tiff", ".asc", ".xyz")
# The UTF-8 byte order mark some XYZ files start with (GUGiK's NMT sheets of survey 70159, 2018, in PL-2000 zone 6:
# np.loadtxt read it as part of the first number and failed; 2026-11-14)
BOM = b"\xef\xbb\xbf"
# Lines of an XYZ text that are not "x y z" are left out when at most this share of its lines (one broken line of a
# 400 000-line GUGiK sheet had 4 fields, 2026-11-13): more is not an XYZ grid, an error
MALFORMED_SHARE = 0.001
# The spacing of an XYZ grid (_step) is a step between points one after another that at least this share of them
# share: the smallest step alone made one pair of near-duplicate points (millimetres apart) a grid of millimetres,
# (res / step)² times the pixels (review of 2026-11-14; a guard, not a measured value)
STEP_SUPPORT = 0.01
# A step within this share of a multiple of the listed resolution, or of a fraction 1/k of it, is that exactly: steps
# between coordinates written to the millimetre differ by up to 2 mm (0.4 % at 0.5 m)
STEP_SNAP = 0.01
# Moves between points under the listed resolution / MAX_FINER are not a grid's step but the other coordinate's
# jitter along a row (millimetres), so a group's raster is never more than MAX_FINER² times the pixels at the listed
# resolution (no publisher's sheet was seen finer than listed; a grid finer than this splits by lattice offset first)
MAX_FINER = 4
# A line of three numbers (blank lines are skipped by np.loadtxt): any other line with something on it is malformed
_NOT_XYZ = re.compile(rb"^(?![ \t]*[-+.\deE]+[ \t]+[-+.\deE]+[ \t]+[-+.\deE]+[ \t]*\r?$)[^\n]*\S[^\n]*$", re.M)
# A first line of five comma-separated numbers: "n,x,y,z,flag" (_csv_points). Such a file failed as "x y z" lines
# before, so the branch changes no file read before
_CSV_NXYZF = re.compile(rb"[ \t]*-?\d+(?:[ \t]*,[ \t]*[-+.\deE]+){4}[ \t]*\r?(?:\n|$)")


class SheetFile(Reader):
    """A Sheet's file (geoportal.gov.pl): an ARC/INFO ASCII grid or "x y z" lines of a regular
    grid, sometimes zipped (twice), saved as a float32 GeoTIFF in the sheet's CRS.

    With members (a regex of the members' names, matched case-insensitively), the file is one
    ZIP whose matching members (ASCII grids, XYZ or GeoTIFF) are the parts of the tile, all on
    the same pixels: they are merged into one raster over their union (GeoSN's 2 km ZIPs of one
    GeoTIFF, LGL's of four 1 km XYZ grids or GeoTIFFs), in the request's CRS whatever the
    members name (a compound CRS with heights, or none). A ZIP without a matching member is an
    error when it holds a raster of another name (RASTER_MEMBERS), no data when it holds none (a
    publisher's ZIP of metadata only). A ZIP is read whole (the servers give no index of its
    members): at most max_bytes downloaded, at most member_bytes unpacked per member, so a broken
    or hostile ZIP cannot fill the memory. Requests need url, godlo (the name in messages), crs and
    res."""
    rewrites = True  # the cached tile is written by _write_tile: reencode / cache migrate may convert it

    def __init__(self, description: str, members: Optional[str] = None, max_bytes: int = 200_000_000,
                 member_bytes: int = 100_000_000, listed: bool = False):
        self.description, self.members = description, members
        self.max_bytes, self.member_bytes = max_bytes, member_bytes
        # listed: every request is a file the publisher lists (a static table, a bucket's listing), so a 404 is an
        # error of that tile (asked again by the next search), never a tile without data recorded as missing
        self.listed = listed

    def url(self, tile) -> Optional[str]:
        return tile.url

    def download(self, tile):
        """The answer of a sheet's URL; None for a 404 (no such sheet), an error for a 404 when the files are
        listed (listed) and for any other failure."""
        try:
            if self.listed:  # a 403 for a listed file is that file's error, not asked again
                response = net._get(tile.url, binary_types=("octet", "zip", "text", "image"), final=(403,))
            else:
                response = net._get(tile.url, binary_types=("octet", "zip", "text", "image"))
        except RuntimeError as e:
            raise RuntimeError(f"Could not download {self.description} sheet {tile.godlo}: {e}")
        if response is None and self.listed:
            raise RuntimeError(f"Could not download {self.description} sheet {tile.godlo}: HTTP 404 for a "
                               f"listed file")
        return response

    def fetch(self, tile, path: str) -> Fetched:
        response = self.download(tile)
        if response is None:
            return Fetched(0, tile.url)
        if self.members is not None:
            parts = self._parts(tile, response.content)
            if parts is None:  # a ZIP without any raster: no data there
                return Fetched(0, tile.url)
            band, transform = parts
            _write_tile(path, _clean(band), tile.crs, transform)
            return Fetched.of(response, tile.url)
        where = f"{self.description} sheet {tile.godlo}"
        name, data, zipped = tile.url.lower(), response.content, False
        try:
            while name.endswith(".zip"):  # sometimes zipped twice
                with zipfile.ZipFile(io.BytesIO(data)) as archive:
                    name = next(n for n in archive.namelist()
                                if n.lower().endswith((".asc", ".xyz", ".txt", ".zip")))
                    data = archive.read(name)
                    name, zipped = name.lower(), True
            if not data.strip(BOM + b" \t\r\n"):
                if not zipped:  # an empty answer, not the publisher's file
                    raise RuntimeError("the answer is empty")
                print(f"{where}: the file in its ZIP is empty; no data")
                return Fetched(0, tile.url)
            grid = _ascii_grid(data, tile.res, tile.crs, where) if name.endswith(".asc") \
                else _xyz_grid(data, tile.res, tile.crs, where)
        except (ValueError, RuntimeError, RasterioIOError, zipfile.BadZipFile, StopIteration) as e:
            raise RuntimeError(f"{where}: {str(e) or type(e).__name__}") from e
        band, transform = grid
        _write_tile(path, _clean(band), tile.crs, transform)
        return Fetched.of(response, tile.url)

    def _parts(self, tile, data: bytes) -> Optional[Tuple[np.ndarray, Affine]]:
        """The members of a ZIP matching self.members, merged into one raster; None (said) when the ZIP
        holds no raster at all (RASTER_MEMBERS), RuntimeError when it holds one of another name."""
        where = f"{self.description} sheet {tile.godlo}"
        if len(data) > self.max_bytes:
            raise RuntimeError(f"{where}: the file has {len(data)} bytes, more than {self.max_bytes}")
        try:
            archive = zipfile.ZipFile(io.BytesIO(data))
        except zipfile.BadZipFile as e:
            raise RuntimeError(f"{where}: not a ZIP file ({e})")
        parts = []
        with archive:
            files = [i for i in archive.infolist() if not i.is_dir()]
            wanted = [i for i in files if re.search(self.members, i.filename.rsplit("/", 1)[-1], re.I)]
            if not wanted:
                names = [i.filename for i in files]
                if not any(n.lower().endswith(RASTER_MEMBERS) for n in names):
                    print(f"{where}: no raster in the file, only {names[:10]}; no data")
                    return None
                raise RuntimeError(f"{where}: no member like {self.members} in {names[:10]}")
            for info in sorted(wanted, key=lambda i: i.filename):
                if info.file_size > self.member_bytes:
                    raise RuntimeError(f"{where}: {info.filename} has {info.file_size} bytes unpacked, "
                                       f"more than {self.member_bytes}")
                with archive.open(info) as member:  # the header's size is not trusted
                    content = member.read(self.member_bytes + 1)
                if len(content) > self.member_bytes:
                    raise RuntimeError(f"{where}: {info.filename} unpacks to more than {self.member_bytes} bytes")
                parts.append(_member_grid(info.filename, content, tile.res, tile.crs, f"{where} {info.filename}"))
        return _merge(parts, tile.res, where)


def _member_grid(name: str, data: bytes, res: float, crs: str, where: str) -> Tuple[np.ndarray, Affine]:
    """The raster of one member: a GeoTIFF as GDAL reads it (its nodata as NaN), an ASCII grid
    (_ascii_grid) or "x y z" lines of cell centres (_xyz_grid)."""
    lower = name.lower()
    if lower.endswith(".asc"):
        return _ascii_grid(data, res, crs, where)
    if lower.endswith((".tif", ".tiff")):
        with MemoryFile(data, ext=".tif") as memfile, memfile.open() as src:
            if src.count != 1:
                raise RuntimeError(f"{name}: {src.count} bands, one expected")
            return src.read(1, masked=True).astype(np.float32).filled(np.nan), src.transform
    return _xyz_grid(data, res, crs, where)


def _ascii_grid(data: bytes, res: float, crs: str, where: str) -> Tuple[np.ndarray, Affine]:
    """An ".asc" file as GDAL reads it (an ARC/INFO ASCII grid, or ARSO's "x;y;z" text by GDAL's XYZ driver; its
    nodata as NaN), a UTF-8 BOM left out (GDAL knows neither format behind one). A file GDAL does not recognise
    is read as "x y z" lines (_xyz_grid), and is an error when it is not that either."""
    if data.startswith(BOM):
        data = data[len(BOM):]
    try:
        with MemoryFile(data, ext=".asc") as memfile, memfile.open() as src:
            return src.read(1, masked=True).astype(np.float32).filled(np.nan), src.transform
    except RasterioIOError as e:
        if "not recognized" not in str(e):
            raise
    print(f"{where}: not a raster GDAL recognises, read as x y z lines")
    return _xyz_grid(data, res, crs, where)


def _merge(parts: List[Tuple[np.ndarray, Affine]], res: float, where: str) -> Tuple[np.ndarray, Affine]:
    """Rasters on the same pixels (pixel size res, north up) in one over their union; where they
    overlap, the first in order wins on its valid pixels. One raster is returned as it is."""
    for band, transform in parts:
        if not (np.isclose(transform.a, res) and np.isclose(transform.e, -res) and transform.b == 0
                and transform.d == 0):
            raise RuntimeError(f"{where}: a member of {transform.a} x {-transform.e} m, {res} m expected")
    if len(parts) == 1:
        return parts[0]
    left = min(t.c for _, t in parts)
    top = max(t.f for _, t in parts)
    offsets = []
    for band, t in parts:
        col, row = (t.c - left) / res, (top - t.f) / res
        if not (np.isclose(col, round(col)) and np.isclose(row, round(row))):
            raise RuntimeError(f"{where}: the members are not on the same pixels")
        offsets.append((round(row), round(col)))
    height = max(r + b.shape[0] for (r, _), (b, _) in zip(offsets, parts))
    width = max(c + b.shape[1] for (_, c), (b, _) in zip(offsets, parts))
    merged = np.full((height, width), np.nan, dtype=np.float32)
    for (row, col), (band, _) in zip(offsets, parts):
        window = merged[row:row + band.shape[0], col:col + band.shape[1]]
        free = np.isnan(window)
        window[free] = band[free]
    return merged, from_origin(left, top, res, res)


def _xyz_grid(data: bytes, res: float, crs: str, where: str = "") -> Tuple[np.ndarray, Affine]:
    """A raster from "x y z" lines of cell centres (_xyz_points), the sheet's CRS crs.

    Usually one regular grid at res, written on its own pixels. Some files hold another spacing or several grids
    (GUGiK's NMT survey 70159 of 2018 in PL-2000 zone 6, sheets listed at 1 m: 5 m grids on whole metres, alone
    or a patchwork with 1 m grids of centres on .5; 2026-11-14). So the points are split into grids by their
    offset from the lattice of res, each at its own spacing (the smallest step between points one after another):
    one grid is written at its spacing (the mosaic resamples it as any coarser raster), several on the finest one
    over their union, the others filling the pixels it has no point for, resampled bilinearly (as the mosaic
    does coarser data). Said in a line when the file is not one grid at res."""
    xyz = _xyz_points(data, where)
    grids = sorted(_lattices(xyz, res), key=lambda g: (g[1], -len(g[0])))  # the finest, then the most points
    rasters = [_grid_of(points, step) for points, step in grids]
    steps = [step for _, step in grids]
    if len(rasters) == 1:
        if steps[0] != res:
            print(f"{where}: points {steps[0]:g} m apart, not the {res:g} m listed; written at {steps[0]:g} m")
        return rasters[0]
    step = steps[0]
    first, at = rasters[0]
    edges = [(t.c, t.f, t.c + b.shape[1] * t.a, t.f + b.shape[0] * t.e) for b, t in rasters]
    left = at.c - np.ceil((at.c - min(e[0] for e in edges)) / step - 1e-9) * step
    top = at.f + np.ceil((max(e[1] for e in edges) - at.f) / step - 1e-9) * step
    width = int(np.ceil((max(e[2] for e in edges) - left) / step - 1e-9))
    height = int(np.ceil((top - min(e[3] for e in edges)) / step - 1e-9))
    transform = from_origin(left, top, step, step)
    band = np.full((height, width), np.nan, dtype=np.float32)
    row, col = round((top - at.f) / step), round((at.c - left) / step)
    band[row:row + first.shape[0], col:col + first.shape[1]] = first
    for other, other_at in rasters[1:]:
        resampled = np.full_like(band, np.nan)
        reproject(other, resampled, src_transform=other_at, src_crs=crs, dst_transform=transform, dst_crs=crs,
                  src_nodata=np.nan, dst_nodata=np.nan, resampling=Resampling.bilinear)
        free = np.isnan(band)
        band[free] = resampled[free]
    counts = ", ".join(f"{len(points)} at {s:g} m" for points, s in grids)
    print(f"{where}: {len(grids)} grids in one file ({counts}); written at {step:g} m, the others filling it")
    return band, transform


def _xyz_points(data: bytes, where: str = "") -> np.ndarray:
    """The x, y, z columns of "x y z" lines (more columns are left out, as ever), a UTF-8 BOM left out. Lines that
    are not three numbers are left out and said when they are at most MALFORMED_SHARE of the lines (at least
    one); more, or no line at all, is an error."""
    if data.startswith(BOM):
        data = data[len(BOM):]
    if _CSV_NXYZF.match(data):
        return _csv_points(data, where)
    try:
        xyz = _loadtxt(data)
    except ValueError:
        bad = [m.span() for m in _NOT_XYZ.finditer(data)]
        lines = data.count(b"\n") + 1
        if not bad:
            raise
        first = data[bad[0][0]:bad[0][1]][:80]
        if len(bad) > max(1.0, MALFORMED_SHARE * lines):
            raise RuntimeError(f"{len(bad)} of {lines} lines are not x y z (the first: {first!r})") from None
        kept, pos = [], 0
        for start, end in bad:
            kept.append(data[pos:start])
            pos = end
        kept.append(data[pos:])
        xyz = _loadtxt(b"".join(kept))
        print(f"{where}: {len(bad)} of {lines} lines are not x y z and are left out (the first: {first!r})")
    if xyz.shape[0] == 0:
        raise RuntimeError("no x y z lines in the file")
    if xyz.shape[1] < 3:
        raise RuntimeError(f"lines of {xyz.shape[1]} number(s), x y z expected")
    return xyz[:, :3]


def _csv_points(data: bytes, where: str = "") -> np.ndarray:
    """The x, y, z of "n,x,y,z,flag" lines (columns 2-4): VIRTUAL SHIZUOKA's CSV grids (FY2021 centre and west,
    FY2025 north-west; 2026-11-15). The flag column is undocumented: 0, 1 and -9999 occur, all three with valid
    heights (08ME9065_2: the -9999 rows at 117.6-127.6 m among 117.4-232.4 m), so every row is kept. A line that is
    not five numbers is an error (these files are written by a program, none was seen broken)."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            xyz = np.loadtxt(io.BytesIO(data), dtype=np.float64, delimiter=",", usecols=(1, 2, 3), ndmin=2)
    except ValueError as e:
        raise RuntimeError(f"not n,x,y,z,flag lines ({e})") from None
    if xyz.shape[0] == 0:
        raise RuntimeError("no n,x,y,z,flag lines in the file")
    return xyz


def _loadtxt(data: bytes) -> np.ndarray:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)  # "input contained no data": _xyz_points says it
        return np.loadtxt(io.BytesIO(data), dtype=np.float64, ndmin=2)  # ~30x faster than np.fromstring


def _lattices(xyz: np.ndarray, res: float) -> List[Tuple[np.ndarray, float]]:
    """The points split by their offset from the lattice of res (in hundredths of res, x and y: coordinates
    written to the millimetre stay in one group), in the file's order, each group with its spacing (_step)."""
    phase = np.rint(np.mod(xyz[:, :2], res) / res * 100).astype(np.int64) % 100
    if (phase == phase[0]).all():
        return [(xyz, _step(xyz, res))]
    keys, inverse = np.unique(phase, axis=0, return_inverse=True)
    groups = [xyz[inverse.ravel() == i] for i in range(len(keys))]
    return [(points, _step(points, res)) for points in groups]


def _step(points: np.ndarray, res: float) -> float:
    """The spacing of a regular grid's points: the smallest step in x or y between points one after another in
    the file (along a row or a column) that at least STEP_SUPPORT of that axis's steps share (to res / 1000),
    so a stray pair of near-duplicate points does not count; res when no step is shared so (the points are on
    one spot, or too few). Moves under res / MAX_FINER are not steps (the other coordinate's jitter along a
    row), so the raster has at most MAX_FINER² times the pixels at res. A step within STEP_SNAP of a multiple
    of res, or of res / k, is that exactly (coordinates written to the millimetre)."""
    quantum = res * 1e-3
    steps = []
    for axis in (0, 1):
        moves = np.abs(np.diff(points[:, axis]))
        moves = moves[moves >= res / MAX_FINER]
        if moves.size:
            values, counts = np.unique(np.rint(moves / quantum).astype(np.int64), return_counts=True)
            shared = values[counts >= max(2, STEP_SUPPORT * moves.size)]
            if shared.size:
                steps.append(float(shared[0]) * quantum)
    step = min(steps) if steps else res
    k = max(1, round(step / res)) if step >= res else max(1, round(res / step))
    snapped = k * res if step >= res else res / k
    if abs(step - snapped) <= STEP_SNAP * snapped:
        step = snapped
    return res if step == res else round(step, 6)


def _grid_of(points: np.ndarray, step: float) -> Tuple[np.ndarray, Affine]:
    """The raster of the points of one regular grid (cell centres step apart), north up, NaN without a point."""
    x, y, z = points[:, 0], points[:, 1], points[:, 2]
    left, top = x.min(), y.max()
    cols = np.rint((x - left) / step).astype(np.int64)
    rows = np.rint((top - y) / step).astype(np.int64)
    band = np.full((rows.max() + 1, cols.max() + 1), np.nan, dtype=np.float32)
    band[rows, cols] = z
    return band, from_origin(left - step / 2, top + step / 2, step, step)
