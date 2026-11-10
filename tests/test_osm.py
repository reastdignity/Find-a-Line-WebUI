"""OpenStreetMap without the network: which theme tiles the extracts can build, the Nominatim cache,
the shared rate limits of Nominatim and Overpass (against a local fake server), the User-Agent."""

import contextlib
import json
import os
import sys
import threading
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import osmextract  # noqa: E402


def square(west, south, east, north):
    return {"type": "Polygon", "coordinates": [[[west, south], [east, south], [east, north], [west, north],
                                                [west, south]]]}


def fake_cache(tmp_path):
    """A Geofabrik index with a continent and two neighbouring countries; the extract of "island"."""
    cache_dir = tmp_path / "cache"
    (cache_dir / "osm").mkdir(parents=True)
    index = {"features": [
        {"properties": {"id": "europe", "name": "Europe"}, "geometry": square(0, 40, 30, 60)},
        {"properties": {"id": "island", "name": "Island", "parent": "europe"}, "geometry": square(10.05, 50.05, 10.2, 50.2)},
        {"properties": {"id": "mainland", "name": "Mainland", "parent": "europe"}, "geometry": square(10.3, 50.0, 12, 52)},
    ]}
    (cache_dir / "osm" / "geofabrik-index.json").write_text(json.dumps(index))
    folder = cache_dir / "island" / "osm-extract"
    folder.mkdir(parents=True)
    (folder / "island.osm.pbf").write_bytes(b"")
    (folder / "island.geojson").write_text(json.dumps(square(10.05, 50.05, 10.2, 50.2)))
    cliff = {"type": "Feature", "geometry": {"type": "LineString", "coordinates": [[10.1, 50.1], [10.11, 50.11]]},
             "properties": {"id": "way/1", "tags": {"natural": "cliff"}}}
    (folder / "island.themes.json").write_text(json.dumps(
        {"timestamp": "2026-10-25T00:00:00", "themes": {"cliff": [cliff], "coastline": []}}))
    return str(cache_dir)


def test_tile_with_open_sea_is_built_from_the_extract(tmp_path):
    cache_dir = fake_cache(tmp_path)
    # Tile 50.00-50.25 N, 10.00-10.25 E: the island and the sea around it, no other country
    assert osmextract.build_tile(cache_dir, "cliff", 50.0, 10.0)
    with open(os.path.join(cache_dir, "osm", "themes", "cliff", "N50.00_E010.00.geojson")) as f:
        assert [f["properties"]["id"] for f in json.load(f)["features"]] == ["way/1"]
    # Tile 50.00-50.25 N, 10.25-10.50 E reaches the mainland, whose extract is not there: Overpass
    assert not osmextract.build_tile(cache_dir, "cliff", 50.0, 10.25)


def test_regions_at_a_point(tmp_path):
    cache_dir = fake_cache(tmp_path)
    assert osmextract.regions_at(cache_dir, 50.1, 10.1) == [
        {"id": "island", "name": "Island", "depth": 1, "downloaded": True}]
    assert [r["id"] for r in osmextract.regions_at(cache_dir, 51, 11)] == ["mainland"]


def test_user_agent(monkeypatch):
    """One User-Agent for every request with the version of pyproject.toml: "self-hosted", or a public
    site's address; the operator's contact when set."""
    import tomllib
    import cache
    with open(os.path.join(os.path.dirname(cache.__file__), "pyproject.toml"), "rb") as f:
        version = tomllib.load(f)["project"]["version"]
    assert cache.VERSION == version
    monkeypatch.delenv("FINDALINE_CONTACT", raising=False)
    monkeypatch.delenv("FINDALINE_PUBLIC_URL", raising=False)
    assert cache.http_headers() == {"User-Agent": f"Find-a-Line/{version} (highline finder; self-hosted)"}
    monkeypatch.setenv("FINDALINE_CONTACT", " admin@example.org\r\n")
    assert cache.http_headers() == {"User-Agent": f"Find-a-Line/{version} (highline finder; self-hosted; "
                                                  "contact: admin@example.org)"}
    monkeypatch.setenv("FINDALINE_PUBLIC_URL", "https://findaline.example")
    assert cache.http_headers() == {"User-Agent": f"Find-a-Line/{version} (highline finder; +https://findaline.example; "
                                                  "contact: admin@example.org)"}


def _old_nominatim_db(cache_dir: str, rows):
    """nominatim.sqlite as it was before schema versions (user_version 0)."""
    import sqlite3
    os.makedirs(os.path.join(cache_dir, "osm"), exist_ok=True)
    db = sqlite3.connect(os.path.join(cache_dir, "osm", "nominatim.sqlite"))
    with db:
        db.execute("CREATE TABLE search (query TEXT PRIMARY KEY, answer TEXT, fetched_at TEXT)")
        db.execute("CREATE TABLE reverse (query TEXT PRIMARY KEY, answer TEXT, fetched_at TEXT)")
        db.executemany("INSERT INTO search VALUES (?, ?, ?)", rows)
    db.close()


def _fake_nominatim(monkeypatch, answers):
    """osm._ask answering from a dict (by the "q" of a search); returns the list of names asked."""
    import osm
    asked = []

    def ask(url, params, timeout, cache_dir):
        asked.append(params.get("q"))
        return answers.get(params.get("q"), [])
    monkeypatch.setattr(osm, "_ask", ask)
    return asked


def test_nominatim_cache_migration_keeps_rows(tmp_path, monkeypatch):
    """An old nominatim.sqlite gets schema version 1 and keeps its answers, also those without a time."""
    import sqlite3

    import osm
    cache_dir = str(tmp_path)
    island = {"name": "Island", "geojson": square(10.05, 50.05, 10.2, 50.2)}
    _old_nominatim_db(cache_dir, [("Island", json.dumps(island), "2020-01-01T00:00:00+00:00"),
                                  ("Nowhere", "{}", None)])  # no time: kept like a successful answer
    asked = _fake_nominatim(monkeypatch, {})
    assert osm.search("Island", cache_dir) == island
    assert osm.search("Nowhere", cache_dir) == {}
    assert asked == []
    db = sqlite3.connect(os.path.join(cache_dir, "osm", "nominatim.sqlite"))
    assert db.execute("PRAGMA user_version").fetchone()[0] == len(osm.MIGRATIONS) == 2
    assert db.execute("SELECT COUNT(*) FROM search").fetchone()[0] == 2
    db.close()


def test_nominatim_failed_searches_expire(tmp_path, monkeypatch):
    """A search without a match is asked again after FAILED_DAYS; a match is kept however old."""
    from datetime import datetime, timedelta, timezone

    import osm
    cache_dir = str(tmp_path)
    island = {"name": "Island", "geojson": square(10.05, 50.05, 10.2, 50.2)}
    long_ago = (datetime.now(timezone.utc) - timedelta(days=osm.FAILED_DAYS + 1)).isoformat(timespec="seconds")
    recently = (datetime.now(timezone.utc) - timedelta(days=osm.FAILED_DAYS - 1)).isoformat(timespec="seconds")
    _old_nominatim_db(cache_dir, [("Island", json.dumps(island), long_ago), ("Old miss", "{}", long_ago),
                                  ("New miss", "{}", recently)])
    asked = _fake_nominatim(monkeypatch, {"Old miss": [{"name": "Old miss", "geojson": square(0, 0, 1, 1)}]})
    assert osm.search("Island", cache_dir) == island
    assert osm.search("New miss", cache_dir) == {}
    assert osm.search("Old miss", cache_dir)["name"] == "Old miss"  # asked again: found now
    assert osm.search("Old miss", cache_dir)["name"] == "Old miss"  # and stored
    assert asked == ["Old miss"]


def test_nominatim_large_answers_are_simplified(tmp_path, monkeypatch):
    """An outline above MAX_ANSWER_BYTES is stored simplified, and the first answer is the stored one."""
    import math

    import osm
    cache_dir = str(tmp_path)
    ring = [[10 + 0.1 * math.cos(i / 5000 * 2 * math.pi), 50 + 0.1 * math.sin(i / 5000 * 2 * math.pi)]
            for i in range(5000)]
    big = {"name": "Big", "geojson": {"type": "Polygon", "coordinates": [ring + [ring[0]]]}}
    monkeypatch.setattr(osm, "MAX_ANSWER_BYTES", len(json.dumps(big)) // 4)
    asked = _fake_nominatim(monkeypatch, {"Big": [big]})
    first = osm.search("Big", cache_dir)
    assert len(json.dumps(first)) <= osm.MAX_ANSWER_BYTES
    assert first["name"] == "Big" and len(first["geojson"]["coordinates"][0]) < 5000
    assert osm.search("Big", cache_dir) == first and asked == ["Big"]


def test_nominatim_whole_outline_is_kept(tmp_path, monkeypatch):
    """search(whole=True), a country of the highline layer: the outline as it came whatever its size, on a row of its
    own, so a simplified row is never taken for it, and the plain search stays simplified."""
    import math

    import osm
    cache_dir = str(tmp_path)
    ring = [[10 + 0.1 * math.cos(i / 5000 * 2 * math.pi), 50 + 0.1 * math.sin(i / 5000 * 2 * math.pi)]
            for i in range(5000)]
    big = {"name": "Big", "geojson": {"type": "Polygon", "coordinates": [ring + [ring[0]]]}}
    monkeypatch.setattr(osm, "MAX_ANSWER_BYTES", len(json.dumps(big)) // 4)
    asked = _fake_nominatim(monkeypatch, {"Big": [big]})
    plain = osm.search("Big", cache_dir)
    assert len(plain["geojson"]["coordinates"][0]) < 5000
    whole = osm.search("Big", cache_dir, whole=True)
    assert whole == big and asked == ["Big", "Big"]
    assert osm.search("Big", cache_dir, whole=True) == big and osm.search("Big", cache_dir) == plain
    assert asked == ["Big", "Big"]


def test_places_of_a_name(tmp_path, monkeypatch):
    """osm.places: the matches of a name with their boxes as [S, W, N, E], at most PLACES_MAX, cached per
    name stripped and case folded, apart from search()'s areas; none is [] (stored, asked again later)."""
    import osm
    cache_dir = str(tmp_path)
    town = {"display_name": "Kraków, Polska", "lat": "50.06", "lon": "19.94", "type": "city",
            "boundingbox": ["49.97", "50.13", "19.79", "20.22"]}
    peak = {"display_name": "Giewont", "lat": "49.25", "lon": "19.93", "category": "natural"}
    asked = _fake_nominatim(monkeypatch, {"kraków": [town] * 7, "giewont": [peak]})
    places = osm.places("  Kraków ", cache_dir)
    assert len(places) == osm.PLACES_MAX
    assert places[0] == {"name": "Kraków, Polska", "lat": 50.06, "lon": 19.94, "bbox": [49.97, 19.79, 50.13, 20.22],
                         "type": "city"}
    assert osm.places("KRAKÓW", cache_dir) == places and asked == ["kraków"]
    assert osm.places("Giewont", cache_dir)[0]["bbox"] is None
    assert osm.places("Nowhere", cache_dir) == [] and osm.places("nowhere", cache_dir) == []
    assert asked == ["kraków", "giewont", "nowhere"]
    assert osm.search("Kraków", cache_dir) == {} and asked[-1] == "Kraków"  # its own table


@contextlib.contextmanager
def _fake_server(body: bytes, seconds: float = 0.0, statuses=(), asked=None):
    """A local HTTP server answering every GET with `body` after `seconds` (the first ones with the
    HTTP statuses of `statuses`, then 200); yields its URL and the list of (start, end) times of the
    requests it served. `asked`: a list it adds (start, the query's q) of each request to."""
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from urllib.parse import parse_qs, urlsplit
    served = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            start = time.time()
            if asked is not None:
                asked.append((start, parse_qs(urlsplit(self.path).query).get("q", [None])[0]))
            time.sleep(seconds)
            self.send_response(statuses[len(served)] if len(served) < len(statuses) else 200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            served.append((start, time.time()))

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/", served
    finally:
        server.shutdown()
        server.server_close()


def _in_turn(kind: str, url: str, cache_dir: str, names, start: float, out=None):
    """Run in a spawned process: Nominatim searches or Overpass tiles against the fake server; `out`:
    a JSON file for each search's name, the time (ms) of the permit granted for it and the timeouts
    of the bucket's polls (tests/test_rates.py, permit_recorders)."""
    os.environ["NO_PROXY"] = "127.0.0.1"
    import osm
    import osmextract
    osmextract.build_tile = lambda *args: False  # no extracts: Overpass
    osm.SEARCH_URL = osm.OVERPASS_URL = url
    permits, waits, turns = [], set(), []
    if out is not None:
        from pyrate_limiter import Limiter, SQLiteBucket
        from test_rates import permit_recorders
        SQLiteBucket.put, Limiter.try_acquire = permit_recorders(permits, waits)
    time.sleep(max(0.0, start - time.time()))  # both processes begin together
    for name in names:
        if kind == "nominatim":
            osm.search(name, cache_dir)
            turns.append((name, permits[-1] if permits else None, len(permits)))
        else:
            osm.fetch_tile("cliff", name, 10.0, cache_dir)
    if out is not None:
        with open(out, "w", encoding="utf-8") as f:
            json.dump({"turns": turns, "waits": sorted(waits)}, f)


def _two_processes(kind: str, url: str, cache_dir: str, names, outs=(None, None)):
    import multiprocessing
    context = multiprocessing.get_context("spawn")
    start = time.time() + 5  # time to start both
    processes = [context.Process(target=_in_turn, args=(kind, url, cache_dir, names[i::2], start, outs[i]))
                 for i in range(2)]
    for process in processes:
        process.start()
    for process in processes:
        process.join(120)
        assert process.exitcode == 0


def test_nominatim_one_request_per_second_across_processes(tmp_path):
    """Two processes searching at once share one limit: the permits granted to both together are
    NOMINATIM_INTERVAL_MS (1.1 s) apart, and each request reaches Nominatim only after its own permit.
    That is what the code guarantees; the time from a permit to the request reaching the server depends
    on the scheduler (measured under heavy load: up to 0.5 s in the client and 0.7 s before the fake
    server's handler ran), so the arrivals themselves can come closer than a second: an accepted risk
    while the production load is light."""
    import osm
    names = [f"place {i}" for i in range(6)]
    outs = [str(tmp_path / f"turns{i}.json") for i in range(2)]
    asked = []
    with _fake_server(b"[]", asked=asked) as (url, served):
        _two_processes("nominatim", url, str(tmp_path), names, outs)
    assert len(served) == 6 and sorted(q for _, q in asked) == names
    children = [json.loads(open(out, encoding="utf-8").read()) for out in outs]
    assert all(child["waits"] == [0] for child in children)  # polled: each permit stamped when asked
    turns = [turn for child in children for turn in child["turns"]]
    # one permit per search, each process's own in its order
    assert all([n for _, _, n in child["turns"]] == [1, 2, 3] for child in children)
    permits = sorted(permit for _, permit, _ in turns)
    assert min(b - a for a, b in zip(permits, permits[1:])) >= osm.NOMINATIM_INTERVAL_MS
    permit_of = {name: permit for name, permit, _ in turns}
    assert all(start >= permit_of[q] / 1000 for start, q in asked), (asked, permit_of)


def test_nominatim_turns_never_early(tmp_path, monkeypatch):
    """Threads asking for Nominatim turns at once get them NOMINATIM_INTERVAL_MS apart, never less
    (pyrate-limiter's own blocking wait let one in about a timer's oversleep early). The turns as the
    bucket grants them and no wait inside pyrate-limiter (tests/test_rates.py, permit_recorders): a
    clock read after the turn, 2 ms allowed for the way there, was 19 ms short on a busy machine."""
    import osm
    from test_rates import _record_permits
    permits, waits = _record_permits(monkeypatch)

    def ask():
        for _ in range(3):
            osm._nominatim_turn(str(tmp_path))

    threads = [threading.Thread(target=ask) for _ in range(3)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(60)
    permits.sort()
    assert len(permits) == 9 and waits == {0}
    assert min(b - a for a, b in zip(permits, permits[1:])) >= osm.NOMINATIM_INTERVAL_MS


def test_overpass_one_query_at_a_time_across_processes(tmp_path):
    """Two processes building theme tiles at once: their Overpass queries never overlap."""
    with _fake_server(b'{"elements": []}', seconds=0.5) as (url, served):
        _two_processes("overpass", url, str(tmp_path), [50.0, 50.25, 50.5, 50.75])
    served.sort()
    assert len(served) == 4
    assert all(end <= next_start for (_, end), (next_start, _) in zip(served, served[1:]))


def test_overpass_busy(tmp_path, monkeypatch):
    """A query that cannot get its turn fails with a readable requests error (callers handle those)."""
    import pytest
    import requests
    from filelock import FileLock

    import osm
    import osmextract
    monkeypatch.setattr(osmextract, "build_tile", lambda *args: False)
    monkeypatch.setattr(osm, "OVERPASS_WAIT_S", 0.2)
    (tmp_path / "osm").mkdir()
    with FileLock(str(tmp_path / "osm" / "overpass.lock")):  # another search's query
        with pytest.raises(requests.Timeout, match="Overpass is busy"):
            osm.fetch_tile("cliff", 50.0, 10.0, str(tmp_path))


def _overpass_here(monkeypatch, url):
    """Overpass at the fake server, no extracts, nothing slept."""
    import osm
    monkeypatch.setenv("NO_PROXY", "127.0.0.1")
    monkeypatch.setattr(osmextract, "build_tile", lambda *args: False)
    monkeypatch.setattr(osm, "OVERPASS_URL", url)
    slept = []
    monkeypatch.setattr(osm, "_sleep", slept.append)
    return slept


def test_overpass_daily_cap(tmp_path, monkeypatch):
    """At most FINDALINE_OVERPASS_DAY_MAX queries a day per data folder (osm.OVERPASS_DAY_MAX without
    it): one more is not sent but refused with a coded requests error; cached tiles never count."""
    import pytest
    import requests

    import osm
    import search
    assert osm.overpass_day_max() == osm.OVERPASS_DAY_MAX == 75
    monkeypatch.setenv("FINDALINE_OVERPASS_DAY_MAX", "2")
    cache_dir = str(tmp_path)
    with _fake_server(b'{"elements": []}') as (url, served):
        _overpass_here(monkeypatch, url)
        osm.fetch_tile("cliff", 50.0, 10.0, cache_dir)
        osm.theme("cliff", 10.1, 50.1, 10.2, 50.2, cache_dir)  # the same tile, cached: not asked again
        osm.theme("cliff", 10.3, 50.1, 10.4, 50.2, cache_dir)
        assert len(served) == 2 and osm.overpass_queries_today(cache_dir) == 2
        with pytest.raises(osm.OverpassDayMax) as error:
            osm.fetch_tile("cliff", 50.0, 10.5, cache_dir)
        assert len(served) == 2  # not sent
    assert isinstance(error.value, requests.RequestException)  # callers that go on without Overpass do
    assert error.value.code == "overpass_day_max" and error.value.params == {"max": 2}
    assert "FINDALINE_OVERPASS_DAY_MAX" in str(error.value)
    assert "2 OpenStreetMap queries" in error.value.web_text()
    assert search.SearchError.of(error.value, "Area: ...", "area_failed").code == "overpass_day_max"
    # Yesterday's queries do not count today
    db = osm._overpass_db(cache_dir)
    with db:
        db.execute("UPDATE days SET day = '2000-01-01'")
    db.close()
    assert osm.overpass_queries_today(cache_dir) == 0


def test_cliffs_area_refused_by_the_cap(tmp_path, monkeypatch):
    """--area cliffs needs Overpass where no extract covers it: the cap refuses it with its code."""
    import pytest

    import area
    import osm
    monkeypatch.setenv("FINDALINE_OVERPASS_DAY_MAX", "0")
    _overpass_here(monkeypatch, "http://127.0.0.1:9/")  # never asked
    with pytest.raises(osm.OverpassDayMax):
        area.from_spec("cliffs", 50.0, "50.0,10.0,50.1,10.1", str(tmp_path), 300.0)


def test_overpass_pause_after_refusal(tmp_path, monkeypatch):
    """A 429 or 406: no other server tried, at least OVERPASS_PAUSE_S of rest, then one more query."""
    import osm
    cache_dir = str(tmp_path)
    with _fake_server(b'{"elements": []}', statuses=(429,)) as (url, served):
        slept = _overpass_here(monkeypatch, url)
        osm.fetch_tile("cliff", 50.0, 10.0, cache_dir)
    assert len(served) == 2 and osm.overpass_queries_today(cache_dir) == 2
    assert len(slept) == 1 and osm.OVERPASS_PAUSE_S - 1 < slept[0] <= osm.OVERPASS_PAUSE_S
    cache_dir = str(tmp_path / "other")  # without the pause of the 429 above (nothing really slept)
    with _fake_server(b'{"elements": []}', statuses=(406, 406)) as (url, served):
        slept = _overpass_here(monkeypatch, url)
        import pytest
        import requests
        with pytest.raises(requests.HTTPError):
            osm.fetch_tile("cliff", 50.0, 10.25, cache_dir)
        assert len(served) == 2
        osm.fetch_tile("cliff", 50.0, 10.5, cache_dir)  # the next query waits for the pause too
    assert len(slept) == 2 and len(served) == 3


def test_overpass_no_fallback(tmp_path, monkeypatch):
    """A 504 is an error at once: no second server, one query counted."""
    import pytest
    import requests

    import osm
    with _fake_server(b"busy", statuses=(504,)) as (url, served):
        _overpass_here(monkeypatch, url)
        with pytest.raises(requests.HTTPError):
            osm.fetch_tile("cliff", 50.0, 10.0, str(tmp_path))
    assert len(served) == 1 and osm.overpass_queries_today(str(tmp_path)) == 1
    monkeypatch.setenv("FINDALINE_OVERPASS_URL", "https://example.org/api/interpreter")
    assert osm.overpass_url() == "https://example.org/api/interpreter"


def test_catalogue_extracts(tmp_path):
    """The Geofabrik extracts of the catalogue's countries and regions (the VPS downloads them):
    countries by the ISO codes of Geofabrik's index, its regions without codes by GEOFABRIK_OF_CODE
    and GEOFABRIK_OF_SOURCE. A new source's country or region lands here: check its Geofabrik id."""
    import osm
    countries = {"poland": "PL", "switzerland": "CH", "liechtenstein": "LI", "slovakia": "SK", "malta": "MT",
                 "spain": "ES", "us": "US", "austria": "AT", "luxembourg": "LU", "denmark": "DK", "finland": "FI",
                 "norway": "NO", "czech-republic": "CZ",
                 "france": "FR",
                 "germany": "DE", "italy": "IT", "united-kingdom": "GB",
                 "new-zealand": "NZ", "canada": "CA",
                 "slovenia": "SI"}
    features = [{"properties": {"id": rid, "name": rid, "parent": "europe", "iso3166-1:alpha2": [code]},
                 "geometry": None} for rid, code in countries.items()]
    features += [{"properties": {"id": rid, "name": rid, "parent": "us", "iso3166-1:alpha2": [code],
                                 "iso3166-2": [f"US-{code}"]}, "geometry": None}
                 for rid, code in (("us/puerto-rico", "PR"), ("us/us-virgin-islands", "VI"))]
    features += [{"properties": {"id": rid, "name": rid, "parent": "x"}, "geometry": None}
                 for rid in ("canary-islands", "england", "wales", "hessen", "mecklenburg-vorpommern",
                             "sachsen-anhalt", "niedersachsen", "nord-est",
                             "sachsen", "baden-wuerttemberg",
                             "bayern", "rheinland-pfalz",
                             "scotland", "nordrhein-westfalen", "tasmania", "brandenburg", "berlin",
                             "schleswig-holstein", "queensland", "saarland")]
    features += [{"properties": {"id": "greenland", "name": "Greenland", "parent": "north-america",
                                 "iso3166-1:alpha2": ["GL"]}, "geometry": None},
                 {"properties": {"id": "nunavut", "name": "Nunavut", "parent": "canada", "iso3166-2": ["CA-NU"]},
                  "geometry": None},
                 {"properties": {"id": "british-columbia", "name": "British Columbia", "parent": "canada",
                                 "iso3166-2": ["CA-BC"]}, "geometry": None},
                 {"properties": {"id": "iceland", "name": "Iceland", "parent": "europe", "iso3166-1:alpha2": ["IS"]},
                  "geometry": None}]
    (tmp_path / "osm").mkdir()
    (tmp_path / "osm" / "geofabrik-index.json").write_text(json.dumps({"features": features}))
    found, missing = osm.catalogue_extracts(str(tmp_path))
    assert missing == []
    assert sorted(found) == sorted(
        ["poland", "switzerland", "liechtenstein", "slovakia", "malta", "canary-islands", "spain", "us",
         "us/puerto-rico", "us/us-virgin-islands", "canada", "austria", "wales", "england", "hessen",
         "mecklenburg-vorpommern", "sachsen-anhalt", "niedersachsen", "nord-est", "luxembourg", "denmark",
         "finland", "norway", "new-zealand", "czech-republic",
         "france", "sachsen", "baden-wuerttemberg",
         "bayern", "rheinland-pfalz",
         "scotland", "nordrhein-westfalen", "tasmania", "brandenburg", "schleswig-holstein", "saarland",
         "slovenia", "queensland", "greenland", "nunavut", "british-columbia", "iceland"])
    # A region Geofabrik does not have: named among the missing, not guessed
    (tmp_path / "osm" / "geofabrik-index.json").write_text(json.dumps(
        {"features": [f for f in features if f["properties"]["id"] != "hessen"]}))
    assert osm.catalogue_extracts(str(tmp_path))[1] == ["hessen"]


def test_nested_region_id(tmp_path):
    """An extract of a region id with a slash (us/puerto-rico) is found by extracts() under its id and
    builds theme tiles; a flat id keeps its path (cache/<country>/osm-extract/<id>.osm.pbf)."""
    cache_dir = tmp_path / "cache"
    (cache_dir / "osm").mkdir(parents=True)
    index = {"features": [
        {"properties": {"id": "north-america", "name": "North America"}, "geometry": square(-170, 10, -50, 75)},
        {"properties": {"id": "us/puerto-rico", "name": "Puerto Rico", "parent": "north-america"},
         "geometry": square(-67.3, 17.9, -65.2, 18.6)},
    ]}
    (cache_dir / "osm" / "geofabrik-index.json").write_text(json.dumps(index))
    pbf, outline, themes = osmextract._paths(str(cache_dir), "us/puerto-rico", "us/puerto-rico")
    assert pbf == os.path.join(str(cache_dir), "us_puerto-rico", "osm-extract", "us_puerto-rico.osm.pbf")
    assert osmextract._paths("c", "poland", "malopolskie")[0] == os.path.join("c", "poland", "osm-extract",
                                                                          "malopolskie.osm.pbf")
    os.makedirs(os.path.dirname(pbf))
    open(pbf, "wb").close()
    with open(outline, "w") as f:
        json.dump(square(-67.3, 17.9, -65.2, 18.6), f)
    cliff = {"type": "Feature", "geometry": {"type": "LineString", "coordinates": [[-66.1, 18.1], [-66.11, 18.11]]},
             "properties": {"id": "way/2", "tags": {"natural": "cliff"}}}
    with open(themes, "w") as f:
        json.dump({"timestamp": "2026-11-01T00:00:00", "themes": {"cliff": [cliff], "coastline": []}}, f)
    assert osmextract.extracts(str(cache_dir)) == [("us/puerto-rico", pbf)]
    assert osmextract.build_tile(str(cache_dir), "cliff", 18.0, -66.25)
    assert [r["id"] for r in osmextract.downloaded(str(cache_dir))] == ["us/puerto-rico"]


def _ring(west, south, east, north):
    return square(west, south, east, north)["coordinates"][0]


def test_polygons_of_ways_and_relations():
    """osm.polygons: a closed way is a polygon, a relation its outer rings (joined from several ways)
    less its inner rings, an island in a hole stays; open ways, points and relations without a closed
    outer ring are left out; a self-crossing way is made valid; a relation without roles (theme tiles
    of before) takes every part as outer."""
    from shapely.geometry import LineString, MultiLineString, Point

    import osm
    outer = _ring(0, 0, 10, 10)
    wood = {"id": "relation/1", "tags": {"natural": "wood"}, "roles": ["outer", "outer", "inner", "outer"],
            "geometry": MultiLineString([outer[:3], outer[2:], _ring(2, 2, 8, 8), _ring(4, 4, 6, 6)])}
    scree = {"id": "way/2", "tags": {"natural": "scree"}, "geometry": LineString(_ring(20, 0, 21, 1))}
    found = osm.polygons([
        wood, scree,
        {"id": "way/3", "tags": {}, "geometry": LineString([(0, 0), (1, 1), (2, 0)])},  # open
        {"id": "node/4", "tags": {}, "geometry": Point(0, 0)},
        {"id": "relation/5", "tags": {}, "roles": ["outer"], "geometry": MultiLineString([outer[:3]])},  # not closed
        {"id": "way/6", "tags": {"x": "bow"}, "geometry": LineString([(0, 0), (1, 1), (1, 0), (0, 1), (0, 0)])},
        {"id": "relation/7", "tags": {"x": "old"}, "geometry": MultiLineString([_ring(30, 0, 31, 1)])},
    ])
    assert [tags for _, tags in found] == [{"natural": "wood"}, {"natural": "scree"}, {"x": "bow"}, {"x": "old"}]
    area, _ = found[0]
    assert area.area == 100 - 36 + 4
    assert not area.contains(Point(3, 3)) and area.contains(Point(1, 1)) and area.contains(Point(5, 5))
    assert found[1][0].area == 1 and found[2][0].is_valid and found[2][0].area == 0.5 and found[3][0].area == 1
    # Dicts of GeoJSON geometry are taken too
    line = {"type": "LineString", "coordinates": _ring(0, 0, 1, 1)}
    assert osm.polygons([{"tags": {}, "geometry": line}])[0][0].area == 1


def test_overpass_relations_keep_their_roles(tmp_path, monkeypatch):
    """A relation of Overpass "out geom" keeps its member ways' roles in properties["roles"], in the
    order of its parts (members without a geometry left out of both); ways get none."""
    import osm
    geometry = [{"lon": x, "lat": y} for x, y in _ring(10.0, 50.0, 10.1, 50.1)]
    hole = [{"lon": x, "lat": y} for x, y in _ring(10.02, 50.02, 10.08, 50.08)]
    answer = {"elements": [
        {"type": "relation", "id": 1, "tags": {"type": "multipolygon", "landuse": "forest"},
         "members": [{"type": "way", "ref": 11, "role": "outer", "geometry": geometry},
                     {"type": "node", "ref": 12, "role": "label", "lat": 50.05, "lon": 10.05},
                     {"type": "way", "ref": 13, "role": "inner", "geometry": hole}]},
        {"type": "way", "id": 2, "tags": {"natural": "scree"}, "geometry": hole}]}
    with _fake_server(json.dumps(answer).encode()) as (url, served):
        _overpass_here(monkeypatch, url)
        found = {f["id"]: f for f in osm.theme("landcover", 10.0, 50.0, 10.1, 50.1, str(tmp_path))}
    assert len(served) == 1
    assert found["relation/1"]["roles"] == ["outer", "inner"] and "roles" not in found["way/2"]
    forest = dict((tags.get("landuse"), area) for area, tags in osm.polygons(found.values()))["forest"]
    assert abs(forest.area - (0.01 - 0.0036)) < 1e-9


def _tiny_extract(path):
    """An .osm.pbf with a wood multipolygon (two outer ways making one ring, an inner way), a closed
    scree way, a cliff and an unrelated way (pyosmium's SimpleWriter)."""
    import osmium
    from osmium.osm.mutable import Node, Relation, Way
    points = {1: (10.0, 50.0), 2: (10.1, 50.0), 3: (10.1, 50.1), 4: (10.0, 50.1),
              5: (10.02, 50.02), 6: (10.08, 50.02), 7: (10.08, 50.08), 8: (10.02, 50.08),
              9: (10.15, 50.15), 10: (10.16, 50.15), 11: (10.16, 50.16), 12: (10.15, 50.16)}
    writer = osmium.SimpleWriter(str(path))
    try:
        for ref, location in points.items():
            writer.add_node(Node(id=ref, location=location, tags={}))
        writer.add_way(Way(id=21, nodes=[1, 2, 3], tags={}))
        writer.add_way(Way(id=22, nodes=[3, 4, 1], tags={}))
        writer.add_way(Way(id=23, nodes=[5, 6, 7, 8, 5], tags={}))
        writer.add_way(Way(id=24, nodes=[9, 10, 11, 12, 9], tags={"natural": "scree"}))
        writer.add_way(Way(id=25, nodes=[9, 11], tags={"natural": "cliff"}))
        writer.add_way(Way(id=26, nodes=[1, 3], tags={"highway": "track"}))
        writer.add_relation(Relation(id=31, members=[("w", 21, "outer"), ("w", 22, "outer"), ("w", 23, "inner")],
                                     tags={"type": "multipolygon", "natural": "wood"}))
    finally:
        writer.close()


def test_extract_features_with_roles(tmp_path):
    """_take_features takes the themes of EXTRACT_THEMES (no landcover) from an extract; asked for
    landcover, the wood relation's member ways with their roles and the scree way, which polygons()
    makes areas of (the wood's hole not forest)."""
    from shapely.geometry import Point

    import osm
    pbf, out = tmp_path / "tiny.osm.pbf", tmp_path / "tiny.themes.json"
    _tiny_extract(pbf)
    osmextract._take_features(str(pbf), str(out), "2026-11-03T00:00:00+00:00")
    themes = json.loads(out.read_text())["themes"]
    assert set(themes) == set(osmextract.EXTRACT_THEMES) == {"coastline", "cliff"}
    assert [f["properties"]["id"] for f in themes["cliff"]] == ["way/25"]
    osmextract._take_features(str(pbf), str(out), "2026-11-03T00:00:00+00:00", ("landcover", "cliff"))
    themes = json.loads(out.read_text())["themes"]
    assert set(themes) == {"landcover", "cliff"}
    by_id = {f["properties"]["id"]: f for f in themes["landcover"]}
    assert set(by_id) == {"relation/31", "way/24"}
    assert by_id["relation/31"]["properties"]["roles"] == ["outer", "outer", "inner"]
    assert "roles" not in by_id["way/24"]["properties"] and "roles" not in themes["cliff"][0]["properties"]
    features = [{**f["properties"], "geometry": f["geometry"]} for f in themes["landcover"]]
    areas = {tags.get("natural"): area for area, tags in osm.polygons(features)}
    assert areas["wood"].contains(Point(10.01, 50.01)) and not areas["wood"].contains(Point(10.05, 50.05))
    assert abs(areas["wood"].area - (0.01 - 0.0036)) < 1e-9 and abs(areas["scree"].area - 0.0001) < 1e-9


def test_themes_not_from_the_extracts(tmp_path):
    """landcover never comes from the extracts (Overpass instead), even from a themes.json holding it;
    an extract whose themes.json lacks a theme of EXTRACT_THEMES (taken before it existed) does not give
    its tiles either (Overpass instead of a KeyError)."""
    cache_dir = fake_cache(tmp_path)  # its themes.json has cliff and coastline only
    themes = os.path.join(cache_dir, "island", "osm-extract", "island.themes.json")
    assert osmextract._missing_themes(themes) == []
    assert osmextract._missing_themes(themes + ".none") == ["coastline", "cliff"]
    assert osmextract.build_tile(cache_dir, "cliff", 50.0, 10.0)
    assert not osmextract.build_tile(cache_dir, "landcover", 50.0, 10.0)
    with open(themes) as f:
        data = json.load(f)
    data["themes"] = {"cliff": data["themes"]["cliff"], "landcover": []}  # as an old file lacking coastline
    with open(themes, "w") as f:
        json.dump(data, f)
    os.utime(themes, (1, 1))  # osmextract._load sees the change whatever the clock's resolution
    assert osmextract._missing_themes(themes) == ["coastline"]
    assert not osmextract.build_tile(cache_dir, "coastline", 50.0, 10.0)
    assert not osmextract.build_tile(cache_dir, "landcover", 50.0, 10.0)
    assert osmextract.build_tile(cache_dir, "cliff", 50.0, 10.0)


def test_update_takes_a_missing_extract_theme_again(tmp_path, monkeypatch):
    """osm update of an extract with no new diffs takes its theme features again when its themes.json
    lacks a theme of EXTRACT_THEMES, never because of landcover (the extracts never hold it)."""
    from datetime import datetime
    from types import SimpleNamespace

    import osmium.replication.utils as replication
    cache_dir = fake_cache(tmp_path)  # cliff and coastline: complete, no landcover
    pbf = os.path.join(cache_dir, "island", "osm-extract", "island.osm.pbf")
    header = SimpleNamespace(url="https://example.invalid/replication", sequence=7,
                             timestamp=datetime(2026, 11, 3))
    monkeypatch.setattr(replication, "get_replication_header", lambda path: header)
    monkeypatch.setattr(osmextract, "_replication_server", lambda url: SimpleNamespace(
        set_request_parameter=lambda *args: None, get_state_info=lambda: SimpleNamespace(sequence=7)))
    finished = []
    monkeypatch.setattr(osmextract, "_finish", lambda *args: finished.append(args[1]))
    assert not osmextract.update(cache_dir, "island", pbf) and finished == []
    themes = pbf[:-len(".osm.pbf")] + ".themes.json"
    with open(themes) as f:
        data = json.load(f)
    del data["themes"]["coastline"]
    with open(themes, "w") as f:
        json.dump(data, f)
    os.utime(themes, (1, 1))
    assert osmextract.update(cache_dir, "island", pbf) and finished == ["island"]


def test_tiles_across_the_antimeridian():
    """A box with west > east crosses 180° (transform_bounds of a grid spanning it): the 0.25° tiles of
    both sides, in osm.tiles' order (a row south to north, the west side's tiles first), nothing else;
    the edges stay inclusive."""
    import osm
    both = osm.tiles(170, 50, -170, 55)
    west_side = [(lat, lon) for lat in np.arange(50, 55.01, 0.25) for lon in np.arange(170, 179.76, 0.25)]
    east_side = [(lat, lon) for lat in np.arange(50, 55.01, 0.25) for lon in np.arange(-180, -169.99, 0.25)]
    assert set(both) == set(west_side) | set(east_side) and len(both) == len(west_side) + len(east_side)
    assert both[:40] == west_side[:40] and both[40:81] == east_side[:41] and both[81] == (50.25, 170.0)
    assert all(-180 <= lon < 180 for _, lon in both)
    assert osm.tiles(0, 0, 0.25, 0.25) == [(0.0, 0.0), (0.0, 0.25), (0.25, 0.0), (0.25, 0.25)]
