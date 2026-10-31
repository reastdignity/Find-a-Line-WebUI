"""SheetTiles: map sheets from a WFS sheet index (geoportal.gov.pl)."""

import io
import json
import os
import re
import zipfile
from typing import List, Optional, Tuple

import numpy as np
import requests
from affine import Affine
from rasterio.io import MemoryFile
from rasterio.transform import from_origin

import cache
import osm

from .. import net
from ..net import _part
from ..layer import Fetched, _clean, _write_tile
from .indexed import IndexedTiles

# Coordinate systems named in the uklad_xy attribute of the geoportal.gov.pl sheet indexes
SHEET_CRS = {"PL-1992": "EPSG:2180", "PL-2000:S5": "EPSG:2176", "PL-2000:S6": "EPSG:2177",
             "PL-2000:S7": "EPSG:2178", "PL-2000:S8": "EPSG:2179"}
SHEET_FORMATS = ("ARC/INFO ASCII GRID", "ASCII XYZ GRID")


class SheetTiles(IndexedTiles):
    """Map sheets listed in a WFS sheet index, downloaded as files (geoportal.gov.pl).

    The index has one layer per year (`<prefix><year>`); every sheet links to a file
    (ASCII grid or XYZ, sometimes zipped). Extents are cached in EPSG:2180.
    """
    index_crs = "EPSG:2180"

    def __init__(self, description: str, index_url: str, prefix: str, folder: str,
                 native_res: float, min_res: float = 0.5, bytes_per_tile: float = 30e6):
        """Sheets with a resolution between min_res and native_res are used (finer ones
        are huge as text: a 0.15 m sheet is about 2 GB)."""
        super().__init__(description, index_url, prefix, folder, native_res, bytes_per_tile)
        self.min_res = min_res
        self._years: Optional[List[str]] = None

    def _wfs(self, **params) -> str:
        response = requests.get(self.index_url, timeout=300, headers=cache.http_headers(),
                                params={"SERVICE": "WFS", "VERSION": "2.0.0", **params})
        response.raise_for_status()
        return response.text

    def _year_layers(self) -> List[str]:
        if self._years is None:
            names = re.findall(rf"<Name>(gugik:{self.prefix}\d{{4}})</Name>", self._wfs(REQUEST="GetCapabilities"))
            self._years = sorted(set(names))
        return self._years

    def _fetch_tile(self, lat: float, lon: float, path: str):
        sheets = []
        for layer in self._year_layers():
            text = self._wfs(REQUEST="GetFeature", TYPENAMES=layer, COUNT=10000,
                             PROPERTYNAME="godlo,akt_rok,char_przestrz,format,uklad_xy,url_do_pobrania,msGeometry",
                             BBOX=f"{lat},{lon},{lat + osm.TILE_DEG},{lon + osm.TILE_DEG},urn:ogc:def:crs:EPSG::4326")
            for member in text.split("<wfs:member>")[1:]:
                f = dict(re.findall(r"<gugik:(\w+)>([^<]*)</gugik:\1>", member))
                res = re.match(r"[\d.]+", f.get("char_przestrz", ""))
                url = f.get("url_do_pobrania", "")
                if not (res and url and f.get("format") in SHEET_FORMATS and f.get("uklad_xy") in SHEET_CRS):
                    continue
                if not self.min_res - 1e-6 <= float(res.group()) <= self.native_res + 1e-6:
                    continue
                # Extent from the sheet outline; EPSG:2180 lists northing before easting
                values = [float(v) for v in " ".join(re.findall(r"<gml:posList[^>]*>([^<]*)<", member)).split()]
                north, east = values[0::2], values[1::2]
                if not north:
                    continue
                sheets.append({"year": int(f["akt_rok"]), "godlo": f.get("godlo", ""), "url": url,
                               "crs": SHEET_CRS[f["uklad_xy"]], "res": float(res.group()),
                               "extent": [min(east), min(north), max(east), max(north)]})
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = _part(path)
        with open(tmp, "w", encoding="utf-8") as out:
            json.dump({"layers": self._year_layers(), "sheets": sheets}, out)
        os.replace(tmp, path)

    def download_tile(self, tile, path: str) -> Fetched:
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
