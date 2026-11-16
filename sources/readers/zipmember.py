"""ZipMember: one member of a remote ZIP archive read by an HTTP Range request (its local header and compressed
data), inflated, checked against its CRC-32 and written as a tile; and `ranged`, the Range request itself, which
the ZIP directories of sources/indexes/zipdir.py share.

The ZIP format is PKWARE's APPNOTE.TXT, version 6.3.10 (2022-11-01); the sections named below are its."""

import contextlib
import re
import struct
import threading
import zlib
from typing import Callable, Dict, NamedTuple, Optional, Tuple

import numpy as np
import rasterio as rio
import requests
from rasterio.transform import Affine

import cache
import servicecounts

from .. import net
from ..composed import Reader
from ..layer import Fetched, _clean, _write_tile

# 4.3.7: the local file header, its signature and fixed size (the name and the extra field follow)
LOCAL_SIG = b"PK\x03\x04"
LOCAL_SIZE = 30
# 4.4.4: general purpose bit flags: bit 0 the member is encrypted, bit 11 its name is UTF-8 (else CP437)
FLAG_ENCRYPTED = 0x0001
FLAG_UTF8 = 0x0800
# 4.4.5: the compression methods read: 0 stored, 8 deflated (zlib's raw deflate, window bits -15)
STORED, DEFLATED = 0, 8
# Bytes beyond the central directory's lengths of the name read with a member: the local header's extra field
# has a length of its own (4.3.7; a ZIP64 extra of 20 bytes in a local header whose central entry has none),
# so a second, small Range is needed only when the local extra is longer than this
HEADER_SLACK = 1024
# The largest member read (Saarland's members: 0.8-2.8 MB deflated, 4 MB inflated)
MEMBER_MAX = 64_000_000
# The smallest range asked: never a single byte (a "Range: bytes=0-0" is not ours to send)
RANGE_MIN = 2
# GDAL's XYZ driver (3.12) reads points written in columns through a cache it keeps once per process: two such members
# read at once by two threads evict each other's on every block, 46 s for the pair instead of 0.3 s each (Bremerhaven's
# DGM1 474_5936, measured 2026-11-16; points in rows are read at once without it): they are read one at a time
COLUMNS_LOCK = threading.Lock()


class ArchiveChanged(RuntimeError):
    """The archive is no longer where its directory says, or not what it said: a 404 (the share's address
    changed), or a local header that is not the member's (the archive was replaced)."""


class MemberChanged(ArchiveChanged):
    """The member's bytes are not what the directory says (its CRC-32 or size, a deflate stream that does not end
    there): the archive may have been replaced under the same name with this member made again."""


class Mismatch(ValueError):
    """A member's inflated bytes differ from its directory's CRC-32 or size (ZipMember._inflate)."""


class RangeRefused(RuntimeError):
    """The server answered a Range request with the whole file (HTTP 200): closed unread."""


class RangeMismatch(RuntimeError):
    """The server answered another range than the one asked, or none (416: the range lies beyond the file's end):
    the file is shorter now; total: the file's size its Content-Range names (None: unknown); unsatisfiable: a 416."""

    def __init__(self, message: str, total: Optional[int] = None, unsatisfiable: bool = False):
        super().__init__(message)
        self.total, self.unsatisfiable = total, unsatisfiable


class WrongShape(RuntimeError):
    """A member that opens as a raster but not as a tile of one band: what its bytes are, the same on every
    reading (a reader may leave such a tile to its gap filler: PackageMember)."""


# What renew may answer besides a request or None: the directory read again lists another version of the member
# (another CRC-32: another tile), so this request cannot be read; fetch fails at once (no reading of it again)
MEMBER_REMADE = object()


def ranged(url: str, first: int, last: int, timeout: int = 120) -> Tuple[bytes, Optional[int], Dict[str, str]]:
    """The bytes first..last (inclusive) of a remote file by one Range GET (RFC 9110, 14.2), with the total size
    its Content-Range names (None for "*") and the answer's headers. Through net: the host's turn (rate_turn),
    the thread's session, our headers, counted (servicecounts). The answer must be 206 with exactly the asked
    Content-Range, not content-encoded, and at most last - first + 1 bytes are read: a 200 (the whole file) is
    RangeRefused and closed unread, a 404 ArchiveChanged, an answer cut short or longer a RuntimeError (as any
    other status). The caller retries."""
    if first < 0 or last - first + 1 < RANGE_MIN:
        raise ValueError(f"range {first}-{last}: at least {RANGE_MIN} bytes")
    expected = last - first + 1
    headers = {**cache.http_headers(), "Range": f"bytes={first}-{last}", "Accept-Encoding": "identity"}
    net.rate_turn(url)
    with servicecounts.request(url) as counted, \
            net.session().get(url, headers=headers, stream=True, timeout=timeout, verify=net.verify(url),
                              allow_redirects=False) as response:
        counted.got(response, read=False)
        if response.status_code == 404:
            raise ArchiveChanged(f"HTTP 404 for {cache.clean_url(url)}")
        if response.status_code == 200:
            counted.outcome = "other"
            raise RangeRefused(f"{cache.clean_url(url)} answered a range request with the whole file (HTTP 200); "
                               f"not read")
        if response.status_code == 416:  # Range Not Satisfiable (RFC 9110, 15.5.17): "bytes */<size>" if given
            counted.outcome = "other"
            unsatisfied = re.fullmatch(r"bytes \*/(\d+)", response.headers.get("Content-Range", "").strip())
            raise RangeMismatch(f"HTTP 416 for {cache.clean_url(url)}, bytes {first}-{last} asked",
                                int(unsatisfied.group(1)) if unsatisfied else None, unsatisfiable=True)
        if response.status_code != 206:
            raise RuntimeError(f"HTTP {response.status_code} for {cache.clean_url(url)}")
        content_range = response.headers.get("Content-Range", "").strip()
        match = re.fullmatch(r"bytes (\d+)-(\d+)/(\d+|\*)", content_range)
        if not match or (int(match.group(1)), int(match.group(2))) != (first, last):
            counted.outcome = "other"
            total = int(match.group(3)) if match and match.group(3) != "*" else None
            raise RangeMismatch(f"{cache.clean_url(url)}: Content-Range {content_range!r}, bytes {first}-{last} asked",
                                total)
        if response.headers.get("Content-Encoding", "identity").lower() not in ("", "identity"):
            counted.outcome = "other"
            raise RuntimeError(f"{cache.clean_url(url)}: content-encoded ({response.headers['Content-Encoding']})")
        body = bytearray()
        for chunk in response.iter_content(1 << 16):
            counted.add(len(chunk))
            body += chunk
            if len(body) > expected:
                raise RuntimeError(f"{cache.clean_url(url)}: more than the {expected} bytes asked")
        if len(body) != expected:
            raise RuntimeError(f"{cache.clean_url(url)}: cut short, {len(body)} of {expected} bytes")
        total = None if match.group(3) == "*" else int(match.group(3))
        return bytes(body), total, dict(response.headers)


def member_name(raw: bytes, flags: int) -> str:
    """A member's name as the archive writes it (4.4.4 bit 11: UTF-8, else IBM code page 437; APPNOTE D.1)."""
    return raw.decode("utf-8" if flags & FLAG_UTF8 else "cp437", "replace")


def local_header(body: bytes) -> Tuple[int, int, int]:
    """(flags, name length, extra length) of a local file header (4.3.7) at the start of body; ArchiveChanged
    when it is none."""
    if len(body) < LOCAL_SIZE or body[:4] != LOCAL_SIG:
        raise ArchiveChanged("no local file header at the member's offset")
    flags, = struct.unpack_from("<H", body, 6)
    name_length, extra_length = struct.unpack_from("<HH", body, 26)
    return flags, name_length, extra_length


def drop_below(band: np.ndarray, floor: Optional[float], ring: int = 0) -> np.ndarray:
    """The band (float32, NaN for no data) with every pixel below floor made no data, and with ring > 0 also
    the pixels within ring pixels of one (a square dilation of (2 ring + 1)²: scipy.ndimage), in place. For an
    artifact of a survey: LVGL's 0 m patches (Saarland), whose rim of a pixel or two falls from the ground to
    the patch."""
    if floor is None:
        return band
    with np.errstate(invalid="ignore"):
        low = band < floor
    if not low.any():
        return band
    if ring > 0:
        from scipy import ndimage
        low = ndimage.binary_dilation(low, structure=np.ones((2 * ring + 1, 2 * ring + 1), dtype=bool))
    band[low] = np.nan
    return band


def xyz_in_columns(data: bytes) -> bool:
    """Whether a member is XYZ text whose first two points share their x (written in columns, as Bremerhaven's);
    False for anything else (a GeoTIFF, points in rows)."""
    try:
        head = data[:1024].decode("ascii")
    except UnicodeDecodeError:
        return False
    points = []
    for line in head.splitlines()[:4]:
        try:
            values = [float(v) for v in line.split()]
        except ValueError:
            continue  # the header line
        if len(values) == 3:
            points.append(values)
    return len(points) >= 2 and points[0][0] == points[1][0] and points[0][1] != points[1][1]


def xyz_rows(data: bytes) -> Optional[bytes]:
    """An XYZ text member ("x y z" a line, after a header line or not) with its lines in rows, north to south and
    west to east, for GDAL's XYZ driver: it reads points in columns only when none is missing ("does not support
    datasets organized by columns with missing values", GDAL 3.12), and points in rows with any missing (no data
    there). Bremerhaven's DGM1 and DOM1 are written in columns, and 41 of the DOM1's tiles hold part of their km. The
    lines are kept as they are (no number written again). None when data is no such text (a GeoTIFF)."""
    try:
        text = data.decode("ascii")
    except UnicodeDecodeError:
        return None
    lines = [line for line in text.splitlines() if line.strip()]
    header = []
    if lines:
        try:
            [float(v) for v in lines[0].split()]
        except ValueError:
            header, lines = lines[:1], lines[1:]
    if not lines:
        return None
    try:
        values = np.array(" ".join(lines).split(), dtype=np.float64)
    except ValueError:
        return None
    if values.size != 3 * len(lines):
        return None
    points = values.reshape(-1, 3)
    order = np.lexsort((points[:, 0], -points[:, 1]))
    return ("\n".join(header + [lines[i] for i in order]) + "\n").encode("ascii")


class TransformFix(NamedTuple):
    """A correction of a member's georeferencing before its tile is written, for archives whose files lie on the
    right grid but say so imprecisely: offset (dx, dy) metres added to the origin first (Bremen's Bremerhaven XYZ
    files carry the UTM zone in their eastings: (-32 000 000, 0)), then with snap the origin rounded to a multiple
    of snap metres (Hamburg's DGM1: 552999.9999999999 for 553000). A rounding of more than tolerance of a pixel is
    an error, never applied: it mends float noise, it never moves a member that lies off the grid. North-up
    members only (no rotation)."""
    offset: Tuple[float, float] = (0.0, 0.0)
    snap: Optional[float] = None
    tolerance: float = 1e-3  # pixels

    def apply(self, transform: Affine, where: str) -> Affine:
        if transform.b != 0 or transform.d != 0:
            raise RuntimeError(f"{where}: a rotated member ({transform})")
        x, y = transform.c + self.offset[0], transform.f + self.offset[1]
        if self.snap:
            snapped = (round(x / self.snap) * self.snap, round(y / self.snap) * self.snap)
            off = max(abs(snapped[0] - x) / abs(transform.a), abs(snapped[1] - y) / abs(transform.e))
            if off > self.tolerance:
                raise RuntimeError(f"{where}: the origin ({x}, {y}) lies {off:.3g} px off the {self.snap} m grid")
            x, y = snapped
        return Affine(transform.a, 0.0, x, 0.0, transform.e, y)


class ZipMember(Reader):
    """One member of a remote ZIP archive per tile (a request with url, member, offset, method, flags, crc,
    size (compressed), usize and length (the archive's), as sources/indexes/zipdir.py's ZipTile carries
    them): one Range GET of the local header and the compressed data (the local header's own name and extra
    lengths: 4.3.7; a second, small Range only when the first was short), deflated (8) or stored (0) members
    only (4.4.5; others and encrypted ones an error), inflated with zlib (raw deflate) and checked against the
    CRC-32 and size of the central directory (4.4.7-4.4.9): a mismatch is asked again (net.RETRIES), then an
    error, never cached. The member (a raster GDAL reads from memory: a GeoTIFF, an ERDAS Imagine file, or XYZ
    text: one GDAL refuses is read again with its points in rows, xyz_rows) is written again as a tile (float32,
    NaN for no data and below layer.VALID_MIN), in crs's name if given, else in that of the request's own crs if
    it has one (a tile of a package in several UTM zones), else as the member says; with floor, drop_below(floor,
    ring) first; with fix, its transform corrected first (TransformFix: an offset, a rounding to the grid); then
    placed(transform, width, height, request, where) gives the transform it is written with and the window of it
    kept, or refuses it (a subclass's check of where the member lies; here the member as it is).

    A 404 or a local header that is not the member's (ArchiveChanged) calls renew(request): a newer request of
    the same member (the share's address resolved again, the directory read again) is tried once; without one
    the tile fails. With renew, so does the first read whose bytes are not what the directory says (MemberChanged:
    an archive replaced under the same name, its member made again, where a header of the same name still stands);
    without a newer request the member is then asked again as before (a transfer's fault), and a mismatch again
    is the error; renew answering MEMBER_REMADE (the directory lists the member made again: another tile) fails
    the tile at once. A 416 or another range from a shorter archive counts as such a read (RangeMismatch). Without
    renew a mismatch is asked again as before."""
    rewrites = True  # the cached tile is written by _write_tile: reencode / cache migrate may convert it

    def __init__(self, description: str, crs: Optional[str] = None, floor: Optional[float] = None, ring: int = 0,
                 renew: Optional[Callable[[object], Optional[object]]] = None, fix: Optional[TransformFix] = None):
        self.description, self.crs, self.floor, self.ring, self.renew = description, crs, floor, ring, renew
        self.fix = fix

    def url(self, request) -> Optional[str]:
        return request.url

    def fetch(self, request, path: str) -> Fetched:
        where = f"{self.description} tile {request.godlo}"
        try:
            data, received = self._member(request, where, changed=self.renew is not None)
        except ArchiveChanged as e:
            renewed = self.renew(request) if self.renew else None
            if renewed is MEMBER_REMADE:
                raise RuntimeError(f"Could not download {where}: {e}; the directory lists the member made again "
                                   f"(another CRC-32): the next search reads it") from None
            if renewed is None:
                if not isinstance(e, MemberChanged):
                    raise RuntimeError(f"Could not download {where}: {e}") from None
                data, received = self._member(request, where)  # the directory says the same: asked again
            else:
                request = renewed
                try:
                    data, received = self._member(request, where)
                except ArchiveChanged as again:
                    raise RuntimeError(f"Could not download {where}: {again}") from None
        self._write(data, path, where, request)
        return Fetched(received, request.url)

    def _member(self, request, where: str, changed: bool = False) -> Tuple[bytes, int]:
        """The member's inflated bytes and the bytes received; with changed, bytes that are not the directory's
        raise MemberChanged at once (else they are asked again, net.RETRIES, then an error)."""
        if request.method not in (STORED, DEFLATED):
            raise RuntimeError(f"{where}: compression method {request.method} (only 0 and 8 are read)")
        if request.flags & FLAG_ENCRYPTED:
            raise RuntimeError(f"{where}: an encrypted member")
        if request.size > MEMBER_MAX or request.usize > MEMBER_MAX:
            raise RuntimeError(f"{where}: a member of {max(request.size, request.usize)} bytes (at most {MEMBER_MAX})")
        name = request.member.encode("utf-8" if request.flags & FLAG_UTF8 else "cp437", "replace")
        start = request.offset
        last = start + LOCAL_SIZE + len(name) + HEADER_SLACK + request.size - 1
        if request.length:
            last = min(last, request.length - 1)
        error: Optional[BaseException] = None
        for attempt in range(net.RETRIES):
            try:
                body, _, _ = ranged(request.url, start, last)
                received = len(body)
                _, name_length, extra_length = local_header(body)
                if member_name(body[LOCAL_SIZE:LOCAL_SIZE + name_length], request.flags) != request.member:
                    raise ArchiveChanged(f"the local header at {start} is not {request.member}'s")
                data_start = LOCAL_SIZE + name_length + extra_length
                need = data_start + request.size
                if len(body) < need:  # a local extra field longer than HEADER_SLACK
                    more, _, _ = ranged(request.url, start + len(body), start + need - 1)
                    received += len(more)
                    body += more
                data = self._inflate(body[data_start:need], request)
                return data, received
            except (ArchiveChanged, RangeRefused):
                raise
            except (Mismatch, zlib.error) as e:
                if changed:
                    raise MemberChanged(f"{request.member}: {cache.clean_error(e)}") from None
                error = e
                net._sleep(attempt)
            except RangeMismatch as e:  # the archive is shorter now than where its directory put the member
                if changed and (e.unsatisfiable or (e.total is not None and request.length
                                                    and e.total != request.length)):
                    raise MemberChanged(f"{request.member}: the archive has {e.total or 'fewer'} bytes, its "
                                        f"directory was read from {request.length}") from None
                error = e
                net._sleep(attempt)
            except (requests.RequestException, RuntimeError, ValueError) as e:
                error = e
                net._sleep(attempt)
        raise RuntimeError(f"Could not download {where}: {cache.clean_error(error)}")

    @staticmethod
    def _inflate(raw: bytes, request) -> bytes:
        """The member's bytes from its compressed data; Mismatch unless size and CRC-32 are the directory's."""
        if request.method == DEFLATED:
            inflater = zlib.decompressobj(-15)
            data = inflater.decompress(raw, request.usize + 1)  # never more than one byte beyond the size
            if not inflater.eof:
                raise Mismatch("the deflated data does not end where the directory says")
        else:
            data = raw
        if len(data) != request.usize or zlib.crc32(data) != request.crc:
            raise Mismatch(f"CRC-32 or size differs from the directory's ({len(data)} of {request.usize} bytes)")
        return data

    def placed(self, transform: Affine, width: int, height: int, request,
               where: str) -> Tuple[Affine, Optional[rio.windows.Window]]:
        """The transform to write the member with and the window of it to keep (None: all of it); RuntimeError
        when the member does not lie where its tile is (a subclass's check; here the transform as it is, all)."""
        return transform, None

    def _write(self, data: bytes, path: str, where: str, request=None):
        band, crs, transform = self.raster(data, where, request)
        drop_below(band, self.floor, self.ring)
        _write_tile(path, band, crs, transform)

    def raster(self, data: bytes, where: str, request=None):
        """(band, crs, transform) of a member's bytes as its tile is written, before drop_below: the band float32
        with NaN for no data, in crs's name if given (else the request's, else the file's), the transform fixed
        (TransformFix) and placed (placed: the window kept); an XYZ member GDAL refuses is read again with its
        points in rows (xyz_rows); one in columns under COLUMNS_LOCK. Only GDAL's errors are caught here (a
        subclass's refusal from placed passes). (tools/check_source.py reads a member again by its own rules, not
        through this: its file check finds a fix that is wrong.)"""
        try:
            with COLUMNS_LOCK if xyz_in_columns(data) else contextlib.nullcontext():
                return self._raster(data, where, request)
        except rio.errors.RasterioError as e:
            rows = xyz_rows(data)  # an XYZ member in columns with points missing: read again in rows
            if rows is None:
                raise RuntimeError(f"{where}: not a raster ({e})") from None
            try:
                return self._raster(rows, where, request)
            except rio.errors.RasterioError as again:
                raise RuntimeError(f"{where}: not a raster ({again})") from None

    def _raster(self, data: bytes, where: str, request=None):
        """(band, crs, transform) of a member's bytes: float32, NaN for no data, the CRS the reader's, else the
        request's, else the file's; the transform fixed, then placed and the band cut to placed's window;
        WrongShape for more than one band."""
        with rio.io.MemoryFile(data) as memfile, memfile.open() as src:
            if src.count != 1:
                raise WrongShape(f"{where}: {src.count} bands, one expected")
            band = _clean(src.read(1, masked=True).astype(np.float32).filled(np.nan), copy=False)
            crs, transform = self.crs or getattr(request, "crs", None) or src.crs, src.transform
            if self.fix is not None:
                transform = self.fix.apply(transform, where)
            transform, window = self.placed(transform, src.width, src.height, request, where)
            if window is not None:
                band = band[window.toslices()]
        return band, crs, transform
