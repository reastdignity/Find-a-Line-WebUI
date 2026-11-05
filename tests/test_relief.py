"""relief.py: Copernicus GLO-30 in blocks of about 1 km (tile_blocks, the proxies of
tools/perf_country.py's relief and estimate), the steep km² of the blocks inside an outline
(steep_blocks) and their sums per core of a fixed lattice (per_core: country._relief_weights);
offline, on synthetic tiles."""

import os
import sys

import numpy as np
import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
import relief  # noqa: E402


def write_tile(path: str, lat0: float, lon0: float, n: int, size: float = 0.1, slope_from: float = 0.5,
               degrees: float = 50.0):
    """A GeoTIFF of size × size degrees at n × n pixels, flat west of slope_from (a share of its
    width) and a slope of `degrees` rising eastwards beyond."""
    import rasterio as rio
    from rasterio.transform import from_origin
    dy = size / n * relief.EARTH_M_PER_DEG
    dx = dy * np.cos(np.radians(lat0 + size / 2))
    z = np.zeros((n, n))
    first = int(round(n * slope_from))
    z[:, first:] = np.tan(np.radians(degrees)) * dx * np.arange(n - first)[None, :]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with rio.open(path, "w", driver="GTiff", width=n, height=n, count=1, dtype="float32", crs="EPSG:4326",
                  transform=from_origin(lon0, lat0 + size, size / n, size / n)) as out:
        out.write(z.astype(np.float32), 1)
    return dy, dx


def test_tile_blocks(tmp_path):
    """A 0.1° GeoTIFF at 1″, flat in its west half and a 50° slope in its east half: blocks of
    about 1 km, relief and steep shares per block and over windows."""
    n = 360
    path = str(tmp_path / "t.tif")
    dy, dx = write_tile(path, 46.0, 7.0, n)
    b = relief.tile_blocks(path)
    rows, cols = b["km2"].shape
    assert rows == round(n * dy / 1000) and cols == round(n * dx / 1000)
    assert b["km2"].sum() == pytest.approx(n * dy * n * dx / 1e6, rel=1e-3)
    assert b["relief1"][:, 0].max() == 0 and b["steep30_1"][:, 0].max() == 0  # the flat west
    assert b["steep45_1"][:, -1].min() > 0.95 and b["relief1"][:, -1].min() > 900  # 50°, about 0.8 km a block
    assert (b["relief3"] >= b["relief1"] - 1e-9).all() and (b["relief5"] >= b["relief3"] - 1e-9).all()
    found = relief.proxies_at({(46, 7): b}, np.array([7.01, 7.09, 8.5]), np.array([46.05, 46.05, 46.05]))
    assert found["steep45_1"][0] == 0 and found["steep45_1"][1] > 0.95 and np.isnan(found["steep45_1"][2])


def cached_tile(cache_dir: str, lat: int, lon: int, **kwargs) -> str:
    """A synthetic 1° GLO-30 tile where the relief layer caches it, recorded in the cache's index
    (fetch_relief_tiles then downloads nothing)."""
    import cache
    path = relief.relief_layer().tile_path(cache_dir, (lat, lon))
    write_tile(path, lat, lon, kwargs.pop("n", 400), size=1.0, **kwargs)
    cache.record(cache_dir, path, "ok")
    return path


def test_steep_blocks_inside_the_outline(tmp_path):
    """The blocks whose centre lies inside the outline, in the asked CRS, with their km² of slopes of
    45° or more; a degree tile without data (sea) is read as none; other angles are refused."""
    from pyproj import Transformer
    from shapely.geometry import box
    cache_dir = str(tmp_path / "cache")
    cached_tile(cache_dir, 48, 19, slope_from=0.75)  # 45° and more in its eastern quarter only
    relief_layer = relief.relief_layer()
    import cache
    cache.record(cache_dir, relief_layer.tile_path(cache_dir, (48, 20)), "missing")  # the sea
    outline = box(19.5, 48.2, 20.4, 48.8)
    found = relief.steep_blocks(outline, "EPSG:32634", cache_dir, 45)
    assert found.tiles == 2 and len(found.x) == len(found.y) == len(found.steep) > 0
    lon, lat = Transformer.from_crs("EPSG:32634", "EPSG:4326", always_xy=True).transform(found.x, found.y)
    assert (np.asarray(lon) > 19.5).all() and (np.asarray(lon) < 20.0).all()  # no data beyond 20°: the sea
    assert (np.asarray(lat) > 48.2).all() and (np.asarray(lat) < 48.8).all()
    steep = found.steep > 0
    assert steep.any() and (np.asarray(lon)[steep] > 19.74).all() and (np.asarray(lon)[~steep] < 19.76).all()
    # every steep block holds about its km²: 0.6° x 0.25° of slope inside the outline
    km2 = 0.6 * 0.25 * relief.EARTH_M_PER_DEG ** 2 * np.cos(np.radians(48.5)) / 1e6
    assert found.steep.sum() == pytest.approx(km2, rel=0.05)
    with pytest.raises(ValueError):
        relief.steep_blocks(outline, "EPSG:32634", cache_dir, 60)


def test_per_core_sums_the_points_of_each_core():
    """The points inside each core of a lattice (left and bottom edges inside, right and top
    outside, negative coordinates too); points outside every core are left out."""
    cores = [(-20, 0, -10, 10), (-10, 0, 0, 10), (0, 0, 10, 10), (-10, -10, 0, 0)]
    x = np.array([-20, -10.5, -10, 0, 9.99, 10, -5, -5, 30])
    y = np.array([0, 5, 9.99, 0, 5, 5, -10, 0, 0])
    v = np.array([1, 2, 4, 8, 16, 32, 64, 128, 256], dtype=float)
    assert relief.per_core(x, y, v, cores).tolist() == [3, 4 + 128, 8 + 16, 64]
    assert relief.per_core(x[:0], y[:0], v[:0], cores).tolist() == [0, 0, 0, 0]
