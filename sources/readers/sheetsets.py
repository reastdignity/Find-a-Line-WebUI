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
from .sheetfile import SheetFile


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

    def _read(self, name: str, url: str, request: SheetSetRequest) -> Tuple[Optional[Tuple[np.ndarray, Affine]], int]:
        """A file's raster (None: its ZIP holds no raster) and the bytes received."""
        res = request.transform.a
        tile = SimpleNamespace(url=url, godlo=f"{request.godlo} ({name})", crs=request.crs, res=res)
        response = self.sheet.download(tile)
        parts = self.sheet._parts(tile, response.content)
        return (None if parts is None else (_clean(parts[0]), parts[1])), len(response.content)

    def fetch(self, request: SheetSetRequest, path: str) -> Fetched:
        band = np.full(request.shape, np.nan, dtype=np.float32)
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
            for _, name, (values, transform) in sorted(read, key=lambda r: (-r[0], r[1])):  # the fuller first
                try:
                    pixels = paste(band, request.transform, values, transform)
                except ValueError as e:
                    raise RuntimeError(f"{self.description} sheet {request.godlo} ({name}): {e}") from e
                if pixels:
                    gave.append((name, year, pixels))
        url = self.url(request)
        if not gave:
            return Fetched(0, url)
        tags = {"sources": ",".join(g[0] for g in gave), "years": ",".join(str(g[1]) for g in gave),
                "pixels": ",".join(str(g[2]) for g in gave)}
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
