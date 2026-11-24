"""Cyprus (DLS's 2019 tiles kept in ETRS89 degrees, warped onto blocks of Cyprus LTM: Windows(warp=)) and Estonia (the
Land Board's 1 m sheets behind a PHP download address read by our own range requests: Windows(ranged=True), its DSM
sheets downloaded whole: MetricSheetTiles, Download(tiff_only=, not_found=)). The catalogue's own layers are read
against the local server (their URLs' bases patched), so their settings are what is tested."""

import contextlib
import os
import re
import sys
import threading
import time

import numpy as np
import pytest
import rasterio as rio
import rasterio.cache
import requests
from rasterio.transform import from_origin
from rasterio.warp import Resampling, reproject, transform_bounds

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cache  # noqa: E402
import sources as src  # noqa: E402
from http_server import Answer, key_of  # noqa: E402
from sources import probe  # noqa: E402
from sources.catalogue import cyprus, estonia  # noqa: E402
from sources.layers.fileblocks import FileBlocks  # noqa: E402
from sources.readers import ranges, windows  # noqa: E402

NODATA_CY = -3.4028230607370965e+38  # DLS's files'
# The live error pages of the Estonian download address (2026-11-15), byte for byte: a sheet number out of range,
# asked with a Range (HTTP 206, Content-Range bytes 0-192/193), and a DSM sheet in the sea (HTTP 200, no Range)
EE_RANGE_ERROR = (b'<div class="alert alert-danger" role="alert"><span class="fa-solid fa-circle-exclamation" '
                  b'aria-hidden="true"></span> Error: map sheet numbers of 1:10000 scale are between 44744 and '
                  b'74331 </div>')
EE_NOT_FOUND = (b'<h3 class="w-100">Absolute height (DSM), 1m resolution GeoTIFF</h3><p><span class="fa-solid '
                b'fa-circle-info text-danger" aria-hidden="true"></span> Map sheet not found.</p>')
CY_TILE = (1900, 3725)  # ETRS89_1900_3725 (Kakopetria): E 190 000-192 500, N 372 500-375 000 of LTM
CY_BLOCKS = [(152, 299), (153, 299)]  # its two northern blocks of 1.25 km


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(src.net, "_sleep", lambda attempt: None)


# --- Cyprus: a file in degrees warped onto blocks of LTM ---

def _degree_file(path, pixel=1.0e-5, far=False, invalid=False):
    """A file like DLS's: EPSG:4258, square pixels in degrees, 128 px tiles, LZW, nodata -3.4028e38, over the two
    northern blocks of tile 1900_3725 and 30 m around; a slope with a wall of 20 m (where nearest and bilinear
    differ) and "sea" (nodata) in its south-west corner. far: its overviews and mask after the data (the directories
    beyond the bytes the open fetches, as DLS's files keep their directory at the end). invalid: a patch of -9999 in
    the data (below VALID_MIN, not the file's nodata)."""
    west, south, east, north = transform_bounds(cyprus.CY_LTM, "EPSG:4258", 190_000 - 30, 373_750 - 30,
                                                192_500 + 30, 375_000 + 30)
    width, height = int((east - west) / pixel) + 1, int((north - south) / pixel) + 1
    rows, cols = np.mgrid[0:height, 0:width]
    band = (600 + rows * 0.03 + cols * 0.05 + 20.0 * (cols > width // 2)).astype(np.float32)
    band[height - 200:, :300] = NODATA_CY
    if invalid:
        band[300:304, 400:404] = -9999.0
    profile = dict(driver="GTiff", width=width, height=height, count=1, dtype="float32", crs="EPSG:4258",
                   transform=from_origin(west, north, pixel, pixel), tiled=True, blockxsize=128, blockysize=128,
                   compress="lzw", nodata=NODATA_CY)
    with rio.Env(GDAL_TIFF_INTERNAL_MASK=True), rio.open(path, "w", **profile) as dst:
        dst.write(band, 1)
        if far:
            dst.write_mask(np.where(band == NODATA_CY, 0, 255).astype(np.uint8))
            dst.build_overviews([2, 4])
    return path


def _expected(path, request, resampling):
    """The file warped onto a block's pixels by rasterio's reproject (not the WarpedVRT of the reader), NaN for no
    data."""
    out = np.full(request.shape, np.nan, np.float32)
    with rio.open(path) as f:
        band = f.read(1).astype(np.float32)
        band[(band == NODATA_CY) | (band < -500)] = np.nan  # as the layers clean (sources.layer.VALID_MIN)
        reproject(band, out, src_transform=f.transform, src_crs=f.crs, dst_transform=request.transform,
                  dst_crs=request.crs, src_nodata=np.nan, dst_nodata=np.nan, resampling=resampling)
    return out


@pytest.fixture
def cy_served(http_server, tmp_path, monkeypatch):
    """DTM and DSM tiles 1900_3725 on the local server where the catalogue's layers look for them (CY_DATA)."""
    folder = tmp_path / "rasters"
    (folder / "2019_DTM").mkdir(parents=True)
    (folder / "2019_DSM").mkdir(parents=True)
    _degree_file(folder / "2019_DTM" / "ETRS89_1900_3725.tif")
    _degree_file(folder / "2019_DSM" / "ETRS89_1900_3725.tif", pixel=0.5e-5)
    http_server.add_folder("/rasters", str(folder))
    monkeypatch.setattr(cyprus, "CY_DATA", http_server.url("/rasters"))
    return folder


def test_cyprus_settings():
    """The catalogue's Cyprus: blocks of 1.25 km of LTM on whole metres, the DTM warped by nearest, the DSM by
    average, a tile outside the published ones (the north, the sea) without any file, so no request."""
    s = src.SOURCES["cyprus"]
    assert s.crs == cyprus.CY_LTM == "EPSG:6312" and s.countries == ("cy",) and s.fallbacks == ["europe"]
    assert s.nmt.reader.warp == Resampling.nearest and s.nmpt.reader.warp == Resampling.average
    assert not s.nmt.reader.ranged and s.nmt.folder == "cyprus/dtm/2019" and s.nmpt.folder == "cyprus/dsm/2019"
    request = s.nmt.index.request(CY_BLOCKS[0])
    assert request.files == [("ETRS89_1900_3725", f"{cyprus.CY_DATA}/2019_DTM/ETRS89_1900_3725.tif", 2019)]
    assert request.crs == "EPSG:6312" and request.shape == (1250, 1250)
    assert (request.transform.c, request.transform.f, request.transform.a) == (190_000, 375_000, 1.0)
    north = s.nmt.index.request((int(230_000 // 1250), int(410_000 // 1250)))  # Kyrenia's range, the north
    assert north.files == []
    occupied = s.nmt.index.request((int(190_000 // 1250), int(387_500 // 1250)))  # Morphou, the north: 1900_3875
    assert (1900, 3875) not in cyprus.cy_tiles("DTM") and occupied.files == []
    # the tables as listed: 1 069 DTM tiles (the one-pixel file 2000_3250 left out), 1 068 DSM tiles
    assert len(cyprus.cy_tiles("DTM")) == 1069 and len(cyprus.cy_tiles("DSM")) == 1068
    assert (2000, 3250) not in cyprus.cy_tiles("DTM")
    assert cyprus.cy_tiles("DTM") ^ cyprus.cy_tiles("DSM") == {
        (1350, 3650), (1425, 3475), (1625, 3350), (2025, 3275), (2250, 3400), (2275, 3400), (2000, 3250)}


def test_cyprus_tile_names_by_formula():
    """A tile's name is floor(E / 2500) * 25, floor(N / 2500) * 25 of LTM: Cape Greco and Kakopetria."""
    from pyproj import Transformer
    to_ltm = Transformer.from_crs(4326, 6312, always_xy=True)
    for (lat, lon), name in (((34.963, 34.080), "ETRS89_2975_3700"), ((34.985, 32.900), "ETRS89_1900_3725")):
        e, n = to_ltm.transform(lon, lat)
        files = src.SOURCES["cyprus"].nmt.index.request((int(e // 1250), int(n // 1250))).files
        assert files[0][0] == name


def test_cyprus_warped_block(cy_served, tmp_path):
    """A block of the catalogue's DTM: the file in degrees warped by nearest onto 1 m of LTM, equal to rasterio's
    reproject of the same file; the sea without data. Without warp the same file is refused (another CRS)."""
    layer = src.SOURCES["cyprus"].nmt
    request = layer.index.request(CY_BLOCKS[0])
    path = str(tmp_path / "block.tif")
    layer.download_tile(CY_BLOCKS[0], path)
    expected = _expected(cy_served / "2019_DTM" / "ETRS89_1900_3725.tif", request, Resampling.nearest)
    with rio.open(path) as block:
        values = block.read(1)
        assert block.crs.to_epsg() == 6312 and block.transform == request.transform
        assert block.tags()["sources"] == "ETRS89_1900_3725" and block.tags()["years"] == "2019"
    assert np.isfinite(expected).mean() > 0.9 and np.isnan(expected).any()
    assert np.array_equal(np.isnan(values), np.isnan(expected))
    assert np.allclose(values[np.isfinite(values)], expected[np.isfinite(expected)], atol=0.006)  # LERC's bound
    plain = FileBlocks("no warp", "test/cy", cyprus.CY_LTM, 1.0, 1250, layer.index.files, year=2019)
    with pytest.raises(RuntimeError, match="no file of this block could be read in its CRS"):
        plain.download_tile(CY_BLOCKS[0], str(tmp_path / "plain.tif"))
    assert not os.path.exists(tmp_path / "plain.tif")


def test_cyprus_dsm_averaged(cy_served, tmp_path):
    """The catalogue's DSM: 0.5 m pixels in degrees averaged onto 1 m of LTM (not nearest)."""
    layer = src.SOURCES["cyprus"].nmpt
    request = layer.index.request(CY_BLOCKS[0])
    path = str(tmp_path / "dsm.tif")
    layer.download_tile(CY_BLOCKS[0], path)
    file = cy_served / "2019_DSM" / "ETRS89_1900_3725.tif"
    average, nearest = _expected(file, request, Resampling.average), _expected(file, request, Resampling.nearest)
    with rio.open(path) as block:
        values = block.read(1)
    inside = np.isfinite(values) & np.isfinite(average)
    assert inside.mean() > 0.9
    assert np.allclose(values[inside], average[inside], atol=0.006)
    assert not np.allclose(values[inside], nearest[inside], atol=0.006)


def test_cyprus_average_leaves_out_invalid_values(http_server, tmp_path, monkeypatch):
    """A value below VALID_MIN that is not the file's nodata (-9999 where the nodata is -3.4e38) is no data before the
    average: never averaged into the valid pixels around it (GDAL's warper alone leaves out only the nodata)."""
    folder = tmp_path / "rasters"
    (folder / "2019_DSM").mkdir(parents=True)
    file = _degree_file(folder / "2019_DSM" / "ETRS89_1900_3725.tif", pixel=0.5e-5, invalid=True)
    http_server.add_folder("/rasters", str(folder))
    monkeypatch.setattr(cyprus, "CY_DATA", http_server.url("/rasters"))
    layer = src.SOURCES["cyprus"].nmpt
    request = layer.index.request(CY_BLOCKS[0])
    path = str(tmp_path / "dsm.tif")
    layer.download_tile(CY_BLOCKS[0], path)
    with rio.open(path) as block:
        values = block.read(1)
    expected = _expected(file, request, Resampling.average)
    assert np.nanmin(values) > 500  # nothing of the -9999 patch in any pixel
    assert np.array_equal(np.isnan(values), np.isnan(expected))
    assert np.allclose(values[np.isfinite(values)], expected[np.isfinite(expected)], atol=0.006)


def test_cyprus_group_equals_blocks(cy_served, tmp_path):
    """The country prefetch's group read (each file once over its blocks, our own range requests) gives the blocks
    of the one-by-one read."""
    layer = src.SOURCES["cyprus"].nmt
    requests_ = [layer.index.request(t) for t in CY_BLOCKS]
    results = layer.reader.fetch_group(requests_)
    for tile, (values, tags) in zip(CY_BLOCKS, results):
        path = str(tmp_path / f"{tile[0]}.tif")
        layer.download_tile(tile, path)
        with rio.open(path) as block:
            one = block.read(1)
        assert tags["sources"] == "ETRS89_1900_3725"
        assert np.array_equal(np.isnan(values), np.isnan(one))
        assert np.allclose(values[np.isfinite(values)], one[np.isfinite(one)], atol=0.006)


def test_cyprus_cut_short_never_cached(cy_served, http_server, tmp_path):
    """Every range answer cut short: the block fails after its retries, nothing is written."""
    url_path = "/rasters/2019_DTM/ETRS89_1900_3725.tif"
    http_server.fault(url_path, "truncate", lambda n, r: True)
    rasterio.cache.invalidate(http_server.url(url_path))
    path = tmp_path / "cut.tif"
    with pytest.raises(RuntimeError):
        src.SOURCES["cyprus"].nmt.download_tile(CY_BLOCKS[0], str(path))
    assert not path.exists()
    rasterio.cache.invalidate(http_server.url(url_path))


class _Watchdog:
    """A thread ticking every 10 ms; gap: its longest stand-still (as tests/test_window_gil.py's)."""

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


def test_cyprus_warp_holds_no_gil_for_requests(http_server, tmp_path, monkeypatch):
    """The warp of a remote file whose directories lie beyond the bytes of the open (its mask and overviews after the
    data) makes no HTTP request holding the GIL, also with GDAL's cache of the file dropped right before the warp:
    the in-process server answers, the watchdog never stands still for curl's timeout (5 s here)."""
    folder = tmp_path / "far"
    (folder / "2019_DTM").mkdir(parents=True)
    _degree_file(folder / "2019_DTM" / "ETRS89_1900_3725.tif", far=True)
    http_server.add_folder("/far", str(folder))
    monkeypatch.setattr(cyprus, "CY_DATA", http_server.url("/far"))
    original = windows._gdal_http

    @contextlib.contextmanager
    def short(serial=False):
        with original(serial), rio.Env(GDAL_HTTP_TIMEOUT="5", GDAL_HTTP_MAX_RETRY="0"):
            yield
    monkeypatch.setattr(windows, "_gdal_http", short)
    url = http_server.url("/far/2019_DTM/ETRS89_1900_3725.tif")
    warp = windows._warp_window

    def dropped(*args, **kwargs):
        rasterio.cache.invalidate(url)
        return warp(*args, **kwargs)
    monkeypatch.setattr(windows, "_warp_window", dropped)
    rasterio.cache.invalidate(url)
    with _Watchdog() as watchdog:
        src.SOURCES["cyprus"].nmt.download_tile(CY_BLOCKS[1], str(tmp_path / "far.tif"))
    assert watchdog.gap < 2.5
    assert os.path.exists(tmp_path / "far.tif")


def test_cyprus_probe_window(tmp_path, monkeypatch):
    """The probe's window read warps a file in degrees for a layer with warp (a local file: no request)."""
    folder = tmp_path / "rasters"
    (folder / "2019_DTM").mkdir(parents=True)
    _degree_file(folder / "2019_DTM" / "ETRS89_1900_3725.tif")
    monkeypatch.setattr(cyprus, "CY_DATA", str(folder).replace(os.sep, "/"))
    text = probe._window(str(tmp_path / "cache"), src.SOURCES["cyprus"].nmt, CY_BLOCKS[0])
    assert text == "window 100% with data"


# --- Estonia: sheets behind a PHP address, read by our own ranges ---

def test_estonia_sheet_numbers():
    """The 1:10 000 sheet's number from its corner and back (the tie points of four live sheets), every sheet of the
    table round trip, the 1:2 000 DSM sheets."""
    for sheet, corner in (("64442", (645, 6540)), ("73041", (540, 6600)), ("51681", (380, 6460)),
                          ("63944", (545, 6595)), ("44744", (645, 6375)), ("74331", (630, 6630))):
        assert estonia.ee_corner(sheet) == corner and estonia.ee_sheet(*corner) == sheet
        assert estonia.ee_sheet(corner[0] + 4, corner[1] + 4) == sheet  # any point of its 5 km square
    assert len(estonia.ee_sheets()) == 2073
    assert all(estonia.ee_corner(estonia.ee_sheet(e, n)) == (e, n) for e, n in estonia.ee_sheets())
    assert all(44744 <= int(estonia.ee_sheet(e, n)) <= 74331 for e, n in estonia.ee_sheets())
    for bad in ("6444", "64445", "6444a", "644420"):
        assert estonia.ee_corner(bad) is None
    assert estonia.ee_dsm_sheet(645, 6541) == "541645"
    assert estonia.ee_dsm_sheet(540, 6640) is None  # the gulf: no DTM sheet there, so no request


def test_estonia_settings():
    """The catalogue's Estonia: L-EST97, DTM blocks of 1.25 km read by our own ranges, the URL of a sheet, a block
    outside the sheets without a file; the DSM's 1 km sheets, only TIFFs kept, the sea's page missing."""
    s = src.SOURCES["estonia"]
    assert s.crs == "EPSG:3301" and s.countries == ("ee",) and s.fallbacks == ["europe"]
    assert s.nmt.reader.ranged and s.nmt.reader.warp is None
    assert s.nmt.folder == "estonia/dtm-1m/20260409" and s.nmpt.folder == "estonia/dsm-1m/20260409"
    request = s.nmt.index.request((516, 5235))  # 645 000-646 250 E, 6 543 750-6 545 000 N: sheet 64442
    assert request.files == [("64442", estonia.ee_dtm_url("64442"), 0)] and request.shape == (1250, 1250)
    assert request.files[0][1] == (
        "https://geoportaal.maaruum.ee/index.php?lang_id=2&plugin_act=otsing&kaardiruut=64442&andmetyyp="
        "dem_1m_geotiff&dl=1&f=64442_dtm_1m.tif&page_id=664")
    assert s.nmt.index.request((432, 5312)).files == []  # 540 000 E, 6 640 000 N: the Gulf of Finland
    reader = s.nmpt.reader
    assert reader.tiff_only and "text/html" in reader.binary_types
    assert re.search(reader.not_found, ranges.page_text(EE_NOT_FOUND))
    assert s.nmpt.tile_url((645, 6541)) == (
        "https://geoportaal.maaruum.ee/index.php?lang_id=2&plugin_act=otsing&kaardiruut=541645&andmetyyp="
        "ndsm_abs_1m_geotiff&dl=1&f=541645_dsm_1m.tif&page_id=664")
    assert s.nmpt.tile_url((540, 6640)) is None
    assert s.nmpt.download_tile((540, 6640), "unused.tif").received == 0  # no request (none could be answered)


def _sheet_file(path, left=645_000.0, top=6_545_000.0, size=2500):
    """A DTM sheet like the Board's (EPSG:3301, 1 m, 512 px tiles, DEFLATE with the float predictor, nodata -9999),
    smaller (size px)."""
    rows, cols = np.mgrid[0:size, 0:size]
    band = (20 + rows * 0.011 + cols * 0.007 + 15.0 * ((cols // 300) % 2)).astype(np.float32)
    band[:40, :60] = -9999.0
    with rio.open(path, "w", driver="GTiff", width=size, height=size, count=1, dtype="float32", crs="EPSG:3301",
                  transform=from_origin(left, top, 1.0, 1.0), tiled=True, blockxsize=512, blockysize=512,
                  compress="deflate", predictor=3, nodata=-9999.0) as dst:
        dst.write(band, 1)
    return np.where(band == -9999.0, np.nan, band)


def _ee_path(sheet, kind, model):
    return (f"/index.php?lang_id=2&plugin_act=otsing&kaardiruut={sheet}&andmetyyp={kind}&dl=1"
            f"&f={sheet}_{model}_1m.tif&page_id=664")


@pytest.fixture
def ee_served(http_server, tmp_path, monkeypatch):
    """Sheet 64442 (its upper-left 2.5 km) at its PHP address on the local server (EE_URL's host patched)."""
    band = _sheet_file(tmp_path / "64442.tif")
    http_server.add(_ee_path("64442", "dem_1m_geotiff", "dtm"), (tmp_path / "64442.tif").read_bytes(), "image/tiff")
    monkeypatch.setattr(estonia, "EE_URL", estonia.EE_URL.replace("https://geoportaal.maaruum.ee",
                                                                   http_server.base))
    return band


def test_estonia_ranged_block(ee_served, http_server, tmp_path):
    """A block of the catalogue's DTM through the PHP address: our own range requests (every one with a Range and our
    User-Agent, no HEAD: never GDAL's /vsicurl/, which refuses the address), its values as the sheet's."""
    path = str(tmp_path / "block.tif")
    src.SOURCES["estonia"].nmt.download_tile((516, 5235), path)
    with rio.open(path) as block:
        values = block.read(1)
        assert block.crs.to_epsg() == 3301 and (block.transform.c, block.transform.f) == (645_000, 6_545_000)
        assert block.tags()["sources"] == "64442"
    expected = ee_served[:1250, :1250]
    assert np.array_equal(np.isnan(values), np.isnan(expected))
    assert np.allclose(values[np.isfinite(values)], expected[np.isfinite(expected)], atol=0.006)
    asked = http_server.requests("/index.php")
    assert asked and all(r.method == "GET" and "range" in r.headers for r in asked)
    assert all(r.user_agent == cache.http_headers()["User-Agent"] for r in asked)


def test_estonia_ranged_group(ee_served, http_server):
    """The group read of two blocks of one sheet equals the sheet's pixels."""
    layer = src.SOURCES["estonia"].nmt
    (first, tags), (second, _) = layer.reader.fetch_group([layer.index.request((516, 5235)),
                                                            layer.index.request((517, 5235))])
    assert tags["sources"] == "64442"
    for values, expected in ((first, ee_served[:1250, :1250]), (second, ee_served[:1250, 1250:2500])):
        assert np.array_equal(np.isnan(values), np.isnan(expected))
        assert np.array_equal(values[np.isfinite(values)], expected[np.isfinite(expected)])


def test_estonia_ranged_block_in_strips(ee_served, http_server, tmp_path, monkeypatch):
    """A block of the catalogue's DTM read in strips with prefetch (windows._ranged_values, since 2026-11-24) gives
    the values of the reader before it (GDAL's reads through our ranges), of GDAL's /vsicurl/ reading the same bytes
    at a .tif address (all written as cached tiles); two blocks of the sheet, one with its nodata corner."""
    from sources.readers import windows
    layer = src.SOURCES["estonia"].nmt
    http_server.add("/ee/64442.tif", (tmp_path / "64442.tif").read_bytes(), "image/tiff")
    strips = windows._ranged_values
    for tile, expected in (((516, 5235), ee_served[:1250, :1250]), ((517, 5235), ee_served[:1250, 1250:2500])):
        request = layer.index.request(tile)
        found = {}
        for name in ("strips", "before", "gdal"):
            monkeypatch.setattr(windows, "_ranged_values", strips if name != "before" else (
                lambda s, f, crs, t, shape, warp=None: windows._values_on(s, crs, t, shape, warp)))
            files = [("64442", http_server.url("/ee/64442.tif"), 0)] if name == "gdal" else request.files
            out = str(tmp_path / f"{name}.tif")
            windows._read_block(files, request.crs, request.transform, request.shape, out, "test",
                                ranged=name != "gdal")
            with rio.open(out) as block:
                found[name] = block.read(1)
        for name, values in found.items():
            assert np.array_equal(values, found["gdal"], equal_nan=True), (tile, name)
        assert np.array_equal(np.isnan(found["strips"]), np.isnan(expected))


def test_estonia_error_page_as_206_never_cached(http_server, tmp_path, monkeypatch):
    """The address's error page with HTTP 206 and its own Content-Range: not a TIFF, an error naming the page's text,
    nothing written; also through the group read and the probe's window."""
    http_server.add(_ee_path("64442", "dem_1m_geotiff", "dtm"), EE_RANGE_ERROR, "text/html;charset=utf-8",
                    status=206, headers={"Content-Range": f"bytes 0-{len(EE_RANGE_ERROR) - 1}/{len(EE_RANGE_ERROR)}"})
    monkeypatch.setattr(estonia, "EE_URL", estonia.EE_URL.replace("https://geoportaal.maaruum.ee",
                                                                   http_server.base))
    layer = src.SOURCES["estonia"].nmt
    path = tmp_path / "error.tif"
    with pytest.raises(RuntimeError, match="not a TIFF.*map sheet numbers of 1:10000 scale"):
        layer.download_tile((516, 5235), str(path))
    assert not path.exists()
    with pytest.raises(RuntimeError, match="not a TIFF"):
        layer.reader.fetch_group([layer.index.request((516, 5235))])
    with pytest.raises(RuntimeError, match="not a TIFF"):
        probe._window(str(tmp_path / "cache"), layer, (516, 5235))


def test_estonia_file_in_another_crs(http_server, tmp_path, monkeypatch):
    """A sheet at the PHP address in another CRS than L-EST97: never used by the ranged read (WrongCrs), the block
    fails rather than being missing, alone and in a group; nothing written."""
    rows, cols = np.mgrid[0:1300, 0:1300]
    with rio.open(tmp_path / "utm.tif", "w", driver="GTiff", width=1300, height=1300, count=1, dtype="float32",
                  crs="EPSG:32635", transform=from_origin(645_000.0, 6_545_000.0, 1.0, 1.0), tiled=True,
                  blockxsize=512, blockysize=512, compress="deflate") as dst:
        dst.write((20 + rows * 0.01 + cols * 0.01).astype(np.float32), 1)
    http_server.add(_ee_path("64442", "dem_1m_geotiff", "dtm"), (tmp_path / "utm.tif").read_bytes(), "image/tiff")
    monkeypatch.setattr(estonia, "EE_URL", estonia.EE_URL.replace("https://geoportaal.maaruum.ee",
                                                                   http_server.base))
    layer = src.SOURCES["estonia"].nmt
    path = tmp_path / "block.tif"
    with pytest.raises(RuntimeError, match="64442 is in EPSG:32635, not EPSG:3301; no file of this block"):
        layer.download_tile((516, 5235), str(path))
    assert not path.exists()
    with pytest.raises(RuntimeError, match="could be read in its CRS"):
        layer.reader.fetch_group([layer.index.request((516, 5235))])


def test_range_answer_wider_than_asked_never_read(http_server, monkeypatch):
    """A 206 whose Content-Range claims more than the range asked (50 MB for 64 KB): closed unread every time, then
    an error; none of its body read."""
    body = bytes(2_000_000)

    def wide(request):
        return Answer(206, body, {"Content-Type": "image/tiff", "Content-Range": "bytes 0-52428799/52428800"})
    http_server.route("/wide", wide)
    read = []
    original = requests.models.Response.iter_content

    def counting(self, *args, **kwargs):
        for chunk in original(self, *args, **kwargs):
            read.append(len(chunk))
            yield chunk
    monkeypatch.setattr(requests.models.Response, "iter_content", counting)
    with pytest.raises(RuntimeError, match="0-52428799/52428800 \\(not read\\)"):
        ranges.get_range(http_server.url("/wide"), 0, ranges.CHUNK - 1)
    assert sum(read) == 0 and len(http_server.requests("/wide")) == src.net.RETRIES


def test_check_source_reads_ranged_files(ee_served, http_server):
    """tools/check_source.py reads a ranged layer's file through our own ranges (the PHP address is no .tif for
    /vsicurl/): the sheet's pixels on a cached tile's grid."""
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
    import check_source as cs
    url = estonia.ee_dtm_url("64442")
    profile = {"crs": rio.crs.CRS.from_epsg(3301), "transform": from_origin(646_250.0, 6_545_000.0, 1.0, 1.0),
               "width": 300, "height": 200}
    values = cs._read_ranged(url, profile)
    expected = ee_served[:200, 1250:1550]
    assert np.array_equal(np.isnan(values), np.isnan(expected))
    assert np.array_equal(values[np.isfinite(values)], expected[np.isfinite(expected)])
    assert all("range" in r.headers for r in http_server.requests("/index.php"))


def test_check_source_compares_with_the_layers_warp(cy_served, tmp_path, monkeypatch):
    """check_source's file check takes a warping layer's own resampling: Cyprus' averaged DSM blocks equal their
    file averaged (PASS), and would not equal it by nearest (WARN)."""
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
    import check_source as cs
    import grid as gd
    monkeypatch.setattr(src.layer, "DOWNLOAD_THREADS", 1)
    layer = src.SOURCES["cyprus"].nmpt
    grid = gd.make_grid((190_100, 374_000, 190_900, 374_900), 1.0, cyprus.CY_LTM)
    cache_dir = str(tmp_path / "cache")
    layer.download(grid, cache_dir, None, "test")
    check = cs.check_files(layer, grid, cache_dir, 2)
    assert check["status"] == cs.PASS, check["text"]
    monkeypatch.setattr(layer.reader, "warp", Resampling.nearest)
    assert cs.check_files(layer, grid, cache_dir, 2)["status"] == cs.WARN


def test_estonia_whole_file_for_a_range_never_read(http_server, tmp_path, monkeypatch):
    """A server answering the Range with the whole file (HTTP 200): closed unread every time (none of its body
    read), then an error; nothing written."""
    band = _sheet_file(tmp_path / "64442.tif")
    body = (tmp_path / "64442.tif").read_bytes()
    assert len(body) > 400_000 and np.isfinite(band).any()
    http_server.answers[key_of("GET", _ee_path("64442", "dem_1m_geotiff", "dtm"))] = \
        Answer(200, body, {"Content-Type": "image/tiff"}, ranges=False)
    monkeypatch.setattr(estonia, "EE_URL", estonia.EE_URL.replace("https://geoportaal.maaruum.ee",
                                                                   http_server.base))
    read = []
    original = requests.models.Response.iter_content

    def counting(self, *args, **kwargs):
        for chunk in original(self, *args, **kwargs):
            read.append(len(chunk))
            yield chunk
    monkeypatch.setattr(requests.models.Response, "iter_content", counting)
    path = tmp_path / "whole.tif"
    with pytest.raises(RuntimeError, match="whole file"):
        src.SOURCES["estonia"].nmt.download_tile((516, 5235), str(path))
    assert not path.exists() and sum(read) == 0
    # the file's first request: opening it, OPEN_RETRIES + 1 attempts (the user's decision of 2026-11-24)
    assert len(http_server.requests("/index.php")) == src.net.OPEN_RETRIES + 1


@pytest.mark.parametrize("every", [False, True])
def test_estonia_cut_short(ee_served, http_server, tmp_path, every):
    """A range answer cut short is asked again (the block as the sheet's); cut short every time, the block fails and
    nothing is written."""
    cut = []
    http_server.fault("/index.php", "truncate", lambda n, r: every or (not cut and not cut.append(n)))
    path = tmp_path / "cut.tif"
    if every:
        with pytest.raises(RuntimeError):
            src.SOURCES["estonia"].nmt.download_tile((516, 5235), str(path))
        assert not path.exists()
        return
    src.SOURCES["estonia"].nmt.download_tile((516, 5235), str(path))
    with rio.open(path) as block:
        values = block.read(1)
    assert cut and np.allclose(values[np.isfinite(values)], ee_served[:1250, :1250][np.isfinite(values)], atol=0.006)


def test_estonia_missing_sheet(http_server, tmp_path, monkeypatch):
    """A sheet the server does not have (404): the block is missing, no file, no error."""
    monkeypatch.setattr(estonia, "EE_URL", estonia.EE_URL.replace("https://geoportaal.maaruum.ee",
                                                                   http_server.base))
    fetched = src.SOURCES["estonia"].nmt.download_tile((516, 5235), str(tmp_path / "none.tif"))
    assert fetched.received == 0 and not (tmp_path / "none.tif").exists()


def test_estonia_probe_window(ee_served, tmp_path):
    """The probe reads a window of a block through our own ranges."""
    text = probe._window(str(tmp_path / "cache"), src.SOURCES["estonia"].nmt, (517, 5235))
    assert text.startswith("window ") and text.endswith("% with data")


def _dsm_sheet(path, left=645_000.0, bottom=6_541_000.0):
    """A DSM sheet like the Board's: 1000 x 1000 float32, uncompressed strips of 2 rows, no nodata, the sea at -0.2."""
    band = np.full((1000, 1000), -0.2, np.float32)
    band[:, 400:] = 12.5 + np.arange(600, dtype=np.float32) * 0.01
    with rio.open(path, "w", driver="GTiff", width=1000, height=1000, count=1, dtype="float32", crs="EPSG:3301",
                  transform=from_origin(left, bottom + 1000, 1.0, 1.0), blockysize=2) as dst:
        dst.write(band, 1)
    return band


def test_estonia_dsm_sheets(http_server, tmp_path, monkeypatch):
    """The catalogue's DSM: a sheet downloaded whole and written as the cache's tile; the sea's "Map sheet not found."
    page (HTTP 200) missing after one request; another page an error after the retries, never cached."""
    monkeypatch.setattr(estonia, "EE_URL", estonia.EE_URL.replace("https://geoportaal.maaruum.ee",
                                                                   http_server.base))
    band = _dsm_sheet(tmp_path / "541645.tif")
    http_server.add(_ee_path("541645", "ndsm_abs_1m_geotiff", "dsm"), (tmp_path / "541645.tif").read_bytes(),
                    "image/tiff")
    http_server.add(_ee_path("541646", "ndsm_abs_1m_geotiff", "dsm"), EE_NOT_FOUND, "text/html;charset=utf-8")
    http_server.add(_ee_path("541647", "ndsm_abs_1m_geotiff", "dsm"), b"<html>Service unavailable</html>",
                    "text/html;charset=utf-8")
    layer = src.SOURCES["estonia"].nmpt
    path = tmp_path / "cache" / "dsm.tif"
    layer.download_tile((645, 6541), str(path))
    with rio.open(path) as tile:
        assert tile.crs.to_epsg() == 3301 and (tile.transform.c, tile.transform.f) == (645_000, 6_542_000)
        assert np.allclose(tile.read(1), band, atol=0.006)
    fetched = layer.download_tile((646, 6541), str(tmp_path / "sea.tif"))
    assert fetched.received == 0 and not (tmp_path / "sea.tif").exists()
    assert len(http_server.requests("/index.php")) == 2
    with pytest.raises(RuntimeError, match="not a TIFF: Service unavailable"):
        layer.download_tile((647, 6541), str(tmp_path / "error.tif"))
    assert not (tmp_path / "error.tif").exists()
    assert len(http_server.requests("/index.php")) == 2 + src.net.RETRIES


def test_estonia_dsm_probe(http_server, tmp_path, monkeypatch):
    """The probe's sheet kind for the DSM: the first 8 bytes must be a TIFF's; the sea's page fails."""
    monkeypatch.setattr(estonia, "EE_URL", estonia.EE_URL.replace("https://geoportaal.maaruum.ee",
                                                                   http_server.base))
    assert probe.strategy(src.SOURCES["estonia"].nmpt) == "sheet"
    _dsm_sheet(tmp_path / "541645.tif")
    http_server.add(_ee_path("541645", "ndsm_abs_1m_geotiff", "dsm"), (tmp_path / "541645.tif").read_bytes(),
                    "image/tiff")
    http_server.add(_ee_path("541646", "ndsm_abs_1m_geotiff", "dsm"), EE_NOT_FOUND, "text/html;charset=utf-8")
    layer = src.SOURCES["estonia"].nmpt
    assert probe._tiff_head(str(tmp_path), layer.tile_url((645, 6541))) == ""
    with pytest.raises(RuntimeError, match="not a TIFF"):
        probe._tiff_head(str(tmp_path), layer.tile_url((646, 6541)))


def test_download_tiff_only_leaves_other_layers_alone(http_server, tmp_path):
    """Download without tiff_only keeps a non-raster answer as it came (NASADEM's integer files, the water mask):
    the option changes nothing for the other layers."""
    from sources.readers.download import Download
    http_server.add("/x.bin", b"not a raster", "application/octet-stream")
    reader = Download("test", lambda t: http_server.url("/x.bin"), lambda t: "x")
    reader.fetch(None, str(tmp_path / "x.tif"))
    assert (tmp_path / "x.tif").read_bytes() == b"not a raster"
