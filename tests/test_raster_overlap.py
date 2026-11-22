"""tools/raster_overlap.py: where rasters of one pixel grid overlap (pixels valid in both, in one only, their
differences) and how low each raster's values go, read in bands of rows, from plain files and ZIPs."""

import json
import os
import sys
import zipfile

import numpy as np
import pytest
import rasterio as rio
from rasterio.transform import from_origin

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
import raster_overlap as ro  # noqa: E402


def _tif(path, values, left, top, res=1.0, nodata=None, crs="EPSG:3812"):
    with rio.open(path, "w", driver="GTiff", width=values.shape[1], height=values.shape[0], count=1,
                  dtype="float32", crs=crs, transform=from_origin(left, top, res, res), nodata=nodata,
                  compress="lzw", blockysize=5) as dst:
        dst.write(values.astype(np.float32), 1)
    return str(path)


def _pair(tmp_path):
    """A (100 x 80 px from x 1000, top 600; -9999 its tag) and B (80 x 80 px from x 1060, the same top; NaN and
    -32768, a value only --nodata names): they share 40 columns. In the shared box A is valid in columns 60-89, B in
    70-99 (of A's), so 20 columns are valid in both: equal but for five pixels 3 mm, 2 cm, 0.3 m, 1 m and 10 m off.
    A holds four values below 10 m and one below 0."""
    rng = np.random.default_rng(1)
    truth = (200 + rng.random((80, 140)) * 50).round(3).astype(np.float32)
    a = truth[:, :100].copy()
    a[:, 90:] = -9999.0
    b = truth[:, 60:].copy()
    b[:, :10] = np.nan
    b[:, 30:] = -32768.0
    for (r, c), d in zip(((5, 15), (6, 15), (7, 16), (8, 17), (9, 18)), (0.003, 0.02, 0.3, 1.0, 10.0)):
        b[r, c] += d  # B's columns 10-29 are A's 70-89
    a[50, 20], a[51, 22], a[60, 30], a[70, 5] = -5.0, 3.0, 9.0, 9.5
    return _tif(tmp_path / "a.tif", a, 1000.0, 600.0, nodata=-9999.0), _tif(tmp_path / "b.tif", b, 1060.0, 600.0)


def test_a_seam_its_differences_and_the_low_values(tmp_path):
    """The shared box's counts and differences in their bins (an exact 0, then at most 5 mm, 5 cm, 0.5 m, 5 m and
    above), the low values' counts, boxes and the lowest pixel; the same in bands of one row; a raster apart
    makes no pair."""
    a, b = _pair(tmp_path)
    far = _tif(tmp_path / "far.tif", np.full((10, 10), 300.0), 5000.0, 600.0)
    result = ro.measure([a, b, far], nodata=[-32768.0])
    assert len(result["pairs"]) == 1
    pair = result["pairs"][0]
    assert pair["box"] == [1060.0, 520.0, 1100.0, 600.0]
    assert (pair["valid_both"], pair["valid_a_only"], pair["valid_b_only"]) == (20 * 80, 10 * 80, 0)
    assert pair["histogram"] == {"0": 1600 - 5, "<= 5 mm": 1, "<= 5 cm": 1, "<= 0.5 m": 1, "<= 5 m": 1, "> 5 m": 1}
    assert abs(pair["max_abs_diff_m"] - 10.0) < 1e-3
    low = result["rasters"][0]
    assert low["valid"] == 90 * 80 and low["lowest_m"] == -5.0 and low["lowest_at"] == [1020.5, 549.5]
    assert low["below"] == [{"threshold_m": 0.0, "valid_below": 1, "box": [1020.0, 549.0, 1021.0, 550.0]},
                            {"threshold_m": 10.0, "valid_below": 4, "box": [1005.0, 529.0, 1031.0, 550.0]}]
    assert result["rasters"][1]["valid"] == 20 * 80 and result["rasters"][1]["below"][1]["valid_below"] == 0
    assert result["rasters"][1]["below"][0]["box"] is None
    banded = ro.measure([a, b, far], nodata=[-32768.0], max_memory_gb=1e-9)  # one row a band
    assert ro.rows_per_band(140, 1e-9) == 1 and banded == result
    without = ro.measure([a, b], nodata=[])  # -32768 is a value then: valid in B (where A has none)
    assert without["pairs"][0]["valid_b_only"] == 10 * 80 and without["pairs"][0]["valid_both"] == 1600
    assert without["rasters"][1]["lowest_m"] == -32768.0 and without["rasters"][1]["valid"] == 70 * 80


def test_zip_members_the_table_and_the_json(tmp_path, capsys):
    """A ZIP of one .tif is read as its /vsizip/ member (two .tif members are refused); the command line prints the
    table and writes the JSON; rasters off one grid stop with exit 2."""
    a, b = _pair(tmp_path)
    with zipfile.ZipFile(tmp_path / "a.zip", "w", zipfile.ZIP_DEFLATED) as z:
        z.write(a, "inner/A.tif")
        z.writestr("inner/A.tfw", "1\n0\n0\n-1\n1000.5\n599.5\n")
    assert ro.readable_path(str(tmp_path / "a.zip")) == f"/vsizip/{tmp_path / 'a.zip'}/inner/A.tif"
    out = tmp_path / "r.json"
    assert ro.main([str(tmp_path / "a.zip"), b, "--nodata", "-32768", "--json", str(out)]) == 0
    text = capsys.readouterr().out
    assert "a.zip | " in text and "| 1,600 | 800 | 0 | 10.0000 | 1,595 | 1 | 1 | 1 | 1 | 1 |" in text
    assert json.loads(out.read_text())["pairs"][0]["valid_both"] == 1600
    with zipfile.ZipFile(tmp_path / "two.zip", "w") as z:
        z.write(a, "A.tif")
        z.write(b, "B.tif")
    with pytest.raises(ValueError, match="2 .tif members, one expected"):
        ro.readable_path(str(tmp_path / "two.zip"))
    off = _tif(tmp_path / "off.tif", np.full((10, 10), 1.0), 1000.5, 600.0)  # half a pixel off
    coarse = _tif(tmp_path / "coarse.tif", np.full((10, 10), 1.0), 1000.0, 600.0, res=2.0)
    other = _tif(tmp_path / "other.tif", np.full((10, 10), 1.0), 1000.0, 600.0, crs="EPSG:31370")
    for bad, words in ((off, "not a whole number of pixels"), (coarse, "2 m pixels"), (other, "EPSG:31370")):
        assert ro.main([a, bad]) == 2
        assert words in capsys.readouterr().err
    with pytest.raises(ValueError, match="two rasters or more"):
        ro.measure([a])
