"""Layer, one elevation model of a source cached in tiles, and the download of several layers at once."""

import math
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, NamedTuple, Optional, Sequence, Tuple

import numpy as np
import rasterio as rio

import cache
import servicecounts
from grid import Grid
from progress import progress

from .net import _part, host_slot, tile_lock
from .credit import Credit

DOWNLOAD_THREADS = 8  # tiles of one download (all its layers) at a time; each connection is slow
VALID_MIN = -500  # metres; anything lower is treated as "no data"


def _write_tile(path: str, band: np.ndarray, crs: str, transform, tags: Optional[Dict[str, str]] = None):
    """Save a float32 tile as a compressed GeoTIFF (atomically)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = _part(path)
    with rio.open(tmp, "w", driver="GTiff", height=band.shape[0], width=band.shape[1], count=1,
                  dtype="float32", crs=crs, transform=transform, nodata=np.nan,
                  compress="deflate", predictor=3, tiled=True) as dst:
        dst.write(band.astype(np.float32), 1)
        if tags:
            dst.update_tags(**tags)
    os.replace(tmp, path)


class Fetched(NamedTuple):
    """What a tile download got: bytes received (0: the service has no data there) and the source."""
    received: int
    url: Optional[str] = None
    etag: Optional[str] = None
    last_modified: Optional[str] = None

    @staticmethod
    def of(response, url: Optional[str] = None) -> "Fetched":
        return Fetched(len(response.content), url or response.url, response.headers.get("ETag"),
                       response.headers.get("Last-Modified"))


def _extent(path: str) -> Tuple[int, float]:
    """Pixels and km² of a cached tile from its header ((0, 0.0) when there is no file or it is not a
    raster), for the counts of the downloaded tiles (servicecounts.tiles)."""
    try:
        with rio.open(path) as src:
            pixels = src.width * src.height
            area = abs(src.transform.a * src.transform.e)
            if src.crs is not None and src.crs.is_geographic:  # degrees: their metres at the tile's latitude
                area *= 111_320.0 ** 2 * math.cos(math.radians((src.bounds.bottom + src.bounds.top) / 2))
            return pixels, pixels * area / 1e6
    except Exception:  # a tile outside the data (no file), or a file rasterio cannot read
        return 0, 0.0


def _clean(band: np.ndarray, zero_is_nodata: bool = False) -> np.ndarray:
    band = band.astype(np.float32)
    band[band < VALID_MIN] = np.nan
    if zero_is_nodata:
        band[band == 0.0] = np.nan
    return band


class Layer:
    """One elevation model of a source, cached in cache/<folder> (see cache.py)."""
    description = ""
    folder = ""
    credit: Optional[Credit] = None  # the source's, unless set for this layer (Source.__post_init__)
    # Correction (east, north) in metres of the layer CRS for data whose service is
    # georeferenced wrongly; applied when tiles are placed on the grid
    shift: Tuple[float, float] = (0.0, 0.0)
    # Version of what download_tile does with the data; tiles made by another version are fetched again
    processing = 1

    @property
    def ttl_days(self) -> Optional[int]:
        """Days between update checks; None for a release that never changes (see cache.py)."""
        return cache.TTL_DAYS["live"] if "/live" in self.folder else None

    def tiles(self, grid: Grid) -> list:
        raise NotImplementedError

    def tile_path(self, cache_dir: str, tile) -> str:
        raise NotImplementedError

    def bytes_per_tile(self) -> float:
        return 0

    def missing(self, grid: Grid, cache_dir: str, update: Optional[str]) -> list:
        """Tiles to download: not cached yet, or due for a check with update ("stale" or "all")."""
        return [t for t in self.tiles(grid)
                if cache.due(cache_dir, self.tile_path(cache_dir, t), self.processing, update, self.ttl_days)]

    def estimate(self, grid: Grid, cache_dir: str, update: Optional[str]) -> Tuple[int, int, float]:
        """(tiles, tiles to download, MB to download)."""
        missing = self.missing(grid, cache_dir, update)
        return len(self.tiles(grid)), len(missing), len(missing) * self.bytes_per_tile() / 1e6

    def download_tile(self, tile, path: str) -> Fetched:
        """Download one tile to path (received 0 and no file if the service has no data there)."""
        raise NotImplementedError

    def download(self, grid: Grid, cache_dir: str, update: Optional[str], label: str):
        download_layers([(self, label)], grid, cache_dir, update)

    def to_download(self, grid: Grid, cache_dir: str, update: Optional[str]) -> Tuple[list, Optional[str]]:
        """The tiles download_layers fetches, and the line saying how many there are (None: none)."""
        todo = self.missing(grid, cache_dir, update)
        total = len(self.tiles(grid))
        return todo, f"{self.description}: {total} tiles ({total - len(todo)} cached, {len(todo)} to download)"

    def downloaded(self, grid: Grid, cache_dir: str):
        """What a layer does once its tiles are downloaded (IndexedTiles: deletes older surveys)."""

    def tile_url(self, tile) -> Optional[str]:
        """Where a tile comes from, for the limit per host (host_slot); None: a local copy."""
        return None

    def unavailable(self) -> Optional[str]:
        """Why this layer cannot be used here (e.g. no copy of our own tiles is set up), or None."""
        return None

    def tile_of(self, path: str):
        """The tile of a cached file (path relative to the cache, with /), or None if it
        is not one of this layer's tiles. Used by update.py for data that can change."""
        return None

    def has_data_near(self, lat: float, lon: float, cache_dir: str) -> Optional[bool]:
        """Whether the layer has data near a point, when its index can tell (None: unknown)."""
        return None

    def _download_and_record(self, tile, cache_dir: str, update: Optional[str] = None,
                             if_due: bool = False, role: str = "other") -> int:
        """Download a tile under its lock (tile_lock) and a slot of its host (host_slot); with
        if_due only if it is still due then (another search may have just downloaded it). Counted
        for the monitoring (servicecounts.tiles, as `role`) where the web worker turned that on."""
        path = self.tile_path(cache_dir, tile)
        asked = time.monotonic()
        with tile_lock(cache_dir, path):
            if if_due and not cache.due(cache_dir, path, self.processing, update, self.ttl_days):
                servicecounts.tiles(self.folder, role, cached=1, waited=time.monotonic() - asked)
                return 0
            with host_slot(cache_dir, self.tile_url(tile)):
                started = time.monotonic()
                fetched = self.download_tile(tile, path)
                seconds = time.monotonic() - started
            # A tile outside the data (e.g. sea) is remembered as missing
            cache.record(cache_dir, path, "ok" if os.path.exists(path) else "missing", fetched.url,
                         fetched.etag, fetched.last_modified, self.source_date(tile), self.processing)
        if servicecounts.enabled():
            pixels, km2 = _extent(path)
            servicecounts.tiles(self.folder, role, 1, 0, pixels, km2, fetched.received, seconds,
                                started - asked)
        return fetched.received

    def source_date(self, tile) -> Optional[str]:
        """Date (or year) of the survey in the tile, when the service says it."""
        return None

    def files(self, grid: Grid, cache_dir: str) -> List[str]:
        return [p for p in (self.tile_path(cache_dir, t) for t in self.tiles(grid)) if os.path.exists(p)]

    def used(self, grid: Grid, cache_dir: str) -> Dict:
        """What a run records about the data it used (see runs.py)."""
        files = self.files(grid, cache_dir)
        info = {"layer": self.description, "folder": self.folder, "files": len(files),
                "fetched": cache.touch(cache_dir, files),
                "paths": sorted(cache.relative(cache_dir, p) for p in files)}
        if self.credit:
            info["credit"] = self.credit.as_dict()
        return info


def download_layers(layers: Sequence[Tuple[Layer, str]], grid: Grid, cache_dir: str,
                    update: Optional[str] = None):
    """Download what the layers (layer, label) miss over the grid in one pool of DOWNLOAD_THREADS,
    so a slow tile of one layer does not hold the others: one progress bar for all their tiles,
    a line per layer of how many it has. Each tile under its lock and a slot of its host
    (Layer._download_and_record), skipped when another search downloaded it meanwhile."""
    # The layers' indexes asked at the same time too (a WFS query of geoportal.gov.pl takes
    # seconds), each layer once; the lines in the order of the layers
    distinct = list({id(layer): layer for layer, _ in layers}.values())
    with ThreadPoolExecutor(max_workers=len(distinct)) as pool:
        listed = list(pool.map(lambda layer: layer.to_download(grid, cache_dir, update), distinct))
    roles = {id(layer): servicecounts.role_of(label) for layer, label in reversed(layers)}  # the first label's
    todo = []
    for layer, (tiles, line) in zip(distinct, listed):
        if line:
            print(line)
        todo += [(layer, tile) for tile in tiles]
        if servicecounts.enabled():  # the tiles found in the cache (the index may be unreachable: None)
            servicecounts.tiles(layer.folder, roles[id(layer)], cached=len(layer.tiles(grid) or []) - len(tiles))
    if todo:
        labels = list(dict.fromkeys(label for layer, label in layers if any(t[0] is layer for t in todo)))
        progress.download.start(f"{', '.join(labels)} tiles", len(todo), unit="tile")
        received = 0
        pool = ThreadPoolExecutor(max_workers=DOWNLOAD_THREADS)
        try:
            futures = [pool.submit(layer._download_and_record, tile, cache_dir, update, True, roles[id(layer)])
                       for layer, tile in todo]
            for future in as_completed(futures):
                received += future.result()
                progress.download.update(1, MB=f"{received / 1e6:.0f}")
        finally:
            pool.shutdown(cancel_futures=True)  # after an error: the tiles not started yet are not
        progress.download.finish(f"{received / 1e6:.0f} MB")
    for layer, _ in layers:
        layer.downloaded(grid, cache_dir)


def _hemi(value: int, positive: str, negative: str, digits: int) -> str:
    return f"{positive if value >= 0 else negative}{abs(value):0{digits}d}"
