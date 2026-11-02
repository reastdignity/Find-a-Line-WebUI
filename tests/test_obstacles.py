"""The obstacle surface (obstacles.py): rock faces are no obstacles, trees and buildings stay.

The grids are made as the services make theirs from a fine surface (0.1 m): the terrain
model is the ground at each pixel's centre, the surface model the highest point of the pixel.
The rows are all alike, so a line along a row sees one profile.
"""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import helpers as sh  # noqa: E402
import obstacles  # noqa: E402

FINE = 10  # fine samples per pixel of 1 m
ROWS = 7


def rasterize(ground, surface, width):
    """Terrain and surface model of `width` pixels of 1 m from functions of x (metres): the
    ground at the pixel's centre, the highest fine sample of the pixel's surface."""
    x = (np.arange(width * FINE) + 0.5) / FINE
    centres = np.arange(width) + 0.5
    dtm = np.tile(ground(centres).astype(np.float32), (ROWS, 1))
    dsm = np.tile(surface(x).reshape(width, FINE).max(axis=1).astype(np.float32), (ROWS, 1))
    return dtm, dsm


def canyon(x):
    """Plateaus at 100 m, a floor at 50 m between walls that stand inside pixels 20 and 69."""
    return np.where((x >= 20.35) & (x < 69.65), 50.0, 100.0)


def test_wall_inside_a_pixel_is_no_obstacle():
    dtm, dsm = rasterize(canyon, canyon, 90)
    assert dsm[0, 20] - dtm[0, 20] == 50  # the rim stands in the pixel of the floor
    assert dsm[0, 69] - dtm[0, 69] == 50
    surface = obstacles.obstacle_surface(dtm, dsm, 1.0)
    np.testing.assert_array_equal(surface, dtm)  # bare rock: the terrain everywhere


def test_line_from_the_rim():
    """The first pixel of a line from a wall: over the raw surface model the line is marked,
    over the obstacle surface it is as clear as over the terrain, and a tree in the middle
    still marks it."""
    dtm, dsm = rasterize(canyon, canyon, 90)
    a1, a2 = np.array([3, 19]), np.array([3, 70])
    raw = sh.evaluate_line(a1, a2, dtm, 1.0, dsm)
    clearance, clearance_nmpt = raw[3], raw[4]
    assert clearance > 40 and clearance_nmpt < 0  # 100 - 6.15 - 100 at the rim
    rule = sh.evaluate_line(a1, a2, dtm, 1.0, obstacles.obstacle_surface(dtm, dsm, 1.0))
    assert rule[4] == rule[3] == clearance

    tree = lambda x: canyon(x) + np.where((x >= 43) & (x < 46), 45.0, 0.0)  # noqa: E731
    dtm, dsm = rasterize(canyon, tree, 90)
    rule = sh.evaluate_line(a1, a2, dtm, 1.0, obstacles.obstacle_surface(dtm, dsm, 1.0))
    assert rule[3] == clearance and rule[4] < 0  # 95 m over a limit of 90.25 m


def test_trees_and_buildings_stay():
    slope = np.tan(np.radians(40))

    def ground(x):
        return np.where(x < 20.35, 100.0,  # a plateau with its rim inside pixel 20
                        np.where(x < 50, 50.0,  # flat ground
                                 50.0 + slope * (x - 50)))  # a slope of 40 degrees

    def things(x):
        return np.select([(x >= 15) & (x < 18),  # a tree of 15 m on the plateau near the rim
                          (x >= 30) & (x < 34),  # a tree of 15 m on flat ground
                          (x >= 38) & (x < 44),  # a building of 8 m
                          (x >= 46) & (x < 48),  # a shrub of 0.8 m: below MIN_HEIGHT
                          (x >= 60) & (x < 64)],  # a tree of 12 m on the slope
                         [15.0, 15.0, 8.0, 0.8, 12.0], 0.0)

    dtm, dsm = rasterize(ground, lambda x: ground(x) + things(x), 80)
    surface = obstacles.obstacle_surface(dtm, dsm, 1.0)[0]
    kept = surface > dtm[0]
    assert kept[[15, 16, 17, 30, 31, 32, 33, 38, 43, 60, 61, 62, 63]].all()
    np.testing.assert_array_equal(surface[kept], dsm[0][kept])  # an obstacle keeps its full height
    assert not kept[[19, 20, 21, 46, 47]].any()  # the rim and the shrub
    assert kept.sum() == 13 + 4  # the building's middle pixels too (39-42)


def test_overhang_needs_the_wall_band():
    """A lip reaching 0.85 m beyond the foot of the wall: the ground filter keeps the floor
    under it, the surface model the lip. The envelope of 3 x 3 pixels does not reach the
    plateau from there; the band of 3 pixels around terrain steeper than 70 degrees does."""
    ground = lambda x: np.where(x < 20.35, 100.0, 50.0)  # noqa: E731
    lip = lambda x: np.where(x < 21.2, 100.0, 50.0)  # noqa: E731
    dtm, dsm = rasterize(ground, lip, 40)
    assert dsm[0, 21] == 100 and dtm[0, 21] == 50
    assert obstacles.obstacle_surface(dtm, dsm, 1.0)[0, 21] == 100
    assert obstacles.obstacle_surface(dtm, dsm, 1.0, wall=(70, 3))[0, 21] == 50
    assert obstacles.obstacle_surface(dtm, dsm, 1.0, radius=2)[0, 21] == 50


def test_cut_block_top_stays_an_obstacle():
    """The limit of these rules: a block whose top the ground filter cut 3 m lower is rock,
    but the surface model stands above every terrain around it (tools/obstacle_study.py
    counts how often this happens)."""
    ground = lambda x: np.where((x >= 30.35) & (x < 36.35), 60.0, 50.0)  # noqa: E731
    block = lambda x: np.where((x >= 30.35) & (x < 36.35), 63.0, 50.0)  # noqa: E731
    dtm, dsm = rasterize(ground, block, 60)
    for wall in (None, (70, 3)):
        assert (obstacles.obstacle_surface(dtm, dsm, 1.0, wall=wall)[0, 31:36] == 63).all()


def test_no_data():
    dtm, dsm = rasterize(canyon, lambda x: canyon(x) + np.where((x >= 43) & (x < 46), 45.0, 0.0), 90)
    dsm[:, 50:55] = np.nan
    dtm[:, 42] = np.nan  # a pixel without terrain neither hides nor marks the trees next to it
    surface = obstacles.obstacle_surface(dtm, dsm, 1.0)
    assert np.isnan(surface[:, 50:55]).all()  # not measured there, as before
    assert (surface[:, 43:46] == 95).all() and np.isnan(surface[:, 42]).all()


def test_blocks_give_one_pass():
    """Blocks of rows with their halo give what one pass over the whole grid gives."""
    rng = np.random.default_rng(7)
    dtm = np.cumsum(np.cumsum(rng.normal(0, 1, (61, 47)), axis=0), axis=1).astype(np.float32)
    dsm = dtm + np.where(rng.random(dtm.shape) < 0.2, rng.uniform(0, 20, dtm.shape), 0).astype(np.float32)
    dsm[rng.random(dtm.shape) < 0.05] = np.nan
    for radius, wall in ((1, None), (2, (60, 3)), (1, (45, 5))):
        whole = obstacles.obstacle_surface(dtm, dsm, 2.0, radius=radius, wall=wall, block_rows=1000)
        for rows in (1, 3, 8):
            parts = obstacles.obstacle_surface(dtm, dsm, 2.0, radius=radius, wall=wall, block_rows=rows)
            np.testing.assert_array_equal(parts, whole)
