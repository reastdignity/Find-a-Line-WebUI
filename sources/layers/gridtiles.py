"""GridTiles: our own tiles on a fixed grid (Slovakia), from a local mirror or a remote copy."""

import hashlib
import json
import math
import os
import re
from typing import Dict, List, Optional

from rasterio.warp import transform_bounds

from grid import Grid

from .. import net
from ..net import _part
from ..layer import Fetched, Layer


def grid_tile_name(i: int, j: int, block: int = 10) -> str:
    """Path of tile (i, j) of a GridTiles layer: blocks of block x block tiles per folder
    (shared with tools/sk_tiles.py, which makes the tiles)."""
    return f"{i // block}_{j // block}/{i}_{j}.tif"


# The folder above the local copies of our own tiles (tools/sk_tiles.py writes them in the
# layout of the Hugging Face dataset, e.g. <mirror>/slovakia/dmr5/1m/...)
MIRROR_ENV = "FINDALINE_MIRROR"


class GridTiles(Layer):
    """Square tiles on a fixed grid in a metric CRS, our own hosted tiles (tools/sk_tiles.py),
    as <base>/<grid_tile_name>.

    The bases are tried in turn: the local mirror first (<FINDALINE_MIRROR>/<mirror>, when
    that folder exists), then the URLs. A mirror is copied from like a server: its
    index.json says which tiles exist (null: outside the data, recorded as missing) and
    their sha256; a tile not in the index is not cut yet and is looked for further. Over
    HTTP a tile that the server does not have (404) is outside the data.
    Tile (i, j) covers [i, i + 1) x [j, j + 1) tile sizes in the CRS.
    """

    def __init__(self, description: str, urls: List[str], crs: str, folder: str, tile_m: float,
                 native_res: float, bytes_per_tile: float, mirror: Optional[str] = None):
        self.description, self.urls, self.crs, self.folder = description, urls, crs, folder
        self.tile_m, self.native_res, self._bytes, self.mirror = tile_m, native_res, bytes_per_tile, mirror
        self._indexes: Dict[str, Dict] = {}

    def bases(self) -> List[str]:
        """Where the tiles come from, in order (the mirror is read from the environment now,
        so a worker process sees the same as the app)."""
        root = os.environ.get(MIRROR_ENV)
        local = os.path.join(root, *self.mirror.split("/")) if root and self.mirror else None
        return ([local] if local and os.path.isdir(local) else []) + list(self.urls)

    def unavailable(self) -> Optional[str]:
        if self.bases():
            return None
        where = (f"{os.environ[MIRROR_ENV]}/{self.mirror} does not exist" if os.environ.get(MIRROR_ENV)
                 else f"set {MIRROR_ENV} to the folder holding {self.mirror} (made by tools/sk_tiles.py)")
        return f"{self.description}: no copy of the tiles is set up ({where})"

    def tiles(self, grid: Grid):
        left, bottom, right, top = transform_bounds(grid.crs, self.crs, *grid.bounds)
        shape = None
        if grid.area_shape is not None:
            from area import project
            shape = project(grid.area_shape, grid.crs, self.crs)
        found = []
        for j in range(math.floor(bottom / self.tile_m), math.floor(top / self.tile_m) + 1):
            for i in range(math.floor(left / self.tile_m), math.floor(right / self.tile_m) + 1):
                if shape is not None:
                    from shapely.geometry import box
                    if not shape.intersects(box(i * self.tile_m, j * self.tile_m,
                                                (i + 1) * self.tile_m, (j + 1) * self.tile_m)):
                        continue
                found.append((i, j))
        return found

    def tile_path(self, cache_dir: str, tile) -> str:
        return os.path.join(cache_dir, self.folder, grid_tile_name(*tile))

    def bytes_per_tile(self) -> float:
        return self._bytes

    def _index(self, base: str) -> Dict:
        """The tiles of a local mirror (read once; {} while it has no index)."""
        if base not in self._indexes:
            path, tiles = os.path.join(base, "index.json"), {}
            if os.path.exists(path):
                with open(path, encoding="utf-8") as f:
                    tiles = json.load(f)["tiles"]
            self._indexes[base] = tiles  # whole: the download threads read it meanwhile
        return self._indexes[base]

    def _copy(self, base: str, tile, path: str) -> Optional[Fetched]:
        """Copy a tile from a local mirror; None if it is not cut there yet."""
        key = f"{tile[0]}_{tile[1]}"
        index = self._index(base)
        if key not in index:
            return None
        source = os.path.join(base, *grid_tile_name(*tile).split("/"))
        if index[key] is None:
            return Fetched(0, source)  # not in the data
        with open(source, "rb") as f:
            data = f.read()
        if hashlib.sha256(data).hexdigest() != index[key]:
            raise RuntimeError(f"{source} does not match the sha256 in its index.json (cut it again)")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = _part(path)
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
        return Fetched(len(data), source)

    def tile_url(self, tile) -> Optional[str]:
        bases = self.bases()
        return bases[0] if bases else None  # a local mirror first: no host

    def download_tile(self, tile, path: str) -> Fetched:
        name, error = grid_tile_name(*tile), None
        for base in self.bases():  # the first that has it
            if not re.match(r"https?://", base):
                fetched = self._copy(base, tile, path)
                if fetched is not None:
                    return fetched
                error = f"not in {base} yet"
                continue
            url = f"{base}/{name}"
            try:
                response = net._get(url)
            except RuntimeError as e:
                error = e
                continue
            if response is None:
                return Fetched(0, url)  # not in the data
            os.makedirs(os.path.dirname(path), exist_ok=True)
            tmp = _part(path)
            with open(tmp, "wb") as f:
                f.write(response.content)
            os.replace(tmp, path)
            return Fetched.of(response, url)
        raise RuntimeError(f"Could not download {self.description} tile {name}: {error or self.unavailable()}")
