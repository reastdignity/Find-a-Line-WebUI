"""Package ZIPs of 1 km tiles in several UTM zones (Ontario's DTM and DSM, Lidar-Derived): the packages over a
0.25° tile from an ArcGIS FeatureServer of their footprints, each package's central directory read by Range and
kept per package (PackageListing), and one version of each place, the newest survey's (PackageVersions).

A member's name gives its tile (the DTM user guide's figure 4): 1km<zone><east><north>[<year>]<project>, east
and north in 100 m units of NAD83(CSRS) / UTM of the zone, the year missing in some projects (Ottawa River)."""

import glob
import gzip
import json
import os
import re
import threading
from dataclasses import dataclass
from typing import Dict, List, Optional, Pattern, Sequence, Set, Tuple

import requests
from rasterio.warp import transform_bounds

import cache
import osm
from grid import Grid

from .. import net
from ..net import _part
from ..readers.windows import _same_crs
from ..readers.zipmember import ArchiveChanged, RangeRefused
from .arcgis import query_features
from .cached import CachedIndex, IndexUnavailable, Listing, Versions, index_tiles
from .versions import _answers
from .zipdir import head, read_directory

TILE_M = 1000
# 1km<zone 2><east 4><north 5>[<year 4>]<the project's code ...>.<tif|img>, east and north in 100 m: the 1 km
# tile's lower-left corner (1km175870481302023LGTA2023_DTM.tif: zone 17, (587 000, 4 813 000), 2023)
MEMBER = re.compile(r"(?:^|/)1km(?P<zone>\d{2})(?P<east>\d{4})(?P<north>\d{5})(?P<year>\d{4})?L[^/]*\.(?:tif|img)$",
                    re.I)
# The footprints of the index miss some of their tiles by up to 968 m (Ontario's, 2026-11-16: 69 of 139 102
# tiles): the 0.25° tile is grown by this many degrees when the index is asked
MARGIN_DEG = 0.02
# The link of a package in the index is an HTML anchor (<a href="...zip" ...>)
HREF = re.compile(r"""href\s*=\s*["']([^"']+)["']""", re.I)


def member_tile(name: str) -> Optional[Tuple[int, int, int, int]]:
    """(zone, east, north, year) of a member's 1 km tile, east and north in km (its lower-left corner), year 0 when
    the name has none; None for a name of another form or a corner off the whole kilometre."""
    match = MEMBER.search(name)
    if not match:
        return None
    east, north = int(match.group("east")), int(match.group("north"))
    if east % 10 or north % 10:
        return None
    return int(match.group("zone")), east // 10, north // 10, int(match.group("year") or 0)


def package_url(link: Optional[str], prefix: str) -> Optional[str]:
    """The address of a package from the index's DownloadLink (an anchor's href, or a bare address), only when it
    is a .zip under prefix (the package host's folder); None otherwise."""
    if not link:
        return None
    match = HREF.search(link)
    url = (match.group(1) if match else link).strip()
    if not url.startswith(prefix) or not url.lower().endswith(".zip") or "/" in url[len(prefix):].strip("/"):
        return None
    return url


def project_date(project: str, dates: Dict[str, str]) -> str:
    """The end of a project's acquisition (ISO date) from the catalogue's table, else the 31 December of the
    latest year its name gives ("2025-26": 2026; a project published after the table), else "0000-00-00" (the
    oldest)."""
    if project in dates:
        return dates[project]
    years = [int(year[:2] + to) if to else int(year)
             for year, to in re.findall(r"(?<!\d)((?:19|20)\d{2})(?:-(\d{2}))?(?!\d)", project)]
    return f"{max(years)}-12-31" if years else "0000-00-00"


class PackageListing(Listing):
    """The tiles of the packages over a 0.25° tile: the FeatureServer layer of their footprints (url) asked for
    the packages over the tile grown by MARGIN_DEG (attributes Package, Project, DownloadLink, Resolution; no
    geometry: Ontario's footprints are 34 MB), each package's link checked to lie under packages (the host's
    folder), then the package's central directory (read_directory: a HEAD, then the tail by Range), kept per
    package in <top>/zipdir/<key>/<package>.json.gz with its ETag and length for ttl_days: read again then, or
    with an update, and kept as it was when its ETag and length did not change. Every directory read holds a
    slot of the host (net.host_slot). Members whose names match exclude (a second copy in another height datum)
    or are no tile's (member_tile) are left out.

    Every member over the 0.25° tile is listed as {crs (its zone's), zone, east, north (km), year (its name's,
    else the project's), date (the project's: project_date), project, res, url, member, method, flags, crc, size,
    usize, offset, length (the package's), extent (in crs)}. cache_dir and update are set by PackageIndex."""

    def __init__(self, url: str, packages: str, zones: Dict[int, str], dates: Dict[str, str], top: str, key: str,
                 res: float, exclude: Optional[str] = None, ttl_days: float = 180):
        self.url, self.packages, self.zones, self.dates = url, packages, dict(zones), dict(dates)
        self.top, self.key, self.res, self.ttl_days = top, key, res, ttl_days
        self.exclude: Optional[Pattern] = re.compile(exclude) if exclude else None
        self.cache_dir: Optional[str] = None
        self.update: Optional[str] = None
        self._asked: Set[str] = set()  # the packages whose directories were checked in this process
        self._lock = threading.Lock()

    def directory_path(self, cache_dir: str, url: str) -> str:
        stem = re.sub(r"\.zip$", "", url.rsplit("/", 1)[-1], flags=re.I)
        return os.path.join(cache_dir, self.top, "zipdir", self.key, f"{stem}.json.gz")

    @staticmethod
    def _kept(path: str) -> Optional[Dict]:
        try:
            with gzip.open(path, "rt", encoding="utf-8") as kept_file:
                return json.load(kept_file)
        except (OSError, ValueError):
            return None

    def _wanted(self, name: str) -> bool:
        return member_tile(name) is not None and not (self.exclude and self.exclude.search(name))

    def _read(self, url: str, previous: Optional[Dict], slot: bool = True) -> Dict:
        """The package's directory as kept: its HEAD (length, ETag), then its directory unless previous holds it
        for the same ETag and length; under a slot of the host unless slot is False (a tile's download holds one
        already)."""
        def read() -> Dict:
            length, etag = head(url)
            if previous and etag and previous.get("etag") == etag and previous.get("length") == length:
                return previous
            try:
                listed = read_directory(url, length)
            except (ValueError, ArchiveChanged, RangeRefused, RuntimeError, requests.RequestException) as e:
                raise IndexUnavailable(f"package {cache.clean_url(url)}: {cache.clean_error(e)}") from e
            return {"url": url, "etag": etag, "length": length,
                    "members": [list(m) for m in listed if self._wanted(m.name)]}
        if not slot:
            return read()
        with net.host_slot(self.cache_dir, url):
            return read()

    def _store(self, path: str, kept: Dict):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = _part(path)
        with gzip.open(tmp, "wt", encoding="utf-8") as out:
            json.dump(kept, out)
        os.replace(tmp, path)
        cache.record(self.cache_dir, path, url=kept["url"], etag=kept.get("etag"))

    def directory(self, url: str, force: bool = False, slot: bool = True) -> Dict:
        """A package's kept directory, read when not kept or due (at most once per process), or now with force."""
        cache_dir = self.cache_dir
        path = self.directory_path(cache_dir, url)
        due = lambda: force or cache.due(cache_dir, path, update=self.update, ttl=self.ttl_days)  # noqa: E731
        if force or (path not in self._asked and due()):
            with net.tile_lock(cache_dir, path):  # another search may be reading it now
                if due():
                    self._store(path, self._read(url, self._kept(path), slot))
            with self._lock:
                self._asked.add(path)
        kept = self._kept(path)
        if kept is None:
            raise IndexUnavailable(f"{cache.relative(cache_dir, path)} cannot be read")
        return kept

    def packages_over(self, west: float, south: float, east: float, north: float) -> Dict[str, Tuple[str, float]]:
        """The packages whose footprints meet a box (WGS84): {url: (project, resolution)}, in the index's order."""
        found: Dict[str, Tuple[str, float]] = {}
        for feature in query_features(self.url, (west, south, east, north),
                                      ("Package", "Project", "DownloadLink", "Resolution"), geometry=False):
            attributes = feature.get("attributes") or {}
            url = package_url(attributes.get("DownloadLink"), self.packages)
            if url and url not in found:
                found[url] = (str(attributes.get("Project") or "").strip(),
                              float(attributes.get("Resolution") or self.res))
        return found

    def fetch(self, lat: float, lon: float) -> Dict:
        m = MARGIN_DEG
        box = (lon - m, lat - m, lon + osm.TILE_DEG + m, lat + osm.TILE_DEG + m)
        packages = self.packages_over(*box)
        bounds: Dict[str, Tuple[float, float, float, float]] = {}
        items = []
        for url, (project, res) in packages.items():
            kept = self.directory(url)
            date = project_date(project, self.dates)
            for name, method, flags, crc, size, usize, offset in kept["members"]:
                tile = member_tile(name)
                if tile is None or tile[0] not in self.zones:
                    continue
                zone, east, north, year = tile
                crs = self.zones[zone]
                if crs not in bounds:
                    bounds[crs] = transform_bounds("EPSG:4326", crs, *box, densify_pts=21)
                left, bottom, right, top = bounds[crs]
                x, y = east * TILE_M, north * TILE_M
                if not (x < right and x + TILE_M > left and y < top and y + TILE_M > bottom):
                    continue
                items.append({"crs": crs, "zone": zone, "east": east, "north": north,
                              "year": year or int(date[:4]), "date": date, "project": project, "res": res,
                              "url": url, "member": name, "method": method, "flags": flags, "crc": crc, "size": size,
                              "usize": usize, "offset": offset, "length": kept["length"],
                              "extent": [x, y, x + TILE_M, y + TILE_M]})
        return {"packages": list(packages), "sheets": items}


class PackageIndex(CachedIndex):
    """A CachedIndex of a PackageListing: tells the listing the cache folder and update mode of each answer it
    asks for (it keeps the packages' directories there)."""
    listing: PackageListing

    def answers(self, cache_dir: str, lat: float, lon: float, update: Optional[str] = None) -> List[Dict]:
        self.listing.cache_dir, self.listing.update = cache_dir, update
        return super().answers(cache_dir, lat, lon, update)


@dataclass(frozen=True)
class PackageTile:
    """A 1 km tile of one member of a package: (east, north) in km of crs (its UTM zone's), its survey year and
    key (the member's CRC-32 in 8 hex digits), and what ZipMember reads (url, member, offset, method, flags, crc,
    size, usize, length). date and project order the versions of a place (PackageVersions)."""
    crs: str
    east: int
    north: int
    year: int
    key: str
    date: str = ""
    project: str = ""
    url: str = ""
    member: str = ""
    offset: int = 0
    method: int = 8
    flags: int = 0
    crc: int = 0
    size: int = 0
    usize: int = 0
    length: int = 0

    @property
    def godlo(self) -> str:
        return f"{self.crs.split(':')[-1]}_{self.east}_{self.north}"


# A cached tile: <folder>/epsg<code>/<east // 10>_<north // 10>/<east>_<north>_<year>_<crc8>.tif
PACKAGE_FILE = re.compile(r"[\\/]epsg(\d+)[\\/]-?\d+_-?\d+[\\/](-?\d+)_(-?\d+)_(\d{4})_([0-9a-f]{8})\.tif$")


def _order(tile: PackageTile) -> tuple:
    """Newer first: the project's date, then the member's year (two surveys of one project), then its key."""
    return tile.date, tile.year, tile.key


class PackageVersions(Versions):
    """One version of each place (a 1 km tile of a zone): the newest survey's (_order: the project's date from the
    catalogue's table, then the member's year), so where two projects cover a tile the newer is used whole and its
    holes go to the source's gap filler. The tiles are used newest first, and of equal ones those in the working
    CRS first (copied as they are). A member is known by its CRC-32: a changed member has another name in the
    cache and is read again, and the cached files of a place's other versions are deleted then (prune).
    Cached as <folder>/epsg<code>/<east // 10>_<north // 10>/<east>_<north>_<year>_<crc8>.tif."""

    def __init__(self, folder: str):
        self.folder = folder

    @staticmethod
    def tile(item: Dict) -> PackageTile:
        return PackageTile(item["crs"], item["east"], item["north"], item["year"], f"{item['crc']:08x}",
                           item.get("date", ""), item.get("project", ""), item["url"], item["member"],
                           item["offset"], item["method"], item["flags"], item["crc"], item["size"], item["usize"],
                           item["length"])

    @staticmethod
    def _newest(tiles: Sequence[PackageTile]) -> Dict[Tuple[str, int, int], PackageTile]:
        newest: Dict[Tuple[str, int, int], PackageTile] = {}
        for tile in tiles:
            place = (tile.crs, tile.east, tile.north)
            old = newest.get(place)
            if old is None or _order(tile) > _order(old):
                newest[place] = tile
        return newest

    @staticmethod
    def _sorted(tiles, grid_crs: str) -> List[PackageTile]:
        same = {crs: _same_crs(crs, grid_crs) for crs in {t.crs for t in tiles}}
        return sorted(tiles, key=lambda t: (t.date, same[t.crs], t.year, t.key, t.crs, t.north, t.east),
                      reverse=True)

    def query(self, index: CachedIndex, grid: Grid, cache_dir: str, update: Optional[str]) -> list:
        """The newest tile of each place over the grid (and the area's shape), newest first."""
        items = [item for answer in _answers(index, cache_dir, index_tiles(grid), update) for item in answer]
        bounds = {crs: transform_bounds(grid.crs, crs, *grid.bounds) for crs in {item["crs"] for item in items}}
        shapes = {}
        if grid.area_shape is not None:
            import shapely
            from area import project
            from shapely.geometry import box
            for crs, (left, bottom, right, top) in bounds.items():
                shapes[crs] = project(grid.area_shape, grid.crs, crs).intersection(box(left, bottom, right, top))
                shapely.prepare(shapes[crs])
        tiles = []
        for item in items:
            left, bottom, right, top = item["extent"]
            g_left, g_bottom, g_right, g_top = bounds[item["crs"]]
            if not (left < g_right and right > g_left and bottom < g_top and top > g_bottom):
                continue
            if shapes:
                from shapely.geometry import box
                if not shapes[item["crs"]].intersects(box(left, bottom, right, top)):
                    continue
            tiles.append(self.tile(item))
        return self._sorted(self._newest(tiles).values(), grid.crs)

    def path(self, cache_dir: str, tile) -> str:
        code = tile.crs.split(":")[-1]
        return os.path.join(cache_dir, self.folder, f"epsg{code}", f"{tile.east // 10}_{tile.north // 10}",
                            f"{tile.east}_{tile.north}_{tile.year}_{tile.key}.tif")

    @staticmethod
    def _of(path: str) -> Optional[PackageTile]:
        match = PACKAGE_FILE.search(path)
        if not match:
            return None
        return PackageTile(f"EPSG:{match.group(1)}", int(match.group(2)), int(match.group(3)), int(match.group(4)),
                           match.group(5))

    def _others(self, cache_dir: str, tile: PackageTile) -> List[str]:
        """The cached files of the same place but another version."""
        folder = os.path.dirname(self.path(cache_dir, tile))
        mine = os.path.basename(self.path(cache_dir, tile))
        found = os.listdir(folder) if os.path.isdir(folder) else []
        return [os.path.join(folder, n) for n in found if n != mine
                and (t := self._of(os.path.join(folder, n))) is not None and (t.east, t.north) == (tile.east, tile.north)]

    def prune(self, cache_dir: str, tiles: list) -> int:
        older = []
        for tile in tiles:
            if os.path.exists(self.path(cache_dir, tile)):
                older += self._others(cache_dir, tile)
        cache.forget(cache_dir, older)
        return len(older)

    def update_tile(self, index: CachedIndex, cache_dir: str, lat: float, lon: float) -> Tuple[list, list]:
        """The listed tiles of one 0.25° tile whose place is cached in another version: read again, and the older
        files deleted then."""
        newest = self._newest([self.tile(item) for item in index.answers(cache_dir, lat, lon, "all")])
        todo = [t for t in newest.values()
                if not os.path.exists(self.path(cache_dir, t)) and self._others(cache_dir, t)]
        return todo, todo

    def cached(self, grid: Grid, cache_dir: str) -> list:
        """The cached tiles over the grid (the index cannot be reached), the newest of each place by year."""
        tiles = []
        bounds: Dict[str, Tuple[float, float, float, float]] = {}
        for path in glob.glob(os.path.join(cache_dir, self.folder, "epsg*", "*", "*.tif")):
            tile = self._of(path)
            if tile is None or path != self.path(cache_dir, tile):
                continue
            if tile.crs not in bounds:
                bounds[tile.crs] = transform_bounds(grid.crs, tile.crs, *grid.bounds)
            g_left, g_bottom, g_right, g_top = bounds[tile.crs]
            x, y = tile.east * TILE_M, tile.north * TILE_M
            if x < g_right and x + TILE_M > g_left and y < g_top and y + TILE_M > g_bottom:
                tiles.append(tile)
        newest: Dict[Tuple[str, int, int], PackageTile] = {}
        for tile in tiles:
            place = (tile.crs, tile.east, tile.north)
            if place not in newest or (tile.year, tile.key) > (newest[place].year, newest[place].key):
                newest[place] = tile
        return self._sorted(newest.values(), grid.crs)

    def has_data_near(self, index: CachedIndex, lat: float, lon: float, cache_dir: str,
                      metres: float = 2000) -> Optional[bool]:
        try:
            items = [item for corner in osm.tiles(lon, lat, lon, lat) for item in index.answers(cache_dir, *corner)]
        except requests.RequestException:
            return None
        from rasterio.warp import transform
        points: Dict[str, Tuple[float, float]] = {}
        for item in items:
            if item["crs"] not in points:
                (x,), (y,) = transform("EPSG:4326", item["crs"], [lon], [lat])
                points[item["crs"]] = (x, y)
            x, y = points[item["crs"]]
            left, bottom, right, top = item["extent"]
            if left - metres <= x <= right + metres and bottom - metres <= y <= top + metres:
                return True
        return False


def package_years(paths: Sequence[str]) -> Set[int]:
    """The survey years named by cached files of a PackageVersions layer."""
    return {t.year for t in (PackageVersions._of(p) for p in paths) if t is not None and t.year}


def forget_answers(cache_dir: str, top: str, prefix: str) -> None:
    """Forget the cached 0.25° answers of a layer (a package's members moved: they are made again from its
    directory read anew)."""
    answers = glob.glob(os.path.join(cache_dir, top, "sheet-index", prefix, "*.json"))
    try:
        cache.forget(cache_dir, answers)
    except OSError:  # another process forgot them now
        pass
