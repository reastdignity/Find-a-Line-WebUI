"""Package ZIPs of 1 km tiles in several UTM zones (Ontario's DTM and DSM, Lidar-Derived): the packages over a
0.25° tile from an ArcGIS FeatureServer of their footprints, each package's central directory read by Range and
kept per package (PackageListing), and one version of each place, the newest survey's (PackageVersions).

A member's name gives its tile (the DTM user guide's figure 4): 1km<zone><east><north>[<year>]<project>, east
and north in 100 m units of NAD83(CSRS) / UTM of the zone, the year missing in some projects (Ottawa River)."""

import contextlib
import glob
import gzip
import json
import math
import os
import re
import threading
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Pattern, Sequence, Set, Tuple

import requests
from filelock import FileLock, Timeout
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
# A package that answers but cannot be read (a 404 of a renamed or removed one, not a ZIP archive) is left out of
# a 0.25° tile's answer, with a warning; that answer is asked again after this many seconds (not on every search)
GONE_RETRY_S = 24 * 3600
# Where two versions cover a place and the newest one's member is under this share of another's size (compressed,
# from the directory: no data compresses to almost nothing), that other is used too and fills the newest's holes
HOLE_SHARE = 0.75


class PackageGone(IndexUnavailable):
    """A package that answers but cannot be read: an HTTP status (a 404 of a renamed or removed package), not a ZIP
    archive, a Range answered with the whole file. Not the network's failure (an IndexUnavailable)."""


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
    with an update, and kept as it was when its ETag and length did not change. A directory is read under a slot
    of the host (net.host_slot), then a lock of its own (not a tile's lock: the answer's tile lock is held around
    fetch, a tile's around a renewal, and two of those could be one file): everywhere a tile's lock, then a slot,
    then a directory's lock. A package that answers but cannot be read (PackageGone: a renamed or removed one) is
    left out with a warning, and the answer is asked again after GONE_RETRY_S (a marker beside it: PackageIndex);
    the network's failure leaves the whole answer unavailable. Members whose names match exclude (a second copy in
    another height datum) or are no tile's (member_tile) are left out.

    Every member over the 0.25° tile is listed as {crs (its zone's), zone, east, north (km), year (its name's,
    else the project's), date (the project's: project_date), project, res, url, member, method, flags, crc, size,
    usize, offset, length (the package's), extent (in crs)}; the packages left out as "gone" ({url, error}).
    cache_dir and update are set by PackageIndex."""

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

    def _read(self, url: str, previous: Optional[Dict]) -> Dict:
        """The package's directory as kept: its HEAD (length, ETag), then its directory unless previous holds it
        for the same ETag and length. PackageGone when the package answers but cannot be read, IndexUnavailable
        when the host cannot be reached."""
        where = f"package {cache.clean_url(url)}"
        try:
            length, etag = head(url)
        except IndexUnavailable as e:
            status = re.search(r"HTTP (\d{3})", str(e))
            if e.__cause__ is None and status and 400 <= int(status.group(1)) < 500:  # 404, 410, 403: gone
                raise PackageGone(str(e)) from None
            raise  # the network, or a server's error (5xx): the whole answer waits
        if previous and etag and previous.get("etag") == etag and previous.get("length") == length:
            return previous
        try:
            listed = read_directory(url, length)
        except (ValueError, ArchiveChanged, RangeRefused) as e:  # not a ZIP archive, a 404, the whole file
            raise PackageGone(f"{where}: {cache.clean_error(e)}") from e
        except (RuntimeError, requests.RequestException) as e:
            raise IndexUnavailable(f"{where}: {cache.clean_error(e)}") from e
        return {"url": url, "etag": etag, "length": length,
                "members": [list(m) for m in listed if self._wanted(m.name)]}

    def _store(self, path: str, kept: Dict):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = _part(path)
        with gzip.open(tmp, "wt", encoding="utf-8") as out:
            json.dump(kept, out)
        os.replace(tmp, path)
        cache.record(self.cache_dir, path, url=kept["url"], etag=kept.get("etag"))

    @contextlib.contextmanager
    def _directory_lock(self, cache_dir: str, path: str):
        """The lock of a package's kept directory: a file of its own in cache/locks/packages (not one of the tile
        locks, which the answer's and a tile's holders share by their hash)."""
        name = f"{self.key}-{os.path.basename(path)}.lock"
        lock = FileLock(os.path.join(net._locks(cache_dir, "packages"), name))
        try:
            lock.acquire(timeout=net.LOCK_WAIT_S)
        except Timeout:
            raise RuntimeError(f"{cache.relative(cache_dir, path)} is being read by another search "
                               f"(waited {net.LOCK_WAIT_S // 60} min); try again later") from None
        try:
            yield
        finally:
            lock.release()

    def directory(self, url: str, force: bool = False, slot: bool = True) -> Dict:
        """A package's kept directory, read when not kept or due (at most once per process), or now with force:
        under a slot of the host (unless slot is False: a tile's download holds one already), then its lock."""
        cache_dir = self.cache_dir
        path = self.directory_path(cache_dir, url)
        due = lambda: force or cache.due(cache_dir, path, update=self.update, ttl=self.ttl_days)  # noqa: E731
        if force or (path not in self._asked and due()):
            with (net.host_slot(cache_dir, url) if slot else contextlib.nullcontext()), \
                    self._directory_lock(cache_dir, path):  # another search may be reading it now
                if due():
                    self._store(path, self._read(url, self._kept(path)))
            with self._lock:
                self._asked.add(path)
        kept = self._kept(path)
        if kept is None:
            raise IndexUnavailable(f"{cache.relative(cache_dir, path)} cannot be read")
        return kept

    def retry_path(self, cache_dir: str, lat: float, lon: float) -> str:
        """The marker beside a 0.25° tile's answer that left out a package: when to ask that answer again."""
        return os.path.join(cache_dir, self.top, "sheet-index", self.key, f"{osm.tile_name(lat, lon)}.json.retry")

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
        items, gone = [], []
        for url, (project, res) in packages.items():
            try:
                kept = self.directory(url)
            except PackageGone as e:
                print(f"{self.key}: {cache.clean_url(url)} left out ({cache.clean_error(e)}); the 0.25° tile "
                      f"{osm.tile_name(lat, lon)} is listed without it and asked again in {GONE_RETRY_S // 3600} h")
                gone.append({"url": url, "error": cache.clean_error(e)})
                continue
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
        marker = self.retry_path(self.cache_dir, lat, lon)
        if gone:
            os.makedirs(os.path.dirname(marker), exist_ok=True)
            with open(marker, "w", encoding="utf-8") as f:
                f.write(str(time.time() + GONE_RETRY_S))
        elif os.path.exists(marker):
            with contextlib.suppress(OSError):
                os.remove(marker)
        return {"packages": list(packages), "sheets": items, "gone": gone}


class PackageIndex(CachedIndex):
    """A CachedIndex of a PackageListing: tells the listing the cache folder and update mode of each answer it
    asks for (it keeps the packages' directories there), and forgets an answer that left out a package once its
    retry marker's time has come (PackageListing.retry_path), so it is asked again."""
    listing: PackageListing

    def answers(self, cache_dir: str, lat: float, lon: float, update: Optional[str] = None) -> List[Dict]:
        self.listing.cache_dir, self.listing.update = cache_dir, update
        marker = self.listing.retry_path(cache_dir, lat, lon)
        if os.path.exists(marker):
            try:
                with open(marker, encoding="utf-8") as f:
                    when = float(f.read().strip() or 0)
            except (OSError, ValueError):
                when = 0.0
            if time.time() >= when:
                try:
                    cache.forget(cache_dir, [self.index_path(cache_dir, lat, lon)])
                    os.remove(marker)
                except OSError:  # another process forgot it now
                    pass
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
    """Newer first: the member's year (its survey's: a project of several years names each tile's), then the
    project's date (two projects of one year), then the larger member (its compressed size in the directory: of two
    members of one project and year at a place, a partial copy in a neighbouring package loses), then its name.
    Ontario's tile index (2026-10-28): of 30 414 places in two or more projects, 54 would go the other way by the
    project's date first, each to the older survey (Huron-Georgian Bay's tiles of 2022 against GTA 2023's)."""
    return tile.year, tile.date, tile.size, tile.member, tile.key


class PackageVersions(Versions):
    """The versions of each place (a 1 km tile of a zone) that are used: the newest survey's (_order: the member's
    year, then the project's date from the catalogue's table, then the larger member), and each other whose member
    the newest's is under HOLE_SHARE of in size (the newest is partial there: no data compresses to almost
    nothing), which fills the newest's holes; what neither covers goes to the source's gap filler. The tiles are
    used newest first (the mosaic writes a pixel from the first file holding it: the newest, then its fillers), of
    equal ones those in the working CRS first (copied as they are). A member is known by its CRC-32: a changed
    member has another name in the cache and is read again, and the cached files of a place's versions no longer
    used are deleted (prune). Cached as <folder>/epsg<code>/<east // 10>_<north // 10>/<east>_<north>_<year>_<crc8>.tif."""

    def __init__(self, folder: str):
        self.folder = folder

    @staticmethod
    def _places(tiles: Sequence[PackageTile]) -> Dict[Tuple[str, int, int], List[PackageTile]]:
        """The distinct members of each place, newest first."""
        places: Dict[Tuple[str, int, int], Dict[Tuple[str, str], PackageTile]] = {}
        for tile in tiles:
            places.setdefault((tile.crs, tile.east, tile.north), {}).setdefault((tile.url, tile.member), tile)
        return {place: sorted(found.values(), key=_order, reverse=True) for place, found in places.items()}

    @classmethod
    def _used(cls, tiles: Sequence[PackageTile]) -> List[PackageTile]:
        """Of each place its newest version, and the others whose member the newest's is under HOLE_SHARE of."""
        used = []
        for versions in cls._places(tiles).values():
            newest = versions[0]
            used.append(newest)
            used += [other for other in versions[1:] if newest.size < HOLE_SHARE * other.size]
        return used

    @staticmethod
    def tile(item: Dict) -> PackageTile:
        return PackageTile(item["crs"], item["east"], item["north"], item["year"], f"{item['crc']:08x}",
                           item.get("date", ""), item.get("project", ""), item["url"], item["member"],
                           item["offset"], item["method"], item["flags"], item["crc"], item["size"], item["usize"],
                           item["length"])

    @classmethod
    def _newest(cls, tiles: Sequence[PackageTile]) -> Dict[Tuple[str, int, int], PackageTile]:
        return {place: versions[0] for place, versions in cls._places(tiles).items()}

    @staticmethod
    def _sorted(tiles, grid_crs: str) -> List[PackageTile]:
        same = {crs: _same_crs(crs, grid_crs) for crs in {t.crs for t in tiles}}
        return sorted(tiles, key=lambda t: (t.year, t.date, same[t.crs], t.size, t.member, t.key, t.crs, t.north,
                                            t.east), reverse=True)

    def query(self, index: CachedIndex, grid: Grid, cache_dir: str, update: Optional[str]) -> list:
        """The used versions of each place over the grid (and the area's shape: _used), newest first."""
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
        return self._sorted(self._used(tiles), grid.crs)

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
        """Of each place whose newest version (its first among tiles, which are newest first) is cached, delete the
        cached files of the versions not among tiles (an older survey, a changed member; never a filler in use)."""
        used: Dict[Tuple[str, int, int], Set[str]] = {}
        newest: Dict[Tuple[str, int, int], PackageTile] = {}
        for tile in tiles:
            place = (tile.crs, tile.east, tile.north)
            used.setdefault(place, set()).add(os.path.basename(self.path(cache_dir, tile)))
            newest.setdefault(place, tile)
        older = []
        for place, tile in newest.items():
            if os.path.exists(self.path(cache_dir, tile)):
                older += [p for p in self._others(cache_dir, tile) if os.path.basename(p) not in used[place]]
        cache.forget(cache_dir, older)
        return len(older)

    def update_tile(self, index: CachedIndex, cache_dir: str, lat: float, lon: float) -> Tuple[list, list]:
        """The newest tiles of one 0.25° tile whose place is cached in another version: read again; the versions
        used there are kept, the others deleted then."""
        listed = [self.tile(item) for item in index.answers(cache_dir, lat, lon, "all")]
        todo = [t for t in self._newest(listed).values()
                if not os.path.exists(self.path(cache_dir, t)) and self._others(cache_dir, t)]
        return todo, sorted(self._used(listed), key=_order, reverse=True)

    def cached(self, grid: Grid, cache_dir: str) -> list:
        """The cached tiles over the grid (the index cannot be reached), newest first by year (a filler after the
        newest of its place)."""
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
        return self._sorted(tiles, grid.crs)

    def has_data_near(self, index: CachedIndex, lat: float, lon: float, cache_dir: str,
                      metres: float = 2000) -> Optional[bool]:
        """Whether a listed tile lies within metres of the point (every 0.25° tile within them asked); None when
        the index cannot be asked."""
        d_lat = metres / 111_320.0
        d_lon = metres / (111_320.0 * max(0.01, math.cos(math.radians(lat))))
        try:
            items = [item for corner in osm.tiles(lon - d_lon, lat - d_lat, lon + d_lon, lat + d_lat)
                     for item in index.answers(cache_dir, *corner)]
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
