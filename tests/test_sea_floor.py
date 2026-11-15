"""Heights below a layer's floor are no data where its tiles are read onto the grid (Layer.nodata_below,
mosaic.build_mosaic's below): the sea floor of IGN's overseas RGE ALTI 1 m (sources/catalogue/france.py
OVERSEAS_FLOOR). Every path of the mosaic (a tile on the grid copied, a tile placed where another wrote, a tile
reprojected), a tile cached before the floor existed, the catalogue's own layers on served answers, and the default
(no floor: the mosaic as before, bit for bit)."""

import os
from urllib.parse import urlencode

import numpy as np
import pytest
import rasterio as rio
from rasterio.transform import from_origin

import sources as src
from grid import make_grid
from sources import mosaic, net
from sources.catalogue import france
from sources.layer import _write_tile

# A 4 x 4 tile: below the floor (-30, -1.0001), at it (-1.0), between it and 0 (-0.5, -0.01), 0 and land
VALUES = np.array([[-30.0, -1.0001, -1.0, -0.5],
                   [-0.01, 0.0, 0.4, 1.0],
                   [5.0, 20.0, -2.0, np.nan],
                   [-500.0, -600.0, 3.0, 7.5]], dtype=np.float32)
FLOORED = VALUES.copy()
FLOORED[VALUES < -1.0] = np.nan
FLOORED[3, 1] = np.nan  # below layer.VALID_MIN: no data whatever the floor


def _tile(path, left=1000.0, top=2004.0, res=1.0, values=VALUES, crs="EPSG:32620"):
    _write_tile(path, values, crs, from_origin(left, top, res, res))
    return path


def _grid(res=1.0, left=1000.0, bottom=2000.0, size=4):
    return make_grid((left, bottom, left + size, bottom + size), res, "EPSG:32620")


@pytest.mark.parametrize("below, expected", [(None, np.where(VALUES < -500, np.nan, VALUES)), (-1.0, FLOORED)])
def test_a_tile_on_the_grid(tmp_path, below, expected):
    """Copied straight into the mosaic (the first raster of the part): below the floor no data, at it and above it kept."""
    path = _tile(str(tmp_path / "a.tif"))
    out = mosaic.build_mosaic([path], _grid(), str(tmp_path / "m.npy"), "t", below=below)
    assert np.allclose(np.asarray(out), expected, equal_nan=True, atol=0.0051)
    assert np.isnan(np.asarray(out)).sum() == np.isnan(expected).sum()


def test_a_tile_where_another_wrote(tmp_path):
    """The second raster of a part fills only the first's holes, floored the same way (_put's path)."""
    first = np.full((4, 4), np.nan, np.float32)
    first[0, 0] = 99.0
    a = _tile(str(tmp_path / "a.tif"), values=first)
    b = _tile(str(tmp_path / "b.tif"))
    out = np.asarray(mosaic.build_mosaic([a, b], _grid(), str(tmp_path / "m.npy"), "t", below=-1.0))
    expected = FLOORED.copy()
    expected[0, 0] = 99.0
    assert np.allclose(out, expected, equal_nan=True, atol=0.0051)


def test_a_reprojected_tile_is_floored_before_the_resampling(tmp_path):
    """A tile half a pixel off the grid (the Antilles' edges on half metres, the grid on whole ones) is resampled
    bilinearly: the floor is applied to its own pixels first, so no value of the sea floor leaks into a pixel."""
    values = np.full((8, 8), -30.0, np.float32)
    values[:, 4:] = 2.0
    path = _tile(str(tmp_path / "a.tif"), left=999.5, top=2008.5, values=values)
    grid = make_grid((1000, 2000, 1008, 2008), 1.0, "EPSG:32620")
    plain = np.asarray(mosaic.build_mosaic([path], grid, str(tmp_path / "p.npy"), "t"))
    floored = np.asarray(mosaic.build_mosaic([path], grid, str(tmp_path / "f.npy"), "t", below=-1.0))
    assert np.nanmin(plain) < -1  # without the floor the sea floor is there, and blends into the edge
    finite = floored[np.isfinite(floored)]
    assert finite.size and (finite >= -1.0).all() and np.isnan(floored[:, :3]).all()


def test_no_floor_is_the_mosaic_as_before(tmp_path):
    """The default (None) changes nothing, bit for bit, on every path."""
    path = _tile(str(tmp_path / "a.tif"))
    off = _tile(str(tmp_path / "b.tif"), left=999.5, top=2004.5)
    for files, name in (([path], "same"), ([off], "warp"), ([path, off], "both")):
        before = np.asarray(mosaic.build_mosaic(files, _grid(), str(tmp_path / f"{name}0.npy"), "t"))
        again = np.asarray(mosaic.build_mosaic(files, _grid(), str(tmp_path / f"{name}1.npy"), "t", below=None))
        assert before.tobytes() == again.tobytes(), name


def test_the_default_of_a_layer():
    """No floor unless a layer says so: of every layer of the catalogue, only the overseas RGE ALTI ones."""
    floored = {s.id: layer.nodata_below for s in src.SOURCES.values() for layer in (s.nmt, s.nmpt)
               if layer is not None and layer.nodata_below is not None}
    assert floored == {"france_guadeloupe": -1.0, "france_martinique": -1.0, "france_guiana": -1.0,
                       "france_spm": -1.0, "france_reunion_rgealti": -1.0, "france_mayotte": -1.0}
    assert src.WATER_MASK.nodata_below is None
    for layer in (france.FR_RGEALTI, france.FR_MNT, france.FR_MNS, france.REU_MNT, france.REU_MNS):
        assert layer.nodata_below is None


def _serve(server, layer, tile, values, nodata):
    """The GetMap the catalogue's layer writes for tile, answered by values (a float32 GeoTIFF as IGN's)."""
    request = layer.index.request(tile)
    res = (request.right - request.left) / request.width
    with rio.io.MemoryFile() as memfile:
        with memfile.open(driver="GTiff", width=request.width, height=request.height, count=1, dtype="float32",
                          crs=layer.crs, transform=from_origin(request.left, request.top, res, res),
                          nodata=nodata) as dst:
            dst.write(values.astype(np.float32), 1)
        body = memfile.read()
    server.add(f"/wms-r/wms?{urlencode(layer.reader.getmap_params(request))}", body, "image/geotiff")


@pytest.mark.parametrize("sid", ["france_martinique", "france_mayotte"])
def test_the_catalogues_layers_fresh_and_cached(http_server, tmp_path, monkeypatch, sid):
    """A served answer with the sea floor in it, through the catalogue's own layer (only the service's address
    replaced): the tile is cached as it came (the floor is not written: a tile cached before it existed is the same
    file), and the grid has no data below -1 m, keeps -1 m, the water between -1 and 0 and the land. A tile whose
    every height lies below the floor is cached (it has data) and gives the grid nothing."""
    layer = src.SOURCES[sid].nmt
    monkeypatch.setattr(layer.reader, "service_url", http_server.url("/wms-r/wms"))
    monkeypatch.setattr(net, "_sleep", lambda attempt: None)
    ox, oy = layer.origin
    tile, deep_tile = (1.0, 500, 1600), (1.0, 501, 1600)
    sea = np.full((1000, 1000), 30.0)
    sea[:, :400] = -25.0          # the sea floor
    sea[:, 400:410] = -1.0        # at the floor
    sea[:, 410:420] = -0.4        # the water's edge
    sea[:2, :] = -99999.0         # IGN's no data
    _serve(http_server, layer, tile, sea, -99999.0)
    _serve(http_server, layer, deep_tile, np.full((1000, 1000), -12.0), -99999.0)
    cache_dir = str(tmp_path / "cache")
    grid = make_grid((500000 + ox + 100, 1600000 + oy + 100, 502000 + ox - 100, 1601000 + oy - 100), 1.0,
                     layer.crs, layer.origin)
    out = np.load(src.mosaic.prepare_layer(layer, grid, cache_dir, str(tmp_path / "nmt.npy"), "terrain"))
    for t in (tile, deep_tile):  # cached as they came: the floor is applied when read, not written
        with rio.open(layer.tile_path(cache_dir, t)) as cached:
            assert float(np.nanmin(cached.read(1, masked=True).filled(np.nan))) < -1
    west = out[:, :900]  # tile 500's part of the grid: its columns 100-999
    assert np.isnan(west[:, :300]).all()                       # -25: no data
    assert np.allclose(west[:, 300:310], -1.0, atol=0.0051)    # -1 exactly: kept
    assert np.allclose(west[:, 310:320], -0.4, atol=0.0051)    # between -1 and 0: kept
    assert np.allclose(west[:, 320:], 30.0, atol=0.0051)
    assert np.isnan(out[:, 900:]).all()                        # tile 501: all below the floor
