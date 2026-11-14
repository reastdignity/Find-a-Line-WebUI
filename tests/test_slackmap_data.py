"""tools/slackmap_data.py: SlackMap's lines and spots files fetched into a scratch cache (conditional on their
ETag, gzip on the wire), read as KnownLines with their types and flags, and the details asked once per id;
offline on tests/http_server.py. Synthetic data only: invented ids, coordinates and lengths (no SlackMap data
in the repository: its data have no published licence)."""

import dataclasses
import gzip
import json
import os
import sqlite3
import sys
from decimal import Decimal

import pytest
import requests
from pyproj import Geod

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "tools"))
import cache  # noqa: E402
import slackmap_data as sd  # noqa: E402
from http_server import Answer  # noqa: E402
from sources import net  # noqa: E402

GEOD = Geod(ellps="WGS84")
ETAG = '"lines-1"'
LAST_MODIFIED = "Fri, 06 Nov 2026 10:00:00 GMT"
LINES = "/geojson/lines/all.geojson"
SPOTS = "/geojson/spots/all.geojson"


def _distance(a, b) -> float:
    """The geodesic metres between two (lat, lon) given as texts."""
    return GEOD.inv(float(a[1]), float(a[0]), float(b[1]), float(b[0]))[2]


def _feature(line_id, a, b, **props) -> str:
    """A line feature as GeoJSON text, its coordinates written exactly as the texts a, b (lat, lon) give."""
    properties = json.dumps({"id": line_id, "ft": "l", **props})
    return ('{"type": "Feature", "properties": %s, "geometry": {"type": "LineString", "coordinates": '
            '[[%s, %s], [%s, %s]]}}' % (properties, a[1], a[0], b[1], b[0]))


def _collection(features) -> bytes:
    return ('{"type": "FeatureCollection", "features": [%s]}' % ", ".join(features)).encode()


# Six invented lines: an int length, a "u" type, one without `lt` (nor `c`), a 2-decimal anchor, a length
# far from the anchors' distance, a longline. "10.10000" has 5 decimals as written (its float, 10.1, one).
A1, B1 = ("10.10000", "20.00000"), ("10.10000", "20.00050")
A2, B2 = ("10.20001", "20.10002"), ("10.20021", "20.10002")
A3, B3 = ("10.30001", "20.20001"), ("10.30001", "20.20031")
A4, B4 = ("10.12", "20.34"), ("10.12034", "20.34012")
A5, B5 = ("10.40001", "20.40001"), ("10.40051", "20.40001")
A6, B6 = ("10.50001", "20.50001"), ("10.50001", "20.50111")
FEATURES = [
    _feature("synth1", A1, B1, l=round(_distance(A1, B1)), lt="h", c="sk"),
    _feature("synth2", A2, B2, lt="u", c="SK"),
    _feature("synth3", A3, B3, l=round(_distance(A3, B3), 1)),
    _feature("synth4", A4, B4, l=f"{_distance(A4, B4):.1f}m", lt="h", c="XA"),
    _feature("synth5", A5, B5, l=f"{2 * _distance(A5, B5):.1f}m", lt="m", c="XA"),
    _feature("synth6", A6, B6, l=f"{_distance(A6, B6):.1f}m", lt="l", c="XB"),
]
SPOTS_BODY = json.dumps({"type": "FeatureCollection", "features": [
    {"type": "Feature", "properties": {"id": "spot1", "ft": "s", "c": "sk"},
     "geometry": {"type": "Polygon", "coordinates": [[[20.0, 10.0], [20.001, 10.0], [20.001, 10.001], [20.0, 10.0]]]}},
    {"type": "Feature", "properties": {"id": "spot2"},
     "geometry": {"type": "Point", "coordinates": [20.0, 10.0]}},
]}).encode()


@pytest.fixture
def served(http_server, monkeypatch):
    """The lines file gzipped with Content-Encoding (as CloudFront serves it) and the spots file gzipped
    without that header (an object stored gzipped), each with its ETag; a request with the current
    ETag in If-None-Match gets a 304. state: the bodies and ETags served, changed by a test."""
    state = {LINES: [_collection(FEATURES), ETAG], SPOTS: [SPOTS_BODY, '"spots-1"']}

    def answer(request):
        data, etag = state[request.path]
        if request.headers.get("if-none-match") == etag:
            return Answer(304, b"", {"ETag": etag})
        headers = {"Content-Type": "application/json", "ETag": etag, "Last-Modified": LAST_MODIFIED}
        if request.path == LINES:
            headers["Content-Encoding"] = "gzip"
        return Answer(200, gzip.compress(data), headers, ranges=False)

    http_server.route("/geojson/", answer)
    monkeypatch.setattr(sd, "LINES_URL", http_server.url(LINES))
    monkeypatch.setattr(sd, "SPOTS_URL", http_server.url(SPOTS))
    monkeypatch.setattr(net, "_sleep", lambda attempt: None)
    return state


def _cache(tmp_path) -> str:
    folder = os.path.join(str(tmp_path), "data", "cache")
    cache.check_layout(folder)
    return folder


def test_fetch_writes_the_files_and_their_rows(http_server, served, tmp_path):
    """Both files downloaded, written gzipped and indexed with their ETag; the User-Agent of every
    request is cache.http_headers()'; within TTL_DAYS nothing is asked again."""
    cache_dir = _cache(tmp_path)
    lines, spots = sd.fetch(cache_dir)
    assert lines == os.path.join(cache_dir, "slackmap", "geojson", "lines.geojson.gz")
    assert spots == os.path.join(cache_dir, "slackmap", "geojson", "spots.geojson.gz")
    with open(lines, "rb") as f:
        assert gzip.decompress(f.read()) == _collection(FEATURES)
    with open(spots, "rb") as f:
        assert gzip.decompress(f.read()) == SPOTS_BODY
    row = cache.info(cache_dir, lines)
    assert (row["status"], row["etag"], row["last_modified"], row["url"]) == ("ok", ETAG, LAST_MODIFIED,
                                                                               http_server.url(LINES))
    assert row["sha256"] == cache._sha256(lines)
    assert cache.info(cache_dir, spots)["etag"] == '"spots-1"'
    asked = http_server.requests("/geojson/")
    assert len(asked) == 2 and not http_server.stray()
    assert all(r.user_agent == cache.http_headers()["User-Agent"] for r in asked)
    assert not any("if-none-match" in r.headers for r in asked)
    assert sd.fetch(cache_dir) == (lines, spots)
    assert len(http_server.requests("/geojson/")) == 2


def test_update_asks_with_the_etag_and_a_304_keeps_the_file(http_server, served, tmp_path):
    """fetch(update=True) sends If-None-Match and If-Modified-Since; a 304 leaves the file and its sha256
    and notes the check; a copy older than TTL_DAYS is checked without update; a new ETag replaces it."""
    cache_dir = _cache(tmp_path)
    lines, _ = sd.fetch(cache_dir)
    before = cache.info(cache_dir, lines)
    _age(cache_dir, 2)
    sd.fetch(cache_dir, update=True)
    asked = http_server.requests(LINES)
    assert len(asked) == 2
    assert (asked[1].headers["if-none-match"], asked[1].headers["if-modified-since"]) == (ETAG, LAST_MODIFIED)
    after = cache.info(cache_dir, lines)
    assert (after["sha256"], after["fetched_at"], after["etag"]) == (before["sha256"], before["fetched_at"], ETAG)
    assert cache.age_days(after["checked_at"]) < 1
    with open(lines, "rb") as f:
        assert gzip.decompress(f.read()) == _collection(FEATURES)

    _age(cache_dir, sd.TTL_DAYS + 1)
    sd.fetch(cache_dir)
    assert len(http_server.requests(LINES)) == 3 and cache.age_days(cache.info(cache_dir, lines)["checked_at"]) < 1

    served[LINES] = [_collection(FEATURES[:2]), '"lines-2"']
    sd.fetch(cache_dir, update=True)
    assert [line.id for line in sd.load_lines(cache_dir)] == ["synth1", "synth2"]
    assert cache.info(cache_dir, lines)["etag"] == '"lines-2"'


def _age(cache_dir: str, days: float):
    """Every row of cache/slackmap checked `days` ago."""
    db = sqlite3.connect(os.path.join(cache_dir, "slackmap", "index.sqlite"))
    with db:
        db.execute("UPDATE files SET checked_at = ?", (cache.now_iso(days * 86400),))
    db.close()


def test_errors_write_nothing(http_server, served, tmp_path):
    """A 200 that is no FeatureCollection (an error page) and a 404 stop without a file; a 503 is asked
    again (net.RETRIES attempts, net._sleep between) and the file then written."""
    cache_dir = _cache(tmp_path)
    served[LINES] = [b"<html>maintenance</html>", ETAG]
    with pytest.raises(RuntimeError, match="not GeoJSON"):
        sd.fetch(cache_dir)
    assert not os.path.exists(sd.lines_path(cache_dir))
    http_server.add("/missing.geojson", b"no", "text/plain", status=404)
    with pytest.raises(RuntimeError, match="not found"):
        sd._fetch_file(cache_dir, http_server.url("/missing.geojson"), sd.lines_path(cache_dir), False)
    assert len(http_server.requests("/missing.geojson")) == 1

    calls = []

    def busy_once(request):
        calls.append(request)
        if len(calls) == 1:
            return Answer(503, b"busy", {"Content-Type": "text/plain"})
        return Answer(200, _collection(FEATURES), {"Content-Type": "application/json", "ETag": ETAG})

    http_server.route("/busy/", busy_once)
    path = sd.lines_path(cache_dir)
    sd._fetch_file(cache_dir, http_server.url("/busy/lines.geojson"), path, False)
    assert len(calls) == 2 and len(sd.load_lines(cache_dir)) == 6
    http_server.add("/down.geojson", b"down", "text/plain", status=500)
    with pytest.raises(RuntimeError, match="HTTP 500"):
        sd.conditional_get(http_server.url("/down.geojson"))
    assert len(http_server.requests("/down.geojson")) == net.RETRIES


def test_load_lines_types_and_flags(http_server, served, tmp_path):
    """The served lines as KnownLines: types (a "u", none), countries, lengths stated as an int, a number
    or a text, decimals counted as written, and the flags."""
    cache_dir = _cache(tmp_path)
    found = {line.id: line for line in sd.load_lines(cache_dir)}  # fetched first: the file is missing
    assert list(found) == [f"synth{k}" for k in range(1, 7)]
    one, two, three, four, five, six = (found[f"synth{k}"] for k in range(1, 7))
    assert (one.type, two.type, three.type, four.type, five.type, six.type) == (
        "highline", "unknown", "other", "highline", "midline", "longline")
    assert (one.country, two.country, three.country, six.country) == ("SK", "SK", None, "XB")
    assert one.a == (10.1, 20.0) and one.b == (10.1, 20.0005)
    assert one.stated_m == round(_distance(A1, B1)) and one.geodesic_m == pytest.approx(_distance(A1, B1))
    assert one.decimals == 5 and one.flags == () and one.geometry_ok
    assert two.stated_m is None and two.flags == ("no_length",) and two.length_m == two.geodesic_m
    assert three.stated_m == round(_distance(A3, B3), 1) and three.flags == ()
    assert four.decimals == 2 and four.flags == ("coarse_anchor",)
    assert five.flags == ("length_mismatch",) and five.length_m == five.stated_m
    assert six.flags == () and 115 < six.length_m < 125
    spots = sd.load_spots(cache_dir)
    assert [(s["id"], s["country"]) for s in spots] == [("spot1", "SK")] and spots[0]["polygon"].area > 0


def _line(lt=None, length=None, c=None, coordinates=((20.0, 10.0), (20.0005, 10.0)), line_id="x1"):
    props = {"id": line_id}
    for key, value in (("lt", lt), ("l", length), ("c", c)):
        if value is not None:
            props[key] = value
    return {"type": "Feature", "properties": props,
            "geometry": {"type": "LineString", "coordinates": [list(p) for p in coordinates]}}


def test_normalise():
    """normalise's types, countries and flags, the mismatch's bounds, decimals of floats and of the text, and
    the features it refuses."""
    for lt, kind in (("h", "highline"), ("l", "longline"), ("p", "parkline"), ("w", "waterline"),
                     ("m", "midline"), ("t", "trickline"), ("r", "rodeoline"), ("u", "unknown"), (None, "other"),
                     ("", "other"), ("x", "other"), ("Highline", "highline")):
        assert sd.normalise(_line(lt, "50m")).type == kind, lt
    for c, code in (("pl", "PL"), (" CZ ", "CZ"), ("GBR", None), (None, None), (12, None)):
        assert sd.normalise(_line("h", "50m", c)).country == code, c
    short = ((20.0, 10.0), (20.0, 10.00027))
    near = sd.normalise(_line("h", coordinates=short)).geodesic_m  # about 30 m: 10 m is more than 20 % of it
    assert 29 < near < 31
    for stated, mismatch in ((near + 9.9, False), (near - 9.9, False), (near + 10.1, True), (near - 10.1, True)):
        assert ("length_mismatch" in sd.normalise(_line("h", stated, coordinates=short)).flags) == mismatch, stated
    far = ((20.0, 10.0), (20.0, 10.0 + 150 / 110600))
    geodesic = sd.normalise(_line("h", coordinates=far)).geodesic_m
    for stated, mismatch in ((geodesic / 0.81, False), (geodesic / 0.79, True), (geodesic / 1.19, False),
                             (geodesic / 1.21, True)):  # 20 % of the stated length, beyond 10 m
        assert ("length_mismatch" in sd.normalise(_line("h", stated, coordinates=far)).flags) == mismatch, stated
    fine = ((20.00001, 10.00001), (20.00051, 10.00001))
    assert sd.normalise(_line("h", None, coordinates=fine)).flags == ("no_length",)
    assert sd.normalise(_line("h", "55m", coordinates=fine)).flags == ()
    assert sd.normalise(_line("h", None)).flags == ("no_length", "coarse_anchor")  # 10.0: one decimal
    coarse = sd.normalise(_line("h", None, coordinates=((20.123, 10.5), (20.12345, 10.50001))))
    assert coarse.decimals == 1 and coarse.flags == ("no_length", "coarse_anchor")
    assert sd.normalise(_line("h", "55m", coordinates=((20.1234, 10.1234), (20.1239, 10.1234)))).decimals == 4
    text = json.loads('{"c": [[20.10000, 10.00010], [20.10050, 10.00010]]}', parse_float=Decimal)["c"]
    assert sd.normalise(_line("h", "55m", coordinates=text)).decimals == 5  # as written, zeros too
    assert sd.normalise(_line("h", "55m", coordinates=[[float(v) for v in p] for p in text])).decimals == 1  # 20.1
    assert sd.normalise(_line("h", "55m", coordinates=((20, 10), (20.0005, 10.0)))).decimals == 0
    for bad in ({"type": "Feature", "properties": {"id": "x"}, "geometry": {"type": "Point", "coordinates": [1, 2]}},
                _line(coordinates=((20.0, 10.0),)), _line(coordinates=((20.0, 95.0), (20.0, 10.0))),
                _line(coordinates=((200.0, 10.0), (20.0, 10.0))), _line(line_id=None), _line(line_id=" "),
                {"type": "Feature", "properties": {"id": "x"}, "geometry": None}, "not a feature",
                _line(coordinates=((20.0, float("nan")), (20.0, 10.0))), _line(coordinates=(("a", 10.0), (20, 10)))):
        with pytest.raises(ValueError):
            sd.normalise(bad)
    many = _line("h", "55m", coordinates=((20.0, 10.0), (20.0002, 10.0), (20.0005, 10.0)))
    assert sd.normalise(many).b == (10.0, 20.0005)  # the last point the second anchor


def test_parse_length():
    for value, metres in (("42.0m", 42.0), ("42 m", 42.0), ("42,5m", 42.5), ("42.0M", 42.0), (" 42 metres ", 42.0),
                          ("42", 42.0), (42, 42.0), (42.5, 42.5), (Decimal("42.50"), 42.5), (None, None), ("", None),
                          ("abc", None), ("1.2km", None), (0, None), ("0m", None), ("-5m", None), (True, None),
                          (float("inf"), None), (float("nan"), None), ([42], None)):
        assert sd.parse_length(value) == metres, value


def test_known_line_as_dict():
    """dataclasses.asdict through JSON and back (a known.json) gives the same KnownLine."""
    line = sd.normalise(_line("h", "55m", "pl"))
    assert sd.KnownLine.from_dict(json.loads(json.dumps(dataclasses.asdict(line)))) == line
    lone = sd.normalise(_line(None, None, coordinates=((20.1, 10.1), (20.1005, 10.1))))
    assert sd.KnownLine.from_dict(json.loads(json.dumps(dataclasses.asdict(lone)))) == lone


def test_body_gzip_whatever_the_headers():
    """body() unpacks a body starting with gzip's magic bytes and leaves a plain one."""
    def response(content):
        found = requests.Response()
        found._content = content
        return found
    data = b'{"type": "FeatureCollection", "features": []}'
    assert sd.body(response(data)) == data
    assert sd.body(response(gzip.compress(data))) == data
    assert sd.body(response(gzip.compress(gzip.compress(data)))) == data
    assert sd.body(response(b"")) == b""


def test_details_once_per_id(http_server, tmp_path, monkeypatch):
    """One request per id not cached, time.sleep(interval) between two, none for a cached id; a 404 cached
    as {"missing": true}; an id that cannot name a file stops before any request."""
    cache_dir = _cache(tmp_path)
    sleeps = []
    monkeypatch.setattr(sd.time, "sleep", lambda seconds: sleeps.append(seconds))
    monkeypatch.setattr(sd, "DETAILS_URL", http_server.url("/line/{id}/details"))

    def answer(request):
        line_id = request.path.split("/")[2]
        if line_id.startswith("gone"):
            return Answer(404, b'{"message": "not found"}', {"Content-Type": "application/json"})
        return Answer(200, json.dumps({"id": line_id, "name": f"invented {line_id}", "height": 20}).encode(),
                      {"Content-Type": "application/json"})

    http_server.route("/line/", answer)
    found = sd.details(cache_dir, ["abc1", "def2", "gone1", "abc1"])
    assert found == {"abc1": {"id": "abc1", "name": "invented abc1", "height": 20},
                     "def2": {"id": "def2", "name": "invented def2", "height": 20}, "gone1": {"missing": True}}
    assert [r.path for r in http_server.requests("/line/")] == ["/line/abc1/details", "/line/def2/details",
                                                                 "/line/gone1/details"]
    assert all(r.user_agent == cache.http_headers()["User-Agent"] for r in http_server.requests("/line/"))
    assert sleeps == [sd.DETAILS_INTERVAL] * 2
    for line_id, status in (("abc1", "ok"), ("gone1", "missing")):
        path = os.path.join(cache_dir, "slackmap", "details", f"{line_id}.json")
        assert os.path.exists(path) and cache.info(cache_dir, path)["status"] == status

    # Ids differing in case only are two files, also where the file system ignores the case
    assert sd.details_path(cache_dir, "aB-x_Z9") == os.path.join(cache_dir, "slackmap", "details", "a^b-x_^z9.json")
    assert sd.details(cache_dir, ["caseAb", "caseab"], interval=0) == {
        "caseAb": {"id": "caseAb", "name": "invented caseAb", "height": 20},
        "caseab": {"id": "caseab", "name": "invented caseab", "height": 20}}
    assert len(http_server.requests("/line/")) == 5 and sleeps[-1] == 0
    del sleeps[-1]

    assert sd.details(cache_dir, ["abc1", "gone1", "ghi3"], interval=0.25)["gone1"] == {"missing": True}
    assert len(http_server.requests("/line/")) == 6 and sleeps == [sd.DETAILS_INTERVAL] * 2  # first: no wait
    assert sd.details(cache_dir, ["ghi3", "def2"], interval=0.25)["ghi3"]["id"] == "ghi3"
    assert len(http_server.requests("/line/")) == 6
    for bad in ("../x", "a/b", "", "x y", "a" * 200):
        with pytest.raises(ValueError):
            sd.details(cache_dir, ["new1", bad])
    assert len(http_server.requests("/line/")) == 6


def test_command_line(http_server, served, tmp_path, monkeypatch, capsys):
    """fetch, status (per type and country, the flags) and details from the command line."""
    data = os.path.join(str(tmp_path), "data")
    assert sd.main(["status", "--data-dir", data]) == 1
    assert sd.main(["fetch", "--data-dir", data]) == 0
    assert "downloaded" in capsys.readouterr().out
    assert sd.main(["fetch", "--update", "--data-dir", data]) == 0
    assert "unchanged (304)" in capsys.readouterr().out
    assert sd.main(["status", "--data-dir", data, "--top", "2"]) == 0
    out = capsys.readouterr().out
    assert "Lines: 6 of 6 features" in out and f"  {'highline':<10} {2:>6}\n" in out and "Spots: 1" in out
    assert f"  {'SK':<3} {2:>6} {1:>6} {0:>6}\n  {'XA':<3} {2:>6} {1:>6} {1:>6}\n\n" in out  # the top 2
    assert f"  {'length_mismatch':<16} {1:>6} {1:>6}\n" in out and f"  {'geometry ok':<16} {3:>6} {1:>6}\n" in out
    assert f"  {'no_length':<16} {1:>6} {0:>6}\n" in out and f"  {'coarse_anchor':<16} {1:>6} {1:>6}\n" in out
    monkeypatch.setattr(sd, "DETAILS_URL", http_server.url("/line/{id}/details"))
    http_server.route("/line/", lambda request: Answer(200, b'{"id": "1"}', {"Content-Type": "application/json"}))
    ids = tmp_path / "ids.txt"
    ids.write_text("abc1\n# a comment\n\nabc2  # another\n", encoding="utf-8")
    assert sd.main(["details", "--ids", str(ids), "abc3", "--interval", "0", "--data-dir", data]) == 0
    assert "3 ids, 0 cached before, 3 asked, 0 not found" in capsys.readouterr().out
    assert sd.main(["status", "--data-dir", data]) == 0
    assert "Details cached: 3 (0 not found)" in capsys.readouterr().out
    assert sd.main(["details", "--ids", "../x", "--data-dir", data]) == 1
