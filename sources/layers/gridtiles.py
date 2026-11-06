"""GridTiles: our own tiles on a fixed grid (Slovakia), from a local mirror or a remote copy, at the
native resolution or averaged to a coarser one the tiles are kept at too."""

import math
import re
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from grid import Grid

from ..composed import ComposedLayer, Index, Reader
from ..indexes.tilings import MetricTiling
from ..readers.tilebases import TileBases
from ..layer import Fetched


def res_name(res: float) -> str:
    """The name of a resolution in the folders of the tiles ("1m", "2m", "0.5m")."""
    return f"{res:g}m"


def _same(a: str, b: str) -> bool:
    """Are two CRS (as a grid names them) the same?"""
    if str(a) == str(b):
        return True
    from rasterio.crs import CRS
    return CRS.from_user_input(a) == CRS.from_user_input(b)


def renamed(text: str, native: float, res: float) -> str:
    """text (a cache folder, a mirror folder, a URL) with its one name of the native resolution
    replaced by that of res: "slovakia/dmr5/5.0/epsg8353-1m-2km" -> "...-2m-2km",
    "slovakia/dmr5/1m" -> "slovakia/dmr5/2m". The name must stand alone (between separators)
    exactly once."""
    pattern = rf"(?<![\w.]){re.escape(res_name(native))}(?![\w.])"
    if len(re.findall(pattern, text)) != 1:
        raise ValueError(f"{text!r} does not name the resolution {res_name(native)} exactly once")
    return re.sub(pattern, res_name(res), text)


class GridResolutions(Index):
    """One MetricTiling per resolution the tiles are kept at (the native, and the averaged ones):
    a grid of the tiles' CRS at exactly one of them reads that resolution's tiles when they are
    available (`available(res)`: the mirror or a URL has them), any other grid the native ones. A
    grid of another CRS (a neighbour's, filling its border gaps) never reads the averaged tiles:
    the mosaic would reproject them bilinearly, as data of its own resolution (averaged, then
    smoothed: on Poland's 2 m grid in the Tatras 12 % of the Slovak side's spots were lost, 4 %
    with the native tiles averaged by the mosaic; docs/performance.md, "The resampling of a
    neighbour's data"). A tile is (res, i, j), cached in the folder of its resolution."""

    def __init__(self, crs: str, folders: Dict[float, str], tile_m: float, available: Callable[[float], bool]):
        self.tilings = {res: MetricTiling(crs, folder, tile_m) for res, folder in folders.items()}
        self.native = min(self.tilings)
        self.available = available
        self.crs = crs

    def resolution(self, grid_res: float, grid_crs: Optional[str] = None) -> float:
        """The resolution of the tiles a grid reads (grid_crs None: a grid of the tiles' CRS)."""
        if grid_crs is not None and not _same(grid_crs, self.crs):
            return self.native
        for res in self.tilings:
            if res != self.native and math.isclose(res, grid_res) and self.available(res):
                return res
        return self.native

    def tiles(self, grid: Grid) -> list:
        res = self.resolution(grid.res, grid.crs)
        return [(res, i, j) for i, j in self.tilings[res].tiles(grid)]

    def path(self, cache_dir: str, tile) -> str:
        return self.tilings[tile[0]].path(cache_dir, tile[1:])

    def bounds_wgs84(self, tile) -> Tuple[float, float, float, float]:
        return self.tilings[tile[0]].bounds_wgs84(tile[1:])


class ResolutionBases(Reader):
    """The TileBases of every resolution: a tile (res, i, j) is fetched from the bases of its
    resolution (the mirror's <product>/<res>m folder, the URLs' <res>m)."""

    def __init__(self, readers: Dict[float, TileBases], native: float):
        self.readers, self.native = readers, native

    def url(self, request) -> Optional[str]:
        return self.readers[request[0]].url(request[1:])

    def fetch(self, request, path: str) -> Fetched:
        return self.readers[request[0]].fetch(request[1:], path)

    def unavailable(self) -> Optional[str]:
        return self.readers[self.native].unavailable()


class GridTiles(ComposedLayer):
    """Square tiles on a fixed grid in a metric CRS, our own hosted tiles (tools/sk_tiles.py),
    as <base>/<grid_tile_name>: a MetricTiling read by TileBases (the local mirror first,
    then the URLs). Tile (res, i, j) covers [i, i + 1) x [j, j + 1) tile sizes in the CRS.

    averaged: factors (2, 5) of the native resolution the tiles are also kept at, each the block
    mean of the valid native pixels (tools/sk_tiles.py average, the rule of Download(average=)),
    in folders named by that resolution where the native ones are named "1m": the mirror's
    <product>/2m, the URLs' .../2m and the cache's ...-2m-... A grid of exactly that resolution
    reads them (a mosaic of them is the native tiles' averaged by GDAL, byte for byte: the
    pixels of a 2 km tile divide into whole blocks, and a working grid's edges lie on
    multiples of its resolution), any other grid the native tiles as before; a resolution the
    mirror or a URL does not have yet falls back to the native tiles too.
    """

    def __init__(self, description: str, urls: List[str], crs: str, folder: str, tile_m: float,
                 native_res: float, bytes_per_tile: float, mirror: Optional[str] = None,
                 averaged: Sequence[int] = ()):
        self.description, self.urls, self.crs, self.folder = description, urls, crs, folder
        self.tile_m, self.native_res, self._bytes, self.mirror = tile_m, native_res, bytes_per_tile, mirror
        self.averaged = tuple(averaged)
        if any(not isinstance(f, int) or f < 2 for f in self.averaged):
            raise ValueError(f"averaged must be integer factors above 1, not {averaged!r}")
        resolutions = [native_res] + [native_res * f for f in self.averaged]
        folders, readers = {}, {}
        for res in resolutions:
            at = (lambda text: text) if res == native_res else (lambda text: renamed(text, native_res, res))
            folders[res] = at(folder)
            readers[res] = TileBases(description, [at(url) for url in urls], at(mirror) if mirror else None)
        self.readers = readers
        self.index = GridResolutions(crs, folders, tile_m, lambda res: bool(readers[res].bases()))
        self.reader = ResolutionBases(readers, native_res)

    def bases(self) -> List[str]:
        """Where the native tiles come from, in order (see TileBases.bases)."""
        return self.readers[self.native_res].bases()

    def resolution(self, grid_res: float, grid_crs: Optional[str] = None) -> float:
        """The resolution of the tiles a grid of grid_res reads (the native, or an averaged one;
        a grid of another CRS than the tiles' always the native)."""
        return self.index.resolution(grid_res, grid_crs)
