"""TileBases: our own tiles (tools/sk_tiles.py, tools/mirror_tiles.py) from a local mirror folder or the project's data
server (docs/mirror-hosting/spec.md, solution C), the first base that has them."""

import hashlib
import json
import os
import re
import threading
import time
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlsplit

import cache

from .. import net
from ..net import _part
from ..layer import Fetched
from ..composed import Reader

# The folder above the local copies of our own tiles (tools/sk_tiles.py writes them in the
# layout of the data server, e.g. <mirror>/slovakia/dmr5/1m/...)
MIRROR_ENV = "FINDALINE_MIRROR"
# The project's data server (deploy/mirror): its origin only; a dataset's tiles are at
# <origin>/v1/tiles/<mirror folder>. FINDALINE_MIRROR_URL overrides it; an empty value turns it off
MIRROR_URL = "https://mirror.findaline.lukawski.org"
MIRROR_URL_ENV = "FINDALINE_MIRROR_URL"
TILES_PATH = "v1/tiles"
MIRROR_TIMEOUT = (10, 300)  # a request to a remote base: seconds to connect, seconds for each read
REACH_TIMEOUT = (10, 20)    # the start check (reach): seconds to connect, seconds for each read
REACH_ATTEMPTS = 2          # the start check's attempts (net._get's retries)
INDEX_SECONDS = 300         # how long a remote index is kept in memory (never stored)
UNANSWERED_SECONDS = 60     # how long a start check that got no answer is remembered (for later start checks only)
HEAL_PAUSE = 2              # net._sleep's attempt before the index is taken again (2-6 s): a dataset being swapped


def mirror_url() -> Optional[str]:
    """The data server's origin (MIRROR_URL, or FINDALINE_MIRROR_URL when set); None when that is empty."""
    return os.environ.get(MIRROR_URL_ENV, MIRROR_URL).strip().rstrip("/") or None


def _clock() -> float:
    """The clock of the kept indexes and of the remembered failures (patched by the tests)."""
    return time.monotonic()


def _is_remote(base: str) -> bool:
    return bool(re.match(r"https?://", base))


def grid_tile_name(i: int, j: int, block: int = 10) -> str:
    """Path of tile (i, j) of a GridTiles layer: blocks of block x block tiles per folder
    (shared with tools/sk_tiles.py, which makes the tiles)."""
    return f"{i // block}_{j // block}/{i}_{j}.tif"


def _key_extent(tiles: Dict, partial: bool) -> Optional[Tuple[int, int, int, int]]:
    """The rectangle of an index's keys (i0, j0, i1, j1); None without keys or for a "partial" index."""
    if not tiles or partial:
        return None
    i, j = zip(*(map(int, key.split("_")) for key in tiles))
    return min(i), min(j), max(i), max(j)


OUTSIDE = object()  # _listed: the tile is outside the data (null, or beyond a complete index's extent)


def _listed(tiles: Dict, extent, tile):
    """What an index says of a tile: its sha256, OUTSIDE, or None when it does not list it (not cut yet)."""
    key = f"{tile[0]}_{tile[1]}"
    if key in tiles:
        return OUTSIDE if tiles[key] is None else tiles[key]
    if extent is not None and not (extent[0] <= tile[0] <= extent[2] and extent[1] <= tile[1] <= extent[3]):
        return OUTSIDE
    return None


class IndexMissing(RuntimeError):
    """A remote base answered 404 for its index.json (the dataset, or this resolution of it, is not published)."""


class _Kept:
    """The index of a remote base kept in memory: (tiles, extent, when) as one value, so a thread reading it
    without the lock sees a whole one; `generation` counts the fetches (a thread waiting on the lock takes the
    outcome of the fetch it waited for, its failure too)."""

    def __init__(self):
        self.lock = threading.Lock()
        self.index: Optional[Tuple[Dict, Optional[Tuple[int, int, int, int]], float]] = None
        self.generation = 0
        self.error: Optional[RuntimeError] = None

    def fresh(self) -> Optional[Tuple]:
        index = self.index
        return index if index is not None and _clock() - index[2] < INDEX_SECONDS else None


class TileBases(Reader):
    """Tiles (i, j) as <base>/<grid_tile_name>, the bases tried in turn: the local mirror folder first
    (<FINDALINE_MIRROR>/<mirror>, when that folder exists), then the data server
    (<mirror_url()>/v1/tiles/<mirror>), then the URLs. Every base is read as a mirror: its index.json says
    which tiles exist (null: outside the data, recorded as missing) and their sha256. It lists every tile of
    the dataset's extent (tools/sk_tiles.py: the national raster's 2 km rows and columns), so a tile beyond
    the rectangle of its keys is outside the data too, missing without a request (a country layer's
    footprint grown beyond the border reaches such tiles); a tile within it but not in the index is not cut
    yet and is looked for further, as is every tile not in an index that says "partial" (tools/sk_tiles.py
    while it cuts or averages: the rows not written yet lie beyond its keys).

    Over HTTP (docs/mirror-hosting/spec.md C.2) the index is fetched when a download first needs it (once
    for all threads: a lock per base) or by the start check (reach), kept in memory for INDEX_SECONDS; a
    listed tile is downloaded and its sha256 compared before the file is written. A 404 of a listed tile,
    a 404 of the index or a sha256 that does not match is an error, never "no data": after net._sleep's
    pause the index is taken again once and the tile once more (a dataset being swapped), then the next
    base is tried."""

    def __init__(self, description: str, urls: List[str], mirror: Optional[str] = None,
                 tool: str = "tools/sk_tiles.py"):
        self.description, self.urls, self.mirror = description, urls, mirror
        self.tool = tool  # what makes the mirror's tiles, named when they are missing
        self._indexes: Dict[str, Dict] = {}
        self._extents: Dict[str, Optional[Tuple[int, int, int, int]]] = {}
        self._kept: Dict[str, _Kept] = {}
        self._kept_lock = threading.Lock()
        self._unanswered: Dict[str, Tuple[float, str]] = {}  # base -> (when, why): reach's remembered failures

    def bases(self) -> List[str]:
        """Where the tiles come from, in order (the settings are read from the environment now,
        so a worker process sees the same as the app)."""
        root = os.environ.get(MIRROR_ENV)
        local = os.path.join(root, *self.mirror.split("/")) if root and self.mirror else None
        server = mirror_url()
        return (([local] if local and os.path.isdir(local) else [])
                + ([f"{server}/{TILES_PATH}/{self.mirror}"] if server and self.mirror else []) + list(self.urls))

    def unavailable(self) -> Optional[str]:
        if self.bases():
            return None
        where = (f"{os.environ[MIRROR_ENV]}/{self.mirror} does not exist" if os.environ.get(MIRROR_ENV)
                 else f"set {MIRROR_ENV} to the folder holding {self.mirror} (made by {self.tool})")
        return (f"{self.description}: no copy of the tiles is set up ({where}, and {MIRROR_URL_ENV}, the project's "
                f"data server, is empty)")

    # A local mirror folder

    def _index(self, base: str) -> Dict:
        """The tiles of a local mirror (read once; {} while it has no index), and the extent of
        its keys (i0, j0, i1, j1) in _extents (None: no keys, or a "partial" index)."""
        if base not in self._indexes:
            path, tiles, extent = os.path.join(base, "index.json"), {}, None
            if os.path.exists(path):
                with open(path, encoding="utf-8") as f:
                    index = json.load(f)
                tiles = index["tiles"]
                extent = _key_extent(tiles, index.get("partial"))
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

    # A remote base (the data server)

    def _kept_of(self, base: str) -> _Kept:
        with self._kept_lock:
            return self._kept.setdefault(base, _Kept())

    def _remote_index(self, base: str, used: Optional[int] = None, timeout=MIRROR_TIMEOUT,
                      retries: int = net.RETRIES) -> Tuple[Dict, Optional[Tuple[int, int, int, int]], int]:
        """(tiles, extent, generation) of a remote base's index: the kept one while it is fresh, else fetched
        (net._get: its rate turn, no host slot). used: the generation a thread found wrong (a tile's 404 or
        sha256): taken again unless another thread did so meanwhile. A thread that waited for another's fetch
        takes its outcome, its failure too (eight threads never pay a dead server eight times in a row).
        IndexMissing on a 404, RuntimeError when it cannot be had."""
        kept = self._kept_of(base)
        ticket = kept.generation
        with kept.lock:
            moved = kept.generation != ticket or (used is not None and kept.generation != used)
            if moved and kept.error is not None:
                raise kept.error
            index = kept.index if moved else (kept.fresh() if used is None else None)
            if index is not None:
                return index[0], index[1], kept.generation
            try:
                response = net._get(f"{base}/index.json", timeout=timeout, binary_types=("json",), retries=retries)
                if response is None:
                    raise IndexMissing(f"{cache.clean_url(base)}/index.json is not on the server (HTTP 404): this "
                                       f"dataset or resolution is not published there")
                try:
                    found = json.loads(response.content)
                    tiles = found["tiles"]
                except (ValueError, KeyError, TypeError) as e:
                    raise RuntimeError(f"{cache.clean_url(base)}/index.json cannot be read ({e})") from None
            except RuntimeError as e:
                kept.index, kept.error = None, e
                kept.generation += 1  # after the fetch: the threads that waited for it see that it moved
                raise
            kept.index, kept.error = (tiles, _key_extent(tiles, found.get("partial")), _clock()), None
            kept.generation += 1
            return kept.index[0], kept.index[1], kept.generation

    def _download(self, base: str, tile, path: str) -> Optional[Fetched]:
        """A tile from a remote base by its index: Fetched(0) outside the data (no request), None when the
        index does not list it (not cut yet: the next base), else downloaded and checked. A 404 of the tile or
        of the index, or a wrong sha256, takes the index again once after a pause; RuntimeError after that."""
        url, used, healed = f"{base}/{grid_tile_name(*tile)}", None, False
        while True:
            try:
                tiles, extent, used = self._remote_index(base, used)
                sha = _listed(tiles, extent, tile)
                if sha is OUTSIDE:
                    return Fetched(0, url)
                if sha is None:
                    return None
                response = net._get(url, timeout=MIRROR_TIMEOUT)
                if response is not None and hashlib.sha256(response.content).hexdigest() == sha:
                    os.makedirs(os.path.dirname(path), exist_ok=True)
                    tmp = _part(path)
                    with open(tmp, "wb") as f:
                        f.write(response.content)
                    os.replace(tmp, path)
                    return Fetched.of(response, url)
                problem = (f"{cache.clean_url(url)} is not on the server (HTTP 404), though its index lists it"
                           if response is None else f"{cache.clean_url(url)} does not match the sha256 of its index")
            except IndexMissing as e:
                problem, used = str(e), None
            if healed:
                raise RuntimeError(f"{problem}, also after taking the index again")
            healed = True
            net._sleep(HEAL_PAUSE)

    def remote_index(self, base: str) -> Tuple[Dict, Optional[Tuple[int, int, int, int]]]:
        """(tiles, extent) of a remote base's index, kept or fetched (the probe reads its first tile with data)."""
        tiles, extent, _ = self._remote_index(base)
        return tiles, extent

    def listed_empty(self, tile) -> bool:
        """Whether the kept index of the first base, a remote one, says a tile has no data (an estimate does
        not count it); False without a kept index, or for a local folder first."""
        bases = self.bases()
        kept = self._kept.get(bases[0]) if bases and _is_remote(bases[0]) else None
        index = kept.fresh() if kept is not None else None
        return index is not None and _listed(index[0], index[1], tile) is OUTSIDE

    def reach(self) -> Optional[str]:
        """Whether the data server answers (the start check of a search's first planning, an estimate, a country
        run's main process and the probe; docs/mirror-hosting/spec.md C.3): None when it does, or when the
        tiles are read from a local folder first (or there is no base at all: unavailable says why); else why
        not. Asks each remote base for its index.json (REACH_TIMEOUT, REACH_ATTEMPTS) unless a fresh one is
        kept: no HTTP answer, any 5xx and a 404 of the index are "does not answer", remembered for
        UNANSWERED_SECONDS for later start checks only; a 429 (busy) answers."""
        bases = self.bases()
        if not bases or not _is_remote(bases[0]):
            return None
        reasons = []
        for base in (b for b in bases if _is_remote(b)):
            why = self._reach(base)
            if why is None:
                return None
            reasons.append(why)
        return reasons[0]

    def _reach(self, base: str) -> Optional[str]:
        remembered = self._unanswered.get(base)
        if remembered is not None and _clock() - remembered[0] < UNANSWERED_SECONDS:
            return remembered[1]
        try:
            self._remote_index(base, timeout=REACH_TIMEOUT, retries=REACH_ATTEMPTS)
        except RuntimeError as e:
            status = getattr(e, "status", None)
            if status == 429:
                return None  # busy: it is there; the downloads' own retries deal with it
            detail = ("HTTP 404: not published there" if isinstance(e, IndexMissing) else
                      f"HTTP {status}" if status else "no answer")
            why = f"{self.description}: the data copy at {urlsplit(base).hostname} does not answer ({detail})"
            self._unanswered[base] = (_clock(), why)
            return why
        self._unanswered.pop(base, None)
        return None

    def url(self, tile) -> Optional[str]:
        bases = self.bases()
        return bases[0] if bases else None  # a local mirror first: no host

    def fetch(self, tile, path: str) -> Fetched:
        name, error = grid_tile_name(*tile), None
        for base in self.bases():  # the first that has it
            if not _is_remote(base):
                fetched = self._copy(base, tile, path)
                if fetched is not None:
                    return fetched
                error = f"not in {base} yet"
                continue
            try:
                fetched = self._download(base, tile, path)
            except RuntimeError as e:
                error = e
                continue
            if fetched is not None:
                return fetched
            error = f"not in {cache.clean_url(base)} yet"
        raise RuntimeError(f"Could not download {self.description} tile {name}: {error or self.unavailable()}")
