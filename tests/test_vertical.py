"""The geoid part (sources/vertical.py) and its hook in Windows / FileBlocks: N of EGM2008 against GeographicLib on
windows of PROJ's grid recorded on 2026-11-03 (tests/data/geoid/, 6 x 6 points each, not the 80 MB file), the
longitude wrapped past 180°, the lattice of a block, the grid's download (local server: once, its size and sha256
checked, a byte cap) and blocks cached as heights above the geoid."""

import hashlib
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
from tile_values import TILE_EPS, same_tile  # noqa: E402
from sources import vertical  # noqa: E402
from sources.layers.fileblocks import FileBlocks  # noqa: E402

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "geoid")
# GeographicLib's GeoidEval with egm2008-1 (the research of batch 3, 2026-11-02): (lat, lon, N)
GEOIDEVAL = {"nuuk": (64.1814, -51.6941, 28.3209), "longyearbyen": (78.2232, 15.6267, 32.3626),
             "qikiqtarjuaq": (67.5547, -64.0247, 7.6898)}


@pytest.mark.parametrize("name", sorted(GEOIDEVAL))
def test_egm2008_against_geographiclib(name):
    """Bilinear on the 2.5' points of PROJ's grid: within 1 cm of GeographicLib's 1' grid (cubic)."""
    lat, lon, expected = GEOIDEVAL[name]
    found = vertical.EGM2008.at([lon], [lat], grid=os.path.join(DATA, f"egm08-{name}.tif"))
    assert abs(found[0] - expected) < 0.01, (name, found[0])


def _world(path, step=10.0):
    """A whole-earth grid of points every step degrees (pixel-is-point, PROJ's layout: -180 to 180 - step,
    90 to -90), N = lon / 10 + lat / 100 (a jump from +17 to -18 between the last column and the first)."""
    lons = -180 + step * np.arange(round(360 / step))
    lats = 90 - step * np.arange(round(180 / step) + 1)
    band = (lons[None, :] / 10 + lats[:, None] / 100).astype(np.float32)
    with rio.open(path, "w", driver="GTiff", width=len(lons), height=len(lats), count=1, dtype="float32",
                  crs="EPSG:4326", transform=from_origin(-180 - step / 2, 90 + step / 2, step, step)) as dst:
        dst.write(band, 1)
    return path


def test_longitude_wraps_past_180(tmp_path):
    grid = _world(str(tmp_path / "world.tif"))
    at = vertical.EGM2008.at
    # On a point, between two points, and past the last column (170° E) towards the first (-180°) on both sides
    assert at([20.0], [40.0], grid)[0] == pytest.approx(2.4, abs=1e-5)
    assert at([25.0], [45.0], grid)[0] == pytest.approx(2.95, abs=1e-5)
    assert at([175.0], [40.0], grid)[0] == pytest.approx((17.0 + -18.0) / 2 + 0.4, abs=1e-5)
    assert at([-185.0], [40.0], grid)[0] == pytest.approx(at([175.0], [40.0], grid)[0], abs=1e-5)
    assert at([179.0], [40.0], grid)[0] == pytest.approx(17.0 * 0.1 + -18.0 * 0.9 + 0.4, abs=1e-5)
    assert at([0.0], [90.0], grid)[0] == pytest.approx(0.9, abs=1e-5)
    assert at([0.0], [-90.0], grid)[0] == pytest.approx(-0.9, abs=1e-5)


def test_points_outside_a_small_grid(tmp_path):
    with pytest.raises(ValueError):
        vertical.EGM2008.at([0.0], [0.0], grid=os.path.join(DATA, "egm08-nuuk.tif"))


def test_lattice_of_a_block(tmp_path):
    """N of a block from a lattice of 9 x 9 points is within a millimetre of N at every pixel (over a whole-earth
    grid with steep jumps between its points, a stand-in for the real grid's 2.5'), float32 of the block's shape;
    the block's corner pixels are the lattice's."""
    grid = _world(str(tmp_path / "world.tif"), step=0.05)
    transform = from_origin(-150000, -2400000, 2.0, 2.0)  # EPSG:3413, west Greenland
    fast = vertical.EGM2008.undulation("EPSG:3413", transform, (1000, 1000), grid=grid)
    exact = vertical.EGM2008.undulation("EPSG:3413", transform, (1000, 1000), grid=grid, lattice=0)
    assert fast.dtype == np.float32 and fast.shape == (1000, 1000)
    assert np.abs(fast - exact).max() < 0.002
    assert fast[0, 0] == exact[0, 0] and fast[-1, -1] == exact[-1, -1]
    one = vertical.EGM2008.undulation("EPSG:3413", transform, (1, 3), grid=grid)
    assert one.shape == (1, 3) and np.allclose(one, exact[0, :3], atol=1e-4)


def test_no_grid_no_heights():
    geoid = vertical.Geoid("Test", "test", "https://example.invalid/g.tif", "0" * 64, 10, "geoid/test", "")
    with pytest.raises(vertical.GeoidMissing):
        geoid.at([0.0], [0.0])
    assert issubclass(vertical.GeoidMissing, RuntimeError)


def _served_geoid(http_server, tmp_path, body=None, size=None, sha=None):
    grid = _world(str(tmp_path / "world-src.tif"))
    with open(grid, "rb") as f:
        content = f.read()
    http_server.add("/grids/world.tif", body if body is not None else content, "image/tiff")
    return vertical.Geoid("Test geoid", "tg", http_server.url("/grids/world.tif"),
                          sha or hashlib.sha256(content).hexdigest(), size or len(content), "geoid/test", ""), content


def test_grid_downloaded_once(http_server, tmp_path, monkeypatch):
    monkeypatch.setattr(src.net, "_sleep", lambda attempt: None)
    geoid, content = _served_geoid(http_server, tmp_path)
    cache_dir = str(tmp_path / "cache")
    assert geoid.located(cache_dir) is None
    path = geoid.ensure(cache_dir)
    assert path == os.path.join(cache_dir, "geoid", "test", "world.tif") and geoid.grid == path
    with open(path, "rb") as f:
        assert f.read() == content
    assert cache.state(cache_dir, path) == "ok"
    assert geoid.ensure(cache_dir) == path and len(http_server.requests("/grids/")) == 1
    # Another process finds it in the cache (its size) without asking
    again = vertical.Geoid(geoid.name, geoid.tag, geoid.url, geoid.sha256, geoid.size, geoid.folder, "")
    assert again.ensure(cache_dir) == path and len(http_server.requests("/grids/")) == 1
    assert not [n for n in os.listdir(os.path.dirname(path)) if n.endswith(".part")]


def test_grid_with_another_checksum_or_too_large(http_server, tmp_path, monkeypatch):
    monkeypatch.setattr(src.net, "_sleep", lambda attempt: None)
    cache_dir = str(tmp_path / "cache")
    geoid, _ = _served_geoid(http_server, tmp_path, sha="0" * 64)
    with pytest.raises(vertical.GeoidMissing, match="could not be downloaded"):
        geoid.ensure(cache_dir)
    assert len(http_server.requests("/grids/")) == src.net.RETRIES
    folder = os.path.join(cache_dir, "geoid", "test")
    assert geoid.located(cache_dir) is None and not os.listdir(folder)  # nothing kept, no .part left
    small, _ = _served_geoid(http_server, tmp_path, size=1000)            # more bytes come than the cap
    with pytest.raises(vertical.GeoidMissing):
        small.ensure(cache_dir)
    assert not os.listdir(folder)


def _file(path, left, top, band, crs="EPSG:3413"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with rio.open(path, "w", driver="GTiff", width=band.shape[1], height=band.shape[0], count=1, dtype="float32",
                  crs=crs, nodata=-9999.0, transform=from_origin(left, top, 2.0, 2.0), tiled=True,
                  blockxsize=16, blockysize=16) as dst:
        dst.write(np.where(np.isnan(band), -9999.0, band).astype(np.float32), 1)


def test_blocks_cached_above_the_geoid(http_server, tmp_path, monkeypatch):
    """A FileBlocks layer with a geoid caches h - N with the tag "vertical"; its grid is made ready by the layer's
    download; without it, a block asks no file. The same layer without a geoid caches the values as they are."""
    monkeypatch.setattr(src.layer, "DOWNLOAD_THREADS", 1)
    monkeypatch.setattr(src.net, "_sleep", lambda attempt: None)
    band = np.add.outer(np.arange(40) * 0.5, np.arange(40) * 0.25).astype(np.float32) + 100
    band[0, 0] = np.nan
    left, top = -150000.0, -2400000.0
    _file(str(tmp_path / "files" / "a.tif"), left, top, band)
    http_server.add_folder("/files", str(tmp_path / "files"))
    geoid, _ = _served_geoid(http_server, tmp_path)
    url = http_server.url("/files/a.tif")
    with pytest.raises(ValueError, match="-tg"):
        FileBlocks("H", "test/h", "EPSG:3413", 2.0, 40, url, geoid=geoid)
    layer = FileBlocks("H", "test/h-tg", "EPSG:3413", 2.0, 40, url, geoid=geoid)
    plain = FileBlocks("H", "test/h", "EPSG:3413", 2.0, 40, url)
    grid = gd.make_grid((left + 2, top - 78, left + 78, top - 2), 2.0, "EPSG:3413")
    tile = (-3750, -60001)  # the block at the file's top left corner
    assert tile in layer.tiles(grid)
    cache_dir = str(tmp_path / "cache")
    with pytest.raises(vertical.GeoidMissing):    # the reader alone: no grid made ready yet
        layer.download_tile(tile, str(tmp_path / "x.tif"))
    assert not http_server.requests("/files/")
    layer.download(grid, cache_dir, None, "test")
    plain.download(grid, cache_dir, None, "test")
    with rio.open(layer.tile_path(cache_dir, tile)) as moved, rio.open(plain.tile_path(cache_dir, tile)) as kept:
        n = geoid.undulation("EPSG:3413", moved.transform, moved.shape)
        assert moved.tags()["vertical"] == "Test geoid" and "vertical" not in kept.tags()
        assert np.abs(n).min() > 1
        values, raw = moved.read(1), kept.read(1)
        assert np.isnan(values[0, 0]) and np.isnan(raw[0, 0])
        assert same_tile(values[1:, 1:], (raw - n)[1:, 1:], 2 * TILE_EPS)  # two tiles, each within the bound
        assert same_tile(raw[1:, 1:], band[:20, :20][1:, 1:])


def test_check_source_compares_after_the_geoid(http_server, tmp_path, monkeypatch):
    """tools/check_source.py's file comparison applies the layer's geoid as the layer does: equal values."""
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
    import check_source as cs
    monkeypatch.setattr(src.layer, "DOWNLOAD_THREADS", 1)
    band = np.add.outer(np.arange(40) * 0.5, np.arange(40) * 0.25).astype(np.float32) + 100
    left, top = -150000.0, -2400000.0
    _file(str(tmp_path / "files" / "a.tif"), left, top, band)
    http_server.add_folder("/files", str(tmp_path / "files"))
    geoid, _ = _served_geoid(http_server, tmp_path)
    layer = FileBlocks("H", "test/h-tg", "EPSG:3413", 2.0, 40, http_server.url("/files/a.tif"), geoid=geoid)
    grid = gd.make_grid((left + 2, top - 78, left + 78, top - 2), 2.0, "EPSG:3413")
    cache_dir = str(tmp_path / "cache")
    layer.download(grid, cache_dir, None, "test")
    check = cs.check_files(layer, grid, cache_dir, 4)
    assert check["status"] == cs.PASS and all(r["max_abs_m"] <= TILE_EPS for r in check["tiles"]), check["text"]
