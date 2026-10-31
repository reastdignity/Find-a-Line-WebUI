"""TnmBlocks: blocks of the files of The National Map (USGS 3DEP), found through its API and composed newest
survey first."""

import re
from typing import Dict, List, Optional

import rasterio as rio
import rasterio.warp
from rasterio.warp import transform_bounds

from grid import Grid

from ..indexes.cached import CachedIndex
from ..indexes.listings import TnmProducts
from ..indexes.versions import ComposedBlocks
from ..readers.windows import Windows
from .indexed import IndexedTiles

TNM_API = "https://tnmaccess.nationalmap.gov/api/v1/products"


def _survey_year(url: str, published: str) -> int:
    """The year of a 3DEP project from its folders (e.g. CA_YosemiteNP_2019_D19 or
    AK_IFSAR_2010/AK_IFSAR-Cell23_2010): a year in the name, else the fiscal year of a work
    unit suffix (UT_WestEast_B22), else the year of publication."""
    folders = url.split("/Projects/", 1)[-1].rsplit("/", 2)[0] if "/Projects/" in url else ""
    years = re.findall(r"(?<!\d)((?:19|20)\d\d)(?!\d)", folders)
    if years:
        return max(int(y) for y in years)
    suffix = re.findall(r"_[A-Z](\d\d)(?=/|$)", folders)
    if suffix:
        return 2000 + max(int(y) for y in suffix)
    return int(published[:4]) if published[:4].isdigit() else 0


class TnmBlocks(IndexedTiles):
    """Blocks of the files of a dataset of The National Map (USGS 3DEP), found through the
    TNM Access API and read by HTTP range requests: a CachedIndex of TnmProducts with
    ComposedBlocks, read by Windows.

    The files are big (10 km tiles of the 1 m DEM: 10-450 MB; Alaska's IfSAR cells: up to
    900 MB) and tiled, mostly cloud-optimized, so only the blocks over the grid are read:
    squares of block_m on a fixed grid in the files' CRS, each cached as a GeoTIFF of its own
    (<folder>/<epsg>/<i // 10>_<j // 10>/<year>_<i>_<j>_<key>.tif). A place is often in
    several files (surveys, "projects"), and a newer project may cover only part of a tile,
    so a block is composed newest first: an older file fills only the pixels still without
    data and is read only while some remain. The index answers are cached per 0.25° tile
    like a sheet index; a new project over a block changes its key, so the block is read
    again (update.py, or a search after the answer was renewed) and the older file deleted.
    """
    index_crs = "EPSG:4326"

    def __init__(self, description: str, dataset: str, prefix: str, folder: str, native_res: float,
                 block_m: float, bytes_per_tile: float, api: str = TNM_API):
        super().__init__(description, api, prefix, folder, native_res, bytes_per_tile)
        self.dataset, self.block_m = dataset, block_m
        self.index = CachedIndex(description, TnmProducts(api, dataset, self._item),
                                 ComposedBlocks(folder, block_m, native_res), prefix, folder.split("/")[0])
        self.reader = Windows(description)

    def _item(self, product: Dict) -> Optional[Dict]:
        """A product of the API as cached ({name, url, crs, extent (in crs), year, published}),
        or None if it is not used."""
        raise NotImplementedError

    def has_data_near(self, lat: float, lon: float, cache_dir: str, metres: float = 2000) -> Optional[bool]:
        return self.index.versions.has_data_near(self.index, lat, lon, cache_dir, metres)

    def used(self, grid: Grid, cache_dir: str) -> Dict:
        """With the files the blocks were read from and the years of their surveys (the
        newest year of a block's name may come from a file without data in it)."""
        info = super().used(grid, cache_dir)
        names, years = set(), set()
        for path in self.files(grid, cache_dir):
            with rio.open(path) as src:
                tags = src.tags()
            names.update(n for n in tags.get("sources", "").split(",") if n)
            years.update(int(y) for y in tags.get("years", "").split(",") if y)
        info["source_files"] = sorted(names)
        info["survey_years"] = [min(years), max(years)] if years else info["survey_years"]
        return info


def _utm_zone_of(box: Dict, extent: List[float]) -> Optional[int]:
    """The UTM zone of a 1 m tile whose file name does not say it: the zone (of the centre of
    its box, or a neighbour) in which the tile's extent lands on its box."""
    lon, lat = (box["minX"] + box["maxX"]) / 2, (box["minY"] + box["maxY"]) / 2
    zone = int((lon + 180) // 6) + 1
    cx, cy = (extent[0] + extent[2]) / 2, (extent[1] + extent[3]) / 2
    for z in (zone, zone - 1, zone + 1):
        if 1 <= z <= 23:
            x, y = rio.warp.transform(f"EPSG:{26900 + z}", "EPSG:4326", [cx], [cy])
            if box["minX"] - 0.01 <= x[0] <= box["maxX"] + 0.01 and box["minY"] - 0.01 <= y[0] <= box["maxY"] + 0.01:
                return z
    return None


class Usgs1mBlocks(TnmBlocks):
    """3DEP's standard 1 m DEM: 10 km tiles, USGS_1M_<zone>_x<E / 10 km>y<N of the top / 10 km>_
    <project>.tif, in NAD83 / UTM of their zone (a tile crossing two zones is delivered in
    both), with 6 pixels of overlap around; older names give no zone (USGS_one_meter_x..y..)."""

    def _item(self, product: Dict) -> Optional[Dict]:
        url = product.get("downloadURL") or ""
        name = url.rsplit("/", 1)[-1]
        xy = re.search(r"_x(\d+)y(\d+)_", name, re.I)
        if not name.lower().endswith(".tif") or not xy:
            return None
        x, y = int(xy.group(1)), int(xy.group(2))
        extent = [x * 10000, (y - 1) * 10000, (x + 1) * 10000, y * 10000]
        zone = re.match(r"USGS_1M_(\d+)_", name, re.I)
        zone = int(zone.group(1)) if zone else _utm_zone_of(product.get("boundingBox") or {}, extent)
        if zone is None:
            return None
        published = product.get("publicationDate") or ""
        return {"name": name[:-4], "url": url, "crs": f"EPSG:{26900 + zone}", "extent": extent,
                "year": _survey_year(url, published), "published": published}


class IfsarBlocks(TnmBlocks):
    """Alaska's 5 m IfSAR DTM: cells of varying extent in Alaska Albers (EPSG:3338), on whole
    5 m pixels. Their extent is the box of the API projected (a little too large: a file
    without data in a block costs one opening)."""
    crs = "EPSG:3338"

    def _item(self, product: Dict) -> Optional[Dict]:
        url, box = product.get("downloadURL") or "", product.get("boundingBox")
        if not url.lower().endswith(".tif") or not box:
            return None
        extent = transform_bounds("EPSG:4326", self.crs, box["minX"], box["minY"], box["maxX"], box["maxY"],
                                  densify_pts=21)
        published = product.get("publicationDate") or ""
        return {"name": url.rsplit("/", 1)[-1][:-4], "url": url, "crs": self.crs, "extent": list(extent),
                "year": _survey_year(url, published), "published": published}
