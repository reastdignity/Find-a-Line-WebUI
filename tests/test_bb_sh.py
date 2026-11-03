"""Brandenburg with Berlin and Schleswig-Holstein: LGB's WCS extent to the millimetre (its edge tiles missing,
not failed), the CA bundle of a host with an incomplete TLS chain (net.verify), the GeoJSON listing
(GeoJsonFiles) on a recorded index, the plain XYZ files (XyzFile: an outdated link's HTML page is an error that
makes the index be read again), and the catalogue's two sources (offline: tests/http_server.py)."""

import datetime
import glob
import gzip
import json
import os
import warnings

import numpy as np
import pytest
import rasterio as rio
import requests
from cryptography import x509
from cryptography.hazmat.primitives import hashes

import cache
import sources as src
from grid import make_grid
from sources import net
from sources.catalogue import germany
from sources.indexes import geojsonfiles
from sources.indexes.cached import IndexUnavailable
from sources.indexes.geojsonfiles import file_name, parse_features
from sources.layers.geojson import GeoJsonTiles, XyzFile, XyzSheet
from sources.readers.wcsreader import WcsReader
from http_server import Answer  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
RECORDED = os.path.join(HERE, "data", "recorded", "bb_sh")
SH_HOST = "https://geodaten.schleswig-holstein.de"
SH_FINGERPRINT = "199ab2aaafff40401e0a3b7b87ee9964659effa94a1fecbe918ae136e4b4e0a8"


def _body(name: str) -> bytes:
    with open(os.path.join(RECORDED, name), "rb") as f:
        return f.read()


@pytest.fixture
def no_sleep(monkeypatch):
    monkeypatch.setattr(net, "_sleep", lambda attempt: None)


# --- the CA bundle of a host with an incomplete chain ---

def _certificates(data: bytes):
    """The certificates of a PEM bundle, each read alone (certifi holds a root with a serial number that
    cryptography warns about)."""
    marker = b"-----BEGIN CERTIFICATE-----"
    found = []
    for block in data.split(marker)[1:]:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            found.append(x509.load_pem_x509_certificate(marker + block.split(b"-----END CERTIFICATE-----")[0]
                                                        + b"-----END CERTIFICATE-----\n"))
    return found


def test_bundled_intermediate():
    """The intermediate kept for Schleswig-Holstein's server is the one recorded (fingerprint, names), still
    valid, and issued by a root of certifi (its signature checked)."""
    with open(os.path.join(net.CERTS, net.HOST_CA_OF["geodaten.schleswig-holstein.de"]), "rb") as f:
        (cert,) = _certificates(f.read())
    assert cert.fingerprint(hashes.SHA256()).hex() == SH_FINGERPRINT
    assert cert.subject.rfc4514_string() == "CN=D-TRUST BR CA 1-20-1 2020,O=D-Trust GmbH,C=DE"
    assert cert.issuer.rfc4514_string() == "CN=D-TRUST BR Root CA 1 2020,O=D-Trust GmbH,C=DE"
    assert cert.not_valid_after_utc == datetime.datetime(2035, 2, 11, 9, 44, 59, tzinfo=datetime.timezone.utc)
    assert cert.not_valid_after_utc > datetime.datetime.now(datetime.timezone.utc)
    with open(requests.certs.where(), "rb") as f:
        roots = [c for c in _certificates(f.read()) if c.subject == cert.issuer]
    assert roots
    cert.verify_directly_issued_by(roots[0])


def test_verify_per_host(tmp_path, monkeypatch):
    """Only the hosts of HOST_CA_OF get a bundle: certifi's roots and the intermediate, written once into the
    temporary folder; every other host (and a local path) verifies against certifi's roots as before."""
    import tempfile
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    monkeypatch.setattr(net, "_bundles", {})
    assert net.verify("https://inspire.brandenburg.de/services/el_dgm1_wcs") is True
    assert net.verify("/a/local/path") is True and net.verify(None) is True
    path = net.verify(f"{SH_HOST}/gaialight-sh/_apps/dladownload/massen.php?file=x.xyz")
    assert os.path.dirname(path) == str(tmp_path) and os.path.basename(path).startswith("findaline-ca-")
    with open(path, "rb") as f:
        bundle = f.read()
    with open(requests.certs.where(), "rb") as f:
        roots = f.read()
    with open(os.path.join(net.CERTS, "d-trust-br-ca-1-20-1-2020.pem"), "rb") as f:
        extra = f.read()
    assert bundle.startswith(roots.rstrip(b"\n")) and bundle.endswith(extra)
    assert bundle.count(b"BEGIN CERTIFICATE") == roots.count(b"BEGIN CERTIFICATE") + 1
    os.utime(path, (0, 0))
    assert net.verify(f"{SH_HOST}/x") == path and os.stat(path).st_mtime == 0  # not written again
    import ssl
    ssl.create_default_context(cafile=path)  # OpenSSL reads it


def test_get_passes_the_bundle(monkeypatch):
    """net._get verifies each request against its host's bundle."""
    seen = []

    class Response:
        status_code, headers, content, text = 200, {"content-type": "image/tiff"}, b"x", ""

    def get(url, **kwargs):
        seen.append(kwargs.get("verify"))
        return Response()
    monkeypatch.setattr(net.requests, "get", get)
    net._get("https://example.org/a.tif")
    net._get(f"{SH_HOST}/b.tif")
    assert seen[0] is True and seen[1] == net.verify(f"{SH_HOST}/b.tif") and seen[1] is not True


# --- Brandenburg's WCS ---

def _bb_reader(server) -> WcsReader:
    layer = src.SOURCES["brandenburg"].nmt
    return WcsReader("DGM1 (test)", server.url("/bb/wcs"), layer.coverage, layer.crs, 1.0, 2000, "image/tiff",
                     ("x", "y"), None, True, params=layer.params)


def test_extent_to_the_millimetre(http_server):
    """LGB gives its whole-metre extent with 0.01 mm of noise; the extent is read to the millimetre."""
    http_server.route("/bb/wcs", lambda r: Answer(200, _body("003-bb-dgm1-describe.xml"), {"Content-Type": "text/xml"}))
    assert _bb_reader(http_server).coverage_extent() == (248000.0, 5690000.0, 466000.0, 5936000.0)


@pytest.mark.parametrize("tile", [(1.0, 233, 2900), (1.0, 150, 2844)])
def test_edge_tiles_missing(http_server, tmp_path, no_sleep, tile):
    """The tile east of the last column (466-468 km) and the one south of the last row (5688-5690 km) are
    answered HTTP 400; reaching 0.01 mm into the extent as given, they are missing, not failed, and once the
    extent is known such a tile is not asked."""
    def answer(request):
        query = dict(request.query)
        if query.get("REQUEST") == "DescribeCoverage":
            return Answer(200, _body("003-bb-dgm1-describe.xml"), {"Content-Type": "text/xml"})
        return Answer(400, _body("004-bb-beyond.html"), {"Content-Type": "text/html"})
    http_server.route("/bb/wcs", answer)
    reader = _bb_reader(http_server)
    path = str(tmp_path / "tile.tif")
    assert reader.fetch(tile, path).received == 0 and not os.path.exists(path)
    asked = len(http_server.requests("/bb/"))
    assert reader.fetch(tile, path).received == 0 and len(http_server.requests("/bb/")) == asked
    with pytest.raises(RuntimeError, match="HTTP 400"):  # inside the extent an error stays one
        reader.fetch((1.0, 207, 2908), path)


# --- the GeoJSON listing ---

def test_parse_features():
    files = parse_features(_body("001-sh-dgm1.geojson"), "link_data")
    assert len(files) == 27
    assert files["dgm1_32_426_6005_1_sh_2025.xyz"] == (
        f"{SH_HOST}/gaialight-sh/_apps/dladownload/massen.php?file=dgm1_32_426_6005_1_sh_2025.xyz&id=2&live=2025"
        "&km=32420_6000")
    assert file_name("https://h/a/b/c.tif?x=1") == "c.tif"
    for body in (_body("002-sh-stale.html"), b"", b"[]", b'{"type": "Feature"}', b'{"type": "FeatureCollection"}'):
        with pytest.raises(ValueError):
            parse_features(body, "link_data")
    odd = {"type": "FeatureCollection", "features": [{"properties": {"link_data": "ftp://h/a.xyz"}},
                                                     {"properties": {}}, "x", {"properties": {"link_data": 3}}]}
    assert parse_features(json.dumps(odd).encode(), "link_data") == {}


def _sh_layer(server, **kwargs) -> GeoJsonTiles:
    return GeoJsonTiles("DGM1 (test)", [server.url("/sh/index.geojson")], germany.SH_NAME, "test_sh/dgm1",
                        "EPSG:25832", "dgm1", **kwargs)


def _serve_index(server, body=None, status=200, kind="application/txt"):
    body = _body("001-sh-dgm1.geojson") if body is None else body
    server.add("/sh/index.geojson", body.replace(SH_HOST.encode(), server.base.encode()), kind, status=status)


def test_listing_asks_once(http_server, tmp_path):
    """The statewide index is asked once and kept (gzipped, the files matching the name): every 0.25° tile is
    picked from it; the items are the Metalink listing's."""
    _serve_index(http_server)
    cache_dir = str(tmp_path / "cache")
    layer = _sh_layer(http_server)
    sheets = layer.index.answers(cache_dir, 54.0, 7.75)
    assert len(sheets) == 25 and len(http_server.requests("/sh/")) == 1
    lange_anna = next(s for s in sheets if s["godlo"] == "426_6005")
    assert lange_anna == {"year": 2025, "godlo": "426_6005", "crs": "EPSG:25832", "res": 1.0, "sha256": None,
                          "size": None, "extent": [426000, 6005000, 427000, 6006000],
                          "url": http_server.url("/gaialight-sh/_apps/dladownload/massen.php?file=dgm1_32_426_6005_1_sh"
                                                 "_2025.xyz&id=2&live=2025&km=32420_6000")}
    kept = os.path.join(cache_dir, "test_sh", "geojson", "dgm1.json.gz")
    with gzip.open(kept, "rt", encoding="utf-8") as f:
        assert len(json.load(f)["files"]) == 27
    assert layer.index.answers(cache_dir, 52.0, 13.0) == []
    assert len(http_server.requests("/sh/")) == 1
    grid = make_grid((425800, 6004800, 426600, 6005600), 1.0, "EPSG:25832")
    layer._use(cache_dir)
    tiles = layer.tiles(grid)
    assert sorted((t.godlo, t.year) for t in tiles) == [("425_6004", 2025), ("425_6005", 2025), ("426_6004", 2025),
                                                        ("426_6005", 2025)]
    tile = next(t for t in tiles if t.godlo == "426_6005")
    assert layer.tile_path(cache_dir, tile).replace(os.sep, "/").endswith(
        f"test_sh/dgm1/42_600/426_6005_2025_{tile.key}.tif")


@pytest.mark.parametrize("status, body, kind", [(404, b"not found", "text/html"),
                                                (200, None, "text/html"),
                                                (200, b"{}", "application/txt")])
def test_listing_error_answers(http_server, tmp_path, status, body, kind):
    """An index that cannot be had is IndexUnavailable, and nothing is kept."""
    _serve_index(http_server, _body("002-sh-stale.html") if body is None else body, status, kind)
    cache_dir = str(tmp_path / "cache")
    with pytest.raises(IndexUnavailable):
        _sh_layer(http_server).index.answers(cache_dir, 54.0, 7.75)
    assert not glob.glob(os.path.join(cache_dir, "test_sh", "*", "*"))


def test_listing_too_large(http_server, tmp_path, monkeypatch):
    monkeypatch.setattr(geojsonfiles, "GEOJSON_MAX_BYTES", 5000)
    _serve_index(http_server)
    with pytest.raises(IndexUnavailable, match="more than 5000 bytes"):
        _sh_layer(http_server).index.answers(str(tmp_path / "cache"), 54.0, 7.75)


# --- the XYZ files ---

def _xyz(east_km: int, north_km: int, n: int = 4) -> bytes:
    """n x n cell centres at the north-west corner of a 1 km tile, rows from the north, as LVermGeo SH writes them."""
    lines = []
    for row in range(n):
        for col in range(n):
            x, y = east_km * 1000 + col + 0.5, north_km * 1000 + 1000 - row - 0.5
            lines.append(f"{x:.2f} {y:.2f} {row * 10 + col + 0.25:.2f}")
    return ("\n".join(lines) + "\n").encode()


def _serve_files(server, files, stale=()):
    """massen.php: the files of `files` (name: body), the stale page for the names in stale, else 404."""
    def answer(request):
        name = dict(request.query).get("file", "")
        if name in stale:
            return Answer(200, _body("002-sh-stale.html"), {"Content-Type": "text/html; charset=UTF-8"})
        if name in files:
            return Answer(200, files[name], {"Content-Type": "text/plain;charset=UTF-8",
                                             "Content-Disposition": f'attachment; filename="{name}"'})
        return Answer(404, b"", {"Content-Type": "text/html"})
    server.route("/gaialight-sh/_apps/dladownload/massen.php", answer)


def test_tile_downloaded(http_server, tmp_path):
    """A tile's XYZ text becomes its GeoTIFF on the cell edges (whole metres), rows from the north."""
    _serve_index(http_server)
    _serve_files(http_server, {"dgm1_32_426_6005_1_sh_2025.xyz": _xyz(426, 6005)})
    cache_dir = str(tmp_path / "cache")
    layer = _sh_layer(http_server)
    grid = make_grid((426000, 6005990, 426010, 6006000), 1.0, "EPSG:25832")
    assert layer.missing(grid, cache_dir, None)
    layer.download(grid, cache_dir, None, "terrain")
    (path,) = layer.files(grid, cache_dir)
    with rio.open(path) as tile:
        assert tile.crs.to_epsg() == 25832 and tile.transform[:6] == (1.0, 0.0, 426000.0, 0.0, -1.0, 6006000.0)
        values = tile.read(1)
    assert values.shape == (4, 4) and values[0, 0] == np.float32(0.25) and values[3, 1] == np.float32(31.25)
    assert cache.state(cache_dir, path) == "ok"


def test_stale_link_reads_the_index_again(http_server, tmp_path, no_sleep):
    """An outdated link answers an HTML page: an error at once (not tried again), nothing cached, and the kept
    index and its 0.25° answers forgotten, so the next search asks the index again."""
    _serve_index(http_server)
    _serve_files(http_server, {}, stale={"dgm1_32_426_6005_1_sh_2025.xyz"})
    cache_dir = str(tmp_path / "cache")
    layer = _sh_layer(http_server)
    layer._use(cache_dir)
    grid = make_grid((426000, 6005990, 426010, 6006000), 1.0, "EPSG:25832")
    (tile,) = layer.tiles(grid)
    path = layer.tile_path(cache_dir, tile)
    with pytest.raises(RuntimeError, match="veraltet.*index is read again"):
        layer.download_tile(tile, path)
    assert len(http_server.requests("/gaialight-sh/")) == 1 and not os.path.exists(path)
    assert not os.path.exists(os.path.join(cache_dir, "test_sh", "geojson", "dgm1.json.gz"))
    assert not glob.glob(os.path.join(cache_dir, "test_sh", "sheet-index", "dgm1", "*.json"))
    assert cache.state(cache_dir, path) is None
    layer.index.answers(cache_dir, 54.0, 7.75)
    assert len(http_server.requests("/sh/")) == 2


def test_file_answers(http_server, tmp_path, no_sleep):
    """A 404 is no data; another content type, a body over max_bytes or text that is no XYZ grid fails."""
    _serve_files(http_server, {"big.xyz": _xyz(1, 1, 30), "bad.xyz": b"no numbers here\n"})
    http_server.add("/other.xyz", b"\x00" * 10, "application/octet-stream")
    reader = XyzFile("DGM1 (test)", max_bytes=10_000)
    path = str(tmp_path / "t.tif")
    base = http_server.url("/gaialight-sh/_apps/dladownload/massen.php?file=")
    assert reader.fetch(XyzSheet(base + "none.xyz", "x", "EPSG:25832", 1.0), path).received == 0
    with pytest.raises(RuntimeError, match="more than 10000 bytes"):
        reader.fetch(XyzSheet(base + "big.xyz", "x", "EPSG:25832", 1.0), path)
    with pytest.raises(RuntimeError, match="text/plain expected"):
        reader.fetch(XyzSheet(http_server.url("/other.xyz"), "x", "EPSG:25832", 1.0), path)
    with pytest.raises(RuntimeError, match="not an XYZ grid"):
        reader.fetch(XyzSheet(base + "bad.xyz", "x", "EPSG:25832", 1.0), path)
    assert not os.path.exists(path)


# --- the catalogue ---

def test_sources():
    bb, sh = src.SOURCES["brandenburg"], src.SOURCES["schleswig_holstein"]
    assert bb.regions == ("de-bb", "de-be") and sh.regions == ("de-sh",)
    assert bb.nmt.zero_is_nodata and not bb.nmpt.zero_is_nodata
    assert bb.nmt.params == (("GEOTIFF:COMPRESSION", "DEFLATE"),) == bb.nmpt.params
    assert isinstance(sh.nmt, GeoJsonTiles) and sh.nmpt is None
    assert sh.nmt.index_url == germany.SH_INDEX and net.verify(germany.SH_INDEX) is not True
    for host in ("inspire.brandenburg.de", "geodaten.schleswig-holstein.de"):
        assert src.HOST_SLOTS_OF[host] == 4
    assert "image matching" in bb.note and "constant 1.30 m" in sh.note
    assert sh.sea_fill == 1.30 and bb.sea_fill is None
    from sources import probe
    assert probe.strategy(sh.nmt) == "text" and probe.strategy(bb.nmt) == "wcs"


@pytest.mark.parametrize("sea_fill", [None, 1.30])
def test_sea_fill_counts_as_water(tmp_path, sea_fill):
    """A source's constant over the sea (LVermGeo SH's 1.30 m) is water inside the sea zone only, to the
    centimetre (a beach of 1.31 m stays land), and keeps its height; without sea_fill only the gaps filled with
    0 m and data of at most SEA_LEVEL_TOLERANCE are."""
    grid = make_grid((0, 0, 10, 4), 1.0, "EPSG:25832")
    z = np.full((4, 10), 5.0, dtype="float32")
    z[:, :5] = 1.30          # the sea zone: the provider's fill
    z[0, 0] = np.nan         # a gap in it: filled with 0 m
    z[1, 1] = 0.40           # sea at about 0 m
    z[2, 4] = 1.31           # a beach
    z[3, 7] = 1.30           # land of that height outside the zone
    path = str(tmp_path / "nmt.npy")
    np.save(path, z)
    zone = np.zeros((4, 10), bool)
    zone[:, :5] = True
    out = src.fill_water(path, None, grid, np.zeros((4, 10), "uint8"), zone, str(tmp_path / "water.npy"),
                         sea_value=sea_fill)
    water = np.load(out)
    expected = np.zeros((4, 10), bool)
    expected[0, 0] = expected[1, 1] = True
    if sea_fill is not None:
        expected[:, :5] = True
        expected[2, 4] = False
    assert (water == expected).all()
    filled = np.load(path)
    assert filled[0, 0] == 0.0 and filled[2, 0] == np.float32(1.30)


def test_probe_reads_the_first_kb(monkeypatch, tmp_path):
    """The probe asks a tile's XYZ file without a Range (its server has none) and wants text/plain whose first
    line holds three numbers: an outdated link's HTML page fails."""
    from sources import probe
    from sources.indexes.metalink import ShaTile
    layer = src.SOURCES["schleswig_holstein"].nmt
    tile = ShaTile(426, 6005, 2025, "0123abcd", f"{SH_HOST}/a.php?file=dgm1_32_426_6005_1_sh_2025.xyz")
    asked = []

    def answer(kind, body):
        def http(url, params=None, headers=None):
            asked.append(headers)
            return 200, kind, body
        return http
    monkeypatch.setattr(probe, "_http", answer("text/plain;charset=UTF-8", b"426000.50 6005999.50 12.34\n426001.50"))
    assert probe._xyz_head(str(tmp_path), layer, tile) == "" and asked == [None]
    for kind, body in (("text/html; charset=UTF-8", _body("002-sh-stale.html")), ("text/plain", b"<html>")):
        monkeypatch.setattr(probe, "_http", answer(kind, body))
        with pytest.raises(RuntimeError, match="HTTP 200"):
            probe._xyz_head(str(tmp_path), layer, tile)
