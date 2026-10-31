"""TnmBlocks: blocks of the files of The National Map (USGS 3DEP), found through its API and composed newest
survey first."""

import glob
import hashlib
import json
import math
import os
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import rasterio as rio
import rasterio.warp
import requests
from rasterio.transform import from_origin
from rasterio.warp import transform_bounds

import cache
import osm
from grid import Grid

from .. import net
from ..net import RETRIES, _part
from ..layer import Fetched
from .indexed import IndexedTiles
from ..readers.windows import _read_block, _same_crs

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


@dataclass(frozen=True)
class Block:
    """A square of a TnmBlocks layer: (i, j) on a grid of `size` metres in crs, composed from
    the files (name, url, survey year), newest first. The key tells sets of files apart: a new survey over
    the block gives it another key, so it is read again."""
    crs: str
    i: int
    j: int
    size: float
    year: int  # of the newest file
    key: str
    files: Tuple[Tuple[str, str, int], ...] = ()


class TnmBlocks(IndexedTiles):
    """Blocks of the files of a dataset of The National Map (USGS 3DEP), found through the
    TNM Access API and read by HTTP range requests.

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

    def _item(self, product: Dict) -> Optional[Dict]:
        """A product of the API as cached ({name, url, crs, extent (in crs), year, published}),
        or None if it is not used."""
        raise NotImplementedError

    def _fetch_tile(self, lat: float, lon: float, path: str):
        items: Dict[str, Dict] = {}
        offset, total = 0, 1
        while offset < total:  # pages of up to 500 products
            for attempt in range(RETRIES):
                try:
                    response = requests.get(self.index_url, timeout=120, headers=cache.http_headers(), params={
                        "datasets": self.dataset, "max": 500, "offset": offset,
                        "bbox": f"{lon},{lat},{lon + osm.TILE_DEG},{lat + osm.TILE_DEG}"})
                    response.raise_for_status()
                    page = response.json()
                    break
                except (requests.RequestException, ValueError) as e:  # the API is sometimes slow or down
                    if attempt == RETRIES - 1:
                        raise requests.RequestException(f"TNM API: {e}")
                    net._sleep(attempt)
            products = page.get("items") or []
            for product in products:
                item = self._item(product)
                if item:
                    items[item["url"]] = item
            offset, total = offset + len(products), (page.get("total") or 0) if products else 0
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = _part(path)
        with open(tmp, "w", encoding="utf-8") as out:
            json.dump({"sheets": list(items.values())}, out)
        os.replace(tmp, path)

    def _items(self, cache_dir: str, west: float, south: float, east: float, north: float,
               update: Optional[str] = None) -> List[Dict]:
        """The listed files of the index tiles over a box (WGS84)."""
        items: Dict[str, Dict] = {}
        for lat, lon in osm.tiles(west, south, east, north):
            for item in self._index_tile(cache_dir, lat, lon, update):
                items[item["url"]] = item
        return list(items.values())

    def _blocks(self, items: List[Dict], bounds: Dict[str, tuple], shape=None) -> List[Block]:
        """The blocks within bounds (per CRS: left, bottom, right, top), and under the shape
        (in WGS84) if given, with the files over each, newest first."""
        size = self.block_m
        over: Dict[tuple, List[Dict]] = {}
        for item in items:
            if item["crs"] not in bounds:
                continue
            left, bottom, right, top = bounds[item["crs"]]
            e_left, e_bottom, e_right, e_top = item["extent"]
            left, bottom, right, top = max(left, e_left), max(bottom, e_bottom), min(right, e_right), min(top, e_top)
            if left >= right or bottom >= top:
                continue
            for i in range(math.floor(left / size), math.ceil(right / size)):
                for j in range(math.floor(bottom / size), math.ceil(top / size)):
                    over.setdefault((item["crs"], i, j), []).append(item)
        if shape is not None:
            from area import project
            from shapely.geometry import box
            projected = {crs: project(shape, "EPSG:4326", crs) for crs in bounds}
            over = {k: v for k, v in over.items()
                    if projected[k[0]].intersects(box(k[1] * size, k[2] * size, (k[1] + 1) * size, (k[2] + 1) * size))}
        blocks = []
        for (crs, i, j), files in over.items():
            files = sorted(files, key=lambda f: (f["year"], f.get("published", ""), f["name"]), reverse=True)
            key = hashlib.sha1(",".join(sorted(f["name"] for f in files)).encode()).hexdigest()[:8]
            blocks.append(Block(crs, i, j, size, files[0]["year"], key,
                                tuple((f["name"], f["url"], f["year"]) for f in files)))
        return blocks

    def _query(self, grid: Grid, cache_dir: str) -> list:
        west, south, east, north = transform_bounds(grid.crs, "EPSG:4326", *grid.bounds)
        items = self._items(cache_dir, west, south, east, north, self._update)
        bounds = {crs: transform_bounds(grid.crs, crs, *grid.bounds) for crs in {item["crs"] for item in items}}
        shape = None
        if grid.area_shape is not None:
            from area import project
            shape = project(grid.area_shape, grid.crs, "EPSG:4326")
        # Blocks in the working CRS first: copied onto the grid as they are, they win where
        # a tile is delivered in two UTM zones
        return sorted(self._blocks(items, bounds, shape),
                      key=lambda b: (not _same_crs(b.crs, grid.crs), b.crs, b.j, b.i))

    def tile_path(self, cache_dir: str, tile) -> str:
        return os.path.join(cache_dir, self.folder, tile.crs.lower().replace(":", ""),
                            f"{tile.i // 10}_{tile.j // 10}", f"{tile.year}_{tile.i}_{tile.j}_{tile.key}.tif")

    def _block_of(self, path: str) -> Optional[Block]:
        """The block of a cached file (without its files)."""
        match = re.search(r"[\\/](epsg\d+)[\\/]-?\d+_-?\d+[\\/](\d+)_(-?\d+)_(-?\d+)_([0-9a-f]+)\.tif$", path)
        if not match:
            return None
        return Block(match.group(1).upper().replace("EPSG", "EPSG:"), int(match.group(3)), int(match.group(4)),
                     self.block_m, int(match.group(2)), match.group(5))

    def _cached_paths(self, cache_dir: str) -> List[str]:
        return glob.glob(os.path.join(cache_dir, self.folder, "epsg*", "*", "*.tif"))

    def _cached(self, grid: Grid, cache_dir: str) -> list:
        blocks = []
        for path in self._cached_paths(cache_dir):
            block = self._block_of(path)
            if block is None:
                continue
            s = block.size
            left, bottom, right, top = transform_bounds(block.crs, grid.crs, block.i * s, block.j * s,
                                                        (block.i + 1) * s, (block.j + 1) * s)
            g_left, g_bottom, g_right, g_top = grid.bounds
            if left < g_right and right > g_left and bottom < g_top and top > g_bottom:
                blocks.append(block)
        return sorted(blocks, key=lambda b: (not _same_crs(b.crs, grid.crs), -b.year, b.crs, b.j, b.i))

    def _others(self, cache_dir: str, block: Block) -> List[str]:
        """The cached files of the same block made from other sets of files."""
        folder = os.path.dirname(self.tile_path(cache_dir, block))
        found = [os.path.join(folder, n) for n in os.listdir(folder)] if os.path.isdir(folder) else []
        return [p for p in found if (b := self._block_of(p)) is not None and (b.i, b.j) == (block.i, block.j)
                and b.key != block.key]

    def _prune(self, cache_dir: str, sheets: List[Block]) -> int:
        older = []
        for block in sheets:
            if os.path.exists(self.tile_path(cache_dir, block)):
                older += self._others(cache_dir, block)
        cache.forget(cache_dir, older)
        return len(older)

    def _block_wgs84(self, block: Block) -> Tuple[float, float, float, float]:
        s = block.size
        return transform_bounds(block.crs, "EPSG:4326", block.i * s, block.j * s, (block.i + 1) * s, (block.j + 1) * s)

    def update_index_tile(self, cache_dir: str, lat: float, lon: float) -> Tuple[int, int, int]:
        """Ask the index again for one tile and read again the cached blocks (centred in it)
        over which the set of files changed (the older files are deleted)."""
        self._index_tile(cache_dir, lat, lon, "all")
        todo = []
        for path in self._cached_paths(cache_dir):
            block = self._block_of(path)
            if block is None:
                continue
            west, south, east, north = self._block_wgs84(block)
            if not (lat <= (south + north) / 2 < lat + osm.TILE_DEG and lon <= (west + east) / 2 < lon + osm.TILE_DEG):
                continue
            s = block.size
            inner = (block.i * s + s / 4, block.j * s + s / 4, (block.i + 1) * s - s / 4, (block.j + 1) * s - s / 4)
            now = [b for b in self._blocks(self._items(cache_dir, west, south, east, north), {block.crs: inner})
                   if (b.i, b.j) == (block.i, block.j)]
            if now and now[0].key != block.key and not os.path.exists(self.tile_path(cache_dir, now[0])):
                todo.append(now[0])
        received = sum(self._download_and_record(b, cache_dir) for b in todo)
        return len(todo), received / 1e6, self._prune(cache_dir, todo)

    def has_data_near(self, lat: float, lon: float, cache_dir: str, metres: float = 2000) -> Optional[bool]:
        try:
            items = self._items(cache_dir, lon, lat, lon, lat)
        except requests.RequestException:
            return None
        for item in items:
            x, y = rio.warp.transform("EPSG:4326", item["crs"], [lon], [lat])
            left, bottom, right, top = item["extent"]
            if left - metres <= x[0] <= right + metres and bottom - metres <= y[0] <= top + metres:
                return True
        return False

    def tile_url(self, tile) -> Optional[str]:
        return tile.files[0][1] if tile.files else None

    def download_tile(self, tile, path: str) -> Fetched:
        px = round(tile.size / self.native_res)
        transform = from_origin(tile.i * tile.size, (tile.j + 1) * tile.size, self.native_res, self.native_res)
        return _read_block(tile.files, tile.crs, transform, (px, px), path, self.description)

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
