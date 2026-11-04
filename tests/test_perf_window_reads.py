"""tools/perf_window_reads.py: its modes, the order in squares, GDAL's network statistics and a measurement of a
FileBlocks layer against the local server (tests/http_server.py), offline."""

import os
import sys

import numpy as np
import pytest
import rasterio as rio
from rasterio.transform import from_origin

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools"))
import grid as gd  # noqa: E402
import perf_window_reads as pw  # noqa: E402
from sources.layers.fileblocks import FileBlocks  # noqa: E402

CRS = "EPSG:3035"
LEFT, TOP = 4400000.0, 2650200.0
SIZE = 200   # pixels of the file a side (1 m)
BLOCK = 20   # metres: blocks of 20 px over the file's 16 px tiles, as Austria's 1000 px over 512


def _file(path):
    """A tiled GeoTIFF of SIZE x SIZE px (16 px internal tiles, like a COG's), values that compress little."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    band = np.random.default_rng(1).normal(1000, 50, (SIZE, SIZE)).astype(np.float32)
    with rio.open(path, "w", driver="GTiff", width=SIZE, height=SIZE, count=1, dtype="float32", crs=CRS,
                  transform=from_origin(LEFT, TOP, 1.0, 1.0), tiled=True, blockxsize=16, blockysize=16,
                  compress="lzw") as dst:
        dst.write(band, 1)


def _layer(server):
    return FileBlocks("Test windows", "test/windows/1", CRS, 1.0, BLOCK, server.url("/files/one.tif"),
                      bytes_per_tile=1e3)


def _grid(blocks=6):
    """A grid over blocks x blocks of the layer's blocks inside the file (half a pixel inside their edges)."""
    return gd.Grid(left=LEFT + 3 * BLOCK + 0.5, top=TOP - 3 * BLOCK - 0.5, res=1.0, height=blocks * BLOCK - 1,
                   width=blocks * BLOCK - 1, crs=CRS)


def test_modes():
    assert pw.parse_mode("blocks") == {}
    assert pw.parse_mode("cache=256,order=squares,threads=1") == {"cache": 256, "order": "squares", "threads": 1}
    assert pw.slug(pw.parse_mode("order=squares,cache=64")) == "cache64-ordersquares"
    assert pw.slug({}) == "blocks"
    for bad in ("cache", "order=rows", "speed=2"):
        with pytest.raises(ValueError):
            pw.parse_mode(bad)


def test_downloaded_reads_the_totals():
    stats = {"methods": {"HEAD": {"count": 2}, "GET": {"count": 15, "downloaded_bytes": 65798200}},
             "handlers": {"vsicurl": {"methods": {"GET": {"count": 15, "downloaded_bytes": 65798200}}}}}
    assert pw.downloaded(stats) == {"bytes": 65798200, "gets": 15, "heads": 2}
    assert pw.downloaded({}) == {"bytes": 0, "gets": 0, "heads": 0}


def test_squares_keep_neighbours_together(http_server):
    layer = _layer(http_server)
    tiles = layer.tiles(_grid(8))
    assert len(tiles) == 64
    ordered = pw.in_squares(layer, tiles, blocks=4)
    assert sorted(ordered) == sorted(tiles)
    # squares of 4 x 4 blocks on the blocks' own grid (not the search's): each one a single run
    squares = [(j // 4, i // 4) for i, j in ordered]
    runs = [s for k, s in enumerate(squares) if k == 0 or s != squares[k - 1]]
    assert len(runs) == len(set(runs)) == 9


def test_measure_a_layer(http_server, tmp_path, monkeypatch):
    _file(str(tmp_path / "files" / "one.tif"))
    http_server.add_folder("/files", str(tmp_path / "files"))
    monkeypatch.setenv("CPL_VSIL_NETWORK_STATS_ENABLED", "YES")
    layer, grid = _layer(http_server), _grid(4)
    result = pw.measure_layer(layer, grid, str(tmp_path / "cache"), {})
    assert result["blocks"] == 16 and result["cache"]["files"] == 16
    assert result["cache"]["km2"] == pytest.approx(16 * BLOCK * BLOCK / 1e6)
    net = result["network"]
    assert net["bytes"] > 0 and net["gets"] >= 1
    p = result["predicted"]
    assert p["tile_px"] == [16]
    # blocks of 20 px from 60 px: each touches 2 or 3 tiles a side; the 80 px square holds 6 x 6 tiles
    assert p["file_tiles"] == 36 and p["per_block"] > p["each_tile_once"] > 0
    assert "| test |" not in pw.table([dict(result, source="test")]).splitlines()[0]
    # in groups: the same cached blocks
    grouped = pw.measure_layer(_layer(http_server), grid, str(tmp_path / "grouped"), {"group": 40}, predict=False)
    assert grouped["mode"] == "group40" and grouped["cache"] == result["cache"]
    assert 0 < grouped["network"]["bytes"]
