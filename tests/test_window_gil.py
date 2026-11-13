"""The window reader makes no HTTP request while holding the GIL (windows._scan_directories), at no extra request;
nor do the tools' remote reads (check_source's WarpedVRT, obstacle_study's reproject, perf_window_reads' tile sizes).

The server of these tests (tests/http_server.py) lives in this process and answers only when it gets the GIL: a
request GDAL makes with the GIL held waits for curl's timeout (5 s here, no retries), and a watchdog thread stands
still meanwhile. rasterio 1.5.2 asks the mask flags with the GIL held on every read, and GTiff's first such call
scans the file's directories: a request when they lie beyond the bytes the open fetched (a file that is not a COG)
or when GDAL's cache of the file was dropped between the open and the read (another thread's failure, _forget).
Before the fix one test of test_window_groups.py waited 496 s in 2 of 20 runs (2026-11-13).
"""

import contextlib
import os
import sys
import threading
import time

import numpy as np
import pytest
import rasterio as rio
import rasterio.cache
import rasterio.shutil
from affine import Affine
from rasterio.transform import from_origin
from rasterio.windows import Window

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools"))
import check_source  # noqa: E402
import obstacle_study  # noqa: E402
import perf_window_reads as pw  # noqa: E402
import sources as src  # noqa: E402
from http_server import _ranges  # noqa: E402
from sources.readers import windows  # noqa: E402

CRS = "EPSG:2180"
LEFT, TOP = 500000.0, 300000.0
WIDTH, HEIGHT = 1400, 1200
# A longer stand-still of the watchdog is a request made holding the GIL (curl waits 5 s); half of that, so the
# pauses of a crowded machine stay below it
STALL_S = 2.5


def _values():
    rows, cols = np.mgrid[0:HEIGHT, 0:WIDTH]
    data = (200 + rows * 0.37 + cols * 0.11 + np.sin(cols / 7.0) * 3).astype(np.float32)
    data[20:80, 30:90] = -9999.0
    return data


def _profile():
    return dict(driver="GTiff", width=WIDTH, height=HEIGHT, count=1, dtype="float32", crs=CRS,
                transform=from_origin(LEFT, TOP, 1, 1), tiled=True, blockxsize=256, blockysize=256,
                compress="deflate", nodata=-9999.0)


@pytest.fixture(scope="module")
def folder(tmp_path_factory):
    """far.tif: tiled, not a COG, its overviews and internal mask after the data; plain.tif: its directory in the
    header; cog.tif: GDAL's COG (512 px tiles, overviews)."""
    path = tmp_path_factory.mktemp("gil")
    data = _values()
    with rio.Env(GDAL_TIFF_INTERNAL_MASK=True), rio.open(path / "far.tif", "w", **_profile()) as dst:
        dst.write(data, 1)
        mask = np.full((HEIGHT, WIDTH), 255, np.uint8)
        mask[300:340, 400:460] = 0
        dst.write_mask(mask)
        dst.build_overviews([2, 4, 8])
    with rio.open(path / "plain.tif", "w", **_profile()) as dst:
        dst.write(data, 1)
    rasterio.shutil.copy(path / "plain.tif", path / "cog.tif", driver="COG", COMPRESS="DEFLATE", BLOCKSIZE="512")
    return path


@pytest.fixture
def served(http_server, folder, monkeypatch):
    """The files on the server, GDAL's timeout short and without retries (a request holding the GIL then fails in
    5 s, not in 4 x 120), no sleeping between attempts."""
    http_server.add_folder("/f", str(folder))
    original = windows._gdal_http

    @contextlib.contextmanager
    def short(serial=False):
        with original(serial), rio.Env(GDAL_HTTP_TIMEOUT="5", GDAL_HTTP_MAX_RETRY="0"):
            yield
    monkeypatch.setattr(windows, "_gdal_http", short)
    monkeypatch.setattr(src.net, "_sleep", lambda attempt: None)
    return http_server


class Watchdog:
    """A thread ticking every 10 ms; gap: its longest stand-still since started."""

    def __init__(self):
        self.gap, self.last, self.on = 0.0, time.perf_counter(), True
        self.thread = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        while self.on:
            now = time.perf_counter()
            self.gap, self.last = max(self.gap, now - self.last), now
            time.sleep(0.01)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.on = False
        self.thread.join()


BLOCKS = {  # (column, row of the block's first pixel; .5: off the file's pixels, the resampled read), 200 x 200 px
    "own pixels": (500, 520),
    "resampled": (500.5, 520.5),
    "thin edge": (WIDTH - 1, 300),       # one column of the file
    "corner": (WIDTH - 2, HEIGHT - 1),   # 2 x 1 px
}


def _block(served, folder, name, column, row, tmp_path):
    transform = Affine(1, 0, LEFT + column, 0, -1, TOP - row)
    remote, local = str(tmp_path / "remote.tif"), str(tmp_path / "local.tif")
    windows._read_block([(name, served.url(f"/f/{name}"), 2020)], CRS, transform, (200, 200), remote, "remote")
    windows._read_block([(name, str(folder / name), 2020)], CRS, transform, (200, 200), local, "local")
    with rio.open(remote) as a, rio.open(local) as b:
        assert np.array_equal(a.read(1), b.read(1), equal_nan=True)


@pytest.mark.parametrize("block", BLOCKS)
def test_directories_beyond_the_header(served, folder, block, tmp_path):
    """A file whose directories lie after its data: every read needs them, never with the GIL held."""
    rasterio.cache.invalidate(served.url("/f/far.tif"))
    with Watchdog() as watchdog:
        _block(served, folder, "far.tif", *BLOCKS[block], tmp_path)
    assert watchdog.gap < STALL_S


@pytest.mark.parametrize("block", BLOCKS)
def test_cache_dropped_before_the_read(served, folder, block, tmp_path, monkeypatch):
    """GDAL's cache of the file dropped between the open and the read (what another thread's _forget does)."""
    original = windows._read_window

    def dropped(source, transform, shape):
        rasterio.cache.invalidate(served.url("/f/plain.tif"))
        return original(source, transform, shape)
    monkeypatch.setattr(windows, "_read_window", dropped)
    with Watchdog() as watchdog:
        _block(served, folder, "plain.tif", *BLOCKS[block], tmp_path)
    assert watchdog.gap < STALL_S


COG_BLOCKS = {  # (column, row, width, height) on the COG's 512 px tiles
    "one tile": (100, 100, 200, 200),
    "nine tiles": (400, 400, 700, 700),
    "edge": (WIDTH - 100, HEIGHT - 100, 200, 200),
    "thin edge": (WIDTH - 1, 300, 200, 200),
    "resampled": (600.5, 600.5, 300, 300),
    "5 x 5": (700, 700, 5, 5),  # at factor 5 / round(5 / 1.5) = 1.67 GDAL would take the 2x overview
    "8 x 8": (700, 700, 8, 8),
}


@pytest.mark.parametrize("serial", [False, True])
def test_the_scan_costs_no_request(served, folder, serial, tmp_path, monkeypatch):
    """The scan's read fetches what the read fetches and GDAL's block cache serves the read: the same requests and
    bytes per block (a COG: without the scan the flags need no request here either), the same values."""
    url, size = served.url("/f/cog.tif"), os.path.getsize(folder / "cog.tif")
    scan = windows._scan_directories

    def asked(with_scan, column, row, width, height):
        monkeypatch.setattr(windows, "_scan_directories", scan if with_scan else lambda source, window: None)
        rasterio.cache.invalidate(url)
        before = len(served.requests())
        path = str(tmp_path / f"{with_scan}.tif")
        windows._read_block([("cog", url, 2020)], CRS, Affine(1, 0, LEFT + column, 0, -1, TOP - row),
                            (height, width), path, "cog", serial=serial)
        ranges = [_ranges(r.headers["range"], size) for r in served.requests()[before:] if "range" in r.headers]
        with rio.open(path) as f:
            return len(ranges), sum(b - a + 1 for found in ranges for a, b in found), f.read(1)

    for block in COG_BLOCKS.values():
        n, size_read, values = asked(True, *block)
        n0, size_read0, values0 = asked(False, *block)
        assert (n, size_read) == (n0, size_read0)
        assert np.array_equal(values, values0, equal_nan=True)


def test_the_scan_without_rasterios_private_read():
    """Another rasterio without DatasetReaderBase._read of this form: the read goes on without the scan."""
    window = Window(0, 0, 10, 10)

    class Missing:
        width = height = 100
        dtypes = ("float32",)

    class Changed(Missing):
        def _read(self, indexes, out):  # called with four arguments: TypeError
            raise AssertionError("never reached")

    windows._scan_directories(Missing(), window)
    windows._scan_directories(Changed(), window)


# The tools' remote reads (tools/check_source.py, obstacle_study.py, perf_window_reads.py)

class _ShortEnv(rio.Env):
    """rio.Env with GDAL's HTTP timeout 5 s and no retries wherever the code asks for a timeout (the tools open their
    own: check_source's, net._gdal_http's)."""

    def __init__(self, *args, **options):
        if "GDAL_HTTP_TIMEOUT" in options:
            options.update(GDAL_HTTP_TIMEOUT="5", GDAL_HTTP_MAX_RETRY="0")
        super().__init__(*args, **options)


@pytest.fixture
def tools_served(http_server, folder, monkeypatch):
    http_server.add_folder("/f", str(folder))
    monkeypatch.setattr(rio, "Env", _ShortEnv)
    monkeypatch.setattr(src.net, "_sleep", lambda attempt: None)
    return http_server


@pytest.mark.parametrize("name", ["far.tif", "plain.tif"])
def test_check_source_warped_vrt(tools_served, folder, name, monkeypatch):
    """check_source._read_source (a WarpedVRT over /vsicurl/) needs no change: rasterio makes the VRT under nogil,
    which runs the scan, and the VRT's own mask flags never reach the source. Guarded here, plain.tif with GDAL's
    cache dropped right before vrt.read."""
    url = tools_served.url(f"/f/{name}")

    class Dropped(check_source.WarpedVRT):
        def read(self, *args, **kwargs):
            rasterio.cache.invalidate(url)
            return super().read(*args, **kwargs)
    if name == "plain.tif":
        monkeypatch.setattr(check_source, "WarpedVRT", Dropped)
    profile = {"crs": CRS, "transform": Affine(1, 0, LEFT + 100, 0, -1, TOP - 100), "width": 300, "height": 300}
    rasterio.cache.invalidate(url)
    with Watchdog() as watchdog:
        remote = check_source._read_source(url, profile)
    assert watchdog.gap < STALL_S
    assert np.array_equal(remote, check_source._read_source(str(folder / name), profile), equal_nan=True)


@pytest.mark.parametrize("name", ["far.tif", "plain.tif"])
def test_obstacle_study_warp(tools_served, folder, name, monkeypatch):
    """obstacle_study.on_grid: rasterio's reproject initialises GDAL's warper holding the GIL, which scans the
    source's directories: _scan_footprint scans them first. plain.tif with GDAL's cache dropped right before the
    warp; values against a local read."""
    import rasterio.warp
    url = tools_served.url(f"/f/{name}")
    original = rasterio.warp.reproject

    def dropped(*args, **kwargs):
        rasterio.cache.invalidate(url)
        return original(*args, **kwargs)
    if name == "plain.tif":
        monkeypatch.setattr(rasterio.warp, "reproject", dropped)
    grid = {"crs": CRS, "res": 2.0, "left": LEFT + 100.5, "top": TOP - 100.5, "width": 150, "height": 150}
    rasterio.cache.invalidate(url)
    with Watchdog() as watchdog:
        remote = obstacle_study.on_grid([url], grid, rasterio.warp.Resampling.max)
    assert watchdog.gap < STALL_S
    local = obstacle_study.on_grid([str(folder / name)], grid, rasterio.warp.Resampling.max)
    assert np.array_equal(remote, local, equal_nan=True)


@pytest.fixture(scope="module")
def small_tiles(tmp_path_factory):
    """2048 x 2048 px in tiles of 16 px: the arrays of the tiles' offsets and sizes lie beyond the header."""
    path = tmp_path_factory.mktemp("tiles") / "small.tif"
    band = (np.arange(2048 * 2048, dtype=np.float32).reshape(2048, 2048) % 5000) + 100
    with rio.open(path, "w", driver="GTiff", width=2048, height=2048, count=1, dtype="float32", crs=CRS,
                  transform=from_origin(LEFT, TOP, 1, 1), tiled=True, blockxsize=16, blockysize=16,
                  compress="deflate") as dst:
        dst.write(band, 1)
    return path


def test_perf_window_reads_tile_sizes(tools_served, small_tiles):
    """perf_window_reads.predicted reads the tiles' sizes through GDAL's C API by ctypes (_TiffTags): rasterio's
    get_tag_item would load the arrays of tile sizes holding the GIL. A block at the file's far end; the numbers
    equal those of a local read."""
    from sources.layers.fileblocks import FileBlocks
    import grid as gd
    tools_served.add("/f/small.tif", small_tiles.read_bytes(), "image/tiff")
    url = tools_served.url("/f/small.tif")
    g = gd.Grid(left=LEFT + 2000.5, top=TOP - 2000.5, res=1.0, height=19, width=19, crs=CRS)

    def layer(where):
        return FileBlocks("Test tiles", "test/tiles/1", CRS, 1.0, 20, where, bytes_per_tile=1e3)
    rasterio.cache.invalidate(url)
    remote_layer = layer(url)
    tiles = remote_layer.tiles(g)
    with Watchdog() as watchdog:
        remote = pw.predicted(remote_layer, tiles)
    assert watchdog.gap < STALL_S
    assert remote == pw.predicted(layer(str(small_tiles)), tiles) and remote["file_tiles"] > 0
