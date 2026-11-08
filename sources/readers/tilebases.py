"""TileBases: our own tiles (tools/sk_tiles.py) from a local mirror or a remote copy, the first base that has them."""

import hashlib
import json
import os
import re
from typing import Dict, List, Optional, Tuple

from .. import net
from ..net import _part
from ..layer import Fetched
from ..composed import Reader

# The folder above the local copies of our own tiles (tools/sk_tiles.py writes them in the
# layout of the Hugging Face dataset, e.g. <mirror>/slovakia/dmr5/1m/...)
MIRROR_ENV = "FINDALINE_MIRROR"


def grid_tile_name(i: int, j: int, block: int = 10) -> str:
    """Path of tile (i, j) of a GridTiles layer: blocks of block x block tiles per folder
    (shared with tools/sk_tiles.py, which makes the tiles)."""
    return f"{i // block}_{j // block}/{i}_{j}.tif"


class TileBases(Reader):
    """Tiles (i, j) as <base>/<grid_tile_name>, the bases tried in turn: the local mirror first
    (<FINDALINE_MIRROR>/<mirror>, when that folder exists), then the URLs. A mirror is copied
    from like a server: its index.json says which tiles exist (null: outside the data,
    recorded as missing) and their sha256. It lists every tile of the dataset's extent
    (tools/sk_tiles.py: the national raster's 2 km rows and columns), so a tile beyond the
    rectangle of its keys is outside the data too, missing without a request (a country
    layer's footprint grown beyond the border reaches such tiles); a tile within it but not in
    the index is not cut yet and is looked for further, as is every tile not in an index that
    says "partial" (tools/sk_tiles.py while it cuts or averages: the rows not written yet lie
    beyond its keys). Over HTTP a tile that the server does not have (404) is outside the
    data."""

    def __init__(self, description: str, urls: List[str], mirror: Optional[str] = None):
        self.description, self.urls, self.mirror = description, urls, mirror
        self._indexes: Dict[str, Dict] = {}
        self._extents: Dict[str, Optional[Tuple[int, int, int, int]]] = {}

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

    def _index(self, base: str) -> Dict:
        """The tiles of a local mirror (read once; {} while it has no index), and the extent of
        its keys (i0, j0, i1, j1) in _extents (None: no keys, or a "partial" index)."""
        if base not in self._indexes:
            path, tiles, extent = os.path.join(base, "index.json"), {}, None
            if os.path.exists(path):
                with open(path, encoding="utf-8") as f:
                    index = json.load(f)
                tiles = index["tiles"]
                if tiles and not index.get("partial"):
                    i, j = zip(*(map(int, key.split("_")) for key in tiles))
                    extent = (min(i), min(j), max(i), max(j))
            self._extents[base] = extent  # before the index: a thread that sees the index sees its extent
            self._indexes[base] = tiles  # whole: the download threads read it meanwhile
        return self._indexes[base]

    def _beyond(self, base: str, tile) -> bool:
        """Whether a tile lies beyond the extent of a mirror's index (outside the data)."""
        extent = self._extents.get(base)
        return extent is not None and not (extent[0] <= tile[0] <= extent[2] and extent[1] <= tile[1] <= extent[3])

    def _copy(self, base: str, tile, path: str) -> Optional[Fetched]:
        """Copy a tile from a local mirror; None if it is not cut there yet."""
        key = f"{tile[0]}_{tile[1]}"
        index = self._index(base)
        source = os.path.join(base, *grid_tile_name(*tile).split("/"))
        if key not in index:
            return Fetched(0, source) if self._beyond(base, tile) else None  # beyond the data's extent: as null
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

    def url(self, tile) -> Optional[str]:
        bases = self.bases()
        return bases[0] if bases else None  # a local mirror first: no host

    def fetch(self, tile, path: str) -> Fetched:
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
