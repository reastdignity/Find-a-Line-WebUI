"""tools/study_ortho.py on fake orthophoto tiles in a scratch cache (nothing downloaded): the GLI and
luminance of a green, a grey and a dark tile on a Web Mercator grid, a pixel on two tiles' edge, a
tile that failed, a service of base tiles only, the threshold's values and its None rule, and the
files of a call."""

import json
import math
import os
import sys
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image
from pyproj import Transformer

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools"))
import orthophoto  # noqa: E402
import sources  # noqa: E402
import study_ortho  # noqa: E402

LAT, LON = 50.1559508, 19.7562722
Z = study_ortho.ZOOM
GREEN, GREY, DARK = (60, 140, 50), (128, 128, 128), (20, 22, 20)
PX = 16  # grid pixels a tile


def _gli(rgb):
    r, g, b = rgb
    return (2 * g - r - b) / (2 * g + r + b)


def _tile0():
    """The zoom-Z tile holding the place."""
    x, y = orthophoto._to_mercator.transform(LON, LAT)
    size = orthophoto._tile_size(Z)
    return math.floor((x + orthophoto._EARTH) / size), math.floor((orthophoto._EARTH - y) / size)


def _colour(x0, x):
    return GREEN if x <= x0 else GREY if x == x0 + 1 else DARK


def _write(folder, z, x, y, rgb):
    path = orthophoto.tile_path(folder, z, x, y)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    Image.new("RGB", (orthophoto.TILE_PX, orthophoto.TILE_PX), rgb).save(path, "JPEG", quality=95)


def _setup(tmp_path, monkeypatch, service, shift=0.0):
    """A grid of three tiles of zoom Z in a row (green, grey, dark), PX pixels a tile, moved by shift
    pixels to the east; one line along the row; every tile its strips reach written as a JPEG."""
    monkeypatch.setitem(sources.SOURCES, "fake", SimpleNamespace(ortho=service))
    x0, y0 = _tile0()
    left, _, _, top = orthophoto.mercator_box(Z, x0, y0)
    res = orthophoto._tile_size(Z) / PX
    grid = {"crs": "EPSG:3857", "left": left + shift * res, "top": top, "res": res, "height": PX,
            "width": 3 * PX}
    back = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)
    lon1, lat1 = back.transform(left + PX / 2 * res, top - PX / 2 * res)
    lon2, lat2 = back.transform(left + 5 * PX / 2 * res, top - PX / 2 * res)
    lines = [{"anchor1": (lat1, lon1), "anchor2": (lat2, lon2)}]
    cache_dir = str(tmp_path / "cache")
    return grid, lines, cache_dir, x0, y0


def _service(url="https://wms.example/ortho", base_max_zoom=19):
    return sources.OrthoService("Fake orthophoto", url, "Raster", "fake/ortho", "nobody",
                                base_url="https://tiles.example/{z}/{x}/{y}.jpg", base_max_zoom=base_max_zoom)


def _no_download(*args, **kwargs):
    raise AssertionError("nothing to download")


def _write_all(grid, lines, cache_dir, service, x0, zoom=Z):
    folder = orthophoto.cache_folder(cache_dir, service)
    lat = study_ortho._latitude(grid)
    tiles = orthophoto.strip_tiles(lines, [zoom], 1 / math.cos(math.radians(lat)))
    for z, x, y in tiles:
        _write(folder, z, x, y, _colour(x0 >> (Z - zoom), x))
    return tiles


def test_greenness_of_the_tiles(tmp_path, monkeypatch):
    """Each tile's GLI and luminance on its pixels of the grid; nothing downloaded when all are cached."""
    service = _service()
    grid, lines, cache_dir, x0, y0 = _setup(tmp_path, monkeypatch, service)
    tiles = _write_all(grid, lines, cache_dir, service, x0)
    assert {(Z, x0 + i, y0) for i in range(3)} <= tiles
    monkeypatch.setattr(orthophoto, "download", _no_download)
    gli, lum, n = study_ortho.greenness_on_grid(grid, "fake", lines, cache_dir)
    assert n == len(tiles)
    assert gli.shape == lum.shape == (PX, 3 * PX) and gli.dtype == lum.dtype == np.float32
    assert np.isfinite(gli).all() and np.isfinite(lum).all()
    for i, rgb in enumerate((GREEN, GREY, DARK)):
        part = (slice(None), slice(i * PX, (i + 1) * PX))
        assert np.allclose(gli[part], _gli(rgb), atol=0.02), (i, gli[part].min(), gli[part].max())
        assert np.allclose(lum[part], sum(rgb) / 3, atol=2)
    assert gli[:, :PX].mean() > gli[:, PX:2 * PX].mean() + 0.15


def test_pixel_on_two_tiles(tmp_path, monkeypatch):
    """A pixel half on the green tile and half on the grey one: the mean of both."""
    service = _service()
    grid, lines, cache_dir, x0, _ = _setup(tmp_path, monkeypatch, service, shift=0.5)
    _write_all(grid, lines, cache_dir, service, x0)
    monkeypatch.setattr(orthophoto, "download", _no_download)
    gli, lum, _ = study_ortho.greenness_on_grid(grid, "fake", lines, cache_dir)
    edge = PX - 1  # the grid's column from the middle of the green tile's last pixel column on
    assert np.allclose(gli[:, edge], (_gli(GREEN) + _gli(GREY)) / 2, atol=0.02)
    assert np.allclose(lum[:, edge], (sum(GREEN) + sum(GREY)) / 6, atol=2)
    assert np.allclose(gli[:, edge - 1], _gli(GREEN), atol=0.02)


def test_failed_tile_and_no_service(tmp_path, monkeypatch):
    """A tile still missing after its download is NaN; a source without an orthophoto gives NaN only."""
    service = _service()
    grid, lines, cache_dir, x0, y0 = _setup(tmp_path, monkeypatch, service)
    tiles = _write_all(grid, lines, cache_dir, service, x0)
    folder = orthophoto.cache_folder(cache_dir, service)
    os.remove(orthophoto.tile_path(folder, Z, x0 + 1, y0))
    asked = []
    monkeypatch.setattr(orthophoto, "download", lambda s, t, f, c: asked.append((s, list(t), f, c)) or (0, 0))
    gli, lum, n = study_ortho.greenness_on_grid(grid, "fake", lines, cache_dir)
    assert asked == [(service, [(Z, x0 + 1, y0)], folder, cache_dir)]
    assert n == len(tiles) - 1
    assert np.isnan(gli[:, PX + 1:2 * PX - 1]).all() and np.isnan(lum[:, PX + 1:2 * PX - 1]).all()
    assert np.isfinite(gli[:, :PX]).all() and np.isfinite(gli[:, 2 * PX:]).all()

    monkeypatch.setitem(sources.SOURCES, "none", SimpleNamespace(ortho=None))
    gli, lum, n = study_ortho.greenness_on_grid(grid, "none", lines, cache_dir)
    assert n == 0 and np.isnan(gli).all() and np.isnan(lum).all()


def test_base_tiles_only_at_their_last_zoom(tmp_path, monkeypatch):
    """A service without a WMS is asked at its base_max_zoom when that is below ZOOM."""
    service = _service(url=None, base_max_zoom=Z - 1)
    grid, lines, cache_dir, x0, _ = _setup(tmp_path, monkeypatch, service)
    asked = []
    monkeypatch.setattr(orthophoto, "download", lambda s, t, f, c: asked.append(list(t)) or (0, 0))
    gli, _, n = study_ortho.greenness_on_grid(grid, "fake", lines, cache_dir)
    assert n == 0 and np.isnan(gli).all()
    assert asked and {z for z, _, _ in asked[0]} == {Z - 1}

    tiles = _write_all(grid, lines, cache_dir, service, x0, zoom=Z - 1)
    monkeypatch.setattr(orthophoto, "download", _no_download)
    gli, _, n = study_ortho.greenness_on_grid(grid, "fake", lines, cache_dir)
    assert n == len(tiles) and np.isfinite(gli).all()


def test_threshold():
    """tau halfway between the medians, dark the 5th percentile of the forest's luminance, overlap the
    share on the wrong side of tau; None for a set under MIN_PIXELS."""
    rng = np.random.default_rng(3)
    gli = np.concatenate([rng.normal(0.2, 0.05, 400), rng.normal(0.0, 0.05, 400), [np.nan] * 200])
    lum = np.concatenate([rng.uniform(20, 120, 400), rng.uniform(80, 200, 400), [np.nan] * 200])
    forest = np.zeros(1000, bool)
    forest[:400] = True
    forest[800:900] = True  # without an orthophoto: not counted
    rock = np.zeros(1000, bool)
    rock[400:800] = True
    out = study_ortho.threshold(gli, lum, forest, rock)
    f, r = gli[:400], gli[400:800]
    assert out["forest_median"] == pytest.approx(np.median(f))
    assert out["rock_median"] == pytest.approx(np.median(r))
    assert out["tau"] == pytest.approx((np.median(f) + np.median(r)) / 2)
    assert out["dark"] == pytest.approx(np.percentile(lum[:400], 5))
    assert out["overlap"] == pytest.approx(((f < out["tau"]).sum() + (r > out["tau"]).sum()) / 800)
    assert 0 < out["overlap"] < 0.1
    # The luminance's split: bright halfway between the medians (the rock brighter), the share of
    # the forest at bright or above and of the rock below it
    fl, rl = lum[:400], lum[400:800]
    assert out["bright"] == pytest.approx((np.median(fl) + np.median(rl)) / 2)
    assert out["bright_overlap"] == pytest.approx(((fl >= out["bright"]).sum() + (rl < out["bright"]).sum()) / 800)
    assert 0.1 < out["bright_overlap"] < 0.4  # the ranges overlap from 80 to 120
    same = study_ortho.threshold(gli, np.where(np.isnan(lum), np.nan, 100.0), forest, rock)  # one luminance: one side
    assert same["bright"] == 100.0 and same["bright_overlap"] == pytest.approx(0.5)

    few = np.zeros(1000, bool)
    few[400:449] = True
    out = study_ortho.threshold(gli, lum, forest, few)
    assert out["rock_median"] is None and out["tau"] is None and out["overlap"] is None
    assert out["bright"] is None and out["bright_overlap"] is None
    assert out["forest_median"] is not None and out["dark"] is not None
    out = study_ortho.threshold(gli, lum, np.zeros(1000, bool), rock)
    assert out == {"tau": None, "dark": None, "forest_median": None,
                   "rock_median": pytest.approx(np.median(r)), "overlap": None, "bright": None,
                   "bright_overlap": None}


def test_write_greenness(tmp_path, monkeypatch):
    """ortho-gli.npy, ortho-lum.npy and ortho.json in the call's folder."""
    service = _service()
    grid, lines, cache_dir, x0, _ = _setup(tmp_path, monkeypatch, service)
    tiles = _write_all(grid, lines, cache_dir, service, x0)
    monkeypatch.setattr(orthophoto, "download", _no_download)
    call = tmp_path / "call-0"
    call.mkdir()
    info = study_ortho.write_greenness(str(call), grid, "fake", lines, cache_dir)
    gli, lum = np.load(call / "ortho-gli.npy"), np.load(call / "ortho-lum.npy")
    assert gli.shape == lum.shape == (PX, 3 * PX) and gli.dtype == np.float32
    with open(call / "ortho.json", encoding="utf-8") as f:
        saved = json.load(f)
    assert saved == info == {"zoom": Z, "tiles": len(tiles), "tau": None, "dark": None,
                             "forest_median": None, "rock_median": None, "overlap": None}
