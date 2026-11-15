"""S3SheetSets: map sheets as ZIP files in an open S3 bucket, listed by ListObjectsV2, several files per sheet
(surveys of different years, two deliveries of one year) composed newest first (VIRTUAL SHIZUOKA's LP grids)."""

import json
import os
import re
import threading
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from rasterio.warp import transform_bounds

import cache
import osm
from grid import Grid

from ..credit import Credit
from ..indexes.cached import CachedIndex
from ..indexes.s3listing import MAX_KEYS, S3Object, S3Objects, common_prefixes, list_objects
from ..indexes.sheetsets import SheetSets
from ..indexes.tilings import MetricCellTiling
from ..net import _part, tile_lock
from ..readers.sheetfile import ListedFileMissing
from ..readers.sheetsets import SheetSetFile, gave_pixels
from .indexed import IndexedTiles
from .s3blocks import Box

# What a listed key is: (survey year, level, cell (i, j)); None: not a file of the layer
KeyParser = Callable[[str], Optional[Tuple[int, str, Tuple[int, int]]]]
# Days the bucket's list of survey folders is kept (cached in the index's folder, folders.json): a worker that runs
# for weeks sees a new survey within a week
FOLDERS_TTL_DAYS = 7


class _SheetListing(S3Objects):
    """S3Objects whose items are made against the tile's box computed once per tile (its projection took 0.2 ms
    a key, about 9 of a cold tile's 21-26 s, 2026-11-15) and stamped with the time of the listing."""

    def __init__(self, layer: "S3SheetSets", max_keys: int):
        super().__init__(layer.bucket, layer._prefixes, layer._item, max_keys)
        self.layer = layer

    def fetch(self, lat: float, lon: float) -> Dict:
        box = self.layer._box(lat, lon)
        listed = datetime.now(timezone.utc).isoformat(timespec="seconds")
        items: Dict[str, Dict] = {}
        for prefix in self.layer._prefixes_of(box):
            for obj in list_objects(self.url, prefix, self.max_keys):
                item = self.layer._item_in(obj, box, listed)
                if item is not None:
                    items.setdefault(item["url"], item)
        return {"sheets": list(items.values())}


class S3SheetSets(IndexedTiles):
    """Sheets of one or more levels (levels: name -> MetricCellTiling, the cells of each size and their names), each
    composed from every file the bucket holds for it (SheetSets, read by SheetSetFile): the newest survey first, an
    older one only while the sheet has holes, the fuller of two files of one survey first.

    The bucket's top folders matching `folders` (one per survey, e.g. "2019/") are found by one delimiter listing,
    kept FOLDERS_TTL_DAYS in the index's folder; the listing of a 0.25° tile asks prefixes(folder, box) under each (box: the tile in crs) and
    keeps the keys parse(key) knows whose sheet meets the tile, with their size; a file's ETag is part of its
    name, so a file uploaded again in place changes its sheet's key, which is read again (update.py, or a search
    after the cached answer was renewed). A listed file the bucket no longer has (404: removed or renamed) is an
    error of its sheet, and the cached index answers of the sheet's tiles are dropped, so the next search lists
    them again. The estimate counts the listed bytes of each sheet's newest survey (older surveys read for holes
    are not in it); without a listing, bytes_per_tile a sheet."""

    def __init__(self, description: str, bucket: str, folders: str,
                 prefixes: Callable[[str, Box], Sequence[str]], parse: KeyParser, prefix: str, folder: str,
                 crs: str, native_res: float, levels: Dict[str, MetricCellTiling], members: str,
                 bytes_per_tile: float, max_keys: int = MAX_KEYS,
                 level_credits: Optional[Dict[str, Tuple[str, Credit]]] = None, credit: Optional[Credit] = None,
                 splits: Optional[Dict[str, Sequence[int]]] = None):
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
        self.index = CachedIndex(description, _SheetListing(self, max_keys),
                                 SheetSets(folder, crs, native_res, levels, splits), prefix, folder.split("/")[0])
        self.reader = SheetSetFile(description, members)
        self._folders_lock = threading.Lock()

    def folders_path(self, cache_dir: str) -> str:
        """The cached list of the survey folders, beside the index's answers."""
        return os.path.join(os.path.dirname(self.index.index_path(cache_dir, 0.0, 0.0)), "folders.json")

    def survey_folders(self) -> List[str]:
        """The bucket's top folders of the surveys: one delimiter listing, kept FOLDERS_TTL_DAYS in the data folder
        (folders.json beside the index's answers; without a data folder, asked each time)."""
        cache_dir = self.index.cache_dir
        if cache_dir is None:
            return [p for p in common_prefixes(self.bucket, "") if re.fullmatch(self.folders_pattern, p)]
        path = self.folders_path(cache_dir)
        with self._folders_lock, tile_lock(cache_dir, path):
            if cache.due(cache_dir, path, update="stale", ttl=FOLDERS_TTL_DAYS):  # also without an update
                folders = [p for p in common_prefixes(self.bucket, "") if re.fullmatch(self.folders_pattern, p)]
                os.makedirs(os.path.dirname(path), exist_ok=True)
                tmp = _part(path)
                with open(tmp, "w", encoding="utf-8") as out:
                    json.dump({"folders": folders}, out)
                os.replace(tmp, path)
                cache.record(cache_dir, path, url=self.bucket)
            with open(path, encoding="utf-8") as f:
                return list(json.load(f)["folders"])

    def _box(self, lat: float, lon: float) -> Box:
        """A 0.25° tile in crs."""
        return transform_bounds("EPSG:4326", self.crs, lon, lat, lon + osm.TILE_DEG, lat + osm.TILE_DEG,
                                densify_pts=21)

    def _prefixes(self, lat: float, lon: float) -> Sequence[str]:
        return self._prefixes_of(self._box(lat, lon))

    def _prefixes_of(self, box: Box) -> Sequence[str]:
        return [p for folder in self.survey_folders() for p in self.prefixes(folder, box)]

    def _item(self, obj: S3Object, lat: float, lon: float) -> Optional[Dict]:
        return self._item_in(obj, self._box(lat, lon), "")

    def _item_in(self, obj: S3Object, box: Box, listed: str) -> Optional[Dict]:
        """A listed file as cached ({name, url, level, cell, year, size, modified, listed}), or None if it is not
        the layer's or its sheet does not meet the tile's box (in crs)."""
        parsed = self.parse(obj.key)
        if parsed is None:
            return None
        year, level, cell = parsed
        left, bottom, right, top = self.levels[level].edges(cell)
        b_left, b_bottom, b_right, b_top = box
        if not (left < b_right and right > b_left and bottom < b_top and top > b_bottom):
            return None
        stem = obj.key.rsplit("/", 1)[-1].rsplit(".", 1)[0]
        return {"name": f"{year}_{stem}@{obj.etag[:8]}", "url": f"{self.bucket.rstrip('/')}/{obj.key}",
                "level": level, "cell": list(cell), "year": year, "size": obj.size, "modified": obj.last_modified,
                "listed": listed}

    def _download_and_record(self, tile, cache_dir: str, update: Optional[str] = None,
                             if_due: bool = False, role: str = "other") -> int:
        """As every layer's; a listed file the bucket no longer has (404) drops the cached index answers of the
        sheet's 0.25 degree tiles, so the next search lists them again, and stays this sheet's error."""
        try:
            return super()._download_and_record(tile, cache_dir, update, if_due, role)
        except ListedFileMissing as e:
            west, south, east, north = transform_bounds(self.crs, "EPSG:4326",
                                                        *self.levels[tile.level].edges((tile.i, tile.j)))
            paths = [self.index.index_path(cache_dir, lat, lon) for lat, lon in osm.tiles(west, south, east, north)]
            cache.forget(cache_dir, paths)
            raise ListedFileMissing(f"{e}; the cached index answers of its {len(paths)} tile(s) were dropped, the "
                                    f"next search lists them again") from e

    def has_data_near(self, lat: float, lon: float, cache_dir: str, metres: float = 2000) -> Optional[bool]:
        return self.index.versions.has_data_near(self.index, lat, lon, cache_dir, metres)

    def estimate(self, grid: Grid, cache_dir: str, update: Optional[str]) -> Tuple[int, int, float]:
        """(sheets, sheets to download, MB): the listed bytes of each missing sheet's newest survey (an older one
        is read only for holes)."""
        self._use(cache_dir, update)
        sheets = self.tiles(grid)
        if sheets is None:  # no listing: the cached sheets only, nothing to download
            return len(self.index.cached(grid, cache_dir)), 0, 0.0
        missing = self.missing(grid, cache_dir, update)
        # the listed bytes of each sheet's newest survey (sheets listed without a size: bytes_per_tile); older
        # surveys read for holes are not in it
        return len(sheets), len(missing), sum(s.bytes or self.bytes_per_tile() for s in missing) / 1e6

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
