"""A layer composed of parts: an index (which tiles cover a grid and where each is cached) and
a reader (how one tile is fetched into the cache).

The parts (sources/indexes/, sources/readers/) know nothing of each other: the index turns a
tile into a request (by default the tile itself) and the reader fetches that request. The
layer classes of sources/layers/ build their parts in their constructors, keeping their
signatures and attributes; a new source combines existing parts, and a new kind of service
is one new part.
"""

import os
import time
from typing import Optional, Sequence, Tuple

import cache
import servicecounts
from grid import Grid

from .layer import Fetched, Layer, _extent, _write_tile
from .net import host_slot, tile_lock


class Index:
    """Which tiles of a layer cover a grid, and where each is cached."""

    def tiles(self, grid: Grid) -> list:
        """The tiles over a grid, in the order their data is used (the first wins)."""
        raise NotImplementedError

    def path(self, cache_dir: str, tile) -> str:
        """The cached file of a tile."""
        raise NotImplementedError

    def request(self, tile):
        """What the reader needs to fetch a tile (by default the tile itself)."""
        return tile

    def tile_of(self, path: str):
        """The tile of a cached file (relative to the cache, with /), or None (see Layer.tile_of)."""
        return None

    def bounds_wgs84(self, tile) -> Tuple[float, float, float, float]:
        """(west, south, east, north) of a tile."""
        raise NotImplementedError

    def has_data_near(self, lat: float, lon: float, cache_dir: str) -> Optional[bool]:
        """Whether there is data near a point, when the index can tell (None: unknown)."""
        return None


class Reader:
    """How one tile is fetched into the cache."""
    # The secrets its requests need (field names of settings.ServiceKeys; the layer's keys)
    keys: Tuple[str, ...] = ()
    # Whether the tiles it fetches are written by sources.layer._write_tile (so they may be converted to the
    # current encoding: Layer.rewrites); a reader that copies files (TileBases: the Slovak mirror's) does not
    rewrites = False

    def fetch(self, request, path: str) -> Fetched:
        """Fetch a tile (its index's request) to path; received 0 and no file where the service
        has no data."""
        raise NotImplementedError

    def url(self, request) -> Optional[str]:
        """Where a tile comes from, for the limit per host (net.host_slot); None: a local copy."""
        return None

    def unavailable(self) -> Optional[str]:
        """Why the reader cannot be used here, or None."""
        return None


class ComposedLayer(Layer):
    """A layer whose tiles come from an index and are fetched by a reader (set by the
    constructor of a subclass as `index` and `reader`)."""
    index: Index
    reader: Reader
    _bytes: float = 0  # the size of a tile, for estimates

    def tiles(self, grid: Grid) -> list:
        return self.index.tiles(grid)

    def tile_path(self, cache_dir: str, tile) -> str:
        return self.index.path(cache_dir, tile)

    def tile_of(self, path: str):
        return self.index.tile_of(path)

    def bounds_wgs84(self, tile) -> Tuple[float, float, float, float]:
        """(west, south, east, north) of a tile."""
        return self.index.bounds_wgs84(tile)

    def has_data_near(self, lat: float, lon: float, cache_dir: str) -> Optional[bool]:
        return self.index.has_data_near(lat, lon, cache_dir)

    def bytes_per_tile(self) -> float:
        return self._bytes

    def tile_url(self, tile) -> Optional[str]:
        return self.reader.url(self.index.request(tile))

    def download_tile(self, tile, path: str) -> Fetched:
        return self.reader.fetch(self.index.request(tile), path)

    @property
    def serial(self) -> bool:
        """Whether its reader reads range by range through GDAL's cache (Windows(serial=True)): download_layers
        hands its tiles to the pool in squares."""
        return getattr(self.reader, "serial", False)

    @property
    def rewrites(self) -> bool:
        """Whether its reader writes the cached tiles through _write_tile (see Reader.rewrites)."""
        return getattr(self.reader, "rewrites", False)

    @property
    def groups(self) -> bool:
        """Whether its tiles can be read in groups (a reader with fetch_group: Windows)."""
        return hasattr(self.reader, "fetch_group")

    def _download_group(self, tiles: Sequence, cache_dir: str, update: Optional[str] = None,
                        role: str = "other") -> int:
        """Download tiles of one CRS together (the reader's fetch_group, under one slot of their host and no tile's
        lock), then each under its lock (tile_lock) as _download_and_record records it, skipped when it is not
        due any more (another search may have just downloaded it). When the group cannot be read
        (RuntimeError), its tiles are downloaded one by one instead (their errors as ever). Counted for the
        monitoring per tile (servicecounts.tiles)."""
        requests = [self.index.request(tile) for tile in tiles]
        url = next((r.files[0][1] for r in requests if getattr(r, "files", None)), None)
        asked = time.monotonic()
        try:
            with host_slot(cache_dir, url):
                started = time.monotonic()
                results = self.reader.fetch_group(requests)
                seconds = (time.monotonic() - started) / max(len(tiles), 1)
        except RuntimeError as e:
            print(f"{self.description}: {len(tiles)} tiles one by one ({cache.clean_error(e)})")
            return sum(self._download_and_record(tile, cache_dir, update, True, role) for tile in tiles)
        received = 0
        for tile, request, (values, tags) in zip(tiles, requests, results):
            path = self.tile_path(cache_dir, tile)
            with tile_lock(cache_dir, path):
                if not cache.due(cache_dir, path, self.processing, update, self.ttl_days):
                    servicecounts.tiles(self.folder, role, cached=1)
                    continue
                size = 0
                if values is not None:
                    _write_tile(path, values, request.crs, request.transform, tags=tags)
                    size = os.path.getsize(path)
                fetched = Fetched(size, self.reader.url(request))
                cache.record(cache_dir, path, "ok" if os.path.exists(path) else "missing", fetched.url,
                             fetched.etag, fetched.last_modified, self.source_date(tile), self.processing)
            received += size
            if servicecounts.enabled():
                pixels, km2 = _extent(path)
                servicecounts.tiles(self.folder, role, 1, 0, pixels, km2, size, seconds, started - asked)
        return received

    @property
    def keys(self) -> Tuple[str, ...]:
        return self.reader.keys

    def unavailable(self) -> Optional[str]:
        return super().unavailable() or self.reader.unavailable()
