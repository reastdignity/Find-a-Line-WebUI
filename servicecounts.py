"""
Counts of the requests to outside services (docs/monitoring.md, row F11): Nominatim, Overpass,
Geofabrik, the OSM water polygons, the orthophotos and the elevation data's services.

Each request (every attempt, so retries show) is counted in the memory of its process by host
and outcome, with its bytes and seconds; `flush` adds the counts to the table
`service_requests` of jobs.sqlite (Jobs.add_service_requests, one write transaction), from which
the web process's metrics read them (metrics.py). Only where the web worker turns the counting
on (`enable`, in a job's phase process and the quick lane, as osm.BEFORE_REQUEST): the command
line and tests/regression.py count nothing. The worker flushes at the end of every phase and
quick task, and a thread every FLUSH_SECONDS during a phase; counts of a process killed
meanwhile are lost (they are statistics).

The host is the URL's (fixed by the catalogue and the OSM services, so a few dozen at most); a
local path (a mirror, the tests' files) is not counted. Outcomes (OUTCOMES): the class of the
HTTP status (`ok` for 2xx and 3xx, `not_found` for 404) or of the exception (`timeout`,
`connection`, `other`); a caller may set another (`Counted.outcome`, e.g. `other` for a 200 with
an error page instead of data).
"""

import contextlib
import threading
import time
from typing import Callable, Dict, Iterator, List, Optional, Tuple
from urllib.parse import urlsplit

import requests

OUTCOMES = ("ok", "not_found", "http_4xx", "http_5xx", "timeout", "connection", "other")
FLUSH_SECONDS = 60.0

_lock = threading.Lock()
_counts: Dict[Tuple[str, str], List[float]] = {}  # (host, outcome) -> [requests, bytes, seconds]
_writer: Optional[Callable[[List[Tuple[str, str, int, int, float]]], None]] = None
_timer: Optional[threading.Thread] = None
_stop = threading.Event()


def host_of(url: Optional[str]) -> Optional[str]:
    """The host of an http(s) URL in lower case; None for anything else (a local path)."""
    if not url:
        return None
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        return None
    return parts.hostname or None


def outcome_of_status(status: int) -> str:
    if status == 404:
        return "not_found"
    if status < 400:
        return "ok"
    return "http_4xx" if status < 500 else "http_5xx"


def outcome_of_error(error: BaseException) -> str:
    """The outcome of a request that raised (ConnectTimeout is a timeout, not a connection error)."""
    if isinstance(error, requests.Timeout):
        return "timeout"
    if isinstance(error, requests.ConnectionError):
        return "connection"
    if isinstance(error, requests.HTTPError) and error.response is not None:
        return outcome_of_status(error.response.status_code)
    return "other"


def enabled() -> bool:
    return _writer is not None


def record(url: Optional[str], outcome: str, size: int = 0, seconds: float = 0.0):
    """Count one request to the host of `url` (nothing while the counting is off or for a local path)."""
    if _writer is None:
        return
    host = host_of(url)
    if host is None:
        return
    if outcome not in OUTCOMES:
        outcome = "other"
    with _lock:
        found = _counts.setdefault((host, outcome), [0, 0, 0.0])
        found[0] += 1
        found[1] += int(size)
        found[2] += float(seconds)


class Counted:
    """A request being counted (see `request`): `got(response)` notes its status (and its bytes,
    unless the body is streamed: then `add` the bytes of each chunk); `outcome` may be set to
    override what the status or the exception would give."""

    def __init__(self):
        self.status: Optional[int] = None
        self.bytes = 0
        self.outcome: Optional[str] = None

    def got(self, response, read: bool = True):
        self.status = getattr(response, "status_code", None)
        if read:
            with contextlib.suppress(Exception):  # a body that cannot be read counts no bytes
                self.bytes += len(response.content or b"")
        return response

    def add(self, size: int):
        self.bytes += size


@contextlib.contextmanager
def request(url: Optional[str]) -> Iterator[Counted]:
    """Count the request made in the body: its seconds (until the body ends), its outcome (what the
    caller set, else the status it noted, else the exception that left the body: `ok` without one)."""
    counted, start, error = Counted(), time.monotonic(), None
    try:
        yield counted
    except BaseException as e:
        error = e
        raise
    finally:
        outcome = counted.outcome
        if outcome is None:
            if counted.status is not None:
                outcome = outcome_of_status(counted.status)
            elif error is not None:
                outcome = outcome_of_error(error)
            else:
                outcome = "ok"
        record(url, outcome, counted.bytes, time.monotonic() - start)


def call(url: Optional[str], send: Callable[[], requests.Response], read: bool = True) -> requests.Response:
    """Send a request (`send()`, which returns its response) and count it."""
    with request(url) as counted:
        return counted.got(send(), read)


def get(url: str, **kwargs) -> requests.Response:
    """requests.get, counted (a streamed body counts no bytes here: use `request` for those)."""
    return call(url, lambda: requests.get(url, **kwargs), read=not kwargs.get("stream"))


def take() -> List[Tuple[str, str, int, int, float]]:
    """The counts since the last take, as rows (host, outcome, requests, bytes, seconds); cleared."""
    global _counts
    with _lock:
        counts, _counts = _counts, {}
    return [(host, outcome, int(n), int(size), seconds)
            for (host, outcome), (n, size, seconds) in sorted(counts.items())]


def _put_back(rows):
    with _lock:
        for host, outcome, n, size, seconds in rows:
            found = _counts.setdefault((host, outcome), [0, 0, 0.0])
            found[0] += n
            found[1] += size
            found[2] += seconds


def flush():
    """Add the counts to the writer's table; on an error (the database locked for longer than its
    timeout) they stay for the next flush."""
    writer = _writer
    if writer is None:
        return
    rows = take()
    if not rows:
        return
    try:
        writer(rows)
    except Exception as e:  # never fails the work that was counted
        _put_back(rows)
        print(f"service counts not written: {type(e).__name__}: {e}")


def _flushing(stop: threading.Event):
    while not stop.wait(FLUSH_SECONDS):
        flush()


def enable(writer: Callable[[List[Tuple[str, str, int, int, float]]], None], interval: bool = True):
    """Count the requests of this process from now on, `writer(rows)` storing them (the web worker's
    processes: Jobs.add_service_requests); with `interval` a daemon thread flushes every
    FLUSH_SECONDS."""
    global _writer, _timer, _stop
    _writer = writer
    if interval and (_timer is None or not _timer.is_alive()):
        _stop = threading.Event()  # each thread its own, so a stopped one never runs on
        _timer = threading.Thread(target=_flushing, args=(_stop,), name="service-counts", daemon=True)
        _timer.start()


def disable():
    """Stop counting (the counts not flushed are dropped) and the flushing thread (tests)."""
    global _writer, _timer
    _writer = None
    _stop.set()
    _timer = None
    take()
