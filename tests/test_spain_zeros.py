"""IGN Spain's heights of exactly 0 m are no data in `spain`'s terrain and surface (the user's decision of 2026-11-26):
MDT05 and MDS05 answer the sea and the land beyond their data (around Ceuta and Melilla, along the borders) with
0.000 and no nodata value. `spain_canarias` keeps them (its sea is 0 m in the data, R10). The catalogue's own layers,
their tiles through the reader's own path (a local WCS), `spain`'s folders of its own (the tiles cached before the
rule stay where they were, unread by `spain`) and the missing-tiles count of a layer of another processing."""

import hashlib
import os
import re
import sys

import numpy as np
import pytest
import rasterio as rio
from rasterio.io import MemoryFile
from rasterio.transform import from_origin

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cache  # noqa: E402
import sources as src  # noqa: E402
import update  # noqa: E402
from grid import make_grid  # noqa: E402
from sources.catalogue import spain  # noqa: E402
from http_server import Answer  # noqa: E402
from tile_values import TILE_EPS  # noqa: E402

SPAIN, CANARIAS = src.SOURCES["spain"], src.SOURCES["spain_canarias"]
TILE = (5.0, 50, 390)  # 500-510 km E, 3900-3910 km N (Melilla's tile)
LEFT, BOTTOM, SIZE = 500_000.0, 3_900_000.0, 10_000.0
MDS_PIXEL = 5.0045  # MDS05's own grid: the service answers on it, the reader resamples to 5 m


def test_the_catalogues_layers():
    """Only `spain`'s two layers take 0 as no data, each in a folder of its own (a cached tile means one thing);
    `spain_canarias`'s layers are as they were; every layer of processing 1."""
    assert SPAIN.nmt.reader.zero_is_nodata and SPAIN.nmpt.reader.zero_is_nodata
    assert not CANARIAS.nmt.reader.zero_is_nodata and not CANARIAS.nmpt.reader.zero_is_nodata
    assert SPAIN.nmt.processing == SPAIN.nmpt.processing == CANARIAS.nmt.processing == CANARIAS.nmpt.processing == 1
    assert CANARIAS.nmt.folder == "spain/mdt05/live" and SPAIN.nmt.folder == spain.SPAIN_MDT_FOLDER
    assert CANARIAS.nmpt.folder == "spain/mds05/live" and SPAIN.nmpt.folder == spain.SPAIN_MDS_FOLDER
    assert spain.SPAIN_MDT_FOLDER == "spain/mdt05-zeros-nodata/live"
    assert spain.SPAIN_MDS_FOLDER == "spain/mds05-zeros-nodata/live"
    assert SPAIN.nmt.ttl_days == CANARIAS.nmt.ttl_days and SPAIN.nmpt.ttl_days == CANARIAS.nmpt.ttl_days
    # Both surface models are MDS05 on one tiling (EPSG:25830): the same tile is two files, one per rule
    assert SPAIN.nmpt.crs == CANARIAS.nmpt.crs == "EPSG:25830" and SPAIN.nmpt.coverage == CANARIAS.nmpt.coverage
    assert SPAIN.nmpt.tile_path("c", TILE) != CANARIAS.nmpt.tile_path("c", TILE)
    assert "exactly 0 m" in SPAIN.note and "exactly 0 m" in SPAIN.description and "Ceuta" in SPAIN.note
    assert "exactly 0 m" in SPAIN.listing.terrain and "exactly 0 m" in SPAIN.listing.surface
    canary = CANARIAS.note + CANARIAS.description + CANARIAS.listing.terrain + CANARIAS.listing.surface
    assert "exactly 0 m" not in canary


@pytest.mark.parametrize("kind", ["nmt", "nmpt"])
@pytest.mark.parametrize("which", ["spain", "spain_canarias"])
def test_each_path_has_one_layer(which, kind, tmp_path):
    """`cache update` and `cache migrate` find a cached tile's layer by its path (update._check: the first live
    layer whose tile_of knows it; update.rewriting_layer): each source's terrain and surface tiles are known to its
    own layer only, so an update renews them under their own rule."""
    layer = getattr(src.SOURCES[which], kind)
    path = cache.relative(str(tmp_path), layer.tile_path(str(tmp_path), TILE))
    knowing = [other for other in update._live_layers() if other.tile_of(path) is not None]
    assert knowing == [layer] and update.rewriting_layer(path) is layer


def _box(query) -> tuple:
    """(left, bottom, right, top) of a GetCoverage's SUBSET x(..) and y(..)."""
    found = {}
    for key, value in query:
        if key.upper() == "SUBSET":
            axis, low, high = re.fullmatch(r"(\w+)\(([-\d.]+),([-\d.]+)\)", value).groups()
            found[axis] = (float(low), float(high))
    (left, right), (bottom, top) = found["x"], found["y"]
    return left, bottom, right, top


def _heights(x, y):
    """The fake service's answer at (x, y): land with millimetres west of 505 km, 0.000 east of it (the sea or the
    land beyond the data), a strip of land at exactly 0 m (504-504.5 km), a hole without data (NaN) in the south-west
    and a negative height (-0.36 m) beside the zeros."""
    z = np.where(x < 505_000, np.round(20.0 + (x - LEFT) / 50.0 + (y - BOTTOM) / 700.0, 3), 0.0)
    z = np.where((x >= 504_000) & (x < 504_500), 0.0, z)
    z = np.where((x >= 505_000) & (x < 505_100), -0.36, z)
    return np.where((x < 501_000) & (y < 3_901_000), np.nan, z).astype(np.float32)


def _service(pixel_of):
    def handle(request):
        query = request.query
        assert dict((k.upper(), v) for k, v in query)["REQUEST"] == "GetCoverage"
        left, bottom, right, top = _box(query)
        pixel = pixel_of(dict(query)["COVERAGEID"])
        width, rows = round((right - left) / pixel), round((top - bottom) / pixel)
        ys, xs = np.mgrid[0:rows, 0:width]
        band = _heights(left + (xs + 0.5) * pixel, top - (ys + 0.5) * pixel)
        with MemoryFile() as memfile:
            with memfile.open(driver="GTiff", width=width, height=rows, count=1, dtype="float32",
                              crs="EPSG:25830", transform=from_origin(left, top, pixel, pixel), nodata=np.nan) as dst:
                dst.write(band, 1)
            return Answer(200, memfile.read(), {"Content-Type": "image/tiff"})
    return handle


def _fetched(layer, cache_dir) -> np.ndarray:
    assert layer._download_and_record(TILE, cache_dir) > 0
    with rio.open(layer.tile_path(cache_dir, TILE)) as f:
        return f.read(1)


def _expected() -> np.ndarray:
    ys, xs = np.mgrid[0:2000, 0:2000]
    return _heights(LEFT + (xs + 0.5) * 5.0, BOTTOM + SIZE - (ys + 0.5) * 5.0)


@pytest.mark.parametrize("kind", ["nmt", "nmpt"])
def test_zeros_become_no_data(kind, http_server, monkeypatch, tmp_path):
    """A tile of `spain` (each layer: the terrain on its own 5 m pixels, the surface model on MDS05's 5.0045 m,
    resampled by the reader) holds no data where the service answered exactly 0, and the heights elsewhere, the
    negative ones and those of land at a few millimetres too; NaN stays NaN. The same answer through
    `spain_canarias`'s layer keeps its zeros. The row has the layer's processing; fetched again, the same bytes."""
    http_server.route("/wcs", _service(lambda coverage: MDS_PIXEL if coverage == "mds05" else 5.0))
    cache_dir = str(tmp_path / "cache")
    layers = {"spain": getattr(SPAIN, kind), "spain_canarias": getattr(CANARIAS, kind)}
    for layer in layers.values():
        monkeypatch.setattr(layer.reader, "service_url", http_server.url("/wcs"))
        monkeypatch.setattr(layer.reader, "_extent", (0.0, 0.0, 1e7, 1e7))
    tile = layers["spain"]
    if kind == "nmt":  # the Canaries' terrain is another coverage on another CRS: only the surface model is shared
        layers.pop("spain_canarias")
    band, expected = _fetched(tile, cache_dir), _expected()
    if kind == "nmpt":  # nearest from 5.0045 m pixels: the values the service gave, each at its nearest pixel
        expected = _resampled(expected)
    zero = expected == 0.0
    assert zero.any() and np.isnan(band[zero]).all()
    real = np.isfinite(expected) & ~zero
    assert np.abs(band[real] - expected[real]).max() <= TILE_EPS
    assert np.isnan(band[np.isnan(expected)]).all()
    assert (band[real] < 0).any()  # -0.36 m is a height
    row = cache.info(cache_dir, tile.tile_path(cache_dir, TILE))
    assert row["status"] == "ok" and row["processing"] == tile.processing
    first = hashlib.sha256(open(tile.tile_path(cache_dir, TILE), "rb").read()).hexdigest()
    _fetched(tile, cache_dir)
    assert hashlib.sha256(open(tile.tile_path(cache_dir, TILE), "rb").read()).hexdigest() == first
    if "spain_canarias" in layers:
        kept = _fetched(layers["spain_canarias"], cache_dir)
        assert np.abs(kept[zero]).max() <= TILE_EPS and np.isfinite(kept[zero]).all()


def _resampled(expected: np.ndarray) -> np.ndarray:
    """The fake's answer on MDS05's pixels, taken by nearest onto the tile's 5 m pixels (as WcsReader._band does)."""
    from rasterio.warp import Resampling, reproject
    width = round(SIZE / MDS_PIXEL)
    ys, xs = np.mgrid[0:width, 0:width]
    native = _heights(LEFT + (xs + 0.5) * MDS_PIXEL, BOTTOM + SIZE - (ys + 0.5) * MDS_PIXEL)
    out = np.full(expected.shape, np.nan, np.float32)
    reproject(native, out, src_transform=from_origin(LEFT, BOTTOM + SIZE, MDS_PIXEL, MDS_PIXEL), src_crs="EPSG:25830",
              dst_transform=from_origin(LEFT, BOTTOM + SIZE, 5.0, 5.0), dst_crs="EPSG:25830", src_nodata=np.nan,
              dst_nodata=np.nan, resampling=Resampling.nearest)
    return out


def _zeros(request):
    """The service's answer of 0.000 only over the asked box (on the coverage's own pixels: 5 m, MDS05's 5.0045 m)."""
    left, bottom, right, top = _box(request.query)
    pixel = MDS_PIXEL if dict(request.query)["COVERAGEID"] == "mds05" else 5.0
    width, rows = round((right - left) / pixel), round((top - bottom) / pixel)
    with MemoryFile() as memfile:
        with memfile.open(driver="GTiff", width=width, height=rows, count=1, dtype="float32", crs="EPSG:25830",
                          transform=from_origin(left, top, pixel, pixel)) as dst:
            dst.write(np.zeros((rows, width), np.float32), 1)
        return Answer(200, memfile.read(), {"Content-Type": "image/tiff"})


def test_an_all_zero_tile_is_all_no_data(http_server, monkeypatch, tmp_path):
    """A tile the service answers with 0.000 only (Fnideq's, beyond Ceuta's block) is a file without a pixel of data:
    the gap filling takes all of it."""
    http_server.route("/wcs", _zeros)
    monkeypatch.setattr(SPAIN.nmt.reader, "service_url", http_server.url("/wcs"))
    monkeypatch.setattr(SPAIN.nmt.reader, "_extent", (0.0, 0.0, 1e7, 1e7))
    assert np.isnan(_fetched(SPAIN.nmt, str(tmp_path / "cache"))).all()


def test_an_all_zero_surface_tile_is_kept(http_server, monkeypatch, tmp_path):
    """MDS05 answers 0.000 over all of a tile (Ceuta's, Melilla's): the cache keeps a file of the tile's size
    without a pixel of data, recorded "ok" (not "missing", which is asked again after MISSING_TTL_DAYS), and a second
    search over the tile reads that file: no second request, the grid all NaN both times."""
    http_server.route("/wcs", _zeros)
    layer = SPAIN.nmpt
    monkeypatch.setattr(layer.reader, "service_url", http_server.url("/wcs"))
    monkeypatch.setattr(layer.reader, "_extent", (0.0, 0.0, 1e7, 1e7))
    cache_dir = str(tmp_path / "cache")
    grid = make_grid((LEFT + 100, BOTTOM + 100, LEFT + 600, BOTTOM + 600), 5.0, "EPSG:25830")
    first = np.load(src.mosaic.prepare_layer(layer, grid, cache_dir, str(tmp_path / "a.npy"), "surface"))
    asked = len(http_server.requests("/wcs"))
    assert asked >= 1 and np.isnan(first).all()
    path = layer.tile_path(cache_dir, TILE)
    with rio.open(path) as f:
        stored = f.read(1)
    assert stored.shape == (2000, 2000) and np.isnan(stored).all()
    row = cache.info(cache_dir, path)
    assert row["status"] == "ok" and row["processing"] == layer.processing
    assert layer.missing(grid, cache_dir, None) == []
    again = np.load(src.mosaic.prepare_layer(layer, grid, cache_dir, str(tmp_path / "b.npy"), "surface"))
    assert len(http_server.requests("/wcs")) == asked and np.isnan(again).all()


def _tile(cache_dir: str, layer, processing: int, status: str = "ok", tile=TILE) -> str:
    path = layer.tile_path(cache_dir, tile)
    if status == "ok":
        os.makedirs(os.path.dirname(path), exist_ok=True)
        src.layer._write_tile(path, np.zeros((4, 4), np.float32), layer.crs, from_origin(LEFT, BOTTOM + 20, 5, 5))
    cache.record(cache_dir, path, status, processing=processing)
    return path


def test_tiles_of_before_are_not_spains(tmp_path):
    """`spain`'s tiles cached before the rule (zeros as heights) lie in the folders `spain_canarias` keeps: `spain`'s
    own folders start empty (its tiles due), the old ones stay cached for a checkout of before (not due at processing
    1), and no layer of today knows an old peninsula terrain tile (spain/mdt05/live holds the Canaries' tiling too),
    so `cache update` leaves it alone; the old peninsula surface tiles are `spain_canarias`'s (one tiling)."""
    cache_dir = str(tmp_path)
    today = cache.relative(cache_dir, SPAIN.nmt.tile_path(cache_dir, TILE))
    old_terrain = os.path.join(cache_dir, *today.replace(spain.SPAIN_MDT_FOLDER, "spain/mdt05/live").split("/"))
    os.makedirs(os.path.dirname(old_terrain))
    src.layer._write_tile(old_terrain, np.zeros((4, 4), np.float32), "EPSG:25830", from_origin(LEFT, BOTTOM + 20, 5, 5))
    cache.record(cache_dir, old_terrain, "ok", processing=1)
    old_surface = _tile(cache_dir, CANARIAS.nmpt, 1)
    for layer in (SPAIN.nmt, SPAIN.nmpt):
        assert cache.due(cache_dir, layer.tile_path(cache_dir, TILE), layer.processing)
        assert layer.tile_path(cache_dir, TILE) not in (old_terrain, old_surface)
    assert not cache.due(cache_dir, old_terrain, 1) and not cache.due(cache_dir, old_surface, 1)
    relative = cache.relative(cache_dir, old_terrain)
    assert relative.startswith("spain/mdt05/live/epsg25830-")
    assert [layer for layer in update._live_layers() if layer.tile_of(relative) is not None] == []
    surface = cache.relative(cache_dir, old_surface)
    assert [layer for layer in update._live_layers() if layer.tile_of(surface) is not None] == [CANARIAS.nmpt]


def test_tiles_without_data_counted_at_the_layers_processing(tmp_path, capsys):
    """prepare_layer's "N of M tiles without data" counts the tiles the service had none for at the layer's own
    processing: a layer of processing 2 (Bremerhaven's DOM1) was never counted, a row of another processing answering
    None; the line the regression set compares (empty_tiles). A layer of the test's own, not the catalogue's."""
    layer = src.WcsTiles("Test terrain", "https://example.org/wcs", "cov", "EPSG:25830", "test/live", native_res=5.0,
                         fetch_res=5.0, fmt="application/asc", bytes_per_px=8)
    layer.processing = 2
    layer.reader._extent = (0.0, 0.0, 1e7, 1e7)  # no DescribeCoverage
    cache_dir = str(tmp_path / "cache")
    grid = make_grid((LEFT + 100, BOTTOM + 100, LEFT + 600, BOTTOM + 600), 5.0, "EPSG:25830")
    tile = layer.tiles(grid)[0]
    _tile(cache_dir, layer, 2, "missing", tile)
    out = np.load(src.mosaic.prepare_layer(layer, grid, cache_dir, str(tmp_path / "nmt.npy"), "terrain",
                                           download=False))
    assert np.isnan(out).all() and len(layer.tiles(grid)) == 1
    assert "Test terrain: 1 of 1 tiles without data" in capsys.readouterr().out
    _tile(cache_dir, layer, 1, "missing", tile)  # a row of another processing: not counted
    src.mosaic.prepare_layer(layer, grid, cache_dir, str(tmp_path / "again.npy"), "terrain", download=False)
    assert "tiles without data" not in capsys.readouterr().out
