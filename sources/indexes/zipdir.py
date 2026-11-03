"""ZIP directories: the members of remote ZIP archives listed from their central directories, read by HTTP Range
from the archives' ends (ZipDirectories, kept per TTL like a Metalink document), a member per square tile whose
CRC-32 is its version (ZipPerTile). The archives' addresses may hold the token of a share, resolved from a stable
address that redirects to it (a Nextcloud share's: LVGL Saarland's).

The ZIP format is PKWARE's APPNOTE.TXT, version 6.3.10 (2022-11-01); the sections named below are its."""

import gzip
import json
import os
import re
import struct
from dataclasses import dataclass
from typing import Dict, List, NamedTuple, Optional, Sequence, Tuple

import requests

import cache
import servicecounts

from .. import net
from ..net import _part
from ..readers.zipmember import ArchiveChanged, RangeRefused, member_name, ranged
from .cached import IndexUnavailable
from .metalink import MetalinkFiles, ShaPerTile, ShaTile

# 4.3.16: the end of central directory record, its signature and fixed size; its comment is at most 65 535
# bytes, so the record lies within the archive's last TAIL_MAX bytes
EOCD_SIG = b"PK\x05\x06"
EOCD_SIZE = 22
TAIL_MAX = 0xFFFF + EOCD_SIZE
# 4.3.15: the ZIP64 end of central directory locator, right before the record (4.3.6)
ZIP64_LOCATOR_SIG = b"PK\x06\x07"
ZIP64_LOCATOR_SIZE = 20
# 4.3.14: the ZIP64 end of central directory record (its fixed part)
ZIP64_EOCD_SIG = b"PK\x06\x06"
ZIP64_EOCD_SIZE = 56
# 4.3.12: a central directory file header and its fixed size
CENTRAL_SIG = b"PK\x01\x02"
CENTRAL_SIZE = 46
# 4.5.3: the ZIP64 extended information extra field; 4.4.1.4: a field of 0xFFFF / 0xFFFFFFFF is in it
ZIP64_EXTRA = 0x0001
U16, U32 = 0xFFFF, 0xFFFFFFFF
# The largest central directory read (Saarland's: 35-106 kB for 400-650 members)
DIRECTORY_MAX = 4_000_000
DIRECTORY_TIMEOUT_S = 120


class Member(NamedTuple):
    """One entry of a central directory (4.3.12): name, compression method, flags, CRC-32, compressed and
    uncompressed size, and the offset of its local header."""
    name: str
    method: int
    flags: int
    crc: int
    size: int
    usize: int
    offset: int


def end_record(tail: bytes, tail_start: int) -> Tuple[int, int, int, Optional[int]]:
    """(entries, directory size, directory offset, ZIP64 record's offset or None) from the archive's tail (its
    bytes from tail_start to the end): the last end of central directory record (4.3.16) whose comment reaches
    the end exactly, and, when one of its fields is the ZIP64 marker (4.4.1.4), the offset of the ZIP64 end
    record from the locator before it (4.3.15). ValueError when there is none."""
    pos = tail.rfind(EOCD_SIG)
    while pos >= 0:
        if pos + EOCD_SIZE <= len(tail):
            comment, = struct.unpack_from("<H", tail, pos + 20)
            if pos + EOCD_SIZE + comment == len(tail):
                break
        pos = tail.rfind(EOCD_SIG, 0, pos)
    if pos < 0:
        raise ValueError("no end of central directory record")
    disk, cd_disk, _, entries, size, offset = struct.unpack_from("<HHHHII", tail, pos + 4)
    if entries != U16 and size != U32 and offset != U32:
        if disk or cd_disk:
            raise ValueError("a split archive (4.3.16: disk numbers)")
        return entries, size, offset, None
    locator = pos - ZIP64_LOCATOR_SIZE
    if locator < 0 or tail[locator:locator + 4] != ZIP64_LOCATOR_SIG:
        raise ValueError("ZIP64 markers without a ZIP64 end of central directory locator")
    record, = struct.unpack_from("<Q", tail, locator + 8)
    return entries, size, offset, record


def zip64_end_record(record: bytes) -> Tuple[int, int, int]:
    """(entries, directory size, directory offset) of a ZIP64 end of central directory record (4.3.14)."""
    if len(record) < ZIP64_EOCD_SIZE or record[:4] != ZIP64_EOCD_SIG:
        raise ValueError("no ZIP64 end of central directory record where its locator says")
    entries, size, offset = struct.unpack_from("<QQQ", record, 32)
    return entries, size, offset


def central_directory(data: bytes, entries: int) -> List[Member]:
    """The entries of a central directory (4.3.12), their sizes and offset from the ZIP64 extra field (4.5.3)
    where the 32-bit fields hold the marker; ValueError when it is not one."""
    members, pos = [], 0
    for _ in range(entries):
        if data[pos:pos + 4] != CENTRAL_SIG or pos + CENTRAL_SIZE > len(data):
            raise ValueError(f"no central directory file header at {pos}")
        (flags, method, crc, size, usize, name_length, extra_length, comment_length,
         disk) = struct.unpack_from("<HH4xIIIHHHH", data, pos + 8)
        offset, = struct.unpack_from("<I", data, pos + 42)
        name = member_name(data[pos + CENTRAL_SIZE:pos + CENTRAL_SIZE + name_length], flags)
        extra = data[pos + CENTRAL_SIZE + name_length:pos + CENTRAL_SIZE + name_length + extra_length]
        if U32 in (usize, size, offset) or disk == U16:
            usize, size, offset = _zip64(extra, usize, size, offset, disk == U16)
        members.append(Member(name, method, flags, crc, size, usize, offset))
        pos += CENTRAL_SIZE + name_length + extra_length + comment_length
    return members


def _zip64(extra: bytes, usize: int, size: int, offset: int, disk: bool) -> Tuple[int, int, int]:
    """4.5.3: the ZIP64 extra field holds, in this order, the uncompressed size, the compressed size and the
    local header's offset, each only when its field in the header is 0xFFFFFFFF (and the disk number)."""
    pos = 0
    while pos + 4 <= len(extra):
        tag, length = struct.unpack_from("<HH", extra, pos)
        if tag == ZIP64_EXTRA:
            values, at = [], pos + 4
            for field in (usize, size, offset):
                if field == U32:
                    values.append(struct.unpack_from("<Q", extra, at)[0])
                    at += 8
                else:
                    values.append(field)
            return values[0], values[1], values[2]
        pos += 4 + length
    raise ValueError("ZIP64 markers without a ZIP64 extended information extra field")


def read_directory(url: str, length: int) -> List[Member]:
    """The central directory of a remote archive of length bytes: its tail (at most the last TAIL_MAX bytes) in
    one Range, the ZIP64 end record in a second only when it lies before the tail, the directory in one more
    unless the tail holds it (at most DIRECTORY_MAX bytes). ValueError when the bytes are no ZIP archive."""
    if length < EOCD_SIZE:
        raise ValueError(f"{length} bytes: too short for a ZIP archive")
    tail_start = length - min(length, TAIL_MAX)
    tail, _, _ = ranged(url, tail_start, length - 1, DIRECTORY_TIMEOUT_S)
    entries, size, offset, record = end_record(tail, tail_start)
    if record is not None:
        if record >= tail_start and record + ZIP64_EOCD_SIZE <= length:
            body = tail[record - tail_start:record - tail_start + ZIP64_EOCD_SIZE]
        else:
            body, _, _ = ranged(url, record, record + ZIP64_EOCD_SIZE - 1, DIRECTORY_TIMEOUT_S)
        entries, size, offset = zip64_end_record(body)
    if size > DIRECTORY_MAX:
        raise ValueError(f"a central directory of {size} bytes (at most {DIRECTORY_MAX})")
    if offset + size > length:
        raise ValueError("the central directory reaches beyond the archive")
    if size == 0:
        return []
    if offset >= tail_start:
        data = tail[offset - tail_start:offset - tail_start + size]
    else:
        data, _, _ = ranged(url, offset, offset + size - 1, DIRECTORY_TIMEOUT_S)
    return central_directory(data, entries)


def head(url: str) -> Tuple[int, Optional[str]]:
    """(length, ETag) of a remote file by HEAD (no redirect followed); IndexUnavailable unless it answers 200
    with a Content-Length."""
    net.rate_turn(url)
    try:
        with servicecounts.request(url) as counted:
            response = counted.got(net.session().head(url, headers=cache.http_headers(), timeout=DIRECTORY_TIMEOUT_S,
                                                      allow_redirects=False, verify=net.verify(url)), read=False)
    except requests.RequestException as e:
        raise IndexUnavailable(f"ZIP archive {cache.clean_url(url)}: {cache.clean_error(e)}") from e
    length = response.headers.get("Content-Length", "")
    if response.status_code != 200 or not length.isdigit():
        raise IndexUnavailable(f"ZIP archive {cache.clean_url(url)}: HTTP {response.status_code}"
                               + ("" if response.status_code != 200 else ", no Content-Length"))
    return int(length), response.headers.get("ETag")


# A share's token in the address a stable link redirects to (Nextcloud: .../index.php/s/<token>)
SHARE_TOKEN = re.compile(r"/s/([A-Za-z0-9]{6,64})(?:[/?#]|$)")


def share_token(link: str) -> str:
    """The token of the share a stable link redirects to (a HEAD, the redirect not followed: LVGL's goes to
    http); IndexUnavailable without one."""
    net.rate_turn(link)
    try:
        with servicecounts.request(link) as counted:
            response = counted.got(net.session().head(link, headers=cache.http_headers(), timeout=DIRECTORY_TIMEOUT_S,
                                                      allow_redirects=False, verify=net.verify(link)), read=False)
    except requests.RequestException as e:
        raise IndexUnavailable(f"share {cache.clean_url(link)}: {cache.clean_error(e)}") from e
    location = response.headers.get("Location", "")
    match = SHARE_TOKEN.search(location)
    if response.status_code not in (301, 302, 303, 307, 308) or not match:
        raise IndexUnavailable(f"share {cache.clean_url(link)}: HTTP {response.status_code}, no share's token in "
                               f"its redirect ({cache.clean_url(location) or 'none'})")
    return match.group(1)


class ZipDirectories(MetalinkFiles):
    """The members of remote ZIP archives that hold a region's square tiles, each member a tile named by its
    corner: archives, the archives' URLs in the order of their precedence (a tile in two archives is taken from
    the first), each with "{token}" where share's token goes when share is given (a stable link redirecting to
    the share: share_token, resolved again with every reading of the directories); name, a regular expression of
    the members' names with the groups east and north (in tile_m units of crs) and, if the names carry it, year
    (searched: any folder; case as the expression says).

    The directories are read once per TTL ("sheet-index") for all 0.25° tiles: a HEAD of each archive (its
    length and ETag), then its central directory by Range (read_directory), the members matching name kept in
    <top>/zipdir/<key>.json.gz with the token and each archive's URL, ETag and length; when read again, an
    archive whose ETag and length did not change keeps its kept members. An archive that cannot be had (404,
    an error, not a ZIP archive) is IndexUnavailable, and nothing is kept then. table(force=True) reads them
    again now (a 404 of an archive or a moved member: ZipMemberTiles' renew).

    Every member is listed as {year (0 without one), godlo ("<east>_<north>"), url (its archive's), member,
    method, flags, crc, size (compressed), usize, offset, length (the archive's), crs, res, sha256 (None),
    extent}."""

    def __init__(self, archives: Sequence[str], name: str, crs: str, res: float, top: str, key: str,
                 tile_m: float = 1000, share: Optional[str] = None):
        super().__init__(archives, name, crs, res, top, key, tile_m)
        self.share = share
        self.url = share or archives[0]

    def table_path(self, cache_dir: str) -> str:
        return os.path.join(cache_dir, self.top, "zipdir", f"{self.key}.json.gz")

    @staticmethod
    def _kept(path: str) -> Optional[Dict]:
        try:
            with gzip.open(path, "rt", encoding="utf-8") as kept_file:
                return json.load(kept_file)
        except (OSError, ValueError):
            return None

    def _download(self, previous: Optional[Dict] = None) -> Dict:
        """The kept directories, read again where an archive's ETag or length changed since previous."""
        token = share_token(self.share) if self.share else None
        before = {a["name"]: a for a in (previous or {}).get("archives", [])}
        archives = []
        for template in self.urls:
            url = template.format(token=token) if token else template
            length, etag = head(url)
            old = before.get(template)
            if old and etag and old.get("etag") == etag and old.get("length") == length:
                members = old["members"]
            else:
                try:
                    listed = read_directory(url, length)
                except (ValueError, ArchiveChanged, RangeRefused, RuntimeError, requests.RequestException) as e:
                    raise IndexUnavailable(f"ZIP archive {cache.clean_url(url)}: {cache.clean_error(e)}") from e
                members = [list(m) for m in listed if self.name.search(m.name)]
            archives.append({"name": template, "url": url, "etag": etag, "length": length, "members": members})
        return {"share": self.share, "token": token, "archives": archives}

    def table(self, force: bool = False) -> List[Dict]:
        """The kept members, reading the directories when not kept or due (at most once per process), or now
        with force."""
        cache_dir, ttl = self.cache_dir, cache.TTL_DAYS["sheet-index"]
        path = self.table_path(cache_dir)
        due = lambda: force or cache.due(cache_dir, path, update=self.update, ttl=ttl)  # noqa: E731
        if force or (path not in self._asked and due()):
            with net.tile_lock(cache_dir, path):  # another search may be reading them now
                if due():
                    kept = self._download(self._kept(path))
                    os.makedirs(os.path.dirname(path), exist_ok=True)
                    tmp = _part(path)
                    with gzip.open(tmp, "wt", encoding="utf-8") as out:
                        json.dump(kept, out)
                    os.replace(tmp, path)
                    cache.record(cache_dir, path, url=self.url)
            self._asked.add(path)
            self._tables.pop(path, None)
        if path not in self._tables:
            kept = self._kept(path)
            if kept is None:
                raise IndexUnavailable(f"{cache.relative(cache_dir, path)} cannot be read")
            self._tables[path] = self._items(kept)
        return self._tables[path]

    def _items(self, kept: Dict) -> List[Dict]:
        items, seen = [], set()
        for archive in kept["archives"]:
            for name, method, flags, crc, size, usize, offset in archive["members"]:
                match = self.name.search(name)
                if not match:
                    continue
                east, north = int(match.group("east")), int(match.group("north"))
                year = int(match.groupdict().get("year") or 0)
                if (east, north, year) in seen:  # in an earlier archive too (identical at district borders)
                    continue
                seen.add((east, north, year))
                m = self.tile_m
                items.append({"year": year, "godlo": f"{east}_{north}", "url": archive["url"], "member": name,
                              "method": method, "flags": flags, "crc": crc, "size": size, "usize": usize,
                              "offset": offset, "length": archive["length"], "crs": self.crs, "res": self.res,
                              "sha256": None, "extent": [east * m, north * m, (east + 1) * m, (north + 1) * m]})
        return items


@dataclass(frozen=True)
class ZipTile(ShaTile):
    """A tile of a ZipPerTile layer (key: its member's CRC-32 in 8 hex digits) with what ZipMember reads: its
    archive's url and length, the member's name, local header's offset, method, flags, CRC-32, compressed size
    (size) and uncompressed size (usize)."""
    member: str = ""
    offset: int = 0
    method: int = 8
    flags: int = 0
    crc: int = 0
    usize: int = 0
    length: int = 0


class ZipPerTile(ShaPerTile):
    """ShaPerTile whose tiles are members of ZIP archives, known by their CRC-32 (a changed member has another
    name in the cache and is read again; the older file is deleted then):
    <folder>/<east // 10>_<north // 10>/<east>_<north>[_<year>]_<crc8>.tif."""

    @staticmethod
    def tile(item: Dict) -> ZipTile:
        east, north = (int(v) for v in item["godlo"].split("_"))
        return ZipTile(east, north, item["year"], f"{item['crc']:08x}", item["url"], None, item["size"],
                       item["member"], item["offset"], item["method"], item["flags"], item["crc"], item["usize"],
                       item["length"])

