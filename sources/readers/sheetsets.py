"""SheetSetFile: one map sheet composed from every file the publisher has for it (surveys of several years, two
deliveries of one year), newest survey first, each file a ZIP read by SheetFile."""

import itertools
import os
from types import SimpleNamespace
from typing import List, NamedTuple, Optional, Sequence, Tuple

import numpy as np
from affine import Affine

from ..composed import Reader
from ..layer import Fetched, _clean, _write_tile
from .sheetfile import BOM, SheetFile, _lem_grid, _member_grid, _xyz_points


# A text point's offset from its pixel's centre, in pixels, beyond which it is not on the sheet's pixels (the
# coordinates are written to the millimetre: 0.002 of a 0.5 m pixel; a point on a pixel edge is 0.5 off)
OFF_CENTRE = 0.05


class SheetSetRequest(NamedTuple):
    """A sheet to compose: its files (name, url, survey year, bytes), newest year first, and its pixels."""
    files: Sequence[Tuple[str, str, int, int]]
    crs: str
    transform: Affine
    shape: Tuple[int, int]  # rows, columns
    godlo: str  # the sheet's name in messages


def paste(target: np.ndarray, at: Affine, values: np.ndarray, transform: Affine) -> int:
    """Copy a raster on the same pixels into the pixels of target still without data (NaN), the part inside
    target only; how many pixels it gave. ValueError when it is not on target's pixels."""
    res = at.a
    col, row = (transform.c - at.c) / res, (at.f - transform.f) / res
    if not (np.isclose(transform.a, res) and np.isclose(transform.e, at.e) and np.isclose(col, round(col))
            and np.isclose(row, round(row))):
        raise ValueError(f"a raster at ({transform.c}, {transform.f}) of {transform.a} m is not on the sheet's pixels")
    col, row = round(col), round(row)
    r0, c0 = max(row, 0), max(col, 0)
    r1, c1 = min(row + values.shape[0], target.shape[0]), min(col + values.shape[1], target.shape[1])
    if r0 >= r1 or c0 >= c1:
        return 0
    window = target[r0:r1, c0:c1]
    part = values[r0 - row:r1 - row, c0 - col:c1 - col]
    free = np.isnan(window) & ~np.isnan(part)
    window[free] = part[free]
    return int(free.sum())


class SheetSetFile(Reader):
    """A sheet composed from its files (SheetSetRequest), each a ZIP whose members matching members are read by
    SheetFile (listed: a 404 is an error) and placed on the sheet's pixels by their coordinates (points missing
    from a file are no data; a file's points outside the sheet are left out). The newest year first; an older year
    is downloaded only while the sheet still has pixels without data. Within one year every file is read and the
    fuller (more valid pixels) goes first, the others filling its holes (VIRTUAL SHIZUOKA's `<sheet>.zip` and
    `<sheet>_2.zip`: partial or full deliveries of one survey). Saved with the names, years and pixels given of the
    files that gave pixels (tags "sources", "years", "pixels"); no file when none gave any."""
    rewrites = True  # written by _write_tile

    def __init__(self, description: str, members: str, max_bytes: int = 200_000_000,
                 member_bytes: int = 100_000_000):
        self.description = description
        self.sheet = SheetFile(description, members=members, max_bytes=max_bytes, member_bytes=member_bytes,
                               listed=True)

    def url(self, request: SheetSetRequest) -> Optional[str]:
        return request.files[0][1] if request.files else None

    def _member(self, request: SheetSetRequest):
        """SheetFile._parts' reader of one member, on the sheet's own pixels: a GeoTIFF as GDAL reads it (placed by
        paste); text lines ("x y z", or "n,x,y,z,flag") gridded straight onto the sheet's pixels at the layer's
        resolution (each point in the pixel holding it: the step is the layer's, never guessed from the points,
        so a sparse member, every other point or rows 1 m apart, is read as it is); a ".lem" member (heights
        only, _lem_grid) holds exactly the sheet's pixels, rows north to south; an empty member is no data
        (None: an older survey fills the sheet). Points off the sheet are left out; a member none of whose points
        lies on the sheet is an error naming the points' box against the sheet's."""
        at, (rows, cols) = request.transform, request.shape
        res = at.a
        left, top = at.c, at.f
        box = (left, top - rows * res, left + cols * res, top)

        def grid(name: str, data: bytes, member_res: float, crs: str, where: str):
            if name.lower().endswith((".tif", ".tiff", ".asc")):
                return _member_grid(name, data, member_res, crs, where)
            if not data.strip(BOM + b" \t\r\n"):
                print(f"{where}: an empty member; no data")
                return None
            if name.lower().endswith(".lem"):  # heights only, on the sheet's own pixels (Kanagawa's MESH grids)
                try:
                    return _lem_grid(data, (rows, cols)), at
                except RuntimeError as e:
                    raise RuntimeError(f"{where}: {e}") from e
            try:
                xyz = _xyz_points(data, where)
            except (ValueError, RuntimeError) as e:
                raise RuntimeError(f"{where}: {e}") from e
            fx, fy = (xyz[:, 0] - left) / res, (top - xyz[:, 1]) / res
            off = (np.abs(fx - np.floor(fx) - 0.5) > OFF_CENTRE) | (np.abs(fy - np.floor(fy) - 0.5) > OFF_CENTRE)
            if off.any():  # points on pixel edges, or anywhere but the centres: not the sheet's pixels
                k = int(np.argmax(off))
                raise RuntimeError(f"{where}: {int(off.sum())} of its {len(xyz)} points are not on the sheet's "
                                   f"{res:g} m pixel centres (the first: {xyz[k, 0]:.3f}, {xyz[k, 1]:.3f})")
            col = np.floor(fx).astype(np.int64)
            row = np.floor(fy).astype(np.int64)
            inside = (col >= 0) & (col < cols) & (row >= 0) & (row < rows)
            if not inside.any():
                raise RuntimeError(
                    f"{where}: none of its {len(xyz)} points lies on the sheet (points x {xyz[:, 0].min():.2f}.."
                    f"{xyz[:, 0].max():.2f}, y {xyz[:, 1].min():.2f}..{xyz[:, 1].max():.2f}; the sheet x "
                    f"{box[0]:.2f}..{box[2]:.2f}, y {box[1]:.2f}..{box[3]:.2f})")
            band = np.full((rows, cols), np.nan, dtype=np.float32)
            band[row[inside], col[inside]] = xyz[inside, 2]
            return band, at
        return grid

    def _read(self, name: str, url: str, request: SheetSetRequest) -> Tuple[Optional[Tuple[np.ndarray, Affine]], int]:
        """A file's raster (None: its ZIP holds no data) and the bytes received."""
        res = request.transform.a
        tile = SimpleNamespace(url=url, godlo=f"{request.godlo} ({name})", crs=request.crs, res=res)
        response = self.sheet.download(tile)
        parts = self.sheet._parts(tile, response.content, member_grid=self._member(request))
        return (None if parts is None else (_clean(parts[0]), parts[1])), len(response.content)

    def fetch(self, request: SheetSetRequest, path: str) -> Fetched:
        band = np.full(request.shape, np.nan, dtype=np.float32)
        at = request.transform
        sheet_box = (at.c, at.f - request.shape[0] * at.a, at.c + request.shape[1] * at.a, at.f)
        gave: List[Tuple[str, int, int]] = []  # name, year, pixels
        received = 0
        for year, files in itertools.groupby(request.files, key=lambda f: f[2]):
            if gave and not np.isnan(band).any():
                break  # no hole left: the older surveys are not needed
            read = []
            for name, url, _, _ in files:
                raster, size = self._read(name, url, request)
                received += size
                if raster is not None:
                    read.append((int(np.count_nonzero(~np.isnan(raster[0]))), name, raster))
            for count, name, (values, transform) in sorted(read, key=lambda r: (-r[0], r[1])):  # the fuller first
                where = f"{self.description} sheet {request.godlo} ({name})"
                r_box = (transform.c, transform.f + values.shape[0] * transform.e,
                         transform.c + values.shape[1] * transform.a, transform.f)
                if count and not (r_box[0] < sheet_box[2] and r_box[2] > sheet_box[0] and r_box[1] < sheet_box[3]
                                  and r_box[3] > sheet_box[1]):
                    raise RuntimeError(f"{where}: its data lie off the sheet (x {r_box[0]:.2f}..{r_box[2]:.2f}, "
                                       f"y {r_box[1]:.2f}..{r_box[3]:.2f}; the sheet x {sheet_box[0]:.2f}.."
                                       f"{sheet_box[2]:.2f}, y {sheet_box[1]:.2f}..{sheet_box[3]:.2f})")
                try:
                    pixels = paste(band, request.transform, values, transform)
                except ValueError as e:
                    raise RuntimeError(f"{where}: {e}") from e
                if pixels:
                    gave.append((name, year, pixels))
        url = self.url(request)
        if not gave:
            return Fetched(0, url)
        tags = {"sources": ",".join(g[0] for g in gave), "years": ",".join(str(g[1]) for g in gave),
                "pixels": ",".join(str(g[2]) for g in gave), "files": ",".join(f[0] for f in request.files)}
        _write_tile(path, band, request.crs, request.transform, tags=tags)
        return Fetched(received, url)


def gave_pixels(path: str) -> List[Tuple[str, int, int]]:
    """(name, year, pixels) of the files a cached sheet was composed from (SheetSetFile's tags)."""
    import rasterio as rio
    if not os.path.exists(path):
        return []
    with rio.open(path) as src:
        tags = src.tags()
    names, years, pixels = (tags.get(k, "").split(",") for k in ("sources", "years", "pixels"))
    return [(n, int(y), int(p)) for n, y, p in zip(names, years, pixels) if n]
