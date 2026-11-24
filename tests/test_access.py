"""The access measure (access.py): can a person walk to an anchor? Made-up terrain only: a meadow and a wall, a
ledge in the face, a pillar, ground of 35, 45 and 60 degrees, whole-metre heights, the end of the data, water and
lakes held as data, the alpine variant; threads; a window with the measure's margin against the whole grid and the
study's noted exception; the speed, logged (offline, seconds)."""

import os
import time

import numpy as np
import pytest
from scipy import ndimage

import access

CAN, UNSURE, CANNOT = access.CAN, access.UNSURE, access.CANNOT


def tilted(rows, cols, res=1.0, grade=0.1, base=100.0, seed=0):
    """Gentle ground (about 6 degrees at a grade of 0.1) along the columns, a little float noise."""
    rng = np.random.default_rng(seed)
    r, c = np.mgrid[0:rows, 0:cols].astype(np.float64)
    return base + grade * c * res + 0.02 * r * res + rng.random((rows, cols)) * 0.05


def wall_and_meadows(ledge=False, ramp=False, rows=220, cols=320):
    """At 1 m: an upper meadow (columns 0-139, about 6 degrees), a face of 4 m per pixel (76 degrees, columns
    140-162) down to a lower meadow 96 m below (columns 163-): each meadow over 2 ha. With `ledge`, a shelf in the
    face (rows 90-129, columns 148-155) 32 m below the top; with `ramp`, also the meadow's level carried over the face
    (rows 0-43, columns 140-155) and from it a ramp of about 34 degrees down to that shelf (rows 44-89)."""
    z = tilted(rows, cols)
    top = z[:, 139].copy()
    for k, c in enumerate(range(140, 164)):
        z[:, c] -= 4.0 * (k + 1)
    z[:, 164:] -= 96.0
    if ledge or ramp:
        shelf = top[110] - 32.0
        z[90:130, 148:156] = shelf + 0.05 * np.arange(8)[None, :] + 0.03 * np.arange(40)[:, None]
    if ramp:
        # the meadow's level carried over the face down to row 43, then a ramp of about 34 degrees (walkable, not
        # open ground) down to the shelf at row 90: only a walk joins them
        for r in range(44):
            z[r, 140:156] = z[r, 139] + 0.1 * np.arange(1, 17)
        start = z[43, 140:156].copy()
        rise = (start - shelf) / 47.0
        for r in range(44, 90):
            z[r, 140:156] = start - rise * (r - 43)
    return z.astype(np.float32)


def test_grid_values_and_lookup():
    z = wall_and_meadows()
    grid = access.access_grid(z, None, 1.0)
    assert grid.dtype == np.uint8 and grid.shape == z.shape
    assert set(np.unique(grid)) == {CAN, CANNOT}
    assert np.array_equal(access.at(grid, [[100, 50], [100, 150]]), grid[[100, 100], [50, 150]])


def test_meadow_and_wall_can_walk():
    """The lip of a wall and its foot: standing ground on the meadow beside each: can walk. The middle of the face
    and a pixel 4 m below the lip have none: cannot walk."""
    z = wall_and_meadows()
    grid = access.access_grid(z, None, 1.0)
    assert grid[110, 139] == CAN  # the lip
    assert grid[110, 163] == CAN and grid[110, 164] == CAN  # the foot
    assert grid[110, 140] == CANNOT  # the meadow within 3 m is more than 3 m above it
    assert grid[110, 152] == CANNOT  # mid-face


def test_mid_face_ledge_cannot_walk_unless_a_walk_leads_there():
    z = wall_and_meadows(ledge=True)
    grid = access.access_grid(z, None, 1.0)
    assert grid[110, 151] == CANNOT  # a shelf of 320 m2: walkable, not open ground, no walk to it
    z = wall_and_meadows(ramp=True)
    grid = access.access_grid(z, None, 1.0)
    assert grid[110, 151] == CAN  # the same shelf with a ramp up to the meadow
    slope = access.slope_deg(z, 1.0)[50:85, 142:154]
    assert (slope > access.OPEN_DEG).all() and (slope <= access.WALK_DEG).all()  # walkable, not open: a walk decides


def pillar(height):
    """A pillar of 6 x 6 m standing `height` m above a meadow (1 m pixels)."""
    z = tilted(200, 200)
    z[97:103, 97:103] += height
    return z.astype(np.float32)


def test_pillar_top_is_not_open_ground_nor_its_foot_standing_ground():
    assert access.access_grid(pillar(12.0), None, 1.0)[100, 100] == CANNOT  # the meadow 3 m away is 12 m below
    assert access.access_grid(pillar(1.0), None, 1.0)[100, 100] == CAN  # a block 1 m high: the meadow is in reach


def slope_to(deg, rows=200, cols=260):
    """A meadow (columns 0-129, 1 m pixels) then ground rising at `deg` degrees for 60 m, then the meadow's grade
    again; returns the terrain and the column in the slope's middle."""
    z = tilted(rows, cols)
    grade = np.tan(np.radians(deg))
    run = int(round(60.0 / grade))
    z = z + (np.clip(np.arange(cols) - 129, 0, run) * grade)[None, :]
    return z.astype(np.float32), 129 + run // 2


@pytest.mark.parametrize("deg, answer", [(35.0, CAN), (45.0, UNSURE), (60.0, CANNOT)])
def test_ground_steepness(deg, answer):
    """The middle of a slope up from a meadow: walkable at 35 degrees, cannot tell at 45 (only the loose walk up to
    50 degrees reaches it), cannot walk at 60."""
    z, c = slope_to(deg)
    assert access.access_grid(z, None, 1.0, alpine=False)[100, c] == answer


def mesa(side, whole=False):
    """A mesa of `side` x `side` m (1 m pixels, about 6 degrees along the columns) standing 20 m above the ground
    around it, its corner at (50, 50): its rim pixels are steep, so it is open ground from a side of 102 m."""
    rng = np.random.default_rng(0)
    r, c = np.mgrid[0:200, 0:200].astype(np.float64)
    z = 100 + 0.1 * c + rng.random((200, 200)) * 0.05
    z[~((r >= 50) & (r < 50 + side) & (c >= 50) & (c < 50 + side))] -= 20.0
    z = z.astype(np.float32)
    return np.round(z).astype(np.float32) if whole else z


def test_whole_metre_heights_cannot_tell_where_smoothing_changes_the_answer(monkeypatch):
    """A lip of a mesa of 104 m: can walk on float heights (its top is open ground, over 1 ha); on whole metres the
    lightly smoothed heights widen its steep rim, so the top falls under 1 ha and the answer changes: cannot tell.
    Without the smoothing check the same whole-metre heights read can walk; a mesa of 100 m is no open ground."""
    lip = (102, 50)
    assert access.access_grid(mesa(104), None, 1.0, alpine=False)[lip] == CAN
    assert access.access_grid(mesa(100), None, 1.0, alpine=False)[lip] == CANNOT
    whole = mesa(104, whole=True)
    assert access.whole_metres(whole.ravel())
    assert access.access_grid(whole, None, 1.0, alpine=False)[lip] == UNSURE
    with monkeypatch.context() as m:
        m.setattr(access, "whole_metres", lambda heights: False)
        assert access.access_grid(whole, np.zeros(whole.shape, bool), 1.0, alpine=False)[lip] == CAN
    z = np.round(wall_and_meadows()).astype(np.float32)
    grid = access.access_grid(z, None, 1.0)
    assert grid[110, 139] == CAN and grid[110, 152] == CANNOT


def plateau(rows, cols, r0, c0, res=2.0):
    """A plateau of 20 x 20 pixels (1600 m2 at 2 m: not open ground) 30 m above a meadow, its corner at (r0, c0)."""
    z = tilted(rows, cols, res=res, grade=0.1)
    z[r0:r0 + 20, c0:c0 + 20] += 30.0
    return z.astype(np.float32)


def test_end_of_data_cannot_tell():
    """A plateau that no walk reaches: cannot walk where its ground is closed; cannot tell where it touches the
    grid's edge or a gap filled from a coarser model (open ground may lie beyond)."""
    middle = plateau(600, 600, 290, 290)  # 1.2 km: every edge over MARGIN_M away
    assert access.access_grid(middle, None, 2.0)[300, 300] == CANNOT
    corner = plateau(150, 150, 0, 0)
    assert access.access_grid(corner, None, 2.0)[10, 10] == UNSURE
    middle[290:310, 310:330] = middle[290:310, 309:310]  # the plateau 20 pixels wider ...
    assert access.access_grid(middle, None, 2.0)[300, 300] == CANNOT
    filled = np.zeros(middle.shape, bool)
    filled[290:310, 310:330] = True  # ... where those pixels are a filled gap
    assert access.access_grid(middle, None, 2.0, filled=filled)[300, 300] == UNSURE


def test_no_data():
    """A pixel without data holds what an anchor there would get (cannot walk here: open ground all around). A NaN
    hole beside the plateau is no end of the data, unlike a filled gap: the plateau's pixels beside it have no slope
    (the study's rule)."""
    middle = plateau(600, 600, 290, 290)
    middle[290:310, 310:330] = np.nan
    grid = access.access_grid(middle, None, 2.0)
    assert grid[300, 320] == CANNOT
    assert grid[300, 300] == CANNOT


def ridge(width):
    """A meadow (columns 0-119, 1 m pixels), a chasm 60 m deep, a ridge rising at 35 degrees (columns 120-169) to a
    plateau of 40 x 40 m (rows 80-119, columns 170-209): with width 1 a knife edge (its sides 1 m, then 4 m lower),
    with width 5 a flat crest 5 m wide."""
    z = tilted(200, 300)
    out = z - 60.0
    out[:, :120] = z[:, :120]
    top = z[100, 119] + 0.7 * (np.arange(120, 170) - 119)
    half = width // 2
    out[100 - half:101 + half, 120:170] = top[None, :]
    if width == 1:
        out[99, 120:170] = out[101, 120:170] = top - 1.0
        out[98, 120:170] = out[102, 120:170] = top - 4.0
    out[80:120, 170:210] = top[-1] + 0.05 * np.arange(40)[None, :] + 0.02 * np.arange(40)[:, None]
    return out.astype(np.float32)


def test_knife_edge_crest():
    """The plateau beyond a knife-edge ridge of 35 degrees: the strict walk does not take a crest, the loose one
    does: cannot tell. The same ridge 5 m wide: can walk."""
    knife = ridge(1)
    assert access.crest(knife, 1.0)[100, 145] and access.slope_deg(knife, 1.0)[100, 145] < access.WALK_DEG
    assert access.access_grid(knife, None, 1.0, alpine=False)[100, 190] == UNSURE
    assert access.access_grid(ridge(5), None, 1.0, alpine=False)[100, 190] == CAN


def lake(whole=False):
    """A lake of 120 x 120 m at 100 m (1 m pixels) with an island of 19 x 19 m rising 1.5 m in its middle, in a
    meadow rising from its shore."""
    z = tilted(260, 260, base=100.5)
    r, c = np.mgrid[0:260, 0:260]
    water = (r >= 70) & (r < 190) & (c >= 70) & (c < 190)
    z[water] = 100.0
    d = np.maximum(np.abs(r - 130), np.abs(c - 130))
    island = d < 10
    z[island] = 100.1 + 1.5 * (1 - d[island] / 10.0)
    water &= ~island
    z = z.astype(np.float32)
    return (np.round(z).astype(np.float32) if whole else z), water


def test_water():
    """An island in a lake: cannot walk with the app's water; also without it when the lake is held as flat data on
    float heights; on whole-metre heights a flat lake is ground (it cannot be told from a flat field): can walk."""
    z, water = lake()
    assert access.access_grid(z, water, 1.0, alpine=False)[130, 130] == CANNOT
    assert access.access_grid(z, None, 1.0, alpine=False)[130, 130] == CANNOT
    with_lake_as_ground = z.copy()
    with_lake_as_ground[water] += np.random.default_rng(1).random(int(water.sum())).astype(np.float32)
    assert access.access_grid(with_lake_as_ground, None, 1.0, alpine=False)[130, 130] == CAN  # not flat: ground
    whole, _ = lake(whole=True)
    assert access.whole_metres(whole.ravel())
    assert access.access_grid(whole, None, 1.0, alpine=False)[130, 130] == CAN


def test_water_mask_alone_decides():
    """Where the heights cannot tell the lake (not flat; or whole metres, where flat lakes count as ground), only the
    water the caller passes keeps the island cut off: can walk without it, cannot walk with it."""
    z, water = lake()
    rough_lake = z.copy()
    rough_lake[water] += np.random.default_rng(1).random(int(water.sum())).astype(np.float32)
    whole, _ = lake(whole=True)
    for heights in (rough_lake, whole):
        assert access.access_grid(heights, None, 1.0, alpine=False)[130, 130] == CAN
        assert access.access_grid(heights, water, 1.0, alpine=False)[130, 130] == CANNOT


def test_walk_metric_and_limit():
    """The walk itself: steps along an axis cost res, diagonal steps res * sqrt(2), and a pixel is reached when its
    path is at most the limit (REACH_M in the measure) long."""
    for res in (1.0, 2.0):
        line = np.zeros((1, 600), bool)
        line[0, :] = True
        source = np.zeros_like(line)
        source[0, 0] = True
        reached = access._walk(line, source, res, 500.0)
        assert reached[0, int(500 / res)] and not reached[0, int(500 / res) + 1]
        n = 400
        diagonal = np.eye(n, dtype=bool)
        source = np.zeros_like(diagonal)
        source[0, 0] = True
        reached = access._walk(diagonal, source, res, 500.0)
        k = int(500 / (res * np.sqrt(2)))  # 353 steps of 1.414 m: 499.2 m
        assert reached[k, k] and not reached[k + 1, k + 1]


def corridor():
    """A meadow (columns 0-119, 1 m pixels), from its edge a ramp of 35 degrees (columns 120-127) and a corridor of
    gentle ground 5 m wide (rows 98-102, columns 128-700) between drops of 30 m: its middle 3 m are walkable, its
    1800 m2 no open ground of their own, so only the walk from the meadow reaches it (column c: c - 119 m along it)."""
    z = tilted(200, 760) - 30.0
    z[:, :120] += 30.0
    c = np.arange(120, 701)
    path = z[100, 119] + np.where(c < 128, 0.7 * (c - 119), 0.7 * 8 + 0.1 * (c - 127))
    z[98:103, 120:701] = path[None, :]
    return z.astype(np.float32)


def test_walk_of_500_m():
    """Along the corridor: its standing ground 3 m back at 500 m of walk can walk (column 622), 504 m cannot."""
    z = corridor()
    grid = access.access_grid(z, None, 1.0, alpine=False)
    assert access.slope_deg(z, 1.0)[100, 121:126].min() > access.OPEN_DEG
    assert grid[100, 400] == CAN and grid[100, 622] == CAN
    assert grid[100, 626] == CANNOT


def buoy(gap_m):
    """At 0.5 m: a meadow (columns 0-199) at a lake's level (columns 200-), passed as water; a pixel in the lake
    `gap_m` metres from the nearest walkable shore pixel (column 199)."""
    z = 100 + 0.05 * np.mgrid[0:300, 0:300][0] + np.random.default_rng(0).random((300, 300)) * 0.02
    water = np.zeros(z.shape, bool)
    water[:, 200:] = True
    return z.astype(np.float32), water, (150, 199 + int(round(gap_m / 0.5)))


@pytest.mark.parametrize("gap_m, answer", [(2.5, CAN), (3.0, CAN), (4.0, CANNOT)])
def test_standing_ground_within_3_m(gap_m, answer):
    """Standing ground counts within STAND_M = 3 m of the anchor (at its level): 2.5 m and 3 m do, 4 m does not."""
    z, water, pixel = buoy(gap_m)
    assert access.access_grid(z, water, 0.5, alpine=False)[pixel] == answer


def test_at_refuses_pixels_outside_the_grid():
    grid = np.arange(12, dtype=np.uint8).reshape(3, 4)
    assert list(access.at(grid, [[0, 0], [2, 3]])) == [0, 11]
    for bad in ([[-1, 0]], [[0, -1]], [[3, 0]], [[0, 4]]):
        with pytest.raises(ValueError):
            access.at(grid, bad)


def alpine(meadow):
    """1.2 km at 2 m: steep sinusoidal ground (up to about 74 degrees, no gentle region of 1 ha); with `meadow`, a
    gentle meadow over the left 40 % of the grid."""
    r, c = np.mgrid[0:600, 0:600].astype(np.float64) * 2.0
    z = 1000 + 100 * np.sin(r / 40.0) + 100 * np.sin(c / 40.0)
    if meadow:
        z[:, :240] = 700 + 0.1 * c[:, :240]
    return z.astype(np.float32)


def test_alpine_variant():
    """A mid-face pixel on alpine ground: cannot walk in the study's main measure, cannot tell with the variant (no
    open ground within 250 m); where a meadow takes a large share of the square it stays cannot walk."""
    z = alpine(False)
    pixel = (300, 340)
    assert access.slope_deg(z, 2.0)[pixel] > 55
    assert access.access_grid(z, None, 2.0, alpine=False)[pixel] == CANNOT
    assert access.access_grid(z, None, 2.0)[pixel] == UNSURE
    z = alpine(True)
    assert access.access_grid(z, None, 2.0, alpine=False)[pixel] == CANNOT
    assert access.access_grid(z, None, 2.0)[pixel] == CANNOT


def rough(seed=3, n=700):
    """Made-up hills, walls and noise (all three answers at 2 m), float heights."""
    rng = np.random.default_rng(seed)
    z = ndimage.gaussian_filter(rng.normal(0, 1, (n, n)), 20) * 3000
    for _ in range(12):
        r, c = rng.integers(0, n, 2)
        z[r:r + rng.integers(20, 120), c:] += rng.uniform(10, 40)
    z += rng.random((n, n)) * 0.6
    return z.astype(np.float32)


def test_threads_give_the_same_grid():
    import numba
    z = rough(n=400)
    most = numba.config.NUMBA_NUM_THREADS
    grids = []
    try:
        for threads in sorted({1, min(3, most), most}):
            numba.set_num_threads(threads)
            grids.append(access.access_grid(z, None, 2.0))
    finally:
        numba.set_num_threads(most)
    assert set(np.unique(grids[0])) == {CAN, UNSURE, CANNOT}
    for g in grids[1:]:
        assert np.array_equal(g, grids[0])


def test_a_window_with_the_margin_gives_the_grids_answers():
    """The core of a window with MARGIN_M around it reads as the whole grid (where the window reaches the grid's
    edge, its edge is the grid's)."""
    res = 2.0
    z = rough(n=900)
    whole = access.access_grid(z, None, res)
    m = int(np.ceil(access.MARGIN_M / res))
    for r0, c0 in ((300, 300), (0, 450), (600, 100)):
        w0r, w0c = max(0, r0 - m), max(0, c0 - m)
        part = access.access_grid(z[w0r:r0 + 200 + m, w0c:c0 + 200 + m], None, res)
        got = part[r0 - w0r:r0 - w0r + 200, c0 - w0c:c0 - w0c + 200]
        assert np.array_equal(got, whole[r0:r0 + 200, c0:c0 + 200]), (r0, c0)
    assert set(np.unique(whole[300:500, 300:500])) == {CAN, UNSURE, CANNOT}


def test_a_window_cutting_a_thin_open_strip():
    """The study's noted exception: an open strip of 8 m reaching in from a meadow beyond the window's margin has
    less than 1 ha inside the window, so there it is no open ground: its far end reads can walk in the whole grid,
    cannot walk (the main measure) or cannot tell (the variant: no open ground around) in the window. The search
    computes one grid for the whole area, so its tiles never meet this."""
    res = 2.0
    r, c = np.mgrid[0:300, 0:900].astype(np.float64) * res
    z = 1000 + 1.6 * r  # a plane of 58 degrees
    z[:, :150] = 1000 + 0.1 * c[:, :150]  # a meadow of 18 ha (columns 0-149)
    z[144:150, 150:600] = 1000 + 0.1 * c[144:150, 150:600]  # a trench along the columns, its middle 4 pixels gentle
    z = z.astype(np.float32)
    whole = access.access_grid(z, None, res)
    c0 = 590 - int(np.ceil(access.MARGIN_M / res))  # the window's edge cuts the strip
    assert whole[147, 590] == CAN
    assert access.access_grid(z[:, c0:], None, res, alpine=False)[147, 590 - c0] == CANNOT
    assert access.access_grid(z[:, c0:], None, res)[147, 590 - c0] == UNSURE


# --- The grid-wide pass of the grid in blocks (access.block_grid), its parts alone ---

def _sample_grid(kind: str, rows: int = 64 * 12 + 5, cols: int = 300, seed: int = 0):
    """Heights for the whole-metre sample: whole metres, float, whole metres on a share near WHOLE_METRE_SHARE, with
    a strip without data; also a water and a filled mask."""
    rng = np.random.default_rng(seed)
    z = (100 + rng.random((rows, cols)) * 50).astype(np.float32)
    if kind in ("whole", "no-data-strip"):
        z = np.round(z)
    if kind == "share":  # 90 % whole metres give or take a little: the sample's every pixel counts
        z = np.where(rng.random((rows, cols)) < 0.9 + rng.uniform(-0.01, 0.01), np.round(z), z).astype(np.float32)
    if kind == "no-data-strip":
        z[64 * 3:64 * 4 + 7] = np.nan
    z[rng.random((rows, cols)) < 0.05] = np.nan
    water = rng.random((rows, cols)) < 0.1
    filled = rng.random((rows, cols)) < 0.2
    return z.astype(np.float32), water, filled


@pytest.mark.parametrize("kind", ["whole", "float", "share", "no-data-strip"])
def test_whole_metre_sample_in_strips(monkeypatch, kind):
    """access._whole_metres_rows (the grid in blocks, strip by strip) = whole_metres(z[data]) of the grid at once: on
    whole metres, float, a share near the threshold and with a strip without data; with a sample step of 1 and over 1,
    without and with water and filled pixels."""
    monkeypatch.setattr(access, "STRIP_PX", 1)  # 64 rows a strip
    for seed in range(6):
        z, water, filled = _sample_grid(kind, seed=seed)
        for sample in (access.WHOLE_METRE_SAMPLE, 997):  # a step of 1, and of about 220
            monkeypatch.setattr(access, "WHOLE_METRE_SAMPLE", sample)
            for wat, fil in ((None, None), (water, filled)):
                data = np.isfinite(z)
                if fil is not None:
                    data &= ~(fil & ~wat)
                assert access._whole_metres_rows(z, wat, fil) == access.whole_metres(z[data]), (seed, sample)
    if kind in ("whole", "no-data-strip"):
        assert access._whole_metres_rows(z, None, None)
    if kind == "float":
        assert not access._whole_metres_rows(z, None, None)


def test_whole_metre_sample_keeps_no_strip(monkeypatch):
    """The sample keeps its picked heights only, not every strip's heights with data: Python's traced peak of the call
    on a grid of 80 strips stays under half of its heights (the strips' views kept until the sample is joined held
    them all)."""
    import tracemalloc
    monkeypatch.setattr(access, "STRIP_PX", 1)  # 64 rows a strip
    z = np.round(100 + np.random.default_rng(0).random((64 * 80, 500)) * 50).astype(np.float32)
    tracemalloc.start()
    try:
        assert access._whole_metres_rows(z, None, None)
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    assert peak < z.nbytes / 2, (peak, z.nbytes)


EIGHT = np.ones((3, 3), bool)


def _spiral(n=200):
    """A square spiral of width 1 with gaps of 1: one region winding through every strip many times."""
    m = np.zeros((n, n), bool)
    r0, c0, r1, c1 = 0, 0, n - 1, n - 1
    while r0 <= r1 and c0 <= c1:
        m[r0, c0:c1 + 1] = True
        m[r0:r1 + 1, c1] = True
        if r1 > r0:
            m[r1, c0:c1 + 1] = True
        if c1 > c0 + 2:
            m[r0 + 2:r1 + 1, c0] = True
        if c0 + 2 <= c1 - 2 and r0 + 2 < r1:
            m[r0 + 2, c0:c0 + 3] = True  # step inward
        r0, c0, r1, c1 = r0 + 2, c0 + 2, r1 - 2, c1 - 2
    return m


def _comb(rows=300, cols=161):
    """Teeth of width 1 (gaps of 1) through five strips, joined only by the last row."""
    m = np.zeros((rows, cols), bool)
    m[:, ::2] = True
    m[:-1, 1::2] = False
    m[-1] = True
    return m


def _u_below():
    """A U whose arms (strips 0 to 2) join only in strip 3; a second U inside it, joined in strip 2; an H whose bar lies
    on a seam's first row; two arms carried side by side that join in the next strip only by a diagonal."""
    m = np.zeros((280, 120), bool)
    m[0:250, 5] = m[0:250, 60] = True
    m[249, 5:61] = True
    m[10:150, 20] = m[10:150, 40] = True
    m[149, 20:41] = True
    m[0:200, 80] = m[0:200, 90] = True
    m[128, 80:91] = True  # the H's bar on the first row of strip 2
    m[0:191, 100] = True
    m[192, 102] = True  # 100 -> 101 -> 102 by diagonals across the seam of rows 191/192
    m[191, 101] = True
    m[0:192, 104] = True
    m[192, 103] = True  # the second arm reaches 102 by another diagonal
    return m


def _diagonals(rows=260, cols=200):
    """Lines one pixel wide at 45 degrees both ways, each crossing the seams only by a diagonal step."""
    m = np.zeros((rows, cols), bool)
    r = np.arange(rows)
    for k in range(-rows, cols, 9):
        c = k + r
        ok = (c >= 0) & (c < cols)
        m[r[ok], c[ok]] = True
    for k in range(0, cols + rows, 23):
        c = k - r
        ok = (c >= 0) & (c < cols)
        m[r[ok], c[ok]] = True
    return m


def _random(rows, cols, share, seed):
    return np.random.default_rng(seed).random((rows, cols)) < share


def _empty_strip():
    m = _random(64 * 4, 150, 0.5, 5)
    m[64:128] = False
    m[60:64, 70:80] = True  # a region ending on a strip's last row before an empty strip
    return m


REGION_MASKS = {
    "random-sparse": lambda: _random(300, 257, 0.3, 1),
    "random-near-percolation": lambda: _random(320, 240, 0.42, 2),
    "random-dense": lambda: _random(300, 257, 0.6, 3),
    "comb": _comb,
    "spiral": _spiral,
    "u-below": _u_below,
    "diagonals": _diagonals,
    "width-1": lambda: _random(400, 1, 0.7, 4),
    "shorter-than-a-strip": lambda: _random(40, 100, 0.5, 6),
    "last-strip-one-row": lambda: _random(64 * 3 + 1, 90, 0.5, 7),
    "empty": lambda: np.zeros((200, 100), bool),
    "full": lambda: np.ones((200, 100), bool),
    "empty-strip-between": _empty_strip,
}


def _mask_file(tmp_path, mask):
    m = access._Mask(str(tmp_path / "mask.npy"), mask.shape)
    m.write(0, mask.shape[0], mask)
    m.flush()
    return m


def _regions_of(tmp_path, m, judge, heights=None, strips=None):
    rows = None if heights is None else (lambda r0, r1: heights[r0:r1])
    return access._Regions(m, str(tmp_path / "regions.bin"), judge, heights=rows, strips=strips)


def _check_regions(tmp_path, mask, strips=None):
    """_Regions of the mask in strips (64 rows, or `strips`) against ndimage.label of the whole mask: every region an
    open question, their codes one to one with the whole mask's labels, their pixels, lowest and highest height and
    first and last strip; then kept by a size, pixel for pixel."""
    h, w = mask.shape
    heights = (np.random.default_rng(9).normal(0, 300, (h, w))).astype(np.float32)
    lab, n = ndimage.label(mask, structure=EIGHT)
    count = np.bincount(lab.ravel(), minlength=n + 1)
    m = _mask_file(tmp_path, mask)
    regions = _regions_of(tmp_path, m, lambda p, lo, hi: np.full(len(p), access.ASK), heights, strips)
    bounds = regions.strips
    assert bounds[0][0] == 0 and bounds[-1][1] == h and all(a[1] == b[0] for a, b in zip(bounds, bounds[1:]))
    codes = np.concatenate([regions.codes(s) for s in range(len(bounds))])
    assert codes.shape == mask.shape and np.array_equal(codes >= access.ASK, mask)
    q = regions.questions
    assert len(q["pixels"]) == n
    if n:
        pairs = np.unique(np.stack([lab[mask], codes[mask] - access.ASK]), axis=1)
        assert pairs.shape[1] == n  # one question per label and one label per question
        of = np.empty(n + 1, np.int64)
        of[pairs[0]] = pairs[1]
        labels = np.arange(1, n + 1)
        assert np.array_equal(np.array(q["pixels"])[of[1:]], count[1:])
        assert np.array_equal(np.array(q["lowest"])[of[1:]], ndimage.minimum(heights, lab, labels).astype(np.float64))
        assert np.array_equal(np.array(q["highest"])[of[1:]], ndimage.maximum(heights, lab, labels).astype(np.float64))
        strip_of = np.zeros(h, np.int64)
        for s, (r0, r1) in enumerate(bounds):
            strip_of[r0:r1] = s
        rows = [sl[0] for sl in ndimage.find_objects(lab)]
        assert np.array_equal(np.array(q["first"])[of[1:]], strip_of[[r.start for r in rows]])
        assert np.array_equal(np.array(q["last"])[of[1:]], strip_of[[r.stop - 1 for r in rows]])
    regions.remove()
    for least in (1, 3, 40, 500):
        regions = _regions_of(tmp_path, m, lambda p, lo, hi, least=least: np.where(p >= least, access.KEEP,
                                                                                          access.DROP),
                              strips=strips)
        kept = np.concatenate([regions.kept(s) for s in range(len(regions.strips))])
        big = count >= least
        big[0] = False
        assert np.array_equal(kept, big[lab]), least
        assert not regions.questions["pixels"]
        regions.remove()
    m.remove()
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("case", list(REGION_MASKS))
def test_regions_in_strips_are_the_whole_masks(tmp_path, monkeypatch, case):
    """access._Regions (the grid in blocks: regions labelled strip by strip, joined across the seams, no label array of
    the whole grid) = ndimage.label of the whole mask, on made-up masks in strips of 64 rows; no file left."""
    monkeypatch.setattr(access, "STRIP_PX", 1)  # 64 rows a strip
    _check_regions(tmp_path, REGION_MASKS[case]())


@pytest.mark.parametrize("case", ["random-near-percolation", "comb", "spiral", "u-below", "diagonals", "full"])
def test_regions_in_strips_of_any_height(tmp_path, case):
    """The same with strips of uneven heights, strips of one row among them."""
    mask = REGION_MASKS[case]()
    h = mask.shape[0]
    cuts = sorted({0, h, *[c for c in (1, 2, 3, 50, 51, 64, 65, 66, 128, 129, 191, 192, 193, 250) if c < h]})
    _check_regions(tmp_path, mask, strips=list(zip(cuts, cuts[1:])))


def test_a_strip_labelled_twice_gives_the_same_labels(tmp_path, monkeypatch):
    """ndimage.label of a strip's rows (copied from the memory-mapped mask) gives the same labels every time, and so
    _Regions' reading gives the same codes: the reading sweep relies on it."""
    monkeypatch.setattr(access, "STRIP_PX", 1)
    mask = _random(320, 240, 0.42, 2)
    m = _mask_file(tmp_path, mask)
    regions = _regions_of(tmp_path, m, lambda p, lo, hi: np.where(p > 30, access.ASK, access.KEEP))
    for s, (r0, r1) in enumerate(regions.strips):
        first = ndimage.label(m.rows(r0, r1), structure=EIGHT)
        again = ndimage.label(m.rows(r0, r1), structure=EIGHT)
        assert first[1] == again[1] and np.array_equal(first[0], again[0])
        assert np.array_equal(regions.codes(s), regions.codes(s))
    regions.remove()
    m.remove()


def _written_in_the_sweep(tmp_path, mask, least, strips=None):
    """The open ground's way (access._open_ground_rows): regions of at least `least` pixels kept, written over the
    mask in the forward sweep (pieces of regions still growing below stay), those whose region is not kept taken out
    by a visit of their records afterwards. Returns the mask so written and the tables file's size before removal."""
    m = _mask_file(tmp_path, mask)

    def write(regions, s, labels, final):
        r0, r1 = regions.strips[s]
        m.write(r0, r1, ((final == access.KEEP) | (final < 0))[labels])

    regions = access._Regions(m, str(tmp_path / "regions.bin"),
                              lambda p, lo, hi: np.where(p >= least, access.KEEP, access.DROP), strips=strips,
                              settled=lambda p: np.where(p >= least, access.KEEP, -1), on_strip=write)
    for s in range(len(regions.strips)):
        records = regions.records(s)
        assert ((records[:, 6] == access.KEEP) | (records[:, 6] == access.DROP)).all()
        for a, b, c, d, labels, ids, _ in regions.visit(s, records[records[:, 6] != access.KEEP]):
            drop = np.zeros(int(labels.max()) + 1, bool)
            drop[ids] = True
            rows = m.rows(a, b)
            rows[:, c:d] &= ~drop[labels]
            m.write(a, b, rows)
    size = os.path.getsize(tmp_path / "regions.bin")
    regions.remove()
    got = m.rows(0, mask.shape[0])
    m.remove()
    assert not list(tmp_path.iterdir())
    return got, size


@pytest.mark.parametrize("case", list(REGION_MASKS))
def test_regions_written_in_the_sweep_are_the_whole_masks(tmp_path, monkeypatch, case):
    """Regions written over their mask in the forward sweep (wave 2a: no second labelling of every strip), the
    pending pieces of regions not kept taken out by visits of their records = ndimage.label of the whole mask, kept by
    a size, pixel for pixel; in strips of 64 rows and in uneven strips with one-row strips."""
    monkeypatch.setattr(access, "STRIP_PX", 1)  # 64 rows a strip
    mask = REGION_MASKS[case]()
    h = mask.shape[0]
    lab, n = ndimage.label(mask, structure=EIGHT)
    count = np.bincount(lab.ravel(), minlength=n + 1)
    cuts = sorted({0, h, *[c for c in (1, 2, 3, 50, 51, 64, 65, 66, 128, 129, 191, 192, 193, 250) if c < h]})
    for strips in (None, list(zip(cuts, cuts[1:]))):
        for least in (1, 3, 40, 500):
            big = count >= least
            big[0] = False
            got, _ = _written_in_the_sweep(tmp_path, mask, least, strips)
            assert np.array_equal(got, big[lab]), (least, strips is None)


def test_a_strips_verdicts_given_and_visited_are_its_codes(tmp_path, monkeypatch):
    """What the forward sweep hands a strip's caller (the verdict of every piece not pending) and what the visits of
    its records give its pending pieces afterwards (their verdicts resolved by the backward sweep) = the strip's
    codes, at every pixel, on every made-up mask: every region an open question, none settled."""
    monkeypatch.setattr(access, "STRIP_PX", 1)
    for case, make in REGION_MASKS.items():
        mask = make()
        m = _mask_file(tmp_path, mask)
        given = {}

        def keep(regions, s, labels, final):
            given[s] = final[labels]

        regions = access._Regions(m, str(tmp_path / "regions.bin"), lambda p, lo, hi: np.full(len(p), access.ASK),
                                  on_strip=keep)
        for s, (r0, r1) in enumerate(regions.strips):
            got = given[s].copy()
            for a, b, c, d, labels, ids, records in regions.visit(s, regions.records(s)):
                code = np.zeros(int(labels.max()) + 1, np.int32)
                code[ids] = records[:, 6]
                part, mine = got[a - r0:b - r0, c:d], np.isin(labels, ids)
                part[mine] = code[labels][mine]
            assert (got >= 0).all() and np.array_equal(got, regions.codes(s)), (case, s)
        regions.remove()
        m.remove()


def test_the_tables_file_at_its_worst(tmp_path, monkeypatch):
    """The regions' scratch file in the worst made-up cases, strips of 64 rows (the least a strip has): isolated
    pixels (a piece every 4 pixels, and every one in a strip's first and last row pending) and a comb of teeth one
    pixel apart: under 2 B per pixel of the grid (pieces 1 B, records 1/2 B, classes carried in 1/32 B)."""
    monkeypatch.setattr(access, "STRIP_PX", 1)
    dots = np.zeros((64 * 6, 400), bool)
    dots[1::2, ::2] = True  # odd rows: every strip's last row full of pending pieces
    for mask in (dots, _comb(64 * 6, 401)):
        _, size = _written_in_the_sweep(tmp_path, mask, 10 ** 9)
        assert size / mask.size < 2, size / mask.size


def test_a_closed_mask_lets_its_map_go(tmp_path):
    """_Mask.close: the map is let go (Windows renames a mapped file only once no view of it is left) and the next read
    maps the file again, read only, with what was written."""
    rows = np.random.default_rng(0).random((70, 33)) < 0.5
    m = access._Mask(str(tmp_path / "m.npy"), rows.shape)
    m.write(0, 70, rows)
    m.close()
    os.rename(tmp_path / "m.npy", tmp_path / "n.npy")
    os.rename(tmp_path / "n.npy", tmp_path / "m.npy")
    assert np.array_equal(m.rows(0, 70), rows) and np.array_equal(m.window(3, 9, 5, 30), rows[3:9, 5:30])
    m.remove()
    assert not list(tmp_path.iterdir())


def _bits(x) -> bytes:
    return np.float32(x).tobytes()


def _pieces(v: np.ndarray, rng, parts: int):
    """chunks() of v cut at random places (a region's heights strip by strip), views only."""
    cuts = np.sort(rng.integers(0, len(v) + 1, max(0, parts - 1)))
    bounds = [0, *cuts.tolist(), len(v)]
    return lambda: (v[a:b] for a, b in zip(bounds, bounds[1:]))


def _key_range(v: np.ndarray):
    lo, hi = float(v.min()), float(v.max())
    return access._key_range(lo, hi)


def _made_up_region(rng, n: int, kind: int) -> np.ndarray:
    if kind == 0:
        return rng.normal(100, 50, n).astype(np.float32)
    if kind == 1:  # ties, negative heights
        return np.round(rng.normal(0, 3, n), 1).astype(np.float32)
    if kind == 2:  # a spread near 0.3 m: one float32 step each side of it at the ends
        v = (1000 + rng.random(n) * 0.3).astype(np.float32)
        if n > 2:
            v[0] = np.float32(1000.0)
            v[1] = np.nextafter(np.float32(1000.3), np.float32(rng.choice([0, 2000])))
        return v
    if kind == 3:
        return rng.integers(-5, 5, n).astype(np.float32)
    if kind == 4:  # the sea's fill: most heights one value, the rest near it
        v = np.zeros(n, np.float32) + np.float32(0.25)
        some = rng.random(n) < 0.1
        v[some] = rng.normal(0.25, 0.2, int(some.sum())).astype(np.float32)
        return v
    return -rng.random(n).astype(np.float32) * 1e-3  # all negative, close together


def test_percentile_without_the_heights_is_numpys(monkeypatch):
    """access._percentile_of (spec B: p5 and p95 of a large flat region from filling._select on its heights strip by
    strip, joined as numpy joins them) = np.percentile(v, q, overwrite_input=True) to the last bit, two calls with a
    scalar q as flat_water makes them, on 10 000 made-up regions (sizes 1 to 10^6, ties, negative heights, sizes whose
    rank is whole, spreads one float32 step each side of 0.3 m, a sea's fill), each cut into a random number of
    strips; a fifth of them with filling's selection narrowed (16 bins, 64 values collected) so that its many passes,
    its pair split into two and its single key are used; and the spread's verdict is flat_water's."""
    from sources import filling
    rng = np.random.default_rng(11)
    sizes = np.concatenate([np.arange(1, 60), 20 * np.arange(1, 40) + 1, rng.integers(1, 3000, 9_200),
                            np.round(10 ** rng.uniform(3.5, 6, 750)).astype(int), [10 ** 6, 10 ** 6 - 1]])
    checked = 0
    for j, n in enumerate(sizes.tolist()):
        v = _made_up_region(rng, n, j % 6)
        lo, hi = _key_range(v)
        narrow = j % 5 == 0 and n < 50_000
        with monkeypatch.context() as m:
            if narrow:
                m.setattr(filling, "SELECT_BINS", 16)
                m.setattr(filling, "SELECT_COLLECT", 64)
            chunks = _pieces(v, rng, int(rng.integers(1, 12)))
            got = {q: access._percentile_of(chunks, n, q, lo, hi) for q in (95, 5)}
        for q in (95, 5):
            want = np.percentile(v.copy(), q, overwrite_input=True)
            assert _bits(got[q]) == _bits(want), (n, j % 6, q, got[q], want)
            assert type(got[q]) is type(want)
        assert ((got[95] - got[5]) <= access.FLAT_WATER_SPREAD_M) == \
            ((np.percentile(v, 95) - np.percentile(v, 5)) <= access.FLAT_WATER_SPREAD_M)
        checked += 1
    assert checked >= 10_000


def test_percentile_without_the_heights_at_the_spreads_edge():
    """Regions whose lowest and highest tenths are constants a and b, b - a one float32 step either side of
    FLAT_WATER_SPREAD_M as flat_water's comparison sees it (so p95 - p5 is b - a): the percentiles are numpy's bit for
    bit and both verdicts occur, each numpy's."""
    rng = np.random.default_rng(8)
    a = np.float32(1000.0)
    b = np.float32(1000.3)
    while (b - a) <= access.FLAT_WATER_SPREAD_M:  # the first b over the edge, then the last one at it
        b = np.nextafter(b, np.float32(2000))
    while (b - a) > access.FLAT_WATER_SPREAD_M:
        b = np.nextafter(b, np.float32(0))
    over = np.nextafter(b, np.float32(2000))
    verdicts = set()
    for top in (b, over):
        for n in (100, 1001, 20_001, 300_007):
            v = (a + rng.random(n).astype(np.float32) * (top - a)).astype(np.float32)
            v[: n // 10 + 2], v[-(n // 10 + 2):] = a, top
            rng.shuffle(v)
            lo, hi = _key_range(v)
            chunks = _pieces(v, rng, 5)
            got = {q: access._percentile_of(chunks, n, q, lo, hi) for q in (95, 5)}
            want = {q: np.percentile(v.copy(), q, overwrite_input=True) for q in (95, 5)}
            assert all(_bits(got[q]) == _bits(want[q]) for q in (95, 5)), (n, got, want)
            assert want[95] == top and want[5] == a
            verdict = bool(want[95] - want[5] <= access.FLAT_WATER_SPREAD_M)
            assert bool(got[95] - got[5] <= access.FLAT_WATER_SPREAD_M) == verdict
            verdicts.add((top == b, verdict))
    assert verdicts == {(True, True), (False, False)}


def test_percentile_without_the_heights_of_mixed_zeros():
    """Heights of 0.0 and -0.0 together (keys -1 and 0): the range of keys widened at zero, so none is left out; the
    verdict is numpy's (the sign of a zero numpy returns depends on its partition's order, not on the values)."""
    rng = np.random.default_rng(5)
    for n in (2, 3, 21, 1000, 20_001):
        v = np.where(rng.random(n) < 0.5, np.float32(0.0), np.float32(-0.0)).astype(np.float32)
        v[: n // 10] = rng.random(n // 10).astype(np.float32) * 0.5
        for lowest, highest in ((float(v.min()), float(v.max())), (0.0, float(v.max())), (-0.0, 0.0 + float(v.max()))):
            lo, hi = access._key_range(lowest, highest)
            chunks = _pieces(v, rng, 4)
            for q in (95, 5):
                got, want = access._percentile_of(chunks, n, q, lo, hi), np.percentile(v.copy(), q)
                assert got == want, (n, q, got, want)


def test_percentile_without_the_heights_of_large_regions():
    """The same on regions over 2^24 pixels (the sizes B decides in a search, over GATHER_PX), among them sizes whose
    n - 1 is not a float32 number (a rank computed in float32 picks another index there): consecutive float32 bit
    patterns, shuffled (the result's bits show the index picked), and widely spaced ones (the weight matters). One
    array at a time, up to 135 MB, freed before the next."""
    rng = np.random.default_rng(3)
    for n in (16_777_217, 16_777_218, 16_777_220, 20_000_002, 33_554_435, 33_554_436):
        for spaced in (False, True):
            u = np.arange(n, dtype=np.uint32)
            if spaced:
                u *= np.uint32(1024)  # modulo 2^32
                u &= np.uint32((1 << 30) - 1)
            u += np.uint32(0x3F800000)  # from 1.0 up, at most the largest finite float32
            v = u.view(np.float32)
            del u
            rng.shuffle(v)
            lo, hi = _key_range(v)
            chunks = _pieces(v, rng, 9)
            got = {q: access._percentile_of(chunks, n, q, lo, hi) for q in (95, 5)}
            for q in (95, 5):  # numpy partitions v in place: the same values
                assert _bits(got[q]) == _bits(np.percentile(v, q, overwrite_input=True)), (n, spaced, q)
            del v, chunks


LAKE_PX = 2800 * 700


def _wide_flat(rows=64 * 48, cols=700):
    """At 2 m: steep ground (17 degrees) with one large flat region (a lake held as data, 2800 x 700 pixels) whose
    heights spread over FLAT_WATER_SPREAD_M between its lowest and highest (a cone of 0.8 m on 0.4 % of it) but not
    between p5 and p95 (kept only by the exact percentiles), and one of 100 x 500 pixels rising 0.5 m (refused by
    them)."""
    rng = np.random.default_rng(2)
    z = tilted(rows, cols, res=2.0, grade=0.3)
    z[100:2900] = 200.0 + rng.random((2800, cols)) * 0.1
    rr, cc = np.mgrid[100:2900, 0:cols]
    z[100:2900] += np.maximum(0.0, 0.8 * (1 - np.hypot(rr - 1500, cc - 350) / 30.0))
    z[2950:3050, 100:600] = 220.0 + np.linspace(0, 0.5, 100)[:, None]
    return z.astype(np.float32)


@pytest.mark.parametrize("gather_px", [5_000, 4_000_000], ids=["selected", "gathered"])
def test_flat_lakes_in_strips_hold_no_heights_of_a_large_region(tmp_path, monkeypatch, gather_px):
    """The flat lakes of the grid in blocks (access._flat_lakes_rows) = flat_water of the grid at once, pixel for
    pixel, whether an open question over GATHER_PX is answered by the selection (spec B: _spread_large) or by today's
    gather; with the selection Python's traced peak stays under half the large region's heights, which the gather
    holds whole."""
    import tracemalloc
    z = _wide_flat()
    res = 2.0
    want = access.flat_water(z, access.slope_deg(z, res), res)
    monkeypatch.setattr(access, "STRIP_PX", 1)  # 64 rows a strip
    monkeypatch.setattr(access, "GATHER_PX", gather_px)
    large = []
    real = access._spread_large
    monkeypatch.setattr(access, "_spread_large", lambda regions, z, q: large.append(q) or real(regions, z, q))
    wet = access._Mask(str(tmp_path / "wet.npy"), z.shape)
    wet.write(0, z.shape[0], False)
    tracemalloc.start()
    try:
        access._flat_lakes_rows(z, res, str(tmp_path), wet)
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    got = wet.rows(0, z.shape[0])
    wet.remove()
    assert os.listdir(tmp_path) == []
    assert np.array_equal(got, want) and want[600, 300] and want[1500, 350] and not want[3000, 300]
    region = LAKE_PX * 4  # the large region's heights, float32
    if gather_px < LAKE_PX:
        assert len(large) == 2 and peak < region / 2, (large, peak, region)
    else:
        assert not large and peak > region, (peak, region)


def test_speed_logged(record_property):
    """About 0.3 s per megapixel (part P3d, indicative): logged, not asserted."""
    z = rough(n=1000)
    access.access_grid(z[:50, :50], None, 1.0)  # compiled before the clock starts
    t0 = time.perf_counter()
    access.access_grid(z, None, 1.0)
    per_mpx = (time.perf_counter() - t0) / (z.size / 1e6)
    record_property("access_seconds_per_megapixel", round(per_mpx, 3))
    print(f"access: {per_mpx:.2f} s per megapixel")
