"""The parts of an Esri elevation tile cache (LercTiles: MercatorTiling + LercTileReader, TileCells, the mask tool
tools/lerc_coverage.py) against recorded tiles of both services (tests/data/recorded/lerc/) and a fake tile server,
and the catalogue's two sources on it (Northern Ireland's 2021 coastal DTM, Rio de Janeiro's 5 m DTM)."""

import http.server
import json
import math
import os
import sys
import threading

import numpy as np
import pytest
import rasterio as rio
from rasterio.warp import transform

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "tools"))

import sources as src  # noqa: E402
import cache  # noqa: E402
from grid import make_grid  # noqa: E402
from http_server import Answer  # noqa: E402
from sources import choose, net, probe  # noqa: E402
from sources.catalogue import brazil, uk  # noqa: E402
from sources.indexes.mercator import MercatorTiling, TileCells, level_for, tile_box, tile_pixels  # noqa: E402
from sources.readers import lerc  # noqa: E402
import lerc_coverage  # noqa: E402

RECORDED = os.path.join(HERE, "tests", "data", "recorded", "lerc")
NI, RJ = "northern-ireland", "rio-de-janeiro"


def _recorded(case: str, tile) -> bytes:
    with open(os.path.join(RECORDED, case, "{}_{}_{}.lerc".format(*tile)), "rb") as f:
        return f.read()


def _expected():
    with open(os.path.join(RECORDED, "expected.json"), encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    sleeps = []
    monkeypatch.setattr(src.net, "_sleep", lambda attempt: sleeps.append(attempt))
    return sleeps


# --- decoding and the tiles' geometry ---

def test_recorded_tiles_decode_as_read_live():
    """Every recorded tile decodes to 257 x 257 float32 samples with the values decoded when it was read live
    (2026-11-15; the coordinator's check of the same services: Fair Head's tile up to 162.0 m, Pão de Açúcar's 392.0
    m); the LERC mask's invalid samples are NaN, valid zeros stay (Rio's shore), the 70-byte tile has none."""
    for name, want in _expected().items():
        case, file = name.split("/")
        tile = tuple(int(v) for v in file[:-5].split("_"))
        data = _recorded(case, tile)
        assert len(data) == want["bytes"] and data.startswith(lerc.LERC1_MAGIC)
        samples = lerc.decode(data)
        assert samples.shape == (257, 257) and samples.dtype == np.float32
        valid = samples[np.isfinite(samples)]
        assert valid.size == want["valid"] and int((valid == 0).sum()) == want["zeros"], name
        if valid.size:
            assert valid.min() == pytest.approx(want["min"], abs=1e-3)
            assert valid.max() == pytest.approx(want["max"], abs=1e-3)
        for key, value in want["samples"].items():
            r, c = (int(v) for v in key.split(","))
            assert (value is None and np.isnan(samples[r, c])) or samples[r, c] == pytest.approx(value, abs=1e-4)
    assert np.isnan(lerc.decode(_recorded(NI, (17, 41712, 63376)))).all()  # the sea: 70 bytes, no valid sample


def test_the_last_row_and_column_are_the_neighbours_first():
    """257 corner samples: a tile's last column is its east neighbour's first and its last row its south
    neighbour's first, within the LERC tolerance of both (lercError 0.05 m in Rio: 0.2 m at most, 0.04 m on
    average), while the next column differs by metres on Pão de Açúcar's slope (so not a shifted copy)."""
    tile, east, south = (lerc.decode(_recorded(RJ, t)) for t in ((15, 18531, 12455), (15, 18531, 12456),
                                                                  (15, 18532, 12455)))
    for last, first, second in ((tile[:, -1], east[:, 0], east[:, 1]), (tile[-1, :], south[0, :], south[1, :])):
        both = np.isfinite(last) & np.isfinite(first) & np.isfinite(second)
        assert both.sum() > 100
        shared = np.abs(last[both] - first[both])
        assert shared.max() <= 0.21 and shared.mean() < 0.05
        assert np.mean(np.abs(last[both] - second[both])) > 10 * shared.mean()
    ni, ni_east = lerc.decode(_recorded(NI, (17, 41315, 63294))), lerc.decode(_recorded(NI, (17, 41315, 63295)))
    both = np.isfinite(ni[:, -1]) & np.isfinite(ni_east[:, 0])
    assert both.sum() > 50 and np.abs(ni[both, -1] - ni_east[both, 0]).max() <= 0.2 + 1e-3  # lercError 0.1


def test_tile_transform_and_level():
    """A sample is a pixel centre: the grid starts half a cell west and north of the tile's corner; levels by the
    ground size of a cell (Web Mercator's metres times the cosine of the latitude)."""
    res = lerc.resolution(17)
    assert res == pytest.approx(1.19432856685505, rel=1e-9)  # the services' LOD 17
    assert lerc.resolution(15) == pytest.approx(4.77731426794937, rel=1e-9)
    t = lerc.tile_transform(17, 41315, 63294)
    left, bottom, right, top = tile_box(17, 41315, 63294)
    assert (t.c, t.f) == pytest.approx((left - res / 2, top + res / 2), abs=1e-6)
    assert t @ (0.5, 0.5) == pytest.approx((left, top), abs=1e-6)  # the first sample on the corner
    assert t @ (256.5, 256.5) == pytest.approx((right, bottom), abs=1e-6)  # the 257th on the opposite corner
    assert level_for(1.0, 55.0, 19) == 17 and level_for(5.0, 55.0, 19) == 15 and level_for(30.0, 55.0, 19) == 12
    assert level_for(0.25, 55.0, 19) == 19 and level_for(0.1, 55.0, 19) == 19
    assert level_for(5.0, -22.95, 15) == 15 and level_for(1.0, -22.95, 15) == 15 and level_for(10.0, -22.95, 15) == 14


def test_broken_blobs_are_errors():
    good = _recorded(RJ, (15, 18531, 12455))
    with pytest.raises(ValueError, match="not a LERC1"):
        lerc.decode(b"<html>Page Not Found</html>")
    with pytest.raises(ValueError):
        lerc.decode(good[:len(good) // 2])  # cut short
    with pytest.raises(ValueError, match="257 x 257"):
        lerc.decode(_synthetic_blob(np.zeros((65, 65), np.float32)))


# --- a fake tile cache ---

L, ROW, COL = 15, 18531, 12455      # Rio's tiles around Pão de Açúcar


def _f(x, y):
    """A plane of heights over Web Mercator (metres), about 100-200 m over the fake tiles."""
    x0, y0 = tile_box(L, ROW, COL)[0], tile_box(L, ROW, COL)[3]
    return 150.0 + 0.01 * (x - x0) - 0.02 * (y - y0)


def _synthetic_blob(samples: np.ndarray, precision: float = 0.001) -> bytes:
    """A LERC1 blob of the samples (NaN: invalid) written by GDAL's MRF driver, as Esri's caches hold them."""
    import tempfile
    with tempfile.TemporaryDirectory() as folder:
        path = os.path.join(folder, "t.mrf")
        h, w = samples.shape
        with rio.open(path, "w", driver="MRF", width=w, height=h, count=1, dtype="float32", compress="LERC",
                      blockxsize=w, blockysize=h, nodata=-9999, OPTIONS="V1:1", LERC_PREC=precision) as dst:
            dst.write(np.where(np.isfinite(samples), samples, -9999).astype(np.float32), 1)
        with open(os.path.join(folder, "t.lrc"), "rb") as f:
            return f.read()


def _plane_tile(level, row, col, holes: bool = False) -> bytes:
    t = lerc.tile_transform(level, row, col)
    rows, cols = np.mgrid[0:257, 0:257]
    x, y = t @ (cols + 0.5, rows + 0.5)
    samples = _f(x, y).astype(np.float32)
    if holes:
        samples[200:, :60] = np.nan  # the sea of this tile: invalid samples
    return _synthetic_blob(samples)


def _service(server, tiles, path="/svc"):
    """A tile cache at path answering tile/{level}/{row}/{col} from `tiles` ({tile: body}), 404 otherwise."""
    def answer(request):
        parts = request.path[len(path) + len("/tile/"):].split("/")
        body = tiles.get(tuple(int(p) for p in parts)) if len(parts) == 3 and all(p.isdigit() for p in parts) else None
        if body is None:
            return Answer(404, b"<html>Page Not Found</html>", {"Content-Type": "text/html"})
        return Answer(200, body, {"Content-Type": "image/lerc", "ETag": '"abc"'}, ranges=False)
    server.route(f"{path}/tile/", answer)
    return server.url(path)


def _layer(url, **kw):
    return src.LercTiles("Fake LERC DTM", url, "fake/lerc/live", native_res=5.0, max_level=L, **kw)


def _mercator_grid(tiles_wide=2, tiles_high=2):
    """A grid of EPSG:3857 on the samples of level L (pixel edges half a cell off the tiles' corners), over the
    tiles from (ROW, COL)."""
    res = lerc.resolution(L)
    left, _, _, top = tile_box(L, ROW, COL)
    origin = ((left - res / 2) % res, (top + res / 2) % res)
    size = 256 * res
    inset = res / 4  # make_grid snaps outwards: a quarter pixel inside keeps float noise from adding a pixel
    bounds = (left - res / 2 + inset, top + res / 2 - tiles_high * size + inset,
              left - res / 2 + tiles_wide * size - inset, top + res / 2 - inset)
    grid = make_grid(bounds, res, "EPSG:3857", origin)
    assert (grid.width, grid.height) == (256 * tiles_wide, 256 * tiles_high)
    return grid


def test_tiles_on_their_samples_and_stitched(http_server, tmp_path):
    """Four tiles of a plane cached on their own samples (256 x 256 px, the shared last row and column dropped):
    stitched on a grid of their samples they give the plane everywhere, the seams too; the invalid samples are
    NaN; a tile the cache lacks (404) is missing; no request carries a Range; every one our User-Agent."""
    tiles = {(L, ROW + r, COL + c): _plane_tile(L, ROW + r, COL + c, holes=(r, c) == (1, 0))
             for r in (0, 1) for c in (0, 1)}
    layer = _layer(_service(http_server, tiles))
    grid = _mercator_grid(3, 2)  # a third column of tiles the cache lacks
    cache_dir = str(tmp_path / "cache")
    assert layer.tiles(grid) == sorted((L, ROW + r, COL + c) for r in (0, 1) for c in (0, 1, 2))
    out = src.prepare_layer(layer, grid, cache_dir, str(tmp_path / "work" / "dtm.npy"), "terrain")
    mosaic = np.load(out)
    rows, cols = np.mgrid[0:grid.height, 0:grid.width]
    x, y = grid.transform @ (cols + 0.5, rows + 0.5)
    want = _f(x, y)
    covered = np.zeros_like(mosaic, dtype=bool)
    covered[:, :512] = True
    hole = np.zeros_like(covered)
    hole[256 + 200:512, :60] = True
    assert np.isnan(mosaic[~covered | hole]).all()
    assert np.abs(mosaic[covered & ~hole] - want[covered & ~hole]).max() < 0.01  # LERC 1 mm + our 5 mm
    with rio.open(layer.tile_path(cache_dir, (L, ROW, COL))) as cached:
        assert cached.shape == (256, 256) and cached.crs.to_string() == "EPSG:3857"
        # Written out: tile 15/18531/12455's north-west corner (the slippy-map formula, in Web Mercator) less half a
        # cell of 4.7773 m, so the first sample is the centre of the first pixel
        n = 2 ** L
        lon, lat = COL / n * 360 - 180, math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * ROW / n))))
        (cx,), (cy,) = transform("EPSG:4326", "EPSG:3857", [lon], [lat])
        assert (cx - 4.777314267822981 / 2, cy + 4.777314267822981 / 2) == pytest.approx(
            (-4805139.734775916, -2625762.4069949463), abs=1e-3)
        t = cached.transform
        assert (t.a, t.e, t.c, t.f) == pytest.approx((4.777314267822981, -4.777314267822981, -4805139.734775916,
                                                      -2625762.4069949463), abs=1e-6)
    states = cache.states(cache_dir, [layer.tile_path(cache_dir, t) for t in layer.tiles(grid)])
    assert states.count("missing") == 2 and states.count("ok") == 4
    asked = http_server.requests("/svc/")
    assert len(asked) == 6 and not any("range" in r.headers for r in asked)
    assert all(r.user_agent and r.user_agent.startswith("Find-a-Line") for r in asked)


def test_reprojected_onto_a_metric_grid(http_server, tmp_path):
    """The plane reprojected onto SIRGAS 2000 / UTM 23S at 5 m (the mosaic's one resampling, bilinear): within a
    few centimetres everywhere, also along the seams, where a bilinear warp of one tile takes the outer half
    sample from that tile alone (the slope times half a cell at most)."""
    tiles = {(L, ROW + r, COL + c): _plane_tile(L, ROW + r, COL + c) for r in (0, 1) for c in (0, 1)}
    layer = _layer(_service(http_server, tiles))
    left, bottom, right, top = tile_box(L, ROW + 1, COL)[0], tile_box(L, ROW + 1, COL)[1], \
        tile_box(L, ROW, COL + 1)[2], tile_box(L, ROW, COL)[3]
    inset = 300  # metres of Web Mercator inside the four tiles
    (w, e), (s, n) = transform("EPSG:3857", "EPSG:31983", [left + inset, right - inset], [bottom + inset, top - inset])
    grid = make_grid((w, s, e, n), 5.0, "EPSG:31983")
    out = src.prepare_layer(layer, grid, str(tmp_path / "cache"), str(tmp_path / "work" / "dtm.npy"), "terrain")
    mosaic = np.load(out)
    rows, cols = np.mgrid[0:grid.height, 0:grid.width]
    gx, gy = grid.transform @ (cols + 0.5, rows + 0.5)
    mx, my = transform("EPSG:31983", "EPSG:3857", gx.ravel(), gy.ravel())
    want = _f(np.array(mx), np.array(my)).reshape(mosaic.shape)
    assert np.isfinite(mosaic).all()
    error = np.abs(mosaic - want)
    slope = math.hypot(0.01, 0.02)
    assert error.max() < slope * lerc.resolution(L) / 2 + 0.01
    assert np.median(error) < 0.01


def test_floor_and_valid_zeros(http_server, tmp_path):
    """Rio's tile with sea artefacts (down to -348 m): below the floor no data; its valid zeros stay heights."""
    tile = (15, 18536, 12444)
    layer = _layer(_service(http_server, {tile: _recorded(RJ, tile)}), floor=-5.0)
    path = str(tmp_path / "t.tif")
    fetched = layer.download_tile(tile, path)
    assert fetched.received == len(_recorded(RJ, tile)) and fetched.etag == '"abc"'
    with rio.open(path) as cached:
        band = cached.read(1)
    samples = lerc.decode(_recorded(RJ, tile))[:256, :256]
    assert np.nanmin(band) >= -5.0 and np.nanmin(samples) < -300
    assert np.isnan(band[samples < -5]).all()
    zeros = (samples == 0)
    assert zeros.any() and (band[zeros] == 0).all()


def test_a_tile_without_data_is_missing(http_server, tmp_path):
    tile = (17, 41712, 63376)
    layer = _layer(_service(http_server, {tile: _recorded(NI, tile)}))
    path = str(tmp_path / "t.tif")
    assert layer.download_tile(tile, path).received == 0 and not os.path.exists(path)
    assert layer.download_tile((17, 1, 1), path).received == 0 and not os.path.exists(path)  # 404


def test_faults_are_asked_again_then_errors(http_server, tmp_path, no_sleep):
    """A 5xx, an HTML page with 200, an answer over the byte cap and a blob cut short are asked again
    (net.RETRIES) and then raise; a 429 waits longer; one bad answer followed by a good one is a tile."""
    good = _recorded(RJ, (15, 18531, 12455))
    plan = {"n": 0, "answers": []}

    def answer(request):
        plan["n"] += 1
        status, body, kind = plan["answers"][min(plan["n"], len(plan["answers"])) - 1]
        return Answer(status, body, {"Content-Type": kind}, ranges=False)
    http_server.route("/svc/tile/", answer)
    layer = _layer(http_server.url("/svc"))
    path = str(tmp_path / "t.tif")
    tile = (15, 18531, 12455)
    cases = [
        ([(500, b'{"error":"Internal"}', "application/json")], "HTTP 500"),
        ([(200, b"<html>busy</html>", "text/html")], "not a LERC1 tile"),
        ([(200, lerc.LERC1_MAGIC + bytes(lerc.TILE_BYTES_MAX + 10), "image/lerc")], "more than"),
        ([(200, good[:len(good) // 2], "image/lerc")], "not decoded"),
    ]
    for answers, message in cases:
        plan.update(n=0, answers=answers)
        no_sleep.clear()
        with pytest.raises(RuntimeError, match=message):
            layer.download_tile(tile, path)
        assert plan["n"] == net.RETRIES and not os.path.exists(path)
    plan.update(n=0, answers=[(429, b"slow down", "text/plain")])
    no_sleep.clear()
    with pytest.raises(RuntimeError, match="HTTP 429"):
        layer.download_tile(tile, path)
    assert no_sleep == [3, 4, 5]
    plan.update(n=0, answers=[(503, b"busy", "text/plain"), (200, good, "image/lerc")])
    assert layer.download_tile(tile, path).received == len(good) and os.path.exists(path)


class _CutShort(http.server.BaseHTTPRequestHandler):
    """Promises the whole tile (Content-Length), sends half, closes: an answer cut short in transit."""
    body = b""
    asked = 0

    def do_GET(self):
        type(self).asked += 1
        self.send_response(200)
        self.send_header("Content-Type", "image/lerc")
        self.send_header("Content-Length", str(len(self.body)))
        self.end_headers()
        self.wfile.write(self.body[:len(self.body) // 2])
        self.wfile.flush()
        self.close_connection = True

    def log_message(self, *args):
        pass


def test_an_answer_cut_short_in_transit(tmp_path, monkeypatch):
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    _CutShort.body, _CutShort.asked = _recorded(RJ, (15, 18531, 12455)), 0
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _CutShort)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    thread.start()
    try:
        layer = _layer(f"http://127.0.0.1:{server.server_address[1]}/svc")
        with pytest.raises(RuntimeError, match="Could not download"):
            layer.download_tile((15, 18531, 12455), str(tmp_path / "t.tif"))
        assert _CutShort.asked == net.RETRIES and not os.path.exists(tmp_path / "t.tif")
    finally:
        server.shutdown()
        server.server_close()


# --- the tiling and the mask ---

def _mask_file(tmp_path, cells, level=13, per_tile=8, origin=(100, 200), shape=(16, 16)):
    mask = np.zeros(shape, dtype=bool)
    for r, c in cells:
        mask[r, c] = True
    path = str(tmp_path / "cells.npz")
    lerc_coverage.save(path, mask, level, per_tile, origin)
    return path, mask


def test_tile_cells_and_has_data_near(tmp_path):
    """TileCells reads the tool's file: a cell's box in Web Mercator; near() measures metres on the ground."""
    path, _ = _mask_file(tmp_path, [(5, 7)])
    cells = TileCells(path)
    cell = 256 * lerc.resolution(13) / 8
    x0, y0 = -lerc.ORIGIN + 100 * 256 * lerc.resolution(13), lerc.ORIGIN - 200 * 256 * lerc.resolution(13)
    centre = (x0 + 7.5 * cell, y0 - 5.5 * cell)
    assert cells.any_within((centre[0] - 1, centre[1] - 1, centre[0] + 1, centre[1] + 1))
    assert not cells.any_within((centre[0] + cell, centre[1] - 1, centre[0] + 2 * cell, centre[1] + 1))
    assert not cells.any_within((x0 - 10 * cell, y0 + cell, x0 - 9 * cell, y0 + 2 * cell))  # outside the mask
    (lon,), (lat,) = transform("EPSG:3857", "EPSG:4326", [centre[0]], [centre[1]])
    assert cells.near(lat, lon, 10)
    ground = cell * math.cos(math.radians(lat))
    (lon2,), (lat2,) = transform("EPSG:3857", "EPSG:4326", [centre[0] + 2 * cell], [centre[1]])
    assert not cells.near(lat2, lon2, 0.9 * ground) and cells.near(lat2, lon2, 1.6 * ground)


def test_tiling_keeps_tiles_near_the_cells_extent_and_outline(tmp_path):
    """MercatorTiling over grids inside, across and outside an outline (only the grid's box's tiles under it),
    the service's extent and the cells mask (a tile within one cell of a cell with data is kept); path and
    tile_of agree."""
    res = lerc.resolution(L)
    grid = _mercator_grid(3, 3)
    all9 = sorted((L, ROW + r, COL + c) for r in range(3) for c in range(3))
    tiling = MercatorTiling("x/live", L)
    assert tiling.tiles(grid) == all9
    # The extent of the middle column only
    middle = tile_pixels(L, ROW, COL + 1)
    tiling = MercatorTiling("x/live", L, extent=(middle[0] + 1, -1e9, middle[2] - 1, 1e9))
    assert [t[2] for t in tiling.tiles(grid)] == [COL + 1] * 3
    # Outline: a small polygon inside the top-left tile, then one beyond the grid (none of its tiles)
    from shapely.geometry import box as shapely_box
    left, bottom, right, top = tile_box(L, ROW, COL)
    grid.area_shape = shapely_box(left + 10 * res, bottom + 10 * res, left + 40 * res, bottom + 40 * res)
    assert MercatorTiling("x/live", L).tiles(grid) == [(L, ROW, COL)]
    far = 100 * 256 * res
    grid.area_shape = shapely_box(left - far, top + far / 2, left - far + 256 * res, top + far / 2 + 256 * res)
    assert MercatorTiling("x/live", L).tiles(grid) == []
    # Across the grid's west edge: within the first column of tiles' pixels (half a cell west and north of their cells)
    first, below = tile_pixels(L, ROW, COL), tile_pixels(L, ROW + 1, COL)
    grid.area_shape = shapely_box(first[0] - 2 * 256 * res, below[1] + 1, first[2] - 1, first[3] + 10)
    assert MercatorTiling("x/live", L).tiles(grid) == [(L, ROW, COL), (L, ROW + 1, COL)]
    grid.area_shape = None
    # Cells of level 13, 8 a tile: a cell is half a tile of level 15 (a level-13 tile holds 4 x 4 of them). Data
    # in the top-left cell of the top-left tile: that tile is kept, its neighbours within one cell may be, the
    # tiles two away never
    origin13 = (COL // 4, ROW // 4)
    first = ((ROW % 4) * 2, (COL % 4) * 2)
    path, _ = _mask_file(tmp_path, [first], origin=origin13, shape=(16, 16))
    kept = set(MercatorTiling("x/live", L, cells=TileCells(path)).tiles(grid))
    assert (L, ROW, COL) in kept
    assert kept <= {(L, ROW, COL), (L, ROW, COL + 1), (L, ROW + 1, COL), (L, ROW + 1, COL + 1)}
    path, _ = _mask_file(tmp_path, [], origin=origin13, shape=(16, 16))
    assert MercatorTiling("x/live", L, cells=TileCells(path)).tiles(grid) == []
    tiling = MercatorTiling("brazil/x/live", L)
    path = tiling.path("C:/data/cache", (15, 18531, 12455))
    assert path.replace(os.sep, "/").endswith("brazil/x/live/15/18531/12455.tif")
    assert tiling.tile_of("brazil/x/live/15/18531/12455.tif") == (15, 18531, 12455)
    assert tiling.tile_of("brazil/x/live/16/1/1.tif") is None and tiling.tile_of("brazil/x/live/3/9/1.tif") is None


def test_survey_walks_down_to_the_cells():
    """The tool's walk: children only under tiles with a valid sample, cells of PER_TILE x PER_TILE at LEVEL."""
    box = (55.20, 55.25, -6.20, -6.10)
    c0, r0, c1, r1 = lerc_coverage.tile_range(box, 13)
    target = (13, r0, c0)  # the one tile of the level with data: its top-left cell's samples valid

    def fetch(tile):
        level, row, col = tile
        valid = np.zeros((257, 257), dtype=bool)
        shift = 13 - level
        if level <= 13 and (row, col) == (target[1] >> shift, target[2] >> shift):
            valid[:10, :10] = True
        return valid

    mask, origin, asked = lerc_coverage.survey(fetch, [box], start=11, level=13, per_tile=8, say=lambda s: None)
    assert origin == (c0, r0) and mask.shape == ((r1 - r0 + 1) * 8, (c1 - c0 + 1) * 8)
    assert np.argwhere(mask).tolist() == [[0, 0]]
    start = lerc_coverage.tile_range(box, 11)
    assert asked == (start[2] - start[0] + 1) * (start[3] - start[1] + 1) + 4 + 4
    assert lerc_coverage.check(fetch, box, mask, origin, 13, 8) == {"asked": (c1 - c0 + 1) * (r1 - r0 + 1), "missed": 0}
    assert lerc_coverage.cells_of(np.ones((257, 257), bool), 8).shape == (8, 8)


# --- the catalogue ---

def test_catalogue_layers():
    ni, rj = src.SOURCES["northern_ireland"], src.SOURCES["rio_de_janeiro"]
    assert isinstance(ni.nmt, src.LercTiles) and ni.nmt.url == uk.NI_DTM_URL and ni.nmt.max_level == 19
    assert ni.crs == "EPSG:2157" and ni.default_resolution == 1.0 and ni.nmt.floor is None
    assert rj.nmt.max_level == 15 and rj.nmt.floor == -5.0 and rj.crs == "EPSG:31983" and rj.default_resolution == 5.0
    assert ni.nmt.folder.endswith("/live") and rj.nmt.folder.endswith("/live")
    assert ni.nmt.rewrites and rj.nmt.rewrites and probe.strategy(ni.nmt) == "lerc"
    for source in (ni, rj):
        assert os.path.exists(source.nmt.cells)
    assert ni.instead_without_data == "northern_ireland_10m" and rj.instead_without_data == "europe"


@pytest.mark.parametrize("lat, lon, region", [
    (55.2900, -6.2000, "gb-nir"),   # Rathlin
    (54.8200, -5.7200, "gb-nir"),   # Islandmagee (England's and Scotland's boxes hold it too)
    (54.8500, -5.8200, "gb-nir"),   # Larne
    (54.6700, -5.5300, "gb-nir"),   # the Copeland Islands
    (54.4790, -5.4400, "gb-nir"),   # Burr Point, the Ards peninsula
    (55.3108, -5.8030, "gb-sct"),   # the Mull of Kintyre lighthouse
    (55.3170, -5.6380, "gb-sct"),   # Southend, Kintyre
    (55.2830, -5.5830, "gb-sct"),   # Sanda
    (55.1000, -5.6000, "gb-sct"),   # the North Channel, once in Northern Ireland's box
    (54.3000, -5.3000, "gb-eng"),   # the Irish Sea east of Northern Ireland's boxes (England's box)
])
def test_offline_regions_around_northern_ireland(monkeypatch, tmp_path, lat, lon, region):
    """Offline, the first box holding a point names its region: Northern Ireland's two boxes keep off Kintyre."""
    import osm
    import requests

    def offline(*args, **kwargs):
        raise requests.ConnectionError("offline")
    monkeypatch.setattr(osm, "reverse", offline)
    assert choose.country_code(lat, lon, str(tmp_path)) == "gb"
    assert choose.region_codes(lat, lon, str(tmp_path), "gb") == (region,)


@pytest.mark.parametrize("lat, lon, near", [
    (55.2240, -6.1570, True),     # Fair Head (R74)
    (54.4790, -5.4400, True),     # Burr Point, the Ards peninsula's east coast
    (55.1650, -6.8800, True),     # Benone Strand
    (54.5966, -5.9301, False),    # Belfast, City Hall (the survey's strip along the Lagan lies about 440 m off)
    (54.1800, -5.9200, False),    # the Mournes, Slieve Donard
    (54.9500, -6.6000, False),    # the Sperrins' east
])
def test_northern_ireland_cells(lat, lon, near):
    assert src.SOURCES["northern_ireland"].nmt.has_data_near(lat, lon, "unused") is near


@pytest.mark.parametrize("lat, lon, near", [
    (-22.9505, -43.1600, True),   # Pão de Açúcar (R75)
    (-22.9519, -43.2105, True),   # the sample, Corcovado's slope
    (-23.0000, -43.3600, True),   # Barra da Tijuca
    (-22.8833, -43.1036, False),  # Niterói, inside the city's box across the bay
])
def test_rio_cells(lat, lon, near):
    assert src.SOURCES["rio_de_janeiro"].nmt.has_data_near(lat, lon, "unused") is near


def test_auto_choice_offline(monkeypatch, tmp_path):
    """Offline (Nominatim unreachable): Fair Head takes northern_ireland, Belfast's centre northern_ireland_10m (no
    coastal data near), the Ards peninsula northern_ireland (its box before England's and Scotland's); Pão de Açúcar
    rio_de_janeiro, Niterói europe, São Paulo europe (no source)."""
    import osm
    import requests

    def offline(*args, **kwargs):
        raise requests.ConnectionError("offline")
    monkeypatch.setattr(osm, "reverse", offline)
    cache_dir = str(tmp_path)
    for (lat, lon), want in (((55.2240, -6.1570), "northern_ireland"), ((54.5966, -5.9301), "northern_ireland_10m"),
                             ((54.4790, -5.4400), "northern_ireland"), ((-22.9505, -43.1600), "rio_de_janeiro"),
                             ((-22.8833, -43.1036), "europe"), ((-23.55, -46.63), "europe")):
        source, why = choose.choose_source("auto", lat, lon, cache_dir)
        assert source.id == want, (lat, lon, why)


def test_probe_reads_the_first_kb(monkeypatch):
    """The probe asks the tile holding the sample at the source's level (no Range) and wants the LERC1 magic."""
    import contextlib
    asked = []

    def fake(url, params=None, headers=None):
        asked.append((url, headers))
        if "/tile/17/" in url:
            return 200, "image/lerc", lerc.LERC1_MAGIC + b"\x0b\x00"
        return 404, "text/html", b"<html>"
    monkeypatch.setattr(probe, "_http", fake)
    monkeypatch.setattr(probe, "host_slot", lambda cache_dir, url: contextlib.nullcontext())
    ni = src.SOURCES["northern_ireland"]
    row = probe.probe_layer(ni, ni.nmt, "terrain", "unused", "unused", False)
    assert (row.index, row.read) == (probe.NONE, probe.OK) and asked == [(f"{uk.NI_DTM_URL}/tile/17/41315/63294", None)]
    rj = src.SOURCES["rio_de_janeiro"]
    row = probe.probe_layer(rj, rj.nmt, "terrain", "unused", "unused", False)
    assert row.read == probe.FAILED and "HTTP 404" in row.notes[0]
    assert asked[-1][0] == f"{brazil.RJ_DTM_URL}/tile/15/18531/12450"


def test_layer_without_a_mask_and_tile_bounds(http_server):
    """Without cells has_data_near is unknown (None) and every tile is listed; bounds_wgs84 are the tile's pixels in
    degrees (written out: tile 17/41315/63294 at Fair Head); check_source compares no file of a LercTiles layer."""
    import check_source
    layer = _layer(http_server.url("/svc"))
    assert layer.has_data_near(55.224, -6.157, "unused") is None
    assert len(layer.tiles(_mercator_grid(2, 2))) == 4
    ni = src.SOURCES["northern_ireland"].nmt
    assert ni.bounds_wgs84((17, 41315, 63294)) == pytest.approx(
        (-6.157842278479856, 55.22276014781404, -6.155095696448606, 55.22432673256287), abs=1e-9)
    assert check_source._sources_of(ni, (17, 41315, 63294)) is None


def test_mosaic_resamples_web_mercator_by_its_ground_size():
    """mosaic: an EPSG:3857 tile's pixel counts at its size on the ground (times the cosine of the grid centre's
    latitude): Northern Ireland's level 17 (1.19 m, 0.68 m at 55.2° N) is averaged onto a 1 m grid, Rio's level 15
    (4.78 m, 4.40 m at 23° S) interpolated onto 5 m as before; other CRSs keep their sizes (degrees as 111 320 m)."""
    from types import SimpleNamespace
    from rasterio.crs import CRS
    from rasterio.enums import Resampling
    from sources import mosaic

    def grid_at(lat, lon, crs, res):
        (x,), (y,) = transform("EPSG:4326", crs, [lon], [lat])
        return make_grid((x - 500, y - 500, x + 500, y + 500), res, crs)

    ni_grid, rj_grid = grid_at(55.224, -6.157, "EPSG:2157", 1.0), grid_at(-22.95, -43.16, "EPSG:31983", 5.0)
    mercator = CRS.from_epsg(3857)
    ni = mosaic.src_pixel_m(SimpleNamespace(res=(lerc.resolution(17),) * 2), mercator, ni_grid)
    rj = mosaic.src_pixel_m(SimpleNamespace(res=(lerc.resolution(15),) * 2), mercator, rj_grid)
    assert ni == pytest.approx(0.681, abs=0.002) and rj == pytest.approx(4.400, abs=0.005)
    assert mosaic._resampling(ni, 1.0) == Resampling.average
    assert mosaic._resampling(rj, 5.0) == Resampling.bilinear
    assert mosaic.src_pixel_m(SimpleNamespace(res=(2.0, 2.0)), CRS.from_epsg(2157), ni_grid) == 2.0
    assert mosaic.src_pixel_m(SimpleNamespace(res=(1 / 3600,) * 2), CRS.from_epsg(4326), ni_grid) == \
        pytest.approx(111320 / 3600)
