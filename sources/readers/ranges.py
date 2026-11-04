"""Ranges: a remote file read through HTTP range requests of our own, for GDAL through rasterio's opener (the
windows of a group of blocks, windows.read_group).

GDAL's /vsicurl/ reads the tiles of a window in one request, but once GDAL's own threads decode them
(GDAL_NUM_THREADS > 1, what lets GTiff fetch a big window's tiles exactly) a tile's answer cut short is neither
asked again nor reported: its pixels come back wrong without an error (measured 2026-11-04). Here GDAL asks for
the bytes it needs (the tiles of a window in one call, rasterio's MultiByteRangeResourceContainer) and every range
is asked by requests and taken only whole: HTTP 206 with the Content-Range asked and as many bytes, else asked
again (net.RETRIES, net._sleep), then an error; GDAL decodes what came, in the calling thread. Each request waits
for its turn (net.rate_turn) and is counted with its bytes (servicecounts); the caller holds the host's slot.
"""

import bisect
import contextlib
import os
import re
import uuid
from typing import Iterator, List, Optional, Sequence, Tuple
from urllib.parse import urlsplit

import rasterio as rio
import requests
from rasterio.abc import MultiByteRangeResourceContainer

import cache
import servicecounts

from .. import net

CHUNK = 64 * 1024  # bytes asked at least by GDAL's plain reads (the header, the arrays of tile offsets)
TIMEOUT = 120      # seconds, as GDAL_HTTP_TIMEOUT of net._gdal_http
# Ranges this close are asked as one (the gap's bytes thrown away): a COG's tiles in a row lie a few bytes
# apart (each tile's size before it and its last bytes again after it), so a row of a window is one request
MERGE_GAP = 16 * 1024


class Missing(Exception):
    """The file is not there (HTTP 404)."""


def get_range(url: str, first: int, last: int) -> Tuple[bytes, int]:
    """Bytes first..last of url and the file's size, whole or not at all: HTTP 206 whose Content-Range starts at
    first and ends at last (or at the end of the file, when last lies beyond it) with as many bytes; anything else
    (an answer cut short, another range, a 5xx) asked again up to net.RETRIES times, a 429 or 503 after a longer
    pause, then RuntimeError. Raises Missing for a 404."""
    last_error = None
    for attempt in range(net.RETRIES):
        slow_down = False
        try:
            net.rate_turn(url)
            with servicecounts.request(url) as counted:
                headers = dict(cache.http_headers(), Range=f"bytes={first}-{last}")
                response = counted.got(net.session().get(url, headers=headers, timeout=TIMEOUT,
                                                         verify=net.verify(url)))
                if response.status_code == 404:
                    raise Missing(url)
                match = re.fullmatch(r"bytes (\d+)-(\d+)/(\d+)", response.headers.get("content-range", ""))
                if response.status_code == 206 and match:
                    start, end, size = (int(g) for g in match.groups())
                    if start == first and end == min(last, size - 1) and len(response.content) == end - start + 1:
                        return response.content, size
                if response.status_code == 206:
                    counted.outcome = "connection"  # another range, or fewer bytes than it names
                slow_down = response.status_code in (429, 503)
                raise RuntimeError(f"HTTP {response.status_code} for bytes {first}-{last}: "
                                   f"{response.headers.get('content-range') or response.text[:200]}")
        except Missing:
            raise
        except (requests.RequestException, RuntimeError) as e:
            last_error = e
            net._sleep(attempt + 3 if slow_down else attempt)
    raise RuntimeError(cache.clean_error(last_error))


def runs(offsets: Sequence[int], sizes: Sequence[int], gap: int = MERGE_GAP) -> List[Tuple[int, int]]:
    """The ranges (offset, size) merged where the next begins at most gap bytes after one ends: (first, last) bytes
    of each run."""
    merged: List[List[int]] = []
    for offset, size in sorted(zip(offsets, sizes)):
        if size <= 0:
            continue
        if merged and offset <= merged[-1][1] + 1 + gap:
            merged[-1][1] = max(merged[-1][1], offset + size - 1)
        else:
            merged.append([offset, offset + size - 1])
    return [(a, b) for a, b in merged]


class RangeFile:
    """A remote file as a Python file object for GDAL (read, seek, tell, close) and a MultiByteRangeResource
    (get_byte_ranges: the tiles of a window in one call). Plain reads are asked in chunks of CHUNK and kept; the
    ranges of get_byte_ranges are asked as they are (merged where they touch) and not kept. prefetch fetches the
    tiles of the strip GDAL reads next beforehand, a request per run, and both kinds of read take what they can
    from them, so how GTiff happens to read a window (in one multi-range call up to some size, beyond it plain
    reads, tile by tile) costs no requests of its own. They never raise to GDAL (an exception in rasterio's
    callbacks stays set and breaks the next call): a failure is kept in `error` and the read answers no bytes
    (read) or zeros (get_byte_ranges), which GDAL may well decode, so the caller checks `error` after every open
    and read and drops what was read then."""

    def __init__(self, url: str):
        self.url, self.pos = url, 0
        self.chunks = {}
        self.error: Optional[BaseException] = None
        first, self.size = get_range(url, 0, CHUNK - 1)  # its size, and the header's first bytes
        self.chunks[0] = first
        self.received = len(first)
        self.runs: List[Tuple[int, bytes]] = []  # prefetched (offset, bytes), by offset

    def prefetch(self, ranges: Sequence[Tuple[int, int]]):
        """Fetch the ranges (offset, size), merged as get_byte_ranges merges them, in place of those fetched
        before: the reads within them are served from memory until the next prefetch. Raises (called by us)."""
        self.runs = []
        if not ranges:
            return
        offsets, sizes = zip(*ranges)
        for first, last in runs(offsets, sizes):
            data, _ = get_range(self.url, first, min(last, self.size - 1))
            self.received += len(data)
            self.runs.append((first, data))

    def _prefetched(self, offset: int, size: int) -> Optional[bytes]:
        """Bytes offset..offset+size from the prefetched runs, when one holds them all."""
        k = bisect.bisect_right([start for start, _ in self.runs], offset) - 1
        if k >= 0:
            start, data = self.runs[k]
            if offset + size <= start + len(data):
                return data[offset - start:offset - start + size]
        return None

    def _chunk(self, k: int) -> bytes:
        if k not in self.chunks:
            start = k * CHUNK
            self.chunks[k], _ = get_range(self.url, start, min(start + CHUNK, self.size) - 1)
            self.received += len(self.chunks[k])
        return self.chunks[k]

    def read(self, n: int = -1) -> bytes:
        try:
            n = self.size - self.pos if n is None or n < 0 else min(n, self.size - self.pos)
            ready = self._prefetched(self.pos, n) if self.runs else None
            if ready is not None:
                self.pos += n
                return ready
            out = bytearray()
            while len(out) < n:
                at = self.pos + len(out)
                chunk = self._chunk(at // CHUNK)
                out += chunk[at % CHUNK:at % CHUNK + n - len(out)]
            self.pos += n
            return bytes(out)
        except BaseException as e:
            self.error = self.error or e
            return b""

    def get_byte_ranges(self, offsets: Sequence[int], sizes: Sequence[int]) -> List[bytes]:
        try:
            out = [self._prefetched(o, n) if self.runs and n > 0 else None for o, n in zip(offsets, sizes)]
            missing = [(o, n) for o, n, ready in zip(offsets, sizes, out) if ready is None and n > 0]
            got = {}
            for first, last in runs([o for o, _ in missing], [n for _, n in missing]):
                got[first], _ = get_range(self.url, first, last)
                self.received += len(got[first])
            starts = sorted(got)
            for k, (offset, size) in enumerate(zip(offsets, sizes)):
                if out[k] is None:
                    start = starts[bisect.bisect_right(starts, offset) - 1] if size > 0 else 0
                    out[k] = got[start][offset - start:offset - start + size] if size > 0 else b""
            return out
        except BaseException as e:
            self.error = self.error or e
            return [bytes(size) for size in sizes]

    def seek(self, offset: int, whence: int = os.SEEK_SET) -> int:
        self.pos = {os.SEEK_SET: 0, os.SEEK_CUR: self.pos, os.SEEK_END: self.size}[whence] + offset
        return self.pos

    def tell(self) -> int:
        return self.pos

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _Opener(MultiByteRangeResourceContainer):
    """rasterio's opener of one file: its key opens it, nothing else is there (GDAL's look for side files)."""

    def __init__(self, key: str, file: RangeFile):
        self.key, self.file = key, file

    def open(self, path: str, mode: str = "r", **kwds):
        if path != self.key:
            raise FileNotFoundError(path)
        return self.file

    def isfile(self, path: str) -> bool:
        return path == self.key

    def isdir(self, path: str) -> bool:
        return False

    def ls(self, path: str) -> List[str]:
        return []

    def mtime(self, path: str) -> int:
        return 0

    def rm(self, path: str) -> None:
        pass

    def size(self, path: str) -> int:
        return self.file.size if path == self.key else 0


@contextlib.contextmanager
def open_remote(url: str) -> Iterator[Tuple[rio.io.DatasetReader, RangeFile]]:
    """The dataset of a remote file read through RangeFile (raises Missing for a 404), and the RangeFile."""
    file = RangeFile(url)
    name = os.path.basename(urlsplit(url).path) or "file.tif"
    key = f"{uuid.uuid4().hex}/{name}"
    with rio.Env(GDAL_NUM_THREADS="1", GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR"):
        with rio.open(key, opener=_Opener(key, file)) as src:
            yield src, file
