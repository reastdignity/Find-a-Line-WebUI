"""
Run by hand (and by tools/truth_study.py): the slacklines people have rigged, from SlackMap, as the
known positives the search is checked against (the truth check, 2026-11-08).

    uv run tools/slackmap_data.py fetch [--update] --data-dir <data folder>
    uv run tools/slackmap_data.py status --data-dir <data folder>
    uv run tools/slackmap_data.py details --ids <file>|<id> [...] --data-dir <data folder>

The data: SlackMap (slackmap.com), the map of slacklines run by the International Slackline
Association (ISA) and filled by its users, publishes two GeoJSON files without authentication,
LINES_URL (every line a two-point WGS84 LineString with the properties `id`, `ft`, `l`, the length
as the user stated it ("42.0m", sometimes a number), `lt`, the first letter of its type (TYPES),
and `c`, the ISO 3166-1 code of its country) and SPOTS_URL (the spots' polygons), and the details
of one line by its id (DETAILS_URL: name, height, anchors, dates, ...). No names, heights or dates
are in the files.

No licence of the data is published (the code is GPL-3.0; the ISA's pages, the repositories and
the FAQ state no terms for the data), and the collection is a database the ISA has invested in.
So nothing of them is ever written into the repository: the files and the details live only in the
data folder's cache (cache/slackmap/geojson/lines.geojson.gz, spots.geojson.gz and
cache/slackmap/details/<id>.json (details_path), indexed as every top-level folder of the cache), and the tests
use synthetic lines. A private validation copy is the user's decision of 2026-11-08; any public use
(an overlay, a copy, published lists) waits for the ISA's permission.

Requests: through the pieces of sources/net.py (the host's slots of HOST_SLOTS_OF, a courtesy cap
since SlackMap publishes no limit; rate_turn, the thread's session, verify, the backoff of _sleep)
with cache.http_headers()' User-Agent, counted by servicecounts. net._get cannot send If-None-Match
and raises on a 304, so conditional_get is built from those pieces. The files are checked again
after TTL_DAYS (their ETag and Last-Modified: a 304 only notes the check); the details are asked one
after another, DETAILS_INTERVAL apart, each once (a 404 cached as {"missing": true}).

KnownLine is a line as the study reads it: its anchors as the file gives them, the stated and the
geodesic length, its type and country, the fewest decimals among its four coordinates as written in
the file (the precision of a hand-placed anchor), and the flags of a doubtful geometry
(GEOMETRY_FLAGS: no stated length, a stated length far from the anchors' distance, coarse anchors).
"""

import argparse
import collections
import contextlib
import gzip
import json
import math
import os
import re
import sys
import time
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Callable, Dict, Iterable, List, Optional, Tuple
from urllib.parse import quote

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

import requests  # noqa: E402
from pyproj import Geod  # noqa: E402

import cache  # noqa: E402
import servicecounts  # noqa: E402
from sources import net  # noqa: E402

LINES_URL = "https://data.slackmap.com/geojson/lines/all.geojson"
SPOTS_URL = "https://data.slackmap.com/geojson/spots/all.geojson"
DETAILS_URL = "https://api.slackmap.com/line/{id}/details"
TYPES = {"h": "highline", "l": "longline", "p": "parkline", "w": "waterline", "m": "midline",
         "t": "trickline", "r": "rodeoline"}  # `lt` is the first letter; missing -> "other"; "u" -> "unknown"
TTL_DAYS = 30
DETAILS_INTERVAL = 1.0  # seconds between two detail requests
GEOMETRY_FLAGS = ("no_length", "length_mismatch", "coarse_anchor")
MISMATCH_M = 10.0       # length_mismatch: |geodesic - stated| > max(MISMATCH_M, MISMATCH_SHARE * stated)
MISMATCH_SHARE = 0.2
COARSE_DECIMALS = 3     # coarse_anchor: decimals <= this (0.001° is about 111 m of latitude)
TIMEOUT = 120           # seconds of one request
TOP = "slackmap"        # the cache's top-level folder
LINES_FILE = "geojson/lines.geojson.gz"
SPOTS_FILE = "geojson/spots.geojson.gz"
DETAILS_FOLDER = "details"
ID = re.compile(r"[A-Za-z0-9_-]{1,128}")  # what an id may be: it names a file
GZIP_MAGIC = b"\x1f\x8b"
_GEOD = Geod(ellps="WGS84")


@dataclass(frozen=True)
class KnownLine:
    """A line of SlackMap's lines file (normalise). Flags: no_length (no stated length, or 0);
    length_mismatch when |geodesic - stated| > max(MISMATCH_M, MISMATCH_SHARE * stated); coarse_anchor
    when decimals <= COARSE_DECIMALS (an anchor placed roughly by hand)."""
    id: str
    a: Tuple[float, float]       # (lat, lon) of the first anchor as the file gives it
    b: Tuple[float, float]
    stated_m: Optional[float]    # parse_length of `l`
    geodesic_m: float            # the anchors' distance on the WGS84 ellipsoid
    type: str                    # TYPES[lt], "other", "unknown"
    country: Optional[str]       # upper-case ISO 3166-1 alpha-2 from `c`
    decimals: int                # the fewest decimals among the four coordinates (as written in the file)
    flags: Tuple[str, ...]       # of GEOMETRY_FLAGS, in their order

    @property
    def length_m(self) -> float:
        """The stated length when known, else the anchors' distance."""
        return self.stated_m if self.stated_m is not None else self.geodesic_m

    @property
    def geometry_ok(self) -> bool:
        return not self.flags

    @classmethod
    def from_dict(cls, data: dict) -> "KnownLine":
        """A KnownLine from dataclasses.asdict's dict (a known.json: its lists back to tuples)."""
        return cls(id=str(data["id"]), a=tuple(float(v) for v in data["a"]), b=tuple(float(v) for v in data["b"]),
                   stated_m=None if data.get("stated_m") is None else float(data["stated_m"]),
                   geodesic_m=float(data["geodesic_m"]), type=str(data["type"]), country=data.get("country"),
                   decimals=int(data["decimals"]), flags=tuple(data.get("flags") or ()))


# The cache

def lines_path(cache_dir: str) -> str:
    return os.path.join(cache_dir, TOP, *LINES_FILE.split("/"))


def spots_path(cache_dir: str) -> str:
    return os.path.join(cache_dir, TOP, *SPOTS_FILE.split("/"))


def check_id(line_id) -> str:
    """The id as a string; ValueError unless it is one a file can be named after (ID)."""
    text = str(line_id).strip()
    if not ID.fullmatch(text):
        raise ValueError(f"not a SlackMap id: {line_id!r}")
    return text


def details_path(cache_dir: str, line_id) -> str:
    """cache/slackmap/details/<id>.json, each upper-case letter of the id written as "^" and the letter in
    lower case: SlackMap's ids tell the cases apart (7 characters of A-Z, a-z, 0-9, _ and -), the file
    systems of Windows and macOS do not, so "aB" and "ab" must not name one file."""
    name = re.sub(r"[A-Z]", lambda m: "^" + m.group(0).lower(), check_id(line_id))
    return os.path.join(cache_dir, TOP, DETAILS_FOLDER, name + ".json")


# Requests

def conditional_get(url: str, etag: Optional[str] = None, last_modified: Optional[str] = None,
                    cache_dir: Optional[str] = None) -> Optional[requests.Response]:
    """GET url, conditional on the ETag (If-None-Match) and Last-Modified (If-Modified-Since) of a
    cached copy when given: None on a 304 (the copy is current), the response on a 200, and on a 404
    as it came (not retried: the caller tells a file missing). Every other status, and the errors
    of requests, are tried again as net._get tries them (net.RETRIES attempts, net._sleep between,
    longer after a 429 or 503), then RuntimeError (cache.clean_error). Each attempt takes its turn
    (net.rate_turn), goes through the thread's session (net.session) with cache.http_headers() and
    net.verify, and is counted (servicecounts.request); all of them under one of the host's slots
    (net.host_slot) when cache_dir is given. The body may be gzip whatever the headers say: read it
    through body()."""
    headers = dict(cache.http_headers())
    if etag:
        headers["If-None-Match"] = etag
    if last_modified:
        headers["If-Modified-Since"] = last_modified
    last_error: Optional[BaseException] = None
    with net.host_slot(cache_dir, url) if cache_dir else contextlib.nullcontext():
        for attempt in range(net.RETRIES):
            slow_down = False
            try:
                net.rate_turn(url)
                with servicecounts.request(url) as counted:
                    response = counted.got(net.session().get(url, headers=headers, timeout=TIMEOUT,
                                                             verify=net.verify(url)))
                    if response.status_code == 304:
                        return None
                    if response.status_code in (200, 404):
                        return response
                    slow_down = response.status_code in (429, 503)
                    raise RuntimeError(f"HTTP {response.status_code}: {response.text[:300]}")
            except (requests.RequestException, RuntimeError) as e:
                last_error = e
                if attempt + 1 < net.RETRIES:
                    net._sleep(attempt + 3 if slow_down else attempt)
    raise RuntimeError(cache.clean_error(last_error))


def _gunzip(data: bytes) -> bytes:
    """data without its gzip layers (the 1f 8b magic; JSON never starts so), as it is otherwise."""
    for _ in range(3):  # S3 serves the stored gzip, with or without Content-Encoding; never deeper
        if not data.startswith(GZIP_MAGIC):
            break
        data = gzip.decompress(data)
    return data


def body(response: requests.Response) -> bytes:
    """The body of a response, decoded: requests undoes a gzip Content-Encoding itself, and a body
    still starting with gzip's magic bytes (an object stored gzipped, served without that header)
    is unpacked here."""
    return _gunzip(response.content or b"")


# The files

def _feature_collection(data: bytes, parse_float=float) -> dict:
    """The GeoJSON FeatureCollection of data; RuntimeError when it is none (an error page with 200)."""
    try:
        found = json.loads(data.decode("utf-8"), parse_float=parse_float)
    except (UnicodeDecodeError, ValueError) as e:
        raise RuntimeError(f"not GeoJSON: {e}") from None
    if not isinstance(found, dict) or found.get("type") != "FeatureCollection" or \
            not isinstance(found.get("features"), list):
        raise RuntimeError("not a GeoJSON FeatureCollection")
    return found


def _fetch_file(cache_dir: str, url: str, path: str, update: bool) -> str:
    """Download url into path when it is missing, checked more than TTL_DAYS ago or update is set:
    conditional on the cached copy's ETag and Last-Modified (a 304 only notes the check), written
    gzipped (cache.replacing, the gzip header without a time, so the same content gives the same
    sha256 and keeps its fetch time) and indexed (cache.record). What happened, as a text."""
    row = cache.info(cache_dir, path) if os.path.exists(path) else None
    if row is not None and row["status"] != "ok":
        row = None
    if row is not None and not update and cache.age_days(row["checked_at"]) <= TTL_DAYS:
        return f"cached, checked {cache.age_days(row['checked_at']):.1f} days ago"
    response = conditional_get(url, row["etag"] if row else None, row["last_modified"] if row else None,
                               cache_dir)
    if response is None:
        cache.checked(cache_dir, [path])
        return "unchanged (304)"
    if response.status_code == 404:
        raise RuntimeError(f"{cache.clean_url(url)}: not found (404)")
    data = body(response)
    _feature_collection(data)  # nothing written unless it is one
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with cache.replacing(path) as f:
        f.write(gzip.compress(data, compresslevel=9, mtime=0))
    cache.record(cache_dir, path, url=url, etag=response.headers.get("ETag"),
                 last_modified=response.headers.get("Last-Modified"))
    return f"downloaded, {len(data) / 1e6:.2f} MB decoded"


def fetch(cache_dir: str, update: bool = False, say: Optional[Callable[[str], None]] = None) -> Tuple[str, str]:
    """The cached lines and spots files (paths), each downloaded when missing, older than TTL_DAYS
    (its index row's checked_at) or with update, conditional on its ETag and Last-Modified (a 304
    notes the check: cache.checked). say: told what happened to each file."""
    paths = []
    for url, path in ((LINES_URL, lines_path(cache_dir)), (SPOTS_URL, spots_path(cache_dir))):
        what = _fetch_file(cache_dir, url, path, update)
        if say:
            say(f"{cache.relative(cache_dir, path)}: {what}")
        paths.append(path)
    return paths[0], paths[1]


def _read(path: str) -> bytes:
    with open(path, "rb") as f:
        return _gunzip(f.read())


def _features(cache_dir: str, path: str, parse_float=float) -> List[dict]:
    if not os.path.exists(path):
        fetch(cache_dir)
    return _feature_collection(_read(path), parse_float)["features"]


def load_lines(cache_dir: str) -> List[KnownLine]:
    """The lines of the cached lines file (fetched first when missing), as KnownLines; a feature
    without a two-point line or an id is left out. The coordinates are read with their text kept
    (Decimal), so `decimals` counts what the file wrote, trailing zeros too."""
    found = []
    for feature in _features(cache_dir, lines_path(cache_dir), parse_float=Decimal):
        try:
            found.append(normalise(feature))
        except ValueError:
            continue
    return found


def load_spots(cache_dir: str) -> List[dict]:
    """The spots of the cached spots file (fetched first when missing): {"id", "country", "polygon"
    (a shapely geometry)}; a feature without an areal geometry is left out."""
    from shapely.geometry import shape
    found = []
    for feature in _features(cache_dir, spots_path(cache_dir)):
        if not isinstance(feature, dict):
            continue
        props = feature.get("properties")
        props = props if isinstance(props, dict) else {}
        geometry = feature.get("geometry")
        if not isinstance(geometry, dict) or geometry.get("type") not in ("Polygon", "MultiPolygon"):
            continue
        try:
            polygon = shape(geometry)
        except (ValueError, TypeError, KeyError, IndexError):
            continue
        spot_id = props.get("id", feature.get("id"))
        found.append({"id": None if spot_id is None else str(spot_id), "country": _country(props.get("c")),
                      "polygon": polygon})
    return found


# One line

def parse_length(value) -> Optional[float]:
    """A stated length in metres: "42.0m", "42 m", "42,5m", 42, 42.0; None for none, a text it cannot
    read (another unit), and a length that is not positive and finite."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float, Decimal)):
        try:
            metres = float(value)
        except (ValueError, OverflowError):
            return None
    elif isinstance(value, str):
        match = re.fullmatch(r"\s*(\d+(?:[.,]\d*)?|[.,]\d+)\s*(?:m|meters?|metres?)?\s*", value, re.I)
        if not match:
            return None
        metres = float(match.group(1).replace(",", "."))
    else:
        return None
    return metres if math.isfinite(metres) and metres > 0 else None


def _decimals(value) -> int:
    """The decimals of a coordinate as written: a Decimal keeps its text (load_lines); a float counts
    those of its repr (which drops trailing zeros); an int has none."""
    if isinstance(value, Decimal):
        exponent = value.as_tuple().exponent
    elif isinstance(value, float):
        exponent = Decimal(repr(value)).as_tuple().exponent
    elif isinstance(value, int):
        return 0
    else:
        exponent = Decimal(str(value)).as_tuple().exponent
    return max(0, -exponent) if isinstance(exponent, int) else 0


def _coordinate(value, low: float, high: float) -> float:
    if isinstance(value, bool):
        raise ValueError("a coordinate is a number")
    try:
        number = float(value)
    except (TypeError, ValueError, InvalidOperation):
        raise ValueError(f"not a coordinate: {value!r}") from None
    if not (math.isfinite(number) and low <= number <= high):
        raise ValueError(f"coordinate out of range: {value!r}")
    return number


def _country(value) -> Optional[str]:
    if isinstance(value, str) and re.fullmatch(r"[A-Za-z]{2}", value.strip()):
        return value.strip().upper()
    return None


def _type(value) -> str:
    letter = str(value).strip()[:1].lower() if value is not None else ""
    if not letter:
        return "other"
    if letter == "u":
        return "unknown"
    return TYPES.get(letter, "other")


def normalise(feature: dict) -> KnownLine:
    """A line feature of the lines file as a KnownLine (its first and last point the anchors);
    ValueError for a feature without an id or a LineString of two valid points."""
    if not isinstance(feature, dict):
        raise ValueError("not a feature")
    props = feature.get("properties")
    props = props if isinstance(props, dict) else {}
    line_id = props.get("id", feature.get("id"))
    if line_id is None or str(line_id).strip() == "":
        raise ValueError("a line without an id")
    geometry = feature.get("geometry")
    geometry = geometry if isinstance(geometry, dict) else {}
    points = geometry.get("coordinates") if geometry.get("type") == "LineString" else None
    if not isinstance(points, list) or len(points) < 2 or \
            not all(isinstance(p, list) and len(p) >= 2 for p in (points[0], points[-1])):
        raise ValueError(f"line {line_id}: not a LineString of two points")
    ends = (points[0], points[-1])
    lon1, lat1, lon2, lat2 = (_coordinate(v, *r) for v, r in ((ends[0][0], (-180, 180)), (ends[0][1], (-90, 90)),
                                                              (ends[1][0], (-180, 180)), (ends[1][1], (-90, 90))))
    decimals = min(_decimals(v) for p in ends for v in p[:2])
    stated = parse_length(props.get("l"))
    geodesic = float(_GEOD.inv(lon1, lat1, lon2, lat2)[2])
    flags = []
    if stated is None:
        flags.append("no_length")
    elif abs(geodesic - stated) > max(MISMATCH_M, MISMATCH_SHARE * stated):
        flags.append("length_mismatch")
    if decimals <= COARSE_DECIMALS:
        flags.append("coarse_anchor")
    return KnownLine(id=str(line_id).strip(), a=(lat1, lon1), b=(lat2, lon2), stated_m=stated, geodesic_m=geodesic,
                     type=_type(props.get("lt")), country=_country(props.get("c")), decimals=decimals,
                     flags=tuple(flags))


# Details

def details(cache_dir: str, ids: Iterable[str], interval: float = DETAILS_INTERVAL) -> Dict[str, dict]:
    """The details of each line (DETAILS_URL) by its id, {id: the answer's JSON object}: from
    cache/slackmap/details/<id>.json, else asked, one request after another with time.sleep(interval)
    between two (under one of the host's slots), the answer cached as it came and indexed
    (cache.record); a 404 cached as {"missing": true} (its row "missing"). Never asked again once
    cached. An id that cannot name a file stops before any request (ValueError); a request that
    fails after its retries stops with RuntimeError, what was cached before it stays."""
    wanted = list(dict.fromkeys(check_id(i) for i in ids))
    found: Dict[str, dict] = {}
    asked = False
    for line_id in wanted:
        path = details_path(cache_dir, line_id)
        if os.path.exists(path):
            with open(path, "rb") as f:
                found[line_id] = json.loads(f.read().decode("utf-8"))
            continue
        if asked:
            time.sleep(interval)
        url = DETAILS_URL.format(id=quote(line_id, safe=""))
        response = conditional_get(url, cache_dir=cache_dir)
        asked = True
        if response is None:  # a 304 without a condition sent: no answer to keep
            raise RuntimeError(f"{cache.clean_url(url)}: HTTP 304 to an unconditional request")
        if response.status_code == 404:
            data, value, status = b'{"missing": true}', {"missing": True}, "missing"
        else:
            data = body(response)
            try:
                value = json.loads(data.decode("utf-8"))
            except (UnicodeDecodeError, ValueError):
                value = None
            if not isinstance(value, dict):
                raise RuntimeError(f"{cache.clean_url(url)}: the answer is not a JSON object")
            status = "ok"
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with cache.replacing(path) as f:
            f.write(data)
        cache.record(cache_dir, path, status=status, url=url, etag=response.headers.get("ETag"),
                     last_modified=response.headers.get("Last-Modified"))
        found[line_id] = value
    return found


# The command line

def _size(path: str) -> str:
    return f"{os.path.getsize(path) / 1e3:.0f} kB" if os.path.exists(path) else "missing"


def _ids_of(values: List[str]) -> List[str]:
    """The ids of --ids: each value an id, or a file of them (one per line, # comments; or a JSON list
    of ids or of objects with an "id", as a known.json)."""
    found = []
    for value in values:
        if not os.path.isfile(value):
            found.append(value)
            continue
        with open(value, encoding="utf-8") as f:
            text = f.read()
        if text.lstrip().startswith("["):
            found.extend(str(item["id"] if isinstance(item, dict) else item) for item in json.loads(text))
        else:
            found.extend(line.split("#")[0].strip() for line in text.splitlines() if line.split("#")[0].strip())
    return found


def _status(cache_dir: str, top: int) -> int:
    lines, spots = lines_path(cache_dir), spots_path(cache_dir)
    if not os.path.exists(lines):
        print(f"{lines}: missing (run `fetch` first)")
        return 1
    for path in (lines, spots):
        row = cache.info(cache_dir, path) if os.path.exists(path) else None
        if row is None:
            print(f"{cache.relative(cache_dir, path)}: {_size(path)}")
            continue
        print(f"{cache.relative(cache_dir, path)}: {_size(path)} gzipped, fetched {row['fetched_at']}, checked "
              f"{row['checked_at']} ({cache.age_days(row['checked_at']):.1f} days ago), ETag {row['etag']}, "
              f"Last-Modified {row['last_modified']}")
    features = _features(cache_dir, lines)
    known = load_lines(cache_dir)
    print(f"\nLines: {len(known)} of {len(features)} features"
          + (f" ({len(features) - len(known)} without an id or a two-point line)" if len(features) > len(known)
             else ""))
    types = collections.Counter(line.type for line in known)
    print("\nBy type:")
    for name, count in types.most_common():
        print(f"  {name:<10} {count:>6}")
    high = ("highline", "midline")
    by_country = collections.Counter(line.country or "--" for line in known)
    per_type = {t: collections.Counter(line.country or "--" for line in known if line.type == t) for t in high}
    print(f"\nBy country ({len(by_country)} codes{f', the {top} with most highlines' if top else ''}): "
          f"all, highline, midline")
    order = sorted(by_country, key=lambda c: (-per_type["highline"][c], -by_country[c], c))
    for code in order[:top] if top else order:
        print(f"  {code:<3} {by_country[code]:>6} {per_type['highline'][code]:>6} {per_type['midline'][code]:>6}")
    print("\nFlags: all lines, highlines and midlines")
    chosen = [line for line in known if line.type in high]
    for flag in GEOMETRY_FLAGS:
        print(f"  {flag:<16} {sum(flag in line.flags for line in known):>6} "
              f"{sum(flag in line.flags for line in chosen):>6}")
    print(f"  {'geometry ok':<16} {sum(line.geometry_ok for line in known):>6} "
          f"{sum(line.geometry_ok for line in chosen):>6}")
    if os.path.exists(spots):
        print(f"\nSpots: {len(load_spots(cache_dir))}")
    rows = [r for r in cache.rows(cache_dir, TOP) if r["path"].startswith(f"{TOP}/{DETAILS_FOLDER}/")]
    if rows:
        missing = sum(r["status"] == "missing" for r in rows)
        print(f"Details cached: {len(rows)} ({missing} not found)")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().split("\n\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    data_help = "data folder whose cache/ holds the files (default: FINDALINE_DATA or the repository)"
    one = commands.add_parser("fetch", help="download the lines and spots files when missing or older than "
                                            f"{TTL_DAYS} days")
    one.add_argument("--update", action="store_true", help="ask the server now (a 304 keeps the files)")
    one.add_argument("--data-dir", help=data_help)
    one = commands.add_parser("status", help="the cached files: lines per type and country, the flags")
    one.add_argument("--top", type=int, default=10, help="countries listed (0: all; default %(default)s)")
    one.add_argument("--data-dir", help=data_help)
    one = commands.add_parser("details", help="the details of lines by their ids, cached per id")
    one.add_argument("--ids", nargs="+", required=True, help="ids, or files of ids (one per line, or a JSON list)")
    one.add_argument("--interval", type=float, default=DETAILS_INTERVAL,
                     help="seconds between two requests (default %(default)s)")
    one.add_argument("--data-dir", help=data_help)
    args = parser.parse_args(argv)
    cache_dir = os.path.join(cache.data_dir(args.data_dir), "cache")
    if args.command == "status":
        return _status(cache_dir, args.top)
    cache.check_layout(cache_dir)
    try:
        if args.command == "fetch":
            for path in fetch(cache_dir, args.update, say=print):
                print(f"{path}: {_size(path)}")
            return 0
        ids = list(dict.fromkeys(check_id(i) for i in _ids_of(args.ids)))
        cached = sum(os.path.exists(details_path(cache_dir, i)) for i in ids)
        found = details(cache_dir, ids, args.interval)
        missing = sum(bool(v.get("missing")) for v in found.values())
        print(f"details: {len(ids)} ids, {cached} cached before, {len(ids) - cached} asked, {missing} not found")
        return 0
    except (RuntimeError, ValueError) as e:
        print(f"error: {cache.clean_error(e)}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    from progress import utf8_output
    utf8_output()  # redirected output in UTF-8, not the Windows code page
    sys.exit(main())
