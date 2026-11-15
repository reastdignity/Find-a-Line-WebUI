"""S3SheetSets: map sheets as ZIP files in an open S3 bucket, listed by ListObjectsV2, several files per sheet
(surveys of different years, two deliveries of one year) composed newest first (VIRTUAL SHIZUOKA's LP grids)."""

import re
import threading
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from rasterio.warp import transform_bounds

import cache
import osm
from grid import Grid

from ..credit import Credit
from ..indexes.cached import CachedIndex
from ..indexes.s3listing import MAX_KEYS, S3Object, S3Objects, common_prefixes
from ..indexes.sheetsets import SheetSets
from ..indexes.tilings import MetricCellTiling
from ..readers.sheetsets import SheetSetFile, gave_pixels
from .indexed import IndexedTiles
from .s3blocks import Box

# What a listed key is: (survey year, level, cell (i, j)); None: not a file of the layer
KeyParser = Callable[[str], Optional[Tuple[int, str, Tuple[int, int]]]]


class S3SheetSets(IndexedTiles):
    """Sheets of one or more levels (levels: name -> MetricCellTiling, the cells of each size and their names), each
    composed from every file the bucket holds for it (SheetSets, read by SheetSetFile): the newest survey first, an
    older one only while the sheet has holes, the fuller of two files of one survey first.

    The bucket's top folders matching `folders` (one per survey, e.g. "2019/") are found by one delimiter listing
    per process; the listing of a 0.25° tile asks prefixes(folder, box) under each (box: the tile in crs) and
    keeps the keys parse(key) knows whose sheet meets the tile, with their size; a file's ETag is part of its
    name, so a file uploaded again in place changes its sheet's key, which is read again (update.py, or a search
    after the cached answer was renewed). The estimate counts the listed bytes of each sheet's newest survey."""

    def __init__(self, description: str, bucket: str, folders: str,
                 prefixes: Callable[[str, Box], Sequence[str]], parse: KeyParser, prefix: str, folder: str,
                 crs: str, native_res: float, levels: Dict[str, MetricCellTiling], members: str,
                 bytes_per_tile: float, max_keys: int = MAX_KEYS,
                 level_credits: Optional[Dict[str, Tuple[str, Credit]]] = None, credit: Optional[Credit] = None):
        super().__init__(description, bucket, prefix, folder, native_res, bytes_per_tile)
        # A level whose files carry a credit of their own (label, credit): a run records it as an entry of its own
        # when that level's sheets gave the mosaic a pixel (used_entries)
        self.level_credits = dict(level_credits or {})
        self.credits_by_pixels = bool(self.level_credits)
        if credit is not None:
            self.credit = credit
        self.bucket, self.folders_pattern, self.prefixes, self.parse = bucket, folders, prefixes, parse
        self.crs, self.levels, self.members = crs, levels, members
        self.index_crs = crs
        self.index = CachedIndex(description, S3Objects(bucket, self._prefixes, self._item, max_keys),
                                 SheetSets(folder, crs, native_res, levels), prefix, folder.split("/")[0])
        self.reader = SheetSetFile(description, members)
        self._folders: Optional[List[str]] = None
        self._folders_lock = threading.Lock()

    def survey_folders(self) -> List[str]:
        """The bucket's top folders of the surveys (one delimiter listing, kept for the process)."""
        with self._folders_lock:
            if self._folders is None:
                self._folders = [p for p in common_prefixes(self.bucket, "") if re.fullmatch(self.folders_pattern, p)]
            return list(self._folders)

    def _box(self, lat: float, lon: float) -> Box:
        """A 0.25° tile in crs."""
        return transform_bounds("EPSG:4326", self.crs, lon, lat, lon + osm.TILE_DEG, lat + osm.TILE_DEG,
                                densify_pts=21)

    def _prefixes(self, lat: float, lon: float) -> Sequence[str]:
        box = self._box(lat, lon)
        return [p for folder in self.survey_folders() for p in self.prefixes(folder, box)]

    def _item(self, obj: S3Object, lat: float, lon: float) -> Optional[Dict]:
        """A listed file as cached ({name, url, level, cell, year, size}), or None if it is not the layer's or
        its sheet does not meet the tile."""
        parsed = self.parse(obj.key)
        if parsed is None:
            return None
        year, level, cell = parsed
        left, bottom, right, top = self.levels[level].edges(cell)
        b_left, b_bottom, b_right, b_top = self._box(lat, lon)
        if not (left < b_right and right > b_left and bottom < b_top and top > b_bottom):
            return None
        stem = obj.key.rsplit("/", 1)[-1].rsplit(".", 1)[0]
        return {"name": f"{year}_{stem}@{obj.etag[:8]}", "url": f"{self.bucket.rstrip('/')}/{obj.key}",
                "level": level, "cell": list(cell), "year": year, "size": obj.size}

    def has_data_near(self, lat: float, lon: float, cache_dir: str, metres: float = 2000) -> Optional[bool]:
        return self.index.versions.has_data_near(self.index, lat, lon, cache_dir, metres)

    def estimate(self, grid: Grid, cache_dir: str, update: Optional[str]) -> Tuple[int, int, float]:
        """(sheets, sheets to download, MB): the listed bytes of each missing sheet's newest survey (an older one
        is read only for holes)."""
        self._use(cache_dir, update)
        sheets = self.tiles(grid)
        if sheets is None:
            return len(self.index.cached(grid, cache_dir)), 0, 0.0
        missing = self.missing(grid, cache_dir, update)
        return len(sheets), len(missing), sum(s.bytes for s in missing) / 1e6

    def used(self, grid: Grid, cache_dir: str) -> Dict:
        """With the files that gave the sheets their pixels and the years of their surveys."""
        info = super().used(grid, cache_dir)
        names, years = set(), set()
        for path in self.files(grid, cache_dir):
            for name, year, _ in gave_pixels(path):
                names.add(name)
                years.add(year)
        info["source_files"] = sorted(names)
        info["survey_years"] = [min(years), max(years)] if years else info["survey_years"]
        return info

    def used_entries(self, grid: Grid, cache_dir: str, wrote: Optional[Dict[str, bool]] = None) -> List[Dict]:
        """used() alone, or, with level credits, one entry for the sheets of the other levels and one per level of
        its own credit whose sheets gave the mosaic a pixel (wrote: prepare_layer's; None: every file over the
        grid), each with its credit, named "<description>, <label>". Nothing used: one entry without a credit."""
        if not self.level_credits:
            return [self.used(grid, cache_dir)]
        files = self.files(grid, cache_dir)
        gave = [p for p in files if wrote is None or wrote.get(p)]
        if not gave:
            info = self.used(grid, cache_dir)
            info.pop("credit", None)
            return [info]
        cache.touch(cache_dir, files)  # every file over the grid was read
        level_of = {}
        for path in gave:
            parts = re.split(r"[\/]", cache.relative(cache_dir, path))
            depth = len(self.folder.split("/"))
            level_of[path] = parts[depth] if len(parts) > depth and parts[depth] in self.level_credits else ""
        entries = []
        for level in [""] + list(self.level_credits):
            paths = [p for p in gave if level_of[p] == level]
            if not paths:
                continue
            names, years = set(), set()
            for path in paths:
                for name, year, _ in gave_pixels(path):
                    names.add(name)
                    years.add(year)
            label, credit = self.level_credits.get(level, (None, self.credit))
            entry = {"layer": self.description if label is None else f"{self.description}, {label}",
                     "folder": self.folder, "files": len(paths), "fetched": cache.touch(cache_dir, paths),
                     "paths": sorted(cache.relative(cache_dir, p) for p in paths), "source_files": sorted(names),
                     "survey_years": [min(years), max(years)] if years else None}
            if credit is not None:
                entry["credit"] = credit.as_dict()
            entries.append(entry)
        return entries
