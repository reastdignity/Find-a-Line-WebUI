"""Heights below a layer's floor are no data where its tiles are read onto the grid (Layer.nodata_below,
mosaic.build_mosaic's below). Every path of the mosaic (a tile on the grid copied, a tile placed where another
wrote, a tile reprojected), and the default (no floor: the mosaic as before, bit for bit)."""

import numpy as np
import pytest
from rasterio.transform import from_origin

from grid import make_grid
from sources import mosaic
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
