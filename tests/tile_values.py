"""Comparing the values of a cached tile with what it was written from. The cache writes its float tiles as LERC
within 5 mm (sources.layer.MAX_Z_ERROR; float32 rounding adds up to 0.0001 m of a height of some hundred metres), so
a test that compares a tile with the service's or the file's own values uses same_tile; two tiles that were each
written from the same values, but on different pixels, may differ by twice that."""

import numpy as np

TILE_EPS = 0.0051  # m: the writer's bound and the float32 rounding of a height


def same_tile(tile, values, eps: float = TILE_EPS) -> bool:
    """Whether a cached tile holds values (a service's answer, a file's pixels) within eps, with data and without
    data on the same pixels."""
    tile, values = np.asarray(tile, np.float64), np.asarray(values, np.float64)
    return tile.shape == values.shape and bool(np.array_equal(np.isnan(tile), np.isnan(values))
                                               and np.all(np.abs(tile - values)[~np.isnan(tile)] <= eps))
