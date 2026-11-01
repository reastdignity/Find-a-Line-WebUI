"""FileBlocks (FileBlockTiling read by Windows): blocks of big fixed files in a metric CRS, read by HTTP
range requests from the local server (tests/http_server.py): a fixed grid of files that overlap by one
pixel (Austria) and one national file (Wales, Luxembourg)."""

import os
import sys

import numpy as np
import pytest
import rasterio as rio
from rasterio.transform import from_origin

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cache  # noqa: E402
import grid as gd  # noqa: E402
import sources as src  # noqa: E402
from sources.indexes.tilings import FileBlockTiling  # noqa: E402
from sources.layers.fileblocks import FileBlocks  # noqa: E402

CRS = "EPSG:3035"
E0, N0 = 4400000, 2650000  # the lower-left pixel centre of the first file
SIZE = 100                 # metres between files (Austria: 50 000), each SIZE + 1 pixels wide
BLOCK = 20


def _file(path, left, top, band, res=1.0, crs=CRS, nodata=-9999.0):
    """A tiled GeoTIFF (16 px blocks, like a COG's internal tiles); NaN becomes nodata."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with rio.open(path, "w", driver="GTiff", width=band.shape[1], height=band.shape[0], count=1, dtype="float32",
                  crs=crs, nodata=nodata, transform=from_origin(left, top, res, res), tiled=True,
                  blockxsize=16, blockysize=16) as dst:
        dst.write(np.where(np.isnan(band), nodata, band).astype(np.float32), 1)


def _name(e, n):
    return f"T_N{n}E{e}.tif"


def _grid_of_files(folder):
    """Two files side by side, named by their lower-left pixel centre, pixel centres on whole
    metres, SIZE + 1 pixels: they share a column of pixels (told apart by their values)."""
    bands = {}
    for k, e in enumerate((E0, E0 + SIZE)):
        band = np.add.outer(np.arange(SIZE + 1) * 1000.0, np.arange(SIZE + 1)) + 500000.0 * k
        _file(os.path.join(folder, _name(e, N0)), e - 0.5, N0 + SIZE + 0.5, band)
        bands[e] = band
    return bands


def _layer(server):
    """A layer of a grid of files on the server, which lists three files in a row (the third is not
    on the server) and nothing beyond them."""
    def files(i, j):
        e, n = (i * BLOCK) // SIZE * SIZE, (j * BLOCK) // SIZE * SIZE
        if n != N0 or e not in (E0, E0 + SIZE, E0 + 2 * SIZE):
            return []
        return [(_name(e, n), server.url(f"/files/{_name(e, n)}"), 2025)]
    return FileBlocks("Test blocks", "test/blocks/20250915", CRS, 1.0, BLOCK, files, origin=(0.5, 0.5),
                      bytes_per_tile=1e4)


def test_blocks_of_a_grid_of_files(http_server, tmp_path, monkeypatch):
    """Blocks on the files' own pixels (centres on whole metres: edges at x.5) are copied exactly;
    a block at the end of a file reads that file, the next one the neighbour (the shared column of
    pixels comes from the first); a block of a file the server does not have (404) and one without
    files are missing; tile_of inverts the path."""
    # One block at a time: eight threads of GDAL at once overrun the test server (connections
    # aborted on Windows, response_code=0)
    monkeypatch.setattr(src.layer, "DOWNLOAD_THREADS", 1)
    bands = _grid_of_files(str(tmp_path / "files"))
    http_server.add_folder("/files", str(tmp_path / "files"))
    layer, cache_dir = _layer(http_server), str(tmp_path / "cache")
    j = (N0 + SIZE - BLOCK) // BLOCK                      # the top row of blocks of the files
    i = (E0 + SIZE - BLOCK) // BLOCK                      # the last column of blocks of the first file
    grid = gd.make_grid((E0 + SIZE - 30, N0 + SIZE - 15, E0 + 3 * SIZE + 5, N0 + SIZE - 5), 1.0, CRS, (0.5, 0.5))
    tiles = layer.tiles(grid)
    assert (i, j) in tiles and (i + 1, j) in tiles and (i - 1, j) in tiles and (i + 11, j) in tiles
    assert len(tiles) == len(set(tiles)) == 13
    layer.download(grid, cache_dir, None, "test")
    with rio.open(layer.tile_path(cache_dir, (i, j))) as block:
        assert block.crs.to_epsg() == 3035 and block.shape == (BLOCK, BLOCK)
        assert block.transform.c == E0 + SIZE - BLOCK + 0.5 and block.transform.f == N0 + SIZE + 0.5
        assert (block.read(1) == bands[E0][0:BLOCK, SIZE - BLOCK + 1:SIZE + 1]).all()  # up to the shared column
        assert block.tags()["sources"] == _name(E0, N0)
    with rio.open(layer.tile_path(cache_dir, (i + 1, j))) as block:
        assert (block.read(1) == bands[E0 + SIZE][0:BLOCK, 1:BLOCK + 1]).all()        # the neighbour, after it
        assert block.tags()["sources"] == _name(E0 + SIZE, N0) and block.tags()["years"] == "2025"
    states = {t: cache.state(cache_dir, layer.tile_path(cache_dir, t)) for t in tiles}
    assert states[(i + 6, j)] == "missing"                # listed, but 404 on the server
    assert states[(i + 11, j)] == "missing"               # no file listed: not asked
    assert {t for t, s in states.items() if s == "ok"} == {(i - 1, j), (i, j)} | {(i + k, j) for k in range(1, 6)}
    asked = {r.path for r in http_server.requests("/files/")}
    assert asked == {f"/files/{_name(e, N0)}" for e in (E0, E0 + SIZE, E0 + 2 * SIZE)}
    # The blocks on the grid as they are (no resampling)
    mosaic = src.build_mosaic(layer.files(grid, cache_dir), grid, str(tmp_path / "m.npy"), "test")
    assert grid.left == E0 + SIZE - 30.5 and grid.top == N0 + SIZE - 4.5
    assert mosaic[0, 0] == bands[E0][5, 70] and mosaic[0, 80] == bands[E0 + SIZE][5, 50]
    assert np.isnan(mosaic[:, 131:]).all() and not np.isnan(mosaic[:, :131]).any()
    # Paths and tiles
    relative = cache.relative(cache_dir, layer.tile_path(cache_dir, (i, j)))
    assert relative == f"test/blocks/20250915/{i // 50}_{j // 50}/{i}_{j}.tif"
    assert layer.tile_of(relative) == (i, j)
    assert layer.tile_of(relative.replace(f"{i // 50}_", f"{i // 50 + 1}_")) is None
    assert layer.tile_of("test/blocks/20240915/" + relative.split("/", 3)[3]) is None
    west, south, east, north = layer.bounds_wgs84((i, j))
    assert west < east and south < north and 9 < west < 17 and 46 < south < 49.1
    assert layer.ttl_days is None                          # an edition never changes
    assert layer.tile_url((i, j)) == http_server.url(f"/files/{_name(E0, N0)}")
    assert layer.tile_url((i + 11, j)) is None


@pytest.mark.parametrize("tile", [(0, 0), (-1, 0), (0, -1), (-51, -50), (219999, 132500), (-7, 123456)])
def test_path_and_tile_of(tmp_path, tile):
    index = FileBlockTiling(CRS, "x/y", 1.0, 1000, lambda i, j: [])
    relative = os.path.relpath(index.path(str(tmp_path), tile), tmp_path).replace(os.sep, "/")
    assert index.tile_of(relative) == tile
    assert len(os.path.dirname(relative).split("/")) == 3


def test_blocks_are_whole_pixels():
    with pytest.raises(ValueError):
        FileBlockTiling(CRS, "x", 0.3, 1000, lambda i, j: [])


def test_tiles_of_an_area():
    """Only the blocks under an area's outline (as the other indexes)."""
    from shapely.geometry import box
    index = FileBlockTiling(CRS, "x", 1.0, 100, lambda i, j: [], origin=(0.5, 0.5))
    grid = gd.make_grid((E0, N0, E0 + 300, N0 + 300), 1.0, CRS, (0.5, 0.5))
    assert len(index.tiles(grid)) == 25                    # edges at x.5: 5 x 5 blocks
    grid.area_shape = box(E0 + 10, N0 + 10, E0 + 50, N0 + 250)
    assert index.tiles(grid) == [(E0 // 100, N0 // 100 + k) for k in range(3)]


def test_one_national_file(http_server, tmp_path, monkeypatch):
    """One national COG (pixel edges on whole metres) is one line: its address as files and its
    extent; a block partly over it gets what it has, one beyond the extent is missing unasked."""
    monkeypatch.setattr(src.layer, "DOWNLOAD_THREADS", 1)  # as above
    left, top, res = 200010.0, 300040.0, 2.0
    band = np.add.outer(np.arange(20) * 100.0, np.arange(30)).astype(np.float32)   # 60 x 40 m
    _file(str(tmp_path / "files" / "national.tif"), left, top, band, res=res, crs="EPSG:27700")
    http_server.add_folder("/files", str(tmp_path / "files"))
    layer = FileBlocks("National", "test/national/2022", "EPSG:27700", res, 20, http_server.url("/files/national.tif"),
                       extent=(left, top - 40, left + 60, top))
    cache_dir = str(tmp_path / "cache")
    grid = gd.make_grid((left - 20, top - 18, left + 80, top - 2), res, "EPSG:27700")
    tiles = layer.tiles(grid)
    assert tiles == [(i, 15001) for i in range(9999, 10005)]
    layer.download(grid, cache_dir, None, "test")

    def block(i):
        with rio.open(layer.tile_path(cache_dir, (i, 15001))) as raster:
            assert raster.shape == (10, 10) and raster.tags()["sources"] == "national.tif"
            return raster.read(1)
    assert np.isnan(block(10000)[:, :5]).all() and (block(10000)[:, 5:] == band[0:10, 0:5]).all()  # partly
    assert (block(10001) == band[0:10, 5:15]).all() and (block(10002) == band[0:10, 15:25]).all()
    assert (block(10003)[:, :5] == band[0:10, 25:30]).all() and np.isnan(block(10003)[:, 5:]).all()
    states = [cache.state(cache_dir, layer.tile_path(cache_dir, t)) for t in tiles]
    assert states == ["missing", "ok", "ok", "ok", "ok", "missing"]
    assert layer.tile_url((10004, 15001)) is None and layer.tile_url((10000, 15001)).endswith("/national.tif")
    asked = http_server.requests("/files/")
    assert asked and all(r.path == "/files/national.tif" for r in asked)


def test_probe_reads_a_window(http_server, tmp_path, capsys):
    """findaline.py sources check: a FileBlocks layer is probed by a window of its first block's
    file; a file the server does not have fails."""
    from rasterio.warp import transform as warp
    from sources import probe
    _grid_of_files(str(tmp_path / "files"))
    http_server.add_folder("/files", str(tmp_path / "files"))
    (lon,), (lat,) = warp(CRS, "EPSG:4326", [E0 + 70], [N0 + 60])
    (lon2,), (lat2,) = warp(CRS, "EPSG:4326", [E0 + 2 * SIZE + 70], [N0 + 60])
    layer = _layer(http_server)
    sources = {sid: src.Source(id=sid, name=sid, description=sid, nmt=layer, crs=CRS, grid_origin=(0.5, 0.5),
                               sample=sample, default_resolution=1.0)
               for sid, sample in (("there", (lat, lon)), ("gone", (lat2, lon2)))}
    assert probe.strategy(layer) == "window"
    assert probe.run(str(tmp_path / "cache"), ["there"], sources=sources) == 0
    assert "window 100% with data" in capsys.readouterr().out
    assert probe.run(str(tmp_path / "cache"), ["gone"], sources=sources) == 1
    assert "FAIL" in capsys.readouterr().out
