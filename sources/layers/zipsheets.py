"""ZipSheetTiles: map sheets of a fixed table, each the "x y z" text members of remote ZIP archives that name it, read
one member at a time by HTTP Range (OSNI's national 10 m DTM of Northern Ireland: six archives of 50 sheets on
OpenDataNI, whose stable links redirect to signed URLs of the files)."""

import gzip
import json
import math
import os
import re
import zlib
from typing import Callable, Dict, List, NamedTuple, Optional, Sequence, Tuple

import numpy as np
import requests
from rasterio.warp import transform_bounds

import cache
import servicecounts
from grid import Grid

from .. import net
from ..composed import ComposedLayer, Index, Reader
from ..indexes.cached import IndexUnavailable
from ..indexes.tilings import _outline, remembered
from ..indexes.zipdir import read_directory
from ..layer import Fetched, _clean, _write_tile
from ..readers.sheetfile import _xyz_grid
from ..readers.zipmember import ArchiveChanged, RangeRefused, ZipMember, ranged

SheetBox = Tuple[float, float, float, float]  # (left, bottom, right, top) in the sheets' CRS
LINK_TIMEOUT_S = 60


def signed_location(link: str) -> str:
    """The address a stable link of a file sends to now (a HEAD, the redirect not followed: OpenDataNI's downloads
    redirect to a signed URL of Cloudflare R2, valid for 7 days, which answers GET with Range but not HEAD), or the
    link itself when it answers 200. RuntimeError otherwise (a 404: the file is gone)."""
    net.rate_turn(link)
    with servicecounts.request(link) as counted:
        response = counted.got(net.session().head(link, headers=cache.http_headers(), timeout=LINK_TIMEOUT_S,
                                                  allow_redirects=False, verify=net.verify(link)), read=False)
    location = response.headers.get("Location", "")
    if response.status_code in (301, 302, 303, 307, 308) and location.startswith(("https://", "http://")):
        return location
    if response.status_code == 200:
        return link
    raise RuntimeError(f"{cache.clean_url(link)}: HTTP {response.status_code}"
                       + (f", redirected to {cache.clean_url(location)}" if location else ""))


class ZipSheetTile(NamedTuple):
    """A sheet of a ZipSheetIndex: its number, its key (the members' CRC-32s, 8 hex digits: a member changed in its
    archive has another key, so another cached file) and its members (ZipSheetMember)."""
    sheet: int
    key: str
    members: Tuple["ZipSheetMember", ...] = ()


class ZipSheetMember(NamedTuple):
    """One member as ZipMember reads it: its archive's stable link (url: resolved to the file's address when read),
    name, method, flags, CRC-32, compressed size, uncompressed size, local header's offset, the archive's length."""
    url: str
    member: str
    method: int
    flags: int
    crc: int
    size: int
    usize: int
    offset: int
    length: int

    @property
    def godlo(self) -> str:
        return self.member


class ZipSheetIndex(Index):
    """The sheets of a fixed table (sheets: number -> (left, bottom, right, top) in crs) over a grid, each with the
    members of the archives (their stable links, in order) whose names match member (a regular expression with the
    group "sheet", searched: folders, odd spaces and suffixes allowed). A sheet's box is grown by margin to choose
    it (members may reach beyond their sheet: OSNI's Sheet011a); a sheet no member names is left out (no request).

    The archives' central directories are read by Range (sources/indexes/zipdir.py read_directory) on the address
    each link sends to (signed_location), once per TTL ("sheet-index", like a sheet index) and kept in
    <top>/zipdir/<key>.json.gz with each archive's ETag and length (from the first two bytes' Content-Range: the
    signed addresses answer no HEAD); an archive whose ETag and length did not change keeps its members. Without an
    answer the kept directories are used, whatever their age; without those the tiles are unknown (None). Cached
    as <folder>/<sheet:03d>_<key>.tif."""

    def __init__(self, archives: Sequence[str], member: str, sheets: Dict[int, SheetBox], crs: str, folder: str,
                 key: str, margin: float = 0.0):
        self.archives, self.member, self.sheets, self.crs = tuple(archives), re.compile(member), sheets, crs
        self.folder, self.key, self.margin = folder, key, margin
        self.top = folder.split("/")[0]
        self.cache_dir: Optional[str] = None
        self.update: Optional[str] = None
        self._asked: set = set()
        self._table: Optional[Dict[int, List[ZipSheetMember]]] = None

    def use(self, cache_dir: str, update: Optional[str] = None):
        if cache_dir != self.cache_dir:
            self._table = None
        self.cache_dir, self.update = cache_dir, update

    def table_path(self, cache_dir: str) -> str:
        return os.path.join(cache_dir, self.top, "zipdir", f"{self.key}.json.gz")

    @staticmethod
    def _kept(path: str) -> Optional[Dict]:
        try:
            with gzip.open(path, "rt", encoding="utf-8") as kept_file:
                return json.load(kept_file)
        except (OSError, ValueError):
            return None

    def _download(self, previous: Optional[Dict]) -> Dict:
        before = {a["link"]: a for a in (previous or {}).get("archives", [])}
        archives = []
        for link in self.archives:
            try:
                url = signed_location(link)
                head, length, headers = ranged(url, 0, 1)
                if length is None:  # "bytes 0-1/*": no length, so no directory to find
                    raise RuntimeError("the archive's length is not stated (Content-Range bytes 0-1/*)")
                etag = headers.get("ETag")
                old = before.get(link)
                if old and etag and old.get("etag") == etag and old.get("length") == length:
                    members = old["members"]
                else:
                    members = [list(m) for m in read_directory(url, length) if self.member.search(m.name)]
            except (ValueError, ArchiveChanged, RangeRefused, RuntimeError, requests.RequestException) as e:
                raise IndexUnavailable(f"ZIP archive {cache.clean_url(link)}: {cache.clean_error(e)}") from e
            archives.append({"link": link, "etag": etag, "length": length, "members": members})
        return {"archives": archives}

    def table(self, force: bool = False) -> Optional[Dict[int, List[ZipSheetMember]]]:
        """The members of every sheet, the directories read when not kept or due (once per process), or now with
        force; None when they cannot be read and none are kept."""
        cache_dir = self.cache_dir
        if cache_dir is None:
            raise RuntimeError("ZipSheetIndex.use(cache_dir) first")
        path = self.table_path(cache_dir)
        due = lambda: force or cache.due(cache_dir, path, update=self.update,  # noqa: E731
                                         ttl=cache.TTL_DAYS["sheet-index"])
        if force or (path not in self._asked and due()):
            with net.tile_lock(cache_dir, path):  # another search may be reading them now
                if due():
                    try:
                        kept = self._download(self._kept(path))
                    except IndexUnavailable as e:
                        print(f"{self.key}: the archives' directories cannot be read ({e}); the kept ones are used")
                        kept = None
                    if kept is not None:
                        os.makedirs(os.path.dirname(path), exist_ok=True)
                        tmp = net._part(path)
                        with gzip.open(tmp, "wt", encoding="utf-8") as out:
                            json.dump(kept, out)
                        os.replace(tmp, path)
                        cache.record(cache_dir, path, url=self.archives[0])
            self._asked.add(path)
            self._table = None
        if self._table is None:
            kept = self._kept(path)
            if kept is None:
                return None
            self._table = self._sheets(kept)
        return self._table

    def _sheets(self, kept: Dict) -> Dict[int, List[ZipSheetMember]]:
        found: Dict[int, List[ZipSheetMember]] = {}
        for archive in kept["archives"]:
            for name, method, flags, crc, size, usize, offset in archive["members"]:
                match = self.member.search(name)
                if match and not name.endswith("/"):
                    found.setdefault(int(match.group("sheet")), []).append(ZipSheetMember(
                        archive["link"], name, method, flags, crc, size, usize, offset, archive["length"]))
        return found

    def sheet_tile(self, sheet: int, table: Dict[int, List[ZipSheetMember]]) -> Optional[ZipSheetTile]:
        members = tuple(sorted(table.get(sheet, ()), key=lambda m: m.member))
        if not members:
            return None
        key = f"{zlib.crc32(','.join(f'{m.crc:08x}' for m in members).encode()):08x}"
        return ZipSheetTile(sheet, key, members)

    def tiles(self, grid: Grid) -> Optional[list]:
        if self.cache_dir is None:  # never used with a data folder: unknown
            return None
        table = self.table()
        if table is None:
            return None
        return remembered(self, grid, lambda: self._tiles(grid, table))

    def _tiles(self, grid: Grid, table: Dict[int, List[ZipSheetMember]]) -> list:
        left, bottom, right, top = transform_bounds(grid.crs, self.crs, *grid.bounds)
        shape = _outline(grid, self.crs)
        if shape is not None:
            import shapely
        m = self.margin
        tiles = []
        for sheet, (s_left, s_bottom, s_right, s_top) in sorted(self.sheets.items()):
            box = (s_left - m, s_bottom - m, s_right + m, s_top + m)
            if box[0] >= right or box[2] <= left or box[1] >= top or box[3] <= bottom:
                continue
            if shape is not None and not shapely.intersects(shape, shapely.box(*box)):
                continue
            tile = self.sheet_tile(sheet, table)
            if tile is not None:
                tiles.append(tile)
        return tiles

    def path(self, cache_dir: str, tile: ZipSheetTile) -> str:
        return os.path.join(cache_dir, self.folder, f"{tile.sheet:03d}_{tile.key}.tif")

    def bounds_wgs84(self, tile: ZipSheetTile) -> Tuple[float, float, float, float]:
        s_left, s_bottom, s_right, s_top = self.sheets[tile.sheet]
        m = self.margin
        return transform_bounds(self.crs, "EPSG:4326", s_left - m, s_bottom - m, s_right + m, s_top + m)

    def has_data_near(self, lat: float, lon: float, cache_dir: str) -> Optional[bool]:
        """Whether the point lies in a sheet's box (the table's)."""
        from rasterio.warp import transform
        (x,), (y,) = transform("EPSG:4326", self.crs, [lon], [lat])
        return any(a <= x <= c and b <= y <= d for a, b, c, d in self.sheets.values())


class ZipSheetReader(Reader):
    """A sheet's members, each read by one Range of its local header and data on the address its archive's link
    sends to now (signed_location: a signed address expires), inflated and checked against its CRC-32 (ZipMember),
    then their "x y z" lines of cell centres made one raster at res in crs (readers.sheetfile._xyz_grid) and
    written (float32, NaN where no point: the sea and beyond the sheet). A sheet that cannot be read (a member not
    where the kept directory said, ArchiveChanged; or one whose CRC-32 or size still differs after the retries: a
    member replaced in place, as an archive's first member always is) makes the directories be read again (renew)
    and the sheet tried once more when they list it otherwise; it is then written under its new key (its cached
    name) and renewed(new path, sheet, url) records it and deletes the sheet's other versions. Members without a
    point (empty text) make the sheet missing. Messages pass cache.clean_error: a signed address's query never
    reaches a text."""
    rewrites = True  # the cached tile is written by _write_tile: reencode / cache migrate may convert it

    def __init__(self, description: str, res: float, crs: str,
                 renew: Optional[Callable[[ZipSheetTile], Optional[ZipSheetTile]]] = None,
                 renewed: Optional[Callable[[str, ZipSheetTile, Optional[str]], None]] = None):
        self.description, self.res, self.crs, self.renew, self.renewed = description, res, crs, renew, renewed
        self._zip = ZipMember(description)

    def url(self, request: ZipSheetTile) -> Optional[str]:
        return request.members[0].url if request.members else None

    def _read(self, request: ZipSheetTile, where: str) -> Tuple[List[bytes], int]:
        resolved: Dict[str, str] = {}
        texts, received = [], 0
        for member in request.members:
            if member.url not in resolved:
                resolved[member.url] = signed_location(member.url)
            data, got = self._zip._member(member._replace(url=resolved[member.url]), where)
            texts.append(data)
            received += got
        return texts, received

    def fetch(self, request: ZipSheetTile, path: str) -> Fetched:
        where = f"{self.description} sheet {request.sheet}"
        renewed: Optional[ZipSheetTile] = None
        try:
            texts, received = self._read(request, where)
        except (ArchiveChanged, requests.RequestException, RuntimeError) as e:
            renewed = self.renew(request) if self.renew else None
            if renewed is None:
                raise RuntimeError(f"Could not download {where}: {cache.clean_error(e)}") from None
            try:
                texts, received = self._read(renewed, where)
            except (ArchiveChanged, requests.RequestException, RuntimeError) as again:
                raise RuntimeError(f"Could not download {where}: {cache.clean_error(again)}") from None
            path = os.path.join(os.path.dirname(path), f"{renewed.sheet:03d}_{renewed.key}.tif")
        sheet = renewed or request
        if not any(t.strip() for t in texts):  # members without a point
            return Fetched(0, self.url(sheet))
        try:
            band, transform = _xyz_grid(b"\n".join(t.rstrip() for t in texts), self.res, self.crs, where)
        except (ValueError, IndexError, RuntimeError) as e:
            raise RuntimeError(f"{where}: not an XYZ grid ({cache.clean_error(str(e)[:100])})") from None
        band = _clean(band)
        if not np.isfinite(band).any():
            return Fetched(0, self.url(sheet))
        _write_tile(path, band, self.crs, transform)
        if renewed is not None and self.renewed:
            self.renewed(path, renewed, self.url(sheet))
        return Fetched(received, self.url(sheet))


class ZipSheetTiles(ComposedLayer):
    """Sheets of a fixed table made of "x y z" members of remote ZIP archives (ZipSheetIndex, ZipSheetReader): one
    raster per sheet at native_res in crs, cached by the members' CRC-32s. The directories are read before the
    tiles are listed (use), so the tiles of a grid are unknown (None) only when they were never read: the cached
    sheets over the grid are used then."""

    def __init__(self, description: str, archives: Sequence[str], member: str, sheets: Dict[int, SheetBox], crs: str,
                 folder: str, key: str, native_res: float, margin: float = 0.0, bytes_per_tile: float = 3e6):
        self.description, self.folder, self.crs, self.native_res = description, folder, crs, native_res
        self.archives, self._bytes = tuple(archives), bytes_per_tile
        self.index = ZipSheetIndex(archives, member, sheets, crs, folder, key, margin)
        self.reader = ZipSheetReader(description, native_res, crs, renew=self._renew, renewed=self._renewed)

    def _renew(self, tile: ZipSheetTile) -> Optional[ZipSheetTile]:
        """The sheet as the directories, read again now, list it (None: unchanged or gone). The tiles kept for the
        last grid are forgotten, so the next listing has the new key."""
        table = self.index.table(force=True)
        self.index._memo = None
        renewed = self.index.sheet_tile(tile.sheet, table) if table else None
        return renewed if renewed is not None and renewed.members != tile.members else None

    def _renewed(self, path: str, tile: ZipSheetTile, url: Optional[str]):
        """A renewed sheet written at path: recorded in the cache's index and the sheet's other versions deleted
        (as ZipPerTile prunes a changed member's older file)."""
        import glob
        cache_dir = self.index.cache_dir
        if cache_dir:
            cache.record(cache_dir, path, "ok", url)
        for other in glob.glob(os.path.join(glob.escape(os.path.dirname(path)), f"{tile.sheet:03d}_*.tif")):
            if os.path.normcase(other) != os.path.normcase(path):
                try:
                    os.remove(other)
                except OSError:  # open in another process (Windows): left for a later prune
                    pass

    def _cached(self, grid: Grid, cache_dir: str) -> List[str]:
        """The cached sheets over the grid without the directories: of each sheet its newest file (the latest
        written), never two versions."""
        import glob
        left, bottom, right, top = transform_bounds(grid.crs, self.crs, *grid.bounds)
        found = []
        m = self.index.margin
        for sheet, (a, b, c, d) in sorted(self.index.sheets.items()):
            if a - m < right and c + m > left and b - m < top and d + m > bottom:
                versions = glob.glob(os.path.join(glob.escape(cache_dir), self.folder, f"{sheet:03d}_*.tif"))
                if versions:
                    found.append(max(versions, key=lambda p: (os.path.getmtime(p), p)))
        return found

    def missing(self, grid: Grid, cache_dir: str, update: Optional[str]) -> list:
        self.index.use(cache_dir, update)
        if self.tiles(grid) is None:
            return []
        return super().missing(grid, cache_dir, update)

    def estimate(self, grid: Grid, cache_dir: str, update: Optional[str]) -> Tuple[int, int, float]:
        self.index.use(cache_dir, update)
        if self.tiles(grid) is None:
            return len(self._cached(grid, cache_dir)), 0, 0.0
        return super().estimate(grid, cache_dir, update)

    def to_download(self, grid: Grid, cache_dir: str, update: Optional[str]) -> Tuple[list, Optional[str]]:
        self.index.use(cache_dir, update)
        if self.tiles(grid) is None:
            return [], f"{self.description}: the archives' directories cannot be read; the cached sheets are used"
        return super().to_download(grid, cache_dir, update)

    def files(self, grid: Grid, cache_dir: str) -> List[str]:
        self.index.use(cache_dir, update=None)
        if self.tiles(grid) is None:
            return self._cached(grid, cache_dir)
        return super().files(grid, cache_dir)

    def has_data_near(self, lat: float, lon: float, cache_dir: str) -> Optional[bool]:
        return self.index.has_data_near(lat, lon, cache_dir)
