"""SheetFile: a map sheet downloaded as a file (ASCII grid, XYZ or GeoTIFF, zipped once or twice, or several
members of one ZIP) and saved as a GeoTIFF."""

import io
import re
import zipfile
from typing import List, Optional, Tuple

import numpy as np
from affine import Affine
from rasterio.io import MemoryFile
from rasterio.transform import from_origin

from .. import net
from ..layer import Fetched, _clean, _write_tile
from ..composed import Reader

# The members _member_grid reads as rasters (GeoTIFF and ASCII grid by GDAL, XYZ text): a ZIP with members that
# holds none of them is no data, not an error (LGL's DOM1 ZIPs of three 1 km tiles on Baden-Württemberg's border,
# 379 KB each, dated 2026-07-03: two CSV lines of tile metadata, the licence PDF and a Meta-...txt, no raster;
# measured 2026-11-08). A .txt is metadata here, never an XYZ grid without a matching name.
RASTER_MEMBERS = (".tif", ".tiff", ".asc", ".xyz")


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
                 member_bytes: int = 100_000_000):
        self.description, self.members = description, members
        self.max_bytes, self.member_bytes = max_bytes, member_bytes

    def url(self, tile) -> Optional[str]:
        return tile.url

    def fetch(self, tile, path: str) -> Fetched:
        try:
            response = net._get(tile.url, binary_types=("octet", "zip", "text", "image"))
        except RuntimeError as e:
            raise RuntimeError(f"Could not download {self.description} sheet {tile.godlo}: {e}")
        if response is None:
            return Fetched(0, tile.url)
        if self.members is not None:
            parts = self._parts(tile, response.content)
            if parts is None:  # a ZIP without any raster: no data there
                return Fetched(0, tile.url)
            band, transform = parts
            _write_tile(path, _clean(band), tile.crs, transform)
            return Fetched.of(response, tile.url)
        name, data = tile.url.lower(), response.content
        while name.endswith(".zip"):  # sometimes zipped twice
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                name = next(n for n in archive.namelist() if n.lower().endswith((".asc", ".xyz", ".txt", ".zip")))
                data = archive.read(name)
                name = name.lower()
        if name.endswith(".asc"):
            with MemoryFile(data, ext=".asc") as memfile, memfile.open() as src:
                band = src.read(1, masked=True).astype(np.float32).filled(np.nan)
                transform = src.transform
        else:
            band, transform = _xyz_grid(data, tile.res)
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
                parts.append(_member_grid(info.filename, content, tile.res))
        return _merge(parts, tile.res, where)


def _member_grid(name: str, data: bytes, res: float) -> Tuple[np.ndarray, Affine]:
    """The raster of one member: a GeoTIFF or ASCII grid as GDAL reads it (its nodata as NaN),
    or "x y z" lines of cell centres."""
    lower = name.lower()
    if lower.endswith((".tif", ".tiff", ".asc")):
        with MemoryFile(data, ext=".asc" if lower.endswith(".asc") else ".tif") as memfile, memfile.open() as src:
            if src.count != 1:
                raise RuntimeError(f"{name}: {src.count} bands, one expected")
            return src.read(1, masked=True).astype(np.float32).filled(np.nan), src.transform
    return _xyz_grid(data, res)


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


def _xyz_grid(data: bytes, res: float) -> Tuple[np.ndarray, Affine]:
    """A raster from "x y z" lines of a regular grid (cell centres)."""
    xyz = np.loadtxt(io.BytesIO(data), dtype=np.float64, ndmin=2)  # ~30x faster than np.fromstring
    x, y, z = xyz[:, 0], xyz[:, 1], xyz[:, 2]
    left, top = x.min(), y.max()
    cols = np.rint((x - left) / res).astype(np.int64)
    rows = np.rint((top - y) / res).astype(np.int64)
    band = np.full((rows.max() + 1, cols.max() + 1), np.nan, dtype=np.float32)
    band[rows, cols] = z
    return band, from_origin(left - res / 2, top + res / 2, res, res)
