"""Blocks of big remote files read with fewer bytes (docs/performance.md, "Window reads"), offline against
tests/http_server.py: in groups (sources.download_layers(group_m=), ComposedLayer._download_group, windows.read_group
over sources/readers/ranges.py: each file read once per group through range requests of our own, every answer taken
only whole) and range by range in squares (Windows(serial=True)); both cache the same files and index rows as block
by block."""

import os
import sqlite3
import sys

import numpy as np
import pytest
import rasterio as rio
import rasterio.cache
from rasterio.transform import from_origin

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cache  # noqa: E402
import grid as gd  # noqa: E402
import servicecounts  # noqa: E402
import sources as src  # noqa: E402
from sources.layers.fileblocks import FileBlocks  # noqa: E402
from sources.readers import ranges  # noqa: E402
from sources.readers.windows import BlockRequest, _read_block, read_group  # noqa: E402
from sources.layer import _write_tile  # noqa: E402

CRS = "EPSG:3035"
SIZE = 240   # pixels a side of a file (1 m), 16 px internal tiles; uncompressed: tiles beyond the first 64 KB
BLOCK = 20   # metres: blocks of 20 px over 16 px tiles, as Austria's 1000 px over 512
E0, N0 = 4400000, 2650000


def _file(path, left, top, band, crs=CRS, point=False):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with rio.open(path, "w", driver="GTiff", width=band.shape[1], height=band.shape[0], count=1, dtype="float32",
                  crs=crs, nodata=-9999.0, transform=from_origin(left, top, 1.0, 1.0), tiled=True,
                  blockxsize=16, blockysize=16) as dst:
        dst.write(np.where(np.isnan(band), -9999.0, band).astype(np.float32), 1)
        if point:
            dst.update_tags(AREA_OR_POINT="Point")


def _band(seed, holes=False):
    band = np.random.default_rng(seed).normal(800, 40, (SIZE, SIZE)).astype(np.float32)
    if holes:  # a newer survey with gaps: an older one fills them
        band[30:90, 50:130] = np.nan
        band[150:200, :] = np.nan
    return band


@pytest.fixture
def files(http_server, tmp_path):
    """Two files side by side (sharing a column, as Austria's), a newer one with holes over the first, a file in
    another CRS and one with PixelIsPoint, on the server."""
    folder = str(tmp_path / "files")
    _file(os.path.join(folder, "west.tif"), E0, N0 + SIZE, _band(1))
    _file(os.path.join(folder, "east.tif"), E0 + SIZE - 1, N0 + SIZE, _band(2))
    _file(os.path.join(folder, "newer.tif"), E0, N0 + SIZE, _band(3, holes=True))
    _file(os.path.join(folder, "other.tif"), E0, N0 + SIZE, _band(4), crs="EPSG:25833")
    _file(os.path.join(folder, "point.tif"), E0, N0 + SIZE, _band(5), point=True)
    http_server.add_folder("/files", folder)
    return http_server


def _layer(server, kind="grid", origin=(0.0, 0.0)):
    url = lambda name: server.url(f"/files/{name}")  # noqa: E731

    def files(i, j):
        x = i * BLOCK + origin[0]
        if kind == "grid":  # west, east, and beyond them a file the server does not have (404)
            name = "west.tif" if x < E0 + SIZE - 1 else "east.tif" if x < E0 + 2 * SIZE - 2 else "gone.tif"
            return [(name, url(name), 2025)]
        if kind == "newest first":
            return [("newer", url("newer.tif"), 2024), ("west", url("west.tif"), 2019)]
        return [(kind, url(f"{kind}.tif"), 2020)]
    return FileBlocks(f"Test {kind}", f"test/{kind.replace(' ', '-')}/1", CRS, 1.0, BLOCK, files, origin=origin,
                      bytes_per_tile=1e4)


def _grid(width_m=200, height_m=180, left=E0 + 4, bottom=N0 + 6):
    return gd.Grid(left=left + 0.5, top=bottom + height_m - 0.5, res=1.0, height=height_m - 1, width=width_m - 1,
                   crs=CRS)


def _cached(cache_dir, folder):
    """The cached files of a layer (path -> bytes) and the index rows of the top folder but their times."""
    root = os.path.join(cache_dir, folder)
    found = {}
    for dirpath, _, names in os.walk(root):
        for name in names:
            with open(os.path.join(dirpath, name), "rb") as f:
                found[os.path.relpath(os.path.join(dirpath, name), root)] = f.read()
    con = sqlite3.connect(os.path.join(cache_dir, folder.split("/")[0], "index.sqlite"))
    rows = sorted(con.execute("select path, status, url, etag, last_modified, source_date, processing from files"))
    con.close()
    return found, rows


def _download(server, cache_dir, kind, group_m=None, grid=None, origin=(0.0, 0.0)):
    """The layer downloaded into cache_dir, block by block or in groups: its files and index rows."""
    layer = _layer(server, kind, origin)
    src.download_layers([(layer, "terrain")], grid or _grid(), str(cache_dir), None, group_m=group_m)
    return _cached(str(cache_dir), layer.folder)


def _both(server, tmp_path, kind, group_m, grid=None, origin=(0.0, 0.0)):
    return [_download(server, tmp_path / f"cache-{mode}", kind, group, grid, origin)
            for mode, group in (("blocks", None), ("groups", group_m))]


@pytest.mark.parametrize("kind", ["grid", "newest first", "point"])
def test_groups_cache_what_blocks_cache(files, tmp_path, kind):
    """Byte for byte the same files and the same index rows (two files sharing a column and a third one missing,
    a newer file with holes an older one fills, PixelIsPoint), with groups of several sizes."""
    grid = _grid(560) if kind == "grid" else _grid()
    blocks, rows = _download(files, tmp_path / "blocks", kind, None, grid)
    for group_m in (40, 60, 1000):
        grouped, grouped_rows = _download(files, tmp_path / f"g{group_m}", kind, group_m, grid)
        assert grouped.keys() == blocks.keys() and all(grouped[k] == blocks[k] for k in blocks), group_m
        assert grouped_rows == rows
    if kind == "grid":
        assert any("gone" in (r[2] or "") and r[1] == "missing" for r in rows)  # the 404: missing in both
        assert any("east" in (r[2] or "") and r[1] == "ok" for r in rows)


@pytest.mark.parametrize("group_m", [None, 40, 1000])
def test_a_layer_in_another_crs_fails(files, tmp_path, group_m, capsys):
    """A layer whose only file is in another CRS than its blocks' fails, block by block and in groups alike (the
    group falls back to one block at a time, which fails), and caches nothing: before 2026-11-08 every block was
    recorded as "missing" after a printed line only (ArcticDEM over Jan Mayen: "0 of 1252 tiles" in silence)."""
    cache_dir = tmp_path / "cache"
    with pytest.raises(RuntimeError, match="other is in EPSG:25833, not EPSG:3035; no file of this block could be read"):
        _download(files, cache_dir, "other", group_m)
    assert not os.path.exists(cache_dir / "test" / "other")
    out = capsys.readouterr().out
    assert "Test other: other is in EPSG:25833, not EPSG:3035; not used" in out
    if group_m:
        assert "tiles one by one (Test other: other is in EPSG:25833, not EPSG:3035; no file of" in out


def test_blocks_off_the_files_pixels(files, tmp_path):
    """Blocks whose pixels are not the file's (resampled by _read_window) are cached as block by block."""
    (blocks, rows), (grouped, grouped_rows) = _both(files, tmp_path, "west", 60, origin=(0.25, 0.25))
    assert blocks and grouped == blocks and grouped_rows == rows


def test_each_file_once_per_group(files, tmp_path):
    """A group reads each of its files once: one request for the header's first bytes and one per run of tiles;
    the older file only where the newer one left holes."""
    layer = _layer(files, "newest first")
    grid = _grid(60, 60, left=E0 + 20, bottom=N0 + 60)
    cache_dir = str(tmp_path / "cache")
    src.download_layers([(layer, "terrain")], grid, cache_dir, None, group_m=1000)
    newer = [r for r in files.requests("/files/newer.tif") if r.headers.get("range")]
    assert newer[0].headers["range"] == f"bytes=0-{ranges.CHUNK - 1}"
    assert 1 < len(newer) <= 1 + 60 // 16 + 1 + 2  # the header, a run per row of tiles (+ the offsets' arrays)
    assert files.requests("/files/west.tif")  # the newer file has holes here


def test_geoid_as_block_by_block(files, tmp_path):
    """With a geoid, the group's blocks are h - N as _read_block's (N computed per block)."""
    class Geoid:
        name, tag = "Test geoid", "tg"

        def undulation(self, crs, transform, shape):
            return np.full(shape, 30.0 + transform.c % 7, dtype=np.float32)
    url = files.url("/files/west.tif")
    blocks = [BlockRequest([("west", url, 2020)], CRS, from_origin(E0 + 20 * k, N0 + 100, 1, 1), (20, 20))
              for k in range(4)]
    grouped = read_group(blocks, "test", Geoid())
    for k, (r, (values, tags)) in enumerate(zip(blocks, grouped)):
        one = str(tmp_path / f"one-{k}.tif")
        _read_block(r.files, r.crs, r.transform, r.shape, one, "test", Geoid())
        two = str(tmp_path / f"two-{k}.tif")
        _write_tile(two, values, r.crs, r.transform, tags=tags)
        assert tags["vertical"] == "Test geoid"
        assert open(one, "rb").read() == open(two, "rb").read()


def _tile_ranges(n, range_header):
    return not range_header.startswith("bytes=0-")


def test_answer_cut_short_is_asked_again(files, tmp_path, monkeypatch):
    """A tile run's answer cut short once is asked again: the same files as block by block."""
    monkeypatch.setattr(src.net, "_sleep", lambda attempt: None)
    (blocks, _), _ = _both(files, tmp_path / "ref", "grid", 60)
    cut = []
    files.fault("/files/west.tif", "truncate", lambda n, r: _tile_ranges(n, r) and not cut and not cut.append(r))
    layer = _layer(files)
    cache_dir = str(tmp_path / "cut")
    src.download_layers([(layer, "terrain")], _grid(), cache_dir, None, group_m=60)
    assert cut
    assert _cached(cache_dir, layer.folder)[0] == blocks


def test_answers_cut_short_every_time(files, tmp_path, monkeypatch, capsys):
    """Cut short every time: the group's blocks are tried one by one, which fail as ever (those whose tiles lie in
    GDAL's first read of the file are cached, as block by block); nothing cached holds other values."""
    monkeypatch.setattr(src.net, "_sleep", lambda attempt: None)
    reference, _ = _download(files, tmp_path / "ref", "grid", None, _grid(60, 60))
    files.fault("/files/west.tif", "truncate", _tile_ranges)
    layer = _layer(files)
    cache_dir = str(tmp_path / "cache")
    with pytest.raises(RuntimeError, match="Could not read"):
        src.download_layers([(layer, "terrain")], _grid(60, 60), cache_dir, None, group_m=60)
    assert "tiles one by one" in capsys.readouterr().out
    cached = {p: b for p, b in _cached(cache_dir, layer.folder)[0].items() if p.endswith(".tif")}
    assert len(cached) < len([p for p in reference if p.endswith(".tif")])
    assert all(reference[p] == b for p, b in cached.items())


def test_a_tile_cached_meanwhile_is_kept(files, tmp_path):
    """A tile another search cached while the group was read is not written again."""
    layer = _layer(files)
    grid = _grid(60, 60)
    cache_dir = str(tmp_path / "cache")
    tiles = layer.tiles(grid)
    layer._download_and_record(tiles[0], cache_dir)
    path = layer.tile_path(cache_dir, tiles[0])
    before = os.stat(path).st_mtime_ns
    received = layer._download_group(tiles, cache_dir)
    assert os.stat(path).st_mtime_ns == before
    assert all(os.path.exists(layer.tile_path(cache_dir, t)) for t in tiles)
    assert received == sum(os.path.getsize(layer.tile_path(cache_dir, t)) for t in tiles[1:])


def test_tiles_counted_per_block(files, tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(servicecounts, "enabled", lambda: True)
    monkeypatch.setattr(servicecounts, "tiles", lambda *a, **k: calls.append((a, k)))
    layer = _layer(files)
    grid = _grid(60, 60)
    src.download_layers([(layer, "terrain")], grid, str(tmp_path / "cache"), None, group_m=60)
    written = [a for a, k in calls if len(a) > 2 and a[2] == 1]
    assert len(written) == len(layer.tiles(grid))
    assert all(a[3] == 0 and a[4] == BLOCK * BLOCK and a[5] == pytest.approx(BLOCK * BLOCK / 1e6) for a in written)


def test_squares_by_the_blocks_centres(files):
    layer = _layer(files)
    tiles = layer.tiles(_grid(200, 180))
    squares = src.layer.squares(layer, tiles, 60)
    assert sorted(t for s in squares for t in s) == sorted(tiles)
    for square in squares:  # blocks of 20 m from multiples of 60 m: whole squares of 3 x 3 at most
        assert len({i * BLOCK // 60 for i, _ in square}) == 1 and len({j * BLOCK // 60 for _, j in square}) == 1
        assert len(square) <= 9


def test_runs():
    assert ranges.runs([10, 0, 31, 20], [10, 10, 5, 10], gap=0) == [(0, 29), (31, 35)]
    assert ranges.runs([10, 0, 30, 20], [10, 10, 5, 10], gap=0) == [(0, 34)]
    assert ranges.runs([0, 5, 100], [10, 0, 1], gap=0) == [(0, 9), (100, 100)]
    # a COG's tiles in a row, a few bytes apart: one run; the next row far away: another
    assert ranges.runs([0, 1008, 2016, 900_000], [1000, 1000, 1000, 1000]) == [(0, 3015), (900_000, 900_999)]


def test_get_range_takes_only_whole_answers(http_server, monkeypatch):
    monkeypatch.setattr(src.net, "_sleep", lambda attempt: None)
    body = bytes(range(256)) * 10
    http_server.add("/data.bin", body)
    assert ranges.get_range(http_server.url("/data.bin"), 100, 199) == (body[100:200], len(body))
    assert ranges.get_range(http_server.url("/data.bin"), 2500, 9999) == (body[2500:], len(body))
    with pytest.raises(ranges.Missing):
        ranges.get_range(http_server.url("/none.bin"), 0, 9)
    http_server.fault("/data.bin", "truncate", lambda n, r: True)
    with pytest.raises(RuntimeError):
        ranges.get_range(http_server.url("/data.bin"), 0, 1999)
    assert len([r for r in http_server.requests("/data.bin") if r.headers.get("range") == "bytes=0-1999"]) == \
        src.net.RETRIES


def test_country_prefetch_in_groups(monkeypatch):
    import country
    asked = []
    monkeypatch.setattr(src, "download_layers", lambda *a, **k: asked.append(k))

    class Plan:
        resolution, layers = 1.0, [object()]
        grid = gd.Grid(left=0, top=10, res=1.0, height=10, width=10, crs=CRS)

        class params:
            water = "none"

        class paths:
            cache = "cache"
    import search
    monkeypatch.setattr(search, "_fills_gaps", lambda plan: False)
    country._prefetch({"S": Plan()}, lambda text: None)
    assert asked == [{"group_m": country.PREFETCH_GROUP_M}]


def _layer_serial(server, serial, block=BLOCK, name="west.tif"):
    url = server.url(f"/files/{name}")
    return FileBlocks("Test serial", f"test/serial-{int(serial)}/1", CRS, 1.0, block,
                      lambda i, j: [(name, url, 2025)], bytes_per_tile=1e4, serial=serial)


def _asked_bytes(server, path):
    """The bytes the range requests to path asked for."""
    total = 0
    for r in server.requests(path):
        first, _, last = r.headers.get("range", "bytes=0-0").split("=")[1].partition("-")
        total += int(last) - int(first) + 1
    return total


def test_serial_reads_find_shared_tiles_in_gdals_cache(files, tmp_path, monkeypatch):
    """Range by range, the neighbours of a square find the tiles they share in GDAL's cache of ranges: fewer
    bytes asked, the same cached files and rows. Tiles of 128 px (64 KB, beyond GDAL's chunks of 16 KB) under
    blocks of 250 px, as Austria's 512 px under 1000."""
    monkeypatch.setattr(src.layer, "DOWNLOAD_THREADS", 1)
    path = str(tmp_path / "files" / "big.tif")
    band = np.random.default_rng(7).normal(900, 30, (1024, 1024)).astype(np.float32)
    with rio.open(path, "w", driver="GTiff", width=1024, height=1024, count=1, dtype="float32", crs=CRS,
                  nodata=-9999.0, transform=from_origin(E0, N0 + 1024, 1.0, 1.0), tiled=True, blockxsize=128,
                  blockysize=128) as dst:
        dst.write(band, 1)
    with open(path, "rb") as f:
        files.add("/files/big.tif", f.read(), "image/tiff")
    grid = gd.Grid(left=E0 + 250.5, top=N0 + 749.5, res=1.0, height=499, width=499, crs=CRS)
    out = {}
    for serial in (False, True):
        layer = _layer_serial(files, serial, block=250, name="big.tif")
        assert len(layer.tiles(grid)) == 4
        name = "/files/big.tif"
        rasterio.cache.invalidate(files.url(name))  # nothing of the run before in GDAL's caches
        before = _asked_bytes(files, name)
        cache_dir = tmp_path / f"cache-{serial}"
        src.download_layers([(layer, "terrain")], grid, str(cache_dir), None)
        found, rows = _cached(str(cache_dir), layer.folder)
        out[serial] = (_asked_bytes(files, name) - before, found, [r[1:] for r in rows])
    assert len(out[False][1]) == 4 and out[True][1] == out[False][1] and out[True][2] == out[False][2]
    assert out[True][0] < 0.8 * out[False][0]


def test_serial_layers_go_in_squares(files):
    layer = _layer_serial(files, True)
    tiles = layer.tiles(_grid(200, 180))
    tasks = src.layer._tasks([(layer, t) for t in tiles], None)
    assert {kind for _, _, kind in tasks} == {"square"}
    assert sorted(t for _, square, _ in tasks for t in square) == sorted(tiles)
    assert all(len(square) <= src.layer.SERIAL_SQUARE ** 2 for _, square, _ in tasks)
    assert {kind for _, _, kind in src.layer._tasks([(layer, t) for t in tiles], 60)} == {"group"}
    plain = _layer(files, "west")
    assert {kind for _, _, kind in src.layer._tasks([(plain, t) for t in tiles], None)} == {"tile"}


def test_serial_sources():
    """Range by range where it was faster too (docs/performance.md, "Window reads")."""
    serial = {s.id for s in src.SOURCES.values() for lay in (s.nmt, s.nmpt) if getattr(lay, "serial", False)}
    assert serial == {"austria", "luxembourg", "british_columbia"}


def test_strips_end_on_the_rows_of_tiles():
    from sources.readers.windows import _strips

    class Src:
        block_shapes = [(512, 512)]
    assert _strips(Src, 100, 1600) == [(100, 512), (512, 1024), (1024, 1536), (1536, 1600)]
    Src.block_shapes = [(128, 128)]
    assert _strips(Src, 0, 1200) == [(0, 512), (512, 1024), (1024, 1200)]
    Src.block_shapes = [(1, 9000)]  # a file of one-row strips
    assert _strips(Src, 10, 700) == [(10, 512), (512, 700)]
    assert _strips(Src, 5, 6) == [(5, 6)]
