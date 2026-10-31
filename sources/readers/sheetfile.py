"""SheetFile: a map sheet downloaded as a file (ASCII grid or XYZ, zipped once or twice) and saved as a GeoTIFF."""

import io
import zipfile
from typing import Optional, Tuple

import numpy as np
from affine import Affine
from rasterio.io import MemoryFile
from rasterio.transform import from_origin

from .. import net
from ..layer import Fetched, _clean, _write_tile
from ..composed import Reader


class SheetFile(Reader):
    """A Sheet's file (geoportal.gov.pl): an ARC/INFO ASCII grid or "x y z" lines of a regular
    grid, sometimes zipped (twice), saved as a float32 GeoTIFF in the sheet's CRS."""

    def __init__(self, description: str):
        self.description = description

    def url(self, tile) -> Optional[str]:
        return tile.url

    def fetch(self, tile, path: str) -> Fetched:
        try:
            response = net._get(tile.url, binary_types=("octet", "zip", "text", "image"))
        except RuntimeError as e:
            raise RuntimeError(f"Could not download {self.description} sheet {tile.godlo}: {e}")
        if response is None:
            return Fetched(0, tile.url)
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
