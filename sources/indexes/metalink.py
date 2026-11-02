"""Metalink indexes: the files of a download service listed in Metalink 4 documents (RFC 5854), a
document for a whole Land read once per TTL and kept, its files picked per 0.25° tile (MetalinkFiles),
and the version policy of files whose checksum is their version (ShaPerTile)."""

import glob
import gzip
import hashlib
import json
import os
import re
import xml.etree.ElementTree as ElementTree
from dataclasses import dataclass
from typing import Dict, List, NamedTuple, Optional, Sequence, Set, Tuple

import requests
from rasterio.warp import transform_bounds

import cache
import osm
import servicecounts
from grid import Grid

from .. import net
from ..net import _part
from .cached import CachedIndex, IndexUnavailable, Listing, Versions

# RFC 5854, section 4: the namespace of every element of a Metalink 4 document
METALINK_NS = "urn:ietf:params:xml:ns:metalink"
# The textual name of SHA-256 in IANA's "Hash Function Textual Names" registry (RFC 5854, section 4.2.7)
SHA256 = "sha-256"
# RFC 5854, section 4.2.16: "priority" values run from 1 to 999999, the lower the more preferred; a URL
# without one comes after those with one
NO_PRIORITY = 1_000_000


class MetalinkFile(NamedTuple):
    """One <file> of a Metalink document: its name, size (None if not given), SHA-256 (lower-case
    hex, None if not given) and URLs, the most preferred first."""
    name: str
    size: Optional[int]
    sha256: Optional[str]
    urls: Tuple[str, ...]


def _safe_name(name: str) -> bool:
    """RFC 5854, section 4.1.2.1: a file name "MUST NOT contain any directory traversal directives or
    information", nor be absolute; such a file is left out."""
    parts = name.replace("\\", "/").split("/")
    return bool(name) and not name.startswith(("/", "\\")) and ".." not in parts and ":" not in parts[0]


def parse_metalink(body: bytes) -> Tuple[Optional[str], List[MetalinkFile]]:
    """The `published` text and the files of a Metalink 4 document (RFC 5854, section 4), in the
    order of the document: of each <file name="..."> its <size>, the <hash type="sha-256"> and the
    <url>s by their "priority" (section 4.2.16; the document's order among equal ones). <metaurl>s
    (torrents and other Metalinks) and <pieces> are not used; a file without a <url> or with a
    name that is not safe (section 4.1.2.1) is left out. Raises ValueError when the body is no
    Metalink 4 document (an error page, a Metalink 3 document of another namespace)."""
    try:
        root = ElementTree.fromstring(body)
    except ElementTree.ParseError as e:
        raise ValueError(f"not XML ({e})") from e
    if root.tag != f"{{{METALINK_NS}}}metalink":
        raise ValueError(f"not a Metalink 4 document (root {root.tag})")
    ns = {"m": METALINK_NS}
    published = root.findtext("m:published", namespaces=ns)
    files = []
    for element in root.findall("m:file", ns):
        name = element.get("name", "")
        if not _safe_name(name):
            continue
        size = element.findtext("m:size", namespaces=ns)
        sha256 = next((h.text.strip().lower() for h in element.findall("m:hash", ns)
                       if (h.get("type") or "").lower() == SHA256 and h.text), None)
        urls = []
        for k, url in enumerate(element.findall("m:url", ns)):
            if url.text and url.text.strip():
                priority = url.get("priority")
                urls.append((int(priority) if priority and priority.isdigit() else NO_PRIORITY, k, url.text.strip()))
        if not urls:
            continue
        files.append(MetalinkFile(name, int(size) if size and size.strip().isdigit() else None, sha256,
                                  tuple(u for _, _, u in sorted(urls))))
    return (published.strip() if published else None), files


class MetalinkFiles(Listing):
    """The files of one or more Metalink documents (RFC 5854) that list a whole region (a Land's
    tiles), each file a square tile named by its corner: name, a regular expression of the file
    names with the groups east and north (in tile_m units of crs) and, if the names carry it, year.
    The documents are large (Bavaria's 22 MB), so they are not read per 0.25° tile: they are asked
    once per TTL ("sheet-index") for all, the files matching name kept in <top>/metalink/<key>.json.gz
    (cache.record), and each tile's answer (fetch) is picked from them. An update ("all") asks the
    documents again once per process. A document that cannot be had (an error answer, no Metalink)
    is IndexUnavailable; nothing is kept then.

    Every file is listed as {year (0 without one), godlo ("<east>_<north>"), url (the preferred),
    crs, res, sha256, size, extent}; a tile in several documents (Bavaria's Regierungsbezirke
    overlap) once. cache_dir and update are set by MetalinkIndex before each fetch."""

    def __init__(self, urls: Sequence[str], name: str, crs: str, res: float, top: str, key: str,
                 tile_m: float = 1000):
        self.urls, self.url = tuple(urls), urls[0]
        self.name, self.crs, self.res, self.top, self.key, self.tile_m = re.compile(name), crs, res, top, key, tile_m
        self.cache_dir: Optional[str] = None
        self.update: Optional[str] = None
        self._table: Optional[List[Dict]] = None
        self._asked = False  # the documents were asked in this process

    def table_path(self, cache_dir: str) -> str:
        return os.path.join(cache_dir, self.top, "metalink", f"{self.key}.json.gz")

    def _download(self) -> Dict:
        """The files of every document, as kept."""
        files: Dict[str, Dict] = {}
        published = []
        for url in self.urls:
            net.rate_turn(url)
            try:
                response = servicecounts.get(url, timeout=300, headers=cache.http_headers())
            except requests.RequestException as e:
                raise IndexUnavailable(f"Metalink {cache.clean_url(url)}: {e}") from e
            if response.status_code != 200:
                raise IndexUnavailable(f"Metalink {cache.clean_url(url)}: HTTP {response.status_code}")
            try:
                when, listed = parse_metalink(response.content)
            except ValueError as e:
                raise IndexUnavailable(f"Metalink {cache.clean_url(url)}: {e}") from e
            published.append(when)
            for f in listed:
                if self.name.search(f.name) and f.name not in files:
                    files[f.name] = {"name": f.name, "url": f.urls[0], "sha256": f.sha256, "size": f.size}
        return {"documents": list(self.urls), "published": published, "files": list(files.values())}

    def table(self) -> List[Dict]:
        """The kept files, asking the documents when not kept or due (at most once per process)."""
        cache_dir, ttl = self.cache_dir, cache.TTL_DAYS["sheet-index"]
        path = self.table_path(cache_dir)
        if not self._asked and cache.due(cache_dir, path, update=self.update, ttl=ttl):
            with net.tile_lock(cache_dir, path):  # another search may be asking now
                if cache.due(cache_dir, path, update=self.update, ttl=ttl):
                    kept = self._download()
                    os.makedirs(os.path.dirname(path), exist_ok=True)
                    tmp = _part(path)
                    with gzip.open(tmp, "wt", encoding="utf-8") as out:
                        json.dump(kept, out)
                    os.replace(tmp, path)
                    cache.record(cache_dir, path, url=self.url)
            self._asked, self._table = True, None
        if self._table is None:
            with gzip.open(path, "rt", encoding="utf-8") as kept_file:
                files = json.load(kept_file)["files"]
            self._table = [self._item(f) for f in files]
        return self._table

    def _item(self, f: Dict) -> Dict:
        match = self.name.search(f["name"])
        east, north = int(match.group("east")), int(match.group("north"))
        year = int(match.groupdict().get("year") or 0)
        return {"year": year, "godlo": f"{east}_{north}", "url": f["url"], "crs": self.crs, "res": self.res,
                "sha256": f["sha256"], "size": f["size"],
                "extent": [east * self.tile_m, north * self.tile_m, (east + 1) * self.tile_m, (north + 1) * self.tile_m]}

    def fetch(self, lat: float, lon: float) -> Dict:
        left, bottom, right, top = transform_bounds("EPSG:4326", self.crs, lon, lat, lon + osm.TILE_DEG,
                                                    lat + osm.TILE_DEG)
        return {"sheets": [item for item in self.table() if item["extent"][0] < right and item["extent"][2] > left
                           and item["extent"][1] < top and item["extent"][3] > bottom]}


class MetalinkIndex(CachedIndex):
    """A CachedIndex of MetalinkFiles: tells the listing the cache folder and update mode of each
    answer it asks for (the listing keeps its documents there)."""
    listing: MetalinkFiles

    def answers(self, cache_dir: str, lat: float, lon: float, update: Optional[str] = None) -> List[Dict]:
        self.listing.cache_dir, self.listing.update = cache_dir, update
        return super().answers(cache_dir, lat, lon, update)


@dataclass(frozen=True)
class ShaTile:
    """A square tile of a ShaPerTile layer: (east, north) in tile_m units of crs, of one survey year
    (0: not named) and content (key: the first characters of its SHA-256)."""
    east: int
    north: int
    year: int
    key: str
    url: str = ""
    sha256: Optional[str] = None
    size: Optional[int] = None

    @property
    def godlo(self) -> str:
        return f"{self.east}_{self.north}"


# A cached file of a ShaPerTile layer: <east // 10>_<north // 10>/<east>_<north>[_<year>]_<key>.tif
SHA_FILE = re.compile(r"(-?\d+)_(-?\d+)(?:_(\d{4}))?_([0-9a-f]{8})\.tif")


class ShaPerTile(Versions):
    """Square tiles of tile_m in crs whose files are replaced in place (Bavaria's, without a year) or
    by a newer survey (Rhineland-Palatinate's, the year in the name): the newest listed year of each
    tile is used, and a file is known by its SHA-256 (the first 8 hex digits in its name), so a
    changed file has another name and is read again; the cached files of the tile's other versions
    are deleted then. Cached as <folder>/<east // 10>_<north // 10>/<east>_<north>[_<year>]_<key>.tif;
    a listed file without a SHA-256 is known by its URL."""

    def __init__(self, folder: str, crs: str, tile_m: float = 1000):
        self.folder, self.crs, self.tile_m = folder, crs, tile_m

    @staticmethod
    def tile(item: Dict) -> ShaTile:
        east, north = (int(v) for v in item["godlo"].split("_"))
        key = (item.get("sha256") or hashlib.sha1(item["url"].encode()).hexdigest())[:8]
        return ShaTile(east, north, item["year"], key, item["url"], item.get("sha256"), item.get("size"))

    @staticmethod
    def _order(tile: ShaTile) -> tuple:
        return tile.year, -tile.north, tile.east

    def _newest(self, items: List[Dict]) -> Dict[Tuple[int, int], ShaTile]:
        newest: Dict[Tuple[int, int], ShaTile] = {}
        for item in items:
            tile = self.tile(item)
            old = newest.get((tile.east, tile.north))
            if old is None or (tile.year, tile.key) > (old.year, old.key):
                newest[(tile.east, tile.north)] = tile
        return newest

    def query(self, index: CachedIndex, grid: Grid, cache_dir: str, update: Optional[str]) -> list:
        """The newest tile of each place over the grid (and the area's shape), newest first."""
        west, south, east, north = transform_bounds(grid.crs, "EPSG:4326", *grid.bounds)
        g_left, g_bottom, g_right, g_top = transform_bounds(grid.crs, self.crs, *grid.bounds)
        shape = None
        if grid.area_shape is not None:
            from area import project
            from shapely.geometry import box
            shape = project(grid.area_shape, grid.crs, self.crs).intersection(box(g_left, g_bottom, g_right, g_top))
        items = []
        for lat, lon in osm.tiles(west, south, east, north):
            for item in index.answers(cache_dir, lat, lon, update):
                left, bottom, right, top = item["extent"]
                if not (left < g_right and right > g_left and bottom < g_top and top > g_bottom):
                    continue
                if shape is not None:
                    from shapely.geometry import box
                    if not shape.intersects(box(left, bottom, right, top)):
                        continue
                items.append(item)
        return sorted(self._newest(items).values(), key=self._order, reverse=True)

    def _name(self, tile: ShaTile) -> str:
        year = f"_{tile.year}" if tile.year else ""
        return f"{tile.east}_{tile.north}{year}_{tile.key}.tif"

    def path(self, cache_dir: str, tile) -> str:
        return os.path.join(cache_dir, self.folder, f"{tile.east // 10}_{tile.north // 10}", self._name(tile))

    @staticmethod
    def _of(path: str) -> Optional[ShaTile]:
        match = SHA_FILE.fullmatch(os.path.basename(path))
        if not match:
            return None
        return ShaTile(int(match.group(1)), int(match.group(2)), int(match.group(3) or 0), match.group(4))

    def _others(self, cache_dir: str, tile: ShaTile) -> List[str]:
        """The cached files of the same place but another version."""
        folder = os.path.dirname(self.path(cache_dir, tile))
        mine = os.path.basename(self.path(cache_dir, tile))
        found = os.listdir(folder) if os.path.isdir(folder) else []
        return [os.path.join(folder, n) for n in found if n != mine and (t := self._of(n)) is not None
                and (t.east, t.north) == (tile.east, tile.north)]

    def prune(self, cache_dir: str, tiles: list) -> int:
        older = []
        for tile in tiles:
            if os.path.exists(self.path(cache_dir, tile)):
                older += self._others(cache_dir, tile)
        cache.forget(cache_dir, older)
        return len(older)

    def update_tile(self, index: CachedIndex, cache_dir: str, lat: float, lon: float) -> Tuple[list, list]:
        """The listed tiles of one 0.25° tile whose place is cached in another version: read again,
        and the older files deleted then."""
        newest = self._newest(index.answers(cache_dir, lat, lon, "all"))
        todo = [t for t in newest.values()
                if not os.path.exists(self.path(cache_dir, t)) and self._others(cache_dir, t)]
        return todo, todo

    def _cached_tiles(self, cache_dir: str) -> List[ShaTile]:
        tiles = []
        for path in glob.glob(os.path.join(cache_dir, self.folder, "*", "*.tif")):
            tile = self._of(path)
            if tile is not None and path == self.path(cache_dir, tile):
                tiles.append(tile)
        return tiles

    def cached(self, grid: Grid, cache_dir: str) -> list:
        """The cached tiles over the grid (the index cannot be reached), the newest of each place."""
        g_left, g_bottom, g_right, g_top = transform_bounds(grid.crs, self.crs, *grid.bounds)
        newest: Dict[Tuple[int, int], ShaTile] = {}
        m = self.tile_m
        for tile in self._cached_tiles(cache_dir):
            if not (tile.east * m < g_right and (tile.east + 1) * m > g_left
                    and tile.north * m < g_top and (tile.north + 1) * m > g_bottom):
                continue
            old = newest.get((tile.east, tile.north))
            if old is None or (tile.year, tile.key) > (old.year, old.key):
                newest[(tile.east, tile.north)] = tile
        return sorted(newest.values(), key=self._order, reverse=True)

    def has_data_near(self, index: CachedIndex, lat: float, lon: float, cache_dir: str,
                      metres: float = 2000) -> Optional[bool]:
        try:
            items = [item for corner in osm.tiles(lon, lat, lon, lat) for item in index.answers(cache_dir, *corner)]
        except requests.RequestException:
            return None
        from rasterio.warp import transform
        (x,), (y,) = transform("EPSG:4326", self.crs, [lon], [lat])
        return any(left - metres <= x <= right + metres and bottom - metres <= y <= top + metres
                   for left, bottom, right, top in (item["extent"] for item in items))


def years_of(paths: Sequence[str]) -> Set[int]:
    """The survey years named by cached files of a ShaPerTile layer (none for files without one)."""
    return {t.year for t in (ShaPerTile._of(p) for p in paths) if t is not None and t.year}
