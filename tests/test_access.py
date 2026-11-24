"""The access measure (access.py): can a person walk to an anchor? Made-up terrain only: a meadow and a wall, a
ledge in the face, a pillar, ground of 35, 45 and 60 degrees, whole-metre heights, the end of the data, water and
lakes held as data, the alpine variant; threads; a window with the measure's margin against the whole grid and the
study's noted exception; the speed, logged (offline, seconds)."""

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


def test_speed_logged(record_property):
    """About 0.3 s per megapixel (part P3d, indicative): logged, not asserted."""
    z = rough(n=1000)
    access.access_grid(z[:50, :50], None, 1.0)  # compiled before the clock starts
    t0 = time.perf_counter()
    access.access_grid(z, None, 1.0)
    per_mpx = (time.perf_counter() - t0) / (z.size / 1e6)
    record_property("access_seconds_per_megapixel", round(per_mpx, 3))
    print(f"access: {per_mpx:.2f} s per megapixel")
