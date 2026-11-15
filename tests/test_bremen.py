"""Bremen and Bremerhaven: Landesamt GeoInformation Bremen's DGM1 and DOM1 as XYZ members of remote ZIP archives
(sources/catalogue/germany.py), read by sources/readers/zipmember.py: GDAL's XYZ driver, and xyz_rows for a member
in columns with points missing, against archives made here with zipfile (served by tests/http_server.py)."""

import zipfile

import numpy as np
import pytest
import rasterio as rio
from rasterio.transform import Affine

from sources.readers.zipmember import TransformFix, ZipMember, xyz_rows
from test_saarland import _archive, _serve, _tile

ZONE = TransformFix(offset=(-32_000_000.0, 0.0), snap=0.5)


def _xyz(points, header: bool = True, newline: str = "\r\n") -> bytes:
    """An XYZ member: "x y z" lines of the points in their order, after a header line or not."""
    return (newline.join((["x y z"] if header else []) + [f"{x} {y} {z}" for x, y, z in points]) + newline).encode()


def _fetch(http_server, tmp_path, reader: ZipMember, name: str, body: bytes):
    _serve(http_server, "/m.zip", body)
    path = str(tmp_path / "t.tif")
    reader.fetch(_tile(http_server, "/m.zip", body, name), path)
    with rio.open(path) as written:
        return written.transform, written.read(1, masked=True).astype(np.float32).filled(np.nan)


# Bremerhaven's DOM1: whole metres with the zone, in columns from the south (dom1_32474_5936_1_hb.xyz's layout)
COLUMNS = [(32474000 + i, 5936000 + j, round(2 + 0.1 * i + 0.01 * j, 3)) for i in range(4) for j in range(3)]
EXPECTED = np.array([[2.02, 2.12, 2.22, 2.32], [2.01, 2.11, 2.21, 2.31], [2.0, 2.1, 2.2, 2.3]], dtype=np.float32)


def test_xyz_rows_keeps_the_lines():
    """The lines in rows, north to south and west to east, each as it was written; the header kept; a GeoTIFF or
    other text is not XYZ (None)."""
    member = _xyz([(1.5, 10.5, "0.100"), (1.5, 11.5, "0.200"), (2.5, 10.5, "0.300"), (2.5, 11.5, "0.400")])
    assert xyz_rows(member) == b"x y z\n1.5 11.5 0.200\n2.5 11.5 0.400\n1.5 10.5 0.100\n2.5 10.5 0.300\n"
    assert xyz_rows(_xyz([(1, 2, 3), (1, 1, 4)], header=False, newline="\n")) == b"1 2 3\n1 1 4\n"
    assert xyz_rows(b"II*\x00\x08\x00\x00\x00\xff\xfe") is None
    assert xyz_rows(b"x y z\r\n1 2\r\n") is None
    assert xyz_rows(b"x y z\r\n") is None


@pytest.mark.parametrize("gone, nan", [
    ([(32474003, 5936001), (32474003, 5936002)], [(0, 3), (1, 3)]),   # the last column only its lowest point
    ([(32474001, 5936001)], [(1, 1)]),                                  # a point inside a column
    ([(32474000, 5936002), (32474001, 5936002)], [(0, 0), (0, 1)])])    # the first columns' top
def test_a_member_in_columns_with_points_missing(http_server, tmp_path, gone, nan):
    """GDAL refuses points in columns with some missing ("does not support datasets organized by columns with
    missing values", or "Ungridded dataset"): the member is read again in rows, the missing points no data, the
    others where the whole member puts them."""
    name = "Gitternetz_DOM1_2015_BHV/dom1_32474_5936_1_hb.xyz"
    whole = _archive([(name, _xyz(COLUMNS), zipfile.ZIP_DEFLATED, False)])
    transform, z = _fetch(http_server, tmp_path, ZipMember("DOM1 (test)", crs="EPSG:25832", fix=ZONE), name, whole)
    assert transform == Affine(1.0, 0.0, 473999.5, 0.0, -1.0, 5936002.5) and np.allclose(z, EXPECTED)
    part = _archive([(name, _xyz([p for p in COLUMNS if p[:2] not in gone]), zipfile.ZIP_DEFLATED, False)])
    transform_part, z_part = _fetch(http_server, tmp_path, ZipMember("DOM1 (test)", crs="EPSG:25832", fix=ZONE),
                                    name, part)
    expected = EXPECTED.copy()
    for row, col in nan:
        expected[row, col] = np.nan
    assert transform_part == transform and np.allclose(z_part, expected, equal_nan=True)


def test_not_a_raster_is_still_an_error(http_server, tmp_path):
    """Text that is no XYZ grid at all fails as before (no tile), also after the second reading."""
    name = "dom1_32474_5936_1_hb.xyz"
    body = _archive([(name, _xyz([(0, 0, 1), (0.3, 7, 2), (5, 1.1, 3), (9, 9, 4)]), zipfile.ZIP_DEFLATED, False)])
    with pytest.raises(RuntimeError, match="not a raster"):
        _fetch(http_server, tmp_path, ZipMember("DOM1 (test)", crs="EPSG:25832"), name, body)
    assert not (tmp_path / "t.tif").exists()
