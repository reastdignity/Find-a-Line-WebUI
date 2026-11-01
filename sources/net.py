"""HTTP requests with retries, the download slots of a host and the locks of cached tiles."""

import contextlib
import hashlib
import logging
import os
import random
import re
import threading
import time
from typing import Dict, Optional
from urllib.parse import urlsplit

import rasterio as rio
import requests
from filelock import FileLock, Timeout

import cache
import servicecounts

# Tile downloads from one host at a time across all processes of a data folder (several jobs
# of the web worker download at once), through lock files in cache/locks/hosts (host_slot);
# HOST_SLOTS_OF holds the hosts that need another number
HOST_SLOTS = 8
HOST_SLOTS_OF: Dict[str, int] = {}
TILE_LOCKS = 4096  # lock files of tiles (tile_lock): a tile's lock is one of these, by its path
LOCK_WAIT_S = 3600  # longest wait for a host slot or a tile's lock (a download in another job)
RETRIES = 3


def _get(url: str, params=None, timeout: int = 300, binary_types=("image", "octet", "tiff", "multipart")):
    """GET with retries; raises RuntimeError with the server message on failure (without the
    query of the URL or a key's value: cache.clean_error). Every attempt is counted (servicecounts,
    the host only; a 200 that is not data counts as `other`)."""
    last_error = None
    for attempt in range(RETRIES):
        try:
            with servicecounts.request(url) as counted:
                response = counted.got(requests.get(url, params=params, timeout=timeout,
                                                    headers=cache.http_headers()))
                content_type = response.headers.get("content-type", "")
                if response.status_code == 404:
                    return None
                if response.status_code != 200 or not any(t in content_type for t in binary_types):
                    if response.status_code == 200:
                        counted.outcome = "other"
                    raise RuntimeError(f"HTTP {response.status_code}: {response.text[:300]}")
            return response
        except (requests.RequestException, RuntimeError) as e:
            last_error = e
            _sleep(attempt)
    # No API key from a query in the message, and no value of a service key anywhere in it (a
    # server's answer may echo the token of its request: settings.redact through clean_error)
    raise RuntimeError(cache.clean_error(last_error))


def _sleep(attempt: int):
    """Exponential backoff with jitter (swisstopo's fair use asks for it), 0.5-1.5 times 2^attempt s."""
    time.sleep(2 ** attempt * (0.5 + random.random()))


def _locks(cache_dir: str, kind: str) -> str:
    folder = os.path.join(cache_dir, cache.LOCKS, kind)
    os.makedirs(folder, exist_ok=True)
    return folder


@contextlib.contextmanager
def host_slot(cache_dir: str, url: Optional[str]):
    """One of the HOST_SLOTS (HOST_SLOTS_OF) download slots of the host of url, across the
    threads and processes of a data folder: lock files <host>.<n>.lock, each tried in turn,
    waiting while all are taken. A file lock of the OS: a killed process releases it, and the
    files are a fixed few per host. Nothing to wait for without a remote host (a local mirror)."""
    host = urlsplit(url).hostname if url and re.match(r"https?://", url) else None
    if not host:
        yield
        return
    folder = _locks(cache_dir, "hosts")
    slots = list(range(HOST_SLOTS_OF.get(host, HOST_SLOTS)))
    deadline = time.monotonic() + LOCK_WAIT_S
    while True:
        random.shuffle(slots)  # waiters spread over the slots
        for n in slots:
            # A new instance per attempt: filelock's instances are per thread, and two of them
            # on one file exclude each other also within a process (Windows LockFileEx, flock)
            lock = FileLock(os.path.join(folder, f"{host}.{n}.lock"))
            try:
                lock.acquire(blocking=False)
            except Timeout:
                continue
            try:
                yield
            finally:
                lock.release()
            return
        if time.monotonic() > deadline:
            raise RuntimeError(f"{host} is busy with the downloads of other searches "
                               f"(waited {LOCK_WAIT_S // 60} min); try again later")
        time.sleep(0.1 + 0.2 * random.random())


@contextlib.contextmanager
def tile_lock(cache_dir: str, path: str):
    """The lock of a cached file, so two searches never download it at once (the second waits
    and then finds it cached). One of TILE_LOCKS lock files chosen by the path, so their number
    stays fixed (on Linux filelock leaves its files behind); two tiles sharing one only wait
    for each other."""
    digest = hashlib.sha256(cache.relative(cache_dir, path).encode()).digest()
    name = f"{int.from_bytes(digest[:4], 'big') % TILE_LOCKS:04d}.lock"
    lock = FileLock(os.path.join(_locks(cache_dir, "tiles"), name))
    try:
        lock.acquire(timeout=LOCK_WAIT_S)
    except Timeout:
        raise RuntimeError(f"{cache.relative(cache_dir, path)} is being downloaded by another search "
                           f"(waited {LOCK_WAIT_S // 60} min); try again later") from None
    try:
        yield
    finally:
        lock.release()


def _part(path: str) -> str:
    """A temporary name next to path, unique per process and thread (searches may run in parallel)."""
    return f"{path}.{os.getpid()}-{threading.get_ident()}.part"


def _remote(url: str) -> str:
    """What rasterio opens for a file of an index: /vsicurl/ (HTTP range requests) for a URL,
    a local path as it is (tests)."""
    return f"/vsicurl/{url}" if re.match(r"https?://", url) else url


# The HTTP statuses GDAL retries (GDAL_HTTP_RETRY_CODES, "Configuration options", "Networking
# options" of GDAL's documentation): its defaults (429, 500, 502-504) and 0, a request that got no
# answer at all (a connection aborted or reset, a timeout). A list replaces GDAL's default rules,
# which retry only some curl errors by their text ("Connection reset by peer", "Operation timed
# out"; not "Connection was aborted" of Windows). GDAL matches a status as a substring of the
# list, so no other status may be a part of it (0 is part of none of the others here).
GDAL_RETRY_CODES = "0,429,500,502,503,504"


def _gdal_http() -> rio.Env:
    """GDAL's settings for reading windows of remote files: our User-Agent, no directory
    listing, retries of failed requests (GDAL_RETRY_CODES), neighbouring blocks in one request.
    Blocks are read in the calling thread (GDAL_NUM_THREADS=1, whatever the environment says):
    with more, the GTiff driver fetches and decodes them in its own threads, whose errors go to
    GDAL's default handler (printed to stderr) instead of the caller's, so gdal_errors would not
    see a failed read there, which then comes back as zeros."""
    return rio.Env(GDAL_HTTP_USERAGENT=cache.http_headers()["User-Agent"],
                   GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif",
                   GDAL_HTTP_MAX_RETRY=str(RETRIES), GDAL_HTTP_RETRY_DELAY="2", GDAL_HTTP_TIMEOUT="120",
                   GDAL_HTTP_RETRY_CODES=GDAL_RETRY_CODES, GDAL_NUM_THREADS="1",
                   GDAL_HTTP_MULTIRANGE="YES", GDAL_HTTP_MERGE_CONSECUTIVE_RANGES="YES")


# GDAL's errors as rasterio logs them: an error (CE_Failure) that did not make the call fail is
# logged at INFO by the loggers of its error handlers (rasterio._err: log_error), never raised
_GDAL_LOGGERS = ("rasterio._env", "rasterio._err")
_GDAL_ERROR = "GDAL signalled an error"
_errors_of: Dict[int, list] = {}  # thread -> the GDAL errors logged in it while gdal_errors is open
_errors_lock = threading.Lock()


class _GdalErrors(logging.Filter):
    """Collects GDAL's errors for the threads in gdal_errors; passes a record on only as the
    loggers would have without it (INFO is enabled on them for this filter alone)."""

    def filter(self, record) -> bool:
        if record.levelno == logging.INFO and str(record.msg).startswith(_GDAL_ERROR):
            with _errors_lock:
                found = _errors_of.get(record.thread)
            if found is not None:
                found.append(str(record.args[-1]) if record.args else record.getMessage())
        return record.levelno >= logging.getLogger("rasterio").getEffectiveLevel()


def _install_filter():
    for name in _GDAL_LOGGERS:
        logger = logging.getLogger(name)
        if not any(isinstance(f, _GdalErrors) for f in logger.filters):
            logger.addFilter(_GdalErrors())
        if logger.getEffectiveLevel() > logging.INFO:
            logger.setLevel(logging.INFO)


@contextlib.contextmanager
def gdal_errors():
    """The errors GDAL signalled in this thread inside the block, also those of calls that did
    not fail (a list, filled as they come). GDAL takes some failed reads for data: libtiff caches
    a strile offset it could not read as 0, and GDAL's GTiff driver then fills that block with
    nodata, or zeros without nodata ("Cannot read offset/size for strile", libtiff's
    tif_dirread.c, _TIFFFetchStrileValue); /vsicurl/ keeps a range answer cut short (a 206 with
    bytes missing, cpl_vsil_curl.cpp, DownloadRegion: only a debug message). Only such errors
    show it, and rasterio raises none of them for a read that returned."""
    _install_filter()
    found: list = []
    key = threading.get_ident()
    with _errors_lock:
        outer = _errors_of.get(key)
        _errors_of[key] = found
    try:
        yield found
    finally:
        with _errors_lock:
            if outer is None:
                _errors_of.pop(key, None)
            else:
                _errors_of[key] = outer
                outer.extend(found)
