"""Bavaria and Rhineland-Palatinate: the Metalink listing (RFC 5854) on recorded and made-up documents, the
version policy of files known by their SHA-256, Download's averaging and forced CRS, and the catalogue's two
sources (offline: tests/http_server.py)."""

import gzip
import hashlib
import json
import os

import numpy as np
import pytest
import rasterio as rio
import rasterio.warp
from rasterio.crs import CRS
from rasterio.enums import Resampling
from rasterio.transform import from_origin

import cache
import sources as src
from grid import make_grid
from sources.indexes.cached import IndexUnavailable
from sources.indexes.metalink import MetalinkFiles, ShaPerTile, parse_metalink
from sources.layers.metalink import MetalinkTiles
from sources.readers.download import Download, _block_means

HERE = os.path.dirname(os.path.abspath(__file__))
RECORDED = os.path.join(HERE, "data", "recorded", "metalink")
BY_DGM = r"^(?P<east>\d{3})_(?P<north>\d{4})\.tif$"
BY_DOM = r"^32(?P<east>\d{3})_(?P<north>\d{4})_20_DOM\.tif$"
RP_DGM = r"^dgm1_32_(?P<east>\d+)_(?P<north>\d+)_1_rp_(?P<year>\d{4})\.tif$"


def _body(name: str) -> bytes:
    with open(os.path.join(RECORDED, name), "rb") as f:
        return f.read()


def _metalink(files, ns="urn:ietf:params:xml:ns:metalink") -> bytes:
    """A Metalink 4 document of files: (name, sha256 or None, [(url, priority or None)], size or None)."""
    parts = [f'<?xml version="1.0" encoding="UTF-8"?>\n<metalink xmlns="{ns}">\n'
             "<published>2026-11-02T00:00:00Z</published>\n"]
    for name, sha, urls, size in files:
        parts.append(f'<file name="{name}">')
        if size is not None:
            parts.append(f"<size>{size}</size>")
        if sha:
            parts.append(f'<hash type="md5">00</hash><hash type="sha-256">{sha}</hash>')
        for url, priority in urls:
            parts.append(f'<url priority="{priority}">{url}</url>' if priority else f"<url>{url}</url>")
        parts.append('<metaurl mediatype="torrent">https://example/x.torrent</metaurl></file>\n')
    parts.append("</metalink>\n")
    return "".join(parts).encode()


# --- RFC 5854 ---

def test_recorded_documents():
    published, files = parse_metalink(_body("001-bavaria-dgm1.meta4"))
    assert published == "2026-10-28T06:21:35Z" and len(files) == 82
    first = files[0]
    assert first.name == "702_5531.tif" and first.size == 3290056
    assert first.sha256 == "11ebc4952f74458e967a97425bb9695059b1bd78389264328b75640e56c876ad"
    assert first.urls == ("https://download1.bayernwolke.de/a/dgm/dgm1/702_5531.tif",
                          "https://download2.bayernwolke.de/a/dgm/dgm1/702_5531.tif")
    published, files = parse_metalink(_body("003-rlp-dgm1.meta4"))
    assert published == "2026-08-12 09:59:52.573104+00:00"  # not RFC 3339: kept as text
    assert len(files) == 40 and sum(f.name.endswith(".tif") for f in files) == 20
    assert all(len(f.sha256) == 64 and len(f.urls) == 1 for f in files)
    assert len(parse_metalink(_body("002-bavaria-dom20.meta4"))[1]) == 82
    assert len(parse_metalink(_body("004-rlp-dom1.meta4"))[1]) == 20


def test_rfc_5854_details():
    """Priorities (lower first, without one last, the document's order among equals), only sha-256 of
    the hashes, unsafe names and files without a URL left out, other namespaces refused."""
    sha = "AB" * 32
    body = _metalink([("a.tif", sha, [("https://m3/a", None), ("https://m2/a", 2), ("https://m1/a", 1),
                                      ("https://m2b/a", 2)], 10),
                      ("../b.tif", None, [("https://m1/b", None)], None),
                      ("/c.tif", None, [("https://m1/c", None)], None),
                      ("C:/d.tif", None, [("https://m1/d", None)], None),
                      ("dir/e.tif", None, [("https://m1/e", None)], None),
                      ("f.tif", None, [], None)])
    published, files = parse_metalink(body)
    assert published == "2026-11-02T00:00:00Z"
    assert [f.name for f in files] == ["a.tif", "dir/e.tif"]
    assert files[0].urls == ("https://m1/a", "https://m2/a", "https://m2b/a", "https://m3/a")
    assert files[0].sha256 == "ab" * 32 and files[0].size == 10
    assert files[1].sha256 is None and files[1].size is None
    with pytest.raises(ValueError, match="Metalink 4"):
        parse_metalink(_metalink([("a.tif", None, [("https://m1/a", None)], None)], ns="http://www.metalinker.org/"))
    for body in (_body("005-bavaria-404.html"), _body("006-rlp-404.html"), b"", b"<metalink/>"):
        with pytest.raises(ValueError):
            parse_metalink(body)


# --- the listing ---

def _rp_layer(server, path="/rp/dgm1_tif_07.meta4", **kwargs) -> MetalinkTiles:
    return MetalinkTiles("DGM1 (test)", [server.url(path)], RP_DGM, "test_rp/dgm1", "EPSG:25832", "dgm1",
                         force_crs="EPSG:25832", **kwargs)


def test_listing_asks_once_per_ttl(http_server, tmp_path):
    """The statewide document is asked once and kept: every 0.25° tile is picked from it, also by
    another process (a new layer); an update asks again once."""
    http_server.add("/rp/dgm1_tif_07.meta4", _body("003-rlp-dgm1.meta4"), "application/metalink4+xml")
    cache_dir = str(tmp_path / "cache")
    layer = _rp_layer(http_server)
    sheets = layer.index.answers(cache_dir, 49.0, 7.75)
    assert len(sheets) == 20 and len(http_server.requests("/rp/")) == 1
    first = next(s for s in sheets if s["godlo"] == "412_5447")
    assert first == {"year": 2022, "godlo": "412_5447",
                     "url": "https://geobasis-rlp.de/data/dgm1/current/tif/dgm1_32_412_5447_1_rp_2022.tif",
                     "crs": "EPSG:25832", "res": 1.0, "sha256": first["sha256"], "size": first["size"],
                     "extent": [412000, 5447000, 413000, 5448000]}
    kept = os.path.join(cache_dir, "test_rp", "metalink", "dgm1.json.gz")
    with gzip.open(kept, "rt", encoding="utf-8") as f:
        assert len(json.load(f)["files"]) == 20  # the .tfw left out
    assert layer.index.answers(cache_dir, 49.25, 7.75) == []  # another tile: from the kept files
    assert _rp_layer(http_server).index.answers(cache_dir, 49.0, 8.0) == []
    assert len(http_server.requests("/rp/")) == 1
    again = _rp_layer(http_server)
    assert again.update_index_tile(cache_dir, 49.0, 7.75) == (0, 0, 0)  # nothing cached: nothing to download
    again.update_index_tile(cache_dir, 49.25, 7.75)
    assert len(http_server.requests("/rp/")) == 2
    assert cache.state(cache_dir, kept) == "ok"
    other = str(tmp_path / "other")  # another data folder (the probe's temporary one): its own documents
    assert len(again.index.answers(other, 49.0, 7.75)) == 20 and len(http_server.requests("/rp/")) == 3


@pytest.mark.parametrize("status, body", [(404, "006-rlp-404.html"), (200, "006-rlp-404.html"),
                                          (500, "005-bavaria-404.html")])
def test_listing_error_answers(http_server, tmp_path, capsys, status, body):
    """A document that cannot be had is IndexUnavailable: nothing kept, no tile's answer written, and a
    search uses the cached files."""
    http_server.add("/rp/dgm1_tif_07.meta4", _body(body), "text/html", status=status)
    cache_dir = str(tmp_path / "cache")
    layer = _rp_layer(http_server)
    with pytest.raises(IndexUnavailable):
        layer.index.answers(cache_dir, 49.0, 7.75)
    assert not os.path.exists(layer.index.listing.table_path(cache_dir))
    assert not os.path.exists(layer.index_path(cache_dir, 49.0, 7.75))
    grid = make_grid((412000, 5447000, 413000, 5448000), 1.0, "EPSG:25832")
    layer._use(cache_dir)
    assert layer.tiles(grid) is None and "index not available" in capsys.readouterr().out
    assert layer.to_download(grid, cache_dir, None) == ([], None)


def test_several_documents(http_server, tmp_path):
    """Bavaria's DOM20 is listed per Regierungsbezirk: overlapping documents give each file once."""
    http_server.add("/by/091.meta4", _body("002-bavaria-dom20.meta4"), "application/metalink4+xml")
    http_server.add("/by/094.meta4", _body("002-bavaria-dom20.meta4"), "application/metalink4+xml")
    listing = MetalinkFiles([http_server.url("/by/091.meta4"), http_server.url("/by/094.meta4")], BY_DOM,
                            "EPSG:25832", 1.0, "test_by", "dom20")
    listing.cache_dir = str(tmp_path)
    table = listing.table()
    assert len(table) == 82 and len({t["godlo"] for t in table}) == 82
    assert all(t["year"] == 0 and t["url"].startswith("https://download1.bayernwolke.de/a/dom20/DOM/32")
               for t in table)


# --- files known by their SHA-256 ---

TILE_M = 2.0  # a made-up tiling of 2 m, so the files stay 10 x 10 px at 0.2 m
EAST, NORTH = 206000, 2723500  # (412000, 5447000) m, near Dahn


def _raster(values: np.ndarray, res: float, left: float, top: float, crs="EPSG:25832", nodata=-9999.0) -> bytes:
    with rio.io.MemoryFile() as memfile:
        with memfile.open(driver="GTiff", width=values.shape[1], height=values.shape[0], count=1, dtype="float32",
                          crs=crs, transform=from_origin(left, top, res, res), nodata=nodata) as dst:
            dst.write(values.astype(np.float32), 1)
        return memfile.read()


def _file(seed: int) -> bytes:
    rng = np.random.default_rng(seed)
    values = rng.uniform(300, 400, (10, 10))
    values[0, :3] = -9999.0  # no data in one block's corner
    values[5:, 5:] = -9999.0  # and a whole block
    return _raster(values, 0.2, EAST * TILE_M, (NORTH + 1) * TILE_M)


def _sha_layer(server, files) -> MetalinkTiles:
    """A layer of one 2 m tile at 0.2 m averaged to 1 m, over a document listing files (name, body)."""
    entries = []
    for name, body in files:
        server.add(f"/files/{name}", body, "image/tiff")
        entries.append((name, hashlib.sha256(body).hexdigest(), [(server.url(f"/files/{name}"), None)], len(body)))
    server.add("/sha/all.meta4", _metalink(entries), "application/metalink4+xml")
    return MetalinkTiles("DOM (test)", [server.url("/sha/all.meta4")], r"^(?P<east>\d+)_(?P<north>\d+)(_(?P<year>\d{4}))?\.tif$",
                         "test_sha/dom", "EPSG:25832", "dom", tile_m=TILE_M, average=5)


def test_versions_by_checksum(http_server, tmp_path):
    """A file is cached under its SHA-256; a changed file (a new checksum in the document) is read
    again by an update and the older one deleted; the newest listed year of a place wins."""
    cache_dir = str(tmp_path / "cache")
    old = _file(1)
    layer = _sha_layer(http_server, [(f"{EAST}_{NORTH}.tif", old)])
    grid = make_grid((EAST * TILE_M, NORTH * TILE_M, (EAST + 1) * TILE_M, (NORTH + 1) * TILE_M), 1.0, "EPSG:25832")
    layer._use(cache_dir)
    tile, = layer.tiles(grid)
    assert tile.year == 0 and tile.key == hashlib.sha256(old).hexdigest()[:8]
    path = layer.tile_path(cache_dir, tile)
    assert os.path.relpath(path, cache_dir).replace(os.sep, "/") == \
        f"test_sha/dom/{EAST // 10}_{NORTH // 10}/{EAST}_{NORTH}_{tile.key}.tif"
    assert layer.estimate(grid, cache_dir, None) == (1, 1, len(old) / 1e6)
    layer.download(grid, cache_dir, None, "terrain")
    assert os.path.exists(path) and layer.missing(grid, cache_dir, None) == []
    with rio.open(path) as cached:
        assert cached.res == (1.0, 1.0) and cached.shape == (2, 2) and cached.crs == CRS.from_epsg(25832)
        values = cached.read(1)
    with rio.io.MemoryFile(old) as memfile, memfile.open() as source:
        expected = source.read(1, out_shape=(2, 2), resampling=Resampling.average, masked=True).filled(np.nan)
    assert np.isnan(values[1, 1]) and np.allclose(values, expected, equal_nan=True, atol=1e-4)
    assert layer.used(grid, cache_dir)["survey_years"] is None

    new = _file(2)  # replaced in place: the same name, another checksum
    fresh = _sha_layer(http_server, [(f"{EAST}_{NORTH}.tif", new)])
    lat, lon = 49.0, 7.75
    received = fresh.update_index_tile(cache_dir, lat, lon)
    assert received[0] == 1 and received[2] == 1
    assert not os.path.exists(path)
    fresh._use(cache_dir)
    newest, = fresh.tiles(grid)
    assert newest.key == hashlib.sha256(new).hexdigest()[:8] and os.path.exists(fresh.tile_path(cache_dir, newest))
    assert fresh.update_index_tile(cache_dir, lat, lon)[0] == 0  # nothing changed since

    # Offline: the cached files over the grid
    assert ShaPerTile("test_sha/dom", "EPSG:25832", TILE_M).cached(grid, cache_dir) == [
        type(newest)(EAST, NORTH, 0, newest.key)]


def test_newest_year_per_place(http_server, tmp_path):
    cache_dir = str(tmp_path / "cache")
    layer = _sha_layer(http_server, [(f"{EAST}_{NORTH}_2022.tif", _file(1)), (f"{EAST}_{NORTH}_2025.tif", _file(2)),
                                     (f"{EAST + 1}_{NORTH}_2023.tif", _file(3))])
    grid = make_grid((EAST * TILE_M, NORTH * TILE_M, (EAST + 2) * TILE_M, (NORTH + 1) * TILE_M), 1.0, "EPSG:25832")
    layer._use(cache_dir)
    tiles = layer.tiles(grid)
    assert [(t.east, t.year) for t in tiles] == [(EAST, 2025), (EAST + 1, 2023)]
    assert layer.source_date(tiles[0]) == "2025"
    assert os.path.basename(layer.tile_path(cache_dir, tiles[0])) == f"{EAST}_{NORTH}_2025_{tiles[0].key}.tif"
    (lon,), (lat,) = rio.warp.transform("EPSG:25832", "EPSG:4326", [EAST * TILE_M + 1], [NORTH * TILE_M + 1])
    assert layer.has_data_near(lat, lon, cache_dir) is True
    assert layer.has_data_near(lat + 0.1, lon, cache_dir) is False


# --- Download: averaging and a forced CRS ---

def test_block_means_as_gdal():
    rng = np.random.default_rng(7)
    values = rng.uniform(-10, 3000, (40, 30))
    values[rng.random(values.shape) < 0.3] = np.nan
    values[:5, :5] = np.nan
    ours = _block_means(values.copy(), 5)
    with rio.io.MemoryFile(_raster(np.nan_to_num(values, nan=-9999.0), 0.2, 0, 8)) as memfile, memfile.open() as src:
        gdal = src.read(1, out_shape=(8, 6), resampling=Resampling.average, masked=True).filled(np.nan)
    assert np.isnan(ours[0, 0]) and np.allclose(ours, gdal, equal_nan=True, atol=1e-3)


class _Tile:
    url, label, sha = "", "t", None


def test_download_rewrites(http_server, tmp_path, monkeypatch):
    """average: a file that cannot be averaged is an error; crs: the file written in that CRS's name
    (a compound CRS of heights), values as they are; a wrong checksum is never kept."""
    tile = _Tile()
    values = np.arange(36, dtype=np.float32).reshape(6, 6) + 100
    values[0, 0] = -9999.0
    http_server.add("/f/odd.tif", _raster(values, 0.2, 0, 1.2), "image/tiff")
    compound = CRS.from_wkt(CRS.from_user_input("EPSG:25832+7837").to_wkt())
    http_server.add("/f/compound.tif", _raster(values, 1.0, 412000, 5448000, crs=compound), "image/tiff")
    reader = Download("test", lambda t: t.url, lambda t: t.label, binary_types=("tiff",), average=5)
    tile.url = http_server.url("/f/odd.tif")
    with pytest.raises(RuntimeError, match="cannot be averaged 5 x 5"):
        reader.fetch(tile, str(tmp_path / "odd.tif"))
    assert not os.path.exists(tmp_path / "odd.tif")
    forced = Download("test", lambda t: t.url, lambda t: t.label, binary_types=("tiff",), crs="EPSG:25832")
    tile.url = http_server.url("/f/compound.tif")
    forced.fetch(tile, str(tmp_path / "forced.tif"))
    with rio.open(tmp_path / "forced.tif") as written:
        assert written.crs == CRS.from_epsg(25832) and written.res == (1.0, 1.0)
        assert written.transform.c == 412000 and written.transform.f == 5448000
        band = written.read(1)
    assert np.isnan(band[0, 0]) and np.array_equal(band[1:], values[1:])
    checked = Download("test", lambda t: t.url, lambda t: t.label, binary_types=("tiff",),
                       sha256=lambda t: "0" * 64, crs="EPSG:25832")
    monkeypatch.setattr(src.net, "_sleep", lambda attempt: None)
    with pytest.raises(RuntimeError, match="wrong checksum"):
        checked.fetch(tile, str(tmp_path / "wrong.tif"))
    assert not os.path.exists(tmp_path / "wrong.tif")
    with pytest.raises(ValueError):
        Download("test", lambda t: t.url, lambda t: t.label, average=0)
