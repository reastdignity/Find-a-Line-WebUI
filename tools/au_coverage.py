"""The cells of Geoscience Australia's national 5 m lidar DEM that hold data (the source `australia`): a static mask
next to the catalogue (sources/catalogue/australia_dem5m_cells.npz), read by GeoWcsTiles.has_data_near, so
`--source auto` takes `europe` instead of `australia` where the DEM has no survey near the centre (about 97 % of
Australia: the Blue Mountains, the Grampians, Arapiles).

The WCS is asked for the whole grid sampled every STEP pixels (88 x 80 of its 5 m pixels, about 485 x 412 m), in
pieces of at most MAX_PX pixels a side (the service's maxImageWidth/Height 4096: 2 x 2 requests, about 35 MB of
compressed GeoTIFF), each box on the grid's own pixel edges, so the service samples the pixel at each sample's
centre (nearest). A cell of the mask is CELL x CELL samples (about 1.9 x 1.65 km) and holds data when any of its
samples is not 0 (the DEM's no data and its sea). A survey strip narrower than a sample can fall between samples:
checked at the coast's narrow surveys (North Head, Point Perpendicular, Nowra, the Royal National Park's coast)
when the mask was made (tests/test_australia_uruguay.py keeps those places "data" and Arapiles, Mount Victoria and
the Grampians "no data").

GA adds surveys to the service now and then ("New data will be added to the service as it becomes available"):
run this again then (or yearly), check the places of the test, and commit the new mask.

    uv run tools/au_coverage.py [--out sources/catalogue/australia_dem5m_cells.npz]
"""

import argparse
import io
import math
import os
import sys
from typing import Callable, Tuple

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

STEP = (88, 80)   # 5 m pixels of the grid per sample (columns, rows)
CELL = 4          # samples per cell of the mask, a side
MAX_PX = 4096     # the WCS's largest image a side


def pieces(size: Tuple[int, int], step: Tuple[int, int], max_px: int = MAX_PX):
    """The requests over a grid of size (columns, rows) sampled every step pixels: (first sample column, first
    sample row, sample columns, sample rows) of at most max_px a side, the last ones cut at the grid's samples."""
    cols, rows = math.ceil(size[0] / step[0]), math.ceil(size[1] / step[1])
    return [(c, r, min(max_px, cols - c), min(max_px, rows - r))
            for r in range(0, rows, max_px) for c in range(0, cols, max_px)]


def cells(samples: np.ndarray, cell: int = CELL) -> np.ndarray:
    """A cell (cell x cell samples, the last ones cut) holds data when any of its samples does (not 0, finite)."""
    valid = np.isfinite(samples) & (samples != 0)
    rows, cols = math.ceil(valid.shape[0] / cell), math.ceil(valid.shape[1] / cell)
    padded = np.zeros((rows * cell, cols * cell), dtype=bool)
    padded[:valid.shape[0], :valid.shape[1]] = valid
    return padded.reshape(rows, cell, cols, cell).any(axis=(1, 3))


def save(path: str, mask: np.ndarray, step: Tuple[int, int] = STEP, cell: int = CELL):
    """The mask as bits (numpy's packbits, compressed), with its shape and its cell in 5 m pixels."""
    np.savez_compressed(path, bits=np.packbits(mask, axis=None), shape=np.array(mask.shape),
                        cell_px=np.array([step[0] * cell, step[1] * cell]))


def sample(get: Callable[[list], bytes], corner, pixel, size, step=STEP, max_px: int = MAX_PX) -> np.ndarray:
    """The grid sampled every step pixels, asked in pieces (get: the GetCoverage parameters -> the GeoTIFF)."""
    import rasterio
    (dx, dy), (west, north) = pixel, corner
    cols, rows = math.ceil(size[0] / step[0]), math.ceil(size[1] / step[1])
    out = np.zeros((rows, cols), dtype=np.float32)
    for c, r, w, h in pieces(size, step, max_px):
        left, top = west + c * step[0] * dx, north - r * step[1] * dy
        right, bottom = west + (c + w) * step[0] * dx, north - (r + h) * step[1] * dy
        params = [("SERVICE", "WCS"), ("VERSION", "1.0.0"), ("REQUEST", "GetCoverage"), ("COVERAGE", "1"),
                  ("CRS", "EPSG:4283"), ("BBOX", ",".join(f"{v:.17g}" for v in (left, bottom, right, top))),
                  ("WIDTH", str(w)), ("HEIGHT", str(h)), ("FORMAT", "GeoTIFF")]
        with rasterio.open(io.BytesIO(get(params))) as src:
            band = src.read(1)
        if band.shape != (h, w):
            raise RuntimeError(f"piece {c},{r}: {band.shape} answered, {(h, w)} asked")
        out[r:r + h, c:c + w] = band
        print(f"piece {c},{r}: {w} x {h} samples, {int((band != 0).sum())} with data", flush=True)
    return out


def main():
    from sources import net
    from sources.catalogue import australia
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", default=australia.AU_CELLS)
    args = parser.parse_args()

    def get(params) -> bytes:
        response = net._get(australia.AU_WCS, params)
        if response is None:
            raise RuntimeError("HTTP 404 for a piece of the grid")
        return response.content

    samples = sample(get, australia.AU_CORNER, australia.AU_PIXEL, australia.AU_SIZE)
    mask = cells(samples)
    save(args.out, mask)
    print(f"{args.out}: {mask.shape[1]} x {mask.shape[0]} cells, {int(mask.sum())} with data "
          f"({mask.mean():.2%}), {os.path.getsize(args.out)} bytes")


if __name__ == "__main__":
    from progress import utf8_output
    utf8_output()  # redirected output in UTF-8, not the Windows code page
    main()
