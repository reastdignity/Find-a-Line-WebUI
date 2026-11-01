"""
OpenStreetMap data kept in the cache (cache/osm, see cache.py).

- Themes: features of one kind on a fixed grid of 0.25° tiles, stored as GeoJSON
  (cache/osm/themes/<theme>/<tile>.geojson), so nearby searches share tiles and
  large areas are just more tiles:
    coastline  natural=coastline ways (the sea mask, coast.py)
    cliff      natural=cliff ways and climbing=crag features (search areas)
  A tile comes from the Overpass API, or from the downloaded Geofabrik extracts
  (osmextract.py) when they cover it whole; such tiles are rebuilt when the extracts
  are updated.
- Nominatim answers (cache/osm/nominatim.sqlite): place names and countries, so the
  same point is not asked twice.

The public servers ask for moderation, and every process of the app (the CLI, the web
worker, its phase processes) shares them: Nominatim gets at most one request per second
through a rate limiter kept in cache/osm/nominatim-rate.sqlite (pyrate-limiter), Overpass
one query at a time through a lock file, cache/osm/overpass.lock (filelock), at most
OVERPASS_DAY_MAX queries per UTC day (cache/osm/overpass-day.sqlite) and a pause after the
server refuses one (429, 406).
"""

import contextlib
import json
import math
import os
import random
import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, List, Optional, Tuple

import requests
from shapely.geometry import LineString, MultiLineString, Point, shape

import cache
import messages
import servicecounts

# The one Overpass server asked (FINDALINE_OVERPASS_URL replaces it, an operator's choice). No
# automatic fallback: maps.mail.ru, the second one tried until 2026-11, answered 504 to every query
# on 2026-11-01, and a server tried after another only doubles the load of a busy hour
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"
OVERPASS_WAIT_S = 600  # how long a query waits for the one of another process (each query takes up to 120 s)
# Queries per UTC day per data folder, all processes together (FINDALINE_OVERPASS_DAY_MAX replaces it).
# The OSM wiki's Overpass page (https://wiki.openstreetmap.org/wiki/Overpass_API, 2026-11-01) asks
# regular use to stay below 100 queries a day, summed over all users of an application; 75, the user's choice
# (2026-11-01), stays below it with a margin. Cached theme tiles and tiles built from the extracts never count.
OVERPASS_DAY_MAX = 75
# After a 429 (too many requests) or a 406 (refused) the server is left alone at least this long
# (the wiki: wait before trying again), or as long as its Retry-After asks, up to OVERPASS_PAUSE_MAX_S
OVERPASS_PAUSE_S = 30
OVERPASS_PAUSE_MAX_S = 120
OVERPASS_REFUSED = (429, 406)
_sleep = time.sleep  # patched by the tests (call it through the module)
TILE_DEG = 0.25
# What each theme holds: (OSM type, key, value); the Overpass queries and the
# extracts (osmextract.py) use the same list
THEME_TAGS = {
    "coastline": [("way", "natural", "coastline")],
    "cliff": [("way", "natural", "cliff"), ("node", "climbing", "crag"), ("way", "climbing", "crag"),
              ("relation", "climbing", "crag")],
}
THEMES = {name: "".join(f'{kind}["{key}"="{value}"]({{bbox}});' for kind, key, value in tags)
          for name, tags in THEME_TAGS.items()}


def tiles(west: float, south: float, east: float, north: float) -> List[Tuple[float, float]]:
    """South-west corners of the 0.25° tiles covering a WGS84 box."""
    def steps(a, b):
        return range(math.floor(a / TILE_DEG), math.floor(b / TILE_DEG) + 1)
    return [(i * TILE_DEG, j * TILE_DEG) for i in steps(south, north) for j in steps(west, east)]


def tile_name(lat: float, lon: float) -> str:
    return f"{'N' if lat >= 0 else 'S'}{abs(lat):05.2f}_{'E' if lon >= 0 else 'W'}{abs(lon):06.2f}"


def _geometry(element: Dict):
    if element["type"] == "node":
        return Point(element["lon"], element["lat"])
    if element["type"] == "way" and len(element.get("geometry", [])) > 1:
        return LineString([(p["lon"], p["lat"]) for p in element["geometry"]])
    if element["type"] == "relation":
        parts = [[(p["lon"], p["lat"]) for p in m["geometry"]] for m in element.get("members", [])
                 if len(m.get("geometry") or []) > 1]
        return MultiLineString(parts) if parts else None
    return None


def theme_path(cache_dir: str, theme: str, lat: float, lon: float) -> str:
    return os.path.join(cache_dir, "osm", "themes", theme, f"{tile_name(lat, lon)}.geojson")


def write_tile(path: str, features: List[Dict]):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with cache.replacing(path, "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": features}, f)


class OverpassDayMax(messages.Coded, requests.RequestException):
    """The daily cap of Overpass queries is reached (OVERPASS_DAY_MAX): the query was not sent. A
    requests error, so the callers that go on without Overpass (the coastline falls back to the
    Copernicus water mask) do so; a coded error for the page (messages.Coded)."""

    def __init__(self, cli: str, code: Optional[str] = None, **params):
        super().__init__(cli)
        self.code, self.params = code, params


def overpass_url() -> str:
    return os.environ.get("FINDALINE_OVERPASS_URL", "").strip() or OVERPASS_URL


def overpass_day_max() -> int:
    value = os.environ.get("FINDALINE_OVERPASS_DAY_MAX", "").strip()
    return int(value) if value else OVERPASS_DAY_MAX


def _overpass_db(cache_dir: str) -> sqlite3.Connection:
    """cache/osm/overpass-day.sqlite: the queries of each UTC day and the pause after a refusal
    (written under _overpass_turn's lock only; a new file of the limits, like nominatim-rate.sqlite)."""
    path = os.path.join(cache_dir, "osm", "overpass-day.sqlite")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    db = sqlite3.connect(path, timeout=30)
    db.execute("CREATE TABLE IF NOT EXISTS days (day TEXT PRIMARY KEY, queries INTEGER NOT NULL)")
    db.execute("CREATE TABLE IF NOT EXISTS pause (id INTEGER PRIMARY KEY CHECK (id = 1), until REAL NOT NULL)")
    return db


def overpass_queries_today(cache_dir: str) -> int:
    """The Overpass queries sent today (UTC) from this data folder."""
    db = _overpass_db(cache_dir)
    try:
        row = db.execute("SELECT queries FROM days WHERE day = ?",
                         (datetime.now(timezone.utc).date().isoformat(),)).fetchone()
    finally:
        db.close()
    return row[0] if row else 0


def _count_query(cache_dir: str):
    """Count one Overpass query of today, or raise OverpassDayMax when today's are used up; waits
    first for the end of a pause the server asked for."""
    limit = overpass_day_max()
    day = datetime.now(timezone.utc).date().isoformat()
    db = _overpass_db(cache_dir)
    try:
        row = db.execute("SELECT until FROM pause WHERE id = 1").fetchone()
        if row and row[0] > time.time():
            _sleep(min(row[0] - time.time(), OVERPASS_PAUSE_MAX_S))
        with db:
            db.execute("DELETE FROM days WHERE day < ?", (day,))
            row = db.execute("SELECT queries FROM days WHERE day = ?", (day,)).fetchone()
            if (row[0] if row else 0) >= limit:
                raise OverpassDayMax(f"the {limit} Overpass queries of today (UTC) are used up "
                                     "(FINDALINE_OVERPASS_DAY_MAX): try again tomorrow, or download the "
                                     "OpenStreetMap extract of the country (findaline.py osm download)",
                                     "overpass_day_max", max=limit)
            db.execute("INSERT INTO days (day, queries) VALUES (?, 1) "
                       "ON CONFLICT(day) DO UPDATE SET queries = queries + 1", (day,))
    finally:
        db.close()


def _pause(cache_dir: str, response):
    """Leave the server alone after it refused a query: at least OVERPASS_PAUSE_S, all processes."""
    try:
        seconds = float(response.headers.get("Retry-After", 0))
    except ValueError:
        seconds = 0
    seconds = min(max(seconds, OVERPASS_PAUSE_S), OVERPASS_PAUSE_MAX_S)
    db = _overpass_db(cache_dir)
    try:
        with db:
            db.execute("INSERT OR REPLACE INTO pause (id, until) VALUES (1, ?)", (time.time() + seconds,))
    finally:
        db.close()


@contextlib.contextmanager
def _overpass_turn(cache_dir: str):
    """One Overpass query at a time across all processes of this data folder."""
    from filelock import FileLock, Timeout
    path = os.path.join(cache_dir, "osm", "overpass.lock")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    lock = FileLock(path)
    try:
        lock.acquire(timeout=OVERPASS_WAIT_S)
    except Timeout:
        raise requests.Timeout(f"Overpass is busy with the queries of another search (waited {OVERPASS_WAIT_S // 60} "
                               "min); try again later, or download the OpenStreetMap extract of the country "
                               "(findaline.py osm download)") from None
    try:
        yield
    finally:
        lock.release()


def fetch_tile(theme: str, lat: float, lon: float, cache_dir: str):
    """Build one theme tile: from the extracts when they cover it, else from Overpass."""
    import osmextract
    if osmextract.build_tile(cache_dir, theme, lat, lon):
        return
    path = theme_path(cache_dir, theme, lat, lon)
    bbox = f"{lat},{lon},{lat + TILE_DEG},{lon + TILE_DEG}"
    query = f"[out:json][timeout:90];({THEMES[theme].format(bbox=bbox)});out geom;"
    with _overpass_turn(cache_dir):
        for attempt in range(2):  # once more after a refusal and its pause
            _count_query(cache_dir)
            response = servicecounts.get(overpass_url(), params={"data": query}, headers=cache.http_headers(),
                                         timeout=120)
            if response.status_code not in OVERPASS_REFUSED:
                break
            _pause(cache_dir, response)
        response.raise_for_status()
    features = []
    for element in response.json().get("elements", []):
        geometry = _geometry(element)
        if geometry is not None:
            features.append({"type": "Feature", "geometry": geometry.__geo_interface__,
                             "properties": {"id": f"{element['type']}/{element['id']}",
                                            "tags": element.get("tags", {})}})
    write_tile(path, features)
    cache.record(cache_dir, path, url=response.url.split("?")[0])


# Geofabrik's regions for what its index does not name: it gives ISO 3166-1 codes to countries
# ("iso3166-1:alpha2", "iso3166-2" for a few territories) but none to the regions of a country.
# By the codes of Source.regions and Source.countries (Åland lies within Geofabrik's Finland) ...
GEOFABRIK_OF_CODE = {"gb-eng": "england", "gb-wls": "wales", "de-he": "hessen", "de-mv": "mecklenburg-vorpommern",
                     "de-st": "sachsen-anhalt", "de-ni": "niedersachsen", "it-bz": "nord-est", "ax": "finland"}
# ... and by source, for a source covering a part of its country that Geofabrik keeps apart
GEOFABRIK_OF_SOURCE = {"spain_canarias": ("canary-islands",)}


def catalogue_extracts(cache_dir: str) -> Tuple[List[str], List[str]]:
    """The Geofabrik extracts covering the countries and regions of the catalogue's sources
    (sources.SOURCES: a source's regions, else its countries), from Geofabrik's index
    (osmextract._index): (region ids in the order of SOURCES, codes without a region). The VPS
    downloads them (deploy/vps.sh, osm_data), so the public site rarely needs Overpass."""
    import osmextract
    import sources
    regions = osmextract._index(cache_dir)
    by_code: Dict[str, str] = {}
    for rid, feature in regions.items():
        properties = feature["properties"]
        for code in properties.get("iso3166-1:alpha2", []) + properties.get("iso3166-2", []):
            by_code.setdefault(code.lower(), rid)
    found, missing = [], []
    for source in sources.SOURCES.values():
        wanted = GEOFABRIK_OF_SOURCE.get(source.id)
        if wanted is None:
            codes = source.regions or source.countries
            wanted = [GEOFABRIK_OF_CODE.get(code) or by_code.get(code) or code for code in codes]
        for rid in wanted:
            if rid not in regions:
                missing.append(rid)
            elif rid not in found:
                found.append(rid)
    return found, sorted(set(missing))


def from_extract(row: Optional[Dict]) -> bool:
    """Whether an index row is a theme tile built from extracts (updated with them)."""
    return bool(row and (row.get("url") or "").startswith("geofabrik:"))


def theme(name: str, west: float, south: float, east: float, north: float, cache_dir: str,
          update: Optional[str] = None) -> List[Dict]:
    """Features of a theme over a WGS84 box (each once, with "geometry" as a shapely shape).

    Missing tiles (and with update, stale ones from Overpass) are built; requests
    errors are passed on.
    """
    found: Dict[str, Dict] = {}
    for lat, lon in tiles(west, south, east, north):
        path = theme_path(cache_dir, name, lat, lon)
        row = cache.info(cache_dir, path)
        if cache.due(cache_dir, path, update=None if from_extract(row) else update,
                     ttl=cache.TTL_DAYS["osm-theme"]):
            fetch_tile(name, lat, lon, cache_dir)
        with open(path, encoding="utf-8") as f:
            for feature in json.load(f)["features"]:
                found.setdefault(feature["properties"]["id"],
                                 {**feature["properties"], "geometry": shape(feature["geometry"])})
    return list(found.values())


SEARCH_URL = "https://nominatim.openstreetmap.org/search"
FAILED_DAYS = 30  # a search without a match (or a reverse lookup without an answer) is asked again after it
# Answers larger than this (an outline of a country) are stored with their outline simplified
MAX_ANSWER_BYTES = 5_000_000
# Nominatim's usage policy allows one request per second; the limiter admits one per 1.1 s,
# a margin for the way from the permit to the server
NOMINATIM_INTERVAL_MS = 1100
NOMINATIM_WAIT_S = 300  # how long a request waits for its turn
_limiters: Dict[str, object] = {}  # pyrate_limiter.Limiter per data folder, made once per process
_limiters_lock = threading.Lock()  # threads of a process make one Limiter per data folder
# Called before every request to Nominatim (not for cached answers); the web worker sets it per job
# or quick task to count the requests of its user (jobs.nominatim_quota), None elsewhere
BEFORE_REQUEST: Optional[Callable[[], None]] = None
# The schema of nominatim.sqlite, one step per version (cache.migrate; never change a released step).
# Version 1 is the schema the database had before it had versions, so an old one keeps its rows.
MIGRATIONS = [
    """CREATE TABLE IF NOT EXISTS search (query TEXT PRIMARY KEY, answer TEXT, fetched_at TEXT);
    CREATE TABLE IF NOT EXISTS reverse (query TEXT PRIMARY KEY, answer TEXT, fetched_at TEXT);""",
    # 2: the places of a name (places(): the web app's place box), apart from the areas of `search`
    "CREATE TABLE IF NOT EXISTS places (query TEXT PRIMARY KEY, answer TEXT, fetched_at TEXT);",
]
PLACES_MAX = 5  # matches of a name the place box lists


def _nominatim_db(cache_dir: str) -> sqlite3.Connection:
    path = os.path.join(cache_dir, "osm", "nominatim.sqlite")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    db = sqlite3.connect(path, timeout=60)
    cache.migrate(db, MIGRATIONS)
    return db


def _failed(answer: Dict) -> bool:
    """Whether a stored answer found nothing: no match for a name, an error for a point."""
    return not answer or "error" in answer


def _cached(cache_dir: str, table: str, key: str) -> Optional[Dict]:
    """The stored answer to a query; None if there is none or it is a failure older than FAILED_DAYS.

    A row without a time (none is known, but the column allows it) counts as a lasting answer.
    """
    db = _nominatim_db(cache_dir)
    try:
        row = db.execute(f"SELECT answer, fetched_at FROM {table} WHERE query = ?", (key,)).fetchone()
    finally:
        db.close()
    if not row:
        return None
    answer = json.loads(row[0])
    if _failed(answer) and row[1]:
        if datetime.now(timezone.utc) - datetime.fromisoformat(row[1]) > timedelta(days=FAILED_DAYS):
            return None
    return answer


def _fit(answer: Dict) -> Optional[str]:
    """The answer as JSON of at most MAX_ANSWER_BYTES: its outline simplified (from about a metre,
    doubling the tolerance) until it fits; None if it cannot (then it is not stored)."""
    text = json.dumps(answer)
    tolerance = 1e-5  # degrees
    while len(text.encode("utf-8")) > MAX_ANSWER_BYTES:
        if not isinstance(answer.get("geojson"), dict) or tolerance > 0.1:
            return None
        outline = shape(answer["geojson"]).simplify(tolerance, preserve_topology=True)
        text = json.dumps({**answer, "geojson": outline.__geo_interface__})
        tolerance *= 2
    return text


def _store(cache_dir: str, table: str, key: str, answer: Dict) -> Dict:
    """Store an answer; returns it as stored (a simplified outline, see _fit), so that the
    first search and the later ones from the cache see the same."""
    text = _fit(answer)
    if text is None:
        return answer
    db = _nominatim_db(cache_dir)
    try:
        with db:
            db.execute(f"INSERT OR REPLACE INTO {table} VALUES (?, ?, ?)", (key, text, cache.now_iso()))
    finally:
        db.close()
    return json.loads(text)


def _nominatim_turn(cache_dir: str):
    """Wait until this process may send a request to Nominatim (all processes of the data folder
    share one limit: a pyrate-limiter SQLite bucket, its writes serialised by a file lock)."""
    path = os.path.join(cache_dir, "osm", "nominatim-rate.sqlite")
    with _limiters_lock:
        limiter = _limiters.get(path)
        if limiter is None:
            from pyrate_limiter import Limiter, Rate, SQLiteBucket
            os.makedirs(os.path.dirname(path), exist_ok=True)
            bucket = SQLiteBucket.init_from_file([Rate(1, NOMINATIM_INTERVAL_MS)], table="nominatim",
                                                 db_path=path, use_file_lock=True)
            limiter = _limiters[path] = Limiter(bucket)
    # Asked with no wait (timeout 0), polled: pyrate-limiter's own wait (4.5.1) stamps the permit
    # with the time it planned to wake at, not the time it woke, so after an oversleep (Windows'
    # timer, ~15 ms) the next permit came early; a permit asked now is stamped with the bucket's
    # clock now. (blocking=False fails with a file lock: the limiter passes False to
    # FileLock.acquire as its timeout.) A timeout of 0 also gives up while another process holds
    # the bucket's file lock: the next poll asks again. As sources.net.rate_turn.
    interval = NOMINATIM_INTERVAL_MS / 1000
    deadline = time.monotonic() + NOMINATIM_WAIT_S
    while not limiter.try_acquire("nominatim", timeout=0):
        if time.monotonic() > deadline:
            raise requests.Timeout(f"Nominatim is busy with the requests of other searches (waited "
                                   f"{NOMINATIM_WAIT_S // 60} min); try again later")
        time.sleep(interval * (0.1 + 0.2 * random.random()))  # waiters spread; late, never early


def _ask(url: str, params: Dict, timeout: int, cache_dir: str):
    """One request to Nominatim, in its turn (_nominatim_turn); its JSON. BEFORE_REQUEST, when set,
    is called first (it raises to refuse the request: a user's quota)."""
    if BEFORE_REQUEST is not None:
        BEFORE_REQUEST()
    _nominatim_turn(cache_dir)
    response = servicecounts.get(url, headers=cache.http_headers(), timeout=timeout, params=params)
    response.raise_for_status()
    return response.json()


def search(name: str, cache_dir: str) -> Dict:
    """The best Nominatim match for a name, with its outline ("geojson"); {} if none. Cached."""
    answer = _cached(cache_dir, "search", name)
    if answer is not None:
        return answer
    found = _ask(SEARCH_URL, {"q": name, "format": "jsonv2", "polygon_geojson": 1, "limit": 5}, 30, cache_dir)
    # The first match with an area (a peak or a bus stop is a point)
    answer = next((r for r in found if r.get("geojson", {}).get("type") in ("Polygon", "MultiPolygon")), {})
    return _store(cache_dir, "search", name, answer)


def places(name: str, cache_dir: str) -> List[Dict]:
    """The Nominatim matches of a name to move a map to (the web app's place box, no outlines): at
    most PLACES_MAX of {"name", "lat", "lon", "bbox": [S, W, N, E], "type"}; [] if none. Cached per
    name (stripped, case folded), apart from search()'s areas."""
    key = " ".join(name.split()).casefold()
    answer = _cached(cache_dir, "places", key)
    if answer is None:
        found = _ask(SEARCH_URL, {"q": key, "format": "jsonv2", "limit": PLACES_MAX}, 30, cache_dir)
        matches = [{"name": r.get("display_name", ""), "lat": float(r["lat"]), "lon": float(r["lon"]),
                    # Nominatim's box is [S, N, W, E] as strings
                    "bbox": [float(r["boundingbox"][i]) for i in (0, 2, 1, 3)] if r.get("boundingbox") else None,
                    "type": r.get("type") or r.get("category") or ""} for r in found if "lat" in r and "lon" in r]
        answer = _store(cache_dir, "places", key, {"places": matches[:PLACES_MAX]} if matches else {})
    return answer.get("places", [])


def reverse(lat: float, lon: float, cache_dir: str, **params) -> Dict:
    """Nominatim reverse geocoding, cached per point (to 1e-5°) and parameters."""
    query = {"lat": round(lat, 5), "lon": round(lon, 5), "format": "jsonv2", **params}
    key = json.dumps(query, sort_keys=True)
    answer = _cached(cache_dir, "reverse", key)
    if answer is not None:
        return answer
    return _store(cache_dir, "reverse", key, _ask(NOMINATIM_URL, query, 15, cache_dir))
