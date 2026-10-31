"""StacTiles: tiles of a STAC collection (swisstopo)."""

import glob
import hashlib
import json
import os
import re
from typing import Dict, List, Optional, Tuple

import requests

import cache
import osm
from grid import Grid

from .. import net
from ..net import RETRIES, _part
from ..layer import Fetched
from .indexed import IndexedTiles, Sheet


class StacTiles(IndexedTiles):
    """Square tiles of a STAC collection, one item per tile and survey year (swisstopo).

    An item (`<product>_<year>_<E>-<N>`, E and N in km) holds the tile as a
    cloud-optimized GeoTIFF at one or more resolutions (swissALTI3D: 0.5 and 2 m): the
    coarsest one not coarser than the working grid is used, cached in
    <folder>/<res>m/<year>_<E>-<N>.tif as published. Every file is checked against the
    sha256 of its item (file:checksum). The index answers (items per 0.25° tile) are
    cached and updated like a sheet index, so a newer survey of a tile replaces the
    older one.
    """

    def __init__(self, description: str, api: str, collection: str, folder: str, crs: str,
                 sizes: Dict[float, float], tile_m: float = 1000):
        """sizes: bytes per tile of every resolution used."""
        super().__init__(description, f"{api}/collections/{collection}/items", collection, folder,
                         native_res=min(sizes), bytes_per_tile=max(sizes.values()))
        self.index_crs, self.crs, self.sizes, self.tile_m = crs, crs, sizes, tile_m

    def _fetch_tile(self, lat: float, lon: float, path: str):
        sheets = []
        url = self.index_url
        params = {"bbox": f"{lon},{lat},{lon + osm.TILE_DEG},{lat + osm.TILE_DEG}", "limit": 100}
        while url:  # pages of 100 items
            response = requests.get(url, params=params, timeout=120, headers=cache.http_headers())
            response.raise_for_status()
            page = response.json()
            for item in page["features"]:
                name = re.search(r"_(\d{4})_(\d+)-(\d+)$", item["id"])
                if not name:
                    continue
                year, east, north = int(name.group(1)), int(name.group(2)), int(name.group(3))
                for asset in item["assets"].values():
                    res = float(asset.get("gsd") or 0)
                    if "tiff" not in asset.get("type", "") or res not in self.sizes:
                        continue
                    checksum = asset.get("file:checksum", "").lower()
                    sheets.append({"year": year, "godlo": f"{east}-{north}", "url": asset["href"],
                                   "crs": self.crs, "res": res,
                                   "sha256": checksum[4:] if checksum.startswith("1220") else None,
                                   "extent": [east * self.tile_m, north * self.tile_m,
                                              (east + 1) * self.tile_m, (north + 1) * self.tile_m]})
            url = next((link["href"] for link in page.get("links", []) if link.get("rel") == "next"), None)
            params = None  # the next link carries them
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = _part(path)
        with open(tmp, "w", encoding="utf-8") as out:
            json.dump({"sheets": sheets}, out)
        os.replace(tmp, path)

    def _sheet(self, item: Dict) -> Sheet:
        # One godło per tile and resolution: the newest survey and pruning work per resolution
        return Sheet(item["year"], item["godlo"], f"{item['godlo']}/{item['res']:g}m", item["url"],
                     item["crs"], item["res"], item.get("sha256"))

    def res_for(self, grid: Grid) -> float:
        """The resolution used for a grid: the coarsest one not coarser than the grid."""
        fitting = [r for r in self.sizes if r <= grid.res + 1e-6]
        return max(fitting) if fitting else min(self.sizes)

    def _wanted(self, sheet: Sheet, grid: Grid) -> bool:
        return sheet.res == self.res_for(grid)

    def _cached_files(self, grid: Grid, cache_dir: str) -> Tuple[List[str], float]:
        res = self.res_for(grid)
        return glob.glob(os.path.join(cache_dir, self.folder, f"{res:g}m", "*.tif")), res

    def tile_path(self, cache_dir: str, tile) -> str:
        return os.path.join(cache_dir, self.folder, f"{tile.res:g}m", f"{tile.year}_{tile.name}.tif")

    def estimate(self, grid: Grid, cache_dir: str, update: Optional[str]) -> Tuple[int, int, float]:
        self._use(cache_dir, update)
        if self.tiles(grid) is None:
            return super().estimate(grid, cache_dir, update)
        missing = self.missing(grid, cache_dir, update)
        return len(self.tiles(grid)), len(missing), sum(self.sizes[t.res] for t in missing) / 1e6

    def download_tile(self, tile, path: str) -> Fetched:
        for attempt in range(RETRIES):
            try:
                response = net._get(tile.url, binary_types=("tiff", "octet"))
            except RuntimeError as e:
                raise RuntimeError(f"Could not download {self.description} tile {tile.godlo} ({tile.year}): {e}")
            if response is None:
                return Fetched(0, tile.url)
            if not tile.sha256 or hashlib.sha256(response.content).hexdigest() == tile.sha256:
                break
            net._sleep(attempt)
        else:
            raise RuntimeError(f"{self.description} tile {tile.godlo} ({tile.year}): wrong checksum")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = _part(path)
        with open(tmp, "wb") as f:
            f.write(response.content)
        os.replace(tmp, path)
        return Fetched.of(response, tile.url)
