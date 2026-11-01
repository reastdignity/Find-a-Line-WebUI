"""Windows (blocks read from remote files through GDAL's /vsicurl/) when the server fails: a range
answer cut short must never become a block of nodata or zeros ("silent zeros", docs/roadmap.md),
a connection closed without an answer is tried again by GDAL (net.GDAL_RETRY_CODES)."""

import logging
import os
import sys

import numpy as np
import pytest
import rasterio as rio
from rasterio.transform import from_origin

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import sources as src  # noqa: E402
from sources.readers.windows import _read_block  # noqa: E402

CRS = "EPSG:3035"
SIZE = 2048  # pixels a side, in 16 px tiles: the tiles' offsets lie beyond GDAL's first read of the header
HEADER = "bytes=0-16383"  # that first read


@pytest.fixture(scope="module")
def tiff(tmp_path_factory):
    """A tiled GeoTIFF without nodata (where GDAL fills a block it takes for sparse with zeros) and its values."""
    path = str(tmp_path_factory.mktemp("windows") / "big.tif")
    band = (np.arange(SIZE * SIZE, dtype=np.float32).reshape(SIZE, SIZE) % 5000) + 100
    with rio.open(path, "w", driver="GTiff", width=SIZE, height=SIZE, count=1, dtype="float32", crs=CRS,
                  transform=from_origin(0, SIZE, 1, 1), tiled=True, blockxsize=16, blockysize=16) as dst:
        dst.write(band, 1)
    with open(path, "rb") as f:
        return f.read(), band


def _read(server, tiff, tmp_path, name="/big.tif", **fault):
    """A 40 x 40 block from the middle of the file on the server (at name: GDAL caches what it
    read of a URL), the fault given set on it."""
    data, band = tiff
    server.add(name, data, "image/tiff")
    if fault:
        server.fault(name, **fault)
    path = str(tmp_path / "block.tif")
    fetched = _read_block([("big", server.url(name), 2020)], CRS, from_origin(1000, SIZE - 1000, 1, 1),
                          (40, 40), path, "test")
    return path, fetched, band[1000:1040, 1000:1040]


def _headers_read(server):
    return sum(r.headers.get("range") == HEADER for r in server.requests("/big.tif"))


@pytest.fixture(autouse=True)
def no_waiting(monkeypatch):
    monkeypatch.setattr(src.net, "_sleep", lambda attempt: None)


def test_normal_read(http_server, tiff, tmp_path):
    path, fetched, expected = _read(http_server, tiff, tmp_path)
    with rio.open(path) as block:
        assert (block.read(1) == expected).all()
    assert fetched.received == os.path.getsize(path) and _headers_read(http_server) == 1


def test_answer_cut_short_is_read_again(http_server, tiff, tmp_path, caplog):
    """The header's answer cut short: GDAL takes the offsets it could not read for sparse tiles and
    returns zeros without an exception; the read is tried again with GDAL's cache of the file
    dropped, and the block holds the file's values. GDAL's errors reach no log handler."""
    path, _, expected = _read(http_server, tiff, tmp_path, kind="truncate", when=lambda n, r: n == 1)
    with rio.open(path) as block:
        assert (block.read(1) == expected).all()
    assert _headers_read(http_server) == 2
    assert not [r for r in caplog.records if "GDAL signalled" in r.getMessage()]


def test_answer_cut_short_with_gdal_threads(http_server, tiff, tmp_path, monkeypatch):
    """GDAL_NUM_THREADS in the environment (tools/test_lock.py sets it): GDAL's threads would read
    the blocks, their errors unseen (zeros again); _gdal_http keeps the reads in the caller's thread."""
    monkeypatch.setenv("GDAL_NUM_THREADS", "ALL_CPUS")
    path, _, expected = _read(http_server, tiff, tmp_path, kind="truncate", when=lambda n, r: n == 1)
    with rio.open(path) as block:
        assert (block.read(1) == expected).all()


def test_answers_cut_short_every_time(http_server, tiff, tmp_path):
    """Cut short in every attempt: no block is written, the download fails."""
    with pytest.raises(RuntimeError, match="Could not read test big completely"):
        _read(http_server, tiff, tmp_path, kind="truncate", when=lambda n, r: r == HEADER)
    assert not os.path.exists(tmp_path / "block.tif")
    assert _headers_read(http_server) == src.net.RETRIES


def _tile(n, range_header):
    """Whether a range asks for tiles (beyond the header and its arrays of offsets)."""
    return int(range_header.split("=")[1].split("-")[0]) > 1_000_000


def test_tile_cut_short(http_server, tiff, tmp_path):
    """A tile's answer cut short once is read again; every time, GDAL raises: no block."""
    cut = []

    def once(n, r):
        if _tile(n, r) and not cut:
            cut.append(r)
            return True
        return False
    path, _, expected = _read(http_server, tiff, tmp_path, kind="truncate", when=once)
    with rio.open(path) as block:
        assert (block.read(1) == expected).all()
    assert cut
    (tmp_path / "again").mkdir()
    with pytest.raises(RuntimeError, match="Could not read test big"):
        _read(http_server, tiff, tmp_path / "again", name="/again.tif", kind="truncate", when=_tile)
    assert not os.path.exists(tmp_path / "again" / "block.tif")


def test_connection_closed_without_answer(http_server, tiff, tmp_path):
    """No answer at all (no HTTP status: 0) twice: curl itself asks once more on a reused connection,
    then GDAL does (net.GDAL_RETRY_CODES; without the 0 there the file failed to open)."""
    path, _, expected = _read(http_server, tiff, tmp_path, kind="close", when=lambda n, r: n <= 2)
    with rio.open(path) as block:
        assert (block.read(1) == expected).all()
    assert _headers_read(http_server) == 3


def test_gdal_errors_per_thread():
    """gdal_errors collects the errors of its own thread only and restores the loggers' output."""
    import threading
    from rasterio.errors import RasterioIOError
    seen_elsewhere = []

    def elsewhere():
        try:
            rio.open("/vsimem/none-elsewhere.tif")
        except RasterioIOError:
            seen_elsewhere.append(True)

    with src.net.gdal_errors() as errors:
        thread = threading.Thread(target=elsewhere)
        thread.start()
        thread.join()
        assert seen_elsewhere and not errors
        with src.net.gdal_errors() as inner:
            logging.getLogger("rasterio._err").info("GDAL signalled an error: err_no=%r, msg=%r", 1, "test")
        assert inner == ["test"] and errors == ["test"]



def _block_layer(server, name):
    """A FileBlocks layer of the one file at name, and the block at the middle of the file."""
    import grid as gd
    from sources.layers.fileblocks import FileBlocks
    layer = FileBlocks("Big", "test/big", CRS, 1.0, 40, server.url(name), extent=(0, 0, SIZE, SIZE))
    tiles = layer.tiles(gd.make_grid((1000, SIZE - 1040, 1040, SIZE - 1000), 1.0, CRS))
    return layer, tiles[0]


def _header_once(n, range_header):
    """The first reads of a file cut short: its header and the arrays of its tiles' offsets."""
    return n <= 5 and not _tile(n, range_header)


def test_probe_window_cut_short(http_server, tiff, tmp_path):
    """The probe's window (sources check): an answer cut short fails with GDAL's error, never as a
    share of the window with data; a whole answer gives the share."""
    from sources import probe
    http_server.add("/big.tif", tiff[0], "image/tiff")
    layer, tile = _block_layer(http_server, "/big.tif")
    assert probe._window(str(tmp_path), layer, tile) == "window 100% with data"
    http_server.add("/cut.tif", tiff[0], "image/tiff")
    http_server.fault("/cut.tif", "truncate", _header_once)
    layer, tile = _block_layer(http_server, "/cut.tif")
    with pytest.raises(RuntimeError, match="cut.tif not read completely: .*strile"):
        probe._window(str(tmp_path), layer, tile)
    # Read again in this process: GDAL's cache of the short answer was dropped
    assert probe._window(str(tmp_path), layer, tile) == "window 100% with data"


def test_check_source_file_cut_short(http_server, tiff):
    """tools/check_source.py's comparison with a source file: an answer cut short raises with GDAL's
    error (reported as a problem of the check), never values to compare."""
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
    import check_source as cs
    data, band = tiff
    profile = {"crs": CRS, "transform": from_origin(1000, SIZE - 1000, 1, 1), "width": 40, "height": 40}
    http_server.add("/cut.tif", data, "image/tiff")
    http_server.fault("/cut.tif", "truncate", _header_once)
    with pytest.raises(RuntimeError, match="not read completely"):
        cs._read_source(http_server.url("/cut.tif"), profile)
    assert (cs._read_source(http_server.url("/cut.tif"), profile) == band[1000:1040, 1000:1040]).all()
