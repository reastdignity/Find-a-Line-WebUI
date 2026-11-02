"""S3Blocks: blocks of the files of collections in an open S3 bucket, listed by ListObjectsV2 and composed
newest collection first (the Scottish Remote Sensing Portal)."""

import os
from typing import Callable, Dict, Optional, Sequence, Tuple

import rasterio as rio
from rasterio.warp import transform_bounds

import osm
from grid import Grid

from ..indexes.cached import CachedIndex
from ..indexes.s3listing import MAX_KEYS, S3Object, S3Objects
from ..indexes.versions import ComposedBlocks
from ..readers.windows import Windows
from .indexed import IndexedTiles

Box = Tuple[float, float, float, float]


class S3Blocks(IndexedTiles):
    """Blocks of block_m on the pixels of tiled files in an S3 bucket that anyone may list (ListObjectsV2,
    S3Objects), read by HTTP range requests (Windows) at their full resolution (never their overviews) and
    composed newest first (ComposedBlocks): each collection (a prefix of the bucket and its survey year) holds
    files named by the place they cover, names(left, bottom, right, top) the beginnings of the names over a box
    and extent(name) a file's box (None: not a file of the layer), both in crs.

    The listing of a 0.25° tile asks every collection for the names over it and keeps the files of suffix that
    meet the tile, with their collection's year and their date; a file's ETag is part of its name, so a file
    uploaded again (the portal re-uploads them) changes the key of its blocks, which are read again (update.py,
    or a search after the cached answer was renewed). Cached as ComposedBlocks' files.
    """

    def __init__(self, description: str, bucket: str, collections: Sequence[Tuple[str, int]], prefix: str,
                 folder: str, crs: str, native_res: float, block_m: float, bytes_per_tile: float,
                 names: Callable[[float, float, float, float], Sequence[str]],
                 extent: Callable[[str], Optional[Box]], suffix: str = ".tif", max_keys: int = MAX_KEYS):
        super().__init__(description, bucket, prefix, folder, native_res, bytes_per_tile)
        self.bucket, self.collections, self.crs, self.block_m = bucket, tuple(collections), crs, block_m
        self.names, self.extent, self.suffix = names, extent, suffix
        self.index_crs = crs
        self.index = CachedIndex(description, S3Objects(bucket, self._prefixes, self._item, max_keys),
                                 ComposedBlocks(folder, block_m, native_res), prefix, folder.split("/")[0])
        self.reader = Windows(description)

    def _box(self, lat: float, lon: float) -> Box:
        """A 0.25° tile in crs."""
        return transform_bounds("EPSG:4326", self.crs, lon, lat, lon + osm.TILE_DEG, lat + osm.TILE_DEG,
                                densify_pts=21)

    def _prefixes(self, lat: float, lon: float) -> Sequence[str]:
        names = self.names(*self._box(lat, lon))
        return [collection + name for collection, _ in self.collections for name in names]

    def _item(self, obj: S3Object, lat: float, lon: float) -> Optional[Dict]:
        """A listed file as cached ({name, url, crs, extent, year, published}), or None if it is not the
        layer's or does not meet the tile."""
        collection = next(((c, year) for c, year in self.collections if obj.key.startswith(c)), None)
        file = obj.key.rsplit("/", 1)[-1]
        if collection is None or not file.lower().endswith(self.suffix):
            return None
        stem = file[:-len(self.suffix)]
        extent = self.extent(stem)
        if extent is None:
            return None
        left, bottom, right, top = self._box(lat, lon)
        if not (extent[0] < right and extent[2] > left and extent[1] < top and extent[3] > bottom):
            return None
        return {"name": f"{stem}@{obj.etag[:8]}", "url": f"{self.bucket.rstrip('/')}/{obj.key}", "crs": self.crs,
                "extent": list(extent), "year": collection[1], "published": obj.last_modified}

    def has_data_near(self, lat: float, lon: float, cache_dir: str, metres: float = 2000) -> Optional[bool]:
        return self.index.versions.has_data_near(self.index, lat, lon, cache_dir, metres)

    def used(self, grid: Grid, cache_dir: str) -> Dict:
        """With the files the blocks were read from and the years of their collections (the newest year of a
        block's name may come from a file without data in it)."""
        info = super().used(grid, cache_dir)
        names, years = set(), set()
        for path in self.files(grid, cache_dir):
            if not os.path.exists(path):
                continue
            with rio.open(path) as src:
                tags = src.tags()
            names.update(n for n in tags.get("sources", "").split(",") if n)
            years.update(int(y) for y in tags.get("years", "").split(",") if y)
        info["source_files"] = sorted(names)
        info["survey_years"] = [min(years), max(years)] if years else info["survey_years"]
        return info
