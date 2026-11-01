"""A layer composed of parts: an index (which tiles cover a grid and where each is cached) and
a reader (how one tile is fetched into the cache).

The parts (sources/indexes/, sources/readers/) know nothing of each other: the index turns a
tile into a request (by default the tile itself) and the reader fetches that request. The
layer classes of sources/layers/ build their parts in their constructors, keeping their
signatures and attributes; a new source combines existing parts, and a new kind of service
is one new part.
"""

from typing import Optional, Tuple

from grid import Grid

from .layer import Fetched, Layer


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
    def keys(self) -> Tuple[str, ...]:
        return self.reader.keys

    def unavailable(self) -> Optional[str]:
        return super().unavailable() or self.reader.unavailable()
