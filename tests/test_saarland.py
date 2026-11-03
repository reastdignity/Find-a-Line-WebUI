"""Saarland: members of remote ZIP archives read by HTTP Range (sources/indexes/zipdir.py, sources/readers/
zipmember.py, sources/layers/zipmembers.py) against archives made here with zipfile (the oracle) and LVGL's
recorded directory, the 0 m artifact rule, and the catalogue's source (offline: tests/http_server.py)."""

import glob
import gzip
import io
import json
import os
import re
import zipfile
import zlib

import numpy as np
import pytest
import rasterio as rio
import requests
from rasterio.transform import from_origin

import cache
import sources as src
from grid import make_grid
from http_server import Answer
from sources import net
from sources.catalogue import germany
from sources.indexes.cached import IndexUnavailable
from sources.indexes import zipdir
from sources.indexes.zipdir import ZipDirectories, ZipPerTile, ZipTile, read_directory, share_token
from sources.layers.zipmembers import ZipMemberTiles
from sources.readers import zipmember
from sources.readers.zipmember import RangeRefused, ZipMember, drop_below, ranged

HERE = os.path.dirname(os.path.abspath(__file__))
RECORDED = os.path.join(HERE, "data", "recorded", "zipdir")
NAME = r"(?i)(?:^|/)dgm1_32_(?P<east>\d+)_(?P<north>\d+)_1_sl_(?P<year>\d{4})\.tif$"
TILE_M = 10.0  # a made-up tiling of 10 m, so the members stay 10 x 10 px
EAST, NORTH = 32700, 548500  # (327000, 5485000) m, near Mettlach


@pytest.fixture
def no_sleep(monkeypatch):
    monkeypatch.setattr(net, "_sleep", lambda attempt: None)


def _tif(east: int, north: int, base: float = 200.0, seed: int = 0) -> bytes:
    """A 10 x 10 px GeoTIFF of tile (east, north) at 1 m: heights about base, uncompressed float32 as LVGL's."""
    rng = np.random.default_rng(seed)
    values = (base + rng.uniform(0, 5, (10, 10))).astype(np.float32)
    with rio.io.MemoryFile() as memfile:
        with memfile.open(driver="GTiff", width=10, height=10, count=1, dtype="float32", crs="EPSG:25832",
                          transform=from_origin(east * TILE_M, (north + 1) * TILE_M, 1.0, 1.0),
                          nodata=-9999.0) as dst:
            dst.write(values, 1)
        return memfile.read()


def _archive(members, comment: bytes = b"", zip64: bool = False) -> bytes:
    """A ZIP of members (name, body, method, force_zip64); zip64: the central directory and end record written
    with ZIP64 fields (zipfile's limit lowered while it writes them)."""
    out = io.BytesIO()
    zf = zipfile.ZipFile(out, "w")
    for name, body, method, force in members:
        info = zipfile.ZipInfo(name, (2026, 1, 16, 12, 0, 0))
        info.compress_type = method
        with zf.open(info, "w", force_zip64=force) as member:
            member.write(body)
    zf.comment = comment
    limit = zipfile.ZIP64_LIMIT
    if zip64:
        zipfile.ZIP64_LIMIT = 0
    try:
        zf.close()
    finally:
        zipfile.ZIP64_LIMIT = limit
    return out.getvalue()


def _serve(server, path: str, body: bytes, etag: str = '"a1"'):
    server.add(path, body, "application/zip", headers={"ETag": etag})


# --- the ZIP format (APPNOTE.TXT 6.3.10) against zipfile ---

@pytest.mark.parametrize("comment, zip64", [(b"", False), (b"a comment " * 50, False), (b"", True)])
def test_directory_as_zipfile_reads_it(http_server, comment, zip64):
    """The central directory read by Range from the end gives zipfile's names, methods, CRC-32s, sizes and
    offsets: stored and deflated members, one written with ZIP64 local fields, names in other folders and case,
    an archive comment, and ZIP64 end records and extra fields (4.3.14, 4.3.15, 4.5.3)."""
    members = [("DGM1_tif_MZG/dgm1_32_32700_548500_1_SL_2025.tif", _tif(EAST, NORTH), zipfile.ZIP_DEFLATED, False),
               ("other/DGM1_32_32701_548500_1_sl_2025.TIF", _tif(EAST + 1, NORTH, seed=1), zipfile.ZIP_STORED, False),
               ("dgm1_32_32700_548501_1_SL_2025.tif", _tif(EAST, NORTH + 1, seed=2), zipfile.ZIP_DEFLATED, True),
               ("readme.txt", b"not a tile", zipfile.ZIP_DEFLATED, False)]
    body = _archive(members, comment, zip64)
    _serve(http_server, "/a.zip", body)
    listed = read_directory(http_server.url("/a.zip"), len(body))
    with zipfile.ZipFile(io.BytesIO(body)) as zf:
        expected = [(i.filename, i.compress_type, i.flag_bits, i.CRC, i.compress_size, i.file_size, i.header_offset)
                    for i in zf.infolist()]
    assert [tuple(m) for m in listed] == expected
    ranges = [r.headers["range"] for r in http_server.requests("/a.zip")]
    assert len(ranges) == 1  # the tail holds the end record and the directory of a small archive
    assert "bytes=0-0" not in ranges


def test_directory_in_a_large_archive(http_server):
    """The tail is the last 64 KiB + 22 B; the directory before it is a second Range."""
    filler = os.urandom(200_000)
    body = _archive([("dgm1_32_32700_548500_1_sl_2025.tif", _tif(EAST, NORTH), zipfile.ZIP_DEFLATED, False),
                     ("filler.bin", filler, zipfile.ZIP_STORED, False),
                     ("dgm1_32_32701_548500_1_sl_2025.tif", _tif(EAST + 1, NORTH), zipfile.ZIP_DEFLATED, False)])
    # the directory moved before the tail: a big comment
    body = body[:-2] + (0xFFFF).to_bytes(2, "little") + b"x" * 0xFFFF
    _serve(http_server, "/big.zip", body)
    listed = read_directory(http_server.url("/big.zip"), len(body))
    assert [m.name for m in listed] == ["dgm1_32_32700_548500_1_sl_2025.tif", "filler.bin",
                                        "dgm1_32_32701_548500_1_sl_2025.tif"]
    ranges = [r.headers["range"] for r in http_server.requests("/big.zip")]
    assert ranges[0] == f"bytes={len(body) - zipdir.TAIL_MAX}-{len(body) - 1}" and len(ranges) == 2


def test_not_a_zip_and_a_huge_directory(http_server, monkeypatch):
    _serve(http_server, "/no.zip", b"<html>no archive here</html>" * 10)
    with pytest.raises(ValueError, match="no end of central directory"):
        read_directory(http_server.url("/no.zip"), 280)
    body = _archive([("a.tif", b"x" * 100, zipfile.ZIP_STORED, False)])
    _serve(http_server, "/a.zip", body)
    monkeypatch.setattr(zipdir, "DIRECTORY_MAX", 10)
    with pytest.raises(ValueError, match="at most 10"):
        read_directory(http_server.url("/a.zip"), len(body))


def test_range_answers(http_server, no_sleep):
    """A 206 with the asked Content-Range only: a 200 (the whole file) is refused and closed unread, a range of
    one byte is never asked, a 404 says the archive moved."""
    body = os.urandom(1000)
    _serve(http_server, "/f.bin", body)
    data, total, _ = ranged(http_server.url("/f.bin"), 100, 199)
    assert data == body[100:200] and total == 1000
    with pytest.raises(ValueError):
        ranged(http_server.url("/f.bin"), 0, 0)
    http_server.route("/whole.bin", lambda request: Answer(200, os.urandom(2_000_000),
                                                           {"Content-Type": "application/zip"}, ranges=False))
    with pytest.raises(RangeRefused, match="whole file"):
        ranged(http_server.url("/whole.bin"), 0, 99)
    with pytest.raises(zipmember.ArchiveChanged, match="404"):
        ranged(http_server.url("/gone.bin"), 0, 99)
    http_server.fault("/f.bin", "truncate", lambda n, r: True)
    with pytest.raises((requests.RequestException, RuntimeError)):
        ranged(http_server.url("/f.bin"), 0, 999)


# --- the reader ---

def _tile(server, path: str, body: bytes, name: str, east: int = EAST, north: int = NORTH) -> ZipTile:
    with zipfile.ZipFile(io.BytesIO(body)) as zf:
        info = zf.getinfo(name)
    return ZipTile(east, north, 2025, f"{info.CRC:08x}", server.url(path), None, info.compress_size, name,
                   info.header_offset, info.compress_type, info.flag_bits, info.CRC, info.file_size, len(body))


@pytest.mark.parametrize("method, force, slack", [(zipfile.ZIP_DEFLATED, False, 1024), (zipfile.ZIP_STORED, False, 1024),
                                                  (zipfile.ZIP_DEFLATED, True, 1024), (zipfile.ZIP_DEFLATED, True, 0)])
def test_member_read_as_zipfile_reads_it(http_server, tmp_path, monkeypatch, method, force, slack):
    """The member's bytes are zipfile's; a local header longer than the central one (a ZIP64 extra field)
    beyond HEADER_SLACK takes a second, small Range; the tile is written as float32 GeoTIFF."""
    monkeypatch.setattr(zipmember, "HEADER_SLACK", slack)
    name = "Folder/dgm1_32_32700_548500_1_SL_2025.tif"
    first = _tif(EAST, NORTH)
    body = _archive([("x.txt", b"before" * 100, zipfile.ZIP_DEFLATED, False), (name, first, method, force)])
    _serve(http_server, "/m.zip", body)
    tile = _tile(http_server, "/m.zip", body, name)
    reader = ZipMember("DGM1 (test)")
    assert reader._member(tile, "t")[0] == zipfile.ZipFile(io.BytesIO(body)).read(name)
    path = str(tmp_path / "t.tif")
    fetched = reader.fetch(tile, path)
    assert fetched.received >= tile.size and fetched.url == tile.url
    with rio.open(path) as written, rio.io.MemoryFile(first) as memfile, memfile.open() as original:
        assert written.dtypes[0] == "float32" and written.transform == original.transform
        assert np.array_equal(written.read(1), original.read(1))
    ranges = len(http_server.requests("/m.zip"))
    assert ranges == (4 if force and not slack else 2)  # two fetches, one Range each (or two with a short first)


def test_crc_mismatch_never_cached(http_server, tmp_path, no_sleep):
    name = "dgm1_32_32700_548500_1_sl_2025.tif"
    body = bytearray(_archive([(name, _tif(EAST, NORTH), zipfile.ZIP_STORED, False)]))
    tile = _tile(http_server, "/c.zip", bytes(body), name)
    body[tile.offset + 30 + len(name) + 50] ^= 0xFF  # a flipped byte in the stored data
    _serve(http_server, "/c.zip", bytes(body))
    path = str(tmp_path / "t.tif")
    with pytest.raises(RuntimeError, match="CRC-32"):
        ZipMember("DGM1 (test)").fetch(tile, path)
    assert len(http_server.requests("/c.zip")) == net.RETRIES and not os.path.exists(path)


def test_cut_short_answer_asked_again(http_server, tmp_path, no_sleep):
    name = "dgm1_32_32700_548500_1_sl_2025.tif"
    body = _archive([(name, _tif(EAST, NORTH), zipfile.ZIP_DEFLATED, False)])
    _serve(http_server, "/t.zip", body)
    http_server.fault("/t.zip", "truncate", lambda n, r: n == 1)
    path = str(tmp_path / "t.tif")
    ZipMember("DGM1 (test)").fetch(_tile(http_server, "/t.zip", body, name), path)
    assert os.path.exists(path) and len(http_server.requests("/t.zip")) == 2


def test_methods_and_whole_answers_refused(http_server, tmp_path, no_sleep):
    name = "dgm1_32_32700_548500_1_sl_2025.tif"
    body = _archive([(name, _tif(EAST, NORTH), zipfile.ZIP_BZIP2, False)])
    _serve(http_server, "/b.zip", body)
    with pytest.raises(RuntimeError, match="compression method 12"):
        ZipMember("DGM1 (test)").fetch(_tile(http_server, "/b.zip", body, name), str(tmp_path / "t.tif"))
    body = _archive([(name, _tif(EAST, NORTH), zipfile.ZIP_DEFLATED, False)])
    tile = _tile(http_server, "/whole.zip", body, name)
    http_server.route("/whole.zip", lambda request: Answer(200, body, {"Content-Type": "application/zip"},
                                                           ranges=False))
    with pytest.raises(RangeRefused):
        ZipMember("DGM1 (test)").fetch(tile, str(tmp_path / "t.tif"))
    assert len(http_server.requests("/whole.zip")) == 1 and not os.path.exists(tmp_path / "t.tif")


# --- the 0 m artifact rule ---

def test_drop_below_the_floor():
    """Pixels below the floor and the 2 px around them become no data (a 5 x 5 dilation); the ground beyond,
    NaN already and a patch at the tile's edge (its ring cut by the edge) as expected."""
    band = np.full((20, 20), 205.0, dtype=np.float32)
    band[8:11, 8:10] = 0.0         # the patch
    band[7, 8:10] = 120.0          # its rim falling to it
    band[0, 18:20] = -0.26         # a patch at the edge
    band[15, 2] = np.nan
    out = drop_below(band.copy(), 100.0, 2)
    expected = np.zeros((20, 20), dtype=bool)
    expected[6:13, 6:12] = True
    expected[0:3, 16:20] = True
    expected[15, 2] = True
    assert np.array_equal(np.isnan(out), expected)
    assert (out[~expected] == 205.0).all()
    assert np.array_equal(drop_below(band.copy(), None), band, equal_nan=True)
    rim_only = drop_below(band.copy(), 100.0, 0)
    assert np.isnan(rim_only[8:11, 8:10]).all() and rim_only[7, 8] == 120.0  # without a ring the rim stays


def test_rule_applied_when_written(http_server, tmp_path):
    name = "dgm1_32_32700_548500_1_sl_2025.tif"
    values = np.full((10, 10), 205.0, dtype=np.float32)
    values[4:6, 4:6] = 0.0
    with rio.io.MemoryFile() as memfile:
        with memfile.open(driver="GTiff", width=10, height=10, count=1, dtype="float32", crs="EPSG:25832",
                          transform=from_origin(EAST * TILE_M, (NORTH + 1) * TILE_M, 1, 1), nodata=-9999) as dst:
            dst.write(values, 1)
        tif = memfile.read()
    body = _archive([(name, tif, zipfile.ZIP_DEFLATED, False)])
    _serve(http_server, "/r.zip", body)
    path = str(tmp_path / "t.tif")
    ZipMember("DGM1 (test)", floor=100.0, ring=2).fetch(_tile(http_server, "/r.zip", body, name), path)
    with rio.open(path) as written:
        z = written.read(1)
    assert np.isnan(z[2:8, 2:8]).all() and int(np.isnan(z).sum()) == 36 and np.nanmin(z) == 205.0


# --- the layer: directories kept per TTL, the share's token, versions ---

def _share(server, token: str):
    server.route("/cloud/share", lambda request: Answer(302, b"", {"Location": f"http://example.test/cloud/index.php/s/{token}"}))


def _layer(server, archives=("A", "B"), **kwargs) -> ZipMemberTiles:
    urls = [server.url(f"/dav/{{token}}/{a}.zip") for a in archives]
    return ZipMemberTiles("DGM1 (test)", urls, NAME, "test_sl/dgm1", "EPSG:25832", "dgm1",
                          share=server.url("/cloud/share"), tile_m=TILE_M, **kwargs)


def _two_archives(server, token: str, b_tile: bytes = None, etag: str = '"a1"'):
    """Archive A with tiles (EAST, NORTH) and (EAST + 1, NORTH); archive B with (EAST + 1, NORTH) again (its own
    content, b_tile) and (EAST, NORTH + 1)."""
    a = _archive([("DGM1_tif_A/dgm1_32_32700_548500_1_SL_2025.tif", _tif(EAST, NORTH), zipfile.ZIP_DEFLATED, False),
                  ("DGM1_tif_A/dgm1_32_32701_548500_1_SL_2025.tif", _tif(EAST + 1, NORTH, seed=1),
                   zipfile.ZIP_DEFLATED, False)])
    b = _archive([("DGM1_tif_B/dgm1_32_32701_548500_1_SL_2025.tif", b_tile or _tif(EAST + 1, NORTH, seed=1),
                   zipfile.ZIP_DEFLATED, False),
                  ("DGM1_tif_B/dgm1_32_32700_548501_1_SL_2025.tif", _tif(EAST, NORTH + 1, seed=2),
                   zipfile.ZIP_DEFLATED, False)])
    _serve(server, f"/dav/{token}/A.zip", a, etag)
    _serve(server, f"/dav/{token}/B.zip", b, etag)
    return a, b


def _grid(tiles_east: int = 2, tiles_north: int = 2):
    return make_grid((EAST * TILE_M, NORTH * TILE_M, (EAST + tiles_east) * TILE_M, (NORTH + tiles_north) * TILE_M),
                     1.0, "EPSG:25832")


def test_layer_downloads_and_keeps_the_directories(http_server, tmp_path):
    """The token from the share's redirect, a HEAD and the tail of each archive, kept in <top>/zipdir/; a tile in
    two archives from the first; the members cached under their CRC-32; the 0.25° answers made from the kept
    directories, also by another process."""
    _share(http_server, "TOKEN1a")
    a, b = _two_archives(http_server, "TOKEN1a", b_tile=_tif(EAST + 1, NORTH, base=500.0))
    cache_dir = str(tmp_path / "cache")
    layer = _layer(http_server)
    layer._use(cache_dir)
    grid = _grid()
    tiles = layer.tiles(grid)
    assert sorted((t.east, t.north) for t in tiles) == [(EAST, NORTH), (EAST, NORTH + 1), (EAST + 1, NORTH)]
    second = next(t for t in tiles if t.east == EAST + 1)
    with zipfile.ZipFile(io.BytesIO(a)) as zf:
        assert second.url.endswith("/dav/TOKEN1a/A.zip")  # the first archive wins
        assert second.key == f"{zf.getinfo('DGM1_tif_A/dgm1_32_32701_548500_1_SL_2025.tif').CRC:08x}"
    kept = os.path.join(cache_dir, "test_sl", "zipdir", "dgm1.json.gz")
    with gzip.open(kept, "rt", encoding="utf-8") as f:
        table = json.load(f)
    assert table["token"] == "TOKEN1a" and [x["etag"] for x in table["archives"]] == ['"a1"', '"a1"']
    assert layer.estimate(grid, cache_dir, None)[:2] == (3, 3)
    layer.download(grid, cache_dir, None, "terrain")
    assert layer.missing(grid, cache_dir, None) == []
    path = layer.tile_path(cache_dir, second)
    assert os.path.relpath(path, cache_dir).replace(os.sep, "/") == \
        f"test_sl/dgm1/{(EAST + 1) // 10}_{NORTH // 10}/{EAST + 1}_{NORTH}_2025_{second.key}.tif"
    with rio.open(path) as cached:
        assert cached.read(1).max() < 300  # A's tile, not B's
    asked = len(http_server.requests())
    again = _layer(http_server)  # another process: the kept directories, nothing asked
    again._use(cache_dir)
    assert len(again.tiles(grid)) == 3 and len(http_server.requests()) == asked
    assert again.used(grid, cache_dir)["survey_years"] == [2025, 2025]


def test_changed_etag_reads_the_directory_again(http_server, tmp_path):
    """Read again (TTL or update), an archive whose ETag and length are unchanged keeps its directory; one with
    another ETag is read again, and a changed member is a new version."""
    _share(http_server, "TOKEN1a")
    _two_archives(http_server, "TOKEN1a")
    cache_dir = str(tmp_path / "cache")
    layer = _layer(http_server)
    layer.listing.cache_dir = cache_dir
    layer.listing.table()
    assert len(http_server.requests("/dav/TOKEN1a/A.zip")) == 2  # HEAD, tail
    layer.listing.table(force=True)
    assert len(http_server.requests("/dav/TOKEN1a/A.zip")) == 3  # HEAD only
    new_b = _tif(EAST + 1, NORTH, base=300.0)
    b = _archive([("DGM1_tif_B/dgm1_32_32700_548501_1_SL_2025.tif", new_b, zipfile.ZIP_DEFLATED, False)])
    _serve(http_server, "/dav/TOKEN1a/B.zip", b, '"b2"')
    items = layer.listing.table(force=True)
    assert len(http_server.requests("/dav/TOKEN1a/A.zip")) == 4 and len(http_server.requests("/dav/TOKEN1a/B.zip")) == 5
    crc = zipfile.ZipFile(io.BytesIO(b)).getinfo("DGM1_tif_B/dgm1_32_32700_548501_1_SL_2025.tif").CRC
    assert next(i for i in items if i["godlo"] == f"{EAST}_{NORTH + 1}")["crc"] == crc


def test_404_resolves_the_token_again(http_server, tmp_path):
    """The share's token was reissued: a member's 404 reads the directories again (the new token from the
    share's redirect; unchanged archives keep their directories) and the member is read from there."""
    _share(http_server, "TOKEN1a")
    _two_archives(http_server, "TOKEN1a")
    cache_dir = str(tmp_path / "cache")
    layer = _layer(http_server)
    layer._use(cache_dir)
    grid = _grid(1, 1)
    (tile,) = layer.tiles(grid)
    http_server.answers.clear()
    http_server.routes.clear()
    _share(http_server, "TOKEN2b")
    _two_archives(http_server, "TOKEN2b")
    path = layer.tile_path(cache_dir, tile)
    layer.download_tile(tile, path)
    assert os.path.exists(path)
    assert len(http_server.requests("/cloud/share")) == 2
    assert [r.method for r in http_server.requests("/dav/TOKEN2b/A.zip")] == ["HEAD", "GET"]  # no tail read again
    assert not glob.glob(os.path.join(cache_dir, "test_sl", "sheet-index", "dgm1", "*.json"))
    with gzip.open(layer.listing.table_path(cache_dir), "rt", encoding="utf-8") as f:
        assert json.load(f)["token"] == "TOKEN2b"


def test_404_without_a_new_place_fails(http_server, tmp_path, no_sleep, capsys):
    _share(http_server, "TOKEN1a")
    _two_archives(http_server, "TOKEN1a")
    cache_dir = str(tmp_path / "cache")
    layer = _layer(http_server)
    layer._use(cache_dir)
    (tile,) = layer.tiles(_grid(1, 1))
    http_server.add("/dav/TOKEN1a/A.zip", b"", "text/html", status=404)  # gone, and the share names no other place
    with pytest.raises(RuntimeError, match="404"):
        layer.download_tile(tile, str(tmp_path / "t.tif"))
    assert "cannot be read again" in capsys.readouterr().out and not os.path.exists(tmp_path / "t.tif")


@pytest.mark.parametrize("answer", [Answer(404, b"", {"Content-Type": "text/html"}),
                                    Answer(200, b"<html>login</html>", {"Content-Type": "text/html"})])
def test_share_without_a_token(http_server, tmp_path, answer):
    """The share's link answers no redirect to a share: IndexUnavailable, nothing kept, the cached files used."""
    http_server.route("/cloud/share", lambda request: answer)
    with pytest.raises(IndexUnavailable, match="share"):
        share_token(http_server.url("/cloud/share"))
    layer = _layer(http_server)
    cache_dir = str(tmp_path / "cache")
    layer._use(cache_dir)
    assert layer.tiles(_grid()) is None
    assert not os.path.exists(layer.listing.table_path(cache_dir))


def test_missing_archive_is_index_unavailable(http_server, tmp_path):
    _share(http_server, "TOKEN1a")
    _two_archives(http_server, "TOKEN1a")
    layer = _layer(http_server, archives=("A", "B", "C"))
    layer.listing.cache_dir = str(tmp_path)
    with pytest.raises(IndexUnavailable, match="C.zip: HTTP 404"):
        layer.listing.table()


# --- LVGL's recorded directory ---

def _recorded():
    with open(os.path.join(RECORDED, "requests.json"), encoding="utf-8") as f:
        return json.load(f)


def test_recorded_directory(http_server, tmp_path):
    """The end and the central directory of LVGL's district archive (served at their offsets of the real
    archive, nothing else): 311 members (the folder and 310 tiles of 1 km), data descriptors (flag 8), deflated."""
    recorded = _recorded()
    length = recorded["length"]
    parts = []
    for entry in recorded["ranges"]:
        with gzip.open(os.path.join(RECORDED, entry["body"]), "rb") as f:
            parts.append((entry["first"], f.read()))

    def answer(request):
        first, last = (int(v) for v in request.headers["range"].split("=")[1].split("-"))
        for start, data in parts:
            if start <= first and last < start + len(data):
                return Answer(206, data[first - start:last - start + 1],
                              {"Content-Type": "application/zip", "Content-Range": f"bytes {first}-{last}/{length}"})
        return Answer(416, b"", {"Content-Type": "text/plain"})
    http_server.route("/dav/", answer)
    members = read_directory(http_server.url("/dav/archive.zip"), length)
    assert len(members) == recorded["members"]
    expected = recorded["expected"]
    first = next(m for m in members if m.name == expected["name"])
    assert list(first) == [expected[k] for k in ("name", "method", "flags", "crc", "size", "usize", "offset")]
    tiles = [m for m in members if re.search(NAME, m.name)]
    assert len(tiles) == recorded["tiles"]
    assert all(m.method == 8 for m in tiles)


# --- the catalogue ---

def test_source():
    sl = src.SOURCES["saarland"]
    assert sl.regions == ("de-sl",) and sl.countries == ("de",) and sl.crs == "EPSG:25832"
    assert sl.grid_origin == (0.0, 0.0) and sl.fallbacks == ["europe"]
    assert isinstance(sl.nmt, ZipMemberTiles) and isinstance(sl.nmpt, ZipMemberTiles)
    assert sl.nmt.folder == "saarland/dgm1-2025" and sl.nmpt.folder == "saarland/dom1-2025"
    assert sl.nmt.floor == sl.nmpt.floor == 100.0 and sl.nmt.ring == sl.nmpt.ring == 6
    assert sl.nmt.ttl_days is None and sl.nmt.listing.share == germany.SL_SHARE
    assert len(sl.nmt.metalinks) == len(sl.nmpt.metalinks) == 6
    assert sl.nmt.metalinks[0] == ("https://www.shop.lvgl.saarland.de/cloud/public.php/dav/files/{token}/"
                                   "OD_DGM1_2025_tif_LK/DGM1_tif_MZG_EPSG-25832_Entstehung-2025.zip")
    assert sl.nmpt.metalinks[5].endswith("/OD_DOM1_2025_tif_LK/DOM1_tif_WND_EPSG-25832_Entstehung-2025.zip")
    for name in ("DGM1_tif_MZG/dgm1_32_327_5485_1_SL_2025.tif", "x/DGM1_32_327_5485_1_sl_2025.TIF"):
        match = sl.nmt.listing.name.search(name)
        assert match and match.group("east", "north", "year") == ("327", "5485", "2025")
    assert not sl.nmt.listing.name.search("DOM1_tif_MZG/dom1_32_327_5485_1_SL_2025.tif")
    assert sl.nmpt.listing.name.search("DOM1_tif_MZG/dom1_32_327_5485_1_SL_2025.tif")
    assert src.HOST_SLOTS_OF["www.shop.lvgl.saarland.de"] == 2
    assert sl.ortho.url == "https://geoportal.saarland.de/freewms/dop" and sl.ortho.layer == "sl_dop"
    assert sl.neighbours == ("rhineland_palatinate", "france", "luxembourg")
    from sources import probe
    assert probe.strategy(sl.nmt) == "zip"
    ids = [s.id for s in germany.SOURCES]  # the catalogue's order of SOURCES itself: tests/test_catalogue.py
    assert ids.index("saarland") < ids.index("rhineland_palatinate")


@pytest.mark.parametrize("lat, lon, inside", [
    (49.2340, 6.9970, True),    # Saarbrücken
    (49.4950, 6.5970, True),    # Mettlach
    (49.4730, 6.3900, True),    # Perl, east of the Moselle
    (49.2052, 7.0163, True),    # the Felsenwege (R63)
    (49.7500, 6.6400, False),   # Trier
    (49.4400, 7.7700, False),   # Kaiserslautern
    (49.6100, 6.1300, False),   # Luxembourg city
    (49.1200, 6.1800, False),   # Metz
])
def test_offline_boxes(lat, lon, inside):
    """Offline, the first box holding a point wins: Saarland's before Rhineland-Palatinate's and Luxembourg's."""
    found = next((code for code, (s, n, w, e) in src.OFFLINE_BOXES if s <= lat <= n and w <= lon <= e), None)
    assert (found == "de-sl") == inside, found


def test_probe_reads_the_local_header(http_server, tmp_path):
    from sources import probe
    name = "DGM1_tif_A/dgm1_32_32700_548500_1_SL_2025.tif"
    body = _archive([("x.txt", b"x" * 300, zipfile.ZIP_STORED, False), (name, _tif(EAST, NORTH), 8, False)])
    _serve(http_server, "/p.zip", body)
    tile = _tile(http_server, "/p.zip", body, name)
    layer = _layer(http_server)
    assert probe._zip_header(str(tmp_path), layer, tile).startswith("member dgm1_32_32700_548500_1_SL_2025.tif")
    (request,) = http_server.requests("/p.zip")
    first, last = (int(v) for v in request.headers["range"].split("=")[1].split("-"))
    assert first == tile.offset and last - first < 200  # the header, never the data
    wrong = ZipTile(tile.east, tile.north, 2025, tile.key, tile.url, None, tile.size, name, 0, 8, 0, tile.crc,
                    tile.usize, tile.length)
    with pytest.raises(RuntimeError, match="not"):
        probe._zip_header(str(tmp_path), layer, wrong)
