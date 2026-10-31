"""tools/check_source.py: its metrics, and a whole run on the Żabi Koń clip (offline)."""

import json
import os
import sys

import numpy as np
import pytest
import rasterio as rio
from affine import Affine
from rasterio.warp import transform as warp

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools"))
import check_source as cs  # noqa: E402

CLIP = os.path.join(REPO, "tests", "data", "zabi_kon_nmt.tif")


def test_shift_table_finds_a_moved_copy():
    rng = np.random.default_rng(1)
    reference = rng.normal(300, 20, (40, 40)).astype(np.float32)
    raw = np.full_like(reference, np.nan)
    raw[:, 3:] = reference[:, :-3]  # the data placed 3 pixels east: the correction is 3 west
    raw[:-2, :] = raw[2:, :].copy()  # and 2 pixels north: 2 south
    raw[-2:, :] = np.nan
    table = cs.shift_table(raw, reference, 5)
    assert cs.best_shift(table) == (-3, -2)
    assert table[(-3, -2)][0] == 0.0 and table[(0, 0)][0] > 1
    assert set(cs.shift_table(raw, reference, 4, step_px=2)) <= {(i, j) for i in range(-4, 5, 2)
                                                                    for j in range(-4, 5, 2)}


def test_best_shift_prefers_the_nearest_of_equals():
    table = {(0, 0): (1.0, 0.0, 10), (1, 0): (1.0, 0.0, 10), (-2, 0): (0.5, 0.1, 10), (2, 0): (0.5, 0.1, 10)}
    assert cs.best_shift(table) == (-2, 0)
    assert cs.best_shift({(0, 0): (1.0, 0.0, 1), (1, 1): (1.0, 0.0, 1)}) == (0, 0)


def test_valid_share_and_precision():
    values = np.array([[1.0, np.nan], [2.5, 3.25]], dtype=np.float32)
    assert cs.valid_share(values, np.ones((2, 2), bool)) == 0.75
    assert cs.valid_share(values, np.array([[False, True], [False, False]])) == 0.0
    assert cs.valid_share(values, np.zeros((2, 2), bool)) == 0.0
    assert cs.precision(values) == (pytest.approx(1 / 3), 1.0)
    assert cs.precision(np.array([123.45, 7.0, 1.234], dtype=np.float32)) == (pytest.approx(1 / 3),
                                                                             pytest.approx(2 / 3))
    assert cs.precision(np.full(3, np.nan)) == (0.0, 0.0)


def test_compare_and_origin_offset():
    tile = np.array([[1.0, 2.0], [np.nan, 4.0]])
    assert cs.compare(tile, tile.copy()) == {"pixels": 3, "max_abs_m": 0.0, "equal": 1.0, "same_nodata": 1.0}
    other = np.array([[1.0, 2.5], [5.0, np.nan]])
    found = cs.compare(tile, other)
    assert found["max_abs_m"] == 0.5 and found["equal"] == 0.5 and found["same_nodata"] == 0.5
    # A block composed from several files: only where the source has data
    assert cs.compare(tile, np.array([[1.0, np.nan], [np.nan, np.nan]]), source_only=True)["same_nodata"] == 1.0
    assert cs.origin_offset(Affine(1, 0, 553665.5, 0, -1, 254908.5), 1.0, (0.5, 0.5)) == 0.0
    assert cs.origin_offset(Affine(1, 0, 553665.0, 0, -1, 254908.5), 1.0, (0.5, 0.5)) == 0.5
    assert cs.origin_offset(Affine(2, 0, 100.25, 0, -2, 0.0), 2.0, (0.0, 0.0)) == 0.25


@pytest.fixture
def offline(monkeypatch):
    for name in ("HTTP_PROXY", "HTTPS_PROXY"):
        monkeypatch.setenv(name, "http://127.0.0.1:9")
    monkeypatch.setenv("NO_PROXY", "")


def _centre():
    with rio.open(CLIP) as clip:
        b = clip.bounds
    x, y = warp("EPSG:2180", "EPSG:4326", [(b.left + b.right) / 2], [(b.bottom + b.top) / 2])
    return y[0], x[0]


def _moved(tmp_path, east: float) -> str:
    """A copy of the clip whose georeference is east metres further east."""
    path = str(tmp_path / "moved.tif")
    with rio.open(CLIP) as clip:
        profile = clip.profile
        values = clip.read(1)
    profile["transform"] = Affine.translation(east, 0) @ profile["transform"]
    with rio.open(path, "w", **profile) as out:
        out.write(values, 1)
    return path


def _run(tmp_path, elevation: str, reference: str) -> dict:
    lat, lon = _centre()
    out = tmp_path / "result.json"
    code = cs.main(["files", "--elevation-file", elevation, "--reference", reference, "--lat", str(lat),
                    "--lon", str(lon), "--radius", "150", "--shift-range", "60", "--data-dir", str(tmp_path / "data"),
                    "--json", str(out)])
    result = json.loads(out.read_text(encoding="utf-8"))
    assert code == 0
    assert [layer["layer"] for layer in result["layers"]] == ["nmt"]
    return {c["name"]: c for c in result["layers"][0]["checks"]}


def test_clip_against_itself(tmp_path, offline):
    checks = _run(tmp_path, CLIP, CLIP)
    assert checks["shift"]["status"] == "PASS"
    assert checks["shift"]["best_m"] == [0, 0] and checks["shift"]["median_abs_m"] == 0.0
    assert checks["valid"]["valid_1m"] == 1.0 and checks["valid"]["valid_5m"] == 1.0
    assert checks["valid"]["status"] == "PASS"
    assert checks["files"]["status"] == "n/a" and checks["missing"]["status"] == "n/a"
    assert checks["alignment"]["status"] == "PASS" and checks["alignment"]["edge_offset_m"] == 0.0
    assert checks["precision"]["status"] == "PASS"
    assert os.listdir(tmp_path / "data" / "work") == []  # the work folder is deleted


def test_clip_moved_east(tmp_path, offline):
    """Data placed 20 m east of the reference needs a correction of 20 m west."""
    checks = _run(tmp_path, _moved(tmp_path, 20), CLIP)
    assert checks["shift"]["best_m"] == [-20, 0] and checks["shift"]["shift"] == [-20, 0]
    assert checks["shift"]["median_abs_m"] < 0.01 < checks["shift"]["zero_median_abs_m"]
    assert checks["shift"]["status"] == "PASS"  # within 30 m
