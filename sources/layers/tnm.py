"""TnmBlocks: blocks of the files of The National Map (USGS 3DEP), found through its API and composed newest
survey first."""

import math
import re
from typing import Dict, List, Optional

import rasterio as rio
import rasterio.warp
from rasterio.warp import transform_bounds

import cache
from grid import Grid

from ..indexes.cached import CachedIndex, merge_items
from ..indexes.listings import TnmProducts
from ..indexes.versions import ComposedBlocks
from ..readers.windows import Windows
from .indexed import IndexedTiles

TNM_API = "https://tnmaccess.nationalmap.gov/api/v1/products"


def folder_year(url: str) -> Optional[int]:
    """The year a 3DEP project's folders name (e.g. CA_YosemiteNP_2019_D19 or AK_IFSAR_2010/AK_IFSAR-Cell23_2010):
    a year in the name, else the fiscal year of a work unit suffix (UT_WestEast_B22); None when they name none
    (ND_Lidar_Phase10)."""
    folders = url.split("/Projects/", 1)[-1].rsplit("/", 2)[0] if "/Projects/" in url else ""
    years = re.findall(r"(?<!\d)((?:19|20)\d\d)(?!\d)", folders)
    if years:
        return max(int(y) for y in years)
    suffix = re.findall(r"_[A-Z](\d\d)(?=/|$)", folders)
    if suffix:
        return 2000 + max(int(y) for y in suffix)
    return None


def _survey_year(url: str, published: str) -> int:
    """The year of a 3DEP project: the year its folders name (folder_year), else the year of publication."""
    year = folder_year(url)
    if year is not None:
        return year
    return int(published[:4]) if published[:4].isdigit() else 0


class UnlistedIndex(CachedIndex):
    """The cached answers of the TNM index for the 1 m DEM with the files of USGS's bucket the index does not list
    (sources/layers/tnmbucket.py) merged in when an answer is read: a tile's files are its cached answer plus the
    unlisted files whose 10 km square reaches the tile and whose URL the answer does not hold. The cached answer
    stays what the index said (never rewritten), so an answer cached before the list gains its files at once and a
    block over one gets another key (it is read again, the older file pruned). Every reader of the files goes
    through answers(): ComposedBlocks.query, update_tile and has_data_near. The list is read once per process and
    data folder (the cached one, else the copy shipped with the code)."""

    has_list = True  # sources/renewal.py makes the list (tnmbucket.make_unlisted) before it asks the answers again
    bucket: Optional[str] = None  # the bucket the list is made from: tnmbucket.BUCKET (a test: its stand-in)
    regions: Optional[list] = None  # the boxes the index is listed over: tnmbucket.REGIONS

    def answers(self, cache_dir: str, lat: float, lon: float, update: Optional[str] = None) -> List[Dict]:
        return merge_items(super().answers(cache_dir, lat, lon, update), self.extra(cache_dir, lat, lon))

    def extra(self, cache_dir: str, lat: float, lon: float) -> List[Dict]:
        from .tnmbucket import unlisted_in_tile  # imported here: the web process never reads the list
        return unlisted_in_tile(cache_dir, self.top, lat, lon)


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
    index_class = CachedIndex  # the 1 m DEM's: UnlistedIndex
    # A download row's start and a country run's first tile ask its index again (sources/renewal.py): USGS
    # publishes new projects, and a cached answer is otherwise asked again only by `cache update`
    renews = True

    def __init__(self, description: str, dataset: str, prefix: str, folder: str, native_res: float,
                 block_m: float, bytes_per_tile: float, api: str = TNM_API):
        super().__init__(description, api, prefix, folder, native_res, bytes_per_tile)
        self.dataset, self.block_m = dataset, block_m
        self.index = self.index_class(description, TnmProducts(api, dataset, self._item),
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


# The x and y of a 1 m tile in its file name (in 10 km: the left edge, the top edge), and the zone of the names
# that give one (USGS_1M_<zone>_x..y..; USGS_one_meter_x..y.. and USGS_1m_x..y.. give none)
TILE_XY = re.compile(r"_x(\d+)y(\d+)_", re.I)
TILE_ZONE = re.compile(r"USGS_1M_(\d+)_", re.I)


def tile_extent(name: str) -> Optional[List[int]]:
    """The extent (in its UTM zone, metres) of a 1 m tile from its file name; None for a name without x..y.."""
    xy = TILE_XY.search(name)
    if not xy:
        return None
    x, y = int(xy.group(1)), int(xy.group(2))
    return [x * 10000, (y - 1) * 10000, (x + 1) * 10000, y * 10000]


def tile_item(url: str, zone: int, published: str, year: Optional[int] = None) -> Dict:
    """A file of the 1 m DEM as cached ({name, url, crs, extent, year, published}), its zone known: the item of a TNM
    answer (Usgs1mBlocks._item) and of a file of the bucket the index does not list (tnmbucket). year: the survey
    year when it is known otherwise (an unlisted file of a project whose folders name none), else _survey_year."""
    name = url.rsplit("/", 1)[-1]
    return {"name": name[:-4], "url": url, "crs": f"EPSG:{26900 + zone}", "extent": tile_extent(name),
            "year": _survey_year(url, published) if year is None else year, "published": published}


def usgs_1m_item(product: Dict) -> Optional[Dict]:
    """A product of the TNM index's 1 m DEM as cached, or None if it is not used (not a .tif, no x..y.. in its name,
    no zone found)."""
    url = product.get("downloadURL") or ""
    name = url.rsplit("/", 1)[-1]
    extent = tile_extent(name)
    if not name.lower().endswith(".tif") or extent is None:
        return None
    zone = TILE_ZONE.match(name)
    zone = int(zone.group(1)) if zone else _utm_zone_of(product.get("boundingBox") or {}, extent)
    if zone is None:
        return None
    return tile_item(url, zone, product.get("publicationDate") or "")


class Usgs1mBlocks(TnmBlocks):
    """3DEP's standard 1 m DEM: 10 km tiles, USGS_1M_<zone>_x<E / 10 km>y<N of the top / 10 km>_
    <project>.tif, in NAD83 / UTM of their zone (a tile crossing two zones is delivered in
    both), with 6 pixels of overlap around; older names give no zone (USGS_one_meter_x..y..).
    The files of USGS's bucket that the TNM index does not list are merged into its answers
    (UnlistedIndex, sources/layers/tnmbucket.py). `cache update` asks its answers again after
    28 days (update_ttl_days; the public site's monthly timer), a search's --update stale after
    the sheet index's 180 as before."""
    index_class = UnlistedIndex
    update_ttl_days = cache.TTL_DAYS["usgs-1m-index"]

    def _item(self, product: Dict) -> Optional[Dict]:
        return usgs_1m_item(product)


class IfsarBlocks(TnmBlocks):
    """Alaska's 5 m IfSAR DTM: cells of varying extent in Alaska Albers (EPSG:3338), on whole
    5 m pixels. Their extent is the box of the API projected (a little too large: a file
    without data in a block costs one opening)."""
    crs = "EPSG:3338"

    def _item(self, product: Dict) -> Optional[Dict]:
        url, box = product.get("downloadURL") or "", product.get("boundingBox")
        if not url.lower().endswith(".tif") or not box:
            return None
        left, bottom, right, top = transform_bounds("EPSG:4326", self.crs, box["minX"], box["minY"], box["maxX"],
                                                    box["maxY"], densify_pts=21)
        # Whole metres, outwards: PROJ's last digits differ between platforms (their libm), the cached
        # index must not
        extent = [math.floor(left), math.floor(bottom), math.ceil(right), math.ceil(top)]
        published = product.get("publicationDate") or ""
        return {"name": url.rsplit("/", 1)[-1][:-4], "url": url, "crs": self.crs, "extent": extent,
                "year": _survey_year(url, published), "published": published}
