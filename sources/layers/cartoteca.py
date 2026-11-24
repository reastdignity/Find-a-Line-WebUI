"""CartotecaTiles: Tuscany's lidar sheets of Regione Toscana's cartoteca (sources/indexes/cartoteca.py,
sources/readers/cartoteca.py), each run credited by the owners of the sheets it used."""

import os
from typing import Dict, List, Optional

import rasterio as rio

import cache
from grid import Grid

from ..credit import Credit
from ..indexes.cached import CachedIndex
from ..indexes.cartoteca import CARTOTECA_CRS, CartotecaSheets, CartotecaVersions
from ..readers.cartoteca import OWNER_TAG, OWNERS, CartotecaFile, SheetUnresolved
from .indexed import IndexedTiles


def owner_of(path: str) -> str:
    """The owner a cached tile names (OWNER_TAG); MATTM, the stricter licence, when it names none."""
    with rio.open(path) as src:
        owner = src.tags().get(OWNER_TAG)
    return owner if owner in OWNERS else "MATTM"


class CartotecaTiles(IndexedTiles):
    """One model (kind "dtm" or "dsm") of the cartoteca's lidar: a CachedIndex of CartotecaSheets (its answers in
    <top>/sheet-index/<prefix>/, shared by the two models' layers: one GetFeature per 0.25° tile) with
    CartotecaVersions, read by CartotecaFile; the resolved URLs in urls_folder. A run records one entry of the
    data used per owner of the sheets it used (used_entries), each with its owner's credit (credits: owner ->
    Credit), named "<description>, <owner's label>"; its own credit is the Ministry's (the stricter)."""
    index_crs = CARTOTECA_CRS
    credits_by_pixels = True  # an owner is credited when its files gave a pixel (used_entries)

    def __init__(self, description: str, wms_url: str, typename: str, kind: str, prefix: str, folder: str,
                 urls_folder: str, credits: Dict[str, Credit], labels: Dict[str, str], bytes_per_tile: float = 5e6):
        super().__init__(description, wms_url, prefix, folder, 1.0, bytes_per_tile)
        self.typename, self.kind, self.urls_folder = typename, kind, urls_folder
        self.credits, self.labels = credits, labels
        # The layer's own credit (the about page, a file that names no owner): the stricter licence, the Ministry's;
        # a run records each owner's credit by the files it used (used_entries)
        self.credit = credits["MATTM"]
        self.index = CachedIndex(description, CartotecaSheets(wms_url, typename),
                                 CartotecaVersions(folder, kind, urls_folder), prefix, folder.split("/")[0])
        self.reader = CartotecaFile(description, wms_url, typename, kind)

    @staticmethod
    def _year(path: str) -> int:
        return int(os.path.basename(os.path.dirname(path)).split("-")[-1])  # <lotto>-<anno>/<sheet>.tif

    def used(self, grid: Grid, cache_dir: str) -> Dict:
        info = super(IndexedTiles, self).used(grid, cache_dir)
        years = [self._year(p) for p in self.files(grid, cache_dir)]
        info["survey_years"] = [min(years), max(years)] if years else None
        return info

    def used_entries(self, grid: Grid, cache_dir: str, wrote: Optional[Dict[str, bool]] = None) -> List[Dict]:
        """One entry per owner whose files gave the mosaic a pixel (wrote: prepare_layer's; None: every file over
        the grid), Regione Toscana's first, each with its credit: a Ministry's file under a newer survey, or
        whose buffer alone meets the grid, brings no CC BY-SA. Without such a file one entry without a credit
        (used(): the files over the grid)."""
        files = self.files(grid, cache_dir)
        gave = [p for p in files if wrote is None or wrote.get(p)]
        if not gave:  # nothing used: nobody to credit
            info = self.used(grid, cache_dir)
            info.pop("credit", None)
            return [info]
        cache.touch(cache_dir, files)  # every file over the grid was read
        owned: Dict[str, List[str]] = {}
        for path in gave:
            owned.setdefault(owner_of(path), []).append(path)
        entries = []
        for owner in OWNERS:
            paths = owned.get(owner)
            if not paths:
                continue
            years, checksums = [self._year(p) for p in paths], {}
            entries.append({"layer": f"{self.description}, {self.labels[owner]}", "folder": self.folder,
                            "files": len(paths), "fetched": cache.touch(cache_dir, paths, checksums),
                            "paths": sorted(cache.relative(cache_dir, p) for p in paths),
                            "survey_years": [min(years), max(years)], "credit": self.credits[owner].as_dict()})
            entries[-1]["identity"] = cache.identity_of(entries[-1]["paths"], checksums)
        return entries

    def _download_and_record(self, tile, cache_dir: str, update: Optional[str] = None,
                             if_due: bool = False, role: str = "other") -> int:
        """As every layer's, but a survey whose URL no GetFeatureInfo gives (SheetUnresolved) is left out of this
        search with a line and nothing recorded: the next search asks again."""
        try:
            return super()._download_and_record(tile, cache_dir, update, if_due, role)
        except SheetUnresolved as e:
            print(f"{self.description}: {e}; left out of this search")
            return 0
