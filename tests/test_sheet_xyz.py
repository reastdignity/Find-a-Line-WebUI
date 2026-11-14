"""SheetFile's XYZ and ASCII grids beyond the plain case (sources/readers/sheetfile.py), as GUGiK's NMT sheets of
survey 70159 (2018, PL-2000 zone 6, listed at 1 m) were found on 2026-11-14: a UTF-8 BOM, 5 m grids on whole metres,
patchworks of a 1 m grid (centres on .5) and a 5 m one, an empty file in its ZIP, a broken line."""

import io
import os
import sys
import zipfile

import numpy as np
import pytest
from rasterio.errors import RasterioIOError
from rasterio.transform import from_origin

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import sources as src  # noqa: E402
from sources import net  # noqa: E402
from sources.readers import sheetfile as sf  # noqa: E402
from sources.readers.sheetfile import SheetFile  # noqa: E402

CRS = "EPSG:2177"


def _lines(points, sep="\t", newline="\r\n", decimals=2) -> bytes:
    return "".join(f"{x:.{decimals}f}{sep}{y:.{decimals}f}{sep}{z:.2f}{newline}" for x, y, z in points).encode()


def _grid_points(left, top, step, rows, cols, seed, centre=0.5):
    """Points of a grid of rows x cols cells of step m, centres at left + (c + centre) * step, rows from the north."""
    rng = np.random.default_rng(seed)
    z = np.round(rng.uniform(50, 90, (rows, cols)), 2)
    return [(left + (c + centre) * step, top - (r + centre) * step, z[r, c]) for r in range(rows) for c in range(cols)]


def _zip(name, data) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(name, data)
    return buffer.getvalue()


def _fetch(monkeypatch, tmp_path, content, url="https://example/70159_1_s.xyz.zip"):
    class Response:
        def __init__(self):
            self.content, self.url, self.headers = content, url, {}
    monkeypatch.setattr(net, "_get", lambda url, **kw: Response())
    sheet = src.Sheet(year=2018, name="s", godlo="6.175.12.02.1", url=url, crs=CRS, res=1.0)
    path = str(tmp_path / "s.tif")
    fetched = SheetFile("NMT").fetch(sheet, path)
    return fetched, path


def _read(path):
    from rasterio import open as rio_open
    with rio_open(path) as ds:
        return ds.read(1), ds.transform


def test_plain_grid_as_before():
    """One grid at the listed resolution: the raster on its points' cells, as ever."""
    points = _grid_points(6430400, 5800000, 1.0, 3, 4, 1)
    band, transform = sf._xyz_grid(_lines(points), 1.0, CRS)
    assert band.shape == (3, 4) and transform == from_origin(6430400, 5800000, 1.0, 1.0)
    assert band[0, 0] == np.float32(points[0][2]) and band[2, 3] == np.float32(points[-1][2])


def test_a_byte_order_mark_is_left_out():
    """np.loadtxt read the BOM as part of the first number ("could not convert string 'ï»¿6430405.00'")."""
    points = _grid_points(6430400, 5800000, 1.0, 2, 2, 2)
    band, _ = sf._xyz_grid(sf.BOM + _lines(points), 1.0, CRS)
    plain, _ = sf._xyz_grid(_lines(points), 1.0, CRS)
    assert np.array_equal(band, plain)


def test_a_coarser_grid_is_written_at_its_spacing(capsys):
    """A sheet listed at 1 m holding a 5 m grid on whole metres: written at 5 m (not a 1 m raster with one pixel
    in 25), said."""
    points = _grid_points(6429600, 5800000, 5.0, 4, 6, 3, centre=1.0)  # centres on whole metres, multiples of 5
    band, transform = sf._xyz_grid(sf.BOM + _lines(points), 1.0, CRS, "sheet")
    assert band.shape == (4, 6) and np.isfinite(band).all()
    assert transform == from_origin(6429602.5, 5799997.5, 5.0, 5.0)
    assert "points 5 m apart, not the 1 m listed" in capsys.readouterr().out


def test_a_patchwork_on_the_finest_grid(capsys):
    """A 1 m grid (centres on .5) over the west half and a 5 m grid (centres on whole metres) over the east: one
    1 m raster over their union, the 1 m points as they are, the east from the 5 m grid resampled bilinearly
    (a plane stays a plane)."""
    def height(x, y):
        return 0.01 * (x - 6430400) + 0.02 * (y - 5799900)
    fine = [(x, y, height(x, y)) for x, y, _ in _grid_points(6430400, 5800000, 1.0, 20, 10, 0)]
    coarse = [(x, y, height(x, y)) for x, y, _ in _grid_points(6430410, 5800000, 5.0, 4, 2, 0, centre=1.0)]
    band, transform = sf._xyz_grid(_lines(fine + coarse, decimals=2), 1.0, CRS, "sheet")
    # the union of the 1 m cells (x 0-10, y -20-0 from the corner) and the 5 m ones (x 12.5-22.5, y -22.5 to -2.5)
    assert transform == from_origin(6430400, 5800000, 1.0, 1.0) and band.shape == (23, 23)
    rows, cols = band.shape
    x = transform.c + (np.arange(cols) + 0.5)[None, :]
    y = transform.f - (np.arange(rows) + 0.5)[:, None]
    expected = height(x, y)
    west = np.isfinite(band) & (x < 6430410)
    inside = (x > 6430415) & (x < 6430420) & (y > 5799980) & (y < 5799995)  # between the 5 m grid's centres
    assert west.sum() == 200 and np.isnan(band[:, 10:12]).all()  # the gap between the two stays empty
    assert np.allclose(band[west], expected[west], atol=0.006)
    assert np.isfinite(band[inside]).all() and np.allclose(band[inside], expected[inside], atol=0.006)
    assert "2 grids in one file (200 at 1 m, 8 at 5 m)" in capsys.readouterr().out


def test_a_few_broken_lines_are_left_out(capsys):
    """One line of four fields in a sheet: left out and said; many such lines are no XYZ grid, an error."""
    points = _grid_points(6430400, 5800000, 1.0, 40, 40, 4)
    lines = _lines(points).split(b"\r\n")
    lines[700] = lines[700] + b"\t12.5"
    band, _ = sf._xyz_grid(b"\r\n".join(lines), 1.0, CRS, "sheet")
    assert np.isnan(band.flat[700]) and np.isfinite(band).sum() == 1599
    assert "1 of 1601 lines are not x y z" in capsys.readouterr().out
    for i in range(0, 1600, 100):
        lines[i] = b"<html>"
    with pytest.raises(RuntimeError, match="lines are not x y z"):
        sf._xyz_grid(b"\r\n".join(lines), 1.0, CRS)


def test_a_near_duplicate_point_does_not_set_the_spacing():
    """A point repeated 3 mm off right after itself (same lattice offset, millimetre coordinates): the smallest step
    alone made a raster of 3 mm cells; the grid stays 1 m and its size."""
    points = _grid_points(6430400, 5800000, 1.0, 30, 30, 7)
    x, y, z = points[100]
    points.insert(101, (x + 0.003, y, z))
    band, transform = sf._xyz_grid(_lines(points, decimals=3), 1.0, CRS, "sheet")
    assert band.shape == (30, 30) and transform == from_origin(6430400, 5800000, 1.0, 1.0)
    assert np.isfinite(band).all()


def test_millimetre_jitter_keeps_the_listed_spacing():
    """A 0.5 m grid whose coordinates are off by up to 1 mm: written at exactly 0.5 m on the grid's own cells."""
    rng = np.random.default_rng(8)
    points = [(x + rng.uniform(-0.001, 0.001), y + rng.uniform(-0.001, 0.001), z)
              for x, y, z in _grid_points(6430400, 5800000, 0.5, 40, 40, 8)]
    band, transform = sf._xyz_grid(_lines(points, decimals=4), 0.5, CRS, "sheet")
    assert band.shape == (40, 40) and np.isfinite(band).all()
    assert abs(transform.a - 0.5) < 1e-12 and abs(transform.e + 0.5) < 1e-12


def test_the_spacing_is_never_much_finer_than_listed():
    """Moves under res / MAX_FINER are no step: every point repeated 5 mm off gives no 5 mm grid (40 000 times the
    pixels) but 1 m, and a half-resolution grid keeps its step."""
    near = np.array([(6430400.5 + i // 2 + 0.005 * (i % 2), 5800000.5, 50.0) for i in range(400)])
    assert sf._step(near, 1.0) == 1.0
    half = np.array(_grid_points(6430400, 5800000, 0.5, 10, 10, 9))
    assert sf._step(half, 1.0) == 0.5


def test_no_points_is_an_error():
    with pytest.raises(RuntimeError, match="no x y z lines"):
        sf._xyz_grid(sf.BOM + b"\r\n", 1.0, CRS)


def test_an_empty_file_in_its_zip_is_no_data(monkeypatch, tmp_path, capsys):
    """The publisher's empty XYZ in a valid ZIP: no data, no file (np.loadtxt's IndexError before); an empty
    answer of the server itself stays an error."""
    fetched, path = _fetch(monkeypatch, tmp_path, _zip("s.xyz", b""))
    assert fetched.received == 0 and not os.path.exists(path)
    assert "the file in its ZIP is empty; no data" in capsys.readouterr().out
    with pytest.raises(RuntimeError, match="6.175.12.02.1: the answer is empty"):
        _fetch(monkeypatch, tmp_path, b"", url="https://example/s.xyz")


def test_errors_name_the_sheet(monkeypatch, tmp_path):
    with pytest.raises(RuntimeError, match=r"^NMT sheet 6\.175\.12\.02\.1: .*lines are not x y z"):
        _fetch(monkeypatch, tmp_path, _zip("s.xyz", b"<html>\r\n<body>\r\n</body>\r\n"))


def _ascii_grid(z, left, top) -> bytes:
    rows = "\r\n".join(" ".join(f"{v:.2f}" for v in row) for row in z)
    return (f"ncols {z.shape[1]}\r\nnrows {z.shape[0]}\r\nxllcenter {left + 0.5}\r\nyllcenter "
            f"{top - z.shape[0] + 0.5}\r\ncellsize 1\r\nnodata_value -9999\r\n{rows}\r\n").encode()


def test_ascii_grids_behind_a_bom_and_xyz_named_asc(monkeypatch, tmp_path, capsys):
    """An ASCII grid behind a BOM, which GDAL does not recognise as one, read as without it; a ".asc" GDAL does not
    recognise at all read as x y z lines."""
    z = np.round(np.random.default_rng(5).uniform(100, 200, (3, 4)), 2).astype(np.float32)
    _, path = _fetch(monkeypatch, tmp_path, sf.BOM + _ascii_grid(z, 6430400, 5800000),
                     url="https://example/s.asc")
    band, transform = _read(path)
    assert np.allclose(band, z, atol=0.006) and transform == from_origin(6430400, 5800000, 1.0, 1.0)
    points = _grid_points(6430400, 5800000, 1.0, 3, 4, 6)

    class Refused:
        def __init__(self, data, ext):
            self.name = "/vsimem/x.asc"

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def open(self):
            raise RasterioIOError(f"'{self.name}' not recognized as being in a supported file format.")
    monkeypatch.setattr(sf, "MemoryFile", Refused)
    band, transform = sf._ascii_grid(_lines(points), 1.0, CRS, "sheet")
    assert band.shape == (3, 4) and transform == from_origin(6430400, 5800000, 1.0, 1.0)
    assert "not a raster GDAL recognises, read as x y z lines" in capsys.readouterr().out
