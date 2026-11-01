"""The source of Luxembourg (sources/catalogue/luxembourg.py): blocks of 1 km read from the national 0.5 m COGs on
their own pixels, the 1 m working grid averaging them, and --source auto, also offline. No network."""

import os
import sys

import numpy as np
import requests
from rasterio.transform import from_origin

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import osm  # noqa: E402
import sources as src  # noqa: E402
from grid import make_grid  # noqa: E402
from sources.catalogue import luxembourg  # noqa: E402
from sources.layer import _write_tile  # noqa: E402


def test_blocks_of_the_national_files():
    """Blocks of 1 km of 2000 x 2000 pixels of 0.5 m (edges on whole kilometres, which lie on the
    files' 0.5 m lattice from 48 880.5 m), in the upload's folder; one partly over a file reads it,
    one beyond its extent is missing without a request."""
    source = src.SOURCES["luxembourg"]
    for layer, kind in ((source.nmt, "MNT"), (source.nmpt, "MNS")):
        url = f"{luxembourg.LU_FILES}/{kind}_Lidar2024.tif"
        assert layer.folder == f"luxembourg/lidar2024-{kind.lower()}/20241223" and layer.native_res == 0.5
        request = layer.index.request((92, 98))
        assert request.files == [(f"{kind}_Lidar2024.tif", url, 2024)] and request.shape == (2000, 2000)
        assert request.transform == from_origin(92000.0, 99000.0, 0.5, 0.5)
        col = (request.transform.c - luxembourg.LU_EXTENT[0]) / 0.5
        assert col == round(col)  # on the files' own pixels: copied, never resampled
        for inside in ((48, 56), (106, 138)):  # the files start at 48 880.5 / 56 965.5 m, end at 106 189 / 138 809 m
            assert layer.index.request(inside).files, inside
        for outside in ((47, 100), (107, 100), (80, 55), (80, 139)):
            assert layer.index.request(outside).files == [], outside


def test_one_metre_grid_averages_the_pixels(tmp_path):
    """The default working grid is 1 m in LUREF with edges on whole metres: each of its pixels is the
    mean of 2 x 2 cached pixels of 0.5 m, never interpolated half a pixel off."""
    source = src.SOURCES["luxembourg"]
    assert source.default_resolution == 1.0 and source.crs == "EPSG:2169" and source.grid_origin == (0.0, 0.0)
    rows, cols = np.mgrid[0:2000, 0:2000]
    block = (300.0 + 0.01 * ((rows * 7 + cols * 13) % 1000)).astype(np.float32)  # centimetres, like the data
    path = str(tmp_path / "92_98.tif")
    _write_tile(path, block, "EPSG:2169", from_origin(92000.0, 99000.0, 0.5, 0.5))
    grid = make_grid((92100.3, 98100.7, 92400.2, 98400.6), 1.0, "EPSG:2169", origin=source.grid_origin)
    assert (grid.left, grid.top) == (92100.0, 98401.0)
    mosaic = np.asarray(src.build_mosaic([path], grid, str(tmp_path / "nmt.npy"), "test"))
    expected = block.reshape(1000, 2, 1000, 2).mean(axis=(1, 3))  # the block's 1 m means
    r0, c0 = round(99000.0 - grid.top), round(grid.left - 92000.0)
    assert np.allclose(mosaic, expected[r0:r0 + grid.height, c0:c0 + grid.width], atol=1e-4)


def test_texts_fit_a_windows_console():
    """Names, descriptions and the note are printed to the console (cp1250)."""
    source = src.SOURCES["luxembourg"]
    for text in (source.name, source.description, source.note, source.nmt.description, source.nmpt.description):
        text.encode("cp1250")


def test_auto_offline(tmp_path, monkeypatch):
    """Offline, the country box decides: Luxembourg at the sample and in the Sûre valley, europe
    beyond the box."""
    def offline(*args, **kwargs):
        raise requests.ConnectionError("offline")
    monkeypatch.setattr(osm, "reverse", offline)
    cache_dir = str(tmp_path)
    for (lat, lon), sid in {src.SOURCES["luxembourg"].sample: "luxembourg",
                            (49.8695, 6.1650): "luxembourg",   # Bourscheid, the Sûre valley
                            (50.40, 6.10): "europe"}.items():  # the Belgian Eifel, north of the box
        source, reason = src.choose_source("auto", lat, lon, cache_dir)
        assert source.id == sid, (lat, lon, reason)
