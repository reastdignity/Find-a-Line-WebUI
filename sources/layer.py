"""Layer, one elevation model of a source cached in tiles, and the download of several layers at once."""

import math
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Dict, List, NamedTuple, Optional, Sequence, Tuple

import numpy as np
import rasterio as rio

import cache
import servicecounts
import settings
from grid import Grid
from progress import progress

from .net import _part, host_slot, tile_lock
from .credit import Credit

DOWNLOAD_THREADS = 8  # tiles of one download (all its layers) at a time; each connection is slow
SERIAL_SQUARE = 4  # blocks a side of the squares of a serial layer, one task of the pool each
VALID_MIN = -500  # metres; anything lower is treated as "no data"


MAX_Z_ERROR = 0.005  # metres: the error bound of the tiles we write (LERC); None writes them lossless (deflate)
REPLACE_SECONDS = 30  # how long reencode retries replacing a tile that another process has open (Windows)


def _write_part(path: str, band: np.ndarray, crs, transform, tags: Optional[Dict[str, str]] = None,
                max_z_error: Optional[float] = MAX_Z_ERROR) -> str:
    """Write a float32 tile to a temporary file next to path (its .part) and return that file's name.
    The profile: GTiff, NaN for no data, tiles of 256 x 256 px, LERC_ZSTD within max_z_error metres (about 40 %
    smaller than deflate, measured on the cache); with max_z_error None deflate with predictor 3, lossless."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = _part(path)
    options = (dict(compress="deflate", predictor=3, tiled=True) if max_z_error is None else
               dict(compress="lerc_zstd", max_z_error=max_z_error, tiled=True, blockxsize=256, blockysize=256))
    with rio.open(tmp, "w", driver="GTiff", height=band.shape[0], width=band.shape[1], count=1,
                  dtype="float32", crs=crs, transform=transform, nodata=np.nan, **options) as dst:
        dst.write(band.astype(np.float32), 1)
        if tags:
            dst.update_tags(**tags)
    return tmp


def _write_tile(path: str, band: np.ndarray, crs: str, transform, tags: Optional[Dict[str, str]] = None,
                max_z_error: Optional[float] = MAX_Z_ERROR):
    """Save a float32 tile as a compressed GeoTIFF (atomically; see _write_part for the profile)."""
    os.replace(_write_part(path, band, crs, transform, tags, max_z_error), path)


def old_encoding(path: str) -> bool:
    """Whether a cached file is a GeoTIFF of one float band that is not LERC-compressed: the encoding our
    tiles had before _write_tile wrote LERC, and that of the providers' files kept as they came. Only the
    header is read; False for a file that is anything else, unreadable, an integer raster or a LERC one (the Slovak
    mirror's tiles). Whether the file is ours to rewrite is the layer's to say (Layer.rewrites)."""
    try:
        with rio.open(path) as src:
            if src.driver != "GTiff" or src.count != 1 or not np.issubdtype(np.dtype(src.dtypes[0]), np.floating):
                return False
            return not (src.tags(ns="IMAGE_STRUCTURE").get("COMPRESSION") or "").upper().startswith("LERC")
    except Exception:  # not a raster, or one rasterio cannot read: left as it is
        return False


def copied_tags(src) -> Dict[str, str]:
    """The tags of a raster to keep when it is written again (not AREA_OR_POINT: GDAL moves a PixelIsPoint
    file's transform by half a pixel when it reads it, so the transform it gives is for pixel areas already)."""
    return {k: v for k, v in src.tags().items() if k != "AREA_OR_POINT"}


def float_band(src) -> np.ndarray:
    """Band 1 of a raster as the mosaic reads it (sources.mosaic._read_band, then _clean): float32, NaN where it is
    masked (its nodata) or below VALID_MIN."""
    band = src.read(1, masked=True)
    values = band.data.astype(np.float32, copy=False)
    mask = np.ma.getmask(band)
    if mask is not np.ma.nomask:
        np.copyto(values, np.nan, where=mask)
    return _clean(values, copy=False)


_NEW: Dict[str, Tuple[int, int]] = {}  # per process: cached files seen not to be in the old encoding, (mtime, size)


def _signature(path: str) -> Optional[Tuple[int, int]]:
    try:
        st = os.stat(path)
        return st.st_mtime_ns, st.st_size
    except OSError:
        return None


def reencode(cache_dir: str, path: str) -> bool:
    """Write a cached tile of ours again in the current encoding (_write_tile's profile) if it is in the old one
    (old_encoding): under the tile's lock, so another process converting or downloading it waits and then finds
    it done; checked again under the lock. The values: the mosaic's own reading of the file (float_band), the CRS
    exactly as stored (a compound one too), the transform and the tags. The new file replaces the old one
    atomically; where another process has the old one open (Windows refuses) it is tried for REPLACE_SECONDS
    and then given up quietly: the old tile stays, as it was, and the next call converts it. The index row keeps
    its times and gets the file's new sha256 (cache.reencoded). True: converted now."""
    with tile_lock(cache_dir, path):
        if not old_encoding(path):  # converted by another process meanwhile, or gone
            _NEW[path] = _signature(path)
            return False
        try:
            with rio.open(path) as src:
                band, crs, transform, tags = float_band(src), src.crs, src.transform, copied_tags(src)
        except Exception:  # unreadable now: left as it is
            return False
        tmp = _write_part(path, band, crs, transform, tags)
        deadline = time.monotonic() + REPLACE_SECONDS
        while True:
            try:
                os.replace(tmp, path)
                break
            except PermissionError:
                if time.monotonic() > deadline:
                    os.remove(tmp)
                    return False
                time.sleep(0.2)
        cache.reencoded(cache_dir, path)
        _NEW[path] = _signature(path)
        return True


def reencode_paths(cache_dir: str, paths: Sequence[str], threads: int = 0, quiet: bool = False) -> Tuple[int, int]:
    """Reencode the cached tiles among paths that are in the old encoding, in a pool (results do not depend on
    the number of threads: a tile is converted on its own), a Download bar "re-encoding cached tiles" only when
    there are some. A file seen not to need it is not looked at again by this process while it stays as it was
    (_NEW). Returns (converted, left): left are tiles still in the old encoding, held open by another process."""
    todo = [p for p in paths if _NEW.get(p) is None or _NEW[p] != _signature(p)]
    if not todo:
        return 0, 0
    workers = max(1, threads or DOWNLOAD_THREADS)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        old = []
        for p, is_old in zip(todo, pool.map(old_encoding, todo)):
            if is_old:
                old.append(p)
            else:
                _NEW[p] = _signature(p)
        if not old:
            return 0, 0
        if not quiet:
            progress.download.start("re-encoding cached tiles", len(old), unit="tile")
        converted = 0
        for done in pool.map(lambda p: reencode(cache_dir, p), old):
            converted += done
            if not quiet:
                progress.download.update(1)
        if not quiet:
            progress.download.finish(f"{converted} converted")
        left = sum(pool.map(old_encoding, [p for p in old if _NEW.get(p) != _signature(p)]))
    return converted, left


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


def _clean(band: np.ndarray, zero_is_nodata: bool = False, copy: bool = True) -> np.ndarray:
    """The band as float32 with NaN below VALID_MIN (and at 0 with zero_is_nodata); copy False:
    in place when it is float32 already (an array of the caller's own)."""
    band = band.astype(np.float32, copy=copy)
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
    # The secrets the layer's service needs (field names of settings.ServiceKeys, read when used):
    # without them the layer is unavailable (unavailable), as a source without its mirror
    keys: Tuple[str, ...] = ()
    # Whether the cached files are ours to write again in the current encoding: they come from _write_tile (or
    # Download's float files); reencode / cache migrate convert those still in the old one
    rewrites = False

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
        tiles = self.tiles(grid)
        due = cache.due_many(cache_dir, [self.tile_path(cache_dir, t) for t in tiles], self.processing, update,
                             self.ttl_days)  # one connection to the index for all of them
        return [t for t, d in zip(tiles, due) if d]

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
        """Why this layer cannot be used here (e.g. no copy of our own tiles is set up, a key of
        its service not set), or None."""
        missing = settings.missing_keys(self.keys)
        return f"{self.description} needs a key of its service, {missing}" if missing else None

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


def each_layer(layers: Sequence[Layer], call: Callable[[Layer], Any]) -> list:
    """call(layer) of every layer, each in a thread of its own (what asks a layer's index, which
    may take seconds), each layer once: the answers in the order of `layers`."""
    distinct = list({id(layer): layer for layer in layers}.values())
    with ThreadPoolExecutor(max_workers=max(1, len(distinct))) as pool:
        answers = dict(zip(map(id, distinct), pool.map(call, distinct)))
    return [answers[id(layer)] for layer in layers]


def estimate_layers(layers: Sequence[Layer], grid: Grid, cache_dir: str,
                    update: Optional[str] = None) -> List[Tuple[int, int, float]]:
    """Layer.estimate of every layer over the grid, their indexes asked at the same time (as
    download_layers does): (tiles, tiles to download, MB) in the order of `layers`."""
    return each_layer(layers, lambda layer: layer.estimate(grid, cache_dir, update))


def squares(layer: Layer, tiles: Sequence, size_m: float) -> List[list]:
    """The tiles of a layer whose index makes block requests (sources/readers/windows.py) in squares of size_m
    on their CRS from 0, by the centres of their requests: each square's tiles in their order, the squares in the
    order of their first tile."""
    found: Dict[tuple, list] = {}
    for tile in tiles:
        r = layer.index.request(tile)
        x = r.transform.c + r.transform.a * r.shape[1] / 2
        y = r.transform.f + r.transform.e * r.shape[0] / 2
        found.setdefault((str(r.crs), math.floor(x / size_m), math.floor(y / size_m)), []).append(tile)
    return list(found.values())


def download_layers(layers: Sequence[Tuple], grid: Grid, cache_dir: str,
                    update: Optional[str] = None, group_m: Optional[float] = None,
                    on_error: Optional[Callable[[Layer, Sequence, Exception], None]] = None,
                    reencode_cached: bool = True):
    """Download what the layers (layer, label) miss over the grid in one pool of DOWNLOAD_THREADS,
    so a slow tile of one layer does not hold the others: one progress bar for all their tiles,
    a line per layer of how many it has. Each tile under its lock and a slot of its host
    (Layer._download_and_record), skipped when another search downloaded it meanwhile. An entry
    (layer, label, grid) takes that layer over a grid of its own instead (the country prefetch: the
    neighbours' tiles over the windows of the border tiles, in the same pool as the source's own); a
    layer named twice keeps its first grid.

    The tiles of a layer reading range by range (`serial`) go to the pool in squares of SERIAL_SQUARE x
    SERIAL_SQUARE, one task each, its tiles one after another: a tile shared by neighbours is then found in
    GDAL's cache of ranges. With group_m (the country prefetch), the tiles of the layers read by windows of big
    files (a layer whose `groups` is true) are downloaded in squares of group_m, each a task that reads every
    file once over its tiles (ComposedLayer._download_group): the same cached files with a fraction of the
    bytes and requests.

    The first task to fail stops the others. With on_error it gets (the layer, the task's tiles, the error) instead
    and the others go on (tools/area_download.py: weeks of tiles); what it raises stops them.

    Last, the tiles of the layers over the grid that are cached in the old encoding (Layer.rewrites,
    old_encoding) are written again in the current one (reencode_paths), so nothing that reads the cache after
    this call sees a tile of ours in the old encoding. Every search, the web worker's download phase, the quick
    lane and the country prefetch come through here; reencode_cached False (tools/area_download.py, which reads no tile)
    leaves it to whatever reads them."""
    # The layers' indexes asked at the same time too (a WFS query of geoportal.gov.pl takes
    # seconds), each layer once; the lines in the order of the layers
    entries = [(entry[0], entry[1], entry[2] if len(entry) > 2 else grid) for entry in layers]
    grids = {}
    for layer, _, own in entries:
        grids.setdefault(id(layer), own)
    layers = [(layer, label) for layer, label, _ in entries]
    distinct = list({id(layer): layer for layer, _ in layers}.values())
    listed = each_layer(distinct, lambda layer: layer.to_download(grids[id(layer)], cache_dir, update))
    roles = {id(layer): servicecounts.role_of(label) for layer, label in reversed(layers)}  # the first label's
    todo = []
    for layer, (tiles, line) in zip(distinct, listed):
        if line:
            print(line)
        todo += [(layer, tile) for tile in tiles]
        if servicecounts.enabled():  # the tiles found in the cache (the index may be unreachable: None)
            servicecounts.tiles(layer.folder, roles[id(layer)],
                                cached=len(layer.tiles(grids[id(layer)]) or []) - len(tiles))
    if todo:
        labels = list(dict.fromkeys(label for layer, label in layers if any(t[0] is layer for t in todo)))
        progress.download.start(f"{', '.join(labels)} tiles", len(todo), unit="tile")
        received = 0
        pool = ThreadPoolExecutor(max_workers=DOWNLOAD_THREADS)
        try:
            futures = {}
            for layer, tiles, kind in _tasks(todo, group_m):
                if kind == "group":
                    future = pool.submit(layer._download_group, tiles, cache_dir, update, roles[id(layer)])
                else:  # a tile, or a square of a serial layer's: one after another
                    future = pool.submit(_download_each, layer, tiles, cache_dir, update, roles[id(layer)])
                futures[future] = (layer, tiles)
            for future in as_completed(futures):
                layer, tiles = futures[future]
                try:
                    received += future.result()
                except Exception as e:
                    if on_error is None:
                        raise
                    on_error(layer, tiles, e)
                    continue
                progress.download.update(len(tiles), MB=f"{received / 1e6:.0f}")
        finally:
            pool.shutdown(cancel_futures=True)  # after an error: the tiles not started yet are not
        progress.download.finish(f"{received / 1e6:.0f} MB")
    for layer, _ in layers:
        layer.downloaded(grids[id(layer)], cache_dir)
    if reencode_cached:
        fetched = {layer.tile_path(cache_dir, tile) for layer, tile in todo}  # written in the current encoding
        paths = [p for layer in distinct if layer.rewrites for p in layer.files(grids[id(layer)], cache_dir)
                 if p not in fetched]
        reencode_paths(cache_dir, list(dict.fromkeys(paths)))


def _tasks(todo: Sequence[Tuple[Layer, Any]], group_m: Optional[float]) -> List[Tuple[Layer, list, str]]:
    """The tasks of download_layers' pool: (layer, tiles, kind), "tile" one tile each, "square" a serial layer's
    squares of SERIAL_SQUARE blocks, "group" with group_m the squares of the layers that read in groups (after
    the tiles' tasks, each layer's in the order of todo)."""
    tasks, by_layer = [], {}
    for layer, tile in todo:
        if group_m and getattr(layer, "groups", False):
            kind = "group"
        elif getattr(layer, "serial", False):
            kind = "square"
        else:
            tasks.append((layer, [tile], "tile"))
            continue
        by_layer.setdefault((id(layer), kind), (layer, kind, []))[2].append(tile)
    for layer, kind, tiles in by_layer.values():
        if kind == "group":
            size = group_m
        else:
            r = layer.index.request(tiles[0])
            size = abs(r.transform.a) * r.shape[1] * SERIAL_SQUARE
        tasks += [(layer, square, kind) for square in squares(layer, tiles, size)]
    return tasks


def _download_each(layer: Layer, tiles: Sequence, cache_dir: str, update: Optional[str], role: str) -> int:
    """Layer._download_and_record of the tiles, one after another."""
    return sum(layer._download_and_record(tile, cache_dir, update, True, role) for tile in tiles)


def _hemi(value: int, positive: str, negative: str, digits: int) -> str:
    return f"{positive if value >= 0 else negative}{abs(value):0{digits}d}"
