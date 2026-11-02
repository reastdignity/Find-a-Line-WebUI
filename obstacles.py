"""
Which pixels of the surface model (DSM) are obstacles under a line: trees and buildings,
not the terrain's own rock.

On a steep face a pixel of the surface model holds the highest point of its footprint (the
face's upper part, the rim), while the terrain model holds the ground interpolated at the
pixel's centre: the surface stands above the terrain there although nothing grows on it
(half the pixel times the tangent of the slope on a plane, up to the wall's height where a
vertical wall crosses the pixel). A line needs a drop of about 6 m to its first pixel (the
leash fall), so that pixel is on such a face, and nearly every line from a wall came out
"over trees". Ground filters also cut rims, overhangs and the tops of blocks out of the
terrain model, over several pixels (docs/roadmap.md, priority 1).

The obstacle surface keeps the surface model only where it stands more than `min_height`
above the terrain's envelope, the highest terrain within `radius` pixels (a square window):
a pixel of the surface cannot hold more than the highest terrain of its footprint, which
reaches into the neighbouring pixels. Elsewhere it is the terrain itself, so the obstacle
test passes wherever the terrain test does; NaN where the surface model has no data (not
measured there). With `wall` = (degrees, pixels), pixels within that many pixels of terrain
at least that steep take the envelope of that radius instead (cut rims and overhangs).
"""

from typing import Optional, Tuple

import numpy as np
from scipy import ndimage

RADIUS = 1          # pixels of the terrain envelope (3 x 3)
MIN_HEIGHT = 1.0    # metres above the envelope from which the surface counts (the user's choice, 2026-11-02)
BLOCK_ROWS = 1024   # rows computed at once (keeps memory use bounded)


def envelope(elevation: np.ndarray, radius: int) -> np.ndarray:
    """The highest terrain within `radius` pixels (a square of 2 * radius + 1) of every pixel,
    float32; pixels without data (NaN) do not count, -inf where none of them has data."""
    z = np.asarray(elevation, dtype=np.float32)
    z = np.where(np.isnan(z), np.float32(-np.inf), z)
    if radius <= 0:
        return z
    return ndimage.maximum_filter(z, size=2 * radius + 1, mode="constant", cval=-np.inf)


def slope_degrees(elevation: np.ndarray, res: float) -> np.ndarray:
    """The terrain's slope in degrees as helpers.find_significant_slopes computes it (np.gradient)."""
    gy, gx = np.gradient(np.asarray(elevation, dtype=np.float32), res)
    return np.degrees(np.arctan(np.hypot(gx, gy)))


def is_obstacle(elevation: np.ndarray, surface: np.ndarray, res: float, radius: int = RADIUS,
                min_height: float = MIN_HEIGHT, wall: Optional[Tuple[float, int]] = None) -> np.ndarray:
    """Pixels where the surface stands more than min_height above the terrain's envelope (with
    wall, the wider envelope near steep terrain); False where the surface has no data, True
    where it has but no terrain around has."""
    z = np.asarray(elevation, dtype=np.float32)
    top = envelope(z, radius)
    if wall is not None:
        degrees, pixels = wall
        with np.errstate(invalid="ignore"):
            near = ndimage.binary_dilation(slope_degrees(z, res) >= degrees,  # NaN compares False
                                           structure=np.ones((2 * pixels + 1,) * 2, dtype=bool))
        top = np.where(near, np.maximum(top, envelope(z, pixels)), top)
    with np.errstate(invalid="ignore"):
        return np.asarray(surface, dtype=np.float32) > top + np.float32(min_height)  # NaN: False


def _block(z: np.ndarray, s: np.ndarray, res: float, radius: int, min_height: float,
           wall: Optional[Tuple[float, int]]) -> np.ndarray:
    """The obstacle surface of one block of rows (z, s: terrain and surface, with their halo)."""
    obstacle = is_obstacle(z, s, res, radius, min_height, wall)
    return np.where(np.isnan(s), np.float32(np.nan), np.where(obstacle, s, z)).astype(np.float32, copy=False)


def obstacle_surface(elevation: np.ndarray, surface: np.ndarray, res: float, out: Optional[np.ndarray] = None,
                     radius: int = RADIUS, min_height: float = MIN_HEIGHT,
                     wall: Optional[Tuple[float, int]] = None, block_rows: int = BLOCK_ROWS) -> np.ndarray:
    """The surface the obstacle test compares with a line's limit: the surface model where it
    stands more than min_height above the terrain's envelope, the terrain elsewhere, NaN where
    the surface model has no data. Computed in blocks of rows into out (float32, the grid's
    shape; a new array when not given), so memory-mapped grids are never read whole."""
    height, width = elevation.shape
    if out is None:
        out = np.empty((height, width), dtype=np.float32)
    halo = max(radius, wall[1] if wall is not None else 0) + 1  # + 1: the slope of the band's edge
    for r0 in range(0, height, block_rows):
        r1 = min(height, r0 + block_rows)
        h0, h1 = max(0, r0 - halo), min(height, r1 + halo)
        z = np.asarray(elevation[h0:h1], dtype=np.float32)
        s = np.asarray(surface[h0:h1], dtype=np.float32)
        out[r0:r1] = _block(z, s, res, radius, min_height, wall)[r0 - h0:r1 - h0]
    return out
