"""ZipMember: one member of a remote ZIP archive read by an HTTP Range request (its local header and compressed
data), inflated, checked against its CRC-32 and written as a tile; and `ranged`, the Range request itself, which
the ZIP directories of sources/indexes/zipdir.py share.

The ZIP format is PKWARE's APPNOTE.TXT, version 6.3.10 (2022-11-01); the sections named below are its."""

import re
import struct
import zlib
from typing import Callable, Dict, Optional, Tuple

import numpy as np
import rasterio as rio
import requests

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


class ArchiveChanged(RuntimeError):
    """The archive is no longer where its directory says, or not what it said: a 404 (the share's address
    changed), or a local header that is not the member's (the archive was replaced)."""


class RangeRefused(RuntimeError):
    """The server answered a Range request with the whole file (HTTP 200): closed unread."""


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
        if response.status_code != 206:
            raise RuntimeError(f"HTTP {response.status_code} for {cache.clean_url(url)}")
        content_range = response.headers.get("Content-Range", "").strip()
        match = re.fullmatch(r"bytes (\d+)-(\d+)/(\d+|\*)", content_range)
        if not match or (int(match.group(1)), int(match.group(2))) != (first, last):
            counted.outcome = "other"
            raise RuntimeError(f"{cache.clean_url(url)}: Content-Range {content_range!r}, bytes {first}-{last} asked")
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


class ZipMember(Reader):
    """One member of a remote ZIP archive per tile (a request with url, member, offset, method, flags, crc,
    size (compressed), usize and length (the archive's), as sources/indexes/zipdir.py's ZipTile carries
    them): one Range GET of the local header and the compressed data (the local header's own name and extra
    lengths: 4.3.7; a second, small Range only when the first was short), deflated (8) or stored (0) members
    only (4.4.5; others and encrypted ones an error), inflated with zlib (raw deflate) and checked against the
    CRC-32 and size of the central directory (4.4.7-4.4.9): a mismatch is asked again (net.RETRIES), then an
    error, never cached. The member (a GeoTIFF) is written again as a tile (float32, NaN for no data and below
    layer.VALID_MIN), in crs's name if given; with floor, drop_below(floor, ring) first.

    A 404 or a local header that is not the member's (ArchiveChanged) calls renew(request): a newer request of
    the same member (the share's address resolved again, the directory read again) is tried once; without one
    the tile fails."""

    def __init__(self, description: str, crs: Optional[str] = None, floor: Optional[float] = None, ring: int = 0,
                 renew: Optional[Callable[[object], Optional[object]]] = None):
        self.description, self.crs, self.floor, self.ring, self.renew = description, crs, floor, ring, renew

    def url(self, request) -> Optional[str]:
        return request.url

    def fetch(self, request, path: str) -> Fetched:
        where = f"{self.description} tile {request.godlo}"
        try:
            data, received = self._member(request, where)
        except ArchiveChanged as e:
            renewed = self.renew(request) if self.renew else None
            if renewed is None:
                raise RuntimeError(f"Could not download {where}: {e}") from None
            request = renewed
            try:
                data, received = self._member(request, where)
            except ArchiveChanged as again:
                raise RuntimeError(f"Could not download {where}: {again}") from None
        self._write(data, path, where)
        return Fetched(received, request.url)

    def _member(self, request, where: str) -> Tuple[bytes, int]:
        """The member's inflated bytes and the bytes received."""
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
            except (requests.RequestException, RuntimeError, ValueError, zlib.error) as e:
                error = e
                net._sleep(attempt)
        raise RuntimeError(f"Could not download {where}: {cache.clean_error(error)}")

    @staticmethod
    def _inflate(raw: bytes, request) -> bytes:
        """The member's bytes from its compressed data; ValueError unless size and CRC-32 are the directory's."""
        if request.method == DEFLATED:
            inflater = zlib.decompressobj(-15)
            data = inflater.decompress(raw, request.usize + 1)  # never more than one byte beyond the size
            if not inflater.eof:
                raise ValueError("the deflated data does not end where the directory says")
        else:
            data = raw
        if len(data) != request.usize or zlib.crc32(data) != request.crc:
            raise ValueError(f"CRC-32 or size differs from the directory's ({len(data)} of {request.usize} bytes)")
        return data

    def _write(self, data: bytes, path: str, where: str):
        try:
            with rio.io.MemoryFile(data) as memfile, memfile.open() as src:
                if src.count != 1:
                    raise RuntimeError(f"{where}: {src.count} bands, one expected")
                band = _clean(src.read(1, masked=True).astype(np.float32).filled(np.nan), copy=False)
                crs, transform = self.crs or src.crs, src.transform
        except rio.errors.RasterioError as e:
            raise RuntimeError(f"{where}: not a raster ({e})") from None
        drop_below(band, self.floor, self.ring)
        _write_tile(path, band, crs, transform)
