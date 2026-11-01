"""The coverage out of a multipart/related WCS answer (wcsreader._extract_multipart): part headers
ending with CRLF or bare LF lines (Saxony-Anhalt's ArcGIS server), the body kept byte for byte."""

import os
import sys

import numpy as np
import pytest
from rasterio.io import MemoryFile
from rasterio.transform import from_origin

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sources.readers.wcsreader import _extract_multipart  # noqa: E402

CONTENT_TYPE = 'multipart/related; boundary="wcs"; type="application/gml+xml"'


def _tiff(last: float) -> bytes:
    """An uncompressed float32 GeoTIFF whose bytes end with the last pixel's (little endian)."""
    band = np.full((2, 2), 500.0, dtype=np.float32)
    band[-1, -1] = last
    with MemoryFile() as memfile:
        with memfile.open(driver="GTiff", width=2, height=2, count=1, dtype="float32", crs="EPSG:25832",
                          transform=from_origin(0, 2, 1, 1)) as dst:
            dst.write(band, 1)
        data = memfile.read()
    return data


def _answer(tiff: bytes, eol: bytes) -> bytes:
    lines = [b"--wcs", b"Content-Type: application/gml+xml", b"", b"<gml:coverage/>",
             b"--wcs", b"Content-Type: image/tiff", b"Content-ID: coverage/out.tif", b""]
    return eol.join(lines) + eol + tiff + eol + b"--wcs--" + eol


# float32 values whose last byte (little endian) is 0x0D or 0x0A
ENDING_CR = np.frombuffer(b"\x00\x00\x7a\x0d", dtype="<f4")[0]
ENDING_LF = np.frombuffer(b"\x00\x00\x7a\x0a", dtype="<f4")[0]


@pytest.mark.parametrize("eol", [b"\r\n", b"\n"], ids=["crlf", "lf"])
@pytest.mark.parametrize("last", [500.0, ENDING_CR, ENDING_LF], ids=["plain", "ends-0d", "ends-0a"])
def test_coverage_part_intact(eol, last):
    tiff = _tiff(last)
    if last != 500.0:
        assert tiff[-1:] in (b"\r", b"\n")  # the case this test is about
    extracted = _extract_multipart(_answer(tiff, eol), CONTENT_TYPE)
    assert extracted == tiff
    with MemoryFile(extracted) as memfile, memfile.open() as src:
        assert src.read(1)[-1, -1] == np.float32(last)


def test_no_coverage_part():
    answer = b"--wcs\r\nContent-Type: application/gml+xml\r\n\r\n<gml:coverage/>\r\n--wcs--\r\n"
    with pytest.raises(RuntimeError, match="did not contain coverage data"):
        _extract_multipart(answer, CONTENT_TYPE)
