"""Keys of data services (settings.ServiceKeys): read when needed, a layer without its key
unavailable, the key in a WCS's requests (also WCS 1.0.0), and never in an error, the cache's
index, the counts of servicecounts, a job's events or the deployment's other services."""

import os
import re
import sqlite3
import sys
from urllib.parse import quote

import numpy as np
import pytest
import rasterio as rio
import yaml
from rasterio.io import MemoryFile
from rasterio.transform import from_origin

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cache  # noqa: E402
import jobs  # noqa: E402
import servicecounts  # noqa: E402
import settings  # noqa: E402
import sources as src  # noqa: E402
from sources import probe  # noqa: E402
from http_server import Answer  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOKEN = "key-3f9a1c7e5b2d+/="  # an API key with characters a URL encodes: the encoded form is masked too
EXTENT = (500000.0, 6000000.0, 504000.0, 6004000.0)  # the fake coverage in EPSG:25832


@pytest.fixture(autouse=True)
def no_keys(monkeypatch, tmp_path):
    """No key from the environment or a secrets folder of the machine running the tests."""
    for name in settings.ServiceKeys.model_fields:
        monkeypatch.delenv(name.upper(), raising=False)
    monkeypatch.setattr(settings, "SECRETS_DIR", str(tmp_path / "no-secrets"))


def height(x, y):
    return (100 + (x - EXTENT[0]) / 100 + (y - EXTENT[1]) / 10000).astype(np.float32)


def wcs10(token: str, echo: bool = False):
    """A WCS 1.0.0 as the OGC specification (03-065r6) has it, which answers only with its API key in
    the query parameter apikey (Datafordeler: 401 with a problem+json "Access denied. No
    authentication method found."; with echo, the error names the request's query, as some servers
    do): DescribeCoverage with the spatial domain in EPSG:25832, GetCoverage of a BBOX (the pixels'
    outer edges) in WIDTH x HEIGHT pixels as a GeoTIFF."""
    def handle(request):
        query = dict((k.upper(), v) for k, v in request.query)
        if dict(request.query).get("apikey") != token:
            detail = "Access denied. No authentication method found. Please verify your use of API key or OAuth."
            if echo:
                detail += f" Request: {'&'.join(f'{k}={v}' for k, v in request.query)}"
            body = ('{"title":"Unauthorized","status":401,"detail":"%s","errorCode":"DAF-AUTH-0005"}' % detail)
            return Answer(401, body.encode(), {"Content-Type": "application/problem+json"})
        assert query["SERVICE"] == "WCS" and query["VERSION"] == "1.0.0"
        if query["REQUEST"] == "DescribeCoverage":
            assert query["COVERAGE"] == "dhm_terraen"
            body = f"""<?xml version="1.0"?><CoverageDescription version="1.0.0" xmlns="http://www.opengis.net/wcs"
 xmlns:gml="http://www.opengis.net/gml"><CoverageOffering><name>dhm_terraen</name>
<lonLatEnvelope srsName="urn:ogc:def:crs:OGC:1.3:CRS84"><gml:pos>8.0 54.4</gml:pos><gml:pos>15.6 57.8</gml:pos></lonLatEnvelope>
<domainSet><spatialDomain><gml:Envelope srsName="EPSG:4326"><gml:pos>8.0 54.4</gml:pos><gml:pos>15.6 57.8</gml:pos></gml:Envelope>
<gml:Envelope srsName="EPSG:25832"><gml:pos>{EXTENT[0]} {EXTENT[1]}</gml:pos><gml:pos>{EXTENT[2]} {EXTENT[3]}</gml:pos></gml:Envelope>
</spatialDomain></domainSet><supportedFormats><formats>GTiff</formats></supportedFormats></CoverageOffering></CoverageDescription>"""
            return Answer(200, body.encode(), {"Content-Type": "text/xml"})
        assert query["REQUEST"] == "GetCoverage" and query["COVERAGE"] == "dhm_terraen"
        assert query["CRS"] == "EPSG:25832" and query["FORMAT"] == "GTiff"
        left, bottom, right, top = map(float, query["BBOX"].split(","))
        if left >= EXTENT[2] or bottom >= EXTENT[3] or right <= EXTENT[0] or top <= EXTENT[1]:
            return Answer(404, b"outside", {"Content-Type": "text/plain"})
        width, rows = int(query["WIDTH"]), int(query["HEIGHT"])
        res = (right - left) / width
        ys, xs = np.mgrid[0:rows, 0:width]
        band = height(left + (xs + 0.5) * res, top - (ys + 0.5) * res)
        with MemoryFile() as memfile:
            with memfile.open(driver="GTiff", width=width, height=rows, count=1, dtype="float32", crs="EPSG:25832",
                              transform=from_origin(left, top, res, res)) as dst:
                dst.write(band, 1)
            return Answer(200, memfile.read(), {"Content-Type": "image/tiff"})
    return handle


def danish_layer(url: str, tile_px: int = 100) -> src.WcsTiles:
    return src.WcsTiles("DHM terrain", url, "dhm_terraen", "EPSG:25832", "fake/dhm", native_res=0.4, tile_px=tile_px,
                        fmt="GTiff", version="1.0.0", key_params=(("apikey", "datafordeler_api_key"),))


def test_service_keys(monkeypatch, tmp_path):
    """A key from the environment (upper case) or a Docker secret (lower case), the environment
    first; empty means none; a name that is no field is an error."""
    assert set(settings.ServiceKeys.model_fields) == {"opentopography_api_key", "datafordeler_api_key",
                                                      "lantmateriet_user", "lantmateriet_password", "nls_api_key"}
    secrets = tmp_path / "secrets"
    secrets.mkdir()
    assert settings.service_key("datafordeler_api_key", str(secrets)) is None
    (secrets / "datafordeler_api_key").write_text("from-secret\n")
    assert settings.service_key("datafordeler_api_key", str(secrets)) == "from-secret"
    monkeypatch.setenv("DATAFORDELER_API_KEY", "from-env")
    assert settings.service_key("datafordeler_api_key", str(secrets)) == "from-env"
    monkeypatch.setenv("DATAFORDELER_API_KEY", "  ")
    (secrets / "datafordeler_api_key").write_text("")
    assert settings.service_key("datafordeler_api_key", str(secrets)) is None
    with pytest.raises(KeyError):
        settings.service_key("no_such_key")
    assert settings.missing_keys(()) is None
    assert settings.missing_keys(("nls_api_key",)) == "not set: NLS_API_KEY (or the Docker secret nls_api_key)"


def test_redact(monkeypatch):
    """The value of a key, as it is and URL-encoded, is masked in messages, the cache's URLs and the
    public site's texts; short values are left alone."""
    monkeypatch.setenv("DATAFORDELER_API_KEY", TOKEN)
    monkeypatch.setenv("NLS_API_KEY", "abc")  # too short to mask
    text = f"HTTP 403: bad token {TOKEN} ({quote(TOKEN, safe='')}), abc"
    assert settings.redact(text) == "HTTP 403: bad token *** (***), abc"
    assert TOKEN not in cache.clean_error(RuntimeError(text))
    url = f"https://api.example/wcs?SERVICE=WCS&token={quote(TOKEN, safe='')}&x={TOKEN}"
    assert TOKEN not in cache.clean_url(url) and quote(TOKEN, safe="") not in cache.clean_url(url)
    redact = jobs.Redact(ROOT)
    assert redact({"error": [f"failed with {TOKEN}"]}) == {"error": ["failed with ***"]}
    assert cache.clean_url(None) is None and settings.redact("") == ""


def test_layer_without_its_key(monkeypatch, tmp_path):
    """A layer naming a key is unavailable without it (the message names the variable and the
    Docker secret, never a value), and its download asks nothing; with the key it is available."""
    layer = danish_layer("https://wcs.invalid/dhm")
    assert layer.keys == ("datafordeler_api_key",)
    why = layer.unavailable()
    assert "DATAFORDELER_API_KEY" in why and "Docker secret datafordeler_api_key" in why
    source = src.Source(id="fake_dk", name="Fake", description="Fake", nmt=layer, sample=(55.0, 12.4))
    assert src.source_unavailable(source) == why
    assert probe.skip_reason(source, True, None) == why
    with pytest.raises(RuntimeError, match="DATAFORDELER_API_KEY"):
        layer.download_tile((1.0, 5000, 60000), str(tmp_path / "t.tif"))
    monkeypatch.setenv("DATAFORDELER_API_KEY", TOKEN)
    assert layer.unavailable() is None and src.source_unavailable(source) is None
    # The layers without keys stay as they were
    assert src.SOURCES["europe"].nmt.keys == () and src.SOURCES["europe"].nmt.unavailable() is None


def test_wcs10_with_its_key(http_server, monkeypatch, tmp_path):
    """WCS 1.0.0 with the API key in every request: the tile on its own pixels, the extent from
    DescribeCoverage; the cache's index records the request without the key, servicecounts
    the host only."""
    http_server.route("/dhm", wcs10(TOKEN))
    monkeypatch.setenv("DATAFORDELER_API_KEY", TOKEN)
    rows = []
    servicecounts.enable(rows.extend, interval=False)
    layer = danish_layer(http_server.url("/dhm"))
    cache_dir = str(tmp_path / "cache")
    tile = (1.0, 5000, 60000)  # 100 m tiles at 1 m: 500000-500100 / 6000000-6000100
    assert layer.tile_url(tile) == http_server.url("/dhm")  # the host slot's URL, no key
    assert layer._download_and_record(tile, cache_dir) > 0
    path = layer.tile_path(cache_dir, tile)
    with rio.open(path) as f:
        assert f.transform == from_origin(500000, 6000100, 1, 1)
        ys, xs = np.mgrid[0:100, 0:100]
        assert np.array_equal(f.read(1), height(500000 + xs + 0.5, 6000100 - ys - 0.5))
    asked = http_server.requests("/dhm")
    query = dict(asked[-1].query)
    assert query["apikey"] == TOKEN and query["BBOX"] == "500000.000,6000000.000,500100.000,6000100.000"
    assert (query["WIDTH"], query["HEIGHT"], query["VERSION"]) == ("100", "100", "1.0.0")
    with sqlite3.connect(os.path.join(cache_dir, "fake", "index.sqlite")) as db:
        recorded = db.execute("SELECT url FROM files").fetchall()
    assert recorded and all(TOKEN not in u and quote(TOKEN, safe="") not in u for (u,) in recorded)
    assert layer.coverage_extent() == EXTENT
    assert dict(http_server.requests("/dhm")[-1].query)["apikey"] == TOKEN  # DescribeCoverage too
    servicecounts.flush()
    assert rows and {host for host, *_ in rows} == {"127.0.0.1"}
    # Beyond the coverage: 404, missing
    assert layer._download_and_record((1.0, 5100, 60000), cache_dir) == 0


def test_wrong_key_never_in_the_error(http_server, monkeypatch, tmp_path):
    """A key the service refuses (its error echoing the request's query): the download fails with
    the server's message, and the message never holds the key."""
    http_server.route("/dhm", wcs10("the-right-one", echo=True))
    monkeypatch.setenv("DATAFORDELER_API_KEY", TOKEN)
    monkeypatch.setattr(src.net, "_sleep", lambda attempt: None)
    layer = danish_layer(http_server.url("/dhm"))
    with pytest.raises(RuntimeError) as error:
        layer._download_and_record((1.0, 5000, 60000), str(tmp_path / "cache"))
    message = str(error.value)
    assert "Access denied" in message and "HTTP 401" in message
    assert TOKEN not in message and quote(TOKEN, safe="") not in message and "apikey=" not in message.replace(
        "apikey=***", "")


def test_wcs20_requests_unchanged():
    """A 2.0.1 reader without keys asks what it asked before (the regression's sources)."""
    layer = src.WcsTiles("Fake DTM", "https://wcs.example/ows", "dtm", "EPSG:32633", "fake/dtm/1", native_res=1.0,
                         tile_px=100, fetch_res=1.0, axes=("E", "N"), params=(("A", "b"),))
    assert layer.reader.coverage_params(0, 0, 100, 100, 1.0) == [
        ("SERVICE", "WCS"), ("VERSION", "2.0.1"), ("REQUEST", "GetCoverage"), ("COVERAGEID", "dtm"),
        ("FORMAT", "image/tiff"), ("SUBSET", "E(0.000,100.000)"), ("SUBSET", "N(0.000,100.000)"), ("A", "b")]
    assert layer.reader.describe_params() == [("SERVICE", "WCS"), ("VERSION", "2.0.1"),
                                              ("REQUEST", "DescribeCoverage"), ("COVERAGEID", "dtm")]
    with pytest.raises(ValueError):
        src.WcsTiles("x", "https://x", "c", "EPSG:32633", "f", 1.0, version="1.1.1")


def test_keys_are_the_workers_secrets():
    """The keys of ServiceKeys are Docker secrets of the worker only (compose.yaml), with an empty
    example file each (deploy/secrets.example) and the owner set by deploy/vps.sh."""
    names = set(settings.ServiceKeys.model_fields)
    with open(os.path.join(ROOT, "compose.yaml"), encoding="utf-8") as f:
        compose = yaml.safe_load(f)
    assert set(compose["services"]["worker"]["secrets"]) == names
    assert not names & set(compose["services"]["web"].get("secrets", []))
    assert all(compose["secrets"][n] == {"file": f"./secrets/{n}"} for n in names)
    examples = os.path.join(ROOT, "deploy", "secrets.example")
    assert all(os.path.getsize(os.path.join(examples, n)) == 0 for n in names)
    with open(os.path.join(ROOT, "deploy", "vps.sh"), encoding="utf-8") as f:
        listed = re.search(r"^WORKER_SECRETS=\(([^)]*)\)", f.read(), re.M).group(1).split()
    assert set(listed) == names
